#include "backlog.h"
#ifdef USE_ESP32
#include "esphome/core/log.h"
#include <cstring>
#include <algorithm>

namespace esphome {
namespace backlog {

static const char *const TAG = "backlog";
BacklogComponent *global_backlog = nullptr;  // NOLINT

void BacklogComponent::setup() {
  global_backlog = this;
  this->part_ = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
                                         (esp_partition_subtype_t) 0x40, "backlog");
  if (this->part_ == nullptr) {
    // Not fatal. A board flashed with the old table simply has no log, and
    // everything else must keep working -- refusing to boot over a missing
    // diagnostic partition would be a far worse failure than the one it
    // diagnoses.
    ESP_LOGE(TAG, "No 'backlog' partition. Events will not be recorded. "
                  "Reflash over USB with the current partitions.csv.");
    this->mark_failed();
    return;
  }

  // Recover the head by scanning. There is no stored write pointer on purpose:
  // a pointer is one more thing that can be stale after a power cut, and a
  // 4096-slot scan costs a few milliseconds once per boot.
  EventRecord r{};
  uint32_t best_seq = 0, best_slot = 0;
  for (uint32_t i = 0; i < EVENT_SLOTS; i++) {
    if (esp_partition_read(this->part_, i * sizeof(EventRecord), &r, sizeof(r)) != ESP_OK)
      continue;
    if (!valid_(r))
      continue;
    this->written_++;
    if (r.seq >= best_seq) {
      best_seq = r.seq;
      best_slot = i;
    }
  }
  // Same scan for the snapshot ring.
  SampleRecord sr{};
  uint32_t sbest = 0, sslot = 0;
  const uint32_t slots = (this->part_->size - SAMPLE_REGION_OFF) / SECTOR_SIZE *
                         SAMPLES_PER_SECTOR;
  for (uint32_t i = 0; i < slots; i++) {
    if (esp_partition_read(this->part_, SAMPLE_REGION_OFF + i * sizeof(SampleRecord),
                           &sr, sizeof(sr)) != ESP_OK)
      continue;
    if (!svalid_(sr))
      continue;
    this->s_written_++;
    if (sr.seq >= sbest) {
      sbest = sr.seq;
      sslot = i;
    }
  }
  this->s_next_ = sbest + 1;
  this->s_slot_ = this->s_written_ ? (sslot + 1) % slots : 0;
  this->s_acked_ = sbest;

  this->next_seq_ = best_seq + 1;
  this->write_slot_ = this->written_ ? (best_slot + 1) % EVENT_SLOTS : 0;
  this->acked_seq_ = best_seq;  // nothing has asked for a replay yet

  ESP_LOGI(TAG, "Snapshot ring: %u records, next seq %u", (unsigned) this->s_written_,
           (unsigned) this->s_next_);
  ESP_LOGI(TAG, "Event log ready: %u records, next seq %u, slot %u",
           (unsigned) this->written_, (unsigned) this->next_seq_,
           (unsigned) this->write_slot_);
  // The BOOT marker is NOT written here. setup() runs long before Home
  // Assistant time arrives, so every boot recorded ts=0 -- and after a few
  // dozen flashes the ring held 181 untimestamped BOOT records against 18
  // alarms. A boot with no time says almost nothing (uptime and reset reason
  // already cover it) while crowding out the one thing that cannot be
  // reconstructed. It is now written once, from loop(), as soon as the clock
  // is real.
}

void BacklogComponent::loop() {
  if (this->boot_logged_ || this->part_ == nullptr || this->time_ == nullptr)
    return;
  auto now = this->time_->now();
  if (!now.is_valid())
    return;
  this->boot_logged_ = true;
  this->record(EVENT_BOOT);
}

void BacklogComponent::record(EventType type, uint8_t index, uint16_t value) {
  if (this->part_ == nullptr)
    return;

  EventRecord r{};
  r.seq = this->next_seq_;
  // A record with ts == 0 is still worth keeping: it says an alarm happened,
  // just not when. Dropping it because the clock had not synced yet would
  // lose exactly the early-boot events most likely to explain a fault.
  r.ts = 0;
  if (this->time_ != nullptr) {
    auto now = this->time_->now();
    if (now.is_valid())
      r.ts = (uint32_t) now.timestamp;
  }
  r.type = type;
  r.index = index;
  r.value = value;
  r.crc = crc_of_(r);

  // Erase the sector before writing its first slot. Flash bits only go 1->0,
  // so a slot cannot be rewritten in place; the ring reclaims a whole sector
  // at a time, which is the smallest unit the hardware can erase.
  if (this->write_slot_ % SLOTS_PER_SECTOR == 0) {
    const uint32_t off = (this->write_slot_ / SLOTS_PER_SECTOR) * SECTOR_SIZE;
    if (esp_partition_erase_range(this->part_, off, SECTOR_SIZE) != ESP_OK) {
      ESP_LOGW(TAG, "Erase failed at 0x%06X; event dropped", (unsigned) off);
      return;
    }
    if (this->written_ >= SLOTS_PER_SECTOR)
      this->written_ -= SLOTS_PER_SECTOR;  // that sector's records are gone
  }

  if (esp_partition_write(this->part_, this->write_slot_ * sizeof(EventRecord),
                          &r, sizeof(r)) != ESP_OK) {
    ESP_LOGW(TAG, "Write failed; event dropped");
    return;
  }
  this->next_seq_++;
  this->written_++;
  this->write_slot_ = (this->write_slot_ + 1) % EVENT_SLOTS;
}

std::vector<EventRecord> BacklogComponent::read_since(uint32_t after_seq) const {
  std::vector<EventRecord> out;
  if (this->part_ == nullptr)
    return out;
  EventRecord r{};
  for (uint32_t i = 0; i < EVENT_SLOTS; i++) {
    if (esp_partition_read(this->part_, i * sizeof(EventRecord), &r, sizeof(r)) != ESP_OK)
      continue;
    if (valid_(r) && r.seq > after_seq)
      out.push_back(r);
  }
  // Slot order is not sequence order once the ring has wrapped.
  std::sort(out.begin(), out.end(),
            [](const EventRecord &a, const EventRecord &b) { return a.seq < b.seq; });
  return out;
}

void BacklogComponent::erase_events() {
  if (this->part_ == nullptr)
    return;
  if (esp_partition_erase_range(this->part_, 0, EVENT_REGION_SIZE) != ESP_OK) {
    ESP_LOGE(TAG, "Event ring erase FAILED");
    return;
  }
  this->next_seq_ = 1;
  this->write_slot_ = 0;
  this->written_ = 0;
  this->acked_seq_ = 0;
  this->boot_logged_ = false;   // a fresh BOOT marker will open the new log
  ESP_LOGW(TAG, "Event ring erased; log restarts at seq 1");
}

void BacklogComponent::record_sample(const uint16_t *values) {
  if (this->part_ == nullptr)
    return;
  SampleRecord r{};
  r.seq = this->s_next_;
  r.ts = 0;
  if (this->time_ != nullptr) {
    auto now = this->time_->now();
    if (now.is_valid())
      r.ts = (uint32_t) now.timestamp;
  }
  // A snapshot with no timestamp cannot be filed into an hourly bucket, so
  // unlike an event it is genuinely useless. Drop it rather than store a
  // record the consumer will only throw away.
  if (r.ts == 0)
    return;
  for (uint32_t i = 0; i < SNAPSHOT_SLOTS; i++)
    r.v[i] = values[i];
  r.crc = scrc_(r);

  const uint32_t slots = this->sample_slots_();
  if (this->s_slot_ % SAMPLES_PER_SECTOR == 0) {
    const uint32_t off = SAMPLE_REGION_OFF +
                         (this->s_slot_ / SAMPLES_PER_SECTOR) * SECTOR_SIZE;
    if (esp_partition_erase_range(this->part_, off, SECTOR_SIZE) != ESP_OK)
      return;
    if (this->s_written_ >= SAMPLES_PER_SECTOR)
      this->s_written_ -= SAMPLES_PER_SECTOR;
  }
  const uint32_t off = SAMPLE_REGION_OFF + this->s_slot_ * sizeof(SampleRecord);
  if (esp_partition_write(this->part_, off, &r, sizeof(r)) != ESP_OK)
    return;
  this->s_next_++;
  this->s_written_++;
  this->s_slot_ = (this->s_slot_ + 1) % slots;
}

std::string BacklogComponent::sample_batch(uint32_t limit) const {
  if (this->part_ == nullptr)
    return std::string(EMPTY_MARKER);
  std::vector<SampleRecord> found;
  SampleRecord r{};
  const uint32_t slots = this->sample_slots_();
  for (uint32_t i = 0; i < slots; i++) {
    const uint32_t off = SAMPLE_REGION_OFF + i * sizeof(SampleRecord);
    if (esp_partition_read(this->part_, off, &r, sizeof(r)) != ESP_OK)
      continue;
    if (svalid_(r) && r.seq > this->s_acked_)
      found.push_back(r);
  }
  std::sort(found.begin(), found.end(),
            [](const SampleRecord &a, const SampleRecord &b) { return a.seq < b.seq; });
  std::string out;
  for (auto &e : found) {
    if (limit-- == 0)
      break;
    if (!out.empty())
      out += '|';
    out += to_string(e.seq) + ':' + to_string(e.ts);
    for (uint32_t i = 0; i < SNAPSHOT_SLOTS; i++)
      out += ',' + to_string((unsigned) e.v[i]);
  }
  return out.empty() ? std::string(EMPTY_MARKER) : out;
}

void BacklogComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "Backlog event log:");
  if (this->part_ == nullptr) {
    ESP_LOGCONFIG(TAG, "  NO PARTITION - events are not being recorded");
    return;
  }
  ESP_LOGCONFIG(TAG, "  Partition at 0x%06X, %u KB",
                (unsigned) this->part_->address, (unsigned) (this->part_->size / 1024));
  ESP_LOGCONFIG(TAG, "  Snapshot ring: %u slots, %u used",
                (unsigned) this->sample_slots_(), (unsigned) this->s_written_);
  ESP_LOGCONFIG(TAG, "  Event ring: %u slots, %u used, head seq %u",
                (unsigned) EVENT_SLOTS, (unsigned) this->written_,
                (unsigned) this->head_seq());
}

}  // namespace backlog
}  // namespace esphome
#endif

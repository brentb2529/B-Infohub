#pragma once
// Append-only event log in a dedicated flash partition.
//
// WHY THIS EXISTS
//
// When Home Assistant is unreachable, ESPHome simply drops state: the API
// carries the CURRENT value and nothing else, so an outage is a hole in the
// record. For a numeric sensor that is tolerable -- you lose some resolution.
// For an ALARM it is not. A shutdown that asserts and clears while the bridge
// is offline leaves no evidence anywhere that it ever happened.
//
// So alarm transitions are written to flash the moment they occur, with a
// timestamp, and replayed once someone is listening again.
//
// WHY FLASH AND NOT NVS
//
// NVS is a key-value store with wear levelling built for settings that change
// occasionally. An append-only log of thousands of records is the wrong shape
// for it. A raw partition gives sequential writes, trivial indexing, and a
// scan-on-boot that recovers the head with no bookkeeping to corrupt.
//
// DURABILITY
//
// Erased flash reads as 0xFF, so seq == 0xFFFFFFFF means "never written" and
// is the natural empty marker. Each record carries a checksum, because a
// power cut mid-write is exactly the situation this log exists to survive --
// a torn record must be detectably bad rather than quietly wrong.
#include "esphome/core/component.h"
#include "esphome/core/helpers.h"
#include "esphome/components/time/real_time_clock.h"
#include <vector>
#include <string>

#ifdef USE_ESP32
#include "esp_partition.h"

namespace esphome {
namespace backlog {

enum EventType : uint8_t {
  EVENT_ALARM_SET = 1,    // an alarm bit went true
  EVENT_ALARM_CLEAR = 2,  // ...and back to false
  EVENT_BOOT = 3,         // bridge started; brackets any gap
  EVENT_BUS_LOST = 4,     // RS-485 went quiet
  EVENT_BUS_BACK = 5,
  EVENT_LINK_LOST = 6,    // Home Assistant / network went away
  EVENT_LINK_BACK = 7,
};

struct __attribute__((packed)) EventRecord {
  uint32_t seq;    // monotonic; 0xFFFFFFFF == erased slot
  uint32_t ts;     // unix seconds, 0 when the clock was not yet set
  uint8_t type;
  uint8_t index;   // which alarm, for ALARM_SET / ALARM_CLEAR
  uint16_t value;
  uint32_t crc;
};
static_assert(sizeof(EventRecord) == 16, "EventRecord must stay 16 bytes");

// The first 64 KB of the partition is the event ring. The remainder is
// reserved for register snapshots, which are a different size and cadence and
// must not be able to evict alarms.
static const uint32_t EVENT_REGION_SIZE = 0x10000;
static const uint32_t SNAPSHOT_SLOTS = 12;
static const uint32_t EVENT_SLOTS = EVENT_REGION_SIZE / sizeof(EventRecord);
static const uint32_t SECTOR_SIZE = 4096;
static const uint32_t SLOTS_PER_SECTOR = SECTOR_SIZE / sizeof(EventRecord);

struct __attribute__((packed)) SampleRecord {
  uint32_t seq;
  uint32_t ts;
  uint16_t v[SNAPSHOT_SLOTS];  // 0xFFFF == no reading
  uint32_t crc;
};
static_assert(sizeof(SampleRecord) == 36, "SampleRecord must stay 36 bytes");

// Snapshots live in the region after the event ring, and cannot evict events:
// an alarm is unreconstructable, a missing minute of voltage is not.
static const uint32_t SAMPLE_REGION_OFF = EVENT_REGION_SIZE;
static const uint32_t SAMPLES_PER_SECTOR = SECTOR_SIZE / sizeof(SampleRecord);

class BacklogComponent : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  // Record an event. Cheap enough to call from a poll loop: a write only
  // happens on an actual transition.
  void record(EventType type, uint8_t index = 0, uint16_t value = 0);

  // Everything with seq > after_seq, oldest first.
  std::vector<EventRecord> read_since(uint32_t after_seq) const;

  uint32_t head_seq() const { return this->next_seq_ - 1; }
  uint32_t count() const { return this->written_; }
  bool ready() const { return this->part_ != nullptr; }

  // How many events have not yet been acknowledged by a consumer.
  uint32_t pending() const {
    return this->next_seq_ > this->acked_seq_ + 1 ? this->next_seq_ - this->acked_seq_ - 1 : 0;
  }
  void ack(uint32_t seq) { if (seq > this->acked_seq_) this->acked_seq_ = seq; }
  uint32_t acked() const { return this->acked_seq_; }

  // Rewind the cursor so everything still on flash replays. Separate from
  // ack() on purpose: ack only ever moves FORWARD, so ack(0) is silently a
  // no-op and cannot serve as a reset. That mistake made backlog_replay_all
  // look like it worked while doing nothing at all.
  void reset_cursor() { this->acked_seq_ = 0; }

  // Wipe the event ring. Deliberately destructive and only reachable over the
  // authenticated API -- the log exists precisely because its contents cannot
  // be reconstructed, so nothing should be able to clear it by accident.
  void erase_events();

  // --- snapshots -----------------------------------------------------------
  void record_sample(const uint16_t *values);
  std::string sample_batch(uint32_t limit) const;
  void ack_sample(uint32_t seq) { if (seq > this->s_acked_) this->s_acked_ = seq; }
  void reset_sample_cursor() { this->s_acked_ = 0; }
  uint32_t sample_acked() const { return this->s_acked_; }
  uint32_t sample_count() const { return this->s_written_; }
  uint32_t sample_pending() const {
    return this->s_next_ > this->s_acked_ + 1 ? this->s_next_ - this->s_acked_ - 1 : 0;
  }

  // Serialise up to `limit` unacknowledged events as
  //     seq:ts:type:index|seq:ts:type:index|...
  // Deliberately not JSON: this crosses the API as a text_sensor state, and
  // every byte of punctuation costs batch size. A consumer that can parse
  // JSON can parse this.
  // Returns EMPTY_MARKER, never "", when there is nothing pending.
  //
  // This crosses the API as a text_sensor state, and an empty state is
  // indistinguishable from "no update" on the receiving side -- a consumer
  // polling for change sees the previous batch forever and re-acknowledges
  // the same records. Which is exactly what happened: the drain test replayed
  // one record twenty times. A marker makes "nothing left" an explicit value.
  static constexpr const char *EMPTY_MARKER = "-";

  std::string batch(uint32_t limit) const {
    std::string out;
    for (auto &e : this->read_since(this->acked_seq_)) {
      if (limit-- == 0)
        break;
      if (!out.empty())
        out += '|';
      out += to_string(e.seq) + ':' + to_string(e.ts) + ':' +
             to_string((unsigned) e.type) + ':' + to_string((unsigned) e.index);
    }
    return out.empty() ? std::string(EMPTY_MARKER) : out;
  }

  void set_time(time::RealTimeClock *t) { this->time_ = t; }

 protected:
  static uint32_t crc_of_(const EventRecord &r) {
    return r.seq * 2654435761u ^ r.ts * 40503u ^ (uint32_t) r.type << 16 ^
           (uint32_t) r.index << 8 ^ r.value;
  }
  static bool valid_(const EventRecord &r) {
    return r.seq != 0xFFFFFFFFu && r.crc == crc_of_(r);
  }

  time::RealTimeClock *time_{nullptr};
  const esp_partition_t *part_{nullptr};
  uint32_t next_seq_{1};
  uint32_t write_slot_{0};
  uint32_t written_{0};
  uint32_t acked_seq_{0};
  bool boot_logged_{false};
  uint32_t s_next_{1};
  uint32_t s_slot_{0};
  uint32_t s_written_{0};
  uint32_t s_acked_{0};
  uint32_t sample_slots_() const {
    return (this->part_->size - SAMPLE_REGION_OFF) / SECTOR_SIZE * SAMPLES_PER_SECTOR;
  }
  static uint32_t scrc_(const SampleRecord &r) {
    uint32_t c = r.seq * 2654435761u ^ r.ts * 40503u;
    for (uint32_t i = 0; i < SNAPSHOT_SLOTS; i++)
      c ^= (uint32_t) r.v[i] << (i % 16);
    return c;
  }
  static bool svalid_(const SampleRecord &r) {
    return r.seq != 0xFFFFFFFFu && r.crc == scrc_(r);
  }
};

extern BacklogComponent *global_backlog;  // NOLINT

}  // namespace backlog
}  // namespace esphome
#endif  // USE_ESP32

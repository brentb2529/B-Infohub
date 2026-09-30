# Discovery: commissioning a bridge on a generator we have never seen

This bridge was built against one generator and one controller. For it to go
out in the wild, a stranger has to be able to plug it in, join Wi-Fi, add the
integration, and have the generator's capabilities appear by themselves — with
no register knowledge, no laptop probe, and no decisions they are not equipped
to make.

Link settings are fixed for this controller family (9600 baud, even parity,
slave 10). What varies is **what the controller answers, what it means, and
which alarm inputs are wired**. That is what discovery has to learn.

## What already exists

- `tools/gc1032_probe.py` — `scan` / `dump` / `sweep` on a laptop. Read-only
  by construction: holding register `0x0000` starts and stops the engine, so
  there is no write function anywhere in the file.
- `packages/holding-sweep.yaml` — on-device probing, and the record of how it
  fails. Its first version interleaved probe reads with the normal poll loop;
  responses were matched to the wrong requests and telemetry — so the alarm
  pipeline — was down within four minutes. The fix, and the envelope every
  on-device probe must inherit:
  - **take the bus exclusively** (`stop_poller()` / `start_poller()`);
  - **refuse to run while the engine turns**;
  - **watchdog under the 5-minute bridge-dark threshold**, so a probe can
    never page anyone;
  - **no per-register entities** — the board runs at ~81% RAM and heap
    exhaustion has already caused an aborted boot and an automatic rollback;
  - **never a write.** Only function codes 0x03 and 0x04 are constructed.
- **Passthrough is already safe to probe alongside.** Port A faces the
  generator; port B answers the InfoHub as a slave from reconstructed values,
  never from the wire. A probe on port A cannot collide with the InfoHub, and
  registers we do not model are already served as `0xFFFF` — the controller's
  own "not present".

Discovery is a generalisation of `holding-sweep`, not new machinery.

## The commissioning flow

Zero user decisions on the default path.

1. **Flash** from the web installer; **Wi-Fi** via Improv (Bluetooth or the
   USB cable); **HA adopts it** through EnergyTrak's discovery.
2. **The first time `bus_healthy` goes true with the engine stopped, the
   bridge commissions itself.** Four read-only steps inside the sweep's
   envelope:
   - **Identity** — protocol revision (`0x0000`) and model registers →
     controller family.
   - **Presence** — attempt each documented range. A Modbus *illegal address*
     exception means the register genuinely is not there; a *timeout* means
     wiring or link. These must never be conflated.
   - **Plausibility** — sanity-check decodes against physical ranges (battery
     8–16 V, frequency 0/50/60 Hz) so a range that answers with nonsense is
     marked present-but-implausible rather than trusted.
   - **Alarm baseline** — sample `0x0040`–`0x004D` at rest and record every
     nibble. See `alarm-encoding.md` for why this is an inventory, not a
     decode.
3. **The profile is stored in flash and published** as one compact value plus
   a few scalars — never per-register entities.
4. **The poller narrows** to the ranges that answered, so absent registers
   stop dragging `bus_success_rate` down and looking like a fault.
5. **Passthrough is offered only after commissioning** — which is already how
   it behaves: off by default, never restored on.

### Re-probe triggers

- The profile's schema version changes (after an OTA that adds knowledge).
- The identity registers change (a controller was replaced).
- A **Re-run discovery** button, for after a wiring change.

Never automatically while the engine turns, and never during an outage.

## The alarm baseline, and the one thing that cannot be automated

The baseline is only meaningful if the generator is healthy when captured.
Commission during a real fault and the baseline would memorise that fault as
normal — the monitoring would then be silent about the one thing it exists to
catch.

Handled without asking the user anything:

- capture only when the engine is stopped, no shutdown bits are asserted and
  utility power is present;
- mark the baseline **provisional**;
- confirm it automatically after the first complete run that ends with no
  faults;
- publish `baseline_captured_at` and the provisional flag, with a **Recapture
  baseline** button for after a controller swap.

The default path is silent; the risky case is stated rather than hidden.

### What the baseline records

Not "which conditions are faults" — we do not know the encoding well enough
to say that. It records **every condition's raw nibble** and its four-state
classification from `alarm-encoding.md` (not present / ok / indeterminate /
fault). Indeterminate conditions are listed to the user explicitly: *read 0 on
a healthy machine, not treated as a fault, raw value shown.* On someone else's
generator that is the difference between a confusing screen of phantom faults
and an honest inventory.

## The profile

Published by the firmware; carried by the contract as a new `capabilities`
section (schema in one place, both transports agreeing, exactly as `controls`
works today); read by EnergyTrak, which duplicates no decode logic.

```json
{
  "schema": 1,
  "family": "gc103x",
  "identity": {"protocol_revision": "0x8003"},
  "captured_at": "2026-09-27T21:00:00Z",
  "ranges": {
    "0x0000-0x0027": "present",
    "0x0029-0x002B": "present",
    "0x0033-0x0036": "present",
    "0x0038-0x003D": "present",
    "0x0040-0x0056": "present"
  },
  "implausible": [],
  "alarm_baseline": {
    "block": "11001111FF111111F0F0111F0100001110011111000000F011F1111FE",
    "provisional": false,
    "confirmed_by_run_at": "2026-10-03T13:50:00Z"
  }
}
```

EnergyTrak uses it for three things: the model on the device card, a
`Controller Profile` diagnostic, and defaulting indeterminate alarm entities
to disabled. It already creates entities only for fields actually reported,
so it needs no per-model tables.

## What has to change

| Where | Change |
|---|---|
| Firmware | a `commissioning` package modelled on `holding-sweep.yaml`: identity, presence, plausibility, baseline; profile in flash prefs; `Re-run discovery` and `Recapture baseline` buttons |
| Firmware | the poller reads its range list from the profile rather than from compile-time YAML |
| Firmware | the **proxy's slave address follows discovery** — it is a compile-time substitution today, and an InfoHub on a family that uses a different address would not see its generator |
| Contract | `capabilities` section, generated the way `controls` is |
| EnergyTrak | read the profile; device card, diagnostic entity, disabled-by-default for indeterminate alarms |

## Unknown controllers

Fail soft. A family the vendor JSON does not describe gets "unknown
controller — raw registers only, no derived alarms" rather than a guessed
decode. This project has been self-consistent and wrong twice already (the
timezone bug; the 94-minute controller clock). Presenting inferred values as
fact is the failure mode to design against.

## What to ship first

Not autodetect. A **guided setup that verifies and reports**: the installer
accepts the link settings, the bridge probes once, and states plainly —
*controller answering at 9600/EVEN/10, 87 registers present, 15 alarm inputs
indeterminate, baseline captured (provisional)*. That is most of the value,
keeps the bus-exclusive risk to one deliberate action, and produces the first
profile from someone else's generator — which is itself the data this design
is missing.

## The honest caveat

There is one generator and one controller. Everything about other families is
inference until a stranger's board reports a profile. That is an argument for
shipping the profile early, not for waiting.

## Status — 2026-09-29: commissioning is implemented and verified

`packages/commissioning.yaml` runs once, by itself, the first time the bus is
healthy with the engine stopped and no profile is stored, and again on the
**Run Discovery** button. Verified on the real GC-1032: family `gc103x`,
protocol `0x8003`, firmware `0x4113`, model register absent, **87 registers
present** (the same 87 the August laptop sweep found), alt block absent, alarm
inventory 8 absent / 30 ok / 17 indeterminate / 1 unexpected; identical on a
second run and after a reboot; bus impact 1 missed poll. ha-energytrak
≥ 1.26.1 reads it (device model, Controller Family, Registers Present, Alarm
Inputs Indeterminate, Commissioned) and applies the four-state alarm rule.

### What the wire taught, and the code now assumes

- An ESPHome custom command's frame **includes the slave address**; the
  callback receives **register bytes only**; the hub **de-duplicates
  byte-identical frames** (the heartbeat reads two registers so it cannot be
  absorbed into the poller's own read of 0x0000); `send_wait_time` is 2000 ms
  by default and is set to 500 ms for the probe's duration; misses are pooled
  per controller and past `max_cmd_retries` the controller is marked offline
  and its queue cleared — so the probe runs with retries at zero, one command
  in flight, and a heartbeat after every miss. `stop_poller()` stops new
  cycles; the one already queued drains for ~12 s first.
- Only what the poller does not read is probed. The poller's own ranges are
  proven present by their sensors having values, except 0x0033–0x0036, whose
  senders are absent here (all 0xFFFF → NaN) and which is probed directly.
- On this controller an absent register answers **illegal data address in
  12 ms**, so "did not answer" never arose; the design still tolerates it.
- **Home Assistant caps a sensor state at 255 characters.** The profile is
  one string; v1 was ~330 and read `unknown`. v2 is ~237.
- **RAM:** the five-entity first cut aborted on boot (API overflow buffer
  allocation with two clients connecting). Two entities now; +0.6 % RAM.

### Profile v2 (the `Controller Profile` text sensor)

```json
{"v":2,"fam":"gc103x","proto":"8003","fw":"4113","model":"FFFF","n":87,
 "map":"FFFFFFFFFFFFFFFF007FFFFF00000000","alt":"00000000",
 "base":"11001111FF111111F0F0111F010000111001111100000F011F1111FE",
 "prov":1,"batt":1,"util":1,"t":1790737519}
```

| Key | Meaning |
|---|---|
| `fam` | `gc103x` when `proto` is 0x8003 and 0x0040–0x004F are present; otherwise `unknown` |
| `proto` / `fw` / `model` | registers 0x0000 / 0x0055 / 0x00B5 as hex words; `FFFF` = did not answer |
| `n` | registers present |
| `map` | presence bitmap for 0x0000–0x007F, four 32-bit words, MSB first |
| `alt` | presence bitmap for 0x00B4–0x00D3 |
| `base` | 0x0040–0x004D as read at commissioning, four hex digits each |
| `prov` | baseline provisional (no clean run confirmed it yet) |
| `batt` / `util` | battery 8–16 V; utility 0 or 90–140 V per leg |
| `t` | Unix time of capture, 0 if the clock was not valid |

The contract carries `alarm_bits` (register, mask, asserted value per alarm)
so a consumer can apply the four-state rule against `base` without the
device decoding anything.

### Not yet done

- Narrowing the poller to present ranges (Phase 3) and the provisional →
  confirmed baseline transition after a clean run.
- The first profile from a second generator. The friend's unit is the
  candidate; its August cloud dump predates the raw blocks.

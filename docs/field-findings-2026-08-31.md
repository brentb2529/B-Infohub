# Field findings — 2026-08-31

First contact with the real controller. Everything below is measured, not inferred.
Where it contradicts genmon or my own earlier assumptions, the hardware wins.

## Bus parameters

**Slave id 10, 9600 baud, 8E1.** Not the genmon defaults (1 / 19200 / none) that this
repo originally shipped. `tools/gc1032_probe.py scan` found them in 35 seconds.

A detail worth keeping: parity `N` failed while both `E` and `O` matched. That is the
signature of an 8E1 device — pyserial does not reject parity errors, so E and O deliver
identical data bytes and only the (ignored) check differs. Two hits is the expected
result here, not an ambiguity.

## The register space is smaller than the map suggests

Swept 0x0000–0x02FF (768 addresses). **87 registers respond, all within 0x0000–0x0056.**
Nothing above 0x0056 answers. genmon's `alt_input_registers` block reaching to 0x00C1
does not exist on this unit.

`0x00B5` (Controller Model) is the only documented register that does not respond —
exactly as genmon warns. Keep it excluded.

The "holes" are not holes here: 0x002D–0x0032, 0x0037 and 0x003E–0x003F all respond,
returning 0xFFFF. They are exposed raw and disabled by default in
`packages/gc1032-unmapped.yaml`.

**Holding registers: zero response.** FC03 across 0x0000–0x01FF returned nothing at
all. There is no readable configuration space. This retroactively justifies using
ESPHome's write-only `output` platform for control rather than the `number` platform —
`number` would poll-read holding 0x0000 and time out on every cycle.

## 0xFFFF means "sensor not present"

Oil pressure (0x0033), fuel level (0x0035), fuel volume (0x0036) and every L3 register
return 0xFFFF. Unfiltered that publishes **6553.5 V** on Generator L3. All sensors now
filter it to NAN → unavailable, except the raw alarm registers where 0xFFFF is the
legitimate healthy state.

Oil pressure stayed 0xFFFF **at 2800 RPM under load-free running**, which proves the
sender is absent rather than merely idle-zero.

## Alarms: active-low is right, but 0 also means "not fitted"

15 of 51 conditions asserted on a demonstrably healthy generator. Every one is an
unpopulated input: fuel level/theft/cap (gas unit, no tank), water level and
oil-pressure-open (air-cooled), L3 and phase rotation (single-phase), and unwired aux
inputs A/B/F/G/I.

The polarity was never wrong. The problem is that a nibble of 0 encodes both "faulted"
and "not applicable". Healthy-state registers are captured in
`vendor/baseline-2026-08-31.json`; `tools/gen_alarms.py` reads it and marks anything
asserted at baseline as `disabled_by_default` rather than deleting it.

**Re-capture the baseline if a sensor is ever fitted**, or that input stays hidden.

## The status word is flags, not an enum

genmon models 0x004F's high bits as a 0x7F00 enum with six values. Observed run
produced **0x6080** and **0x6100**, neither of which is in it — the entity would have
read "Unknown" for the entire test.

Decomposition, confirmed against genmon's own six values:

| Bit | Meaning |
| --- | --- |
| 0x4000 | utility healthy |
| 0x1000 | called to run |
| 0x0800 | **Auto mode selected** |
| 0x0200 | producing power |
| 0x0100 | engine running |
| 0x0080 | engine stopped |
| 0x0040 | stopped with fault |
| 0x0008 | common shutdown |

The 0x7F00 mask straddles the running bit at 0x0100, which is precisely why unobserved
combinations fall through. `packages/gc1032-status.yaml` now honours genmon's six
labels when the word matches exactly, and composes from flags otherwise.

Observed sequence:

| Time | Word | State |
| --- | --- | --- |
| 17:55:15 | `0x6880` | utility + auto + stopped — idle in AUTO |
| 17:55:31 | `0x6080` | utility + stopped — MANUAL selected at panel |
| 17:55:40 | `0x6100` | utility + running — running in MANUAL |
| 18:02:14 | `0x6080` | stopped |
| after | `0x6880` | back to AUTO, matches pre-test exactly |

No separate cool-down state appeared on a manual stop.

## Decodes confirmed against reality

- **Date/time byte packing** — 0x0052 = `0x081F` → month 8, day 31; 0x0053 = 2026.
  Correct. 0x0050's high byte ticked 0x11 → 0x12 during the sweep: minutes confirmed.
  (Controller clock runs ~1.5 h behind wall time — drift, not a decode error.)
- **Starts counter** — 279 before, **280** after. Arithmetic proof of the decode.
- **0x004E is dual-purpose** — bit 0x0010 (Fuel Relay Open) set on start, cleared on
  stop. Its low nibble also differs by mode (0x7 in Auto, 0x1 in Manual).
- **Battery dipped to 11.4 V on crank**, recovering to 13.4 V. This is the brownout the
  wide-input buck in `docs/wiring.md` §4 exists for — measured, not theoretical.
- **Low-speed test mode is normal** for this unit: 2802 RPM / 46.7 Hz / 180 V, held
  steady with no faults. Confirmed by the owner. Do not alarm on off-nominal frequency
  without checking mode first.

## Two bugs the hardware found

**Local echo.** The RS-422 adapter with RXD jumpered to T/R hears its own transmission.
The probe consumed those 8 bytes as the response, failed CRC, and reported "nothing
responded" while the real reply sat unread. The tell was *timing*: the failing scan ran
in 9.5 s instead of 34.5 s, because every transaction returned instantly on the echo
instead of waiting out its timeout. **A sweep that gets faster is a sweep that stopped
listening.**

**argparse ordering.** `probe.py scan --port X` failed with "unrecognized arguments"
because the common options lived on the top-level parser. It was the exact command the
README told you to run. Common options now sit on a shared parent parser.

## Still untested

The **control path**. `packages/gc1032-control.yaml` validates but has never written to
this controller. Holding registers do not read back, so a write can only be confirmed
by side effect. Test it deliberately, from the ESP32, with the interlock armed — not
from an ad-hoc script.

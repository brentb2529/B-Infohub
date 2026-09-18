# B-Infohub Bridge v1.0 — PCB

90 × 92 mm, 2-layer, 1.6 mm FR4. KiCad 10 project generated programmatically from
`tools/circuit.py` and verified with `kicad-cli` 10.0.5.

Replaces the Briggs & Stratton InfoHub as the Modbus master on the GC-1032's RS-485
bus, **while passing the InfoHub through on a second port** so its cell modem keeps
working as out-of-band backup during an outage.

| Check | Result |
| --- | --- |
| `kicad-cli sch erc --severity-all` | **0 violations** (`binfohub_bridge-erc.rpt`) |
| `kicad-cli pcb drc --severity-all --refill-zones --schematic-parity` | **0 errors, 0 unconnected, 0 parity issues** |
| Routing | **100 %**, 0.25 mm-grid A* router, 441 tracks / 56 vias, GND pour both layers |
| LCSC stock | **all 28 distinct parts in stock**, 10 of them JLC *basic* (no setup fee) |

Remaining DRC output is 28 cosmetic warnings: 25 are back-silkscreen text over the
back ground pour (silk prints on top of soldermask — universal on any poured board),
2 are minor silk-to-silk overlaps, and 1 is a 0.7 mm dangling track stub on `A_DE`
left by the router's path commit. That last one is a transceiver direction line
switching at 9600 baud; a sub-millimetre stub on it is electrically meaningless.
**No silk over any pad.**

## What is on it

| Block | Parts |
| --- | --- |
| **Power in** | J1 screw terminal, AO3401A reverse-polarity P-FET (4 A — carries the InfoHub too), **SMBJ16A TVS**, 100 µF bulk |
| **5 V rail** | AP63205WU-7 sync buck, 3.8–32 V in, fixed 5 V 2 A + 10 µH shielded inductor, 1.1 A polyfuse — lifted from b-hydro carrier v2.1 |
| **InfoHub 12 V** | Separate 2 A polyfuse (F2) |
| **RS-485 × 2** | SP3485EN transceivers, PSM712 TVS per pair, 120 Ω termination on jumpers (ship OPEN — see below) |
| **MCU** | ESP32-DevKitC-38, socketed |
| **Indicators** | 5 LEDs (PWR / WIFI / BUS / FAULT / TX) sized for light pipes, plus J4 header |

### Why the power section is split into two fuses

Our bridge draws ~150 mA. The InfoHub's cell modem pulses to 1–2 A on transmit. Sharing
a fuse would let an InfoHub fault take down the telemetry — precisely backwards. Both
legs sit behind the same reverse-polarity FET, so a miswired harness cannot hurt either
device, but a fault in one cannot starve the other.

### Why the LED resistors are 100R / 330R and not 1k

These are driven from a 3.3 V GPIO. A blue or green LED has a forward drop near 2.9 V,
leaving ~0.4 V across the resistor — 1k would give roughly **0.5 mA**, invisible through
a light pipe. 100R for blue/green and 330R for red/yellow puts all five at about 4 mA.

## Termination: ship JP1 and JP2 OPEN

Measured, not assumed. On 2026-08-31 the live bus delivered **368 consecutive
error-free 87-register block reads** (32,016 values, every one CRC-checked) across
engine cranking and five minutes of running, with an adapter that was almost certainly
unterminated. Zero failures.

The physics agrees. At 9600 baud one bit is **104 µs**; signal propagates at ~5 ns/m,
so even a 30 m run has a 150 ns round trip — 0.14 % of a bit period. Reflections from
the SP3485's fast edges settle within a few hundred nanoseconds, while the receiver
samples in the *middle* of the bit. Termination is governed by edge rate versus cable
delay, and here there are three orders of magnitude of margin.

There is also a cost to fitting them: 120 Ω with no fail-safe biasing pulls A and B
together at idle, which can leave the receiver output indeterminate and produce framing
errors. **Adding termination to a bus that already works can make idle behaviour
worse.**

So: leave both jumpers open. Fit one only if CRC errors appear on that segment. They
exist so the option is available, not because it is needed.

If a bus ever does misbehave at idle rather than in traffic, the fix is fail-safe
biasing (pull-up on A, pull-down on B), not termination. There are no bias footprints
on this revision — say the word and I will add them as DNP.

## Bus parameters — measured, not assumed

**Slave 10, 9600 8E1.** Not the genmon defaults (1 / 19200). Found with
`tools/gc1032_probe.py scan` on 2026-08-31 and confirmed against live readings; the
values are on the back silkscreen so nobody has to re-derive them. See
`../../docs/field-findings-2026-08-31.md`.

## Enclosure interface

The lid needs light pipes over these LED centres (board coordinates, origin = top-left):

| LED | Function | Colour | x | y |
| --- | --- | --- | --- | --- |
| D5 | PWR | green | 18.0 | 80.0 |
| D6 | WIFI | blue | 29.0 | 80.0 |
| D7 | BUS | green | 40.0 | 80.0 |
| D8 | FAULT | red | 51.0 | 80.0 |
| D9 | TX | yellow | 62.0 | 80.0 |

11 mm pitch, which suits 3 mm acrylic rod.

**Cable entry.** All three terminals sit on the **top edge (y = 7)** with their wire
openings facing outward, so one enclosure wall takes every gland. Pad spans:

| Terminal | x range |
| --- | --- |
| J1 12 V IN (2P, 5.08 mm) | 12.0 – 17.1 |
| J2 BUS (2P, 2.54 mm) | 50.0 – 52.5 |
| J3 INFOHUB (4P, 2.54 mm) | 70.0 – 77.6 |

**Terminal contents.** The generator harness carries four conductors that matter:
+12 V, GND, and the RS-485 pair. Power lands on J1, the pair lands on J2 — and J2
needs no ground pin of its own, because the harness ground is already on J1 and it is
the same net. J3 is different: it is a separate cable run out to the InfoHub carrying
power *and* data, so it needs its own return.

| | Pins | To |
| --- | --- | --- |
| J1 | +12V, GND | harness power (red/grey, black) |
| J2 | A, B | harness RS-485 pair (brown, yellow) |
| J3 | +12V, GND, A, B | the InfoHub |

**Mounting:** six M3 holes at (4.5, 4.5), (85.5, 4.5), (4.5, 46), (85.5, 46),
(4.5, 87.5), (85.5, 87.5).

## Files

| File | Purpose |
| --- | --- |
| `binfohub_bridge.kicad_pro/.kicad_sch/.kicad_pcb` | KiCad project |
| `binfohub.kicad_sym`, `binfohub.pretty/` | ESP32-DevKitC-38 symbol + footprint |
| `binfohub_bridge_jlc.zip` | Gerber X2 + Excellon — upload as-is |
| `bom_jlc.csv`, `cpl_jlc.csv` | JLCPCB BOM (verified LCSC numbers) and pick-and-place |
| `ORDER.md` | What to upload, board options, and the loose parts JLC will not place |
| `preview/silk_front-1.png` | Readable silkscreen plot |
| `preview/top.png`, `schematic.pdf` | Render and schematic |
| `tools/` | `circuit.py` is the single source of truth |

Regenerate: `cd tools && python3 gen_libs.py && python3 gen_sch.py && python3 router.py && python3 gen_bom.py`

## Two fixes made to the inherited b-hydro tooling

**`router.py` — trapped-pad escapes.** A pad ringed by its neighbours' keepouts
(SOIC-8 at 1.27 mm, TSOT-23-6) has no free cell for A* to start from. `prelinks`
extended only the *target* set, which helps the far end of a net and does nothing for
the pad that is actually stuck. It now seeds the *source* side too. This took routing
from 11 failures to 0.

**`router.py` — mounting keepouts.** Were hard-coded to b-hydro's 120 × 90 corners, so
two keepouts sat off this board and two real holes had none.

## Before ordering

Not yet reviewed by a second pair of eyes. Specifically worth checking:

- **SM712 pin mapping.** KiCad's `SM712_SOT23` symbol has pin 3 as common; confirm
  against the PSM712 datasheet before fab. Getting it wrong makes the TVS useless.
- Terminal-block orientation (the 180° post-pass in `circuit.py`) — this is the exact
  issue JLC's DFM review flagged on b-hydro.
- AP63205 application circuit against its datasheet, though it is unchanged from a
  board that has already been built.

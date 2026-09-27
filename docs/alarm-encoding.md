# The alarm block: what we know, what we assumed, and how to find out

Every alarm entity this firmware publishes is a nibble test against input
registers `0x0040`–`0x004F`, decoded by one rule from genmon's controller
definition: **asserted when `(raw & mask) == value`**, with the fault nibbles
**active low** — a nibble of `0` means the fault is present.

That rule has never been confirmed on this hardware. **No real alarm has ever
been observed on this generator**, in the registers or anywhere else. This
document records why the rule is now in doubt, what the evidence actually
supports, and the two safe tests that would settle it.

## What the evidence says

### 1. The block does not move

`captures/run-2026-08-31.csv` holds 368 samples across a full manual start,
run and stop. Registers `0x0040`–`0x004D` are **bit-for-bit identical in every
sample**. Only `0x004E` and `0x004F` change — and those are the engine-state
and status words, ordinary active-high bits.

Static across an engine cycle is what *configuration* looks like, not live
alarm state.

### 2. The nibble alphabet is tiny

Across every sample, the only values that appear in `0x0040`–`0x004D` are
`0`, `1`, `0xE` and `0xF`. The baseline capture (`vendor/baseline-2026-08-31.json`):

| Register | Value | Nibbles |
|---|---|---|
| 0x0040 | 0x1100 | 1 1 0 0 |
| 0x0041 | 0x1111 | 1 1 1 1 |
| 0x0042 | 0xFF11 | F F 1 1 |
| 0x0043 | 0x1111 | 1 1 1 1 |
| 0x0044 | 0xF0F0 | F 0 F 0 |
| 0x0045 | 0x111F | 1 1 1 F |
| 0x0046 | 0x0100 | 0 1 0 0 |
| 0x0047 | 0x0011 | 0 0 1 1 |
| 0x0048 | 0x1001 | 1 0 0 1 |
| 0x0049 | 0x1111 | 1 1 1 1 |
| 0x004A | 0x0000 | 0 0 0 0 |
| 0x004B | 0x0F01 | 0 F 0 1 |
| 0x004C | 0x1F11 | 1 F 1 1 |
| 0x004D | 0x11FE | 1 1 F E |

Under the active-low rule, this healthy, idle generator has roughly fifteen
faults asserted. `0x004A` reading `0x0000` would be four simultaneous faults;
it looks far more like an unimplemented register.

### 3. The controller's own manual

The GC1031 operator's manual (Tables 5–7) adds two facts the decode never
accounted for:

- **Every alarm has a configurable action** — None / Notification / Warning /
  Electrical Trip / Shutdown — set per input, per battery threshold, per
  maintenance alarm. If the nibbles were those action codes we would expect
  `2`, `3` or `4` somewhere: low oil pressure ought to be a Shutdown. None
  appear.
- **A missing sensor is its own alarm**: "Anlg LOP (Pin 26) Ckt Open — the oil
  pressure sensor is detected as not being present." Absence is reported
  explicitly. That undercuts the inference this project made to explain the
  fifteen "faults" — that a zero nibble also means an unpopulated input. That
  inference was never verified either.

The manual maps LCD messages to conditions. It says nothing about Modbus
beyond slave id and baud. **No public document maps this controller's
registers to its display**, and genmon's definition carries no display codes.

### Where that leaves us

Neither theory fits the data:

- *Active-low live flags* — contradicted by a block that never moves and by
  fifteen phantom faults on a healthy unit.
- *Configured action codes* — contradicted by the absence of any 2/3/4.

The encoding is **unknown**. Stated plainly: **the critical alarm path may
never fire, and nothing would say so.** What keeps the system from being
blind is the design rule already applied to the alerts that matter most —
`power_out_no_generator` and `bridge_dark` observe facts (utility down, engine
not turning; bridge silent) rather than asking the controller to diagnose
itself.

## What the firmware does about it now

`packages/alarm-watch.yaml` decodes nothing. It publishes the raw block as one
string, counts changes to it, and flags any nibble value never seen before.
Whatever the encoding is, a controller raising an alarm is unlikely to leave
all fourteen registers untouched — and if it does, that is itself the answer,
established rather than assumed.

The three entities:

| Entity | Meaning |
|---|---|
| `Alarm Block` | `0x0040`–`0x004D` as 56 hex characters, MSB first. `incomplete` until every register has arrived — never `0000` in its place. |
| `Alarm Block Changes` | Count since boot. Expected reading: 0. |
| `Alarm Block Unexpected Value` | A nibble outside `{0, 1, E, F}` has appeared. |

The alert this feeds is honest about its ignorance: *the alarm block changed;
read the display.*

## The four-state model this argues for

Stop treating the absolute value as the signal; treat the **transition** as
the signal. Per condition:

| Observed | Meaning | Published as |
|---|---|---|
| `F` | not present — the controller's own absence encoding (`0xFFFF` is used the same way for absent phases) | not present |
| `1` | wired and OK — proof the input exists | ok |
| `0` since commissioning | **indeterminate**, shown as such, never silently dropped, never counted as a fault | indeterminate, with the raw value |
| `1` then `0` | fault — an observed change no interpretation can explain away | fault |

It self-calibrates: the first time a nibble reads `1`, that condition is
proven wired, and from then on its zero means something. The one gap — a
fault already asserted before commissioning looks indeterminate — is exactly
the case to surface, not hide.

## How to settle it

Ranked by safety. The first two need nothing but patience; the third is the
one that gives an answer on demand.

1. **Passively.** The flash event log and `Alarm Block Changes` capture the
   first real event whenever it comes.
2. **Mild natural conditions.** Maintenance-due or low-battery warnings occur
   on their own and can be verified in the InfoHub app at the same time.
3. **The controller's own benign alarms, from its menus.** No engine
   intervention, nothing disconnected, fully reversible. Capture the block
   before and after each:
   - `MAINTENANCE → DUE AT ENGINE HOURS`: set below the current hours (they
     read 94.9 on 2026-09-26), action Notification. The controller raises a
     real alarm and displays it. Restore afterwards.
   - `BATTERY MONITOR → LOW VOLT THRESHOLD`: set just above the actual battery
     voltage (~13.1 V), action Notification, delay at minimum. Restore.

   If the LCD shows an alarm and nothing in `0x0040`–`0x004D` moves, the
   decode is reading something other than live state, and the alarm entities
   must be rebuilt around whatever did move. If a nibble goes `1 → 0`, the
   active-low rule is confirmed and the zero-at-rest conditions are the
   unpopulated inputs after all.

4. **A sender disconnect** (selector OFF, engine cold, InfoHub unplugged) is
   decisive but is a physical intervention on life-safety equipment. Owner's
   call.

Whatever the outcome, record it here with the register values, and update
`tools/gen_alarms.py` to match what was observed rather than what was
documented.

## Sources

- genmon controller definition: `vendor/Briggs_Stratton_GC-1032.json`
- GC1031 GENSET Controller Operation Instructions (Briggs & Stratton),
  Tables 5–7 — https://norwall.com/content/norwall-pim-app/assets/document/8878_GC1031_Operators_Manual.PDF
- genmon Appendix P — https://github.com/jgyates/genmon/wiki/Appendix-P-Briggs-and-Stratton-Controller-Information
- `captures/run-2026-08-31.csv`, `vendor/baseline-2026-08-31.json`

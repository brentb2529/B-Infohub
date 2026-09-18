# GC-1032 register map

Everything here is derived from `vendor/Briggs_Stratton_GC-1032.json` (genmon). That
file is the source of truth; this page is the human-readable version plus the traps.

## The four things that will cost you an afternoon

1. **Function code 04, not 03.** All telemetry lives in *input* registers. Reading them
   as holding registers (FC03) returns nothing useful. In ESPHome this is
   `register_type: read` — which is confusingly named, but it is FC04.

2. **The alarm nibbles are ACTIVE LOW.** A nibble reading `0x0` means the fault **is**
   asserted. Every alarm in genmon is encoded as mask `f000` with value `0000`. Get
   this backwards and your dashboard shows 47 active faults on a healthy generator, or
   worse, shows all-clear during a real one.

3. **There are holes in the address space, and they time out.** `0x002D–0x0032`,
   `0x003E–0x003F`, and `0x00B5` (Controller Model) do not respond on all units, and a
   timeout stalls the whole polling loop. The packages use `force_new_range: true` at
   `0x0033`, `0x0040` and `0x0050` to stop ESPHome merging reads across those gaps.
   **Do not remove those without re-reading this section.**

4. **Start is a two-write sequence.** `0x0001` (Manual) then `0x0002` (Crank). A lone
   `0x0002` does nothing, which makes a half-working control implementation look like
   a wiring fault.

## Control — holding register 0x0000 (FC06)

| Write | Effect |
| --- | --- |
| `0x0001` | Manual mode — this is also the **Stop** command |
| `0x0002` | Crank/Start — only valid immediately after a `0x0001` |
| `0x0004` | Auto mode |

On some installations these also actuate the transfer switch. Assume yours does.

## Status word — input register 0x004F

| Mask | Value | Meaning |
| --- | --- | --- |
| `0x7F00` | `0x3900` / `0x3B00` / `0x6800` / `0x6900` / `0x6B00` / `0x7100` | Initialized / Generating / Off-Ready / Cool Down / Shutdown Pending / Exercising |
| `0x3800` | `0x2000` / `0x2800` / `0x3000` / `0x3800` | Manual / Automatic / Scheduled Exercise / Initialized |
| `0x0100` | set | Engine running |
| `0x0080` | set | Stopped |
| `0x0040` | set | Stopped with fault |
| `0x4000` | set = healthy, clear = **failure** | Utility power |
| `0x8000` | set | Controller in config mode |
| `0x0008` | set | Common shutdown |

Expect `0x6800` at rest and `0x7100` during a scheduled exercise. Watch the
`Status Register Raw` entity through one full exercise cycle before trusting any
decode above — this table is inferred, not from a B&S document.

`0x004E` is dual-purpose: genmon calls it "Alarm Register 15" but also reads engine
state from it (`0x0010` fuel relay open, `0x0020` starting). Those two bits are
ordinary **active-high**, unlike the fault nibbles.

## Input registers (FC04)

| Reg | Words | Scale | Name |
| --- | --- | --- | --- |
| `0x0000` | 1 |  | Protocol Revision |
| `0x0001` | 1 | ×0.1 | Generator L1 Voltage |
| `0x0002` | 1 | ×0.1 | Generator L2 Voltage |
| `0x0003` | 1 | ×0.1 | Generator L3 Voltage |
| `0x0004` | 1 | ×0.1 | Generator L1-L2 Voltage |
| `0x0005` | 1 | ×0.1 | Generator L2-L3 Voltage |
| `0x0006` | 1 | ×0.1 | Generator L3-L1 Voltage |
| `0x0007` | 1 | ×0.1 | Generator L1 Frequency |
| `0x0008` | 1 | ×0.1 | Generator L2 Frequency |
| `0x0009` | 1 | ×0.1 | Generator L3 Frequency |
| `0x000A` | 1 | ×0.01 | L1 Power Factor |
| `0x000B` | 1 | ×0.01 | L2 Power Factor |
| `0x000C` | 1 | ×0.01 | L3 Power Factor |
| `0x000D` | 1 | ×0.01 | Average Power Factor |
| `0x000E` | 1 | ×0.1 | Utility L1 Voltage |
| `0x000F` | 1 | ×0.1 | Utility L2 Voltage |
| `0x0010` | 1 | ×0.1 | Utility L3 Voltage |
| `0x0011` | 1 | ×0.1 | Utility L1-L2 Voltage |
| `0x0012` | 1 | ×0.1 | Utility L2-L3 Voltage |
| `0x0013` | 1 | ×0.1 | Utility L3-L1 Voltage |
| `0x0014` | 1 | ×0.1 | Utility L1 Frequency |
| `0x0015` | 1 | ×0.1 | Utility L2 Frequency |
| `0x0016` | 1 | ×0.1 | Utility L3 Frequency |
| `0x0017` | 1 | ×0.1 | Generator L1 Current |
| `0x0018` | 1 | ×0.1 | Generator L2 Current |
| `0x0019` | 1 | ×0.1 | Generator L3 Current |
| `0x001A` | 1 | ×0.1 | L1 Power kW |
| `0x001B` | 1 | ×0.1 | L2 Power kW |
| `0x001C` | 1 | ×0.1 | L3 Power kW |
| `0x001D` | 1 | ×0.1 | Total Power kW |
| `0x001E` | 1 |  | Percentage Load |
| `0x001F` | 1 | ×0.1 | L1 Load kVA |
| `0x0020` | 1 | ×0.1 | L2 Load kVA |
| `0x0021` | 1 | ×0.1 | L3 Load kVA |
| `0x0022` | 1 | ×0.1 | Total Load kVA |
| `0x0023` | 1 | ×0.1 | L1 Load kVR Reactive |
| `0x0024` | 1 | ×0.1 | L2 Load kVR Reactive |
| `0x0025` | 1 | ×0.1 | L3 Load kVR Reactive |
| `0x0026` | 1 | ×0.1 | Total Load kVR Reactive |
| `0x0027` | 2 | ×0.1 | Cumulative Energy kWh |
| `0x0029` | 2 | ×0.1 | Cumulative Apparent Energy kVAh |
| `0x002B` | 2 | ×0.1 | Cumulative Reactive Energy kVARh |
| | | | *— gap 0x002D–0x0032: do not poll —* |
| `0x0033` | 1 | ×0.1 | Oil Pressure Bar |
| `0x0034` | 1 | ×0.1 | Coolant Temp, C |
| `0x0035` | 1 | ×0.1 | Fuel Level Percent |
| `0x0036` | 1 | ×0.1 | Fuel Volume, L |
| | | | *— gap 0x0037–0x0037: do not poll —* |
| `0x0038` | 1 | ×0.1 | Battery Voltage |
| `0x0039` | 1 |  | Engine Speed |
| `0x003A` | 1 |  | Number of Starts |
| `0x003B` | 1 |  | Number of Trips |
| `0x003C` | 1 |  | Engine Run Time - Hours |
| `0x003D` | 1 |  | Engine Run Time - Minutes |
| | | | *— gap 0x003E–0x003F: do not poll —* |
| `0x0040` | 1 |  | Alarm Register 1 |
| `0x0041` | 1 |  | Alarm Register 2 |
| `0x0042` | 1 |  | Alarm Register 3 |
| `0x0043` | 1 |  | Alarm Register 4 |
| `0x0044` | 1 |  | Alarm Register 5 |
| `0x0045` | 1 |  | Alarm Register 6 |
| `0x0046` | 1 |  | Alarm Register 7 |
| `0x0047` | 1 |  | Alarm Register 8 |
| `0x0048` | 1 |  | Alarm Register 9 |
| `0x0049` | 1 |  | Alarm Register 10 |
| `0x004A` | 1 |  | Alarm Register 11 |
| `0x004B` | 1 |  | Alarm Register 12 |
| `0x004C` | 1 |  | Alarm Register 13 |
| `0x004D` | 1 |  | Alarm Register 14 |
| `0x004E` | 1 |  | Alarm Register 15 |
| `0x004F` | 1 |  | Status Register |
| `0x0050` | 1 |  | Time - Minutes |
| `0x0051` | 1 |  | Time - Hours |
| `0x0052` | 1 |  | Date - Month / Day |
| `0x0053` | 1 |  | Date - Year |
| `0x0054` | 1 |  | Nominal kW |
| `0x0055` | 1 |  | Controller Firmware |
| `0x0056` | 1 |  | Unknown Value |
| | | | *— gap 0x0057–0x00B4: do not poll —* |
| `0x00B5` | 1 |  | Controller Model  **(timeout risk — excluded)** |

## Alarm conditions (51 decoded)

Generated into `packages/gc1032-alarms.yaml` by `tools/gen_alarms.py`. Asserted when
`(raw & mask) == value` — which for the active-low nibbles means the nibble is zero.

| Reg | Mask | Asserted when | Condition |
| --- | --- | --- | --- |
| `0x0040` | `0xF000` | `== 0x0000` | Low Oil Pressure |
| `0x0040` | `0x0F00` | `== 0x0000` | High Coolant Temperature |
| `0x0040` | `0x00F0` | `== 0x0000` | Low Fuel Level |
| `0x0040` | `0x000F` | `== 0x0000` | Water Level Switch |
| `0x0041` | `0xF000` | `== 0x0000` | Engine Under Speed |
| `0x0041` | `0x0F00` | `== 0x0000` | Engine Over Speed |
| `0x0041` | `0x00F0` | `== 0x0000` | Engine Failed to Start |
| `0x0041` | `0x000F` | `== 0x0000` | Engine Failed to Stop |
| `0x0042` | `0x00F0` | `== 0x0000` | Generator Low Frequency |
| `0x0042` | `0x000F` | `== 0x0000` | Generator High Frequency |
| `0x0043` | `0xF000` | `== 0x0000` | Generator High Current |
| `0x0043` | `0x0F00` | `== 0x0000` | Generator Overload |
| `0x0043` | `0x00F0` | `== 0x0000` | Unbalanced Load |
| `0x0043` | `0x000F` | `== 0x0000` | Emergency Stop |
| `0x0044` | `0x0F00` | `== 0x0000` | Maintenance Required |
| `0x0045` | `0xF000` | `== 0x0000` | Battery Low Voltage |
| `0x0045` | `0x0F00` | `== 0x0000` | Battery High Voltage |
| `0x0045` | `0x00F0` | `== 0x0000` | Temperature Circuit Open |
| `0x0046` | `0xF000` | `== 0x0000` | Fuel Theft |
| `0x0046` | `0x0F00` | `== 0x0000` | Magnetic Pick Up Fault |
| `0x0046` | `0x00F0` | `== 0x0000` | Oil Pressure Open Circuit |
| `0x0046` | `0x000F` | `== 0x0000` | Auxiliary Input I |
| `0x0047` | `0xF000` | `== 0x0000` | Auxiliary Input A |
| `0x0047` | `0x0F00` | `== 0x0000` | Auxiliary Input B |
| `0x0047` | `0x00F0` | `== 0x0000` | Auxiliary Input C |
| `0x0047` | `0x000F` | `== 0x0000` | Auxiliary Input D |
| `0x0048` | `0xF000` | `== 0x0000` | Auxiliary Input E |
| `0x0048` | `0x0F00` | `== 0x0000` | Auxiliary Input F |
| `0x0048` | `0x00F0` | `== 0x0000` | Auxiliary Input G |
| `0x0048` | `0x000F` | `== 0x0000` | Auxiliary Input H |
| `0x0049` | `0xF000` | `== 0x0000` | Gen L1 Phase Low Voltage |
| `0x0049` | `0x0F00` | `== 0x0000` | Gen L1 Phase High Voltage |
| `0x0049` | `0x00F0` | `== 0x0000` | Gen L2 Phase Low Voltage |
| `0x0049` | `0x000F` | `== 0x0000` | Gen L2 Phase High Voltage |
| `0x004A` | `0xF000` | `== 0x0000` | Gen L3 Phase Low Voltage |
| `0x004A` | `0x0F00` | `== 0x0000` | Gen L3 Phase High Voltage |
| `0x004A` | `0x00F0` | `== 0x0000` | DG Phase Rotation |
| `0x004A` | `0x000F` | `== 0x0000` | Mains Phase Rotation |
| `0x004B` | `0xF000` | `== 0x0000` | Fuel Cap Open Circuit |
| `0x004B` | `0x00F0` | `== 0x0000` | Extended Over Load Trip |
| `0x004B` | `0x000F` | `== 0x0000` | High Oil Pressure Detected |
| `0x004C` | `0xF000` | `== 0x0000` | Alternator Input Lost |
| `0x004C` | `0x0F00` | `== 0x0000` | High Voltage Warning (Ph-Ph) |
| `0x004C` | `0x00F0` | `== 0x0000` | High Voltage Warning 1 (Ph-Ph) |
| `0x004C` | `0x000F` | `== 0x0000` | High Voltage Warning 2 (Ph-Ph) |
| `0x004D` | `0xF000` | `== 0x0000` | Low Voltage Failure 1 (Ph-Ph) |
| `0x004D` | `0x0F00` | `== 0x0000` | Low Voltage Failure 2 (Ph-Ph) |
| `0x004F` | `0x0020` | `== 0x0020` | Generator Failed to Start |
| `0x004F` | `0x0001` | `== 0x0001` | General Notification |
| `0x004F` | `0x0002` | `== 0x0002` | General Warning |
| `0x004F` | `0x0004` | `== 0x0004` | Electrical Trip |

`Maintenance Required` (0x0044) is typed `regex` rather than `bits` in genmon and its
decode is a guess — it ships `disabled_by_default: true`. Confirm it against the
controller's own display before enabling it.

## Registers the InfoHub never showed you

`alt_input_registers` in the vendored JSON lists ~30 more addresses that respond on
*some* controllers and time out on others, all labelled "Unknown". They are not polled
by this firmware. To find out which ones your unit answers — and which of those
actually carry moving data — use the bench probe:

```bash
python3 tools/gc1032_probe.py sweep --port /dev/cu.usbserial-XXXXXXXX --baud 19200 --parity N
```

Run it once at rest and once during an exercise cycle, then compare. Anything that
responds, is absent from the table above, and *changes* is a candidate. Add it as a
sensor with `force_new_range: true` so a slow or flaky register cannot take the rest
of the polling loop down with it.

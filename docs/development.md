# B-Infohub — development notes

> This is the original bring-up log, kept for anyone working ON the bridge
> rather than installing one. For installation see the [README](../README.md).
>
> Parts of it are historical and no longer accurate: the firmware has since
> been flashed and run on a live generator, the alarm set was filtered from 51
> raw bits down to the 34 that are meaningful on a split-phase unit, and the
> nine `raw_0x00XX` research sensors were removed to free heap. Read it as a
> record of how the decoding was established, not as current state.

## Goal

Replace the Briggs & Stratton InfoHub with a local ESP32 + RS-485 bridge that speaks
Modbus RTU directly to the **GC-1030/1031/1032** controller. No cell modem, no
subscription, no cloud round-trip — and considerably more data than the InfoHub ever
surfaced.

The InfoHub is not decoding anything proprietary. It is a Modbus master with a cell
modem and a billing relationship attached. This project just becomes the master
instead.

**What you get over the InfoHub:** per-phase voltages, currents, kW, kVA, kVAR and
power factor; cumulative kWh; oil pressure, coolant temp, battery voltage, RPM;
lifetime starts, trips and run hours; **51 individually decoded fault conditions**
instead of one "fault" flag; the raw status word; and optional start/stop/auto control.

~146 entities, all local, all in Home Assistant.

## Status

| Piece | State |
| --- | --- |
| Register decoding | **Validated against the real controller**, 2026-08-31 |
| ESPHome firmware, read-only | `esphome config` clean; decodes proven on live data, **not yet flashed** |
| Control (start/stop/auto) | Written, validates, **gated off by default** — see below |
| Bench probe tooling | Written, read-only by construction, **exercised end-to-end against a simulator** |
| Decoder tests | `tools/test_decoders.py` — 50 alarm decoders + status word, all passing |
| HA → Grafana push | Written, follows the existing B-Panels pipeline |
| Grafana dashboard | Generated, 27 panels |

The probe has been run end to end against `tools/fake_gc1032.py`, a simulated
controller on a pseudo-terminal: `scan`, `dump` and `sweep` all behave correctly,
including skipping the dead address holes and surfacing undocumented registers that
change between passes. `tools/test_decoders.py` evaluates all 50 generated alarm
lambdas plus the status word against known register states.

What a pty cannot test: baud/parity detection (line settings are ignored, so `scan`
matches every combination), bus turnaround, and anything electrical.

**2026-08-31: first contact with the real controller — it works.** Bus parameters
found, all 87 registers read, a full start/run/stop cycle captured at 1 Hz, and three
firmware bugs found and fixed against live data. See
[`docs/field-findings-2026-08-31.md`](docs/field-findings-2026-08-31.md).

Still untested: the control (write) path. The register map is genmon's, which is
well-proven, but every decode in `packages/gc1032-status.yaml` should be confirmed
against one exercise cycle before you trust it.

## Repo layout

| Path | Purpose |
| --- | --- |
| `genset-gc1032.yaml` | Device config — ESP32-DevKitC + MAX485. Start here. |
| `packages/base.yaml` | Wi-Fi / API / OTA / web / Improv / mDNS / diagnostics |
| `packages/mqtt.yaml` | MQTT alongside the native API (discovery deliberately off) |
| `packages/gc1032-power.yaml` | Electrical measurements, 0x0000–0x002C |
| `packages/gc1032-engine.yaml` | Engine, fuel, battery, runtime, clock |
| `packages/gc1032-status.yaml` | Raw fault registers + status-word decode |
| `packages/gc1032-alarms.yaml` | **Generated** — 51 fault entities |
| `packages/gc1032-control.yaml` | **DANGEROUS** — start/stop/auto. Not included by default. |
| `tools/gc1032_probe.py` | Read-only bench probe for the FTDI USB-RS485 cable |
| `tools/adapter_check.py` | Bench-checks the USB-RS485 adapter with nothing connected |
| `tools/fake_gc1032.py` | Simulated GC-1032 on a pty — test the probe with no generator |
| `tools/test_decoders.py` | Verifies the generated alarm/status decoders against known states |
| `tools/gen_alarms.py` | Regenerates the alarms package from the register map |
| `tools/gen_dashboard.py` | Regenerates the Grafana dashboard |
| `ha/packages/` | Home Assistant: metric attributes + Grafana Cloud push |
| `grafana/dashboards/` | **Generated** dashboard JSON |
| `vendor/` | Pinned genmon register map + provenance |
| `docs/wiring.md` | FTDI hookup, ESP32 wiring, 12 V power front end, grounding |
| `docs/register-map.md` | Register tables and the four traps |
| `docs/field-findings-2026-08-31.md` | **What the real hardware actually did** — read this |
| `captures/` | Live captures: full run cycle at 1 Hz, sweeps, at-rest dumps |

## Bring-up order

Do these in order. Each step de-risks the next.

### 1. Prove the bus exists (no soldering, no ESP32)

You already have the FTDI USB-RS485 cable. Wire it per
[`docs/wiring.md` §2](docs/wiring.md) — and note the colour collision: the FTDI cable
has a yellow wire and so does the generator harness, and they are different signals.

```bash
pip install pyserial
ls /dev/cu.usbserial-*                                   # NOT /dev/tty.* -- see docs/wiring.md
python3 tools/adapter_check.py --port /dev/cu.usbserial-XXXXXXXX   # do this at the desk first
python3 tools/gc1032_probe.py scan --port /dev/cu.usbserial-XXXXXXXX
```

`adapter_check.py` verifies the port and settles whether your adapter needs RXD+/RXD-
jumpered, without the generator being involved at all. **Already run for this
adapter** (`/dev/cu.usbserial-A94C31KL`): it is full-duplex RS-422 silicon and **needs
the jumpers** — RXD+ to T/R+, RXD- to T/R-, both joined pairs going to bus A and B.
See `docs/wiring.md`.

`scan` brute-forces baud, parity and slave id and never writes anything. The full
240-combination sweep takes about **35 seconds**. If it finds
nothing, swap A and B and run it again before concluding anything.

Then see what is actually there:

```bash
python3 tools/gc1032_probe.py dump  --port /dev/cu.usbserial-XXXXXXXX --baud 19200 --parity N
python3 tools/gc1032_probe.py sweep --port /dev/cu.usbserial-XXXXXXXX --baud 19200 --parity N
```

`sweep` is the one that answers "the controller must know more than the InfoHub told
me" — it probes the whole low address space twice and reports which **undocumented**
registers respond and which of them moved. Run it again during an exercise cycle.

### 2. Build the bridge

Set `modbus_baud`, `modbus_parity` and `modbus_address` in `genset-gc1032.yaml` to
whatever step 1 found.

```bash
python3 -m venv .venv && .venv/bin/pip install esphome
cp secrets.yaml.example secrets.yaml     # then fill it in
.venv/bin/esphome run genset-gc1032.yaml # USB the first time, OTA after
```

### 3. Confirm the decodes before trusting the dashboard

Watch `Status Register Raw` through one full exercise cycle. Expect `0x6800` at rest
and `0x7100` while exercising. If those do not match, fix
`packages/gc1032-status.yaml` before wiring up alerts.

Also sanity-check `Percentage Load` under real load — genmon's own map is internally
inconsistent about whether it needs a ×0.1 scale, and the sensor carries a comment
saying so.

### 4. Grafana

Copy `ha/packages/*.yaml` into `<config>/packages/`, then import
`grafana/dashboards/b-infohub-genset.json`.

**Verify the entity ids first.** `ha/packages/b_infohub_customize.yaml` is the one file
that must name entity ids, and it assumes `sensor.genset_*`. If HA assigned a `_2`
suffix, the customize entries bind to nothing — silently, because customize does not
warn about unknown ids. Developer Tools → States, filter on `genset`.

The push writes a **`genset_*`** measurement, deliberately separate from the existing
`generator_*` series that B-Panels' cloud poller produces. Both dashboards run side by
side. See the header of `b_infohub_customize.yaml` for why colliding on the same
attribute namespace would have silently corrupted the old dashboard rather than
failing loudly.

## Control is off by default

`packages/gc1032-control.yaml` can start and stop the engine, and on some
installations actuate the transfer switch. It is behind two interlocks:

1. The include in `genset-gc1032.yaml` is commented out.
2. A **Generator Control Enabled** switch that defaults off and is *not* restored
   across reboots.

Leave it read-only until the telemetry has been right for a while. There is no hurry:
reading is the whole value proposition, and writing is a five-minute uncomment
whenever you want it.

## Things that will bite you

- **One master.** The InfoHub must come off the RS-485 pair. Two masters means
  collisions and an InfoHub reporting comm faults to your dealer.
- **You lose the cell modem.** The generator runs when the grid is down, so the
  network path has to survive the outage too. **Resolved for this install: the house
  is on UPS.** LAN-side monitoring (bridge → AP → Home Assistant) therefore keeps
  working through an outage. Remote viewing additionally depends on the ISP's own
  equipment staying up, which is outside the UPS.
- **Alarms are active low.** A nibble of `0x0` means the fault *is* present.
- **The address space has holes that time out.** See `docs/register-map.md`.
- **Cranking browns out cheap buck converters.** Use a wide-input part; see
  `docs/wiring.md` §4.

## Credit

The register map is [genmon](https://github.com/jgyates/genmon)'s
`Briggs_Stratton_GC-1032.json` — pinned in `vendor/` with provenance. Without it this
would have been a logic-analyzer project.

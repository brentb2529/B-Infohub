# B-Infohub

**Local telemetry from a Briggs & Stratton standby generator — no subscription, no cell modem, no cloud.**

A small ESP32 board that plugs into the RS-485 port your generator already has and
speaks Modbus to its GC-1030/1031/1032 controller directly. Home Assistant gets the
readings in about a second, over your own network.

> The InfoHub is not decoding anything proprietary. It is a Modbus master with a cell
> modem and a billing relationship attached. This becomes the master instead — and you
> can keep the InfoHub connected alongside it if you want the cellular path as backup.

---

## What you get

| | EnergyTrak cloud | B-Infohub |
| --- | --- | --- |
| Readings | 34 | **130+** |
| Freshness | minutes | **~1 second** |
| Faults | one "fault" flag | **34 individually decoded alarms** |
| Works without internet | no | **yes** |
| Subscription | yes | no |

Per-leg voltages and currents, kW / kVA / kVAr, power factor, cumulative energy,
coolant temperature, battery voltage, engine RPM and hours, lifetime starts and trips,
the raw controller status word, and each fault condition as its own entity you can
automate on.

It also records alarms to onboard flash, so a fault that happens while Home Assistant
is down or the network is out is still reported when things come back — the one case
cloud monitoring cannot cover.

## What you need

- A Briggs & Stratton standby generator with a **GC-1030, GC-1031 or GC-1032**
  controller (check the label on the panel).
- A **B-Infohub board** — see [Getting the hardware](#getting-the-hardware).
- Home Assistant, with [HACS](https://hacs.xyz) installed.
- A Chrome or Edge browser on a desktop, once, to flash the board.

No soldering. No toolchain. No command line.

## Install

### 1. Flash the board

Connect it to your computer with a **data** USB cable and open the installer:

### → **[Install B-Infohub](https://brentb2529.github.io/B-Infohub/)**

Click Connect, pick the serial port, and wait. The page will then ask for your Wi-Fi.

<sub>A charge-only USB cable is the most common reason nothing appears in the port list —
it powers the board but carries no data, so the board looks dead to the browser while its
power light is on. Web Serial needs Chrome or Edge; Safari and Firefox do not implement it.</sub>

### 2. Wire it to the generator

**Switch the generator to OFF at the panel first.** Two wires, into the RS-485
terminals the controller already exposes — [wiring guide](docs/wiring.md), including
where the terminals are on each controller and how to keep an existing InfoHub
connected at the same time.

### 3. Add it to Home Assistant

Install the **[EnergyTrak integration](https://github.com/brentb2529/ha-energytrak)**
from HACS, then **Settings → Devices & Services → Add Integration → EnergyTrak**.

The bridge is discovered automatically if it is on the same subnet. On a routed or
VLAN'd network — which includes most setups where the generator is on a different
segment — choose **Local B-Infohub bridge** and enter its IP.

You do **not** need an EnergyTrak account. The integration supports three shapes:

- **Bridge only** — no subscription at all
- **Cloud only** — the original behaviour, no hardware
- **Both** — the bridge is used while it is healthy, and the cloud takes over
  automatically if it is not

## Getting the hardware

The board is built in small batches and is **not sold through a shop**. If you want
one, open a [GitHub issue](https://github.com/brentb2529/B-Infohub/issues) or get in
touch — see the ordering note below.

<!-- ORDERING DETAILS: fill these in before publishing.
     - How should people contact you (issue / email / form)?
     - What is supplied: bare PCB, assembled board, assembled + enclosure?
     - Price, and whether shipping is US-only.
     - Any lead time or batch-size caveat. -->

> **Ordering:** _contact details and what is supplied to be filled in._

Everything needed to have one made independently is in this repository —
schematic, layout, gerbers and a JLCPCB-ready fab package in
[`hardware/pcb/`](hardware/pcb/) — and the firmware is MIT licensed. Buying a board
is a convenience, not a requirement.

## If something looks wrong

The bridge reports its own health, because a monitor that fails silently is worse
than no monitor:

| Entity | What it means when it is unhappy |
| --- | --- |
| **Bridge reachable** | the board is not answering Home Assistant — power or Wi-Fi |
| **Generator answering bus** | the board is fine; the generator has gone quiet on RS-485 |
| **Controller clock age** | the controller is answering but its clock has stopped — it has hung |
| **Bridge silence** | the board holds its connection but has stopped sending |
| **Wi-Fi Signal** | below about −72 dBm an ESP32 stays associated but cannot be reached |

Those are deliberately five separate signals rather than one "online" flag. They fail
independently and each one points at a different place to look.

There are also five LEDs on the board readable through the lid, which is all you have
standing at the generator with no phone signal. [How to read
them](docs/bring-up.md#status-leds).

## Documentation

| | |
| --- | --- |
| [Wiring](docs/wiring.md) | terminals, cable, termination, keeping the InfoHub |
| [Bring-up](docs/bring-up.md) | first boot, LEDs, proving the bus |
| [Register map](docs/register-map.md) | every address, what it means, what it returns |
| [Field findings](docs/field-findings-2026-08-31.md) | what a real controller actually answers |
| [Development](docs/development.md) | building the firmware, the contract, the tooling |

## Safety and scope

A standby generator is life-safety equipment. This is a **read-only monitor**: it does
not start, stop, or configure anything, and engine control is deliberately not
implemented.

Do not rely on it as your only alerting for anything that matters. It is unofficial,
unaffiliated with Briggs & Stratton, and provided as-is under the MIT licence with no
warranty. Wiring anything into a generator is your responsibility; if you are not
comfortable working in the panel, have an electrician do it.

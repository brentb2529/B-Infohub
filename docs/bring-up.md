# Bring-up and bench testing

Order matters here. Each step proves one thing, so that when something fails
you know which thing.

## 0. Before the first flash

```sh
cd ~/Documents/GitHub/B-Infohub
```

**Nothing in `secrets.yaml` blocks a first flash.** No network is compiled in;
the bridge onboards on first boot (step 1 below). The device-identity secrets —
`api_encryption_key`, `ota_password`, `ap_password`, `web_password` — are already
generated and unique to this board.

| | |
|---|---|
| `wifi_ssid`, `wifi_password` | optional — only if you pre-seed a network |
| `mqtt_broker`, `mqtt_username`, `mqtt_password` | optional — only if you turn MQTT on |

MQTT ships **off**. Home Assistant reaches the bridge over the native API, so
MQTT is an extra for Grafana. Set the broker, then flip *Feature: MQTT*.

### The first flash must be over USB

Not a preference — `partitions.csv` changes the partition table, and a partition
table cannot move itself over the air. Every update after this one is OTA.

```sh
.venv/bin/esphome run genset-gc1032.yaml
```

## 1. Onboard it to your network

Three routes, all live at once. Credentials land in NVS and survive re-flashing,
so this is a one-time step.

| | how | when it is the right one |
|---|---|---|
| **USB serial** | keep the cable in after flashing; `esphome run` offers to configure Wi-Fi, or use improv-wifi.com in Chrome | on the bench — the only route available before the board leaves it |
| **Bluetooth** | Home Assistant companion app, or improv-wifi.com | at the generator pad, where you do not want a laptop |
| **Setup Wi-Fi** | join `b-infohub Setup` (password `ap_password`); a config page opens by itself | no BLE, no cable |

The WIFI LED **blinks** while the setup AP is up and goes **solid** once
associated. Blinking-versus-dark is the distinction that matters: "needs
configuring" must not look like "radio is dead".

The AP also returns if a provisioned network is unreachable for a minute, so a
router swap does not mean a trip up a ladder.

Home Assistant should then discover the bridge by itself — it advertises
`project_name: bbensten.b_infohub` over mDNS. Paste `api_encryption_key` once.

## 2. Prove the firmware without the generator

`tools/gc1032_sim.py` replays `captures/run-2026-08-31.csv` — 368 frames at
1 Hz covering a **complete cycle**: 13 s at rest, 7 s cranking, 320 s running,
28 s stopping. Better than the real generator for this: repeatable, costs no
fuel, and replays at 20× on a bench.

Wire the FTDI cable to **port A** (J3, the generator pair) and run:

```sh
.venv/bin/python tools/gc1032_sim.py serve --port /dev/tty.usbserial-XXXX --loop
```

The simulator is deliberately as unhelpful as the real controller — FC03 gets
silence rather than an error, `0xFFFF` is replayed verbatim, and reads past
`0x0056` get an illegal-address exception. Firmware that quietly depends on a
polite error passes against a nicer simulator and fails in the field.

Protocol behaviour is covered by `tools/test_sim.py`, which needs no hardware:

```sh
.venv/bin/python tools/test_sim.py
```

**What to look for:** the BUS LED goes solid, and in Home Assistant the engine
state walks *at rest → cranking → running → stopping* while voltages, currents
and power move. 26% of the captured cells are `0xFFFF`, so the "sensor not
present" filters get properly exercised — those entities should read *unknown*,
not zero.

## 3. Prove the failover

This is the failure the whole design is built around, and it is worth seeing
with your own eyes:

```sh
.venv/bin/python tools/gc1032_sim.py serve --port ... --loop --kill-bus
```

The link stays physically up; the device just stops answering. Watch:

| | expected |
|---|---|
| `Bus Healthy` | goes **false** after 3 missed polls (~30 s) |
| `Bus Age` | climbs |
| BUS LED | goes **dark** |
| `telemetry_source` in HA | flips to **cloud** |

A bridge whose RS-485 has died stays online and keeps serving its last good
readings, which look exactly like a healthy idle generator. If `telemetry_source`
does not flip, the failover is broken — and it will be silent in service.

## 4. Prove the passthrough

Turn on *Feature: InfoHub Passthrough*, keep `serve` driving port A, and put a
second adapter on **port B** (the InfoHub pair):

```sh
.venv/bin/python tools/gc1032_sim.py verify --port /dev/tty.usbserial-YYYY
```

`verify` polls the proxy and diffs **every register** against the capture. It
exits non-zero on any mismatch, so it is the end-to-end check that the inverse
scaling reconstructs raw words correctly — including the three 32-bit counters
at `0x0027`/`0x0029`/`0x002B`, which cannot round-trip through a float32 and are
captured raw for exactly this reason.

Expect `all 87 registers match`.

## 5. When the PCB arrives — the deferred tests

Everything below needs an RS-485 transceiver, which is why it was deferred: on
a bare ESP32 it means wiring a MAX485 by hand, and rev 1.0 has SP3485s on
board. Do it in this order — each step is only meaningful if the previous one
passed.

**a. Flash the assembled board over USB.** Mandatory, not preference: the
partition table changed (`backlog` region), and a table cannot relocate the
image running from it.

**b. Bench replay, before the generator.** Wire the FTDI cable to J3 and let
the Mac play the controller:

```sh
.venv/bin/python tools/gc1032_sim.py serve --port /dev/cu.usbserial-XXXX --loop
```

Expect `Modbus device=10 set online`, `bus_healthy` true, the BUS LED solid,
and roughly 100 local-only entities appearing in Home Assistant. Those entities
have never been created against real data.

**c. Failover.** Re-run with `--kill-bus`. `bus_healthy` must go false within
~30 s and `telemetry_source` must stop claiming local. A bridge that keeps
serving frozen values is the failure this whole design exists to prevent.

**d. The snapshot ring.** Stop Home Assistant while the simulator runs. The
bridge should buffer a 12-value snapshot every 60 s; restart HA and confirm the
drain replays them. UNTESTED with real values — only synthetic ones so far.

**e. The passthrough proxy.** Enable *Feature: InfoHub Passthrough*, put a
second adapter on port B, and run:

```sh
.venv/bin/python tools/gc1032_sim.py verify --port /dev/cu.usbserial-YYYY
```

It diffs every register against the capture and exits non-zero on any
mismatch. Wholly untested — including the inverse scaling that reconstructs raw
words from float sensor states.

## 6. Only then, the generator

Read `docs/wiring.md` first, especially the passthrough section.

> **Never leave the InfoHub connected to the generator's own RS-485 pair once
> this bridge is installed.** Modbus RTU permits one master. That is the two-
> master case, and it is what this whole arrangement exists to prevent.

## Reading the lights

| | solid | blinking | off |
|---|---|---|---|
| **WIFI** | associated | setup portal up — join `b-infohub Setup` | radio down |
| **BUS** | controller answering | passthrough serving an InfoHub | **nothing heard** |
| **FAULT** | generator reporting a fault | **safe mode** — push firmware | no fault |
| **PWR** | 5 V rail alive (hard-wired, cannot lie) | | buck is dead |
| **TX** | | flashes on every transmission (wired to DE, no code) | not talking |

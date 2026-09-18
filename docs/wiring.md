# Wiring

## 0. Before anything else

- **Generator selector to OFF, then disconnect the battery.** A standby generator in
  AUTO will crank while your hands are in the cabinet — it does not care that you are
  in there. This is the only genuinely dangerous step in the project.
- **Disconnect the InfoHub from the RS-485 pair.** Modbus RTU allows exactly one
  master. Leaving it wired in means collisions, corrupt frames in both directions, and
  hours spent debugging a wiring problem you do not have.
- **Meter before you connect.** Every wire colour below is what the documentation and
  the genmon community report. Your harness is the authority, not this file.

## 1. Where the bus is

The InfoHub interface harness carries five wires, and it is the easiest tap point
because it is already routed out of the engine enclosure:

| Wire | Function |
| --- | --- |
| Red | +12 VDC |
| Grey | +12 VDC (may be switched or separately fused — meter both) |
| Black | Ground |
| Brown | RS-485 data |
| Yellow | RS-485 data |

Everything this project needs is in that one connector: power and the differential
pair. Pulling the InfoHub frees all of it.

**Which of brown/yellow is A and which is B is not documented.** Nobody knows without
trying. Connect one way, and if the bus stays silent, swap them. This costs ten
seconds and is the single most common reason a first attempt reads nothing — the same
rule as the AID port on the WaterFurnace bridges.

Bus settings: whatever the controller's **Module → Communication** menu reports.
Confirm `COMM MODE` is `MODBUS` and not `None`, and note the slave ID, baud and
parity. Several of these are dealer-locked (the password lives on the B&S Power
Portal), so you may be able to view but not change them. Viewing is all you need —
match your side to whatever it says. If you cannot get into the menu, `gc1032_probe.py
scan` finds the settings without touching the panel.

## 2. Bench probing with the FTDI USB-RS485 cable

This is the fastest way to find out what the controller will actually tell you, and it
needs no soldering and no ESP32.

### Which pins get the data wires — SETTLED BY BENCH TEST

This adapter exposes **T/R+, T/R-, RXD+, RXD- and GND**. It was bench-tested with
`tools/adapter_check.py` and the answer is not the obvious one:

- **No jumpers:** transmitted correctly, received *nothing*.
- **RXD+ tied to T/R+, RXD- tied to T/R-:** clean byte-for-byte echo of the frame.

That is **full-duplex RS-422 silicon**. Its driver is on T/R± and its receiver is on a
*separate* RXD± pair. Used as 2-wire RS-485 without the jumpers it talks and never
hears — which on a live bus is indistinguishable from a reversed pair, a dead
controller, or the InfoHub stealing the replies.

**Keep the jumpers. Final wiring:**

| Adapter | | Connect to |
| --- | --- | --- |
| **T/R+** *and* **RXD+** tied together | → | one harness data wire (bus A) |
| **T/R-** *and* **RXD-** tied together | → | the other harness data wire (bus B) |
| **GND** | → | harness black (ground) |

If the adapter also has a +5 V / VBUS lead, leave it disconnected and heat-shrink it.
It is an output from the USB bus, and the harness has +12 V on red and grey — bridging
them back-feeds 12 V into the Mac's USB port.

The only unknown left at the generator is which harness data wire is A. If `scan`
finds nothing, swap the two joined pairs and run it once more. Nothing here can damage
the controller or the adapter — a reversed differential pair simply decodes nothing.

Re-verify at any time, with nothing connected to the generator:

```bash
python3 tools/adapter_check.py --port /dev/cu.usbserial-A94C31KL --jumpered
```

### Use /dev/cu.*, not /dev/tty.*

macOS exposes every serial device twice. `/dev/tty.*` is the *incoming* (dial-in) node
and blocks on open until it sees carrier detect, which a USB-RS485 adapter never
asserts — so it can hang instead of failing. `/dev/cu.*` ("callout") is the outbound
node and is the correct one here. Same device, same adapter, different open semantics.

Verified working on this machine: **`/dev/cu.usbserial-A94C31KL`**.

### Then

```bash
pip install pyserial
ls /dev/cu.usbserial-*                       # find the port
python3 tools/gc1032_probe.py scan  --port /dev/cu.usbserial-XXXXXXXX
python3 tools/gc1032_probe.py dump  --port /dev/cu.usbserial-XXXXXXXX --baud 19200 --parity N
python3 tools/gc1032_probe.py sweep --port /dev/cu.usbserial-XXXXXXXX --baud 19200 --parity N
```

`scan` brute-forces baud, parity and slave id. `dump` reads every documented register
once. `sweep` probes the whole low register space twice and reports which
**undocumented** registers respond and which ones moved — that is where data the
InfoHub never showed you lives. Run `sweep` again during an exercise cycle; most of
the interesting registers only change while the engine is turning.

The probe tool never writes. There is no write function in it at all.

## 3. Permanent install — ESP32 + MAX485

Same hardware pattern as the WaterFurnace bridges: ESP32-DevKitC 38-pin
(ESP32-WROOM-32D) plus a MAX485 module **with exposed DE/RE pins**. Auto-direction
modules are unreliable at Modbus timing — if that is what you have, replace it rather
than fight it.

| From | To | Notes |
| --- | --- | --- |
| MAX485 DI | ESP **GPIO17** | ESP transmits into the module |
| MAX485 RO | ESP **GPIO16** | module output to ESP (3.3 V logic, since VCC is 3.3 V) |
| MAX485 DE **and** RE (bridge them) | ESP **GPIO4** | HIGH to transmit, LOW to receive |
| MAX485 VCC | ESP **3V3** | clone modules run fine at 3.3 V on a short stub |
| MAX485 GND | ESP GND | |
| MAX485 A | harness data wire 1 | swap with B if the bus never connects |
| MAX485 B | harness data wire 2 | |
| Buck 5 V out | ESP **VIN** | see below — never feed VIN from anything unregulated |
| Buck ground | ESP GND | common with harness black |

These pins match `genset-gc1032.yaml`; change them there, not here.

**Termination.** With the InfoHub removed you are one of two nodes, so the module's
onboard 120 Ω is correct — leave it. If you ever put a third device back on the pair,
termination belongs at the two physical ends only and this module's resistor must come
off (solder jumper on most clones; some are hard-wired and need the resistor lifted).

## 4. The 12 V power front end

The harness gives you +12 V, but treat it as automotive DC, not a clean rail:

- Resting ~12.6–13.2 V; ~13.5–14.6 V while the charger is on.
- **Cranking drops it to 8–9 V for a second or two on every start.** A converter with
  a 9 V minimum input browns out the ESP32 at exactly the moment you most want data.
- Load dump when the starter disengages — an inductive spike above 14 V.

So, in order from the harness:

```
harness +12 V ──[ 1 A fuse ]──[ reverse-polarity Schottky or P-FET ]──┬──[ TVS to GND ]
                                                                      │
                                                          [ bulk cap, 220–470 µF ]
                                                                      │
                                                   [ wide-input 5 V DC-DC ] ── ESP32 VIN
harness ground ───────────────────────────────────────────────────────┴──────── ESP32 GND
```

| Part | Spec | Why |
| --- | --- | --- |
| DC-DC | **Recom R-78E5.0-1.0** (7–28 V in, 5 V @ 1 A) or any automotive 6–36 V unit | Wide input range is the whole point — it rides through cranking |
| Fuse | 1 A inline | |
| TVS | SMBJ16A or 1.5KE18A across the input | Clamps the load dump |
| Reverse protection | Schottky or P-FET | |
| Bulk cap | 220–470 µF | Holds the rail up through the crank dip |

Do **not** use a bare LM2596 module. They have no transient protection and the common
clones are marginal on both input range and noise.

Size for 1 A — Wi-Fi TX peaks pull 300–500 mA.

## 5. Grounding: pick one lane and stay in it

Powering from the generator battery means the ESP32's ground **is** the generator's
ground. That is fine, and it is why a non-isolated MAX485 is acceptable here — but
only because there is no second ground reference:

- **This build: battery power + Wi-Fi only.** One ground reference. Nothing to fight.
- **Alternative: PoE from the house + isolated RS-485 (ADM2582E).** The isolator breaks
  the loop.

What you must never do is power from the generator battery **and** run Ethernet back
to the house with a non-isolated transceiver. That puts the full house-to-pad ground
potential difference across the board.

Mount in a poly NEMA 4X enclosure **outside** the engine enclosure. Under-hood ambient
plus vibration kills a dev board faster than anything electrical will.

---

## InfoHub passthrough (PCB rev 1.0, port B)

Enabled by `packages/passthrough.yaml` and the **Feature: InfoHub Passthrough**
switch. Off by default.

### Why it is not optional to get this right

Modbus RTU permits exactly one master. The InfoHub is a master. So is this
bridge. Wire both to the generator's RS-485 pair and they transmit over each
other — corrupt frames in both directions, and an InfoHub reporting comm faults
to your dealer.

The board avoids that in hardware, with two transceivers:

| | Transceiver | ESP32 pins | Role |
|---|---|---|---|
| Port A | U3 | IO17 TX, IO16 RX, IO4 DE/RE | **master** — talks to the generator |
| Port B | U4 | IO22 TX, IO23 RX, IO21 DE/RE | **slave** — answers the InfoHub |

The InfoHub is no longer on the generator's bus at all. It talks to *us*, and
we answer at the same slave address from the values we just read. It cannot
tell the difference.

### Wiring

```
  generator RS-485  ──────►  J3 (A/B)   port A   sole master
  generator 12 V    ──────►  J1 (+/−)

  J2 (+/−)          ──────►  InfoHub 12 V        passthrough power
  J3 (A/B, IH pair) ──────►  InfoHub RS-485      port B
```

Never leave the InfoHub connected to the generator's own RS-485 pair once this
bridge is installed. That is the two-master case, and it is the one failure
mode this whole arrangement exists to prevent.

### What is served

All 84 registers across `0x0000`–`0x0056`, reconstructed from the scaled sensor
values by inverting each filter's `multiply`. Reconstruction rather than a
second raw read of the same addresses: a duplicate read would double traffic on
a 9600 baud bus the field notes already warn against saturating.

The round trip is exact for every 16-bit register — verified across all 65536
values at each scale in use (0.1, 0.01, 1/256, 1.0).

The three **32-bit** counters at `0x0027`, `0x0029` and `0x002B` are a special
case. An ESPHome sensor state is a float32 with 24 bits of mantissa, so above
~16.7 million it cannot hold a 32-bit counter exactly — 98% of values come back
altered. Those three are therefore captured as raw words from the response
bytes in `gc1032-power.yaml`, before any float is involved, and served from
there.

A register never read, or one the controller reported as `0xFFFF` ("sensor not
present"), is served as `0xFFFF` — exactly what the InfoHub would have seen
from the controller itself.

### What is NOT served: writes

**The InfoHub can no longer command the generator through this bridge.** Remote
start/stop from the Briggs app stops working; monitoring and cloud reporting
continue.

This is deliberate. Proxying writes would mean this bridge cranking an engine on
behalf of a remote request it cannot authenticate, using the control path that
was explicitly removed from this build. If you need remote start, wire the
InfoHub directly to the generator and do not run this bridge — you cannot have
both on one pair.

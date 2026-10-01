# Ordering — B-Infohub Bridge v1.1

## 1. PCB + assembly (JLCPCB)

Upload as-is:

| File | Where it goes |
| --- | --- |
| `binfohub_bridge_jlc.zip` | Gerber upload |
| `bom_jlc.csv` | Assembly → BOM |
| `cpl_jlc.csv` | Assembly → pick-and-place (CPL) |

Board options: **90 × 92 mm, 2 layers, 1.6 mm FR4, 1 oz copper, HASL or ENIG,
green/any mask.** Nothing here needs impedance control, castellation, or special
finish. Same outline and holes as rev 1.0 — it fits the rev 1.0 enclosure.

Assembly: **top side only.** Every SMT part is on F.Cu, **including the ESP32
module** (rev 1.1 solders an ESP32-WROOM-32E; there are no socket rows any more).
The through-hole parts (J1–J6, JP1, JP2) are flagged in the BOM as
`JLC THT (economic, hand-solder fee)` — include them if you want JLC to fit them,
or drop those rows and hand-solder.

**35 distinct LCSC parts** (38 BOM lines). Stock was checked on 2026-10-01 for the
parts new in rev 1.1 (module, AP63203, AO3400A, SS14, TS-1187A, 0.5 A polyfuse,
1 µF / 10 µF); re-check the rest in JLC's BOM review before paying — rev 1.0's
check is a month old.

## 2. Loose parts — NOT on the PCB BOM

JLC will not place these; order them as normal LCSC line items, or use what you have.

| Qty | Part | LCSC | Note |
| --- | --- | --- | --- |
| 2–4 | 2.54 mm jumper shunt (black, capped) | **C100114** | JP1 / JP2 termination. **Ship the board with these OFF** — see the termination section in README.md. Buy spares; they cost nothing and vanish. |
| 1 | 3.3 V USB-serial adapter (CP2102 / CH340, with a 3.3 V logic setting) | any | For the one first flash through J6. Wire GND, TX→RX, RX→TX; hold BOOT, tap RESET, `esphome run`. Do not power the board from it — feed 12 V on J1. |

Optional, depending on how you build it:

| Qty | Part | Note |
| --- | --- | --- |
| 1 | **ESP32-WROOM-32UE-N4** (C2934568) in place of the -32E | Remote antenna. Same pads; swap the U1 line in the BOM. |
| 1 | U.FL → SMA bulkhead pigtail + 2.4 GHz antenna | With the -32UE. The U.FL is on the module's top face, at its antenna end (board +x). |
| 1 | 12 V 2-wire fan, ≤ 0.5 A (40–60 mm) | J5. Only if shading/venting the box is not enough; see *Heat* in README.md. Enable `packages/fan.yaml` in the firmware. |
| 5 | 3 mm clear acrylic rod, 21 mm | Light pipes — see the enclosure README |
| 12 | M3 × 5 × 4.6 brass heat-set inserts | Enclosure |
| 3 | PG7 cable gland | Enclosure |
| 2 | M12 × 1.5 Gore-type vent | Enclosure — one low, **one high**, so the box convects. Rev 1.0 had one, low, and still reached 188 °F at the die. |

## 3. Before you press order

- **Terminal-block orientation.** `circuit.py` rotates every screw terminal 180° so
  the wire openings face the board edge. This is the exact issue JLC's DFM review
  flagged on the b-hydro board. Check the 3D render they generate: **J1/J2/J3 wire
  openings should face outward, toward the top edge; J5 (fan, interior) faces the
  same way.**
- **J2 is 2-position, J3 is 4-position, J5 is 2-position.** If the render shows
  anything else, stop.
- **U1 orientation — new in rev 1.1, not yet verified in JLC's viewer.** The
  module's antenna end must point at the right-hand board edge (+x), over the bare
  copper-free strip. JLC's library rotation for this package is unknown; if the
  render shows the antenna pointing into the board, fix the `ESPW` entry in
  `ROT_FIX` (tools/gen_bom.py) and re-export the CPL. Same check for **D10** (SS14
  cathode band toward F3 / the +12 V side) and the two **TS-1187A** switches
  (symmetric; any rotation is fine).
- The `lib_footprint_mismatch` DRC warnings on J2/J3/J5 are expected: the locating
  pegs are deliberately stripped because the KF128 parts we buy do not have them.

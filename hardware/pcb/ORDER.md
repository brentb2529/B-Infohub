# Ordering — B-Infohub Bridge v1.0

## 1. PCB + assembly (JLCPCB)

Upload as-is:

| File | Where it goes |
| --- | --- |
| `binfohub_bridge_jlc.zip` | Gerber upload |
| `bom_jlc.csv` | Assembly → BOM |
| `cpl_jlc.csv` | Assembly → pick-and-place (CPL) |

Board options: **90 × 92 mm, 2 layers, 1.6 mm FR4, 1 oz copper, HASL or ENIG,
green/any mask.** Nothing here needs impedance control, castellation, or special
finish.

Assembly: **top side only.** Every SMT part is on F.Cu. The through-hole parts
(J1–J4, JP1, JP2 and the two ESP32 socket rows) are flagged in the BOM as
`JLC THT (economic, hand-solder fee)` — include them if you want JLC to fit them,
or drop those rows and hand-solder.

**28 distinct LCSC parts, all verified in stock. 10 are JLC *basic* parts** (no
per-part setup fee); the other 18 are extended.

## 2. Loose parts — NOT on the PCB BOM

JLC will not place these; order them as normal LCSC line items, or use what you have.

| Qty | Part | LCSC | Note |
| --- | --- | --- | --- |
| 2–4 | 2.54 mm jumper shunt (black, capped) | **C100114** | JP1 / JP2 termination. $0.009 each, 879 k in stock. **Ship the board with these OFF** — see the termination section in README.md. Buy spares; they cost nothing and vanish. |

### A note on the ESP32 sockets (U1A / U1B)

They **are** placed by JLC — `C319202`, 5364 in their assembly stock, confirmed in
their own part search on 2026-08-31.

If you ever see them come back as Qty 0 in the BOM review, the cause is almost
certainly a duplicate-line warning earlier in the same upload leaving the row
deselected, not a stock problem. Re-select the part with the row's magnifier icon
rather than accepting "do not place".

Optional, depending on how you build it:

| Qty | Part | Note |
| --- | --- | --- |
| 1 | ESP32-DevKitC-32**U** | Only if you want an external antenna. Same socket as the -32. |
| 1 | U.FL → RP-SMA bulkhead pigtail | With the -32U |
| 5 | 3 mm clear acrylic rod, 21 mm | Light pipes — see the enclosure README |
| 12 | M3 × 5 × 4.6 brass heat-set inserts | Enclosure |
| 3 | PG7 cable gland | Enclosure |
| 1 | M12 × 1.5 Gore-type vent | Enclosure |

## 3. Before you press order

- **Terminal-block orientation.** `circuit.py` rotates every screw terminal 180° so
  the wire openings face the board edge. This is the exact issue JLC's DFM review
  flagged on the b-hydro board. Check the 3D render they generate: **all wire
  openings should face outward, toward the nearest board edge.**
- **J2 is 2-position, J3 is 4-position.** If the render shows anything else, stop.
- The one DRC warning (`lib_footprint_mismatch` on J2) is expected: the locating pegs
  are deliberately stripped because the KF128 parts we buy do not have them.

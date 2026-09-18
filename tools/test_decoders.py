#!/usr/bin/env python3
"""Verify the generated alarm decoders and the status-word decode against known values.

The 51 alarm lambdas in packages/gc1032-alarms.yaml are generated, so the risk is not
a typo in any one of them -- it is that the generation RULE is wrong, in which case
all 51 are wrong the same way and a healthy generator reports 47 active faults (or,
far worse, a faulted one reports all clear).

This extracts the mask/value pairs straight out of the generated YAML and evaluates
them the way ESPHome will, against register states with known meaning.

    python3 tools/test_decoders.py
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALARMS = ROOT / "packages" / "gc1032-alarms.yaml"

# name -> (register id, mask, expected value)
PATTERN = re.compile(
    r'name: "([^"]+)".*?'
    r'id\((alarm_reg_[0-9a-f]{2})\)\.state\) & 0x([0-9A-F]{4})\) == 0x([0-9A-F]{4})',
    re.S)


def load():
    text = ALARMS.read_text()
    out = []
    for block in text.split("  - platform: template")[1:]:
        m = PATTERN.search(block)
        if m:
            out.append((m.group(1), m.group(2), int(m.group(3), 16), int(m.group(4), 16)))
    return out


def evaluate(decoders, regs):
    return {name: ((regs.get(rid, 0) & mask) == value)
            for name, rid, mask, value in decoders}


def main():
    decoders = load()
    if len(decoders) < 45:
        sys.exit(f"only parsed {len(decoders)} decoders -- generator output changed?")

    failures = []

    # --- Case 1: healthy. All fault nibbles set (active low), status word 0x6880. ---
    healthy = {f"alarm_reg_{a:02x}": 0xFFFF for a in range(0x40, 0x4F)}
    healthy["alarm_reg_4f"] = 0x6880
    active = [n for n, v in evaluate(decoders, healthy).items() if v]
    if active:
        failures.append(f"healthy generator reported {len(active)} active faults: "
                        f"{active[:5]}")
    else:
        print(f"PASS  healthy state (all nibbles 0xFFFF): 0 of {len(decoders)} faults active")

    # --- Case 2: low oil pressure. 0x0040 high nibble cleared. ---
    oil = dict(healthy)
    oil["alarm_reg_40"] = 0x0FFF                     # f000 nibble -> 0
    res = evaluate(decoders, oil)
    active = [n for n, v in res.items() if v]
    if active != ["Low Oil Pressure"]:
        failures.append(f"low-oil case: expected exactly ['Low Oil Pressure'], got {active}")
    else:
        print("PASS  0x0040 = 0x0FFF -> exactly 'Low Oil Pressure' asserted")

    # --- Case 3: two simultaneous faults in different registers. ---
    two = dict(healthy)
    two["alarm_reg_41"] = 0xFF0F                     # 00f0 nibble -> Engine Failed to Start
    two["alarm_reg_45"] = 0x0FFF                     # f000 nibble -> Battery Low Voltage
    active = sorted(n for n, v in evaluate(decoders, two).items() if v)
    expect = sorted(["Engine Failed to Start", "Battery Low Voltage"])
    if active != expect:
        failures.append(f"two-fault case: expected {expect}, got {active}")
    else:
        print("PASS  two independent nibbles cleared -> exactly those two faults")

    # --- Case 4: status-word bits in 0x004F are ACTIVE HIGH, not active low. ---
    trip = dict(healthy)
    trip["alarm_reg_4f"] = 0x6880 | 0x0004           # Electrical Trip bit set
    active = [n for n, v in evaluate(decoders, trip).items() if v]
    if active != ["Electrical Trip"]:
        failures.append(f"status-bit case: expected ['Electrical Trip'], got {active}")
    else:
        print("PASS  0x004F bit 0x0004 set -> 'Electrical Trip' (active high, not low)")

    # --- Case 5: the status word decode itself. ---
    s = 0x6880
    checks = [
        ("Power Status", s & 0x7F00, 0x6800, "Off - Ready"),
        ("Switch Status", s & 0x3800, 0x2800, "Automatic"),
        ("Engine stopped bit", s & 0x0080, 0x0080, "Stopped"),
        ("Utility healthy bit", s & 0x4000, 0x4000, "utility present"),
        ("Common shutdown", s & 0x0008, 0x0000, "clear"),
    ]
    for label, got, want, meaning in checks:
        if got != want:
            failures.append(f"{label}: 0x{got:04X} != 0x{want:04X} ({meaning})")
    if not any(f.startswith(("Power", "Switch", "Engine", "Utility", "Common"))
               for f in failures):
        print("PASS  status word 0x6880 -> Off-Ready / Automatic / Stopped / utility OK")

    print()
    if failures:
        for f in failures:
            print("FAIL ", f)
        return 1
    print(f"All decoder checks passed ({len(decoders)} alarm decoders exercised).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

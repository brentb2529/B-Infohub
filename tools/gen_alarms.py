#!/usr/bin/env python3
"""Generate packages/gc1032-alarms.yaml from vendor/Briggs_Stratton_GC-1032.json.

Every alarm on the GC-1032 is a bitfield test against one of the raw registers
0x0040-0x004F, which gc1032-status.yaml exposes as internal sensors named
`alarm_reg_40` .. `alarm_reg_4f`.

The decode rule is uniform: the condition is ASSERTED when (raw & mask) == value.

That looks backwards for most of them, and it is worth understanding why. The fault
nibbles are ACTIVE LOW -- genmon encodes them as mask "f000" with value "0000", so a
nibble reading zero means the fault is present, not absent. The handful of conditions
living in the status word 0x004F are ordinary active-high bits (mask == value). Both
fall out of the same expression, so this generator does not special-case them.

Regenerate after bumping the vendored JSON:

    python3 tools/gen_alarms.py

Do not hand-edit the generated file.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "vendor" / "Briggs_Stratton_GC-1032.json"
BASELINE = ROOT / "vendor" / "baseline-2026-08-31.json"
DST = ROOT / "packages" / "gc1032-alarms.yaml"

HEADER = """# GENERATED FILE -- DO NOT EDIT.
# Regenerate with: python3 tools/gen_alarms.py
# Source: vendor/Briggs_Stratton_GC-1032.json  (genmon alarm_conditions)
#
# {count} fault conditions decoded from raw registers 0x0040-0x004F, which are polled
# as internal sensors in gc1032-status.yaml.
#
# Decode rule: asserted when (raw & mask) == value. The fault nibbles are ACTIVE LOW
# (mask f000 / value 0000), so a nibble of zero means the fault IS present. This is
# the single most common thing to get backwards on this controller.

binary_sensor:
"""

ENTRY = """  - platform: template
    name: "{name}"
    device_class: problem
    lambda: |-
      if (isnan(id({reg_id}).state)) return {{}};
      return (((uint16_t) id({reg_id}).state) & 0x{mask:04X}) == 0x{value:04X};
"""


def load_baseline():
    """Register values read from the real controller while it was demonstrably healthy.

    Any condition that evaluates TRUE against this snapshot cannot be a fault -- the
    generator was sitting in Off-Ready with the utility present and the engine stopped.
    It is an unpopulated input whose nibble reads 0 because nothing is wired to it.
    """
    if not BASELINE.exists():
        return None
    raw = json.loads(BASELINE.read_text())["registers"]
    return {k.lower(): int(v, 16) for k, v in raw.items()}


def main() -> None:
    data = json.loads(SRC.read_text())
    conditions = data["alarm_conditions"]
    baseline = load_baseline()

    out = [HEADER.format(count=len(conditions))]
    skipped = []
    absent = []

    for cond in conditions:
        reg = cond["reg"].lower()
        text = cond["text"]
        mask = int(cond["mask"], 16)

        if cond.get("type") != "bits":
            # 0x0044's "Maintenance Required" is typed `regex` in genmon and is not a
            # plain bitfield equality test. Emit it, but flag it as unverified rather
            # than silently guessing a decode that could hide a real service alert.
            nibble_shift = (mask & -mask).bit_length() - 1
            out.append(
                f"""  # UNVERIFIED DECODE -- genmon types this as `{cond.get('type')}`, not `bits`.
  # Confirm against the controller's own display before trusting it.
  - platform: template
    name: "{text}"
    device_class: problem
    disabled_by_default: true
    lambda: |-
      if (isnan(id(alarm_reg_{reg[2:]}).state)) return {{}};
      return ((((uint16_t) id(alarm_reg_{reg[2:]}).state) & 0x{mask:04X}) >> {nibble_shift}) == {int(cond['value'])};
"""
            )
            skipped.append(text)
            continue

        value = int(cond["value"], 16)
        not_present = (baseline is not None
                       and reg in baseline
                       and (baseline[reg] & mask) == value)
        if not_present:
            absent.append(text)
            out.append(
                f"""  # NOT PRESENT on this unit. Asserted in the healthy baseline capture
  # (vendor/baseline-2026-08-31.json, reg 0x{reg.upper()} = 0x{baseline[reg]:04X}), which means
  # nothing is wired to this input rather than that it is faulted. Left in place,
  # disabled, so it can be switched on if the sensor is ever fitted.
""" + ENTRY.format(
                    name=text, reg_id=f"alarm_reg_{reg[2:]}", mask=mask, value=value
                ).replace('    device_class: problem\n',
                          '    device_class: problem\n    disabled_by_default: true\n')
            )
            continue

        out.append(
            ENTRY.format(
                name=text,
                reg_id=f"alarm_reg_{reg[2:]}",
                mask=mask,
                value=value,
            )
        )

    DST.write_text("\n".join(out))
    print(f"wrote {DST.relative_to(ROOT)} ({len(conditions)} conditions)")
    if absent:
        print(f"  disabled as NOT PRESENT on this unit ({len(absent)}), from the "
              f"healthy baseline: " + ", ".join(absent))
    if skipped:
        print("  flagged as unverified (non-bits decode): " + ", ".join(skipped))


if __name__ == "__main__":
    main()

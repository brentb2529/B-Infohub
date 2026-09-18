#!/usr/bin/env python3
"""A fake GC-1032 on a pseudo-terminal, for testing the probe without a generator.

Serves Modbus RTU over a pty so `gc1032_probe.py` can be exercised end to end on a
desk. Reproduces the controller's awkward behaviours on purpose:

  * FC04 (input registers) for the documented map, with plausible at-rest values.
  * The address holes (0x002D-0x0032, 0x003E-0x003F) and 0x00B5 SILENTLY TIME OUT
    rather than returning a clean exception -- which is what makes them dangerous.
  * A few undocumented-but-live registers, so the `sweep` hunt has something to find.
  * FC03/FC06 on holding register 0x0000 for the control path.

What this CANNOT test: baud rate and parity detection. A pty ignores line settings,
so `scan` will match on its first attempt regardless. Real bus timing, turnaround and
electrical behaviour are equally out of scope. This validates the code, not the wire.

    python3 tools/fake_gc1032.py          # prints its pty path, then serves
"""

import json
import os
import pathlib
import sys
import termios
import tty

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "vendor" / "Briggs_Stratton_GC-1032.json").read_text())

SLAVE_ID = 1
DEAD = set(range(0x002D, 0x0033)) | {0x003E, 0x003F, 0x00B5}


def crc16(frame: bytes) -> bytes:
    crc = 0xFFFF
    for byte in frame:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_registers():
    """A healthy 26 kW unit sitting in AUTO, engine stopped, utility present."""
    r = {a: 0 for a in range(0x0000, 0x0057)}
    r[0x0000] = 2                      # protocol revision
    for a in range(0x0001, 0x000A):
        r[a] = 0                       # generator not producing
    r[0x000D] = 100                    # avg power factor 1.00
    r[0x000E] = r[0x000F] = 1207       # utility L-N 120.7 V
    r[0x0011] = 2413                   # utility L1-L2 241.3 V
    r[0x0014] = 600                    # utility 60.0 Hz
    r[0x001E] = 0                      # 0% load
    r[0x0027], r[0x0028] = 0x0000, 0x2B67   # 1114.3 kWh cumulative (32-bit)
    r[0x0033] = 0                      # oil pressure, engine stopped
    r[0x0034] = 212                    # 21.2 C
    r[0x0038] = 131                    # battery 13.1 V
    r[0x0039] = 0                      # 0 RPM
    r[0x003A] = 47                     # starts
    r[0x003B] = 0                      # trips
    r[0x003C] = 122                    # run hours
    r[0x003D] = 30                     # run minutes
    for a in range(0x0040, 0x004F):
        r[a] = 0xFFFF                  # ACTIVE LOW: all nibbles set == no faults
    # Off-Ready (0x6800) + utility healthy (0x4000, already in 0x6800) + stopped (0x0080).
    # Masked against 0x3800 this also reads as Automatic.
    r[0x004F] = 0x6880
    r[0x0050] = 0x2D00                 # minutes in high byte -> :45
    r[0x0051] = 0x000E                 # hours in low byte -> 14
    r[0x0052] = 0x0813                 # month 8 / day 19
    r[0x0053] = 2026
    r[0x0054] = 26 << 8                # nominal 26 kW
    r[0x0055] = 0x0104                 # firmware 1.4
    r[0x0056] = 0x1234
    # Undocumented but live -- what `sweep` is meant to surface.
    r[0x00B8] = 0x00AA
    r[0x00C0] = 0x0100
    return r


REGS = build_registers()
_tick = [0]


def read_regs(start, count):
    """None means 'do not answer at all', i.e. simulate the timeout."""
    if any((start + i) in DEAD for i in range(count)):
        return None
    out = []
    for i in range(count):
        a = start + i
        if a not in REGS:
            return None
        v = REGS[a]
        # Make a couple of registers move between passes so `sweep` can prove it
        # detects change: battery sags slightly, and one undocumented register walks.
        if a == 0x0038:
            v = 131 - (_tick[0] % 3)
        elif a == 0x00B8:
            v = 0x00AA + _tick[0]
        out.append(v & 0xFFFF)
    return out


def handle(req: bytes):
    if len(req) < 8 or req[0] != SLAVE_ID:
        return None
    if crc16(req[:-2]) != req[-2:]:
        return None

    func = req[1]
    start = (req[2] << 8) | req[3]

    if func in (0x04, 0x03):
        count = (req[4] << 8) | req[5]
        if func == 0x03:
            body = [0x0004] * count if start == 0x0000 else None
        else:
            body = read_regs(start, count)
        if body is None:
            return None                       # silence == timeout
        payload = b"".join(bytes([v >> 8, v & 0xFF]) for v in body)
        resp = bytes([SLAVE_ID, func, len(payload)]) + payload
        return resp + crc16(resp)

    if func == 0x06:
        value = (req[4] << 8) | req[5]
        print(f"  [sim] WRITE holding 0x{start:04X} = 0x{value:04X}", file=sys.stderr)
        return req                            # echo, per spec

    resp = bytes([SLAVE_ID, func | 0x80, 0x01])
    return resp + crc16(resp)


def main():
    master, slave = os.openpty()
    for fd in (master, slave):
        tty.setraw(fd)
        termios.tcsetattr(fd, termios.TCSANOW, termios.tcgetattr(fd))
    print(os.ttyname(slave), flush=True)

    buf = b""
    while True:
        try:
            chunk = os.read(master, 256)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        # Every request this controller answers is exactly 8 bytes.
        while len(buf) >= 8:
            req, buf = buf[:8], buf[8:]
            _tick[0] += 1
            resp = handle(req)
            if resp:
                os.write(master, resp)


if __name__ == "__main__":
    main()

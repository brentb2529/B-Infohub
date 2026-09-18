#!/usr/bin/env python3
"""Protocol tests for the GC-1032 simulator. No hardware, no serial port.

    python3 tools/test_sim.py

Checks the behaviours that make the simulator worth trusting: that it is as
UNHELPFUL as the real controller where the real controller is unhelpful.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gc1032_sim import crc16, handle_request, load_capture, DEFAULT_CAPTURE, LAST_REG

def req(slave, func, start, count):
    b = bytes([slave, func, start >> 8, start & 0xFF, count >> 8, count & 0xFF])
    return b + crc16(b)

stamps, frames = load_capture(DEFAULT_CAPTURE)
f = frames[100]                      # mid-run frame
ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'PASS' if cond else '** FAIL'}  {name}{'  ' + extra if extra else ''}")
    ok &= bool(cond)

print(f"capture: {len(frames)} frames, registers 0x0000-0x{LAST_REG:04X}\n")

r = handle_request(req(10, 4, 0x0000, 4), f, 10)
check("FC04 read of 4 registers answers", r is not None and len(r) == 13)
if r:
    words = [(r[3+i*2] << 8) | r[4+i*2] for i in range(4)]
    check("values match the capture", words == f[0:4], f"{[hex(w) for w in words]}")
    check("reply CRC is valid", crc16(r[:-2]) == r[-2:])

check("FC03 (holding) gets SILENCE, as the real unit does",
      handle_request(req(10, 3, 0x0000, 1), f, 10) is None)
check("wrong slave id ignored", handle_request(req(11, 4, 0, 4), f, 10) is None)
check("corrupt CRC ignored", handle_request(req(10, 4, 0, 4)[:-1] + b"\x00", f, 10) is None)

r = handle_request(req(10, 4, 0x0050, 20), f, 10)
check("read past 0x0056 -> illegal data address",
      r is not None and r[1] == 0x84 and r[2] == 0x02)
r = handle_request(req(10, 6, 0x0000, 1), f, 10)
check("write (FC06) -> illegal function",
      r is not None and r[1] == 0x86 and r[2] == 0x01)
check("--kill-bus goes mute while wired",
      handle_request(req(10, 4, 0, 4), f, 10, kill_bus=True) is None)

r = handle_request(req(10, 4, 0x0000, LAST_REG + 1), f, 10)
check("full-map read (87 registers) answers", r is not None and r[2] == 174)

sent = handle_request(req(10, 4, 0x0003, 1), f, 10)
check("0xFFFF 'not present' replayed verbatim",
      sent is not None and ((sent[3] << 8) | sent[4]) == f[3], f"0x{f[3]:04X}")

st = [fr[0x004F] for fr in frames]
runs = []
for v in st:
    if not runs or runs[-1][0] != v: runs.append([v, 0])
    runs[-1][1] += 1
check("capture contains a full cycle (rest -> crank -> run -> stop)",
      len(runs) == 4 and runs[0][0] == 0x6880 and runs[2][0] == 0x6100,
      " ".join(f"0x{v:04X}x{n}" for v, n in runs))

print("\n" + ("ALL PASS" if ok else "FAILURES ABOVE"))
sys.exit(0 if ok else 1)

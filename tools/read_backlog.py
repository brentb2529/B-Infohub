#!/usr/bin/env python3
"""Decode the on-flash event log over USB.

    python3 tools/read_backlog.py --port /dev/cu.usbserial-0001

Reads the raw partition rather than asking the firmware, so it also works when
the firmware is the thing under suspicion.
"""
import argparse, struct, subprocess, sys, pathlib

PART_OFF, EVENT_REGION = 0x3B0000, 0x10000
TYPES = {1: "ALARM SET", 2: "ALARM CLEAR", 3: "BOOT",
         4: "BUS LOST", 5: "BUS BACK", 6: "LINK LOST", 7: "LINK BACK"}

def crc_of(seq, ts, typ, idx, val):
    return ((seq * 2654435761) ^ (ts * 40503) ^ (typ << 16) ^ (idx << 8) ^ val) & 0xFFFFFFFF

a = argparse.ArgumentParser()
a.add_argument("--port", required=True)
a.add_argument("--out", default="/tmp/backlog.bin")
a.add_argument("--names", default="contract/alarm_index.json")
n = a.parse_args()

venv = pathlib.Path(__file__).resolve().parent.parent / ".venv/bin/python"
r = subprocess.run([str(venv), "-m", "esptool", "--port", n.port, "--baud", "115200",
                    "--before", "default-reset", "--after", "hard-reset",
                    "read-flash", hex(PART_OFF), hex(EVENT_REGION), n.out],
                   capture_output=True, text=True)
if r.returncode:
    sys.exit(r.stdout[-400:] + r.stderr[-400:])

names = []
try:
    import json
    names = json.loads(pathlib.Path(n.names).read_text())["index"]
except Exception:
    pass

d = pathlib.Path(n.out).read_bytes()
recs = []
for i in range(0, len(d), 16):
    seq, ts, typ, idx, val, crc = struct.unpack("<IIBBHI", d[i:i+16])
    if seq == 0xFFFFFFFF:
        continue
    ok = crc == crc_of(seq, ts, typ, idx, val)
    recs.append((seq, ts, typ, idx, val, ok))
recs.sort()
print(f"{len(recs)} records in the event ring ({EVENT_REGION//16} slots)\n")
import datetime
for seq, ts, typ, idx, val, ok in recs:
    when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "(clock not set)"
    what = TYPES.get(typ, f"type{typ}")
    who = f"  {names[idx]}" if typ in (1, 2) and idx < len(names) else ""
    print(f"  seq {seq:<5} {when:<21} {what}{who}" + ("" if ok else "   ** BAD CRC"))
bad = sum(1 for *_, ok in recs if not ok)
print(f"\n  {len(recs)-bad} valid, {bad} corrupt")

#!/usr/bin/env python3
"""Replay a captured GC-1032 session as a live Modbus RTU device.

    # stand in for the generator, feeding the bridge's port A
    python3 tools/gc1032_sim.py serve --port /dev/tty.usbserial-XXXX

    # stand in for the InfoHub, polling the bridge's port B
    python3 tools/gc1032_sim.py poll --port /dev/tty.usbserial-YYYY

    # end-to-end: is the proxy handing back what we fed in?
    python3 tools/gc1032_sim.py verify --port /dev/tty.usbserial-YYYY

WHY THIS EXISTS

The capture in captures/run-2026-08-31.csv is 368 frames at 1 Hz covering a
complete cycle -- 13 s at rest, 7 s cranking, 320 s running, 28 s stopping.
That is a far better test fixture than the generator itself, because it is
repeatable, it costs no fuel, and it can be replayed at 20x on a bench.

FIDELITY DETAILS THAT MATTER

Copied from the real controller's observed behaviour, because a simulator that
is nicer than the hardware teaches you nothing:

  * FC04 (input registers) only. FC03 gets NO REPLY AT ALL -- not an exception,
    silence. That is what the real unit did across 0x0000-0x01FF, and firmware
    that quietly depends on a polite error would pass here and fail in the field.
  * 0xFFFF means "sensor not present". 26% of the captured cells are 0xFFFF and
    they are replayed as-is, so the NaN filters get properly exercised.
  * The register space ends at 0x0056. Reads past it get an illegal-address
    exception.

THE --kill-bus FLAG IS THE POINT

It stops answering while leaving the link physically up. That is the failure
this whole design is built around: a bridge that is online, publishing, and
serving frozen values that look exactly like a healthy idle generator. Use it
to watch `bus_healthy` go false, the BUS LED go dark, and Home Assistant fall
back to the EnergyTrak cloud.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial required:  pip install pyserial")

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CAPTURE = REPO / "captures" / "run-2026-08-31.csv"
FIRST_REG, LAST_REG = 0x0000, 0x0056


def crc16(data: bytes) -> bytes:
    """Modbus CRC, low byte first."""
    crc = 0xFFFF
    for ch in data:
        crc ^= ch
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, crc >> 8])


def load_capture(path: pathlib.Path) -> tuple[list[str], list[list[int]]]:
    """Read the CSV into frames of 16-bit words indexed by register number."""
    rows = list(csv.DictReader(path.open()))
    if not rows:
        sys.exit(f"{path} is empty")
    cols = [c for c in rows[0] if c.startswith("0x")]
    addrs = sorted(int(c, 16) for c in cols)
    if addrs != list(range(FIRST_REG, LAST_REG + 1)):
        print(f"  note: capture covers {len(addrs)} registers "
              f"0x{addrs[0]:04X}-0x{addrs[-1]:04X}", file=sys.stderr)
    frames = []
    for row in rows:
        frame = [0xFFFF] * (LAST_REG + 1)
        for c in cols:
            frame[int(c, 16)] = int(row[c], 16)
        frames.append(frame)
    return [r["timestamp"] for r in rows], frames


def open_port(port: str, baud: int, parity: str) -> serial.Serial:
    return serial.Serial(
        port, baud,
        parity={"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
                "O": serial.PARITY_ODD}[parity],
        stopbits=1, bytesize=8, timeout=0.05,
    )


def describe(frame: list[int]) -> str:
    """One-line human summary, so the console shows the cycle progressing."""
    st = frame[0x004F]
    state = {0x6880: "at rest", 0x6080: "cranking/stopping",
             0x6100: "RUNNING"}.get(st & 0xFF00 | (st & 0x00FF), None)
    if state is None:
        state = {0x6880: "at rest", 0x6080: "crank/stop",
                 0x6100: "RUNNING"}.get(st, f"0x{st:04X}")
    volts = frame[0x0001]
    batt = frame[0x0031]
    return (f"status 0x{st:04X} {state:<18} "
            f"L1 {volts / 10:6.1f} V  batt "
            f"{'--' if batt == 0xFFFF else f'{batt / 10:4.1f} V'}")


# --------------------------------------------------------------------- serve
def cmd_serve(a: argparse.Namespace) -> None:
    stamps, frames = load_capture(a.capture)
    ser = open_port(a.port, a.baud, a.parity)
    print(f"GC-1032 simulator on {a.port} {a.baud} 8{a.parity}1, slave id {a.address}")
    print(f"  {len(frames)} frames from {a.capture.name}, {a.speed}x speed"
          + (", looping" if a.loop else "") + (", BUS KILLED" if a.kill_bus else ""))
    print("  FC04 answered; FC03 deliberately ignored (matches the real unit)\n")

    idx, served, ignored, last_advance = 0, 0, 0, time.monotonic()
    buf = b""
    try:
        while True:
            now = time.monotonic()
            if now - last_advance >= 1.0 / a.speed:
                last_advance = now
                idx += 1
                if idx >= len(frames):
                    if not a.loop:
                        print(f"\ncapture exhausted after {served} replies")
                        return
                    idx = 0
                if idx % max(1, int(10 * a.speed)) == 0 or idx < 3:
                    print(f"  [{idx:3d}/{len(frames)}] {describe(frames[idx])}  "
                          f"served={served}")

            chunk = ser.read(256)
            if not chunk:
                continue
            buf += chunk
            # A request is 8 bytes; anything shorter is still arriving.
            while len(buf) >= 8:
                req, buf = buf[:8], buf[8:]
                if len(req) == 8 and req[1] == 0x03 and req[0] == a.address:
                    ignored += 1
                reply = handle_request(req, frames[idx], a.address, a.kill_bus)
                if reply is not None:
                    ser.write(reply)
                    served += 1
    except KeyboardInterrupt:
        print(f"\nstopped. {served} replies sent, {ignored} FC03 requests ignored")


def handle_request(req: bytes, frame: list[int], address: int,
                   kill_bus: bool = False) -> bytes | None:
    """Turn one 8-byte request into the bytes to send back, or None for silence.

    Split out from the serve loop so the protocol can be tested without a
    serial port -- see tools/test_sim.py. Silence and exceptions are as
    meaningful here as replies, so all three are exercised.
    """
    if len(req) != 8 or crc16(req[:6]) != req[6:8]:
        return None                                # framing noise
    slave, func = req[0], req[1]
    start = (req[2] << 8) | req[3]
    count = (req[4] << 8) | req[5]
    if slave != address or kill_bus:
        return None
    if func == 0x03:
        return None                                # real unit says nothing
    if func != 0x04:
        return exception(slave, func, 0x01)        # illegal function
    if count == 0 or start < FIRST_REG or start + count - 1 > LAST_REG:
        return exception(slave, func, 0x02)        # illegal data address
    body = bytearray([slave, func, count * 2])
    for r in range(start, start + count):
        w = frame[r]
        body += bytes([w >> 8, w & 0xFF])
    return bytes(body) + crc16(bytes(body))


def exception(slave: int, func: int, code: int) -> bytes:
    body = bytes([slave, func | 0x80, code])
    return body + crc16(body)


# ---------------------------------------------------------------------- poll
def read_block(ser: serial.Serial, slave: int, start: int, count: int,
               timeout: float = 1.0) -> list[int] | None:
    """One FC04 read, tolerating an adapter that echoes our own transmission."""
    req = bytes([slave, 0x04, start >> 8, start & 0xFF, count >> 8, count & 0xFF])
    req += crc16(req)
    ser.reset_input_buffer()
    ser.write(req)
    want = 5 + count * 2
    deadline = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < deadline:
        buf += ser.read(want)
        # Full-duplex adapters used as 2-wire hand our own bytes straight back.
        if buf.startswith(req):
            buf = buf[len(req):]
        if len(buf) >= want:
            break
    if len(buf) < want or crc16(buf[:want - 2]) != buf[want - 2:want]:
        return None
    n = buf[2]
    return [(buf[3 + i * 2] << 8) | buf[4 + i * 2] for i in range(n // 2)]


def cmd_poll(a: argparse.Namespace) -> None:
    ser = open_port(a.port, a.baud, a.parity)
    print(f"Polling slave {a.address} on {a.port} like an InfoHub would "
          f"({a.block} registers per read)\n")
    try:
        while True:
            frame, ok = {}, True
            for start in range(FIRST_REG, LAST_REG + 1, a.block):
                count = min(a.block, LAST_REG - start + 1)
                got = read_block(ser, a.address, start, count)
                if got is None:
                    ok = False
                    print(f"  no reply for 0x{start:04X}+{count}")
                    break
                for i, w in enumerate(got):
                    frame[start + i] = w
            if ok:
                full = [frame.get(r, 0xFFFF) for r in range(LAST_REG + 1)]
                print(f"  {describe(full)}")
            time.sleep(a.interval)
    except KeyboardInterrupt:
        print("\nstopped")


# -------------------------------------------------------------------- verify
def cmd_verify(a: argparse.Namespace) -> None:
    """Poll a target and diff every register against the capture.

    Point this at the bridge's port B while `serve` drives its port A: it
    proves the whole path, including the inverse-scaling the proxy does to
    reconstruct raw words from float sensor states.
    """
    stamps, frames = load_capture(a.capture)
    ser = open_port(a.port, a.baud, a.parity)
    print(f"Verifying proxy on {a.port} against {a.capture.name}\n")
    checked = mismatch = 0
    try:
        while checked < a.samples:
            frame = {}
            for start in range(FIRST_REG, LAST_REG + 1, a.block):
                count = min(a.block, LAST_REG - start + 1)
                got = read_block(ser, a.address, start, count)
                if got is None:
                    print("  no reply -- is passthrough enabled on the bridge?")
                    time.sleep(1)
                    break
                for i, w in enumerate(got):
                    frame[start + i] = w
            else:
                # Match against whichever captured frame this equals best; the
                # replay and the poll are not in lockstep.
                best = min(frames, key=lambda f: sum(
                    1 for r in frame if f[r] != frame[r]))
                diffs = [(r, best[r], frame[r]) for r in sorted(frame)
                         if best[r] != frame[r]]
                checked += 1
                if diffs:
                    mismatch += 1
                    print(f"  sample {checked}: {len(diffs)} differ")
                    for r, exp, got_ in diffs[:6]:
                        print(f"     0x{r:04X}  capture 0x{exp:04X}  proxy 0x{got_:04X}")
                else:
                    print(f"  sample {checked}: all {len(frame)} registers match")
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    print(f"\n{checked} samples, {mismatch} with differences")
    sys.exit(1 if mismatch else 0)


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--port", required=True)
    common.add_argument("--baud", type=int, default=9600)
    common.add_argument("--parity", default="E", choices=["N", "E", "O"])
    common.add_argument("--address", type=int, default=10)
    common.add_argument("--capture", type=pathlib.Path, default=DEFAULT_CAPTURE)

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", parents=[common], help="act as the generator")
    s.add_argument("--speed", type=float, default=1.0, help="replay rate multiplier")
    s.add_argument("--loop", action="store_true")
    s.add_argument("--kill-bus", action="store_true",
                   help="stay wired but stop answering, to test failover")
    s.set_defaults(func=cmd_serve)

    q = sub.add_parser("poll", parents=[common], help="act as the InfoHub")
    q.add_argument("--interval", type=float, default=2.0)
    q.add_argument("--block", type=int, default=32)
    q.set_defaults(func=cmd_poll)

    v = sub.add_parser("verify", parents=[common], help="diff proxy against capture")
    v.add_argument("--interval", type=float, default=2.0)
    v.add_argument("--block", type=int, default=32)
    v.add_argument("--samples", type=int, default=10)
    v.set_defaults(func=cmd_verify)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()

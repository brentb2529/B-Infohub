#!/usr/bin/env python3
"""Read-only Modbus RTU probe for the Briggs & Stratton GC-1030/1031/1032 controller.

Runs on a Mac with a USB-to-RS485 adapter (FTDI cable: /dev/cu.usbserial-XXXXXXXX).
Answers three questions, in the order you need them:

    scan    What baud rate / parity / slave id does this controller actually use?
    dump    What do the documented registers read right now?
    sweep   Which UNDOCUMENTED registers respond, and which of them move?

THIS TOOL NEVER WRITES. There is no write function anywhere in this file, and that
is deliberate: holding register 0x0000 starts and stops the engine. Probing is not
the time to find out you fat-fingered a function code.

BEFORE YOU PLUG IN
  * Generator selector in OFF.
  * Disconnect the InfoHub from the RS-485 pair first. Modbus RTU allows exactly one
    master. If the InfoHub is still talking, your reads will collide with its polls
    and you will chase phantom CRC errors for an hour.
  * Adapter A -> bus A, B -> bus B. If `scan` finds nothing at any setting, swap A/B
    and run it again before concluding the controller has no Modbus stack.

USAGE
    pip install pyserial
    python3 tools/gc1032_probe.py scan  --port /dev/cu.usbserial-XXXXXXXX
    python3 tools/gc1032_probe.py dump  --port /dev/cu.usbserial-XXXXXXXX --baud 19200 --parity N
    python3 tools/gc1032_probe.py sweep --port /dev/cu.usbserial-XXXXXXXX --baud 19200 --parity N
"""

import argparse
import json
import pathlib
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed.  pip install pyserial")

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTER_MAP = ROOT / "vendor" / "Briggs_Stratton_GC-1032.json"

BAUDS = [9600, 19200, 38400, 57600, 115200, 4800, 2400, 1200]
PARITIES = [("N", serial.PARITY_NONE), ("E", serial.PARITY_EVEN), ("O", serial.PARITY_ODD)]

# genmon documents these as timing out on some controllers and taking the whole
# polling loop down with them. Never probed unless --include-risky is passed.
RISKY = {0x00B5}

FC_READ_INPUT = 0x04
FC_READ_HOLDING = 0x03


def crc16(frame: bytes) -> bytes:
    crc = 0xFFFF
    for byte in frame:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


class Bus:
    def __init__(self, port, baud, parity, slave, timeout=0.35, quiet=False):
        self.slave = slave
        self.quiet = quiet
        self.saw_echo = False
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=parity,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )
        # Let the adapter settle and flush anything the last master left behind.
        time.sleep(0.05)
        self.ser.reset_input_buffer()

    def close(self):
        self.ser.close()

    def read(self, address, count=1, func=FC_READ_INPUT):
        """Return a list of `count` 16-bit words, or None on timeout/CRC/exception.

        LOCAL ECHO. An RS-422 adapter with RXD+ jumpered to T/R+ (see docs/wiring.md)
        hears its own transmission: every request comes straight back before the
        controller's reply does. Reading naively consumes those 8 echoed bytes as if
        they were the response, fails CRC, and reports "no reply" -- while the real
        answer is still sitting in the buffer, unread.

        The symptom is subtle and worth recognising: the scan gets FASTER when it
        starts failing this way, because each transaction returns immediately on the
        echo instead of waiting out its timeout. A sweep that speeds up is a sweep
        that stopped listening.

        So: read one request's worth first, and if it is our own frame, discard it and
        read on. If it is not, those bytes are the start of a genuine response and are
        kept.
        """
        req = bytes([self.slave, func,
                     (address >> 8) & 0xFF, address & 0xFF,
                     (count >> 8) & 0xFF, count & 0xFF])
        req += crc16(req)

        self.ser.reset_input_buffer()
        self.ser.write(req)
        self.ser.flush()

        head = self.ser.read(len(req))
        if head == req:
            self.saw_echo = True
            buf = b""                             # our own transmission; drop it
        else:
            buf = head                            # no echo: real response bytes

        if len(buf) < 3:
            buf += self.ser.read(3 - len(buf))
        if len(buf) < 3:
            return None

        if buf[1] & 0x80:                         # Modbus exception response
            if len(buf) < 5:
                buf += self.ser.read(5 - len(buf))
            if not self.quiet and len(buf) >= 3:
                codes = {1: "illegal function", 2: "illegal address",
                         3: "illegal value", 4: "device failure"}
                print(f"    exception {buf[2]}: {codes.get(buf[2], 'unknown')}")
            return None

        byte_count = buf[2]
        need = 3 + byte_count + 2
        if len(buf) < need:
            buf += self.ser.read(need - len(buf))
        if len(buf) < need:
            return None

        header, payload, crc = buf[:3], buf[3:3 + byte_count], buf[3 + byte_count:need]
        if crc16(header + payload) != crc:
            return None

        return [(payload[i] << 8) | payload[i + 1] for i in range(0, byte_count, 2)]


def cmd_scan(args):
    """Brute-force baud, parity and slave id until a frame CRC-checks.

    Opens the port ONCE and reconfigures it in place. The obvious implementation --
    open/close per combination -- measured 3m28s for the 240-combination sweep on
    macOS, because an FTDI open costs the better part of a second and dominates
    everything else. Reassigning `baudrate`/`parity` on a live pyserial handle brings
    the same sweep under a minute, which is the difference between a usable field tool
    and one you are tempted to skip.
    """
    print("Scanning for the controller. This does not write anything.\n")
    slaves = [args.slave] if args.slave else list(range(1, 11))
    found = []

    try:
        bus = Bus(args.port, BAUDS[0], serial.PARITY_NONE, slaves[0],
                  timeout=0.2, quiet=True)
    except serial.SerialException as exc:
        sys.exit(f"cannot open {args.port}: {exc}")

    try:
        for baud in BAUDS:
            # One frame is 8 bytes out, up to 7 back, 11 bits each with parity. Allow
            # the wire time plus a fixed slice for controller turnaround, so slow baud
            # rates are not judged on a timeout tuned for fast ones.
            wire = (15 * 11) / baud
            for pname, pconst in PARITIES:
                bus.ser.baudrate = baud
                bus.ser.parity = pconst
                bus.ser.timeout = 0.10 + wire
                for slave in slaves:
                    bus.slave = slave
                    words = bus.read(0x0000, 1)
                    if words is not None:
                        print(f"  HIT  baud={baud:<6} parity={pname}  slave={slave}  "
                              f"reg 0x0000 (Protocol Revision) = {words[0]}")
                        found.append((baud, pname, slave))
                    else:
                        print(f"  --   baud={baud:<6} parity={pname}  slave={slave}",
                              end="\r")
    finally:
        bus.close()

    print(" " * 70, end="\r")
    if not found:
        print("\nNothing responded.")
        print("  1. Swap the two data wires (T/R+ and T/R-) and run this again. This is")
        print("     the single most common cause and costs ten seconds to rule out.")
        print("  2. Confirm the InfoHub is physically off the bus -- it will absorb the")
        print("     controller's replies if it is still connected.")
        print("  3. At the controller panel, check Module -> Communication and confirm")
        print("     COMM MODE is set to MODBUS rather than None.")
        print("  4. See the four-combination table in docs/wiring.md if your adapter")
        print("     may need RXD+/RXD- jumpered to the T/R pair.")
        return 1

    print(f"\nFound {len(found)} working combination(s). Use the first one for dump/sweep:")
    baud, pname, slave = found[0]
    print(f"  --baud {baud} --parity {pname} --slave {slave}")
    return 0


def cmd_dump(args):
    """Read every documented register and print it decoded."""
    spec = json.loads(REGISTER_MAP.read_text())["input_registers"]
    bus = Bus(args.port, args.baud, dict(PARITIES)[args.parity], args.slave)

    print(f"{'REG':<8}{'RAW':<12}{'VALUE':<16}NAME")
    print("-" * 72)

    for reg_hex, meta in sorted(spec.items()):
        address = int(reg_hex, 16)
        if address in RISKY and not args.include_risky:
            print(f"0x{address:04X}  {'skipped':<12}{'':<16}{meta['text']}  (known timeout risk)")
            continue

        words = bus.read(address, 2 if meta.get("length") == 4 else 1)
        if words is None:
            print(f"0x{address:04X}  {'NO REPLY':<12}{'':<16}{meta['text']}")
            continue

        raw = (words[0] << 16 | words[1]) if len(words) == 2 else words[0]
        mult = meta.get("multiplier")
        value = f"{raw * mult:.2f}" if isinstance(mult, (int, float)) and mult != 1 else str(raw)
        print(f"0x{address:04X}  0x{raw:<10X}{value:<16}{meta['text']}")
        time.sleep(args.delay)

    bus.close()
    return 0


def cmd_sweep(args):
    """Probe the whole low register space, then re-probe to see what moves.

    This is the part that answers 'the controller must know more than the InfoHub
    reports'. Registers that respond but are absent from genmon's map are exactly
    where undocumented data lives; ones that CHANGE between passes are the
    interesting ones.
    """
    func = FC_READ_HOLDING if getattr(args, "func", "input") == "holding" else FC_READ_INPUT
    # Only the input-register space has a published map; nothing in genmon documents
    # holding registers, so in that mode every responder is by definition unmapped.
    documented = ({int(k, 16) for k in json.loads(REGISTER_MAP.read_text())["input_registers"]}
                  if func == FC_READ_INPUT else set())
    bus = Bus(args.port, args.baud, dict(PARITIES)[args.parity], args.slave, quiet=True)
    if func == FC_READ_HOLDING:
        print("Reading HOLDING registers (FC03). This is a read. Nothing is written.\n")

    print(f"Pass 1: probing 0x{args.start:04X}-0x{args.end:04X} ...")
    first = {}
    for address in range(args.start, args.end + 1):
        if address in RISKY and not args.include_risky:
            continue
        words = bus.read(address, 1, func=func)
        if words is not None:
            first[address] = words[0]
        time.sleep(args.delay)

    print(f"  {len(first)} registers responded.")
    print(f"Waiting {args.interval}s, then re-probing to see which values move ...")
    time.sleep(args.interval)

    print("Pass 2 ...\n")
    second = {}
    for address in sorted(first):
        words = bus.read(address, 1, func=func)
        if words is not None:
            second[address] = words[0]
        time.sleep(args.delay)

    bus.close()

    if getattr(args, "csv", None):
        import csv as _csv
        with open(args.csv, "w", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["address", "pass1", "pass2", "changed", "documented"])
            for address in sorted(first):
                a, b = first[address], second.get(address)
                w.writerow([f"0x{address:04X}", f"0x{a:04X}",
                            "" if b is None else f"0x{b:04X}",
                            int(b is not None and a != b),
                            int(address in documented)])
        print(f"CSV written to {args.csv}\n")

    print(f"{'REG':<9}{'PASS1':<9}{'PASS2':<9}{'CHANGED':<10}DOCUMENTED")
    print("-" * 60)
    undocumented_movers = []
    for address in sorted(first):
        a, b = first[address], second.get(address)
        changed = "yes" if b is not None and a != b else ""
        known = "yes" if address in documented else "NO  <-- unmapped"
        if changed and address not in documented:
            undocumented_movers.append(address)
        print(f"0x{address:04X}   0x{a:04X}   "
              f"{('0x%04X' % b) if b is not None else '  --  '}   {changed:<10}{known}")

    if undocumented_movers:
        print("\nUndocumented registers whose values changed between passes — these are")
        print("the best candidates for data the InfoHub never showed you:")
        for address in undocumented_movers:
            print(f"  0x{address:04X}: 0x{first[address]:04X} -> 0x{second[address]:04X}")
        print("\nCorrelate them against the controller's own display, then add them to")
        print("packages/ as sensors with force_new_range: true.")
    else:
        print("\nNo undocumented register changed. Re-run during an exercise cycle —")
        print("most of the interesting ones only move while the engine is running.")
    return 0


WATCH_FIELDS = [
    (0x004F, "status", None), (0x0039, "rpm", None), (0x0038, "batt", 0.1),
    (0x0004, "genV", 0.1), (0x0007, "genHz", 0.1), (0x0017, "L1A", 0.1),
    (0x001D, "kW", 0.1), (0x001E, "load%", None), (0x0033, "oil", 0.1),
    (0x0034, "tempC", 0.1), (0x0011, "utilV", 0.1),
]


def cmd_watch(args):
    """Poll the whole register block on a timer and log every word to CSV.

    Built for capturing a start/run/stop cycle. The interesting registers on this
    controller are the ones that are dead at rest -- generator voltage, current, kW,
    RPM, oil pressure -- so a single dump while the engine is stopped tells you almost
    nothing about them. This records all 87 registers on every tick so the transition
    can be analysed afterwards rather than watched live and half-remembered.

    Reads the whole 0x0000-0x0056 span in ONE Modbus transaction (87 registers, well
    inside the 125-register limit) so every row is a coherent snapshot. Polling
    register-by-register would smear a single sample across several seconds, which is
    exactly wrong when the thing you are measuring is a transition.

    Still read-only. Starting the engine is your job, at the panel.
    """
    import csv as _csv
    import datetime

    START, END = 0x0000, 0x0056
    count = END - START + 1
    bus = Bus(args.port, args.baud, dict(PARITIES)[args.parity], args.slave,
              timeout=1.0, quiet=True)

    probe = bus.read(START, count)
    if probe is None:
        bus.close()
        sys.exit(f"block read of {count} registers failed. Try --port/--baud/--slave, "
                 f"or fall back to `dump`.")
    print(f"Block read OK: {count} registers in one transaction.", flush=True)

    path = args.csv or "genset-run.csv"
    fh = open(path, "w", newline="")
    w = _csv.writer(fh)
    w.writerow(["timestamp"] + [f"0x{a:04X}" for a in range(START, END + 1)])

    print(f"Logging to {path} every {args.every}s. Ctrl-C to stop.\n")
    print("  time      " + "".join(f"{n:>9}" for _, n, _ in WATCH_FIELDS))

    t0 = time.time()
    try:
        while args.duration <= 0 or (time.time() - t0) < args.duration:
            words = bus.read(START, count)
            now = datetime.datetime.now()
            if words is None:
                print(f"  {now:%H:%M:%S}  (no response)")
            else:
                w.writerow([now.isoformat(timespec="seconds")] +
                           [f"0x{v:04X}" for v in words])
                fh.flush()          # survive a Ctrl-C or an unplugged cable
                cells = []
                for addr, _, mult in WATCH_FIELDS:
                    v = words[addr - START]
                    if addr == 0x004F:
                        cells.append(f"{'0x%04X' % v:>9}")
                    elif v == 0xFFFF:
                        cells.append(f"{'--':>9}")
                    else:
                        cells.append(f"{v * mult:>9.1f}" if mult else f"{v:>9d}")
                print(f"  {now:%H:%M:%S}  " + "".join(cells), flush=True)
            time.sleep(args.every)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        fh.close()
        bus.close()
    print(f"\n{path} written. Re-run `dump` afterwards to compare against the "
          f"at-rest baseline.")
    return 0


def main():
    # Common options live on a PARENT parser rather than the top-level one. With
    # argparse, an option defined on the top-level parser is only accepted BEFORE the
    # subcommand -- `probe.py scan --port X` would fail with "unrecognized arguments"
    # while `probe.py --port X scan` worked. Attaching them to every subparser makes
    # both orderings valid, and the natural one is the one people actually type.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--port", required=True,
                        help="e.g. /dev/cu.usbserial-XXXXXXXX")
    common.add_argument("--slave", type=int, default=None,
                        help="Modbus slave id (default: 1, or scan 1-10 for `scan`)")
    common.add_argument("--baud", type=int, default=19200)
    common.add_argument("--parity", choices=["N", "E", "O"], default="N")
    common.add_argument("--delay", type=float, default=0.03,
                        help="seconds between transactions (default 0.03)")
    common.add_argument("--include-risky", action="store_true",
                        help="also probe 0x00B5, which hangs some controllers")

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", parents=[common], help="find baud/parity/slave id")
    sub.add_parser("dump", parents=[common], help="read all documented registers once")
    watch = sub.add_parser("watch", parents=[common],
                           help="log every register on a timer (for a run cycle)")
    watch.add_argument("--every", type=float, default=2.0, help="seconds per sample")
    watch.add_argument("--duration", type=int, default=0, help="0 = until Ctrl-C")
    watch.add_argument("--csv", metavar="PATH", default=None)
    sweep = sub.add_parser("sweep", parents=[common],
                           help="hunt for undocumented registers")
    sweep.add_argument("--start", type=lambda s: int(s, 0), default=0x0000)
    sweep.add_argument("--end", type=lambda s: int(s, 0), default=0x00FF)
    sweep.add_argument("--func", choices=["input", "holding"], default="input",
                       help="input = FC04 telemetry (default); holding = FC03, a "
                            "SEPARATE address space that may hold configuration such "
                            "as exercise schedule and setpoints. Reading is safe -- "
                            "FC03 never writes. 0x0000 is the command register, so "
                            "read it, never write it.")
    sweep.add_argument("--interval", type=int, default=30,
                       help="seconds between the two passes (default 30)")
    sweep.add_argument("--csv", metavar="PATH",
                       help="also write results as CSV. Strongly recommended: the "
                            "text table below is column-aligned, and when the CHANGED "
                            "column is blank the DOCUMENTED flag shifts into its "
                            "place -- parsing it by whitespace silently mislabels "
                            "every unchanged row as changed.")

    args = parser.parse_args()
    # `scan` sweeps slave ids 1-10 unless one was named; everything else needs a
    # concrete id and defaults to 1.
    if args.cmd != "scan" and args.slave is None:
        args.slave = 1
    return {"scan": cmd_scan, "dump": cmd_dump, "sweep": cmd_sweep,
            "watch": cmd_watch}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

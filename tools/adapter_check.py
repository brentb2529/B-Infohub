#!/usr/bin/env python3
"""Bench-check the USB-RS485 adapter with nothing connected to the generator.

Answers three things you would otherwise only find out standing at the generator:

  1. Does the port open and accept every baud/parity combination `scan` will try?
  2. Does the adapter LOOP BACK its own transmission?  This is the decisive test for
     whether RXD+/RXD- need external jumpers, and it works with the bus disconnected.
  3. Does a floating, unconnected bus produce noise that could fake a response?

THE LOOPBACK RESULT IS THE USEFUL ONE.

A half-duplex RS-485 adapter has its receiver sitting on the same T/R+ / T/R- pair as
its driver. Transmit into an open line and the receiver still hears it, so you get your
own frame back. A full-duplex RS-422 part has a separate receiver on RXD+ / RXD-, hears
nothing from its own driver, and must have RXD+ jumpered to T/R+ and RXD- to T/R-
before it can work as 2-wire RS-485.

    ECHO SEEN     -> receiver is on the T/R pair. Leave RXD+/RXD- unconnected.
    NO ECHO       -> jumper RXD+ to T/R+ and RXD- to T/R-, then run this again.
                     If the echo appears, keep the jumpers for the real hookup.

That turns a four-combination guessing game at the generator into one known-good
wiring configuration before you leave the desk.

    python3 tools/adapter_check.py --port /dev/cu.usbserial-XXXXXXXX
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed.  pip install pyserial")

BAUDS = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
PARITIES = [("N", serial.PARITY_NONE), ("E", serial.PARITY_EVEN), ("O", serial.PARITY_ODD)]


def crc16(frame: bytes) -> bytes:
    crc = 0xFFFF
    for byte in frame:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=19200)
    ap.add_argument("--jumpered", action="store_true",
                    help="RXD+ is tied to T/R+ and RXD- to T/R- right now. The echo "
                         "result means the OPPOSITE thing depending on this, so say so.")
    args = ap.parse_args()

    print(f"Adapter check on {args.port}\n")

    # --- 1. Port opens, and every setting `scan` will try is accepted ------------
    print("[1] Port and line settings")
    bad = []
    for baud in BAUDS:
        for pname, pconst in PARITIES:
            try:
                s = serial.Serial(args.port, baudrate=baud, bytesize=8,
                                  parity=pconst, stopbits=1, timeout=0.1)
                s.close()
            except Exception as exc:
                bad.append(f"{baud}/{pname}: {exc}")
    if bad:
        print(f"    {len(bad)} combination(s) REJECTED:")
        for b in bad[:5]:
            print(f"      {b}")
    else:
        print(f"    OK - all {len(BAUDS) * len(PARITIES)} baud/parity combinations open cleanly")

    # --- 2. Idle-line noise -----------------------------------------------------
    print("\n[2] Idle line (2s, transmitting nothing)")
    s = serial.Serial(args.port, baudrate=args.baud, bytesize=8,
                      parity=serial.PARITY_NONE, stopbits=1, timeout=2.0)
    time.sleep(0.1)
    s.reset_input_buffer()
    noise = s.read(64)
    if noise:
        print(f"    {len(noise)} stray byte(s): {noise.hex(' ')}")
        print("    A floating, unbiased pair picks up noise. Harmless here - the probe")
        print("    CRC-checks every frame - but it is why an unterminated bus can look")
        print("    'almost working'.")
    else:
        print("    Quiet. No stray bytes on the floating pair.")

    # --- 3. Loopback ------------------------------------------------------------
    print("\n[3] Loopback test  <- this is the one that matters")
    req = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x01])
    req += crc16(req)
    print(f"    transmitting: {req.hex(' ')}")

    s.timeout = 0.5
    s.reset_input_buffer()
    s.write(req)
    s.flush()
    got = s.read(len(req))
    s.close()

    print(f"    received:     {got.hex(' ') if got else '(nothing)'}")
    print()

    if got == req:
        if args.jumpered:
            print("    ECHO SEEN, byte for byte -- WITH the RXD jumpers fitted.")
            print()
            print("    CONCLUSION: this is FULL-DUPLEX RS-422 silicon. Its receiver sits")
            print("    on RXD+ / RXD-, not on the T/R pair. Without the jumpers it")
            print("    transmits correctly and hears nothing -- which is exactly what the")
            print("    no-jumper run showed.")
            print()
            print("    KEEP THE JUMPERS. Final wiring:")
            print("      T/R+ and RXD+ tied together -> one harness data wire  (bus A)")
            print("      T/R- and RXD- tied together -> the other data wire    (bus B)")
            print("      GND                         -> harness black")
            print()
            print("    Remaining unknown at the generator is only which data wire is A.")
            print("    If scan finds nothing, swap the two joined pairs and run it once more.")
        else:
            print("    ECHO SEEN, byte for byte -- with NO jumpers fitted.")
            print()
            print("    CONCLUSION: the receiver is already on the T/R+ / T/R- pair. This is")
            print("    a half-duplex RS-485 adapter and needs no jumpers.")
            print()
            print("    Wire it as: T/R+ -> one data wire, T/R- -> the other, GND -> harness")
            print("    ground. Leave RXD+ and RXD- unconnected and insulated.")
        print()
        print("    Either way, this also proves the port, framing and CRC path all work:")
        print("    8 bytes out, the same 8 bytes back, byte for byte.")
        return 0

    if got:
        print("    Partial or garbled echo. The receiver hears the driver but something")
        print("    is off. Re-run once before drawing conclusions.")
        return 1

    print("    NO ECHO.")
    if args.jumpered:
        print("    With jumpers fitted and still no echo, the adapter mutes its receiver")
        print("    while the driver is active. That is normal and harmless, but it means")
        print("    the loopback test cannot settle the RXD question -- fall back to the")
        print("    four-combination table in docs/wiring.md.")
    else:
        print("    Either the receiver sits on a separate RXD+ / RXD- pair (full-duplex")
        print("    RS-422 silicon), or it is muted while the driver is active.")
        print()
        print("    NEXT: jumper RXD+ to T/R+ and RXD- to T/R-, then run again WITH")
        print("    --jumpered. If the echo appears, keep those jumpers for the real hookup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Bring-up harness for the B-Infohub bridge.

    python3 tools/harness.py preflight        # no hardware needed
    python3 tools/harness.py boot --port ...  # flash, then assert on boot log

Checks the things that are easy to assume and expensive to get wrong: that the
partition table really has two OTA slots, that the image fits the SMALLER of
them (OTA writes into the inactive slot, so that is the real limit), that
rollback is compiled in, and that the device says the right things on boot.
"""
from __future__ import annotations
import argparse, pathlib, re, struct, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / ".esphome" / "build" / "b-infohub"
ESPHOME = ROOT / ".venv" / "bin" / "esphome"
YAML = "genset-gc1032.yaml"

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else '** FAIL':8} {name}" + (f"   {detail}" if detail else ""))
    return bool(cond)


def partitions():
    p = BUILD / "build" / "partition_table" / "partition-table.bin"
    if not p.exists():
        return []
    d, out = p.read_bytes(), []
    for i in range(0, len(d), 32):
        e = d[i:i + 32]
        if e[:2] != b"\xaa\x50":
            break
        typ, sub = e[2], e[3]
        off, size = struct.unpack("<II", e[4:12])
        out.append((e[12:28].rstrip(b"\0").decode(), typ, sub, off, size))
    return out


def cmd_preflight(a):
    print("=== preflight (no hardware) ===\n")
    r = subprocess.run([str(ESPHOME), "config", YAML], cwd=ROOT,
                       capture_output=True, text=True)
    check("config validates", r.returncode == 0, r.stderr.strip()[-200:] if r.returncode else "")

    parts = partitions()
    check("partition table present", bool(parts), f"{len(parts)} entries")
    apps = [p for p in parts if p[1] == 0]
    check("two OTA app slots", len(apps) == 2,
          " ".join(f"{n}@{o:#x}={s:#x}" for n, _, _, o, s in apps))
    if parts:
        end = max(o + s for _, _, _, o, s in parts)
        check("table fills 4 MB exactly", end == 0x400000, f"ends {end:#x}")
        nvs = [p for p in parts if p[0] == "nvs"]
        check("nvs present and sane", bool(nvs) and 0x4000 <= nvs[0][4] <= 0x20000,
              f"{nvs[0][4]:#x}" if nvs else "missing")

    bin_ = BUILD / "build" / "b-infohub.bin"
    if bin_.exists() and apps:
        smallest = min(s for *_, s in apps)
        size = bin_.stat().st_size
        # The inactive slot is where an OTA lands, so headroom is measured
        # against the smaller slot, not against total flash.
        check("image fits the smaller OTA slot", size < smallest,
              f"{size:,} / {smallest:,} = {size/smallest*100:.1f}%")
        check("at least 15% OTA headroom", size < smallest * 0.85,
              f"{(smallest-size):,} B free")

    sdk = BUILD / "build" / "config" / "sdkconfig.h"
    if sdk.exists():
        t = sdk.read_text()
        check("bootloader rollback compiled in",
              "#define CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 1" in t)

    main = BUILD / "src" / "main.cpp"
    if main.exists():
        t = main.read_text()
        for name, pat in (("safe_mode present", "safe_mode"),
                          ("BLE improv present", "esp32_improv"),
                          ("serial improv present", "improv_serial"),
                          ("captive portal present", "captive_portal"),
                          ("modbus server (passthrough)", "modbus_server")):
            check(name, pat in t)
        # Two UARTs is necessary but not sufficient -- the point is that one
        # bus is a CLIENT (master, to the generator) and the other a SERVER
        # (slave, to the InfoHub). Two clients would be the two-master fault
        # the whole design exists to avoid, and it would compile happily.
        n_uart = t.count("uart::IDFUARTComponent()")
        check("two UARTs instantiated", n_uart == 2, f"{n_uart} found")
        check("port A is a Modbus CLIENT (master to generator)",
              "modbus::ModbusClientHub" in t)
        check("port B is a Modbus SERVER (slave to InfoHub)",
              "modbus::ModbusServerHub" in t)
        check("exactly one master on the genset bus",
              t.count("new(rs485_bus) modbus::ModbusClientHub") <= 1)
        check("no wifi network compiled in (onboarding path)",
              "add_sta" not in t or t.count("add_sta") == 0)
        check("AP ssid compiled in", "Setup" in t)
    return 0


# Markers the firmware MUST emit on a healthy first boot. Each is paired with
# what its absence would mean, because "the log looked fine" is not a test.
# Assert on what the firmware ACTUALLY prints at INFO on a real boot. The first
# version of this list was written from expectation rather than observation and
# "failed" six times on a device that was working perfectly -- ROM messages
# predate the log attaching, safe_mode and modbus_server say nothing on a good
# boot, and bus health is an entity state rather than a log line. A test that
# cries wolf is worse than no test.
BOOT_MARKERS = [
    ("setup() completed",         r"setup\(\) finished successfully"),
    ("running from an OTA slot",  r"Boot complete on partition (app0|app1)"),
    ("our project + version",     r"Project bbensten\.b_infohub version"),
    ("BLE stack is up",           r"BT_BTM|BTU_TASK|esp32_ble"),
    ("port A polling the genset", r"waiting for response from 10|Modbus device=10"),
    ("bus correctly seen as DEAD",r"Modbus device=10 set offline"),
    ("API waiting for a client",  r"api set Warning flag|waiting for client"),
]


def capture_logs(port_or_host, seconds, extra=()):
    """Run `esphome logs` for a while and return everything it printed."""
    cmd = [str(ESPHOME), "logs", YAML, "--device", port_or_host, *extra]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    out, deadline = [], time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            out.append(line)
            print("   |", line.rstrip()[:130])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return "".join(out)


def cmd_boot(a):
    print(f"=== flashing over USB: {a.port} ===")
    print("    (first flash MUST be USB -- partitions.csv moves the table, and")
    print("     a partition table cannot relocate the image it is running)\n")
    # Stream logs from the SAME invocation that flashes. Doing it as two steps
    # loses the first second of boot -- which is exactly where Wi-Fi, the AP and
    # Improv announce themselves -- and makes a healthy device look silent.
    print(f"\n=== flashing and capturing {a.seconds}s from cold boot ===")
    proc = subprocess.Popen([str(ESPHOME), "run", YAML, "--device", a.port],
                            cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    out, deadline, uploaded = [], None, False
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            out.append(line)
            if "Successfully uploaded" in line:
                uploaded = True
                deadline = time.monotonic() + a.seconds
                print("   -- upload done, watching cold boot --")
            if uploaded and not line.startswith("Writing at"):
                print("   |", line.rstrip()[:130])
            if deadline and time.monotonic() > deadline:
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    log = "".join(out)
    if not check("flash completed", uploaded):
        return 1
    print("\n=== boot assertions ===")
    for name, pat in BOOT_MARKERS:
        check(name, re.search(pat, log, re.I) is not None)
    check("no panic / guru meditation",
          not re.search(r"Guru Meditation|abort\(\)|assert failed|Backtrace:", log))
    check("no boot loop", len(re.findall(r"Boot complete on partition", log)) <= 1,
          f"{len(re.findall(r'Boot complete on partition', log))} boots seen")
    m = re.search(r"Boot complete on partition (app\d)", log)
    if m:
        print(f"\n  running from {m.group(1)}; the OTHER slot is where an OTA lands")
    return 0


def cmd_ota(a):
    """Push a build over the network and prove the safety machinery works."""
    print(f"=== OTA to {a.host} ===\n")
    # `esphome logs` never exits on its own, so it has to be read with a
    # deadline rather than subprocess.run(timeout=), which kills and raises
    # instead of handing back what it already captured.
    #
    # The running slot is not re-announced after boot, so asking the device
    # over the API is the only way to learn it without rebooting -- which
    # would defeat the purpose. Read the Boot Partition sensor instead.
    print("  reading current slot from the device...")
    before = capture_logs(a.host, 12)
    m = re.search(r"Boot Partition.*?(app\d)", before) or \
        re.search(r"Boot complete on partition (app\d)", before)
    start_slot = m.group(1) if m else None
    print(f"  currently running from: {start_slot or 'unknown (will infer after OTA)'}")

    r = subprocess.run([str(ESPHOME), "run", YAML, "--device", a.host,
                        "--no-logs"], cwd=ROOT, text=True)
    if not check("OTA upload accepted", r.returncode == 0):
        return 1

    print("\n=== waiting for the device to come back ===")
    log = capture_logs(a.host, a.seconds)
    check("device rebooted and reconnected",
          bool(re.search(r"Boot complete on partition", log)))
    m2 = re.search(r"Boot complete on partition (app\d)", log)
    if m2 and start_slot:
        # This is THE assertion that proves A/B OTA rather than in-place
        # overwrite: a real OTA must land in the other slot.
        check("image landed in the OTHER OTA slot", m2.group(1) != start_slot,
              f"{start_slot} -> {m2.group(1)}")
    check("no panic after OTA",
          not re.search(r"Guru Meditation|assert failed|Backtrace:", log))
    check("did not fall into safe mode",
          not re.search(r"SAFE MODE ENTERED", log))
    print("\n  Rollback note: the new image boots PENDING-VERIFY and is only marked")
    print("  valid after safe_mode's boot_is_good_after (3 min). Check the")
    print("  'Boot Partition' entity -- it should read 'app1 (valid)' after that.")
    return 0


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("preflight").set_defaults(func=cmd_preflight)
    b = s.add_parser("boot"); b.add_argument("--port", required=True)
    b.add_argument("--seconds", type=int, default=45)
    b.set_defaults(func=cmd_boot)
    o = s.add_parser("ota"); o.add_argument("--host", default="b-infohub.local")
    o.add_argument("--seconds", type=int, default=90)
    o.set_defaults(func=cmd_ota)
    a = p.parse_args()
    rc = a.func(a)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  failed: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else (rc or 0))


if __name__ == "__main__":
    main()

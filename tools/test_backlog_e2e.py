#!/usr/bin/env python3
"""End-to-end simulation of store-and-forward, against real hardware.

    python3 tools/test_backlog_e2e.py --host 192.168.1.52

Injects synthetic alarm events and snapshots into flash, drains both rings
over the native API exactly as ha-energytrak does, and checks the records come
back intact and in order. Proves the whole path without a generator, a fault,
or an outage to wait for.
"""
import argparse, asyncio, pathlib, re, sys
from aioesphomeapi import APIClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = re.search(r'^api_encryption_key:\s*"(.*)"',
                (ROOT / "secrets.yaml").read_text(), re.M).group(1)
INJECT = 10
ALARM_IDX = 5

PASS, FAIL = [], []
def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else '** FAIL':8} {name}" + (f"   {extra}" if extra else ""))


async def drain(cli, svc, state, batch_key, ack_name, parse, rounds=60):
    out, n = [], 0
    while n < rounds:
        raw = state.get(batch_key)
        if not raw or raw == "-":
            break
        recs = parse(str(raw))
        if not recs:
            break
        out += recs
        last = max(r[0] for r in recs)
        prev = raw
        await cli.execute_service(svc[ack_name], {"seq": last})
        n += 1
        for _ in range(24):
            await asyncio.sleep(0.25)
            if state.get(batch_key) != prev:
                break
    return out


async def main(host):
    cli = APIClient(host, 6053, password=None, noise_psk=KEY, client_info="e2e")
    await cli.connect(login=True)
    ents, svcs = await cli.list_entities_services()
    keys = {}
    for g in ents:
        for e in (g if isinstance(g, list) else [g]):
            oid, k = getattr(e, "object_id", None), getattr(e, "key", None)
            if oid is not None:
                keys[k] = oid
    svc = {s.name: s for s in svcs}
    state = {}
    cli.subscribe_states(lambda s: state.__setitem__(
        keys.get(getattr(s, "key", None)), getattr(s, "state", None))
        if keys.get(getattr(s, "key", None)) else None)
    await asyncio.sleep(3)

    print("=== preconditions ===")
    for a in ("backlog_ack", "backlog_replay_all", "snapshot_ack",
              "snapshot_replay_all", "backlog_inject_test"):
        check(f"action {a}", a in svc)
    check("snapshot_batch entity", "snapshot_batch" in keys.values())

    print(f"\n=== injecting {INJECT} synthetic event+snapshot pairs ===")
    await cli.execute_service(svc["backlog_inject_test"],
                              {"count": INJECT, "alarm_index": ALARM_IDX})
    await asyncio.sleep(3)
    await cli.execute_service(svc["backlog_replay_all"], {})
    await cli.execute_service(svc["snapshot_replay_all"], {})
    await asyncio.sleep(3)

    print("\n=== draining the EVENT ring ===")
    evs = await drain(cli, svc, state, "backlog_batch", "backlog_ack",
                      lambda r: [tuple(int(x) for x in c.split(":"))
                                 for c in r.split("|") if c.count(":") == 3])
    seqs = [e[0] for e in evs]
    check("events drained", len(evs) >= INJECT, f"{len(evs)} records")
    check("sequence strictly increasing", seqs == sorted(set(seqs)), f"{seqs[:6]}...")
    inj = [e for e in evs if e[3] == ALARM_IDX and e[2] in (1, 2)]
    check("injected alarms present", len(inj) >= INJECT, f"{len(inj)} for index {ALARM_IDX}")
    check("alternating set/clear", all(inj[i][2] != inj[i+1][2] for i in range(len(inj)-1)))
    check("event ring emptied", state.get("backlog_batch") == "-")

    print("\n=== draining the SNAPSHOT ring ===")
    def psnap(raw):
        out = []
        for c in raw.split("|"):
            head, *rest = c.split(",")
            if ":" not in head or len(rest) != 12:
                continue
            seq, ts = (int(x) for x in head.split(":"))
            out.append((seq, ts, [int(x) for x in rest]))
        return out
    sns = await drain(cli, svc, state, "snapshot_batch", "snapshot_ack", psnap)
    check("snapshots drained", len(sns) >= INJECT, f"{len(sns)} records")
    check("each carries 12 slots", all(len(s[2]) == 12 for s in sns))
    check("all timestamped", all(s[1] > 1_700_000_000 for s in sns),
          f"first ts {sns[0][1] if sns else 'n/a'}")
    if len(sns) >= 2:
        # injector writes 1000 + n*10 + i, so slot i rises by 10 per record
        d = [sns[i+1][2][0] - sns[i][2][0] for i in range(len(sns)-1)]
        check("payload survived the round trip", all(x == 10 for x in d[-INJECT+1:]),
              f"slot0 deltas {d[-5:]}")
    check("snapshot ring emptied", state.get("snapshot_batch") == "-")

    await cli.disconnect()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  failed: " + ", ".join(FAIL))
    return 1 if FAIL else 0

a = argparse.ArgumentParser(); a.add_argument("--host", default="192.168.1.52")
sys.exit(asyncio.run(main(a.parse_args().host)))

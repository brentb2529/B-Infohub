#!/usr/bin/env python3
"""Exercise the backlog drain protocol exactly as ha-energytrak will.

    python3 tools/test_drain.py --host 192.168.1.52

Connects over the native API, reads the batch entity, acknowledges it, and
checks the cursor advances and eventually empties. This is the protocol test
that the Home Assistant side depends on; getting it wrong there would look
like "history is missing" rather than "the ack never landed".
"""
import argparse, asyncio, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from aioesphomeapi import APIClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sec = (ROOT / "secrets.yaml").read_text()
KEY = re.search(r'^api_encryption_key:\s*"(.*)"', sec, re.M).group(1)

TYPES = {1: "ALARM SET", 2: "ALARM CLEAR", 3: "BOOT", 4: "BUS LOST",
         5: "BUS BACK", 6: "LINK LOST", 7: "LINK BACK"}


async def main(host: str) -> int:
    cli = APIClient(host, 6053, password=None, noise_psk=KEY, client_info="drain-test")
    await cli.connect(login=True)
    entities, services = await cli.list_entities_services()

    keys, names = {}, {}
    for group in entities:
        for e in group if isinstance(group, list) else [group]:
            oid, k = getattr(e, "object_id", None), getattr(e, "key", None)
            if oid is not None:
                keys[k] = oid
                names[oid] = getattr(e, "name", oid)
    svc = {s.name: s for s in services}
    print(f"connected: {len(keys)} entities, actions: {sorted(svc)}\n")

    ok = True
    def check(label, cond, extra=""):
        nonlocal ok
        print(f"  {'PASS' if cond else '** FAIL':8} {label}" + (f"   {extra}" if extra else ""))
        ok &= bool(cond)

    check("backlog_batch entity exists", "backlog_batch" in names)
    check("backlog_ack action exists", "backlog_ack" in svc)
    check("backlog_replay_all action exists", "backlog_replay_all" in svc)

    state: dict[str, object] = {}
    done = asyncio.Event()
    def on_state(s):
        oid = keys.get(getattr(s, "key", None))
        if oid:
            state[oid] = getattr(s, "state", None)
            if oid == "backlog_batch":
                done.set()
    cli.subscribe_states(on_state)
    await asyncio.sleep(4)

    pending = state.get("event_log_pending")
    print(f"\n  pending before drain: {pending}")
    print(f"  batch: {state.get('backlog_batch')!r}\n")

    # Force a full replay so there is definitely something to drain.
    if "backlog_replay_all" in svc:
        await cli.execute_service(svc["backlog_replay_all"], {})
        await asyncio.sleep(3)
        print(f"  after replay_all, batch: {state.get('backlog_batch')!r}\n")

    total, rounds = 0, 0
    while rounds < 20:
        raw = state.get("backlog_batch")
        if not raw or raw == "-":     # explicit empty marker
            break
        recs = [c.split(":") for c in str(raw).split("|") if c.count(":") == 3]
        if not recs:
            break
        for seq, ts, typ, idx in recs:
            print(f"     seq {seq:<4} ts={ts:<12} {TYPES.get(int(typ), typ)} idx={idx}")
        total += len(recs)
        last = max(int(r[0]) for r in recs)
        before_cursor = state.get("event_log_cursor")
        await cli.execute_service(svc["backlog_ack"], {"seq": last})
        await asyncio.sleep(1.5)
        print(f"       ack(seq={last}) -> cursor {before_cursor} -> "
              f"{state.get('event_log_cursor')}, batch={state.get('backlog_batch')!r}")
        rounds += 1
        prev = raw
        for _ in range(20):
            await asyncio.sleep(0.25)
            if state.get("backlog_batch") != prev:
                break

    check("drained at least one record", total > 0, f"{total} records in {rounds} rounds")
    check("cursor emptied", state.get("backlog_batch") in ("-", "", None),
          f"final batch {state.get('backlog_batch')!r}")
    check("pending returned to 0", state.get("event_log_pending") in (0, 0.0, None),
          f"pending={state.get('event_log_pending')}")

    await cli.disconnect()
    print(f"\n{'ALL PASS' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


a = argparse.ArgumentParser()
a.add_argument("--host", default="192.168.1.52")
n = a.parse_args()
sys.exit(asyncio.run(main(n.host)))

#!/usr/bin/env python3
"""Generate the MQTT snapshot publisher and the JSON contract.

    python3 contract/gen.py

Reads the RESOLVED ESPHome config (so it sees exactly the entities that will be
built, ids and all) plus contract/telemetry.py, and writes:

    packages/local-telemetry.yaml   -- consumed by genset-gc1032.yaml
    contract/telemetry.json         -- consumed by ha-energytrak

Never edit either output by hand; edit telemetry.py and re-run.
"""
import json, subprocess, sys, pathlib, textwrap
import yaml
from esphome.helpers import sanitize, snake_case

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "contract"))
import telemetry as T

class _L(yaml.SafeLoader): pass
_L.add_multi_constructor('!', lambda l, s, n: f"<{s}>")

# Every file this generator writes into packages/. All of them are parsed by
# `esphome config`, which this generator has to run to see the entity list --
# so a bad generation in ANY of them wedges the generator that would fix it.
# They are all neutralised before resolving, not just the first one, because
# the first time this was written it only covered local-telemetry.yaml and the
# next bad output deadlocked exactly as predicted.
OUT_PKGS = [ROOT / "packages/local-telemetry.yaml",
            ROOT / "packages/passthrough.yaml",
            ROOT / "packages/alarm-log.yaml",
            ROOT / "packages/snapshot-log.yaml"]

def resolved():
    for f in OUT_PKGS:
        f.write_text("# placeholder -- contract/gen.py is regenerating this\n")
    out = subprocess.run([str(ROOT/".venv/bin/esphome"), "config", "genset-gc1032.yaml"],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode: sys.exit("esphome config failed:\n" + out.stderr[-2000:])
    body = out.stdout[out.stdout.index("substitutions:"):]
    return yaml.load(body, _L)

cfg = resolved()
ents = {}
for dom in ("sensor", "binary_sensor", "text_sensor"):
    entries = []
    for e in cfg.get(dom) or []:
        if not isinstance(e, dict):
            continue
        if e.get("id") and e.get("name"):
            entries.append(e)
            continue
        # SOME PLATFORMS NEST THEIR ENTITIES ONE LEVEL DOWN.
        #
        # `debug:` is the one that matters here: its free / block / loop_time
        # sensors are sub-keys of a SINGLE sensor entry whose top level has no
        # id and no name. The old scan tested the outer dict, found neither,
        # and dropped all three silently -- so heap telemetry could be added to
        # the firmware, compiled in, and still never appear in the contract,
        # with nothing anywhere saying why.
        for value in e.values():
            if isinstance(value, dict) and value.get("id") and value.get("name"):
                entries.append(value)

    for e in entries:
        if True:
            # object_id is what the native API and MQTT actually expose, and it
            # is derived from the NAME, not from the C++ id. They usually match
            # because the ids were generated from the names -- but not always:
            # "Status Register" has id alarm_reg_4f, and "Utility L1-L2 Voltage"
            # sanitises to utility_l1-l2_voltage, with a hyphen. Computed here
            # with ESPHome's own helpers rather than guessed.
            ents[e["id"]] = dict(dom=dom, name=e["name"],
                                 off=bool(e.get("disabled_by_default")),
                                 object_id=sanitize(snake_case(e["name"])),
                                 unit=e.get("unit_of_measurement"),
                                 diag=e.get("entity_category") == "diagnostic")

KIND = {"sensor": "num", "binary_sensor": "bin", "text_sensor": "txt"}
shared_ids = {lid for _, lid, _ in T.SHARED}
missing = [f"{k} -> {lid}" for k, lid, _ in T.SHARED if lid not in ents]
if missing: sys.exit("SHARED refers to ids that do not exist:\n  " + "\n  ".join(missing))

local_only = [(i, m) for i, m in ents.items()
              if (not m["diag"] or i in T.INCLUDE_DIAGNOSTICS)
              and i not in shared_ids and i not in T.EXCLUDE_LOCAL_ONLY]
# Alarms worth logging: exclude the ones that are ASSERTED ON A HEALTHY UNIT.
#
# On this hardware an alarm nibble of 0 means both "fault asserted" and "input
# not populated", so 15 conditions read as faulted on a demonstrably fine
# generator. tools/gen_alarms.py already identifies them from
# vendor/baseline-2026-08-31.json and marks them disabled_by_default.
#
# The event log was ignoring that and recording all 43, so the flash ring filled
# with phantom faults -- Gen L3 phase low AND high at once, on a single-phase
# unit. A real shutdown would have arrived buried in a dozen of them, which is
# worse than not logging at all.
alarms = [(i, ents[i]["name"]) for i in ents
          if ents[i]["dom"] == "binary_sensor" and i not in T.NOT_A_FAULT
          and not ents[i]["diag"] and not ents[i]["off"]]

# ---------------------------------------------------------------- lambda ---
L = []
L.append("// GENERATED by contract/gen.py -- do not edit here.")
L.append("int _ac = 0; std::string _al;")
for i, name in sorted(alarms):
    L.append(f'if (id({i}).state) {{ _ac++; if (!_al.empty()) _al += ", "; _al += "{name}"; }}')
L.append("")
L.append('root["telemetry_source"] = "local";')
L.append('root["schema"] = 1;')
L.append("root[\"bus_healthy\"] = id(bus_healthy).state;")
L.append("root[\"bus_age_s\"] = id(bus_age_seconds).state;")
L.append("root[\"uptime_s\"] = (uint32_t)(millis()/1000);")
L.append("")

def oid(lid):
    return ents[lid]["object_id"]

def emit(key, lid, kind):
    if kind == "num":
        return f'if (!std::isnan(id({lid}).state)) root["{key}"] = id({lid}).state;'
    if kind == "bin":
        return f'root["{key}"] = id({lid}).state;'
    return f'if (!id({lid}).state.empty()) root["{key}"] = id({lid}).state;'

L.append("// --- keys ha-energytrak already knows (same names as the cloud path) ---")
for key, lid, kind in T.SHARED:
    L.append(emit(key, lid, kind))
L.append("")
L.append("// --- derived ---")
for key, expr in T.DERIVED.items():
    if expr == "__ALARM_COUNT__":  L.append(f'root["{key}"] = _ac;')
    elif expr == "__ALARM_LIST__": L.append(f'root["{key}"] = _al.empty() ? "None" : _al.c_str();')
    else:                          L.append(f'root["{key}"] = {expr};')
L.append("")
L.append(f"// --- local-only superset: {len(local_only)} keys the cloud never had ---")
# Published under object_id, not the C++ id. The id is an internal handle --
# "Status Register" carries id alarm_reg_4f -- and using it would surface
# sensor.alarm_reg_4f in Home Assistant instead of sensor.status_register.
for lid, m in sorted(local_only):
    L.append(emit(oid(lid), lid, KIND[m["dom"]]))

lam = "\n".join("                  " + x for x in L)

pkg = f'''# GENERATED by contract/gen.py -- DO NOT EDIT. Edit contract/telemetry.py.
#
# One retained JSON snapshot of everything the bridge can see, for the
# ha-energytrak custom component to consume as its LOCAL source.
#
# Published to ${{mqtt_prefix}}/{T.MQTT_TOPIC} every {T.PUBLISH_INTERVAL}, retained, so a
# restarting Home Assistant has current state immediately rather than after a
# poll interval. Availability comes from the birth/will on ${{mqtt_prefix}}/status
# already configured in packages/mqtt.yaml.
#
# The integration must check `bus_healthy` before trusting the values: a bridge
# whose RS-485 has died is still online and still retaining this document, and
# its stale readings look exactly like an idle generator.

interval:
  - interval: {T.PUBLISH_INTERVAL}
    then:
      - if:
          condition:
            lambda: 'return id(feat_mqtt).state;'
          then:
            - mqtt.publish_json:
                topic: ${{mqtt_prefix}}/{T.MQTT_TOPIC}
                retain: true
                payload: |-
{lam}
'''
(ROOT/"packages/local-telemetry.yaml").write_text(pkg)

# ---------------------------------------------------------- passthrough ---
# The InfoHub proxy. Serves the SAME register map back out of port B from the
# values we already read on port A, so the InfoHub keeps working while we are
# the only master on the generator's bus.
mb = [e for e in cfg.get("sensor", []) or []
      if isinstance(e, dict) and e.get("platform") == "modbus_controller"]
mb.sort(key=lambda e: e["address"])

def scale_of(e):
    for f in e.get("filters") or []:
        if isinstance(f, dict) and "multiply" in f:
            return f["multiply"]
    return None

WORDS = {"U_DWORD": ("uint32_t", "llroundf", "0xFFFFFFFF"),
         "S_DWORD": ("int32_t", "llroundf", "0")}
regs = []
for e in mb:
    vt = e.get("value_type", "U_WORD")
    ctype, rnd, sentinel = WORDS.get(vt, ("uint16_t", "lroundf", "0xFFFF"))
    m = scale_of(e)
    expr = f"v / {m}f" if m else "v"
    if vt in WORDS:
        # 32-bit counters cannot survive a float32 state -- served from the
        # exact word captured in gc1032-power.yaml instead.
        body = (f"          // {e.get('name', e['id'])} -- exact 32-bit capture\n"
                f"          if (!id(feat_passthrough).state) return {{}};\n"
                f"          return ({ctype}) id(raw_dword_{e['address']:04x});")
    else:
        body = (f"          // {e.get('name', e['id'])}\n"
                f"          if (!id(feat_passthrough).state) return {{}};\n"
                f"          float v = id({e['id']}).state;\n"
                f"          if (std::isnan(v)) return ({ctype}) {sentinel};\n"
                f"          return ({ctype}) {rnd}({expr});")
    regs.append(f"""      - address: 0x{e['address']:04X}
        value_type: {vt}
        read_lambda: |-
{body}""")

pt = f'''# GENERATED by contract/gen.py -- DO NOT EDIT.
#
# InfoHub passthrough: a CACHING MODBUS PROXY on port B.
#
# WHY THIS IS NEEDED AT ALL
#
# Modbus RTU permits exactly one master. The InfoHub is a master. So is this
# bridge. Wire both to the generator's RS-485 pair and they transmit over each
# other: corrupt frames in both directions, and an InfoHub reporting comm
# faults to your dealer.
#
# The board solves it in hardware -- two transceivers, U3 (IO17/16/4) facing
# the generator and U4 (IO22/23/21) facing the InfoHub -- and this file solves
# it in firmware. We are the sole master on the generator bus. The InfoHub is
# no longer on that bus at all; it talks to US, and we answer as a SLAVE at the
# same address, from the values we just read. It cannot tell the difference.
#
# WHAT IS SERVED
#
# All {len(regs)} registers across 0x0000-0x{mb[-1]['address']:04X}, reconstructed from the
# scaled sensor values by inverting each filter's multiply. Reconstruction
# rather than a second raw read of the same addresses: a duplicate read would
# double the traffic on a 9600 baud bus that the field notes already warn
# against saturating. lroundf absorbs the float round trip.
#
# A register we have never read, or one the controller reported as 0xFFFF
# ("sensor not present"), is served as 0xFFFF -- exactly what the InfoHub would
# have seen from the controller itself.
#
# WHAT IS NOT SERVED: WRITES.
#
# The InfoHub can no longer command the generator through this bridge. Remote
# start/stop from the Briggs app will stop working; monitoring and cloud
# reporting continue. This is deliberate. Proxying writes would mean this
# bridge cranking an engine on behalf of a remote request it cannot
# authenticate, using the control path that was explicitly removed from this
# build. If you need remote start, wire the InfoHub directly and run this
# bridge read-only on its own port -- you cannot have both on one pair.

uart:
  - id: rs485_uart_b
    tx_pin: ${{uart_b_tx_pin}}
    rx_pin: ${{uart_b_rx_pin}}
    baud_rate: ${{modbus_baud}}
    parity: ${{modbus_parity}}
    stop_bits: 1
    data_bits: 8

modbus:
  - id: rs485_bus_b
    uart_id: rs485_uart_b
    role: server
    flow_control_pin: ${{flow_control_b_pin}}

modbus_server:
  - id: infohub_proxy
    modbus_id: rs485_bus_b
    address: ${{modbus_address}}
    # Answer, rather than fault, for anything in range we do not model. An
    # exception reply teaches the InfoHub the device is broken; 0xFFFF is the
    # controller's own "not present" value and is what it already handles.
    courtesy_response:
      enabled: true
      register_last_address: 0x{mb[-1]['address']:04X}
      register_value: 0xFFFF
    registers:
{chr(10).join(regs)}
'''
(ROOT / "packages/passthrough.yaml").write_text(pt)
print(f"passthrough: {len(regs)} registers 0x0000-0x{mb[-1]['address']:04X}")

# ------------------------------------------------------------- backlog ----
# One interval that diffs the whole alarm bitmask, rather than an on_state
# bolted onto each of the 43 alarm sensors. Centralised so regenerating the
# data packages cannot silently drop the hook, and so the index numbering
# below has exactly one definition.
alarm_ids = [i for i, _ in alarms]
lines = []
lines.append("// GENERATED by contract/gen.py -- do not edit here.")
lines.append("static bool prev[%d];" % len(alarm_ids))
lines.append("static bool primed = false;")
lines.append("bool cur[%d];" % len(alarm_ids))
for n, i in enumerate(alarm_ids):
    lines.append(f"cur[{n}] = id({i}).state;")
# Only track transitions while the bus is actually delivering data.
#
# Without this the watcher primes from NaN sensors -- everything reads clear --
# and then logs a storm the instant real data lands. That is exactly what the
# first field log showed: Common Shutdown, Electrical Trip and Generator Failed
# to Start all setting and clearing in one burst, none of them real.
#
# Dropping `primed` when the bus goes away means a reconnection re-primes
# silently instead of replaying the whole alarm state as fresh transitions.
lines.insert(3, "if (!id(bus_healthy).state) { primed = false; return; }")
lines.append("if (!primed) { for (int k=0;k<%d;k++) prev[k]=cur[k]; primed=true; return; }" % len(alarm_ids))
lines.append("for (int k = 0; k < %d; k++) {" % len(alarm_ids))
lines.append("  if (cur[k] == prev[k]) continue;")
lines.append("  backlog::global_backlog->record(")
lines.append("      cur[k] ? backlog::EVENT_ALARM_SET : backlog::EVENT_ALARM_CLEAR, k);")
lines.append("  prev[k] = cur[k];")
lines.append("}")
body = chr(10).join("          " + x for x in lines)

names = ",\n".join(f'  "{ents[i]["name"]}"' for i in alarm_ids)
pkg = f'''# GENERATED by contract/gen.py -- DO NOT EDIT. Edit contract/telemetry.py.
#
# Writes every alarm transition to the flash event log, so a fault that
# asserts and clears while Home Assistant is unreachable still leaves a record.
# That is the whole point: a numeric sensor loses resolution during an outage,
# but a one-shot alarm loses the only evidence it ever happened.
#
# Polled as a single bitmask diff rather than {len(alarm_ids)} separate on_state hooks --
# one place to reason about, and regenerating the data packages cannot quietly
# remove it.
#
# The FIRST pass only primes the previous-state array. Without that, every
# asserted alarm would be written as a fresh transition on each boot and the
# log would fill with events that did not happen.

interval:
  - interval: 1s
    then:
      - lambda: |-
{body}
'''
(ROOT / "packages/alarm-log.yaml").write_text(pkg)
(ROOT / "contract/alarm_index.json").write_text(json.dumps(
    {"index": [ents[i]["name"] for i in alarm_ids]}, indent=1) + chr(10))
print(f"alarm-log: {len(alarm_ids)} alarms watched")

# ------------------------------------------------------- snapshot ring ----
sl = []
sl.append("// GENERATED by contract/gen.py -- do not edit here.")
sl.append("uint16_t v[%d];" % len(T.SNAPSHOT_SLOTS))
for n, (eid, key, scale) in enumerate(T.SNAPSHOT_SLOTS):
    if eid not in ents:
        sys.exit(f"SNAPSHOT_SLOTS refers to a missing entity: {eid}")
    sl.append(f"{{ float x = id({eid}).state;")
    sl.append(f"  v[{n}] = std::isnan(x) ? 0xFFFF : (uint16_t) std::min(65534.0f, "
              f"std::max(0.0f, x * {scale}.0f)); }}   // {key}")
sl.append("id(event_log)->record_sample(v);")
sbody = chr(10).join("                " + x for x in sl)

slot_doc = chr(10).join(
    f"#   {n:>2}  {key:<22} from {eid:<24} x{scale}"
    for n, (eid, key, scale) in enumerate(T.SNAPSHOT_SLOTS))

snap = f'''# GENERATED by contract/gen.py -- DO NOT EDIT. Edit contract/telemetry.py.
#
# Buffers a reduced snapshot to flash WHILE NOBODY IS LISTENING, so an outage
# leaves history rather than a hole.
#
# ONLY WHILE DISCONNECTED. Writing continuously would burn the ring on data
# nobody ever lost, and flash endurance is a budget worth spending on the case
# it exists for.
#
# 60 s, not the 10 s poll rate. The destination is hourly statistics, which
# cannot represent finer detail anyway, and 60 s turns a 192 KB ring into
# ninety hours of cover instead of fifteen.
#
# SLOTS (raw uint16, 0xFFFF = no reading):
{slot_doc}

interval:
  - interval: 60s
    then:
      - if:
          condition:
            lambda: |-
              return id(event_log)->ready() && id(bus_healthy).state &&
                     (api::global_api_server == nullptr ||
                      !api::global_api_server->is_connected());
          then:
            - lambda: |-
{sbody}

text_sensor:
  - platform: template
    name: "Snapshot Batch"
    id: snapshot_batch
    icon: mdi:tray-arrow-down
    entity_category: diagnostic
    update_interval: never
    lambda: 'return id(event_log)->sample_batch(6);'

sensor:
  - platform: template
    name: "Snapshot Pending"
    id: snapshot_pending
    icon: mdi:counter
    accuracy_decimals: 0
    entity_category: diagnostic
    update_interval: 30s
    lambda: 'return id(event_log)->ready() ? (float) id(event_log)->sample_pending() : NAN;'

api:
  actions:
    - action: snapshot_ack
      variables:
        seq: int
      then:
        - lambda: 'id(event_log)->ack_sample((uint32_t) seq);'
        - component.update: snapshot_batch
        - component.update: snapshot_pending
    - action: snapshot_replay_all
      then:
        - lambda: 'id(event_log)->reset_sample_cursor();'
        - component.update: snapshot_batch

    # TEST ONLY. Writes synthetic records so the whole chain -- flash, drain,
    # Home Assistant statistics -- can be exercised without a generator and
    # without waiting for a real fault. Reachable only over the authenticated
    # API; it cannot be triggered from the web UI or by the device itself.
    - action: backlog_inject_test
      variables:
        count: int
        alarm_index: int
      then:
        - lambda: |-
            uint16_t v[{len(T.SNAPSHOT_SLOTS)}];
            for (int n = 0; n < count; n++) {{
              id(event_log)->record(n % 2 ? backlog::EVENT_ALARM_CLEAR
                                          : backlog::EVENT_ALARM_SET,
                                    (uint8_t) alarm_index);
              for (int i = 0; i < {len(T.SNAPSHOT_SLOTS)}; i++)
                v[i] = (uint16_t) (1000 + n * 10 + i);
              id(event_log)->record_sample(v);
            }}
            ESP_LOGW("backlog", "TEST: injected %d synthetic event+sample pairs", count);
'''
(ROOT / "packages/snapshot-log.yaml").write_text(snap)
print(f"snapshot-log: {len(T.SNAPSHOT_SLOTS)} slots, sampled only while disconnected")

contract = {
    "schema": 1,
    "topic": T.MQTT_TOPIC,
    "publish_interval_s": int(T.PUBLISH_INTERVAL.rstrip("s")),
    "shared_keys": {k: {"object_id": ents[lid]["object_id"], "kind": kind}
                    for k, lid, kind in T.SHARED},
    "derived": T.DERIVED_SPEC,
    # Keyed by object_id: that is the name the transports actually use and the
    # one that becomes the Home Assistant entity id. esphome_id is kept only so
    # a reader can trace a key back to the YAML that produced it.
    "local_only_keys": {m["object_id"]: {"object_id": m["object_id"],
                                         "esphome_id": lid, "unit": m["unit"],
                                         "name": m["name"], "kind": KIND[m["dom"]]}
                        for lid, m in sorted(local_only)},
    "alarm_keys": sorted(ents[i]["object_id"] for i, _ in alarms),
    "snapshot_slots": [{"key": k, "scale": sc, "esphome_id": e}
                       for e, k, sc in T.SNAPSHOT_SLOTS],
    # How a consumer decides whether to trust any of the above. Both transports
    # need this; the native API has no last-will, and MQTT's last-will only
    # catches a dead BRIDGE, never a dead BUS behind a live bridge.
    "liveness": {
        "mqtt_availability_topic_suffix": "status",
        "mqtt_health_key": "bus_healthy",
        "mqtt_age_key": "bus_age_s",
        "api_health_object_id": "bus_healthy",
        "api_age_object_id": "bus_age",
        "api_status_object_id": "bus_status",
    },
    "device": {"project_name": "bbensten.b_infohub", "zeroconf": "_esphomelib._tcp.local."},
}
(ROOT/"contract/telemetry.json").write_text(json.dumps(contract, indent=2) + "\n")

print(f"shared keys      {len(T.SHARED)} mapped + {len(T.DERIVED)} derived")
print(f"local-only keys  {len(local_only)}")
print(f"alarms counted   {len(alarms)}")
print(f"total published  {len(T.SHARED)+len(T.DERIVED)+len(local_only)}")
print("wrote packages/local-telemetry.yaml, contract/telemetry.json")

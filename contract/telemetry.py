"""Single source of truth for the B-Infohub telemetry contract.

Two things consume this file:

  * ``gen.py`` writes ``packages/local-telemetry.yaml`` -- the ESPHome MQTT
    snapshot publisher on the bridge.
  * ``gen.py`` writes ``contract/telemetry.json`` -- read by the ha-energytrak
    custom component so the integration and the firmware cannot drift.

WHY A SNAPSHOT AND NOT PER-ENTITY TOPICS

ESPHome already publishes every entity to its own MQTT topic, so a local source
could be built by subscribing to 150 of them. It is the wrong shape. The
integration's coordinator is built around ``normalize.py`` returning ONE flat
telemetry dict per poll, and the cloud path is atomic -- a whole site document
at once. Feeding the same coordinator from 150 independently-arriving retained
topics means it can never say "this is the state at time T", only "this is the
most recent value of each field, which arrived at 150 different times".

So the bridge publishes one retained JSON document to ``<prefix>/telemetry``.
Retained means a restarting Home Assistant gets current state immediately
instead of waiting a poll interval.

THE THREE-STATE LIVENESS PROBLEM

Failover is not "is the bridge online". There are three states, and only the
first should use local data:

    bridge online,  bus healthy  -> use local  (the superset)
    bridge online,  bus DEAD     -> use cloud  <- the subtle one
    bridge offline               -> use cloud

The middle case is why ``bus_healthy`` and ``bus_age_s`` are in the payload. A
bridge whose RS-485 has failed is still online, still publishing, and still
retaining its last good document. Without an explicit health flag the
integration would happily serve values frozen at the moment the bus died, and
they would look perfectly plausible -- a generator that is simply idle. The
MQTT last-will only catches the third case.

NAMING RULE

Keys in SHARED reuse ha-energytrak's existing names EXACTLY, so the integration
can merge the two sources without a translation table and existing dashboards
keep working when the source flips. Keys in LOCAL_ONLY are data the cloud has
never had; the integration needs a new EntityDescription for each.
"""

# --- keys ha-energytrak already produces from the cloud -------------------
# (energytrak key, esphome entity id, kind)   kind: num | bin | txt
SHARED = [
    ("battery_voltage",         "battery_voltage",        "num"),
    ("engine_speed",            "engine_speed",           "num"),
    ("engine_hours",            "engine_run_time",        "num"),
    ("generator_frequency",     "generator_l1_frequency", "num"),
    ("grid_frequency",          "utility_l1_frequency",   "num"),
    # LINE-TO-LINE, not line-to-neutral. A shared key must be drop-in
    # compatible with the cloud's representation of the SAME name, and
    # EnergyTrak's grid_voltage is the 240V L1-L2 figure (measured: cloud 237,
    # bridge L1-L2 238, bridge L1-N 120).
    #
    # Mapping it to utility_l1_voltage halved the value the instant the bridge
    # took over. Entity ids are preserved across a source switch precisely so
    # that dashboards and alert rules need no changes -- and a rule thresholded
    # near 240V would then have read 120 and fired "grid voltage low" forever,
    # on a healthy utility feed, with nothing in Home Assistant saying the
    # meaning of the number had changed underneath it.
    #
    # The per-leg readings are not lost: utility_l1_voltage and
    # utility_l2_voltage remain available as local-only entities.
    ("grid_voltage",            "utility_l1_l2_voltage",  "num"),
    ("output_voltage_l1n",      "generator_l1_voltage",   "num"),
    ("output_voltage_l2n",      "generator_l2_voltage",   "num"),
    ("load_l1_current",         "generator_l1_current",   "num"),
    ("load_l2_current",         "generator_l2_current",   "num"),
    ("load_l1_power",           "l1_power",               "num"),
    ("load_l2_power",           "l2_power",               "num"),
    ("load_power",              "total_power",            "num"),
    ("load_l1_apparent_power",  "l1_apparent_power",      "num"),
    ("load_l2_apparent_power",  "l2_apparent_power",      "num"),
    ("load_apparent_power",     "total_apparent_power",   "num"),
    ("load_l1_reactive_power",  "l1_reactive_power",      "num"),
    ("load_l2_reactive_power",  "l2_reactive_power",      "num"),
    ("load_reactive_power",     "total_reactive_power",   "num"),
    ("power_factor",            "average_power_factor",   "num"),
    ("power_factor_l1",         "l1_power_factor",        "num"),
    ("power_factor_l2",         "l2_power_factor",        "num"),
    ("operation_mode",          "switch_status",          "txt"),
    ("ignition_status",         "engine_state",           "txt"),
    ("fault_condition",         "common_shutdown",        "bin"),
    # The cloud carries these two but reports them poorly -- the equipment
    # snapshot can be months stale. The bridge watches 0x004F transition in
    # real time, so local is strictly better here.
    ("last_exercise_at",             "last_exercise_at",             "txt"),
    ("last_exercise_duration_seconds","last_exercise_duration_seconds","num"),
]

# Keys the cloud has but that must be DERIVED here rather than read straight
# from one register. Each value is a C++ expression returning the JSON value.
DERIVED = {
    # The controller reports a utility FAILURE; energytrak reports PRESENCE.
    "grid_present":      "!id(utility_power_failure).state",
    "grid_status":       '(id(utility_power_failure).state ? "Lost" : "Present")',
    # energytrak counts what is asserted right now. Cheap here: we already have
    # every alarm as a bool, so count them rather than re-decode the registers.
    "active_alarm_count": "__ALARM_COUNT__",
    "active_alarms":      "__ALARM_LIST__",
    "has_malfunction":    "id(common_shutdown).state",
    "monitor_online":     "true",   # if this document arrived, the bridge is up
}

# Anything with an id in the ESPHome config that is not SHARED and not
# diagnostic becomes a LOCAL_ONLY key, named after its entity id. That is the
# superset: L3 phases, line-to-line voltages, oil pressure, coolant, fuel,
# cumulative energy, and ~55 discrete alarms the cloud never exposed.
EXCLUDE_LOCAL_ONLY = {
    # raw scratch values -- the decoded versions are published instead
    "clock_minutes_raw", "clock_hours_raw", "date_monthday_raw", "date_year_raw",
    "oil_pressure_psi",        # duplicate of oil_pressure_bar in other units
    "run_time_hours",          # duplicate of engine_run_time
}

# Alarms, for active_alarm_count / active_alarms. Filled by gen.py from the
# binary_sensor list minus the ones that are states rather than faults.
NOT_A_FAULT = {
    "engine_running", "engine_starting", "utility_power_failure",
    "dg_phase_rotation", "mains_phase_rotation",
    "auxiliary_input_a", "auxiliary_input_b", "auxiliary_input_c",
    "auxiliary_input_d", "auxiliary_input_e", "auxiliary_input_f",
    "auxiliary_input_g", "auxiliary_input_h", "auxiliary_input_i",
}

# The native-API path cannot use the C++ lambdas above -- it sees raw entities
# only. Each derived key is therefore also declared as a transport-neutral spec
# that the Home Assistant integration implements in Python. Kept beside the C++
# so a change to one is an obvious prompt to change the other.
DERIVED_SPEC = {
    "grid_present":       {"op": "not",       "src": "utility_power_failure"},
    "grid_status":        {"op": "map_bool",  "src": "utility_power_failure",
                           "true": "Lost", "false": "Present"},
    "active_alarm_count": {"op": "count_true", "src": "@alarms"},
    "active_alarms":      {"op": "join_true",  "src": "@alarms", "empty": "None"},
    "has_malfunction":    {"op": "copy",      "src": "common_shutdown"},
    "monitor_online":     {"op": "const",     "value": True},
}

# ---------------------------------------------------------------------------
# SNAPSHOT SLOTS -- what gets buffered to flash while Home Assistant is away.
#
# Not all 87 registers. A raw snapshot is 186 bytes, which buys under 3 hours
# of ring and costs 372 characters per record to drag back over a text entity.
# Twelve values at 36 bytes buys NINETY hours and drains in a fraction of the
# round trips, and hourly statistics cannot represent more resolution than
# this anyway.
#
# (esphome entity id, wire key, scale)  -- value is stored as
#     uint16(round(state * scale)),  0xFFFF meaning "no reading"
# so the scale has to keep every plausible reading under 65534.
SNAPSHOT_SLOTS = [
    ("battery_voltage",        "battery_voltage",      100),   # 13.1 V -> 1310
    ("engine_speed",           "engine_speed",           1),   # rpm
    ("generator_l1_voltage",   "output_voltage_l1n",    10),
    ("generator_l1_current",   "load_l1_current",       10),
    ("total_power",            "load_power",            10),   # kW
    ("total_apparent_power",   "load_apparent_power",   10),
    ("utility_l1_l2_voltage",  "grid_voltage",          10),
    ("generator_l1_frequency", "generator_frequency",  100),
    ("oil_pressure_bar",       "oil_pressure",         100),
    ("coolant_temperature",    "coolant_temperature",   10),
    ("fuel_level",             "fuel_level",            10),
    ("percentage_load",        "percentage_load",       10),
]

MQTT_TOPIC = "telemetry"     # under ${mqtt_prefix}
PUBLISH_INTERVAL = "10s"

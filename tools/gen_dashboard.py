#!/usr/bin/env python3
"""Generate grafana/dashboards/b-infohub-genset.json.

Written as a generator rather than hand-authored JSON for the same reason
gen_alarms.py is: the metric names have to match ha/packages/b_infohub_push.yaml
exactly, and a typo in a 900-line hand-edited dashboard shows up as an empty panel
with no error anywhere.

Targets the SAME Grafana Cloud Prometheus datasource and the same $site_id variable
as B-Panels/grafana/dashboards/generator-dashboard.json, but queries the `genset_*`
series this bridge produces rather than `generator_*` from the cloud poller. Both
dashboards can run side by side during cutover.

    python3 tools/gen_dashboard.py
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DST = ROOT / "grafana" / "dashboards" / "b-infohub-genset.json"

DS = {"type": "prometheus", "uid": "${datasource}"}
SEL = '{site_id=~"$site_id"}'

_id = iter(range(1, 500))
panels = []
row_y = [0]


def _target(expr, legend=None):
    t = {"datasource": DS, "editorMode": "code", "expr": expr,
         "range": True, "refId": "A"}
    if legend:
        t["legendFormat"] = legend
    return t


def row(title):
    panels.append({"id": next(_id), "type": "row", "title": title, "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": row_y[0]}, "panels": []})
    row_y[0] += 1


def panel(kind, title, expr, w, x, h=5, unit="none", decimals=None,
          mappings=None, thresholds=None, legend=None, minv=None, maxv=None):
    defaults = {"unit": unit, "color": {"mode": "thresholds"},
                "mappings": mappings or [],
                "thresholds": {"mode": "absolute",
                               "steps": thresholds or [{"color": "text", "value": None}]}}
    if decimals is not None:
        defaults["decimals"] = decimals
    if minv is not None:
        defaults["min"] = minv
    if maxv is not None:
        defaults["max"] = maxv

    p = {"id": next(_id), "type": kind, "title": title, "datasource": DS,
         "gridPos": {"h": h, "w": w, "x": x, "y": row_y[0]},
         "fieldConfig": {"defaults": defaults, "overrides": []},
         "targets": [_target(expr, legend)]}

    if kind == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                          "values": False},
                        "textMode": "auto", "colorMode": "value",
                        "graphMode": "area", "justifyMode": "auto"}
    elif kind == "gauge":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                          "values": False}, "showThresholdLabels": False,
                        "showThresholdMarkers": True}
    elif kind == "timeseries":
        defaults["custom"] = {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 8,
                              "showPoints": "never", "spanNulls": False}
        defaults["color"] = {"mode": "palette-classic"}
        p["options"] = {"legend": {"displayMode": "list", "placement": "bottom",
                                   "showLegend": True, "calcs": []},
                        "tooltip": {"mode": "multi", "sort": "none"}}
    return panels.append(p) or p


def maps(pairs, default="Unknown"):
    """Grafana value mappings from {numeric code: (text, colour)}."""
    return [{"type": "value",
             "options": {str(k): {"text": v[0], "color": v[1], "index": i}
                         for i, (k, v) in enumerate(pairs.items())}},
            {"type": "special", "options": {"match": "null",
                                            "result": {"text": default,
                                                       "color": "text", "index": 99}}}]


OK_BAD = maps({0: ("No", "green"), 1: ("YES", "red")})
RUN = maps({0: ("Stopped", "text"), 1: ("RUNNING", "green")})

# --------------------------------------------------------------------------
row("Live Status")
panel("stat", "Engine State", f"genset_engine_state_code{SEL}", 4, 0,
      mappings=maps({0: ("Stopped", "text"), 1: ("Starting", "yellow"),
                     2: ("Running", "green"), 3: ("Stopped w/ Fault", "red")}))
panel("stat", "Power Status", f"genset_power_status_code{SEL}", 4, 4,
      mappings=maps({0: ("Off - Ready", "green"), 1: ("Initialized", "blue"),
                     2: ("Generating", "green"), 3: ("Exercising", "yellow"),
                     4: ("Cool Down", "yellow"), 5: ("Shutdown Pending", "orange")}))
panel("stat", "Mode", f"genset_switch_status_code{SEL}", 4, 8,
      mappings=maps({0: ("MANUAL", "orange"), 1: ("Automatic", "green"),
                     2: ("Exercise", "yellow"), 3: ("Initialized", "blue")}))
panel("stat", "Utility Power", f"genset_utility_failure{SEL}", 4, 12,
      mappings=maps({0: ("Healthy", "green"), 1: ("FAILED", "red")}))
panel("stat", "Active Alarms", f"genset_active_alarm_count{SEL}", 4, 16, decimals=0,
      thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}])
panel("stat", "Bridge", f"genset_bridge_connected{SEL}", 4, 20,
      mappings=maps({0: ("OFFLINE", "red"), 1: ("Online", "green")}))
row_y[0] += 5

# --------------------------------------------------------------------------
row("Generator Output")
panel("timeseries", "Output Voltage (L1-L2)", f"genset_gen_output_voltage{SEL}",
      8, 0, h=7, unit="volt", decimals=1, legend="L1-L2")
panel("timeseries", "Load", f"genset_load_power_kw{SEL}", 8, 8, h=7,
      unit="kwatt", decimals=2, legend="kW")
panel("gauge", "Load %", f"genset_load_percent{SEL}", 4, 16, h=7, unit="percent",
      decimals=0, minv=0, maxv=100,
      thresholds=[{"color": "green", "value": None},
                  {"color": "yellow", "value": 70}, {"color": "red", "value": 90}])
panel("stat", "Power Factor", f"genset_power_factor{SEL}", 4, 20, h=7, decimals=2)
row_y[0] += 7

panel("timeseries", "Line Currents", f"genset_gen_l1_current{SEL}", 8, 0, h=6,
      unit="amp", decimals=1, legend="L1")
panels[-1]["targets"].append({**_target(f"genset_gen_l2_current{SEL}", "L2"),
                              "refId": "B"})
panel("timeseries", "Generator Frequency", f"genset_gen_frequency{SEL}", 8, 8, h=6,
      unit="hertz", decimals=2, legend="Gen Hz")
panel("stat", "Cumulative Energy", f"genset_cumulative_kwh{SEL}", 8, 16, h=6,
      unit="kwatth", decimals=1)
row_y[0] += 6

# --------------------------------------------------------------------------
row("Utility (Mains)")
panel("timeseries", "Utility Voltage (L1-L2)", f"genset_utility_voltage{SEL}",
      12, 0, h=6, unit="volt", decimals=1, legend="Utility L1-L2")
panel("timeseries", "Utility Frequency", f"genset_utility_frequency{SEL}", 12, 12,
      h=6, unit="hertz", decimals=2, legend="Utility Hz")
row_y[0] += 6

# --------------------------------------------------------------------------
row("Engine & Battery")
panel("timeseries", "Battery Voltage", f"genset_battery_voltage{SEL}", 10, 0, h=7,
      unit="volt", decimals=2, legend="Battery")
# 12.2 V resting is the practical "this battery will not crank in January" line.
panel("gauge", "Battery", f"genset_battery_voltage{SEL}", 4, 10, h=7, unit="volt",
      decimals=2, minv=10, maxv=15,
      thresholds=[{"color": "red", "value": None},
                  {"color": "yellow", "value": 12.2},
                  {"color": "green", "value": 12.6},
                  {"color": "yellow", "value": 14.8}])
panel("timeseries", "Engine Speed", f"genset_engine_speed{SEL}", 10, 14, h=7,
      unit="rotrpm", decimals=0, legend="RPM")
row_y[0] += 7

panel("timeseries", "Oil Pressure", f"genset_oil_pressure_psi{SEL}", 12, 0, h=6,
      unit="pressurepsi", decimals=1, legend="Oil PSI")
panel("timeseries", "Coolant Temperature", f"genset_coolant_temp_c{SEL}", 12, 12,
      h=6, unit="celsius", decimals=1, legend="Coolant")
row_y[0] += 6

# --------------------------------------------------------------------------
row("Lifetime Counters")
panel("stat", "Engine Hours", f"genset_engine_hours_total{SEL}", 6, 0, unit="h",
      decimals=1)
panel("stat", "Total Starts", f"genset_starts_total{SEL}", 6, 6, decimals=0)
panel("stat", "Total Trips", f"genset_trips_total{SEL}", 6, 12, decimals=0,
      thresholds=[{"color": "green", "value": None}, {"color": "yellow", "value": 1}])
panel("stat", "Faults Decoded", f"genset_decoded_alarm_total{SEL}", 6, 18, decimals=0)
row_y[0] += 5

# --------------------------------------------------------------------------
row("Bridge Health")
panel("timeseries", "Wi-Fi Signal", f"genset_wifi_rssi{SEL}", 8, 0, h=6, unit="dBm",
      decimals=0, legend="RSSI")
panel("timeseries", "Bridge Temperature", f"genset_bridge_temp_c{SEL}", 8, 8, h=6,
      unit="celsius", decimals=1, legend="ESP32")
panel("stat", "Bridge Uptime", f"genset_bridge_uptime{SEL}", 8, 16, h=6, unit="s",
      decimals=0)

# --------------------------------------------------------------------------
dashboard = {
    "uid": "b-infohub-genset",
    "title": "Genset (B-Infohub local bridge)",
    "description": ("Local Modbus RTU telemetry from the Briggs & Stratton GC-1032, "
                    "via the ESP32/RS-485 bridge. Replaces the InfoHub. "
                    "Generated by tools/gen_dashboard.py -- do not hand-edit."),
    "tags": ["generator", "b-infohub", "genset"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"},
    "editable": True,
    "templating": {"list": [
        {"name": "datasource", "type": "datasource", "query": "prometheus",
         "current": {}, "hide": 0, "label": "Datasource"},
        {"name": "site_id", "type": "query", "datasource": DS,
         "definition": "label_values(genset_battery_voltage, site_id)",
         "query": {"query": "label_values(genset_battery_voltage, site_id)",
                   "refId": "StandardVariableQuery"},
         "includeAll": True, "multi": True, "current": {}, "hide": 0,
         "label": "Site", "refresh": 1, "sort": 1},
    ]},
    "panels": panels,
}

DST.parent.mkdir(parents=True, exist_ok=True)
DST.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"wrote {DST.relative_to(ROOT)}: {len([p for p in panels if p['type'] != 'row'])} "
      f"panels in {len([p for p in panels if p['type'] == 'row'])} rows")

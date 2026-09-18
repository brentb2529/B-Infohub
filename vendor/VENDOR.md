# Vendored sources

## Briggs_Stratton_GC-1032.json

Source: https://github.com/jgyates/genmon — `data/controller/Briggs_Stratton_GC-1032.json`
Fetched: 2026-08-31

This is genmon's custom-controller definition for the Briggs & Stratton GC-1032
(and the GC-1031 / GC-1030-series controllers that share its Modbus stack). It is the
source of truth for every register address, scaling multiplier, bitfield mask and alarm
condition used in `packages/`.

It is vendored (not submoduled) so the register map this firmware was built against is
pinned and diffable. `tools/gen_alarms.py` regenerates `packages/gc1032-alarms.yaml`
directly from this file — do not hand-edit that package.

# Full-Scene Controlled Spawn Hold (Design)

**Date:** 2026-07-10
**Status:** Approved direction (user: plan then execute)
**Parent:** A2+B2 fluid recipe; G1 D4A_018

## Problem

G1 controlled spawn (`d4_promotion_spawn_layout`) PASSes on isolated fluid-spike scenes, but FAILs on the full colleague USD with step-0 spill already present.

## Root cause (locked)

1. **Spawn radius inflated:** `build_tabletop_region_config` uses `bbox_half + 0.005`, while FluidSafeWrapper inner radius uses mesh AABB half **without** +0.005 → particles authored into wall contact.
2. **Spawn Z anchored to table top:** G1 has `table_z == cup bottom`; full scene uses table top (~3 cm below beaker floor) → large G1 widths depenetrate hard.
3. **Secondary:** wrapper `bottom_thickness` hard-coded 0.012 vs G1 promotion 0.008; classifier `wall_thickness=0.01` vs wrapper 0.026.

## Goal

Full colleague scene + D4A_018 + controlled spawn:
- **Gate A:** N=1024 seed0 → `PASS_SOURCE_HOLD`, step0 spill=0 / below=0
- **Gate B:** N=4096 seed0 → `PASS_SOURCE_HOLD` (after A)

## Non-goals

- S3 pour; claiming recipe = G1 promotion matrix; official Visual A; 真实水

## Approach

Add `build_full_scene_controlled_spawn_frame(...)` that derives spawn frame from **beaker2 mesh AABB** (and optionally wrapper local params):
- `source_radius = mesh_xy_half` (no +0.005)
- `table_z = mesh_min_z` (cup floor world Z), not table top
- `wall_thickness = 0.026` for classification when wrapper overlay is on
- `bottom_thickness = 0.008` to match G1 promotion ≤4096
- Keep `bottom_overlap = g1_wrapper_bottom_overlap(N)`

Wire into video runner controlled-spawn path and recipe export. Keep `build_tabletop_region_config` +0.005 for **non-spawn** region diagnostics if needed, but spawn must use the mesh frame.

## Claim boundary

Allowed: `full_scene_controlled_spawn_hold_passed=true` with linked manifest.
Blocked: `full_scene_controlled_spawn_equals_g1_isolated_promotion_matrix` without matching seed×count matrix.

## Honest runtime finding (2026-07-10)

- **Gate A (1024) + Gate B (4096):** both `PASS_SOURCE_HOLD` on the full colleague USD (`fluid_spike_full_scene_controlled_spawn_hold_20260710.json`).
- Fixes that mattered beyond mesh-frame radius/Z: weekly-grade bottom seal (`bottom_thickness=0.012`, `bottom_overlap=0.018`), width cap (`≤0.0006` / `≤0.00045` @4096), `interior_inset≥0.008` @4096, and `spawn_prefer_interior=true` (G1 default prefers the outer rim).
- Wrapper Bottom remains mesh-AABB anchored when `visual_mesh_path` is set; `wrapper_table_z=mesh_floor_z` is hygiene for the fallback path.
- **Do not claim** width-capped full-scene hold equals isolated G1 promotion parameters or a 12/12 seed matrix.

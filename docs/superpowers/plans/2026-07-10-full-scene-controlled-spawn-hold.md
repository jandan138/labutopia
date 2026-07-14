# Full-Scene Controlled Spawn Hold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make G1-style controlled spawn hold on the full colleague USD (`PASS_SOURCE_HOLD` at 1024, then 4096) by aligning spawn radius/Z to beaker mesh/wrapper frame.

**Architecture:** Add a pure helper that builds a spawn `ColliderConfig` from beaker2 mesh AABB (radius without +0.005, `table_z` = mesh floor). Video runner + recipe export use it for `--controlled-spawn-count`. Offline unit tests assert step-0 region counts spill=0 before Isaac.

**Tech Stack:** pytest (CPU), Isaac Sim 4.1 headless, existing D4A_018 overlay + `d4_promotion_spawn_layout`.

**Spec:** `docs/superpowers/specs/2026-07-10-full-scene-controlled-spawn-hold-design.md`

**Diagnosis refs:** RECIPE_P1024 step0 spill=26; G1 isolated PASS; weekly B_P1024 PASS uses tiny raw widths only.

---

## File map

| File | Role |
|------|------|
| `tools/labutopia_fluid/full_scene_spawn_frame.py` | **Create** — mesh-frame spawn config helper |
| `tests/test_full_scene_spawn_frame.py` | **Create** — offline radius/Z/spill=0 asserts |
| `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` | Wire controlled-spawn to mesh frame; bottom_thickness=0.008 |
| `tools/labutopia_fluid/run_export_fluid_recipe_usd.py` | Same spawn frame for recipe bake |
| `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_full_scene_controlled_spawn_hold_20260710*` | Isaac evidence |

---

### Task 1: Spawn-frame helper + failing tests

**Files:** Create `tools/labutopia_fluid/full_scene_spawn_frame.py`, `tests/test_full_scene_spawn_frame.py`

- [ ] **Step 1: Failing tests**

```python
def test_spawn_radius_drops_bbox_padding():
    # classification radius may keep +0.005; spawn radius must equal mesh half
    frame = build_full_scene_spawn_frame(
        source_bbox=BBox(min=(0.256, 0.036, 0.827), max=(0.367, 0.147, 0.917)),
        target_bbox=BBox(min=(0.20, -0.30, 0.81), max=(0.36, -0.14, 0.94)),
        table_top_z=0.773,
    )
    mesh_half = max(0.367 - 0.256, 0.147 - 0.036) / 2.0
    assert frame["spawn_radius"] == round(mesh_half, 6)
    assert frame["spawn_radius"] < round(mesh_half + 0.005, 6)
    assert frame["spawn_table_z"] == round(0.827, 6)  # mesh min z, not table top
    assert frame["spawn_table_z"] > frame["table_top_z"]


def test_controlled_positions_step0_spill_zero_offline():
    from tools.labutopia_fluid.fluid_recipe import build_controlled_spawn_plan
    from tools.labutopia_fluid.run_beaker_collider_smoke import build_source_particle_positions, compute_region_counts
    plan = build_controlled_spawn_plan(1024, particle_seed=0)
    config = build_controlled_spawn_collider_config(
        source_bbox=..., target_bbox=..., table_top_z=0.773, plan=plan,
    )
    positions = build_source_particle_positions(config)
    counts = compute_region_counts(positions, config)
    assert counts["spill_count"] == 0
    assert counts["below_table_count"] == 0
```

- [ ] **Step 2:** `pytest tests/test_full_scene_spawn_frame.py -v` → FAIL

- [ ] **Step 3: Implement** `build_full_scene_spawn_frame` + `build_controlled_spawn_collider_config` in `full_scene_spawn_frame.py`:
  - spawn_radius = xy half of source_bbox (no +0.005)
  - spawn_table_z = source_bbox.min[2]
  - wall_thickness=0.026, bottom_thickness=0.008
  - merge d4 layout fields from plan
  - source_center xy from bbox center; z = spawn_table_z

- [ ] **Step 4:** pytest PASS

---

### Task 2: Wire video runner controlled-spawn path

**Files:** Modify `run_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1:** When `controlled_spawn_count > 0`, build config via `build_controlled_spawn_collider_config` from static-stage beaker2/beaker1/table bboxes instead of `replace(build_tabletop_region_config(...))` with inflated radius/table_z.

- [ ] **Step 2:** Wrapper overlay: `bottom_thickness=0.008`, `bottom_overlap=g1_wrapper_bottom_overlap(N)`.

- [ ] **Step 3:** Summary records `spawn_frame` provenance: `spawn_radius`, `spawn_table_z`, `table_top_z`, `radius_padding_removed=true`.

- [ ] **Step 4:** Unit test parser/smoke that controlled path sets `spawn_frame["radius_padding_removed"]` (mock or pure helper test).

---

### Task 3: Wire recipe export

**Files:** Modify `run_export_fluid_recipe_usd.py`

- [ ] Use same `build_controlled_spawn_collider_config` for positions + wrapper bottom_thickness=0.008.
- [ ] Re-export recipe package (Isaac) + refresh `assets/chemistry_lab/lab_001_fluid_recipe_v1/` mirror.
- [ ] `pytest tests/test_export_fluid_recipe_usd.py` still PASS.

---

### Task 4: Isaac Gate A — controlled 1024

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES $ISAAC_PY \
  tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  --usd outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd \
  --fluid-safe-wrapper-overlay \
  --controlled-spawn-count 1024 --controlled-spawn-seed 0 \
  --presentation-render-mode particle_omniglass \
  --presentation-look-preset weekly_omniglass_B \
  --disable-particle-debug-display \
  --steps 120 --headless --hard-exit-after-run \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_full_scene_controlled_spawn_hold_20260710_001/P1024 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_full_scene_controlled_spawn_hold_20260710_P1024.json
```

Expected: `classification=PASS_SOURCE_HOLD`, step0 spill=0, below=0.

---

### Task 5: Isaac Gate B — controlled 4096 + evidence

Same as Task 4 with `--controlled-spawn-count 4096`.
Write top manifest `fluid_spike_full_scene_controlled_spawn_hold_20260710.json` with both cells + claim boundary.
Update weekly HTML note if 4096 PASS (leadership density upgrade candidate).

---

## Success checklist

- [x] Offline: controlled positions spill=0 with mesh frame
- [x] Isaac 1024 full-scene controlled PASS
- [x] Isaac 4096 full-scene controlled PASS
- [x] Recipe export uses same frame; source USD untouched
- [x] No claim that one seed equals full G1 12/12 matrix

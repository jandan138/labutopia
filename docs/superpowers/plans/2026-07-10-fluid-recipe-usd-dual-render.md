# Fluid Recipe USD + Dual Render (A2+B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship A2 derived recipe USD @ 4096 controlled spawn + B2 dual presentation render (`particle_omniglass` leadership default, `isosurface` twin) on the colleague lab scene, with honest claim boundaries and weekly HTML leadership slot.

**Architecture:** `fluid_recipe.py` centralizes spawn/manifest/render-mode/claim helpers. `run_export_fluid_recipe_usd.py` authors a frozen recipe package from immutable source USD. Video runner gains `--presentation-render-mode` + `--controlled-spawn-count`; branches on `presentation_enabled` + `render_mode` — **never** maps `particle_omniglass` → `presentation_isosurface_video=True` (that authors PhysX isosurface). Isaac smokes: leadership `particle_omniglass` first, then isosurface twin on same recipe.

**Tech Stack:** Isaac Sim 4.1 headless, PhysX PBD, USD/UsdShade, pytest (CPU), Isaac python at `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python`.

**Spec:** `docs/superpowers/specs/2026-07-10-fluid-recipe-usd-dual-render-design.md`

**Hard rules:** (1) Never overwrite source `lab_001_level1_pour_tabletop_with_liquid.usd`. (2) `particle_omniglass` must not enable isosurface APIs. (3) Physics authority = particle readback only. (4) Wrapper pinned D4A_018. (5) Leadership density = 4096. (6) Enforce spec §Claim boundary in manifests + tests.

---

## File map

| File | Role |
|------|------|
| `tools/labutopia_fluid/fluid_recipe.py` | Spawn, manifest, render-mode, claim boundary (partial) |
| `tests/test_fluid_recipe.py` | Unit tests (partial) |
| `tools/labutopia_fluid/run_export_fluid_recipe_usd.py` | **Create** — source → wrapper + CompletedPBD → package |
| `tests/test_export_fluid_recipe_usd.py` | **Create** — manifest + immutability |
| `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` | CLI + dual-render branching |
| `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py` | Render-mode wiring tests |
| `tools/labutopia_fluid/run_fluid_recipe_dual_render_smoke.py` | **Create** — 2-cell Isaac sweep |
| `tests/test_fluid_recipe_dual_render_smoke.py` | **Create** — cell table + manifest schema |
| `outputs/usd_asset_packages/lab_001_fluid_recipe_v1/` | `lab_001_level1_pour_tabletop_fluid_recipe_v1.usd` + `recipe_manifest.json` |
| `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_fluid_recipe_dual_render_20260710_v1.json` | Dual-render manifest |
| `reports/2026-07-07-labutopia-fluid-weekly/index.html` | Leadership candidate slot |

---

## Task 1: Finish `fluid_recipe` helpers + unit tests (partially done)

**Files:** `tools/labutopia_fluid/fluid_recipe.py`, `tests/test_fluid_recipe.py`

**Done:** `resolve_presentation_render_mode`, `presentation_video_enabled`, `build_controlled_spawn_plan`, 4 tests.

- [ ] **Step 1: Failing tests** — add `test_build_recipe_manifest_4096_defaults`, `test_build_fluid_recipe_claim_boundary_blocks_leadership_overclaims` asserting `recipe_id`, `wrapper_variant_id=D4A_018`, `raw_colleague_points_used=false`, allowed `fluid_recipe_usd_exported=true`, blocked `leadership_video_equals_g1_promotion` / `recipe_equals_raw_colleague_50k_zero_leak`.

- [ ] **Step 2:** `pytest tests/test_fluid_recipe.py -v` → FAIL.

- [ ] **Step 3: Implement** `SOURCE_USD_REL`, `recipe_package_dir()`, `build_recipe_manifest()` (wraps spawn plan + `source_usd`, `fluid_recipe_usd_exported=true`), `build_fluid_recipe_claim_boundary()` per spec §Claim boundary.

- [ ] **Step 4:** `pytest tests/test_fluid_recipe.py -v` → PASS.

---

## Task 2: Video runner CLI + dual render (CRITICAL separation)

**Files:** `run_colleague_native_usd_completed_pbd_step_video.py`, `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

**Bug to fix:** L2006–2007 sets `args.presentation_isosurface_video = True` for any `presentation_enabled` — this enables isosurface for `particle_omniglass`. **Delete this.** Use separate `presentation_enabled` + `render_mode`.

- [ ] **Step 1: Failing tests** — `test_resolve_render_mode_particle_omniglass_does_not_imply_isosurface_flag`; summary must emit `presentation_render_mode` + `presentation_isosurface_enabled=false` for omniglass.

- [ ] **Step 2: Add CLI** in `build_arg_parser` (~L2605):
  - `--controlled-spawn-count` (int, default 0)
  - `--controlled-spawn-seed` (int, default 0)
  - `--presentation-render-mode` choices `{none,isosurface,particle_omniglass}` default `none`

- [ ] **Step 3: Refactor `_run_runtime`** — compute `render_mode`, `presentation_enabled`, `enable_isosurface = (render_mode == "isosurface")`, `enable_particle_omniglass = (render_mode == "particle_omniglass")`. Replace all `if args.presentation_isosurface_video:` with mode-specific branches:
  - **isosurface:** isosurface contract, `add_physx_particle_isosurface(enabled=True)`, `presentation_isosurface` camera slot.
  - **particle_omniglass:** OmniGlass material bind to ParticleSet/Points, debug viz OFF, **no** isosurface APIs, presentation camera (not isosurface slot).
  - Pass `presentation_isosurface_video=enable_isosurface` only into `_author_completed_pbd_runtime_particles`.

- [ ] **Step 4:** Summary fields: `presentation_render_mode`, `presentation_enabled`, `presentation_isosurface_enabled` (true only for isosurface). Keep `--presentation-isosurface-video` as back-compat alias mapping to `isosurface` via `resolve_presentation_render_mode`.

- [ ] **Step 5:** `pytest tests/test_fluid_recipe.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py -v -k "render_mode or presentation"` → PASS.

---

## Task 3: Export tool `run_export_fluid_recipe_usd.py`

**Files:** Create `tools/labutopia_fluid/run_export_fluid_recipe_usd.py`, `tests/test_export_fluid_recipe_usd.py`

- [ ] **Step 1: Failing tests** — manifest has `particle_count=4096`, `controlled_spawn=true`; source USD bytes unchanged after export (`test_export_does_not_modify_source_usd`).

- [ ] **Step 2: Implement** — open `outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd` → optional MDL closure → `apply_fluid_safe_wrapper_overlay` (D4A_018, skip if exists) → deactivate original fluid → author `/World/CompletedPBD` from `build_controlled_spawn_plan(N)` positions → export to `outputs/usd_asset_packages/lab_001_fluid_recipe_v1/lab_001_level1_pour_tabletop_fluid_recipe_v1.usd` + `recipe_manifest.json`. Reuse `_author_completed_pbd_runtime_particles(..., presentation_isosurface_video=False)`. CLI: `--particle-count` (4096), `--particle-seed`, `--out-dir`, `--dry-run`.

- [ ] **Step 3: Run export (Isaac):**
```bash
ISAAC_PY=.../embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
$ISAAC_PY tools/labutopia_fluid/run_export_fluid_recipe_usd.py --particle-count 4096 --headless
```

- [ ] **Step 4:** `pytest tests/test_export_fluid_recipe_usd.py -v` → PASS.

---

## Task 4: Dual Isaac smoke @ 4096

**Files:** Create `run_fluid_recipe_dual_render_smoke.py`, `tests/test_fluid_recipe_dual_render_smoke.py`, `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_fluid_recipe_dual_render_20260710_v1/`

- [ ] **Step 1: Failing test** — cell table: `RECIPE_P4096_OMNIGLASS` (`particle_omniglass`, leadership_default=true) + `RECIPE_P4096_ISOSURFACE` (`isosurface`, leadership_default=false).

- [ ] **Step 2: Thin sweep** — for each cell, call video runner on recipe USD:
```bash
--usd outputs/.../lab_001_level1_pour_tabletop_fluid_recipe_v1.usd \
--fluid-safe-wrapper-overlay --presentation-look-preset weekly_omniglass_B \
--presentation-render-mode {particle_omniglass|isosurface} \
--particle-limit 0 --controlled-spawn-count 0 \
--steps 120 --headless --hard-exit-after-run
```
Run **OMNIGLASS first** (B2 leadership). Write top manifest with `readback_classification`, `claim_boundary`, per-cell `presentation_render_mode`.

- [ ] **Step 3: Verify** leadership cell: MP4 exists, `presentation_isosurface_enabled=false`. Twin: comparison artifact (shard OK).

---

## Task 5: Weekly HTML leadership slot

**Files:** `reports/2026-07-07-labutopia-fluid-weekly/index.html`, `assets/fluid-recipe-leadership/`

- [ ] **Step 1:** Add `#fluid-recipe-leadership` section **above** `#omniglass-matrix` — eyebrow `B2 领导力候选`, embed `RECIPE_P4096_OMNIGLASS` MP4, bilingual caption: recipe USD · controlled spawn 4096 · D4A_018 · not official Visual A · readback honest · ≠ G1 promotion. Link/note for isosurface twin as diagnostic.

- [ ] **Step 2:** Register manifest in `docs/labutopia_lab_poc/evidence_manifests/README.md`.

---

## Task 6: Claim boundary checks

**Files:** `fluid_recipe.py`, video runner summary, smoke manifest, tests

- [ ] **Step 1: Failing test** — when USD path contains `fluid_recipe_v1` or `--controlled-spawn-count > 0`, summary includes `build_fluid_recipe_claim_boundary()` merged allowed/blocked; `official_visual_a_compatible=false`; leadership cell sets `leadership_look_candidate_recorded=true`.

- [ ] **Step 2: Implement** in runner summary + smoke manifest writer. Block forbidden claims from spec (no `真实水`, no `photoreal`, no `video=physics success`).

- [ ] **Step 3: Full CPU suite:**
```bash
pytest tests/test_fluid_recipe.py tests/test_export_fluid_recipe_usd.py \
  tests/test_fluid_recipe_dual_render_smoke.py \
  tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py -v
```

---

## Success checklist (B2)

- [ ] Package `outputs/usd_asset_packages/lab_001_fluid_recipe_v1/`; source USD untouched
- [ ] `particle_omniglass` @ 4096 with `presentation_isosurface_enabled=false`
- [ ] Isosurface twin for comparison
- [ ] Captions: recipe + density + classification + not Visual A
- [ ] Weekly HTML leadership slot live
- [ ] Claim boundary tests green

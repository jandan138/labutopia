# Dual-Track Realistic Water Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Physics A (fluid-safe wrapper zero-leak) and Visual A/B infrastructure (MDL ClearWater + reconstruction/lighting + honest claims + C stubs), with official Visual A evidence only on a Physics-A-passing trajectory.

**Architecture:** Three lanes on one PBD trajectory — physics readback (authority), presentation surface (ClearWater MDL + aniso/smooth/isosurface), product FX stubs (disabled). Wrapper is an invisible beaker2-local box-panel collider; native mesh collision stays off.

**Tech Stack:** Isaac Sim 4.1 headless, PhysX PBD, OmniSurfacePresets MDL, USD/PhysX APIs, existing `tools/labutopia_fluid/*` runners and pytest.

**Spec:** `docs/superpowers/specs/2026-07-09-dual-track-realistic-water-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `tools/labutopia_fluid/run_beaker_collider_smoke.py` | `_add_fluid_safe_wrapper()`, local-frame panels, hold classification |
| `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py` | `D4_WRAPPER_SWEEP` + promotion matrix |
| `tools/labutopia_fluid/run_colleague_liquid_usd_leak_smoke.py` | Full-scene wrapper overlay |
| `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` | MDL water, aniso/smooth, DomeLight, RTX, FX stubs, contracts |
| `tests/test_fluid_beaker_collider_*.py` | Wrapper + sweep unit tests |
| `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py` | Visual contract / MDL status tests |
| `reports/2026-07-07-labutopia-fluid-weekly/index.html` | P0 claim scrub |
| `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md` | P0 + progress notes |
| `docs/labutopia_lab_poc/evidence_manifests/README.md` | Registry keys |
| `assets/chemistry_lab/lab_001_fluid_spike/colliders_d4/` | Authored wrapper USDs |
| `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_proxy_wrapper_design_*` | Physics evidence |
| `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_mdl_water_visual_*` | Visual evidence |

## Workstream order

1. **P0** claim scrub (can ship alone)
2. **Visual infra** (MDL attempt, aniso, lights, stubs) — parallel with physics
3. **Physics D4** wrapper → 9-trial ladder → 3×50k G1
4. **Visual A official** on Physics-A traj
5. **P2 pour** (after G1) — separate follow-up if needed

---

## Task 0: P0 Claim Scrub

**Status:** done (`64aa9bc`)

**Files:**
- Modify: `reports/2026-07-07-labutopia-fluid-weekly/index.html`
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [x] **Step 1:** Grep for `真实水|像水|统一真实水|photoreal` in those files; list hits.
- [x] **Step 2:** Replace titles/body with `统一诊断水面（MDL 目标未过）` / machine claims; keep WARN language.
- [x] **Step 3:** Grep again — zero forbidden colloquial claims in titles; blocked-claim lists still present.
- [x] **Step 4:** Commit `docs: scrub realistic-water PM claims pending MDL+wrapper GO`

---

## Task 1: Fluid-safe wrapper authoring (local frame)

**Status:** done (`27f9918`, motion_contract `9de467c`)

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_smoke.py`
- Test: `tests/test_fluid_beaker_collider_smoke.py`

- [ ] **Step 1:** Write failing tests for `_add_fluid_safe_wrapper`:
  - creates `/World/beaker2/FluidSafeWrapper` (or test fixture parent)
  - `visibility=invisible`, `labutopia:fluidSafeWrapper=true`
  - panels in **parent-local** frame (not world poses under transformed parent)
  - native mesh `physics:collisionEnabled=false`
  - records `wrapper_frame=local_to_beaker2`
- [ ] **Step 2:** Run tests — expect fail.
- [ ] **Step 3:** Implement `_add_fluid_safe_wrapper()` from `_add_proxy_collision_wrapper` lineage; world AABB → local bake; box panels only.
- [ ] **Step 4:** Pin defaults `initial_radial_velocity=0.08`, `particle_max_velocity=5.0` in promotion config helpers.
- [ ] **Step 5:** Run tests — pass.
- [ ] **Step 6:** Commit `feat: author beaker2-local fluid-safe wrapper collider`

---

## Task 2: D4 sweep phase + STOP taxonomy

**Status:** done (`69848fe`)

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
- Test: `tests/test_fluid_beaker_collider_followup_sweep.py`

- [ ] **Step 1:** Failing tests for `build_d4_wrapper_sweep()` / phase id `D4_WRAPPER_SWEEP` covering panel_count/wall_thickness/bottom_overlap/inset ranges from spec.
- [ ] **Step 2:** Failing tests that matrix incomplete → `STOP_WITH_EVIDENCE`; velocity crutch → `FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE`.
- [ ] **Step 3:** Implement sweep + compose `classify_collider_hold` + followup non-physical gate (do not collapse FAIL_*).
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit `feat: add D4 fluid-safe wrapper sweep phase`

---

## Task 3: Full-scene wrapper integration smoke

**Status:** done (`4a96720`)

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_liquid_usd_leak_smoke.py`
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` (overlay hook)
- Test: `tests/test_fluid_colleague_liquid_usd_leak_smoke.py`

- [x] **Step 1:** Failing test: collider mode `fluid-safe-wrapper` disables `/World/beaker2/mesh` collision and authors `FluidSafeWrapper`.
- [x] **Step 2:** Implement full-scene overlay path.
- [x] **Step 3:** Dry-run/unit pass without requiring GPU if mocked; document Isaac command for 512p smoke.
- [x] **Step 4:** Commit `feat: overlay fluid-safe wrapper on colleague native scene`

---

## Task 4: Promotion matrix runner (9 then 12)

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py` (or new `run_d4_wrapper_promotion.py` if cleaner)
- Test: matching tests
- Create manifests under `docs/labutopia_lab_poc/evidence_manifests/`

- [ ] **Step 1:** Failing test: promotion grid = seeds{0,1,2} × counts{512,1024,4096,50000}; G1 requires all 12 `PASS_SOURCE_HOLD`.
- [ ] **Step 2:** Implement matrix driver; partial near-pass → `STOP_WITH_EVIDENCE`.
- [ ] **Step 3:** Run unit tests pass.
- [ ] **Step 4:** Execute Isaac promotion (engineering runtime) — record manifests; do not claim GO until 12/12.
- [ ] **Step 5:** Commit evidence when available `docs: record D4 wrapper promotion matrix evidence`

---

## Task 5: MDL ClearWater attempt + status honesty

**Status:** done (`c6b13ef`)

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` (`_author_liquid_presentation_water_material`)
- Test: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1:** Failing tests:
  - `mdl_bind_attempted` true when MDL path runs
  - statuses: `PASS | MDL_COMPILE_FAIL | FALLBACK_USED | MDL_NOT_ATTEMPTED`
  - hardcoded Preview without attempt must be `MDL_NOT_ATTEMPTED` (fix current lie)
  - success path: `sub_identifier=OmniSurface_ClearWater`, `material_backend=MDL_WATER`
- [ ] **Step 2:** Implement attempt via local mirror / `CreateAndBindMdlMaterialFromLibrary`; fallback only after fail.
- [ ] **Step 3:** Extend `scan_mdl_compile_errors` for presentation shader path.
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit `feat: attempt OmniSurface_ClearWater for presentation liquid`

---

## Task 6: Anisotropy + smoothing postprocess

**Status:** done (`8a2c943`)

**Files:**
- Modify: `run_colleague_native_usd_completed_pbd_step_video.py`
- Test: same test file

- [ ] **Step 1:** Failing tests for `build_presentation_postprocess_contract`: anisotropy scale=5,min=1,max=2; smoothing strength=0.5; claim_boundary visual-only.
- [ ] **Step 2:** Implement `add_physx_particle_anisotropy` / `add_physx_particle_smoothing` in presentation mode.
- [ ] **Step 3:** Tests pass; commit `feat: enable particle anisotropy and smoothing for presentation`

---

## Task 7: DomeLight + refraction bounces

**Status:** done (`00c010b`)

**Files:**
- Modify: `_author_liquid_presentation_lighting`, SimulationApp/kit settings in runner
- Test: lighting/render contract tests

- [ ] **Step 1:** Failing tests: DomeLight path + DistantLight; `lighting_contract_hash=liquid_presentation_dome_key_v2`; `max_refraction_bounces>=12` recorded.
- [ ] **Step 2:** Implement; record actual RTX setting in manifest.
- [ ] **Step 3:** Pass + commit `feat: presentation dome light and refraction bounce contract`

---

## Task 8: product_water_fx stubs + VLA overlay hashes

**Status:** done (`e06b994`)

**Files:**
- Modify: `build_presentation_visual_contract` and related
- Test: contract tests

- [ ] **Step 1:** Failing tests for stub schema (system+set paths, roles splash/foam/spray/bubbles, wetting reserved, `affects_leak_classification=false`).
- [ ] **Step 2:** Failing tests for VLA overlay fields: `material_hash` valid only if MDL PASS; `fallback_material_hash`; `product_fx_hash=product_water_fx_disabled_v1`.
- [ ] **Step 3:** Implement `build_product_water_fx_contract()` always `enabled=false`; CLI `--product-water-fx` default off.
- [ ] **Step 4:** Pass + commit `feat: reserve product_water_fx stubs and VLA overlay hashes`

---

## Task 9: Visual A provenance + rubric manifest fields

**Status:** done (`2af956a`)

**Files:**
- Modify: runner summary / manifest writers
- Test: provenance required when `visual_acceptance_scenario=A_static_clear_water`

- [x] **Step 1:** Failing test: official Visual A summary requires `physics_trajectory_id`, seed, particle_count, wrapper_variant_id, physics `PASS_SOURCE_HOLD`.
- [x] **Step 2:** Implement fields; block official A claim without provenance.
- [x] **Step 3:** Commit `feat: require physics provenance for Visual A evidence`

---

## Task 10: Headless smokes + docs registry

**Files:**
- Evidence manifests + `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Spike doc progress section

- [ ] **Step 1:** Run low-N MDL presentation smoke; record `mdl_bind_attempted` and compile status.
- [ ] **Step 2:** After Physics G1, run official Visual A on that traj; fill rubric A booleans.
- [ ] **Step 3:** Update README registry keys (`mdl_water_visual_pass_*`, wrapper design keys).
- [ ] **Step 4:** Commit docs/evidence.

---

## Task 11 (later): Slow pour B

**Depends on:** Task 4 G1 GO + Task 9/10 Visual A.

- [ ] Define pour readback gates in plan follow-up.
- [ ] Kinematic slow pour + rubric B capture.
- [ ] Keep `s3_kinematic_pour_released=false` until gates pass.

---

## Self-review checklist

- [x] Spec blockers addressed (12-trial math, FAIL taxonomy, local frame, MDL honesty, C stubs)
- [ ] Plan tasks map 1:1 to spec stages P0–P2
- [ ] No task claims Visual A complete without Physics A provenance
- [ ] TDD steps present for code tasks
- [ ] Commits frequent and scoped

---

## Execution note

Prefer **subagent-driven-development**: P0 + Tasks 5–8 can parallelize with Tasks 1–3; Task 4 and official Task 10 Visual A are gated on GPU Isaac runs.


## Progress (2026-07-09)

Code/unit tasks complete: 0,1,2,3,5,6,7,8,9 (+ motion_contract fix).
**79 passed** on beaker collider unit tests (smoke + followup).

### Physics G1 — GO (Task 4 complete)

Live promotion matrix `fluid_spike_d4_wrapper_promotion_v4_20260709.json`:
**12/12 `PASS_SOURCE_HOLD`**, `g1_physics_a=true`, contract `s2_no_outside_source_v3_outer_face`.

Stack that cleared G1:
- Dual-ring segmented panels (72×2) + phase offset + arc≥1.35 + wall≥0.026
- Outer-face classifier (`R+T+slack`)
- CCD on; 50k absolute `interior_inset≥0.010`, `bottom_overlap≥0.016`
- Spawn width/offsets scaled with spacing (no width>spacing)

Honest claim: **Physics A static zero-leak on D4A_018 promotion matrix**. Do **not** claim colloquial “真实水” until Visual A (G2) also passes.

Still GPU-gated:
- Task 10: Official Visual A on Physics-A traj (in progress)
- Task 11: Slow pour B after Visual A

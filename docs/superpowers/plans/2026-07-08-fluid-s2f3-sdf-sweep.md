# Fluid S2F3 SDF Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and run `S2F3_C3_SDF_SWEEP` so the SDF beaker-collider route has bounded IsaacSim41 evidence and clear stop/go wording.

**Architecture:** Extend the existing S2F follow-up runner instead of adding a new script. Add SDF fields to the candidate/config/spec path, build 24 `C3A_*` candidates, write a phase-aware manifest, and reuse the same per-variant evidence pipeline as C2/S2F2/S2F5.

**Tech Stack:** Python 3.10, pytest, Isaac Sim 4.1, USD/PhysX/PBD, JSON manifests, Markdown evidence docs.

---

### Task 1: Add S2F3 Candidate Contract Tests

**Files:**
- Modify: `tests/test_fluid_beaker_collider_followup_sweep.py`

- [x] **Step 1: Write failing tests**

Add tests that import `build_s2f3_sdf_sweep`, assert the 24-candidate grid, and assert a sample candidate materializes into `ColliderConfig` and `VariantSpec` with `collision_approximation="sdf"` and `setup="s2f3_sdf_open_concave_mesh"`.

- [x] **Step 2: Verify RED**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f3_builds_required_sdf_grid tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f3_candidate_materializes_sdf_config_and_spec
```

Expected: FAIL because `build_s2f3_sdf_sweep` does not exist.

### Task 2: Add SDF Config and Candidate Implementation

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_smoke.py`
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`

- [x] **Step 1: Extend data models**

Add optional SDF fields to `ColliderConfig` and `VariantSpec`: `sdf_subgrid_resolution`, `sdf_margin`, and `sdf_narrow_band_thickness`. Keep defaults as `None` except the existing C3 spec defaults.

- [x] **Step 2: Wire SDF fields into USD authoring**

Pass SDF fields into `_apply_static_collision` and author the corresponding PhysX SDF attributes only when the API exposes them.

- [x] **Step 3: Add `build_s2f3_sdf_sweep`**

Build the 24 required `C3A_*` candidates with `mesh_bottom_fan_closure=True` and `normals_winding_audit="pass"`.

- [x] **Step 4: Verify GREEN**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f3_builds_required_sdf_grid tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f3_candidate_materializes_sdf_config_and_spec
```

Expected: PASS.

### Task 3: Add Manifest and CLI Tests

**Files:**
- Modify: `tests/test_fluid_beaker_collider_followup_sweep.py`
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`

- [x] **Step 1: Write failing manifest tests**

Add tests for S2F3 `GO_NEXT` and `STOP_WITH_EVIDENCE`. Passing C3A results must populate `best_for_s2f5`, keep `best_for_s3=[]`, and set `next_stage.id="S2F5_PROMOTION_REVIEW"`. Failing results must set `next_stage.id="S2F4_C4_NATIVE_MESH_ISOLATION"`.

- [x] **Step 2: Write failing CLI test**

Add a plan-only test for `--phase S2F3_C3_SDF_SWEEP` that writes the default S2F3 manifest shape and 24 candidates.

- [x] **Step 3: Verify RED**

Run the new tests and confirm they fail because the phase is unsupported.

- [x] **Step 4: Implement phase support**

Add S2F3 defaults, phase dispatch, manifest type, allowed claims, next-stage logic, and artifact loading support for `C3A_*` summaries.

- [x] **Step 5: Verify GREEN**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py
```

Expected: all follow-up tests PASS.

### Task 4: Run S2F3 Evidence

**Files:**
- Runtime output: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json`
- Runtime output: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f3_c3_sdf_sweep_20260708_001/`
- Runtime output: `assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f3/`

- [x] **Step 1: Run plan-only**

```bash
python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F3_C3_SDF_SWEEP --plan-only
```

Expected: manifest status `PLAN_READY`, candidate count `24`.

- [x] **Step 2: Run live S2F3**

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F3_C3_SDF_SWEEP --steps 240 --headless
```

Expected: final manifest status is either `GO_NEXT` with `best_for_s2f5` or `STOP_WITH_EVIDENCE` with concrete C3A failures.

Observed: `STOP_WITH_EVIDENCE`, `reason=no_c3a_sdf_candidate_passed`, `best_for_s2f5=[]`, `best_for_s3=[]`.
All 24 candidates produced complete evidence and classified as `FAIL_CONTAINER_LEAK`; the runtime warning gate passed.

### Task 5: Update Docs and Verify

**Files:**
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md`

- [x] **Step 1: Update PM wording**

Explain S2F3 result in plain Chinese: what SDF tested, whether it passed, and what it means for liquid in `level1_pour`.

- [x] **Step 2: Update evidence index**

Register the S2F3 manifest and artifact directory.

- [ ] **Step 3: Run verification**

```bash
python -m pytest -q tests/test_fluid_beaker_collider_smoke.py tests/test_fluid_beaker_collider_followup_sweep.py
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json
git diff --check
```

Expected: all commands exit `0`.

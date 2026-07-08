# Fluid S2F5 Promotion Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run `S2F5_PROMOTION_REVIEW` for only `C2A_009_S2F2_VEL020` across 3 authored layout seeds and 2 particle counts, then decide whether it is a stable `best_for_s3` static-hold candidate.

**Architecture:** Reuse the existing S2F follow-up runner and `_run_variant` path so every S2F5 trial writes the same readback traces, frames, overlays, and warning scan as S2F1/S2F2. Add seed-aware particle layout selection to `ColliderConfig` with default `None`, preserving existing S2/S2F behavior when no seed is provided. S2F5 aggregates six trial summaries into one manifest and promotes the parent only if every required trial passes strict static-hold gates.

**Tech Stack:** Python 3.10, pytest, Isaac Sim 4.1, USD/PhysX/PBD, JSON evidence manifests.

---

## Files

- Modify: `tools/labutopia_fluid/run_beaker_collider_smoke.py`
  - Add optional `particle_seed` to `ColliderConfig`.
  - Preserve current deterministic source layout when `particle_seed is None`.
  - Use deterministic hash-ranked sampling when `particle_seed` is set.
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
  - Add S2F5 defaults, candidate builder, aggregation helpers, manifest writer support, CLI phase support, and runtime execution path.
- Modify: `tests/test_fluid_beaker_collider_smoke.py`
  - Prove seeded source particle layouts are deterministic, seed-sensitive, and preserve count/source bounds.
- Modify: `tests/test_fluid_beaker_collider_followup_sweep.py`
  - Prove S2F5 builds exactly six trials for `C2A_009_S2F2_VEL020`.
  - Prove aggregation promotes only when all six trials pass.
  - Prove partial failure keeps `best_for_s3=[]`.
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
  - Add PM-facing S2F5 status and interpretation after live run.
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
  - Register the S2F5 manifest and artifact directory.
- Modify: `docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md`
  - Mark Step 8 complete or blocked with concrete S2F5 evidence.
- Create after live run: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json`
- Create after live run: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f5_promotion_review_20260708_001/`
- Create at runtime: `assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f5/*.usda`

---

### Task 1: Seed-Aware Static-Hold Particle Layouts

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_smoke.py`
- Test: `tests/test_fluid_beaker_collider_smoke.py`

- [ ] **Step 1: Write failing tests**

Add two tests:

```python
def test_source_particle_positions_are_deterministic_for_same_seed():
    from tools.labutopia_fluid.run_beaker_collider_smoke import ColliderConfig, build_source_particle_positions

    config = ColliderConfig(particle_count=64, particle_seed=7)

    assert build_source_particle_positions(config) == build_source_particle_positions(config)


def test_source_particle_positions_vary_across_seed_without_changing_count():
    from tools.labutopia_fluid.run_beaker_collider_smoke import ColliderConfig, build_source_particle_positions

    seed_7 = build_source_particle_positions(ColliderConfig(particle_count=64, particle_seed=7))
    seed_8 = build_source_particle_positions(ColliderConfig(particle_count=64, particle_seed=8))

    assert len(seed_7) == 64
    assert len(seed_8) == 64
    assert seed_7 != seed_8
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_smoke.py::test_source_particle_positions_are_deterministic_for_same_seed tests/test_fluid_beaker_collider_smoke.py::test_source_particle_positions_vary_across_seed_without_changing_count
```

Expected: both tests fail because `ColliderConfig` has no `particle_seed`.

- [ ] **Step 3: Implement seed support**

Add `particle_seed: int | None = None` to `ColliderConfig`. In `build_source_particle_positions`, keep the current sort key when the seed is `None`; when seed is set, compute a deterministic hash from seed and rounded coordinates and combine it with radius ranking so S2F5 tests different initial layouts while still stressing the container wall.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_smoke.py::test_source_particle_positions_are_deterministic_for_same_seed tests/test_fluid_beaker_collider_smoke.py::test_source_particle_positions_vary_across_seed_without_changing_count
```

Expected: both tests pass.

---

### Task 2: S2F5 Candidate Builder and Aggregation Contract

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
- Test: `tests/test_fluid_beaker_collider_followup_sweep.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert:

```python
def test_s2f5_builds_only_promoted_vel020_trials():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f5_promotion_review_sweep

    candidates = build_s2f5_promotion_review_sweep()

    assert len(candidates) == 6
    assert {candidate.parent_candidate_id for candidate in candidates} == {"C2A_009_S2F2_VEL020"}
    assert {candidate.particle_count for candidate in candidates} == {256, 1024}
    assert {candidate.particle_seed for candidate in candidates} == {0, 1, 2}
    assert all(candidate.phase == "S2F5_PROMOTION_REVIEW" for candidate in candidates)
    assert all(candidate.variable_group == "promotion_review" for candidate in candidates)


def test_s2f5_aggregation_promotes_only_when_all_required_trials_pass():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import aggregate_s2f5_promotion_review

    results = [
        {
            "candidate_id": f"C2A_009_S2F2_VEL020_S2F5_P{particle_count:04d}_SEED{seed:03d}",
            "parent_candidate_id": "C2A_009_S2F2_VEL020",
            "classification": "PASS_SOURCE_HOLD",
            "particle_count": particle_count,
            "particle_seed": seed,
            "readback_available": True,
            "evidence_files_complete": True,
            "non_physical_parameter_dependence": False,
        }
        for particle_count in (256, 1024)
        for seed in (0, 1, 2)
    ]

    aggregate = aggregate_s2f5_promotion_review(results)

    assert aggregate["status"] == "GO_NEXT"
    assert aggregate["best_for_s3"] == ["C2A_009_S2F2_VEL020"]
    assert aggregate["required_trial_count"] == 6
    assert aggregate["passed_trial_count"] == 6


def test_s2f5_aggregation_keeps_s3_closed_on_any_trial_failure():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import aggregate_s2f5_promotion_review

    results = [
        {
            "candidate_id": f"C2A_009_S2F2_VEL020_S2F5_P{particle_count:04d}_SEED{seed:03d}",
            "parent_candidate_id": "C2A_009_S2F2_VEL020",
            "classification": "PASS_SOURCE_HOLD",
            "particle_count": particle_count,
            "particle_seed": seed,
            "readback_available": True,
            "evidence_files_complete": True,
            "non_physical_parameter_dependence": False,
        }
        for particle_count in (256, 1024)
        for seed in (0, 1, 2)
    ]
    results[-1]["classification"] = "FAIL_CONTAINER_LEAK"

    aggregate = aggregate_s2f5_promotion_review(results)

    assert aggregate["status"] == "STOP_WITH_EVIDENCE"
    assert aggregate["best_for_s3"] == []
    assert aggregate["failed_trials"] == [results[-1]["candidate_id"]]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f5_builds_only_promoted_vel020_trials tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f5_aggregation_promotes_only_when_all_required_trials_pass tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f5_aggregation_keeps_s3_closed_on_any_trial_failure
```

Expected: tests fail because S2F5 builder and aggregator do not exist.

- [ ] **Step 3: Implement builder and aggregation**

Implement `build_s2f5_promotion_review_sweep`, `aggregate_s2f5_promotion_review`, and trial metadata handling in `C2ProxyCandidate.to_config`.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same three focused tests. Expected: all pass.

---

### Task 3: S2F5 CLI Runtime and Manifest

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
- Test: `tests/test_fluid_beaker_collider_followup_sweep.py`

- [ ] **Step 1: Write failing manifest test**

Add a test that calls `write_followup_manifest` with `phase="S2F5_PROMOTION_REVIEW"` and six passing trial results, then asserts:

```python
assert manifest["stage"] == "S2F5_PROMOTION_REVIEW"
assert manifest["status"] == "GO_NEXT"
assert manifest["best_for_s3"] == ["C2A_009_S2F2_VEL020"]
assert manifest["s2f5_promotion_review_complete"] is True
assert manifest["s3_kinematic_pour_released"] is True
assert manifest["phase_specs"]["S2F5_PROMOTION_REVIEW"]["status"] == "COMPLETE_GO_NEXT"
```

Add a sibling test with one failed trial and assert `best_for_s3=[]`, `s3_kinematic_pour_released=False`, and `status="STOP_WITH_EVIDENCE"`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py::test_write_s2f5_manifest_promotes_after_all_trials_pass tests/test_fluid_beaker_collider_followup_sweep.py::test_write_s2f5_manifest_blocks_on_single_trial_failure
```

Expected: tests fail because `write_followup_manifest` does not support S2F5.

- [ ] **Step 3: Implement CLI support**

Add:

```text
DEFAULT_S2F5_ARTIFACT_DIR=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f5_promotion_review_20260708_001
DEFAULT_S2F5_MANIFEST_PATH=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json
DEFAULT_S2F5_SCENE_DIR=assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f5
```

Allow `--phase S2F5_PROMOTION_REVIEW`. Use `build_s2f5_promotion_review_sweep` and the existing `_run_c2_proxy_sweep` loop. In each trial result, carry `particle_count`, `particle_seed`, `readback_available`, and `evidence_files_complete`.

- [ ] **Step 4: Run focused and adjacent tests**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py
```

Expected: all tests in that file pass.

---

### Task 4: Live S2F5 Review, Docs, and Verification

**Files:**
- Runtime writes: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json`
- Runtime writes: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f5_promotion_review_20260708_001/`
- Runtime writes: `assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f5/`
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md`

- [x] **Step 1: Run plan-only**

Run:

```bash
python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F5_PROMOTION_REVIEW --plan-only
```

Expected: manifest is written with six S2F5 trial candidates and `status=PLAN_READY`.

- [x] **Step 2: Run live IsaacSim41**

Run:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F5_PROMOTION_REVIEW --steps 240 --headless
```

Expected: six trial artifact folders are written. Final manifest reports either `GO_NEXT` with `best_for_s3=["C2A_009_S2F2_VEL020"]` or `STOP_WITH_EVIDENCE` with explicit failed trial IDs.

- [x] **Step 3: Update docs with the actual result**

Update the three docs listed above with the concrete result, not a predicted result.

Actual result:

```text
stage=S2F5_PROMOTION_REVIEW
status=STOP_WITH_EVIDENCE
reason=one_or_more_s2f5_trials_failed
best_for_s3=[]
s3_kinematic_pour_released=false
passed_trial_count=0/6
```

All six trials produced same-run readback and evidence files, but all failed the
strict zero-leak gate. The 256-particle trials were near misses with 1-2 outside
particles. The 1024-particle trials leaked heavily, with outside counts 347,
340, and 338. The PM interpretation is that `C2A_009_S2F2_VEL020` was a useful
near-pass diagnostic, not a stable S3 entry candidate. S2F5 ran before S2F3/S2F4
because S2F2 had exactly one near-pass candidate and the shortest stop/go check
was to retest that candidate directly. S2F3/S2F4 are the next diagnostic work;
they were not canceled.

- [ ] **Step 4: Verify**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_smoke.py tests/test_fluid_beaker_collider_followup_sweep.py
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json
git diff --check
```

Expected: tests pass, JSON parses, and diff check exits 0.

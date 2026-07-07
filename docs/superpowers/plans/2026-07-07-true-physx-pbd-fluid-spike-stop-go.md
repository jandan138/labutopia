# True PhysX/PBD Fluid Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded True PhysX/PBD fluid spike for LabUtopia `level1_pour` that either demonstrates real particle fluid transfer or produces signed failure evidence explaining why it cannot currently work in LabUtopia / EBench.

**Architecture:** Treat fluid as a parallel spike, not as part of the current rigid/articulation Expert Oracle Score claim. Start with USD/schema and standalone runtime smoke, then isolate beaker collider behavior, then kinematic pouring, then LabUtopia expert replay, and only then EBench consumer/readback. S2 and S3 must evaluate a collider matrix instead of a single collider path.

**Tech Stack:** Isaac Sim 5.1 / 4.1 concepts, Omni PhysX PBD particles, USD/USDA overlays, `pxr.Usd`, LabUtopia `main.py`, LabUtopia `PickPourTask`, EBench / GenManip evidence manifests, JSON/JSONL readback traces.

---

## Scope Check

This plan does not implement visual-only liquid, semantic volume proxy, policy training, or official leaderboard evaluation. It only establishes whether true PhysX/PBD particles can be made usable enough for future task integration.

If any stage returns `STOP_WITH_EVIDENCE`, do not continue by tuning blindly. Write the failure manifest, update the PM-facing status, and open a narrower follow-up plan.

## File Structure

Create or modify these files in `LabUtopia` during implementation:

```text
docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s<stage>_<slug>_<yyyymmdd>.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_<run_id>/
tools/labutopia_fluid/inspect_usd_particles.py
tools/labutopia_fluid/build_level1_pour_fluid_overlay.py
tools/labutopia_fluid/run_standalone_particle_smoke.py
tools/labutopia_fluid/run_beaker_collider_smoke.py
tools/labutopia_fluid/run_kinematic_pour_rig.py
tools/labutopia_fluid/review_fluid_spike_artifacts.py
config/level1_pour_fluid_spike.yaml
tasks/pickpour_task.py
```

Potential generated overlay roots:

```text
assets/chemistry_lab/lab_001_fluid_spike/
assets/chemistry_lab/lab_001_fluid_spike/lab_001_fluid_spike.usda
assets/chemistry_lab/lab_001_fluid_spike/colliders/
```

Do not edit `assets/chemistry_lab/lab_001/lab_001.usd` in place. The native
asset stays as evidence baseline.

## Stage Status Vocabulary

Use exactly these statuses in manifests:

```text
GO_NEXT
STOP_WITH_EVIDENCE
INVALID_SPIKE
NOT_RUN
```

Use exactly these top-level claim fields:

```json
{
  "fluid_spike_claim_allowed": true,
  "true_fluid_claim_allowed": false,
  "expert_oracle_score_claim_allowed": false,
  "canonical_score_claim_allowed": false,
  "score_claim_allowed": false,
  "policy_score_claim_allowed": false,
  "official_leaderboard_claim_allowed": false,
  "visual_only_liquid_claim_allowed": false
}
```

---

### Task 1: S0 Scope Freeze and Schema Probe

**Files:**
- Create: `tools/labutopia_fluid/inspect_usd_particles.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_scope_freeze_20260707.json`
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`

- [ ] **Step 1: Write `inspect_usd_particles.py`**

Create a read-only USD scanner that records particle prims, particle material bindings, physics scene settings, and beaker collider settings.

The script must inspect at least:

```text
assets/chemistry_lab/lab_001/lab_001.usd
assets/chemistry_lab/lab_003/clock.usd
assets/chemistry_lab/lab_003/lab_003.usd
```

Expected output fields:

```json
{
  "usd_path": "assets/chemistry_lab/lab_001/lab_001.usd",
  "particle_systems": [],
  "particle_sets": [],
  "physics_scenes": [],
  "candidate_beaker_colliders": [],
  "schema_preserved": true
}
```

- [ ] **Step 2: Run S0 schema probe**

Run:

```bash
python tools/labutopia_fluid/inspect_usd_particles.py \
  --usd assets/chemistry_lab/lab_001/lab_001.usd \
  --usd assets/chemistry_lab/lab_003/clock.usd \
  --usd assets/chemistry_lab/lab_003/lab_003.usd \
  --out docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_schema_probe_20260707.json
```

Expected:

```text
lab_001 particle_systems=[]
clock.usd has /World/ParticleSystem and /World/ParticleSet
```

- [ ] **Step 3: Write S0 manifest**

Write:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_scope_freeze_20260707.json
```

Required fields:

```json
{
  "schema_version": 1,
  "manifest_type": "true_physx_pbd_fluid_spike_evidence",
  "run_id": "fluid_spike_isaacsim41_ebench_s0_scope_freeze_20260707_001",
  "stage": "S0_SCOPE_FREEZE",
  "live_evidence": false,
  "status": "GO_NEXT",
  "expert_oracle_score_claim_allowed": false,
  "canonical_score_claim_allowed": false,
  "true_fluid_definition": "PhysxParticleSystem + ParticleSet + GPU dynamics + particle readback",
  "not_true_fluid": [
    "mesh_only_liquid",
    "shader_only_water",
    "offline_video",
    "rgb_only_success"
  ],
  "allowed_claims": [
    "true fluid spike scope is frozen",
    "level1_pour currently has no particle system",
    "lab_003 clock.usd is the local particle template"
  ],
  "blocked_claims": [
    "level1_pour has true fluid today",
    "Expert Oracle Score includes fluid",
    "official leaderboard claim",
    "policy score claim"
  ]
}
```

- [ ] **Step 4: Commit S0 documentation and probe**

Run:

```bash
git add tools/labutopia_fluid/inspect_usd_particles.py docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_scope_freeze_20260707.json docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_schema_probe_20260707.json
git commit -m "docs: freeze true fluid spike scope"
```

---

### Task 2: S1 Standalone Particle Runtime Smoke

**Files:**
- Create: `tools/labutopia_fluid/run_standalone_particle_smoke.py`
- Create: `assets/chemistry_lab/lab_001_fluid_spike/standalone_particle_smoke.usda`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s1_<slug>_<yyyymmdd>.json`

- [ ] **Step 1: Build a minimal standalone smoke scene**

The scene must include:

```text
/World/PhysicsScene with GPU dynamics intended
/World/ParticleSystem type=PhysxParticleSystem
/World/ParticleSet type=Points
/World/Looks/Blue_Glass or local basic transparent material
ground plane or simple static collider
one review camera
```

Use `lab_003/clock.usd` particle attributes as a reference, but reduce particle
count for first smoke:

```text
particle_count=256
particleContactOffset=0.005
isosurfaceEnabled=false
```

- [ ] **Step 2: Run with GPU backend**

Run:

```bash
python main.py --config-dir config --config-name level1_pour --backend gpu --headless --no-video
```

If this command cannot run the standalone scene, stop and create a narrower
runner command in `tools/labutopia_fluid/run_standalone_particle_smoke.py`.

- [ ] **Step 3: Record runtime smoke artifacts**

Required artifacts:

```text
runtime_smoke_summary.json
particle_readback_trace.jsonl
physics_scene_settings.json
initial_frame.png
mid_frame.png
terminal_frame.png
server.stdout.txt
server.stderr.txt
```

S1 pass:

```text
gpu_dynamics_enabled=true
particle_count_initial > 0
particle_count_final >= 0.95 * particle_count_initial
nan_count=0
readback_available=true
```

S1 stop:

```text
GPU_DYNAMICS_DISABLED
PARTICLE_SCHEMA_UNSUPPORTED
RUNTIME_CRASH
READBACK_UNAVAILABLE
```

---

### Task 3: S2 Beaker Collider Smoke Matrix

**Files:**
- Create: `tools/labutopia_fluid/run_beaker_collider_smoke.py`
- Create: `assets/chemistry_lab/lab_001_fluid_spike/colliders/*.usda`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_<yyyymmdd>.json`

- [ ] **Step 1: Implement collider variants**

The matrix must include these variants:

| ID | Collider | Required setup |
|---|---|---|
| C0 | Segmented box/wall proxy | Floor + 8/12/16 thin wall boxes, no top cap; first positive-control baseline |
| C1 | Simplified thick-wall open cup proxy | Low-poly thick open cup with explicit bottom and inner/outer wall |
| C2 | Segmented convex wall pieces | Curved wall approximated by convex panels, avoiding a single sealing hull |
| C3 | SDF tri-mesh open beaker | Open concave mesh with recorded SDF resolution/subgrid settings |
| C4 | Native `beaker2/mesh` `convexDecomposition` | Reference original mesh and record current collision attrs |
| C5 | Custom cylinder / analytic negative control | Expected unsupported or poor GPU-particle collision; never promote directly |

- [ ] **Step 2: Run static hold smoke for each variant**

For every variant:

```text
seed particle_count in source container
step 240 frames
record final particle counts by region
record particle AABB and centroid every 30 frames
record all PhysX collision/cooking/GPU warnings
save initial/mid/terminal frames
save collision overlay screenshots for top and side views
```

The region definitions must be stable and written to the manifest:

```json
{
  "source_region": "axis-aligned or collider-local box enclosing source beaker interior",
  "target_region": "axis-aligned or collider-local box enclosing target beaker interior",
  "spill_region": "tabletop/world area outside source and target"
}
```

- [ ] **Step 3: Classify each collider**

Use these exact classifications:

```text
PASS_SOURCE_HOLD
FAIL_CONTAINER_SEALED
FAIL_CONTAINER_LEAK
FAIL_NATIVE_CONVEX_INTERIOR_NOT_USABLE
FAIL_GPU_COLLIDER_UNSUPPORTED
FAIL_CPU_COLLISION_FALLBACK
FAIL_PARTICLE_EXPLOSION
FAIL_READBACK_UNAVAILABLE
FAIL_PERF_BUDGET_EXCEEDED
```

S2 can proceed to S3 if at least one collider has:

```text
source_retention_fraction >= 0.95
particle_count_final_fraction >= 0.95
below_table_count == 0
tail_leak_rate_fraction_per_second < 0.02
cpu_collision_fallback_detected=false
nan_count=0
```

- [ ] **Step 4: Write S2 review manifest**

The manifest must rank variants:

```json
{
  "best_for_s3": ["C0", "C1", "C2"],
  "native_beaker_status": "PASS_SOURCE_HOLD|...",
  "negative_control_status": "FAIL_GPU_COLLIDER_UNSUPPORTED|...",
  "s2_status": "GO_NEXT|STOP_WITH_EVIDENCE",
  "reason": "..."
}
```

---

### Task 4: S3 Kinematic Pour Rig Matrix

**Files:**
- Create: `tools/labutopia_fluid/run_kinematic_pour_rig.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s3_kinematic_pour_<yyyymmdd>.json`

- [ ] **Step 1: Select S2 variants**

Run S3 on every S2 variant that passed `PASS_SOURCE_HOLD`. If no variant passed,
run S3 only on the top two variants by retention fraction and mark the stage as
`STOP_WITH_EVIDENCE`.

- [ ] **Step 2: Run controlled pour schedule**

For each selected collider:

```text
settle 120 frames
tilt to 30 deg over 60 frames
hold 30 deg for 60 frames
tilt to 60 deg over 60 frames
hold 60 deg for 60 frames
tilt to 90 deg over 60 frames
hold 90 deg for 120 frames
return to 0 deg over 60 frames
```

Do not teleport the source beaker. The source beaker must rotate with continuous
kinematic motion so the run can expose `KINEMATIC_COUPLING_FAIL` separately from
static containment failures.

Run three speed profiles:

```text
slow
medium
fast
```

Run at least two particle counts:

```text
small=256
medium=1024
```

Add `native_like=2941` only after small and medium are stable.

- [ ] **Step 3: Record kinematic pour metrics**

Required readback fields:

```text
particles_total
particles_in_source
particles_in_target
particles_spilled
source_fraction
target_fraction
spill_fraction
particle_count_final_fraction
centroid
AABB
settled_velocity_proxy
nan_count
```

S3 pass for a variant:

```text
particle_count_final_fraction >= 0.90
source_fraction drops by >= 0.30 during tilt
target_fraction reaches >= 0.10
nan_count=0
terminal render visually agrees with particle readback direction
```

- [ ] **Step 4: Stop or promote**

If S3 passes, promote exactly one collider to S4 and record why.

If S3 fails for all variants, stop with evidence and do not move to robot replay.
The manifest must include a ranked failure table and the next recommended
intervention.

---

### Task 5: S4 LabUtopia `level1_pour` Expert Replay

**Files:**
- Modify: `config/level1_pour_fluid_spike.yaml`
- Modify: `tasks/pickpour_task.py`
- Create: `tools/labutopia_fluid/build_level1_pour_fluid_overlay.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s4_level1_pour_<yyyymmdd>.json`

- [ ] **Step 1: Create fluid-specific config**

Create `config/level1_pour_fluid_spike.yaml` by copying `config/level1_pour.yaml`
and changing only:

```yaml
name: Level1_pour_fluid_spike
usd_path: "assets/chemistry_lab/lab_001_fluid_spike/lab_001_fluid_spike.usda"
task:
  fluid_spike:
    enabled: true
    source_path: "/World/beaker2"
    target_path: "/World/beaker1"
    particle_count: 1024
    collider_variant: "selected_from_s3"
```

- [ ] **Step 2: Add opt-in particle seeding after reset**

Only if `cfg.task.fluid_spike.enabled` is true, seed or transform the
`ParticleSet` after `PickPourTask.reset()` places `/World/beaker2` and
randomizes `/World/beaker1`.

Do not alter normal `level1_pour` behavior.

- [ ] **Step 3: Replay expert motion**

Run a bounded headless replay using GPU backend:

```bash
python main.py \
  --config-dir config \
  --config-name level1_pour_fluid_spike \
  --backend gpu \
  --headless \
  --video-dir artifacts/videos/fluid_spike/<run_id>
```

S4 pass:

```text
existing pick/pour controller completes
particle readback shows meaningful motion
no particle explosion/disappearance
terminal render and readback agree
```

S4 stop:

```text
ROBOT_MOTION_TUNNELING
PARTICLE_INSTABILITY_UNDER_KINEMATIC_SOURCE
EXPERT_TRAJECTORY_NO_LONGER_COMPLETES
READBACK_LOST_IN_TASK_RUNTIME
```

---

### Task 6: S5 EBench / IsaacSim41 Consumer Gate

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s5_ebench_consumer_<yyyymmdd>.json`
- Update GenManip/EBench configs only in the GenManip repo after a separate release review.

- [ ] **Step 1: Perform no-score consumer preflight**

Preflight must prove:

```text
fluid wrapper resolves
ParticleSystem exists after composition
ParticleSet exists after reset
particle count is nonzero
GPU dynamics setting is visible
selected collider variant exists
```

- [ ] **Step 2: Run exactly one no-score smoke**

Run one bounded reset/step smoke. Do not claim score.

Required artifacts:

```text
consumer_preflight.json
resolved_assets_root.txt
usd_reference_closure.json
server.stdout.txt
server.stderr.txt
schema_loss_diff.json
```

S5 pass:

```text
consumer preserves fluid schema and runtime can step at least once
```

---

### Task 7: S6 Metric / Readback and S7 Repeatability / Performance

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s6_s7_<yyyymmdd>.json`
- Create: `tools/labutopia_fluid/review_fluid_spike_artifacts.py`

- [ ] **Step 1: Define particle metric contract**

The metric cannot use particle contact reports. It must use particle readback:

```json
{
  "particles_total": 1024,
  "particles_in_source": 512,
  "particles_in_target": 256,
  "particles_spilled": 256,
  "target_fraction": 0.25,
  "source_fraction": 0.5,
  "spill_fraction": 0.25,
  "centroid": [0.0, 0.0, 0.0],
  "aabb_min": [0.0, 0.0, 0.0],
  "aabb_max": [0.0, 0.0, 0.0]
}
```

- [ ] **Step 2: Run three repeatability trials**

Run either:

```text
same seed x 3
```

or:

```text
three declared seeds
```

Record:

```text
initial_state_hash
terminal_state_hash
particle count
target_fraction
spill_fraction
failure class
episode wall time
GPU memory
```

- [ ] **Step 3: Final claim review**

Write `score_claim_review.json` with:

```json
{
  "true_fluid_claim_allowed": true,
  "score_claim_allowed": false,
  "policy_score_claim_allowed": false,
  "official_leaderboard_claim_allowed": false,
  "reason": "True fluid runtime/readback passed, but benchmark score contract is not yet signed"
}
```

Only set `score_claim_allowed=true` if authoritative `result_info.json`,
`metric_trace.jsonl`, particle readback, and terminal render all come from the
same EBench run and agree.

---

## Self-Review Checklist

- S2/S3 run more than one collider path and include negative controls.
- The native `lab_001` asset is never edited in place.
- No visual-only liquid artifact can satisfy true fluid criteria.
- `Expert Oracle Score` claims remain isolated.
- Contact reports are not used as the liquid success metric.
- Every live attempt has `allowed_claims` and `blocked_claims`.
- Failure can stop the spike without being treated as project failure.

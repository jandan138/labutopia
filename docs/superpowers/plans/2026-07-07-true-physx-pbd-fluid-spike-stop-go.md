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
tools/labutopia_fluid/probe_isaacsim41_fluid_schema.py
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

## S0 Execution Status

S0 closed on 2026-07-07 with `GO_NEXT`. The conclusion is deliberately narrow:
the selected IsaacSim41 / EBench runtime can load the PhysX particle schemas after
`SimulationApp` startup, and the selected machine exposes an RTX 4090 GPU. This
releases S1 standalone particle runtime smoke, but it does not release any claim
that `level1_pour` already has true fluid or that EBench has stepped/scored it.

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_scope_freeze_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_schema_probe_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_isaacsim41_app_schema_probe_20260707.json
```

Implementation checkpoint:

```text
tools/labutopia_fluid/inspect_usd_particles.py
tools/labutopia_fluid/probe_isaacsim41_fluid_schema.py
```

Asset finding: `assets/chemistry_lab/lab_001/lab_001.usd` has no authored
`PhysxParticleSystem` / `ParticleSet`; `assets/chemistry_lab/lab_003/clock.usd`
and `assets/chemistry_lab/lab_003/lab_003.usd` provide local particle templates.

## S1 Execution Status

S1 closed on 2026-07-07 with `GO_NEXT`. The selected IsaacSim41 runtime stepped
the standalone particle scene for 120 frames with GPU dynamics enabled and USD
particle readback enabled. This releases S2 beaker collider smoke. It does not
release any `level1_pour`, EBench consumer, metric/readback, score, policy, or
leaderboard claim.

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s1_standalone_particle_smoke_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/runtime_smoke_summary.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/particle_readback_trace.jsonl
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/physics_scene_settings.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s1_visual_review_20260707.json
```

Pass values:

```text
gpu_dynamics_enabled=true
particle_count_initial=256
particle_count_final=256
particle_count_final_fraction=1.0
nan_count=0
readback_available=true
runtime_step_executed=true
```

Implementation checkpoint:

```text
tools/labutopia_fluid/run_standalone_particle_smoke.py
tests/test_fluid_particle_smoke.py
assets/chemistry_lab/lab_001_fluid_spike/standalone_particle_smoke.usda
```

Visual boundary: `initial_frame.png`, `mid_frame.png`, and `terminal_frame.png`
are diagnostic x-z projections generated from particle readback. They are valid
S1 evidence for particle existence and motion, but they are not product camera
renders or visual/material parity evidence. The first camera-RGB attempt produced
near-black frames; the runner now detects unusable camera frames and falls back to
diagnostic projections.
Independent visual review of the final diagnostic projection frames is `PASS`.

## S2 Execution Status

S2 closed on 2026-07-07 with `STOP_WITH_EVIDENCE`. The selected IsaacSim41
runtime ran the required C0-C5 beaker collider matrix for 240 frames per variant
with GPU dynamics and USD particle readback enabled. All variants produced
finite particle readback and particle motion, but no non-negative-control
collider met the S3 release criteria.

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_runtime_warning_scan_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_visual_review_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2_beaker_collider_matrix_20260707_001/
```

Implementation checkpoint:

```text
tools/labutopia_fluid/run_beaker_collider_smoke.py
tests/test_fluid_beaker_collider_smoke.py
assets/chemistry_lab/lab_001_fluid_spike/colliders/
```

Result matrix:

```text
C0 FAIL_CONTAINER_LEAK source_retention_fraction=0.6953125 spill_count=66 below_table_count=12
C1 FAIL_CONTAINER_LEAK source_retention_fraction=0.78125 spill_count=40 below_table_count=16
C2 FAIL_CONTAINER_LEAK source_retention_fraction=0.828125 spill_count=32 below_table_count=12
C3 FAIL_CONTAINER_LEAK source_retention_fraction=0.0 spill_count=0 below_table_count=256
C4 FAIL_NATIVE_CONVEX_INTERIOR_NOT_USABLE source_retention_fraction=0.0 spill_count=0 below_table_count=256
C5 FAIL_CONTAINER_LEAK source_retention_fraction=0.0 spill_count=0 below_table_count=256
best_for_s3=[]
```

Runtime warning scan found no `CPU collision fallback`, `GPU collider
unsupported`, or PhysX error. C4 emits native mesh `material:binding` scope
warnings because the referenced mesh points to `/World/Looks/OmniSurface_Glass`
outside the referenced prim scope; this is recorded as visual-material reference
scope noise, not as the collider failure root cause.

Visual boundary: S2 PNGs are diagnostic readback projections, not product camera
renders. The first projection version clipped below-table particles for C3/C4;
the final `v2_dynamic_z_shows_below_table_leaks` overlays show below-table leak
particles in red. Independent visual review of the final diagnostic overlays is
`PASS`.

S2 does not release S3. Before S3 can run, an S2 follow-up must produce at least
one non-negative-control `PASS_SOURCE_HOLD` collider satisfying:

```text
source_retention_fraction >= 0.95
particle_count_final_fraction >= 0.95
outside_source_count == 0
target_count == 0
spill_count == 0
below_table_count == 0
tail_leak_rate_fraction_per_second < 0.02
cpu_collision_fallback_detected=false
nan_count=0
```

## S2F Research Basis and Follow-up Plan

S2F exists because S2 answered the static hold question with
`STOP_WITH_EVIDENCE`: C0-C5 all produced particle readback and motion, but none
held particles well enough to release S3. The follow-up is not blind tuning. It
is a bounded collider/particle-contact investigation based on official PhysX PBD
particle behavior, local Isaac Sim API evidence, NVIDIA forum experience, and the
S2 result matrix.

Research basis:

```text
Official/local API facts:
- PhysX particle systems are GPU-accelerated PBD particles and can simulate fluids.
- CPU simulation of particles is not supported; GPU dynamics must stay enabled.
- SingleParticleSystem exposes contact_offset, rest_offset, particle_contact_offset,
  enable_ccd, max_velocity, max_depenetration_velocity, solver iterations, and
  non_particle_collision_enabled.
- particleUtils can author fluid=True Points/PointInstancer particle sets.
- PhysX mesh collision utilities support approximation modes including sdf.

Forum/field experience:
- Liquid particle leak-through-collider cases are often sensitive to particle
  contact offset and collider contact offset.
- Hand-pouring style demos can work at low acceleration but become unstable under
  fast motion; max_velocity can reduce tunneling-like behavior, but may create
  non-physical sticky liquid.

Project inference:
- Native render mesh is not automatically a fluid-safe collider.
- Convex decomposition can be acceptable for rigid-body contact while still
  failing as a particle container for concave open-cup interiors.
- Product camera/video can wait; S2F success must be particle readback first.
```

References:

```text
https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/particles/particles.html
https://forums.developer.nvidia.com/t/liquid-particle-sampler-is-passing-through-the-collider/248815
/isaac-sim/exts/isaacsim.core.prims/isaacsim/core/prims/impl/single_particle_system.py
/isaac-sim/exts/isaacsim.core.prims/isaacsim/core/prims/impl/particle_system.py
/isaac-sim/extsPhysics/omni.physx/omni/physx/scripts/particleUtils.py
/isaac-sim/extsPhysics/omni.physx/omni/physx/scripts/utils.py
```

S2F stage split:

| Stage | Goal | Work | Release condition |
|---|---|---|---|
| S2F-0 Evidence Freeze | Keep S2 as baseline | Freeze C0-C5 result matrix, warning scan, visual review, and `s2_no_outside_source_v2` contract. | No S3 release; baseline copied into S2F manifest. |
| S2F-1 C2 Proxy Sweep | Repair closest failed candidate first | Sweep C2 wall thickness, panel count, bottom seal overlap, particle spawn clearance, collider `contactOffset/restOffset`, and particle `particle_contact_offset/fluid_rest_offset`. | At least one C2-derived variant has `outside_source_count==0`, `spill_count==0`, `below_table_count==0`. |
| S2F-2 Velocity / Contact Offset Isolation | Separate geometry leak from tuning leak | Test `initial_radial_velocity`, `particle_contact_offset`, `fluid_rest_offset`, `solid_rest_offset`, `enable_ccd`, `max_velocity`, and `max_depenetration_velocity` only after geometry/contact candidates exist. | Any velocity cap must be recorded; sticky/non-physical workaround cannot alone release S3. |
| S2F-3 C3 SDF Sweep | Test concave mesh route | Sweep SDF resolution, subgrid, margin/narrow band, remeshing, mesh normals, and bottom fan closure. | SDF variant passes static hold without perf/cooking failure. |
| S2F-4 C4 Native Isolation | Decide if native beaker can be salvaged | Compare native `beaker2/mesh` as convexDecomposition, SDF, and proxy wrapper; isolate pose/material warnings from collider failure. | Either native-derived collider passes, or manifest signs `NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER`. |
| S2F-5 Promotion Review | Decide S3 entry | Re-run promoted candidates across 3 seeds and 2 particle counts: 256 and 1024; write `fluid_spike_s2f_collider_followup_<yyyymmdd>.json` with ranked candidates, warnings, images, traces, and claim guard. | Exactly one or more non-negative-control variants in `best_for_s3`, otherwise remain `STOP_WITH_EVIDENCE`. |

S2F candidate naming:

```text
C2A_* = C2-derived proxy/contact/gap variants
C3A_* = C3 SDF/cooking variants
C4A_* = C4 native mesh isolation variants
```

Current status:

```text
S2F0_BASELINE_FREEZE=COMPLETE
S2F1_C2_PROXY_SWEEP=COMPLETE_STOP_WITH_EVIDENCE
S2F2_VELOCITY_CONTACT_OFFSET=COMPLETE_GO_NEXT
S2F3_C3_SDF_SWEEP=PENDING
S2F4_C4_NATIVE_MESH_ISOLATION=PENDING
S2F5_PROMOTION_REVIEW=NEXT
S2F0 result manifest:
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json
S2F1 result manifest:
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_c2_proxy_sweep_20260707.json
S2F2 result manifest:
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f2_velocity_contact_offset_20260708.json
```

Do not repeat S2F0 unless the S2 collider matrix is intentionally regenerated.
All later follow-up evidence must cite this baseline freeze manifest.

S2F1 closed on 2026-07-07 with `STOP_WITH_EVIDENCE`. The run completed the
bounded 12-candidate C2A segmented proxy sweep in the IsaacSim41 / EBench target
runtime. The result is an improvement over the S2 C2 baseline, but not a release
for S3. `C2A_005` and `C2A_009` both reached
`source_retention_fraction=0.9921875`, but both still had
`outside_source_count=2` and `spill_count=2`. The strict
`s2_no_outside_source_v2` contract requires zero outside-source, zero spill,
zero target, and zero below-table particles. Therefore:

```text
best_for_s3=[]
s3_kinematic_pour_released=false
near_pass_for_s2f2=["C2A_005", "C2A_009", "C2A_007"]
```

S2F2 closed on 2026-07-08 with `GO_NEXT`. It focused only on
`C2A_005`, `C2A_009`, and `C2A_007`, fixed the proxy geometry, and isolated
velocity/contact/CCD/max-velocity variables. Only `C2A_009_S2F2_VEL020` passed
the static source-hold contract without non-physical damping:

```text
best_for_s2f5=["C2A_009_S2F2_VEL020"]
best_for_s3=[]
s2f2_root_cause_classification=VELOCITY_INITIAL_LAYOUT_COUPLED_SENSITIVITY
s2f2_root_cause_confidence=COUPLED_DIAGNOSTIC
s2f5_promotion_review_next=true
s3_kinematic_pour_released=false
```

Do not move directly to S3. `C2A_009_S2F2_VEL020` must first pass S2F5
promotion review across multiple seeds and particle counts. Because the diagnosis
is coupled with post-reset initial layout variation, S2F5 must first retest
initial-layout hash stability before it can treat the candidate as promotable.

S2F required evidence per variant:

```text
variant_summary.json
particle_readback_trace.jsonl
physics_scene_settings.json
runtime_warning_scan.json
initial_frame.png
mid_frame.png
terminal_frame.png
top_collision_overlay.png
side_collision_overlay.png
source/outside/spill/below-table counts
all authored collider and particle offsets
```

S2F stop rules:

```text
If C2A cannot reach zero outside-source particles after bounded sweep, do not
continue tuning C2 indefinitely; move to C3A/C4A and record C2A_BOUND_EXHAUSTED.

If all C2A/C3A/C4A variants fail, keep best_for_s3=[] and do not run S3.

If a variant only works by extreme max_velocity damping or non-physical sticky
settings, classify it as FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE.
```

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
- Create: `tools/labutopia_fluid/probe_isaacsim41_fluid_schema.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_scope_freeze_20260707.json`
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`

- [x] **Step 1: Write `inspect_usd_particles.py`**

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

- [x] **Step 2: Run S0 schema probe**

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

- [x] **Step 2B: Run IsaacSim41 `SimulationApp` schema probe**

Run:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES PYTHONNOUSERSITE=1 \
  /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  tools/labutopia_fluid/probe_isaacsim41_fluid_schema.py \
  --out docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_isaacsim41_app_schema_probe_20260707.json
```

Expected:

```text
pxr.PhysxSchema=true after SimulationApp startup
omni.physx=true after SimulationApp startup
PhysxParticleSystem=true
PhysxParticleSetAPI=true
PhysxParticleAPI=true
PhysxPBDMaterialAPI=true
gpu_visible=true
runtime_step_executed=false
```

- [x] **Step 3: Write S0 manifest**

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
  "true_fluid_definition": "PhysxSceneAPI with GPU dynamics enabled + PhysxParticleSystem + ParticleSet + PBD material + runtime step/fetch + particle readback",
  "not_true_fluid": [
    "mesh_only_liquid",
    "shader_only_water",
    "offline_video",
    "rgb_only_success"
  ],
  "allowed_claims": [
    "true fluid spike scope is frozen",
    "level1_pour currently has no particle system",
    "lab_003 clock.usd is the local particle template",
    "S1 standalone particle runtime smoke may proceed"
  ],
  "blocked_claims": [
    "level1_pour has true fluid today",
    "Expert Oracle Score includes fluid",
    "official leaderboard claim",
    "policy score claim"
  ]
}
```

- [x] **Step 4: Commit S0 documentation and probe**

Run:

```bash
git add tools/labutopia_fluid/inspect_usd_particles.py tools/labutopia_fluid/probe_isaacsim41_fluid_schema.py docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_scope_freeze_20260707.json docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_schema_probe_20260707.json docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_isaacsim41_app_schema_probe_20260707.json
git commit -m "docs: freeze true fluid spike scope"
```

---

### Task 2: S1 Standalone Particle Runtime Smoke

**Files:**
- Create: `tools/labutopia_fluid/run_standalone_particle_smoke.py`
- Create: `assets/chemistry_lab/lab_001_fluid_spike/standalone_particle_smoke.usda`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s1_<slug>_<yyyymmdd>.json`

- [x] **Step 1: Build a minimal standalone smoke scene**

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

- [x] **Step 2: Run with GPU backend**

Run:

```bash
python main.py --config-dir config --config-name level1_pour --backend gpu --headless --no-video
```

If this command cannot run the standalone scene, stop and create a narrower
runner command in `tools/labutopia_fluid/run_standalone_particle_smoke.py`.

Actual S1 used the narrower standalone runner because the plan command targets
LabUtopia task execution, while S1 needs an isolated PhysX/PBD particle positive
control:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 \
  /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  tools/labutopia_fluid/run_standalone_particle_smoke.py \
  --artifact-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001 \
  --scene-path assets/chemistry_lab/lab_001_fluid_spike/standalone_particle_smoke.usda \
  --manifest-path docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s1_standalone_particle_smoke_20260707.json \
  --particle-count 256 \
  --steps 120 \
  --width 512 \
  --height 512 \
  --headless
```

- [x] **Step 3: Record runtime smoke artifacts**

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

- [x] **Step 1: Implement collider variants**

The matrix must include these variants:

| ID | Collider | Required setup |
|---|---|---|
| C0 | Segmented box/wall proxy | Floor + 8/12/16 thin wall boxes, no top cap; first positive-control baseline |
| C1 | Simplified thick-wall open cup proxy | Low-poly thick open cup with explicit bottom and inner/outer wall |
| C2 | Segmented convex wall pieces | Curved wall approximated by convex panels, avoiding a single sealing hull |
| C3 | SDF tri-mesh open beaker | Open concave mesh with recorded SDF resolution/subgrid settings |
| C4 | Native `beaker2/mesh` `convexDecomposition` | Reference original mesh and record current collision attrs |
| C5 | Custom cylinder / analytic negative control | Expected unsupported or poor GPU-particle collision; never promote directly |

- [x] **Step 2: Run static hold smoke for each variant**

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

- [x] **Step 3: Classify each collider**

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
outside_source_count == 0
target_count == 0
spill_count == 0
below_table_count == 0
tail_leak_rate_fraction_per_second < 0.02
cpu_collision_fallback_detected=false
nan_count=0
```

- [x] **Step 4: Write S2 review manifest**

The manifest must rank variants:

```json
{
  "best_for_s3": [],
  "native_beaker_status": "FAIL_NATIVE_CONVEX_INTERIOR_NOT_USABLE",
  "negative_control_status": "FAIL_CONTAINER_LEAK",
  "s2_status": "STOP_WITH_EVIDENCE",
  "reason": "no_non_negative_control_variant_passed"
}
```

S2 final state: no variant can proceed to S3 yet. C2 is the closest failed
candidate and should be the first geometry/parameter follow-up route.

---

### Task 3A: S2 Collider Follow-up Recovery

**Files:**
- Create: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
- Create: `tests/test_fluid_beaker_collider_followup_sweep.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_plan_20260707.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_<phase>_<yyyymmdd>.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2_followup_<phase>_<yyyymmdd>_<NNN>/`
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

S2F is required before Task 4. Do not run S3 until this task writes a promotion
review manifest with non-empty `best_for_s3`.

- [x] **Step 1: Freeze S2F baseline contract**

Create:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_plan_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json
```

Required fields:

```json
{
  "schema_version": 1,
  "manifest_type": "true_physx_pbd_fluid_spike_s2_followup_plan",
  "stage": "S2F_COLLIDER_FOLLOW_UP_PLAN",
  "parent_s2_manifest": "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json",
  "status": "PLAN_READY",
  "s3_kinematic_pour_released": false,
  "best_for_s3": [],
  "contract_version": "s2_no_outside_source_v2",
  "baseline_closest_failed_candidate": "C2",
  "baseline_c2": {
    "classification": "FAIL_CONTAINER_LEAK",
    "source_retention_fraction": 0.828125,
    "outside_source_count": 44,
    "spill_count": 32,
    "below_table_count": 12
  },
  "baseline_phase": "S2F0_BASELINE_FREEZE",
  "required_pass_criteria": {
    "source_retention_fraction": ">=0.95",
    "particle_count_final_fraction": ">=0.95",
    "outside_source_count": 0,
    "target_count": 0,
    "spill_count": 0,
    "below_table_count": 0,
    "tail_leak_rate_fraction_per_second": "<0.02",
    "cpu_collision_fallback_detected": false,
    "gpu_collider_unsupported": false,
    "nan_count": 0
  },
  "phase_order": [
    "S2F0_BASELINE_FREEZE",
    "S2F1_C2_PROXY_SWEEP",
    "S2F2_VELOCITY_CONTACT_OFFSET",
    "S2F3_C3_SDF_SWEEP",
    "S2F4_C4_NATIVE_MESH_ISOLATION",
    "S2F5_PROMOTION_REVIEW"
  ]
}
```

Result: `fluid_spike_s2f0_baseline_freeze_20260707.json` freezes the S2
collider matrix, runtime warning scan, visual review, strict
`s2_no_outside_source_v2` contract, C2 closest-failed metrics, and the
`best_for_s3=[]` / `s3_kinematic_pour_released=false` guard.

- [x] **Step 2: Write failing tests for follow-up sweep planning helpers**

Create `tests/test_fluid_beaker_collider_followup_sweep.py` with tests for:

```python
def test_followup_matrix_names_do_not_collide_with_s2_baseline():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import followup_phase_specs

    phases = followup_phase_specs()
    assert list(phases) == [
        "S2F0_BASELINE_FREEZE",
        "S2F1_C2_PROXY_SWEEP",
        "S2F2_VELOCITY_CONTACT_OFFSET",
        "S2F3_C3_SDF_SWEEP",
        "S2F4_C4_NATIVE_MESH_ISOLATION",
        "S2F5_PROMOTION_REVIEW",
    ]
    assert phases["S2F0_BASELINE_FREEZE"]["candidate_prefix"] == "S2"
    assert phases["S2F1_C2_PROXY_SWEEP"]["candidate_prefix"] == "C2A"
    assert phases["S2F3_C3_SDF_SWEEP"]["candidate_prefix"] == "C3A"
    assert phases["S2F4_C4_NATIVE_MESH_ISOLATION"]["candidate_prefix"] == "C4A"


def test_followup_pass_criteria_require_zero_outside_source():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import classify_followup_candidate

    result = classify_followup_candidate(
        candidate_id="C2A_001",
        source_retention_fraction=1.0,
        particle_count_final_fraction=1.0,
        outside_source_count=1,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        nan_count=0,
        non_physical_parameter_dependence=False,
    )
    assert result["classification"] == "FAIL_CONTAINER_LEAK"
    assert result["pass_criteria"]["outside_source_count_eq_zero"] is False
```

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py
```

Expected before implementation: import failure.

- [x] **Step 3: Implement C2 proxy sweep generator**

Create `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py` with:

```text
followup_phase_specs()
build_c2_proxy_sweep()
build_velocity_contact_offset_sweep()
classify_followup_candidate()
rank_followup_candidates()
write_followup_manifest()
```

The first bounded C2A grid should cover:

```text
panel_count: 24, 32, 48
wall_thickness: 0.010, 0.014, 0.018
bottom_overlap: 0.000, 0.003, 0.006
particle_contact_offset: 0.0045, 0.0060, 0.0075
collider_contact_offset: 0.002, 0.004, 0.006
collider_rest_offset: -0.001, 0.000
initial_radial_velocity: 0.02, 0.04, 0.08
```

Bound the first live batch to 12 candidates selected by risk coverage, not the
full Cartesian product. Write the candidate list into the S2F1 manifest before
launching runtime.

- [x] **Step 4: Run S2F1 C2 proxy sweep**

Run:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 \
  /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  tools/labutopia_fluid/run_beaker_collider_followup_sweep.py \
  --phase S2F1_C2_PROXY_SWEEP \
  --parent-manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json \
  --artifact-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2_followup_c2_proxy_sweep_20260707_001 \
  --manifest-path docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_c2_proxy_sweep_20260707.json \
  --steps 240 \
  --headless
```

Do not release S3 from this phase unless at least one C2A candidate satisfies
all S2F pass criteria.

Actual run used the same target IsaacSim41 / EBench conda runtime and included
the frozen S2F0 baseline manifest:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 \
  /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  tools/labutopia_fluid/run_beaker_collider_followup_sweep.py \
  --phase S2F1_C2_PROXY_SWEEP \
  --parent-manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json \
  --baseline-freeze-manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json \
  --artifact-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2_followup_c2_proxy_sweep_20260707_001 \
  --manifest-path docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_c2_proxy_sweep_20260707.json \
  --steps 240 \
  --headless
```

S2F1 result:

```text
status=STOP_WITH_EVIDENCE
reason=no_c2a_candidate_passed
best_for_s3=[]
runtime_warning_scan.blocking_runtime_warning_detected=false
near_pass_for_s2f2=["C2A_005", "C2A_009", "C2A_007"]
C2A_005 source_retention_fraction=0.9921875 outside_source_count=2 spill_count=2 below_table_count=0
C2A_009 source_retention_fraction=0.9921875 outside_source_count=2 spill_count=2 below_table_count=0
C2A_007 source_retention_fraction=0.9765625 outside_source_count=6 spill_count=3 below_table_count=3
```

The live runner wrote all 12 candidate artifact folders under:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2_followup_c2_proxy_sweep_20260707_001/
```

Each candidate has `variant_summary.json`, particle readback trace, physics scene
settings, diagnostic frames, and collision overlays. A final
`--summarize-existing` pass rebuilt the manifest from the already generated
candidate artifacts after fixing manifest finalization order around
`SimulationApp.close()`.

- [x] **Step 5: Run S2F2 velocity/contact-offset isolation**

Only run this after S2F1 shows at least one near-pass candidate or a clear
geometry failure. The goal is to separate geometry leak from particle/contact
parameter sensitivity.

Required variants:

```text
same geometry, lower initial_radial_velocity
same geometry, higher particle_contact_offset
same geometry, collider contact/rest offset pair sweep
same geometry, enable_ccd on/off if supported by runtime
same geometry, max_velocity guardrail
```

Classify any success that depends only on extreme `max_velocity` damping as:

```text
FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE
```

Result on 2026-07-08:

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f2_velocity_contact_offset_20260708.json
artifact_dir=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f2_velocity_contact_offset_20260708_001/
candidate_count=18
result_count=18
status=GO_NEXT
best_for_s2f5=["C2A_009_S2F2_VEL020"]
best_for_s3=[]
s2f5_promotion_review_next=true
s3_kinematic_pour_released=false
s2f2_diagnosis.conclusion=VELOCITY_INITIAL_LAYOUT_COUPLED_SENSITIVITY
s2f2_diagnosis.root_cause_confidence=COUPLED_DIAGNOSTIC
next_stage.promotion_caveat=COUPLED_DIAGNOSTIC_REQUIRES_INITIAL_LAYOUT_RETEST
next_stage.requires_initial_layout_hash_stability_check=true
runtime_warning_gate.passed=true
```

Promotion candidate:

```text
C2A_009_S2F2_VEL020
source_retention_fraction=1.0
outside_source_count=0
spill_count=0
below_table_count=0
target_count=0
initial_radial_velocity=0.02
```

Important exclusions:

```text
C2A_009_S2F2_VMAX010 reached zero leak counts but is
FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE because it relies on a max_velocity
guardrail. It is diagnostic-only and not promotable.

C2A_007_S2F2_PCO045 reached outside_source_count=1 and spill_count=1, but the
contract requires zero, so it remains FAIL_CONTAINER_LEAK.

Particle/contact-offset variants did not explain the leak cleanly; several
contact/collider-offset variants worsened leakage.

s2f2_initial_layout_hash_audit shows post-reset hash variation for C2A_005,
C2A_007, and C2A_009. Authored spawn positions were pinned, but PhysX reset /
settle can still differ when contact offsets change. Treat contact-offset results
as diagnostic evidence, not release evidence.
```

PM interpretation: S2F2 found one static-hold promotion-review candidate. It
does not release S3 or true-fluid `level1_pour`; it releases S2F5 only.

- [ ] **Step 6: Run S2F3 C3 SDF sweep**

Run SDF as its own phase, not mixed with C2A. Required variables:

```text
sdf_resolution: 64, 96, 128
sdf_subgrid_resolution: 4, 8
sdf_margin: 0.002, 0.005
sdf_narrow_band_thickness: 0.01, 0.02
mesh bottom fan closure: on
normals/winding audit: pass
```

Stop S2F3 early if stdout/stderr scan finds CPU fallback, GPU unsupported, SDF
cooking error, or perf budget exceeded for every candidate.

- [ ] **Step 7: Run S2F4 C4 native mesh isolation**

Compare native-derived routes:

```text
C4A_convexDecomposition_reference_scope_closed
C4A_sdf_reference_scope_closed
C4A_native_render_mesh_plus_proxy_collision
```

The phase must separate three issues:

```text
material:binding reference-scope warning
native pose/scale/orientation mismatch
particle collider interior usability
```

If native-derived routes still fail, write:

```text
NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER
```

This is not a no-go for fluid overall; it only means native render mesh should be
wrapped by a fluid-safe physics proxy.

- [ ] **Step 8: Write S2F5 promotion review**

Create:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_promotion_review_20260707.json
```

Required fields:

```json
{
  "stage": "S2F5_PROMOTION_REVIEW",
  "status": "GO_NEXT|STOP_WITH_EVIDENCE",
  "best_for_s3": [],
  "s3_kinematic_pour_released": false,
  "ranked_candidates": [],
  "blocked_claims": [
    "S3 kinematic pour released without PASS_SOURCE_HOLD",
    "native beaker mesh is fluid-safe by default",
    "isosurface render equals physical success",
    "particle contact report can be used as score evidence"
  ]
}
```

Set `s3_kinematic_pour_released=true` only if `best_for_s3` is non-empty and
every promoted candidate has same-run particle readback, warning scan, and visual
diagnostic overlays.

- [ ] **Step 9: Update docs and commit S2F result**

Update:

```text
docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md
docs/labutopia_lab_poc/evidence_manifests/README.md
docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md
```

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py tests/test_fluid_beaker_collider_smoke.py
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_promotion_review_20260707.json
git diff --check
```

Commit:

```bash
git add tools/labutopia_fluid/run_beaker_collider_followup_sweep.py tests/test_fluid_beaker_collider_followup_sweep.py docs/labutopia_lab_poc docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md
git commit -m "feat: add fluid collider follow-up sweep"
```

---

### Task 4: S3 Kinematic Pour Rig Matrix

**Files:**
- Create: `tools/labutopia_fluid/run_kinematic_pour_rig.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s3_kinematic_pour_<yyyymmdd>.json`

- [ ] **Step 1: Select S2 variants**

Run S3 on every S2 variant that passed `PASS_SOURCE_HOLD`. If no variant passed,
do not run S3. Keep `best_for_s3=[]`, record `STOP_WITH_EVIDENCE`, and open a
narrow S2 collider follow-up first. Retention-fraction ranking may choose the
first follow-up candidate, but it must not release a failed collider into S3.

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

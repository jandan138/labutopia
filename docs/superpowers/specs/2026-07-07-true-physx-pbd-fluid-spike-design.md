# True PhysX/PBD Fluid Spike Design

Date: 2026-07-07

## Purpose

This spike answers one bounded question:

```text
Can LabUtopia `level1_pour` be extended with real PhysX/PBD particle fluid,
then carried far enough toward EBench / IsaacSim41 to expose the true blockers
with evidence?
```

The spike is allowed to fail. A useful failure is one that clearly identifies
whether the blocker is USD schema preservation, GPU dynamics, beaker collider
generation, particle stability, kinematic pouring, EBench consumer loading,
metric/readback, repeatability, or performance.

This is not a replacement for the current rigid/articulation `Expert Oracle
Score` line. It cannot claim policy score, official leaderboard readiness, or
general fluid benchmark readiness unless every declared gate passes with
same-run evidence.

## Current Evidence Boundary

`level1_pour` currently uses `assets/chemistry_lab/lab_001/lab_001.usd`:

```text
config/level1_pour.yaml:8
```

That stage has no authored or composed `PhysxParticleSystem`, `ParticleSet`,
`PhysxParticle`, `PhysxPBD`, `physxParticle`, or particle isosurface prims in
the local USD. The existing `PickPourTaskController` success check is still a
pose/action proxy: pick the beaker, move it near the target, rotate it past a
threshold, return it, and hold. It does not read liquid volume or particle
state.

The strongest local starting point is not `level1_pour`; it is
`level4_LiquidMixing`, which points to `assets/chemistry_lab/lab_003/clock.usd`:

```text
config/level4_LiquidMixing.yaml:7
```

That stage contains:

```text
/World/ParticleSystem type=PhysxParticleSystem
/World/ParticleSet type=Points
ParticleSet points=2941
particleContactOffset=0.005
physxParticleIsosurface:isosurfaceEnabled=false
material=/World/Looks/Blue_Glass
```

Historical Isaac logs prove PhysX recognized `/World/ParticleSet`, but also
record that particles require GPU dynamics. Therefore the current local evidence
proves particle assets exist and can be noticed by PhysX; it does not prove that
true GPU PBD fluid simulation already runs correctly.

## Official Capability Boundary

NVIDIA / Omniverse official docs establish these design constraints:

- Omni Physics has GPU-accelerated PBD particles for fluids and granular media:
  https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/particles/particles.html
- CPU particle simulation is not supported for this path; the spike must enable
  GPU dynamics.
- The required USD chain is `UsdPhysics.Scene` plus `PhysxSceneAPI`, a
  `PhysxParticleSystem`, a `Points` or `PointInstancer` particle set with
  `PhysxParticleSetAPI`, and a PBD material on a `UsdShade.Material`.
- Isaac Sim 4.1 is not automatically disqualified: it is based on Kit 106.0.1,
  and Kit 106 has `PhysxParticleSystem` / PBD material schemas. The risk is
  runtime stability and EBench integration, not absence of schema.
- Isaac Sim physics limitations explicitly matter for this spike:
  https://docs.isaacsim.omniverse.nvidia.com/5.1.0/physics/physics_resources.html
  Custom geometry does not reliably collide with GPU particles/deformables,
  particle/deformable contact reports are unsupported, and isosurface is
  render-only with possible memory risk.

## Design

The spike is staged so every step isolates one failure class.

### S0: True Fluid Scope Freeze

Define the claim boundary before any live work.

Pass requires all of the following to be predeclared:

```text
true fluid = PhysX/PBD particle system + particle set + GPU dynamics + particle state readback
not true fluid = mesh-only liquid, shader water, offline cached video, RGB-only success
initial task = source beaker contains N particles; after motion, readback shows transfer or stable failure
```

Primary artifacts:

```text
fluid_truth_criteria.json
usd_schema_probe.json
stage_layer_list.txt
```

### S1: Standalone Particle Runtime Smoke

Start without robot control and without `level1_pour`. Use a minimal scene or a
small overlay adapted from `lab_003/clock.usd` to prove that the target runtime
can load particles, enable GPU dynamics, step simulation, and read particle
state.

This stage answers:

```text
Can a true PhysX/PBD particle set run at all in our Isaac runtime?
```

Pass does not require pouring. It requires finite particle positions, non-empty
particle count, GPU dynamics evidence, and frame-to-frame state evolution or a
documented static equilibrium.

### S2: Beaker Collider Smoke

This is the highest-risk stage. It answers:

```text
Can a source beaker collider hold PBD particles without sealing, leaking,
falling back to CPU-only geometry, or exploding?
```

S2 must try a collider matrix rather than a single "best guess". The execution
order intentionally starts with controllable proxy colliders, then moves toward
native/high-fidelity geometry. This separates "can PBD fluid work at all" from
"can the original beaker collider work without repair".

| Variant | Purpose | Expected value | Expected failure |
|---|---|---|---|
| C0 segmented box/wall proxy | First positive-control baseline | Most GPU-native open container; easiest to debug | Wall seam leaks, corner artifacts, rim too low |
| C1 simplified thick open-cup proxy | Practical delivery candidate | Open cup with explicit wall thickness and bottom | Mesh/SDF seals opening, particles stick at rim, wall too thin |
| C2 segmented convex wall pieces | Curved proxy while staying convex | Better cup shape than boxes without single-hull sealing | Seams, convex cooking warnings, GPU convex limits |
| C3 SDF tri-mesh open beaker | High-fidelity concave container | Best chance for native-looking open cup physics | SDF resolution, sign/normal errors, GPU memory, moving-body issues |
| C4 native `beaker2/mesh` `convexDecomposition` | Native asset reality check | Shows whether existing asset is sufficient | May seal opening, fill interior, or cook into particle-incompatible hulls |
| C5 custom cylinder / analytic custom geometry negative control | Confirm official limitation locally | Expected unsupported/negative control | False success requires careful log review; cannot become production route |

Each variant must run at least a static hold test:

```text
seed particles inside source beaker
step 240 frames with gravity
record source/target/spill particle counts, AABB, centroid, NaN count, log warnings
```

S2 pass for a variant:

```text
gpu_dynamics_enabled=true
schema_preserved=true
particle_count_final >= 95% of particle_count_initial
source_retention_fraction >= 0.95 after settle
below_table_count=0
tail_leak_rate < 0.02 particles_per_second_fraction
nan_count=0
cpu_collision_fallback_detected=false
```

Failure is still useful if classified as `CONTAINER_SEALED`,
`CONTAINER_LEAK`, `GPU_COLLIDER_UNSUPPORTED`, `CPU_FALLBACK`,
`PARTICLE_EXPLOSION`, `READBACK_UNAVAILABLE`, or `PERF_BUDGET_EXCEEDED`.

### S3: Kinematic Pour Rig

S3 uses the S2 collider variants in a kinematic rig before using Franka. It
answers:

```text
If we rotate the source beaker along a controlled trajectory, can particles
leave the source and reach the target beaker?
```

The rig should test both source and target collider behavior:

```text
static target beaker with selected target collider
kinematic source beaker rotated through continuous angular velocity, not teleport transforms
tilt schedule: settle -> 30 deg -> 60 deg -> 90 deg -> return
motion speed sweep: slow, medium, fast
particle count sweep: small smoke, medium, native-like
```

S2 static retention is not enough to claim S3 readiness. If a collider holds
particles while static but fails when the source beaker moves, classify the
result as `KINEMATIC_COUPLING_FAIL`, not as a general fluid no-go.

S3 pass for a variant:

```text
particle_count_final >= 90% of particle_count_initial
source_fraction decreases by at least 0.30 during tilt
target_fraction reaches at least 0.10
nan_count=0
the terminal frame and particle readback agree on flow direction
```

If every collider fails, the spike still succeeds as a research result if the
manifest ranks failures and identifies the best next intervention.

### S4: LabUtopia `level1_pour` Expert Replay

Only after S2/S3 identify at least one working collider path should the spike
enter `level1_pour`. The initial integration should seed particles around
`/World/beaker2` after `PickPourTask.reset()` places the randomized source
beaker. If random placement makes the readback ambiguous, freeze one deterministic
layout first and explicitly record the waiver.

This stage answers:

```text
Does the existing Franka-native pour motion move true fluid in the expected
direction, or does robot motion introduce tunneling / instability?
```

### S5: EBench / IsaacSim41 Consumer Gate

This stage answers whether the fluid overlay survives the EBench consumer path.
It must not claim score just because reset/step works.

Pass requires:

```text
consumer preflight lists particle system and particle count
runtime reset preserves particle prims
GPU dynamics settings are visible in the live scene
one step or short step_chunk completes without schema loss or worker crash
```

### S6: Metric / Readback Gate

Fluid success cannot rely on contact reports. The metric candidate must be based
on particle state readback:

```text
particles_total
particles_in_source
particles_in_target
particles_spilled
target_fraction
source_fraction
centroid
AABB
settled_velocity_proxy
```

A score can be discussed only if `result_info.json`, `metric_trace.jsonl`,
terminal particle state, and render/video all refer to the same run.

### S7: Repeatability and Performance

Run either three same-seed replays or three declared seeds. A stable failure is
acceptable if it is consistently classified.

Performance must record:

```text
particle_count
reset time
step time
episode wall time
GPU memory
render/readback overhead
```

## Architecture Boundaries

The spike should add a parallel fluid track, not mutate the current
`Expert Oracle Score` evidence line. Use separate names:

```text
run_id prefix: fluid_spike_isaacsim41_ebench_...
manifest_type: true_physx_pbd_fluid_spike_evidence
score_claim_allowed: false until S6 passes
official_leaderboard_claim_allowed: false throughout the spike
policy_score_claim_allowed: false throughout the spike
```

## PM Summary

给产品经理的说法：这条线不是把假水画上去，而是测试 Isaac/PhysX 的真实粒子流体能不能进入
LabUtopia/EBench。它很可能失败，但失败也有价值，因为我们会知道问题到底是杯子碰撞体、
GPU 粒子开关、粒子数值稳定、EBench 运行时，还是评分读回。只有同一次 run 同时有粒子读回、
渲染和 metric 证据时，才能把它升级成 benchmark 方向。

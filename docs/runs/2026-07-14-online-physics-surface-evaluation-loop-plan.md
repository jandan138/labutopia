# Online Physics-Surface Evaluation Loop Plan

## Goal and Claim Boundary

Build a model-facing loop in which each liquid image is generated from the
particle state produced by the immediately preceding PhysX transition:

`action t -> four PhysX substeps -> state t+1 readback -> surface t+1 -> render -> observation t+1`

This is **same-state, physics-driven online surface rendering**. It is not the
Isaac Sim 4.1 native PhysX isosurface: a current-frame reconstruction step
authors a USD mesh before rendering. The existing offline trace and mesh cache
are comparison evidence only and are forbidden as runtime inputs.

The work has two explicit milestones. Milestone 1 proves online synchronization
with the accepted kinematic source-beaker physics. Milestone 2 makes the source
beaker robot-graspable, adds episode reset and raw-particle task scoring, and
connects the same runtime to the actual LabUtopia controller/model cameras.

## Reviewed Findings Incorporated

- The accepted `/World/beaker2` is kinematic and cannot by itself prove Franka
  model-action causality.
- The bare `config/level1_pour.yaml` contains no validated fluid scene.
- A reset currently randomizes beakers after `world.reset()`, while particle
  positions are world-space; a fluid episode needs an explicit reset contract.
- One `world.step()` is not the accepted fluid cadence. One observation uses a
  1/30 s logical transition composed of four 1/120 s integration substeps.
- The first observation is a reset observation with no model action. Subsequent
  observations identify the prior action that caused them.
- A changing caller index is not a freshness proof. Online readback must use
  `physxParticle:simulationPoints` only and bind to authoritative step counters.
- Camera freshness and raw-particle transfer both require direct evidence;
  differing RGB hashes alone are insufficient.

## Files

### Milestone 1: online causality probe

- Add `utils/online_fluid_surface.py` as the only reusable online surface
  runtime. It owns strict simulation-point validation, frame tokens,
  current-frame reconstruction, mesh invalidation/update, render handoff, and
  latency records. It has no trace, NPZ, or mesh-cache reader.
- Add `tools/labutopia_fluid/run_interndata_online_surface_probe.py` as a thin
  Isaac Sim 4.1 adapter around that runtime. It opens the accepted initial
  package, retains the strict 1/30 s plus four-substep physics authority, and
  runs `pour` and `hold` action treatments.
- Extend `tools/labutopia_fluid/interndata_surface_reconstruction.py` with one
  separately named live reconstruction contract if profiling confirms that the
  accepted offline contract cannot meet the interactive target. The offline
  contract and its hashes remain unchanged.
- Add `tests/test_online_fluid_surface.py` and
  `tests/test_interndata_online_surface_probe.py`.

### Milestone 2: robot evaluation integration

- Add a robot-compatible fluid overlay under
  `assets/chemistry_lab/lab_001_fluid_eval/`. The source beaker becomes one
  dynamic compound actor whose visual mesh and validated box-panel liquid
  collider move together; the target remains static.
- Add `config/level1_pour_online_fluid.yaml` with one fixed, calibrated initial
  layout, the validated particle/system paths, GPU PBD settings, four physics
  substeps per observation, and online-surface settings. Randomized fluid
  layouts remain out of scope until pose-relative reset is validated.
- Add `utils/fluid_evaluation_loop.py` to expose importable, testable setup,
  episode reset, physics advance, surface update, render, and observation-token
  operations without importing or launching `main.py` in tests.
- Make a small opt-in change in `main.py`: disabled configurations retain
  `world.step(render=True)`; the fluid configuration calls the helper before
  `task.step()` reads cameras and calls it after every task reset.
- Add raw-particle transfer scoring to the fluid evaluation runtime. Model task
  success requires target occupancy and zero nonfinite/tabletop/below-table
  particles; the presentation mesh is never used for scoring.
- Add `tests/test_fluid_evaluation_loop.py` and a focused fluid-config contract
  test. Existing non-fluid task tests remain unchanged.

## Runtime Contracts

### 1. Transition identity

Every online record contains:

- `episode_id`;
- `observation_index`;
- nullable `caused_by_action_index` (`null` for reset observation 0);
- physics logical/integration counters before and after the transition;
- simulation time before and after;
- strict current particle count and canonical position hash;
- surface contract/hash and authored vertex/face counts;
- render token and exact camera array hashes delivered to the controller.

Unchanged particle hashes are valid during a hold. Freshness comes from the
post-step epoch/counters and render token, not from forcing state hashes to
change. Duplicate or decreasing episode/observation/counter identities fail.

### 2. Strict particle authority

Online mode reads only `physxParticle:simulationPoints`. It does not fall back
to authored `UsdGeom.Points` or PointInstancer display positions. Readback must
be exactly `3600 x 3`, finite, and associated with the active attached physics
stage after all four substeps. The raw array is passed in memory to both
classification and reconstruction.

The runtime does not author particle positions, velocities, cup poses,
colliders, or scores during a normal transition. A presentation failure hides
the old mesh and suppresses the model observation; stale liquid is never shown
as current.

### 3. Surface and render ordering

For each transition:

1. hold the selected robot or kinematic action constant;
2. advance exactly four 1/120 s PhysX substeps;
3. read and hash current simulation points;
4. reconstruct only that array and update the sole visible liquid mesh;
5. execute a bounded render-only barrier;
6. prove timeline and physics counters did not advance in the barrier;
7. read the exact camera arrays consumed by the controller/model.

A topology-alternation smoke changes visible vertex and face counts on adjacent
render tokens and verifies that the corresponding surface-only image region
changes without a one-frame delay.

### 4. Episode reset

Milestone 1 starts each treatment in a fresh process from the same initial USD.
Milestone 2 uses a fixed calibrated layout and implements:

1. world reset;
2. restore source/target poses and robot state;
3. restore all 3,600 initial simulation points and zero velocities while
   physics is paused/detached;
4. clear or hide the old surface and reset frame-token state;
5. run the pinned settle sequence;
6. create reset observation 0 from the settled readback.

Two consecutive episodes must reproduce the reset particle hash and have
separate episode/token identities. Pose-randomized liquid reset is a later
extension, not an implicit fallback.

### 5. Robot ownership

The kinematic probe proves the visual bridge only. Model evaluation requires a
dynamic source actor with the validated collider children under the same rigid
body as the visible beaker. A real Franka controller or replay action smoke must
show the gripper moving the source visual mesh, compound collider, and contained
particles together. No robot-to-kinematic teleport adapter is used unless it is
explicitly labeled as a separate non-contact evaluation mode.

### 6. Performance labels

Latency is split into particle readback, reconstruction, USD authoring, render,
camera read, and total observation time after warm-up.

- `online`: no future/offline state and correct transition synchronization;
- `interactive`: measured cadence at least 2 observations/s on this host;
- `real_time`: wall-clock/simulated-time ratio meets a declared target.

Correctness is not blocked on the interactive target. Thirty warm observations
report p50/p95 and stale-frame count. No asynchronous old surface or temporal
future accumulation is allowed.

## TDD Order

1. Write failing runtime tests for strict simulation-point reads, reset and
   transition tokens, exact call order, current-array hash propagation,
   unchanged hold states, malformed input, topology changes, failure
   invalidation, render tokens, latency schema, and two consecutive episodes.
2. Implement `utils/online_fluid_surface.py` until the pure tests pass.
3. Write failing probe-contract tests for pinned paths, four-substep cadence,
   fresh-process treatments, no forbidden runtime input, and evidence schema.
4. Implement and run a five-checkpoint online Isaac gate. Profile thirty warm
   frames before changing reconstruction.
5. If needed, write failing tests for a live reconstruction contract, then
   implement one measured fast path. Review its topology, support/volume,
   target-wall clearance, and exact online model-camera images before adoption.
6. Run pour to completion and hold through the matched peak-transfer
   checkpoint in clean copied directories that contain no trace, NPZ, or mesh
   cache. Review initial hold, stream onset, peak stream, target accumulation,
   and final pour frames.
7. Write failing config, reset, dynamic-actor ownership, substep, main-loop
   ordering, model-camera, and raw-particle-score tests for Milestone 2.
8. Implement the robot-compatible overlay, fixed fluid config, evaluation-loop
   helper, and opt-in `main.py` hook.
9. Run two episode resets, a real controller/replay grasp-and-pour smoke, and a
   negative hold episode. Verify raw-particle scoring and the exact 256 x 256
   arrays passed to the inference engine.
10. Run focused and related regressions, decode media, audit manifests, and
    perform independent visual and implementation review.

## Acceptance Criteria

### Milestone 1

- Every non-reset RGB is linked to one prior action and one exact four-substep
  transition; reset RGB has a null caused-by action.
- Runtime provenance contains no trace, NPZ, mesh cache, or future frame.
- Strict readback has exactly 3,600 finite simulation points at every gate.
- Mesh update precedes render; render changes no physics/timeline counters; the
  camera freshness smoke has zero one-frame lag.
- Pour and hold share the initial state and matched simulated time. At the
  transfer checkpoint they differ in cup pose, raw-particle distribution,
  current surface, and visible liquid pixels.
- Raw-particle classification, not the mesh or RGB, proves containment and
  transfer.
- Online images have one visible liquid representation and pass visual review
  without definite wall crossing or tabletop spill.
- Measured latency is reported with accurate `online`, `interactive`, and
  `real_time` labels.

### Milestone 2

- A concrete tracked fluid USD/config opens without external output-directory
  dependencies and uses one `/World/PhysicsScene` with GPU PBD enabled.
- In the explicit `gripper_attached_kinematic_vessel` mode, Franka actions move
  the source beaker through PhysX kinematic targets while PhysX independently
  computes the contained liquid. This is not a contact-grasp claim.
- Two consecutive episode resets restore the same accepted particle state,
  clear stale surfaces, and produce distinct episode tokens.
- The model receives current online liquid in the actual configured 256 x 256
  cameras after each action transition.
- Positive pour and negative hold episodes are distinguished by raw particle
  target/source/transit/spill counts.
- Fluid-disabled tasks preserve the previous world-step/render behavior.
- All focused and related regressions pass and the runtime evidence manifest is
  internally hash-consistent.

## 2026-07-15 Reviewed Implementation Update

Milestone 1 is frozen as an Isaac Sim 4.1 kinematic-vessel evidence adapter.
The matched pour/hold gate proves the current-state chain but does not prove
that the LabUtopia model consumed the probe's Replicator buffers.

The original dynamic-vessel requirement is replaced for the first production
integration by an explicitly named `gripper_attached_kinematic_vessel` mode.
This is not a contact-grasp claim. Three bounded dynamic-hold attempts showed:

- switching before particle initialization produced 34 tabletop particles;
- switching after initialization first exposed Isaac 4.1 mixed-precision xform
  authoring errors; and
- after handling that warning, the first dynamic step dropped the source body
  about 3 cm and produced 29 tabletop particles.

No mass, table-height, collider, or hidden-support tuning follows in this
milestone. The model still controls the Franka; after grasp attachment, the
source vessel follows the measured gripper pose through kinematic targets and
the liquid motion remains PhysX PBD.

Milestone 2 is a separate Isaac Sim 5.1 integration with `World` as the sole
simulation owner. The opt-in fluid branch replaces the legacy world step:

`pending action -> attach vessel to current gripper pose -> 4 x world.step(render=False) -> strict particle read/score -> current surface -> world.render() -> one task.step() -> exact model camera buffers`

The helper owns the pending action, the sole `task.step()` camera read, surface
token, raw-particle score, and episode reset. Non-fluid control flow remains on
the legacy branch. The existing 5 mm cameras are contract
`level1_pour_rgb_v1_legacy_5mm`; liquid-aware cameras are a separate
`level1_pour_rgb_v2_liquid_aware` contract and require compatible data/model
evaluation. Their scores are not directly comparable.

The source attachment and source containment scorer read the same current
PhysX rigid-body pose. The authored wrapper-to-parent transform is cached once,
then composed as
`wrapper_to_parent @ current_parent_physics_world` for each post-step score.
The target remains a verified static authored frame. Per-observation evidence
records the current source-frame origin and axis so a stale USD scoring frame
cannot be mistaken for liquid escape.

The exact state passed to the controller/model is adapted after `task.step()`
and before controller consumption. Only `object_position` and
`object_quaternion` are replaced: the authored geometry-center offset follows
the current PhysX source pose, and scalar-first PhysX orientation is normalized
and exposed as the existing controller's `xyzw` contract. Camera mappings and
arrays remain identical objects, and the adapted pose is recorded alongside
the camera hashes.

The live surface lattice permits up to 384 voxels on one axis so a normal
elongated pour stream can be rendered. This is intentionally isolated from the
offline reference contract, which remains at 256, and from the unchanged live
total guard of 8,000,000 voxels. It changes presentation capacity only: all
fluid success and leakage decisions continue to use strict raw-particle
classification.

Updated Milestone 2 acceptance:

- exactly one `/World/PhysicsScene`, 1/120 s physics, four substeps per 1/30 s
  observation, and one render-only barrier;
- the same CHW uint8 camera arrays hashed by the helper are passed to inference;
- attachment follows the actual gripper frame and is clearly reported as
  kinematic, with no direct model-to-vessel pose command;
- raw particles, not RGB or mesh, determine transfer and spill success;
- reset observation 0 has no pending action and two consecutive episodes have
  distinct tokens with equivalent restored particle sets; and
- performance is labeled `online` only until complete-loop timing meets a
  separately declared interactive or real-time threshold.

## 2026-07-15 Deterministic Pour Completion Plan

The first complete Isaac Sim 5.1 run produced three distinct outcomes from the
same fixed scene: one controller path stopped at 55.1 degrees with no transfer;
one reached 174.4 degrees and physically transferred 3,560 of 3,600 particles;
and a third formed a long stream before the live presentation lattice stopped
at 8,383,500 voxels. The successful transfer then remained exactly at
`target=3560, transit=38, tabletop_spill=2, below_table=0` for more than 300
observations. These results isolate controller randomness, quantized scoring,
and presentation capacity from the already working PhysX liquid motion.

Implementation order and file scope:

1. Live lattice capacity, presentation only.
   Add failing boundaries in
   `tests/test_interndata_live_surface_reconstruction.py`, then raise only the
   live `max_total_voxels` from 8,000,000 to 10,000,000 in
   `tools/labutopia_fluid/interndata_surface_reconstruction.py`. The observed
   `[150, 243, 230]` stream span must pass; 10,000,000 is accepted and any
   larger volume is rejected. The offline contract remains 256 per axis and
   8,000,000 total.
2. Reproducible expert motion.
   Add focused tests for `controllers/atomic_actions/pour_controller.py` before
   changing it. Height offsets are sampled once per episode, never on every
   `forward()` call, and `forward()` must not mutate the caller's target array.
   The actually selected `controllers/pour_controller.py` passes candidate
   online-fluid offsets `[0.4, 0.2]` from the config; ordinary data collection
   retains one random sample per episode. These upper-bound offsets are not
   accepted as a working trajectory until two live episodes pass.
3. Preserve strict scoring and diagnose outliers.
   Do not redefine the existing zero-transit, zero-tabletop
   `fluid_transfer_passed` result to make the observed `3560/38/2` frame pass.
   Add compact per-category world bounds to the raw score so a new run can
   distinguish particles in the target wall/rim from real table loss. If a
   bounded-loss product metric is later accepted, it must be a second named
   result, require `source=0`, and never be reported as strict leak-free
   transfer. RGB and surface meshes never decide either result.
4. Liquid-aware model/review cameras.
   Keep `level1_pour_rgb_v1_legacy_5mm` unchanged. Add a separate
   `level1_pour_rgb_v2_liquid_aware` config using the already validated
   `/World/InternDataParityCamera` context view and
   `/World/InternDataParityCloseupCamera` target-pour view, with explicit
   clipping. Validate the resolved USD camera transform and optics, hash the
   normalized contract, and record its ID/hash with every observation. V2 is
   first a visual-review and new-data contract; it is not substituted into an
   existing V1 model or compared to V1 scores without matching data/model work.
5. Runtime acceptance.
   Write video from the exact hashed `camera_data` arrays at 30 FPS before the
   terminal controller branch, so every evidence observation has the same
   ordered video frame. Run two reproducible positive episodes and a thin
   orchestration-level no-action hold using the same USD, camera contract, four
   substeps, and duration. Require the pick-to-pour transition, complete 3,600
   particle partitions, render barriers that do not advance physics, and two
   reset tokens with equivalent restored distributions. GPU PhysX is not
   claimed bitwise deterministic; reset evidence records hashes plus compact
   distribution summaries. Run independent V2 visual review for a readable
   stream that crosses the source rim and enters the target, with no definite
   wall penetration or visible tabletop spill.

No collider, particle size, viscosity, reconstruction spacing, robot grasp
ownership, or source/target asset geometry changes are part of this plan.

## 2026-07-15 Product Transfer Metric Revision

Product acceptance now distinguishes vessel containment from normal pouring
spill. A beaker must not passively leak during a separate static or gentle-move
qualification, but a model-driven pour is not rejected merely because some
water splashes onto the rim or table. The strict zero-spill result remains a
diagnostic and is never relabeled.

Implementation order and file scope:

1. Add a second, explicit task result without changing strict classification.
   `classify_transfer_positions()` continues to emit
   `fluid_transfer_passed` with zero transit/tabletop/below-table requirements.
   `FluidTransferScorer` additionally emits `task_transfer_passed`, whose hard
   requirement is a valid complete partition, at least the configured
   `minimum_target_particles`, and `target_fraction >= 0.50`. The fraction is
   configured, not hard-coded. Source, transit, tabletop, below-table, aggregate
   spill, and nonfinite fractions use the original particle count as their
   common denominator and remain continuous quality diagnostics; none of those
   spill categories individually vetoes the task result.
2. Use the product result only at the evaluation boundary.
   `FluidEvaluationLoop.finalize_episode()` returns strict and task results
   separately; its combined `success` uses controller completion plus
   `task_transfer_passed`. It also exposes `expert_episode_accepted`, requiring
   controller completion and `target_fraction >= 0.90`, for high-quality H5
   collection. Tests must prove that a high-transfer pour with a small spill
   passes both product and expert results while strict zero-spill remains false,
   and that an almost-empty target still fails.
3. Do not commit failed expert data early.
   In online-fluid collection, `PourTaskController` defers H5 commit until
   `main.py` combines controller and liquid results, then receives exactly one
   `finalize_collection_episode(...)` call. Expert acceptance writes H5; all
   other outcomes clear the cache. The H5 task properties bind the metric
   policy ID, strict/task/expert results, final particle counts/fractions,
   camera contract ID/hash, and configured expert target offset. Legacy
   non-fluid collection keeps its existing behavior.
4. Make repeated expert episodes start from the same lifecycle.
   Construct the controller after the initial task reset, and on later episodes
   reset the task before resetting the controller/RMP state. `attempt_index`
   advances for every trial and names evidence/video; collector episode count
   advances only for accepted H5. A configured maximum attempt count prevents
   an endless run when no expert episode is accepted. Add a focused orchestration
   contract test before changing `main.py`; then run a short two-reset smoke
   before another complete pour.
5. Improve the expert and model view with one bounded correction each.
   Keep the fluid physics unchanged. Make the evidence-derived `+0.05 m` pour
   target Y correction configurable for online fluid, and widen only the V2
   context camera enough to keep source cup, gripper, stream, and target in
   frame while retaining the close-up camera. Re-run independent visual review.
6. Qualify containment separately.
   Run a short hold/gentle-move protocol on the same asset and require every
   particle to remain in the source vessel before pouring begins. Report this
   as vessel-integrity evidence, not as the pouring task score.

No spill threshold sweep, collider change, particle retuning, V3 camera, or
strict-score deletion is part of this revision.

## 2026-07-15 Final Isaac Sim 5.1 Outcome

The product evaluation loop passed its first complete expert episode in
Isaac Sim 5.1. This section supersedes the earlier provisional 384-axis,
8M/10M-total, full-relative-attachment, and zero-spill-as-task-gate notes above.
Those entries remain as the investigation history.

The final implementation uses a staged non-contact kinematic source-vessel
policy. When scripted close completes, the source follows only the gripper's
world-translation delta and retains its current orientation. On the first
controller call that actually emits atomic pour event 2, the runtime recaptures
the full source-to-gripper transform and begins rigid translation/rotation
following. This handoff is action-latched rather than inferred from cup angle.
It preserves PhysX authority for every liquid particle while preventing a
random pre-pour gripper orientation from tipping the source early.

TDD evidence:

- the staged-attachment focused gate passed 113 tests, and the final broader
  selected liquid/controller/config/real-beaker suite passes 193 tests;
- initial source attachment measured 0 m / 0 degrees of pose jump;
- the pour handoff measured about 2.31e-16 m / 0 degrees of pose jump;
- exactly one attachment and one rotation handoff occurred; and
- the accepted episode reports `expert_attachment_valid=true`.

Final runtime evidence:

- run: `outputs/collect/2026.07.15/11.43.46_Level1_pour_online_fluid_v2`;
- episode 0: 847 observations, 28.23 seconds of logical simulation time;
- raw-particle result: source 0, target 3,594, transit 1, tabletop 5,
  below-table 0, nonfinite 0;
- target fraction 99.8333%, task transfer passed, expert transfer passed,
  strict zero-spill transfer false;
- accepted dataset: `dataset/episode_0000.h5`, 426 action/observation steps,
  with both 256x256 CHW uint8 V2 camera streams and final policy metadata;
- the second reset remained at source 3,600, tabletop 0, below-table 0 for its
  recorded 153-observation prefix; and
- independent image review returned WARN, not FAIL: the stream and final target
  fill are clear, with no visible penetration or broken surface; the close-up
  crops part of the transported source cup and should be widened in future V2
  data collection.

The dynamic task metric intentionally treats five tabletop particles (0.139%)
as measured splash rather than a binary task failure. Passive containment is a
separate qualification: static or gentle motion must not create environmental
loss. The strict zero-spill diagnostic is still recorded and remains false for
this episode.

The final live reconstruction guards are axis 512 and total 24,000,000 voxels;
the offline contract remains axis 256 and total 8,000,000. The largest observed
successful-run lattice was `[97, 162, 384]` (6,034,176 voxels). Complete-loop
latency was p50 0.131 s, p95 0.344 s, and max 0.601 s, so the result is online
and same-state but not yet 30 FPS wall-clock real-time. Physics still advances
at four 1/120 s substeps per 1/30 s logical observation; the video is encoded
at that logical 30 FPS.

Repository-wide `python -m pytest -q tests` completed with 1,025 passing tests
and three pre-existing failures in `test_support_aligned_authority_bundle.py`.
All three reject an unrelated historical authority bundle because its frozen
runner SHA no longer matches the current runner; none exercises or modifies the
online-fluid implementation. The mismatch is left visible rather than silently
re-signing historical evidence in this feature change.

# Online Physics-Surface Evaluation Loop Plan Reviews

## Reviewers

- Architecture: agent `Halley the 2nd`
  (`019f6104-7d48-7c63-a00e-2bdcbec18116`).
- Completeness and edge cases: agent `Huygens the 2nd`
  (`019f6104-8d43-7013-81e6-7b0b9b3de7b0`).
- Risk and evidence: agent `Locke the 2nd`
  (`019f6104-9bc0-7cd1-8422-8969a846a18a`).

All three reviewers inspected the draft and relevant repository code without
editing files. All returned `REVISE`.

## Accepted Corrections

1. Rename the claim from native/direct PhysX rendering to same-state,
   physics-driven online surface rendering. The tested Isaac Sim 4.1 native
   isosurface remains a failed presentation route, not a universal claim about
   later Isaac versions.
2. Split the kinematic online causality probe from robot model evaluation. The
   accepted kinematic beaker can prove the bridge but not Franka action
   causality.
3. Require a tracked fluid evaluation scene/config with a dynamic, graspable
   source compound actor before claiming model evaluation support.
4. Pin the accepted 1/30 s logical transition and four 1/120 s PhysX substeps,
   one physics scene, GPU PBD, and strict post-step simulation-point readback.
5. Define episode, observation, caused-by action, physics-counter, and render
   identities. Reset observation 0 explicitly has no causing model action.
6. Add an episode reset contract. The first model milestone uses a fixed
   calibrated layout; unsupported pose-randomized liquid reset is not hidden
   behind fallback behavior.
7. Use one reusable runtime module rather than overlapping tool and utility
   bridges. The Isaac probe and `main.py` integration are thin adapters.
8. Add strict no-fallback particle readback, stale-mesh invalidation on failure,
   changing-topology tests, bounded render freshness proof, and exact
   model-camera array hashes.
9. Separate model-visible liquid from fluid-aware benchmark scoring. Positive
   pour and negative hold episodes are scored from raw particle regions.
10. Separate `online`, `interactive`, and `real_time` claims and report warm
    stage latency instead of inferring speed from correctness.
11. Run the online proof in a clean directory without traces, NPZ files, or
    mesh caches and review exact 256 x 256 model-facing images.

## Scope Decisions

- A robot-to-kinematic cup teleport adapter is not the default model-evaluation
  route because it bypasses grasp/contact behavior. It may be added later only
  as an explicitly labeled control mode.
- General randomized fluid reset is deferred. A fixed calibrated scene is
  sufficient for the first real robot evaluation and avoids silently leaving
  world-space particles behind after object randomization.
- A second complete 690-step hold run is unnecessary. The hold treatment ends
  at the matched peak-transfer checkpoint, which is sufficient to establish the
  negative contrast while keeping the evidence small.
- Isaac Sim 5.1 support is not inherited from documentation alone. The current
  host has a working 4.1 environment; a 5.1 runtime must be located or installed
  and its physics revalidated before making a 5.1 claim.

## Final Review State

The revised plan now distinguishes a visual synchronization milestone from a
robot benchmark milestone, defines the missing reset/timing/scoring contracts,
and keeps the first implementation focused on one online bridge and one
causality probe. TDD implementation may proceed.

## 2026-07-15 Milestone 2 Re-review

Three fresh read-only reviews covered architecture, completeness, and product
risk after the model-camera and dynamic-hold evidence existed.

### Shared P0 Findings

1. Fluid mode must replace the legacy `world.step(render=True)` rather than add
   work around it. The 5.1 `World` owns one `/World/PhysicsScene`, executes four
   1/120 s physics-only steps, then one render-only update.
2. The fluid helper must call `task.step()` exactly once and hash the exact
   `state["camera_data"]` arrays passed to the controller/inference engine. The
   4.1 Replicator probe cannot prove production model-buffer identity.
3. Pending action ownership and reset observation 0 must be explicit; reset is
   checked before any new physics transition.
4. Raw-particle scoring must gate fluid success independently of the legacy
   pose-based controller result.
5. Fixed fluid reset cannot use the ordinary randomized `PickPourTask.reset()`
   path and needs a two-episode gate.
6. Legacy 5 mm and liquid-aware camera profiles are different versioned
   observation contracts.

### Iterated Decision

The reviewers preferred a validated dynamic source. The bounded Isaac 4.1
dynamic-hold experiment then failed that prerequisite: pre-init activation
spilled 34 particles; post-init activation exposed a mixed-precision xform
warning; and the warning-checked run dropped the source about 3 cm on its first
dynamic step and spilled 29 particles. The implementation therefore does not
claim contact grasp or dynamic source ownership.

For this milestone, the production boundary is
`gripper_attached_kinematic_vessel`: model actions move the Franka, the vessel
tracks the measured gripper frame after attachment, and PhysX independently
computes all particle motion. This route keeps the accepted containment physics
and is explicitly reported as a kinematic attachment. Dynamic contact grasp is
a later asset/physics redesign, not a hidden fallback inside this integration.

### Deferred By Review

- randomized liquid layouts;
- asynchronous or real-time reconstruction optimization;
- broad camera tuning inside the legacy contract;
- generalized all-task reset/scoring frameworks; and
- claims about Isaac Sim 5.1, multi-episode reset, or model consumption until
  the corresponding live gates pass.

## 2026-07-15 PhysX Pose/Scoring Re-review

Reviewers:

- Architecture: `Volta` (`019f62fc-bf62-7d13-9aae-5e65eaf8c0c9`).
- Completeness and edge cases: `Euler`
  (`019f62fc-c33f-7802-bb74-42da8c5dd716`).
- Risk and evidence: `Hilbert` (`019f62fc-c7bc-7c03-8c18-c2b9319b2fa0`).

All three gave conditional approval to the same minimal correction. The
450-observation run proved that the source and reconstructed liquid rose from
about 0.76 m to 1.09 m without the prior lattice failure, while the scorer
misclassified all particles as transit because its wrapper frame still came
from the static USD transform.

The iterated plan is:

1. Make attachment capture and source scoring share
   `SingleRigidPrim.get_world_pose()` as their current PhysX authority.
2. Preserve the authored wrapper local relation and compose row-affine matrices
   as `wrapper_to_parent @ current_parent_physics_world`.
3. Test scalar-first quaternion conversion, nontrivial rotation, child-frame
   tracking, and scoring with a static USD pose but moving physics pose before
   implementation.
4. Record the current source-frame origin and axis in every score, then rerun
   the 450-observation attachment gate.
5. Do not infer full transfer from that lift gate. A complete expert pour,
   matched hold, and two real resets remain required before the evaluation-loop
   claim is accepted.

Contact grasp, generalized moving targets, randomized layouts, and a generic
USD/Fabric synchronization framework remain outside this correction.

## 2026-07-15 Controller State Re-review

Reviewers:

- Architecture: `Euclid` (`019f630b-ed37-7843-a3d7-1f79ffca7d93`).
- Completeness: `Descartes` (`019f630b-f175-7903-8b0f-f8f658cb2e07`).
- Risk: `Franklin` (`019f630b-f5de-7ac2-bcec-47b53e098ae8`).

All three conditionally approved a narrow state adapter after a complete run
ended its first episode with the physical source at about 1.21 m and all 3,600
particles still inside it, while the expert controller had not entered the
pour phase. The evidence strongly supports a stale USD task pose, but the fix
is accepted only when a new run demonstrates the phase transition.

Accepted constraints:

1. `FluidEvaluationLoop` provides only an optional post-`task.step()` adapter;
   PhysX-specific work remains in `PhysicsSourceStateAdapter`.
2. Position and orientation come from one `get_world_pose()` snapshot. The
   original geometry-center offset is transformed as a row-vector local point,
   and `wxyz` is normalized and reordered to controller `xyzw`.
3. The adapter shallow-copies state, changes only the two pose fields, and
   preserves exact camera mappings and arrays.
4. Tests cover call order, unchanged cameras, nonzero center offset under a
   90-degree rotation, quaternion order, invalid adapter output, and fail-closed
   episode behavior.
5. Acceptance still requires a real `PICKING -> POURING` transition, physical
   tilt, target occupancy, two real resets, and unchanged camera provenance.

## 2026-07-15 Live Lattice Capacity Re-review

Reviewers:

- Architecture: `Galileo`.
- Completeness and boundary cases: `Parfit`.
- Risk and evidence: `Leibniz`.

All three conditionally approved a presentation-only capacity correction after
the controller reached `POURING` and the run stopped at observation 511 with
`lattice_axis_limit_exceeded:[84, 216, 271]`. Raw-particle evidence at that
frame still contained 3,593 particles in the source, 7 in transit, and none on
or below the tabletop. The failure was therefore a live surface lattice limit,
not a spill or unstable-physics result.

Accepted constraints:

1. Increase only the live contract's `max_axis_voxels` from 256 to 384.
2. Keep the offline reference contract at 256 and the live total-volume guard
   at 8,000,000 voxels.
3. Keep raw particles as the sole authority for transfer, spill, below-table,
   and non-finite failure; lattice limits remain presentation capacity guards.
4. Tests accept the observed `[84, 216, 271]` pour span and the exact 384-axis
   boundary, while rejecting axis 385 and total volume above 8,000,000.
5. Acceptance still requires the full expert run; passing these synthetic
   lattice boundaries alone is not evidence of a successful pour.

## 2026-07-15 Deterministic Completion Re-review

Reviewers:

- Architecture: `Turing` (`019f6326-4f73-7ed0-91ca-33b441885907`).
- Completeness and boundary cases: `Carson`
  (`019f6326-5c39-7662-a50c-280ec18822ba`).
- Risk and product evidence: `Dalton`
  (`019f6326-69a7-7a92-b869-df104f36506c`).

All three returned conditional approval. The plan was iterated before code:

1. The active config selects `controller_type: pour`; fixed offsets therefore
   enter through `controllers/pour_controller.py`, not the similarly shaped
   but inactive `pickpour_controller.py`.
2. `[0.4, 0.2]` is an unverified candidate because the successful randomized
   run cannot be inverted to one fixed pair. Two positive runs are the gate.
3. The observed stable `target=3560, transit=38, tabletop_spill=2` result is not
   renamed leak-free. Strict scoring remains visible; category bounds are
   collected before any separately named bounded-loss decision.
4. Raising only the live total lattice capacity to 10,000,000 is accepted as a
   presentation fix, with offline still at 8,000,000 and runtime labeled
   `online`; p95/max latency and process memory are reported.
5. V2 cameras are independently validated and versioned. They are approved for
   visual review and future V2 data/model evaluation, not as a silent change to
   the existing V1 model distribution.
6. Video consumes the same hashed model arrays at 30 FPS, and a matched hold is
   implemented only at orchestration level. Neither concern is pushed into the
   physics scorer or reconstruction module.

The reviewers requested exact reset hashes. The implementation instead keeps
the existing stricter raw hashes and adds distribution summaries, because GPU
PhysX reproducibility is an empirical gate rather than a promised bitwise
property. Any hash mismatch must be quantified and cannot be called equivalent
without the declared tolerances.
# 2026-07-15 Product Metric Revision Review

Three read-only reviewers re-audited the revised product requirement that
normal pouring spill must not be a binary failure while passive vessel leakage
remains a separate hard qualification.

## Architecture review

- Conditionally approved the split between vessel integrity, strict zero-spill
  diagnostics, product transfer, and expert H5 acceptance.
- Required a meaningful target-volume threshold instead of the existing
  150-particle smoke threshold alone.
- Required one idempotent controller-owned H5 finalize interface after the
  combined liquid result, plus separate attempt and accepted-episode counters.
- Approved the lifecycle order `task.reset -> controller init/reset -> fluid
  loop` and required unresolved collection state to be rejected at reset.

## Completeness and boundary review

- Recommended a configured `target_fraction >= 0.80` task boundary; the final
  synthesis adopts a more permissive 0.50 model-task threshold and a separate
  0.90 expert-data threshold so normal imperfect model pours are accepted while
  expert demonstrations remain high quality.
- Required boundary tests at the exact fraction, one particle below it, a
  `3557/14/29` high-transfer spill case, controller-incomplete rejection,
  nonfinite rejection, and ratio partition completeness.
- Required static hold and gentle motion to remain an independent all-particles-
  in-source qualification, not part of the pouring score.

## Risk review

- Approved spill as a continuous quality metric rather than a veto.
- Required the H5 to bind camera contract ID/hash, metric policy ID, final
  particle counts, and the expert-only target correction.
- Approved one fixed `+0.05 m` expert Y correction only if it is configured,
  never applied to inference/model actions, and not adapted online from score.
- Confirmed that widening the not-yet-frozen V2 context view is a necessary
  observability correction, not metric manipulation; V1 data remains separate.

## Synthesized decision

- Model task success: controller completed, valid particle partition, target
  count above the configured absolute floor, and target fraction at least 0.50.
- Expert H5 acceptance: controller completed and target fraction at least 0.90.
- Spill categories never independently veto either result; all remain reported.
- Existing strict zero-spill semantics remain unchanged under an explicit
  diagnostic name and compatibility alias.
- No collider, particle, surface-reconstruction, or scoring-region geometry is
  changed by this revision.

## 2026-07-15 Staged Attachment and Final Gate Review

Reviewers:

- Architecture: `019f63d6-fd7b`.
- Completeness and boundary cases: `019f63d6-f524`.
- Risk and evidence: `019f63d6-f932`.

All three reviewers selected the same minimal staged policy: preserve the
source orientation while transporting it with the gripper's world-translation
delta, then recapture the full rigid relation only after atomic pour event 2
actually emits its joint velocity. They rejected cup-angle inference and
continuous relative-transform blending as unnecessary state and ambiguity.

The implementation was written against failing action-latch, attachment,
handoff, reset, and live-capacity boundaries. The staged focused gate passed
113 tests; the final broader selected fluid suite passed 193. A full Isaac Sim
5.1 gate completed with one zero-jump attachment,
one zero-jump rotation handoff, 3,594 of 3,600 particles in the target, five on
the tabletop, one in transit, and none below the table. Task and expert metrics
passed; the strict zero-spill diagnostic remained false as designed.

Independent context-free visual review returned WARN with high confidence. It
confirmed a coherent stream into the target, stable final collection, and no
obvious beaker/table penetration, floating geometry, or broken surface. The
only material limitation is framing: the V2 close-up crops part of the source
beaker during transport and active pouring. This is accepted for the current
physics/data gate and recorded as a future camera-contract improvement, not a
reason to retune the liquid or add fallback logic.

The final evidence also corrects earlier provisional capacity statements: live
is axis 512 / total 24M, offline remains axis 256 / total 8M, and the largest
successful-run lattice was 6,034,176 voxels. Complete-loop p50/p95/max latency
was 0.131/0.344/0.601 seconds, so the claim remains online and same-state rather
than wall-clock 30 FPS real-time.

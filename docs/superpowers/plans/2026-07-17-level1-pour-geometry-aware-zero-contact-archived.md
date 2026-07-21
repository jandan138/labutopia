# Archived Level1 Pour Geometry-Aware Zero-Contact Plan

> Archived after the product decision to permit bounded, monitored finger-source
> contact before CLOSE. This document is evidence history only and is not a
> normative implementation or authorization contract.

**Goal:** Replace the failed legacy diagonal approach with one frozen,
source-centered top-down trajectory, first prove its actual swept clearance and
aperture authority without interacting with the source, and only then determine
whether the unchanged Franka and filled 600 Hz vessel can achieve brief bilateral
contact without lift, pour, source writes, attachment, geometry changes, or
particle loss.

## Established Evidence

- The sealed native attempt completed with
  `NATIVE_EXPERT_CLOSE_ONLY_FAIL`. At physics step 3253 the right finger touched
  the source during legacy event 2, before any close command. The controller was
  still in positioning, all 3,600 particles remained in source, and source motion
  was only `2.8272342302348016e-05 m`.
- The cooked open inner finger gap is `0.07741653828466591 m`. The widest sampled
  source shell is `0.07131712 m`, leaving `0.003049709142332948 m` geometric
  clearance per side. This is enough for a precisely centered geometric path but
  too small for the legacy 5 mm position tolerance or an uncontrolled diagonal
  sweep.
- The source contact offset is `0.0020000000949949026 m`; the finger contact
  offset remains PhysX-autocomputed. Therefore no analytical clearance PASS is
  claimed. The live current-step contact monitor remains the authority and must
  reject any contact before close.
- The exact step-600 particle layout with robot present is passively stable at
  600 Hz. Geometry, asset, material, collision roles, source ownership, physics,
  camera cadence, and acceptance thresholds remain unchanged.

## Boundary

- Reuse the existing `ContactPickController`; do not add another state machine.
- Change only the commanded approach trajectory and its explicit controller
  evidence. Do not change the vessel, Franka USD, colliders, contact/rest offsets,
  material, particle layout, 2 mm/1 degree motion limits, or contact gate.
- Keep collect mode, one attempt, 600-step pre-roll, 600 Hz physics, 30 Hz
  control, 20 physics substeps per action, and the 2,400-observation bound.
- Never use source pose following, kinematic targets, teleporting, attachment,
  collision filtering, hidden support, or a fallback trajectory.
- The filled close-only attempt is not authorized until the measurement preflight
  below passes every gate. Run exactly one filled attempt after that GO. A
  failure does not authorize parameter tuning or an automatic retry.

## Review Decision

Architecture, completeness, and physical-risk reviews rejected a direct filled
run. Their blocking findings are incorporated here:

- The prior top-down zero-offset pose and `0.037 m` endpoint were previously
  rejected because effective finger contact offsets and dynamic tracking error
  were unknown. They are provisional measurement inputs, not approved product
  parameters.
- Nominal joint positions and commanded waypoints cannot prove physical aperture
  or swept clearance. The preflight must measure cooked inner-pad gap, actual
  tool/finger motion, orientation error, lag, overshoot, and contact onset at
  600 Hz.
- The production controller must not advance from an open command to arm motion
  without a later measured full-open state. INSERT must stay on the frozen world-Z
  line, ALIGN must require current orientation, SETTLE must revalidate pose, and
  CLOSE must not become CONTACT_SETTLE without current bilateral qualification.
- Current contact, sensor freshness, action application, and controller latches
  must agree. Applied lift, hold, pour, source write, attachment, kinematic target,
  or a trajectory different from the reviewed one makes the attempt runtime
  invalid rather than a physical FAIL.

## Provisional Frozen Trajectory

Use `expert_control_profile=contact_pick_v1` and freeze the source pose on the
first post-reset observation. Compute the tool-center waypoints once in world
space from that frozen source frame:

- tool-center orientation WXYZ: `[0.0, 0.0, 1.0, 0.0]`;
- object-frame grasp offset: `[0.0, 0.0, 0.0]`;
- world approach direction: `[0.0, 0.0, -1.0]`;
- configured row-affine `right_gripper -> tool_center` matrix:
  `[[-1,0,0,0],[0,-1,0,0],[0,0,1,0],[0,0,-0.0034,1]]`;
- SETTLE and CONTACT_SETTLE durations: `0.10 s` each.

1. `PREGRASP`: command both finger joints to their physical open target
   `0.040 m` and hold until a later control observation confirms both measured
   positions. The allowed tolerance is derived from the measured gap calibration,
   not assumed to be `0.0002 m`.
2. Move to the source-centered pregrasp point `0.120 m` above the grasp center.
3. `ALIGN`: move to a point `0.060 m` above the grasp center, preserving the
   hash-pinned configured `right_gripper -> tool_center` transform. Do not advance
   until current tool position and orientation satisfy tolerances derived from the
   preflight clearance budget. Missing current orientation cannot pass.
4. `INSERT`: descend only along world `[0, 0, -1]` at `0.006 m/s`, which is
   `0.0002 m` per 30 Hz command. The insertion starts roughly 15 mm above the
   first native contact height and ends at the frozen source geometry center.
5. `SETTLE`: hold the final pre-close pose. Any finger, hand, source, table, or
   other unexpected contact before the first close command fails the attempt.
6. `CLOSE`: close symmetrically using the preflight-calibrated speed and endpoint.
   `0.003 m/s` and `0.037 m` are calibration inputs only. They are frozen for the
   filled run only if measured aperture, velocity, and contact-onset evidence
   supports them.
7. `CONTACT_SETTLE`: once the existing five-distinct-step bilateral gate is
   current and valid, hold the measured aperture and terminate. Never enter
   `LIFT`, `HOLD`, or `POURING`.

The controller evidence must include the frozen source pose, grasp/pregrasp/
align positions, current insertion waypoint, open target/readiness, position and
orientation tolerances, approach/close rates, phase history, last emitted phase,
explicit close/lift flags, control invocation count, open-confirmation control
index, first arm-command control index, and applied action-kind counts.

## Measurement Preflight

Add one parent-sealed `geometry_aware_trajectory_preflight_v1`. It uses the exact
Franka, candidate stage, reset pose, 600 Hz physics, and 30 Hz command cadence,
but disables particles and source interaction for measurement only. It emits no
near-source close, lift, hold, pour, attachment, source write, or kinematic target.

### A. Remote Aperture And Contact-Offset Calibration

1. At a collision-free remote pose, command and confirm the physical `0.040 m`
   open state.
2. Measure both finger joint positions, cooked inner-pad gap, asymmetry, API pad
   velocities, 600 Hz finite-difference velocities, settling time, and limit
   saturation while traversing the predeclared calibration points from `0.040 m`
   through `0.037 m`.
3. Insert a temporary hash-described static calibration body with known width,
   zero rest offset, and an explicitly tiny known contact offset between the
   fingers. Close only at the remote pose and record each exact finger collider's
   first current raw contact. Derive a conservative per-finger effective contact
   offset bound from measured geometric gap minus calibration-body width and its
   known offset.
4. Reject nonmonotonic gap, unresolved collider attribution, API/finite-difference
   disagreement above the contact gate's `0.002 m/s` scale, or any value that
   cannot be represented as finite SI evidence.

### B. Noninteracting Shadow Sweep

1. Freeze the same geometry-center source frame used by the production fluid
   adapter. Disable source collision response and contact reporting only for this
   shadow measurement; keep the source pose fixed and record that diagnostic
   override explicitly.
2. Execute PREGRASP, ALIGN, and the complete INSERT with the production
   `ContactPickController` and RMPFlow. Stop before SETTLE can emit CLOSE.
3. At every 600 Hz step record commanded and measured tool-center pose, RMPFlow
   control pose, both finger and hand cooked-collider transforms, joint state,
   stage units, phase, and action kind/hash.
4. Require INSERT targets to retain the frozen X/Y exactly and move only along
   world Z. Measure maximum lateral error, orientation error, lag, overshoot, and
   per-side geometric clearance over the full sweep.
5. Inflate every swept sample by source contact offset, the calibrated
   per-finger effective offset bound, actual tracking envelope, orientation edge
   displacement, and the existing 1 mm numerical margin. The minimum remaining
   per-side clearance must be strictly positive for both fingers; hand, table,
   and unrelated robot-link clearance must also remain positive.

`GEOMETRY_AWARE_TRAJECTORY_PREFLIGHT_GO` authorizes only implementation and one
filled close-only attempt with the exact measured treatment. Unknown budget terms,
nonpositive clearance, incomplete trace, wrong action, or identity/lifecycle
failure produces `GEOMETRY_AWARE_TRAJECTORY_PREFLIGHT_NO_GO` or
`PROBE_RUNTIME_ERROR` and stops the work before source interaction.

## TDD Implementation Order

1. Add failing pure tests for aperture calibration, effective-offset bounds,
   actual tracking envelopes, orientation edge displacement, swept-clearance
   budgets, contiguous 600 Hz traces, and fail-closed unknown terms.
2. Add failing controller tests proving PREGRASP requires a later bilateral open
   measurement and emits no arm target early; derive the runtime tolerance from
   preflight output rather than hard-code it.
3. Add failing tests for exact frozen waypoint calculation, required current
   orientation, world-Z-only INSERT, SETTLE pose revalidation, and action-ordered
   evidence. Later source motion must not move the waypoints.
4. Add failing tests that CLOSE remains CLOSE without contact, CONTACT_SETTLE
   requires current `probe_qualified_now`, and probe completion cannot issue a
   later LIFT/HOLD action.
5. Add preflight parent tests for immutable identity, create-only output,
   timeout/nonzero exit, strict finite JSON, trace completeness, exact action
   counts, and independent recomputation of every GO conjunct.
6. Only after preflight GO, add the exact filled diagnostic config and
   contact-profile parent validator tests. Compare against the hash-pinned failed
   native close-only config and enumerate every reviewed trajectory/fixed-frame
   difference.
7. Before a filled run, add production-order tests proving sensor readiness and
   zero initial reported contact are checked before the first action is applied,
   close evidence is bound to the applied finger action, and terminal non-null
   actions are rejected before application.
8. Run each new test red before implementation, then run the focused controller,
   preflight, contact, loop, main, config, and parent suites.

## Filled Runtime And Evidence

- Use normal production `main.py`, task/controller factories,
  `build_isaac_fluid_evaluation_loop`, current sensors, writer audit, and
  containment sampling. Do not create a second physics or control loop.
- After preflight GO, add one non-Isaac geometry-aware close-only parent launcher.
  It may reuse parsing,
  lifecycle, and artifact helpers from the native launcher, but it must have its
  own profile-aware terminal validator and decisions:
  `GEOMETRY_AWARE_CLOSE_ONLY_PASS`, `GEOMETRY_AWARE_CLOSE_ONLY_FAIL`, and
  `PROBE_RUNTIME_ERROR`.
- Pin the new config, unchanged candidate asset, Franka USD, parent launcher,
  imported lifecycle helper, controller files, robot adapter, main loop, contact
  monitor, and acceptance implementation before launch and again after child
  exit.
- Preserve stdout/stderr, the existing child PID/run-id owner binding, exactly one
  terminal episode, all contiguous observations, identity closure, and artifact
  hashes in a fresh immutable attempt directory. Do not claim a nonce unless the
  owner schema and main CLI are explicitly expanded and tested.
- Make the contact monitor the sole source-motion acceptance authority. It uses
  the configured vessel axis and one origin through close; controller-local full
  quaternion drift may stop motion conservatively but is not a second acceptance
  metric.

## Decision Contract

`GEOMETRY_AWARE_CLOSE_ONLY_PASS` requires all existing contact-acquisition probe
checks plus:

- selected profile is exactly `contact_pick_v1`;
- frozen top-down trajectory evidence exactly matches the reviewed config;
- the gripper was confirmed fully open before the first arm action;
- no contact occurred in PREGRASP, ALIGN, INSERT, or SETTLE;
- terminal phase is `CONTACT_SETTLE`, close was emitted and observed, and lift,
  hold, pour, terminal action, source writer, kinematic target, and attachment
  counts are zero;
- current bilateral contact is valid for five distinct 600 Hz steps with the
  existing attribution, normal, side, height, speed, and impulse checks;
- cumulative source translation and tilt remain within 2 mm/1 degree;
- every sampled partition contains exactly 3,600 particles in source and zero in
  target, transit, tabletop spill, below-table, and non-finite categories.

Any authoritative left-finger, right-finger, or hand contact before close, source
motion violation, spill, no-contact timeout, or
nonqualifying close is `GEOMETRY_AWARE_CLOSE_ONLY_FAIL`. Missing sensor authority,
identity drift, malformed evidence, incomplete writer coverage, prohibited
applied action, controller/action disagreement, wrong trajectory, or lifecycle
failure is `PROBE_RUNTIME_ERROR` and carries no physical conclusion. Contact
claims are limited to the three instrumented robot bodies; source-table support
contact is not classified as an unexpected robot contact.

A PASS proves only one brief bilateral close observation. It does not prove
load-bearing grasp, retention, lift, transport, pour, repeatability, or production
readiness. Only a PASS authorizes a separately reviewed lift-only plan.

## Expected File Scope

- `controllers/atomic_actions/contact_pick_controller.py`
- `controllers/pour_controller.py`
- one parent-sealed trajectory-preflight tool and focused tests
- production-order changes in `main.py` and/or the fluid loop only if required by
  the pre-apply interlock tests
- one new geometry-aware diagnostic YAML
- one new geometry-aware parent launcher
- focused controller, config, and parent tests
- this plan document

The preflight may create temporary calibration geometry and diagnostic collision
overrides, but these must be described and hashed in its report and never enter
the filled config or asset. No persistent USD, robot, fluid threshold, or
unrelated controller change is expected unless a failing test demonstrates a
concrete integration defect.

## Attempt 008 Calibration-Only Amendment

Attempt 007 ended with a valid pre-interaction NO-GO before the temporary
calibration body was collision-enabled. The body remained geometrically
separate from every obstacle and was strictly between the open finger pads, but
the pre-enable budget found only `0.01029027164088453 m` from `panda_hand` and
`0.02047216060777718 m` from `panda_link7`, versus a conservative
`0.021099999552965164 m` requirement after their `0.02 m` contact-offset values
and the 1 mm numerical margin. The table's authored PhysX contact offset is the
auto-computed `-inf` sentinel, so its effective bound correctly remained
unresolved. No calibration collision, shadow trajectory, source approach, close,
lift, or pour occurred.

Do not resolve this by changing any contact offset, excluding a physically
compatible obstacle from evidence, reducing the numerical margin, or assuming an
undocumented PhysX default.

Three independent reviews rejected the initial proposal to pair-filter the
temporary body from non-finger colliders. Relationship readback alone would not
prove that PhysX installed the filter, the existing three robot contact sensors
cannot observe every proposed counterparty, and the current abort schema cannot
truthfully represent a failed first enabled step. Attempt 008 therefore must not
add `FilteredPairsAPI` or weaken the offset-aware budget.

The table term has a narrower resolution. `/World/table` has no enabled rigid
body ancestor and the temporary calibration body is also authored without
`RigidBodyAPI`; PhysX does not generate a contact pair between two static
colliders. Record and parent-validate collision roles per enabled collider, not
from a trusted label or root path. A static-static pair does not use either
contact offset but must retain strictly more than the unchanged 1 mm geometric
margin. Every dynamic or kinematic collider continues to require the existing
sum of both contact-offset bounds plus the numerical margin.

Close this classification over the whole composed stage immediately before
authoring the calibration layer. Enumerate every `CollisionAPI` prim and classify
`collisionEnabled=false` first. For each enabled collider, resolve the nearest
`RigidBodyAPI` owner from the collider itself and its ancestors without skipping
a disabled owner: no owner is static, a disabled nearest owner is disabled and
inapplicable, an enabled owner with `kinematicEnabled=true` is kinematic, and any
other enabled owner is dynamic. Never climb past a disabled nearest owner.
Partition the exact paths into the two intended finger colliders, compatible
obstacle colliders, static colliders, disabled colliders, and the known
colliderless-body inventory. Reject every unclassified, multiply owned, or
drifting path. Do not assume that `/World/beaker1` is kinematic: classify all of
its enabled colliders from the candidate stage. `panda_link8` remains separate
clean zero-collider evidence rather than an obstacle with invented bounds.

The fixture placement also changes, but only within the temporary diagnostic
geometry. Preserve the calibrated width and offsets while changing its size from
`[0.004, 0.070, 0.004] m` to `[0.002, 0.070, 0.002] m` and translating it from
the reset tool frame by exactly `[0.009, 0.0, 0.006] m` in tool coordinates.
Planning geometry predicts approximately `0.02231 m` hand clearance versus the
unchanged `0.02110 m` requirement. The runtime, not that prediction, remains the
authority. It must independently prove that the complete box remains strictly
inside the cooked left/right finger overlap along both tool-X and tool-Z, remains
strictly between the pads along tool-Y, and passes every compatible-obstacle
offset budget before collision can be enabled.

The row-affine placement formula is normative:

```python
body_world = row_translation([0.009, 0.0, 0.006]) @ reset_tool_world
```

The static-static exception resolves the calibration-body/table pair only. The
later filled run contains dynamic robot/table pairs and therefore still needs an
effective table offset. Isaac's tensor API does not expose static actors, and
neither a kinematic adapter nor a transient `RigidBodyAPI` may be used to
manufacture one. Use OmniPVD's direct static actor and cooked geometry instead.

### Two-Process Authority Architecture

The host parent creates a mode-0700 output root and launches the authority child
and measurement child sequentially with `start_new_session=True`. They must have
different PIDs, process-group IDs, owner files, stdout/stderr files, report paths,
and create-only artifact directories. The parent must reap the authority leader,
prove its process group empty, and validate its immutable evidence before it may
launch the measurement process group. No process, `SimulationApp`, stage, task,
world, layer, Python object, or file descriptor is shared between them.

The parent never passes the authority report path to the measurement child. The
measurement child does not enrich a table catalog or make a GO decision from PVD
data. It emits `MEASUREMENT_COMPLETE_PENDING_PARENT` plus raw, recomputable
measurement evidence. Only the host parent may join the two quiescent immutable
buffers, recompute all budgets, and emit GO or NO-GO. This removes the sidecar
TOCTOU and prevents the measurement process from laundering authority evidence.

### Disposable OmniPVD Process

Before constructing a PhysX scene, the authority child enables the hash-pinned
`omni.physx.pvd` extension and sets a fresh recording directory. It loads the
same sealed config, USD composition, Franka, stage units, gravity, physics scene,
GPU setting, solver, broadphase, tolerance scale, cooking parameters, and 600 Hz
time step as measurement. It deactivates particles before play and authors no
calibration body, source isolation, table API, attachment, controller action,
source writer, contact/rest offset, or robot command.

The capture lifecycle is exact: record the physics index after reset, enable
recording, call `world.play()` once, execute exactly one explicit
`world.step(render=False)`, call `world.pause()` once, disable recording, and
perform at most eight non-rendering finalization updates while proving the
physics index does not change. Record every play, pause, step, update, reset,
source-write, and robot-command count. The failed zero-step planning experiment
is not authority; a zero-step or multi-step capture is rejected.

After recording is disabled, exactly one new finalized OVD must exist. A
`tmp.ovd` may be present only as a stable, non-authoritative plugin scratch file:
recording must be false, its inode must differ from the finalized OVD, its size
and mtime must remain unchanged across the finalization barrier, and it must
never be selected or referenced by the report. More than one finalized segment,
a changing temporary file, or an unclassified file fails closed. Conversion must
produce exactly the expected `stage.usda`, `scene.usda`, and `shared.usda`
closure with relative in-root dependencies and no symlink, hardlink, device,
socket, FIFO, absolute asset path, or path escape.

The identity seal includes the resolved Isaac interpreter, config, complete USD
composition, implementation files, `omni.physx.pvd` extension code, converter,
loaded PhysX/PVD shared objects, Carbonite/Kit build identifiers, and all scene,
solver, tolerance, GPU, broadphase, and cooking settings that can affect shape
cooking or serialization. Unknown loaded plugin paths or settings are a runtime
error. Any traceback, sanitizer message, segfault marker, or unallowlisted error
in authority stderr is also a runtime error even if the child exits zero.

### Parent PVD Parsing Contract

After authority process-group quiescence, the parent opens every artifact with
no-follow semantics, requires a regular single-link file inside the private root,
reads it once, and hashes that immutable byte buffer. It reparses the converted
closure and requires the converter-version-specific schema observed in the
pinned planning captures: exactly one time-zero actor named
`/World/table/surface/mesh`, raw class `PxRigidStatic`, type `eRIGID_STATIC`, and
exactly one `PxShape`. A different raw class is not silently normalized even if a
viewer can derive the same display type.

The shape must have finite nonnegative float32 `omni:pvd:contactOffset`, zero
rest offset, identity shape local pose, simulation and scene-query flags, and one
`PxTriangleMeshGeometry`. Parse the shared cooked points, mesh identity, geometry
scale, geometry local pose, actor global pose, and all referenced handles.
Reconstruct the actual cooked world bounds from those values with conservative
outward float32/transform interval error. Do not use the actor's display
`worldBounds` as cooked geometry: the planning captures show those bounds are
inflated by exactly 1.01 about their center. Require the same center and 1.01
half-extent relation within the derived error bound, then retain the reconstructed
geometry bounds as authority.

Three independent planning segments produced the same contact offset
`0.0016397404251620173 m`. Their reconstructed cooked bounds were approximately
`[-0.92391846,-1.33221931,0.69077349,1.42102487,1.31249079,0.77276064]`, matching
Attempt 007's live query, while the PVD display bounds were
`[-0.9356432,-1.3454428,0.6903635,1.4327495,1.3257143,0.7731706]`. These values
validate the proposed parser but are never accepted as sealed-run constants.

Bind the PVD record to the sealed USD collider by exact actor name, collision
prim path, prim-stack asset hashes, static rigid-body ancestry, composed world
matrix, geometry type, point/mesh digest, and complete PVD actor/shape inventory.
The fresh measurement child records the same USD-only identity and proves that
the table matrix is constant at every measurement sample; it never queries or
authors a table rigid body. The parent rejects identity, transform, topology,
shape-count, flag, offset, rest-offset, plugin, setting, error-bound, or artifact
drift. For arithmetic it rounds the float32 contact offset and every geometry
interval outward before applying the unchanged 1 mm numerical margin.

### Fail-Safe Calibration And Shadow Isolation

Fixture collision enablement is one exception-safe transaction. While paused,
the child checks open state and all pre-enable budgets, enables collision in the
anonymous calibration layer, updates composition without changing physics index,
and repeats every budget. It then executes exactly one enabled physics step and
reads a global PhysX contact stream covering the fixture and every counterparty,
not only the three existing robot sensors. A `try/finally` must pause physics and
disable fixture collision before propagating any contact, query, callback, or
serialization error. The same cleanup guard remains active throughout the remote
close calibration.

An unexpected first-step or later fixture contact is reported truthfully as
`interaction_prevented=false`, with first contact step, both body and collider
paths, cleanup outcome, and no claim that the enabled interval was interaction
free. Reports distinguish `PRE_ENABLE_ABORT`, `ENABLED_CONTACT_ABORT`,
`ENABLED_EXCEPTION_ABORT`, `CLEANUP_ERROR`, and normal completion. Every abort
contains the calibration setup evidence accumulated so far. Cleanup failure is
always `PROBE_RUNTIME_ERROR` and cannot be overwritten by an earlier NO-GO.

After fixture cleanup, the child authors a separate anonymous shadow-isolation
layer. It disables every originally enabled non-robot collider, including source,
target, table, cabinets, and props, while preserving every robot collider. The
source may be made kinematic solely to hold its frozen pose, but no kinematic
target or later pose write is permitted. At each checkpoint, verify exact layer
opinions, unchanged physics index, unchanged source pose, unchanged robot shape
inventory, and direct PhysX absence of every non-robot simulation/query shape.
`FilteredPairsAPI`, contact-report suppression as a substitute for isolation, and
sensor-only absence claims are forbidden.

The shadow therefore cannot physically interact with scene objects. Parent-side
replay still evaluates the realized robot collider sweep against the complete
pre-isolation environment inventory. Static geometry and offsets come from the
PVD closure; dynamic/kinematic geometry and offsets come from unmodified live
property queries taken before isolation. Unknown ownership, geometry, transform,
offset, cooking precision, or minimum distance for any originally enabled pair
makes GO impossible. The isolation layer is removed under the same no-step,
USD-absence, PhysX-absence, edit-target, and sublayer-order cleanup contract as
the calibration layer.

Projection containment is necessary but not sufficient. For each side, exactly
one intended finger collider must contain the complete tool-X/tool-Z fixture
footprint by more than the derived cooked-projection error bound and must furnish
the inner tool-Y boundary used by the gap calculation. With fixture collision
disabled, cast tool-Y rays from the center and four corners of each fixture face;
all five nearest support hits must resolve to that same collider, have the
expected inward normal sign, and agree with its cooked inner boundary within the
derived error bound. The first attributed contact on each side must be from that
preselected collider, have the expected normal direction, and project strictly
inside the 2 mm fixture face rather than onto an edge. Revalidate this witness at
the consecutive no-contact/contact samples used for the offset bound.

Author the calibration body in a dedicated anonymous sublayer, not directly in
the persistent diagnostic session layer. Every collision-enabled toggle must
explicitly target that layer. After remote calibration, pause without stepping,
disable collision, remove the sublayer, update composition, prove the body is
absent, and perform a non-stepping PhysX overlap query around the former body
bounds that resolves no shape to the calibration path. Restore the exact prior
edit target and session sublayer order, and only then begin the shadow trajectory.
No calibration geometry or placement change enters the source asset, Franka,
shadow trajectory, or filled configuration.

### TDD And Implementation Order

1. In `tests/test_geometry_aware_trajectory_preflight.py`, add red tests for the
   exact tool-frame translation, 2 mm non-width dimensions, unchanged 70 mm
   width/contact/rest offsets, and full-box containment inside the cooked
   bilateral tool-X/tool-Z overlap. Missing overlap, equality at a boundary,
   a margin at or below the derived cooked-projection error bound, wrong row-
   matrix translation order, or loss of tool-Y placement must fail closed.
2. Add red budget tests for explicit interaction modes. An unresolved offset may
   be inapplicable only for an independently classified per-collider static-
   static pair;
   dynamic, kinematic, unknown, or mismatched roles retain the old offset-aware
   failure. Both modes still require strictly positive remaining clearance.
3. Add red inventory tests for complete enabled-collider partitioning, runtime
   target classification, exact static ancestor chains, duplicate ownership,
   disabled colliders, an unexpected scene collider, and clean colliderless
   `panda_link8`. Every non-finger collider-bearing Franka body remains an
   offset-budget obstacle; finger colliders are the only intended contacts.
4. Add red lifecycle tests for a dedicated anonymous calibration sublayer,
   explicit edit-target selection on every collision toggle, no hidden physics
   step during removal, exact layer cleanup, USD absence, a PhysX overlap query
   free of the calibration path, and calibration-body absence before the first
   shadow action. Include reset/recomposition and wrong-layer failure cases.
5. Add red support-witness tests for five same-collider ray hits per side,
   cooked-boundary agreement, normal direction, unique first-contact collider,
   and contact-point containment inside the fixture face. Aggregate or mixed-
   collider projection evidence, edge contacts, stale rays, and nonconsecutive
   onset samples fail closed.
6. In
   `tools/labutopia_fluid/run_geometry_aware_trajectory_preflight.py`, implement
   the pure translated-body spec, exact collider inventory, support witness,
   role-aware budget, and layer lifecycle. Preserve the first-enabled-step empty
   contact check and all existing source-isolation gates.
7. Add red tests and implementation for the disposable OmniPVD authority child:
   a distinct process group, exact one-step lifecycle, stable temporary-file
   classification, create-only/private outputs, complete dependency closure,
   immutable OVD/layer hashes, unique converter-specific static actor and shape,
   conservative cooked-mesh reconstruction, 1.01 display-bound validation, and
   rejection of identity drift, malformed conversion, stderr errors, or any
   preliminary robot/source action.
8. Add red tests proving the fresh measurement child receives no PVD path or
   value, starts in a distinct process group and fresh world, emits only
   `MEASUREMENT_COMPLETE_PENDING_PARENT`, never authors or queries table physics
   APIs, and supplies the USD identity and static transform needed for the parent
   join.
9. Add red tests for exception-safe fixture enablement and anonymous shadow
   isolation: global contact coverage, immediate pause/disable on every exception,
   truthful enabled-contact aborts, full non-robot collision disablement, direct
   PhysX shape absence, no filtered pairs, no physics-index drift, and cleanup on
   normal and failing paths.
10. Extend parent validation to reconstruct the translated body matrix and all
   three projection intervals from the sealed body spec, cooked finger catalogs,
   collider transforms, support hits, role chains, and every obstacle transform;
   independently reparse the PVD artifacts, join only quiescent immutable buffers,
   and recompute the complete pre/post and swept-clearance budgets plus both layer
   cleanup contracts.
   Put this `calibration_setup_evidence` bundle in both completed and early-abort
   reports so a NO-GO does not discard the parent inputs.
11. Run the focused preflight tests red then green, the adjacent controller and
   runtime suites, `py_compile`, `git diff --check`, and identity validation.
   Update the config and preflight implementation hashes only after all changes
   are final.
12. Rerun architecture, completeness, and physical-risk reviews against this
    exact contract. Do not launch while any review returns revise or reject.
13. Launch one fresh immutable Attempt 008. A runtime error or NO-GO stops the
   work. Only a fully sealed `GEOMETRY_AWARE_TRAJECTORY_PREFLIGHT_GO` may
   authorize planning the single filled close-only attempt; this amendment does
   not itself authorize source interaction.

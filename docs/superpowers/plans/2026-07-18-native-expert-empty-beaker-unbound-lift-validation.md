# Native Expert Empty-Beaker Unbound Lift Validation Plan

## Product Decision

This validation replaces the blocked friction-causality claim with the product
acceptance criterion below:

> The empty `beaker2` Expert task, using sealed repository-local scene and
> Franka assets, performs a native PhysX pick, lift, and pour motion without
> application-authored attachment, kinematic following, source pose/velocity
> takeover, or source/robot collision filtering.

This experiment may claim an observed dynamic PhysX empty-beaker lift with
bilateral finger contact. It must not claim that friction is the unique or
necessary physical cause of the lift. The zero-friction ablation and its missing
pair-material/cache authority are explicitly out of scope.

The prior causal probe remains archived as a correctly reported
`PROBE_PROTOCOL_NO_GO`; this plan does not weaken or reinterpret that result.

## Acceptance Decision

The final parent decision has fixed precedence:

1. `PROBE_RUNTIME_ERROR`: launch, timeout, identity, parse, artifact, shutdown,
   or unexpected application error.
2. `NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO`: an observer/audit authority is missing,
   an unknown source/robot relationship is found, or the observer changes a
   non-report scene property.
3. `NATIVE_EXPERT_UNBOUND_LIFT_FAIL`: the clean native Expert terminal outcome
   or measured physical acceptance gates fail.
4. `NATIVE_EXPERT_UNBOUND_LIFT_PASS`: every audit and physical demonstration
   gate passes.

`PASS` means all of the following, not a causal friction conclusion:

- physical source `/World/beaker2/mesh` is a rigid, collision-enabled,
  gravity-enabled, awake, non-kinematic body participating in the active
  physics world by live PhysX readback; an explicit simulation-owner relation
  is optional;
- a sealed source/finger topology gate observes simultaneous, opposing,
  mid-sidewall contacts from both enabled finger sides in the native close/lift
  window, with no palm, arm, target, or other source contact;
- an explicit source/Cube `LOST` event occurs after the first integrated native
  event-5 lift action and before the source rigid-body origin rises at least
  `0.12 m` above its stable supported pre-lift baseline;
- the production controller enters `POURING`, emits and applies native
  `PourController` event 2 with a nonzero joint-6 velocity target, and the
  source remains above the lift threshold and rotates at least `50 degrees`
  after that action integrates while it has no forbidden source contact;
- source/robot attachment, joint, filter, and post-reset writer audits are
  clean; and
- after threshold crossing, exactly 60 contiguous post-step samples, inclusive
  of the threshold sample, remain above the threshold with no source/Cube
  recontact.

The source need not remain in bilateral contact during the tilt/pour phase.
Contact evidence only establishes observed physical finger/source interaction;
it does not establish a force decomposition or a friction-only claim.

## Minimal File Scope

- `config/diagnostic_level1_pour_native_empty_unbound_lift_v1.yaml`
- `tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py`
- `tests/test_native_expert_empty_beaker_unbound_lift_probe.py`
- this plan

No production controller, task, robot, USD, material, or fluid file may change.
The new runner must not call `main.py`, because it needs observer-only evidence
without changing main's public CLI or non-fluid behavior.

## Input And Runtime Contract

- Production projection: exactly `config/level1_pour.yaml` after removing only
  diagnostic identity, local output-routing fields, and the explicit local
  asset metadata. The task, controller, object-placement ranges, and Expert
  control remain unchanged.
- Scene: diagnostic-only local substitution
  `assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_localized_20260707/lab_001.usd`,
  SHA-256 `b3861b5a17945abe401062a04125969c3a63b0f8a0a5ce0026a461dbdfc935f2`,
  referenced at `/World`. It is the localized raw root, not the tabletop layer,
  so normal seeded `PickPourTask.reset()` placement remains authoritative. The
  production projection retains the original scene path; this is a sealed
  diagnostic scene substitution, not byte-identical original-scene parity.
- Robot: `assets/robots/Franka.usd`, SHA-256
  `312a326e338949fb40fd245886508cc52cc47e2bebd696e99c7dcdd3d3a7f90b`,
  mounted at `/World/Franka`. This is the repository-standard asset already
  used by successful Franka diagnostics. Its root hash and resolved USD
  dependency closure are sealed before and after each treatment. The only
  non-repository USD resolver dependency permitted for the robot is the
  hash-pinned local Isaac Sim 4.1 runtime `OmniPBR.mdl`; remote and all other
  external dependencies remain rejected. The report does not claim byte
  identity with the unavailable remote Isaac URL.
- Task/controller: production `PickPourTask` and `PourTaskController` through
  `factories.task_factory.create_task` and
  `factories.controller_factory.create_controller`.
- Runtime: pinned Isaac Sim `4.1.0.0` Python interpreter, headless,
  `World(stage_units_in_meters=1.0, physics_prim_path="/physicsScene",
  backend="numpy")`, actual physics dt `1/60 s`, stage units `1.0`, and
  gravity `[0, 0, -9.81]`.
- Placement seed: `20260718`, applied immediately before the normal task reset.
- Maximum production transitions: `1500`; child timeout: `900 seconds` per
  treatment. This operational wall-clock cap covers Isaac startup, evidence
  serialization, cleanup, and shutdown; it is not a physics-step or acceptance
  threshold.
- Video: a non-authoritative two-camera composite MP4 sampled every two normal
  production transitions. Failure to encode the requested video is a runtime
  error; video cannot change a physical decision.

The parent is Isaac-free. It runs two fresh sequential children from frozen
canonical diagnostic JSON with the same seed:

- `control`: production-projection run with no probe-authored report API;
- `instrumented`: identical run with only the report-only delta below.

For each child independently, the parent and child seal the config, runner and
transitive Python implementation closure, localized-scene dependency closure,
pinned local-Franka dependency closure, runtime version, and scene contract
before and after the run. The parent binds a run nonce and parent/child PIDs into every
artifact, proves process-group quiescence after each child, and creates the
only final `report.json`. It refuses an existing output root. The instrumented
child alone writes the requested MP4. The parent compares both action/phase
ledgers and live source origin pose/orientation/velocity traces at aligned
world indices; any difference beyond `0.1 mm`, `0.1 degrees`, `1 mm/s`, or
`0.1 deg/s` is `NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO`.

## Observer-Only Stage Delta

The child may author only one anonymous session sublayer before task creation:

- `PhysxContactReportAPI` on `/World/beaker2/mesh`,
  `/World/Franka/panda_leftfinger`, `/World/Franka/panda_rightfinger`, and
  `/World/Franka/panda_hand`;
- `threshold=0.0` and empty `reportPairs` on those exact bodies.

The observer must restore the original edit target, call
`get_physx_simulation_interface().flush_changes()`, and catalog session-layer
paths, metadata, list operations, relationship targets, and properties. The
only allowed opinions are the report API schema application, threshold, and
empty report-pairs relation at those exact bodies. Any other authored opinion
or any observer-caused physics-step advance is `AUDIT_NO_GO`.

No source/robot material, collision, mass, gravity, damping, contact offset,
rest offset, filter, group, attachment, or transform edit is permitted.

## Dynamic Source And No-Artificial-Coupling Audit

After normal reset, construct a non-mutating `SingleRigidPrim` for
`/World/beaker2/mesh` with `reset_xform_properties=False`. Its runtime
`get_world_pose`, linear velocity, angular velocity, and low-level
`IPhysxSimulation.is_sleeping` readbacks are the sole source motion authority.
The lift baseline and threshold refer to this body's rigid-body origin, not a
USD geometry center or task-state value. Resolve and seal the source local COM,
all enabled source/finger/hand/support colliders, their owning rigid bodies,
the active stage ID, scene ownership, and actual dt/gravity before stepping.

Before reset and after reset, record a complete source/robot relation graph.
After every task/controller/action boundary and terminal or no-action retention,
freshly compute a versioned canonical SHA-256 fingerprint of that complete graph.
The child fails closed on a boundary fingerprint that differs from the self-hashed
post-reset graph; the parent independently recomputes that baseline hash and
rejects missing, malformed, or mismatched boundary fingerprints. This avoids
serializing hundreds of duplicate full inventories while retaining the full
pre-reset/post-reset evidence and mutation history. The pre-reset and post-reset
graphs are each independently required to be coupling-clean; the post-reset graph
is the invariant baseline for normal production boundaries, so task-owned camera
initialization is not mistaken for a source/robot physical change. Install a USD
mutation notice before reset; it records every changed
source/robot/support relation/property path during task, controller, action,
and close boundaries. Source roots are `/World/beaker2` and
`/World/beaker2/mesh`; robot root is `/World/Franka`; the only permitted static
support root is `/World/Cube`.

The audit rejects any source-to-robot relationship in either endpoint order:

- USD physics joints and relationships whose body endpoints cross source and
  robot roots;
- PhysX/fixed/D6/surface-gripper/attachment-like schemas or relationships with
  cross-root body endpoints;
- `UsdPhysics.FilteredPairsAPI` targets crossing source and robot roots,
  inspected on the source/robot roots, descendants, and ancestors through
  `/World`; and
- collision-group collection membership, filtered groups, masks, and merge
  groups that make a source/robot pair filtered or otherwise change their
  collision treatment.

The relation graph rejects direct or transitive source-to-robot coupling and
every source-to-nonrobot driving relation, force-field membership, or external
constraint not explicitly identified as ordinary static support. It records
unrelated constraints/groups rather than treating their mere presence as a
failure. Empty built-in joint `proxyPrim` slots and a source-free empty joint
body slot are catalogued but are not graph endpoints; they are normal USD
articulation topology. Unsupported endpoint-bearing relations, collection
membership, relationship, or runtime identity are `AUDIT_NO_GO`, not a pass. A
create-and-remove coupling is detected by the mutation notice and action-boundary
inventories and is also `AUDIT_NO_GO`.

After the normal placement reset, open a zero-write epoch. Audit these command
surfaces for the physical source body and reset root:

- `SingleRigidPrim` world/local pose and linear/angular velocity setters;
- plural prim-view pose/velocity setters;
- physics-view kinematic targets, dynamic targets, transforms, velocities,
  forces, torques, impulses, and force-at-position methods;
- `ObjectUtils.set_object_position` for `/World/beaker2`;
- the controller's `Gripper.add_object_to_gripper`,
  `update_grasped_object_position`, and `release_object` methods.

The one normal reset-root placement occurs before the zero-write epoch. During
the epoch, all source body/root writer, target, force/impulse, and
software-gripper call counts must remain zero. A raw source Xform, rigid-body,
collision, gravity, mass, or force-property change at an action boundary is
also rejected. Missing required wrapper authority is `AUDIT_NO_GO`. This audit
demonstrates that this application run did not author artificial following; it
does not claim omniscient visibility into closed PhysX internals.

At the same boundaries, snapshot and require byte-identical source, finger, and
hand body/collider physics attributes and material-binding relationships:
enabled state, kinematic state, gravity, mass/damping, collision/contact/rest
offsets, collision/filter/group relationships, and material bindings. A sealed
local collider may explicitly have no physics-purpose material binding, or an
authored empty physics-purpose binding, and is recorded as using the PhysX
default rather than edited. A nonempty physics-purpose binding that cannot be
resolved remains `AUDIT_NO_GO`. This does not relax the no-material-edit,
coupling, or source-writer audits and does not establish friction coefficients.

Seal `/World/Cube` as immutable static support before reset: world transform,
rigid/kinematic state, velocity, force/constraint membership, collision and
material properties, and group/filter relationships. Include it in the mutation
notice and every boundary snapshot. Any support movement or mutation during the
zero-write epoch is `NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO`.

## Physical Observation

After each and only each production `world.step(render=True)`, deep-copy and read
`get_full_contact_report()` exactly once before `task.step()`. Preserve raw
headers, contact data, and friction anchors in a chained JSONL trace. Resolve
and seal all enabled descendant source/finger/hand/support colliders and their
actor ownership before stepping. Every header must have the sealed stage ID,
finite vectors, valid disjoint ranges, and resolved actor/collider ownership.

Classify each header pair as:

- `LEFT_SOURCE`
- `RIGHT_SOURCE`
- `SOURCE_SUPPORT` for `/World/beaker2/mesh` and `/World/Cube`
- `SOURCE_OTHER`
- `ROBOT_ENVIRONMENT`
- `UNRESOLVED`

The first post-reset report starts an observer history rather than proving that
every current contact began in that step. It may bootstrap an exact `PERSIST`,
`LOST`, or `PERSIST,LOST` sequence for any sealed, resolved pair, preserving the
raw event and classification. This does not relax acceptance: a first-observed
source/finger, `SOURCE_OTHER`, or `ROBOT_ENVIRONMENT` contact cannot support a
PASS. Source support still begins only with an explicit current support report,
becomes lost only through an explicit zero-data `LOST` report while the awake
source is still reportable, and may never reappear. Missing reports leave state
`unknown` and produce `AUDIT_NO_GO`; they are never treated as support loss.
Every later unseen `PERSIST`, missing active pair, malformed range, unknown
identity, or noncontiguous raw physics index is `AUDIT_NO_GO`.

The sidewall topology gate evaluates current source-local source/finger contact
points from the first integrated close action through threshold crossing. It
requires both sides on sealed enabled finger colliders in the same report, all
points in the source middle height band `[0.20, 0.80]`, outside a `1 mm` pad
edge margin, on opposite source sides along the live finger-closing axis, and
with `abs(dot(raw_normal, source_up)) <= 0.25`. Sealed bounds and transforms
are validated every observation, but inward-face selection is required only for
a collider with a current source/finger pair; unused collider ambiguity cannot
block a pre-contact sample. An ambiguous participating collider remains
`AUDIT_NO_GO`. The gate rejects every `SOURCE_OTHER` pair except source/Cube
support before loss, and every finger/hand environment contact in that interval.
This excludes rim, underside, palm, target, and environment carry without
asserting a friction-force decomposition.

All geometry predicates are deterministic float64 calculations. Freeze source
and finger local bounds before interaction. Define `source_up` as the signed
source-local bound axis whose reset-world direction has maximum anti-gravity
dot product. Derive each point's normalized source height from its current
source-local coordinate and the frozen bound extent. Derive the live closing
axis from current left/right aggregate finger-bound centers projected
perpendicular to `source_up`; reject zero projections. Select each finger's
unique inward local bound face, normalize every raw contact normal, and reject
degenerate normals, zero-point current manifolds, ambiguous faces, or points
outside the two tangential pad-edge margins. Every sealed pair follows a
canonical `FOUND/PERSIST/LOST` lifecycle with contiguous physics indices;
missing active pairs or malformed ranges are `AUDIT_NO_GO`.

Each trace transition `k` contains `pre[k] -> post[k]`, then the normal
task/controller result and the action applied after `post[k]`; a non-null action
integrates only in transition `k+1`. The trace records source rigid-body
origin/velocity/orientation, controller phase, native pick/pour events, action
receipt/hash, source support state, classifications, and world index.

`k_close_action` is the first applied native pick event-4 action.
`k_lift_action` is the first later applied native pick event-5 action;
`k_lift = k_lift_action + 1` is its first integrating transition.
`pre[k_lift]` must end a ten-transition stable supported window and is the
fixed lift baseline. A stable sample has current source support, source awake,
linear speed `<= 0.001 m/s`, angular speed `<= 0.1 deg/s`, and origin
displacement from the preceding post-state `<= 0.0001 m`. `k_loss` is the first
explicit support `LOST` transition after `k_lift`; `k_rise` is the first later
post-state at least `0.12 m` above the baseline. `post[k_rise]` through
`post[k_rise + 59]` are the exactly 60 retention samples. Every retention step
performs the one immediate full-contact read/classification and rejects support
headers, including transient `FOUND,LOST` recontact. The parent recomputes all
indices and rejects a discontinuous world/action ledger.

`k_pour_action` is the first applied native `PourController` event-2 action
whose decoded joint-6 velocity target is finite and nonzero; it integrates at
`k_pour_action + 1`. The pour rotation baseline is `pre[k_pour_action + 1]`;
the first `>= 50 degree` sample must occur strictly after that integration,
remain above the lift threshold, and satisfy the no-forbidden-source-contact
gate. The result is labelled "native pour-command plus post-command cup
rotation", not a liquid-transfer or friction-causality claim.

The loop order mirrors the original non-fluid path:

1. Construct World, default Franka, scene reference, and `ObjectUtils`.
2. Install the report-only session layer.
3. Construct task; seed; execute normal task reset; construct controller.
4. Open the zero-write epoch.
5. Repeat `world.step -> report read -> task.step -> controller.step ->
   apply each non-null action exactly once`.
6. Stop after normal terminal or the transition limit; never reset for a retry.
   If a structurally valid terminal precedes completion of the 60-sample
   retention window, perform only the remaining no-controller/no-new-action
   physics steps needed to complete that fixed window.

The child writes a nonce/PID/identity-bound provisional trace/report and video
frame-to-world-index map, then closes the controller/collector while the audit
remains active and proves that close did not advance the world. It then writes
the cleanup receipt/artifact manifest, closes `SimulationApp`, and exits. The
parent reads artifacts only after child quiescence, rejects missing/stale/
non-finite/malformed or identity-mismatched artifacts, independently recomputes
every decision component from the trace, and rejects any provisional-summary
contradiction.

## Test-Driven Delivery

1. Add failing pure tests for diagnostic projection/frozen bytes, exact child
   command, decision precedence, and create-only artifacts.
2. Add failing evaluator tests for dynamic source/scene authority, clean/direct
   and transitive cross-root attachment/filter/group inventories, raw-property
   changes, every source writer/target/force/software-gripper surface, and
   robot-side material/collision mutation, mutation-notice create/remove
evidence, compact relation-boundary fingerprints, and control-versus-instrumented
non-perturbation.
3. Add failing evaluator tests for sealed actor/collider identity, simultaneous
   bilateral middle-sidewall topology, rim/underside/palm/environment rejection,
   explicit awake support lifecycle, deterministic geometry degeneracy,
   action integration indexing, lift/support
   loss boundaries, 60-step retention, native pour event-2 receipt, and
   post-actuation threshold-retained `50 degree` rotation.
4. Add failing parser/trace tests for unknown contacts, source/Cube recontact,
   duplicate/missing action receipts, malformed report-only layer catalogs, and
   parent handling of clean physical failure versus runtime error.
5. Implement only pure evaluators and the Isaac-free parent until the focused
   CPU tests pass.
6. Implement the smallest delayed-import Isaac child using only the observer
   delta described above.
7. Run focused tests, adjacent contact tests, `py_compile`, and
   `git diff --check`.
8. Obtain architecture, completeness, and physical-risk review approval.
9. Run one fresh locked two-treatment Isaac attempt. Inspect `report.json`, trace, video
   frame count, and a human visual sample before reporting product acceptance.

## Stop Conditions

- Never add an attachment, source pose follower, collision filter, or material
  workaround to make the run pass.
- Never use synthetic attachment evidence as this experiment's source motion.
- Never rerun with tuned poses, thresholds, mass, collision, or controller
  parameters after a failure.
- A clean physical failure is informative; an unsupported observer or audit is
  `NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO`.
- A PASS authorizes the product label "native PhysX empty-beaker Expert
  pick/lift/pour-motion demonstration using the sealed local Franka asset,
  without application-authored artificial coupling." It does not authorize
  default-remote-asset parity, a filled-beaker physical-liquid claim, or a
  friction-causality claim.

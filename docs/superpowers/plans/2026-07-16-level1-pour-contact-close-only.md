# Level1 Pour Native Expert Contact-Close-Only Plan

**Goal:** Reuse the unchanged legacy native Expert command policy under the
established 30 Hz online-fluid wrapper against the hash-pinned filled 600 Hz
candidate, terminate after one current bilateral contact qualification, and
prove that no lift, pour, attachment, source write, or kinematic target action
was applied.

## Corrected Boundary

- Attempt 002 stopped before close at `0.002017180978061738 m` source motion and
  one escaped particle. It did not test native close or lift.
- Attempt 004 proves passive robot-present stability for the exact candidate:
  maximum motion `1.5699819825788087e-05 m`, maximum tilt
  `0.00017287598734470351 deg`, and all 3,600 particles in source for 2,401
  records.
- The prior cooked-clearance NO-GO evaluated a proposed side-body replacement
  topology. Its tight-clearance measurement remains risk evidence but is not a
  prior rejection of this bounded native-policy diagnostic.
- Keep vessel, Franka, colliders, material, native target policy, and task layout
  unchanged. Do not add geometry, filters, offsets, attachment, or fallback
  control.
- This is not claimed as an exact temporal replay of an authoritative historical
  empty-vessel artifact. It is the same legacy policy, pose/offset logic, and
  close lookup running at the existing online 30 Hz cadence.

The run remains unauthorized until the TDD changes and preflight contracts below
pass. Once they pass, the reviewed decision is conditional GO for exactly one
immutable close-only attempt.

## Exact Treatment

Clone the passing 600 Hz config and change only top-level `name`,
`online_fluid.execution_mode` to `contact_acquisition_probe_v1`, and
`online_fluid.performance_label`.

Pin and verify:

- candidate asset SHA-256
  `7c7667850dfc80a1d04c8649657cf9d9f5369b82e21f97b3d5c87c07ca218b02`;
- Franka USD and the participating controller/evaluation implementation hashes;
- collect mode, one attempt, 600-step pre-roll, 2,400-observation limit;
- physics 600 Hz, control 30 Hz, exactly 20 substeps per action;
- legacy `PickController` event schedule and native collect orientation/offsets;
- actual emitted native finger targets `[0.028,0.028]`, derived by the unchanged
  `beaker2` lookup rather than the inert YAML field.

Five qualifying 600 Hz steps mean only about `8.33 ms` of brief contact. Do not
call this settled, durable, or load-bearing grasp. The existing dry-vessel-only
impulse floor may qualify this diagnostic observation but cannot support a
filled-payload or retention claim.

## Blocking TDD Changes

1. Restrict contact-acquisition probe mode to `collect`.
2. Add a native-probe completion predicate in `PourTaskController`. It requires
   native profile, probe mode, controller close emitted, monitor close observed,
   current-step contact qualification, zero loss steps, and both controller and
   monitor lift flags false.
3. Evaluate that predicate in `_check_phase_success` before another native
   `forward()` call. A pending legacy event index of 5 is allowed because it only
   means lift is next; applying an event-5 action or setting the lift latch is a
   contract violation. Production mode retains its original lift path.
4. Add `last_emitted_event`/semantic action evidence to `PickController`. Prove
   probe and production modes emit identical event-0 through event-4 actions.
5. Preauthor effective ContactReportAPI on left finger, right finger, and hand
   parents before the first activating reset. During pre-roll require at least
   20 consecutive current-step raw sensor frames from all three sensors with no
   runtime auto-add warning. Hand contact is diagnostic and cannot satisfy a
   left/right role.
6. Extend `ContactFrictionDynamicVessel` with observer-only through-close motion
   accounting from one monitoring origin until lift is requested or the probe
   terminates. Motion above 2 mm/1 degree during close fails the attempt.
7. Expose `probe_qualified_now`: current gate valid, non-stale, loss steps zero,
   consecutive count at least five, and gate physics step equal to the current
   world step. Keep existing latched retention semantics unchanged for
   production.
8. Replace hard-coded no-writer claims for this probe with a policy ledger over
   actual source world/local pose, velocity, kinematic-target, attachment,
   collision-filter, and ObjectUtils source-position surfaces. Robot joint
   targets are expected and phase-authorized.
9. Gather controller evidence before final acceptance. A pure combined validator
   must require collect/native/probe identity, controller-monitor agreement on
   close/lift, current contact, no pour forward/emission, outer `FINISHED`, and no
   terminal action.
10. Strengthen contact-probe finalization to require dynamic ownership, close
    true, lift false, current qualification, cumulative containment, visual sync,
    and the observed writer ledger. Test each conjunct independently.

Required adversarial tests include post-close source motion, one invalid terminal
contact inside loss grace, hand-only/cross-sensor contact, stale sensor steps,
missing close, observed lift, pending event 5 without lift, applied event 5,
recovered substep spill, production-mode lift regression, contact-specific probe
regression, success exactly at observation limit, and exact config diff/hash.

## Production Runtime And Lifecycle

1. Use normal `main.py`, task/controller factories, and
   `build_isaac_fluid_evaluation_loop`. Do not create another controller or
   physics loop.
2. Add a thin non-Isaac parent launcher that invokes production `main.py`,
   captures stdout/stderr, enforces a timeout, and writes the only authoritative
   final report after child exit.
3. The parent requires exit 0, exactly one terminal episode, config/asset/robot/
   implementation hashes, and a matching nonce. It distinguishes a limit
   boundary reached from an episode actually terminated by the limit.
4. The production child performs normal reset, 600-step pre-roll, camera
   observations, 30 Hz controller actions, and 20 contact/containment samples per
   action. Sensor readiness and writer audit must be valid before the first robot
   action.
5. Native events 0-4 may open, approach, descend, settle, and incrementally close.
   Qualification can occur within a 20-substep block; termination occurs at the
   next 30 Hz boundary after the remaining substeps complete.
6. On terminal success, `main.py` returns no action, applies no action, and calls
   neither `maybe_attach` nor `commit_action`. The parent validates that no event-5
   forward, lift action, or pour action occurred.
7. Preserve child logs, composed config, observation/episode JSONL, controller
   and attachment evidence, sensor/writer audit, runtime identity, and hashes in
   one immutable attempt directory. `expert_episode_accepted=false` is expected;
   contact-probe acceptance is a separate result.

## Decision Contract

`NATIVE_EXPERT_CLOSE_ONLY_PASS` requires:

- clean parent-sealed lifecycle and one completed attempt;
- exact native/collect/probe identity and pinned physical/control closure;
- authoritative sensors and observed writer ledger;
- controller and monitor close true, lift false, no applied event-5 action, no
  pour invocation, and no terminal action;
- current five-step bilateral exact-body/external-shell qualification with valid
  normals, band, side projection, speed, and declared dry-only diagnostic impulse;
- cumulative through-close motion within 2 mm/1 degree;
- every sampled pre-pour partition complete with source=3,600 and every
  non-source/non-finite maximum zero.

Outcomes remain distinct:

- lifecycle, sensor, readback, attribution, or audit failure:
  `PROBE_RUNTIME_ERROR`, no physical conclusion;
- pinned native prefix causes movement/spill/unexpected contact, timeout, or no
  current bilateral qualification: `NATIVE_EXPERT_CLOSE_ONLY_FAIL`;
- applied lift/pour/source-writer/kinematic action:
  `PROBE_CONTRACT_VIOLATION`, stop pending review.

A PASS means only `brief_bilateral_contact_observed=true`. It does not establish
continuous support, filled payload authority, load-bearing grasp, retention,
repeatability, benchmark completion, lift, transport, pour, or production
readiness. It authorizes only a separately reviewed native lift-only plan.

## Expected File Scope

- one close-only diagnostic YAML;
- minimal native cutoff/control evidence in `controllers/pour_controller.py` and
  `controllers/atomic_actions/pick_controller.py`;
- through-close/current-contact/sensor/writer evidence in
  `utils/isaac_fluid_evaluation.py`;
- combined acceptance and production ordering updates in
  `utils/fluid_evaluation_loop.py` and `main.py`;
- one thin parent lifecycle launcher;
- focused controller, contact, loop, config, main-ordering, and parent tests;
- no asset, geometry, robot trajectory, or non-contact behavior change.

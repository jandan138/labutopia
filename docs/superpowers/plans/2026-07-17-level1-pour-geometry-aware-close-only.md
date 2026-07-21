# Level1 Pour Geometry-Aware Controlled-Contact Close-Only Plan

**Goal:** Reuse LabUtopia's native `ContactPickController`, RMPFlow, task, robot,
and 600 Hz physics loop with one source-centered top-down trajectory. First run a
particle-disabled dry close with real collisions, then permit exactly one filled
close-only attempt if the dry run proves bounded contact, bounded source motion,
and correct controller behavior. Never lift, transport, or pour.

## Product Decision

The earlier zero-contact requirement is superseded. Contact between an intended
finger pad and the source during INSERT, SETTLE, PRECONTACT_SETTLE, CLOSE, or
CONTACT_SETTLE is allowed and recorded; it is not by itself a failure. The
following remain hard physical failures:

- source translation above `0.002 m` or tilt above `1 degree` from the frozen
  post-reset pose;
- any particle outside the source partition, any non-finite particle, or a count
  other than exactly 3,600 in the filled attempt;
- contact between the source and `panda_hand` or any non-finger robot link;
- robot contact with table, target, cabinet, prop, or another environment body;

The following are protocol runtime errors rather than physical conclusions:

- attachment, source pose write/following, kinematic target, teleport, collision
  filtering, collision disabling, hidden support, lift, hold, transport, pour, or
  an unreviewed fallback trajectory;
- stale/missing contact evidence, wrong action order, lifecycle failure, identity
  drift, or incomplete trace.

Here `hold` means the production post-lift HOLD phase/action. Maintaining the
latched insertion target during PRECONTACT_SETTLE is an audited arm-settle action,
not that prohibited phase.

This is a simulation product decision, not a claim that premature contact is
universally safe. A passing run proves only a bounded close in this sealed scene.

### Contact Classification

Before physics play, seal exact actor, body, and collider path sets from the
composed USD inventory and reconcile them with live PhysX shapes. Derive and hash
the intended pair set from the exact left/right finger-pad colliders and source
external-shell colliders. Also seal the exact expected reset-baseline source/table
collider pairs in config; the child may not learn an allowlist from observed
contacts. Classify every same-step contact occurrence in canonical collider-path
and point-instancer-index order:

| Class | Rule | Result |
| --- | --- | --- |
| `BACKGROUND` | Exact presealed reset-baseline pair, neither body is a robot body, and the pair is current in the validated baseline | Record only |
| `INTENDED_PRECONTACT` | Exact intended pad/source pair in INSERT, SETTLE, or PRECONTACT_SETTLE and every manifold gate below passes | Allow and latch |
| `INTENDED_CLOSE_CONTACT` | Exact intended pad/source pair in CLOSE or CONTACT_SETTLE and every close-contact manifold gate below passes | Allow; only current qualified pairs count toward success |
| `PROHIBITED_CONTACT` | Any resolved robot-involved pair not explicitly allowed, any otherwise intended pair with a finite gate breach, or any new resolved source-involved non-robot pair absent from the baseline | Immediate physical NO-GO/FAIL |
| `UNKNOWN_CONTACT` | Any actor/body/collider path or required manifold attribute is missing, non-finite, or cannot be resolved uniquely | Immediate protocol runtime error |

For each current `CONTACT_FOUND` or `CONTACT_PERSIST` occurrence, aggregate every
header, contact point, and friction anchor for that canonical collider pair before
classification. Convert separation to penetration as `max(0, -separation)`.
Using the pinned actor-order convention, orient normal and impulse as acting on
the source; an integration test must prove that convention. Construct the inward
direction from the contact point toward the source axis at the same object-frame
height, without absolute-value or bilateral cancellation. Every intended point
must be inside the sealed object-frame grasp-height band, have inward-normal
cosine at least `0.8`, and have penetration no greater than `0.001 m`.

Compute contact-point velocity for both bodies as `v + omega x (p - com)` from
both the pre-solver state captured immediately before `world.step` and the
post-solver state captured immediately after it. The maximum finite pad/source
relative speed is the maximum Euclidean norm of the two point-velocity differences
and must be no greater than `0.008 m/s` in
INSERT/SETTLE and `0.002 m/s` in PRECONTACT_SETTLE/CLOSE/CONTACT_SETTLE. Sum
source-oriented normal impulse as the sum of each contact point's scalar
projection onto its own canonical inward normal. Friction anchors contribute only
to total impulse, defined as `sum(norm(contact_point_impulse)) +
sum(norm(friction_anchor_impulse))`; no vector cancellation is permitted. Sum
both quantities across all intended pairs and pads for the physics step. Both
step-global aggregates must be no greater than `0.001 N*s`. A negative
source-oriented normal projection beyond numeric error is a finite gate breach,
not silently clamped away. From first intended contact through the terminal
sample, `episode_normal_impulse = sum(step_normal_impulse)` and
`episode_total_impulse = sum(step_total_impulse)` must each be no greater than
`1.500 N*s`.

A finite limit breach is `PROHIBITED_CONTACT`; missing, non-finite, structurally
overlapping, unreferenced, or orientation-ambiguous evidence is
`UNKNOWN_CONTACT`. These are sealed candidate limits, not values derived from the
dry outcome. Every contact occurrence must match exactly one row. Classify all
same-step occurrences before any latch or resume decision. Unknown-contact
precedence is highest, then prohibited contact, intended contact, and background.
A simultaneous bilateral first contact latches both sides at one physics step.

The pinned Isaac 4.1 authority is the synchronous
`get_physx_simulation_interface().get_full_contact_report()` immediate API, not
an asynchronous callback. Before reset pre-roll, apply report-only
`PhysxContactReportAPI` with threshold exactly zero and empty `reportPairs` to
every robot rigid actor and the source rigid actor, then flush and read it back.
Every pair relevant to this contract contains one of those actors. Seal the API
prim set and prove that collision APIs, filters, shapes, contact/rest offsets, and
rigid-body behavior are otherwise byte-identical. Require contact processing to
be enabled. The pinned immediate API has a dynamically sized one-step vector and
no user-sized report buffer; validate that header ranges exactly partition the
returned contact/friction vectors. A pinned-version stress test above the
production scene's combinatorial pair, contact-point, and friction-anchor bounds
must construct a sealed exact number of independent contacts and recover every
expected collider pair/header plus the expected per-pair point/anchor cardinality.
Seal the installed `_physx.pyi` and extension hashes with its current-step-buffer
contract, and fail closed on any native PhysX report allocation, resize, overflow,
or contact-processing diagnostic in strict stderr/log evidence.
FOUND/PERSIST/LOST and threshold-zero tests are also required. If this pinned build
cannot establish the direct vector's no-omission authority, no dry run may start;
range conservation alone is explicitly insufficient.

For each canonical collider pair, reset-epoch lifecycle starts inactive. Group
all immediate-API fragments before applying this transition table:

| Prior | Same-step event group | Occurrence | End state | Result |
| --- | --- | --- | --- | --- |
| inactive | FOUND | yes | active | valid |
| active | PERSIST | yes | active | valid |
| active | LOST | no | inactive | valid |
| inactive | FOUND then LOST | yes, transient | inactive | valid and classified |
| active | PERSIST then LOST | yes, transient | inactive | valid and classified |

Repeated same-type headers with disjoint ranges are valid fragments and are
aggregated once. Every other transition, a range used twice, or an active pair
without fresh PERSIST/LOST evidence is `PROTOCOL_FAILURE`. LOST carries lifecycle
evidence and need not have manifold data. An empty immediate vector is a valid
no-contact sample only when no pair was active. A transient intended occurrence
still triggers the no-lower-Z latch, but cannot count as a current settled or
bilateral step. Existing finger/hand sensors are diagnostic cross-checks: any
contact they report must be present in the immediate report for the same physics
index; disagreement is `PROTOCOL_FAILURE`, while sensor-only absence is not proof
of no contact.

During pre-roll, exact presealed baseline pairs are
`PROVISIONAL_BACKGROUND`; they are ratified as `BACKGROUND` only if the final
baseline current set equals the sealed set. Any other occurrence receives the
normal intended/prohibited/unknown classification immediately. Reset completion
defines the epoch boundary. From that boundary onward, reporting installation,
flush, activation, inventory reconciliation, and pause/play calls must leave the
world counter unchanged unless made through the sole explicit stepper; otherwise
the epoch is `PROTOCOL_FAILURE`. The first monitored pre-roll event may bootstrap
an inactive lifecycle with PERSIST only for a provisional baseline pair, covering
a contact retained internally across reset/report installation. All other
PERSIST-without-FOUND cases remain invalid. Source limits for every negative-index
pre-roll record use the already frozen `reset_origin_pre_roll_pose`.

## Established Evidence

- The sealed legacy Expert attempt stopped when the right finger touched the
  source during diagonal positioning before CLOSE. The contact moved the source
  only `2.8272342302348016e-05 m`; all 3,600 particles remained in the source.
  This demonstrates that contact itself was not catastrophic, but the legacy
  diagonal path remains rejected.
- The cooked open inner finger gap is `0.07741653828466591 m`; the widest sampled
  source shell is `0.07131712 m`, leaving approximately `0.0030497091 m` nominal
  geometric clearance per side.
- Attempt 007 correctly returned NO-GO under the obsolete zero-contact contract
  because effective contact-offset budgets were unresolved. Its calibration
  fixture never became collision enabled and no shadow motion ran. That result is
  retained, not reinterpreted as a controlled-contact trajectory result.
- The step-600 particle layout with robot present is passively stable at 600 Hz.

## Frozen Treatment

Use `expert_control_profile=contact_pick_v1` and the existing controller/RMPFlow
stack. After task reset completes and the world is paused, freeze the finite pose
immediately before the first monitored pre-roll step as
`reset_origin_pre_roll_pose`; all source limits include pre-roll and use that one
origin. After the final pre-roll/baseline step validates the presealed baseline
contacts, freeze its finite post-step pose as
`waypoint_origin_post_baseline_pose` for controller waypoint construction. Seal
both raw matrices, hashes, names, and distinct outward bounds; both must match the
sealed composed reset matrix. Compute these world-space tool-center values exactly
once from the waypoint origin:

- orientation WXYZ `[0.0, 0.0, 1.0, 0.0]`;
- object-frame grasp offset `[0.0, 0.0, 0.0]`;
- approach direction `[0.0, 0.0, -1.0]`;
- pregrasp distance `0.120 m`;
- align/insert start distance `0.060 m`;
- insertion speed `0.006 m/s`, yielding one `0.0002 m` target increment per
  30 Hz control observation;
- configured row-affine `right_gripper -> tool_center` matrix
  `[[-1,0,0,0],[0,-1,0,0],[0,0,1,0],[0,0,-0.0034,1]]`;
- settle and contact-settle durations `0.10 s`;
- close speed `0.003 m/s` and candidate endpoint `0.037 m`, accepted only if the
  dry aperture calibration and dry close support that predeclared endpoint.

The dry run and filled run both enforce these predeclared candidate limits:

- tool-center position error at most `0.0005 m` and orientation error at most
  `0.5 degree` before phase advancement;
- running maximum downward tool-center excursion from the last no-contact
  pre-step pose at most `0.001 m`, including the contact-producing step and every
  later step through the final no-more-physics sample;
- source translation at most `0.001 m` and tilt at most `0.5 degree` before
  CLOSE, leaving headroom below the terminal `0.002 m / 1 degree` limits;
- source linear speed at most `0.002 m/s` and angular speed at most
  `1 degree/s` from monitoring start through terminal; after first contact the
  cumulative source path length is at most `0.005 m` and cumulative absolute
  angular variation is at most `2.5 degrees`;
- PREGRASP timeout `5 s`, ALIGN timeout `15 s`, INSERT timeout `12 s`, SETTLE
  timeout `1 s`, PRECONTACT_SETTLE timeout `0.5 s`,
  CLOSE/contact acquisition timeout `1.5 s`, and CONTACT_SETTLE timeout `0.5 s`.

All distances, angles, speeds, and impulses use finite float64 SI values plus a
versioned outward numeric-error bound before comparison. Equality at a maximum
is allowed only when the outward upper bound remains at or below that maximum.
The dry run must satisfy these limits; its observed maxima cannot redefine them.

The controller phases are PREGRASP, ALIGN, INSERT, SETTLE, CLOSE, and
CONTACT_SETTLE, plus one contact-aware PRECONTACT_SETTLE branch inside the same
`ContactPickController`. `ContactPickController` exclusively owns committed phase
and immutable Cartesian targets. `FluidEvaluationLoop` exclusively owns action
transactions, timeline play/pause, physics stepping, interval/substep indices,
600 Hz qualification counters, terminal stopping, and partial-interval records.
The contact monitor is a read/classify/accumulate component and can only return a
typed step decision. `PourTaskController` only delegates latch calls and passes
the loop's qualification certificates to `ContactPickController`; it does not
implement another phase machine.

The following epoch-local indices are normative. Action-bearing indices start at
zero; no-action fields are JSON null:

- before stepping, derive `B = epoch_start_world_counter + configured_pre_roll_steps`
  as the expected post-step counter of the final no-action baseline. Every step
  record uses `physics_index = post_step_world_counter - B`; earlier pre-roll
  values are negative, baseline is zero, and every later simulated step increments
  the value exactly once. The actual baseline counter must equal precomputed `B`.
  Thus even an early pre-roll terminal has a deterministic signed index. There is
  no separate `pre_roll_index`;
- `control_index` counts controller invocations that propose an action;
- `action_index` counts successfully committed action transactions;
- `apply_index` counts successful articulation API calls and equals
  `action_index` for every physics-bearing transaction; an apply exception leaves
  a committed transaction with no apply index and zero physics;
- `interval_index` identifies the `observe()` interval consuming one applied
  action; `substep_slot` is `1..20` inside a complete interval;
- reset `observation_index=0` has no action; a complete interval emits the next
  observation and camera-frame index, while a terminal partial interval emits
  neither.

Pre-roll/baseline records set control/action/apply/interval/substep/observation/
frame indices to null. After baseline validation, capture one explicit paused
`initial_observation` without physics advancement at `physics_index=0`,
`observation_index=0`, and `frame_index=0`, with all action-bearing indices null.
The first controller invocation consumes exactly this state; the first complete
action interval emits observation/frame 1. A final no-more-physics sample has the
same physics index as its preceding terminal or complete step and is distinguished
by `sample_kind=final_no_more_physics` plus a monotonically increasing sample
ordinal.

Every action follows one total order while physics is paused:
`controller proposal -> pure preapply validation -> loop commit -> articulation
apply -> loop applied receipt -> physics`. Validation failure or apply/receipt
failure is `PROTOCOL_FAILURE` with no physics step. The immutable applied receipt
binds phase, semantic action kind, canonical action SHA-256, target-token SHA-256,
control/action/apply/interval indices, and normal API return without exception.

An arm target token contains the tool-center and mapped RMPFlow-control-frame
position/orientation, both frame names, stage units, and each array encoded as
C-contiguous little-endian float64 with shape, raw-byte hex, and SHA-256. A finger
token equivalently contains both exact joint indices and target bytes. Quaternion
sign is canonicalized before token creation. `ContactPickController` creates the
token for every controller phase from the exact target passed to RMPFlow and
exposes it with the proposal; the loop never reconstructs it from rounded JSON.
The separately named dry-only aperture orchestrator is the sole other token
proposer.

The only legal nonterminal transitions are START -> PREGRASP -> ALIGN -> INSERT,
INSERT -> SETTLE or PRECONTACT_SETTLE, SETTLE -> CLOSE or
PRECONTACT_SETTLE, PRECONTACT_SETTLE -> CLOSE, and CLOSE -> CONTACT_SETTLE.
CONTACT_SETTLE terminates after its exact 60-step window. A physical or protocol
terminal fact may stop any phase; no other transition or re-entry is valid.

1. PREGRASP commands the physical finger upper limits and requires a later
   bilateral measured-open observation before any arm action.
2. ALIGN requires current position and orientation before INSERT.
3. INSERT issues only the frozen world-Z target sequence. X/Y, orientation, and
   the frozen source frame never change.
4. The first intended preclose finger-pad/source occurrence in INSERT or SETTLE,
   including a same-step
   FOUND-then-LOST transient, is sampled immediately
   after one 600 Hz `world.step`. Controlled mode executes every substep as the
   sole stepper sequence `validate -> world.play() -> world.step(render=False) ->
   world.pause() -> seal same-step evidence`; play or pause alone must advance no
   time. Therefore the world is already paused before classification or another
   step is possible. Seal all simultaneous pairs plus pre/post body twists,
   tool/source state, particles, and the applied receipt before deciding.
5. If the dominant same-step result is intended contact, atomically install a
   `precontact_continuation_lease` and call the existing controller latch while
   paused. The lease binds the original INSERT/SETTLE applied receipt and target
   token. The controller independently compares the token's raw bytes with its
   last emitted target before entering PRECONTACT_SETTLE. The contact-producing
   slot retains its original command phase; each unfinished slot has effective
   safety phase PRECONTACT_SETTLE but inherits the same applied receipt under this
   sole whitelist exception. No controller invocation, action commit, apply call,
   observation, render, or camera frame occurs at the latch.
6. If slots remain, resume one explicit step at a time under the still-active,
   unchanged position drive. This is not treated as passive: all contact,
   impulse, coast, source pose/path/velocity, particle, action-authority, and
   timeout limits continue on every slot. Any breach leaves the world paused
   permanently. A successful 20-slot interval emits one normal observation and
   camera frame attributed to the original action, with exact command/effective
   phase segments. Contact at slot 20 follows the same latch but has no remainder.
   It returns a `ControlledObservationTransition` with
   `timeline_state_after=paused`. In controlled mode `main.py` drives its business
   loop from this transition/`fluid_loop.ready_for_action`, not
   `world.is_playing()`: pause is neither stopped nor reset-needed. It processes
   the next controller proposal and transaction while paused, then calls the next
   `observe()`, whose sole stepper performs play-step-pause. Non-controlled modes
   retain their existing timeline condition.
7. The next controller proposal must be `ARM_PRECONTACT_SETTLE` with the identical
   target-token bytes; its joint-action hash may differ because RMPFlow observes a
   new robot state. The last no-contact pre-step pose remains the coast baseline;
   the contact-producing step does not count as settled. Each subsequent current
   intended-contact step counts only if
   target authority, all hard gates, source velocity, measured tool speed, and
   contact relative speed are at their settled `0.002 m/s` limits. A nonterminal
   miss or contact loss resets the counter to zero. The loop certifies readiness
   after 60 consecutive steps; CLOSE can be proposed only at the next 30 Hz
   boundary, so the actual unchanged-target window is 60 to 79 steps. Timeout is
   measured from the first-contact physics index.
8. If INSERT reaches its endpoint without contact, ordinary SETTLE requires an
   exact 60-consecutive-step no-intended-contact window while the unchanged target,
   pose-error, source headroom/velocity, measured tool-speed, particle, authority,
   and all prohibited-contact gates pass. Intended preclose contact switches to
   PRECONTACT_SETTLE and its contact-producing step counts in neither window. Any
   nonterminal miss resets ordinary SETTLE to zero. Its inclusive 600-step timeout
   begins on the first physics step under an applied ARM_SETTLE receipt.
9. CLOSE remains symmetric. CLOSE acquisition requires five consecutive current
   bilateral steps, ending current, with every per-pad and step-global gate valid;
   unilateral, intermittent, or otherwise nonqualifying contact resets the streak.
   Reaching the sealed finger endpoint does not fail or succeed immediately; the
   controller holds that endpoint without overshoot until qualification or the
   inclusive 900-step deadline. At the next 30 Hz boundary it holds the
   measured finger distances and enters CONTACT_SETTLE. CONTACT_SETTLE requires 60
   consecutive current bilateral valid steps within its timeout. At the next
   boundary the controller terminates successfully without proposing another
   action. No early-contact step can count toward either bilateral streak.

Every 600 Hz certificate is current, not permanently latched: a miss after 60
ordinary/PRECONTACT_SETTLE steps, after five CLOSE steps, or after 60
CONTACT_SETTLE steps resets/revokes it before the next control boundary. For each
phase step, first apply total contact/protocol and hard
physical precedence, then update/reset the streak, then accept a certificate, and
only then evaluate timeout. Thus a valid certificate on the exact inclusive final
allowed step succeeds; otherwise that step records `PHYSICAL_TIMEOUT`. Timeout
origins and integer deadlines are serialized, and wall-clock time is diagnostic.

If a current certificate is first obtained on or before its inclusive deadline
inside an unfinished interval, the remaining zero to 19 slots are a bounded
`certificate_to_boundary_grace`, not a deadline extension for reacquisition. They
run only under the unchanged applied receipt and all hard/cumulative gates. The
certificate must remain current on every grace slot. A miss before the original
deadline follows the normal reset rule; a miss after the deadline emits immediate
`PHYSICAL_TIMEOUT`. At the boundary a still-current certificate authorizes the
next transition. The trace marks every grace slot and its originating certificate.

Phase deadlines are inclusive physics-step counts at 600 Hz: PREGRASP 3,000,
ALIGN 9,000, INSERT 7,200, ordinary SETTLE 600, PRECONTACT_SETTLE 300, CLOSE 900,
and CONTACT_SETTLE 300. Each begins on the first physics step governed by the
first applied receipt for that command phase, except PRECONTACT_SETTLE begins on
the contact-producing physics step under its continuation lease. A phase
certificate is evaluated before timeout on the final allowed step.

Measured tool speed is evaluated at the configured tool-center point, never from
the command. For each step take the maximum Euclidean norm of (a) pre-step rigid-
link twist shifted to tool center, (b) post-step shifted twist, and (c) tool-center
finite displacement divided by `1/600 s`; also record the signed projection on the
frozen approach direction. The settled bound applies to that conservative
Euclidean maximum. Source speed uses the source COM for direct and finite-
difference values and is the maximum of pre-step direct, post-step direct, and
COM displacement over the step; angular speed is the analogous maximum of direct
angular rates and shortest quaternion-angle change over the step. Endpoint and
average values need not numerically agree; each must be finite and individually
below the bound, avoiding both undermeasurement and a false equality requirement.

An early contact may disappear during PRECONTACT_SETTLE; it remains recorded and
does not count toward bilateral success. Only current qualified contact after a
CLOSE action can satisfy CONTACT_SETTLE.

After any prohibited contact, motion/tilt/particle violation, authority loss, or
phase timeout, retain the post-step paused state and execute no further physics
step, render, control-policy `step`/`forward`, robot action, or normal camera
capture. Finish sealing all available same-step evidence, then emit exactly one
`ControlledTerminalTransition` variant:

- `no_action_step` covers any physical or protocol terminal after an explicit
  pre-roll/baseline step; all action and interval fields are null;
- `prephysics_transaction` covers every zero-physics setup or action failure before
  an applied receipt, including report installation/readback, reset/inventory
  authority, proposal validation, commit, apply, or receipt failure. It has zero
  executed slots and nullable proposal/control/action/commit/apply/receipt fields;
- `applied_interval` covers a post-step terminal; it contains the original applied
  receipt plus executed and omitted slots.

Every variant includes command/effective phase where applicable, terminal
precedence, and final unchanged world-counter snapshots. `particle_sidecar` is
required in filled mode and null in dry mode, where the record instead binds
explicit particle-deactivation evidence. No variant consumes an observation/frame
index or requires a padding step. `main.py` and the direct child runner handle the
typed return separately from exceptions. Exactly one action-free
`abort_online_fluid_episode` bookkeeping call may set terminal task state; it is
not a controller policy invocation and must return no action. Normal
observation/finalization code is not called. Cleanup must prove the world counter
unchanged. A validated physical timeout is NO-GO/FAIL; missing timeout authority,
autonomous advancement, or pause/cleanup failure is runtime error.

Before every articulation mutation or explicit play/step, validate the current
phase, terminal latch, action kind, payload channels, receipt/lease, and canonical
hash while physics is paused. The versioned phase/action whitelist permits only
open, pregrasp, align, insert, audited precontact-settle, close, and contact-settle
actions in matching phases, plus only the receipt-bound no-mutation continuation
lease above. It additionally permits the pair
`APERTURE_CALIBRATION/CALIBRATION_GRIPPER_TARGET` only in the dry calibration
stage; that pair is forbidden after its fresh reset and in every filled run. Any
lift, production HOLD, pour, attachment, source write, terminal
non-null action, wrong-phase action, or unknown channel latches
`PROTOCOL_FAILURE` before application; articulation state is not mutated and zero
physics steps occur under that action. Parent replay proves all preapply checks
precede corresponding commit, apply, receipt, and physics indices.

## Dry Controlled-Contact Preflight

Add one parent-sealed `geometry_aware_controlled_contact_preflight_v1`. It starts
from the exact candidate USD, Franka, reset pose, stage units, gravity, 600 Hz
physics, 30 Hz control cadence, 20 substeps per action, and production controller
path. It deactivates particle prims before physics play, but does not alter source,
robot, table, target, or environment collision roles or contact/rest offsets. It
authors no fixture, adapter, PVD recording, filtered pair, attachment, source
pose, or kinematic target.

### A. Free-Space Aperture Calibration

`APERTURE_CALIBRATION` is a dry-parent orchestration stage, not a
`ContactPickController` phase and not part of the filled treatment. Its only legal
semantic action is `CALIBRATION_GRIPPER_TARGET`: two finite position targets on
the exact configured finger indices, with no arm/velocity/effort channel. The
calibration orchestrator creates the canonical finger target token; the same loop
validation-commit-apply-receipt and play-step-pause contact interlock apply under
an explicit dry-only whitelist entry. Its legal stage transitions are
`DRY_START -> APERTURE_CALIBRATION -> FRESH_RESET -> CONTROLLER_START`; no
calibration state or action survives the fresh reset, and PREGRASP still performs
independent measured-open confirmation.

At the remote reset pose, traverse the frozen targets from physical open through
`0.037 m`. Record commanded and measured finger positions, physical limits,
cooked inner-pad gap, asymmetry, API and finite-difference pad velocity, settling
time, and saturation at every 600 Hz step. Reject nonmonotonic aperture, missing
bilateral movement, unresolved pad colliders, stale samples, or velocity
disagreement above `0.002 m/s`. No temporary calibration body is used. The same
immediate contact authority and hard-failure pause behavior are active throughout this
phase; any robot/environment contact is a dry physical failure.

### B. Dry Source Close

Reset into a fresh dry episode and execute the complete frozen treatment through
CONTACT_SETTLE or a terminal failure. Keep source collision and dynamics real.
At every 600 Hz substep, before deciding whether another target may be applied,
record:

- all current in-scope PhysX contact pairs, with both actor and collider paths;
- commanded/applied action kind and canonical hash;
- commanded and measured tool/control poses and current controller phase;
- every robot collider transform, source pose, table pose, and joint state;
- source translation/tilt from `reset_origin_pre_roll_pose` and waypoint deltas
  from `waypoint_origin_post_baseline_pose`;
- direct-report call count, returned range conservation, lifecycle state, sensor
  cross-check, pre/post world counters, and pause/play counts.

The immediate report authority must reconcile every live robot/source rigid actor
and every originally enabled collider relevant to an allowed or prohibited pair
before play. In-scope means every pair involving any robot collider or source
collider; unrelated environment/environment contacts are not safety claims. It
supplements the existing three robot sensors; sensor-only absence is not authority.
Each task reset starts a new monotonic reset epoch while paused: install and read
back reporting, reconcile USD and live PhysX inventories, clear lifecycle state,
freeze `reset_origin_pre_roll_pose`, then monitor every explicit no-action pre-roll
step with negative `physics_index` values under the bootstrap rule above. The
final pre-roll step is the baseline and normalizes to `physics_index=0`. Its
end-of-step current set must equal exactly the presealed baseline pair set and it
is included in motion and particle evidence; its post-step pose becomes
`waypoint_origin_post_baseline_pose`. Extra or missing baseline pairs are
`PROTOCOL_FAILURE`. Every later
physics step has exactly one blocking immediate-API read before any next play,
including valid empty reads. A second read, skipped read, malformed range,
cross-epoch state, or sensor disagreement is a runtime error.

Apply the complete contact classification table to every pair. Background
non-robot contacts are recorded and do not count as grasp contact. Prohibited
contacts pause immediately and terminate with a physical fact; unknown contacts
terminate with a protocol fact. Because this dry process is disposable and
contains no particles, bounded source contact is measurement, not contamination
of the filled attempt. Pre-play particle deactivation is the sole dry-only scene
mutation and is explicitly exempt from the collision-role-mutation count.

The dry GO requires:

- exact frozen trajectory and action order;
- measured full-open confirmation before arm motion;
- no lower-Z target after first intended contact;
- measured postcontact downward coast at or below `0.001 m` and, if a preclose
  contact latch occurs, 60 consecutive settled steps before CLOSE;
- source translation and tilt within `2 mm / 1 degree` at every sample;
- source velocity, cumulative postcontact path/angular variation, step and
  episode impulse budgets within their predeclared limits through terminal;
- no prohibited contact or action;
- a complete 600 Hz trace with exact immediate-report range/lifecycle authority;
- current five-consecutive-step bilateral CLOSE qualification and 60-consecutive-
  step CONTACT_SETTLE qualification;
- zero lift, hold, transport, pour, attachment, source write, kinematic target,
  collision filter, or collision-role mutation. The sealed report-only API is not
  a collision-role mutation.

Authored/cooked contact offsets may be recorded as diagnostics, but no PVD
recording or PVD-derived field exists in this contract. GO observes real collision
onset rather than claiming strictly positive no-contact clearance.

### Source And Particle Metrics

At each reset epoch, require finite source pose/twist at the named pre-roll reset
origin and named post-baseline waypoint origin. The composed expected reset matrix
and both observed matrices/bounds are sealed in the run identity. Compute source
translation from `reset_origin_pre_roll_pose` as the Euclidean norm between current
and origin translations. Compute tilt as
`acos(clamp(dot(current_axis, origin_axis), -1, 1))`, where the axis is the
configured vessel axis transformed and normalized in world space. Compute speed
with the conservative COM/direct/finite-difference formula above. Postcontact path
length is the non-cancelling sum of consecutive source-COM translation norms;
angular variation is the sum of shortest quaternion-angle changes. Both
accumulators include the last-no-contact-pre-step to contact-producing-post-step
increment and never reset on contact loss, pause/resume, or phase transition.
Apply outward error to each value and require finite initial, pre-step, post-step,
terminal, and final unchanged-counter samples.

In the filled run, classify all 3,600 stable particle IDs after every 600 Hz
physics step from activation through pre-roll, approach, close, terminal pause,
and final no-more-physics sample. Store stable IDs once and every step's little-
endian float64 positions, source/target frames, and partition codes in atomic
compressed interval sidecars; partial intervals receive a shorter sidecar. Each
position/partition row is in canonical ascending stable-ID order; a changed,
missing, duplicate, or permuted ID is terminal evidence, never silently reordered.
Each sidecar sample has a unique key
`(reset_epoch, sample_kind, physics_index, sample_ordinal)` covering negative
pre-roll, baseline, initial observation, action substep, terminal post-step, and
final unchanged-counter samples. The JSON trace contains the exact sidecar member,
row, shape/dtype, key,
and SHA-256. The parent opens it no-follow under size limits and independently
recomputes geometry partitions and one-to-one trace/sample coverage.
Categories are source, target, transit, tabletop, below-table, non-finite, and
unclassified; their sum must be exactly 3,600. A leave-and-return event therefore
remains a latched physical FAIL. Non-finite IEEE values are preserved in the
binary sidecar and represented in JSON by tagged raw-byte objects, never invalid
JSON numbers. Missing, stale, duplicate-ID, malformed-sidecar, or non-exhaustive
particle evidence is a runtime error.

## Parent And Artifact Contract

The host parent runs under `/usr/bin/python`; the Isaac child uses the pinned
Isaac Python. The parent creates a mode-0700 output directory, owner file, and
stdout/stderr files with exclusive create. It proves the child runtime-report and
trace paths absent; the bound child alone creates them with `O_EXCL`. After child
quiescence, the parent alone creates the final report. Every writer fsyncs its
file and containing directory before close. Seal the config, asset, robot,
controller, loop, contact classifier/monitor, imported implementation closure,
USD composition, runtime data, and interpreter before launch and after exit.

Launch the child with `start_new_session=True`. On Linux the parent acts as a
child subreaper, records PID/PGID/SID and descendant start times, waits for the
leader, terminates the whole group on timeout or interruption, reaps adopted
descendants, and requires no tracked live descendant before reading artifacts.
Every artifact is opened no-follow, required to be a regular single-link file
inside the private root, read once after quiescence, and parsed from that
immutable byte buffer. Any child traceback, segfault marker, unallowlisted error,
nonzero exit, malformed/non-finite JSON, duplicate key, identity drift, or
post-quiescence file mutation is `PROBE_RUNTIME_ERROR`.

The child emits raw lifecycle status and either `MEASUREMENT_COMPLETE` or a typed
physical terminal fact. It does not emit GO. The parent independently validates
binding, recomputes every trajectory/contact/motion/particle conjunct from the
trace and binary sidecars, and
alone emits `GEOMETRY_AWARE_CONTROLLED_CONTACT_PREFLIGHT_GO`,
`GEOMETRY_AWARE_CONTROLLED_CONTACT_PREFLIGHT_NO_GO`, or `PROBE_RUNTIME_ERROR`.
Physical dry failure is NO-GO; missing authority or cleanup is runtime error.

The version-1 child report has exactly these top-level keys and JSON types:
`schema_version:int`, `role:str`, `run_id:str`, `owner_binding:object`,
`identity_sha256:str`, `reset_epochs:array`, `lifecycle:object`,
`terminal_fact:object`, `counters:object`, `trace_artifact:object`, and
`fatal_error:null|object`. `role` is `dry_preflight_child` or
`filled_close_only_child`. `terminal_fact.kind` is exactly one of
`MEASUREMENT_COMPLETE`, `PHYSICAL_CONTACT_FAILURE`, `PHYSICAL_MOTION_FAILURE`,
`PHYSICAL_PARTICLE_FAILURE`, `PHYSICAL_TIMEOUT`, or `PROTOCOL_FAILURE`; it never
contains a parent decision. Each phase record contains entry/exit physics and
control indices, deadline, legal predecessor, and terminal reason. The canonical
state transition table and report schema are implementation constants included
in the treatment hash.

The versioned trace contains one record per executed physics step and a baseline
record iff the final pre-roll step executed. An earlier terminal sets
`baseline_status=not_reached_due_to_terminal`, records expected `B`, its negative
physics index, and the complete terminal prefix; absence of a later baseline is
then valid rather than an incomplete trace. A reached baseline records
`baseline_status=validated|invalid`. Every record contains all normative indices;
command/effective
phase before and after; action proposal, commit, applied receipt, target token or
continuation lease; pre/post actor transforms, COMs, linear/angular twists and
tool pose; raw ordered contact headers, points, normals, impulses, separations,
materials and friction anchors; canonical lifecycle transitions; pair and
step-global classifications and aggregation provenance; all running coast,
source, impulse, settle/bilateral/timeout values; immediate-report structural
checks; sensor cross-check; play/pause/world-counter values; particle-sidecar
member and digest; and terminal/no-more-physics state. Raw non-finite contact
values use tagged IEEE-byte objects so the trace remains strict finite JSON while
preserving the protocol failure. Callback order is absent because callbacks are
not part of this authority.

A normal interval record maps all 20 substep slots to one observation/action and
records command/effective phase segments. A terminal record identifies its
`no_action_step`, `prephysics_transaction`, or `applied_interval` variant; only the
last has executed/omitted slots. All variants emit no observation/camera identity
and bind their terminal trace/sample. A first contact at slot 1, slot 20, and every
intermediate slot therefore has one unambiguous index mapping.

Decision precedence is total: invalid schema, identity, binding, inventory,
contact/particle authority, prohibited applied action, artifact, stderr,
descendant, application-close, or cleanup evidence yields runtime error and
dominates every physical fact. With complete authority, any latched physical
contact, motion, particle, or phase-timeout fact yields dry NO-GO or filled FAIL.
Only complete authority, no physical fact, and every positive conjunct yields GO
or PASS. The parent recomputes this lattice and rejects child disagreement.

## Filled Attempt Handoff

A preflight GO authorizes exactly one filled close-only launch, not general
production use. Before the dry preflight, the reviewed filled launcher,
deterministic filled-config template, contact classifier, state schema, and
parent validator already exist and their hashes are part of the dry run identity.
The dry and filled identity delta is an exact allowlist: particles and their
presentation are active in filled mode, the dry-only aperture phase is skipped,
and the preflight-report/authorization fields are populated. No open-ended
represented difference is accepted.

After GO, the filled parent requires the immutable preflight report, raw trace
artifact manifest, and their SHA-256 values. It creates an authorization record
containing:

- preflight report hash and run identity hash;
- frozen trajectory and controller-treatment hash;
- exact hashes of the filled launcher, filled-config template and instantiated
  config, classifier/inventory, state schema, controller, loop, and error formulas;
- measured open target/tolerance and observed dry maxima, plus the unchanged
  candidate endpoint/speed, pose, contact, physical-coast, source-motion, phase-
  timeout, and precontact-settle limits;
- all source/contact/particle thresholds;
- expected composed source reset matrix plus both named
  `reset_origin_pre_roll_pose` and `waypoint_origin_post_baseline_pose` matrices,
  hashes, and distinct reset-error bounds;
- one parent-generated 256-bit authorization ID and one create-only filled
  attempt directory.

Before launch, the filled parent recomputes the complete bundle and exact delta.
It claims one fixed repository ledger path with `O_CREAT|O_EXCL`, keyed only by
`sha256(GO report bytes || filled bundle hash)`. The single parent-generated ID
and create-only attempt path are contents of that exclusive ledger entry, not
part of its key. It fsyncs the entry and ledger directory before spawn. Two
independently generated IDs, concurrent parents, or copied local authorizations
for the same GO and bundle therefore contend on the same path and only one may
launch. This is a workspace-local one-shot guarantee, not an external trust root.
Timeout, runtime error, FAIL, or PASS never authorizes a retry or parameter
adjustment.

The filled run uses normal `main.py`, task/controller factories, fluid loop,
contact monitors, writer audit, and particle partition authority. No second
physics loop is introduced. Current contact and source pose are checked at every
600 Hz substep; all particle IDs are classified after every step. It repeats the
same reset-epoch lifecycle reset, report-API readback, live collider
reconciliation, blocking immediate reads, range/lifecycle conservation,
sensor-agreement, source-pose, immediate-pause, raw-child-schema, and
phase-timeout contracts as the dry child. Its parent inherits the same subreaper,
process-group termination, descendant quiescence, strict stderr, no-follow
immutable artifact, fsync, application-close, cleanup, parent-only decision, and
error-precedence contract.

The filled episode repeats the exact two-origin baseline procedure: freeze its own
pre-first-pre-roll `reset_origin_pre_roll_pose`, validate every pre-roll source
sample against it, validate the final baseline, and construct waypoints only from
its own post-baseline `waypoint_origin_post_baseline_pose`. Both must match their
sealed expected matrices/bounds; it does not reuse the dry episode's dynamic
poses. Particle activation is expected to change source dynamics, so the dry run
is not claimed to predict them exactly; the same predeclared candidate bounds are
enforced online in filled mode, and any breach stops after the current physics
step.

## Filled Decision Contract

`GEOMETRY_AWARE_CONTROLLED_CONTACT_CLOSE_ONLY_PASS` requires:

- exact handoff, profile, frozen trajectory, and controller evidence;
- full-open confirmation before the first arm action;
- every preclose contact, if any, is an intended finger-pad/source pair in an
  allowed phase;
- the first contact latch suppresses every later lower-Z target and the measured
  coast remains within the predeclared `0.001 m` candidate bound;
- the same synchronous immediate contact authority is complete, current,
  reconciled, range-conserving, lifecycle-valid, and agrees with contacts reported
  by the existing sensors for every filled physics step;
- source translation and tilt remain within `2 mm / 1 degree` for the full run;
- source speed, postcontact path/angular variation, per-step/cumulative impulse,
  and physical coast remain within their sealed limits through terminal;
- pre-CLOSE source pose/velocity headroom gates pass and, if a preclose contact
  latch occurs, intended-contact settle gates pass for 60 consecutive steps;
- terminal phase is CONTACT_SETTLE after an applied CLOSE and current bilateral
  qualification for five consecutive 600 Hz steps followed by 60 consecutive
  current bilateral CONTACT_SETTLE steps;
- exactly 3,600 stable finite particle IDs remain in the source after every
  physics step, with zero target, transit, tabletop, below-table, non-finite, or
  unclassified particles;
- lift, hold, transport, pour, terminal non-null action, source writer,
  kinematic-target, attachment, collision-filter, and collision-role-mutation
  counts are zero.

A bounded allowed early contact followed by valid bilateral close can PASS. With
complete authority, source motion violation, observed particle excursion,
prohibited contact, failure to obtain five consecutive current bilateral
qualifying steps within `1.5 s` after the first applied CLOSE receipt, another
validated phase timeout, or nonqualifying close is
`GEOMETRY_AWARE_CONTROLLED_CONTACT_CLOSE_ONLY_FAIL`. A prohibited commanded or
applied action is a treatment/protocol violation and therefore runtime error, not
physical FAIL. Missing authority, identity drift, wrong treatment, malformed
evidence, action disagreement, or lifecycle failure is `PROBE_RUNTIME_ERROR` and
carries no physical conclusion.

## TDD Implementation Order

1. Add red pure tests for the complete contact matrix: background source/table,
   each allowed phase including CLOSE/CONTACT_SETTLE, exact path allowlists,
   all-header/all-point/all-friction-anchor aggregation, canonical source-oriented
   normal/impulse, pre/post contact-point speed, penetration sign, step and episode
   non-cancelling impulse budgets,
   out-of-limit intended pairs, non-pad source contacts, new background pairs,
   simultaneous bilateral and mixed pairs, prohibited hand/link/environment
   pairs, unknown attributes/paths, canonical order, and precedence.
2. Add red controller tests for later measured-open readiness, frozen top-down
   waypoints, every legal/illegal transition and deadline, exact multi-pair first-
   contact latch, raw-byte target-token match/mismatch, no lower-Z target after
   latch, externally certified PRECONTACT_SETTLE, ordinary SETTLE, CLOSE timeout,
   five-consecutive bilateral acquisition, 60-step CONTACT_SETTLE certificate,
   contact loss/reacquisition reset, and zero postterminal action.
3. Add red loop tests proving each 600 Hz contact sample is read before another
   substep; exact `play-step-pause-read-classify` order; first contact latch and
   exact unchanged-target proof before resume; a receipt-bound continuation lease;
   remaining substeps explicitly reclassified as PRECONTACT_SETTLE without
   another controller invocation, action index, or articulation mutation;
   measured coast includes lag/velocity/overshoot and is bounded by `0.001 m`,
   proposal-validation-commit-apply-receipt ordering; prohibited actions receive
   zero physics steps; slot-1, slot-20, mid-interval 60th-settle-step, target-byte
   mismatch, hard-failure partial intervals, no padding/render/frame, exact index
   counts, all three terminal variants, two consecutive normal paused handoffs in
   `main.py`, explicit initial observation/frame zero, deadline certificate at a
   mid-interval slot, grace-slot certificate loss, and pause/cleanup failure
   dominance.
4. Add red source/particle tests for reset-origin matching, exact translation and
   tilt/path/angular-variation formulas, common COM/tool-center references and
   conservative direct/pre/post/finite-difference speed maxima,
   outward comparisons and equality, velocity/headroom gates,
   every-step 3,600-ID classification, leave-and-return latching, stale/duplicate/
   unclassified/non-finite particles, canonical-ID reorder rejection, exact
   sample-key coverage, sidecar shape/hash/replay, and terminal no-more-physics
   evidence.
5. Add red immediate-report tests for report-API prim coverage and threshold-zero
   readback, disabled contact processing, exact range partitioning, valid empty
   reads, FOUND/PERSIST/LOST and transient transition-table cases, repeated
   disjoint fragments, invalid lifecycle/reused ranges, abnormal baseline,
   provisional-baseline PERSIST bootstrap, zero hidden world-counter movement,
   complete USD-to-live-PhysX reconciliation, and sensor agreement. Add a pinned
   Isaac integration test proving exact header/point/anchor recovery for a
   constructed cardinality above production bounds, threshold-zero/current
   manifold coverage, and that play/pause/render/cleanup advance no physics without
   the sole explicit `world.step`.
6. Add red dry-preflight tests for particle deactivation only, unchanged collision
   roles/offsets, exact child schema, total decision lattice, parent-only decision,
   exclusive creator/writer paths, fsync barriers, process/escaped-descendant and
   application cleanup, strict immutable parsing, stderr, identity drift, and a
   valid pre-baseline terminal prefix with `baseline_status=not_reached_due_to_terminal`.
7. Add red handoff tests for exact report/trace bytes and hashes, prebuilt filled-
   bundle hashes, exact dry/filled delta, source-origin contract, candidate versus
   observed envelopes, fixed-ledger atomic consumption, two independently issued
   IDs plus concurrent/copied replay, stale GO, changed config/code/classifier/
   schema/threshold, and retry rejection.
8. Add red filled-parent tests for inherited process/artifact/contact authority and
   independent recomputation of every PASS conjunct and binary sidecar, bounded allowed precontact,
   prohibited contact, source-limit equality/breach, particle excursion, phase
   timeout, prohibited action, and runtime-error dominance.
9. Run each focused test red before implementation. Then implement the smallest
   changes in the existing controller and loop, run focused suites, `py_compile`,
   `git diff --check`, and the adjacent controller/contact/config/parent suites.
10. Rerun architecture, completeness, and physical-risk reviews. Only unanimous
   approval and green verification permit one fresh dry Attempt 008. Only its
   sealed GO permits the one filled close-only attempt.

## Expected File Scope

- `controllers/atomic_actions/contact_pick_controller.py`
- `controllers/pour_controller.py` only for existing-controller routing/evidence
- `utils/controlled_contact.py` for reusable pure token, lifecycle, aggregation,
  and classification contracts
- `utils/fluid_evaluation_loop.py` and `utils/isaac_fluid_evaluation.py` only for
  the tested action transaction, immediate-report authority, 600 Hz interlock,
  qualification counters, and partial terminal
- `main.py` only for action-transaction wiring and typed partial-terminal handling
- `tools/labutopia_fluid/run_geometry_aware_trajectory_preflight.py`
- `tests/test_geometry_aware_trajectory_preflight.py` and focused adjacent tests
- the dry preflight YAML plus a reviewed deterministic filled-config template and
  filled parent launcher, all sealed before the dry run; only the instantiated
  authorization and filled attempt directory are created after GO
- this plan and immutable run artifacts

No persistent USD, Franka geometry, vessel geometry, fluid material, particle
layout, contact/rest offset, task threshold, or unrelated controller change is
authorized.

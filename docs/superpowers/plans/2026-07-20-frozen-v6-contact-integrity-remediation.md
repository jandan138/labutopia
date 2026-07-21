# Frozen V6 Contact Integrity Remediation Plan

## Trigger

The `_011` HD diagnostic visibly shows the right Franka finger entering or
wedging into the source beaker while the left finger does not establish a
credible opposing contact. The beaker is subsequently lifted and tipped, but
this is not a valid grasp or transfer.

The evidence identifies the first unexpected contact at observed source
transition 229 / physics step 2903, during `PICKING` and before the source
trace's close phase at transition 331 and lift phase at transition 351. The
command integrated in the detecting interval is source transition 228; action
229 is issued only after that observation. The contact receipt names only
`/World/Franka/panda_rightfinger` and `/World/beaker2`. The runner latches the
failure but intentionally continues all frozen actions, so subsequent
close/lift/pour commands can carry an already invalidly wedged vessel.

The source trace is not physically scene-equivalent to the PBD fixture:

- the trace was recorded in `assets/chemistry_lab/lab_001/lab_001.usd` with a
  1/60 s physics step and a random source-beaker position range;
- at source transition 229, the recorded source-body origin is
  `[0.3295563757, 0.1307391822, 0.8223384023]`;
- the counterfactual uses the PBD overlay with a 1/600 s physics step and a
  fixed beaker pose `[0.295, 0.075, 0.8233382266]`, a horizontal difference of
  about 6.6 cm before accounting for the different scene/collision setup;
- the PBD source beaker uses a dynamic rigid body and convex-decomposition
  external collision proxy, while its fluid interior uses 145 invisible box
  panel colliders.

Existing outputs remain immutable rejected diagnostics. This work must never
reclassify them as stable-grasp, transfer, or success evidence.

## Execution And Evidence Isolation

The immutable `_005` source trace, source config, source asset/dependency
closure, and `_011` counterfactual artifacts are read-only inputs. A safe
diagnostic uses a new schema, a new create-only output directory, and
parent-validated source-trace and source-dependency hashes. It must not alter
the existing full-counterfactual schema, its all-858-action requirement, or
its 433-frame validator.

The source trace does not contain a complete initial robot-joint reset receipt.
It is therefore `unavailable` as proof of faithful reset equivalence. A
post-hoc run against current assets may create a new source-state artifact, but
cannot fill or rewrite the historical `_005` record.

## Product Boundary

There are two valid but mutually exclusive products:

1. **Faithful frozen-trace replay.** Run the source scene, source initial robot
   and vessel state, source timing, and source collision configuration. This
   can claim only exact execution of the frozen trace if all state-equivalence
   checks pass.
2. **Physical PBD pour demonstration.** Retarget/replan against the current
   dynamic PBD vessel, exact PBD collision model, and observed state. It must
   use a new action trace and cannot claim frozen-v6 trace replay.

The current mixed mode is a rejected diagnostic only. It must not be polished
or rerun as a positive demo. A PBD retarget must not reuse frozen action hashes,
source transition indices, or frozen-replay wording as action provenance.

## Reset And Route Contracts

Implement and test these contracts before either product route is released:

1. Define a canonical checkpoint: after reset, all fixed pre-roll/warmup and
   contact-report setup, but before the first action. It records seed, reset
   order, units, world step/time, scene/dependency identity, physics scene and
   timing, body/frame conventions, robot DOF names/positions/velocities, source
   root/body/collider roles, source pose/velocity, material/filter identity,
   and collision identity.
2. Define three versioned receipts: `source_reset_receipt_v1`,
   `candidate_reset_receipt_v1`, and `state_comparison_v1`. The comparison
   records every checked field, uses exact comparison for paths/hashes and
   pinned numeric tolerances with quaternion shortest-arc handling, and returns
   `equivalent`, `non_equivalent`, or `unavailable`. Any conclusive mismatch
   wins over unavailable fields; `equivalent` requires all required fields.
3. Faithful source replay requires `equivalent` source-scene receipts. A
   non-equivalent or unavailable comparison issues zero frozen actions and may
   emit only a rejected compatibility diagnostic. A PBD retarget requires an
   independently valid PBD reset receipt; its source comparison is retained as
   non-equivalent or unavailable context, never as a replay claim.
4. Define a PBD vessel-proxy receipt separately from source equivalence. It
   records composed-layer hashes, external-shell collider paths/owners/
   transforms/approximation/material, all 145 interior-wrapper collider paths
   and transforms, offsets, enabled states, and effective collision-group/filter
   relationships. An unavailable cooked-convex detail is explicit, not assumed.

## Safe Prefix Diagnostic

Implement a new `frozen_v6_preclose_abort_diagnostic_v1` artifact contract;
do not retrofit an early stop into the existing full replay.

1. Enable a frozen-run-only synchronous PhysX manifold reporter independently
   of the controlled-action interlock. Sample once per physics substep and fail
   closed on a report gap, malformed ownership, or lifecycle discontinuity.
   Keep contact-sensor evidence only as a cross-check.
2. Serialize a canonical full first-tick contact receipt, not `contacts[0]`.
   It includes observed and integrated source transitions/action hashes, next
   unissued transition, absolute physics step, substep slot, phase, all sorted
   manifold fragments, raw-report provenance, body and collider paths/prototype
   identities, points, separation, raw/oriented normals and impulses, source
   pose/velocity, and both finger poses/velocities.
3. Use an absorbing substep state machine:
   - `APPROACH`: any new robot-to-source-external-shell contact fails closed;
   - `CLOSE_ACQUIRING`: only expected left/right external-shell contacts may
     accumulate a bilateral certificate; hand, wrapper, unknown, malformed,
     or sustained one-sided contact fails;
   - `CERTIFIED`: only a valid sustained bilateral certificate permits lift;
   - a lift command without a certificate fails closed.
   Expected reset support, particles, and non-robot contacts are recorded but
   do not qualify as grasp contacts.
4. At the detecting substep, issue no remaining substeps, no next source
   action, no pour marker, and no later render/observation. Seal one rejected
   prefix artifact with the applied action-hash prefix, expected/omitted action
   ranges, prefix-scoped velocity-mode receipt, terminal contact receipt, and
   `measurement_coverage=through_first_invalid_contact_only`.
5. The prefix artifact has `full_source_replay=false`, all collection and
   acceptance flags false, no HD/pour release-media object, and a distinct
   parent validator. The legacy full-counterfactual validator must reject it.

## Test-Driven Delivery

1. Add Isaac-free tests for source/live receipt schema, malformed fields,
   unavailable evidence, reset-boundary drift, scene/timestep mismatch,
   source-pose mismatch, robot-state mismatch, root/body/collider role
   confusion, collision identity mismatch, quaternion tolerance edges, and the
   complete route decision matrix.
2. Add state-machine tests for baseline support, pre-close right-only contact,
   hand contact, wrapper contact, unknown ownership, simultaneous and transient
   contacts, a contact on a close boundary, malformed full-report evidence, and
   reporting gaps. Assert deterministic canonical first-tick serialization.
3. Prove a contact in a middle substep prevents remaining substeps, the next
   action, later source phases, and any post-terminal frame. Assert correct
   attribution of integrated transition 228 versus observed transition 229.
4. Add prefix-artifact validation tests: exact hash prefix, omitted ranges,
   early termination before the velocity-mode transition, stale/malformed
   receipts, cleanup behavior, rejection flags, and incompatibility with the
   legacy full-replay validator.
5. Add USD-stage tests for the full PBD proxy receipt: dynamic source body,
   convex-decomposition outer mesh, each wrapper collider identity, contact and
   rest offsets, material, and collision-group relationships.
6. Run focused tests, `py_compile`, and `git diff --check`. Run a create-only
   PBD safe-prefix diagnostic; its expected result is a short rejected
   pre-close-contact artifact, not a pour video.

## Product Route After The Safety Gate

### Faithful Frozen Replay

Use only the original source scene and a new complete, immutable source-reset
receipt. If reset comparison is unavailable or non-equivalent, issue zero
frozen actions. If a complete compatible run cannot reproduce bilateral contact,
retain a rejected result and investigate the source environment; do not
transplant the trace into PBD and call it physically equivalent.

### PBD Demonstration

Build a new closed-loop route: derive cup-frame targets from the live PBD
vessel, plan an approach with clearance, command a measured bilateral close,
validate sustained two-finger contact/impulse, then lift and pour. Save this as
a separate PBD action trace and report it as a new experiment, not a replay of
the frozen-v6 trace.

## Stop Conditions

- No output may present a one-sided, penetrative, wedged, or unverified grasp
  as successful transport.
- No remaining substep or action after the first invalid contact may be issued
  in the safe diagnostic path.
- No use of source-trace wording is allowed when initial scene, state, timing,
  or collision identity is non-equivalent.
- Do not replace the vessel pose, add a mechanical attachment, or modify source
  actions to make the current video appear correct.

## Plan Review

Architecture, completeness, and runtime-evidence reviews converged on the same
corrections: early stopping needs a new prefix-replay schema; the historical
source record is insufficient for faithful reset equivalence; passive contact
needs an explicit full-manifold authority; and source replay must be isolated
from PBD retargeting. The revised plan adopts those requirements and leaves the
legacy rejected evidence unchanged.

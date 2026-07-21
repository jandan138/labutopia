# Level1 Pour Robot-Present Zero-Action Plan

**Goal:** Observe whether the hash-pinned step-600 candidate meets the registered
source-motion and containment gates for four simulated seconds after the final
normal task reset, with the production Franka, PickPourTask, camera bootstrap,
contact-grasp material binding, and authored robot drives present, while no
controller is constructed and no robot command API is called after authority
origin.

## Product Boundary

- Use the passing candidate asset and 600 Hz timing unchanged.
- Construct the production Franka and task through existing factories and apply
  the normal reset path. Production Franka/task cameras and render products are
  unavoidable and must be disclosed; create no additional diagnostic cameras,
  capture no images, and issue no explicit render after authority origin.
- Define zero action as zero post-origin controller construction, `task.step`,
  articulation `apply_action`, direct joint/effort/target write, gripper command,
  source pose/kinematic write, particle mutation, or reset. Production-authored
  Franka drives remain active and are not zeroed.
- Keep production `configure_contact_grasp_scene()` material binding. Do not
  change collision filters or attach the source.
- Record reset-origin source motion so task reset cannot hide relocation.
- This diagnostic cannot authorize grasp by itself.

## TDD And Implementation

1. Add failing pure tests for the zero-command ledger, exact two-reset bootstrap,
   robot/task live-state contract, 2,401-record schedule, full containment,
   source motion, and final lifecycle publication.
2. Add a thin dedicated parent/child runner. Reuse passive trace/publication
   helpers while keeping a robot-present manifest; do not change `main.py` or
   construct `FluidEvaluationLoop`.
3. Execute the exact prefix in this order: configure particle readback before
   World construction; reference the pinned candidate; capture authored source
   matrix/center; construct World; create Franka with explicit configured
   position/USD/frequency; reassert and verify effective particle readback after
   World construction; apply `configure_contact_grasp_scene()`; initialize
   ObjectUtils; create `pickpour`; call `task.reset()` once explicitly. Task
   camera setup performs the first reset and explicit task reset performs the
   second. Do not prepend another reset.
4. Reassert 600 Hz timing, validate the full robot-present fluid stage contract,
   initialize source readback, and establish authority origin. Record net
   authored-to-each-reset/checkpoint source motion; this does not claim absence
   of unsampled internal reset transients.
5. Run exactly 600 no-action pre-roll and 1,800 no-action hold physics steps at
   600 Hz. Capture all source poses and all 3,600 particle positions after every
   step, with the same motion and containment gates. Record whether the
   post-reset baseline particle hash matches the pre-World authored layout, and
   require live particle hashes to change during integration.
6. Derive robot/task presence from initialized live state: valid Franka
   articulation, nine finite DOFs, expected finger colliders/material binding,
   `task.robot is robot`, source path `/World/beaker2`, and task frame index 4.
   Instrument post-origin command/reset methods rather than hard-code counters.
7. Run focused tests, compilation, and `git diff --check`, then one fresh bounded
   Isaac child. The parent must independently recompute motion and source-cup
   containment from the raw arrays, validate the pinned scene closure and robot
   hash, and terminate the child process group on timeout or interruption.

## Decision

- Invalid lifecycle, reset-origin, timing, artifact, or trace authority yields
  no physics conclusion.
- If source motion or containment fails, keep product NO-GO and isolate the
  combined robot/task prefix difference. Do not attribute failure to the robot,
  reset, cameras, material, or collision topology without another discriminator.
- If it passes, preserve one robot-present zero-action result and write a
  separately reviewed contact-close-only plan. Do not proceed directly to lift
  or pour.
- No repeatability, mass, force, grasp-capacity, reliability, production, or
  product claim is authorized.

## Expected Files

- one dedicated robot-present zero-action runner
- focused zero-action tests
- immutable evidence under a new output directory

## Result

The authoritative run is
`outputs/robot_present_zero_action_20260716/attempt_004/report.json` and reports
`ROBOT_PRESENT_ZERO_ACTION_PASS` with a clean child exit and parent artifact
validation.

- Final report SHA-256:
  `623a37ffa01aa12ba0d5c05a1227b1282bb76a7bb0136715db60c5f3a69fbfe4`.
- Source trace SHA-256:
  `67a8c6c341ee2ff14ced4c2180b7c90a725fbb59ede4c0b42ed6891fd32dae19`.
- Particle trace SHA-256:
  `e76d59d102cf7622033dc57d07e57ac184d54e9bb1c9e3bfbb64b8a79facf2c9`.

- Exactly two bootstrap resets were observed and no reset occurred after
  authority origin.
- Exactly 2,400 `render=False` physics steps produced 2,401 source records and
  a `(2401, 3600, 3)` particle trace. All 2,401 particle-position hashes are
  distinct and all source/particle/frame hashes validate.
- Parent-recomputed maximum source translation is `1.5699819825788087e-05 m`
  and maximum tilt is `0.00017287598734470351 deg`. No motion gate failed.
- All 3,600 particles remain in the source cup in every record; every non-source
  partition maximum is zero and there is no first containment failure.
- Post-origin task, controller, robot, gripper, source-writer, render, camera,
  reset, and probe-issued particle-mutation counts are zero. Authored Franka
  drives remain present and unchanged.
- The post-reset baseline particle hash differs from the pre-World authored
  hash. This is disclosed as part of the normal two-reset treatment rather than
  hidden; current-state readback is effective and changes on every physics step.
- Attempts 001 and 002 are invalid bootstrap runs stopped by an over-strict
  baseline byte-equality gate. Attempt 003 completed with a child-side physics
  PASS but failed parent publication because of a validator scoping bug. Its raw
  traces subsequently pass offline validation, but its immutable final report
  remains a runtime error. Attempt 004 is the only promoted result.
- Isaac logs warn that the Franka hand contact sensor parent was missing a
  ContactReportAPI and was updated at runtime. Contact sensors were not read in
  this probe, so this does not affect the zero-action result; contact-sensor
  authority must be established before any contact-close claim.

This PASS authorizes a separately reviewed contact-close-only plan. It does not
authorize approach geometry, closing, grasp, lift, transport, or pour by itself.

# Accepted Final Isosurface Single-Init-Step Plan

## Goal

Use the accepted frame-600 positions as immutable parent input, then render a
derived presentation state produced by exactly one fixed `1/600 s` PhysX
initialization step with explicitly verified zero initial velocities. This is
not a continuation of the accepted trajectory, is neither accepted frame 600
nor authoritative frame 601, and creates no containment or long-hold physics
authority.

The zero-step probe is terminally invalid: its predeclared discarded capture
and its one strict final capture both returned a near-constant white `context`
frame. The runtime USD bridge existed but remained a placeholder, so this plan
does not retry zero-step warmup or add render variants.

## Scope

Modify only:

- `tools/labutopia_fluid/run_real_beaker_accepted_final_isosurface_probe.py`
- `tests/test_real_beaker_accepted_final_isosurface_probe.py`

Add the new output directory:

- `docs/labutopia_lab_poc/evidence_manifests/real_beaker_accepted_final_isosurface_single_init_step_probe_20260713`

Keep the pinned authority bundle, frame-600 positions, physical offsets,
isosurface parameters, ClearWater MDL, cameras, resolution, renderer, and source
USD unchanged. Do not add a parameter matrix, alternative material, extra
warmup count, or capture retry.

Treat the existing probe as an atomic contract migration. Replace every active
zero-step identifier: docstring, output root, probe ID, statuses, technical
gates, fixed-contract fields, checkpoint validator, lifecycle/manifest keys,
PNG stems, executed-step fields, and claim boundary. Retain zero-step wording
only as predecessor provenance. Do not duplicate the capture pipeline.

## Fixed Runtime Contract

1. Validate the same accepted authority, trace, frame-600 position hash, source
   USD hash, and ClearWater MDL hash before Isaac starts.
2. Author the same 4096 ordered positions into the disposable wrapper and
   require exact pre-attach readback equality. Require exactly 4096 authored
   finite zero velocities before attach.
3. Attach `StrictPhysicsStepper` with `logical_dt=integration_dt=1/600` and
   `substeps_per_logical_step=1`.
4. Invoke `stepper.step(after_integration_step=...)` exactly once. No code
   outside `StrictPhysicsStepper` may call `simulate` or `fetch_results`.
   Capture the sole post-step readback in that callback. The PhysX step-event
   counter must change from 0 to exactly 1. After detach,
   `summary(requested_steps=1)` must report one logical step, one integration
   step, one ordered simulate/fetch pair, `simulated_seconds=1/600`, and exact
   count plus ordered-lifecycle verification.
5. Read the post-step runtime particle points once. Require 4096 finite points
   and classify every point inside the source beaker with zero strict
   violations. Reuse the same `derive_cup_interior_frame` construction and
   `classify_visible_beaker_positions` implementation as the accepted
   authority; do not introduce probe-local bounds. Record the ordered hash,
   AABB, finite count, violation count, and any violating indices. Because
   PhysX smoothing may affect this USD readback, label it only as derived
   presentation-state point-center containment.
6. Perform no further simulation. During all render warmups, the one discarded
   capture, the strict final capture, cleanup, and detach, the step-event count
   must remain exactly 1 and the timeline must remain stopped.
7. Preserve the existing single-use discarded-frame rule: only the predeclared
   discarded batch, only its `context` frame, and only the exact
   `static_replicator_capture_near_black_or_flat` quality error may be recorded
   and discarded once. The final three-camera capture remains strict and is
   never retried or caught.
8. Require the runtime isosurface bridge and pinned ClearWater binding, three
   decodable non-flat 960x540 PNGs whose raw annotator dtype is `uint8`. If the
   USD bridge is populated rather than a placeholder, require all exposed mesh
   points finite. Require scoped MDL plus PhysX/isosurface/CUDA/Hydra fatal and
   non-finite log acceptance, unchanged source and wrapper files, and unchanged
   non-runtime scene-point hashes. Exclude only the named runtime particle-set
   and isosurface subtrees from that scene hash.
9. Persist every checkpoint with cumulative event count and timeline state, the
   strict stepper lifecycle summary, and the fixed camera/capture attempt count.
   Store separate manifest sections named `accepted_authority_input` and
   `derived_presentation_state`. Use the claim boundary
   `accepted_frame_600_positions_are_parent_authority;single_zero_velocity_init_step_state_is_presentation_only;not_frame_601;no_new_physics_authority`.

## TDD Order

1. Change the fixed contract test to require one initialization step and
   `initialization_dt=1/600`.
2. Add failing tests for an exact single-step checkpoint sequence: 0 before and
   after attach, then 1 after initialization and at every later checkpoint.
   Cover missing/extra steps and lifecycle order failure.
3. Add failing tests for post-step presentation readback: exact count, all
   finite, all inside, and rejection of any violating or non-finite point.
4. Add failing tests for zero authored velocities, populated bridge finiteness,
   raw `uint8` final captures, exact one-time `context` discard semantics, and a
   status/identity that distinguishes the new probe from terminal zero-step.
5. Implement the smallest runtime change, run focused and related tests, then
   execute one formal Isaac integration run.

## Terminal Outcomes

- `CAPTURED_SINGLE_INIT_STEP_PENDING_VISUAL_REVIEW`: exactly one integration
  step executed, all derived presentation-state point centers remain inside,
  and all three strict captures pass.
- `INVALID_SINGLE_INIT_STEP_ISOSURFACE_PROBE`: any input, step-count,
  containment, bridge, material, capture, log, or source-integrity gate fails.

If technically valid, submit only the three final PNGs to a fresh visual
reviewer. The review requires a continuous contained water-like surface that is
readable in close-up and table context. No tuning or recapture occurs before the
verdict.

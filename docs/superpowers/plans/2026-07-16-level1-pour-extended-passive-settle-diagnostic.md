# Level1 Pour Extended Passive Settle Diagnostic Plan

**Goal:** Determine whether, in one fresh run, the rest-offset-zero filled vessel
remains within the unchanged `2 mm / 1 deg` limits during the fixed 360-step
interval immediately following a precommitted 1,200-step passive wait. This is
fixed-window characterization, not evidence of convergence, settling time, or
repeatability.

## Why This Is Next

- Rest offset zero removes dry seating and keeps all particles contained.
- Filled motion still oscillates: each one-second window moves roughly
  `1.3-2.0 mm`, while instantaneous terminal speed can happen to be near zero.
- A longer passive observation distinguishes slow settling from persistent
  oscillation before considering any damping, mass, friction, or solver change.

## Boundary

- Change only `dynamic_pre_roll_steps` from `120` to `1200` in a diagnostic copy
  of the rest-offset-zero config. Keep `physics_dt=1/120`, so pre-roll is exactly
  10 seconds; retain the existing 360-step hold.
- Keep the rest-offset-zero asset, particle state, physics, thresholds, runner,
  and no-robot/no-action contract unchanged.
- This is characterization, not a production latency decision or grasp gate.
- Step 1200 is the precommitted and only hold reference. Do not shift or extend
  the window after inspecting the trace.

## TDD And Runtime

1. Add a config-diff test proving only name, performance label, and pre-roll step
   count differ from the reviewed rest-offset-zero config, then add that config.
2. Add focused pure tests and an offline audit mode that leave measurement
   behavior unchanged. The audit must distinguish pre-roll failure/hold pass
   from hold failure and preserve transient full-trace containment failure.
3. Run existing probe tests and `git diff --check`.
4. Run one fresh filled treatment, producing exactly 1,561 records and all
   `1,561 x 3,600` particle positions.
5. After final lifecycle and artifact validation, publish a separate immutable
   audit bound to the final report and both NPZ hashes. Recompute exactly steps
   `1201..1560` relative to step 1200 with the shared motion metric and unchanged
   tolerances. Preserve the runner's all-record decision unchanged.
6. Keep containment full-trace: every record `0..1560` must contain exactly
   3,600 finite positions with `source=3600` and all non-source partitions zero.
7. Report step-0-to-1200 displacement and the 13 fixed one-second windows
   `[0,120]`, `[120,240]`, ..., `[1440,1560]`. For each, report endpoint
   displacement and mean horizontal speed descriptively; they are not gates.

## Decision

- If full-trace containment fails or any hold step exceeds its step-1200-relative
  limit, conclude that the fixed 10-second wait did not yield one bounded and
  contained 3-second hold. Stop the waiting branch and do not search another
  duration or window.
- If both pass, conclude only that this fixed 10-to-13-second window was bounded
  and contained in this run. State any earlier accumulated drift explicitly and
  write a separate plan to assess latency and relocation. Do not call it
  settling, replace production, or launch grasp.

## Expected Files

- one diagnostic config under `config/`
- one focused config test
- one immutable hash-bound offline hold audit
- immutable filled evidence under
  `outputs/contact_grasp_passive_stability_20260716/`

## Runtime Outcome

- The run completed all 1,561 records and archived all 5,619,600 particle
  positions. Final report and both NPZ hashes validate.
- Full-trace containment failed transiently at local step 17 with one tabletop
  particle; it later recovered, but the failure remains latched.
- Pre-roll ended `2.26851469 mm` from step 0 and reached a maximum
  `5.49724091 mm` displacement, so ten seconds did not converge to a fixed
  source location.
- The precommitted hold-only audit also failed. Relative to step 1200,
  translation first exceeded `2 mm` at local step 1301 and reached
  `5.38546815 mm`; maximum tilt remained only `0.00076654 deg`.
- Motion remained oscillatory. The fixed `1200..1320` window moved
  `2.19175311 mm` with mean horizontal speed `12.04298 mm/s`; the final two
  windows moved `1.60390201 mm` and `1.63960569 mm`, with mean speeds
  `7.24760 mm/s` and `8.05127 mm/s`.
- Classification is `HOLD_ONLY_FAIL`. The waiting branch is closed without
  trying another duration or moving the reference window. No convergence,
  repeatability, latency, product, mass, contact-force, or grasp claim is
  authorized.

Evidence:

- `outputs/contact_grasp_passive_stability_20260716/rest_offset_zero_extended_settle_filled_attempt_001/report.json`
- `outputs/contact_grasp_passive_stability_20260716/rest_offset_zero_extended_settle_filled_attempt_001/settle_audit.json`

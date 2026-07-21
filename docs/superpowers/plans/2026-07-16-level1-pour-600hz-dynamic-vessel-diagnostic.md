# Level1 Pour 600 Hz Dynamic-Vessel Diagnostic Plan

**Goal:** Determine whether the 600 Hz timing variant of the rest-offset-zero
configuration, with the 30 Hz outer cadence and one-second pre-roll plus
three-second hold preserved, meets the existing all-integration-step passive
motion and containment gates in one fresh no-robot, 3,600-particle run. This is
candidate qualification, not a paired causal or repeatability estimate.

## Why This Is Next

- Rest offset zero removes dry seating but filled motion remains oscillatory and
  does not become bounded after a fixed 10-second wait.
- The current InternData recipe integrates at 120 Hz. Separate Isaac Sim 4.1
  qualification passed six 10-second static-source cells at 600 Hz, but sampled
  only 21 frames per cell and used different particle counts, contact scales,
  particle-system rest offsets, and a static source. It motivates this fixed
  rate test but does not predict its result. Here, rest-offset-zero refers only
  to the dynamic source shell property.
- Integration frequency is tested before changing particle contact scale,
  damping, friction, vessel mass, or thresholds.

## Single-Treatment-Factor Contract

The sole physical treatment factor is integration frequency. Start from
`config/diagnostic_level1_pour_source_rest_offset_zero_v1.yaml` and change only
the coupled timing fields required to preserve physical duration:

- `physics_dt`: `1/120` to `1/600`;
- `physics_substeps_per_observation`: `4` to `20`, preserving 30 Hz observations;
- `dynamic_pre_roll_steps`: `120` to `600`, preserving one second;
- `filled_static_hold_steps`: `360` to `1800`, preserving three seconds;
- diagnostic name and performance label.

Keep rendering dt, asset, source and particle authoring, positions, velocities,
solver values, collision offsets, density, mass, friction, gravity, thresholds,
runner, robot, and controller unchanged.

## TDD And Runtime

1. Add a failing config-diff test allowing exactly `name`, `performance_label`,
   and the four timing fields above. Assert `physics_dt == 1/600`,
   `physics_dt * physics_substeps_per_observation == rendering_dt == 1/30`,
   `physics_dt * dynamic_pre_roll_steps == 1`, and
   `physics_dt * filled_static_hold_steps == 3`.
2. Add the diagnostic config outside the production-config filename inventory.
3. Run focused tests, Python compilation, and `git diff --check`; do not change
   measurement code.
4. Run one fresh no-robot filled treatment. It must produce exactly 2,401
   records and all `2,401 x 3,600` particle positions.
5. Require hold reference step 600, terminal step 2400, world-step delta 2400,
   approximately four recorded seconds, and
   `positions_world_m.shape == (2401, 3600, 3)` with finite float64 values and
   valid stored hashes.
6. Use the unchanged completed `report.json` all-record decision as authority.
   Steps `0..600` reference step 0; steps `601..2400` reference step 600.
   Translation uses `2 mm + 1e-12 m`, tilt uses `1 deg + 1e-9 deg`, and every
   sample must have `source=3600` with all non-source partitions zero.
7. Report first failures in local steps and simulated seconds. Descriptively
   report the fixed windows `[0,600]`, `[600,1200]`, `[1200,1800]`, and
   `[1800,2400]`, using source-center endpoint displacement and mean horizontal
   rigid-body speed.

## Decision

- If lifecycle, timing, trace shape, or artifact validation fails, classify the
  attempt as invalid and draw no physics conclusion.
- If a valid run fails motion or containment, conclude only that this exact
  600 Hz configuration did not meet the gate in this run and close further
  frequency-only experimentation. Do not try another rate or combine it with a
  contact-scale change in this experiment.
- If both pass, preserve the bounded 4-second evidence and write a separate
  robot-present zero-action plan. That plan must preserve contact/grace durations
  in seconds and measure wall-clock cost separately; only the fivefold
  integration-step count is known here. Do not replace production or launch
  grasp from this diagnostic.
- No effective payload mass, contact-force, causality, convergence,
  repeatability, or product claim is authorized in either branch.

## Expected Files

- `config/diagnostic_level1_pour_source_rest_offset_zero_600hz_v1.yaml`
- focused config test coverage
- immutable filled evidence under
  `outputs/contact_grasp_passive_stability_20260716/`

## Runtime Outcome

- The run completed with 2,401 records, exact world-step delta 2,400, recorded
  time delta `4.00000010 s`, and finite float64 particle positions shaped
  `(2401, 3600, 3)`. All artifact and per-record position hashes validate.
- All 3,600 particles remained in the source at every sample. Maximum tilt was
  `0.13779917 deg`.
- The authoritative all-record motion gate failed at local step 8
  (`0.013333 s`) and reached `2.45794253 mm`. The source completed an initial
  center adjustment of approximately `[-0.69746, -2.35685, 0.00006] mm` by the
  end of the one-second pre-roll.
- The fixed hold-only audit is descriptive, not authoritative: steps 601..2400
  remained within `0.00007593 mm` translation and `0.00012221 deg` tilt, with
  complete containment. This cannot overwrite the preregistered all-record
  `PASSIVE_STABILITY_FAIL` decision.
- The exact 600 Hz configuration therefore failed its named gate and the
  frequency-only branch is closed. The result narrows the next candidate to
  initial particle-state equilibration rather than persistent source drift; it
  does not authorize another frequency, production replacement, robot-present
  execution, or grasp.

Evidence:

- `outputs/contact_grasp_passive_stability_20260716/rest_offset_zero_600hz_filled_attempt_001/report.json`
- `outputs/contact_grasp_passive_stability_20260716/rest_offset_zero_600hz_filled_attempt_001/descriptive_hold_audit.json`

# Level1 Pour Particle Density Authority Diagnostic Plan

**Goal:** Test whether making the particle-set density authority explicit at
`1000 kg/m3` changes the bounded 3,600-particle, 120 Hz dynamic-vessel passive
outcome. This is an explicit-default authoring diagnostic, not a known physics
correction, and it does not establish effective payload mass, contact force, or
causality.

## Why This Is Next

- Dry settles by about `1 mm` and then remains stationary.
- Filled continues sliding at about `12.3 mm/s` near the end of the same hold.
- The production particle set currently authors both `physics:mass = 0` and
  `physics:density = 0`. Isaac treats zero values as non-overrides and selects a
  simulation default documented as `1000 kg/m3`.
- Making particle-set density explicit is therefore likely nominally equivalent
  to the current default path. A changed outcome would be an authoring-associated
  observation, not proof that effective mass was corrected.
- The repository's explicit-SI matrix qualified separate 1,024/4,096-particle,
  600 Hz static-hold recipes. It does not qualify this 3,600-particle, 120 Hz
  dynamic-vessel recipe. The exact 3,600-particle recipe previously passed only
  with a kinematic source.

## Product Boundary

- Create a diagnostic overlay and config. Do not replace the current production
  asset from this plan.
- Change only particle-set `physics:density` from `0` to `1000`. Keep the
  inherited particle-set total mass at `0` and leave PBD-material density
  unauthored.
- Do not change source pose, source mass/COM/inertia, support geometry,
  collision groups, wrapper, particle positions or velocities, solver values,
  timestep, friction, thresholds, controller code, or robot code.
- Do not infer effective filled mass or support force from authored density.
- Run no robot and no action. Do not launch a grasp from this plan.

## TDD And Implementation

1. Add failing tests that the candidate overlay has the current contact asset as
   its sole sublayer and authors exactly one physical property opinion:
   `/World/InternDataParityFluid/Particles.physics:density = 1000`. On the
   composed stage, particle-set total mass remains the inherited `0` and
   PBD-material density remains unauthored.
2. Add the density-only overlay and a diagnostic config outside the
   `level1_pour_online_fluid*.yaml` production-config inventory. The normalized
   config may differ from the native Expert config only in `name`, `usd_path`,
   and `online_fluid.performance_label`.
3. Keep the passive runner and shared runtime code unchanged. Run focused tests
   and `git diff --check`.
4. Run one fresh filled passive probe with the candidate config. Reuse the exact
   481-record schedule and existing `2 mm / 1 deg` and zero-spill gates.
5. Record the historical filled baseline report hash and the exact one-property
   authored difference. Compare values descriptively only; do not use the
   dry/filled comparator because config and dependency hashes intentionally
   differ. Terminal and last-60-sample velocity remain descriptive, not gates.

## Decision

- If candidate filled motion and containment both pass, the result supports only
  that this candidate met one bounded passive probe. Preserve the evidence and
  write a separately reviewed robot-present zero-action plan before any grasp.
- If either fails, keep the current product NO-GO and stop this density branch.
  Do not tune density, friction, vessel mass, timestep, or thresholds in the
  same experiment.
- In both branches, `causal_claim_allowed=false`, filled payload mass and
  particle-to-support contact authority remain unresolved, production
  replacement is not authorized, and `next_grasp_authorized=false`.

## Expected Files

- one density-only overlay under `assets/chemistry_lab/lab_001_fluid_eval/`
- one diagnostic config under `config/`
- focused overlay/config tests
- immutable candidate evidence under
  `outputs/contact_grasp_passive_stability_20260716/`

## Runtime Outcome

- The candidate overlay authored exactly one additional physics opinion:
  particle-set `physics:density = 1000`. The passive runner and shared runtime
  code remained unchanged; focused overlay/config/probe tests passed.
- `density_explicit_filled_attempt_001` completed all 481 records and retained
  all 3,600 particles in the source at every sample, but motion failed. Pre-roll
  displacement was `1.75520007 mm`; hold-reference displacement reached
  `6.07621520 mm`; the phase-relative maximum was `6.54172003 mm` and first
  exceeded the limit at local step 166.
- The terminal horizontal speed was `27.61180 mm/s` and the last-60-sample mean
  was `10.35670 mm/s`, so the source was not settling.
- The candidate changed the particle trajectory and removed the baseline's
  single transient tabletop classification, but did not satisfy passive motion.
  The explicit-density branch is closed without tuning another density value.
- This result does not establish density, mass, force, or contact causality and
  does not authorize production replacement, robot-present execution, or grasp.

Evidence:

- `outputs/contact_grasp_passive_stability_20260716/density_explicit_filled_attempt_001/report.json`

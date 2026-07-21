# Level1 Pour Step-600 Particle-Position Layout Diagnostic Plan

**Goal:** Test the hash-bound local-step-600 particle-position layout from the
600 Hz run, expressed back in the original source frame while retaining baseline
zero velocities, under the unchanged authored-reset lifecycle and passive gates.
This is a position-only candidate, not a settled-state or equilibrium replay.

## Why This Is Next

- At 600 Hz the source exceeds `2 mm` within `0.0133 s`, then remains effectively
  fixed for the following three seconds with all particles contained.
- From step 0 to 600 the particle cloud rearranges substantially relative to the
  source while the source moves to a new horizontal equilibrium.
- The product already uses authored-world-reset particle positions. Rebasing a
  measured contained layout is an initialization treatment, not runtime pose
  following, kinematic control, or attachment.
- Local step 600 was fixed before the donor run as its one-second hold boundary.
  Reusing it for initialization was chosen after inspecting that run, but no
  search across trace frames is permitted.

## Single-Treatment Contract

- Pin the donor report
  `41957cce41e8cdd97490f61750d8990ebd946f8efc8e36124ad7e2329a347890`,
  source trace `027b0911fa4565d8a23ce64f30dd8ce587a095c2b9ed52c68e810d3a5e73ead4`,
  particle trace `1b100786c13d1da1d03dcf4910522a10433a590329bf5abaa05f674179071248`,
  local-step-600 position hash
  `b56ab6028f611cb9ac87acc1b8058ed33eec46174ffaaf7bfab8bae349f94357`,
  and matching source-pose hash
  `6e2d22597c57578a3c561b26582c52519216aa303430a36fdf4aed655bf55134`.
- Convert each step-600 world position into the step-600 source frame, then map
  it through the step-0 source matrix and inverse authored particle-prim world
  matrix. For row-affine homogeneous points:
  `A0 = ((H600 @ inverse(S600)) @ S0) @ inverse(Lparticles0)`.
  Author `A0` as both `points` and `physxParticle:simulationPoints`.
- Keep particle ordering, count, widths, zero authored velocities, system,
  density, material, source pose/mass, rest offset zero, support, 600 Hz timing,
  thresholds, runner, robot, and controller unchanged.
- Do not author or mutate the source pose. Do not pre-settle at runtime.
- Preserve raw array order without claiming persistent particle identity.
- Zero inherited velocities are an initialization choice, not measured
  step-600 velocity replay. Particles continue rearranging in the donor hold.

## TDD And Implementation

1. Add failing pure tests for row-affine particle rebasing including a
   noncommuting rotation/translation case, float64 round-trip error at most
   `1e-12 m`, finiteness, shape/count validation, and deterministic hashes.
2. Add a small offline generator that validates the final report and NPZ hashes,
   validates same-step source-pose binding, selects exactly step 600, rebases
   positions, and writes a create-only USDA overlay with layer metadata. The
   reopened point3f quantization error must be at most `1e-7 m`.
3. Add overlay/config tests proving an explicit `World` default prim, sole
   rest-offset-zero sublayer, and only two physical property opinions: matching
   `point3f[] points` and `physxParticle:simulationPoints`. Do not author
   velocities, widths, transforms, source properties, or activation. Composed
   velocities must remain 3,600 finite zeros. The config differs from the 600 Hz
   config only in name, USD path, and performance label.
4. Run focused tests, compilation, and `git diff --check`.
5. Run one fresh no-robot filled treatment with the unchanged 2,401-record
   schedule and all-record motion/containment gate.
6. Audit reset-time source motion by comparing the composed authored source
   matrix and geometry center against candidate local step 0. Apply the same
   `2 mm / 1 deg` limits so movement before the recorded authority origin cannot
   be hidden.

## Decision

- Invalid lifecycle, provenance, shape, or artifact evidence yields no physics
  conclusion.
- If authored-to-local-step-0 motion exceeds the limits, or the valid run fails,
  conclude only that this fixed step-600-derived position candidate did not
  satisfy the gate. Stop further trace-frame candidates in this branch; this
  does not rule out particle initialization generally.
- If both startup audit and run pass, preserve one bounded four-second no-robot
  result and write a
  separately reviewed robot-present zero-action plan. Do not replace production
  or launch grasp from this diagnostic.
- No physical-equilibrium, mass, force, causality, repeatability, reliability,
  or product claim is authorized.

## Expected Files

- one offline settled-layout overlay generator
- one generated particle-position-only overlay under
  `assets/chemistry_lab/lab_001_fluid_eval/`
- one diagnostic config under `config/`
- focused generator/overlay/config tests
- immutable candidate evidence under
  `outputs/contact_grasp_passive_stability_20260716/`

## Runtime Outcome

- The generated layer is hash-bound to donor local step 600 and authors only
  matching `points` and `physxParticle:simulationPoints`; composed 3,600
  velocities remain inherited finite zeros. Rebased point3f hash is
  `eddddcb010e3078cf5d0ed60e369c7bd51470e94edb84cdc097b2b9ba60ff6ef`.
- The fresh candidate completed all 2,401 records with exact schedule, finite
  `(2401, 3600, 3)` float64 positions, zero per-record hash mismatches, and valid
  final artifact hashes.
- Reset-origin audit passed: authored-to-local-step-0 source translation was
  `0.00002092 mm` and rotation was `0.00001120 deg`.
- The authoritative report is `PASSIVE_STABILITY_PASS`. Maximum phase-relative
  source translation was `0.00015279 mm`, maximum tilt was `0.00015724 deg`, and
  all 3,600 particles remained in the source at every sample.
- This is one bounded four-second no-robot PASS for a trajectory-derived,
  position-only initialization. It does not establish equilibrium,
  repeatability, mass, force, reliability, or product readiness. It authorizes
  only a separately reviewed robot-present zero-action diagnostic, not grasp.

Evidence:

- `outputs/contact_grasp_passive_stability_20260716/step600_layout_600hz_filled_attempt_001/report.json`

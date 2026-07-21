# Level1 Pour Source Rest-Offset Diagnostic Plan

**Goal:** Test whether changing the source external shell's collision rest
offset from `-1 mm` to `0` suppresses the measured dry `1 mm` seating signature
and changes the bounded filled passive outcome. This is a one-property treatment
test, not proof of the baseline sliding mechanism.

## Evidence

- Runtime property query confirms that the source owns one cooked external-shell
  collider plus 145 wrapper colliders. Separate composed-USD readback resolves
  the shell's authored contact offset `2 mm` and rest offset `-1 mm`; Cube has no
  authored rest-offset opinion and uses the PhysX rigid-collider default.
- The dry source drops `0.99997 mm` during pre-roll, then remains stationary.
- PhysX defines pair rest distance as the sum of both shape offsets. The nominal
  source-support rest distance and measured dry drop agree to about `0.00003 mm`,
  which motivates this treatment but does not prove cooked-surface separation or
  sole causality.
- Particles are collision-filtered from the external shell, so particle-wall
  containment geometry is unchanged. The shape-level override changes every
  unfiltered shell contact, including support now and fingers in future runs.
- Filled baseline and explicit-density candidate both continue sliding, so this
  branch does not change density, mass, or fluid settings.

## Boundary

- Add a diagnostic overlay that changes only
  `/World/beaker2/mesh.physxCollision:restOffset` from `-0.001` to `0`.
- `restOffset=0` is PhysX-valid but is not yet a calibrated hull-to-render
  correction; convex cooking remains unchanged.
- Keep contact offset, friction, source mass/COM/inertia, support, wrapper,
  particles, timing, thresholds, runner, robot, and controller unchanged.
- Use no robot and no actions. Do not infer support force or authorize grasp.

## TDD And Runtime

1. Add failing overlay/config tests proving a sole base sublayer, exactly one
   candidate-layer rest-offset opinion, composed rest offset `0`, weaker
   inherited rest offset `-0.001`, composed contact offset unchanged at `0.002`,
   and a diagnostic config differing only in name, USD path, and performance
   label.
2. Add the overlay and config without changing runtime code.
3. Run focused tests and `git diff --check`.
4. Run one fresh dry treatment. It must complete all 481 records, remain within
   existing motion gates, and satisfy
   `abs(z_center(step 120) - z_center(step 0)) <= 0.0001 m`, at least 90%
   suppression from the pinned `0.99996765 mm` baseline. Compare the static
   authored source root with trace step 0 and step 120 so reset-time motion is
   not hidden.
5. Only if dry passes, run one fresh filled treatment with the same candidate.
   Judge it solely by the existing phase-relative `2 mm / 1 deg` motion and
   zero-spill containment gates.

## Decision

- If dry does not remove the `1 mm` seating signature, classify the authored
  override as not suppressing seating in this run and stop.
- If dry is corrected but filled fails, conclude only that rest offset explained
  is consistent with the common seating signature but was insufficient for the
  horizontal filled instability; stop this branch.
- If both pass, preserve the bounded associative evidence and write a separate
  robot-present zero-action plan. Do not replace production or launch grasp.
- Before any later close/contact-acquisition run, requalify aperture and contact
  impulse; do not reuse finger-contact conclusions from the `-1 mm` shell offset.

## Expected Files

- one rest-offset-only overlay under `assets/chemistry_lab/lab_001_fluid_eval/`
- one diagnostic config under `config/`
- focused overlay/config tests
- immutable dry and, conditionally, filled evidence under
  `outputs/contact_grasp_passive_stability_20260716/`

## Runtime Outcome

- `rest_offset_zero_dry_attempt_001` completed and suppressed the dry seating
  signature. Authored-to-baseline vertical displacement was `0.00001603 mm`;
  baseline-to-step-120 vertical displacement was `0.00003203 mm`, versus the
  pinned `0.99996765 mm` baseline. Maximum phase-relative translation was
  `0.00015525 mm`.
- `rest_offset_zero_filled_attempt_001` retained all 3,600 particles at every
  sample and maximum tilt was only `0.00079985 deg`, but motion failed. It first
  exceeded `2 mm` at local step 66, reached a phase-relative maximum of
  `2.89201501 mm`, and moved `2.85010151 mm` from the step-120 hold reference.
- The candidate therefore accounts for the common vertical seating signature
  in this run and removes the observed transient spill, but it is insufficient
  for horizontal filled stability. The rest-offset branch is closed without
  tuning another offset.
- No support-force, payload-mass, repeatability, production, or grasp claim is
  authorized. Future finger-contact conclusions cannot reuse the original
  `-1 mm` shell rest-distance assumptions.

Evidence:

- `outputs/contact_grasp_passive_stability_20260716/rest_offset_zero_dry_attempt_001/report.json`
- `outputs/contact_grasp_passive_stability_20260716/rest_offset_zero_filled_attempt_001/report.json`

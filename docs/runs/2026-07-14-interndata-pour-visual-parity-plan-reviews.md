# InternData Pour Visual-Parity Plan Reviews

## Reviewers

- Architecture: agent `Meitner`.
- Completeness and edge cases: agent `Newton`.
- Risk and evidence strength: agent `Pascal`.

All reviewers inspected the draft independently and made no file changes. All
three returned `REVISE`.

## Accepted Changes

1. Split `particleContactOffset`, initial spacing, point width, isosurface, and
   collider responsibilities instead of calling them one particle-size value.
2. Restore the complete public `12 x 12 x 25` grid. The live LabUtopia beaker is
   approximately 90.4 mm tall with a 32.0 mm interior radius, so the public
   75 mm-tall particle envelope fits; the draft's 60 mm assumption was wrong.
3. Label the fluid recipe as public evidence and the exact convex-decomposition
   treatment as an inferred collider hypothesis.
4. Reproduce and read back the public material-binding sequence rather than
   assuming every authored PBD value remains the effective final binding.
5. Override the existing collider through a run-scoped overlay instead of
   creating a second enabled collider. Include friction `1.0/1.0`, unique-route
   checks, cooking warnings, and a minimal open-cavity qualification.
6. Replace the draft's 95% static threshold with zero-leak 3D containment at
   every post-fluid step.
7. Split static physics and static visual verdicts. Do not infer collider failure
   from an empty isosurface or other combined-treatment failure.
8. Add stage units, up axis, gravity, exact reset/warmup order, same-tick image
   and particle sampling, and render-no-step checks.
9. Insert one fixed deterministic kinematic pour before any robot/expert replay.
   Freeze its transform trace and keep the random `PourController` out of scope.
10. Reuse the existing canonical beaker frame and classifier instead of
    reimplementing coordinate semantics.

## Partially Accepted Or Rejected

- The suggestion to keep `12 x 12 x 16` as a reduced fill was rejected because
  the complete public 25-layer grid fits the measured vessel and gives a more
  direct recipe test.
- The suggestion to end the whole plan after static hold was partially accepted:
  static hold remains a hard gate, but the product question is pouring, so the
  plan retains exactly one separately gated deterministic pour and removes
  direct expert replay.
- The draft's `PARITY_HOLD_PASS >= 95%` was rejected. It could hide up to 180
  leaked particles after restoring the full 3,600-particle grid.
- Pixel-level parity was rejected because cameras, vessels, and lighting differ.
  The visual claim is qualitative similarity/acceptability against pinned public
  reference frames.

## Final Scope

One public fluid recipe, one inferred collider hypothesis, one static run, and
at most one deterministic kinematic run after static eligibility. There is no
parameter matrix, fallback collider, or expert-controller integration in this
plan.

## Post-Execution Delivery Review

Three independent reviewers inspected the completed probe and first delivery
candidate from architecture, completeness/edge-case, and risk/evidence
perspectives. Reviewers `Popper`, `Goodall`, and `Russell` all returned blocking
findings rather than approving the first candidate.

Accepted remediation items:

1. Record the reviewed execution amendment: the native mesh collider hypothesis
   failed qualification, the final treatment is the explicit open inner-wall
   proxy, and the approach duration changed once from 60 to 120 steps after a
   measured three-particle tabletop failure.
2. Remove the offline `/VisualParticles` replay prim from delivery USDs. Bind
   the water material to the physical particle prim and make it the sole live
   visual authority; disable the competing isosurface presentation there.
3. Synchronize `PointInstancer.positions`, the legacy custom `points` attribute,
   and `physxParticle:simulationPoints` in the final snapshot. The first result
   USD had contradictory arrays hidden by its replay proxy.
4. Mark initial and result USDs as snapshots with `/World` as `defaultPrim` and
   state explicitly that they contain no prescribed pour animation.
5. Report final exclusive counts, intermediate airborne-stream semantics, pose
   error, and visual verdict in a portable evidence manifest using relative
   paths.
6. Remove dangling material bindings, restore missing stainless-steel textures,
   validate nested and root manifests, and reopen both roots from a clean
   directory with `LoadAll`.
7. Treat the evidence videos as offline decimated PhysX-readback replay, not as
   proof that a live render proxy follows simulation.

Final approval is intentionally deferred until these changes are regenerated,
tested in Isaac Sim 4.1 from a clean copy, visually reviewed, and resubmitted to
the same three review angles.

## Visual Review Iteration

The first delivery-render review failed for two concrete reasons: its motion
check deliberately displaced the source beaker by 15 mm and created an
unrepresentative apparent spill, while the result delivery still rendered a
`PointInstancer` that looked like a smooth cyan slab and exterior collar.

The remediation was narrow and test-first:

1. Replace the artificial displacement check with 30 logical steps of natural
   settling in Isaac Sim 4.1.
2. Normalize the existing physical particle prim to `UsdGeom.Points` for both
   delivery roots, preserving 3 mm widths and removing the separate replay
   visual authority.
3. Re-render initial-before, initial-after-settle, and final-result states from
   the isolated copy with matched context and close cameras.

The final clean-room reviewer returned `PASS` with high confidence for all six
images. It found no visible tabletop spill, below-table particles, floating
cloud, or particles outside the beaker silhouette. The cyan bands at the
transparent target base were judged optical overlap within the glass outline,
not an exterior pool.

## Final Contract Corrections

The first post-execution architecture/risk review found two blocking contract
errors that were corrected before delivery:

1. `/World/beaker1` had been authored as a second parent kinematic actor. The
   target is now static; `/World/beaker2` is the only parent compound actor.
2. The runtime report still claimed smoothing strength `0.5`, while the pinned
   public InternData code authors `50`. Runtime authoring and readback now both
   use `50`.

Making the target truly static exposed one sub-millimeter center-boundary
escape during the source pre-hold. The correction was geometric and fixed:
both open inner-wall panel rings are inset by the 1.5 mm rendered particle
radius. Static and kinematic modes now author the same two-beaker proxy
environment. The final source hold and 690-step pour both pass with no retry or
candidate sweep.

## Direct-Open Review

An independent clean-room reviewer then marked the first delivery entrypoint
`WARN`: it showed the raw `12 x 12 x 25` initialization block suspended in the
source beaker, although one second of physics settled it correctly. This was a
presentation defect for a colleague opening the USD directly.

The initial entrypoint now stores the validated 150-step source-hold positions
in both `points` and `physxParticle:simulationPoints`. A fresh isolated-copy
Isaac Sim 4.1 run retained all 3,600 particles inside the source through 30
additional logical steps. The replacement six-image clean-room review returned
`PASS` with high confidence: initial, live-stepped, and final states are clear,
with no visible spill, wall penetration, gross floating, or clipping. Granular
point texture remains a documented non-blocking presentation limit.

## Final Three-Angle Approval

The final architecture, completeness, and risk reviewers all returned
`APPROVE` after two evidence-only blockers were corrected:

1. Regenerate `delivery_manifest.json` and the root SHA manifest after the last
   clean-validation wording change.
2. Replace stale draft run paths with the final static and
   `interndata_kinematic_pour_probe_final_inset_20260714` paths, then add
   `evidence/trace_provenance.json`.

The provenance report pins the final 151-state static trace and 691-state
kinematic trace by byte size and SHA-256, records the `262` maximum transit and
`8514` transit-particle-state aggregate, and proves that the delivered initial
and result position hashes match static step 150 and kinematic step 690. The
package has 13 hash-bound key artifacts and 171 root-manifest entries; both
manifest checks pass.

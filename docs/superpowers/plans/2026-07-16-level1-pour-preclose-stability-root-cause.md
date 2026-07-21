# Level1 Pour Pre-Close Stability Root-Cause Plan

**Goal:** Determine whether the fully dynamic `beaker2` reproduces the pre-close
`2 mm / 1 deg` motion and containment failures in a bare no-robot bootstrap, and
whether those observations differ between dry and 3,600-particle treatments.
Preserve enough raw pose and particle data for independent reclassification.
Report filled-payload load authority as unresolved unless a separately qualified
measurement mechanism becomes available.

## Product Boundary

This is a no-action diagnostic, not another grasp attempt.

- Do not create a robot, task, controller, gripper command, approach, close,
  lift, transport, or pour action.
- Do not write the source pose, use a kinematic target, add a joint, attach the
  source, filter source-to-support contact, or relax the existing stability
  limits.
- Open the exact production contact-grasp USD and preserve its source, support,
  wrapper, collision groups, physics scene, cameras, and 3,600-particle layout.
- A dry control may deactivate only the particle actor before the timeline
  starts, in an anonymous session layer before World construction or reset.
  Record that initialization mutation and make no runtime mutation.
- Results can authorize a later root-cause correction plan, but cannot authorize
  a real grasp or a load-bearing product claim by themselves.
- Missing PBD contact reports cannot be interpreted as absence of direct
  particle-to-support contact. This probe does not claim contact-force or filled
  mass authority.

## Confirmed Facts

- The replacement native Expert run stopped before close at physics step 154
  after `2.01718098 mm` source translation and also observed one transient
  tabletop particle at step 152.
- The authored wrapper identifies parent-local Y as vessel-up.
- The exact support under the source is `/World/Cube`; `/World/table` is lower
  and is not the intended support contact.
- The current asset authors `0.02 kg` dry source mass. Runtime PhysX property
  query confirms that dry rigid-body mass, COM, and inertia.
- The particle actor authors zero mass and density, so its effective runtime
  contribution is unknown.
- The old G1 artifact used one terminal observation after a combined 480-step
  reset period. It did not retain pose, contact, or containment history and is
  not sufficient for this decision.

## Implementation Scope

1. Add `run_contact_grasp_passive_stability_probe.py` as a dedicated one-
   treatment parent/child runner plus a non-Isaac offline comparison mode. One
   invocation runs exactly one explicit `dry` or `filled` treatment in a fresh
   process. Never reset from dry to filled inside one PhysX process.
2. Use a race-safe create-only artifact publisher and reserve each treatment
   directory exclusively. The child publishes its trace and provisional report
   before `SimulationApp.close()`. The parent enforces a pinned timeout, sends
   terminate then kill to the child process group if needed, reaps it, validates
   all artifact hashes, and writes the only authoritative final report.
3. Load the exact native Expert dynamic-fluid config and production contact USD
   without constructing the Franka, task, controller, cameras, render products,
   or online surface. Call `configure_particle_usd_readback()` before World
   construction. Record an ordered bootstrap ledger and every intentional
   difference from the failed production run.
4. Extract a robot-independent dynamic-source stage validator from the existing
   production validator. Reuse it in both production validation and the probe so
   source, external shell, wrapper, particle system, collision groups, physics
   scene, `/World/Cube` support, and `/World/table` checks do not diverge.
5. Extract the production pre-close center-translation and configured-axis tilt
   calculation into one pure helper. `ContactFrictionDynamicVessel` and the probe
   must share it, including the existing `1e-12 m / 1e-9 deg` boundary
   tolerances. The configured local Y vessel axis remains authoritative.
6. For `dry`, author only `active=false` on
   `/World/InternDataParityFluid/Particles` in an anonymous session layer before
   World construction. For `filled`, author no particle-active override. Verify
   the active particle-set inventory and record the mutation ledger.
7. After all setup and reset work is complete, capture one non-integrated
   baseline record at local step 0. Execute exactly 120 `world.step(render=False)`
   pre-roll calls and 360 hold calls. The hold reference aliases the post-step
   pre-roll record 120, yielding exactly 481 state records. Assert every call
   advances the absolute world step by one and world time by exactly configured
   dt. Do not render or issue unaccounted Kit updates after the authority origin.
8. Sample in one fixed post-step order: PhysX source pose and velocities,
   transformed local geometry center and vessel axis, current dynamic wrapper
   frame, then filled particle readback and classification. Record absolute and
   local step indices, phase, world time, pose/frame hashes, translation, tilt,
   velocities, partition counts, and first failure per class.
9. Preserve independently checkable trace artifacts:
   - a compressed source trace containing all 481 matrices, geometry centers,
     axes, velocities, indices, and times for both treatments;
   - for `filled`, all 481 exact 3,600-particle position arrays plus per-step
     hashes and partition records;
   - JSON summaries that reference the trace paths, byte counts, and SHA-256
     hashes rather than embedding large arrays.
10. Report three independent authorities:
    - `motion_stability`: valid only with complete timing and pose traces;
    - `containment`: filled only, valid only with complete runtime readback and
      dynamic source-frame classification;
    - `support_load_authority`: `UNSUPPORTED_BY_THIS_PROBE`, because current
      PBD contact reporting cannot prove particle-to-support bypass absence and
      the existing high-level contact sensor cannot prove complete fresh impulse
      accounting.
11. Add a pure offline comparator that requires matching config, dependency
    closure, runner, runtime, timing, gravity, stage, source, classifier, and
    common bootstrap contracts. Allowed differences are treatment, dry particle
    deactivation, process identity, traces, and outcomes. Its classifications
    are deliberately associative, not causal:
    - both unstable: common bare-scene/bootstrap instability candidate;
    - dry stable and filled unstable: particle-associated differential candidate;
    - dry unstable and filled stable: inconclusive;
    - both stable: failed native behavior not reproduced in this bare bootstrap;
      the next discriminator is robot-present zero-action, not a grasp rerun.

## Decision Gates

The `filled` motion and containment results pass only when all of these hold:

- exactly one baseline plus 120 pre-roll and 360 hold records are present;
- hold-reference translation is at most `0.002 m + 1e-12 m`;
- hold-reference vessel-axis tilt is at most `1 deg + 1e-9 deg`;
- every sampled particle partition totals exactly 3,600;
- every sample has `source=3600` and all other categories zero;
- all particle arrays are finite, hash-bound, and sampled against the same-step
  dynamic source pose;
- no source pose write, kinematic target, mechanical attachment, controller
  action, or runtime particle mutation is reported.

The `dry` treatment uses the same timing and motion gates, with containment
explicitly `NOT_APPLICABLE_BY_TREATMENT`. Motion PASS never implies support-load
or filled-mass authority.

## TDD Order

1. Add failing tests for the shared production pre-close metric, including local
   Y axis transforms, geometry-center versus root motion, exact threshold
   boundaries, zero/degenerate axes, booleans, NaN, and infinities.
2. Add failing tests for exactly 481 records, baseline/pre-roll/hold indexing,
   hold-reference aliasing, duplicate or missing steps, absolute-step offsets,
   nonmonotonic world time, and dt drift.
3. Add failing tests for filled trace summarization: exact 3,600 finite positions,
   partition total, transient recovery that remains latched, stale pose/frame
   binding, and first failure per containment/translation/tilt class.
4. Add failing tests for explicit dry mutation semantics, active particle-set
   inventory, filled no-opinion behavior, and mutation-ledger mismatches.
5. Add failing tests for offline report comparability and all four associative
   decision branches. Support-load authority must remain unsupported regardless
   of motion outcome.
6. Add lifecycle tests for create-only publication races, provisional persistence
   before shutdown, clean/nonzero/signal child exit, timeout before and after a
   provisional report, terminate-to-kill fallback, malformed/nonfinite JSON,
   artifact hash mismatch, wrong treatment/run nonce, and output reuse refusal.
7. Extract only the shared pre-close metric and robot-independent stage contract,
   then implement the smallest probe needed to pass tests. Do not change
   controller commands, physics values, source assets, or `main.py`.
8. Run focused tests, Python compilation, and `git diff --check` before Isaac.

## Runtime Sequence

1. Run one fresh bounded `dry` child with the pinned Isaac 4.1 managed
   interpreter and repository-only `PYTHONPATH`.
2. Audit its final report before launching `filled`. Stop on lifecycle, stepping,
   pose, trace, or artifact-authority failure. A support-load limitation does not
   block the filled motion/containment diagnostic because it is already declared
   unsupported.
3. Run one fresh bounded `filled` child with identical timing and source/support
   contracts.
4. Compare the two immutable reports. Do not tune thresholds, source pose,
   friction, solver settings, particle parameters, or support geometry between
   treatments.
5. Report one associative branch. If both are stable, write a robot-present
   zero-action plan. If either is unstable, write a narrowly matched diagnostic
   or intervention plan; do not call the association a proven physical cause.
   Do not launch another grasp from this plan.

## Prohibited Claims

- numeric filled payload mass, per-particle mass, liquid density, physical
  volume, or water parity;
- complete or fresh particle/support contact authority, or absence of bypass;
- load-bearing grasp capacity or a production finger-impulse threshold;
- causal attribution to particles, support, robot, task, controller, gravity,
  friction, COM, inertia, or collision geometry from one dry/filled pair;
- product stability, reliability, determinism, or product GO.

## Expected Files

- `tools/labutopia_fluid/run_contact_grasp_passive_stability_probe.py`
- `tests/test_contact_grasp_passive_stability_probe.py`
- `utils/isaac_fluid_evaluation.py` for shared pre-close and stage-contract
  extraction without behavior change
- this plan with architecture, boundary-case, and risk review updates
- fresh immutable runtime outputs under a new
  `outputs/contact_grasp_passive_stability_20260716/` directory

## Runtime Outcome

- `dry_attempt_001` is excluded from physics interpretation because its
  pairwise-valid Isaac clock trace exposed an overly strict accumulated-time
  comparison in the probe. A focused regression test was added before changing
  schedule validation; no physics value or acceptance threshold changed.
- `dry_attempt_002` completed with 481 records and passed. The source settled
  downward by `0.99996765 mm` during pre-roll, reached its maximum
  `1.00002496 mm` displacement at local step 13, and moved only
  `0.00010943 mm` from the hold reference through local step 480. Maximum tilt
  was `0.00030497 deg`.
- `filled_attempt_001` completed with all 481 source poses and all
  `481 x 3,600` particle positions hash-bound. One particle was classified on
  the tabletop at local step 18 and recovered on the next sample. Source
  translation first exceeded `2 mm` at local step 44, reached
  `3.66260781 mm` by the hold reference at step 120, and moved another
  `2.74098501 mm` through step 480. Maximum tilt was only `0.33706996 deg`.
- The filled source was not settling at the terminal sample: its final
  horizontal speed was `14.97745 mm/s`, versus `0.00117 mm/s` for dry, and its
  last-60-sample mean horizontal speed was `12.32294 mm/s`, versus
  `0.00221 mm/s` for dry.
- The immutable offline comparison is
  `PARTICLE_ASSOCIATED_DIFFERENTIAL_CANDIDATE`. This is an associative result,
  not proof of particle force, payload mass, or a causal mechanism. It does not
  authorize another grasp.

Runtime evidence:

- `outputs/contact_grasp_passive_stability_20260716/dry_attempt_002/report.json`
- `outputs/contact_grasp_passive_stability_20260716/filled_attempt_001/report.json`
- `outputs/contact_grasp_passive_stability_20260716/comparison_001.json`

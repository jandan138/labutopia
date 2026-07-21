# Level1 Pour Native Expert Dynamic Fluid Baseline Plan

**Goal:** Run the original LabUtopia `beaker2` Expert pick-and-pour trajectory
against the 3,600-particle online-fluid scene while the source beaker remains a
fully dynamic PhysX body held only by finger contact. No source pose following,
kinematic target, fixed joint, hidden attachment, or source-to-finger collision
filter is permitted.

## Confirmed Baseline

The native non-fluid task already uses physical beaker contact:

- `PourTaskController` selects the legacy `PickController`.
- `beaker2` closes to `0.028 m` on each finger joint, then lifts `0.5 m`.
- The native pick orientation comes from Euler XYZ `[0, 90, 30]` and the
  approach falls back to world `[-1, 0, 0]`.
- The native pour tracks the gripper, uses its default Euler XYZ
  `[0, 90, 10]`, and rotates joint 6 at `-1 rad/s`.
- The generic manual gripper writer is activated for the glass rod only;
  `beaker2` has no native per-step pose writer.

The online-fluid kinematic ownership mode is a later stability mechanism, not
the native beaker behavior. It is not used by this baseline.

## Implementation Scope

1. Add an orthogonal `expert_control_profile` configuration. Keep
   `source_ownership=contact_friction_dynamic_v1` for source physics and
   monitoring, while `expert_control_profile=native_expert_v1` selects the
   legacy `PickController`, native pick forward call, and native pour dispatch.
   Existing online configs explicitly declare their current profile rather than
   relying on source-ownership inference.
2. Do not infer picker selection from source ownership. Contact ownership still
   requires bilateral contact qualification, dynamic readback, drift/loss
   monitoring, pre-pour containment, and zero attachment use.
3. Bridge native close onset with an observer-only latch set when phase 4 has
   actually emitted its close action. The post-forward `_event` value is not
   authoritative because it advances one control interval before that action.
   Also latch lift emission and reject acquisition that first occurs during lift.
4. Preserve native control semantics in this mode:
   - no configured pick position or orientation override;
   - native `beaker2` close target `0.028 m`;
   - native `0.5 m` lift target;
   - gripper-tracked pour positioning and default legacy quaternion bytes;
   - direct RMP control-frame targets with no fixed `tool_center` pose adapter.
5. Repair the production `ContactFrictionDynamicVessel` construction by passing
   the external source shell, explicit object-frame vessel-up/grasp axis,
   contact band, bilateral height tolerance, and normal thresholds from config.
   Use that configured axis for pre-close tilt instead of hard-coded local Z.
6. Add a sibling config and leave the existing native, synthetic-fluid, and
   ContactPick behavior unchanged. Existing online configs gain only an explicit
   profile declaration and the existing ContactPick config gains the strict
   geometry fields already required by its monitor. The sibling uses the dynamic
   contact USD, fixed initial layout, and one attempt.
7. Keep the first run diagnostic and fail closed. A controller-complete episode
   is accepted only if the source actually lifts, the bilateral gate qualifies,
   no contact loss is latched, all 3,600 particles remain in source before pour,
   and no prohibited attachment mechanism is reported.
8. Make monitor failure mode-independent: a latched pre-close, timeout, loss, or
   sensor failure aborts native PICKING or POURING before another action. Require
   the atomic pour controller to finish before terminal success in the native
   profile.
9. Strengthen final dynamic acceptance to require the exact dynamic ownership
   record, `source_dynamic=true`, `mechanical_attachment_used=false`, current
   valid grasp, and zero pose-writer/kinematic-target counters. Product GO uses
   `expert_episode_accepted`, not the weaker task-transfer `success` metric.
10. Label the first run accurately as legacy Expert command-policy parity in the
    30 Hz online-fluid loop, not exact 60 Hz temporal replay. The particle mass
    authority is audited separately; until a positive effective payload is
    measured, the run cannot claim a load-bearing filled-liquid grasp even if the
    visual transfer succeeds.

## TDD Order

1. Extend controller tests to prove native picker construction and native
   forward dispatch under dynamic contact ownership.
2. Prove native close requests become true only after a phase-4 close action was
   emitted, lift-before-acquisition fails, and attachment requests remain false.
3. Add config contract tests for exact native parameters and absence of all
   synthetic attachment keys.
4. Extend builder tests to require every strict geometry argument, a derived dry
   payload impulse floor, and the configured object-frame up axis.
5. Add finalization tests rejecting the wrong ownership record, mechanical
   attachment, a non-dynamic source, nonzero writer counters, and terminal
   contact loss.
6. Implement the smallest controller, builder, config, and acceptance changes.
7. Run focused CPU tests and Python compilation before Isaac.

## Runtime Sequence

1. Launch one headless GPU-backed Isaac 4.1 attempt with a fresh evidence
   directory and video enabled. This first attempt is diagnostic, not an
   automatic product claim.
2. Audit the first physical cause in this order: pre-close source motion,
   bilateral contact acquisition, lift/retention, pre-pour containment,
   transport, pour transfer, terminal partition integrity.
3. If one concrete implementation defect is identified, correct only that defect
   and run one fresh replacement attempt. Do not tune multiple grasp parameters
   or fall back to synthetic attachment.
4. Report GO only for a complete physical-contact transfer. Otherwise preserve
   the evidence and report the exact NO-GO stage.

## Expected Files

- `controllers/pour_controller.py`
- `controllers/atomic_actions/pick_controller.py`
- `controllers/atomic_actions/pour_controller.py`
- `utils/isaac_fluid_evaluation.py`
- `utils/fluid_evaluation_loop.py`
- `main.py`
- `config/level1_pour_online_fluid_native_expert_contact_v1.yaml`
- existing online-fluid configs for explicit profile/strict geometry fields
- `tests/test_atomic_pour_controller.py`
- `tests/test_isaac_fluid_evaluation.py`
- `tests/test_fluid_evaluation_loop.py`
- `tests/test_level1_pour_online_fluid_config.py`

## Runtime Result

The bounded diagnostic is `NO_GO_PRE_CLOSE_SOURCE_MOTION`. No further retry is
authorized by this plan.

- Attempt 001 used local Z as the configured grasp-height axis and stopped at
  physics step 133 with `1.0331135786 deg` apparent pre-close tilt. The authored
  wrapper identifies parent-local Y as vessel-up, so this was corrected as the
  one concrete implementation defect allowed by the retry policy. Its evidence
  remains immutable under
  `outputs/native_expert_dynamic_20260716/attempt_001/evidence`.
- Replacement attempt 002 used the authored Y axis and stopped at physics step
  154 when pre-close source translation reached `0.00201718098 m`, above the
  fixed `0.002 m` limit. Tilt remained below the limit at
  `0.8505818880 deg`.
- Attempt 002 emitted no close or lift command, acquired no contact, and used no
  mechanical attachment, source pose writer, or kinematic target. The dynamic
  grasp contract and expert episode acceptance are therefore false.
- The 120 Hz containment ledger also observed one transient tabletop particle
  at physics step 152 (`pre_pour_source_min=3599`), although the terminal frame
  returned to `source=3600`. This independently fails pre-pour containment.
- The impulse floor was `0.001635 N*s` per finger, derived only from the
  authored `0.02 kg` dry-vessel mass. It is not filled-payload authority.
- Independent visual review of the initial and terminal camera pairs returned
  WARN: the robot and both beakers are visible, but no contact, grasp, lift,
  pour, spill, or clearly visible source displacement is demonstrated.

Authoritative replacement evidence:
`outputs/native_expert_dynamic_20260716/attempt_002/evidence/episodes.jsonl`.

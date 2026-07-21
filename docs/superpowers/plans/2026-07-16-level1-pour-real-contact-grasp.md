# Level1 Pour Real Contact Grasp Continuation Plan

**Goal:** Replace synthetic source-vessel ownership with a dynamic beaker held
only by Franka finger contact and friction in Isaac Sim 4.1, then complete the
existing online-fluid lift, transport, and pour task.

**Current state:** G0 dynamic ownership and G1 filled static hold pass. G2 real
grasp does not pass. The latest top-down attempt pushes the beaker before close,
records no qualifying bilateral contact, and terminates with `contact_timeout`.
G3-G5 have not started.

**Hard constraints:** No source pose following, kinematic targets, teleporting,
fixed joints, surface grippers, hidden attachment, or external-shell-to-finger
collision filtering. A failed physical topology must result in an explicit
NO-GO decision, not a fallback to the old synthetic attachment.

## Decisions From Plan Review

Three read-only reviews covered architecture, boundary cases, and physical and
delivery risk. Their common decisions are:

1. Stop full-episode experiments at G2 until geometry, control frames, finger
   velocity units, and evidence accounting are authoritative.
2. Reject the current top-down rim pinch unless cooked-collider measurement
   disproves the observed clearance problem. The only plausible existing-asset
   candidate is a side-body pinch below the rim, subject to a swept-volume GO
   gate.
3. Do not add more contact branches to the generic `PickController`. Add a
   contact-specific sibling controller and leave the legacy controller contract
   unchanged.
4. Latch one grasp frame before approach. Never recompute the target from a
   beaker that has already been pushed.
5. Make displacement, tilt, containment, contact, and prohibited-writer checks
   cumulative at 120 Hz. A later reset or terminal frame must not erase an
   earlier violation.
6. Treat every experiment attempt as an immutable evidence unit with a unique
   output directory and provenance hashes.

## Phase 0: Freeze and Repair Evidence Authority

Before changing the trajectory:

1. Record the current commit, dirty diff SHA256, config SHA256, composed USD
   closure SHA256, Isaac/PhysX version, CLI, seed, physics dt, and control dt.
2. Add `run_id`, `attempt_id`, and a process-global sample index. Reject a
   non-empty evidence directory and duplicate attempt/sample keys.
3. Seal every attempt as completed, failed, or interrupted. Never mix g2/g2b/
   g2c/g2d records as one run.
4. At 120 Hz, latch maximum displacement and tilt, minimum source-particle
   count, maximum counts in every non-source partition, first spill step,
   non-finite count, contact loss, and prohibited API calls.
5. Replace hard-coded zero writer counters with instrumentation around actual
   source/USD pose writers, teleports, and kinematic-target APIs.
6. Make reset evidence prove source pose and velocity restoration, particle
   state restoration, empty contact frames, and cleared gate/controller state.
7. Fix acquired-contact freshness: a repeated or stale physics step cannot
   preserve a grasp or clear contact-loss history.

TDD additions for this phase:

- Attempt-ledger uniqueness and interrupted-attempt sealing.
- Substep spill that disappears before the 30 Hz observation still fails.
- Reset cannot erase an earlier attempt's cumulative violations.
- Stale acquired contact increments loss instead of preserving validity.
- Prohibited-writer instrumentation fails on any real writer invocation.
- Final expert acceptance requires 3,600-way partition integrity, zero
  non-finite particles, and zero cumulative below-table particles.

## Phase 1: Establish Mechanical Feasibility

Run two small Isaac 4.1 probes before another fluid episode.

### 1A. Frame and velocity probe

- Resolve and store the fixed transform between RMPFlow's `right_gripper`
  control frame and the evidence/config `tool_center` frame.
- Bind RMPFlow integration to its actual 30 Hz command cadence while physics
  remains 120 Hz.
- Record finger DOF names, types, indices, positions, API velocities, finite-
  difference velocities, and measured inner-pad gap.
- Keep the `0.002 m/s` qualification threshold only if API and finite-
  difference velocity agree in meters per second.

### 1B. Cooked-collider swept-volume probe

- Use the actual composed PhysX colliders, not visual bounds.
- Measure the beaker's candidate body band, rim, open finger inner faces,
  contact/rest offsets, palm, table, and neighboring geometry.
- Evaluate top-down and side-body topology without closing or lifting.
- For a topology to pass, per-side open clearance must exceed the combined
  contact offset, measured controller tracking error, and a 1 mm numerical
  margin. The full swept path must avoid palm/rim/table contact.
- The pre-close pose must be reachable with no source contact, no table contact,
  source displacement over 2 mm, source tilt over 1 degree, or particle spill.

Expected decision: top-down rim insertion is likely NO-GO because its ideal
clearance is only about 2.3 mm per side and can fall below 1 mm when misaligned.
Side-body pinch is promoted only if the cooked probe confirms roughly 5 mm per
side at a specific below-rim grasp band.

If neither topology passes, stop. The compliant product choices are a narrower
physical vessel, a physical handle, or a different gripper. Synthetic attachment
is not an acceptable product fallback.

## Phase 2: Implement One Contact-Specific Grasp Path With TDD

Create a `ContactPickController` selected only by
`source_ownership=contact_friction_dynamic_v1`. Keep legacy `PickController`
behavior unchanged.

The contact controller has explicit phases:

1. `PREGRASP`: fully open the gripper and move to a collision-free waypoint.
2. `ALIGN`: converge in full 6D to the frozen grasp frame.
3. `INSERT`: move along the validated approach axis at a bounded near-object
   speed; abort instead of chasing the source if it moves or tilts.
4. `SETTLE`: hold the pre-close pose and verify zero unexpected contact and
   zero source motion.
5. `CLOSE`: close at a bounded rate toward one geometry-derived preload target.
   Do not run a target matrix.
6. `CONTACT_SETTLE`: hold the measured aperture and qualify bilateral contact.
7. `LIFT`: generate rate-limited waypoints rather than jumping to a final pose.
8. `HOLD`: prove load-bearing retention before transport.

The grasp frame is computed once from the validated object-frame grasp band and
the measured `tool_center <-> right_gripper` transform. It is not recomputed
from live source pose during approach.

Improve grasp qualification to require:

- Current raw contact from each exact finger body to the external source shell.
- Five consecutive and distinct 120 Hz physics steps.
- Opposing inward contact normals and opposite-side projection.
- Contact points inside the approved vertical grasp band, with left/right
  height difference no more than 5 mm.
- Validated finger velocity units and a settled closing speed.
- A load-bearing impulse threshold derived from measured total effective
  payload mass, friction, dt, and a 2x safety factor. Do not assume the current
  `0.001 N*s` value is sufficient until this calculation is complete.

Retention after acquisition uses contact load, contact freshness, and measured
source-to-gripper slip. It does not reuse an unvalidated closing-speed rule as
the only retention criterion.

## Phase 3: Sequential Runtime Gates

### C0 Dry approach probe

- Robot plus empty dynamic beaker; online surface disabled.
- Validate only pregrasp, align, insertion, settle, and close geometry.
- This probe can reject a topology but cannot accept the production grasp.

### C1 Wet approach probe

- Restore all 3,600 particles; online surface remains disabled.
- Do not lift.
- At every 120 Hz step before close: `source=3600` and every other partition is
  zero; displacement is at most 2 mm; tilt is at most 1 degree.

### G2 Real contact acquisition

- 3,600 particles, surface disabled.
- Pass the improved bilateral load-bearing gate once.
- No pre-contact source movement beyond C1 limits.
- All prohibited mechanism counters remain zero.
- Do not perform three repeated runs at G2; promote one clean deterministic
  pass to G3.

### G3 Lift and hold

- Enable the production online surface.
- Lift `0.10 m` at no more than `0.05 m/s`, then hold for 240 physics steps.
- Actual lift must remain within `0.08-0.12 m`.
- Source-to-gripper drift must remain within `5 mm / 5 deg`.
- Invalid contact gaps may not exceed 2 physics steps, and valid retention must
  cover at least 95 percent of the hold.
- Before tilt, all 3,600 particles must remain in source at every sampled
  physics step.
- Run exactly three consecutive reset-grasp-lift-hold attempts in one process.

### G4 Transport and pre-pour hold

- One clean promoted run after G3.
- Source speed at most `0.10 m/s`; angular speed at most `15 deg/s`.
- Preserve the G3 contact and drift limits.
- Hold at the pre-pour pose for 60 physics steps.
- Pre-tilt containment remains exactly `source=3600`.

### G5 Pour and terminal settle

- Pour at `-0.35 rad/s`, then settle for 240 physics steps.
- Final target count is at least 3,240 of 3,600.
- Cumulative below-table and non-finite counts are zero.
- Every partition sum remains exactly 3,600.
- Post-tilt tabletop splash is reported and visualized but is not alone a
  failure.

## Retry and Stop Policy

- One initial run and one rerun after one identified root-cause correction per
  gate.
- Never use `max_attempts` as a hidden parameter sweep.
- Stop immediately on geometry NO-GO, frame/unit mismatch, pre-close source
  motion beyond the limit, pre-tilt containment loss, contact loss, prohibited
  writer use, or repeated failure at the same gate.
- Change only the first demonstrated physical cause between runs.

## Final Verification and Release Checklist

After G5 passes:

1. Run the focused CPU suite, the actual composed-stage contract tests, two
   Isaac reset/contact smoke tests, and the full repository test suite.
2. Run one clean G0-G5 episode in a new evidence directory with all provenance
   and artifact hashes.
3. Produce exact-camera 30 FPS video and review contact, lift, transport, pour,
   and terminal frames independently with `render-visual-reviewer`.
4. Measure dry-scene, particles-without-surface, and complete online-surface
   throughput using the same trajectory and cameras.
5. Update reports only with the clean promoted run; enumerate all failed and
   interrupted attempts rather than selecting only successful evidence.
6. Do not commit, push, deploy, or clean unrelated worktree changes unless the
   user explicitly requests the release step.

## Expected File Scope

- Add `controllers/atomic_actions/contact_pick_controller.py` and focused tests.
- Keep contact selection and grasp-frame construction in
  `controllers/pour_controller.py`.
- Keep physics-step contact/load monitoring and stage contracts in
  `utils/isaac_fluid_evaluation.py`.
- Add immutable attempt and cumulative 120 Hz evidence accounting in
  `utils/fluid_evaluation_loop.py` and its output setup in `main.py`.
- Validate sensor DOF mapping in `robots/franka/franka.py`; avoid changing the
  behavior of non-contact Franka tasks.
- Preserve the sibling contact-grasp USD/config and the already passing dynamic
  ownership/collision-role design unless a failing composed-stage test proves a
  defect.

## Immediate G2 Slice Review Addendum

The architecture, boundary-case, and physical-risk reviews of the next slice
converged on this implementation order:

1. Do not publish a side-body grasp pose from visual bounds. First run a dry,
   surface-off measurement probe against the composed PhysX scene. It must
   report the cooked source, finger, hand, support, and table geometry; the
   fixed control-frame error; API and 120 Hz finite-difference finger velocity;
   and a swept-path clearance result. The probe is single-attempt and cannot
   emit close, lift, or pour actions.
2. Preserve both raw collider paths and resolved rigid-body paths in contact
   evidence. Canonicalize body order with an explicitly named normal convention
   before deduplication; do not infer normal sign from an unnamed vector.
3. Express the approved contact band in a geometry-center-relative source frame
   with an explicit configured height axis. This asset's rigid-body local Z is
   not assumed to be vessel-up. Transform points with the full row-affine
   inverse and normals with rotation only.
4. Use one authoritative per-step gate result for acquisition and retention.
   It must include exact external-shell attribution, named finger sides,
   inward/opposing normals, all contributing points inside the approved band,
   at most 5 mm representative-height mismatch, distinct physics steps,
   settled per-pad speed, and the derived per-finger impulse threshold.
5. Derive the threshold as
   `safety_factor * effective_payload_mass * gravity * physics_dt /
   (2 * effective_friction)`. The safety factor is fixed at 2. The composed
   friction, gravity, and measured filled-payload mass are evidence inputs; the
   authored 0.02 kg dry-vessel mass alone is not sufficient.
6. Add a probe execution mode orthogonal to source ownership. Its controller
   may terminate successfully after contact settle, must keep contact monitoring
   active through terminal sampling, and must never transition to LIFT, HOLD,
   or POURING. Probe acceptance is separate from production expert acceptance.
7. A no-lift contact pass proves acquisition geometry only. Load-bearing status
   remains blocked until G3 lifts the filled vessel and passes retention/slip
   gates.

The current top-down pose, zero-offset horizontal substitution, 0.037 m close
target, and 0.001 N*s threshold remain NO-GO inputs. They must not be reused as
fallbacks if the cooked-collider probe rejects the side-body candidate.

## Feasibility Probe Runtime Recovery

The first formal probe launch found that this Isaac 4.1 runtime may terminate
the Python process from `SimulationApp.close()`. The probe currently writes its
manifest only after shutdown, so both successful measurements and caught
runtime errors can be lost. Architecture, boundary-case, and evidence-risk
reviews require this recovery sequence:

1. Add lifecycle regression tests for a pre-shutdown report followed by normal
   return, `SystemExit`, a nonzero child exit, and a runtime exception. The test
   must parse current report content from inside the fake `close()` call; file
   existence alone is insufficient.
2. Use a parent/child launch contract. The Isaac child atomically writes one
   strict-JSON provisional report with `shutdown_status=pending` before closing
   the app. The non-Isaac parent observes the actual child return code and
   writes the only authoritative final report. A missing/invalid provisional
   report or nonzero/signal child exit seals `PROBE_RUNTIME_ERROR`, even if the
   measurements looked promotable before shutdown.
3. Reject an existing final or provisional path. Write through a same-directory
   temporary file, flush and fsync it, and atomically rename it. Preserve the
   runtime exception and traceback as primary evidence; record shutdown failure
   separately rather than overwriting it.
4. Run the focused CPU tests, then launch a new corrected feasibility attempt
   with the pinned Isaac 4.1 interpreter and repository-only `PYTHONPATH`. The
   prior launches are interrupted pre-G2 feasibility attempts, not the same
   immutable attempt. Do not alter the globally installed `/isaac-sim`
   environment, whose NumPy 2.2.6 installation is binary incompatible with its
   bundled extensions.
5. Fail the prerequisite decision closed. The report must include error-free
   cooked source, both fingers, hand, table/support geometry, resolved contact
   offsets, source width, and an explicit symmetric-clearance result. Merely
   obtaining one non-null ray width is not a pass. Free-space finger motion is
   velocity qualification, not contact acquisition or a G2 close attempt.
6. Audit the authoritative final manifest before changing grasp configuration.
   A runtime error, pending shutdown, incomplete geometry, or failed clearance
   remains NO-GO evidence; only a complete prerequisite pass permits the
   separate side-pose swept-volume step.

## Feasibility Result and Stop Decision

The corrected `g2h_feasibility_probe` child exited cleanly and its parent-sealed
manifest reports `NO_GO_PREREQUISITE_MEASUREMENT_FAILED`. It is the stop result
for this slice; production side-body parameters are not authorized.

- The Lula `right_gripper` to USD `tool_center` frame check passes with
  `1.37e-6 m` translation error and `9.65e-5 deg` rotation error.
- The cooked open inner gap is `0.0774165383 m`. Sampled external-shell widths
  range from `0.07096344 m` to `0.07131712 m`, leaving only
  `0.0030497091 m` per side at the widest sampled band.
- The known source contact offset (`0.002 m`) plus mandatory numerical margin
  (`0.001 m`) leave about `0.000049709 m` for both the unresolved finger contact
  offset and unmeasured controller tracking error. This cannot authorize a
  side-pose sweep.
- Both finger contact offsets remain PhysX-autocomputed and unresolved. The
  support sensor produced zero qualifying impulse samples. API and finite-
  difference pad velocities differ by up to `0.00236616 m/s`, exceeding the
  `0.002 m/s` agreement tolerance.
- The artifact predates the added fail-closed table/clearance checklist, so it
  is not retroactively rewritten. Those omissions reinforce the NO-GO; they do
  not justify another live attempt after the stop decision.

Authoritative evidence:
`outputs/contact_grasp_20260716/g2h_feasibility_probe/runtime_summary.json`.

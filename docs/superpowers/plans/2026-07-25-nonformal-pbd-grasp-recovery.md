# Non-Formal PBD Grasp Recovery Plan

## Purpose

Recover the physical grasp stage before attempting a full PBD pour. The current
historical controller reaches the final PICKING event but does not lift the
dynamic source vessel. This plan first establishes a dry, unbound lift gate,
then reintroduces the 4096-particle PBD runtime, and only then retries the full
historical controller.

All results remain `NON_FORMAL_HISTORICAL_REFERENCE`. This plan cannot authorize
formal evaluation, G0-G4 promotion, acceptance, or delivery.

## Current Evidence

- Latest full run: `artifacts/runs/nonformal-historical-pbd-4096-20260723-174000/`.
- Runtime: Isaac Sim 4.1 sealed child, GPU dynamics, explicit `600 Hz` physics,
  `10` integration substeps per historical controller frame.
- PBD trace: `664` records with `4096` particles, finite readback, and changed
  positions.
- PBD static containment: passed; no particle explosion, no out-of-wrapper
  count, and no tail leak in the recorded interval.
- PhysX contact trace: both finger bodies contact the generated
  `FluidSafeWrapperCanonical` wall.
- Source motion: approximately `8.3 mm` maximum upward motion, below the
  controller's `0.12 m` pick threshold.
- Controller: `659` records, remained in `PICKING`, failed at pick event `7`,
  and never entered `POURING`.
- Existing authoring defect: the generated dynamic-wrapper path disables the
  native `/World/beaker2/mesh` collision, so the fingers contact the fluid
  wrapper instead of the external source shell.
- The selected reviewed fixture does not author the Franka robot itself. The
  sealed G0 child composes `assets/robots/Franka.usd` at `/World/Franka` and
  binds its SHA-256 before checking the contact topology.
- Latest sealed topology result:
  `artifacts/runs/nonformal-pbd-grasp-recovery-g0-runtime-20260725-006/`.
  The topology contract passes with 145 wrapper colliders, enabled native
  source shell, bilateral finger colliders, and no source-to-robot filtered
  pairs.
- Latest parent-validated geometry result:
  `artifacts/runs/nonformal-pbd-grasp-recovery-g0-geometry-v2-20260725-026/`.
  Effective-runtime-v2 attestation, static table cooked query, role offsets,
  topology, collision inventory, and timeline checks pass. The direct
  pregrasp sweep is a genuine PhysX `sweep_box_all` witness, but it hits the
  source wrapper/native shell, the target beaker wrapper, and `/World/Cube`.
  Parent validation therefore emits `G0_NO_GO`; no lift or filled PBD run is
  authorized. The USD `BBoxCache` table bound is also implausibly large,
  while the cooked table catalog is finite and approximately
  `2.3449 x 2.6447 x 0.0820 m`; no scale factor is inferred.

## Hard Constraints

- Keep `/World/beaker2` dynamic, gravity-enabled, and non-kinematic.
- No attachment, fixed joint, surface gripper, source pose/velocity write,
  kinematic target, force, torque, impulse, or software grasp update.
- Do not filter external-shell-to-finger collision to manufacture a lift.
- Do not treat robot-to-wrapper contact as valid grasp contact. It is a
  prohibited-contact diagnostic result.
- Do not modify the historical controller state machine to bypass PICKING.
- Do not tune the lift threshold downward.
- Use a fresh run directory for every Isaac execution and preserve failed runs.
- Use the formal Isaac 4.1 interpreter and effective-runtime v2 evidence for
  every physics decision.

## Topology Decision

The preferred source is an existing reviewed contact-grasp fixture, selected and
hash-pinned before execution:

`assets/chemistry_lab/lab_001_fluid_eval/lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda`

The selected fixture must prove all of the following in a read-only topology
gate before any controller action:

- `/World/beaker2/mesh` remains an enabled external collision surface.
- `/World/beaker2` is the only dynamic rigid-body owner for the source compound.
- The source mass is authored on the dynamic parent and is read back at runtime.
- The 145 `FluidSafeWrapperCanonical` colliders remain present for particle
  interior support.
- Existing particle/environment collision-group topology is unchanged.
- There is no source-to-robot joint, attachment, filtered-pair, or collision
  group that suppresses the external shell contact.
- Any contact used by the grasp gate is an exact left/right finger to external
  shell pair. Wrapper-to-finger contact is a terminal NO-GO.

The generated `author_inner_wall_collision_proxy(dynamic_actor=True)` path is
not an acceptable production grasp topology for this gate until it is rewritten
as a separately reviewed, opt-in authoring path that preserves the above
contract. It currently disables the native mesh collision and transfers mass
from the mesh rather than using the reviewed parent mass authority.

## Staged Gates

### Gate 0: Topology And Cooked Geometry

Create a fresh read-only Isaac child that composes the selected fixture with the
reviewed local Franka asset and reports:

- composed USD dependency closure and hashes;
- dynamic source root, mesh, wrapper, and rigid-body ownership;
- all 145 wrapper colliders and their collision/material/group inventory;
- source, finger, hand, support, and table cooked geometry;
- effective contact/rest offsets and stage units;
- external-shell swept clearance for the chosen grasp band;
- source-to-robot relation and collision-filter audit.

Any missing cooked geometry, unresolved offset, non-positive swept clearance,
wrapper-to-finger route, or altered collision group is `G0_NO_GO`. Do not proceed
to a lift run after a G0 failure.

### Gate 0 Execution Contract

The Gate 0 implementation is split into a pure parent and one sealed Isaac 4.1
child. The parent freezes the selected fixture, Franka asset, source files, and
command before launch. The child must bootstrap `SimulationApp`, emit the
matched effective-runtime-v2 receipt before USD/PhysX inspection, compose the
fixture with the local Franka asset, and keep the timeline stopped throughout
the inspection. The parent then recomputes the clearance decision from the
child certificate and binds the receipt, input closure, child logs, certificate,
and decision hashes into one fresh manifest.

The certificate must contain the composed collision inventory, runtime-resolved
contact/rest offsets for every required role, the selected bilateral grasp
candidate, and positive signed-clearance samples for the external shell,
internal wrapper, hand, finger pads, and table support. A missing or inferred
offset is unresolved; an AABB-only estimate or a single raycast is not a
clearance certificate. The existing `run_robot_table_geometry_probe.py` is
therefore reference code only and cannot be relabeled as Gate 0 authority.

### Gate 1: Dry Unbound Lift

Use the existing native empty-beaker lift authority where possible:

`tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py`

The dry treatment must disable particles before World creation without changing
the source/robot collision topology. It must record:

- exact bilateral finger-to-external-shell contacts;
- explicit source/support contact loss before lift;
- source rise of at least `0.12 m`;
- exactly `60` contiguous airborne retention samples;
- no source/support recontact;
- no source writer, attachment, kinematic, force, or velocity calls;
- no robot-environment or finger-to-wrapper contact during the accepted window.

The dry gate must be independently `PASS` before any filled PBD controller run.

### Gate 2: Filled PBD Hold And Lift

Run a fresh `4096`-particle treatment with the same source topology and the
declared `600 Hz` integration schedule. Keep the historical controller disabled
for the first probe segment. Verify:

- initial and final particle counts remain `4096`;
- all positions remain finite;
- particle motion is nonzero;
- all particles remain in the source wrapper before tilt;
- source shell/finger contact remains the only accepted grasp contact;
- source pose/velocity writer audits remain clean.

If Gate 1 passes but Gate 2 fails, classify the cause as filled-load or PBD
coupling failure, not as a controller failure.

### Gate 3: Historical PICKING Then POURING

Only after Gates 0-2 pass, run the historical `PickPourTask` and
`PourTaskController` unchanged. The run must show:

- `PICKING` transition through event `7`;
- source height crossing `0.12 m`;
- `current_phase=POURING`;
- PBD containment through the pick/transport prefix;
- no prohibited writer or artificial coupling;
- separate fixed-camera video and optional wrist-camera video.

The wrist camera must not be used as the primary review view because it is
attached to `/World/Franka/panda_hand` and moves with the grasp motion.

## TDD Sequence

1. Add failing pure tests for the topology contract: native mesh collision must
   remain enabled; wrapper count must be 145; parent dynamic ownership and mass
   authority must hold; wrapper-to-finger contact must be rejected; filtered
   source-to-robot pairs must be rejected.
2. Add failing dry-lift classifier tests for support loss, `0.12 m` rise,
   60-step retention, recontact, nonfinite values, and prohibited writers.
3. Add a failing PBD trace test requiring `4096` finite particles throughout
   the accepted pre-tilt interval and rejecting a zero-particle reset tail as
   part of the active episode.
4. Implement the smallest opt-in fixture/runner change that preserves the
   reviewed topology. Do not change `main.py` or the historical controller.
5. Run focused tests, `py_compile`, and `git diff --check`.
6. Execute Gate 0 in a fresh sealed child.
7. Execute Gate 1 only after Gate 0 is `GO`.
8. Execute Gate 2 only after Gate 1 passes.
9. Execute Gate 3 only after Gates 0-2 pass.

10. If a gate fails, preserve its fresh run directory, classify the failure as
     runtime, topology, geometry, coupling, or controller evidence, and continue
     only after the diagnosed cause has a concrete code or asset change.

### Attempt 025 Geometry Authority Amendment

The v2 G0 child now performs a static cooked-collider query for `/World/table`
using a temporary disabled rigid-body query layer, flattens runtime-resolved
offsets into the pure G0 schema, and records a parent-recomputed certificate
hash. Its clearance witness subdivides the direct tool-to-pregrasp translation
into 32 fixed-orientation PhysX box-sweep segments and covers every wrapper,
shell, hand, finger, and table role. A raycast is retained only as a skipped
legacy reference; it is not used for the decision.

Attempt 025 remains a geometry NO-GO. The current robot placement and direct
translation are not an admissible pregrasp path because the inflated sweep
reports `/World/Cube`, `/World/beaker1/FluidSafeWrapperCanonical/*`, and
`/World/beaker2/FluidSafeWrapperCanonical/*` hits, with zero precontact pad to
shell clearance. The raw witness is preserved in the run report; the malformed
zero-clearance candidate is not promoted to a certificate. A new placement or
trajectory requires a separately hashed candidate and a fresh G0 run.

### Attempt 027 Collision Provenance Audit

The sealed child now records top-level provenance for unexpected sweep hits.
`/World/Cube` is not authored by the G0 runner or the offset overlay. Its prim
stack contains only the localized package layer
`dependencies/lab_001_localized_20260707/lab_001.usd`; it is an invisible
`Mesh` with `PhysicsCollisionAPI`, `PhysicsMeshCollisionAPI`,
`PhysxCollisionAPI`, `PhysxTriangleMeshCollisionAPI`, and enabled collision.
Its composed world bounds are `[-0.5, 0.5]^3`, so it is a real hidden unit cube
at the world origin, not the tabletop. `/World/beaker1` is separately traced
to the same lab package plus the expected tabletop placement overlays and is
the legitimate target beaker.

Attempt 027 remains `G0_NO_GO`. The hidden cube must not be silently ignored or
removed from the reviewed asset. The next change is an explicit fixture review:
either author a hash-pinned diagnostic treatment that disables/removes only
this confirmed stray collider, or retain it as an environment obstacle and
plan around it. Neither option changes the historical controller.

## Complete End-To-End Roadmap

This roadmap starts from the current `G0_NO_GO` state and ends with the
non-formal target: a physically real 4096-particle source-beaker grasp, lift,
transport, and pour that enters the unchanged historical `POURING` phase.

### Phase 0: Freeze Current Evidence

- Preserve `artifacts/runs/nonformal-pbd-grasp-recovery-g0-geometry-v2-20260725-027/`
  as the current baseline.
- Keep `NON_FORMAL_HISTORICAL_REFERENCE` on every result.
- Do not modify the original `lab_001` package, `Franka.usd`, historical
  controller, or existing reviewed fixture.

### Phase 1: Build A Cube-Only Diagnostic Treatment

- Author `lab_001_g0_disable_hidden_cube_collision_v1.usda`.
- The overlay may only disable `/World/Cube` collision. It must not delete the
  prim, change its visibility, move geometry, or touch `beaker1`, `beaker2`,
  wrappers, table, robot, particles, materials, or collision groups.
- The G0 runner must bind both offset-overlay and cube-overlay hashes into the
  composed fixture identity.
- Pure tests must prove that the overlay affects only `/World/Cube` collision
  and preserves the original asset bytes.

Acceptance: a static parent-side fixture audit shows `/World/Cube` collision
disabled by exactly one overlay, with no other USD opinion differences.

### Phase 2: Re-Run G0 With The Cube Treatment

- Run a fresh sealed G0 geometry child.
- Runtime identity, topology, offsets, static table cooked query, collision
  inventory, timeline, and parent certificate recomputation must remain clean.
- The direct pregrasp witness must no longer contain `/World/Cube`.

Acceptance: the only remaining NO-GO causes, if any, are explicit
`beaker1`/wrapper/shell path collisions or a missing candidate.

### Phase 3: Define A Collision-Free Pregrasp Candidate

- Use runtime cooked geometry and PhysX scene-query sweeps; do not infer path
  clearance from USD `BBoxCache`.
- Evaluate a finite set of hash-pinned candidates, starting with a lift-first
  approach: move the tool straight upward from its current pose, move laterally
  over the source, then descend into the pregrasp pose.
- Reject any candidate with wrapper/native-shell precontact, `beaker1`, table,
  support, cube, or other unallowlisted environment hits.
- Reject any candidate that assumes invisible or non-cooked geometry does not
  matter.

Acceptance: the parent emits a valid `G0_GO` certificate only if every
required collider role has positive signed clearance for every segment of the
selected candidate.

### Phase 4: Gate 1 Dry Unbound Lift

- Run `run_native_expert_empty_beaker_unbound_lift_probe.py` with the selected
  candidate and Cube treatment, with particles disabled before World creation.
- The robot must contact only `/World/beaker2/mesh` with both finger pads.
- The source must lose support, rise at least `0.12 m`, and remain airborne for
  `60` contiguous samples.
- No wrapper-to-finger contact, table/support recontact, source writer,
  attachment, kinematic call, force, torque, impulse, or software coupling is
  allowed.

Acceptance: the dry gate is independently `PASS`; otherwise classify and fix
the cause before touching PBD.

### Phase 5: Gate 2 Filled PBD Hold And Lift

- Reintroduce the reviewed `4096`-particle PBD runtime with the same source
  topology and `600 Hz` schedule.
- Keep the historical controller disabled for the first hold/lift probe.
- Verify `4096` finite particles at the beginning and end, nonzero particle
  motion, no out-of-wrapper particle before tilt, and clean source-pose and
  source-velocity writer audits.
- Verify finger-to-external-shell contact remains the only accepted grasp
  contact.

Acceptance: the filled probe passes with no leak and no artificial coupling.
If it fails while Gate 1 passed, classify as filled-load/PBD coupling failure.

### Phase 6: Gate 3 Historical PICKING Then POURING

- Run the unchanged `PickPourTask` and `PourTaskController`.
- The controller must traverse `PICKING` through event `7`, cross the source
  height threshold, and enter `POURING`.
- The run must retain PBD containment through the pick/transport prefix and
  provide fixed-camera video; wrist video is optional and non-authoritative.

Acceptance: the historical controller reaches `POURING` without prohibited
writes, wrapper contacts, collision filtering, threshold changes, or controller
edits.

### Phase 7: Final Non-Formal Evidence Bundle

- Produce a manifest that binds:
  - G0 certificate and fixture closure;
  - Cube-only overlay hash;
  - Gate 1 dry-lift result;
  - Gate 2 filled-PBD result;
  - Gate 3 controller trace;
  - all stdout/stderr and video/trace hashes;
  - effective-runtime-v2 receipt;
  - final classification `NON_FORMAL_HISTORICAL_REFERENCE`.
- Do not compare this result with formal G0-G4 evidence, historical Isaac 4.5
  evidence, or unreviewed runtime evidence.

Acceptance: a reviewer can recompute every claim from the manifest and raw
artifacts without trusting a narrative summary.

### Explicit Failure Handling

- If Cube treatment does not remove the cube blocker, stop and audit the
  treatment; do not plan around an unknown geometry change.
- If `beaker1` remains on every direct path, select a lift-first or side
  approach candidate; do not relocate the target beaker for convenience.
- If wrapper contact appears again, classify as topology or contact-routing
  failure, not controller failure.
- If dry lift fails after `G0_GO`, classify as grasp/control failure.
- If filled lift fails after dry lift passes, classify as PBD/filled-load
  coupling failure.
- If historical controller still stops in `PICKING` after Gate 2 passes,
  classify as controller/trajectory mismatch only then.


## Artifact And Stop Rules

Every gate writes a fresh manifest containing runtime receipt, source/config/USD
closure hashes, command, seed, timing, stdout/stderr hashes, trace hashes, and
terminal decision. Failed runs are preserved and never relabeled.

Stop immediately on:

- runtime identity or preflight mismatch;
- source writer or attachment call;
- wrapper-to-finger contact used as grasp evidence;
- source mesh collision disabled;
- source/robot filtering or unknown collision group change;
- nonfinite or missing particle readback;
- dry lift failure;
- repeated failure at the same gate without a new diagnosed cause.

## Verification Commands

Focused tests:

```bash
python3 -m pytest -q \
  tests/test_historical_june_collision_observe.py \
  tests/test_real_beaker_strict_step_schedule.py \
  tests/test_native_expert_empty_beaker_unbound_lift_probe.py
```

The Isaac commands must use the absolute formal interpreter from `AGENTS.md`.
No commit, push, cleanup, or unrelated worktree change is part of this plan.

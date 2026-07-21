# Real PBD Grasp And Pour Plan

## Product Decision

The selected product is a real closed-loop PBD grasp and pour. It must use the
current dynamic PBD vessel, its live collision model, and a newly produced
action trace. It must not reuse the frozen-v6 source actions, source transition
indices, action hashes, or replay wording.

The existing `_011` frozen-v6 output remains a rejected diagnostic. The legacy
geometry-aware v1 preflight also remains historical: it temporarily disabled
particles, made the source kinematic, filtered robot/source collision, disabled
source contact reporting, and authored a calibration body. It cannot establish
a real PBD grasp.

## Facts To Preserve

- The real PBD fixture is
  `lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda`.
- The source vessel is a dynamic 0.02 kg dry body; its external contact surface
  is the `beaker2/mesh` convex-decomposition collider and its liquid interior is
  a 145-collider invisible wrapper.
- The source vessel starts at the fixed PBD pose `[0.295, 0.075,
  0.8233382266115852]`.
- The current PBD fluid evidence shows pre-roll movement at micrometer scale,
  not the 6.6 cm source-trace mismatch. A same-scene dry/filled A/B measurement
  must nevertheless quantify particle-induced displacement before motion.
- The selected fixture's authored particle density/mass requires runtime
  verification. A dry-vessel mass threshold cannot certify a filled-vessel lift.

## Stage Gates

### G0: Cooked Geometry And Load Authority

Before dynamics, parent-seal a composed-PhysX clearance certificate for every
finite candidate close endpoint. It must include the cooked finger-pad, hand,
source-shell, source-wrapper, support, and table geometry; effective contact and
rest offsets; target tracking envelope; and signed swept clearance over the full
approach and close envelope. Any unavailable geometry, unresolved offset,
nonpositive margin, or candidate collision is NO-GO. The legacy `0.037 m`
endpoint is only a rejected historical candidate and cannot be reused unless G0
proves a positive margin for the current composed fixture.

G0 also seals runtime particle count, particle density/mass inputs, effective
filled payload authority, gravity, solver settings, and source mass. If the
fixture cannot demonstrate a nonzero, physically attributable filled load, G3
and G4 are blocked; a separate physically authored candidate asset is required
and may not be substituted silently.

### G1-D/G1-F: Same-Scene Dry/Filled Baseline

Run no-robot, same-PBD-fixture dry and filled passive holds with the same source
pose, collision topology, timestep, and pre-roll. Record source root/COM pose,
velocity, tilt, particle partition, and collision-state receipts. This measures
particle-induced equilibrium changes without conflating them with trajectory
differences.

Dry may deactivate only the declared particle prim before World creation. The
external shell, internal wrapper, source rigid-body role/mass, collision APIs,
offsets, source/table/target topology, solver settings, and composed USD closure
must match filled mode. The absent robot is an intentional G1 scope difference.
Each fresh reset epoch records baseline and every 600 Hz post-step source root
matrix, COM position, source-axis tilt, linear/angular twist, baseline contact
set, world counter/time, and collision inventory hash. Filled additionally
records canonical stable particle IDs, positions, source-frame hash, and complete
partition counts.

V2 config pins literal pre-roll/hold length and own-run plus dry/filled
differential bounds for translation, tilt, linear velocity, angular velocity,
contact-set changes, particle count, and ID coverage. The dry and filled runs are
diagnostic baselines, not grasp evidence. Any nonfinite particle, missing receipt,
nonzero forbidden identity delta, or bound breach is a NO-GO.

### G2-D/G2-F: Controlled Bilateral Close

Use the production `ContactPickController`, `FluidEvaluationLoop`, real Franka,
real PBD source, and synchronous full PhysX contact reports. Create a new v2
controlled-contact configuration and create-only runner; do not mutate the v1
geometry-preflight config or outputs.

Freeze one source-centered top-down target from the post-baseline live PBD pose.
G0 selects only from a parent-pinned finite candidate set; it cannot tune from a
filled run. The v2 config explicitly records object-frame grasp offset, world
approach, pregrasp/insertion distance, close speed/endpoint, tool and source
motion/penetration/impulse limits, bilateral certificate windows, and all phase
deadlines. Missing, defaulted, nonfinite, or post-dry-tuned values are protocol
failures.

Before arm motion, conduct only a real-finger aperture measurement; do not add a
calibration body, disable particles, make the vessel kinematic, filter contact,
or write source pose/velocity.

At every 600 Hz substep, complete immediate PhysX reports are the sole authority
for acquire/retain decisions; finger/hand sensors are same-step cross-checks.
All in-scope raw fragments are aggregated and classified before a latch, phase
change, or another step:

| Class | Rule | Result |
| --- | --- | --- |
| `BACKGROUND` | Exact presealed non-robot source/table baseline collider pair, current at reset | Record only; never earns grasp credit |
| `INTENDED_PRECONTACT` | Exact pad-to-external-shell pair in an approved precontact phase and every manifold/global gate passes | May enter audited precontact settle |
| `INTENDED_CLOSE_CONTACT` | Exact left/right pad-to-external-shell pair during close/retention and every gate passes | May count toward bilateral certificate |
| `PROHIBITED_CONTACT` | Any other robot/source/environment pair, robot-to-wrapper contact, finite breach, or changed baseline | Physical terminal |
| `UNKNOWN_CONTACT` | Missing, stale, malformed, unresolved, nonfinite, or lifecycle-invalid evidence | Protocol terminal |

`UNKNOWN_CONTACT` has precedence. Lift is prohibited in G2. G2-D and G2-F are
fresh processes; G2-F requires one-use parent authorization bound to the exact
G0/G1/G2-D artifacts but inherits no physical state from them.

### G3: Controlled Lift, Separate Implementation Gate

G3 is not enabled by the current close-only runtime. After G2-F passes, create a
separate reviewed implementation that adds an explicit lift/hold action grammar,
loop-owned phase-specific target tokens, full-manifold retention authority,
support-release deadline, filled-payload threshold, source/gripper slip bounds,
and a predeclared hold window. A G3 child starts from a fresh reset and repeats
G2 acquisition in the same child before any lift; a prior G2 artifact authorizes
launch only and never restores a frictional grasp.

### G4: Controlled Pour, Separate Implementation Gate

G4 is not enabled by the current controlled runtime. After G3 passes, create a
separate reviewed implementation that repeats G2 and G3 in one fresh child,
derives a target-frame policy, uses loop-owned transport/pour mode changes and
target tokens, and introduces phase-specific particle policy. Before
`POUR_STARTED`, every particle remains in source. During a predeclared pour
window, only source/target/bounded transit are allowed; tabletop spill,
below-table, nonfinite, missing/duplicate IDs, and unclassified particles use
literal fail limits. PASS requires literal target fraction/count, transit/spill
limits, final grasp certificate, and post-pour settle duration.

## Execution And Artifact Semantics

Stage artifacts are evidence, not simulator checkpoints. The lineage is
`G0 -> G1-D + G1-F -> G1 comparison -> G2-D -> G2-F`; later G3/G4 routes add
their own same-child acquisition prefixes. A promotion artifact authorizes a
fresh child launch but transfers no pose, contact, controller, target, or action
state.

Every parent-owned artifact is create-only and includes schema/stage/run/epoch
identity, predecessor byte hashes, config/USD/code/runtime/GPU/seed hashes,
source/collider inventory hashes, complete trace hash, particle-sidecar manifest,
terminal fact, parent recomputation, and a one-use authorization ledger keyed by
predecessor bytes and successor treatment hash. Parent validation uses no-follow
regular files, strict JSON, fsync, child quiescence, and fail-closed child exit.
The input closure is audited for forbidden frozen-v6 trace/config/adapter use;
this prohibits using frozen artifacts as inputs, not accidental equality of a
newly generated action hash.

## Safety And Evidence Contracts

- `FluidEvaluationLoop` remains the only owner of play/pause, action commit,
  articulation application, physics stepping, and terminal partial intervals.
- The immediate full PhysX report is canonical for acquire and retain decisions;
  finger/hand sensors are same-step cross-checks and disagreement is a protocol
  terminal.
- Every terminal contact receipt includes all manifold fragments, actor/body/
  collider identities, point/separation/normal/impulse data, pre/post source
  and finger state, phase, applied action receipt, substep slot, and a canonical
  evidence hash.
- A terminal substep prevents remaining substeps, future actions, lift/pour
  markers, observations, and frames in the same experiment.
- Parent validation combines writer interception with a composed-stage
  snapshot/diff allowlist for source transforms/velocity, kinematic state,
  collision filters/groups/APIs, attachment constraints, and source replacement.
- Each stage writes a create-only artifact and can be consumed only by the next
  stage after parent-side hash validation. No stage upgrades an earlier rejected
  result.

## TDD Implementation Sequence

1. Add failing G0 tests for composed cooked clearance, effective offsets,
   tracking envelope, particle/load authority, and every unavailable/negative
   margin outcome.
2. Add failing G1 tests for dry-only pre-World mutation, same-fixture identity
   delta, reset restoration, matched differential bounds, stale particle
   readback, and collision receipt changes.
3. Add failing G2 tests for a serializable contact-trajectory specification,
   fixed source-frame derivation, target token hashes, no lower-Z target after
   intended precontact, stale live poses, baseline background exception,
   wrapper/particle scope, lifecycle fragments, immediate/sensor disagreement,
   and terminal partial intervals.
4. Implement the narrow G0/G1/G2 pure specifications in
   `utils/controlled_contact.py`, then wire them through the existing controller
   and loop without altering the legacy geometry-preflight path.
5. Add failing tests for real-finger aperture measurement and eliminate the
   legacy temporary calibration body from the v2 path.
6. Add a v2 controlled parent/child runner and dry/filled configs with complete
   per-substep receipt serialization, parent recomputation, source mutation
   barrier, and atomic one-use authorization consumption.
7. Run focused tests, `py_compile`, and `git diff --check`. Execute one
   GPU-locked G0/G1/G2-D run; G2-F is allowed only after sealed parent GO.
   G3/G4 require their own implementation plans and three-way review.

## Reviewed Implementation Boundary

The first implementation is isolated in `utils/real_pbd_grasp_v2.py`. It does
not alter `main.py`, the legacy geometry preflight, the native close-only probe,
or `FluidEvaluationLoop`; those paths have different evidence semantics and
must remain historical diagnostics.

- G0 has a strict composed-geometry certificate validator, but a static USD
  inspection can only produce `G0_NO_GO`. A `G0_GO` requires a fresh Isaac
  child to read cooked geometry and runtime-effective offsets for every one of
  the 145 wrapper colliders, then seal positive swept witnesses.
- G1-D and G1-F are separately sealable before their comparison. G2-F may be
  close-only after a valid dry/filled baseline, but G3/G4 stay blocked unless a
  runtime measurement proves a nonzero filled payload.
- G2 seals a launch context containing the reviewed G0 certificate, selected
  candidate, derived trajectory/action targets, and reset-observed baseline
  roles. Every immediate PhysX envelope, classifier receipt, sensor receipt,
  source-state receipt, and applied-action receipt must bind that same context,
  phase, interval, and substep. Classification covers every current and
  transient occurrence; it cannot omit a wrapper or particle breach. Sensors
  are exact same-step cross-checks only and cannot grant contact credit.
- The immediate report retains and reconciles every raw PhysX header, contact
  range, friction range, and occurrence fragment. A `FOUND,LOST` contact is
  still terminal even if it is absent from the final current-pair set. The
  trajectory is rederived from the G0-selected candidate and post-baseline live
  source pose; a stale pre-baseline physics step cannot enter G2.
- Parent artifacts carry typed source evidence rather than an opaque evidence
  hash. G2-F consumes an authorization only after reparsing the exact parent
  bytes and a bound successor-launch manifest, before creating the one-use
  ledger entry. Rejected artifacts cannot be relabeled in place to authorize a
  successor.
- These hashes provide integrity and cross-receipt consistency, not independent
  issuer authentication. A production positive route still requires a
  parent-owned runtime, protected ledger, and external signing or capability
  boundary; none exists in the current static preflight.
- The selected fixture's static preflight is currently `G0_NO_GO`: it has 3,600
  particles and 145 wrapper colliders, while authored particle density and mass
  are both zero. This does not assert a zero runtime payload because Isaac may
  use defaults; it records that static USD cannot establish runtime payload
  authority. The prior explicit-density diagnostic is a closed branch and is
  not a production replacement.
- Static identity now hashes the resolved USD dependency closure, not only the
  root USD file, and rechecks the closure around authored-fact extraction. It
  remains diagnostic-only and cannot issue `G0_GO`.

Evidence: `outputs/real_pbd_grasp_v2_static_preflight_20260720_002/`.

## G0 Runtime Capability Audit Increment

The next implementation is a read-only Isaac child and an Isaac-free parent
validator. It is intentionally a capability audit, not a geometry-clearance
issuer: the currently available PhysX property query exposes cooked AABBs and
source mass/COM, but not complete cooked shape distances or PhysX-effective
contact/rest offsets. Therefore this increment can only issue `G0_NO_GO` with
specific missing-authority reasons.

1. Add a pure runtime-capability evaluator that validates a stopped-timeline,
   pre-step source snapshot, complete cooked source-collider query, authored
   offset readback, dependency closure, and query completion records.
2. Add an isolated parent/child runner. The child may load the current PBD USD
   and pump Kit for the asynchronous property query, but may not construct a
   task/controller, apply an action, reset/step a World, write the source, or
   alter particles/collision settings.
3. Parent-side code re-evaluates the child snapshot, seals typed `G0_NO_GO`
   source evidence and a create-only stage artifact, and preserves child logs.
4. The audit explicitly reports missing robot/table cooked geometry,
   effective offsets, signed swept-clearance witness, stable particle IDs, and
   runtime filled-load authority. None may be treated as a default or inferred
   GO condition.

## Stop Conditions

- No frozen-v6 action is used as a PBD grasp/pour action.
- No particle, collider, source pose, attachment, or collision-filter shortcut
  is allowed to improve the result.
- A visually plausible lift is not a G3 pass without the G2 bilateral-contact
  certificate and per-substep retention evidence.
- A visible stream is not a G4 pass without target-containment and spill gates.
- The existing rejected video is never overwritten, reclassified, or used as a
  positive baseline.

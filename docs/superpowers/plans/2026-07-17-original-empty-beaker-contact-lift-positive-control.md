# Original Empty-Beaker Friction-Lift Causal Probe Plan

## Goal

Determine whether the original non-fluid `level1_pour` Expert trajectory lifts
the empty `beaker2` because of bilateral finger-to-side-wall friction.

The evidence uses three fresh, same-seed child treatments:

1. `control`: original runtime with no probe-authored contact-report changes.
2. `instrumented_original`: original physics plus report-only contact APIs.
3. `zero_friction_ablation`: the same instrumented runtime and trajectory, with
   only effective finger/source static and dynamic friction changed to zero in a
   session layer.

A causal PASS requires the original treatment to complete a geometry-qualified
contact lift and retention, the report instrumentation to be non-perturbing, and
the zero-friction treatment to fail to lift while reaching the same pre-lift
contact pose. This is stronger and less convention-dependent than inferring
friction support from raw friction-vector direction alone.

## Claim Boundary And Decisions

The final decision enum and precedence are fixed:

1. `PROBE_RUNTIME_ERROR`: child launch, timeout, signal, cleanup, parse, identity,
   unexpected exception, or invalid application outcome. Highest precedence.
2. `PROBE_PROTOCOL_NO_GO`: incomplete audit, unknown contact identity, runtime or
   treatment-isolation contract mismatch, unsupported report semantics, or
   malformed/contradictory authority.
3. `CONTACT_REPORT_PERTURBATION_NO_GO`: the control and instrumented-original
   production prefixes differ beyond preregistered tolerances.
4. `ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL`: clean original treatment does not
   complete the required contact lift.
5. `EMPTY_BEAKER_RETENTION_CONTINUATION_FAIL`: clean original lift passes but the
   explicit no-new-action continuation does not retain it.
6. `ZERO_FRICTION_CAUSALITY_FAIL`: a contract-valid zero-friction treatment still
   lifts/retains or does not reproduce pre-lift geometry.
7. `ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS`: all positive and ablation gates
   pass. Lowest precedence.

The report also exposes the component booleans and physical measurements. The
60-step retention interval is explicitly a diagnostic continuation after the
production `PICKING -> POURING` transition, not part of the original Expert
trajectory. No result claims filled-beaker grasp capability.

## Minimal File Scope

- `tools/labutopia_fluid/run_original_level1_pour_empty_contact_lift_probe.py`
- `config/diagnostic_level1_pour_original_empty_contact_lift_v1.yaml`
- `tests/test_original_level1_pour_empty_contact_lift_probe.py`
- this plan

No production Python, USD, material, controller, task, or robot file may change.
The parent remains Isaac-free. Any need to edit production code stops this plan.

## Pinned Runtime

- Isaac Sim/PhysX: exact installed 4.1 builds, recorded and sealed
- Python: pinned project Isaac Sim 4.1 interpreter
- backend: production default `numpy`; never pass `--backend gpu`
- world: `World(stage_units_in_meters=1.0,
  physics_prim_path="/physicsScene", backend="numpy")`
- original scene: `assets/chemistry_lab/lab_001/lab_001.usd`
- robot: default Franka URL resolved by `Franka` with no `usd_path`; local robot
  substitution is forbidden
- production task/controller: `PickPourTask` and `PourTaskController`
- NumPy seed: `20260717`, applied immediately before explicit placement reset
- actual physics dt: exactly `1/60 s` within `1e-12 s`
- gravity: finite `[0, 0, -9.81] m/s^2` within `1e-6 m/s^2`
- maximum production steps: 1500
- child wall timeout: 240 seconds per treatment
- retention continuation: exactly 60 physics steps

The expected composed physics-scene paths in traversal order are exactly
`["/physicsScene", "/World/PhysicsScene"]`. The active `PhysicsContext` path must
be `/physicsScene`. The source, fingers, and `/World/Cube` may have empty authored
`physics:simulationOwner` only when runtime resolution proves the traversal-first
default is `/physicsScene`; `/World/PhysicsScene` must own none of the monitored
actors. The runner records raw owner relationships and never authors repairs.

The parent composes the diagnostic config once, freezes canonical bytes, and
passes those exact bytes to all children. Removing only the diagnostic subtree,
`name`, `max_episodes`, and output-routing fields must yield a canonical
production-visible projection equal to `config/level1_pour.yaml`.

Each child runs in a distinct mode-0700 treatment directory. The unchanged
collector receives a treatment-local relative `multi_run.run_dir`; no collector
or Hydra output may escape that directory. Children run sequentially, and the
parent proves full process/collector quiescence before launching the next.

## Runtime And Dependency Identity

Before and after every child, seal:

- raw source config, canonical composed config, runner, and production
  factory/task/controller/robot implementation hashes;
- original lab root layer and all loaded local dependency layers;
- resolved default Franka root identifier and loaded dependency identifiers;
- Isaac, PhysX, contact-report extension, and schema versions;
- stage units, active scene inventory/order, PhysicsContext path, actual dt,
  gravity, source/finger/support ownership, and GPU settings;
- direct, inherited, collection, and fallback physics-material resolution for the
  source, support, and every finger collider, including binding strength/purpose,
  layer provenance, raw solver-material values, combine modes, and friction model;
- the full collision-eligible finger-pair matrix and its runtime-effective solver
  material tuple under the installed PhysX combine-priority semantics.

Unresolved required dependencies, implementation drift, scene/owner ambiguity,
or runtime mismatch stops before interaction.

## Fixed Physical Identities

- logical/reset root: `/World/beaker2`
- physical source body/collider: `/World/beaker2/mesh`
- source mass: `0.019999999552965164 kg` within `1e-9 kg`
- source: rigid enabled, collision enabled, non-kinematic,
  `disableGravity=false`, and awake during accepted intervals
- left finger body: `/World/Franka/panda_leftfinger`
- right finger body: `/World/Franka/panda_rightfinger`
- initial support collider: `/World/Cube`
- native finger target: `0.028 m` per joint
- native lift target: `0.5 m`

All enabled finger colliders and all stage body/collider identities are resolved
at runtime. Define the sealed target pair set as the source collider paired with
every enabled collider owned by the exact left or right finger body. It must
contain at least one pair per side. Unknown actors, colliders, material subsets,
per-face materials, unresolved material indices, or non-sentinel prototype
indices are protocol NO-GO.

## Report Instrumentation

The control child may contain contact APIs created by the production Franka
sensor construction; “control” means no probe-authored report APIs or edits.
The child inventories those APIs and attributes before any probe edit.

For the two instrumented children:

1. Create World and default Franka, add the original lab reference, then save the
   current production edit target.
2. Create and select a dedicated anonymous session sublayer for probe edits.
3. Reuse existing finger/hand report APIs without modifying them when they already
   have zero threshold and empty `reportPairs`. Otherwise apply the minimal same
   report-only edits in both instrumented treatments.
4. Apply report API to the source body, set threshold `0.0`, and clear
   `reportPairs` to empty.
5. Flush/read back the changes, restore and verify the production edit target,
   then call `create_task()` and both normal resets.
6. The only permitted original-instrumented stage delta is the exact report API,
   zero threshold, and empty report-pair catalog. World counters, source/robot
   state, materials, constraints, filters, and collision properties must not
   change while installing it.
7. Sample one `ImmediatePhysxContactReporter` report after every existing
   production `world.step`. First-sample `PERSIST` bootstrap is allowed only for
   the exact source-to-`/World/Cube` pair. Every later index and lifecycle is
   consecutive with no missing active pair.

The zero-friction child has the same report delta plus the separately cataloged
ablation delta below. Any other stage change is protocol NO-GO.

For each current canonical collider pair, merge every report header and all of its
claimed contact-point and friction-anchor records before evaluation. A pair's
friction-anchor norm is the float64 sum of the Euclidean norm of every finite
world-space friction-anchor impulse in that merged occurrence; vectors never
cancel. A side's friction-anchor norm is the sum across all sealed target pairs
owned by that finger body. Contact normal impulse is likewise the float64 sum of
each finite contact-point impulse projected onto its own canonical
source-oriented normal; a negative projection is invalid rather than clamped.
One pinned integration case independently proves (a) whether each raw report
impulse acts on collider 0 or collider 1 and (b) whether each raw contact normal
points from collider 0 to collider 1 or the reverse. Use those two fixed
actor-order conventions to express contact normals and contact/friction-anchor
impulse vectors as acting on the source whenever the source is in the pair; no
path/name heuristic, lift-result fitting, or norm-only substitute may define
orientation or vector parity.
Overlapping/orphan ranges, unknown ownership, non-finite vectors, or ambiguous
actor orientation are protocol NO-GO. The child records all inputs, and the
parent repeats these reductions in canonical pair/header/record order.

## Zero-Friction Ablation

In the dedicated session layer, author one diagnostic physics material. All
target finger colliders must have the same complete baseline solver-material
tuple; otherwise stop before authoring. The diagnostic material has:

- static friction `0.0`
- dynamic friction `0.0`
- restitution scalar and combine mode copied from the baseline finger material
- a friction combine mode that, against the untouched source material, selects
  exact `+0.0` static and dynamic pair friction under the installed PhysX rules
- every unrelated solver-material attribute copied unchanged

Create no opinion on, and never bind or edit, `/World/beaker2`, its source
collider or descendants, `/World/Cube`, their ancestors, any collection that
includes them, or any existing/shared material. Bind the diagnostic material only
to the sealed enabled target finger colliders with explicit
stronger-than-descendants physics-purpose bindings. The only permitted authored
ablation delta is the new session-layer material and those exact finger-collider
bindings. No table/support, target, palm, other robot, scene, solver, mass,
damping, contact/rest offset, gravity, filter, group, or collision property may
change.

Before authoring, after readback, after both resets, and immediately before the
first interaction, seal every finger descendant's collider-enabled state,
geometry, owner, filter/group state, resolved material, and full solver-material
tuple. Enumerate every stage collider and derive the complete collision-eligible
counterpart set for each changed finger collider after resolving both-direction
filtered pairs, collision groups and exclusions, masks, merge groups,
self-collision rules, live collision flags, ownership, descendants, and
prototype/instance state. Observed contacts are not an adequate substitute for
this complete matrix, and the sealed set may not drift after interaction starts.

For every eligible pair, record the raw runtime PhysX material authority, selected
combine operations, and canonical finite float32 bytes for effective static
friction, dynamic friction, restitution, and every other exposed solver-material
term. Composed USD attributes alone are not authority. The child and parent both
recompute the pair table under the exact installed combine-priority semantics and
must agree with live runtime readback. Unsupported semantics, stale/lazy material
resolution, missing live authority, or disagreement is `PROBE_PROTOCOL_NO_GO`.

Relative to `instrumented_original`, the only permitted effective pair deltas are
that static and dynamic friction for every sealed target finger/source pair
change from finite values greater than zero to canonical `+0.0`. Target-pair
restitution, its combine operation, and every non-friction solver term remain
exactly unchanged. Every non-target pair's eligibility, selected combine
operations, and complete effective solver-material tuple remain byte-identical.
The source and `/World/Cube` material graphs, binding resolution, eligibility,
effective friction/restitution, and complete pair tuple also remain
byte-identical. Any non-target finger contact from the first production
transition through terminal is protocol NO-GO even when its effective tuple is
unchanged.

If one-sided finger binding cannot satisfy all of these conditions, stop before
interaction with `PROBE_PROTOCOL_NO_GO`. Do not fall back to source binding,
material tuning, collision filtering/exclusion, pose tuning, or a contact-modify
or other pair-scoped intervention. A pair-scoped mechanism requires a new,
separately reviewed plan.

The final pre-lift state is exactly `pre[k_lift]`, and `k_lift >= 1`. Contact-load
parity uses the complete merged occurrence generated by transition `k_lift-1`,
whose post-state is that `pre[k_lift]`. Whenever a target-point, support-point, or
support-friction-anchor parity gate below requires matching, it requires equal
record counts and a unique minimum-total-Euclidean-distance bijection in
source-local position coordinates; an absent or non-unique minimum assignment is
protocol NO-GO. Target friction-anchor records are not count-matched. At this
state, the zero-friction treatment must match the instrumented original within:

- controller event/action hashes: exact
- all non-finger Franka joint positions: `1e-6 rad`
- all non-finger Franka joint velocities: `1e-5 rad/s`
- finger joints: `1e-6 rad`
- finger joint velocities: `1e-5 rad/s`
- tool pose: `0.1 mm / 0.1 deg`
- source pose: `0.1 mm / 0.1 deg`
- tool/source linear velocity: `1 mm/s`
- tool/source angular velocity: `0.1 deg/s`
- target-pair contact counts: exact, with unique minimum-total-distance point
  bijections and every matched distance `<= 1 mm`
- per-side source-oriented normal impulse: `1e-5 N*s`
- source-to-`/World/Cube` support: current in both treatments with at least one
  contact point, same lifecycle and contact count; matched point distance
  `<= 1 mm`, normal angle `<= 0.1 deg`, and separation difference `<= 0.1 mm`;
  same friction-anchor count, matched anchor distance `<= 1 mm`, and each matched
  canonical source-oriented anchor-impulse vector difference `<= 1e-5 N*s`;
  aggregate normal-impulse and friction-anchor-norm differences each
  `<= 1e-5 N*s`
- all exposed non-target and source/support solver/contact-cache and warm-start
  bytes: exact; target normal-cache values: `1e-5 N*s`
- every contact-classification predicate has the same boolean result and signed
  native-unit margin in both treatments. For each matched point compute separate
  margins for normalized-height lower/upper bounds, inner-half displacement in
  meters, tangential pad-face clearance in meters, opposite-side displacement in
  meters, inward cosine, opposing-normal dot product, vertical-normal cosine, and
  aperture-rate limit in `m/s`. Each pair of margins must have the same sign and
  differ by no more than half the smaller absolute margin. Zero margin in either
  treatment is protocol NO-GO; margins of different units are never compared.

Target friction-anchor impulse is intentionally excluded from this parity list
because it, including its target tangential warm-start/cache entries, is the
intervened quantity. The listed non-treatment dynamic/contact values must satisfy
the parity gates. Missing or inseparable solver-cache authority is
`PROBE_PROTOCOL_NO_GO`.

The ablation PASS requires each side's friction-anchor norm to be `<= 1e-8 N*s`
for every current target occurrence from `k_lift` through terminal, maximum
post-lift source-COM rise below `0.02 m`, no crossing of the production `0.12 m`
threshold, and no 60-step airborne retention. If zero friction still lifts or
geometry differs before lift, friction causality is not established.

## Geometry Authority And Contact Qualification

Before interaction, seal the exact composed local bounds and transforms for the
source collider and every enabled finger collider using
`UsdGeom.BBoxCache(Usd.TimeCode.Default(),
includedPurposes=[UsdGeom.Tokens.default_, UsdGeom.Tokens.proxy,
UsdGeom.Tokens.render], useExtentsHint=False, ignoreVisibility=True)` and exactly
`ComputeLocalBound(prim)`. Guide-purpose bounds are excluded. Record the returned
range and matrix separately in float64 and require finite nondegenerate ranges.
Enumerate the eight raw range corners, transform them exactly once with the
returned `Gf.BBox3d` matrix using `Gf.Matrix4d.Transform`, then transform those
parent-space corners exactly once with the Default-time local-to-world transform
of `prim.GetParent()`. Never apply the prim local transform or the returned bbox
matrix a second time. To classify a world contact point in raw bbox coordinates,
apply the exact inverse sequence: parent-world inverse, then returned-bbox-matrix
inverse. Hash all raw and derived values and include them in the trace for parent
recalculation.

Definitions use float64 closed comparisons with no hidden epsilon:

- source vessel axis: the signed source-local basis axis whose reset-world
  direction has maximum dot with anti-gravity; require cosine `>= 0.95`
- source height: projection of the eight sealed source-local bound corners onto
  that axis; normalized height is `(h-h_min)/(h_max-h_min)`
- collider world bound center: arithmetic mean of its eight sealed local-bound
  corners after applying the collider's sealed world transform
- finger side bound center: center of the componentwise world-space enclosing
  bound of all transformed sealed-bound corners for enabled colliders owned by
  that exact finger body; an empty or degenerate side bound is protocol NO-GO
- closing axis at final pre-lift: normalized world vector from the left finger
  side bound center to the right finger side bound center, projected perpendicular
  to vessel up; a zero/degenerate projection is protocol NO-GO
- source world center: arithmetic mean of the eight transformed source-bound
  corners; source closing coordinate and half-width are the center and half-range
  of those corners projected onto the closing axis
- finger inner half: for each point, the world-space half-space whose boundary
  plane passes through its owning collider's world bound center and whose normal
  is the normalized vector from that center toward source world center; require
  nonnegative point displacement along that normal, and reject a zero vector
- finger inner contact face: choose the local bound axis/sign whose transformed
  face normal has the largest positive dot with the world vector from collider
  bound center toward source center; require that dot to be unique and `>= 0.8`
- finger pad interior: transform the point into finger-collider local coordinates;
  on the two axes tangent to the selected inner face require
  `min_i + 0.001 <= p_i <= max_i - 0.001` meters. The normal-axis coordinate is
  used only to select the two tangential axes and is not an additional distance
  gate: exact collider-pair attribution, inner-half membership, source-side
  position, and the source-oriented normal gates provide the normal-axis contact
  authority without an implementation-dependent contact-offset tolerance.

A qualified bilateral step evaluates every contact point from every current
target occurrence; selecting a representative or strongest point is forbidden.
It requires:

- at least one current sealed target pair on each side, with every current
  source/finger pair belonging to the sealed target set and containing at least
  one contact point;
- every point's source normalized contact height in `[0.20, 0.80]`;
- every point in its corresponding finger inner half and pad interior;
- every left and right point on opposite source sides, each at least `0.25`
  source half-width from the source closing coordinate;
- every point's source-oriented inward-normal cosine `>= 0.8`;
- every cross-side pair of source-oriented normals has dot product `<= -0.8`;
- every point has `abs(dot(normal, up)) <= 0.25`, excluding rim/underside normal
  lifting;
- finger aperture rate `<= 0.01 m/s` at final pre-lift;
- from the first production transition through terminal, no source contact with
  palm, non-finger robot, target, table, lab geometry, or unknown body; exact
  source-to-`/World/Cube` support is the sole exception while support remains
  current, through `pre[k_loss]` and report transition `k_loss-1` when `k_loss`
  exists, or through terminal when it does not;
- no finger/palm environment contact from the first production transition through
  terminal;
- transition `k_loss` permits only one source-to-`/World/Cube` `LOST` occurrence
  with zero contact-point/friction-anchor records and zero impulse; its post-state
  has no support, and no later source-to-`/World/Cube` report is allowed.

Any later LOST/missing bilateral report ends the interval and fails acceptance;
there is no grace gap.

## Production-Parity Loop And Action Receipts

Reproduce current non-fluid order exactly:

1. World, default Franka, original scene reference, `ObjectUtils`.
2. Production task construction, including camera reset.
3. Seed, explicit task reset, then production controller construction.
4. Require exactly two bootstrap resets and no later reset.
5. Each loop performs exactly one `world.step(render=True)`, then one
   `task.step()`. Do not invoke controller for `None` state.
6. Observe after task state and before exactly one controller call.
7. Apply each non-null production action exactly once. Its physical effect belongs
   to the following world transition.

Canonical action hashing fixes channel order, float64 little-endian finite values,
shape, and a bitmask for each `None` entry. The per-interval ledger records
pre/post phase/event, action bytes/hash, decoded targets, apply-entry,
normal-return receipt, apply index, and subsequent integrating transition.

Duplicate/missing calls, duplicate/missing applies, unknown apply outcome,
controller call on `None`, world stop, reset request, task timeout, failure before
the structurally valid clean pick-terminal outcome defined below, or any pour
action is protocol/runtime failure.

## Transition Indexing And Acceptance Intervals

Trace transition `k` contains state `pre[k]`, the single existing physics step,
state `post[k]`, and impulses generated by `pre[k] -> post[k]`.

- A `settled_supported` post-state has source/Cube support current, source linear
  speed `<= 0.001 m/s`, source angular speed `<= 0.1 deg/s`, finger aperture rate
  `<= 0.01 m/s`, and source-COM displacement from the preceding post-state
  `<= 0.0001 m`. The final settled supported COM is the latest post-state before
  `k_lift` that ends a run of at least ten consecutive `settled_supported`
  transitions. Absence of this exact window is protocol NO-GO.
- `k_lift` is the first transition integrating the first normally applied native
  lift action.
- The rise baseline is source COM in `pre[k_lift]`; pre-lift rise from final
  settled supported COM must be `<= 0.002 m`.
- The drift reference is the rigid source-to-tool relative matrix computed from
  source and tool world matrices in `pre[k_lift]`. Every later drift value is the
  translation norm and shortest-arc rotation angle between that fixed reference
  and the current source-to-tool relative matrix; no moving or first-airborne
  reference is permitted.
- In `instrumented_original`, bilateral geometry qualification is required
  continuously from `k_lift` through the `PICKING -> POURING` transition.
- When support loss occurs, `k_loss >= k_lift` is the first transition whose
  post-state has no source/Cube support. Its only Cube report is the
  zero-data/zero-impulse `LOST` occurrence above; any `FOUND`/`PERSIST`, support
  impulse, or later recontact fails. `instrumented_original` must define
  `k_loss`; the ablation may remain supported through terminal and omit it.
- When the threshold is crossed, `k_rise` is the first post-state at least
  `0.12 m` above the rise baseline. `instrumented_original` must define it; an
  ablation negative may omit it.
- Accepted airborne lift transitions exist only when both indices exist and are
  `k_loss..k_rise` inclusive.
- Duration is `(k_rise-k_loss+1)*dt`; boundary velocities are explicitly
  `v_pre[k_loss]` and `v_post[k_rise]`.

In the original instrumented treatment, every accepted airborne transition must
have qualified bilateral contact, no prohibited contact, source-to-tool drift
`<= 5 mm / 5 deg`, and per-side friction-anchor norm `> 1e-5 N*s`.

In `instrumented_original`, no action is returned at the first production
transition to `POURING`. Seal the production prefix, invoke no further controller
method, apply no new action, and observe continuation transitions `c0..c0+59`
inclusive. All 60 require the same bilateral/prohibited-contact/drift conditions.
Terminal source speed must be `<= 0.02 m/s`, angular speed `<= 5 deg/s`, and each
side must continue to report friction-anchor norm `> 1e-5 N*s`.

Every treatment has two structurally valid pick-terminal outcomes after the native
pick event/action/apply sequence through the terminal pick-controller event:

- it transitions to `POURING` with no action; or
- the native pick controller is done and the production phase check returns the
  ordinary `(action=None, done=True, success=False)` `PICKING` failure because the
  source did not reach the fixed lift threshold.

For control or `instrumented_original`, the ordinary clean failure is physical
`ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL`, not a runtime error. For the ablation,
the clean failure is the expected negative outcome, while a transition to
`POURING` is `ZERO_FRICTION_CAUSALITY_FAIL` when its lift/retention gates pass.
Any other application outcome is invalid. At either valid ablation terminal, seal
the production prefix, call no controller/task method, apply no action, and run
exactly 60 no-new-action physics transitions. The ablation causal gate evaluates
its fixed COM-rise, threshold-crossing, airborne-retention, contact, and terminal
motion evidence over the production prefix plus this continuation; it does not
use wall-clock timeout or an outcome-derived horizon as negative evidence.

## Prohibited-Mechanism And Force Audit

Treat `/World/beaker2` root and `/World/beaker2/mesh` body as separate authorities.
Install audit surfaces before explicit reset, record the legitimate reset root
placement write, then open a zero-write epoch.

Continuously audit:

- root/body ObjectUtils, singular/plural pose and velocity setters;
- physics-view kinematic targets;
- rigid-body force, torque, impulse, and force-at-position APIs, including tensor
  and physics-view variants;
- raw root/body xform, velocity, kinematic, gravity, collision, mass, and force
  attributes/schemas at controller/apply boundaries;
- `PhysxForceAPI`, force-field membership/relationships, and transient force calls;
- software-gripper add/update/release, including attach then release;
- all source-referencing USD/runtime joints, fixed/D6/surface-gripper constraints,
  PhysX attachments, and actor relationships;
- source/robot `FilteredPairsAPI` in both directions and on ancestors/descendants;
- collision-group membership/exclusion/filtered/merge groups and live collision
  flags.

Incomplete coverage is protocol NO-GO. The original and zero-friction treatment
must have zero post-reset writers, kinematic targets, forces, attachments,
constraints, and source/robot filters. Only the explicit report and ablation
session-layer deltas are allowed.

## A/B Non-Perturbation

Control and instrumented-original must match exactly in composed config bytes,
initial requested/read-back poses, reset count, controller event sequence,
canonical action hashes, applies, and controller outcome.

Before first source/finger contact they must match within:

- joints `1e-6 rad`
- tool/source pose `0.1 mm / 0.1 deg`
- linear/angular velocity `1 mm/s / 0.1 deg/s`

After contact, matched controller-event samples must remain within the same
limits. For contact predicates exposed by both treatments, compare only the
same-predicate signed margins in their native units using the same-sign/half-
smaller-margin rule defined in the pre-lift parity contract; never compare pose
tolerances directly with normalized, cosine, or velocity margins. Both must cross
`0.12 m` and transition to `POURING` on the same event sequence. Any larger
difference is `CONTACT_REPORT_PERTURBATION_NO_GO`.

The control child also executes the exact 60-step no-new-action continuation.
Control and instrumented-original continuation world indices and no-action
receipts match exactly; tool/source pose and linear/angular velocity match at
every post-state within the same limits above; and both satisfy the same kinematic
retention, drift, and terminal-motion outcome. Existing production contact-sensor
streams also match in lifecycle and pair identity wherever both treatments expose
them; `instrumented_original` supplies the complete authoritative
prohibited-contact decision. Any state or common-stream mismatch is
`CONTACT_REPORT_PERTURBATION_NO_GO`.

## Evidence And Parent Recalculation

Strict finite JSON/JSONL artifacts bind treatment, nonce, parent/child PID, run
identity, config/runtime identity, and a canonical hash chain. Reject duplicate
keys, nonfinite values, invalid UTF-8, missing newline, truncation, extra records,
stale identities, discontinuous indices/time, summary contradictions, or data
after terminal.

The child writes a provisional report and trace before cleanup. Cleanup order:
release optional supporting video, fsync trace/report, close controller/collector,
prove no world-counter advance, then close SimulationApp. Signal, timeout,
escaped descendant, nonzero exit, cleanup exception, or provisional PASS followed
by abnormal exit becomes `PROBE_RUNTIME_ERROR`.

The parent independently recomputes all runtime, A/B, geometry, contact lifecycle,
transition, lift/retention, ablation, prohibited mechanism, and artifact decisions.
Only the Isaac-free parent creates the final create-only `report.json`.

The MP4 is non-authoritative. If produced, it must decode and match the specified
trace frame count, but video quality cannot change the physical decision.

## TDD Order

1. Failing tests for config projection, frozen bytes, treatment-local outputs,
   runtime/scene/owner identity, default robot resolution, and decision precedence.
2. Failing tests for Isaac-free parent, exact child commands, sequential process
   quiescence, timeout/signal cleanup, and create-only artifacts.
3. Failing strict parser, identity, hash-chain, partial/stale/extra/abnormal-exit,
   and parent-recalculation tests.
4. Failing action-ledger tests for `None`, close/lift ordering, canonical hashes,
   exactly-once apply receipts, integrating transitions, resets, no pour, both
   valid ablation terminals, invalid/early failure, and fixed negative
   continuation.
5. Failing report API inventory/edit-target/stage-delta/lifecycle/bootstrap and
   all-header/all-point/all-friction-anchor aggregation, actor orientation, and
   control-instrumented production/continuation perturbation tests.
6. Failing sealed-geometry tests for every formula/margin and bilateral side-wall
   all-point qualification/matching, including multi-collider side-center and
   owning-collider inner-half rules, multiple manifolds, ambiguous target/support
   point and support-anchor bijections, support anchor-vector parity, rim,
   underside, edge, wedging, unknown, support, palm, environment, and
   zero-data/nonzero-data LOST cases.
7. Failing transition-index/rise/retention tests at every exact threshold boundary.
8. Failing target-pair-set, finger-only binding, source/support immutability,
   material-resolution, combine-priority, eligible-pair matrix, full-tuple
   equality, non-target-contact, exact-zero, pre-lift pose/velocity/load parity,
   support-manifold/cache parity, and causal-ablation tests. Include multiple
   collider/material, inherited/collection binding, source-binding,
   unsupported-runtime/cache authority, and changed non-target-pair rejection
   cases.
9. Failing root/body writer, force, constraint, attachment, reverse-filter,
   collision-group, raw-property, and incomplete-coverage tests.
10. Implement pure parent schemas/evaluators/process handling until CPU tests pass.
11. Implement the smallest delayed-import Isaac child without production edits.
12. Run focused and adjacent contact/controller tests, `py_compile`, and
    `git diff --check`.
13. Obtain architecture, completeness, and physical-risk implementation GO.
14. Run one fresh three-treatment diagnostic under the GPU lock and independently
    review the supporting video.

## Stop Conditions

- Stop before interaction on runtime, scene, owner, dependency, dt, gravity,
  source, robot, report-delta, ablation-delta, audit-coverage, constraint, filter,
  force, or collision mismatch.
- Never auto-retry or tune pose, target, friction, mass, material, collider,
  solver, timestep, gravity, or thresholds after failure.
- Never broaden the ablation to the source or support, or substitute an unreviewed
  pair-scoped mechanism, when finger-only binding cannot isolate the target pairs.
- Missing authority is NO-GO, not a physical failure or PASS.
- Do not proceed to filled close/lift until this causal empty positive control
  passes or a new reviewed plan changes the claim.

## Execution Result (2026-07-18)

The pinned Isaac Sim 4.1 capability gate completed at
`outputs/original_empty_beaker_contact_lift_probe_20260718_authority_no_go_001/report.json`
with `PROBE_PROTOCOL_NO_GO`.

All three sequential children completed cleanly with the same blocker before
orientation calibration, source-scene reference, target interaction, or any
trajectory step:

- `live_solver_pair_materials`
- `contact_cache_and_warm_start`
- `collision_eligible_pair_matrix`

The installed public `IPhysxSimulation` interface exposes neither candidate
method for any required authority. Each child trace contains only bootstrap,
protocol-blocker, and terminal records; the control cleanup receipt records a
world counter of zero before and after cleanup. This is a protocol limitation,
not evidence that friction does or does not lift the empty beaker.

Do not weaken the authority requirements or proceed to filled-beaker close/lift.
A new independently reviewed protocol must provide a native read-only authority
for complete collision eligibility, effective pair material tuples, and
separable solver-cache state before this experiment can continue.

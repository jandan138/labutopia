# InternData Pour Visual-Parity Plan (Implemented)

## Goal

Reproduce the visible liquid behavior of the public InternData Baijiu-pour
example in the real LabUtopia `level1_pour` tabletop scene with:

1. the complete public fluid recipe;
2. one explicit open inner-wall collider treatment derived from the calibrated
   LabUtopia beaker geometry; and
3. separate physical and visual verdicts.

The implementation has two sequential probes: a static source hold and, only
after that passes, one deterministic two-beaker kinematic pour. Robot/expert
replay is outside this plan because the current accepted authority does not
claim an exact expert episode and the live `PourController` samples random
heights.

This is not a width sweep, collider matrix, material matrix, or automatic
recovery loop. No fallback candidate is added inside either probe.

## Terminology And Product Answer

The following values have different jobs and must not be called one generic
"particle size":

- `particleContactOffset` controls the PhysX particle interaction/contact scale.
- particle spacing controls the initial distance between particle centers.
- `UsdGeom.Points.widths` controls the displayed point diameter when points are
  rendered directly.
- the PhysX isosurface reconstructs a continuous surface from the simulated
  particle field.
- the vessel collider determines where particles can physically contact the
  cup wall and bottom.

Changing only `Points.widths` does not change particle collision. It does change
the final image in point/sphere mode: a width much larger than center spacing
causes heavy overlap and an opaque foam/gel appearance, while a much smaller
width appears sparse or grainy. In isosurface mode, point width is primarily a
proxy/debug property; physical offsets and isosurface reconstruction control
the visible liquid surface.

The accepted LabUtopia static-hold runner labels its nominal physics particle
width `0.00045` m, authors particle contact offset `0.000529254` m, and uses
display point width `0.0043` m. The display-to-nominal-width ratio is about
`9.56`. That separation is valid for its accepted physics/debug claim, but it
is not the public InternData rendering recipe.

The public InternData recipe instead sets all three numeric values below to
3 mm and renders a native isosurface:

- `particleContactOffset = 0.003` m;
- particle spacing `= 0.003` m;
- `Points.widths = 0.003` m.

The working hypothesis is therefore: match the continuous-liquid look through
the public 3 mm fluid recipe and a usable hollow vessel collider, not by
enlarging display spheres independently. Native isosurface remains part of the
runtime experiment, while the portable delivery snapshot renders the physical
particle prim directly so that simulation and display cannot diverge.

## Evidence Boundary

### Confirmed From Public InternData Sources

- Repository: `InternRobotics/InternDataEngine`, commit
  `2a0a21f2c836df97c925729084e13d68950b4deb`.
- Downloaded source archive SHA-256:
  `a7ad013afc3741b32b556ab2391b715f27bc2ab5a815ddb85b520b98ebc7bd2b`.
- The documented recommended runtime is Isaac Sim 4.1.0; support for 4.2 and
  4.5 is also documented. A newer Isaac version is not required to explain the
  public look.
- `pour_Baijiu_left.yaml` uses a complete `12 x 12 x 25` particle grid (3,600
  particles), 3 mm contact offset/spacing, maximum velocity `0.8` m/s, and a
  white visual material with opacity `0.05`.
- `banana.py::_set_fluid` sets point width equal to spacing, enables CCD, 16
  position iterations, max neighborhood `96`, neighborhood scale `1.01`,
  global self-collision, native PhysX isosurface, and smoothing strength `50`.
- Its authored PBD values are cohesion `0.01`, friction `0.1`, surface tension
  `0.0074`, viscosity `0.0000017`, and zero drag/lift/damping/vorticity.
- Its `UsdPreviewSurface` is white, non-metallic, roughness `0.4`, and opacity
  `0.05`.
- Its reset sequence includes one setup step, 20 pre-fluid warmup steps, fluid
  creation, and 150 post-fluid physics steps. The public world configuration
  uses physics and rendering dt `1/30` s.
- Its generic asset preprocessing applies `convexDecomposition` with 64 hulls,
  64 vertices per hull, minimum thickness `0.001`, shrink-wrap enabled, error
  percentage `0.1`, and static/dynamic friction `1.0/1.0`.
- Its public pour success checker counts particles only by XY radius around the
  target. It does not check particle Z, source leakage, tabletop spill, or
  below-table loss.

The public fluid code binds a PBD material and then a visual material through
the same default material-binding API. The effective final binding can depend
on USD/PhysX binding semantics. This plan reproduces the public call sequence
and records the effective live-stage binding; it does not silently introduce a
second "corrected" material-binding variant.

### Confirmed From The Public Video

- Downloaded video SHA-256:
  `869837e254ec94477c98b62d58656741abf6013ad91dd3bf71e8f5bc126bee44`.
- The visible stream is continuous and highly transparent; individual large
  particle balls are not visible.
- The source bottle and target glass visibly have openings, wall thickness,
  and interior volume.

### Inference, Not Fact

- The visible continuous stream is strongly consistent with the public native
  isosurface code, but pixels alone do not prove which render prim produced it.
- The exact Wuliangye and liquor-glass assets are gated. Their collision prims
  cannot be inspected, so the video does not prove that the generic public
  convex-decomposition script was used on those assets.
- Applying that exact generic collider recipe to the LabUtopia beakers was the
  initial fixed hypothesis, not a known parity collider. Runtime qualification
  rejected it for this asset. The executed treatment is the separately
  reviewed open inner-wall proxy described below.

## Pinned LabUtopia Inputs

- Scene:
  `outputs/usd_asset_packages/lab_001_level1_pour_support_aligned_v1_20260712/lab_001_level1_pour_support_aligned_v1.usda`.
- Scene SHA-256:
  `3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b`.
- Source vessel: `/World/beaker2` and `/World/beaker2/mesh`.
- Target vessel: `/World/beaker1` and `/World/beaker1/mesh`.
- Existing accepted physics authority remains read-only:
  `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712/accepted_authority_P4096_S2`.
- Runtime: the repository's Isaac Sim 4.1 Python environment.
- Existing `tools/labutopia_fluid/real_beaker.py` is the authority for the cup
  canonical frame and 3D interior classification; the new runner reuses it.

At runtime, read back and record stage units, up axis, gravity, physics dt, and
rendering dt. Required values are meters-per-unit `1`, Z-up, and dt `1/30` s.

The pinned source-beaker calibration reports interior radius approximately
`0.032007` m and interior height approximately `0.090400` m. The complete public
`12 x 12 x 25` grid fits: center spans are `33 x 33 x 72` mm and the 3 mm point
width produces a `36 x 36 x 75` mm render envelope. Separately, a conservative
3 mm center-to-collider contact clearance produces a `39 x 39 x 78` mm contact
envelope, which also fits. The preflight must read the autocomputed contact/rest
offsets and prove positive radial, floor, and rim margins against the live
collider rather than trusting these rounded numbers.

## Planned Files

- Add `tools/labutopia_fluid/run_interndata_pour_parity_probe.py`.
  It owns the fixed recipe contract, run-scoped collider overlay, live-stage
  readback, particle/isosurface authoring, deterministic kinematic trace,
  accounting, captures, and manifests.
- Add `tests/test_interndata_pour_parity_probe.py`.
  It owns recipe, fit, overlay, material binding, classifier, trajectory, and
  artifact-contract tests.
- Do not modify `tools/labutopia_fluid/real_beaker.py`, the accepted frozen
  runner, the source scene, or the source beaker assets.

Generated evidence directories:

- Static hold:
  `docs/labutopia_lab_poc/evidence_manifests/interndata_source_hold_probe_final_20260714/`.
- Deterministic pour, only after static eligibility:
  `docs/labutopia_lab_poc/evidence_manifests/interndata_kinematic_pour_probe_final_inset_20260714/`.

## Fixed Treatment

### Fluid Contract

- Complete centered `12 x 12 x 25` grid: 3,600 particles.
- Generate points in the calibrated beaker canonical frame, then transform once
  into world space. Do not construct the grid from a world AABB.
- 3 mm contact offset, spacing, and point width; no independent display width.
- CCD on, 16 position iterations, max neighborhood `96`, neighborhood scale
  `1.01`, max velocity `0.8`, global self-collision on, and GPU simulation.
- Public authored PBD values and public PreviewSurface values listed above.
- Native PhysX isosurface using the public default call and particle smoothing
  strength `50`; point prim purpose `proxy`.
- Public material-binding call order reproduced exactly. Record both authored
  materials and the effective final live-stage binding. Do not claim an
  authored PBD value is effective unless runtime readback supports that claim.
- Sequence:
  `reset -> post-reset/setup -> 1 setup step -> 20 pre-fluid steps -> author
  fluid/state 0 -> 150 post-fluid steps`.
- Replicator/camera updates may sample the same physics state but must not add a
  physics step. Record physics-step index with every particle sample and image.

### Collider Contract

- Disable the native visual-mesh collision route for each participating beaker.
- Author one open compound proxy per beaker from the accepted canonical frame:
  GPU-native box panels around the wall plus an overlapping box bottom. The top
  remains open and the render mesh/material remain unchanged.
- Use the qualified contract in `build_inner_wall_contract`: 72 angular
  panels, two vertical rings, 26 mm authored wall-box thickness, 12 mm bottom
  thickness, 18 mm bottom overlap, 4 mm contact offset, and zero rest offset.
  Each beaker therefore has 145 enabled proxy shapes: 144 wall boxes and one
  bottom box. The collision-panel inner radius is shifted inward by one rendered
  particle radius, 1.5 mm, while the visible beaker geometry remains unchanged.
- Bind a physics material with static and dynamic friction both `1.0`.
- For the moving source, make `/World/beaker2` the sole parent compound
  kinematic actor so the visual vessel and all proxy children share one pose
  authority. The target proxy remains static.
- Before simulation, assert that the enabled collision paths are exactly the
  authored proxy paths, with no competing native mesh collider.

This proxy is a deliberate LabUtopia vessel treatment. It is not claimed to be
the unknown collider used by the gated InternData bottle and glass assets.

## TDD Order

1. **Recipe red tests, then implementation.** Assert all public values, source
   paths/commit/hash, 3,600 particles, distinct parameter meanings, and evidence
   labels `public_fluid_recipe` and `explicit_open_inner_wall_proxy`.
2. **Geometry red tests, then implementation.** Assert canonical-frame
   generation, 12 x 12 x 25 dimensions, finite points, and positive particle
   envelope margins against the live cup interior. Fit failure stops before
   Isaac launch; grid dimensions are not automatically changed.
3. **Collider red tests, then implementation.** On a temporary composed stage,
   assert the fixed panel/bottom proxy dimensions, friction `1.0/1.0`, exact
   enabled proxy paths, one parent compound actor for the moving source,
   inherited vessel transform, and unchanged source hash.
4. **Fluid/material red tests, then implementation.** Assert particle system,
   PBD fields, isosurface, smoothing, proxy purpose, PreviewSurface, public
   material-binding order, and effective-binding evidence fields.
5. **Accounting red tests, then implementation.** Use synthetic point sets to
   test canonical source/target interiors, epsilon boundaries, nonfinite input,
   tabletop spill, below-table loss, transit, and mutually exclusive totals.
   Keep the public XY-only result as `legacy_reference_metric`, never as a gate.
6. **Runtime/artifact red tests, then implementation.** Assert exact step
   sequence, same-tick sampling, render-no-step behavior, immutable input hashes,
   trace completeness, valid images/video, scoped logs, and terminal verdicts.
7. Run the focused unit tests. Only after they pass, run the one static Isaac
   probe.
8. If and only if static eligibility passes, add trajectory red tests and the
   deterministic-pour mode. Run its focused tests, then run one Isaac pour.

## Phase 1: Static Source Hold

Required artifacts are the overlay USD, runtime manifest, every-step particle
trace, scoped Isaac log, close-up PNG, tabletop-context PNG, and a short
checkpoint MP4. Every image/frame carries its corresponding physics-step index.

Technical validity requires:

- exact live-stage fluid, material, collider, units, gravity, and dt readbacks;
- valid cooked-cavity qualification;
- 3,600 finite particles at every post-fluid step;
- enabled isosurface and nonblank captures;
- no render update that advances physics;
- unchanged source scene and accepted-authority hashes.

Verdicts are independent:

- `STATIC_PHYSICS_PASS`: every one of the 150 post-fluid states has all 3,600
  particles inside the measured 3D source interior, with zero outside-radial,
  above-rim, tabletop-spill, and below-table counts.
- `STATIC_VISUAL_PASS`: the checkpoint MP4 and final close-up/context frames show
  a coherent transparent liquid body, no visible large spheres, no opaque gel
  block, no obvious wall intersection, and no external pool.
- `STATIC_ELIGIBLE_FOR_KINEMATIC`: both verdicts pass.

Visual review compares the LabUtopia outputs with fixed frames from the pinned
public video as a qualitative appearance reference. It is called visual
similarity/acceptability, not pixel parity, because vessel, camera, and lighting
are different.

## Phase 2: One Deterministic Kinematic Pour

This phase is gated by `STATIC_ELIGIBLE_FOR_KINEMATIC` and uses the identical
fluid and collider contracts. It does not invoke the random robot controller.

The source trajectory is one immutable, hashed beaker2 transform trace at 30 Hz:

1. 120 steps moving the source rim above the target center;
2. 120 steps rotating smoothly from upright to 100 degrees about the canonical
   pour axis while keeping the rim pivot near the target center;
3. 120 steps holding the 100-degree pose;
4. 120 steps returning upright;
5. 60 steps returning to the initial pose; and
6. 150 stationary settling steps.

The resulting trace contains 690 physics steps and 691 sampled states including
state zero.

No speed/angle candidate is added if this fixed trace fails.

At every physics tick, sample particles and the moving source frame from the
same state. Assignment priority is:

1. nonfinite -> invalid run;
2. inside moving source interior;
3. inside target interior;
4. below table;
5. tabletop spill;
6. transit.

Use one documented metric epsilon and require the mutually exclusive finite
counts to sum to 3,600 every tick. Transit is allowed during the pour but must
be zero after settling.

Physical pass requires zero nonfinite, below-table, and tabletop-spill counts at
all ticks; zero final transit; source plus target final count of 3,600; and at
least 150 particles in the target, matching the public example's minimum only
as a transfer floor. The public XY-only metric is still reported separately.

Visual pass requires a continuous transparent stream across consecutive video
frames, visible accumulation in beaker1, no large-sphere appearance, no obvious
wall crossing, no external pool, and both vessels visible at trajectory extrema.

Terminal results are:

- `KINEMATIC_POUR_PASS` when physical and visual gates both pass;
- `KINEMATIC_POUR_FAIL` when runtime is valid but either gate fails; or
- `INVALID_KINEMATIC_POUR` for setup, collider, runtime, accounting, or capture
  invalidity.

Passing this phase proves one deterministic two-beaker pour treatment. It does
not prove robot control, expert replay, policy score, or benchmark readiness.

## Reviewed Execution Amendment

The first runtime qualification invalidated the native visual-mesh
convex-decomposition hypothesis for these thin open beakers. In accordance with
the reviewed stop rule, the executed probe uses the explicit open inner-wall
proxy above. This was a collider-model correction, not a parameter sweep or a
fallback matrix.

The initially reviewed 60-step approach produced three tabletop-classified
particles. Keeping all geometry, angle, fluid, collider, and remaining phase
durations fixed, the approach duration was changed once to 120 steps. This is
the final immutable trace; there is no speed candidate matrix.

During the pour, `transit` means particles in the expected airborne stream
between the two beakers. It is allowed at intermediate states. The physical gate
requires zero tabletop, below-table, and nonfinite particles at every state and
zero transit in the final settled state.

The evidence MP4 files are decimated offline visualizations reconstructed from
strict PhysX position readbacks. They prove the recorded trajectory is visually
coherent, but they do not prove live render synchronization. Portable delivery
USDs therefore remove the separate `/VisualParticles` replay proxy, disable the
competing isosurface presentation, and make the physical particle prim the sole
render/material authority.

The two delivery roots are snapshots: one initial state and one final settled
state. They contain no time-sampled prescribed pour animation. Pressing Play may
advance the particles, but an external controller must drive `/World/beaker2`
to reproduce the prescribed pour.

For portable delivery, both particle prims are normalized to
`UsdGeom.Points`, retain the 3 mm physical/rendered width, and bind the local
particle material directly. Both snapshots synchronize `points` and
`physxParticle:simulationPoints`. The initial entrypoint uses the 150-step
stable source-hold state so a direct open shows liquid at the beaker bottom,
not the unsettled initialization grid.

## Final Qualification

- Static source hold: `STATIC_ELIGIBLE_FOR_KINEMATIC`.
- Fixed 690-step pour: `KINEMATIC_POUR_PASS`; all 3,600 particles finish in
  `/World/beaker1`, with zero final source, transit, tabletop, below-table, or
  nonfinite particles.
- Isolated dependency closure: both roots open with `LoadAll`, with zero
  unresolved or outside-package dependencies and no dangling material binding.
- Isaac Sim 4.1.0 live check: after 30 natural-settle logical steps, all 3,600
  particles remain inside the source beaker; the delivered result sphere
  envelope is wholly inside the target beaker.
- Independent clean-room review of the six final Isaac renders: `PASS` with
  high confidence and no retake required. The reviewer notes only non-blocking
  granular/layered point texture.

## Stop Rules And Next Decision

- Do not add a particle width, opacity, isosurface, speed, angle, or collider
  candidate inside this plan.
- Collider qualification failure rejects only the tested collider treatment.
- A valid static hold failure rejects the combined fixed treatment; do not blame
  collider alone without direct cooking/cavity evidence.
- A physics pass plus visual failure isolates the remaining problem to the
  isosurface/material/capture treatment, not vessel containment.
- A static failure stops before kinematic pour. No automatic collider fallback
  is selected inside a run.
- A kinematic pass is the prerequisite for a later plan that freezes an actual
  expert action/transform trace and integrates the robot. Do not call the current
  support-aligned scene an exact expert episode.

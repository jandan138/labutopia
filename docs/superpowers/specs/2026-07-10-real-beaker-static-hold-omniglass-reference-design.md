# Real Beaker Static Hold and OmniGlass Reference Alignment Design

**Date:** 2026-07-10

**Status:** Approved; implementation authorized on 2026-07-11

**Scope:** LabUtopia `lab_001` source beaker (`/World/beaker2`) static hold plus reference-style OmniGlass particle presentation

## Objective

Produce a derived LabUtopia USD in which:

1. PhysX PBD particles are physically contained inside the visible source beaker, not merely inside a broad tabletop classification cylinder.
2. The static hold result survives the required particle-count, seed, and duration matrix.
3. A render-only OmniGlass particle layer reproduces the relative bead scale and material character of `inputs/usd/scene/liquid/physics_fidelity_A18_FloatBall.usd` without changing the accepted physics trajectory.
4. The final USD package, particle readback, videos, and review artifacts support the same conclusion.

## Current-State Finding

The existing `FULL_SCENE_CONTROLLED_P1024` and `P4096` manifests are classifier false positives for visible-beaker containment.

- `/World/beaker2` maps parent local Y to world Z, while the existing wrapper authors its bottom and wall height along parent local Z.
- The exported `FluidSafeWrapper/Bottom` is therefore a vertical slab in world space rather than a horizontal beaker bottom.
- The legacy source-region classifier starts at the lab table top (`z ~= 0.772761`) instead of the visible beaker floor (`z ~= 0.826656`).
- At step 120, 974/1024 and 3926/4096 particle centers are below the visible beaker mesh minimum Z while still classified as source-held.
- Existing unit fixtures exercise parent translation but not the real parent rotation or a visible-interior containment gate.

These manifests remain useful as regression evidence but must not be promoted as a successful static beaker hold.

## Measured Geometry and Reference Metrics

### LabUtopia source beaker

Measured from `lab_001_level1_pour_tabletop_with_liquid.usd`:

- Parent-local mesh bounds: X `[-0.016815, 0.064340]`, Y `[-0.043344, 0.047056]`, Z `[-0.037666, 0.037666]` meters.
- Parent-local mesh size: approximately `81.2 x 90.4 x 75.3 mm`.
- Cup axis: parent local Y; at the authored tabletop pose this maps to world Z.
- Visible mesh floor in world space: approximately `z = 0.826656`.
- Original 50k authored liquid AABB: approximately `60 x 60 x 60 mm`.
- Original liquid radial maximum around the intended source center: approximately `32.0 mm`.

The original authored liquid is not accepted as working PBD fluid, but its initial bounds are useful calibration evidence for the intended visible interior volume.

### A18 reference

Measured from `inputs/usd/scene/liquid/physics_fidelity_A18_FloatBall.usd`:

- Container interior span: approximately `0.30 m`.
- Point width: `0.02 m`.
- Particle nearest-neighbor median: approximately `0.018516 m`.
- Width / nearest-neighbor ratio: approximately `1.08`.
- Approximately 15 displayed beads span the container width.
- Material: `OmniGlass.mdl`, with the reference `glass_color` and `reflection_color` retained as the first visual candidate.

The design copies these dimensionless visual ratios, not the absolute `0.02 m` width.

## Architecture

### 1. Canonical cup frame

Author a canonical Z-up wrapper frame beneath `/World/beaker2`.

- The canonical frame origin is the center of the visible beaker floor.
- Canonical +Z is the beaker axis.
- Canonical X/Y span the radial plane.
- The child transform compensates for the beaker asset's parent-local axis convention, so canonical +Z maps to parent local Y for this asset.
- Wrapper colliders are authored in canonical coordinates and inherit `/World/beaker2` motion through the corrective child transform.

The frame must be derived from the composed stage transform and parent-relative mesh bounds. It must not assume that parent local Z is the beaker axis and must not reconstruct local geometry by inverse-transforming a world-aligned AABB.

The authored wrapper summary records:

- canonical-to-world matrix;
- parent-local cup-axis token;
- world cup-axis vector;
- visible floor and rim world positions;
- radial interior calibration source;
- wrapper bottom normal and alignment dot product.

Static acceptance requires the wrapper bottom normal to align with the beaker axis with `dot >= 0.999` and its support plane to lie within `1 mm` of the configured visible floor support level.

### 2. Interior calibration

Build one `CupInteriorFrame` contract shared by spawning, collision authoring, classification, and evidence reporting.

Calibration order:

1. Use the original authored liquid bounds when available to estimate the intended interior center and radial fill envelope.
2. Clamp the estimate inside the parent-relative visual mesh radial bounds.
3. Apply explicit contact and wall clearances.
4. Fall back to conservative parent-relative mesh bounds only when the original liquid calibration prim is unavailable.

For `lab_001`, the expected calibrated fluid radius is near `0.032 m`; the implementation must record the actual derived value rather than silently pinning this number.

### 3. Strict visible-beaker classifier

Every readback position is transformed from world space into the canonical cup frame.

The classifier records at least:

- `inside_visible_interior_count`;
- `below_visible_floor_count`;
- `outside_visible_radial_count`;
- `above_visible_rim_count`;
- `legacy_source_region_count` for comparison only;
- minimum/median/maximum canonical axial coordinate;
- maximum canonical radial coordinate.

`PASS_VISIBLE_BEAKER_STATIC_HOLD` requires:

- all particles finite;
- final particle fraction at least `0.95`;
- `below_visible_floor_count == 0` at every recorded step;
- `outside_visible_radial_count == 0` at every recorded step;
- `above_visible_rim_count == 0` at every recorded step;
- final `inside_visible_interior_count == final_particle_count`;
- no CPU collision fallback, unsupported GPU collider warning, fatal PhysX error, or particle explosion;
- tail leak rate equal to zero under the strict classifier.

The legacy table/source cylinder cannot grant a pass. It remains diagnostic-only so old and new evidence can be compared.

### 4. Controlled spawn

Spawn positions are generated in canonical cup coordinates and transformed to world space.

- The lowest particle center must clear the physical support plane by the configured particle/collider contact clearance.
- The maximum radial spawn coordinate must remain inside the calibrated visible interior after applying contact clearance.
- Initial positions must pass the strict visible-beaker classifier before Isaac runtime starts.
- Initial radial velocity remains zero for the static-hold gate.

Physics resolution remains explicit through particle contact/rest offsets. `UsdGeom.Points.widths` is no longer used as the source of truth for physics offsets.

### 5. Physics/display separation

Introduce distinct concepts:

- `physics_particle_offsets`: PhysX contact, rest, solid-rest, and fluid-rest values.
- `display_particle_width`: render diameter for a `UsdGeom.Points` or render-only proxy set.

Changing `display_particle_width` must not change:

- particle-system offsets;
- particle mass or PBD material;
- spawn positions or velocities;
- collider geometry;
- readback trajectory hashes.

The manifest records both values and explicitly states that display width is presentation-only.

### 6. OmniGlass reference presentation

The physical `ParticleSet` remains the physics authority and can be hidden for presentation.

Create a render-only `PresentationParticleSet` from each captured physical readback frame:

- deterministic canonical-space voxel clustering prevents thousands of enlarged spheres from occupying nearly identical positions;
- one visual point is emitted per occupied voxel at the particle centroid;
- no physics schema or simulation-owner relationship is applied to the visual set;
- the visual set binds an OmniGlass material initialized from the A18 reference values;
- the physical readback trace is stored independently and is never reconstructed from presentation points.

Reference candidates are derived from the calibrated interior diameter and A18 ratios:

| Candidate | Target display width | Purpose |
| --- | ---: | --- |
| `OMNI_REF_FINE` | `1.5-2.0 mm` | all-particle/fine fallback with limited overlap |
| `OMNI_REF_RATIO_15` | about interior diameter / 15 (`~4.3 mm` for the current calibration) | closest dimensionless A18 match |
| `OMNI_REF_RATIO_12` | about interior diameter / 12 (`~5.3 mm`) | slightly larger, more legible bead candidate |

The exact authored widths are computed from the measured interior diameter and recorded in the visual manifest. Proxy count is an output of deterministic clustering, not a hard-coded success condition. A practical review range is expected to be hundreds to low thousands of visible beads.

### 7. Cameras and visual review

Produce two synchronized views from the accepted trajectory:

- source-beaker closeup: visibly proves beads are above the real floor and inside the glass wall;
- tabletop context: shows the real lab scene, both beakers, and source placement.

Run a blind-label visual comparison across the three candidates. Review criteria:

- liquid is visibly inside `beaker2`;
- bead scale resembles A18 without foam-like overdraw;
- no black/metallic fallback, severe refraction noise, or detached particle cloud;
- beaker wall, rim, and liquid remain distinguishable;
- closeup and context views are useful and correctly framed.

The selected candidate must receive `PASS` or an explicitly accepted `WARN` from the render visual review. A physics pass cannot substitute for this review.

## Validation Matrix

### Offline geometry and contract tests

Required tests cover:

- the real 90-degree beaker parent rotation;
- canonical wrapper Z mapping to the actual cup axis;
- wrapper bottom normal/plane alignment;
- parent-relative mesh bounds without world-AABB inflation;
- canonical spawn positions all inside the visible interior;
- deliberate below-floor and outside-radius positions fail the strict classifier;
- display width changes do not alter physics offsets;
- deterministic visual proxy generation and stable manifest fields.

### Isaac static hold

Run the full colleague scene with D4-style GPU-native wrapper colliders:

| Particle count | Seeds | Simulated duration | Required result |
| ---: | --- | ---: | --- |
| 1024 | 0, 1, 2 | 10 seconds each | `PASS_VISIBLE_BEAKER_STATIC_HOLD` for all seeds |
| 4096 | 0, 1, 2 | 10 seconds each | `PASS_VISIBLE_BEAKER_STATIC_HOLD` for all seeds |

At 60 Hz, each cell runs 600 physics steps. Trace cadence must be sufficient to prove that no intermediate recorded step violates the strict gate.

If 1024 fails, stop before 4096 and investigate the first strict-gate violation. Width, collider, and spawn changes are tested one variable at a time.

### Visual parity

Use one accepted 4096 trajectory when available; otherwise use the accepted 1024 trajectory and record that limitation. Render all three OmniGlass candidates from the same readback trajectory so physics is identical across the visual comparison.

## Deliverables

1. Derived standalone USD package with real lab scene, corrected hidden wrapper, accepted physics particle setup, selected OmniGlass presentation, and no unresolved external asset paths.
2. Top-level static-hold manifest summarizing all six seed/count cells and strict visible-beaker metrics.
3. Per-cell readback traces, Isaac logs, and source-beaker closeup/context videos.
4. A18 reference metrics plus candidate visual matrix and visual-review verdict.
5. Updated project evidence documentation that marks the old full-scene PASS manifests as false-positive regression evidence.

## Claim Boundary

Allowed only after all required gates pass:

- `real_beaker_static_hold_closed=true`;
- `visible_beaker_containment_verified=true`;
- `omniglass_reference_particle_look_selected=true`;
- `physics_and_display_parameters_separated=true`.

Blocked by this scope:

- kinematic tilt or pour success;
- transfer into `beaker1`;
- benchmark or policy readiness;
- photoreal or true-water claims;
- claiming the visual proxy points are physical particles;
- using the legacy source cylinder as visible-beaker containment proof.

## Implementation Boundaries

- Preserve the localized source package and original colleague USD as immutable inputs.
- Work with the current dirty worktree and do not revert unrelated or prior-engineer changes.
- Add focused helpers rather than expanding the already-large runtime runner with unrelated geometry logic.
- Follow TDD for every behavior change and preserve red/green evidence.
- Do not promote or rewrite evidence manifests until fresh Isaac runs produce authoritative replacements.

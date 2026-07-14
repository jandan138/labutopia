# Real Beaker Static-Hold Stabilization Plan

## Objective

Close the real-beaker static liquid hold in Isaac Sim 4.1, preserve an auditable
accepted physical trace, replay that trace with the reference-aligned OmniGlass
particle look, and export a standalone USD directory package that opens cleanly.

## Current Evidence

- The 60 Hz baseline is physically under-resolved: a single integration step
  moves a resting particle about 1.93 spawn spacings under gravity.
- A one-particle 60 Hz control does not tunnel through the wrapper, but rebounds
  about 9.68 mm after floor contact.
- The 1024-particle 60 Hz baseline reaches 240 particles below the visible floor,
  44 above the rim, two outside the radial boundary, about 123 mm vertical
  extent, and about 2.42 m/s peak finite-difference speed.
- The timestep-only 600 Hz diagnostic at
  `/tmp/lab001_real_beaker_600hz_1024x30_20260711T080941Z` executes 30 logical
  steps, 300 integration steps, and 0.5 simulated seconds exactly. It has zero
  rim and radial escapes, about 7.10 mm maximum vertical extent, and about
  0.323 mm maximum integration-step cloud displacement. Its remaining raw floor
  residual is at most 2.62 micrometers.
- The localized tabletop entry USDs do not author stage units and resolve to the
  OpenUSD fallback `metersPerUnit=0.01`, while the source `lab_001.usd` and all
  numerical geometry/physics values use meters. The final product must author
  and verify `metersPerUnit=1.0` and `kilogramsPerUnit=1.0`.

## Acceptance Invariants

- Product cadence stays 60 logical steps per second; PhysX integration runs at
  600 steps per second using ten explicit `simulate(1/600)` / `fetch_results()`
  pairs per logical step.
- A ten-second cell means 600 logical steps, 6,000 integration calls, and exactly
  10 simulated seconds. Render updates must not advance physics.
- Particle count remains exact, positions remain finite, and no particle crosses
  the visible rim or radial wall.
- Raw floor-plane residuals remain reported. A numerical contact band may only
  be introduced as a separate measured field; it must not erase raw counts or
  convert the old millimeter-scale leak artifacts into passes.
- Physics particle size, display width, and OmniGlass proxy size remain separate.
- A short diagnostic pass cannot close the product claim. Closure requires all
  six 1024/4096 x seed 0/1/2 ten-second cells.
- OmniGlass rendering is replay-only and must not mutate or re-step the accepted
  physical trajectory.
- Final delivery is a localized directory package that opens from a clean copy
  without original absolute paths, unresolved assets, or unresolved MDL files.

## Implementation Order

### 1. Finish the Two-Level Step Contract

**Files**

- `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- `tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py`
- `tests/test_real_beaker_strict_step_schedule.py`
- `tests/test_real_beaker_runtime_contract.py`
- `tests/test_real_beaker_matrix_isaac_runtime.py`

**Changes**

1. Keep `--steps` as logical steps and replace ambiguous `--physics-dt` with
   `--logical-dt`, `--integration-dt`, and
   `--substeps-per-logical-step`.
2. Require `1/60`, `1/600`, and `10` in the canonical matrix.
3. Record exact logical and integration counts, both frequencies, both time
   increments, total simulated seconds, attach/detach state, and render
   invariance.
4. Keep optional integration-substep JSONL readback for short diagnostics.
5. Make matrix acceptance fail closed unless all scheduling fields match exactly.
6. Represent the canonical schedule by integer frequencies and substep count;
   fail closed unless `logical_hz=60`, `integration_hz=600`, `substeps=10`,
   `integration_hz=logical_hz*substeps`, and each reported `dt` is the exact
   reciprocal of its frequency.
7. Treat the outer loop as the only logical-step boundary. Every iteration must
   contain exactly ten ordered `simulate`/`fetch_results` pairs; no render,
   callback, diagnostic, or cleanup path may perform an extra physics call.
8. Hash an ordered lifecycle event stream covering stage open, attach, every
   simulate/fetch pair, render-invariance checks, detach, evidence flush, and
   close. Record the last completed logical/integration step on failure.
9. Version the trace schema and bind run/cell ID, source/config hashes, seed,
   particle count, units, initial spawn hash, frame fields, final trace bytes,
   and lifecycle-event hash. Reject unknown, incomplete, stale, or mismatched
   schemas in matrix and replay consumers.

**Verification**

- Run the focused strict-step and matrix tests.
- Run the full pure fluid suite.
- Run the matrix dry plan and confirm six cells and zero Isaac launches.

### 2. Author and Verify the SI Stage-Unit Contract

**Files**

- `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- `tests/test_real_beaker_runtime_contract.py`

**Changes**

1. Immediately after stage composition, before authoring any physics material,
   collider, particle system, or particles, read and record the composed input
   units, then author `UsdGeom.SetStageMetersPerUnit(stage, 1.0)` and
   `UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)` on the runtime root layer.
2. Read both values back and fail strict mode before physical authoring if either
   is not exactly `1.0`.
3. Record source/effective units and the unit-authoring layer in the runtime
   summary and exported evidence USD.
4. Do not change timestep, spawn, offsets, collider, solver, or material in this
   experiment.
5. Record pre/post stage-space AABBs, beaker dimensions, visible floor/rim,
   particle spacing, collider support planes, and all material distance values;
   stop if any authored numerical geometry changes when metadata is corrected.
6. Record and assert authored/effective particle and material density as finite,
   positive SI `kg/m^3`; include density source/value in physical authoring
   identity and reject default or missing density.

**Verification**

- Add in-memory USD tests that start from unauthored/default units and assert
  exact SI readback.
- First run one particle at 600 Hz to calibrate floor-contact numerical error.
- Then rerun 1024 particles, seed 0, 30 logical steps, with all 300 integration
  substeps recorded. Compare spawn hash, coordinates, geometry measurements, and
  every non-unit physical authoring field with the timestep-only diagnostic.

### 3. Resolve Floor Contact Semantics Without Hiding Leaks

**Files**

- `tools/labutopia_fluid/real_beaker.py`
- `tests/test_real_beaker.py`
- `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`

**Decision Gate**

- If the SI-unit diagnostic has no rim/radial escape, no expansion, and only a
  bounded floor residual within an independently calibrated numerical error
  budget, classify that interval as a numerical contact band.
- Otherwise, do not relax classification; proceed to step 4.

Before evaluating the gate, require all of the following for every diagnostic
frame: vertical extent no larger than twice its initial value, median nearest
neighbor distance at least `0.9 * fluidRestOffset`, bidirectional nearest-neighbor
cloud-motion `p99` per integration step no larger than one spawn spacing, and zero hard rim/radial
violations. Require final-20% centroid speed below `0.01 m/s`, no progressively
more-negative floor excursion, and no monotonic growth of contact-band occupancy.
Record `p50/p95/p99/max`; without stable particle IDs, treat max as a diagnostic
set-distance outlier rather than a per-particle speed gate.

**Proposed Contact-Band Contract**

1. Preserve `raw_below_visible_floor_count` using the exact visible plane.
2. Derive the candidate from the SI one-particle 600 Hz control:
   `max(8 * float32_ulp_at_world_floor, 2 * max_single_particle_floor_residual)`.
   Cap it by both `0.01 * fluidRestOffset` and `1e-5 m`; require it to remain
   positive and below the visible-floor-to-first-layer clearance. Record every
   input and cap used by this error budget. Do not tune it from the 1024 result.
3. Add `floor_contact_band_count` for centers in
   `[floor - tolerance, floor)` and `hard_below_visible_floor_count` for centers
   below `floor - tolerance`.
4. Static hold may pass only when hard-floor, rim, radial, nonfinite, runtime,
   and diagnostic failures are all zero.
5. Regression tests must prove the old micrometer-to-millimeter 60 Hz artifacts
   and historical false-positive traces still fail.
6. Classification is post hoc and read-only. It must never modify positions,
   solver state, replay input, or trace identity; matrix acceptance consumes raw
   and hard counts from the same immutable trace.
7. Retain per-frame signed floor-distance extrema and contact-band occupancy;
   stop on any hard breach, persistent downward drift, or tolerance overrun.

### 4. Apply One Physical Correction Only If the SI Run Still Fails

**Files**

- `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- `tools/labutopia_fluid/real_beaker.py`
- corresponding focused tests

**First correction after the SI diagnostic exceeds the calibrated floor budget**

1. Change exactly one independently authored scalar: particle-system
   non-particle `restOffset` from `0` to the authored `solidRestOffset`.
   Assert particle rest/contact offsets, particle scale, density, solver values,
   and all stage-unit metadata are byte-identical before and after.
2. Keep all initial spawn positions and velocities byte-identical to the SI+600 Hz
   baseline. The treatment is exactly `restOffset: 0 -> 0.000594 m`.
3. Run one-particle and 1024-particle 0.5-second controls. Require the 1024 hard
   floor residual to fall within the independently calibrated `0.477 micrometer`
   budget while rim/radial escape and expansion remain zero.

**Only if non-particle rest separation does not improve the settled residual**

1. Return to the SI+600 Hz baseline and test only the lowest spawn-layer
   clearance as a separate fork; do not combine it with the rest-offset change.
2. If necessary, separately replace hash-distributed sparse occupancy with
   complete bottom-up disk layers and only a partial top layer.

Do not change particle scale, count, solver iterations, viscosity, cohesion, or
surface tension in the same run.

### 5. Run the Canonical Static-Hold Matrix

1. Run 1024 particles for seeds 0, 1, and 2 for 600 logical steps each.
2. Stop before 4096 if any 1024 cell fails.
3. Run 4096 particles for seeds 0, 1, and 2 only after all 1024 cells pass.
4. Require zero particle-count mismatch, nonfinite, hard-floor, rim, radial,
   runtime, diagnostic, lifecycle, trace-integrity, and artifact-integrity
   failures in every cell.
5. Require full Kit-log byte-range/hash evidence, exact physical trace identity,
   strict lifecycle evidence, clean diagnostics, and complete artifact hashes.
   Bind executable/configuration hashes, Isaac/Kit version, host/runtime metadata,
   input layer hashes, seed, units, and exact command to each attempt.
6. Never overwrite a failed/superseded attempt. Write reruns as new immutable
   records, identify the selected attempt explicitly, and reject missing,
   duplicate, stale, or silently substituted cells.
7. For full cells, record logical traces only; disable per-integration position
   dumps. Enforce 900-second runtime, 1,020-second process, and 2 GiB per-cell
   log/trace budgets, with atomic manifest checkpointing after every cell.
8. Have an independent reviewer verify the six-cell manifest before declaring
   physical closure.

### 6. Replay and Visually Review OmniGlass

**Files**

- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- `tools/labutopia_fluid/omniglass_reference.py`
- replay tests and visual manifests

1. Select an accepted canonical trace by identity, not directory guessing.
2. Render the committed A18-scaled OmniGlass candidates without physics writes.
   Run against a read-only accepted evidence directory, snapshot trace/evidence
   USD/state hashes and physics call/write counters before and after, and fail on
   any mutation or simulation activity.
3. Capture whole-table and beaker-closeup views.
4. Run an independent visual review for containment, cup/table intersections,
   particle appearance, materials, camera framing, and missing assets.
5. Keep output pending until the reviewer explicitly approves it.
6. Bind accepted trace hash, replay/config hash, camera/render settings,
   frame/time, resolution, image hashes, reviewer identity, and timestamp into
   the visual manifest. Each required view has explicit pass/fail fields for
   containment, intersections, particle appearance, materials, framing, and
   missing assets.

### 7. Export and Validate the Standalone Delivery

1. Export the tabletop layout, accepted liquid setup, selected presentation,
   explicit SI units, and all referenced assets into one localized directory.
2. Copy that directory into an isolated path with original package/source roots
   and ambient asset search paths unavailable.
3. Recursively resolve and hash every USD, payload, reference, MDL, texture,
   material, and required plugin dependency. Fail on absolute/original paths,
   ambient/fallback resolution, missing files, or unmanifested dependencies.
4. Open it in Isaac Sim 4.1 and render a whole-table plus closeup evidence image.
5. Deliver the directory path, entry USD path, dependency manifest and hashes,
   runtime version, accepted matrix manifest, visual-review report, and
   clean-open report.

### 6A. Visual-Failure Recovery Addendum (2026-07-11)

The first authoritative replay (`..._015`) passed matrix/input/runtime/MDL
validation but failed blind visual review: all three bead candidates appeared as
dark lumps or regular bead grids, and the native table camera made the cups too
small to judge. Preserve that failure as evidence; do not select or rewrite it.

1. Keep the three A18 bead candidates unchanged as diagnostic comparisons.
2. Add `OMNI_REF_SURFACE`, a presentation-only smooth envelope derived from
   each accepted trace frame. It must use only measured point bounds, the
   calibrated cup frame, and a fixed display padding tied to the fine candidate
   width. It must not change, rescale, translate, or simulate accepted points.
3. Author the envelope as a deterministic high-resolution ellipsoid mesh with
   stable topology, smooth normals, no PhysX schema/API, and the same
   version-matched A18 OmniGlass material. Record source point count/hash,
   canonical bounds, display padding, clamping, mesh topology, and output hash.
4. Clamp the display envelope to the measured cup interior and floor. Fail if
   its authored bounds exceed the interior or if any nonfinite/degenerate frame
   is encountered. Keep accepted physical points hidden but packaged as
   provenance.
5. Replace the closeup with a measured approximately 75-degree cup-mouth view
   so liquid is seen through the opening instead of through two refractive side
   walls. Add a measured medium-wide pair-context camera in which both cups and
   enough tabletop are identifiable; keep the original native table camera only
   as secondary provenance.
6. Render all four candidates from the same immutable accepted trace and rerun
   the run-scoped MDL, input-byte, timeline, point-state, and resource-cleanup
   gates. Do not claim a PhysX step count that is not instrumented.
7. Run a new blind visual review. Select only a candidate that is visibly
   contained, identifies the real cup, avoids black/fallback material and a
   regular bead grid, and has useful closeup plus context framing. A documented
   WARN may be accepted only for minor cup-bottom refraction that does not look
   like leakage or intersection; any missing cup, opaque lump, or grid remains
   FAIL.
8. Export only the reviewed selected presentation into the standalone package;
   preserve the three bead candidates and failed review outside the delivery
   entry layer as comparison evidence.

#### Reviewed implementation constraints

Plan reviews were performed independently for architecture, completeness/edge
cases, and evidence risk. The implementation must also satisfy the following:

1. Author every candidate into a dedicated session/presentation layer. The
   accepted source layer remains read-only and is never saved. Export an entry
   layer that composes the accepted source plus the candidate presentation
   layer; mark the surface non-physical and non-collidable.
2. Define `OMNI_REF_SURFACE` exactly as a cup-canonical UV ellipsoid mesh:
   fixed `24` latitude by `64` longitude segments; deterministic north-pole,
   ring, south-pole vertex order; fixed top, quad-band, bottom face order;
   double-precision fitting followed by float32 USD authoring. The per-side XY
   padding is half the fine display width and the axial padding is one quarter
   of that width.
3. Fit canonical min/max bounds first, then uniformly reduce the radial
   semi-axes before mesh generation when required by the cylindrical interior
   clearance. Clamp only the fitted axial interval to floor/rim clearance; do
   not clamp individual vertices. Reject an impossible fit or any correction
   larger than the declared display padding.
4. Require at least four unique finite points and nondegenerate X/Y footprint;
   zero or near-zero Z span is allowed and receives the declared axial display
   padding. Reject empty, nonfinite, collinear-footprint, out-of-cup, mirrored,
   singular, or non-orthonormal frame inputs with stable error codes.
5. Verify every source point and every generated vertex against the same
   canonical cylindrical floor/rim/radius contract used by the accepted
   classifier. This is a conservative calibrated-cylinder claim, not a full
   tapered-wall SDF claim. Record the frame, geometry source/hash, clearance,
   maximum radius, axial extrema, and correction magnitude.
6. Validate fixed vertex/face counts, finite unit normals, outward winding,
   positive face area, closed two-face edge incidence, Euler characteristic
   `2`, and deterministic canonical vertex/index buffer SHA-256. Repeated and
   permuted input builds must yield the same hash.
7. Record the ellipsoid display volume, nominal disjoint physical-particle
   sphere volume, point-AABB volume, and their ratios. Every surface manifest,
   review report, caption, and delivery manifest must include exactly:
   `Presentation-only surface; not valid for physical-volume or volume-parity claims.`
   Fill level, mass, density, occupancy, or physical volume may not be inferred
   from the surface.
8. Freeze the four-candidate matrix, P4096/S0 trace, material closure hash,
   lighting, frame IDs, and camera matrices before blind review. The closeup
   angle is `75 degrees above the cup radial plane` (`15 degrees off the cup
   axis`), not 75 degrees from the axis. The pair-context frame must contain
   complete projected bounds for both cups; the native table view remains an
   uncropped provenance render.
9. Keep automated gates separate from subjective review. Geometry containment
   remains authoritative; images are presentation evidence only. A visual WARN
   requires an explicit accepted-WARN record with named residual artifact and
   cannot excuse black material, a missing cup, a particle grid, or apparent
   leakage/intersection.
10. Snapshot source/matrix/summary/trace bytes, root/session layer text,
    physical point positions/velocities/widths/IDs, relevant transforms,
    timeline, and simulation-disable settings before and after each render.
    Whitelist only the intentional presentation-frame edit before capture; do
    not claim an uninstrumented PhysX step count.
11. Record exact resolved MDL URI, Isaac/package version, required material file
    hashes, bound shader/material paths, run-scoped compiler scan, and fallback
    absence. Reproduce the pure mesh buffer hash twice before runtime promotion.
12. Preserve an audit manifest for all four candidates, image hashes, anonymous
    review labels, verdicts, and rejection reasons. The selected entry may omit
    failed candidate payloads only when this audit evidence remains linked and
    hashed from the delivery report.

## Test Order

1. Focused RED test for the next change.
2. Minimal implementation.
3. Focused GREEN test.
4. Related pure-test group.
5. Short one-variable Isaac diagnostic.
6. Independent review at each decision gate.
7. Full six-cell runtime matrix only after short diagnostics are stable.

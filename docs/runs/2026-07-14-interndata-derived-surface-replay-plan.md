# InternData Derived-Surface Replay Plan

## Goal

Turn the accepted 3 mm, 3,600-particle InternData-style pour trajectory into a
continuous-looking liquid video in the real LabUtopia tabletop scene without
changing or rerunning the accepted physics.

The implementation will reconstruct one closed presentation mesh from each
captured particle state outside the Isaac Sim 4.1 PhysX isosurface bridge. Isaac
Sim 4.1 will then replay the accepted source-beaker poses and render those
meshes with the existing context and close-up cameras. Every old particle or
isosurface presentation path will be disabled so the mesh is the sole visible
liquid representation.

This is one reviewed reconstruction treatment, not a physics retry,
runtime-isosurface retry, or top-film fallback. Visual calibration is recorded
as explicit contract revisions rather than hidden automatic retries.

## Product Contract

- Physics authority remains the accepted 691-state trace with 3,600 particles.
- Reconstruction is presentation-only and executes no physics steps.
- The visible output is a closed liquid volume, not enlarged spheres and not a
  rigid top disk.
- A18 is a look reference only: its tint, transparency, lighting, and framing
  may guide presentation, but its 20 mm particles and rectangular tank physics
  are not transferred to the small beakers.
- InternData is the behavior reference: the target is a coherent body and pour
  stream with no obvious bead texture. Pixel-identical parity is out of scope
  because assets, cameras, and lighting differ.

## Pinned Inputs

- Accepted run root:
  `docs/labutopia_lab_poc/evidence_manifests/interndata_kinematic_pour_probe_final_inset_20260714`.
- Trace: `kinematic_trace.jsonl`, 691 records, steps 0 through 690.
- Trace SHA-256:
  `0321dee981f3ca82e62018352ef66ca12772f75dda35f20330ef2124b552dfb7`.
- Authored scene: `authored_scene.usda`.
- Authored-scene SHA-256:
  `e0c020fe44536406253a9bb14a89f0d2d2b6d415abd369e780e03ef0d1db347d`.
- Accepted runtime summary: `runtime_summary.json`.
- Runtime-summary SHA-256:
  `91e2c65dfcd96841e018975d772b4c2ace081d802fc4789d28b5251d7f2a1333`.
- Capture selection: steps `0, 10, ..., 690`, exactly 70 frames.
- Cameras, 960 x 540 resolution, 15 fps, and source-beaker parent transforms
  come from the accepted runner/trace.

All three hashes are checked before reconstruction or rendering. A mismatch is
a hard failure because it would break provenance. The inherited physics verdict
comes from the pinned runtime summary; per-state trace counts remain supporting
evidence rather than a replacement top-level verdict.

## Files

- Add `tools/labutopia_fluid/interndata_surface_reconstruction.py`.
  This pure Python module owns trace loading, deterministic lattice bounds,
  particle splatting, scalar-field smoothing, marching-cubes extraction,
  normal/face validation, mesh-cache writing, and cache manifest generation.
- Add `tools/labutopia_fluid/run_interndata_surface_replay.py`.
  This runner owns cache verification, stage opening, liquid-mesh authoring,
  Points hiding, beaker-pose replay, existing camera reuse, zero-step
  Replicator capture, MP4 writing, and the final evidence manifest.
- Add `tests/test_interndata_surface_reconstruction.py`.
  This covers the pure reconstruction and cache contract.
- Add `tests/test_interndata_surface_replay.py`.
  This covers CLI/defaults, visual authority, pose/capture selection, material,
  output, and evidence contracts without launching Isaac Sim.
- Add `scikit-image==0.25.2` to `requirements.txt`. The formal cache is generated
  in a run-scoped Python 3.10 environment with the repository pins
  `numpy==1.26.0`, `scipy==1.15.3`, and `scikit-image==0.25.2`. Reconstruction
  runs before Isaac, so the Isaac runtime itself does not need this dependency.

Generated meshes, frames, videos, and manifests stay under `outputs/` and are
not committed.

## Architecture

### 1. Deterministic Reconstruction

For each selected trace state:

1. Stream all 691 JSONL records in exact step order. Reject malformed lines,
   missing/duplicate/out-of-order steps, nonnumeric or ragged points, nonfinite
   values, count/hash mismatches, invalid classification partitions, malformed
   rigid 4 x 4 source matrices, or a lattice above the fixed size cap. Do not
   sort, skip, coerce, or repair a bad record.
2. Select exact steps `list(range(0, 691, 10))` and validate all 3,600
   world-space positions in each selected record.
3. Snap the padded dynamic AABB to a world lattice anchored at `(0, 0, 0)`.
   The fixed contract is XYZ axis order, `float32` field, 0.00135 m spacing,
   16 padding voxels, and deterministic trace-order trilinear splatting.
4. Apply `scipy.ndimage.gaussian_filter` with sigma `1.60` voxels, truncate
   `4.0`, mode `constant`, and cval `0.0`.
5. Apply one gravity-Z ellipsoidal grayscale closing with XYZ radii
   `[3, 3, 8]` voxels. Require the nonzero support bounds to remain unchanged;
   this bridges the measured vertical gaps in the stream without extending the
   liquid into new spatial support.
6. Extract level `0.02` using `skimage.measure.marching_cubes` with Lewiner,
   step size `1`, descent gradient, and degenerate triangles disabled.
7. Convert vertices to world space and quantize them to the delivered
   `float32` representation. Contract only bit-identical adjacent edges, and
   reject any cleanup that changes component count, Euler characteristic,
   AABB, manifoldness, winding, or component volume beyond `1e-5` relative
   drift. No epsilon welding is permitted.
8. Apply ten uniform Taubin cycles (`lambda=0.50`, `mu=-0.53`) only to
   components at least `1e-7 m^3`. A deterministic guard limits per-component
   volume drift to 1%, total volume drift to 0.1%, vertex displacement to 1 mm,
   and outward AABB growth to 0.125 mm.
9. Orient every closed component outward, compute finite area-weighted vertex
   normals, and retain every component. Presentation reconstruction must not
   delete droplets or hide leakage.
10. Require all six scalar-field boundary slabs below level `0.02`, every
   undirected mesh edge incident to exactly two faces, valid indices, no
   degenerate triangles, positive closed volume, and no boundary-touching
   component.
11. Write compressed little-endian arrays plus per-frame diagnostics. The
   canonical geometry hash covers array names, dtypes, shapes, and uncompressed
   bytes; the cache key also covers trace/position hashes, the complete numeric
   contract, dependency versions, and reconstruction-module SHA-256.

The builder writes through a temporary directory and publishes the complete
cache atomically. The Isaac runner only consumes and verifies the manifest and
cache; it never imports or executes reconstruction. Calibration frames are
pinned to steps `0, 190, 220, 260, 690`, plus the active-pour temporal gate.
Each reviewed revision produces a new explicit contract hash and rebuilds the
gate from scratch; no automatic search matrix exists.

Execution produced four evidence gates. V1 (`sigma=1.25`) was foamy and gray;
V2 (`sigma=1.60`) still showed a bead-chain stream; V3 added guarded Taubin
smoothing and the accepted cyan material but retained stacked blobs. Reviewers
then selected the current-frame gravity-Z grayscale closing over temporal
mixing or a new mesher dependency. V4 connected every active-pour gate frame,
kept support bounds unchanged, stayed below 10% volume growth against V3, and
passed the target-wall clearance gate. The full 70-frame build then exposed two
float32-only degenerate faces at steps 170 and 450; exact adjacent-edge
contraction removed only those collapsed faces while preserving topology and
volume. Per-frame RTX subframes are fixed at eight.

### 2. Render-Only Isaac Replay

The renderer opens the pinned accepted scene and authors one
`/World/InternDataSurfaceReplay` mesh. For each selected state it:

1. applies the trace's exact `source_parent_matrix` to `/World/beaker2`;
2. keeps the world-space mesh at identity transform and atomically updates
   points, `[3] * face_count`, flattened face indices, vertex normals, and
   extent; subdivision is fixed to `none`;
3. hides `/World/InternDataParityFluid/Particles`,
   `/World/InternDataParityFluid/VisualParticles`, legacy
   `/World/ParticleSet`, and `/World/fluid` when present, disables the old
   ParticleSystem isosurface attribute, and hides any generated isosurface
   descendants;
4. traverses the composed stage and requires the reconstructed mesh to be the
   only render-visible liquid representation;
5. invokes a local minimal Replicator render barrier with timeline delta zero;
6. captures context and close-up RGB without attaching or stepping PhysX.

The final gate uses one pinned cyan `UsdPreviewSurface` contract: diffuse
`[0.46, 0.82, 0.96]`, emissive `[0.01, 0.025, 0.035]`, metallic `0.0`,
roughness `0.06`, opacity `0.06`, and IOR `1.333`. The shader backend and inputs
are read back; there is no MDL or material fallback. Geometry and material
contract hashes remain separate.

The dynamic replay authority is the cache plus runner. The exported USD is
explicitly a static final-state snapshot, not a time-sampled animation; this
keeps variable-topology authoring outside the current scope.

### 3. Evidence Boundary

The final manifest records:

- pinned input paths, sizes, and SHA-256 hashes;
- reconstruction parameters and dependency versions;
- selected trace steps and each source position hash;
- per-frame mesh counts, bounds, connected components, and cache hashes;
- source-beaker pose equality against trace matrices;
- old Points/isosurface visibility and sole-visible-liquid-representation checks;
- zero simulation/timeline advancement during replay;
- image/video properties, hashes, and capture diagnostics; and
- a separate physics verdict inherited from the trace and visual verdict from
  rendered evidence.

The mesh video demonstrates presentation of accepted readback. It does not
claim that Isaac Sim generated the surface or reran the particle simulation.
The manifest also states that stride-10 samples from a 30 Hz physics trace are
played at 15 fps, so the evidence video is a 5x-speed decimated replay.

## TDD Order

1. Write failing pure tests for all pinned digest lengths/values, strict trace
   validation, exact frame selection, snapped bounds, deterministic synthetic
   reconstruction, closed/manifold geometry, retained separated components,
   safe cache round-trip, corrupt/missing cache rejection, and manifest hashes.
2. Implement the reconstruction module until those tests pass.
3. Write failing runner-contract tests for fixed defaults, zero-step mode,
   source-pose extraction, all hidden legacy liquid paths, disabled old
   isosurface, sole mesh representation, atomic USD topology updates, material
   values, 70-frame output, and evidence schema.
4. Implement the Isaac replay runner until non-Isaac tests pass.
5. Run a synthetic marching-cubes environment smoke, then generate the five
   pinned keyframes and the eight-frame pour gate. Render five stills and one
   short clip in Isaac Sim 4.1.
6. Perform visual review for static shape, refraction, and temporal popping.
   Every concrete correction requires a reviewed, hash-bound contract revision
   and a rebuilt gate.
7. Generate all 70 meshes, both videos, the cache, and the final-state USD
   snapshot.
8. Run focused tests, related existing InternData tests, cache reopen checks, a
   two-frame radically different-topology capture smoke, decoded media checks,
   and independent visual review.

## Acceptance Criteria

### Technical

- Input hashes exactly match the pinned values.
- Exactly 70 selected states are reconstructed from the accepted trace.
- Every mesh is nonempty, finite, closed, orientable, manifold, positive-volume,
  triangulated, and hash-bound to its source positions and reconstruction
  contract. No component is silently removed.
- No accepted trace record, particle position, collider, or physics setting is
  changed.
- Both accepted particle paths, legacy points, and any old isosurface are
  invisible in every capture; the derived mesh is the sole visible liquid
  representation.
- Replay applies the exact source-beaker parent matrix for each frame.
- Isaac replay performs zero physics steps and does not advance timeline time.
- Exactly 70 unique PNGs per camera map one-to-one to the selected step/cache
  hashes; camera warmup is not a video frame.
- Context and close-up videos decode to 960 x 540, 15 fps, exactly 70 frames,
  H.264/yuv420p. Encoding uses `ffmpeg`/`libx264`, not the existing `mp4v`
  helper.

### Visual

- Source hold and final target hold read as filled liquid volumes, not bead
  clouds, foam, or rigid disks.
- The pour phase has a coherent stream and does not expose the original point
  texture.
- No obvious tabletop pool, below-table liquid, gross wall penetration,
  detached cloud, black liquid, white/flat capture, severe flicker, or camera
  clipping is visible.
- Independent visual review returns PASS. A WARN is acceptable only for a
  clearly documented minor presentation difference that does not obscure the
  liquid body or stream; FAIL blocks delivery.

## Stop Conditions

- Do not retry Isaac Sim 4.1 runtime isosurface; that route already has a
  terminal evidence outcome.
- Do not return to the top-film treatment; it already failed visual review.
- Do not change physical particle width, contact offset, trajectory, collider,
  or beaker placement to improve rendering.
- If a reviewed reconstruction revision fails the topology, volume, clearance,
  or visual gate, do not publish it as the final presentation contract.

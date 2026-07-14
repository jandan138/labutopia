# InternData Derived-Surface Replay Outcome

## Result

The accepted LabUtopia real-beaker pour now has a continuous-surface
presentation without changing or rerunning its physics. Exactly 70 states from
the hash-pinned 691-state trace were reconstructed into closed meshes and
replayed in Isaac Sim with the trace-exact source-beaker poses. The renderer made
zero physics-step calls and left timeline time unchanged.

The final presentation is not an Isaac Sim 4.1 runtime isosurface. It is a
deterministic external reconstruction of the accepted particle readback, then an
Isaac render of those meshes in the original tabletop scene. Physics and visual
claims therefore remain separate:

- the accepted particle trace proves the ending partition of 3,600 particles in
  the target, with source, transit, tabletop, below-table, and nonfinite counts
  all zero;
- the reconstructed videos prove that the same states can be presented as a
  coherent body and pour stream instead of visible Points.

## Final Contract

- World-anchored XYZ lattice with 1.35 mm spacing and 16 padding voxels.
- Trace-order trilinear splat, Gaussian sigma 1.60, and iso level 0.02.
- Gravity-Z ellipsoidal grayscale closing with radii `[3, 3, 8]` voxels and no
  support-bound expansion.
- Lewiner marching cubes, no component filtering, exact `float32` adjacent-edge
  cleanup, and guarded ten-cycle Taubin smoothing.
- Reconstruction contract SHA-256:
  `e4d62bc2b33ef73ae601a0b322cded3dd32685c4dc97e76944fa95d802453a16`.
- Cyan `UsdPreviewSurface` material with opacity 0.06, roughness 0.06, and IOR
  1.333.
- 960 x 540, 15 fps, H.264/yuv420p, exactly 70 frames per camera.

## Artifacts

- Mesh cache:
  `outputs/interndata_surface_replay_20260714/mesh_cache`.
- Cache manifest SHA-256:
  `67f4d6a5ebceab48c8b36fea48e0d3e5537a07892a25b37e9569bcba9e44b24b`.
- Final render directory:
  `outputs/interndata_surface_replay_20260714/final_render`.
- Close-up video SHA-256:
  `b151b05bd80f46854c2a86314e61ee2fee812907d5f7c0266d8b37ff0284644b`.
- Context video SHA-256:
  `ff8270af4183eee6bf33326dbbd68694ceadf8c1944f23c3ae3a38d1ec915361`.
- Static final-state USD snapshot SHA-256:
  `da7ce2879df1a3226adb83573de65194ce05367a34bbd2051d8912a54d489e51`.

The cache plus `run_interndata_surface_replay.py` is the dynamic animation
authority. `surface_replay_final.usda` is intentionally a static final-state
snapshot, not a variable-topology animation.

## Technical Gates

- All 70 frames are finite, closed, manifold, consistently wound, and
  positive-volume; no connected component was removed.
- Old Points and generated isosurface paths are hidden. The reconstructed mesh
  is the sole visible liquid representation.
- Every replayed source-beaker matrix exactly matches its trace matrix.
- Capture steps are exactly `0, 10, ..., 690`; warmup is excluded.
- Steps 170 and 450 each required one exact duplicate-vertex contraction and
  removal of two collapsed zero-area faces. Component count, Euler
  characteristic, AABB, manifoldness, and volume gates remained unchanged.
- Both videos decode as H.264, 960 x 540, 15 fps, yuv420p, with exactly 70
  frames.

## Visual Verdict

Independent review returned high-confidence `WARN`, accepted for final use. The
main stream is continuous and understandable, liquid accumulates in the target,
and no definite tabletop spill or wall penetration is visible. The remaining
non-blocking difference is mild surface faceting. A bright object visible at the
receiver bottom before pouring is pre-existing scene content, not liquid.

## Verification

- TDD report red state: the old weekly report failed the new derived-surface
  outcome contract before its content and media were updated.
- Combined regression suite: `96 passed` across reconstruction, replay,
  InternData parity, presentation profiles, and the PM report.
- Python bytecode compilation passed for both new tools.
- `git diff --check` passed after preserving the existing requirements-file
  line-ending boundary.
- Manifest audit confirmed 70 closed frames, no removed components, no density
  support expansion, all smoothing gates true, trace-exact beaker poses, sole
  visible liquid mesh, zero physics steps, and unchanged timeline time.
- Local browser audit passed at desktop `1440 x 900`, tablet `834 x 1112`, and
  mobile `390 x 844`. All three views had zero horizontal overflow, broken
  images, page errors, or console errors; all three videos reported their
  expected 960 x 540 metadata and no media error.
- Direct HTTP checks returned 200 for all three report MP4 files. Browser
  screenshots and audit JSON are under the ignored directory
  `test_outputs/pages-review/final-surface-report`.
- Three independent final report reviewers returned `PASS`: media evidence,
  responsive layout, and product-content boundaries. Their first pass found an
  undersized validation strip, cropped reference image, one empty tablet grid
  cell, missing dynamic-authority paths, and a long-link mobile overflow. The
  report was corrected and the same reviewers confirmed every finding fixed.

## Product Report

The PM weekly report now publishes the final continuous-surface context and
close-up videos while retaining the three-stage comparison: original point
attempt, rectangular-tank visual reference, and InternData-inspired real-beaker
final. It explicitly states that 3 mm particles remain the physics authority and
the offline surface is presentation-only.

# Real-Beaker Preview-Water Material Probe Plan

## Objective

Determine whether the stable real-beaker display fill becomes visibly readable
when only its render material changes from the A18 OmniGlass treatment to the
repository's existing near-clear cyan `UsdPreviewSurface` water treatment.

This is one material probe, not a new AO/RT matrix and not a physics rerun.

## Fixed Input

Use the immutable `_008` decision-authority closure, control replicate A, final
static frame:

```text
docs/labutopia_lab_poc/evidence_manifests/
real_beaker_ao_rt_matrix_v3_20260712_008/
matrix_decision_authority/final_closure/aggregate/cells/
A_0_AO0_RT4_CONTROL/OMNI_REF_DISPLAY_FILL/
OMNI_REF_DISPLAY_FILL_static.usda
```

The probe verifies only the evidence needed for a fair material comparison:

- the decision is `_008`'s `FAIL_NO_RENDER_SETTING_RECOVERY` authority;
- the static entry SHA-256 is
  `c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a`;
- `/World/CompletedPBD/PresentationSurface` is the frame-600 display mesh with
  geometry hash
  `8905803d5177e9d2a194720f942c7558847046dffce6b084bc8b66aa36f4a70d`;
- the close-up and pair-context cameras exist; and
- the static USDA bytes and presentation geometry are unchanged after capture.

Do not re-hash or freeze the full 1.7 GB authority closure.

## Changes

Create:

- `tools/labutopia_fluid/run_real_beaker_preview_water_probe.py`
- `tests/test_real_beaker_preview_water_probe.py`

Generated evidence after implementation in the unnumbered directory
`real_beaker_preview_water_material_probe_20260713`:

- `treatment_source_beaker_closeup.png`;
- `treatment_pair_context.png`;
- `probe_manifest.json`;
- two anonymous A/B sheets, one hidden label map, and a blind review record.

Do not modify:

- either existing fluid runner;
- any `_001` through `_008` evidence;
- the accepted physical trace or display-fill geometry;
- beaker materials, normals, lights, cameras, or render settings; or
- particle width, collision, or simulation parameters.

## Material Treatment

Reuse the existing presentation-water values already defined in
`run_colleague_native_usd_completed_pbd_step_video.py`:

```text
diffuseColor = [0.74, 0.94, 1.0]
emissiveColor = [0.0, 0.0, 0.0]
opacity = 0.34
roughness = 0.02
metallic = 0.0
ior = 1.333
```

Author the material in one anonymous treatment layer under the in-memory
session layer and bind it only to `/World/CompletedPBD/PresentationSurface`.
Inspect that treatment layer before Replicator starts: its authored specs may
only be the water material/shader subtree and the target material binding. Do
not save the source stage and do not add an MDL fallback or a parameter sweep.

## TDD Sequence

1. Add tests for the fixed source contract and exact render/material values.
2. Add an in-memory USD test proving the treatment layer changes only the new
   material and target binding while the presentation geometry stays identical.
3. Add a small test for the two-camera resource contract and static capture
   manifest fields.
4. Implement the pure contract/validation functions, then the Isaac capture.
5. Run focused tests, the related existing material/capture tests,
   `py_compile`, and `git diff --check`.

## Runtime And Review

1. Launch Isaac Sim 4.1 with `RayTracedLighting` and apply/read back the exact
   `_008` control settings: AO disabled, AO ray length 5, AO samples 8/16,
   denoiser mode 2, shadows enabled with 4 samples, 12 refraction bounces, and
   4 RTX subframes at 960x540.
2. Use two probe-local Replicator resources for
   `/World/Beaker2CloseupNativeMaterialCamera` and
   `/World/BeakerPairContextCamera`; do not change the frozen three-camera
   helper. Keep the timeline stopped, disable simulation playback, and render
   with `delta_time=0.0`.
3. After binding the treatment, call Replicator preview, perform camera warmup
   updates, discard one warmup capture, then retain exactly two nonblank PNGs.
4. Require exact post-capture geometry identity, no timeline advance, unchanged
   static USDA bytes, and the exact effective treatment binding/input values.
   Do not claim an instrumented zero physics-step count.
5. Build one anonymous label mapping across both views. Compare against these
   exact closure controls:
   - close-up `frame_0600.png`, SHA-256
     `6f127941887c7f3b3175f06cfd78eadfd58b8b932305e48e20b71a72d36c8dbd`;
   - pair-context `frame_0600.png`, SHA-256
     `43b9b88f7f75cfc7b726b838a5efcea81ab1ea62797e291ec8af25adcbb90dec`.
6. Preserve the sheet hashes, hidden mapping, reviewer response, and unblinded
   result.
7. Send only the sheets and visual acceptance criteria to a fresh visual reviewer.
8. Accept the treatment only if both close-up and pair-context views show a
   readable light-cyan liquid surface/body, visible containment and grounding,
   and no near-black top, ink-like body, external liquid, penetration,
   starburst, broken normal, or framing blocker.

## Stop Rule

- If the treatment passes, promote it as the presentation-material candidate
  for the eventual portable USD; physics authority remains unchanged.
- If it fails, stop this material family. Do not create `_009`, do not tune
  AO/RT again, and do not add fallback branches. The next discussion is a
  different surface/material model, informed by the visible failure.

## Plan Review

Three independent reviews covered architecture/scope, completeness/edge cases,
and operational/visual risk. All requested the same corrections now reflected
above: use 4 subframes rather than confusing them with 12 refraction bounces,
pin both control images, use a local two-camera setup, and remove full-closure
rehashing and unsupported physics-step instrumentation.

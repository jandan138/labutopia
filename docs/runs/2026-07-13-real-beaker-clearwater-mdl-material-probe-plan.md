# Real-Beaker ClearWater MDL Material Probe Plan

## Objective

Test one genuinely transmissive water material on the same accepted frame-600
display mesh after the PreviewSurface probe failed as opaque white. This is one
material-model change, not a parameter sweep, physics rerun, or new AO/RT matrix.

## Fixed Inputs

Reuse without modification:

- the `_008` control static USDA, presentation mesh, two cameras, lighting, and
  AO0/RT4 render contract used by the completed PreviewSurface probe;
- the same 960x540, four-subframe static Replicator path; and
- the `_008` cell-local `material_closure_isaacsim41_conda_core` tree.

Pin the exact absolute closure-local material entry under
`_008/A_0_AO0_RT4_CONTROL/material_closure_isaacsim41_conda_core`:

```text
Base/OmniSurfacePresets.mdl
SHA-256 5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930
subIdentifier OmniSurface_ClearWater
```

Use that same closure's `Base` and `mdl` directories as the explicit
Kit/renderer MDL search roots and require both to precede competing defaults.
After warmup, require `sourceAsset.resolvedPath` to equal the pinned entry. Do
not copy, rewrite, or flatten the closure.

## Files

Create:

- `tools/labutopia_fluid/run_real_beaker_clearwater_mdl_probe.py`
- `tests/test_real_beaker_clearwater_mdl_probe.py`

Do not modify the completed PreviewSurface runner or evidence. The new runner
starts `SimulationApp` before importing its existing static-capture helpers.

Generated output uses the unnumbered directory
`real_beaker_clearwater_mdl_material_probe_20260713` and contains exactly two
retained PNGs, one capture manifest, anonymous review sheets/mapping, and one
review record.

## Treatment

In one anonymous session sublayer:

1. Author `/World/Looks/LiquidPresentationWater/Shader` as an MDL source-asset
   shader pointing at the pinned `OmniSurfacePresets.mdl` entry and
   `OmniSurface_ClearWater` subidentifier.
2. Bind only `/World/CompletedPBD/PresentationSurface` to that material.
3. Verify the layer contains only the material/shader connection and target
   binding, with no geometry, camera, light, beaker, or physics edits.

There is no PreviewSurface fallback. Missing assets, search-path mismatch, MDL
compile errors, wrong effective binding, or blank captures fail this probe.

## TDD Sequence

1. Test the pinned MDL entry/hash, subidentifier, and search-root contract.
2. Test in-memory USD authoring: only the expected MDL material and target
   binding are authored, no PreviewSurface appears, and geometry is unchanged.
3. Test that a missing/wrong MDL entry is rejected rather than falling back.
4. Implement the fixed treatment and reuse the existing two-camera static
   capture functions.
5. Run focused and related tests, `py_compile`, and `git diff --check`.

## Runtime And Review

1. Start Isaac Sim 4.1 `RayTracedLighting` with the closure-local MDL search
   roots and exact `_008` AO0/RT4 settings.
2. After source-stage warmup and immediately before ClearWater authoring, capture
   a Kit-log cursor. Warm up and discard one capture, retain close-up and
   pair-context PNGs, then scan only the run segment for ClearWater/OmniSurface
   compile failures. Missing, truncated, incomplete, or empty log segments are
   `INVALID_PROBE`; an empty scanner result is not accepted without a valid
   non-empty segment.
3. Require unchanged source bytes and presentation geometry, a stopped timeline,
   successful two-camera cleanup, and an effective ClearWater MDL binding.
4. Build anonymous three-way sheets from the existing black OmniGlass control,
   the opaque-white PreviewSurface failure, and the new ClearWater render. Keep
   one hidden mapping across both views and ask a fresh reviewer for absolute
   pass/fail against the same water criteria. Keep the mapping outside the
   reviewer packet and do not reveal prior material identities until both-view
   judgments are final.

## Stop Rule

- If ClearWater passes both views, select it as the display-mesh material
  candidate and move to portable USD authoring/localization.
- If a technically valid ClearWater render fails visual review, stop tuning
  materials on this smooth display mesh. The next work changes presentation
  geometry (particle/isosurface lane), not another color, opacity, AO, or RT
  setting.
- Search-path, MDL compile, binding, log-segment, or capture failure is
  `INVALID_PROBE/NO_RESULT`; it does not support the visual stop conclusion.

## Plan Review

Three independent reviewers covered architecture/scope, completeness/edge
cases, and operational/visual risk. The revised plan removes the proposed edit
to completed PreviewSurface code, fails closed on unavailable MDL logs, pins
resolved MDL identity/search precedence, keeps the blind mapping outside the
review packet, and distinguishes invalid execution from a valid visual failure.

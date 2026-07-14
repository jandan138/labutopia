# Real Beaker Derived Water Film Plan

## Goal

Produce one readable, presentation-only liquid surface in the accepted real
beaker scene without changing particle physics and without relying on the Isaac
Sim 4.1 runtime-isosurface bridge.

This is not another material or render-setting matrix. The fixed change is a
different geometry model: retain only the upper liquid surface film and remove
the closed proxy's side and bottom faces. The closed display body rendered
opaque white with PreviewSurface and dark/noisy with ClearWater; a single film
avoids that nested closed-dielectric configuration.

## Fixed Inputs

- Accepted authority: `accepted_authority_P4096_S2`, frame 600, 4096 points.
- Static scene: the pinned `_008` control
  `OMNI_REF_DISPLAY_FILL_static.usda`, SHA-256
  `c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a`.
- Existing deterministic display-fill frame and calibrated beaker frame.
- Existing close-up and pair-context cameras.
- RayTracedLighting, AO0, four RTX subframes, 960x540.

## One Treatment

1. Verify the pinned closed mesh identity: proxy geometry SHA-256
   `8905803d5177e9d2a194720f942c7558847046dffce6b084bc8b66aa36f4a70d`,
   386 points, 480 faces, and the accepted frame index 600.
2. Extract source indices `289..384` as the ordered 96-vertex top ring and
   source index `385` as the top center. No duplicate closing vertex is added.
   Author exactly 96 non-degenerate upward-wound triangles
   `[center, i, (i+1) mod 96]` into a right-handed, double-sided fan at
   `/World/CompletedPBD/DerivedWaterFilm`.
3. Hide the old closed `/World/CompletedPBD/PresentationSurface` only in the
   disposable wrapper layer.
4. Bind one fixed non-emissive glossy aqua `UsdPreviewSurface`:
   diffuse `[0.16, 0.52, 0.62]`, opacity `0.72`, roughness `0.06`, metallic
   `0.0`, and IOR `1.333`.
5. Do not author any PhysX API, particle system relationship, collider, light,
   camera, or simulation state.

The stronger aqua tint is intentional: this is a readable presentation film,
not a transparent-material parity claim. No second tint or material fallback is
allowed in this run.

## Files

Create:

- `tools/labutopia_fluid/run_real_beaker_derived_water_film_probe.py`
- `tests/test_real_beaker_derived_water_film_probe.py`

Generated output:

- `docs/labutopia_lab_poc/evidence_manifests/real_beaker_derived_water_film_probe_20260713/`

If and only if visual review passes, export:

- package root:
  `outputs/usd_asset_packages/lab_001_derived_water_film_20260713/`;
- film sublayer: `derived_water_film.usda`;
- entry USD: `lab_001_level1_pour_tabletop_derived_water_film.usda`; and
- manifest: `derived_water_film_manifest.json`.

Do not modify the accepted trace, `_008` source, completed material probes, or
runtime-isosurface probe evidence.

## TDD Order

1. Test exact source/authority identity and fixed treatment values.
2. Test pure top-film extraction: exact source index order, 97 vertices, 96
   non-degenerate triangles, upward finite normals/winding, positive area,
   deterministic hash, and no side/bottom faces.
3. Test in-memory USD authoring: only the film/material and old-proxy visibility
   override are authored. The treatment layer, rather than the composed source
   stage, must add no PhysX spec, API, or relationship.
4. Test the two-camera capture manifest, exact zero-step checkpoints, and
   source/geometry integrity contract.
5. Implement the minimum static builder/capture path by reusing the existing
   display-fill and stopped-timeline Replicator helpers.

## Runtime And Review

1. Open a disposable wrapper; never save the pinned source.
2. Register a PhysX step-event counter before treatment authoring. Keep timeline
   stopped and simulation playback disabled; require count zero after warmup,
   after the discarded capture, after the strict final capture, and at cleanup.
3. Use exactly `/World/Beaker2CloseupNativeMaterialCamera` and
   `/World/BeakerPairContextCamera`. Perform the existing static warmup, require
   one successful predeclared discarded capture, then execute one strict final
   capture with no retry.
4. Require exactly two decodable, nonblank `uint8` 960x540 final PNGs with exact
   role mapping and SHA-256, unchanged source bytes, unchanged accepted
   input hash, unchanged film geometry across capture, and complete Replicator
   cleanup.
5. Send only the two retained images and these criteria to a fresh independent
   visual reviewer: liquid level readable in the right beaker, film contained
   inside the glass, no penetration/floating disk, no opaque-white plug, no
   near-black body, no framing blocker, and the treatment must read as a liquid
   surface rather than a solid plastic disk, lid, or cap.

## Stop Rule

- Missing/blank/wrong-size images or any source/hash/cleanup/zero-step failure is
  technical `INVALID`, not a visual result.
- If both technically valid views pass visual review, export the same film as a
  presentation-only sublayer in the fixed colleague-openable package. Reopen
  the entry and require resolvable source sublayers, film/material/binding,
  old-proxy visibility override, no new PhysX specs, and unchanged source hash.
- If either technically valid view fails visual review, stop Isaac Sim 4.1
  presentation tuning for this target.
  Do not change opacity/color or add another geometry candidate. The remaining
  product options are an offline renderer/mesher or a newer Isaac Sim runtime.

## Claim Boundary

The film is derived presentation geometry. It does not preserve physical liquid
volume, does not assert the free-surface shape, does not replace the accepted
particle trace, and is not valid as frame 601 or as new physics evidence.

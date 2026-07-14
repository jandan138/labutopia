# Real Beaker Derived Water Film Outcome

## Decision

Stop Isaac Sim 4.1 presentation tuning for this real-beaker target. The fixed
top-film treatment passed every technical capture guard but failed the visual
acceptance criterion: it looks like a rigid cyan disk instead of liquid.

Do not export `lab_001_derived_water_film_20260713` as a colleague-openable
package. Preserve the accepted 4096-particle static-hold result as the physics
authority.

## Formal Evidence

- Output:
  `docs/labutopia_lab_poc/evidence_manifests/real_beaker_derived_water_film_probe_20260713`
- Runtime status: `CAPTURED_DERIVED_WATER_FILM_PENDING_VISUAL_REVIEW`
- Technical validity: `true`
- Physics steps during treatment and capture: `0`
- Source and wrapper unchanged: `true`
- Film geometry: 97 vertices, 96 faces, unchanged across capture
- Close-up SHA-256:
  `8e9d0ecc0c11b5837ba2f59636df4a7e44c7cb544f38d38915c0cf21e863035c`
- Pair-context SHA-256:
  `036c057d877fbe0c7cad0cf9f9dbc6bed179af1af4e0d29421c255371dc8a17c`
- Visual verdict: `FAIL`
- Independent visual-review confidence: `0.95`
- Visual review:
  `docs/labutopia_lab_poc/evidence_manifests/real_beaker_derived_water_film_probe_20260713/visual_review.md`

## Product Interpretation

The no-leak result and the presentation result are separate. The accepted
particle simulation still demonstrates that the real USD beaker can hold the
tested static liquid state. This probe shows that rendering only its upper
surface as a translucent film is not enough to make that state look like a
filled beaker.

## Remaining Product Routes

The next implementation should change rendering technology rather than tune
this film:

1. mesh accepted particles outside the Isaac Sim 4.1 runtime-isosurface bridge
   and render the resulting closed liquid volume; or
2. validate the same accepted scene in a newer Isaac Sim runtime with a working
   particle-isosurface path.

Neither route should change the accepted particle authority until it has its
own physics validation.

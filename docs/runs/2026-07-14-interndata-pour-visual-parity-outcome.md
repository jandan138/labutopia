# InternData-style Pour Delivery Outcome

## Delivery

Package:
`outputs/usd_asset_packages/lab_001_level1_pour_interndata_liquid_v1_20260714/`

Entrypoints:

- `lab_001_level1_pour_interndata_liquid_v1.usda`: 3,600 particles in the
  validated settled source state inside `/World/beaker2`.
- `lab_001_level1_pour_interndata_pour_result_v1.usda`: all 3,600 particles in
  target beaker `/World/beaker1`.

The entire package directory is the delivery unit. Both roots use only relative
dependencies under `dependencies/` and open with `/World` as `defaultPrim`.

## Implemented Treatment

- Public InternData fluid scale: 3 mm contact offset, spacing, and rendered
  point width; 3,600 particles in a `12 x 12 x 25` grid; smoothing strength
  `50`.
- Physical and delivery visual authority are the same
  `/World/InternDataParityFluid/Particles` prim.
- Both roots deliver discrete pale-cyan `UsdGeom.Points`; there is no separate
  replay proxy and no competing delivery isosurface.
- Native beaker mesh collision is disabled. Each beaker uses one open compound
  proxy with 144 wall boxes and one bottom box, inset 1.5 mm from the visible
  interior radius.
- `/World/beaker2` is the single compound kinematic source actor; the target
  proxy under `/World/beaker1` is static.

## Results

- Static source hold: pass.
- Deterministic 690-step pour: pass.
- Final exclusive counts: target 3,600; source, transit, tabletop spill,
  below-table, and nonfinite all zero.
- Intermediate maximum transit: 262 particles, representing the airborne pour
  stream; tabletop, below-table, and nonfinite maxima remain zero.
- Clean dependency closure: pass for both roots with zero unresolved or
  outside-package dependencies.
- Isaac Sim 4.1.0 isolated-copy validation: pass. Thirty logical natural-settle
  steps advance the stabilized snapshot while retaining all 3,600 inside the
  source cup.
- Result snapshot: all 3 mm render-sphere envelopes remain inside the target,
  with positive radial and floor clearance.
- Independent final-render review: pass with high confidence for all six
  context/close views; no retake required. The remaining granular/layered point
  texture is non-blocking.

## Claim Boundary

The entrypoints are initial and final snapshots, not a prescribed animation.
An external controller must drive `/World/beaker2` to execute a pour. The MP4s
are decimated offline visualizations of strict PhysX readbacks; they support the
recorded trajectory but do not prove live render synchronization or exact robot
expert replay.

Authoritative reports:

- `evidence/delivery_manifest.json`
- `evidence/trace_provenance.json`
- `evidence/clean_directory_validation.json`
- `evidence/clean_isaacsim41_validation/delivery_clean_isaacsim41_validation.json`
- `evidence/clean_isaacsim41_validation/final_delivery_visual_review.json`

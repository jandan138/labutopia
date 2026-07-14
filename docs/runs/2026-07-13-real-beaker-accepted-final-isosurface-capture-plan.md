# Accepted Frame-600 Isosurface Capture Plan

## Goal

Render the accepted frame-600 particle state as one real PhysX isosurface in
the LabUtopia beaker scene, with zero physics steps. Capture the fixed close-up,
pair-context, and native tabletop cameras at 960x540 for visual review.

This replaces the invalid attempt that enabled smoothing and anisotropy before
the accepted 600-step solve. That attempt correctly stopped at step 0 because
presentation smoothing rewrote display point positions during paused warmup.

## Scope

Add only:

- `tools/labutopia_fluid/run_real_beaker_accepted_final_isosurface_probe.py`
- `tests/test_real_beaker_accepted_final_isosurface_probe.py`

Do not modify the accepted source USD, authority bundle, trace, frozen physics
runner, physical widths, colliders, or existing material probes. Do not add a
parameter matrix.

## Pinned Inputs

- Accepted authority bundle:
  `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712/accepted_authority_P4096_S2`
  with logical hash
  `edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605`.
- Accepted trace file SHA-256:
  `24d75adf7c5120760c127aafc29886a193a5eb288c913828dba33819da4e28d2`.
  Use only its ordered step-600 record: 4096 finite world-space positions,
  all already classified inside the visible source beaker.
- Closed real-scene render entry:
  `docs/labutopia_lab_poc/evidence_manifests/real_beaker_ao_rt_matrix_v3_20260712_008/matrix_decision_authority/final_closure/aggregate/cells/A_0_AO0_RT4_CONTROL/OMNI_REF_DISPLAY_FILL/OMNI_REF_DISPLAY_FILL_static.usda`
  with SHA-256
  `c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a`.
- ClearWater MDL SHA-256:
  `5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930`,
  subidentifier `OmniSurface_ClearWater`.
- Accepted physical offsets: particle width `0.00045`, fluid rest offset
  `0.000264627`, particle contact offset `0.000529254`, system contact offset
  `0.000793881`, and solid/non-particle rest offset `0.0004455`.
- Existing presentation contract: grid spacing `0.0002381643`, surface distance
  `0.00025139565`, smoothing radius `0.000264627`, mesh/normal smoothing passes
  `4/4`, anisotropy `5/1/2`, smoothing strength `0.5`, and no look variant.

## Implementation

1. Before starting `SimulationApp`, validate the authority through the existing
   `_validate_final_bundle` consumer, load the registered final trace record
   with standard-library JSON, and reject any wrong hash, step, count,
   non-finite coordinate, or containment count.
2. Start formal Isaac Sim 4.1 in RayTracedLighting mode with the already proven
   local MDL search roots and fixed 960x540 control render settings.
3. Create a disposable wrapper root layer whose only sublayer is the pinned
   closed real-scene entry, then open that wrapper with the timeline stopped.
   This is required because the existing authoring helper intentionally writes
   to `stage.GetRootLayer()`. Hide the old
   `/World/CompletedPBD/PresentationSurface` proxy and deactivate the native
   source fluid graph in the disposable wrapper; never edit the source layer.
4. Reuse `_author_completed_pbd_runtime_particles` against the wrapper root to
   author the accepted final positions under `/World/CompletedPBD`, enable the
   existing PhysX isosurface, anisotropy and smoothing APIs, and bind the
   existing ClearWater MDL. Before PhysX attach/smoothing, read the authored
   runtime points back in stable order and require exact equality with the
   authority step-600 positions.
5. Disable simulation playback and register a PhysX step-event counter before
   attach. Attach the stage without calling `simulate`, `fetch_results`, or
   `timeline.play`. Require the counter to remain zero after attach, every
   paused warmup update, both Replicator captures, and detach. Presentation
   smoothing may update only the runtime display points; that is expected and
   is not reused as physics evidence.
6. From the particle-system path returned by the helper, poll the exact
   `<particle-system>/Isosurface` child and require it to be the unique runtime
   `UsdGeom.Mesh`; absence after fixed warmup is technical `INVALID`. Isaac 4.1
   may expose only bridge/placeholder mesh attributes in USD while the generated
   vertices live in Fabric/Hydra, so do not claim USD mesh bounds that the API
   does not provide. Record whether USD attributes are placeholder or populated.
   Compute the runtime mesh's bound material and require it to resolve to the
   pinned ClearWater source asset and subidentifier, with no PreviewSurface
   fallback. Accepted bottom/radial/rim containment remains bound to the pinned
   frame-600 particles; visible reconstructed-surface containment is judged from
   the three actual captures.
7. Reuse the existing Replicator static-capture helper for exactly these camera
   paths: `/World/Beaker2CloseupNativeMaterialCamera`,
   `/World/BeakerPairContextCamera`, and `/World/Camera1`. Keep the timeline
   stopped through one discarded material warmup and one final capture. Its
   scene-integrity callback excludes only the PhysX-owned runtime particle set
   and isosurface subtree while continuing to hash all other scene point data.
   Require one decodable, non-constant 960x540 PNG from each exact camera.
8. Detach the zero-step PhysX stage, destroy Replicator resources, scan the
   run-scoped Kit log for ClearWater compile success and fatal isosurface errors,
   and verify the pinned source file/layer and generated wrapper file remain
   unchanged on disk. In-memory wrapper edits are disposable and expected.
9. Write `probe_manifest.json` with the accepted input hashes, authored final
   position hash, zero-step lifecycle summary, isosurface mesh summary, material
   contract, camera capture hashes, log hash, and terminal technical status.

## TDD Order

1. Write failing tests for final-record loading and pin validation.
2. Write failing tests for the fixed isosurface contract and source/runtime path
   separation.
3. Write failing tests for pre-smoothing authored-position equality, zero-step
   counter checkpoints, runtime isosurface bridge classification, exact three
   cameras/PNG validity, and terminal status when material/log/source gates fail.
4. Implement only enough standard-library contract code to pass those tests.
5. Run the focused tests, then related existing isosurface/material tests.
6. Run one formal Isaac integration capture. Do not add a second candidate.

## Technical Outcomes

- `CAPTURED_TECHNICALLY_VALID_PENDING_VISUAL_REVIEW`: frame 600 is pinned,
  physics step count is zero, the runtime isosurface bridge exists and carries
  ClearWater, timeline stays stopped, and all three PNGs are valid. Visible
  surface containment remains pending visual review.
- `INVALID_ACCEPTED_FINAL_ISOSURFACE_PROBE`: any input, zero-step, mesh,
  material, capture, source-integrity, or log gate fails. Invalid is not a
  visual failure.

## Visual Review

Submit the three original PNGs with neutral labels to a fresh reviewer. Pass
requires all of: a continuous surface rather than beads or a rigid proxy;
contained and grounded liquid without spill/floating/wall intersection;
water-like rather than chalk-white, near-black, or artifact-heavy appearance;
and readable close-up plus table context. No image tuning or recapture occurs
before the verdict.

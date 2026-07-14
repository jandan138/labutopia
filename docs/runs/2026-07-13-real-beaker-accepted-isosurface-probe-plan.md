# Accepted Real-Beaker Isosurface Probe Plan

## Goal

Produce one formal Isaac Sim 4.1 run with fixed multi-camera captures of the
accepted 4096-particle, 600-step static hold using the repository's existing
PhysX isosurface path.
The probe answers only whether true reconstructed liquid geometry looks like
water in the real LabUtopia beaker and tabletop scene.

This is a single probe, not a parameter matrix. It does not change particle
widths, collision offsets, spawn layout, collider geometry, source USD, or the
accepted runner implementation.

## Pinned Inputs

- Scene:
  `outputs/usd_asset_packages/lab_001_level1_pour_support_aligned_v1_20260712/lab_001_level1_pour_support_aligned_v1.usda`
  with SHA-256
  `3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b`.
- Frozen accepted runner:
  `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712/accepted_authority_P4096_S2/frozen_runner_baseline/run_colleague_native_usd_completed_pbd_step_video.py`
  with SHA-256
  `25f02f58e5a4d0adc11beaf503f8d5e74c5fcfafc7b1b7078e1a971ae50118e4`.
- Accepted authority:
  `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712/accepted_authority_P4096_S2`.
  Its logical bundle hash is
  `edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605`.
- Accepted checkpoint trace:
  `accepted_authority_P4096_S2/runtime_evidence_snapshot/particle_readback_trace.jsonl`
  with file SHA-256
  `24d75adf7c5120760c127aafc29886a193a5eb288c913828dba33819da4e28d2`.
  It contains the 21 ordered checkpoints `0, 30, ..., 600`.
- Physics configuration: 4096 particles, seed 2, 600 logical steps,
  logical dt 1/60 s, integration dt 1/600 s, 10 integration substeps, physical
  particle width 0.00045 m, and unchanged accepted collision offsets.
- Presentation configuration: existing PhysX isosurface with grid spacing
  `0.0002381643`, surface distance `0.00025139565`, smoothing radius
  `0.000264627`, four mesh and four normal smoothing passes; anisotropy
  scale/min/max `5/1/2`; smoothing strength `0.5`; existing
  `OmniSurface_ClearWater` material; 960x540; and no look preset or
  render-setting sweep.
- ClearWater source:
  `.../site-packages/omni/mdl/core/Base/OmniSurfacePresets.mdl`, subidentifier
  `OmniSurface_ClearWater`, with SHA-256
  `5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930`.

## Files And Artifacts

No production source file is modified for this probe.

- Existing tests exercised:
  `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py` and
  `tests/test_fluid_recipe.py`.
- New output directory:
  `docs/labutopia_lab_poc/evidence_manifests/real_beaker_accepted_isosurface_probe_20260713`.
- Required final images:
  `presentation_isosurface_frames/frame_0600.png`,
  `beaker2_closeup_native_material_frames/frame_0600.png`, and
  `camera1_native_material_frames/frame_0600.png`.
- Required runtime records:
  `runtime_smoke_summary.json`, `particle_readback_trace.jsonl`, the generated
  overlay USD, MP4 outputs, and the run-scoped Isaac log segment.

## Execution Order

1. Verify both pinned input hashes and that the output directory is absent.
   Validate the complete accepted authority bundle through the repository's
   existing `_validate_final_bundle` consumer. Any preflight failure stops the
   probe.
2. Run the existing focused unit tests for presentation-mode resolution,
   isosurface contract construction, postprocessing, and frame accounting.
   Then run the frozen runner's `--help` through the exact formal interpreter,
   working directory, and `PYTHONPATH` used below. A test or import failure stops
   the probe.
3. Launch exactly one formal Isaac Sim 4.1 process from the repository root.
   All paths passed to the nested frozen runner are absolute:

   ```bash
   env PYTHONPATH=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia \
     /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python3.10 \
     /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712/accepted_authority_P4096_S2/frozen_runner_baseline/run_colleague_native_usd_completed_pbd_step_video.py \
     --usd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/outputs/usd_asset_packages/lab_001_level1_pour_support_aligned_v1_20260712/lab_001_level1_pour_support_aligned_v1.usda \
     --real-beaker-static-hold --controlled-spawn-count 4096 \
     --controlled-spawn-seed 2 --steps 600 \
     --logical-dt 0.016666666666666666 \
     --integration-dt 0.0016666666666666668 \
     --substeps-per-logical-step 10 --trace-interval 30 \
     --runtime-timeout-seconds 900 --capture-native-cameras \
     --capture-closeup-camera --hard-exit-after-run --video-stride 30 \
     --video-fps 15 --width 960 --height 540 \
     --display-particle-width 0.0043 \
     --presentation-render-mode isosurface --headless \
     --out-dir /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_accepted_isosurface_probe_20260713 \
     --manifest /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_accepted_isosurface_probe_20260713/runtime_smoke_summary.json
   ```

4. Validate the runtime before judging appearance:
   - strict 600-step execution and containment still pass;
   - all 21 new checkpoints have the same step index, particle count, ordered
     world-space positions, and finite values as the 21 authority checkpoints;
     this is called checkpoint equivalence, not an unobserved per-step claim;
   - strict execution reports 600 logical steps, 6000 integration steps, and
     `render_updates_advance_physics=false` with 22 render-invariance checks;
   - the PhysX isosurface, anisotropy, and smoothing contracts are enabled with
     the pinned values above;
   - the final material contract positively reports MDL ClearWater, its source
     asset and subidentifier, no fallback, and no compile error in the scoped log;
   - each required PNG decodes at exactly 960x540 and contains non-constant RGB
     pixels. Process failure, missing/corrupt frames, incomplete log evidence, or
     any failed technical gate makes the result `INVALID` before visual review.
5. Submit all three unmodified final PNGs, with neutral filenames and no
   implementation history or expected outcome, to a fresh visual-review agent.
   The fixed rubric is:
   - continuous liquid surface rather than isolated beads or a rigid block;
   - contained inside and grounded at the bottom of the source beaker, with no
     visible spill, floating sheet, or wall intersection;
   - water-like appearance rather than opaque chalk, near-black ink, or severe
     red/grain artifacts;
   - coherent and identifiable in both close-up and table context.

   All four items must pass. An unreadable/empty/corrupt capture is technical
   `INVALID`; a valid capture that fails any item is visual `FAIL`.
6. Record one terminal result:
   - `PASS_ACCEPTED_ISOSURFACE_VISUAL_PROBE` when the continuous surface is
     visibly contained, grounded, water-like, and coherent in both close-up and
     table context;
   - `FAIL_ACCEPTED_ISOSURFACE_VISUAL_PROBE` when the runtime is valid but the
     reconstructed surface visibly fails that rubric;
   - `INVALID_ACCEPTED_ISOSURFACE_PROBE` when physics identity, isosurface
     authoring, material compilation, or capture validity fails.

## TDD And Verification

The implementation path already exists and this task changes no executable
code, so a new red-green implementation cycle is not applicable. Its 56 focused
unit tests are a mandatory pre-run gate. The generated artifact is the
integration test: compare its checkpoint trace, source identities, runtime
contract, material contract, and capture validity with the accepted authority.
The visual result is reviewed independently because pixel quality is not
inferable from unit tests.

## Stop Rules

- Do not add another material, width, AO, refraction, camera, or isosurface
  parameter candidate in this probe.
- A technical-invalid result is not a visual failure.
- A technically valid visual failure ends this exact probe and informs the next
  product decision; it does not trigger an automatic matrix.

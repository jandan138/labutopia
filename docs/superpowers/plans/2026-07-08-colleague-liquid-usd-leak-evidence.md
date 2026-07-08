# Colleague Liquid USD Leak Evidence Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans for future implementation rounds. This file is both the execution plan and the signed evidence handoff for the first bounded run.

**Goal:** Produce bounded, reviewable evidence for whether the colleague-provided `lab_001_level1_pour_tabletop_with_liquid.usd` leaks when stepped under IsaacSim41 particle physics.

**Current result:** B0 is `FAIL_CONTAINER_LEAK` on the bounded 512-particle colleague-position smoke run. D0 is `STOP_RAW_RUNTIME_INCOMPLETE` on the immutable raw 50k colleague USD audit. D1-D3 have a completed 50k diagnostic run in a minimal native-beaker slice. D3N/D4N now have a stronger full-native-scene run: the original `lab_001_level1_pour_tabletop_with_liquid.usd` was opened, all original `50000` particle positions were used as initial-condition data, a complete IsaacSim41 PBD runtime overlay was authored under `/World/CompletedPBD`, MDL materials were closed with an IsaacSim41 core local mirror, native/closeup videos were captured, and the static hold leaked. D4 remains the next engineering stage if we want to make the beaker actually hold true PBD fluid.

**B0 architecture:** Keep the colleague USD immutable. The B0 runner opens it in IsaacSim41, reads the authored `/World/ParticleSet` particle positions, disables the original incomplete runtime particle prims in the session, re-authors a bounded 512-particle red PBD diagnostic set from the same initial positions, and steps against the LabUtopia native `beaker2` visual plus a `native-proxy-wrapper` collision route. Evidence is a JSON manifest, particle readback trace, projection frames, and a red side-view diagnostic MP4 centered on the source beaker.

**D0 architecture:** D0 is separate from B0. It is a raw 50k direct-step readiness/contract audit. It does not re-author particles, does not add PBD material, does not add wrapper collision, and stopped before original 50k timeline step because the raw runtime contract was incomplete.

**D1-D3 50k diagnostic architecture:** Keep the raw USD immutable, but treat `/World/ParticleSet` as initial-condition data. The runner uses all original `50000` points (`--particle-limit 0`), authors a complete runtime PBD particle system/material overlay in IsaacSim41, steps a static hold against the current `native-proxy-wrapper` source beaker route, records particle readback, writes a diagnostic projection video, and captures a real IsaacSim41 RGB camera video. This proves the completed-PBD diagnostic leaks at rest; it still does **not** prove the raw USD can direct-step or that the asset is benchmark-ready.

**Tech Stack:** Python 3.10, Isaac Sim 4.1, USD/PhysX/PBD, `pxr.Usd`, OpenCV MP4 encoding, JSON evidence manifests.

## Scope And Claim Boundary

This plan answers one narrow question:

```text
If we take the colleague-authored initial liquid particle positions and make them a valid IsaacSim41 PBD particle set, does the source beaker keep them inside after step?
```

Allowed claim after this run:

```text
colleague_liquid_usd_bounded_leak_smoke_executed=true
colleague_liquid_usd_bounded_classification=FAIL_CONTAINER_LEAK
leak_status_supported_by_particle_readback=true
red_side_projection_video_available=true
colleague_raw_50k_liquid_usd_d0_readiness_audit_completed=true
colleague_raw_50k_liquid_usd_runtime_step_executed=false
colleague_raw_50k_liquid_usd_direct_runtime_claim_allowed=false
colleague_50k_completed_pbd_static_leak_run_executed=true
colleague_50k_completed_pbd_static_leak_classification=FAIL_CONTAINER_LEAK
colleague_50k_completed_pbd_static_leak_below_table_count=36013
colleague_50k_completed_pbd_static_leak_real_rgb_camera_available=true
colleague_native_usd_50k_completed_pbd_step_video_recorded=true
colleague_native_usd_50k_completed_pbd_classification=FAIL_CONTAINER_LEAK
colleague_native_usd_50k_completed_pbd_below_table_count=46301
colleague_native_usd_50k_completed_pbd_source_retention_fraction=0.07398
colleague_native_usd_50k_material_closure=isaacsim41_core_mdl_local_mirror
colleague_native_usd_50k_mdl_compile_status=PASS
colleague_native_usd_50k_visual_review=WARN
```

Blocked claims remain:

```text
original_50k_colleague_usd_is_benchmark_ready
direct_original_50k_colleague_usd_runtime_result
level1_pour_true_fluid_runtime_passed
s3_kinematic_pour_released
s4_franka_replay_released
ebench_score_or_policy_claim_allowed
full_visual_material_parity
diagnostic_projection_equals_product_camera_render
native_visual_material_parity_complete
wide_native_cameras_prove_fluid_leak_detail
marker_video_equals_physical_fluid_mesh
```

Plain-language boundary:

```text
这次不是直接宣布同事的原始 50k 液体 USD 已经能进 benchmark。
我们做的是一个受控诊断：拿同事文件里的初始液体点位，按 IsaacSim41 能 step/readback 的 PBD 粒子方式重建一份红色诊断液体，再看它在 source beaker 里会不会漏。
```

## Files

- Created: `tools/labutopia_fluid/run_colleague_liquid_usd_leak_smoke.py`
  - Reads the colleague USD, builds the actual tabletop source/target regions from `/World/beaker2`, `/World/beaker1`, and `/World/table` bboxes.
  - Creates a bounded red runtime particle set under standard `/World/ParticleSystem` and `/World/ParticleSet` without modifying the source USD.
  - Writes `runtime_smoke_summary.json`, `particle_readback_trace.jsonl`, projection frames, diagnostic MP4, real IsaacSim41 RGB frames/MP4, and D3 review marker metadata.
- Created: `tests/test_fluid_colleague_liquid_usd_leak_smoke.py`
  - Covers deterministic particle sub-sampling, actual tabletop region construction, source-grid control positions, runtime offset resolution, variant spec selection, and leak classification.
- Updated: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
  - Adds PM-facing interpretation of this colleague-USD evidence.
- Updated: `docs/labutopia_lab_poc/evidence_manifests/README.md`
  - Registers the manifest and artifact directory.
- Created:
  - `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708.json`
  - `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/`
- Created:
  - `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
  - `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`
  - `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708.json`
  - `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/`
  - `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_visual_review_20260708.json`

## Execution Record

### Task 1: Add Helper Tests And Runner

- [x] Write failing helper tests for the missing module.
- [x] Implement deterministic particle subset selection, bbox-to-region conversion, source-grid controls, native/proxy variant selection, runtime offset handling, and trace classification.
- [x] Verify helper tests pass.

Latest focused test:

```bash
python -m pytest -q tests/test_fluid_colleague_liquid_usd_leak_smoke.py
```

Expected: `7 passed`.

Current focused test after D1-D3 camera/50k additions:

```bash
python -m pytest -q tests/test_fluid_colleague_liquid_usd_leak_smoke.py
```

Expected: `11 passed`.

### Task 2: Run Bounded IsaacSim41 Leak Smoke

- [x] Execute the bounded run with the source-beaker-facing red diagnostic view.

Command:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
tools/labutopia_fluid/run_colleague_liquid_usd_leak_smoke.py \
  --headless \
  --collider-mode native-proxy-wrapper \
  --position-mode colleague-sampled \
  --particle-limit 512 \
  --steps 120 \
  --trace-interval 10 \
  --video-stride 4 \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708.json
```

Artifacts:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/runtime_smoke_summary.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/particle_readback_trace.jsonl
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/colleague_liquid_leak_red_side_projection.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/projection_frames/
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/minimal_native_beaker_slice.usda
```

### Task 3: Result Classification

- [x] Classify by particle readback, not by visual impression alone.

Key result:

```text
classification=FAIL_CONTAINER_LEAK
sampled_particle_count=512
original_particle_count=50000
diagnostic_particle_size_override_used=false
source_count_step0=512
source_count_final=150
outside_source_count_final=362
below_table_count_final=362
target_count_final=0
spill_count_final=0
particle_count_final_fraction=1.0
nan_count=0
readback_position_changed=true
max_displacement=0.19574435605145393
gpu_dynamics_enabled=true
update_particles_to_usd_setting=true
suppress_readback_setting=false
```

Plain-language interpretation:

```text
第 0 步，512 个采样红色液体粒子都在 source beaker 区域内。
step 后，362 个粒子到了桌面高度以下，只有 150 个还留在 source 区域。
所以在这个受控 PBD/readback 诊断中，source beaker 没有把同事液体初始点位装住。
```

### Task 4: Video And Visual Review

- [x] Inspect MP4 metadata.
- [x] Inspect start/mid/end frames.

Video:

```text
path=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/colleague_liquid_leak_red_side_projection.mp4
resolution=960x540
duration=2.066667s
frames=31
fps=15
```

Visual review summary:

```text
frame_0000.png: red particles are inside the blue source-beaker region.
frame_0060.png: most red particles are below the table line; label shows below_table=362.
frame_0120.png: terminal frame remains below-table leak; not a transient single-frame artifact.
```

Boundary:

```text
The MP4 is a source-beaker-centered red diagnostic side projection.
It is intentionally readable for leak evidence, but it is not a full Isaac RGB camera render and not product-level visual/material parity evidence.
```

### Task 5: Root Cause Learned During Debug

- [x] Separate readback failure from real leak.

Initial debug runs produced `FAIL_READBACK_UNAVAILABLE` because USD particle readback settings were reset during `World.reset()`:

```text
update_particles_to_usd=false
suppressReadback=true
```

The runner now forces readback settings before `World` creation, after `World` creation, and again after reset/play/update:

```text
SETTING_UPDATE_TO_USD=true
SETTING_UPDATE_PARTICLES_TO_USD=true
SETTING_UPDATE_VELOCITIES_TO_USD=true
/physics/suppressReadback=false
```

After this fix, the same diagnostic route produced moving particles and a real leak classification instead of a static readback failure.

### Task 6: PM/Intern Handoff

- [x] Update handoff docs.
- [x] Register the evidence manifest.
- [x] Keep claim boundary strict.

The recommended PM explanation is:

```text
同事的 USD 不是完全没内容：它确实在 source beaker 里放了液体点位。
但“有液体点位”不等于“IsaacSim41/EBench 里能稳定盛住真实液体”。
我们把这些点位转成可 step、可 readback 的红色 PBD 粒子后，看到多数粒子很快掉到桌面以下。
这说明当前方案更像静态视觉/初始点位包，不是可以直接进入 benchmark 的稳定真实液体方案。
```

### Task 7: D1-D3 Full 50k Completed-PBD Static Leak Evidence

- [x] Reuse the colleague USD as immutable initial-condition data.
- [x] Use all original `50000` particle positions with `--particle-limit 0`.
- [x] Author a complete IsaacSim41 PBD runtime overlay: valid `ParticleSystem`, `ParticleSet`, PBD material, GPU dynamics, and readback settings.
- [x] Step a static hold, with no pouring motion.
- [x] Capture diagnostic projection video and real IsaacSim41 RGB review camera video.
- [x] Keep red D3 review markers explicitly labeled as review-only, readback-derived, and non-physics.
- [x] Record independent visual review for the terminal RGB/projection frames.

Command:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
tools/labutopia_fluid/run_colleague_liquid_usd_leak_smoke.py \
  --headless \
  --collider-mode native-proxy-wrapper \
  --position-mode colleague-sampled \
  --particle-limit 0 \
  --steps 120 \
  --trace-interval 10 \
  --video-stride 10 \
  --require-camera-rgb \
  --width 960 \
  --height 540 \
  --rgb-review-marker-limit 512 \
  --rgb-review-marker-width 0.02 \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708.json
```

Key result:

```text
runtime_step_executed=true
d1_pbd_completion_overlay_executed=true
d2_static_hold_leak_evidence_executed=true
particle_scope=full_original_50k
full_original_50k_completed_pbd_overlay=true
original_particle_count=50000
selected_particle_count=50000
classification=FAIL_CONTAINER_LEAK
source_retention_fraction=0.27974
outside_source_count=36013
below_table_count=36013
spill_count=0
target_count=0
nan_count=0
readback_position_changed=true
max_displacement=0.19898774732047234
d3_real_isaacsim41_rgb_camera_passed=true
real_rgb_camera_frame_count=13
diagnostic_projection_frame_count=13
rgb_camera_video_written=true
```

Artifacts:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/runtime_smoke_summary.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/particle_readback_trace.jsonl
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/colleague_liquid_leak_red_side_projection.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/colleague_liquid_static_leak_rgb_camera.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/rgb_camera_frames/frame_0120.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/projection_frames/frame_0120.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/minimal_native_beaker_slice.usda
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_visual_review_20260708.json
```

Plain-language interpretation:

```text
这次不是追求“不漏”。相反，我们要给领导证明：同事文件里的 50000 个液体初始点位，在我们补齐 IsaacSim41 PBD 物理以后，静置就会漏。
结果很清楚：50k 粒子全部进入运行时并被 readback；step 后有 36013 个粒子已经到 source 区域外且低于桌面高度。真实 RGB 图也能看到杯底外侧的红色漏出区域。
所以当前证据支持“补全 PBD 以后静置会漏”，不支持“可以直接做 benchmark-ready true fluid”。
```

Independent visual review:

```text
overall_verdict=PASS
rgb_terminal_frame=PASS
diagnostic_projection_terminal_frame=PASS
note=RGB can be used for PM/leadership review; physics classification still comes from particle readback counts.
```

### Task 8: D3N/D4N Full Native USD Scene Step Video And Material Closure

- [x] Open the original colleague package entry directly:
  `outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd`.
- [x] Keep the raw USD immutable; use its `/World/ParticleSet` as initial-condition data.
- [x] Use all original `50000` positions with `--particle-limit 0`.
- [x] Deactivate the incomplete original `/World/fluid`, `/World/ParticleSet`, and `/World/ParticleSystem` in the runtime session.
- [x] Author a completed PBD overlay under `/World/CompletedPBD/ParticleSystem` and `/World/CompletedPBD/ParticleSet`.
- [x] Avoid `World.reset()` for the full native scene, because it triggers raw `/World/fluid/Cylinder` Poisson sampling/cooking and can hang; use timeline updates after the overlay is authored.
- [x] Close IsaacSim41 material dependencies with a local mirror of `/isaac-sim/kit/mdl/core`.
- [x] Retarget native `sourceAsset` MDL references to the local mirror and record the compatibility fallback:
  `/World/Looks/OmniSurface_Glass/Shader` maps `OmniSurfacePresets.mdl::OmniSurface_Glass` to
  `OmniGlass.mdl::OmniGlass` for IsaacSim41.
- [x] Capture native `Camera1`, native `Camera2`, a beaker2 closeup native-material camera, and a closeup review-marker video.
- [x] Record independent visual review as WARN, not PASS-without-caveats.

Command:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  --headless \
  --usd outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd \
  --particle-limit 0 \
  --steps 24 \
  --trace-interval 4 \
  --video-stride 4 \
  --video-fps 8 \
  --width 960 \
  --height 540 \
  --capture-native-cameras \
  --capture-closeup-camera \
  --capture-review-markers \
  --review-marker-limit 1500 \
  --review-marker-width 0.012 \
  --warmup-updates 1 \
  --camera-warmup-updates 3 \
  --runtime-timeout-seconds 720 \
  --skip-app-close \
  --hard-exit-after-run \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708.json
```

Key result:

```text
runtime_step_executed=true
native_scene_opened=true
particle_scope=full_original_50k
selected_particle_count=50000
runtime_pbd_completion_overlay_used=true
classification=FAIL_CONTAINER_LEAK
source_retention_fraction=0.07398
outside_source_count=46301
below_table_count=46301
particle_count_final_fraction=1.0
nan_count=0
readback_position_changed=true
max_displacement=3.258722390681572
mdl_compile_status=PASS
```

Artifacts:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/runtime_smoke_summary.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/particle_readback_trace.jsonl
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/native_scene_completed_pbd_overlay.usda
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/beaker2_closeup_native_material.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/beaker2_closeup_review_markers.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/camera1_native_material.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/camera2_native_material.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_visual_review_20260708.json
```

Material closure:

```text
material_closure_mode=isaacsim41_core_mdl_local_mirror
copied_base_file_count=18
copied_omnisurface_file_count=6
retargeted_shader_count=10
compatibility_fallback=OmniSurface_Glass_to_OmniGlass_for_isaacsim41
mdl_compile_status=PASS
```

Plain-language interpretation:

```text
这次终于是在同事给的原生完整桌面 USD 场景里录的，不是最小切片。
同事文件里的 50000 个液体点被全部拿来做初始条件；我们在 runtime 里补了一套完整 PBD 物理层。
补完以后，粒子确实动了，也能 readback；但静置 24 step 后，46301 个粒子已经低于桌面线，只有约 7.4% 还留在 source 区域。
所以这条证据证明“补全物理后会漏”，不是证明“液体资产已经可评测”。
```

Visual review:

```text
overall_verdict=WARN
A_early_closeup=WARN: first usable closeup frame; beaker rim is visible, but red content reads like a solid red mass.
A_end_closeup=PASS: transparent beaker and escaped red blob/smear are visible.
B_end_marker=WARN: useful diagnostic overlay, not product-facing native evidence.
C/D wide native cameras=WARN: useful for tabletop context, too distant for leak detail.
```

PM wording:

```text
给领导看时，用 closeup end video/frame 解释“原生场景里，补完 PBD 后静置会漏”。
不要把 wide camera 当漏液证据；wide camera 只证明这是桌面布局。
不要把 marker video 当真实水面；它只是把 readback 粒子位置放大给人看。
不要说材质已经达到 LabUtopia51 native visual parity；现在只是 IsaacSim41 能编译渲染，不再红色 fallback。
```

### Task 9: D3N-L Long 20s Full Native USD Video

- [x] Re-run the same full native USD scene for a longer product-facing review video.
- [x] Keep `--particle-limit 0`, so all original `50000` points are used.
- [x] Use `--steps 240`, `--video-stride 1`, and `--video-fps 12`, yielding `240` frames and `20.0s` per video.
- [x] Preserve the same IsaacSim41 core MDL local mirror material closure.
- [x] Record the visual caveat: the native closeup shows time evolution clearly, but below-table leak classification still comes from particle readback.

Command:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  --headless \
  --usd outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd \
  --particle-limit 0 \
  --steps 240 \
  --trace-interval 12 \
  --video-stride 1 \
  --video-fps 12 \
  --width 960 \
  --height 540 \
  --capture-native-cameras \
  --capture-closeup-camera \
  --capture-review-markers \
  --review-marker-limit 1500 \
  --review-marker-width 0.012 \
  --warmup-updates 1 \
  --camera-warmup-updates 3 \
  --runtime-timeout-seconds 1200 \
  --skip-app-close \
  --hard-exit-after-run \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708.json
```

Key result:

```text
duration=20.000000s
fps=12
frame_count=240
resolution=960x540
selected_particle_count=50000
runtime_step_executed=true
classification=FAIL_CONTAINER_LEAK
below_table_count=49235
source_retention_fraction=0.0153
mdl_compile_status=PASS
```

Artifacts:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/beaker2_closeup_native_material.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/beaker2_closeup_review_markers.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/camera1_native_material.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/camera2_native_material.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_visual_review_20260708.json
```

PM wording:

```text
这版视频长度已经符合“长一点”的展示需求：主 closeup 是 20 秒，不再是 0.75 秒。
它是原生完整 USD 场景里的 native-material camera，不是 minimal slice。
但画面上主要看到红色粒子团从满杯逐步塌到杯底/前侧；真正的 49235 below-table leak 数字来自 readback 统计，不应该只凭肉眼视频解释。
```

## D0-D4 Follow-up Plan

This section tracks the D-stage follow-up. D0 raw 50k readiness audit is
complete and frozen as evidence; no original 50k timeline step was executed.
D1-D3 now also have completed diagnostic evidence for the user's immediate
leadership-demo question: after completing the PBD runtime overlay, the full
50k static hold leaks. D3N/D4N adds the requested full-native-USD scene video
and material closure evidence, with the same failed-containment conclusion.
D4 remains planned because D4 is the stage that tries to make a fluid-safe
wrapper instead of merely proving the current route leaks.

Multi-agent review changed one important naming choice: the run above is **not**
`D0 direct original USD`. It is a completed baseline evidence item:

```text
B0_COMPLETED = 512-particle bounded PBD/readback smoke
B0 status = STOP_WITH_EVIDENCE
B0 classification = FAIL_CONTAINER_LEAK
B0 direct_original_50k_runtime_claim_allowed = false
```

The D-stages below start from the user's two questions:

```text
1. Can the raw 50k USD be stepped directly?
2. Can we produce a real IsaacSim41 camera view instead of a diagnostic projection?
```

### Review Basis

The plan uses these facts from local IsaacSim41 and existing project evidence:

```text
PhysX/PBD particle helpers:
/isaac-sim/extsPhysics/omni.physx/omni/physx/scripts/particleUtils.py
  add_physx_particle_system
  add_pbd_particle_material
  add_physx_particleset_points

Particle readback settings:
/isaac-sim/extsPhysics/omni.physx/omni/physx/bindings/_physx.pyi
  SETTING_UPDATE_PARTICLES_TO_USD = /physics/updateParticlesToUsd
  SETTING_SUPPRESS_READBACK = /physics/suppressReadback

Isaac camera/render APIs:
/isaac-sim/exts/isaacsim.sensors.camera/isaacsim/sensors/camera/camera.py
  Camera.get_current_frame
  render_product_path

Existing project evidence:
docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md
docs/labutopia_lab_poc/evidence_manifests/README.md
```

External reference:

```text
NVIDIA Omni Physics particles:
https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/particles/particles.html
```

### Stage Summary

| Stage | Name | Question | Current status |
|---|---|---|---|
| B0 | Existing bounded smoke | If we re-author 512 sampled colleague positions as valid red PBD particles, does source hold? | Completed: `FAIL_CONTAINER_LEAK`, 362/512 below table. |
| D0 | Raw USD direct-step readiness audit, no-step contract check | Does the original colleague USD already contain a complete IsaacSim41 PBD runtime object? | Completed: `STOP_RAW_RUNTIME_INCOMPLETE`; raw points exist, no original 50k timeline step was executed, and raw runtime contract is incomplete. |
| D1 | PBD completion overlay | If raw USD is incomplete, can we treat its points as initial-condition data and build a complete runtime overlay? | Completed for diagnostic route: all original 50k positions stepped with completed PBD overlay. |
| D2 | Static hold ladder | With completed PBD runtime and candidate collider route, can source hold at 512/1024/4096/50k without leak? | Completed as failure evidence for current route: full 50k static hold is `FAIL_CONTAINER_LEAK`, 36013/50000 below table. This does not pass the D2 zero-leak gate. |
| D3 | Real IsaacSim41 RGB review camera | Can a real Isaac camera show the source beaker and red liquid evidence clearly? | Completed for review media: 13 real RGB frames and MP4 captured; RGB is explanatory evidence, not the physics judge. |
| D4 | Fluid-safe wrapper collider fix | Can we design a wrapper collider that keeps the native beaker visual but provides stable PBD particle containment? | Planned only. Required before releasing S3 kinematic pour. |

### D0: Raw USD Direct-Step Readiness Audit

Goal:

```text
Open the colleague USD immutably and test whether the authored particle prims
are already a valid IsaacSim41 PBD runtime object.
```

Do not do these in D0:

```text
do_not_reauthor_particles
do_not_replace_material_with_PBD_material
do_not_switch_to_red_diagnostic_particles
do_not_add_proxy_wrapper_collision
do_not_claim_50k_benchmark_ready
```

D0 may set runtime readback flags so we can observe what the raw USD does:

```text
/physics/updateParticlesToUsd=true
/physics/suppressReadback=false
```

Audit fields:

```text
raw_usd_path
raw_usd_sha256
particle_set_path=/World/ParticleSet
particle_system_path=/World/ParticleSystem
particle_count
particle_widths_summary
physics_scene_path=/World/PhysicsScene
gravity_direction
gravity_magnitude
gpu_dynamics_enabled
broadphase_type
solver_type
has_PhysxParticleSystem
has_PhysxParticleSetAPI
has_PhysxPBDMaterialAPI
particle_system_relationship_closed
material_binding_target
readback_position_changed
initial_position_hash
final_position_hash
warning_scan
```

D0 GO criteria:

```text
raw stage loads in IsaacSim41
original /World/ParticleSet remains active
original /World/ParticleSet is driven by original /World/ParticleSystem
PhysicsScene has finite non-zero gravity
GPU dynamics and GPU broadphase are enabled
PBD material contract is present and bound to the particle system/set
reset/play/update keeps particle readback available
particle position hash changes after step
particle_count_final_fraction >= 0.95
nan_count == 0
no CPU fallback / GPU unsupported / PhysX fatal error
```

D0 STOP classifications:

```text
STOP_RAW_RUNTIME_INCOMPLETE
  Missing or invalid PBD material, GPU dynamics, gravity, particle schema, or
  particle-system relationship.

STOP_READBACK_UNAVAILABLE
  USD points do not update after step even with readback settings enabled.

STOP_CONTAINER_LEAK
  Raw particles move, but source beaker/native collision cannot hold them.

STOP_PERF_OR_OOM
  Raw 50k direct run is too slow, OOMs, or is too unstable to classify.
```

PM wording:

```text
D0 只回答“同事原文件是不是已经能被 IsaacSim41 当成完整真实液体来 step”。
如果 D0 STOP，并不代表同事没给液体；它代表原 USD 还不能直接当 benchmark-ready 真实液体。
```

D0 execution record:

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_raw_usd_direct_step_audit_20260708.json
artifact_dir=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_raw_usd_direct_step_audit_20260708_001/
runtime=isaacsim41
audit_mode=static_raw_contract_audit
runtime_step_executed=false
raw_50k_timeline_step_executed=false
step_skipped_reason=raw_runtime_contract_incomplete
warning_scan_status=not_run_due_to_raw_contract_stop
classification=STOP_RAW_RUNTIME_INCOMPLETE
status=STOP_WITH_EVIDENCE
direct_original_50k_runtime_claim_allowed=false
```

Key D0 findings:

```text
raw particle count=50000
particle set path=/World/ParticleSet
particle system path=/World/ParticleSystem
particle_system_relationship_closed=true
has_PhysxParticleSetAPI=true
has_PhysxParticleSystem=true
has_PhysxPBDMaterialAPI=false
gravity_direction=(0, 0, 0)
gravity_magnitude="-Infinity"
gravity_finite_nonzero=false
gravity_invalid_reasons=["zero_gravity_direction", "nonfinite_gravity_magnitude"]
gpu_dynamics_authored=true
broadphase_type=GPU
solver_type=TGS
material_binding_targets=["/World/Looks/OmniGlass_01"]
no_step_static_snapshot_particle_count=50000
no_step_static_snapshot_nan_count=0
readback_position_changed=false
readback_note="No-step static snapshot fields; not post-timeline survival evidence."
```

Plain-language D0 result:

```text
同事原始 USD 不是空文件：里面确实有 50000 个液体点，也有 ParticleSet 和 ParticleSystem。
但它还不是 IsaacSim41 可以直接 step 的完整真实液体资产，因为缺少 PBD material 合同，
而且 PhysicsScene 的重力是无效/零向量状态。我们没有替它补 PBD material、没有改红色粒子、
没有加 wrapper collider，所以 D0 正确停止在 raw runtime contract incomplete。
```

### D1: PBD Completion Overlay

Goal:

```text
Treat the colleague liquid points as initial-condition data, not as a completed
runtime fluid asset. Build a runtime-complete PBD overlay without modifying the
raw USD.
```

D1 responsibilities:

```text
read /World/ParticleSet authored positions
record raw particle count and hash
disable or isolate incomplete raw runtime prims in the session/overlay
author explicit PhysxParticleSystem
author explicit PhysxParticleSetAPI
author explicit PBD material
bind red review material/displayColor for visibility
force GPU dynamics and readback settings
record collider route in manifest
record exact particle count used: 512 / 1024 / 4096 / 50000
```

D1 GO criteria:

```text
runtime_step_executed=true
readback_position_changed=true
particle_count_final_fraction >= 0.95
nan_count == 0
no CPU fallback / GPU unsupported / PhysX fatal error
manifest records raw-vs-overlay claim boundary
```

D1 current evidence:

```text
B0 proves D1-style completion can step/readback for 512 sampled particles:
readback_position_changed=true
particle_count_final_fraction=1.0
nan_count=0

B0 does not prove source hold:
classification=FAIL_CONTAINER_LEAK
outside_source_count=362
below_table_count=362

D1-D3 full 50k diagnostic proves the overlay route also steps/readbacks with every original point:
full_original_50k_completed_pbd_overlay=true
original_particle_count=50000
selected_particle_count=50000
runtime_step_executed=true
readback_position_changed=true
particle_count_final_fraction=1.0
nan_count=0
```

PM wording:

```text
D1 是把“静态液体点位”补成“IsaacSim41 能 step/readback 的 PBD 粒子”。
D1 通过只代表粒子能动、能读回；不代表杯子能装住，也不代表能倒液。
```

### D2: Static Hold Ladder

Goal:

```text
Before pouring, prove the source beaker/collider can hold completed PBD particles
while static.
```

D2 particle-count ladder:

```text
512 -> 1024 -> 4096 -> 50000
```

Do not jump directly to a 50k release claim. A direct 50k run can be useful as a
diagnostic, but it cannot be called release evidence unless lower counts already
pass the same strict gate.

D2 GO criteria for each candidate:

```text
outside_source_count == 0
spill_count == 0
target_count == 0
below_table_count == 0
source_retention_fraction >= 0.95
particle_count_final_fraction >= 0.95
tail_leak_rate_fraction_per_second < 0.02
nan_count == 0
readback_position_changed=true
cpu_collision_fallback_detected=false
gpu_collider_unsupported=false
```

D2 STOP classifications:

```text
STOP_STATIC_HOLD_LEAK
STOP_READBACK_UNAVAILABLE
STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE
STOP_PERF_OR_OOM
```

Current D2 status:

```text
B0 already gives one D2-style 512-particle static hold result:
status=STOP_WITH_EVIDENCE
classification=FAIL_CONTAINER_LEAK

The full 50k diagnostic run confirms the same failure mode at original scale:
status=STOP_WITH_EVIDENCE
classification=FAIL_CONTAINER_LEAK
outside_source_count=36013
below_table_count=36013
source_retention_fraction=0.27974
```

PM wording:

```text
D2 是“杯子静止时能不能装住水”。静止都装不住，就不能进入倒液视频。
```

### D3: Real IsaacSim41 RGB Review Camera

Goal:

```text
Produce human-readable real IsaacSim41 RGB review camera evidence targeted at
/World/beaker2, synchronized with particle readback.
```

D3 is not a physics gate. The physics classifier remains `particle_readback_trace.jsonl`
and region counts. RGB video explains the evidence to humans.

D3 implementation requirements:

```text
create /World/D3Beaker2ReviewCamera or equivalent Isaac Camera sensor
target camera from /World/beaker2 world bbox, not hand-guessed framing
capture raw Isaac RGB frames or MP4 via Camera.get_current_frame / render product
record camera position, orientation, focal length, clipping range, resolution
capture start/mid/final frames with matching readback step_index
save raw RGB separately from annotated/contact-sheet derivatives
```

Visibility strategy:

```text
PBD particles should have red review material/displayColor.
If raw RGB cannot reliably show tiny particles, add non-collision
/World/D3ReviewMarkers derived from readback positions.
Markers must be labeled review-only and must not affect physics.
```

D3 GO criteria:

```text
frame_source=isaac_camera_rgb
raw RGB frames/MP4 are non-empty and non-near-black
resolution >= 1280x720 recommended
/World/beaker2 or runtime native beaker visual is clearly visible
source beaker rim, table top, bottom/below-table area are visible
red particles or readback-derived markers are visible
RGB frames are synchronized with readback records
manifest includes raw frame hashes and trace path
independent visual review returns PASS or accepted WARN
```

D3 blocked claims:

```text
rgb_visual_alone_proves_leak_status
diagnostic_projection_equals_product_camera_render
full_visual_material_parity
level1_pour_true_fluid_runtime_passed
```

PM wording:

```text
D3 是“让人看懂”的真实相机证据，不是“让机器判定漏不漏”的证据。
漏不漏仍然看 readback 数字。
```

D3 execution record:

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708.json
rgb_video=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/colleague_liquid_static_leak_rgb_camera.mp4
rgb_terminal_frame=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/rgb_camera_frames/frame_0120.png
d3_real_isaacsim41_rgb_camera_passed=true
real_rgb_camera_frame_count=13
d3_review_markers_enabled=true
d3_review_markers_are_physics=false
d3_review_marker_source=particle_readback_positions
```

PM interpretation:

```text
RGB 图给人看现象：杯子底部外侧有红色漏出区域。
判定漏不漏不靠肉眼，而靠同一 step 的 readback 数字；红色 review markers 只是把 readback 粒子位置在相机图里放大给人看，不参与物理。
```

### D4: Fluid-Safe Wrapper Collider Fix

Goal:

```text
Keep the native LabUtopia beaker visual, but build a controlled fluid-safe
physics wrapper that can actually hold PBD particles.
```

D4 should consume B0/S2/S2F evidence:

```text
native beaker2 visual is useful for appearance
native beaker2 mesh is not proven fluid-safe
convexDecomposition/SDF direct native routes failed in S2F4
native render mesh plus proxy wrapper was closer but still leaked
```

D4 candidate families:

```text
segmented wall/bottom proxy wrapper
native visual + invisible physics shell
SDF/cooked wrapper with explicit bottom seal
contact-offset and particle-spacing variants
slow-settle initialization variants
```

D4 GO criteria:

```text
at least one wrapper candidate passes D2 static hold at 512/1024/4096
candidate does not depend on non-physical max_velocity guardrail
warning scan has no CPU fallback / GPU unsupported / PhysX fatal error
visual prim and physics wrapper are separately documented
manifest records exact wrapper geometry and material/collision settings
```

D4 STOP classifications:

```text
STOP_WRAPPER_NOT_FLUID_SAFE
STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE
STOP_PERF_OR_OOM
STOP_VISUAL_PHYSICS_MISMATCH
```

After D4 GO:

```text
Return to the main True PhysX/PBD Fluid Spike pipeline.
Only then release S3 kinematic pouring.
Only after S3/S4/S5/S6/S7 evidence can any EBench benchmark-ready wording be considered.
```

PM wording:

```text
D4 是真正修“杯子能不能装水”的阶段：外观看原生烧杯，物理上用专门给液体设计的 wrapper。
它过了以后，才值得拍倒液和接 EBench。
```

## Revised Next Stop-Go

Recommended next work is not S3 pouring and not another blind 50k release run:

```text
1. Keep B0 as signed 512-particle bounded leak evidence.
2. Treat completed D0 as the raw USD readiness audit: raw 50k points exist, but no original 50k timeline step was executed because the raw runtime contract is incomplete.
3. Treat completed D1-D3 50k run as signed leak evidence for the completed-PBD diagnostic route; do not call it raw USD pass or benchmark-ready.
4. Stop using the current native-proxy-wrapper route as a release candidate, because full 50k static hold leaked.
5. Use D4 to build a fluid-safe wrapper collider.
6. Re-run D2 static zero-leak gates on any D4 candidate before any pouring.
7. Release S3 kinematic pour only after D4 produces a D2-passing wrapper candidate.
```

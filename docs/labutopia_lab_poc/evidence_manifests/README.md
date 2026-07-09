# LabUtopia EBench Evidence Manifest Field Guide

## 目的

这个目录里的 manifest 是 PM 汇报和工程签收的证据来源。以后外部 asset package 进入 EBench 时，不能先写“已完成”，而要先写清楚 `run_id`、`command`、`artifact path`、`PASS/FAIL/BLOCKED`、`allowed_claims` 和 `blocked_claims`。
AAN runtime environment、preflight、failure classification 和 evidence 字段以
[`../aan_runtime_environment_bootstrap.md`](../aan_runtime_environment_bootstrap.md)
为准。

## 2026-07-06 Expert Oracle Stop-Go Roadmap

`eos2_expert_oracle_stop_go_roadmap_20260706.json` 记录最新总控 stop-go 规划，计划文档是
[`../../superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md`](../../superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md)。
它不是新的 live evidence，不释放更强 score claim；它把后续判断统一成 PM 侧 M1-M4 和工程侧 S0-S4。
当前 canonical 状态是：S0 real expert action source 已冻结，S1/M1 formal score-chain 已通过，Route B
fresh S1 产出 `score=1.0` / `success_rate=1.0`；S2-R1E full-env repaired replacement replay 已补齐
M3 single-episode score/readback evidence。最新 result review 是
`eos2_expert_oracle_s2_r1e_full_env_repaired_result_review_20260707.json`：run id
`eos2_s2_l1r_full_env_repaired_route_b_readback_render_20260707_003`，official `score=1.0` /
`success_rate=1.0`，`metric_score=[[[1.0]]]`，终态 DryingBox `RevoluteJoint=41.715865deg`，
`metric_input.within_range=true`，`succ_cnts=59`，terminal camera artifact 和 canonical `camera2.mp4`
都存在。当前允许 claim `s1_completed=true`、`m1_formal_score_chain_pass=true` 和
`m3_single_episode_score_readback_evidence_complete=true`；`workflow_ready_for_expansion=false`、
`official_leaderboard_claim_allowed=false`、`policy_score_claim_allowed=false`、`visual_material_parity_complete=false`
和 `project_no_go_claim_allowed=false` 仍保持不变。

`eos2_expert_oracle_s0_s2_completion_audit_20260707.json` 是当前 goal 的完成审计索引：它逐项引用
S0 freeze success、S1/M1 fresh score-chain result 和 S2-R1E result review，结论为
`PASS_EOS2_S0_S1_S2_COMPLETION_AUDIT`。它只签收 EOS 0-2 / M3 单集 score-readback 证据；M4 小样本稳定、
S3 Lift2 oracle/retarget、policy score、official leaderboard 和视觉材质 parity 仍未签收。

`eos2_review_camera_reset_smoke_20260707_104047.json` 是 `level1_open_door` 的 review-only 相机证据。
它不是新的 score run，也不是 task completion 视频，只证明 reset 状态下新增的 `tabletop_camera`、
`front_camera` 和 `side_camera` 能被 EBench/GenManip runtime 创建、读回并产出可审阅 PNG。
独立视觉 review 给三路新增相机均为 PASS：俯视图能看桌面布局，正面图能看门、handle 和控制面板，侧面图能看
机器人与 DryingBox 的相对位置。整体 verdict 仍记录为 WARN，是因为原 `camera2` 作为 canonical
scoring/readback camera 画面不适合产品展示；这不是 blocker，也不改变评分口径。

`eos2_review_camera_full_replay_20260707_111621.json` 是上述 reset smoke 之后的 full replay review-media
闭环证据。它用同一份 frozen Route B action source，在 review camera override 下跑完整 `level1_open_door`
replay，runner 退出 `0`，`classification=PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT`，`review_media_run=true`，
`score_claim_allowed=false`，`canonical_score_claim_allowed=false`。server-side recorder 产出四路 MP4：
`tabletop_camera.mp4`、`front_camera.mp4`、`side_camera.mp4` 和 unchanged `camera2.mp4`，每路 `579` frames /
`19.3s`。独立视觉 review 结论是整体 WARN：`tabletop_camera` / `front_camera` / `side_camera` 均 PASS，
`camera2` 仍 WARN，因为它是 legacy scoring/debug view，不是产品正面。PM 可以说“完整任务过程现在有俯视、
正面、侧面三路可读视频”；不能把这条 review-media run 升级成新的 official score source、policy score、
leaderboard claim 或 full visual/material parity。

## 2026-07-07 True PhysX/PBD Fluid Spike

True PhysX/PBD Fluid Spike 是一条 parallel research track，不覆盖当前 `Expert Oracle Score` 主线。
它回答的是 `level1_pour` 能否加入真实 PhysX/PBD particle fluid，并在失败时把 blocker 归因到
schema、GPU dynamics、beaker collider、kinematic pour、EBench consumer、metric/readback、repeatability
或 performance。

关联文档：

```text
docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md
docs/superpowers/specs/2026-07-07-true-physx-pbd-fluid-spike-design.md
docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md
```

证据命名必须使用独立前缀，不使用 `eos2_`、`expert_oracle_`、`score_oracle_` 或 `aan_`：

```text
run_id=fluid_spike_isaacsim41_ebench_<stage>_<scene>_<YYYYMMDD>_<NNN>
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s<stage>_<slug>_<YYYYMMDD>.json
manifest_type=true_physx_pbd_fluid_spike_evidence
```

S0 scope freeze 已完成，当前 canonical evidence 是：

```text
fluid_spike_s0_scope_freeze_20260707.json
fluid_spike_s0_schema_probe_20260707.json
fluid_spike_s0_isaacsim41_app_schema_probe_20260707.json
```

S0 结论：目标 IsaacSim41 / EBench 环境在 `SimulationApp` 启动后可以看到
`pxr.PhysxSchema`、`omni.physx`、`PhysxSceneAPI`、`PhysxParticleSystem`、
`PhysxParticleSetAPI`、`PhysxParticleAPI` 和 `PhysxPBDMaterialAPI`；RTX 4090 GPU 对该环境可见。
但 S0 没有做粒子 step，也没有验证烧杯 collider、EBench consumer 或 metric readback。

S1 standalone particle smoke 已完成，当前 canonical evidence 是：

```text
fluid_spike_s1_standalone_particle_smoke_20260707.json
fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/runtime_smoke_summary.json
fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/particle_readback_trace.jsonl
fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/physics_scene_settings.json
fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/initial_frame.png
fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/mid_frame.png
fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/terminal_frame.png
fluid_spike_s1_visual_review_20260707.json
```

S1 结论：standalone scene 在目标 IsaacSim41 runtime 中 `status=GO_NEXT`；`gpu_dynamics_enabled=true`、
`particle_count_initial=256`、`particle_count_final=256`、`particle_count_final_fraction=1.0`、
`nan_count=0`、`readback_available=true`、`runtime_step_executed=true`。它只释放
standalone PBD particle runtime/readback claim 和 S2 collider matrix，不释放 `level1_pour` true fluid、
EBench particle runtime、metric/readback、score、policy 或 leaderboard claim。三张 PNG 是 readback
diagnostic projection，不是产品级 camera render；最终 diagnostic projection 独立视觉 review 为 `PASS`。

S2/S3 必须包含 collider matrix，至少覆盖 segmented box/wall proxy、simplified thick-wall open cup
proxy、segmented convex wall pieces、SDF tri-mesh open beaker、native `beaker2/mesh`
`convexDecomposition` 和 custom cylinder / analytic geometry negative control。

当前允许 claim：

```text
level1_pour_current_true_fluid=false
lab003_clock_usd_particle_template_exists=true
true_fluid_spike_scope_planned=true
s0_scope_freeze_completed=true
isaacsim41_app_physx_particle_schema_available=true
selected_runtime_gpu_visible=true
s1_particle_smoke_released=true
s1_particle_runtime_passed=true
s1_standalone_particle_readback_available=true
s1_diagnostic_projection_frames_available=true
s2_beaker_collider_matrix_released=true
s2_beaker_collider_matrix_completed=true
s2_beaker_collider_matrix_status=STOP_WITH_EVIDENCE
s2_best_for_s3=[]
s2_followup_plan_ready=true
s2f1_c2_proxy_sweep_completed=true
s2f1_c2_proxy_sweep_status=STOP_WITH_EVIDENCE
s2f1_best_for_s3=[]
s2f2_velocity_contact_offset_completed=true
s2f2_velocity_contact_offset_status=GO_NEXT
s2f2_root_cause_classification=VELOCITY_INITIAL_LAYOUT_COUPLED_SENSITIVITY
s2f2_best_for_s2f5=["C2A_009_S2F2_VEL020"]
s2f5_promotion_review_completed=true
s2f5_promotion_review_status=STOP_WITH_EVIDENCE
s2f5_promotion_review_passed_trial_count=0/6
s2f5_best_for_s3=[]
s2f3_c3_sdf_sweep_completed=true
s2f3_c3_sdf_sweep_status=STOP_WITH_EVIDENCE
s2f3_c3_sdf_sweep_reason=no_c3a_sdf_candidate_passed
s2f3_best_for_s2f5=[]
colleague_liquid_usd_bounded_leak_smoke_executed=true
colleague_liquid_usd_bounded_classification=FAIL_CONTAINER_LEAK
colleague_liquid_usd_bounded_sampled_particle_count=512
colleague_liquid_usd_bounded_original_particle_count=50000
colleague_liquid_usd_bounded_below_table_count=362
colleague_liquid_usd_bounded_readback_position_changed=true
colleague_liquid_usd_red_side_projection_video_available=true
colleague_raw_50k_liquid_usd_d0_audit_completed=true
colleague_raw_50k_liquid_usd_d0_classification=STOP_RAW_RUNTIME_INCOMPLETE
colleague_raw_50k_liquid_usd_particle_count=50000
colleague_raw_50k_liquid_usd_runtime_step_executed=false
colleague_raw_50k_liquid_usd_step_skipped_reason=raw_runtime_contract_incomplete
colleague_raw_50k_liquid_usd_direct_runtime_claim_allowed=false
colleague_50k_completed_pbd_static_leak_run_executed=true
colleague_50k_completed_pbd_static_leak_classification=FAIL_CONTAINER_LEAK
colleague_50k_completed_pbd_static_leak_particle_scope=full_original_50k
colleague_50k_completed_pbd_static_leak_below_table_count=36013
colleague_50k_completed_pbd_static_leak_readback_position_changed=true
colleague_50k_completed_pbd_static_leak_real_rgb_camera_available=true
colleague_50k_completed_pbd_static_leak_visual_review=PASS
colleague_native_usd_50k_completed_pbd_step_video_recorded=true
colleague_native_usd_50k_completed_pbd_classification=FAIL_CONTAINER_LEAK
colleague_native_usd_50k_completed_pbd_below_table_count=46301
colleague_native_usd_50k_completed_pbd_source_retention_fraction=0.07398
colleague_native_usd_50k_material_closure=isaacsim41_core_mdl_local_mirror
colleague_native_usd_50k_mdl_compile_status=PASS
colleague_native_usd_50k_visual_review=WARN
colleague_native_usd_50k_long_video_recorded=true
colleague_native_usd_50k_long_video_duration_seconds=20.0
colleague_native_usd_50k_long_video_frame_count=240
colleague_native_usd_50k_long_completed_pbd_below_table_count=49235
colleague_native_usd_50k_long_visual_review=WARN
colleague_50k_completed_pbd_blue_isosurface_diagnostic_baseline=true
colleague_50k_completed_pbd_blue_isosurface_final_realistic_water_claim_allowed=false
# Historical registry keys below keep evidence path continuity; PM label is
# "unified diagnostic surface (MDL target not yet passed)" / presentation water (MDL pending).
unified_realistic_water_visualization_followup_planned=false
unified_realistic_water_visualization_executed=true
unified_realistic_water_visualization_manifest=fluid_spike_unified_realistic_water_visualization_20260709.json
unified_realistic_water_visualization_runtime_manifest=fluid_spike_unified_realistic_water_visualization_20260709_001/RAW_AS_IS_full50k_v2.json
unified_realistic_water_visualization_video_duration_seconds=20.0
unified_realistic_water_visualization_video_frame_count=240
unified_realistic_water_visualization_classification=FAIL_CONTAINER_LEAK
unified_realistic_water_visualization_below_table_count=39024
unified_realistic_water_visualization_outside_source_count=41067
unified_realistic_water_visualization_source_retention_fraction=0.17866
unified_realistic_water_visualization_material_backend=USD_PREVIEW_FALLBACK
unified_realistic_water_visualization_preferred_backend=MDL_WATER
unified_realistic_water_visualization_mdl_compile_status=FALLBACK_USED
unified_realistic_water_visualization_visual_review=WARN_REALISM_NOT_YET_PHOTOREAL
unified_realistic_water_visualization_all_liquid_particles_visible=true
unified_realistic_water_visualization_state_specific_materials=false
# Do not claim MDL_WATER PASS; presentation water remains FALLBACK / MDL pending.
s3_kinematic_pour_released=false
next_fluid_work=["S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP"]
s2_s3_collider_matrix_required=true
```

当前禁止 claim：

```text
level1_pour_true_fluid_runtime_passed
ebench_particle_runtime_passed
s3_kinematic_pour_released
fluid_score_claim_allowed
policy_score_claim_allowed
official_leaderboard_claim_allowed
visual_only_liquid_equals_true_fluid
diagnostic_projection_equals_product_camera_render
original_50k_colleague_liquid_usd_is_benchmark_ready
direct_original_50k_colleague_liquid_usd_runtime_result
raw_50k_colleague_liquid_usd_can_direct_step_as_true_pbd_fluid
completed_pbd_static_leak_equals_benchmark_ready_fluid
real_rgb_review_marker_equals_physical_fluid_mesh
native_visual_material_parity_complete
wide_native_cameras_prove_fluid_leak_detail
marker_video_equals_physical_fluid_mesh
saturated_blue_isosurface_equals_final_realistic_water
realistic_water_video_equals_physics_success
realistic_water_video_fixes_collider_leak
unified_realistic_water_visualization_equals_photoreal_water
unified_realistic_water_visualization_equals_mdl_water_parity
state_specific_coloring_required_to_show_leak
```

S2 canonical evidence:

```text
fluid_spike_s2_collider_matrix_20260707.json
fluid_spike_s2_runtime_warning_scan_20260707.json
fluid_spike_isaacsim41_ebench_s2_beaker_collider_matrix_20260707_001/
```

S2 follow-up planning evidence:

```text
fluid_spike_s2_followup_plan_20260707.json
fluid_spike_s2f0_baseline_freeze_20260707.json
fluid_spike_s2_followup_c2_proxy_sweep_20260707.json
fluid_spike_isaacsim41_ebench_s2_followup_c2_proxy_sweep_20260707_001/
fluid_spike_s2f2_velocity_contact_offset_20260708.json
fluid_spike_isaacsim41_ebench_s2f2_velocity_contact_offset_20260708_001/
fluid_spike_s2f3_c3_sdf_sweep_20260708.json
fluid_spike_isaacsim41_ebench_s2f3_c3_sdf_sweep_20260708_001/
fluid_spike_s2f4_c4_native_mesh_isolation_20260708.json
fluid_spike_isaacsim41_ebench_s2f4_c4_native_mesh_isolation_20260708_001/
```

S2 结论：`status=STOP_WITH_EVIDENCE`，`best_for_s3=[]`。C0、C1、C2、C3、C5 均为
`FAIL_CONTAINER_LEAK`；C4 native `beaker2/mesh` `convexDecomposition` 为
`FAIL_NATIVE_CONVEX_INTERIOR_NOT_USABLE`。所有 variant 都有 particle readback 和运动证据，
没有 `NaN`，但没有任何非负控 collider 达到 `source_retention_fraction>=0.95`、
`outside_source_count==0`、`spill_count==0`、`target_count==0` 且 `below_table_count==0`
的 S3 放行条件。C2 是当前最接近的 failed candidate：`source_retention_fraction=0.828125`，
但仍有 `spill_count=32` 和 `below_table_count=12`。

S2 runtime warning scan 未发现 `CPU collision fallback`、`GPU collider unsupported` 或 PhysX error。
C4 的 `material:binding` scope warning 只说明原生 mesh reference 的外观材质绑定超出 reference scope，
不把它解释为 collider 失败主因。S2 PNG 是 diagnostic projection；`v2_dynamic_z_shows_below_table_leaks`
版本用红色点显示 below-table leak，不是产品级 camera render。

S2 后续规划已更新为 `S2F Collider Follow-up`，不是直接进入 S3。调研结论是：Isaac Sim /
Omniverse 的确支持 PBD particle fluid demo，但 demo 通常依赖 GPU dynamics、physics-friendly
collider、`particle_contact_offset/contactOffset/restOffset` 调参、SDF/convex proxy 和低加速度动作；
不能假设 LabUtopia 原生 render mesh 天然就是可盛液体的 particle collider。S2F 统一拆成
`S2F0-S2F5`：先冻结 S2 baseline，再做 C2 proxy sweep、velocity/contact offset isolation、
C3 SDF sweep、C4 native beaker isolation，最后做 promotion review。只有至少一个非负控
variant 达到 `outside_source_count==0`、`spill_count==0`、`target_count==0`、
`below_table_count==0`，才允许释放 S3。

S2F0 已完成 baseline freeze：`fluid_spike_s2f0_baseline_freeze_20260707.json`
把 S2 collider matrix、runtime warning scan、visual review、`s2_no_outside_source_v2`
放行合同和 C2 closest-failed baseline 锁成一个不可变入口。当前 `phase_status` 是
`S2F0_BASELINE_FREEZE=COMPLETE`，`S2F1_C2_PROXY_SWEEP=COMPLETE_STOP_WITH_EVIDENCE`，
`S2F2_VELOCITY_CONTACT_OFFSET=COMPLETE_GO_NEXT`，`S2F5_PROMOTION_REVIEW=COMPLETE_STOP_WITH_EVIDENCE`，
`S2F3_C3_SDF_SWEEP=COMPLETE_STOP_WITH_EVIDENCE`，
`S2F4_C4_NATIVE_MESH_ISOLATION=COMPLETE_STOP_WITH_EVIDENCE`。这表示 S2F2 找到的
promotion review 候选已经复核失败，SDF 路线和 LabUtopia 原生 beaker mesh 路线也没有找到可晋级候选，
仍不允许直接跑 S3。

S2F1 已完成 C2 proxy sweep：12 个 C2A segmented proxy 候选都在 IsaacSim41 中完成 240-step
runtime smoke，artifact-level warning scan 未发现 `CPU collision fallback`、`GPU collider unsupported`
或 PhysX error。结果仍是 `STOP_WITH_EVIDENCE`，`best_for_s3=[]`：没有候选满足
`outside_source_count==0` 和 `spill_count==0` 的严格放行条件。最接近的是 `C2A_005` 和
`C2A_009`，均为 `source_retention_fraction=0.9921875`，但仍各有 `outside_source_count=2`、
`spill_count=2`；`C2A_007` 为 `source_retention_fraction=0.9765625`，但仍有
`outside_source_count=6`、`spill_count=3`、`below_table_count=3`。因此 S3 仍不放行，
下一步进入 `S2F2_VELOCITY_CONTACT_OFFSET`，聚焦这三个 near-pass 候选。

S2F2 已完成 velocity/contact-offset isolation：18 个候选只围绕 `C2A_005`、`C2A_009`
和 `C2A_007` 展开，固定杯子几何，只分别隔离初始径向速度、particle contact offset、
collider contact/rest offset、CCD 和 non-physical `max_velocity` guardrail。唯一有效通过候选是
`C2A_009_S2F2_VEL020`，`source_retention_fraction=1.0`、`outside_source_count=0`、
`spill_count=0`、`below_table_count=0`。诊断结论是
`VELOCITY_INITIAL_LAYOUT_COUPLED_SENSITIVITY`：低初始速度让静态持液通过，但 baseline 与
VEL020 的 post-reset position hash 不同，所以不能把它夸大成“纯速度变量已完全隔离”。
`C2A_009_S2F2_VMAX010` 也能数值不漏，但它被明确标记为
`FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE`，不能作为 release 方案。

S2F5 promotion review 已完成：`fluid_spike_s2f5_promotion_review_20260708.json`
只复核 `C2A_009_S2F2_VEL020`，覆盖 3 个 `particle_seed` 和 2 个粒子数，合计 6 组
IsaacSim41 headless runtime。结果是 `STOP_WITH_EVIDENCE`，`best_for_s3=[]`，
`s3_kinematic_pour_released=false`。256 粒子组只漏 1-2 个粒子，说明 S2F2 线索接近但未达
严格 gate；1024 粒子组三个 seed 分别有 347、340、338 个粒子到 source 外，说明高粒子数下容器
不稳定。当时的下一步是不释放 S3，而是执行 `S2F3_C3_SDF_SWEEP` 和
`S2F4_C4_NATIVE_MESH_ISOLATION` 两条 collider 诊断路线。现在这两条路线均已完成，当前下一步是
`S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP`。

产品口径：F3/F4 不是被取消。之前先做 S2F5，是因为 S2F2 已经给出唯一 near-pass 候选，最短路径是先
验证它能否直接放行；现在 S2F5 复核失败，F3/F4 就从后备分支变成下一步主线。`s2f2_initial_layout_hash_audit`
仍然保留为解释背景：USD authored spawn position 是固定的，但 PhysX reset / settle 后 contact 参数会带来
轻微初始状态差异，因此 contact-offset 组只作为诊断证据，不直接升级为 release evidence。

S2F3 C3 SDF sweep 已完成：`fluid_spike_s2f3_c3_sdf_sweep_20260708.json` 覆盖 24 个 `C3A_*`
SDF 候选，系统 sweep `sdf_resolution=64/96/128`、`sdf_subgrid_resolution=4/8`、
`sdf_margin=0.002/0.005`、`sdf_narrow_band_thickness=0.01/0.02`，并固定
`mesh_bottom_fan_closure=true`、`normals_winding_audit=pass`。结果是
`STOP_WITH_EVIDENCE`，`reason=no_c3a_sdf_candidate_passed`，`best_for_s2f5=[]`，
`best_for_s3=[]`，`s3_kinematic_pour_released=false`。Artifact-level warning scan 未发现
`CPU collision fallback`、`GPU collider unsupported`、PhysX error 或 SDF warning；24 个候选都有
particle readback 和完整证据文件。失败主因不是 runtime/cooking 挂掉，而是所有 SDF 候选都
`FAIL_CONTAINER_LEAK`，最终 `below_table_count=256`，说明当前 procedural SDF open beaker 没有形成
可盛液体的有效内部碰撞空间。当时下一步只进入 `S2F4_C4_NATIVE_MESH_ISOLATION`，不释放 S3；现在
S2F4 已完成，当前下一步是 `S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP`。

S2F4 C4 native mesh isolation 已完成：`fluid_spike_s2f4_c4_native_mesh_isolation_20260708.json`
覆盖 3 个 `C4A_*` 候选，并把旧 C4 的混杂问题拆开验证：
`C4A_convexDecomposition_reference_scope_closed` 使用原生 `/World/beaker2` parent-scope reference、
local blue-glass material override 和 `convexDecomposition`；`C4A_sdf_reference_scope_closed`
使用同样的 scope-closed native reference 和 `sdf_resolution=128`；`C4A_native_render_mesh_plus_proxy_collision`
保留原生 render mesh，但关闭 native mesh collision，并在 `/World/SourceContainer/ProxyCollision`
下加 24-wall proxy collider。结果是 `STOP_WITH_EVIDENCE`，
`reason=native_beaker_not_fluid_safe_collider`，`native_beaker_fluid_safe_collider_status=NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER`，
`best_for_s2f5=[]`，`best_for_s3=[]`，`s3_kinematic_pour_released=false`。两个 direct native
routes 都是 `source_retention_fraction=0.0`、`below_table_count=256`；proxy-wrapper route
更接近但仍为 `source_retention_fraction=0.953125`、`outside_source_count=12`、`spill_count=12`，
没有通过 zero-leak gate。

S2F4 runtime warning scan 没有发现 `CPU collision fallback`、`GPU collider unsupported`、
PhysX error、SDF warning 或 material binding scope warning；只有 headless window warning。
因此这次 STOP 不是旧 material scope warning 或 cooking failure，而是 particle readback 证明碰撞空间仍会漏。
视觉 review 结论：direct native 两张 terminal diagnostic frame 为 `PASS`，红色 below-table leak 点清楚；
proxy-wrapper terminal frame 为 `WARN`，图像非空且 source region 可识别，但粒子颜色和 proxy 底线接近，
只能作为诊断图，不能升级成产品级 render。

Colleague liquid USD bounded leak smoke 已完成：`fluid_spike_colleague_liquid_usd_leak_smoke_20260708.json`
记录对同事提供的
`outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd`
做的受控漏液诊断。该文件原始 `/World/ParticleSet` 有 `50000` 个 authored positions；本次没有修改原 USD，
而是确定性抽样 `512` 个点，保留 authored particle width `0.0005940000992268324`，在 IsaacSim41 headless
minimal native beaker slice 中重新 author 为红色 PBD particles，并用 `native-proxy-wrapper` 碰撞路线 step
`120` 帧。结果为 `classification=FAIL_CONTAINER_LEAK`：第 0 步 `source_count=512`，终态
`source_count=150`、`outside_source_count=362`、`below_table_count=362`、`target_count=0`、`spill_count=0`、
`particle_count_final_fraction=1.0`、`nan_count=0`、`readback_position_changed=true`、
`max_displacement=0.19574435605145393`。

对应 artifacts：

```text
fluid_spike_colleague_liquid_usd_leak_smoke_20260708.json
fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/runtime_smoke_summary.json
fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/particle_readback_trace.jsonl
fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/colleague_liquid_leak_red_side_projection.mp4
fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/projection_frames/frame_0000.png
fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/projection_frames/frame_0060.png
fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/projection_frames/frame_0120.png
fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/minimal_native_beaker_slice.usda
```

这条证据的 PM 口径是：同事 USD 的初始液体点位读入正确，但在这次 bounded PBD/readback smoke 中，
source beaker 没能稳定装住这些粒子。它只释放 `512` 粒子采样 smoke 的 leak 诊断，不释放原始 `50000`
粒子完整 runtime claim、产品级 RGB render、S3 倒液、S4 Franka replay、EBench score、policy score 或
leaderboard claim。红色视频是对准 source beaker 的 diagnostic side projection，不是最终视觉效果。

Colleague raw 50k liquid USD D0 direct-step readiness audit 已完成，且
`runtime_step_executed=false`：
`fluid_spike_colleague_raw_usd_direct_step_audit_20260708.json` 记录对同一份
`lab_001_level1_pour_tabletop_with_liquid.usd` 的 immutable raw audit。D0 不重新 author particles、
不添加 `PhysxPBDMaterialAPI`、不换红色诊断粒子、不加 wrapper collider，只检查原文件是否已经满足
IsaacSim41 直接按真实 PBD fluid step 的最小 runtime contract。结果为
`classification=STOP_RAW_RUNTIME_INCOMPLETE`，`direct_original_50k_runtime_claim_allowed=false`：
原始 `/World/ParticleSet` 有 `50000` 个 points，`/World/ParticleSystem` 和 relationship 存在，
`gpu_dynamics_authored=true`，但缺少 `PhysxPBDMaterialAPI`，且 `PhysicsScene` 重力为
`gravity_direction=(0,0,0)`、`gravity_magnitude="-Infinity"`，并记录
`gravity_invalid_reasons=["zero_gravity_direction", "nonfinite_gravity_magnitude"]`。因此这份 raw USD
只能说“包含液体初始点位”，不能说“原始 50k 已经可直接 step 成 benchmark-ready 真实液体”。

D0 的 `particle_count_final_fraction=1.0`、`nan_count=0`、`readback_position_changed=false`
属于 no-step static snapshot 字段，不是 post-timeline survival evidence。因为 raw runtime contract
已经不完整，runner 记录 `step_skipped_reason=raw_runtime_contract_incomplete`，并把
`warning_scan_status` 标为 `not_run_due_to_raw_contract_stop`。

对应 artifacts：

```text
fluid_spike_colleague_raw_usd_direct_step_audit_20260708.json
fluid_spike_colleague_raw_usd_direct_step_audit_20260708_001/runtime_smoke_summary.json
fluid_spike_colleague_raw_usd_direct_step_audit_20260708_001/raw_particle_readback_trace.jsonl
```

Colleague 50k completed-PBD static leak evidence 已完成：
`fluid_spike_colleague_50k_completed_pbd_static_leak_20260708.json` 记录的是 D1-D3 诊断路线，
不是 raw USD direct-step。它把同事 raw USD 里的 `/World/ParticleSet` 当成 initial-condition data，
使用全部 `50000` 个点位，在 IsaacSim41 运行时补齐有效 `ParticleSystem`、`ParticleSet`、PBD material、
GPU dynamics 和 readback 设置，然后静置 step `120` 帧。结论是 `classification=FAIL_CONTAINER_LEAK`：
`particle_scope=full_original_50k`、`full_original_50k_completed_pbd_overlay=true`、
`runtime_step_executed=true`、`readback_position_changed=true`、`particle_count_final_fraction=1.0`、
`nan_count=0`，但终态 `outside_source_count=36013`、`below_table_count=36013`、
`source_retention_fraction=0.27974`。这正是当前领导展示需要的证据：补全 PBD 物理后，静置就会漏。

对应 artifacts：

```text
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708.json
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/runtime_smoke_summary.json
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/particle_readback_trace.jsonl
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/colleague_liquid_leak_red_side_projection.mp4
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/colleague_liquid_static_leak_rgb_camera.mp4
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/rgb_camera_frames/frame_0120.png
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/projection_frames/frame_0120.png
fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/minimal_native_beaker_slice.usda
fluid_spike_colleague_50k_completed_pbd_static_leak_visual_review_20260708.json
```

RGB review camera 是真实 IsaacSim41 camera 证据：`colleague_liquid_static_leak_rgb_camera.mp4`
可打开，`13` frames、`960x540`、`15 fps`。独立视觉 review 对终帧 `frame_0120.png` 判定为 `PASS`：
杯子居中可识别，杯底外侧红色漏出区域清楚。红色 D3 review markers 来自同一步的
`particle_readback_positions`，只是给人看的非碰撞标记，不参与物理；漏液判定仍以
`particle_readback_trace.jsonl` 和 region counts 为准。

这条 evidence 允许说：

```text
colleague_50k_completed_pbd_static_leak_run_executed=true
colleague_50k_completed_pbd_static_leak_classification=FAIL_CONTAINER_LEAK
colleague_50k_completed_pbd_static_leak_particle_scope=full_original_50k
colleague_50k_completed_pbd_static_leak_below_table_count=36013
colleague_50k_completed_pbd_static_leak_real_rgb_camera_available=true
```

仍然禁止说：

```text
raw_50k_colleague_liquid_usd_can_direct_step_as_true_pbd_fluid
completed_pbd_static_leak_equals_benchmark_ready_fluid
real_rgb_review_marker_equals_physical_fluid_mesh
s3_kinematic_pour_released
fluid_score_claim_allowed
```

Colleague full native USD 50k completed-PBD step video 已完成：
`fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708.json` 记录的是更强的
D3N/D4N 证据线。它不是 minimal native beaker slice，而是直接打开同事提供的完整入口
`lab_001_level1_pour_tabletop_with_liquid.usd`，在原生桌面布局里使用全部 `50000` 个 authored
particle positions 作为 initial-condition data，并在运行时补齐 `/World/CompletedPBD/ParticleSystem`
和 `/World/CompletedPBD/ParticleSet`。原始 raw USD 不被修改；原始不完整的 `/World/fluid`、
`/World/ParticleSet` 和 `/World/ParticleSystem` 只在 runtime session 中 deactivate，避免把 raw
incomplete contract 和 completed-PBD overlay 混在一起。

关键结果：

```text
runtime_step_executed=true
native_scene_opened=true
particle_scope=full_original_50k
selected_particle_count=50000
runtime_pbd_completion_overlay_used=true
classification=FAIL_CONTAINER_LEAK
outside_source_count=46301
below_table_count=46301
source_retention_fraction=0.07398
particle_count_final_fraction=1.0
nan_count=0
readback_position_changed=true
max_displacement=3.258722390681572
```

这条 evidence 的材质处理也已登记：`material_closure_mode=isaacsim41_core_mdl_local_mirror`，
把 `/isaac-sim/kit/mdl/core` 下的 core MDL 依赖 mirror 到 evidence artifact 目录，并把 native
`info:mdl:sourceAsset` retarget 到 local mirror。runtime log 扫描为 `mdl_compile_status=PASS`。
其中 `/World/Looks/OmniSurface_Glass/Shader` 使用
`OmniSurface_Glass_to_OmniGlass_for_isaacsim41` compatibility fallback。它解决的是 IsaacSim41
runtime 可编译/可渲染问题，不释放 `LabUtopia51 native visual material parity`。

对应 artifacts：

```text
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708.json
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/runtime_smoke_summary.json
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/particle_readback_trace.jsonl
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/native_scene_completed_pbd_overlay.usda
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/beaker2_closeup_native_material.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/beaker2_closeup_review_markers.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/camera1_native_material.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/camera2_native_material.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/material_closure_isaacsim41_core/
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_visual_review_20260708.json
```

视觉 review 是 `WARN`：closeup end frame 能支持“failed containment / leak”叙事，但 first usable
early closeup frame 的红色粒子团会像实体红块，Camera1/Camera2 太远，只能作为原生桌面上下文。产品展示时应使用
`beaker2_closeup_native_material.mp4` 作为主视频，`beaker2_closeup_review_markers.mp4` 只作为
readback 粒子位置诊断，不把 marker 当真实 fluid mesh。

这条 evidence 允许说：

```text
colleague_native_usd_50k_completed_pbd_step_video_recorded=true
colleague_native_usd_50k_completed_pbd_classification=FAIL_CONTAINER_LEAK
colleague_native_usd_50k_completed_pbd_below_table_count=46301
colleague_native_usd_50k_material_closure=isaacsim41_core_mdl_local_mirror
colleague_native_usd_50k_mdl_compile_status=PASS
colleague_native_usd_50k_visual_review=WARN
```

仍然禁止说：

```text
raw_50k_colleague_liquid_usd_can_direct_step_as_true_pbd_fluid
completed_pbd_static_leak_equals_benchmark_ready_fluid
marker_video_equals_physical_fluid_mesh
native_visual_material_parity_complete
s3_kinematic_pour_released
fluid_score_claim_allowed
```

Colleague full native USD 50k completed-PBD long video evidence 已完成：
`fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708.json` 是短版 native
step video 的 20 秒复跑版本。它使用同一个 full native USD、同一个 `50000` 粒子 initial condition、
同一个 `/World/CompletedPBD/*` runtime overlay 和同一个 IsaacSim41 core MDL local mirror material closure。

关键结果：

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

对应 artifacts：

```text
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708.json
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/runtime_smoke_summary.json
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/particle_readback_trace.jsonl
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/beaker2_closeup_native_material.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/beaker2_closeup_review_markers.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/camera1_native_material.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/camera2_native_material.mp4
fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_visual_review_20260708.json
```

视觉 review 是 `WARN`：长版 closeup 满足 20 秒展示需求，且能看到原生材质场景和红色液体/粒子团随 step
塌落；但 below-table leak 主要由 readback 证明，native closeup 画面本身不能单独证明所有 below-table
粒子。产品展示时主视频使用 `beaker2_closeup_native_material.mp4`，marker 视频只作为 readback 诊断。

`eos2_expert_oracle_s2_readback_render_inventory_20260706.json` 和
`eos2_expert_oracle_s2_claim_review_20260706.json` 是 S1R-D fresh S1 之后的 no-new-live S2 证据盘点和声明复核。
结论是 `S2_BLOCKED_READBACK_RENDER_EVIDENCE_GAP_NO_NEW_LIVE_RELEASE`：官方 `score=1.0` 候选分成立，但当时
artifact 没有 DryingBox `RevoluteJoint` 初末角、metric input dump、success counter trace 或终态正面渲染图。
它允许 claim M1 pass / positive official score candidate，不允许 claim S2 complete、M3 complete 或
`Expert Oracle Score complete`。这条旧结论已被 S2-R1E result review supersede：S2-L1 和 S2-L1R
分别用于暴露 evidence/export 与 execution-env 合约缺口；最新 `_003` run 已补齐 M3 单集 score/readback
证据。S2-I0 runner instrumentation code checkpoint、S2-R0 release review、S2-I1 evidence export repair、
S2-I2 metric producer repair、S2-I3/I4/I5 环境修复仍作为追溯证据保留。

`eos2_expert_oracle_s2_instrumented_replay_stop_go_20260706.json` 是上述 replay 之前的更细 stop-go 规则，
计划文档是
[`../../superpowers/plans/2026-07-06-eos2-s2-instrumented-replay-stop-go.md`](../../superpowers/plans/2026-07-06-eos2-s2-instrumented-replay-stop-go.md)。
当前状态已更新为 S2-L1 score pass / evidence failure，且 S2-I1 no-live evidence export repair code
checkpoint 已完成：
`eos2_expert_oracle_s2_instrumented_replay_code_checkpoint_20260706.json` 记录 GenManip runner 现在能记录
terminal obs、DryingBox door angle、metric input / `succ_cnts` 和 terminal/front-view render 所需的取证接口。
S2-R0 release review 已完成并被 S2-L1 消费；S2-L1 authoritative `result_info.json` 为 `score=1.0` /
`success_rate=1` / `metric_score=[[[1.0]]]`，但 `terminal_obs_compact.json` 的 `obs_keys=[]`、
`debug.labutopia_open_door=null`，terminal camera artifact 缺失，runner log 有 567 次
`No camera frames provided for this step`。因此已执行 S2-I1 no-live evidence export contract repair。
`eos2_expert_oracle_s2_i1_evidence_export_contract_repair_20260706.json` 记录修复结果：`EvalClient.step_chunk`
现在透传 `render_mode/subframes`；`EvalClient._resolve_pending_resets` 不会在 client 侧轮询 async reset result
时丢掉 `terminal_obs`；worker pending reset response 可以保留 done-step `terminal_obs`；runner 会从
`terminal_obs` 写 terminal readback、camera2 artifact、metric input 和 `succ_cnts`；worker_pool `step_chunk`
不会再把 ready pending reset result 消费后丢掉；`render_mode=always` 不再静默 fallback 到旧 client 签名。
S2-I1 不释放 live。S2-R1 post-repair replay release review 随后执行，结论是 blocked / no-live：
`eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json` 确认当时 live debug/metric producer
还不会自己产出 metric input / `succ_cnts`，runner 只是“有就保存”。因此没有释放 S2-L1R，而是转入
S2-I2。`eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json` 记录 S2-I2 no-live
修复：`MetricsManager` 现在保留刚判分的 metric debug snapshot，`debug.labutopia_open_door` 会导出
`CheckJointAngle(obj_DryingBox_01/RevoluteJoint)` 的 `metric_input`、`succ_cnts`、`metric_success_counter`
和 `metric_score_snapshot`。`eos2_expert_oracle_s2_r1b_post_s2_i2_release_review_20260706.json` 签发了
exactly one S2-L1R post-repair evidence replay；该 replay 已执行但在 reset 前失败，结果见
`eos2_expert_oracle_s2_l1r_post_s2_i2_env_failure_result_20260707.json`。失败原因是 worker
`PYTHONPATH` 没包含 `/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src`，导致 `curobo.types.state`
导入失败；这是 execution contract failure，不是 expert route failure。S2-I3 环境合约修复见
`eos2_expert_oracle_s2_i3_curobo_env_contract_repair_20260707.json`，S2-R1C 准跑证见
`eos2_expert_oracle_s2_r1c_post_env_repair_release_review_20260707.json`。后续又登记了 Ray tmpdir 和
CUDA runtime / `ninja` 环境修复，最终结果见
`eos2_expert_oracle_s2_r1e_full_env_repaired_result_review_20260707.json`。当前不再执行 S2 replacement replay，
也不释放 S2-L2。

`eos2_expert_oracle_s2_instrumented_replay_release_review_20260706.json` 是 S2-R0 准跑审查。当时状态是
`RELEASED_EXACTLY_ONE_S2_L1_INSTRUMENTED_REPLAY_AFTER_CODE_CHECKPOINT_NO_LIVE_RESULT_YET`：它释放的 exactly one
S2-L1 instrumented replay 已经消费。S2-L1 使用同一份 Route B action source sha256
`fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`，server 端开启
`LABUTOPIA_ORACLE_DEBUG_OBS=1`，runner 端使用 `--step-chunk-render-mode always --step-chunk-subframes 2
--trace-final-obs`。实际结果见
`eos2_expert_oracle_s2_l1_instrumented_replay_result_20260706.json`：分数链路通过，但 terminal obs、door angle
和 terminal camera artifact 缺失，只能判 evidence failure，不能判 Expert Oracle route 失败。

`eos2_expert_oracle_s2_l1_instrumented_replay_result_20260706.json` 是 historical S2-L1 结果。给 PM 的白话结论是：
专家答案在正式 EBench 下又拿到 `score=1.0`，但“门角度截图和评分过程录像”没有被证据系统导出成功。
下一步不是继续跑；S2-I1 已经先把 `EvalClient.step_chunk` 的 `render_mode/subframes` 参数透传、episode done
时的 terminal observation 保留、terminal camera2/front-view artifact 绑定入口、metric input / `succ_cnts`
导出入口用 no-live tests 修到通过。S2-R1 审查发现 producer 还没闭环，所以没有放行 live；S2-I2 又把
metric producer snapshot 补到 no-live tests 通过。S2-R1B release review 固定的 S2-L1R 已执行，但
reset 前因 cuRobo env 缺口失败；S2-I3/R1C 完成环境修复和 replacement replay 准跑后，后续又关闭 Ray
tmpdir 与 CUDA runtime / `ninja` 环境缺口。最新 replacement live 结果已登记在
`eos2_expert_oracle_s2_r1e_full_env_repaired_result_review_20260707.json`。

下面的 S0 条目按时间记录 historical progression。早期条目里的 “S0 未完成 / action source missing”
是当时状态；当前 canonical 状态以后面的
`eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json` 和
`eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json` 为准，即 S0 已完成、
S1/M1 已通过，S2-L1 分数通过但 evidence-blocked，S2-I1 evidence export repair 已完成，S2-R1 release
review 因 metric producer 缺口 blocked，S2-I2 metric producer snapshot repair 已 no-live 通过，S2-R1B
release review 签发的 S2-L1R 在 reset 前因 cuRobo env 缺口失败，S2-I3/R1C 已完成环境修复和 replacement
replay 准跑，当前下一步是执行这唯一一次 replacement replay。

`eos2_expert_oracle_s0_action_source_freezer_code_checkpoint_20260706.json` 是 roadmap 下第一个 S0 code
checkpoint。它登记 GenManip 新增的 `score_oracle_action_source_freezer.py` 及测试，TDD RED/GREEN 后
focused `3 passed`，与 score-capable runner 合跑 `10 passed`。这份 manifest 只说明“冻结工具 ready”：
当前没有发现现成可冻结的真实 expert action JSONL，因此 `frozen_real_expert_action_source_exists=false`、
`score_claim_allowed=false`、`bounded_score_live_release_allowed_now=false`。下一步必须提供或生成真实
EBench-executable expert action source，再用 freezer 产出 `action_source_manifest.json`。

`eos2_expert_oracle_s0_action_source_exporter_code_checkpoint_20260706.json` 是同一 S0 下的 exporter code
checkpoint。它登记 GenManip 新增的 `score_oracle_action_source_exporter.py` 及测试，可以把 planner summary
里的 `trajectory_action_joint_positions` 转成 freezer-compatible replay JSONL。fresh verification 为 exporter、
freezer、score-capable runner 合跑 `13 passed in 0.04s`，`py_compile` 和 `git diff --check` exit 0。
这份 manifest 只允许 claim `diagnostic_trajectory_export_claim_allowed=true`：被导出的轨迹点仍是 replay
input，不会自动升级成真实 expert action source、live evidence 或 `Expert Oracle Score`。S0 的真正完成条件
仍是选定真实 expert/oracle 来源，导出并冻结成带 sha256 的 `action_source_manifest.json`。

`eos2_expert_oracle_s0_source_eligibility_audit_20260706.json` 随后审计了现有 evidence 里是否已经有可升级为
S0 的真实 expert action source。结果是 no-live audit / no eligible source：目录中有 75 个 JSON 含
`plan_success=true` 的 `trajectory_action_joint_positions`，共 33274 个轨迹点，但状态分布为 43 个
`FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`、18 个
`BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`、14 个
`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`。这些都可以作为 diagnostic replay input 的来源，
但不能升级为真实 expert action source。目录中也没有 `action_source_manifest.json`；唯一 `result_info.json`
来自 AAN runtime smoke，`score=0.0`、`success_rate=0`。因此 S0 仍未完成，S1 formal score-chain smoke
仍不释放。

`eos2_expert_oracle_s0_next_source_route_review_20260706.json` 把 eligibility audit 后的下一步路线固化为
A -> B -> C。A 是第一优先：生成或导出 deterministic Franka/native oracle replay JSONL，并用 freezer 冻结
成 `action_source_manifest.json`。A 做不到或后续 formal stop line 失败后，B 才单独开
`native_drive_target` / native controller contract research，且先保持 no-score。C 只能并行做
asset/task no-score hardening，不能替代 expert action source。当前
`s1_formal_score_chain_smoke_allowed_now=false`、`bounded_fallback_score_live_allowed_now=false`。

`eos2_expert_oracle_s0_deterministic_franka_source_code_checkpoint_20260706.json` 把 A 路线推进到
code-ready / no-live：新增 `utils/ebench_replay_action_source.py`、`tests/test_ebench_replay_action_source.py`，
并在 `main.py` 增加 opt-in `--ebench-action-log-dir`。TDD RED 为模块缺失，GREEN 后
`python -m pytest tests/test_ebench_replay_action_source.py -q` 得到 `6 passed in 0.04s`；`py_compile` 和
`git diff --check` exit 0。它只说明 candidate logger ready：还没有运行 LabUtopia native expert capture，
没有生成 `candidate_action_source.jsonl`，也没有 freezer 输出的 `action_source_manifest.json`。

`eos2_expert_oracle_s0_native_capture_attempt_20260706.json` 记录了随后唯一一次 bounded S0 native capture。
attempt1 是 wrong-python runtime，`isaacsim` import 失败；attempt2 使用 `labutopia-py311` 后进入
Isaac/LabUtopia，但因 `ValueError: action_dim_mismatch:7!=9` 停止。根因是 LabUtopia native open
controller 会混合输出 9D full Franka action 和 7D arm-only C-space action，而 logger 原先要求所有 raw
action 都已经是 9D。目录里只留下 1 条 partial `candidate_action_source.jsonl`，没有
`candidate_action_source_manifest.json`、没有 native success、没有 freezer manifest，所以不能 claim S0
完成，也不能进入 S1。

`eos2_expert_oracle_s0_action_dim_contract_repair_code_checkpoint_20260706.json` 是上述 capture 后的 zero-live
repair checkpoint。`utils/ebench_replay_action_source.py` 现在支持显式
`allow_prefix_joint_positions`；`main.py` 增加 `--ebench-action-allow-prefix-dim`。默认行为仍 strict；只有显式开启时，
7D arm-only prefix 才会用 observed tail joints 补成 9D，并写入 `raw_action_dim`、`observed_joint_dim` 和
`normalization=prefix_action_expanded_with_observed_tail`。TDD RED 为 2 failed / 5 passed，GREEN 后
`7 passed in 0.11s`，`py_compile` exit 0。这是 code-ready / no-live / no-freeze；任何新 capture 都必须先做
新的 bounded live release review。

`eos2_expert_oracle_s0_prefix_repair_validation_release_review_20260706.json` 随后释放 exactly one
prefix-dim repair-validation capture；结果登记在
`eos2_expert_oracle_s0_prefix_repair_validation_capture_result_20260706.json`。这次 live exit 0，并证明
prefix expansion 在 runtime 中生效：968 条 action 全部为 9D，其中 664 条由 7D raw action 扩展而来。
但 manifest 是 `success_observed=false`，stdout 显示第 9 次才 `Task success!`。因此不能 freezer：
logger 记录并 finalize 了第一个 failed episode，而不是后面的 successful episode。

`eos2_expert_oracle_s0_logger_lifecycle_repair_code_checkpoint_20260706.json` 是后续 zero-live lifecycle 修复。
`EbenchReplayActionLogger` 新增 `discard_episode()`；`main.py` 在 `done && is_success=false` 时丢弃当前
candidate JSONL，只有 `is_success=true` 才 finalize。TDD RED 为缺 `discard_episode`，GREEN 后
`8 passed in 0.05s`，`py_compile` exit 0。它仍不释放 live/freezer/S1；下一步需要新的 bounded live
release review 来验证 successful episode capture。

`eos2_expert_oracle_s0_lifecycle_validation_release_review_20260706.json` 释放 exactly one lifecycle-validation
capture，最终冻结成功登记在
`eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json`。这份 evidence 是当前 S0 闭合证据：
capture exit 0，candidate manifest `success_observed=true`、`discarded_episode_count=1`；最终 action source
有 905 条连续 9D `joint_position`，601 条由 7D raw action prefix 扩展而来。freezer manifest 为
`PASS_SCORE_ORACLE_ACTION_SOURCE_FREEZE`，source/frozen sha256 均为
`e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f`。允许 claim：
`frozen_real_expert_action_source_exists=true`、`s0_completed=true`。仍然禁止 claim score、S1、policy、
leaderboard 或 project no-go。该段记录 S0 freeze 当时状态；S1 release review 后续已执行，当前以
attempt2 partial result 和 S1R repair plan 为准。

`eos2_expert_oracle_s1_s4_stop_go_refresh_20260706.json` 是 S0 闭合后的 no-live planning refresh。它把
roadmap 的执行起点从“还缺 frozen expert action source”更新为“从 S1 formal score-chain smoke 开始”：
S1 最多两次 bounded attempt，必须产出 authoritative `episode_result.score` 和匹配的 `result_info.json`；
S2 才判断 Franka/native frozen source 是否能在 EBench metric 下得分；S3 才判断 Lift2 oracle / retarget；
S4 才做 3-5 episodes/seeds 稳定性。该 refresh 不释放 live 或 score claim，只允许说明
`s0_completed=true` 且后续 stop-go 起点已更新。

`eos2_expert_oracle_s1_formal_score_chain_release_review_20260706.json` 释放 exactly one S1 bounded live
attempt。它固定 frozen config、S0 `action_source.jsonl`、Gate1V-2c `score_capable_oracle_runner.py`、
IsaacSim41 GenManip py310 环境、端口 `18130`、`run_id=eos2_s1_formal_score_chain_smoke_20260706_001`
和 `step_chunk_size=1`。这仍不是 live result，也不释放 score claim；它只允许执行一次 formal
score-chain smoke。S1 通过标准不是高分，而是同一 run 产出 authoritative `episode_result.score`、
匹配的 `result_info.json`、`action_log.jsonl` 和 `metric_trace.jsonl`。没有 `result_info.json` 时归为
runner/evaluator lifecycle blocker；`metric_score` 缺失或为空时归为 score artifact incomplete。

`eos2_expert_oracle_s1_formal_score_chain_attempt1_result_20260706.json` 记录 S1 attempt1 结果：
server health 正常，但 `/start_new_job` 因 absolute config path 被 allowed-directory guard 拒绝，
没有 reset/action/result_info。随后
`eos2_expert_oracle_s1_config_path_repair_release_review_20260706.json` 释放第二次也是最后一次
bounded S1 infra attempt，只允许把 config path 修成
`ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`。

`eos2_expert_oracle_s1_formal_score_chain_attempt2_result_20260706.json` 是当前 S1 最新结论：
attempt2 已经真实产出 client `episode_result.json`、client `result.json` 和 authoritative
`result_info.json`，其中 `score=0.0`、`success_rate=0`。但它只能算 partial S1 evidence，不能算
S1 pass：runner 使用了过深的 `--result-base-dir`，导致 artifact locator 找到了
`.../ebench/<run_id>/ebench/<run_id>/...` 这种重复路径并 exit `1`；同时
`result_info.log_info.metric_score=[]`，`action_log.jsonl` 只有 1 条，server 在 step 0 报
`Invalid robot state detected ... arm_state_jump_too_la`。所以当前不能说 expert 得分失败，只能说
S1 formal score-chain contract 尚未闭合。

`eos2_expert_oracle_s1r_result_locator_metric_score_repair_plan_20260706.json` 是 historical S1R stop-go 计划，
现已被 S1R-D fresh S1 pass 结果 supersede：S1R-A/B/B2/C/D 均已闭合，Route B fresh S1 已产出
`score=1.0` / `success_rate=1.0`。当前下一步不再是 S1R repair 或 S1 retry；S2-L1 instrumented replay
已执行并再次 `score=1.0`，但 terminal readback/render/metric-input evidence 缺失。S2-I1 no-live evidence
export repair 已完成；S2-R1 review 因 producer 缺口 blocked；S2-I2 metric producer snapshot repair 已完成。
S2-R1B review 签发的 S2-L1R post-repair evidence replay 已在 reset 前因 cuRobo env 缺口失败；
S2-I3/R1C 已完成环境修复和 replacement replay 准跑，当前还没有 replacement live result。
对应实施计划是
[`../../superpowers/plans/2026-07-06-eos2-s1r-score-chain-repair.md`](../../superpowers/plans/2026-07-06-eos2-s1r-score-chain-repair.md)。
该计划还记录了 attempt2 的 reset-to-first-action 最大关节跳变为 `2.734214574098587rad`，因此
step0 invalid state 很可能是 reset/action contract mismatch，不能直接解释成 expert 质量失败。

`eos2_expert_oracle_s1r_a_result_locator_code_checkpoint_20260706.json` 记录 S1R-A zero-live 修复已完成：
新增 fake-client regression 复现 `result_base_dir=.../saved/eval_results/ebench/<run_id>` 且
`episode_id=ebench/<run_id>/...` 时的重复前缀 bug。RED 明确失败在
`.../ebench/run/ebench/run/.../result_info.json`，GREEN 后 runner 支持
`run_specific_base_dir_compat`，并把 `result_info_locator_mode` 写回 summary 和 `score_artifact`
trace。focused test `1 passed`，runner test file `8 passed`。这只关闭 result locator contract；
`metric_score=[]` 和 step0 invalid-state 仍未闭，仍不释放 fresh S1 / S2 / score claim。

`eos2_expert_oracle_s1r_b_metric_score_policy_review_20260706.json` 记录 S1R-B zero-live 审计已完成，
但结论是 release blocked。多角度 review 后没有创建 S1-only waiver：attempt2 的 `result_info.json`
虽然有 `score=0.0` 和 `success_rate=0`，但 `episode_start_time=null`、`episode_end_time=null`、
`metric_score=[]`，这和 GenManip `ProgressManager._write_minimal_result_info` 的 minimal fallback
产物一致，不是 `EpisodeRecorder.finalize` 写出的完整 score-capable artifact。历史扫描 79 个
`result_info.json` 中，5 个非空 `metric_score` 全部有真实 start/end，74 个空 `metric_score` 全部
start/end 为 null；历史 readiness PASS 使用的是非空 `metric_score=[[[0.0]]]`。因此当前允许 claim
只有 “S1R-B policy review completed / empty metric_score is not accepted as M1 evidence”；仍禁止 claim
S1 pass、M1 pass、Expert Oracle Score、fresh S1 release 或 project no-go。

`eos2_expert_oracle_s1r_b2_full_finalize_lifecycle_code_checkpoint_20260706.json` 记录 S1R-B2 no-live
code checkpoint 已完成。TDD 先用轻量 helper contract RED 到缺
`should_skip_post_episode_process`，GREEN 后 `post_episode_process` 只有在 done 且 recorder 已不存在时才跳过；
done 但 recorder 仍存在的 terminal episode 可以继续构造 `finalize_payload`，避免退化到 minimal fallback
writer。focused tests `2 passed`，episode-result + score-capable runner 组合 `15 passed`，`py_compile`
通过。它仍不是 live evidence，不能 retroactively 修复 attempt2 的空 `metric_score`；fresh S1 release
在该 checkpoint 当时仍要等 S1R-C step0 invalid-state attribution 和 S1R-D release review；后续 S1R-C/D
已经完成，见下面两条。

`eos2_expert_oracle_s1r_c_step0_invalid_state_attribution_20260706.json` 记录 S1R-C zero-live 归因已完成。
attempt2 的 EBench reset arm joint 和第一条 frozen expert action target 不在同一个起点邻域：最大差值
`2.734214574098587rad`，发生在 joint6；joint4 也有 `2.577224478125572rad`。GenManip
`detect_invalid_robot_state` 的 arm per-step delta limit 是 `1.0rad`，所以 step0 触发
`arm_state_jump_too_large` 是 reset/action contract mismatch 的预期结果，不是 expert 不会开门。
路线选择为 `S2_ROUTE_B_PREPEND_BOUNDED_SETTLE_BRIDGE`：保留原始 S0 frozen expert source 不变，在 replay
前加一段 provenance 分开的 bounded settle/bridge，把机器人从 EBench reset 平滑带到 frozen source
起点附近。该段记录 S1R-C 当时状态；后续 S1R-D 已完成 release review，见下一条。

`eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706.json` 记录 S1R-D release review 已完成。
它释放 exactly one Route B fresh S1，不是 live result，也不释放 score claim。Route B bridge artifact 位于
`eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706/bridged_action_source/action_source.jsonl`：
前 14 步是 `s1r_route_b_settle_bridge`，后 905 步是原始 S0 frozen expert replay；总动作数 919，
9D `joint_position`，bridged source sha256 为
`fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`。bridge manifest classification 是
`PASS_S1R_ROUTE_B_BRIDGED_ACTION_SOURCE_BUILD`，freezer validation 是
`PASS_SCORE_ORACLE_ACTION_SOURCE_FREEZE`，最大 bridge 单步跳变 `0.19530104100704193rad`，低于
`1.0rad` invalid guard。fresh S1 的唯一允许 run_id 是
`eos2_s1r_d_route_b_bridge_fresh_s1_20260706_003`，端口 `18132`，config path 必须是相对路径
`ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`，`--result-base-dir` 必须是 canonical
`/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results`，不能使用
`saved/eval_results/ebench/<run_id>`，也不能提供 empty-`metric_score` waiver。若 fresh S1 后仍缺
`result_info.json`、`metric_trace`、`action_log` 或非空 `metric_score`，停止 oracle scoring 并按
runner/evaluator lifecycle 或 Route B bridge contract blocker 归因。

`eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json` 记录上述 exactly one fresh S1 的
live result：有效 runner invocation exit `0`，`summary.json` classification 为
`PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT`，canonical `result_info.json` 的 sha256 是
`34294f17633802a8faf6a806483cfaf827ebac97ff74e83cbce230e7676d2f4f`，其中 `score=1.0`、
`success_rate=1`、`log_info.metric_score=[[[1.0]]]`，并有非空 `episode_start_time` /
`episode_end_time`。same-run `action_log.jsonl` 有 578 条：前 14 条是
`s1r_route_b_settle_bridge`，后 564 条是 `labutopia_native_articulation_action`；same-run
`metric_trace.jsonl` 有 578 个 `step_chunk` 和 1 个 `score_artifact`。同目录的
`runner.exit_code=1` 是 prelive launcher 失败，没有 start_job/reset/action/result artifact；正式结论以
`runner_attempt2.exit_code=0` 为准。允许 claim：S1/M1 formal score-chain pass，以及 Route B bridged expert
replay 出现 positive score candidate。禁止 claim：S2/M3 complete、small-sample robustness、workflow
ready for expansion、policy score、official leaderboard readiness 或所有资产/任务都可评。

`eos2_expert_oracle_stop_go_review_20260706.json` 是 attempt2 之前的多角度 stop-go 审阅记录。技术审阅和
产品审阅结论一致：当时还没到 S1，路线 blocker 是 real expert action source 未冻结；最早的 capture
失败只是环境入口问题，stderr 为 `ModuleNotFoundError: No module named 'isaacsim'`，不是 expert、metric、
retarget 或 DryingBox route 失败。随后 `labutopia-py311` 加 `OMNI_KIT_ACCEPT_EULA=YES`、
`env -u OMNI_SERVER` 已验证 `import isaacsim` 通过，并释放 exactly one S0 capture；后续 attempt2 又把
blocker 收窄到 action-dim contract mismatch，见上面的 native capture attempt manifest。该 review manifest 只允许 claim
`environment_import_smoke_passed=true` 和 `single_s0_capture_release_recommended=true`；仍不释放 live、
score、policy、leaderboard 或 project no-go claim。后续 attempt budget 固定为：S0 最多一次
`max_episodes=1` capture；S1 最多两次 formal score-chain smoke；S3 最多
2 个 mapping families x 2 个 critical variants；S4 只做 3-5 episodes/seeds 稳定性。

## 2026-07-06 Gate 1T Contract-Fork Review

Gate 1R + Gate 1S 已经把当前精确定义合同推进到 bounded no-go 建议点。下一步不是继续扫 offset，
而是新开 Gate 1T contract fork，优先验证 `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR`。PM 侧可以理解为：
当前这套 `Franka + 当前任务布局 + mesh-open-face near route` 已经不建议继续硬调；如果继续，就要换一条
EBench-native route generator 合同。Gate 2/contact/micro-pull/`Expert Oracle Score` 在新的 Gate 1
pass 之前继续 blocked。

新的结构化 review manifest 是
`eos2_gate1t_contract_fork_review_20260706.json`，状态为
`PREPARED_GATE1T_CONTRACT_FORK_REVIEW_NOT_LIVE_EVIDENCE`。它冻结三条证据：
Gate 1R 的 `BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS`、
Gate 1S review 的 `max_selected_live_strategy_count=1`、以及 Gate 1S selected live 的
`BLOCKED_GATE1S_SELECTED_STRATEGY_NO_NEAR_REACHABILITY`。允许结论只到“当前精确定义合同没有产生
scoring-eligible expert route”；不能扩大成 DryingBox 全局打不开、LabUtopia 资产不能进 EBench、
`Expert Oracle Score` 失败、official score 失败或所有机器人/布局/route generator 都不可行。

下一阶段计划是
[`../superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md`](../../superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md)。
优先 lane 是 `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR`：保持 Franka、当前 layout、DryingBox 资产和
EBench metric 不变，只把 route authoring 改成 EBench `microwave` 风格的 `custom_motion`：
`robot_frame` staging + `object_frame` DryingBox waypoints，由 runtime/curobo 逐段现算。硬边界是
`max_native_pattern_routes=3`、`max_selected_live_route_count=1`；如果这条 lane 失败，下一步只能转
`A_LIFT2_ROBOT_CONTRACT_FORK`、`B_TASK_LAYOUT_CONTRACT_FORK` 或 `W_FINAL_BOUNDED_NO_GO`，不能在当前
Franka/current-layout/native-route lane 里继续加 offset。

Gate 1T-C0 / C1 已准备好。`eos2_gate1t_native_oracle_pattern_extraction_20260706.json`
记录了 EBench `microwave` 的 native pattern：`custom_motion` 里混合 `object_frame`、`robot_frame`
和 `pending`。`eos2_gate1t_native_pattern_route_candidates_20260706.json` 预注册了 3 条候选：
`C1_ROOT_DIRECT_NATIVE_PATTERN`、`C2_ROOT_STAGED_CORRIDOR_NATIVE_PATTERN`、
`C3_REVERSE_REACHABILITY_ROOT_PATTERN`。后续 C2b live 证明，C1 里使用的
`rel_object_uid=obj_DryingBox_01` root 在当前 LabUtopia articulated-object setup 后不在
`scene.object_list`，所以 root-object-frame 路线不能被 native `custom_motion` resolver 直接消费。
这个发现修正了 C1 的 resolver 假设，但不是 route-generator no-go。

2026-07-06 C2a runner capability audit 又收紧了一步，并已推进到 code-ready：
`eos2_gate1t_c2_runner_capability_audit_20260706.json` 当前状态是
`CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE`。通俗讲，GenManip 里现在已经有
一个最小 runner，可以把选中的 task-level `custom_motion` route 解析、规划、转成 EBench
`joint_position` action chunk，并通过 `step_chunk` 的 fake-client contract 验证。对应代码是
`standalone_tools/labutopia_poc/native_action_path_runner.py`，测试是
`tests/labutopia_poc/test_native_action_path_runner.py`；验证结果包括 `5 passed` 的 runner 单测和
`29 passed` 的相邻 planner contract 组合测试。runner 现在还接受 `--run-id`，会把 run_id 写入
summary，避免 C2b live 输出和 server submit/job logs 混淆。

2026-07-06 C2b live 已执行：
`eos2_gate1t_native_pattern_route_live_20260706/` 固定了选中 route
`C1_ROOT_DIRECT_NATIVE_PATTERN`、run_id
`eos2_gate1t_c2b_c1_root_direct_native_pattern_20260706_0001`、端口 `18107`、单任务配置
`ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`。compact result 是
`LIVE_BLOCKED_RESOLVER_MISMATCH_NOT_ROUTE_NO_GO`：runner 打到了 live Isaac / EBench，但
`robot_frame` 当时 unsupported，`obj_DryingBox_01` root object-frame not found，`executed_steps=0`。
因此 C2b 只能证明 resolver contract 未闭合，不能证明 near reachability no-go、contact、micro-pull、
door-open、`Expert Oracle Score` 或 score。

2026-07-06 C2c resolver-closure live 也已执行：
`eos2_gate1t_c2c_resolver_closure_live_20260706/` 固定了 route
`C1_RESOLVER_CLOSED_HANDLE_FRAME_NATIVE_PATTERN`、run_id
`eos2_gate1t_c2c_resolver_closed_c1_handle_frame_20260706_0001` 和端口 `18108`。这次
`robot_frame_staging_microwave_style` 成功并生成 `44` 个 action points，两个
`obj_DryingBox_01_handle` object-frame target 也成功解析；失败点进入 planner reachability：
`handle_object_staging_085` 和 `handle_object_near_045` 都是 `MotionGenStatus.IK_FAIL`、
`trajectory_point_count=0`，所以 `executed_steps=0`、Gate 2/contact 和 `Expert Oracle Score`
继续 blocked。compact result 是
`LIVE_BLOCKED_REACHABILITY_AFTER_RESOLVER_CLOSURE_TARGET_EQUIVALENCE_UNPROVEN`。

2026-07-06 C2d target-frame equivalence audit 已写入
`eos2_gate1t_c2d_target_frame_equivalence_audit_20260706.json`。它是不启动 Isaac 的只读审计：
C2c handle local `Y+` 在 live 中映射到 world `X+`，C2c near target 距离 mesh/open-face 参考的
handle-front approach-near target 约 `0.1116m`。因此当前严谨结论是：C2c 证明 resolver closure
和一个真实 IK-layer failure，但还没有证明这个 target 等价于我们想验证的正面把手前方目标。
下一步只能按
[`../../superpowers/plans/2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md`](../../superpowers/plans/2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md)
推进：如果 C2d 证明等价，C lane 可停止；如果不等价，C2e 先补 raw resolver / adjusted-target dump
并推导等价 local 坐标。

2026-07-06 C2e resolver dump 已执行：
`eos2_gate1t_c2e_resolver_dump_live_20260706/`。runner 的旧 route 分类仍是
`BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`，但这次接受的不是 route 结果，而是
`target_resolver_debug` 证据：它把 `obj_DryingBox_01_handle` 的 `frame_in_world`、raw target 和
adjusted target 分开记录。随后
`eos2_gate1t_c2e_equivalent_target_coordinate_derivation_20260706.json` 已推进为
`PASS_C2E_EQUIVALENT_TARGET_COORDINATES_DERIVED_READY_FOR_C2F_SINGLE_LIVE`。通俗讲：我们已经能把
“真实正面把手前方目标”反算成 EBench object-frame local coordinate，并 forward-check 回原目标，误差约
`5.55e-17m`，低于 `0.01m` 门槛。orientation 边界是：C2f 保持 native route gripper orientation，
它和 C2e live adjusted orientation 完全一致，但和旧 mesh-open-face runtime orientation 相差约
`90deg`。这仍不是 route pass，只是证明下一次 live 不是盲调；若 C2f 失败，只能停止当前
native-route orientation 合同，不能宣称所有姿态都不可达。

下一步唯一允许的 live 节点单独命名为 C2f：
`eos2_gate1t_c2f_equivalent_target_live_20260706/`，route manifest 是
`eos2_gate1t_c2f_equivalent_target_route_candidates_20260706.json`。C2f 只跑一条
`C1_RESOLVER_CLOSED_EQUIVALENT_TARGET_NATIVE_PATTERN`。现在 C2f 已执行并写入 compact result：
`eos2_gate1t_c2f_equivalent_target_live_20260706/result_compact.json`，status 为
`LIVE_BLOCKED_C2F_EQUIVALENT_TARGET_IK_FAIL_STOP_C_NATIVE_ROUTE_CONTRACT`。关键事实是：
`robot_frame` staging 成功，等价 `approach_near` adjusted target 精确落到
`[0.4797899613973845, 0.3107189912618622, 1.1085915534527668]`，但该目标仍
`MotionGenStatus.IK_FAIL`，没有 action points，也没有执行步数。因此
`C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR` 已按预注册规则停止；下一步推荐
`A_LIFT2_ROBOT_CONTRACT_FORK`，因为它直接验证 official Lift2 baseline 口径。`B_TASK_LAYOUT_CONTRACT_FORK`
是后续 fallback，`W_FINAL_BOUNDED_NO_GO` 是最后停止项。

2026-07-06 Gate 1U-A Lift2 fork review 已建立：
`eos2_gate1u_lift2_contract_fork_review_20260706.json`，计划文档是
[`../../superpowers/plans/2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md`](../../superpowers/plans/2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md)。
这一步先不算分，只验证 `manip/lift2/R5a`、16D action contract、camera/observation schema、step 和
metric fields。通过后才设计 Lift2 oracle / retarget；失败则归类为 Lift2 runtime/action contract
blocker，而不是 expert failure。

A0 static audit 已通过：
`eos2_gate1u_a0_lift2_static_contract_audit_20260706.json`。它确认
`lift2_candidate/level1_open_door.yml` 使用 `manip/lift2/R5a`、16D `joint_position` action、同一个
`obj_DryingBox_01/RevoluteJoint` door-angle metric，并声明历史 scene path / AAN-11 evidence 不能混用。
下一步允许 A1 单次 live schema/action probe。

A1/A1a/A1b/A1c 已形成完整证据链。A1 首次 live 停在
`LIVE_BLOCKED_A1_RESET_RESULT_PENDING_ASSETS_ROOT_OVERRIDE_MISSING_STOP_BEFORE_A2`，root cause 指向旧
overlay root 缺 `robot_usds/lift2/robot.usd`。A1a preflight 随后通过：
`eos2_gate1u_a1a_assets_root_reset_contract_20260706.json` 确认 effective assets root 为
`$GENMANIP_WORKTREE/saved/assets`，realpath 是 composite root，并且 Lift2 robot USD / R5a cuRobo
config / runtime scene 都存在。

A1b corrected live 证据是
`eos2_gate1u_a1b_lift2_live_schema_probe_corrected_20260706/result_compact.json`，状态为
`LIVE_BLOCKED_A1B_LOGGING_METADATA_INCOMPLETE_RUNTIME_ACTION_CONTRACT_PASSED_NEEDS_A1C`。它证明 reset
observation、camera keys、三种 16D action dialect 和 reward/success fields 都 PASS；唯一 blocker
是 logging fields 缺 `episode_id`、`seed`、`result_path`、`stdout_path`、`stderr_path`。

A1c logging-closed fresh live 证据是
`eos2_gate1u_a1c_lift2_live_schema_probe_logging_closed_20260706/result_compact.json`，状态为
`PASS_A1C_LIFT2_LIVE_SCHEMA_ACTION_LOGGING_PROBE_READY_FOR_A2_ORACLE_DESIGN`。它证明单任务 Lift2
schema/action/logging contract 可用，但不证明 route reachability、contact、door opening、
`Expert Oracle Score`、official score 或 Stage 7 aggregate pass。

A1a/A1b/A1c 的停止线已经写入
[`../../superpowers/plans/2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md`](../../superpowers/plans/2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md)：
A1a 预检不能证明 effective `ASSETS_DIR` 是 composite root，则不启动 Isaac；A1b corrected live
仍卡 reset 或 action dialect，则停止 A lane runtime contract；A1c 仍有 schema row blocked，则不进入
A2。现在 A1c 已通过，下一步允许 A2 Lift2 oracle / retarget design review。

A2 的 evidence 不应直接是 score 或 long live run。A2a 写 oracle path review，A2b 写 target/waypoint
static audit，A2c 写 translator dry contract。只有这三个零 live evidence 都通过，A3 才允许一次
selected Lift2 oracle live；A3 只测 Gate 1 near reachability，不跑 contact、micro-pull 或 score。

A2a/A2b/A2c 已新增：

| File | Stage | Status | 含义 |
|---|---|---|---|
| `eos2_gate1u_a2_lift2_oracle_design_review_20260706.json` | A2a Lift2 oracle path review | `PASS_A2A_LIFT2_SCRIPTED_ORACLE_SELECTED_READY_FOR_A2B_TARGET_WAYPOINT_AUDIT` | 选定 `LIFT2_SCRIPTED_ORACLE`，输出合同是 Lift2/R5a 16D `joint_position`，A2 不消耗 live budget。 |
| `eos2_gate1u_a2b_lift2_target_waypoint_static_audit_20260706.json` | A2b target/waypoint static audit | `PASS_A2B_DRYINGBOX_TARGET_WAYPOINT_STATIC_AUDIT_READY_FOR_A2C_TRANSLATOR_DRY_CONTRACT` | 固定 metric joint、handle frame、front approach pose、contact pose 和 pull intent；A3 只允许执行 front approach。 |
| `eos2_gate1u_a2c_lift2_translator_dry_contract_20260706.json` | A2c translator dry contract | `PASS_A2C_LIFT2_TRANSLATOR_DRY_CONTRACT_READY_FOR_A3_SINGLE_LIVE_PACKAGE` | dry 验证 16D action payload，并补 runner `--expected-action-dim 16` guard，阻止 7D Franka action 混入 Lift2 live。 |
| `eos2_gate1u_a2c_lift2_dual_arm_route_guard_addendum_20260706.json` | A2c addendum dual-arm route guard | `PASS_A2C_ADDENDUM_LIFT2_DUAL_ARM_REQUIRED_ARM_GUARD_READY_FOR_A3B_DRY` | 在 16D guard 之外补 `--required-arm right`，让缺 `arm` 或 `rel_arm=default` 的 Lift2 dual-arm route 在 reset 前失败。 |
| `eos2_gate1u_a3_lift2_oracle_single_live_20260706/result_compact.json` | A3 selected Lift2 oracle single live | `LIVE_BLOCKED_A3_LIFT2_ORACLE_PLANNER_UPDATE_UNAVAILABLE_STOP_BEFORE_GATE2` | A3 只跑一次；submit/reset 到位，但两条 waypoint 都是 `planner_update_unavailable`、0 action points、`executed_steps=0`。这不是 contact、door、score 或几何 no-go 证据。 |
| `eos2_gate1u_a3a_planner_update_root_cause_review_20260706.json` | A3a planner-update root-cause review | `REVIEW_A3A_LIFT2_DUAL_ARM_CONTRACT_BLOCKER_REVISE_A2C_A3_BEFORE_SECOND_LIVE` | 只读 review 指出当前 A3 route/summary 落成 `arm=default`，但 Lift2/R5a 需要 `left_planner` / `right_planner`。下一次 live 前必须显式选择 `arm=left|right` 并 dry-validate。 |
| `eos2_gate1u_a3b_lift2_right_arm_dry_contract_20260706/result_compact.json` | A3b revised right-arm dry contract | `PASS_A3B_LIFT2_RIGHT_ARM_DRY_CONTRACT_READY_FOR_REVISED_A3_SINGLE_LIVE` | 基于 EBench native microwave right-arm pattern，固定 revised route 为 `arm=right` / `rel_arm=right`，dry check 通过且 action 仍是 16D；只允许下一步一次 revised A3 live。 |
| `eos2_gate1u_a3c_lift2_right_arm_single_live_20260706/result_compact.json` | A3c revised right-arm single live | `LIVE_BLOCKED_A3C_LIFT2_RIGHT_ARM_START_STATE_WORLD_COLLISION_STOP_BEFORE_GATE2` | A3c 证明 `arm=right` route live planner dispatch 和 world refresh 已走通，但 cuRobo 在目标可达性前先报 `INVALID_START_STATE_WORLD_COLLISION` against table，`sphere_index=17`、0 action points、`executed_steps=0`。这不是 contact、door、score 或 Lift2 几何 no-go 证据。 |
| `eos2_gate1u_a3d_right_arm_start_state_collision_review_20260706.json` | A3d start-state collision review | `A3D_REVIEW_SUPERSEDED_BY_A3E_NO_GO_RESET_LAYOUT_COLLIDER_CONTRACT_REQUIRED` | 已从 A3c trace 提取 reset state 和 planner collision attribution；A3e 后续已补同 frame table/sphere clearance，并证明 A3f 不允许。仍缺 sphere 17 link mapping、12D joint order / seed 审计和 table collider 归属判断；下一步回 reset/layout/collider contract，不允许 action/contact/score。 |
| `eos2_gate1u_a3e_support_surface_diagnostic_runner_checkpoint_20260706.json` | A3e support-surface diagnostic runner checkpoint | `CODE_READY_A3E_SUPPORT_SURFACE_DIAGNOSTIC_PAYLOAD_NOT_LIVE_EVIDENCE` | 通过 TDD 给 `native_action_path_runner` 增加 diagnostic-only `support_surface_payload` 透传和 CLI 参数，用于后续请求 `support_surface_clearance_records`。这不是 live、不是 table ignore 修复、不是 reachability/contact/score 证据。 |
| `eos2_gate1u_a3e_support_surface_diagnostic_request_20260706/` | A3e support-surface diagnostic request | `A3E_SUPPORT_SURFACE_CLEARANCE_DIAGNOSTIC_EXECUTED_NO_GO_A3F_BLOCKED_RESET_LAYOUT_COLLIDER_CONTRACT` | 已执行 server/submit/runner，固定 A3B right-arm route、A3c exact table obstacle、`support_surface_uid=table`，并强制 `--max-action-points 0`；runner exit code `2` 是 blocked/no-go。summary 产出 2 条 same-frame `support_surface_clearance_records`，`clearance_margin_m=-0.6237133788083942`、`physically_intersecting_support_surface=true`、`planner_only_support_surface_exclusion_allowed=false`。raw runner classification 是旧泛化标签，canonical status 以 same-frame clearance no-go 为准；A3f 不允许，下一步回到 Lift2 reset/base/joint/table-collider contract review。 |
| `eos2_gate1u_a3g_reset_layout_collider_contract_review_20260706.json` | A3g reset/layout/collider contract review | `REVIEW_A3G_PLANNER_WORLD_TABLE_VISUAL_MESH_OVERBROAD_REPAIR_REQUIRED_BEFORE_A3F` | 只读 review 已把 `sphere_index=17` 映射到 Lift2/R5a right-arm `link6` sphere0，并确认 A3e 报告的 table obstacle 是无 `PhysicsCollisionAPI` 的完整视觉桌体 mesh；真正带 `PhysicsCollisionAPI` 的 table surface 是 `/World/labutopia_level1_poc/obj_table/surface/mesh`。因此 A3f 仍 blocked，下一步 A3h 只能做 planner-world scoped repair preflight：过滤/替换非 physics visual table mesh，同时保留真实 table collision surface。 |
| `eos2_gate1u_a3h_planner_world_visual_mesh_repair_preflight_20260706/result_compact.json` | A3h planner-world visual-mesh scoped repair preflight live | `LIVE_A3H_VISUAL_MESH_BLOCKER_ADVANCED_STAGING_PASS_HANDLE_NEAR_IK_FAIL_NEEDS_A3J_REACHABILITY_DIAGNOSTIC` | A3h 0002 已实际跑完：`executed_steps=0`，第一段 `lift2_right_robot_frame_staging_microwave_style` planner 成功并生成 `84` 个 trajectory points；第二段 `lift2_right_handle_front_approach_near_035` 返回 `MotionGenStatus.IK_FAIL`、0 points。它支持从 table visual-mesh blocker 转入 bounded handle-front reachability 诊断，但不证明 runtime filter full closure、execution readback、contact、door motion、Expert Oracle Score 或官方分数。 |
| `eos2_gate1u_a3h_runtime_filter_telemetry_code_checkpoint_20260706.json` | A3h runtime filter telemetry code checkpoint | `CODE_READY_A3H_RUNTIME_FILTER_TELEMETRY_NOT_LIVE_EVIDENCE` | 通过 TDD 让 cuRobo start-state collision diagnostic 暴露 `exact_ignore_paths_without_physics_collision_api` 和 `exact_non_physics_obstacle_filter`，下一次 A3h telemetry rerun 可直接看到 `removed_paths` / `kept_requested_paths`。这只是 code-ready checkpoint，不是 live rerun，也不证明 A3h 0002 的 filter full closure。 |
| `eos2_gate1u_a3j_handle_front_runtime_target_equivalence_review_20260706.json` | A3j handle-front runtime target equivalence review | `REVIEW_A3J_RUNTIME_TARGET_EQUIVALENCE_MISMATCH_FOUND_STOP_BEFORE_REACHABILITY_SWEEP` | A3j 先做 zero-live trace review，发现 A2b intended world target `[0.47979, 0.31072, 1.10859]` 与 A3h runtime target `[0.43479, 0.31072, 1.10859]` 在 world X 差 `0.045m`，超过 `0.01m` tolerance。结论：不能直接扩大 IK sweep；下一步先做 corrected local coordinate forward-check，再进入最多 5 个候选的 bounded reachability matrix。 |
| `eos2_gate1u_a3j1_corrected_target_forward_check_20260706.json` | A3j1 corrected target forward-check | `PASS_A3J1_CORRECTED_TARGET_FORWARD_CHECK_READY_FOR_A3J2_BOUNDED_REACHABILITY` | 用 A3h runtime resolver frame 做 zero-live forward-check：将 local Y 从 `-0.0208166` 改为 `0.0241834` 后，forward world target 回到 A2b intended `[0.47979, 0.31072, 1.10859]`，误差约 `3.22e-09m`，低于 `0.01m`。这只证明点位修正成立，不证明 planner 可达。 |
| `eos2_gate1u_a3j2_bounded_handle_front_reachability_matrix_20260706.json` | A3j2 bounded handle-front reachability matrix | `CONSUMED_BY_A3J2_LIVE_ALL_CANDIDATES_IK_FAIL_STOP_SELECTED_ROUTE` | 预注册最多 5 个候选：A3j1 corrected center、approach farther/closer `1cm`、world-X/local-Y `+/-5mm`。该 matrix 已被 A3j2 live 消费，5 个候选全部 `IK_FAIL` / 0 trajectory；当前 selected route 按 stop line 停止。 |
| `eos2_gate1u_a3j2_bounded_handle_front_reachability_matrix_20260706/route_manifest.json` | A3j2 runner-consumable route manifest | `PREPARED_A3J2_ROUTE_MANIFEST_NOT_LIVE_EVIDENCE` | 将 A3j2 5 个候选打包成 runner 可选择的 route-id：`A3J2_CORRECTED_CENTER`、`A3J2_APPROACH_FARTHER_010`、`A3J2_APPROACH_CLOSER_010`、`A3J2_WORLD_X_PLUS_005`、`A3J2_WORLD_X_MINUS_005`。每条 route 都保留 right-arm staging + one object-frame handle-front waypoint，不含 contact/score。 |
| `eos2_gate1u_a3j2_bounded_reachability_live_20260706/aggregate_summary.json` | A3j2 bounded reachability live aggregate | `BLOCKED_A3J2_ALL_HANDLE_FRONT_REACHABILITY_CANDIDATES_FAILED_STOP_SELECTED_ROUTE` | 按 reviewer 要求拆成 5 个独立 child run，每个 child 有独立 `run_id`、`summary.json`、`trace.jsonl` 和 stdout。结果：`pass_candidate_route_ids=[]`，`executed_steps_total=0`，5/5 handle-front waypoint 都是 `MotionGenStatus.IK_FAIL` 和 `trajectory_point_count=0`。不能进入 A3k/contact/score；下一步转 layout/base/official Lift2 placement 或 route redesign。 |
| `eos2_gate1u_a3l_official_lift2_placement_base_layout_review_20260706.json` | A3l official Lift2 placement / base-layout review | `REVIEW_A3L_OFFICIAL_PLACEMENT_BASE_LAYOUT_BRANCH_RECOMMENDED_NOT_LIVE_EVIDENCE` | A3j2 后的推荐优先分支。zero-live 抽取 current reset base、corrected handle target、right-arm reference frame 和 official microwave Lift2 pose pattern，结论是先检查机器人是否站位不合适；后续只允许 max-5 base-layout matrix，不改把手目标、不删真实 table surface、不跑 contact/score。 |
| `eos2_gate1u_a3l_base_layout_candidate_matrix_20260706.json` | A3l base-layout candidate matrix | `CONSUMED_BY_A3L_LIVE_PASS_READY_FOR_A3K` | 预注册 5 个 base-layout candidate；每个 candidate 固定 A3j2 corrected handle target、right arm、route id 和真实 table surface，只改 `robots[0].position/orientation`。该 matrix 已被 A3l live 消费，3/5 candidate pass。 |
| `eos2_gate1u_a3l_base_layout_live_20260706/aggregate_summary.json` | A3l base-layout live aggregate | `PASS_A3L_AT_LEAST_ONE_BASE_LAYOUT_CANDIDATE_READY_FOR_A3K` | 5 个独立 child run 已完成；3/5 candidate planner success 且 trajectory 非空：`A3L_XP10_YP30_KEEP_YAW` 70 points、`A3L_XP15_YP25_KEEP_YAW` 67 points、`A3L_XP10_YP20_OFFICIAL_YAW90` 96 points。`executed_steps_total=0`，只解锁 A3k short execution readback，不证明 contact/door/score。 |
| `eos2_gate1u_a3r_fixed_layout_terminal_orientation_review_20260706.json` | A3r fixed-layout terminal orientation fallback review | `REVIEW_A3R_FIXED_LAYOUT_TERMINAL_ORIENTATION_FALLBACK_PREPARED_NOT_LIVE_EVIDENCE` | 如果 A3l 被拒绝、延期或失败，A3r 作为固定布局 fallback。它固定 corrected handle-front translation，只允许最多 5 个 terminal orientation candidate；禁止第 6 个 offset、禁止中间 waypoint/path-family 变更、禁止 contact/score。当前 A3l 已通过，因此 A3r 暂缓，下一步先 A3k。 |
| `eos2_gate1u_a3k_short_execution_readback_20260706/selection_manifest.json` | A3k short execution readback selection | `CONSUMED_BY_A3K_LIVE_BLOCKED_READBACK_INSTRUMENTATION` | 只选 `A3L_XP15_YP25_KEEP_YAW` 一个 A3l pass candidate；动作预算固定为 180 points，joint tolerance `0.02rad`，EE translation/orientation tolerance 分别为 `0.03m` / `15deg`。该 manifest 已被 A3k live 消费。 |
| `eos2_gate1u_a3k_short_execution_readback_20260706/result_compact.json` | A3k short execution readback live result | `BLOCKED_A3K_SHORT_EXECUTION_READBACK_NOT_READY_FOR_A3M` | 单候选实际执行 `142` steps，final planner record 是 `a3j2_corrected_center`。post-run review 发现 final trace 里有 `obs.state.joints`、`obs.state.ee_pose` 和 `obs.state.gripper`，所以 blocker 不是“完全没有状态”，而是 12D observation joint order 到 16D action payload 的映射、right-arm EE pose 显式归属、以及 full-run collision/contact schema 未闭合。因此不能进入 A3m/contact/score；下一步是 A3k1 offline readback mapping audit，必要时同一 candidate 最多 1 次 instrumentation rerun。 |
| `eos2_gate1u_a3k1_offline_readback_mapping_audit_20260706.json` | A3k1 offline readback mapping audit | `BLOCKED_A3K1_MAPPING_CLOSED_SELECTED_CANDIDATE_JOINT_READBACK_FAILS_A3K2_INSTRUMENTATION_ALLOWED` | 0-live audit 已闭合 Lift2 schema：`state.joints` 是 12D arm-only，`state.gripper` 是 4D gripper-only，16D action 是 left arm / left gripper / right arm / right gripper；`state.ee_pose[1]` 可由 `DualArmEmbodiment._fk_single` 证明为 right arm。runner comparator 已按 TDD 修正，`test_native_action_path_runner.py` 14 passed。用修正 comparator 重算旧 trace：gripper max error 约 `3.49e-05`，但 12D arm joint max error `2.5710rad > 0.02rad`，所以 A3k 仍不能进 A3m。A3k2 只允许同一 candidate 一次 instrumentation rerun，补 controller applied target、right-arm EE frame/world pose 和 full-run collision/contact telemetry；不是 route sweep。 |
| `eos2_gate1u_a3k2_instrumentation_code_checkpoint_20260706.json` | A3k2 instrumentation code checkpoint | `CODE_READY_A3K2_SPLIT_READBACK_AND_DUAL_ARM_EE_DEBUG_NOT_LIVE_EVIDENCE` | GenManip runner 已补 Lift2 split arm/gripper comparator，debug obs 已补 `evaluator_last_ee_pose_by_arm.left/right` 和 `evaluator_last_ee_pose_frame=planner_fk_reference_frame`；测试：runner focused 1 passed、runner file 14 passed、debug focused 1 passed、debug file 27 passed。它不是 live evidence，也不消耗 A3k2 唯一 rerun。当前还不能立刻跑 A3k2，因为旧 A3k postprocess 只接受 `dict:right/right_arm`，尚未消费 `debug.labutopia_open_door.evaluator_last_ee_pose_by_arm.right` 或归一化 full-run contact schema。 |
| `eos2_gate1u_a3k2_package_postprocess_closure_20260706.json` | A3k2 package postprocess closure | `CODE_READY_A3K2_PACKAGE_POSTPROCESS_CLOSURE_BLOCKS_LIVE_RERUN_UNTIL_WORLD_EE_FULL_RUN_CONTACT_CONTROLLER_DEBUG` | 0-live code/test/package stop-go。新增 `a3k_readback_postprocess.py` 和 7 条单测，证明 postprocess 能消费 `debug.labutopia_open_door.evaluator_last_ee_pose_by_arm.right`，但会阻断非 world-frame EE、final-step-only `physx_contact_debug`、contact sample coverage mismatch、以及缺 controller/applied-target debug 的 package。结论：A3k2 唯一 live rerun 仍未允许；下一步先做 instrumentation expansion，补 world-frame EE 或 transform、full-run contact coverage、`final_applied_action_target_16d` 和 `tail_joint_error_series`。 |
| `eos2_gate1u_a3k2_instrumentation_expansion_step_sampling_checkpoint_20260706.json` | A3k2 instrumentation expansion step-sampling checkpoint | `CODE_READY_A3K2_STEP_SAMPLING_NOT_FULL_TELEMETRY_NOT_LIVE_EVIDENCE` | runner 新增显式 `--step-chunk-size`；默认仍一次性 `step_chunk`，只有设置 `--step-chunk-size 1` 时才逐 action 执行并在 trace 写 `step_chunk_sample`。测试：focused 1 passed、runner+postprocess 22 passed。multi-agent review 明确：这只是 full-run telemetry 的前置采样能力，不能证明 no abnormal table/door/body contact；Lift2 right-arm EE world transform 必须来自 `robot_base_right.get_world_pose()`，不能用 robot root pose；controller/applied-target debug 必须来自 evaluator `env.step`。A3k2 live 仍不允许。 |
| `eos2_gate1u_a3k2_instrumentation_expansion_world_ee_checkpoint_20260706.json` | A3k2 instrumentation expansion world-EE checkpoint | `CODE_READY_A3K2_RIGHT_ARM_WORLD_EE_DEBUG_NOT_FULL_A3K2_LIVE_READY` | debug obs 保留 raw `evaluator_last_ee_pose_by_arm.right` 的 `planner_fk_reference_frame` 语义，同时新增 `evaluator_last_ee_pose_reference_frame_by_arm.right` 和 `evaluator_last_ee_pose_world_by_arm.right`。Lift2 right-arm world transform 使用 `embodiment.robot_base_right.get_world_pose()`，不是 robot root pose。postprocess 现在优先消费 explicit world-by-arm right EE，并拒绝“把 raw by-arm frame 字符串改成 world”的 shortcut。测试：world-EE focused 1 passed、postprocess focused 3 passed、combined 53 passed。A3k2 live 仍不允许，因为 full-run abnormal contact aggregation 和 controller/applied-target aggregation 未闭合。 |
| `eos2_gate1u_a3k2_instrumentation_expansion_controller_checkpoint_20260706.json` | A3k2 instrumentation expansion controller checkpoint | `CODE_READY_A3K2_CONTROLLER_APPLIED_TARGET_AGGREGATION_NOT_FULL_A3K2_LIVE_READY` | runner 在 `--step-chunk-size 1` 下会从每步 `debug.labutopia_open_door.evaluator_last_action_application_debug` 聚合 `a3k2_controller_debug.v1`：`final_applied_action_target_16d` 来自 evaluator `applied_joint_position_target`，`tail_joint_error_series` 来自 `post_world_step_minus_target_abs_max`，不是 runner 用 action_chunk 猜出来的。TDD：focused RED KeyError 后 GREEN 1 passed，combined adjacent 54 passed。A3k2 live 仍不允许；剩余 blocker 收敛为 full-run abnormal contact aggregation 和刷新 package closure。 |
| `eos2_gate1u_a3k2_instrumentation_expansion_full_run_contact_checkpoint_20260706.json` | A3k2 instrumentation expansion full-run contact checkpoint | `CODE_READY_A3K2_FULL_RUN_CONTACT_AGGREGATION_NOT_LIVE_EVIDENCE` | runner 在 `--step-chunk-size 1` 下会把每步 `physx_contact_debug` 聚合为 `a3k_full_run_collision_contact_readback.v1`，要求 `contact_sample_count == executed_steps` 且 `missing_contact_sample_count == 0`；postprocess 仍会把单个 final obs 的 `physx_contact_debug` 判为 final-step-only，不会冒充 full-run。review 后又收紧 shape validation：`status=available` 不够，schema/method/list/errors 形状不对会计为 invalid/missing sample。该 schema 只覆盖 per-step observed `physx_contact_debug` unmatched pairs，不是全局所有场景碰撞证明。A3k2 live budget 尚未消耗；下一步允许准备同一 candidate 的唯一 A3k2 live rerun package。 |
| `eos2_gate1u_a3k2_same_candidate_live_rerun_20260706/result_compact.json` | A3k2 same-candidate live rerun result | `BLOCKED_A3K2_SAME_CANDIDATE_INSTRUMENTED_READBACK_NOT_READY_FOR_A3M` | Instrumented live 已执行：固定 `A3L_XP15_YP25_KEEP_YAW` + `A3J2_CORRECTED_CENTER`，端口 `18121`，`--step-chunk-size 1`。关键事实：`executed_steps=143`、final planner record 是 `a3j2_corrected_center`，所以动作链确实进入 EBench step。它没通过：runner exit code `2`，right-arm EE missing、controller/tail debug missing、full-run contact sample coverage `0/143`。这不是 selected route/contact/score failure，因为 root cause 是 debug obs 没注入 live observation；full A3k2 readback 只在 A3k2b PASS 后 exactly one rerun。 |
| `eos2_gate1u_a3k2_generated_task_name_debug_gate_closure_20260706.json` | A3k2 generated task-name debug gate closure | `CODE_READY_A3K2_GENERATED_LIFT2_TASK_NAME_DEBUG_GATE_NOT_LIVE_RERUN` | Root cause 已定位并用 TDD 修复：A3k2 generated config 的 task name 是 `ebench/labutopia_lab_poc/lift2_candidate/a3l_base_layout/a3l_xp15_yp25_keep_yaw`，但 debug gate 只接受 leaf 为 `level1_open_door*` 的任务，导致 `LABUTOPIA_ORACLE_DEBUG_OBS=1` 仍不注入 `debug.labutopia_open_door`。新增 regression test 先 RED `KeyError: debug.labutopia_open_door`，修复后 focused `1 passed`，debug-state suite `29 passed`。它是 code-ready，不是 live rerun；下一步必须先做 A3k2b debug-gate live/short validation，不能进入 A3m/contact/fallback candidate。 |
| `eos2_gate1u_a3k2b_debug_gate_validation_20260706/result_compact.json` | A3k2b generated task-name debug-gate live validation | `PASS_A3K2B_GENERATED_TASK_NAME_DEBUG_GATE_READY_FOR_A3K2_READBACK` | A3k2b 只执行 1 个 diagnostic action point，runner exit code `2` 是预期的 `execution_action_points_limited:1/142`。postprocess PASS：`executed_steps=1`、reset/step obs 都有 `debug.labutopia_open_door`、step debug keys 包含 right-arm world EE、`a3k2_controller_debug.v1` 有 `final_applied_action_target_16d` 和 `tail_joint_error_series`、`a3k_full_run_collision_contact_readback.v1` 覆盖 1/1 step 且 missing/invalid 为 0。它只证明 generated Lift2 task-name debug observations 已进入 live obs；不证明 full A3k2 readback、contact、retention、micro-pull、door opening、Expert Oracle Score、policy score 或 official score。下一步只允许 exactly 1 次 full A3k2 same-candidate readback rerun。 |
| `eos2_gate1u_a3k2c_full_readback_rerun_20260706/result_compact.json` | A3k2c full same-candidate readback rerun | `BLOCKED_A3K2C_FULL_SAME_CANDIDATE_READBACK_NOT_READY_FOR_A3M` | A3k2b 解锁后的 exactly 1 次 full same-candidate rerun 已执行并消耗预算：同一 `A3L_XP15_YP25_KEEP_YAW` + `A3J2_CORRECTED_CENTER`，`executed_steps=142`，final planner label 是 `a3j2_corrected_center`。好消息是 full-run contact coverage 是 `142/142`，missing/invalid 为 0，异常 table/door/body contact 为 0，trace 最后一帧也能看到 Lift2 `state.joints` / `state.gripper`。A3k2c 的旧 blocker 先归类为 readback consistency：runner summary 报 `state_joints_missing`，postprocess 的旧 `readback_schema_closed=false` 继承该字段，不能直接把 A3k2c 判成 selected route failure。后续 A3k2d 已完成，见下一行。 |
| `eos2_gate1u_a3k2d_readback_consistency_audit_20260706.json` | A3k2d zero-live readback consistency audit | `BLOCKED_A3K2D_READBACK_CONSISTENCY_SELECTED_CANDIDATE_NOT_READY_FOR_A3M` | A3k2d 不启动 live，只流式读取 A3k2c 的 `trace.jsonl` 和 `summary.json`。结论：final worker obs 存在，`robot_id=manip/lift2/R5a`，`state.joints` 长度 12、`state.gripper` 长度 4；用 controller `final_applied_action_target_16d` 重算后，`readback_source=final_worker_obs_and_controller_debug`、`readback_schema=lift2_split_arm_gripper_obs_to_16d_action`，因此旧 `state_joints_missing` 是 stale runner summary，不再是 telemetry blocker。闭合后的真实失败点是 selected candidate 未到位：joint error `2.570956rad > 0.02rad`，right-arm EE translation error `0.527791m > 0.03m`，orientation error `166.862deg > 15deg`；full-run contact 仍 clean。按 stop-go，不能进 A3m，也不能同 candidate 重调；下一步允许 A3k bounded fallback 最多再评估 A3l 剩余 2 个 planner-success candidates。 |
| `eos2_gate1u_a3k_bounded_fallback_readback_20260706/result_compact.json` | A3k bounded fallback readback | `BLOCKED_A3K_BOUNDED_FALLBACK_ALL_CANDIDATES_NOT_READY_FOR_A3M` | A3k bounded fallback 消耗 A3l 剩余两个 planner-success candidates，仍固定 `A3J2_CORRECTED_CENTER`、right arm、16D action、`--step-chunk-size 1` 和同一套 readback/contact/controller telemetry。结果 `pass_candidate_ids=[]`。`A3L_XP10_YP30_KEEP_YAW` 执行 `152` steps，schema 闭合、contact `152/152` clean，但 joint error `1.133121rad`、EE translation error `0.342726m` 超阈值；`A3L_XP10_YP20_OFFICIAL_YAW90` 执行 `178` steps，schema 闭合、contact `178/178` clean，但 joint error `2.027691rad`、EE translation error `0.312915m`、orientation error `89.758deg` 超阈值。结论：A3l 的 3 个 planner-success candidates 全部在 closed-schema A3k readback 下失败；不能进入 A3m/contact/score，下一步是 A3l route-family no-go review，转 A3r 或上层合同评审。 |
| `eos2_gate1u_a3l_route_family_no_go_review_20260706.json` | A3l route-family no-go review | `REVIEW_A3L_BASE_LAYOUT_ROUTE_FAMILY_NO_GO_FOR_A3M` | 多角度 review 已把 A3l 结论升级为 route-family no-go for A3m：三条 planner-success candidates 都已经闭合 readback 且失败，full-run contact 均 clean，因此不再允许继续 A3l base/yaw/offset sweep。下一步只允许 E0/E1：0-live evidence freeze 和 controller/execution contract audit。只有 E1 找到明确可修或可验证的 controller/action/readback hypothesis，才允许 E2 的 1 次 EBench reference probe。 |
| `eos2_gate1u_e1_controller_execution_contract_audit_20260706.json` | E1 controller/execution contract audit | `REVIEW_E1_CONTROLLER_EXECUTION_CONTRACT_HYPOTHESIS_READY_FOR_E2_REFERENCE_PROBE` | E1 0-live 审计已完成。它冻结了三条 A3l readback fail 证据，并排除没提交动作、碰撞中断和简单 readback 顺序写反：三条路线的 `applied_target_sample_count == executed_steps`，contact clean，但 tail joint error 停在 `1.13-2.57rad`。可信假设是 `H1_PLAYBACK_OUTRUNS_LIFT2_CONTROLLER`：每个 planner point 只执行一次 `world.step()`，而 Lift2 velocity cap 和 action delta 可能导致 controller 追不上。下一步唯一允许 E2：一次 non-DryingBox Lift2 controller reference / retiming probe，包含 5 no-op、5 right-arm small ramp、60 terminal hold；不允许直接重跑 DryingBox candidate。 |
| `eos2_gate1u_e2r_controller_action_readback_root_cause_plan_20260706.json` | E2R controller/action/readback root-cause plan | `E2R5_CLOSED_DIRECT_16D_ROUTE_NO_GO_FORK_OFFICIAL_LIFT2_BASELINE_CONTROLLER_ACTION_PATH` | E2 live 已触发 stop line 后新增的阶段计划。它冻结 E2 事实：70/70 steps 执行、target 与 applied target 最大差约 `5.52e-09rad`、但 no-op/hold readback 失败。E2R1/E2R2/E2R3/E2R4/E2R5 均已完成；E2R5 关闭当前 direct 16D `joint_position` 路线，转 official Lift2 baseline controller/action path review。这不代表整个 LabUtopia-to-EBench 项目 no-go。 |
| `eos2_gate1u_e2r1_per_joint_telemetry_code_checkpoint_20260706.json` | E2R1 per-joint telemetry code checkpoint | `CODE_READY_E2R1_PER_JOINT_TELEMETRY_PENDING_E2R2_LIVE` | GenManip E2 reference probe 已补 per-joint telemetry：observed/expected/error vectors、max-error slot / component / global DOF / DOF name、完整 action-application debug、post-step joint vector、controller drive debug 和静态 Lift2 action-slot mapping。TDD RED 包括缺 `observed_joints12`、缺 `full_action_application_debug`、缺 `action_slot_mapping`；GREEN 后 E2 probe test file `13 passed in 0.03s`。这仍是 code/test-only checkpoint，不证明 live blocker 修好；下一步只允许 E2R2 enhanced non-DryingBox live。 |
| `eos2_gate1u_e2r2_enhanced_lift2_controller_reference_live_20260706/result_compact.json` | E2R2 enhanced Lift2 controller reference live | `BLOCKED_E2R2_TARGET_APPLIED_BUT_ARM_JOINTS_DO_NOT_TRACK` | E2R2 消耗唯一 enhanced non-DryingBox live：`executed_steps=70/70`，raw classification 仍是 E2 controller/readback blocked。Enhanced telemetry 已闭合：no-op 最大误差来自 `fl_joint3`，支持 reset baseline stale / settling；terminal hold 最大误差来自 `fr_joint1`，controller applied target 是 `0.20075rad`，但 observed 仍接近 `0rad`，60 hold 后仍不跟踪。因此单纯 ramp 太快解释被削弱；下一步 E2R3 只做 zero-live / single-hypothesis repair planning，不能重复 E2R2、不能进 DryingBox E3/E4/contact/score。 |
| `eos2_gate1u_e2r3_lift2_articulation_contract_repair_plan_20260706.json` | E2R3 Lift2 articulation contract repair plan | `E2R5_CLOSED_DIRECT_16D_ROUTE_NO_GO_FORK_OFFICIAL_LIFT2_BASELINE_CONTROLLER_ACTION_PATH` | 多角度 review 后选择单一优先假设：action 到 controller 已基本闭合，但 controller target 没有变成 Lift2 arm DOF 的物理运动。E2R3 没有消耗 live；E2R4 按 E2R3c 决策跑完最后一次 non-DryingBox 小动作 live 后仍失败，因此 E2R5 封账并转 official Lift2 baseline controller/action path。 |
| `eos2_gate1u_e2r3a_lift2_articulation_contract_zero_live_audit_20260706.json` | E2R3a Lift2 articulation zero-live audit | `COMPLETED_E2R3A_ZERO_LIVE_AUDIT_READY_FOR_E2R3B_TELEMETRY` | 静态 USD/PXR 审计确认 `fr_joint1` 存在、是 `PhysicsRevoluteJoint`、有 `PhysicsDriveAPI:angular`、`jointEnabled=true`、`excludeFromArticulation=false`、maxForce `100`，所以 blocker 不是粗粒度的“右臂 joint/drive 缺失”。但当前 telemetry 还不能证明 runtime DOF mapping、qdot、limit、max velocity、sleep/constraint 状态，因此不允许行为修复或 live；下一步 E2R3b code/test-only 补 per-DOF runtime telemetry。 |
| `eos2_gate1u_e2r3b_articulation_telemetry_code_checkpoint_20260706.json` | E2R3b articulation telemetry code checkpoint | `CODE_READY_E2R3B_ARTICULATION_TELEMETRY_PENDING_E2R3C_REPAIR_DECISION` | GenManip `read_articulation_controller_debug` 已补 runtime `joint_position`、`joint_velocity`、`max_joint_velocity`、`joint_lower_limit`、`joint_upper_limit`，并保留原 applied target / drive gains / max effort。TDD RED 为缺 `joint_position` 和 legacy schema 缺 null 字段；GREEN 后 focused 2 passed，相关 LabUtopia suite `97 passed in 0.60s`，`py_compile` 与 diff check exit 0。仍是 code/test-only，不证明 arm tracking fixed；下一步 E2R3c 先选唯一修复点，不能直接 live/score。 |
| `eos2_gate1u_e2r3b2_summary_telemetry_addendum_20260706.json` | E2R3b2 summary telemetry addendum | `CODE_READY_E2R3B2_SUMMARY_TELEMETRY_READY_FOR_E2R4` | 0-live / code-test-only 可判读性补丁。`lift2_controller_reference_probe` 现在把最终 step 的 `controller_drive_debug` 提升为 `final_controller_drive_debug`，并把最终 `joint_position`、`joint_velocity`、`max_joint_velocity`、上下限、applied target 和 drive 参数摘成 `final_runtime_motion_debug`。新增测试先 RED 到缺 `final_controller_drive_debug`，GREEN 后相关 suite `98 passed in 0.60s`，`py_compile` 与 diff check exit 0。它不改机器人行为，只让 E2R4 一次 live 后可直接按 summary 判定。 |
| `eos2_gate1u_e2r3c_single_repair_decision_20260706.json` | E2R3c single repair decision | `READY_E2R4_FINAL_CONTROLLER_SANITY_LIVE_WITH_TELEMETRY_NO_BEHAVIOR_REPAIR` | E2R3c 明确拒绝盲目加 drive/gain、盲目换 articulation API、盲目加 hold 或把 reset baseline 当主修复。理由是当前零 live 证据还没有锁定具体行为变量。下一步允许 exactly one E2R4 non-DryingBox controller sanity live，使用 E2R3b telemetry 判定：pass 回 E3/E4；target applied 但 qdot 近零且 limit/effort 解释不了则 direct 16D 路线 no-go，转 official Lift2 baseline action path。 |
| `eos2_gate1u_e2r4_final_controller_sanity_live_20260706/result_compact.json` | E2R4 final controller sanity live | `NO_GO_DIRECT_16D_JOINT_POSITION_ROUTE_FORK_OFFICIAL_LIFT2_BASELINE_ACTION_PATH` | E2R4 消耗唯一 allowed live：同一个 non-DryingBox Lift2 小动作 probe 执行 `70/70` steps，no-op/ramp/hold 都未达到 `0.02rad` tolerance。最终最大误差仍是 slot `8` / `right_joint1`：target `0.200753768836rad`、controller applied target `0.20075376331806183rad`，但 worker obs observed `-0.000003879rad`，final error `0.20075764784227174rad`。limits 不挡、drive 参数存在、`readback_errors=[]`；runtime `max_joint_velocity` 为 null，作为 caveat 记录。结论是当前 direct 16D route no-go，不是项目 no-go。 |
| `eos2_gate1u_e2r5_direct_16d_route_closure_fork_20260706.json` | E2R5 zero-live closure / fork decision | `E2R5_CLOSED_DIRECT_16D_JOINT_POSITION_ROUTE_NO_GO_FORK_OFFICIAL_LIFT2_BASELINE_CONTROLLER_ACTION_PATH` | 0-live 封账，不再启动第三次 exploratory live。多角度 review 一致认为 E2R4 足以关闭当前 direct 16D `joint_position` 路线：target 到 controller，但 right_joint1 不物理跟踪，60-step hold 不收敛。下一步只能开 official Lift2 baseline controller/action path review；DryingBox E3/E4、contact、micro-pull 和 Expert Oracle Score 继续 blocked。 |
| `eos2_gate1u_f1_f5_stop_go_planning_review_20260706.json` | F1-F5 official baseline stop-go planning review | `PLANNED_F1_F5_STOP_GO_BOUNDARY_NOT_LIVE_EVIDENCE` | 多角度 zero-live planning review，并已随 F1b/F1c/F1d 更新收紧。F1 判 official prep-output 是否只是 E2R4 direct 16D payload 的重复；F1b 判 endpoint/base_motion 是否可作为修复理由；F1c 选唯一下一方向；F1d 只释放 F1e code/test；F1e 通过后才允许一次 F2。F2 通过只说明底层控制可用，不代表开门或 score；F2 若 telemetry 完整、target applied、max effort repaired，但 `right_joint1` 同向运动不足或 terminal error 超阈值，则关闭当前 max-effort repair route。完整 `Expert Oracle Score` 闭环最早是 F5/Gate 5。 |
| `eos2_gate1u_f1_official_prep_output_equivalence_20260706.json` | F1 terminal zero-base arm-only prep-output equivalence | `F1_TERMINAL_ZERO_BASE_ARM_ONLY_EQUIVALENCE_NO_ARM_ONLY_F2_LIVE_F1B_REQUIRED` | 0-live code/test + classification。GenManip helper 和测试已验证：相邻 focused suite `40 passed in 0.89s`，`py_compile` 和 `diff --check` exit 0。用 E2R4 final `applied_joint_position_target_16d` 生成 official 19D row 再 prep-output，terminal arm-only zero-base 分类为 `EQUIVALENT_TO_DIRECT_16D_PAYLOAD`，joint/base/metadata diff 均为 0。因此不允许 terminal arm-only zero-base official F2 live。该 manifest 不覆盖 no-op、ramp、full official policy 19D horizon、endpoint 或 wrapper boundary；synthetic `base_motion` probe 只说明同一 terminal arm payload 下 base_motion 是 payload-level 差异，不能解释 right_joint1 arm tracking blocker。该阶段后续已被 F1b/F1c 消费，当前下一步是 F1d。 |
| `eos2_gate1u_f1b_official_runner_endpoint_base_motion_boundary_20260706.json` | F1b official runner endpoint/base-motion boundary review | `F1B_ZERO_LIVE_STEP_CHUNK_ENDPOINT_BOUNDARY_CLOSED_BASE_MOTION_SEPARATE_NOT_RUNTIME_EVIDENCE` | 多角度 zero-live source review。official runner 和 E2R4 reference probe 都进入 GenManip `/step_chunk` 并最终调用同一 `env.step` action application path；`base_motion` 是真实的 3D 底盘通道，但与 16D arm/gripper joint target 分离，不能解释或修复 `right_joint1` arm no-motion。因此 terminal arm-only zero-base official F2 live 不允许，endpoint 差异也不能作为 F2 理由。该阶段后续已被 F1c 消费，当前下一步是 F1d concrete repair selector。 |
| `eos2_gate1u_f1c_single_hypothesis_selector_20260706.json` | F1c single-hypothesis selector | `F1C_SELECTED_CONTROLLER_ARTICULATION_RUNTIME_REPAIR_ZERO_LIVE_F2_NOT_RELEASED` | 多角度 zero-live selector。选择 `controller_articulation_runtime_repair` 作为唯一下一路由，因为 E2R4 证明 target 到 controller 但 `right_joint1` physical readback 不跟踪。Newton/action homologation 只能作为 supporting audit，不能验证 GenManip/Isaac runtime；higher-level official action abstraction 和 base-only diagnostic 当前不释放 F2。下一步 F1d 必须选 exactly one 具体 repair family，并写清 F2 command/readback/tolerance/no-go condition；F1c 本身不消耗 live，也不解锁 DryingBox/contact/score。 |
| `eos2_gate1u_f1d_concrete_repair_selector_20260706.json` | F1d concrete repair selector | `F1D_REVISED_SELECTED_LIFT2_ARM_RUNTIME_MAX_EFFORT_ONLY_REPAIR_F2_NOT_RELEASED_PENDING_F1E_CODE_TEST` | 0-live selector。后续 review 修订选择为 `lift2_arm_runtime_max_effort_only_repair`：E2R4 target 到 controller 但 `right_joint1` 不跟踪，API swap 不会改变底层 target path，而 runtime `drive_max_effort=100.0` 是最具体的未闭合 actuation 变量。F1d 只释放 F1e code/test checkpoint，不释放 F2 live；F1e 必须证明实现与 E2R4 unchanged path 不同，且不混入 action API/gain/max-velocity/hold/base/DryingBox 修复。 |
| `eos2_gate1u_f1e_lift2_runtime_max_effort_code_checkpoint_20260706.json` | F1e Lift2 runtime max-effort code checkpoint | `CODE_READY_F1E_LIFT2_ARM_RUNTIME_MAX_EFFORT_ONLY_REPAIR_READY_FOR_EXACTLY_ONE_F2_LIVE_CANDIDATE` | TDD code/test checkpoint，不是 live evidence。GenManip 只对 Lift2 左右臂 12 个 arm DOF 调用 `ArticulationView.set_max_efforts`，值 `1000000.0`，且调用点在 `_post_initialize()` 后以避免未初始化 no-op；不改 action API、gain、max velocity、hold、base、DryingBox 或 gripper/lift/base DOF。Focused `2 passed`，相邻 suite `20 passed`，`py_compile` 和 `diff --check` exit 0。多 agent review PASS，下一步只能预注册 exactly one F2 non-DryingBox live；缺 required readback 时必须判 telemetry-blocked。 |
| `eos2_gate1u_f2_f5_decision_checkpoint_planning_20260706.json` | F2-F5 decision checkpoint planning | `PLANNED_CURRENT_DECISION_CHECKPOINTS_NOT_LIVE_EVIDENCE` | 0-live planning manifest。它把当前预计定论点写成三层：F2 只判断 selected max-effort repair route 的底层控制能不能继续；E4/Gate 4 才判断 DryingBox 专家路线是否有工程成功信号；Gate 5 才能 claim `Expert Oracle Score`。F2 不产生 oracle_score、policy_score 或 official_score claim。术语统一：局部 no-go = 当前路线停；项目 no-go = 所有预先允许的分支都按证据停止。 |
| `eos2_gate1u_f2_lift2_max_effort_controller_sanity_preflight_20260706.json` | F2 Lift2 max-effort command preflight | `PREPARED_F2_COMMAND_PREFLIGHT_COMMAND_FILES_MATERIALIZED_RAY_TMPDIR_REPAIRED_AFTER_PRELIVE_INFRA_ATTEMPT` | 0-live command preflight。固定端口 `18132`、server parent run_id、client run_id、evidence dir、server command、submit command、runner command 和 F2 hard readback schema。precheck 显示 `PORT_18132_FREE`；同时记录 `EvalClient.reset` 不会自动加载 config，所以必须先 `submit`。第一轮 review 的 BLOCKING 已修：F2 专属 `server.command.txt` / `runner.command.txt` 已落地到 F2 live evidence dir，并带 `live_consumed_at.txt` 防 retry；readback CONCERN 已修：summary 增加 `right_joint1_motion`，pass table 不再只看 runner classification。复审 PASS 后，pre-live server attempt 0001 又暴露 Ray `AF_UNIX` socket path 过长；已缩短 `RAY_TMPDIR=/tmp/gf2_18132` 并保留 `server_attempt_0001.*` logs。因为没有 `live_consumed_at.txt`、`summary.json`、`trace.jsonl` 或 `runner.exit_code.txt`，F2 live budget 仍是 `0/1`。下一步只允许按 F2 专属命令执行 exactly one F2 live；F2 结果必须按 hard checklist 分类为 PASS / local no-go / telemetry blocked / infra blocked。 |
| `eos2_gate1u_f2_lift2_max_effort_controller_sanity_live_20260706/result_compact.json` | F2 Lift2 max-effort controller/runtime sanity live | `LOCAL_NO_GO_LIFT2_ARM_RUNTIME_MAX_EFFORT_REPAIR_ROUTE_REVIEW_HIGHER_LEVEL_OFFICIAL_RUNNER_OR_ACTION_ABSTRACTION` | F2 exactly-one live 已消耗当前 max-effort-only repair route 的唯一 live budget。server/submit/runner 均完成，server 已停止且端口释放；runner exit code `2` 不是 pass authority。hard checklist：`70/70` steps、slot `8 -> global DOF 9 -> right_joint1`、requested/applied diff 约 `2.90e-09rad <= 1e-5`、`drive_max_effort[8]=1000000.0`、`readback_errors=[]`。失败点不是“完全没动”，而是响应不足：`right_joint1` 同向运动约 `0.11047rad < 0.18rad`，terminal error 约 `0.08953rad > 0.02rad`。结论只关闭当前 max-effort repair route；不能回 E3/E4、不能 contact/micro-pull/score，下一步是 higher-level official runner / action abstraction zero-live review。 |
| `eos2_gate1u_f2a_post_f2_stop_go_route_plan_20260706.json` | F2a post-F2 stop-go route plan | `PLANNED_F2A_ZERO_LIVE_PROVENANCE_REVIEW_BEFORE_ANY_NEW_LIVE` | 0-live planning manifest。多角度 review 后明确：`physics_hold_steps` 是 diagnostic-only，`step_chunk_size` 不改变 control semantics，official prep-output / `base_motion` 的 arm 部分仍落到同一 16D `joint_position` path。下一步只能先做 F2a provenance review；若找不到真正不同的 official runner / action abstraction，就关闭 F-stage lower-level action 分支。若找到，则先 F2b 本地离线上限验证 movement `>=0.18rad` 且 terminal error `<=0.02rad`，再 F2c canonical packaging，最后才允许 F2d exactly-one live confirmation。 |
| `eos2_gate1u_f2a_provenance_review_result_20260706.json` | F2a provenance review result | `F2A_FAIL_NO_TRUE_NEW_OFFICIAL_ACTION_ABSTRACTION_CLOSE_F_STAGE_LOWER_LEVEL_ACTION_BRANCH` | 0-live result manifest。EOS 侧 review 证明 official/OpenPI Pi0 path 仍是 `50x19 -> 16D joint_position + 3D base_motion -> /step_chunk`；GenManip 侧 review 证明 `/step_chunk` 逐条进 `env.step`，最终 `set_joint_position_targets -> world.step`。`base_motion`、`physics_hold_steps`、`step_chunk_size`、`ee_pose/custom_motion`、native-drive-target controller 均不能作为当前 F-stage official lower-level action 的 F2b 新路线。结论：F2b/F2c/F2d 不进入，不允许同分支 live retry；这不是项目 no-go，也不是 Expert Oracle Score failure。 |
| `eos2_gate1v_post_f_stage_route_decision_plan_20260706.json` | Gate1V post-F route re-branch / score path selection | `PLANNED_GATE1V_POST_F_STAGE_ROUTE_DECISION_NO_LIVE` | F2a 后的上层路线决策计划，不消耗 live。它冻结当前 F-stage lower-level official/OpenPI action branch，不再 F2b/F2c/F2d 或同路线 retry；同时把下一步拆成三条线：`robot_task_fallback_oracle` 优先闭合 EBench metric / reward / success / Expert Oracle Score 最小评分链，`asset_task_no_score_hardening` 继续交付资产/任务 runtime contract 但 `score_claim_allowed=false`，`native_controller_research` 单独定义 Lift2 native control contract 且不能 claim official benchmark reproduction、standard model score 或 Expert Oracle Score。最近“弄好”必须拆成两步：Gate1V-2a 先冻结 config / score-capable runner / action stream / artifact contract，只代表可释放一次 bounded fallback score live；后续 live artifact 全闭合，才代表最小 Expert Oracle Score 评分链闭合。 |
| `eos2_gate1v_fallback_oracle_preflight_20260706.json` | Gate1V-2 fallback oracle preflight | `BLOCKED_GATE1V2_FALLBACK_ORACLE_PREFLIGHT_NO_LIVE_RELEASE_MISSING_FROZEN_SCORE_CAPABLE_ACTION_STREAM` | 0-live preflight result，不释放 live。最近 fallback route 是 Franka POC `level1_open_door`；metric 侧已明确：`manip/default/check_joint_angle` 读 `obj_DryingBox_01/RevoluteJoint`，成功范围 `30-120deg`，`succ_cnts=59`，future live 必须写出 `result_info.json` 的 `score` / `success_rate` / `log_info.metric_score`、action log、metric trace 和 render/readback。但 preflight 当前 blocked：实际 EBench Franka config 只在外部 GenManip dirty worktree 中，native LabUtopia expert 只有 video/log success，没有 frozen EBench action stream 或 score-capable runner。下一步 Gate1V-2a 只做 config / runner / action-stream freeze，不启动 Isaac。 |
| `eos2_gate1v_2a_fallback_oracle_freeze_20260706.json` | Gate1V-2a fallback oracle freeze | `BLOCKED_GATE1V2A_FALLBACK_ORACLE_FREEZE_NO_LIVE_RELEASE_MISSING_SCORE_CAPABLE_ORACLE_RUNNER_AND_ACTION_STREAM` | 0-live freeze result，不释放 live。已冻结 Franka POC `level1_open_door` EBench config 到 `eos2_gate1v_2a_fallback_oracle_freeze_20260706/frozen_configs/level1_open_door.yml`，sha256 `e78e5f4b58a39b15bc9146436bf50249b850f71b1171e3f671bbd95e9d58956e`；metric 仍是 `obj_DryingBox_01/RevoluteJoint`、`30-120deg`、`succ_cnts=59`。但 score-capable oracle runner 和 EBench 可执行 expert action stream / deterministic route 未冻结；两个 LabUtopia probe 均为 diagnostic/no-score，历史 `native_expert_oracle` result_info 为 `score=0.0` 且 `metric_score=[]`，不能作为专家已得分证据。下一步只做 runner/action-source contract，不启动 Isaac。 |
| `eos2_gate1v_2b_runner_action_source_contract_20260706.json` | Gate1V-2b runner/action-source contract audit | `BLOCKED_GATE1V2B_RUNNER_ACTION_SOURCE_CONTRACT_NO_LIVE_RELEASE_NO_SCORE_CAPABLE_ORACLE_ACTION_SOURCE` | 0-live contract audit，不释放 live。正式 EBench evaluator/result_info 写出链路存在，但还没有冻结的 score-capable oracle runner 和 EBench 可执行 expert action source。只读扫描 73 个 Franka open-door `result_info.json`，全部 `score=0.0`、`success_rate=0`、`metric_score=[]`，没有历史证据可升级成 Expert Oracle Score。两个现有 probe 仍是 diagnostic/no-score。下一步需要在 GenManip/EBench runner 层开发 score-capable oracle runner，或转 `native_controller_research` / `asset_task_no_score_hardening`。 |
| `eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json` | Gate1V-2c score runner build plan | `PLANNED_GATE1V2C_SCORE_CAPABLE_ORACLE_RUNNER_NO_LIVE` | 0-live planning / implementation-readiness，不释放 live。2c 把 Gate1V-2b 后的缺口收敛成 GenManip/EBench runner-layer 任务：实现 score-capable oracle runner，并用 fake-client tests 证明 start job、reset、feed action、pending-reset polling、`episode_result` 和 authoritative `result_info.json` 处理。正式 score authority 是 `post_episode_process -> episode_result -> result_info.json`；diagnostic `metric`、`done_info.info`、no-score probe summary 和历史 `expert_oracle` 命名目录都不能当 benchmark score。2c 通过后也只允许进入 bounded score-live release review，不等于 Expert Oracle Score 完成。 |
| `eos2_gate1v_2c_score_capable_oracle_runner_code_checkpoint_20260706.json` | Gate1V-2c score runner code checkpoint | `CODE_READY_GATE1V2C_SCORE_CAPABLE_ORACLE_RUNNER_FAKE_CLIENT_CONTRACT_NO_LIVE` | code/test-only，不释放 live。GenManip 新增 `standalone_tools/labutopia_poc/score_capable_oracle_runner.py` 和 `tests/labutopia_poc/test_score_capable_oracle_runner.py`；TDD RED 为缺模块 ImportError，GREEN 后 focused `7 passed`，相邻 `test_episode_result_completion.py` 合跑 `12 passed`，`py_compile` 和 `diff --check` 通过。runner 会 start job、reset、喂 action、处理 `reset_pending`、读取 `episode_result`、校验 authoritative `result_info.json`，并在异常时保持 `score_claim_allowed=false`。早期缺 frozen source 的 blocker 已被 S0 freeze 关闭；S1 release review 已登记，当前仍缺 bounded score-chain live/result，所以不能 claim Expert Oracle Score。 |
| `eos2_gate1v_native_control_contract_research_20260706.json` | Gate1V-3 native-control contract research audit | `INCOMPLETE_GATE1V3_NATIVE_CONTROL_CONTRACT_RESEARCH_NO_LIVE_RELEASE_NO_FROZEN_DIFFERENT_CONTROL_SURFACE` | 0-live native lane audit，不释放 live，也不算 score。多 agent review + current-state source audit 认为当前没有冻结的 Lift2/R5a native control contract 能证明自己不同于已关闭的 `16D joint_position -> set_joint_position_targets -> world.step` 路线。已排除或降级的 candidate 包括 official prep-output、`step_chunk` / `step_chunk_size`、`base_motion`、`ee_pose` / planner / `custom_motion`、`physics_hold_steps`、max-effort repair 和 no-score `native_action_path_runner`。这不是 native-controller 大方向 no-go；它只说明未来必须先写 no-score `native_drive_target` contract spec + fake-client/readback harness，证明 target/applied/observed readback、units、frames 和 transport 都不只是旧 joint-position 路线换名，然后才允许 `native_research_live` 预发布审查。 |

## 2026-07-04 EOS-2xC7 Candidate / First Live Evidence

这个条目先记录下一轮只读诊断候选清单，再记录第一条 C7-A live witness 的结果。它的
作用是把“接下来该跑哪 6 行、每行继承哪个 C6 baseline、哪些证据路径存在、哪些源
manifest 还缺失、第一条 live run 到底失败在哪个硬门”写清楚，避免后续把 C6/C7、
LabUtopia/GenManip、smoke/oracle 的证据混用。

`Status` 列使用 PM/验收口径：`PASS` / `WARN` / `BLOCKED` / `PREPARED` 等。probe
内部的 raw status（例如 `PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER`）只写在含义里，不能直接升级成验收 PASS。

| File | Stage | Status | 含义 |
|---|---|---|---|
| `eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_candidates.tsv` | EOS-2xC7-A candidate queue | `PREPARED` | 6 行候选：`w024` / `w028` 各跑 attachment audit、collider owner audit、filter/offset readout。所有行都保持 `micro_pull_allowed=false`、`score_claim_allowed=false`、`physics_intervention_allowed=false`。 |
| `eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_base_attachment_audit/contact_frame_summary.json` | EOS-2xC7-A first live witness | `PARTIAL_NEGATIVE` / upstream `approach_near` hard gate failure | submit/probe 已跑通，`PhysX contact` debug channel 可用；但 run 没进入 `grasp_hold`，在 `approach_near` 达不到阈值后结束。因此 `contact_pair_count=0` 只能说明这次没有进入有效接触窗口，不能归因为 handle collider 不能生成接触。 |
| `eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_near_readback_20260704_124339/readback_summary.json` | EOS-2xC7-A bounded readback | `FAIL_CONTROLLER_READBACK_COMPARATOR_NO_IK_TARGET` | 按上一条结论追加的只读 `approach_near` comparator。它只执行 1 step，发现没有 successful `ee_pose` IK debug target，且 `ee_pose_target_position_error_m=0.5245884806528617`。这把问题进一步收窄到 approach target / IK / readback 链路，仍不是接触层证据。 |
| `eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_readback_20260704_125312/readback_summary.json` | EOS-2xC7-A comparator baseline | `FAIL_CONTROLLER_READBACK_COMPARATOR_DIAGNOSTIC_ONLY` | 只读 `approach_pre` comparator。它证明较早 waypoint 的 IK debug 能正常暴露，`parse_only_ik.ik_success=true`，但把同一个 IK target 单步下发会触发 `panda_joint4` 关节跳变过大。因此当时下一步应验证 bounded joint lead-in，而不是回到 contact/collider 归因。 |
| `eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_bounded_lead_in_20260704_130833/lead_in_summary.json` | EOS-2xC7-A bounded joint lead-in | `FAIL_BOUNDED_JOINT_LEAD_IN_DIAGNOSTIC_ONLY` | 把 `approach_pre` 的同一个 IK target 拆成 `0.05 rad` 小关节步长后，命令侧没有超过步长上限，但真实 readback 在 step 52-54 后段发散并触发 `arm_state_jump_too_large`。这说明问题已从“单步命令太大”进一步变成 target/orientation/reachability/controller stability，仍不能回到 contact/collider 归因。 |
| `eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_target_frame_reachability_audit_20260704_132909/target_frame_reachability_audit.json` | EOS-2xC7-A target-frame / reachability audit | `READ_ONLY_AUDIT_COMPLETE_DIAGNOSTIC_ONLY` | 派生审计，不是新 live run。它把 C7 first live、两个 comparator、bounded lead-in 和 EBench microwave 参考实现合并判断：当时 audited path 的 base frame 一致，不是主嫌；但这不排除后续 object-frame convention 仍需校验。当时 DryingBox waypoint 仍是 handle center + fixed world-X offset；comparator/lead-in 使用 fixed absolute orientation，和 full oracle 的 relative/identity 口径不同；当时下一步应转成 EBench microwave 风格的 object-frame waypoint + per-waypoint cuRobo planning。 |
| GenManip `object-frame-curobo-pose-ladder` code checkpoint, 2026-07-05 | EOS-2 Task 4b follow-up capability | `WARN` | raw status=`CODE_READY_NOT_LIVE_EVIDENCE_SUPERSEDED_BY_BRIDGE_LIVE_EVIDENCE`。probe 已支持 reset/readback-aware pose basis：`--pose-ladder-offset-y-m`、`--pose-ladder-offset-z-m`、`--pose-ladder-include-reset-pose-basis`，并会记录 `pose_ladder_reset_debug_excerpt`。这不是新 live run；该能力已被后续 richer ladder、reset seed、bridge ladder、Task 4c attribution、Task 4d.3 clearance evidence 和 Task 4d.4A frame-aware live evidence 消费。 |
| `eos2_object_frame_bridge_ladder_20260704_181425/pose_ladder_summary_compact.json` | EOS-2 reset-to-handle bridge ladder, no world refresh | `WARN` | raw status=`PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER`。no-refresh 模式下，第二个候选 `approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 生成 152 个 trajectory points。这证明 reset 到 handle 之间存在可规划中间点；但它没有启用 world obstacles，不能当作 collision-aware 或抓取/开门证据。 |
| `eos2_object_frame_bridge_ladder_20260704_181425/pose_ladder_world_refresh_summary_compact.json` | EOS-2 bridge ladder first world-refresh attempt | `BLOCKED` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_RESET_FAILED`。第一次 world-refresh 复跑在 reset 阶段被 Ray OOM 杀掉；这不是 planner/collision 证据，只记录 runtime resource blocker。 |
| `eos2_object_frame_bridge_ladder_20260704_181425/pose_ladder_world_refresh_retry2_summary_compact.json` | EOS-2 bridge ladder world-refresh retry2 | `BLOCKED` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP`。retry2 中 reset 成功，12 个候选的 world refresh 都成功，但 planner debug 全部是 `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`。该 blocker 已由后续 Task 4c classify evidence 归因到 table surface mesh vs `panda_hand`。 |
| `eos2_bridge_start_state_collision_attribution_code_checkpoint_20260705.json` | EOS-2 Task 4c bridge start-state collision attribution code checkpoint | `WARN` | raw status=`CODE_READY_NOT_LIVE_EVIDENCE`。GenManip 已补 cuRobo start-state collision 诊断字段；该 code checkpoint 已被后续 live classify evidence 消费。它本身不是 live Isaac 证据，不能进入 grasp、micro-pull、door opened 或 score。 |
| `eos2_bridge_start_state_collision_attribution_live_20260705_193305/pose_ladder_start_state_attribution_summary.json` | EOS-2 Task 4c first live attribution attempt | `WARN` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP`，diagnostic-only。12/12 个 bridge candidate 仍是 `INVALID_START_STATE_WORLD_COLLISION`，但第一版诊断使用 `get_sphere_distance(... compute_esdf=True)`，只能证明 diagnostic 执行过，不能定位具体 obstacle。该结果被后续 classify evidence supersede。 |
| `eos2_bridge_start_state_collision_attribution_live_classify_20260705_194133/pose_ladder_start_state_attribution_compact.json` | EOS-2 Task 4c classify live attribution | `BLOCKED` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP`，attributed。改用与 cuRobo `check_start_state` 一致的 `get_sphere_collision` classify 路径后，12/12 个 candidate 都归因到 `/World/labutopia_level1_poc/obj_table/surface/mesh`，robot link 是 `panda_hand`；world refresh 和 reset 都成功，诊断 restore 成功。 |
| `eos2_bridge_start_state_collision_attribution_ignore_table_surface_20260705_194441/pose_ladder_ignore_table_surface_compact.json` | EOS-2 Task 4c minimal ignore-list validation | `WARN` | raw status=`PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER`，diagnostic validation。只把 `/World/labutopia_level1_poc/obj_table/surface/mesh` 加到 diagnostic planner ignore-list 后，第一条 candidate 变为普通 `IK_FAIL`，第二条 `approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 在 world refresh 下成功规划 152 个点。这证明 table surface / `panda_hand` start-state collision 是 bridge blocker；ignore-list 仍不是正式产品修复。 |
| `eos2_support_surface_clearance_audit_stage_bbox_retry_20260704_212941/pose_ladder_support_surface_clearance_summary.json` | EOS-2 Task 4d.3 first stage-bbox live retry | `BLOCKED_ENV` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_RESET_FAILED`。server 端缺 conda `PATH` 与 Isaac CUDA 11 `LD_LIBRARY_PATH`，worker 创建时 cuRobo extension JIT 报 `libcudart.so.11.0` / `ninja` 问题，未进入 planner；该目录只保留为环境 blocker 证据。 |
| `eos2_support_surface_clearance_audit_stage_bbox_envfix_20260704_213347/pose_ladder_support_surface_clearance_compact.json` | EOS-2 Task 4d.3 live support-surface clearance audit | `BLOCKED_FRAME_AMBIGUOUS` / superseded by 4d.4A | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP`。按旧 live 环境修正 `PATH` / `LD_LIBRARY_PATH` 后，submit/probe exit code 都是 `0`，reset 成功，12/12 个 bridge candidate 进入 world-refresh planner；runtime 从 `stage_prim_path:/World/labutopia_level1_poc/obj_table/surface/mesh` 读到 table AABB，并写出 12 条 `support_surface_clearance_records`。旧记录都被 `sphere_vertically_intersects_support_surface` 阻断，第一条 table top z 约 `0.773m`、`panda_hand` sphere bottom z 约 `0.051m`、`clearance_margin_m=-0.722m`；但 2026-07-05 frame 复核确认 cuRobo spheres 是 planner/reference frame，不是 USD world frame，不能直接和 world AABB 比较。因此该 evidence 只能证明 table surface / `panda_hand` 是 bridge blocker，不能证明真实物理穿桌。 |
| `eos2_support_surface_frame_contract_code_checkpoint_20260705.json` | EOS-2 Task 4d.4A diagnostic contract repair | `WARN` | raw status=`CODE_READY_NOT_LIVE_EVIDENCE`。Code/unit evidence only；`CuroboPlanner` sphere debug 改为 `sphere_center_planner_frame` / `sphere_frame=planner_reference_frame`；support-surface clearance builder 遇到 frame 不一致时输出 `clearance_status=unverified_frame_mismatch` 并禁止 planner-only exclusion；随后补上 world AABB -> planner/reference frame transform 合同。验证：`test_curobo_start_state_collision_diagnostics.py` 2 passed；`test_plan_object_frame_waypoints_route_contract.py` 20 passed；相关文件 `py_compile` exit 0。 |
| `eos2_support_surface_frameaware_clearance_audit_20260704_221731/pose_ladder_support_surface_frameaware_compact.json` | EOS-2 Task 4d.4A live frame-aware support-surface clearance audit | `BLOCKED_SAME_FRAME_NEGATIVE_CLEARANCE` / superseded by 4d.4B | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP`。submit/probe exit code 都是 `0`，12/12 个 bridge candidate 都进入 world-refresh planner；12/12 条 support-surface records 都是 `planner_reference_frame` vs `planner_reference_frame` 的 `measured_same_frame`，`clearance_margin_m=-0.011760663122180937`，blocker 统一是 `sphere_vertically_intersects_support_surface`，planner-only exclusion allowed count 为 `0`。这说明旧 `-0.722m` 是 frame-mismatched，但同 frame 后仍是负 clearance；4d.4B 已继续用 base-z-lift 隔离验证，当前优先方向是正式 reset/base/joint contract，而不是 exact ignore table。 |
| `eos2_bridge_start_state_base_z_lift_002_20260704_223919/pose_ladder_base_z_lift_002_compact.json` | EOS-2 Task 4d.4B base-z-lift isolation | `WARN` / superseded by observed-base rerun | raw status=`PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER`，diagnostic-only。只把 Franka diagnostic base position 从 `[-0.4, 0.0, 0.71]` 改到 `[-0.4, 0.0, 0.73]`，其它资产、metric、planner 和 pose-ladder 参数不变；submit/probe exit code 都是 `0`。start-state collision 从上一轮 12/12 变成 `0`，第二个 bridge candidate 在 world refresh 下规划成功，`trajectory_point_count=152`。这说明 blocker 优先指向 reset/base clearance；base z +2cm 不是最终产品姿态，下一条 observed-base rerun 证明该 base pose 确实进入 robot prim。 |
| `eos2_reset_base_observed_pose_code_checkpoint_20260705.json` | EOS-2 Task 4d.4C observed robot base instrumentation | `WARN` | raw status=`CODE_AND_LIVE_EVIDENCE_READY_DIAGNOSTIC_ONLY`。GenManip debug state 已给 `debug.labutopia_open_door` 和 `pose_ladder_reset_debug_excerpt` 增加 `robot_prim_path`、`robot_world_position`、`robot_world_orientation_wxyz`。验证：`test_labutopia_oracle_debug_state.py` 26 passed；pose-ladder excerpt focused tests 2 passed；相关文件 `py_compile` exit 0。 |
| `eos2_bridge_start_state_base_z_lift_002_observed_base_20260704_225244/pose_ladder_base_z_lift_002_observed_base_compact.json` | EOS-2 Task 4d.4C observed-base live rerun | `WARN` | raw status=`PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER`，diagnostic-only。submit/probe exit code 都是 `0`；observed robot prim 是 `/World/labutopia_level1_poc/franka`，observed `robot_world_position=[-0.4000000059604645, 2.98e-10, 0.7300000190734863]`；start-state collision count 为 `0`，第二个 bridge candidate 仍规划成功，`trajectory_point_count=152`。这证明 base-z-lift 真实进入 Isaac/USD robot prim；它仍不是最终 reset policy。 |
| `eos2_reset_joint_readback_probe_checkpoint_20260705.json` | EOS-2 Task 4d.4D reset joint readback instrumentation | `WARN` | raw status=`CODE_AND_LIVE_EVIDENCE_READY_DIAGNOSTIC_ONLY`。`pose_ladder_reset_debug_excerpt` 新增 `state_joint_positions`，用于判断 `default_joint_positions` 是否真的进入 reset。验证：focused probe tests `2 passed, 262 deselected`；相关 probe/test `py_compile` exit 0。 |
| `eos2_bridge_start_state_reset_seed_retract_001_20260704_230558/pose_ladder_reset_seed_retract_001_readback_compact.json` | EOS-2 Task 4d.4D default-joint reset branch | `BLOCKED_RESET_SEED_NOT_SUFFICIENT` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP`，diagnostic-only。配置保持 base z=`0.71m`，加入 9D Franka reset seed `[0, -1.3, 0, -2.5, 0, 1.0, 0, 0.04, 0.04]`；live readback 看到 7D arm seed 基本进入 reset，EE pose 改为约 `[0.1106, 0, 0.5907]`，但 12/12 bridge candidate 仍是 `INVALID_START_STATE_WORLD_COLLISION`，blocker 仍是 table surface vs `panda_hand`。结论：只换 joint seed 不能作为当前最小闭环。 |
| `eos2_bridge_start_state_base_z_lift_002_only_20260704_231348/pose_ladder_base_z_lift_002_only_compact.json` | EOS-2 Task 4d.4D base-z-only promotion candidate | `PASS` / diagnostic promotion candidate | raw status=`PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER`，diagnostic-only。配置只把 Franka base position 从 `[-0.4, 0.0, 0.71]` 改到 `[-0.4, 0.0, 0.73]`，不设置 `solver_velocity_iteration_count`，也不关闭 `enabled_self_collisions`；observed base z=`0.730000019m`；start-state collision count 为 `0`；第二个 bridge candidate 规划成功，`trajectory_point_count=152`。结论：当前正式 reset contract 候选优先走 POC-specific base z=`0.73m` layout。 |
| `eos2_open_door_formal_reset_contract_checkpoint_20260705.json` | EOS-2 Task 4d.4E formal reset/base contract landing | `PASS_CONFIG_CONTRACT` | raw status=`FORMAL_CONFIG_UPDATED_WITH_DIAGNOSTIC_LIVE_BACKING`。正式 `franka_poc/level1_open_door.yml` 已接受 `position=[-0.4,0.0,0.73]`，不加入 `default_joint_positions`、solver override、self-collision disable 或 oracle debug obs；普通 open-door diagnostic configs 同步到 `0.73m`，`reset_seed_retract_001` 保留 `0.71m` 作为失败对照。验证：`test_franka_robot_config_contract.py` 7 passed。当时下一步是 bounded execution/readback，不是 score；该路线已被后续 Task 5A-5I 消费。 |
| `eos2_bounded_execution_base_z_073_20260704_233033/lead_in_base_z_073_compact.json` | EOS-2 Task 4d.4F bounded execution/readback on formal base-z contract | `BLOCKED_CONTROLLER_STABILITY` | raw status=`FAIL_BOUNDED_JOINT_LEAD_IN_DIAGNOSTIC_ONLY`。fresh server 下先暴露 `python -m genmanip_client.cli submit` 没有真正启动 job 的调用问题，已保留 `no_job_probe.*`；改用 `from genmanip_client.cli import main` 后 submit/probe exit code 都是 `0`。正式 run 中 `parse_only_ik.ik_success=true`，53 个 bounded lead-in 小步实际执行，但 step 51/52 readback 发散，terminal reason=`arm_state_jump_too_large`，最终 `reached_joint_target=false`。结论：reset/base/IK/diagnostic execution 链路可跑，但不能宣布 stable grasp、micro-pull、door opened、Expert Oracle Score 或 policy score；当时下一步转 EBench microwave 风格的 object-frame waypoint + per-waypoint cuRobo execution/readback，该路线已推进到 Task 5I。 |
| `eos2_planner_trajectory_export_code_checkpoint_20260705.json` | EOS-2 Task 5A planner trajectory export code checkpoint | `WARN` | raw status=`CODE_READY_NOT_LIVE_EVIDENCE`。planner-only `plan_object_frame_waypoints` 通道新增默认关闭的 `include_trajectory_points`；开启后每个 successful waypoint record 会保留 raw `trajectory_joint_positions` 作为 planner 审计证据，并保留 action-level `trajectory_action_joint_positions` / `trajectory_action_joint_names` / control type / replay policy 作为下一步 replay 输入。online probe 会把这些点写入 summary/trace，genmanip-client 能转发该 flag；non-finite trajectory 会失败为 `non_finite_trajectory_point`，不会输出坏 payload。它只提供下一步 bounded trajectory execution/readback 的输入，不执行 Isaac action，不改变 planner-only no-step/no-reset 合同，也不能汇报 stable grasp、micro-pull、door opened、Expert Oracle Score 或 score。 |
| `eos2_planner_trajectory_execution_readback_code_checkpoint_20260705.json` | EOS-2 Task 5B planner trajectory execution/readback code checkpoint | `WARN` | raw status=`CODE_READY_NOT_LIVE_EVIDENCE`。online probe 新增 `--probe-mode planner-trajectory-execution-readback`，会向 planner endpoint 请求 `include_trajectory_points=true`，只消费 `trajectory_action_joint_positions`，不把 raw `trajectory_joint_positions` 当 replay 合同；有 fresh job starter 时会先切到 `planner_trajectory_replay` run_id，再逐帧发送 absolute `joint_position` action，并记录 readback、terminal blocker、final joint tolerance 和 no-claim guards。review 后补了 action-only payload 支持、fresh-run 强制、`stable_grasp/micro_pull/score` 机器可读禁用字段。`005444` live 前又补了 pre-plan reset：先 reset 出 worker，再调用 `plan_object_frame_waypoints`；reset summary 只保留 compact 字段，不再把 video/camera 像素数组写入 evidence。 |
| `eos2_planner_trajectory_execution_readback_live_20260705_005444/planner_trajectory_execution_summary.compact.json` | EOS-2 Task 5B live rerun after worker lifecycle fix | `BLOCKED_PLANNER_IK` | raw status=`FAIL_PLANNER_TRAJECTORY_EXECUTION_PLANNER_FAILED`，diagnostic-only。fresh run 使用独立 `run_id`、`RAY_TMPDIR`、evidence dir 和端口；旧失败 `worker 0 does not exist` 已越过，summary 记录 `preplan_reset_attempted=true`、`preplan_reset_worker_obs_available=true`，server log 里 `/reset` 和 `/plan_object_frame_waypoints` 都返回 200。新的 blocker 在真实 planner 层：`approach_pre`、`approach_near`、`contact` 三个 waypoint 都是 `MotionGenStatus.IK_FAIL`，`trajectory_point_count=0`，所以没有 action trajectory 可 replay。不能汇报 stable grasp、micro-pull、door opened、Expert Oracle Score 或 score；下一步回到 object-frame target/orientation/reachability 校准。 |
| `eos2_planner_trajectory_explicit_waypoint_code_checkpoint_20260705.json` | EOS-2 Task 5C explicit object-frame planner waypoint contract | `WARN` | raw status=`CODE_READY_WITH_LIVE_EVIDENCE_CONSUMED`。online probe 新增 `--planner-trajectory-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`，允许 formal run 显式追加 object-frame waypoint；默认 `approach_pre` / `approach_near` / `contact` payload 不变。TDD 记录：新增测试先 RED 为 2 个 expected failure，修复后 2 passed；review 后补 non-finite translation guard；`planner_trajectory_execution_readback` focused tests 5 passed；整份 probe 单测 272 passed。 |
| `eos2_planner_trajectory_bridge_execution_readback_live_20260705_5c_0100/planner_trajectory_bridge_execution_summary.json` | EOS-2 Task 5C formal debug-absence negative control | `BLOCKED_FORMAL_DEBUG_ABSENCE` | raw status=`FAIL_PLANNER_TRAJECTORY_EXECUTION_PLANNER_FAILED`，diagnostic-only。该 run 仍尝试用 reset debug 动态生成 bridge waypoint；formal `level1_open_door.yml` reset observation 只保留标准字段并省略 `debug.labutopia_open_door`，所以 runtime planner records 只有默认三点，选中 bridge label 成为 synthetic failed record。它证明 debug observation 不能作为正式接口。 |
| `eos2_planner_trajectory_explicit_bridge_execution_readback_live_20260705_5c_0120/planner_trajectory_explicit_bridge_execution_summary.compact.json` | EOS-2 Task 5C explicit bridge live execution/readback | `PASS_DIAGNOSTIC_REPLAY` | raw status=`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`。formal `level1_open_door.yml` 下显式追加 bridge waypoint `approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity`；planner 生成 152 个 action-level trajectory points，probe replay 152 步，`reached_joint_target=true`，最终 joint target 误差约 `7.13e-05 rad`，小于 `0.02 rad` 阈值，`blockers=[]`。这证明 formal config 能消费显式 object-frame bridge 并执行到中间目标；仍不能声明 stable grasp、micro-pull、door opened、Expert Oracle Score 或 score。 |
| `eos2_planner_trajectory_post_replay_replan_code_checkpoint_20260705.json` | EOS-2 Task 5D post-replay replan/readback code checkpoint | `WARN` | raw status=`CODE_READY_WITH_LIVE_EVIDENCE_CONSUMED`。online probe 新增默认关闭的 `--planner-trajectory-post-replay-replan`、`--planner-trajectory-post-replay-waypoint-label`、`--planner-trajectory-post-replay-execute`；在 selected bridge replay 后，可不 reset worker，直接基于 post-replay worker state 再调用 `plan_object_frame_waypoints`，并把 `post_replay_replan` 与 follow-up action samples 写入 summary。验证：新增 TDD 先 RED 后 GREEN；focused tests 8 passed；整份 probe 单测 273 passed；`py_compile` 和 `git diff --check` 通过。 |
| `eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0200/summary_compact.json` | EOS-2 Task 5D post-replay continuation live evidence | `BLOCKED_POST_REPLAY_REPLAN_IK` | raw status=`FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，diagnostic-only。`5d_0130/5d_0145` 保留为环境 negative controls；`5d_0200` 用 conda env `bin` 和 Isaac `omni.cuda.libs` CUDA 11 runtime 修复 server 环境后进入真实 planner/replay。selected bridge waypoint 规划成功，生成 150 个 action-level points，probe replay 150 步，`reached_joint_target=true`，最终 joint target 误差约 `7.13e-05 rad < 0.02 rad`。随后 probe 在 post-replay worker state 上继续 replan 到 `approach_pre`，cuRobo 返回 `MotionGenStatus.IK_FAIL`，没有第二段 action trajectory；不能声明 stable grasp、micro-pull、door opened、Expert Oracle Score 或 score。 |
| `eos2_planner_trajectory_post_bridge_followup_sweep_code_checkpoint_20260705.json` | EOS-2 Task 5E post-bridge follow-up waypoint candidate sweep code checkpoint | `WARN` | raw status=`CODE_READY_NOT_LIVE_EVIDENCE`。online probe 新增 `--planner-trajectory-post-replay-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`，允许在 bridge replay 后传入一组 handle-side follow-up 候选点。重要语义：候选点是 alternatives，不是连续路径；因为 server-side `object_frame_waypoint_planner` 在同一次 call 内会把成功 waypoint 推进本地 `sim_js`，所以 5E probe 会逐个 candidate 单独调用 planner，汇总 `candidate_records`、`selected_waypoint_label`、`failure_status_counts`，默认选择第一个 `plan_success=true` 的候选。验证：`sweeps_post_replay_extra` 1 passed；`planner_trajectory_execution_readback or post_replay` 7 passed；`py_compile` 和 `git diff --check` 通过。它本身不是 live Isaac evidence；live 5E 结果见下一行。 |
| `eos2_planner_trajectory_post_bridge_followup_sweep_live_20260705_5e_0300/summary_compact.json` | EOS-2 Task 5E post-bridge follow-up waypoint candidate sweep live evidence | `BLOCKED_POST_BRIDGE_CANDIDATES_IK` | raw status=`FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，diagnostic-only。submit/probe exit code 都是 `0`，server 环境、worker reset、planner endpoint 和 selected bridge replay 都跑通；bridge waypoint 生成 150 个 action-level points，probe replay 150 步，`reached_joint_target=true`，最终 joint target 误差约 `7.12e-05 rad < 0.02 rad`。随后 probe 在 post-bridge worker state 上逐个扫描 4 个 follow-up candidate：`post_bridge_to_approach_pre_f_0p20/0p40/0p60/0p80`，4/4 都是 `MotionGenStatus.IK_FAIL`，`successful_candidate_count=0`，没有第二段 action trajectory。结论：5E 证明候选扫描工具和第一段桥接回放闭环，但这组“往旧 approach_pre 方向插值”的第二段候选不可达；下一步要围绕 post-bridge pose 本身系统扫 wrist orientation 和 handle-side translation，而不是继续直接回插到 stale `approach_pre`。仍不能声明 stable grasp、micro-pull、door opened、Expert Oracle Score 或 score。 |
| `eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json` | EOS-2 Task 5F post-bridge pose-centered continuation live evidence | `PASS_DIAGNOSTIC_CONTINUATION_REPLAY` | raw status=`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，diagnostic-only。submit/probe exit code 都是 `0`，18437 server 已停止且端口无监听残留。第一段 bridge waypoint 仍成功：150 个 action-level points，replay 150 步，`reached_joint_target=true`，最终 joint target 误差约 `8.01e-05 rad < 0.02 rad`。5F 不再沿 stale `approach_pre` 大步插值，而是从 post-bridge pose 周围扫 12 个候选；前 4 个局部 slerp/Y/X 候选仍是 `MotionGenStatus.IK_FAIL`，第 5 个 `post_bridge_local_z_m006_q_bridge` 成功，生成 33 个 action-level points，第二段 replay 33 步，`reached_joint_target=true`，最终 joint target 误差约 `6.79e-05 rad < 0.02 rad`。结论：我们已经找到“从桥接点继续小步移动”的第一条可执行第二段，下一步应把它固定为 5G close-hold staging 的前置段，并把 gripper close/pending 与移动分开；仍不能声明 stable grasp、micro-pull、door opened、Expert Oracle Score 或 score。 |
| `eos2_planner_trajectory_post_replay_close_hold_code_checkpoint_20260705.json` | EOS-2 Task 5G post-replay close-hold staging code checkpoint | `WARN` | raw status=`PASS_CODE_CHECKPOINT_DIAGNOSTIC_ONLY`。GenManip probe 已新增 `--planner-trajectory-post-replay-close-hold-steps`。语义是：只有 bridge replay 和 5F 的 `post_bridge_local_z_m006_q_bridge` continuation 都执行后，才保持最终 7 个 arm joints 不动，把两个 Franka finger joints 命令到 `close_width_m` 并 pending N 步。新增 summary key 是 `post_replay_close_hold`，sample key/type 是 `planner_trajectory_post_replay_close_hold_action`。验证：focused tests `4 passed in 0.47s`，probe `py_compile` exit 0，GenManip diff check exit 0。该 checkpoint 只证明 close-hold stage 已可被 probe 调用和记录；还没有 live 5G、PhysX contact retention、stable grasp、micro-pull、door-open 或 score 证据。 |
| `eos2_planner_trajectory_post_replay_close_hold_live_20260705_5g_0500/summary_compact.json` | EOS-2 Task 5G post-replay close-hold live evidence | `PASS_DIAGNOSTIC_CLOSE_HOLD_READBACK` | raw status=`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，diagnostic-only。submit/probe exit code 都是 `0`，18438 server 已停止且端口无监听残留。复跑前先修了一个证据读取缺口：GenManip 标准 obs 把 7D arm 放在 `state.joints`、2D finger 放在 `state.gripper`，probe 原先只读 `state.joints`，导致 finger width readback unavailable；现在已按 TDD 修为优先读 9D `state.joints`，否则读 split `state.gripper`。live 结果：bridge replay 148 步，最终 joint target 误差约 `8.36e-05 rad < 0.02 rad`；第二段仍选择 `post_bridge_local_z_m006_q_bridge`，replay 31 步，误差约 `8.07e-05 rad < 0.02 rad`；close-hold 执行 15 步，arm 保持误差约 `8.43e-05 rad < 0.02 rad`，finger width 从约 `0.03533m` 收到约 `0.01280m`，目标 `close_width_m=0.010m`。这证明 close command/readback 链路进入真实 Isaac；仍没有 PhysX/contact retention、stable grasp、micro-pull、door-open 或 score 证据。 |
| `eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json` | EOS-2 Task 5H post-replay contact-retention code checkpoint | `WARN` | raw status=`PASS_CODE_CHECKPOINT_DIAGNOSTIC_ONLY`。5G 已证明真实 Isaac 里能执行 close-hold 并读回 finger width；5H 现在补的是下一层诊断仪表：每个 `planner_trajectory_post_replay_close_hold_action` sample 都能记录 `post_close_contact_frame`，summary 写入 `post_replay_close_hold.retention_summary`，用于区分“手指确实闭上了”和“左右 finger 是否真的靠近/重叠 handle、PhysX 是否有 required-role contact”。验证：focused tests `4 passed in 0.25s`，probe/test `py_compile` exit 0，GenManip diff check exit 0。这个 checkpoint 本身不能 claim stable grasp、micro-pull readiness、door-open、Expert Oracle Score、policy score、official leaderboard score 或 full task completion；live 5H 结论见后两行。 |
| `eos2_planner_trajectory_post_replay_contact_retention_live_20260705_5h_0430/summary_compact.json` | EOS-2 Task 5H live negative control without debug obs | `BLOCKED_CONTACT_FRAME_MISSING_DEBUG_OBS` | raw status=`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，diagnostic-only。submit/probe exit code 都是 `0`，18439 server 已停止。bridge + continuation + close-hold 都执行到位，close-hold 15 步，最终 arm joint target 误差约 `8.27e-05 rad < 0.02 rad`，finger width 约 `0.01280m`。但 server 只开了 `LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1`，没有开 `LABUTOPIA_ORACLE_DEBUG_OBS=1`；这版 evaluator 只有在 `DEBUG_OBS=1` 时才会把 `evaluator_last_action_application_debug/contact_debug` 写进 obs，所以 `post_close_contact_frame.available=false` 且 reason=`missing_action_application_debug`。该 run 证明 5H live 必须同时开启 `LABUTOPIA_ORACLE_DEBUG_OBS=1` 和 `LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1`；不能据此判断 stable grasp 或 contact retention。 |
| `eos2_planner_trajectory_post_replay_contact_retention_debugobs_live_20260705_5h_0440/summary_compact.json` | EOS-2 Task 5H live contact-retention readback | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | raw status=`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，diagnostic-only；这里的 raw PASS 只表示诊断 motion/readback 跑完，不表示 grasp 或 task success。submit/probe exit code 都是 `0`，18440 server 已停止。server 同时开启 `LABUTOPIA_ORACLE_DEBUG_OBS=1` 和 `LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1` 后，contact telemetry 已可用：`tail_physx_contact_status_counts.available=15`。动作层面仍然通过：close-hold 执行 15 步，`reached_joint_target=true`，final joint target 误差约 `8.27e-05 rad`，最后 finger width 约 `0.01280m`。但抓持没有形成：`retention_pass=false`、`tail_bilateral_overlap_pass=false`、`tail_physx_required_roles_contact_records=0`，最后一帧 `post_close_contact_frame.classification=OUTSIDE_PRE_CLOSE_CONTACT_FRAME`，左右 finger 均没有 near/overlap handle，最大 required-role axis gap 约 `[0.1353, 0.0692, 0.0]m`；`finger_width_max_pass=false` 是因为 15 步 tail 包含闭爪过渡帧，不能解读成最终宽度失败或抓取成功。下一步不是 micro-pull，而是用 contact-frame readback 调 handle-side contact pose；只有左右 finger 在 tail window 内同时 near/overlap handle，且 `retention_requires_physx_contact=true` 时 required-role PhysX contact 也通过，才进入 micro-pull。仍不能 claim stable grasp、micro-pull readiness、door-open、Expert Oracle Score、policy score、official leaderboard score 或 full task completion。 |
| `eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0610/summary_compact.json` | EOS-2 Task 5I negative control | `BLOCKED_NO_SUBMIT` | 该目录保留为流程负控：第一次 5I run 没有先 `submit.start_job(...)`，所以 reset/preplan 失败，post-replay candidate 没有真正被尝试。它不能作为 contact-frame 或 IK 结论，只用于提醒后续 evidence 必须同时保存 `submit.command.txt` / `submit.exitcode.txt`。 |
| `eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0620/summary_compact.json` | EOS-2 Task 5I first contact-frame candidate | `BLOCKED_POST_REPLAY_IK` | `cf_right_050` 从 5H 成功的 `post_bridge_local_z_m006_q_bridge` 出发，沿 contact-frame gap 做约 5.6cm 的半量校正；bridge replay 仍成功，但 post-replay replan 返回 `MotionGenStatus.IK_FAIL`，`successful_candidate_count=0`，没有 close-hold 或 retention 证据。结论：半量 gap 校正太大，不能进入 micro-pull。 |
| `eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0630/summary_compact.json` | EOS-2 Task 5I coarse micro candidate | `BLOCKED_POST_REPLAY_IK` | `cf_micro_x010_y008` 把位移缩到约 1cm / 8mm，仍是 `MotionGenStatus.IK_FAIL`。这证明问题不是只把 5.6cm 改小一点就能解决；fixed bridge quaternion 附近的可达域很窄。 |
| `eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0640_baseline_z_m006/summary_compact.json` | EOS-2 Task 5I harness baseline | `PASS_DIAGNOSTIC_BASELINE_REPLAY` | 同一个 5I server/harness 复现 `post_bridge_local_z_m006_q_bridge`：post-replay replan 成功、执行 31 步、close-hold 15 步、`reached_joint_target=true`。但 retention 仍失败，required-role near/overlap 和 PhysX contact 都是 `0`。结论：5I harness 没坏；blocker 是后续 contact correction 的 IK / contact corridor，不是 server 或命令问题。 |
| `eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0650_cf_right_005mm/summary_compact.json` | EOS-2 Task 5I 5mm mixed-direction probe | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | `cf_right_005mm_from_z` 可规划、可执行，且 close-hold 已执行并读回到目标，但 retention 仍失败。相对 baseline，它让 required-role world X gap 略变小，但 world Y gap 变大；这暴露出 `signed_axis_gap_m` 是 world AABB gap，不能直接当 object-frame x/y 同向修正。 |
| `eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0700_obj_y_p005/summary_compact.json`, `...5i_0710_obj_x_m005/summary_compact.json`, `...5i_0720_obj_x_m005_y_p005/summary_compact.json`, `...5i_0730_obj_x_m002_y_p002/summary_compact.json` | EOS-2 Task 5I correct-direction paired correction attempts | `BLOCKED_POST_REPLAY_IK` | 坐标复核后，减小 world X gap 应 object-frame `Y+`，减小 world Y gap 应 object-frame `X-`。但 correct-direction 的 `Y+5mm`、`X-5mm`、`X-5mm/Y+5mm` 以及 `X-2mm/Y+2mm` 均 `IK_FAIL`，没有 close-hold evidence。结论：fixed quaternion 下同时做正确双轴接触校正不可达。 |
| `eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0740_obj_y_p002/summary_compact.json`, `...5i_0750_obj_x_m002/summary_compact.json` | EOS-2 Task 5I single-axis 2mm corridor probes | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | 单轴 `Y+2mm` 和 `X-2mm` 都能规划、执行，且 close-hold 已执行并读回到目标，但 retention 仍失败。`Y+2mm` 主要降低 world X gap、轻微恶化 world Y gap；`X-2mm` 主要降低 world Y gap、轻微恶化 world X gap。结论：fixed quaternion 下有极窄单轴 corridor，但单轴不能让左右 finger 同时 near/overlap handle，双轴组合又会 IK_FAIL；下一步应从纯 translation sweep 升级到 orientation-aware / approach-seed / staged correction。仍不能 claim stable grasp、micro-pull readiness、door-open、Expert Oracle Score、policy score、official leaderboard score 或 full task completion。 |
| 5J summary after `eos2_contact_retention_orientation_aware_live_20260705_5j_0850_ori_z_p02/summary_compact.json` | EOS-2 Task 5J orientation-only 2deg live summary | `SUPERSEDED_BY_5K_A_LIVE` | Orientation-only 六条 2deg live 候选 5J-A 到 5J-F 已全部跑完。5J-A/C/D/F 可走到 close-hold 但 strict retention 失败；5J-B/E 是 post-replay `MotionGenStatus.IK_FAIL`。5J-F 的 Z+2deg 是第一条双指 world X gap 一致略小的线索，但 world Y gap 变大，所以不是 stable grasp。该线索已被 5K-A 单候选 live probe 消费；当前不再停留在 prepared review，也不能进入 micro-pull 或 score。 |
| `eos2_contact_retention_orientation_aware_staged_correction_20260705_5j_candidates.json` | EOS-2 Task 5J orientation-aware staged correction candidate manifest | `CONSUMED_BY_5J_AND_5K_A` | 5I 已证明 fixed-quaternion pure translation 不能同时满足 reachability 和 contact retention。5J 候选沿用历史 right-multiply quaternion 规则 `q_candidate = q_bridge * axis_angle(axis, deg)`；原 manifest 计划先在 `post_bridge_local_z_m006_q_bridge` 基线上测 2deg orientation delta，再评估 single-axis 2mm translation + orientation。该 manifest 已被 5J-A 到 5J-F 和 5K-A live evidence 消费；不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。 |
| `eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02/summary_compact.json` | EOS-2 Task 5J-A first z_m006 + orientation live candidate | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | `ori_y_m02_z_m006` 首跑已经越过 IK：submit/probe exit code 都是 `0`，18443 server 已停止；raw status 是 `PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，只表示诊断 motion/readback 跑完，不表示任务成功。bridge replay 执行 150 步、post-replay candidate 执行 42 步、close-hold 执行 15 步，三段都 `reached_joint_target=true`，最终 joint target 误差约 `7.12e-05 rad < 0.02 rad`。注意这个候选是 `z_m006` continuation 加 Y-2deg orientation delta：相对 bridge waypoint 的 object-frame z 位移是 `-0.006m`，相对 `post_bridge_local_z_m006_q_bridge` 基线没有新增 translation。但 retention 仍失败：tail bilateral overlap / required-role near / required-role PhysX contact 都是 `0`，15/15 tail records 都是 `AABB_OUTSIDE_CONTACT_FRAME`；最后 left/right finger axis gap 约为 left `[0.1315, 0.0533, 0.0]m`、right `[0.0858, 0.0669, 0.0]m`。结论：`z_m006 + Y-2deg` 可达，但没有把 finger 带到 handle 两侧；仍不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。该行当时触发同轴反号和 x/z orientation delta；这些 orientation-only 对照已由 5J-B 到 5J-F 完成。 |
| `eos2_contact_retention_orientation_aware_live_20260705_5j_0810_ori_y_p02/summary_compact.json` | EOS-2 Task 5J-B same-axis opposite orientation candidate | `BLOCKED_5J_ORIENTATION_IK` | `ori_y_p02_z_m006` 是 5J-A 的同轴反号对照：同样基于 `z_m006` continuation，但 orientation delta 从 Y-2deg 换成 Y+2deg。submit/probe exit code 都是 `0`，18444 server 已停止；raw status 是 `FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`。bridge replay 仍成功，执行 151 步，`reached_joint_target=true`，final joint error 约 `7.13e-05 rad < 0.02 rad`。失败点在 post-replay replan：`successful_candidate_count=0`，`failure_status_counts={"MotionGenStatus.IK_FAIL": 1}`，没有 `trajectory_action_joint_positions`，所以 close-hold 被 `no_post_replay_worker_state` 跳过，retention telemetry 不可用。结论：在当前 post-bridge worker state / `z_m006` baseline 下，Y+2deg 不是可用于后续 contact tuning 的方向；不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。下一步应继续在同一个 `z_m006` 基线上逐条跑 x/z orientation delta，而不是把 Y+2deg 直接和 2mm translation 组合。 |
| `eos2_contact_retention_orientation_aware_live_20260705_5j_0820_ori_x_m02/summary_compact.json` | EOS-2 Task 5J-C x-axis orientation candidate | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | `ori_x_m02_z_m006` 是 x 轴负号候选：同样基于 `z_m006` continuation，加 X-2deg orientation delta。submit/probe exit code 都是 `0`，18445 server 已停止；raw status 是 `PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，只表示诊断 motion/readback 跑完，不表示任务成功。bridge replay 执行 156 步、post-replay candidate 执行 31 步、close-hold 执行 15 步，三段都 `reached_joint_target=true`，最终 joint target 误差约 `8.08e-05 rad < 0.02 rad`。但 retention 仍失败：tail bilateral overlap / required-role near / required-role PhysX contact 都是 `0`，15/15 tail records 都是 `AABB_OUTSIDE_CONTACT_FRAME`。最后 gaps 约为 left `[0.1346, 0.0554, 0.0]m`、right `[0.0890, 0.0698, 0.0]m`，比 5J-A 的 Y-2deg 样本更大。结论：X-2deg 可达但没有改善 contact gaps；仍不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。后续 X+2deg 已作为 5J-D 跑完，见下一行；不要把 X-2deg 直接和 2mm translation 组合。 |
| `eos2_contact_retention_orientation_aware_live_20260705_5j_0830_ori_x_p02/summary_compact.json` | EOS-2 Task 5J-D x-axis opposite orientation candidate | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | `ori_x_p02_z_m006` 是 X+2deg 候选：同样基于 `z_m006` continuation。submit/probe exit code 都是 `0`；18446 server 使用 foreground exec session 持有，probe 后已停止，背景启动失败原因另有 `server_attempt*_not_ready_note.txt` 记录，这是 harness 运行方式记录，不影响 5J-D 证据结论。raw status 是 `PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`，只表示诊断 motion/readback 跑完，不表示任务成功。bridge replay 执行 151 步、post-replay candidate 执行 78 步、close-hold 执行 15 步，三段都 `reached_joint_target=true`，最终 joint target 误差约 `7.13e-05 rad < 0.02 rad`。但 retention 仍失败：tail bilateral overlap / required-role near / required-role PhysX contact 都是 `0`，15/15 tail records 都是 `AABB_OUTSIDE_CONTACT_FRAME`。最后 gaps 约为 left `[0.1352, 0.0564, 0.0]m`、right `[0.0888, 0.0692, 0.0]m`；相对 best-so-far 5J-A 在所有 required-role X/Y gaps 上仍更差，相对 5J-C 只轻微改善 right finger、同时恶化 left finger，不是相对所有 required-role X/Y gaps 的稳定改善方向。结论：X 轴正负号都不能进入 translation 组合；下一步转 z 轴 2deg orientation delta。仍不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。 |
| `eos2_contact_retention_orientation_aware_live_20260705_5j_0840_ori_z_m02/summary_compact.json` | EOS-2 Task 5J-E z-axis orientation candidate | `BLOCKED_5J_ORIENTATION_IK` | 白话结论：bridge replay 正常，Z-2deg candidate 已被提交和尝试，但 post-replay replan 返回 `MotionGenStatus.IK_FAIL`，所以没有 selected waypoint / action points；顶层 `waypoint_not_found` 不是标签漏写。Z+2deg 对照已由 5J-F 完成，见下一行。证据细节：submit/probe exit code 都是 `0`，18447 server probe 后已停止并释放；bridge replay 执行 150 步并达到 joint target，最终 joint target 误差约 `7.13e-05 rad < 0.02 rad`。close-hold 没有成功的 post-replay action trajectory 可承接，因此被 `no_post_replay_worker_state` 跳过，retention telemetry 不可用。结论：Z-2deg 不可用于 contact tuning，同样不直接叠 translation。仍不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。 |
| `eos2_contact_retention_orientation_aware_live_20260705_5j_0850_ori_z_p02/summary_compact.json` | EOS-2 Task 5J-F z-axis opposite orientation candidate | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | `ori_z_p02_z_m006` 是 Z+2deg 候选：同样基于 `z_m006` continuation。submit/probe exit code 都是 `0`，18448 server probe 后已停止并释放。bridge replay 执行 151 步、post-replay candidate 执行 41 步、close-hold 执行 15 步，三段都达到 joint target；最终 joint target 误差约 `7.24e-05 rad < 0.02 rad`。但 retention 仍失败：tail bilateral overlap / required-role near / required-role PhysX contact 都是 `0`，15/15 tail records 都是 `AABB_OUTSIDE_CONTACT_FRAME`。最后 gaps 约为 left `[0.1295, 0.0571, 0.0]m`、right `[0.0838, 0.0691, 0.0]m`。相对 best-so-far 5J-A，Z+2deg 让左右手指 world X gap 都略小，但 world Y gap 都变大；它不是 stable retention improvement，但这是 orientation-only 里第一条双指 X-gap 一致改善信号。该信号已被 5K-A live candidate 消费，仍不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。 |
| `eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json` | EOS-2 Task 5K staged-combination review candidate | `CONSUMED_BY_5K_A_LIVE` | 5K 不是直接宣布组合 translation 已批准，而是把 5J-F 的 Z+2deg 信号和 5I 的 object-frame X-2mm 单轴 correction 收敛成一个可审阅候选：`x_m002_ori_z_p02`。它的目标是保留 Z+2deg 对双指 world X gap 的轻微改善，同时尝试补偿 world Y gap。该 manifest 是 live 前 review artifact；后续 5K-A 已按单候选执行，仍不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。 |
| `eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json` | EOS-2 Task 5K-A staged-combination live candidate | `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME` | `x_m002_ori_z_p02` 已按 review 决策跑完单候选 live probe。submit/probe exit code 都是 `0`，18449 server probe 后已停止并释放；server lifecycle 只证明诊断链路干净，不表示任务成功。post-replay replan 成功，`successful_candidate_count=1`、selected waypoint 是 `x_m002_ori_z_p02`、可执行 action points 为 `40`；close-hold 执行 `15` 步并达到 joint target，最终误差约 `7.25e-05 rad < 0.02 rad`。失败点仍是 contact retention：`retention_pass=false`、tail bilateral overlap / required-role near / required-role PhysX contact 都是 `0`，15/15 tail records 是 `AABB_OUTSIDE_CONTACT_FRAME`。最后 gaps 为 left `[0.1302, 0.0553, 0.0]m`、right `[0.0844, 0.0673, 0.0]m`；相对 5J-F，5K-A 双指 Y gap 改善约 `1.8mm` 但 X gap 恶化约 `0.6mm`；相对 5J-A，X gap 改善但 Y gap 变差。结论：5K-A 把问题从单轴线索推进到“gap tradeoff 仍未闭合”，不是 stable grasp。下一步不能 micro-pull，应分析更小 staged correction 或切换到 contact-frame / handle-frame target generation。 |

当前下一阶段计划是 Task 5L `contact-frame / handle-frame target generation`，计划文档为
[`../../superpowers/plans/2026-07-05-eos2-contact-frame-handle-frame-target-generation.md`](../../superpowers/plans/2026-07-05-eos2-contact-frame-handle-frame-target-generation.md)。
该阶段采用 EBench `microwave` 的同类思路：用 task-level manual `custom_motion`
waypoints、object-frame / robot-frame staging 和 cuRobo runtime planning 生成可执行轨迹，
而不是 replay 资产里的旧 `skill_trajectory`。它的输入是 5K-A 暴露出的 contact-frame
gap tradeoff；它的输出先是 prepared manifest 和单候选 live evidence。只有 retention、
required-role near/overlap 和 required-role PhysX contact 同时通过后，才允许进入
micro-pull 或 score。

2026-07-05 Task 5L prepared review manifest 已生成：
`eos2_contact_frame_handle_frame_target_generation_review_20260705_5l_candidates.json`。它不是
live evidence，状态是 `PREPARED_REVIEW_NOT_LIVE_EVIDENCE`。当前只锁定一个保守候选
`5l_cf_handle_right_025_clamped_xy12_zp02`：使用 5K-A right finger tail gap
`[0.084393376008, 0.067267486749, 0.0]`，按 `scale_factor=0.25` 并把 X/Y shift 都 clamp 到
`0.012m`，得到 `contact_offset_x_m=0.007`、`center_offset_y_m=0.012`、
`center_offset_z_m=-0.006`、`orientation_offset_z_deg=2.0`。配套合同测试已加入
GenManip `test_online_open_door_oracle_probe.py`，focused test 结果是 `4 passed, 273 deselected`。
注意：正式 live runtime 仍使用
`/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python`；
该 env 当前没有 `pytest`，所以这次纯 Python 合同测试使用
`/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python`。

2026-07-05 Task 5L single-candidate live probe 已完成，证据目录是
`eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/`，
compact manifest 是 `summary_compact.json`。submit/probe exit code 都是 `0`，server 使用
foreground exec session 持有，probe 后 Ctrl-C 停止，端口 `18450` 已验证释放。第一段 bridge
replay 成功：`approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 生成并执行
`151` 个 action points，最终 joint target 误差约 `7.13e-05 rad < 0.02 rad`。但 5L 候选
`5l_cf_handle_right_025_clamped_xy12_zp02` 在 post-replay replan 阶段失败：
`successful_candidate_count=0`、`available_action_points=0`、
`failure_status_counts={"MotionGenStatus.IK_FAIL": 1}`。因此 close-hold 被
`no_post_replay_worker_state` 跳过，retention telemetry 不可用。分类是
`BLOCKED_5L_HANDLE_FRAME_TARGET_IK`，不是 stable grasp 失败，更不是 micro-pull 或 score 失败。
下一步应把 5L 从“单个大 X/Y correction”收敛成 reachability ladder 或 smaller staged
handle-frame target review，再选择单候选 live；仍不能 claim stable grasp、micro-pull、
door-open、Expert Oracle Score、policy score、official score 或 full task completion。

2026-07-05 Task 5M 下一阶段计划已落文档：
`docs/superpowers/plans/2026-07-05-eos2-handle-frame-reachability-ladder.md`。通俗讲，5M
不是继续把 5L 那个大 correction 硬调，而是先用 GenManip 已有的 `centerline` /
`inner-face-corridor` / `bilateral-contact-frame` 候选生成逻辑，把“手应该站到把手哪一条中线”
拆成更小、可审阅、可单独 live 验证的候选。当前 focused test 已验证候选生成相关测试为
`12 passed, 265 deselected`。5M 的第一失败门会单独分类为 centerline solver input、IK
reachability、post-replay execution readback 或 contact retention；任何一门失败都不能升级成
micro-pull、door-open 或 `Expert Oracle Score`。
路线复核后补充一条工程边界：5L 的可比证据来自
`planner-trajectory-execution-readback` 的 post-replay candidate sweep，不能用 default oracle
live 结果冒充 5L 后续。因此 5M live 必须走 route-bound post-replay candidate：要么是手填的
`--planner-trajectory-post-replay-extra-object-frame-waypoint`，要么是生成式的
`--planner-trajectory-post-replay-candidate-source centerline`。

2026-07-05 route binding 已有 code checkpoint：
`eos2_handle_frame_reachability_ladder_route_binding_code_checkpoint_20260705.json`。GenManip 现在支持
`--planner-trajectory-post-replay-candidate-source centerline`，在 bridge replay 后用 live debug
state 生成 `centerline` / `inner-face-corridor` / `bilateral-contact-frame` 候选，并转成
`obj_DryingBox_01_handle` 的 object-frame waypoint 进入原来的 post-replay candidate sweep。
验证结果：route-binding/centerline/inner-face 相关测试 `21 passed, 259 deselected`；
planner-trajectory/post-replay 相关测试 `11 passed, 269 deselected`；`py_compile` exit `0`。
这是 `CODE_READY_NOT_LIVE_EVIDENCE`，不能 claim stable grasp、micro-pull、door-open、
Expert Oracle Score 或 score。

2026-07-05 Task 5M first route-bound live probe 已跑完：
`eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary_compact.json`。
这次不再是 default oracle，也不是路线未绑定；probe command 明确使用
`--probe-mode planner-trajectory-execution-readback` 和
`--planner-trajectory-post-replay-candidate-source centerline`。第一段 bridge replay 仍然稳定：
`approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 执行 `151` 步，
`reached_joint_target=true`，最终 joint error 约 `8.50e-05 rad < 0.02 rad`。但这 `151`
步只代表 bridge replay 成功，不代表 post-replay candidate、close-hold 或 retention 成功。
新的失败点发生在 bridge 后的 generated centerline candidate / post-replay replan 入口：
`candidate_count=0`、`available_action_points=0`、`failure_status_counts={}`，
`replan_error=TypeError("float() argument must be a string or a real number, not 'NoneType'")`。
因此这次分类是 `BLOCKED_5M_CENTERLINE_SOLVER_INPUT`，产品口径可理解为
“route-bound post-replay replan 暴露了新的 live-state / waypoint input blocker”。它不是
centerline IK 失败，也不是 contact retention 失败，因为没有生成 candidate planner record，
close-hold 执行步数是 `0`，retention summary 是 `no_post_replay_worker_state`。下一步先修
centerline live-state / waypoint input，再重跑同一候选；仍不能 claim stable grasp、
micro-pull、door-open、Expert Oracle Score、policy score、official score 或 full task
completion。

2026-07-05 Task 5M state-reference rerun 已完成：
`eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias_state_reference/summary_compact.json`。
这次复跑保留同一个 route-bound 5M 候选，但先修正了两类输入问题：post-replay centerline
calibration 改用 `state.ee_pose`，`grasp_selection_axis_gap_threshold_m=None` 也会 fallback 到
pre-close threshold。验证结果在 compact 里记录为 focused pytest
`13 passed, 267 deselected`、`py_compile` exit `0`、`git diff --check` exit `0`。live
结果显示第一段 bridge replay 仍执行 `151` 步并达到 joint target，final joint error 约
`7.10e-05 rad < 0.02 rad`；`replan_error=null`，说明旧 `NoneType` 输入 bug 已越过。新的第一失败门是
`post_replay_centerline_candidate_solver_no_candidate`：`candidate_count=0`、
`attempted_candidate_count=0`、`available_action_points=0`、`failure_status_counts={}`，
`candidate_failure_reason=PAD_DEPTH_MISS`，`reference_source=state.ee_pose`。这仍分类为
`BLOCKED_5M_CENTERLINE_SOLVER_INPUT`，但含义已经从“输入坏了”推进到“几何候选求解器没有找到满足
bilateral contact-frame 的把手中线”。诊断里 world X interval 是
`[0.8913130708603386, 0.8816189957111638]`，上下界反向约 `9.7mm`，而当前
`contact_frame_axis_gap_threshold_m=0.006`。下一步不应直接重跑 full planner；先在同一
post-replay state 上做 candidate-only preflight，把 bilateral contact-frame tolerance 或等价 handle
padding 在 `0.010m` 到 `0.012m` 附近扫出 `candidate_count>0`，再进入完整 Isaac planner live。
仍不能 claim centerline cuRobo plan、close-hold、contact retention、stable grasp、micro-pull、
door-open、Expert Oracle Score 或 score。

2026-07-05 Task 5M candidate-only preflight code checkpoint 已生成：
`eos2_handle_frame_reachability_ladder_candidate_preflight_code_checkpoint_20260705.json`。这一步不是
live success evidence，而是为了防止盲目重跑 full Isaac planner：GenManip 新增
`--planner-trajectory-post-replay-candidate-preflight-only`，在 bridge replay 后只生成
post-replay centerline candidate metadata / object-frame waypoint，然后在调用 post-replay cuRobo
planner 前停止。验证：新增 focused test `2 passed, 280 deselected`，相关 post-replay /
centerline / inner-face / threshold / handle padding 测试 `44 passed, 238 deselected`；
`py_compile` 和 `git diff --check` 都是 exit `0`。后续有限矩阵只扫
`grasp_selection_axis_gap_threshold_m=[0.006,0.008,0.0095,0.010,0.011,0.012,0.014]` 和
`grasp_contact_model_handle_x_padding_m=[0.003,0.0048,0.005,0.006,0.008,0.010,0.012]`。如果这两组都不能让
`candidate_count>0`，就停止 5M centerline tuning，分类为
`BLOCKED_5M_CENTERLINE_MODEL_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`，不继续扩大 offset 硬调。

2026-07-05 Task 5M candidate-only bounded preflight 已完成：
`eos2_handle_frame_reachability_ladder_live_20260705_5m_candidate_preflight_bounded_sweep/summary_compact.json`。
实际跑完 `14` 个预设点，`candidate_found=false`：axis-gap 7 个点
`[0.006,0.008,0.0095,0.010,0.011,0.012,0.014]` 全部 `candidate_count=0`；
handle-x-padding 7 个点 `[0.003,0.0048,0.005,0.006,0.008,0.010,0.012]` 也全部
`candidate_count=0`。失败原因前半段主要是 `PAD_DEPTH_MISS`，后半段变为
`HANDLE_NOT_BETWEEN_INNER_FACES`。通俗讲，bridge replay 能把手臂带到门把手附近，但当前
`centerline + inner-face-corridor + bilateral-contact-frame` 候选模型仍然不能把真实门把手解释成一个
合法抓取点。因此这一步正式分类为
`BLOCKED_5M_CENTERLINE_MODEL_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`。下一步不再扩大 offset 硬调；
应换成 mesh-aware / open-face handle candidate model，再给新模型单独跑 candidate-only gate。

2026-07-05 Task 6C geometry audit 已完成：
`eos2_mesh_aware_open_face_geometry_audit_20260705.json`，代码 checkpoint 是
`eos2_mesh_aware_open_face_geometry_audit_code_checkpoint_20260705.json`。结论是
`PASS_HANDLE_GEOMETRY_AUDIT_READY_FOR_MESH_AWARE_CANDIDATE`：EBench-loaded USD 中可以唯一定位
真实 drying box handle `/World/labutopia_level1_poc/obj_obj_DryingBox_01/handle`、door leaf
`/World/labutopia_level1_poc/obj_obj_DryingBox_01/body/Group/door/mesh` 和 RevoluteJoint
`/World/labutopia_level1_poc/obj_obj_DryingBox_01/RevoluteJoint`。open-face normal 记录为
`[0.0, 1.0, 0.0]`，来源是 `handle_door_center_delta_overlap_fallback`：通俗讲，handle 和 door
的静态 AABB 有重叠，不能直接靠“两个盒子分开的一面”判断正面，只能用 handle center 相对 door center
的偏移方向给下一步候选生成提供一个有标记的 fallback normal。下一步允许进入 mesh-aware /
open-face candidate-only preflight；仍不能 claim candidate_count、planner success、close-hold、
retention、door opened、Expert Oracle Score 或 score。

2026-07-05 mesh/open-face candidate preflight code checkpoint 已完成：
`eos2_mesh_aware_open_face_candidate_preflight_code_checkpoint_20260705.json`。GenManip probe
现在新增 `--planner-trajectory-post-replay-candidate-source mesh-open-face`，并通过
`--planner-trajectory-post-replay-mesh-open-face-geometry-audit-json` 消费上面的 Task 6C
geometry audit JSON。它会把 audited handle open face 转成 post-replay object-frame waypoint，
且在 candidate metadata 里保留
`handle_open_face_source=handle_door_center_delta_overlap_fallback`。用真实 geometry audit 做的离线
计算显示：primary normal 的 contact target 是
`[0.47978996139738445,0.27571899126186217,1.1085915534527668]`，opposite sign sanity 的
contact target 是 `[0.47978996139738445,0.22180747411861262,1.1085915534527668]`。这些只是
code/geometry checkpoint，不是 live `candidate_count>0` 证据；下一步仍必须跑 bounded
candidate-only preflight，并在进入 cuRobo planner 前停住。

2026-07-05 mesh/open-face primary live candidate-only preflight 已完成：
`eos2_mesh_open_face_candidate_preflight_live_20260705_primary/summary_compact.json`。结果是
`candidate_found=true`，分类为
`PASS_MESH_OPEN_FACE_CANDIDATE_ONLY_PREFLIGHT_READY_FOR_PLANNER_READBACK`。bridge replay 执行
`150` 步并达到 joint target，final joint error 是 `8.344650268554688e-05 rad`；post-replay
候选生成阶段 `candidate_source=mesh-open-face`、`candidate_preflight_only=true`、`candidate_count=1`、
`attempted_candidate_count=0`、`skipped_reason=candidate_preflight_only`。候选 label 是
`post_replay_mesh_open_face_primary_clearance_0p003_approach_0p035`，contact target 是
`[0.47978996139738445,0.27571899126186217,1.1085915534527668]`，normal 仍标记为
`handle_door_center_delta_overlap_fallback`。这说明新候选模型已经越过“候选生成”这道门；不需要再跑
opposite-normal sign sanity。下一步才是去掉 preflight-only，跑 exactly one full post-replay
planner/readback。当前仍不能 claim planner success、close-hold、retention、door opened、
Expert Oracle Score 或 score。

2026-07-05 full `mesh-open-face` primary planner/readback 已完成：
`eos2_mesh_open_face_planner_readback_live_20260705_primary/summary_compact.json`。它证明
Gate 6C-3 确实进入了 cuRobo planning：`candidate_count=1`、`attempted_candidate_count=1`，
但 contact target `[0.47978996139738445,0.27571899126186217,1.1085915534527668]`
返回 `MotionGenStatus.IK_FAIL`，`available_action_points=0`。注意措辞：这不是 post-replay
execution/readback 失败，因为没有 action points 可以执行；它是 post-replay planning 阶段失败。
因此不再继续候选 sweep 或 opposite-normal sign，下一步按停止规则转 bridge-to-near reachability。

2026-07-05 bridge-to-near bounded sanity 也已完成：
`eos2_mesh_open_face_bridge_to_near_bounded_sanity_20260705/summary_compact.json`。新增 code checkpoint
`eos2_mesh_open_face_bridge_to_near_code_checkpoint_20260705.json` 只增加一个显式选择器：
`--planner-trajectory-post-replay-mesh-open-face-target-world-key approach_near_target_world`。
两条 near 尝试都生成了 numeric waypoint 并进入 cuRobo planning，但都失败为
`MotionGenStatus.IK_FAIL`、`available_action_points=0`：`0.035m` 的 near target 是
`[0.47978996139738445,0.3107189912618622,1.1085915534527668]`，`0.045m` 的 farther-near
target 是 `[0.47978996139738445,0.32071899126186215,1.1085915534527668]`。bridge replay 本身仍
达到 joint tolerance，所以这不是 reset/server 回退。分类是
`BLOCKED_MESH_OPEN_FACE_BRIDGE_TO_NEAR_REACHABILITY_AFTER_BOUNDED_NEAR_OFFSET`。现在应停止
contact-target / near-offset 调参，转 approach-seed / robot-staging redesign；仍不能 claim
close-hold、retention、door opened、Expert Oracle Score、policy score、official score 或 full task
completion。

2026-07-05 已把下一步收束为新的 5-gate 计划：
`docs/superpowers/plans/2026-07-05-eos2-approach-seed-robot-staging-redesign.md`。这份计划的作用是
防止继续盲扫参数：Gate 1 只回答 wrist orientation / approach seed / robot staging 能否让
handle-front approach pose 变成可规划、可执行；Gate 2 才测 contact target；Gate 3 测 close-hold /
retention；Gate 4 测 micro-pull / door joint readback；Gate 5 才允许进入 `Expert Oracle Score`。
现在 Gate 1 已细分为 1A/1B/1C：1A 测 wrist orientation source，1B 测是否存在可执行 staging
parent，1C 才测 staging parent 到 handle-front `approach_near_target_world`。只有 1C 通过，
才允许进入 Gate 2 contact。若 1C 失败，只能得出窄结论：当前 selected bridge +
staging-parent 路线不适合接到 handle-front approach；不能扩大成 DryingBox 不可开、所有 staging
都不可行或 score 不可能。

PM 阶段口径：

| 阶段 | 白话验收问题 | 通过后能说什么 |
|---|---|---|
| Gate 1C | 机器人从已找到的中间站，能不能伸到把手正前方安全点 | 当前路线可以进入接触验证 |
| Gate 2 | 能不能从安全点走到把手接触点 | 可以进入闭爪保持验证 |
| Gate 3 | 闭爪后是不是真的夹住把手 | 可以进入小幅拉门验证 |
| Gate 4 | 夹住后小拉，门关节/门角是否朝正确方向变化 | 工程上接近弄好 |
| Gate 5 | 专家路线在 EBench metric 下是否得分 | 评测口径弄好 |

当前最早 no-go 点是 Gate 1C。如果 Gate 1C 失败，停止当前 bridge +
`post_bridge_local_z_m006_q_bridge` 路线，不继续扫 contact / close-hold / score。
Gate 1C 已在 2026-07-05 触发这个 no-go，所以后续必须先做路线分流；任何新路线仍要重新通过
Gate 1，才允许进入 Gate 2 contact。

2026-07-05 Gate 1 的第一段 code checkpoint 已完成：
`eos2_approach_seed_orientation_source_code_checkpoint_20260705.json`。GenManip probe 现在新增
`--planner-trajectory-post-replay-mesh-open-face-orientation-source {native-open,post-replay-ee}`；
默认仍是 `native-open`，不会改变旧证据口径。focused pytest 结果是 `32 passed, 258 deselected`，
`py_compile` 和 GenManip diff check 均为 exit `0`。这只是代码入口就绪，不是 live Isaac 证据；
下一步才是在 fresh server 上跑一次 `post-replay-ee + approach_near_target_world + 0.045m` isolation
probe。

2026-07-05 Gate 1A wrist-orientation isolation live probe 已完成：
`eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045/summary_compact.json`。
这次把 mesh/open-face `approach_near_target_world` 的 world orientation 从固定
`native-open` 改成 bridge replay 后实时 `state.ee_pose[1]`。候选生成正常：
`candidate_source=mesh-open-face`、`candidate_count=1`、target 是
`[0.47978996139738445,0.32071899126186215,1.1085915534527668]`，normal 来源仍保留
`handle_door_center_delta_overlap_fallback`。但 post-replay cuRobo replan 仍返回
`MotionGenStatus.IK_FAIL`，`successful_candidate_count=0`、`available_action_points=0`、
`selected_plan_success=false`。分类是
`BLOCKED_APPROACH_SEED_ORIENTATION_SOURCE_IK_FAIL_NO_ACTION_POINTS`。注意边界：bridge replay
达到 joint tolerance，final error 约 `0.00497 rad < 0.02 rad`，但这轮也触发了 `64` step cap，
而 bridge 一共有 `151` 个 action points。因此它足够说明“单纯换成 post-replay-ee wrist orientation
不够”，可以停止 orientation-source tuning；但还不能宣布整个 Gate 1 route no-go。下一步只允许跑
Gate 1B bounded staging family：`post_bridge_local_z_m006_q_bridge`、
`post_bridge_local_y_p006_q_bridge`、`post_bridge_local_x_m006_q_bridge`。实际 Gate 1B 因
first-success selection 先选中 `z_m006`，未消费的 sibling 已在后续 Gate 1D 单独补跑。

2026-07-05 Gate 1B bounded staging family 已完成：
`eos2_approach_seed_staging_family_live_20260705/summary_compact.json`。结果不是 Gate 1 pass，而是
`STAGING_CONTINUATION_EVIDENCE_ONLY_REQUIRES_GATE_1C_STAGING_TO_MESH_OPEN_FACE_APPROACH_NEAR`：
三条 explicit staging candidates 中，第一条 `post_bridge_local_z_m006_q_bridge` 成功，生成 `90`
个 action points，staging replay 后 joint readback 进入 `0.02 rad` 容差；另外两条因为 first-success
selection policy 未尝试。这说明找到了一个可执行中间站，但还没有从这个中间站到把手正前方
`approach_near_target_world` 的 live evidence。下一步只跑 Gate 1C；Gate 1C 通过才进入 contact，
Gate 1C 失败就停止当前 bridge + selected staging parent 路线，不再回到 contact offset、normal
sign、close-hold、micro-pull 或 score。

2026-07-05 Gate 1C selected staging-to-near live probe 已完成：
`eos2_approach_seed_staging_to_mesh_open_face_near_live_20260705/summary_compact.json`。分类是
`BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS`。这次的正证据和
负证据要分开讲：bridge replay 有 `151` 个 action points，执行到 `64` step cap 时已经达到 joint
tolerance；选中的中间站 `post_bridge_local_z_m006_q_bridge` 也生成 `91` 个 action points，
执行到 `64` step cap 后达到 `0.02 rad` joint tolerance。真正失败点是第三段 follow-up：从这个
中间站继续到 mesh-open-face `approach_near_target_world` 时，cuRobo 返回
`MotionGenStatus.IK_FAIL`，`available_action_points=0`，没有动作可以执行。PM 口径是：当前这条
bridge + selected staging parent 路线已经到达最早 no-go 点，不能进入 contact、close-hold、
micro-pull 或 `Expert Oracle Score`。但这个结论只针对当前选中的中间站路线，不能扩大成
DryingBox 一定打不开、所有 staging 都不可行、或者专家评分一定做不了。下一步不是继续扫 contact
/ close-hold / score，而是进入路线分流：要么预注册少量 sibling staging-to-near 变体验证
“是不是只选错了中间站”，要么更大幅度重设 robot layout / staging / candidate-generation。

多角度 review 后，下一步排序定为三段，防止继续盲试：

| 下一段 | 白话目的 | 停止条件 |
|---|---|---|
| Gate 1D: Sibling Staging-to-Near Bounded Triage | 只换少量预注册 sibling staging parent，看是不是只选错了 `post_bridge_local_z_m006_q_bridge` | sibling 集合全部 `IK_FAIL`、0 action points 或 replay 不达标，就停止这组 staging family |
| Gate 1R: Robot Layout / Staging Redesign Gate | 如果 1D 也失败，再重设 robot layout、approach seed、staging 或 candidate-generation | 必须重新产出 `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`，否则不进 contact |
| Gate 2: Contact Planner / Readback Re-entry | 只有新的 Gate 1 route 到达 handle-front near 后，才重新进入 contact target | contact planner/readback 失败就停，不进 close-hold / micro-pull / score |

2026-07-05 Gate 1D sibling staging-to-near bounded triage 已完成：
`eos2_approach_seed_sibling_staging_to_near_live_20260705/summary_compact.json`。分类是
`BLOCKED_APPROACH_SEED_SIBLING_STAGING_TO_NEAR_FAMILY_IK_FAIL_NO_ACTION_POINTS`。这次没有临时加候选，
只跑了预注册的 `post_bridge_local_y_p006_q_bridge` 和 `post_bridge_local_x_m006_q_bridge`。
两条都能复现 bridge replay 到位，但 sibling staging parent 自己在 post-replay replan 阶段就
`MotionGenStatus.IK_FAIL`、`available_action_points=0`，所以 follow-up 到
`approach_near_target_world` 被 `no_post_replay_execution` guard 跳过。PM 口径是：这一步证明
“不只是 z_m006 这一个中间站选错了”，小集合 sibling staging family 也没有打开 Gate 1。下一步进入
Gate 1R，重新设计 robot layout / staging / candidate-generation；仍不能进入 contact、close-hold、
micro-pull 或 `Expert Oracle Score`。

Gate 1R 的下一步合同已经收敛，不是 broad sweep。阶段名是
`Gate 1R: Robot Layout / Staging / Candidate-Generation Redesign Gate`，产品侧可理解为
“把手前安全点可达性重设门”。它先冻结 Gate 1D 的边界，再预注册 layout 候选，最后只问一个问题：
有没有新路线能真实 replay 到 handle-front `approach_near`。预注册候选优先改 robot base/layout
的 XY 相对位置，而不是继续扫 contact、near offset、wrist orientation 或 reset seed：

预注册 manifest：
`eos2_approach_seed_gate1r_layout_redesign_20260705/candidate_manifest.json`。它是
`PRE_REGISTERED_NOT_LIVE_EVIDENCE`，只能作为下一轮 live 执行合同，不能当作 pass evidence。

| Gate 1R 候选 | 改什么 | 不改什么 | 继续条件 |
|---|---|---|---|
| `R1_layout_y_p010` | robot base `[-0.4, 0.10, 0.73]` | asset、metric、planner route、base z=0.73、no reset seed、bridge label、`z_m006` staging、mesh-open-face primary normal、`approach_offset=0.045`、`orientation_source=post-replay-ee` | bridge、staging、near 三段都有 action points 且 replay 到 `0.02 rad` |
| `R2_layout_x_p012` | robot base `[-0.28, 0.0, 0.73]` | 同上 | 同上 |
| `R3_layout_x_p012_y_p008` | robot base `[-0.28, 0.08, 0.73]` | 同上 | 同上 |
| `R4_approach_line_staging_under_best_layout` | 条件运行：在最好 layout 下把 staging 改成 handle open-face approach-line staging | final target 仍是 `0.045m` near；contact/score 仍禁用 | staging 和 near 都 replay 到容差 |

Gate 1R 通过最多只能说 `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`，也就是可以重新进入
Gate 2 contact planner/readback；不能说已经抓住、拉开门或得分。

2026-07-06 Gate 1R live 已跑完：
`eos2_approach_seed_gate1r_layout_live_20260706/summary_compact.json`。分类是
`BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS`。白话结论是：我们没有继续盲调，
而是按预注册合同把 Gate 1R 的 R1/R2/R3/R4 都跑到了止损点。R1/R2/R3 只改 robot base 的 XY：
`[-0.4,0.10,0.73]`、`[-0.28,0.0,0.73]`、`[-0.28,0.08,0.73]`。三条都能 replay bridge，
也都能规划 `post_bridge_local_z_m006_q_bridge` staging；但三条从 staging 到把手前
`0.045m near` 都是 `MotionGenStatus.IK_FAIL`、0 action points。

因为 R1-R3 的 bridge/staging 是干净的但 near 仍失败，按合同触发了 R4。R4 选 R2 layout，
先用 candidate-only preflight 生成 handle open-face approach-line staging：
`[0.47978996139738445,0.3607189912618622,1.1085915534527668]`，即
`contact_target_world + primary_normal * 0.085m`；然后 live 里把它作为 explicit staging，再继续尝试
原来的 `0.045m near` follow-up。R4 的 bridge 仍到位，但 `0.085m` staging 本身就
`MotionGenStatus.IK_FAIL`、0 action points，所以 follow-up 被 `no_post_replay_execution` 跳过。

产品口径：这不是“门一定打不开”，也不是“专家分数失败”。它只说明在当前预注册的 Gate 1R 候选集合里，
机器人仍没有可执行动作到达把手前安全点，所以 Gate 1 继续 blocked；不能进入 contact、close-hold、
micro-pull 或 `Expert Oracle Score`。下一步应开 `Gate 1S: Strategy Redesign / No-Go Review`，
决定是改 task layout、改 robot/object-frame route generation、改 expert/oracle 生成方式、换机器人，
还是对这个精确定义的 EBench+Franka+DryingBox 合同给出 bounded no-go。

Gate 1S review manifest 已建立：
`eos2_gate1s_strategy_review_20260706.json`。Gate 1S is now the next stage. It is a strategy
redesign / bounded no-go review, not another local offset sweep. The selected default strategy is
`S1_TASK_LAYOUT_NORMALIZATION`, with `max_selected_live_strategy_count=1`. Gate 2 and Expert Oracle
Score remain blocked until a new `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT` is recorded.

2026-07-06 Gate 1S selected strategy live 已完成：
`eos2_gate1s_selected_strategy_live_20260706/summary_compact.json`。分类是
`BLOCKED_GATE1S_SELECTED_STRATEGY_NO_NEAR_REACHABILITY`。S1 把 robot base 调到
`[-0.2,0.0,0.73]`，也就是 strategy-level 的 task layout normalization 诊断；bridge 仍然能 replay 到位，
100 个 action points 中执行 64 步，最终 joint error 约 `0.00493 rad < 0.02 rad`。但 bridge 后的
mesh-open-face `0.045m near` 仍然是 `MotionGenStatus.IK_FAIL`、0 action points，因此没有 near replay，
也仍不能进入 contact 或 score。

Gate 1S 的计划约束是 `max_selected_live_strategy_count=1`，所以这里达到 bounded no-go 建议点。允许结论：
当前这个精确定义的 EBench+Franka+LabUtopia DryingBox 合同，在 Gate 1R 加一个 strategy-level Gate 1S
尝试后，仍没有产生 scoring-eligible expert route；Gate 2 和 `Expert Oracle Score` 继续 blocked。
不允许扩大成 DryingBox 全局打不开、LabUtopia 资产不能进 EBench、官方分数失败或所有机器人/布局/路线都不可行。

EOS-2xC7 candidate queue 历史校验结论：

```text
candidate_row_count=6
source_rows=eos2xc6_w024_base,eos2xc6_w028_base
source_log_dirs_exist=true
source_eval_result_dirs_exist=true
source_eval_result_file_count=0
source_manifest_present=false
first_live_candidate_id=eos2xc7_w024_base_attachment_audit
first_live_run_id=labutopia_eos2xc7_physx_contact_generation_collider_attribution_eos2xc7_w024_base_attachment_audit_20260704_223000_eos2xc7
submit_exit=0
probe_exit=0
trace_lines=297
first_live_status=PARTIAL_NEGATIVE
hard_gate_failure.label=approach_near
hard_gate_failure.exit_reason=stage_not_reached:max_steps_exhausted
hard_gate_failure.min_actual_distance_m=0.03453716465463178
hard_gate_failure.final_actual_distance_m=0.03913976102212624
hard_gate_failure.max_command_actual_gap_m=0.01619371223682052
post_close_contact_retention_summary.sample_count=0
physx_contact_debug.status=available
physx_contact_debug.contact_pair_count=0
score_claim_allowed=false
micro_pull_diagnostic_allowed=false
grasp_hold_retention_claim_allowed=false
server_start_fix=use short RAY_TMPDIR such as /tmp/r7c7 to avoid Ray AF_UNIX socket path limit
readback_row_dir=eos2xc7_w024_approach_near_readback_20260704_124339
readback_run_id=labutopia_eos2xc7_approach_near_readback_eos2xc7_w024_base_attachment_audit_20260704_124339
readback_submit_exit=0
readback_probe_exit=0
readback_trace_lines=1
readback_status=FAIL_CONTROLLER_READBACK_COMPARATOR_NO_IK_TARGET
readback_blockers=missing_successful_ee_pose_ik_debug,ee_pose_target_position_error_exceeds_tolerance
readback_executed_steps=1
readback_ee_pose_target_position_error_m=0.5245884806528617
readback_target_world=[0.44979134324235837,0.24876333628991587,1.1085916790181332]
readback_target_robot_frame=[0.8497913432423584,0.24876333628991587,0.3985916790181332]
readback_post_ee_position=[0.3892921805381775,0.004671737086027861,0.45819777250289917]
approach_pre_row_dir=eos2xc7_w024_approach_pre_readback_20260704_125312
approach_pre_run_id=labutopia_eos2xc7_approach_pre_readback_eos2xc7_w024_base_attachment_audit_20260704_125312
approach_pre_submit_exit=0
approach_pre_probe_exit=0
approach_pre_trace_lines=2
approach_pre_status=FAIL_CONTROLLER_READBACK_COMPARATOR_DIAGNOSTIC_ONLY
approach_pre_blockers=ee_pose_terminal_without_post_obs,ee_pose_arm_state_jump_too_large,joint_position_terminal_without_post_obs,joint_position_arm_state_jump_too_large
approach_pre_executed_steps=2
approach_pre_target_world=[0.3997913432423583,0.24876333628991587,1.1085916790181332]
approach_pre_target_robot_frame=[0.7997913432423583,0.24876333628991587,0.3985916790181332]
approach_pre_parse_only_ik_success=true
approach_pre_action_source=ik_solution
approach_pre_ik_joint_delta_abs_max=2.0215107798576355
approach_pre_invalid_state=arm_state_jump_too_large
approach_pre_violating_joint=panda_joint4
approach_pre_post_world_step_delta_abs_max=1.6464000940322876
bounded_lead_in_row_dir=eos2xc7_w024_approach_pre_bounded_lead_in_20260704_130833
bounded_lead_in_run_id=labutopia_eos2xc7_approach_pre_bounded_lead_in_eos2xc7_w024_base_attachment_audit_20260704_130833
bounded_lead_in_submit_exit=0
bounded_lead_in_probe_exit=0
bounded_lead_in_trace_lines=56
bounded_lead_in_status=FAIL_BOUNDED_JOINT_LEAD_IN_DIAGNOSTIC_ONLY
bounded_lead_in_executed_steps=56
bounded_lead_in_lead_in_steps=55
bounded_lead_in_max_joint_step_rad=0.05
bounded_lead_in_command_target_delta_exceed_indices=[]
bounded_lead_in_post_step_delta_exceed_indices=[52,53,54]
bounded_lead_in_final_joint_target_abs_max_rad=0.6525141596794128
bounded_lead_in_terminal_reason=arm_state_jump_too_large
bounded_lead_in_terminal_violating_joint=panda_joint6
target_frame_audit_row_dir=eos2xc7_w024_target_frame_reachability_audit_20260704_132909
target_frame_audit_status=READ_ONLY_AUDIT_COMPLETE_DIAGNOSTIC_ONLY
target_frame_audit_classification=UPSTREAM_TARGET_REACHABILITY_AND_CONTROLLER_STABILITY_OPEN
target_frame_audit_base_frame_assessment=PASS_BASE_FRAME_CONSISTENT_FOR_CURRENT_EVIDENCE
target_frame_audit_decision=move_to_ebench_style_object_frame_waypoints_plus_curobo_planning
```

历史 PM 口径（2026-07-04 C7/readback 排查链路，已被后续 object-frame ladder 和 bridge
evidence 推进；当前下一步见本文件后面的 `EOS-2 Open-Door Oracle Evidence, 2026-07-04/05`）：
候选清单相当于“把下一轮体检单排好了”；第一条 live witness 相当于“已经进了
诊室，但还没检查到手指和把手真实接触那一步”。这条证据证明 server / submit / probe /
debug 字段链路能跑，也证明 claim guard 没有误放行；但它失败在更早的 `approach_near`，
所以当时还不能说 handle collider 有问题、稳定抓住了、可以 micro-pull 或可以算分。当时下一步
已经追加只读 `controller-readback-comparator --controller-readback-waypoint-label approach_near`。
结果显示不是“已经到位但没接触”，而是 `approach_near` 本身没有形成可用的 successful IK
target / readback：手爪位置和目标相差约 0.525 m。当时下一步应先判断这是 target frame 构造或
IK 可达性问题，还是 comparator 缺少 IK debug 暴露；在这个结论出来前不要盲跑剩余
collider/filter 候选行。随后补跑的 `approach_pre` 对照基线显示：诊断工具本身能看到
successful IK，问题不是“所有 IK debug 都没暴露”。但 `approach_pre` 的 IK target 相对当前
关节姿态跨度很大，单步执行时 `panda_joint4` 从约 `-2.81` 跳到 `-1.16`，超过 `1.0 rad`
安全阈值，导致 terminal without post obs。当时下一步应跑 `bounded-joint-lead-in`，把同一个
IK target 拆成小关节步长，确认这是执行步长问题，还是目标姿态/控制接口仍有根因问题。
新的 bounded lead-in 结果显示：命令侧每步确实被限制在 `0.05 rad`，前段稳定，但 step
52-54 真实 readback 开始明显发散，最后 `panda_joint6` 单步跳变约 `1.386 rad` 触发安全保护。
多角度 reviewer 结论一致：这还不是 contact/collider 问题；应先做 target-frame /
reachability / late-step controller timeline 审计，再把 oracle 改成 EBench 风格的
object-frame manual waypoint + per-waypoint cuRobo planning，而不是继续依赖单个
absolute IK target replay。注意：只有实现中显式刷新并记录 cuRobo world obstacles
后，才允许升级为完整 `collision-aware planning` 说法。
这次派生 audit 已经完成：它确认当前 audited path 的 base frame 一致，主要问题是 waypoint /
wrist orientation / reachability / controller stability 仍未闭环；但后续 object-frame
convention 还要单独校验。产品口径可以说“我们找到了为什么不能直接套 expert 轨迹：EBench
microwave 的标准做法不是 replay 单个 IK 点，而是 object-frame waypoint + cuRobo 在线规划；
DryingBox 接下来也要按这个模式重写 oracle 入口。”
源码核对口径：EOS 当前 `mobile_manip/microwave` registry 指向
`GenManip/configs/tasks/ebench/mobile_manip/test_mini/microwave.yml`；GenManip
的 `test`、`test_mini`、`val_train`、`val_unseen` microwave 配置共享同一类
manual `custom_motion` / `object_frame` expert 模板，把开门 expert 写成相对 `microwave`
的 waypoints；
`custom_motion.py` 再转成 world pose 并调用 `BaseEmbodiment.plan_pose` / cuRobo
`MotionGen.plan_single`。metric 读取 articulation qpos 和物体关系，因此后续 DryingBox
也必须证明 runtime planner 和 EBench metric 都闭环，不能只证明固定轨迹 replay。

2026-07-04 object-frame oracle Task 4a 又补了一层工程结论：此前
`object-frame-curobo-planner-smoke` 只能证明 EvalClient 缺 planner-only endpoint；
现在已经补上 `POST /plan_object_frame_waypoints`，并把 server、worker pool、Ray worker、
env helper、genmanip-client 和 probe 串成单元/契约闭环。这个通道会记录
approach_pre、approach_near、contact 三个 waypoint 的 cuRobo planning records；
三点都规划成功且 world refresh 为 success 时，目前只能开放
`planner_world_refresh_observed` 这个弱证据，不能开放 `collision_aware_planning` claim。
post-review 后已补保护：planner smoke 不消费 pending reset result；runtime side-effect
flags 会透传并阻断 PASS；object-frame UID 只从 `scene.object_list` 解析以匹配 EBench
custom_motion。这个 checkpoint 当时仍然不是 live planner smoke passed，因为还没有在真实
Isaac/cuRobo server 对 DryingBox scene 跑 evidence。后续 Task 4b live evidence 见下段，
并继续保持
stable grasp、micro-pull、score、full collision-aware planning 等更高层 claim 为 false，
直到对应证据出现。

2026-07-04 Task 4b live evidence 已新增：
`eos2_object_frame_curobo_oracle_debug_20260704_155243/`。这轮证明了 planner-only
runtime 真实进入 Isaac/cuRobo：`reset` 成功，`/plan_object_frame_waypoints` 可调用，
world refresh 对 approach_pre / approach_near / contact 都返回 `success`，并且没有
runtime reset / step / post_episode_process 副作用。它没有通过 planner smoke：三个
waypoint 的 `trajectory_point_count=0`。新加的 planner debug 把原因拆清楚：
完整 world refresh 下是 `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`；clean
reset 里第一项 `refresh_world=false` 是 `MotionGenStatus.IK_FAIL`。PM 口径：现在不是
conda、cuRobo import、endpoint 或资产加载没通，而是默认 DryingBox 专家手部目标姿态还没调成
Franka/curobo 能规划的状态；当时下一步要做 pose/orientation ladder 和 start-collision
attribution。

2026-07-04 Task 4b follow-up live evidence 已新增：
`eos2_object_frame_pose_ladder_20260704_162947/`。这轮运行
`object-frame-curobo-pose-ladder`，`submit_exitcode=0`、`probe_exitcode=0`、
`status=BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_NO_IK_SOLVABLE_VARIANT`。
它先不 fresh refresh cuRobo world，而是测试 20 个 `approach_pre` object-frame
pose 变体是否至少有一个 IK-solvable：5 个 X offset 乘以 4 个 yaw orientation。
结果 20/20 个变体都是 `MotionGenStatus.IK_FAIL`，`first_ik_solvable_variant_label=null`，
`runtime_side_effect_reported=false`。PM 口径：planner 通道和 reset 都工作了，
但第一批“把手前方手部姿态”还不可达；当时下一步扩展 pose basis，而不是进入 score、
policy、micro-pull 或 collision 结论。

## 2026-07-01 AAN Consumer Evidence

DryingBox AAN-ready package 接入 EBench 的当前证据分为多个阶段记录。早期记录里
`status` 使用 producer/raw 风格的小写 `pass`；从 Stage 4b final manifest 开始，PM
汇总和验收 manifest 的顶层 `status` 统一使用大写 `PASS/FAIL/BLOCKED/WARN/IN_PROGRESS`。

| File | Stage | Status | 含义 |
|---|---|---|---|
| `aan_dryingbox_package_intake_20260701_0719.json` | Stage 1: `AAN package intake` | raw `pass` / canonical `PASS` | 固定 ConvertAsset retained package、manifest、package hash 和 file count。 |
| `aan_dryingbox_consumer_check_20260701_0000.json` | Stage 2: `Consumer manifest check` | raw `pass` / canonical `PASS` | AAN schema、runtime profile、benchmark profile、stage gates、entrypoints、dependency closure、blockers、waivers 通过 consumer 准入。 |
| `aan_dryingbox_task_mount_20260701_0000.json` | Stage 3: `Task-root wiring and dry-run composition` | raw `pass` / canonical `PASS` | AAN package 已用 symlink 挂到 composite assets root；`asset.usd`、task files 和 required prims 能解析。 |
| `aan_dryingbox_runtime_adapter_20260701_0000.json` | Stage 4a: `AAN runtime adapter preflight` | raw `pass` / canonical `PASS` | AAN-specific wrapper、task config、assets manifest 已生成；wrapper 真实引用 mounted `asset.usd`；package digest 在 Stage 4a 重新计算并匹配 Stage 1/3；`legacy_overlay_used=false`。 |
| `aan_dryingbox_runtime_smoke_20260701_085521.json` | Stage 4b: `AAN live eval smoke` | `PASS` | Fresh `run_id=labutopia_aan_lift2_stage4b_20260701_085521` 通过 submit / probe / eval 一致性检查；reset、step、render、metric、logging、`result_info.json`、stdout/stderr 都有证据；`legacy_overlay_used=false`。 |
| `aan_dryingbox_no_local_repair_snapshot_20260701_0000.json` | Stage 6a: `No-local-repair snapshot` | `PASS` | 对 retained ConvertAsset AAN package 做 hash baseline；`package_mutation_allowed=false`，`local_usd_repair_allowed=false`。 |
| `aan_dryingbox_no_local_repair_verify_20260701_0000.json` | Stage 6a: `No-local-repair verify` | `PASS` | Stage 6 guard 复核 package digest 仍为 `6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936`；没有 consumer-side local repair。 |
| `aan_muffle_furnace_package_intake_20260701_094329.json` | Stage 6 replication Stage 1 | raw `pass` / canonical `PASS` | 非 DryingBox articulated asset `MuffleFurnace` 的 retained ConvertAsset package 已锁定。 |
| `aan_muffle_furnace_consumer_check_20260701_094329.json` | Stage 6 replication Stage 2 | raw `pass` / canonical `PASS` | `MuffleFurnace` AAN manifest 通过 consumer schema / profile / gate / entrypoint 检查。 |
| `aan_muffle_furnace_task_mount_20260701_094802.json` | Stage 6 replication Stage 3 | raw `pass` / canonical `PASS` | `MuffleFurnace` package 以独立 namespace 挂载，`asset.usd` 能打开，非 `N/A` required prims 能解析。 |
| `aan_muffle_furnace_no_local_repair_verify_20260701_094846.json` | Stage 6 replication guard | `PASS` | `MuffleFurnace` package digest 仍为 `69c49538658892e4faef4265a9dd5049b16e690d3740f5a764b47a5f2b42a233`；没有 consumer-side local repair。 |
| `aan_muffle_furnace_runtime_adapter_20260701_102820.json` | Stage 6 replication Stage 4a | raw `pass` / canonical `PASS` | `MuffleFurnace` 已生成独立 generic AAN task lane、wrapper `.usda` 和 lane-local `assets_manifest.json`；wrapper 指向自己的 mounted AAN package；`legacy_overlay_used=false`。 |
| `aan_muffle_furnace_runtime_smoke_20260701_105508.json` | Stage 6 replication Stage 4b | `PASS` | Fresh `run_id=labutopia_aan_muf4b_20260701_104829` 通过 generic live smoke；reset、step、render、metric、logging、`result_info.json` 均有证据；`score=0.0` 是 smoke 边界，不是 semantic task success；`mdl_compiler_error_count=264` 阻止 full visual parity 声明。 |
| `aan_beaker_01_package_intake_20260701_094343.json` | Stage 6 replication Stage 1 | raw `pass` / canonical `PASS` | 非 DryingBox rigid transparent prop `Beaker_01` 的 retained ConvertAsset package 已锁定。 |
| `aan_beaker_01_consumer_check_20260701_094343.json` | Stage 6 replication Stage 2 | raw `pass` / canonical `PASS` | `Beaker_01` AAN manifest 通过 consumer schema / profile / gate / entrypoint 检查。 |
| `aan_beaker_01_task_mount_20260701_094802.json` | Stage 6 replication Stage 3 | raw `pass` / canonical `PASS` | `Beaker_01` package 以独立 namespace 挂载，`asset.usd` 能打开，非 `N/A` required prims 能解析。 |
| `aan_beaker_01_no_local_repair_verify_20260701_094846.json` | Stage 6 replication guard | `PASS` | `Beaker_01` package digest 仍为 `b707403b13a7295d0f5385e0c48b1498dc98119f5a728cc2d9d07614c3c87e98`；没有 consumer-side local repair。 |
| `aan_beaker_01_runtime_adapter_20260701_102820.json` | Stage 6 replication Stage 4a | raw `pass` / canonical `PASS` | `Beaker_01` 已生成独立 generic AAN task lane、wrapper `.usda` 和 lane-local `assets_manifest.json`；wrapper 指向自己的 mounted AAN package；`legacy_overlay_used=false`。 |
| `aan_beaker_01_runtime_smoke_20260701_1135.json` | Stage 6 replication Stage 4b | `PASS` | Fresh `run_id=labutopia_aan_beak4b_envfix_20260701_1135` 通过 generic live smoke；reset、step、render、metric、logging、`result_info.json` 均有证据；`score=0.0` 是 smoke 边界，不是 semantic task success；`mdl_compiler_error_count=8` 阻止 full visual parity 声明。 |
| `aan_stage6_replication_summary_20260701_0950.json` | Stage 6 replication summary | `BLOCKED` | 旧 summary。它记录当时 Stage 4a 尚未补齐时的 blocker，现在已被 `20260701_1145` summary supersede。 |
| `aan_stage6_replication_summary_20260701_1029.json` | Stage 6 replication summary | `IN_PROGRESS` | 旧 summary。它记录两个新资产完成 Stage 1-4a、但 Stage 4b live smoke 仍 `NOT_RUN` 的中间状态；现在已被 `20260701_1145` summary supersede。 |
| `aan_stage6_replication_summary_20260701_1056.json` | Stage 6 replication summary | `IN_PROGRESS`; minimum `PASS` | 旧 summary。它记录 `MuffleFurnace` 已通过 Stage 4b、`Beaker_01` 尚未运行 Stage 4b 的中间状态；现在已被 `20260701_1145` summary supersede。 |
| `aan_stage6_replication_summary_20260701_1145.json` | Stage 6 replication summary | `PASS` | 当前 summary。`stage6_minimum_acceptance_status=PASS`、`highest_common_passed_stage=4b`、`highest_replicated_stage=4b`、`stage4b_live_smoke_status=PASS`：`MuffleFurnace` 和 `Beaker_01` 都通过 generic Stage 4b live smoke。 |

## 2026-07-02 AAN-11 Consumer Evidence

AAN-11 是 ConvertAsset material runtime closure 后的新 DryingBox package。它不是 7 月 1
日旧包的同名重跑；PM 汇报和工程 handoff 里必须把旧包 Stage 4b、AAN-11 producer
material closure、AAN-11 consumer rerun 分开说。

运行环境固化入口：
[`../aan_runtime_environment_bootstrap.md`](../aan_runtime_environment_bootstrap.md)。
以后 AAN consumer live smoke 的 manifest 应按该 runbook 记录
`runtime_environment_contract`、`bootstrap_preflight`、`diagnostic_attempts_before_final`
和 claim boundary，避免把 conda / cuRobo / assets root 问题误判成资产失败。

| File | Stage | Status | 含义 |
|---|---|---|---|
| `aan11_dryingbox_consumer_intake_mount_adapter_20260702_1755.json` | AAN-11 intake / mount / runtime adapter | `PASS` | 锁定 AAN-11 新 package、digest、composite assets root、wrapper、task config 和 no-local-repair boundary；证明 consumer 将加载 `dryingbox_01_overlay_aan11_scene`，不是 7 月 1 日旧 wrapper。 |
| `aan11_dryingbox_runtime_smoke_20260702_1803.json` | AAN-11 consumer live smoke rerun | `PASS` for consumer smoke; `WARN` for fixed-front visual parity | Fresh `run_id=labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803` 通过 submit / eval；reset 后跑满 1000 steps，产出 `result_info.json`。固定 native vs AAN 正面对比相机已生成，构图和可比性 PASS；但 rack、控制面板、小脚和表面质感仍有差异，full visual/material parity 仍 OPEN。 |

AAN-11 final run 证据目录：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803/
```

关键结论：

```text
run_id=labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803
runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene
submit_exit_code=0
eval_exit_code=0
reset_observed=true
step_1000_observed=true
score=0.0
success_rate=0
consumer_mdlc_compiler_error_count=16
consumer_relationship_out_of_scope_count=70
solid_red_text_count=0
fixed_front_visual_review=WARN
```

AAN-11 consumer rerun 的允许说法：

```text
AAN-11 DryingBox package 已进入 LabUtopia / EBench consumer 并通过本地 live smoke；
固定正面对比相机证明 AAN 侧没有大面积 red fallback，且门、handle、控制面板和观察窗可比。
```

AAN-11 consumer rerun 的禁止说法：

```text
official leaderboard score 已完成。
policy/model 已经解决 open-door 任务。
full visual/material parity 已证明。
consumer runtime 中所有 MDL compiler warning 和 USD material:binding warning 都已消失。
```

Stage 1-4b 的允许说法：

```text
DryingBox AAN-ready package 已完成 LabUtopia / GenManip consumer 的收货、验货、task-root 挂载、AAN runtime adapter/preflight，并通过本地 EBench / GenManip live smoke。
```

Stage 1-4b 的禁止说法：

```text
official leaderboard score 已完成。
policy/model 已经解决 open-door 任务。
full visual material parity 已证明。
```

Stage 4b 已产出 `aan_dryingbox_runtime_smoke_20260701_085521.json`。只有这个 final
manifest 可以让 PM 汇报 “AAN package 通过本地 live eval smoke”。它记录 fresh
`run_id`、run-id/artifact 一致性、`reset_passed=true`、`step_passed=true`、
`render_passed=true`、`metric_passed=true`、`logging_passed=true`、
`result_info_exists=true`、stdout/stderr paths、exit codes，并且没有任何 `FAIL` /
`BLOCKED` row。

Stage 6 复制验证的允许说法：

```text
Stage 6 replication hardening 已 PASS：MuffleFurnace 和 Beaker_01 已经复制通过
AAN consumer Stage 1-4b：收货、验货、task-root 挂载 dry-run、no-local-repair verify、
generic lane/wrapper 生成、runtime adapter preflight 和 generic live smoke；两个包都没有被
LabUtopia / GenManip 本地修改。两次 generic Stage 4b smoke 都证明 reset / step /
render / metric / logging / result_info 链路可运行。
```

Stage 6 复制验证的禁止说法：

```text
semantic evaluator / task/evaluator.yaml runtime execution 已经实现。
MuffleFurnace 或 Beaker_01 的 generic smoke pass 等于 semantic task success。
Beaker_01 的 OmniGlass MDL warning 已经完成 full visual parity closure。
Stage 6 PASS 等于任意 USD / MJCF / deformable / liquid 资产都 ready。
```

Stage 6 当前 summary：

```text
stage6_minimum_acceptance_status=PASS
status=PASS
highest_common_passed_stage=4b
highest_replicated_stage=4b
stage4a_runtime_adapter_preflight_status=PASS
stage4b_live_smoke_status=PASS
blocker_or_next_action=Stage6 replication hardening PASS. Next follow-ups: standardize the AAN runtime env bootstrap, implement semantic evaluator dispatch for task/evaluator.yaml, and close material-warning/full-visual-parity evidence separately.
```

Beaker_01 的前两次 diagnostic failure 不是资产失败，而是 consumer runtime 环境诊断：

- 第一次 worker 没继承 `CUROBO_SRC`，还没进入资产加载；
- 第二次修好 cuRobo Python import 后，暴露 `PATH/LD_LIBRARY_PATH` 缺少 `ninja` 和 `libcudart.so.11.0`；
- final fresh run 用现有 `embodied-eval-os-sim-isaacsim41-genmanip-py310` 环境，加上 `CUROBO_SRC`、`PATH=$PYENV/bin:$PATH`、IsaacSim `omni.cuda.libs/bin` 和 `omni.gpu_foundation/bin/deps` 的 `LD_LIBRARY_PATH` 后通过。

Stage 4b 的运行证据目录：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan_lift2_stage4b_20260701_085521/
```

Stage 4b 运行时仍记录了 `mdl_compiler_error_count=636`。这不阻塞 reset / step /
render / metric / logging 的 smoke pass，但它阻止任何更强的视觉声明：不能把 Stage 4b
PASS 说成 full visual material parity 或 source-native full material closure。

### 2026-07-02 Producer Render Visual QA

`reports/2026-06-15-labutopia-weekly/assets/aan-dryingbox-producer-runtime-smoke-render.png`
现在只保留为 7 月 1 日旧包的问题诊断图，不作为展示图；AAN-11 新包已经用
`aan11-dryingbox-qualified-front.png` 和 `aan11-native-vs-aan-fixed-front-contact.png`
替代它作为最新 PM-facing 图。旧图视觉复核结论：

- 明显异常红色材质：ConvertAsset producer runtime log 中有
  `Failed to create MDL shade node`、`could not find module` 和 unresolved texture
  记录，说明 MDL / texture runtime 解析没有闭环；
- 背面/俯视相机：画面看不到 DryingBox 的门、handle 和正面整体结构；
- 因此 producer `runtime_smoke.status=pass` 只能说明 headless load / render
  readback / step / reset 这些 smoke gate 通过，不能升级为 full visual material
  parity 或可展示最终材质效果。

关键 producer 证据：

```text
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package/evidence/runtime_smoke/report.json
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package/evidence/runtime_smoke/stderr.log
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package/evidence/runtime_smoke/stdout.log
```

当前日志计数：

```text
producer_failed_mdl_shade_nodes=10
producer_missing_mdl_modules=41
producer_unresolved_textures=18
producer_payload_scope_material_binding_warnings=84
consumer_mdl_compiler_error_count=636
```

这也修正了 `material_closure=pass` 的 PM 读法：它是 package-local dependency /
material evidence gate，不等于 Isaac 4.1 runtime 中所有 MDL shader、texture 和最终颜色
都已经正确显示。下一步应由 ConvertAsset 侧做 material runtime closure follow-up：
补齐 MDL transitive dependencies、texture path、material binding scope，并用 task-facing
showcase camera 重拍；LabUtopia / GenManip 只消费新包并复跑 evidence，不做本地修包。

Stage 5 PM/weekly HTML 已发布到：

```text
reports/2026-06-15-labutopia-weekly/index.html#aan-handoff
```

该页面把 Producer evidence 和 Consumer evidence 分开展示。7 月 1 日旧 AAN producer
render 已标注为视觉 QA FAIL/OPEN，只作为问题对照保留；AAN-11 的合格正面图和
固定 native vs AAN 正面对比图是最新 PM-facing 证据。AAN-11 已解决 broad red fallback
和背面视角问题，但固定对比仍是 `WARN`，不能升级为 full visual material parity。

`aan_dryingbox_runtime_adapter_20260701_0000.json` 的关键硬门：

- `config_path=ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml`，不是旧 `lift2_candidate`；
- `runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_scene`，不是旧 overlay scene；
- `wrapper_references` 是从 USDA reference list 解析出来的，不接受注释里的假字符串；
- `package_tree_digest` 和 `mounted_package_tree_digest` 都等于 `6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936`；
- AAN manifest routing 忽略旧全局 `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT`，防止 leftover env 把 AAN config 带回旧 overlay。

Stage 4b final manifest 的最小硬门：

- `status=PASS`，不是 raw `pass`；
- fresh `run_id` 同时出现在 submit/eval/probe logs、artifact directory、`result_info_path` 和 manifest；
- `config_path=ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml`；
- `legacy_overlay_used=false`；
- Lift2/R5a eval 使用 16D action dialect，例如 `-a r5a -g lift2`，不能用默认 Franka/Panda 9D action；
- `reset_passed=true`、`step_passed=true`、`render_passed=true`、`metric_passed=true`、`logging_passed=true`；
- `result_info_exists=true`、`stdout_exists=true`、`stderr_exists=true`；
- `submit_exit_code=0`、`probe_or_eval_exit_code=0`；
- `no_fail_or_blocked_rows=true`；
- 非 PASS 时必须写 `failure_phase`、`failure_owner`、`blocker_or_next_action`。

## 标准顶层字段

每个新的 AAN consumer 验收记录建议包含：

```json
{
  "schema_version": 1,
  "recorded_at_utc": "2026-07-01T00:00:00Z",
  "asset_id": "DryingBox_01_overlay",
  "task_lane": "ebench/labutopia_lab_poc/aan_lift2_candidate",
  "stage": "aan_stage4b_live_smoke",
  "status": "PASS",
  "run_id": "example_run_id",
  "commands": {
    "server": "PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python; PYTHONPATH=$CUROBO_SRC:$WORKTREE $PY ray_eval_server.py --host 127.0.0.1 --port 18189 --run_id $RUN_ID --no_save_process --episode_recorder_save_every 0 --reset_timeout 1200 --step_timeout 1200 --load_config_timeout 300",
    "submit": "gmp submit ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml ...",
    "probe": "python standalone_tools/labutopia_poc/lift2_eval_contract_probe.py --live --host 127.0.0.1 --port 18189 --worker-id 0 --run-id $RUN_ID --task-name level1_open_door --logging-json $EVIDENCE_DIR/live_probe_logging.json --output $EVIDENCE_DIR/probe.json",
    "eval_or_smoke_client": "python -m genmanip_client.cli eval -a r5a -g lift2 ..."
  },
  "profile": {
    "asset_class": "articulated",
    "runtime_profile": "isaac41",
    "benchmark_profile": "ebench-lift2",
    "dynamics_profile": "articulated_body",
    "profile_support_status": "supported_phase1"
  },
  "artifact_paths": [],
  "artifact_sha256": {},
  "gate_status": {},
  "failure_phase": null,
  "failure_owner": null,
  "blockers": [],
  "allowed_claims": {},
  "blocked_claims": {},
  "verification": []
}
```

New PM/evidence-summary `status` values only allow:

```text
PASS
FAIL
BLOCKED
WARN
IN_PROGRESS
```

`WARN` 只能表示 diagnostic evidence 可用，不能表示验收完成。Producer manifest 内部的
raw status 可以保留原样，但要放在 `producer_manifest_raw_status`、`stage_gates_raw` 等
字段下，不要覆盖顶层 canonical `status`。

## Gate 字段

推荐统一记录这些 gate：

```json
{
  "gate_status": {
    "asset_intake": "PASS",
    "usd_composition": "PASS",
    "material_closure": "PASS",
    "physics_closure": "PASS",
    "articulation_closure": "PASS | NOT_APPLICABLE | NOT_REQUIRED",
    "task_runtime": "PASS",
    "render_evidence": "WARN",
    "evaluator_robot_contract": "PASS"
  }
}
```

PM 文案只能说对应 `PASS` 的部分。比如 `task_runtime=PASS` 可以说“本地任务链路可评”，但不能推出 `policy_success=true`。
Rigid-only USD assets must not force `articulation_closure=PASS`; use `NOT_APPLICABLE` or
`NOT_REQUIRED`. Articulated assets must keep explicit articulation evidence.

## Expert Oracle Score 字段

`score=0.0` 的 live smoke 不等于 expert 失败。后续新增 `Stage 4c: Expert Oracle
Score / Score Calibration` 时，manifest 必须把 smoke、oracle、policy 和 official score
分开记录。

推荐字段：

```json
{
  "stage": "expert_oracle_score",
  "substage": "franka_native_expert_replay | lift2_oracle_retarget",
  "score_lane": "franka_expert_oracle | lift2_oracle | real_policy | official_leaderboard",
  "evidence_freeze": {
    "task_name": "",
    "usd_name": "",
    "config_sha256": "",
    "asset_wrapper_sha256": "",
    "run_id_policy": "must include expert_oracle or lift2_oracle",
    "assets_root": "",
    "wrapper_path": "",
    "no_local_repair": true
  },
  "embodiment": "manip/franka/panda_hand | manip/lift2/R5a",
  "controller_kind": "labutopia_native_expert | retargeted_expert | lift2_scripted_oracle | learned_policy",
  "action_contract": "franka_native | lift2_r5a_16d",
  "metric_authority": "genmanip_ebench_metric_output",
  "metric_target": {
    "object_uid": "obj_DryingBox_01",
    "joint_name": "RevoluteJoint",
    "angle_deg_range": [30, 120]
  },
  "oracle_score": null,
  "policy_score": null,
  "policy_score_claim_allowed": false,
  "official_score_claim_allowed": false,
  "result_info_path": "",
  "action_log_path": "",
  "metric_trace_path": "",
  "render_or_video_path": ""
}
```

允许说法：

```text
Franka expert oracle 通过，只能说明 LabUtopia native expert 的标准答案能被 EBench metric 识别。
Lift2 oracle / retarget 通过，只能说明 Lift2/R5a 口径存在可完成专家上限。
真实 policy score 必须由模型通过 EvalClient 输出标准 action 后单独记录。
```

禁止说法：

```text
Franka expert oracle 等于 Lift2 score。
Lift2 oracle / retarget 等于模型能力。
本地 policy score 自动等于 official leaderboard score。
```

## Material Closure 字段

`material_closure` 必须拆清楚 package-level claim 和 source-native claim：

```json
{
  "material_closure": {
    "material_status": "resolved_material_with_local_overrides",
    "remote_unmirrored_unwaived_count": 0,
    "remote_waiver_count": 0,
    "local_mirror_count": 1,
    "source_resolved_surface_count": 1,
    "wrapper_authored_material_count": 2,
    "fallback_surface_count": 0,
    "dependency_records": [],
    "source_resolved_surface_records": [],
    "authored_material_records": [],
    "fallback_surface_records": [],
    "waiver_records": [],
    "material_closure_claim_allowed": true,
    "full_material_closure_claim_allowed": true,
    "native_material_closure_claim_allowed": false,
    "full_native_material_closure_claim_allowed": false,
    "asset_specific_claims": {
      "aluminum_material_closure_claim_allowed": true
    },
    "native_material_closure_reason": "wrapper_local_material_overrides_present",
    "native_material_provenance": {
      "schema_version": 1,
      "status": "blocked_by_wrapper_local_overrides",
      "source_native_blocker_surface_count": 2,
      "native_wrapper_override_surface_count": 2,
      "native_claim_blocker_records": [
        {
          "source_prim_path": "/World/DryingBox_01/Group/_900_1",
          "runtime_prim_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/Group/_900_1",
          "source_binding_status": "empty_authored_binding_in_stage2_source_readback",
          "source_material_binding": null,
          "runtime_material_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/Looks/task_indicator_mat",
          "replacement_required_for_full_native_closure": true,
          "blocked_claims": ["native_material_closure", "full_native_material_closure"]
        },
        {
          "source_prim_path": "/World/DryingBox_01/button",
          "runtime_prim_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/button",
          "source_binding_status": "unbound_in_stage2_source_readback",
          "source_material_binding": null,
          "runtime_material_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/Looks/task_button_mat",
          "replacement_required_for_full_native_closure": true,
          "blocked_claims": ["native_material_closure", "full_native_material_closure"]
        }
      ]
    }
  }
}
```

规则：

- 单个 material dependency 已 local mirror，只能升级 scoped dependency claim。
- 当 runtime `fallback_surface_count=0`，且 wrapper-local override 已显式记录时，`full_material_closure_claim_allowed` 可以是 `true`，表示 EBench package material gate 已通过。
- 只要存在 wrapper-local authored material，`full_native_material_closure_claim_allowed` 必须是 `false`。
- `native_material_provenance` 是 source-native claim 的刹车字段：它说明哪些 wrapper-local material override 还没有 source-native `material:binding` 证据，且每条 blocker 必须写清 source path、runtime path、runtime material path、source binding status 和 blocked claims。
- hash mismatch、missing texture、stale `/World/Looks` binding、unknown unbound mesh 和 overclaim 都是 FAIL。
- explicit waiver 可以保留资产验收边界，但不能让 package material closure 或 native material closure 自动变成 true。
- `primvars:displayColor` 不自动等于 fallback；有有效 `material:binding` 时只算 authored auxiliary color，只有 fallback-only surface 才计入 `fallback_surface_count`。

Reusable validator boundary:

- New assets should construct `MaterialClosureExpectation` instead of copy/pasting DryingBox assertions; the expectation includes material status, claim flags, forbidden claims, native provenance status, and blocker paths.
- `NativeMaterialProvenanceBlocker` records are the reusable unit for surfaces that have package-visible wrapper material but cannot claim source-native material binding.
- Asset-specific validators may still add package checks for source files, physics reports, camera contracts, or task semantics.

## PM 文案映射

| Manifest 字段 | PM 可以怎么说 | PM 不能怎么说 |
| --- | --- | --- |
| `task_runtime_ready=true` | 任务能 reset/step/logging，本地链路可评 | 策略已经会做任务 |
| `task_render_accepted=true` | eval camera 能拍到可读任务图 | 官方榜单成绩已复现 |
| `lift2_contract_ready=true` | 旧 local Lift2 合同检查通过，或某个本地 schema/action/logging 合同通过 | official leaderboard 已发布，或当前 F2/F2a 后的 official/native control route 已解决 |
| `asset_specific_claims.aluminum_material_closure_claim_allowed=true` | DryingBox 的 Aluminum 远端材质依赖已 local mirror | DryingBox 全部 native 材质已恢复 |
| `full_material_closure_claim_allowed=true` | EBench package material evidence 已记录 | runtime MDL/texture closure 或 source-native full material closure 已完成 |
| `full_native_material_closure_claim_allowed=false` | 仍不能宣称 source-native 全闭环 | 把它解读为 package material gate 未通过 |
| `pm_showcase_ready=false` | 当前图只能作为诊断证据 | 当前图可直接对外展示 |

## 当前 DryingBox 状态示例

```text
旧 evidence lane - LabUtopia hand-built overlay:
  Stage 7 local Lift2 contract: PASS (historical local contract only; not current official/native control closure)
  full native material closure: BLOCKED by wrapper-local button and Group/_900_1 materials
  native material provenance: BLOCKED by /World/DryingBox_01/button and /World/DryingBox_01/Group/_900_1

新 evidence lane - ConvertAsset AAN package consumer:
  Stage 1-4b AAN consumer live smoke: PASS
  Stage 5 PM/weekly HTML publication: PASS
  Stage 6a no-local-repair guard: PASS
  Stage 6 replication on additional assets: PASS; Stage 1-4b generic smoke PASS on MuffleFurnace and Beaker_01
  EBench package material evidence: PASS
  Aluminum local mirror: PASS
  Stage 4b consumer live smoke: PASS
  runtime material warning: mdl_compiler_error_count=636; not full visual parity evidence

共同禁止声明:
  policy success: BLOCKED / not evaluated
  official leaderboard: BLOCKED / not an official run
  full visual material parity: BLOCKED / not proven
```

这说明 DryingBox 当前已经能证明“本地 consumer live smoke 通过”和“包级材质 evidence 已记录”，但还不能证明“策略成功”“官方成绩发布”或“source-native 全材质闭环完成”。PM 汇报时可以说 package material evidence 和 Stage 4b local live smoke 有证据，不能把 `button` 和 `Group/_900_1` 的 wrapper-local `PreviewSurface` 说成原生材质已恢复，也不能把红色 producer render 或 636 条 MDL compiler warning 解释成视觉一致性已经无风险。

## EOS-2 Task 4d.2 Code Checkpoint, 2026-07-05

代码 checkpoint 已补齐 support-surface clearance 诊断入口：

```text
GenManip:
  plan_object_frame_waypoints_for_scene 支持 support_surface_uid=table
  online_open_door_oracle_probe.py 支持 --support-surface-* 参数
  trace / variant record 可保留 support_surface_clearance_records
  support_surface_clearance_records 区分三个 path/source 字段：
    support_surface_prim_path = cuRobo start_state_collision.world 报出的具体 obstacle
    support_surface_reference_prim_path = 用来读 AABB 的 scene/table 实体
    support_surface_aabb_source = payload 或 scene_uid:table
  planner_only_support_surface_exclusion_allowed 只有在 exact ignore candidate、
  sphere 与 support-surface AABB 已经转到同一个 frame、Z clearance 非负、
  XY footprint 与 support-surface AABB 重叠时才为 true

Evidence boundary:
  Task 4d.2 是 code+unit-test evidence；Task 4d.4A 已补 live clearance evidence。
  live evidence directory:
    eos2_support_surface_frameaware_clearance_audit_20260704_221731
  compact:
    pose_ladder_support_surface_frameaware_compact.json
  12/12 records measured_same_frame; clearance_margin_m=-0.011760663122180937;
  planner_only_exclusion_allowed_count=0。
```

## EOS-2 Open-Door Oracle Evidence, 2026-07-04/05

| Evidence | Status | Product meaning | Boundary |
|---|---|---|---|
| `eos2_object_frame_pose_ladder_richer_20260704_173743` | `BLOCKED` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_NO_IK_SOLVABLE_VARIANT`。600 个 handle-side 候选都 IK_FAIL，说明不是简单改 yaw 或 clearance。 | 不允许 stable grasp、door opened、score 或 collision-aware claim。 |
| `eos2_object_frame_pose_ladder_reset_seed_20260704_174832` | `WARN` | raw status=`PASS_OBJECT_FRAME_CUROBO_POSE_LADDER`。reset EE pose seed 可规划，说明 planner endpoint 和 reset-seed object-frame round-trip sanity 是通的。 | 只证明 sanity seed，不证明已经能靠近把手或开门。 |
| `eos2_object_frame_bridge_ladder_20260704_181425/pose_ladder_summary_compact.json` | `WARN` | raw status=`PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER`。no-refresh 下找到第一个 reset-to-handle bridge 可规划点，152 个 trajectory points。 | 只证明不带 world obstacles 的 bridge 可达；不证明 collision-aware、grasp、door opened 或 score。 |
| `eos2_object_frame_bridge_ladder_20260704_181425/pose_ladder_world_refresh_summary_compact.json` | `BLOCKED` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_RESET_FAILED`。第一次 world-refresh 复跑被 Ray OOM 打断，不能用于 planner/collision 结论。 | 只能作为 resource blocker 记录。 |
| `eos2_object_frame_bridge_ladder_20260704_181425/pose_ladder_world_refresh_retry2_summary_compact.json` | `BLOCKED` | raw status=`BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP`。reset 和 world refresh 都成功，但 12 个候选全部被判 `INVALID_START_STATE_WORLD_COLLISION`。 | 不能汇报抓住、开门或得分；该 collision source 已由后续 Task 4c classify evidence 归因到 table surface mesh vs `panda_hand`。 |

Task 4d.3 live no-extra-ignore support-surface clearance audit 已完成：它记录了 table
surface mesh AABB、`panda_hand` sphere center/radius、clearance_margin_m、XY footprint
overlap、AABB source 和 reference prim path。2026-07-05 frame 复核后，这批旧记录的
`sphere_vertically_intersects_support_surface` 只能作为“table surface / `panda_hand`
是 bridge blocker”的诊断证据，不能直接解释成真实物理穿桌，因为 table AABB 来自 USD
world frame，而 sphere 来自 cuRobo planner/reference frame。

Task 4d.4A live frame-aware audit 已补齐同 frame 证据：
`eos2_support_surface_frameaware_clearance_audit_20260704_221731/pose_ladder_support_surface_frameaware_compact.json`。
submit/probe exit code 均为 `0`；12/12 条记录都是 `planner_reference_frame` vs
`planner_reference_frame` 的 `measured_same_frame`；`clearance_margin_m` 约
`-0.011760663m`；planner-only exclusion allowed count 为 `0`。当前不能写入 planner-only
support-surface exclusion。

Task 4d.4B base-z-lift isolation 已完成：
`eos2_bridge_start_state_base_z_lift_002_20260704_223919/pose_ladder_base_z_lift_002_compact.json`。
submit/probe exit code 均为 `0`；只把 Franka diagnostic base z 从 `0.71m` 改到 `0.73m`
后，start-state collision 从上一轮 12/12 变成 `0`，第二个 bridge candidate 在 world refresh
下规划出 152 个 trajectory points。该结果支持“reset/base clearance 是首要修复方向”；
它不是最终产品姿态，也不是 score/grasp/door-open evidence。

Task 4d.4C observed-base rerun 已完成：
`eos2_bridge_start_state_base_z_lift_002_observed_base_20260704_225244/pose_ladder_base_z_lift_002_observed_base_compact.json`。
GenManip 先补了 observed robot base debug 字段，然后复跑同一个 base-z-lift diagnostic config。
compact 明确记录 `/World/labutopia_level1_poc/franka` 的 observed base z 是 `0.730000019m`，
start-state collision 仍为 `0`，第二个 bridge candidate 仍规划出 152 个点。

Task 4d.4D reset branch decision 已完成：
`eos2_bridge_start_state_reset_seed_retract_001_20260704_230558/pose_ladder_reset_seed_retract_001_readback_compact.json`
证明 `default_joint_positions` 分支 seed 已进入 reset，但仍 12/12 start-state collision；
`eos2_bridge_start_state_base_z_lift_002_only_20260704_231348/pose_ladder_base_z_lift_002_only_compact.json`
证明只改 base z=`0.73m`、不带 solver/self-collision override 也能清掉 start-state collision，
第二个 bridge candidate 仍规划出 152 个点。

Task 4d.4E formal reset/base contract 已落配置：
`eos2_open_door_formal_reset_contract_checkpoint_20260705.json`。正式 Franka POC
`level1_open_door.yml` 现在使用 base z=`0.73m`，没有加入 diagnostic-only solver/self-collision/
oracle-debug 开关。随后 bounded execution/readback 证明单个 absolute IK target 小步 replay
仍会在后段 readback 发散，因此已转向 EBench microwave 风格的 object-frame waypoint +
per-waypoint cuRobo 路线。

Task 5B live rerun 已新增：
`eos2_planner_trajectory_execution_readback_live_20260705_005444/planner_trajectory_execution_summary.compact.json`。
这次先修了 probe 生命周期：submit 后 worker list 为空是正常初始状态，必须由 probe 先
`reset` 创建 worker，再请求 `plan_object_frame_waypoints`。旧证据里的
`worker 0 does not exist` 已不再出现；新 run 中 `/reset` 和
`/plan_object_frame_waypoints` 都返回 200。新的 blocker 更靠近专家轨迹本体：三个
DryingBox object-frame waypoint 都是 `MotionGenStatus.IK_FAIL`，没有生成
`trajectory_action_joint_positions`，所以还不能执行 replay。产品口径：现在不是 EBench
服务没跑起来，而是“伸手到把手前”的 object-frame target / wrist orientation /
reachability 还没调到 Franka + cuRobo 可规划。下一步应回到 target/orientation ladder，
不要进入 grasp、micro-pull、door opened、Expert Oracle Score 或 policy score。

Task 5C/5D 已把当时的下一层边界拆清楚。Task 5C 的成功证据
`eos2_planner_trajectory_explicit_bridge_execution_readback_live_20260705_5c_0120/planner_trajectory_explicit_bridge_execution_summary.compact.json`
证明 formal `level1_open_door.yml` 可以显式接收 bridge waypoint，cuRobo 能生成 action-level
trajectory，EBench consumer 能 replay 到目标关节容差内。Task 5D 的新证据
`eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0200/summary_compact.json`
进一步证明 bridge replay 后不 reset worker 也能发起 post-replay replan：`post_replay_replan.attempted=true`，
`planner_state_source=post_planner_trajectory_replay_worker_state`。但 follow-up 仍选择旧
`approach_pre`，cuRobo 返回 `MotionGenStatus.IK_FAIL`，所以第二段没有 action trajectory。
历史产品口径：第一段桥已经能走，第二段导航点还不合格。当时下一步应做 bridge-relative 的
handle-side waypoint family，从 post-bridge state 系统扫描 translation/orientation，
先让第二段也通过 planner trajectory + replay readback，再谈 close/grasp、micro-pull、
door opened、Expert Oracle Score 或 policy score。

该叙事已经被后续 Task 5E-5K-A 消费：5F 找到可执行的
`post_bridge_local_z_m006_q_bridge`，5G/5H 证明 close-hold / contact telemetry 链路可跑但
retention 失败，5I 又证明 fixed-quaternion 纯 translation 校正无法同时满足可达性和 contact
retention；5J-F 提供 Z+2deg 的 X-gap 线索，5K-A 已把它和 object-frame X-2mm 做成
`x_m002_ori_z_p02` 单候选并完成 live probe。当前不再回到 5C/5D 的旧 second-segment
waypoint 问题，也不再停在 prepared review。该路线已继续推进到 5L/5M：5L 暴露 handle-frame
target IK 不可达，5M route-bound rerun 已越过 `NoneType` 输入 bug，当前第一失败门是
`PAD_DEPTH_MISS` 导致 centerline solver 生成不了 numeric candidate。下一步先做
candidate-only tolerance / padding preflight，让 `candidate_count>0` 后再重跑完整 planner live。

2026-07-06 E2 code-ready checkpoint 已新增：
`eos2_gate1u_e2_lift2_controller_reference_probe_code_checkpoint_20260706.json`。它记录
non-DryingBox Lift2 controller reference / retiming probe 的工具、TDD 证据和多角度审阅闭环；
`live_runs_consumed=0`、`max_live_runs=1`。该 checkpoint 只说明 E2 live 可以按规范执行，
不证明 Lift2 controller tracking、DryingBox precontact、contact、door opened、Expert Oracle Score
或 policy score。

2026-07-06 E2 live 已完成：
`eos2_gate1u_e2_lift2_controller_reference_probe_live_20260706/result_compact.json`。本次是唯一允许的
non-DryingBox Lift2 controller reference probe，`executed_steps=70/70`，没有使用 DryingBox route、
没有 contact、没有 micro-pull、没有 score。结果是
`BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED`：no-op 和 terminal hold 都没到
`0.02rad` joint tolerance，final joint error `0.20075764784227174rad`，action-application debug 存在。
当前停止线是先修 Lift2 controller/action/readback，不能进入 E3/E4 或重新跑 DryingBox candidate。

2026-07-06 E2R root-cause plan 已新增：
`eos2_gate1u_e2r_controller_action_readback_root_cause_plan_20260706.json`。它明确下一步不是继续试
DryingBox，而是先补 per-joint telemetry。必须记录 observed_joints12 / observed_gripper4 /
observed_action_16d、expected vectors、target_minus_observed_16d、per-index error、max-error action slot /
component / global DOF / DOF name、完整 action_application_debug、post-step joint vector、
controller_drive_debug 和 action-slot mapping。E2R2 之后才能判断根因是 reset baseline、slot mapping、
drive/effort 还是 timing/hold；E2R4 通过后才回 E3/E4。若 E2R4 在 telemetry 闭合后仍同类失败，当前
direct 16D `joint_position` 路线 no-go，转 official Lift2 baseline controller/action path review。

2026-07-06 E2R1 code checkpoint 已完成：
`eos2_gate1u_e2r1_per_joint_telemetry_code_checkpoint_20260706.json`。这一步只改 E2 reference probe 的
diagnostic output 和 fake-client tests，不改变 action 生成、分类阈值或 controller 行为，也不消耗 live。
新增 RED/GREEN 覆盖缺 observed vectors、缺 full action debug 和缺 static action-slot mapping；GREEN 后
`test_lift2_controller_reference_probe.py` 为 `13 passed in 0.03s`。下一步允许 E2R2 exactly one enhanced
non-DryingBox live，用同一个 5 no-op + 5 ramp + 60 hold 小动作计划定位 root cause。

2026-07-06 E2R2 enhanced live 已完成：
`eos2_gate1u_e2r2_enhanced_lift2_controller_reference_live_20260706/result_compact.json`。这次消耗了 E2R2
唯一 live budget；raw classification 仍是
`BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED`，但 telemetry 已经足够具体。no-op 最大误差
来自 `left_joint3` / controller `fl_joint3`，target `0.047641370445rad`，observed
`0.09468900412321091rad`，支持 reset baseline stale / settling。terminal hold 最大误差来自 action slot `8`
即 `right_joint1` / controller `fr_joint1`：controller applied target 是 `0.20075376331806183rad`，drive
stiffness/damping/max effort 均有读数，但 observed 到最后仍约 `-0.000003879rad`。因此不能再把主因写成
“trajectory 太快，hold 一下即可”；下一步是 E2R3 zero-live / single-hypothesis repair planning，审计 Lift2 arm
joint tracking / controller application path。

2026-07-06 E2R3 plan 已补齐，且 E2R3a zero-live audit 已完成：
`eos2_gate1u_e2r3_lift2_articulation_contract_repair_plan_20260706.json` 和
`eos2_gate1u_e2r3a_lift2_articulation_contract_zero_live_audit_20260706.json`。它把当前优先假设固定为
`H3_CONTROLLER_TARGET_APPLIED_BUT_ARM_JOINT_TRACKING_DISABLED_OR_BYPASSED`：controller target 已经 applied，
但还没有变成 Lift2 arm DOF 的真实物理运动。E2R3a 证明静态 USD 不是缺右臂 joint/drive 的粗问题；
E2R3b 已把 runtime articulation telemetry 补到 code-ready，能记录 joint position、velocity、
max velocity 和 lower/upper limits。E2R3c 决策是不做猜测式行为修复，带新 telemetry 进入最后一次
E2R4。E2R4 是当前 direct
16D `joint_position` 路线的 yes/no 节点；E2R5 只做 0-live closure/fork decision。

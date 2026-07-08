# True PhysX/PBD Fluid Spike Handoff

Date: 2026-07-07

## 给产品经理的通俗结论

我们会做一条真实液体粒子的研究线，但它和当前 `Expert Oracle Score`
主线分开。当前 `level1_pour` 只是“机械臂做倒液动作”，不是“真的有液体被倒过去”。
新 spike 要验证的是：Isaac/PhysX 的真实 PBD 粒子液体能不能放进 LabUtopia 的烧杯，再进一步进入
EBench 运行时。

这条线允许失败。失败也有价值，因为我们会把问题说清楚：到底是杯子碰撞体装不住粒子，还是
GPU dynamics 没启用，还是粒子能跑但进不了 EBench，还是能进 EBench 但没法稳定读回评分。

## 当前事实

- `level1_pour` 使用 `assets/chemistry_lab/lab_001/lab_001.usd`，本地检查没有
  `PhysxParticleSystem` 或 `ParticleSet`。
- `level4_LiquidMixing` 使用 `assets/chemistry_lab/lab_003/clock.usd`，里面已有
  `/World/ParticleSystem` 和 `/World/ParticleSet`，可作为本地模板。
- 历史日志显示 PhysX 曾识别 `/World/ParticleSet`，但也提示 particles require GPU dynamics。
  所以现在只能说“已有粒子资产线索”，不能说“真实流体已经跑通”。

## S0 已完成：环境支持线先摸清楚了

S0 的作用不是证明“液体已经能倒起来”，而是先确认我们要用的 EBench / Isaac Sim 4.1
运行环境里有没有做真实液体所需的底层能力。当前结论是：可以进入下一步 S1，但还不能对外说
`level1_pour` 已经有真实液体。

本次冻结的目标运行环境是：

```text
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
```

这个环境里有 `isaacsim==4.1.0.0`，对应 EBench 侧要验证的 Isaac Sim 4.1 口径。直接用普通
Python import 时，`pxr.PhysxSchema` 和 `omni.physx` 不可见；但启动 `SimulationApp` 之后，
Isaac/Kit 会加载扩展，这时可以看到：

```text
pxr.Usd
pxr.PhysxSchema
omni.physx
PhysxSceneAPI
PhysxParticleSystem
PhysxParticleSetAPI
PhysxParticleAPI
PhysxPBDMaterialAPI
PhysxParticleAnisotropyAPI
PhysxParticleSmoothingAPI
PhysxParticleIsosurfaceAPI
```

白话解释：底层“能描述真实粒子液体”的 USD/PhysX 组件是存在的；只是这些组件不是普通 Python
一启动就能看到，必须进入 Isaac Sim runtime 之后才完整可用。

GPU 也能被目标环境看到：`NVIDIA GeForce RTX 4090`，`torch cuda_available=true`。这很关键，
因为 PhysX particle fluid 依赖 GPU dynamics；没有 GPU，后面不会进入真实液体 runtime 验证。

资产侧结论也已冻结：

- `lab_001/lab_001.usd`，也就是当前 `level1_pour` 场景，没有现成 `ParticleSystem` / `ParticleSet`。
- `lab_003/clock.usd` 和 `lab_003/lab_003.usd` 里有本地粒子模板，可作为 S1/S2 搭建 smoke scene 的参考。
- S0 只证明 schema、模板和 GPU 条件具备；它没有 step 粒子、没有验证烧杯能装住液体，也没有证明 EBench
  consumer 已经能稳定评分真实液体。

S0 证据文件：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_scope_freeze_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_schema_probe_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s0_isaacsim41_app_schema_probe_20260707.json
```

S0 之后进入 S1：做一个最小粒子场景，明确打开 GPU dynamics，真的跑几帧并读回粒子状态。

## S1 已完成：最小真实粒子 runtime 已跑通

S1 的问题很简单：不管烧杯、机器人、EBench 评分，先确认 Isaac Sim 4.1 里“真实 PBD 粒子”
能不能真的动起来，并且能不能读回粒子位置。当前结论是：S1 通过，可以进入 S2 烧杯 collider
矩阵测试。

本次运行仍然使用 S0 冻结的 IsaacSim41 / EBench 目标环境：

```text
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
```

S1 standalone scene 写到了：

```text
assets/chemistry_lab/lab_001_fluid_spike/standalone_particle_smoke.usda
```

这不是修改原始 `lab_001.usd`，而是在旁边新建了一个最小 smoke scene。scene 里包含：

```text
/World/PhysicsScene
/World/ParticleSystem
/World/ParticleSet
/World/Looks/Blue_Glass
ground plane
review camera
```

关键结果：

```text
gpu_dynamics_enabled=true
particle_count_initial=256
particle_count_final=256
particle_count_final_fraction=1.0
nan_count=0
readback_available=true
runtime_step_executed=true
max_displacement=0.12548987609554446
mean_delta_z=-0.11030351449353759
```

白话解释：我们放了 256 个真实 PhysX/PBD 粒子，打开 GPU dynamics，让它们跑了 120 step。
跑完以后粒子没有丢、没有 NaN，并且位置确实变化了；这说明“真实粒子本体能在目标 IsaacSim41
runtime 里 step，并且能被读回”。

S1 证据文件：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s1_standalone_particle_smoke_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/runtime_smoke_summary.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/particle_readback_trace.jsonl
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/physics_scene_settings.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/initial_frame.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/mid_frame.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001/terminal_frame.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s1_visual_review_20260707.json
```

视觉边界也要说清楚：三张图片现在是基于粒子 readback 的 diagnostic projection，用来说明粒子
初始悬空、step60/step120 后落到地面附近。它们不是产品级相机图，也不是材质/视觉 parity 证据。
第一次相机 RGB 图曾出现 near-black 画面，runner 已改成检测这种不可用相机帧并回退到诊断投影。
独立视觉 review 对最终三张 diagnostic projection 的结论是 `PASS`；后续 S2/S3 如果需要给产品展示，
仍需要重新布置更好的 scene camera。

S1 仍然不能说明：

- `level1_pour` 已经有真实液体。
- 烧杯能装住这些粒子。
- 机器人倒液动作能带动粒子。
- EBench consumer 已经能 step 或评分这些粒子。
- 任何 policy / leaderboard / official score claim。

## S2 已完成：当前这批烧杯 collider 还装不住粒子

S2 的问题是：真实粒子能跑以后，烧杯碰撞体能不能把粒子稳定留在杯里。我们没有只试一个方案，
而是按计划跑了 C0-C5 六种 collider，全部在目标 IsaacSim41 环境里 step 240 frames，并且每 30
frames 记录粒子位置、AABB、centroid 和 source/target/spill/below-table 区域统计。

结论是：`S2_BEAKER_COLLIDER_SMOKE` 当前为 `STOP_WITH_EVIDENCE`。这不是说真实液体路线彻底不可行，
而是说“当前这六种 collider 方案，没有一个达到进入 S3 倾倒测试的稳定持液门槛”。

正式证据：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_runtime_warning_scan_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2_beaker_collider_matrix_20260707_001/
assets/chemistry_lab/lab_001_fluid_spike/colliders/
tools/labutopia_fluid/run_beaker_collider_smoke.py
tests/test_fluid_beaker_collider_smoke.py
```

六个方案的结果：

| ID | 方案 | 结果 | 白话解释 |
|---|---|---|---|
| C0 | segmented box/wall proxy | `FAIL_CONTAINER_LEAK` | 约 69.5% 粒子留在 source，12 个粒子掉到 table 以下。 |
| C1 | simplified thick-wall open cup proxy | `FAIL_CONTAINER_LEAK` | 约 78.1% 留在 source，16 个粒子掉到 table 以下。 |
| C2 | segmented convex wall pieces | `FAIL_CONTAINER_LEAK` | 当前最接近，约 82.8% 留在 source，但仍有 12 个 below-table 粒子，不能放行。 |
| C3 | SDF tri-mesh open beaker | `FAIL_CONTAINER_LEAK` | 粒子全部掉到 table 以下，说明当前 SDF mesh/cooking 设置不能稳定持液。 |
| C4 | native `beaker2/mesh` `convexDecomposition` | `FAIL_NATIVE_CONVEX_INTERIOR_NOT_USABLE` | 原生 beaker mesh 引用成功，但 convexDecomposition 口径下内部不能作为稳定持液空间。 |
| C5 | analytic cylinder negative control | `FAIL_CONTAINER_LEAK` | 负控也不能持液；它本来就不会被推荐进入 S3。 |

S2 的通过门槛是：

```text
source_retention_fraction >= 0.95
particle_count_final_fraction >= 0.95
outside_source_count == 0
target_count == 0
spill_count == 0
below_table_count == 0
tail_leak_rate_fraction_per_second < 0.02
cpu_collision_fallback_detected=false
nan_count=0
```

实际没有任何非负控方案达到这些条件，所以 `best_for_s3=[]`，S3 暂时不放行。C2 是最接近的方向，
但它仍有 32 个 above-table spill 粒子和 12 个 below-table leak 粒子，所以只能作为“下一轮
collider 修复优先候选”，不是已经可用于倒液。

这次也扫了 runtime warning：没有发现 `CPU collision fallback`、`GPU collider unsupported` 或
PhysX error。C4 有 `material:binding` scope warning，是因为我们只 reference 了原生
`/World/beaker2/mesh`，它原本绑定的 `/World/Looks/OmniSurface_Glass` 不在 reference scope 内；
这个 warning 影响的是材质/外观绑定解释，不是这次 collider 失败的主因。

视觉边界：S2 图片仍是 diagnostic projection，不是产品级 camera render。它用于说明粒子 readback 后
是否在杯内、是否掉到 table 以下；红色点代表 below-table leak。第一版 C3/C4 side projection 曾把
below-table 粒子裁掉，已用动态 z 范围重生成 `v2_dynamic_z_shows_below_table_leaks` 版本。

S2 之后不能继续说：

- S3 kinematic pouring can proceed.
- 当前任何 collider 已经能稳定装住真实液体。
- 原生 LabUtopia beaker collider 天然适合 PBD particles。
- `level1_pour` 已经可以接真实液体或进 EBench 评分。

下一步应该先做 S2 follow-up，而不是直接进入 S3：优先从 C2 开始修 collider 参数和几何缝隙，
同时单独开 C3 SDF resolution/subgrid/cooking sweep 和 C4 native beaker reference/material/pose
closure，直到至少一个非负控方案达到 95% source retention，且 source 外、spill、target、
below-table 都为 0。

当前 S2F0 已完成：我们没有改口径、没有重新挑图，而是把 S2 的失败基线冻结成一个单独 manifest：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json
```

它固定了四件事：第一，C0-C5 的 S2 矩阵结果不再漂移；第二，C2 是当前最接近但仍失败的 baseline；
第三，runtime warning scan 和 visual review 已作为 S2F 后续比较的基准；第四，S3 仍然不放行。
所以 S2F0 当时的产品口径是：先进入 `S2F1_C2_PROXY_SWEEP`，不是进入倒液视频。现在 S2F1、S2F2、
S2F3、S2F4 和 S2F5 都已经完成，当前产品口径应更新为：唯一静态持液候选在 promotion review
中不稳定，procedural SDF open beaker 没兜住液体，LabUtopia 原生 `beaker2/mesh` 也不能直接当
fluid-safe collider。S3 仍不放行，下一步进入 `S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP`，专门设计
“外观看原生烧杯、物理碰撞用可控 wrapper”的方案。

当前 S2F1 也已完成：我们优先修了 C2 proxy collider，不是只手调一个参数，而是跑了 12 个 C2A
候选，系统覆盖 `panel_count`、`wall_thickness`、`bottom_overlap`、`particle_contact_offset`、
`collider_contact_offset/rest_offset` 和初始径向速度。正式证据是：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_c2_proxy_sweep_20260707.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2_followup_c2_proxy_sweep_20260707_001/
```

S2F1 的结果是：C2 proxy 明显有进步，但还没有达到 benchmark 放行。最好的两个候选 `C2A_005` 和
`C2A_009` 都把 source retention 提到 `0.9921875`，也就是 256 个粒子里大约 254 个留在杯内；
但严格口径要求 source 外必须是 0，它们仍各有 2 个粒子跑到 source 外并形成 spill。因此
`best_for_s3=[]`，S3 仍不放行。下一步不是扩大盲扫，而是进入 `S2F2_VELOCITY_CONTACT_OFFSET`，
围绕 `C2A_005`、`C2A_009` 和 `C2A_007` 判断这最后几个粒子是几何缝隙问题，还是
contact offset / velocity 参数敏感问题。

当前 S2F2 已完成：我们没有继续盲目调几何，而是只围绕 `C2A_005`、`C2A_009`、`C2A_007`
这三个 near-pass 候选做 18 个隔离实验。每个候选都固定原来的杯子几何，只分别改一类变量：
低初始径向速度、particle contact offset、collider contact/rest offset、CCD、以及一个明确标记为
non-physical 的 `max_velocity` guardrail。

正式证据是：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f2_velocity_contact_offset_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f2_velocity_contact_offset_20260708_001/
assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f2/
```

S2F2 的关键结果：

| 候选 | 结果 | 白话解释 |
|---|---|---|
| `C2A_009_S2F2_VEL020` | `PASS_SOURCE_HOLD` | 把初始径向速度从 `0.08` 降到 `0.02` 后，256 个粒子全部留在 source 区域：`outside=0`, `spill=0`, `below=0`。 |
| `C2A_009_S2F2_VMAX010` | `FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE` | 数值上也不漏，但它依赖极低 `max_velocity` 限速，等于把液体变得过黏，只能作为诊断，不能作为可推广方案。 |
| `C2A_007_S2F2_PCO045` | `FAIL_CONTAINER_LEAK` | 非常接近，只剩 1 个 spill 粒子，但严格门槛要求 0，所以仍不能通过。 |
| contact / collider offset 组 | mostly worse | 单独调 contact offset 没解决问题，部分方案反而漏得更多。 |

因此当前结论是：`C2A_009` 的最后泄漏更像
`VELOCITY_INITIAL_LAYOUT_COUPLED_SENSITIVITY`，不是简单的 collider contact offset 一调就好。
白话说，低初始速度确实让这次静态装液不漏，但它和 PhysX reset 后的轻微初始布局变化耦合在一起，
还不能说根因被纯粹隔离成“只改速度就一定解决”。它给了我们一个很具体的下一步候选：
`C2A_009_S2F2_VEL020`。

还有一个边界要讲清楚：S2F2 的 `spawn_position_pinned=true` 表示我们写入 USD 的初始粒子坐标是固定的，
不是每个方案随便换一批液体。但是正式 manifest 的 `s2f2_initial_layout_hash_audit` 显示三个 parent
都有 post-reset hash variation。白话说，PhysX 在 reset / settle 后会因为 contact offset 等参数让粒子
出现细小的初始稳定状态差异。因此 contact-offset 组只能作为诊断证据；真正进入下一步复核的是低初始速度通过的
`C2A_009_S2F2_VEL020`，不是那些依赖 contact offset 或 `max_velocity` 的方案。

S2F5 已完成：我们没有直接把 S2F2 的一次成功升级成倒液候选，而是只复核
`C2A_009_S2F2_VEL020`，跑了 3 个 `particle_seed` 和 2 个粒子数，合计 6 组 IsaacSim41 headless
runtime。正式证据是：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f5_promotion_review_20260708_001/
assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f5/
```

S2F5 的结果是 `STOP_WITH_EVIDENCE`，`passed_trial_count=0/6`，`best_for_s3=[]`，
`s3_kinematic_pour_released=false`。为什么先跑 S2F5、而不是马上做 F3/F4？因为 S2F2 当时已经给出
唯一 near-pass 候选，最短路径是先验证这个候选能不能直接放行；如果它通过，就可以少走更重的
SDF/native mesh 诊断。现在复核结果证明它不稳定，所以 F3/F4 不是不要做，而是正式变成下一步。

通俗说，S2F2 的候选不是完全没价值，但它经不起更严格复测：256 粒子组只漏 1-2 个粒子，已经非常接近；
1024 粒子组三个 seed 都明显漏出，`outside_source_count` 分别是 347、340、338。我们的 benchmark
放行条件是 0 个粒子漏到 source 外，所以不能把它升级成 S3 倒液。

| 复核组 | 结果 | 白话解释 |
|---|---|---|
| 256 粒子，seed 0/1/2 | 全部 `FAIL_CONTAINER_LEAK` | 分别漏 1、1、2 个粒子；接近成功，但严格 gate 要求 0。 |
| 1024 粒子，seed 0/1/2 | 全部 `FAIL_CONTAINER_LEAK` | 分别有 347、340、338 个粒子到 source 外，说明高粒子数下容器不稳定。 |

给产品经理的一句话版本：我们确实找到了一个“单次 256 粒子静态不漏”的线索，但 S2F5 已经验证它不是稳定
方案；因此现在不能进入 S3，也不能说 `level1_pour` 已经能真实倒液。S2F5 刚结束时的下一步是按原规划做
F3/F4；现在 F3 和 F4 都已经跑完，结论见下文，当前下一步是 `S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP`：
用原生杯子的外观，重新设计一套更可控的 fluid-safe physics wrapper。

S2F3 已完成：我们没有把 SDF 路线混进 C2 proxy，而是单独跑了 24 个 `C3A_*` 候选，系统覆盖
`sdf_resolution=64/96/128`、`sdf_subgrid_resolution=4/8`、`sdf_margin=0.002/0.005`、
`sdf_narrow_band_thickness=0.01/0.02`，并固定 `mesh_bottom_fan_closure=true`、
`normals_winding_audit=pass`。正式证据是：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f3_c3_sdf_sweep_20260708_001/
assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f3/
```

S2F3 的结果是 `STOP_WITH_EVIDENCE`，`reason=no_c3a_sdf_candidate_passed`，`best_for_s2f5=[]`，
`best_for_s3=[]`，`s3_kinematic_pour_released=false`。这次不是 `SDF cooking error`，也不是
`CPU collision fallback` 或 `GPU unsupported`：runtime warning scan 里这几项都是 0，24 个候选也都
有 particle readback 和完整证据文件。真正的问题是所有 SDF 候选都 `FAIL_CONTAINER_LEAK`：
每组 256 个粒子最后都在 source 外，且 `below_table_count=256`，说明当前这版开口凹形 SDF beaker
没有形成可盛液体的有效内部碰撞空间。

| 结果项 | S2F3 结论 | 白话解释 |
|---|---|---|
| 候选数量 | 24 | 该测的 SDF resolution / subgrid / margin / narrow band 组合都跑了。 |
| runtime 阻断 | 无 | 没有 CPU fallback、GPU unsupported、PhysX error 或 SDF warning。 |
| particle readback | 有 | 不是没读到数据；是读到的数据证明粒子全部漏出。 |
| 通过候选 | 0 | 没有任何 `C3A_*` 能进入 S2F5 promotion review。 |
| 下一步 | 已完成 `S2F4_C4_NATIVE_MESH_ISOLATION` | 原生 beaker mesh / native-derived route 已验证，结论是不直接放行。 |

给产品经理的一句话版本：SDF 这条路“技术上能跑起来”，但“物理上没兜住液体”。它没有把项目判死，
只是说明当前 procedural SDF open beaker 不能作为进入倒液动作的杯子碰撞体。后续 F4 已按计划把
native `beaker2/mesh` 的 convexDecomposition / SDF / render-mesh-plus-proxy route 分开验证，
结论是原生复杂资产不能直接包装成 fluid-safe collider；下一步改做专门的 proxy wrapper 设计。

## 调研补充：别人不是没做过 Isaac 液体 demo，但 demo 和 benchmark 不是一回事

通俗解释：Isaac Sim / Omniverse 当然有人做过液体类 demo。常见做法是用
`PhysxParticleSystem` + `ParticleSet` + `PBD Particle Material` 生成真实粒子，再用
`Isosurface` / `Smoothing` / `Anisotropy` 把一堆粒子渲染成一团连续的水。官方 Isaac Sim
本地 API 也明确写着 PhysX 使用 GPU-accelerated `PBD` particle simulation，可以模拟
`fluids`, `cloth`, `inflatables`；并且 particles 不支持 CPU simulation，必须启用 GPU。

但是这些 demo 通常只需要“看起来像液体、在手工场景里大致能流动”。我们现在要的是更严格的
benchmark 口径：

```text
headless 可复现
IsaacSim41 / EBench consumer 可加载
LabUtopia beaker 资产或等价 physics proxy 可复用
particle readback 能解释结果
source 外、spill、target、below-table 全部为 0 才能进入 S3
```

所以当前 S2 失败不是“IsaacSim41 完全不能盛液体”，而是“这批 collider 还没有达到我们对
benchmark evidence 的严格要求”。

调研结论按证据强弱分三类：

| 类型 | 资料结论 | 对我们的影响 |
|---|---|---|
| 官方/本地 API 事实 | `/isaac-sim/exts/isaacsim.core.prims/.../single_particle_system.py` 写明 PBD particles 可模拟 fluids，且 CPU simulation of particles is not supported。 | 必须继续坚持 GPU dynamics，不能用 CPU fallback 当成功。 |
| 官方/本地 API 事实 | `SingleParticleSystem` 暴露 `contact_offset`, `rest_offset`, `particle_contact_offset`, `enable_ccd`, `max_velocity`, `max_depenetration_velocity` 等参数。 | S2F follow-up 应系统 sweep 这些参数，而不是只换 mesh。 |
| 官方/本地 API 事实 | `omni.physx.scripts.particleUtils.add_physx_particleset_points` 支持 `fluid=True` 的 `Points` particle set。 | S1/S2 当前用 Points readback 是合理路线。 |
| 官方/本地 API 事实 | `omni.physx.scripts.utils` 支持 mesh collision approximation，例如 `sdf` 对应 `PhysxSDFMeshCollisionAPI`。 | C3 SDF 路线应继续做 cooking/resolution/subgrid sweep。 |
| 官方/本地 demo 事实 | 本机 `/isaac-sim/extsPhysics/omni.physx.demos/.../HoneyDemo.py` 是 "Honey flowing into a glass jar"，并说明使用 SDF collision + 高黏度 fluid。 | 官方 demo 路线存在，但它是专门调过的 showcase，不等于任意 LabUtopia 杯子 mesh 可直接持液。 |
| 官方/本地 demo 事实 | `ParticleDemoBaseDemo.create_particle_box_collider()` 用多个 box/cylinder collider 拼出接粒子的容器，而不是依赖单个复杂凹形玻璃 mesh。 | S2F 的 C2 proxy / segmented collider 方向符合官方 demo 习惯，应优先继续修。 |
| 官方限制事实 | Isaac Sim physics limitations 建议 GPU native collision approximation，如 `convex hull`, `SDF tri-mesh`, `sphere/box/capsule`；并说明 custom geometry 不与 GPU particles/deformables 碰撞。 | C5 analytic/custom cylinder 不能作为生产路线；S2F 必须明确 GPU-compatible collider。 |
| 官方限制事实 | Particles/deformable contact reports 不支持；`Isosurface` 是 render-only，并可能有 memory/OOM 风险。 | 后续评分不能依赖 contact report 或漂亮水面图，必须继续用 particle position readback / region counts。 |
| NVIDIA forum 经验 | “Liquid particle sampler passing through collider” 类问题里，工程师建议检查/增大 particle contact offset；用户反馈增大后漏穿缓解。 | C2 首轮 follow-up 应优先做 contact offset / particle contact offset / wall thickness 联合 sweep。 |
| NVIDIA forum 经验 | 旧的 hand pouring liquid demo 对高加速度敏感；限制 particle max velocity 可以缓解穿透，但会让液体更黏、更不真实。 | S3 之前必须先做静态持液；进入 S3 后也要先 slow tilt，再 medium/fast。 |
| 我们的推论 | 原生 render mesh 不等于好的 particle collider。`convexDecomposition` 可能让凹形杯内空间不稳定或不可用。 | C4 native mesh 不能直接信任，要和 SDF / proxy collider 分开验证。 |

参考资料：

```text
NVIDIA Omni Physics particles:
https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/particles/particles.html

Isaac Sim physics limitations:
https://docs.isaacsim.omniverse.nvidia.com/5.1.0/physics/physics_resources.html

NVIDIA forum, liquid particles passing through collider:
https://forums.developer.nvidia.com/t/liquid-particle-sampler-is-passing-through-the-collider/248815

Local Isaac Sim API evidence:
/isaac-sim/exts/isaacsim.core.prims/isaacsim/core/prims/impl/single_particle_system.py
/isaac-sim/exts/isaacsim.core.prims/isaacsim/core/prims/impl/particle_system.py
/isaac-sim/extsPhysics/omni.physx/omni/physx/scripts/particleUtils.py
/isaac-sim/extsPhysics/omni.physx/omni/physx/scripts/utils.py
/isaac-sim/extsPhysics/omni.physx.demos/omni/physxdemos/scenes/HoneyDemo.py
/isaac-sim/extsPhysics/omni.physx.demos/omni/physxdemos/scenes/ParticleDemoBaseDemo.py
/isaac-sim/extsPhysics/omni.physx.demos/omni/physxdemos/scenes/ParticleSamplerDemo.py
/isaac-sim/extsPhysics/omni.physx.demos/omni/physxdemos/scenes/ParticlePostProcessingDemo.py
```

给产品经理的白话结论：别人做 demo 的核心经验不是“直接把漂亮杯子 mesh 丢进去就能盛水”，而是
“单独给液体做 physics-friendly collider，并且反复调 particle contact / collider contact /
速度 / SDF cooking”。我们下一步要做的就是把这套经验变成可复现的 S2F follow-up，而不是直接进
倒液视频。

## 不会混淆的主线

这条 fluid spike 不改变以下结论：

```text
Expert Oracle Score current score/readback evidence remains a rigid/articulation line.
Fluid spike is parallel research.
Fluid spike failure is not LabUtopia-to-EBench project no-go.
Fluid render/video is not policy score.
AAN current profile still excludes deformable/liquid/cloth/particle assets.
```

## 阶段

| 阶段 | 要回答的问题 | 通过后能说什么 | 失败也要留下什么 |
|---|---|---|---|
| S0 Scope Freeze | 什么才算 true fluid？ | 真假液体边界已冻结 | `fluid_truth_criteria.json` |
| S1 Particle Smoke | 粒子能不能在 Isaac runtime 中 step？ | 已通过：standalone PBD 粒子本体可运行 | GPU/schema/readback 失败归因 |
| S2 Beaker Collider Smoke | 烧杯能不能装住粒子？ | 已完成：当前 C0-C5 均未达到 S3 放行门槛 | collider 失败矩阵 |
| S2F Collider Follow-up | 怎么把 S2 失败收敛成一个可持液 collider？ | 已完成到 S2F6：C2 proxy、C3 SDF、C4 native isolation、native approximation sweep 都没有放行 S3 | 参数/几何/cooking/native mesh/内置 approximation 失败归因 |
| S3 Kinematic Pour Rig | 杯子倾斜后粒子能不能流向目标杯？ | 找到可倒液的 collider+参数 | 倾倒失败归因 |
| S4 level1_pour Replay | 原 expert 倒液动作能不能带动粒子？ | LabUtopia native 任务中有真实粒子运动 | 机器人动作/粒子耦合失败归因 |
| S5 EBench Consumer | EBench 4.1 能不能加载/step 这套流体？ | consumer 没丢 fluid schema | runtime/consumer 失败归因 |
| S6 Metric Readback | 粒子读回能不能解释分数？ | 有粒子 readback metric contract | score/readback 不一致证据 |
| S7 Repeatability/Perf | 是否可重复、性能是否可接受？ | 有小样本稳定性和性能边界 | OOM/慢/不稳定证据 |

## S2/S3 Collider Matrix

用户明确要求 S2/S3 各种 collider 方式都试。当前计划固定这些 variants：

| ID | Collider | 为什么要试 |
|---|---|---|
| C0 | segmented box/wall proxy | 最少变量的 GPU-native 正例，先证明 fluid 参数本身能跑 |
| C1 | simplified thick-wall open cup proxy | 最像可交付的开口厚壁杯方案 |
| C2 | segmented convex wall pieces | 比 box 更接近圆杯，同时避免单 hull 封口 |
| C3 | SDF tri-mesh open beaker | 尽量保持开口凹形真实几何，但要严查 SDF resolution 和显存 |
| C4 | 原生 `beaker2/mesh` `convexDecomposition` | 必须试，用来判断 native beaker collider 是否天然可用 |
| C5 | custom cylinder / analytic geometry 负例 | 验证官方限制在本地是否复现，不作为生产路线 |

S2 只看“静态装不装得住”。当前 S2 结论是 `STOP_WITH_EVIDENCE`，所以 S3 暂不放行。S3 只有在后续
S2 follow-up 找到至少一个 `PASS_SOURCE_HOLD` 非负控 collider 后，才看“kinematic source beaker
连续倾斜后流不流得出来”。
如果 static pass 但 moving fail，结论归类为 `KINEMATIC_COUPLING_FAIL`，不把它误写成
collider 完全可用或 true fluid 完全不可用。

S2F4 已经专门验证 LabUtopia 原生 `beaker2/mesh`。这一步不是简单重跑旧 C4，而是把三个问题拆开：
第一，USD reference / material binding scope 是否闭合；第二，原生烧杯的 pose / scale 是否对齐到 S2
source region；第三，对齐后的 native-derived collision 是否真的能装住 PBD particles。结果是
`STOP_WITH_EVIDENCE`：`C4A_convexDecomposition_reference_scope_closed` 和
`C4A_sdf_reference_scope_closed` 都把 256/256 个粒子漏到桌面以下；
`C4A_native_render_mesh_plus_proxy_collision` 明显更接近，保住 244/256 个粒子，但仍有
`outside_source_count=12`、`spill_count=12`，没有达到 zero-leak gate。因此当前可以说
“原生 LabUtopia beaker2 mesh 在这三条 scope-closed 路线下没有成为 fluid-safe collider”，不能说
“level1_pour 可以进入 S3 倒液”。

这次 S2F4 的重要价值是把旧怀疑点排掉：runtime warning scan 中
`material_binding_scope_warning=0`、`cpu_fallback=0`、`gpu_unsupported=0`、`physx_error=0`、
`sdf_warning=0`。也就是说，这次失败不是因为旧 C4 的 material binding scope warning，也不是
因为 SDF cooking / GPU fallback 挂掉，而是粒子 readback 明确显示容器物理碰撞仍漏。视觉 review
也只把 S2F4 图片当 diagnostic evidence：两个 direct native terminal frame 可读；proxy-wrapper 图非空，
但粒子颜色和 proxy 底线接近，只作为泄漏诊断图，不作为产品级 render。

S2F6 已完成：在设计自定义 wrapper 之前，我们先按用户要求把 Isaac/PhysX 原生或内置的
`mesh collision approximation` 方式系统切了一遍。这个步骤故意不设计新 collider，也不把视觉
render mesh 和物理 collider 拆成自定义 proxy；它只在同一个原生路径 `/World/beaker2/mesh`
上改 collision contract：`MeshCollisionAPI` approximation、contact/rest offset、SDF 参数；
non-RAW 方案还会关闭该 prim 上已有的 rigid-body/kinematic flags，避免动态刚体口径干扰静态容器测试。
它验证的是“官方/内置一键模式能不能直接救这个烧杯”，不是在设计新的杯壁。

运行方式：

```text
source_usd=outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd
mesh_path=/World/beaker2/mesh
runtime=IsaacSim41 headless
particle_source=/World/ParticleSet
selected_particle_count=512
steps=120
trace_interval=10
video_stride=10
PBD_completion=runtime overlay
custom_wrapper_used=false
```

我们测试了 10 个 built-in/native modes：

| Variant | 结果 | source retention | outside | spill | below table | 产品解释 |
|---|---|---:|---:|---:|---:|---|
| `RAW_AS_IS` | `FAIL_CONTAINER_LEAK` | `0.8027` | `101` | `11` | `90` | 原始 authored collider 最接近，但仍明显漏。 |
| `NATIVE_NONE` | `FAIL_CONTAINER_LEAK` | `0.3770` | `319` | `0` | `319` | 负向诊断：几乎直接掉下去。 |
| `NATIVE_MESH_SIMPLIFICATION` | `FAIL_CONTAINER_LEAK` | `0.3750` | `320` | `0` | `320` | 简化 mesh 没形成可靠杯底/杯壁。 |
| `NATIVE_CONVEX_HULL` | `FAIL_CONTAINER_LEAK` | `0.0918` | `465` | `131` | `334` | convex hull 对开口杯内腔不合适。 |
| `NATIVE_CONVEX_DECOMPOSITION` | `FAIL_CONTAINER_LEAK` | `0.6582` | `175` | `11` | `164` | 比多数模式好，但离 zero-leak 很远。 |
| `NATIVE_SDF_64` | `FAIL_CONTAINER_LEAK` | `0.3809` | `317` | `0` | `317` | SDF 64 没兜住。 |
| `NATIVE_SDF_128` | `FAIL_CONTAINER_LEAK` | `0.3535` | `331` | `1` | `330` | SDF 128 没兜住。 |
| `NATIVE_SDF_256` | `FAIL_CONTAINER_LEAK` | `0.3887` | `313` | `2` | `311` | SDF 256 仍没兜住。 |
| `NATIVE_BOUNDING_CUBE` | `FAIL_CONTAINER_LEAK` | `0.0273` | `498` | `193` | `305` | 负控，不是生产路线。 |
| `NATIVE_BOUNDING_SPHERE` | `FAIL_CONTAINER_LEAK` | `0.0078` | `508` | `178` | `330` | 负控，不是生产路线。 |

所有 10 个 variant 都完成了 runtime step、particle readback 和 closeup video；没有缺失 runtime result。
但 `static_hold_pass_count=0`、`promotable_variant_ids=[]`，所以 S3 仍不放行。给产品经理的白话结论是：
我们已经先试过“不要自定义，直接切 Isaac/PhysX 内置 collider approximation”的路线；这些一键模式都没把
LabUtopia 原生烧杯变成 `fluid-safe container`。因此下一步做 `fluid-safe wrapper collider` 不是跳过
官方能力，而是在官方/内置路线失败后进入更可控的工程方案。

正式证据：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_runtime_sweep_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001/
tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py
tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py
tests/test_fluid_colleague_native_collider_approx_sweep.py
```

这次 runtime 还修正了一个重要的 IsaacSim41/PhysX 生命周期问题：不能直接 `SetActive(false)` 关掉同事 USD
里原始不完整的 `/World/fluid`、`/World/ParticleSet`、`/World/ParticleSystem`，否则 Kit/PhysX 可能在后续
`update()` 时访问 expired prim。现在 runner 保持这些 prim active，但把它们 hide/disable，然后另建
`/World/CompletedPBD/ParticleSystem` 和 `/World/CompletedPBD/ParticleSet` 做真正的 step/readback。

## 同事 liquid USD 的 bounded 漏液证据

同事提供的文件是：

```text
outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd
```

给产品经理的通俗解释是：这个文件不是“空的”，它确实在 `level1_pour` 的 source beaker
`/World/beaker2` 附近放了液体点位，原始 `/World/ParticleSet` 有 `50000` 个点。但是“杯子里有液体点位”
不等于“IsaacSim41 / EBench 里真实液体可以稳定盛住”。USD 里可以写一堆初始点，就像把水珠坐标先摆在杯子里；
真正 benchmark 需要的是：simulation step 之后，这些点作为 PhysX/PBD 粒子还能被杯子的碰撞体留住，并且
能稳定 readback。

这次我们没有修改同事原始 USD，也没有直接把“完整 50000 粒子原文件”当成已验收资产。我们做了一个受控
bounded smoke：

```text
source USD: lab_001_level1_pour_tabletop_with_liquid.usd
source prim: /World/ParticleSet
original particle count: 50000
sampled particle count: 512
authored particle width: 0.0005940000992268324
runtime: IsaacSim41 headless
collider mode: native-proxy-wrapper
position mode: colleague-sampled
steps: 120
diagnostic_particle_size_override_used: false
```

白话说，我们从同事文件里的 `50000` 个液体初始点中确定性抽样 `512` 个，保留原始粒子宽度，把它们重新写成
IsaacSim41 能 step、能 readback 的红色 PBD 粒子；杯子外观仍使用 LabUtopia 原生 `beaker2`，碰撞体使用
当前流体 spike 里更可控的 `native-proxy-wrapper` 诊断路线。这个做法的目的不是美化画面，而是让“到底有没有漏”
可以用粒子坐标统计判断。

正式结果是 `FAIL_CONTAINER_LEAK`：

```text
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
```

产品经理可以这样理解：第 0 步时，`512` 个红色粒子全部在 source beaker 区域里；step 之后，`362` 个粒子
已经掉到桌面高度以下，只有 `150` 个还留在 source 区域里。粒子没有丢失，也没有 NaN，readback 也确实在更新。
所以这次不是“看不清所以瞎猜漏了”，而是粒子坐标统计支持“这个 bounded 配置装不住液体”。

对应证据是：

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/runtime_smoke_summary.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/particle_readback_trace.jsonl
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/colleague_liquid_leak_red_side_projection.mp4
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/projection_frames/frame_0000.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/projection_frames/frame_0060.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/projection_frames/frame_0120.png
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001/minimal_native_beaker_slice.usda
```

这段红色视频是对准 source beaker 的 diagnostic side projection：蓝色框表示 source beaker 区域，灰线表示桌面高度，
红点表示从同事液体点位抽样出来的 PBD 粒子。它很适合给产品看“step 前在杯里、step 后掉到桌下”，但它不是
完整 Isaac RGB camera render，也不是材质/视觉 parity 证据。

这次 debug 还排除了一个容易误判的问题：最早几次运行出现过 `FAIL_READBACK_UNAVAILABLE`，原因是
`World.reset()` 后 USD readback 设置被 runtime 重置成：

```text
update_particles_to_usd=false
suppressReadback=true
```

这会让 `/World/ParticleSet.points` 看起来不动，不能判断漏不漏。现在 runner 在 reset/play/update 后重新固定：

```text
SETTING_UPDATE_TO_USD=true
SETTING_UPDATE_PARTICLES_TO_USD=true
SETTING_UPDATE_VELOCITIES_TO_USD=true
/physics/suppressReadback=false
```

所以当前 `FAIL_CONTAINER_LEAK` 是 readback 闭环后的结果，不是 readback 没刷新造成的假象。

这条证据释放的 claim 很窄：

```text
colleague_liquid_usd_bounded_leak_smoke_executed=true
colleague_liquid_usd_bounded_classification=FAIL_CONTAINER_LEAK
leak_status_supported_by_particle_readback=true
red_side_projection_video_available=true
```

仍然禁止说：

```text
original_50k_colleague_usd_is_benchmark_ready
direct_original_50k_colleague_usd_runtime_result
level1_pour_true_fluid_runtime_passed
s3_kinematic_pour_released
s4_franka_replay_released
ebench_score_or_policy_claim_allowed
diagnostic_projection_equals_product_camera_render
```

下一步不应该直接进 S3 倒液视频。更稳的顺序是：先把这次结果作为 colleague-liquid bounded leak evidence 固化；
如果需要对外展示，再补一条完整 Isaac RGB review camera，但判定仍以 particle readback 为准；然后继续
`S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP`，设计能真正 zero-leak 静态持液的 fluid-safe wrapper collider。只有静态持液
在 512/1024/更高粒子数下稳定通过，才释放 S3 kinematic pouring。

## 同事 50k liquid USD 补全 PBD 后静置漏液证据

这次新增的目标不是证明“不漏”，而是给领导展示一个更直接的结论：同事文件里的 `50000` 个液体初始点位，
在我们补齐 IsaacSim41 PBD 物理以后，静置就会漏。

这里要把三件事分清楚：

| 名称 | 做了什么 | 可以说明什么 |
|---|---|---|
| raw USD D0 | 只检查同事原文件是否已经能直接 step；不补 PBD material、不加 wrapper collider。 | 原文件有 `50000` 个点，但 raw runtime contract 不完整，不能直接当 benchmark-ready 液体。 |
| bounded B0 | 抽样 `512` 个点，补成 PBD 粒子，做小样本静置漏液诊断。 | 小样本已经会漏，说明方向有问题。 |
| 50k D1-D3 | 使用全部 `50000` 个点，补齐 PBD runtime overlay，静置 step，并用真实 RGB camera 取证。 | 当前路线在原始粒子规模下也会漏，且有可给领导看的图和视频。 |

正式运行：

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708.json
artifact_dir=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/
runtime=isaacsim41
collider_mode=native-proxy-wrapper
position_mode=colleague-sampled
particle_limit=0
steps=120
trace_interval=10
video_stride=10
require_camera_rgb=true
```

`particle_limit=0` 在这个 runner 里表示“不要抽样，使用全部原始点位”。所以这次不是 `512` 小样本，
而是完整 `50000` 个同事液体初始点位：

```text
particle_scope=full_original_50k
full_original_50k_completed_pbd_overlay=true
original_particle_count=50000
selected_particle_count=50000
runtime_step_executed=true
d1_pbd_completion_overlay_executed=true
d2_static_hold_leak_evidence_executed=true
```

关键结果：

```text
classification=FAIL_CONTAINER_LEAK
source_retention_fraction=0.27974
outside_source_count=36013
below_table_count=36013
spill_count=0
target_count=0
particle_count_final_fraction=1.0
nan_count=0
readback_position_changed=true
max_displacement=0.19898774732047234
```

给产品经理的白话解释：这次 `50000` 个点都进了 IsaacSim41 PBD runtime，也都能 readback，粒子没有丢失、没有
NaN。但静置 `120` step 后，`36013` 个点已经不在 source beaker 区域里，并且低于桌面高度。也就是说，
这不是“倒液动作太剧烈导致洒了”，而是“杯子和当前碰撞路线静止都装不住这批 PBD 粒子”。

真实 RGB camera 也已经补上：

```text
rgb_video=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/colleague_liquid_static_leak_rgb_camera.mp4
rgb_terminal_frame=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/rgb_camera_frames/frame_0120.png
diagnostic_projection_video=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/colleague_liquid_leak_red_side_projection.mp4
diagnostic_projection_terminal_frame=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_20260708_001/projection_frames/frame_0120.png
visual_review=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_50k_completed_pbd_static_leak_visual_review_20260708.json
```

独立视觉 review 的结论是 `PASS`：RGB 终帧里，烧杯居中、可识别，杯底外侧红色漏出区域清楚；projection 终帧里，
蓝色 source beaker 区域和红色 below-table leak 点也清楚，适合解释 `below_table_count=36013`。

这里的红色要严格解释：红色 D3 review markers 是从同一步的 `particle_readback_positions` 生成的非碰撞可视化标记，
只是把很小的 PBD 粒子位置放大给人看；它们不参与物理、不改变漏液结果。真正判断漏不漏的依据仍然是
`particle_readback_trace.jsonl` 里的 region counts。

这条证据允许说：

```text
colleague_50k_completed_pbd_static_leak_run_executed=true
colleague_50k_completed_pbd_static_leak_classification=FAIL_CONTAINER_LEAK
colleague_50k_completed_pbd_static_leak_below_table_count=36013
colleague_50k_completed_pbd_static_leak_real_rgb_camera_available=true
```

仍然不能说：

```text
raw_50k_colleague_liquid_usd_can_direct_step_as_true_pbd_fluid
completed_pbd_static_leak_equals_benchmark_ready_fluid
real_rgb_review_marker_equals_physical_fluid_mesh
level1_pour_true_fluid_runtime_passed
s3_kinematic_pour_released
fluid_score_claim_allowed
```

后续如果领导问“那能不能让它不漏”，那不是继续调这条证据线，而是进入 D4 / `S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP`：
重新设计 fluid-safe wrapper collider。只有 D4 候选先通过 D2 静置 zero-leak，再考虑 S3 倒液。

## 同事 full native USD 场景 50k 补全 PBD 后静置漏液视频

上面那条 `50k completed-PBD static leak` 证据用的是 minimal native beaker slice：它适合先证明物理读数会漏，
但用户明确要求“我要原生的 USD 场景中录下液体怎么 step 的视频”。因此我们又补了一条更强的证据：
直接打开同事给的完整入口文件：

```text
outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd
```

这次不是只截出杯子，也不是新搭一个最小场景，而是在原生 `level1_pour` 桌面布局中做 runtime 取证。
我们仍然不修改同事原始 USD：原始 `/World/ParticleSet` 只作为 `50000` 个液体初始点位的数据源；运行时把
原始不完整的 `/World/fluid`、`/World/ParticleSet`、`/World/ParticleSystem` 保持 active 但 hide/disable，
另起一套完整 PBD overlay：

```text
/World/CompletedPBD/ParticleSystem
/World/CompletedPBD/ParticleSet
```

为什么要这样做？因为 D0 已经证明原始 USD 还缺完整 true fluid runtime 合同：raw USD 有点位，但缺
`PhysxPBDMaterialAPI`，`PhysicsScene` 的重力也不可信。直接把 raw USD 按真实流体 step，不会得到可信结论。
这次做的是“把同事的 50000 个点位补成 IsaacSim41 可 step/readback 的 PBD 粒子”，再看它在原生桌面场景里
静置会不会漏。

正式证据：

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708.json
artifact_dir=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001/
runtime=isaacsim41
source_usd=outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd
particle_scope=full_original_50k
selected_particle_count=50000
runtime_pbd_completion_overlay_used=true
steps=24
```

关键结果：

```text
classification=FAIL_CONTAINER_LEAK
source_retention_fraction=0.07398
outside_source_count=46301
below_table_count=46301
particle_count_final_fraction=1.0
nan_count=0
readback_position_changed=true
max_displacement=3.258722390681572
```

给产品经理的白话解释：这次 `50000` 个液体点都进入了 IsaacSim41 PBD runtime，粒子没有丢、没有 NaN，
位置也确实随着 step 改变。但静置 `24` step 后，`46301` 个粒子已经低于桌面线，source 区域只留下约
`7.4%`。所以它比旧最小切片更接近用户想看的“原生 USD 场景视频”，结论也更直接：同事这份 50k 点位
补成真实 PBD 后，当前杯子/碰撞路线静置就装不住。

这次还单独处理了材质问题。早期原生场景视频出现红色异常，主要是 MDL runtime compile / import 兼容问题，
不是我们想展示的液体颜色。现在采用的是 `isaacsim41_core_mdl_local_mirror`：

```text
copy /isaac-sim/kit/mdl/core/Base/*.mdl
copy /isaac-sim/kit/mdl/core/mdl/OmniSurface/*.mdl
retarget native info:mdl:sourceAsset to the local mirror
retargeted_shader_count=10
mdl_compile_status=PASS
```

其中 `/World/Looks/OmniSurface_Glass/Shader` 在 IsaacSim41 下还有一个兼容 fallback：

```text
OmniSurfacePresets.mdl::OmniSurface_Glass
-> OmniGlass.mdl::OmniGlass
```

通俗说，这不是把杯子粗暴刷成蓝色，也不是用 preview color 假装材质好了；它是把 IsaacSim41 能编译的官方
core MDL 文件 local mirror 到证据目录，并把 shader 指向这套本地依赖。这样 runtime log 里
`mdl_compile_status=PASS`，画面不再是红色 fallback。但这仍然不能升级成
`LabUtopia51 native visual material parity`：因为我们为了 IsaacSim41 兼容，把
`OmniSurface_Glass` 映射成了 `OmniGlass`，视觉上只能说“可渲染、可解释”，不能说“和 LabUtopia51 原生材质完全一致”。

视频证据：

```text
beaker2_closeup_native_material.mp4       # 主要给产品/领导看
beaker2_closeup_review_markers.mp4        # 诊断用，把 readback 粒子位置放大
camera1_native_material.mp4               # 原生桌面上下文，太远，不看漏液细节
camera2_native_material.mp4               # 原生桌面上下文，太远，不看漏液细节
visual_review=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_visual_review_20260708.json
```

独立视觉 review 的整体结论是 `WARN`，不是无 caveat 的 `PASS`。具体说：

| 画面 | 结论 | 产品解释 |
|---|---|---|
| early closeup | `WARN` | 第一张可用 closeup frame 中杯口可见，但红色粒子团太满，看起来像一个实体红块，不适合单独展示材质；它不是 step 0 原始帧。 |
| end closeup | `PASS` | 透明杯子可见，杯外有红色团块/痕迹，能支撑“没有装住”的故事。 |
| review marker | `WARN` | 有助于看粒子位置，但只是诊断 overlay，不是真实水面。 |
| Camera1/Camera2 | `WARN` | 能证明是原生桌面布局，但离杯子太远，不能作为漏液细节证据。 |

所以给领导汇报时应这样说：我们已经在原生 USD 场景里跑了 50k completed-PBD step，并录到了 closeup/native
camera 视频；物理读数明确显示静置漏液。画面能支持这个结论，但仍是工程证据，不是最终产品级流体视觉。
下一步如果要从“展示会漏”走到“让它不漏并能 benchmark”，必须进入 D4 / `S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP`，
重新设计 fluid-safe wrapper collider。

### 20 秒长视频版本

短版 `beaker2_closeup_native_material.mp4` 只有 `0.75s`，原因是当时只跑了 `24` step、每 `4` step
取一帧，最终只有 `6` 帧。现在已按“20 秒更长版本”重录一条新证据：

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708.json
artifact_dir=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/
primary_video=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_20260708_001/beaker2_closeup_native_material.mp4
```

这版仍然是同一个原生完整 USD 场景、同一个 source beaker、全部 `50000` 个液体初始点位，以及同一套
`isaacsim41_core_mdl_local_mirror` 材质闭环：

```text
steps=240
video_stride=1
video_fps=12
frame_count=240
duration=20.000000s
resolution=960x540
selected_particle_count=50000
runtime_step_executed=true
mdl_compile_status=PASS
classification=FAIL_CONTAINER_LEAK
below_table_count=49235
source_retention_fraction=0.0153
```

给产品经理的解释：这版视频已经足够长，可以看清楚红色液体/粒子团随 step 从满杯状态逐步塌到杯底和前侧；
它是原生完整 USD 场景中的 native-material closeup camera。需要注意的是，肉眼视频不能单独证明
`49235` 个粒子低于桌面线，因为很多 below-table 粒子从这个相机角度不可见；这个数字仍来自
`particle_readback_trace.jsonl` 的 region count。也就是说，视频负责“让人看懂场景和时间变化”，
readback 负责“证明漏液分类”。

对应辅助视频：

```text
beaker2_closeup_review_markers.mp4   # 诊断 overlay，不是真实 fluid mesh
camera1_native_material.mp4          # 原生桌面远景上下文
camera2_native_material.mp4          # 原生桌面俯视上下文
visual_review=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_long_visual_review_20260708.json
```

## 同事 50k USD 的液面重建展示层

20 秒 native-material closeup 证明了完整原生 USD 场景能被补成可 step/readback 的 50k PBD runtime，
但它使用红色粒子/marker 可视化，给产品和领导看时很容易被误解成“材质坏了”“粒子很大”或“这就是最终水面”。
因此我们新增了一条独立的 `presentation lane`：物理输入、粒子轨迹、collider 设置和 leak classifier 不变，
只在渲染层开启 `PhysX Isosurface`，把离散 `PBD particles` 重建成更连续、更像液面的蓝色
`reconstructed render surface`，并使用固定的领导汇报 camera / lighting。

正式证据：

```text
artifact_dir=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_smoke_20260708_001/
main_manifest=RAW_AS_IS_runtime_full50k_refined_v2.json
main_video=RAW_AS_IS_runtime_full50k_refined_v2/presentation_isosurface.mp4
wide_context_manifest=RAW_AS_IS_runtime_full50k_v1.json
wide_context_video=RAW_AS_IS_runtime_full50k_v1/presentation_isosurface.mp4
source_usd=outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd
source_particle_count=50000
selected_particle_count=50000
runtime_step_executed=true
presentation_video_enabled=true
presentation_isosurface_enabled=true
debug_particle_display_enabled=false
```

主展示 run 的物理结论仍然是失败：

```text
classification=FAIL_CONTAINER_LEAK
below_table_count=19093
outside_source_count=24606
spill_count=5513
source_retention_fraction=0.50788
particle_count_final_fraction=1.0
nan_count=0
cpu_collision_fallback_detected=false
```

主展示 run 的 `Isosurface` 参数采用 Isaac Sim 4.1 demo-style 设置，而不是随意把粒子刷成蓝色：

```text
api_path=/World/CompletedPBD/ParticleSystem
claim_boundary=visual_surface_reconstruction_only
parameter_reference=isaacsim41_fluid_isosurface_cup_demo_style
grid_spacing=0.00028868404822424056
surface_distance=0.00030472205090336497
grid_filtering_passes=GS
grid_smoothing_radius=0.0003207600535824895
num_mesh_smoothing_passes=4
num_mesh_normal_smoothing_passes=4
max_subgrids=12500
max_vertices=3200000
max_triangles=6400000
```

`presentation_visual_contract.claim_boundary_text` 已写入 manifest，核心口径是：

```text
This video is a presentation render of the same simulated particle trajectory used for the diagnostic verdict.
Leak classification and spike assessment are based on particle readback, not on visual appearance.
Rendering choices including PhysX Isosurface reconstruction, material color/opacity, lighting, and camera framing were adjusted only to improve human readability for review.
These adjustments do not change the particle simulation, collider setup, leak classifier, or benchmark claims.
```

给产品经理的白话解释：这条蓝色视频不是“把漏液问题修好了”，而是“把同一条失败轨迹用更像液面的方式展示出来”。
它解决的是展示层问题：红色点云太像一坨，领导很难判断是不是液体；`PhysX Isosurface` 能让人更直观看到
source beaker、target beaker、桌面和泄漏区域。它不解决 `collider` 问题，也不能替代 readback：
能不能放行下一阶段仍看 `below_table_count=0`、`spill_count=0`、`outside_source_count=0` 这些物理 gate。

独立 visual review 对这版仍是 `WARN`，不是无 caveat 的 `PASS`。优点是：不再是红色 debug 粒子、不是黑屏、
相机能看到杯子和蓝色液面；风险是：泄漏区域仍有 speckled 观感，不能包装成 polished pour，也不能说成
`LabUtopia51 native visual material parity`。因此周报可以把它作为“更适合领导理解的诊断展示视频”，但不能把它
升级为 benchmark-ready fluid evidence。

## 同事 raw 50k liquid USD 的 D0 直接-step 准入审计

D0 的 raw 50k 直接-step 准入审计已完成；它没有跑原始 `50000` 粒子的 timeline step，结论是
`STOP_RAW_RUNTIME_INCOMPLETE`。这句话的意思不是“同事的文件没有液体”，而是：同事的文件里确实有
`50000` 个液体点，但它还不是 IsaacSim41 可以直接按真实 PBD 液体去 step 的完整 runtime 资产。

这次 D0 没有替同事文件补东西，也没有把粒子换成红色诊断粒子，更没有加 wrapper collider。它只做一件事：
打开原始 USD，检查 `/World/ParticleSet`、`/World/ParticleSystem` 和 `/World/PhysicsScene` 这三类对象是否已经
满足“可以直接跑真实液体”的最小合同。

正式结果：

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_raw_usd_direct_step_audit_20260708.json
artifact_dir=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_colleague_raw_usd_direct_step_audit_20260708_001/
runtime=isaacsim41
audit_mode=static_raw_contract_audit
classification=STOP_RAW_RUNTIME_INCOMPLETE
runtime_step_executed=false
raw_50k_timeline_step_executed=false
step_skipped_reason=raw_runtime_contract_incomplete
direct_original_50k_runtime_claim_allowed=false
```

审计看到的关键事实：

```text
raw particle count=50000
has_PhysxParticleSetAPI=true
has_PhysxParticleSystem=true
particle_system_relationship_closed=true
has_PhysxPBDMaterialAPI=false
gravity_direction=(0, 0, 0)
gravity_magnitude="-Infinity"
gravity_invalid_reasons=["zero_gravity_direction", "nonfinite_gravity_magnitude"]
gpu_dynamics_authored=true
broadphase_type=GPU
solver_type=TGS
material_binding_targets=["/World/Looks/OmniGlass_01"]
```

给产品经理的白话解释：现在这个 raw USD 更像“杯子里预先摆好了 50000 个水点的位置”，但还缺“这些水点在
IsaacSim41 里作为真实液体运动”的完整说明书。其中最关键的两个缺口是：

| 缺口 | 白话解释 | 为什么会阻止直接 step |
|---|---|---|
| 缺 `PhysxPBDMaterialAPI` | 没有告诉 PhysX 这些点的液体材料参数，比如像水还是像胶、粒子如何相互作用。 | 只有点位和普通玻璃材质，不等于 PBD fluid material。 |
| 重力无效 | `gravity_direction=(0,0,0)` 且 `gravity_magnitude="-Infinity"`；审计记录为 `zero_gravity_direction` 和 `nonfinite_gravity_magnitude`。 | 物理世界的基础力场不成立，不能把 raw step 结果当成可信液体运动。 |

所以 D0 的正确处理是“停止并留下证据”，而不是强行跑 timeline 然后拿不可信画面当结论。后续如果要把同事这个
USD 做成可评测液体，路线应该进入 D1/D2/D4：把原始点位当 initial condition，补齐 PBD material、有效
PhysicsScene、GPU/readback 设置和 fluid-safe wrapper collider；等静态持液通过后，才进入 D3 RGB review camera
和 S3 kinematic pouring。

这份 D0 manifest 里的 `particle_count`、`nan_count` 和 `readback_position_changed=false` 是 no-step
static snapshot 字段，只说明原始点位可被读到、没有 NaN；它们不是 post-timeline survival evidence，不能被解读成
“原始 `50000` 粒子 step 后保持稳定”。

## 允许和禁止的汇报

允许：

```text
True fluid spike is planned.
level1_pour currently has no true fluid.
lab_003/clock.usd provides a local particle template.
S2/S3 will test a collider matrix, not one hard-coded collider.
S1 standalone PBD particle runtime smoke passed.
S2 beaker collider matrix completed with STOP_WITH_EVIDENCE.
C2 segmented convex wall pieces is the closest failed candidate, not a pass.
S2F collider follow-up has completed through S2F6 with STOP_WITH_EVIDENCE; S3 is still not released.
S2F4 native beaker mesh isolation completed with STOP_WITH_EVIDENCE.
Native beaker2 mesh is not proven fluid-safe for PBD particles.
S2F6 native collider approximation sweep completed: 10/10 runtime step/readback, static_hold_pass_count=0, promotable_variant_ids=[].
Built-in/native Isaac/PhysX approximation modes did not produce a fluid-safe native beaker collider under this setup.
Colleague liquid USD bounded smoke completed with FAIL_CONTAINER_LEAK.
Colleague liquid leak status is supported by particle readback in the 512-particle bounded run.
Colleague raw 50k liquid USD D0 readiness audit completed with STOP_RAW_RUNTIME_INCOMPLETE.
Colleague raw 50k liquid USD runtime_step_executed=false.
Raw 50k points exist, but direct original runtime claim is not allowed yet.
Colleague 50k completed-PBD static leak diagnostic completed with FAIL_CONTAINER_LEAK.
Colleague 50k completed-PBD static leak is supported by particle readback: below_table_count=36013.
Colleague 50k completed-PBD real IsaacSim41 RGB review camera evidence is available.
Colleague 50k completed-PBD PhysX Isosurface presentation render is available for human-readable review.
Presentation render uses the same simulated particle trajectory and does not replace particle readback.
```

禁止：

```text
level1_pour already has real fluid.
standalone S1 equals level1_pour fluid integration.
fluid is already EBench-scoreable.
policy can already solve fluid pouring.
official leaderboard claim.
visual-only water equals true fluid.
diagnostic projection equals product-quality render.
original 50k colleague liquid USD is benchmark-ready.
direct original 50k colleague liquid USD runtime result.
raw 50k colleague liquid USD can be directly stepped as true PBD fluid.
completed-PBD static leak evidence means benchmark-ready true fluid.
red RGB review markers are physical fluid mesh or colliders.
presentation video equals physics success.
isosurface reconstruction equals zero-leak.
presentation water material equals LabUtopia51 visual material parity.
native collider approximation sweep proves benchmark-ready true fluid.
built-in/native approximation modes have passed static hold.
```

## 关联文档

```text
docs/superpowers/specs/2026-07-07-true-physx-pbd-fluid-spike-design.md
docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md
```

## Manifest 命名

```text
run_id prefix: fluid_spike_isaacsim41_ebench_<stage>_<scene>_<YYYYMMDD>_<NNN>
manifest family: docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s<stage>_<slug>_<YYYYMMDD>.json
forbidden prefixes: eos2_, expert_oracle_, score_oracle_, aan_
```

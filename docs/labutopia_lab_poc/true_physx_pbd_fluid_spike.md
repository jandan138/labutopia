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

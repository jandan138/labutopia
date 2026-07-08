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
所以 S2F0 当时的产品口径是：先进入 `S2F1_C2_PROXY_SWEEP`，不是进入倒液视频。现在 S2F1、S2F2
和 S2F5 都已经完成，当前产品口径应更新为：S2F5 已经证明唯一静态持液候选不稳定，S3 仍不放行，
下一步回到 `S2F3_C3_SDF_SWEEP` 和 `S2F4_C4_NATIVE_MESH_ISOLATION` 两条 collider 诊断路线。

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
方案；因此现在不能进入 S3，也不能说 `level1_pour` 已经能真实倒液。下一步不是继续手调这个候选，而是
按原规划做 F3/F4：F3 用 `SDF` 路线测试凹形容器 collider，F4 用 native beaker mesh isolation 判断原生
杯子是否能被修成 fluid-safe collider。

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
| S2F Collider Follow-up | 怎么把 S2 失败收敛成一个可持液 collider？ | 至少一个非负控 `PASS_SOURCE_HOLD` | 参数/几何/cooking 失败归因 |
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
S2F collider follow-up plan is ready; S3 is still not released.
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

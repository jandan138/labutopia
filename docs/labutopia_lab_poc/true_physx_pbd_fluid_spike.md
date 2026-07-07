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
| S1 Particle Smoke | 粒子能不能在 Isaac runtime 中 step？ | PBD 粒子本体可运行 | GPU/schema/readback 失败归因 |
| S2 Beaker Collider Smoke | 烧杯能不能装住粒子？ | 至少一个 collider 能稳定持液 | collider 失败矩阵 |
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

S2 只看“静态装不装得住”。S3 再看“kinematic source beaker 连续倾斜后流不流得出来”。
如果 static pass 但 moving fail，结论归类为 `KINEMATIC_COUPLING_FAIL`，不把它误写成
collider 完全可用或 true fluid 完全不可用。

## 允许和禁止的汇报

允许：

```text
True fluid spike is planned.
level1_pour currently has no true fluid.
lab_003/clock.usd provides a local particle template.
S2/S3 will test a collider matrix, not one hard-coded collider.
```

禁止：

```text
level1_pour already has real fluid.
fluid is already EBench-scoreable.
policy can already solve fluid pouring.
official leaderboard claim.
visual-only water equals true fluid.
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

# liquid_0812 规范杯体驱动复测结论

日期：2026-08-13

## 一句话结论

源杯已经从运行时 USD transform 瞬移改为 PhysX kinematic target 驱动，姿态跟踪通过；但同事优化 USD 的液体仍在倾斜前逸出，30/60/120 Hz 三档均未通过“不撒不漏”质量门。因此本轮没有选出可进入 RTX 50 Hz 视频交付的积分频率。

## 修复了什么

- `/World/beaker2` 在粒子初始化前切换为 kinematic rigid body。
- 通过 `RigidBodyView.set_kinematic_targets` 写入目标，不再在正式路径中逐帧修改 USD transform 并调用 `flush_changes()`。
- 控制轨迹保持 30 Hz；60/120 Hz 时分别在线性位移和最短四元数弧上插入 2/4 个物理目标。
- 每个控制状态使用 PhysX tensor readback 验证真实杯体姿态，分类也使用真实姿态，而不是命令姿态。
- 保持同事 USD 的 548 粒子、convex decomposition、offset、16 次位置迭代和资产闭包不变。

实现过程中还修复了一个 Isaac 4.1 生命周期问题：`RigidBodyView` 不拥有 tensor backend，必须在整个仿真期间保留 `SimulationView` 的强引用；否则初始 transform 可能可读，但后续 kinematic target 写入会报 backend failure。

## 正式 sweep

控制频率均为 30 Hz；每档完整运行 953 个控制状态。三次父 manifest 均为 `passed`，effective-runtime v2 receipt 均为 `MATCH`：Python 3.10.20、Isaac Sim 4.1.0.0、Kit NumPy 1.26.0、USD 0.22.11。

| 积分频率 | 子步/控制帧 | 物理均值 | 模型就绪 FPS | 倾斜前最多杯外 | 最终目标杯 | 最终桌面 spill | 最终桌下 | 结论 |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 30 Hz | 1 | 5.76 ms | 164.60 | 32 / 548 | 507 | 40 | 1 | NO-GO |
| 60 Hz | 2 | 10.99 ms | 88.35 | 23 / 548 | 496 | 38 | 14 | NO-GO |
| 120 Hz | 4 | 21.64 ms | 45.46 | 23 / 548 | 478 | 40 | 30 | NO-GO |

三档最大位置跟踪误差均为 `1.2288e-7 m`（约 0.000123 mm），最大旋转误差均为 `2.4567e-5°`，远低于 0.5 mm / 0.1° 门槛。因此“杯子没有按轨迹运动”已经不是当前失败原因。

## 漏液发生在哪里

120 Hz 短测的第 0 个控制状态是 548/548 个粒子都在源杯内；随后尚未倾斜，杯内数就在数帧内下降并稳定到约 527–529。静置 8 秒时三档最低杯内数分别为 524、525、526。也就是说，这不是初始分类框偏移，而是物理推进后真实出现了早期逸出/挤出。

提高积分频率只把倾斜前最大杯外数从 32 降到 23，没有达到允许上限 10；完整倾倒的桌下粒子反而从 1 增加到 14/30。因此不能用“多算子步”作为修复。

下一轮应优先检查：

1. 源杯 convex decomposition 的内壁是否形成对粒子稳定、连续的容器；
2. 粒子初始采样是否距离内壁/杯底过近，导致第一批求解步骤把粒子推出；
3. 5 mm source rest offset、10 mm contact offset 与 5 mm particle contact offset 的组合；
4. 在不改资产外观的条件下，是否需要专用的不可见 compound/convex 容器代理。

## 证据

- sweep：`outputs/liquid0812_kinematic_integration_sweep_20260813_v1/integration_sweep.json`
- sweep 内容哈希：`f343c5f5c2b7fda02adf0dd5e7341e80c90991c7dc37ce7cd3dd06e2e8401c8f`
- 120 Hz 成功短测：`outputs/liquid0812_kinematic_smoke_20260813_v6/`
- 已验证 runner 对照：`outputs/liquid0812_known_kinematic_runner_contrast_20260813/`
- runner：`tools/labutopia_fluid/run_isaac41_liquid0812_benchmark.py`
- async RTX 接口：`tools/labutopia_fluid/run_isaac41_liquid0812_async_rtx_benchmark.py`

按预先约定的 stop rule，物理质量失败后不继续生成新的 RTX 视频。历史 8 月 12 日视频仍仅证明旧驱动的 RTX 吞吐与失败形态，不能作为本轮规范驱动的“不漏液”视频。

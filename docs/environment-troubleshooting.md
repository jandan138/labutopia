# 环境和踩坑记录

本文记录当前 LabUtopia 跑 Isaac Sim expert trajectory 时遇到的环境问题和处理原则。

## Driver 风险

当前 driver：

```text
570.153.02
```

本次调研 Isaac Sim 5.1 Linux requirements 时，官方文档列出的 tested driver 是：

```text
580.65.06
```

风险判断：

- 短流程 headless smoke 已经跑通。
- 29 个视频批跑也基本跑通，28 个成功，1 个 controller bug。
- driver 低于 tested version，长期复杂渲染、材质、RTX、传感器和大规模批处理仍有不确定性。
- 如果这个环境要变成长期共享基线，应升级到 `580.65.06` 或更高的 Isaac Sim 5.1 官方支持版本。

## Isaac 和旧目录清理

旧目录已经删除：

- `/cpfs/user/zhuzihou/isaac-sim-5.0`
- `/cpfs/user/zhuzihou/isaac-sim-5.0.0`
- `/cpfs/user/zhuzihou/IsaacLab`

清理原因：

- 旧 Isaac Sim/Isaac Lab 版本与 LabUtopia 需要的 Isaac Sim 5.1 不一致。
- 旧 Omniverse 内容路径可能通过环境变量、cache 或 config 污染当前运行。
- 用户确认旧项目不用，因此采用彻底删除策略。

## OMNI_SERVER 污染

曾经发现 `OMNI_SERVER` 指向旧内容。每次运行前执行：

```bash
unset OMNI_SERVER
```

如果看到 asset 从旧 Isaac 或旧 Nucleus 路径加载，优先检查：

```bash
env | rg 'OMNI|ISAAC|NUCLEUS'
```

## Omniverse Cache

曾看到 stale cache/proxy 相关配置：

- `/root/.nvidia-omniverse/config/omniverse.toml`
- `/root/.cache/ov/Kit/106.5`
- `/root/.local/share/ov/data/Kit/Isaac-Sim Full/4.5`

当前没有把这些全部作为复现要求删除，因为短流程已经跑通。但如果后续遇到旧 asset、旧 Kit、旧 extension 路径问题，应把这些 cache 纳入清理范围。

## Isaac pip 安装和 Torch

当前环境保留了 `torch==2.9.0+cu126`。安装 Isaac Sim 5.1 pip 包时使用过 `--no-deps`，避免 Isaac 依赖覆盖 torch/cu 版本。

这说明当前环境是“调出来的可用环境”，不是严格 lock 的新环境。建议后续补：

- `environment.yml`
- pip constraints 或 lock file
- 可复用的 container/Singularity recipe
- 明确 torch、cuda wheel、Isaac Sim package 的安装顺序

## Extcache 口径

README 中曾出现类似 `isaacsim[all,extscache]` 的描述，但当前环境并未严格按 extcache 方式沉淀。需要统一：

- 如果长期依赖 extcache，就把 `isaacsim-extscache-*` 写入安装规范。
- 如果当前只要求 pip + 在线/cache 加载，就不要在 README 里暗示 extcache 是已验证流程。

## Project Import 问题

曾遇到 Isaac/cv2 预加载路径里的顶层 `utils` 抢占本项目 `utils` 的问题。当前修复包括：

- 在 `main.py` 中确保 project root 回到 `sys.path` 前面。
- 新增 `utils/__init__.py`，让本项目 `utils` 成为明确 package。

这个问题说明 `main.py` 的 import 和 Isaac app lifecycle 还比较脆弱。后续应把入口重构成更容易测试的函数。

## Headless Video 问题

之前 headless 模式仍可能触发 `cv2.imshow`，这在无显示环境下不合适。当前逻辑已经改为：

- `--headless` 时 `show_video=False`
- `--no-video` 可以显式关闭视频
- `--video-dir` 可以把视频稳定写到指定目录

后续仍建议增加：

- `VideoWriter.isOpened()` 检查
- `try/finally` 释放 video writer
- 多 camera 拼接前检查分辨率一致

## Mock Collector 语义

为了只录视频，当前 `mock_collector` 避免写正式 H5。它目前的一个语义风险是 `clear_cache()` 会推进 episode count，这对 video-only 流程有用，但不完全等价于正式 `DataCollector.clear_cache()`。

后续应写测试明确：

- mock collector 不写 H5。
- max episode 的结束条件符合预期。
- mock collector 不能误用于正式 dataset 生产。

## 材质和资产 WARN

本次视频批跑中看到的典型资产日志：

- `level4_LiquidMixing`: heat device 相关 MDL module 缺失。
- `level5_Mobile_manipulation`: `Materials/mdl_0061.mdl` 缺失。
- `level5_Navigation`: `Materials/mdl_0061.mdl` 缺失。
- `level4_CleanBeaker`: `lounge_booth_table_texture0.jpg` 缺失。

这些没有阻止对应任务成功，但会影响展示质量和可视化可信度。showcase 版本视频应先修 asset，再重录。


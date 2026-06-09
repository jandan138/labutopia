# 2026-06-09 Expert 视频批跑记录

## 目标

把当前 LabUtopia 项目跑起来，只跑 expert trajectory 完成任务，并为所有主 config 录制视频，供后续讨论和视觉 review 使用。

## 结论

| 项 | 结果 |
| --- | --- |
| 主 config | 29 |
| 视频可读 | 29/29 |
| expert 成功 | 28/29 |
| video-only | 1/29 |
| 总帧数 | 38675 |
| final 目录大小 | 约 162 MB |
| final summary | `artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.csv` |

非成功项：

```text
level4_CleanBeaker7Policy
```

它录到了 2001 帧、512x256、约 33.35 秒的视频，但 `success_seen=False`，`exit_code=-11`。日志中可见 controller 调用错误：

```text
PourController.forward() got an unexpected keyword argument 'target_name'
```

因此它只能算 video-only failure trace，不能算 expert 成功轨迹。

## 本次运行路径

临时 config：

```text
docs/tmp/expert_video_configs/20260609_002039/
```

primary run：

```text
artifacts/videos/expert_trajectories/20260609_002039/
```

retry run：

```text
artifacts/videos/expert_trajectories/20260609_002039_retry/
```

final consolidated run：

```text
artifacts/videos/expert_trajectories/20260609_002039_final/
```

final summary：

```text
artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.csv
artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.json
```

这些路径均被 gitignore 管理，不提交进仓库。

## 已做代码调整

为了让项目在当前 Isaac Sim 5.1 pip 环境里稳定跑起来，本次做了几类必要修复：

- `main.py`: 修复 project root/import 顺序，避免 Isaac/cv2 预加载的顶层 `utils` 抢占本项目 package。
- `main.py`: 默认 config 从不存在的 `level3_Heat_Liquid` 改为 `level3_HeatLiquid`。
- `main.py`: `--headless` 真正传入 `SimulationApp`。
- `main.py`: 新增 `--video-dir`，headless 下不再调用 `cv2.imshow`。
- `utils/__init__.py`: 明确本项目 `utils` package。
- `data_collectors/mock_collector.py`: 支持 video-only 流程，避免正式 H5 写入。
- `tasks/cleanbeaker_task.py`: 补充 beaker size/object size state。
- `controllers/cleanbeaker7policy_controller.py`: 局部修复 size 字段读取，但 controller 仍有 `PourController.forward(target_name=...)` 接口 bug。
- `.gitignore`: 忽略 `outputs/`、`docs/tmp/`、`artifacts/videos/`。

## 多角度审阅结论

### 环境角度

当前环境是“本机已跑通”，还不是可迁移的标准环境。

主要风险：

- driver `570.153.02` 低于 Isaac Sim 5.1 Linux 文档 tested driver `580.65.06`。
- Isaac pip 安装中为保留 torch/cu 版本使用过 `--no-deps`，安装顺序需要文档化。
- `OMNI_SERVER`、Omniverse cache 和旧 Isaac 路径可能污染运行。
- extcache 是否作为正式依赖需要统一口径。

建议：

- 长期基线升级 driver 到 `580.65.06` 或官方支持的更新版本。
- 增加 `environment.yml`、constraints/lock 或容器 recipe。
- 把安装顺序和 cache 清理写成脚本或 runbook。

### 代码和流程角度

当前能跑，但流程不够工程化。

主要风险：

- `level4_CleanBeaker7Policy` 仍失败，不能算成功 expert。
- `main.py` 顶层直接 parse args 和启动 `SimulationApp`，难做单元测试。
- video writer 缺 `isOpened()` 检查和 `try/finally` 释放。
- 多相机 `np.hstack` 假设所有 camera 分辨率一致。
- mock collector 的 episode 推进语义需要测试固定。

建议：

- 新增 batch 脚本和 validate 脚本。
- 给 controller/task state contract 加测试。
- 修复 `CleanBeaker7Policy` 后单独重跑。

### 视频视觉角度

所有 final mp4 都可读，contact sheet 也已生成。视频足够作为“执行证据”和讨论材料，但部分不适合作为 showcase。

主要 WARN：

- 开门、开抽屉、开合类任务有较高黑区或相机遮挡。
- `level2_ShakeBeaker`、`level2_StirGlassrod` 是 512x256，展示质量一般。
- `level4_LiquidMixing`、`level5_Mobile_manipulation`、`level5_Navigation`、`level4_CleanBeaker` 有材质或贴图缺失日志。

建议：

- discussion 版本保留当前视频。
- showcase 版本应重新设计 camera、补 asset/material，再重录。

### 文档角度

原 README 更像项目说明，不适合承载本次环境、视频和 run 记录。现在单独沉淀到 `docs/`：

- 入口索引：`docs/README.md`
- 环境复现：`docs/reproduction.md`
- 视频 runbook：`docs/expert-video-runbook.md`
- config 矩阵：`docs/task-config-matrix.md`
- 排障记录：`docs/environment-troubleshooting.md`
- artifact 策略：`docs/artifacts-and-git-policy.md`

## 是否规范

结论：**能跑通，但还不完全规范**。

已经规范的部分：

- 旧 Isaac/Isaac Lab 已清理。
- 当前运行 env 路径明确。
- headless/video 命令明确。
- 视频、临时 config、outputs 已 gitignored。
- 29 个 config 的状态有 summary 和 matrix。

还不规范的部分：

- 缺少一键批跑脚本。
- 缺少一键视频验证脚本。
- 环境未 lock。
- driver 低于 Isaac Sim 5.1 tested driver。
- 一个 expert 配置仍是 video-only。
- 若作为正式 dataset pipeline，mock collector 和视频流程需要与正式 collector 明确隔离。

## 下一步优先级

1. 修复 `level4_CleanBeaker7Policy` 的 controller 接口和 state 字段不一致，单独重跑该 config。
2. 增加 `scripts/record_expert_videos.py` 和 `scripts/validate_expert_videos.py`。
3. 固化环境：driver、Isaac package、torch/cu、pip constraints 或容器。
4. 给 mock collector、video writer、controller state contract 加测试。
5. 对 showcase 视频重新布 camera，并补齐缺失材质/贴图。


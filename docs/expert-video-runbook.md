# Expert 视频运行 Runbook

目标：只跑 expert trajectory 完成任务并录制视频，尽量避免正式数据采集的 H5 写入成本。这个流程用于调试、视觉 review 和讨论，不等同于正式 dataset 生产流程。

## 推荐口径

对外或对内同步本次结果时使用：

```text
29/29 configs have readable videos.
28/29 configs completed successful expert trajectories.
1/29 configs is video_only: level4_CleanBeaker7Policy.
```

不要把“视频存在”写成“expert 成功”。

## 运行前检查

```bash
nvidia-smi
/cpfs/user/zhuzihou/conda-managed/envs/labutopia-py311/bin/python -V
git status --short
```

运行 Isaac 前设置：

```bash
unset OMNI_SERVER
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONUNBUFFERED=1
```

## 临时 config 规则

为视频 review 生成的临时 config 应该落在：

```text
docs/tmp/expert_video_configs/<run_id>/
```

每个临时 config 至少改动：

- `simulation.max_episodes: 1`
- `collector.type: mock`
- `collector.compression: null`
- `collector.output_dir: outputs/expert_video_runs/<run_id>/<config_name>`
- `simulation.save_video: true`
- `simulation.show_video: false`

这样可以让视频输出独立于正式数据采集，避免每个任务都写大 H5。

## 单 config 命令模板

```bash
unset OMNI_SERVER
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONUNBUFFERED=1

/cpfs/user/zhuzihou/conda-managed/envs/labutopia-py311/bin/python \
  main.py \
  --config-dir docs/tmp/expert_video_configs/<run_id> \
  --config-name <config_name> \
  --headless \
  --video-dir artifacts/videos/expert_trajectories/<run_id>/<config_name>
```

输出视频通常是：

```text
artifacts/videos/expert_trajectories/<run_id>/<config_name>/episode_0.mp4
```

## 验证规则

最小验证：

```bash
ffprobe artifacts/videos/expert_trajectories/<run_id>/<config_name>/episode_0.mp4
```

推荐验证字段：

- mp4 可读。
- frame count 大于 0。
- fps 和 resolution 可读。
- 日志中能看到成功完成。
- 进程 exit code 为 0。
- contact sheet 中目标和关键动作可辨认。

QA 标准：

| 级别 | 条件 |
| --- | --- |
| `PASS` | `final_status=ok`，`success_seen=True`，`exit_code=0`，视频可读，动作可辨认。 |
| `WARN` | 成功完成，但存在黑区、相机遮挡、低分辨率、材质缺失或其他展示质量风险。 |
| `VIDEO_ONLY` | 视频可读，但任务没有成功完成，不能计入 expert success。 |
| `FAIL` | 没有视频、视频不可读、动作不可辨认或任务无法启动。 |

## 本次已知 WARN

黑区或相机遮挡较明显的任务：

- `level1_close_drawer`
- `level1_open_door`
- `level2_openclose`
- `level1_open_drawer`
- `level3_open`
- `level4_DeviceOperation`
- `level4_OpenTransportPour`
- `level1_close_door`
- `level1_pour`
- `level2_PourLiquid`
- `level3_PourLiquid`

低分辨率但成功的任务：

- `level2_ShakeBeaker`
- `level2_StirGlassrod`

非成功但有视频：

- `level4_CleanBeaker7Policy`

## 后续脚本化要求

当前流程不够规范，因为批跑、重试、汇总和 QA 仍是人工组合。后续建议新增：

- `scripts/record_expert_videos.py`: 读取 `config/*.yaml`，生成 ignored temp config，逐个运行，落日志和视频。
- `scripts/validate_expert_videos.py`: 用 `ffprobe`/OpenCV 生成 summary、contact sheet、黑区比例和 PASS/WARN/FAIL。
- 单元测试覆盖 mock collector、video writer、Hydra 参数解析和 controller state contract。


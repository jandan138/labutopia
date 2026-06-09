# 本机复现记录

本文记录 2026-06-09 在当前机器上已经验证过的 LabUtopia 启动方式。它描述的是“本机可跑通”的状态，不等同于干净机器上的完整安装规范。

## 已验证环境

| 项 | 值 |
| --- | --- |
| 工作目录 | `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia` |
| Conda env | `/cpfs/user/zhuzihou/conda-managed/envs/labutopia-py311` |
| Python | 3.11.15 |
| Isaac Sim | 5.1 pip installation |
| GPU | NVIDIA GeForce RTX 4090 |
| Driver | 570.153.02 |
| Torch | 2.9.0+cu126 |
| Torchvision | 0.24.0+cu126 |
| NumPy | 1.26.0 |
| H5py | 3.15.1 |

Isaac Sim 5.1 官方 Linux requirements 文档在本次调研时列出的 tested driver 是 `580.65.06`。当前 driver `570.153.02` 低于该版本，因此属于“已完成短流程 smoke 和视频批跑，但长期复杂渲染仍有 driver 风险”的状态。

参考官方文档：

- https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html
- https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html

## 必要环境变量

每次运行 Isaac Sim 前建议显式设置：

```bash
unset OMNI_SERVER
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONUNBUFFERED=1
```

原因：

- `OMNI_SERVER` 之前指向过旧 Isaac/Omniverse 内容，会造成 asset 路径污染。
- `OMNI_KIT_ACCEPT_EULA=YES` 避免 headless 环境下 EULA 阻塞。
- `PYTHONUNBUFFERED=1` 让日志及时落盘，便于判断卡死、crash 和成功状态。

## Python 入口

使用当前 env 的 Python：

```bash
/cpfs/user/zhuzihou/conda-managed/envs/labutopia-py311/bin/python
```

不要混用系统 Python、其他 conda env 或旧 Isaac Lab 的 Python。

## 最小 smoke

本次已经验证过的 smoke config 位于 ignored 临时目录：

```bash
unset OMNI_SERVER
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONUNBUFFERED=1

/cpfs/user/zhuzihou/conda-managed/envs/labutopia-py311/bin/python \
  main.py \
  --config-dir docs/tmp/labutopia_smoke \
  --config-name level1_pick_smoke \
  --headless \
  --no-video
```

已验证结果：

- `Success Rate = 1/1 (100.00%)`
- H5 数据曾写入 `outputs/smoke/collect/2026.06.08/19.07.57_Level1_pick_smoke/dataset/episode_0000.h5`

`docs/tmp/` 和 `outputs/` 都是 ignored 路径，不作为正式仓库内容提交。

## 单任务视频

只录视频、减少数据采集开销时，建议使用 mock collector 的临时 config，并指定视频目录：

```bash
unset OMNI_SERVER
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONUNBUFFERED=1

/cpfs/user/zhuzihou/conda-managed/envs/labutopia-py311/bin/python \
  main.py \
  --config-dir docs/tmp/expert_video_configs/20260609_002039 \
  --config-name level1_pick \
  --headless \
  --video-dir artifacts/videos/manual/level1_pick
```

如果不传 `--video-dir`，视频会跟随 Hydra output/run directory，更难收集和 gitignore 管理。

## 全量视频批跑

本次全量结果使用 29 个临时 config 跑出，每个 config 设置：

- `simulation.max_episodes: 1`
- `collector.type: mock`
- 视频保存开启
- 输出目录落在 `outputs/expert_video_runs/...`
- 视频目录落在 `artifacts/videos/expert_trajectories/...`

最终合并结果：

- `artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.csv`
- `artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.json`

这套批跑过程目前还没有正式脚本，属于本次人工整理出来的流程。后续应该沉淀成：

- `scripts/record_expert_videos.py`
- `scripts/validate_expert_videos.py`

## 旧 Isaac 清理状态

用户确认旧项目不用后，已删除旧目录：

- `/cpfs/user/zhuzihou/isaac-sim-5.0`
- `/cpfs/user/zhuzihou/isaac-sim-5.0.0`
- `/cpfs/user/zhuzihou/IsaacLab`

清理原则是不要让旧 Isaac Sim、旧 Isaac Lab、旧 Omniverse cache 和当前 LabUtopia 运行环境混在一起。


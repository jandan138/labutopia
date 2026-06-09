# Artifacts 和 Git 策略

LabUtopia 的视频、临时 config、Hydra output 和 H5 数据都可能很大，不应该直接提交。仓库里只提交代码、配置、文档和小型验证脚本。

## 应该提交

- `config/*.yaml`
- `controllers/`, `tasks/`, `data_collectors/` 等源码改动
- `requirements.txt` 或后续新增的环境 lock 文件
- `docs/*.md`
- 后续新增的 `scripts/*.py`

## 不应该提交

- `artifacts/videos/`
- `outputs/`
- `docs/tmp/`
- Isaac/Omniverse cache
- H5 dataset
- 批跑日志
- contact sheet 图片

当前 `.gitignore` 已覆盖：

```text
outputs/
docs/tmp/
artifacts/videos/
```

## 本次视频产物

最终视频目录：

```text
artifacts/videos/expert_trajectories/20260609_002039_final/
```

关键文件：

```text
artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.csv
artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.json
```

这些文件用于本机审阅和讨论，不提交进 git。

## 检查命令

确认视频目录被 ignore：

```bash
git check-ignore artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.csv
```

确认临时 config 被 ignore：

```bash
git check-ignore docs/tmp/expert_video_configs/20260609_002039/level1_pick.yaml
```

查看当前工作区：

```bash
git status --short
```

## 清理建议

保留最近一次 final 结果用于讨论，旧的 primary/retry 中间目录可以在确认不需要后删除：

```bash
rm -rf artifacts/videos/expert_trajectories/20260609_002039
rm -rf artifacts/videos/expert_trajectories/20260609_002039_retry
```

不要删除 `20260609_002039_final`，除非已经确认视频不再需要或已经转存到外部 artifact storage。

## 后续规范

建议后续把大文件产物转移到独立 artifact storage，并在 repo 内只保留 manifest：

```text
docs/runs/<date>-expert-videos.md
artifacts_manifest/<run_id>.json
```

manifest 应包含 config name、video relative path、hash、frame count、resolution、success status、QA verdict 和 log 摘要。


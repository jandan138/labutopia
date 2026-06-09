# LabUtopia 运行文档索引

本目录记录 LabUtopia 在当前机器上跑 expert trajectory、录制视频、排查环境问题和沉淀流程规范的结论。它不是论文说明文档，也不保存大文件产物。

## 当前结论

2026-06-09 的完整视频批跑结果：

| 项 | 结果 |
| --- | --- |
| 主配置数量 | 29 |
| 注册 controller/expert 类型 | 21 |
| 视频文件 | 29/29 可读 |
| expert 成功轨迹 | 28/29 |
| 非成功但有视频 | `level4_CleanBeaker7Policy` |
| 视频目录 | `artifacts/videos/expert_trajectories/20260609_002039_final/` |
| 汇总文件 | `artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.csv` |

这次结果应该表述为：**29 个配置都有视频证据，28 个配置完成 expert 成功轨迹，1 个配置是 video-only failure trace**。不要写成 29/29 expert 成功。

## 文档结构

- [reproduction.md](reproduction.md): 当前机器的环境、启动命令、必要环境变量和最小复现方式。
- [expert-video-runbook.md](expert-video-runbook.md): 如何只跑 expert trajectory 并录视频，不做正式数据采集。
- [task-config-matrix.md](task-config-matrix.md): 29 个 config、task、controller 和本次视频状态矩阵。
- [environment-troubleshooting.md](environment-troubleshooting.md): Isaac Sim、driver、cache、Hydra、import、headless/video 的踩坑记录。
- [artifacts-and-git-policy.md](artifacts-and-git-policy.md): 哪些东西应该提交，哪些必须保持 gitignored。
- [runs/2026-06-09-expert-videos.md](runs/2026-06-09-expert-videos.md): 本次多角度审阅和视频批跑记录。

## 状态定义

| 状态 | 含义 |
| --- | --- |
| `ok` | 进程退出码为 0，日志中出现成功轨迹，视频可读。 |
| `video_only` | 视频存在且可读，但没有成功完成 expert 任务，不能作为成功轨迹。 |
| `WARN` | 成功完成，但视频或日志存在展示质量风险，例如黑区、相机遮挡、低分辨率、材质缺失。 |

## 规范性评价

当前项目已经可以在本机跑起来，并且可以批量产出 expert 视频；但流程还没有达到“长期可复现、别人一键跑”的规范程度。

主要缺口：

- 缺少正式的 `scripts/record_expert_videos.py` 批跑入口。
- 缺少正式的 `scripts/validate_expert_videos.py` 视频验证入口。
- 环境还没有 lock file 或容器镜像描述，当前 driver 低于 Isaac Sim 5.1 文档测试版本。
- `level4_CleanBeaker7Policy` 的 controller/state 接口仍有 bug。
- `main.py` 顶层生命周期、视频 writer 和 mock collector 语义还需要工程化整理。


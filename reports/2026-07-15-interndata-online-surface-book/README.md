# 把粒子变成水面 · LabUtopia online surface book

面向有一点 Games101 基础的读者，系统讲解 LabUtopia 的 InternData-inspired **online liquid surface reconstruction**。

页面已加入 2026-07-15 Isaac Sim 5.1 最终验收视频与产品口径：3594/3600 粒子进入目标杯，5 个桌面飞溅，0 个落到桌下；任务和专家 H5 验收通过，严格零飞溅诊断保留为 false。

## GitHub Pages

https://jandan138.github.io/labutopia/reports/2026-07-15-interndata-online-surface-book/

（与液体周报同一套 Pages 托管：`main` 分支仓库根目录。）

## 本地打开

```bash
python3 -m http.server 8765 --directory .
```

## 资料口径

公开论文 / PhysX docs 提供概念与能力边界；LabUtopia `docs/runs/*` 与源码提供本地 contract。灵感 ≠ runtime dependency。

# LabUtopia Interactive Book

这是一份多章节 HTML 教程，面向已经有一点 RL、Isaac Sim 和 USD 资产基础的读者，目标是把 LabUtopia 项目从论文概念、runtime、task/controller、data/policy、assets 到 EBench 资产复用判断讲清楚。

- 章节数：55
- 入口：`learn/index.html`
- 目录源：`learn/content.js`
- 样式：`learn/assets/css/book.css`
- 导航与搜索：`learn/assets/js/book.js`
- 交互控件：`learn/assets/js/widgets/book-widgets.js`
- 校验：`python3 learn/validate.py`
- 视觉审查：先启动 `python3 -m http.server 8099 --bind 127.0.0.1`，临时安装 `npm install --no-save @playwright/test` 后运行 `npx playwright test learn/visual_audit.spec.js --reporter=line`

内容组织参考了 `/cpfs/shared/simulation/zhuzihou/dev/EBench/learn` 的 book scaffold，但章节事实和写作结构重新围绕 LabUtopia、本地代码和外部资料整理。

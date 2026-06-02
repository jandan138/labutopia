# LabUtopia Learn Design

目标：把 `learn/` 从单页说明改成多章节互动书，既能解释 LabUtopia 项目，也能系统比较 LabUtopia assets 与 EBench assets。

结构：
- `content.js` 是目录单一来源。
- 每个章节是完整 HTML，可直接由 GitHub Pages 服务。
- `book.js` 负责 sidebar、search、theme、progress、pager 和右侧目录。
- `book-widgets.js` 提供 runtime loop、task levels、asset map、dataset flow、reuse matrix、version bridge 等交互控件。
- `validate.py` 检查章节数量、关键事实、来源链接、资产对比章节和 widget 覆盖。

写作口径：
- 中文解释，English terms 保留。
- 公开资料与本地代码事实分开陈述。
- 资产复用结论：LabUtopia assets 不能直接复用到 EBench；可经过 conversion workflow、task/eval contract 重建和 visual QA 迁移。

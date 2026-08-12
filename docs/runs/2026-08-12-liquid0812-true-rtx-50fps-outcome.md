# liquid_0812 真 RTX 50 FPS 实验结论

日期：2026-08-12

## 一句话结论

已经实现并实测了“每秒真正完成约 50 张新的 256×256 RTX 图、图像保持在 GPU、物理按 30 Hz 更新”的链路。速度优先玻璃档在 headless 和 offscreen viewport 中都连续 3/3 次超过 50 FPS；原始玻璃画质档只有 1/3 次超过 50 FPS，不能宣称稳定达标。

这只证明出图性能链路可行。当前 USD 的液体仍会穿漏，且中后段构图看不清倒液，因此完整产品场景仍是 NO-GO。

## 这里的 50 FPS 到底是什么

- 每次计数都来自目标 RTX render product 的 `NEW_FRAME` 完成事件。
- 每张图必须是新的、严格递增的渲染帧号。
- 图像通过 `LdrColor(device="cuda", do_array_copy=False)` 留在 GPU，并进入三槽 CUDA ring buffer 的模拟消费者。
- 计时路径没有 CPU RGB 读回；视频编码和 PNG 保存放在计时结束后。
- 物理是 30 Hz，渲染是 50 Hz，所以部分相邻 RTX 图共享同一个物理状态。这不是重复旧图片，而是对同一物理状态重新完成一张 RTX 图。

## 三次完整重复结果

每次包含 953 个物理状态和 1589 张 RTX 图，单相机 256×256，RTX RayTracedLighting。

| 路径 | 画质档 | RTX FPS（3 次） | 平均 | 物理 Hz 平均 | 50 FPS 通过率 |
|---|---|---:|---:|---:|---:|
| Headless render product | 原始玻璃 | 47.65 / 48.92 / 50.36 | 48.98 | 29.37 | 1/3 |
| Headless render product | 速度优先玻璃 | 53.97 / 55.68 / 50.26 | 53.30 | 31.97 | 3/3 |
| Offscreen viewport | 原始玻璃 | 49.55 / 48.57 / 51.06 | 49.73 | 29.82 | 1/3 |
| Offscreen viewport | 速度优先玻璃 | 52.55 / 52.40 / 53.04 | 52.66 | 31.58 | 3/3 |

速度优先玻璃保留 DLSS、反射、阴影和透明材质，把间接漫反射关掉，并把最大折射次数从 6 降到 2。降到 1 次会让透明杯壁基本消失，因此没有采用。

矩阵总状态是 `measured_no_go`，原因是总门要求四个 cell 全部通过，而两个原始玻璃 cell 没有稳定达到 50；推荐档本身两种路径均为 3/3 通过。

## 尚未通过的质量门

- 数值检查：完整序列从物理状态 423 开始出现粒子穿到桌面下方；所有 12 次矩阵运行的稳定性门都失败。
- 独立画面复核：FAIL。约在 RTX render 759 开始，源烧杯移出上边界，桌面留下扁平液体圆盘，无法看出连续倾倒和接液。
- 所以不能把 53 FPS 表述为“高质量不漏液的完整产品方案”；准确表述应是“异步 RTX GPU 出图链路达到 50 FPS，液体物理和动作构图待修”。

## 证据与复现入口

- 实现：`tools/labutopia_fluid/run_isaac41_liquid0812_async_rtx_benchmark.py`
- 完整矩阵：`outputs/liquid0812_async_rtx_matrix_glass_v2/matrix.json`
- 独立视觉复核：`outputs/liquid0812_async_rtx_matrix_glass_v2/visual_review.json`
- 完整 headless 视频：`outputs/liquid0812_full_50fps_v1/headless/artifacts/liquid0812_headless_product_full_50fps.mp4`，1589 帧、50 FPS、31.78 秒；计时吞吐 52.22 FPS。
- 完整 offscreen viewport 视频：`outputs/liquid0812_full_50fps_v1/offscreen/artifacts/liquid0812_offscreen_viewport_full_50fps.mp4`，1589 帧、50 FPS、31.78 秒；计时吞吐 51.85 FPS。
- 面试复盘页源码：`reports/2026-08-12-labutopia-rtx50-field-notes/index.html`。页面内嵌了上述两条完整视频的发布副本，并显式保留物理质量失败边界。
- 每次运行均绑定 matched effective-runtime v2 receipt：Python 3.10.20、Isaac Sim 4.1.0.0、Kit NumPy 1.26.0、USD 0.22.11。
- 12/12 个父 manifest 均为 `passed`，child return code 为 0，且各次 source-before/source-after 完全一致。

完整视频并不是“计时过程中实时 H.264 编码 50 FPS”。正式窗口里，每张完成图先进入 CUDA 全帧库；窗口结束后才统一读回、编码并用 ffprobe 验证帧数、帧率、分辨率和时长。因此视频可以按 50 FPS 交付或供后续评测系统读取，但编码性能不能冒充在线吞吐。

## 下一步

先修液体碰撞/约束，使粒子不穿桌、不提前脱离源杯；同时把相机略拉远并上移。修好后必须在同一正式运行合同下重新跑完整 3 次矩阵，不能沿用本轮性能通过来替代质量验收。

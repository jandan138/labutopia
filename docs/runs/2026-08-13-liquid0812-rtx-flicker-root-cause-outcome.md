# liquid_0812 RTX 闪烁根因复测

日期：2026-08-13

## 结论

本轮没有发布替换视频。源杯的 PhysX、USD 根节点和可见 mesh 数值姿态已经同步，但完整视频仍出现少量尖刺和幽灵杯。新的隔离矩阵排除了 H.264、网页播放器、CUDA 零拷贝生命周期、CPU/GPU RGB copy 选择和 Replicator `LdrColor` annotator 是主因。

固定 physics state 448 连续渲染 96 张时，world transform 保持完全一致；managed CUDA 路线的变化比例 P95 为 0.117%，但第 0→1 张达到 4.64%，随后稳定。原生 Viewport byte capture 也出现相同的“前 1–3 张变化、之后收敛”。因此当前根因收敛为：RTX 透明/反射画面在场景状态切换后需要多帧收敛，而固定丢弃一张或三张不能保证整条轨迹稳定。

## 已排除方向

| 路线 | 忙载探索 RTX FPS | 闪烁门 |
| --- | ---: | --- |
| zero-copy async | 61.1119 | FAIL |
| zero-copy blocking | 61.9102 | FAIL |
| managed CUDA copy | 61.1992 | FAIL |
| CPU copy reference | 58.8057 | FAIL |
| managed step-and-wait | 4.2359 | FAIL |
| native Viewport fixed-state reference | 23.9769 | 初始收敛帧 FAIL |

这些运行都使用 sealed Isaac Sim 4.1 effective-runtime v2 child，但因共享 GPU 上存在其他 Isaac 工作负载，证据类为 `non_authoritative_busy_gpu_exploration`。它们只支持根因隔离，不支持正式 FPS 资格。

## 完整稳定候选

`native AA + step-wait + 每状态丢 1 张` 生成了 953 帧、30 FPS、31.7667 秒的视频，忙载实测完成帧吞吐为 3.6745 FPS。密集接触表仍发现少量尖刺/幽灵杯，因此没有复制到报告媒体，也没有触发页面视频 promotion。

该候选的液体质量仍是独立 NO-GO：最终 548 粒子中，目标杯 505、桌面 42、桌下 1；它不能证明不撒不漏。

## 下一道门

下一实现应让每个物理状态至少产生两张可比较的新 RTX 图：第一张作为收敛探针，第二张与第一张通过同状态差分后才允许写入交付序列。不能再用固定丢弃 N 张代替实际收敛判定。只有全 953 状态通过、完整视频视觉复核通过，才允许更新报告页面。

原始 USD、EOS 仓库和 canonical Isaac 4.1 环境均未修改；所有诊断可见性改动只存在于匿名 session layer。

# Expert Oracle Score Plan

Date: 2026-07-02

## 目的

当前 LabUtopia / EBench consumer smoke 已经证明 AAN package 能进入 runtime，完成
reset / step / render / metric / logging，并写出 `result_info.json`。但这些 smoke
run 使用的是 EBench / GenManip eval client 的普通 action path，不是 LabUtopia expert
controller，也不是训练好的 policy，所以 `score=0.0` 不能说明 expert 失败。

`Expert Oracle Score` 阶段要补的是另一层证据：如果把“专家答案”接到同一套 EBench
metric 下，评分器应该能给出高分。它用来证明 metric / layout / action replay 是可信的，
再往后才进入真实 policy 或 official leaderboard 评测。

一句话给 PM：现在已经证明“考场能开、卷子能交”；`Expert Oracle Score` 要证明“标准答案
放进去能拿分”。这和真实模型成绩仍然是两件事。

## 命名和位置

推荐工程名：

```text
Stage 4c: Expert Oracle Score / Score Calibration
```

它位于 Stage 4b consumer smoke 之后、真实 policy score 之前：

```text
4b Consumer Smoke -> 4c Expert Oracle Score -> Semantic Evaluator / Policy Score -> Official Leaderboard
```

这里的 “4c” 不重排现有 6 个 AAN consumer acceptance stages。它表示：Stage 4b 已经证明
任务链路能跑，4c 再校准“标准答案是否能在同一 metric 下得分”。

## 证据层级

| 层级 | 回答的问题 | 当前状态 | 能不能当作模型成绩 |
|---|---|---|---|
| Runtime smoke | 任务链路能不能 reset、step、出图、写 metric？ | 已通过 | 不能 |
| Franka expert oracle | LabUtopia 原生 Franka expert 在 EBench metric 下能不能得分？ | 规划中 | 不能，属于 oracle / 标准答案验证 |
| Lift2 oracle / retarget | 官方 Lift2/R5a 口径下，专家策略或 retarget 后动作能不能完成任务？ | 规划中 | 不能，属于 oracle / 上限验证 |
| Real policy score | 真实 baseline / model 输出 action 后能得几分？ | 后续 | 可以作为 policy 质量证据，是否 official 另看运行入口 |

## 为什么要分两步

LabUtopia 桌面 expert 主线是 Franka。EBench official-style Lift2 lane 使用
`manip/lift2/R5a` 和 16D action contract。Franka expert 的轨迹不能直接等价于 Lift2
policy action。

因此 `Expert Oracle Score` 先分成两步：

0. **Evidence freeze**：先锁定 lane、config、asset wrapper、run id 规则和 hash，避免
   把历史 `lift2_candidate`、AAN-11 lane、Franka POC 的证据混用。
1. **Franka native expert under EBench metric**：先验证评分器、任务布局和
   `RevoluteJoint` / object-state metric 是对的。这里用 Franka 是合理的，因为它最接近
   LabUtopia 原生 expert。
2. **Lift2 oracle / retarget**：再把专家意图迁移到 Lift2/R5a 口径，验证官方机器人
   embodiment 也能完成同一任务。

## 子阶段

### EOS-0: Evidence Freeze

目标：冻结本轮 oracle score 到底跑哪条 lane、哪个 config、哪个 asset wrapper，避免
复用旧 smoke 证据。

PASS 硬门：

- 记录 `task_name`、`usd_name`、robot type、action contract、metric config、config SHA；
- AAN-11 lane 必须指向
  `scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene`；
- Franka POC 和 Lift2 candidate 不能共用 action log；
- `run_id` 命名必须包含 `expert_oracle` 或 `lift2_oracle`，不能复用 smoke run id；
- no-local-repair、assets root、AAN wrapper 指向正确 package；
- runtime bootstrap 继续使用 `aan_runtime_environment_bootstrap.md`。

### EOS-1: Metric Parity Preflight

目标：确认 EBench metric 读的是正确任务状态，而不是 LabUtopia controller 的内部
`done`。

首个任务：

```text
task=level1_open_door
native_config=config/level1_open_door.yaml
franka_poc=ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
lift2_candidate=ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml
metric=check_joint_angle(obj_DryingBox_01, RevoluteJoint, 30-120 deg)
```

PASS 硬门：

- reset 后能读到 `obj_DryingBox_01`；
- metric 读取的是门的 `RevoluteJoint`，不是按钮 `PrismaticJoint`；
- metric 来源是 GenManip / EBench step output；
- 不把 LabUtopia expert controller 的 `done` 直接当 score。当前 LabUtopia open
  controller 的成功条件偏 handle 位移 / gripper 距离，而 EBench metric 是
  `check_joint_angle(obj_DryingBox_01, RevoluteJoint, 30-120 deg)`；
- 记录初始门角、结束门角、metric score、success_rate、result_info 路径。

### EOS-2: Franka Native Expert Oracle Replay

目标：在 Franka POC lane 中运行或 replay LabUtopia native expert，让 EBench metric 给
专家答案打分。

可接受实现方式：

- 在线运行 LabUtopia scripted expert controller，但 score 只读 EBench metric；
- replay 已记录的 Franka expert action / joint trajectory，但 score 只读 EBench metric。

PASS 硬门：

- 使用 `franka_poc` 或等价 Franka task config；
- action 来源标记为 `labutopia_native_expert_oracle`，不能伪装成 learned policy；
- EBench metric score 达到任务阈值，例如单 episode `score=1.0` 或 `success_rate=1.0`；
- 产出 `result_info.json`、action log、关键帧 render / video、metric trace；
- 对比 LabUtopia native expert success 和 EBench metric success，并解释任何差异。

允许说法：

```text
Franka expert oracle 在 EBench metric 下能得分，说明评分器和任务布局能识别专家完成状态。
```

禁止说法：

```text
真实 policy 已经会做任务。
Lift2 official baseline 已经成功。
official leaderboard score 已经完成。
```

### EOS-3: Lift2 Oracle / Retarget

目标：把 expert 意图迁移到 Lift2/R5a 口径，证明官方机器人 action contract 下也能完成
任务。

可接受实现方式：

- Franka expert end-effector trajectory -> Lift2 IK / retarget -> 16D R5a action；
- 编写 Lift2-specific scripted oracle，但仍走 EBench / GenManip action接口；
- 分阶段 open-door oracle：approach handle、contact / pull、verify joint angle。

PASS 硬门：

- 使用 `lift2_candidate` 或 AAN-11 Lift2 candidate lane；
- action dialect 是 `-a r5a -g lift2` 或等价 16D Lift2 action client；
- 不使用 LabUtopia Franka joint action 直接冒充 Lift2 action；
- EBench metric score 达到任务阈值；
- 记录 retarget / IK 失败率、collision / reachability、joint limit、step count；
- 产出 result_info、action log、metric trace 和 render / video 证据。

允许说法：

```text
Lift2 oracle / retarget 能在本地 EBench metric 下完成该任务，说明官方机器人口径存在可行专家上限。
```

禁止说法：

```text
训练模型已经达到 oracle 水平。
official leaderboard 已经发布成绩。
任意 LabUtopia 任务都已经可由 Lift2 完成。
```

### EOS-4: Real Policy Handoff

目标：在 oracle 证明 metric 和 embodiment 可完成后，再接真实 baseline / model policy。

PASS 硬门：

- policy 输出标准 EBench action，而不是调用 expert controller；
- run_id、policy checkpoint、task config、result_info、score 和 success_rate 全部记录；
- 与 EOS-2 / EOS-3 的 oracle score 分开汇报。

## 失败归类

| 失败现象 | 归类 | 处理方式 |
|---|---|---|
| Franka expert 在 LabUtopia 内成功，但 EBench metric 不得分 | metric / state mapping 问题 | 检查 prim path、joint name、角度单位、success threshold。 |
| Franka expert 在 EBench lane 中 reach 不到物体 | layout / robot pose 问题 | 对齐 native layout、robot pose、asset scale、camera / table frame。 |
| Lift2 retarget IK 失败 | embodiment retarget 问题 | 检查 reachability、joint limits、base pose、handle contact strategy。 |
| Lift2 oracle 得分，真实 policy 仍 0 分 | policy quality 问题 | 不改资产结论，单独推进 model / policy。 |
| oracle 得分但 render / material 仍有差异 | visual parity follow-up | 不把 oracle score 升级成 visual/material parity。 |

## Evidence Manifest 建议字段

```json
{
  "stage": "expert_oracle_score",
  "substage": "franka_native_expert_replay | lift2_oracle_retarget",
  "evidence_freeze": {
    "task_name": "",
    "usd_name": "",
    "config_sha256": "",
    "asset_wrapper_sha256": "",
    "run_id_policy": "must include expert_oracle or lift2_oracle"
  },
  "status": "PASS | FAIL | BLOCKED | WARN | NOT_RUN",
  "run_id": "example_run_id",
  "task_name": "ebench/labutopia_lab_poc/franka_poc/level1_open_door",
  "robot": "manip/franka/panda_hand | manip/lift2/R5a",
  "oracle_source": "labutopia_native_expert_controller | expert_trajectory_replay | lift2_scripted_oracle | retargeted_expert",
  "policy_claim_allowed": false,
  "official_score_claim_allowed": false,
  "metric_source": "genmanip_ebench_metric_output",
  "metric_target": {
    "object_uid": "obj_DryingBox_01",
    "joint_name": "RevoluteJoint",
    "angle_deg_range": [30, 120]
  },
  "result_info_path": "",
  "score": null,
  "success_rate": null,
  "action_log_path": "",
  "render_or_video_path": "",
  "allowed_claims": [],
  "forbidden_claims": []
}
```

## 推荐推进顺序

1. 先做 `level1_open_door` 的 EOS-1 / EOS-2，因为它已经有 Franka POC 和 Lift2
   candidate 两条 lane，metric 也最明确。
2. 再做 EOS-3，把 open-door oracle 迁移到 Lift2/R5a。
3. EOS-2 / EOS-3 都通过后，再复制到 `level1_pick`、`level1_place`。
4. 最后再接真实 baseline / model policy，单独汇报 policy score。

## 当前状态

```text
Expert Oracle Score status=PLANNED
runtime smoke score=0.0 is not an expert failure
Franka expert oracle score=NOT_RUN
Lift2 oracle / retarget score=NOT_RUN
real policy score=NOT_RUN
```

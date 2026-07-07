# EOS2 S0 Deterministic Franka Native Replay Source Design

Date: 2026-07-06

## Purpose

S0 当前已经有 exporter / freezer / score-capable runner 的 code-ready 证据，但还没有真实
EBench-executable expert action source。A 路线的目标是补出这一份 source：从 LabUtopia
`level1_open_door` 的 Franka/native expert controller 捕获实际送给 Isaac 的 `ArticulationAction`，
转换成 EBench `joint_position` replay JSONL，并用 freezer 冻结成 `action_source_manifest.json`。

给 PM 的一句话：现在不是继续看视频说“专家成功”，而是把专家每一步实际给机器人的关节目标记录成
EBench 能重放的标准答案文件。

## Current State

LabUtopia 原生 open-door expert 走这条路径：

```text
main.py
  -> task.step()
  -> OpenTaskController.step(state)
  -> OpenController.forward(...)
  -> ArticulationAction(joint_positions=...)
  -> robot.get_articulation_controller().apply_action(action)
```

现有视频证据和 H5 dataset 不够：

- `artifacts/videos/expert_trajectories/...` 只能证明看起来执行过，不是 EBench replay input。
- `DataCollector` 的 H5 `actions` 是由 `agent_pose[1:] + final_joint_positions` 推导的下一帧状态，不是
  controller 原始输出。
- `ActionStateDataCollector` 支持显式 action，但 `level1_open_door` 当前并没有把 `ArticulationAction`
  传进去。
- `ArticulationAction.joint_positions` 可能包含 `None`，表示该 joint 不下新目标；EBench replay 需要完整数值向量。

因此 A 路线不能直接从旧视频或旧 dataset 转换，必须新增一个旁路 action capture / normalize / export
合同。

## Recommended Design

### Component 1: Action Normalizer

新增 Isaac-free 工具模块，负责把 controller 输出整理为完整 EBench action vector。

Input:

- `ArticulationAction`-like object with `joint_positions`
- current observed `state["joint_positions"]`
- expected action dimension, initially `9` for `manip/franka/panda_hand`

Rules:

- If `joint_positions[i]` is numeric, use it.
- If `joint_positions[i] is None`, fill with current observed joint position at the same index.
- Reject missing `joint_positions`, non-numeric values, dimension mismatch, and boolean values.
- Output full absolute `joint_position` vector.

Rationale: LabUtopia controllers use `None` as "hold this joint"; EBench replay JSONL should be explicit and deterministic.

### Component 2: Replay JSONL Logger

Add an optional logger that writes each applied action to JSONL without changing controller behavior.

Each line:

```json
{
  "step_index": 0,
  "worker_id": "0",
  "action": {
    "action": [0.0],
    "control_type": "joint_position",
    "is_rel": false,
    "base_motion": [0.0, 0.0, 0.0],
    "base_is_rel": true
  },
  "source": {
    "kind": "labutopia_native_articulation_action",
    "source_role": "candidate_expert_action_source",
    "controller_type": "open",
    "task_config": "config/level1_open_door.yaml",
    "normalization": "none_filled_from_observed_joint_positions"
  }
}
```

Runtime integration should be opt-in, for example:

```bash
python main.py \
  --config-name level1_open_door \
  --headless --no-video \
  --ebench-action-log-dir <output_dir> \
  --ebench-action-expected-dim 9 \
  --ebench-action-worker-id 0
```

`main.py` should call the logger after `task_controller.step(state)` returns a non-null action and before or after
`apply_action(action)`. The logger must not affect simulation control flow.

### Component 3: Candidate Manifest

The logger writes a candidate manifest next to JSONL:

- task config path and sha256
- command
- expected action dim
- worker id
- control type
- source kind
- action count
- first/last step
- action source sha256
- success flag observed from LabUtopia controller
- explicit claim boundary

This manifest is still candidate evidence. It becomes S0 frozen evidence only after `score_oracle_action_source_freezer.py`
accepts the JSONL and writes `action_source_manifest.json`.

### Component 4: S0 Freeze + S1 Preflight

After a successful LabUtopia run:

1. Run the S0 freezer on the logged JSONL.
2. Register the freezer output manifest in LabUtopia evidence.
3. Only then prepare S1 formal score-chain smoke preflight.

S1 still requires a separate release review with the EBench config hash, action source hash, score runner command,
conda/env, output directory, `result_info.json`, `action_log.jsonl`, `metric_trace.jsonl`, and render/readback expectations.

## Alternatives Considered

### Alternative A: Convert Existing H5 Dataset

Rejected as the main S0 source. The H5 `actions` field is derived from pose sequence rather than the exact
controller `ArticulationAction`, and old runs do not contain the S0 provenance, reset contract, dt, source hash, or
EBench action dialect manifest.

### Alternative B: Export Existing Planner Trajectories

Useful for diagnostics, already covered by the S0 exporter. Rejected as the real source because current planner
summaries are diagnostic-only or blocked, and source eligibility audit found no eligible expert source.

### Alternative C: Native Controller Research First

Keep as route B, not first. It is useful only if deterministic Franka/native replay cannot become EBench-executable,
or if fallback score route later hits a formal stop line. It must remain no-score until a distinct controller contract
and readback harness pass review.

## Stop Lines

- If LabUtopia cannot log controller `ArticulationAction` without changing behavior, stop and fix logging isolation.
- If logged actions cannot be normalized to full numeric 9D `joint_position`, stop before freezer.
- If the LabUtopia run does not reach native success, keep the JSONL as diagnostic only; do not freeze as real expert source.
- If freezer rejects the JSONL, stop before S1.
- If frozen JSONL exists but S1 preflight cannot lock command/env/result artifact expectations, do not run live.

## Non-Claims

This design does not claim:

- `Expert Oracle Score` complete
- Franka/native expert scored by EBench
- Lift2 official baseline solved
- policy or model score
- official benchmark reproduction
- leaderboard readiness
- project no-go

The only claim after implementing the logger and passing unit tests is: LabUtopia can produce a candidate EBench replay
action source from native controller outputs. Formal S0 completion requires a successful run and freezer output.

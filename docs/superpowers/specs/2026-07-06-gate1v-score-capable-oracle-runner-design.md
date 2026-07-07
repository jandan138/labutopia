# Gate1V-2c Score-Capable Oracle Runner Design

Date: 2026-07-06

## Purpose

`Gate1V-2c Score Runner Build Plan` 的目标不是继续试 policy，也不是启动
Isaac live，而是先把“专家答案如何进入正式 EBench evaluator 并落成正式 score artifact”定义清楚。

给 PM 的一句话：前面已经证明“考场在哪里”和“判卷器大概怎么写分”，但还没有一个合格的“标准答案投递器”。
Gate1V-2c 要做的就是这个投递器的合同；没有它，就不能把任何诊断图、diagnostic metric 或历史
`expert_oracle` 命名目录说成 `Expert Oracle Score`。

## Current Score Path Audit

当前 GenManip / EBench 侧有正式落分链路，但它不是 oracle runner：

- `genmanip/core/evaluator/env.py`
  - `step()` 中调用 `scene.metric_manager.step(scene)` 得到 step-level metric。
  - episode 结束后，`post_episode_process()` 调用 `scene.metric_manager.calc_overall_score()`，并把
    `metric_score` 放进 recorder finalize payload。
- `genmanip/core/evaluator/isaac_worker_pool.py`
  - `step()` / `step_chunk()` 发现 done 后不会立即返回最终 score，而是先返回 `reset_pending`。
  - `_handle_done()` 在后台调用 worker `post_episode_process()`，再用 `resolve_episode_score()` 决定 episode score。
  - `progress_manager.record_result()` 负责登记 episode result；最后 `_save_final_result()` 写最终结果。
- `genmanip/core/evaluator/progress_manager.py`
  - 如果没有 async finalize，`_write_minimal_result_info()` 也会写 `result_info.json`，但
    `log_info.metric_score` 可能是空数组。
- `genmanip_client/eval_client.py`
  - `_resolve_pending_resets()` 会轮询 `/reset_result`，直到后台 reset / finalization 完成。
  - `_record_episode_results()` 只在 response 里真的带 `episode_result` 时写 client 侧 episode result。

结论：runner 不能把 `done_info.info`、单步 `metric`、diagnostic summary 或 `score_claim_allowed=false`
的 probe 输出当成正式 benchmark score。runner 必须等 pending reset / episode finalization 完成，并校验
正式 `result_info.json` 和同一次 action/metric trace。

## Contract

未来实现建议放在 GenManip / EBench runner 层，而不是 LabUtopia 文档仓库里直接伪造结果：

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/
  standalone_tools/labutopia_poc/score_capable_oracle_runner.py
  tests/labutopia_poc/test_score_capable_oracle_runner.py
```

### Inputs

runner 必须显式声明：

- `base_url`
- `config_path`
- `run_id`
- `worker_id`
- `output_dir`
- `action_source`
- `action_source_kind`: `replay_jsonl` 或 `deterministic_oracle_route`
- `action_dialect`: `control_type`、action dimension、units、frames、base channel、gripper convention
- `max_steps`
- `step_chunk_size`
- `conda_env`

### Action Source

最小 `replay_jsonl` action source 每行必须是一个可直接送进 EBench `step` / `step_chunk` 的 payload：

```json
{
  "step_index": 0,
  "worker_id": "0",
  "action": {
    "action": [0.0, 0.0, 0.0],
    "control_type": "joint_position",
    "is_rel": false,
    "base_motion": [0.0, 0.0, 0.0],
    "base_is_rel": true
  },
  "source": {
    "kind": "replay_jsonl",
    "generator": "frozen_oracle_action_stream",
    "sha256": "<sha256>"
  }
}
```

真实文件里 action dimension 必须匹配对应 robot/task。Franka route 和 Lift2/R5a route 不能混用。

### Required Output Artifacts

同一次 run 必须产出：

- `summary.json`
- `action_log.jsonl`
- `metric_trace.jsonl`
- `episode_result.json`
- authoritative `result_info.json`
- render/readback evidence path or explicit no-render waiver
- `command.txt`
- `environment.json`

`summary.json` 里的 `score_claim_allowed` 只有在这些条件都满足时才能为 `true`：

- `result_info.json` 存在。
- `score` 是 number。
- `success_rate` 是 number。
- `log_info.metric_score` 非空，或者 manifest 明确给出 reviewed waiver。
- `episode_result` 来自 evaluator finalization，不是 runner 自己推断。
- `action_log.jsonl` 覆盖所有实际执行 action。
- `metric_trace.jsonl` 覆盖 reset、每个 step/chunk、done/finalization。

当前默认策略：没有 reviewed waiver 时，空 `metric_score=[]` 只能判 `score_artifact_incomplete`，不能 claim
`Expert Oracle Score`。

## Stop Lines

### Stage 2: Formal Scoring Chain

如果 runner 无法稳定产出 authoritative `result_info.json`、`episode_result` 和 trace，则停止。
这说明问题在 runner / evaluator finalization / job lifecycle，不是 expert policy。

### Stage 3: Task Semantics

如果专家动作看起来完成任务，但正式 metric / reward / success 不涨，则停止调 action，先审计 task contract：
metric object、joint path、success range、episode state、layout 和 coordinate frame。

### Stage 4: Robot Control Mouth

如果 Franka/native expert 能在 EBench metric 下得分，但 Lift2 / official robot 口径不能得分，则不要说资产失败。
问题应转到 robot-control workstream：action space、IK、joint mapping、controller endpoint 或 retarget。

## Fake-Client Test Plan

实现前先写 tests，至少覆盖：

- `test_runner_requires_result_info_with_score_and_success_rate`
- `test_runner_rejects_diagnostic_only_metric_without_episode_result`
- `test_runner_polls_pending_reset_until_episode_result_available`
- `test_runner_writes_action_log_and_metric_trace`
- `test_runner_rejects_empty_metric_score_without_reviewed_waiver`
- `test_runner_rejects_action_dimension_mismatch`
- `test_runner_never_sets_score_claim_allowed_true_on_exception`

这些测试不需要 Isaac。它们用 fake client / fake filesystem 证明 runner 的验收口径正确。

## Non-Claims

Gate1V-2c planning / contract 本身不能 claim：

- `Expert Oracle Score` complete
- model score
- policy score
- official Lift2 baseline solved
- official benchmark reproduction
- leaderboard result
- LabUtopia-to-EBench project no-go

Gate1V-2c 通过后，最多只代表“可以进入一次 bounded fallback score live release review”。真正的
`Expert Oracle Score` 必须等那次 live 产出 score / reward / success、action log、metric trace、
`result_info.json` 和 render/readback evidence。

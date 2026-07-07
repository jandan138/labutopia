# EOS2 Gate1V Post-F Route Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop blind retries after F2a, choose the next score-eligible route, and define the earliest pass/no-go points for LabUtopia-to-EBench Expert Oracle Score.

**Architecture:** Gate1V is a zero-live route re-branch. It freezes the closed F-stage lower-level official/OpenPI action branch, then separates three lanes: `robot/task fallback oracle`, `asset/task no-score hardening`, and `native-controller research`. Live runs are only released after a lane has zero-live contract evidence and a named claim boundary.

**Tech Stack:** LabUtopia docs, EBench / GenManip evidence manifests, EOS plan docs, JSON manifest validation with `python -m json.tool`, Markdown validation with `git diff --check`.

---

## PM Summary

F2/F2a 已经回答了一个具体问题：当前 `Lift2 official/OpenPI lower-level action path` 没有隐藏的新动作入口。F2 证明 target 确实写到 controller，runtime max effort 也提高了，但右臂只动了约 `0.11047rad`，没达到预注册的 `>=0.18rad`，最终误差约 `0.08953rad`，也没达到 `<=0.02rad`。F2a 进一步证明，EOS official runner / GenManip runtime 仍落到同一个 `joint_position -> set_joint_position_targets -> world.step` 语义。

所以现在不能继续 F2b/F2c/F2d，也不能靠加 hold、调 gain、换 seed、扫 offset 继续尝试。下一步进入 Gate1V：先决定新的路线，再释放 live。

## 预计到哪一步能弄好

最近的“弄好”不是 Lift2 直接开门满分，而是两步走。第一步先完成 `Gate1V-2a Fallback Oracle Freeze`，这个节点如果通过，只能说：

```text
EBench Franka config、score-capable oracle runner、expert action stream / deterministic route 和 artifact contract 都已冻结，可以释放一次 bounded fallback score live。
```

第二步再跑这一次 bounded live。只有这次 live 产出完整 score artifact，才可以说：

```text
EBench metric / reward / success 能给一套 expert/oracle answer 正确计分。
```

这就是最小 `Expert Oracle Score` 评分链闭环。它证明“考场和判卷器能给标准答案打分”，但还不能说 official Lift2 baseline、real policy 或 leaderboard 已经完成。

完整对外可说 `Expert Oracle Score` 闭环，需要再到 live release 后的 score artifact：

```text
score / reward / success
action log
metric trace
result_info.json
render/readback evidence
```

如果目标升级为 `Lift2 official` 或 native Lift2 control，那要走 `Gate1V-3 Native Control Contract Research`，先定义新的 `native_drive_target` / native controller contract，再证明它不是当前 failed joint-position path 的换名版本。

## 2026-07-06 当前判断

`Gate1V-2 Fallback Oracle Preflight` 已完成 zero-live 审计，结论是 no-live blocked，不是 pass，也不是项目失败。它已经确认最近 fallback route 是 Franka POC `level1_open_door`，EBench 判卷器会读 `obj_DryingBox_01/RevoluteJoint`，成功范围是 `30-120deg`，`succ_cnts=59`。

当前不能 live 的原因很具体：

- EBench Franka config 还只在外部 GenManip dirty worktree 中，没有冻结成本仓库 artifact。
- LabUtopia native expert 目前只有 video/log success，没有 frozen EBench action stream。
- 当前候选 runner 是 diagnostic/no-score 证据，不能冒充 `Expert Oracle Score`。

所以预计“能弄好”的最近节点变成 `Gate1V-2a`。它不是跑仿真，而是冻结四件事：config、score-capable runner、expert action stream / deterministic route、同一次 live 必须产出的 artifacts。只有这四件事过审，才允许一次 bounded fallback score live。

`Gate1V-2a` 已执行 zero-live freeze，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2a_fallback_oracle_freeze_20260706.json`。当前结果仍是
no-live blocked：Franka POC `level1_open_door` 的 EBench config 已冻结到本仓库，sha256 为
`e78e5f4b58a39b15bc9146436bf50249b850f71b1171e3f671bbd95e9d58956e`；但 score-capable oracle runner 和
EBench 可执行的 expert action stream / deterministic route 仍未冻结。下一步不是 live，而是
`Gate1V-2b Runner / Action-Source Contract`。

`Gate1V-2b` 已完成 runner/action-source contract 审计，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2b_runner_action_source_contract_20260706.json`。结论仍是
no-live blocked：正式 EBench evaluator 可以写 `result_info.json`，但没有冻结的 score-capable oracle runner
把 expert action 送进去；只读扫描 73 个 Franka open-door `result_info.json` 后，全部是 `score=0.0`、
`success_rate=0`、`metric_score=[]`。因此 fallback score live 不释放。

`Gate1V-2c Score Runner Build Plan` 已新增，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json`，
设计说明是
`docs/superpowers/specs/2026-07-06-gate1v-score-capable-oracle-runner-design.md`。随后 2c runner code checkpoint
也已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_code_checkpoint_20260706.json`。
它仍是 no-live code/test evidence，不是 score pass：它把 GenManip/EBench runner 层的
score-capable oracle runner 做到 fake-client contract 通过。
正式分数只能来自 `post_episode_process -> episode_result -> result_info.json`；runner 必须处理
`reset_pending`，不能把 diagnostic `metric`、`done_info.info`、旧 `native_action_path_runner` summary
或历史 `expert_oracle` 命名目录当成 benchmark score。当前仍缺 frozen EBench-executable expert action source
和 live release review，所以 fallback score live 仍不释放；即使后续 2c 全部通过，也只进入 bounded live
release review，不等于 `Expert Oracle Score` 已完成。

`Gate1V-3 Native Control Contract Research` 也已完成 zero-live audit，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json`。结论不是
native-controller 大方向失败，而是 current-state incomplete/no-live：当前 repo + 外部 GenManip 状态里没有一份
已冻结的、不同于 `16D joint_position -> set_joint_position_targets -> world.step` 的 Lift2/R5a native control
contract。现有 candidate 要么还是同一路线，要么只是 batching、base channel、planner/IK 预处理、diagnostic
hold、max-effort repair 或 no-score diagnostic runner。下一步如走 native lane，必须先写 `native_drive_target`
这类 no-score contract spec + fake-client/readback harness，证明它不是旧 joint-position 路线的换名版本；通过前
不得 release `native_research_live`，更不得 claim `Expert Oracle Score` 或 `Lift2 official baseline`。

## 预计到哪一步判弄不好

Gate1V 不会给“项目不行”的大结论，只会给分支级 no-go：

- 如果 `Gate1V-2` 做不到 metric parity、expert replay runbook、score/reward/success 字段和 result artifact 闭合，则判定当前 fallback oracle 评分链不可释放 live。
- 如果 `Gate1V-2a` 冻结不了 config、score-capable runner 或 EBench action stream，则判定当前 fallback oracle route 仍不能进入 live；这时应该转 `native_controller_research` 或 asset/task no-score hardening，而不是继续试。
- 如果 `Gate1V-2c` 不能用 fake-client tests 证明 runner 会 start job、reset、feed action、poll pending reset、读取 `episode_result` 和 authoritative `result_info.json`，则不能释放 score live；此时停止调 expert/policy，先修 runner / evaluator job lifecycle。
- 如果 bounded expert-oracle live 后 expert 动作进入了 EBench，但 metric 不涨、success 不记录、result_info 或 trace 不可复现，则判定当前 robot/task fallback score route blocked。
- 如果 `Gate1V-3` 最后仍落回当前 `16D joint_position -> set_joint_position_targets -> world.step`，或只能靠 diagnostic-only hold / seed / offset / local hack 达标，则 native-controller route 不能升级为 score route。
- 如果 asset/task lane 只完成 reset/step/render/metric/logging，但没有 score artifact，则只能 claim asset/task contract，不得 claim task success。

## Branches

| Lane | Purpose | Earliest useful result | Stop line |
|---|---|---|---|
| `robot_task_fallback_oracle` | 用更容易评分的 robot/task 组合先闭合 EBench metric / Expert Oracle Score | `Gate1V-2` zero-live preflight 过审后，一次 bounded expert-oracle live 产出 score artifact | metric 读错对象、expert action 进不了 EBench、reward/success/result_info 不闭合 |
| `asset_task_no_score_hardening` | 继续把 LabUtopia DryingBox / AAN 资产、layout、render、metric、logging 做成稳定交付物 | reset / step / render / metric / logging 全部复现，`score_claim_allowed=false` | wrapper 指错资产、door RevoluteJoint metric 不闭合、waiver/material/physics 不清楚 |
| `native_controller_research` | 单独研究 Lift2 native control contract | 新 control contract 与当前 joint-position path 的差异、readback schema、fake-client harness 闭合 | 仍回到同一 joint-position path，或无法接 score metric |

## Gate1V Stages

### Gate1V-0: Branch Freeze

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_live_20260706/result_compact.json`
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2a_provenance_review_result_20260706.json`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [x] **Step 1: Freeze the closed branch**

Write the following canonical status into the handoff and score plan:

```text
F2A_FAIL_NO_TRUE_NEW_OFFICIAL_ACTION_ABSTRACTION_CLOSE_F_STAGE_LOWER_LEVEL_ACTION_BRANCH
```

- [x] **Step 2: Preserve the non-claims**

Record that F2a closes only the F-stage lower-level official/OpenPI action branch. It does not close the LabUtopia-to-EBench project, DryingBox asset acceptance, native-controller research, or Expert Oracle Score as a final objective.

- [x] **Step 3: Verify wording**

Run:

```bash
rg -n "F2A_FAIL|not project no-go|Expert Oracle Score" docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Expected: the documents contain the branch closure and the non-claim boundary.

### Gate1V-1: Route Triage Zero-Live

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_post_f_stage_route_decision_plan_20260706.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [x] **Step 1: Register the three lanes**

The manifest must include these lane ids:

```text
robot_task_fallback_oracle
asset_task_no_score_hardening
native_controller_research
```

- [x] **Step 2: Assign the recommended priority**

Recommended order:

```text
1. robot_task_fallback_oracle
2. asset_task_no_score_hardening
3. native_controller_research
```

- [x] **Step 3: Validate JSON**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_post_f_stage_route_decision_plan_20260706.json >/tmp/gate1v.json
```

Expected: exit code `0`.

### Gate1V-2: Fallback Oracle Preflight

**Files:**
- Modify later: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Create later: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_fallback_oracle_preflight_20260706.json`

- [x] **Step 1: Zero-live metric parity audit**

Before any live, identify the metric object, metric joint, expected state field, `reward`, `success`, `result_info.json`, and trace field that will prove the expert answer is being scored.

- [x] **Step 2: Zero-live expert replay runbook**

Write the exact robot/task pair, expert action source, action dialect, conda/runtime environment, command, output directory, and artifact list.

- [x] **Step 3: Live release decision**

Live is allowed only if Step 1 and Step 2 both pass review. The live can claim `Expert Oracle Score` only if it produces score / reward / success, action log, metric trace, `result_info.json`, and render/readback evidence. 2026-07-06 result: live was not released because the frozen score-capable action stream / runner contract did not close.

- [x] **Step 4: Stop if the score contract is not closed**

If expert action reaches EBench but metric/reward/success/result artifacts do not close, mark the fallback oracle route blocked and do not re-run with changed seeds or offsets until a new zero-live hypothesis is written.

### Gate1V-2a: Fallback Oracle Freeze

**Files:**
- Create later: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2a_fallback_oracle_freeze_20260706.json`
- Modify later: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify later: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Freeze the EBench task config**

Copy or pin the exact Franka POC `level1_open_door` EBench config from GenManip into a frozen location, record sha256, Git revision, robot, action space, metric object, metric joint, and output artifact contract.

- [x] **Step 2: Audit/freeze the score-capable runner**

Record the runner path, sha256, command, conda environment, output directory, and evidence files. The runner must produce EBench score artifacts, not only diagnostic logs.

- [x] **Step 3: Audit/freeze the expert action source**

Record whether the expert input is a replayable action stream or a deterministic oracle route. It must be executable by EBench and must not rely only on native LabUtopia video success.

- [x] **Step 4: Decide live release**

If Steps 1-3 close, release exactly one bounded fallback score live. If any step fails, do not start Isaac; mark the fallback route still blocked and pick the next branch by zero-live review.

2026-07-06 result: Step 1 closed, Steps 2-3 did not close. The local frozen config is
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2a_fallback_oracle_freeze_20260706/frozen_configs/level1_open_door.yml`.
The formal evaluator score-artifact chain is identified, but the available LabUtopia probe scripts remain diagnostic/no-score and the native expert evidence is video/log only. Therefore Step 4 is no-live release.

### Gate1V-2b: Runner / Action-Source Contract

**Files:**
- Create later: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2b_runner_action_source_contract_20260706.json`
- Modify later: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify later: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Audit the score-capable oracle runner contract**

The runner must feed the formal EBench evaluator, not only a diagnostic probe. It must declare command, conda env, input action dialect, output directory, and required score artifacts: `result_info.json`, action log, metric trace, and render/readback.

- [x] **Step 2: Audit the expert action source**

Choose one: a replayable EBench action stream, or a deterministic oracle route that EBench can execute. Native LabUtopia video/log success is not enough.

- [x] **Step 3: Reject historical false positives**

Do not reuse a run only because its run id contains `expert_oracle`. It must have `score=1` or an explicitly expected score, non-empty metric trace, and matching action/source provenance.

- [x] **Step 4: Live release decision**

If Steps 1-3 close, allow at most one bounded fallback score live. If they do not close, keep the selected fallback route blocked and move effort to `native_controller_research` or `asset_task_no_score_hardening`.

2026-07-06 result: Gate1V-2b did not close. Evidence:
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2b_runner_action_source_contract_20260706.json`.
The formal EBench evaluator score-artifact chain exists, but no frozen score-capable oracle runner/action source exists. A read-only scan found 73 Franka open-door `result_info.json` files and all had `score=0.0`, `success_rate=0`, and `metric_score=[]`. Therefore no bounded fallback score live is released from this branch.

### Gate1V-2c: Score Runner Build Plan

**Files:**
- Create: `docs/superpowers/specs/2026-07-06-gate1v-score-capable-oracle-runner-design.md`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json`
- Modify later in GenManip: `standalone_tools/labutopia_poc/score_capable_oracle_runner.py`
- Test later in GenManip: `tests/labutopia_poc/test_score_capable_oracle_runner.py`

- [x] **Step 1: Define formal score authority**

Record that formal score authority is:

```text
post_episode_process -> episode_result.score -> saved/eval_results/<benchmark>/<run_id>/<task>/<seed>/result_info.json
```

Diagnostic `metric`, `done_info.info`, old no-score probe summaries, and historical `expert_oracle` directory names are not score authority.

- [x] **Step 2: Define runner contract**

The runner must start the formal job, reset, feed a replayable or deterministic oracle action source, resolve pending resets,
record `episode_result`, and verify authoritative `result_info.json`.

- [x] **Step 3: Define fake-client test gate**

Before any live release, fake-client tests must prove the runner:

```text
requires result_info score/success_rate
rejects diagnostic-only metric
polls reset_pending until episode_result exists
writes action_log and metric_trace
rejects empty metric_score without reviewed waiver
rejects action dimension mismatch
keeps score_claim_allowed=false on exception
```

- [x] **Step 4: Preserve no-live claim boundary**

2c is planning / implementation-readiness evidence only. It keeps
`live_release_allowed_now=false`, `bounded_fallback_score_live_allowed=false`,
`expert_oracle_score_claim_allowed=false`, `official_benchmark_reproduction_claim_allowed=false`,
`standard_model_score_claim_allowed=false`, and `project_no_go=false`.

2026-07-06 result: Gate1V-2c runner code checkpoint is code-ready/no-live, not passed. Evidence:
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json`.
and
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_code_checkpoint_20260706.json`.
The GenManip runner core now exists and passes fake-client tests, but the EBench-executable expert action source is
not frozen. Passing 2c would allow only a bounded score-live release review; it would not itself prove
`Expert Oracle Score`.

### Gate1V-3: Native Control Contract Research

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json`

- [x] **Step 1: Audit current candidate control surfaces**

Audit whether current repo / external GenManip state already contains a frozen native control contract that defines input/output schema, units, frames, readback fields, and how `native_drive_target` differs from the failed `joint_position` path.

- [x] **Step 2: Record the future contract required for pass**

The zero-live proof required for a future pass must show the route does not simply flow back into the current `set_joint_position_targets -> world.step` semantics as the sole physical control surface. Current result: no such frozen proof exists yet, so Gate1V-3 is incomplete/no-live, not pass.

- [x] **Step 3: Keep research claims separate**

The manifest must set:

```json
{
  "standard_model_score_claim_allowed": false,
  "official_benchmark_reproduction_claim_allowed": false,
  "expert_oracle_score_claim_allowed": false
}
```

2026-07-06 result: Gate1V-3 does not pass and does not release live. Evidence:
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json`.
The current-state audit found no frozen native Lift2/R5a control contract genuinely different from the closed direct
16D route. This is not a final native-controller no-go; it means the next native-lane task must first create a
no-score contract spec and fake-client/readback harness.

### Gate1V-4: Live Release Board

**Files:**
- Create later: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_live_release_board_20260706.json`

- [ ] **Step 1: Split live categories**

Use separate categories:

```text
fallback_score_live
native_research_live
asset_smoke_live
```

- [ ] **Step 2: Require a zero-live preflight per live**

No live is released unless the lane has a passing zero-live manifest with command, environment, evidence dir, pass/fail thresholds, and non-claims.

- [ ] **Step 3: Close failed lives by branch**

A failed `native_research_live` cannot be reported as Expert Oracle Score failure. A failed `asset_smoke_live` cannot be reported as official score failure. A failed `fallback_score_live` cannot be reported as Lift2 official baseline failure.

## Immediate Next Work

1. Do not release fallback score live from Gate1V-2b.
2. Do not release native research live from Gate1V-3.
3. Continue Gate1V-2c by freezing or generating the EBench-executable expert action source / deterministic route for the new score-capable runner.
4. After 2c passes, run a separate live release review before any bounded fallback score live.
5. If the team wants the native Lift2 route, write a separate `native_drive_target` contract spec plus fake-client/readback harness; keep all claims no-score until it proves it differs from the failed `joint_position` route.
6. In parallel only as no-score work, keep asset/task hardening moving with `score_claim_allowed=false`.

## Verification

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_post_f_stage_route_decision_plan_20260706.json >/tmp/gate1v.json
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json >/tmp/gate1v_2c.json
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json >/tmp/gate1v_native.json
git diff --check -- docs/superpowers/plans/2026-07-06-eos2-gate1v-post-f-route-decision.md docs/superpowers/specs/2026-07-06-gate1v-score-capable-oracle-runner-design.md docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_post_f_stage_route_decision_plan_20260706.json docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/evidence_manifests/README.md
rg -n "Gate1V|Gate1V-2c|F2A_FAIL|robot_task_fallback_oracle|native_controller_research|native_drive_target|score_claim_allowed|INCOMPLETE_GATE1V3" docs/superpowers/plans/2026-07-06-eos2-gate1v-post-f-route-decision.md docs/superpowers/specs/2026-07-06-gate1v-score-capable-oracle-runner-design.md docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_post_f_stage_route_decision_plan_20260706.json docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/evidence_manifests/README.md
```

Expected: JSON valid, diff check clean, and all key stage terms present.

# EOS2 S2 Instrumented Replay Stop-Go Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide whether the Route B LabUtopia native expert replay can be promoted from M1 positive score candidate to S2/M3 defensible Expert Oracle Score evidence without blind retries.

**Architecture:** S2 is split into a no-live instrumentation checkpoint, one release-reviewed instrumented replay, and one optional confirmation replay only if the first replay has complete evidence but fails the metric/physics criterion. Missing readback, missing metric trace, or missing terminal render is classified as an evidence-system failure, not as proof that the expert route is impossible.

**Tech Stack:** GenManip `score_capable_oracle_runner.py`, EBench `/step_chunk` replay, `LABUTOPIA_ORACLE_DEBUG_OBS=1`, `result_info.json`, `action_log.jsonl`, `metric_trace.jsonl`, DryingBox `obj_DryingBox_01/RevoluteJoint`, `python -m pytest`, `python -m json.tool`, `git diff --check`.

---

## Current Decision

S0 and S1 are already closed:

```text
S0: frozen real expert action source, 905 contiguous 9D joint_position actions
S1/M1: Route B fresh S1 official score-chain pass, score=1.0, success_rate=1.0
```

S2 is now closed for M3 single-episode score/readback evidence after the full-env repaired S2-R1E replay:

```text
S2-R1E: official score chain PASS, score=1.0, success_rate=1.0
S2/M3: PASS for single-episode score/readback evidence, with final door angle=41.715865deg, within_range=true, succ_cnts=59, terminal camera artifact, and canonical camera2.mp4
```

The next action is **not** another S1 retry, **not** score tuning, **not** S2-L2, and **not** an unbounded S2 replay loop. S2-L1 exposed the evidence export gap; S2-L1R then exposed `curobo` import, Ray tmpdir socket path, CUDA runtime, and `ninja` environment contract gaps. Those were execution/evidence contracts, not expert route failures. The latest reviewed run is `eos2_s2_l1r_full_env_repaired_route_b_readback_render_20260707_003`; it is recorded in `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1e_full_env_repaired_result_review_20260707.json`. Next work moves to M4/S4 small-sample robustness or S3 Lift2 oracle/retarget, with visual/material parity as a separate follow-up.

## Product Interpretation

给 PM 的一句话：现在“标准答案放进 EBench 能拿分”已经不是只看分数文件，而是同一轮 run 同时看到了分数、门角、评分输入和视频 artifact。S2-R1E 的正式 EBench 分数是 `score=1.0`，最终门角 `41.715865deg` 落在 `[30,120]deg` 成功范围内，`succ_cnts=59`，`camera2.mp4` 存在。所以 M3 single-episode Expert Oracle Score POC 的 score/readback evidence 可以签收。还不能说多 seed 稳定、policy 能做、Lift2 baseline 完成、official leaderboard 或视觉材质完全一致。

已经到达的“弄好”点：

```text
S2-R1E full-env repaired replacement replay pass
```

也就是同一次 EBench run 里同时有：

- official `result_info.json` 中 `score=1.0` / `success_rate=1.0` / `metric_score=[[[1.0]]]`
- same-run `action_log.jsonl`
- DryingBox `obj_DryingBox_01/RevoluteJoint` terminal angle `41.715865deg`
- metric input dump 和 `succ_cnts=59` trace
- terminal camera artifact 和 canonical `camera2.mp4`

最早能说“这条 Route B Franka/native replay 路线不成立”的点：

```text
post-repair replay + optional confirmation replay both have complete evidence, identical action source sha, identical command/env, identical metric code/contract, identical instrumentation, and the same metric/physics failure signature
```

S2-L1 已经出现的情况就是 evidence failure：分数通过，但终态门角和 terminal render 没有闭环。这不能判路线失败；只能判取证系统没闭环。S2-L1R 之后出现的 `curobo` / Ray tmpdir / CUDA runtime / `ninja` 问题都是 execution contract failure，也不能判路线失败。S2-R1E 已在修好这些合同后通过；因此当前不释放 S2-L2。

## Stop-Go Ladder

| Stage | Live budget | Goal | Pass | Stop / fail classification |
|---|---:|---|---|---|
| S2-I0 instrumentation checkpoint | 0 | 让 runner 能稳定记录门角度、metric 输入和终态渲染 | tests pass，日志能显示 render/debug/readback 配置 | 代码 checkpoint 不过，不释放 live |
| S2-R0 release review | 0 | 审核 replay #1 是否满足一次性放行条件 | release manifest 明确 run id、source sha、env、artifact list、stop lines | manifest 缺任何关键项，不释放 live |
| S2-L1 instrumented replay #1 | 1 consumed | 用同一个 frozen Route B source 重跑并补证据 | official score chain 再次 `score=1.0` | 已分类为 evidence failure；不进入 L2，不判路线失败 |
| S2-E0 result classification | 0 | 登记 L1 结果并做 root-cause audit | result manifest 写清 score pass / evidence fail | 不允许把 missing evidence 升级成 Route B no-go |
| S2-I1 evidence export contract repair | 0 | 修 client 参数透传、terminal obs 保留、metric input/succ_cnts 和 render artifact 绑定 | no-live tests + review 证明证据出口能产出 | 不过则不释放新的 live |
| S2-R1 post-S2-I1 release review | 0 | 审核修复后的一次 replay 是否准跑 | 已执行但 blocked：确认当时 live producer 没有 metric_input/succ_cnts | 不释放 live，转 S2-I2 |
| S2-I2 metric producer snapshot repair | 0 | 补齐 debug/metric producer，让 terminal obs 能真实导出 metric_input/succ_cnts | `MetricsManager.last_metric_debug_snapshot` + `debug.labutopia_open_door` producer tests 通过 | 不过则继续停在 evidence system |
| S2-R1B post-S2-I2 release review | 0 | 审核 producer 修复后的一次 replay 是否准跑 | 已完成：固定同一 source sha、run id、env、artifact list、producer expectations 和 stop lines，释放 exactly one S2-L1R | manifest 缺任何关键项，不释放 live |
| S2-L1R post-repair evidence replay | 1 | 用同一 frozen Route B source 验证证据闭环 | 已执行但 reset 前失败：`curobo` import path 缺失 | execution contract failure；不能判 Route B，不能进 L2 |
| S2-I3 cuRobo env contract repair | 0 | 把 `curobo_src` 加入 server/runner `PYTHONPATH` 并 no-live 验证原失败点 | `from curobo.types.state import JointState` 在目标 conda + fixed `PYTHONPATH` 下通过 | 不过则不释放 replacement replay |
| S2-R1C replacement replay release review | 0 | 审核环境修复后是否能准跑一次替代 evidence replay | 已完成：新 run id、干净 evidence dir、同 source sha、cuRobo-inclusive `PYTHONPATH`、同 render/debug 参数 | manifest 缺任何关键项，不释放 live |
| S2-L1R-env replacement evidence replay | 1 consumed | 用修好环境的同一 Route B source 验证证据闭环 | 已通过：S2-R1E `_003` score、door angle、metric input/succ_cnts、terminal camera artifact 和 canonical `camera2.mp4` 同 run 一致 | 不释放 L2；视觉/材质 parity 另做 follow-up |
| S2-L2 confirmation replay | 0 now, optional 1 only in future metric/physics failure | 只在完整取证但 metric/physics 失败时复验 | 当前不需要；S2-R1E 没有 metric/physics failure | 不能因为 L1/L1R 历史取证或环境失败而进入 L2 |
| S2-D decision | 0 | 更新 M3 claim 或 route closure | M3 single-episode score/readback evidence passed | 不得升级为 project-wide readiness、policy score 或 leaderboard |

## Failure Classes

### A. Evidence Failure

表现：

- no terminal/front-view render
- no metric input dump
- no `succ_cnts` trace
- no initial/final DryingBox joint readback
- stdout 仍大量出现 `No camera frames provided for this step`

结论：

```text
取证系统失败，不是 expert route 失败。
```

下一步只能修 instrumentation / renderer / debug obs / metric dump。不能换路线，也不能判 Route B 不成立。S2-L1 当前结果属于这一类。

S2-L1 已知 root-cause candidates:

- `genmanip_client.EvalClient.step_chunk()` 当前只接受 `action_chunk`，但 server / worker_pool 已支持 `render_mode` 和 `subframes` query params；runner 因此落到 `legacy_fallback`，`render_mode=always` 没真正透传。
- episode `done` 时 worker_pool 会启动 pending reset，并先返回 `reset_pending` / result packet；runner 的 `terminal_obs_compact.json` 是从这个包写出来的，所以 `debug.labutopia_open_door` 和 `video.camera2_view` 为空。
- authoritative `metric_score=[[[1.0]]]` 已存在，但 metric input dump / `succ_cnts` trace 还没有作为 S2 证据导出。

S2-R1 后的补充结论：

- S2-R1 多角度 review 确认 S2-I1 只证明“runner 能保存已有字段”，没有证明 live producer 会生成 `metric_input/succ_cnts`。
- S2-I2 no-live repair 已补 producer：`MetricsManager` 保留 `last_metric_debug_snapshot`，`debug.labutopia_open_door` 会从 current metric 或 last completed metric snapshot 中找到 `CheckJointAngle(obj_DryingBox_01/RevoluteJoint)`，并导出 `metric_input`、`succ_cnts`、`metric_success_counter` 和 `metric_score_snapshot`。
- S2-I2 仍不释放 live；S2-L1R 只能由 S2-R1B release review 放行。

### B. Complete Evidence, Metric/Physics Failure

表现：

- official score 不是 1，或 `success_rate` 不是 1
- final door angle 不在 `[30,120]deg`
- door angle 进入范围但 `succ_cnts < 59`
- terminal render 和 joint readback 一致显示门没有达到 metric 要求

结论：

```text
Route B 可能不适配 official metric，需要一次同配置 L2 confirmation replay。
```

只有 L1R 和 L2 的 action source sha、command/env、metric code/contract、instrumentation、step count、metric trace、readback、render 都完整，且失败签名一致，才关闭当前 Franka/native replay route。

### C. Execution Contract Failure

表现：

- runner 异常退出
- action split 不再是 Route B bridge + native expert replay
- scene 找不到 `obj_DryingBox_01` 或 `RevoluteJoint`
- action schema / worker id / reset contract 不一致

结论：

```text
执行合约失败，不是 expert quality 失败。
```

下一步修 runner / scene binding / action contract，不消耗 L2 route judgment。

## Task 1: Runner Instrumentation Code Checkpoint

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/score_capable_oracle_runner.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_score_capable_oracle_runner.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_code_checkpoint_20260706.json`

- [x] **Step 1: Add failing tests for render/debug capture**

Run from GenManip:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
python -m pytest tests/labutopia_poc/test_score_capable_oracle_runner.py -q
```

Add tests that require the runner to:

- accept `--step-chunk-render-mode always`
- accept `--step-chunk-subframes 2`
- accept `--trace-final-obs`
- pass `render_mode` and `subframes` to `client.step_chunk(...)` when the client supports them
- fall back to the old `client.step_chunk(action_chunk)` signature for fake or older clients
- write a compact terminal observation artifact without dumping giant image arrays into the main trace

Expected before implementation: at least one focused test fails because the runner does not yet expose these options or artifacts.

- [x] **Step 2: Implement minimal runner instrumentation**

Add CLI options:

```text
--step-chunk-render-mode {lite,always}
--step-chunk-subframes INT
--trace-final-obs
```

Implement a small helper around `client.step_chunk`:

```text
try extended signature with render_mode/subframes
if TypeError, fall back to the existing signature
```

When `--trace-final-obs` is enabled, write:

```text
terminal_obs_compact.json
terminal_camera2_view.<ext> if a terminal camera frame exists
metric_trace event: terminal_readback
```

The compact JSON must include:

- observed obs keys
- `debug.labutopia_open_door.door_angle_rad`
- `debug.labutopia_open_door.door_angle_deg`
- `debug.labutopia_open_door.status`
- `video.camera2_view` metadata or saved artifact path
- `state.joints`, `state.ee_pose`, and `state.gripper` metadata when present

- [x] **Step 3: Verify code checkpoint**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
python -m pytest tests/labutopia_poc/test_score_capable_oracle_runner.py -q
python -m py_compile standalone_tools/labutopia_poc/score_capable_oracle_runner.py
git diff --check -- standalone_tools/labutopia_poc/score_capable_oracle_runner.py tests/labutopia_poc/test_score_capable_oracle_runner.py
```

Expected: tests pass, py_compile exits 0, diff check exits 0.

## Task 2: S2 Replay #1 Release Review

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_release_review_20260706.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [x] **Step 1: Write release review manifest**

The manifest must set:

```json
{
  "status": "RELEASED_EXACTLY_ONE_S2_INSTRUMENTED_REPLAY_AFTER_CODE_CHECKPOINT",
  "maximum_live_replays_released_now": 1,
  "action_source_policy": "same frozen Route B source only",
  "score_tuning_allowed": false
}
```

If the code checkpoint is not complete, the manifest must instead set:

```json
{
  "status": "BLOCKED_S2_INSTRUMENTED_REPLAY_RELEASE_PENDING_RUNNER_INSTRUMENTATION_CODE_CHECKPOINT_NO_LIVE",
  "maximum_live_replays_released_now": 0
}
```

- [x] **Step 2: Verify release criteria**

Release only if all are true:

- S0 source sha is fixed
- S1R-D Route B source path is fixed
- runner instrumentation tests passed
- `LABUTOPIA_ORACLE_DEBUG_OBS=1` is listed in command env
- `--step-chunk-render-mode always` is listed in command
- `--trace-final-obs` is listed in command
- output artifact list includes terminal obs, terminal render, metric trace, action log, official result_info

Expected now: blocked until Task 1 is complete.

## Task 3: S2 Replay #1 Decision

**Files:**
- Create after live: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_result_20260706.json`
- Modify after live: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify after live: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Classify replay #1**

Allowed statuses:

```text
PASS_S2_M3_SINGLE_EPISODE_EXPERT_ORACLE_EVIDENCE_CLOSED
BLOCKED_S2_EVIDENCE_FAILURE_NO_ROUTE_JUDGMENT
FAIL_S2_COMPLETE_EVIDENCE_METRIC_PHYSICS_MISMATCH_REQUIRES_ONE_CONFIRMATION_REPLAY
FAIL_S2_EXECUTION_CONTRACT_FAILURE_NO_ROUTE_JUDGMENT
```

Actual S2-L1 result:

```text
BLOCKED_S2_L1_EVIDENCE_FAILURE_SCORE_1_NO_ROUTE_JUDGMENT_TERMINAL_READBACK_RENDER_MISSING
```

Evidence:

- runner exit `0`
- authoritative `result_info.json`: `score=1.0`, `success_rate=1`, `metric_score=[[[1.0]]]`
- executed steps: `578`
- action split: `14` Route B bridge + `564` native expert actions
- `terminal_obs_compact.json`: `obs_keys=[]`, `debug.labutopia_open_door=null`
- terminal readback: `door_angle_deg=null`, `video_camera2_available=false`
- runner log: `567` x `No camera frames provided for this step`

- [x] **Step 2: Enforce decision boundary**

If PASS:

```text
允许 claim: M3 single-episode Expert Oracle Score POC complete
禁止 claim: M4 stability, workflow ready for expansion, official leaderboard result
```

If evidence failure:

```text
不允许 L2 confirmation replay；先修 instrumentation。
```

If complete metric/physics failure:

```text
允许 exactly one S2-L2 confirmation replay with identical action source sha, command/env, metric code/contract, and instrumentation.
```

If execution contract failure:

```text
先修 runner/scene/action contract；不判 expert route。
```

## Task 4: S2-I1 Evidence Export Contract Repair Plan

**Files:**
- Modify after approval: `/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src/genmanip_client/eval_client.py`
- Modify after approval: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/isaac_worker_pool.py`
- Modify after approval: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/score_capable_oracle_runner.py`
- Test after approval: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_score_capable_oracle_runner.py`
- Create after approval: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i1_evidence_export_contract_repair_20260706.json`

- [x] **Step 1: Add no-live tests for the two proven evidence gaps**

Required failing tests:

```text
EvalClient.step_chunk forwards render_mode/subframes as query params to /step_chunk
score_capable_oracle_runner fails fast if render_mode=always falls back to legacy in live S2 mode
terminal done response preserves final_obs or terminal_obs separately from reset_pending packet
terminal_obs_compact includes debug.labutopia_open_door and video.camera2_view when the server produced them
metric trace exports metric input and succ_cnts, not just final metric_score
```

- [x] **Step 2: Implement the minimal contract repair**

Required behavior:

```text
client.step_chunk(action_chunk, render_mode="always", subframes=2)
server response keeps terminal_obs when final_done=True before pending reset starts
runner writes terminal obs/readback from terminal_obs, not reset result
runner binds recorder camera2.mp4 or extracted terminal/front-view frame into result manifest
runner records explicit failure if terminal readback/render is absent
```

- [x] **Step 3: Review before any live replay**

Pass condition:

```text
focused tests pass
py_compile passes
diff check passes
reviewer agrees S2-L1R evidence fields cannot silently fall back to empty/null
```

If this does not pass, no S2-R1 or S2-L1R live replay is released.

Actual S2-I1 code checkpoint result:

```text
PASS_S2_I1_EVIDENCE_EXPORT_CONTRACT_REPAIR_NO_LIVE_CODE_CHECKPOINT
```

Evidence manifest:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i1_evidence_export_contract_repair_20260706.json
```

Validated repairs:

- `genmanip_client.EvalClient.step_chunk(...)` now accepts `render_mode` and `subframes`, and forwards them as `/step_chunk` query params.
- `genmanip_client.EvalClient._resolve_pending_resets(...)` preserves done-step `terminal_obs` while polling async reset results.
- `make_reset_pending_response(...)` and `IsaacWorkerPool` can preserve done-step `terminal_obs` even when async pending reset starts.
- `IsaacWorkerPool.step_chunk(...)` returns a ready pending-reset result instead of consuming and discarding it before slow-path execution.
- `score_capable_oracle_runner.py` preserves `terminal_obs` across pending reset polling and writes terminal readback from it.
- `terminal_readback` now exports `metric_input` and `succ_cnts` when `debug.labutopia_open_door` provides them.
- `render_mode=always` no longer silently falls back to a legacy `step_chunk(action_chunk)` client unless an explicit compatibility flag is passed.

Fresh no-live verification:

```text
PYTHONPATH=src python -m pytest tests/test_eval_client_step_chunk_render_params.py tests/test_eval_client_plan_object_frame_waypoints.py -q
6 passed in 0.27s

python -m pytest tests/labutopia_poc/test_isaac_worker_pool_done_info.py tests/labutopia_poc/test_score_capable_oracle_runner.py -q
18 passed in 0.56s

py_compile checks: exit 0
git diff --check checks: exit 0
```

Next action:

```text
S2-R1 post-repair replay release review has been executed and blocked; no S2-L1R live replay was released by S2-I1/S2-R1.
```

S2-R1 review resolved the reviewer-identified producer boundary as blocked:

```text
metric_input/succ_cnts export tests proved the runner preserves those fields when present, but live debug/metric producer code did not emit them. S2-I2 was required and has now passed no-live producer tests. Next action is S2-R1B post-S2-I2 release review before any S2-L1R live replay.
```

## Task 5: S2-I2 Metric Producer Snapshot Repair

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/metrics/metrics_manager.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/labutopia_oracle_debug_state.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_labutopia_oracle_debug_state.py`
- Create: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_metrics_manager_debug_snapshot.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json`

- [x] **Step 1: Record S2-R1 blocked release review**

S2-R1 did not release live because `debug.labutopia_open_door` did not produce `metric_input/succ_cnts`.

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json
maximum_live_replays_released_now=0
```

- [x] **Step 2: Add RED tests for producer gap**

Focused RED failures:

```text
test_oracle_debug_obs_exports_metric_input_and_success_counter_snapshot
KeyError: 'metric_input'

test_metrics_manager_preserves_last_metric_debug_snapshot_after_completion
AttributeError: 'MetricsManager' object has no attribute 'last_metric_debug_snapshot'
```

- [x] **Step 3: Implement metric producer snapshot**

Implementation:

- `MetricsManager.step()` preserves `last_metric_debug_snapshot` after metric update and before `cur_union_metric` can advance.
- `debug.labutopia_open_door` finds `CheckJointAngle(obj_DryingBox_01/RevoluteJoint)` from current metrics or `last_metric_debug_snapshot`.
- The debug payload exports `metric_input`, `succ_cnts`, `metric_success_counter`, and `metric_score_snapshot`.

- [x] **Step 4: Verify no-live producer closure**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. python -m pytest tests/labutopia_poc/test_labutopia_oracle_debug_state.py tests/labutopia_poc/test_metrics_manager_debug_snapshot.py tests/labutopia_poc/test_score_capable_oracle_runner.py tests/labutopia_poc/test_isaac_worker_pool_done_info.py tests/labutopia_poc/test_labutopia_metrics.py -q
```

Observed:

```text
55 passed in 1.46s
```

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json
```

Next action before S2-L1R:

```text
S2-R1B post-S2-I2 release review released exactly one S2-L1R live replay.
That S2-L1R run failed before reset with ModuleNotFoundError: No module named 'curobo'.
S2-I3 cuRobo env contract repair has passed no-live preflight.
S2-R1C has released exactly one env-repaired replacement replay with a new run id.
```

## Task 6: S2-I3 / S2-R1C Environment Contract Repair

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_l1r_post_s2_i2_env_failure_result_20260707.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i3_curobo_env_contract_repair_20260707.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1c_post_env_repair_release_review_20260707.json`

- [x] **Step 1: Classify S2-L1R failure**

Observed:

```text
runner exit 1
reset completed: false
step actions executed: 0
official result_info.json: missing
error: ModuleNotFoundError: No module named 'curobo'
```

Decision:

```text
FAILED_EXECUTION_CONTRACT_BEFORE_RESET_CUROBO_IMPORT_MISSING_NO_ROUTE_JUDGMENT
```

- [x] **Step 2: Verify environment root cause no-live**

Observed:

```text
without curobo_src in PYTHONPATH: curobo import fails
with curobo_src in PYTHONPATH: from curobo.types.state import JointState succeeds
```

- [x] **Step 3: Release one env-repaired replacement replay**

Fixed run contract:

```text
run_id=eos2_s2_l1r_env_repaired_route_b_readback_render_20260707_001
port=18139
PYTHONPATH=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback:/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
action_source_sha256=fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a
evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_l1r_env_repaired_replay_20260707
```

## Verification

Run from LabUtopia:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_stop_go_20260706.json >/tmp/s2_instrumented_stop_go.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json >/tmp/s2_r1_blocked.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json >/tmp/s2_i2_metric_producer.json.ok
git diff --check -- \
  docs/superpowers/plans/2026-07-06-eos2-s2-instrumented-replay-stop-go.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_stop_go_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md
```

Expected: JSON is valid and diff check exits 0.

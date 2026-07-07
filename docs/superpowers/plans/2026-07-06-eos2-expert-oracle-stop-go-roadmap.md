# EOS2 Expert Oracle Stop-Go Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent blind EOS-2 retries by defining the exact evidence gates that prove LabUtopia expert actions can be scored by EBench, or that a bounded route must stop.

**Architecture:** This roadmap sits above the current F2a / Gate1V evidence chain. It separates formal EBench scoring, expert action reproducibility, first nonzero official score, and small-sample stability into independent gates with explicit local no-go conditions. It also maps engineering gates S0-S4 to PM-facing milestones M1-M4 so the same evidence can be used for execution and reporting.

**Tech Stack:** LabUtopia Markdown docs, EBench / GenManip evidence manifests, `result_info.json` score artifacts, `python -m json.tool`, `git diff --check`.

---

## Current State

S0 is now closed. The frozen LabUtopia native expert action source is recorded in:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json
```

The frozen replay source has 905 contiguous 9D `joint_position` actions and a freezer sha256:

```text
e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f
```

This means the "standard answer file" exists. It does **not** mean EBench has scored it yet.
S1 has now consumed its two bounded infrastructure attempts. Attempt 2 reached real EBench /
GenManip finalization far enough to write authoritative `result_info.json`, but the runner
contract still failed because the result locator was pointed at a run-specific directory, the
`result_info.json` has empty `metric_score`, and only one action executed before `done=true`.
S1R-A result locator repair is now complete. S1R-B metric-score review is also complete,
but it blocks release: attempt2's `metric_score=[]` with null start/end is a minimal
fallback artifact, not a full recorder finalize artifact. S1R-B2 full finalize lifecycle
code checkpoint is now complete. S1R-C has attributed the step0 invalid state to
reset/action contract mismatch and selected Route B bounded bridge. S1R-D release review
then released exactly one Route B fresh S1 smoke, using a 14-step bounded bridge followed
by the unchanged 905-action frozen expert replay. That fresh S1 has now passed M1:
runner exit 0, `PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT`, canonical `result_info.json`,
`score=1.0`, `success_rate=1`, non-empty `metric_score=[[[1.0]]]`, same-run action log,
and same-run metric trace.
The implementation plan is:

```text
docs/superpowers/plans/2026-07-06-eos2-s1r-score-chain-repair.md
```

Earlier, F2a closed the current F-stage lower-level official/OpenPI action branch:

```text
F2A_FAIL_NO_TRUE_NEW_OFFICIAL_ACTION_ABSTRACTION_CLOSE_F_STAGE_LOWER_LEVEL_ACTION_BRANCH
```

This is a local route closure, not a LabUtopia-to-EBench project no-go and not an `Expert Oracle Score` failure. Gate1V-2c has a score-capable oracle runner code checkpoint with fake-client tests. The remaining blocker has moved from "S1 formal score-chain smoke artifact contract is not yet closed" to "S2/M3 readback, render, and route-claim review are not yet closed."

The authoritative score source remains:

```text
post_episode_process -> episode_result.score -> saved/eval_results/<benchmark>/<run_id>/<task>/<seed>/result_info.json
```

Diagnostic `metric`, `done_info`, render screenshots, fake-client summaries, and historical folders named `expert_oracle` are not score evidence.

## 2026-07-06 Review Addendum

The first review addendum is now superseded by the S0 freeze success evidence. The useful historical
lesson remains: the earlier failures were environment entry, action-dimension contract, and logger
lifecycle issues; they were not proof that the expert, metric, retarget, or DryingBox route failed.

Current stop/go interpretation:

- S0 已完成：real EBench-executable LabUtopia native expert action source 已冻结。
- S1/M1 现在已经完成：S1R-D Route B fresh S1 产出 authoritative `result_info.json`，`score=1.0`、`success_rate=1`、`metric_score=[[[1.0]]]`，runner contract exit 0。
- S1R-A 已修好 runner locator；S1R-B 已审计并阻止 release，因为 `metric_score=[]` 对应 minimal fallback artifact，不是完整评分明细。
- S1 的目标不是拿高分；哪怕 `score=0`，只要正式 `result_info.json` 和 same-run `action_log.jsonl` / `metric_trace.jsonl` 闭合，并且 runner contract exit 0，M1 才通过。
- S1 两次 bounded live 已用完；S1R-D 使用 14 步 `s1r_route_b_settle_bridge` + 905 步原始 frozen expert replay 的 919-step source，实际执行 578 步后成功结束，其中 14 步 bridge、564 步 native expert action。
- S2/M3 不能直接宣称完成：还缺 door joint readback、metric input dump、render/snapshot 和 route-claim review。
- S3 才判断 Lift2 oracle / retarget 是否有 official scoring value。
- 任何失败都只关闭对应 route：S1 失败关闭 runner / evaluator lifecycle route；S2 失败关闭当前 Franka/native score route；S3 失败关闭当前 Lift2 retarget route。不能直接升级为 project no-go。

Bounded attempt budget:

| Gate | Maximum attempts | Go condition | Stop condition |
|---|---:|---|---|
| S0 native capture | Completed | 已产出 frozen `action_source.jsonl` 和 `action_source_manifest.json` | 不再重复 S0；除非 S1 证明 source contract 本身不可消费 |
| S1 formal score-chain smoke | 2 bounded attempts after S0 freeze plus one S1R-D reviewed fresh S1, completed | 已通过：runner exit 0，真实 EBench finalization 产出 `episode_result.score=1.0`、匹配 `result_info.json`、same-run `action_log` / `metric_trace`，且 `metric_score=[[[1.0]]]` | S1 不再继续 live retry；下一步转 S2/M3 evidence review |
| S1R result-locator / metric-score / finalize repair | Zero-live first; one fresh S1 after review, completed | S1R-A/B/B2/C/D 已完成；Route B fresh S1 已通过 M1 | 不再作为 blocker；历史 attempt2 不能覆盖 fresh S1 结果 |
| S2 Franka/native metric | No new live before readback review | 同一 run 有 action trace、metric inputs、door joint readback、render/snapshot 和 official `result_info.json` | 如果无法从 current fresh run 补足 readback/render，先登记 S2 evidence gap，不盲跑 |
| S3 Lift2 oracle / retarget | 2 mapping families x 2 critical variants | 至少一个 mapping 出现 official nonzero score 或清晰可修的 control-interface blocker | 4 个 bounded variants 都 official zero / invalid 且 control-interface 已排除，关闭当前 Lift2 retarget route |
| S4 robustness | 3-5 episodes / seeds | 多数过预声明阈值，失败可分类 | 单次成功不可复现，或失败超过 3 类 / 不可分类，则不扩展 |

PM-facing interpretation:

- 最早能说 single-episode score POC “弄好”的点是 M3 / Gate 5：不是只看 `score=1.0`，而是同一 run 里 `result_info.json` / `episode_result.score`、action log、`metric_trace`、door joint readback、metric input dump 和 render/snapshot 能互相证明。
- 能说 workflow 可交付扩展的点是 M4 / S4：3-5 episodes/seeds 多数通过预声明阈值，失败分类清楚。
- 任何中间失败都只能判具体 route blocked，例如 S1 runner/evaluator lifecycle、S2 Franka/native frozen replay route、S3 Lift2 retarget route，不能扩大成 LabUtopia-to-EBench project no-go。

## 2026-07-06 Multi-Agent Stop-Go Synthesis After S1R-D

Three review angles were used after the Route B fresh S1 result:

- Score-chain review: M1/S1 is already done; no more S1 live retry should be run. The next valid question is whether the `score=1.0` run has enough same-run evidence to support S2/M3.
- Asset/render review: red material, MDL import path, remote Aluminum, and non-front-view renders are material/visual parity follow-ups unless they make the target invisible or prove the wrong asset/joint is being scored. They must not be mixed into score-chain retries.
- PM delivery review: the work is not "completely done" until score, physical state, visual evidence, and repeatability all agree.

Decision:

| Decision point | Expected next action | Pass means | Fail means |
|---|---|---|---|
| Current state | Stop S1 retries; inspect the fresh S1 artifacts first | We know whether same-run readback/render already exists | Missing evidence becomes an S2 evidence gap, not a reason to rerun S1 |
| S2 no-new-live inventory | Inspect `metric_trace.jsonl`, `action_log.jsonl`, `result_info.json`, metric config/code, and any saved snapshot/video | Door joint state, metric inputs, official score, and visual evidence are all attributable to the same run | Release at most one instrumented S2 replay only to collect missing readback/render, not to tune score |
| S2 instrumented replay, if needed | Run the same frozen Route B source with explicit readback/render capture | `score=1.0`, door joint moved into the configured range, metric input matches DryingBox `RevoluteJoint`, and front-view snapshot supports the state | If score says success but readback/render contradict it, pause score claim and audit evaluator/metric contract |
| S3 Lift2 oracle / retarget | Try only two mapping families with at most two critical variants each | At least one official-robot route has nonzero official score or a clear control-interface blocker | Four bounded variants all zero/invalid after control issues are excluded closes the current Lift2 retarget route |
| S4 robustness | Run 3-5 predeclared episodes/seeds with the same evidence bundle | Majority pass and failures are classified | Single-run-only success or unclassified failures means no expansion |

Therefore the earliest honest "弄好了" is:

```text
M3/S2 closure = single-episode Expert Oracle Score POC is defensible.
M4/S4 closure = workflow is reproducible enough to expand.
```

The earliest honest "这条路线暂时弄不好" is:

```text
S2 no-go = score and physical/readback evidence disagree, or required readback/render cannot be collected by one instrumented replay.
S3 no-go = bounded Lift2 retarget variants all fail after control-interface blockers are excluded.
S4 no-go = the single success cannot be reproduced across 3-5 episodes/seeds.
```

## 2026-07-06 S1 Attempt Update

S1 attempt 1 failed before reset/action because the EBench server rejected an absolute config path
outside its allowed config directory. This was an infrastructure contract issue.

S1 attempt 2 used the corrected relative config path and produced these real artifacts:

```text
client episode_result.json: score=0.0, sr=0.0
client result.json: score=0.0, sr=0.0
authoritative result_info.json: score=0.0, success_rate=0, metric_score=[]
```

However, S1 still does **not** pass:

- runner exit code is `1` because `--result-base-dir` was set to
  `saved/eval_results/ebench/<run_id>` instead of the `saved/eval_results` root, so the runner
  looked for `ebench/<run_id>/ebench/<run_id>/.../result_info.json`;
- `result_info.log_info.metric_score` is empty, so score artifact completeness is not closed under
  the current policy;
- `action_log.jsonl` has only one action and `metric_trace.jsonl` shows `done=true` after
  `executed_steps_total=1`; server stdout logs `Invalid robot state detected at step 0`.
- the reset-to-first-action max joint delta is `2.734214574098587rad`, so the first replay target
  is not in the EBench reset state's local neighborhood.

Therefore the next step is:

```text
S1R-A result locator contract repair (complete)
S1R-B metric_score completeness audit (complete, release blocked; no waiver)
S1R-B2 full finalize lifecycle repair (complete)
S1R-C step0 invalid-state attribution (complete; Route B bounded bridge selected)
S1R-D fresh S1 live result (complete; M1 pass, score=1.0, sr=1.0)
```

The S1R-D fresh S1 result is recorded in:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json
```

It proves M1 / formal score-chain pass. It does not yet prove S2/M3 completion because
door joint readback, metric input dump, render/snapshot, and route-claim review are not
yet closed.

## PM Milestones

| Milestone | Question | Pass Evidence | Stop Condition |
|---|---|---|---|
| M1 formal EBench score chain | Can a real EBench run produce official score artifacts? | Live run with `episode_result.score` and matching `result_info.json`; score may be zero | If real EBench cannot produce `result_info.json`, stop oracle work and fix runner / evaluator lifecycle |
| M2 reproducible expert action | Can expert actions actually change the EBench scene through the official control interface? | Frozen action trace plus observation / readback showing expected scene or joint state change | If actions are accepted only in logs but scene state does not change, stop scoring work and fix action schema / control mapping |
| M3 defensible single-episode expert score | Can the official score, physical readback, metric inputs, and render evidence all support the same expert/oracle success? | `result_info.json` with valid nonzero `score`, plus same-run action log, metric trace, door joint readback, metric input dump, and render/snapshot | If score and physical/readback evidence disagree, or bounded Franka/native and Lift2/retarget paths both yield official zero / invalid after contract issues are excluded, close the current score route |
| M4 small-sample stability | Is the score reproducible enough to expand? | 3-5 episodes or seeds with majority passing the predeclared threshold and failures classified | If success is single-run only or failures are unstable and unclassified, do not scale; return to the dominant failure class |

## Engineering Gates

### S0: Freeze Expert Action Source

**Purpose:** Remove ambiguity about what "the expert trajectory" means.

**Required evidence:**

- EBench-executable replay JSONL or deterministic oracle route.
- Fixed task config, seed/reset contract, action dialect, control dt, termination rule, and worker id.
- SHA256 of the action source or deterministic route spec.
- Runner command and output directory.

**Stop line:** If the expert source depends on unrecorded online state, hidden simulator state, human/script mixing, or an internal LabUtopia controller that cannot be exported into an EBench runner input, stop replay work and create a deterministic oracle reconstruction plan.

### S1: Formal Score Chain Smoke

**Purpose:** Prove the runner can reach the official EBench score artifact path.

**Required evidence:**

- Real EBench server / submit / runner commands.
- `episode_result.json` or client-side episode result from server finalization.
- `result_info.json` with numeric `score` and `success_rate`.
- `action_log.jsonl` and `metric_trace.jsonl` for the same run.

**Stop line:** If two bounded attempts fail before authoritative `result_info.json` exists for infra reasons, stop expert tuning. The blocker is EBench integration / evaluator lifecycle, not oracle quality.

### S2: Franka Native Expert Under EBench Metric

**Purpose:** Prove that the native expert answer can be scored before any Lift2 retargeting.

**Required evidence:**

- Frozen Franka/native expert source from S0.
- Same-run action trace, metric inputs, initial and final door joint state.
- Official `result_info.json` score authority.

**Stop line:** If the frozen expert action is nondeterministic on the same seed, or if action scale / dt / reset pose have each been checked and the formal score remains zero / invalid, stop blind tuning and produce a failure attribution matrix.

### S3: Lift2 Oracle / Retarget Smoke

**Purpose:** Prove the official robot mouth can execute an expert-equivalent strategy.

**Required evidence:**

- Explicit mapping from Franka/task-level expert intent to Lift2/R5a action dialect.
- Readback for target, applied target, observed joints / EE, and relevant object state.
- Official `result_info.json` with score authority.

**Stop line:** Limit retarget exploration to two mapping families with at most two critical parameter variants each. If all bounded attempts fail with official zero / invalid score after control-interface issues are classified, close the current Lift2 retarget route and open a new control-contract plan instead of expanding sweeps.

### S4: Robustness Gate

**Purpose:** Upgrade a one-off score into a deliverable scoring workflow.

**Required evidence:**

- 3-5 episode / seed score table.
- Per-run `result_info.json`, command, config, action trace, metric trace, and failure category.
- Predeclared pass threshold and allowed retry budget.

**Stop line:** If failures span more than three root-cause classes or cannot be classified, do not expand to more tasks. Return to the most frequent failure class with a smaller gate.

## Claim Boundaries

Allowed now after S1R-D:

```text
stop_go_roadmap_defined=true
s0_completed=true
s1_completed=true
m1_formal_score_chain_pass=true
first_nonzero_official_score_candidate_evidence=true
expert_oracle_complete_score_claim_allowed=false
expert_oracle_score_complete=false
policy_score_claim_allowed=false
official_leaderboard_claim_allowed=false
project_no_go_claim_allowed=false
```

Allowed after M3 only:

```text
first_official_expert_score_observed=true
single_episode_score_poc=true
readback_render_metric_input_closed=true
small_sample_stability_claim_allowed=false
```

Allowed after M4 only:

```text
expert_oracle_score_workflow_ready_for_expansion=true
```

## Historical Implementation Checklist

The checklist below is the original documentation-task plan used to register the stop-go roadmap.
It is kept for traceability and should not be read as the current execution state. The current
canonical state is in the sections above and in
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json`:
S0 is complete, S1/M1 passed with Route B fresh S1 `score=1.0`, and no S2/M3 or workflow claim has been released.
S1R-A/B/B2/C/D are complete. Route B fresh S1 has already produced the M1 pass evidence; the
current next blocker is S2/M3 readback, render, metric-input, and route-claim review.

## Task 1: Register The Roadmap Evidence

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_stop_go_roadmap_20260706.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [ ] **Step 1: Create the manifest**

Use this exact status and claim boundary:

```json
{
  "stage": "EOS-2 Expert Oracle Stop-Go Roadmap",
  "status": "PLANNED_EOS2_EXPERT_ORACLE_STOP_GO_ROADMAP_NO_LIVE_NO_SCORE",
  "live_evidence": false,
  "score_claim_allowed": false,
  "expert_oracle_score_complete": false
}
```

- [ ] **Step 2: Validate JSON**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_stop_go_roadmap_20260706.json >/tmp/eos2_stop_go_roadmap.json
```

Expected: exit code `0`.

- [ ] **Step 3: Add README entry**

Add a short entry stating that this roadmap is planning evidence only. It defines M1-M4 / S0-S4 and does not release live or score claims.

## Task 2: Update PM Handoff

**Files:**
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [ ] **Step 1: Add PM-facing summary near the current conclusion**

Add this message:

```text
当前不是继续试到开门，而是按 M1-M4 阶段门推进：M1 已经通过，Route B fresh S1 在正式 EBench score chain 下产出 score=1.0；M3 还要证明 official score、door joint readback、metric input dump 和 render/snapshot 互相一致；M4 才是小样本稳定。M3 之前不能说 single-episode POC 弄好；M4 之前不能说可交付扩展。
```

- [ ] **Step 2: Preserve local no-go language**

Make clear that F2a closed only the current F-stage lower-level action branch. It does not close the project, DryingBox asset acceptance, or `Expert Oracle Score` objective.

## Task 3: Update Expert Oracle Score Plan

**Files:**
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [ ] **Step 1: Add stop-go roadmap link**

Add a section that links this plan and the roadmap manifest.

- [ ] **Step 2: Add engineering gates**

Summarize S0-S4 in Chinese with English architecture terms preserved: `result_info.json`, `episode_result.score`, `action_trace`, `metric_trace`, `Franka native expert`, `Lift2 oracle / retarget`.

- [ ] **Step 3: Preserve score authority**

State that formal score still comes only from `post_episode_process -> episode_result.score -> result_info.json`.

## Task 4: Verify Documentation

**Files:**
- Check: changed Markdown and JSON files.

- [ ] **Step 1: Validate JSON**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_stop_go_roadmap_20260706.json >/tmp/eos2_stop_go_roadmap.json
```

Expected: exit code `0`.

- [ ] **Step 2: Check Markdown whitespace**

Run:

```bash
git diff --check -- docs/superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_stop_go_roadmap_20260706.json docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/evidence_manifests/README.md docs/README.md
```

Expected: exit code `0`.

- [ ] **Step 3: Verify claim boundary terms**

Run:

```bash
rg -n "score_claim_allowed|expert_oracle_score_complete|official_leaderboard_claim_allowed|project_no_go_claim_allowed|M1|M2|M3|M4|S0|S1|S2|S3|S4" docs/superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_stop_go_roadmap_20260706.json docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Expected: output includes the no-score claim boundary and all M/S gates.

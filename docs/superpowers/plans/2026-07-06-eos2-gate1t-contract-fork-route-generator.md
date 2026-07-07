# EOS2 Gate 1T Contract-Fork Route Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After Gate 1R and Gate 1S reached a bounded no-go for the exact current contract, define and execute one bounded contract fork that tests whether an EBench-native route generator can recover handle-front reachability.

**Architecture:** Gate 1T freezes the current `EBench+Franka+LabUtopia DryingBox` evidence and does not continue local offset tuning. The primary lane is `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR`: keep Franka, the current task layout, the native DryingBox asset, and the EBench metric fixed, but replace the static mesh-open-face near route with an EBench-style `custom_motion` route made of `robot_frame` staging and `object_frame` DryingBox waypoints. Lift2 robot and task-layout changes remain separate fallback contract forks.

**Tech Stack:** LabUtopia docs, GenManip task YAML and planner/readback probe, EBench `custom_motion` task pattern, Isaac Sim 4.1, cuRobo, JSON evidence manifests, conda env `embodied-eval-os-sim-isaacsim41-genmanip-py310` for live probes and `embodied-eval-os-isaacsim41-py310` for unit tests.

---

## PM Summary

当前不是“还没试够”。Gate 1R 已经把 R1/R2/R3/R4 的预注册候选跑完，Gate 1S 也只允许一个 strategy-level 尝试并已跑完。结果都说明：当前这套 `Franka + 当前任务布局 + mesh-open-face near route` 不能把手稳定送到把手前的安全操作位。

这不是 DryingBox 全局打不开，也不是 `Expert Oracle Score` 失败。准确结论是：**当前精确定义合同已经到 bounded no-go 建议点**。如果继续，就必须改合同。Gate 1T 推荐优先改 route generator，学习 EBench 原生 `microwave` 任务的 `custom_motion` 写法：不是 replay 一个旧轨迹文件，而是在任务里写一组 `robot_frame` / `object_frame` waypoints，让 runtime 和 cuRobo 逐段现算。

2026-07-06 追加审计结论：Gate 1T-C0/C1 已经把 route 候选准备好，但 C2 不能直接把 planner-only 输出冒充 live。C2a 最初发现缺少一个可审计 runner；随后已补出最小 runner 代码并通过单元测试，状态更新为 `CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE`。C2b 已用这个 runner 真实进入 Isaac / EBench，但失败在 resolver mismatch：当时 `robot_frame` unsupported，`obj_DryingBox_01` root object-frame not found，所以不能当 route no-go。C2c 进一步闭合 resolver：`robot_frame` 成功规划 44 个 action points，`obj_DryingBox_01_handle` object-frame 成功解析，但两个 handle-frame targets 在 cuRobo 中 `MotionGenStatus.IK_FAIL`。C2d 只读审计又发现 C2c target 与 mesh/open-face handle-front 参考目标相差约 `0.1116m`，且 C2c summary 记录的是 adjusted target，不能安全反推 local 坐标。C2e resolver dump 已补齐 raw/adjusted split，C2e coordinate derivation 证明等价 local coordinate 可用，forward-check 误差约 `5.55e-17m`。为了避免混淆，唯一 live rerun 单独命名为 C2f。C2f 已跑完：等价正面目标命中，但该目标仍 `MotionGenStatus.IK_FAIL` / 0 action points / 0 executed steps。因此 C lane 按规则停止，下一步推荐 `A_LIFT2_ROBOT_CONTRACT_FORK`。

## PM Decision Ladder

| Step | Purpose | Pass Means | Fail / Stop Means | What PM Can Say |
| --- | --- | --- | --- | --- |
| 0. Frozen current contract | Freeze Gate 1R + Gate 1S evidence | Evidence exists and classifications match | Do not continue until evidence is complete | 当前精确定义合同已经到 bounded no-go 建议点。 |
| 1. Gate 1T-C0/C1 route prep | Learn EBench `microwave` custom_motion pattern and pre-register routes | 3 routes max, 0 selected live routes, no contact/score | Stop if route count, base/layout, collision, or resolver rules are changed | 下一步路线已经规范化，但还没证明可达。 |
| 2. Gate 1T-C2a runner gate | Prove there is an auditable native action-path runner | `CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE` under unit tests | No real C2b live claim until Isaac / EBench executes one selected route | runner 代码已准备好，但还不是 live 证据。 |
| 3. Gate 1T-C2b one-route live | Run exactly 1 selected native-pattern route | Runner reaches live Isaac / EBench | Resolver mismatch means no route no-go claim | C2b 证明链路跑到现场，但靶子还没解析对。 |
| 4. Gate 1T-C2c resolver closure | Close native `custom_motion` resolver with handle object-frame | Resolver passes and route produces action/readback | IK failure is useful only if target equivalence is later proven | C2c 已经不是没跑；它卡在 planner reachability。 |
| 5. Gate 1T-C2d target-frame equivalence | Compare C2c resolved target against intended handle-front target | Equivalent target; C2c IK can stop C lane | Not equivalent; allow exactly one C2e rerun | 先确认“打的靶子是不是同一个靶子”。 |
| 6. Gate 1T-C2e resolver dump / coordinate proof | Capture raw/adjusted target split and derive equivalent local coordinates | Coordinates reconstruct mesh/open-face handle-front target within `0.01m` | Coordinates underdetermined; stop before live | 先把坐标算准，不直接跑。 |
| 7. Gate 1T-C2f equivalent-target single live | Run one resolver-closed equivalent-target route | `PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT` | Equivalent target still `IK_FAIL` / 0 action points; stop C lane | 已失败，C lane 停止。 |
| 8. Gate 2/3 contact-retention | Verify contact and close-hold retention | Contact/overlap/retention positive | No micro-pull and no score | 能不能抓住/保持住在这里判定。 |
| 9. Gate 4/5 door-score | Verify micro-pull opens joint and EBench metric scores | Door angle reaches metric and `Expert Oracle Score` recorded | Score remains blocked or fails with evidence | 到这里才算评测口径真正闭环。 |

最早能宣布“弄不好”的层级已经明确：Gate 1S 之后可以说**当前精确定义合同**弄不好；C2b 只能说 resolver mismatch，不是 C lane no-go；C2c 只能说 resolver-closed handle-frame target IK 失败；C2d 证明 C2c target 不等价；C2e 证明等价坐标已可推导；C2f 在等价目标下仍失败。因此现在可以说**当前 Franka/current-layout/native-route-generator 合同**弄不好。Gate 5 pass 之前仍不能说 `Expert Oracle Score` 已经成功或失败。

## Frozen Evidence

Gate 1T 只能基于以下 frozen evidence 启动：

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_gate1r_layout_live_20260706/summary_compact.json
classification=BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS

docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_strategy_review_20260706.json
max_selected_live_strategy_count=1

docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_selected_strategy_live_20260706/summary_compact.json
classification=BLOCKED_GATE1S_SELECTED_STRATEGY_NO_NEAR_REACHABILITY
bounded_no_go_recommended=true
```

Allowed wording:

```text
The exact current EBench+Franka+LabUtopia DryingBox contract has not produced a
scoring-eligible expert route through Gate 1R plus one strategy-level Gate 1S
attempt. Gate 2 and Expert Oracle Score remain blocked for this contract.
```

Disallowed wording:

```text
DryingBox cannot be opened globally.
LabUtopia assets cannot be evaluated in EBench.
Expert Oracle Score failed.
Official EBench score failed.
All robots, layouts, or route generators are impossible.
```

## Contract Fork Priority

| Lane | Priority | What Changes | What Stays Fixed | When To Use |
| --- | --- | --- | --- | --- |
| `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR` | 1 | Route generator and waypoint authoring style | Franka, current task layout, native DryingBox, EBench metric | Default next lane. Tests whether the current static near target is the wrong route shape. |
| `A_LIFT2_ROBOT_CONTRACT_FORK` | 2 | Robot/action/retarget contract | Native DryingBox, EBench metric | Use only after C fails or product chooses official robot compatibility first. Must not reuse Franka joint actions. |
| `B_TASK_LAYOUT_CONTRACT_FORK` | 3 | Robot-object/table relative layout | Native DryingBox, EBench metric | Adapter diagnostic only. Must document exactly what layout changed. |
| `W_FINAL_BOUNDED_NO_GO` | stop lane | No new live run | All evidence frozen | Use if C/A/B are rejected or fail under their own pre-registered caps. |

## Gate 1T Stop Rules

Gate 1T is not another local sweep:

```text
max_native_pattern_routes=3
max_selected_live_route_count=1
```

The selected live route must produce:

```text
PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT
```

meaning bridge/staging/near all have action points and replay readback reaches the `0.02 rad` joint tolerance. Otherwise classify:

```text
BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY
```

and stop this lane only after target-frame equivalence has been proven by C2d or by the single allowed C2e equivalent-target rerun. Do not continue by changing offset, normal sign, wrist orientation, reset seed, Franka base, collision toggles, or debug-only planner ignore lists in the same lane.

Before that live route can run, Gate 1T-C2a must pass the runner capability gate. The first audit classification was:

```text
BLOCKED_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_MISSING
```

The current code status is:

```text
CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE
```

This is no longer the latest route state; it remains the runner code-readiness baseline. The repo now has a unit-tested runner that consumes a selected native route, asks the planner for trajectory action points, builds `joint_position` chunks, and exercises the `step_chunk` contract under fake-client tests. Do not substitute planner-only `/plan_object_frame_waypoints` output or the current `online_open_door_oracle_probe.py` diagnostics for live evidence. Current live evidence is C2b resolver mismatch, C2c resolver-closed IK block, and C2d target-frame equivalence audit.

## File Responsibilities

- `docs/superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md`: this plan and stop rules.
- `docs/superpowers/plans/2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md`: bounded C2d/C2e follow-up plan.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_contract_fork_review_20260706.json`: structured review manifest for PM and engineering handoff.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/result_compact.json`: C2c resolver-closed live result.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2d_target_frame_equivalence_audit_20260706.json`: C2d read-only target-frame equivalence audit.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_resolver_dump_live_20260706/result_compact.json`: C2e live resolver dump; proves raw/adjusted target split exists.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_coordinate_derivation_20260706.json`: C2e coordinate proof; authorizes one C2f equivalent-target live attempt.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_route_candidates_20260706.json`: C2f single allowed equivalent-target route.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_live_20260706/result_compact.json`: C2f single live result; stops C lane.
- `docs/labutopia_lab_poc/evidence_manifests/README.md`: evidence index and PM summary.
- `docs/labutopia_lab_poc/aan_consumer_handoff.md`: next-engineer handoff and claim boundary.
- `docs/labutopia_lab_poc/expert_oracle_score_plan.md`: score status; remains blocked until Gate 1T or a later fork produces a scoring-eligible expert route.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/mobile_manip/val_train_20p/microwave.yml`: EBench native `custom_motion` reference.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`: current DryingBox task contract.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/object_frame_waypoint_planner.py`: current planner helper; by default it matches `custom_motion` object-list semantics.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`: live probe entry point for route readback.

## Task 1: Freeze Gate 1S And Publish Gate 1T Review Manifest

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_contract_fork_review_20260706.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [ ] **Step 1: Validate frozen JSON evidence**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_gate1r_layout_live_20260706/summary_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_strategy_review_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_selected_strategy_live_20260706/summary_compact.json >/dev/null
python - <<'PY'
import json
gate1r = json.load(open("docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_gate1r_layout_live_20260706/summary_compact.json", encoding="utf-8"))
gate1s = json.load(open("docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_selected_strategy_live_20260706/summary_compact.json", encoding="utf-8"))
assert gate1r["classification"] == "BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS"
assert gate1s["classification"] == "BLOCKED_GATE1S_SELECTED_STRATEGY_NO_NEAR_REACHABILITY"
assert gate1s["decision"]["bounded_no_go_recommended"] is True
assert gate1s["decision"]["gate2_contact_allowed"] is False
assert gate1s["decision"]["expert_oracle_score_allowed"] is False
print("gate1t_frozen_evidence_ok")
PY
```

Expected:

```text
gate1t_frozen_evidence_ok
```

- [ ] **Step 2: Create Gate 1T review manifest**

Create `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_contract_fork_review_20260706.json` with status:

```text
PREPARED_GATE1T_CONTRACT_FORK_REVIEW_NOT_LIVE_EVIDENCE
```

The manifest must include:

```text
primary lane: C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR
max_native_pattern_routes=3
max_selected_live_route_count=1
pass classification: PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT
fail classification: BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY
```

- [ ] **Step 3: Update PM/handoff/score docs**

Add a latest-status note to:

```text
docs/labutopia_lab_poc/evidence_manifests/README.md
docs/labutopia_lab_poc/aan_consumer_handoff.md
docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Required Chinese wording:

```text
Gate 1R + Gate 1S 已经把当前精确定义合同推进到 bounded no-go 建议点。下一步不是继续扫 offset，而是新开 Gate 1T contract fork，优先验证 C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR。Gate 2/contact/micro-pull/Expert Oracle Score 在新的 Gate 1 pass 之前继续 blocked。
```

## Task 2: Extract Native EBench Oracle Pattern

**Files:**
- Read: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/mobile_manip/val_train_20p/microwave.yml`
- Read: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/object_frame_waypoint_planner.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_oracle_pattern_extraction_20260706.json`

- [ ] **Step 1: Inspect EBench `microwave` custom_motion**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
rg -n "type: custom_motion|type: object_frame|type: robot_frame|type: pending|rel_object_uid: microwave|grasp:" configs/tasks/ebench/mobile_manip/val_train_20p/microwave.yml
```

Expected: output includes `custom_motion`, `object_frame`, `robot_frame`, `pending`, and `rel_object_uid: microwave`.

- [ ] **Step 2: Confirm current helper semantics**

Run:

```bash
rg -n "_find_scene_object|object_list|articulation_list|RelativeObjectNotFoundError" genmanip/core/evaluator/object_frame_waypoint_planner.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
```

Expected: current helper resolves `object_frame` from `scene.object_list`; articulation-part resolver is not part of this native-compatible lane.

- [ ] **Step 3: Write extraction manifest**

Create `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_oracle_pattern_extraction_20260706.json` with:

```json
{
  "schema_version": 1,
  "stage": "EOS-2 Gate 1T-C0 Native Oracle Pattern Extraction",
  "status": "PREPARED_NATIVE_PATTERN_EXTRACTION_NOT_LIVE_EVIDENCE",
  "source_reference": "configs/tasks/ebench/mobile_manip/val_train_20p/microwave.yml",
  "required_primitives": ["custom_motion", "object_frame", "robot_frame", "pending_grasp"],
  "dryingbox_frame_contract": {
    "native_compatible_primary": "rel_object_uid=obj_DryingBox_01",
    "not_in_this_lane": "articulation-part object_frame resolver for obj_DryingBox_01_handle",
    "reason": "EBench native custom_motion object_frame semantics are object-list based; articulation-part support would be a separate contract fork."
  },
  "claim_boundary": "Pattern extraction only; not live reachability, contact, micro-pull, Expert Oracle Score, policy score, or official score."
}
```

## Task 3: Pre-Register Native-Pattern Route Candidates

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_candidates_20260706.json`
- Modify later, if execution is selected: GenManip diagnostic config or probe arguments only for the selected route.

- [ ] **Step 1: Create route candidate manifest**

Create up to three native-pattern routes. Each route must include:

```text
robot_frame staging waypoint
object_frame approach waypoint using rel_object_uid=obj_DryingBox_01
object_frame handle-front near waypoint using rel_object_uid=obj_DryingBox_01
grasp=false for reachability gate
contact=false
score=false
```

The manifest must explicitly say:

```text
No articulation-part resolver is added in Gate 1T-C.
No Franka base/layout change is allowed in Gate 1T-C.
No self-collision or task-collision disable is allowed.
```

- [ ] **Step 2: Validate candidate cap**

Run:

```bash
python - <<'PY'
import json
path = "docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_candidates_20260706.json"
data = json.load(open(path, encoding="utf-8"))
assert data["max_native_pattern_routes"] == 3
assert len(data["routes"]) <= 3
for route in data["routes"]:
    assert route["contact_enabled"] is False
    assert route["score_enabled"] is False
    assert route["robot_base_change_allowed"] is False
print("gate1t_route_candidate_cap_ok")
PY
```

Expected:

```text
gate1t_route_candidate_cap_ok
```

### 2026-07-06 Task 2/3 Execution Note

Gate 1T-C0 and Gate 1T-C1 have been prepared:

```text
pattern_extraction=docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_oracle_pattern_extraction_20260706.json
route_candidates=docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_candidates_20260706.json
selected_live_route_count=0
```

C0 confirms that EBench `microwave` uses native `custom_motion` with `object_frame`,
`robot_frame`, and `pending` primitives. It also freezes the helper boundary:
Gate 1T-C uses `rel_object_uid=obj_DryingBox_01` because the native-compatible
planner resolver reads `scene.object_list`; `obj_DryingBox_01_handle`
articulation-part support is not part of this lane.

C1 pre-registers exactly three routes:

```text
C1_ROOT_DIRECT_NATIVE_PATTERN
C2_ROOT_STAGED_CORRIDOR_NATIVE_PATTERN
C3_REVERSE_REACHABILITY_ROOT_PATTERN
```

All three keep Franka, current task layout, native DryingBox, and EBench metric
fixed. `contact_enabled=false`, `score_enabled=false`, `grasp=false` for every
Gate 1 waypoint, and `selected_live_route_count=0`. These files are prepared
inputs only; they do not claim live reachability, contact, micro-pull, door open,
Expert Oracle Score, policy score, or official score.

Supersession note, 2026-07-06: C2b live later proved that the C1
`rel_object_uid=obj_DryingBox_01` root assumption does not satisfy current
native `custom_motion` resolver semantics, because the articulated root is not
in `scene.object_list`. C2c switched to the resolvable
`obj_DryingBox_01_handle`; that closed resolver lookup, but C2d then showed
target-frame equivalence is unproven. Treat this Task 2/3 note as historical
route-prep evidence, not the current stop condition.

## Task 4: Gate 1T-C2a Runner Capability Gate, Then C2b One-Route Live

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_live_20260706/`

- [x] **Step 1: Audit runner capability before any live route**

Use the audit manifest:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json
```

Current status:

```text
CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE
```

Expected consequence:

```text
gate1t_c2b_live_allowed_now=false
```

Historical note: this was true at C2a. C2b has since been run and is recorded as
`LIVE_BLOCKED_RESOLVER_MISMATCH_NOT_ROUTE_NO_GO`; C2c has also been run and is
recorded as
`LIVE_BLOCKED_REACHABILITY_AFTER_RESOLVER_CLOSURE_TARGET_EQUIVALENCE_UNPROVEN`.
The next engineering task is now C2d/C2e equivalence closure, not C2b.

- [x] **Step 2: Implement or identify the minimal native action-path runner**

The runner must satisfy all of the following before C2b is allowed:

```text
consume exactly one selected route
resolve robot_frame and object_frame waypoints like EBench custom_motion
record resolved targets and planner status per waypoint
convert planned trajectories to EBench joint_position action payloads
execute through /step_chunk or equivalent Ray eval step path
persist controller/readback debug, metric trace, result_info.json, run_id, commands, and artifact paths
```

Expected before live:

```text
gate1t_c2_native_action_path_runner_ready=true
```

- [x] **Step 3: Select exactly one route**

The selected route must be copied from `eos2_gate1t_native_pattern_route_candidates_20260706.json`.

Expected:

```text
selected_route_for_next_live=C1_ROOT_DIRECT_NATIVE_PATTERN
selected_live_route_count=0 until the real live command runs
```

- [x] **Step 4: Write server/submit/runner command files**

Create:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_live_20260706/server.command.txt
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_live_20260706/submit.command.txt
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_live_20260706/runner.command.txt
```

The submit step must load the current formal task config:

```text
ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
```

The runner uses `--run-id eos2_gate1t_c2b_c1_root_direct_native_pattern_20260706_0001`, connects to the prepared server on port `18107`, selects only `C1_ROOT_DIRECT_NATIVE_PATTERN`, and writes `summary.json` plus `trace.jsonl`. It must not enable contact, close-hold, micro-pull, or score flags.

- [ ] **Step 5: Run live readback**

Use env:

```bash
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
```

Stop the server after the probe. Record the port and verify it is free after shutdown.

- [ ] **Step 6: Write compact result**

If the selected route reaches near:

```json
{
  "classification": "PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT",
  "gate2_contact_allowed": true,
  "expert_oracle_score_allowed": false
}
```

If it fails:

```json
{
  "classification": "BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY",
  "gate2_contact_allowed": false,
  "expert_oracle_score_allowed": false,
  "next_allowed_forks": ["A_LIFT2_ROBOT_CONTRACT_FORK", "B_TASK_LAYOUT_CONTRACT_FORK", "W_FINAL_BOUNDED_NO_GO"]
}
```

## Task 5: Decide Gate 2 Eligibility Or Fork Again

**Files:**
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [ ] **Step 1: If Gate 1T passes, document Gate 2 eligibility**

Append:

```text
Gate 1T-C produced PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT. Gate 2 contact planner/readback may start from this selected route. This still does not claim close-hold, stable grasp, micro-pull, door opened, Expert Oracle Score, policy score, or official score.
```

- [ ] **Step 2: If Gate 1T fails, document next fork**

Append:

```text
Gate 1T-C did not recover handle-front near reachability under the current Franka/current-layout contract. Do not continue native-pattern route tuning in this lane. The next allowed choices are A_LIFT2_ROBOT_CONTRACT_FORK, B_TASK_LAYOUT_CONTRACT_FORK, or W_FINAL_BOUNDED_NO_GO.
```

## Verification

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_contract_fork_review_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json >/dev/null
rg -n "Gate 1T|C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR|bounded no-go|Expert Oracle Score.*blocked|PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT|BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY|BLOCKED_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_MISSING|runner capability" \
  docs/superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_contract_fork_review_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json
git diff --check -- \
  docs/superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_contract_fork_review_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json
```

Expected:

```text
json validation exits 0
rg finds Gate 1T, C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR, bounded no-go, and both Gate 1T classifications
git diff --check exits 0
```

## Self-Review

Spec coverage:

- The plan preserves Gate 1R and Gate 1S as frozen evidence.
- It avoids endless trial by setting route and live-run caps.
- It adds C2a runner capability as a hard gate before C2b live readback.
- It prioritizes EBench-native route generation before changing robot or task layout.
- It keeps `Expert Oracle Score` blocked until a scoring-eligible expert route exists.

Placeholder scan:

- No `TBD`, `TODO`, or open-ended sweep is present.
- Every stage has a pass/fail classification and explicit stop rule.

Type consistency:

- `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR`, `A_LIFT2_ROBOT_CONTRACT_FORK`, and `B_TASK_LAYOUT_CONTRACT_FORK` match the review manifest.
- Gate 1T classification strings match the verification command.

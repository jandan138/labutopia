# EOS2 Gate 1T-C2d Target-Frame Equivalence Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide, without open-ended route tuning, whether the `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR` lane can still recover handle-front reachability after C2c resolver closure.

**Architecture:** C2d is a read-only target-frame audit: compare live C2c handle-frame targets against the intended mesh/open-face handle-front world targets before running anything else. If the targets are equivalent, C2c's IK failure is enough to stop C lane. If they are not equivalent, C2e first captures raw resolver and adjusted-target transforms, derives equivalent local coordinates, and only then authorizes one resolver-closed equivalent-target live rerun. The live rerun is named C2f so that diagnostic coordinate proof and actual route execution are not mixed.

**Tech Stack:** LabUtopia evidence manifests, GenManip C2 native action-path runner, EBench `custom_motion` object-frame semantics, Isaac Sim 4.1 live evidence, cuRobo planner debug, JSON manifests.

---

## PM Summary

现在不是“再试几个点”。C2c 已经把前一个 resolver 问题修正到 live 层：`robot_frame` 能规划出 44 个 action points，`obj_DryingBox_01_handle` 也能被 `object_frame` resolver 找到。真正失败点变成两个 handle target 的 `MotionGenStatus.IK_FAIL`。

但 C2c 又暴露出一个新的边界：handle frame 的 local `Y+` 在 live 里映射到了 world `X+`，而我们之前认为的正面接近线主要沿 world `Y`。进一步看代码发现，planner record 记录的是经过 `adjust_target_pose_by_embodiment` 后的 target，不是纯 raw `pose_frame_to_world`。所以 C2c 不能直接判定“C route generator 整体不行”，也不能直接从当前 summary 反推出 C2e 坐标。先要确认它是不是打到了正确的把手正前方目标，并补齐 raw/adjusted target dump。

## Decision Ladder

| Stage | Purpose | Pass Means | Fail / Stop Means | PM Wording |
| --- | --- | --- | --- | --- |
| C2d target-frame equivalence audit | 不跑仿真，只比较 C2c resolved world target 和 intended handle-front target 是否一致 | 目标等价；C2c IK failure 可升级为 C lane no-go 证据 | 目标不等价；C2c 只能算 target-frame mismatch | 先确认“打的靶子是不是同一个靶子”。 |
| C2e resolver-dump derivation | 先补 raw frame / pre-adjust / adjusted target dump，推导等价 local 坐标 | 坐标能在 adjusted target 下复刻 intended world target，允许 C2f live | 坐标仍 underdetermined，停止 live rerun | 先把坐标算准，不直接跑。 |
| C2f equivalent-target rerun | 只允许一次，用推导出的 handle-frame local 坐标复刻 intended world target | 生成 action points 且 readback 达 0.02 rad，进入 Gate 2 contact | 已证明目标等价仍 IK_FAIL / 0 action points，则停 C lane | 这一步后就能判断 C route generator 是否值得继续。 |
| Gate 2 / 3 contact-retention | 验证夹爪真的接触并保持把手 | 允许 micro-pull | retention 失败则不能算分 | 到这里才判断“抓没抓住”。 |
| Gate 4 / 5 Expert Oracle Score | 验证微拉门和 EBench metric | `Expert Oracle Score` 可记录 | score 失败才是评分器 / oracle 问题 | 到这里才算评测口径闭环。 |

## File Responsibilities

- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/summary.json`: authoritative C2c live summary.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/result_compact.json`: compact C2c PM / handoff result.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2d_target_frame_equivalence_audit_20260706.json`: read-only C2d audit result and C2e entry condition.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_resolver_dump_live_20260706/result_compact.json`: C2e resolver-dump live result.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_coordinate_derivation_20260706.json`: C2e no-blind-rerun coordinate derivation result.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_route_candidates_20260706.json`: C2f exactly-one route manifest.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_live_20260706/`: C2f command package for the single equivalent-target live rerun.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_candidate_preflight_live_20260705_primary/summary_compact.json`: intended handle-front mesh/open-face target reference.
- `docs/labutopia_lab_poc/aan_consumer_handoff.md`: next-engineer and PM handoff.
- `docs/labutopia_lab_poc/expert_oracle_score_plan.md`: Expert Oracle Score remains blocked until Gate 2/3/4 pass.
- `docs/labutopia_lab_poc/evidence_manifests/README.md`: evidence index.

## Task 1: Record C2c Live Result And Target-Frame Audit

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/result_compact.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2d_target_frame_equivalence_audit_20260706.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/selection_manifest.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/README.md`

- [x] **Step 1: Verify C2c live summary**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/summary.json >/dev/null
python - <<'PY'
import json
p="docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/summary.json"
s=json.load(open(p))
print(s["classification"], s["executed_steps"], s["blockers"])
for r in s["planner_records"]:
    print(r["label"], r["plan_success"], r["trajectory_point_count"], r.get("failure_reason"), r.get("target_world_translation"), (r.get("planner_debug") or {}).get("status"))
PY
```

Expected:

```text
BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY 0 [...]
robot_frame_staging_microwave_style True 44 None [...]
handle_object_staging_085 False 0 motion_planning_failed [...] MotionGenStatus.IK_FAIL
handle_object_near_045 False 0 motion_planning_failed [...] MotionGenStatus.IK_FAIL
```

- [x] **Step 2: Compare C2c target to mesh/open-face reference**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python - <<'PY'
import json, math
c2c=json.load(open("docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/summary.json"))
mesh=json.load(open("docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_candidate_preflight_live_20260705_primary/summary_compact.json"))
records={r["label"]:r for r in c2c["planner_records"]}
near=records["handle_object_near_045"]["target_world_translation"]
ref=mesh["first_candidate"]["approach_near_target_world"]
dist=math.sqrt(sum((near[i]-ref[i])**2 for i in range(3)))
print("c2c_near=", near)
print("mesh_approach_near=", ref)
print("distance_m=", dist)
PY
```

Expected:

```text
distance_m= 0.11155819044435669
```

- [x] **Step 3: Write compact C2c and C2d audit manifests**

The compact result must say:

```text
resolver_closure_passed=true
reachability_failed_after_resolution=true
target_equivalence_unproven=true
next_stage=Gate 1T-C2d Target-Frame Equivalence Audit
```

The C2d audit must say:

```text
equivalence_pass=false
safe_c2e_coordinates_available_from_current_summary=false
next_stage=Gate 1T-C2e Resolver-Dump Equivalent-Target Derivation
```

- [x] **Step 4: Validate JSON**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/result_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2d_target_frame_equivalence_audit_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/selection_manifest.json >/dev/null
```

Expected: exit `0`.

## Task 2: Prepare C2e Coordinates Before The Single Allowed Rerun

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_coordinate_derivation_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_route_candidates_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_live_20260706/README.md`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_live_20260706/server.command.txt`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_live_20260706/submit.command.txt`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_equivalent_target_live_20260706/runner.command.txt`

- [ ] **Step 1: Capture raw resolver and adjusted target transforms**

Before a live rerun, add or run a diagnostic that records, per waypoint:

```text
frame_in_world.translation
frame_in_world.orientation
raw_pose_frame_to_world.translation
raw_pose_frame_to_world.orientation
adjusted_target.translation
adjusted_target.orientation
adjust_target_pose_by_embodiment source/version
```

This can be code instrumentation or a no-action diagnostic planner call. It must not execute contact, close-hold, micro-pull, or score.

Current result: completed by `eos2_gate1t_c2e_resolver_dump_live_20260706/summary.json` and compacted in `result_compact.json`. The dump includes `target_resolver_debug.frame_in_world_translation`, `frame_in_world_orientation`, `raw_target_world_translation`, `raw_target_world_orientation`, `adjusted_target_world_translation`, and `adjusted_target_world_orientation`.

- [x] **Step 2: Attempt equivalent handle-frame local coordinate derivation from current evidence**

Use the raw/adjusted transform dump and target world reference. The route must target the mesh/open-face `approach_near_target_world` and `contact_target_world` within `0.01m` after the same `adjust_target_pose_by_embodiment` step; if the full raw-to-adjusted transform cannot be reconstructed from live evidence, do not run live. Write:

```text
status=BLOCKED_C2E_EQUIVALENT_TARGET_COORDINATES_UNDERDETERMINED
```

and stop C route execution without starting Isaac.

Current result: status is
`PASS_C2E_EQUIVALENT_TARGET_COORDINATES_DERIVED_READY_FOR_C2F_SINGLE_LIVE`. The derived `approach_near` local translation is `[-0.061955757838629166, -0.020816618383194208, 1.1611298411651205e-07]`, and the forward reconstruction error is approximately `5.55e-17m`. Orientation is deliberately scoped: C2f preserves the EBench-native local orientation `[0.7071, 0.0, 0.0, 0.7071]`, whose adjusted world orientation matches C2e live exactly but differs by `90deg` from the older mesh-open-face runtime orientation. Therefore C2f can stop the current native-route orientation contract if it fails, but it cannot prove every possible gripper orientation at that position is unreachable.

- [x] **Step 3: Register exactly one C2f route**

Route constraints:

```text
route_id=C1_RESOLVER_CLOSED_EQUIVALENT_TARGET_NATIVE_PATTERN
selected_live_route_count=0
max_selected_live_route_count=1
robot=Franka
task_layout=current franka_poc/level1_open_door.yml
asset=LabUtopia native DryingBox
metric=EBench check_joint_angle on obj_DryingBox_01 RevoluteJoint
contact_enabled=false
close_hold_enabled=false
micro_pull_enabled=false
score_enabled=false
```

- [x] **Step 4: Prepare C2f live commands on a fresh port**

Use a unique run id and do not touch `8087`:

```text
run_id=eos2_gate1t_c2f_equivalent_target_20260706_0001
port=18110
ray_tmpdir=/tmp/gm_c2f_18110
```

- [x] **Step 5: Run C2f once**

Run the same C2 native action-path runner used by C2c. The only allowed difference is the equivalent-target route manifest. Do not add offsets, route variants, collision toggles, robot base changes, or layout changes.

- [x] **Step 6: Classify C2f**

Pass:

```text
PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT
gate2_contact_allowed=true
expert_oracle_score_allowed=false
```

Fail:

```text
BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY
stop_C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR=true
next_options=A_LIFT2_ROBOT_CONTRACT_FORK | B_TASK_LAYOUT_CONTRACT_FORK | W_FINAL_BOUNDED_NO_GO
```

Current result: C2f failed with the fail classification above. Evidence:
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_live_20260706/result_compact.json`.
The equivalent target reached the intended adjusted world translation, but cuRobo returned
`MotionGenStatus.IK_FAIL` for `handle_object_approach_near_equivalent_035`, so C lane is stopped.

## Task 3: Update PM And Handoff Docs

**Files:**
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md`

- [x] **Step 1: Replace stale C2b/C2c prepared wording**

Docs must say C2b is live but resolver-mismatched; C2c is live, resolver-closed, and IK-failed with target equivalence unproven.

- [x] **Step 2: Add the bounded stop ladder**

Docs must say:

```text
C2d audit first.
If equivalent, C lane can stop from C2c.
If not equivalent, first derive equivalent-target coordinates from raw/adjusted resolver dump.
If C2e coordinates remain underdetermined, stop before live rerun.
If coordinates are proven equivalent, allow exactly one C2f equivalent-target rerun.
If C2f fails after equivalence is proven, stop C lane and move to A/B/W.
Expert Oracle Score remains blocked until Gate 2/3/4 pass.
```

- [ ] **Step 3: Verify docs and JSON**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/result_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2d_target_frame_equivalence_audit_20260706.json >/dev/null
git diff --check -- docs/labutopia_lab_poc docs/superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md docs/superpowers/plans/2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md
```

Expected: exit `0`.

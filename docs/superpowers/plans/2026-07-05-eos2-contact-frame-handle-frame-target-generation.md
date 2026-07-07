# EOS-2 Contact-Frame Handle-Frame Target Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 5K-A contact-retention gap tradeoff into a reviewable Task 5L stage that generates DryingBox handle/contact-frame waypoints in the same family as EBench `microwave` manual experts.

**Architecture:** Keep the current GenManip online probe as the execution harness, but move candidate design away from one-off absolute IK targets and old trajectory replay. First generate a prepared manifest from 5K-A tail contact telemetry; then run exactly one conservative live candidate; only retention-positive evidence can unlock micro-pull or score work.

**Tech Stack:** LabUtopia docs, GenManip `online_open_door_oracle_probe.py`, Isaac Sim 4.1, cuRobo `MotionGen.plan_single`, EBench / GenManip task YAML, JSON evidence manifests, pytest, conda env `embodied-eval-os-sim-isaacsim41-genmanip-py310`.

---

## Multi-Agent Review Result

Technical review verdict: the `microwave` reference claim is accurate with one wording constraint. It should be phrased as task-level manual `custom_motion` waypoints plus runtime cuRobo planning. The YAML includes `object_frame` waypoints relative to `microwave` and also `robot_frame` staging waypoints. Asset metadata contains `skills.open_door.skill_trajectory`, but the audited microwave task path does not use that asset-level trajectory as the direct replay source.

PM review verdict: the detailed docs already contain the key facts, but the current-status sections need a short bridge explaining why the next DryingBox direction is `custom_motion`-style waypoint generation, not direct trajectory replay.

## Evidence Boundary

Task 5K-A evidence:

- Source compact manifest: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`
- Classification: `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`
- Positive signal: post-replay replan succeeded; selected waypoint was `x_m002_ori_z_p02`; generated `40` executable action points; close-hold ran `15` steps and reached joint target with about `7.25e-05 rad` final error.
- Hard boundary: `retention_pass=false`; tail bilateral overlap, required-role near, and required-role PhysX contact are all `0`; tail classification is `AABB_OUTSIDE_CONTACT_FRAME` for all `15` records.
- Gap reading: 5K-A improves world Y gap by about `1.8mm` versus 5J-F but worsens world X gap by about `0.6mm`; versus 5J-A it improves X and worsens Y. This is a contact-frame tradeoff, not a stable grasp.

EBench `microwave` reference:

- EBench has a microwave task, for example `configs/tasks/ebench/mobile_manip/test_mini/microwave.yml`.
- The task uses manual `custom_motion`, not direct asset-level `skill_trajectory` replay.
- The YAML contains `object_frame` targets relative to `microwave` and `robot_frame` staging targets.
- `custom_motion.py` converts those targets through `pose_frame_to_world`, calls `embodiment.plan_pose`, then cuRobo `MotionGen.plan_single` generates an interpolated joint trajectory.
- The task score is checked by metric/goal logic, including articulation status ranges and object relations, rather than by assuming the trajectory itself is success.

DryingBox implication: 5L should encode relative handle/contact targets, then prove planning, execution, readback, and retention. It must not claim stable grasp, micro-pull readiness, door opening, `Expert Oracle Score`, policy score, official score, or full task completion until the evidence explicitly supports those claims.

## File Responsibilities

- `docs/labutopia_lab_poc/expert_oracle_score_plan.md`: PM-facing EOS status and no-claim boundaries.
- `docs/labutopia_lab_poc/aan_consumer_handoff.md`: cross-team handoff status and next operating procedure.
- `docs/labutopia_lab_poc/evidence_manifests/README.md`: evidence index and claim boundary for each run.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`: candidate generation, live probe, replay, retention telemetry.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`: focused unit tests for candidate generation and summary guards.

## Acceptance Rules

- Prepared manifest is allowed to claim only `PREPARED_REVIEW`, not live success.
- Live evidence is allowed to advance only if `submit_exit=0`, `probe_exit=0`, selected candidate is logged, server port is released, and summary writes a compact manifest.
- A retention-positive run must show `retention_pass=true`, nonzero tail bilateral overlap, nonzero required-role near, and nonzero required-role PhysX contact.
- If any retention field is missing or false, the status remains blocked and the plan must not mention stable grasp, micro-pull readiness, door-open, `Expert Oracle Score`, policy score, official score, or full task completion.

### Task 1: Freeze 5L Claim Boundary In LabUtopia Docs

**Files:**
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/README.md`

- [x] **Step 1: Add PM bridge text after the 5K-A current-status block**

Use this wording in both the handoff and oracle plan, adapted to local flow:

```markdown
EBench `microwave` 的参考实现给了下一步方向：它也不是直接 replay 资产里的
`skill_trajectory`，而是在 task YAML 中写 task-level manual `custom_motion` waypoints，
其中既有相对微波炉的 `object_frame` 目标，也有 `robot_frame` staging；runtime 再把这些点
转成 world/robot pose，并通过 cuRobo 在线生成 joint trajectory。对 PM 来说，这意味着
DryingBox 的 oracle 不应继续围绕“一个旧轨迹能不能照抄”打转，而应进入 Task 5L：用
handle/contact frame 生成候选目标，先做 prepared manifest review，再只跑一个保守 live
候选。
```

- [x] **Step 2: Add evidence-index boundary text after the 5K-A row**

Use this exact boundary:

```markdown
当前下一阶段计划是 Task 5L `contact-frame / handle-frame target generation`。
该阶段采用 EBench `microwave` 的同类思路：用 task-level manual `custom_motion`
waypoints、object-frame / robot-frame staging 和 cuRobo runtime planning 生成可执行轨迹，
而不是 replay 资产里的旧 `skill_trajectory`。它的输入是 5K-A 暴露出的 contact-frame
gap tradeoff；它的输出先是 prepared manifest 和单候选 live evidence。只有 retention、
required-role near/overlap 和 required-role PhysX contact 同时通过后，才允许进入
micro-pull 或 score。
```

- [x] **Step 3: Verify docs do not overclaim**

Run:

```bash
git diff --check docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/evidence_manifests/README.md docs/README.md
```

Expected: command exits `0` and prints no whitespace errors.

### Task 2: Add A 5L Prepared Candidate Contract

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_review_20260705_5l_candidates.json`

- [x] **Step 1: Add a focused test for 5K-A right-finger gap input**

Append this test near `test_build_contact_frame_recovery_candidates_from_pre_close_frame_uses_x_and_y_gap`:

```python
def test_build_contact_frame_recovery_candidates_from_5k_a_right_gap_contract():
    frame = {
        "available": True,
        "required_role_states": {
            "panda_rightfinger": {
                "available": True,
                "near": False,
                "overlap": False,
                "signed_axis_gap_m": [0.084393376008, 0.067267486749, 0.0],
            },
        },
    }

    candidates = probe.build_contact_frame_recovery_candidates_from_pre_close_frame(
        frame,
        base_contact_offset_x_m=-0.005,
        base_center_offset_y_m=0.0,
        base_center_offset_z_m=-0.006,
        base_orientation_offset_z_deg=2.0,
        role="panda_rightfinger",
        scale_factors=(0.25,),
        x_clearance_margin_m=0.0,
        y_clearance_margin_m=0.0,
        max_x_shift_m=0.012,
        max_y_shift_m=0.012,
        orientation_y_offsets_deg=(0.0,),
    )

    assert candidates == [
        {
            "contact_offset_x_m": 0.007,
            "center_offset_y_m": 0.012,
            "center_offset_z_m": -0.006,
            "orientation_offset_z_deg": 2.0,
            "orientation_offset_y_deg": 0.0,
            "source_role": "panda_rightfinger",
            "source_signed_axis_gap_m": [0.084393376008, 0.067267486749, 0.0],
            "x_shift_m": 0.012,
            "y_shift_m": 0.012,
        }
    ]
```

- [x] **Step 2: Run the focused candidate tests**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "contact_frame_recovery_candidates" -q
```

Expected: all selected tests pass. If the new test fails because the function does not preserve the 5K-A source gap or clamping values, update only `build_contact_frame_recovery_candidates_from_pre_close_frame` and rerun the same command.

- [x] **Step 3: Write the prepared manifest**

Create `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_review_20260705_5l_candidates.json` with this structure:

```json
{
  "status": "PREPARED_REVIEW_NOT_LIVE_EVIDENCE",
  "task": "EOS-2 Task 5L contact-frame / handle-frame target generation",
  "source_evidence": "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json",
  "source_classification": "BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME",
  "ebench_reference": "microwave task-level manual custom_motion waypoints plus runtime cuRobo planning",
  "no_claims": [
    "stable_grasp",
    "micro_pull_readiness",
    "door_opened",
    "Expert Oracle Score",
    "policy_score",
    "official_score"
  ],
  "candidates": [
    {
      "candidate_id": "5l_cf_handle_right_025_clamped_xy12_zp02",
      "source_role": "panda_rightfinger",
      "source_signed_axis_gap_m": [0.084393376008, 0.067267486749, 0.0],
      "scale_factor": 0.25,
      "max_x_shift_m": 0.012,
      "max_y_shift_m": 0.012,
      "contact_offset_x_m": 0.007,
      "center_offset_y_m": 0.012,
      "center_offset_z_m": -0.006,
      "orientation_offset_z_deg": 2.0,
      "orientation_offset_y_deg": 0.0,
      "review_decision": "single_conservative_live_candidate"
    }
  ]
}
```

- [x] **Step 4: Validate the JSON**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_review_20260705_5l_candidates.json >/tmp/eos2_5l_candidates.pretty.json
```

Expected: command exits `0`.

### Task 3: Run One Conservative 5L Live Candidate

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_review_20260705_5l_candidates.json`
- Create directory: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [x] **Step 1: Start fresh GenManip server with contact telemetry enabled**

Run from the GenManip worktree:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
conda run -n embodied-eval-os-sim-isaacsim41-genmanip-py310 env \
  LABUTOPIA_ORACLE_DEBUG_OBS=1 \
  LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1 \
  python -m genmanip_client.cli server start \
  --port 18450 \
  --host 127.0.0.1
```

Expected: server responds on `127.0.0.1:18450`; save the server log into the new 5L evidence directory.

- [x] **Step 2: Submit a fresh run before probing**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
conda run -n embodied-eval-os-sim-isaacsim41-genmanip-py310 python - <<'PY'
from genmanip_client.cli import main

raise SystemExit(main([
    "submit",
    "--host", "127.0.0.1",
    "--port", "18450",
    "--run-id", "labutopia_eos2_5l_cf_handle_right_025_clamped_xy12_zp02_20260705_1000",
]))
PY
```

Expected: submit exits `0`; save stdout, stderr, command, and exit code.

- [x] **Step 3: Run the 5L probe against exactly one selected candidate**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
conda run -n embodied-eval-os-sim-isaacsim41-genmanip-py310 python standalone_tools/labutopia_poc/online_open_door_oracle_probe.py \
  --host 127.0.0.1 \
  --port 18450 \
  --mode planner-trajectory-post-replay-close-hold-action \
  --stage-labels approach_pre,approach_near,contact,post_bridge_local_z_m006_q_bridge,5l_cf_handle_right_025_clamped_xy12_zp02 \
  --include-trajectory-points \
  --retention-requires-physx-contact \
  --summary-output docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json \
  --trace-output docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/trace.jsonl
```

Expected: probe exits `0`; selected candidate, action-point count, close-hold samples, and retention telemetry are present in the compact summary.

- [x] **Step 4: Stop the server and verify the port is released**

Run:

```bash
python - <<'PY'
import socket

sock = socket.socket()
try:
    result = sock.connect_ex(("127.0.0.1", 18450))
finally:
    sock.close()
print(result)
PY
```

Expected after stopping the server: prints a nonzero integer.

### Task 4: Classify 5L Result And Decide Next Stage

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Extract the four retention fields**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json")
data = json.loads(path.read_text())

def walk(obj, key):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(walk(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(walk(item, key))
    return found

for key in [
    "retention_pass",
    "tail_bilateral_overlap_records",
    "tail_required_roles_near_records",
    "tail_physx_required_roles_contact_records",
]:
    print(f"{key}={walk(data, key)}")
PY
```

Expected pass classification: `retention_pass` contains `True` and all three tail count fields contain at least one positive integer.

- [x] **Step 2: Write the blocked update with the first failed gate**

Use this status wording if the candidate planned and executed but retention is false or missing:

```markdown
Task 5L live candidate remains blocked at contact retention. It may have planned and executed,
but it is not a stable grasp because at least one of retention_pass, tail bilateral overlap,
required-role near, or required-role PhysX contact is false or missing. The next stage remains
candidate generation / contact-frame refinement, not micro-pull or score.
```

Use this status wording if the candidate fails before post-replay action points are generated:

```markdown
Task 5L live candidate remains blocked at handle-frame target reachability. The bridge replay still
works, but the selected generated candidate failed post-replay replan with `MotionGenStatus.IK_FAIL`,
so there are no action points, no close-hold, and no retention telemetry. The next stage is a smaller
reachability ladder / staged handle-frame target review, not micro-pull or score.
```

- [ ] **Step 3: If retention is true, open a separate micro-pull plan**

Create a new plan under `docs/superpowers/plans/` named
`2026-07-05-eos2-micro-pull-readback.md`. The first paragraph must say that Task 5L proved
retention only, not door opening or score; the plan must require door joint readback before any
`Expert Oracle Score` claim.

### Task 5: PM Handoff

**Files:**
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [x] **Step 1: Add the PM explanation**

Use this wording if Task 5L is still blocked:

```markdown
给 PM 的一句话：我们已经确认 EBench 自己也不是靠“旧轨迹逐帧照抄”来开微波炉门，而是靠
task-level manual custom_motion waypoint + cuRobo runtime planning。DryingBox 现在也在转向
这条正路：先让机器人基于把手/接触坐标系生成目标点，再用真实 physics 和 readback 验证是否
真的夹住。当前还没到开门或算分；如果候选连 post-replay replan 都到不了，就先拆成更小的
reachability ladder，不能把它误判成夹持失败。
```

Use this wording only if Task 5L retention passes:

```markdown
给 PM 的一句话：Task 5L 已证明机器人能在真实 Isaac 里到达候选把手姿态并形成 retention-positive
夹持；这仍不是开门成功。下一步只允许做 micro-pull readback，看门铰链角度是否按预期变化。
```

- [ ] **Step 2: Run final doc checks**

Run:

```bash
git diff --check docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/evidence_manifests/README.md docs/superpowers/plans/2026-07-05-eos2-contact-frame-handle-frame-target-generation.md
```

Expected: command exits `0`.

## Self-Review

- Spec coverage: this plan answers why EBench `microwave` is relevant, how its expert is computed, why DryingBox should not replay old trajectories, and what exact 5L evidence must be produced before micro-pull or score.
- Placeholder scan: no `TBD`, `TODO`, or unbounded “handle edge cases” steps remain.
- Claim boundary: the plan explicitly blocks stable grasp, micro-pull, door-open, `Expert Oracle Score`, policy score, official score, and full task completion unless retention-positive evidence exists.

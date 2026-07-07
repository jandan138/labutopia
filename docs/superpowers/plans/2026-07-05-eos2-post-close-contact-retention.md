# EOS2 Post-Close Contact Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add EOS-2 Task 5H instrumentation so planner `post_replay_close_hold` records finger-handle contact/retention evidence after the proven 5G close command/readback stage.

**Architecture:** Keep 5H as a diagnostic instrumentation stage between close-hold and micro-pull. Reuse the existing `summarize_pre_close_contact_frame`, `finger_width_readback_record`, and `PostCloseContactRetentionTracker` helpers; do not create a second contact semantics stack. The planner close-hold summary may report AABB/PhysX contact-retention telemetry, but stable grasp, micro-pull, door-open, score, policy, and official leaderboard claims remain false unless a later acceptance stage explicitly proves them.

**Tech Stack:** Python, pytest, Isaac Sim 4.1 / GenManip online probe, LabUtopia evidence manifests.

---

## Files

- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
  - Wire planner close-hold samples into `PostCloseContactRetentionTracker`.
  - Add per-step `post_close_contact_frame` and a summary-level `retention_summary`.
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
  - Add focused unit coverage proving planner close-hold contact frames are collected and claim guards stay false.
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
  - Add Task 5H code checkpoint / live evidence rows after verification.
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
  - Add PM-readable 5H status and next-step routing.
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
  - Add handoff notes for 5H and the next micro-pull preconditions.
- Create after code verification: `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json`
  - Machine-readable code checkpoint manifest.

## Contract

Task 5H is allowed to claim:

- planner close-hold contact frames are collected per hold step.
- `post_replay_close_hold.retention_summary.available=true` when samples are actually recorded.
- AABB near/overlap counts, finger width readback counts, and PhysX required-role contact counts are preserved in the summary.
- whether a later stage is allowed to proceed to micro-pull diagnostics.

Task 5H is not allowed to claim:

- `stable_grasp=true`
- `micro_pull_readiness=true`
- `door_opened=true`
- `expert_oracle_score=true`
- `policy_score=true`
- `official_leaderboard_score=true`
- `full_task_completion=true`

If `require_physx_contact_retention=true` and PhysX required-role contact is absent, then `retention_pass=false` even if AABB overlap and finger width pass.

## Task 1: Add Planner Close-Hold Contact Retention Unit Test

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`

- [x] **Step 1: Write the failing test**

Add a focused helper/test near the existing planner close-hold tests:

```python
def test_planner_close_hold_records_post_close_contact_retention_summary():
    class CloseHoldClient:
        def __init__(self):
            self.step_calls = 0

        def step(self, actions):
            self.step_calls += 1
            return {
                "worker-0": {
                    "obs": {
                        "state.joints": [0.0] * 7,
                        "state.gripper": [0.010, 0.010],
                    },
                    "done": False,
                    "info": {
                        "evaluator_last_action_application_debug": {
                            "target_delta_abs_max": 0.0,
                            "post_world_step_delta_abs_max": 0.0,
                            "contact_debug": {
                                "closest_pairs": [
                                    {
                                        "robot_prim_path": "/World/franka/panda_leftfinger",
                                        "target_prim_path": "/World/obj_DryingBox_01/handle",
                                        "target_uid": "obj_DryingBox_01_handle",
                                        "aabb_signed_clearance_m": -0.001,
                                        "separated": False,
                                        "axis_gap_m": [0.0, 0.0, 0.0],
                                    },
                                    {
                                        "robot_prim_path": "/World/franka/panda_rightfinger",
                                        "target_prim_path": "/World/obj_DryingBox_01/handle",
                                        "target_uid": "obj_DryingBox_01_handle",
                                        "aabb_signed_clearance_m": -0.001,
                                        "separated": False,
                                        "axis_gap_m": [0.0, 0.0, 0.0],
                                    },
                                ]
                            },
                            "physx_contact_debug": {
                                "status": "available",
                                "required_roles_contact": False,
                                "contact_pair_count": 0,
                            },
                        }
                    },
                }
            }, False

    # Use the existing planner trajectory execution helper with a fake client path
    # that enters post_replay_close_hold and then assert:
    # summary["post_replay_close_hold"]["retention_summary"]["available"] is True
    # summary["post_replay_close_hold"]["retention_summary"]["sample_count"] == 3
    # summary["post_replay_close_hold"]["retention_summary"]["tail_bilateral_overlap_records"] == 3
    # summary["post_replay_close_hold"]["retention_summary"]["tail_physx_required_roles_contact_records"] == 0
    # summary["post_replay_close_hold"]["stable_grasp_claim_allowed"] is False
    # summary["claim_guards"]["stable_grasp"] is False
```

Use existing test fixture patterns in the same file rather than building a new fake server framework.

- [x] **Step 2: Run the test to verify RED**

Run:

```bash
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-newton-ebench-rolling-py310/bin/python -m pytest \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_close_hold_records_post_close_contact_retention_summary -q
```

Expected: fails because `post_replay_close_hold.retention_summary.available` is still false / reason is `contact_retention_not_collected_in_planner_close_hold_stage`.

## Task 2: Wire Existing Tracker Into Planner Close-Hold

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [x] **Step 1: Create tracker state in planner trajectory execution**

Near `post_replay_close_hold_samples`, initialize:

```python
post_replay_close_hold_retention_tracker = PostCloseContactRetentionTracker(
    stage_label="planner_trajectory_post_replay_close_hold_action",
    tail_window=int(getattr(args, "post_close_retention_tail_window", 20)),
    min_bilateral_overlap_records=int(
        getattr(args, "post_close_retention_min_bilateral_overlap_records", 18)
    ),
    finger_width_max_m=float(
        getattr(args, "post_close_retention_finger_width_max_m", 0.020)
    ),
    require_physx_contact_retention=bool(
        getattr(args, "post_close_retention_require_physx_contact", False)
    ),
)
```

If the existing arg names differ, use the existing names from `_parse_args()` and do not add duplicate flags.

- [x] **Step 2: Record contact frame for every close-hold step**

After `sample["finger_width_readback"] = finger_width_readback_record(...)`, add:

```python
contact_frame = summarize_pre_close_contact_frame(
    app_debug,
    required_roles=("panda_leftfinger", "panda_rightfinger"),
)
sample["post_close_contact_frame"] = contact_frame
finger_width = sample["finger_width_readback"].get("actual_finger_width_avg_m")
post_replay_close_hold_retention_tracker.record(
    step=executed_steps,
    segment="planner_trajectory_post_replay_close_hold_action",
    segment_step=close_step_index,
    contact_frame=contact_frame,
    actual_finger_width_m=finger_width if isinstance(finger_width, (int, float)) else None,
    finger_width_readback=sample["finger_width_readback"],
    contact_debug_method=(
        (app_debug.get("contact_debug") or {}).get("method")
        if isinstance(app_debug, dict) and isinstance(app_debug.get("contact_debug"), dict)
        else None
    ),
    physx_contact_debug=(
        app_debug.get("physx_contact_debug") if isinstance(app_debug, dict) else None
    ),
)
```

- [x] **Step 3: Replace fixed unavailable summary**

Before building `summary`, compute:

```python
post_replay_close_hold_retention_summary = (
    post_replay_close_hold_retention_tracker.summary()
    if post_replay_close_hold_samples
    else {
        "available": False,
        "reason": (
            post_replay_close_hold_skipped_reason
            or "post_replay_close_hold_not_executed"
        ),
    }
)
```

Then set:

```python
"retention_summary": post_replay_close_hold_retention_summary,
```

Keep:

```python
"stable_grasp_claim_allowed": False,
```

- [x] **Step 4: Run focused tests**

Run:

```bash
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-newton-ebench-rolling-py310/bin/python -m pytest \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_close_hold_records_post_close_contact_retention_summary \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_post_close_retention_tracker_passes_tail_bilateral_overlap \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_post_close_retention_tracker_can_require_physx_contact_for_c6 \
  -q
```

Expected: all selected tests pass.

## Task 3: Code Checkpoint Manifest And Docs

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Create code checkpoint manifest**

The manifest must include:

```json
{
  "schema_version": 1,
  "stage": "EOS2 5H post-close contact retention instrumentation",
  "status": "PASS_CODE_CHECKPOINT_DIAGNOSTIC_ONLY",
  "generated_at_utc": "2026-07-05T00:00:00Z",
  "code_artifacts": [
    "/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py",
    "/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py"
  ],
  "new_summary_fields": [
    "post_replay_close_hold.retention_summary",
    "samples.planner_trajectory_post_replay_close_hold_action[].post_close_contact_frame"
  ],
  "allowed_claims": [
    "planner close-hold contact-retention instrumentation is code-ready",
    "AABB/PhysX contact telemetry is recorded when available"
  ],
  "blocked_claims": [
    "stable_grasp",
    "micro_pull_readiness",
    "door_opened",
    "expert_oracle_score",
    "policy_score",
    "official_leaderboard_score",
    "full_task_completion"
  ],
  "verification": []
}
```

Historical note: this checkpoint manifest shape is retained for context only; the
later evidence rows in `docs/labutopia_lab_poc/evidence_manifests/README.md`
carry the executed verification status for Task 5H and downstream Task 5I.

- [x] **Step 2: Update PM-facing docs**

Add concise text:

```text
2026-07-05 Task 5H code checkpoint adds contact-retention instrumentation after 5G close-hold. Product meaning: 5G proved the fingers can be commanded closed and read back; 5H records whether both finger roles are actually near/overlapping the DryingBox handle and whether PhysX required-role contact exists. This is still diagnostic evidence, not a stable grasp or score claim. If live evidence shows bilateral near/overlap and, when `retention_requires_physx_contact=true`, required-role PhysX contact also passes, the next stage can run a tiny micro-pull; if it shows near-only, outside-frame, or missing PhysX contact, the next stage must adjust the handle-side close/contact pose instead of pulling.
```

- [x] **Step 3: Verify docs**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json
git diff --check -- \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json
```

Expected: both commands exit 0.

## Task 4: Optional Live 5H Evidence

**Files:**
- Create evidence dir under `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_live_20260705_5h_<suffix>/`

- [x] **Step 1: Run live only after code checkpoint passes**

Use the same conda env and server discipline as 5G, with a fresh port and Ray tmpdir. Enable both `LABUTOPIA_ORACLE_DEBUG_OBS=1` and `LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1` in the server environment. `PHYSX_CONTACT_OBS` alone is insufficient because this evaluator only exports `evaluator_last_action_application_debug/contact_debug` through obs when `LABUTOPIA_ORACLE_DEBUG_OBS=1`.

- [x] **Step 2: Preserve claim boundary**

The compact summary may use:

```text
PASS_DIAGNOSTIC_CONTACT_RETENTION_AABB_ONLY
PASS_DIAGNOSTIC_CONTACT_RETENTION_PHYSX_REQUIRED_ROLES
BLOCKED_CONTACT_RETENTION_NEAR_ONLY
BLOCKED_CONTACT_RETENTION_MISSING_CONTACT_FRAME
```

It must not report a public score or official EBench result.

## 2026-07-05 Execution Checkpoint

Task 5H code checkpoint is implemented in the GenManip dedicated worktree. The
actual test coverage reused the existing planner close-hold replay fixture rather
than adding a second fake-server fixture under the placeholder name in Task 1.
The covered test is:

```text
tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_trajectory_execution_readback_closes_gripper_after_post_replay_continuation
```

Fresh verification on 2026-07-05:

```text
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-newton-ebench-rolling-py310/bin/python -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_trajectory_execution_readback_closes_gripper_after_post_replay_continuation tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_finger_width_readback_record_reads_split_gripper_obs tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_post_close_retention_tracker_passes_tail_bilateral_overlap tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_post_close_retention_tracker_can_require_physx_contact_for_c6 -q
4 passed in 0.25s

/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-newton-ebench-rolling-py310/bin/python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
exit 0

git diff --check -- standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
exit 0
```

LabUtopia evidence docs now include:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json
docs/labutopia_lab_poc/evidence_manifests/README.md
docs/labutopia_lab_poc/expert_oracle_score_plan.md
docs/labutopia_lab_poc/aan_consumer_handoff.md
```

Docs verification:

```text
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json
exit 0

git diff --check -- docs/labutopia_lab_poc/evidence_manifests/README.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json
exit 0
```

Current boundary at code checkpoint time: this was code checkpoint evidence only.
No live 5H run had yet proven bilateral handle retention, PhysX required-role
contact, stable grasp, micro-pull readiness, door opening, Expert Oracle Score,
policy score, official leaderboard score, or full task completion.

## 2026-07-05 Live 5H Execution Checkpoint

Two live 5H runs now exist:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_live_20260705_5h_0430/summary_compact.json
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_debugobs_live_20260705_5h_0440/summary_compact.json
```

The first run is a negative control for server environment. It used
`LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1` but omitted `LABUTOPIA_ORACLE_DEBUG_OBS=1`.
The bridge, continuation, and close-hold actions still executed; close-hold ran
15 steps, reached the joint target, and read final finger width around
`0.01280m`. But `post_close_contact_frame.available=false` with reason
`missing_action_application_debug`, so it cannot prove or disprove contact
retention.

The second run fixed the server environment with both debug flags enabled. It
proves that contact telemetry is now available:
`tail_physx_contact_status_counts.available=15`. Motion/readback remains good:
close-hold executed 15 steps, `reached_joint_target=true`, final joint target
error was about `8.27e-05 rad`, and final finger width was about `0.01280m`.
The raw `PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY` status only
means diagnostic motion/readback completed; it does not mean grasp or task
success. `finger_width_max_pass=false` because the 15-step tail includes the
closing transient, so the safe finger-width statement is only the final readback
of about `0.01280m`. Retention did not pass:

```text
retention_pass=false
tail_bilateral_overlap_pass=false
tail_physx_required_roles_contact_records=0
last post_close_contact_frame.classification=OUTSIDE_PRE_CLOSE_CONTACT_FRAME
last required_roles_near=false
last required_roles_overlap=false
last max_required_axis_gap_abs_m ~= [0.1353, 0.0692, 0.0]m
```

Conclusion: 5H moved the blocker from "can we close the gripper and observe
contacts?" to "the current handle-side contact pose closes outside the handle
frame." The immediate next action was a contact-frame-guided local pose sweep
after `post_bridge_local_z_m006_q_bridge`.

## 5I Checkpoint: Contact-Frame-Guided Micro Sweep

Live 5I evidence has now consumed that next action:

```text
negative control:
  5i_0610 missing submit -> reset/preplan failed, not contact evidence

baseline:
  5i_0640 post_bridge_local_z_m006_q_bridge -> planner success, executed 31 post-replay steps,
  close-hold executed 15 steps, retention_pass=false

too-large / coarse candidates:
  5i_0620 cf_right_050 -> IK_FAIL
  5i_0630 cf_micro_x010_y008 -> IK_FAIL

coordinate semantics:
  signed_axis_gap_m is a world-AABB gap, not object-frame x/y.
  For this DryingBox object frame, object-frame Y+ mainly reduces world X gap,
  and object-frame X- mainly reduces world Y gap.

micro-candidate outcomes:
  5i_0650 mixed-direction 5mm -> planner success, executed, retention=false;
    world X gap improved but world Y gap worsened.
  5i_0700 object-frame Y+5mm -> IK_FAIL.
  5i_0710 object-frame X-5mm -> IK_FAIL.
  5i_0720 object-frame X-5mm/Y+5mm -> IK_FAIL.
  5i_0730 object-frame X-2mm/Y+2mm -> IK_FAIL.
  5i_0740 object-frame Y+2mm -> planner success, executed, retention=false;
    world X gap improves slightly but world Y gap worsens slightly.
  5i_0750 object-frame X-2mm -> planner success, executed, retention=false;
    world Y gap improves slightly but world X gap worsens slightly.
```

Updated conclusion after 5I: fixed-quaternion pure translation is too narrow to
solve contact retention. There is a reachable single-axis 2mm corridor, but it
only improves one world-axis gap while worsening the other; the correct paired
correction falls outside IK reachability even at 2mm. The next action should be
an orientation-aware / approach-seed / staged-correction sweep around
`post_bridge_local_z_m006_q_bridge`, not micro-pull. Only after both fingers are
near/overlap the handle in the tail window and required-role PhysX contact passes
should micro-pull diagnostics start.

Current boundary after live 5I: still no stable grasp, micro-pull readiness,
door opening, Expert Oracle Score, policy score, official leaderboard score, or
full task completion.

Follow-up plan: Task 5J has been split into
[`2026-07-05-eos2-contact-retention-orientation-aware-staged-correction.md`](2026-07-05-eos2-contact-retention-orientation-aware-staged-correction.md).
It starts with an explicit candidate manifest and a one-candidate-per-run
orientation-aware live probe so retention evidence is not hidden by the existing
multi-candidate first-success behavior.

## Self-Review

- Spec coverage: covers 5H contact-retention instrumentation, code checkpoint, documentation, and optional live evidence.
- Placeholder scan: no `TBD` / `TODO`; exact files and commands are provided.
- Type consistency: uses existing tracker names and summary keys already present in the probe. The only new sample key is `post_close_contact_frame` inside existing close-hold samples.

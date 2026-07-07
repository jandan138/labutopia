# EOS2 Post-Bridge Close Grasp Staging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 5G diagnostic stage that executes gripper close / pending hold only after the already-proven bridge + post-bridge continuation movements, matching EBench microwave `custom_motion` staging without claiming score.

**Architecture:** Keep motion planning and gripper closing as separate stages. `planner-trajectory-execution-readback` continues to replay the selected bridge trajectory and optional post-replay continuation; a new close-hold stage then sends repeated absolute `joint_position` actions that preserve the final 7 arm joints and set both Franka fingers to `close_width_m`. The summary records close-hold readback and contact-retention diagnostics, but all score, stable grasp, micro-pull, door-open, policy, and official leaderboard claims remain false.

**Tech Stack:** Python, pytest, GenManip EvalClient diagnostic probe, EBench/Isaac Sim 4.1 runtime, LabUtopia evidence manifests.

---

## Files

- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
  - Add focused TDD coverage for post-replay close-hold staging.
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
  - Add CLI args and execution/summary fields for the close-hold stage.
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
  - Add 5G code checkpoint and live evidence rows after verification.
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
  - Mark 5G as the next diagnostic stage after 5F and before micro-pull.
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
  - Add PM-readable explanation of why close/pending is separated from movement.
- Optional modify after live evidence: `reports/2026-06-15-labutopia-weekly/index.html`
  - Add one concise status paragraph if live 5G evidence is generated.

## Task 1: TDD Test For Post-Replay Close Hold

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`

- [ ] **Step 1: Write the failing test**

Add a test after `test_planner_trajectory_execution_readback_sweeps_post_replay_extra_waypoints_and_selects_first_success`.

```python
def test_planner_trajectory_execution_readback_closes_gripper_after_post_replay_continuation(
    tmp_path,
):
    selected_bridge_label = (
        "approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity"
    )
    bridge_action_points = [
        [0.1, -0.1, 0.0, -2.7, 0.0, 2.9, 0.7, 0.04, 0.04],
    ]
    followup_action_points = [
        [0.18, -0.12, 0.02, -2.62, 0.08, 2.82, 0.66, 0.04, 0.04],
    ]

    class FakeEvalClient:
        def __init__(self):
            self.run_id = "unit_planner_post_bridge_close_hold"
            self.current_joints = [0.0, -0.2, 0.0, -2.8, 0.0, 3.0, 0.7, 0.04, 0.04]
            self.plan_calls = []
            self.step_calls = []

        def reset(self):
            return {
                "0": {
                    "obs": _worker_obs_with_joints(
                        [0.3892936706542969, 0.004671652801334858, 0.45820391178131104],
                        list(self.current_joints),
                    ),
                    "metric": {},
                }
            }

        def plan_object_frame_waypoints(self, **kwargs):
            labels = [waypoint["label"] for waypoint in kwargs["waypoints"]]
            self.plan_calls.append(
                {
                    "run_id": self.run_id,
                    "labels": labels,
                    "current_joints": list(self.current_joints),
                    "include_trajectory_points": kwargs["include_trajectory_points"],
                }
            )
            if len(self.plan_calls) == 1:
                success_label = selected_bridge_label
                action_points = bridge_action_points
            else:
                success_label = "post_bridge_near"
                action_points = followup_action_points
            return {
                "worker_id": str(kwargs["worker_id"]),
                "planner_records": [
                    {
                        "label": label,
                        "plan_success": label == success_label,
                        "world_refresh_status": "success",
                        "trajectory_point_count": len(action_points) if label == success_label else 0,
                        "failure_reason": None if label == success_label else "motion_planning_failed",
                        "trajectory_action_joint_position_schema": "embodiment.convert_curobo_result_to_action",
                        "trajectory_action_control_type": "joint_position",
                        "trajectory_action_replay_policy": "diagnostic_consumer_must_apply_readback_guards",
                        "trajectory_action_joint_names": [
                            "panda_joint1",
                            "panda_joint2",
                            "panda_joint3",
                            "panda_joint4",
                            "panda_joint5",
                            "panda_joint6",
                            "panda_joint7",
                            "panda_finger_joint1",
                            "panda_finger_joint2",
                        ],
                        "trajectory_action_joint_positions": action_points if label == success_label else [],
                    }
                    for label in labels
                ],
                "world_refresh_status_by_waypoint": {label: "success" for label in labels},
                "planning_status_by_waypoint": {
                    label: "success" if label == success_label else "failed:motion_planning_failed"
                    for label in labels
                },
            }

        def step(self, action):
            self.step_calls.append((self.run_id, action))
            sent_action = action["0"]
            previous_joints = list(self.current_joints)
            self.current_joints = list(sent_action["action"])
            target_delta_abs_max = max(
                abs(after - before)
                for after, before in zip(self.current_joints, previous_joints)
            )
            return {
                "0": {
                    "obs": _worker_obs_with_joints(
                        [0.40, 0.02, 0.46],
                        list(self.current_joints),
                        evaluator_last_action_application_debug={
                            "action_control_type": "joint_position",
                            "target_delta_abs_max": target_delta_abs_max,
                            "post_world_step_delta_abs_max": target_delta_abs_max,
                        },
                    ),
                    "metric": {"*task": {"score": 0.0, "sr": 0.0}},
                }
            }, False

    args = Namespace(
        run_id="unit_planner_post_bridge_close_hold",
        task_config="task.yml",
        output=str(tmp_path / "summary.json"),
        trace_jsonl=str(tmp_path / "trace.jsonl"),
        planner_trajectory_waypoint_label=selected_bridge_label,
        planner_trajectory_extra_object_frame_waypoint=[
            [
                selected_bridge_label,
                "0.0010228951554745458",
                "-0.11657822728157047",
                "0.014903118610382071",
                "0.9478491886430741",
                "-0.209547848787944",
                "-0.22171216853953848",
                "-0.09227854018408849",
            ]
        ],
        planner_trajectory_post_replay_replan=True,
        planner_trajectory_post_replay_waypoint_label=None,
        planner_trajectory_post_replay_extra_object_frame_waypoint=[
            [
                "post_bridge_near",
                "-0.06",
                "-0.015",
                "0.02",
                "1.0",
                "0.0",
                "0.0",
                "0.0",
            ],
        ],
        planner_trajectory_post_replay_execute=True,
        planner_trajectory_post_replay_close_hold_steps=3,
        object_frame_rel_object_uid="obj_DryingBox_01_handle",
        pose_ladder_include_reset_to_handle_bridge=True,
        approach_pre_offset_x_m=-0.08,
        approach_near_offset_x_m=-0.03,
        approach_near_offset_y_m=0.0,
        approach_near_offset_z_m=0.0,
        contact_offset_x_m=-0.005,
        contact_offset_y_m=0.0,
        contact_offset_z_m=0.0,
        open_width_m=0.04,
        close_width_m=0.012,
        controller_readback_joint_tolerance_rad=0.02,
        controller_readback_lead_in_max_joint_step_rad=0.5,
        controller_readback_lead_in_post_step_delta_threshold_rad=0.8,
        controller_readback_lead_in_max_steps=64,
        physics_hold_steps=0,
    )

    client = FakeEvalClient()
    summary = probe.run_planner_trajectory_execution_readback(
        client,
        args=args,
        worker_id="0",
        trace_path=tmp_path / "trace.jsonl",
        fresh_job_starter=lambda run_id: None,
    )

    assert [action["0"]["action"] for _, action in client.step_calls] == [
        bridge_action_points[-1],
        followup_action_points[-1],
        [*followup_action_points[-1][:7], 0.012, 0.012],
        [*followup_action_points[-1][:7], 0.012, 0.012],
        [*followup_action_points[-1][:7], 0.012, 0.012],
    ]
    assert summary["post_replay_close_hold"]["enabled"] is True
    assert summary["post_replay_close_hold"]["hold_steps"] == 3
    assert summary["post_replay_close_hold"]["executed_steps"] == 3
    assert summary["post_replay_close_hold"]["close_width_m"] == 0.012
    assert summary["post_replay_close_hold"]["arm_joint_source"] == "post_replay_final_joint_readback"
    assert summary["samples"]["planner_trajectory_post_replay_close_hold_action"][-1][
        "joint_target_position"
    ] == [*followup_action_points[-1][:7], 0.012, 0.012]
    assert summary["stable_grasp_claim_allowed"] is False
    assert summary["micro_pull_claim_allowed"] is False
    assert summary["score_claim_allowed"] is False
```

- [ ] **Step 2: Run RED**

Run:

```bash
pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_trajectory_execution_readback_closes_gripper_after_post_replay_continuation -q
```

Expected: FAIL because `post_replay_close_hold` is missing from the summary and the fake client only receives bridge + follow-up actions.

## Task 2: Implement Close-Hold Stage

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [ ] **Step 1: Add CLI argument**

Add near the existing post-replay args:

```python
parser.add_argument(
    "--planner-trajectory-post-replay-close-hold-steps",
    type=int,
    default=0,
    help=(
        "Diagnostic-only for --probe-mode planner-trajectory-execution-readback: "
        "after a successful post-replay continuation execution, preserve the final "
        "arm joints and repeatedly command both fingers to --close-width-m for N "
        "steps. This mirrors custom_motion pending grasp staging."
    ),
)
```

- [ ] **Step 2: Add execution state**

Inside `run_planner_trajectory_execution_readback`, validate the new arg with `_validated_physics_hold_steps`, initialize `post_replay_close_hold_samples`, `post_replay_close_hold_last_worker_obs`, `post_replay_close_hold_final_joint_target`, and `post_replay_close_hold_skipped_reason`.

- [ ] **Step 3: Execute repeated close-hold actions after post-replay continuation**

After post-replay readback is computed, run the close-hold only when:

```python
post_replay_close_hold_steps > 0
and post_replay_execute_enabled
and post_replay_last_worker_obs is not None
and post_replay_final_joint_target is not None
and not any(blocker in blockers for blocker in {
    "planner_trajectory_post_replay_terminal_done",
    "planner_trajectory_post_replay_terminal_without_post_obs",
    "planner_trajectory_post_replay_final_joint_target_exceeds_tolerance",
})
```

For each close step, build:

```python
close_target = [*arm_source[:7], float(args.close_width_m), float(args.close_width_m)]
action = make_absolute_joint_position_action_from_action_target(close_target)
```

Set `sample_type="planner_trajectory_post_replay_close_hold_action"`, write each sample to the trace, and update `previous_worker_obs`.

- [ ] **Step 4: Add summary fields**

Add:

```python
"post_replay_close_hold": {
    "enabled": post_replay_close_hold_steps > 0,
    "hold_steps": post_replay_close_hold_steps,
    "executed_steps": len(post_replay_close_hold_samples),
    "close_width_m": float(getattr(args, "close_width_m", 0.015)),
    "arm_joint_source": post_replay_close_hold_arm_joint_source,
    "skipped_reason": post_replay_close_hold_skipped_reason,
    "joint_target_tolerance_rad": joint_tolerance,
    **post_replay_close_hold_readback_summary,
},
"samples": {
    "planner_trajectory_action": replay_samples,
    "planner_trajectory_post_replay_action": post_replay_samples,
    "planner_trajectory_post_replay_close_hold_action": post_replay_close_hold_samples,
},
```

Keep `stable_grasp_claim_allowed`, `micro_pull_claim_allowed`, and `score_claim_allowed` false.

- [ ] **Step 5: Run GREEN**

Run:

```bash
pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_trajectory_execution_readback_closes_gripper_after_post_replay_continuation -q
```

Expected: PASS.

## Task 3: Regression Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused post-replay tests**

Run:

```bash
pytest \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_trajectory_execution_readback_replans_followup_after_bridge_replay \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_trajectory_execution_readback_sweeps_post_replay_extra_waypoints_and_selects_first_success \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py::test_planner_trajectory_execution_readback_closes_gripper_after_post_replay_continuation \
  -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run syntax and whitespace checks**

Run:

```bash
python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
git diff --check -- standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
```

Expected: both commands exit 0.

## Task 4: LabUtopia 5G Code Checkpoint Docs

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_code_checkpoint_20260705.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [ ] **Step 1: Create checkpoint manifest**

Manifest fields:

```json
{
  "schema_version": 1,
  "status": "PASS_CODE_CHECKPOINT_DIAGNOSTIC_ONLY",
  "stage": "EOS2 5G post-replay close-hold staging",
  "claim_boundary": {
    "stable_grasp": false,
    "micro_pull_readiness": false,
    "door_opened": false,
    "expert_oracle_score": false,
    "policy_score": false,
    "official_leaderboard_score": false
  },
  "implementation": {
    "probe": "standalone_tools/labutopia_poc/online_open_door_oracle_probe.py",
    "test": "tests/labutopia_poc/test_online_open_door_oracle_probe.py",
    "new_cli_arg": "--planner-trajectory-post-replay-close-hold-steps",
    "new_sample_type": "planner_trajectory_post_replay_close_hold_action"
  },
  "verification": []
}
```

- [ ] **Step 2: Update docs**

Use this PM-readable language:

```markdown
5G 把“走到把手附近”和“闭爪夹住”拆开验证。前两段移动沿用 5F 已经跑通的 bridge + post_bridge_local_z_m006_q_bridge；新增阶段只做一件事：保持手臂 7 个关节不动，把两个 finger command 改成 close_width_m，并连续 pending 若干步。这样对齐 EBench microwave 的 custom_motion 模式：waypoint 负责移动，pending grasp 负责闭爪等待。
```

Keep boundary language:

```markdown
这仍是 diagnostic-only。它最多证明 close/pending action 能接在 post-replay continuation 后面并有 readback；不能升级为 stable grasp、micro-pull readiness、door opened、Expert Oracle Score、policy score 或 official score。
```

## Task 5: Live 5G Evidence

**Files:**
- Create evidence dir: `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_live_20260705_5g_*/`
- Modify docs listed in Task 4.

- [ ] **Step 1: Start isolated server**

Use a fresh run id, port, and Ray temp dir, following the 5F command style. Do not reuse another engineer's EOS run id.

- [ ] **Step 2: Run probe**

Use 5F's successful setup:

```bash
--planner-trajectory-waypoint-label approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity
--planner-trajectory-extra-object-frame-waypoint approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity 0.0010228951554745458 -0.11657822728157047 0.014903118610382071 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849
--planner-trajectory-post-replay-replan
--planner-trajectory-post-replay-extra-object-frame-waypoint post_bridge_local_z_m006_q_bridge 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849
--planner-trajectory-post-replay-execute
--planner-trajectory-post-replay-close-hold-steps 15
--close-width-m 0.012
```

- [ ] **Step 3: Stop server and compact evidence**

Always stop the isolated server before reporting. Create `summary_compact.json` with:

```json
{
  "status": "...",
  "post_replay_replan": {
    "selected_waypoint_label": "post_bridge_local_z_m006_q_bridge",
    "executed_steps": 0
  },
  "post_replay_close_hold": {
    "enabled": true,
    "hold_steps": 15,
    "executed_steps": 0,
    "close_width_m": 0.012
  },
  "claim_guards": {
    "stable_grasp": false,
    "micro_pull_readiness": false,
    "door_opened": false,
    "expert_oracle_score": false,
    "policy_score": false,
    "official_leaderboard_score": false
  }
}
```

- [ ] **Step 4: Verify evidence**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_live_20260705_5g_*/summary_compact.json
bash -n docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_live_20260705_5g_*/*.command.txt
git diff --check
```

Expected: all commands exit 0.

## Self-Review

- Spec coverage: covers the explicit 5G need to separate close/pending from movement, preserves 5F movement evidence, and keeps score/stable-grasp claims guarded.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: new arg is `planner_trajectory_post_replay_close_hold_steps`; new summary key is `post_replay_close_hold`; new sample key is `planner_trajectory_post_replay_close_hold_action`.

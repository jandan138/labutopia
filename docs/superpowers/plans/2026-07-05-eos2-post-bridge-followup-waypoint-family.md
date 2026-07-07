# EOS2 Post-Bridge Follow-Up Waypoint Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the EOS2 DryingBox oracle probe so that, after a successful bridge trajectory replay, it can scan a small family of post-bridge object-frame follow-up waypoints and select the first planner-successful continuation instead of repeatedly retrying the stale `approach_pre` target.

**Architecture:** Keep the current no-score/no-door-open claim boundary. Reuse the EBench microwave pattern: declare object-frame keypoints, convert them server-side, and ask cuRobo/MotionGen to plan from the live post-replay robot state. Post-bridge follow-up candidates are alternatives, so the probe sends one candidate per planner call, records every attempted candidate result, selects either an explicit requested label or the first successful candidate, and only executes the selected post-replay trajectory when requested.

**Tech Stack:** Python, pytest, GenManip EvalClient planner route, Isaac Sim 4.1, cuRobo `MotionGen.plan_single`, LabUtopia evidence manifests.

---

## Current Evidence

The latest live 5D run proves the first bridge path is useful but the old follow-up target is not:

```text
evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0200/summary_compact.json
bridge_replay.available_action_points=150
bridge_replay.executed_steps=150
bridge_replay.reached_joint_target=true
bridge_replay.final_joint_target_abs_max_rad=7.128715515136719e-05
post_replay_replan.waypoint_label=approach_pre
post_replay_replan.selected_plan_success=false
post_replay_replan.selected_planner_record.planner_debug.status=MotionGenStatus.IK_FAIL
```

Decision: 5E should not keep tuning only `approach_pre`. It should expose a post-bridge follow-up waypoint family so the live post-replay state can be matched to a nearby, reachable continuation.

## Reference Pattern

EBench `microwave.yml` uses manual `custom_motion` keypoints rather than a fixed joint replay:

```text
configs/tasks/ebench/mobile_manip/test_mini/microwave.yml:
  generation_config.action_path.mode=manual
  actions[].type=custom_motion
  motion_list.right[].type=object_frame
  rel_object_uid=microwave

genmanip/extensions/skills/default/custom_motion/custom_motion.py:
  object_frame targets are converted with pose_frame_to_world(...)
  each target is passed to embodiment.plan_pose(...)

genmanip/utils/planner/curobo/base.py:
  CuroboPlanner.plan calls MotionGen.plan_single(...)
```

Implication for DryingBox: keep the bridge as a planned object-frame segment, then treat the continuation as another object-frame planning problem from the post-replay robot state.

## File Map

GenManip worktree:

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
```

Files to modify:

```text
standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
tests/labutopia_poc/test_online_open_door_oracle_probe.py
```

LabUtopia documentation:

```text
docs/superpowers/plans/2026-07-05-eos2-post-bridge-followup-waypoint-family.md
docs/labutopia_lab_poc/expert_oracle_score_plan.md
docs/labutopia_lab_poc/aan_consumer_handoff.md
docs/labutopia_lab_poc/evidence_manifests/README.md
```

## Public Contract

Add a repeatable CLI argument for post-replay follow-up candidates:

```text
--planner-trajectory-post-replay-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ
```

Each argument creates one object-frame waypoint:

```python
{
    "label": LABEL,
    "type": "object_frame",
    "rel_object_uid": args.object_frame_rel_object_uid,
    "translation": [X, Y, Z],
    "orientation": normalized_wxyz,
    "grasp": False,
    "arm": "default",
    "explicit_planner_waypoint": True,
    "waypoint_source": "planner_trajectory_post_replay_extra_object_frame_waypoint",
}
```

Planner-call rule:

```text
Preplan bridge selection remains one normal planner call.
Post-replay candidate mode sends each candidate in a separate planner call.
Do not send the whole candidate family in one call, because the server-side
object_frame_waypoint_planner advances local sim_js after a successful waypoint
inside a single call. A candidate family represents alternatives, not a
continuous waypoint chain.
```

Selection rule:

```text
If --planner-trajectory-post-replay-waypoint-label is supplied:
  select that label.
Else if post-replay extra candidates are supplied:
  attempt candidates in input order and select the first candidate with plan_success=true.
Else:
  preserve 5D behavior and select approach_pre.
```

Summary additions:

```text
post_replay_replan.requested_waypoint_label
post_replay_replan.selected_waypoint_label
post_replay_replan.candidate_count
post_replay_replan.successful_candidate_count
post_replay_replan.failure_status_counts
post_replay_replan.planner_records
post_replay_replan.selected_planner_record
```

Backward compatibility:

```text
post_replay_replan.waypoint_label remains present and mirrors selected_waypoint_label.
post_replay_replan.execution.waypoint_label mirrors selected_waypoint_label.
If no new post-replay candidates are passed, the old approach_pre-only behavior is unchanged.
```

## Claim Boundary

Allowed after Stage 5E code and unit tests:

```text
The probe can request multiple post-replay object-frame follow-up candidates.
The probe can select the first successful post-replay planner record.
The probe can execute the selected post-replay joint trajectory and report readback.
```

Still forbidden until live evidence proves it:

```text
stable grasp
micro-pull readiness
door opened
Expert Oracle Score
policy score
official leaderboard score
full task completion
```

## Task 1: Add Failing Unit Test

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`

- [x] Add `test_planner_trajectory_execution_readback_sweeps_post_replay_extra_waypoints_and_selects_first_success`.
- [x] Fake first planner call succeeds only for the explicit bridge label.
- [x] Fake second planner call receives only the first post-replay extra label and fails it with `MotionGenStatus.IK_FAIL`.
- [x] Fake third planner call receives only the second post-replay extra label, succeeds it, and returns `trajectory_action_joint_positions`.
- [x] Assert the summary records `candidate_count == 2`, `successful_candidate_count == 1`, `selected_waypoint_label == "post_bridge_near"`, and post-replay execution sends the follow-up action.

Run:

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "sweeps_post_replay_extra"
```

Expected before implementation:

```text
FAIL
```

## Task 2: Add Post-Replay Candidate Payload Builder

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [x] Add `_explicit_post_replay_object_frame_waypoints_from_args(args, rel_object_uid=...)`.
- [x] Use the same numeric validation and quaternion normalization rules as `_explicit_planner_object_frame_waypoints_from_args`.
- [x] Add `build_dryingbox_post_replay_object_frame_planner_waypoint_payload(args)` that returns the post-replay explicit candidates when provided, otherwise the existing default DryingBox waypoint payload.
- [x] In candidate mode, pass one candidate payload at a time to `plan_object_frame_waypoints(...)`.

Run:

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "sweeps_post_replay_extra or post_replay"
```

Expected after minimal implementation:

```text
PASS
```

## Task 3: Add Selection and Summary Fields

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [x] Compute `post_replay_requested_waypoint_label` from `args.planner_trajectory_post_replay_waypoint_label`.
- [x] When no explicit label is provided and candidates exist, select the first successful candidate.
- [x] Add candidate count, success count, and failure status counts to `summary["post_replay_replan"]`.
- [x] Preserve `summary["post_replay_replan"]["waypoint_label"]` for existing docs/tests.

Run:

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "planner_trajectory_execution_readback"
```

Expected:

```text
All selected tests pass.
```

## Task 4: Add CLI Argument

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [x] Add `--planner-trajectory-post-replay-extra-object-frame-waypoint` with `action="append"` and `nargs=8`.
- [x] Set `--planner-trajectory-post-replay-waypoint-label` default to `None`.
- [x] In runtime code, default back to `approach_pre` only when no explicit post-replay candidates are present.

Run:

```bash
/usr/bin/python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
```

Expected:

```text
exit 0
```

## Task 5: Live 5E Evidence

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_live_20260705_5e_*/`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] Run the probe with the known successful bridge waypoint as the primary selected waypoint.
- [x] Pass a small post-replay extra candidate family around the handle side.
- [x] Record whether any candidate replans from the post-bridge state.
- [x] Preserve claim guards even if a candidate succeeds.

Expected output:

```text
Either PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY
or FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY with candidate-level planner diagnostics.
```

## Verification Checklist

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "sweeps_post_replay_extra or post_replay or planner_trajectory_execution_readback"
/usr/bin/python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
git diff --check -- standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
```

Completion requires code evidence and at least one live or explicitly blocked live 5E evidence manifest.
This condition is now satisfied by the 2026-07-05 live blocked evidence below.

## 2026-07-05 Code Checkpoint

Machine-readable manifest:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_code_checkpoint_20260705.json
```

Verified:

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "sweeps_post_replay_extra"
# 1 passed, 273 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "planner_trajectory_execution_readback or post_replay"
# 7 passed, 267 deselected

/usr/bin/python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
# exit 0

git diff --check -- standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
# exit 0
```

## 2026-07-05 Live 5E Evidence

Machine-readable compact manifest:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_live_20260705_5e_0300/summary_compact.json
```

Run result:

```text
submit.exitcode=0
probe.exitcode=0
status=FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY
bridge.available_action_points=150
bridge.executed_steps=150
bridge.reached_joint_target=true
bridge.final_joint_target_abs_max_rad~=7.12e-05
post_replay.candidate_mode=true
post_replay.candidate_count=4
post_replay.attempted_candidate_labels=post_bridge_to_approach_pre_f_0p20,post_bridge_to_approach_pre_f_0p40,post_bridge_to_approach_pre_f_0p60,post_bridge_to_approach_pre_f_0p80
post_replay.successful_candidate_count=0
post_replay.failure_status_counts.MotionGenStatus.IK_FAIL=4
```

Interpretation:

```text
The probe, server, worker reset, planner endpoint, and first bridge replay are
closed for this diagnostic path. The remaining blocker is target-family
reachability after the bridge replay: all four candidates that interpolate from
the post-bridge pose toward stale approach_pre are IK-infeasible. The next sweep
should vary wrist orientation and local handle-side translation around the
post-bridge pose itself instead of continuing to interpolate directly toward
approach_pre.
```

Claim boundary remains unchanged: this evidence does not prove stable grasp,
micro-pull readiness, door opened, Expert Oracle Score, policy score, official
score, or full task completion.

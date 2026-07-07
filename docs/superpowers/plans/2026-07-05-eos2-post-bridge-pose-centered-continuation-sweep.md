# EOS2 Post-Bridge Pose-Centered Continuation Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a 5F live diagnostic that finds whether DryingBox can plan and replay a small post-bridge continuation from the proven bridge pose, without falling back to the stale reset-time `approach_pre` target.

**Architecture:** Keep GenManip code unchanged for this stage. Reuse the existing `planner-trajectory-execution-readback` probe and its repeatable `--planner-trajectory-post-replay-extra-object-frame-waypoint` CLI. Candidate order prioritizes small spatial continuations around the proven bridge pose, then orientation-only wrist adjustments as diagnostic fallback.

**Tech Stack:** LabUtopia evidence manifests, GenManip online probe, EBench EvalClient, Isaac Sim 4.1, cuRobo `MotionGen.plan_single`, JSON compact evidence.

---

## Current Evidence

5E live evidence proves the first bridge segment and narrows the remaining blocker:

```text
evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_live_20260705_5e_0300/summary_compact.json
bridge_label=approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity
bridge_xyz=[0.0010228951554745458, -0.11657822728157047, 0.014903118610382071]
bridge_wxyz=[0.9478491886430741, -0.209547848787944, -0.22171216853953848, -0.09227854018408849]
bridge_action_points=150
bridge_executed_steps=150
bridge_reached_joint_target=true
bridge_final_joint_target_abs_max_rad=7.11679458618164e-05
post_bridge_candidate_count=4
post_bridge_successful_candidate_count=0
post_bridge_failure_status_counts.MotionGenStatus.IK_FAIL=4
```

Interpretation:

```text
The server, worker lifecycle, planner endpoint, bridge planner trajectory export,
bridge replay, and readback are all working. The blocker is the follow-up target
family. The 5E candidates moved from the bridge toward the stale reset-time
approach_pre target while holding the bridge quaternion fixed. Even the smallest
candidate returned IK_FAIL, so 5F must search near the post-bridge pose itself.
```

## Candidate Policy

The 5F sweep uses 12 ordered candidates. The first six are real spatial
continuations; the last six are orientation-only fallback diagnostics.

Do not include the exact bridge hold pose in the selectable candidate list. It is
likely to succeed trivially and would stop the first-success sweep without
proving any continuation.

### Spatial Candidates

Use local bridge-to-target slerp candidates first because 5E held the bridge
quaternion fixed; these two candidates test whether the missing orientation
slerp was the reason the direct line failed. Then use single-axis local
translation candidates to isolate translation direction.

```text
post_bridge_local_slerp_f_0p7625
xyz  = [-0.0030282496022991934, -0.11074931591749199, 0.014157962679862968]
wxyz = [0.95289357041153944, -0.19941342353258021, -0.21098943665149894, -0.087815645558450436]

post_bridge_local_slerp_f_0p775
xyz  = [-0.0070793943600729325, -0.10492040455341345, 0.013412806749343864]
wxyz = [0.95768729660390195, -0.18922654322020868, -0.20021120467358822, -0.083329651310869515]

post_bridge_local_y_p006_q_bridge
xyz  = [0.0010228951554745458, -0.11057822728157047, 0.014903118610382071]
wxyz = [0.9478491886430741, -0.209547848787944, -0.22171216853953848, -0.09227854018408849]

post_bridge_local_x_m006_q_bridge
xyz  = [-0.004977104844525454, -0.11657822728157047, 0.014903118610382071]
wxyz = [0.9478491886430741, -0.209547848787944, -0.22171216853953848, -0.09227854018408849]

post_bridge_local_z_m006_q_bridge
xyz  = [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071]
wxyz = [0.9478491886430741, -0.209547848787944, -0.22171216853953848, -0.09227854018408849]

post_bridge_local_y_p012_q_bridge
xyz  = [0.0010228951554745458, -0.10457822728157047, 0.014903118610382071]
wxyz = [0.9478491886430741, -0.209547848787944, -0.22171216853953848, -0.09227854018408849]
```

### Orientation-Only Fallback Candidates

These candidates keep the bridge translation fixed and rotate the wrist by
approximately `±8deg` around object-frame axes. They diagnose whether the robot
can at least adjust wrist orientation from the post-bridge state.

```text
post_bridge_ori_x_m08
xyz  = [0.0010228951554745458, -0.11657822728157047, 0.014903118610382071]
wxyz = [0.930922956646159, -0.275156017801106, -0.214735063274693, -0.107519613361585]

post_bridge_ori_x_p08
xyz  = [0.0010228951554745458, -0.11657822728157047, 0.014903118610382071]
wxyz = [0.960157594670387, -0.142918783719164, -0.227609114405688, -0.0765878952346219]

post_bridge_ori_y_m08
xyz  = [0.0010228951554745458, -0.11657822728157047, 0.014903118610382071]
wxyz = [0.930074416594792, -0.215474426325632, -0.287290705881162, -0.0774364352859891]

post_bridge_ori_y_p08
xyz  = [0.0010228951554745458, -0.11657822728157047, 0.014903118610382071]
wxyz = [0.961006134721755, -0.202600375194637, -0.155053471799220, -0.106671073310217]

post_bridge_ori_z_m08
xyz  = [0.0010228951554745458, -0.11657822728157047, 0.014903118610382071]
wxyz = [0.939103250092776, -0.193571541696653, -0.235789407852305, -0.158172371339074]

post_bridge_ori_z_p08
xyz  = [0.0010228951554745458, -0.11657822728157047, 0.014903118610382071]
wxyz = [0.951977301223771, -0.224503259823616, -0.206554769828077, -0.0259351372571322]
```

## Claim Boundary

Allowed after a 5F live run:

```text
5F can report whether one small post-bridge continuation candidate planned.
If selected and executed, 5F can report planner trajectory action count,
executed steps, final joint target error, and candidate-level planner status.
```

Still forbidden:

```text
stable grasp
micro-pull readiness
door opened
Expert Oracle Score
policy score
official leaderboard score
full task completion
```

## Task 1: Prepare Live Evidence Directory

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/`
- Create: `run.vars`
- Create: `server.command.txt`
- Create: `submit.command.txt`
- Create: `probe.command.txt`

- [x] Use a fresh `run_id`, `RAY_TMPDIR`, port, and output filenames.
- [x] Use the same conda env and CUDA 11 library path as the successful 5E run.
- [x] Keep `--planner-trajectory-post-replay-execute` enabled so a selected candidate is replayed and read back.

## Task 2: Run 5F Live Probe

**Files:**
- Write: `server.log`
- Write: `submit.log`, `submit.stderr.log`, `submit.exitcode`
- Write: `probe.log`, `probe.stderr.log`, `probe.exitcode`
- Write: `planner_trajectory_post_bridge_pose_centered_sweep_summary.json`
- Write: `planner_trajectory_post_bridge_pose_centered_sweep_trace.jsonl`

- [x] Start Ray eval server from the GenManip worktree.
- [x] Submit `ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`.
- [x] Run the 5F probe command.
- [x] Stop the eval server after probe completion.
- [x] Confirm no listener remains on the 5F port.

## Task 3: Compact Evidence

**Files:**
- Create: `summary_compact.json`

- [x] Parse the full summary JSON.
- [x] Preserve selected bridge result, primary trajectory replay result, candidate labels, selected candidate, failure status counts, and post-replay execution readback.
- [x] Preserve claim guards and forbidden claims.
- [x] Validate with `python -m json.tool`.

## Task 4: Update Documentation

**Files:**
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/superpowers/plans/2026-07-05-eos2-post-bridge-pose-centered-continuation-sweep.md`

- [x] Record live status and candidate-level outcome.
- [x] If a spatial candidate succeeds, mark the next action as close/grasp staging.
- [x] If only orientation-only succeeds, mark the next action as spatial continuation after wrist realignment. Not applicable for 5F because a spatial candidate succeeded.
- [x] If all candidates fail, mark the next action as smaller-radius planner target family or a planner-seed/IK-branch audit. Not applicable for 5F because a spatial candidate succeeded.

## 2026-07-05 Live 5F Evidence

Machine-readable compact manifest:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json
```

Run result:

```text
submit.exitcode=0
probe.exitcode=0
status=PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY
bridge.available_action_points=150
bridge.executed_steps=150
bridge.reached_joint_target=true
bridge.final_joint_target_abs_max_rad=8.0108642578125e-05
post_replay.candidate_count=12
post_replay.attempted_candidate_count=5
post_replay.selected_waypoint_label=post_bridge_local_z_m006_q_bridge
post_replay.selected_plan_success=true
post_replay.available_action_points=33
post_replay.execution.executed_steps=33
post_replay.execution.reached_joint_target=true
post_replay.execution.final_joint_target_abs_max_rad=6.794929504394531e-05
post_replay.failure_status_counts.MotionGenStatus.IK_FAIL=4
```

Interpretation:

```text
The first successful post-bridge continuation is a local -0.006m move along the
handle object-frame Z axis while preserving the bridge quaternion. This proves
the oracle is no longer blocked at the bridge pose. It does not prove grasp,
micro-pull, door opening, or score. The next stage should fix this continuation
as a pre-grasp movement segment and test close/grasp staging separately.
```

## Verification Checklist

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json >/dev/null
git diff --check -- docs/labutopia_lab_poc/evidence_manifests/README.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/aan_consumer_handoff.md docs/superpowers/plans/2026-07-05-eos2-post-bridge-pose-centered-continuation-sweep.md
```

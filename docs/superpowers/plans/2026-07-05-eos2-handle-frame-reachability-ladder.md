# EOS-2 Handle-Frame Reachability Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Task 5L `MotionGenStatus.IK_FAIL` into a smaller Task 5M reachability ladder that tests centerline / inner-face / bilateral-contact-frame handle targets before any micro-pull or score work.

**Architecture:** Keep the current GenManip online probe and LabUtopia evidence manifest workflow. Do not continue the 5L single large clamped X/Y correction; instead use the existing `geometry-aware` and `centerline` candidate machinery to produce a tiny reviewed ladder. Before live evidence, bind those generated candidates back into the `planner-trajectory-execution-readback` post-replay route used by 5L; a default-oracle `centerline` run is a different diagnostic line and cannot be reported as the 5L follow-up.

**Tech Stack:** LabUtopia docs, GenManip `standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`, Isaac Sim 4.1, cuRobo `MotionGen.plan_single`, EBench / GenManip task YAML, JSON evidence manifests, pytest, conda envs `embodied-eval-os-sim-isaacsim41-genmanip-py310` and `embodied-eval-os-isaacsim41-py310`.

---

## Evidence Boundary

Task 5L live evidence:

- Compact manifest: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json`
- Classification: `BLOCKED_5L_HANDLE_FRAME_TARGET_IK`
- Positive signal: the explicit bridge waypoint still generated and replayed `151` action points; `trajectory_execution.reached_joint_target=true`; final joint target error is about `7.13e-05 rad < 0.02 rad`.
- First failed gate: `post_replay_replan.failure_status_counts={"MotionGenStatus.IK_FAIL": 1}` for `5l_cf_handle_right_025_clamped_xy12_zp02`.
- Consequence: `post_replay_replan.available_action_points=0`; close-hold is skipped with `no_post_replay_worker_state`; retention telemetry is unavailable.
- Claim boundary: stable grasp, micro-pull readiness, door-open readback, `Expert Oracle Score`, policy score, official score, and full task completion remain false.

Task 5K-A retained diagnostic input:

- Compact manifest: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`
- Classification: `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`
- Tail role gaps after close-hold:
  - `panda_leftfinger`: `axis_gap_abs_m=[0.130159870635, 0.055287809085, 0.0]`
  - `panda_rightfinger`: `axis_gap_abs_m=[0.084393376008, 0.067267486749, 0.0]`
- Retention hard facts: `tail_bilateral_overlap_records=0`, `tail_required_roles_near_records=0`, `tail_physx_required_roles_contact_records=0`.

GenManip candidate machinery already present:

- `build_geometry_aware_grasp_contact_candidate` in `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- `build_centerline_grasp_contact_candidate` in the same file
- CLI surface: `--grasp-contact-pose-mode {offset,geometry-aware,centerline}`, `--grasp-centerline-capture-mode {solid-overlap,inner-face-corridor}`, `--grasp-centerline-selection-objective {inner-face-corridor,bilateral-contact-frame}`
- Route boundary resolved at code level on 2026-07-05: `run_planner_trajectory_execution_readback` still supports explicit `--planner-trajectory-post-replay-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`, and now also supports generated post-replay centerline candidates through `--planner-trajectory-post-replay-candidate-source centerline`. This is code/test evidence only; no 5M live reachability claim exists yet.
- Fresh focused unit check on 2026-07-05:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "contact_frame_recovery_candidates or geometry_aware_grasp_contact or centerline_grasp_contact" -q
```

Expected output already observed for this checkpoint:

```text
12 passed, 265 deselected
```

## Root-Cause Hypothesis

Task 5L did not fail because the server, reset, explicit bridge waypoint, action replay, or controller readback path regressed. It failed after the bridge, when the generated handle-frame target was handed to cuRobo for post-replay replan. The most likely failure class is that the 5L target moved the end-effector center by too much or into a poor wrist/handle geometry for the current post-bridge robot state.

Task 5M therefore must test smaller and more geometry-constrained targets. It must not be framed as a contact retention fix until a candidate first produces post-replay action points and executes close-hold.

Independent review result: the main rung order should be `centerline` -> `inner-face-corridor` -> `bilateral-contact-frame`; `geometry-aware` is only a baseline fallback rung. The review also flags one recurrent pitfall: the 5K / 5L signed gaps are world-AABB diagnostic gaps, not direct object-frame X/Y offsets. Task 5M must not convert those numbers one-for-one into new object-frame correction commands.

Route-contract audit result: a 5M live run must not use default oracle mode as if it were 5L continuation evidence. The current safe path is either:

1. generate/review centerline candidates, convert the chosen world target into an object-frame `planner_trajectory_post_replay_extra_object_frame_waypoint`, and run the existing 5L planner-trajectory probe; or
2. add a TDD-protected GenManip bridge that generates the centerline candidate inside `run_planner_trajectory_execution_readback` after bridge replay, then calls the same post-replay candidate-sweep planner path.

2026-07-05 follow-up decision: after the later `mesh-open-face` full planner/readback and bounded
bridge-to-near sanity, the contact/near offset route satisfied its stop condition. The next execution
entry is `docs/superpowers/plans/2026-07-05-eos2-approach-seed-robot-staging-redesign.md`. That plan
keeps 5M evidence as historical input, but moves the active question to wrist orientation source,
approach seed, and robot staging before any more contact, retention, micro-pull, or score work.

## File Responsibilities

- `docs/superpowers/plans/2026-07-05-eos2-handle-frame-reachability-ladder.md`: this execution plan and gate contract.
- `docs/labutopia_lab_poc/evidence_manifests/README.md`: evidence index and PM-readable status.
- `docs/labutopia_lab_poc/aan_consumer_handoff.md`: cross-team handoff status.
- `docs/labutopia_lab_poc/expert_oracle_score_plan.md`: PM-facing Expert Oracle Score status and no-claim boundary.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`: existing candidate generation and live probe harness.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`: focused tests for candidate generation and summary guards.

## Acceptance Rules

- A prepared 5M manifest may claim only `PREPARED_REVIEW_NOT_LIVE_EVIDENCE`.
- A live 5M run may claim `post_replay_replan` reachability only if `selected_plan_success=true` and `available_action_points>0`.
- A live 5M run may claim close-hold execution only if `post_replay_close_hold.executed_steps>0` and readback reaches the configured joint tolerance.
- A live 5M run may claim retention readiness only if `retention_pass=true`, `tail_bilateral_overlap_records>0`, `tail_required_roles_near_records>0`, and `tail_physx_required_roles_contact_records>0`.
- Any earlier failure must stop at the first failed gate and keep the no-claim guards false.
- The candidate review must treat `geometry-aware` as a fallback sanity rung, not the primary fix, because it does not enforce the bilateral contact-frame objective.
- World-AABB signed gap values may be used to explain why 5L was too coarse, but they must not be copied as raw object-frame X/Y command deltas.
- A generated `centerline` live run that is route-bound but produces no numeric post-replay candidate because of missing/invalid live state must classify as `BLOCKED_5M_CENTERLINE_SOLVER_INPUT`, not as IK reachability or contact retention.

Required classification strings:

```text
PREPARED_5M_REVIEW_NOT_LIVE_EVIDENCE
BLOCKED_5M_ROUTE_CONTRACT_NOT_BOUND
BLOCKED_5M_CENTERLINE_SOLVER_INPUT
BLOCKED_5M_CENTERLINE_REACHABILITY_IK
BLOCKED_5M_POST_REPLAY_EXECUTION_READBACK
BLOCKED_5M_CONTACT_RETENTION
PASS_5M_RETENTION_READY_FOR_MICRO_PULL_PLAN
```

### Task 1: Freeze 5L Input Evidence

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json`
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [x] **Step 1: Validate the JSON inputs**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json >/dev/null
```

Expected: both commands exit `0`.

- [x] **Step 2: Extract the first failed gate**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python - <<'PY'
import json
p = "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json"
with open(p) as f:
    d = json.load(f)
print("classification=", d["classification"])
print("bridge_reached=", d["trajectory_execution"]["reached_joint_target"])
print("post_replay_failure_counts=", d["post_replay_replan"]["failure_status_counts"])
print("post_replay_action_points=", d["post_replay_replan"]["available_action_points"])
print("close_hold_skipped=", d["post_replay_close_hold"]["skipped_reason"])
print("claim_guards=", d["claim_guards"])
PY
```

Expected:

```text
classification= BLOCKED_5L_HANDLE_FRAME_TARGET_IK
bridge_reached= True
post_replay_failure_counts= {'MotionGenStatus.IK_FAIL': 1}
post_replay_action_points= 0
close_hold_skipped= no_post_replay_worker_state
claim_guards= {'door_opened': False, 'expert_oracle_score': False, 'full_collision_aware_task_completion': False, 'micro_pull_readiness': False, 'official_leaderboard_score': False, 'policy_score': False, 'stable_grasp': False}
```

### Task 2: Keep Candidate Generator Tests Green

**Files:**
- Read/Test: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
- Read: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [x] **Step 1: Run focused candidate-generation regression**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "contact_frame_recovery_candidates or geometry_aware_grasp_contact or centerline_grasp_contact" -q
```

Expected:

```text
12 passed, 265 deselected
```

- [x] **Step 2: If this test regresses, stop before live runs**

If the command fails, classify the stage as:

```text
BLOCKED_5M_CENTERLINE_SOLVER_INPUT
```

Then update only docs with the failing pytest output and do not run Isaac live evidence.

### Task 3: Prepare 5M Candidate Review Manifest

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_review_20260705_5m_candidates.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [x] **Step 1: Create the manifest with three ordered candidates**

Create this JSON exactly first; later live evidence may add measured values, but the review manifest must stay diagnostic-only:

```json
{
  "stage": "EOS-2 Task 5M",
  "status": "PREPARED_5M_REVIEW_NOT_LIVE_EVIDENCE",
  "source_5l_summary": "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json",
  "source_5k_summary": "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json",
  "diagnostic_only": true,
  "candidate_order": [
    {
      "candidate_id": "5m_centerline_inner_face_bilateral_zero_bias",
      "grasp_contact_pose_mode": "centerline",
      "grasp_centerline_capture_mode": "inner-face-corridor",
      "grasp_centerline_selection_objective": "bilateral-contact-frame",
      "grasp_contact_center_offset_y_m": 0.0,
      "grasp_contact_center_offset_z_m": 0.0,
      "grasp_centerline_role_overlap_margin_m": 0.0,
      "grasp_centerline_max_center_shift_m": 0.012,
      "purpose": "Prefer a handle-centered candidate that satisfies the predicted bilateral contact-frame interval before applying any 5L-style large correction."
    },
    {
      "candidate_id": "5m_centerline_inner_face_bilateral_half_5l_shift",
      "grasp_contact_pose_mode": "centerline",
      "grasp_centerline_capture_mode": "inner-face-corridor",
      "grasp_centerline_selection_objective": "bilateral-contact-frame",
      "grasp_contact_center_offset_y_m": 0.006,
      "grasp_contact_center_offset_z_m": -0.003,
      "grasp_centerline_role_overlap_margin_m": 0.0,
      "grasp_centerline_max_center_shift_m": 0.012,
      "purpose": "Use half of the 5L Y/Z correction while keeping the centerline gate responsible for deciding the final EE center."
    },
    {
      "candidate_id": "5m_geometry_aware_handle_center_fallback",
      "grasp_contact_pose_mode": "geometry-aware",
      "grasp_contact_center_offset_y_m": 0.0,
      "grasp_contact_center_offset_z_m": 0.0,
      "purpose": "Fallback sanity candidate: handle-bbox-center target without the centerline solver, used only to separate centerline solver-input failure from general reachability failure."
    }
  ],
  "no_claim_guards": {
    "stable_grasp": false,
    "micro_pull_readiness": false,
    "door_opened": false,
    "expert_oracle_score": false,
    "policy_score": false,
    "official_leaderboard_score": false,
    "full_collision_aware_task_completion": false
  }
}
```

- [x] **Step 2: Validate the manifest**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_review_20260705_5m_candidates.json >/dev/null
```

Expected: exit `0`.

### Task 4: Bind 5M Candidates To The 5L Planner-Trajectory Route

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_review_20260705_5m_candidates.json`
- Read: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Test: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
- Modify if implementing bridge: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [x] **Step 1: Audit the route boundary**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
rg -n "def run_planner_trajectory_execution_readback|grasp_contact_pose_mode|planner_trajectory_post_replay_extra_object_frame_waypoint|build_centerline_grasp_contact_candidate" standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
```

Expected finding:

```text
run_planner_trajectory_execution_readback consumes planner_trajectory_post_replay_extra_object_frame_waypoint.
grasp_contact_pose_mode and centerline candidate generation are handled by the default oracle path.
Therefore a 5M default-oracle centerline run is not directly comparable to 5L planner-trajectory post-replay evidence.
```

- [x] **Step 2: Choose and implement the route binding**

Implemented route:

```text
After the primary bridge replay has produced last_replay_worker_obs, GenManip can now
build a centerline candidate from the post-replay debug state, calibrate finger envelopes
from post-replay contact_debug closest-pair AABBs, optionally apply inner-face-corridor /
bilateral-contact-frame selection, convert the selected world contact target into an
object-frame waypoint relative to obj_DryingBox_01_handle, and feed that waypoint into
the existing post_replay_candidate_sweep planner path.
```

Code checkpoint:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_route_binding_code_checkpoint_20260705.json
```

- [x] **Step 3: Verify route binding before live**

Verification run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "post_replay_candidate_object_frame or post_replay_centerline_candidate_source or builds_post_replay_centerline_candidate_from_live_debug or sweeps_post_replay_extra_waypoints or centerline_grasp_contact_candidate or inner_face_capture_candidate" -q
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "planner_trajectory_execution_readback or post_replay" -q
PYTHONPATH=. "$PY" -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
```

Observed:

```text
21 passed, 259 deselected
11 passed, 269 deselected
py_compile exit 0
```

Claim boundary: this removes `BLOCKED_5M_ROUTE_CONTRACT_NOT_BOUND` for code readiness only. It does not claim live 5M reachability, close-hold, retention, stable grasp, micro-pull, door-open, `Expert Oracle Score`, policy score, official score, or full task completion.

### Task 5: Run One 5M Live Candidate At A Time

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_review_20260705_5m_candidates.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_<candidate_id>/`

- [x] **Step 1: Start the GenManip server in a foreground session**

Use the same runtime env as the previous live evidence:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
GENMANIP_WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
GENMANIP_CLIENT_SRC=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src
RUN_ID=labutopia_eos2_handle_frame_reachability_ladder_20260705_5m_centerline_inner_face_bilateral_zero_bias
SERVER_RUN_ID=${RUN_ID}_server
PYTHONNOUSERSITE=1 \
RAY_ADDRESS=local \
RAY_USAGE_STATS_ENABLED=0 \
RAY_TMPDIR=/tmp/r5m18451 \
LABUTOPIA_ORACLE_DEBUG_OBS=1 \
LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1 \
GENMANIP_VERBOSE=1 \
PATH=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin:$PATH \
PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback \
LD_LIBRARY_PATH=/isaac-sim/exts/omni.isaac.ml_archive/pip_prebundle/nvidia/cuda_runtime/lib:/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin:/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps:/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/torch/lib:${LD_LIBRARY_PATH:-} \
"$PY" -u ray_eval_server.py --host 127.0.0.1 --port 18451 --run_id "$SERVER_RUN_ID" --no_save_process --episode_recorder_save_every 0 --reset_timeout 1200 --step_timeout 1200 --load_config_timeout 300
```

Expected: server stays running and listens on `127.0.0.1:18451`. Keep it foreground and stop it with Ctrl-C after the probe.

- [x] **Step 2: Submit and run the first route-bound centerline candidate**

Create output directory:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
mkdir -p docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias
```

Submit the task config after the server is ready. The task config belongs to `submit`, not to `ray_eval_server.py`:

```bash
PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
RUN_ID=labutopia_eos2_handle_frame_reachability_ladder_20260705_5m_centerline_inner_face_bilateral_zero_bias
TASK_CONFIG=ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback \
"$PY" - <<PY
from genmanip_client.submit import start_job
start_job("http://127.0.0.1:18451", ["$TASK_CONFIG"], "$RUN_ID")
PY
```

Task 4 has produced the generated route-binding path, so this live run must not hand-copy a centerline target into an 8-field waypoint. Write the exact command used to `docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/probe.command.txt` before executing it. The command must use:

```text
--probe-mode planner-trajectory-execution-readback
--planner-trajectory-waypoint-label approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity
--planner-trajectory-extra-object-frame-waypoint approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity 0.0010228951554745458 -0.11657822728157047 0.014903118610382071 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849
--planner-trajectory-post-replay-replan
--planner-trajectory-post-replay-candidate-source centerline
--planner-trajectory-post-replay-candidate-label 5m_centerline_inner_face_bilateral_zero_bias
--grasp-centerline-capture-mode inner-face-corridor
--grasp-centerline-selection-objective bilateral-contact-frame
--grasp-contact-center-offset-y-m 0.0
--grasp-contact-center-offset-z-m 0.0
--grasp-centerline-role-overlap-margin-m 0.0
--grasp-centerline-max-center-shift-m 0.012
--planner-trajectory-post-replay-execute
--planner-trajectory-post-replay-close-hold-steps 15
--post-close-min-bilateral-overlap-records 15
--post-close-retention-tail-window 15
--post-close-retention-require-physx-contact
```

The required generated-candidate flag must be present exactly once in `probe.command.txt`:

```text
flag_name=--planner-trajectory-post-replay-candidate-source
value=centerline
label=5m_centerline_inner_face_bilateral_zero_bias
```

Expected after a valid route-bound command exists: the command writes `summary.json` and `trace.jsonl`. This run is diagnostic; even if it produces contact telemetry, it does not claim score.

- [x] **Step 3: Stop the server and verify the port is free**

After Ctrl-C in the server session, run:

```bash
python - <<'PY'
import socket
s = socket.socket()
try:
    s.bind(("127.0.0.1", 18451))
except OSError as exc:
    raise SystemExit(f"port 18451 still busy: {exc}")
finally:
    s.close()
print("port_18451_free=true")
PY
```

Expected:

```text
port_18451_free=true
```

Observed 2026-07-05:

```text
server_started=true
submit_exit=0
probe_exit=0
port_18451_free=true
summary=docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary.json
trace=docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/trace.jsonl
```

The probe command contained the generated route-binding flag exactly once:

```text
--planner-trajectory-post-replay-candidate-source centerline
--planner-trajectory-post-replay-candidate-label 5m_centerline_inner_face_bilateral_zero_bias
```

Live result boundary:

```text
status=FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY
classification=BLOCKED_5M_CENTERLINE_SOLVER_INPUT
first_failed_gate=post_replay_centerline_candidate_input_error
bridge_replay.executed_steps=151
bridge_replay.reached_joint_target=true
bridge_replay.final_joint_target_abs_max_rad=8.499622344970703e-05
post_replay_replan.candidate_source=centerline
post_replay_replan.candidate_count=0
post_replay_replan.available_action_points=0
post_replay_replan.replan_error=TypeError("float() argument must be a string or a real number, not 'NoneType'")
post_replay_close_hold.executed_steps=0
post_replay_close_hold.skipped_reason=no_post_replay_worker_state
```

PM wording: 5M has now proved that the generated `centerline` route is wired into the same
planner-trajectory post-replay path as 5L, and the bridge trajectory still executes correctly.
The new blocker is earlier than IK/contact retention: after bridge replay, the generated
centerline candidate path did not produce a valid numeric post-replay waypoint and failed with a
`NoneType` conversion error. Therefore this run cannot claim centerline reachability, close-hold,
retention, stable grasp, micro-pull, door-open, `Expert Oracle Score`, policy score, official
score, or full task completion.

### Task 6: Classify The 5M Live Result

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary_compact.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [x] **Step 1: Build compact classification**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python - <<'PY'
import json
from pathlib import Path

root = Path("docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias")
summary_path = root / "summary.json"
compact_path = root / "summary_compact.json"
with summary_path.open() as f:
    d = json.load(f)

pr = d.get("post_replay_replan") or {}
close = d.get("post_replay_close_hold") or {}
retention = close.get("retention_summary") or d.get("retention_summary") or d.get("post_close_retention_summary") or {}
claim_guards = {
    "stable_grasp": False,
    "micro_pull_readiness": False,
    "door_opened": False,
    "expert_oracle_score": False,
    "policy_score": False,
    "official_leaderboard_score": False,
    "full_collision_aware_task_completion": False,
}
route_bound = pr.get("candidate_source") == "centerline" and pr.get("enabled") is True and pr.get("attempted") is True
if not route_bound:
    classification = "BLOCKED_5M_ROUTE_CONTRACT_NOT_BOUND"
elif pr.get("candidate_count", 0) == 0 and pr.get("replan_error"):
    classification = "BLOCKED_5M_CENTERLINE_SOLVER_INPUT"
elif pr.get("candidate_count", 0) > 0 and pr.get("selected_plan_success") is not True:
    classification = "BLOCKED_5M_CENTERLINE_REACHABILITY_IK"
elif retention.get("retention_pass") is True:
    classification = "PASS_5M_RETENTION_READY_FOR_MICRO_PULL_PLAN"
else:
    classification = "BLOCKED_5M_CONTACT_RETENTION"

compact = {
    "stage": "EOS-2 Task 5M",
    "candidate_label": "5m_centerline_inner_face_bilateral_zero_bias",
    "classification": classification,
    "status": d.get("status"),
    "diagnostic_only": True,
    "grasp_contact_pose_mode": d.get("grasp_contact_pose_mode"),
    "grasp_centerline_capture_mode": d.get("grasp_centerline_capture_mode"),
    "grasp_centerline_selection_objective": d.get("grasp_centerline_selection_objective"),
    "post_replay_replan": pr,
    "retention_summary": retention,
    "claim_guards": claim_guards,
}
compact_path.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n")
print(compact_path)
print(classification)
PY
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary_compact.json >/dev/null
```

Observed:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary_compact.json
BLOCKED_5M_CENTERLINE_SOLVER_INPUT
```

The compact summary intentionally stores `route_bound_to_planner_trajectory_post_replay=true`
and `blocked_claims` that include centerline IK, contact retention, stable grasp, micro-pull,
door-open, `Expert Oracle Score`, policy score, official leaderboard score, and full task
completion. This preserves the distinction between "route wired and bridge replayed" and
"centerline candidate reached IK/contact validation."

- [x] **Step 2: Write PM wording based on first failed gate**

Use this wording when the compact classification is `BLOCKED_5M_ROUTE_CONTRACT_NOT_BOUND`:

```markdown
5M 当前还没进入 live grasp 逻辑。我们确认 centerline candidate 生成和 5L 的 planner-trajectory
post-replay route 不是同一条入口；在把 centerline 结果绑定成 post-replay object-frame waypoint
之前，不能运行默认 oracle 然后把结果当作 5L 后续。下一步先补 route binding 合同。
```

Use this wording when the compact classification is `BLOCKED_5M_CENTERLINE_REACHABILITY_IK`:

```markdown
5M 第一候选能生成几何目标，但机器人在当前 post-bridge / near-grasp 状态下仍规划不到。结论是
把 5L 的大 X/Y correction 拆小还不够，下一步要切换候选顺序或增加 bridge-to-near 中间点；仍不能进入
close-hold、micro-pull 或 score。
```

Use this wording when the compact classification is `BLOCKED_5M_CENTERLINE_SOLVER_INPUT`:

```markdown
5M route 已接进 5L 同一条 planner-trajectory post-replay 入口，第一段 bridge replay 也能走到位。
但 live 状态生成 centerline candidate 时还没形成有效数值 waypoint，first route-bound run 的表现是 `NoneType` 转
float 的 post-replay replan 错误。所以这还不是 IK 不可达，也不是抓取保持失败；下一步先修
centerline live-state / waypoint input，再重跑同一候选。
```

Use this wording when the compact classification is `BLOCKED_5M_CONTACT_RETENTION`:

```markdown
5M 第一候选已经越过 reachability，能执行到 close-hold，但还没有满足 retention。下一步才是
contact retention tuning；仍不能宣称 stable grasp、door opened 或 Expert Oracle Score。
```

Use this wording when the compact classification is `PASS_5M_RETENTION_READY_FOR_MICRO_PULL_PLAN`:

```markdown
5M 第一候选已经证明 retention-positive，但这只打开 micro-pull plan。它还不是开门成功，也不是
Expert Oracle Score；下一步必须单独验证 door joint angle readback。
```

### Task 6A: State-Reference Rerun After Centerline Input Fixes

The first route-bound run above is retained as historical evidence for the `NoneType`
live-state / waypoint-input bug. After that, the GenManip probe was fixed and rechecked
before the next live run:

```text
focused pytest: planner_trajectory_execution_readback or post_replay or stage_post_step_centerline_prefers -> 13 passed, 267 deselected
py_compile online_open_door_oracle_probe.py and test_online_open_door_oracle_probe.py -> exit 0
git diff --check on edited probe/test files -> exit 0
```

The rerun evidence is:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias_state_reference/summary_compact.json
```

Observed boundary:

```text
status=FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY
classification=BLOCKED_5M_CENTERLINE_SOLVER_INPUT
first_failed_gate=post_replay_centerline_candidate_solver_no_candidate
bridge_replay.executed_steps=151
bridge_replay.reached_joint_target=true
bridge_replay.final_joint_target_abs_max_rad=7.104873657226562e-05
post_replay_replan.candidate_source=centerline
post_replay_replan.reference_source=state.ee_pose
post_replay_replan.candidate_count=0
post_replay_replan.attempted_candidate_count=0
post_replay_replan.available_action_points=0
post_replay_replan.failure_status_counts={}
post_replay_replan.replan_error=null
post_replay_replan.candidate_failure_reason=PAD_DEPTH_MISS
post_replay_close_hold.executed_steps=0
post_replay_close_hold.skipped_reason=no_post_replay_worker_state
```

PM wording: the earlier `NoneType` input bug is no longer the current first failed gate.
The live rerun now uses `state.ee_pose` as the post-replay calibration reference, and the
axis-threshold fallback no longer throws. The route is still correctly bound, and the
bridge replay still reaches the joint target. The new first failed gate is purely inside
centerline candidate generation: the bilateral contact-frame solver returns
`PAD_DEPTH_MISS` and emits no numeric candidate, so no post-replay IK, no second
trajectory execution, no close-hold, and no retention telemetry happened.

Engineering interpretation: this is still `BLOCKED_5M_CENTERLINE_SOLVER_INPUT`, but it
has advanced from an invalid input bug to a geometry-constraint miss. The diagnostic
candidate interval is inverted on world X:

```text
left lower bound=0.8913130708603386
right upper bound=0.8816189957111638
gap miss ~= 0.0096940751491748 m
current contact_frame_axis_gap_threshold_m=0.006
```

Next step: run a candidate-generation-only preflight on the same post-replay state,
sweeping the bilateral contact-frame tolerance / equivalent handle padding around the
observed `~9.7mm` X miss, with first trials around `0.010m` to `0.012m`. Do not rerun the
full Isaac planner path until the preflight can produce `candidate_count > 0`; otherwise
another full live run would only reproduce the same no-candidate gate.

### Task 6B: Candidate-Only Preflight And Stop Criteria

This task exists to prevent blind full Isaac reruns. 5M now has a narrower decision tree:

1. **Candidate generation gate.** Only run post-replay candidate generation after the bridge
   replay. Success means `candidate_count > 0` and a generated object-frame waypoint exists.
   Failure after the bounded matrix below means the current `centerline + inner-face-corridor +
   bilateral-contact-frame` model is not suitable for this post-bridge state.
2. **cuRobo reachability gate.** Only after `candidate_count > 0`, rerun one full live
   planner attempt. Success means `selected_plan_success=true` and
   `available_action_points>0`. Failure here is an IK/reachability problem, not a
   candidate-generation problem.
3. **Close-hold / retention gate.** Only after post-replay action points execute, evaluate
   close-hold and contact retention. Failure here is a grasp/contact-retention problem, not
   a candidate-generation or IK problem.

Code checkpoint for the new preflight gate:

```text
GenManip worktree: /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
files:
  standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
  tests/labutopia_poc/test_online_open_door_oracle_probe.py
new CLI:
  --planner-trajectory-post-replay-candidate-preflight-only
behavior:
  after primary replay, build post-replay candidate metadata/object-frame waypoint(s),
  then stop before calling post-replay cuRobo planner
```

Verification observed before live preflight:

```text
PYTHONPATH=. python -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "post_replay_candidate_preflight_only or preflights_post_replay_centerline" -q
2 passed, 280 deselected

PYTHONPATH=. python -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "post_replay or centerline or inner_face or grasp_selection_axis_gap_threshold or handle_x_padding" -q
44 passed, 238 deselected

python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
exit 0

git diff --check -- standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
exit 0
```

Bounded candidate-only sweep matrix:

```text
Primary A: --grasp-selection-axis-gap-threshold-m
  [0.006, 0.008, 0.0095, 0.010, 0.011, 0.012, 0.014]

Primary B: --grasp-contact-model-handle-x-padding-m
  [0.003, 0.0048, 0.005, 0.006, 0.008, 0.010, 0.012]

Secondary only after candidate_count > 0:
  --grasp-centerline-max-center-shift-m [0.012, 0.05, 0.10, 0.16, 0.18]
```

Stop rule:

- If neither Primary A nor Primary B produces `candidate_count > 0`, stop 5M centerline
  tuning and write `BLOCKED_5M_CENTERLINE_MODEL_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`.
  Do not keep expanding offsets.
- If Primary A/B produces a candidate but the first full planner rerun returns
  `MotionGenStatus.IK_FAIL`, stop padding/tolerance tuning and move to bridge-to-near
  reachability / approach seed planning.
- If planner and execution pass but retention fails, move to contact-retention tuning.

Allowed claims for Task 6B are intentionally narrow: candidate-only preflight may claim only
whether a numeric candidate was generated. It may not claim centerline cuRobo plan, close-hold,
contact retention, stable grasp, micro-pull, door opened, `Expert Oracle Score`, policy score,
official score, or full task completion.

Observed 2026-07-05 live preflight result:

```text
evidence:
  docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_candidate_preflight_bounded_sweep/summary_compact.json
run_count=14
candidate_found=false
classification=BLOCKED_5M_CENTERLINE_MODEL_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT
axis_gap rows:
  0.006, 0.008, 0.0095, 0.010, 0.011, 0.012, 0.014 -> candidate_count=0
handle_x_padding rows:
  0.003, 0.0048, 0.005, 0.006, 0.008, 0.010, 0.012 -> candidate_count=0
failure_reason_counts:
  PAD_DEPTH_MISS=8
  HANDLE_NOT_BETWEEN_INNER_FACES=6
server_port_after_shutdown=closed
```

PM-readable conclusion: this is not yet an EBench policy/expert-score failure. The bridge replay
can still bring the arm to the post-bridge state, but the current centerline candidate model cannot
turn that state into a legal handle grasp target. Since both bounded primary parameter families
failed, stop this 5M centerline tuning route. Do not keep enlarging offsets.

Next route: replace the candidate-generation model before running full planner again. The preferred
next route is a mesh-aware/open-face handle candidate model: read the actual handle/door geometry,
generate a grasp target on the visible handle face instead of requiring the handle to sit between the
old bilateral inner-face intervals, then run a fresh candidate-only gate. Only if that new gate
produces `candidate_count > 0` should the work return to full post-replay cuRobo planning,
close-hold, retention, and finally `Expert Oracle Score`.

### Task 6C: Mesh-Aware/Open-Face Candidate Route Plan

This is the replacement route after the bounded centerline preflight stopped. It is deliberately
staged so the team can decide early whether the route is working or should be abandoned.

**Definition of "fixed enough to continue":** EBench can generate at least one numeric handle grasp
candidate from the real drying-box handle geometry, pass one full post-replay planner run, then pass
close-hold/contact-retention before any `Expert Oracle Score` claim.

**Definition of "current replacement route does not work":** the route fails at its bounded gate and
produces a named blocker, without expanding into open-ended tuning.

1. **Geometry audit gate.** Locate the real handle mesh/prim, door link/articulation root, hinge axis,
   and handle face normal in the EBench-loaded USD. Write these into evidence. If the handle prim or
   door link cannot be uniquely identified, stop with `BLOCKED_HANDLE_GEOMETRY_METADATA_MISSING`.
2. **Mesh/open-face candidate gate.** Generate grasp candidates from the actual handle face or handle
   bbox/mesh surface, not from the old inner-face corridor. Run candidate-only preflight first. Success
   means `candidate_count > 0`, object-frame waypoint exists, and candidate labels record which handle
   face/normal was used. If a bounded face-normal/padding matrix still yields `candidate_count=0`, stop
   with `BLOCKED_MESH_AWARE_CANDIDATE_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`.
3. **Reachability gate.** Run exactly one full planner attempt for the first valid candidate family.
   Success means `selected_plan_success=true` and `available_action_points>0`. If this fails with
   `IK_FAIL` or no action points, stop candidate tuning and switch to bridge-to-near / approach-seed
   reachability planning.
4. **Close-hold/contact-retention gate.** Only after action points execute, evaluate close-hold and
   hand/handle retention. Success means the hold window keeps bilateral overlap/contact without drift
   beyond the documented threshold. Failure here is contact-retention work, not candidate generation.
5. **Expert Oracle Score gate.** Only after retention passes, replay the expert/oracle path under the
   EBench metric. Success means the native expert answer can score in the migrated EBench task. Failure
   here is a metric/task-contract problem, not a geometry candidate problem.

PM-readable expectation: the next likely "good" milestone is not full score immediately; it is
candidate generation from the real handle geometry. Once that passes, the problem becomes standard
reachability/retention/oracle-score validation. If geometry audit or mesh-aware preflight fails, we
will have a precise "not this route" conclusion instead of another long parameter sweep.

Decision horizon for the next work:

| Gate | What it answers | Success evidence | Stop / no-go evidence |
| --- | --- | --- | --- |
| 6C-1 geometry audit | Did EBench load enough native USD structure to target the real handle? | `PASS_HANDLE_GEOMETRY_AUDIT_READY_FOR_MESH_AWARE_CANDIDATE`; unique handle, door leaf, RevoluteJoint, hinge axis, and open-face normal. | `BLOCKED_HANDLE_GEOMETRY_METADATA_MISSING` or ambiguous handle/door/joint records. |
| 6C-2 mesh/open-face candidate-only preflight | Can the new candidate model produce a legal numeric target before any expensive planner run? | `candidate_count > 0`, object-frame waypoint exists, and candidate metadata records normal source, normal sign, approach offset, padding, and fallback status. | After the bounded matrix below, `candidate_count=0`; classify as `BLOCKED_MESH_AWARE_CANDIDATE_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT` and stop this replacement candidate model. |
| 6C-3 one full planner/readback | Can the robot actually reach the first valid candidate family from the post-bridge state? | `selected_plan_success=true`, `available_action_points>0`, and post-replay readback reaches joint tolerance. | `IK_FAIL`, no selected plan, or no action points. Stop candidate tuning and switch to bridge-to-near / approach-seed reachability planning. |
| 6C-4 close-hold/contact-retention | Does the hand remain on the handle after the grasp, rather than only passing through a waypoint? | close-hold executed, retention pass, tail bilateral overlap records, required-role near records, and required-role PhysX contact records are nonzero. | Tail window remains outside contact frame or required-role contact stays zero. This becomes contact-retention work, not candidate-generation work. |
| 6C-5 micro-pull / Expert Oracle Score | Can the retained grasp produce door-angle change and score under EBench metric? | door joint readback changes in the correct direction; then `Expert Oracle Score` has metric/action evidence. | Retention-positive grasp cannot move the door, or the EBench metric rejects the expert replay. This is a task-contract / oracle-score blocker. |

Bounded matrix for Gate 6C-2:

```text
Primary normal:
  handle_open_face_normal_world from geometry audit, preserving
  handle_open_face_source=handle_door_center_delta_overlap_fallback

Sign sanity:
  only if primary normal gives no candidate, try the opposite normal once as a sign check;
  do not run a full mirrored sweep unless evidence shows the normal sign was wrong

Approach offsets:
  [0.025, 0.035, 0.045] m

Face clearance / padding:
  [0.003, 0.006] m

Maximum candidate-only attempts before a route decision:
  6 primary attempts + 2 sign-sanity attempts = 8 attempts
```

This is the earliest point where the new route can be judged "not this way": if the bounded
candidate-only matrix cannot produce a numeric candidate, do not proceed to cuRobo, close-hold,
micro-pull, or score. If Gate 6C-2 passes, the earliest PM wording is "the real handle can now
produce EBench candidate targets"; it is still not "the door is solved". The earliest engineering
"looks fixed" point is Gate 6C-4 retention pass. The earliest evaluation-level "done" point is
Gate 6C-5 score evidence.

Observed 2026-07-05 Task 6C geometry audit result:

```text
code checkpoint:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_geometry_audit_code_checkpoint_20260705.json
offline geometry evidence:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_geometry_audit_20260705.json
status:
  PASS_HANDLE_GEOMETRY_AUDIT_READY_FOR_MESH_AWARE_CANDIDATE
selected_handle_prim_path:
  /World/labutopia_level1_poc/obj_obj_DryingBox_01/handle
selected_door_leaf_prim_path:
  /World/labutopia_level1_poc/obj_obj_DryingBox_01/body/Group/door/mesh
hinge_joint_prim_path:
  /World/labutopia_level1_poc/obj_obj_DryingBox_01/RevoluteJoint
hinge_axis_world:
  [0.0, 1.0, 0.0]
handle_open_face_normal_world:
  [0.0, 1.0, 0.0]
handle_open_face_source:
  handle_door_center_delta_overlap_fallback
```

Engineering interpretation: the real EBench-loaded drying-box USD now passes the first replacement
route gate. We can uniquely identify the nested native handle, the door leaf mesh, and the door
RevoluteJoint. The handle/door static AABBs overlap, so the open-face normal is not from direct bbox
separation; it is inferred from handle-center vs door-center delta and marked as fallback. That is
strong enough to enter a bounded mesh-aware/open-face candidate preflight, but it is not evidence of
`candidate_count > 0`, cuRobo planning, close-hold, retention, door opening, or score.

Verification observed for this checkpoint:

```text
TDD RED:
  mesh-aware audit tests first failed because build_mesh_aware_handle_geometry_audit_summary
  was missing; the overlap fallback test failed until center-delta fallback was implemented.
Focused GREEN:
  3 passed, 282 deselected
Related conda verification:
  6 passed, 7 skipped, 272 deselected
PXr/static USD verification with /usr/bin/python3:
  10 passed, 275 deselected
py_compile:
  exit 0
git diff --check:
  exit 0
json_tool geometry evidence:
  exit 0
```

Next gate after this paragraph: implement the actual mesh-aware/open-face candidate preflight. It
must consume the audited handle/door/joint fields and fallback normal, generate object-frame waypoint
metadata, and stop before post-replay cuRobo. Success means `candidate_count > 0`; failure after a
bounded face-normal/padding matrix should be classified as
`BLOCKED_MESH_AWARE_CANDIDATE_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`.

Observed 2026-07-05 mesh/open-face candidate preflight code checkpoint:

```text
code checkpoint:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_candidate_preflight_code_checkpoint_20260705.json
GenManip worktree:
  /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
new source:
  --planner-trajectory-post-replay-candidate-source mesh-open-face
new required audit input:
  --planner-trajectory-post-replay-mesh-open-face-geometry-audit-json PATH
new bounded parameters:
  --planner-trajectory-post-replay-mesh-open-face-approach-offset-m
  --planner-trajectory-post-replay-mesh-open-face-clearance-m
  --planner-trajectory-post-replay-mesh-open-face-normal-sign primary|opposite
status:
  READY_FOR_MESH_OPEN_FACE_CANDIDATE_ONLY_PREFLIGHT
```

The new code consumes the Task 6C geometry audit JSON, preserves
`handle_open_face_source=handle_door_center_delta_overlap_fallback`, and turns the audited handle
face into a generated post-replay object-frame waypoint with
`waypoint_source=planner_trajectory_post_replay_mesh_open_face_candidate`. On the real geometry audit
manifest, the offline primary target is `[0.47978996139738445, 0.27571899126186217,
1.1085915534527668]`; the opposite sign sanity target is `[0.47978996139738445,
0.22180747411861262, 1.1085915534527668]`. These numbers are geometry/code evidence only. They do
not prove live `candidate_count > 0`, cuRobo planning, close-hold, retention, door opening, or score.

Verification observed:

```text
TDD RED:
  argparse rejected mesh-open-face before the CLI was updated
  build_post_replay_mesh_open_face_candidate_object_frame_waypoints was missing
  run_planner_trajectory_execution_readback rejected mesh-open-face before the branch was added
Focused GREEN:
  5 passed, 283 deselected
Broader focused regression:
  8 passed, 280 deselected
Post-replay/centerline/mesh regression:
  30 passed, 258 deselected
py_compile:
  exit 0
git diff --check:
  exit 0
```

Next operational step: run the bounded live candidate-only matrix for `mesh-open-face`. Start with
the primary normal and the documented approach/clearance values. Only if no candidate is generated,
run the opposite-normal sign sanity checks. The run remains preflight-only and must stop before
post-replay cuRobo planning.

Observed 2026-07-05 mesh/open-face primary live candidate-only preflight:

```text
evidence:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_candidate_preflight_live_20260705_primary/summary_compact.json
attempt:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_candidate_preflight_live_20260705_primary/01_primary_normal_clearance_0p003_approach_0p035/summary_compact.json
classification:
  PASS_MESH_OPEN_FACE_CANDIDATE_ONLY_PREFLIGHT_READY_FOR_PLANNER_READBACK
bridge replay:
  executed_steps=150
  reached_joint_target=true
  final_joint_target_abs_max_rad=8.344650268554688e-05
post_replay candidate generation:
  candidate_source=mesh-open-face
  candidate_preflight_only=true
  candidate_count=1
  attempted_candidate_count=0
  skipped_reason=candidate_preflight_only
  replan_error=null
candidate:
  label=post_replay_mesh_open_face_primary_clearance_0p003_approach_0p035
  normal_sign=primary
  handle_open_face_source=handle_door_center_delta_overlap_fallback
  contact_target_world=[0.47978996139738445,0.27571899126186217,1.1085915534527668]
server_port_after_shutdown:
  closed
```

Engineering interpretation: Gate 6C-2 passed on the first primary-normal attempt. Do not run the
opposite-normal sign sanity path now; it was only a fallback if the primary normal produced no
candidate. This still does not prove post-replay cuRobo planning, action points, close-hold,
retention, door opening, or score because the run intentionally stopped at candidate-only preflight.

Observed 2026-07-05 full `mesh-open-face` primary planner/readback:

```text
evidence:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_planner_readback_live_20260705_primary/summary_compact.json
attempt:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_planner_readback_live_20260705_primary/01_primary_normal_clearance_0p003_approach_0p035/summary_compact.json
classification:
  BLOCKED_MESH_OPEN_FACE_PLANNER_READBACK_IK_FAIL_NO_ACTION_POINTS
bridge replay:
  executed_steps=150
  reached_joint_target=true
  final_joint_target_abs_max_rad=8.0108642578125e-05
post_replay contact target:
  target_world_key=contact_target_world
  target_world_position=[0.47978996139738445,0.27571899126186217,1.1085915534527668]
post_replay planner:
  candidate_source=mesh-open-face
  candidate_count=1
  attempted_candidate_count=1
  successful_candidate_count=0
  available_action_points=0
  failure_status_counts={"MotionGenStatus.IK_FAIL": 1}
```

Engineering interpretation: Gate 6C-3 was reached and failed at cuRobo planning. This is
not a candidate-generation failure anymore, and it is not post-replay execution/readback failure:
there were no post-replay action points to execute. The correct next gate is bridge-to-near
reachability, not more `mesh-open-face` candidate tuning or opposite-normal sign checks.

Observed 2026-07-05 bridge-to-near bounded sanity:

```text
aggregate evidence:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_bridge_to_near_bounded_sanity_20260705/summary_compact.json
code checkpoint:
  docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_bridge_to_near_code_checkpoint_20260705.json
new explicit target selector:
  --planner-trajectory-post-replay-mesh-open-face-target-world-key approach_near_target_world
attempts:
  approach_offset_m=0.035 -> target_world_position=[0.47978996139738445,0.3107189912618622,1.1085915534527668], MotionGenStatus.IK_FAIL, available_action_points=0
  approach_offset_m=0.045 -> target_world_position=[0.47978996139738445,0.32071899126186215,1.1085915534527668], MotionGenStatus.IK_FAIL, available_action_points=0
classification:
  BLOCKED_MESH_OPEN_FACE_BRIDGE_TO_NEAR_REACHABILITY_AFTER_BOUNDED_NEAR_OFFSET
```

Engineering interpretation: two bounded `approach_near_target_world` attempts both generated
numeric waypoints and reached post-replay cuRobo planning. The bridge replay itself still reached
joint tolerance, so this is not a reset/server regression. Both near targets failed with
`MotionGenStatus.IK_FAIL` and produced zero post-replay action points. Stop contact-target and
near-offset tuning here. The next route is an approach-seed / robot-staging redesign: adjust the
post-bridge state, wrist orientation, or staging waypoint before asking cuRobo to reach the handle
front. This still does not prove the door is globally impossible to open, and it does not allow
close-hold, retention, door-open, `Expert Oracle Score`, policy score, official score, or full task
completion claims.

### Task 7: Verification And Handoff

**Files:**
- Verify: all modified LabUtopia docs
- Verify: GenManip focused tests if any code changed

- [x] **Step 1: Run document and JSON checks**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_review_20260705_5m_candidates.json >/dev/null
git diff --check -- docs/superpowers/plans/2026-07-05-eos2-handle-frame-reachability-ladder.md docs/labutopia_lab_poc/evidence_manifests/README.md docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Expected: both commands exit `0`.

Observed:

```text
json_tool_review_manifest_exit=0
json_tool_summary_exit=0
json_tool_summary_compact_exit=0
git_diff_check_exit=0
```

- [x] **Step 2: Run claim-boundary grep**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
rg -n "PASS_5M_RETENTION_READY_FOR_MICRO_PULL_PLAN|BLOCKED_5M_|Expert Oracle Score|stable grasp|micro-pull|door-open" docs/superpowers/plans/2026-07-05-eos2-handle-frame-reachability-ladder.md docs/labutopia_lab_poc/evidence_manifests/README.md docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Expected: any positive claim is explicitly conditioned on the required evidence; no current-status paragraph claims stable grasp, door-open, score, or official result.

Observed: grep hits are either historical evidence, no-claim guard text, or conditional future wording.
Current 5M status remains `BLOCKED_5M_CENTERLINE_SOLVER_INPUT`.

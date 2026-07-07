# EOS-2 Contact Retention Orientation-Aware Staged Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Task 5J evidence that moves beyond fixed-quaternion translation-only contact correction by testing orientation-aware and staged post-replay candidates around `post_bridge_local_z_m006_q_bridge`.

**Architecture:** Reuse the existing `planner-trajectory-execution-readback` probe path and `--planner-trajectory-post-replay-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`; do not add new runtime interfaces for the first 5J pass. Each live run submits a fresh job, replays the known bridge, replans one explicit post-replay candidate, optionally executes close-hold, and records whether the candidate is planner-reachable and whether contact retention improves.

**Tech Stack:** GenManip online probe, genmanip-client submit API, Isaac Sim 4.1 conda env `embodied-eval-os-sim-isaacsim41-genmanip-py310`, cuRobo, JSON evidence manifests.

---

## Current 5J Status

Orientation-only six 2deg live candidates 5J-A through 5J-F are complete. 5J-A/C/D/F reached
post-replay close-hold but failed strict retention outside the handle contact frame. 5J-B/E
failed post-replay replan with `MotionGenStatus.IK_FAIL`. 5J-F Z +2deg is the first row with a
consistent two-finger world X-gap improvement signal, but it worsens both world Y gaps and is
not a stable retention improvement.

The next step is a staged-combination review. Do not automatically pair translation with any
orientation row, and do not claim stable grasp, micro-pull readiness, door opening, Expert Oracle
Score, policy score, official score, or full task completion.

## Current Evidence Boundary

5I established the following facts:

```text
baseline:
  post_bridge_local_z_m006_q_bridge
  xyz = 0.0010228951554745458 -0.11657822728157047 0.008903118610382071
  q_bridge = 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849
  planner success, close-hold executed, retention_pass=false

single-axis translation corridor:
  object-frame Y+2mm planner success, retention=false, improves world X gap but worsens world Y gap
  object-frame X-2mm planner success, retention=false, improves world Y gap but worsens world X gap

paired translation correction:
  object-frame X-2mm/Y+2mm IK_FAIL
  object-frame X-5mm/Y+5mm IK_FAIL
```

Therefore Task 5J must not continue broad translation-only sweeps. It should test whether small wrist-orientation changes can make paired contact correction reachable or can reduce both world-axis gaps during close-hold.

## Candidate Quaternion Rule

Use the historical post-bridge orientation perturbation convention:

```python
q_candidate = q_bridge * axis_angle_quaternion(axis, deg)
```

That is right multiplication in WXYZ order. This reproduces existing historical candidates such as `post_bridge_ori_x_m08` / `post_bridge_ori_x_p08`.

The first 5J candidate set uses the same baseline XYZ and small orientation deltas:

```text
ori_x_m02_z_m006 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.9440477123955275 -0.2260581829170542 -0.220067918113651 -0.09613389659290084
ori_x_p02_z_m006 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.9513619408457388 -0.1929736843541575 -0.2232888832911148 -0.08839507483801379
ori_y_m02_z_m006 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.9438354157431896 -0.2111264162243377 -0.2382206499838313 -0.08860737149035168
ori_y_p02_z_m006 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.9515742374980767 -0.2079054510468739 -0.2051361514209346 -0.09592159994056294
ori_z_m02_z_m006 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.9460943440319013 -0.2056465227581623 -0.2253355149274885 -0.1088067349969057
ori_z_p02_z_m006 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.949315309209365 -0.2133853445130493 -0.2180212864772773 -0.07572223643400897
```

Original prepared-manifest idea: if an orientation-only candidate became a credible review
candidate, test translation plus orientation around the two single-axis reachable translations.
Current 5J-F evidence narrows this to review first, not automatic execution:

```text
y_p002_ori_y_m02 0.0010228951554745458 -0.11457822728157047 0.008903118610382071 0.9438354157431896 -0.2111264162243377 -0.2382206499838313 -0.08860737149035168
y_p002_ori_y_p02 0.0010228951554745458 -0.11457822728157047 0.008903118610382071 0.9515742374980767 -0.2079054510468739 -0.2051361514209346 -0.09592159994056294
x_m002_ori_y_m02 -0.0009771048445254542 -0.11657822728157047 0.008903118610382071 0.9438354157431896 -0.2111264162243377 -0.2382206499838313 -0.08860737149035168
x_m002_ori_y_p02 -0.0009771048445254542 -0.11657822728157047 0.008903118610382071 0.9515742374980767 -0.2079054510468739 -0.2051361514209346 -0.09592159994056294
```

Run candidates one per live run. Multi-candidate mode selects the first planner-success candidate and can hide later retention behavior.

### Task 1: Create 5J Prepared Evidence Manifest

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_staged_correction_20260705_5j_candidates.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [x] **Step 1: Write candidate manifest**

Create the manifest with this exact JSON:

```json
{
  "stage": "EOS-2 Task 5J",
  "status": "PREPARED_NOT_LIVE_EVIDENCE",
  "base_waypoint": {
    "label": "post_bridge_local_z_m006_q_bridge",
    "object_frame_xyz": [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071],
    "object_frame_quaternion_wxyz": [0.9478491886430741, -0.209547848787944, -0.22171216853953848, -0.09227854018408849]
  },
  "quaternion_rule": "q_candidate = q_bridge * axis_angle_quaternion(axis, deg), WXYZ right-multiply",
  "candidate_groups": [
    {
      "group": "orientation_only_2deg",
      "purpose": "Test whether small wrist orientation changes are reachable and whether they reduce contact-frame gaps without translation.",
      "candidates": [
        {"label": "ori_x_m02_z_m006", "xyz": [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.9440477123955275, -0.2260581829170542, -0.220067918113651, -0.09613389659290084]},
        {"label": "ori_x_p02_z_m006", "xyz": [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.9513619408457388, -0.1929736843541575, -0.2232888832911148, -0.08839507483801379]},
        {"label": "ori_y_m02_z_m006", "xyz": [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.9438354157431896, -0.2111264162243377, -0.2382206499838313, -0.08860737149035168]},
        {"label": "ori_y_p02_z_m006", "xyz": [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.9515742374980767, -0.2079054510468739, -0.2051361514209346, -0.09592159994056294]},
        {"label": "ori_z_m02_z_m006", "xyz": [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.9460943440319013, -0.2056465227581623, -0.2253355149274885, -0.1088067349969057]},
        {"label": "ori_z_p02_z_m006", "xyz": [0.0010228951554745458, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.949315309209365, -0.2133853445130493, -0.2180212864772773, -0.07572223643400897]}
      ]
    },
    {
      "group": "translation_plus_orientation_y_axis_2deg",
      "purpose": "Review whether a small orientation change keeps the known single-axis 2mm translation corridor reachable while improving retention; do not run these combinations automatically after a one-axis gap improvement.",
      "candidates": [
        {"label": "y_p002_ori_y_m02", "xyz": [0.0010228951554745458, -0.11457822728157047, 0.008903118610382071], "q_wxyz": [0.9438354157431896, -0.2111264162243377, -0.2382206499838313, -0.08860737149035168]},
        {"label": "y_p002_ori_y_p02", "xyz": [0.0010228951554745458, -0.11457822728157047, 0.008903118610382071], "q_wxyz": [0.9515742374980767, -0.2079054510468739, -0.2051361514209346, -0.09592159994056294]},
        {"label": "x_m002_ori_y_m02", "xyz": [-0.0009771048445254542, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.9438354157431896, -0.2111264162243377, -0.2382206499838313, -0.08860737149035168]},
        {"label": "x_m002_ori_y_p02", "xyz": [-0.0009771048445254542, -0.11657822728157047, 0.008903118610382071], "q_wxyz": [0.9515742374980767, -0.2079054510468739, -0.2051361514209346, -0.09592159994056294]}
      ]
    }
  ],
  "allowed_claims": [
    "Task 5J candidates are prepared",
    "quaternion generation rule is explicit",
    "live runs must still prove reachability and retention"
  ],
  "forbidden_claims": [
    "stable grasp",
    "micro-pull readiness",
    "door opened",
    "Expert Oracle Score",
    "policy score",
    "official leaderboard score",
    "full task completion"
  ]
}
```

- [x] **Step 2: Validate JSON**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_staged_correction_20260705_5j_candidates.json >/dev/null
```

Expected: exit code `0`.

- [x] **Step 3: Add README row**

Add one row after the Task 5I rows in `docs/labutopia_lab_poc/evidence_manifests/README.md`:

```markdown
| `eos2_contact_retention_orientation_aware_staged_correction_20260705_5j_candidates.json` | EOS-2 Task 5J orientation-aware staged correction candidate manifest | `PREPARED` | 5I 已证明 fixed-quaternion pure translation 不能同时满足 reachability 和 contact retention。5J 候选沿用历史 right-multiply quaternion 规则 `q_candidate = q_bridge * axis_angle(axis, deg)`，先在 `post_bridge_local_z_m006_q_bridge` 基线上测 2deg orientation delta，再测 single-axis 2mm translation + orientation。该 manifest 不是 live evidence，不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。 |
```

### Task 2: Run First Live 5J-A Orientation-Only Candidate

**Files:**
- Create directory: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02/`

- [x] **Step 1: Start a fresh server**

Run from `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback`:

```bash
EVIDENCE_DIR=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02
mkdir -p "$EVIDENCE_DIR"
PYENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
GENMANIP_WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
GENMANIP_CLIENT_SRC=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src
PORT=18443
SERVER_RUN_ID=labutopia_eos2_contact_retention_orientation_aware_20260705_5j_0800_server
RAY_TMPDIR=/tmp/r5j0800
PYTHONNOUSERSITE=1 RAY_ADDRESS=local RAY_USAGE_STATS_ENABLED=0 RAY_TMPDIR=$RAY_TMPDIR \
LABUTOPIA_ORACLE_DEBUG_OBS=1 LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1 GENMANIP_VERBOSE=1 \
PATH=$PYENV/bin:$PATH \
PYTHONPATH=$CUROBO_SRC:$GENMANIP_CLIENT_SRC:$GENMANIP_WORKTREE \
LD_LIBRARY_PATH=/isaac-sim/exts/omni.isaac.ml_archive/pip_prebundle/nvidia/cuda_runtime/lib:$PYENV/lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin:$PYENV/lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps:$PYENV/lib/python3.10/site-packages/torch/lib:${LD_LIBRARY_PATH:-} \
$PYENV/bin/python -u ray_eval_server.py --host 127.0.0.1 --port $PORT \
  --run_id $SERVER_RUN_ID --no_save_process --episode_recorder_save_every 0 \
  --reset_timeout 1200 --step_timeout 1200 --load_config_timeout 300 \
  2>&1 | tee "$EVIDENCE_DIR/server.log"
```

Expected: server prints `Uvicorn running on http://127.0.0.1:18443`.

- [x] **Step 2: Submit and run `ori_y_m02_z_m006`**

Use the same environment variables as Step 1:

```bash
EVIDENCE_DIR=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02
RUN_ID=labutopia_eos2_contact_retention_orientation_aware_20260705_5j_0800_ori_y_m02
TASK_CONFIG=ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
PYTHONPATH=$CUROBO_SRC:$GENMANIP_CLIENT_SRC:$GENMANIP_WORKTREE $PYENV/bin/python - <<PY > "$EVIDENCE_DIR/submit.stdout.txt" 2> "$EVIDENCE_DIR/submit.stderr.txt"
from genmanip_client.submit import start_job
start_job("http://127.0.0.1:$PORT", ["$TASK_CONFIG"], "$RUN_ID")
PY
printf '%s\n' "$?" > "$EVIDENCE_DIR/submit.exitcode.txt"

cd "$GENMANIP_WORKTREE"
LABUTOPIA_ORACLE_DEBUG_OBS=1 LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1 \
PYTHONPATH=$CUROBO_SRC:$GENMANIP_CLIENT_SRC:$GENMANIP_WORKTREE \
$PYENV/bin/python standalone_tools/labutopia_poc/online_open_door_oracle_probe.py \
  --host 127.0.0.1 --port $PORT --worker-id 0 --run-id $RUN_ID \
  --task-config $TASK_CONFIG \
  --probe-mode planner-trajectory-execution-readback \
  --planner-trajectory-waypoint-label approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity \
  --planner-trajectory-extra-object-frame-waypoint approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity \
    0.0010228951554745458 -0.11657822728157047 0.014903118610382071 \
    0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849 \
  --planner-trajectory-post-replay-replan \
  --planner-trajectory-post-replay-execute \
  --planner-trajectory-post-replay-extra-object-frame-waypoint ori_y_m02_z_m006 \
    0.0010228951554745458 -0.11657822728157047 0.008903118610382071 \
    0.9438354157431896 -0.2111264162243377 -0.2382206499838313 -0.08860737149035168 \
  --planner-trajectory-post-replay-close-hold-steps 15 \
  --post-close-min-bilateral-overlap-records 15 \
  --post-close-retention-tail-window 15 \
  --post-close-retention-require-physx-contact \
  --open-width-m 0.024 --close-width-m 0.010 \
  --controller-readback-joint-tolerance-rad 0.02 \
  --controller-readback-lead-in-max-joint-step-rad 0.50 \
  --controller-readback-lead-in-post-step-delta-threshold-rad 0.80 \
  --controller-readback-lead-in-max-steps 256 \
  --output "$EVIDENCE_DIR/planner_trajectory_contact_retention_orientation_summary.json" \
  --trace-jsonl "$EVIDENCE_DIR/planner_trajectory_contact_retention_orientation_trace.jsonl" \
  > "$EVIDENCE_DIR/probe.stdout.txt" 2> "$EVIDENCE_DIR/probe.stderr.txt"
printf '%s\n' "$?" > "$EVIDENCE_DIR/probe.exitcode.txt"
```

- [x] **Step 3: Summarize the result**

Run this command to create `summary_compact.json` from the full probe summary:

```bash
EVIDENCE_DIR=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02
python - <<'PY'
import json
from pathlib import Path

root = Path("/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02")
summary = json.loads((root / "planner_trajectory_contact_retention_orientation_summary.json").read_text())
post_replay = summary.get("post_replay_replan") or {}
close_hold = summary.get("post_replay_close_hold") or {}
retention = close_hold.get("retention_summary") or {}
compact = {
    "stage": "EOS-2 Task 5J",
    "candidate_label": "ori_y_m02_z_m006",
    "status": summary.get("status"),
    "blockers": summary.get("blockers", []),
    "post_replay_successful_candidate_count": post_replay.get("successful_candidate_count"),
    "post_replay_failure_status_counts": post_replay.get("failure_status_counts"),
    "close_hold_executed_steps": close_hold.get("executed_steps"),
    "retention_pass": retention.get("retention_pass"),
    "tail_bilateral_overlap_records": retention.get("tail_bilateral_overlap_records"),
    "tail_required_roles_near_records": retention.get("tail_required_roles_near_records"),
    "tail_physx_required_roles_contact_records": retention.get("tail_physx_required_roles_contact_records"),
    "tail_last_required_role_states": retention.get("tail_last_required_role_states"),
    "claim_boundary": "diagnostic only; no stable grasp, micro-pull, door-open, Expert Oracle Score, policy score, official score, or full task completion",
}
(root / "summary_compact.json").write_text(json.dumps(compact, indent=2, ensure_ascii=False) + "\n")
PY
python -m json.tool "$EVIDENCE_DIR/summary_compact.json" >/dev/null
```

Expected: `summary_compact.json` exists and `json.tool` exits `0`.

### Task 3: Decision Rules for More 5J Candidates

**Files:**
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Classify the first live result**

Use this exact decision table:

```text
If post_replay_successful_candidate_count=0:
  classification=BLOCKED_5J_ORIENTATION_IK
  next action=try the opposite sign on the same axis, then x/z axes.

If planner succeeds but retention_pass=false and only one of X/Y gap families improves:
  classification=PARTIAL_5J_ORIENTATION_CORRIDOR
  next action=review whether a staged combination is justified; do not auto-run translation.

If planner succeeds and both X/Y gaps improve but retention_pass=false:
  classification=PARTIAL_5J_CONTACT_FRAME_IMPROVED
  next action=run the same orientation with close-hold tail tuning or staged two-step correction.

If retention_pass=true and required-role PhysX contact records pass:
  classification=PASS_5J_CONTACT_RETENTION
  next action=only then plan micro-pull diagnostics.
```

- [x] **Step 2: Update docs with actual result**

Add one evidence row for the live 5J run in `docs/labutopia_lab_poc/evidence_manifests/README.md` and add a PM paragraph in `expert_oracle_score_plan.md` and `aan_consumer_handoff.md`.

Allowed wording:

```text
Task 5J has started testing orientation-aware post-replay candidates. This is still diagnostic-only. It can prove whether a wrist orientation makes contact correction reachable or improves the contact-frame gaps; it cannot claim stable grasp, micro-pull readiness, door opening, Expert Oracle Score, policy score, official score, or full task completion until the retention gate passes.
```

### 5J-A Live Result

The first live candidate `ori_y_m02_z_m006` completed submit/probe with exit code `0`.
Bridge replay, post-replay execution, and close-hold all reached their joint targets:
150 bridge steps, 42 post-replay steps, and 15 close-hold steps. The run is therefore no
longer blocked at environment startup, submit, planner reachability, or close-hold command
readback.

The strict retention gate still failed. `retention_pass=false`,
`tail_bilateral_overlap_records=0`, `tail_required_roles_near_records=0`, and
`tail_physx_required_roles_contact_records=0`; 15/15 tail contact records were classified
as `AABB_OUTSIDE_CONTACT_FRAME`. Classification for this row is
`BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`. This proves the `z_m006` continuation plus
Y -2deg orientation candidate is reachable, but not that it grasps the handle.

Next 5J action: run same-axis opposite sign and x/z orientation deltas on the same `z_m006`
baseline, one at a time. Only if a candidate improves the X/Y contact gaps should it be
paired with the known single-axis 2mm translation corridor.

### 5J-B Live Result

The same-axis opposite-sign candidate `ori_y_p02_z_m006` completed submit/probe with exit
code `0`, and the 18444 server was stopped after the probe. Bridge replay still succeeded:
151 bridge steps, `reached_joint_target=true`, and final joint error around
`7.13e-05 rad < 0.02 rad`.

The post-replay candidate itself was not reachable. `successful_candidate_count=0`,
`failure_status_counts={"MotionGenStatus.IK_FAIL": 1}`, and no action joint trajectory was
available. Because IK failed before a post-replay action trajectory existed, close-hold and
retention could not execute for this row. Classification is `BLOCKED_5J_ORIENTATION_IK`.

Next 5J action: do not pair Y +2deg with translation. Continue with x/z orientation deltas
on the same `z_m006` baseline, one candidate per live run.

### 5J-C Live Result

The x-axis negative candidate `ori_x_m02_z_m006` completed submit/probe with exit code `0`,
and the 18445 server was stopped after the probe. Bridge replay, post-replay execution, and
close-hold all reached their joint targets: 156 bridge steps, 31 post-replay steps, and 15
close-hold steps. This row is not blocked at IK or action replay.

The strict retention gate still failed. `retention_pass=false`,
`tail_bilateral_overlap_records=0`, `tail_required_roles_near_records=0`, and
`tail_physx_required_roles_contact_records=0`; 15/15 tail contact records were classified
as `AABB_OUTSIDE_CONTACT_FRAME`. Last gaps were about left `[0.1346, 0.0554, 0.0]m` and
right `[0.0890, 0.0698, 0.0]m`, which are worse than 5J-A's Y -2deg row. Classification is
`BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`.

Next 5J action: run X +2deg or Z-axis orientation deltas on the same `z_m006` baseline.
Do not pair X -2deg with translation because it did not improve the contact gaps.

### 5J-D Live Result

The x-axis positive candidate `ori_x_p02_z_m006` completed submit/probe with exit code `0`.
The 18446 server was held by a foreground exec session because two background launcher attempts
exited before readiness with empty `server.log`; the server was stopped after the probe. This
server lifecycle note is about the harness and does not affect the 5J-D evidence classification.

Bridge replay, post-replay execution, and close-hold all reached their joint targets: 151 bridge
steps, 78 post-replay steps, and 15 close-hold steps. This row is not blocked at IK or action
replay.

The strict retention gate still failed. `retention_pass=false`,
`tail_bilateral_overlap_records=0`, `tail_required_roles_near_records=0`, and
`tail_physx_required_roles_contact_records=0`; 15/15 tail contact records were classified
as `AABB_OUTSIDE_CONTACT_FRAME`. Last gaps were about left `[0.1352, 0.0564, 0.0]m` and
right `[0.0888, 0.0692, 0.0]m`. Compared with best-so-far 5J-A, X +2deg remains worse on all
last required-role X/Y gaps. Compared with 5J-C, it slightly improves right-finger gaps but
worsens left-finger gaps, so it is not a consistent contact-gap improvement relative to all
required-role X/Y gaps. Classification is
`BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`.

Next 5J action: run Z-axis orientation deltas on the same `z_m006` baseline. Do not pair either
X-axis orientation candidate with translation yet.

### 5J-E Live Result

The z-axis negative candidate `ori_z_m02_z_m006` completed submit/probe with exit code `0`.
The 18447 server was held by a foreground exec session, stopped after the probe with Ctrl-C,
and the port was verified free afterward. The unrelated 8087 server stayed running and was not
touched.

Bridge replay still reached the joint target: 150 bridge steps and final joint error around
`7.13e-05 rad < 0.02 rad`. The post-replay candidate itself was not reachable. The candidate
record for `ori_z_m02_z_m006` exists and was attempted, but `successful_candidate_count=0`,
`failure_status_counts={"MotionGenStatus.IK_FAIL": 1}`, `available_action_points=0`, and no
selected waypoint was produced. Because there was no successful post-replay selected waypoint or
action trajectory to hand off from, close-hold was skipped with `no_post_replay_worker_state`
and retention telemetry was unavailable.

Classification is `BLOCKED_5J_ORIENTATION_IK`. The top-level `waypoint_not_found` and
`action_joint_positions_missing` blockers are consequences of no selected post-replay waypoint;
they are not evidence that the CLI candidate label was missing.

Follow-up: the opposite Z +2deg orientation candidate was run as 5J-F below. Do not pair
Z -2deg with translation.

### 5J-F Live Result

The z-axis positive candidate `ori_z_p02_z_m006` completed submit/probe with exit code `0`.
The 18448 server was held by a foreground exec session, stopped after the probe with Ctrl-C,
and the port was verified free afterward.

Bridge replay, post-replay execution, and close-hold all reached their joint targets: 151 bridge
steps, 41 post-replay steps, and 15 close-hold steps. This row is not blocked at IK or action
replay.

The strict retention gate still failed. `retention_pass=false`,
`tail_bilateral_overlap_records=0`, `tail_required_roles_near_records=0`, and
`tail_physx_required_roles_contact_records=0`; 15/15 tail contact records were classified as
`AABB_OUTSIDE_CONTACT_FRAME`. Last gaps were about left `[0.1295, 0.0571, 0.0]m` and
right `[0.0838, 0.0691, 0.0]m`. Compared with best-so-far 5J-A approximate last gaps, Z +2deg
slightly improves both required-role world X gaps but worsens both world Y gaps. Classification is
`BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`.

Next 5J action: do not claim stable grasp or move to micro-pull. Review whether the Z +2deg
X-gap improvement should be paired with a known single-axis Y-gap correction as a staged
combination, instead of broad blind sweeping.

### Task 4: Verification and Review

**Files:**
- Verify: `docs/labutopia_lab_poc/evidence_manifests/*.json`
- Verify: updated Markdown docs

- [x] **Step 1: Run JSON validation**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_staged_correction_20260705_5j_candidates.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02/summary_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0810_ori_y_p02/summary_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0820_ori_x_m02/summary_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0830_ori_x_p02/summary_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0840_ori_z_m02/summary_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0850_ori_z_p02/summary_compact.json >/dev/null
```

Expected: all exit code `0`.

- [x] **Step 2: Run Markdown diff check**

Run:

```bash
git diff --check -- \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/superpowers/plans/2026-07-05-eos2-post-close-contact-retention.md \
  docs/superpowers/plans/2026-07-05-eos2-contact-retention-orientation-aware-staged-correction.md
```

Expected: exit code `0`.

- [x] **Step 3: Check no 5J server remains**

Run:

```bash
ps -eo pid,ppid,stat,cmd | rg 'ray_eval_server.py --host 127.0.0.1 --port 18443|online_open_door_oracle_probe|labutopia_eos2_contact_retention_orientation_aware' || true
```

Expected: only the `rg` command appears after server shutdown.

## Self-Review

- Spec coverage: This plan covers the transition from 5I translation-only failure to 5J orientation-aware / staged correction evidence.
- Placeholder scan: No TBD/TODO placeholders are present; exact candidate labels, translations, quaternions, commands, paths, and claim boundaries are provided.
- Type consistency: Candidate fields use the existing CLI contract `LABEL X Y Z QW QX QY QZ` and WXYZ quaternion order.

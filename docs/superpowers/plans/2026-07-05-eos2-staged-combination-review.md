# EOS-2 Staged Combination Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 5J-F Z+2deg orientation signal into one reviewable staged-combination candidate without overclaiming grasp or score.

**Architecture:** Create a prepared review manifest for one prioritized live candidate, `x_m002_ori_z_p02`, then run exactly one live probe only after the review manifest is accepted by technical and PM review. The candidate keeps the 5J-F Z+2deg quaternion and adds the previously reachable object-frame X-2mm correction that 5I showed can reduce world Y gap.

**Tech Stack:** GenManip online probe, genmanip-client submit API, Isaac Sim 4.1 conda env `embodied-eval-os-sim-isaacsim41-genmanip-py310`, cuRobo, JSON evidence manifests, Markdown handoff docs.

---

## Current Evidence Boundary

5J orientation-only is complete:

```text
5J-A Y-2deg: reachable, close-hold executed, retention=false, outside contact frame
5J-B Y+2deg: post-replay IK_FAIL
5J-C X-2deg: reachable, close-hold executed, retention=false, gaps worse than 5J-A
5J-D X+2deg: reachable, close-hold executed, retention=false, not a consistent improvement
5J-E Z-2deg: post-replay IK_FAIL
5J-F Z+2deg: reachable, close-hold executed, retention=false
```

5J-F is the only orientation-only row with a consistent two-finger world X-gap improvement signal:

```text
5J-F vs approximate 5J-A:
  left  delta = [-0.001968022713, +0.003801109404, 0.0]
  right delta = [-0.002032489679, +0.002210562122, 0.0]
```

Negative X delta means world X gap got smaller. Positive Y delta means world Y gap got worse. Therefore 5J-F is not a stable retention improvement, but it is a reasonable review candidate for staged combination.

5I single-axis correction evidence:

```text
object-frame Y+2mm: reachable, mainly reduces world X gap, slightly worsens world Y gap
object-frame X-2mm: reachable, mainly reduces world Y gap, slightly worsens world X gap
object-frame X-2mm/Y+2mm paired: IK_FAIL
```

The first 5K hypothesis is therefore:

```text
Keep 5J-F Z+2deg orientation to preserve the world X-gap improvement signal.
Add object-frame X-2mm to compensate the world Y gap that Z+2deg worsened.
Run as one staged-combination candidate, not as a broad sweep.
```

## Candidate Contract

Use the existing CLI contract:

```text
--planner-trajectory-post-replay-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ
```

The candidate is:

```text
x_m002_ori_z_p02 -0.0009771048445254542 -0.11657822728157047 0.008903118610382071 0.949315309209365 -0.2133853445130493 -0.2180212864772773 -0.07572223643400897
```

This is `post_bridge_local_z_m006_q_bridge` with:

```text
object-frame X delta = -0.002m
object-frame Y delta = 0.000m
object-frame Z delta = 0.000m
orientation = 5J-F Z+2deg quaternion
```

Allowed claims before a live 5K run:

```text
5K candidate is prepared for staged-combination review
5J-F produced a two-finger world X-gap improvement signal but failed retention
5I object-frame X-2mm is the known single-axis correction that targets world Y gap
```

Forbidden claims before and after 5K unless strict evidence passes:

```text
stable grasp
micro-pull readiness
door opened
Expert Oracle Score
policy score
official leaderboard score
full task completion
```

### Task 1: Create 5K Prepared Review Manifest

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Write candidate manifest**

Create `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json` with this exact JSON:

```json
{
  "stage": "EOS-2 Task 5K",
  "status": "PREPARED_FOR_REVIEW_NOT_LIVE_EVIDENCE",
  "purpose": "Review one staged-combination candidate derived from 5J-F Z+2deg and 5I object-frame X-2mm before running any live translation-plus-orientation probe.",
  "evidence_dependencies": [
    {
      "path": "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0850_ori_z_p02/summary_compact.json",
      "role": "5J-F Z+2deg orientation-only signal",
      "summary": "reachable and close-hold executed; strict retention failed; both required-role world X gaps slightly improved relative to 5J-A while both world Y gaps worsened"
    },
    {
      "path": "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0750_obj_x_m002/summary_compact.json",
      "role": "known single-axis Y-gap correction",
      "summary": "object-frame X-2mm was reachable and mainly reduced world Y gap under fixed quaternion, but retention still failed",
      "baseline_comparison": {
        "baseline_path": "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0640_baseline_z_m006/planner_trajectory_contact_frame_guided_sweep_summary.json",
        "baseline_tail_last_required_role_gaps_m": {
          "panda_leftfinger": [0.135334314338, 0.0558935641, 0.0],
          "panda_rightfinger": [0.088899776142, 0.069633008273, 0.0]
        },
        "candidate_tail_last_required_role_gaps_m": {
          "panda_leftfinger": [0.135168152786, 0.054337791698, 0.0],
          "panda_rightfinger": [0.089521731714, 0.067830380643, 0.0]
        },
        "delta_candidate_minus_baseline_m": {
          "panda_leftfinger": [-0.000166161552, -0.001555772402, 0.0],
          "panda_rightfinger": [0.000621955572, -0.00180262763, 0.0]
        },
        "interpretation": "negative Y deltas on both fingers show object-frame X-2mm reduced the world Y gap relative to the z_m006 baseline; X gap was nearly unchanged for the left finger and slightly worse for the right finger"
      }
    },
    {
      "path": "docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0730_obj_x_m002_y_p002/summary_compact.json",
      "role": "paired-translation risk boundary",
      "summary": "object-frame X-2mm/Y+2mm paired correction failed with MotionGenStatus.IK_FAIL under fixed quaternion"
    }
  ],
  "candidate": {
    "label": "x_m002_ori_z_p02",
    "object_frame_xyz": [
      -0.0009771048445254542,
      -0.11657822728157047,
      0.008903118610382071
    ],
    "object_frame_quaternion_wxyz": [
      0.949315309209365,
      -0.2133853445130493,
      -0.2180212864772773,
      -0.07572223643400897
    ],
    "translation_delta_from_post_bridge_local_z_m006_q_bridge_m": [
      -0.002,
      0.0,
      0.0
    ],
    "orientation_source": "5J-F ori_z_p02_z_m006"
  },
  "review_decision_rule": {
    "run_live_candidate_only_if": [
      "technical review confirms this is the minimal staged candidate supported by 5I and 5J-F",
      "PM review confirms the docs describe this as a review candidate, not as a grasp success or a wide live sweep approval"
    ],
    "do_not_run_if": [
      "review finds stale docs that still imply translation combination is automatic",
      "review finds the candidate mixes incompatible coordinate frames",
      "review finds the candidate would duplicate an already failed live row"
    ]
  },
  "live_run_interpretation": {
    "if_post_replay_successful_candidate_count_is_0_and_failure_status_counts_contains_motiongenstatus_ik_fail_and_selected_waypoint_is_null_and_available_action_points_is_0": "classify as BLOCKED_5K_STAGED_COMBO_IK",
    "if_post_replay_successful_candidate_count_is_0_without_ik_fail_or_if_summary_is_missing": "classify as BLOCKED_5K_STAGED_COMBO_PLANNER_OR_RUN_FAILURE, not IK",
    "if_reachable_but_retention_pass_is_false": "classify as BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME and compare X/Y gaps against 5J-F and 5J-A",
    "if_retention_pass_true_and_required_role_physx_contact_records_pass": "classify as PASS_5K_CONTACT_RETENTION_CANDIDATE and only then open a separate micro-pull diagnostic review gate"
  },
  "allowed_claims": [
    "5K staged-combination candidate is prepared for review",
    "5J-F gave a one-axis X-gap improvement signal",
    "5I object-frame X-2mm is the known single-axis correction for world Y gap"
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
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json >/dev/null
```

Expected: exit code `0`.

- [x] **Step 3: Add evidence README row**

Add one row after the 5J-F row in `docs/labutopia_lab_poc/evidence_manifests/README.md`:

```markdown
| `eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json` | EOS-2 Task 5K staged-combination review candidate | `PREPARED_FOR_REVIEW` | 5K 不是直接宣布组合 translation 已批准，而是把 5J-F 的 Z+2deg 信号和 5I 的 object-frame X-2mm 单轴 correction 收敛成一个可审阅候选：`x_m002_ori_z_p02`。它的目标是保留 Z+2deg 对双指 world X gap 的轻微改善，同时尝试补偿 world Y gap。该 manifest 不是 live evidence；只有技术/PM review 通过后才跑单候选 live probe。仍不能 claim stable grasp、micro-pull、door-open、Expert Oracle Score 或 score。 |
```

- [x] **Step 4: Add PM summary paragraphs**

Add this paragraph near the current 5J-F status in `docs/labutopia_lab_poc/expert_oracle_score_plan.md` and `docs/labutopia_lab_poc/aan_consumer_handoff.md`:

```markdown
2026-07-05 Task 5K staged-combination review 已准备候选 manifest：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json`。
通俗讲，5J-F 的 Z+2deg 让左右手指在 world X 方向都稍微更接近把手，但 world Y 方向更远；5I 的 object-frame X-2mm 单轴 correction 刚好是历史上能补 world Y gap 的方向。因此 5K 先只评审一个最小候选 `x_m002_ori_z_p02`，不做大范围 sweep，也不把它说成已经能抓住。该 review artifact 后续已被 5K-A live probe 消费；即使 live 能执行，也必须看 close-hold tail window 的 bilateral near/overlap 和 required-role PhysX contact，不能直接进入 micro-pull 或算分。
```

### Task 2: Review 5K Candidate Before Live Run

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json`
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0850_ori_z_p02/summary_compact.json`
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0750_obj_x_m002/summary_compact.json`
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_guided_post_replay_sweep_live_20260705_5i_0730_obj_x_m002_y_p002/summary_compact.json`

- [x] **Step 1: Dispatch technical review**

Ask one reviewer to answer these exact questions:

```text
1. Does x_m002_ori_z_p02 mix coordinate frames correctly?
2. Is object-frame X-2mm the right single-axis correction to pair with Z+2deg if the target is world Y gap?
3. Does the prepared manifest avoid claiming stable grasp or score?
4. If the candidate fails, will the evidence classify it unambiguously as IK failure vs retention failure?
```

Expected: no blocking issue before running live 5K-A.

- [x] **Step 2: Dispatch PM review**

Ask one reviewer to answer these exact questions:

```text
1. Does the text explain that this is a review candidate, not a guaranteed fix?
2. Does the text explain why we choose one candidate instead of a broad sweep?
3. Does the text avoid implying micro-pull, door-open, Expert Oracle Score, or model score?
```

Expected: no blocking issue before running live 5K-A.

- [x] **Step 3: Apply review fixes**

If either reviewer reports a doc or manifest blocker, update only the affected docs/manifests, then run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json >/dev/null
git diff --check -- \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/superpowers/plans/2026-07-05-eos2-staged-combination-review.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json
```

Expected: both commands exit `0`.

### Task 3: Run 5K-A Live Candidate (Post-Review Only)

**Files:**
- Create directory: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/`

Hard gate: do not execute Task 3 unless Task 2 has explicit technical review and PM review sign-off with no blockers. Preparing command files is allowed; starting the server or submitting the job is not allowed before sign-off.

- [x] **Step 1: Verify ports and write command files**

Run:

```bash
python - <<'PY'
import socket
for port in [18449, 8087]:
    s = socket.socket()
    s.settimeout(0.5)
    r = s.connect_ex(("127.0.0.1", port))
    s.close()
    print(f"{port}={'LISTENING' if r == 0 else 'FREE'}")
PY
```

Expected: `18449=FREE`. If `8087=LISTENING`, leave it alone because it belongs to a separate worker.

Create these run constants:

```text
EVIDENCE_DIR=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02
PYENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
GENMANIP_WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
GENMANIP_CLIENT_SRC=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src
PORT=18449
SERVER_RUN_ID=labutopia_eos2_contact_retention_staged_combo_20260705_5k_0900_server
RAY_TMPDIR=/tmp/r5k0900
RUN_ID=labutopia_eos2_contact_retention_staged_combo_20260705_5k_0900_x_m002_ori_z_p02
TASK_CONFIG=ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
```

- [x] **Step 2: Start server in foreground**

Run from `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback`:

```bash
EVIDENCE_DIR=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02
mkdir -p "$EVIDENCE_DIR"
PYENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
GENMANIP_WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
GENMANIP_CLIENT_SRC=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src
PORT=18449
SERVER_RUN_ID=labutopia_eos2_contact_retention_staged_combo_20260705_5k_0900_server
RAY_TMPDIR=/tmp/r5k0900
cd "$GENMANIP_WORKTREE"
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

Expected: `Uvicorn running on http://127.0.0.1:18449`.

- [x] **Step 3: Submit and run probe**

Run in another shell:

```bash
set -u
EVIDENCE_DIR=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02
PYENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
GENMANIP_WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
GENMANIP_CLIENT_SRC=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src
PORT=18449
RUN_ID=labutopia_eos2_contact_retention_staged_combo_20260705_5k_0900_x_m002_ori_z_p02
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
  --planner-trajectory-post-replay-extra-object-frame-waypoint x_m002_ori_z_p02 \
    -0.0009771048445254542 -0.11657822728157047 0.008903118610382071 \
    0.949315309209365 -0.2133853445130493 -0.2180212864772773 -0.07572223643400897 \
  --planner-trajectory-post-replay-close-hold-steps 15 \
  --post-close-min-bilateral-overlap-records 15 \
  --post-close-retention-tail-window 15 \
  --post-close-retention-require-physx-contact \
  --open-width-m 0.024 --close-width-m 0.010 \
  --controller-readback-joint-tolerance-rad 0.02 \
  --controller-readback-lead-in-max-joint-step-rad 0.50 \
  --controller-readback-lead-in-post-step-delta-threshold-rad 0.80 \
  --controller-readback-lead-in-max-steps 256 \
  --output "$EVIDENCE_DIR/planner_trajectory_contact_retention_staged_combo_summary.json" \
  --trace-jsonl "$EVIDENCE_DIR/planner_trajectory_contact_retention_staged_combo_trace.jsonl" \
  > "$EVIDENCE_DIR/probe.stdout.txt" 2> "$EVIDENCE_DIR/probe.stderr.txt"
printf '%s\n' "$?" > "$EVIDENCE_DIR/probe.exitcode.txt"
```

Expected: `submit.exitcode.txt` and `probe.exitcode.txt` both contain `0`.

- [x] **Step 4: Stop server and verify cleanup**

Stop the foreground server with Ctrl-C, then run:

```bash
python - <<'PY'
import socket
for port in [18449, 8087]:
    s = socket.socket()
    s.settimeout(0.5)
    r = s.connect_ex(("127.0.0.1", port))
    s.close()
    print(f"{port}={'LISTENING' if r == 0 else 'FREE'}")
PY
ps -eo pid,ppid,stat,cmd | rg 'ray_eval_server.py --host 127.0.0.1 --port 18449|online_open_door_oracle_probe|labutopia_eos2_contact_retention_staged_combo_20260705_5k_0900|127.0.0.1:8087|--port 8087' || true
```

Expected: `18449=FREE`; only the `rg` command may appear for the 5K run.

### Task 4: Compact Evidence and Update Docs

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Extract compact evidence**

Read:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path("docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/planner_trajectory_contact_retention_staged_combo_summary.json")
d = json.loads(p.read_text())
post = d.get("post_replay_replan") or {}
close = d.get("post_replay_close_hold") or {}
ret = close.get("retention_summary") or {}
print("status", d.get("status"))
print("blockers", d.get("blockers"))
print("post", {k: post.get(k) for k in ["successful_candidate_count", "failure_status_counts", "selected_waypoint_label", "available_action_points"]})
print("close", {k: close.get(k) for k in ["executed_steps", "reached_joint_target", "final_joint_target_abs_max_rad", "skipped_reason"]})
print("retention", {k: ret.get(k) for k in ["retention_pass", "tail_bilateral_overlap_records", "tail_required_roles_near_records", "tail_physx_required_roles_contact_records", "tail_contact_semantics_counts"]})
print("last_roles", ret.get("tail_last_required_role_states"))
PY
```

Expected: output clearly identifies one of these states:

```text
BLOCKED_5K_STAGED_COMBO_IK
BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME
PASS_5K_CONTACT_RETENTION_CANDIDATE
```

- [x] **Step 2: Write compact manifest**

Run this script to derive `summary_compact.json` from the live summary:

```bash
python - <<'PY'
import json
from pathlib import Path

base = Path("docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02")
summary = json.loads((base / "planner_trajectory_contact_retention_staged_combo_summary.json").read_text())
post = summary.get("post_replay_replan") or {}
close = summary.get("post_replay_close_hold") or {}
traj = summary.get("trajectory_execution") or {}
ret = close.get("retention_summary") or {}

if post.get("successful_candidate_count", 0) == 0:
    failure_counts = post.get("failure_status_counts") or {}
    selected = post.get("selected_waypoint_label")
    action_points = post.get("available_action_points") or 0
    if "MotionGenStatus.IK_FAIL" in failure_counts and selected is None and action_points == 0:
        classification = "BLOCKED_5K_STAGED_COMBO_IK"
    else:
        classification = "BLOCKED_5K_STAGED_COMBO_PLANNER_OR_RUN_FAILURE"
elif ret.get("retention_pass") is True and ret.get("tail_physx_required_roles_contact_records", 0) >= 15:
    classification = "PASS_5K_CONTACT_RETENTION_CANDIDATE"
else:
    classification = "BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME"

compact = {
    "stage": "EOS-2 Task 5K-A",
    "candidate_label": "x_m002_ori_z_p02",
    "classification": classification,
    "status": summary.get("status"),
    "blockers": summary.get("blockers"),
    "submit_exitcode": (base / "submit.exitcode.txt").read_text().strip(),
    "probe_exitcode": (base / "probe.exitcode.txt").read_text().strip(),
    "server_port": 18449,
    "object_frame_pose_contract": {
        "xyz": [-0.0009771048445254542, -0.11657822728157047, 0.008903118610382071],
        "q_wxyz": [0.949315309209365, -0.2133853445130493, -0.2180212864772773, -0.07572223643400897],
    },
    "trajectory_execution": {
        "executed_steps": traj.get("executed_steps"),
        "reached_joint_target": traj.get("reached_joint_target"),
        "final_joint_target_abs_max_rad": traj.get("final_joint_target_abs_max_rad"),
        "joint_target_tolerance_rad": traj.get("joint_target_tolerance_rad"),
    },
    "post_replay_replan": {
        "attempted": post.get("attempted"),
        "candidate_count": post.get("candidate_count"),
        "attempted_candidate_labels": post.get("attempted_candidate_labels"),
        "successful_candidate_count": post.get("successful_candidate_count"),
        "failure_status_counts": post.get("failure_status_counts"),
        "selected_waypoint_label": post.get("selected_waypoint_label"),
        "available_action_points": post.get("available_action_points"),
        "execution": post.get("execution"),
    },
    "post_replay_close_hold": {
        "enabled": close.get("enabled"),
        "executed_steps": close.get("executed_steps"),
        "reached_joint_target": close.get("reached_joint_target"),
        "final_joint_target_abs_max_rad": close.get("final_joint_target_abs_max_rad"),
        "close_width_m": close.get("close_width_m"),
        "skipped_reason": close.get("skipped_reason"),
    },
    "retention_summary": {
        "retention_pass": ret.get("retention_pass"),
        "retention_requires_physx_contact": ret.get("retention_requires_physx_contact"),
        "tail_available_records": ret.get("tail_available_records"),
        "tail_bilateral_overlap_records": ret.get("tail_bilateral_overlap_records"),
        "tail_required_roles_near_records": ret.get("tail_required_roles_near_records"),
        "tail_physx_required_roles_contact_records": ret.get("tail_physx_required_roles_contact_records"),
        "tail_contact_semantics_counts": ret.get("tail_contact_semantics_counts"),
        "tail_last_required_role_states": ret.get("tail_last_required_role_states"),
        "tail_role_axis_gap_stats_m": ret.get("tail_role_axis_gap_stats_m"),
    },
    "comparison_note": "Compare X/Y gaps separately against 5J-F and 5J-A before deciding any follow-up.",
    "claim_boundary": "diagnostic only; no stable grasp, micro-pull, door-open, Expert Oracle Score, policy score, official score, or full task completion",
}
(base / "summary_compact.json").write_text(json.dumps(compact, indent=2, ensure_ascii=False) + "\n")
print(base / "summary_compact.json")
PY
```

Expected: the script prints the compact manifest path and exits `0`.

- [x] **Step 3: Update docs with actual result**

Add one row to `docs/labutopia_lab_poc/evidence_manifests/README.md` after the prepared 5K row, and add one PM paragraph to `expert_oracle_score_plan.md` and `aan_consumer_handoff.md`.

Generate the PM sentence with this script, then paste the printed paragraph into both docs:

```bash
python - <<'PY'
import json
from pathlib import Path

p = Path("docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json")
d = json.loads(p.read_text())
cls = d["classification"]
if cls == "BLOCKED_5K_STAGED_COMBO_IK":
    plain = "桥接段能跑，但 `x_m002_ori_z_p02` 在 post-replay replan 阶段规划不到，所以没有 close-hold 和 retention 证据。"
elif cls == "BLOCKED_5K_STAGED_COMBO_PLANNER_OR_RUN_FAILURE":
    plain = "这轮没有形成可解释为 IK 的 post-replay 成功轨迹，需要先看 planner/server/probe failure 细节，不能把它归因为抓取失败。"
elif cls == "PASS_5K_CONTACT_RETENTION_CANDIDATE":
    plain = "这条 staged combination 首次通过 close-hold retention 和 required-role PhysX contact，只开启单独的 micro-pull 诊断评审门，不代表 micro-pull readiness 或 execution approval。"
else:
    plain = "这条 staged combination 能执行到 close-hold，但 strict retention 仍失败，需要按 X/Y gap 变化决定下一步。"
print("2026-07-05 Task 5K-A live candidate `x_m002_ori_z_p02` 已完成，compact manifest 是")
print("`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`。")
print(f"这轮结果是 `{cls}`。通俗讲，{plain}")
print("当前仍不能 claim stable grasp、door-open、Expert Oracle Score 或 score；只有 retention 通过时，才允许单独规划 micro-pull 诊断。")
PY
```

### Task 5: Verification and Review

**Files:**
- Verify: all 5K JSON manifests
- Verify: all updated Markdown docs

- [x] **Step 1: Run JSON validation**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json >/dev/null
```

Expected: both commands exit `0`.

- [x] **Step 2: Run diff and stale-phrase checks**

Run:

```bash
git diff --check -- \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/superpowers/plans/2026-07-05-eos2-staged-combination-review.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json
python - <<'PY'
from pathlib import Path

patterns = [
    "stable grasp " + "passed",
    "stable grasp" + "=true",
    "micro-pull ready" + "=true",
    "micro-pull readiness " + "passed",
    "door opened " + "passed",
    "door-open " + "success",
    "Expert Oracle Score " + "passed",
    "official score " + "passed",
    "wide live sweep " + "approved",
    "translation combination " + "approved",
]
paths = [
    Path("docs/labutopia_lab_poc/evidence_manifests/README.md"),
    Path("docs/labutopia_lab_poc/expert_oracle_score_plan.md"),
    Path("docs/labutopia_lab_poc/aan_consumer_handoff.md"),
    Path("docs/superpowers/plans/2026-07-05-eos2-staged-combination-review.md"),
]
hits = []
for path in paths:
    text = path.read_text()
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern in patterns:
            if pattern in line:
                hits.append(f"{path}:{lineno}:{pattern}:{line}")
if hits:
    print("\n".join(hits))
    raise SystemExit(1)
PY
```

Expected: `git diff --check` exits `0`; the stale-phrase script prints nothing and exits `0`.

- [x] **Step 3: Dispatch final technical and PM review**

Technical review questions:

```text
1. Is the live 5K classification supported by the raw summary?
2. Are X/Y gap comparisons reported separately against 5J-F and 5J-A?
3. Are server lifecycle notes separated from task success/failure?
4. Are stable grasp and score claims still blocked unless strict retention passed?
```

PM review questions:

```text
1. Can a product manager understand whether 5K-A improved, failed, or only moved the problem?
2. Is the next step concrete without implying the task is solved?
3. Are old 5J-only status statements clearly superseded by 5K-A?
```

Expected: no blocking issue. If either reviewer reports a blocker, patch docs/manifests and repeat Task 5 Steps 1-3 once.

Result:

```text
technical_review=PASS
pm_review=PASS_AFTER_STALE_CURRENT_NEXT_STEP_FIXES
```

## Self-Review

- Spec coverage: This plan covers the transition from 5J-F orientation-only evidence to one staged-combination review candidate and one possible live run.
- Placeholder scan: No replacement markers are left; future live-run values are generated from the raw summary by scripts in Task 4.
- Type consistency: Candidate labels, XYZ, WXYZ quaternion order, run IDs, port, and evidence paths are consistent across manifest, commands, and docs.
- Claim boundary: The plan forbids stable grasp, micro-pull, door-open, Expert Oracle Score, policy score, official score, and full task completion unless strict retention passes.

# EOS2 Approach-Seed Robot-Staging Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace blind contact/near offset tuning with a bounded sequence that proves whether DryingBox can reach the handle-front approach, contact, retention, micro-pull, and finally `Expert Oracle Score`.

**Architecture:** Keep the existing GenManip online probe, EBench `level1_open_door.yml`, cuRobo planner route, and LabUtopia evidence-manifest workflow. The next work isolates one variable at a time: first wrist orientation source, then approach seed, then robot staging. Each gate emits `PASS` or `BLOCKED` evidence and stops before the next gate if the previous gate has no executable trajectory.

**Tech Stack:** LabUtopia docs, GenManip `standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`, pytest, Isaac Sim 4.1, cuRobo `MotionGen.plan_single`, EBench / GenManip task YAML, JSON evidence manifests, conda env `embodied-eval-os-sim-isaacsim41-genmanip-py310`.

---

## Current Stop Decision

The current selected `mesh-open-face` approach route has reached its Gate 1C
stop condition. Do not continue broad sweeps over `contact_target_world`,
`approach_near_target_world`, `normal_sign`, face clearance, close-hold, or
score from the selected `post_bridge_local_z_m006_q_bridge` staging parent.
The next work must open a new reachable route first.

Evidence:

- `docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_candidate_preflight_live_20260705_primary/summary_compact.json`
  - `candidate_source=mesh-open-face`
  - `candidate_count=1`
  - preflight only, so no planner / retention / score claim.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_planner_readback_live_20260705_primary/summary_compact.json`
  - bridge replay reached joint target.
  - full post-replay contact target attempted once.
  - cuRobo returned `MotionGenStatus.IK_FAIL`.
  - `available_action_points=0`.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_bridge_to_near_bounded_sanity_20260705/summary_compact.json`
  - `0.035m` and `0.045m` `approach_near_target_world` both generated numeric waypoints.
  - both bridge replays reached joint target.
  - both near targets returned `MotionGenStatus.IK_FAIL`.
  - `post_replay_action_points_available_any_attempt=false`.
  - `stop_contact_tuning=true`.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_to_mesh_open_face_near_live_20260705/summary_compact.json`
  - bridge replay reached joint target.
  - selected staging parent `post_bridge_local_z_m006_q_bridge` reached joint target.
  - Gate 1C follow-up to mesh-open-face `approach_near_target_world` returned `MotionGenStatus.IK_FAIL`.
  - `available_action_points=0` for the follow-up.
  - classification=`BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS`.

PM wording:

```text
现在不是资产导入、metric、score、候选生成的问题。我们已经证明机器人能走到 bridge，也能走到选中的中间站；但从这个中间站继续到把手正前方安全点时没有可执行轨迹，所以不能进入闭爪、保持、微拉或算分。
```

Engineering wording:

```text
The proven blocker is the selected bridge + `post_bridge_local_z_m006_q_bridge` staging-parent route's reachability to mesh-open-face `approach_near_target_world`. This does not prove global door-opening impossibility, all staging impossibility, or Expert Oracle Score failure.
```

## Definition Of Done

This goal is not "done" when a candidate exists. It is done only when the chain below reaches Gate 5.

| Gate | Question | Success Evidence | Stop / Blocked Evidence |
| --- | --- | --- | --- |
| Gate 1: Approach Seed / Wrist Orientation / Robot Staging | Can Franka reach a safe handle-front approach pose from a designed staging state? | `selected_plan_success=true`, `available_action_points>0`, action replay executed, and readback reached joint tolerance. | Bounded orientation/seed/staging candidates all return `MotionGenStatus.IK_FAIL` or zero action points. |
| Gate 2: Full Contact Planner / Readback | From a reachable near/staging pose, can Franka plan and replay to the handle contact target? | contact target has planner action points and readback reaches joint tolerance. | contact remains `IK_FAIL` or replay fails before close-hold. |
| Gate 3: Close-Hold / Contact Retention | Does closing the gripper actually retain the handle between the fingers? | close-hold executed; `retention_pass=true`; tail bilateral overlap, required-role near, and required-role PhysX contact are all non-zero. | retention fields remain zero or unavailable. |
| Gate 4: Micro-Pull / Door Joint Readback | Does the retained grasp move the articulated door in the scoring direction? | door joint / angle readback changes in the expected direction and reaches the configured threshold. | slip, no door-angle change, or action interruption. |
| Gate 5: Expert Oracle Score | Does the expert answer score under the EBench metric? | score manifest with expert trajectory, metric fields, and action evidence. | any earlier gate is not passed; score must not run. |

## Expected Decision Points

This plan is intentionally not an open-ended tuning loop. Each stage answers one
small question and either unlocks the next stage or stops the current route.

| Decision Point | What We Can Say | What We Cannot Say |
| --- | --- | --- |
| Current status after Gate 1C | The selected bridge + `post_bridge_local_z_m006_q_bridge` route reaches staging, but cannot reach mesh-open-face `approach_near_target_world`. | Gate 1 has passed, contact is ready, or score can run. |
| Current no-go reached | Stop this selected staging-parent route and redesign robot layout/staging or candidate generation before any contact/score attempt. | DryingBox cannot be opened, all staging is impossible, or Expert Oracle Score is impossible. |
| Gate 3 passes | The robot can close and retain the handle under contact telemetry. | The door is opened or score is valid. |
| Gate 4 passes | Engineering route is close: retained grasp moves the articulated door in the scoring direction. | Official metric score is proven. |
| Gate 5 passes | Evaluation route is done: expert route records `PASS_EXPERT_ORACLE_SCORE_RECORDED` under EBench metric. | Policy or official leaderboard performance is proven unless separately run. |

The earliest "current route is not workable" conclusion is at Gate 1, after
bounded orientation-source, staging-parent, and staging-to-handle-front-near
checks have been exhausted. That point was reached on 2026-07-05 for the selected
`post_bridge_local_z_m006_q_bridge` route. The conclusion must be narrow:

```text
current bridge + selected staging/orientation family is not a viable route to handle-front approach
```

It must not be broadened to:

```text
DryingBox cannot be opened
Expert Oracle Score is impossible
all robot staging is impossible
```

PM wording after Gate 1C:

```text
现在已经不是“还没试到位”。我们已经证明机器人能走到 bridge，也能走到选中的中间站
post_bridge_local_z_m006_q_bridge；但从这个中间站继续到把手正前方安全点时，cuRobo
还是 IK_FAIL，没有 action points 可以执行。所以当前这条路线要停止，不能再往 contact、
close-hold、micro-pull 或 Expert Oracle Score 走。下一步要换路线设计，而不是继续盲调。
```

## File Responsibilities

- `docs/superpowers/plans/2026-07-05-eos2-approach-seed-robot-staging-redesign.md`: this gate plan and stop rules.
- `docs/labutopia_lab_poc/evidence_manifests/README.md`: evidence index and PM-readable status after each gate.
- `docs/labutopia_lab_poc/aan_consumer_handoff.md`: cross-team handoff status.
- `docs/labutopia_lab_poc/expert_oracle_score_plan.md`: no-score boundary until Gate 5.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`: probe CLI, mesh-open-face waypoint builder, and planner/readback harness.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`: focused TDD tests for new CLI and summary fields.

## Required Classification Strings

```text
PREPARED_APPROACH_SEED_ROBOT_STAGING_REDESIGN_NOT_LIVE_EVIDENCE
PASS_APPROACH_SEED_ORIENTATION_SOURCE_CODE_READY_NOT_LIVE_EVIDENCE
BLOCKED_APPROACH_SEED_ORIENTATION_SOURCE_IK_FAIL_NO_ACTION_POINTS
STAGING_CONTINUATION_EVIDENCE_ONLY_REQUIRES_GATE_1C_STAGING_TO_MESH_OPEN_FACE_APPROACH_NEAR
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
BLOCKED_APPROACH_SEED_STAGING_FAMILY_IK_FAIL_NO_ACTION_POINTS
BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS
BLOCKED_APPROACH_SEED_SIBLING_STAGING_TO_NEAR_FAMILY_IK_FAIL_NO_ACTION_POINTS
PASS_CONTACT_PLANNER_READBACK_READY_FOR_CLOSE_HOLD
BLOCKED_CONTACT_PLANNER_READBACK
PASS_CLOSE_HOLD_RETENTION_READY_FOR_MICRO_PULL
BLOCKED_CLOSE_HOLD_RETENTION
PASS_MICRO_PULL_DOOR_READBACK_READY_FOR_EXPERT_ORACLE_SCORE
BLOCKED_MICRO_PULL_DOOR_READBACK
PASS_EXPERT_ORACLE_SCORE_RECORDED
```

## Gate 1 Strategy

The next smallest test is not another handle offset. It is the same `approach_near_target_world` position with a different wrist-orientation source.

Current failing variant:

```text
position source: mesh-open-face approach_near_target_world
approach_offset_m: 0.045
orientation source: native-open controller orientation
result: MotionGenStatus.IK_FAIL, 0 action points
```

First replacement:

```text
position source: same mesh-open-face approach_near_target_world
approach_offset_m: 0.045
orientation source: post-replay state.ee_pose orientation
expected diagnostic value: separates "native-open wrist is unreachable here" from "the position/staging itself is unreachable"
```

Decision tree:

```text
If post-replay-ee orientation succeeds:
  classify as PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT.
  Proceed to Gate 2 with staged orientation transition and contact target.

If post-replay-ee orientation also returns IK_FAIL / 0 action points:
  stop orientation-source tuning.
  Use the earlier successful post-bridge local continuation evidence to design a staging family.

If the staging family also returns IK_FAIL / 0 action points:
  classify as BLOCKED_APPROACH_SEED_STAGING_FAMILY_IK_FAIL_NO_ACTION_POINTS.
  The conclusion is that the current bridge/staging route is not viable for handle-front approach.

If the staging family finds a reachable staging parent:
  classify as STAGING_CONTINUATION_EVIDENCE_ONLY_REQUIRES_GATE_1C_STAGING_TO_MESH_OPEN_FACE_APPROACH_NEAR.
  Do not proceed to contact yet.
  Run Gate 1C from that selected staging parent to mesh-open-face approach_near_target_world.

If Gate 1C succeeds:
  classify as PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT.
  Proceed to Gate 2 contact planner/readback.

If Gate 1C fails with IK_FAIL / 0 action points:
  classify as BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS.
  The narrow conclusion is that the current selected bridge + staging parent cannot reach the handle-front near pose.
```

## Task 1: Add Wrist Orientation Source To Mesh-Open-Face Candidate Builder

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [x] **Step 1: Write the failing parse test**

Add this test next to `test_parse_args_accepts_post_replay_mesh_open_face_candidate_source`:

```python
def test_parse_args_accepts_post_replay_mesh_open_face_orientation_source(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "online_open_door_oracle_probe.py",
            "--port",
            "18189",
            "--run-id",
            "unit_parse_post_replay_mesh_open_face_orientation_source",
            "--output",
            str(tmp_path / "summary.json"),
            "--trace-jsonl",
            str(tmp_path / "trace.jsonl"),
            "--planner-trajectory-post-replay-candidate-source",
            "mesh-open-face",
            "--planner-trajectory-post-replay-mesh-open-face-orientation-source",
            "post-replay-ee",
        ],
    )

    args = probe.parse_args()

    assert (
        args.planner_trajectory_post_replay_mesh_open_face_orientation_source
        == "post-replay-ee"
    )
```

- [x] **Step 2: Run the parse test and verify it fails**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "post_replay_mesh_open_face_orientation_source" -q
```

Expected before implementation:

```text
unrecognized arguments: --planner-trajectory-post-replay-mesh-open-face-orientation-source
```

- [x] **Step 3: Write the failing builder test**

Add this test near `test_build_post_replay_mesh_open_face_candidate_object_frame_waypoints_uses_geometry_audit_fallback_normal`:

```python
def test_build_post_replay_mesh_open_face_candidate_can_use_post_replay_ee_orientation(
    tmp_path,
):
    geometry_audit_path = tmp_path / "geometry_audit.json"
    geometry_audit_path.write_text(
        json.dumps(
            {
                "mesh_aware_handle_geometry_audit": {
                    "status": (
                        "PASS_HANDLE_GEOMETRY_AUDIT_READY_FOR_MESH_AWARE_CANDIDATE"
                    ),
                    "candidate_generation_allowed": True,
                    "selected_handle_prim_path": "/World/DryingBox/handle",
                    "selected_door_leaf_prim_path": "/World/DryingBox/door",
                    "hinge_joint_prim_path": "/World/DryingBox/RevoluteJoint",
                    "hinge_axis_world": [0.0, 1.0, 0.0],
                    "handle_open_face_normal_world": [0.0, 1.0, 0.0],
                    "handle_open_face_source": (
                        "handle_door_center_delta_overlap_fallback"
                    ),
                    "handle_open_face_confidence": "fallback",
                },
                "static_usd_geometry_ledger": {
                    "available": True,
                    "handle_records": [
                        {
                            "available": True,
                            "prim_path": "/World/DryingBox/handle",
                            "visual_bbox": {
                                "available": True,
                                "bbox_min_world": [0.45, 0.22, 1.0],
                                "bbox_max_world": [0.50, 0.27, 1.2],
                            },
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    post_replay_orientation = [0.7071067811865476, 0.0, 0.7071067811865476, 0.0]
    args = Namespace(
        planner_trajectory_post_replay_candidate_label=(
            "post_replay_mesh_open_face_near"
        ),
        planner_trajectory_post_replay_mesh_open_face_geometry_audit_json=str(
            geometry_audit_path
        ),
        planner_trajectory_post_replay_mesh_open_face_approach_offset_m=0.045,
        planner_trajectory_post_replay_mesh_open_face_clearance_m=0.003,
        planner_trajectory_post_replay_mesh_open_face_normal_sign="primary",
        planner_trajectory_post_replay_mesh_open_face_target_world_key=(
            "approach_near_target_world"
        ),
        planner_trajectory_post_replay_mesh_open_face_orientation_source=(
            "post-replay-ee"
        ),
    )
    worker_obs = _worker_obs_with_debug(
        [0.40, 0.02, 0.46],
        handle_position=[0.475, 0.245, 1.1],
        handle_orientation=[1.0, 0.0, 0.0, 0.0],
    )
    worker_obs["state.ee_pose"] = [[0.40, 0.02, 0.46], post_replay_orientation]

    waypoints, summary = (
        probe.build_post_replay_mesh_open_face_candidate_object_frame_waypoints(
            args,
            worker_obs=worker_obs,
            rel_object_uid="obj_DryingBox_01_handle",
        )
    )

    assert len(waypoints) == 1
    assert summary["target_world_orientation_source"] == "post_replay_state.ee_pose[1]"
    assert summary["target_world_orientation_wxyz"] == pytest.approx(
        post_replay_orientation
    )
    assert waypoints[0]["target_world_orientation_source"] == (
        "post_replay_state.ee_pose[1]"
    )
    assert waypoints[0]["target_world_orientation_wxyz"] == pytest.approx(
        post_replay_orientation
    )
    assert waypoints[0]["orientation"] == pytest.approx(post_replay_orientation)
```

- [x] **Step 4: Run the builder test and verify it fails**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "post_replay_mesh_open_face_candidate_can_use_post_replay_ee_orientation" -q
```

Expected before implementation:

```text
KeyError: 'target_world_orientation_source'
```

or an assertion failure showing the waypoint still uses `native-open`.

- [x] **Step 5: Implement the CLI argument**

Add this parser argument after `--planner-trajectory-post-replay-mesh-open-face-target-world-key`:

```python
parser.add_argument(
    "--planner-trajectory-post-replay-mesh-open-face-orientation-source",
    choices=("native-open", "post-replay-ee"),
    default="native-open",
    help=(
        "Select the world orientation used by generated mesh-open-face "
        "post-replay waypoints. native-open preserves the old controller "
        "orientation; post-replay-ee reuses the live state.ee_pose orientation "
        "after bridge replay to isolate wrist-orientation reachability."
    ),
)
```

- [x] **Step 6: Implement the orientation resolver**

Add this helper near `build_post_replay_candidate_object_frame_waypoint`:

```python
def resolve_post_replay_mesh_open_face_world_orientation(
    args: argparse.Namespace,
    *,
    worker_obs: dict[str, Any],
) -> tuple[list[float], str]:
    source = str(
        getattr(
            args,
            "planner_trajectory_post_replay_mesh_open_face_orientation_source",
            "native-open",
        )
    )
    if source == "native-open":
        return (
            list(NATIVE_OPEN_CONTROLLER_ORIENTATION_WXYZ),
            "native_open_controller_orientation_wxyz",
        )
    if source == "post-replay-ee":
        return (
            _normalize_quaternion_wxyz(
                _ee_orientation(worker_obs),
                name="state.ee_pose[1]",
            ).tolist(),
            "post_replay_state.ee_pose[1]",
        )
    raise ValueError(f"unsupported mesh-open-face orientation source: {source}")
```

- [x] **Step 7: Thread the orientation source into the waypoint metadata**

Change `build_post_replay_candidate_object_frame_waypoint` signature:

```python
def build_post_replay_candidate_object_frame_waypoint(
    *,
    candidate: dict[str, Any],
    debug_state: dict[str, Any],
    label: str,
    rel_object_uid: str,
    target_world_orientation_wxyz: Any = NATIVE_OPEN_CONTROLLER_ORIENTATION_WXYZ,
    target_world_orientation_source: str = "native_open_controller_orientation_wxyz",
    waypoint_source: str = "planner_trajectory_post_replay_centerline_candidate",
    target_world_key: str = "contact_target_world",
) -> dict[str, Any]:
```

Add these two fields to `waypoint`:

```python
"target_world_orientation_wxyz": _normalize_quaternion_wxyz(
    target_world_orientation_wxyz,
    name="target_world_orientation_wxyz",
).tolist(),
"target_world_orientation_source": str(target_world_orientation_source),
```

In `build_post_replay_mesh_open_face_candidate_object_frame_waypoints`, replace the fixed native-open argument with:

```python
target_world_orientation, target_world_orientation_source = (
    resolve_post_replay_mesh_open_face_world_orientation(args, worker_obs=worker_obs)
)
waypoint = build_post_replay_candidate_object_frame_waypoint(
    candidate=candidate,
    debug_state=debug,
    label=label,
    rel_object_uid=rel_object_uid,
    target_world_orientation_wxyz=target_world_orientation,
    target_world_orientation_source=target_world_orientation_source,
    waypoint_source="planner_trajectory_post_replay_mesh_open_face_candidate",
    target_world_key=str(
        getattr(
            args,
            "planner_trajectory_post_replay_mesh_open_face_target_world_key",
            "contact_target_world",
        )
    ),
)
```

Add these fields to the generated `summary`:

```python
"target_world_orientation_wxyz": target_world_orientation,
"target_world_orientation_source": target_world_orientation_source,
```

- [x] **Step 8: Run focused tests**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "mesh_open_face or post_replay or centerline" -q
```

Expected:

```text
all selected tests pass
```

- [x] **Step 9: Run syntax and diff checks**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
"$PY" -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
git diff --check -- standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
```

Expected: both commands exit `0`.

- [x] **Step 10: Write a code checkpoint manifest**

Create:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_code_checkpoint_20260705.json
```

Content:

```json
{
  "schema_version": 1,
  "classification": "PASS_APPROACH_SEED_ORIENTATION_SOURCE_CODE_READY_NOT_LIVE_EVIDENCE",
  "diagnostic_only": true,
  "code_surface": {
    "cli": "--planner-trajectory-post-replay-mesh-open-face-orientation-source",
    "choices": ["native-open", "post-replay-ee"],
    "default": "native-open",
    "backward_compatible": true
  },
  "claim_boundary": {
    "claim_allowed": [
      "probe can build mesh-open-face post-replay candidates with native-open or post-replay-ee world orientation",
      "code path is unit-tested but not live Isaac evidence"
    ],
    "claim_not_allowed": [
      "near reachability solved",
      "contact reachability solved",
      "close-hold or retention works",
      "Expert Oracle Score is ready"
    ]
  }
}
```

Validate:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_code_checkpoint_20260705.json >/dev/null
```

Expected: command exits `0`.

## Task 2: Run The Single Wrist-Orientation Isolation Probe

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045/`
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_bridge_to_near_live_20260705_farther045/01_primary_normal_clearance_0p003_approach_0p045_target_approach_near/probe.command.txt`

- [x] **Step 1: Start a fresh GenManip server**

Run in a foreground shell:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
RUN_ID=labutopia_eos2_approach_seed_orientation_source_20260705_post_replay_ee_near045
SERVER_RUN_ID=${RUN_ID}_server
PYTHONNOUSERSITE=1 \
RAY_ADDRESS=local \
RAY_USAGE_STATS_ENABLED=0 \
RAY_TMPDIR=/tmp/r_eos2_orientation_18465 \
LABUTOPIA_ORACLE_DEBUG_OBS=1 \
LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1 \
GENMANIP_VERBOSE=1 \
PATH=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin:$PATH \
PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback \
LD_LIBRARY_PATH=/isaac-sim/exts/omni.isaac.ml_archive/pip_prebundle/nvidia/cuda_runtime/lib:/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin:/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps:/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/torch/lib:${LD_LIBRARY_PATH:-} \
"$PY" -u ray_eval_server.py --host 127.0.0.1 --port 18465 --run_id "$SERVER_RUN_ID" --no_save_process --episode_recorder_save_every 0 --reset_timeout 1200 --step_timeout 1200 --load_config_timeout 300
```

Expected: server stays running and listens on `127.0.0.1:18465`.

- [x] **Step 2: Submit the task**

Run after server readiness:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
RUN_ID=labutopia_eos2_approach_seed_orientation_source_20260705_post_replay_ee_near045
TASK_CONFIG=ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback \
"$PY" - <<PY
from genmanip_client.submit import start_job
start_job("http://127.0.0.1:18465", ["$TASK_CONFIG"], "$RUN_ID")
PY
```

Expected: submit exits `0`.

- [x] **Step 3: Run exactly one post-replay-ee orientation probe**

Create the evidence directory and run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
EVID=docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045
mkdir -p "$EVID"
PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
RUN_ID=labutopia_eos2_approach_seed_orientation_source_20260705_post_replay_ee_near045
CMD="PYTHONNOUSERSITE=1 PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback $PY /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py --host 127.0.0.1 --port 18465 --run-id $RUN_ID --task-config ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml --output /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/$EVID/summary.json --trace-jsonl /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/$EVID/trace.jsonl --probe-mode planner-trajectory-execution-readback --planner-trajectory-waypoint-label approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity --planner-trajectory-extra-object-frame-waypoint approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity 0.0010228951554745458 -0.11657822728157047 0.014903118610382071 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849 --planner-trajectory-post-replay-replan --planner-trajectory-post-replay-candidate-source mesh-open-face --planner-trajectory-post-replay-candidate-label post_replay_mesh_open_face_post_replay_ee_approach_near_clearance_0p003_approach_0p045 --planner-trajectory-post-replay-mesh-open-face-geometry-audit-json /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_geometry_audit_20260705.json --planner-trajectory-post-replay-mesh-open-face-approach-offset-m 0.045 --planner-trajectory-post-replay-mesh-open-face-clearance-m 0.003 --planner-trajectory-post-replay-mesh-open-face-normal-sign primary --planner-trajectory-post-replay-mesh-open-face-target-world-key approach_near_target_world --planner-trajectory-post-replay-mesh-open-face-orientation-source post-replay-ee --planner-trajectory-post-replay-execute"
printf '%s\n' "$CMD" > "$EVID/probe.command.txt"
bash "$EVID/probe.command.txt"
```

Expected:

```text
summary.json and trace.jsonl are created
```

- [x] **Step 4: Classify the result**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python - <<'PY'
import json
p = "docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045/summary.json"
with open(p, encoding="utf-8") as f:
    d = json.load(f)
post = d.get("post_replay_replan", {})
print("status=", d.get("status"))
print("candidate_count=", post.get("candidate_count"))
print("selected_plan_success=", post.get("selected_plan_success"))
print("available_action_points=", post.get("available_action_points"))
print("failure_status_counts=", post.get("failure_status_counts"))
print("execution=", post.get("execution"))
PY
```

Success classification:

```text
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
```

Required facts:

```text
selected_plan_success=true
available_action_points>0
post_replay execution executed_steps>0
post_replay execution reached_joint_target=true
```

Failure classification:

```text
BLOCKED_APPROACH_SEED_ORIENTATION_SOURCE_IK_FAIL_NO_ACTION_POINTS
```

Required facts:

```text
failure_status_counts includes MotionGenStatus.IK_FAIL
available_action_points=0
selected_plan_success=false
```

- [x] **Step 5: Stop the server and verify no leftover process**

After Ctrl-C in the server shell, run:

```bash
ss -ltnp | rg ':18465' || true
ps -eo pid,ppid,stat,cmd | rg 'ray_eval_server.py --host 127.0.0.1 --port 18465|online_open_door_oracle_probe|labutopia_eos2_approach_seed_orientation_source_20260705_post_replay_ee_near045' || true
```

Expected: no live server/probe process remains.

### Task 2 Result: Orientation Source Is Not Enough

Evidence:

- `docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045/summary_compact.json`
- `docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045/summary.json`

Classification:

```text
BLOCKED_APPROACH_SEED_ORIENTATION_SOURCE_IK_FAIL_NO_ACTION_POINTS
```

Facts:

```text
candidate_source=mesh-open-face
target_world_key=approach_near_target_world
orientation_source=post_replay_state.ee_pose[1]
candidate_count=1
attempted_candidate_count=1
successful_candidate_count=0
failure_status_counts={"MotionGenStatus.IK_FAIL": 1}
available_action_points=0
selected_plan_success=false
```

Important boundary:

```text
This is enough to stop wrist-orientation-source tuning.
This is not enough to declare the whole Gate 1 route impossible.
```

Why the boundary matters: bridge replay reached joint tolerance
(`final_joint_target_abs_max_rad=0.004973113536834717 < 0.02`), but this run also
hit the configured `64` step cap while `151` bridge action points were available.
So this is a strong negative diagnostic for the `post-replay-ee` orientation
variant, not a final global no-go for DryingBox, Expert Oracle Score, or all
robot staging.

Next step is therefore Task 3 only: run the bounded staging family. Do not go
back to contact offset, normal sign, face clearance, material, camera, close-hold,
micro-pull, or score from this result.

## Task 3: If Orientation Source Fails, Run A Bounded Staging Family

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_family_live_20260705/`

- [x] **Step 1: Confirm the earlier successful local continuation**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python - <<'PY'
import json
p = "docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json"
with open(p, encoding="utf-8") as f:
    d = json.load(f)
post = d["post_replay_replan"]
print("selected_waypoint_label=", post["selected_waypoint_label"])
print("selected_plan_success=", post["selected_plan_success"])
print("available_action_points=", post["available_action_points"])
print("execution_reached=", post["execution"]["reached_joint_target"])
PY
```

Expected:

```text
selected_waypoint_label= post_bridge_local_z_m006_q_bridge
selected_plan_success= True
available_action_points= 33
execution_reached= True
```

Verified on 2026-07-05:

```text
source=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json
selected_waypoint_label=post_bridge_local_z_m006_q_bridge
selected_plan_success=True
available_action_points=33
execution_reached=True
execution_steps=33
final_joint_error=6.794929504394531e-05
```

- [x] **Step 2: Prepare three bounded staging candidates**

Use only these existing, already documented candidates first:

```text
post_bridge_local_z_m006_q_bridge
post_bridge_local_y_p006_q_bridge
post_bridge_local_x_m006_q_bridge
```

Do not add new contact offsets in this task. The purpose is to answer whether a staging pose near the known successful local continuation can become a safe parent state for the handle-front approach.

- [x] **Step 3: Run a route-bound staging-family probe**

Run one fresh server and probe using the same server discipline as Task 2, but with evidence root:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_family_live_20260705/
```

The probe must use:

```text
--planner-trajectory-post-replay-extra-object-frame-waypoint post_bridge_local_z_m006_q_bridge 0.0010228951554745458 -0.11657822728157047 0.008903118610382071 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849
--planner-trajectory-post-replay-extra-object-frame-waypoint post_bridge_local_y_p006_q_bridge 0.0010228951554745458 -0.11057822728157047 0.014903118610382071 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849
--planner-trajectory-post-replay-extra-object-frame-waypoint post_bridge_local_x_m006_q_bridge -0.004977104844525454 -0.11657822728157047 0.014903118610382071 0.9478491886430741 -0.209547848787944 -0.22171216853953848 -0.09227854018408849
--planner-trajectory-post-replay-execute
```

Expected final Gate 1 success classification:

```text
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
```

Task 3 all-staging-fail classification:

```text
BLOCKED_APPROACH_SEED_STAGING_FAMILY_IK_FAIL_NO_ACTION_POINTS
```

Actual 2026-07-05 Task 3 result:

```text
evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_family_live_20260705/summary_compact.json
classification=STAGING_CONTINUATION_EVIDENCE_ONLY_REQUIRES_GATE_1C_STAGING_TO_MESH_OPEN_FACE_APPROACH_NEAR
selected_staging_parent=post_bridge_local_z_m006_q_bridge
staging_available_action_points=90
staging_replay_reached_joint_target=true
gate1_complete=false
```

Boundary:

```text
Gate 1B found a reachable staging parent, not a reachable handle-front approach pose.
Do not run contact, close-hold, micro-pull, Expert Oracle Score, or policy scoring from this evidence.
```

## Task 3C: Verify Staging Parent To Mesh-Open-Face Approach Near

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_to_mesh_open_face_near_live_20260705/`

- [x] **Step 1: Add chained follow-up replan support**

The current probe can do bridge -> one post-replay replan. Gate 1C needs
bridge -> selected staging parent -> mesh-open-face `approach_near_target_world`.
Add a default-off follow-up replan path so old evidence remains comparable.

Required CLI:

```text
--planner-trajectory-post-replay-followup-replan
--planner-trajectory-post-replay-followup-candidate-source mesh-open-face
--planner-trajectory-post-replay-followup-execute
```

Required summary key:

```text
post_replay_followup_replan
```

Implemented on 2026-07-05 as default-off CLI so old evidence remains comparable.
The follow-up replan is only eligible after post-replay staging execution reaches
joint tolerance and has reusable worker state.

- [x] **Step 2: Run focused TDD checks**

Run from the GenManip worktree:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/user/zhuzihou/conda-managed/envs/embodied-eval-os-isaacsim41-py310/bin/python
PYTHONPATH=. "$PY" -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "post_replay_followup" -q
PYTHONPATH=. "$PY" -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
```

Expected:

```text
follow-up parse and behavior tests pass
py_compile exits 0
```

Verified on 2026-07-05:

```text
focused pytest: 20 passed, 272 deselected
py_compile: exit 0
git diff --check on GenManip probe/test: exit 0
```

Code checkpoint:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_to_near_followup_code_checkpoint_20260705.json
```

- [x] **Step 3: Run one live Gate 1C probe**

Use the selected Gate 1B parent only:

```text
post_bridge_local_z_m006_q_bridge
```

Then generate one mesh-open-face target:

```text
target_world_key=approach_near_target_world
approach_offset_m=0.045
clearance_m=0.003
normal_sign=primary
orientation_source=post-replay-ee
```

Success classification:

```text
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
```

Required facts:

```text
post_replay_followup_replan.selected_plan_success=true
post_replay_followup_replan.available_action_points>0
post_replay_followup_replan.execution.reached_joint_target=true
```

Failure classification:

```text
BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS
```

Stop if Gate 1C fails. This is the first clean point where we can tell PM:

```text
The current selected bridge + staging-parent route cannot reach the handle-front near pose under the EBench/cuRobo execution route. We should stop this route and redesign robot layout/staging or candidate generation, rather than continue contact/score attempts.
```

Actual 2026-07-05 Gate 1C result:

```text
evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_to_mesh_open_face_near_live_20260705/summary_compact.json
classification=BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS
bridge_replay.reached_joint_target=true
bridge_replay.available_action_points=151
bridge_replay.executed_steps=64
selected_staging_parent.waypoint_label=post_bridge_local_z_m006_q_bridge
selected_staging_parent.available_action_points=91
selected_staging_parent.executed_steps=64
selected_staging_parent.reached_joint_target=true
gate1c_followup.target_world_key=approach_near_target_world
gate1c_followup.target_world_orientation_source=post_replay_state.ee_pose[1]
gate1c_followup.selected_plan_success=false
gate1c_followup.available_action_points=0
gate1c_followup.failure_status_counts={"MotionGenStatus.IK_FAIL": 1}
```

Boundary after Gate 1C:

```text
Stop the selected bridge + post_bridge_local_z_m006_q_bridge route.
Do not run Task 4 contact, Task 5 close-hold, Task 6 micro-pull, or Task 7 score from this route.
Do not claim DryingBox cannot be opened, all staging is impossible, or Expert Oracle Score is impossible.
Next work must be a route redesign or a pre-registered sibling staging-to-near family, not contact/score tuning.
```

## Next Route Split After Gate 1C

Multi-angle review on 2026-07-05 reached the same recommendation: do not jump
straight to broad redesign, and do not continue contact/score attempts. The
next step is a small, pre-registered sibling staging-to-near triage, because
Gate 1C only ruled out one selected staging parent.

| Next Stage | Purpose | Stop Rule |
| --- | --- | --- |
| Gate 1D: Sibling Staging-to-Near Bounded Triage | Test whether `post_bridge_local_z_m006_q_bridge` was simply the wrong staging parent. Keep the same bridge, mesh-open-face `approach_near_target_world`, orientation source, planner route, and stop rules; only vary a small registered sibling staging set. | If every sibling returns `MotionGenStatus.IK_FAIL`, zero action points, or replay readback failure, stop this staging family and escalate to Gate 1R. |
| Gate 1R: Robot Layout / Staging Redesign Gate | Redesign robot layout, approach seed, staging, or candidate-generation only after Gate 1D fails. | Must produce `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`; otherwise do not enter contact. |
| Gate 2: Contact Planner / Readback Re-entry | Re-enter contact only after a new Gate 1 route reaches handle-front near with executable replay evidence. | If contact planner/readback fails, stop at Gate 2 and do not enter close-hold, micro-pull, or score. |

Gate 1D candidate policy:

```text
pre_register_all_candidates=true
change_only=staging_parent
do_not_change=bridge, target_world_key, approach_offset_m, face_clearance_m, normal_sign, orientation_source, planner_ignore_list, metric, asset
target_world_key=approach_near_target_world
classification_if_all_fail=BLOCKED_APPROACH_SEED_SIBLING_STAGING_TO_NEAR_FAMILY_IK_FAIL_NO_ACTION_POINTS
classification_if_any_pass=PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
```

Actual 2026-07-05 Gate 1D result:

```text
evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_sibling_staging_to_near_live_20260705/summary_compact.json
classification=BLOCKED_APPROACH_SEED_SIBLING_STAGING_TO_NEAR_FAMILY_IK_FAIL_NO_ACTION_POINTS
registered_candidates=post_bridge_local_y_p006_q_bridge, post_bridge_local_x_m006_q_bridge
y_p006.bridge_replay.reached_joint_target=true
y_p006.staging_replan.failure_status_counts={"MotionGenStatus.IK_FAIL": 1}
y_p006.staging_replan.available_action_points=0
y_p006.followup_to_near.skipped_reason=no_post_replay_execution
x_m006.bridge_replay.reached_joint_target=true
x_m006.staging_replan.failure_status_counts={"MotionGenStatus.IK_FAIL": 1}
x_m006.staging_replan.available_action_points=0
x_m006.followup_to_near.skipped_reason=no_post_replay_execution
```

Boundary after Gate 1D:

```text
The registered sibling staging family did not open a new Gate 1 route.
The failure happened before follow-up to approach_near_target_world, at sibling staging replan.
Do not run Gate 2 contact from y_p006 or x_m006.
Proceed to Gate 1R: redesign robot layout / staging / candidate-generation.
```

## Gate 1R: Robot Layout / Staging / Candidate-Generation Redesign Gate

Gate 1R is the next stage after Gate 1D. It is not a contact stage. It exists
only to recover a valid handle-front near route:

```text
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
```

PM name:

```text
Gate 1R：机器人布局 / 中间站 / 候选生成重设门
Gate 1R: Robot Layout / Staging / Candidate-Generation Redesign Gate
```

Gate 1R small gates:

| Small Gate | Question | Continue Condition |
| --- | --- | --- |
| 1R-0 Failure Boundary Freeze | What did Gate 1D actually rule out? | Only `z_m006` selected route and pre-registered `y_p006/x_m006` sibling family are ruled out; no global DryingBox/all-staging/score no-go claim. |
| 1R-1 Redesign Candidate Review | Which route variable changes? | Pre-register a bounded candidate set. State whether the candidate changes robot layout, approach seed, staging parent, wrist orientation, or candidate-generation. |
| 1R-2 Candidate / Geometry Preflight | Can the new route generate a legal handle-front near candidate? | At least one numeric `approach_near_target_world` / staging-to-near candidate with metadata. If `candidate_count=0`, stop in Gate 1R. |
| 1R-3 Full Near Planner / Readback | Can the new route physically replay to handle-front near? | `selected_plan_success=true`, `available_action_points>0`, action joint payload exists, and replay readback reaches joint tolerance. |
| 1R-4 Gate 2 Handoff | Is contact allowed again? | Only after `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`; otherwise remain in Gate 1. |

Engineering priority after review:

```text
priority_1=robot base/layout XY relative to handle
priority_2=staging waypoint generation under best layout
avoid_first=reset joint seed, final target/orientation sweep, wider local sibling staging sweep
```

Why: mesh-open-face candidate generation already works; `0.035m` / `0.045m`
near targets entered planner but returned `IK_FAIL`; `post-replay-ee`
orientation also returned `IK_FAIL`; `z_m006` staging is reachable but cannot
continue to near; `y_p006/x_m006` sibling staging failed before follow-up. The
next likely lever is workspace geometry, not another contact/near/orientation
micro-tweak in the same layout.

Pre-registered Gate 1R layout candidates:

| Candidate | Robot Base Position | Fixed Contract | Success / Stop Rule |
| --- | --- | --- | --- |
| `R1_layout_y_p010` | `[-0.4, 0.10, 0.73]` | same asset/metric/planner route, no reset seed, same bridge label, same `post_bridge_local_z_m006_q_bridge`, mesh-open-face primary normal, `clearance=0.003`, `approach_offset=0.045`, `orientation_source=post-replay-ee`; contact/score disabled | pass only if bridge replay, z_m006 staging replay, and follow-up near all have action points and readback reaches `0.02 rad`; otherwise stop candidate. |
| `R2_layout_x_p012` | `[-0.28, 0.0, 0.73]` | same fixed contract | tests whether current blocker is mainly robot X reach; same pass/stop rule. |
| `R3_layout_x_p012_y_p008` | `[-0.28, 0.08, 0.73]` | same fixed contract | conservative workspace re-center; same pass/stop rule. |
| `R4_approach_line_staging_under_best_layout` | best clean reset + bridge layout from `R1-R3` | conditional only if at least one layout has clean reset + bridge but near still fails | change staging generation to handle open-face approach-line staging, e.g. `contact + normal * 0.085m`, then follow-up to `0.045m near`; pass only if staging and near both replay to tolerance. |

Gate 1R classifications:

```text
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
BLOCKED_APPROACH_SEED_LAYOUT_CANDIDATE_RESET_OR_BRIDGE_FAILURE
BLOCKED_APPROACH_SEED_LAYOUT_TO_NEAR_FAMILY_IK_FAIL_NO_ACTION_POINTS
BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS
```

If Gate 1R passes, it only unlocks Gate 2 contact planner/readback. It does not
claim close-hold, stable grasp, micro-pull, door opened, `Expert Oracle Score`,
policy score, or official score.

2026-07-06 Gate 1R live result:

```text
evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_gate1r_layout_live_20260706/summary_compact.json
classification=BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS
status=FAIL_GATE1R_PRE_REGISTERED_CANDIDATE_SET_DIAGNOSTIC_ONLY
```

R1/R2/R3 all kept the same bridge, `post_bridge_local_z_m006_q_bridge`
staging, mesh-open-face `approach_near_target_world`, `approach_offset=0.045`,
and `orientation_source=post-replay-ee`; only robot base XY changed. All three
reached the bridge and all three planned the `z_m006` staging, but all three
failed the follow-up near replan with `MotionGenStatus.IK_FAIL` and
`available_action_points=0`.

Because R1-R3 had clean bridge/staging evidence but near still failed, the
pre-registered conditional R4 was triggered. Review selected R2 as the best
layout because it had the lowest bridge readback error and the largest
successful `z_m006` staging plan among R1-R3. R4 first generated a
candidate-only handle open-face approach-line staging target:

```text
world_target=[0.47978996139738445, 0.3607189912618622, 1.1085915534527668]
definition=contact_target_world + primary_normal * 0.085m
source=R4_approach_line_staging_R2_preflight/summary.json
```

R4 live then used that generated target as an explicit post-replay staging
waypoint and kept the final follow-up target at the existing `0.045m near`.
Bridge replay again reached joint tolerance, but R4 staging itself returned
`MotionGenStatus.IK_FAIL` with `available_action_points=0`; the near follow-up
was skipped by `no_post_replay_execution`.

Gate 1R therefore reached its registered stop point. The allowed conclusion is
narrow:

```text
Within the pre-registered Gate 1R candidate set, R1-R3 robot layout variants
plus conditional R4 approach-line staging did not produce
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT.
Gate 1 remains blocked; do not start Gate 2 contact, close-hold, micro-pull,
or Expert Oracle Score.
```

Do not broaden this to "DryingBox cannot be opened", "all layouts/staging are
impossible", policy failure, or official score failure.

Recommended next stage:

```text
Gate 1S: Strategy Redesign / No-Go Review
```

Gate 1S must not be another local offset sweep. It should decide whether the
contract changes at task layout, robot/object-frame route generation,
controller/oracle generation, robot choice, or whether this exact
EBench+Franka+DryingBox contract receives a bounded no-go.

## Task 4: Blocked Until A New Gate 1 Route Passes Contact-Ready Near

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_contact_after_approach_seed_live_20260705/`

Gate 1C did not pass for the selected staging-parent route. Do not execute this
task against `post_bridge_local_z_m006_q_bridge`. This section remains the next
contract only if a redesigned route or a pre-registered sibling staging family
later produces:

```text
PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT
```

- [ ] **Step 1: Run one contact target from the selected Gate 1 state**

The probe must keep the winning Gate 1 staging/orientation and change only:

```text
--planner-trajectory-post-replay-mesh-open-face-target-world-key contact_target_world
```

Success classification:

```text
PASS_CONTACT_PLANNER_READBACK_READY_FOR_CLOSE_HOLD
```

Required facts:

```text
selected_plan_success=true
available_action_points>0
post_replay execution reached_joint_target=true
```

Failure classification:

```text
BLOCKED_CONTACT_PLANNER_READBACK
```

Stop if contact fails. Do not run close-hold, retention, micro-pull, or score.

## Task 5: If Gate 2 Passes, Run Close-Hold / Retention

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_retention_after_approach_seed_live_20260705/`

- [ ] **Step 1: Enable close-hold and retention telemetry**

Use the winning Gate 2 route and include:

```text
LABUTOPIA_ORACLE_DEBUG_OBS=1
LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1
--planner-trajectory-post-replay-close-hold-steps 15
--post-close-min-bilateral-overlap-records 15
--require-physx-contact-retention
```

Success classification:

```text
PASS_CLOSE_HOLD_RETENTION_READY_FOR_MICRO_PULL
```

Required facts:

```text
post_replay_close_hold.executed_steps>0
retention_pass=true
tail_bilateral_overlap_records>0
tail_required_roles_near_records>0
tail_physx_required_roles_contact_records>0
```

Failure classification:

```text
BLOCKED_CLOSE_HOLD_RETENTION
```

Stop if retention fails. Do not run micro-pull or score.

## Task 6: If Gate 3 Passes, Run Micro-Pull / Door Readback

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_micro_pull_after_retention_live_20260705/`

- [ ] **Step 1: Run one bounded micro-pull**

Use the winning retained grasp and keep the pull bounded:

```text
micro_pull_diagnostic_only=true
pull step count <= 20
door joint / angle readback required before and after pull
```

Success classification:

```text
PASS_MICRO_PULL_DOOR_READBACK_READY_FOR_EXPERT_ORACLE_SCORE
```

Required facts:

```text
door joint / angle changes in expected open direction
retention does not drop before the readback window
```

Failure classification:

```text
BLOCKED_MICRO_PULL_DOOR_READBACK
```

Stop if micro-pull fails. Do not run Expert Oracle Score.

## Task 7: If Gate 4 Passes, Run Expert Oracle Score

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_score_live_20260705/`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [ ] **Step 1: Replay the winning expert route under EBench metric**

Required manifest fields:

```json
{
  "classification": "PASS_EXPERT_ORACLE_SCORE_RECORDED",
  "expert_route_source": "Gate 1-4 winning route",
  "metric_source": "EBench level1_open_door evaluator",
  "score_claim_allowed": true,
  "door_opened": true,
  "retention_pass": true
}
```

Do not create this manifest unless Gates 1-4 have passed with live evidence.

## Documentation Updates After Each Gate

After every live gate, update:

```text
docs/labutopia_lab_poc/evidence_manifests/README.md
docs/labutopia_lab_poc/aan_consumer_handoff.md
docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Required PM sentence shape:

```text
现在卡在 [first failed gate]。已经证明 [positive evidence]。还不能承诺 [next-stage claims]。下一步只做 [single next gate]，不继续扫 [old route].
```

## Verification Before Reporting

Run from LabUtopia:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
git diff --check -- docs/superpowers/plans/2026-07-05-eos2-approach-seed-robot-staging-redesign.md docs/labutopia_lab_poc/evidence_manifests/README.md docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md
rg -n "PASS_APPROACH_SEED|BLOCKED_APPROACH_SEED|Gate 1|Expert Oracle Score|stop_contact_tuning" docs/superpowers/plans/2026-07-05-eos2-approach-seed-robot-staging-redesign.md docs/labutopia_lab_poc/evidence_manifests/README.md docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Expected:

```text
git diff --check exits 0
rg returns the new plan and PM boundary entries
```

# DryingBox Object-Frame cuRobo Oracle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current single-target DryingBox open-door oracle diagnostics with an EBench-style object-frame waypoint contract and per-waypoint cuRobo planning path that can produce a stable `grasp_hold` window before contact/collider attribution resumes.

**Architecture:** Keep the current EOS no-score/no-pull claim boundary. First add a pure DryingBox waypoint contract and unit tests, then add a planning smoke path that converts object-frame waypoints to world/robot poses and calls cuRobo per waypoint. Do not claim full `collision-aware planning` until the implementation explicitly refreshes and logs cuRobo world obstacles.

**Tech Stack:** Python, pytest, Isaac Sim 4.1, GenManip `custom_motion` / `BaseEmbodiment.plan_pose`, cuRobo `MotionGen.plan_single`, LabUtopia evidence manifests.

---

## Evidence Inputs

Current blocker evidence:

```text
target_frame_audit=docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_target_frame_reachability_audit_20260704_132909/target_frame_reachability_audit.json
status=READ_ONLY_AUDIT_COMPLETE_DIAGNOSTIC_ONLY
classification=UPSTREAM_TARGET_REACHABILITY_AND_CONTROLLER_STABILITY_OPEN
decision=move_to_ebench_style_object_frame_waypoints_plus_curobo_planning

formal_reset_contract=docs/labutopia_lab_poc/evidence_manifests/eos2_open_door_formal_reset_contract_checkpoint_20260705.json
status=FORMAL_CONFIG_UPDATED_WITH_DIAGNOSTIC_LIVE_BACKING
accepted_robot_position=[-0.4, 0.0, 0.73]

bounded_execution=docs/labutopia_lab_poc/evidence_manifests/eos2_bounded_execution_base_z_073_20260704_233033/lead_in_base_z_073_compact.json
status=FAIL_BOUNDED_JOINT_LEAD_IN_DIAGNOSTIC_ONLY
parse_only_ik_success=true
lead_in_executed_steps=53
reached_joint_target=false
terminal_reason=arm_state_jump_too_large
decision=do_not_continue_absolute_ik_target_replay; implement EBench microwave style object-frame waypoints plus per-waypoint cuRobo execution/readback
```

Reference pattern:

```text
/cpfs/user/zhuzihou/dev/embodied-eval-os/configs/benchmark_packs/ebench/task_registry.yaml
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/mobile_manip/test/microwave.yml
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/mobile_manip/test_mini/microwave.yml
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/mobile_manip/val_unseen/microwave.yml
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/extensions/skills/default/custom_motion/custom_motion.py
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/robot/base.py
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/utils/planner/curobo/base.py
```

The active EOS benchmark-pack row points `mobile_manip/microwave` at
`test_mini/microwave.yml`; GenManip's `test`, `test_mini`, `val_train`, and
`val_unseen` microwave configs share the same manual `custom_motion`
object-frame expert template, with different split sizes / task names.

EBench microwave reference mechanics, verified from code:

```text
microwave.yml lines 26-136:
  the open-door phase is a custom_motion block with right-arm object_frame
  waypoints relative to rel_object_uid=microwave, plus pending gripper-close
  holds and later pull poses.

custom_motion.py lines 150-167:
  object_frame targets are converted from the relative object frame into world
  pose through pose_frame_to_world using scene.object_list[rel_object_uid].

custom_motion.py lines 335-383 and curobo/base.py lines 502-568:
  each world-pose target is sent through embodiment.plan_pose, which transforms
  it into the robot frame and calls CuroboPlanner.plan; CuroboPlanner.plan
  calls MotionGen.plan_single and returns interpolated joint positions only
  when cuRobo reports success.

microwave.yml lines 302-328 and genmanip/extensions/metrics/default/sr_based_genmanip_relationship.py lines 195-204:
  score comes from metric readback of articulation qpos / object relationships,
  not from the fact that a trajectory file finished replaying.
```

Important non-confusion boundary:

```text
assets/objects/articulation_data.json contains microwave skills.open_door.skill_trajectory
records for articulated microwave assets, but the audited microwave.yml execution
chain does not directly read those skill_trajectory records for the manual
demonstration path. The reference pattern for DryingBox is therefore the
task-level manual custom_motion waypoint contract plus runtime cuRobo planning,
not asset-metadata skill_trajectory replay.
```

Implication for DryingBox: do not port a fixed LabUtopia controller trajectory
as the oracle. Port the intent as object-frame waypoints relative to the native
DryingBox handle/door frame, then let the EBench/GenManip runtime generate the
joint trajectory through `custom_motion` / cuRobo and judge it with EBench metric
readback.

Latest bounded execution implication: the formal `base_z=0.73m` reset/base
contract is accepted and can enter runtime, but bounded joint-position replay
still diverges in physics readback. The next implementation should therefore
avoid treating a single absolute IK target as the oracle; it should execute a
sequence of microwave-style object-frame waypoints, with planner records and
readback for each segment.

Reviewer caveats to preserve:

```text
base_frame_not_primary is scoped to the audited path only; object-frame convention still needs tests.
per-waypoint cuRobo planning is allowed terminology now.
full collision-aware planning requires explicit cuRobo world obstacle refresh/logging evidence.
```

## File Map

GenManip implementation worktree:

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
```

Likely files:

```text
standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
genmanip/core/evaluator/labutopia_oracle_debug_state.py
tests/labutopia_poc/test_online_open_door_oracle_probe.py
tests/labutopia_poc/test_labutopia_oracle_debug_state.py
```

LabUtopia evidence / docs:

```text
docs/labutopia_lab_poc/evidence_manifests/
docs/labutopia_lab_poc/expert_oracle_score_plan.md
docs/labutopia_lab_poc/aan_consumer_handoff.md
docs/superpowers/plans/2026-07-04-eos2xc7-physx-contact-generation-collider-attribution-repair.md
```

## Claim Boundary

Allowed after this plan starts:

```text
DryingBox object-frame waypoint contract exists.
per-waypoint cuRobo planning smoke was attempted / passed / failed with planner diagnostics.
cuRobo world refresh was or was not logged.
```

Still forbidden until live evidence proves it:

```text
stable grasp
micro-pull readiness
door opened
Expert Oracle Score
policy score
official leaderboard score
full collision-aware planning without obstacle-refresh evidence
```

## Implementation Checkpoints

2026-07-04 Task 1-3 code checkpoint:

```text
GenManip worktree=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
modified=standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
modified=tests/labutopia_poc/test_online_open_door_oracle_probe.py
```

Completed:

```text
Task 1 object-frame waypoint contract implemented.
Task 2 waypoint planning record claim guard implemented.
Task 3 client-side runtime planner interface audit implemented.
--probe-mode object-frame-curobo-planner-smoke now returns BLOCKED_RUNTIME_PLANNER_INTERFACE_NOT_EXPOSED when EvalClient exposes no planner-only method.
```

Verification:

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "dryingbox_object_frame"
# 2 passed, 233 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "waypoint_planning_record or object_frame"
# 6 passed, 233 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "object_frame_curobo_planner_smoke"
# 2 passed, 237 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "build_oracle_waypoints or dryingbox_object_frame or waypoint_planning_record or object_frame_curobo_planner_smoke"
# 26 passed, 213 deselected

/usr/bin/python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
# exit 0
```

Boundary:

```text
This checkpoint proves pure contract, claim-guard plumbing, and the current client-side planner-interface blocker.
Runtime cuRobo planning has not executed because the current EvalClient path exposes reset/step APIs but no planner-only endpoint.
cuRobo world obstacle refresh is not attempted yet.
No stable grasp, micro-pull readiness, door-open, Expert Oracle Score, policy score, official score, or full collision-aware planning claim is allowed from this checkpoint.
```

## Task 1: Add Pure Waypoint Contract Tests

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`

- [x] Add a failing test named `test_dryingbox_object_frame_waypoints_are_relative_to_handle_frame`.

Expected assertions:

```python
waypoints = build_dryingbox_object_frame_waypoints(
    handle_frame_world={
        "position": [0.48, 0.25, 1.108],
        "orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
    },
    robot_base_world_xyz=[-0.4, 0.0, 0.71],
    open_width_m=0.024,
    close_width_m=0.010,
)
labels = [item.label for item in waypoints]
assert labels[:4] == ["approach_pre", "approach_near", "contact", "grasp_hold"]
assert waypoints[0].frame_type == "object_frame"
assert waypoints[0].rel_object_uid == "obj_DryingBox_01_handle"
assert waypoints[0].target_world is not None
assert waypoints[0].target_robot_frame is not None
```

- [x] Add a failing test named `test_dryingbox_object_frame_waypoints_preserve_frame_residuals`.

Expected assertions:

```python
for item in waypoints:
    if item.target_world is None:
        continue
    residual = np.asarray(item.target_world) - np.asarray([-0.4, 0.0, 0.71]) - np.asarray(item.target_robot_frame)
    assert np.linalg.norm(residual) < 1e-9
```

- [x] Implement `DryingBoxObjectFrameWaypoint` as a dataclass without changing the existing `OracleWaypoint` contract:

```python
@dataclass(frozen=True)
class DryingBoxObjectFrameWaypoint:
    label: str
    frame_type: str
    rel_object_uid: str | None
    translation_object_frame: list[float] | None
    orientation_object_frame_wxyz: list[float] | None
    target_world: list[float] | None
    target_robot_frame: list[float] | None
    gripper_width: float
    max_steps: int
    threshold_m: float
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [x] Implement `build_dryingbox_object_frame_waypoints(...)` as a pure helper. Initial offsets must be explicit and conservative:

```text
approach_pre translation_object_frame=[-0.08, 0.0, 0.0], gripper_width=open_width_m
approach_near translation_object_frame=[-0.03, 0.0, 0.0], gripper_width=open_width_m
contact translation_object_frame=[-0.005, 0.0, 0.0], gripper_width=open_width_m
grasp_hold targetless, gripper_width=close_width_m
```

- [x] Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "dryingbox_object_frame"
```

Expected: all new tests pass.

## Task 2: Add cuRobo Planning Smoke Interface

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`

- [x] Add a pure planner result schema helper:

```python
def build_waypoint_planning_record(
    *,
    waypoint_label: str,
    planner_name: str,
    world_refresh_status: str,
    plan_success: bool,
    trajectory_point_count: int,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    ...
```

Required semantics:

```text
world_refresh_status in {"not_attempted", "attempted", "success", "failed", "unknown"}
plan_success=false requires failure_reason
trajectory_point_count > 0 only when plan_success=true
planner_world_refresh_observed=true only when world_refresh_status="success"
collision_aware_claim_allowed remains false at this unit checkpoint; full
collision-aware planning requires live evidence that obstacles were populated
and collision checking was active, not just a successful planner.update() return.
```

- [x] Add tests:

```python
def test_waypoint_planning_record_blocks_collision_aware_without_world_refresh():
    record = build_waypoint_planning_record(
        waypoint_label="approach_pre",
        planner_name="curobo",
        world_refresh_status="not_attempted",
        plan_success=True,
        trajectory_point_count=12,
    )
    assert record["per_waypoint_curobo_planning"] is True
    assert record["collision_aware_claim_allowed"] is False
```

```python
def test_waypoint_planning_record_requires_failure_reason():
    with pytest.raises(ValueError, match="failure_reason"):
        build_waypoint_planning_record(
            waypoint_label="approach_pre",
            planner_name="curobo",
            world_refresh_status="success",
            plan_success=False,
            trajectory_point_count=0,
        )
```

- [x] Add a probe mode name but keep it disabled until implementation is complete:

```text
--probe-mode object-frame-curobo-planner-smoke
```

The first checkpoint returned a disabled skeleton. The current checkpoint returns a concrete
`BLOCKED_RUNTIME_PLANNER_INTERFACE_NOT_EXPOSED` diagnostic when the runtime planner interface
is not available, while keeping all claim guards false.

- [x] Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "waypoint_planning_record or object_frame"
```

Expected: pass.

## Task 3: Runtime Planner Smoke

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Test: add focused tests if pure seams are added.

- [x] Implement `run_object_frame_curobo_planner_smoke(...)` diagnostic branch.

Current implemented branch:

```text
inspect EvalClient-visible methods
do not reset live runtime
do not execute step / step_chunk
write per-waypoint planning records for approach_pre, approach_near, contact
status=BLOCKED_RUNTIME_PLANNER_INTERFACE_NOT_EXPOSED
next_required_interface=server-side planner smoke hook or custom_motion-backed generation path
```

Full runtime planner execution is still pending behind the next required interface:

Required runtime sequence:

```text
reset worker
read debug.labutopia_open_door
build DryingBox object-frame waypoint contract
for each target waypoint before grasp_hold:
  convert object-frame pose to world pose
  transform world pose to robot pose through the robot embodiment path
  refresh/log cuRobo world obstacles when the robot planner exposes update()
  call per-waypoint planning
  record plan_success, trajectory length, first/last joint target, failure reason
write summary JSON
do not execute pull
do not claim score
```

- [x] The diagnostic summary includes:

```text
probe_mode=object-frame-curobo-planner-smoke
waypoint_contract_schema_version
world_refresh_status_by_waypoint
planning_status_by_waypoint
first_failed_waypoint
all_required_waypoints_planned
collision_aware_claim_allowed
stable_grasp_claim_allowed=false
micro_pull_claim_allowed=false
score_claim_allowed=false
```

- [x] If the live runtime cannot expose the robot embodiment planner from the EvalClient path, return a diagnostic summary:

```text
status=BLOCKED_RUNTIME_PLANNER_INTERFACE_NOT_EXPOSED
next_required_interface=server-side planner smoke hook or custom_motion-backed generation path
```

This is an acceptable result for Task 3 if it is evidenced and documented.

2026-07-04 result: this diagnostic branch is now implemented and covered by
`test_object_frame_curobo_planner_smoke_blocks_when_runtime_planner_interface_missing`.
The test has been hardened to assert all three required waypoint records
(`approach_pre`, `approach_near`, `contact`) in both summary maps and trace JSONL.
Fresh focused verification: `object_frame_curobo_planner_smoke` = 2 passed,
237 deselected. It is not a live planner smoke pass. It chooses Route A unless
a server-side planner hook or custom_motion-backed generation path is added.

## Task 4a: Route A Planner-Only Server Hook

Current Task 3 result selects Route A: the EvalClient path cannot access the
robot embodiment planner. Implement a diagnostic-only server hook before any
new live evidence run.

**Design decision:** do not call `CustomMotionSkill.execute()` for this hook.
It writes recorder entries, sets joint targets, and steps Isaac. The diagnostic
path should reuse the object-frame pose conversion semantics, then call
`embodiment.plan_pose()` directly inside the Ray Isaac worker.

**Files:**
- Modify:
  `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/eval_server.py`
- Modify:
  `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/isaac_worker_pool.py`
- Modify:
  `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/isaac_worker.py`
- Modify:
  `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/env.py`
- Modify:
  `/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src/genmanip_client/eval_client.py`
- Modify:
  `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Test:
  existing `tests/labutopia_poc/test_online_open_door_oracle_probe.py`; add
  focused evaluator route/pool/worker/env tests where import-safe.

**Endpoint contract:**

```text
POST /plan_object_frame_waypoints
body: pickle {
  "worker_id": "0",
  "waypoints": [
    {
      "label": "approach_pre",
      "translation": [x, y, z],
      "orientation": [w, x, y, z],
      "rel_object_uid": "obj_DryingBox_01_handle",
      "arm": "default" | "left" | "right",
      "grasp": false
    }
  ],
  "refresh_world": true | false,
  "planner_ignore_list": [...]
}
return: pickle {
  "worker_id": "0",
  "runtime_reset_attempted": false,
  "runtime_step_attempted": false,
  "world_refresh_status_by_waypoint": {...},
  "planning_status_by_waypoint": {...},
  "planner_records": [...]
}
```

Implementation sequence:

- [x] Add failing route-registration test proving `plan_object_frame_waypoints`
      appears in `EvalServer` route paths.
- [x] Add failing pool-dispatch test with fake worker proving the pool calls
      `worker.plan_object_frame_waypoints.remote(payload)` and does not call
      step/reset/post-episode helpers.
- [x] Add failing worker-forwarding test proving `IsaacWorker.plan_object_frame_waypoints`
      delegates to `env.plan_object_frame_waypoints`.
- [x] Add failing env planner-only test with fake scene/embodiment proving the
      method calls `embodiment.plan_pose`, records three waypoint results, and
      does not call `scene.step`, `robot_view.set_joint_position_targets`, or
      `metric_manager.step`.
- [x] Implement the minimal server/pool/worker/env/client methods to satisfy the
      tests.
- [x] Wire `run_object_frame_curobo_planner_smoke()` to call
      `client.plan_object_frame_waypoints(...)` when that method exists.
- [x] Preserve current blocked diagnostic when the method is absent.
- [x] Keep claim guards false unless every required waypoint plans and world
      obstacle refresh is explicitly successful. Review adjustment: this now
      means `planner_world_refresh_observed`, not full `collision_aware_planning`.
      `collision_aware_planning` remains false until Task 4b or later records
      obstacle inventory / collision-check-active evidence.

2026-07-04 implementation checkpoint:

```text
PASS_ROUTE_A_PLANNER_ONLY_HOOK_UNIT_CONTRACT is reached at unit/contract level.
Implemented endpoint/client path:
EvalServer /plan_object_frame_waypoints
-> IsaacWorkerPool.plan_object_frame_waypoints
-> IsaacWorker.plan_object_frame_waypoints
-> IsaacEvalEnvRay.plan_object_frame_waypoints
-> object_frame_waypoint_planner.plan_object_frame_waypoints_for_scene
-> embodiment.plan_pose()

The helper resolves object_frame waypoints through scene.object_list only,
matching EBench custom_motion semantics. It optionally calls cuRobo planner
world refresh, plans each waypoint, and updates only local sim_js.positions
between waypoints. It does not call env.step(), scene.step(),
set_joint_position_targets(), post_episode_process(), metric_manager.step(),
reset(), or recorder writes.

Post-review hardening:
- Planner smoke no longer consumes completed pending reset futures; it returns
  reset_pending/reset_result_ready and leaves /reset_result ownership intact.
- Probe summaries propagate runtime_reset_attempted/runtime_step_attempted from
  the server response and block PASS if a side effect is reported.
- planner.update success is recorded as planner_world_refresh_observed only;
  collision_aware_planning stays false until live evidence proves collision
  world population and active collision checking.

This is still not a live planner smoke pass. It proves the API seam and
planner-only semantics. The next milestone is Task 4b live evidence in an
Isaac/cuRobo server run.
```

Required verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "object_frame_curobo_planner_smoke or plan_object_frame_waypoints"
/usr/bin/python -m py_compile \
  genmanip/core/evaluator/eval_server.py \
  genmanip/core/evaluator/object_frame_waypoint_planner.py \
  genmanip/core/evaluator/isaac_worker_pool.py \
  genmanip/core/evaluator/isaac_worker.py \
  genmanip/core/evaluator/env.py \
  tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py \
  standalone_tools/labutopia_poc/online_open_door_oracle_probe.py \
  tests/labutopia_poc/test_online_open_door_oracle_probe.py

cd /cpfs/shared/simulation/zhuzihou/dev/genmanip-client
/usr/bin/python -m pytest -q tests/test_eval_client_plan_object_frame_waypoints.py
/usr/bin/python -m py_compile src/genmanip_client/eval_client.py
```

Exit conditions:

```text
PASS_ROUTE_A_PLANNER_ONLY_HOOK_UNIT_CONTRACT
BLOCKED_ENV_IMPORT_OR_ISAAC_RUNTIME_REQUIRED
```

Do not mark this as live planner smoke pass. This task only proves the API seam
and planner-only call contract.

## Task 4b: Live Evidence Run

**Files:**
- Create evidence directory under:
  `docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_curobo_oracle_<timestamp>/`
- Update:
  `docs/labutopia_lab_poc/evidence_manifests/README.md`
  `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
  `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] Start server with short `RAY_TMPDIR`, following the current C7 evidence convention.
- [x] Submit `ebench/labutopia_lab_poc/franka_poc/diagnostics/level1_open_door_solver_vit4_self_collision_off.yml`.
- [x] Run:

```bash
python standalone_tools/labutopia_poc/online_open_door_oracle_probe.py \
  --probe-mode object-frame-curobo-planner-smoke \
  --controller-readback-waypoint-label approach_pre \
  --open-width-m 0.024 \
  --close-width-m 0.010
```

- [x] Save:

```text
server.command.txt
server.env.txt
submit.command.txt
gmp_submit.exitcode
probe.command.txt
probe.exitcode
planner_smoke_summary.json
planner_smoke_trace.jsonl
README.md
```

- [x] Classify result:

```text
PASS_OBJECT_FRAME_CUROBO_PLANNER_SMOKE
FAIL_WAYPOINT_PLANNING
BLOCKED_RUNTIME_PLANNER_INTERFACE_NOT_EXPOSED
FAIL_WORLD_REFRESH
```

- [x] Update docs with exact run id, exit codes, first failed waypoint, collision-awareness claim status, and next action.

2026-07-04 Task 4b live checkpoint:

```text
primary_evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_curobo_oracle_debug_20260704_155243
run_id=labutopia_eos2_object_frame_curobo_planner_smoke_debug_20260704_155243
server_port=18319
submit_exitcode=0
probe_exitcode=0
status=BLOCKED_OBJECT_FRAME_CUROBO_PLANNER_SMOKE_FAILED
reset_before_plan=observed
runtime_planner_interface_exposed=true
runtime_reset_attempted=false
runtime_step_attempted=false
runtime_post_episode_process_attempted=false
world_refresh_status=success for approach_pre / approach_near / contact
trajectory_point_count=0 for approach_pre / approach_near / contact
planner_debug_status=MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION
```

Interpretation: the environment, `CUROBO_SRC`, endpoint route, reset-prep, and
cuRobo world refresh are no longer the blocker. The default DryingBox object-frame
waypoints still do not produce a trajectory. The new planner debug shows that
the collision-aware run fails before reaching the target: `MotionGen` marks the
current start state as `INVALID_START_STATE_WORLD_COLLISION`.

The paired direct diagnostic in
`direct_planner_diagnostics_clean_reset.json` splits the failure into two layers:

```text
clean_refresh_world_false_first: MotionGenStatus.IK_FAIL, world_refresh=skipped
clean_ignore_dryingbox: MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION
clean_ignore_table_dryingbox: MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION
```

This means the current target pose/orientation is not IK-solvable even without a
fresh world obstacle update. Once the world is refreshed, the planner additionally
considers the current start state to be in world collision. Ignoring the obvious
DryingBox/table substrings did not remove that start-state collision, so the next
diagnostic must attribute which obstacle or robot link causes the start collision,
not keep changing the same three waypoint offsets blindly.

Claim boundary remains:

```text
stable_grasp=false
micro_pull_ready=false
door_opened=false
expert_oracle_score=false
policy_score=false
full_collision_aware_planning=false
```

Task 4b follow-up, 2026-07-04 object-frame pose ladder:

```text
primary_evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_pose_ladder_20260704_162947
run_id=labutopia_eos2_object_frame_pose_ladder_20260704_162947
probe_mode=object-frame-curobo-pose-ladder
submit_exitcode=0
probe_exitcode=0
status=BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_NO_IK_SOLVABLE_VARIANT
reset_before_plan=observed
runtime_side_effect_reported=false
executed_variant_count=20
offset_x_m=-0.04 / -0.08 / -0.12 / -0.16 / -0.20
orientation_ladder=identity / yaw_90 / yaw_-90 / yaw_180
world_refresh_status=not_attempted for all variants
planner_debug_status=MotionGenStatus.IK_FAIL for all variants
```

Interpretation: the new ladder deliberately kept `refresh_world=false` so it
could isolate the first question: can Franka/cuRobo reach any candidate
`approach_pre` hand pose before we attribute world collision? The answer from
this first sweep is no. All 20 object-frame variants failed at IK, so the next
blocker is still target pose/orientation/reachability, not score, policy,
material, or definitive collision attribution. `world_refresh_status=not_attempted`
does not mean collision checking is proven disabled or solved; it only means this
diagnostic avoided a fresh world-obstacle refresh until at least one pose is
IK-solvable.

2026-07-05 code checkpoint: the richer pose-basis ladder is now implemented and
unit-tested in the GenManip worktree. The probe can now:

```text
--pose-ladder-offset-y-m <...>
--pose-ladder-offset-z-m <...>
--pose-ladder-include-reset-pose-basis
```

When `--planner-smoke-reset-before-plan` is enabled, the runner extracts reset
debug/readback fields, adds `reset_ee_world_as_object_frame` and
`native_open_world_as_object_frame` to the fixed yaw ladder, and records
`pose_ladder_reset_debug_excerpt` in the summary. This was a historical code
capability checkpoint only; it did not by itself change the 2026-07-04 run
status. It has now been consumed by the richer live ladder and reset-to-handle
bridge evidence below. The bridge start-state collision attribution has since
identified the blocker as table surface mesh versus `panda_hand`; Task 4d.3 has
also measured live support-surface clearance and selected Task 4d.4A
reset/base/joint/bridge clearance repair as the current next action.

Post-review hardening: the probe now preserves `planner_debug` in the normalized
`planner_records` and `planner_smoke_trace.jsonl` records for future runs, not
only inside the embedded `runtime_planner_response`. It also separates
`all_world_refresh_success` from `all_required_waypoints_planned`, so consumers
can see "world refresh passed but waypoint planning failed" without relying on
per-waypoint records.

2026-07-04 richer live evidence:

```text
evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_pose_ladder_richer_20260704_173743
run_id=labutopia_eos2_object_frame_pose_ladder_richer_20260704_173743
submit_exitcode=0
probe_exitcode=0
status=BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_NO_IK_SOLVABLE_VARIANT
variant_count=600
executed_variant_count=600
orientation_basis=fixed_yaw_ladder x400, reset_ee_world x100, native_open_world x100
offset_x_m=-0.04 / -0.08 / -0.12 / -0.16 / -0.20
offset_y_m=-0.02 / -0.01 / 0.0 / 0.01 / 0.02
offset_z_m=-0.02 / 0.0 / 0.02 / 0.04
world_refresh_status=not_attempted for all variants
planner_debug_status=MotionGenStatus.IK_FAIL for all variants
```

Interpretation: this rules out the simple hypothesis that the handle-side
approach only needed small Y/Z clearance or a reset/native-open wrist basis.
The target family near the handle is still not IK-solvable before world refresh.

2026-07-04 reset-position seed follow-up:

```text
evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_pose_ladder_reset_seed_20260704_174832
run_id=labutopia_eos2_object_frame_pose_ladder_reset_seed_20260704_174832
submit_exitcode=0
probe_exitcode=0
status=PASS_OBJECT_FRAME_CUROBO_POSE_LADDER
variant_count=601
executed_variant_count=1
first_plannable_variant_label=approach_pre_reset_ee_pose_as_object_frame
trajectory_point_count=149
runtime_side_effect_reported=false
world_refresh_status=not_attempted
```

Interpretation: the planner-only endpoint, reset/readback extraction, and
object-frame coordinate round-trip are sane enough to plan a reset EE pose seed.
This is a diagnostic sanity PASS, not a handle-approach PASS. It does not prove
stable grasp, micro-pull readiness, door opening, score, or collision-aware
planning.

2026-07-05 code checkpoint: the reset-to-handle bridge / bisection ladder is now
implemented in the GenManip probe as a diagnostic-only code path. It adds:

```text
--pose-ladder-include-reset-to-handle-bridge
--pose-ladder-bridge-fractions 1.0 0.875 0.75 0.625 0.5 0.375 0.25 0.125
```

Bridge mode does not plan the exact reset seed as a success candidate. Instead,
it uses the reset seed as the source pose, then generates intermediate
`approach_pre` object-frame poses from each handle-side target back toward reset.
The candidates are ordered from closest-to-handle toward reset, so the first
planning success is the nearest-handle bridge point observed by that sweep. The
runner records `reset_to_handle_bridge_enabled`, `bridge_candidate_count`, and
`first_bridge_plannable_variant_label`. It also separates the bridge statuses:

```text
PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER
BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP
```

2026-07-05 live bridge ladder evidence:

```text
evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_bridge_ladder_20260704_181425

no_refresh_summary=pose_ladder_summary_compact.json
no_refresh_status=PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER
no_refresh_variant_count=48
no_refresh_executed_variant_count=2
first_bridge_plannable_variant=approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity
first_bridge_plannable_trajectory_point_count=152
world_refresh_status=not_attempted

world_refresh_attempt_1=pose_ladder_world_refresh_summary_compact.json
world_refresh_attempt_1_status=BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_RESET_FAILED
world_refresh_attempt_1_interpretation=Ray OOM during reset, not planner/collision evidence

world_refresh_retry2=pose_ladder_world_refresh_retry2_summary_compact.json
world_refresh_retry2_status=BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP
world_refresh_retry2_variant_count=12
world_refresh_retry2_executed_variant_count=12
world_refresh_retry2_trace_world_refresh_status=success for all tested candidates
world_refresh_retry2_planner_debug_status=MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION for all tested candidates
```

Historical interpretation: the bridge ladder changed the diagnosis. Without
cuRobo world refresh, a mid-way reset-to-handle bridge point can plan, so the
system is no longer blocked at "no reachable intermediate pose exists." With
world refresh enabled and reset succeeding, every tested bridge candidate was
blocked by `INVALID_START_STATE_WORLD_COLLISION`; at that point the next live
step was start-state collision attribution. That attribution has since been
completed in Task 4c and identified table surface mesh versus `panda_hand`.
Task 4d.3 has since measured live no-extra-ignore support-surface clearance and
blocked planner-only table exclusion because the measured `panda_hand` sphere
intersects the support surface. The current next live step is Task 4d.4A
reset/base/joint/bridge clearance repair. Do not proceed to grasp, micro-pull,
door opening, score, or official claims until that repair route has live
no-extra-ignore bridge evidence.

## Task 4c: Bridge Start-State Collision Attribution

Purpose: turn the current cuRobo error from "the start state collides with the
world" into a debuggable engineering fact: which world obstacle, which robot
link/sphere, and which planner ignore-list condition caused the classification.

PM explanation: we already found a bridge pose that the robot can plan when the
planner does not refresh scene obstacles. After refreshing the real scene,
cuRobo refuses to start because it believes the robot is already touching a
world obstacle. Task 4c is the "find the exact thing it thinks we are touching"
step. It is still before grasping, pulling, door opening, or scoring.

2026-07-05 code checkpoint:

```text
GenManip worktree=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
modified=genmanip/utils/planner/curobo/base.py
modified=standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
modified=tests/labutopia_poc/test_online_open_door_oracle_probe.py
manifest=docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_code_checkpoint_20260705.json
status=CODE_READY_NOT_LIVE_EVIDENCE
```

Implemented diagnostics:

```text
CuroboPlanner.last_world_debug records obstacle inventory, obstacle type counts,
planner_ignore_list, and effective_ignore_substring.

CuroboPlanner.last_plan_debug records MotionGenResult status and, only for
INVALID_START_STATE_*COLLISION statuses, adds start_state_collision diagnostics.

start_state_collision contains:
  schema_version
  available
  diagnostic_available
  attribution_available
  diagnostic_only=true
  claim_allowed=false
  scope=planner_start_state_only
  planner_ignore_list
  effective_ignore_substring
  robot_prim_path
  world_obstacle_count
  world_obstacle_names_sample
  world_obstacle_names_sample_truncated
  world_obstacle_names_source
  world_config_obstacle_type_counts
  world[] top obstacle/sphere/link collision candidates
  self_pair_attribution_available=false
  temporary_obstacle_enable_mutation=true
  restore_policy
  restore_status
  diagnostic_errors[] when the best-effort query cannot complete

object-frame-curobo-pose-ladder now accepts:
  --pose-ladder-planner-ignore-list <extra obstacle-name substrings...>

pose ladder summaries now expose bridge start-state collision counts, first
collision evidence, generic start-state collision counts, claim guards, and
not_evidence_for. The summary distinguishes diagnostic availability from
attribution availability: a cuRobo start-state collision status can be observed
without yet identifying a specific obstacle/link attribution.

Post-review hardening:

```text
available/attribution_available=true only when a world/self attribution entry exists.
diagnostic_available=true means the diagnostic ran, not that attribution succeeded.
fallback diagnostics use the full stored obstacle list, not only the 25-name sample.
after temporary per-obstacle enable/disable queries, cuRobo world is rebuilt with
the last planner world config via motion_gen.update_world(...).
bridge_* summary fields describe bridge candidates only; non-bridge collisions
are exposed through generic start_state_collision_* fields.
```

2026-07-05 live attribution results:

```text
v1_evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_live_20260705_193305
v1_status=BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP
v1_result=diagnostic_available_true_but_attribution_available_false
v1_root_cause=get_sphere_distance_compute_esdf was the wrong predicate for cuRobo check_start_state classification

v2_evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_live_classify_20260705_194133
v2_compact=pose_ladder_start_state_attribution_compact.json
v2_status=BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP
v2_variant_count=12
v2_executed_variant_count=12
v2_world_refresh_status=success for 12/12
v2_planner_status=MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION for 12/12
v2_attributed_obstacle=/World/labutopia_level1_poc/obj_table/surface/mesh
v2_attributed_robot_link=panda_hand
v2_restore_status=success

ignore_validation_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_ignore_table_surface_20260705_194441
ignore_validation_compact=pose_ladder_ignore_table_surface_compact.json
ignored_obstacle=/World/labutopia_level1_poc/obj_table/surface/mesh
ignore_validation_status=PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER
ignore_validation_first_row=MotionGenStatus.IK_FAIL
ignore_validation_second_row=plan_success true, trajectory_point_count=152
```

Interpretation: Task 4c localized the world-collision blocker. With normal
planner world construction, every bridge candidate fails because cuRobo classifies
`panda_hand` as colliding with the table surface mesh at the start state. When
only that table surface mesh is removed from the diagnostic planner world, the
same world-refresh bridge ladder is no longer blocked by start-state world
collision: the first bridge candidate becomes a normal IK failure, and the second
candidate plans with 152 trajectory points.

This validates the root-cause class as table/hand start-state clearance or table
surface collision modeling in cuRobo world construction. The diagnostic
ignore-list is not the product fix. The next implementation decision should be a
real scene/planner contract change, for example one of:

```text
1. adjust robot reset/base/hand clearance so panda_hand is not embedded in the
   table collision surface at planner start;
2. refine the table surface collision mesh or collision filtering for the planner
   world while preserving task physics;
3. if justified by benchmark convention, explicitly exclude support-surface
   collision from planner world with a documented waiver and independent PhysX
   scene evidence.
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k "object_frame_curobo or plan_object_frame_waypoints or waypoint_planning_record or dryingbox_object_frame or pose_ladder or planner_failure_debug or start_state_collision"
# 36 passed, 234 deselected

/usr/bin/python -m py_compile genmanip/utils/planner/curobo/base.py standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
# exit 0

git diff --check -- genmanip/utils/planner/curobo/base.py standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
# exit 0
```

Claim boundary for this checkpoint:

```text
This checkpoint now has live Isaac/cuRobo attribution evidence for the bridge
start-state blocker.
It proves the planner-classified collision source for the current bridge runs:
table surface mesh vs panda_hand.
It does not prove whether the physical scene is truly invalid or whether the
cuRobo planner collision model is too conservative.
It does not allow stable_grasp, micro_pull_readiness, door_opened,
Expert Oracle Score, policy score, official score, or full collision-aware
planning claims.
```

## Task 4d: Support-Surface Clearance Contract Repair

Purpose: turn the Task 4c attribution into a formal repair decision. The current
evidence says `panda_hand` is classified as colliding with
`/World/labutopia_level1_poc/obj_table/surface/mesh` at planner start. It does
not yet say whether the hand is physically below the table, whether the table
collision mesh is too thick, or whether cuRobo's robot-sphere/table-mesh model
needs a documented support-surface planner contract.

PM explanation: we know which object blocks the planner: the table surface. But
removing the table from the planner is only a diagnostic shortcut. Before making
that a product rule, we need to measure the actual clearance between the robot
hand, the table surface, and cuRobo's collision spheres. Then we can decide
whether to raise/change the robot reset pose, fix the table collision mesh, or
document a safe planner-only support-surface exclusion.

Required audit evidence:

```text
reset robot base pose and orientation
reset joint positions / gripper positions
reset end-effector world pose
table surface mesh prim path and world AABB
cuRobo obstacle inventory entry for table surface mesh
colliding robot link name, sphere index, sphere center world, sphere radius
signed or conservative clearance estimate against table surface AABB
collision_value from get_sphere_collision
ESDF/distance value as auxiliary evidence only
whether PhysX scene reset is stable and finite
whether support-surface exclusion is planner-only or also changes task physics
claim guards for stable_grasp, micro_pull, door_opened, score
```

Decision rules:

```text
If panda_hand sphere center/radius is physically intersecting or below the table
surface AABB at reset:
  Fix the robot reset/base/joint contract first. Do not hide the table.

If the hand has positive physical clearance but cuRobo table mesh or sphere
inflation still reports start-state collision:
  Fix planner collision representation if a narrower table collision mesh can
  preserve task physics; otherwise introduce a planner-only support-surface
  exclusion with an explicit waiver and clearance evidence.

If excluding table surface is used:
  It must be scoped to planner world construction only, must not remove PhysX
  task collision, must name the exact prim path, and must preserve separate
  evidence that the physical robot is not embedded in the support surface.

If no no-extra-ignore bridge candidate plans after the formal repair:
  Stay in Task 4d and re-run attribution. Do not proceed to bounded execution.
```

Implementation plan:

```text
Task 4d.1 Add clearance audit schema and pure tests.
Task 4d.2 Add runtime planner-only clearance readback to the existing
           plan_object_frame_waypoints response or a dedicated diagnostic mode.
Task 4d.3 Run live no-extra-ignore clearance audit.
Task 4d.4 Choose one repair route:
           A reset/base/joint clearance adjustment;
           B table collision mesh/filter correction;
           C documented planner-only support-surface exclusion.
Task 4d.5 Re-run bridge ladder with refreshed world and no diagnostic shortcut.
Task 4d.6 Only if a bridge candidate plans, move to bounded execution/readback.
```

2026-07-05 Task 4d.1 code checkpoint:

```text
GenManip worktree=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
modified=genmanip/core/evaluator/object_frame_waypoint_planner.py
modified=tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
implemented=build_support_surface_clearance_record
schema_version=1
behavior=computes sphere_bottom_z - table_top_z clearance_margin_m
behavior=blocks planner_only_support_surface_exclusion_allowed when the sphere
         physically intersects the support-surface AABB
behavior=allows planner-only support-surface exclusion only when the ignore
         candidate exactly matches the support-surface prim path and clearance
         is non-negative and the sphere XY footprint overlaps the support-surface
         AABB
claim_guards=stable_grasp/micro_pull/door_opened/expert_oracle_score/policy_score/official_score all false
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k support_surface_clearance_record
# 2 passed, 9 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# 11 passed

/usr/bin/python -m py_compile genmanip/core/evaluator/object_frame_waypoint_planner.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# exit 0
```

2026-07-05 Task 4d.2a sphere geometry checkpoint:

```text
GenManip worktree=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
modified=genmanip/utils/planner/curobo/base.py
added=tests/labutopia_poc/test_curobo_start_state_collision_diagnostics.py
implemented=_sphere_geometry_record_from_query_spheres
runtime_hook=CuroboPlanner._diagnose_world_start_state_collision now attaches
             sphere_geometry_available, sphere_center_world, sphere_radius,
             sphere_bottom_z, and sphere_query_row_index to each colliding
             world obstacle record when query_spheres exposes [x, y, z, r].
behavior=diagnostic-only readback; planner action selection, world refresh,
         collision values, and obstacle enable/restore behavior are unchanged.
purpose=feeds Task 4d live support-surface clearance audit with the missing
        robot sphere geometry needed to compare panda_hand sphere bottom
        against the table surface AABB.
claim_boundary=this is not yet live clearance evidence and does not permit
               support-surface exclusion, stable grasp, micro-pull, door-open,
               expert oracle score, or policy score claims.
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_curobo_start_state_collision_diagnostics.py
# 2 passed

/usr/bin/python -m pytest -q tests/labutopia_poc/test_curobo_start_state_collision_diagnostics.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k "sphere_geometry_record or support_surface_clearance_record"
# 4 passed, 9 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "start_state_collision or pose_ladder"
# 16 passed, 245 deselected

/usr/bin/python -m py_compile genmanip/utils/planner/curobo/base.py tests/labutopia_poc/test_curobo_start_state_collision_diagnostics.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# exit 0
```

Multi-agent reset / clearance review, 2026-07-05:

```text
reviewer=reset/hand/table explorer
status=read_only_complete
finding=Evidence was produced from the GenManip worktree, not the shared main
        GenManip checkout.
finding=Task YAML sets robot position [-0.4, 0.0, 0.71], no orientation, and no
        default_joint_positions.
finding=The worktree Franka builder applies that base pose through
        resolve_optional_robot_pose() and robot.set_world_pose(...); missing
        orientation defaults to [1, 0, 0, 0].
finding=Joint reset uses Isaac Franka default state because the task YAML does
        not set default_joint_positions.
finding=Planner start state comes from embodiment.robot.get_joints_state() inside
        plan_object_frame_waypoints_for_scene().
finding=obs["state.base"] is not evidence for robot world base in the single-arm
        path because it is reported as [0, 0, 0].
finding=Current live evidence proves cuRobo start-state attribution only:
        table surface mesh vs panda_hand sphere_index=0. It does not prove
        whether USD/PhysX hand geometry is physically intersecting the table.
recommendation=Next runtime audit must record robot.get_world_pose(), reset
               joint/gripper state, hand/finger USD AABBs, table surface AABB,
               cuRobo panda_hand sphere centers/radii, table obstacle geometry,
               and signed gap scalars.
```

Multi-agent support-surface review, 2026-07-05:

```text
reviewer=planner/support-surface explorer
status=read_only_complete
finding=No direct EBench microwave evidence was found for planner-level table or
        support-surface exclusion.
finding=Microwave uses object-frame custom_motion and cuRobo planning, but its
        config has layout_config.ignored_objects=[] and no planner ignore-list
        evidence.
finding=Existing generic planner ignore support is code-level CuroboPlanner.update
        ignore_substring=[robot_name, "Camera"] + ignore_list; PickAndPlace has
        separate update_planner / plan_ignored_list behavior, but that is not a
        demonstrated microwave precedent.
finding=object_config.without_colliders and table_without_collider affect physics
        / loading paths and are not equivalent to planner-only exclusion.
recommendation=Keep the table-surface ignore as diagnostic until clearance audit
               proves the robot is not physically embedded in the table.
recommendation=If support-surface exclusion is chosen, make it planner-only,
               exact-prim scoped, PhysX-preserving, and backed by clearance
               evidence plus recorded effective_ignore_list.
```

2026-07-05 Task 4d.2b runtime support-surface clearance hook checkpoint:

```text
GenManip worktree=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
modified=genmanip/core/evaluator/object_frame_waypoint_planner.py
modified=standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
modified=tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
modified=tests/labutopia_poc/test_online_open_door_oracle_probe.py

implemented=build_support_surface_clearance_records_from_planner_debug
implemented=plan_object_frame_waypoints_for_scene support_surface_uid runtime AABB lookup
implemented=online probe --support-surface-* payload passthrough
implemented=trace/variant preservation of support_surface_clearance_records
implemented=support_surface_aabb_source and support_surface_reference_prim_path
            distinguish whether the AABB came from payload or scene_uid:table,
            and distinguish the AABB reference entity from the concrete cuRobo
            obstacle path.
implemented=planner_only_support_surface_exclusion_allowed requires exact
            planner_ignore_candidate match, non-negative Z clearance, and XY
            footprint overlap with the support-surface AABB.

runtime_use=pass support_surface_uid=table and
            support_surface_planner_ignore_candidate=<exact table obstacle prim>
            into object-frame-curobo-pose-ladder. The server-side planner hook
            reads the table object's runtime get_world_bounding_box(), matches
            planner_debug.start_state_collision.world obstacle_name, and records
            panda sphere bottom z versus table top z.

claim_boundary=this is still diagnostic-only code evidence. It allows the next
               live run to decide whether a planner-only, exact support-surface
               ignore retry is physically safe. It does not itself prove live
               clearance, stable grasp, micro-pull, door-open, Expert Oracle
               Score, policy score, official score, or full collision-aware
               planning.
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k "support_surface_clearance_records_are_built or attaches_support_surface_clearance or reads_support_surface_aabb_from_scene_uid"
# 3 passed, 11 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k "reads_support_surface_aabb_from_scene_uid or candidate_can_match_child_obstacle"
# 2 passed, 14 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# 16 passed

	/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "support_surface_diagnostic_fields or object_frame_curobo_pose_ladder_searches_reset_to_handle_bridge"
	# 2 passed, 260 deselected
	```

2026-07-05 Task 4d.2c stage-prim AABB fallback checkpoint:

```text
GenManip worktree=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
modified=genmanip/core/evaluator/object_frame_waypoint_planner.py
modified=tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py

root_cause=Task 4d.3 first live clearance audit passed support_surface_uid=table
           and support_surface_planner_ignore_candidate=<table surface mesh>, but
           the runtime scene did not expose a uid=table object with
           get_world_bounding_box(). Therefore no table AABB was available and no
           support_surface_clearance_records could be attached.

implemented=_world_bbox_from_stage_prim_path()
behavior=if payload AABB is absent and scene uid bbox is unavailable, use the
         exact support_surface_prim_path against the current USD stage and
         pxr.UsdGeom.BBoxCache to compute world AABB.
source_label=stage_prim_path:<support_surface_prim_path>
claim_boundary=this only fills the missing AABB diagnostic field. It does not
               change planner world construction, PhysX collision, robot reset,
               or task semantics.
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k stage_prim_path
# 1 passed, 17 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k support_surface
# 9 passed, 9 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# 18 passed

/usr/bin/python -m py_compile genmanip/core/evaluator/object_frame_waypoint_planner.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# exit 0
```

2026-07-05 Task 4d.3 live no-extra-ignore clearance audit:

```text
evidence_dir=docs/labutopia_lab_poc/evidence_manifests/eos2_support_surface_clearance_audit_stage_bbox_envfix_20260704_213347
compact=pose_ladder_support_surface_clearance_compact.json
submit_exit=0
probe_exit=0
status=BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP
reset_observed=true
planner_ignore_list=["Camera"]
bridge_candidate_count=12
bridge_start_state_collision_variant_count=12
support_surface_clearance_record_count=12
support_surface_aabb_source=stage_prim_path:/World/labutopia_level1_poc/obj_table/surface/mesh
support_surface_exclusion_allowed_count=0
support_surface_exclusion_blocker_counts.sphere_vertically_intersects_support_surface=12
first_record.table_top_z=0.7727606407108345
first_record.robot_link=panda_hand
first_record.sphere_bottom_z=0.050999999046325684
first_record.clearance_margin_m=-0.7217606416645088

decision=Route A is selected. The current evidence blocks planner-only
         support-surface exclusion because the measured cuRobo panda_hand sphere
         is vertically intersecting the table support surface. Fix reset/base/
         joint/bridge clearance first, then re-run no-extra-ignore bridge ladder.

not_evidence_for=stable_grasp,micro_pull_readiness,door_opened,expert_oracle_score,policy_score,official_score
```

Environment note:

```text
The first stage-bbox retry in
eos2_support_surface_clearance_audit_stage_bbox_retry_20260704_212941 failed
before planner reset because the server shell did not include the conda bin path
or Isaac CUDA 11 runtime in LD_LIBRARY_PATH. The envfix run restored PATH and
LD_LIBRARY_PATH to match the previous successful live environment and reached
the planner stage.
```

## Task 5: Resume EOS Path Decision

After Task 4, choose exactly one route:

```text
Route A: planner smoke cannot access runtime planner -> implement server-side planner hook or custom_motion-backed generation path.
Route B: planner smoke plans approach/grasp but does not execute -> add bounded execution/readback for planned trajectory.
Route C: planner smoke executes and creates stable grasp_hold -> resume C7 contact/collider attribution rows.
Route D: planner smoke reaches metric success -> enter Franka Expert Oracle Score evidence, still not policy score.
```

Current route after Task 4d.3 live clearance audit: stay before Route B and
select Task 4d.4 Route A. We now have the planner-only hook, live cuRobo
diagnostics, a 600-variant handle-offset sweep showing the original handle-side
approach family is still IK_FAIL, a reset EE pose seed that plans with 149
trajectory points, a no-refresh reset-to-handle bridge point that plans with 152
trajectory points, live attribution proving the world-refresh bridge blocker is
table surface mesh vs `panda_hand`, and live support-surface clearance records
showing 12/12 candidate records are physically blocked by
`sphere_vertically_intersects_support_surface`.

2026-07-05 Task 4d.4D update: reset/base/joint branch review is no longer
unresolved. The `reset_seed_retract_001` diagnostic kept base z=`0.71m` and
applied a 9D Franka `default_joint_positions` seed; live readback showed the 7D
arm seed entered reset, but 12/12 bridge candidates still hit cuRobo
`INVALID_START_STATE_WORLD_COLLISION` against table surface vs `panda_hand`.
The `base_z_lift_002_only` diagnostic changed only robot base z from `0.71m` to
`0.73m`, without solver velocity override or self-collision disable; live
evidence cleared start-state collision to `0` and the second bridge candidate
planned with refreshed world and `trajectory_point_count=152`.

2026-07-05 Task 4d.4E update: `position: [-0.4, 0.0, 0.73]` has been promoted
into the formal Franka POC `level1_open_door.yml` reset/base contract without
adding `default_joint_positions`, solver override, self-collision disable, or
oracle debug obs. Ordinary open-door diagnostic configs are aligned to `0.73m`;
`reset_seed_retract_001` remains at `0.71m` as the negative-control branch.

Current route after Task 4d.4E: run bounded execution/readback under the accepted
POC-specific reset/base contract.
Do not move to grasp, pull, Expert Oracle Score, policy score, or official score
until bounded execution proves stable grasp/micro-pull/door-angle readback under
the accepted reset contract.

2026-07-05 Task 4d.4F update: bounded execution/readback under the accepted
`base_z=0.73m` contract ran as
`docs/labutopia_lab_poc/evidence_manifests/eos2_bounded_execution_base_z_073_20260704_233033/lead_in_base_z_073_compact.json`.
It proved reset/base/IK/diagnostic execution can enter runtime, but it failed as
`FAIL_BOUNDED_JOINT_LEAD_IN_DIAGNOSTIC_ONLY`: `parse_only_ik_success=true`,
53 bounded lead-in steps executed, step 51/52 readback diverged, and terminal
reason was `arm_state_jump_too_large`. This means the next route should not keep
hand-interpolating one absolute IK target. It should execute the actual
object-frame cuRobo trajectory points produced by the planner-only endpoint.

2026-07-05 Task 5A planner trajectory export checkpoint:

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_export_code_checkpoint_20260705.json
status=CODE_READY_NOT_LIVE_EVIDENCE
implemented=plan_object_frame_waypoints include_trajectory_points payload flag
implemented=successful planner_records can include raw trajectory_joint_positions
implemented=successful planner_records can include executable trajectory_action_joint_positions
implemented=trajectory_action_joint_names/control_type/replay_policy metadata
implemented=non-finite planner/action trajectory points fail as non_finite_trajectory_point
implemented=online probe --planner-smoke-include-trajectory-points preserves
            raw and action-level trajectory fields in summary and trace records
implemented=genmanip-client forwards include_trajectory_points only when true
default_off=true
runtime_execution_added=false
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# 23 passed

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "object_frame_curobo_planner_smoke or waypoint_planning_record or dryingbox_object_frame"
# 16 passed, 249 deselected

cd /cpfs/shared/simulation/zhuzihou/dev/genmanip-client
PYTHONPATH=src /usr/bin/python -m pytest -q tests/test_eval_client_plan_object_frame_waypoints.py
# 3 passed
```

Task 5A is a schema/input checkpoint for execution. It still does not prove live
execution, stable grasp, micro-pull, door opening, Expert Oracle Score, policy
score, official score, or full collision-aware completion.

Task 5B bounded trajectory execution/readback route:

```text
Use accepted base_z=0.73m reset/base contract.
Call planner-only endpoint with include_trajectory_points=true.
Require approach_pre or selected bridge waypoint planner record to include
trajectory_action_joint_positions. Keep trajectory_joint_positions as raw planner
evidence only.
Replay trajectory_action_joint_positions through joint_position actions with
readback guards, preferably in a fresh run_id suffix.
Record per-trajectory-point command target, post-step readback, terminal reason,
post_world_step_delta_abs_max, final target tolerance, and claim guards.
If readback diverges, classify as trajectory_execution_readback blocker, not
contact/collider or score.
Only if approach/contact/grasp_hold are stable should the plan resume C7 contact
or micro-pull diagnostics.
```

2026-07-05 Task 5B planner trajectory execution/readback code checkpoint:

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_execution_readback_code_checkpoint_20260705.json
status=CODE_READY_NOT_LIVE_EVIDENCE
implemented=online_open_door_oracle_probe --probe-mode planner-trajectory-execution-readback
implemented=planner call forces include_trajectory_points=true
implemented=consumer uses trajectory_action_joint_positions only
implemented=trajectory_joint_positions remains raw planner audit evidence only
implemented=fresh replay run_id suffix planner_trajectory_replay when fresh_job_starter is available
implemented=per-point joint_position action readback samples
implemented=target_delta/post_step_delta/final_joint_tolerance blockers
implemented=machine-readable no-claim guards for stable_grasp/micro_pull/score
implemented=pre-plan reset before plan_object_frame_waypoints so worker 0 exists
implemented=pre-plan reset response compact summary; video/camera obs arrays omitted
review_fixed=action-only trajectory payload is accepted without raw trajectory fields
review_fixed=normal reset path no longer replays in the original planner run
runtime_execution_code_path_added=true
live_runtime_execution_run=false
followup_live_evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_execution_readback_live_20260705_005444/planner_trajectory_execution_summary.compact.json
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "planner_trajectory_execution_readback_replays_action_level_points or planner_trajectory_execution_readback_consumes_action_only_payload_in_fresh_run"
# 2 passed, 265 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "planner_trajectory_execution_readback"
# 3 passed, 265 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "planner_trajectory_execution_readback or object_frame_curobo_planner_smoke_preserves_requested_trajectory_points or bounded_joint_lead_in"
# 6 passed, 262 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "object_frame_curobo_planner_smoke or waypoint_planning_record or dryingbox_object_frame"
# 16 passed, 251 deselected

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py
# 268 passed

/usr/bin/python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
# exit 0
```

2026-07-05 Task 5B live rerun after lifecycle fix:

```text
evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_execution_readback_live_20260705_005444/planner_trajectory_execution_summary.compact.json
run_id=labutopia_eos2_planner_trajectory_execution_readback_20260705_005444
status=FAIL_PLANNER_TRAJECTORY_EXECUTION_PLANNER_FAILED
diagnostic_only=true
old_failure_regression=preplan_reset_attempted=true, preplan_reset_worker_obs_available=true
server_routes=/reset 200, /plan_object_frame_waypoints 200
new_failure_layer=cuRobo IK / object-frame waypoint planning
approach_pre=MotionGenStatus.IK_FAIL, trajectory_point_count=0
approach_near=MotionGenStatus.IK_FAIL, trajectory_point_count=0
contact=MotionGenStatus.IK_FAIL, trajectory_point_count=0
available_action_points=0
executed_steps=0
```

Interpretation: the old `worker 0 does not exist` blocker was a lifecycle bug in
the probe and is now resolved by resetting before planner call. The current
blocker is not evidence of replay/controller instability because no replayable
trajectory exists yet. The planner reached cuRobo with world refresh success,
but the three DryingBox object-frame targets are still not IK-solvable for the
current Franka reset, handle target, and wrist orientation contract.

Next required runtime work after 5B was to make the successful reset-to-handle
bridge candidate consumable by the formal config without relying on debug-only
reset observations.

2026-07-05 Task 5C formal-safe explicit bridge waypoint contract:

```text
code_checkpoint=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_explicit_waypoint_code_checkpoint_20260705.json
old_failure_evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_bridge_execution_readback_live_20260705_5c_0100/planner_trajectory_bridge_execution_summary.json
new_pass_evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_explicit_bridge_execution_readback_live_20260705_5c_0120/planner_trajectory_explicit_bridge_execution_summary.compact.json
old_failure_status=FAIL_PLANNER_TRAJECTORY_EXECUTION_PLANNER_FAILED
old_failure_root_cause=formal reset observation omitted debug.labutopia_open_door,
                       so dynamic reset-to-handle bridge construction appended no
                       bridge waypoint to the planner payload
implemented=--planner-trajectory-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ
implemented=explicit waypoint appends the same object-frame schema consumed by
            plan_object_frame_waypoints
implemented=default approach_pre/approach_near/contact payload unchanged
explicit_waypoint=approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity
explicit_translation_object_frame=[0.0010228951554745458,-0.11657822728157047,0.014903118610382071]
explicit_orientation_object_frame_wxyz=[0.9478491886430741,-0.209547848787944,-0.22171216853953848,-0.09227854018408849]
new_pass_status=PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY
new_pass_selected_plan_success=true
new_pass_trajectory_point_count=152
new_pass_available_action_points=152
new_pass_executed_steps=152
new_pass_reached_joint_target=true
new_pass_final_joint_target_abs_max_rad=7.128715515136719e-05
new_pass_joint_target_tolerance_rad=0.02
new_pass_blockers=[]
```

Verification:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
python -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k 'explicit_object_frame_waypoint_without_reset_debug or explicit_waypoint_without_debug_state' -q
# RED before implementation: 2 failed for expected missing explicit-waypoint behavior
# GREEN after implementation: 2 passed, 269 deselected

python -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k 'rejects_nonfinite_explicit_object_frame_translation' -q
# RED before review fix: 1 failed for expected missing finite translation validation
# GREEN after review fix: 1 passed, 271 deselected

python -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -k 'planner_trajectory_execution_readback' -q
# 5 passed, 267 deselected

python -m pytest tests/labutopia_poc/test_online_open_door_oracle_probe.py -q
# 272 passed
```

PM interpretation: the formal EBench config can now consume a bridge waypoint
without relying on hidden debug fields. This is the same architecture direction
as EBench microwave: object-relative waypoint contract first, planner generates
the joint trajectory at runtime, probe replays action-level trajectory points and
checks readback. This proves the first bridge trajectory can be planned and
executed to the requested joint target under the formal `level1_open_door.yml`
base-z contract.

Boundary: Task 5C is still a diagnostic bridge/replay pass, not a full open-door
oracle score. The selected bridge point is an intermediate reset-to-handle pose;
it has not yet closed the gripper, established stable handle contact, performed
micro-pull, changed door angle, or run EBench metric scoring. Do not report
stable grasp, micro-pull readiness, door opened, Expert Oracle Score, policy
score, official score, or full collision-aware task completion from this pass.

Next required runtime work: convert this single successful bridge into a staged
object-frame expert route: bridge -> handle-side approach/contact -> close/grasp
readback -> micro-pull/door-angle readback. Each stage needs its own planner
record, action-level trajectory replay, readback guard, and claim boundary before
entering Expert Oracle Score.

2026-07-05 Task 5D post-replay replan/readback checkpoint:

```text
code_checkpoint=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_code_checkpoint_20260705.json
env_negative_control_1=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0130/
env_negative_control_2=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0145/
live_evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0200/summary_compact.json
run_id=labutopia_eos2_planner_trajectory_post_replay_replan_20260705_5d_0200
status=FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY
implemented=--planner-trajectory-post-replay-replan
implemented=--planner-trajectory-post-replay-waypoint-label
implemented=--planner-trajectory-post-replay-execute
implemented=after selected bridge replay, call plan_object_frame_waypoints again
            on the same worker/run state without reset
environment_fix=server launch must include conda env bin on PATH and Isaac
                omni.cuda.libs libcudart.so.11.0 on LD_LIBRARY_PATH
preplan_selected_waypoint=approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity
preplan_selected_plan_success=true
preplan_selected_trajectory_point_count=150
bridge_replay_available_action_points=150
bridge_replay_executed_steps=150
bridge_replay_reached_joint_target=true
bridge_replay_final_joint_target_abs_max_rad=7.128715515136719e-05
bridge_replay_joint_target_tolerance_rad=0.02
post_replay_replan_attempted=true
post_replay_waypoint=approach_pre
post_replay_state_source=post_planner_trajectory_replay_worker_state
post_replay_selected_plan_success=false
post_replay_failure=MotionGenStatus.IK_FAIL
post_replay_available_action_points=0
blockers=planner_trajectory_post_replay_planner_failed,
         planner_trajectory_post_replay_action_joint_positions_missing
claim_guards=stable_grasp:false, micro_pull:false, door_opened:false,
             expert_oracle_score:false, policy_score:false, official_score:false
```

PM interpretation: Task 5D answers a narrower but important question: after the
robot reaches the formal bridge point, can the EBench worker keep its current
state and ask cuRobo for the next motion? The answer is now "the plumbing works,
but the next target is wrong." The bridge replay itself succeeded in this fresh
run: cuRobo produced action-level joint points, the EBench consumer executed 150
steps, and readback reached the final joint target within the 0.02 rad tolerance.
Then the probe did call the planner again on the post-replay worker state, so the
server/API/state-continuation path exists. That follow-up target was still the
old `approach_pre`, and cuRobo returned `MotionGenStatus.IK_FAIL`; no follow-up
action trajectory was produced.

Interpretation: Task 5D is not a regression from Task 5C. It advances the
evidence boundary from "single bridge replay works" to "post-bridge continuation
is reachable as an API path, but the next waypoint needs to be designed for the
new post-bridge robot state." The next technical step is not score. It is to
define a bridge-relative follow-up waypoint family, such as small handle-side
approach/contact poses measured from the post-bridge state, with orientation
and reachability ladders. Only a follow-up waypoint that returns action-level
trajectory points and passes replay readback should be allowed to move toward
close/grasp and micro-pull.

Boundary: Task 5D does not prove stable grasp, micro-pull readiness, door-angle
change, door opened, Expert Oracle Score, policy score, official leaderboard
score, or full collision-aware task completion. It also does not prove material
or visual parity; the server log still contains known USD material-binding
warnings for payload-scoped assets, which remain outside the oracle score claim.

Do not skip directly from planner smoke to score unless `result_info.json`, action log, metric trace, and claim guards exist.

## Verification

Minimum verification before reporting this plan as implemented:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "dryingbox_object_frame or waypoint_planning_record or object_frame"
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py -k "object_frame_curobo or plan_object_frame_waypoints or waypoint_planning_record or dryingbox_object_frame or pose_ladder or planner_failure_debug or start_state_collision"
/usr/bin/python -m py_compile standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_online_open_door_oracle_probe.py

cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
git diff --check -- docs/labutopia_lab_poc docs/superpowers/plans
```

If live runtime is run, also verify no server remains listening on the temporary port and no `/tmp/r7*` Ray temp process is left active for this run.

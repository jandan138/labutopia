# EOS2 Gate 1T-C2a Native Action-Path Runner Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal, test-covered GenManip runner that can consume one pre-registered Gate 1T native `custom_motion` route, plan it through the existing object-frame planner endpoint, execute the generated action stream through EBench/Ray eval stepping, and write a bounded readback summary.

**Architecture:** Keep evaluator core unchanged. Add a standalone LabUtopia POC runner module that is importable for unit tests and executable as a CLI for live runs. The runner reads the Gate 1T route manifest, selects exactly one route, calls `client.reset()`, calls `client.plan_object_frame_waypoints(... include_trajectory_points=True)`, converts `trajectory_action_joint_positions` into `joint_position` action chunks, executes them via `client.step_chunk`, and writes a summary with pass/fail/blocker classifications.

**Tech Stack:** Python 3.10, GenManip standalone tools, `genmanip_client.EvalClient` for live mode, pytest fake clients for unit tests, LabUtopia JSON evidence manifests.

---

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/native_action_path_runner.py` | New library + CLI runner. No Isaac imports at module import time. |
| `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_native_action_path_runner.py` | Unit tests using fake clients. Tests route selection, planner payloads, action chunks, pass/fail classifications, and no score/contact escalation. |
| `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json` | Update from runner missing to code-ready-not-live after tests pass. |
| `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/aan_consumer_handoff.md` | Handoff summary for the new runner. |
| `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/expert_oracle_score_plan.md` | Keep Expert Oracle Score blocked until C2b live evidence exists. |
| `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/README.md` | Evidence index update. |

## Task 1: Write Runner Unit Tests First

**Files:**
- Create: `tests/labutopia_poc/test_native_action_path_runner.py`

- [x] **Step 1: Add fake-client pass test**

Test content:

```python
def test_runner_executes_selected_route_through_planner_and_step_chunk(tmp_path):
    manifest_path = tmp_path / "routes.json"
    manifest_path.write_text(json.dumps({
        "routes": [{
            "route_id": "C1_ROOT_DIRECT_NATIVE_PATTERN",
            "priority": 1,
            "waypoints": [
                {"label": "robot_stage", "type": "robot_frame", "translation": [0.3, 0.0, 0.3], "orientation": [1.0, 0.0, 0.0, 0.0], "grasp": False},
                {"label": "root_near", "type": "object_frame", "rel_object_uid": "obj_DryingBox_01", "translation": [0.0, 0.2, 0.0], "orientation": [1.0, 0.0, 0.0, 0.0], "grasp": False}
            ]
        }]
    }), encoding="utf-8")

    client = FakeClient(planner_records=[
        _planned_record("robot_stage", [[0.1] * 9]),
        _planned_record("root_near", [[0.2] * 9])
    ])

    summary = runner.run_native_action_path_route(
        client,
        manifest_path=manifest_path,
        route_id="C1_ROOT_DIRECT_NATIVE_PATTERN",
        worker_id="0",
        output_path=tmp_path / "summary.json",
        trace_path=tmp_path / "trace.jsonl",
    )

    assert client.reset_calls == 1
    assert client.plan_calls[0]["include_trajectory_points"] is True
    assert client.plan_calls[0]["refresh_world"] is True
    assert [step["0"]["control_type"] for step in client.step_chunk_calls[0]] == ["joint_position", "joint_position"]
    assert summary["classification"] == "PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT"
    assert summary["gate2_contact_allowed"] is True
    assert summary["expert_oracle_score_allowed"] is False
```

- [x] **Step 2: Add planner failure stop test**

Test content:

```python
def test_runner_blocks_when_selected_waypoint_has_no_action_points(tmp_path):
    manifest_path = _write_single_route_manifest(tmp_path)
    client = FakeClient(planner_records=[
        _planned_record("robot_stage", [[0.1] * 9]),
        {"label": "root_near", "plan_success": False, "trajectory_point_count": 0, "failure_reason": "IK_FAIL"}
    ])

    summary = runner.run_native_action_path_route(
        client,
        manifest_path=manifest_path,
        route_id="C1_ROOT_DIRECT_NATIVE_PATTERN",
        worker_id="0",
        output_path=tmp_path / "summary.json",
        trace_path=tmp_path / "trace.jsonl",
    )

    assert client.step_chunk_calls == []
    assert summary["classification"] == "BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY"
    assert "planner_record_failed:root_near" in summary["blockers"]
    assert summary["gate2_contact_allowed"] is False
```

- [x] **Step 3: Add runner capability guard test**

Test content:

```python
def test_runner_blocks_if_client_lacks_step_chunk(tmp_path):
    manifest_path = _write_single_route_manifest(tmp_path)
    client = FakeClient(planner_records=[_planned_record("robot_stage", [[0.1] * 9])])
    delattr(client, "step_chunk")

    summary = runner.run_native_action_path_route(
        client,
        manifest_path=manifest_path,
        route_id="C1_ROOT_DIRECT_NATIVE_PATTERN",
        worker_id="0",
        output_path=tmp_path / "summary.json",
        trace_path=tmp_path / "trace.jsonl",
    )

    assert summary["classification"] == "BLOCKED_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_MISSING"
    assert "client_step_chunk_missing" in summary["blockers"]
```

- [x] **Step 4: Run tests and verify RED**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest tests/labutopia_poc/test_native_action_path_runner.py -q
```

Expected: fail with `ImportError` or `ModuleNotFoundError` because `native_action_path_runner.py` does not exist yet.

## Task 2: Implement Minimal Runner

**Files:**
- Create: `standalone_tools/labutopia_poc/native_action_path_runner.py`

- [x] **Step 1: Implement route loading and selection**

Required functions:

```python
def load_route_manifest(path: Path | str) -> dict[str, Any]:
    ...

def select_route(manifest: dict[str, Any], route_id: str) -> dict[str, Any]:
    ...
```

Selection must require exactly one explicit `route_id`; it must reject missing, duplicate, or unknown routes.

- [x] **Step 2: Implement planner payload and action chunk conversion**

Required functions:

```python
def build_planner_payload(route: dict[str, Any], *, worker_id: str, refresh_world: bool, planner_ignore_list: list[str]) -> dict[str, Any]:
    ...

def action_from_joint_target(joint_target: Sequence[float], *, physics_hold_steps: int = 0) -> dict[str, Any]:
    ...

def action_chunk_from_planner_records(planner_records: list[dict[str, Any]], *, worker_id: str, max_action_points: int, physics_hold_steps: int = 0) -> tuple[list[dict[str, Any]], list[str]]:
    ...
```

Each action must include:

```python
{
    "control_type": "joint_position",
    "is_rel": False,
    "base_motion": [0.0, 0.0, 0.0],
    "base_is_rel": True,
    "action": [...]
}
```

- [x] **Step 3: Implement `run_native_action_path_route`**

Required behavior:

```python
summary = {
    "schema_version": 1,
    "runner": "native_action_path_runner",
    "route_id": route_id,
    "classification": ...,
    "gate2_contact_allowed": bool,
    "expert_oracle_score_allowed": False,
    "planner_response": ...,
    "planner_records": ...,
    "executed_steps": int,
    "blockers": [...]
}
```

Pass classification is `PASS_GATE1T_NATIVE_PATTERN_ROUTE_READY_FOR_GATE2_CONTACT`.
Planner/action/readback failure classification is `BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`.
Missing interface classification is `BLOCKED_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_MISSING`.

- [x] **Step 4: Implement CLI**

Required CLI arguments:

```text
--host
--port
--worker-id
--route-manifest
--route-id
--output
--trace-jsonl
--max-action-points
--physics-hold-steps
```

Import `genmanip_client.EvalClient` inside `main()` only so unit tests do not need optional live dependencies.

## Task 3: Verify Runner Tests

**Files:**
- Modify as needed: `tests/labutopia_poc/test_native_action_path_runner.py`
- Modify as needed: `standalone_tools/labutopia_poc/native_action_path_runner.py`

- [x] **Step 1: Run new tests**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest tests/labutopia_poc/test_native_action_path_runner.py -q
```

Expected: all tests pass.

- [x] **Step 2: Run adjacent planner/probe tests**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py tests/labutopia_poc/test_native_action_path_runner.py -q
```

Expected: all selected tests pass.

## Task 4: Update LabUtopia Evidence Documents

**Files:**
- Modify: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [x] **Step 1: Update runner audit status**

Change status from:

```text
BLOCKED_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_MISSING
```

to:

```text
CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE
```

Only after tests pass. Keep `gate1t_c2b_live_allowed_now=false` until a real Isaac live run exists.

- [x] **Step 2: Add PM summary**

Append the same claim boundary:

```text
C2a runner code is ready under unit tests, but C2b live evidence still does not exist. The next step is one selected live route; no contact, micro-pull, door-open, Expert Oracle Score, policy score, or official score claim is allowed yet.
```

## Verification

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest tests/labutopia_poc/test_native_action_path_runner.py -q
/usr/bin/python -m py_compile standalone_tools/labutopia_poc/native_action_path_runner.py

cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json >/dev/null
rg -n "CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE|C2a runner|C2b live|Expert Oracle Score" \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json
git diff --check -- \
  docs/superpowers/plans/2026-07-06-eos2-gate1t-c2a-native-action-path-runner-closure.md \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json
```

Expected:

```text
pytest exits 0
py_compile exits 0
json validation exits 0
rg finds the code-ready and C2b-live claim boundary strings
git diff --check exits 0
```

## Execution Update, 2026-07-06

C2a is now code-ready under unit tests, not live evidence. The completed red/green path was:

```text
RED: /usr/bin/python -m pytest tests/labutopia_poc/test_native_action_path_runner.py -q
     failed with ImportError before native_action_path_runner.py existed.

GREEN: /usr/bin/python -m pytest tests/labutopia_poc/test_native_action_path_runner.py -q
       5 passed.

ADJACENT: /usr/bin/python -m pytest tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py tests/labutopia_poc/test_native_action_path_runner.py -q
          28 passed.
```

The later two tests add C2b traceability: the runner now accepts `--run-id` and records `run_id` in the summary so live output can be matched to the submitted EBench job and server logs.

This closes only the C2a runner capability gap. C2b still requires one real Isaac / EBench live execution of a selected route before any Gate 1T route pass/fail, Gate 2 contact, Expert Oracle Score, policy score, or official score claim is allowed.

## Self-Review

Spec coverage:

- C2a runner missing blocker is addressed by code-ready runner tests.
- C2b remains not-live until a real Isaac run executes one selected route.
- Expert Oracle Score remains blocked.

Placeholder scan:

- No `TBD`, `TODO`, or unbounded sweep remains.

Type consistency:

- Classification strings match the existing Gate 1T manifests.

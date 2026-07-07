# EOS2 S0 Deterministic Franka Native Replay Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the zero-live code path that can capture LabUtopia Franka/native `ArticulationAction` outputs and turn a successful `level1_open_door` expert run into freezer-ready EBench replay JSONL.

**Architecture:** Add an Isaac-free action normalizer/logger module that is unit-testable without launching Isaac. Wire it into `main.py` behind opt-in CLI flags so normal LabUtopia behavior is unchanged. A future LabUtopia live run will use the logger output as the S0 candidate source, then `score_oracle_action_source_freezer.py` will freeze it before S1 formal score-chain smoke.

**Tech Stack:** Python, pytest, JSONL, SHA256, LabUtopia `main.py`, Isaac `ArticulationAction`-like duck typing, EBench replay JSONL schema.

---

## File Structure

- Create `utils/ebench_replay_action_source.py`
  - `normalize_joint_position_action(action, current_joint_positions, expected_action_dim)`
  - `make_replay_action_record(...)`
  - `EbenchReplayActionLogger`
  - JSON / JSONL / sha256 helpers
- Create `tests/test_ebench_replay_action_source.py`
  - Pure Python tests using fake action objects, no Isaac import.
- Modify `main.py`
  - Add opt-in CLI flags.
  - Initialize logger only when `--ebench-action-log-dir` is provided.
  - Log each non-null action after `task_controller.step(state)` and before `apply_action(action)`.
  - Finalize logger when episode ends or process exits.
- Create `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_deterministic_franka_source_plan_20260706.json`
  - Register this as zero-live implementation plan evidence.
- Modify `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify `docs/labutopia_lab_poc/evidence_manifests/README.md`

## Task 1: Action Normalizer

**Files:**
- Create: `utils/ebench_replay_action_source.py`
- Create: `tests/test_ebench_replay_action_source.py`

- [ ] **Step 1: Write failing tests**

Add this test content:

```python
import json
from pathlib import Path

import pytest

from utils.ebench_replay_action_source import (
    EbenchReplayActionLogger,
    make_replay_action_record,
    normalize_joint_position_action,
)


class FakeAction:
    def __init__(self, joint_positions=None):
        self.joint_positions = joint_positions


def test_normalize_fills_none_from_current_joint_positions():
    action = FakeAction([None, 0.2, None])
    result = normalize_joint_position_action(
        action,
        current_joint_positions=[0.1, 0.0, 0.3],
        expected_action_dim=3,
    )

    assert result == [0.1, 0.2, 0.3]


def test_normalize_rejects_missing_joint_positions():
    with pytest.raises(ValueError, match="missing_joint_positions"):
        normalize_joint_position_action(
            FakeAction(None),
            current_joint_positions=[0.1, 0.2, 0.3],
            expected_action_dim=3,
        )


def test_normalize_rejects_dimension_mismatch():
    with pytest.raises(ValueError, match="action_dim_mismatch:2!=3"):
        normalize_joint_position_action(
            FakeAction([0.1, 0.2]),
            current_joint_positions=[0.1, 0.2, 0.3],
            expected_action_dim=3,
        )


def test_normalize_rejects_bool_and_non_numeric_values():
    with pytest.raises(ValueError, match="joint_position_non_numeric:1"):
        normalize_joint_position_action(
            FakeAction([0.1, True, 0.3]),
            current_joint_positions=[0.1, 0.2, 0.3],
            expected_action_dim=3,
        )
```

- [ ] **Step 2: Run RED**

Run:

```bash
python -m pytest tests/test_ebench_replay_action_source.py -q
```

Expected: fail with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement normalizer**

Create `utils/ebench_replay_action_source.py` with:

```python
from __future__ import annotations

from numbers import Real
from typing import Any, Iterable


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _as_list(values: Iterable[Any], *, label: str) -> list[Any]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{label}_not_list")
    return list(values)


def normalize_joint_position_action(
    action: Any,
    *,
    current_joint_positions: Iterable[Any],
    expected_action_dim: int,
) -> list[float]:
    raw_joint_positions = getattr(action, "joint_positions", None)
    if raw_joint_positions is None:
        raise ValueError("missing_joint_positions")
    joint_positions = _as_list(raw_joint_positions, label="joint_positions")
    current = _as_list(current_joint_positions, label="current_joint_positions")
    if len(joint_positions) != int(expected_action_dim):
        raise ValueError(f"action_dim_mismatch:{len(joint_positions)}!={int(expected_action_dim)}")
    if len(current) != int(expected_action_dim):
        raise ValueError(f"current_joint_dim_mismatch:{len(current)}!={int(expected_action_dim)}")

    normalized: list[float] = []
    for index, value in enumerate(joint_positions):
        if value is None:
            value = current[index]
        if not _is_number(value):
            raise ValueError(f"joint_position_non_numeric:{index}")
        normalized.append(float(value))
    return normalized
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
python -m pytest tests/test_ebench_replay_action_source.py -q
```

Expected: tests pass.

## Task 2: Replay Record And Logger

**Files:**
- Modify: `utils/ebench_replay_action_source.py`
- Modify: `tests/test_ebench_replay_action_source.py`

- [ ] **Step 1: Add tests**

Append:

```python
def test_make_replay_action_record_has_ebench_schema():
    record = make_replay_action_record(
        step_index=2,
        worker_id="0",
        action_vector=[0.1, 0.2, 0.3],
        source={"controller_type": "open"},
    )

    assert record["step_index"] == 2
    assert record["worker_id"] == "0"
    assert record["action"]["control_type"] == "joint_position"
    assert record["action"]["action"] == [0.1, 0.2, 0.3]
    assert record["action"]["is_rel"] is False
    assert record["action"]["base_motion"] == [0.0, 0.0, 0.0]
    assert record["action"]["base_is_rel"] is True
    assert record["source"]["kind"] == "labutopia_native_articulation_action"
    assert record["source"]["controller_type"] == "open"


def test_logger_writes_jsonl_and_candidate_manifest(tmp_path):
    logger = EbenchReplayActionLogger(
        output_dir=tmp_path,
        worker_id="0",
        expected_action_dim=3,
        task_config_path="config/level1_open_door.yaml",
        controller_type="open",
        run_id="unit_run",
    )
    logger.log_action(
        FakeAction([None, 0.2, 0.3]),
        current_joint_positions=[0.1, 0.0, 0.0],
        labutopia_step_index=7,
    )
    manifest = logger.finalize(success_observed=True)

    action_source = tmp_path / "candidate_action_source.jsonl"
    records = [json.loads(line) for line in action_source.read_text(encoding="utf-8").splitlines()]
    assert records[0]["step_index"] == 0
    assert records[0]["source"]["labutopia_step_index"] == 7
    assert records[0]["action"]["action"] == [0.1, 0.2, 0.3]
    assert manifest["classification"] == "CANDIDATE_LABUTOPIA_NATIVE_ACTION_SOURCE"
    assert manifest["action_count"] == 1
    assert manifest["success_observed"] is True
    assert manifest["score_claim_allowed"] is False
    assert (tmp_path / "candidate_action_source_manifest.json").exists()
```

- [ ] **Step 2: Run RED**

Run:

```bash
python -m pytest tests/test_ebench_replay_action_source.py -q
```

Expected: fail because record/logger functions are missing.

- [ ] **Step 3: Implement record/logger**

Add JSON helpers, `make_replay_action_record`, and `EbenchReplayActionLogger` to `utils/ebench_replay_action_source.py`.
The logger must write `candidate_action_source.jsonl` and `candidate_action_source_manifest.json`, with all score/live
claims set to false.

- [ ] **Step 4: Run GREEN**

Run:

```bash
python -m pytest tests/test_ebench_replay_action_source.py -q
```

Expected: all tests pass.

## Task 3: Optional Main Integration

**Files:**
- Modify: `main.py`
- Modify: `tests/test_ebench_replay_action_source.py`

- [ ] **Step 1: Add CLI contract test by extracting parser helper if needed**

Avoid importing Isaac in tests. If parser testing requires refactor, add a pure helper in `utils/ebench_replay_action_source.py`
instead of importing `main.py`.

- [ ] **Step 2: Add CLI flags**

Add to `parse_args()`:

```python
parser.add_argument('--ebench-action-log-dir', type=str, default=None)
parser.add_argument('--ebench-action-worker-id', type=str, default='0')
parser.add_argument('--ebench-action-expected-dim', type=int, default=9)
```

- [ ] **Step 3: Initialize logger**

After config compose:

```python
from utils.ebench_replay_action_source import EbenchReplayActionLogger

ebench_action_logger = None
if args.ebench_action_log_dir:
    ebench_action_logger = EbenchReplayActionLogger(
        output_dir=args.ebench_action_log_dir,
        worker_id=args.ebench_action_worker_id,
        expected_action_dim=args.ebench_action_expected_dim,
        task_config_path=os.path.join(args.config_dir, f"{args.config_name}.yaml"),
        controller_type=str(cfg.controller_type),
        run_id=os.path.basename(os.path.abspath(args.ebench_action_log_dir)),
    )
```

- [ ] **Step 4: Log actions without changing behavior**

When `action is not None`, call:

```python
if ebench_action_logger is not None:
    ebench_action_logger.log_action(
        action,
        current_joint_positions=state['joint_positions'],
        labutopia_step_index=getattr(task, 'frame_idx', None),
    )
robot.get_articulation_controller().apply_action(action)
```

On done, finalize with `success_observed=is_success`. On shutdown, finalize if not already finalized.

- [ ] **Step 5: Static verification**

Run:

```bash
python -m py_compile utils/ebench_replay_action_source.py tests/test_ebench_replay_action_source.py
python -m pytest tests/test_ebench_replay_action_source.py -q
```

Expected: pass without Isaac.

## Task 4: Evidence Registration

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_deterministic_franka_source_plan_20260706.json`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [ ] **Step 1: Create zero-live manifest**

Manifest status:

```text
PLANNED_S0_DETERMINISTIC_FRANKA_NATIVE_REPLAY_SOURCE_NO_LIVE
```

Required claim boundary:

```json
{
  "live_evidence": false,
  "score_claim_allowed": false,
  "expert_oracle_score_claim_allowed": false,
  "frozen_real_expert_action_source_exists": false,
  "bounded_score_live_release_allowed_now": false
}
```

- [ ] **Step 2: Update PM docs**

Explain that A route now has a concrete implementation plan: capture actual controller output, normalize `None` with current
joint positions, write candidate JSONL, then freezer-gate before S1.

- [ ] **Step 3: Validate**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_deterministic_franka_source_plan_20260706.json >/tmp/s0_deterministic_franka_source_plan.json
git diff --check -- utils/ebench_replay_action_source.py tests/test_ebench_replay_action_source.py main.py docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_deterministic_franka_source_plan_20260706.json docs/labutopia_lab_poc/aan_consumer_handoff.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/evidence_manifests/README.md
```

Expected: exit code `0`.

## Self-Review

- The plan does not start S1 live.
- The plan does not claim existing video/H5 evidence is an expert action source.
- The plan keeps `candidate_action_source.jsonl` distinct from freezer-produced `action_source_manifest.json`.
- The plan makes all score/live claims false until a successful LabUtopia run and freezer output exist.

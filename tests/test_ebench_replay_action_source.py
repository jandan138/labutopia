import json

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


def test_normalize_expands_prefix_action_from_observed_tail_when_allowed():
    result = normalize_joint_position_action(
        FakeAction([1.0, 2.0, 3.0]),
        current_joint_positions=[0.1, 0.2, 0.3, 0.4, 0.5],
        expected_action_dim=5,
        allow_prefix_joint_positions=True,
    )

    assert result == [1.0, 2.0, 3.0, 0.4, 0.5]


def test_normalize_rejects_bool_and_non_numeric_values():
    with pytest.raises(ValueError, match="joint_position_non_numeric:1"):
        normalize_joint_position_action(
            FakeAction([0.1, True, 0.3]),
            current_joint_positions=[0.1, 0.2, 0.3],
            expected_action_dim=3,
        )


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
        allow_prefix_joint_positions=True,
    )
    logger.log_action(
        FakeAction([None, 0.2]),
        current_joint_positions=[0.1, 0.0, 0.3],
        labutopia_step_index=7,
    )
    manifest = logger.finalize(success_observed=True)

    action_source = tmp_path / "candidate_action_source.jsonl"
    records = [
        json.loads(line)
        for line in action_source.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["step_index"] == 0
    assert records[0]["source"]["labutopia_step_index"] == 7
    assert records[0]["action"]["action"] == [0.1, 0.2, 0.3]
    assert records[0]["source"]["raw_action_dim"] == 2
    assert records[0]["source"]["observed_joint_dim"] == 3
    assert records[0]["source"]["normalization"] == "prefix_action_expanded_with_observed_tail"
    assert manifest["classification"] == "CANDIDATE_LABUTOPIA_NATIVE_ACTION_SOURCE"
    assert manifest["action_count"] == 1
    assert manifest["allow_prefix_joint_positions"] is True
    assert manifest["success_observed"] is True
    assert manifest["score_claim_allowed"] is False
    assert (tmp_path / "candidate_action_source_manifest.json").exists()


def test_logger_discards_failed_episode_before_success_manifest(tmp_path):
    logger = EbenchReplayActionLogger(
        output_dir=tmp_path,
        worker_id="0",
        expected_action_dim=3,
        task_config_path="config/level1_open_door.yaml",
        controller_type="open",
        run_id="unit_run",
        allow_prefix_joint_positions=True,
    )

    logger.log_action(
        FakeAction([9.0, 9.0, 9.0]),
        current_joint_positions=[0.0, 0.0, 0.0],
        labutopia_step_index=1,
    )
    logger.discard_episode(success_observed=False, reason="failed_before_success")
    logger.log_action(
        FakeAction([None, 0.2]),
        current_joint_positions=[0.1, 0.0, 0.3],
        labutopia_step_index=7,
    )
    manifest = logger.finalize(success_observed=True)

    action_source = tmp_path / "candidate_action_source.jsonl"
    records = [
        json.loads(line)
        for line in action_source.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["step_index"] == 0
    assert records[0]["action"]["action"] == [0.1, 0.2, 0.3]
    assert records[0]["source"]["labutopia_step_index"] == 7
    assert manifest["success_observed"] is True
    assert manifest["discarded_episode_count"] == 1
    assert manifest["discarded_episode_reasons"] == ["failed_before_success"]

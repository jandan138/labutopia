from __future__ import annotations

import hashlib
import json
from numbers import Real
from pathlib import Path
from typing import Any, Iterable


CANDIDATE_CLASSIFICATION = "CANDIDATE_LABUTOPIA_NATIVE_ACTION_SOURCE"


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _as_list(values: Iterable[Any], *, label: str) -> list[Any]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{label}_not_list")
    return list(values)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_jsonable(payload), sort_keys=True) + "\n")


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_joint_position_action(
    action: Any,
    *,
    current_joint_positions: Iterable[Any],
    expected_action_dim: int,
    allow_prefix_joint_positions: bool = False,
) -> list[float]:
    raw_joint_positions = getattr(action, "joint_positions", None)
    if raw_joint_positions is None:
        raise ValueError("missing_joint_positions")
    joint_positions = _as_list(raw_joint_positions, label="joint_positions")
    current = _as_list(current_joint_positions, label="current_joint_positions")
    if len(joint_positions) != int(expected_action_dim):
        if allow_prefix_joint_positions and len(joint_positions) < int(expected_action_dim):
            joint_positions = joint_positions + current[len(joint_positions):int(expected_action_dim)]
        else:
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


def make_replay_action_record(
    *,
    step_index: int,
    worker_id: str,
    action_vector: Iterable[Any],
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    vector = _as_list(action_vector, label="action_vector")
    for index, value in enumerate(vector):
        if not _is_number(value):
            raise ValueError(f"action_vector_non_numeric:{index}")

    source_payload = {
        "kind": "labutopia_native_articulation_action",
        "source_role": "candidate_expert_action_source",
        "normalization": "none_filled_from_observed_joint_positions",
    }
    if source:
        source_payload.update(source)

    return {
        "step_index": int(step_index),
        "worker_id": str(worker_id),
        "action": {
            "action": [float(value) for value in vector],
            "control_type": "joint_position",
            "is_rel": False,
            "base_motion": [0.0, 0.0, 0.0],
            "base_is_rel": True,
        },
        "source": source_payload,
    }


class EbenchReplayActionLogger:
    def __init__(
        self,
        *,
        output_dir: str | Path,
        worker_id: str,
        expected_action_dim: int,
        task_config_path: str,
        controller_type: str,
        run_id: str,
        allow_prefix_joint_positions: bool = False,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.worker_id = str(worker_id)
        self.expected_action_dim = int(expected_action_dim)
        self.task_config_path = str(task_config_path)
        self.controller_type = str(controller_type)
        self.run_id = str(run_id)
        self.allow_prefix_joint_positions = bool(allow_prefix_joint_positions)
        self.action_source_path = self.output_dir / "candidate_action_source.jsonl"
        self.manifest_path = self.output_dir / "candidate_action_source_manifest.json"
        self._action_count = 0
        self._finalized = False
        self._discarded_episode_reasons: list[str] = []
        if self.action_source_path.exists():
            self.action_source_path.unlink()

    def log_action(
        self,
        action: Any,
        *,
        current_joint_positions: Iterable[Any],
        labutopia_step_index: int | None,
    ) -> dict[str, Any]:
        if self._finalized:
            raise RuntimeError("action_logger_finalized")
        raw_joint_positions = getattr(action, "joint_positions", None)
        raw_action_dim = len(_as_list(raw_joint_positions, label="joint_positions"))
        observed_joint_dim = len(_as_list(current_joint_positions, label="current_joint_positions"))
        normalization = "none_filled_from_observed_joint_positions"
        if self.allow_prefix_joint_positions and raw_action_dim < self.expected_action_dim:
            normalization = "prefix_action_expanded_with_observed_tail"
        action_vector = normalize_joint_position_action(
            action,
            current_joint_positions=current_joint_positions,
            expected_action_dim=self.expected_action_dim,
            allow_prefix_joint_positions=self.allow_prefix_joint_positions,
        )
        record = make_replay_action_record(
            step_index=self._action_count,
            worker_id=self.worker_id,
            action_vector=action_vector,
            source={
                "controller_type": self.controller_type,
                "task_config": self.task_config_path,
                "run_id": self.run_id,
                "labutopia_step_index": labutopia_step_index,
                "raw_action_dim": raw_action_dim,
                "observed_joint_dim": observed_joint_dim,
                "normalization": normalization,
            },
        )
        _append_jsonl(self.action_source_path, record)
        self._action_count += 1
        return record

    def discard_episode(self, *, success_observed: bool | None, reason: str) -> None:
        if self._finalized:
            raise RuntimeError("action_logger_finalized")
        self._discarded_episode_reasons.append(str(reason))
        if self.action_source_path.exists():
            self.action_source_path.unlink()
        self._action_count = 0

    def finalize(self, *, success_observed: bool | None = None) -> dict[str, Any]:
        task_config = Path(self.task_config_path)
        manifest = {
            "schema_version": 1,
            "classification": CANDIDATE_CLASSIFICATION,
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "expected_action_dim": self.expected_action_dim,
            "control_type": "joint_position",
            "source_kind": "labutopia_native_articulation_action",
            "task_config_path": self.task_config_path,
            "task_config_sha256": _sha256(task_config),
            "controller_type": self.controller_type,
            "allow_prefix_joint_positions": self.allow_prefix_joint_positions,
            "discarded_episode_count": len(self._discarded_episode_reasons),
            "discarded_episode_reasons": list(self._discarded_episode_reasons),
            "action_source_path": str(self.action_source_path),
            "action_source_sha256": _sha256(self.action_source_path),
            "action_count": self._action_count,
            "success_observed": success_observed,
            "score_claim_allowed": False,
            "expert_oracle_score_claim_allowed": False,
            "official_benchmark_reproduction_claim_allowed": False,
            "standard_model_score_claim_allowed": False,
            "policy_claim_allowed": False,
            "live_evidence": False,
            "frozen_real_expert_action_source_exists": False,
            "bounded_score_live_release_allowed_now": False,
            "claim_boundary": (
                "This is a candidate LabUtopia native action source. It must pass the "
                "S0 freezer and S1 release review before any Expert Oracle Score claim."
            ),
        }
        _write_json(self.manifest_path, manifest)
        self._finalized = True
        return manifest

#!/usr/bin/env python3
"""Replay an accepted strict real-beaker trace as three render-only OmniGlass candidates."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if TYPE_CHECKING:
    from tools.labutopia_fluid.real_beaker import CupInteriorFrame


PRESENTATION_POINTS_PATH = "/World/CompletedPBD/PresentationParticleSet"
HIDDEN_PHYSICAL_INITIAL_STATE_PATH = "/World/CompletedPBD/AcceptedPhysicalInitialState"
REFERENCE_CANDIDATE_IDS = (
    "OMNI_REF_FINE",
    "OMNI_REF_RATIO_15",
    "OMNI_REF_RATIO_12",
)
DEFAULT_CANDIDATES = ",".join(REFERENCE_CANDIDATE_IDS)
DEFAULT_OUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_omniglass_reference_20260711_001"
)
VERSION_MATCHED_MDL_CLOSURE_DIRNAME = "material_closure_isaacsim41_conda_core"
PHYSICAL_TRACE_IDENTITY_FIELDS = (
    "source_usd_sha256",
    "particle_count",
    "seed",
    "steps",
    "trace_interval",
    "frame_indices",
    "frame_particle_counts",
    "frame_count",
    "positions_sha256",
    "physical_trace_sha256",
)
_HEX_DIGITS = frozenset("0123456789abcdef")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_version_matched_mdl_source_contract(
    native: Any,
    *,
    runtime_prefix: str | os.PathLike[str] | None = None,
    runtime_version: str | None = None,
) -> dict[str, Any]:
    """Resolve and hash the active Isaac 4.1 conda MDL source tree."""
    prefix = Path(runtime_prefix or sys.prefix).resolve()
    version = runtime_version or importlib.metadata.version("isaacsim")
    if not str(version).startswith("4.1"):
        raise ValueError(f"target_isaacsim41_runtime_required:{version}")
    source_root = Path(native.PRESENTATION_WATER_MDL_ROOT).resolve()
    try:
        relative_root = source_root.relative_to(prefix)
    except ValueError as exc:
        raise ValueError(
            f"version_matched_conda_mdl_root_required:{source_root}:runtime_prefix={prefix}"
        ) from exc
    if "site-packages" not in relative_root.parts or source_root.parts[-3:] != (
        "omni",
        "mdl",
        "core",
    ):
        raise ValueError(f"version_matched_conda_mdl_root_required:{source_root}")

    required_relative = {
        *(f"Base/{name}" for name in native.CORE_MDL_DIRECT_ASSETS),
        *(f"Base/{name}" for name in native.CORE_MDL_TRANSITIVE_DEPENDENCIES),
        "mdl/OmniSurface/OmniSurfaceBase.mdl",
    }
    missing = sorted(
        relative
        for relative in required_relative
        if not (source_root / relative).is_file()
    )
    if missing:
        raise FileNotFoundError(
            "version_matched_omniglass_mdl_files_missing:" + ",".join(missing)
        )
    source_files = sorted(
        [*source_root.glob("Base/*.mdl"), *source_root.glob("mdl/OmniSurface/*.mdl")]
    )
    if not source_files:
        raise FileNotFoundError("version_matched_omniglass_mdl_tree_empty")
    source_hashes = {
        str(path.relative_to(source_root)): _sha256_file(path) for path in source_files
    }
    required_hashes = {
        relative: source_hashes[relative] for relative in sorted(required_relative)
    }
    return {
        "source_root": str(source_root),
        "runtime_prefix": str(prefix),
        "runtime_version": str(version),
        "source_root_under_runtime_prefix": True,
        "required_file_sha256": required_hashes,
        "source_file_sha256": source_hashes,
        "source_tree_sha256": _json_sha256(source_hashes),
        "host_isaac_sim_root_allowed": False,
    }


def _mirror_version_matched_mdl_closure(
    native: Any,
    *,
    artifact_dir: Path,
) -> dict[str, Any]:
    source = build_version_matched_mdl_source_contract(native)
    source_root = Path(source["source_root"])
    closure_root = artifact_dir / VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    for relative in source["source_file_sha256"]:
        source_path = source_root / relative
        target_path = closure_root / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    copied_hashes = {
        relative: _sha256_file(closure_root / relative)
        for relative in source["source_file_sha256"]
    }
    if copied_hashes != source["source_file_sha256"]:
        raise RuntimeError("version_matched_mdl_closure_hash_mismatch")
    return {
        **source,
        "material_closure_mode": "isaacsim41_conda_version_matched_core",
        "closure_root": str(closure_root),
        "closure_base_dir": str(closure_root / "Base"),
        "closure_omnisurface_module_dir": str(closure_root / "mdl/OmniSurface"),
        "copied_file_sha256": copied_hashes,
        "copied_tree_sha256": _json_sha256(copied_hashes),
    }


def _require_plain_int(name: str, value: Any, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise ValueError(f"{name}_must_be_non_bool_int")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name}_must_be_at_least_{minimum}")
    return value


def _require_sha256(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_DIGITS for character in value.lower())
    ):
        raise ValueError(f"{name}_must_be_sha256")
    return value.lower()


def _reject_nonfinite_json(token: str) -> Any:
    raise ValueError(f"nonfinite_json_token:{token}")


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8")
        value = json.loads(payload, parse_constant=_reject_nonfinite_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label}_unreadable:{type(exc).__name__}:{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}_must_be_json_object")
    return value


def _load_trace_once(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"accepted_trace_unreadable:{type(exc).__name__}:{exc}"
        ) from exc
    if not text or not text.endswith("\n"):
        raise ValueError("accepted_trace_must_be_nonempty_newline_delimited_json")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"accepted_trace_blank_line:{line_number}")
        try:
            record = json.loads(line, parse_constant=_reject_nonfinite_json)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"accepted_trace_json_invalid:{line_number}:{exc}"
            ) from exc
        if not isinstance(record, dict):
            raise ValueError(f"accepted_trace_record_not_object:{line_number}")
        records.append(record)
    return tuple(records)


def _resolve_input_path(summary_path: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}_missing")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = summary_path.parent / path
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label}_missing:{resolved}")
    return resolved


def _classification_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        name = value.get("classification")
        return str(name) if name is not None else None
    return str(value) if value is not None else None


def _validate_run_scoped_diagnostics(
    summary: Mapping[str, Any], *, summary_path: Path
) -> None:
    segment = summary.get("strict_kit_log_segment")
    isaac_summary = summary.get("isaac_log_summary")
    if not isinstance(segment, Mapping) or not isinstance(isaac_summary, Mapping):
        raise ValueError("run_scoped_diagnostics_incomplete:missing_contract")
    try:
        if not isinstance(segment.get("log_path"), str) or not segment["log_path"]:
            raise ValueError("missing_log_path")
        byte_offset = _require_plain_int(
            "diagnostic_byte_offset", segment.get("byte_offset"), minimum=0
        )
        byte_count = _require_plain_int(
            "diagnostic_segment_byte_count",
            segment.get("segment_byte_count"),
            minimum=0,
        )
        segment_hash = _require_sha256(
            "diagnostic_segment_sha256", segment.get("segment_sha256")
        )
        if segment.get("cursor_captured") is not True:
            raise ValueError("cursor_not_captured")
        if segment.get("diagnostic_scan_complete") is not True:
            raise ValueError("scan_not_complete")
        if isaac_summary.get("run_segment_only") is not True:
            raise ValueError("diagnostics_not_run_segment_only")
        if isaac_summary.get("isaac_log_available") is not True:
            raise ValueError("isaac_log_unavailable")
        if isaac_summary.get("diagnostic_scan_complete") is not True:
            raise ValueError("isaac_scan_not_complete")
        equality_fields = {
            "log_path": segment["log_path"],
            "byte_offset": byte_offset,
            "segment_byte_count": byte_count,
            "segment_sha256": segment_hash,
            "cursor_captured": True,
        }
        for field, expected in equality_fields.items():
            if isaac_summary.get(field) != expected:
                raise ValueError(f"diagnostic_provenance_mismatch:{field}")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"run_scoped_diagnostics_incomplete:{exc}") from exc

    log_path = _resolve_input_path(
        summary_path, segment["log_path"], label="declared_kit_log"
    )
    try:
        with log_path.open("rb") as stream:
            stream.seek(byte_offset)
            payload = stream.read(byte_count)
    except OSError as exc:
        raise ValueError(
            f"diagnostic_segment_unreadable:{type(exc).__name__}:{exc}"
        ) from exc
    if len(payload) != byte_count:
        raise ValueError(
            f"diagnostic_segment_truncated:{len(payload)}!={byte_count}"
        )
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != segment_hash:
        raise ValueError(
            f"diagnostic_segment_sha256_mismatch:{actual_hash}!={segment_hash}"
        )


def _vector3(name: str, value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"accepted_cup_frame_invalid:{name}")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"accepted_cup_frame_invalid:{name}")
    return result


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(left[index]) * float(right[index]) for index in range(3))


def _frame_from_summary(value: Any) -> CupInteriorFrame:
    from tools.labutopia_fluid.real_beaker import CupInteriorFrame

    if not isinstance(value, Mapping):
        raise ValueError("accepted_cup_frame_missing")
    core_fields = {
        "origin_world",
        "x_axis_world",
        "y_axis_world",
        "z_axis_world",
        "parent_local_axis",
        "outer_radius",
        "interior_radius",
        "outer_floor",
        "interior_floor",
        "rim_height",
        "calibration_source",
        "axis_alignment_dot",
    }
    try:
        origin = _vector3("origin_world", value["origin_world"])
        axes = tuple(
            _vector3(name, value[name])
            for name in ("x_axis_world", "y_axis_world", "z_axis_world")
        )
        scalars = {
            name: float(value[name])
            for name in (
                "outer_radius",
                "interior_radius",
                "outer_floor",
                "interior_floor",
                "rim_height",
                "axis_alignment_dot",
            )
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"accepted_cup_frame_invalid:{exc}") from exc
    if not all(math.isfinite(item) for item in scalars.values()):
        raise ValueError("accepted_cup_frame_invalid:nonfinite_scalar")
    if scalars["interior_radius"] <= 0.0 or scalars["outer_radius"] <= 0.0:
        raise ValueError("accepted_cup_frame_invalid:radius")
    if scalars["rim_height"] <= scalars["interior_floor"]:
        raise ValueError("accepted_cup_frame_invalid:height")
    if scalars["axis_alignment_dot"] < 0.999:
        raise ValueError("accepted_cup_frame_invalid:axis_alignment")
    for index, axis in enumerate(axes):
        if not math.isclose(_dot(axis, axis), 1.0, abs_tol=1e-6):
            raise ValueError(f"accepted_cup_frame_invalid:axis_norm:{index}")
    if any(
        not math.isclose(_dot(axes[left], axes[right]), 0.0, abs_tol=1e-6)
        for left, right in ((0, 1), (0, 2), (1, 2))
    ):
        raise ValueError("accepted_cup_frame_invalid:axis_orthogonality")
    measurements = {
        key: deepcopy(item) for key, item in value.items() if key not in core_fields
    }
    return CupInteriorFrame(
        origin_world=origin,
        x_axis_world=axes[0],
        y_axis_world=axes[1],
        z_axis_world=axes[2],
        parent_local_axis=str(value["parent_local_axis"]),
        outer_radius=scalars["outer_radius"],
        interior_radius=scalars["interior_radius"],
        outer_floor=scalars["outer_floor"],
        interior_floor=scalars["interior_floor"],
        rim_height=scalars["rim_height"],
        calibration_source=str(value["calibration_source"]),
        axis_alignment_dot=scalars["axis_alignment_dot"],
        _measurements=measurements,
    )


@dataclass(frozen=True)
class AcceptedReplayInput:
    summary_path: Path
    source_usd_path: Path
    trace_path: Path
    summary: dict[str, Any]
    records: tuple[dict[str, Any], ...]
    physical_trace_identity: dict[str, Any]
    frame: CupInteriorFrame
    candidates: dict[str, dict[str, Any]]

    def proxy_frame(self, candidate_id: str, *, frame_offset: int) -> dict[str, Any]:
        from tools.labutopia_fluid.omniglass_reference import (
            build_presentation_proxy_frame,
        )

        if candidate_id not in self.candidates:
            raise ValueError(f"unknown_reference_candidate:{candidate_id}")
        try:
            record = self.records[frame_offset]
        except IndexError as exc:
            raise ValueError(f"trace_frame_offset_out_of_range:{frame_offset}") from exc
        return build_presentation_proxy_frame(
            record["positions"],
            frame=self.frame,
            candidate=self.candidates[candidate_id],
        )


def load_and_validate_accepted_replay(
    accepted_summary: str | os.PathLike[str],
) -> AcceptedReplayInput:
    """Load all accepted evidence once and fail closed before Isaac is imported."""
    from tools.labutopia_fluid.omniglass_reference import (
        REFERENCE_CANDIDATE_IDS as HELPER_CANDIDATE_IDS,
        build_reference_candidates,
    )
    from tools.labutopia_fluid.real_beaker import validate_strict_trace_schema

    if HELPER_CANDIDATE_IDS != REFERENCE_CANDIDATE_IDS:
        raise RuntimeError("reference_candidate_ids_diverged")
    summary_path = Path(accepted_summary).expanduser().resolve()
    if not summary_path.is_file():
        raise FileNotFoundError(f"accepted_summary_missing:{summary_path}")
    summary = _load_json_object(summary_path, label="accepted_summary")
    strict = summary.get("strict_visible_classification")
    if not isinstance(strict, Mapping):
        raise ValueError("accepted_static_hold_required:strict_classification_missing")
    if (
        _classification_name(strict) != "PASS_VISIBLE_BEAKER_STATIC_HOLD"
        or _classification_name(summary.get("classification"))
        != "PASS_VISIBLE_BEAKER_STATIC_HOLD"
        or strict.get("trace_schema_valid") is not True
        or strict.get("diagnostic_scan_complete") is not True
        or summary.get("visible_beaker_containment_verified") is not True
    ):
        raise ValueError("accepted_static_hold_required")
    _validate_run_scoped_diagnostics(summary, summary_path=summary_path)

    identity_value = summary.get("physical_trace_identity")
    strict_identity = strict.get("physical_trace_identity")
    if not isinstance(identity_value, Mapping) or not isinstance(
        strict_identity, Mapping
    ):
        raise ValueError("physical_trace_identity_missing")
    identity = deepcopy(dict(identity_value))
    if dict(strict_identity) != identity:
        raise ValueError("physical_trace_identity_inconsistent_in_summary")
    try:
        requested_count = _require_plain_int(
            "identity_particle_count", identity["particle_count"], minimum=1
        )
        seed = _require_plain_int("identity_seed", identity["seed"], minimum=0)
        steps = _require_plain_int("identity_steps", identity["steps"], minimum=0)
        cadence = _require_plain_int(
            "identity_trace_interval", identity["trace_interval"], minimum=1
        )
        expected_source_hash = _require_sha256(
            "identity_source_usd_sha256", identity["source_usd_sha256"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"physical_trace_identity_incomplete:{exc}") from exc

    source_path = _resolve_input_path(
        summary_path, summary.get("source_usd_path"), label="accepted_source_usd"
    )
    trace_path = _resolve_input_path(
        summary_path, summary.get("trace_path"), label="accepted_trace"
    )
    actual_source_hash = _sha256_file(source_path)
    if actual_source_hash != expected_source_hash:
        raise ValueError(
            f"accepted_source_usd_sha256_mismatch:{actual_source_hash}!={expected_source_hash}"
        )
    if summary.get("source_usd_sha256") not in (None, expected_source_hash):
        raise ValueError("accepted_summary_source_usd_sha256_mismatch")

    try:
        if (
            _require_plain_int(
                "selected_particle_count", summary["selected_particle_count"], minimum=1
            )
            != requested_count
        ):
            raise ValueError("selected_particle_count_mismatch")
        if _require_plain_int("summary_steps", summary["steps"], minimum=0) != steps:
            raise ValueError("summary_steps_mismatch")
        plan = summary["controlled_spawn_plan"]
        region = summary["region_config"]
        if not isinstance(plan, Mapping) or not isinstance(region, Mapping):
            raise ValueError("summary_trace_configuration_missing")
        if _require_plain_int("summary_seed", plan["particle_seed"], minimum=0) != seed:
            raise ValueError("summary_seed_mismatch")
        if (
            _require_plain_int(
                "summary_trace_interval", region["trace_interval"], minimum=1
            )
            != cadence
        ):
            raise ValueError("summary_trace_interval_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"accepted_summary_trace_contract_invalid:{exc}") from exc

    try:
        records = _load_trace_once(trace_path)
        recomputed = validate_strict_trace_schema(
            records,
            requested_count=requested_count,
            steps=steps,
            cadence=cadence,
            source_usd_sha256=actual_source_hash,
            particle_seed=seed,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"strict_trace_schema_invalid:{exc}") from exc
    if recomputed != identity:
        raise ValueError(
            "physical_trace_identity_mismatch:accepted_summary_does_not_exactly_equal_recomputed_trace"
        )
    if set(recomputed) != set(PHYSICAL_TRACE_IDENTITY_FIELDS):
        raise ValueError("physical_trace_identity_field_set_invalid")

    frame = _frame_from_summary(summary.get("cup_interior_frame"))
    candidates = build_reference_candidates(frame.interior_radius * 2.0)
    return AcceptedReplayInput(
        summary_path=summary_path,
        source_usd_path=source_path,
        trace_path=trace_path,
        summary=summary,
        records=records,
        physical_trace_identity=recomputed,
        frame=frame,
        candidates=candidates,
    )


def _parse_candidate_ids(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        candidate_ids = tuple(item.strip() for item in value.split(",") if item.strip())
    else:
        candidate_ids = tuple(str(item).strip() for item in value)
    if candidate_ids != REFERENCE_CANDIDATE_IDS:
        raise ValueError(
            "replay_requires_all_three_candidates_in_canonical_order:"
            + ",".join(REFERENCE_CANDIDATE_IDS)
        )
    return candidate_ids


def build_candidate_replay_contracts(
    accepted: AcceptedReplayInput,
    candidate_ids: Sequence[str] = REFERENCE_CANDIDATE_IDS,
) -> dict[str, dict[str, Any]]:
    candidate_ids = _parse_candidate_ids(candidate_ids)
    identity = accepted.physical_trace_identity
    manifests: dict[str, dict[str, Any]] = {}
    for candidate_id in candidate_ids:
        candidate = accepted.candidates[candidate_id]
        frame_contracts = []
        for frame_offset, record in enumerate(accepted.records):
            proxy = accepted.proxy_frame(candidate_id, frame_offset=frame_offset)
            frame_contracts.append(
                {
                    "frame_offset": frame_offset,
                    "frame_index": int(record["step_index"]),
                    "source_physical_point_count": proxy["source_physical_point_count"],
                    "proxy_count": proxy["proxy_count"],
                    "display_width": proxy["display_width"],
                    "voxel_size": proxy["voxel_size"],
                    "width_to_interior_ratio": proxy["width_to_interior_ratio"],
                }
            )
        manifests[candidate_id] = {
            "schema_version": 1,
            "manifest_type": "real_beaker_omniglass_reference_candidate",
            "candidate_id": candidate_id,
            "source_usd_path": str(accepted.source_usd_path),
            "accepted_summary_path": str(accepted.summary_path),
            "accepted_trace_path": str(accepted.trace_path),
            "physical_trace_identity": deepcopy(identity),
            "input_identity": deepcopy(identity),
            "display_width": candidate["display_width"],
            "voxel_size": candidate["voxel_size"],
            "width_to_interior_ratio": candidate["width_to_interior_ratio"],
            "interior_diameter": candidate["interior_diameter"],
            "proxy_mode": candidate["proxy_mode"],
            "presentation_only": True,
            "presentation_points_path": PRESENTATION_POINTS_PATH,
            "presentation_uses_physx_api": False,
            "frames": frame_contracts,
            "frame_indices": deepcopy(identity["frame_indices"]),
            "frame_particle_counts": deepcopy(identity["frame_particle_counts"]),
            "frame_count": identity["frame_count"],
            "per_frame_proxy_counts": [
                frame["proxy_count"] for frame in frame_contracts
            ],
            "static_presentation_frame_index": identity["frame_indices"][-1],
            "static_presentation_source_physical_point_count": identity[
                "frame_particle_counts"
            ][-1],
            "hidden_physical_initial_state_path": HIDDEN_PHYSICAL_INITIAL_STATE_PATH,
            "hidden_physical_initial_state_frame_index": identity["frame_indices"][0],
            "hidden_physical_initial_state_point_count": identity[
                "frame_particle_counts"
            ][0],
            "a18_material": deepcopy(candidate["a18_reference"]),
            "beaker_override_required": True,
            "runtime_contract": {
                "source_usd_path": str(accepted.source_usd_path),
                "open_exact_accepted_source": True,
                "physics_steps_executed": 0,
                "timeline_play_called": False,
                "cameras": ["context", "source_beaker_closeup"],
            },
            "accepted_4096_trace_preferred": identity["particle_count"] == 4096,
            "accepted_1024_visual_debug_limitation": identity["particle_count"] == 1024,
            "visual_review_verdict": "PENDING_INDEPENDENT_REVIEW",
            "omniglass_reference_particle_look_selected": False,
        }
    if any(manifest["input_identity"] != identity for manifest in manifests.values()):
        raise AssertionError("candidate_input_identity_diverged")
    return manifests


def atomic_write_json(path: str | os.PathLike[str], payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _artifact_relative_path(candidate_dir: Path, path: Path) -> str:
    resolved_dir = candidate_dir.resolve()
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(resolved_dir))
    except ValueError as exc:
        raise ValueError(f"candidate_artifact_outside_run_scope:{resolved}") from exc


def _validate_nonempty_artifact(path: Path, *, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"candidate_artifact_missing:{label}:{path}")


def _validate_png(path: Path) -> None:
    _validate_nonempty_artifact(path, label="image")
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"candidate_image_not_png:{path}")


def finalize_candidate_manifest(
    contract: Mapping[str, Any],
    *,
    candidate_dir: str | os.PathLike[str],
    static_usd_path: str | os.PathLike[str],
    closeup_image_paths: Sequence[str | os.PathLike[str]],
    context_image_paths: Sequence[str | os.PathLike[str]],
    video_paths: Sequence[str | os.PathLike[str]],
) -> dict[str, Any]:
    """Hash complete artifacts and leave visual acceptance to independent review."""
    candidate_root = Path(candidate_dir).resolve()
    static_path = Path(static_usd_path)
    closeups = [Path(path) for path in closeup_image_paths]
    contexts = [Path(path) for path in context_image_paths]
    videos = [Path(path) for path in video_paths]
    expected_frames = _require_plain_int(
        "candidate_frame_count", contract.get("frame_count"), minimum=1
    )
    if len(closeups) != expected_frames or len(contexts) != expected_frames:
        raise ValueError(
            "candidate_images_incomplete:"
            f"closeup={len(closeups)},context={len(contexts)},expected={expected_frames}"
        )
    missing_images = [path for path in [*closeups, *contexts] if not path.is_file()]
    if missing_images:
        raise ValueError(
            "candidate_images_incomplete:missing="
            + ",".join(str(path) for path in missing_images)
        )
    _validate_nonempty_artifact(static_path, label="static_usd")
    for path in [*closeups, *contexts]:
        _validate_png(path)
    for path in videos:
        _validate_nonempty_artifact(path, label="video")
    artifacts = [static_path, *closeups, *contexts, *videos]
    hashes = {
        _artifact_relative_path(candidate_root, path): _sha256_file(path)
        for path in artifacts
    }
    finalized = deepcopy(dict(contract))
    finalized.update(
        {
            "static_candidate_usd_path": str(static_path.resolve()),
            "closeup_image_paths": [str(path.resolve()) for path in closeups],
            "context_image_paths": [str(path.resolve()) for path in contexts],
            "video_paths": [str(path.resolve()) for path in videos],
            "artifact_sha256": hashes,
            "render_artifacts_complete": True,
            "visual_review_verdict": "PENDING_INDEPENDENT_REVIEW",
            "omniglass_reference_particle_look_selected": False,
            "claim_boundary": {
                "allowed": [
                    "accepted_physical_trace_replayed_without_physics_steps=true",
                    "render_only_omniglass_proxy_authored=true",
                    "candidate_images_recorded=true",
                ],
                "blocked": [
                    "visual_review_passed=true",
                    "omniglass_reference_particle_look_selected=true",
                    "presentation_points_are_physical_particles=true",
                ],
            },
        }
    )
    return finalized


def hide_physical_and_debug_points(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    hidden: list[str] = []
    physical_roots = {
        "/World/fluid",
        "/World/ParticleSet",
        "/World/ParticleSystem",
        "/World/CompletedPBD/ParticleSet",
        "/World/CompletedPBD/ParticleSystem",
    }
    for prim in list(stage.Traverse()):
        path = str(prim.GetPath())
        lower_path = path.lower()
        is_debug = any(
            token in lower_path for token in ("debug", "reviewmarker", "visualizer")
        )
        is_physical_root = path in physical_roots
        if path != PRESENTATION_POINTS_PATH and (is_debug or is_physical_root):
            imageable = UsdGeom.Imageable(prim)
            if imageable:
                imageable.MakeInvisible()
                hidden.append(path)
    return {
        "hidden_paths": sorted(hidden),
        "disabled_particle_system_paths": [],
        "physics_attributes_authored": False,
        "physical_and_debug_points_hidden": True,
    }


def require_stopped_timeline(timeline: Any) -> None:
    if bool(timeline.is_playing()):
        raise RuntimeError("timeline_must_remain_stopped_for_static_trace_replay")


def author_static_candidate_state(
    stage: Any,
    *,
    accepted: AcceptedReplayInput,
    candidate_contract: Mapping[str, Any],
    material_path: str | None,
) -> dict[str, Any]:
    """Author hidden initial physical evidence and the final presentation default."""
    from pxr import Sdf, UsdGeom

    from tools.labutopia_fluid.omniglass_reference import author_presentation_points

    candidate_id = str(candidate_contract["candidate_id"])
    visibility = hide_physical_and_debug_points(stage)
    physics_width = float(
        accepted.summary["physics_particle_offsets"]["particle_width"]
    )
    hidden_prim = author_presentation_points(
        stage,
        path=HIDDEN_PHYSICAL_INITIAL_STATE_PATH,
        positions=accepted.records[0]["positions"],
        display_width=physics_width,
        material_path=None,
    )
    UsdGeom.Imageable(hidden_prim).MakeInvisible()
    hidden_prim.CreateAttribute(
        "labutopia:physicalTraceFrameIndex", Sdf.ValueTypeNames.Int, custom=True
    ).Set(int(candidate_contract["hidden_physical_initial_state_frame_index"]))
    hidden_prim.CreateAttribute(
        "labutopia:traceRole", Sdf.ValueTypeNames.Token, custom=True
    ).Set("accepted_physical_initial_state")

    final_proxy = accepted.proxy_frame(candidate_id, frame_offset=-1)
    presentation_prim = author_presentation_points(
        stage,
        path=PRESENTATION_POINTS_PATH,
        positions=final_proxy["positions_world"],
        display_width=float(candidate_contract["display_width"]),
        material_path=material_path,
    )
    UsdGeom.Imageable(presentation_prim).MakeVisible()
    presentation_prim.CreateAttribute(
        "labutopia:physicalTraceFrameIndex", Sdf.ValueTypeNames.Int, custom=True
    ).Set(int(candidate_contract["static_presentation_frame_index"]))
    presentation_prim.CreateAttribute(
        "labutopia:candidateId", Sdf.ValueTypeNames.Token, custom=True
    ).Set(candidate_id)
    presentation_has_physx = any(
        "physx" in token.lower() for token in presentation_prim.GetAppliedSchemas()
    ) or any(
        relationship.GetName().lower().startswith("physx")
        for relationship in presentation_prim.GetRelationships()
    )
    if presentation_has_physx:
        raise RuntimeError("presentation_points_unexpectedly_have_physx_api")
    return {
        **visibility,
        "presentation_points_path": PRESENTATION_POINTS_PATH,
        "hidden_physical_initial_state_path": HIDDEN_PHYSICAL_INITIAL_STATE_PATH,
        "static_presentation_frame_index": int(
            candidate_contract["static_presentation_frame_index"]
        ),
        "hidden_physical_initial_state_frame_index": int(
            candidate_contract["hidden_physical_initial_state_frame_index"]
        ),
        "static_proxy_count": final_proxy["proxy_count"],
        "hidden_physical_initial_state_point_count": len(
            accepted.records[0]["positions"]
        ),
        "physics_schema_applied_to_presentation": False,
    }


def _set_presentation_frame(stage: Any, proxy: Mapping[str, Any]) -> None:
    from pxr import Gf, UsdGeom

    points = UsdGeom.Points(stage.GetPrimAtPath(PRESENTATION_POINTS_PATH))
    if not points:
        raise RuntimeError("presentation_points_missing_during_replay")
    points.GetPointsAttr().Set([Gf.Vec3f(*point) for point in proxy["positions_world"]])
    points.GetWidthsAttr().Set([float(proxy["display_width"])])
    points.SetWidthsInterpolation(UsdGeom.Tokens.constant)


def _same_frame_core(left: CupInteriorFrame, right: CupInteriorFrame) -> bool:
    if left.parent_local_axis != right.parent_local_axis:
        return False
    for name in (
        "origin_world",
        "x_axis_world",
        "y_axis_world",
        "z_axis_world",
    ):
        if any(
            not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-9)
            for a, b in zip(getattr(left, name), getattr(right, name))
        ):
            return False
    return all(
        math.isclose(
            float(getattr(left, name)),
            float(getattr(right, name)),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for name in (
            "outer_radius",
            "interior_radius",
            "outer_floor",
            "interior_floor",
            "rim_height",
            "axis_alignment_dot",
        )
    )


def _author_version_matched_beaker_override(
    stage: Any,
    *,
    profile: Mapping[str, Any],
    mdl_source_asset: Path,
) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    override = dict(profile.get("beaker_override") or {})
    if override.get("enabled") is not True:
        raise ValueError("beaker_override_required_for_omniglass_replay")
    source_asset = mdl_source_asset.resolve()
    if not source_asset.is_file() or source_asset.name != "OmniGlass.mdl":
        raise FileNotFoundError(f"version_matched_omniglass_mdl_missing:{source_asset}")
    looks_path = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)

    target_mesh = str(override.get("target_mesh") or "/World/beaker2/mesh")
    material_path = str(
        override.get("material_path") or "/World/Looks/LiquidPresentationBeakerGlass"
    )
    glass_color = override.get("glass_color") or (0.85, 0.92, 0.95)
    reflection_color = override.get("reflection_color") or (0.90, 0.95, 0.98)
    cutout_opacity = float(override.get("cutout_opacity", 0.72))
    enable_opacity = bool(override.get("enable_opacity", True))

    material_sdf_path = Sdf.Path(material_path)
    material = UsdShade.Material.Define(stage, material_sdf_path)
    shader_path = material_sdf_path.AppendChild("Shader")
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath(str(source_asset)), "mdl")
    shader.SetSourceAssetSubIdentifier("OmniGlass", "mdl")
    shader.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*(float(value) for value in glass_color))
    )
    shader.CreateInput("reflection_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*(float(value) for value in reflection_color))
    )
    if enable_opacity:
        shader.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(True)
        shader.CreateInput("cutout_opacity", Sdf.ValueTypeNames.Float).Set(
            cutout_opacity
        )
    shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")

    mesh_prim = stage.GetPrimAtPath(target_mesh)
    if not mesh_prim:
        raise RuntimeError(f"beaker_override_target_missing:{target_mesh}")
    UsdShade.MaterialBindingAPI.Apply(mesh_prim).Bind(material)
    return {
        "enabled": True,
        "beaker_override_used": True,
        "target_mesh": target_mesh,
        "material_path": material_path,
        "shader_path": str(shader_path),
        "mdl_source_asset": str(source_asset),
        "mdl_source_sha256": _sha256_file(source_asset),
        "glass_color": [float(value) for value in glass_color],
        "reflection_color": [float(value) for value in reflection_color],
        "cutout_opacity": cutout_opacity,
        "enable_opacity": enable_opacity,
        "official_visual_a_compatible": False,
    }


def _validate_output_scope(args: argparse.Namespace) -> tuple[Path, Path]:
    out_root = Path(args.out_root).expanduser().resolve()
    manifest_path = (
        Path(args.manifest).expanduser().resolve()
        if args.manifest
        else out_root / "replay_manifest.json"
    )
    if out_root == Path(out_root.anchor) or out_root == Path.cwd().resolve():
        raise ValueError(f"out_root_not_run_scoped:{out_root}")
    protected = {
        Path(args.accepted_summary).expanduser().resolve(),
    }
    if out_root in protected or manifest_path in protected:
        raise ValueError("output_path_overlaps_accepted_input")
    if out_root.exists() and any(out_root.iterdir()):
        raise ValueError(f"out_root_must_be_empty_or_absent:{out_root}")
    if manifest_path.exists():
        raise ValueError(f"manifest_already_exists:{manifest_path}")
    return out_root, manifest_path


def build_dry_plan(args: argparse.Namespace) -> dict[str, Any]:
    candidate_ids = _parse_candidate_ids(args.candidates)
    formulas = {
        "OMNI_REF_FINE": "clamp(interior_diameter/32,0.0015,0.0020)",
        "OMNI_REF_RATIO_15": "interior_diameter/15",
        "OMNI_REF_RATIO_12": "interior_diameter/12",
    }
    return {
        "mode": "real_beaker_omniglass_reference_dry_plan",
        "accepted_summary": args.accepted_summary,
        "accepted_summary_read": False,
        "trace_read": False,
        "isaac_runtime_imported": False,
        "simulation_app_started": False,
        "physics_steps_planned": 0,
        "timeline_play_planned": False,
        "candidate_ids": list(candidate_ids),
        "candidate_contracts": {
            candidate_id: {
                "candidate_id": candidate_id,
                "width_formula": formulas[candidate_id],
                "voxel_size_formula": "display_width",
                "proxy_mode": "deterministic_canonical_voxel_centroid",
                "presentation_points_type": "UsdGeom.Points",
                "physx_api_applied": False,
                "cameras": ["context", "source_beaker_closeup"],
            }
            for candidate_id in candidate_ids
        },
        "out_root": str(Path(args.out_root).expanduser().resolve()),
        "manifest": str(
            Path(args.manifest).expanduser().resolve()
            if args.manifest
            else Path(args.out_root).expanduser().resolve() / "replay_manifest.json"
        ),
    }


def _open_exact_stage(
    *,
    context: Any,
    app: Any,
    timeline: Any,
    source_path: Path,
    warmup_updates: int,
) -> Any:
    opened = bool(context.open_stage(str(source_path)))
    stage = context.get_stage()
    updates = 0
    while stage is None and updates < max(1, warmup_updates):
        require_stopped_timeline(timeline)
        app.update()
        updates += 1
        stage = context.get_stage()
    if not opened or stage is None:
        raise RuntimeError(f"open_exact_accepted_source_failed:{source_path}")
    root_real_path = Path(stage.GetRootLayer().realPath).resolve()
    if root_real_path != source_path.resolve():
        raise RuntimeError(
            f"opened_source_path_mismatch:{root_real_path}!={source_path}"
        )
    stage.Reload()
    reloaded_root_path = Path(stage.GetRootLayer().realPath).resolve()
    if reloaded_root_path != source_path.resolve():
        raise RuntimeError(
            f"reloaded_source_path_mismatch:{reloaded_root_path}!={source_path}"
        )
    return stage


def _render_validated_replay(
    args: argparse.Namespace,
    accepted: AcceptedReplayInput,
    contracts: Mapping[str, Mapping[str, Any]],
    *,
    app: Any,
    out_root: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    import carb
    import omni.kit.app
    import omni.physx.bindings._physx as pb
    import omni.timeline
    import omni.usd

    from tools.labutopia_fluid import (
        run_colleague_native_usd_completed_pbd_step_video as native,
    )
    from tools.labutopia_fluid.presentation_look_profiles import (
        PRESENTATION_LOOK_WEEKLY_B,
        REF_OMNIGLASS_GLASS_COLOR,
        REF_OMNIGLASS_REFLECTION_COLOR,
        resolve_presentation_look_profile,
    )
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    out_root.mkdir(parents=True, exist_ok=True)
    settings = carb.settings.get_settings()
    render_settings = native.apply_presentation_render_settings(settings)
    settings.set(pb.SETTING_DISPLAY_PARTICLES, native._physx_visualizer_mode_none(pb))
    closure = _mirror_version_matched_mdl_closure(native, artifact_dir=out_root)
    omniglass_source = Path(closure["closure_base_dir"]) / "OmniGlass.mdl"
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    require_stopped_timeline(timeline)
    profile = resolve_presentation_look_profile(PRESENTATION_LOOK_WEEKLY_B)
    completed: dict[str, dict[str, Any]] = {}

    for candidate_id in REFERENCE_CANDIDATE_IDS:
        contract = deepcopy(dict(contracts[candidate_id]))
        candidate_dir = out_root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=False)
        stage = _open_exact_stage(
            context=context,
            app=app,
            timeline=timeline,
            source_path=accepted.source_usd_path,
            warmup_updates=args.warmup_updates,
        )
        derived_frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker2",
            visual_mesh_path="/World/beaker2/mesh",
            calibration_points_path="/World/ParticleSet",
        )
        if not _same_frame_core(accepted.frame, derived_frame):
            raise RuntimeError("opened_source_cup_frame_mismatch")
        material_retarget = native._retarget_stage_mdl_source_assets(stage, closure)
        material = native._author_omniglass_presentation_water_material(
            stage,
            glass_color=REF_OMNIGLASS_GLASS_COLOR,
            reflection_color=REF_OMNIGLASS_REFLECTION_COLOR,
            mdl_source_asset=omniglass_source,
            closure_base_dir=closure["closure_base_dir"],
        )
        beaker_override = _author_version_matched_beaker_override(
            stage,
            profile=profile,
            mdl_source_asset=omniglass_source,
        )
        lighting = native._author_liquid_presentation_lighting(stage, profile)
        config = SimpleNamespace(**accepted.summary["region_config"])
        context_camera = native._define_liquid_presentation_camera(
            stage, config, profile
        )
        closeup_camera = native._define_closeup_camera(stage, config)
        authored_state = author_static_candidate_state(
            stage,
            accepted=accepted,
            candidate_contract=contract,
            material_path=material["material_path"],
        )
        context_sensor = native._make_positioned_camera_sensor(
            context_camera["camera_path"],
            name=f"{candidate_id}_context_camera",
            width=args.width,
            height=args.height,
            eye=context_camera["eye"],
            target=context_camera["target"],
            up=context_camera["up"],
        )
        closeup_sensor = native._make_positioned_camera_sensor(
            closeup_camera["camera_path"],
            name=f"{candidate_id}_closeup_camera",
            width=args.width,
            height=args.height,
            eye=closeup_camera["eye"],
            target=closeup_camera["target"],
            up=closeup_camera["up"],
        )
        if context_sensor is None or closeup_sensor is None:
            raise RuntimeError("omniglass_replay_camera_initialization_failed")
        for _ in range(args.camera_warmup_updates):
            require_stopped_timeline(timeline)
            app.update()

        context_dir = candidate_dir / "context_frames"
        closeup_dir = candidate_dir / "source_beaker_closeup_frames"
        context_paths: list[Path] = []
        closeup_paths: list[Path] = []
        camera_diagnostics: dict[str, Any] = {}
        for frame_offset, record in enumerate(accepted.records):
            proxy = accepted.proxy_frame(candidate_id, frame_offset=frame_offset)
            _set_presentation_frame(stage, proxy)
            require_stopped_timeline(timeline)
            app.update()
            frame_index = int(record["step_index"])
            for role, sensor, directory, paths in (
                ("context", context_sensor, context_dir, context_paths),
                ("source_beaker_closeup", closeup_sensor, closeup_dir, closeup_paths),
            ):
                frame_path = directory / f"frame_{frame_index:04d}.png"
                source, diagnostics = native._try_write_camera_png_with_diagnostics(
                    sensor, frame_path
                )
                camera_diagnostics[str(frame_path.relative_to(candidate_dir))] = (
                    diagnostics
                )
                if source is None or not frame_path.is_file():
                    raise RuntimeError(
                        f"omniglass_replay_image_capture_failed:{candidate_id}:{role}:{frame_index}"
                    )
                paths.append(frame_path)

        final_proxy = accepted.proxy_frame(candidate_id, frame_offset=-1)
        _set_presentation_frame(stage, final_proxy)
        static_usd = candidate_dir / f"{candidate_id}_static.usda"
        if not stage.GetRootLayer().Export(str(static_usd)):
            raise RuntimeError(f"static_candidate_export_failed:{static_usd}")
        context_video = candidate_dir / "context.mp4"
        closeup_video = candidate_dir / "source_beaker_closeup.mp4"
        if not native._write_mp4_from_frames(
            context_paths, context_video, fps=args.video_fps
        ) or not native._write_mp4_from_frames(
            closeup_paths, closeup_video, fps=args.video_fps
        ):
            raise RuntimeError(f"omniglass_replay_video_encode_failed:{candidate_id}")

        contract.update(
            {
                "generated_at_utc": _utc_now(),
                "material": material,
                "material_retarget": material_retarget,
                "material_closure": closure,
                "version_matched_mdl_source": {
                    "source_root": closure["source_root"],
                    "runtime_prefix": closure["runtime_prefix"],
                    "runtime_version": closure["runtime_version"],
                    "source_root_under_runtime_prefix": closure[
                        "source_root_under_runtime_prefix"
                    ],
                    "required_file_sha256": closure["required_file_sha256"],
                    "source_file_sha256": closure["source_file_sha256"],
                    "source_tree_sha256": closure["source_tree_sha256"],
                },
                "beaker_override": beaker_override,
                "lighting": lighting,
                "render_settings": render_settings,
                "context_camera": context_camera,
                "source_beaker_closeup_camera": closeup_camera,
                "camera_capture_diagnostics": camera_diagnostics,
                "static_stage_authoring": authored_state,
            }
        )
        finalized = finalize_candidate_manifest(
            contract,
            candidate_dir=candidate_dir,
            static_usd_path=static_usd,
            closeup_image_paths=closeup_paths,
            context_image_paths=context_paths,
            video_paths=[context_video, closeup_video],
        )
        candidate_manifest_path = candidate_dir / "candidate_manifest.json"
        atomic_write_json(candidate_manifest_path, finalized)
        finalized["candidate_manifest_path"] = str(candidate_manifest_path)
        finalized["candidate_manifest_sha256"] = _sha256_file(candidate_manifest_path)
        completed[candidate_id] = finalized

    source_hash_after = _sha256_file(accepted.source_usd_path)
    if source_hash_after != accepted.physical_trace_identity["source_usd_sha256"]:
        raise RuntimeError("accepted_source_usd_changed_during_replay")
    identities = [item["input_identity"] for item in completed.values()]
    if any(identity != accepted.physical_trace_identity for identity in identities):
        raise RuntimeError("candidate_manifest_input_identity_diverged")
    top_manifest = {
        "schema_version": 1,
        "manifest_type": "real_beaker_omniglass_reference_replay",
        "generated_at_utc": _utc_now(),
        "classification": "RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
        "accepted_summary_path": str(accepted.summary_path),
        "accepted_trace_path": str(accepted.trace_path),
        "source_usd_path": str(accepted.source_usd_path),
        "source_usd_sha256": source_hash_after,
        "physical_trace_identity": deepcopy(accepted.physical_trace_identity),
        "candidate_ids": list(REFERENCE_CANDIDATE_IDS),
        "candidate_manifests": completed,
        "all_candidate_input_identities_equal": True,
        "runtime_contract": {
            "exact_source_opened_for_every_candidate": True,
            "physics_steps_executed": 0,
            "timeline_play_called": False,
            "physical_and_debug_points_hidden": True,
        },
        "render_artifacts_complete": True,
        "visual_review_verdict": "PENDING_INDEPENDENT_REVIEW",
        "omniglass_reference_particle_look_selected": False,
    }
    scoped_manifest = out_root / "replay_manifest.json"
    atomic_write_json(scoped_manifest, top_manifest)
    if manifest_path != scoped_manifest:
        atomic_write_json(manifest_path, top_manifest)
    return top_manifest


def _run_runtime(
    args: argparse.Namespace,
    accepted: AcceptedReplayInput,
    contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    from isaacsim import SimulationApp

    out_root = Path(args._resolved_out_root)
    manifest_path = Path(args._resolved_manifest)
    app = SimulationApp(
        {
            "headless": bool(args.headless),
            "width": int(args.width),
            "height": int(args.height),
        }
    )
    try:
        return _render_validated_replay(
            args,
            accepted,
            contracts,
            app=app,
            out_root=out_root,
            manifest_path=manifest_path,
        )
    except Exception as exc:  # pragma: no cover - Isaac runtime only.
        failure = {
            "schema_version": 1,
            "manifest_type": "real_beaker_omniglass_reference_replay",
            "generated_at_utc": _utc_now(),
            "classification": "STOP_RUNTIME_ERROR",
            "fatal_error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=30),
            },
            "physical_trace_identity": deepcopy(accepted.physical_trace_identity),
            "render_artifacts_complete": False,
            "visual_review_verdict": "NOT_RUN",
            "omniglass_reference_particle_look_selected": False,
            "runtime_contract": {
                "physics_steps_executed": 0,
                "timeline_play_called": False,
            },
        }
        out_root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(out_root / "replay_failure.json", failure)
        atomic_write_json(manifest_path, failure)
        return failure
    finally:
        app.close()


def run_replay(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.dry_plan):
        raise ValueError("run_replay_does_not_execute_dry_plan")
    candidate_ids = _parse_candidate_ids(args.candidates)
    accepted = load_and_validate_accepted_replay(args.accepted_summary)
    contracts = build_candidate_replay_contracts(accepted, candidate_ids)
    out_root, manifest_path = _validate_output_scope(args)
    args._resolved_out_root = str(out_root)
    args._resolved_manifest = str(manifest_path)
    return _run_runtime(args, accepted, contracts)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-summary", required=True)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES)
    parser.add_argument("--dry-plan", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--video-fps", type=float, default=15.0)
    parser.add_argument("--warmup-updates", type=int, default=8)
    parser.add_argument("--camera-warmup-updates", type=int, default=8)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.dry_plan:
        print(json.dumps(build_dry_plan(args), indent=2))
        return 0
    result = run_replay(args)
    print(json.dumps(result, indent=2))
    return (
        0
        if result.get("classification") == "RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

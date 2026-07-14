#!/usr/bin/env python3
"""Run the final graph-owned isosurface probe from accepted frame 600."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import traceback
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AUTHORITY_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712"
    / "accepted_authority_P4096_S2"
)
ACCEPTED_TRACE = (
    AUTHORITY_ROOT / "runtime_evidence_snapshot/particle_readback_trace.jsonl"
)
ACCEPTED_SUMMARY = (
    AUTHORITY_ROOT / "runtime_evidence_snapshot/runtime_smoke_summary.json"
)
SOURCE_STAGE = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008"
    / "matrix_decision_authority/final_closure/aggregate/cells"
    / "A_0_AO0_RT4_CONTROL/OMNI_REF_DISPLAY_FILL"
    / "OMNI_REF_DISPLAY_FILL_static.usda"
)
MATERIAL_CLOSURE_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008"
    / "matrix_decision_authority/final_closure/aggregate/cells"
    / "A_0_AO0_RT4_CONTROL/material_closure_isaacsim41_conda_core"
)
MDL_SOURCE_ASSET = MATERIAL_CLOSURE_ROOT / "Base/OmniSurfacePresets.mdl"
OUTPUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_isosurface_graph_owned_final_probe_20260713"
)

PROBE_ID = "real_beaker_isosurface_graph_owned_final_probe_20260713"
SUCCESS_STATUS = "CAPTURED_GRAPH_OWNED_ISOSURFACE_PENDING_VISUAL_REVIEW"
FAILURE_STATUS = "INVALID_GRAPH_OWNED_ISOSURFACE_PROBE"
INITIALIZATION_DT = 1.0 / 600.0
LEGACY_GRAPH_SYNC_UPDATES = 5
CLAIM_BOUNDARY = (
    "accepted_frame_600_positions_are_parent_authority;"
    "single_zero_velocity_init_step_state_is_presentation_only;"
    "not_frame_601;no_new_physics_authority"
)

EXPECTED_AUTHORITY_BUNDLE_SHA256 = (
    "edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605"
)
EXPECTED_TRACE_SHA256 = (
    "24d75adf7c5120760c127aafc29886a193a5eb288c913828dba33819da4e28d2"
)
EXPECTED_FINAL_POSITIONS_SHA256 = (
    "8a1942e82b21d470fe873570bbfcc9056de813a7427e6e1293c5ceac12ab0033"
)
EXPECTED_SOURCE_SHA256 = (
    "c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a"
)
EXPECTED_MDL_SOURCE_SHA256 = (
    "5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930"
)
EXPECTED_FINAL_STEP = 600
EXPECTED_PARTICLE_COUNT = 4096

RUNTIME_PBD_SCOPE_PATH = "/World/CompletedPBD"
RUNTIME_PARTICLE_SYSTEM_PATH = f"{RUNTIME_PBD_SCOPE_PATH}/ParticleSystem"
RUNTIME_PARTICLE_SET_PATH = f"{RUNTIME_PBD_SCOPE_PATH}/ParticleSet"
LEGACY_PARTICLE_SYSTEM_PATH = "/World/ParticleSystem"
PRESENTATION_SURFACE_PATH = f"{RUNTIME_PBD_SCOPE_PATH}/PresentationSurface"
TREATMENT_MATERIAL_PATH = "/World/Looks/LiquidPresentationWater"
MDL_SUB_IDENTIFIER = "OmniSurface_ClearWater"

CAMERA_PATHS = (
    "context",
    "source_beaker_closeup",
    "native_table_context",
)
CAMERA_PRIMS = {
    "context": "/World/BeakerPairContextCamera",
    "source_beaker_closeup": "/World/Beaker2CloseupNativeMaterialCamera",
    "native_table_context": "/World/Camera1",
}
CAPTURE_RESOLUTION = (960, 540)
RT_SUBFRAMES = 4
WARMUP_UPDATES = 8

TECHNICAL_GATES = (
    "authority",
    "legacy_graph_setup",
    "strict_physics_scene",
    "operation_order",
    "authored_positions",
    "authored_zero_velocities",
    "single_initialization_step",
    "post_step_presentation_containment",
    "isosurface_bridge",
    "clearwater_material",
    "capture",
    "log",
    "source_integrity",
)

EXPECTED_OPERATION_ORDER = (
    "register_step_counter",
    "remove_legacy_particle_sampling_api",
    "deactivate_original_fluid_prims",
    "synchronize_legacy_particle_graph",
    "configure_physics_scene",
    "author_runtime_particles",
    "verify_second_deactivation",
    "attach_stepper",
    "single_initialization_step",
)

SINGLE_STEP_CHECKPOINT_NAMES = (
    "before_attach",
    "after_attach",
    "after_initialization",
    *(f"warmup_update_{index}" for index in range(1, WARMUP_UPDATES + 1)),
    "after_warmup",
    "after_discarded_capture",
    "after_final_capture",
    "after_detach",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable_positions(
    positions: Sequence[Sequence[float]],
) -> list[list[float]]:
    result: list[list[float]] = []
    for index, point in enumerate(positions):
        if len(point) != 3:
            raise ValueError(f"position_shape_invalid:{index}")
        values = [float(point[0]), float(point[1]), float(point[2])]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"position_nonfinite:{index}")
        result.append(values)
    return result


def positions_sha256(positions: Sequence[Sequence[float]]) -> str:
    payload = json.dumps(
        _jsonable_positions(positions),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_accepted_final_record(
    trace_path: Path = ACCEPTED_TRACE,
    *,
    expected_sha256: str = EXPECTED_TRACE_SHA256,
) -> dict[str, Any]:
    path = trace_path.resolve(strict=True)
    payload = path.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("accepted_trace_sha256_mismatch")
    if not payload.endswith(b"\n"):
        raise ValueError("accepted_trace_not_newline_terminated")
    records = []
    for line_number, raw_line in enumerate(payload.splitlines(), start=1):
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"accepted_trace_json_invalid:{line_number}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"accepted_trace_record_invalid:{line_number}")
        records.append(record)
    matches = [
        record
        for record in records
        if record.get("step_index") == EXPECTED_FINAL_STEP
    ]
    if len(matches) != 1:
        raise ValueError("accepted_final_step_missing")
    record = dict(matches[0])
    positions = _jsonable_positions(record.get("positions") or [])
    if record.get("particle_count") != EXPECTED_PARTICLE_COUNT or len(
        positions
    ) != EXPECTED_PARTICLE_COUNT:
        raise ValueError("accepted_final_particle_count_mismatch")
    strict_counts = record.get("strict_visible_beaker_counts")
    if not isinstance(strict_counts, Mapping) or (
        strict_counts.get("particle_count") != EXPECTED_PARTICLE_COUNT
        or strict_counts.get("finite_count") != EXPECTED_PARTICLE_COUNT
        or strict_counts.get("inside_visible_interior_count")
        != EXPECTED_PARTICLE_COUNT
        or strict_counts.get("strict_violating_point_count") != 0
    ):
        raise ValueError("accepted_final_containment_mismatch")
    position_digest = positions_sha256(positions)
    if position_digest != EXPECTED_FINAL_POSITIONS_SHA256:
        raise ValueError("accepted_final_positions_sha256_mismatch")
    return {
        **record,
        "positions": positions,
        "trace_path": str(path),
        "trace_sha256": actual_sha256,
        "positions_sha256": position_digest,
    }


def build_fixed_isosurface_contract() -> dict[str, Any]:
    fluid_rest_offset = 0.000264627
    return {
        "particle_width": 0.00045,
        "particle_contact_offset": 0.000529254,
        "particle_system_contact_offset": 0.000793881,
        "solid_rest_offset": 0.0004455,
        "fluid_rest_offset": fluid_rest_offset,
        "grid_spacing": fluid_rest_offset * 0.9,
        "surface_distance": fluid_rest_offset * 0.95,
        "grid_smoothing_radius": fluid_rest_offset,
        "mesh_smoothing_passes": 4,
        "normal_smoothing_passes": 4,
        "anisotropy": {"scale": 5.0, "min": 1.0, "max": 2.0},
        "smoothing_strength": 0.5,
        "initialization_integration_steps": 1,
        "initialization_dt": INITIALIZATION_DT,
    }


def create_disposable_wrapper_layer(
    source_path: Path,
    wrapper_path: Path,
) -> dict[str, Any]:
    from pxr import Sdf

    source = source_path.resolve(strict=True)
    wrapper = wrapper_path.resolve()
    if source == wrapper or wrapper.exists():
        raise ValueError("disposable_wrapper_path_invalid")
    source_sha256 = _sha256_file(source)
    layer = Sdf.Layer.CreateNew(str(wrapper))
    if layer is None:
        raise RuntimeError("disposable_wrapper_create_failed")
    layer.subLayerPaths = [str(source)]
    if not layer.Save():
        raise RuntimeError("disposable_wrapper_save_failed")
    if _sha256_file(source) != source_sha256:
        raise RuntimeError("disposable_wrapper_changed_source")
    return {
        "source_path": str(source),
        "source_sha256": source_sha256,
        "wrapper_path": str(wrapper),
        "wrapper_sha256": _sha256_file(wrapper),
        "source_is_sublayer": list(layer.subLayerPaths) == [str(source)],
    }


def validate_authored_positions(
    actual: Sequence[Sequence[float]],
    expected: Sequence[Sequence[float]],
) -> dict[str, Any]:
    actual_values = _jsonable_positions(actual)
    expected_values = _jsonable_positions(expected)
    if actual_values != expected_values:
        raise ValueError("authored_positions_mismatch")
    return {
        "exact_ordered_match": True,
        "particle_count": len(actual_values),
        "positions_sha256": positions_sha256(actual_values),
    }


def validate_authored_zero_velocities(
    velocities: Sequence[Sequence[float]],
    *,
    expected_count: int = EXPECTED_PARTICLE_COUNT,
) -> dict[str, Any]:
    if len(velocities) != expected_count:
        raise ValueError("authored_velocity_count_mismatch")
    for index, velocity in enumerate(velocities):
        if len(velocity) != 3:
            raise ValueError(f"authored_velocity_shape_invalid:{index}")
        values = [float(value) for value in velocity]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"authored_velocity_nonfinite:{index}")
        if any(value != 0.0 for value in values):
            raise ValueError(f"authored_velocity_nonzero:{index}")
    return {
        "particle_count": expected_count,
        "all_finite": True,
        "all_zero": True,
    }


def validate_legacy_graph_setup(
    sampler_removal: Mapping[str, Any],
    isolation_summary: Mapping[str, Any],
    checkpoints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ownership = isolation_summary.get("ownership_isolation")
    old_system_summary = isolation_summary.get(LEGACY_PARTICLE_SYSTEM_PATH)
    disabled_old_system = bool(
        isinstance(old_system_summary, Mapping)
        and isinstance(old_system_summary.get("disabled_attrs"), Mapping)
        and old_system_summary["disabled_attrs"].get("particleSystemEnabled")
        is False
    )
    checkpoint_names = (
        "before_legacy_graph_setup",
        "after_legacy_graph_setup",
    )
    checkpoints_valid = tuple(checkpoints) == checkpoint_names and all(
        isinstance(checkpoints[name], Mapping)
        and checkpoints[name].get("physics_step_events") == 0
        and checkpoints[name].get("timeline_stopped") is True
        for name in checkpoint_names
    )
    valid = bool(
        isinstance(sampler_removal, Mapping)
        and sampler_removal.get("api_present_after") is False
        and sampler_removal.get("verified") is True
        and isinstance(ownership, Mapping)
        and ownership.get("verified") is True
        and ownership.get("sampler_targets_after") == []
        and ownership.get("particle_set_targets_after") == []
        and type(ownership.get("synchronization_required")) is bool
        and ownership.get("synchronization_updates")
        == LEGACY_GRAPH_SYNC_UPDATES
        and ownership.get("synchronization_verified") is True
        and disabled_old_system
        and checkpoints_valid
    )
    if not valid:
        raise RuntimeError("legacy_graph_setup_invalid")
    return {
        "verified": True,
        "synchronization_required": ownership["synchronization_required"],
        "synchronization_updates": ownership["synchronization_updates"],
        "checkpoints": {
            name: dict(checkpoints[name]) for name in checkpoint_names
        },
    }


def validate_second_deactivation(
    isolation_summary: Mapping[str, Any],
) -> dict[str, Any]:
    ownership = isolation_summary.get("ownership_isolation")
    valid = bool(
        isinstance(ownership, Mapping)
        and ownership.get("verified") is True
        and ownership.get("sampler_targets_after") == []
        and ownership.get("particle_set_targets_after") == []
        and ownership.get("synchronization_required") is False
    )
    if not valid:
        raise RuntimeError("second_deactivation_invalid")
    return {
        "verified": True,
        "synchronization_required": False,
        "sampler_targets_after": [],
        "particle_set_targets_after": [],
    }


def validate_strict_physics_scene(
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    valid = bool(
        summary.get("physics_scene_path") == "/World/PhysicsScene"
        and summary.get("gpu_dynamics_enabled") is True
        and summary.get("broadphase_type") == "GPU"
        and summary.get("solver_type") == "TGS"
        and summary.get("time_steps_per_second") == 600
        and math.isclose(
            float(summary.get("effective_physics_dt", math.nan)),
            INITIALIZATION_DT,
            rel_tol=0.0,
            abs_tol=1e-15,
        )
        and summary.get("time_steps_per_second_authored") is True
        and summary.get("strict_timestep_verified") is True
    )
    if not valid:
        raise RuntimeError("strict_physics_scene_invalid")
    return {**dict(summary), "verified": True}


def validate_operation_ledger(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    operations = tuple(record.get("operation") for record in records)
    valid = operations == EXPECTED_OPERATION_ORDER and all(
        isinstance(record, Mapping)
        and record.get("timeline_stopped") is True
        and record.get("physics_step_events")
        == (1 if operation == "single_initialization_step" else 0)
        for operation, record in zip(EXPECTED_OPERATION_ORDER, records)
    )
    if not valid:
        raise RuntimeError("operation_ledger_invalid")
    return {
        "verified": True,
        "operations": list(operations),
        "records": [dict(record) for record in records],
    }


def validate_single_step_checkpoints(
    checkpoints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if tuple(checkpoints) != SINGLE_STEP_CHECKPOINT_NAMES:
        raise RuntimeError("single_step_checkpoint_invalid:names")
    for index, name in enumerate(SINGLE_STEP_CHECKPOINT_NAMES):
        record = checkpoints[name]
        expected_steps = 0 if index < 2 else 1
        if (
            not isinstance(record, Mapping)
            or record.get("physics_step_events") != expected_steps
            or record.get("timeline_stopped") is not True
        ):
            raise RuntimeError(f"single_step_checkpoint_invalid:{name}")
    return {
        "single_initialization_step_verified": True,
        "physics_steps_executed": 1,
        "checkpoints": {name: dict(checkpoints[name]) for name in checkpoints},
    }


def validate_single_step_lifecycle_summary(
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    valid = bool(
        summary.get("requested_logical_steps") == 1
        and summary.get("executed_logical_steps") == 1
        and summary.get("requested_integration_steps") == 1
        and summary.get("executed_integration_steps") == 1
        and summary.get("simulate_fetch_pair_count") == 1
        and math.isclose(
            float(summary.get("simulated_seconds", math.nan)),
            INITIALIZATION_DT,
            rel_tol=0.0,
            abs_tol=1e-15,
        )
        and summary.get("exact_logical_step_count_verified") is True
        and summary.get("exact_integration_step_count_verified") is True
        and summary.get("exact_step_count_verified") is True
        and summary.get("ordered_lifecycle_verified") is True
        and summary.get("attach_verified") is True
        and summary.get("detach_verified") is True
    )
    if not valid:
        raise RuntimeError("single_step_lifecycle_invalid")
    return {**dict(summary), "verified": True}


def validate_post_step_presentation_readback(
    positions: Sequence[Sequence[float]],
    strict_counts: Mapping[str, Any],
    *,
    violating_indices: Sequence[int],
    expected_count: int = EXPECTED_PARTICLE_COUNT,
) -> dict[str, Any]:
    values = _jsonable_positions(positions)
    indices = [int(index) for index in violating_indices]
    valid_counts = bool(
        len(values) == expected_count
        and strict_counts.get("particle_count") == expected_count
        and strict_counts.get("finite_count") == expected_count
        and strict_counts.get("nonfinite_count") == 0
        and strict_counts.get("inside_visible_interior_count") == expected_count
        and strict_counts.get("strict_violating_point_count") == 0
        and not indices
    )
    if not valid_counts:
        raise ValueError("post_step_presentation_containment_failed")
    columns = list(zip(*values))
    return {
        "presentation_state_only": True,
        "particle_count": expected_count,
        "positions_sha256": positions_sha256(values),
        "aabb": {
            "min": [min(column) for column in columns],
            "max": [max(column) for column in columns],
        },
        "strict_visible_beaker_counts": dict(strict_counts),
        "violating_indices": indices,
    }


def validate_runtime_isosurface_bridge(
    summary: Mapping[str, Any],
    *,
    particle_system_path: str,
) -> dict[str, Any]:
    expected_path = f"{particle_system_path}/Isosurface"
    point_count = summary.get("usd_point_count")
    face_count = summary.get("usd_face_count")
    populated = bool(
        isinstance(point_count, int)
        and isinstance(face_count, int)
        and (point_count > 1 or face_count > 1)
    )
    valid_hash = (
        isinstance(summary.get("mdl_source_asset_sha256"), str)
        and summary["mdl_source_asset_sha256"] == EXPECTED_MDL_SOURCE_SHA256
    )
    if (
        summary.get("path") != expected_path
        or summary.get("prim_exists") is not True
        or summary.get("type_name") != "Mesh"
        or type(point_count) is not int
        or point_count < 0
        or type(face_count) is not int
        or face_count < 0
        or summary.get("bound_material_path") != TREATMENT_MATERIAL_PATH
        or not valid_hash
        or summary.get("mdl_sub_identifier") != MDL_SUB_IDENTIFIER
        or summary.get("preview_fallback_used") is not False
        or (populated and summary.get("usd_points_finite") is not True)
    ):
        raise ValueError("runtime_isosurface_bridge_invalid")
    geometry_classification = (
        "USD_BRIDGE_POPULATED" if populated else "USD_BRIDGE_PLACEHOLDER"
    )
    return {
        **dict(summary),
        "verified": True,
        "usd_geometry_classification": geometry_classification,
    }


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def validate_camera_capture_contract(
    capture: Mapping[str, Any],
) -> dict[str, Any]:
    frames = capture.get("frames")
    valid = isinstance(frames, Mapping) and set(frames) == set(CAMERA_PATHS)
    if valid:
        for role in CAMERA_PATHS:
            frame = frames[role]
            shape = frame.get("shape") if isinstance(frame, Mapping) else None
            valid = bool(
                isinstance(shape, list)
                and len(shape) == 3
                and shape[0] == CAPTURE_RESOLUTION[1]
                and shape[1] == CAPTURE_RESOLUTION[0]
                and shape[2] >= 3
                and frame.get("dtype") == "uint8"
                and isinstance(frame.get("mean"), (int, float))
                and float(frame["mean"]) >= 5.0
                and isinstance(frame.get("std"), (int, float))
                and float(frame["std"]) >= 2.0
                and _valid_sha256(frame.get("sha256"))
                and isinstance(frame.get("path"), str)
                and frame["path"]
            )
            if not valid:
                break
    if not valid:
        raise ValueError("camera_capture_contract_invalid")
    return {
        "verified": True,
        "camera_roles": list(CAMERA_PATHS),
        "resolution": list(CAPTURE_RESOLUTION),
        "frames": {role: dict(frames[role]) for role in CAMERA_PATHS},
    }


def build_technical_status(gates: Mapping[str, bool]) -> dict[str, Any]:
    failed = [name for name in TECHNICAL_GATES if gates.get(name) is not True]
    valid = not failed
    return {
        "status": (
            SUCCESS_STATUS
            if valid
            else FAILURE_STATUS
        ),
        "failed_gates": failed,
        "technically_valid": valid,
    }


def build_failure_manifest(exc: BaseException) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "status": FAILURE_STATUS,
        "technically_valid": False,
        "fatal_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=30),
        },
    }


def build_discarded_warmup_failure_summary(exc: RuntimeError) -> dict[str, Any]:
    message = str(exc)
    if not message.startswith(
        "static_replicator_capture_near_black_or_flat:context:"
    ):
        raise RuntimeError(f"unexpected_discarded_warmup_failure:{message}") from exc
    return {
        "discarded": True,
        "frame_quality_valid": False,
        "continued_to_strict_final_capture": True,
        "error": message,
    }


def finalize_discarded_warmup_failure_attempt(
    attempt: dict[str, Any],
    exc: RuntimeError,
) -> dict[str, Any]:
    attempt["outcome"] = "failed"
    attempt["error"] = str(exc)
    summary = build_discarded_warmup_failure_summary(exc)
    attempt["outcome"] = "allowed_context_flat_failure"
    return summary


def validate_terminal_capture_failure_context(
    context: Mapping[str, Any],
) -> dict[str, Any]:
    attempts = context.get("capture_attempts")
    final_attempt = attempts[-1] if isinstance(attempts, list) and attempts else None
    single_step = context.get("single_step_validation")
    checkpoints = (
        single_step.get("checkpoints")
        if isinstance(single_step, Mapping)
        else None
    )
    after_final = (
        checkpoints.get("after_final_capture")
        if isinstance(checkpoints, Mapping)
        else None
    )
    after_detach = (
        checkpoints.get("after_detach")
        if isinstance(checkpoints, Mapping)
        else None
    )
    valid = bool(
        isinstance(final_attempt, Mapping)
        and final_attempt.get("kind") == "strict_final"
        and final_attempt.get("predeclared_discard") is False
        and final_attempt.get("outcome") == "failed"
        and isinstance(final_attempt.get("error"), str)
        and final_attempt.get("error")
        and isinstance(context.get("operation_ledger"), Mapping)
        and context["operation_ledger"].get("verified") is True
        and isinstance(single_step, Mapping)
        and single_step.get("single_initialization_step_verified") is True
        and single_step.get("physics_steps_executed") == 1
        and isinstance(after_final, Mapping)
        and after_final.get("physics_step_events") == 1
        and after_final.get("timeline_stopped") is True
        and isinstance(after_detach, Mapping)
        and after_detach.get("physics_step_events") == 1
        and after_detach.get("timeline_stopped") is True
        and isinstance(context.get("single_step_lifecycle"), Mapping)
        and context["single_step_lifecycle"].get("verified") is True
        and context.get("scene_hash_unchanged") is True
        and isinstance(context.get("replicator_cleanup"), Mapping)
        and context["replicator_cleanup"].get("cleanup_complete") is True
        and not context["replicator_cleanup"].get("cleanup_failures")
        and isinstance(context.get("log"), Mapping)
        and context["log"].get("verified") is True
        and isinstance(context.get("source_integrity"), Mapping)
        and context["source_integrity"].get("verified") is True
    )
    if not valid:
        raise RuntimeError("terminal_capture_evidence_invalid")
    return {"verified": True}


def validate_single_step_log_segment(log_text: str) -> dict[str, Any]:
    relevant_keywords = ("physx", "isosurface", "cuda", "hydra", "mdl")
    invalid_lines = []
    for raw_line in str(log_text).splitlines():
        line = raw_line.strip()
        lower = line.lower()
        relevant = any(keyword in lower for keyword in relevant_keywords)
        severe = "[error]" in lower or "[fatal]" in lower
        nonfinite = "non-finite" in lower or "nonfinite" in lower
        if relevant and (severe or nonfinite):
            invalid_lines.append(line)
    if invalid_lines:
        raise RuntimeError(
            "single_step_runtime_log_invalid:"
            + json.dumps(invalid_lines[:20], sort_keys=True)
        )
    return {"verified": True, "relevant_fatal_or_nonfinite_lines": []}


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"nonfinite_float": "nan"}
        if math.isinf(value):
            return {"nonfinite_float": "+inf" if value > 0 else "-inf"}
        return value
    try:
        return [_canonical_value(item) for item in value]
    except TypeError:
        return str(value)


def stable_scene_points_sha256(
    stage: Any,
    *,
    excluded_roots: Sequence[str],
) -> str:
    prims = []
    for prim in stage.TraverseAll():
        path = str(prim.GetPath())
        if any(path == root or path.startswith(f"{root}/") for root in excluded_roots):
            continue
        points = prim.GetAttribute("points")
        if not points:
            continue
        prims.append({"path": path, "points": _canonical_value(points.Get())})
    payload = json.dumps(
        sorted(prims, key=lambda item: item["path"]),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _find_source_layer(stage: Any, source_path: Path) -> Any:
    source = source_path.resolve()
    matches = [
        layer
        for layer in stage.GetUsedLayers()
        if layer.realPath and Path(layer.realPath).resolve() == source
    ]
    if len(matches) != 1:
        raise RuntimeError("pinned_source_layer_not_unique")
    return matches[0]


def _runtime_bridge_summary(stage: Any, particle_system_path: str) -> dict[str, Any]:
    from pxr import UsdGeom, UsdShade

    expected_path = f"{particle_system_path}/Isosurface"
    matches = [
        prim
        for prim in stage.TraverseAll()
        if str(prim.GetPath()) == expected_path and prim.IsA(UsdGeom.Mesh)
    ]
    if len(matches) != 1:
        return {
            "path": expected_path,
            "prim_exists": False,
            "type_name": None,
            "usd_point_count": 0,
            "usd_face_count": 0,
            "usd_points_finite": None,
        }
    prim = matches[0]
    mesh = UsdGeom.Mesh(prim)
    points = mesh.GetPointsAttr().Get() or []
    face_counts = mesh.GetFaceVertexCountsAttr().Get() or []
    material = UsdShade.Material(stage.GetPrimAtPath(TREATMENT_MATERIAL_PATH))
    if not material:
        raise RuntimeError("clearwater_material_missing_before_bridge_binding")
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
    bound_material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    shader = UsdShade.Shader(
        stage.GetPrimAtPath(f"{TREATMENT_MATERIAL_PATH}/Shader")
    )
    source_asset = shader.GetSourceAsset("mdl") if shader else None
    source_path = Path(str(source_asset.resolvedPath or source_asset.path)).resolve()
    return {
        "path": expected_path,
        "prim_exists": True,
        "type_name": prim.GetTypeName(),
        "usd_point_count": len(points),
        "usd_face_count": len(face_counts),
        "usd_points_finite": all(
            all(math.isfinite(float(component)) for component in point)
            for point in points
        ),
        "bound_material_path": (
            str(bound_material.GetPath()) if bound_material else None
        ),
        "mdl_source_asset": str(source_path),
        "mdl_source_asset_sha256": (
            _sha256_file(source_path) if source_path.is_file() else None
        ),
        "mdl_sub_identifier": (
            shader.GetSourceAssetSubIdentifier("mdl") if shader else None
        ),
        "preview_fallback_used": bool(
            stage.GetPrimAtPath(f"{TREATMENT_MATERIAL_PATH}/PreviewSurface")
        ),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(path)
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False, indent=2, sort_keys=True)
            stream.write("\n")
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _run_runtime(source_path: Path, out_root: Path) -> dict[str, Any]:
    from tools.labutopia_fluid import run_build_support_aligned_authority_bundle
    from tools.labutopia_fluid import run_real_beaker_clearwater_mdl_probe as clearwater

    authority = run_build_support_aligned_authority_bundle._validate_final_bundle(
        AUTHORITY_ROOT
    )
    if (
        authority.get("accepted_authority_bundle_sha256")
        != EXPECTED_AUTHORITY_BUNDLE_SHA256
    ):
        raise ValueError("authority_bundle_sha256_mismatch")
    final_record = load_accepted_final_record()
    fixed_contract = build_fixed_isosurface_contract()
    mdl_input = clearwater.verify_clearwater_mdl_input()
    source = source_path.resolve(strict=True)
    if _sha256_file(source) != EXPECTED_SOURCE_SHA256:
        raise ValueError("fixed_source_sha256_mismatch")
    out_root.mkdir(parents=True, exist_ok=False)
    search_contract = clearwater.build_mdl_search_contract()
    for argument in (
        search_contract["startup_arguments"]
        + clearwater._control_render_startup_arguments()
    ):
        if argument not in sys.argv:
            sys.argv.append(argument)

    from isaacsim import SimulationApp

    app = SimulationApp(
        {
            "headless": True,
            "width": CAPTURE_RESOLUTION[0],
            "height": CAPTURE_RESOLUTION[1],
            "renderer": "RayTracedLighting",
        }
    )
    resources: dict[str, dict[str, Any]] = {}
    stepper: Any = None
    step_subscription: Any = None
    failure_context: dict[str, Any] = {}
    try:
        import carb
        import omni.kit.commands
        import omni.physx
        import omni.physx.bindings._physx as pb
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from pxr import UsdGeom, UsdUtils
        from tools.labutopia_fluid import (
            run_colleague_native_usd_completed_pbd_step_video as native,
        )
        from tools.labutopia_fluid import (
            run_real_beaker_omniglass_replay as replay,
        )
        from tools.labutopia_fluid.real_beaker import (
            classify_visible_beaker_positions,
            derive_cup_interior_frame,
        )

        settings = carb.settings.get_settings()
        settings.set_bool("/app/player/playSimulations", False)
        settings.set_bool("/omni/replicator/captureOnPlay", False)
        rep.orchestrator.set_capture_on_play(False)
        settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
        settings.set_bool("/physics/suppressReadback", False)
        settings.set(pb.SETTING_UPDATE_TO_USD, True)
        settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
        settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
        settings.set(pb.SETTING_DISPLAY_PARTICLES, native._physx_visualizer_mode_none(pb))
        mdl_search = clearwater.validate_mdl_search_readback(
            settings, search_contract
        )
        render_contract = clearwater._apply_control_render_settings(
            settings, app.update
        )

        wrapper_path = out_root / "accepted_final_isosurface_wrapper.usda"
        wrapper_contract = create_disposable_wrapper_layer(source, wrapper_path)
        wrapper_sha256_before = _sha256_file(wrapper_path)
        source_sha256_before = _sha256_file(source)
        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        replay.require_stopped_timeline(timeline)
        stage = replay._open_exact_stage(
            context=omni.usd.get_context(),
            app=app,
            timeline=timeline,
            source_path=wrapper_path,
            warmup_updates=2,
        )
        source_layer = _find_source_layer(stage, source)
        if source_layer.dirty:
            raise RuntimeError("pinned_source_layer_dirty_at_open")
        for camera_path in CAMERA_PRIMS.values():
            camera = stage.GetPrimAtPath(camera_path)
            if not camera or not camera.IsA(UsdGeom.Camera):
                raise RuntimeError(f"fixed_camera_missing:{camera_path}")
        cup_interior_frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker2",
            visual_mesh_path="/World/beaker2/mesh",
            calibration_points_path=native.EVIDENCE_PARTICLE_SET_PATH,
        )
        old_proxy = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
        if not old_proxy:
            raise RuntimeError("old_presentation_proxy_missing")
        UsdGeom.Imageable(old_proxy).MakeInvisible()

        physics_step_count = 0

        def on_physics_step(_dt: float) -> None:
            nonlocal physics_step_count
            physics_step_count += 1

        step_checkpoints: dict[str, dict[str, Any]] = {}

        def record_step_checkpoint(name: str, *, expected_steps: int) -> None:
            replay.require_stopped_timeline(timeline)
            if physics_step_count != expected_steps:
                raise RuntimeError(
                    f"single_step_checkpoint_invalid:{name}:"
                    f"actual={physics_step_count}:expected={expected_steps}"
                )
            step_checkpoints[name] = {
                "physics_step_events": physics_step_count,
                "timeline_stopped": True,
            }

        operation_records: list[dict[str, Any]] = []

        def record_operation(name: str, *, expected_steps: int) -> None:
            replay.require_stopped_timeline(timeline)
            if physics_step_count != expected_steps:
                raise RuntimeError(
                    f"operation_ledger_invalid:{name}:"
                    f"actual={physics_step_count}:expected={expected_steps}"
                )
            operation_records.append(
                {
                    "operation": name,
                    "physics_step_events": physics_step_count,
                    "timeline_stopped": True,
                }
            )

        legacy_graph_checkpoints: dict[str, dict[str, Any]] = {}

        def record_legacy_graph_checkpoint(name: str) -> None:
            replay.require_stopped_timeline(timeline)
            if physics_step_count != 0:
                raise RuntimeError(
                    f"legacy_graph_setup_advanced_physics:{name}:"
                    f"actual={physics_step_count}"
                )
            legacy_graph_checkpoints[name] = {
                "physics_step_events": 0,
                "timeline_stopped": True,
            }

        step_subscription = omni.physx.get_physx_interface().subscribe_physics_step_events(
            on_physics_step
        )
        record_operation("register_step_counter", expected_steps=0)
        record_legacy_graph_checkpoint("before_legacy_graph_setup")
        legacy_sampling_api_removal = native.remove_legacy_particle_sampling_api(
            stage,
            execute_command=omni.kit.commands.execute,
        )
        record_operation(
            "remove_legacy_particle_sampling_api", expected_steps=0
        )
        original_fluid_deactivate_summary = (
            native._deactivate_original_fluid_prims(stage)
        )
        record_operation("deactivate_original_fluid_prims", expected_steps=0)
        original_fluid_deactivate_summary = (
            native.synchronize_legacy_particle_graph(
                app=app,
                timeline=timeline,
                settings=settings,
                isolation_summary=original_fluid_deactivate_summary,
                warmup_updates=LEGACY_GRAPH_SYNC_UPDATES,
                strict_mode=True,
            )
        )
        record_operation("synchronize_legacy_particle_graph", expected_steps=0)
        record_legacy_graph_checkpoint("after_legacy_graph_setup")
        legacy_graph_validation = validate_legacy_graph_setup(
            legacy_sampling_api_removal,
            original_fluid_deactivate_summary,
            legacy_graph_checkpoints,
        )
        failure_context["legacy_graph_setup"] = legacy_graph_validation

        physics_settings = native._configure_physics_scene_for_pbd(
            stage,
            "/World/PhysicsScene",
            integration_dt=INITIALIZATION_DT,
            strict_mode=True,
        )
        physics_scene_validation = validate_strict_physics_scene(
            physics_settings
        )
        record_operation("configure_physics_scene", expected_steps=0)
        failure_context["strict_physics_scene"] = physics_scene_validation

        log_cursor = native._capture_kit_log_cursor()
        if log_cursor.get("cursor_captured") is not True:
            raise RuntimeError("accepted_final_kit_log_cursor_unavailable")
        material_info = native._author_liquid_presentation_water_material(
            stage,
            attempt_mdl=True,
            mdl_source_asset=MDL_SOURCE_ASSET,
            closure_base_dir=None,
            prefer_kit_bind=False,
        )
        if (
            material_info.get("material_backend") != "MDL_WATER"
            or material_info.get("sub_identifier") != MDL_SUB_IDENTIFIER
            or material_info.get("fallback_reason") is not None
        ):
            raise RuntimeError("clearwater_material_authoring_failed")
        lighting_info = native._author_liquid_presentation_lighting(stage)
        widths = {
            "particle_width": fixed_contract["particle_width"],
            "particle_contact_offset": fixed_contract[
                "particle_contact_offset"
            ],
            "particle_system_contact_offset": fixed_contract[
                "particle_system_contact_offset"
            ],
            "solid_rest_offset": fixed_contract["solid_rest_offset"],
            "fluid_rest_offset": fixed_contract["fluid_rest_offset"],
        }
        authored = native._author_completed_pbd_runtime_particles(
            stage=stage,
            positions=final_record["positions"],
            widths=widths,
            physics_scene_path="/World/PhysicsScene",
            visual_material_path="/World/Looks/OmniGlass_01",
            presentation_isosurface_video=True,
            presentation_visual_material_path=TREATMENT_MATERIAL_PATH,
            presentation_postprocess_overrides=None,
            display_particle_width=0.0043,
            non_particle_rest_offset=fixed_contract["solid_rest_offset"],
        )
        record_operation("author_runtime_particles", expected_steps=0)
        second_deactivation_validation = validate_second_deactivation(
            authored.get("pre_deactivate_summary") or {}
        )
        record_operation("verify_second_deactivation", expected_steps=0)
        if authored["particle_system_path"] != RUNTIME_PARTICLE_SYSTEM_PATH:
            raise RuntimeError("runtime_particle_system_path_mismatch")
        runtime_points = UsdGeom.Points(
            stage.GetPrimAtPath(RUNTIME_PARTICLE_SET_PATH)
        )
        authored_points = runtime_points.GetPointsAttr().Get()
        authored_position_validation = validate_authored_positions(
            authored_points or [], final_record["positions"]
        )
        authored_velocity_validation = validate_authored_zero_velocities(
            runtime_points.GetVelocitiesAttr().Get() or []
        )
        if source_layer.dirty:
            raise RuntimeError("authoring_dirtied_pinned_source_layer")
        record_step_checkpoint("before_attach", expected_steps=0)
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        stepper = native.StrictPhysicsStepper.attach(
            interface=omni.physx.get_physx_simulation_interface(),
            logical_dt=INITIALIZATION_DT,
            integration_dt=INITIALIZATION_DT,
            substeps_per_logical_step=1,
            stage_id=stage_id,
        )
        record_operation("attach_stepper", expected_steps=0)
        record_step_checkpoint("after_attach", expected_steps=0)

        post_step_presentation_state: dict[str, Any] | None = None

        def capture_post_step_readback(
            integration_step: int,
            simulated_seconds: float,
        ) -> None:
            nonlocal post_step_presentation_state
            if integration_step != 1 or not math.isclose(
                simulated_seconds,
                INITIALIZATION_DT,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise RuntimeError("single_step_callback_contract_invalid")
            post_step_positions = runtime_points.GetPointsAttr().Get() or []
            strict_counts = classify_visible_beaker_positions(
                post_step_positions,
                cup_interior_frame,
            )
            violating_indices: list[int] = []
            if strict_counts.get("strict_violating_point_count"):
                violating_indices = [
                    index
                    for index, point in enumerate(post_step_positions)
                    if classify_visible_beaker_positions(
                        [point], cup_interior_frame
                    ).get("strict_violating_point_count")
                ]
            post_step_presentation_state = (
                validate_post_step_presentation_readback(
                    post_step_positions,
                    strict_counts,
                    violating_indices=violating_indices,
                )
            )
            post_step_presentation_state.update(
                {
                    "integration_step": integration_step,
                    "simulated_seconds": simulated_seconds,
                }
            )

        stepper.step(after_integration_step=capture_post_step_readback)
        record_operation("single_initialization_step", expected_steps=1)
        operation_validation = validate_operation_ledger(operation_records)
        failure_context["operation_ledger"] = operation_validation
        record_step_checkpoint("after_initialization", expected_steps=1)
        if post_step_presentation_state is None:
            raise RuntimeError("post_step_presentation_readback_missing")

        cameras = {
            role: {"camera_path": CAMERA_PRIMS[role]} for role in CAMERA_PATHS
        }
        resources = replay.create_replicator_capture_resources(
            rep,
            cameras=cameras,
            resolution=CAPTURE_RESOLUTION,
        )
        annotators = {
            role: resource["annotator"] for role, resource in resources.items()
        }
        rep.orchestrator.preview()
        for index in range(WARMUP_UPDATES):
            native.paused_render_update(app, timeline, settings=settings)
            record_step_checkpoint(
                f"warmup_update_{index + 1}", expected_steps=1
            )
        record_step_checkpoint("after_warmup", expected_steps=1)

        bridge_raw = _runtime_bridge_summary(
            stage, authored["particle_system_path"]
        )
        bridge = validate_runtime_isosurface_bridge(
            bridge_raw,
            particle_system_path=authored["particle_system_path"],
        )
        excluded_runtime_roots = (
            RUNTIME_PARTICLE_SYSTEM_PATH,
            RUNTIME_PARTICLE_SET_PATH,
        )
        scene_hash = lambda: stable_scene_points_sha256(  # noqa: E731
            stage, excluded_roots=excluded_runtime_roots
        )
        scene_hash_before_captures = scene_hash()

        capture_attempts: list[dict[str, Any]] = []
        failure_context["capture_attempts"] = capture_attempts
        discarded_capture: dict[str, Any] | None = None
        discarded_warmup_summary: dict[str, Any]
        discarded_attempt = {
            "kind": "discarded_warmup",
            "camera_roles": list(CAMERA_PATHS),
            "predeclared_discard": True,
            "outcome": "started",
        }
        capture_attempts.append(discarded_attempt)
        with tempfile.TemporaryDirectory(
            prefix="discarded_warmup_", dir=out_root
        ) as warmup_dir:
            try:
                discarded_capture = replay.capture_static_replicator_rgbs(
                    orchestrator=rep.orchestrator,
                    timeline=timeline,
                    annotators=annotators,
                    output_paths={
                        role: Path(warmup_dir) / f"{role}.png"
                        for role in CAMERA_PATHS
                    },
                    width=CAPTURE_RESOLUTION[0],
                    height=CAPTURE_RESOLUTION[1],
                    rt_subframes=RT_SUBFRAMES,
                    observed_default_time_usd_point_attributes_hash=scene_hash,
                )
            except RuntimeError as exc:
                discarded_warmup_summary = (
                    finalize_discarded_warmup_failure_attempt(
                        discarded_attempt,
                        exc,
                    )
                )
            else:
                discarded_attempt["outcome"] = "captured_then_discarded"
                discarded_warmup_summary = {
                    "discarded": True,
                    "frame_quality_valid": True,
                    "continued_to_strict_final_capture": True,
                    "frame_sha256": {
                        role: discarded_capture["frames"][role]["sha256"]
                        for role in CAMERA_PATHS
                    },
                }
        record_step_checkpoint("after_discarded_capture", expected_steps=1)

        output_paths = {
            "context": out_root
            / "graph_owned_isosurface_pair_context.png",
            "source_beaker_closeup": out_root
            / "graph_owned_isosurface_source_beaker_closeup.png",
            "native_table_context": out_root
            / "graph_owned_isosurface_native_table_context.png",
        }
        final_attempt = {
            "kind": "strict_final",
            "camera_roles": list(CAMERA_PATHS),
            "predeclared_discard": False,
            "outcome": "started",
        }
        capture_attempts.append(final_attempt)
        capture_validation: dict[str, Any] | None = None
        final_capture_error: BaseException | None = None
        try:
            capture = replay.capture_static_replicator_rgbs(
                orchestrator=rep.orchestrator,
                timeline=timeline,
                annotators=annotators,
                output_paths=output_paths,
                width=CAPTURE_RESOLUTION[0],
                height=CAPTURE_RESOLUTION[1],
                rt_subframes=RT_SUBFRAMES,
                observed_default_time_usd_point_attributes_hash=scene_hash,
            )
            capture_validation = validate_camera_capture_contract(capture)
        except BaseException as exc:
            final_attempt["outcome"] = "failed"
            final_attempt["error"] = str(exc)
            final_capture_error = exc
        else:
            final_attempt["outcome"] = "captured"
            final_attempt["contract_verified"] = True
        record_step_checkpoint("after_final_capture", expected_steps=1)
        scene_hash_after_captures = scene_hash()
        scene_hash_unchanged = (
            scene_hash_after_captures == scene_hash_before_captures
        )
        failure_context["scene_hash_unchanged"] = scene_hash_unchanged

        cleanup = replay.destroy_replicator_capture_resources(resources)
        resources = {}
        replay.require_replicator_cleanup(cleanup)
        failure_context["replicator_cleanup"] = cleanup
        stepper.detach()
        record_step_checkpoint("after_detach", expected_steps=1)
        single_step_validation = validate_single_step_checkpoints(step_checkpoints)
        single_step_lifecycle = validate_single_step_lifecycle_summary(
            stepper.summary(requested_steps=1)
        )
        failure_context["single_step_validation"] = single_step_validation
        failure_context["single_step_lifecycle"] = single_step_lifecycle

        log_segment = native._read_kit_log_segment(log_cursor)
        clearwater_log_validation = clearwater.validate_clearwater_log_segment(
            log_segment
        )
        single_step_log_validation = validate_single_step_log_segment(
            str(log_segment["log_text"])
        )
        log_path = out_root / "kit_log_segment.txt"
        with log_path.open("x", encoding="utf-8") as stream:
            stream.write(str(log_segment["log_text"]))
        log_artifact = {
            "path": str(log_path),
            "sha256": _sha256_file(log_path),
            "verified": True,
            "clearwater": clearwater_log_validation,
            "single_step_runtime": single_step_log_validation,
        }
        failure_context["log"] = log_artifact
        replay.require_stopped_timeline(timeline)
        source_integrity = {
            "source_sha256_before": source_sha256_before,
            "source_sha256_after": _sha256_file(source),
            "source_layer_dirty_after": bool(source_layer.dirty),
            "wrapper_sha256_before": wrapper_sha256_before,
            "wrapper_sha256_after": _sha256_file(wrapper_path),
            "non_runtime_scene_points_sha256_before_captures": (
                scene_hash_before_captures
            ),
            "non_runtime_scene_points_sha256_after_captures": (
                scene_hash_after_captures
            ),
        }
        source_integrity["verified"] = bool(
            source_integrity["source_sha256_after"] == source_sha256_before
            and source_integrity["source_layer_dirty_after"] is False
            and source_integrity["wrapper_sha256_after"]
            == wrapper_sha256_before
            and scene_hash_after_captures == scene_hash_before_captures
        )
        failure_context["source_integrity"] = source_integrity
        if source_integrity["verified"] is not True:
            raise RuntimeError("source_or_wrapper_integrity_failed")

        if final_capture_error is not None:
            terminal_evidence = validate_terminal_capture_failure_context(
                failure_context
            )
            failure_context["terminal_capture_failure_evidence"] = (
                terminal_evidence
            )
            raise final_capture_error
        if capture_validation is None:
            raise RuntimeError("strict_final_capture_validation_missing")

        gates = {name: True for name in TECHNICAL_GATES}
        status = build_technical_status(gates)
        manifest = {
            "schema_version": 1,
            "probe_id": PROBE_ID,
            **status,
            "accepted_authority_input": {
                "bundle_path": str(AUTHORITY_ROOT),
                "bundle_sha256": authority[
                    "accepted_authority_bundle_sha256"
                ],
                "trace_path": final_record["trace_path"],
                "trace_sha256": final_record["trace_sha256"],
                "frame_index": final_record["step_index"],
                "particle_count": final_record["particle_count"],
                "positions_sha256": final_record["positions_sha256"],
                "strict_visible_beaker_counts": final_record[
                    "strict_visible_beaker_counts"
                ],
            },
            "derived_presentation_state": {
                "authored_position_validation": authored_position_validation,
                "authored_velocity_validation": authored_velocity_validation,
                "post_step_point_center_containment": (
                    post_step_presentation_state
                ),
                "single_step_validation": single_step_validation,
                "single_step_lifecycle": single_step_lifecycle,
                "initial_velocities_are_authoring_choice_not_authority": True,
                "not_frame_601": True,
            },
            "source_path": str(source),
            "wrapper_contract": wrapper_contract,
            "source_integrity": source_integrity,
            "fixed_isosurface_contract": fixed_contract,
            "legacy_graph_setup": {
                "sampler_removal": legacy_sampling_api_removal,
                "first_deactivation_and_sync": (
                    original_fluid_deactivate_summary
                ),
                "validation": legacy_graph_validation,
                "second_deactivation_validation": (
                    second_deactivation_validation
                ),
            },
            "strict_physics_scene": physics_scene_validation,
            "operation_ledger": operation_validation,
            "authored_runtime": authored,
            "runtime_isosurface_bridge": bridge,
            "material": material_info,
            "mdl_input": mdl_input,
            "mdl_search_contract": mdl_search,
            "lighting": lighting_info,
            "render_contract": render_contract,
            "discarded_warmup_capture": discarded_warmup_summary,
            "capture_attempts": capture_attempts,
            "capture": capture_validation,
            "replicator_cleanup": cleanup,
            "kit_log_segment": log_artifact,
            "technical_gates": gates,
            "timeline_stopped": True,
            "physics_step_count_instrumented": True,
            "physics_steps_executed": 1,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        _write_json(out_root / "probe_manifest.json", manifest)
        step_subscription = None
        return manifest
    except BaseException as exc:
        failure = build_failure_manifest(exc)
        if failure_context:
            failure["runtime_context"] = failure_context
        failure_path = out_root / "probe_manifest.json"
        if not failure_path.exists():
            _write_json(failure_path, failure)
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        sys.stderr.flush()
        raise
    finally:
        if resources:
            from tools.labutopia_fluid import (
                run_real_beaker_omniglass_replay as replay,
            )

            replay.destroy_replicator_capture_resources(resources)
        if stepper is not None and not stepper.detach_verified:
            try:
                stepper.detach()
            except Exception:
                pass
        step_subscription = None
        app.close()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_STAGE)
    parser.add_argument("--out-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_root = args.out_root.resolve()
    try:
        manifest = _run_runtime(args.source, out_root)
    except Exception as exc:
        failure = build_failure_manifest(exc)
        if out_root.is_dir() and not (out_root / "probe_manifest.json").exists():
            _write_json(out_root / "probe_manifest.json", failure)
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

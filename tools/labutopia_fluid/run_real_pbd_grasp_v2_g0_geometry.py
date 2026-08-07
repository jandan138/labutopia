#!/usr/bin/env python3
"""Run the sealed effective-runtime-v2 G0 geometry audit for grasp recovery.

The parent only orchestrates and verifies artifacts.  USD, Isaac, Omni, and
PhysX inspection is confined to the attested Isaac 4.1 child.  This first
authority deliberately remains NO-GO until a parent-validated clearance
certificate is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils import real_pbd_g0_full_robot_fk_capability as fk_capability

FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
PROFILE_PATH = REPO_ROOT / "tools/labutopia_fluid/profiles/isaac41_g0_property_query_experimental.kit"
FK_CAPABILITY_PROFILE_PATH = (
    REPO_ROOT
    / "tools/labutopia_fluid/profiles/"
    "isaac41_g0_full_robot_fk_capability_experimental.kit"
)
FK_CAPABILITY_PLAN_PATH = REPO_ROOT / "config/real_pbd_g0_full_robot_fk_capability_v1.json"
DEFAULT_ASSET = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
ROBOT_ASSET = REPO_ROOT / "assets/robots/Franka.usd"
OFFSET_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_explicit_contact_offsets_v1.usda"
)
HIDDEN_CUBE_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_disable_hidden_cube_collision_v1.usda"
)
LEGACY_OVERLAY_PROFILE = "legacy_contact_offsets_and_hidden_cube_v1"
V7_CUBE_ONLY_OVERLAY_PROFILE = "v7_cube_only_static_geometry_v1"
V9_DIAGNOSTIC_CONFIG = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v7.yaml"
)
V9_DIAGNOSTIC_RUNNER = (
    REPO_ROOT / "tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py"
)
_OVERLAY_PROFILE_STACKS = {
    LEGACY_OVERLAY_PROFILE: (
        ("explicit_contact_offsets", OFFSET_OVERLAY),
        ("hidden_cube_collision_disable", HIDDEN_CUBE_OVERLAY),
    ),
    V7_CUBE_ONLY_OVERLAY_PROFILE: (
        ("hidden_cube_collision_disable", HIDDEN_CUBE_OVERLAY),
    ),
}
CHILD_REPORT_BASENAME = "child_report.json"
RUNTIME_RECEIPT_BASENAME = "runtime_receipt.json"
RUN_MANIFEST_BASENAME = "run_manifest.json"
V9_DIAGNOSTIC_ELIGIBILITY_BASENAME = "v9_diagnostic_eligibility.json"
STDOUT_BASENAME = "child.stdout.log"
STDERR_BASENAME = "child.stderr.log"
GEOMETRY_SNAPSHOT_BASENAME = "geometry_snapshot.json"
DECISION_NO_GO = "G0_NO_GO"
DECISION_GO = "G0_GO"
SOURCE_PATH = "/World/beaker2"
SOURCE_SHELL_PATH = "/World/beaker2/mesh"
WRAPPER_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
BEAKER1_PATH = "/World/beaker1"
ROBOT_ROOT_PATH = "/World/Franka"
LEFT_FINGER_PATH = "/World/Franka/panda_leftfinger"
RIGHT_FINGER_PATH = "/World/Franka/panda_rightfinger"
HAND_PATH = "/World/Franka/panda_hand"
TABLE_PATH = "/World/table/surface/mesh"
TABLE_BODY_PATH = "/World/table"
PARTICLE_PATH = "/World/InternDataParityFluid/Particles"
TOOL_CENTER_PATH = "/World/Franka/panda_hand/tool_center"
APPROACH_DIRECTION_WORLD = (0.0, 0.0, -1.0)
PREGRASP_DISTANCE_M = 0.120
CLEARANCE_NUMERICAL_MARGIN_M = 0.001
APPROACH_SEGMENTS_PER_LEG = 8
APPROACH_CANDIDATE_DIRECTIONS = {
    "lift_first_top_down": ((0.0, 0.0, 1.0), (1.0, 1.0, 0.0), (0.0, 0.0, -1.0)),
    "lift_first_y_positive": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)),
    "lift_first_y_negative": ((0.0, 0.0, 1.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)),
    "lift_first_x_positive": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
    "lift_first_x_negative": ((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
}
APPROACH_CANDIDATE_LIFT_DISTANCES_M = (0.08, 0.12, 0.16)
APPROACH_CANDIDATE_LATERAL_DISTANCES_M = (0.0, 0.08, 0.16)
APPROACH_CANDIDATE_DESCENT_MARGIN_M = 0.04
APPROACH_GRASP_HEIGHT_OFFSET_M = 0.12
MIN_PRECONTACT_CLEARANCE_M = 1.0e-9


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_overlay_profile(profile_id: str) -> dict[str, Any]:
    if profile_id not in _OVERLAY_PROFILE_STACKS:
        raise ValueError("g0_geometry_overlay_profile_invalid")
    overlay_stack = []
    seen_paths = set()
    for overlay_id, raw_path in _OVERLAY_PROFILE_STACKS[profile_id]:
        path = raw_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"g0_geometry_overlay_missing:{path}")
        if path in seen_paths:
            raise ValueError("g0_geometry_overlay_profile_duplicate_path")
        seen_paths.add(path)
        overlay_stack.append(
            {
                "id": overlay_id,
                "path": str(path),
                "sha256": sha256_file(path),
            }
        )
    return {
        "authority": "real_pbd_g0_overlay_profile_v1",
        "id": profile_id,
        "overlay_stack": overlay_stack,
        "physics_scene_dt_reset_parity": "NOT_CLAIMED",
    }


def _validated_overlay_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = value.get("id") if isinstance(value, Mapping) else None
    expected = resolve_overlay_profile(profile_id)
    if dict(value) != expected:
        raise ValueError("g0_geometry_overlay_profile_mismatch")
    return expected


def _overlay_path(profile: Mapping[str, Any], overlay_id: str) -> Path:
    validated = _validated_overlay_profile(profile)
    matches = [
        item for item in validated["overlay_stack"] if item["id"] == overlay_id
    ]
    if len(matches) != 1:
        raise ValueError("g0_geometry_overlay_profile_overlay_missing")
    return Path(matches[0]["path"])


def _artifact(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _active_profile_path(*, full_robot_fk_capability: bool) -> Path:
    return FK_CAPABILITY_PROFILE_PATH if full_robot_fk_capability else PROFILE_PATH


def _load_fk_capability_plan(path: Path) -> dict[str, Any]:
    candidate = Path(path)
    resolved = candidate.resolve()
    if (
        candidate.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(REPO_ROOT)
    ):
        raise ValueError("g0_geometry_fk_capability_plan_invalid")
    try:
        raw = json.loads(resolved.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("g0_geometry_fk_capability_plan_invalid") from exc
    if not isinstance(raw, Mapping) or resolved.read_bytes() != canonical_json_bytes(dict(raw)):
        raise ValueError("g0_geometry_fk_capability_plan_invalid")
    try:
        return fk_capability.validate_plan(raw)
    except ValueError as exc:
        raise ValueError("g0_geometry_fk_capability_plan_invalid") from exc


def _source_paths(
    overlay_profile: Mapping[str, Any],
    *,
    full_robot_fk_capability: bool = False,
    fk_capability_plan_path: Path | None = None,
) -> tuple[Path, ...]:
    profile = _validated_overlay_profile(overlay_profile)
    paths = [
        Path(__file__),
        _active_profile_path(full_robot_fk_capability=full_robot_fk_capability),
        REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        REPO_ROOT / "tools/labutopia_fluid/run_robot_table_geometry_probe.py",
        REPO_ROOT / "tools/labutopia_fluid/run_real_pbd_grasp_v2_preflight.py",
        REPO_ROOT / "utils/controlled_contact.py",
        REPO_ROOT / "utils/real_pbd_grasp_v2.py",
        REPO_ROOT / "utils/real_pbd_g0_full_robot_fk_capability.py",
        *(Path(item["path"]) for item in profile["overlay_stack"]),
    ]
    if full_robot_fk_capability:
        plan_path = (
            FK_CAPABILITY_PLAN_PATH
            if fk_capability_plan_path is None
            else Path(fk_capability_plan_path)
        )
        _load_fk_capability_plan(plan_path)
        paths.extend(
            (
                plan_path,
                REPO_ROOT
                / "tools/labutopia_fluid/nonformal_controller_static_collision_screen_runtime.py",
            )
        )
    if profile["id"] == V7_CUBE_ONLY_OVERLAY_PROFILE:
        paths.extend((V9_DIAGNOSTIC_CONFIG, V9_DIAGNOSTIC_RUNNER))
    return tuple(path.resolve() for path in paths)


def require_child_overlay_profile(
    child_report: Mapping[str, Any], expected_profile: Mapping[str, Any]
) -> dict[str, Any]:
    expected = _validated_overlay_profile(expected_profile)
    fixture = child_report.get("fixture")
    if (
        not isinstance(fixture, Mapping)
        or fixture.get("overlay_profile") != expected
        or fixture.get("overlay_profile_sha256") != canonical_json_sha256(expected)
    ):
        raise RuntimeError("g0_geometry_child_overlay_profile_mismatch")
    return expected


def _v9_diagnostic_config_binding(
    overlay_profile: Mapping[str, Any],
) -> dict[str, Any]:
    if _validated_overlay_profile(overlay_profile)["id"] != V7_CUBE_ONLY_OVERLAY_PROFILE:
        raise ValueError("g0_geometry_v9_config_profile_invalid")
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as probe

    frozen = probe.freeze_diagnostic_config(
        V9_DIAGNOSTIC_CONFIG, production_config_path=probe.PRODUCTION_CONFIG
    )
    diagnostic = frozen["config"].get("diagnostic")
    if not isinstance(diagnostic, Mapping):
        raise ValueError("g0_geometry_v9_config_invalid")
    treatment = diagnostic.get("g0_native_pick_treatment")
    hidden_cube = diagnostic.get("hidden_cube_treatment")
    local_scene = frozen.get("local_scene")
    local_franka = frozen.get("local_franka")
    if (
        diagnostic.get("schema_version") != 7
        or diagnostic.get("protocol_id") != "native_expert_empty_beaker_unbound_lift_v7"
        or not isinstance(treatment, Mapping)
        or treatment.get("authority") != "g0_native_expert_pick_v9"
        or not isinstance(hidden_cube, Mapping)
        or not isinstance(local_scene, Mapping)
        or not isinstance(local_franka, Mapping)
        or Path(str(local_scene.get("absolute_usd_path", ""))).resolve()
        != DEFAULT_ASSET.resolve()
        or local_scene.get("sha256") != sha256_file(DEFAULT_ASSET)
        or local_franka.get("sha256") != sha256_file(ROBOT_ASSET)
        or hidden_cube.get("usd_path")
        != str(HIDDEN_CUBE_OVERLAY.relative_to(REPO_ROOT))
        or hidden_cube.get("sha256") != sha256_file(HIDDEN_CUBE_OVERLAY)
    ):
        raise ValueError("g0_geometry_v9_config_invalid")
    return {
        "diagnostic_config_sha256": frozen["sha256"],
        "native_pick_treatment": dict(treatment),
        "native_pick_treatment_sha256": canonical_json_sha256(dict(treatment)),
        "asset_sha256": str(local_scene["sha256"]),
        "robot_asset_sha256": str(local_franka["sha256"]),
    }


def _v9_unavailable_public_offset_readback(
    *,
    offsets: Mapping[str, Any],
    role_paths: Mapping[str, Any],
    runtime_receipt: Mapping[str, Any],
    property_query_info_surface: Mapping[str, Any],
) -> dict[str, Any] | None:
    contract = runtime_receipt.get("runtime_contract")
    observed = runtime_receipt.get("observed_runtime")
    if (
        runtime_receipt.get("attestation_status") != "MATCH"
        or not isinstance(contract, Mapping)
        or not isinstance(observed, Mapping)
        or contract.get("python_version") != "3.10.20"
        or contract.get("isaacsim_version") != "4.1.0.0"
        or contract.get("physx_version") != "106.0.20"
        or contract.get("usd_version") != "0.22.11"
        or contract.get("effective_numpy_version") != "1.26.0"
        or observed.get("python_version") != contract["python_version"]
        or observed.get("isaacsim_version") != contract["isaacsim_version"]
        or observed.get("physx_version") != contract["physx_version"]
        or observed.get("usd_version") != contract["usd_version"]
        or observed.get("effective_numpy_version") != contract["effective_numpy_version"]
        or property_query_info_surface.get("finished") is not True
        or property_query_info_surface.get("fields") != []
        or property_query_info_surface.get("values") != {}
    ):
        return None
    left = list(role_paths.get("finger_pad_collider_paths", {}).get("left", []))
    right = list(role_paths.get("finger_pad_collider_paths", {}).get("right", []))
    support = list(role_paths.get("support_collider_paths", []))
    if len(left) != 1 or len(right) != 1 or len(support) != 1:
        return None
    records = offsets.get("records")
    if not isinstance(records, Mapping):
        return None
    role_paths_by_name = (
        ("left_finger_pad", left[0]),
        ("right_finger_pad", right[0]),
        ("table_support", support[0]),
    )
    output_records = []
    for role, path in role_paths_by_name:
        record = records.get(path)
        contact_nonfinite_sentinel = bool(
            isinstance(record, Mapping)
            and record.get("contact_offset_authored") is True
        )
        rest_nonfinite_sentinel = bool(
            isinstance(record, Mapping)
            and record.get("rest_offset_authored") is True
        )
        if (
            not isinstance(record, Mapping)
            or record.get("authority") != "unresolved"
            or record.get("contact_offset_m") is not None
            or record.get("rest_offset_m") is not None
            or (
                contact_nonfinite_sentinel
                and record.get("raw_contact_offset") != "-inf"
            )
            or (
                rest_nonfinite_sentinel and record.get("raw_rest_offset") != "-inf"
            )
        ):
            return None
        output_records.append(
            {
                "role": role,
                "path": path,
                "contact_offset_status": "ENGINE_DEFAULT_PUBLIC_READBACK_UNAVAILABLE",
                "rest_offset_status": "ENGINE_DEFAULT_PUBLIC_READBACK_UNAVAILABLE",
                "contact_offset_usd_nonfinite_sentinel": contact_nonfinite_sentinel,
                "rest_offset_usd_nonfinite_sentinel": rest_nonfinite_sentinel,
            }
        )
    return {
        "authority": "real_pbd_g0_public_offset_readback_unavailable_v1",
        "runtime_contract_sha256": canonical_json_sha256(dict(contract)),
        "property_query_info_surface_sha256": canonical_json_sha256(
            dict(property_query_info_surface)
        ),
        "api_surface": "PhysxSchema.PhysxCollisionAPI_authored_offset_readback_v1",
        "records": output_records,
    }


def _build_v9_diagnostic_eligibility(
    *,
    child_report: Mapping[str, Any],
    runtime_receipt: Mapping[str, Any],
    execution_request: Mapping[str, Any],
    overlay_profile: Mapping[str, Any],
    config_binding: Mapping[str, Any],
) -> dict[str, Any] | None:
    from utils.real_pbd_grasp_v2 import evaluate_nonformal_v9_diagnostic_eligibility

    profile = _validated_overlay_profile(overlay_profile)
    if profile["id"] != V7_CUBE_ONLY_OVERLAY_PROFILE:
        return None
    fixture = child_report.get("fixture")
    checks = child_report.get("checks")
    inventory = child_report.get("collision_inventory")
    raw = child_report.get("raw_geometry_witness")
    if (
        child_report.get("classification") != "NON_FORMAL_HISTORICAL_REFERENCE"
        or child_report.get("decision") != DECISION_NO_GO
        or child_report.get("certificate") is not None
        or not isinstance(fixture, Mapping)
        or not isinstance(checks, Mapping)
        or not isinstance(inventory, Mapping)
        or not isinstance(raw, Mapping)
        or fixture.get("overlay_profile") != profile
        or fixture.get("overlay_profile_sha256") != canonical_json_sha256(profile)
        or fixture.get("asset_sha256") != config_binding["asset_sha256"]
        or fixture.get("robot_asset_sha256") != config_binding["robot_asset_sha256"]
        or checks.get("effective_offsets_resolved") is not False
        or checks.get("signed_swept_clearance_certificate") is not False
        or any(
            checks.get(name) is not True
            for name in (
                "runtime_attestation_match",
                "timeline_stopped",
                "stage_units_source_contract",
                "topology_contract",
                "collision_inventory_present",
                "cooked_queries_complete",
            )
        )
    ):
        return None
    gap = _v9_unavailable_public_offset_readback(
        offsets=child_report.get("effective_offsets", {}),
        role_paths=child_report.get("role_paths", {}),
        runtime_receipt=runtime_receipt,
        property_query_info_surface=child_report.get("property_query_info_surface", {}),
    )
    if gap is None:
        return None
    if (
        raw.get("status") != "COMPLETE"
        or raw.get("unexpected_hit_paths") != []
        or raw.get("prohibited_hit_paths") != []
    ):
        return None
    contract = runtime_receipt.get("runtime_contract")
    if not isinstance(contract, Mapping) or not isinstance(config_binding, Mapping):
        return None
    payload = {
        "authority": "real_pbd_g0_v9_diagnostic_eligibility_sidecar_v1",
        "schema_version": 1,
        "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
        "strict_g0_decision": DECISION_NO_GO,
        "g2_authorized": False,
        "formal_promotion_authorized": False,
        "allowed_protocol": {
            "schema_version": 7,
            "protocol_id": "native_expert_empty_beaker_unbound_lift_v7",
            "native_pick_authority": "g0_native_expert_pick_v9",
            "single_named_diagnostic_only": True,
        },
        "native_pick_treatment_sha256": config_binding[
            "native_pick_treatment_sha256"
        ],
        "bindings": {
            "diagnostic_config_sha256": config_binding["diagnostic_config_sha256"],
            "g0_child_report_sha256": canonical_json_sha256(dict(child_report)),
            "g0_runtime_receipt_sha256": canonical_json_sha256(dict(runtime_receipt)),
            "g0_execution_request_sha256": canonical_json_sha256(dict(execution_request)),
            "g0_runtime_contract_sha256": canonical_json_sha256(dict(contract)),
            "g0_asset_sha256": fixture["asset_sha256"],
            "g0_robot_asset_sha256": fixture["robot_asset_sha256"],
            "g0_overlay_profile_sha256": canonical_json_sha256(profile),
            "g0_collision_inventory_sha256": inventory.get("sha256"),
            "raw_geometry_witness_sha256": canonical_json_sha256(dict(raw)),
            "g0_public_offset_surface_sha256": gap[
                "property_query_info_surface_sha256"
            ],
        },
        "unavailable_public_offset_readback": gap,
        "raw_geometry_witness": dict(raw),
        "eligible": True,
    }
    eligibility = {**payload, "sha256": canonical_json_sha256(payload)}
    return evaluate_nonformal_v9_diagnostic_eligibility(eligibility)


def _write_create_only(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"g0_geometry_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_bytes(payload)
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_canonical(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("g0_geometry_json_mapping_required")
    payload = dict(value)
    if path.read_bytes() != canonical_json_bytes(payload):
        raise ValueError("g0_geometry_json_noncanonical")
    return payload


def _runtime_error_report(error: BaseException, runtime: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "authority": "real_pbd_g0_geometry_child_report_v1",
        "schema_version": 1,
        "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
        "decision": "RUNTIME_BLOCKED",
        "runtime": None if runtime is None else dict(runtime),
        "fatal_error": {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def _child_marker(value: str) -> None:
    print(f"g0_geometry_child:{value}", file=sys.stderr, flush=True)


def _enabled_colliders(stage: Any, root_path: str) -> list[str]:
    from pxr import Usd, UsdPhysics

    root = stage.GetPrimAtPath(root_path)
    if not root or not root.IsValid():
        return []
    paths = []
    for prim in Usd.PrimRange(root):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is not False:
            paths.append(str(prim.GetPath()))
    return sorted(set(paths))


def _collision_inventory(stage: Any) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    records = []
    filtered_pairs = []
    for prim in Usd.PrimRange.Stage(stage):
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            material_targets = []
            material_relation = prim.GetRelationship("material:binding:physics")
            if material_relation:
                material_targets = sorted(str(item) for item in material_relation.GetTargets())
            enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
            records.append(
                {
                    "path": str(prim.GetPath()),
                    "type": str(prim.GetTypeName()),
                    "enabled": enabled is not False,
                    "schemas": sorted(str(item) for item in prim.GetAppliedSchemas()),
                    "material_targets": material_targets,
                }
            )
        if prim.HasAPI(UsdPhysics.FilteredPairsAPI):
            relation = UsdPhysics.FilteredPairsAPI(prim).GetFilteredPairsRel()
            for target in relation.GetTargets():
                filtered_pairs.append([str(prim.GetPath()), str(target)])
    records.sort(key=lambda item: item["path"])
    filtered_pairs.sort()
    payload = {"colliders": records, "filtered_pairs": filtered_pairs}
    return {
        **payload,
        "sha256": canonical_json_sha256(payload),
    }


def _role_paths(stage: Any, topology: Mapping[str, Any]) -> dict[str, Any]:
    wrappers = _enabled_colliders(stage, WRAPPER_PATH)
    left = _enabled_colliders(stage, LEFT_FINGER_PATH)
    right = _enabled_colliders(stage, RIGHT_FINGER_PATH)
    hand = _enabled_colliders(stage, HAND_PATH)
    full_robot = _enabled_colliders(stage, ROBOT_ROOT_PATH)
    support = _enabled_colliders(stage, TABLE_PATH)
    beaker1 = _enabled_colliders(stage, BEAKER1_PATH)
    return {
        "source_external_shell_paths": [SOURCE_SHELL_PATH],
        "source_internal_wrapper_paths": wrappers,
        "support_collider_paths": support or [TABLE_PATH],
        "beaker1_collider_paths": beaker1,
        "full_robot_collider_paths": full_robot,
        "hand_collider_paths": hand,
        "finger_pad_collider_paths": {"left": left, "right": right},
        "topology_wrapper_count": topology.get("wrapper_collider_count"),
    }


def build_full_robot_static_collision_scope(
    role_paths: Mapping[str, Any],
) -> dict[str, Any]:
    """Declare the complete blocking matrix without fabricating an arm sweep.

    The existing geometry route can only translate a tool-centered box. It must
    not relabel that approximation as a sweep of every articulated Franka link.
    This scope binds the required pairs for a future configuration-sampled/FK
    screen while allowing only the two named finger collider sets to touch the
    designated source mesh.
    """
    if not isinstance(role_paths, Mapping):
        raise ValueError("g0_geometry_full_robot_scope_invalid")

    def paths(name: str, *, root: str | None = None) -> list[str]:
        value = role_paths.get(name)
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
            or not value
            or any(not isinstance(path, str) or not path.startswith("/") for path in value)
            or len(value) != len(set(value))
        ):
            raise ValueError(f"g0_geometry_full_robot_scope_{name}_invalid")
        normalized = sorted(value)
        if root is not None and any(
            path != root and not path.startswith(f"{root}/") for path in normalized
        ):
            raise ValueError(f"g0_geometry_full_robot_scope_{name}_root_invalid")
        return normalized

    shell = paths("source_external_shell_paths", root=SOURCE_PATH)
    wrappers = paths("source_internal_wrapper_paths", root=SOURCE_PATH)
    support = paths("support_collider_paths", root="/World/table")
    beaker1 = paths("beaker1_collider_paths", root=BEAKER1_PATH)
    full_robot = paths("full_robot_collider_paths", root=ROBOT_ROOT_PATH)
    pads = role_paths.get("finger_pad_collider_paths")
    if not isinstance(pads, Mapping) or set(pads) != {"left", "right"}:
        raise ValueError("g0_geometry_full_robot_scope_finger_paths_invalid")
    left = pads["left"]
    right = pads["right"]
    if (
        not isinstance(left, Sequence)
        or isinstance(left, (str, bytes))
        or not isinstance(right, Sequence)
        or isinstance(right, (str, bytes))
    ):
        raise ValueError("g0_geometry_full_robot_scope_finger_paths_invalid")
    left_paths = sorted(left)
    right_paths = sorted(right)
    if (
        not left_paths
        or not right_paths
        or any(not isinstance(path, str) for path in [*left_paths, *right_paths])
        or len([*left_paths, *right_paths]) != len(set([*left_paths, *right_paths]))
        or not set([*left_paths, *right_paths]) <= set(full_robot)
    ):
        raise ValueError("g0_geometry_full_robot_scope_finger_paths_invalid")

    designated_fingers = sorted([*left_paths, *right_paths])
    non_designated = sorted(set(full_robot) - set(designated_fingers))
    if not non_designated:
        raise ValueError("g0_geometry_full_robot_scope_nonfinger_inventory_invalid")

    def pairs(first: Sequence[str], second: Sequence[str]) -> list[list[str]]:
        return [list(sorted((left_path, right_path))) for left_path in first for right_path in second]

    allowed = sorted(pairs(designated_fingers, shell))
    blocking = {
        tuple(pair)
        for targets in (wrappers, support, beaker1)
        for pair in pairs(full_robot, targets)
    }
    blocking.update(tuple(pair) for pair in pairs(non_designated, shell))
    payload = {
        "authority": "real_pbd_g0_full_robot_static_collision_scope_v1",
        "full_robot_collider_paths": full_robot,
        "designated_finger_collider_paths": designated_fingers,
        "non_designated_robot_collider_paths": non_designated,
        "source_shell_paths": shell,
        "source_wrapper_paths": wrappers,
        "table_paths": support,
        "beaker1_paths": beaker1,
        "allowed_source_shell_pairs": allowed,
        "blocking_pairs": [list(pair) for pair in sorted(blocking)],
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def raw_direct_contact_summary() -> dict[str, Any]:
    """Describe this static runner's intentionally absent direct-contact feed."""
    return {
        "authority": "real_pbd_g0_raw_direct_contact_summary_v1",
        "status": "NOT_COLLECTED",
        "reason": "static_geometry_runner_has_no_runtime_contact_observer",
        "does_not_determine_geometry_verdict": True,
    }


def _offset_inventory(stage: Any, role_paths: Mapping[str, Any]) -> dict[str, Any]:
    from pxr import PhysxSchema

    paths = []
    for key in (
        "source_external_shell_paths",
        "source_internal_wrapper_paths",
        "support_collider_paths",
        "beaker1_collider_paths",
        "full_robot_collider_paths",
        "hand_collider_paths",
    ):
        paths.extend(role_paths.get(key, []))
    pads = role_paths.get("finger_pad_collider_paths", {})
    paths.extend(pads.get("left", []))
    paths.extend(pads.get("right", []))
    records = {}
    unresolved = []
    for path in sorted(set(paths)):
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            unresolved.append(path)
            continue
        api = PhysxSchema.PhysxCollisionAPI(prim)
        contact_attr = api.GetContactOffsetAttr()
        rest_attr = api.GetRestOffsetAttr()
        contact = contact_attr.Get() if contact_attr else None
        rest = rest_attr.Get() if rest_attr else None
        raw_contact = repr(contact)
        raw_rest = repr(rest)
        contact_authored = bool(contact_attr and contact_attr.HasAuthoredValueOpinion())
        rest_authored = bool(rest_attr and rest_attr.HasAuthoredValueOpinion())
        try:
            contact = None if contact is None else float(contact)
            rest = None if rest is None else float(rest)
        except (TypeError, ValueError):
            contact = None
            rest = None
        if contact is not None and not math.isfinite(contact):
            contact = None
        if rest is not None and not math.isfinite(rest):
            rest = None
        effective = (
            contact is not None
            and rest is not None
            and contact >= 0.0
            and rest <= contact
        )
        authority = "runtime_effective_physx_cooked_v2" if effective else "unresolved"
        if authority == "unresolved":
            unresolved.append(path)
        records[path] = {
            "contact_offset_m": contact,
            "rest_offset_m": rest,
            "contact_offset_authored": contact_authored,
            "rest_offset_authored": rest_authored,
            "raw_contact_offset": raw_contact,
            "raw_rest_offset": raw_rest,
            "authority": authority,
        }
    return {
        "records": records,
        "unresolved_paths": sorted(set(unresolved)),
        "complete": not unresolved and bool(records),
        "sha256": canonical_json_sha256(
            {"records": records, "unresolved_paths": sorted(set(unresolved))}
        ),
    }


def _stage_units(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    meters = float(UsdGeom.GetStageMetersPerUnit(stage))
    return {
        "meters_per_unit": meters,
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "valid": meters > 0.0,
    }


def _world_bounds(stage: Any, paths: Sequence[str]) -> dict[str, Any]:
    from pxr import Usd, UsdGeom

    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_, UsdGeom.Tokens.proxy, UsdGeom.Tokens.render],
        useExtentsHint=False,
        ignoreVisibility=True,
    )
    result = {}
    for path in paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            result[path] = None
            continue
        bound = cache.ComputeWorldBound(prim).GetRange()
        low = [float(value) for value in bound.GetMin()]
        high = [float(value) for value in bound.GetMax()]
        result[path] = {
            "world_min": low,
            "world_max": high,
            "world_extent": [high[index] - low[index] for index in range(3)],
        }
    return result


def _top_level_collision_roots(paths: Sequence[str]) -> list[str]:
    roots = set()
    for path in paths:
        if not isinstance(path, str) or not path.startswith("/World/"):
            continue
        components = path.split("/")
        if len(components) >= 3 and components[2]:
            roots.add(f"/World/{components[2]}")
    return sorted(roots)


def audit_hidden_cube_collision_treatment(overlay: Path) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    overlay = Path(overlay).resolve()
    if not overlay.is_file():
        raise FileNotFoundError(f"g0_hidden_cube_overlay_missing:{overlay}")
    stage = Usd.Stage.Open(str(overlay))
    if stage is None:
        raise RuntimeError(f"g0_hidden_cube_overlay_invalid:{overlay}")
    def descendants(layer: Any, path: Any) -> list[str]:
        spec = layer.GetPrimAtPath(path)
        if not spec:
            return []
        result = [str(child.path) for child in spec.nameChildren]
        nested = []
        for child in spec.nameChildren:
            nested.extend(descendants(layer, child.path))
        return [*result, *nested]

    prim_paths = sorted(
        {
            path
            for layer in stage.GetLayerStack()
            for spec in layer.rootPrims
            for path in (str(spec.path), *descendants(layer, spec.path))
        }
    )
    changed_paths = []
    changed_attributes = []
    removal_count = 0
    visibility_opinion_count = 0
    collision_disabled_path = None
    for path in prim_paths:
        prim = stage.GetPrimAtPath(path)
        changed = False
        for property_name in prim.GetPropertyNames():
            if property_name == "physics:collisionEnabled":
                changed = True
                if property_name not in changed_attributes:
                    changed_attributes.append(property_name)
            elif "visibility" in property_name:
                visibility_opinion_count += 1
        collision_enabled_attr = prim.GetAttribute("physics:collisionEnabled")
        if collision_enabled_attr and collision_enabled_attr.Get() is False:
            collision_path = str(prim.GetPath())
            if collision_disabled_path is not None:
                raise RuntimeError("g0_hidden_cube_overlay_multiple_disables")
            collision_disabled_path = collision_path
            changed = True
        if changed:
            changed_paths.append(path)
    if prim_paths != ["/World", "/World/Cube"]:
        raise RuntimeError("g0_hidden_cube_overlay_scope_invalid")
    if changed_paths != ["/World/Cube"]:
        raise RuntimeError("g0_hidden_cube_overlay_changes_invalid")
    if collision_disabled_path != "/World/Cube":
        raise RuntimeError("g0_hidden_cube_overlay_collision_disable_missing")
    return {
        "overlay_path": str(overlay),
        "overlay_sha256": sha256_file(overlay),
        "prim_paths": prim_paths,
        "changed_paths": changed_paths,
        "changed_attributes": changed_attributes,
        "collision_disabled_path": collision_disabled_path,
        "removal_count": removal_count,
        "visibility_opinion_count": visibility_opinion_count,
    }


def _prim_provenance(stage: Any, paths: Sequence[str]) -> dict[str, Any]:
    from pxr import UsdGeom, UsdPhysics

    bounds = _world_bounds(stage, paths)
    result = {}
    for path in paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            result[path] = {"valid": False, "world_bounds": bounds.get(path)}
            continue
        stack = []
        for spec in prim.GetPrimStack():
            layer = spec.layer
            stack.append(
                {
                    "layer_identifier": str(layer.identifier),
                    "layer_real_path": str(layer.realPath or ""),
                    "spec_path": str(spec.path),
                    "specifier": str(spec.specifier),
                    "type_name": str(spec.typeName),
                }
            )
        collision = UsdPhysics.CollisionAPI(prim)
        visibility = None
        if prim.IsA(UsdGeom.Imageable):
            visibility = str(UsdGeom.Imageable(prim).ComputeVisibility())
        result[path] = {
            "valid": True,
            "type_name": str(prim.GetTypeName()),
            "applied_schemas": sorted(str(value) for value in prim.GetAppliedSchemas()),
            "collision_enabled": (
                collision.GetCollisionEnabledAttr().Get() if collision else None
            ),
            "visibility": visibility,
            "prim_stack": stack,
            "world_bounds": bounds.get(path),
        }
    return result


def _world_matrix(stage: Any, path: str) -> Any:
    import numpy as np
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"g0_geometry_prim_missing:{path}")
    matrix = np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise RuntimeError(f"g0_geometry_world_matrix_invalid:{path}")
    return matrix


def _cooked_world_box(stage: Any, collider: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    low = np.asarray(collider.get("aabb_local_min_m"), dtype=np.float64)
    high = np.asarray(collider.get("aabb_local_max_m"), dtype=np.float64)
    if (
        low.shape != (3,)
        or high.shape != (3,)
        or not np.isfinite(low).all()
        or not np.isfinite(high).all()
        or np.any(high < low)
    ):
        raise RuntimeError("g0_geometry_cooked_aabb_invalid")
    corners = np.asarray(
        [
            [x, y, z, 1.0]
            for x in (low[0], high[0])
            for y in (low[1], high[1])
            for z in (low[2], high[2])
        ],
        dtype=np.float64,
    )
    world = corners @ _world_matrix(stage, str(collider["path"]))
    world_points = world[:, :3]
    world_min = world_points.min(axis=0)
    world_max = world_points.max(axis=0)
    center = (world_min + world_max) / 2.0
    half_extent = (world_max - world_min) / 2.0
    if not np.isfinite(center).all() or not np.isfinite(half_extent).all():
        raise RuntimeError("g0_geometry_cooked_world_aabb_invalid")
    return {
        "path": str(collider["path"]),
        "world_min_m": world_min.tolist(),
        "world_max_m": world_max.tolist(),
        "center_m": center.tolist(),
        "half_extent_m": half_extent.tolist(),
    }


def _cooked_query_world_bounds(stage: Any, query: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    colliders = query.get("colliders")
    if not isinstance(colliders, Sequence) or isinstance(colliders, (str, bytes)) or not colliders:
        raise RuntimeError("g0_geometry_cooked_query_empty")
    boxes = [_cooked_world_box(stage, collider) for collider in colliders]
    low = np.min(np.asarray([box["world_min_m"] for box in boxes], dtype=np.float64), axis=0)
    high = np.max(np.asarray([box["world_max_m"] for box in boxes], dtype=np.float64), axis=0)
    return {
        "world_min_m": low.tolist(),
        "world_max_m": high.tolist(),
        "world_extent_m": (high - low).tolist(),
        "colliders": boxes,
    }


def _static_collision_paths(stage: Any, body_path: str) -> list[str]:
    from pxr import Usd, UsdPhysics

    body = stage.GetPrimAtPath(body_path)
    if not body or not body.IsValid() or body.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError("g0_geometry_static_body_invalid")
    collision_paths = []
    nested_rigid_bodies = []
    for prim in Usd.PrimRange(body):
        path = str(prim.GetPath())
        if path != body_path and prim.HasAPI(UsdPhysics.RigidBodyAPI):
            nested_rigid_bodies.append(path)
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is not False:
            collision_paths.append(path)
    if nested_rigid_bodies or not collision_paths:
        raise RuntimeError("g0_geometry_static_collision_inventory_invalid")
    return sorted(collision_paths)


def _query_static_cooked_colliders(
    app: Any,
    stage: Any,
    body_path: str,
    *,
    query_colliders: Any,
) -> dict[str, Any]:
    from pxr import Sdf, Usd, UsdPhysics

    collision_paths = _static_collision_paths(stage, body_path)
    session = stage.GetSessionLayer()
    if session is None:
        raise RuntimeError("g0_geometry_static_query_session_missing")
    previous_target = stage.GetEditTarget()
    previous_sublayers = list(session.subLayerPaths)
    temporary_layer = Sdf.Layer.CreateAnonymous("g0_geometry_static_cooked_query.usda")
    if temporary_layer is None:
        raise RuntimeError("g0_geometry_static_query_layer_create_failed")
    raw: Mapping[str, Any] | None = None
    try:
        session.subLayerPaths.insert(0, temporary_layer.identifier)
        stage.SetEditTarget(Usd.EditTarget(temporary_layer))
        body = stage.GetPrimAtPath(body_path)
        rigid_body = UsdPhysics.RigidBodyAPI.Apply(body)
        rigid_body.CreateRigidBodyEnabledAttr(False)
        app.update()
        app.update()
        raw = query_colliders(app, stage, body_path)
    finally:
        stage.SetEditTarget(previous_target)
        session.subLayerPaths = previous_sublayers
        app.update()
        app.update()
    restored_paths = _static_collision_paths(stage, body_path)
    if restored_paths != collision_paths or not isinstance(raw, Mapping):
        raise RuntimeError("g0_geometry_static_query_cleanup_invalid")
    colliders = raw.get("colliders")
    raw_body_path = raw.get("body_path", raw.get("rigid_body_owner_path"))
    if (
        raw_body_path != body_path
        or not isinstance(colliders, Sequence)
        or isinstance(colliders, (str, bytes))
        or sorted(str(collider.get("path")) for collider in colliders)
        != collision_paths
    ):
        raise RuntimeError("g0_geometry_static_query_result_invalid")
    return {
        **dict(raw),
        "body_path": body_path,
        "status": "COMPLETE",
        "query_authority": "runtime_static_physx_cooked_v1",
    }


def _property_query_info_surface(app: Any, stage: Any, timeline: Any) -> dict[str, Any]:
    """Record scalar fields exposed by the sealed PhysX query callback."""
    from omni.physx import get_physx_property_query_interface
    from omni.physx.bindings._physx import PhysxPropertyQueryMode, PhysxPropertyQueryResult
    from pxr import PhysicsSchemaTools, UsdUtils

    surface: dict[str, Any] = {"callback_count": 0, "fields": [], "values": {}}
    finished = {"value": False}

    def scalar(value: Any) -> Any:
        if isinstance(value, bool) or isinstance(value, int):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else repr(value)
        if isinstance(value, str):
            return value
        return None

    def rigid_callback(info: Any) -> None:
        names = sorted(name for name in dir(info) if not name.startswith("_") and "offset" in name.lower())
        surface["fields"] = names
        surface["values"] = {
            name: scalar(getattr(info, name))
            for name in names
            if scalar(getattr(info, name)) is not None
        }

    def collider_callback(_info: Any) -> None:
        return None

    def finished_callback() -> None:
        surface["callback_count"] += 1
        finished["value"] = True

    query = get_physx_property_query_interface()
    query.query_prim(
        stage_id=UsdUtils.StageCache.Get().Insert(stage).ToLongInt(),
        prim_id=PhysicsSchemaTools.sdfPathToInt(
            stage.GetPrimAtPath("/World/Franka/panda_leftfinger") .GetPath()
        ),
        query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS,
        rigid_body_fn=rigid_callback,
        collider_fn=collider_callback,
        finished_fn=finished_callback,
        timeout_ms=60_000,
    )
    for _ in range(8):
        if finished["value"]:
            break
        app.update()
        if timeline.is_playing():
            raise RuntimeError("g0_geometry_timeline_changed_during_info_query")
    surface["finished"] = finished["value"]
    return surface


def _hit_collision_path(hit: Any) -> str:
    from pxr import PhysicsSchemaTools

    value = None
    if isinstance(hit, Mapping):
        value = hit.get("collision")
    else:
        value = getattr(hit, "collision", None)
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return str(PhysicsSchemaTools.intToSdfPath(value))
        except (TypeError, ValueError, RuntimeError):
            return str(value)
    return ""


def _sweep_box_segment(
    scene_query: Any,
    *,
    center: Sequence[float],
    half_extent: Sequence[float],
    direction: Sequence[float],
    distance: float,
) -> list[dict[str, Any]]:
    import carb
    from pxr import Gf

    hits: list[dict[str, Any]] = []
    callback_error: list[str] = []

    def field(hit: Any, *names: str) -> Any:
        for name in names:
            if isinstance(hit, Mapping) and name in hit:
                return hit[name]
            value = getattr(hit, name, None)
            if value is not None:
                return value
        return None

    def callback(hit: Any) -> bool:
        path = _hit_collision_path(hit)
        if not path:
            callback_error.append(
                "g0_geometry_sweep_hit_path_missing:"
                + ",".join(sorted(name for name in dir(hit) if not name.startswith("_")))
            )
            return True
        hit_distance = field(hit, "distance")
        try:
            hit_distance = None if hit_distance is None else float(hit_distance)
        except (TypeError, ValueError):
            hit_distance = None
        hits.append(
            {
                "collision_path": path,
                "distance_m": hit_distance,
                "rigid_body_path": (
                    str(field(hit, "rigid_body", "rigidBody"))
                    if field(hit, "rigid_body", "rigidBody") is not None
                    else None
                ),
                "face_index": (
                    int(field(hit, "face_index", "faceIndex"))
                    if isinstance(field(hit, "face_index", "faceIndex"), int)
                    else None
                ),
            }
        )
        return True

    result = scene_query.sweep_box_all(
        Gf.Vec3f(*[float(value) for value in half_extent]),
        Gf.Vec3f(*[float(value) for value in center]),
        carb.Float4(0.0, 0.0, 0.0, 1.0),
        Gf.Vec3f(*[float(value) for value in direction]),
        float(distance),
        callback,
    )
    if result is False and hits:
        raise RuntimeError("g0_geometry_sweep_result_inconsistent")
    if callback_error:
        raise RuntimeError(callback_error[0])
    return hits


def _role_world_box(stage: Any, role_paths: Sequence[str], queries: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    boxes = []
    for path in role_paths:
        owner_query = next(
            (
                query
                for query in queries.values()
                if any(
                    str(collider.get("path")) == path
                    for collider in query.get("colliders", [])
                )
            ),
            None,
        )
        if owner_query is None:
            raise RuntimeError(f"g0_geometry_role_collider_query_missing:{path}")
        collider = next(
            collider
            for collider in owner_query.get("colliders", [])
            if str(collider.get("path")) == path
        )
        boxes.append(_cooked_world_box(stage, collider))
    low = np.min(np.asarray([box["world_min_m"] for box in boxes]), axis=0)
    high = np.max(np.asarray([box["world_max_m"] for box in boxes]), axis=0)
    return {
        "collider_paths": list(role_paths),
        "world_min_m": low.tolist(),
        "world_max_m": high.tolist(),
        "center_m": ((low + high) / 2.0).tolist(),
        "half_extent_m": ((high - low) / 2.0).tolist(),
    }


def _runtime_gravity_and_solver_settings(stage: Any) -> tuple[list[float], dict[str, Any]]:
    scene = stage.GetPrimAtPath("/World/PhysicsScene")
    if not scene or not scene.IsValid():
        raise RuntimeError("g0_geometry_physics_scene_missing")
    direction_attr = scene.GetAttribute("physics:gravityDirection")
    magnitude_attr = scene.GetAttribute("physics:gravityMagnitude")
    direction = direction_attr.Get() if direction_attr else None
    magnitude = magnitude_attr.Get() if magnitude_attr else None
    if direction is None or magnitude is None:
        raise RuntimeError("g0_geometry_gravity_unresolved")
    gravity = [float(value) * float(magnitude) for value in direction]
    if len(gravity) != 3 or not all(math.isfinite(value) for value in gravity):
        raise RuntimeError("g0_geometry_gravity_invalid")
    names = (
        "physxScene:solverType",
        "physxScene:timeStepsPerSecond",
        "physxScene:broadphaseType",
        "physxScene:enableGPUDynamics",
    )
    settings = {
        "physics_scene_path": "/World/PhysicsScene",
        "gravity_direction": [float(value) for value in direction],
        "gravity_magnitude": float(magnitude),
    }
    for name in names:
        attribute = scene.GetAttribute(name)
        if attribute and attribute.HasAuthoredValueOpinion():
            settings[name] = attribute.Get()
    return gravity, settings


def _swept_clearance_witness(
    *,
    app: Any,
    stage: Any,
    queries: Mapping[str, Any],
    role_paths: Mapping[str, Any],
    offsets: Mapping[str, Any],
    raw_geometry_no_inflation: bool = False,
) -> dict[str, Any]:
    try:
        full_robot_scope = build_full_robot_static_collision_scope(role_paths)
    except ValueError as exc:
        return {
            "authority": "real_pbd_g0_candidate_sweep_set_v1",
            "status": "NOT_RUN",
            "reason": "g0_geometry_full_robot_scope_invalid",
            "scope_error": str(exc),
            "selected": None,
            "candidates": [],
            "passing_candidate_ids": [],
        }
    return {
        "authority": "real_pbd_g0_candidate_sweep_set_v1",
        "status": "NOT_RUN",
        "reason": "g0_geometry_full_robot_fk_sweep_required",
        "full_robot_static_collision_scope": full_robot_scope,
        "selected": None,
        "candidates": [],
        "passing_candidate_ids": [],
    }


def _particle_usd_snapshot(np: Any, stage: Any) -> dict[str, Any]:
    """Hash readable particle USD arrays without claiming live PBD readback."""
    prim = stage.GetPrimAtPath(PARTICLE_PATH)
    if not prim or not prim.IsValid():
        raise RuntimeError("g0_geometry_fk_capability_particle_prim_missing")
    attributes = {}
    point_count = None
    for name in ("points", "positions", "velocities", "ids"):
        attribute = prim.GetAttribute(name)
        if not attribute or not attribute.IsValid():
            continue
        raw = attribute.Get()
        if raw is None:
            continue
        try:
            array = np.asarray(raw, dtype=np.float64)
        except (TypeError, ValueError):
            continue
        if array.size == 0 or not np.isfinite(array).all():
            continue
        if name in {"points", "positions"}:
            if array.ndim != 2 or array.shape[1] != 3:
                continue
            point_count = int(array.shape[0])
        attributes[name] = {
            "shape": list(array.shape),
            "sha256": canonical_json_sha256(array.tolist()),
        }
    payload = {
        "prim_path": PARTICLE_PATH,
        "type_name": str(prim.GetTypeName()),
        "point_count": point_count,
        "attributes": attributes,
        "complete": point_count is not None and bool(attributes),
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _fk_capability_source_state(np: Any, source_reader: Any, stage: Any) -> dict[str, Any]:
    position, orientation = source_reader.get_world_pose()
    payload = {
        "source": {
            "position_m": [float(value) for value in position],
            "orientation_xyzw": [float(value) for value in orientation],
            "linear_velocity_m_s": [
                float(value) for value in source_reader.get_linear_velocity()
            ],
            "angular_velocity_rad_s": [
                float(value) for value in source_reader.get_angular_velocity()
            ],
        },
        "particle_usd_snapshot": _particle_usd_snapshot(np, stage),
    }
    return {
        **payload,
        "source_state_sha256": canonical_json_sha256(payload["source"]),
        "particle_usd_snapshot_sha256": payload["particle_usd_snapshot"]["sha256"],
        "particle_usd_snapshot_complete": payload["particle_usd_snapshot"]["complete"],
    }


def _fk_capability_state_binding(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_state_sha256": state["source_state_sha256"],
        "particle_usd_snapshot_sha256": state["particle_usd_snapshot_sha256"],
        "particle_usd_snapshot_complete": state["particle_usd_snapshot_complete"],
    }


def _instrument_fk_capability_prohibitions(world: Any, robot: Any, source_reader: Any) -> tuple[dict[str, int], Any]:
    counts = {
        "world_step": 0,
        "apply_action": 0,
        "source_pose_writer": 0,
        "collision_filter_write": 0,
    }
    restorers = []

    def forbid(instance: Any, name: str, counter: str) -> None:
        original = getattr(instance, name, None)
        if not callable(original):
            return

        def denied(*_args: Any, **_kwargs: Any) -> None:
            counts[counter] += 1
            raise RuntimeError(f"g0_geometry_fk_capability_prohibited_{counter}")

        setattr(instance, name, denied)
        restorers.append(lambda: setattr(instance, name, original))

    forbid(world, "step", "world_step")
    controller = getattr(robot, "get_articulation_controller", lambda: None)()
    if controller is not None:
        forbid(controller, "apply_action", "apply_action")
    view = getattr(source_reader, "_view", None)
    if view is not None:
        for method in ("set_world_poses", "set_local_poses", "set_default_state"):
            forbid(view, method, "source_pose_writer")

    def restore() -> None:
        for restore_one in reversed(restorers):
            restore_one()

    return counts, restore


def _fk_capability_target(
    np: Any,
    *,
    baseline: Sequence[float],
    lower: Any,
    upper: Any,
    probe: Mapping[str, Any],
) -> tuple[int, float, list[float]]:
    index = int(probe["dof_index"])
    for direction, field in ((1, "positive_delta"), (-1, "negative_delta")):
        delta = float(probe[field])
        candidate = np.asarray(baseline, dtype=np.float64).copy()
        candidate[index] += direction * delta
        if candidate[index] <= upper[index] - 1.0e-8 and candidate[index] >= lower[index] + 1.0e-8:
            return direction, delta, [float(value) for value in candidate.tolist()]
    raise RuntimeError(f"g0_geometry_fk_capability_joint_excursion_unavailable:{index}")


def _full_robot_fk_capability(
    *,
    app: Any,
    stage: Any,
    timeline: Any,
    role_paths: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Exercise every Franka DOF through tensor FK without issuing a motion command."""
    import numpy as np
    import omni.physx
    from omni.isaac.core import World
    from omni.isaac.core.articulations import Articulation
    from omni.isaac.core.prims import RigidPrimView
    from scipy.spatial.transform import Rotation
    from tools.labutopia_fluid import (
        nonformal_controller_static_collision_screen_runtime as static_runtime,
    )
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native

    normalized_plan = fk_capability.validate_plan(plan)
    scope = build_full_robot_static_collision_scope(role_paths)
    world = None
    clear_instance = None
    try:
        world = World(
            physics_dt=1.0 / 600.0,
            rendering_dt=1.0 / 600.0,
            stage_units_in_meters=1.0,
            physics_prim_path="/World/PhysicsScene",
            backend="numpy",
            set_defaults=False,
        )
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
        reset_before = static_runtime._runtime_receipt(world, timeline)
        world.reset()
        reset_after = static_runtime._runtime_receipt(world, timeline)
        physics_view = world.physics_sim_view
        if physics_view is None:
            raise RuntimeError("g0_geometry_fk_capability_tensor_view_missing")
        robot = Articulation(prim_path=ROBOT_ROOT_PATH, name="g0_full_robot_fk_capability")
        robot.initialize(physics_sim_view=physics_view)
        initialized = static_runtime._runtime_receipt(world, timeline)
        if (
            initialized["world_index"] != reset_after["world_index"]
            or initialized["timeline_time_s"] != reset_after["timeline_time_s"]
        ):
            raise RuntimeError("g0_geometry_fk_capability_initialization_advanced")
        baseline_runtime = static_runtime._pause_after_reset(
            app, world, timeline, post_reset_receipt=initialized
        )
        if list(robot.dof_names) != normalized_plan["dof_names"]:
            raise RuntimeError("g0_geometry_fk_capability_dof_names_invalid")
        source_reader = native.RuntimeReadOnlySourceAdapter(RigidPrimView, SOURCE_PATH)
        source_reader.initialize()
        source_before = _fk_capability_source_state(np, source_reader, stage)
        collision_before = _collision_inventory(stage)
        robot_kinematics = static_runtime._robot_kinematic_model(
            np=np,
            Rotation=Rotation,
            Usd=__import__("pxr").Usd,
            UsdGeom=__import__("pxr").UsdGeom,
            UsdPhysics=__import__("pxr").UsdPhysics,
            stage=stage,
            robot=robot,
            expected_simulation_view=physics_view,
            collider_paths=scope["full_robot_collider_paths"],
        )
        lower, upper = static_runtime._joint_position_limits(np, robot)
        baseline_joints = static_runtime._read_joint_positions(np, robot)
        baseline_matrices = static_runtime._robot_collider_world_matrices(
            np, Rotation, robot_kinematics
        )
        counts, restore_prohibitions = _instrument_fk_capability_prohibitions(
            world, robot, source_reader
        )
        samples = []
        try:
            for probe in normalized_plan["probes"]:
                direction, delta, target = _fk_capability_target(
                    np,
                    baseline=baseline_joints,
                    lower=lower,
                    upper=upper,
                    probe=probe,
                )
                readback, _source_matrix, matrices = static_runtime._materialize_configuration(
                    np=np,
                    Rotation=Rotation,
                    Usd=__import__("pxr").Usd,
                    UsdGeom=__import__("pxr").UsdGeom,
                    stage=stage,
                    robot=robot,
                    robot_kinematics=robot_kinematics,
                    source_matrix_before=static_runtime._world_matrix(
                        np, __import__("pxr").Usd, __import__("pxr").UsdGeom, stage, SOURCE_PATH
                    ),
                    world=world,
                    timeline=timeline,
                    baseline=baseline_runtime,
                    target_positions=target,
                    joint_lower_limits=lower,
                    joint_upper_limits=upper,
                    is_hold=False,
                )
                changed = sorted(
                    path
                    for path in matrices
                    if not np.allclose(
                        baseline_matrices[path], matrices[path], rtol=0.0, atol=1.0e-10
                    )
                )
                matrix_payload = {
                    path: np.asarray(matrices[path], dtype=np.float64).tolist()
                    for path in sorted(matrices)
                }
                samples.append(
                    {
                        "dof_index": probe["dof_index"],
                        "selected_direction": direction,
                        "selected_delta": delta,
                        "joint_positions": readback,
                        "changed_collider_paths": changed,
                        "collider_world_matrices_sha256": canonical_json_sha256(matrix_payload),
                        "state": _fk_capability_state_binding(
                            _fk_capability_source_state(np, source_reader, stage)
                        ),
                    }
                )
                static_runtime._materialize_configuration(
                    np=np,
                    Rotation=Rotation,
                    Usd=__import__("pxr").Usd,
                    UsdGeom=__import__("pxr").UsdGeom,
                    stage=stage,
                    robot=robot,
                    robot_kinematics=robot_kinematics,
                    source_matrix_before=static_runtime._world_matrix(
                        np, __import__("pxr").Usd, __import__("pxr").UsdGeom, stage, SOURCE_PATH
                    ),
                    world=world,
                    timeline=timeline,
                    baseline=baseline_runtime,
                    target_positions=baseline_joints,
                    joint_lower_limits=lower,
                    joint_upper_limits=upper,
                    is_hold=False,
                )
        finally:
            restore_prohibitions()
        final_runtime = static_runtime._require_paused_unchanged(
            world, timeline, baseline_runtime, context="g0_full_robot_fk_capability_final"
        )
        source_after = _fk_capability_source_state(np, source_reader, stage)
        collision_after = _collision_inventory(stage)
        if collision_after != collision_before:
            counts["collision_filter_write"] += 1
        observation_payload = {
            "authority": fk_capability.OBSERVATION_AUTHORITY,
            "schema_version": 1,
            "plan_sha256": normalized_plan["sha256"],
            "dof_names": list(robot.dof_names),
            "baseline_joint_positions": baseline_joints,
            "baseline_runtime": baseline_runtime,
            "final_runtime": final_runtime,
            "baseline_state": _fk_capability_state_binding(source_before),
            "restored_joint_positions": static_runtime._read_joint_positions(np, robot),
            "post_reset_physics_advance": {
                "world_index_delta": final_runtime["world_index"] - initialized["world_index"],
                "timeline_time_delta_s": (
                    final_runtime["timeline_time_s"] - initialized["timeline_time_s"]
                ),
                "verified_zero": final_runtime == baseline_runtime,
            },
            "operation_counts": counts,
            "samples": samples,
        }
        observation = {
            **observation_payload,
            "sha256": fk_capability.canonical_json_sha256(observation_payload),
        }
        return {
            "authority": "real_pbd_g0_full_robot_fk_capability_report_v1",
            "status": "COMPLETE",
            "plan": normalized_plan,
            "observation": observation,
            "evaluation": fk_capability.evaluate_observation(
                observation, plan=normalized_plan
            ),
            "reset_bootstrap_advance": {
                "world_index_delta": reset_after["world_index"] - reset_before["world_index"],
                "timeline_time_delta_s": (
                    reset_after["timeline_time_s"] - reset_before["timeline_time_s"]
                ),
            },
            "baseline_state": source_before,
            "final_state": source_after,
            "collision_inventory_before_sha256": collision_before["sha256"],
            "collision_inventory_after_sha256": collision_after["sha256"],
        }
    finally:
        if world is not None:
            clear_instance = getattr(World, "clear_instance", None)
            if callable(clear_instance):
                clear_instance()

def _legacy_tool_center_clearance_witness(
    *,
    app: Any,
    stage: Any,
    queries: Mapping[str, Any],
    role_paths: Mapping[str, Any],
    offsets: Mapping[str, Any],
    raw_geometry_no_inflation: bool = False,
) -> dict[str, Any]:
    """Retain the old tool-centered sweep only as non-authoritative reference."""
    required_targets = [
        *role_paths.get("source_external_shell_paths", []),
        *role_paths.get("source_internal_wrapper_paths", []),
        *role_paths.get("support_collider_paths", []),
        *role_paths.get("beaker1_collider_paths", []),
    ]
    if not required_targets or len(required_targets) != len(set(required_targets)):
        raise RuntimeError("g0_geometry_sweep_target_inventory_invalid")
    offset_records = offsets.get("records", {})
    all_required = [
        *required_targets,
        *role_paths.get("hand_collider_paths", []),
        *role_paths.get("finger_pad_collider_paths", {}).get("left", []),
        *role_paths.get("finger_pad_collider_paths", {}).get("right", []),
    ]
    unresolved_offset_paths = sorted(
        {
            path
            for path in all_required
            if path not in offset_records
            or offset_records[path].get("authority") == "unresolved"
        }
    )
    if unresolved_offset_paths and not raw_geometry_no_inflation:
        return {
            "authority": "real_pbd_g0_candidate_sweep_set_v1",
            "status": "NOT_RUN",
            "reason": "g0_geometry_sweep_offsets_unresolved",
            "unresolved_offset_paths": unresolved_offset_paths,
            "selected": None,
            "candidates": [],
            "passing_candidate_ids": [],
        }
    import numpy as np
    import omni.timeline
    from omni.physx import get_physx_scene_query_interface, get_physx_simulation_interface
    from pxr import Usd, UsdGeom, UsdUtils

    if raw_geometry_no_inflation:
        inflation = 0.0
    else:
        maximum_contact_offset = max(
            float(offset_records[path]["contact_offset_m"]) for path in all_required
        )
        inflation = maximum_contact_offset + CLEARANCE_NUMERICAL_MARGIN_M

    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    source = stage.GetPrimAtPath(SOURCE_PATH)
    tool_center = stage.GetPrimAtPath(TOOL_CENTER_PATH)
    if not source or not source.IsValid() or not tool_center or not tool_center.IsValid():
        raise RuntimeError("g0_geometry_sweep_target_frame_missing")
    source_position = np.asarray(cache.GetLocalToWorldTransform(source).ExtractTranslation(), dtype=np.float64)
    tool_position = np.asarray(
        cache.GetLocalToWorldTransform(tool_center).ExtractTranslation(), dtype=np.float64
    )
    approach = np.asarray(APPROACH_DIRECTION_WORLD, dtype=np.float64)
    source_wrapper_bounds = _cooked_query_world_bounds(
        stage,
        next(
            query
            for query in queries.values()
            if any(
                str(collider.get("path", "")).startswith(WRAPPER_PATH)
                for collider in query.get("colliders", [])
            )
        ),
    )
    wrapper_top_z = float(source_wrapper_bounds["world_max_m"][2])
    pregrasp_position = source_position - approach * PREGRASP_DISTANCE_M
    pregrasp_position[2] = max(
        pregrasp_position[2],
        wrapper_top_z + APPROACH_GRASP_HEIGHT_OFFSET_M,
    )

    role_boxes = {
        "left": _role_world_box(
            stage, role_paths["finger_pad_collider_paths"]["left"], queries
        ),
        "right": _role_world_box(
            stage, role_paths["finger_pad_collider_paths"]["right"], queries
        ),
        "hand": _role_world_box(stage, role_paths["hand_collider_paths"], queries),
    }
    stage_id = UsdUtils.StageCache.Get().Insert(stage).ToLongInt()
    attached = get_physx_simulation_interface().attach_stage(stage_id)
    if attached is not True:
        raise RuntimeError(f"g0_geometry_sweep_stage_attach_unexpected:{attached}")
    scene_query = get_physx_scene_query_interface()
    timeline = omni.timeline.get_timeline_interface()
    if timeline.is_playing() or float(timeline.get_current_time()) != 0.0:
        raise RuntimeError("g0_geometry_sweep_timeline_not_pristine")

    candidates = []
    for family_name, direction_family in APPROACH_CANDIDATE_DIRECTIONS.items():
        lift_direction = np.asarray(direction_family[0], dtype=np.float64)
        lateral_direction = np.asarray(direction_family[1], dtype=np.float64)
        descent_direction = np.asarray(direction_family[2], dtype=np.float64)
        for lift_distance in APPROACH_CANDIDATE_LIFT_DISTANCES_M:
            for lateral_distance in APPROACH_CANDIDATE_LATERAL_DISTANCES_M:
                lift_point = tool_position + lift_direction * lift_distance
                lateral_point = lift_point + lateral_direction * lateral_distance
                descent_target = pregrasp_position + descent_direction * APPROACH_CANDIDATE_DESCENT_MARGIN_M
                legs = [
                    ("lift", tool_position, lift_point),
                    ("lateral", lift_point, lateral_point),
                    ("descent", lateral_point, descent_target),
                ]
                candidate_id = (
                    f"{family_name}_lift_{lift_distance:.2f}_"
                    f"lateral_{lateral_distance:.2f}"
                )
                candidates.append(
                    {
                        "id": candidate_id,
                        "family": family_name,
                        "lift_distance_m": lift_distance,
                        "lateral_distance_m": lateral_distance,
                        "descent_margin_m": APPROACH_CANDIDATE_DESCENT_MARGIN_M,
                        "legs": legs,
                    }
                )

    all_candidate_witnesses = []
    passing_candidates = []
    shell_path = role_paths["source_external_shell_paths"][0]
    for candidate in candidates:
        witness = {
            "authority": "real_pbd_g0_physx_box_sweep_witness_v1",
            "candidate_id": candidate["id"],
            "family": candidate["family"],
            "start_tool_center_world_m": tool_position.tolist(),
            "pregrasp_position_world_m": pregrasp_position.tolist(),
            "legs": [
                {
                    "name": name,
                    "start_m": start.tolist(),
                    "end_m": end.tolist(),
                    "distance_m": float(np.linalg.norm(end - start)),
                }
                for name, start, end in candidate["legs"]
            ],
            "segment_count_per_leg": APPROACH_SEGMENTS_PER_LEG,
            "movers": {},
        }
        if raw_geometry_no_inflation:
            witness["inflation_mode"] = "NONE"
        else:
            witness["inflation_margin_m"] = inflation
        candidate_precontact = {
            "left": float(max(inflation, MIN_PRECONTACT_CLEARANCE_M)),
            "right": float(max(inflation, MIN_PRECONTACT_CLEARANCE_M)),
        }
        candidate_prohibited_sweeps = []
        candidate_failures = []
        for role, box in role_boxes.items():
            start = np.asarray(box["center_m"], dtype=np.float64)
            target_hits: set[str] = set()
            unexpected_hits: set[str] = set()
            leg_records = []
            for leg_name, leg_start, leg_end in candidate["legs"]:
                leg_translation = leg_end - leg_start
                leg_distance = float(np.linalg.norm(leg_translation))
                leg_hits = []
                if leg_distance > 1.0e-9:
                    direction = leg_translation / leg_distance
                    for segment in range(APPROACH_SEGMENTS_PER_LEG):
                        segment_start = start + leg_translation * (
                            float(segment) / APPROACH_SEGMENTS_PER_LEG
                        )
                        segment_end = start + leg_translation * (
                            float(segment + 1) / APPROACH_SEGMENTS_PER_LEG
                        )
                        segment_delta = segment_end - segment_start
                        segment_distance = float(np.linalg.norm(segment_delta))
                        if segment_distance <= 1.0e-12:
                            raise RuntimeError("g0_geometry_sweep_segment_invalid")
                        hits = _sweep_box_segment(
                            scene_query,
                            center=segment_start,
                            half_extent=np.asarray(box["half_extent_m"], dtype=np.float64)
                            + inflation,
                            direction=segment_delta / segment_distance,
                            distance=segment_distance,
                        )
                        hit_paths = sorted({hit["collision_path"] for hit in hits})
                        for path in hit_paths:
                            if path in required_targets:
                                target_hits.add(path)
                            elif not path.startswith("/World/Franka"):
                                unexpected_hits.add(path)
                        leg_hits.append(
                            {
                                "segment": segment,
                                "center_m": segment_start.tolist(),
                                "distance_m": segment_distance,
                                "hit_paths": hit_paths,
                            }
                        )
                leg_records.append(
                    {
                        "name": leg_name,
                        "translation_m": leg_translation.tolist(),
                        "distance_m": leg_distance,
                        "segments": leg_hits,
                    }
                )
                start = start + leg_translation
            witness["movers"][role] = {
                "moving_collider_paths": box["collider_paths"],
                "start_center_m": np.asarray(box["center_m"], dtype=np.float64).tolist(),
                "end_center_m": start.tolist(),
                "half_extent_m": box["half_extent_m"],
                "leg_records": leg_records,
                "unexpected_hit_paths": sorted(unexpected_hits),
            }
            moving_path = box["collider_paths"][0]
            for target_path in required_targets:
                hit_found = target_path in target_hits or unexpected_hits
                if target_path == shell_path:
                    minimum = (
                        float(CLEARANCE_NUMERICAL_MARGIN_M)
                        if target_path in target_hits
                        else float(inflation)
                    )
                else:
                    minimum = 0.0 if hit_found else float(inflation)
                candidate_prohibited_sweeps.append(
                    {
                        "collider_paths": [moving_path, target_path],
                        "minimum_signed_clearance_m": float(minimum),
                        "sample_count": APPROACH_SEGMENTS_PER_LEG * len(candidate["legs"]),
                        "method": (
                            "physx_sweep_box_raw_geometry_v1"
                            if raw_geometry_no_inflation
                            else "physx_sweep_box_all_inflated_v1"
                        ),
                        "moving_role": role,
                        "unexpected_hit_paths": sorted(unexpected_hits),
                    }
                )
            if unexpected_hits:
                candidate_failures.append(f"{role}_unexpected_hits")
            if shell_path in target_hits:
                if role in ("left", "right"):
                    candidate_precontact[role] = float(CLEARANCE_NUMERICAL_MARGIN_M)
        witness["target_hits_by_role"] = {
            role: sorted(target_hits_by_role)
            for role, target_hits_by_role in (
                (role, {
                    path
                    for sweep in candidate_prohibited_sweeps
                    if sweep["moving_role"] == role
                    and sweep["minimum_signed_clearance_m"] == 0.0
                    for path in sweep["collider_paths"]
                    if path in required_targets
                })
                for role in role_boxes
            )
        }
        witness["precontact_pad_shell_clearance_m"] = candidate_precontact
        witness["witness_sha256"] = canonical_json_sha256(witness)
        candidate_result = {
            "candidate": {
                key: value
                for key, value in candidate.items()
                if key != "legs"
            },
            "candidate_target_spec": {
                "candidate_id": candidate["id"],
                "family": candidate["family"],
                "approach_direction_world": approach.tolist(),
                "start_tool_center_world_m": tool_position.tolist(),
                "pregrasp_position_world_m": pregrasp_position.tolist(),
                "legs": witness["legs"],
                "pregrasp_distance_m": PREGRASP_DISTANCE_M,
            },
            "precontact_pad_shell_clearance_m": candidate_precontact,
            "prohibited_sweeps": candidate_prohibited_sweeps,
            "witness": witness,
            "failures": sorted(set(candidate_failures)),
        }
        all_candidate_witnesses.append(candidate_result)
        if not candidate_failures and all(
            value > 0.0
            for side, value in candidate_precontact.items()
            if side in ("left", "right")
        ):
            passing_candidates.append(candidate_result)

    if not passing_candidates:
        return {
            "selected": None,
            "candidates": all_candidate_witnesses,
            "passing_candidate_ids": [],
            "authority": "real_pbd_g0_candidate_sweep_set_v1",
        }
    selected = min(
        passing_candidates,
        key=lambda item: (
            item["candidate"]["lift_distance_m"],
            item["candidate"]["lateral_distance_m"],
            item["candidate"]["id"],
        ),
    )
    return {
        "selected": selected,
        "candidates": all_candidate_witnesses,
        "passing_candidate_ids": [item["candidate"]["id"] for item in passing_candidates],
        "authority": "real_pbd_g0_candidate_sweep_set_v1",
    }


def _raw_geometry_no_inflation_witness(
    sweep: Mapping[str, Any], role_paths: Mapping[str, Any]
) -> dict[str, Any]:
    candidates = sweep.get("candidates") if isinstance(sweep, Mapping) else None
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ValueError("g0_geometry_raw_witness_candidates_invalid")
    prohibited_targets = {
        *role_paths.get("source_internal_wrapper_paths", []),
        *role_paths.get("support_collider_paths", []),
    }
    eligible = []
    for item in candidates:
        if not isinstance(item, Mapping):
            raise ValueError("g0_geometry_raw_witness_candidate_invalid")
        candidate = item.get("candidate")
        target_spec = item.get("candidate_target_spec")
        witness = item.get("witness")
        failures = item.get("failures")
        if (
            not isinstance(candidate, Mapping)
            or not isinstance(candidate.get("id"), str)
            or not candidate["id"]
            or not isinstance(target_spec, Mapping)
            or not isinstance(witness, Mapping)
            or not isinstance(failures, list)
        ):
            raise ValueError("g0_geometry_raw_witness_candidate_invalid")
        movers = witness.get("movers")
        target_hits = witness.get("target_hits_by_role")
        if not isinstance(movers, Mapping) or not isinstance(target_hits, Mapping):
            raise ValueError("g0_geometry_raw_witness_candidate_invalid")
        unexpected_hit_paths = set()
        for record in movers.values():
            paths = record.get("unexpected_hit_paths") if isinstance(record, Mapping) else None
            if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
                raise ValueError("g0_geometry_raw_witness_candidate_invalid")
            unexpected_hit_paths.update(paths)
        prohibited_hit_paths = set()
        for paths in target_hits.values():
            if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
                raise ValueError("g0_geometry_raw_witness_candidate_invalid")
            prohibited_hit_paths.update(path for path in paths if path in prohibited_targets)
        if failures or unexpected_hit_paths or prohibited_hit_paths:
            continue
        eligible.append(
            {
                "candidate": candidate,
                "candidate_target_spec": dict(target_spec),
                "unexpected_hit_paths": sorted(unexpected_hit_paths),
                "prohibited_hit_paths": sorted(prohibited_hit_paths),
            }
        )
    if not eligible:
        return {
            "authority": "real_pbd_g0_raw_geometry_no_inflation_witness_v1",
            "schema_version": 1,
            "status": "NO_ELIGIBLE_CANDIDATE",
            "inflation_mode": "NONE",
            "effective_offset_clearance": "NOT_CLAIMED",
            "candidate_id": None,
            "candidate_target_spec_sha256": None,
            "unexpected_hit_paths": [],
            "prohibited_hit_paths": [],
        }
    selected = min(
        eligible,
        key=lambda item: (
            float(item["candidate"].get("lift_distance_m", math.inf)),
            float(item["candidate"].get("lateral_distance_m", math.inf)),
            item["candidate"]["id"],
        ),
    )
    return {
        "authority": "real_pbd_g0_raw_geometry_no_inflation_witness_v1",
        "schema_version": 1,
        "status": "COMPLETE",
        "inflation_mode": "NONE",
        "effective_offset_clearance": "NOT_CLAIMED",
        "candidate_id": selected["candidate"]["id"],
        "candidate_target_spec_sha256": canonical_json_sha256(
            selected["candidate_target_spec"]
        ),
        "unexpected_hit_paths": selected["unexpected_hit_paths"],
        "prohibited_hit_paths": selected["prohibited_hit_paths"],
    }


def _build_clearance_certificate(
    *,
    asset_closure: Mapping[str, Any],
    fixture: Mapping[str, Any],
    inventory: Mapping[str, Any],
    role_paths: Mapping[str, Any],
    offsets: Mapping[str, Any],
    gravity: Sequence[float],
    solver_settings: Mapping[str, Any],
    sweep: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from utils.real_pbd_grasp_v2 import evaluate_g0_clearance_certificate

    required_paths = [
        *role_paths.get("source_external_shell_paths", []),
        *role_paths.get("source_internal_wrapper_paths", []),
        *role_paths.get("support_collider_paths", []),
        *role_paths.get("beaker1_collider_paths", []),
        *role_paths.get("full_robot_collider_paths", []),
        *role_paths.get("hand_collider_paths", []),
        *role_paths.get("finger_pad_collider_paths", {}).get("left", []),
        *role_paths.get("finger_pad_collider_paths", {}).get("right", []),
    ]
    records = offsets.get("records", {})
    effective_offsets = {}
    for path in required_paths:
        record = records.get(path)
        if not isinstance(record, Mapping) or record.get("authority") == "unresolved":
            raise RuntimeError(f"g0_geometry_certificate_offset_missing:{path}")
        effective_offsets[path] = {
            "contact_offset_m": float(record["contact_offset_m"]),
            "rest_offset_m": float(record["rest_offset_m"]),
            "authority": "runtime_effective_physx_cooked_v2",
        }
    solver_sha256 = canonical_json_sha256(dict(solver_settings))
    selected = sweep.get("selected")
    if selected is None:
        candidate_failures = sorted(
            {
                failure
                for item in sweep.get("candidates", [])
                for failure in item.get("failures", [])
            }
        )
        raise RuntimeError(
            "g0_geometry_no_passing_candidate:"
            + ",".join(candidate_failures)
        )
    target_spec = dict(selected["candidate_target_spec"])
    target_spec["close_endpoint_m"] = 0.028
    target_spec_sha256 = canonical_json_sha256(target_spec)
    candidate = {
        "authority": "real_pbd_g0_candidate_v1",
        "id": selected["candidate"]["id"],
        "target_spec_sha256": target_spec_sha256,
        **target_spec,
        "close_endpoint_m": 0.028,
        "tracking_envelope": {
            "maximum_position_error_m": 0.0005,
            "maximum_orientation_error_degrees": 0.5,
        },
        "precontact_pad_shell_clearance_m": dict(
            selected["precontact_pad_shell_clearance_m"]
        ),
        "prohibited_sweeps": list(selected["prohibited_sweeps"]),
    }
    certificate = {
        "authority": "real_pbd_g0_clearance_certificate_v2",
        "schema_version": 1,
        "fixture": {
            "usd_dependency_closure_sha256": asset_closure[
                "usd_dependency_closure_sha256"
            ],
            "composed_collision_inventory_sha256": inventory["sha256"],
            "source_actor_path": SOURCE_PATH,
            "particle_path": PARTICLE_PATH,
            "source_external_shell_paths": list(
                role_paths["source_external_shell_paths"]
            ),
            "source_internal_wrapper_paths": list(
                role_paths["source_internal_wrapper_paths"]
            ),
            "support_collider_paths": list(role_paths["support_collider_paths"]),
            "beaker1_collider_paths": list(role_paths["beaker1_collider_paths"]),
            "full_robot_collider_paths": list(
                role_paths["full_robot_collider_paths"]
            ),
            "finger_pad_collider_paths": {
                "left": list(role_paths["finger_pad_collider_paths"]["left"]),
                "right": list(role_paths["finger_pad_collider_paths"]["right"]),
            },
            "hand_collider_paths": list(role_paths["hand_collider_paths"]),
        },
        "effective_offsets_m": effective_offsets,
        "load_input_authority": {
            "particle_count": int(fixture["particle_count"]),
            "particle_density_or_mass_authority": "runtime_readback_required_v1",
            "source_dry_mass_kg": float(fixture["source_dry_mass_kg"]),
            "gravity_world_m_s2": [float(value) for value in gravity],
            "solver_settings_sha256": solver_sha256,
            "runtime_filled_load_verified": False,
        },
        "candidate_set": {
            "authority": "g0_predeclared_finite_candidate_set_v1",
            "selected_candidate_id": candidate["id"],
            "candidates": [candidate],
        },
        "witness": {
            "authority": "real_pbd_g0_clearance_witness_bundle_v1",
            "stage_units": {"meters_per_unit": 1.0, "up_axis": "Z"},
            "solver_settings": dict(solver_settings),
            "physx_sweep_witness": dict(selected["witness"]),
            "candidate_sweep_set": {
                "authority": sweep.get("authority"),
                "passing_candidate_ids": list(sweep.get("passing_candidate_ids", [])),
                "candidate_count": len(sweep.get("candidates", [])),
            },
        },
    }
    evaluation = evaluate_g0_clearance_certificate(certificate)
    return certificate, evaluation


def _build_child_geometry_report(
    *,
    app: Any,
    stage: Any,
    timeline: Any,
    asset: Path,
    robot_asset: Path,
    asset_closure: Mapping[str, Any],
    robot_closure: Mapping[str, Any],
    overlay_profile: Mapping[str, Any],
    hidden_cube_treatment: Mapping[str, Any],
    topology: Mapping[str, Any],
    role_paths: Mapping[str, Any],
    queries: Mapping[str, Any],
    offsets: Mapping[str, Any],
    inventory: Mapping[str, Any],
    property_query_surface: Mapping[str, Any],
    world_bounds: Mapping[str, Any],
    table_cooked_query: Mapping[str, Any],
    table_cooked_world_bounds: Mapping[str, Any],
    fixture: Mapping[str, Any],
    gravity: Sequence[float],
    solver_settings: Mapping[str, Any],
    runtime_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    from utils.real_pbd_grasp_v2 import evaluate_grasp_topology_contract

    profile = _validated_overlay_profile(overlay_profile)
    hidden_cube_overlay = _overlay_path(profile, "hidden_cube_collision_disable")
    offset_overlays = [
        item for item in profile["overlay_stack"] if item["id"] == "explicit_contact_offsets"
    ]
    swept_reference = {
        "status": "SKIPPED",
        "method": "raycast_vertical_clearance_v1",
        "reason": "legacy_reference_not_run_after_authoritative_physx_sweep_attach",
    }
    stage_units = _stage_units(stage)
    composed_closure = {
        "fixture": dict(asset_closure),
        "robot": dict(robot_closure),
        "overlay_profile": profile,
        "hidden_cube_treatment": dict(hidden_cube_treatment),
    }
    fixture_identity = canonical_json_sha256(composed_closure)
    topology_evaluation = evaluate_grasp_topology_contract(
        {
            **dict(topology),
            "robot_asset_path": str(robot_asset),
            "robot_asset_sha256": sha256_file(robot_asset),
        }
    )
    query_checks = {
        "source_query_complete": queries.get("source_beaker", {}).get("status") == "COMPLETE",
        "left_finger_query_complete": queries.get("left_finger", {}).get("status") == "COMPLETE",
        "right_finger_query_complete": queries.get("right_finger", {}).get("status") == "COMPLETE",
        "hand_query_complete": queries.get("hand", {}).get("status") == "COMPLETE",
        "table_cooked_query_complete": table_cooked_query.get("status") == "COMPLETE"
        and bool(table_cooked_query.get("colliders")),
    }
    clearance_witness = _swept_clearance_witness(
        app=app,
        stage=stage,
        queries={**dict(queries), "table_cooked": dict(table_cooked_query)},
        role_paths=role_paths,
        offsets=offsets,
    )
    full_robot_static_collision_screen = {
        "status": clearance_witness.get("status"),
        "reason": clearance_witness.get("reason"),
        "scope": clearance_witness.get("full_robot_static_collision_scope"),
    }
    raw_geometry_witness = None
    raw_geometry_sweep = None
    if clearance_witness.get("reason") == "g0_geometry_sweep_offsets_unresolved":
        raw_geometry_sweep = _swept_clearance_witness(
            app=app,
            stage=stage,
            queries={**dict(queries), "table_cooked": dict(table_cooked_query)},
            role_paths=role_paths,
            offsets=offsets,
            raw_geometry_no_inflation=True,
        )
        raw_geometry_witness = _raw_geometry_no_inflation_witness(
            raw_geometry_sweep, role_paths
        )
    selected_witness = clearance_witness.get("selected") or {
        "witness": {"movers": {}},
    }
    unexpected_collision_paths = sorted(
        {
            path
            for mover in selected_witness["witness"]["movers"].values()
            for path in mover.get("unexpected_hit_paths", [])
        }
    )
    unexpected_collision_roots = _top_level_collision_roots(
        unexpected_collision_paths
    )
    unexpected_collision_provenance = _prim_provenance(
        stage, unexpected_collision_roots
    )
    certificate = None
    certificate_evaluation = None
    certificate_error = None
    try:
        certificate, certificate_evaluation = _build_clearance_certificate(
            asset_closure=asset_closure,
            fixture=fixture,
            inventory=inventory,
            role_paths=role_paths,
            offsets=offsets,
            gravity=gravity,
            solver_settings=solver_settings,
            sweep=clearance_witness,
        )
    except (RuntimeError, ValueError) as exc:
        certificate_error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    checks = {
        "runtime_attestation_match": runtime_receipt.get("attestation_status") == "MATCH",
        "timeline_stopped": not bool(timeline.is_playing()),
        "stage_units_source_contract": (
            math.isclose(stage_units["meters_per_unit"], 1.0, rel_tol=0.0, abs_tol=1.0e-12)
            and stage_units["up_axis"] == "Z"
        ),
        "topology_contract": topology_evaluation.get("passed") is True,
        "collision_inventory_present": bool(inventory.get("colliders")),
        "cooked_queries_complete": all(query_checks.values()),
        "effective_offsets_resolved": offsets.get("complete") is True,
        "full_robot_collision_scope_bound": isinstance(
            full_robot_static_collision_screen["scope"], Mapping
        ),
        "full_robot_configuration_sweep_complete": (
            full_robot_static_collision_screen["status"] == "COMPLETE"
        ),
        "signed_swept_clearance_certificate": (
            isinstance(certificate_evaluation, Mapping)
            and certificate_evaluation.get("decision") == DECISION_GO
        ),
    }
    reasons = []
    for key, passed in checks.items():
        if not passed:
            reasons.append(key)
    if not checks["signed_swept_clearance_certificate"]:
        reasons.append("signed_swept_clearance_certificate_not_issued")
    if clearance_witness.get("status") == "NOT_RUN":
        reasons.append(str(clearance_witness.get("reason")))
    if certificate_error is not None:
        reasons.append("clearance_certificate_validation_failed")
    decision = DECISION_GO if all(checks.values()) else DECISION_NO_GO
    fixture_record = {
        "asset_path": str(asset),
        "asset_sha256": sha256_file(asset),
        "robot_asset_path": str(robot_asset),
        "robot_asset_sha256": sha256_file(robot_asset),
        "overlay_profile": profile,
        "overlay_profile_sha256": canonical_json_sha256(profile),
        "hidden_cube_treatment_path": str(hidden_cube_overlay),
        "hidden_cube_treatment_sha256": sha256_file(hidden_cube_overlay),
        "hidden_cube_treatment": dict(hidden_cube_treatment),
        "usd_dependency_closure": composed_closure,
        "usd_dependency_closure_sha256": fixture_identity,
    }
    if offset_overlays:
        offset_overlay = Path(offset_overlays[0]["path"])
        fixture_record.update(
            {
                "offset_treatment_path": str(offset_overlay),
                "offset_treatment_sha256": sha256_file(offset_overlay),
            }
        )
    return {
        "authority": "real_pbd_g0_geometry_child_report_v1",
        "schema_version": 1,
        "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
        "runtime": dict(runtime_receipt),
        "fixture": fixture_record,
        "stage_units": stage_units,
        "topology": topology_evaluation,
        "role_paths": dict(role_paths),
        "cooked_queries": {
            **dict(queries),
            "table_cooked": dict(table_cooked_query),
        },
        "effective_offsets": dict(offsets),
        "collision_inventory": dict(inventory),
        "property_query_info_surface": dict(property_query_surface),
        "world_bounds": dict(world_bounds),
        "table_cooked_query": dict(table_cooked_query),
        "table_cooked_world_bounds": dict(table_cooked_world_bounds),
        "unexpected_collision_paths": unexpected_collision_paths,
        "unexpected_collision_roots": unexpected_collision_roots,
        "unexpected_collision_provenance": unexpected_collision_provenance,
        "reference_clearance_probe": swept_reference,
        "checks": checks,
        "query_checks": query_checks,
        "no_go_reasons": sorted(set(reasons)),
        "clearance_witness": clearance_witness,
        "raw_geometry_witness": raw_geometry_witness,
        "raw_geometry_sweep": raw_geometry_sweep,
        "raw_direct_contact_summary": raw_direct_contact_summary(),
        "full_robot_static_collision_screen": full_robot_static_collision_screen,
        "selected_candidate_id": (
            clearance_witness.get("selected", {}).get("candidate", {}).get("id")
            if clearance_witness.get("selected") is not None
            else None
        ),
        "candidate_failure_summary": {
            item["candidate"]["id"]: list(item.get("failures", []))
            for item in clearance_witness.get("candidates", [])
        },
        "certificate": certificate,
        "certificate_sha256": (
            canonical_json_sha256(certificate)
            if isinstance(certificate, Mapping)
            else None
        ),
        "certificate_evaluation": certificate_evaluation,
        "certificate_error": certificate_error,
        "decision": decision,
    }


def _run_child(args: argparse.Namespace) -> int:
    app = None
    runtime_receipt: dict[str, Any] | None = None
    report: dict[str, Any]
    try:
        _child_marker("begin")
        from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

        overlay_profile = resolve_overlay_profile(args.overlay_profile)
        request = attestation._read_canonical_json(args.execution_request)
        source_paths = _source_paths(overlay_profile)
        request = attestation.verify_execution_request(request, source_paths=source_paths)
        _child_marker("request_verified")
        pre_app_numpy_modules = sorted(
            name for name in sys.modules if name == "numpy" or name.startswith("numpy.")
        )
        from isaacsim import SimulationApp

        app = SimulationApp(
            {"headless": True, "width": 64, "height": 64},
            experience=str(PROFILE_PATH),
        )
        _child_marker("app_started")
        runtime_receipt = attestation.attest_existing_application(
            application=app,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=request,
            source_paths=source_paths,
        )
        attestation.write_canonical_json(args.out_dir / RUNTIME_RECEIPT_BASENAME, runtime_receipt)
        binding = attestation.execution_binding_for_request(request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(
            runtime_receipt, expected_execution_binding=binding
        )
        _child_marker("runtime_attested")

        import omni.timeline
        import omni.usd
        from pxr import UsdGeom
        from tools.labutopia_fluid import run_robot_table_geometry_probe as reference_probe
        from tools.labutopia_fluid.run_real_pbd_grasp_v2_preflight import (
            _static_grasp_topology,
            read_static_fixture,
            usd_dependency_closure,
        )
        from utils.real_pbd_grasp_v2 import evaluate_grasp_topology_contract

        asset = Path(args.asset).resolve()
        robot_asset = ROBOT_ASSET.resolve()
        hidden_cube_overlay = _overlay_path(
            overlay_profile, "hidden_cube_collision_disable"
        )
        hidden_cube_treatment = audit_hidden_cube_collision_treatment(
            hidden_cube_overlay
        )
        fixture = read_static_fixture(asset)
        asset_closure = usd_dependency_closure(asset)
        robot_closure = usd_dependency_closure(robot_asset)
        timeline = omni.timeline.get_timeline_interface()
        usd_context = omni.usd.get_context()
        usd_context.new_stage()
        stage = usd_context.get_stage()
        stage.GetRootLayer().Clear()
        stage.GetSessionLayer().Clear()
        session_overlay_paths = [
            item["path"] for item in overlay_profile["overlay_stack"]
        ]
        for overlay_path in session_overlay_paths:
            stage.GetSessionLayer().subLayerPaths.append(overlay_path)
        if list(stage.GetSessionLayer().subLayerPaths) != session_overlay_paths:
            raise RuntimeError("g0_geometry_overlay_stack_mismatch")
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        from pxr import Gf

        world_root = stage.DefinePrim("/World", "Xform")
        world_root.GetReferences().AddReference(str(asset))
        franka = stage.DefinePrim("/World/Franka", "Xform")
        franka.GetReferences().AddReference(str(robot_asset))
        translate = franka.GetAttribute("xformOp:translate")
        if translate and translate.IsValid():
            translate.Set(Gf.Vec3d(-0.4, 0.0, 0.71))
        else:
            UsdGeom.Xformable(franka).AddTranslateOp().Set(Gf.Vec3d(-0.4, 0.0, 0.71))
        baseline = {"is_playing": bool(timeline.is_playing()), "time_s": float(timeline.get_current_time())}
        for _ in range(60):
            app.update()
            if timeline.is_playing() or float(timeline.get_current_time()) != baseline["time_s"]:
                raise RuntimeError("g0_geometry_timeline_changed_while_loading")
        _child_marker("stage_loaded")

        topology = _static_grasp_topology(stage)
        role_paths = _role_paths(stage, topology)
        cube = stage.GetPrimAtPath("/World/Cube")
        cube_collision_enabled = cube.GetAttribute("physics:collisionEnabled").Get()
        if cube_collision_enabled is not False:
            raise RuntimeError("g0_geometry_hidden_cube_collision_still_enabled")
        queries = {
            name: reference_probe._query_body_cooked_colliders(app, stage, path, timeline)
            for name, path in reference_probe.BODY_PATHS.items()
        }
        table_cooked_query = _query_static_cooked_colliders(
            app,
            stage,
            TABLE_BODY_PATH,
            query_colliders=lambda query_app, query_stage, query_body: reference_probe._query_body_cooked_colliders(
                query_app,
                query_stage,
                query_body,
                timeline,
            ),
        )
        offsets = _offset_inventory(stage, role_paths)
        inventory = _collision_inventory(stage)
        property_query_surface = _property_query_info_surface(app, stage, timeline)
        gravity, solver_settings = _runtime_gravity_and_solver_settings(stage)
        world_bounds = _world_bounds(
            stage,
            [
                SOURCE_PATH,
                BEAKER1_PATH,
                ROBOT_ROOT_PATH,
                LEFT_FINGER_PATH,
                RIGHT_FINGER_PATH,
                HAND_PATH,
                TABLE_PATH,
            ],
        )
        table_cooked_world_bounds = _cooked_query_world_bounds(stage, table_cooked_query)
        report = _build_child_geometry_report(
            app=app,
            stage=stage,
            timeline=timeline,
            asset=asset,
            robot_asset=robot_asset,
            asset_closure=asset_closure,
            robot_closure=robot_closure,
            overlay_profile=overlay_profile,
            hidden_cube_treatment=hidden_cube_treatment,
            topology=topology,
            role_paths=role_paths,
            queries=queries,
            offsets=offsets,
            inventory=inventory,
            property_query_surface=property_query_surface,
            world_bounds=world_bounds,
            table_cooked_query=table_cooked_query,
            table_cooked_world_bounds=table_cooked_world_bounds,
            fixture=fixture,
            gravity=gravity,
            solver_settings=solver_settings,
            runtime_receipt=runtime_receipt,
        )
        _child_marker("report_built")
    except BaseException as exc:
        _child_marker(f"error:{type(exc).__name__}:{exc}")
        report = _runtime_error_report(exc, runtime_receipt)
    _child_marker("writing_report")
    _write_create_only(args.out_dir / CHILD_REPORT_BASENAME, canonical_json_bytes(report))
    _child_marker("report_written")
    if app is not None:
        _child_marker("closing_app")
        try:
            app.close()
        except BaseException as exc:
            _child_marker(f"close_error:{type(exc).__name__}:{exc}")
        else:
            _child_marker("app_closed")
    return 2 if report.get("decision") != DECISION_GO else 0


def _run_parent(args: argparse.Namespace) -> int:
    import tools.labutopia_fluid.attest_isaac41_effective_runtime as attestation
    from utils.real_pbd_grasp_v2 import evaluate_g0_clearance_certificate

    overlay_profile = resolve_overlay_profile(args.overlay_profile)
    v9_config_binding = (
        _v9_diagnostic_config_binding(overlay_profile)
        if overlay_profile["id"] == V7_CUBE_ONLY_OVERLAY_PROFILE
        else None
    )
    args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    source_paths = _source_paths(overlay_profile)
    source_before = attestation.capture_source_identity(source_paths)
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.out_dir / "execution_request.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.out_dir / "runtime")
    environment["NVIDIA_VISIBLE_DEVICES"] = "4"
    environment.pop("CUDA_VISIBLE_DEVICES", None)
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--asset",
        str(args.asset.resolve()),
        "--out-dir",
        str(args.out_dir.resolve()),
        "--execution-request",
        str(request_path.resolve()),
        "--overlay-profile",
        args.overlay_profile,
    ]
    stdout_path = args.out_dir / STDOUT_BASENAME
    stderr_path = args.out_dir / STDERR_BASENAME
    child_pid = None
    returncode = None
    verification_failure = None
    receipt = None
    parent_clearance_evaluation = None
    v9_diagnostic_eligibility = None
    v9_diagnostic_eligibility_path = (
        args.out_dir / V9_DIAGNOSTIC_ELIGIBILITY_BASENAME
    )
    parent_report: dict[str, Any]
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = process.pid
            try:
                returncode = process.wait(timeout=float(args.timeout_seconds))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait()
                raise RuntimeError("g0_geometry_child_timeout")
        child_report = _read_canonical(args.out_dir / CHILD_REPORT_BASENAME)
        receipt = attestation._read_canonical_json(args.out_dir / RUNTIME_RECEIPT_BASENAME)
        binding = attestation.execution_binding_for_request(request, child_pid=child_pid)
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        if child_report.get("runtime", {}).get("attestation_status") != "MATCH":
            raise RuntimeError("g0_geometry_runtime_attestation_not_matched")
        require_child_overlay_profile(child_report, overlay_profile)
        if child_report.get("decision") not in {DECISION_NO_GO, DECISION_GO}:
            raise RuntimeError("g0_geometry_child_decision_invalid")
        certificate = child_report.get("certificate")
        if not isinstance(certificate, Mapping):
            parent_report = {
                **child_report,
                "authority": "real_pbd_g0_geometry_parent_report_v1",
                "decision": DECISION_NO_GO,
                "child_authority": child_report.get("authority"),
                "parent_recomputed": True,
                "parent_clearance_evaluation": None,
                "no_go_reasons": sorted(
                    set(child_report.get("no_go_reasons", []))
                    | {"signed_swept_clearance_certificate_missing"}
                ),
            }
        else:
            certificate_sha256 = attestation.canonical_json_sha256(certificate)
            if child_report.get("certificate_sha256") != certificate_sha256:
                raise RuntimeError("g0_geometry_certificate_hash_mismatch")
            certificate_fixture = certificate.get("fixture")
            child_fixture = child_report.get("fixture", {})
            composed_closure = child_fixture.get("usd_dependency_closure", {})
            if (
                not isinstance(certificate_fixture, Mapping)
                or not isinstance(composed_closure, Mapping)
                or not isinstance(composed_closure.get("fixture"), Mapping)
                or certificate_fixture.get("usd_dependency_closure_sha256")
                != composed_closure["fixture"].get("usd_dependency_closure_sha256")
                or certificate_fixture.get("composed_collision_inventory_sha256")
                != child_report.get("collision_inventory", {}).get("sha256")
            ):
                raise RuntimeError("g0_geometry_certificate_fixture_binding_invalid")
            parent_clearance_evaluation = evaluate_g0_clearance_certificate(certificate)
            checks = child_report.get("checks")
            if not isinstance(checks, Mapping) or not checks or any(
                type(value) is not bool for value in checks.values()
            ):
                raise RuntimeError("g0_geometry_child_checks_invalid")
            parent_decision = (
                DECISION_GO
                if parent_clearance_evaluation.get("decision") == DECISION_GO
                and all(checks.values())
                else DECISION_NO_GO
            )
            parent_report = {
                **child_report,
                "authority": "real_pbd_g0_geometry_parent_report_v1",
                "decision": parent_decision,
                "child_authority": child_report.get("authority"),
                "parent_recomputed": True,
                "parent_clearance_evaluation": parent_clearance_evaluation,
            }
        if v9_config_binding is not None:
            v9_diagnostic_eligibility = _build_v9_diagnostic_eligibility(
                child_report=child_report,
                runtime_receipt=receipt,
                execution_request=request,
                overlay_profile=overlay_profile,
                config_binding=v9_config_binding,
            )
            if v9_diagnostic_eligibility is not None:
                _write_create_only(
                    v9_diagnostic_eligibility_path,
                    canonical_json_bytes(v9_diagnostic_eligibility),
                )
                parent_report = {
                    **parent_report,
                    "v9_diagnostic_eligibility": v9_diagnostic_eligibility,
                }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        child_report = {
            "authority": "real_pbd_g0_geometry_parent_report_v1",
            "schema_version": 1,
            "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
            "decision": "RUNTIME_BLOCKED",
            "fatal_error": verification_failure,
        }
        parent_report = child_report
    manifest = {
        "authority": "real_pbd_g0_geometry_run_manifest_v1",
        "schema_version": 1,
        "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
        "decision": parent_report.get("decision", "RUNTIME_BLOCKED"),
        "command": command,
        "source_before": source_before,
        "source_after": attestation.capture_source_identity(source_paths),
        "asset_path": str(args.asset.resolve()),
        "asset_sha256": sha256_file(args.asset.resolve()),
        "robot_asset_path": str(ROBOT_ASSET.resolve()),
        "robot_asset_sha256": sha256_file(ROBOT_ASSET.resolve()),
        "overlay_profile": overlay_profile,
        "overlay_profile_sha256": canonical_json_sha256(overlay_profile),
        "v9_diagnostic_config_binding": v9_config_binding,
        "profile_path": str(PROFILE_PATH.resolve()),
        "profile_sha256": sha256_file(PROFILE_PATH.resolve()),
        "execution_request_sha256": attestation.canonical_json_sha256(request),
        "runtime_receipt_sha256": (
            attestation.canonical_json_sha256(receipt)
            if isinstance(receipt, Mapping)
            else None
        ),
        "sanitized_environment_sha256": attestation.canonical_json_sha256(
            dict(sorted(environment.items()))
        ),
        "child_pid": child_pid,
        "child_returncode": returncode,
        "child_report": _artifact(args.out_dir / CHILD_REPORT_BASENAME, root=args.out_dir),
        "runtime_receipt": _artifact(args.out_dir / RUNTIME_RECEIPT_BASENAME, root=args.out_dir),
        "v9_diagnostic_eligibility": _artifact(
            v9_diagnostic_eligibility_path, root=args.out_dir
        ),
        "stdout": _artifact(stdout_path, root=args.out_dir),
        "stderr": _artifact(stderr_path, root=args.out_dir),
        "verification_failure": verification_failure,
        "certificate_sha256": parent_report.get("certificate_sha256"),
        "parent_clearance_decision": (
            parent_clearance_evaluation.get("decision")
            if isinstance(parent_clearance_evaluation, Mapping)
            else None
        ),
    }
    report_path = args.out_dir / "report.json"
    _write_create_only(report_path, canonical_json_bytes(parent_report))
    manifest["parent_report"] = _artifact(report_path, root=args.out_dir)
    attestation.write_canonical_json(args.out_dir / RUN_MANIFEST_BASENAME, manifest)
    print(
        f"real PBD G0 geometry decision={parent_report.get('decision')} out={report_path}",
        flush=True,
    )
    return 2 if parent_report.get("decision") == "RUNTIME_BLOCKED" else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, default=DEFAULT_ASSET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--overlay-profile",
        choices=tuple(_OVERLAY_PROFILE_STACKS),
        default=LEGACY_OVERLAY_PROFILE,
    )
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--execution-request", type=Path)
    args = parser.parse_args(argv)
    args.asset = args.asset.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.asset.is_file():
        parser.error(f"asset not found: {args.asset}")
    if args.child:
        if args.execution_request is None or not args.execution_request.is_file():
            parser.error("--child requires --execution-request")
    elif args.out_dir.exists():
        parser.error(f"output already exists: {args.out_dir}")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_child(args) if args.child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())

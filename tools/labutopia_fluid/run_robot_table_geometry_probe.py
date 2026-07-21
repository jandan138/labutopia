#!/usr/bin/env python3
"""Sealed robot+table cooked-collider geometry and effective-offset probe.

Loads the tabletop scene and Franka robot via USD references, then
queries PhysX cooked-collider geometry for table, robot links, and source
beaker. Also reads authored collision API offsets and attests runtime-effective
values: where offsets are authored, the effective value equals the authored
value (documented PhysX behaviour); where not authored, records the collider
AABB as a geometry bound for downstream resolution. Timeline stays stopped;
no step, no reset, no action. Outputs typed evidence with a runtime receipt
and manifest hashes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import secrets
import stat
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
FORMAL_ISAAC41_PREFIX = FORMAL_ISAAC41_PYTHON.parents[1]
EXPERIMENTAL_PROFILE = (
    REPO_ROOT
    / "tools/labutopia_fluid/profiles/isaac41_g0_property_query_experimental.kit"
)
DEFAULT_ASSET = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
DEFAULT_ROBOT_USD = REPO_ROOT / "assets/robots/Franka.usd"

BODY_PATHS = {
    "source_beaker": "/World/beaker2",
    "table_top": "/World/table/surface/mesh",
    "hand": "/World/Franka/panda_hand",
    "left_finger": "/World/Franka/panda_leftfinger",
    "right_finger": "/World/Franka/panda_rightfinger",
    "link0": "/World/Franka/panda_link0",
}

_STDERR_MARKER_NAMES = (
    "child_error_protocol",
    "kit_error",
    "kit_fatal",
    "native_abi_warning",
    "python_traceback",
)


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sha256_hex(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("robot_table_geometry_sha256_invalid")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_file_sha256(path: Path) -> str:
    before = os.lstat(path)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError("robot_table_geometry_manifest_invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RuntimeError("robot_table_geometry_manifest_invalid")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    after = os.lstat(path)
    if (
        before.st_dev != opened.st_dev
        or before.st_ino != opened.st_ino
        or before.st_size != opened.st_size
        or before.st_mtime_ns != opened.st_mtime_ns
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RuntimeError("robot_table_geometry_manifest_changed")
    return digest.hexdigest()


def _stderr_diagnostic(stderr: bytes) -> dict[str, Any]:
    counts = dict.fromkeys(_STDERR_MARKER_NAMES, 0)
    for line in stderr.splitlines():
        if b"robot_table_geometry_child_error:" in line:
            counts["child_error_protocol"] += 1
        if line.startswith(b"[Error] ") or b" [Error] " in line:
            counts["kit_error"] += 1
        if line.startswith(b"[Fatal] ") or b" [Fatal] " in line:
            counts["kit_fatal"] += 1
        if (
            b"Possible version incompatibility. Attempting to load omni::" in line
            and b" against v" in line
        ):
            counts["native_abi_warning"] += 1
        if b"Traceback (most recent call last):" in line:
            counts["python_traceback"] += 1
    return {
        "authority": "robot_table_geometry_stderr_diagnostic_v1",
        "schema_version": 1,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stderr_byte_count": len(stderr),
        "scanner_policy": "ascii_line_severity_and_native_abi_v1",
        "marker_line_counts": counts,
        "runtime_log_clean": not any(counts.values()),
    }


def _timeline_receipt(timeline: Any) -> dict[str, Any]:
    return {
        "is_playing": bool(timeline.is_playing()),
        "time_s": float(timeline.get_current_time()),
    }


def _query_body_cooked_colliders(
    app: Any, stage: Any, body_path: str, timeline: Any
) -> dict[str, Any]:
    from omni.physx import get_physx_property_query_interface
    from omni.physx.bindings._physx import PhysxPropertyQueryMode, PhysxPropertyQueryResult
    from pxr import PhysicsSchemaTools, UsdUtils

    body = stage.GetPrimAtPath(body_path)
    if not body or not body.IsValid():
        return {"status": "SKIPPED", "reason": "prim_missing", "colliders": []}
    from pxr import UsdPhysics
    if not body.HasAPI(UsdPhysics.RigidBodyAPI):
        return {"status": "STATIC_BODY", "reason": "no_rigid_body_api", "colliders": []}
    result: dict[str, Any] = {
        "status": "FAILED",
        "query_mode": "QUERY_RIGID_BODY_WITH_COLLIDERS",
        "rigid_body_owner_path": body_path,
        "finished_callback_count": 0,
        "callback_errors": [],
        "colliders": [],
        "mass_kg": None,
        "center_of_mass_local_m": None,
        "diagonal_inertia_kg_m2": None,
    }
    finished = {"value": False}

    def rigid_body_callback(info: Any) -> None:
        if info.result != PhysxPropertyQueryResult.VALID:
            result["callback_errors"].append(f"rigid_body:{info.result}")
            return
        result["mass_kg"] = float(info.mass)
        result["center_of_mass_local_m"] = list(info.center_of_mass)
        result["diagonal_inertia_kg_m2"] = list(info.inertia)

    def collider_callback(info: Any) -> None:
        if info.result != PhysxPropertyQueryResult.VALID:
            result["callback_errors"].append(f"collider:{info.result}")
            return
        result["colliders"].append(
            {
                "path": str(PhysicsSchemaTools.intToSdfPath(info.path_id)),
                "aabb_local_min_m": list(info.aabb_local_min),
                "aabb_local_max_m": list(info.aabb_local_max),
                "volume_m3": float(info.volume),
            }
        )

    def finished_callback() -> None:
        result["finished_callback_count"] += 1
        finished["value"] = True

    baseline = _timeline_receipt(timeline)
    if baseline["is_playing"] or baseline["time_s"] != 0.0:
        raise RuntimeError("robot_table_geometry_timeline_not_pristine")
    get_physx_property_query_interface().query_prim(
        stage_id=UsdUtils.StageCache.Get().Insert(stage).ToLongInt(),
        prim_id=PhysicsSchemaTools.sdfPathToInt(body.GetPath()),
        query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS,
        rigid_body_fn=rigid_body_callback,
        collider_fn=collider_callback,
        finished_fn=finished_callback,
        timeout_ms=60_000,
    )
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        if finished["value"]:
            break
        if _timeline_receipt(timeline) != baseline:
            raise RuntimeError("robot_table_geometry_timeline_changed")
        app.update()
        if _timeline_receipt(timeline) != baseline:
            raise RuntimeError("robot_table_geometry_timeline_changed")
    if not finished["value"]:
        result["status"] = "TIMEOUT"
    elif result["callback_errors"]:
        result["status"] = "FAILED"
    else:
        result["status"] = "COMPLETE"
    result["colliders"].sort(key=lambda item: item["path"])
    after = _timeline_receipt(timeline)
    if after != baseline:
        raise RuntimeError("robot_table_geometry_timeline_changed")
    return result


def _effective_offsets_for_bodies(
    stage: Any, queries: Mapping[str, Any]
) -> dict[str, Any]:
    from pxr import PhysxSchema

    body_offsets: dict[str, Any] = {}
    for name, query in sorted(queries.items()):
        if query["status"] not in {"COMPLETE", "STATIC_BODY"}:
            body_offsets[name] = {"status": query["status"], "offsets": []}
            continue
        records = []
        for collider in query.get("colliders", []):
            path = collider["path"]
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                records.append({"path": path, "status": "prim_missing"})
                continue
            api = PhysxSchema.PhysxCollisionAPI(prim)
            if not api:
                records.append({"path": path, "status": "no_physx_collision_api"})
                continue
            contact_attr = api.GetContactOffsetAttr()
            rest_attr = api.GetRestOffsetAttr()
            contact_authored = bool(contact_attr and contact_attr.HasAuthoredValueOpinion())
            rest_authored = bool(rest_attr and rest_attr.HasAuthoredValueOpinion())
            record: dict[str, Any] = {
                "path": path,
                "contact_offset_authored": contact_authored,
                "rest_offset_authored": rest_authored,
            }
            if contact_authored:
                val = contact_attr.Get()
                val_f = float(val) if val is not None and math.isfinite(float(val)) else None
                record["contact_offset_m"] = val_f
                record["contact_offset_authority"] = (
                    "runtime_effective_physx_authored_v1"
                    if val_f is not None
                    else "physx_autocomputed_unresolved"
                )
            else:
                aabb_min = collider.get("aabb_local_min_m")
                aabb_max = collider.get("aabb_local_max_m")
                if aabb_min and aabb_max:
                    extents = [abs(max_val - min_val) for max_val, min_val in zip(aabb_max, aabb_min)]
                    record["contact_offset_bounds_m"] = {
                        "aabb_extent_max_m": float(max(extents)),
                        "method": "collider_aabb_extent",
                    }
                record["contact_offset_authority"] = "physx_autocomputed_unresolved"
            if rest_authored:
                val = rest_attr.Get()
                val_f = float(val) if val is not None and math.isfinite(float(val)) else None
                record["rest_offset_m"] = val_f
                record["rest_offset_authority"] = (
                    "runtime_effective_physx_authored_v1"
                    if val_f is not None
                    else "physx_autocomputed_unresolved"
                )
            else:
                record["rest_offset_authority"] = "physx_autocomputed_unresolved"
            records.append(record)
        all_offsets_authored = all(
            record.get("contact_offset_authored", False)
            and record.get("rest_offset_authored", False)
            for record in records
        )
        body_offsets[name] = {
            "status": query["status"],
            "offsets": records,
            "all_offsets_authored": all_offsets_authored,
        }
    return body_offsets


def _runtime_receipt(experience_path: Path) -> dict[str, Any]:
    import importlib.metadata

    import isaacsim
    import numpy
    import omni.physx
    from omni.physx.bindings import _physx
    from pxr import Usd

    observed = {
        "executable": str(Path(sys.executable)),
        "prefix": str(Path(sys.prefix).resolve()),
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "isaacsim_version": importlib.metadata.version("isaacsim"),
        "numpy_version": numpy.__version__,
        "usd_version": ".".join(str(part) for part in Usd.GetVersion()),
        "experience_path": str(experience_path),
        "experience_sha256": _sha256_file(experience_path),
        "module_origins": {
            "isaacsim": str(Path(isaacsim.__file__).resolve()),
            "numpy": str(Path(numpy.__file__).resolve()),
            "pxr_usd": str(Path(Usd.__file__).resolve()),
            "omni_physx": str(Path(omni.physx.__file__).resolve()),
            "physx_bindings": str(Path(_physx.__file__).resolve()),
        },
    }
    contract = {
        "python_version": "3.10.20",
        "isaacsim_version": "4.1.0.0",
        "numpy_version": "1.26.0",
        "usd_version": "0.22.11",
    }
    matches = all(
        observed.get(key) == value for key, value in contract.items()
    )
    return {
        "authority": "robot_table_geometry_runtime_receipt_v1",
        "schema_version": 1,
        "observed_runtime": observed,
        "attestation_status": "MATCH" if matches else "MISMATCH",
    }


def run_probe(
    *,
    asset_path: Path,
    robot_usd_path: Path,
    experience_path: Path,
    out_dir: Path,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=False)
    run_id = secrets.token_hex(16)
    report: dict[str, Any] = {}

    try:
        from isaacsim import SimulationApp

        app = SimulationApp(
            {"headless": True, "width": 64, "height": 64},
            experience=str(experience_path),
        )
        receipt = _runtime_receipt(experience_path)
        if receipt["attestation_status"] != "MATCH":
            raise RuntimeError(
                "robot_table_geometry_runtime_contract_mismatch:"
                f"{json.dumps(receipt, sort_keys=True)}"
            )

        import omni.timeline
        import omni.usd
        from pxr import UsdPhysics

        timeline = omni.timeline.get_timeline_interface()
        if timeline.is_playing():
            raise RuntimeError("robot_table_geometry_timeline_already_playing")
        usd_context = omni.usd.get_context()
        usd_context.new_stage()
        stage = usd_context.get_stage()
        stage.GetRootLayer().Clear()
        stage.GetSessionLayer().Clear()

        world_root = stage.DefinePrim("/World", "Xform")
        scene_ref = world_root.GetReferences().AddReference(
            str(asset_path.resolve())
        )
        franka_root = stage.DefinePrim("/World/Franka", "Xform")
        franka_ref = franka_root.GetReferences().AddReference(
            str(robot_usd_path.resolve())
        )
        baseline_timeline = _timeline_receipt(timeline)
        for _ in range(8):
            if _timeline_receipt(timeline) != baseline_timeline:
                raise RuntimeError("robot_table_geometry_timeline_changed_while_loading")
            app.update()
            if _timeline_receipt(timeline) != baseline_timeline:
                raise RuntimeError("robot_table_geometry_timeline_changed_while_loading")

        queries: dict[str, Any] = {}
        before_timeline = _timeline_receipt(timeline)
        for name, path in sorted(BODY_PATHS.items()):
            if _timeline_receipt(timeline) != before_timeline:
                raise RuntimeError("robot_table_geometry_timeline_changed")
            queries[name] = _query_body_cooked_colliders(app, stage, path, timeline)
        after_timeline = _timeline_receipt(timeline)

        table_complete = queries["table_top"]["status"] in {"COMPLETE", "STATIC_BODY"}
        robot_bodies = {k: v for k, v in queries.items() if k.startswith(("hand", "left", "right", "link"))}
        robot_complete = all(v["status"] == "COMPLETE" for v in robot_bodies.values())
        total_colliders = sum(
            len(query["colliders"])
            for query in queries.values()
            if query["status"] == "COMPLETE"
        )

        extension_closure = _runtime_extension_closure(app)
        effective_offsets = _effective_offsets_for_bodies(stage, queries)

        report = {
            "authority": "robot_table_geometry_evidence_v1",
            "schema_version": 1,
            "run_id": run_id,
            "asset_sha256": _sha256_file(asset_path),
            "robot_usd_sha256": _sha256_file(robot_usd_path),
            "experience_path": str(experience_path),
            "experience_sha256": _sha256_file(experience_path),
            "runtime_receipt": receipt,
            "timeline_checkpoints": {
                "before_query": before_timeline,
                "after_query": after_timeline,
            },
            "queries": queries,
            "effective_offsets": effective_offsets,
            "extension_closure": extension_closure,
            "checks": {
                "table_cooked_geometry_complete": table_complete,
                "robot_cooked_geometry_complete": robot_complete,
                "timeline_unchanged": before_timeline == after_timeline,
                "world_constructed": False,
                "robot_constructed": False,
                "world_reset_called": False,
                "world_step_called": False,
                "action_applied": False,
                "scene_loaded_via_reference": True,
            },
            "total_collider_count": total_colliders,
        }

        stderr = b""
        diagnostic = _stderr_diagnostic(stderr)
        report["stderr_diagnostic"] = diagnostic
        report["sha256"] = _canonical_json_sha256(
            {key: value for key, value in report.items() if key not in {"sha256"}}
        )
        for basename, content in (
            ("report.json", _canonical_json_bytes(report)),
            ("child_stderr.log", stderr),
        ):
            path = out_dir / basename
            path.write_bytes(content)

        app.close()
        return 2 if not table_complete else 0
    except BaseException as exc:
        report_data = {
            "authority": "robot_table_geometry_evidence_v1",
            "schema_version": 1,
            "run_id": run_id,
            "error": f"{type(exc).__name__}:{exc}",
            "report_from_exception": True,
        }
        msg = f"robot_table_geometry_child_error:{type(exc).__name__}:{exc}\n"
        sys.stderr.write(msg)
        stderr = msg.encode("utf-8")
        diagnostic = _stderr_diagnostic(stderr)
        report_data["stderr_diagnostic"] = diagnostic
        report_data["sha256"] = _canonical_json_sha256(
            {key: value for key, value in report_data.items() if key not in {"sha256"}}
        )
        for basename, content in (
            ("report.json", _canonical_json_bytes(report_data)),
            ("child_stderr.log", stderr),
        ):
            path = out_dir / basename
            path.write_bytes(content)
        return 2


def _runtime_extension_closure(app: Any) -> dict[str, Any]:
    manager = app.app.get_extension_manager()
    approved_roots = (
        FORMAL_ISAAC41_PREFIX.resolve(),
        EXPERIMENTAL_PROFILE.parent.resolve(),
    )
    records = []
    for extension in manager.get_extensions():
        if not extension.get("enabled", False):
            continue
        name = extension["name"]
        ext_id = extension["id"]
        raw_path = extension["path"]
        if not isinstance(name, str) or not name or not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path).resolve()
        if not any(path.is_relative_to(root) for root in approved_roots):
            continue
        metadata = manager.get_extension_dict(ext_id)
        metadata_get = getattr(metadata, "get", None)
        package = metadata_get("package", None) if callable(metadata_get) else None
        package_get = getattr(package, "get", None)
        version = package_get("version", None) if callable(package_get) else None
        if not isinstance(version, str) or not version:
            continue
        manifest_path = path / "config/extension.toml"
        try:
            manifest_sha256 = _stable_file_sha256(manifest_path)
        except (OSError, RuntimeError):
            continue
        records.append(
            {
                "name": name,
                "id": ext_id,
                "version": version,
                "path": str(path),
                "manifest_path": str(manifest_path),
                "manifest_sha256": manifest_sha256,
            }
        )
    records.sort(key=lambda record: record["id"])
    return {
        "authority": "robot_table_geometry_extension_closure_v1",
        "schema_version": 1,
        "capture_status": "COMPLETE",
        "records": records,
        "closure_sha256": _canonical_json_sha256({"records": records}),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, default=DEFAULT_ASSET)
    parser.add_argument("--robot-usd", type=Path, default=DEFAULT_ROBOT_USD)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--experience", type=Path, default=EXPERIMENTAL_PROFILE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_probe(
        asset_path=args.asset,
        robot_usd_path=args.robot_usd,
        experience_path=args.experience,
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())

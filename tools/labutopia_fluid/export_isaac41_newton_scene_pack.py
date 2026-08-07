#!/usr/bin/env python3
"""One-time, attested Isaac 4.1 export of the Newton-only scene contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
DEFAULT_PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
DEFAULT_SCENE = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval"
    / "lab_001_level1_pour_interndata_liquid_v1.usda"
)
DEFAULT_ROBOT = REPO_ROOT / "assets/robots/Franka.usd"
DEFAULT_OBSERVATIONS = (
    REPO_ROOT
    / "outputs/collect/2026.07.15/20.15.27_Level1_pour_online_fluid_v2"
    / "online_fluid_evidence/observations.jsonl"
)
CAMERAS = {
    "front": "/World/InternDataParityCamera",
    "wrist": "/World/InternDataParityCloseupCamera",
}


def source_paths() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_contract.py",
        REPO_ROOT / "tools/labutopia_fluid/newton_only_contract.py",
        Path(__file__).resolve(),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"scene_pack_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.link(temporary, path)
    temporary.unlink()


def _matrix_list(matrix: Any) -> list[list[float]]:
    result = [[float(matrix[row][column]) for column in range(4)] for row in range(4)]
    if len(result) != 4 or any(len(row) != 4 for row in result):
        raise ValueError("usd_matrix_invalid")
    return result


def _vector(value: Any, length: int) -> list[float] | None:
    if value is None:
        return None
    result = [float(value[index]) for index in range(length)]
    return result


def _layer_closure(stage: Any) -> list[dict[str, Any]]:
    records = []
    for layer in stage.GetUsedLayers():
        real_path = str(layer.realPath or "")
        if not real_path:
            continue
        path = Path(real_path).resolve(strict=True)
        records.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    records.sort(key=lambda row: row["path"])
    if not records:
        raise ValueError("usd_layer_closure_empty")
    return records


def _camera_record(stage: Any, path: str, *, width: int, height: int, Usd: Any, UsdGeom: Any) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsA(UsdGeom.Camera):
        raise ValueError(f"camera_prim_missing:{path}")
    camera = UsdGeom.Camera(prim)
    focal = float(camera.GetFocalLengthAttr().Get())
    horizontal_aperture = float(camera.GetHorizontalApertureAttr().Get())
    vertical_aperture = float(camera.GetVerticalApertureAttr().Get())
    horizontal_offset = float(camera.GetHorizontalApertureOffsetAttr().Get() or 0.0)
    vertical_offset = float(camera.GetVerticalApertureOffsetAttr().Get() or 0.0)
    if min(focal, horizontal_aperture, vertical_aperture) <= 0.0:
        raise ValueError(f"camera_intrinsics_invalid:{path}")
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    world = cache.GetLocalToWorldTransform(prim)
    return {
        "path": path,
        "resolution": [width, height],
        "fx": focal / horizontal_aperture * width,
        "fy": focal / vertical_aperture * height,
        "cx": width * (0.5 + horizontal_offset / horizontal_aperture),
        "cy": height * (0.5 + vertical_offset / vertical_aperture),
        "focal_length": focal,
        "horizontal_aperture": horizontal_aperture,
        "vertical_aperture": vertical_aperture,
        "horizontal_aperture_offset": horizontal_offset,
        "vertical_aperture_offset": vertical_offset,
        "camera_to_world_row_matrix": _matrix_list(world),
        "usd_camera_convention": "local_-Z_optical_axis_+Y_up",
    }


def _relationship_targets(api: Any, name: str) -> list[str]:
    relationship = api.GetPrim().GetRelationship(name)
    return [str(path) for path in relationship.GetTargets()] if relationship else []


def _attachment_record(path: Path) -> dict[str, Any]:
    """Bind the first physically observed source/hand relative transform."""
    selected = None
    record_count = 0
    with path.open("r", encoding="utf-8") as stream:
        for record_index, line in enumerate(stream):
            if not line.strip():
                continue
            record_count += 1
            value = json.loads(line)
            attachment = value.get("attachment")
            if not isinstance(attachment, Mapping):
                continue
            matrix = attachment.get("observed_source_to_gripper_matrix")
            if matrix is not None:
                selected = {
                    "observation_index": record_index,
                    "matrix": [[float(item) for item in row] for row in matrix],
                    "field": "attachment.observed_source_to_gripper_matrix",
                }
                break
    if selected is None:
        raise ValueError("observed_source_to_gripper_matrix_missing")
    matrix = selected["matrix"]
    if len(matrix) != 4 or any(len(row) != 4 for row in matrix):
        raise ValueError("observed_source_to_gripper_matrix_invalid")
    import numpy as np

    numeric = np.asarray(matrix, dtype=np.float64)
    if not np.isfinite(numeric).all() or not np.allclose(
        numeric[:, 3], [0.0, 0.0, 0.0, 1.0], atol=1.0e-9, rtol=0.0
    ):
        raise ValueError("observed_source_to_gripper_matrix_invalid")
    return {
        "semantics": (
            "row_matrix_source_world_equals_source_to_gripper_times_gripper_world"
        ),
        "fixed_grasp_start_observation_index": selected["observation_index"],
        "source_to_gripper_row_matrix": matrix,
        "source_field": selected["field"],
        "observations": {
            "path": str(path),
            "sha256": _sha256_file(path),
            "record_count_scanned_through_selection": record_count,
        },
    }


def _joint_record(prim: Any, UsdPhysics: Any) -> dict[str, Any] | None:
    joint_type = None
    if prim.IsA(UsdPhysics.RevoluteJoint):
        joint_type = "revolute"
    elif prim.IsA(UsdPhysics.PrismaticJoint):
        joint_type = "prismatic"
    elif prim.IsA(UsdPhysics.FixedJoint):
        joint_type = "fixed"
    if joint_type is None:
        return None
    joint = UsdPhysics.Joint(prim)
    record: dict[str, Any] = {
        "path": str(prim.GetPath()),
        "name": prim.GetName(),
        "type": joint_type,
        "body0": _relationship_targets(joint, "physics:body0"),
        "body1": _relationship_targets(joint, "physics:body1"),
        "local_pos0": _vector(joint.GetLocalPos0Attr().Get(), 3),
        "local_pos1": _vector(joint.GetLocalPos1Attr().Get(), 3),
        "local_rot0_xyzw": None,
        "local_rot1_xyzw": None,
        "collision_enabled": bool(joint.GetCollisionEnabledAttr().Get() or False),
    }
    for key, value in (
        ("local_rot0_xyzw", joint.GetLocalRot0Attr().Get()),
        ("local_rot1_xyzw", joint.GetLocalRot1Attr().Get()),
    ):
        if value is not None:
            imaginary = value.GetImaginary()
            record[key] = [
                float(imaginary[0]),
                float(imaginary[1]),
                float(imaginary[2]),
                float(value.GetReal()),
            ]
    if joint_type in {"revolute", "prismatic"}:
        typed = UsdPhysics.RevoluteJoint(prim) if joint_type == "revolute" else UsdPhysics.PrismaticJoint(prim)
        record.update(
            {
                "axis": str(typed.GetAxisAttr().Get()),
                "lower_limit": float(typed.GetLowerLimitAttr().Get()),
                "upper_limit": float(typed.GetUpperLimitAttr().Get()),
            }
        )
        drive = prim.GetAttribute("drive:angular:physics:targetPosition")
        if not drive:
            drive = prim.GetAttribute("drive:linear:physics:targetPosition")
        record["initial_drive_target"] = float(drive.Get()) if drive and drive.Get() is not None else 0.0
    return record


def _robot_record(stage: Any, Usd: Any, UsdGeom: Any, UsdPhysics: Any) -> dict[str, Any]:
    default_prim = stage.GetDefaultPrim()
    joints = []
    rigid_bodies = []
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    for prim in stage.Traverse():
        joint = _joint_record(prim, UsdPhysics)
        if joint is not None:
            joints.append(joint)
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            rigid_bodies.append(
                {
                    "path": str(prim.GetPath()),
                    "name": prim.GetName(),
                    "world_row_matrix": _matrix_list(cache.GetLocalToWorldTransform(prim)),
                    "kinematic_enabled": bool(
                        UsdPhysics.RigidBodyAPI(prim).GetKinematicEnabledAttr().Get() or False
                    ),
                }
            )
    joints.sort(key=lambda row: row["path"])
    rigid_bodies.sort(key=lambda row: row["path"])
    if not joints or not rigid_bodies:
        raise ValueError("franka_articulation_export_empty")
    return {
        "default_prim": str(default_prim.GetPath()) if default_prim else None,
        "joints": joints,
        "rigid_bodies": rigid_bodies,
        "joint_count": len(joints),
        "rigid_body_count": len(rigid_bodies),
    }


def _export(
    args: argparse.Namespace,
    *,
    runtime_record: Mapping[str, Any],
) -> dict[str, Any]:
    import importlib.metadata

    from pxr import Usd, UsdGeom, UsdPhysics

    from tools.labutopia_fluid.fluid_benchmark_contract import (
        EXPECTED_OBSERVATION_COUNT,
        load_packet,
        sha256_file,
    )
    from tools.labutopia_fluid.newton_only_contract import (
        SCENE_PACK_SCHEMA,
        validate_scene_pack_manifest,
    )

    packet = load_packet(args.packet)
    scene = Usd.Stage.Open(str(args.scene))
    robot = Usd.Stage.Open(str(args.robot))
    if scene is None or robot is None:
        raise RuntimeError("usd_stage_open_failed")
    cameras = {
        camera_id: _camera_record(
            scene,
            camera_path,
            width=args.width,
            height=args.height,
            Usd=Usd,
            UsdGeom=UsdGeom,
        )
        for camera_id, camera_path in CAMERAS.items()
    }
    manifest: dict[str, Any] = {
        "schema": SCENE_PACK_SCHEMA,
        "claim_boundary": (
            "one_time_matched_isaac41_scene_export_for_experimental_newton_only_lane"
        ),
        "observation_count": EXPECTED_OBSERVATION_COUNT,
        "particle_count": int(packet.manifest["particle_count"]),
        "cameras": cameras,
        "packet": {
            "path": str(packet.manifest_path),
            "sha256": sha256_file(packet.manifest_path),
            "arrays_path": str(packet.arrays_path),
            "arrays_sha256": sha256_file(packet.arrays_path),
        },
        "scene": {
            "path": str(args.scene),
            "sha256": _sha256_file(args.scene),
            "layer_closure": _layer_closure(scene),
        },
        "robot_asset": {
            "path": str(args.robot),
            "sha256": _sha256_file(args.robot),
            "layer_closure": _layer_closure(robot),
            "articulation": _robot_record(robot, Usd, UsdGeom, UsdPhysics),
            "newton_import_policy": (
                "reconstruct_from_attested_usd_joint_and_rigid_body_records;"
                "no_per_frame_usd_bridge"
            ),
        },
        "fixed_grasp": _attachment_record(args.observations),
        "runtime": dict(runtime_record),
        "exporter_packages": {
            "isaacsim": importlib.metadata.version("isaacsim"),
        },
    }
    validate_scene_pack_manifest(manifest)
    manifest["content_sha256"] = _canonical_hash(manifest)
    output_path = args.output_dir / "newton_scene_pack_v1.json"
    _atomic_json(output_path, manifest)
    return manifest


def _run_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    request = attestation._read_canonical_json(args.execution_request)
    closure = source_paths()
    request = attestation.verify_execution_request(request, source_paths=closure)
    pre_app_numpy_modules = sorted(
        name for name in sys.modules if name == "numpy" or name.startswith("numpy.")
    )
    from isaacsim import SimulationApp

    parsed_argv = sys.argv
    sys.argv = [sys.argv[0]]
    application = SimulationApp({"headless": True})
    sys.argv = parsed_argv
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    try:
        receipt = attestation.attest_existing_application(
            application=application,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=request,
            source_paths=closure,
        )
        attestation.write_canonical_json(receipt_path, receipt)
        binding = attestation.execution_binding_for_request(request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        _export(
            args,
            runtime_record={
                "lane": "formal_isaac41_effective_runtime_v2_scene_export",
                "receipt_path": str(receipt_path),
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
            },
        )
        return 0
    except BaseException as error:
        _atomic_json(
            args.evidence_dir / "child_failure.json",
            {
                "status": "blocked_runtime",
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        return 2
    finally:
        application.close()


def _child_command(args: argparse.Namespace, request_path: Path) -> list[str]:
    return [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--packet",
        str(args.packet),
        "--scene",
        str(args.scene),
        "--robot",
        str(args.robot),
        "--observations",
        str(args.observations),
        "--output-dir",
        str(args.output_dir),
        "--evidence-dir",
        str(args.evidence_dir),
        "--execution-request",
        str(request_path),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]


def _run_parent(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    if args.output_dir.exists() or args.evidence_dir.exists():
        raise FileExistsError("scene_pack_output_or_evidence_exists")
    args.evidence_dir.mkdir(parents=True)
    closure = source_paths()
    source_before = attestation.capture_source_identity(closure)
    def storage_capacity(path: Path) -> dict[str, Any]:
        probe = path
        while not probe.exists():
            if probe.parent == probe:
                raise FileNotFoundError(f"capacity_probe_has_no_existing_parent:{path}")
            probe = probe.parent
        usage = shutil.disk_usage(probe)
        return {
            "requested_path": str(path),
            "probe_path": str(probe),
            "free_bytes": usage.free,
            "minimum_free_bytes": args.minimum_free_bytes,
            "passed": usage.free >= args.minimum_free_bytes,
        }

    capacities = {
        "output": storage_capacity(args.output_dir),
        "evidence": storage_capacity(args.evidence_dir),
    }
    if not all(record["passed"] for record in capacities.values()):
        attestation.write_canonical_json(
            args.evidence_dir / "run_manifest.json",
            {
                "schema": "labutopia.isaac41_newton_scene_pack_parent_manifest.v1",
                "status": "blocked_infrastructure_prelaunch",
                "child_returncode": None,
                "source_before": source_before,
                "source_after": attestation.capture_source_identity(closure),
                "runtime_receipt_sha256": None,
                "scene_pack_sha256": None,
                "capacity": capacities,
                "verification_error": {
                    "type": "InsufficientStorage",
                    "message": (
                        "sealed Isaac child not launched because an intended "
                        "output/evidence storage target failed the capacity gate"
                    ),
                },
            },
        )
        return 2
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.evidence_dir / "execution_request.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.evidence_dir / "runtime")
    command = _child_command(args, request_path)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=environment, check=False)
    output_path = args.output_dir / "newton_scene_pack_v1.json"
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    verification_error = None
    try:
        receipt = attestation._read_canonical_json(receipt_path)
        attestation.require_matched_runtime_receipt(receipt)
        if completed.returncode != 0 or not output_path.is_file():
            raise RuntimeError(f"scene_pack_child_exit:{completed.returncode}")
    except BaseException as error:
        verification_error = {"type": type(error).__name__, "message": str(error)}
    manifest = {
        "schema": "labutopia.isaac41_newton_scene_pack_parent_manifest.v1",
        "status": "passed" if verification_error is None else "blocked_runtime",
        "command": command,
        "child_returncode": completed.returncode,
        "source_before": source_before,
        "source_after": attestation.capture_source_identity(closure),
        "runtime_receipt_sha256": _sha256_file(receipt_path) if receipt_path.is_file() else None,
        "scene_pack_sha256": _sha256_file(output_path) if output_path.is_file() else None,
        "verification_error": verification_error,
    }
    attestation.write_canonical_json(args.evidence_dir / "run_manifest.json", manifest)
    return 0 if verification_error is None else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--robot", type=Path, default=DEFAULT_ROBOT)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--minimum-free-bytes", type=int, default=2 * 1024**3)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in (
        "packet",
        "scene",
        "robot",
        "observations",
        "output_dir",
        "evidence_dir",
    ):
        setattr(args, name, getattr(args, name).resolve())
    if args.child:
        if args.execution_request is None:
            raise SystemExit("--execution-request required for child")
        return _run_child(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())

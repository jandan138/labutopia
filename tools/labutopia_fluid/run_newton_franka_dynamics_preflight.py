#!/usr/bin/env python3
"""Fail-closed Newton Franka/fixed-grasp dynamics capability audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_contract import load_packet, sha256_file  # noqa: E402
from tools.labutopia_fluid.newton_franka_dynamics import (  # noqa: E402
    FrankaDynamicsController,
    verify_robot_asset_closure,
)
from tools.labutopia_fluid.newton_only_contract import validate_scene_pack_manifest  # noqa: E402


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _runtime(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime_receipt is None:
        return {
            "authoritative": False,
            "executable": sys.executable,
            "prefix": sys.prefix,
            "reason": args.runtime_claim,
        }
    path = args.runtime_receipt.resolve(strict=True)
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("schema") != "labutopia.newton_only_runtime_attestation.v1"
        or value.get("status") != "matched_experimental_runtime"
        or value.get("executable") != sys.executable
        or Path(value.get("prefix", "")).resolve(strict=True)
        != Path(sys.prefix).resolve(strict=True)
    ):
        raise RuntimeError("newton_runtime_receipt_mismatch")
    return {
        "authoritative": True,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "receipt_path": str(path),
        "receipt_sha256": sha256_file(path),
        "receipt_content_sha256": value["content_sha256"],
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.output_dir.exists():
        raise FileExistsError(f"output_dir_exists:{args.output_dir}")
    args.output_dir.mkdir(parents=True)
    packet = load_packet(args.packet)
    scene_pack = json.loads(args.scene_pack.read_text(encoding="utf-8"))
    scene_validation = validate_scene_pack_manifest(scene_pack)
    closure = verify_robot_asset_closure(scene_pack)
    fixed_grasp = scene_pack["fixed_grasp"]
    started = time.perf_counter()
    controller = FrankaDynamicsController(
        robot_usd_path=closure["robot_path"],
        initial_source_pose_xyzw=packet.array("source_poses_xyzw", (953, 7))[0],
        source_box_poses_xyzw=packet.array("source_box_poses_xyzw", (145, 7)),
        source_box_half_extents=packet.array("source_box_half_extents", (145, 3)),
        source_to_gripper_row_matrix=np.asarray(
            fixed_grasp["source_to_gripper_row_matrix"], dtype=np.float64
        ),
        device=args.device,
    )
    setup_ms = (time.perf_counter() - started) * 1000.0
    capability = controller.dynamics_capability_preflight()
    grasp_residual = controller.grasp_residual()
    status = "capability_pass" if capability["passed"] else "blocked_capability"
    result: dict[str, Any] = {
        "schema": "labutopia.newton_franka_dynamics_preflight.v1",
        "status": status,
        "claim_boundary": (
            "experimental_newton_only_robot_lane;no_dynamics_step_or_performance_"
            "claim_when_preflight_is_no_go"
        ),
        "runtime": _runtime(args),
        "packet": {"path": str(args.packet), "sha256": sha256_file(args.packet)},
        "scene_pack": {
            "path": str(args.scene_pack),
            "sha256": sha256_file(args.scene_pack),
            "validation": scene_validation,
            "isaac41_runtime_receipt_sha256": scene_pack["runtime"]["receipt_sha256"],
        },
        "robot_asset_closure": closure,
        "fixed_grasp": {
            "start_observation_index": fixed_grasp[
                "fixed_grasp_start_observation_index"
            ],
            "residual": grasp_residual,
        },
        "setup_ms_not_performance_comparable": setup_ms,
        "capability": capability,
        "dynamics_step_attempted": False,
        "performance_claim_generated": False,
    }
    result["content_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _atomic_json(args.output_dir / "result.json", result)
    return result, 0 if capability["passed"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--scene-pack", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--runtime-receipt", type=Path)
    parser.add_argument("--runtime-claim", default="unattested_nonformal_capability_probe")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("packet", "scene_pack", "output_dir", "runtime_receipt"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    result, exit_code = run(args)
    print(
        json.dumps(
            {"status": result["status"], "result": str(args.output_dir / "result.json")},
            sort_keys=True,
        ),
        flush=True,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

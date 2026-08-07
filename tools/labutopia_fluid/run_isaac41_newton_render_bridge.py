#!/usr/bin/env python3
"""Run the Newton particle render bridge in the sealed Isaac Sim 4.1 child."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)


def source_paths() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        Path(__file__).resolve(),
        REPO_ROOT / "tools/labutopia_fluid/run_isaac601_newton_render_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_contract.py",
        REPO_ROOT / "tools/labutopia_fluid/interndata_surface_reconstruction.py",
        REPO_ROOT / "tools/labutopia_fluid/run_interndata_online_surface_probe.py",
        REPO_ROOT / "utils/online_fluid_surface.py",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _child_command(args: argparse.Namespace, request_path: Path) -> list[str]:
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--packet",
        str(args.packet),
        "--scene",
        str(args.scene),
        "--output-dir",
        str(args.output_dir),
        "--evidence-dir",
        str(args.evidence_dir),
        "--execution-request",
        str(request_path),
        "--bridge-socket",
        str(args.bridge_socket),
        "--shared-memory-name",
        args.shared_memory_name,
        "--bridge-payload",
        args.bridge_payload,
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--renderer",
        args.renderer,
        "--rt-subframes",
        str(args.rt_subframes),
        "--camera-count",
        str(args.camera_count),
        "--surface-mode",
        args.surface_mode,
        "--stage-warmup-updates",
        str(args.stage_warmup_updates),
        "--bridge-timeout-s",
        str(args.bridge_timeout_s),
        "--pour-retarget-offset-m",
        *(str(value) for value in args.pour_retarget_offset_m),
        "--pour-retarget-blend",
        *(str(value) for value in args.pour_retarget_blend),
    ]
    if args.trajectory_npz is not None:
        command.extend(["--trajectory-npz", str(args.trajectory_npz)])
    command.append("--pour-retarget" if args.pour_retarget else "--no-pour-retarget")
    return command


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
    application = SimulationApp(
        {
            "headless": True,
            "hide_ui": True,
            "width": int(args.width),
            "height": int(args.height),
            "renderer": args.renderer,
            "extra_args": ["--/rtx/raytracing/fractionalCutoutOpacity=true"],
        }
    )
    sys.argv = parsed_argv
    try:
        receipt = attestation.attest_existing_application(
            application=application,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=request,
            source_paths=closure,
        )
        receipt_path = args.evidence_dir / "runtime_receipt.json"
        attestation.write_canonical_json(receipt_path, receipt)
        binding = attestation.execution_binding_for_request(
            request, child_pid=os.getpid()
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        from tools.labutopia_fluid import run_isaac601_newton_render_bridge as bridge

        args.runtime_label = "isaac41"
        bridge.run(
            args,
            application=application,
            runtime_record={
                "lane": "formal_isaac41_renderer_for_experimental_newton140",
                "receipt_path": str(receipt_path),
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
            },
        )
        return 0
    finally:
        application.close()


def _run_parent(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    if args.evidence_dir.exists():
        raise FileExistsError(f"evidence_dir_exists:{args.evidence_dir}")
    args.evidence_dir.mkdir(parents=True)
    closure = source_paths()
    source_before = attestation.capture_source_identity(closure)
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
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        check=False,
    )
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    verification_error = None
    receipt_sha256 = None
    try:
        receipt = attestation._read_canonical_json(receipt_path)
        attestation.require_matched_runtime_receipt(receipt)
        receipt_sha256 = attestation.canonical_json_sha256(receipt)
        if completed.returncode != 0:
            raise RuntimeError(f"isaac41_render_child_exit:{completed.returncode}")
    except BaseException as error:
        verification_error = {"type": type(error).__name__, "message": str(error)}
    manifest = {
        "schema": "labutopia.isaac41_newton_render_parent_manifest.v1",
        "status": "passed" if verification_error is None else "blocked_runtime",
        "command": command,
        "child_returncode": completed.returncode,
        "source_before": source_before,
        "source_after": attestation.capture_source_identity(closure),
        "execution_request_sha256": attestation.canonical_json_sha256(request),
        "runtime_receipt_sha256": receipt_sha256,
        "result": (
            {
                "path": str(args.output_dir / "result.json"),
                "sha256": _sha256_file(args.output_dir / "result.json"),
            }
            if (args.output_dir / "result.json").is_file()
            else None
        ),
        "verification_error": verification_error,
    }
    attestation.write_canonical_json(args.evidence_dir / "run_manifest.json", manifest)
    return 0 if verification_error is None else 2


def build_parser() -> argparse.ArgumentParser:
    from tools.labutopia_fluid import run_isaac601_newton_render_bridge as bridge

    parser = bridge.build_parser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir = args.output_dir.resolve()
    args.evidence_dir = args.evidence_dir.resolve()
    args.packet = args.packet.resolve()
    args.scene = args.scene.resolve()
    args.bridge_socket = args.bridge_socket.resolve()
    if args.trajectory_npz is not None:
        args.trajectory_npz = args.trajectory_npz.resolve()
    if args.bridge_payload == "render-v2" and args.surface_mode not in {
        "particles",
        "surface-shm",
    }:
        raise ValueError("render_v2_surface_mode_invalid")
    if args.child:
        if args.execution_request is None:
            raise ValueError("child_execution_request_required")
        args.execution_request = args.execution_request.resolve()
        return _run_child(args)
    if args.execution_request is not None:
        raise ValueError("execution_request_is_child_only")
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())

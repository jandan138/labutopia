#!/usr/bin/env python3
"""Fail-closed parent for the experimental Isaac 6 PhysX PBD baseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
ISAAC_PREFIX = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim601-fluid-py312"
)
LOCK_MANIFEST = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/environment_locks/isaacsim601/environment-lock.json"
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


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    from tools.labutopia_fluid.run_wcsph_scaling_matrix import _atomic_json as write

    write(path, value)


def run(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid.fluid_benchmark_contract import sha256_file
    from tools.labutopia_fluid.run_newton_only_solver_search import wait_for_idle_gpu
    from tools.labutopia_fluid.run_wcsph_scaling_matrix import (
        _gpu_process_classification,
        _sealed_environment,
        _terminate_process,
    )

    if args.output_root.exists():
        raise FileExistsError(f"output_root_exists:{args.output_root}")
    args.output_root.mkdir(parents=True)
    lock = LOCK_MANIFEST
    checks = {
        "python_exists": (ISAAC_PREFIX / "bin/python").is_file(),
        "lock_exists": lock.is_file(),
        "packet_exists": args.packet.is_file(),
        "scene_exists": args.scene.is_file(),
    }
    _atomic_json(args.output_root / "preflight.json", {"passed": all(checks.values()), "checks": checks})
    if not all(checks.values()):
        _atomic_json(
            args.output_root / "run_manifest.json",
            {
                "schema": "labutopia.isaac601_pbd_parent_manifest.v1",
                "status": "blocked_infrastructure",
                "claim_boundary": "experimental_isaac601_physx_pbd;not_formal_isaac41_evidence",
                "checks": checks,
            },
        )
        return 2
    gpu_gate = wait_for_idle_gpu(
        timeout_s=args.wait_gpu_hours * 3600.0,
        poll_interval_s=args.gpu_poll_seconds,
        consecutive_samples=args.gpu_idle_samples,
    )
    _atomic_json(args.output_root / "gpu_idle_gate.json", gpu_gate)
    if gpu_gate["status"] != "idle":
        _atomic_json(
            args.output_root / "run_manifest.json",
            {
                "schema": "labutopia.isaac601_pbd_parent_manifest.v1",
                "status": "blocked_gpu_busy",
                "claim_boundary": "experimental_isaac601_physx_pbd;not_formal_isaac41_evidence",
                "gpu_idle_gate_path": str(args.output_root / "gpu_idle_gate.json"),
            },
        )
        return 2
    artifact_dir = args.output_root / "artifacts"
    receipt = args.output_root / "runtime_receipt.json"
    failure = args.output_root / "child_failure.json"
    command = [
        str(ISAAC_PREFIX / "bin/python"),
        "-I",
        "-B",
        str(REPO_ROOT / "tools/labutopia_fluid/run_isaac601_pbd_attested_child.py"),
        "--lock-manifest",
        str(lock),
        "--runtime-receipt",
        str(receipt),
        "--child-failure",
        str(failure),
        "--packet",
        str(args.packet),
        "--scene",
        str(args.scene),
        "--output-dir",
        str(artifact_dir),
        "--max-observations",
        str(args.max_observations),
    ]
    environment = _sealed_environment(ISAAC_PREFIX, args.output_root / "runtime", isaac=True)
    stdout_path = args.output_root / "child.stdout.log"
    stderr_path = args.output_root / "child.stderr.log"
    started = time.time()
    contention: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    sample_count = 0
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=stdout,
            stderr=stderr,
        )
        deadline = time.monotonic() + args.child_timeout_s
        returncode: int | None = None
        while returncode is None:
            returncode = process.poll()
            if returncode is not None:
                break
            foreign, advisory = _gpu_process_classification(process.pid)
            sample_count += 1
            sample = {
                "observed_unix_s": time.time(),
                "foreign_compute_processes": foreign,
                "advisory_compute_processes": advisory,
            }
            if advisory:
                advisories.append(sample)
            if foreign:
                contention.append(sample)
                returncode = _terminate_process(process)
                break
            if time.monotonic() >= deadline:
                returncode = _terminate_process(process)
                break
            time.sleep(args.gpu_monitor_interval_s)
    result_path = artifact_dir / "result.json"
    if contention:
        status = "failed_gpu_contention"
    elif returncode == 0 and result_path.is_file():
        status = "completed"
    else:
        status = "failed_runtime"
    manifest = {
        "schema": "labutopia.isaac601_pbd_parent_manifest.v1",
        "status": status,
        "claim_boundary": "experimental_isaac601_physx_pbd;not_formal_isaac41_evidence",
        "command": command,
        "returncode": returncode,
        "started_unix_s": started,
        "finished_unix_s": time.time(),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "runtime_receipt_sha256": sha256_file(receipt) if receipt.is_file() else None,
        "result_path": str(result_path) if result_path.is_file() else None,
        "result_sha256": sha256_file(result_path) if result_path.is_file() else None,
        "gpu_isolation": {
            "monitor_interval_s": args.gpu_monitor_interval_s,
            "sample_count": sample_count,
            "passed": not contention,
            "contention": contention,
            "advisories": advisories,
        },
    }
    _atomic_json(args.output_root / "run_manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "output_root": str(args.output_root)}, sort_keys=True))
    return 0 if manifest["status"] == "completed" else 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--wait-gpu-hours", type=float, default=24.0)
    parser.add_argument("--gpu-poll-seconds", type=float, default=60.0)
    parser.add_argument("--gpu-idle-samples", type=int, default=3)
    parser.add_argument("--child-timeout-s", type=float, default=3600.0)
    parser.add_argument("--gpu-monitor-interval-s", type=float, default=1.0)
    args = parser.parse_args(argv)
    for name in ("output_root", "packet", "scene"):
        setattr(args, name, getattr(args, name).resolve())
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create fresh, versioned Isaac/Newton fluid environments fail-closed."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
CONDA = Path("/cpfs/user/zhuzihou/conda-managed/miniforge3/bin/conda")
PREFIX_ROOT = Path("/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs")
LANES = {
    "isaac": {
        "prefix": PREFIX_ROOT / "labutopia-sim-isaacsim601-newton-wcsph-py312-r2",
        "clone_prefix": PREFIX_ROOT / "embodied-eval-os-sim-isaacsim601-fluid-py312",
        "attester": "experimental",
    },
    "main": {
        "prefix": PREFIX_ROOT / "labutopia-sim-newton140-fluidbench-py312-r2",
        "yaml": REPO_ROOT
        / "environments/fluid_benchmark/newton140-fluidbench-py312-r2.yaml",
        "attester": "newton_only",
    },
    "rtx": {
        "prefix": PREFIX_ROOT / "labutopia-sim-newton140-fluidbench-ovrtx-py312-r2",
        "yaml": REPO_ROOT
        / "environments/fluid_benchmark/newton140-fluidbench-ovrtx-py312-r2.yaml",
        "attester": "newton_only",
    },
}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sealed_environment(
    prefix: Path,
    run_root: Path,
    *,
    isaac: bool,
) -> dict[str, str]:
    directories = {
        "HOME": run_root / "home",
        "TMPDIR": run_root / "tmp",
        "XDG_CACHE_HOME": run_root / "cache",
        "XDG_CONFIG_HOME": run_root / "config",
        "XDG_DATA_HOME": run_root / "data",
        "XDG_STATE_HOME": run_root / "state",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=False)
    environment = {
        **{name: str(path) for name, path in directories.items()},
        "PATH": f"{prefix / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
    }
    if isaac:
        environment.update(
            {
                "ACCEPT_EULA": "Y",
                "OMNI_KIT_ACCEPT_EULA": "YES",
                "LD_LIBRARY_PATH": str(prefix / "lib"),
            }
        )
    return environment


def create_lane(
    lane: str,
    *,
    evidence_dir: Path,
    minimum_free_bytes: int,
) -> dict[str, Any]:
    selected = LANES[lane]
    prefix = selected["prefix"]
    yaml_path = selected.get("yaml")
    yaml_path = yaml_path.resolve(strict=True) if yaml_path is not None else None
    clone_prefix = selected.get("clone_prefix")
    if prefix.exists():
        raise FileExistsError(f"target_prefix_exists:{prefix}")
    if evidence_dir.exists():
        raise FileExistsError(f"evidence_dir_exists:{evidence_dir}")
    evidence_dir.mkdir(parents=True)
    usage = shutil.disk_usage(PREFIX_ROOT)
    preflight = {
        "lane": lane,
        "target_prefix": str(prefix),
        "yaml": str(yaml_path) if yaml_path is not None else None,
        "clone_prefix": str(clone_prefix) if clone_prefix is not None else None,
        "clone_prefix_exists": clone_prefix.is_dir() if clone_prefix is not None else None,
        "prefix_root_free_bytes": usage.free,
        "minimum_free_bytes": minimum_free_bytes,
        "capacity_passed": usage.free >= minimum_free_bytes,
        "target_absent": not prefix.exists(),
        "conda_exists": CONDA.is_file(),
    }
    _atomic_json(evidence_dir / "preflight.json", preflight)
    if not all(
        (
            preflight["capacity_passed"],
            preflight["target_absent"],
            preflight["conda_exists"],
        )
    ):
        result = {
            "schema": "labutopia.newton_environment_creation.v1",
            "status": "blocked_infrastructure",
            "preflight": preflight,
            "target_mutated": False,
        }
        _atomic_json(evidence_dir / "creation_manifest.json", result)
        return result

    package_cache = Path("/tmp/labutopia-newton-env-create-pkgs") / lane
    package_cache.mkdir(parents=True, exist_ok=True)
    if clone_prefix is not None:
        if not clone_prefix.is_dir():
            raise FileNotFoundError(f"clone_prefix_missing:{clone_prefix}")
        create_command = [
            str(CONDA),
            "create",
            "--prefix",
            str(prefix),
            "--clone",
            str(clone_prefix),
            "--yes",
        ]
    else:
        create_command = [
            str(CONDA),
            "env",
            "create",
            "--prefix",
            str(prefix),
            "--file",
            str(yaml_path),
            "--yes",
        ]
    create_environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "CONDA_PKGS_DIRS": str(package_cache),
        "PYTHONNOUSERSITE": "1",
    }
    started = time.time()
    stdout_path = evidence_dir / "conda-create.stdout.log"
    stderr_path = evidence_dir / "conda-create.stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            create_command,
            cwd=REPO_ROOT,
            env=create_environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    if completed.returncode != 0:
        result = {
            "schema": "labutopia.newton_environment_creation.v1",
            "status": "failed_creation",
            "returncode": completed.returncode,
            "target_exists_after_failure": prefix.exists(),
            "recovery": "inspect_partial_prefix;do_not_reuse_or_delete_automatically",
        }
        _atomic_json(evidence_dir / "creation_manifest.json", result)
        return result

    python = prefix / "bin/python"
    lock_dir = evidence_dir / "environment_lock"
    receipt_path = evidence_dir / "runtime_receipt.json"
    sealed_root = evidence_dir / "sealed_runtime"
    isaac_lane = selected["attester"] == "experimental"
    environment = _sealed_environment(prefix, sealed_root, isaac=isaac_lane)
    snapshot_command = [
        str(python),
        "-I",
        "-B",
        str(REPO_ROOT / "tools/labutopia_fluid/snapshot_experimental_fluid_environment.py"),
        "--output-dir",
        str(lock_dir),
    ]
    snapshot = subprocess.run(
        snapshot_command,
        cwd=REPO_ROOT,
        env=environment,
        check=False,
    )
    lock_manifest = lock_dir / "environment-lock.json"
    if isaac_lane:
        attest_command = [
            str(python),
            "-I",
            "-B",
            str(REPO_ROOT / "tools/labutopia_fluid/attest_experimental_fluid_runtime.py"),
            "--lane",
            "isaacsim601_wcsph_r1",
            "--output",
            str(receipt_path),
        ]
    else:
        attest_command = [
            str(python),
            "-I",
            "-B",
            str(REPO_ROOT / "tools/labutopia_fluid/attest_newton_only_runtime.py"),
            "--lane",
            lane,
            "--lock-manifest",
            str(lock_manifest),
            "--output",
            str(receipt_path),
        ]
    attestation = (
        subprocess.run(
            attest_command,
            cwd=REPO_ROOT,
            env=environment,
            check=False,
        )
        if snapshot.returncode == 0
        else None
    )
    passed = snapshot.returncode == 0 and attestation is not None and attestation.returncode == 0
    result = {
        "schema": "labutopia.newton_environment_creation.v1",
        "status": "created_and_attested" if passed else "created_but_attestation_failed",
        "lane": lane,
        "target_prefix": str(prefix),
        "create_command": create_command,
        "clone_source_prefix": str(clone_prefix) if clone_prefix is not None else None,
        "create_started_unix_s": started,
        "finished_unix_s": time.time(),
        "snapshot_returncode": snapshot.returncode,
        "attestation_returncode": attestation.returncode if attestation is not None else None,
        "lock_manifest": str(lock_manifest) if lock_manifest.is_file() else None,
        "runtime_receipt": str(receipt_path) if receipt_path.is_file() else None,
    }
    _atomic_json(evidence_dir / "creation_manifest.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=sorted(LANES), required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--minimum-free-bytes", type=int, default=8 * 1024**3)
    args = parser.parse_args(argv)
    try:
        result = create_lane(
            args.lane,
            evidence_dir=args.evidence_dir.resolve(),
            minimum_free_bytes=args.minimum_free_bytes,
        )
    except BaseException as error:
        failure = {
            "schema": "labutopia.newton_environment_creation.v1",
            "status": "failed_or_refused",
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        if not args.evidence_dir.exists():
            args.evidence_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(args.evidence_dir / "creation_manifest.json", failure)
        print(json.dumps({key: value for key, value in failure.items() if key != "traceback"}, sort_keys=True))
        return 2
    print(json.dumps({"status": result["status"], "evidence_dir": str(args.evidence_dir)}, sort_keys=True))
    return 0 if result["status"] == "created_and_attested" else 2


if __name__ == "__main__":
    raise SystemExit(main())

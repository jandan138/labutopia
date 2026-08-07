#!/usr/bin/env python3
"""Fail-closed attestation for the locked Newton-only fluid runtimes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


PREFIX_ROOT = Path("/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs")
EXPECTED = {
    "main": {
        "prefix": PREFIX_ROOT / "labutopia-sim-newton140-fluidbench-py312-r2",
        "packages": {
            "newton": "1.4.0",
            "newton-usd-schemas": "0.4.0",
            "warp-lang": "1.15.0",
            "numpy": "2.5.1",
            "usd-core": "26.3",
            "pyglet": "2.1.15",
            "PyOpenGL": "3.1.10",
            "glfw": "2.10.2",
            "mujoco": "3.10.0",
            "mujoco-warp": "3.10.0.3",
            "scipy": "1.17.0",
            "scikit-image": "0.26.0",
            "psutil": "7.2.2",
        },
    },
    "rtx": {
        "prefix": PREFIX_ROOT / "labutopia-sim-newton140-fluidbench-ovrtx-py312-r2",
        "packages": {
            "newton": "1.4.0",
            "newton-usd-schemas": "0.4.0",
            "warp-lang": "1.15.0",
            "numpy": "2.5.1",
            "usd-core": "26.3",
            "pyglet": "2.1.15",
            "PyOpenGL": "3.1.10",
            "glfw": "2.10.2",
            "mujoco": "3.10.0",
            "mujoco-warp": "3.10.0.3",
            "scipy": "1.17.0",
            "scikit-image": "0.26.0",
            "psutil": "7.2.2",
        },
    },
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _module_record(module: Any) -> dict[str, Any]:
    path = Path(module.__file__).resolve(strict=True)
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _command(arguments: list[str]) -> str:
    return subprocess.run(
        arguments,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _driver_record() -> dict[str, Any]:
    text = _command(
        [
            "nvidia-smi",
            "--query-gpu=driver_version,name,uuid,memory.total",
            "--format=csv,noheader,nounits",
        ]
    ).strip()
    if not text:
        raise RuntimeError("gpu_record_missing")
    fields = [field.strip() for field in text.splitlines()[0].split(",")]
    version = fields[0]
    components = tuple(int(part) for part in version.split("."))
    padded = (*components, 0, 0)[:3]
    isaac601_known_blocked = (570, 0, 0) <= padded < (570, 158, 1)
    return {
        "driver_version": version,
        "gpu_name": fields[1],
        "gpu_uuid": fields[2],
        "memory_total_mib": int(fields[3]),
        "viewer_rtx_capability_expected": not isaac601_known_blocked,
        "driver_caveat": (
            "host_driver_is_in_observed_isaac601_rtx_blocked_range_[570.00,570.158.01)"
            if isaac601_known_blocked
            else None
        ),
    }


def _validate_lock(lock_manifest: Path, *, prefix: Path) -> dict[str, Any]:
    value = json.loads(lock_manifest.resolve(strict=True).read_text(encoding="utf-8"))
    if value.get("schema") != "labutopia.experimental_fluid_environment_lock.v1":
        raise RuntimeError("environment_lock_schema_mismatch")
    if Path(value.get("prefix", "")).resolve(strict=True) != prefix:
        raise RuntimeError("environment_lock_prefix_mismatch")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise RuntimeError("environment_lock_artifacts_missing")
    verified: dict[str, Any] = {}
    for name in ("conda_explicit", "pip_freeze_all", "pip_inspect"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise RuntimeError(f"environment_lock_artifact_missing:{name}")
        path = Path(str(record.get("path", ""))).resolve(strict=True)
        actual = _sha256_file(path)
        if actual != record.get("sha256"):
            raise RuntimeError(f"environment_lock_artifact_hash_mismatch:{name}")
        verified[name] = {"path": str(path), "sha256": actual}
    return {
        "manifest_path": str(lock_manifest.resolve()),
        "manifest_sha256": _sha256_file(lock_manifest.resolve()),
        "artifacts": verified,
    }


def attest(lane: str, lock_manifest: Path) -> dict[str, Any]:
    expected = EXPECTED[lane]
    prefix = Path(sys.prefix).resolve(strict=True)
    executable = Path(sys.executable).absolute()
    if prefix != expected["prefix"]:
        raise RuntimeError(f"prefix_mismatch:expected={expected['prefix']}:actual={prefix}")
    if executable != prefix / "bin/python":
        raise RuntimeError(f"absolute_environment_python_required:{executable}")
    if platform.python_version() != "3.12.13":
        raise RuntimeError(f"python_version_mismatch:{platform.python_version()}")
    forbidden = (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "CARB_APP_PATH",
        "EXP_PATH",
        "ISAAC_PATH",
        "OMNI_SERVER",
        "LD_PRELOAD",
    )
    leaked = sorted(name for name in forbidden if os.environ.get(name))
    if leaked:
        raise RuntimeError(f"forbidden_environment_present:{leaked}")
    if os.environ.get("PYTHONNOUSERSITE") != "1":
        raise RuntimeError("python_no_user_site_not_enabled")
    if os.environ.get("LD_LIBRARY_PATH"):
        raise RuntimeError("ambient_ld_library_path_forbidden")
    selected_environment = {
        name: os.environ[name]
        for name in (
            "CUDA_VISIBLE_DEVICES",
            "HOME",
            "PATH",
            "PYTHONNOUSERSITE",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        )
        if name in os.environ
    }
    package_versions = {
        name: importlib.metadata.version(name) for name in expected["packages"]
    }
    mismatches = {
        name: {"expected": version, "actual": package_versions[name]}
        for name, version in expected["packages"].items()
        if package_versions[name] != version
    }
    if mismatches:
        raise RuntimeError(f"package_version_mismatch:{mismatches}")

    import newton
    import newton_usd_schemas
    import numpy
    import scipy
    import skimage
    import warp

    warp.init()
    device = warp.get_device("cuda:0")
    if not device.is_cuda:
        raise RuntimeError("cuda_device_required")
    modules = {
        "newton": _module_record(newton),
        "newton_usd_schemas": _module_record(newton_usd_schemas),
        "warp": _module_record(warp),
        "numpy": _module_record(numpy),
        "scipy": _module_record(scipy),
        "skimage": _module_record(skimage),
    }
    warp_native = Path(warp.__file__).resolve().parent / "bin/warp.so"
    if not warp_native.is_file():
        raise RuntimeError("warp_native_library_missing")
    modules["warp_native"] = {
        "path": str(warp_native.resolve()),
        "size_bytes": warp_native.stat().st_size,
        "sha256": _sha256_file(warp_native),
    }
    if any(not Path(record["path"]).is_relative_to(prefix) for record in modules.values()):
        raise RuntimeError("module_origin_outside_prefix")
    ovrtx_record = None
    if lane == "rtx":
        version = importlib.metadata.version("ovrtx")
        major_minor = tuple(int(part) for part in version.split(".")[:2])
        if major_minor < (0, 3):
            raise RuntimeError(f"ovrtx_version_too_old:{version}")
        import ovrtx

        ovrtx_record = {"version": version, **_module_record(ovrtx)}

    lock = _validate_lock(lock_manifest, prefix=prefix)
    freeze = _command([str(executable), "-m", "pip", "freeze", "--all"])
    driver = _driver_record()
    receipt: dict[str, Any] = {
        "schema": "labutopia.newton_only_runtime_attestation.v1",
        "status": "matched_experimental_runtime",
        "claim_boundary": "experimental_newton_only_lane_not_formal_isaac41_evidence",
        "lane": lane,
        "created_unix_s": time.time(),
        "executable": str(executable),
        "executable_sha256": _sha256_file(executable.resolve(strict=True)),
        "prefix": str(prefix),
        "python": platform.python_version(),
        "packages": package_versions,
        "ovrtx": ovrtx_record,
        "modules": modules,
        "warp_device": {
            "alias": str(device),
            "name": device.name,
            "architecture": device.arch,
            "is_cuda": device.is_cuda,
        },
        "driver": driver,
        "environment": selected_environment,
        "environment_sha256": _canonical_sha256(selected_environment),
        "pip_freeze_sha256": hashlib.sha256(freeze.encode("utf-8")).hexdigest(),
        "lock": lock,
    }
    receipt["content_sha256"] = _canonical_sha256(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=sorted(EXPECTED), required=True)
    parser.add_argument("--lock-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"attestation_output_exists:{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = attest(args.lane, args.lock_manifest)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    print(json.dumps({"status": receipt["status"], "receipt": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

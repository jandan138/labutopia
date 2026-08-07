#!/usr/bin/env python3
"""Fail-closed attestation for the experimental Isaac 6/Newton fluid lanes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


EXPECTED = {
    "newton140": {
        "prefix": Path(
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-newton140-mpm-py312"
        ),
        "packages": {
            "newton": "1.4.0",
            "warp-lang": "1.15.0",
        },
    },
    "isaacsim601": {
        "prefix": Path(
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim601-fluid-py312"
        ),
        "packages": {
            "isaacsim": "6.0.1.0",
            "torch": "2.11.0+cu128",
        },
    },
    "isaacsim601_wcsph_r1": {
        "prefix": Path(
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim601-fluid-py312"
        ),
        "packages": {
            "isaacsim": "6.0.1.0",
            "newton": "1.2.1",
            "warp-lang": "1.13.0",
            "numpy": "2.3.1",
            "torch": "2.11.0+cu128",
        },
    },
}


RTX_DRIVER_VERIFY_DISABLE_ARG = "--/rtx/verifyDriverVersion/enabled=false"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(f"distribution_missing:{name}") from error


def _module_record(name: str) -> dict[str, Any]:
    module = sys.modules.get(name)
    origin = getattr(module, "__file__", None) if module is not None else None
    if origin is None:
        spec = importlib.util.find_spec(name)
        origin = None if spec is None else spec.origin
    record: dict[str, Any] = {"name": name, "origin": origin}
    if origin and origin not in {"built-in", "frozen"}:
        path = Path(origin).resolve(strict=True)
        record.update(
            {
                "origin": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return record


def _command_output(arguments: list[str]) -> str:
    completed = subprocess.run(
        arguments,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _isaac_driver_preflight(
    *, allow_unvalidated_driver: bool = False
) -> dict[str, Any]:
    value = _command_output(
        [
            "nvidia-smi",
            "--query-gpu=driver_version,name,uuid",
            "--format=csv,noheader",
        ]
    ).strip()
    if not value:
        raise RuntimeError("nvidia_smi_gpu_record_missing")
    first = [part.strip() for part in value.splitlines()[0].split(",")]
    version = first[0]
    try:
        components = tuple(int(part) for part in version.split("."))
    except ValueError as error:
        raise RuntimeError(f"nvidia_driver_version_invalid:{version}") from error
    components = (*components, 0, 0)[:3]
    blocked = (570, 0, 0) <= components < (570, 158, 1)
    return {
        "driver_version": version,
        "gpu_name": first[1] if len(first) > 1 else None,
        "gpu_uuid": first[2] if len(first) > 2 else None,
        "isaac601_rtx_supported": not blocked,
        "observed_unsupported_range": "[570.00,570.158.01)",
        "observed_recommended_driver": "580.95.05",
        "unvalidated_driver_override_requested": bool(allow_unvalidated_driver),
        "rtx_launch_permitted": bool(not blocked or allow_unvalidated_driver),
        "driver_verification_setting": (
            RTX_DRIVER_VERIFY_DISABLE_ARG if allow_unvalidated_driver else None
        ),
    }


def _base_receipt(lane: str) -> dict[str, Any]:
    expected = EXPECTED[lane]
    executable = Path(sys.executable).absolute()
    executable_real = executable.resolve(strict=True)
    prefix = Path(sys.prefix).resolve(strict=True)
    if prefix != expected["prefix"]:
        raise RuntimeError(
            f"prefix_mismatch:expected={expected['prefix']}:actual={prefix}"
        )
    if executable != prefix / "bin/python":
        raise RuntimeError(f"executable_mismatch:{executable}")
    if sys.version_info[:2] != (3, 12):
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
    leaked = {name: os.environ[name] for name in forbidden if os.environ.get(name)}
    if leaked:
        raise RuntimeError(f"forbidden_environment_present:{sorted(leaked)}")
    if os.environ.get("PYTHONNOUSERSITE") != "1":
        raise RuntimeError("python_no_user_site_not_enabled")
    approved_libraries = []
    if lane.startswith("isaacsim601"):
        expected_library_path = str(prefix / "lib")
        if os.environ.get("LD_LIBRARY_PATH") != expected_library_path:
            raise RuntimeError(
                "isaac_ld_library_path_mismatch:"
                f"expected={expected_library_path}:"
                f"actual={os.environ.get('LD_LIBRARY_PATH')}"
            )
        for name in ("libstdc++.so.6", "libgcc_s.so.1"):
            library_path = (prefix / "lib" / name).resolve(strict=True)
            approved_libraries.append(
                {
                    "purpose": "isaac601_conda_cxx_runtime_abi",
                    "requested_path": str(prefix / "lib" / name),
                    "real_path": str(library_path),
                    "size_bytes": library_path.stat().st_size,
                    "sha256": _sha256_file(library_path),
                }
            )
    package_versions = {
        name: _distribution_version(name)
        for name in expected["packages"]
    }
    for name, version in expected["packages"].items():
        actual = package_versions[name]
        if actual != version:
            raise RuntimeError(
                f"package_version_mismatch:{name}:expected={version}:actual={actual}"
            )
    freeze = _command_output([str(executable), "-m", "pip", "freeze", "--all"])
    conda_history = prefix / "conda-meta/history"
    if not conda_history.is_file():
        raise RuntimeError("conda_history_missing")
    selected_environment = {
        name: os.environ[name]
        for name in (
            "ACCEPT_EULA",
            "CUDA_VISIBLE_DEVICES",
            "HOME",
            "LD_LIBRARY_PATH",
            "OMNI_KIT_ACCEPT_EULA",
            "PATH",
            "PYTHONNOUSERSITE",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
        )
        if name in os.environ
    }
    return {
        "schema": "labutopia.experimental_fluid_runtime_attestation.v1",
        "lane": lane,
        "claim_boundary": (
            "experimental_lane_only_not_formal_isaac41_effective_runtime_v2"
        ),
        "created_unix_s": time.time(),
        "executable": str(executable),
        "executable_realpath": str(executable_real),
        "executable_sha256": _sha256_file(executable_real),
        "prefix": str(prefix),
        "python": platform.python_version(),
        "packages": package_versions,
        "pip_freeze_sha256": hashlib.sha256(freeze.encode("utf-8")).hexdigest(),
        "conda_history_sha256": _sha256_file(conda_history),
        "approved_native_libraries": approved_libraries,
        "selected_environment": selected_environment,
        "selected_environment_sha256": _canonical_sha256(selected_environment),
        "platform": platform.platform(),
    }


def _attest_newton(receipt: dict[str, Any]) -> None:
    import newton
    import numpy
    import warp
    from pxr import Usd

    warp.init()
    device = warp.get_device("cuda:0")
    if not device.is_cuda:
        raise RuntimeError("newton_cuda_device_missing")
    receipt["runtime"] = {
        "newton": str(newton.__version__),
        "warp": str(warp.__version__),
        "numpy": str(numpy.__version__),
        "usd": str(Usd.GetVersion()),
        "device": str(device),
        "device_is_cuda": bool(device.is_cuda),
        "modules": [
            _module_record(name)
            for name in ("newton", "warp", "numpy", "pxr.Usd")
        ],
    }


def _attest_isaac(
    receipt: dict[str, Any],
    *,
    allow_unvalidated_driver: bool = False,
    width: int = 64,
    height: int = 64,
    renderer: str = "RayTracedLighting",
    minimal_shading_mode: int = 0,
) -> Any:
    if os.environ.get("ACCEPT_EULA") != "Y":
        raise RuntimeError("accept_eula_missing")
    if os.environ.get("OMNI_KIT_ACCEPT_EULA") != "YES":
        raise RuntimeError("omni_kit_accept_eula_missing")
    from isaacsim import SimulationApp

    renderer_lower = str(renderer).lower()
    render_mode = {
        "raytracedlighting": "RaytracedLighting",
        "pathtracing": "PathTracing",
        "realtimepathtracing": "RealTimePathTracing",
        "minimal": "MinimalRendering",
        "minimalrendering": "MinimalRendering",
    }.get(renderer_lower, str(renderer))
    extra_args = [f"--/rtx/rendermode={render_mode}"]
    if render_mode == "MinimalRendering":
        extra_args.append(
            f"--/rtx/minimal/mode={int(minimal_shading_mode)}"
        )
    if allow_unvalidated_driver:
        extra_args.append(RTX_DRIVER_VERIFY_DISABLE_ARG)
    launch_config = {
        "headless": True,
        "hide_ui": True,
        "width": int(width),
        "height": int(height),
        "renderer": renderer,
        "minimal_shading_mode": int(minimal_shading_mode),
        "extra_args": extra_args,
    }
    receipt["isaac_launch"] = {
        "headless": True,
        "resolution": [int(width), int(height)],
        "renderer_requested": renderer,
        "minimal_shading_mode_requested": int(minimal_shading_mode),
        "unvalidated_driver_override_requested": bool(
            allow_unvalidated_driver
        ),
        "extra_args": list(launch_config["extra_args"]),
    }
    application = SimulationApp(launch_config)
    try:
        import carb
        import newton
        import numpy
        import omni.kit.app
        import torch
        import warp
        from pxr import Usd

        if not torch.cuda.is_available():
            raise RuntimeError("isaac_torch_cuda_unavailable")
        receipt["runtime"] = {
            "isaacsim": _distribution_version("isaacsim"),
            "kit": str(omni.kit.app.get_app().get_build_version()),
            "numpy": str(numpy.__version__),
            "newton": str(newton.__version__),
            "warp": str(warp.__version__),
            "torch": str(torch.__version__),
            "torch_cuda": str(torch.version.cuda),
            "usd": str(Usd.GetVersion()),
            "gpu": str(torch.cuda.get_device_name(0)),
            "rtx_settings": {
                "verify_driver_version_enabled": carb.settings.get_settings().get(
                    "/rtx/verifyDriverVersion/enabled"
                ),
                "render_mode": carb.settings.get_settings().get(
                    "/rtx/rendermode"
                ),
                "minimal_shading_mode": carb.settings.get_settings().get(
                    "/rtx/minimal/mode"
                ),
            },
            "modules": [
                _module_record(name)
                for name in (
                    "isaacsim",
                    "carb",
                    "numpy",
                    "newton",
                    "omni.kit.app",
                    "torch",
                    "warp",
                    "pxr.Usd",
                )
            ],
        }
    except BaseException:
        application.close()
        raise
    return application


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=sorted(EXPECTED), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unvalidated-driver", action="store_true")
    args = parser.parse_args(argv)
    receipt = _base_receipt(args.lane)
    application = None
    if args.lane == "newton140":
        _attest_newton(receipt)
    else:
        driver = _isaac_driver_preflight(
            allow_unvalidated_driver=args.allow_unvalidated_driver
        )
        receipt["driver_preflight"] = driver
        application = _attest_isaac(
            receipt,
            allow_unvalidated_driver=args.allow_unvalidated_driver,
        )
        receipt["capabilities"] = {
            "physics": {
                "status": "passed",
                "claim": "python_usd_newton_warp_cuda_same_process_available",
            },
            "rtx": {
                "status": (
                    "passed"
                    if driver["isaac601_rtx_supported"]
                    else "unvalidated_override_enabled"
                    if args.allow_unvalidated_driver
                    else "blocked_driver"
                ),
                "blocker": (
                    None
                    if driver["isaac601_rtx_supported"]
                    or args.allow_unvalidated_driver
                    else "isaac601_rtx_driver_unsupported"
                ),
                "formal_evidence_eligible": False,
            },
        }
    receipt["status"] = "passed"
    receipt["content_sha256"] = _canonical_sha256(receipt)
    _atomic_json(args.output.resolve(), receipt)
    print(
        json.dumps(
            {
                "status": "passed",
                "lane": args.lane,
                "output": str(args.output.resolve()),
                "content_sha256": receipt["content_sha256"],
            },
            sort_keys=True,
        )
    )
    if application is not None:
        application.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Probe PhysX/PBD fluid schemas after Isaac Sim SimulationApp startup."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_NAMES = [
    "PhysxSceneAPI",
    "PhysxParticleSystem",
    "PhysxParticleSetAPI",
    "PhysxParticleAPI",
    "PhysxPBDMaterialAPI",
    "PhysxParticleAnisotropyAPI",
    "PhysxParticleSmoothingAPI",
    "PhysxParticleIsosurfaceAPI",
]


def _import_status(name: str) -> dict[str, Any]:
    try:
        mod = __import__(name, fromlist=["*"])
        return {"ok": True, "file": getattr(mod, "__file__", None)}
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}


def _build_report() -> tuple[dict[str, Any], Any | None]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_isaacsim41_app_schema_probe",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "accept_eula": os.environ.get("ACCEPT_EULA"),
            "omni_kit_accept_eula": os.environ.get("OMNI_KIT_ACCEPT_EULA"),
        },
        "events": [],
        "imports_after_app": {},
        "physx_schema_attrs": {},
        "gpu_probe": _gpu_probe(),
        "runtime_step_executed": False,
        "true_fluid_runtime_claim_allowed": False,
    }
    app = None
    try:
        from isaacsim import SimulationApp

        report["events"].append("SimulationApp import OK")
        app = SimulationApp({"headless": True, "width": 64, "height": 64})
        report["events"].append("SimulationApp start OK")

        for name in ["pxr", "pxr.Usd", "pxr.PhysxSchema", "omni.physx"]:
            report["imports_after_app"][name] = _import_status(name)

        try:
            from pxr import PhysxSchema

            for schema_name in SCHEMA_NAMES:
                report["physx_schema_attrs"][schema_name] = hasattr(PhysxSchema, schema_name)
        except Exception as exc:
            report["physx_schema_attr_error"] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    except Exception as exc:
        report["fatal_error"] = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc()[-4000:],
        }
    return report, app


def _gpu_probe() -> dict[str, Any]:
    probe: dict[str, Any] = {}
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        probe["nvidia_smi"] = {
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr_tail": proc.stderr[-1000:],
        }
    except Exception as exc:
        probe["nvidia_smi"] = {"error_type": type(exc).__name__, "error": str(exc)}
    try:
        import torch

        probe["torch"] = {
            "cuda_available": bool(torch.cuda.is_available()),
            "device_count": int(torch.cuda.device_count()),
            "device_0_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except Exception as exc:
        probe["torch"] = {"error_type": type(exc).__name__, "error": str(exc)}
    return probe


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="JSON output path.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report, app = _build_report()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report["events"].append("writing probe JSON before SimulationApp close")
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"IsaacSim41 app schema probe out={out_path}", flush=True)
    if app is not None:
        app.close()
    fatal = report.get("fatal_error")
    if fatal:
        return 2
    attrs = report.get("physx_schema_attrs", {})
    required = ["PhysxSceneAPI", "PhysxParticleSystem", "PhysxParticleSetAPI", "PhysxPBDMaterialAPI"]
    return 0 if all(attrs.get(name) is True for name in required) else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

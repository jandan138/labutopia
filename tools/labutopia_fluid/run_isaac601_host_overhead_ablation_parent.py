#!/usr/bin/env python3
"""Parent launcher for Isaac 6 host-overhead ablation (experimental)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PREFIX = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim601-fluid-py312"
)
LOCK = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/environment_locks/isaacsim601"
    / "environment-lock.json"
)
PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
CHILD = (
    REPO_ROOT
    / "tools/labutopia_fluid/run_isaac601_host_overhead_ablation_child.py"
)
MODES = ("none", "isaac_kit", "isaac_kit_particles")


def _sealed_environment(run_root: Path) -> dict[str, str]:
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
    return {
        **{name: str(path) for name, path in directories.items()},
        "PATH": f"{PREFIX / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
        "ACCEPT_EULA": "Y",
        "OMNI_KIT_ACCEPT_EULA": "YES",
        "LD_LIBRARY_PATH": str(PREFIX / "lib"),
    }


def _short_runtime_root(scope: Path) -> Path:
    parent = Path("/tmp/lbu-fluid-runtime")
    parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{scope}:{time.time_ns()}".encode("utf-8")).hexdigest()[:16]
    root = parent / digest
    root.mkdir(parents=True, exist_ok=False)
    return root


def _mean(timing: dict[str, Any] | None, key: str = "mean_ms") -> float | None:
    if not isinstance(timing, dict):
        return None
    value = timing.get(key)
    return float(value) if value is not None else None


def main() -> int:
    output_root = (
        REPO_ROOT
        / "outputs/newton_only_fluid_solver_benchmark"
        / f"2026-08-04_isaac601_host_overhead_ablation_r2"
    )
    output_root.mkdir(parents=True, exist_ok=False)
    frames = 120
    particle_count = 3600
    parameters = {
        "boundary_kind": "boxes",
        "maximum_dt_s": 1.0 / 120.0,
        "profile_stages": False,
        "sound_speed_m_s": 4.0,
        "viscosity": 0.002,
    }
    records: list[dict[str, Any]] = []
    for index, mode in enumerate(MODES):
        scope = output_root / "runs" / mode
        scope.mkdir(parents=True, exist_ok=False)
        artifacts = scope / "artifacts"
        receipt = scope / "runtime_receipt.json"
        failure = scope / "child_failure.json"
        microbench = scope / "host_microbench.json" if mode == "none" else None
        command = [
            str(PREFIX / "bin/python"),
            "-I",
            "-B",
            str(CHILD),
            "--lock-manifest",
            str(LOCK),
            "--runtime-receipt",
            str(receipt),
            "--child-failure",
            str(failure),
            "--host-runtime-update",
            mode,
        ]
        if microbench is not None:
            command.extend(
                [
                    "--host-microbench-output",
                    str(microbench),
                    "--host-microbench-frames",
                    str(frames),
                    "--host-microbench-particles",
                    str(particle_count),
                ]
            )
        command.extend(
            [
                "--",
                "--solver-id",
                "labutopia_wcsph",
                "--packet",
                str(PACKET),
                "--output-dir",
                str(artifacts),
                "--particle-count",
                str(particle_count),
                "--max-observations",
                str(frames),
                "--warmup-observations",
                "2",
                "--parameters-json",
                json.dumps(parameters, sort_keys=True),
            ]
        )
        runtime_root = _short_runtime_root(scope)
        env = _sealed_environment(runtime_root)
        stdout_path = scope / "child.stdout.log"
        stderr_path = scope / "child.stderr.log"
        started = time.time()
        print(f"[ablation] start mode={mode}", flush=True)
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        finished = time.time()
        result_path = artifacts / "result.json"
        result = (
            json.loads(result_path.read_text(encoding="utf-8"))
            if result_path.is_file()
            else None
        )
        timing = result.get("timing") if isinstance(result, dict) else None
        record = {
            "mode": mode,
            "returncode": completed.returncode,
            "elapsed_wall_s": finished - started,
            "result_path": str(result_path) if result_path.is_file() else None,
            "physics_mean_ms": _mean((timing or {}).get("physics_logical_frame")),
            "host_runtime_update_mean_ms": _mean((timing or {}).get("host_runtime_update")),
            "usd_authoring_mean_ms": _mean((timing or {}).get("host_usd_particle_authoring")),
            "readback_mean_ms": _mean((timing or {}).get("particle_readback")),
            "score_mean_ms": _mean((timing or {}).get("quality_scoring")),
            "simulation_chain_mean_ms": _mean((timing or {}).get("simulation_chain_frame")),
            "host_microbench_path": str(microbench) if microbench and microbench.is_file() else None,
        }
        records.append(record)
        print(json.dumps(record, sort_keys=True), flush=True)
        if completed.returncode != 0:
            summary = {
                "schema": "labutopia.isaac601_host_overhead_ablation.v1",
                "status": "failed",
                "failed_mode": mode,
                "records": records,
            }
            (output_root / "summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return completed.returncode or 2

    by_mode = {row["mode"]: row for row in records}
    physics = by_mode["none"]["physics_mean_ms"]
    kit_only = by_mode["isaac_kit"]["host_runtime_update_mean_ms"]
    particle_host = by_mode["isaac_kit_particles"]["host_runtime_update_mean_ms"]
    summary = {
        "schema": "labutopia.isaac601_host_overhead_ablation.v1",
        "status": "passed",
        "claim_boundary": (
            "experimental_isaac601_lane;headless_no_rtx;"
            "not_product_full_chain;not_formal_isaac41_evidence"
        ),
        "configuration": {
            "particle_count": particle_count,
            "observations": frames,
            "solver_id": "labutopia_wcsph",
            "packet": str(PACKET),
        },
        "records": records,
        "derived": {
            "physics_only_ms": physics,
            "empty_kit_update_on_fluid_path_ms": kit_only,
            "usd_points_plus_kit_host_ms": particle_host,
            "particle_bridge_extra_over_empty_kit_ms": (
                None
                if particle_host is None or kit_only is None
                else particle_host - kit_only
            ),
            "isaac41_product_residual_reference_ms": 80.6,
            "note": (
                "Isaac 4.1 product residual 80.6 ms includes product dry/cameras/"
                "PBD path costs and is not the same meter as this Isaac 6 host ablation."
            ),
        },
    }
    if records[0].get("host_microbench_path"):
        summary["host_microbench"] = json.loads(
            Path(records[0]["host_microbench_path"]).read_text(encoding="utf-8")
        )
    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["derived"], indent=2, sort_keys=True), flush=True)
    print(f"summary={output_root / 'summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

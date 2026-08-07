#!/usr/bin/env python3
"""Run repeated WCSPH scaling in locked Newton and Isaac 6 processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_contract import (  # noqa: E402
    EXPECTED_OBSERVATION_COUNT,
    sha256_file,
)
from tools.labutopia_fluid.newton_only_contract import (  # noqa: E402
    RESOLUTIONS,
    SOLVERS_BY_ID,
)
from tools.labutopia_fluid.run_newton_only_solver_search import (  # noqa: E402
    gpu_snapshot,
    wait_for_idle_gpu,
)


PREFIX_ROOT = Path("/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs")
LANES = {
    "newton140": {
        "prefix": PREFIX_ROOT / "embodied-eval-os-sim-newton140-mpm-py312",
        "child": REPO_ROOT / "tools/labutopia_fluid/run_newton140_wcsph_attested_child.py",
        "lock_manifest": REPO_ROOT
        / "outputs/fluid_benchmark_isaac601_newton140/environment_locks/newton140/environment-lock.json",
    },
    "isaac601": {
        "prefix": PREFIX_ROOT / "embodied-eval-os-sim-isaacsim601-fluid-py312",
        "child": REPO_ROOT / "tools/labutopia_fluid/run_isaac601_wcsph_attested_child.py",
        "lock_manifest": REPO_ROOT
        / "outputs/fluid_benchmark_isaac601_newton140/environment_locks/isaacsim601/environment-lock.json",
    },
}
DEFAULT_PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _source_record() -> dict[str, Any]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {
        "revision": revision,
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }


def _sealed_environment(prefix: Path, run_root: Path, *, isaac: bool) -> dict[str, str]:
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


def _short_runtime_root(scope: Path) -> Path:
    """Return a run-unique short path so NVRTC does not reject TMPDIR length."""
    parent = Path("/tmp/lbu-fluid-runtime")
    parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(scope).encode("utf-8")).hexdigest()[:16]
    root = parent / digest
    if root.exists():
        raise FileExistsError(f"short_runtime_root_exists:{root}")
    return root


def _is_completed_result(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("timing"), Mapping)
        and isinstance(value.get("stability"), Mapping)
        and isinstance(value.get("quality"), Mapping)
        and isinstance(value.get("artifacts"), Mapping)
    )


def _descendant_pids(root_pid: int) -> set[int]:
    """Return the live process tree rooted at ``root_pid`` using procfs."""
    parents: dict[int, int] = {}
    for stat_path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat_path.read_text(encoding="utf-8").split()
            parents[int(fields[0])] = int(fields[3])
        except (FileNotFoundError, IndexError, PermissionError, ValueError):
            continue
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return descendants


def _is_negligible_swiftshader_process(process: Mapping[str, Any]) -> bool:
    name = str(process.get("process_name", ""))
    return (
        "chrome" in name
        and "--use-angle=swiftshader-webgl" in name
        and int(process.get("used_memory_mib", 10**9)) <= 32
    )


def _gpu_process_classification(
    root_pid: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    owned = _descendant_pids(root_pid)
    external = [
        process
        for process in gpu_snapshot()["compute_processes"]
        if int(process["pid"]) not in owned
    ]
    advisory = [process for process in external if _is_negligible_swiftshader_process(process)]
    foreign = [process for process in external if not _is_negligible_swiftshader_process(process)]
    return foreign, advisory


def _terminate_process(process: subprocess.Popen[bytes]) -> int:
    process.terminate()
    try:
        return process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=10.0)


def _preflight(lanes: Sequence[str]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for lane in lanes:
        selected = LANES[lane]
        prefix = selected["prefix"]
        lock = selected["lock_manifest"]
        checks[lane] = {
            "python_exists": (prefix / "bin/python").is_file(),
            "lock_exists": lock.is_file(),
            "child_exists": selected["child"].is_file(),
            "prefix": str(prefix),
            "lock_manifest": str(lock),
        }
    passed = all(
        record["python_exists"]
        and record["lock_exists"]
        and record["child_exists"]
        for record in checks.values()
    )
    return {"passed": passed, "lanes": checks}


def _run_one(
    *,
    lane: str,
    solver_id: str,
    particle_count: int,
    repeat_index: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    selected = LANES[lane]
    prefix: Path = selected["prefix"]
    lock_manifest: Path = selected["lock_manifest"]
    scope = (
        args.output_root
        / "runs"
        / lane
        / solver_id
        / str(particle_count)
        / f"repeat_{repeat_index:02d}"
    )
    scope.mkdir(parents=True)
    artifact_dir = scope / "artifacts"
    receipt_path = scope / "runtime_receipt.json"
    failure_path = scope / "child_failure.json"
    parameters = {
        "sound_speed_m_s": args.sound_speed_m_s,
        "viscosity": args.viscosity,
        "maximum_dt_s": args.maximum_dt_s,
        "boundary_kind": "boxes",
        "profile_stages": False,
    }
    parameters.update(args.parameters)
    command = [str(prefix / "bin/python"), "-I", "-B", str(selected["child"])]
    command.extend(
        [
            "--lock-manifest",
            str(lock_manifest),
            "--runtime-receipt",
            str(receipt_path),
            "--child-failure",
            str(failure_path),
            "--",
            "--solver-id",
            solver_id,
            "--packet",
            str(args.packet),
            "--output-dir",
            str(artifact_dir),
            "--particle-count",
            str(particle_count),
            "--max-observations",
            str(args.max_observations),
            "--warmup-observations",
            str(args.warmup_observations),
            "--parameters-json",
            json.dumps(parameters, sort_keys=True),
        ]
    )
    if args.capture_all_particle_frames:
        command.append("--capture-all-particle-frames")
    if args.trajectory_npz is not None:
        command.extend(["--trajectory-npz", str(args.trajectory_npz)])
    runtime_root = _short_runtime_root(scope)
    environment = _sealed_environment(prefix, runtime_root, isaac=lane == "isaac601")
    stdout_path = scope / "child.stdout.log"
    stderr_path = scope / "child.stderr.log"
    started = time.time()
    gpu_isolation_samples: list[dict[str, Any]] = []
    contention: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
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
            sample = {
                "observed_unix_s": time.time(),
                "foreign_compute_processes": foreign,
                "advisory_compute_processes": advisory,
            }
            gpu_isolation_samples.append(sample)
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
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else None
    )
    completed_result = returncode == 0 and not contention and _is_completed_result(result)
    if contention:
        status = "failed_gpu_contention"
    elif completed_result:
        status = "completed"
    else:
        status = "failed"
    record = {
        "lane": lane,
        "solver_id": solver_id,
        "particle_count": particle_count,
        "repeat_index": repeat_index,
        "status": status,
        "result_status": result.get("status") if isinstance(result, Mapping) else None,
        "returncode": returncode,
        "started_unix_s": started,
        "finished_unix_s": time.time(),
        "command": command,
        "environment_sha256": _canonical_sha256(environment),
        "short_runtime_root": str(runtime_root),
        "gpu_isolation": {
            "monitor_interval_s": args.gpu_monitor_interval_s,
            "sample_count": len(gpu_isolation_samples),
            "passed": not contention,
            "contention": contention,
            "advisories": advisories,
        },
        "stdout": {"path": str(stdout_path), "sha256": sha256_file(stdout_path)},
        "stderr": {"path": str(stderr_path), "sha256": sha256_file(stderr_path)},
        "runtime_receipt": (
            {"path": str(receipt_path), "sha256": sha256_file(receipt_path)}
            if receipt_path.is_file()
            else None
        ),
        "result_path": str(result_path) if result_path.is_file() else None,
        "result_sha256": sha256_file(result_path) if result_path.is_file() else None,
        "result": result,
    }
    _atomic_json(scope / "run_manifest.json", record)
    return record


def _summaries(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for lane in sorted({str(record["lane"]) for record in records}):
        for solver_id in sorted(
            {
                str(record.get("solver_id", "labutopia_wcsph"))
                for record in records
                if record["lane"] == lane
            }
        ):
            for particle_count in sorted(
                {
                    int(record["particle_count"])
                    for record in records
                    if record["lane"] == lane
                    and str(record.get("solver_id", "labutopia_wcsph")) == solver_id
                }
            ):
                selected = [
                    record
                    for record in records
                    if record["lane"] == lane
                    and str(record.get("solver_id", "labutopia_wcsph")) == solver_id
                    and int(record["particle_count"]) == particle_count
                    and record["status"] == "completed"
                ]
                physics = np.asarray(
                    [
                        record["result"]["timing"]["physics_logical_frame"]["mean_ms"]
                        for record in selected
                    ],
                    dtype=np.float64,
                )
                chain = np.asarray(
                    [
                        record["result"]["timing"]["simulation_chain_frame"]["mean_ms"]
                        for record in selected
                    ],
                    dtype=np.float64,
                )
                rows.append(
                    {
                        "lane": lane,
                        "solver_id": solver_id,
                        "particle_count": particle_count,
                        "headless": True,
                        "completed_repeats": len(selected),
                        "physics_mean_ms_across_repeats": float(np.mean(physics)) if len(physics) else None,
                        "physics_fps": float(1000.0 / np.mean(physics)) if len(physics) else None,
                        "simulation_chain_mean_ms_across_repeats": float(np.mean(chain)) if len(chain) else None,
                        "simulation_chain_fps": float(1000.0 / np.mean(chain)) if len(chain) else None,
                        "stability_passed_all_repeats": bool(selected)
                        and all(record["result"]["stability"]["passed"] for record in selected),
                        "target_fraction": (
                            float(np.mean([record["result"]["quality"]["final_score"]["target_fraction"] for record in selected]))
                            if selected
                            else None
                        ),
                        "tabletop_spill_fraction": (
                            float(np.mean([record["result"]["quality"]["final_score"]["tabletop_spill_fraction"] for record in selected]))
                            if selected
                            else None
                        ),
                    }
                )
    return rows


def _runtime_parity(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    comparisons = []
    solver_ids = sorted(
        {str(record.get("solver_id", "labutopia_wcsph")) for record in records}
    )
    for solver_id in solver_ids:
        counts = sorted(
            {
                int(record["particle_count"])
                for record in records
                if str(record.get("solver_id", "labutopia_wcsph")) == solver_id
            }
        )
        for particle_count in counts:
            selected = {}
            for lane in ("newton140", "isaac601"):
                selected[lane] = next(
                    (
                        record
                        for record in records
                        if record["lane"] == lane
                        and str(record.get("solver_id", "labutopia_wcsph")) == solver_id
                        and int(record["particle_count"]) == particle_count
                        and int(record["repeat_index"]) == 0
                        and record["status"] == "completed"
                    ),
                    None,
                )
            if any(value is None for value in selected.values()):
                continue
            arrays = {}
            for lane, record in selected.items():
                artifact = record["result"]["artifacts"]["all_particle_frames"]
                if artifact is None:
                    arrays = {}
                    break
                with np.load(Path(artifact["path"]), allow_pickle=False) as archive:
                    arrays[lane] = np.asarray(archive["particle_positions"], dtype=np.float64)
            if len(arrays) != 2:
                continue
            if arrays["newton140"].shape != arrays["isaac601"].shape:
                comparisons.append(
                    {
                        "particle_count": particle_count,
                        "solver_id": solver_id,
                        "passed": False,
                        "reason": "particle_frame_shape_mismatch",
                    }
                )
                continue
            distances = np.linalg.norm(arrays["newton140"] - arrays["isaac601"], axis=2)
            radius = float(selected["newton140"]["result"]["particle_radius_m"])
            target_delta = abs(
                float(selected["newton140"]["result"]["quality"]["final_score"]["target_fraction"])
                - float(selected["isaac601"]["result"]["quality"]["final_score"]["target_fraction"])
            )
            spill_delta = abs(
                float(selected["newton140"]["result"]["quality"]["final_score"]["tabletop_spill_fraction"])
                - float(selected["isaac601"]["result"]["quality"]["final_score"]["tabletop_spill_fraction"])
            )
            rmse = float(np.sqrt(np.mean(np.square(distances))))
            p99 = float(np.percentile(distances, 99))
            checks = {
                "position_rmse_lte_quarter_radius": rmse <= 0.25 * radius,
                "position_p99_lte_one_radius": p99 <= radius,
                "target_fraction_delta_lte_2pp": target_delta <= 0.02,
                "spill_fraction_delta_lte_2pp": spill_delta <= 0.02,
            }
            comparisons.append(
                {
                    "particle_count": particle_count,
                    "solver_id": solver_id,
                    "frame_count": int(distances.shape[0]),
                    "particle_radius_m": radius,
                    "position_rmse_m": rmse,
                    "position_p99_m": p99,
                    "target_fraction_delta": target_delta,
                    "tabletop_spill_fraction_delta": spill_delta,
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
    return comparisons


def run(args: argparse.Namespace) -> int:
    if args.output_root.exists():
        raise FileExistsError(f"output_root_exists:{args.output_root}")
    args.output_root.mkdir(parents=True)
    preflight = _preflight(args.lanes)
    _atomic_json(args.output_root / "preflight.json", preflight)
    if not preflight["passed"]:
        _atomic_json(
            args.output_root / "matrix.json",
            {
                "schema": "labutopia.wcsph_scaling_matrix.v1",
                "status": "blocked_infrastructure",
                "preflight": preflight,
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
            args.output_root / "matrix.json",
            {
                "schema": "labutopia.wcsph_scaling_matrix.v1",
                "status": "blocked_gpu_busy",
                "gpu_gate": gpu_gate,
            },
        )
        return 2
    records = []
    abort_for_gpu_contention = False
    for lane in args.lanes:
        for solver_id in args.solver_ids:
            for particle_count in args.particle_counts:
                for repeat_index in range(args.repeats):
                    record = _run_one(
                        lane=lane,
                        solver_id=solver_id,
                        particle_count=particle_count,
                        repeat_index=repeat_index,
                        args=args,
                    )
                    records.append(record)
                    if record["status"] == "failed_gpu_contention":
                        abort_for_gpu_contention = True
                        break
                if abort_for_gpu_contention:
                    break
            if abort_for_gpu_contention:
                break
        if abort_for_gpu_contention:
            break
    postflight = gpu_snapshot()
    matrix = {
        "schema": "labutopia.wcsph_scaling_matrix.v1",
        "status": (
            "blocked_gpu_contention"
            if abort_for_gpu_contention
            else "completed"
            if all(record["status"] == "completed" for record in records)
            else "completed_with_failures"
        ),
        "run_id": secrets.token_hex(16),
        "claim_boundary": (
            "experimental_kinematic_replay;speed_valid_when_stability_passes;"
            "pour_quality_diagnostic;not_formal_isaac41_evidence"
        ),
        "policy": "numeric_stability_then_speed;task_quality_does_not_block_timing",
        "source": _source_record(),
        "packet": {"path": str(args.packet), "sha256": sha256_file(args.packet)},
        "trajectory": (
            {"path": str(args.trajectory_npz), "sha256": sha256_file(args.trajectory_npz)}
            if args.trajectory_npz is not None
            else None
        ),
        "gpu_idle_gate": gpu_gate,
        "gpu_postflight": postflight,
        "configuration": {
            "lanes": args.lanes,
            "solver_ids": args.solver_ids,
            "particle_counts": args.particle_counts,
            "repeats": args.repeats,
            "observation_count": args.max_observations,
            "sound_speed_m_s": args.sound_speed_m_s,
            "viscosity": args.viscosity,
            "maximum_dt_s": args.maximum_dt_s,
            "boundary_kind": "boxes",
            "capture_all_particle_frames": args.capture_all_particle_frames,
            "parameters": args.parameters,
        },
        "summary": _summaries(records),
        "runtime_parity": _runtime_parity(records),
        "runs": [
            {key: value for key, value in record.items() if key != "result"}
            for record in records
        ],
    }
    matrix["content_sha256"] = _canonical_sha256(matrix)
    _atomic_json(args.output_root / "matrix.json", matrix)
    return 0 if matrix["status"] == "completed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--lane", dest="lanes", action="append", choices=sorted(LANES))
    parser.add_argument(
        "--solver-id",
        dest="solver_ids",
        action="append",
        choices=sorted(SOLVERS_BY_ID),
    )
    parser.add_argument("--particle-count", dest="particle_counts", action="append", type=int, choices=RESOLUTIONS)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-observations", type=int, default=EXPECTED_OBSERVATION_COUNT)
    parser.add_argument("--warmup-observations", type=int, default=2)
    parser.add_argument("--sound-speed-m-s", type=float, default=4.0)
    parser.add_argument("--viscosity", type=float, default=0.002)
    parser.add_argument("--maximum-dt-s", type=float, default=1.0 / 120.0)
    parser.add_argument("--parameters-json", default="{}")
    parser.add_argument("--trajectory-npz", type=Path)
    parser.add_argument("--wait-gpu-hours", type=float, default=24.0)
    parser.add_argument("--gpu-poll-seconds", type=float, default=60.0)
    parser.add_argument("--gpu-idle-samples", type=int, default=3)
    parser.add_argument("--child-timeout-s", type=float, default=3600.0)
    parser.add_argument("--gpu-monitor-interval-s", type=float, default=1.0)
    parser.add_argument("--capture-all-particle-frames", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_root = args.output_root.resolve()
    args.packet = args.packet.resolve(strict=True)
    if args.trajectory_npz is not None:
        args.trajectory_npz = args.trajectory_npz.resolve(strict=True)
    try:
        parameters = json.loads(args.parameters_json)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid --parameters-json: {error}") from error
    if not isinstance(parameters, Mapping):
        raise SystemExit("--parameters-json must decode to an object")
    args.parameters = dict(parameters)
    args.lanes = list(dict.fromkeys(args.lanes or ["newton140", "isaac601"]))
    args.solver_ids = list(
        dict.fromkeys(args.solver_ids or ["labutopia_dfsph", "labutopia_wcsph"])
    )
    args.particle_counts = sorted(set(args.particle_counts or RESOLUTIONS))
    if args.repeats < 1 or args.max_observations < 1 or args.max_observations > EXPECTED_OBSERVATION_COUNT:
        raise SystemExit("invalid repeat or observation count")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

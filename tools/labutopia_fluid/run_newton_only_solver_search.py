#!/usr/bin/env python3
"""Fail-closed 24+8 Newton-only fluid solver search orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
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
    load_packet,
    sha256_file,
)
from tools.labutopia_fluid.newton_only_contract import (  # noqa: E402
    SEARCH_CONFIGURATION_COUNT,
    SEARCH_EXPLORATION_COUNT,
    SEARCH_REFINEMENT_COUNT,
    SOLVER_CATALOG,
    SOLVERS_BY_ID,
    build_search_schedule,
    validate_scene_pack_manifest,
)
from tools.labutopia_fluid.newton_trajectory_search import (  # noqa: E402
    generate_trajectory_candidate,
)


EXPERIMENTAL_NEWTON_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-newton140-mpm-py312/bin/python"
)
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


def _nvidia_query(arguments: Sequence[str]) -> str:
    return subprocess.run(
        ["nvidia-smi", *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def gpu_snapshot() -> dict[str, Any]:
    device = _nvidia_query(
        [
            "--query-gpu=index,name,uuid,driver_version,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    fields = [field.strip() for field in device.splitlines()[0].split(",")]
    compute_text = _nvidia_query(
        ["--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"]
    )
    processes = []
    for line in compute_text.splitlines():
        if not line.strip() or "No running processes" in line:
            continue
        values = [value.strip() for value in line.split(",")]
        processes.append(
            {
                "pid": int(values[0]),
                "process_name": values[1],
                "used_memory_mib": int(values[2]),
            }
        )
    return {
        "index": int(fields[0]),
        "name": fields[1],
        "uuid": fields[2],
        "driver_version": fields[3],
        "memory_total_mib": int(fields[4]),
        "memory_used_mib": int(fields[5]),
        "utilization_percent": int(fields[6]),
        "compute_processes": processes,
    }


def wait_for_idle_gpu(
    *,
    timeout_s: float,
    poll_interval_s: float,
    consecutive_samples: int,
    maximum_utilization_percent: int = 5,
    maximum_used_memory_mib: int = 512,
) -> dict[str, Any]:
    started = time.time()
    samples: list[dict[str, Any]] = []
    consecutive = 0
    while True:
        sample = gpu_snapshot()
        sample["observed_unix_s"] = time.time()
        idle = (
            sample["utilization_percent"] <= maximum_utilization_percent
            and sample["memory_used_mib"] <= maximum_used_memory_mib
            and not sample["compute_processes"]
        )
        sample["idle"] = idle
        samples.append(sample)
        consecutive = consecutive + 1 if idle else 0
        if consecutive >= consecutive_samples:
            return {
                "status": "idle",
                "waited_s": time.time() - started,
                "required_consecutive_samples": consecutive_samples,
                "samples": samples,
            }
        if time.time() - started >= timeout_s:
            return {
                "status": "timeout",
                "waited_s": time.time() - started,
                "required_consecutive_samples": consecutive_samples,
                "samples": samples,
            }
        time.sleep(poll_interval_s)


def _parameters_for_row(solver_id: str, row: Mapping[str, Any]) -> dict[str, Any]:
    substep_tier = row["substep_tier"]
    if isinstance(substep_tier, int):
        maximum_dt_s = 1.0 / (30.0 * max(2, substep_tier))
    else:
        maximum_dt_s = 1.0 / 120.0
    iteration_tier = row["iteration_tier"]
    iterations = int(iteration_tier) if isinstance(iteration_tier, int) else 4
    material_tier = row["material_tier"]
    material = int(material_tier) if isinstance(material_tier, int) else 0
    parameters: dict[str, Any] = {
        "maximum_dt_s": maximum_dt_s,
        "iterations": iterations,
        "maximum_iterations": max(2, iterations),
        "minimum_iterations": 1,
        "tolerance": 0.02 if material == 0 else 0.01,
    }
    if solver_id in {"labutopia_wcsph", "warp_example_sph"}:
        parameters.update(
            {
                "sound_speed_m_s": 4.0 if material == 0 else 8.0,
                "viscosity": 0.002 if material == 0 else 0.01,
            }
        )
    if solver_id == "newton_xpbd_cohesion":
        parameters["cohesion"] = 0.001 if material == 0 else 0.004
    return parameters


def _result_rank_key(result: Mapping[str, Any]) -> tuple[Any, ...]:
    """Rank stable candidates by task quality, then use speed as a tiebreaker."""
    quality = result.get("quality")
    if not isinstance(quality, Mapping):
        raise ValueError("search_result_quality_missing")
    final_score = quality.get("final_score")
    if not isinstance(final_score, Mapping):
        raise ValueError("search_result_final_score_missing")
    timing = result.get("timing")
    if not isinstance(timing, Mapping):
        raise ValueError("search_result_timing_missing")
    physics = timing.get("physics_logical_frame")
    if not isinstance(physics, Mapping):
        raise ValueError("search_result_physics_timing_missing")

    target = float(final_score.get("target_fraction", 0.0))
    spill = float(final_score.get("tabletop_spill_fraction", 1.0))
    below = float(final_score.get("below_table_fraction", 1.0))
    nonfinite = float(final_score.get("nonfinite_fraction", 1.0))
    mean_ms = float(physics.get("mean_ms", float("inf")))
    stability = result.get("stability")
    if isinstance(stability, Mapping):
        stability_passed = bool(stability.get("passed", False))
    else:
        # Compatibility with pre-policy result documents.
        stability_passed = nonfinite == 0.0 and below == 0.0
    finite = all(np.isfinite(value) for value in (target, spill, below, nonfinite, mean_ms))
    if not finite:
        raise ValueError("search_result_rank_value_nonfinite")
    return (
        1 if stability_passed else 0,
        1 if bool(quality.get("numeric_passed", False)) else 0,
        -spill,
        target,
        -mean_ms,
    )


def _load_rankable_result(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    path_value = manifest.get("result_path")
    if not isinstance(path_value, str):
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        _result_rank_key(value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value


def _resolve_refinement_row(
    row: Mapping[str, Any],
    selected_exploration: Mapping[str, Any],
) -> dict[str, Any]:
    selected_row = selected_exploration.get("configuration")
    if not isinstance(selected_row, Mapping):
        raise ValueError("selected_exploration_configuration_missing")
    resolved = dict(row)
    for name in (
        "trajectory_candidate",
        "substep_tier",
        "iteration_tier",
        "material_tier",
    ):
        value = selected_row.get(name)
        if not isinstance(value, int):
            raise ValueError(f"selected_exploration_{name}_invalid")
        resolved[name] = value
    resolved["selected_from_explore_configuration_id"] = selected_row.get(
        "configuration_id"
    )
    resolved["selection_policy"] = "numeric_stability_then_quality_then_speed"
    return resolved


def _sealed_environment(run_root: Path) -> dict[str, str]:
    directories = {
        "HOME": run_root / "home",
        "TMPDIR": run_root / "tmp",
        "XDG_CACHE_HOME": run_root / "cache",
        "XDG_CONFIG_HOME": run_root / "config",
        "XDG_DATA_HOME": run_root / "data",
        "XDG_STATE_HOME": run_root / "state",
    }
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=False)
    return {
        **{name: str(path) for name, path in directories.items()},
        "PATH": f"{EXPERIMENTAL_NEWTON_PYTHON.parent}:/usr/local/bin:/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
    }


def _preflight(args: argparse.Namespace, gpu_gate: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "gpu_idle": gpu_gate.get("status") == "idle",
        "runtime_python_exists": EXPERIMENTAL_NEWTON_PYTHON.is_file(),
        "lock_manifest_exists": args.lock_manifest.is_file(),
        "packet_exists": args.packet.is_file(),
        "scene_pack_exists": args.scene_pack.is_file(),
    }
    parent = EXPERIMENTAL_NEWTON_PYTHON.parents[2]
    usage = shutil.disk_usage(parent)
    checks["runtime_parent_free_bytes"] = usage.free
    checks["minimum_runtime_parent_free_bytes"] = args.minimum_free_bytes
    checks["runtime_parent_has_capacity"] = usage.free >= args.minimum_free_bytes
    scene_validation = None
    if checks["scene_pack_exists"]:
        try:
            scene_validation = validate_scene_pack_manifest(
                json.loads(args.scene_pack.read_text(encoding="utf-8"))
            )
        except BaseException as error:
            checks["scene_pack_valid"] = False
            scene_validation = {"type": type(error).__name__, "message": str(error)}
        else:
            checks["scene_pack_valid"] = True
    else:
        checks["scene_pack_valid"] = False
    passed = all(value is True for name, value in checks.items() if isinstance(value, bool))
    return {"passed": passed, "checks": checks, "scene_validation": scene_validation}


def _trajectory_path(
    output_root: Path,
    solver_id: str,
    candidate_index: int,
    reference: np.ndarray,
) -> tuple[Path, dict[str, Any]]:
    directory = output_root / "trajectory_candidates" / solver_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"candidate_{candidate_index:02d}.npz"
    record_path = directory / f"candidate_{candidate_index:02d}.json"
    if not path.exists():
        candidate, record = generate_trajectory_candidate(reference, candidate_index)
        np.savez_compressed(path, source_poses_xyzw=candidate)
        record = {**record, "path": str(path), "sha256": sha256_file(path)}
        _atomic_json(record_path, record)
    else:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    return path, record


def _run_configuration(
    args: argparse.Namespace,
    *,
    solver_id: str,
    row: Mapping[str, Any],
    trajectory_path: Path,
    repeat_index: int = 0,
) -> dict[str, Any]:
    run_root = args.output_root / "search_runs" / solver_id / str(row["configuration_id"])
    if row.get("phase") == "resolution_refine":
        run_root = run_root / f"repeat_{repeat_index:02d}"
    if run_root.exists():
        raise FileExistsError(f"search_run_exists:{run_root}")
    run_root.mkdir(parents=True)
    receipt_path = run_root / "runtime_receipt.json"
    failure_path = run_root / "child_failure.json"
    artifact_dir = run_root / "artifacts"
    command = [
        str(EXPERIMENTAL_NEWTON_PYTHON),
        "-I",
        "-B",
        str(REPO_ROOT / "tools/labutopia_fluid/run_newton140_wcsph_attested_child.py"),
        "--lock-manifest",
        str(args.lock_manifest),
        "--runtime-receipt",
        str(receipt_path),
        "--child-failure",
        str(failure_path),
        "--",
    ]
    parameters = _parameters_for_row(solver_id, row)
    if solver_id == "newton_implicit_mpm":
        raise RuntimeError(
            "newton_implicit_mpm_uses_the_separate_attested_mpm_runner"
        )
    else:
        command.extend(
            [
                "--solver-id",
                solver_id,
                "--packet",
                str(args.packet),
                "--output-dir",
                str(artifact_dir),
                "--particle-count",
                str(row["particle_count"]),
                "--max-observations",
                str(args.max_observations),
                "--warmup-observations",
                str(args.warmup_observations),
                "--trajectory-npz",
                str(trajectory_path),
                "--parameters-json",
                json.dumps(parameters, sort_keys=True),
            ]
        )
    environment = _sealed_environment(run_root / "runtime")
    stdout_path = run_root / "child.stdout.log"
    stderr_path = run_root / "child.stderr.log"
    started = time.time()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    result_path = artifact_dir / "result.json"
    manifest = {
        "schema": "labutopia.newton_fluid_search_run_manifest.v1",
        "solver_id": solver_id,
        "configuration": dict(row),
        "repeat_index": repeat_index,
        "command": command,
        "returncode": completed.returncode,
        "started_unix_s": started,
        "finished_unix_s": time.time(),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "runtime_receipt_sha256": sha256_file(receipt_path) if receipt_path.is_file() else None,
        "result_path": str(result_path) if result_path.is_file() else None,
        "result_sha256": sha256_file(result_path) if result_path.is_file() else None,
        "status": "completed" if result_path.is_file() else "failed_runtime",
    }
    _atomic_json(run_root / "run_manifest.json", manifest)
    return manifest


def run(args: argparse.Namespace) -> int:
    if args.output_root.exists():
        raise FileExistsError(f"output_root_exists:{args.output_root}")
    args.output_root.mkdir(parents=True)
    gpu_gate = wait_for_idle_gpu(
        timeout_s=args.wait_gpu_hours * 3600.0,
        poll_interval_s=args.gpu_poll_seconds,
        consecutive_samples=args.gpu_idle_samples,
    )
    _atomic_json(args.output_root / "gpu_idle_gate.json", gpu_gate)
    preflight = _preflight(args, gpu_gate)
    _atomic_json(args.output_root / "preflight.json", preflight)
    selected_solvers = [SOLVERS_BY_ID[solver_id] for solver_id in args.solver_ids]
    plan = {
        "schema": "labutopia.newton_fluid_search_plan.v1",
        "run_id": secrets.token_hex(16),
        "configuration_count_per_solver": SEARCH_CONFIGURATION_COUNT,
        "solver_count": len(selected_solvers),
        "total_configuration_count": len(selected_solvers) * SEARCH_CONFIGURATION_COUNT,
        "planned_execution_count": len(selected_solvers)
        * (
            SEARCH_EXPLORATION_COUNT
            + SEARCH_REFINEMENT_COUNT * args.refinement_repeats
        ),
        "refinement_repeats": args.refinement_repeats,
        "solvers": {
            solver.solver_id: build_search_schedule(solver.solver_id)
            for solver in selected_solvers
        },
    }
    _atomic_json(args.output_root / "search_plan.json", plan)
    if not preflight["passed"]:
        manifest = {
            "schema": "labutopia.newton_fluid_search_manifest.v1",
            "status": "blocked_infrastructure",
            "preflight": preflight,
            "gpu_gate": {
                "status": gpu_gate["status"],
                "waited_s": gpu_gate["waited_s"],
            },
            "executed_configuration_count": 0,
            "claim_boundary": "no_performance_claim_generated",
        }
        _atomic_json(args.output_root / "run_manifest.json", manifest)
        print(json.dumps({"status": manifest["status"], "output_root": str(args.output_root)}, sort_keys=True))
        return 2

    packet = load_packet(args.packet)
    reference = packet.array("source_poses_xyzw", (EXPECTED_OBSERVATION_COUNT, 7))
    manifests = []
    refinement_selections: dict[str, Any] = {}
    for solver in selected_solvers:
        schedule = build_search_schedule(solver.solver_id)
        exploration_schedule = schedule[
            : min(SEARCH_EXPLORATION_COUNT, args.max_configurations_per_solver)
        ]
        refinement_budget = max(
            0, args.max_configurations_per_solver - SEARCH_EXPLORATION_COUNT
        )
        refinement_schedule = schedule[
            SEARCH_EXPLORATION_COUNT : SEARCH_EXPLORATION_COUNT
            + min(SEARCH_REFINEMENT_COUNT, refinement_budget)
        ]
        solver_exploration_manifests = []
        for row in exploration_schedule:
            candidate_index = row["trajectory_candidate"]
            if not isinstance(candidate_index, int):
                raise RuntimeError("exploration_trajectory_candidate_not_resolved")
            trajectory_path, _ = _trajectory_path(
                args.output_root, solver.solver_id, candidate_index, reference
            )
            run_manifest = _run_configuration(
                args,
                solver_id=solver.solver_id,
                row=row,
                trajectory_path=trajectory_path,
            )
            manifests.append(run_manifest)
            solver_exploration_manifests.append(run_manifest)

        ranked_exploration = []
        for run_manifest in solver_exploration_manifests:
            result = _load_rankable_result(run_manifest)
            if result is None:
                continue
            ranked_exploration.append(
                {
                    "configuration": run_manifest["configuration"],
                    "result_path": run_manifest["result_path"],
                    "result_sha256": run_manifest["result_sha256"],
                    "rank_key": list(_result_rank_key(result)),
                }
            )
        ranked_exploration.sort(
            key=lambda value: tuple(value["rank_key"]), reverse=True
        )
        selected = ranked_exploration[:2]
        refinement_selections[solver.solver_id] = {
            "selection_policy": "numeric_stability_then_quality_then_speed",
            "rankable_exploration_count": len(ranked_exploration),
            "selected": selected,
            "status": "selected" if selected else "no_rankable_exploration_result",
        }
        if refinement_schedule and not selected:
            refinement_selections[solver.solver_id]["skipped_refinement_count"] = len(
                refinement_schedule
            )
            continue
        for row in refinement_schedule:
            selection_index = min(int(row["refinement_rank"]), len(selected) - 1)
            resolved_row = _resolve_refinement_row(row, selected[selection_index])
            trajectory_path, _ = _trajectory_path(
                args.output_root,
                solver.solver_id,
                int(resolved_row["trajectory_candidate"]),
                reference,
            )
            for repeat_index in range(args.refinement_repeats):
                manifests.append(
                    _run_configuration(
                        args,
                        solver_id=solver.solver_id,
                        row=resolved_row,
                        trajectory_path=trajectory_path,
                        repeat_index=repeat_index,
                    )
                )
    _atomic_json(
        args.output_root / "refinement_selections.json",
        {
            "schema": "labutopia.newton_fluid_refinement_selection.v1",
            "solvers": refinement_selections,
        },
    )
    summary = {
        "schema": "labutopia.newton_fluid_search_manifest.v1",
        "status": "search_complete_visual_review_pending",
        "executed_configuration_count": len(manifests),
        "completed_result_count": sum(row["result_sha256"] is not None for row in manifests),
        "failed_result_count": sum(row["result_sha256"] is None for row in manifests),
        "skipped_refinement_count": sum(
            int(value.get("skipped_refinement_count", 0))
            for value in refinement_selections.values()
        ),
        "claim_boundary": "visual_review_and_top3_repeats_required_before_performance_claim",
    }
    _atomic_json(args.output_root / "run_manifest.json", summary)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--scene-pack", type=Path, required=True)
    parser.add_argument("--lock-manifest", type=Path, required=True)
    parser.add_argument("--wait-gpu-hours", type=float, default=24.0)
    parser.add_argument("--gpu-poll-seconds", type=float, default=60.0)
    parser.add_argument("--gpu-idle-samples", type=int, default=3)
    parser.add_argument("--minimum-free-bytes", type=int, default=8 * 1024**3)
    parser.add_argument("--max-configurations-per-solver", type=int, default=32)
    parser.add_argument("--max-observations", type=int, default=EXPECTED_OBSERVATION_COUNT)
    parser.add_argument("--warmup-observations", type=int, default=2)
    parser.add_argument(
        "--solver-id",
        dest="solver_ids",
        action="append",
        choices=sorted(SOLVERS_BY_ID),
        help=(
            "Solver route to run; repeat for multiple routes "
            "(default: labutopia_dfsph and labutopia_wcsph)."
        ),
    )
    parser.add_argument("--refinement-repeats", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.solver_ids is None:
        args.solver_ids = ["labutopia_dfsph", "labutopia_wcsph"]
    args.solver_ids = list(dict.fromkeys(args.solver_ids))
    for name in ("output_root", "packet", "scene_pack", "lock_manifest"):
        setattr(args, name, getattr(args, name).resolve())
    if (
        args.gpu_idle_samples < 1
        or args.max_configurations_per_solver < 1
        or args.refinement_repeats < 1
    ):
        raise SystemExit("positive sample/configuration counts required")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run quality-first Newton 1.4 MPM solver and step-size experiments.

This is an experimental Newton lane.  It reuses the matched packet and the GPU
idle/activity gates from the Isaac 4.1/Newton matrix, but never labels retarget,
fixed-grid, diagnostic, or large-step candidates as strict Isaac/PBD evidence.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
import os
import sys
import threading
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import run_isaac41_newton140_fluid_matrix as matrix  # noqa: E402


OUTPUT_ROOT = REPO_ROOT / "outputs/fluid_benchmark_isaac41_newton140/solver_sweeps"

CORE_CANDIDATES = (
    {"id": "gs_i05_t5e4", "solver": "gs", "max_iterations": 5, "tolerance": 5.0e-4},
    {"id": "gs_i10_t5e4", "solver": "gs", "max_iterations": 10, "tolerance": 5.0e-4},
    {"id": "gs_i15_t5e4", "solver": "gs", "max_iterations": 15, "tolerance": 5.0e-4},
    {"id": "gs_i10_t2e3", "solver": "gs", "max_iterations": 10, "tolerance": 2.0e-3},
    {"id": "jacobi_i10_t5e4", "solver": "jacobi", "max_iterations": 10, "tolerance": 5.0e-4},
)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _candidate_args(
    args: argparse.Namespace,
    candidate: dict[str, Any],
    *,
    max_observations: int | None = None,
) -> argparse.Namespace:
    trial = copy.deepcopy(args)
    trial.max_observations = max_observations or args.max_observations
    trial.newton_profile = candidate.get("profile", "sparse_q1_gs_fast")
    trial.newton_max_iterations = candidate["max_iterations"]
    trial.newton_tolerance = candidate["tolerance"]
    trial.newton_solver = candidate["solver"]
    trial.newton_grid_type = candidate.get("grid_type")
    trial.newton_grid_padding = candidate.get("grid_padding")
    trial.newton_graph = candidate.get("graph")
    trial.newton_warmstart_mode = candidate.get("warmstart_mode")
    trial.newton_substeps = candidate.get("substeps", 4)
    trial.newton_integration_dt = candidate.get("integration_dt", 1.0 / 120.0)
    trial.timing_warmup_observations = 1
    trial.solver_diagnostics = bool(candidate.get("solver_diagnostics", False))
    trial.timing_breakdown = bool(candidate.get("timing_breakdown", False))
    trial.render_camera_count = 2
    trial.render_surface_mode = "dynamic"
    return trial


def _trial_summary(
    candidate: dict[str, Any],
    record: dict[str, Any],
    gpu_record: dict[str, Any],
    *,
    observation_count: int,
) -> dict[str, Any]:
    result = record.get("result") or {}
    timing = result.get("timing") or {}
    quality = result.get("quality") or {}
    gpu_valid = bool(
        gpu_record["preflight"]["status"] in {"idle", "bypassed_smoke"}
        and not gpu_record["activity"].get("external_process_seen", True)
        and gpu_record["postflight"]["status"] in {"idle", "bypassed_smoke"}
    )
    strict_step = bool(
        candidate.get("substeps", 4) == 4
        and math.isclose(
            candidate.get("integration_dt", 1.0 / 120.0),
            1.0 / 120.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    )
    performance_comparable = bool(
        observation_count == 953
        and gpu_valid
        and timing.get("performance_comparable") is True
        and strict_step
    )
    return {
        "candidate": candidate,
        "lane": record["lane"],
        "process_exit_code": record.get("process", {}).get("exit_code"),
        "result_path": record.get("process", {}).get("command", [None])[-1],
        "result": result,
        "quality_numeric_passed": bool(quality.get("numeric_passed")),
        "target_fraction": (quality.get("final_score") or {}).get("target_fraction"),
        "tabletop_spill_fraction": (quality.get("final_score") or {}).get("tabletop_spill_fraction"),
        "physics_fps": timing.get("physics_fps"),
        "solver_execution_fps": timing.get("solver_execution_fps"),
        "gpu_valid": gpu_valid,
        "strict_step_schedule": strict_step,
        "performance_comparable": performance_comparable,
    }


def _run_trial(
    args: argparse.Namespace,
    run_root: Path,
    candidate: dict[str, Any],
    *,
    ordinal: int,
    max_observations: int | None = None,
) -> dict[str, Any]:
    trial_args = _candidate_args(args, candidate, max_observations=max_observations)
    lane = f"{ordinal:02d}_{candidate['id']}_retarget_physics"
    scope = run_root / lane
    if args.smoke:
        preflight = {"status": "bypassed_smoke", "snapshot": matrix._gpu_snapshot()}
    else:
        preflight = matrix._wait_for_idle(
            trial_args,
            evidence_path=scope / "gpu_idle_preflight.json",
            timeout_s=args.wait_hours * 3600.0,
        )
    if preflight["status"] not in {"idle", "bypassed_smoke"}:
        return {
            "candidate": candidate,
            "lane": lane,
            "status": "blocked_gpu_busy",
            "gpu": {"preflight": preflight},
        }
    activity_path = scope / "gpu_lane_activity.json"
    stop = threading.Event()
    monitor = threading.Thread(
        target=matrix._monitor_lane_activity,
        args=(trial_args,),
        kwargs={"evidence_path": activity_path, "stop": stop},
        name=f"gpu-activity-{lane}",
    )
    monitor.start()
    try:
        record = matrix._run_newton_physics(lane, trial_args, run_root)
    finally:
        stop.set()
        monitor.join()
    activity = matrix._load_json(activity_path)
    if args.smoke:
        postflight = {"status": "bypassed_smoke", "snapshot": matrix._gpu_snapshot()}
    else:
        postflight = matrix._wait_for_idle(
            trial_args,
            evidence_path=scope / "gpu_idle_postflight.json",
            timeout_s=(
                args.postflight_wait_s
                if args.postflight_wait_s is not None
                else args.wait_hours * 3600.0
            ),
        )
    gpu_record = {
        "preflight": preflight,
        "activity": activity,
        "postflight": postflight,
    }
    return {
        "status": "completed" if matrix._lane_passed(record) else "failed_runtime",
        "record": record,
        "gpu": gpu_record,
        "summary": _trial_summary(
            candidate,
            record,
            gpu_record,
            observation_count=trial_args.max_observations,
        ),
    }


def _select_best(trials: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [
        trial["summary"]
        for trial in trials
        if trial.get("status") == "completed"
        and trial.get("summary", {}).get("quality_numeric_passed")
        and trial.get("summary", {}).get("performance_comparable")
        and isinstance(trial.get("summary", {}).get("physics_fps"), (int, float))
    ]
    return max(eligible, key=lambda item: float(item["physics_fps"])) if eligible else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--wait-hours", type=float, default=12.0)
    parser.add_argument("--idle-samples", type=int, default=6)
    parser.add_argument("--idle-interval-s", type=float, default=10.0)
    parser.add_argument("--max-idle-utilization", type=float, default=2.0)
    parser.add_argument("--max-idle-memory-mib", type=float, default=128.0)
    parser.add_argument("--lane-timeout-s", type=float, default=7200.0)
    parser.add_argument("--postflight-wait-s", type=float)
    parser.add_argument("--lane-monitor-interval-s", type=float, default=1.0)
    parser.add_argument("--diagnostic-observations", type=int, default=20)
    parser.add_argument("--skip-diagnostic", action="store_true")
    parser.add_argument("--skip-fixed-grid", action="store_true")
    parser.add_argument("--skip-large-step", action="store_true")
    parser.add_argument("--skip-repeats", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke:
        args.max_observations = min(args.max_observations, 3)
        args.diagnostic_observations = min(args.diagnostic_observations, 2)
        args.idle_samples = 1
        args.wait_hours = 0.0
    if not 1 <= args.max_observations <= 953:
        raise ValueError("max_observations_out_of_range")
    run_id = args.run_id or dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = (args.output_root / run_id).resolve()
    if run_root.exists():
        raise FileExistsError(f"run_root_exists:{run_root}")
    run_root.mkdir(parents=True)

    attestation = matrix._attest_newton(args, run_root)
    trials: list[dict[str, Any]] = []
    ordinal = 0
    if not attestation["passed"]:
        payload = {
            "schema": "labutopia.newton140_mpm_solver_sweep.v1",
            "status": "blocked_newton_runtime_attestation",
            "run_id": run_id,
            "newton_attestation": attestation,
        }
        payload["content_sha256"] = matrix._canonical_sha256(payload)
        _atomic_json(run_root / "sweep.json", payload)
        return 2

    if not args.skip_diagnostic:
        diagnostic = {
            "id": "diagnostic_gs_i15_t5e4",
            "solver": "gs",
            "max_iterations": 15,
            "tolerance": 5.0e-4,
            "solver_diagnostics": True,
            "timing_breakdown": True,
            "claim": "synchronizing_diagnostic_not_performance_comparable",
        }
        trials.append(
            _run_trial(
                args,
                run_root,
                diagnostic,
                ordinal=ordinal,
                max_observations=args.diagnostic_observations,
            )
        )
        ordinal += 1

    for candidate in CORE_CANDIDATES:
        trials.append(_run_trial(args, run_root, dict(candidate), ordinal=ordinal))
        ordinal += 1
        if trials[-1].get("status") != "completed":
            break

    best = _select_best(trials)
    if best is not None and not args.skip_fixed_grid:
        base = best["candidate"]
        fixed = {
            "id": f"fixed_graph_from_{base['id']}",
            "profile": "fixed_q1_gs_graph",
            "solver": base["solver"],
            "max_iterations": base["max_iterations"],
            "tolerance": base["tolerance"],
            "grid_type": "fixed",
            "grid_padding": 40,
            "graph": True,
            "claim": "fixed_grid_cuda_graph_candidate",
        }
        trials.append(_run_trial(args, run_root, fixed, ordinal=ordinal))
        ordinal += 1
        best = _select_best(trials)

    if best is not None and not args.skip_large_step:
        base = best["candidate"]
        for substeps, integration_dt in ((2, 1.0 / 60.0), (1, 1.0 / 30.0)):
            candidate = {
                "id": f"{base['id']}_{substeps}x{integration_dt:.9f}",
                "solver": base["solver"],
                "max_iterations": base["max_iterations"],
                "tolerance": base["tolerance"],
                "substeps": substeps,
                "integration_dt": integration_dt,
                "claim": "non_strict_large_step_candidate",
            }
            trials.append(_run_trial(args, run_root, candidate, ordinal=ordinal))
            ordinal += 1

    repeat_variation = None
    if best is not None and not args.skip_repeats:
        repeat_fps = []
        for repeat_index in range(2):
            candidate = dict(best["candidate"])
            candidate["id"] = f"repeat_{repeat_index + 1}_{candidate['id']}"
            candidate["claim"] = "best_candidate_repeatability"
            trial = _run_trial(args, run_root, candidate, ordinal=ordinal)
            trials.append(trial)
            ordinal += 1
            fps = trial.get("summary", {}).get("physics_fps")
            if isinstance(fps, (int, float)):
                repeat_fps.append(float(fps))
        if len(repeat_fps) == 2:
            mean = sum(repeat_fps) / 2.0
            repeat_variation = {
                "fps": repeat_fps,
                "relative_range": abs(repeat_fps[0] - repeat_fps[1]) / mean,
                "passed_le_5_percent": abs(repeat_fps[0] - repeat_fps[1]) / mean <= 0.05,
            }

    payload = {
        "schema": "labutopia.newton140_mpm_solver_sweep.v1",
        "status": "completed" if all(t.get("status") == "completed" for t in trials) else "partial",
        "claim_boundary": (
            "experimental_newton140_mpm;retarget_quality_sweep;"
            "only_4x_1over120_full953_gpu_valid_rows_are_performance_comparable;"
            "large_step_and_diagnostic_rows_are_non_strict"
        ),
        "run_id": run_id,
        "run_root": str(run_root),
        "source_provenance": matrix._source_provenance(),
        "newton_attestation": attestation,
        "selection_rule": "numeric_quality_pass_then_highest_physics_fps",
        "best": _select_best(trials),
        "repeatability": repeat_variation,
        "trials": trials,
    }
    payload["content_sha256"] = matrix._canonical_sha256(payload)
    _atomic_json(run_root / "sweep.json", payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "best": (payload["best"] or {}).get("candidate"),
                "sweep": str(run_root / "sweep.json"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if payload["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

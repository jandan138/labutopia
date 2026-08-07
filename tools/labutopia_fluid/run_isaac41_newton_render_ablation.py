#!/usr/bin/env python3
"""Measure Isaac 4.1 render/reconstruction ablations for the best Newton lane."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import run_isaac41_newton140_fluid_matrix as matrix  # noqa: E402


OUTPUT_ROOT = REPO_ROOT / "outputs/fluid_benchmark_isaac41_newton140/render_ablations"
CASES = (
    {"id": "particle_instancer_dual_camera", "surface_mode": "particles", "camera_count": 2},
    {"id": "static_surface_dual_camera", "surface_mode": "static-first", "camera_count": 2},
    {"id": "dynamic_surface_single_camera", "surface_mode": "dynamic", "camera_count": 1},
    {"id": "full_dynamic_surface_dual_camera", "surface_mode": "dynamic", "camera_count": 2},
)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _configure(args: argparse.Namespace, case: dict[str, Any]) -> argparse.Namespace:
    args.newton_profile = "sparse_q1_gs_fast"
    args.newton_max_iterations = args.max_iterations
    args.newton_tolerance = args.tolerance
    args.newton_solver = "gs"
    args.newton_grid_type = None
    args.newton_grid_padding = None
    args.newton_warmstart_mode = None
    args.newton_graph = None
    args.newton_substeps = 4
    args.newton_integration_dt = 1.0 / 120.0
    args.timing_warmup_observations = 1
    args.solver_diagnostics = False
    args.timing_breakdown = False
    args.render_camera_count = int(case["camera_count"])
    args.render_surface_mode = str(case["surface_mode"])
    return args


def _run_case(
    args: argparse.Namespace,
    run_root: Path,
    case: dict[str, Any],
    ordinal: int,
) -> dict[str, Any]:
    args = _configure(args, case)
    lane = f"{ordinal:02d}_{case['id']}_newton_retarget_rendered"
    scope = run_root / lane
    preflight = (
        {"status": "bypassed_smoke", "snapshot": matrix._gpu_snapshot()}
        if args.smoke
        else matrix._wait_for_idle(
            args,
            evidence_path=scope / "gpu_idle_preflight.json",
            timeout_s=args.wait_hours * 3600.0,
        )
    )
    if preflight["status"] not in {"idle", "bypassed_smoke"}:
        return {"case": case, "lane": lane, "status": "blocked_gpu_busy", "preflight": preflight}
    activity_path = scope / "gpu_lane_activity.json"
    stop = threading.Event()
    monitor = threading.Thread(
        target=matrix._monitor_lane_activity,
        args=(args,),
        kwargs={"evidence_path": activity_path, "stop": stop},
        name=f"gpu-activity-{lane}",
    )
    monitor.start()
    try:
        record = matrix._run_newton_rendered(lane, args, run_root)
    finally:
        stop.set()
        monitor.join()
    activity = matrix._load_json(activity_path)
    postflight = (
        {"status": "bypassed_smoke", "snapshot": matrix._gpu_snapshot()}
        if args.smoke
        else matrix._wait_for_idle(
            args,
            evidence_path=scope / "gpu_idle_postflight.json",
            timeout_s=(
                args.postflight_wait_s
                if args.postflight_wait_s is not None
                else args.wait_hours * 3600.0
            ),
        )
    )
    newton = record.get("newton_result") or {}
    isaac = record.get("isaac_result") or {}
    gpu_valid = bool(
        preflight["status"] in {"idle", "bypassed_smoke"}
        and not activity.get("external_process_seen", True)
        and postflight["status"] in {"idle", "bypassed_smoke"}
    )
    lane_passed = bool(
        record.get("newton_process", {}).get("exit_code") == 0
        and record.get("isaac_process", {}).get("exit_code") == 0
        and record.get("newton_result") is not None
        and record.get("isaac_result") is not None
        and record.get("shared_memory_cleanup", {}).get("status")
        == "unlinked_by_owner"
    )
    return {
        "case": case,
        "lane": lane,
        "status": "completed" if lane_passed else "failed_runtime",
        "gpu": {"preflight": preflight, "activity": activity, "postflight": postflight},
        "gpu_valid": gpu_valid,
        "record": record,
        "summary": {
            "artifact_ready_fps": (newton.get("timing") or {}).get("artifact_ready_fps"),
            "artifact_ready_mean_ms": (newton.get("timing") or {}).get("artifact_ready_mean_ms"),
            "physics_fps": (newton.get("timing") or {}).get("physics_fps"),
            "transport_write": (newton.get("timing") or {}).get("transport_write_per_observation"),
            "socket_send": (newton.get("timing") or {}).get("socket_send_per_observation"),
            "renderer_roundtrip_wait": (newton.get("timing") or {}).get("renderer_roundtrip_wait_per_observation"),
            "renderer_components": isaac.get("timing"),
            "quality_numeric_passed": bool((newton.get("quality") or {}).get("numeric_passed")),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--max-iterations", type=int, default=15)
    parser.add_argument("--tolerance", type=float, default=5.0e-4)
    parser.add_argument("--wait-hours", type=float, default=12.0)
    parser.add_argument("--idle-samples", type=int, default=6)
    parser.add_argument("--idle-interval-s", type=float, default=10.0)
    parser.add_argument("--max-idle-utilization", type=float, default=2.0)
    parser.add_argument("--max-idle-memory-mib", type=float, default=128.0)
    parser.add_argument("--lane-timeout-s", type=float, default=7200.0)
    parser.add_argument("--postflight-wait-s", type=float)
    parser.add_argument("--lane-monitor-interval-s", type=float, default=1.0)
    parser.add_argument("--cases", nargs="+", choices=tuple(c["id"] for c in CASES))
    parser.add_argument("--smoke", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke:
        args.max_observations = min(args.max_observations, 2)
        args.idle_samples = 1
        args.wait_hours = 0.0
    selected = [case for case in CASES if not args.cases or case["id"] in args.cases]
    run_id = args.run_id or dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = (args.output_root / run_id).resolve()
    if run_root.exists():
        raise FileExistsError(f"run_root_exists:{run_root}")
    run_root.mkdir(parents=True)
    attestation = matrix._attest_newton(args, run_root)
    if not attestation["passed"]:
        payload = {"schema": "labutopia.isaac41_newton_render_ablation.v1", "status": "blocked_newton_runtime_attestation", "newton_attestation": attestation}
        payload["content_sha256"] = matrix._canonical_sha256(payload)
        _atomic_json(run_root / "ablation.json", payload)
        return 2
    cases = [_run_case(args, run_root, case, index) for index, case in enumerate(selected)]
    full = next(
        (case for case in cases if case["case"]["id"] == "full_dynamic_surface_dual_camera" and case.get("status") == "completed"),
        None,
    )
    derived_replay = None
    if full is not None:
        timing = full["summary"]["renderer_components"] or {}
        frame_ms = float((timing.get("frame_processing") or {}).get("mean_ms", 0.0))
        reconstruction_ms = float((timing.get("reconstruction") or {}).get("mean_ms", 0.0))
        derived_replay = {
            "status": "derived_not_separately_measured",
            "dynamic_mesh_authoring_rtx_capture_mean_ms": frame_ms - reconstruction_ms,
            "estimated_fps_if_surface_meshes_were_precomputed": (
                1000.0 / (frame_ms - reconstruction_ms)
                if frame_ms > reconstruction_ms
                else None
            ),
        }
    payload = {
        "schema": "labutopia.isaac41_newton_render_ablation.v1",
        "status": "completed" if all(case.get("status") == "completed" for case in cases) else "partial",
        "claim_boundary": (
            "formal_isaac41_renderer_receipt_per_case;experimental_newton140_particles;"
            "retarget_quality_candidate;derived_replay_row_is_not_measured"
        ),
        "run_id": run_id,
        "run_root": str(run_root),
        "source_provenance": matrix._source_provenance(),
        "newton_attestation": attestation,
        "solver": {"name": "gs", "max_iterations": args.max_iterations, "tolerance": args.tolerance},
        "cases": cases,
        "derived_dynamic_mesh_replay": derived_replay,
    }
    payload["content_sha256"] = matrix._canonical_sha256(payload)
    _atomic_json(run_root / "ablation.json", payload)
    print(json.dumps({"status": payload["status"], "ablation": str(run_root / "ablation.json")}, sort_keys=True), flush=True)
    return 0 if payload["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

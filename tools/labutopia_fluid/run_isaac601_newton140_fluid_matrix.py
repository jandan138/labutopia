#!/usr/bin/env python3
"""Orchestrate the controlled Isaac 6.0.1 + Newton 1.4 fluid matrix."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
ISAAC_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim601-fluid-py312/bin/python"
)
NEWTON_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-newton140-mpm-py312/bin/python"
)
PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs/fluid_benchmark_isaac601_newton140/runs"
ENVIRONMENT_LOCK_ROOT = (
    REPO_ROOT / "outputs/fluid_benchmark_isaac601_newton140/environment_locks"
)
ISAAC_BLOCKED_RECEIPT = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/environment_attestations"
    / "isaacsim601-v3/receipt.json"
)
PROFILES = (
    "sparse_q1_gs_fast",
    "sparse_q1_cg_fast",
    "sparse_q1_jacobi_fast",
    "sparse_q1_gs_balanced",
    "fixed_q1_gs_graph",
)
DEFAULT_PROFILES = (
    "sparse_q1_gs_fast",
    "sparse_q1_jacobi_fast",
    "sparse_q1_gs_balanced",
)

HISTORICAL_BASELINES = [
    {
        "name": "isaac41_physx_pbd_dry",
        "runtime": "Isaac Sim 4.1 / PhysX PBD",
        "solver": "no particles",
        "particle_count": 0,
        "sample": "850 observations, full pick+pour",
        "headless": True,
        "physics_only_fps": None,
        "rendered_2x256_fps": 19.4,
        "reconstruction": False,
        "comparability": "historical_nonmatched_dry_reference",
    },
    {
        "name": "isaac41_physx_pbd_no_reconstruction",
        "runtime": "Isaac Sim 4.1 / PhysX PBD",
        "solver": "PhysX PBD",
        "particle_count": 3600,
        "sample": "200 observations, pick phase",
        "headless": True,
        "physics_only_fps": None,
        "rendered_2x256_fps": 6.1,
        "reconstruction": False,
        "comparability": "historical_busy_gpu_pick_only",
    },
    {
        "name": "isaac41_physx_pbd_full_online",
        "runtime": "Isaac Sim 4.1 / PhysX PBD",
        "solver": "PhysX PBD",
        "particle_count": 3600,
        "sample": "200 observations, pick phase",
        "headless": True,
        "physics_only_fps": None,
        "rendered_2x256_fps": 4.3,
        "full_episode_rendered_fps": 3.0349817522942617,
        "reconstruction": True,
        "comparability": "historical_busy_gpu_pick_only",
    },
]


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


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _gpu_snapshot() -> dict[str, Any]:
    queries = {
        "gpus": [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,driver_version,utilization.gpu,"
            "memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ],
        "compute_processes": [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
    }
    result: dict[str, Any] = {}
    for name, command in queries.items():
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result[name] = {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip().splitlines(),
            "stderr": completed.stderr.strip(),
        }
    result["exclusive"] = (
        result["gpus"]["exit_code"] == 0
        and result["compute_processes"]["exit_code"] == 0
        and not result["compute_processes"]["stdout"]
    )
    return result


def _child_environment(
    prefix: Path,
    run_scope: Path,
    *,
    isaac: bool,
) -> dict[str, str]:
    home = run_scope / "home"
    short_scope = hashlib.sha256(str(run_scope.resolve()).encode("utf-8")).hexdigest()[:12]
    temporary = Path("/tmp") / f"lbf_{short_scope}"
    cache = run_scope / "xdg_cache"
    config = run_scope / "xdg_config"
    data = run_scope / "xdg_data"
    for path in (home, temporary, cache, config, data):
        path.mkdir(parents=True, exist_ok=True)
    environment = {
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(config),
        "XDG_DATA_HOME": str(data),
        "PATH": f"{prefix / 'bin'}:/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "CUDA_VISIBLE_DEVICES": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    if isaac:
        environment.update(
            {
                "ACCEPT_EULA": "Y",
                "LD_LIBRARY_PATH": str(prefix / "lib"),
                "OMNI_KIT_ACCEPT_EULA": "YES",
            }
        )
    return environment


def _run_logged(
    command: list[str],
    *,
    environment: dict[str, str],
    log_dir: Path,
    timeout_s: float,
) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
    started = time.time()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            timeout=timeout_s,
            check=False,
        )
    return {
        "command": command,
        "environment_sha256": _canonical_sha256(environment),
        "started_unix_s": started,
        "finished_unix_s": time.time(),
        "exit_code": completed.returncode,
        "stdout": {
            "path": str(stdout_path),
            "sha256": _sha256_file(stdout_path),
        },
        "stderr": {
            "path": str(stderr_path),
            "sha256": _sha256_file(stderr_path),
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_document_not_object:{path}")
    return value


def _environment_lock_record(lane: str) -> dict[str, Any]:
    path = ENVIRONMENT_LOCK_ROOT / lane / "environment-lock.json"
    if not path.is_file():
        raise RuntimeError(f"environment_lock_missing:{lane}:{path}")
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "manifest": _load_json(path),
    }


def _source_record() -> dict[str, Any]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    return {
        "revision": revision,
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }


def _rendered_lane_record(rendered_requested: bool) -> dict[str, Any]:
    if rendered_requested:
        return {"status": "requested"}
    if ISAAC_BLOCKED_RECEIPT.is_file():
        receipt = _load_json(ISAAC_BLOCKED_RECEIPT)
        return {
            "status": receipt.get("status"),
            "reason": receipt.get("blocker"),
            "receipt_path": str(ISAAC_BLOCKED_RECEIPT),
            "receipt_sha256": _sha256_file(ISAAC_BLOCKED_RECEIPT),
            "driver_preflight": receipt.get("driver_preflight"),
        }
    return {"status": "not_requested"}


def _ensure_packet(run_root: Path, timeout_s: float) -> dict[str, Any]:
    if PACKET.is_file():
        return {
            "status": "reused",
            "path": str(PACKET),
            "sha256": _sha256_file(PACKET),
        }
    output_dir = PACKET.parent
    command = [
        str(NEWTON_PYTHON),
        str(REPO_ROOT / "tools/labutopia_fluid/build_fluid_benchmark_packet.py"),
        "--output-dir",
        str(output_dir),
    ]
    record = _run_logged(
        command,
        environment=_child_environment(
            NEWTON_PYTHON.parents[1],
            run_root / "packet_runtime",
            isaac=False,
        ),
        log_dir=run_root / "packet_logs",
        timeout_s=timeout_s,
    )
    if record["exit_code"] != 0 or not PACKET.is_file():
        raise RuntimeError(f"packet_build_failed:{record}")
    return {
        "status": "built",
        "path": str(PACKET),
        "sha256": _sha256_file(PACKET),
        "process": record,
    }


def _attest(
    lane: str,
    python: Path,
    run_root: Path,
    timeout_s: float,
) -> dict[str, Any]:
    scope = run_root / f"attest_{lane}"
    output = scope / "receipt.json"
    command = [
        str(python),
        str(
            REPO_ROOT
            / "tools/labutopia_fluid/attest_experimental_fluid_runtime.py"
        ),
        "--lane",
        lane,
        "--output",
        str(output),
    ]
    process = _run_logged(
        command,
        environment=_child_environment(
            python.parents[1],
            scope / "runtime",
            isaac=lane.startswith("isaac"),
        ),
        log_dir=scope / "logs",
        timeout_s=timeout_s,
    )
    if process["exit_code"] != 0 or not output.is_file():
        raise RuntimeError(f"attestation_failed:{lane}:{process}")
    return {
        "process": process,
        "receipt": _load_json(output),
        "receipt_path": str(output),
        "receipt_sha256": _sha256_file(output),
    }


def _run_newton_profile(
    profile: str,
    *,
    run_root: Path,
    observation_count: int,
    visual_liquid_passed: bool,
    timeout_s: float,
) -> dict[str, Any]:
    scope = run_root / "physics_only" / profile
    output = scope / "artifacts"
    command = [
        str(NEWTON_PYTHON),
        str(
            REPO_ROOT
            / "tools/labutopia_fluid/run_newton140_mpm_benchmark.py"
        ),
        "--packet",
        str(PACKET),
        "--output-dir",
        str(output),
        "--profile",
        profile,
        "--max-observations",
        str(observation_count),
    ]
    if visual_liquid_passed:
        command.append("--visual-liquid-passed")
    process = _run_logged(
        command,
        environment=_child_environment(
            NEWTON_PYTHON.parents[1],
            scope / "runtime",
            isaac=False,
        ),
        log_dir=scope / "logs",
        timeout_s=timeout_s,
    )
    result_path = output / "result.json"
    return {
        "profile": profile,
        "display_mode": "headless_physics_only",
        "headless": True,
        "process": process,
        "result": _load_json(result_path) if result_path.is_file() else None,
    }


def _wait_for_path(path: Path, process: subprocess.Popen[bytes], timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.is_file():
            return
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"renderer_exited_before_ready:exit_code={return_code}"
            )
        time.sleep(0.05)
    raise TimeoutError(f"renderer_ready_timeout:{path}")


def _run_rendered_profile(
    profile: str,
    *,
    run_root: Path,
    observation_count: int,
    visual_liquid_passed: bool,
    timeout_s: float,
) -> dict[str, Any]:
    from tools.labutopia_fluid.fluid_benchmark_bridge import SharedFluidFrame

    scope = run_root / "rendered" / profile
    renderer_output = scope / "isaac_artifacts"
    newton_output = scope / "newton_artifacts"
    socket_path = scope / "runtime" / "fluid.sock"
    ready_path = renderer_output / "bridge_ready.json"
    scope.mkdir(parents=True, exist_ok=True)
    memory = SharedFluidFrame.create()
    renderer_stdout_path = scope / "isaac_stdout.log"
    renderer_stderr_path = scope / "isaac_stderr.log"
    renderer_environment = _child_environment(
        ISAAC_PYTHON.parents[1],
        scope / "isaac_runtime",
        isaac=True,
    )
    renderer_command = [
        str(ISAAC_PYTHON),
        str(
            REPO_ROOT
            / "tools/labutopia_fluid/run_isaac601_newton_render_bridge.py"
        ),
        "--packet",
        str(PACKET),
        "--output-dir",
        str(renderer_output),
        "--bridge-socket",
        str(socket_path),
        "--shared-memory-name",
        memory.name,
    ]
    renderer_started = time.time()
    renderer_stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        renderer_stdout_path.open("wb") as renderer_stdout,
        renderer_stderr_path.open("wb") as renderer_stderr,
    ):
        renderer = subprocess.Popen(
            renderer_command,
            cwd=REPO_ROOT,
            env=renderer_environment,
            stdout=renderer_stdout,
            stderr=renderer_stderr,
        )
        try:
            _wait_for_path(ready_path, renderer, min(timeout_s, 300.0))
            newton_command = [
                str(NEWTON_PYTHON),
                str(
                    REPO_ROOT
                    / "tools/labutopia_fluid/run_newton140_mpm_benchmark.py"
                ),
                "--packet",
                str(PACKET),
                "--output-dir",
                str(newton_output),
                "--profile",
                profile,
                "--max-observations",
                str(observation_count),
                "--bridge-socket",
                str(socket_path),
                "--shared-memory-name",
                memory.name,
            ]
            if visual_liquid_passed:
                newton_command.append("--visual-liquid-passed")
            newton_process = _run_logged(
                newton_command,
                environment=_child_environment(
                    NEWTON_PYTHON.parents[1],
                    scope / "newton_runtime",
                    isaac=False,
                ),
                log_dir=scope / "newton_logs",
                timeout_s=timeout_s,
            )
            remaining_timeout = max(
                1.0,
                timeout_s - (time.time() - renderer_started),
            )
            renderer_exit_code = renderer.wait(timeout=remaining_timeout)
        except BaseException:
            renderer.terminate()
            try:
                renderer.wait(timeout=30.0)
            except subprocess.TimeoutExpired:
                renderer.kill()
                renderer.wait()
            raise
        finally:
            memory.close()
            memory.unlink()

    renderer_process = {
        "command": renderer_command,
        "environment_sha256": _canonical_sha256(renderer_environment),
        "started_unix_s": renderer_started,
        "finished_unix_s": time.time(),
        "exit_code": renderer_exit_code,
        "stdout": {
            "path": str(renderer_stdout_path),
            "sha256": _sha256_file(renderer_stdout_path),
        },
        "stderr": {
            "path": str(renderer_stderr_path),
            "sha256": _sha256_file(renderer_stderr_path),
        },
    }
    isaac_result_path = renderer_output / "result.json"
    newton_result_path = newton_output / "result.json"
    return {
        "profile": profile,
        "display_mode": "headless_rtx_2x256_surface_reconstruction",
        "headless": True,
        "newton_process": newton_process,
        "isaac_process": renderer_process,
        "newton_result": (
            _load_json(newton_result_path)
            if newton_result_path.is_file()
            else None
        ),
        "isaac_result": (
            _load_json(isaac_result_path)
            if isaac_result_path.is_file()
            else None
        ),
    }


def _candidate_rank(record: dict[str, Any]) -> tuple[int, float, float]:
    result = record.get("result") or {}
    quality = result.get("quality") or {}
    final = quality.get("final_score") or {}
    timing = result.get("timing") or {}
    physics_fps = float(timing.get("physics_fps") or 0.0)
    return (
        int(bool(quality.get("passed"))),
        float(final.get("target_fraction") or 0.0),
        physics_fps,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=PROFILES,
        default=list(DEFAULT_PROFILES),
    )
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--physics-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rendered", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-busy-gpu", action="store_true")
    parser.add_argument("--skip-attestation", action="store_true")
    parser.add_argument(
        "--visual-liquid-passed",
        action="store_true",
        help="Bind a completed local visual review; review remains non-independent.",
    )
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run one profile for two observations and label it non-performance.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke:
        args.profiles = [args.profiles[0]]
        args.max_observations = min(args.max_observations, 2)
        args.allow_busy_gpu = True
    run_id = args.run_id or dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = (args.output_root / run_id).resolve()
    if run_root.exists():
        raise FileExistsError(f"run_root_exists:{run_root}")
    run_root.mkdir(parents=True)

    gpu_before = _gpu_snapshot()
    _atomic_json(run_root / "gpu_preflight.json", gpu_before)
    if not gpu_before["exclusive"] and not args.allow_busy_gpu:
        blocked = {
            "schema": "labutopia.fluid_benchmark_matrix.v1",
            "status": "blocked_runtime",
            "reason": "gpu_not_exclusive",
            "run_id": run_id,
            "run_root": str(run_root),
            "gpu_preflight": gpu_before,
        }
        _atomic_json(run_root / "matrix.json", blocked)
        print(json.dumps(blocked, sort_keys=True))
        return 2

    packet_record = _ensure_packet(run_root, args.timeout_s)
    attestations = {}
    if not args.skip_attestation:
        attestations["newton140"] = _attest(
            "newton140",
            NEWTON_PYTHON,
            run_root,
            args.timeout_s,
        )
        if args.rendered:
            attestations["isaacsim601"] = _attest(
                "isaacsim601",
                ISAAC_PYTHON,
                run_root,
                args.timeout_s,
            )

    physics_records = []
    if args.physics_only:
        for profile in args.profiles:
            physics_records.append(
                _run_newton_profile(
                    profile,
                    run_root=run_root,
                    observation_count=args.max_observations,
                    visual_liquid_passed=args.visual_liquid_passed,
                    timeout_s=args.timeout_s,
                )
            )

    rendered_record = None
    selected_profile = None
    successful_physics_records = [
        record
        for record in physics_records
        if record["process"]["exit_code"] == 0 and record.get("result") is not None
    ]
    if successful_physics_records:
        selected = max(successful_physics_records, key=_candidate_rank)
        selected_profile = selected["profile"]
    elif not args.physics_only and args.profiles:
        selected_profile = args.profiles[0]
    if args.rendered and selected_profile is not None:
        rendered_record = _run_rendered_profile(
            selected_profile,
            run_root=run_root,
            observation_count=args.max_observations,
            visual_liquid_passed=args.visual_liquid_passed,
            timeout_s=args.timeout_s,
        )

    gpu_after = _gpu_snapshot()
    performance_valid = (
        gpu_before["exclusive"]
        and gpu_after["exclusive"]
        and not args.smoke
        and args.max_observations == 953
    )
    requested_processes_passed = (
        len(successful_physics_records) == len(physics_records)
        and (
            not args.rendered
            or (
                rendered_record is not None
                and rendered_record["newton_process"]["exit_code"] == 0
                and rendered_record["isaac_process"]["exit_code"] == 0
                and rendered_record.get("newton_result") is not None
                and rendered_record.get("isaac_result") is not None
            )
        )
    )
    comparison_rows = [dict(record) for record in HISTORICAL_BASELINES]
    for record in physics_records:
        result = record.get("result") or {}
        timing = result.get("timing") or {}
        quality = result.get("quality") or {}
        final_score = quality.get("final_score") or {}
        rendered_fps = None
        if rendered_record is not None and record["profile"] == selected_profile:
            rendered_newton = rendered_record.get("newton_result") or {}
            rendered_fps = (
                (rendered_newton.get("timing") or {}).get("artifact_ready_fps")
            )
        comparison_rows.append(
            {
                "name": f"newton140_{record['profile']}",
                "runtime": "Newton 1.4 MPM + Isaac Sim 6.0.1 render lane",
                "solver": record["profile"],
                "particle_count": 3600,
                "sample": f"{args.max_observations} observations",
                "headless": True,
                "physics_only_fps": timing.get("physics_fps"),
                "rendered_2x256_fps": rendered_fps,
                "reconstruction": rendered_fps is not None,
                "target_fraction": final_score.get("target_fraction"),
                "below_table": final_score.get("below_table"),
                "tabletop_spill_fraction": final_score.get(
                    "tabletop_spill_fraction"
                ),
                "comparability": (
                    "experimental_solver_specific_controller_retarget;"
                    "not_formal_isaac41_comparable"
                ),
            }
        )
    matrix = {
        "schema": "labutopia.fluid_benchmark_matrix.v1",
        "status": "completed" if requested_processes_passed else "failed_runtime",
        "claim_boundary": (
            "experimental_cross_runtime_matrix;"
            "not_formal_isaac41_evidence;"
            "historical_rows_non_comparable;"
            + (
                "performance_valid"
                if performance_valid
                else "smoke_or_busy_gpu_not_performance_evidence"
            )
        ),
        "run_id": run_id,
        "run_root": str(run_root),
        "source": _source_record(),
        "headless_columns": [
            "physics_only_fps",
            "rendered_2x256_fps",
        ],
        "particle_count": 3600,
        "observation_count": args.max_observations,
        "substeps_per_observation": 4,
        "integration_dt_s": 1.0 / 120.0,
        "performance_valid": performance_valid,
        "gpu_preflight": gpu_before,
        "gpu_postflight": gpu_after,
        "packet": packet_record,
        "attestations": attestations,
        "environment_locks": {
            "newton140": _environment_lock_record("newton140"),
            "isaacsim601": _environment_lock_record("isaacsim601"),
        },
        "historical_baselines": HISTORICAL_BASELINES,
        "comparison_rows": comparison_rows,
        "newton_physics_only": physics_records,
        "selected_profile": selected_profile,
        "selected_profile_quality_passed": (
            bool(
                ((max(successful_physics_records, key=_candidate_rank).get("result") or {}).get("quality") or {}).get(
                    "passed"
                )
            )
            if successful_physics_records
            else False
        ),
        "rendered_lane": _rendered_lane_record(args.rendered),
        "rendered": rendered_record,
    }
    matrix["content_sha256"] = _canonical_sha256(matrix)
    matrix_path = run_root / "matrix.json"
    _atomic_json(matrix_path, matrix)
    print(
        json.dumps(
            {
                "status": matrix["status"],
                "matrix_path": str(matrix_path),
                "performance_valid": performance_valid,
                "selected_profile": selected_profile,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

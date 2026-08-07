#!/usr/bin/env python3
"""Run the matched Isaac 4.1 PBD versus Newton 1.4 fluid A/B matrix."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

NEWTON_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-newton140-mpm-py312/bin/python"
)
PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
OUTPUT_ROOT = REPO_ROOT / "outputs/fluid_benchmark_isaac41_newton140/runs"
NEWTON_LOCK = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/environment_locks/newton140"
    / "environment-lock.json"
)
LANES = (
    "pbd_exact_physics",
    "newton_exact_physics",
    "pbd_exact_rendered",
    "newton_exact_rendered",
    "newton_retarget_physics",
    "newton_retarget_rendered",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _gpu_snapshot() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,driver_version,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    gpu = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process_command = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ]
    processes = subprocess.run(process_command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    parsed = None
    lines = gpu.stdout.strip().splitlines()
    if gpu.returncode == 0 and lines:
        parts = [part.strip() for part in lines[0].split(",")]
        if len(parts) >= 9:
            parsed = {
                "index": int(parts[0]),
                "uuid": parts[1],
                "name": parts[2],
                "driver_version": parts[3],
                "utilization_gpu_percent": float(parts[4]),
                "memory_used_mib": float(parts[5]),
                "memory_total_mib": float(parts[6]),
                "temperature_c": float(parts[7]),
                "power_w": float(parts[8]),
            }
    return {
        "captured_unix_s": time.time(),
        "gpu_command": command,
        "gpu_exit_code": gpu.returncode,
        "gpu_stdout": lines,
        "gpu_stderr": gpu.stderr.strip(),
        "gpu": parsed,
        "process_command": process_command,
        "process_exit_code": processes.returncode,
        "compute_processes": processes.stdout.strip().splitlines(),
        "process_stderr": processes.stderr.strip(),
    }


def _snapshot_idle(snapshot: dict[str, Any], args: argparse.Namespace) -> bool:
    gpu = snapshot.get("gpu")
    return bool(
        isinstance(gpu, dict)
        and snapshot.get("gpu_exit_code") == 0
        and snapshot.get("process_exit_code") == 0
        and not snapshot.get("compute_processes")
        and float(gpu["utilization_gpu_percent"]) <= args.max_idle_utilization
        and float(gpu["memory_used_mib"]) <= args.max_idle_memory_mib
    )


def _process_is_descendant(pid: int, ancestor_pid: int) -> bool:
    current = pid
    visited: set[int] = set()
    while current > 1 and current not in visited:
        if current == ancestor_pid:
            return True
        visited.add(current)
        try:
            stat = (Path("/proc") / str(current) / "stat").read_text(encoding="utf-8")
            suffix = stat[stat.rfind(")") + 1 :].split()
            current = int(suffix[1])
        except (FileNotFoundError, IndexError, ValueError):
            return False
    return current == ancestor_pid


def _monitor_lane_activity(
    args: argparse.Namespace,
    *,
    evidence_path: Path,
    stop: threading.Event,
) -> None:
    samples: list[dict[str, Any]] = []
    known_lane_pids: set[int] = set()
    orchestrator_pid = os.getpid()
    sample_log = evidence_path.with_suffix(".samples.jsonl")
    sample_log.parent.mkdir(parents=True, exist_ok=True)
    while True:
        snapshot = _gpu_snapshot()
        external_lines: list[str] = []
        lane_lines: list[str] = []
        for line in snapshot.get("compute_processes", []):
            try:
                pid = int(line.split(",", 1)[0].strip())
            except ValueError:
                external_lines.append(line)
                continue
            if pid in known_lane_pids or _process_is_descendant(pid, orchestrator_pid):
                known_lane_pids.add(pid)
                lane_lines.append(line)
            else:
                external_lines.append(line)
        snapshot["lane_compute_processes"] = lane_lines
        snapshot["external_compute_processes"] = external_lines
        samples.append(snapshot)
        with sample_log.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
                + "\n"
            )
        if stop.wait(args.lane_monitor_interval_s):
            break
    evidence = {
        "schema": "labutopia.gpu_lane_activity.v1",
        "orchestrator_pid": orchestrator_pid,
        "sample_interval_s": args.lane_monitor_interval_s,
        "sample_count": len(samples),
        "known_lane_pids": sorted(known_lane_pids),
        "external_process_seen": any(
            bool(sample["external_compute_processes"]) for sample in samples
        ),
        "sample_log": str(sample_log),
        "sample_log_sha256": _sha256_file(sample_log),
        "samples": samples,
    }
    _atomic_json(evidence_path, evidence)


def _wait_for_idle(
    args: argparse.Namespace,
    *,
    evidence_path: Path,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    consecutive = 0
    samples: list[dict[str, Any]] = []
    sample_log = evidence_path.with_suffix(".samples.jsonl")
    sample_log.parent.mkdir(parents=True, exist_ok=True)
    while True:
        snapshot = _gpu_snapshot()
        idle = _snapshot_idle(snapshot, args)
        snapshot["idle"] = idle
        samples.append(snapshot)
        with sample_log.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
                + "\n"
            )
        consecutive = consecutive + 1 if idle else 0
        elapsed = time.monotonic() - started
        status = (
            "idle"
            if consecutive >= args.idle_samples
            else "timeout"
            if elapsed >= timeout_s
            else "waiting"
        )
        evidence = {
            "schema": "labutopia.gpu_idle_wait.v1",
            "status": status,
            "required_consecutive_samples": args.idle_samples,
            "sample_interval_s": args.idle_interval_s,
            "maximum_utilization_percent": args.max_idle_utilization,
            "maximum_memory_used_mib": args.max_idle_memory_mib,
            "consecutive_idle_samples": consecutive,
            "sample_count": len(samples),
            "sample_log": str(sample_log),
            "last_sample": snapshot,
        }
        if status != "waiting":
            evidence["samples"] = samples
            evidence["sample_log_sha256"] = _sha256_file(sample_log)
        _atomic_json(evidence_path, evidence)
        if status != "waiting":
            return evidence
        time.sleep(min(args.idle_interval_s, max(0.0, timeout_s - elapsed)))


def _newton_environment(scope: Path) -> dict[str, str]:
    short = hashlib.sha256(str(scope).encode("utf-8")).hexdigest()[:12]
    directories = {
        "HOME": scope / "home",
        "TMPDIR": Path("/tmp") / f"lbn_{short}",
        "XDG_CACHE_HOME": scope / "xdg-cache",
        "XDG_CONFIG_HOME": scope / "xdg-config",
        "XDG_DATA_HOME": scope / "xdg-data",
    }
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=True)
    return {
        **{name: str(path) for name, path in directories.items()},
        "PATH": f"{NEWTON_PYTHON.parents[1] / 'bin'}:/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CUDA_VISIBLE_DEVICES": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _run_logged(
    command: list[str],
    *,
    environment: dict[str, str] | None,
    log_dir: Path,
    timeout_s: float,
) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
    started = time.time()
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
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
        "environment_sha256": (
            _canonical_sha256(environment) if environment is not None else None
        ),
        "started_unix_s": started,
        "finished_unix_s": time.time(),
        "exit_code": completed.returncode,
        "stdout": {"path": str(stdout_path), "sha256": _sha256_file(stdout_path)},
        "stderr": {"path": str(stderr_path), "sha256": _sha256_file(stderr_path)},
    }


def _run_pbd(lane: str, args: argparse.Namespace, run_root: Path) -> dict[str, Any]:
    mode = "rendered" if lane.endswith("rendered") else "physics-only"
    scope = run_root / lane
    command = [
        "/usr/bin/python3",
        str(REPO_ROOT / "tools/labutopia_fluid/run_isaac41_pbd_benchmark.py"),
        "--mode", mode,
        "--packet", str(PACKET),
        "--output-dir", str(scope / "artifacts"),
        "--evidence-dir", str(scope / "runtime_evidence"),
        "--max-observations", str(args.max_observations),
    ]
    process = _run_logged(command, environment=None, log_dir=scope / "logs", timeout_s=args.lane_timeout_s)
    result_path = scope / "artifacts/result.json"
    return {
        "lane": lane,
        "display_mode": mode,
        "process": process,
        "result": _load_json(result_path) if result_path.is_file() else None,
    }


def _newton_command(
    args: argparse.Namespace,
    *,
    output: Path,
    retarget: bool,
    bridge_socket: Path | None = None,
    shared_memory_name: str | None = None,
) -> list[str]:
    command = [
        str(NEWTON_PYTHON),
        str(REPO_ROOT / "tools/labutopia_fluid/run_newton140_mpm_benchmark.py"),
        "--packet", str(PACKET),
        "--output-dir", str(output),
        "--profile", "sparse_q1_gs_fast",
        "--max-observations", str(args.max_observations),
        "--pour-retarget" if retarget else "--no-pour-retarget",
        "--debug-substeps", str(args.newton_substeps),
        "--debug-integration-dt", str(args.newton_integration_dt),
        "--timing-warmup-observations", str(args.timing_warmup_observations),
    ]
    command[command.index("sparse_q1_gs_fast")] = args.newton_profile
    for option, value in (
        ("--max-iterations", args.newton_max_iterations),
        ("--tolerance", args.newton_tolerance),
        ("--solver", args.newton_solver),
        ("--grid-type", args.newton_grid_type),
        ("--grid-padding", args.newton_grid_padding),
        ("--warmstart-mode", args.newton_warmstart_mode),
    ):
        if value is not None:
            command.extend([option, str(value)])
    if args.newton_graph is not None:
        command.append("--graph" if args.newton_graph else "--no-graph")
    if args.solver_diagnostics:
        command.append("--solver-diagnostics")
    if args.timing_breakdown:
        command.append("--timing-breakdown")
    if bridge_socket is not None and shared_memory_name is not None:
        command.extend(["--bridge-socket", str(bridge_socket), "--shared-memory-name", shared_memory_name])
    return command


def _run_newton_physics(lane: str, args: argparse.Namespace, run_root: Path) -> dict[str, Any]:
    scope = run_root / lane
    retarget = "retarget" in lane
    command = _newton_command(args, output=scope / "artifacts", retarget=retarget)
    process = _run_logged(
        command,
        environment=_newton_environment(scope / "runtime"),
        log_dir=scope / "logs",
        timeout_s=args.lane_timeout_s,
    )
    result_path = scope / "artifacts/result.json"
    return {
        "lane": lane,
        "display_mode": "physics-only",
        "process": process,
        "result": _load_json(result_path) if result_path.is_file() else None,
    }


def _wait_for_path(path: Path, process: subprocess.Popen[bytes], timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.is_file():
            return
        if process.poll() is not None:
            raise RuntimeError(f"renderer_exited_before_ready:{process.returncode}")
        time.sleep(0.1)
    raise TimeoutError(f"renderer_ready_timeout:{path}")


def _run_newton_rendered(lane: str, args: argparse.Namespace, run_root: Path) -> dict[str, Any]:
    from tools.labutopia_fluid.fluid_benchmark_bridge import SharedFluidFrame

    scope = run_root / lane
    scope.mkdir(parents=True, exist_ok=True)
    retarget = "retarget" in lane
    short = hashlib.sha256(str(scope).encode("utf-8")).hexdigest()[:12]
    socket_path = Path("/tmp") / f"lb41_{short}.sock"
    if socket_path.exists():
        socket_path.unlink()
    memory = SharedFluidFrame.create()
    renderer_command = [
        "/usr/bin/python3",
        str(REPO_ROOT / "tools/labutopia_fluid/run_isaac41_newton_render_bridge.py"),
        "--packet", str(PACKET),
        "--output-dir", str(scope / "isaac_artifacts"),
        "--evidence-dir", str(scope / "isaac_runtime_evidence"),
        "--bridge-socket", str(socket_path),
        "--shared-memory-name", memory.name,
        "--pour-retarget" if retarget else "--no-pour-retarget",
        "--camera-count", str(args.render_camera_count),
        "--surface-mode", args.render_surface_mode,
    ]
    renderer_stdout_path = scope / "isaac_stdout.log"
    renderer_stderr_path = scope / "isaac_stderr.log"
    renderer_started = time.time()
    newton_process = None
    renderer_returncode = None
    shared_memory_cleanup = {"status": "pending", "name": memory.name}
    with renderer_stdout_path.open("xb") as stdout, renderer_stderr_path.open("xb") as stderr:
        renderer = subprocess.Popen(
            renderer_command,
            cwd=REPO_ROOT,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            _wait_for_path(scope / "isaac_artifacts/bridge_ready.json", renderer, min(300.0, args.lane_timeout_s))
            newton_command = _newton_command(
                args,
                output=scope / "newton_artifacts",
                retarget=retarget,
                bridge_socket=socket_path,
                shared_memory_name=memory.name,
            )
            newton_process = _run_logged(
                newton_command,
                environment=_newton_environment(scope / "newton_runtime"),
                log_dir=scope / "newton_logs",
                timeout_s=args.lane_timeout_s,
            )
            renderer_returncode = renderer.wait(timeout=args.lane_timeout_s)
        except BaseException:
            try:
                os.killpg(renderer.pid, signal.SIGTERM)
                renderer.wait(timeout=30.0)
            except Exception:
                try:
                    os.killpg(renderer.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                renderer.wait()
            raise
        finally:
            memory.close()
            try:
                memory.unlink()
                shared_memory_cleanup["status"] = "unlinked_by_owner"
            except FileNotFoundError:
                shared_memory_cleanup["status"] = "prematurely_unlinked_by_attachment"
            if socket_path.exists():
                socket_path.unlink()
    renderer_process = {
        "command": renderer_command,
        "started_unix_s": renderer_started,
        "finished_unix_s": time.time(),
        "exit_code": renderer_returncode,
        "stdout": {"path": str(renderer_stdout_path), "sha256": _sha256_file(renderer_stdout_path)},
        "stderr": {"path": str(renderer_stderr_path), "sha256": _sha256_file(renderer_stderr_path)},
    }
    newton_result_path = scope / "newton_artifacts/result.json"
    isaac_result_path = scope / "isaac_artifacts/result.json"
    return {
        "lane": lane,
        "display_mode": "rendered",
        "newton_process": newton_process,
        "isaac_process": renderer_process,
        "shared_memory_cleanup": shared_memory_cleanup,
        "newton_result": _load_json(newton_result_path) if newton_result_path.is_file() else None,
        "isaac_result": _load_json(isaac_result_path) if isaac_result_path.is_file() else None,
    }


def _lane_passed(record: dict[str, Any]) -> bool:
    if record["display_mode"] == "rendered" and record["lane"].startswith("newton"):
        return bool(
            record.get("newton_process", {}).get("exit_code") == 0
            and record.get("isaac_process", {}).get("exit_code") == 0
            and record.get("newton_result") is not None
            and record.get("isaac_result") is not None
            and record.get("shared_memory_cleanup", {}).get("status")
            == "unlinked_by_owner"
        )
    return bool(record.get("process", {}).get("exit_code") == 0 and record.get("result") is not None)


def _fps(record: dict[str, Any]) -> float | None:
    lane = record["lane"]
    if lane.startswith("pbd"):
        result = record.get("result") or {}
        timing = result.get("timing") or {}
        return timing.get("model_ready_fps" if lane.endswith("rendered") else "physics_only_fps")
    result = record.get("newton_result") if lane.endswith("rendered") else record.get("result")
    timing = (result or {}).get("timing") or {}
    return timing.get("artifact_ready_fps" if lane.endswith("rendered") else "physics_fps")


def _quality(record: dict[str, Any]) -> dict[str, Any] | None:
    lane = record["lane"]
    if lane.startswith("pbd"):
        result = record.get("result")
    elif lane.endswith("rendered"):
        result = record.get("newton_result")
    else:
        result = record.get("result")
    quality = (result or {}).get("quality")
    return quality if isinstance(quality, dict) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--lanes", nargs="+", choices=LANES, default=list(LANES))
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--wait-hours", type=float, default=12.0)
    parser.add_argument("--idle-samples", type=int, default=6)
    parser.add_argument("--idle-interval-s", type=float, default=10.0)
    parser.add_argument("--max-idle-utilization", type=float, default=2.0)
    parser.add_argument("--max-idle-memory-mib", type=float, default=128.0)
    parser.add_argument("--lane-timeout-s", type=float, default=7200.0)
    parser.add_argument("--postflight-wait-s", type=float)
    parser.add_argument("--lane-monitor-interval-s", type=float, default=1.0)
    parser.add_argument("--newton-profile", default="sparse_q1_gs_fast")
    parser.add_argument("--newton-max-iterations", type=int)
    parser.add_argument("--newton-tolerance", type=float)
    parser.add_argument("--newton-solver")
    parser.add_argument("--newton-grid-type", choices=("sparse", "dense", "fixed"))
    parser.add_argument("--newton-grid-padding", type=int)
    parser.add_argument(
        "--newton-warmstart-mode",
        choices=("none", "auto", "particles", "grid", "smoothed"),
    )
    parser.add_argument(
        "--newton-graph",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--newton-substeps", type=int, default=4)
    parser.add_argument("--newton-integration-dt", type=float, default=1.0 / 120.0)
    parser.add_argument("--timing-warmup-observations", type=int, default=1)
    parser.add_argument("--solver-diagnostics", action="store_true")
    parser.add_argument("--timing-breakdown", action="store_true")
    parser.add_argument("--render-camera-count", type=int, choices=(1, 2), default=2)
    parser.add_argument(
        "--render-surface-mode",
        choices=("dynamic", "static-first", "particles"),
        default="dynamic",
    )
    parser.add_argument("--smoke", action="store_true")
    return parser


def _source_provenance() -> dict[str, Any]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    source_paths = [
        Path(__file__).resolve(),
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_contract.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac41_pbd_benchmark.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac41_newton_render_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac601_newton_render_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/run_newton140_mpm_benchmark.py",
        REPO_ROOT / "tools/labutopia_fluid/run_newton140_mpm_solver_sweep.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac41_newton_render_ablation.py",
    ]
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "revision_exit_code": revision.returncode,
        "dirty": bool(status.stdout),
        "status_sha256": hashlib.sha256(status.stdout.encode("utf-8")).hexdigest(),
        "files": [
            {"path": str(path), "sha256": _sha256_file(path)}
            for path in source_paths
        ],
    }


def _attest_newton(args: argparse.Namespace, run_root: Path) -> dict[str, Any]:
    scope = run_root / "newton_attestation"
    receipt_path = scope / "receipt.json"
    command = [
        str(NEWTON_PYTHON),
        str(REPO_ROOT / "tools/labutopia_fluid/attest_experimental_fluid_runtime.py"),
        "--lane",
        "newton140",
        "--output",
        str(receipt_path),
    ]
    process = _run_logged(
        command,
        environment=_newton_environment(scope / "runtime"),
        log_dir=scope / "logs",
        timeout_s=min(args.lane_timeout_s, 600.0),
    )
    receipt = _load_json(receipt_path) if receipt_path.is_file() else None
    return {
        "process": process,
        "receipt": receipt,
        "passed": bool(
            process["exit_code"] == 0
            and receipt is not None
            and receipt.get("status") == "passed"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke:
        args.max_observations = min(args.max_observations, 2)
        args.idle_samples = 1
        args.wait_hours = 0.0
    if args.max_observations <= 0 or args.max_observations > 953:
        raise ValueError("max_observations_out_of_range")
    if args.postflight_wait_s is not None and args.postflight_wait_s < 0:
        raise ValueError("postflight_wait_s_negative")
    if args.lane_monitor_interval_s <= 0:
        raise ValueError("lane_monitor_interval_s_not_positive")
    run_id = args.run_id or dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = (args.output_root / run_id).resolve()
    if run_root.exists():
        raise FileExistsError(f"run_root_exists:{run_root}")
    run_root.mkdir(parents=True)

    source_provenance = _source_provenance()
    if args.smoke:
        idle_record = {"status": "bypassed_smoke", "snapshot": _gpu_snapshot()}
    else:
        idle_record = _wait_for_idle(
            args,
            evidence_path=run_root / "gpu_idle_wait.json",
            timeout_s=args.wait_hours * 3600.0,
        )
    if idle_record["status"] == "timeout":
        matrix = {
            "schema": "labutopia.isaac41_newton140_matched_matrix.v1",
            "status": "blocked_gpu_busy",
            "run_id": run_id,
            "source_provenance": source_provenance,
            "gpu_idle_wait": idle_record,
        }
        matrix["content_sha256"] = _canonical_sha256(matrix)
        _atomic_json(run_root / "matrix.json", matrix)
        print(json.dumps({"status": matrix["status"], "matrix": str(run_root / "matrix.json")}, sort_keys=True))
        return 2

    newton_attestation = _attest_newton(args, run_root)
    if not newton_attestation["passed"]:
        matrix = {
            "schema": "labutopia.isaac41_newton140_matched_matrix.v1",
            "status": "blocked_newton_runtime_attestation",
            "run_id": run_id,
            "source_provenance": source_provenance,
            "newton_attestation": newton_attestation,
            "gpu_idle_wait": idle_record,
        }
        matrix["content_sha256"] = _canonical_sha256(matrix)
        _atomic_json(run_root / "matrix.json", matrix)
        print(json.dumps({"status": matrix["status"], "matrix": str(run_root / "matrix.json")}, sort_keys=True))
        return 2

    lane_records: list[dict[str, Any]] = []
    lane_gpu_records: list[dict[str, Any]] = []
    for lane in args.lanes:
        if not args.smoke:
            lane_idle = _wait_for_idle(
                args,
                evidence_path=run_root / lane / "gpu_idle_preflight.json",
                timeout_s=args.wait_hours * 3600.0,
            )
            if lane_idle["status"] != "idle":
                break
        before = _gpu_snapshot()
        activity_path = run_root / lane / "gpu_lane_activity.json"
        activity_stop = threading.Event()
        activity_thread = threading.Thread(
            target=_monitor_lane_activity,
            args=(args,),
            kwargs={"evidence_path": activity_path, "stop": activity_stop},
            name=f"gpu-activity-{lane}",
        )
        activity_thread.start()
        try:
            if lane.startswith("pbd"):
                record = _run_pbd(lane, args, run_root)
            elif lane.endswith("physics"):
                record = _run_newton_physics(lane, args, run_root)
            else:
                record = _run_newton_rendered(lane, args, run_root)
        finally:
            activity_stop.set()
            activity_thread.join()
        activity = _load_json(activity_path)
        after = _gpu_snapshot()
        if args.smoke:
            post_idle = {"status": "bypassed_smoke", "snapshot": after}
        else:
            post_idle = _wait_for_idle(
                args,
                evidence_path=run_root / lane / "gpu_idle_postflight.json",
                timeout_s=(
                    args.postflight_wait_s
                    if args.postflight_wait_s is not None
                    else args.wait_hours * 3600.0
                ),
            )
        lane_gpu_records.append(
            {
                "lane": lane,
                "before": before,
                "activity": activity,
                "after": after,
                "post_idle": post_idle,
            }
        )
        lane_records.append(record)
        if not _lane_passed(record) or post_idle["status"] not in {"idle", "bypassed_smoke"}:
            break

    records_by_lane = {record["lane"]: record for record in lane_records}
    quality_by_lane = {
        lane: _quality(record) for lane, record in records_by_lane.items()
    }
    all_requested_completed = len(lane_records) == len(args.lanes) and all(_lane_passed(record) for record in lane_records)
    performance_valid = bool(
        not args.smoke
        and args.max_observations == 953
        and all_requested_completed
        and all(_snapshot_idle(item["before"], args) for item in lane_gpu_records)
        and all(not item["activity"]["external_process_seen"] for item in lane_gpu_records)
        and all(item["post_idle"]["status"] == "idle" for item in lane_gpu_records)
        and args.newton_substeps == 4
        and abs(args.newton_integration_dt - 1.0 / 120.0) <= 1.0e-15
        and not args.timing_breakdown
        and args.render_camera_count == 2
        and args.render_surface_mode == "dynamic"
    )
    physics_speedup = None
    rendered_speedup = None
    physics_exact_lanes = {"pbd_exact_physics", "newton_exact_physics"}
    rendered_exact_lanes = {"pbd_exact_rendered", "newton_exact_rendered"}
    exact_lanes = physics_exact_lanes | rendered_exact_lanes
    if performance_valid and physics_exact_lanes.issubset(records_by_lane):
        pbd_physics = _fps(records_by_lane["pbd_exact_physics"])
        newton_physics = _fps(records_by_lane["newton_exact_physics"])
        if pbd_physics and newton_physics:
            physics_speedup = newton_physics / pbd_physics
    if performance_valid and rendered_exact_lanes.issubset(records_by_lane):
        pbd_rendered = _fps(records_by_lane["pbd_exact_rendered"])
        newton_rendered = _fps(records_by_lane["newton_exact_rendered"])
        if pbd_rendered and newton_rendered:
            rendered_speedup = newton_rendered / pbd_rendered
    physics_exact_quality_eligible = bool(
        physics_exact_lanes.issubset(records_by_lane)
        and all(
            bool((quality_by_lane.get(lane) or {}).get("numeric_passed"))
            for lane in physics_exact_lanes
        )
    )
    rendered_exact_quality_eligible = bool(
        rendered_exact_lanes.issubset(records_by_lane)
        and all(
            bool((quality_by_lane.get(lane) or {}).get("numeric_passed"))
            for lane in rendered_exact_lanes
        )
    )
    exact_quality_eligible = bool(
        physics_exact_quality_eligible and rendered_exact_quality_eligible
    )
    postflight_failed = any(
        item["post_idle"]["status"] not in {"idle", "bypassed_smoke"}
        for item in lane_gpu_records
    )
    matrix = {
        "schema": "labutopia.isaac41_newton140_matched_matrix.v1",
        "status": (
            "completed"
            if all_requested_completed and not postflight_failed
            else "invalid_gpu_conditions"
            if postflight_failed
            else "failed_runtime"
        ),
        "claim_boundary": (
            "experimental_hybrid_newton140_with_formal_isaac41_renderer;"
            "exact_trace_rows_are_performance_ab;"
            "retarget_rows_are_quality_candidate_not_exact_trace"
        ),
        "run_id": run_id,
        "run_root": str(run_root),
        "source_provenance": source_provenance,
        "newton_attestation": newton_attestation,
        "newton_environment_lock": {
            "path": str(NEWTON_LOCK),
            "sha256": _sha256_file(NEWTON_LOCK),
        },
        "packet": {"path": str(PACKET), "sha256": _sha256_file(PACKET)},
        "particle_count": 3600,
        "observation_count": args.max_observations,
        "substeps_per_observation": args.newton_substeps,
        "integration_dt_s": args.newton_integration_dt,
        "newton_solver_controls": {
            "profile": args.newton_profile,
            "max_iterations": args.newton_max_iterations,
            "tolerance": args.newton_tolerance,
            "solver": args.newton_solver,
            "grid_type": args.newton_grid_type,
            "grid_padding": args.newton_grid_padding,
            "graph": args.newton_graph,
            "warmstart_mode": args.newton_warmstart_mode,
        },
        "render_ablation_controls": {
            "camera_count": args.render_camera_count,
            "surface_mode": args.render_surface_mode,
        },
        "headless_columns": ["physics_only_fps", "rendered_2x256_fps"],
        "performance_valid": performance_valid,
        "gpu_idle_wait": idle_record,
        "lane_gpu_records": lane_gpu_records,
        "lanes": lane_records,
        "fps": {lane: _fps(record) for lane, record in records_by_lane.items()},
        "quality": quality_by_lane,
        "strict_exact_trace_speedup": {
            "physics_only": physics_speedup,
            "rendered_2x256": rendered_speedup,
            "performance_valid": performance_valid,
            "quality_eligible": exact_quality_eligible,
            "physics_quality_eligible": physics_exact_quality_eligible,
            "rendered_quality_eligible": rendered_exact_quality_eligible,
            "promotion_eligible": performance_valid and exact_quality_eligible,
        },
        "isaac601_status": "blocked_runtime_driver_570_153_02",
    }
    matrix["content_sha256"] = _canonical_sha256(matrix)
    _atomic_json(run_root / "matrix.json", matrix)
    print(json.dumps({"status": matrix["status"], "performance_valid": performance_valid, "matrix": str(run_root / "matrix.json")}, sort_keys=True), flush=True)
    return 0 if all_requested_completed else 2


if __name__ == "__main__":
    raise SystemExit(main())

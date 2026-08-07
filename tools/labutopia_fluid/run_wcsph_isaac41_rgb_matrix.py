#!/usr/bin/env python3
"""Measure live WCSPH -> formal Isaac 4.1 dual-camera RGB throughput."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_bridge import (  # noqa: E402
    SharedFluidRenderFrame,
)
from tools.labutopia_fluid.fluid_benchmark_contract import (  # noqa: E402
    sha256_file,
    summarize_milliseconds,
)
from tools.labutopia_fluid.run_newton_only_solver_search import (  # noqa: E402
    gpu_snapshot,
    wait_for_idle_gpu,
)
from tools.labutopia_fluid.run_wcsph_scaling_matrix import (  # noqa: E402
    _gpu_process_classification,
    _sealed_environment,
    _short_runtime_root,
)


FORMAL_ISAAC41_PARENT_PYTHON = Path("/usr/bin/python3")
ISAAC601_PREFIX = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim601-fluid-py312"
)
ISAAC601_PYTHON = ISAAC601_PREFIX / "bin/python"
ISAAC601_LOCK = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/environment_locks/"
    "isaacsim601/environment-lock.json"
)
NEWTON_PREFIX = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-newton140-mpm-py312"
)
NEWTON_PYTHON = NEWTON_PREFIX / "bin/python"
NEWTON_LOCK = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/environment_locks/"
    "newton140/environment-lock.json"
)
PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2/"
    "fluid_benchmark_packet_v2.json"
)
SCENE = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_liquid_v1.usda"
)
TRAJECTORY = (
    REPO_ROOT
    / "outputs/wcsph_quality_repair/2026-08-04_trajectory_candidates_v4/"
    "candidate_04.npz"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "outputs/wcsph_quality_repair/2026-08-04_wcsph_isaac41_rgb_matrix_r1"
)
REPRESENTATIONS = ("particles", "surface_gpu")
RESOLUTIONS = {"256": (256, 256), "720": (1280, 720)}
REVIEW_INDICES = (0, 300, 450, 580, 650, 750, 852, 952)


def _renderer_for_profile(
    renderer_runtime: str, render_profile: str
) -> str:
    if renderer_runtime == "isaac41":
        return "RayTracedLighting"
    if render_profile in {"strict", "cuda_rgb"}:
        return "RealTimePathTracing"
    if render_profile == "minimal_textured":
        return "MinimalRendering"
    raise ValueError(f"unsupported_render_profile:{render_profile}")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _source_record() -> dict[str, Any]:
    paths = (
        Path(__file__).resolve(),
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/run_newton_only_fluid_benchmark.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac41_newton_render_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac601_newton_render_bridge.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac601_rtx_render_attested_child.py",
        REPO_ROOT / "tools/labutopia_fluid/run_isaac601_wcsph_rgb_same_process.py",
        REPO_ROOT / "tools/labutopia_fluid/warp_surface_reconstruction.py",
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {
        "revision": revision,
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "files": [{"path": str(path), "sha256": sha256_file(path)} for path in paths],
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


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=20.0)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=20.0)


def _particle_content_sha256(path: Path) -> str:
    with np.load(path, allow_pickle=False) as archive:
        indices = np.asarray(archive["observation_indices"], dtype="<i4")
        positions = np.asarray(archive["particle_positions"], dtype="<f4")
    digest = hashlib.sha256()
    digest.update(indices.tobytes(order="C"))
    digest.update(positions.tobytes(order="C"))
    return digest.hexdigest()


def _run_lane(
    *,
    args: argparse.Namespace,
    resolution_id: str,
    representation: str,
    repeat_index: int,
) -> dict[str, Any]:
    width, height = RESOLUTIONS[resolution_id]
    scope = (
        args.output_root
        / "runs"
        / resolution_id
        / representation
        / f"repeat_{repeat_index:02d}"
    )
    scope.mkdir(parents=True, exist_ok=False)
    renderer_output = scope / "isaac_artifacts"
    renderer_evidence = scope / "isaac_runtime_evidence"
    renderer_receipt = renderer_evidence / "runtime_receipt.json"
    renderer_failure = renderer_evidence / "child_failure.json"
    producer_output = scope / "newton_artifacts"
    producer_receipt = scope / "newton_runtime_receipt.json"
    producer_failure = scope / "newton_child_failure.json"
    short = hashlib.sha256(str(scope).encode("utf-8")).hexdigest()[:16]
    socket_path = Path("/tmp") / f"lbwr_{short}.sock"
    if socket_path.exists():
        raise FileExistsError(f"render_socket_exists:{socket_path}")
    memory = SharedFluidRenderFrame.create()
    renderer_mode = "particles" if representation == "particles" else "surface-shm"
    common_renderer_arguments = [
        "--packet",
        str(args.packet),
        "--scene",
        str(args.scene),
        "--output-dir",
        str(renderer_output),
        "--bridge-socket",
        str(socket_path),
        "--shared-memory-name",
        memory.name,
        "--bridge-payload",
        "render-v2",
        "--trajectory-npz",
        str(args.trajectory_npz),
        "--width",
        str(width),
        "--height",
        str(height),
        "--renderer",
        _renderer_for_profile(args.renderer_runtime, args.render_profile),
        "--rt-subframes",
        "1",
        "--camera-count",
        "2",
        "--surface-mode",
        renderer_mode,
        "--stage-warmup-updates",
        str(args.stage_warmup_updates),
        "--bridge-timeout-s",
        str(args.bridge_timeout_s),
        "--no-pour-retarget",
    ]
    if args.save_all_rgb:
        common_renderer_arguments.append("--save-all-rgb")
    if args.architecture == "same_process":
        renderer_command = [
            str(ISAAC601_PYTHON),
            "-I",
            "-B",
            str(
                REPO_ROOT
                / "tools/labutopia_fluid/run_isaac601_wcsph_rgb_same_process.py"
            ),
            "--lock-manifest",
            str(ISAAC601_LOCK),
            "--runtime-receipt",
            str(renderer_receipt),
            "--child-failure",
            str(renderer_failure),
            "--producer-output-dir",
            str(producer_output),
            "--max-observations",
            str(args.max_observations),
            "--warmup-observations",
            "2",
            "--render-profile",
            args.render_profile,
            *common_renderer_arguments,
        ]
        if args.allow_unvalidated_driver:
            renderer_command.append("--allow-unvalidated-driver")
        renderer_environment = _sealed_environment(
            ISAAC601_PREFIX,
            _short_runtime_root(scope / "isaac_runtime"),
            isaac=True,
        )
    elif args.renderer_runtime == "isaac41":
        renderer_command = [
            str(FORMAL_ISAAC41_PARENT_PYTHON),
            str(
                REPO_ROOT
                / "tools/labutopia_fluid/run_isaac41_newton_render_bridge.py"
            ),
            "--evidence-dir",
            str(renderer_evidence),
            *common_renderer_arguments,
        ]
        renderer_environment = None
    else:
        renderer_command = [
            str(ISAAC601_PYTHON),
            "-I",
            "-B",
            str(
                REPO_ROOT
                / "tools/labutopia_fluid/run_isaac601_rtx_render_attested_child.py"
            ),
            "--lock-manifest",
            str(ISAAC601_LOCK),
            "--runtime-receipt",
            str(renderer_receipt),
            "--child-failure",
            str(renderer_failure),
            "--render-profile",
            args.render_profile,
            *common_renderer_arguments,
        ]
        if args.allow_unvalidated_driver:
            renderer_command.append("--allow-unvalidated-driver")
        renderer_environment = _sealed_environment(
            ISAAC601_PREFIX,
            _short_runtime_root(scope / "isaac_runtime"),
            isaac=True,
        )
    parameters = {
        "boundary_kind": "boxes",
        "maximum_dt_s": 1.0 / 120.0,
        "profile_stages": False,
        "sound_speed_m_s": 4.0,
        "viscosity": 0.002,
    }
    producer_command = [
        str(NEWTON_PYTHON),
        "-I",
        "-B",
        str(REPO_ROOT / "tools/labutopia_fluid/run_newton140_wcsph_attested_child.py"),
        "--lock-manifest",
        str(NEWTON_LOCK),
        "--runtime-receipt",
        str(producer_receipt),
        "--child-failure",
        str(producer_failure),
        "--",
        "--solver-id",
        "labutopia_wcsph",
        "--packet",
        str(args.packet),
        "--output-dir",
        str(producer_output),
        "--particle-count",
        "3600",
        "--max-observations",
        str(args.max_observations),
        "--warmup-observations",
        "2",
        "--parameters-json",
        json.dumps(parameters, sort_keys=True),
        "--trajectory-npz",
        str(args.trajectory_npz),
        "--capture-all-particle-frames",
        "--render-bridge-socket",
        str(socket_path),
        "--render-shared-memory-name",
        memory.name,
        "--render-representation",
        representation,
        "--render-bridge-timeout-s",
        str(args.bridge_timeout_s),
        "--render-voxel-size-m",
        "0.003",
        "--render-support-radius-m",
        "0.006",
        "--render-surface-threshold",
        "0.45",
    ]
    if args.architecture == "same_process":
        producer_command = [
            "embedded_in_isaac601_process",
            "solver=labutopia_wcsph",
            f"observations={args.max_observations}",
            f"representation={representation}",
        ]
    renderer_stdout_path = scope / "isaac_parent.stdout.log"
    renderer_stderr_path = scope / "isaac_parent.stderr.log"
    producer_stdout_path = scope / "newton.stdout.log"
    producer_stderr_path = scope / "newton.stderr.log"
    runtime_root = _short_runtime_root(scope / "newton_runtime")
    producer_environment = _sealed_environment(
        NEWTON_PREFIX, runtime_root, isaac=False
    )
    renderer_stdout = renderer_stdout_path.open("xb")
    renderer_stderr = renderer_stderr_path.open("xb")
    producer_stdout = None
    producer_stderr = None
    renderer = subprocess.Popen(
        renderer_command,
        cwd=REPO_ROOT,
        env=renderer_environment,
        stdout=renderer_stdout,
        stderr=renderer_stderr,
        start_new_session=True,
    )
    producer: subprocess.Popen[bytes] | None = None
    renderer_started = time.time()
    producer_started = None
    producer_finished = None
    contention: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    monitor_samples: list[dict[str, Any]] = []
    timed_out = False
    try:
        if args.architecture == "external_bridge":
            _wait_for_path(
                renderer_output / "bridge_ready.json",
                renderer,
                min(args.lane_timeout_s, 900.0),
            )
            producer_stdout = producer_stdout_path.open("xb")
            producer_stderr = producer_stderr_path.open("xb")
            producer_started = time.time()
            producer = subprocess.Popen(
                producer_command,
                cwd=REPO_ROOT,
                env=producer_environment,
                stdout=producer_stdout,
                stderr=producer_stderr,
                start_new_session=True,
            )
        else:
            producer_started = renderer_started
        deadline = time.monotonic() + args.lane_timeout_s
        while (
            (producer is not None and producer.poll() is None)
            or renderer.poll() is None
        ):
            foreign, advisory = _gpu_process_classification(os.getpid())
            sample = {
                "observed_unix_s": time.time(),
                "foreign_compute_processes": foreign,
                "advisory_compute_processes": advisory,
            }
            monitor_samples.append(sample)
            if advisory:
                advisories.append(sample)
            if foreign:
                contention.append(sample)
                break
            if (
                producer is not None
                and producer.poll() is not None
                and producer_finished is None
            ):
                producer_finished = time.time()
            if (
                producer is not None
                and producer.poll() not in (None, 0)
            ) or renderer.poll() not in (None, 0):
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(args.gpu_monitor_interval_s)
        if (
            producer is not None and producer.poll() is None
        ) or renderer.poll() is None:
            if producer is not None:
                _stop_process_group(producer)
            _stop_process_group(renderer)
        else:
            if producer is not None:
                producer.wait()
            renderer.wait()
        if (
            producer_finished is None
            and producer is not None
            and producer.poll() is not None
        ):
            producer_finished = time.time()
        if producer is None and renderer.poll() is not None:
            producer_finished = time.time()
    finally:
        if producer is not None:
            _stop_process_group(producer)
        _stop_process_group(renderer)
        renderer_stdout.close()
        renderer_stderr.close()
        if producer_stdout is not None:
            producer_stdout.close()
        if producer_stderr is not None:
            producer_stderr.close()
        memory.close()
        try:
            memory.unlink()
            memory_cleanup = "unlinked_by_owner"
        except FileNotFoundError:
            memory_cleanup = "prematurely_unlinked"
        if socket_path.exists():
            socket_path.unlink()

    producer_result_path = producer_output / "result.json"
    renderer_result_path = renderer_output / "result.json"
    renderer_manifest_path = renderer_evidence / "run_manifest.json"
    producer_result = (
        json.loads(producer_result_path.read_text(encoding="utf-8"))
        if producer_result_path.is_file()
        else None
    )
    renderer_result = (
        json.loads(renderer_result_path.read_text(encoding="utf-8"))
        if renderer_result_path.is_file()
        else None
    )
    renderer_manifest = (
        json.loads(renderer_manifest_path.read_text(encoding="utf-8"))
        if renderer_manifest_path.is_file()
        else None
    )
    renderer_runtime_receipt = (
        json.loads(renderer_receipt.read_text(encoding="utf-8"))
        if renderer_receipt.is_file()
        else None
    )
    renderer_returncode = renderer.returncode
    producer_returncode = (
        producer.returncode
        if producer is not None
        else 0
        if renderer_returncode == 0 and isinstance(producer_result, Mapping)
        else renderer_returncode
    )
    producer_task_passed = bool(
        isinstance(producer_result, Mapping)
        and producer_result.get("status")
        in {
            "performance_valid_quality_candidate",
            "performance_valid_quality_unqualified",
        }
    )
    renderer_task_passed = bool(
        isinstance(renderer_result, Mapping)
        and renderer_result.get("status") == "passed"
    )
    quality_gate_passed = bool(
        isinstance(producer_result, Mapping)
        and producer_result.get("stability", {}).get("passed")
        and producer_result.get("quality", {}).get("numeric_passed")
    )
    passed = bool(
        producer_returncode == 0
        and renderer_returncode == 0
        and not contention
        and not timed_out
        and memory_cleanup == "unlinked_by_owner"
        and isinstance(producer_result, Mapping)
        and isinstance(renderer_result, Mapping)
        and (
            (
                args.renderer_runtime == "isaac41"
                and isinstance(renderer_manifest, Mapping)
                and renderer_manifest.get("status") == "passed"
            )
            or (
                args.renderer_runtime == "isaac601"
                and isinstance(renderer_runtime_receipt, Mapping)
                and renderer_runtime_receipt.get("status") == "passed"
            )
        )
        and producer_task_passed
        and renderer_task_passed
        and (quality_gate_passed or args.smoke)
    )
    particle_artifact = (
        producer_result.get("artifacts", {}).get("all_particle_frames")
        if isinstance(producer_result, Mapping)
        else None
    )
    record = {
        "schema": "labutopia.wcsph_isaac_rgb_run.v2",
        "status": "passed" if passed else "failed",
        "resolution_id": resolution_id,
        "resolution": [width, height],
        "representation": representation,
        "architecture": args.architecture,
        "renderer_runtime": args.renderer_runtime,
        "render_profile": args.render_profile,
        "repeat_index": repeat_index,
        "observation_count": args.max_observations,
        "producer_command": producer_command,
        "renderer_command": renderer_command,
        "producer_environment_sha256": (
            _canonical_sha256(producer_environment)
            if args.architecture == "external_bridge"
            else None
        ),
        "renderer_environment_sha256": (
            _canonical_sha256(renderer_environment)
            if renderer_environment is not None
            else None
        ),
        "producer_returncode": producer_returncode,
        "renderer_returncode": renderer_returncode,
        "producer_online_wall_seconds": (
            producer_finished - producer_started
            if producer_started is not None and producer_finished is not None
            else None
        ),
        "renderer_parent_wall_seconds": time.time() - renderer_started,
        "timed_out": timed_out,
        "acceptance": {
            "producer_task_passed": producer_task_passed,
            "renderer_task_passed": renderer_task_passed,
            "full_episode_quality_gate_passed": quality_gate_passed,
            "full_episode_quality_gate_required": not args.smoke,
        },
        "gpu_isolation": {
            "passed": not contention,
            "monitor_interval_s": args.gpu_monitor_interval_s,
            "sample_count": len(monitor_samples),
            "contention": contention,
            "advisories": advisories,
        },
        "shared_memory_cleanup": memory_cleanup,
        "producer_runtime_receipt": (
            {"path": str(producer_receipt), "sha256": sha256_file(producer_receipt)}
            if producer_receipt.is_file()
            else {
                "path": str(renderer_receipt),
                "sha256": sha256_file(renderer_receipt),
                "shared_with_renderer": True,
            }
            if args.architecture == "same_process" and renderer_receipt.is_file()
            else None
        ),
        "renderer_runtime_manifest": (
            {"path": str(renderer_manifest_path), "sha256": sha256_file(renderer_manifest_path)}
            if renderer_manifest_path.is_file()
            else None
        ),
        "renderer_runtime_receipt": (
            {
                "path": str(renderer_receipt),
                "sha256": sha256_file(renderer_receipt),
            }
            if renderer_receipt.is_file()
            else None
        ),
        "producer_result": producer_result,
        "renderer_result": renderer_result,
        "particle_content_sha256": (
            _particle_content_sha256(Path(particle_artifact["path"]))
            if isinstance(particle_artifact, Mapping)
            else None
        ),
        "logs": {
            "producer_stdout": (
                {"path": str(producer_stdout_path), "sha256": sha256_file(producer_stdout_path)}
                if producer_stdout_path.is_file()
                else {"shared_with_renderer": True}
            ),
            "producer_stderr": (
                {"path": str(producer_stderr_path), "sha256": sha256_file(producer_stderr_path)}
                if producer_stderr_path.is_file()
                else {"shared_with_renderer": True}
            ),
            "renderer_stdout": {"path": str(renderer_stdout_path), "sha256": sha256_file(renderer_stdout_path)},
            "renderer_stderr": {"path": str(renderer_stderr_path), "sha256": sha256_file(renderer_stderr_path)},
        },
    }
    record["content_sha256"] = _canonical_sha256(record)
    _atomic_json(scope / "run.json", record)
    return record


def _summaries(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    groups = sorted(
        {(str(record["resolution_id"]), str(record["representation"])) for record in records}
    )
    for resolution_id, representation in groups:
        selected = [
            record
            for record in records
            if record["resolution_id"] == resolution_id
            and record["representation"] == representation
            and record["status"] == "passed"
        ]
        samples = []
        gpu_samples = []
        renderer_stage_samples: dict[str, list[np.ndarray]] = {}
        repeat_fps = []
        repeat_gpu_fps = []
        for record in selected:
            artifact = record["producer_result"]["artifacts"]["render_bridge_timings"]
            with np.load(Path(artifact["path"]), allow_pickle=False) as archive:
                values = np.asarray(archive["artifact_ready_ms"], dtype=np.float64)
            steady = values[1:] if len(values) > 1 else values
            samples.append(steady)
            repeat_fps.append(float(1000.0 / np.mean(steady)))
            render_artifact = (
                record["renderer_result"].get("artifacts", {}).get(
                    "render_timing_arrays"
                )
            )
            if isinstance(render_artifact, Mapping):
                with np.load(
                    Path(render_artifact["path"]), allow_pickle=False
                ) as render_archive:
                    host_ready = np.asarray(
                        render_archive["camera_host_ready_ms"],
                        dtype=np.float64,
                    )
                    gpu_ready = np.asarray(
                        render_archive["camera_gpu_ready_ms"],
                        dtype=np.float64,
                    )
                    if len(gpu_ready) == len(values):
                        gpu_chain = values - host_ready + gpu_ready
                        gpu_steady = (
                            gpu_chain[1:]
                            if len(gpu_chain) > 1
                            else gpu_chain
                        )
                        gpu_samples.append(gpu_steady)
                        repeat_gpu_fps.append(
                            float(1000.0 / np.mean(gpu_steady))
                        )
                    for key in (
                        "reconstruction_ms",
                        "usd_authoring_ms",
                        "rtx_render_ms",
                        "camera_host_ready_ms",
                        "camera_gpu_ready_ms",
                        "camera_gpu_to_cpu_ms",
                        "frame_processing_ms",
                    ):
                        stage_values = np.asarray(
                            render_archive[key], dtype=np.float64
                        )
                        if len(stage_values):
                            renderer_stage_samples.setdefault(key, []).append(
                                stage_values[1:]
                                if len(stage_values) > 1
                                else stage_values
                            )
        pooled = np.concatenate(samples) if samples else np.asarray([], dtype=np.float64)
        gpu_pooled = (
            np.concatenate(gpu_samples)
            if gpu_samples
            else np.asarray([], dtype=np.float64)
        )
        final_scores = [
            record["producer_result"]["quality"]["final_score"] for record in selected
        ]
        hashes = [str(record["particle_content_sha256"]) for record in selected]
        rows.append(
            {
                "resolution_id": resolution_id,
                "resolution": list(RESOLUTIONS[resolution_id]),
                "representation": representation,
                "requested_repeats": len(
                    [
                        record
                        for record in records
                        if record["resolution_id"] == resolution_id
                        and record["representation"] == representation
                    ]
                ),
                "completed_repeats": len(selected),
                "official_sample_policy": "pooled_steady_frames_excluding_observation_0_per_repeat",
                "artifact_ready": summarize_milliseconds(pooled) if len(pooled) else None,
                "artifact_ready_fps": float(1000.0 / np.mean(pooled)) if len(pooled) else None,
                "cpu_ready": summarize_milliseconds(pooled) if len(pooled) else None,
                "cpu_ready_fps": float(1000.0 / np.mean(pooled)) if len(pooled) else None,
                "gpu_ready": (
                    summarize_milliseconds(gpu_pooled)
                    if len(gpu_pooled)
                    else None
                ),
                "gpu_ready_fps": (
                    float(1000.0 / np.mean(gpu_pooled))
                    if len(gpu_pooled)
                    else None
                ),
                "repeat_fps": repeat_fps,
                "repeat_gpu_fps": repeat_gpu_fps,
                "repeat_fps_min": min(repeat_fps, default=None),
                "repeat_fps_max": max(repeat_fps, default=None),
                "quality": (
                    {
                        "target_fraction": float(np.mean([row["target_fraction"] for row in final_scores])),
                        "tabletop_spill_fraction": float(
                            np.mean([row["tabletop_spill_fraction"] for row in final_scores])
                        ),
                        "below_table": int(max(row["below_table"] for row in final_scores)),
                        "nonfinite": int(max(row["nonfinite"] for row in final_scores)),
                        "passed_all": all(
                            record["producer_result"]["quality"]["numeric_passed"]
                            and record["producer_result"]["stability"]["passed"]
                            for record in selected
                        ),
                    }
                    if final_scores
                    else None
                ),
                "particle_content_sha256": hashes[0] if hashes and len(set(hashes)) == 1 else None,
                "deterministic_across_repeats": bool(hashes) and len(set(hashes)) == 1,
                "renderer_stages": {
                    key: summarize_milliseconds(np.concatenate(values))
                    for key, values in sorted(renderer_stage_samples.items())
                },
            }
        )
    return rows


def run(args: argparse.Namespace) -> int:
    if args.output_root.exists():
        raise FileExistsError(f"output_root_exists:{args.output_root}")
    args.output_root.mkdir(parents=True)
    preflight = {
        "newton_python": str(NEWTON_PYTHON),
        "newton_python_exists": NEWTON_PYTHON.is_file(),
        "newton_lock": str(NEWTON_LOCK),
        "newton_lock_exists": NEWTON_LOCK.is_file(),
        "formal_isaac41_parent": str(
            REPO_ROOT / "tools/labutopia_fluid/run_isaac41_newton_render_bridge.py"
        ),
        "renderer_runtime": args.renderer_runtime,
        "render_profile": args.render_profile,
        "isaac601_python": str(ISAAC601_PYTHON),
        "isaac601_python_exists": ISAAC601_PYTHON.is_file(),
        "isaac601_lock": str(ISAAC601_LOCK),
        "isaac601_lock_exists": ISAAC601_LOCK.is_file(),
        "packet": {"path": str(args.packet), "sha256": sha256_file(args.packet)},
        "scene": {"path": str(args.scene), "sha256": sha256_file(args.scene)},
        "trajectory": {
            "path": str(args.trajectory_npz),
            "sha256": sha256_file(args.trajectory_npz),
        },
    }
    preflight["passed"] = bool(
        preflight["newton_python_exists"] and preflight["newton_lock_exists"]
        and (
            args.renderer_runtime == "isaac41"
            or (
                preflight["isaac601_python_exists"]
                and preflight["isaac601_lock_exists"]
            )
        )
    )
    _atomic_json(args.output_root / "preflight.json", preflight)
    if not preflight["passed"]:
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
            {"status": "blocked_gpu_busy", "gpu_idle_gate": gpu_gate},
        )
        return 2
    records = []
    for resolution_id in args.resolutions:
        repeats = 1 if args.smoke or resolution_id == "720" else args.primary_repeats
        for representation in args.representations:
            for repeat_index in range(repeats):
                record = _run_lane(
                    args=args,
                    resolution_id=resolution_id,
                    representation=representation,
                    repeat_index=repeat_index,
                )
                records.append(record)
                if record["status"] != "passed":
                    break
            if records[-1]["status"] != "passed":
                break
        if records[-1]["status"] != "passed":
            break
    summaries = _summaries(records)
    expected_runs = sum(
        (1 if args.smoke or resolution_id == "720" else args.primary_repeats)
        * len(args.representations)
        for resolution_id in args.resolutions
    )
    matrix = {
        "schema": "labutopia.wcsph_isaac_rgb_matrix.v2",
        "status": (
            "passed"
            if len(records) == expected_runs and all(record["status"] == "passed" for record in records)
            else "failed"
        ),
        "run_id": secrets.token_hex(16),
        "claim_boundary": (
            (
                "formal_isaac41_effective_runtime_v2_renderer;"
                if args.renderer_runtime == "isaac41"
                else "experimental_isaac601_unvalidated_driver_renderer;"
            )
            + "experimental_newton140_wcsph_producer;"
            + (
                "not_isaac601_rtx;not_strict_same_runtime_acceleration"
                if args.renderer_runtime == "isaac41"
                else (
                    "not_formal_evidence;external_shared_memory_architecture"
                    if args.architecture == "external_bridge"
                    else "not_formal_evidence;same_process_threaded_shared_frame_v1"
                )
            )
            + (
                ";media_generation_png_io_in_timed_loop_not_performance_evidence"
                if args.save_all_rgb
                else ""
            )
        ),
        "performance_valid": bool(
            not args.smoke
            and not args.save_all_rgb
            and args.max_observations == 953
            and len(records) == expected_runs
            and all(record["status"] == "passed" for record in records)
        ),
        "official_timing_boundary": (
            "media_generation_only;png_encoding_in_timed_loop;not_performance_evidence"
            if args.save_all_rgb
            else (
                "before_wcsph_logical_step_to_after_both_camera_rgb_arrays_are_copied_validated_hashed;"
                "observation_0_excluded_per_repeat;startup_stage_load_shader_warmup_and_png_encoding_excluded"
            )
        ),
        "source": _source_record(),
        "preflight": preflight,
        "gpu_idle_gate": gpu_gate,
        "gpu_postflight": gpu_snapshot(),
        "configuration": {
            "architecture": args.architecture,
            "resolutions": args.resolutions,
            "representations": args.representations,
            "primary_repeats": args.primary_repeats,
            "appendix_repeats": 1,
            "observation_count": args.max_observations,
            "particle_count": 3600,
            "camera_paths": [
                "/World/InternDataParityCamera",
                "/World/InternDataParityCloseupCamera",
            ],
            "renderer": _renderer_for_profile(
                args.renderer_runtime, args.render_profile
            ),
            "renderer_runtime": args.renderer_runtime,
            "render_profile": args.render_profile,
            "allow_unvalidated_driver": bool(
                args.allow_unvalidated_driver
            ),
            "save_all_rgb": bool(args.save_all_rgb),
            "rt_subframes": 1,
            "surface": {
                "backend": "newton_warp115_gpu_marching_cubes",
                "voxel_size_m": 0.003,
                "support_radius_m": 0.006,
                "threshold": 0.45,
                "residual_policy": "outside_bounds_particles_rendered_as_points",
            },
        },
        "historical_reference": {
            "isaac41_pbd_particles_2x256_fps": 6.1,
            "isaac41_pbd_surface_pick_2x256_fps": 4.3,
            "isaac41_pbd_surface_full_episode_2x256_fps": 3.0349817522942617,
            "comparability": "historical_reference_only_not_matched_runtime",
        },
        "summary": summaries,
        "runs": records,
    }
    matrix["content_sha256"] = _canonical_sha256(matrix)
    _atomic_json(args.output_root / "matrix.json", matrix)
    print(
        json.dumps(
            {
                "status": matrix["status"],
                "performance_valid": matrix["performance_valid"],
                "matrix": str(args.output_root / "matrix.json"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if matrix["status"] == "passed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--scene", type=Path, default=SCENE)
    parser.add_argument("--trajectory-npz", type=Path, default=TRAJECTORY)
    parser.add_argument(
        "--resolutions", nargs="+", choices=tuple(RESOLUTIONS), default=["256", "720"]
    )
    parser.add_argument(
        "--representations", nargs="+", choices=REPRESENTATIONS, default=list(REPRESENTATIONS)
    )
    parser.add_argument("--primary-repeats", type=int, default=3)
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--stage-warmup-updates", type=int, default=64)
    parser.add_argument("--bridge-timeout-s", type=float, default=600.0)
    parser.add_argument("--lane-timeout-s", type=float, default=7200.0)
    parser.add_argument("--gpu-monitor-interval-s", type=float, default=1.0)
    parser.add_argument("--wait-gpu-hours", type=float, default=12.0)
    parser.add_argument("--gpu-poll-seconds", type=float, default=10.0)
    parser.add_argument("--gpu-idle-samples", type=int, default=3)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--renderer-runtime",
        choices=("isaac41", "isaac601"),
        default="isaac41",
    )
    parser.add_argument(
        "--render-profile",
        choices=("strict", "cuda_rgb", "minimal_textured"),
        default="strict",
    )
    parser.add_argument("--allow-unvalidated-driver", action="store_true")
    parser.add_argument("--save-all-rgb", action="store_true")
    parser.add_argument(
        "--architecture",
        choices=("external_bridge", "same_process"),
        default="external_bridge",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.output_root = args.output_root.resolve()
    args.packet = args.packet.resolve(strict=True)
    args.scene = args.scene.resolve(strict=True)
    args.trajectory_npz = args.trajectory_npz.resolve(strict=True)
    if args.renderer_runtime == "isaac41" and args.render_profile != "strict":
        parser.error("Isaac 4.1 baseline supports only --render-profile strict")
    if args.renderer_runtime == "isaac41" and args.allow_unvalidated_driver:
        parser.error("driver override is experimental Isaac 6 only")
    if args.architecture == "same_process" and args.renderer_runtime != "isaac601":
        parser.error("same-process architecture requires Isaac 6")
    if args.smoke:
        args.max_observations = min(args.max_observations, 32)
        args.resolutions = ["256"]
        args.primary_repeats = 1
        args.gpu_idle_samples = 1
    if args.primary_repeats < 1:
        parser.error("primary repeats must be positive")
    if args.max_observations < 1 or args.max_observations > 953:
        parser.error("max observations out of range")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

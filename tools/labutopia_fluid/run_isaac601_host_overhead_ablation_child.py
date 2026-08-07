#!/usr/bin/env python3
"""Attest Isaac 6.0.1 and run a host-overhead ablation for WCSPH."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_fresh_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"child_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.link(temporary, path)
    temporary.unlink()


def _summarize_ms(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        raise ValueError("empty_timing_series")
    n = len(ordered)
    return {
        "count": float(n),
        "mean_ms": sum(ordered) / n,
        "median_ms": ordered[n // 2],
        "p95_ms": ordered[max(0, int(0.95 * (n - 1)))],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
    }


def _run_host_microbench(*, frames: int, particle_count: int) -> dict[str, Any]:
    """Measure Kit/USD Points host cost without WCSPH or cameras."""
    import time

    import numpy as np
    import omni.kit.app
    import omni.usd
    from pxr import Gf, UsdGeom, Vt

    if frames < 1 or particle_count < 1:
        raise ValueError("host_microbench_invalid_counts")

    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("isaac_usd_stage_missing_after_new_stage")

    # Warm Kit once after stage creation.
    app.update()

    empty_kit_ms: list[float] = []
    for _ in range(frames):
        started = time.perf_counter()
        app.update()
        empty_kit_ms.append((time.perf_counter() - started) * 1000.0)

    points = UsdGeom.Points.Define(stage, "/World/LiquidParticles")
    widths = [0.003] * particle_count
    points.CreateWidthsAttr().Set(Vt.FloatArray(widths))
    points.CreateDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0.05, 0.65, 0.82)]))
    points_attr = points.CreatePointsAttr()
    seed = np.zeros((particle_count, 3), dtype=np.float32)
    points_attr.Set(Vt.Vec3fArray.FromNumpy(seed))
    app.update()

    static_points_kit_ms: list[float] = []
    for _ in range(frames):
        started = time.perf_counter()
        app.update()
        static_points_kit_ms.append((time.perf_counter() - started) * 1000.0)

    author_ms: list[float] = []
    author_plus_kit_ms: list[float] = []
    rng = np.random.default_rng(0)
    for _ in range(frames):
        positions = rng.normal(size=(particle_count, 3)).astype(np.float32) * 0.01
        started = time.perf_counter()
        points_attr.Set(Vt.Vec3fArray.FromNumpy(positions))
        author_done = time.perf_counter()
        app.update()
        finished = time.perf_counter()
        author_ms.append((author_done - started) * 1000.0)
        author_plus_kit_ms.append((finished - started) * 1000.0)

    return {
        "schema": "labutopia.isaac601_host_microbench.v1",
        "claim_boundary": (
            "experimental_isaac601_lane;no_rtx_cameras;"
            "no_wcsph_solver;not_formal_isaac41_evidence"
        ),
        "frames": frames,
        "particle_count": particle_count,
        "timing": {
            "empty_stage_kit_update": _summarize_ms(empty_kit_ms),
            "static_points_kit_update": _summarize_ms(static_points_kit_ms),
            "usd_points_authoring": _summarize_ms(author_ms),
            "usd_points_authoring_plus_kit_update": _summarize_ms(author_plus_kit_ms),
        },
    }


def _lock_record(path: Path) -> dict[str, Any]:
    manifest_path = path.resolve(strict=True)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if value.get("schema") != "labutopia.experimental_fluid_environment_lock.v1":
        raise RuntimeError("environment_lock_schema_mismatch")
    if Path(str(value.get("prefix", ""))).resolve(strict=True) != Path(sys.prefix).resolve(strict=True):
        raise RuntimeError("environment_lock_prefix_mismatch")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise RuntimeError("environment_lock_artifacts_missing")
    verified = {}
    for name in ("conda_explicit", "pip_freeze_all", "pip_inspect"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise RuntimeError(f"environment_lock_artifact_missing:{name}")
        artifact = Path(str(record.get("path", ""))).resolve(strict=True)
        actual = _sha256_file(artifact)
        if actual != record.get("sha256"):
            raise RuntimeError(f"environment_lock_artifact_hash_mismatch:{name}")
        verified[name] = {"path": str(artifact), "sha256": actual}
    return {
        "path": str(manifest_path),
        "sha256": _sha256_file(manifest_path),
        "artifacts": verified,
    }


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    try:
        separator = values.index("--")
    except ValueError:
        separator = len(values)
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-manifest", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--child-failure", type=Path, required=True)
    parser.add_argument(
        "--host-runtime-update",
        choices=("none", "isaac_kit", "isaac_kit_particles"),
        required=True,
    )
    parser.add_argument("--host-microbench-output", type=Path)
    parser.add_argument("--host-microbench-frames", type=int, default=120)
    parser.add_argument("--host-microbench-particles", type=int, default=3600)
    args = parser.parse_args(values[:separator])
    benchmark_arguments = values[separator + 1 :] if separator < len(values) else []
    application = None
    try:
        from tools.labutopia_fluid import attest_experimental_fluid_runtime as attestation

        receipt = attestation._base_receipt("isaacsim601_wcsph_r1")
        driver = attestation._isaac_driver_preflight()
        receipt["driver_preflight"] = driver
        application = attestation._attest_isaac(receipt)
        receipt["capabilities"] = {
            "physics": {
                "status": "passed",
                "claim": "isaac_kit_newton_warp_wcsph_host_overhead_ablation",
            },
            "rtx": {
                "status": "passed" if driver["isaac601_rtx_supported"] else "blocked_driver",
                "blocker": None
                if driver["isaac601_rtx_supported"]
                else "isaac601_rtx_driver_unsupported",
            },
            "host_runtime_update": args.host_runtime_update,
        }
        receipt["environment_lock"] = _lock_record(args.lock_manifest)
        receipt["status"] = "passed"
        receipt["content_sha256"] = attestation._canonical_sha256(receipt)
        _write_fresh_json(args.runtime_receipt.resolve(), receipt)

        if args.host_microbench_output is not None:
            microbench = _run_host_microbench(
                frames=args.host_microbench_frames,
                particle_count=args.host_microbench_particles,
            )
            _write_fresh_json(args.host_microbench_output.resolve(), microbench)

        from tools.labutopia_fluid.run_newton_only_fluid_benchmark import main as benchmark_main

        return benchmark_main(
            [
                *benchmark_arguments,
                "--runtime-receipt",
                str(args.runtime_receipt.resolve()),
                "--host-runtime-update",
                args.host_runtime_update,
            ]
        )
    except BaseException as error:
        failure = {
            "schema": "labutopia.isaac601_host_overhead_ablation_child_failure.v1",
            "status": "blocked_runtime",
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "host_runtime_update": args.host_runtime_update,
        }
        try:
            _write_fresh_json(args.child_failure.resolve(), failure)
        except Exception:
            print(json.dumps(failure, sort_keys=True), flush=True)
        return 2
    finally:
        if application is not None:
            try:
                application.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

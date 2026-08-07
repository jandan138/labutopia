#!/usr/bin/env python3
"""Run WCSPH and Isaac 6 RTX in one sealed Python process.

The renderer remains on Kit's main thread.  WCSPH runs in a worker thread and
uses the existing checksummed shared-frame contract, so this first integrated
lane changes runtime/process ownership without inventing a second solver loop.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: Sequence[str] | None = None) -> int:
    from tools.labutopia_fluid import attest_experimental_fluid_runtime as attestation
    from tools.labutopia_fluid import run_isaac601_newton_render_bridge as bridge
    from tools.labutopia_fluid.run_isaac601_wcsph_attested_child import (
        _lock_record,
        _write_fresh_json,
    )

    parser = bridge.build_parser()
    parser.add_argument("--lock-manifest", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--child-failure", type=Path, required=True)
    parser.add_argument("--producer-output-dir", type=Path, required=True)
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--warmup-observations", type=int, default=2)
    args = parser.parse_args(argv)
    bridge._apply_render_profile(args)
    application: Any | None = None
    producer_thread: threading.Thread | None = None
    producer_state: dict[str, Any] = {}
    try:
        receipt = attestation._base_receipt("isaacsim601_wcsph_r1")
        driver = attestation._isaac_driver_preflight(
            allow_unvalidated_driver=args.allow_unvalidated_driver
        )
        receipt["driver_preflight"] = driver
        application = attestation._attest_isaac(
            receipt,
            allow_unvalidated_driver=args.allow_unvalidated_driver,
            width=args.width,
            height=args.height,
            renderer=args.renderer,
            minimal_shading_mode=args.minimal_shading_mode,
        )
        receipt["capabilities"] = {
            "physics": {
                "status": "passed",
                "claim": "isaac601_integrated_newton121_warp113_wcsph",
            },
            "rtx": {
                "status": (
                    "passed"
                    if driver["isaac601_rtx_supported"]
                    else "unvalidated_override_enabled"
                    if args.allow_unvalidated_driver
                    else "blocked_driver"
                ),
                "blocker": (
                    None
                    if driver["isaac601_rtx_supported"]
                    or args.allow_unvalidated_driver
                    else "isaac601_rtx_driver_unsupported"
                ),
                "formal_evidence_eligible": False,
            },
            "architecture": {
                "id": "same_process_threaded_shared_frame_v1",
                "python_process_count": 1,
                "direct_zero_copy": False,
            },
        }
        receipt["environment_lock"] = _lock_record(args.lock_manifest)
        receipt["status"] = "passed"
        receipt["content_sha256"] = attestation._canonical_sha256(receipt)
        receipt_path = args.runtime_receipt.resolve()
        _write_fresh_json(receipt_path, receipt)

        ready_path = args.output_dir.resolve() / "bridge_ready.json"

        def run_producer() -> None:
            try:
                deadline = time.monotonic() + args.bridge_timeout_s
                while not ready_path.is_file():
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"same_process_renderer_ready_timeout:{ready_path}"
                        )
                    time.sleep(0.05)
                from tools.labutopia_fluid.run_newton_only_fluid_benchmark import (
                    main as benchmark_main,
                )

                representation = (
                    "particles"
                    if args.surface_mode == "particles"
                    else "surface_gpu"
                )
                parameters = {
                    "boundary_kind": "boxes",
                    "maximum_dt_s": 1.0 / 120.0,
                    "profile_stages": False,
                    "sound_speed_m_s": 4.0,
                    "viscosity": 0.002,
                }
                command = [
                    "--solver-id",
                    "labutopia_wcsph",
                    "--packet",
                    str(args.packet),
                    "--output-dir",
                    str(args.producer_output_dir),
                    "--particle-count",
                    "3600",
                    "--max-observations",
                    str(args.max_observations),
                    "--warmup-observations",
                    str(args.warmup_observations),
                    "--parameters-json",
                    json.dumps(parameters, sort_keys=True),
                    "--trajectory-npz",
                    str(args.trajectory_npz),
                    "--capture-all-particle-frames",
                    "--runtime-receipt",
                    str(receipt_path),
                    "--render-bridge-socket",
                    str(args.bridge_socket),
                    "--render-shared-memory-name",
                    args.shared_memory_name,
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
                producer_state["command"] = command
                producer_state["returncode"] = benchmark_main(command)
            except BaseException as error:
                producer_state["error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                }

        producer_thread = threading.Thread(
            target=run_producer,
            name="labutopia-wcsph-producer",
            daemon=True,
        )
        producer_thread.start()
        bridge_result = bridge.run(
            args,
            application=application,
            runtime_record={
                "lane": "experimental_isaac601_same_process_wcsph_rtx",
                "architecture": "same_process_threaded_shared_frame_v1",
                "receipt_path": str(receipt_path),
                "receipt_sha256": bridge._sha256_file(receipt_path),
                "receipt_content_sha256": receipt["content_sha256"],
                "formal_evidence_eligible": False,
            },
        )
        producer_thread.join(timeout=args.bridge_timeout_s)
        if producer_thread.is_alive():
            raise TimeoutError("same_process_producer_join_timeout")
        if "error" in producer_state:
            raise RuntimeError(
                f"same_process_producer_failed:{producer_state['error']}"
            )
        if producer_state.get("returncode") != 0:
            raise RuntimeError(
                "same_process_producer_nonzero:"
                f"{producer_state.get('returncode')}"
            )
        bridge_result["same_process_producer"] = {
            "returncode": producer_state["returncode"],
            "result_path": str(args.producer_output_dir / "result.json"),
        }
        bridge_result.pop("content_sha256", None)
        bridge_result["content_sha256"] = bridge._canonical_sha256(
            bridge_result
        )
        bridge._atomic_json(args.output_dir / "result.json", bridge_result)
        return 0
    except BaseException as error:
        failure = {
            "schema": "labutopia.isaac601_wcsph_rgb_same_process_failure.v1",
            "status": "failed_experimental_runtime",
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "producer_state": producer_state,
        }
        try:
            _write_fresh_json(args.child_failure.resolve(), failure)
        except Exception:
            print(json.dumps(failure, sort_keys=True), flush=True)
        return 2
    finally:
        if producer_thread is not None and producer_thread.is_alive():
            producer_thread.join(timeout=5.0)
        if application is not None:
            application.close()


if __name__ == "__main__":
    raise SystemExit(main())

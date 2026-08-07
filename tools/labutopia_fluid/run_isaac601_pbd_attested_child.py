#!/usr/bin/env python3
"""Run the matched 3600-particle PhysX PBD lane under sealed Isaac 6.0.1."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_isaac601_wcsph_attested_child import (  # noqa: E402
    _lock_record,
    _write_fresh_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-manifest", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--child-failure", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-observations", type=int, default=953)
    parser.add_argument("--stage-warmup-updates", type=int, default=32)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in (
        "lock_manifest",
        "runtime_receipt",
        "child_failure",
        "packet",
        "scene",
        "output_dir",
    ):
        setattr(args, name, getattr(args, name).resolve())
    application = None
    try:
        from tools.labutopia_fluid import attest_experimental_fluid_runtime as attestation

        receipt = attestation._base_receipt("isaacsim601_wcsph_r1")
        driver = attestation._isaac_driver_preflight()
        receipt["driver_preflight"] = driver
        application = attestation._attest_isaac(receipt)
        receipt["capabilities"] = {
            "physics": {"status": "passed", "claim": "physx_pbd_headless"},
            "rtx": {
                "status": "passed" if driver["isaac601_rtx_supported"] else "blocked_driver",
                "blocker": None if driver["isaac601_rtx_supported"] else "isaac601_rtx_driver_unsupported",
            },
        }
        receipt["environment_lock"] = _lock_record(args.lock_manifest)
        receipt["status"] = "passed"
        receipt["content_sha256"] = attestation._canonical_sha256(receipt)
        _write_fresh_json(args.runtime_receipt, receipt)

        from tools.labutopia_fluid.run_isaac41_pbd_benchmark import _run_benchmark

        args.mode = "physics-only"
        args.width = 64
        args.height = 64
        args.rt_subframes = 1
        args.evidence_dir = args.output_dir.parent
        _run_benchmark(
            args,
            application=application,
            runtime_record={
                "lane": "experimental_isaac601_physx_pbd",
                "receipt_path": str(args.runtime_receipt),
                "receipt_sha256": attestation._sha256_file(args.runtime_receipt),
                "result_schema": "labutopia.isaac601_pbd_packet_benchmark_result.v1",
                "claim_boundary": (
                    "experimental_isaac601_physx_pbd;matched_packet_and_scene;"
                    "rtx_capability_separate;not_formal_isaac41_evidence"
                ),
            },
        )
        return 0
    except BaseException as error:
        failure = {
            "schema": "labutopia.isaac601_pbd_child_failure.v1",
            "status": "blocked_runtime",
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "executable": sys.executable,
            "prefix": sys.prefix,
        }
        _write_fresh_json(args.child_failure, failure)
        print(
            json.dumps(
                {key: value for key, value in failure.items() if key != "traceback"},
                sort_keys=True,
            ),
            flush=True,
        )
        return 2
    finally:
        if application is not None:
            application.close()


if __name__ == "__main__":
    raise SystemExit(main())

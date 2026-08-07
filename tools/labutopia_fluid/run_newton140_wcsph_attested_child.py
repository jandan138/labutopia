#!/usr/bin/env python3
"""Attest the locked Newton 1.4 lane and run WCSPH in the same process."""

from __future__ import annotations

import argparse
import json
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
    args = parser.parse_args(values[:separator])
    benchmark_arguments = values[separator + 1 :] if separator < len(values) else []
    try:
        from tools.labutopia_fluid import attest_experimental_fluid_runtime as attestation

        receipt = attestation._base_receipt("newton140")
        attestation._attest_newton(receipt)
        receipt["capabilities"] = {
            "physics": {
                "status": "passed",
                "claim": "newton140_warp115_wcsph_cuda_same_process",
            }
        }
        receipt["environment_lock"] = _lock_record(args.lock_manifest)
        receipt["status"] = "passed"
        receipt["content_sha256"] = attestation._canonical_sha256(receipt)
        _write_fresh_json(args.runtime_receipt.resolve(), receipt)

        from tools.labutopia_fluid.run_newton_only_fluid_benchmark import main as benchmark_main

        return benchmark_main(
            [
                *benchmark_arguments,
                "--runtime-receipt",
                str(args.runtime_receipt.resolve()),
            ]
        )
    except BaseException as error:
        failure = {
            "schema": "labutopia.newton140_wcsph_child_failure.v1",
            "status": "blocked_runtime",
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "executable": sys.executable,
            "prefix": sys.prefix,
        }
        _write_fresh_json(args.child_failure.resolve(), failure)
        print(
            json.dumps(
                {key: value for key, value in failure.items() if key != "traceback"},
                sort_keys=True,
            ),
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Attest a locked Newton runtime and execute one benchmark in the same child."""

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


def _write_fresh_json(path: Path, value: dict) -> None:
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


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    try:
        separator = values.index("--")
    except ValueError:
        separator = len(values)
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=("main", "rtx"), required=True)
    parser.add_argument(
        "--benchmark-kind",
        choices=("fluid", "mpm"),
        default="fluid",
    )
    parser.add_argument("--lock-manifest", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--child-failure", type=Path, required=True)
    args = parser.parse_args(values[:separator])
    benchmark_arguments = values[separator + 1 :] if separator < len(values) else []
    try:
        from tools.labutopia_fluid.attest_newton_only_runtime import attest

        receipt = attest(args.lane, args.lock_manifest.resolve())
        _write_fresh_json(args.runtime_receipt.resolve(), receipt)
        if args.benchmark_kind == "mpm":
            from tools.labutopia_fluid.run_newton140_mpm_benchmark import (
                main as benchmark_main,
            )
        else:
            from tools.labutopia_fluid.run_newton_only_fluid_benchmark import (
                main as benchmark_main,
            )

        return benchmark_main(
            [*benchmark_arguments, "--runtime-receipt", str(args.runtime_receipt.resolve())]
        )
    except BaseException as error:
        failure = {
            "schema": "labutopia.newton_fluid_child_failure.v1",
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

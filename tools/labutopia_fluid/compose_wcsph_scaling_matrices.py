#!/usr/bin/env python3
"""Compose isolated Newton and Isaac lane runs into one traceable matrix."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_contract import sha256_file  # noqa: E402
from tools.labutopia_fluid.newton_only_contract import RESOLUTIONS  # noqa: E402
from tools.labutopia_fluid.run_wcsph_scaling_matrix import (  # noqa: E402
    _canonical_sha256,
    _summaries,
)


SOLVERS = ("labutopia_dfsph", "labutopia_wcsph")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=False)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _lane_records(matrix_path: Path, lane: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    matrix = _load(matrix_path)
    selected: list[dict[str, Any]] = []
    for raw in matrix.get("runs", []):
        if raw.get("lane") != lane:
            continue
        if raw.get("status") != "completed":
            continue
        isolation = raw.get("gpu_isolation") or {}
        if isolation.get("passed") is not True:
            raise ValueError(f"gpu_isolation_not_passed:{matrix_path}:{raw}")
        result_path = Path(str(raw["result_path"]))
        result = _load(result_path)
        selected.append({**raw, "result": result, "source_matrix": str(matrix_path)})
    expected = {
        (solver, particles, repeat)
        for solver in SOLVERS
        for particles in RESOLUTIONS
        for repeat in range(3)
    }
    actual = {
        (str(record["solver_id"]), int(record["particle_count"]), int(record["repeat_index"]))
        for record in selected
    }
    if actual != expected or len(selected) != len(expected):
        raise ValueError(
            f"incomplete_lane:{lane}:missing={sorted(expected - actual)}:extra={sorted(actual - expected)}"
        )
    return matrix, selected


def compose(
    *,
    newton_matrix_path: Path,
    isaac_matrix_path: Path,
    parity_matrix_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    newton_matrix, newton_records = _lane_records(newton_matrix_path, "newton140")
    isaac_matrix, isaac_records = _lane_records(isaac_matrix_path, "isaac601")
    parity_matrix = _load(parity_matrix_path)
    parity = parity_matrix.get("runtime_parity", [])
    if len(parity) != len(SOLVERS) or not all(item.get("passed") is True for item in parity):
        raise ValueError(f"runtime_parity_not_passed:{parity_matrix_path}")
    records = newton_records + isaac_records
    output: dict[str, Any] = {
        "schema": "labutopia.wcsph_scaling_matrix.composite.v1",
        "status": "completed",
        "claim_boundary": (
            "experimental_kinematic_replay;speed_valid_when_stability_and_gpu_isolation_pass;"
            "pour_quality_diagnostic;not_formal_isaac41_evidence"
        ),
        "policy": (
            "numeric_stability_then_speed;task_quality_does_not_block_timing;"
            "tiny_chromium_swiftshader_lte_32mib_is_recorded_advisory"
        ),
        "configuration": {
            "lanes": ["newton140", "isaac601"],
            "solver_ids": list(SOLVERS),
            "particle_counts": list(RESOLUTIONS),
            "repeats": 3,
            "observation_count": 953,
        },
        "source_matrices": [
            {
                "lane": "newton140",
                "path": str(newton_matrix_path),
                "sha256": sha256_file(newton_matrix_path),
                "source_status": newton_matrix.get("status"),
            },
            {
                "lane": "isaac601",
                "path": str(isaac_matrix_path),
                "sha256": sha256_file(isaac_matrix_path),
                "source_status": isaac_matrix.get("status"),
            },
            {
                "lane": "runtime_parity",
                "path": str(parity_matrix_path),
                "sha256": sha256_file(parity_matrix_path),
                "source_status": parity_matrix.get("status"),
            },
        ],
        "summary": _summaries(records),
        "runtime_parity": parity,
        "runs": [{key: value for key, value in record.items() if key != "result"} for record in records],
    }
    output["content_sha256"] = _canonical_sha256(output)
    _atomic_json(output_path, output)
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--newton-matrix", type=Path, required=True)
    parser.add_argument("--isaac-matrix", type=Path, required=True)
    parser.add_argument("--parity-matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = compose(
        newton_matrix_path=args.newton_matrix.resolve(strict=True),
        isaac_matrix_path=args.isaac_matrix.resolve(strict=True),
        parity_matrix_path=args.parity_matrix.resolve(strict=True),
        output_path=args.output.resolve(),
    )
    print(json.dumps({"status": result["status"], "runs": len(result["runs"]), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

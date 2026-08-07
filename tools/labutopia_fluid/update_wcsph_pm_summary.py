#!/usr/bin/env python3
"""Build the product-facing WCSPH summary from immutable benchmark evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "reports/2026-08-03-labutopia-isaac6-wcsph-integration-study"
DEFAULT_OUTPUT = REPORT_DIR / "benchmark-summary.json"
FORMAL_PBD = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac41_newton140/runs/matched-full-953-005"
    / "pbd_exact_physics/artifacts/result.json"
)
DEFAULT_MATRIX = (
    REPO_ROOT
    / "outputs/newton_only_fluid_solver_benchmark/2026-08-03_wcsph_parity_gpu_gate_r1/matrix.json"
)
DEFAULT_PBD601_MANIFEST = (
    REPO_ROOT
    / "outputs/newton_only_fluid_solver_benchmark/2026-08-03_isaac601_pbd_gpu_gate_r2/run_manifest.json"
)
RECOVERY = (
    REPO_ROOT
    / "outputs/newton_only_fluid_solver_benchmark/2026-08-03_failed_environment_recovery.json"
)


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _row(
    *,
    route: str,
    runtime: str,
    particles: int | None,
    mode: str,
    physics_ms: float | None,
    chain_ms: float | None,
    stability: bool | None,
    target: float | None,
    spill: float | None,
    evidence_label: str,
    evidence_kind: str,
) -> dict[str, Any]:
    return {
        "route": route,
        "runtime": runtime,
        "particles": particles,
        "mode": mode,
        "physics_ms": physics_ms,
        "physics_fps": 1000.0 / physics_ms if physics_ms else None,
        "chain_ms": chain_ms,
        "chain_fps": 1000.0 / chain_ms if chain_ms else None,
        "stability": stability,
        "target_fraction": target,
        "spill_fraction": spill,
        "evidence_label": evidence_label,
        "evidence_kind": evidence_kind,
    }


def _gpu_blocker(matrix: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not matrix or matrix.get("status") != "blocked_gpu_busy":
        return None
    samples = ((matrix.get("gpu_gate") or {}).get("samples") or [])
    if not samples:
        return {"status": "blocked_gpu_busy"}
    last = samples[-1]
    return {
        "status": "blocked_gpu_busy",
        "memory_used_mib": last.get("memory_used_mib"),
        "utilization_percent": last.get("utilization_percent"),
        "compute_processes": last.get("compute_processes"),
        "observed_unix_s": last.get("observed_unix_s"),
    }


def build(
    *,
    matrix_path: Path,
    pbd601_manifest_path: Path,
) -> dict[str, Any]:
    matrix = _load(matrix_path)
    pbd601_manifest = _load(pbd601_manifest_path)
    formal = _load(FORMAL_PBD)
    if formal is None:
        raise FileNotFoundError(FORMAL_PBD)
    formal_ms = float(formal["timing"]["physics_per_observation"]["mean_ms"])
    formal_score = formal["quality"]["final_score"]
    blocker = _gpu_blocker(matrix)

    rows = [
        _row(
            route="Isaac 4.1 无液体",
            runtime="历史产品 A/B 量级",
            particles=None,
            mode="双相机场景",
            physics_ms=None,
            chain_ms=51.5,
            stability=None,
            target=None,
            spill=None,
            evidence_label="历史量级",
            evidence_kind="warn",
        ),
        _row(
            route="Isaac 4.1 PhysX PBD",
            runtime="effective-runtime v2 正式基线",
            particles=3600,
            mode="Headless 物理",
            physics_ms=formal_ms,
            chain_ms=None,
            stability=True,
            target=float(formal_score["target_fraction"]),
            spill=float(formal_score["tabletop_spill_fraction"]),
            evidence_label="正式 MATCH",
            evidence_kind="ok",
        ),
    ]

    completed_matrix = bool(matrix and matrix.get("status") in {"completed", "completed_with_failures"})
    if completed_matrix:
        for summary in matrix.get("summary", []):
            lane = str(summary["lane"])
            solver_id = str(summary.get("solver_id", "labutopia_wcsph"))
            algorithm = {
                "labutopia_dfsph": "DFSPH",
                "labutopia_wcsph": "WCSPH",
            }.get(solver_id, solver_id)
            rows.append(
                _row(
                    route=f"Newton 1.4 + {algorithm}" if lane == "newton140" else f"Isaac 6 + {algorithm}",
                    runtime=(
                        "Newton 1.4 / Warp 1.15 锁定环境"
                        if lane == "newton140"
                        else "Isaac 6.0.1 同进程 Kit + Warp 1.13"
                    ),
                    particles=int(summary["particle_count"]),
                    mode="Headless 纯物理" if lane == "newton140" else "Headless USD 粒子 + Kit update",
                    physics_ms=summary.get("physics_mean_ms_across_repeats"),
                    chain_ms=summary.get("simulation_chain_mean_ms_across_repeats"),
                    stability=summary.get("stability_passed_all_repeats"),
                    target=summary.get("target_fraction"),
                    spill=summary.get("tabletop_spill_fraction"),
                    evidence_label=f"实测 ×{summary.get('completed_repeats', 0)}",
                    evidence_kind="ok" if summary.get("stability_passed_all_repeats") else "blocked",
                )
            )
    else:
        # Preserve the earlier 900-particle exploratory speed point, but label it
        # explicitly as non-current-runtime evidence.
        rows.append(
            _row(
                route="Newton 1.4 + WCSPH",
                runtime="旧临时探索环境",
                particles=900,
                mode="Headless 纯物理",
                physics_ms=8.646842608265462,
                chain_ms=None,
                stability=True,
                target=0.5933333333333334,
                spill=0.29333333333333333,
                evidence_label="探索实测",
                evidence_kind="warn",
            )
        )
        wait_label = "GPU 被占用" if blocker else "等待实测"
        for route, runtime, mode in (
            ("Newton 1.4 + WCSPH", "Newton 1.4 / Warp 1.15 锁定环境", "Headless 纯物理"),
            ("Isaac 6 + WCSPH", "Isaac 6.0.1 同进程 Kit + Warp 1.13", "Headless USD 粒子 + Kit update"),
        ):
            rows.append(
                _row(
                    route=route,
                    runtime=runtime,
                    particles=3600,
                    mode=mode,
                    physics_ms=None,
                    chain_ms=None,
                    stability=None,
                    target=None,
                    spill=None,
                    evidence_label=wait_label,
                    evidence_kind="warn",
                )
            )

    pbd601_result = None
    if pbd601_manifest and pbd601_manifest.get("status") == "completed":
        result_value = pbd601_manifest.get("result_path")
        pbd601_result = _load(Path(result_value)) if isinstance(result_value, str) else None
    if pbd601_result:
        timing = pbd601_result["timing"]["physics_per_observation"]
        score = pbd601_result["quality"]["final_score"]
        rows.append(
            _row(
                route="Isaac 6 PhysX PBD",
                runtime="实验基线",
                particles=int(pbd601_result["particle_count"]),
                mode="Headless 物理",
                physics_ms=float(timing["mean_ms"]),
                chain_ms=None,
                stability=(score["nonfinite"] == 0 and score["below_table"] == 0),
                target=float(score["target_fraction"]),
                spill=float(score["tabletop_spill_fraction"]),
                evidence_label="实验实测",
                evidence_kind="ok",
            )
        )
    else:
        pbd_status = pbd601_manifest.get("status") if pbd601_manifest else None
        rows.append(
            _row(
                route="Isaac 6 PhysX PBD",
                runtime="实验基线",
                particles=3600,
                mode="Headless 物理",
                physics_ms=None,
                chain_ms=None,
                stability=None,
                target=None,
                spill=None,
                evidence_label="GPU 被占用" if pbd_status == "blocked_gpu_busy" else "等待实测",
                evidence_kind="warn",
            )
        )

    def measured(route: str, particles: int) -> dict[str, Any] | None:
        return next(
            (row for row in rows if row["route"] == route and row["particles"] == particles),
            None,
        )

    frame_budget = []
    newton_wcsph_3600 = measured("Newton 1.4 + WCSPH", 3600)
    isaac_wcsph_3600 = measured("Isaac 6 + WCSPH", 3600)
    isaac_pbd_3600 = measured("Isaac 6 PhysX PBD", 3600)
    if newton_wcsph_3600 and newton_wcsph_3600["physics_ms"]:
        frame_budget.append(
            {"label": "Newton WCSPH 3600 / 物理", "ms": newton_wcsph_3600["physics_ms"], "kind": ""}
        )
    if isaac_wcsph_3600 and isaac_wcsph_3600["chain_ms"]:
        frame_budget.append(
            {"label": "Isaac 6 WCSPH 3600 / 整链", "ms": isaac_wcsph_3600["chain_ms"], "kind": ""}
        )
    if isaac_pbd_3600 and isaac_pbd_3600["physics_ms"]:
        frame_budget.append(
            {"label": "Isaac 6 PBD 3600 / 物理", "ms": isaac_pbd_3600["physics_ms"], "kind": "pbd"}
        )
    frame_budget.extend(
        [
            {"label": "Isaac 4.1 / 无液体", "ms": 51.5, "kind": "dry"},
            {"label": "Isaac 4.1 / PBD 粒子", "ms": 163.8, "kind": "pbd"},
            {"label": "Isaac 4.1 / 连续液面", "ms": 233.3, "kind": "surface"},
        ]
    )

    return {
        "schema": "labutopia.wcsph_pm_followup.v1",
        "as_of_utc": "2026-08-03",
        "claim_boundary": "Isaac 4.1 正式基线与 Isaac 6/Newton 实验结果不可直接宣称同运行时加速比",
        "capabilities": [
            {"label": "Newton 1.4 / Warp 1.15", "value": "锁定可用", "kind": "ok"},
            {"label": "Isaac 6 同进程物理", "value": "锁定可用", "kind": "ok"},
            {"label": "Isaac 6 RTX", "value": "驱动阻塞", "kind": "blocked"},
            {"label": "当前 GPU 测速", "value": "训练占用" if blocker else "可运行", "kind": "warn" if blocker else "ok"},
            {"label": "质量是否阻断测速", "value": "不阻断", "kind": "ok"},
        ],
        "frame_budget": frame_budget,
        "rows": rows,
        "solver_screen": [
            {"solver": "SPlisHSPlasH DFSPH port", "physics_ms": 7.079727236271405, "stability": True, "target": 0.2833333333333333, "spill": 0.6422222222222222, "eligible": False, "verdict": "算法等价性未审查"},
            {"solver": "LabUtopia DFSPH", "physics_ms": 7.17571891398645, "stability": True, "target": 0.2833333333333333, "spill": 0.6422222222222222, "eligible": True, "verdict": "速度候选 #1"},
            {"solver": "LabUtopia WCSPH", "physics_ms": 8.646842608265462, "stability": True, "target": 0.5933333333333334, "spill": 0.29333333333333333, "eligible": True, "verdict": "速度候选 #2"},
            {"solver": "Newton Implicit MPM", "physics_ms": 10.490944092514134, "stability": True, "target": 0.05555555555555555, "spill": 0.9433333333333334, "eligible": True, "verdict": "独立 MPM lane"},
            {"solver": "Warp example SPH", "physics_ms": 12.641119627049438, "stability": True, "target": 0.005555555555555556, "spill": 0.9755555555555555, "eligible": True, "verdict": "速度候选 #3"},
            {"solver": "Warp example APIC", "physics_ms": 32.01833660132863, "stability": True, "target": 0.0, "spill": 1.0, "eligible": True, "verdict": "速度落后"},
            {"solver": "Newton SemiImplicit", "physics_ms": 86.30206523871622, "stability": False, "target": 0.0, "spill": 0.0, "eligible": False, "verdict": "穿桌，测速无效"},
            {"solver": "SPlisHSPlasH PBF port", "physics_ms": 126.86213999517567, "stability": True, "target": 0.005555555555555556, "spill": 0.7144444444444444, "eligible": False, "verdict": "算法等价性未审查"},
            {"solver": "Newton XPBD cohesion", "physics_ms": 145.12150268708547, "stability": False, "target": 0.0, "spill": 0.03777777777777778, "eligible": False, "verdict": "穿桌，测速无效"},
            {"solver": "Newton VBD self-contact", "physics_ms": None, "stability": None, "target": None, "spill": None, "eligible": False, "verdict": "能力阻塞"}
        ],
        "runtime_parity": matrix.get("runtime_parity", []) if completed_matrix else [],
        "blocker": blocker,
        "evidence": {
            "formal_isaac41_pbd": str(FORMAL_PBD),
            "wcsph_matrix": str(matrix_path),
            "isaac601_pbd_manifest": str(pbd601_manifest_path),
            "failed_environment_recovery": str(RECOVERY),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--pbd601-manifest", type=Path, default=DEFAULT_PBD601_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    summary = build(
        matrix_path=args.matrix.resolve(),
        pbd601_manifest_path=args.pbd601_manifest.resolve(),
    )
    _atomic_json(args.output.resolve(), summary)
    print(json.dumps({"status": "written", "output": str(args.output.resolve()), "rows": len(summary["rows"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

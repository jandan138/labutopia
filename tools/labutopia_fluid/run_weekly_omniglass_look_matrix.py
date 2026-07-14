#!/usr/bin/env python3
"""Run the weekly OmniGlass look matrix (B/C × 4096/50k) and write a matrix manifest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ISAAC_PYTHON = (
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
DEFAULT_RUNNER = REPO_ROOT / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py"
DEFAULT_OUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "fluid_spike_weekly_omniglass_look_matrix_20260709_001"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "fluid_spike_weekly_omniglass_look_matrix_20260709.json"
)

MATRIX_CELLS: list[dict[str, Any]] = [
    {
        "cell_id": "B_P1024",
        "look_id": "weekly_omniglass_B",
        "particle_limit": 1024,
        "steps": 120,
        "note": "known_pass_window_visual_hold",
    },
    {
        "cell_id": "B_P4096",
        "look_id": "weekly_omniglass_B",
        "particle_limit": 4096,
        "steps": 120,
    },
    {
        "cell_id": "B_P50000",
        "look_id": "weekly_omniglass_B",
        "particle_limit": 50000,
        "steps": 120,
    },
    {
        "cell_id": "C_P1024",
        "look_id": "weekly_omniglass_C",
        "particle_limit": 1024,
        "steps": 120,
        "note": "known_pass_window_visual_hold",
    },
    {
        "cell_id": "C_P4096",
        "look_id": "weekly_omniglass_C",
        "particle_limit": 4096,
        "steps": 120,
    },
    {
        "cell_id": "C_P50000",
        "look_id": "weekly_omniglass_C",
        "particle_limit": 50000,
        "steps": 120,
    },
]

FORBIDDEN_CLAIMS = [
    "mdl_water_equals_photoreal_water",
    "presentation_video_equals_physics_success",
    "omniglass_water_equals_official_visual_a",
    "reference_liquid_usd_box_cup_equals_labutopia_beaker",
    "colleague_50k_overlay_equals_g1_zero_leak",
]


def build_matrix_manifest(*, cells: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "fluid_spike_weekly_omniglass_look_matrix",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "weekly_omniglass_look_matrix_executed": True,
        "weekly_omniglass_matrix_is_visual_diagnostic_not_official_visual_a": True,
        "official_visual_a_clearwater_unchanged": True,
        "leak_status_remains_particle_readback_authoritative": True,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "cells": list(cells),
        "human_visual_qa_status": "pending",
    }


def _cell_cmd(
    *,
    isaac_python: Path,
    runner: Path,
    cell: dict[str, Any],
    out_root: Path,
    video_stride: int,
    video_fps: float,
) -> list[str]:
    cell_dir = out_root / cell["cell_id"]
    cell_manifest = cell_dir / "runtime_smoke_summary.json"
    return [
        str(isaac_python),
        str(runner),
        "--headless",
        "--hard-exit-after-run",
        "--fluid-safe-wrapper-overlay",
        "--presentation-isosurface-video",
        "--presentation-look-preset",
        str(cell["look_id"]),
        "--disable-particle-debug-display",
        "--particle-limit",
        str(cell["particle_limit"]),
        "--steps",
        str(cell["steps"]),
        "--video-stride",
        str(video_stride),
        "--video-fps",
        str(video_fps),
        "--out-dir",
        str(cell_dir),
        "--manifest",
        str(cell_manifest),
    ]


def _summarize_cell(cell: dict[str, Any], out_root: Path, returncode: int) -> dict[str, Any]:
    cell_dir = out_root / cell["cell_id"]
    summary_path = cell_dir / "runtime_smoke_summary.json"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {"parse_error": True}
    classification = summary.get("classification") or {}
    if isinstance(classification, dict):
        class_name = classification.get("classification")
    else:
        class_name = classification
    return {
        "cell_id": cell["cell_id"],
        "look_id": cell["look_id"],
        "particle_limit": cell["particle_limit"],
        "steps_requested": cell["steps"],
        "steps_completed": summary.get("steps"),
        "classification": class_name,
        "returncode": returncode,
        "presentation_look_preset": summary.get("presentation_look_preset", cell["look_id"]),
        "presentation_water_backend": (summary.get("presentation_material") or {}).get("material_backend"),
        "official_visual_a_compatible": summary.get("official_visual_a_compatible", False),
        "official_visual_a_claim_allowed": summary.get("official_visual_a_claim_allowed", False),
        "artifact_dir": str(cell_dir),
        "video_path": ((summary.get("videos") or {}).get("presentation_isosurface") or {}).get("path"),
        "human_visual_qa_status": "pending",
    }


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    cells_out: list[dict[str, Any]] = []
    for cell in MATRIX_CELLS:
        if args.only_cell and cell["cell_id"] != args.only_cell:
            continue
        cmd = _cell_cmd(
            isaac_python=Path(args.isaac_python),
            runner=Path(args.runner),
            cell=cell,
            out_root=out_root,
            video_stride=args.video_stride,
            video_fps=args.video_fps,
        )
        env = os.environ.copy()
        env.setdefault("ACCEPT_EULA", "Y")
        env.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
        print("RUN", " ".join(cmd), flush=True)
        if args.dry_run:
            cells_out.append({**cell, "dry_run": True, "human_visual_qa_status": "pending"})
            continue
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
        cells_out.append(_summarize_cell(cell, out_root, proc.returncode))
    manifest = build_matrix_manifest(cells=cells_out)
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isaac-python", default=DEFAULT_ISAAC_PYTHON)
    parser.add_argument("--runner", default=str(DEFAULT_RUNNER))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--video-stride", type=int, default=1)
    parser.add_argument("--video-fps", type=float, default=8.0)
    parser.add_argument("--only-cell", default=None, choices=[c["cell_id"] for c in MATRIX_CELLS])
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    run_matrix(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

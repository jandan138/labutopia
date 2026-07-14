"""Dual-render Isaac smoke cells for fluid recipe A2+B2 (leadership = particle_omniglass)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_recipe import (
    PRESENTATION_RENDER_MODE_ISOSURFACE,
    PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS,
    RECIPE_DEFAULT_PARTICLE_COUNT,
    build_fluid_recipe_claim_boundary,
    recipe_usd_path,
    source_usd_path,
)

DEFAULT_OUT_ROOT = (
    REPO_ROOT
    / "docs"
    / "labutopia_lab_poc"
    / "evidence_manifests"
    / "fluid_spike_fluid_recipe_dual_render_20260710_v1"
)
VIDEO_RUNNER = REPO_ROOT / "tools" / "labutopia_fluid" / "run_colleague_native_usd_completed_pbd_step_video.py"
ISAAC_PY = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)


def dual_render_cells(
    *,
    particle_count: int = RECIPE_DEFAULT_PARTICLE_COUNT,
) -> list[dict[str, Any]]:
    return [
        {
            "cell_id": f"RECIPE_P{particle_count}_OMNIGLASS",
            "presentation_render_mode": PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS,
            "leadership_default": True,
            "particle_count": int(particle_count),
        },
        {
            "cell_id": f"RECIPE_P{particle_count}_ISOSURFACE",
            "presentation_render_mode": PRESENTATION_RENDER_MODE_ISOSURFACE,
            "leadership_default": False,
            "particle_count": int(particle_count),
        },
    ]


def build_cell_argv(
    cell: dict[str, Any],
    *,
    usd: Path,
    out_dir: Path,
    steps: int = 120,
    look_preset: str = "weekly_omniglass_B",
) -> list[str]:
    return [
        str(VIDEO_RUNNER),
        "--usd",
        str(usd),
        "--out-dir",
        str(out_dir),
        "--manifest",
        str(out_dir / "summary.json"),
        "--fluid-safe-wrapper-overlay",
        "--presentation-look-preset",
        look_preset,
        "--presentation-render-mode",
        str(cell["presentation_render_mode"]),
        "--controlled-spawn-count",
        str(int(cell["particle_count"])),
        "--controlled-spawn-seed",
        "0",
        "--particle-limit",
        "0",
        "--steps",
        str(int(steps)),
        "--video-stride",
        "4",
        "--headless",
        "--hard-exit-after-run",
        "--disable-particle-debug-display",
    ]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--particle-count", type=int, default=RECIPE_DEFAULT_PARTICLE_COUNT)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument(
        "--usd",
        default="",
        help="USD path (default: recipe USD if present else source USD).",
    )
    parser.add_argument("--isaac-python", default=str(ISAAC_PY))
    parser.add_argument("--dry-plan", action="store_true")
    parser.add_argument("--cells", default="all", help="all|omniglass|isosurface")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cells = dual_render_cells(particle_count=args.particle_count)
    if args.cells == "omniglass":
        cells = [c for c in cells if c["leadership_default"]]
    elif args.cells == "isosurface":
        cells = [c for c in cells if not c["leadership_default"]]

    recipe = recipe_usd_path(REPO_ROOT)
    usd = Path(args.usd) if args.usd else (recipe if recipe.is_file() else source_usd_path(REPO_ROOT))
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    plan = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_fluid_recipe_dual_render",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "usd": str(usd),
        "particle_count": int(args.particle_count),
        "cells": cells,
        "claim_boundary": build_fluid_recipe_claim_boundary(),
        "leadership_default_mode": PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS,
    }
    (out_root / "dual_render_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    if args.dry_plan:
        print(json.dumps(plan, indent=2))
        return 0

    results: list[dict[str, Any]] = []
    for cell in cells:
        cell_dir = out_root / cell["cell_id"]
        cell_dir.mkdir(parents=True, exist_ok=True)
        cmd = [str(args.isaac_python), *build_cell_argv(cell, usd=usd, out_dir=cell_dir, steps=args.steps)]
        print("RUN", " ".join(cmd), flush=True)
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
        summary_path = cell_dir / "summary.json"
        summary: dict[str, Any] = {}
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        results.append(
            {
                "cell_id": cell["cell_id"],
                "leadership_default": cell["leadership_default"],
                "presentation_render_mode": cell["presentation_render_mode"],
                "exit_code": proc.returncode,
                "presentation_isosurface_enabled": summary.get("presentation_isosurface_enabled"),
                "classification": (summary.get("classification") or {}).get("status")
                or (summary.get("classification") or {}).get("classification"),
                "selected_particle_count": summary.get("selected_particle_count"),
                "videos": summary.get("videos"),
                "summary_path": str(summary_path) if summary_path.is_file() else None,
            }
        )

    top = {
        **plan,
        "results": results,
        "leadership_look_candidate_recorded": any(
            r.get("leadership_default") and r.get("exit_code") == 0 for r in results
        ),
    }
    (out_root / "dual_render_manifest.json").write_text(json.dumps(top, indent=2), encoding="utf-8")
    print(json.dumps(top, indent=2))
    return 0 if all(r.get("exit_code") == 0 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared source closure for opt-in, same-process main.py runtime attestation."""

from __future__ import annotations

from pathlib import Path


MAIN_RUNTIME_SOURCE_RELATIVE_PATHS = (
    "main.py",
    "controllers/pour_controller.py",
    "controllers/atomic_actions/pick_controller.py",
    "controllers/atomic_actions/pour_controller.py",
    "utils/fluid_evaluation_loop.py",
    "utils/isaac_fluid_evaluation.py",
    "tools/labutopia_fluid/main_runtime_attestation_sources.py",
)


def main_runtime_source_paths(
    *,
    repo_root: Path,
    attester_path: Path,
) -> tuple[Path, ...]:
    root = Path(repo_root).resolve()
    paths = [Path(attester_path).resolve()]
    for relative_path in MAIN_RUNTIME_SOURCE_RELATIVE_PATHS:
        path = (root / relative_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"main_runtime_attestation_source_missing:{path}")
        paths.append(path)
    return tuple(paths)

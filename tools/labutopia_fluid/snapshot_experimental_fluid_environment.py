#!/usr/bin/env python3
"""Write reproducibility locks for one installed experimental fluid lane."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _command(arguments: list[str]) -> str:
    completed = subprocess.run(
        arguments,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def snapshot(output_dir: Path) -> dict[str, Any]:
    prefix = Path(sys.prefix).resolve(strict=True)
    executable = Path(sys.executable).absolute()
    if executable != prefix / "bin/python":
        raise RuntimeError(f"absolute_environment_python_required:{executable}")
    conda_meta = prefix / "conda-meta"
    if not conda_meta.is_dir():
        raise RuntimeError("conda_meta_missing")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output_dir_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    conda_records = []
    explicit_lines = ["@EXPLICIT"]
    for record_path in sorted(conda_meta.glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        url = record.get("url")
        sha256 = record.get("sha256")
        if not isinstance(url, str) or not isinstance(sha256, str):
            raise RuntimeError(f"conda_record_source_hash_missing:{record_path}")
        explicit_lines.append(f"{url}#sha256={sha256}")
        conda_records.append(
            {
                "name": record.get("name"),
                "version": record.get("version"),
                "build": record.get("build"),
                "url": url,
                "sha256": sha256,
                "record_sha256": _sha256(record_path),
            }
        )
    explicit_path = output_dir / "conda-explicit.txt"
    _atomic_text(explicit_path, "\n".join(explicit_lines) + "\n")

    freeze_path = output_dir / "pip-freeze-all.txt"
    _atomic_text(
        freeze_path,
        _command([str(executable), "-m", "pip", "freeze", "--all"]),
    )
    inspect_path = output_dir / "pip-inspect.json"
    _atomic_text(
        inspect_path,
        _command([str(executable), "-m", "pip", "inspect", "--local"]),
    )

    distributions = []
    for distribution in importlib.metadata.distributions():
        record_path = Path(distribution._path) / "RECORD"  # type: ignore[attr-defined]
        direct_url_path = Path(distribution._path) / "direct_url.json"  # type: ignore[attr-defined]
        distributions.append(
            {
                "name": distribution.metadata.get("Name"),
                "version": distribution.version,
                "record_path": str(record_path) if record_path.is_file() else None,
                "record_sha256": _sha256(record_path) if record_path.is_file() else None,
                "direct_url": (
                    json.loads(direct_url_path.read_text(encoding="utf-8"))
                    if direct_url_path.is_file()
                    else None
                ),
            }
        )
    distributions.sort(key=lambda item: str(item["name"]).lower())
    manifest = {
        "schema": "labutopia.experimental_fluid_environment_lock.v1",
        "claim_boundary": "experimental_lane_only_not_formal_isaac41_evidence",
        "executable": str(executable),
        "prefix": str(prefix),
        "python": sys.version,
        "conda_packages": conda_records,
        "pip_distributions": distributions,
        "artifacts": {
            "conda_explicit": {
                "path": str(explicit_path),
                "sha256": _sha256(explicit_path),
            },
            "pip_freeze_all": {
                "path": str(freeze_path),
                "sha256": _sha256(freeze_path),
            },
            "pip_inspect": {
                "path": str(inspect_path),
                "sha256": _sha256(inspect_path),
            },
        },
    }
    manifest_path = output_dir / "environment-lock.json"
    _atomic_text(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    result = {
        "status": "passed",
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
    }
    print(json.dumps(result, sort_keys=True))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    snapshot(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

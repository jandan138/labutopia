#!/usr/bin/env python3
"""Attest Isaac 6.0.1 and run WCSPH in the same sealed Kit process."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_fresh_json(path: Path, value: Mapping[str, Any]) -> None:
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


def _lock_record(path: Path) -> dict[str, Any]:
    manifest_path = path.resolve(strict=True)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if value.get("schema") != "labutopia.experimental_fluid_environment_lock.v1":
        raise RuntimeError("environment_lock_schema_mismatch")
    if Path(str(value.get("prefix", ""))).resolve(strict=True) != Path(sys.prefix).resolve(strict=True):
        raise RuntimeError("environment_lock_prefix_mismatch")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise RuntimeError("environment_lock_artifacts_missing")
    verified = {}
    for name in ("conda_explicit", "pip_freeze_all", "pip_inspect"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise RuntimeError(f"environment_lock_artifact_missing:{name}")
        artifact = Path(str(record.get("path", ""))).resolve(strict=True)
        actual = _sha256_file(artifact)
        if actual != record.get("sha256"):
            raise RuntimeError(f"environment_lock_artifact_hash_mismatch:{name}")
        verified[name] = {"path": str(artifact), "sha256": actual}
    return {
        "path": str(manifest_path),
        "sha256": _sha256_file(manifest_path),
        "artifacts": verified,
    }


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
    application = None
    try:
        from tools.labutopia_fluid import attest_experimental_fluid_runtime as attestation

        receipt = attestation._base_receipt("isaacsim601_wcsph_r1")
        driver = attestation._isaac_driver_preflight()
        receipt["driver_preflight"] = driver
        application = attestation._attest_isaac(receipt)
        receipt["capabilities"] = {
            "physics": {
                "status": "passed",
                "claim": "isaac_kit_newton_warp_wcsph_usd_points_same_process",
            },
            "rtx": {
                "status": "passed" if driver["isaac601_rtx_supported"] else "blocked_driver",
                "blocker": None if driver["isaac601_rtx_supported"] else "isaac601_rtx_driver_unsupported",
            },
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
                "--host-runtime-update",
                "isaac_kit_particles",
            ]
        )
    except BaseException as error:
        failure = {
            "schema": "labutopia.isaac601_wcsph_child_failure.v1",
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
    finally:
        if application is not None:
            application.close()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Seal a static NO-GO preflight for the real PBD grasp v2 fixture.

This is intentionally not a physics runner.  It reads the composed USD's
authored fixture facts and emits a rejected G0 artifact because static USD
inspection cannot certify cooked runtime geometry or a signed swept clearance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_ASSET = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
SOURCE_PATH = "/World/beaker2"
PARTICLE_PATH = "/World/InternDataParityFluid/Particles"
WRAPPER_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
EXPECTED_WRAPPER_COLLIDER_COUNT = 145
REPORT_BASENAME = "report.json"
G0_ARTIFACT_BASENAME = "g0_stage_artifact.json"


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def usd_dependency_closure(asset_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Hash every resolved USD layer used by the static composed stage."""

    from pxr import Usd

    asset = Path(asset_path).resolve()
    stage = Usd.Stage.Open(str(asset))
    if stage is None:
        raise RuntimeError(f"real_pbd_preflight_stage_open_failed:{asset}")
    layers = []
    for layer in stage.GetUsedLayers():
        real_path = Path(layer.realPath).resolve() if layer.realPath else None
        if real_path is None and bool(getattr(layer, "anonymous", False)):
            # USD creates an empty session layer for Stage.Open; it is not an
            # authored dependency and must not make static identity unstable.
            continue
        if real_path is None or not real_path.is_file():
            raise RuntimeError(
                f"real_pbd_preflight_dependency_unresolved:{layer.identifier}"
            )
        layers.append(
            {
                "identifier": str(layer.identifier),
                "real_path": str(real_path),
                "sha256": sha256_file(real_path),
            }
        )
    payload = {"layers": sorted(layers, key=lambda item: item["real_path"])}
    return {
        "usd_dependency_closure_sha256": hashlib.sha256(
            _canonical_json_bytes(payload)
        ).hexdigest(),
        "usd_dependency_layers": payload["layers"],
    }


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def atomic_create_bytes(path: str | os.PathLike[str], payload: bytes) -> None:
    """Publish a file without replacing an existing result."""

    output = Path(path)
    if output.exists():
        raise FileExistsError(f"real_pbd_preflight_output_exists:{output}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise FileExistsError(
                f"real_pbd_preflight_output_exists:{output}"
            ) from exc
        directory_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _finite_nonnegative(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"real_pbd_preflight_{field}_invalid")
    result = float(value)
    if not result >= 0.0 or result == float("inf"):
        raise ValueError(f"real_pbd_preflight_{field}_invalid")
    return result


def read_static_fixture(asset_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read authored source, particle, and wrapper facts without starting physics."""

    from pxr import Usd, UsdPhysics

    asset = Path(asset_path).resolve()
    stage = Usd.Stage.Open(str(asset))
    if stage is None:
        raise RuntimeError(f"real_pbd_preflight_stage_open_failed:{asset}")
    source = stage.GetPrimAtPath(SOURCE_PATH)
    particles = stage.GetPrimAtPath(PARTICLE_PATH)
    wrapper = stage.GetPrimAtPath(WRAPPER_PATH)
    if not source or not particles or not wrapper:
        raise RuntimeError("real_pbd_preflight_required_prim_missing")

    def attribute(prim: Any, name: str) -> Any:
        value = prim.GetAttribute(name)
        if not value or not value.IsValid():
            raise RuntimeError(f"real_pbd_preflight_attribute_missing:{name}")
        return value.Get()

    source_mass = _finite_nonnegative(
        attribute(source, "physics:mass"), field="source_mass"
    )
    particle_density = _finite_nonnegative(
        attribute(particles, "physics:density"), field="particle_density"
    )
    particle_mass = _finite_nonnegative(
        attribute(particles, "physics:mass"), field="particle_mass"
    )
    points = attribute(particles, "points")
    try:
        particle_count = len(points)
    except TypeError as exc:
        raise RuntimeError("real_pbd_preflight_particle_points_invalid") from exc
    if particle_count <= 0:
        raise RuntimeError("real_pbd_preflight_particle_points_invalid")
    wrapper_colliders = []
    for prim in Usd.PrimRange(wrapper):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = prim.GetAttribute("physics:collisionEnabled")
        if enabled and enabled.Get() is False:
            continue
        wrapper_colliders.append(str(prim.GetPath()))
    return {
        "source_dry_mass_kg": source_mass,
        "particle_density_kg_m3": particle_density,
        "particle_mass_kg": particle_mass,
        "particle_count": particle_count,
        "wrapper_collider_count": len(wrapper_colliders),
        "wrapper_collider_paths": sorted(wrapper_colliders),
    }


def build_static_preflight_report(
    *,
    asset_path: str | os.PathLike[str],
    fixture: Mapping[str, Any],
    dependency_closure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from utils.real_pbd_grasp_v2 import evaluate_static_pbd_fixture_preflight

    asset = Path(asset_path).resolve()
    asset_sha256 = sha256_file(asset)
    closure = (
        dict(dependency_closure)
        if dependency_closure is not None
        else usd_dependency_closure(asset)
    )
    closure_sha256 = closure.get("usd_dependency_closure_sha256")
    if not isinstance(closure_sha256, str) or len(closure_sha256) != 64:
        raise ValueError("real_pbd_preflight_dependency_closure_invalid")
    evaluation = evaluate_static_pbd_fixture_preflight(
        fixture={
            "fixture_identity_sha256": closure_sha256,
            **dict(fixture),
            "expected_wrapper_collider_count": EXPECTED_WRAPPER_COLLIDER_COUNT,
            "runtime_cooked_geometry_available": False,
            "runtime_stable_particle_ids_available": False,
        }
    )
    return {
        "authority": "real_pbd_static_fixture_preflight_report_v1",
        "asset_path": str(asset),
        "asset_sha256": asset_sha256,
        **closure,
        "static_fixture": dict(fixture),
        "evaluation": evaluation,
    }


def run_preflight(*, asset_path: Path, out_dir: Path) -> int:
    from utils.controlled_contact import canonical_json_sha256
    from utils.real_pbd_grasp_v2 import (
        build_stage_artifact,
        build_stage_evidence,
        serialize_stage_artifact,
    )

    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return 2
    try:
        closure_before = usd_dependency_closure(asset_path)
        fixture = read_static_fixture(asset_path)
        closure_after = usd_dependency_closure(asset_path)
        if closure_before != closure_after:
            raise RuntimeError("real_pbd_preflight_dependency_closure_changed")
        report = build_static_preflight_report(
            asset_path=asset_path,
            fixture=fixture,
            dependency_closure=closure_before,
        )
        report_payload = {
            **report,
            "report_sha256": canonical_json_sha256(report),
        }
        artifact = build_stage_artifact(
            stage="G0",
            decision="G0_NO_GO",
            run_id=secrets.token_hex(16),
            reset_epoch=0,
            fixture_identity_sha256=report_payload["usd_dependency_closure_sha256"],
            treatment_sha256=report_payload["usd_dependency_closure_sha256"],
            stage_evidence=build_stage_evidence(
                stage="G0",
                decision="G0_NO_GO",
                fixture_identity_sha256=report_payload["usd_dependency_closure_sha256"],
                treatment_sha256=report_payload["usd_dependency_closure_sha256"],
                source_evidence=report_payload,
            ),
            input_closure_sha256=canonical_json_sha256(
                {
                    "asset_path": report_payload["asset_path"],
                    "asset_sha256": report_payload["asset_sha256"],
                    "usd_dependency_closure_sha256": report_payload[
                        "usd_dependency_closure_sha256"
                    ],
                }
            ),
            forbidden_frozen_v6_input_count=0,
            predecessor_byte_hashes={},
        )
        atomic_create_bytes(
            out_dir / REPORT_BASENAME, _canonical_json_bytes(report_payload)
        )
        atomic_create_bytes(
            out_dir / G0_ARTIFACT_BASENAME,
            serialize_stage_artifact(artifact),
        )
    except BaseException as exc:
        resolved_asset = Path(asset_path).resolve()
        try:
            fixture_identity_sha256 = sha256_file(resolved_asset)
        except OSError:
            fixture_identity_sha256 = canonical_json_sha256(
                {"unavailable_asset_path": str(resolved_asset)}
            )
        error = {
            "authority": "real_pbd_static_fixture_preflight_error_v1",
            "decision": "G0_NO_GO",
            "asset_path": str(resolved_asset),
            "asset_sha256": fixture_identity_sha256,
            "error": f"{type(exc).__name__}:{exc}",
        }
        try:
            error_payload = {
                **error,
                "report_sha256": canonical_json_sha256(error),
            }
            artifact = build_stage_artifact(
                stage="G0",
                decision="G0_NO_GO",
                run_id=secrets.token_hex(16),
                reset_epoch=0,
                fixture_identity_sha256=fixture_identity_sha256,
                treatment_sha256=fixture_identity_sha256,
                stage_evidence=build_stage_evidence(
                    stage="G0",
                    decision="G0_NO_GO",
                    fixture_identity_sha256=fixture_identity_sha256,
                    treatment_sha256=fixture_identity_sha256,
                    source_evidence=error_payload,
                ),
                input_closure_sha256=canonical_json_sha256(
                    {
                        "asset_path": str(resolved_asset),
                        "asset_sha256": fixture_identity_sha256,
                    }
                ),
                forbidden_frozen_v6_input_count=0,
                predecessor_byte_hashes={},
            )
            atomic_create_bytes(
                out_dir / REPORT_BASENAME, _canonical_json_bytes(error_payload)
            )
            atomic_create_bytes(
                out_dir / G0_ARTIFACT_BASENAME,
                serialize_stage_artifact(artifact),
            )
        except FileExistsError:
            pass
        return 2
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, default=DEFAULT_ASSET)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    args.asset = args.asset.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.asset.is_file():
        parser.error(f"asset not found: {args.asset}")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_preflight(asset_path=args.asset, out_dir=args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only S0 USD particle/fluid schema scanner for LabUtopia assets."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PARTICLE_TYPE_NAMES = {"PhysxParticleSystem"}
PARTICLE_API_NAMES = {
    "PhysxParticleSetAPI",
    "PhysxPBDMaterialAPI",
    "PhysxParticleAnisotropyAPI",
    "PhysxParticleSmoothingAPI",
    "PhysxParticleIsosurfaceAPI",
}
PHYSICS_SCENE_TYPE_NAMES = {"PhysicsScene"}
COLLIDER_API_NAMES = {
    "PhysicsCollisionAPI",
    "PhysicsMeshCollisionAPI",
    "PhysicsRigidBodyAPI",
    "PhysicsMassAPI",
}
VESSEL_HINTS = (
    "beaker",
    "bottle",
    "cylinder",
    "cup",
    "flask",
    "glass",
    "target",
    "table",
    "ground",
    "cube",
)


def _load_pxr() -> tuple[Any, Any, str | None]:
    try:
        from pxr import Sdf, Usd  # type: ignore

        return Sdf, Usd, None
    except Exception as exc:  # pragma: no cover - exercised only in missing-env cases.
        return None, None, f"{type(exc).__name__}: {exc}"


SDF, USD, PXR_IMPORT_ERROR = _load_pxr()


def _json_value(value: Any, *, max_items: int = 8) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "pathString"):
        return value.pathString
    if hasattr(value, "assetPath"):
        return value.assetPath
    if isinstance(value, (list, tuple)):
        return [_json_value(v, max_items=max_items) for v in list(value)[:max_items]]
    if hasattr(value, "__len__") and not isinstance(value, dict):
        try:
            length = len(value)
        except Exception:
            length = None
        if length is not None and not isinstance(value, (str, bytes)):
            preview = []
            try:
                preview = [_json_value(value[i], max_items=max_items) for i in range(min(length, max_items))]
            except Exception:
                preview = []
            return {"len": length, "preview": preview}
    return str(value)


def _attr_value(prim: Any, attr_name: str) -> Any:
    attr = prim.GetAttribute(attr_name)
    if not attr:
        return None
    try:
        return _json_value(attr.Get())
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _attr_len(prim: Any, attr_name: str) -> int | None:
    attr = prim.GetAttribute(attr_name)
    if not attr:
        return None
    try:
        value = attr.Get()
        return len(value) if value is not None and hasattr(value, "__len__") else None
    except Exception:
        return None


def _relationship_targets(prim: Any, rel_name: str) -> list[str]:
    rel = prim.GetRelationship(rel_name)
    if not rel:
        return []
    try:
        return [str(target) for target in rel.GetTargets()]
    except Exception:
        return []


def _property_names(prim: Any) -> list[str]:
    try:
        return list(prim.GetPropertyNames())
    except Exception:
        return []


def _selected_attributes(prim: Any, prefixes: tuple[str, ...]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for name in _property_names(prim):
        if any(name.startswith(prefix) for prefix in prefixes):
            attr = prim.GetAttribute(name)
            if attr:
                selected[name] = _attr_value(prim, name)
    return selected


def _material_bindings(prim: Any) -> list[str]:
    targets: list[str] = []
    for rel_name in ("material:binding", "material:binding:full", "material:binding:preview"):
        targets.extend(_relationship_targets(prim, rel_name))
    return sorted(set(targets))


def _looks_like_particle_set(prim: Any, applied_schemas: list[str]) -> bool:
    properties = _property_names(prim)
    return (
        "PhysxParticleSetAPI" in applied_schemas
        or bool(_relationship_targets(prim, "physxParticle:particleSystem"))
        or any(name.startswith("physxParticle:") for name in properties)
    )


def _looks_like_sampling_prim(prim: Any) -> bool:
    return any(name.startswith("physxParticleSampling:") for name in _property_names(prim))


def _looks_like_collider(prim: Any, applied_schemas: list[str]) -> bool:
    return bool(COLLIDER_API_NAMES.intersection(applied_schemas))


def _is_candidate_vessel(path: str, applied_schemas: list[str]) -> bool:
    lowered = path.lower()
    return _looks_like_collider_path(lowered) and bool(COLLIDER_API_NAMES.intersection(applied_schemas))


def _looks_like_collider_path(lowered_path: str) -> bool:
    return any(hint in lowered_path for hint in VESSEL_HINTS)


def _prim_summary(prim: Any, applied_schemas: list[str]) -> dict[str, Any]:
    return {
        "path": str(prim.GetPath()),
        "type_name": str(prim.GetTypeName()),
        "applied_schemas": applied_schemas,
    }


def inspect_usd(usd_path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = os.path.relpath(usd_path, repo_root)
    result: dict[str, Any] = {
        "usd_path": rel_path,
        "abs_path": str(usd_path),
        "exists": usd_path.exists(),
        "particle_systems": [],
        "particle_sets": [],
        "particle_materials": [],
        "particle_sampling_prims": [],
        "physics_scenes": [],
        "candidate_beaker_colliders": [],
        "collider_count": 0,
        "schema_preserved": False,
        "errors": [],
    }
    if PXR_IMPORT_ERROR:
        result["errors"].append({"stage": "import_pxr", "message": PXR_IMPORT_ERROR})
        return result
    if not usd_path.exists():
        result["errors"].append({"stage": "open", "message": "file not found"})
        return result

    try:
        stage = USD.Stage.Open(str(usd_path))
    except Exception as exc:
        result["errors"].append({"stage": "open", "message": f"{type(exc).__name__}: {exc}"})
        return result
    if stage is None:
        result["errors"].append({"stage": "open", "message": "Usd.Stage.Open returned None"})
        return result

    result["schema_preserved"] = True
    result["root_layer"] = stage.GetRootLayer().identifier
    result["used_layer_count"] = len(stage.GetUsedLayers())

    for prim in stage.TraverseAll():
        if not prim.IsValid():
            continue
        path = str(prim.GetPath())
        type_name = str(prim.GetTypeName())
        applied_schemas = [str(schema) for schema in prim.GetAppliedSchemas()]
        base = _prim_summary(prim, applied_schemas)

        if type_name in PARTICLE_TYPE_NAMES:
            particle_system = dict(base)
            particle_system["material_bindings"] = _material_bindings(prim)
            particle_system["attributes"] = _selected_attributes(
                prim,
                (
                    "particle",
                    "physxParticle",
                    "physxParticleAnisotropy",
                    "physxParticleSmoothing",
                    "physxParticleIsosurface",
                ),
            )
            result["particle_systems"].append(particle_system)

        if _looks_like_particle_set(prim, applied_schemas):
            particle_set = dict(base)
            particle_set["particle_system_targets"] = _relationship_targets(prim, "physxParticle:particleSystem")
            particle_set["material_bindings"] = _material_bindings(prim)
            particle_set["points_len"] = _attr_len(prim, "points")
            particle_set["velocities_len"] = _attr_len(prim, "velocities")
            particle_set["widths_len"] = _attr_len(prim, "widths")
            particle_set["attributes"] = _selected_attributes(prim, ("physxParticle:", "physics:"))
            result["particle_sets"].append(particle_set)

        if "PhysxPBDMaterialAPI" in applied_schemas or any(
            name.startswith("physxPBDMaterial:") for name in _property_names(prim)
        ):
            material = dict(base)
            material["attributes"] = _selected_attributes(prim, ("physxPBDMaterial:",))
            result["particle_materials"].append(material)

        if _looks_like_sampling_prim(prim):
            sampler = dict(base)
            sampler["attributes"] = _selected_attributes(prim, ("physxParticleSampling:",))
            sampler["particle_targets"] = _relationship_targets(prim, "physxParticleSampling:particles")
            result["particle_sampling_prims"].append(sampler)

        if type_name in PHYSICS_SCENE_TYPE_NAMES:
            scene = dict(base)
            scene["attributes"] = _selected_attributes(prim, ("physics:", "physxScene:"))
            result["physics_scenes"].append(scene)

        if _looks_like_collider(prim, applied_schemas):
            result["collider_count"] += 1
            if _is_candidate_vessel(path, applied_schemas):
                collider = dict(base)
                collider["material_bindings"] = _material_bindings(prim)
                collider["attributes"] = _selected_attributes(
                    prim,
                    ("physics:", "physxCollision:", "physxMeshCollision:"),
                )
                result["candidate_beaker_colliders"].append(collider)

    return result


def _import_probe_code() -> str:
    return r"""
import json, sys
result = {"python": sys.executable, "imports_without_app": {}}
for name in ["isaacsim", "isaacsim.core.api", "isaacsim.core.prims", "pxr", "pxr.Usd", "pxr.PhysxSchema", "omni.physx"]:
    try:
        mod = __import__(name, fromlist=["*"])
        result["imports_without_app"][name] = {"ok": True, "file": getattr(mod, "__file__", None)}
    except Exception as exc:
        result["imports_without_app"][name] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
print(json.dumps(result, sort_keys=True))
"""


def run_import_probe(python_executable: str) -> dict[str, Any]:
    env = os.environ.copy()
    env.update({"ACCEPT_EULA": "Y", "OMNI_KIT_ACCEPT_EULA": "YES", "PYTHONNOUSERSITE": "1"})
    try:
        proc = subprocess.run(
            [python_executable, "-c", _import_probe_code()],
            check=False,
            capture_output=True,
            env=env,
            text=True,
            timeout=45,
        )
    except Exception as exc:
        return {
            "python": python_executable,
            "probe_error": f"{type(exc).__name__}: {exc}",
        }
    stdout = proc.stdout.strip()
    parsed: dict[str, Any]
    try:
        parsed = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except Exception:
        parsed = {"raw_stdout_tail": stdout[-1000:]}
    parsed["exit_code"] = proc.returncode
    parsed["stderr_tail"] = proc.stderr[-2000:]
    return parsed


def build_report(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_schema_probe",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "scanner": "tools/labutopia_fluid/inspect_usd_particles.py",
        "host": {
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "usd_results": [],
        "runtime_import_probes": [],
        "summary": {},
    }
    for usd_arg in args.usd:
        report["usd_results"].append(inspect_usd((repo_root / usd_arg).resolve(), repo_root))

    for python_arg in args.runtime_python:
        report["runtime_import_probes"].append(run_import_probe(python_arg))

    particle_template_paths = [
        r["usd_path"]
        for r in report["usd_results"]
        if r.get("particle_systems") or r.get("particle_sets")
    ]
    no_particle_paths = [
        r["usd_path"]
        for r in report["usd_results"]
        if not r.get("particle_systems") and not r.get("particle_sets")
    ]
    report["summary"] = {
        "usd_count": len(report["usd_results"]),
        "usd_paths_with_particle_schema": particle_template_paths,
        "usd_paths_without_particle_schema": no_particle_paths,
        "particle_system_count": sum(len(r.get("particle_systems", [])) for r in report["usd_results"]),
        "particle_set_count": sum(len(r.get("particle_sets", [])) for r in report["usd_results"]),
        "particle_material_count": sum(len(r.get("particle_materials", [])) for r in report["usd_results"]),
        "physics_scene_count": sum(len(r.get("physics_scenes", [])) for r in report["usd_results"]),
        "candidate_collider_count": sum(len(r.get("candidate_beaker_colliders", [])) for r in report["usd_results"]),
        "all_stages_opened": all(r.get("schema_preserved") for r in report["usd_results"]),
    }
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", action="append", required=True, help="USD path relative to repo root.")
    parser.add_argument("--out", required=True, help="JSON output path relative to repo root.")
    parser.add_argument(
        "--runtime-python",
        action="append",
        default=[],
        help="Optional Python executable for import-only Isaac/PhysX schema probing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    report = build_report(args, repo_root)
    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary = report["summary"]
    print(
        "S0 schema probe: "
        f"usd={summary['usd_count']} "
        f"particle_systems={summary['particle_system_count']} "
        f"particle_sets={summary['particle_set_count']} "
        f"physics_scenes={summary['physics_scene_count']} "
        f"out={out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

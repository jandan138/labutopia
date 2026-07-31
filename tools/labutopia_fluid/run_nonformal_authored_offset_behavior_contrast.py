#!/usr/bin/env python3
"""Compare cube-only and finite-offset-package close-only contact behavior.

Both cells are fresh sealed Isaac children. This diagnostic compares whole
treatments only; it cannot resolve native offsets or authorize clearance, G0,
or Phase 3.
"""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import time
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import run_nonformal_pbd_direct_contact_probe as direct_probe
from utils import nonformal_authored_offset_behavior_contrast as contrast
from utils import nonformal_usd_dependency_resolution as dependency_resolution


FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
DEFAULT_CONFIG = direct_probe.DEFAULT_CONFIG
HIDDEN_CUBE_OVERLAY = direct_probe.HIDDEN_CUBE_OVERLAY
FINITE_TARGET_OFFSET_OVERLAY = direct_probe.FINITE_TARGET_OFFSET_OVERLAY
AUTHORITY = "nonauthorizing_authored_offset_behavior_contrast_runner_v1"
CLASSIFICATION = contrast.CLASSIFICATION
REQUEST_BASENAME = "behavior_contrast_request.json"
OBSERVATION_BASENAME = "behavior_contrast_observation.json"
REPORT_BASENAME = "report.json"
MANIFEST_BASENAME = "run_manifest.json"
CELL_REPORT_BASENAME = "cell_report.json"
DIRECT_REPORT_BASENAME = "direct_contact_report.json"
RUNTIME_RECEIPT_BASENAME = "runtime_receipt.json"
EXECUTION_REQUEST_BASENAME = "execution_request.json"
STDOUT_BASENAME = "child.stdout.log"
STDERR_BASENAME = "child.stderr.log"
DEFAULT_SEED = 20260730
DEFAULT_MAX_CONTROL_STEPS = 600
FIXTURE_USD_CLOSURE_AUTHORITY = "nonauthorizing_authored_offset_behavior_fixture_usd_closure_v1"
STATIC_COMPOSITION_RUNNER = (
    REPO_ROOT / "tools/labutopia_fluid/run_nonformal_authored_offset_overlay_composition.py"
)
STATIC_PREFLIGHT_DIRNAME = "fixture_usd_composition_preflight"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return contrast.canonical_json_sha256(value)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_repo_regular(path: Path, *, field: str) -> Path:
    candidate = Path(path)
    if (
        candidate.is_symlink()
        or not candidate.is_file()
        or not candidate.is_relative_to(REPO_ROOT)
    ):
        raise ValueError(f"authored_offset_behavior_{field}_invalid")
    return candidate.resolve()


def _artifact(path: Path, *, field: str) -> dict[str, str]:
    regular = _require_repo_regular(path, field=field)
    return {"path": str(regular), "sha256": _sha256_file(regular)}


def _config_binding() -> dict[str, Any]:
    cfg, closure = direct_probe.load_composed_config(DEFAULT_CONFIG)
    config_path = _require_repo_regular(DEFAULT_CONFIG, field="config")
    asset_path = _require_repo_regular(
        REPO_ROOT / str(cfg.usd_path), field="asset"
    )
    robot_path = _require_repo_regular(
        REPO_ROOT / str(cfg.robot.usd_path), field="robot_asset"
    )
    normalized_closure = []
    for raw_path, digest in sorted(closure.items()):
        path = _require_repo_regular(Path(raw_path), field="config_closure")
        if not _is_sha256(digest) or _sha256_file(path) != digest:
            raise ValueError("authored_offset_behavior_config_closure_invalid")
        normalized_closure.append({"path": str(path), "sha256": digest})
    closure_payload = {"files": normalized_closure}
    physics_dt = float(cfg.online_fluid.physics_dt)
    if not math.isfinite(physics_dt) or physics_dt <= 0.0:
        raise ValueError("authored_offset_behavior_physics_dt_invalid")
    if getattr(cfg.online_fluid, "stop_after_pre_roll", None) is not False:
        raise ValueError("authored_offset_behavior_close_only_config_invalid")
    return {
        "config": {"path": str(config_path), "sha256": _sha256_file(config_path)},
        "config_closure": normalized_closure,
        "config_closure_sha256": _canonical_sha256(closure_payload),
        "asset": {"path": str(asset_path), "sha256": _sha256_file(asset_path)},
        "robot_asset": {"path": str(robot_path), "sha256": _sha256_file(robot_path)},
        "physics_dt_s": physics_dt,
    }


def _cell_profiles() -> list[dict[str, Any]]:
    cells = []
    for identifier, profile_id in (
        ("cube_only_baseline", "cube_only_baseline_v1"),
        ("cube_plus_finite_target_offsets", "finite_target_offsets_calibration_v2"),
    ):
        profile = direct_probe.resolve_treatment_profile(profile_id)
        cells.append(
            {
                "id": identifier,
                "profile": profile,
                "profile_sha256": _canonical_sha256(profile),
            }
        )
    return cells


def _internal_module_path(module: str) -> Path | None:
    root = module.split(".", 1)[0] if module else ""
    if root not in {
        "controllers",
        "data_collectors",
        "factories",
        "isaacsim_compat",
        "robots",
        "tasks",
        "tools",
        "utils",
    }:
        return None
    base = REPO_ROOT.joinpath(*module.split("."))
    candidate = base.with_suffix(".py")
    if candidate.is_file():
        return candidate
    package = base / "__init__.py"
    return package if package.is_file() else None


def _python_import_paths(seed_files: Sequence[str]) -> set[Path]:
    queue = [REPO_ROOT / relative for relative in seed_files]
    visited: set[Path] = set()
    while queue:
        path = queue.pop().resolve()
        if path in visited:
            continue
        _require_repo_regular(path, field="python_source")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError("authored_offset_behavior_python_source_invalid") from exc
        visited.add(path)
        package = path.relative_to(REPO_ROOT).with_suffix("").parts[:-1]
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    prefix = package[: max(0, len(package) - node.level + 1)]
                    suffix = tuple(node.module.split(".")) if node.module else ()
                    base = ".".join((*prefix, *suffix))
                else:
                    base = node.module or ""
                if base:
                    modules.append(base)
                    modules.extend(f"{base}.{alias.name}" for alias in node.names)
            for module in modules:
                candidate = _internal_module_path(module)
                if candidate is not None:
                    queue.append(candidate)
    return visited


def _source_paths_for(
    binding: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    fixture_usd_dependency_closure: Mapping[str, Any],
) -> tuple[Path, ...]:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation
    from tools.labutopia_fluid import run_nonformal_authored_offset_overlay_composition as static_runner

    seeds = (
        "tools/labutopia_fluid/run_nonformal_authored_offset_behavior_contrast.py",
        "tools/labutopia_fluid/run_nonformal_pbd_direct_contact_probe.py",
        "tools/labutopia_fluid/run_nonformal_authored_offset_overlay_composition.py",
        "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        "utils/nonformal_authored_offset_behavior_contrast.py",
    )
    paths = {
        *_python_import_paths(seeds),
        Path(attestation.__file__),
        Path(binding["config"]["path"]),
        *(Path(item["path"]) for item in binding["config_closure"]),
        Path(binding["asset"]["path"]),
        Path(binding["robot_asset"]["path"]),
        *(Path(item["real_path"]) for item in fixture_usd_dependency_closure["layers"]),
        *(
            Path(item["path"])
            for closure in fixture_usd_dependency_closure["resolved_usd_dependency_closures"].values()
            for item in closure["files"]
        ),
        *static_runner.source_paths(),
    }
    for cell in cells:
        paths.update(Path(item["path"]) for item in cell["profile"]["overlay_stack"])
    return tuple(sorted(_require_repo_regular(path, field="source_closure") for path in paths))


def _validate_fixture_usd_dependency_closure(
    value: Any,
    *,
    binding: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected = {
        "authority",
        "schema_version",
        "preflight",
        "layers",
        "closure_sha256",
        "resolved_usd_dependency_closures",
        "sha256",
    }
    expected = {
        "authority",
        "schema_version",
        "preflight",
        "layers",
        "closure_sha256",
        "resolved_usd_dependency_closures",
        "static_kit_profile",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if (
        value.get("authority") != FIXTURE_USD_CLOSURE_AUTHORITY
        or value.get("schema_version") != 1
        or not _is_sha256(value.get("closure_sha256"))
        or not _is_sha256(value.get("sha256"))
        or _canonical_sha256(payload) != value["sha256"]
    ):
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    preflight = value.get("preflight")
    if (
        not isinstance(preflight, Mapping)
        or set(preflight)
        != {
            "artifact_dir",
            "report_sha256",
            "manifest_sha256",
            "runtime_receipt_sha256",
            "observation_sha256",
            "execution_request_sha256",
            "source_identity_sha256",
        }
        or not isinstance(preflight.get("artifact_dir"), str)
        or not preflight["artifact_dir"]
        or Path(preflight["artifact_dir"]).is_absolute()
        or ".." in Path(preflight["artifact_dir"]).parts
        or any(
            not _is_sha256(preflight.get(name))
            for name in (
                "report_sha256",
                "manifest_sha256",
                "runtime_receipt_sha256",
                "observation_sha256",
                "execution_request_sha256",
                "source_identity_sha256",
            )
        )
    ):
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    raw_layers = value.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    normalized_layers = []
    seen_paths = set()
    profile_paths = {
        item["path"] for cell in cells for item in cell["profile"]["overlay_stack"]
    }
    for layer in raw_layers:
        if (
            not isinstance(layer, Mapping)
            or set(layer) != {"identifier", "real_path", "sha256"}
            or not isinstance(layer.get("identifier"), str)
            or not layer["identifier"]
            or not isinstance(layer.get("real_path"), str)
            or not _is_sha256(layer.get("sha256"))
        ):
            raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
        path = _require_repo_regular(Path(layer["real_path"]), field="fixture_usd_closure_layer")
        if str(path) != layer["real_path"] or layer["real_path"] in seen_paths:
            raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
        if _sha256_file(path) != layer["sha256"] or layer["real_path"] in profile_paths:
            raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
        seen_paths.add(layer["real_path"])
        normalized_layers.append(dict(layer))
    if normalized_layers != sorted(normalized_layers, key=lambda item: item["real_path"]):
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    if direct_probe._canonical_json_sha256({"layers": normalized_layers}) != value["closure_sha256"]:
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    expected_base_paths = {binding["asset"]["path"], binding["robot_asset"]["path"]}
    if not expected_base_paths <= seen_paths:
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    raw_resolved_dependency_closures = value.get("resolved_usd_dependency_closures")
    expected_profiles = {cell["profile"]["id"]: cell["profile"] for cell in cells}
    if (
        not isinstance(raw_resolved_dependency_closures, Mapping)
        or set(raw_resolved_dependency_closures) != set(expected_profiles)
    ):
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    approved_mdl_roots = {
        record["path"]: {
            "purpose": record["purpose"],
            "path": record["path"],
            "byte_count": Path(record["path"]).stat().st_size,
            "sha256": record["sha256"],
        }
        for record in dependency_resolution.APPROVED_RUNTIME_MDL_DEPENDENCIES
    }
    mdl_root = Path(next(iter(approved_mdl_roots))).parents[1]
    resolved_dependency_closures = {}
    for profile_id, profile in expected_profiles.items():
        expected_dependency_entries = [
            {"id": "fixture_asset", **binding["asset"]},
            {"id": "robot_asset", **binding["robot_asset"]},
            *(
                {"id": item["id"], "path": item["path"], "sha256": item["sha256"]}
                for item in profile["overlay_stack"]
            ),
        ]
        try:
            closure = dependency_resolution.validate(raw_resolved_dependency_closures[profile_id])
        except ValueError as exc:
            raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid") from exc
        if closure["entries"] != expected_dependency_entries or closure["unresolved"]:
            raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
        for record in closure["files"]:
            path = _require_repo_regular(Path(record["path"]), field="resolved_usd_dependency")
            if (
                str(path) != record["path"]
                or path.stat().st_size != record["byte_count"]
                or _sha256_file(path) != record["sha256"]
            ):
                raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
        observed_mdl_roots = {}
        for record in closure["runtime_mdl_files"]:
            path = Path(record["path"])
            if (
                not dependency_resolution._regular_file_under(path, mdl_root)
                or path.stat().st_size != record["byte_count"]
                or _sha256_file(path) != record["sha256"]
            ):
                raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
            if record["purpose"] == "kit_mdl_material_root":
                observed_mdl_roots[record["path"]] = dict(record)
        if observed_mdl_roots != approved_mdl_roots:
            raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
        resolved_dependency_closures[profile_id] = closure
    static_kit_profile = value.get("static_kit_profile")
    if (
        not isinstance(static_kit_profile, Mapping)
        or set(static_kit_profile) != {"path", "sha256", "pvd_extension_declared"}
        or static_kit_profile.get("pvd_extension_declared") is not False
        or not _is_sha256(static_kit_profile.get("sha256"))
    ):
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    profile_path = _require_repo_regular(Path(static_kit_profile["path"]), field="static_kit_profile")
    if _sha256_file(profile_path) != static_kit_profile["sha256"]:
        raise ValueError("authored_offset_behavior_fixture_usd_closure_invalid")
    return {
        "authority": FIXTURE_USD_CLOSURE_AUTHORITY,
        "schema_version": 1,
        "preflight": dict(preflight),
        "layers": normalized_layers,
        "closure_sha256": value["closure_sha256"],
        "resolved_usd_dependency_closures": resolved_dependency_closures,
        "static_kit_profile": dict(static_kit_profile),
        "sha256": value["sha256"],
    }


def source_paths(request: Mapping[str, Any]) -> tuple[Path, ...]:
    return _source_paths_for(
        request["binding"],
        request["cells"],
        request["fixture_usd_dependency_closure"],
    )


def build_contrast_request(
    *,
    fixture_usd_dependency_closure: Mapping[str, Any],
    binding: Mapping[str, Any] | None = None,
    cells: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    current_binding = _config_binding()
    current_cells = _cell_profiles()
    binding = current_binding if binding is None else dict(binding)
    cells = current_cells if cells is None else [dict(cell) for cell in cells]
    if binding != current_binding or cells != current_cells:
        raise RuntimeError("authored_offset_behavior_inputs_changed_after_preflight")
    fixture = _validate_fixture_usd_dependency_closure(
        fixture_usd_dependency_closure,
        binding=binding,
        cells=cells,
    )
    source_identity = attestation.capture_source_identity(_source_paths_for(binding, cells, fixture))
    source_identity_sha256 = attestation.canonical_json_sha256(source_identity)
    common = {
        "config_closure_sha256": binding["config_closure_sha256"],
        "asset_sha256": binding["asset"]["sha256"],
        "robot_asset_sha256": binding["robot_asset"]["sha256"],
        "source_identity_sha256": source_identity_sha256,
        "cube_only_profile_sha256": cells[0]["profile_sha256"],
        "finite_profile_sha256": cells[1]["profile_sha256"],
        "fixture_usd_dependency_closure_sha256": fixture["closure_sha256"],
        "cube_only_resolved_usd_dependency_closure_sha256": fixture[
            "resolved_usd_dependency_closures"
        ]["cube_only_baseline_v1"]["sha256"],
        "finite_resolved_usd_dependency_closure_sha256": fixture[
            "resolved_usd_dependency_closures"
        ]["finite_target_offsets_calibration_v2"]["sha256"],
        "fixture_usd_dependency_preflight_sha256": fixture["sha256"],
        "seed": DEFAULT_SEED,
        "max_control_steps": DEFAULT_MAX_CONTROL_STEPS,
        "physics_dt_s": binding["physics_dt_s"],
    }
    plan = contrast.build_plan(common)
    payload = {
        "authority": AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "binding": binding,
        "source_identity": source_identity,
        "source_identity_sha256": source_identity_sha256,
        "cells": cells,
        "fixture_usd_dependency_closure": fixture,
        "plan": plan,
        "plan_sha256": plan["sha256"],
        "authorization": dict(contrast.AUTHORIZATION),
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def _validate_contrast_request(value: Any) -> dict[str, Any]:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    expected_fields = {
        "authority",
        "schema_version",
        "classification",
        "binding",
        "source_identity",
        "source_identity_sha256",
        "cells",
        "fixture_usd_dependency_closure",
        "plan",
        "plan_sha256",
        "authorization",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("authored_offset_behavior_request_invalid")
    request = dict(value)
    digest = request.pop("sha256")
    if (
        request.get("authority") != AUTHORITY
        or request.get("schema_version") != 1
        or request.get("classification") != CLASSIFICATION
        or request.get("authorization") != contrast.AUTHORIZATION
        or not _is_sha256(digest)
        or _canonical_sha256(request) != digest
        or not isinstance(request.get("source_identity"), Mapping)
        or request.get("source_identity_sha256")
        != attestation.canonical_json_sha256(request["source_identity"])
    ):
        raise ValueError("authored_offset_behavior_request_invalid")
    binding = _config_binding()
    cells = _cell_profiles()
    if request.get("binding") != binding or request.get("cells") != cells:
        raise ValueError("authored_offset_behavior_request_invalid")
    fixture = _validate_fixture_usd_dependency_closure(
        request.get("fixture_usd_dependency_closure"), binding=binding, cells=cells
    )
    plan = contrast.build_plan(
        {
            "config_closure_sha256": binding["config_closure_sha256"],
            "asset_sha256": binding["asset"]["sha256"],
            "robot_asset_sha256": binding["robot_asset"]["sha256"],
            "source_identity_sha256": request["source_identity_sha256"],
            "cube_only_profile_sha256": cells[0]["profile_sha256"],
            "finite_profile_sha256": cells[1]["profile_sha256"],
            "fixture_usd_dependency_closure_sha256": fixture["closure_sha256"],
            "cube_only_resolved_usd_dependency_closure_sha256": fixture[
                "resolved_usd_dependency_closures"
            ]["cube_only_baseline_v1"]["sha256"],
            "finite_resolved_usd_dependency_closure_sha256": fixture[
                "resolved_usd_dependency_closures"
            ]["finite_target_offsets_calibration_v2"]["sha256"],
            "fixture_usd_dependency_preflight_sha256": fixture["sha256"],
            "seed": DEFAULT_SEED,
            "max_control_steps": DEFAULT_MAX_CONTROL_STEPS,
            "physics_dt_s": binding["physics_dt_s"],
        }
    )
    if request.get("plan") != plan or request.get("plan_sha256") != plan["sha256"]:
        raise ValueError("authored_offset_behavior_request_invalid")
    return {**request, "sha256": digest}


def expected_child_returncode(decision: str) -> int:
    if decision == contrast.RUNTIME_BLOCKED:
        return 2
    if decision in {contrast.OBSERVED, contrast.INCONCLUSIVE, contrast.NO_GO}:
        return 0
    raise ValueError("authored_offset_behavior_decision_invalid")


def _regular_file(path: Path, *, field: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"authored_offset_behavior_{field}_invalid")
    return path


def _artifact_record(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        return {"path": str(path.relative_to(root)), "invalid_kind": "symlink_or_non_regular"}
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


class _FixturePreflightNoGo(RuntimeError):
    def __init__(self, evidence: Mapping[str, Any]):
        super().__init__("authored_offset_behavior_fixture_preflight_no_go")
        self.evidence = dict(evidence)


def _fixture_from_static_preflight_artifacts(
    *, out_dir: Path, binding: Mapping[str, Any], cells: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify a static sealed preflight and convert it into a dynamic input closure."""
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation
    from tools.labutopia_fluid import run_nonformal_authored_offset_overlay_composition as static_runner

    preflight_dir = out_dir / STATIC_PREFLIGHT_DIRNAME
    if preflight_dir.is_symlink() or not preflight_dir.is_dir():
        raise RuntimeError("authored_offset_behavior_fixture_preflight_output_invalid")
    report_path = _regular_file(preflight_dir / static_runner.REPORT_BASENAME, field="fixture_preflight_report")
    manifest_path = _regular_file(
        preflight_dir / static_runner.MANIFEST_BASENAME, field="fixture_preflight_manifest"
    )
    observation_path = _regular_file(
        preflight_dir / static_runner.OBSERVATION_BASENAME, field="fixture_preflight_observation"
    )
    runtime_receipt_path = _regular_file(
        preflight_dir / static_runner.RUNTIME_RECEIPT_BASENAME,
        field="fixture_preflight_runtime_receipt",
    )
    execution_request_path = _regular_file(
        preflight_dir / static_runner.EXECUTION_REQUEST_BASENAME,
        field="fixture_preflight_execution_request",
    )
    report = attestation._read_canonical_json(report_path)
    manifest = attestation._read_canonical_json(manifest_path)
    observation = attestation._read_canonical_json(observation_path)
    receipt = attestation._read_canonical_json(runtime_receipt_path)
    static_execution_request = attestation._read_canonical_json(execution_request_path)
    static_request = report.get("request")
    verification = report.get("parent_verification")
    composition_report = report.get("composition")
    static_source_sha256 = attestation.canonical_json_sha256(
        static_execution_request.get("source", {})
    )
    receipt_source_sha256 = (
        receipt.get("execution_binding", {}).get("source_sha256")
        if isinstance(receipt.get("execution_binding"), Mapping)
        else None
    )
    evidence = {
        "command": manifest.get("command"),
        "execution_request_sha256": attestation.canonical_json_sha256(static_execution_request),
        "report": _artifact_record(report_path, root=out_dir),
        "manifest": _artifact_record(manifest_path, root=out_dir),
        "observation": _artifact_record(observation_path, root=out_dir),
        "runtime_receipt": _artifact_record(runtime_receipt_path, root=out_dir),
    }
    if (
        static_source_sha256 != receipt_source_sha256
        or attestation.canonical_json_sha256(manifest["source_before"]) != static_source_sha256
    ):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_source_invalid")
    if (
        report.get("authority")
        != "nonauthorizing_authored_offset_overlay_composition_parent_report_v1"
        or report.get("decision") not in {static_runner.PASS, static_runner.NO_GO}
        or not isinstance(static_request, Mapping)
        or not isinstance(verification, Mapping)
        or not isinstance(composition_report, Mapping)
        or verification.get("verified") is not True
        or not _is_sha256(verification.get("runtime_receipt_sha256"))
        or attestation.canonical_json_sha256(receipt) != verification["runtime_receipt_sha256"]
        or manifest.get("decision") != report.get("decision")
        or manifest.get("runtime_receipt_sha256") != verification["runtime_receipt_sha256"]
        or manifest.get("source_before") != manifest.get("source_after")
        or not isinstance(manifest.get("source_before"), Mapping)
    ):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_invalid")
    try:
        attestation.validate_runtime_receipt(receipt)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_invalid") from exc
    observation_artifact = composition_report.get("observation_artifact")
    manifest_observation = manifest.get("observation")
    if (
        not isinstance(observation_artifact, Mapping)
        or set(observation_artifact) != {"path", "sha256", "observation_sha256"}
        or observation_artifact.get("path") != static_runner.OBSERVATION_BASENAME
        or observation_artifact.get("sha256") != _sha256_file(observation_path)
        or observation_artifact.get("observation_sha256") != observation.get("sha256")
        or verification.get("observation_sha256") != _sha256_file(observation_path)
        or not isinstance(manifest_observation, Mapping)
        or manifest_observation.get("path") != static_runner.OBSERVATION_BASENAME
        or manifest_observation.get("sha256") != _sha256_file(observation_path)
    ):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_artifact_invalid")
    try:
        static_evaluation = static_runner.composition.evaluate_observation(
            observation,
            plan=static_request["plan"],
            fixture=static_request["fixture"],
            kit_profile=static_request["kit_profile"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_artifact_invalid") from exc
    if (
        composition_report.get("evaluation") != static_evaluation
        or report.get("parent_evaluation") != static_evaluation
        or composition_report.get("input_usd_dependency_closure_sha256")
        != observation["input_usd_dependency_closures"]["before"]["sha256"]
    ):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_artifact_invalid")
    if report["decision"] == static_runner.NO_GO:
        raise _FixturePreflightNoGo(evidence)
    static_fixture = static_request.get("fixture")
    finite_profile = cells[1]["profile"]
    if (
        not isinstance(static_fixture, Mapping)
        or static_fixture.get("asset") != binding["asset"]
        or static_fixture.get("robot_asset") != binding["robot_asset"]
        or not isinstance(static_fixture.get("overlay_profile"), Mapping)
        or static_fixture["overlay_profile"].get("overlay_stack")
        != finite_profile["overlay_stack"]
    ):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_binding_invalid")
    closures = observation.get("input_usd_dependency_closures")
    if (
        not isinstance(closures, Mapping)
        or set(closures) != {"before", "after"}
        or closures.get("before") != closures.get("after")
        or not isinstance(closures.get("after"), Mapping)
    ):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_closure_invalid")
    stage = observation.get("stage")
    if not isinstance(stage, Mapping) or stage.get("robot_reference_ready_before_treatment") is not True:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_order_invalid")
    dependency_closures = observation.get("resolved_usd_dependency_closures")
    expected_profiles = {cell["profile"]["id"] for cell in cells}
    if not isinstance(dependency_closures, Mapping) or set(dependency_closures) != expected_profiles:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_closure_invalid")
    resolved_dependency_closures = {}
    for profile_id in expected_profiles:
        profile_record = dependency_closures[profile_id]
        try:
            resolved_dependency_before = dependency_resolution.validate(
                profile_record.get("before") if isinstance(profile_record, Mapping) else None
            )
            resolved_dependency_after = dependency_resolution.validate(
                profile_record.get("after") if isinstance(profile_record, Mapping) else None
            )
        except ValueError as exc:
            raise RuntimeError("authored_offset_behavior_fixture_preflight_closure_invalid") from exc
        if resolved_dependency_before != resolved_dependency_after or resolved_dependency_after["unresolved"]:
            raise RuntimeError("authored_offset_behavior_fixture_preflight_closure_invalid")
        resolved_dependency_closures[profile_id] = resolved_dependency_after
    full_closure = closures["after"]
    layers = full_closure.get("layers")
    if (
        not isinstance(layers, list)
        or full_closure.get("sha256")
        != static_runner.composition.canonical_json_sha256({"layers": layers})
    ):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_closure_invalid")
    profile_paths = {
        item["path"] for cell in cells for item in cell["profile"]["overlay_stack"]
    }
    layer_paths = {
        item.get("real_path") for item in layers if isinstance(item, Mapping)
    }
    if not profile_paths <= layer_paths:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_closure_invalid")
    common_layers = [
        dict(layer)
        for layer in layers
        if isinstance(layer, Mapping) and layer.get("real_path") not in profile_paths
    ]
    preflight = {
        "artifact_dir": str(preflight_dir.relative_to(out_dir)),
        "report_sha256": _sha256_file(report_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "runtime_receipt_sha256": verification["runtime_receipt_sha256"],
        "observation_sha256": observation.get("sha256"),
        "execution_request_sha256": evidence["execution_request_sha256"],
        "source_identity_sha256": attestation.canonical_json_sha256(manifest["source_before"]),
    }
    static_kit_profile = static_request.get("kit_profile")
    if not isinstance(static_kit_profile, Mapping) or not _is_sha256(static_kit_profile.get("sha256")):
        raise RuntimeError("authored_offset_behavior_fixture_preflight_kit_profile_invalid")
    fixture_payload = {
        "authority": FIXTURE_USD_CLOSURE_AUTHORITY,
        "schema_version": 1,
        "preflight": preflight,
        "layers": common_layers,
        "closure_sha256": direct_probe._canonical_json_sha256({"layers": common_layers}),
        "resolved_usd_dependency_closures": resolved_dependency_closures,
        "static_kit_profile": dict(static_kit_profile),
    }
    fixture = _validate_fixture_usd_dependency_closure(
        {**fixture_payload, "sha256": _canonical_sha256(fixture_payload)},
        binding=binding,
        cells=cells,
    )
    return fixture, evidence


def _run_fixture_usd_composition_preflight(
    *,
    out_dir: Path,
    binding: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the static preflight in-process so its child cleanup remains authoritative."""
    from tools.labutopia_fluid import run_nonformal_authored_offset_overlay_composition as static_runner

    preflight_dir = out_dir / STATIC_PREFLIGHT_DIRNAME
    if preflight_dir.exists():
        raise RuntimeError("authored_offset_behavior_fixture_preflight_output_exists")
    static_args = static_runner.parse_args(
        ["--out-dir", str(preflight_dir), "--timeout-seconds", str(timeout_seconds)]
    )
    try:
        returncode = static_runner._run_parent(static_args)
    except BaseException as exc:
        static_runner._write_parent_preflight_blocked(static_args, exc)
        raise
    if returncode not in {0, 2}:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_exit_invalid")
    try:
        fixture, evidence = _fixture_from_static_preflight_artifacts(
            out_dir=out_dir, binding=binding, cells=cells
        )
    except _FixturePreflightNoGo as exc:
        exc.evidence["returncode"] = returncode
        raise
    if returncode != 0:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_failed")
    return fixture, {**evidence, "returncode": returncode}


def _verify_fixture_preflight_binding(request: Mapping[str, Any], *, run_dir: Path) -> None:
    fixture, _ = _fixture_from_static_preflight_artifacts(
        out_dir=run_dir,
        binding=request["binding"],
        cells=request["cells"],
    )
    if fixture != request["fixture_usd_dependency_closure"]:
        raise RuntimeError("authored_offset_behavior_fixture_preflight_binding_drift")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("authored_offset_behavior_json_invalid") from exc
    if not isinstance(value, Mapping):
        raise RuntimeError("authored_offset_behavior_json_invalid")
    return dict(value)


def _hash_uncompressed_gzip(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with gzip.open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, EOFError) as exc:
        raise RuntimeError("authored_offset_behavior_trace_invalid") from exc
    return digest.hexdigest()


def _metrics(history: Any) -> dict[str, Any]:
    if not isinstance(history, list):
        raise RuntimeError("authored_offset_behavior_history_invalid")
    bilateral_indices = []
    expected_index = 0
    for record in history:
        if not isinstance(record, Mapping) or record.get("physics_index") != expected_index:
            raise RuntimeError("authored_offset_behavior_history_invalid")
        direct = record.get("direct")
        contact = direct.get("direct_contact") if isinstance(direct, Mapping) else None
        if (
            not isinstance(contact, Mapping)
            or type(contact.get("left")) is not bool
            or type(contact.get("right")) is not bool
        ):
            raise RuntimeError("authored_offset_behavior_history_invalid")
        if contact["left"] and contact["right"]:
            bilateral_indices.append(expected_index)
        expected_index += 1
    longest = 0
    current = 0
    previous = None
    for index in bilateral_indices:
        current = current + 1 if previous is not None and index == previous + 1 else 1
        longest = max(longest, current)
        previous = index
    return {
        "first_bilateral_current_physics_index": bilateral_indices[0] if bilateral_indices else None,
        "bilateral_current_sample_count": len(bilateral_indices),
        "longest_bilateral_current_window": longest,
    }


def _trace_metrics(path: Path, *, expected_record_count: int, identities: Any) -> dict[str, Any]:
    if not isinstance(identities, Mapping):
        raise RuntimeError("authored_offset_behavior_trace_identities_invalid")
    source = set(identities.get("source_colliders", []))
    left = set(identities.get("left_colliders", []))
    right = set(identities.get("right_colliders", []))
    if not source or not left or not right:
        raise RuntimeError("authored_offset_behavior_trace_identities_invalid")
    bilateral_indices = []
    expected_index = 0
    line_count = 0
    try:
        with gzip.open(path, "rb") as stream:
            for raw_line in stream:
                if not raw_line.endswith(b"\n"):
                    raise RuntimeError("authored_offset_behavior_trace_noncanonical")
                try:
                    report = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("authored_offset_behavior_trace_noncanonical") from exc
                canonical = json.dumps(
                    report,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8") + b"\n"
                if raw_line != canonical or not isinstance(report, Mapping):
                    raise RuntimeError("authored_offset_behavior_trace_noncanonical")
                if report.get("physics_index") != expected_index:
                    raise RuntimeError("authored_offset_behavior_trace_index_invalid")
                observed = {"left": False, "right": False}
                occurrences = report.get("occurrences")
                if not isinstance(occurrences, list):
                    raise RuntimeError("authored_offset_behavior_trace_occurrences_invalid")
                for occurrence in occurrences:
                    if not isinstance(occurrence, Mapping) or occurrence.get("current") is not True:
                        continue
                    pair = occurrence.get("canonical_pair")
                    if not isinstance(pair, list) or len(pair) != 2:
                        raise RuntimeError("authored_offset_behavior_trace_pair_invalid")
                    paths = {item.get("collider_path") for item in pair if isinstance(item, Mapping)}
                    if len(paths) != 2:
                        raise RuntimeError("authored_offset_behavior_trace_pair_invalid")
                    if paths & source and paths & left:
                        observed["left"] = True
                    if paths & source and paths & right:
                        observed["right"] = True
                if observed["left"] and observed["right"]:
                    bilateral_indices.append(expected_index)
                expected_index += 1
                line_count += 1
    except (OSError, EOFError) as exc:
        raise RuntimeError("authored_offset_behavior_trace_invalid") from exc
    if line_count != expected_record_count:
        raise RuntimeError("authored_offset_behavior_trace_count_invalid")
    longest = 0
    current = 0
    previous = None
    for index in bilateral_indices:
        current = current + 1 if previous is not None and index == previous + 1 else 1
        longest = max(longest, current)
        previous = index
    return {
        "first_bilateral_current_physics_index": bilateral_indices[0] if bilateral_indices else None,
        "bilateral_current_sample_count": len(bilateral_indices),
        "longest_bilateral_current_window": longest,
    }


def _valid_treatment_audit(
    *, treatment: Mapping[str, Any], request: Mapping[str, Any], cell: Mapping[str, Any]
) -> dict[str, Any]:
    reset_snapshot = treatment.get("offset_target_snapshot_after_reset")
    run_snapshot = treatment.get("offset_target_snapshot_after_run")
    reset_closure = treatment.get("usd_dependency_closure_after_reset")
    run_closure = treatment.get("usd_dependency_closure_after_run")
    if (
        not isinstance(reset_snapshot, Mapping)
        or not isinstance(run_snapshot, Mapping)
        or reset_snapshot != run_snapshot
        or reset_snapshot.get("sha256") != direct_probe._canonical_json_sha256(
            {"records": reset_snapshot.get("records")}
        )
        or not isinstance(reset_closure, Mapping)
        or reset_closure != run_closure
        or reset_closure.get("sha256") != direct_probe._canonical_json_sha256(
            {"layers": reset_closure.get("layers")}
        )
        or treatment.get("cube_collision_disabled_after_reset") is not True
        or treatment.get("cube_collision_disabled_after_run") is not True
    ):
        raise RuntimeError("authored_offset_behavior_treatment_audit_invalid")
    expected_paths = {
        request["binding"]["asset"]["path"],
        request["binding"]["robot_asset"]["path"],
        *(item["path"] for item in cell["profile"]["overlay_stack"]),
    }
    layers = reset_closure.get("layers")
    if (
        not isinstance(layers, list)
        or not expected_paths <= {item.get("real_path") for item in layers if isinstance(item, Mapping)}
    ):
        raise RuntimeError("authored_offset_behavior_treatment_audit_invalid")
    normalized_layers = []
    seen_paths = set()
    for layer in layers:
        if (
            not isinstance(layer, Mapping)
            or set(layer) != {"identifier", "real_path", "sha256"}
            or not isinstance(layer.get("identifier"), str)
            or not isinstance(layer.get("real_path"), str)
            or not Path(layer["real_path"]).is_absolute()
            or not _is_sha256(layer.get("sha256"))
            or layer["real_path"] in seen_paths
        ):
            raise RuntimeError("authored_offset_behavior_treatment_audit_invalid")
        seen_paths.add(layer["real_path"])
        normalized_layers.append(dict(layer))
    if normalized_layers != sorted(normalized_layers, key=lambda item: item["real_path"]):
        raise RuntimeError("authored_offset_behavior_treatment_audit_invalid")
    profile_layer_paths = {item["path"] for item in cell["profile"]["overlay_stack"]}
    common_layers = [
        layer for layer in normalized_layers if layer["real_path"] not in profile_layer_paths
    ]
    if not common_layers:
        raise RuntimeError("authored_offset_behavior_treatment_audit_invalid")
    common_closure_payload = {"layers": common_layers}
    common_closure_sha256 = direct_probe._canonical_json_sha256(common_closure_payload)
    expected_common_closure = request["fixture_usd_dependency_closure"]
    common_closure_matches_preflight = (
        common_layers == expected_common_closure["layers"]
        and common_closure_sha256 == expected_common_closure["closure_sha256"]
    )
    try:
        resolved_before_world = dependency_resolution.validate(
            treatment.get("resolved_usd_dependency_closure_before_world")
        )
        resolved_after_reset = dependency_resolution.validate(
            treatment.get("resolved_usd_dependency_closure_after_reset")
        )
        resolved_after_run = dependency_resolution.validate(
            treatment.get("resolved_usd_dependency_closure_after_run")
        )
    except ValueError as exc:
        raise RuntimeError("authored_offset_behavior_treatment_audit_invalid") from exc
    resolved_dependency_closure_unchanged = (
        resolved_before_world == resolved_after_reset == resolved_after_run
    )
    expected_resolved_dependency_closure = request["fixture_usd_dependency_closure"][
        "resolved_usd_dependency_closures"
    ][cell["profile"]["id"]]
    resolved_dependency_closure_matches_preflight = (
        resolved_dependency_closure_unchanged
        and resolved_after_reset == expected_resolved_dependency_closure
    )
    records = reset_snapshot.get("records")
    if not isinstance(records, list) or len(records) != 3:
        raise RuntimeError("authored_offset_behavior_treatment_audit_invalid")
    by_id = {record.get("id"): record for record in records if isinstance(record, Mapping)}
    if set(by_id) != {"left_finger", "right_finger", "table"}:
        raise RuntimeError("authored_offset_behavior_treatment_audit_invalid")
    profile_authoring_valid = True
    finite = cell["profile"]["id"] == "finite_target_offsets_calibration_v2"
    calibration_path = str(FINITE_TARGET_OFFSET_OVERLAY.resolve())
    expected_values = {
        "left_finger": 0.001,
        "right_finger": 0.001,
        "table": 0.00164,
    }
    for identifier, record in by_id.items():
        if (
            record.get("prim_type") != "Mesh"
            or record.get("usd_collision_api_applied") is not True
            or record.get("physx_collision_api_applied") is not True
            or record.get("contact_offset_anonymous_opinion") is not False
            or record.get("rest_offset_anonymous_opinion") is not False
        ):
            profile_authoring_valid = False
            continue
        if finite:
            profile_authoring_valid = profile_authoring_valid and (
                record.get("contact_offset_authored") is True
                and record.get("rest_offset_authored") is True
                and isinstance(record.get("contact_offset_m"), (int, float))
                and math.isclose(
                    float(record["contact_offset_m"]), expected_values[identifier], rel_tol=0.0, abs_tol=1.0e-9
                )
                and record.get("rest_offset_m") == 0.0
                and record.get("contact_offset_strongest_layer") == calibration_path
                and record.get("rest_offset_strongest_layer") == calibration_path
            )
        else:
            profile_authoring_valid = profile_authoring_valid and (
                record.get("contact_offset_strongest_layer") != calibration_path
                and record.get("rest_offset_strongest_layer") != calibration_path
            )
    return {
        "cube_collision_disabled": True,
        "offset_snapshot_after_reset_sha256": reset_snapshot["sha256"],
        "offset_snapshot_after_run_sha256": run_snapshot["sha256"],
        "offset_snapshot_unchanged": True,
        "usd_dependency_closure_after_reset_sha256": reset_closure["sha256"],
        "usd_dependency_closure_after_run_sha256": run_closure["sha256"],
        "usd_dependency_closure_unchanged": True,
        "common_usd_dependency_closure_after_reset_sha256": common_closure_sha256,
        "common_usd_dependency_closure_matches_preflight": common_closure_matches_preflight,
        "resolved_usd_dependency_closure_sha256": resolved_after_reset["sha256"],
        "resolved_usd_dependency_closure_unchanged": resolved_dependency_closure_unchanged,
        "resolved_usd_dependency_closure_matches_preflight": resolved_dependency_closure_matches_preflight,
        "profile_authoring_valid": profile_authoring_valid,
    }


def _source_writer_summary(value: Any) -> dict[str, Any]:
    names = (
        "valid",
        "coverage_complete",
        "source_pose_write_count_after_play",
        "source_velocity_write_count_after_play",
        "object_utils_source_position_write_count_after_play",
        "kinematic_target_update_count",
    )
    if not isinstance(value, Mapping) or any(name not in value for name in names):
        raise RuntimeError("authored_offset_behavior_source_writer_invalid")
    return {name: value[name] for name in names}


def _blocked_cell_observation(request: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    common = request["plan"]["common"]
    return {
        "id": cell["id"],
        "profile_id": cell["profile"]["id"],
        "profile_sha256": cell["profile_sha256"],
        "decision": contrast.RUNTIME_BLOCKED,
        "runtime_receipt_matched": False,
        "config_closure_sha256": common["config_closure_sha256"],
        "asset_sha256": common["asset_sha256"],
        "robot_asset_sha256": common["robot_asset_sha256"],
        "source_identity_sha256": common["source_identity_sha256"],
        "physics_dt_s": common["physics_dt_s"],
        "seed": common["seed"],
        "max_control_steps": common["max_control_steps"],
        "direct_report_trace": {
            "complete": False,
            "record_count": 0,
            "uncompressed_sha256": "0" * 64,
            "compressed_sha256": "0" * 64,
        },
        "report_layer": {
            "after_reset_sha256": "0" * 64,
            "after_run_sha256": "0" * 64,
            "unchanged": False,
        },
        "treatment_audit": {
            "cube_collision_disabled": False,
            "offset_snapshot_after_reset_sha256": "0" * 64,
            "offset_snapshot_after_run_sha256": "0" * 64,
            "offset_snapshot_unchanged": False,
            "usd_dependency_closure_after_reset_sha256": "0" * 64,
            "usd_dependency_closure_after_run_sha256": "0" * 64,
            "usd_dependency_closure_unchanged": False,
            "common_usd_dependency_closure_after_reset_sha256": "0" * 64,
            "common_usd_dependency_closure_matches_preflight": False,
            "resolved_usd_dependency_closure_sha256": "0" * 64,
            "resolved_usd_dependency_closure_unchanged": False,
            "resolved_usd_dependency_closure_matches_preflight": False,
            "profile_authoring_valid": False,
        },
        "source_writer_audit": {
            "valid": False,
            "coverage_complete": False,
            "source_pose_write_count_after_play": 0,
            "source_velocity_write_count_after_play": 0,
            "object_utils_source_position_write_count_after_play": 0,
            "kinematic_target_update_count": 0,
        },
        "source_writer_audit_scope": "instrumented_known_surfaces_only",
        "lift_action_applied": False,
        "metrics": {
            "first_bilateral_current_physics_index": None,
            "bilateral_current_sample_count": 0,
            "longest_bilateral_current_window": 0,
        },
    }


def _summarize_direct_report(
    *,
    direct_report: Mapping[str, Any],
    request: Mapping[str, Any],
    cell: Mapping[str, Any],
    cell_dir: Path,
    runtime_receipt_matched: bool,
    child_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    if direct_report.get("decision") == contrast.RUNTIME_BLOCKED:
        return _blocked_cell_observation(request, cell)
    on_disk_direct_report = _read_json(cell_dir / DIRECT_REPORT_BASENAME)
    if on_disk_direct_report != dict(direct_report):
        raise RuntimeError("authored_offset_behavior_direct_report_drift")
    decision = direct_report.get("decision")
    if child_receipt_sha256 is not None:
        dr_runtime = direct_report.get("runtime")
        if (
            not isinstance(dr_runtime, Mapping)
            or dr_runtime.get("receipt_sha256") != child_receipt_sha256
        ):
            raise RuntimeError("authored_offset_behavior_direct_runtime_mismatch")
    if (
        direct_report.get("schema_version") != 1
        or direct_report.get("manifest_type") != "nonformal_pbd_direct_contact_probe_v1"
        or direct_report.get("classification") != "NON_FORMAL_DIAGNOSTIC_ONLY"
        or decision not in {"OBSERVED", "PHYSICAL_FAIL", "AUDIT_NO_GO"}
    ):
        raise RuntimeError("authored_offset_behavior_direct_decision_invalid")
    config = direct_report.get("config")
    treatment = direct_report.get("treatment")
    result = direct_report.get("result")
    if not isinstance(config, Mapping) or not isinstance(treatment, Mapping) or not isinstance(result, Mapping):
        raise RuntimeError("authored_offset_behavior_direct_report_invalid")
    expected_input_closure = {
        item["path"]: item["sha256"] for item in request["binding"]["config_closure"]
    }
    expected_input_closure.update(
        {
            item["path"]: item["sha256"]
            for item in request["fixture_usd_dependency_closure"]["resolved_usd_dependency_closures"][
                cell["profile"]["id"]
            ]["files"]
        }
    )
    if (
        config.get("path") != request["binding"]["config"]["path"]
        or config.get("input_closure") != dict(sorted(expected_input_closure.items()))
        or config.get("asset_path") != request["binding"]["asset"]["path"]
        or config.get("robot_asset_path") != request["binding"]["robot_asset"]["path"]
        or treatment.get("offset_treatment_profile") != cell["profile"]
        or treatment.get("seed", {}).get("requested_seed") != request["plan"]["common"]["seed"]
    ):
        raise RuntimeError("authored_offset_behavior_direct_binding_invalid")
    trace = result.get("direct_report_trace")
    if not isinstance(trace, Mapping):
        raise RuntimeError("authored_offset_behavior_trace_invalid")
    raw_trace_path = Path(str(trace.get("path", "")))
    if raw_trace_path.is_symlink():
        raise RuntimeError("authored_offset_behavior_trace_invalid")
    trace_path = raw_trace_path.resolve()
    if (
        not trace_path.is_file()
        or not trace_path.is_relative_to(cell_dir.resolve())
        or trace.get("complete") is not True
        or type(trace.get("record_count")) is not int
        or trace["record_count"] <= 0
        or _sha256_file(trace_path) != trace.get("compressed_sha256")
        or _hash_uncompressed_gzip(trace_path) != trace.get("uncompressed_sha256")
    ):
        raise RuntimeError("authored_offset_behavior_trace_invalid")
    trace_metrics = _trace_metrics(
        trace_path,
        expected_record_count=trace["record_count"],
        identities=treatment.get("contact_identities"),
    )
    if trace_metrics != _metrics(direct_report.get("history")):
        raise RuntimeError("authored_offset_behavior_trace_history_mismatch")
    if decision == "OBSERVED" and (
        trace_metrics["bilateral_current_sample_count"] <= 0
        or result.get("observed_bilateral_direct_contact") is not True
    ):
        raise RuntimeError("authored_offset_behavior_observed_contact_missing")
    report_layer = {
        "after_reset_sha256": treatment.get("report_layer_sha256_after_reset"),
        "after_run_sha256": treatment.get("report_layer_sha256_after_run"),
        "unchanged": treatment.get("report_layer_unchanged_post_reset"),
    }
    if not all(_is_sha256(report_layer[name]) for name in ("after_reset_sha256", "after_run_sha256")):
        raise RuntimeError("authored_offset_behavior_report_layer_invalid")
    common = request["plan"]["common"]
    return {
        "id": cell["id"],
        "profile_id": cell["profile"]["id"],
        "profile_sha256": cell["profile_sha256"],
        "decision": decision,
        "runtime_receipt_matched": runtime_receipt_matched,
        "config_closure_sha256": common["config_closure_sha256"],
        "asset_sha256": common["asset_sha256"],
        "robot_asset_sha256": common["robot_asset_sha256"],
        "source_identity_sha256": common["source_identity_sha256"],
        "seed": common["seed"],
        "max_control_steps": common["max_control_steps"],
        "physics_dt_s": common["physics_dt_s"],
        "direct_report_trace": {
            "complete": True,
            "record_count": trace["record_count"],
            "uncompressed_sha256": trace["uncompressed_sha256"],
            "compressed_sha256": trace["compressed_sha256"],
        },
        "report_layer": report_layer,
        "treatment_audit": _valid_treatment_audit(
            treatment=treatment,
            request=request,
            cell=cell,
        ),
        "source_writer_audit": _source_writer_summary(result.get("source_writer_audit")),
        "source_writer_audit_scope": "instrumented_known_surfaces_only",
        "lift_action_applied": treatment.get("lift_action_applied"),
        "metrics": trace_metrics,
    }


def _child_error_report(
    error: BaseException,
    *,
    request: Mapping[str, Any] | None,
    cell: Mapping[str, Any] | None,
    runtime: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": contrast.RUNTIME_BLOCKED,
        "request": dict(request) if isinstance(request, Mapping) else None,
        "cell": dict(cell) if isinstance(cell, Mapping) else None,
        "runtime": dict(runtime) if isinstance(runtime, Mapping) else None,
        "fatal_error": {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def _run_cell_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation
    from tools.labutopia_fluid import run_nonformal_authored_offset_overlay_composition as static_runner

    app = None
    request: dict[str, Any] | None = None
    cell: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    report: dict[str, Any]
    close_failed = False
    try:
        request = _validate_contrast_request(attestation._read_canonical_json(args.contrast_request))
        cells = {item["id"]: item for item in request["cells"]}
        cell = cells.get(args.cell)
        if cell is None:
            raise RuntimeError("authored_offset_behavior_cell_unknown")
        _verify_fixture_preflight_binding(
            request,
            run_dir=args.contrast_request.parent.resolve(),
        )
        execution_request = attestation._read_canonical_json(args.execution_request)
        closure = source_paths(request)
        execution_request = attestation.verify_execution_request(
            execution_request, source_paths=closure
        )
        if attestation.canonical_json_sha256(execution_request["source"]) != request["source_identity_sha256"]:
            raise RuntimeError("authored_offset_behavior_source_request_mismatch")
        runtime = direct_probe.runtime_process_preflight(execution_request)
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=execution_request,
            source_paths=closure,
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(execution_request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)

        runtime.update(
            {
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
                "execution_request_sha256": attestation.canonical_json_sha256(execution_request),
                "gpu": static_runner._collect_child_gpu_identity(),
            }
        )
        direct_args = argparse.Namespace(
            out_dir=args.out_dir,
            config=Path(request["binding"]["config"]["path"]),
            max_control_steps=request["plan"]["common"]["max_control_steps"],
            treatment_profile=cell["profile"]["id"],
            seed=request["plan"]["common"]["seed"],
            child_report_path=args.direct_report_path,
        )
        direct_report = direct_probe._runtime_probe(direct_args, runtime, app=app)
        summary = _summarize_direct_report(
            direct_report=direct_report,
            request=request,
            cell=cell,
            cell_dir=args.out_dir,
            runtime_receipt_matched=True,
            child_receipt_sha256=attestation.canonical_json_sha256(receipt),
        )
        source_after = attestation.capture_source_identity(closure)
        if source_after != execution_request["source"]:
            raise RuntimeError("authored_offset_behavior_source_changed_during_run")
        report = {
            "authority": AUTHORITY,
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "decision": summary["decision"],
            "request": request,
            "cell": cell,
            "runtime": runtime,
            "direct_report_artifact": {
                "path": DIRECT_REPORT_BASENAME,
                "sha256": _sha256_file(args.direct_report_path),
            },
            "cell_observation": summary,
            "authorization": dict(contrast.AUTHORIZATION),
        }
    except BaseException as exc:
        report = _child_error_report(exc, request=request, cell=cell, runtime=runtime)
    finally:
        if not args.cell_report_path.exists():
            attestation.write_canonical_json(args.cell_report_path, report)
        if app is not None and report["decision"] != contrast.RUNTIME_BLOCKED:
            try:
                app.close()
            except BaseException:
                close_failed = True
    if close_failed:
        return 2
    return 2 if report["decision"] == contrast.RUNTIME_BLOCKED else 0


def _require_process_group_quiescent(pgid: int, *, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise RuntimeError("authored_offset_behavior_child_pgid_uninspectable") from exc
        if time.monotonic() >= deadline:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                return
            raise RuntimeError("authored_offset_behavior_child_process_group_not_quiescent")
        time.sleep(0.05)


def _run_cell_parent(
    *,
    out_dir: Path,
    request: Mapping[str, Any],
    cell: Mapping[str, Any],
    source_before: Mapping[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    cell_dir = out_dir / cell["id"]
    cell_dir.mkdir(mode=0o700)
    execution_request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    execution_request_path = cell_dir / EXECUTION_REQUEST_BASENAME
    attestation.write_canonical_json(execution_request_path, execution_request)
    environment = attestation.sealed_child_environment(cell_dir / "runtime")
    environment["NVIDIA_VISIBLE_DEVICES"] = "4"
    environment.pop("CUDA_VISIBLE_DEVICES", None)
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--out-dir",
        str(cell_dir),
        "--cell",
        str(cell["id"]),
        "--contrast-request",
        str(out_dir / REQUEST_BASENAME),
        "--execution-request",
        str(execution_request_path),
    ]
    stdout_path = cell_dir / STDOUT_BASENAME
    stderr_path = cell_dir / STDERR_BASENAME
    child_pid = None
    child_returncode = None
    receipt = None
    verification_failure = None
    summary = _blocked_cell_observation(request, cell)
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = process.pid
            try:
                child_returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                child_returncode = process.wait()
                raise RuntimeError("authored_offset_behavior_cell_timeout") from exc
        _require_process_group_quiescent(child_pid)
        cell_report_path = cell_dir / CELL_REPORT_BASENAME
        _regular_file(cell_report_path, field="cell_report")
        child_report = attestation._read_canonical_json(cell_report_path)
        if (
            child_report.get("authority") != AUTHORITY
            or child_report.get("schema_version") != 1
            or child_report.get("classification") != CLASSIFICATION
            or child_report.get("request") != dict(request)
            or child_report.get("cell") != dict(cell)
        ):
            raise RuntimeError("authored_offset_behavior_cell_report_invalid")
        if child_report.get("decision") == contrast.RUNTIME_BLOCKED:
            if child_returncode != 2:
                raise RuntimeError("authored_offset_behavior_cell_exit_status_invalid")
            if (cell_dir / RUNTIME_RECEIPT_BASENAME).is_file():
                receipt = attestation._read_canonical_json(cell_dir / RUNTIME_RECEIPT_BASENAME)
                attestation.validate_runtime_receipt(receipt)
        else:
            _regular_file(cell_dir / RUNTIME_RECEIPT_BASENAME, field="runtime_receipt")
            receipt = attestation._read_canonical_json(cell_dir / RUNTIME_RECEIPT_BASENAME)
            binding = attestation.execution_binding_for_request(execution_request, child_pid=child_pid)
            attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
            runtime = child_report.get("runtime")
            if (
                not isinstance(runtime, Mapping)
                or runtime.get("receipt_sha256") != attestation.canonical_json_sha256(receipt)
                or runtime.get("execution_binding") != binding
            ):
                raise RuntimeError("authored_offset_behavior_cell_runtime_invalid")
            from tools.labutopia_fluid import run_nonformal_authored_offset_overlay_composition as static_runner

            static_runner._validate_child_gpu_identity(runtime.get("gpu"))
            artifact = child_report.get("direct_report_artifact")
            direct_path = cell_dir / DIRECT_REPORT_BASENAME
            if (
                not isinstance(artifact, Mapping)
                or artifact.get("path") != DIRECT_REPORT_BASENAME
                or artifact.get("sha256") != _sha256_file(_regular_file(direct_path, field="direct_report"))
                or not isinstance(child_report.get("cell_observation"), Mapping)
            ):
                raise RuntimeError("authored_offset_behavior_cell_artifact_invalid")
            direct_report = _read_json(direct_path)
            summary = _summarize_direct_report(
                direct_report=direct_report,
                request=request,
                cell=cell,
                cell_dir=cell_dir,
                runtime_receipt_matched=True,
                child_receipt_sha256=attestation.canonical_json_sha256(receipt),
            )
            if child_report["cell_observation"] != summary:
                raise RuntimeError("authored_offset_behavior_cell_observation_drift")
            if child_returncode != 0:
                raise RuntimeError("authored_offset_behavior_cell_exit_status_invalid")
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    return {
        "id": cell["id"],
        "summary": summary,
        "command": command,
        "child_pid": child_pid,
        "child_returncode": child_returncode,
        "runtime_receipt": _artifact_record(cell_dir / RUNTIME_RECEIPT_BASENAME, root=out_dir),
        "cell_report": _artifact_record(cell_dir / CELL_REPORT_BASENAME, root=out_dir),
        "direct_report": _artifact_record(cell_dir / DIRECT_REPORT_BASENAME, root=out_dir),
        "stdout": _artifact_record(stdout_path, root=out_dir),
        "stderr": _artifact_record(stderr_path, root=out_dir),
        "verification_failure": verification_failure,
        "runtime_receipt_sha256": (
            attestation.canonical_json_sha256(receipt) if isinstance(receipt, Mapping) else None
        ),
        "sanitized_environment_sha256": attestation.canonical_json_sha256(
            dict(sorted(environment.items()))
        ),
    }


def _run_parent(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    binding = _config_binding()
    cells = _cell_profiles()
    fixture, fixture_preflight = _run_fixture_usd_composition_preflight(
        out_dir=args.out_dir,
        binding=binding,
        cells=cells,
        timeout_seconds=args.timeout_seconds,
    )
    request = build_contrast_request(
        fixture_usd_dependency_closure=fixture,
        binding=binding,
        cells=cells,
    )
    request_path = args.out_dir / REQUEST_BASENAME
    attestation.write_canonical_json(request_path, request)
    closure = source_paths(request)
    source_before = attestation.capture_source_identity(closure)
    if source_before != request["source_identity"]:
        raise RuntimeError("authored_offset_behavior_source_request_mismatch")
    cells = [
        _run_cell_parent(
            out_dir=args.out_dir,
            request=request,
            cell=cell,
            source_before=source_before,
            timeout_seconds=args.timeout_seconds,
        )
        for cell in request["cells"]
    ]
    observation_payload = {
        "authority": contrast.OBSERVATION_AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "plan_sha256": request["plan_sha256"],
        "authorization": dict(contrast.AUTHORIZATION),
        "cells": [cell["summary"] for cell in cells],
    }
    observation = {
        **observation_payload,
        "sha256": contrast.canonical_json_sha256(observation_payload),
    }
    evaluation = contrast.evaluate_observation(observation, plan=request["plan"])
    source_after = attestation.capture_source_identity(closure)
    source_stable = source_after == source_before
    final_decision = evaluation["decision"] if source_stable else contrast.RUNTIME_BLOCKED
    observation_path = args.out_dir / OBSERVATION_BASENAME
    attestation.write_canonical_json(observation_path, observation)
    report = {
        "authority": "nonauthorizing_authored_offset_behavior_contrast_parent_report_v1",
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": final_decision,
        "request": request,
        "evaluation": evaluation,
        "parent_source_audit": {
            "stable": source_stable,
            "source_before_sha256": attestation.canonical_json_sha256(source_before),
            "source_after_sha256": attestation.canonical_json_sha256(source_after),
        },
        "fixture_usd_preflight": fixture_preflight,
        "fixture_usd_dependency_closure": request["fixture_usd_dependency_closure"],
        "observation_artifact": {
            "path": OBSERVATION_BASENAME,
            "sha256": _sha256_file(observation_path),
            "observation_sha256": observation["sha256"],
        },
        "cells": cells,
        "authorization": dict(contrast.AUTHORIZATION),
    }
    report_path = args.out_dir / REPORT_BASENAME
    attestation.write_canonical_json(report_path, report)
    manifest = {
        "authority": AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": final_decision,
        "request_sha256": _sha256_file(request_path),
        "source_before": source_before,
        "source_after": source_after,
        "config_closure_sha256": request["binding"]["config_closure_sha256"],
        "fixture": {
            "asset": request["binding"]["asset"],
            "robot_asset": request["binding"]["robot_asset"],
            "cells": request["cells"],
        },
        "fixture_usd_preflight": fixture_preflight,
        "fixture_usd_dependency_closure": request["fixture_usd_dependency_closure"],
        "observation": _artifact_record(observation_path, root=args.out_dir),
        "report": _artifact_record(report_path, root=args.out_dir),
        "cells": cells,
    }
    attestation.write_canonical_json(args.out_dir / MANIFEST_BASENAME, manifest)
    print(
        f"authored offset behavior contrast decision={final_decision} out={report_path}",
        flush=True,
    )
    return expected_child_returncode(str(final_decision))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cell", type=str, help=argparse.SUPPRESS)
    parser.add_argument("--contrast-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.out_dir = args.out_dir.resolve()
    artifacts_root = (REPO_ROOT / "artifacts/runs").resolve()
    if not args.out_dir.is_relative_to(artifacts_root):
        parser.error("out-dir must be under artifacts/runs")
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("timeout-seconds must be positive")
    child_values = (args.cell, args.contrast_request, args.execution_request)
    if args.child:
        if any(value is None for value in child_values):
            parser.error("--child requires cell and sealed request paths")
        args.contrast_request = args.contrast_request.resolve()
        args.execution_request = args.execution_request.resolve()
        if (
            not args.out_dir.is_dir()
            or not args.contrast_request.is_file()
            or not args.execution_request.is_file()
        ):
            parser.error("child sealed inputs and out-dir must exist")
    else:
        if any(value is not None for value in child_values):
            parser.error("sealed child options are child-only")
        if args.out_dir.exists():
            parser.error("out-dir must not exist")
    args.runtime_receipt_path = args.out_dir / RUNTIME_RECEIPT_BASENAME
    args.cell_report_path = args.out_dir / CELL_REPORT_BASENAME
    args.direct_report_path = args.out_dir / DIRECT_REPORT_BASENAME
    return args


def _write_parent_preflight_blocked(args: argparse.Namespace, exc: BaseException) -> None:
    if not args.out_dir.is_dir() or (args.out_dir / REPORT_BASENAME).exists():
        return
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    failure = {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
    report = {
        "authority": "nonauthorizing_authored_offset_behavior_contrast_parent_report_v1",
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": contrast.RUNTIME_BLOCKED,
        "preflight_failure": failure,
    }
    report_path = args.out_dir / REPORT_BASENAME
    attestation.write_canonical_json(report_path, report)
    attestation.write_canonical_json(
        args.out_dir / MANIFEST_BASENAME,
        {
            "authority": AUTHORITY,
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "decision": contrast.RUNTIME_BLOCKED,
            "preflight_failure": failure,
            "report_sha256": _sha256_file(report_path),
        },
    )


def _write_parent_preflight_no_go(args: argparse.Namespace, evidence: Mapping[str, Any]) -> None:
    if not args.out_dir.is_dir() or (args.out_dir / REPORT_BASENAME).exists():
        return
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    report = {
        "authority": "nonauthorizing_authored_offset_behavior_contrast_parent_report_v1",
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": contrast.NO_GO,
        "fixture_usd_preflight": dict(evidence),
        "authorization": dict(contrast.AUTHORIZATION),
    }
    report_path = args.out_dir / REPORT_BASENAME
    attestation.write_canonical_json(report_path, report)
    attestation.write_canonical_json(
        args.out_dir / MANIFEST_BASENAME,
        {
            "authority": AUTHORITY,
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "decision": contrast.NO_GO,
            "fixture_usd_preflight": dict(evidence),
            "report_sha256": _sha256_file(report_path),
            "authorization": dict(contrast.AUTHORIZATION),
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.child:
        status = _run_cell_child(args)
        if status != 0:
            os._exit(status)
        return 0
    try:
        return _run_parent(args)
    except _FixturePreflightNoGo as exc:
        _write_parent_preflight_no_go(args, exc.evidence)
        print(
            f"authored offset behavior contrast decision={contrast.NO_GO} out={args.out_dir / REPORT_BASENAME}",
            flush=True,
        )
        return expected_child_returncode(contrast.NO_GO)
    except BaseException as exc:
        _write_parent_preflight_blocked(args, exc)
        print(
            f"authored offset behavior contrast decision={contrast.RUNTIME_BLOCKED} "
            f"out={args.out_dir / REPORT_BASENAME}",
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

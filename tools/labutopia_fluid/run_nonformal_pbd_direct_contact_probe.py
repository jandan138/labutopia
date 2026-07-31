#!/usr/bin/env python3
"""Observe a close-only dynamic PBD contact attempt with direct PhysX reports.

This tool is diagnostic only. It never emits a formal grasp, lift, pour, or
acceptance result and terminates before an arm-lift action can be applied.
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
import subprocess
import sys
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
FORMAL_ISAAC41_PREFIX = FORMAL_ISAAC41_PYTHON.parents[1]
APPROVED_LIBRARY_PATHS = (
    FORMAL_ISAAC41_PREFIX
    / "lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin",
    FORMAL_ISAAC41_PREFIX
    / "lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps",
    FORMAL_ISAAC41_PREFIX / "lib/python3.10/site-packages/torch/lib",
)
APPROVED_LD_LIBRARY_PATH = ":".join(str(path) for path in APPROVED_LIBRARY_PATHS)
DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_contact_pick_top_down_"
    "g2_600hz_step600_layout_v1.yaml"
)
HIDDEN_CUBE_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_disable_hidden_cube_collision_v1.usda"
)
FINITE_TARGET_OFFSET_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_finite_target_offsets_calibration_v2.usda"
)
_OFFSET_TARGETS = (
    ("left_finger", "/World/Franka/panda_leftfinger/geometry/panda_leftfinger"),
    ("right_finger", "/World/Franka/panda_rightfinger/geometry/panda_rightfinger"),
    ("table", "/World/table/surface/mesh"),
)
REQUIRED_ENVIRONMENT = {
    "PYTHONNOUSERSITE": "1",
    "ACCEPT_EULA": "Y",
    "OMNI_KIT_ACCEPT_EULA": "YES",
}
FORBIDDEN_ENVIRONMENT = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUSERBASE",
    "CARB_APP_PATH",
    "EXP_PATH",
    "ISAAC_PATH",
    "OMNI_SERVER",
    "LD_PRELOAD",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_treatment_profile(profile_id: str) -> dict[str, Any]:
    """Return the optional authored-offset session stack for one direct probe."""
    stacks = {
        "none": (),
        "cube_only_baseline_v1": (("hidden_cube_collision_disable", HIDDEN_CUBE_OVERLAY),),
        "finite_target_offsets_calibration_v2": (
            ("finite_target_offsets_calibration_v2", FINITE_TARGET_OFFSET_OVERLAY),
            ("hidden_cube_collision_disable", HIDDEN_CUBE_OVERLAY),
        ),
    }
    entries = stacks.get(profile_id)
    if entries is None:
        raise ValueError("nonformal_probe_treatment_profile_invalid")
    overlay_stack = []
    for identifier, raw_path in entries:
        path = Path(raw_path).resolve()
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(f"nonformal_probe_treatment_overlay_missing:{path}")
        overlay_stack.append(
            {"id": identifier, "path": str(path), "sha256": _sha256_file(path)}
        )
    return {
        "authority": "nonformal_pbd_direct_contact_treatment_profile_v1",
        "id": profile_id,
        "overlay_stack": overlay_stack,
    }


def _source_regular(path: Path) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file() or not candidate.is_relative_to(REPO_ROOT):
        raise ValueError("nonformal_probe_source_closure_invalid")
    return candidate.resolve()


def _internal_module_path(module: str) -> Path | None:
    if module.split(".", 1)[0] not in {
        "controllers",
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


def _python_import_closure(seed_paths: tuple[Path, ...]) -> set[Path]:
    queue = list(seed_paths)
    visited: set[Path] = set()
    while queue:
        path = _source_regular(queue.pop())
        if path in visited:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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


def _runtime_source_paths(config_path: Path, treatment_profile: str) -> tuple[Path, ...]:
    attestation = _attestation_module()
    cfg, config_closure = load_composed_config(config_path)
    asset_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
    robot_asset_path = (REPO_ROOT / str(cfg.robot.usd_path)).resolve()
    profile = resolve_treatment_profile(treatment_profile)
    paths = {
        *_python_import_closure((Path(__file__), Path(attestation.__file__))),
        Path(attestation.__file__),
        Path(config_path),
        *(Path(path) for path in config_closure),
        asset_path,
        robot_asset_path,
        *(Path(item["path"]) for item in profile["overlay_stack"]),
    }
    return tuple(sorted(_source_regular(path) for path in paths))


def _isolated_mode() -> bool:
    return bool(sys.flags.isolated)


def _stable_file_bytes(path: Path) -> tuple[bytes, str]:
    before = _sha256_file(path)
    payload = path.read_bytes()
    after = _sha256_file(path)
    if before != after or hashlib.sha256(payload).hexdigest() != before:
        raise RuntimeError("nonformal_probe_input_changed_while_loading")
    return payload, before


def _ensure_robot_reference(
    stage: Any,
    *,
    robot_asset_path: Path,
    add_reference_to_stage: Any,
) -> None:
    """Load the robot before overlays can author a valid-looking prim over."""
    robot_path = "/World/Franka"
    robot_prim = stage.GetPrimAtPath(robot_path)
    if not robot_prim or not robot_prim.IsValid():
        add_reference_to_stage(usd_path=str(robot_asset_path.resolve()), prim_path=robot_path)
    robot_prim = stage.GetPrimAtPath(robot_path)
    if not robot_prim or not robot_prim.IsValid():
        raise RuntimeError("nonformal_probe_robot_reference_missing")


def _default_config_path(config_path: Path, entry: Any) -> Path | None:
    if entry == "_self_":
        return None
    if isinstance(entry, str):
        name = entry
    elif isinstance(entry, dict) and len(entry) == 1:
        group, name = next(iter(entry.items()))
        if name is None:
            return None
        if not isinstance(group, str) or not isinstance(name, str):
            raise ValueError("nonformal_probe_config_default_invalid")
        name = f"{group}/{name}"
    else:
        raise ValueError("nonformal_probe_config_default_invalid")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("nonformal_probe_config_default_invalid")
    if relative.suffix not in {"", ".yaml", ".yml"}:
        raise ValueError("nonformal_probe_config_default_invalid")
    if not relative.suffix:
        relative = relative.with_suffix(".yaml")
    return (config_path.parent / relative).resolve()


def load_composed_config(config_path: Path) -> tuple[Any, dict[str, str]]:
    """Compose the small diagnostic YAML default chain and seal every input."""
    from omegaconf import OmegaConf
    import yaml

    closure: dict[str, str] = {}
    active: set[Path] = set()

    def load(path: Path) -> Any:
        path = path.resolve()
        if path in active:
            raise RuntimeError("nonformal_probe_config_default_cycle")
        if not path.is_file():
            raise FileNotFoundError(f"nonformal_probe_config_missing:{path}")
        payload, digest = _stable_file_bytes(path)
        try:
            raw = yaml.safe_load(payload)
        except yaml.YAMLError as exc:
            raise ValueError("nonformal_probe_config_yaml_invalid") from exc
        if not isinstance(raw, dict):
            raise ValueError("nonformal_probe_config_mapping_required")
        closure[str(path)] = digest
        active.add(path)
        try:
            defaults = raw.pop("defaults", [])
            if not isinstance(defaults, list):
                raise ValueError("nonformal_probe_config_defaults_invalid")
            current = OmegaConf.create(raw)
            composed = OmegaConf.create()
            self_merged = False
            for entry in defaults:
                default_path = _default_config_path(path, entry)
                if default_path is None:
                    composed = OmegaConf.merge(composed, current)
                    self_merged = True
                else:
                    composed = OmegaConf.merge(composed, load(default_path))
            if not self_merged:
                composed = OmegaConf.merge(composed, current)
            return composed
        finally:
            active.remove(path)

    return load(config_path), dict(sorted(closure.items()))


def _require_unchanged_input_hashes(
    *,
    input_closure: Mapping[str, str],
) -> None:
    if not input_closure or any(
        not isinstance(path, str) or not _is_sha256(digest)
        for path, digest in input_closure.items()
    ):
        raise ValueError("nonformal_probe_input_closure_invalid")
    for raw_path, digest in input_closure.items():
        path = Path(raw_path)
        if not path.is_file() or _sha256_file(path) != digest:
            raise RuntimeError("nonformal_probe_input_changed_during_run")


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
            "utf-8"
        )
    ).hexdigest()


def _json_native(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_native(value.tolist())
    if hasattr(value, "item"):
        return _json_native(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite_json_value")
    return value


def _write_create_only(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(
        _json_native(value),
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if os.path.exists(path):
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)


def runtime_process_preflight(execution_request: Mapping[str, Any]) -> dict[str, Any]:
    if Path(sys.executable).resolve() != FORMAL_ISAAC41_PYTHON.resolve():
        raise RuntimeError("nonformal_probe_interpreter_mismatch")
    if Path(sys.prefix).resolve() != FORMAL_ISAAC41_PREFIX.resolve():
        raise RuntimeError("nonformal_probe_prefix_mismatch")
    if not _isolated_mode():
        raise RuntimeError("nonformal_probe_isolated_mode_required")
    for name, expected in REQUIRED_ENVIRONMENT.items():
        if os.environ.get(name) != expected:
            raise RuntimeError(f"nonformal_probe_environment_missing:{name}")
    present = [name for name in FORBIDDEN_ENVIRONMENT if os.environ.get(name)]
    if present:
        raise RuntimeError(
            "nonformal_probe_environment_forbidden:" + ",".join(sorted(present))
        )
    if os.environ.get("LD_LIBRARY_PATH") != APPROVED_LD_LIBRARY_PATH:
        raise RuntimeError("nonformal_probe_library_path_invalid")
    if not isinstance(execution_request, Mapping):
        raise RuntimeError("nonformal_probe_execution_request_invalid")
    return {
        "executable": str(FORMAL_ISAAC41_PYTHON),
        "prefix": str(FORMAL_ISAAC41_PREFIX),
        "child_pid": os.getpid(),
        "execution_binding": "same_process_runtime_receipt_v1",
        "library_path": APPROVED_LD_LIBRARY_PATH,
        "library_path_sha256": hashlib.sha256(
            APPROVED_LD_LIBRARY_PATH.encode("utf-8")
        ).hexdigest(),
        "environment": {
            name: os.environ[name]
            for name in (*REQUIRED_ENVIRONMENT, "HOME", "TMPDIR", "XDG_CACHE_HOME")
            if name in os.environ
        },
    }


def _finite_vector(value: Any, *, name: str) -> list[float]:
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"direct_report_{name}_invalid") from exc
    if len(result) != 3 or not all(math.isfinite(item) for item in result):
        raise RuntimeError(f"direct_report_{name}_invalid")
    return result


def _event_name(value: Any) -> str:
    names = {
        "CONTACT_FOUND": "FOUND",
        "CONTACT_PERSIST": "PERSIST",
        "CONTACT_LOST": "LOST",
    }
    values = {0: "FOUND", 1: "LOST", 2: "PERSIST"}
    name = getattr(value, "name", None)
    if name in names:
        return names[name]
    try:
        return values[int(value)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("direct_report_event_invalid") from exc


def _runtime_probe(
    args: argparse.Namespace,
    runtime: dict[str, Any],
    *,
    app: Any,
) -> dict[str, Any]:
    # The sealed child has already bootstrapped and attested this exact app.
    trace_path = args.out_dir / "direct_physx_reports.jsonl.gz"
    trace_stream = None
    trace_digest = hashlib.sha256()
    trace_records = 0
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from isaacsim_compat import install_legacy_isaacsim_aliases

        install_legacy_isaacsim_aliases()
        import numpy as np
        import omni.physx
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleRigidPrim
        from isaacsim.core.utils.stage import add_reference_to_stage
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysxSchema, PhysicsSchemaTools, Sdf, Usd, UsdPhysics, UsdShade, UsdUtils

        from controllers.atomic_actions.contact_pick_controller import (
            ContactPickController,
            ContactPickEvent,
        )
        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from robots.franka.rmpflow_controller import RMPFlowController
        from tools.labutopia_fluid import nonformal_direct_contact
        from utils.fluid_evaluation_loop import fluid_control_dt
        from utils.isaac_fluid_evaluation import (
            PhysicsSourceStateAdapter,
            SourceBodyWriterAudit,
            configure_contact_grasp_scene,
            construct_single_rigid_prim,
            configure_fluid_world_timing,
            configure_particle_usd_readback,
            validate_fluid_stage_contract,
        )
        from utils.object_utils import ObjectUtils
        from utils.controlled_contact import FullContactReportAccumulator
        from utils import nonformal_usd_dependency_resolution as dependency_resolution

        if args.seed is not None:
            import random

            random.seed(args.seed)
            np.random.seed(args.seed)
            try:
                import torch

                torch.manual_seed(args.seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(args.seed)
                torch_seeded = True
            except (ImportError, RuntimeError):
                torch_seeded = False
        else:
            torch_seeded = False
        seed_record = {
            "requested_seed": args.seed,
            "numpy_seeded": args.seed is not None,
            "python_random_seeded": args.seed is not None,
            "torch_seeded": torch_seeded,
            "deterministic_physics_claimed": False,
        }
        cfg, config_closure = load_composed_config(args.config)
        fluid = cfg.online_fluid
        if (
            fluid.enabled is not True
            or str(fluid.source_ownership) != "contact_friction_dynamic_v1"
            or str(fluid.expert_control_profile) != "contact_pick_v1"
            or str(fluid.execution_mode) != "contact_acquisition_probe_v1"
            or str(cfg.task_type) != "pickpour"
        ):
            raise RuntimeError("nonformal_probe_config_contract_invalid")
        asset_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
        if not asset_path.is_file():
            raise FileNotFoundError(f"nonformal_probe_asset_missing:{asset_path}")
        robot_asset_path = (REPO_ROOT / str(cfg.robot.usd_path)).resolve()
        if not robot_asset_path.is_file():
            raise FileNotFoundError(
                f"nonformal_probe_robot_asset_missing:{robot_asset_path}"
            )
        treatment_profile = resolve_treatment_profile(args.treatment_profile)
        dependency_entries = [
            {
                "id": "fixture_asset",
                "path": str(asset_path),
                "sha256": _stable_file_bytes(asset_path)[1],
            },
            {
                "id": "robot_asset",
                "path": str(robot_asset_path),
                "sha256": _stable_file_bytes(robot_asset_path)[1],
            },
            *(
                {"id": item["id"], "path": item["path"], "sha256": item["sha256"]}
                for item in treatment_profile["overlay_stack"]
            ),
        ]
        resolved_dependency_closure_before_world = dependency_resolution.discover(
            dependency_entries,
            repo_root=REPO_ROOT,
            UsdUtils=UsdUtils,
        )
        if resolved_dependency_closure_before_world["unresolved"]:
            raise RuntimeError("nonformal_probe_usd_dependency_unresolved")
        input_closure = {
            **config_closure,
            **{
                item["path"]: item["sha256"]
                for item in resolved_dependency_closure_before_world["files"]
            },
        }
        input_closure = dict(sorted(input_closure.items()))
        input_closure_sha256 = _canonical_json_sha256(input_closure)

        configure_particle_usd_readback()
        stage = omni.usd.get_context().get_stage()
        add_reference_to_stage(usd_path=str(asset_path), prim_path="/World")
        # The finite treatment uses `over /World/Franka`; load the actual robot
        # first so that the overlay cannot mask a missing reference.
        _ensure_robot_reference(
            stage,
            robot_asset_path=robot_asset_path,
            add_reference_to_stage=add_reference_to_stage,
        )
        treatment_session = stage.GetSessionLayer()
        if treatment_session is None:
            raise RuntimeError("nonformal_probe_treatment_session_layer_missing")
        prior_treatment_sublayers = list(treatment_session.subLayerPaths)
        if prior_treatment_sublayers:
            raise RuntimeError("nonformal_probe_treatment_session_layer_not_empty")
        treatment_sublayers = [item["path"] for item in treatment_profile["overlay_stack"]]
        for treatment_sublayer in treatment_sublayers:
            treatment_session.subLayerPaths.append(treatment_sublayer)
        if list(treatment_session.subLayerPaths) != [
            *prior_treatment_sublayers,
            *treatment_sublayers,
        ]:
            raise RuntimeError("nonformal_probe_treatment_sublayer_order_invalid")
        if (
            not stage.GetPrimAtPath(str(fluid.particle_path)).IsValid()
            or not stage.GetPrimAtPath(str(fluid.particle_system_path)).IsValid()
        ):
            raise RuntimeError("nonformal_probe_pbd_prims_missing")
        world = World(
            physics_dt=float(fluid.physics_dt),
            rendering_dt=float(fluid.rendering_dt),
            stage_units_in_meters=1.0,
            physics_prim_path=str(fluid.physics_scene_path),
            set_defaults=False,
            backend="numpy",
            device="cpu",
        )
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
        configure_particle_usd_readback()
        configure_fluid_world_timing(
            world,
            physics_dt=float(fluid.physics_dt),
            rendering_dt=float(fluid.rendering_dt),
        )
        simulation = get_physx_simulation_interface()

        robot = create_robot(
            str(cfg.robot.type),
            position=np.asarray(cfg.robot.position, dtype=np.float64),
            usd_path=str(robot_asset_path),
            camera_frequency=int(cfg.robot.camera_frequency),
        )

        def target_offset_snapshot() -> dict[str, Any]:
            def finite_scalar(attribute: Any) -> float | None:
                if not attribute or not attribute.IsValid():
                    return None
                try:
                    value = float(attribute.Get())
                except (TypeError, ValueError):
                    return None
                return value if math.isfinite(value) else None

            records = []
            for identifier, path in _OFFSET_TARGETS:
                prim = stage.GetPrimAtPath(path)
                if not prim or not prim.IsValid():
                    records.append(
                        {
                            "id": identifier,
                            "path": path,
                            "prim_type": "",
                            "usd_collision_api_applied": False,
                            "physx_collision_api_applied": False,
                            "contact_offset_authored": False,
                            "rest_offset_authored": False,
                            "contact_offset_m": None,
                            "rest_offset_m": None,
                            "contact_offset_strongest_layer": None,
                            "rest_offset_strongest_layer": None,
                            "contact_offset_anonymous_opinion": False,
                            "rest_offset_anonymous_opinion": False,
                        }
                    )
                    continue
                api = PhysxSchema.PhysxCollisionAPI(prim)

                def strongest_layer(attribute: Any) -> str | None:
                    if not attribute or not attribute.IsValid():
                        return None
                    stack = attribute.GetPropertyStack(Usd.TimeCode.Default())
                    if not stack:
                        return None
                    layer = stack[0].layer
                    raw_path = getattr(layer, "realPath", "")
                    return str(Path(raw_path).resolve()) if raw_path else str(layer.identifier)

                def has_anonymous_opinion(attribute: Any) -> bool:
                    if not attribute or not attribute.IsValid():
                        return False
                    return any(
                        bool(getattr(spec.layer, "anonymous", False))
                        for spec in attribute.GetPropertyStack(Usd.TimeCode.Default())
                    )

                contact = api.GetContactOffsetAttr()
                rest = api.GetRestOffsetAttr()
                records.append(
                    {
                        "id": identifier,
                        "path": path,
                        "prim_type": str(prim.GetTypeName()),
                        "usd_collision_api_applied": bool(prim.HasAPI(UsdPhysics.CollisionAPI)),
                        "physx_collision_api_applied": bool(
                            prim.HasAPI(PhysxSchema.PhysxCollisionAPI)
                        ),
                        "contact_offset_authored": bool(
                            contact and contact.HasAuthoredValueOpinion()
                        ),
                        "rest_offset_authored": bool(rest and rest.HasAuthoredValueOpinion()),
                        "contact_offset_m": finite_scalar(contact),
                        "rest_offset_m": finite_scalar(rest),
                        "contact_offset_strongest_layer": strongest_layer(contact),
                        "rest_offset_strongest_layer": strongest_layer(rest),
                        "contact_offset_anonymous_opinion": has_anonymous_opinion(contact),
                        "rest_offset_anonymous_opinion": has_anonymous_opinion(rest),
                    }
                )
            payload = {"records": records}
            return {**payload, "sha256": _canonical_json_sha256(payload)}

        def composed_usd_closure() -> dict[str, Any]:
            layers_by_path: dict[str, dict[str, str]] = {}
            for usd_layer in stage.GetUsedLayers():
                if bool(getattr(usd_layer, "anonymous", False)):
                    continue
                raw_path = getattr(usd_layer, "realPath", "")
                candidate = Path(raw_path) if isinstance(raw_path, str) else None
                if candidate is None or not raw_path or candidate.is_symlink() or not candidate.is_file():
                    raise RuntimeError("nonformal_probe_usd_closure_layer_invalid")
                path = candidate.resolve()
                record = {
                    "identifier": str(usd_layer.identifier),
                    "real_path": str(path),
                    "sha256": _sha256_file(path),
                }
                existing = layers_by_path.get(record["real_path"])
                if existing is not None and existing != record:
                    raise RuntimeError("nonformal_probe_usd_closure_layer_ambiguous")
                layers_by_path[record["real_path"]] = record
            layers = [layers_by_path[path] for path in sorted(layers_by_path)]
            expected_paths = {
                str(asset_path),
                str(robot_asset_path),
                *(item["path"] for item in treatment_profile["overlay_stack"]),
            }
            if not expected_paths <= {item["real_path"] for item in layers}:
                raise RuntimeError("nonformal_probe_usd_closure_direct_input_missing")
            payload = {"layers": layers}
            return {**payload, "sha256": _canonical_json_sha256(payload)}

        def cube_collision_disabled() -> bool:
            cube = stage.GetPrimAtPath("/World/Cube")
            attribute = cube.GetAttribute("physics:collisionEnabled") if cube and cube.IsValid() else None
            return bool(attribute and attribute.IsValid() and attribute.Get() is False)

        session = stage.GetSessionLayer()
        if session is None:
            raise RuntimeError("nonformal_probe_session_layer_missing")
        initial_world_index = int(world.current_time_step_index)
        previous_target = stage.GetEditTarget()
        layer = Sdf.Layer.CreateAnonymous("nonformal_pbd_direct_contact.usda")
        if layer is None:
            raise RuntimeError("nonformal_probe_session_layer_create_failed")
        session.subLayerPaths.insert(0, layer.identifier)
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            # This is the declared physical treatment: finger friction binding.
            configure_contact_grasp_scene(stage, fluid)
            robot_root_path = "/World/Franka"
            robot_root = stage.GetPrimAtPath(robot_root_path)
            if not robot_root or not robot_root.IsValid():
                raise RuntimeError("nonformal_probe_robot_root_missing")
            robot_rigid_body_paths = sorted(
                str(prim.GetPath())
                for prim in Usd.PrimRange(robot_root)
                if prim.HasAPI(UsdPhysics.RigidBodyAPI)
            )
            if not robot_rigid_body_paths:
                raise RuntimeError("nonformal_probe_robot_rigid_bodies_missing")
            report_paths = tuple(
                sorted(
                    {
                        str(fluid.source_actor_path),
                        *robot_rigid_body_paths,
                    }
                )
            )
            for path in report_paths:
                prim = stage.GetPrimAtPath(path)
                if not prim or not prim.IsValid():
                    raise RuntimeError(f"nonformal_probe_report_body_missing:{path}")
                api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
                api.CreateThresholdAttr().Set(0.0)
                api.CreateReportPairsRel().ClearTargets(True)
                if api.GetThresholdAttr().Get() != 0.0 or api.GetReportPairsRel().GetTargets():
                    raise RuntimeError(f"nonformal_probe_report_api_invalid:{path}")
        finally:
            stage.SetEditTarget(previous_target)
        simulation.flush_changes()
        if int(world.current_time_step_index) != initial_world_index:
            raise RuntimeError("nonformal_probe_setup_advanced_physics")
        report_layer_usda = layer.ExportToString()
        report_layer_sha256 = hashlib.sha256(
            report_layer_usda.encode("utf-8")
        ).hexdigest()

        ObjectUtils.get_instance(stage)
        task = create_task(str(cfg.task_type), cfg=cfg, world=world, stage=stage, robot=robot)
        task.reset()
        report_layer_usda_after_reset = layer.ExportToString()
        report_layer_sha256_after_reset = hashlib.sha256(
            report_layer_usda_after_reset.encode("utf-8")
        ).hexdigest()
        offset_snapshot_after_reset = target_offset_snapshot()
        usd_closure_after_reset = composed_usd_closure()
        resolved_dependency_closure_after_reset = dependency_resolution.discover(
            dependency_entries,
            repo_root=REPO_ROOT,
            UsdUtils=UsdUtils,
        )
        cube_collision_disabled_after_reset = cube_collision_disabled()

        def controller_state() -> dict[str, Any] | None:
            # This direct-contact diagnostic has no perception consumer. Avoid
            # camera readback while stepping physics without rendering.
            task.frame_idx += 1
            if not task.check_frame_limits():
                return None
            joint_positions = robot.get_joint_positions()
            gripper_position = robot.get_gripper_position()
            if joint_positions is None or gripper_position is None:
                return None
            return {
                "joint_positions": joint_positions,
                "gripper_position": gripper_position,
            }

        source_root = str(fluid.source_actor_path)
        source_collider = str(fluid.source_external_shell_path)
        source_stage_contract = validate_fluid_stage_contract(stage, fluid)
        source_prim = stage.GetPrimAtPath(source_root)
        source_mesh = stage.GetPrimAtPath(source_collider)
        source_body = construct_single_rigid_prim(
            SingleRigidPrim,
            prim_path=source_root,
            name="nonformal_pbd_direct_contact_source_reader",
        )
        source_body.initialize()

        def source_contract() -> dict[str, Any]:
            rigid_enabled = source_prim.GetAttribute("physics:rigidBodyEnabled").Get()
            kinematic = source_prim.GetAttribute("physics:kinematicEnabled").Get()
            collision_enabled = source_mesh.GetAttribute("physics:collisionEnabled").Get()
            position, orientation = source_body.get_world_pose()
            linear = source_body.get_linear_velocity()
            angular = source_body.get_angular_velocity()
            vectors = (position, orientation, linear, angular)
            values_valid = all(np.isfinite(np.asarray(value, dtype=np.float64)).all() for value in vectors)
            return {
                "rigid_body_enabled": rigid_enabled is not False,
                "kinematic_enabled": kinematic is True,
                "collision_enabled": collision_enabled is True,
                "state_finite": bool(values_valid),
                "position_m": np.asarray(position, dtype=np.float64).tolist(),
                "orientation_wxyz": np.asarray(orientation, dtype=np.float64).tolist(),
                "linear_velocity_m_s": np.asarray(linear, dtype=np.float64).tolist(),
                "angular_velocity_rad_s": np.asarray(angular, dtype=np.float64).tolist(),
            }

        initial_source_contract = source_contract()
        if not (
            initial_source_contract["rigid_body_enabled"]
            and not initial_source_contract["kinematic_enabled"]
            and initial_source_contract["collision_enabled"]
            and initial_source_contract["state_finite"]
        ):
            raise RuntimeError("nonformal_probe_source_dynamic_contract_invalid")
        source_state = PhysicsSourceStateAdapter(
            read_source_world_pose=source_body.get_world_pose,
            initial_geometry_center_world=task.object_utils.get_geometry_center(
                object_path=source_root
            ),
        )
        source_writer_audit = SourceBodyWriterAudit(source_body_path=source_root)
        source_writer_audit.install(source_body=source_body, object_utils=task.object_utils)
        source_writer_audit.reset()

        def enabled_colliders(root_path: str) -> list[str]:
            root = stage.GetPrimAtPath(root_path)
            if not root or not root.IsValid():
                raise RuntimeError(f"nonformal_probe_collider_root_missing:{root_path}")
            paths = []
            for prim in Usd.PrimRange(root):
                if not prim.HasAPI(UsdPhysics.CollisionAPI):
                    continue
                enabled = prim.GetAttribute("physics:collisionEnabled")
                if enabled and enabled.Get() is False:
                    continue
                paths.append(str(prim.GetPath()))
            return sorted(set(paths))

        def owner(collider_path: str) -> str:
            prim = stage.GetPrimAtPath(collider_path)
            while prim and prim.IsValid():
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    return str(prim.GetPath())
                prim = prim.GetParent()
            return collider_path

        # Only the external source shell can substantiate a finger grasp. A
        # finger reaching the interior PBD wrapper is classified as unexpected.
        source_colliders = enabled_colliders(source_collider)
        left_colliders = enabled_colliders(str(fluid.finger_body_paths[0]))
        right_colliders = enabled_colliders(str(fluid.finger_body_paths[1]))
        hand_colliders = enabled_colliders("/World/Franka/panda_hand")
        robot_colliders = enabled_colliders(robot_root_path)
        support_colliders = set(enabled_colliders(str(fluid.table_path)))
        cube = stage.GetPrimAtPath("/World/Cube")
        if cube and cube.IsValid():
            support_colliders.update(enabled_colliders("/World/Cube"))
        named = set(source_colliders + left_colliders + right_colliders + hand_colliders)
        other_robot_colliders = sorted(set(robot_colliders) - named)
        support_colliders.difference_update(named)
        support_colliders.difference_update(other_robot_colliders)
        all_colliders = enabled_colliders("/World")
        other_colliders = sorted(
            set(all_colliders)
            - named
            - set(other_robot_colliders)
            - support_colliders
        )
        known = set(source_colliders + left_colliders + right_colliders + hand_colliders)
        known.update(other_robot_colliders)
        known.update(support_colliders)
        known.update(other_colliders)
        robot_collider_owners = {
            collider: owner(collider) for collider in robot_colliders
        }
        if any(
            body_path not in robot_rigid_body_paths
            for body_path in robot_collider_owners.values()
        ):
            raise RuntimeError("nonformal_probe_robot_collider_owner_invalid")
        identities = {
            "source_colliders": source_colliders,
            "left_colliders": left_colliders,
            "right_colliders": right_colliders,
            "hand_colliders": hand_colliders,
            "other_robot_colliders": other_robot_colliders,
            "support_colliders": sorted(support_colliders),
            "other_colliders": other_colliders,
            "collider_owners": {path: owner(path) for path in sorted(known)},
        }
        if not source_colliders or not left_colliders or not right_colliders:
            raise RuntimeError("nonformal_probe_required_colliders_missing")

        stage_cache_id = UsdUtils.StageCache.Get().GetId(stage)
        stage_id = int(stage_cache_id.ToLongInt())
        identities["stage_id"] = stage_id
        accumulator = FullContactReportAccumulator(
            expected_stage_id=stage_id,
            provisional_background_pairs=[
                (source, support)
                for source in source_colliders
                for support in sorted(support_colliders)
            ],
        )
        event_values = {0: "FOUND", 1: "LOST", 2: "PERSIST"}
        reads = 0
        trace_stream = gzip.open(trace_path, "xb")

        def resolve(identifier: Any) -> str:
            if isinstance(identifier, bool) or not isinstance(identifier, (int, np.integer)):
                raise RuntimeError("direct_report_identifier_invalid")
            path = str(PhysicsSchemaTools.intToSdfPath(int(identifier)))
            if not path:
                raise RuntimeError("direct_report_path_unresolved")
            return path

        def report_sample(physics_index: int, *, bootstrap: bool) -> dict[str, Any]:
            nonlocal reads
            raw = simulation.get_full_contact_report()
            if not isinstance(raw, tuple) or len(raw) != 3:
                raise RuntimeError("direct_report_tuple_invalid")
            raw_headers, raw_points, raw_anchors = raw
            headers = []
            points = []
            anchors = []
            for header in raw_headers:
                name = getattr(header.type, "name", None)
                event = name and {
                    "CONTACT_FOUND": "FOUND",
                    "CONTACT_PERSIST": "PERSIST",
                    "CONTACT_LOST": "LOST",
                }.get(name)
                if event is None:
                    try:
                        event = event_values[int(header.type)]
                    except (KeyError, TypeError, ValueError) as exc:
                        raise RuntimeError("direct_report_event_invalid") from exc
                headers.append(
                    {
                        "type": event,
                        "stage_id": int(header.stage_id),
                        "actor0": resolve(header.actor0),
                        "actor1": resolve(header.actor1),
                        "collider0": resolve(header.collider0),
                        "collider1": resolve(header.collider1),
                        "proto_index0": int(header.proto_index0),
                        "proto_index1": int(header.proto_index1),
                        "contact_data_offset": int(header.contact_data_offset),
                        "num_contact_data": int(header.num_contact_data),
                        "friction_anchors_offset": int(header.friction_anchors_offset),
                        "num_friction_anchors_data": int(header.num_friction_anchors_data),
                    }
                )
            for point in raw_points:
                separation = float(point.separation)
                if not math.isfinite(separation):
                    raise RuntimeError("direct_report_separation_invalid")
                points.append(
                    {
                        "position": _finite_vector(point.position, name="position"),
                        "normal": _finite_vector(point.normal, name="normal"),
                        "impulse": _finite_vector(point.impulse, name="impulse"),
                        "separation": separation,
                        "face_index0": int(point.face_index0),
                        "face_index1": int(point.face_index1),
                        "material0": resolve(point.material0) if int(point.material0) else "__zero__",
                        "material1": resolve(point.material1) if int(point.material1) else "__zero__",
                    }
                )
            for anchor in raw_anchors:
                anchors.append(
                    {
                        "position": _finite_vector(anchor.position, name="anchor_position"),
                        "impulse": _finite_vector(anchor.impulse, name="anchor_impulse"),
                    }
                )
            reads += 1
            report = accumulator.consume(
                physics_index=physics_index,
                headers=headers,
                contact_data=points,
                friction_anchors=anchors,
                allow_provisional_persist_bootstrap=bootstrap,
            )
            report["raw_evidence"] = {
                "headers": headers,
                "contact_data": points,
                "friction_anchors": anchors,
            }
            return report

        def record_direct_report(report: dict[str, Any]) -> dict[str, Any]:
            nonlocal trace_records
            if trace_stream is None:
                raise RuntimeError("nonformal_probe_direct_trace_closed")
            payload = json.dumps(
                _json_native(report),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            trace_stream.write(payload + b"\n")
            trace_digest.update(payload + b"\n")
            trace_records += 1
            return {
                "line": trace_records,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }

        control_dt = fluid_control_dt(
            physics_dt=float(fluid.physics_dt),
            physics_substeps_per_observation=int(fluid.physics_substeps_per_observation),
            rendering_dt=float(fluid.rendering_dt),
        )
        rmp = RMPFlowController(
            name="nonformal_pbd_direct_contact_rmp",
            robot_articulation=robot,
            physics_dt=control_dt,
        )
        pick = ContactPickController(
            name="nonformal_pbd_direct_contact_pick",
            cspace_controller=rmp,
            control_dt=control_dt,
            position_threshold=float(getattr(fluid, "expert_pick_position_threshold_m", 0.005)),
            open_position=float(getattr(fluid, "expert_pick_open_position_m", 0.040)),
            open_position_tolerance=float(
                getattr(fluid, "expert_pick_open_position_tolerance_m", 0.0002)
            ),
            pregrasp_distance=float(getattr(fluid, "expert_pick_pregrasp_distance_m", 0.10)),
            insert_distance=float(getattr(fluid, "expert_pick_insert_distance_m", 0.03)),
            approach_speed=float(getattr(fluid, "expert_pick_approach_speed_m_s", 0.03)),
            close_speed=float(getattr(fluid, "expert_pick_close_speed_m_s", 0.01)),
            lift_speed=float(getattr(fluid, "expert_pick_lift_speed_m_s", 0.05)),
            orientation_threshold_degrees=float(
                getattr(fluid, "expert_pick_orientation_threshold_degrees", 5.0)
            ),
            contact_timeout=float(fluid.grasp_contact_timeout_s),
            control_to_end_effector_matrix_m=np.asarray(
                fluid.rmpflow_control_to_grasp_matrix_m, dtype=np.float64
            ),
            end_effector_frame=str(fluid.grasp_target_frame_name),
            control_frame=str(fluid.rmpflow_control_frame_name),
            finger_joint_indices=tuple(int(index) for index in fluid.finger_joint_indices),
            source_translation_limit=999.0,
            source_tilt_limit_degrees=999.0,
            terminate_after_contact_settle=False,
            require_external_phase_certificates=False,
        )

        physics_index = 0
        history: list[dict[str, Any]] = []
        action_ledger: list[dict[str, Any]] = []
        latest: dict[str, Any] | None = None
        observed = False
        terminal: str | None = None
        terminal_reason: str | None = None

        def source_snapshot() -> dict[str, Any]:
            source_state.capture()
            contract = source_contract()
            center = source_state.center_world()
            center_values = np.asarray(center, dtype=np.float64)
            if center_values.shape != (3,) or not np.isfinite(center_values).all():
                raise RuntimeError("nonformal_probe_source_center_invalid")
            contract["geometry_center_world_m"] = center_values.tolist()
            return contract

        def source_contract_valid(contract: dict[str, Any]) -> bool:
            return bool(
                contract["rigid_body_enabled"]
                and not contract["kinematic_enabled"]
                and contract["collision_enabled"]
                and contract["state_finite"]
            )

        def action_record(action: Any) -> dict[str, Any]:
            record: dict[str, Any] = {}
            for name in (
                "joint_positions",
                "joint_velocities",
                "joint_efforts",
                "joint_indices",
            ):
                value = getattr(action, name, None)
                if value is None:
                    record[name] = None
                    continue
                try:
                    array = np.asarray(value, dtype=np.float64)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(f"nonformal_probe_action_{name}_invalid") from exc
                if array.ndim != 1 or np.isinf(array).any():
                    raise RuntimeError(f"nonformal_probe_action_{name}_invalid")
                if name == "joint_indices":
                    if np.isnan(array).any() or not np.equal(array, np.floor(array)).all():
                        raise RuntimeError(f"nonformal_probe_action_{name}_invalid")
                    record[name] = array.astype(np.int64).tolist()
                    continue
                # Isaac encodes intentionally unspecified sparse joints as NaN.
                record[name] = [
                    None if np.isnan(item) else float(item) for item in array.tolist()
                ]
                record[f"{name}_specified_indices"] = np.flatnonzero(
                    ~np.isnan(array)
                ).astype(np.int64).tolist()
            return record

        def writer_summary(writer: dict[str, Any]) -> dict[str, Any]:
            return {
                "valid": writer["valid"],
                "coverage_complete": writer["coverage_complete"],
                "call_count": writer["call_count"],
                "source_pose_write_count_after_play": writer[
                    "source_pose_write_count_after_play"
                ],
                "source_velocity_write_count_after_play": writer[
                    "source_velocity_write_count_after_play"
                ],
                "object_utils_source_position_write_count_after_play": writer[
                    "object_utils_source_position_write_count_after_play"
                ],
                "kinematic_target_update_count": writer[
                    "kinematic_target_update_count"
                ],
            }

        def step_and_observe(*, phase: str, control_index: int, substep: int) -> dict[str, Any]:
            nonlocal physics_index, latest, observed, terminal, terminal_reason
            pre_source = source_snapshot()
            world.step(render=False)
            report = report_sample(physics_index, bootstrap=physics_index == 0)
            trace_record = record_direct_report(report)
            physics_index += 1
            post_source = source_snapshot()
            writer = source_writer_audit.record()
            latest = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
                report,
                identities=identities,
            )
            if latest["decision"] == "OBSERVED":
                observed = True
            if not source_contract_valid(post_source):
                terminal = "AUDIT_NO_GO"
                terminal_reason = "source_dynamic_contract_invalid_after_play"
            elif writer["valid"] is not True:
                terminal = "AUDIT_NO_GO"
                terminal_reason = "source_writer_audit_invalid"
            elif latest["decision"] == "AUDIT_NO_GO":
                terminal = "AUDIT_NO_GO"
                terminal_reason = "direct_report_audit_no_go"
            history.append(
                {
                    "phase": phase,
                    "control_index": control_index,
                    "substep": substep,
                    "physics_index": physics_index - 1,
                    "source_pre_step": pre_source,
                    "source_post_step": post_source,
                    "source_writer_audit": writer_summary(writer),
                    "direct": latest,
                    "direct_report_trace": trace_record,
                    "full_report_counts": {
                        "headers": report["header_count"],
                        "points": report["contact_data_count"],
                        "anchors": report["friction_anchor_count"],
                        "occurrences": report["occurrence_count"],
                    },
                }
            )
            return latest

        for pre_roll_index in range(int(fluid.dynamic_pre_roll_steps)):
            step_and_observe(
                phase="PRE_ROLL", control_index=-1, substep=pre_roll_index
            )
            if terminal is not None:
                break

        stop_after_pre_roll = getattr(fluid, "stop_after_pre_roll", False)
        if type(stop_after_pre_roll) is not bool:
            raise RuntimeError("nonformal_probe_stop_after_pre_roll_invalid")
        if terminal is None and stop_after_pre_roll:
            terminal = "PRE_ROLL_ONLY_COMPLETE"
            terminal_reason = "configured_stop_after_pre_roll"

        control_index = 0
        while terminal is None and control_index < args.max_control_steps:
            state = controller_state()
            if not isinstance(state, dict):
                terminal = "AUDIT_NO_GO"
                terminal_reason = "task_state_invalid"
                break
            state = source_state(state)
            action = pick.forward(
                source_position=state["object_position"],
                source_orientation_xyzw=state["object_quaternion"],
                current_joint_positions=state["joint_positions"],
                gripper_position=state["gripper_position"],
                end_effector_orientation=np.asarray(
                    fluid.expert_pick_target_orientation_wxyz, dtype=np.float64
                ),
                current_end_effector_orientation=rmp.get_end_effector_orientation_wxyz(),
                approach_direction=np.asarray(
                    getattr(fluid, "expert_pick_approach_direction_world", [0.0, 0.0, -1.0]),
                    dtype=np.float64,
                ),
                grasp_offset=np.asarray(
                    fluid.expert_pick_gripper_offset_object_m, dtype=np.float64
                ),
                lift_height=float(fluid.expert_pick_lift_height_m),
                gripper_distance=float(fluid.grasp_finger_joint_target_m),
                contact_qualified=bool(latest and latest["decision"] == "OBSERVED"),
            )
            evidence = pick.control_evidence()
            action_ledger.append(
                {
                    "control_index": control_index,
                    "evidence": evidence,
                    "action": action_record(action),
                    "applied": True,
                }
            )
            robot.get_articulation_controller().apply_action(action)
            for substep in range(int(fluid.physics_substeps_per_observation)):
                step_and_observe(
                    phase=str(evidence["phase"]),
                    control_index=control_index,
                    substep=substep,
                )
                if terminal is not None:
                    break
            if terminal is None and pick.terminal_failure_reason is not None:
                terminal = "PHYSICAL_FAIL"
                terminal_reason = str(pick.terminal_failure_reason)
            elif terminal is None and pick.is_done():
                terminal = "OBSERVED" if observed else "PHYSICAL_FAIL"
                terminal_reason = (
                    "close_only_direct_contact_observed"
                    if observed
                    else "close_only_direct_contact_not_observed"
                )
            control_index += 1

        if terminal is None:
            terminal = "PHYSICAL_FAIL"
            terminal_reason = "max_control_steps_exhausted"
        final_source = source_snapshot()
        final_writer_audit = source_writer_audit.record()
        report_layer_usda_after_run = layer.ExportToString()
        report_layer_sha256_after_run = hashlib.sha256(
            report_layer_usda_after_run.encode("utf-8")
        ).hexdigest()
        offset_snapshot_after_run = target_offset_snapshot()
        usd_closure_after_run = composed_usd_closure()
        resolved_dependency_closure_after_run = dependency_resolution.discover(
            dependency_entries,
            repo_root=REPO_ROOT,
            UsdUtils=UsdUtils,
        )
        cube_collision_disabled_after_run = cube_collision_disabled()
        if usd_closure_after_reset != usd_closure_after_run:
            terminal = "AUDIT_NO_GO"
            terminal_reason = "usd_dependency_closure_changed_after_reset"
        elif (
            resolved_dependency_closure_before_world
            != resolved_dependency_closure_after_reset
            or resolved_dependency_closure_after_reset != resolved_dependency_closure_after_run
            or resolved_dependency_closure_after_run["unresolved"]
        ):
            terminal = "AUDIT_NO_GO"
            terminal_reason = "resolved_usd_dependency_closure_changed_or_unresolved"
        elif treatment_profile["id"] != "none" and (
            not cube_collision_disabled_after_reset or not cube_collision_disabled_after_run
        ):
            terminal = "AUDIT_NO_GO"
            terminal_reason = "hidden_cube_collision_treatment_invalid"
        if terminal == "OBSERVED" and (
            not source_contract_valid(final_source) or final_writer_audit["valid"] is not True
        ):
            terminal = "AUDIT_NO_GO"
            terminal_reason = "final_source_audit_invalid"
        _require_unchanged_input_hashes(
            input_closure=input_closure,
        )
        if trace_stream is None:
            raise RuntimeError("nonformal_probe_direct_trace_missing")
        trace_stream.close()
        trace_stream = None
        direct_report_trace = {
            "path": str(trace_path),
            "compression": "gzip",
            "encoding": "utf-8",
            "record_format": "one_canonical_full_contact_report_step_v1_per_line",
            "record_count": trace_records,
            "uncompressed_sha256": trace_digest.hexdigest(),
            "compressed_sha256": _sha256_file(trace_path),
            "complete": True,
        }
        report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_direct_contact_probe_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": terminal,
            "runtime": runtime,
            "config": {
                "path": str(args.config),
                "input_closure": input_closure,
                "input_closure_sha256": input_closure_sha256,
                "asset_path": str(asset_path),
                "robot_asset_path": str(robot_asset_path),
            },
            "treatment": {
                "source_ownership": str(fluid.source_ownership),
                "source_dynamic": True,
                "offset_treatment_profile": treatment_profile,
                "seed": seed_record,
                "finger_friction_binding": "session_layer_intentional_treatment",
                "report_layer_identifier": layer.identifier,
                "report_layer_usda": report_layer_usda,
                "report_layer_sha256": report_layer_sha256,
                "report_layer_sha256_after_reset": report_layer_sha256_after_reset,
                "report_layer_sha256_after_run": report_layer_sha256_after_run,
                "report_layer_unchanged_post_reset": (
                    report_layer_usda == report_layer_usda_after_reset == report_layer_usda_after_run
                ),
                "offset_target_snapshot_after_reset": offset_snapshot_after_reset,
                "offset_target_snapshot_after_run": offset_snapshot_after_run,
                "usd_dependency_closure_after_reset": usd_closure_after_reset,
                "usd_dependency_closure_after_run": usd_closure_after_run,
                "resolved_usd_dependency_closure_before_world": resolved_dependency_closure_before_world,
                "resolved_usd_dependency_closure_after_reset": resolved_dependency_closure_after_reset,
                "resolved_usd_dependency_closure_after_run": resolved_dependency_closure_after_run,
                "cube_collision_disabled_after_reset": cube_collision_disabled_after_reset,
                "cube_collision_disabled_after_run": cube_collision_disabled_after_run,
                "source_stage_contract": source_stage_contract,
                "no_source_pose_write_claim": "instrumented_known_surfaces_only",
                "robot_report_inventory": {
                    "robot_root_path": robot_root_path,
                    "rigid_body_paths": robot_rigid_body_paths,
                    "collider_paths": robot_colliders,
                    "collider_owners": robot_collider_owners,
                },
                "camera_observation": "not_requested_by_contact_only_diagnostic",
                "contact_identities": identities,
                "lift_action_applied": any(
                    item["applied"] and item["evidence"]["lift_command_emitted"]
                    for item in action_ledger
                ),
            },
            "result": {
                "observed_bilateral_direct_contact": observed,
                "terminal_reason": terminal_reason,
                "final_pick_evidence": pick.control_evidence(),
                "final_direct": latest,
                "direct_report_read_count": reads,
                "direct_report_trace": direct_report_trace,
                "control_steps": control_index,
                "physics_steps": physics_index,
                "source_initial_contract": initial_source_contract,
                "source_final_state": final_source,
                "source_writer_audit": final_writer_audit,
            },
            "action_ledger": action_ledger,
            "history": history,
        }
        report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_create_only(args.child_report_path, report)
        return report
    except BaseException as exc:
        if trace_stream is not None:
            trace_stream.close()
            trace_stream = None
        report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_direct_contact_probe_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": "RUNTIME_BLOCKED",
            "runtime": runtime,
            "fatal_error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            "direct_report_trace": {
                "path": str(trace_path),
                "compression": "gzip",
                "record_count": trace_records,
                "uncompressed_sha256": trace_digest.hexdigest(),
                "compressed_sha256": (
                    _sha256_file(trace_path) if trace_path.is_file() else None
                ),
                "complete": False,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_create_only(args.child_report_path, report)
        return report
    finally:
        # The sealed-child owner closes the attested SimulationApp.
        pass


def _attestation_module() -> Any:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tools.labutopia_fluid import attest_isaac41_effective_runtime

    return attest_isaac41_effective_runtime


def _blocked_report(runtime: dict[str, Any] | None, exc: BaseException) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "manifest_type": "nonformal_pbd_direct_contact_probe_v2",
        "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
        "decision": "RUNTIME_BLOCKED",
        "runtime": runtime,
        "fatal_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _run_child(args: argparse.Namespace) -> int:
    app = None
    runtime = None
    try:
        attestation = _attestation_module()
        source_paths = _runtime_source_paths(args.config, args.treatment_profile)
        request = attestation._read_canonical_json(args.execution_request)
        request = attestation.verify_execution_request(
            request,
            source_paths=source_paths,
        )
        runtime = runtime_process_preflight(request)
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=request,
            source_paths=source_paths,
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(
            request,
            child_pid=os.getpid(),
        )
        attestation.require_matched_runtime_receipt(
            receipt,
            expected_execution_binding=binding,
        )
        runtime.update(
            {
                "receipt_path": str(args.runtime_receipt_path),
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
                "execution_request_sha256": attestation.canonical_json_sha256(
                    request
                ),
            }
        )
        report = _runtime_probe(args, runtime, app=app)
    except BaseException as exc:
        report = _blocked_report(runtime, exc)
    finally:
        if app is not None:
            app.close()
    if not args.child_report_path.exists():
        _write_create_only(args.child_report_path, report)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _run_parent(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, mode=0o700)
    attestation = _attestation_module()
    source_paths = _runtime_source_paths(args.config, args.treatment_profile)
    source_before = attestation.capture_source_identity(source_paths)
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.out_dir / "execution_request.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.out_dir / "runtime")
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--config",
        str(args.config),
        "--out-dir",
        str(args.out_dir),
        "--max-control-steps",
        str(args.max_control_steps),
        "--treatment-profile",
        str(args.treatment_profile),
        "--execution-request",
        str(request_path),
    ]
    if args.seed is not None:
        command.extend(("--seed", str(args.seed)))
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    child_pid = None
    child_returncode = None
    verification_failure = None
    child_report = None
    receipt = None
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
                child_returncode = process.wait(timeout=args.timeout_s)
            except subprocess.TimeoutExpired:
                process.kill()
                child_returncode = process.wait()
                raise RuntimeError("nonformal_probe_child_timeout")
        child_report = json.loads(args.child_report_path.read_text(encoding="utf-8"))
        if not isinstance(child_report, Mapping):
            raise RuntimeError("nonformal_probe_child_report_invalid")
        receipt = attestation._read_canonical_json(args.runtime_receipt_path)
        expected_binding = attestation.execution_binding_for_request(
            request,
            child_pid=child_pid,
        )
        attestation.require_matched_runtime_receipt(
            receipt,
            expected_execution_binding=expected_binding,
        )
        child_runtime = child_report.get("runtime")
        if (
            not isinstance(child_runtime, Mapping)
            or child_runtime.get("receipt_sha256")
            != attestation.canonical_json_sha256(receipt)
            or child_runtime.get("execution_binding") != expected_binding
        ):
            raise RuntimeError("nonformal_probe_child_runtime_binding_invalid")
        if child_returncode != (2 if child_report.get("decision") == "RUNTIME_BLOCKED" else 0):
            raise RuntimeError("nonformal_probe_child_exit_status_invalid")
        report = dict(child_report)
        report["parent_verification"] = {
            "execution_request_sha256": attestation.canonical_json_sha256(request),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "child_report_path": str(args.child_report_path),
            "child_report_sha256": _sha256_file(args.child_report_path),
            "runtime_receipt_sha256": attestation.canonical_json_sha256(receipt),
            "stdout_sha256": _sha256_file(stdout_path),
            "stderr_sha256": _sha256_file(stderr_path),
            "verified": True,
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = _blocked_report(None, exc)
        report["parent_verification"] = {
            "execution_request_sha256": attestation.canonical_json_sha256(request),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "child_report_path": str(args.child_report_path),
            "child_report_sha256": (
                _sha256_file(args.child_report_path)
                if args.child_report_path.is_file()
                else None
            ),
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None
            ),
            "stdout_sha256": _sha256_file(stdout_path) if stdout_path.is_file() else None,
            "stderr_sha256": _sha256_file(stderr_path) if stderr_path.is_file() else None,
            "verified": False,
        }
    finally:
        source_after = attestation.capture_source_identity(source_paths)
        manifest = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_direct_contact_parent_manifest_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "command": command,
            "execution_request_sha256": attestation.canonical_json_sha256(request),
            "source_before": source_before,
            "source_after": source_after,
            "sanitized_environment_sha256": attestation.canonical_json_sha256(
                dict(sorted(environment.items()))
            ),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "stdout_sha256": _sha256_file(stdout_path) if stdout_path.is_file() else None,
            "stderr_sha256": _sha256_file(stderr_path) if stderr_path.is_file() else None,
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None
            ),
            "child_report_sha256": (
                _sha256_file(args.child_report_path)
                if args.child_report_path.is_file()
                else None
            ),
            "verification_failure": verification_failure,
        }
        attestation.write_canonical_json(args.out_dir / "run_manifest.json", manifest)
    _write_create_only(args.out_dir / "report.json", report)
    print(
        f"nonformal pbd direct contact decision={report['decision']} out={args.out_dir / 'report.json'}",
        flush=True,
    )
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-control-steps", type=int, default=600)
    parser.add_argument("--timeout-s", type=float, default=1800.0)
    parser.add_argument("--treatment-profile", type=str, default="none")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file():
        parser.error("config must exist")
    if args.max_control_steps <= 0 or not math.isfinite(args.timeout_s) or args.timeout_s <= 0.0:
        parser.error("max-control-steps and timeout-s must be positive")
    if args.seed is not None and args.seed < 0:
        parser.error("seed must be nonnegative")
    try:
        resolve_treatment_profile(args.treatment_profile)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    if args.child:
        if args.execution_request is None:
            parser.error("--child requires --execution-request")
        args.execution_request = args.execution_request.resolve()
        if not args.execution_request.is_file() or not args.out_dir.is_dir():
            parser.error("child execution request and out-dir must exist")
    else:
        if args.execution_request is not None:
            parser.error("--execution-request is child-only")
        if args.out_dir.exists():
            parser.error("out-dir must not exist")
    args.child_report_path = args.out_dir / "child_report.json"
    args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_child(args) if args.child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())

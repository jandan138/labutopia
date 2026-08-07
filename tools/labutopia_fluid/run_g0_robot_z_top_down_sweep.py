#!/usr/bin/env python3
"""Quick G0 sweep: test robot base Z heights for top-down clearance."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)

SWEEP_Z_VALUES = (0.71, 0.80, 0.90, 1.00, 1.10, 1.20, 1.35, 1.50)
OUT_DIR = REPO_ROOT / "artifacts/runs/g0-robot-z-sweep-top-down"

CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_contact_pick_top_down_"
    "g2_600hz_step600_layout_v1.yaml"
)
HIDDEN_CUBE_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_disable_hidden_cube_collision_v1.usda"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as s:
        for c in iter(lambda: s.read(1024 * 1024), b""):
            digest.update(c)
    return digest.hexdigest()


def _runtime_probe(z: float, out_path: Path) -> None:
    """Start Isaac, load scene at robot Z, run PREGRASP phase with PhysX reports, check for env contact."""
    import sys as _sys
    if str(REPO_ROOT) not in _sys.path:
        _sys.path.insert(0, str(REPO_ROOT))
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True, "width": 64, "height": 64})
    try:
        from isaacsim_compat import install_legacy_isaacsim_aliases
        install_legacy_isaacsim_aliases()

        import numpy as np
        import omni.physx
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.utils.stage import add_reference_to_stage
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysxSchema, PhysicsSchemaTools, Sdf, Usd, UsdPhysics, UsdUtils

        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from robots.franka.rmpflow_controller import RMPFlowController
        from utils.isaac_fluid_evaluation import (
            configure_contact_grasp_scene,
            configure_fluid_world_timing,
            configure_particle_usd_readback,
        )
        from utils.object_utils import ObjectUtils
        from omegaconf import OmegaConf

        cfg = OmegaConf.load(str(CONFIG))
        fluid = cfg.online_fluid
        asset_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
        robot_asset_path = (REPO_ROOT / str(cfg.robot.usd_path)).resolve()

        configure_particle_usd_readback()
        stage = omni.usd.get_context().get_stage()
        add_reference_to_stage(usd_path=str(asset_path), prim_path="/World")

        robot_prim = stage.GetPrimAtPath("/World/Franka")
        if not robot_prim or not robot_prim.IsValid():
            add_reference_to_stage(usd_path=str(robot_asset_path), prim_path="/World/Franka")

        session = stage.GetSessionLayer()
        session.subLayerPaths.append(str(HIDDEN_CUBE_OVERLAY.resolve()))

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
            world, physics_dt=float(fluid.physics_dt), rendering_dt=float(fluid.rendering_dt)
        )
        simulation = get_physx_simulation_interface()

        robot = create_robot(
            str(cfg.robot.type),
            position=np.asarray([cfg.robot.position[0], cfg.robot.position[1], z], dtype=np.float64),
            usd_path=str(robot_asset_path),
            camera_frequency=int(cfg.robot.camera_frequency),
        )

        session2 = stage.GetSessionLayer()
        layer = Sdf.Layer.CreateAnonymous("g0_sweep.usda")
        session2.subLayerPaths.insert(0, layer.identifier)
        previous_target = stage.GetEditTarget()
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            configure_contact_grasp_scene(stage, fluid)
            robot_root_path = "/World/Franka"
            robot_root = stage.GetPrimAtPath(robot_root_path)
            robot_rigid_body_paths = sorted(
                str(prim.GetPath())
                for prim in Usd.PrimRange(robot_root)
                if prim.HasAPI(UsdPhysics.RigidBodyAPI)
            )
            report_paths = tuple(sorted({str(fluid.source_actor_path), *robot_rigid_body_paths}))
            for path in report_paths:
                prim = stage.GetPrimAtPath(path)
                if not prim or not prim.IsValid():
                    continue
                api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
                api.CreateThresholdAttr().Set(0.0)
        finally:
            stage.SetEditTarget(previous_target)
        simulation.flush_changes()

        ObjectUtils.get_instance(stage)
        task = create_task(str(cfg.task_type), cfg=cfg, world=world, stage=stage, robot=robot)
        task.reset()

        control_dt = float(fluid.rendering_dt)
        rmp = RMPFlowController(
            name="g0_sweep_rmp",
            robot_articulation=robot,
            physics_dt=control_dt,
        )

        from controllers.atomic_actions.contact_pick_controller import (
            ContactPickController,
            ContactPickEvent,
        )
        pick = ContactPickController(
            name="g0_sweep_pick",
            cspace_controller=rmp,
            control_dt=control_dt,
            position_threshold=float(getattr(fluid, "expert_pick_position_threshold_m", 0.005)),
            open_position=float(getattr(fluid, "expert_pick_open_position_m", 0.040)),
            open_position_tolerance=float(getattr(fluid, "expert_pick_open_position_tolerance_m", 0.0002)),
            pregrasp_distance=float(getattr(fluid, "expert_pick_pregrasp_distance_m", 0.10)),
            insert_distance=float(getattr(fluid, "expert_pick_insert_distance_m", 0.03)),
            approach_speed=float(getattr(fluid, "expert_pick_approach_speed_m_s", 0.03)),
            close_speed=float(getattr(fluid, "expert_pick_close_speed_m_s", 0.01)),
            lift_speed=float(getattr(fluid, "expert_pick_lift_speed_m_s", 0.05)),
            orientation_threshold_degrees=float(getattr(fluid, "expert_pick_orientation_threshold_degrees", 5.0)),
            contact_timeout=float(fluid.grasp_contact_timeout_s),
            control_to_end_effector_matrix_m=np.asarray(
                fluid.rmpflow_control_to_grasp_matrix_m, dtype=np.float64
            ),
            end_effector_frame=str(fluid.grasp_target_frame_name),
            control_frame=str(fluid.rmpflow_control_frame_name),
            finger_joint_indices=tuple(int(index) for index in fluid.finger_joint_indices),
            source_translation_limit=float(fluid.grasp_preclose_source_translation_limit_m),
            source_tilt_limit_degrees=float(fluid.grasp_preclose_source_tilt_limit_degrees),
            terminate_after_contact_settle=True,
            require_external_phase_certificates=False,
        )

        source_root = str(fluid.source_actor_path)
        source_body = stage.GetPrimAtPath(source_root)
        source_pos, source_ori = (
            source_body.GetAttribute("xformOp:translate").Get()
            if source_body and source_body.IsValid() else None
        ), None
        if source_pos is None:
            raise RuntimeError("source_xform_missing")

        robot_colliders = set()
        robot_root_prim = stage.GetPrimAtPath(robot_root_path)
        for prim in Usd.PrimRange(robot_root_prim):
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                enabled = prim.GetAttribute("physics:collisionEnabled")
                if not enabled or enabled.Get() is not False:
                    robot_colliders.add(str(prim.GetPath()))

        max_steps = 300
        latest = None
        robot_env_contact = False
        for step in range(max_steps):
            joint_positions = robot.get_joint_positions()
            gripper_position = robot.get_gripper_position()
            if joint_positions is None or gripper_position is None:
                break
            source_state = np.asarray(source_pos, dtype=np.float64).tolist()
            source_ori_xyzw = (
                np.asarray(source_ori, dtype=np.float64).tolist()
                if source_ori is not None
                else [1.0, 0.0, 0.0, 0.0]
            )
            action = pick.forward(
                source_position=source_state,
                source_orientation_xyzw=source_ori_xyzw,
                current_joint_positions=joint_positions,
                gripper_position=gripper_position,
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
                contact_qualified=False,
            )
            robot.get_articulation_controller().apply_action(action)
            world.step(render=False)
            raw = simulation.get_full_contact_report()
            headers = raw[0] if isinstance(raw, tuple) and len(raw) == 3 else []
            for header in headers:
                c0 = str(PhysicsSchemaTools.intToSdfPath(int(header.collider0)))
                c1 = str(PhysicsSchemaTools.intToSdfPath(int(header.collider1)))
                if not c0 or not c1:
                    continue
                c0_robot = c0.startswith("/World/Franka")
                c1_robot = c1.startswith("/World/Franka")
                if c0_robot == c1_robot:
                    continue
                if c0_robot and c0 not in robot_colliders:
                    continue
                if c1_robot and c1 not in robot_colliders:
                    continue
                robot_env_contact = True
                break
            evidence = pick.control_evidence()
            if robot_env_contact or pick.terminal_failure_reason is not None:
                break
            if evidence["phase"] not in ("PREGRASP",):
                break

        app.close()
        result = {
            "robot_z": z,
            "cleared": not robot_env_contact,
            "terminal_failure": pick.terminal_failure_reason,
            "phase_at_end": pick.control_evidence()["phase"],
            "steps": step + 1,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
        print(f"  z={z:.2f}: cleared={not robot_env_contact} phase={result['phase_at_end']} steps={result['steps']}", flush=True)
    except BaseException as exc:
        result = {"robot_z": z, "error": str(exc), "cleared": False}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
        print(f"  z={z:.2f}: ERROR {exc}", flush=True)
        try:
            app.close()
        except BaseException:
            pass


def _child_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--z", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    _runtime_probe(args.z, args.out)
    return 0


def _parent_main() -> int:
    OUT_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    results = []
    for z in SWEEP_Z_VALUES:
        out_dir = OUT_DIR / f"z-{z:.2f}".replace(".", "p")
        out_dir.mkdir(mode=0o700, exist_ok=True)
        out_path = out_dir / "result.json"
        if out_path.exists() and json.loads(out_path.read_text()).get("cleared") is False:
            continue
        cmd = [
            str(FORMAL_ISAAC41_PYTHON),
            "-I", "-B",
            str(Path(__file__).resolve()),
            "--z", str(z),
            "--out", str(out_path),
        ]
        import subprocess, signal
        p = subprocess.Popen(cmd, cwd=REPO_ROOT)
        try:
            rc = p.wait(timeout=300)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        if out_path.exists():
            results.append(json.loads(out_path.read_text()))
    manifest = {"sweep": list(SWEEP_Z_VALUES), "results": results}
    import json as _json
    (OUT_DIR / "manifest.json").write_text(_json.dumps(manifest, indent=2, sort_keys=True))
    cleared = [r for r in results if r.get("cleared")]
    print(f"\nTotal: {len(results)} tested, {len(cleared)} cleared")
    for r in cleared:
        print(f"  Z={r['robot_z']:.2f}: cleared at phase={r.get('phase_at_end')} steps={r.get('steps')}")
    return 0


if __name__ == "__main__":
    if "--z" in sys.argv:
        raise SystemExit(_child_main())
    raise SystemExit(_parent_main())

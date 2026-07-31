#!/usr/bin/env python3
"""Shadow-sweep + filled-lift experiment: record a collision-free trajectory, then 
replay it with source collision enabled to test friction-based lift."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
FINITE_OFFSET_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_finite_target_offsets_calibration_v2.usda"
)


def _run(args: argparse.Namespace) -> None:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "width": 64, "height": 64})
    result: dict[str, Any] = {}
    try:
        from isaacsim_compat import install_legacy_isaacsim_aliases
        install_legacy_isaacsim_aliases()

        import numpy as np
        import omni.physx
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.utils.stage import add_reference_to_stage
        from pxr import Sdf, Usd, UsdPhysics
        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from robots.franka.rmpflow_controller import RMPFlowController
        from utils.isaac_fluid_evaluation import (
            configure_contact_grasp_scene,
            configure_fluid_world_timing,
            configure_particle_usd_readback,
        )
        from utils.object_utils import ObjectUtils
        from controllers.atomic_actions.contact_pick_controller import ContactPickController
        from omegaconf import OmegaConf

        cfg = OmegaConf.load(str(CONFIG))
        fluid = cfg.online_fluid
        asset_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
        robot_path = (REPO_ROOT / str(cfg.robot.usd_path)).resolve()

        # --- Phase 0: Setup ---
        configure_particle_usd_readback()
        stage = omni.usd.get_context().get_stage()
        add_reference_to_stage(usd_path=str(asset_path), prim_path="/World")
        robot_prim = stage.GetPrimAtPath("/World/Franka")
        if not robot_prim or not robot_prim.IsValid():
            add_reference_to_stage(usd_path=str(robot_path), prim_path="/World/Franka")
        session = stage.GetSessionLayer()
        session.subLayerPaths.append(str(HIDDEN_CUBE_OVERLAY.resolve()))
        if args.finite_offset:
            session.subLayerPaths.append(str(FINITE_OFFSET_OVERLAY.resolve()))

        world = World(
            physics_dt=float(fluid.physics_dt),
            rendering_dt=float(fluid.rendering_dt),
            stage_units_in_meters=1.0,
            physics_prim_path=str(fluid.physics_scene_path),
            set_defaults=False, backend="numpy", device="cpu",
        )
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
        configure_particle_usd_readback()
        configure_fluid_world_timing(world, physics_dt=float(fluid.physics_dt), rendering_dt=float(fluid.rendering_dt))
        robot = create_robot(str(cfg.robot.type), position=np.asarray(cfg.robot.position, dtype=np.float64), usd_path=str(robot_path), camera_frequency=int(cfg.robot.camera_frequency))

        session2 = stage.GetSessionLayer()
        layer = Sdf.Layer.CreateAnonymous("lift_experiment.usda")
        session2.subLayerPaths.insert(0, layer.identifier)
        prev = stage.GetEditTarget()
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            configure_contact_grasp_scene(stage, fluid)
        finally:
            stage.SetEditTarget(prev)
        world.reset()
        ObjectUtils.get_instance(stage)
        task = create_task(str(cfg.task_type), cfg=cfg, world=world, stage=stage, robot=robot)
        task.reset()

        control_dt = float(fluid.rendering_dt)
        rmp = RMPFlowController(name="lift_rmp", robot_articulation=robot, physics_dt=control_dt)
        pick = ContactPickController(
            name="lift_pick", cspace_controller=rmp, control_dt=control_dt,
            position_threshold=float(getattr(fluid, "expert_pick_position_threshold_m", 0.005)),
            open_position=float(getattr(fluid, "expert_pick_open_position_m", 0.040)),
            open_position_tolerance=float(getattr(fluid, "expert_pick_open_position_tolerance_m", 0.0002)),
            pregrasp_distance=float(getattr(fluid, "expert_pick_pregrasp_distance_m", 0.10)),
            insert_distance=float(getattr(fluid, "expert_pick_insert_distance_m", 0.03)),
            approach_speed=float(getattr(fluid, "expert_pick_approach_speed_m_s", 0.003)),
            close_speed=float(getattr(fluid, "expert_pick_close_speed_m_s", 0.003)),
            lift_speed=float(getattr(fluid, "expert_pick_lift_speed_m_s", 0.05)),
            orientation_threshold_degrees=float(getattr(fluid, "expert_pick_orientation_threshold_degrees", 5.0)),
            contact_timeout=float(fluid.grasp_contact_timeout_s),
            control_to_end_effector_matrix_m=np.asarray(fluid.rmpflow_control_to_grasp_matrix_m, dtype=np.float64),
            end_effector_frame=str(fluid.grasp_target_frame_name),
            control_frame=str(fluid.rmpflow_control_frame_name),
            finger_joint_indices=tuple(int(i) for i in fluid.finger_joint_indices),
            source_translation_limit=999.0, source_tilt_limit_degrees=999.0,
            terminate_after_contact_settle=False,
            require_external_phase_certificates=False,
        )

        source_root = str(fluid.source_actor_path)
        source_prim = stage.GetPrimAtPath(source_root)
        source_pos = float('nan')
        if source_prim and source_prim.IsValid():
            attr = source_prim.GetAttribute("xformOp:translate")
            if attr and attr.IsValid():
                source_pos = float(np.asarray(attr.Get(), dtype=np.float64)[2])
        source_collider = str(fluid.source_external_shell_path)
        source_collider_prim = stage.GetPrimAtPath(source_collider)

        # --- Phase 1: Shadow sweep (disable source collision, record trajectory) ---
        if source_collider_prim and source_collider_prim.IsValid():
            source_collider_prim.GetAttribute("physics:collisionEnabled").Set(False)

        pre_roll = int(fluid.dynamic_pre_roll_steps)
        for _ in range(pre_roll):
            world.step(render=False)

        trajectory: list[list[float]] = []
        max_steps = 500
        for step in range(max_steps):
            jp = robot.get_joint_positions()
            gp = robot.get_gripper_position()
            if jp is None or gp is None:
                break
            if trajectory:
                trajectory.append(jp.tolist())
            s_pos = np.asarray(attr.Get(), dtype=np.float64).tolist()
            s_ori = [1.0, 0.0, 0.0, 0.0]
            action = pick.forward(
                source_position=s_pos, source_orientation_xyzw=s_ori,
                current_joint_positions=jp, gripper_position=gp,
                end_effector_orientation=np.asarray(fluid.expert_pick_target_orientation_wxyz, dtype=np.float64),
                current_end_effector_orientation=rmp.get_end_effector_orientation_wxyz(),
                approach_direction=np.asarray(getattr(fluid, "expert_pick_approach_direction_world", [0.0, 0.0, -1.0]), dtype=np.float64),
                grasp_offset=np.asarray(fluid.expert_pick_gripper_offset_object_m, dtype=np.float64),
                lift_height=float(fluid.expert_pick_lift_height_m),
                gripper_distance=float(fluid.grasp_finger_joint_target_m),
                contact_qualified=False,
            )
            if action is not None:
                robot.get_articulation_controller().apply_action(action)
            world.step(render=False)
            if pick.control_evidence()["phase"] in ("HOLD",):
                break

        shadow_phases = list(set(pick.control_evidence().get("phase_sequence", [])))
        result["shadow"] = {
            "steps": len(trajectory),
            "phases": shadow_phases,
            "final_phase": pick.control_evidence()["phase"],
            "terminal_failure": pick.terminal_failure_reason,
            "trajectory_length": len(trajectory),
        }

        # --- Phase 2: Filled replay ---
        if source_collider_prim and source_collider_prim.IsValid():
            source_collider_prim.GetAttribute("physics:collisionEnabled").Set(True)

        world.reset()
        task.reset()
        for _ in range(pre_roll):
            world.step(render=False)

        source_z_before = float(np.asarray(attr.Get(), dtype=np.float64)[2]) if attr and attr.IsValid() else None
        for jp_list in trajectory:
            jp = np.asarray(jp_list, dtype=np.float64)
            robot.get_articulation_controller().apply_action(
                robot.get_articulation_controller().forward(joint_positions=jp)
            )
            world.step(render=False)

        source_z_after = float(np.asarray(attr.Get(), dtype=np.float64)[2]) if attr and attr.IsValid() else None
        result["filled"] = {
            "source_z_before": source_z_before,
            "source_z_after": source_z_after,
            "source_z_delta": (source_z_after - source_z_before) if source_z_before is not None and source_z_after is not None else None,
        }

    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        try:
            app.close()
        except BaseException:
            pass
    result["finite_offset"] = args.finite_offset
    result["config"] = str(CONFIG)
    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    delta = result.get("filled", {}).get("source_z_delta")
    label = "FINITE" if args.finite_offset else "BASELINE"
    print(f"{label}: shadow={result['shadow']['steps']}steps, src_dz={delta}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--finite-offset", action="store_true")
    parser.add_argument("--out-path", type=Path, required=True)
    args = parser.parse_args()
    _run(args)

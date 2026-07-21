import os
import sys
import argparse
import importlib.util
import time
from isaacsim import SimulationApp

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def ensure_project_root_on_path():
    sys.path[:] = [path for path in sys.path if path != PROJECT_ROOT]
    sys.path.insert(0, PROJECT_ROOT)


def ensure_project_utils_package():
    package_dir = os.path.join(PROJECT_ROOT, "utils")
    init_path = os.path.join(package_dir, "__init__.py")
    current = sys.modules.get("utils")
    current_file = os.path.abspath(getattr(current, "__file__", "")) if current else ""
    if current_file == os.path.abspath(init_path):
        return

    spec = importlib.util.spec_from_file_location(
        "utils",
        init_path,
        submodule_search_locations=[package_dir],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["utils"] = module
    spec.loader.exec_module(module)


ensure_project_root_on_path()

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='LabSim Simulation Environment')
    parser.add_argument('--backend', type=str, default='numpy', 
                       choices=['numpy', 'gpu'], 
                       help='Backend choice: numpy (CPU) or gpu')
    parser.add_argument('--headless', action='store_true', 
                       help='Run in headless mode (default is with GUI)')
    parser.add_argument('--no-video', action='store_true',
                       help='Disable video display and saving')
    parser.add_argument('--video-dir', type=str, default=None,
                       help='Directory for saved episode videos (default: <run_dir>/video)')
    parser.add_argument('--config-name', type=str, default='level3_HeatLiquid',
                       help='Configuration file name (without .yaml extension)')
    parser.add_argument('--config-dir', type=str, default='config',
                       help='Configuration directory path (default: config)')
    parser.add_argument('--ebench-action-log-dir', type=str, default=None,
                       help='Optional directory for candidate EBench replay action JSONL')
    parser.add_argument('--ebench-action-worker-id', type=str, default='0',
                       help='Worker id written into candidate EBench replay actions')
    parser.add_argument('--ebench-action-expected-dim', type=int, default=9,
                       help='Expected joint_position action dimension for EBench replay logging')
    parser.add_argument('--ebench-action-allow-prefix-dim', action='store_true',
                       help='Allow shorter prefix joint_position actions to be expanded with observed tail joints')
    parser.add_argument('--max-fluid-observations', type=int, default=None,
                       help='Stop online-fluid mode cleanly after this many model observations')
    parser.add_argument('--fluid-evidence-dir', type=str, default=None,
                       help='Optional directory that also receives exact model-camera PNG evidence')
    parser.add_argument(
        '--fluid-presentation-video-dir',
        type=str,
        default=None,
        help='Optional directory for synchronized per-camera presentation videos',
    )
    return parser.parse_args()

# Get command line arguments
args = parse_args()

# Set up simulation app based on arguments
simulation_config = {
    "headless": args.headless,
    "extra_args": ["--/rtx/raytracing/fractionalCutoutOpacity=true"],
}

simulation_app = SimulationApp(simulation_config)

ensure_project_root_on_path()
from isaacsim_compat import install_legacy_isaacsim_aliases

install_legacy_isaacsim_aliases()

import hydra
from omegaconf import OmegaConf
import cv2
ensure_project_root_on_path()
ensure_project_utils_package()
import numpy as np

import omni
from isaacsim.core.api import World
from isaacsim.core.utils.stage import add_reference_to_stage
import omni.usd
from isaacsim.core.utils import extensions

extensions.enable_extension("omni.physx.bundle")
extensions.enable_extension("omni.usdphysics.ui")

from factories.robot_factory import create_robot
from utils.object_utils import ObjectUtils
from utils.ebench_replay_action_source import EbenchReplayActionLogger
from factories.task_factory import create_task
from factories.controller_factory import create_controller
from utils.isaac_fluid_evaluation import (
    author_synthetic_attachment_collision_filter,
    build_isaac_fluid_evaluation_loop,
    configure_contact_grasp_scene,
    configure_particle_usd_readback,
    fluid_rotation_handoff_requested,
)
from utils.fluid_evaluation_loop import (
    append_fluid_episode_evidence,
    append_fluid_observation_evidence,
    execute_controlled_action_transaction,
    initialize_controller_after_task_reset,
    model_camera_video_rgb,
    observation_limit_failure_reason,
    observation_limit_reached,
    observation_limit_termination_reason,
    observation_video_fps,
    online_fluid_run_complete,
    prepare_fluid_evidence_directory,
    reset_task_then_controller,
    validate_controlled_terminal_transition,
)
from utils.presentation_video import build_isaac_presentation_video_recorder


def _online_fluid_enabled(cfg):
    online_fluid = getattr(cfg, "online_fluid", None)
    return bool(online_fluid and getattr(online_fluid, "enabled", False))


def _controlled_contact_mode(cfg):
    if not _online_fluid_enabled(cfg):
        return False
    fluid = cfg.online_fluid
    return bool(
        str(getattr(fluid, "expert_control_profile", ""))
        == "contact_pick_v1"
        and str(getattr(fluid, "execution_mode", ""))
        == "contact_acquisition_probe_v1"
    )


def _close_controlled_runtime(task_controller, simulation_app):
    try:
        task_controller.close()
    finally:
        try:
            simulation_app.close()
        finally:
            cv2.destroyAllWindows()


def _create_fluid_world(cfg, stage):
    if args.backend != "gpu":
        raise ValueError("online_fluid_requires_backend_gpu")
    fluid = cfg.online_fluid
    configure_particle_usd_readback()
    add_reference_to_stage(usd_path=os.path.abspath(cfg.usd_path), prim_path="/World")
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
    return world

def main():
    hydra.initialize(config_path=args.config_dir, job_name=args.config_name)
    cfg = hydra.compose(config_name=args.config_name)
    fluid_enabled = _online_fluid_enabled(cfg)
    controlled_contact_loop_mode = _controlled_contact_mode(cfg)
    fluid_evidence_dir = os.path.abspath(
        args.fluid_evidence_dir
        or os.path.join(cfg.multi_run.run_dir, "online_fluid_evidence")
    )
    if fluid_enabled:
        prepare_fluid_evidence_directory(fluid_evidence_dir)
    os.makedirs(cfg.multi_run.run_dir, exist_ok=True)
    OmegaConf.save(cfg, cfg.multi_run.run_dir + "/config.yaml")

    if args.max_fluid_observations is not None and not fluid_enabled:
        raise ValueError("max_fluid_observations_requires_online_fluid")
    if args.max_fluid_observations is not None:
        observation_limit_reached(0, args.max_fluid_observations)
    if args.fluid_presentation_video_dir and not fluid_enabled:
        raise ValueError("fluid_presentation_video_requires_online_fluid")
    if args.fluid_presentation_video_dir and args.no_video:
        raise ValueError("fluid_presentation_video_conflicts_with_no_video")
    stage = omni.usd.get_context().get_stage()
    if fluid_enabled:
        world = _create_fluid_world(cfg, stage)
    elif args.backend == 'gpu':
        world = World(stage_units_in_meters=1, device="cpu")
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
    else:
        world = World(stage_units_in_meters=1.0, physics_prim_path="/physicsScene", backend="numpy")
    
    # Override configuration based on command line arguments
    if args.no_video:
        save_video = False
        show_video = False
    else:
        save_video = True
        show_video = not args.headless
    video_output_dir = args.video_dir or os.path.join(cfg.multi_run.run_dir, "video")
    ebench_action_logger = None
    if args.ebench_action_log_dir:
        ebench_action_logger = EbenchReplayActionLogger(
            output_dir=args.ebench_action_log_dir,
            worker_id=args.ebench_action_worker_id,
            expected_action_dim=args.ebench_action_expected_dim,
            task_config_path=os.path.join(args.config_dir, f"{args.config_name}.yaml"),
            controller_type=str(cfg.controller_type),
            run_id=os.path.basename(os.path.abspath(args.ebench_action_log_dir)),
            allow_prefix_joint_positions=args.ebench_action_allow_prefix_dim,
        )

    robot_kwargs = {"position": np.array(cfg.robot.position)}
    robot_usd_path = getattr(cfg.robot, "usd_path", None)
    if robot_usd_path:
        robot_kwargs["usd_path"] = os.path.abspath(str(robot_usd_path))
    robot_camera_frequency = getattr(cfg.robot, "camera_frequency", None)
    if robot_camera_frequency is not None:
        robot_kwargs["camera_frequency"] = int(robot_camera_frequency)
    robot = create_robot(cfg.robot.type, **robot_kwargs)
    if fluid_enabled:
        source_ownership = str(cfg.online_fluid.source_ownership)
        if source_ownership == "gripper_attached_kinematic_vessel":
            collision_filter_root = getattr(
                cfg.online_fluid,
                "synthetic_attachment_collision_filter_root_path",
                None,
            )
            if collision_filter_root is not None:
                author_synthetic_attachment_collision_filter(
                    stage,
                    source_body_path=str(cfg.online_fluid.source_actor_path),
                    robot_root_path=str(collision_filter_root),
                )
        elif source_ownership == "contact_friction_dynamic_v1":
            configure_contact_grasp_scene(stage, cfg.online_fluid)
        else:
            raise ValueError(
                f"online_fluid_source_ownership_unsupported:{source_ownership}"
            )
    if not fluid_enabled:
        add_reference_to_stage(usd_path=os.path.abspath(cfg.usd_path), prim_path="/World")
    
    ObjectUtils.get_instance(stage)
    
    task = create_task(
        cfg.task_type,
        cfg=cfg,
        world=world,
        stage=stage,
        robot=robot,
    )
    
    task_controller = initialize_controller_after_task_reset(
        task,
        lambda: create_controller(
            cfg.controller_type,
            cfg=cfg,
            robot=robot,
        ),
    )

    video_writer = None
    presentation_video_recorder = None
    fluid_loop = None
    fluid_attempt_count = 0
    fluid_observation_count = 0
    fluid_episode_observation_count = 0
    fluid_episode_wall_start = None
    fluid_evidence_path = os.path.join(
        fluid_evidence_dir, "observations.jsonl"
    )
    fluid_episode_evidence_path = os.path.join(
        fluid_evidence_dir, "episodes.jsonl"
    )
    if fluid_enabled:
        if args.fluid_presentation_video_dir:
            presentation_config = getattr(
                cfg.online_fluid,
                "presentation_video",
                None,
            )
            if presentation_config is None:
                raise ValueError("fluid_presentation_video_config_required")
            presentation_video_recorder = (
                build_isaac_presentation_video_recorder(
                    model_camera_configs=tuple(cfg.cameras),
                    world=world,
                    presentation_config=presentation_config,
                    output_dir=os.path.abspath(
                        args.fluid_presentation_video_dir
                    ),
                )
            )
            presentation_video_recorder.initialize()
        fluid_loop = build_isaac_fluid_evaluation_loop(
            cfg=cfg,
            world=world,
            task=task,
            stage=stage,
        )
        fluid_loop.reset_episode(f"episode-{fluid_attempt_count:04d}")
        fluid_episode_wall_start = time.perf_counter()

    while simulation_app.is_running():
        fluid_global_limit_hit = False
        if not fluid_enabled:
            world.step(render=True)
        
        if world.is_stopped():
            task_controller.reset_needed = True
            
        if world.is_playing() or (
            controlled_contact_loop_mode
            and fluid_loop is not None
            and fluid_loop.controlled_loop_active
        ):
            if (
                task_controller.need_reset() or task.need_reset()
            ) and not (
                controlled_contact_loop_mode
                and (
                    fluid_loop.controlled_terminal_pending
                    or fluid_loop.controlled_interval_pending
                )
            ):
                if video_writer is not None:
                    video_writer.release()
                    video_writer = None
                if fluid_enabled:
                    if presentation_video_recorder is not None:
                        presentation_video_recorder.close_attempt(
                            status="interrupted"
                        )
                    if not fluid_loop.attempt_sealed:
                        interrupted = {
                            **fluid_loop.seal_attempt(
                                status="interrupted",
                                reason="task_or_controller_reset_before_terminal",
                            ),
                            "controller_completed": False,
                            "expert_episode_accepted": False,
                            "success": False,
                            "metric_policy_id": str(
                                cfg.online_fluid.metric_policy_id
                            ),
                            "camera_contract": dict(fluid_loop.camera_contract),
                            "termination": {
                                "reason": "task_or_controller_reset",
                                "observation_count": int(
                                    fluid_episode_observation_count
                                ),
                            },
                        }
                        append_fluid_episode_evidence(
                            fluid_episode_evidence_path,
                            interrupted,
                        )
                        fluid_attempt_count += 1
                    if online_fluid_run_complete(
                        mode=str(cfg.mode),
                        completed_attempts=fluid_attempt_count,
                        accepted_episodes=task_controller.episode_num(),
                        maximum_episodes=int(cfg.max_episodes),
                        maximum_attempts=int(cfg.online_fluid.max_attempts),
                    ):
                        task_controller.close()
                        simulation_app.close()
                        cv2.destroyAllWindows()
                        break
                    reset_task_then_controller(task, task_controller)
                    fluid_loop = build_isaac_fluid_evaluation_loop(
                        cfg=cfg,
                        world=world,
                        task=task,
                        stage=stage,
                    )
                    fluid_loop.reset_episode(
                        f"episode-{fluid_attempt_count:04d}"
                    )
                    fluid_episode_observation_count = 0
                    fluid_episode_wall_start = time.perf_counter()
                else:
                    task_controller.reset()
                    if task_controller.episode_num() >= cfg.max_episodes:
                        task_controller.close()
                        simulation_app.close()
                        cv2.destroyAllWindows()
                        break
                    task.reset()

                continue

            if fluid_enabled:
                fluid_artifact_frame_start = time.perf_counter()
                try:
                    fluid_observation = fluid_loop.observe()
                except Exception:
                    if controlled_contact_loop_mode:
                        _close_controlled_runtime(
                            task_controller,
                            simulation_app,
                        )
                    raise
                if (
                    fluid_observation.get("kind")
                    == "CONTROLLED_TERMINAL_TRANSITION"
                ):
                    try:
                        terminal = fluid_observation.get("terminal")
                        if not isinstance(terminal, dict):
                            raise RuntimeError(
                                "controlled_terminal_transition_record_required"
                            )
                        terminal_kind = terminal.get("terminal_kind")
                        if (
                            not isinstance(terminal_kind, str)
                            or not terminal_kind
                        ):
                            raise RuntimeError(
                                "controlled_terminal_transition_kind_required"
                            )
                        terminal_validation = (
                            validate_controlled_terminal_transition(terminal)
                        )
                        requires_world_termination = terminal_validation[
                            "requires_world_termination"
                        ]
                        world_counter = terminal.get("world_counter_after")
                        if not isinstance(world_counter, dict):
                            raise RuntimeError(
                                "controlled_terminal_world_counter_required"
                            )
                        abort_reason = terminal.get("failure_reason")
                        if not isinstance(abort_reason, str) or not abort_reason:
                            abort_reason = terminal_kind
                        current_step = world.current_time_step_index
                        current_step = (
                            current_step()
                            if callable(current_step)
                            else current_step
                        )
                        current_time = world.current_time
                        current_time = (
                            current_time()
                            if callable(current_time)
                            else current_time
                        )
                        if (
                            int(current_step)
                            != world_counter.get("physics_step")
                            or float(current_time)
                            != world_counter.get("simulation_time")
                            or world.is_playing()
                        ):
                            raise RuntimeError(
                                "controlled_terminal_cleanup_advanced_world"
                            )
                    except Exception:
                        _close_controlled_runtime(
                            task_controller,
                            simulation_app,
                        )
                        raise
                    if requires_world_termination:
                        try:
                            if video_writer is not None:
                                video_writer.release()
                                video_writer = None
                            if presentation_video_recorder is not None:
                                presentation_video_recorder.close_attempt(
                                    status="rejected"
                                )
                            terminal_evidence = {
                                **fluid_loop.seal_attempt(
                                    status="failed",
                                    reason=terminal_kind,
                                ),
                                "controller_completed": False,
                                "expert_episode_accepted": False,
                                "success": False,
                                "metric_policy_id": str(
                                    cfg.online_fluid.metric_policy_id
                                ),
                                "camera_contract": dict(
                                    fluid_loop.camera_contract
                                ),
                                "controlled_terminal_transition": terminal,
                                "attachment": dict(
                                    fluid_observation.get("attachment", {})
                                ),
                                "termination": {
                                    "reason": "controlled_terminal_transition",
                                    "terminal_kind": terminal_kind,
                                    "observation_count": int(
                                        fluid_episode_observation_count
                                    ),
                                    "world_reuse_forbidden": True,
                                },
                            }
                            append_fluid_episode_evidence(
                                fluid_episode_evidence_path,
                                terminal_evidence,
                            )
                            if ebench_action_logger is not None:
                                ebench_action_logger.discard_episode(
                                    success_observed=False,
                                    reason="controlled_terminal_transition",
                                )
                            cleanup_step = world.current_time_step_index
                            cleanup_step = (
                                cleanup_step()
                                if callable(cleanup_step)
                                else cleanup_step
                            )
                            cleanup_time = world.current_time
                            cleanup_time = (
                                cleanup_time()
                                if callable(cleanup_time)
                                else cleanup_time
                            )
                            if (
                                int(cleanup_step)
                                != world_counter.get("physics_step")
                                or float(cleanup_time)
                                != world_counter.get("simulation_time")
                                or world.is_playing()
                            ):
                                raise RuntimeError(
                                    "controlled_terminal_cleanup_advanced_world"
                                )
                        finally:
                            _close_controlled_runtime(
                                task_controller,
                                simulation_app,
                            )
                        break
                    try:
                        abort_result = task_controller.abort_online_fluid_episode(
                            f"controlled_terminal:{terminal_kind}:{abort_reason}"
                        )
                        if abort_result != (None, True, False):
                            raise RuntimeError(
                                "controlled_terminal_abort_result_invalid"
                            )
                        post_abort_step = world.current_time_step_index
                        post_abort_step = (
                            post_abort_step()
                            if callable(post_abort_step)
                            else post_abort_step
                        )
                        post_abort_time = world.current_time
                        post_abort_time = (
                            post_abort_time()
                            if callable(post_abort_time)
                            else post_abort_time
                        )
                        if (
                            int(post_abort_step)
                            != world_counter.get("physics_step")
                            or float(post_abort_time)
                            != world_counter.get("simulation_time")
                            or world.is_playing()
                        ):
                            raise RuntimeError(
                                "controlled_terminal_abort_advanced_world"
                            )
                    except Exception:
                        _close_controlled_runtime(
                            task_controller,
                            simulation_app,
                        )
                        raise
                    if video_writer is not None:
                        video_writer.release()
                        video_writer = None
                    if presentation_video_recorder is not None:
                        presentation_video_recorder.close_attempt(
                            status="rejected"
                        )
                    terminal_evidence = {
                        **fluid_loop.seal_attempt(
                            status="failed",
                            reason=terminal_kind,
                        ),
                        "controller_completed": False,
                        "expert_episode_accepted": False,
                        "success": False,
                        "metric_policy_id": str(
                            cfg.online_fluid.metric_policy_id
                        ),
                        "camera_contract": dict(fluid_loop.camera_contract),
                        "controlled_terminal_transition": terminal,
                        "attachment": dict(
                            fluid_observation.get("attachment", {})
                        ),
                        "termination": {
                            "reason": "controlled_terminal_transition",
                            "terminal_kind": terminal_kind,
                            "observation_count": int(
                                fluid_episode_observation_count
                            ),
                        },
                    }
                    append_fluid_episode_evidence(
                        fluid_episode_evidence_path,
                        terminal_evidence,
                    )
                    if ebench_action_logger is not None:
                        ebench_action_logger.discard_episode(
                            success_observed=False,
                            reason="controlled_terminal_transition",
                        )
                    task_controller.print_failure_reason()
                    task.on_task_complete(False)
                    fluid_attempt_count += 1
                    if online_fluid_run_complete(
                        mode=str(cfg.mode),
                        completed_attempts=fluid_attempt_count,
                        accepted_episodes=task_controller.episode_num(),
                        maximum_episodes=int(cfg.max_episodes),
                        maximum_attempts=int(cfg.online_fluid.max_attempts),
                    ):
                        task_controller.close()
                        simulation_app.close()
                        cv2.destroyAllWindows()
                        break
                    reset_task_then_controller(task, task_controller)
                    fluid_loop = build_isaac_fluid_evaluation_loop(
                        cfg=cfg,
                        world=world,
                        task=task,
                        stage=stage,
                    )
                    fluid_loop.reset_episode(
                        f"episode-{fluid_attempt_count:04d}"
                    )
                    fluid_episode_observation_count = 0
                    fluid_episode_wall_start = time.perf_counter()
                    continue
                state = fluid_observation["state"]
                record = fluid_observation["record"]
                fluid_observation_count += 1
                fluid_episode_observation_count += 1
                if presentation_video_recorder is not None:
                    presentation_frame_start = time.perf_counter()
                    presentation_video_recorder.capture(record)
                    record["latency_seconds"]["presentation_video"] = (
                        time.perf_counter() - presentation_frame_start
                    )
                if args.fluid_evidence_dir:
                    attempt_id = record["attempt_id"]
                    episode_id = record["episode_id"]
                    observation_index = int(record["observation_index"])
                    for camera_name, camera_array in state["camera_data"].items():
                        rgb = np.asarray(camera_array).transpose(1, 2, 0)
                        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                        filename = (
                            f"{attempt_id}_{episode_id}_"
                            f"observation-{observation_index:04d}_"
                            f"{camera_name}.png"
                        )
                        output_path = os.path.join(fluid_evidence_dir, filename)
                        if not cv2.imwrite(output_path, bgr):
                            raise RuntimeError(
                                f"fluid_camera_evidence_write_failed:{output_path}"
                            )
                if save_video or show_video:
                    combined_rgb = model_camera_video_rgb(
                        state,
                        camera_keys=tuple(cfg.online_fluid.model_camera_keys),
                        expected_shape=tuple(cfg.online_fluid.model_camera_shape),
                    )
                    combined_img = cv2.cvtColor(
                        combined_rgb, cv2.COLOR_RGB2BGR
                    )
                    if show_video:
                        cv2.imshow("Camera Views", combined_img)
                        cv2.waitKey(1)
                    if save_video:
                        os.makedirs(video_output_dir, exist_ok=True)
                        output_path = os.path.join(
                            video_output_dir,
                            f"episode_{task_controller._episode_num}.mp4",
                        )
                        if video_writer is None:
                            height, width = combined_img.shape[:2]
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            video_writer = cv2.VideoWriter(
                                output_path,
                                fourcc,
                                observation_video_fps(
                                    float(cfg.online_fluid.rendering_dt)
                                ),
                                (width, height),
                            )
                        video_writer.write(combined_img)
                record["latency_seconds"]["artifact_ready_total"] = (
                    time.perf_counter() - fluid_artifact_frame_start
                )
                append_fluid_observation_evidence(
                    fluid_evidence_path, fluid_observation
                )
                fluid_episode_limit_hit = observation_limit_reached(
                    fluid_episode_observation_count,
                    int(
                        getattr(
                            cfg.online_fluid,
                            "max_observations_per_episode",
                            cfg.task.max_steps,
                        )
                    ),
                )
                fluid_global_limit_hit = observation_limit_reached(
                    fluid_observation_count, args.max_fluid_observations
                )
            else:
                state = task.step()
                fluid_episode_limit_hit = False
            if state is None:
                continue

            controlled_contact_mode = controlled_contact_loop_mode
            if controlled_contact_mode:
                try:
                    fluid_loop.maybe_attach(task_controller, state)
                    if fluid_loop.mechanical_attachment_used:
                        raise RuntimeError(
                            "controlled_contact_attachment_forbidden"
                        )
                except Exception as exc:
                    if not fluid_loop.controlled_terminal_pending:
                        fluid_loop.queue_controlled_prephysics_failure(
                            stage="preaction_authority",
                            error=exc,
                            application_outcome="not_invoked",
                        )
                    continue
                if fluid_loop.controlled_terminal_pending:
                    continue
            try:
                action, done, is_success = task_controller.step(state)
            except Exception as exc:
                if not controlled_contact_mode:
                    raise
                fluid_loop.queue_controlled_prephysics_failure(
                    stage="controller_step",
                    error=exc,
                    application_outcome="not_invoked",
                )
                continue
            controlled_action_precommitted = False
            fluid_limit_boundary_reason = (
                observation_limit_failure_reason(
                    per_episode_limit_hit=fluid_episode_limit_hit,
                    global_limit_hit=fluid_global_limit_hit,
                )
                if fluid_enabled
                else None
            )
            fluid_limit_termination_reason = (
                observation_limit_termination_reason(
                    controller_done=bool(done),
                    per_episode_limit_hit=fluid_episode_limit_hit,
                    global_limit_hit=fluid_global_limit_hit,
                )
                if fluid_enabled
                else None
            )
            if fluid_limit_termination_reason is not None:
                action, done, is_success = (
                    task_controller.abort_online_fluid_episode(
                        fluid_limit_termination_reason
                    )
                )
            if (
                fluid_enabled
                and not done
                and fluid_rotation_handoff_requested(task_controller)
            ):
                fluid_loop.mark_pour_started()
            if controlled_contact_mode and done and action is not None:
                fluid_loop.queue_controlled_prephysics_failure(
                    stage="proposal_validation",
                    error=RuntimeError(
                        "controlled_contact_terminal_action_forbidden"
                    ),
                    application_outcome="not_invoked",
                )
                continue
            if controlled_contact_mode and not done:
                if action is None:
                    fluid_loop.queue_controlled_prephysics_failure(
                        stage="proposal_validation",
                        error=RuntimeError(
                            "controlled_contact_nonterminal_action_missing"
                        ),
                        application_outcome="not_invoked",
                    )
                    continue
                controlled_transaction = (
                    execute_controlled_action_transaction(
                        fluid_loop=fluid_loop,
                        action=action,
                        read_action_context=lambda: (
                            task_controller.controlled_contact_action_context()
                        ),
                        apply_action=lambda value: (
                            robot.get_articulation_controller().apply_action(
                                value
                            )
                        ),
                        log_action=(
                            None
                            if ebench_action_logger is None
                            else lambda value: ebench_action_logger.log_action(
                                value,
                                current_joint_positions=state[
                                    "joint_positions"
                                ],
                                labutopia_step_index=getattr(
                                    task, "frame_idx", None
                                ),
                            )
                        ),
                    )
                )
                if controlled_transaction is None:
                    continue
                controlled_action_precommitted = True
            if action is not None and not controlled_action_precommitted:
                if ebench_action_logger is not None:
                    ebench_action_logger.log_action(
                        action,
                        current_joint_positions=state['joint_positions'],
                        labutopia_step_index=getattr(task, 'frame_idx', None),
                    )
                robot.get_articulation_controller().apply_action(action)
            if done:
                if fluid_enabled:
                    if video_writer is not None:
                        video_writer.release()
                        video_writer = None
                    fluid_episode_wall_seconds = (
                        time.perf_counter() - fluid_episode_wall_start
                    )
                    acceptance_mode = str(
                        getattr(
                            cfg.online_fluid,
                            "execution_mode",
                            "production_pour_v1",
                        )
                    )
                    control_evidence = (
                        task_controller.online_fluid_control_evidence()
                    )
                    terminal_phase = task_controller.current_phase.name
                    combined = fluid_loop.finalize_episode(
                        controller_completed=bool(is_success),
                        acceptance_mode=acceptance_mode,
                        controller_evidence=control_evidence,
                        terminal_phase=terminal_phase,
                        terminal_action=action,
                    )
                    record = fluid_observation["record"]
                    score = fluid_observation["score"]
                    evaluation = {
                        **combined,
                        "episode_id": str(record["episode_id"]),
                        "metric_policy_id": str(
                            cfg.online_fluid.metric_policy_id
                        ),
                        "camera_contract": dict(
                            fluid_loop.camera_contract
                        ),
                        "control": control_evidence,
                        "termination": {
                            "max_observations_per_episode_reached": bool(
                                fluid_episode_limit_hit
                            ),
                            "max_fluid_observations_reached": bool(
                                fluid_global_limit_hit
                            ),
                            "observation_limit_boundary": {
                                "reached": (
                                    fluid_limit_boundary_reason is not None
                                ),
                                "reason": fluid_limit_boundary_reason,
                            },
                            "observation_limit_termination": {
                                "terminated": (
                                    fluid_limit_termination_reason is not None
                                ),
                                "reason": fluid_limit_termination_reason,
                            },
                            "observation_count": int(
                                fluid_episode_observation_count
                            ),
                        },
                        "performance": {
                            "logical_video_fps": observation_video_fps(
                                float(cfg.online_fluid.rendering_dt)
                            ),
                            "episode_wall_seconds": (
                                fluid_episode_wall_seconds
                            ),
                            "episode_wall_fps": (
                                fluid_episode_observation_count
                                / fluid_episode_wall_seconds
                            ),
                        },
                        "terminal_observation": {
                            "episode_id": str(record["episode_id"]),
                            "observation_index": int(record["observation_index"]),
                            "frame_identity": str(record["frame_identity"]),
                        },
                        "attachment": dict(fluid_observation["attachment"]),
                        "final_particle_counts": {
                            name: int(score[name])
                            for name in (
                                "source",
                                "target",
                                "transit",
                                "tabletop_spill",
                                "below_table",
                                "nonfinite",
                            )
                        },
                        "final_particle_fractions": {
                            name: float(score[name])
                            for name in (
                                "source_fraction",
                                "target_fraction",
                                "transit_fraction",
                                "tabletop_spill_fraction",
                                "below_table_fraction",
                                "nonfinite_fraction",
                                "spill_fraction",
                            )
                        },
                        "expert_pour_target_offset_m": [
                            float(value)
                            for value in cfg.online_fluid.expert_pour_target_offset_m
                        ],
                        "expert_pour_position_control": str(
                            cfg.online_fluid.expert_pour_position_control
                        ),
                    }
                    append_fluid_episode_evidence(
                        fluid_episode_evidence_path,
                        evaluation,
                    )
                    if str(cfg.mode) == "collect":
                        task_controller.finalize_collection_episode(
                            accepted=combined["expert_episode_accepted"],
                            final_joint_positions=state["joint_positions"][:-1],
                            evaluation=evaluation,
                        )
                    is_success = (
                        combined["expert_episode_accepted"]
                        if acceptance_mode == "production_pour_v1"
                        else combined["success"]
                    )
                    if presentation_video_recorder is not None:
                        presentation_video_recorder.close_attempt(
                            status="accepted" if is_success else "rejected"
                        )
                    task_controller._last_success = is_success
                    fluid_attempt_count += 1
                if ebench_action_logger is not None:
                    if is_success:
                        ebench_action_logger.finalize(success_observed=True)
                        ebench_action_logger = None
                    else:
                        ebench_action_logger.discard_episode(
                            success_observed=False,
                            reason="failed_episode_before_success",
                        )
                task_controller.print_failure_reason()
                task.on_task_complete(is_success)
                if fluid_enabled and fluid_global_limit_hit:
                    task_controller.close()
                    simulation_app.close()
                    cv2.destroyAllWindows()
                    break
                if fluid_enabled and controlled_contact_mode:
                    if online_fluid_run_complete(
                        mode=str(cfg.mode),
                        completed_attempts=fluid_attempt_count,
                        accepted_episodes=task_controller.episode_num(),
                        maximum_episodes=int(cfg.max_episodes),
                        maximum_attempts=int(cfg.online_fluid.max_attempts),
                    ):
                        task_controller.close()
                        simulation_app.close()
                        cv2.destroyAllWindows()
                        break
                    reset_task_then_controller(task, task_controller)
                    fluid_loop = build_isaac_fluid_evaluation_loop(
                        cfg=cfg,
                        world=world,
                        task=task,
                        stage=stage,
                    )
                    fluid_loop.reset_episode(
                        f"episode-{fluid_attempt_count:04d}"
                    )
                    fluid_episode_observation_count = 0
                    fluid_episode_wall_start = time.perf_counter()
                continue
            if fluid_enabled:
                if not controlled_action_precommitted:
                    fluid_loop.maybe_attach(task_controller, state)
                    fluid_loop.commit_action(action)

            if (save_video or show_video) and not fluid_enabled:
                camera_images = []
                for _, image_data in state['camera_display'].items():
                    display_img = cv2.cvtColor(image_data.transpose(1, 2, 0), cv2.COLOR_RGB2BGR)
                    camera_images.append(display_img)
                
                if camera_images:
                    combined_img = np.hstack(camera_images)
                    total_width = 0
                    for idx, img in enumerate(camera_images):
                        label = f"Camera {idx+1} ({cfg.cameras[idx].image_type})"
                        cv2.putText(combined_img, label, (total_width + 2, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.25, (255, 255, 255), 1)
                        total_width += img.shape[1]
                    if show_video:
                        cv2.imshow('Camera Views', combined_img)
                        cv2.waitKey(1)
                    if save_video:
                        os.makedirs(video_output_dir, exist_ok=True)
                        output_path = os.path.join(video_output_dir, f"episode_{task_controller._episode_num}.mp4")
                        if video_writer is None:
                            height, width = combined_img.shape[:2]
                            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                            video_writer = cv2.VideoWriter(output_path, fourcc, 60.0, (width, height))
                        video_writer.write(combined_img)

    if video_writer is not None:
        video_writer.release()
    if presentation_video_recorder is not None:
        presentation_video_recorder.close()

if __name__ == "__main__":
    main()

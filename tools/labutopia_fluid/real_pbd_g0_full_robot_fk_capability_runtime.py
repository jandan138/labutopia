"""Sealed-child implementation of the paused full-robot FK capability probe.

One bootstrap reset initializes PhysX tensors. After the paused baseline, only
direct articulation joint-position materialization and tensor FK refresh are
permitted. This diagnostic never performs a collision sweep or recovery gate.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


SOURCE_PATH = "/World/beaker2"
PARTICLE_PATH = "/World/InternDataParityFluid/Particles"
ROBOT_ROOT_PATH = "/World/Franka"
SIMULATION_POINTS_ATTRIBUTE = "physxParticle:simulationPoints"
CAPABILITY_JOINT_READBACK_ATOL = 2.0e-7


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _particle_usd_snapshot(np: Any, stage: Any) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(PARTICLE_PATH)
    if not prim or not prim.IsValid():
        raise RuntimeError("g0_fk_capability_particle_prim_missing")
    attributes = {}
    point_count = 0
    for name in (
        SIMULATION_POINTS_ATTRIBUTE,
        "points",
        "positions",
        "velocities",
        "ids",
    ):
        attribute = prim.GetAttribute(name)
        if not attribute or not attribute.IsValid():
            continue
        raw = attribute.Get()
        if raw is None:
            continue
        try:
            array = np.asarray(raw, dtype=np.float64)
        except (TypeError, ValueError):
            continue
        if array.size == 0 or not np.isfinite(array).all():
            continue
        if name == SIMULATION_POINTS_ATTRIBUTE:
            if array.ndim != 2 or array.shape[1] != 3:
                continue
            point_count = int(array.shape[0])
        attributes[name] = {
            "shape": list(array.shape),
            "sha256": _canonical_json_sha256(array.tolist()),
        }
    simulation_points = attributes.get(SIMULATION_POINTS_ATTRIBUTE)
    payload = {
        "prim_path": PARTICLE_PATH,
        "type_name": str(prim.GetTypeName()),
        "point_count": point_count,
        "attributes": attributes,
        "complete": (
            simulation_points is not None
            and simulation_points["shape"] == [point_count, 3]
            and point_count > 0
        ),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _source_state(np: Any, source_reader: Any, stage: Any) -> dict[str, Any]:
    position, orientation = source_reader.get_world_pose()
    payload = {
        "source": {
            "position_m": [float(value) for value in position],
            "orientation_xyzw": [float(value) for value in orientation],
            "linear_velocity_m_s": [
                float(value) for value in source_reader.get_linear_velocity()
            ],
            "angular_velocity_rad_s": [
                float(value) for value in source_reader.get_angular_velocity()
            ],
        },
        "particle_usd_snapshot": _particle_usd_snapshot(np, stage),
    }
    return {
        **payload,
        "source_state_sha256": _canonical_json_sha256(payload["source"]),
        "particle_usd_snapshot_sha256": payload["particle_usd_snapshot"]["sha256"],
        "particle_usd_snapshot_complete": payload["particle_usd_snapshot"]["complete"],
    }


def _target_positions(
    np: Any,
    *,
    baseline: Sequence[float],
    lower: Any,
    upper: Any,
    probe: Mapping[str, Any],
) -> tuple[int, float, list[float]]:
    index = int(probe["dof_index"])
    for direction, field in ((1, "positive_delta"), (-1, "negative_delta")):
        delta = float(probe[field])
        candidate = np.asarray(baseline, dtype=np.float64).copy()
        candidate[index] += direction * delta
        if (
            candidate[index] <= upper[index] - 1.0e-8
            and candidate[index] >= lower[index] + 1.0e-8
        ):
            return direction, delta, [float(value) for value in candidate.tolist()]
    raise RuntimeError(f"g0_fk_capability_joint_excursion_unavailable:{index}")


def _matrix_payload(np: Any, matrices: Mapping[str, Any]) -> dict[str, list[list[float]]]:
    return {
        path: np.asarray(matrices[path], dtype=np.float64).tolist()
        for path in sorted(matrices)
    }


class _TimelineEventAudit:
    def __init__(self, timeline: Any, event_counters: Mapping[int, str]) -> None:
        stream = getattr(timeline, "get_timeline_event_stream", lambda: None)()
        subscribe = getattr(stream, "create_subscription_to_pop", None)
        if not callable(subscribe):
            raise RuntimeError("g0_fk_capability_timeline_event_stream_unavailable")
        self._event_counters = dict(event_counters)
        self._counts = {counter: 0 for counter in set(event_counters.values())}
        self._events: list[dict[str, Any]] = []
        self._error: str | None = None
        self._subscription = subscribe(self._on_event)
        if self._subscription is None:
            raise RuntimeError("g0_fk_capability_timeline_subscription_unavailable")

    @property
    def active(self) -> bool:
        return self._subscription is not None

    def _on_event(self, event: Any) -> None:
        try:
            event_type = int(event.type)
            counter = self._event_counters.get(event_type)
            if counter is not None:
                self._counts[counter] += 1
                self._events.append({"counter": counter, "event_type": event_type})
        except BaseException as exc:
            self._error = f"{type(exc).__name__}:{exc}"
            self._events.append({"counter": "timeline_event_error", "error": type(exc).__name__})

    def operation_counts(self) -> dict[str, int]:
        if self._error is not None:
            raise RuntimeError("g0_fk_capability_timeline_event_audit_invalid")
        return dict(self._counts)

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def close(self) -> None:
        self._subscription = None


def _count_bootstrap_reset(world: Any) -> int:
    original = getattr(world, "reset", None)
    if not callable(original):
        raise RuntimeError("g0_fk_capability_bootstrap_reset_unavailable")
    count = 0

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal count
        count += 1
        return original(*args, **kwargs)

    try:
        setattr(world, "reset", counted)
    except (AttributeError, TypeError) as exc:
        raise RuntimeError("g0_fk_capability_bootstrap_reset_unpatchable") from exc
    try:
        world.reset()
    finally:
        try:
            delattr(world, "reset")
        except AttributeError:
            setattr(world, "reset", original)
    return count


def _instrument_operations(
    *,
    world: Any,
    timeline_event_audit: Any,
    robot: Any,
    simulation_view: Any,
    source_reader: Any,
    required_coverage: Sequence[str],
) -> tuple[dict[str, int], dict[str, bool], Any]:
    counts = {name: 0 for name in required_coverage}
    coverage = {name: False for name in required_coverage}
    restorers: list[Any] = []

    def restore() -> None:
        errors = []
        for restore_one in reversed(restorers):
            try:
                restore_one()
            except BaseException as exc:
                errors.append(f"{type(exc).__name__}:{exc}")
        if errors:
            raise RuntimeError("g0_fk_capability_guard_restore_failed:" + ",".join(errors))

    def patch(instance: Any, method: str, replacement: Any) -> bool:
        original = getattr(instance, method, None)
        if not callable(original):
            return False
        instance_dict = getattr(instance, "__dict__", None)
        had_instance_attribute = isinstance(instance_dict, dict) and method in instance_dict
        try:
            setattr(instance, method, replacement(original))
        except (AttributeError, TypeError) as exc:
            raise RuntimeError(f"g0_fk_capability_guard_unpatchable:{method}") from exc
        def restore_one() -> None:
            if had_instance_attribute:
                setattr(instance, method, original)
            else:
                delattr(instance, method)

        restorers.append(restore_one)
        return True

    def forbid(instance: Any, method: str, counter: str) -> bool:
        def replacement(_original: Any) -> Any:
            def denied(*_args: Any, **_kwargs: Any) -> None:
                counts[counter] += 1
                raise RuntimeError(f"g0_fk_capability_prohibited_{counter}")

            return denied

        return patch(instance, method, replacement)

    def count(instance: Any, method: str, counter: str) -> bool:
        def replacement(original: Any) -> Any:
            def counted(*args: Any, **kwargs: Any) -> Any:
                counts[counter] += 1
                return original(*args, **kwargs)

            return counted

        return patch(instance, method, replacement)

    def require_any(instance: Any, methods: Sequence[str], counter: str) -> None:
        patched = [forbid(instance, method, counter) for method in methods]
        if not any(patched):
            raise RuntimeError(f"g0_fk_capability_guard_unavailable:{counter}")
        coverage[counter] = True

    try:
        for instance, method, counter in (
            (world, "step", "world_step"),
            (world, "reset", "world_reset"),
            (simulation_view, "step", "simulation_view_step"),
        ):
            if not forbid(instance, method, counter):
                raise RuntimeError(f"g0_fk_capability_guard_unavailable:{counter}")
            coverage[counter] = True
        if not bool(getattr(timeline_event_audit, "active", False)):
            raise RuntimeError("g0_fk_capability_timeline_event_audit_unavailable")
        for counter in (
            "timeline_play",
            "timeline_pause",
            "timeline_stop",
            "timeline_time_set",
        ):
            coverage[counter] = True

        controller = getattr(robot, "get_articulation_controller", lambda: None)()
        if controller is None or not forbid(controller, "apply_action", "apply_action"):
            raise RuntimeError("g0_fk_capability_guard_unavailable:apply_action")
        forbid(robot, "apply_action", "apply_action")
        coverage["apply_action"] = True

        require_any(
            robot,
            (
                "set_joint_velocities",
                "set_joint_efforts",
                "set_default_state",
                "set_joints_default_state",
                "set_linear_velocity",
                "set_angular_velocity",
                "set_velocities",
            ),
            "robot_nonposition_writer",
        )
        articulation_view = getattr(robot, "_articulation_view", None)
        if articulation_view is None:
            raise RuntimeError("g0_fk_capability_articulation_view_guard_unavailable")
        require_any(
            articulation_view,
            (
                "set_joint_velocities",
                "set_joint_efforts",
                "set_joints_default_state",
                "set_linear_velocities",
                "set_angular_velocities",
            ),
            "robot_nonposition_writer",
        )
        source_view = getattr(source_reader, "_view", None)
        if source_view is None:
            raise RuntimeError("g0_fk_capability_source_writer_guard_unavailable")
        require_any(
            source_view,
            ("set_world_poses", "set_local_poses", "set_default_state"),
            "source_pose_writer",
        )
        require_any(
            source_view,
            ("set_linear_velocities", "set_angular_velocities", "set_velocities"),
            "source_velocity_writer",
        )
        require_any(
            source_view,
            (
                "apply_forces",
                "apply_forces_and_torques_at_pos",
                "set_forces",
                "set_efforts",
            ),
            "source_force_writer",
        )
        source_physics_view = getattr(source_view, "_physics_view", None)
        if source_physics_view is None:
            raise RuntimeError("g0_fk_capability_source_physics_view_guard_unavailable")
        require_any(
            source_physics_view,
            ("set_transforms", "set_poses"),
            "source_pose_writer",
        )
        require_any(
            source_physics_view,
            ("set_velocities", "set_linear_velocities", "set_angular_velocities"),
            "source_velocity_writer",
        )
        require_any(
            source_physics_view,
            ("apply_forces", "apply_forces_and_torques_at_position"),
            "source_force_writer",
        )
        if not count(robot, "set_joint_positions", "direct_joint_position_materialization"):
            raise RuntimeError("g0_fk_capability_joint_materialization_guard_unavailable")
        coverage["direct_joint_position_materialization"] = True
        if not count(simulation_view, "update_articulations_kinematic", "tensor_kinematic_refresh"):
            raise RuntimeError("g0_fk_capability_kinematic_refresh_guard_unavailable")
        coverage["tensor_kinematic_refresh"] = True
        for counter in ("particle_writer", "collision_filter_write", "raw_usd_mutation"):
            coverage[counter] = True
    except BaseException:
        restore()
        raise
    return counts, coverage, restore


def _mutation_counts(events: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    raw_usd_mutations = len(events)
    collision_filter_writes = 0
    for event in events:
        fields = event.get("fields")
        if not isinstance(fields, list):
            continue
        if any(
            field == "physics:collisionEnabled"
            or "filteredPairs" in field
            or "collisionGroup" in field
            for field in fields
        ):
            collision_filter_writes += 1
    return raw_usd_mutations, collision_filter_writes


def run_full_robot_fk_capability(
    *,
    app: Any,
    stage: Any,
    timeline: Any,
    plan: Mapping[str, Any],
    full_robot_collider_paths: Sequence[str],
) -> dict[str, Any]:
    """Run the one-reset, no-step tensor FK capability probe in an attested child."""
    import numpy as np
    import omni.physx
    import omni.timeline
    from omni.isaac.core import World
    from omni.isaac.core.articulations import Articulation
    from omni.isaac.core.prims import RigidPrimView
    from pxr import Usd, UsdGeom, UsdPhysics
    from scipy.spatial.transform import Rotation

    from tools.labutopia_fluid import (
        nonformal_controller_static_collision_screen_runtime as static_runtime,
    )
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native
    from tools.labutopia_fluid import run_real_pbd_grasp_v2_g0_geometry as geometry
    from utils.isaac_fluid_evaluation import configure_particle_usd_readback
    from utils import real_pbd_g0_full_robot_fk_capability as capability

    normalized_plan = capability.validate_plan(plan)
    collider_paths = sorted(set(full_robot_collider_paths))
    if (
        len(collider_paths) != len(full_robot_collider_paths)
        or not collider_paths
        or any(not path.startswith(f"{ROBOT_ROOT_PATH}/") for path in collider_paths)
    ):
        raise RuntimeError("g0_fk_capability_full_robot_scope_invalid")

    world = None
    mutation_notice = None
    timeline_audit = None
    try:
        particle_usd_readback = configure_particle_usd_readback()
        if (
            particle_usd_readback.get("/physics/suppressReadback") is not False
            or not all(
                particle_usd_readback.get(path) is True
                for path in (
                    "/physics/updateToUsd",
                    "/physics/updateParticlesToUsd",
                    "/physics/updateVelocitiesToUsd",
                )
            )
        ):
            raise RuntimeError("g0_fk_capability_particle_readback_settings_invalid")
        world = World(
            physics_dt=1.0 / 600.0,
            rendering_dt=1.0 / 600.0,
            stage_units_in_meters=1.0,
            physics_prim_path="/World/PhysicsScene",
            backend="numpy",
            set_defaults=False,
        )
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
        reset_before = static_runtime._runtime_receipt(world, timeline)
        bootstrap_reset_count = _count_bootstrap_reset(world)
        reset_after = static_runtime._runtime_receipt(world, timeline)
        physics_view = world.physics_sim_view
        if physics_view is None:
            raise RuntimeError("g0_fk_capability_tensor_view_missing")
        robot = Articulation(prim_path=ROBOT_ROOT_PATH, name="g0_full_robot_fk_capability")
        robot.initialize(physics_sim_view=physics_view)
        initialized = static_runtime._runtime_receipt(world, timeline)
        if (
            initialized["world_index"] != reset_after["world_index"]
            or initialized["timeline_time_s"] != reset_after["timeline_time_s"]
        ):
            raise RuntimeError("g0_fk_capability_initialization_advanced")
        baseline_runtime = static_runtime._pause_after_reset(
            app, world, timeline, post_reset_receipt=initialized
        )
        if list(robot.dof_names) != normalized_plan["dof_names"]:
            raise RuntimeError("g0_fk_capability_dof_names_invalid")

        source_reader = native.RuntimeReadOnlySourceAdapter(RigidPrimView, SOURCE_PATH)
        source_reader.initialize()
        static_runtime._require_paused_unchanged(
            world,
            timeline,
            baseline_runtime,
            context="g0_fk_capability_source_reader_initialization",
        )
        source_before = _source_state(np, source_reader, stage)
        collision_before = geometry._collision_inventory(stage)
        robot_kinematics = static_runtime._robot_kinematic_model(
            np=np,
            Rotation=Rotation,
            Usd=Usd,
            UsdGeom=UsdGeom,
            UsdPhysics=UsdPhysics,
            stage=stage,
            robot=robot,
            expected_simulation_view=physics_view,
            collider_paths=collider_paths,
        )
        lower, upper = static_runtime._joint_position_limits(np, robot)
        baseline_joints = static_runtime._read_joint_positions(np, robot)
        baseline_matrices = static_runtime._robot_collider_world_matrices(
            np, Rotation, robot_kinematics
        )
        if sorted(baseline_matrices) != collider_paths:
            raise RuntimeError("g0_fk_capability_matrix_scope_mismatch")
        source_matrix_before = static_runtime._world_matrix(
            np, Usd, UsdGeom, stage, SOURCE_PATH
        )

        mutation_notice = native._RuntimeMutationNotice(stage)
        mutation_marker = mutation_notice.mark()
        timeline_audit = _TimelineEventAudit(
            timeline,
            {
                int(omni.timeline.TimelineEventType.PLAY): "timeline_play",
                int(omni.timeline.TimelineEventType.PAUSE): "timeline_pause",
                int(omni.timeline.TimelineEventType.STOP): "timeline_stop",
                int(omni.timeline.TimelineEventType.CURRENT_TIME_CHANGED): "timeline_time_set",
                int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED_PERMANENT): "timeline_time_set",
                int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED): "timeline_time_set",
            },
        )
        coverage_fields = capability.OPERATION_GUARD_COVERAGE_FIELDS
        counts, guard_coverage, restore_operations = _instrument_operations(
            world=world,
            timeline_event_audit=timeline_audit,
            robot=robot,
            simulation_view=physics_view,
            source_reader=source_reader,
            required_coverage=coverage_fields,
        )
        samples = []
        restored_matrices = None
        rollback_required = False
        rollback_failure = None
        try:
            for probe in normalized_plan["probes"]:
                direction, delta, target = _target_positions(
                    np,
                    baseline=baseline_joints,
                    lower=lower,
                    upper=upper,
                    probe=probe,
                )
                rollback_required = True
                try:
                    readback, _source_matrix, matrices = static_runtime._materialize_configuration(
                        np=np,
                        Rotation=Rotation,
                        Usd=Usd,
                        UsdGeom=UsdGeom,
                        stage=stage,
                        robot=robot,
                        robot_kinematics=robot_kinematics,
                        source_matrix_before=source_matrix_before,
                        world=world,
                        timeline=timeline,
                        baseline=baseline_runtime,
                        target_positions=target,
                        joint_lower_limits=lower,
                        joint_upper_limits=upper,
                        is_hold=False,
                        joint_readback_atol=CAPABILITY_JOINT_READBACK_ATOL,
                    )
                except RuntimeError as exc:
                    if str(exc) != "controller_static_screen_joint_readback_mismatch":
                        raise
                    diagnostic = {
                        "dof_index": probe["dof_index"],
                        "baseline_joint_positions": baseline_joints,
                        "target_joint_positions": target,
                        "observed_joint_positions": static_runtime._read_joint_positions(
                            np, robot
                        ),
                    }
                    raise RuntimeError(
                        "g0_fk_capability_joint_readback_mismatch:"
                        + json.dumps(diagnostic, sort_keys=True, separators=(",", ":"))
                    ) from exc
                changed = sorted(
                    path
                    for path in collider_paths
                    if not np.allclose(
                        baseline_matrices[path], matrices[path], rtol=0.0, atol=1.0e-10
                    )
                )
                samples.append(
                    {
                        "dof_index": probe["dof_index"],
                        "selected_direction": direction,
                        "selected_delta": delta,
                        "joint_positions": readback,
                        "changed_collider_paths": changed,
                        "collider_world_matrices": _matrix_payload(np, matrices),
                        "state": _source_state(np, source_reader, stage),
                    }
                )
                _restored_readback, _source_matrix, restored_matrices = (
                    static_runtime._materialize_configuration(
                        np=np,
                        Rotation=Rotation,
                        Usd=Usd,
                        UsdGeom=UsdGeom,
                        stage=stage,
                        robot=robot,
                        robot_kinematics=robot_kinematics,
                        source_matrix_before=source_matrix_before,
                        world=world,
                        timeline=timeline,
                        baseline=baseline_runtime,
                        target_positions=baseline_joints,
                        joint_lower_limits=lower,
                        joint_upper_limits=upper,
                        is_hold=False,
                        joint_readback_atol=CAPABILITY_JOINT_READBACK_ATOL,
                    )
                )
                rollback_required = False
        finally:
            if rollback_required:
                try:
                    _restored_readback, _source_matrix, restored_matrices = (
                        static_runtime._materialize_configuration(
                            np=np,
                            Rotation=Rotation,
                            Usd=Usd,
                            UsdGeom=UsdGeom,
                            stage=stage,
                            robot=robot,
                            robot_kinematics=robot_kinematics,
                            source_matrix_before=source_matrix_before,
                            world=world,
                            timeline=timeline,
                            baseline=baseline_runtime,
                            target_positions=baseline_joints,
                            joint_lower_limits=lower,
                            joint_upper_limits=upper,
                            is_hold=False,
                            joint_readback_atol=CAPABILITY_JOINT_READBACK_ATOL,
                        )
                    )
                except BaseException as exc:
                    rollback_failure = exc
            restore_operations()
            if rollback_failure is not None:
                raise RuntimeError(
                    f"g0_fk_capability_joint_rollback_failed:{type(rollback_failure).__name__}"
                ) from rollback_failure

        if restored_matrices is None:
            raise RuntimeError("g0_fk_capability_joint_rollback_missing")
        final_runtime = static_runtime._require_paused_unchanged(
            world, timeline, baseline_runtime, context="g0_fk_capability_final"
        )
        source_after = _source_state(np, source_reader, stage)
        collision_after = geometry._collision_inventory(stage)
        mutation_events = mutation_notice.events_since(mutation_marker)
        for counter, count in timeline_audit.operation_counts().items():
            counts[counter] += count
        raw_usd_mutations, collision_filter_writes = _mutation_counts(mutation_events)
        counts["raw_usd_mutation"] = raw_usd_mutations
        counts["particle_writer"] = raw_usd_mutations
        counts["collision_filter_write"] = collision_filter_writes
        if collision_after != collision_before:
            counts["collision_filter_write"] += 1
        observation_payload = {
            "authority": capability.OBSERVATION_AUTHORITY,
            "schema_version": 4,
            "plan_sha256": normalized_plan["sha256"],
            "dof_names": list(robot.dof_names),
            "baseline_joint_positions": baseline_joints,
            "baseline_runtime": baseline_runtime,
            "final_runtime": final_runtime,
            "baseline_state": source_before,
            "final_state": source_after,
            "restored_joint_positions": static_runtime._read_joint_positions(np, robot),
            "full_robot_collider_paths": collider_paths,
            "baseline_collider_world_matrices": _matrix_payload(np, baseline_matrices),
            "restored_collider_world_matrices": _matrix_payload(np, restored_matrices),
            "particle_usd_readback": particle_usd_readback,
            "bootstrap_world_reset_count": bootstrap_reset_count,
            "post_reset_physics_advance": {
                "world_index_delta": final_runtime["world_index"] - initialized["world_index"],
                "timeline_time_delta_s": (
                    final_runtime["timeline_time_s"] - initialized["timeline_time_s"]
                ),
                "verified_zero": final_runtime == baseline_runtime,
            },
            "operation_counts": counts,
            "operation_guard_coverage": guard_coverage,
            "samples": samples,
        }
        observation = {
            **observation_payload,
            "sha256": capability.canonical_json_sha256(observation_payload),
        }
        return {
            "authority": "real_pbd_g0_full_robot_fk_capability_runtime_v2",
            "status": "COMPLETE",
            "plan": normalized_plan,
            "observation": observation,
            "evaluation": capability.evaluate_observation(
                observation,
                plan=normalized_plan,
                expected_collider_paths=collider_paths,
            ),
            "guard_coverage": guard_coverage,
            "reset_bootstrap_advance": {
                "world_index_delta": reset_after["world_index"] - reset_before["world_index"],
                "timeline_time_delta_s": (
                    reset_after["timeline_time_s"] - reset_before["timeline_time_s"]
                ),
            },
            "baseline_state": source_before,
            "final_state": source_after,
            "source_reader": source_reader.contract(),
            "collision_inventory_before_sha256": collision_before["sha256"],
            "collision_inventory_after_sha256": collision_after["sha256"],
            "mutation_ledger": {
                "event_count": len(mutation_events),
                "events": mutation_events,
            },
            "timeline_event_ledger": timeline_audit.events(),
        }
    finally:
        if timeline_audit is not None:
            timeline_audit.close()
        if mutation_notice is not None:
            mutation_notice.close()
        if world is not None:
            clear_instance = getattr(World, "clear_instance", None)
            if callable(clear_instance):
                clear_instance()

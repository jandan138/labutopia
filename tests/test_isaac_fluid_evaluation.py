from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from utils import isaac_fluid_evaluation as isaac_fluid


class _Frame:
    def __init__(self, center):
        self.center = np.asarray(center, dtype=np.float64)
        self.origin_world = tuple(self.center.tolist())
        self.z_axis_world = (0.0, 0.0, 1.0)
        self.interior_radius = 0.1
        self.interior_floor = 0.0
        self.rim_height = 0.2

    def world_to_canonical(self, point):
        return tuple(np.asarray(point, dtype=np.float64) - self.center)


def _translation(x, y, z):
    result = np.eye(4, dtype=np.float64)
    result[3, :3] = [x, y, z]
    return result


def _controller(
    event: int,
    phase: str = "picking",
    *,
    last_emitted_pour_event: int | None = None,
):
    return SimpleNamespace(
        current_phase=SimpleNamespace(value=phase),
        pick_controller=SimpleNamespace(_event=event),
        pour_controller=SimpleNamespace(
            _last_emitted_event=last_emitted_pour_event
        ),
    )


def _rotation_z(degrees):
    angle = np.radians(degrees)
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = [
        [np.cos(angle), np.sin(angle), 0.0],
        [-np.sin(angle), np.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ]
    return result


def test_transfer_classifier_uses_raw_particle_partition_and_strict_success_gate():
    source = _Frame((0.0, 0.0, 0.8))
    target = _Frame((0.4, 0.0, 0.8))
    positions = np.concatenate(
        [
            np.tile([[0.0, 0.0, 0.9]], (3, 1)),
            np.tile([[0.4, 0.0, 0.9]], (150, 1)),
            [[0.2, 0.0, 1.1]],
        ],
        axis=0,
    )

    counts = isaac_fluid.classify_transfer_positions(
        positions,
        source_frame=source,
        target_frame=target,
        table_z=0.8,
        minimum_target_particles=150,
        minimum_task_target_fraction=0.5,
        minimum_expert_target_fraction=0.9,
    )

    assert counts["source"] == 3
    assert counts["target"] == 150
    assert counts["transit"] == 1
    assert counts["tabletop_spill"] == 0
    assert counts["below_table"] == 0
    assert counts["particle_count"] == 154
    assert counts["partition_complete"] is True
    assert counts["valid"] is True
    assert counts["fluid_transfer_passed"] is False
    assert counts["strict_zero_spill_transfer_passed"] is False
    assert counts["task_transfer_passed"] is True
    assert counts["expert_transfer_passed"] is True
    assert counts["target_fraction"] == pytest.approx(150 / 154)
    assert counts["source_fraction"] == pytest.approx(3 / 154)
    assert counts["transit_fraction"] == pytest.approx(1 / 154)
    assert counts["spill_fraction"] == 0.0
    assert counts["partition_fraction_total"] == pytest.approx(1.0)
    assert counts["category_bounds_world_m"]["source"] == {
        "min": pytest.approx([0.0, 0.0, 0.9]),
        "max": pytest.approx([0.0, 0.0, 0.9]),
    }
    assert counts["category_bounds_world_m"]["target"] == {
        "min": pytest.approx([0.4, 0.0, 0.9]),
        "max": pytest.approx([0.4, 0.0, 0.9]),
    }
    assert counts["category_bounds_world_m"]["transit"] == {
        "min": pytest.approx([0.2, 0.0, 1.1]),
        "max": pytest.approx([0.2, 0.0, 1.1]),
    }
    assert "tabletop_spill" not in counts["category_bounds_world_m"]

    settled = isaac_fluid.classify_transfer_positions(
        positions[:-1],
        source_frame=source,
        target_frame=target,
        table_z=0.8,
        minimum_target_particles=150,
        minimum_task_target_fraction=0.5,
        minimum_expert_target_fraction=0.9,
    )
    assert settled["fluid_transfer_passed"] is True


def test_transfer_classifier_rejects_tabletop_and_below_table_particles():
    source = _Frame((0.0, 0.0, 0.8))
    target = _Frame((0.4, 0.0, 0.8))
    points = np.concatenate(
        [
            np.tile([[0.4, 0.0, 0.9]], (150, 1)),
            [[0.2, 0.0, 0.81], [0.2, 0.0, 0.79]],
        ],
        axis=0,
    )

    counts = isaac_fluid.classify_transfer_positions(
        points,
        source_frame=source,
        target_frame=target,
        table_z=0.8,
        minimum_target_particles=150,
        minimum_task_target_fraction=0.5,
        minimum_expert_target_fraction=0.9,
    )

    assert counts["tabletop_spill"] == 1
    assert counts["below_table"] == 1
    assert counts["fluid_transfer_passed"] is False
    assert counts["task_transfer_passed"] is True
    assert counts["expert_transfer_passed"] is True
    assert counts["tabletop_spill_fraction"] == pytest.approx(1 / 152)
    assert counts["below_table_fraction"] == pytest.approx(1 / 152)
    assert counts["spill_fraction"] == pytest.approx(2 / 152)
    assert counts["category_bounds_world_m"]["tabletop_spill"]["min"] == (
        pytest.approx([0.2, 0.0, 0.81])
    )
    assert counts["category_bounds_world_m"]["below_table"]["max"] == (
        pytest.approx([0.2, 0.0, 0.79])
    )


def test_product_and_expert_transfer_thresholds_allow_spill_without_allowing_token_transfer():
    source = _Frame((0.0, 0.0, 0.8))
    target = _Frame((0.4, 0.0, 0.8))

    def classify(target_count, source_count=0, transit=0, tabletop=0):
        points = np.concatenate(
            [
                np.tile([[0.4, 0.0, 0.9]], (target_count, 1)),
                np.tile([[0.0, 0.0, 0.9]], (source_count, 1)),
                np.tile([[0.2, 0.0, 1.1]], (transit, 1)),
                np.tile([[0.2, 0.0, 0.81]], (tabletop, 1)),
            ],
            axis=0,
        )
        return isaac_fluid.classify_transfer_positions(
            points,
            source_frame=source,
            target_frame=target,
            table_z=0.8,
            minimum_target_particles=150,
            minimum_task_target_fraction=0.5,
            minimum_expert_target_fraction=0.9,
        )

    token_transfer = classify(150, source_count=3450)
    assert token_transfer["fluid_transfer_passed"] is True
    assert token_transfer["task_transfer_passed"] is False
    assert token_transfer["expert_transfer_passed"] is False

    task_boundary = classify(1800, source_count=1800)
    assert task_boundary["task_transfer_passed"] is True
    assert task_boundary["expert_transfer_passed"] is False
    assert classify(1799, source_count=1801)["task_transfer_passed"] is False

    expert_boundary = classify(3240, source_count=360)
    assert expert_boundary["expert_transfer_passed"] is True
    assert classify(3239, source_count=361)["expert_transfer_passed"] is False

    observed_pour = classify(3557, transit=29, tabletop=14)
    assert observed_pour["strict_zero_spill_transfer_passed"] is False
    assert observed_pour["task_transfer_passed"] is True
    assert observed_pour["expert_transfer_passed"] is True
    assert observed_pour["target_fraction"] == pytest.approx(3557 / 3600)


def test_nonfinite_particle_invalidates_all_transfer_results():
    source = _Frame((0.0, 0.0, 0.8))
    target = _Frame((0.4, 0.0, 0.8))
    result = isaac_fluid.classify_transfer_positions(
        [[0.4, 0.0, 0.9], [np.nan, 0.0, 0.9]],
        source_frame=source,
        target_frame=target,
        table_z=0.8,
        minimum_target_particles=1,
        minimum_task_target_fraction=0.5,
        minimum_expert_target_fraction=0.5,
    )

    assert result["valid"] is False
    assert result["fluid_transfer_passed"] is False
    assert result["task_transfer_passed"] is False
    assert result["expert_transfer_passed"] is False


def test_attachment_trigger_is_the_completed_scripted_gripper_close_phase():
    assert not isaac_fluid.scripted_grasp_is_closed(_controller(4))
    assert isaac_fluid.scripted_grasp_is_closed(_controller(5))
    assert not isaac_fluid.scripted_grasp_is_closed(_controller(5, "pouring"))


def test_rotational_handoff_requires_an_emitted_scripted_pour_velocity_action():
    assert not isaac_fluid.scripted_pour_velocity_was_emitted(
        _controller(5, "pouring", last_emitted_pour_event=1)
    )
    assert isaac_fluid.scripted_pour_velocity_was_emitted(
        _controller(5, "pouring", last_emitted_pour_event=2)
    )
    assert not isaac_fluid.scripted_pour_velocity_was_emitted(
        _controller(5, "picking", last_emitted_pour_event=2)
    )


def test_attachment_requests_can_come_from_collect_or_infer_controllers():
    collect = _controller(5, "pouring", last_emitted_pour_event=2)
    infer = SimpleNamespace(
        online_fluid_grasp_attachment_requested=lambda: True,
        online_fluid_rotation_handoff_requested=lambda: True,
    )

    assert isaac_fluid.fluid_grasp_attachment_requested(collect) is False
    assert isaac_fluid.fluid_rotation_handoff_requested(collect) is True
    assert isaac_fluid.fluid_grasp_attachment_requested(infer) is True
    assert isaac_fluid.fluid_rotation_handoff_requested(infer) is True


def test_attachment_preserves_source_to_gripper_relative_transform():
    source = _translation(0.3, 0.1, 0.8)
    gripper_at_attach = _translation(0.28, 0.1, 0.92)
    gripper_after = _translation(0.5, -0.2, 1.2)

    relative = isaac_fluid.relative_source_to_gripper_matrix(
        source,
        gripper_at_attach,
    )
    target = isaac_fluid.attached_source_world_matrix(relative, gripper_after)

    np.testing.assert_allclose(target[3, :3], [0.52, -0.2, 1.08], atol=1e-12)
    np.testing.assert_allclose(target[:3, :3], np.eye(3), atol=1e-12)


def test_staged_attachment_transport_is_pure_translation_and_holds_rotation():
    source_matrix = _translation(0.3, 0.1, 0.8)
    gripper_matrix = _translation(0.28, 0.1, 0.92)
    writes = []

    def write_source(matrix):
        source_matrix[:] = matrix
        writes.append(matrix.copy())

    attachment = isaac_fluid.GripperAttachedKinematicVessel(
        read_source_world_matrix=lambda: source_matrix.copy(),
        read_gripper_world_matrix=lambda: gripper_matrix.copy(),
        write_source_world_matrix=write_source,
    )

    attachment.reset()
    attachment.update_before_substep()
    assert len(writes) == 1
    assert attachment.record()["attached"] is False

    assert attachment.maybe_attach(_controller(5), {}) is True
    gripper_matrix[:] = _rotation_z(90)
    gripper_matrix[3, :3] = [0.5, -0.2, 1.2]
    attachment.update_before_substep()

    assert len(writes) == 2
    np.testing.assert_allclose(writes[-1][3, :3], [0.52, -0.2, 1.08])
    np.testing.assert_allclose(writes[-1][:3, :3], np.eye(3), atol=1e-12)
    assert attachment.record()["attached"] is True
    assert attachment.record()["attachment_count"] == 1
    assert attachment.record()["attachment_stage"] == "upright_translation"
    assert attachment.record()["rotation_handoff_count"] == 0
    assert attachment.record()["expert_attachment_valid"] is False
    assert attachment.record()["kinematic_target_update_count"] == 1


def test_staged_attachment_is_expert_valid_after_one_zero_jump_pour_handoff():
    source_matrix = _translation(0.3, 0.1, 0.8)
    gripper_matrix = _translation(0.28, 0.1, 0.92)

    def write_source(matrix):
        source_matrix[:] = matrix

    attachment = isaac_fluid.GripperAttachedKinematicVessel(
        read_source_world_matrix=lambda: source_matrix.copy(),
        read_gripper_world_matrix=lambda: gripper_matrix.copy(),
        write_source_world_matrix=write_source,
    )

    before = attachment.record()
    assert before["attachment_matrix_policy"] == (
        "captured_translation_then_recaptured_full_at_scripted_pour"
    )
    assert before["expert_attachment_valid"] is False

    attachment.maybe_attach(_controller(5), {})
    attached = attachment.record()

    assert attached["attachment_count"] == 1
    assert attached["rotation_handoff_count"] == 0
    assert attached["expert_attachment_valid"] is False
    assert attached["attachment_translation_jump_m"] == pytest.approx(0.0)
    assert attached["attachment_rotation_jump_degrees"] == pytest.approx(0.0)

    gripper_matrix[3, :3] += [0.2, -0.3, 0.25]
    attachment.update_before_substep()
    assert attachment.maybe_attach(
        _controller(5, "pouring", last_emitted_pour_event=1), {}
    ) is False
    assert attachment.maybe_attach(
        _controller(5, "pouring", last_emitted_pour_event=2), {}
    ) is True
    after = attachment.record()

    assert after["attached"] is True
    assert after["attachment_count"] == 1
    assert after["rotation_handoff_count"] == 1
    assert after["attachment_stage"] == "full_rigid_pour"
    assert after["expert_attachment_valid"] is True
    assert after["pour_handoff_translation_jump_m"] == pytest.approx(0.0)
    assert after["pour_handoff_rotation_jump_degrees"] == pytest.approx(0.0)
    assert len(after["applied_matrix_sha256"]) == 64
    np.testing.assert_allclose(
        after["pour_handoff_source_to_gripper_matrix"],
        after["applied_source_to_gripper_matrix"],
    )
    np.testing.assert_allclose(
        after["pre_pour_handoff_source_world_matrix"],
        after["first_pour_handoff_target_world_matrix"],
    )
    assert attachment.maybe_attach(
        _controller(5, "pouring", last_emitted_pour_event=2), {}
    ) is False
    assert attachment.record()["rotation_handoff_count"] == 1

    before_rigid_rotation = source_matrix.copy()
    gripper_matrix[:] = _rotation_z(30) @ gripper_matrix
    attachment.update_before_substep()
    assert not np.allclose(
        source_matrix[:3, :3], before_rigid_rotation[:3, :3]
    )


def test_staged_attachment_accepts_isaac_rotation_roundoff(monkeypatch):
    source_matrix = _translation(0.3, 0.1, 0.8)
    gripper_matrix = _translation(0.28, 0.1, 0.92)
    jump_measurements = iter(((0.0, 0.0), (0.0, 1.7e-6)))
    monkeypatch.setattr(
        isaac_fluid,
        "_pose_jump",
        lambda *_args, **_kwargs: next(jump_measurements),
    )

    attachment = isaac_fluid.GripperAttachedKinematicVessel(
        read_source_world_matrix=lambda: source_matrix.copy(),
        read_gripper_world_matrix=lambda: gripper_matrix.copy(),
        write_source_world_matrix=lambda matrix: source_matrix.__setitem__(
            slice(None), matrix
        ),
    )

    assert attachment.maybe_attach(_controller(5), {}) is True
    assert attachment.maybe_attach(
        _controller(5, "pouring", last_emitted_pour_event=2), {}
    ) is True
    record = attachment.record()

    assert record["pour_handoff_rotation_jump_degrees"] == pytest.approx(1.7e-6)
    assert record["expert_attachment_valid"] is True


def test_staged_attachment_rejects_rotation_above_numerical_tolerance(monkeypatch):
    source_matrix = _translation(0.3, 0.1, 0.8)
    gripper_matrix = _translation(0.28, 0.1, 0.92)
    jump_measurements = iter(((0.0, 0.0), (0.0, 1.1e-5)))
    monkeypatch.setattr(
        isaac_fluid,
        "_pose_jump",
        lambda *_args, **_kwargs: next(jump_measurements),
    )
    attachment = isaac_fluid.GripperAttachedKinematicVessel(
        read_source_world_matrix=lambda: source_matrix.copy(),
        read_gripper_world_matrix=lambda: gripper_matrix.copy(),
        write_source_world_matrix=lambda matrix: source_matrix.__setitem__(
            slice(None), matrix
        ),
    )

    attachment.maybe_attach(_controller(5), {})
    attachment.maybe_attach(
        _controller(5, "pouring", last_emitted_pour_event=2), {}
    )

    assert attachment.record()["expert_attachment_valid"] is False


def test_staged_attachment_supports_model_infer_handoff_without_pour_controller():
    source_matrix = _translation(0.3, 0.1, 0.8)
    gripper_matrix = _translation(0.28, 0.1, 0.92)
    request = {"grasp": True, "rotation": False}
    controller = SimpleNamespace(
        online_fluid_grasp_attachment_requested=lambda: request["grasp"],
        online_fluid_rotation_handoff_requested=lambda: request["rotation"],
    )

    attachment = isaac_fluid.GripperAttachedKinematicVessel(
        read_source_world_matrix=lambda: source_matrix.copy(),
        read_gripper_world_matrix=lambda: gripper_matrix.copy(),
        write_source_world_matrix=lambda matrix: source_matrix.__setitem__(
            slice(None), matrix
        ),
    )

    assert attachment.maybe_attach(controller, {}) is True
    request["rotation"] = True
    assert attachment.maybe_attach(controller, {}) is True
    assert attachment.record()["attachment_stage"] == "full_rigid_pour"
    assert attachment.record()["rotation_handoff_count"] == 1


def test_attachment_reset_clears_captured_attempt_state():
    source_matrix = _translation(0.3, 0.1, 0.8)
    gripper_matrix = _translation(0.28, 0.1, 0.92)
    attachment = isaac_fluid.GripperAttachedKinematicVessel(
        read_source_world_matrix=lambda: source_matrix.copy(),
        read_gripper_world_matrix=lambda: gripper_matrix.copy(),
        write_source_world_matrix=lambda matrix: None,
    )
    attachment.maybe_attach(_controller(5), {})

    attachment.reset()
    record = attachment.record()

    assert record["attached"] is False
    assert record["attachment_count"] == 0
    assert record["rotation_handoff_count"] == 0
    assert record["attachment_stage"] == "unattached"
    assert record["expert_attachment_valid"] is False
    assert record["observed_source_to_gripper_matrix"] is None
    assert record["attachment_matrix_policy"] == (
        "captured_translation_then_recaptured_full_at_scripted_pour"
    )


def test_single_rigid_writer_uses_physx_kinematic_target_not_teleport():
    calls = []

    class _PhysicsView:
        def set_kinematic_targets(self, transforms, indices):
            calls.append((transforms.copy(), indices.copy()))

    source_body = SimpleNamespace(
        _prim_view=SimpleNamespace(_physics_view=_PhysicsView())
    )

    isaac_fluid.set_single_rigid_kinematic_target(
        source_body,
        position=np.asarray([0.3, -0.2, 1.1]),
        orientation_wxyz=np.asarray([0.5, 0.5, 0.5, 0.5]),
    )

    assert len(calls) == 1
    transforms, indices = calls[0]
    assert transforms.shape == (1, 7)
    assert transforms.dtype == np.float32
    np.testing.assert_allclose(
        transforms[0], [0.3, -0.2, 1.1, 0.5, 0.5, 0.5, 0.5]
    )
    np.testing.assert_array_equal(indices, np.asarray([0], dtype=np.int32))


def test_synthetic_attachment_filters_only_source_to_robot_rigid_collisions():
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    source = UsdGeom.Xform.Define(stage, "/World/beaker2").GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(source)
    source.CreateAttribute(
        "physics:kinematicEnabled",
        pytest.importorskip("pxr.Sdf").ValueTypeNames.Bool,
    ).Set(True)
    existing_target = UsdGeom.Xform.Define(stage, "/World/existingFilter").GetPrim()
    filtered_pairs = UsdPhysics.FilteredPairsAPI.Apply(source)
    filtered_pairs.CreateFilteredPairsRel().SetTargets([existing_target.GetPath()])

    robot = UsdGeom.Xform.Define(stage, "/World/Franka").GetPrim()
    link0 = UsdGeom.Xform.Define(stage, "/World/Franka/panda_link0").GetPrim()
    link1 = UsdGeom.Xform.Define(stage, "/World/Franka/panda_link1").GetPrim()
    disabled_link = UsdGeom.Xform.Define(
        stage, "/World/Franka/disabled_link"
    ).GetPrim()
    for link in (link0, link1, disabled_link):
        UsdPhysics.RigidBodyAPI.Apply(link)
    disabled_link.CreateAttribute(
        "physics:rigidBodyEnabled",
        pytest.importorskip("pxr.Sdf").ValueTypeNames.Bool,
    ).Set(False)
    UsdPhysics.CollisionAPI.Apply(
        UsdGeom.Cube.Define(stage, "/World/Franka/panda_link0/collider").GetPrim()
    )
    UsdGeom.Xform.Define(stage, "/World/Franka/visualOnly")
    table = UsdGeom.Xform.Define(stage, "/World/table").GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(table)

    record = isaac_fluid.author_synthetic_attachment_collision_filter(
        stage,
        source_body_path="/World/beaker2",
        robot_root_path=str(robot.GetPath()),
    )

    assert record == {
        "source_body_path": "/World/beaker2",
        "robot_root_path": "/World/Franka",
        "robot_rigid_body_paths": [
            "/World/Franka/panda_link0",
            "/World/Franka/panda_link1",
        ],
    }
    assert [
        str(path)
        for path in filtered_pairs.GetFilteredPairsRel().GetTargets()
    ] == [
        "/World/Franka/panda_link0",
        "/World/Franka/panda_link1",
        "/World/existingFilter",
    ]
    assert isaac_fluid.author_synthetic_attachment_collision_filter(
        stage,
        source_body_path="/World/beaker2",
        robot_root_path="/World/Franka",
    ) == record
    assert len(filtered_pairs.GetFilteredPairsRel().GetTargets()) == 3


def test_single_rigid_wrapper_disables_xform_reset_when_constructor_supports_it():
    class LegacySingleRigidPrim:
        def __init__(self, prim_path, name, reset_xform_properties=True):
            self.arguments = (prim_path, name, reset_xform_properties)

    wrapper = isaac_fluid.construct_single_rigid_prim(
        LegacySingleRigidPrim,
        prim_path="/World/beaker2",
        name="source",
    )

    assert wrapper.arguments == ("/World/beaker2", "source", False)


def test_single_rigid_wrapper_omits_xform_argument_when_constructor_lacks_it():
    class ModernSingleRigidPrim:
        def __init__(self, prim_path, name):
            self.arguments = (prim_path, name)

    wrapper = isaac_fluid.construct_single_rigid_prim(
        ModernSingleRigidPrim,
        prim_path="/World/beaker2",
        name="source",
    )

    assert wrapper.arguments == ("/World/beaker2", "source")


def test_configure_fluid_world_timing_reasserts_runtime_dt():
    class World:
        def __init__(self):
            self.physics_dt = 1.0 / 60.0
            self.rendering_dt = 1.0 / 60.0

        def set_simulation_dt(self, *, physics_dt, rendering_dt):
            self.physics_dt = physics_dt
            self.rendering_dt = rendering_dt

        def get_physics_dt(self):
            return self.physics_dt

        def get_rendering_dt(self):
            return self.rendering_dt

    world = World()

    isaac_fluid.configure_fluid_world_timing(
        world,
        physics_dt=1.0 / 120.0,
        rendering_dt=1.0 / 30.0,
    )

    assert world.get_physics_dt() == pytest.approx(1.0 / 120.0)
    assert world.get_rendering_dt() == pytest.approx(1.0 / 30.0)


def test_configure_fluid_world_timing_rejects_ignored_runtime_dt():
    world = SimpleNamespace(
        set_simulation_dt=lambda **kwargs: None,
        get_physics_dt=lambda: 1.0 / 60.0,
        get_rendering_dt=lambda: 1.0 / 30.0,
    )

    with pytest.raises(RuntimeError, match="fluid_world_physics_dt_mismatch"):
        isaac_fluid.configure_fluid_world_timing(
            world,
            physics_dt=1.0 / 120.0,
            rendering_dt=1.0 / 30.0,
        )


def test_world_pose_to_row_affine_matrix_preserves_wxyz_rotation_convention():
    half_sqrt_two = np.sqrt(0.5)

    matrix = isaac_fluid._world_pose_to_matrix(
        position=[1.0, 2.0, 3.0],
        orientation_wxyz=[half_sqrt_two, 0.0, 0.0, half_sqrt_two],
    )

    np.testing.assert_allclose(
        matrix,
        [
            [0.0, 1.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [1.0, 2.0, 3.0, 1.0],
        ],
        atol=1.0e-7,
    )
    np.testing.assert_allclose(
        isaac_fluid._world_pose_to_matrix(
            position=[1.0, 2.0, 3.0],
            orientation_wxyz=[-half_sqrt_two, 0.0, 0.0, -half_sqrt_two],
        ),
        matrix,
        atol=1.0e-7,
    )


def test_world_pose_to_row_affine_matrix_rejects_invalid_quaternion():
    with pytest.raises(ValueError, match="world_pose_orientation_invalid"):
        isaac_fluid._world_pose_to_matrix(
            position=[0.0, 0.0, 0.0],
            orientation_wxyz=[0.0, 0.0, 0.0, 0.0],
        )


def test_tracked_child_world_matrix_follows_physics_parent_pose():
    authored_parent = _translation(0.3, -0.2, 0.8)
    authored_child = _translation(0.4, -0.2, 0.85)
    half_sqrt_two = np.sqrt(0.5)
    current_parent = isaac_fluid._world_pose_to_matrix(
        position=[1.0, 2.0, 3.0],
        orientation_wxyz=[half_sqrt_two, 0.0, 0.0, half_sqrt_two],
    )

    current_child = isaac_fluid._tracked_child_world_matrix(
        child_authored_world=authored_child,
        parent_authored_world=authored_parent,
        parent_current_world=current_parent,
    )

    np.testing.assert_allclose(current_child[3, :3], [1.0, 2.1, 3.05], atol=1e-7)
    np.testing.assert_allclose(current_child[0, :3], [0.0, 1.0, 0.0], atol=1e-7)
    np.testing.assert_allclose(current_child[1, :3], [-1.0, 0.0, 0.0], atol=1e-7)
    np.testing.assert_allclose(current_child[2, :3], [0.0, 0.0, 1.0], atol=1e-7)


def test_source_visual_mesh_sync_resets_stale_delta_then_follows_physics():
    authored_source = _translation(0.3, -0.2, 0.8)
    authored_mesh = _translation(0.4, -0.2, 0.85)
    authored_mesh[:3, :3] = np.diag([1.2, 0.8, 1.1])
    stale_source = _rotation_z(45)
    stale_source[3, :3] = [0.8, 0.3, 1.1]
    current_source = _rotation_z(90)
    current_source[3, :3] = [1.0, 2.0, 3.0]
    current_mesh = (
        authored_mesh
        @ np.linalg.inv(authored_source)
        @ stale_source
    )
    written_deltas = []

    def write_visual_mesh_parent_delta(delta):
        nonlocal current_mesh
        written_deltas.append(np.asarray(delta, dtype=np.float64).copy())
        current_mesh = (
            authored_mesh
            @ np.linalg.inv(authored_source)
            @ written_deltas[-1]
            @ authored_source
        )

    synchronizer = isaac_fluid.SourceVisualMeshSynchronizer(
        source_authored_world_matrix=authored_source,
        read_source_world_matrix=lambda: current_source.copy(),
        read_visual_mesh_world_matrix=lambda: current_mesh.copy(),
        write_visual_mesh_parent_delta=write_visual_mesh_parent_delta,
    )

    np.testing.assert_allclose(written_deltas[0], np.eye(4), atol=1e-8)
    np.testing.assert_allclose(current_mesh, authored_mesh, atol=1e-8)

    moved = synchronizer.sync()
    expected_moved = isaac_fluid._tracked_child_world_matrix(
        child_authored_world=authored_mesh,
        parent_authored_world=authored_source,
        parent_current_world=current_source,
    )

    assert moved["policy"] == "visual_mesh_parent_delta_v1"
    assert moved["valid"] is True
    np.testing.assert_allclose(current_mesh, expected_moved, atol=1e-8)
    np.testing.assert_allclose(
        written_deltas[-1],
        current_source @ np.linalg.inv(authored_source),
        atol=1e-8,
    )

    current_source = authored_source.copy()
    reset = synchronizer.sync()

    assert reset["valid"] is True
    np.testing.assert_allclose(written_deltas[-1], np.eye(4), atol=1e-8)
    np.testing.assert_allclose(current_mesh, authored_mesh, atol=1e-8)


def test_physics_pose_reader_and_source_score_share_current_rigid_pose():
    from tools.labutopia_fluid.real_beaker import CupInteriorFrame

    pose = {
        "position": np.asarray([0.4, -0.2, 0.8], dtype=np.float32),
        "orientation": np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
    }
    source_body = SimpleNamespace(
        get_world_pose=lambda: (pose["position"], pose["orientation"])
    )
    template = CupInteriorFrame(
        origin_world=(0.0, 0.0, 0.0),
        x_axis_world=(1.0, 0.0, 0.0),
        y_axis_world=(0.0, 1.0, 0.0),
        z_axis_world=(0.0, 0.0, 1.0),
        parent_local_axis="Z",
        outer_radius=0.11,
        interior_radius=0.1,
        outer_floor=-0.01,
        interior_floor=0.0,
        rim_height=0.2,
        calibration_source="test",
        axis_alignment_dot=1.0,
    )
    authored_parent = np.eye(4, dtype=np.float64)
    authored_child = np.eye(4, dtype=np.float64)

    def source_frame():
        parent_world = isaac_fluid._single_rigid_world_matrix(source_body)
        child_world = isaac_fluid._tracked_child_world_matrix(
            child_authored_world=authored_child,
            parent_authored_world=authored_parent,
            parent_current_world=parent_world,
        )
        return isaac_fluid._frame_at_world_matrix(template, child_world)

    scorer = isaac_fluid.FluidTransferScorer(
        source_frame=source_frame,
        target_frame=lambda: _Frame((2.0, 0.0, 0.8)),
        table_z=0.75,
        minimum_target_particles=1,
        minimum_task_target_fraction=0.5,
        minimum_expert_target_fraction=0.9,
    )

    first = scorer(np.asarray([[0.4, -0.2, 0.9]]))
    assert first["source"] == 1
    assert first["transit"] == 0

    pose["position"] = np.asarray([0.8, 0.3, 1.1], dtype=np.float32)
    moved = scorer(np.asarray([[0.8, 0.3, 1.2]]))
    assert moved["source"] == 1
    assert moved["transit"] == 0
    assert moved["source_frame_origin_world"] == pytest.approx([0.8, 0.3, 1.1])
    assert moved["source_frame_z_axis_world"] == pytest.approx([0.0, 0.0, 1.0])
    assert moved["target_frame_origin_world"] == pytest.approx([2.0, 0.0, 0.8])


def test_physics_source_state_adapter_tracks_geometry_center_and_xyzw_pose():
    half_sqrt_two = np.sqrt(0.5)
    pose = {
        "position": np.asarray([0.3, -0.2, 0.8], dtype=np.float64),
        "orientation": np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
    }
    camera = np.zeros((3, 4, 4), dtype=np.uint8)
    original = {
        "object_position": np.asarray([0.4, -0.2, 0.85]),
        "object_quaternion": np.asarray([9.0, 9.0, 9.0, 9.0]),
        "camera_data": {"camera_1_rgb": camera},
    }
    adapter = isaac_fluid.PhysicsSourceStateAdapter(
        read_source_world_pose=lambda: (pose["position"], pose["orientation"]),
        initial_geometry_center_world=original["object_position"],
    )

    reset_state = adapter(original)
    np.testing.assert_allclose(reset_state["object_position"], [0.4, -0.2, 0.85])
    np.testing.assert_allclose(reset_state["object_quaternion"], [0.0, 0.0, 0.0, 1.0])
    assert reset_state is not original
    assert reset_state["camera_data"] is original["camera_data"]
    assert reset_state["camera_data"]["camera_1_rgb"] is camera
    np.testing.assert_allclose(original["object_quaternion"], [9.0, 9.0, 9.0, 9.0])

    pose["position"] = np.asarray([1.0, 2.0, 3.0])
    pose["orientation"] = np.asarray(
        [half_sqrt_two, 0.0, 0.0, half_sqrt_two]
    )
    moved_state = adapter(original)

    np.testing.assert_allclose(moved_state["object_position"], [1.0, 2.1, 3.05])
    np.testing.assert_allclose(
        moved_state["object_quaternion"],
        [0.0, 0.0, half_sqrt_two, half_sqrt_two],
    )


def test_camera_contract_record_binds_resolved_usd_optics_and_transform():
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    configs = []
    for index, path in enumerate(("/World/Context", "/World/Closeup"), start=1):
        camera = UsdGeom.Camera.Define(stage, path)
        camera.CreateFocalLengthAttr(22.0)
        camera.CreateHorizontalApertureAttr(24.0)
        camera.CreateVerticalApertureAttr(16.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
        UsdGeom.Xformable(camera).AddTranslateOp().Set((index, 0.0, 1.0))
        configs.append(
            SimpleNamespace(
                prim_path=path,
                name=f"camera_{index}",
                resolution=[256, 256],
                frequency=30,
                focal_length=22.0,
                clipping_range=[0.01, 100.0],
                image_type="rgb",
            )
        )

    record = isaac_fluid.resolve_camera_contract_record(
        stage,
        contract_id="level1_pour_rgb_v4_full_action_30hz",
        camera_configs=configs,
        compatibility="requires_v4_data_or_model",
        rendering_dt=1.0 / 30.0,
    )

    assert record["schema_version"] == 2
    assert record["id"] == "level1_pour_rgb_v4_full_action_30hz"
    assert record["compatibility"] == "requires_v4_data_or_model"
    assert record["rendering_dt"] == pytest.approx(1.0 / 30.0)
    assert len(record["sha256"]) == 64
    assert [camera["prim_path"] for camera in record["cameras"]] == [
        "/World/Context",
        "/World/Closeup",
    ]
    assert all(camera["focal_length"] == pytest.approx(22.0) for camera in record["cameras"])
    assert all(camera["frequency"] == 30 for camera in record["cameras"])
    assert all(camera["clipping_range"] == pytest.approx([0.01, 100.0]) for camera in record["cameras"])
    assert record["cameras"][1]["world_transform"][3][:3] == pytest.approx(
        [2.0, 0.0, 1.0]
    )

    UsdGeom.Camera(stage.GetPrimAtPath("/World/Closeup")).GetFocalLengthAttr().Set(5.0)
    with pytest.raises(ValueError, match="camera_focal_length_mismatch"):
        isaac_fluid.resolve_camera_contract_record(
            stage,
            contract_id="level1_pour_rgb_v4_full_action_30hz",
            camera_configs=configs,
            compatibility="requires_v4_data_or_model",
            rendering_dt=1.0 / 30.0,
        )


def test_camera_contract_hash_binds_frequency_and_rendering_dt():
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Camera.Define(stage, "/World/Camera")
    base = SimpleNamespace(
        prim_path="/World/Camera",
        name="camera_1",
        resolution=[256, 256],
        frequency=30,
        focal_length=50.0,
        image_type="rgb",
    )

    first = isaac_fluid.resolve_camera_contract_record(
        stage,
        contract_id="camera_v1",
        camera_configs=[base],
        compatibility="requires_camera_v1",
        rendering_dt=1.0 / 30.0,
    )
    base.frequency = 60
    second = isaac_fluid.resolve_camera_contract_record(
        stage,
        contract_id="camera_v1",
        camera_configs=[base],
        compatibility="requires_camera_v1",
        rendering_dt=1.0 / 30.0,
    )
    base.frequency = 30
    third = isaac_fluid.resolve_camera_contract_record(
        stage,
        contract_id="camera_v1",
        camera_configs=[base],
        compatibility="requires_camera_v1",
        rendering_dt=1.0 / 60.0,
    )

    assert len({first["sha256"], second["sha256"], third["sha256"]}) == 3
    assert (
        isaac_fluid.require_camera_contract_sha256(
            first, expected_sha256=first["sha256"]
        )
        is first
    )
    with pytest.raises(ValueError, match="camera_contract_sha256_mismatch"):
        isaac_fluid.require_camera_contract_sha256(
            first, expected_sha256="0" * 64
        )


def test_usd_surface_author_replaces_particle_visual_and_invalidates_stale_mesh():
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    points = UsdGeom.Points.Define(stage, "/World/Fluid/Particles")
    points.CreatePointsAttr([(0.0, 0.0, 0.0)])
    system = UsdGeom.Xform.Define(stage, "/World/Fluid/ParticleSystem").GetPrim()
    system.CreateAttribute(
        "physxParticleIsosurface:isosurfaceEnabled",
        pytest.importorskip("pxr.Sdf").ValueTypeNames.Bool,
    ).Set(True)
    token = SimpleNamespace(identity="frame-token-1")
    mesh = {
        "vertices": np.asarray(
            [[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]], dtype=np.float32
        ),
        "faces": np.asarray([[0, 1, 2]], dtype=np.int32),
        "normals": np.asarray(
            [[0, 0, 1], [0, 0, 1], [0, 0, 1]], dtype=np.float32
        ),
        "origin_world_m": [0.25, -0.1, 0.8],
    }
    author = isaac_fluid.IsaacFluidSurfaceAuthor(
        stage=stage,
        surface_path="/World/OnlineFluidSurface",
        material_path="/World/Looks/OnlineFluidWater",
        hidden_liquid_paths=("/World/Fluid/Particles",),
        particle_system_path="/World/Fluid/ParticleSystem",
    )

    record = author(mesh, token)

    surface = stage.GetPrimAtPath("/World/OnlineFluidSurface")
    assert record["surface_token"] == "frame-token-1"
    assert record["vertex_count"] == 3
    assert record["face_count"] == 1
    assert surface.GetAttribute("labutopia:surfaceFrameToken").Get() == "frame-token-1"
    assert UsdGeom.Imageable(surface).GetVisibilityAttr().Get() == "inherited"
    assert UsdGeom.Imageable(points.GetPrim()).GetVisibilityAttr().Get() == "invisible"
    assert system.GetAttribute("physxParticleIsosurface:isosurfaceEnabled").Get() is False

    author.invalidate("test_failure")
    assert UsdGeom.Imageable(surface).GetVisibilityAttr().Get() == "invisible"

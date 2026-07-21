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


_SOURCE_BODY = "/World/beaker2"
_SOURCE_COLLIDER = "/World/beaker2/mesh"
_LEFT_FINGER_BODY = "/World/Franka/panda_leftfinger"
_RIGHT_FINGER_BODY = "/World/Franka/panda_rightfinger"
_LEFT_FINGER_COLLIDER = f"{_LEFT_FINGER_BODY}/collision"
_RIGHT_FINGER_COLLIDER = f"{_RIGHT_FINGER_BODY}/collision"
_SOURCE_CENTER_WORLD_M = (0.3, 0.1, 0.9)
_FINGER_SIDE_AXIS_WORLD = (0.0, 1.0, 0.0)


def _full_report_header(event_name, *, contact_count=1):
    return SimpleNamespace(
        type=SimpleNamespace(name=event_name),
        stage_id=7,
        actor0=1,
        actor1=2,
        collider0=3,
        collider1=4,
        proto_index0=0xFFFFFFFF,
        proto_index1=0xFFFFFFFF,
        contact_data_offset=0,
        num_contact_data=contact_count,
        friction_anchors_offset=0,
        num_friction_anchors_data=1 if contact_count else 0,
    )


def _full_report_contact():
    return SimpleNamespace(
        position=(0.1, 0.2, 0.3),
        normal=(1.0, 0.0, 0.0),
        impulse=(0.0001, 0.0, 0.0),
        separation=-0.0001,
        face_index0=5,
        face_index1=6,
        material0=8,
        material1=9,
    )


def _full_report_friction():
    return SimpleNamespace(
        position=(0.1, 0.2, 0.3),
        impulse=(0.0, 0.00001, 0.0),
    )


def _report_paths(value):
    return {
        1: "/World/source",
        2: "/World/table",
        3: "/World/source/collider",
        4: "/World/table/collider",
        8: "/World/material0",
        9: "/World/material1",
    }[value]


def test_immediate_full_contact_report_normalizes_and_reads_exactly_once():
    calls = []
    reports = iter(
        [
            (
                [_full_report_header("CONTACT_FOUND")],
                [_full_report_contact()],
                [_full_report_friction()],
            ),
            (
                [_full_report_header("CONTACT_PERSIST")],
                [_full_report_contact()],
                [_full_report_friction()],
            ),
        ]
    )

    def get_full_contact_report():
        calls.append("read")
        return next(reports)

    reporter = isaac_fluid.ImmediatePhysxContactReporter(
        get_full_contact_report=get_full_contact_report,
        resolve_path=_report_paths,
        expected_stage_id=7,
    )
    found = reporter.sample(physics_index=0)
    persisted = reporter.sample(physics_index=1)

    assert calls == ["read", "read"]
    assert found["immediate_read_index"] == 0
    assert persisted["immediate_read_index"] == 1
    occurrence = found["occurrences"][0]
    assert occurrence["event_sequence"] == "FOUND"
    assert occurrence["headers"][0]["actor0"] == "/World/source"
    assert occurrence["contact_data"][0] == {
        "position": [0.1, 0.2, 0.3],
        "normal": [1.0, 0.0, 0.0],
        "impulse": [0.0001, 0.0, 0.0],
        "separation": -0.0001,
        "face_index0": 5,
        "face_index1": 6,
        "material0": "/World/material0",
        "material1": "/World/material1",
    }
    assert occurrence["friction_anchors"][0]["impulse"] == [
        0.0,
        0.00001,
        0.0,
    ]


def test_immediate_full_contact_report_rejects_malformed_api_tuple():
    reporter = isaac_fluid.ImmediatePhysxContactReporter(
        get_full_contact_report=lambda: ([], []),
        resolve_path=_report_paths,
        expected_stage_id=7,
    )
    with pytest.raises(RuntimeError, match="full_contact_report_tuple_invalid"):
        reporter.sample(physics_index=0)


def _contact_gate():
    return isaac_fluid.BilateralContactGraspGate(
        source_body_path=_SOURCE_BODY,
        source_collider_path=_SOURCE_COLLIDER,
        left_finger_body_path=_LEFT_FINGER_BODY,
        right_finger_body_path=_RIGHT_FINGER_BODY,
        minimum_normal_impulse_n_s=0.001,
        minimum_side_projection_m=0.005,
        required_consecutive_steps=5,
        grasp_height_axis_object=(0.0, 0.0, 1.0),
        grasp_height_band_m=(-0.02, 0.02),
        maximum_bilateral_height_difference_m=0.005,
        minimum_inward_normal_cosine=0.8,
        minimum_opposing_normal_cosine=0.8,
    )


def _bilateral_contacts(physics_step):
    return [
        {
            "physics_step": physics_step,
            "body0_path": _SOURCE_BODY,
            "body1_path": _LEFT_FINGER_BODY,
            "collider0_path": _SOURCE_COLLIDER,
            "collider1_path": _LEFT_FINGER_COLLIDER,
            "position_world_m": (0.3, 0.095, 0.9),
            "normal_body1_to_body0_world": (0.0, 1.0, 0.0),
            "normal_impulse_n_s": 0.001,
        },
        {
            "physics_step": physics_step,
            "body0_path": _RIGHT_FINGER_BODY,
            "body1_path": _SOURCE_BODY,
            "collider0_path": _RIGHT_FINGER_COLLIDER,
            "collider1_path": _SOURCE_COLLIDER,
            "position_world_m": (0.3, 0.105, 0.9),
            "normal_body1_to_body0_world": (0.0, 1.0, 0.0),
            "normal_impulse_n_s": 0.001,
        },
    ]


def _observe_contacts(gate, physics_step, contacts=None):
    return gate.update(
        physics_step=physics_step,
        contacts=(
            _bilateral_contacts(physics_step) if contacts is None else contacts
        ),
        source_center_world_m=_SOURCE_CENTER_WORLD_M,
        source_world_matrix=_translation(*_SOURCE_CENTER_WORLD_M),
        finger_side_axis_world=_FINGER_SIDE_AXIS_WORLD,
    )


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


def test_substep_containment_sampler_refreshes_source_before_read_and_score():
    events = []
    positions = np.asarray([[0.1, 0.2, 0.3]], dtype=np.float64)

    def capture_source():
        events.append("capture_source")

    def read_particles():
        events.append("read_particles")
        return positions

    def score_particles(values):
        events.append("score_particles")
        assert values is positions
        return {"source": 1}

    sampler = isaac_fluid.make_substep_containment_sampler(
        read_particles=read_particles,
        score_particles=score_particles,
        capture_source_state=capture_source,
    )

    assert sampler() == {"source": 1}
    assert events == ["capture_source", "read_particles", "score_particles"]


def test_bilateral_contact_gate_accepts_threshold_contacts_on_fifth_step():
    gate = _contact_gate()

    assert [_observe_contacts(gate, step) for step in range(5)] == [
        False,
        False,
        False,
        False,
        True,
    ]


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (
            lambda contacts: contacts[0].update(
                collider0_path=f"{_SOURCE_BODY}/FluidSafeWrapperCanonical/wall_000"
            ),
            "contact_source_collider_not_external_shell",
        ),
        (
            lambda contacts: contacts[0].update(
                normal_body1_to_body0_world=(0.0, -1.0, 0.0)
            ),
            "contact_normal_not_inward",
        ),
        (
            lambda contacts: contacts[0].update(
                position_world_m=(0.3, 0.095, 0.921)
            ),
            "contact_outside_grasp_band",
        ),
            (
                lambda contacts: contacts[1].update(
                    position_world_m=(0.3, 0.11, 0.9050001)
                ),
            "contact_bilateral_height_mismatch",
        ),
    ],
)
def test_bilateral_contact_gate_rejects_non_authoritative_geometry(mutate, reason):
    gate = _contact_gate()
    contacts = _bilateral_contacts(0)
    mutate(contacts)

    assert _observe_contacts(gate, 0, contacts) is False
    record = gate.record()
    assert record["valid_this_step"] is False
    assert record["failure_reason"] == reason


def test_bilateral_contact_gate_uses_current_source_object_height_axis():
    gate = isaac_fluid.BilateralContactGraspGate(
        source_body_path=_SOURCE_BODY,
        source_collider_path=_SOURCE_COLLIDER,
        left_finger_body_path=_LEFT_FINGER_BODY,
        right_finger_body_path=_RIGHT_FINGER_BODY,
        minimum_normal_impulse_n_s=0.001,
        minimum_side_projection_m=0.005,
        required_consecutive_steps=1,
        grasp_height_axis_object=(1.0, 0.0, 0.0),
        grasp_height_band_m=(-0.01, 0.01),
        maximum_bilateral_height_difference_m=0.011,
        minimum_inward_normal_cosine=0.8,
        minimum_opposing_normal_cosine=0.8,
    )
    source_world = _rotation_z(90)
    source_world[3, :3] = _SOURCE_CENTER_WORLD_M
    contacts = _bilateral_contacts(12)

    assert gate.update(
        physics_step=12,
        contacts=contacts,
        source_center_world_m=_SOURCE_CENTER_WORLD_M,
        source_world_matrix=source_world,
        finger_side_axis_world=_FINGER_SIDE_AXIS_WORLD,
    ) is True
    assert gate.record()["height_m"] == pytest.approx(
        {"left": -0.005, "right": 0.005}
    )


def test_derived_per_finger_impulse_uses_payload_friction_dt_and_fixed_safety_factor():
    record = isaac_fluid.derive_minimum_per_finger_normal_impulse(
        effective_payload_mass_kg=0.12,
        effective_friction=0.8,
        physics_dt=1 / 120,
        gravity_m_s2=9.81,
    )

    assert record["safety_factor"] == 2.0
    assert record["supporting_finger_count"] == 2
    assert record["minimum_per_finger_normal_impulse_n_s"] == pytest.approx(
        2.0 * 0.12 * 9.81 * (1 / 120) / (2 * 0.8)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("effective_payload_mass_kg", 0.0),
        ("effective_friction", float("nan")),
        ("physics_dt", -1.0),
        ("gravity_m_s2", True),
    ],
)
def test_derived_per_finger_impulse_rejects_invalid_inputs(field, value):
    kwargs = {
        "effective_payload_mass_kg": 0.12,
        "effective_friction": 0.8,
        "physics_dt": 1 / 120,
        "gravity_m_s2": 9.81,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=f"contact_gate_{field}_invalid"):
        isaac_fluid.derive_minimum_per_finger_normal_impulse(**kwargs)


@pytest.mark.parametrize("invalid_kind", ["stale", "wrong_body", "one_sided"])
def test_bilateral_contact_gate_rejects_invalid_contact_history(invalid_kind):
    gate = _contact_gate()
    for step in range(4):
        assert _observe_contacts(gate, step) is False

    contacts = _bilateral_contacts(4)
    if invalid_kind == "stale":
        contacts = _bilateral_contacts(3)
    elif invalid_kind == "wrong_body":
        contacts[1]["body1_path"] = f"{_SOURCE_BODY}/mesh"
    else:
        contacts = contacts[:1]
    assert _observe_contacts(gate, 4, contacts) is False

    for step in range(5, 9):
        assert _observe_contacts(gate, step) is False
    assert _observe_contacts(gate, 9) is True


def test_bilateral_contact_gate_rejects_impact_only_contact():
    gate = _contact_gate()

    assert _observe_contacts(gate, 0) is False
    assert _observe_contacts(gate, 1, []) is False
    for step in range(2, 6):
        assert _observe_contacts(gate, step) is False
    assert _observe_contacts(gate, 6) is True


def test_bilateral_contact_gate_reset_clears_qualification_history():
    gate = _contact_gate()
    for step in range(4):
        assert _observe_contacts(gate, step) is False

    gate.reset()

    for step in range(100, 104):
        assert _observe_contacts(gate, step) is False
    assert _observe_contacts(gate, 104) is True


def _sensor_contact_frames(physics_step, *, contacts=True):
    left_contact = {
        "body0": _SOURCE_COLLIDER,
        "body1": _LEFT_FINGER_COLLIDER,
        "position": np.asarray([0.3, 0.095, 0.9], dtype=np.float32),
        "normal": np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
        "impulse": np.asarray([0.0, 0.001, 0.0], dtype=np.float32),
    }
    right_contact = {
        "body0": _RIGHT_FINGER_COLLIDER,
        "body1": _SOURCE_COLLIDER,
        "position": np.asarray([0.3, 0.105, 0.9], dtype=np.float32),
        "normal": np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
        "impulse": np.asarray([0.0, 0.001, 0.0], dtype=np.float32),
    }
    return {
        "left": {
            "physics_step": float(physics_step),
            "contacts": [left_contact] if contacts else [],
        },
        "right": {
            "physics_step": float(physics_step),
            "contacts": [right_contact] if contacts else [],
        },
        "hand": {
            "physics_step": float(physics_step),
            "contacts": [],
        },
    }


def test_contact_sensor_frames_normalize_current_raw_contacts_without_duplicates():
    frames = _sensor_contact_frames(12)
    duplicate = dict(frames["left"]["contacts"][0])
    frames["right"]["contacts"].append(duplicate)

    contacts = isaac_fluid.normalize_contact_sensor_frames(
        frames,
        expected_physics_step=12,
        resolve_body_path=lambda path: {
            _SOURCE_COLLIDER: _SOURCE_BODY,
            _LEFT_FINGER_COLLIDER: _LEFT_FINGER_BODY,
            _RIGHT_FINGER_COLLIDER: _RIGHT_FINGER_BODY,
        }[path],
        expected_sensor_names=("left", "right", "hand"),
    )

    assert len(contacts) == 2
    assert {contact["body1_path"] for contact in contacts} | {
        contact["body0_path"] for contact in contacts
    } >= {_SOURCE_BODY, _LEFT_FINGER_BODY, _RIGHT_FINGER_BODY}
    assert [contact["normal_impulse_n_s"] for contact in contacts] == pytest.approx(
        [0.001, 0.001]
    )
    assert all(contact["physics_step"] == 12 for contact in contacts)
    assert all(
        contact["normal_convention"] == "body1_to_body0_world"
        for contact in contacts
    )
    assert {
        contact["collider0_path"] for contact in contacts
    } | {
        contact["collider1_path"] for contact in contacts
    } >= {_SOURCE_COLLIDER, _LEFT_FINGER_COLLIDER, _RIGHT_FINGER_COLLIDER}


def test_contact_sensor_frames_body_swap_with_inverted_vectors_deduplicates():
    frames = _sensor_contact_frames(7)
    original = frames["left"]["contacts"][0]
    frames["hand"]["contacts"].append(
        {
            **original,
            "body0": original["body1"],
            "body1": original["body0"],
            "normal": -original["normal"],
            "impulse": -original["impulse"],
        }
    )

    contacts = isaac_fluid.normalize_contact_sensor_frames(
        frames,
        expected_physics_step=7,
        resolve_body_path=lambda path: {
            _SOURCE_COLLIDER: _SOURCE_BODY,
            _LEFT_FINGER_COLLIDER: _LEFT_FINGER_BODY,
            _RIGHT_FINGER_COLLIDER: _RIGHT_FINGER_BODY,
        }[path],
        expected_sensor_names=("left", "right", "hand"),
    )

    assert len(contacts) == 2
    duplicate = next(
        contact
        for contact in contacts
        if _LEFT_FINGER_BODY in (contact["body0_path"], contact["body1_path"])
    )
    assert duplicate["sensor_names"] == ["hand", "left"]


def test_contact_sensor_frames_reject_stale_or_missing_raw_data():
    stale = _sensor_contact_frames(11)
    stale["right"]["physics_step"] = 10.0
    with pytest.raises(ValueError, match="contact_sensor_frame_step_mismatch"):
        isaac_fluid.normalize_contact_sensor_frames(
            stale,
            expected_physics_step=11,
        )

    missing = _sensor_contact_frames(11)
    del missing["left"]["contacts"]
    with pytest.raises(ValueError, match="contact_sensor_raw_contacts_required"):
        isaac_fluid.normalize_contact_sensor_frames(
            missing,
            expected_physics_step=11,
        )


def _dynamic_contact_vessel(
    *,
    timeout_s=1.5,
    loss_grace_steps=2,
    grasp_height_axis_object=(0.0, 0.0, 1.0),
    source_writer_audit=None,
    require_complete_writer_audit=False,
    immediate_contact_reporter=None,
    controlled_contact_classifier=None,
    read_controlled_body_states=None,
    controlled_contact_baseline_collider_pairs=None,
    controlled_certificate_kwargs=None,
):
    state = {
        "physics_step": 0,
        "source": _translation(*_SOURCE_CENTER_WORLD_M),
        "gripper": _translation(0.3, 0.1, 1.0),
        "fingers": (
            _translation(0.3, 0.09, 0.9),
            _translation(0.3, 0.11, 0.9),
        ),
        "contacts": False,
        "frame_transform": None,
    }
    vessel_kwargs = dict(
        source_body_path=_SOURCE_BODY,
        source_collider_path=_SOURCE_COLLIDER,
        left_finger_body_path=_LEFT_FINGER_BODY,
        right_finger_body_path=_RIGHT_FINGER_BODY,
        read_source_world_matrix=lambda: state["source"].copy(),
        read_source_center_world=lambda: state["source"][3, :3].copy(),
        read_gripper_world_matrix=lambda: state["gripper"].copy(),
        read_finger_world_matrices=lambda: tuple(
            matrix.copy() for matrix in state["fingers"]
        ),
        read_contact_sensor_frames=lambda: (
            state["frame_transform"](
                _sensor_contact_frames(
                    state["physics_step"], contacts=state["contacts"]
                )
            )
            if state["frame_transform"] is not None
            else _sensor_contact_frames(
                state["physics_step"], contacts=state["contacts"]
            )
        ),
        read_physics_step=lambda: state["physics_step"],
        read_finger_joint_velocities=lambda: np.zeros(2, dtype=np.float64),
        physics_dt=1 / 120,
        minimum_normal_impulse_n_s=0.001,
        minimum_side_projection_m=0.005,
        required_consecutive_steps=5,
        maximum_finger_speed_m_s=0.002,
        grasp_height_axis_object=grasp_height_axis_object,
        grasp_height_band_m=(-0.02, 0.02),
        maximum_bilateral_height_difference_m=0.005,
        minimum_inward_normal_cosine=0.8,
        minimum_opposing_normal_cosine=0.8,
        contact_timeout_s=timeout_s,
        contact_loss_grace_steps=loss_grace_steps,
        preclose_source_translation_limit_m=0.002,
        preclose_source_tilt_limit_degrees=1.0,
        resolve_body_path=lambda path: {
            _SOURCE_COLLIDER: _SOURCE_BODY,
            _LEFT_FINGER_COLLIDER: _LEFT_FINGER_BODY,
            _RIGHT_FINGER_COLLIDER: _RIGHT_FINGER_BODY,
        }.get(path, path),
    )
    if source_writer_audit is not None or require_complete_writer_audit:
        vessel_kwargs.update(
            source_writer_audit=source_writer_audit,
            require_complete_writer_audit=require_complete_writer_audit,
        )
    if immediate_contact_reporter is not None or controlled_contact_classifier is not None:
        vessel_kwargs.update(
            immediate_contact_reporter=immediate_contact_reporter,
            controlled_contact_classifier=controlled_contact_classifier,
            read_controlled_body_states=(
                read_controlled_body_states or (lambda: {})
            ),
        )
    if controlled_contact_baseline_collider_pairs is not None:
        vessel_kwargs["controlled_contact_baseline_collider_pairs"] = (
            controlled_contact_baseline_collider_pairs
        )
    if controlled_certificate_kwargs:
        vessel_kwargs.update(controlled_certificate_kwargs)
    vessel = isaac_fluid.ContactFrictionDynamicVessel(**vessel_kwargs)
    return vessel, state


def _contact_request_controller():
    return SimpleNamespace(online_fluid_grasp_contact_requested=lambda: True)


def _mutable_contact_request_controller(request):
    return SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: request["close"],
        online_fluid_grasp_lift_requested=lambda: request.get("lift", False),
    )


def _reset_and_pre_roll_contact_frames(vessel, state, *, steps=20):
    vessel.reset()
    state["contacts"] = False
    state["frame_transform"] = None
    for step in range(steps):
        state["physics_step"] = step
        vessel.update_after_substep()


def test_dynamic_contact_vessel_requires_twenty_current_pre_roll_frames():
    vessel, state = _dynamic_contact_vessel()
    vessel.reset()

    for step in range(19):
        state["physics_step"] = step
        vessel.update_after_substep()

    not_ready = vessel.record()
    assert not_ready["contact_sensor_ready"] is False
    readiness = not_ready["contact_sensor_readiness"]
    assert readiness["consecutive_current_steps"] == 19
    assert readiness["required_consecutive_current_steps"] == 20
    assert readiness["ready"] is False
    assert vessel.maybe_attach(_contact_request_controller(), {}) is False
    assert vessel.record()["failure_reason"] == "contact_sensor_pre_roll_not_ready"

    vessel.reset()
    for step in range(20):
        state["physics_step"] = step
        vessel.update_after_substep()

    ready = vessel.record()
    assert ready["contact_sensor_ready"] is True
    assert ready["contact_sensor_readiness"]["consecutive_current_steps"] == 20
    assert ready["contact_sensor_readiness"]["last_validated_physics_step"] == 19
    assert vessel.state_record()["contact_sensor_ready"] is True
    assert vessel.maybe_attach(_contact_request_controller(), {}) is True


def test_dynamic_contact_vessel_returns_immediate_precontact_decision_and_delegates_latch():
    class Reporter:
        def __init__(self):
            self.samples = []

        def reset(self):
            self.samples.clear()

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            self.samples.append(
                (physics_index, allow_provisional_persist_bootstrap)
            )
            occurrences = []
            if physics_index >= 20:
                occurrences = [
                    {
                        "fragments": [
                            {
                                "header": {
                                    "collider0": finger,
                                    "collider1": _SOURCE_COLLIDER,
                                }
                            }
                        ]
                    }
                    for finger in (
                        _LEFT_FINGER_COLLIDER,
                        _RIGHT_FINGER_COLLIDER,
                    )
                ]
            return {
                "authority": "physx_immediate_full_contact_report_v1",
                "physics_index": physics_index,
                "occurrences": occurrences,
            }

    reporter = Reporter()
    classifications = []

    def classify(*, report, phase, **_body_states):
        classifications.append((report["physics_index"], phase))
        return {
            "terminal_kind": None,
            "precontact_latch": {
                "physics_step": report["physics_index"],
                "sides": ["left"],
                "records": [
                    {"class": "INTENDED_PRECONTACT", "side": "left"}
                ],
            },
            "evidence_sha256": "d" * 64,
        }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=reporter,
        controlled_contact_classifier=classify,
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    latch_calls = []
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: {"phase": "INSERT"},
        latch_intended_precontact=lambda evidence: (
            latch_calls.append(evidence) or True
        ),
    )
    assert vessel.maybe_attach(controller, {}) is True
    state["physics_step"] = 20
    state["contacts"] = True

    decision = vessel.update_after_substep()

    assert decision["kind"] == "INTENDED_PRECONTACT"
    assert decision["evidence"]["authority"] == (
        "controlled_contact_complete_manifold_v1"
    )
    assert decision["evidence"]["physics_step"] == 20
    assert classifications[-1] == (20, "INSERT")
    assert vessel.record()["failure_reason"] is None
    assert vessel.latch_intended_precontact(decision["evidence"]) is True
    assert latch_calls == [decision["evidence"]]
    assert vessel.state_record()["controlled_phase_elapsed_steps"][
        "PRECONTACT_SETTLE"
    ] == 1


def test_dynamic_contact_vessel_classifies_immediate_reports_during_pre_roll():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [{"pair": "finger-source"}],
                "current_pairs": [],
            }

    phases = []

    def classify(*, phase, **_kwargs):
        phases.append(phase)
        return {
            "terminal_kind": "PHYSICAL_CONTACT_FAILURE",
            "precontact_latch": None,
            "evidence_sha256": "d" * 64,
        }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=classify,
    )
    vessel.reset()
    state["physics_step"] = 0
    vessel.update_before_substep()

    decision = vessel.update_after_substep()

    assert phases == ["PRE_ROLL"]
    assert decision["kind"] == "TERMINAL"
    assert decision["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"


def test_dynamic_contact_vessel_rejects_sensor_contact_missing_from_immediate_report():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "evidence_sha256": "d" * 64,
        },
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: {"phase": "INSERT"},
    )
    assert vessel.maybe_attach(controller, {}) is True
    state["physics_step"] = 20
    state["contacts"] = True
    vessel.update_before_substep()

    decision = vessel.update_after_substep()

    assert decision["kind"] == "TERMINAL"
    assert decision["terminal_kind"] == "PROTOCOL_FAILURE"
    assert decision["failure_reason"] == "contact_sensor_immediate_disagreement"
    assert vessel.record()["sensor_immediate_agreement_valid"] is False


def test_controlled_dynamic_vessel_enforces_source_motion_during_pre_roll():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "evidence_sha256": "d" * 64,
        },
    )
    vessel.reset()
    state["source"][3, 0] += 0.00201
    state["physics_step"] = 0
    vessel.update_before_substep()

    decision = vessel.update_after_substep()

    assert decision["kind"] == "TERMINAL"
    assert decision["terminal_kind"] == "PHYSICAL_MOTION_FAILURE"
    assert decision["failure_reason"] == "source_translation_exceeded_pre_roll"
    assert vessel.record()["pre_roll_max_source_translation_m"] == pytest.approx(
        0.00201
    )


def test_controlled_dynamic_vessel_certifies_sixty_consecutive_settle_steps():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "records": [],
            "class_counts": {},
            "evidence_sha256": "d" * 64,
        },
        controlled_certificate_kwargs={"controlled_settle_deadline_steps": 60},
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: {"phase": "SETTLE"},
    )
    assert vessel.maybe_attach(controller, {}) is True
    vessel.set_controlled_effective_phase("SETTLE")

    for offset in range(59):
        state["physics_step"] = 20 + offset
        vessel.update_before_substep()
        assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    certificate = vessel.state_record()["controlled_phase_certificates"]["SETTLE"]
    assert certificate["consecutive_steps"] == 59
    assert certificate["ready"] is False

    state["physics_step"] = 79
    vessel.update_before_substep()
    assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    certificate = vessel.state_record()["controlled_phase_certificates"]["SETTLE"]
    assert certificate["consecutive_steps"] == 60
    assert certificate["ready"] is True


def test_controlled_dynamic_vessel_times_out_uncertified_settle_on_deadline():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "records": [{"class": "INTENDED_PRECONTACT", "current": False}],
            "class_counts": {"INTENDED_PRECONTACT": 1},
            "evidence_sha256": "d" * 64,
        },
        controlled_certificate_kwargs={
            "controlled_settle_deadline_steps": 3,
        },
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: {"phase": "SETTLE"},
    )
    assert vessel.maybe_attach(controller, {}) is True
    vessel.set_controlled_effective_phase("SETTLE")

    for physics_step in (20, 21):
        state["physics_step"] = physics_step
        vessel.update_before_substep()
        assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    state["physics_step"] = 22
    vessel.update_before_substep()
    decision = vessel.update_after_substep()

    assert decision["kind"] == "TERMINAL"
    assert decision["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert decision["failure_reason"] == "SETTLE_timeout"


@pytest.mark.parametrize(
    ("phase", "deadline_field"),
    [
        ("PREGRASP", "controlled_pregrasp_deadline_steps"),
        ("ALIGN", "controlled_align_deadline_steps"),
        ("INSERT", "controlled_insert_deadline_steps"),
    ],
)
def test_controlled_dynamic_vessel_times_out_movement_phase_on_deadline(
    phase,
    deadline_field,
):
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    context = {"phase": phase, "controller_phase": phase}
    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "records": [],
            "evidence_sha256": "d" * 64,
        },
        controlled_certificate_kwargs={deadline_field: 3},
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: dict(context),
    )
    assert vessel.maybe_attach(controller, {}) is True
    vessel.set_controlled_effective_phase(phase)

    for physics_step in (20, 21):
        state["physics_step"] = physics_step
        vessel.update_before_substep()
        assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    state["physics_step"] = 22
    vessel.update_before_substep()
    decision = vessel.update_after_substep()

    assert decision["kind"] == "TERMINAL"
    assert decision["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert decision["failure_reason"] == f"{phase}_timeout"
    assert decision["phase_elapsed_steps"] == 3


def test_controlled_movement_deadline_allows_same_action_phase_exit():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    context = {"phase": "ALIGN", "controller_phase": "ALIGN"}
    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "records": [],
            "evidence_sha256": "d" * 64,
        },
        controlled_certificate_kwargs={"controlled_align_deadline_steps": 3},
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: dict(context),
    )
    assert vessel.maybe_attach(controller, {}) is True
    vessel.set_controlled_effective_phase("ALIGN")

    for physics_step in (20, 21):
        state["physics_step"] = physics_step
        vessel.update_before_substep()
        assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    context["controller_phase"] = "INSERT"
    state["physics_step"] = 22
    vessel.update_before_substep()

    boundary = vessel.update_after_substep()
    assert boundary["kind"] == "CONTINUE"
    assert boundary["phase_deadline_exit_grace"] == {
        "phase": "ALIGN",
        "controller_phase": "INSERT",
        "phase_elapsed_steps": 3,
        "phase_deadline_steps": 3,
    }
    stale_phase = vessel.validate_controlled_action_phase("ALIGN")
    next_phase = vessel.validate_controlled_action_phase("INSERT")

    assert stale_phase["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert stale_phase["failure_reason"] == "ALIGN_timeout"
    assert next_phase == {"kind": "CONTINUE"}

    state["physics_step"] = 23
    vessel.update_before_substep()
    overrun = vessel.update_after_substep()
    assert overrun["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert overrun["phase_elapsed_steps"] == 4


def test_controlled_action_phase_rejects_skip_and_reentry():
    vessel, _state = _dynamic_contact_vessel()
    vessel.set_controlled_effective_phase("PREGRASP")

    skipped = vessel.validate_controlled_action_phase("INSERT")
    assert skipped["terminal_kind"] == "PROTOCOL_FAILURE"
    assert skipped["failure_reason"] == "PREGRASP_to_INSERT_illegal"
    assert vessel.validate_controlled_action_phase("ALIGN") == {
        "kind": "CONTINUE"
    }

    vessel.set_controlled_effective_phase("ALIGN")
    reentry = vessel.validate_controlled_action_phase("PREGRASP")
    assert reentry["terminal_kind"] == "PROTOCOL_FAILURE"
    assert reentry["failure_reason"] == "ALIGN_to_PREGRASP_illegal"


def test_controlled_insert_latch_wins_on_movement_deadline_step():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    def classify(*, report, **_kwargs):
        latch = None
        if report["physics_index"] == 22:
            latch = {
                "physics_step": 22,
                "sides": ["left"],
                "records": [{"class": "INTENDED_PRECONTACT", "side": "left"}],
            }
        return {
            "terminal_kind": None,
            "precontact_latch": latch,
            "records": [],
            "evidence_sha256": "d" * 64,
        }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=classify,
        controlled_certificate_kwargs={"controlled_insert_deadline_steps": 3},
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: {
            "phase": "INSERT",
            "controller_phase": "INSERT",
        },
    )
    assert vessel.maybe_attach(controller, {}) is True
    vessel.set_controlled_effective_phase("INSERT")

    for physics_step in (20, 21):
        state["physics_step"] = physics_step
        vessel.update_before_substep()
        assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    state["physics_step"] = 22
    vessel.update_before_substep()
    decision = vessel.update_after_substep()

    assert decision["kind"] == "INTENDED_PRECONTACT"
    assert decision["evidence"]["physics_step"] == 22


def test_controlled_movement_phase_reentry_does_not_refresh_deadline():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    context = {"phase": "PREGRASP", "controller_phase": "PREGRASP"}
    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "records": [],
            "evidence_sha256": "d" * 64,
        },
        controlled_certificate_kwargs={"controlled_pregrasp_deadline_steps": 3},
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: False,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: dict(context),
    )
    assert vessel.maybe_attach(controller, {}) is True
    vessel.set_controlled_effective_phase("PREGRASP")

    for physics_step in (20, 21):
        state["physics_step"] = physics_step
        vessel.update_before_substep()
        assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    context.update(phase="ALIGN", controller_phase="ALIGN")
    vessel.set_controlled_effective_phase("ALIGN")
    state["physics_step"] = 22
    vessel.update_before_substep()
    assert vessel.update_after_substep() == {"kind": "CONTINUE"}

    context.update(phase="PREGRASP", controller_phase="PREGRASP")
    vessel.set_controlled_effective_phase("PREGRASP")
    state["physics_step"] = 23
    vessel.update_before_substep()
    decision = vessel.update_after_substep()

    assert decision["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert decision["phase_elapsed_steps"] == 3


def test_dynamic_contact_vessel_requires_exact_immediate_baseline_before_monitoring():
    class Reporter:
        def __init__(self, current_pairs):
            self.current_pairs = current_pairs

        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": self.current_pairs,
            }

    expected_pair = (_SOURCE_COLLIDER, "/World/table/surface/mesh")

    def pair_record(*paths):
        return [
            {"collider_path": path, "proto_index": 0xFFFFFFFF}
            for path in paths
        ]

    classifier = lambda **_kwargs: {
        "terminal_kind": None,
        "precontact_latch": None,
        "evidence_sha256": "d" * 64,
    }
    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter([pair_record(*expected_pair)]),
        controlled_contact_classifier=classifier,
        controlled_contact_baseline_collider_pairs=(expected_pair,),
    )
    _reset_and_pre_roll_contact_frames(vessel, state)

    assert vessel.maybe_attach(_contact_request_controller(), {}) is True
    assert vessel.record()["controlled_contact_baseline_validated"] is True

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(
            [
                pair_record(*expected_pair),
                pair_record(_SOURCE_COLLIDER, "/World/beaker1/mesh"),
            ]
        ),
        controlled_contact_classifier=classifier,
        controlled_contact_baseline_collider_pairs=(expected_pair,),
    )
    _reset_and_pre_roll_contact_frames(vessel, state)

    assert vessel.maybe_attach(_contact_request_controller(), {}) is False
    record = vessel.record()
    assert record["controlled_contact_baseline_validated"] is False
    assert record["failure_reason"] == "contact_report_baseline_pair_mismatch"


def test_dynamic_contact_vessel_exposes_baseline_failure_before_controller_step():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    vessel, state = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {},
        controlled_contact_baseline_collider_pairs=(
            (_SOURCE_COLLIDER, "/World/table/surface/mesh"),
        ),
    )
    _reset_and_pre_roll_contact_frames(vessel, state)

    decision = vessel.validate_controlled_preaction_authority()

    assert decision == {
        "kind": "TERMINAL",
        "terminal_kind": "PROTOCOL_FAILURE",
        "failure_reason": "contact_report_baseline_pair_mismatch",
    }


def test_dynamic_contact_vessel_resets_episode_scoped_classifier_state():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    class Classifier:
        def __init__(self):
            self.reset_calls = 0

        def reset(self):
            self.reset_calls += 1

        def __call__(self, **_kwargs):
            return {
                "terminal_kind": None,
                "precontact_latch": None,
                "evidence_sha256": "d" * 64,
            }

    classifier = Classifier()
    vessel, _ = _dynamic_contact_vessel(
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=classifier,
    )

    assert classifier.reset_calls == 1
    vessel.reset()
    assert classifier.reset_calls == 2


def test_dynamic_contact_vessel_readiness_rejects_stale_and_missing_hand_frames():
    vessel, state = _dynamic_contact_vessel()
    vessel.reset()
    for step in range(19):
        state["physics_step"] = step
        vessel.update_after_substep()

    def stale_hand(frames):
        frames["hand"]["physics_step"] -= 1
        return frames

    state["frame_transform"] = stale_hand
    state["physics_step"] = 19
    vessel.update_after_substep()
    stale = vessel.record()["contact_sensor_readiness"]
    assert stale["ready"] is False
    assert stale["consecutive_current_steps"] == 0
    assert "contact_sensor_frame_step_mismatch" in stale["last_failure_reason"]

    state["frame_transform"] = None
    for step in range(20, 40):
        state["physics_step"] = step
        vessel.update_after_substep()
    assert vessel.record()["contact_sensor_ready"] is True

    vessel.reset()
    state["physics_step"] = 0
    state["frame_transform"] = lambda frames: (
        frames.pop("hand"), frames
    )[1]
    vessel.update_after_substep()
    missing = vessel.record()["contact_sensor_readiness"]
    assert missing["ready"] is False
    assert missing["consecutive_current_steps"] == 0
    assert "contact_sensor_frame_set_mismatch" in missing["last_failure_reason"]


def test_dynamic_contact_vessel_hand_only_contacts_cannot_qualify_finger_roles():
    vessel, state = _dynamic_contact_vessel()
    _reset_and_pre_roll_contact_frames(vessel, state)
    assert vessel.maybe_attach(_contact_request_controller(), {}) is True

    def hand_only(frames):
        bilateral = _sensor_contact_frames(
            state["physics_step"], contacts=True
        )
        frames["hand"]["contacts"] = [
            *bilateral["left"]["contacts"],
            *bilateral["right"]["contacts"],
        ]
        return frames

    state["frame_transform"] = hand_only
    for step in range(20, 25):
        state["physics_step"] = step
        vessel.update_after_substep()

    record = vessel.record()
    assert record["qualified"] is False
    assert record["probe_qualified_now"] is False
    assert record["gate"]["bilateral"] is False
    assert record["contact_sensor_diagnostics"]["hand_raw_contact_count"] == 2
    assert record["contact_sensor_diagnostics"]["qualifying_contact_count"] == 0


def test_dynamic_contact_vessel_latches_single_preclose_motion_substep():
    vessel, state = _dynamic_contact_vessel()
    request = {"close": False}
    _reset_and_pre_roll_contact_frames(vessel, state)

    assert vessel.maybe_attach(
        _mutable_contact_request_controller(request), {}
    ) is True
    state["contacts"] = False
    state["source"][3, 0] += 0.00201
    state["physics_step"] = 1
    vessel.update_after_substep()
    state["source"][3, 0] -= 0.00201
    state["physics_step"] = 2
    vessel.update_after_substep()

    record = vessel.record()
    assert record["failure_reason"] == (
        "source_translation_exceeded_before_contact"
    )
    assert record["preclose_max_source_translation_m"] == pytest.approx(
        0.00201
    )
    assert record["first_failure_physics_step"] == 1


def test_dynamic_contact_vessel_latches_source_motion_during_close_from_same_origin():
    vessel, state = _dynamic_contact_vessel()
    request = {"close": False, "lift": False}
    _reset_and_pre_roll_contact_frames(vessel, state)
    assert vessel.maybe_attach(
        _mutable_contact_request_controller(request), {}
    ) is True

    state["physics_step"] = 20
    vessel.update_after_substep()
    request["close"] = True
    state["source"][3, 0] += 0.00201
    state["physics_step"] = 21
    vessel.update_after_substep()

    record = vessel.record()
    assert record["failure_reason"] == "source_translation_exceeded_during_close"
    assert record["monitoring_max_source_translation_m"] == pytest.approx(0.00201)
    assert record["during_close_max_source_translation_m"] == pytest.approx(
        0.00201
    )
    assert record["preclose_max_source_translation_m"] == pytest.approx(0.0)


def test_dynamic_contact_vessel_uses_configured_object_axis_for_preclose_tilt():
    vessel, state = _dynamic_contact_vessel(
        grasp_height_axis_object=(1.0, 0.0, 0.0)
    )
    request = {"close": False, "lift": False}
    _reset_and_pre_roll_contact_frames(vessel, state)
    vessel.maybe_attach(_mutable_contact_request_controller(request), {})
    state["source"][:] = _rotation_z(1.01)
    state["source"][3, :3] = _SOURCE_CENTER_WORLD_M
    state["physics_step"] = 1

    vessel.update_after_substep()

    assert vessel.record()["failure_reason"] == (
        "source_tilt_exceeded_before_contact"
    )


def test_dynamic_contact_vessel_preclose_steps_do_not_seed_gate_or_timeout():
    vessel, state = _dynamic_contact_vessel(timeout_s=5 / 120)
    request = {"close": False}
    _reset_and_pre_roll_contact_frames(vessel, state)
    vessel.maybe_attach(_mutable_contact_request_controller(request), {})
    state["contacts"] = False

    for step in range(1, 5):
        state["physics_step"] = step
        vessel.update_after_substep()

    preclose = vessel.record()
    assert preclose["failure_reason"] is None
    assert preclose["gate"]["consecutive_steps"] == 0
    assert preclose["contact_acquisition_steps"] == 0

    request["close"] = True
    state["contacts"] = True
    for step in range(5, 10):
        state["physics_step"] = step
        vessel.update_after_substep()

    assert vessel.record()["qualified"] is True


def test_dynamic_contact_vessel_latches_contact_before_close():
    vessel, state = _dynamic_contact_vessel()
    request = {"close": False}
    _reset_and_pre_roll_contact_frames(vessel, state)
    vessel.maybe_attach(_mutable_contact_request_controller(request), {})
    state["contacts"] = True
    state["physics_step"] = 1

    vessel.update_after_substep()

    record = vessel.record()
    assert record["failure_reason"] == "unexpected_contact_before_close"
    assert record["first_unexpected_contact"]["physics_step"] == 1


def test_stale_acquired_contact_counts_toward_loss():
    vessel, state = _dynamic_contact_vessel(loss_grace_steps=1)
    _reset_and_pre_roll_contact_frames(vessel, state)
    vessel.maybe_attach(_contact_request_controller(), {})
    state["contacts"] = True
    for step in range(1, 6):
        state["physics_step"] = step
        vessel.update_after_substep()
    assert vessel.record()["qualified"] is True

    vessel.update_after_substep()
    assert vessel.record()["loss_steps"] == 1
    vessel.update_after_substep()

    assert vessel.record()["failure_reason"] == "grasp_lost"


def test_dynamic_contact_vessel_qualifies_only_from_five_post_step_contacts():
    vessel, state = _dynamic_contact_vessel()
    _reset_and_pre_roll_contact_frames(vessel, state)

    assert vessel.maybe_attach(_contact_request_controller(), {}) is True
    state["contacts"] = True
    for step in range(1, 6):
        state["physics_step"] = step
        vessel.update_before_substep()
        vessel.update_after_substep()

    record = vessel.record()
    assert record["mode"] == "contact_friction_dynamic_v1"
    assert record["contact_grasp_claimed"] is True
    assert record["mechanical_attachment_used"] is False
    assert record["source_dynamic"] is True
    assert record["source_pose_write_count_after_play"] == 0
    assert record["kinematic_target_update_count"] == 0
    assert record["qualified"] is True
    assert record["probe_qualified_now"] is True
    assert record["expert_grasp_valid"] is True
    assert record["failure_reason"] is None
    assert len(record["observed_matrix_sha256"]) == 64


def test_dynamic_contact_vessel_probe_qualification_requires_current_valid_terminal_step():
    vessel, state = _dynamic_contact_vessel(loss_grace_steps=2)
    _reset_and_pre_roll_contact_frames(vessel, state)
    assert vessel.maybe_attach(_contact_request_controller(), {}) is True
    state["contacts"] = True
    for step in range(20, 25):
        state["physics_step"] = step
        vessel.update_after_substep()

    current = vessel.record()
    assert current["qualified"] is True
    assert current["probe_qualified_now"] is True
    assert vessel.state_record()["probe_qualified_now"] is True

    state["physics_step"] = 25
    assert vessel.record()["qualified"] is True
    assert vessel.record()["probe_qualified_now"] is False

    state["contacts"] = False
    vessel.update_after_substep()
    within_grace = vessel.record()
    assert within_grace["failure_reason"] is None
    assert within_grace["qualified"] is True
    assert within_grace["loss_steps"] == 1
    assert within_grace["gate"]["valid_this_step"] is False
    assert within_grace["probe_qualified_now"] is False


def test_dynamic_contact_vessel_rejects_acquisition_that_starts_during_lift():
    vessel, state = _dynamic_contact_vessel()
    request = {"close": True, "lift": False}
    _reset_and_pre_roll_contact_frames(vessel, state)
    vessel.maybe_attach(_mutable_contact_request_controller(request), {})
    state["contacts"] = True
    for step in range(1, 5):
        state["physics_step"] = step
        vessel.update_after_substep()
    request["lift"] = True
    state["physics_step"] = 5

    vessel.update_after_substep()

    record = vessel.record()
    assert record["qualified"] is False
    assert record["failure_reason"] == "lift_started_before_contact_acquisition"


def test_dynamic_contact_builder_parameters_are_strict_and_payload_derived():
    fluid = SimpleNamespace(
        physics_dt=1 / 120,
        source_external_shell_path=_SOURCE_COLLIDER,
        grasp_height_axis_object=[1.0, 0.0, 0.0],
        grasp_height_band_m=[-0.02, 0.02],
        grasp_contact_max_bilateral_height_difference_m=0.005,
        grasp_contact_min_inward_normal_cosine=0.8,
        grasp_contact_min_opposing_normal_cosine=0.8,
        grasp_effective_payload_mass_kg=0.02,
        grasp_effective_friction=1.0,
        grasp_gravity_m_s2=9.81,
        grasp_payload_mass_authority="authored_dry_vessel_only_v1",
    )

    parameters = isaac_fluid.dynamic_contact_grasp_parameters(fluid)

    assert parameters["source_collider_path"] == _SOURCE_COLLIDER
    assert parameters["grasp_height_axis_object"] == (1.0, 0.0, 0.0)
    assert parameters["grasp_height_band_m"] == (-0.02, 0.02)
    assert parameters["maximum_bilateral_height_difference_m"] == 0.005
    assert parameters["minimum_inward_normal_cosine"] == 0.8
    assert parameters["minimum_opposing_normal_cosine"] == 0.8
    assert parameters["minimum_normal_impulse_n_s"] == pytest.approx(
        2.0 * 0.02 * 9.81 * (1 / 120) / (2 * 1.0)
    )
    derivation = parameters["minimum_normal_impulse_derivation"]
    assert derivation["payload_mass_authority"] == (
        "authored_dry_vessel_only_v1"
    )
    assert derivation["effective_payload_mass_kg"] == 0.02


def test_controlled_contact_interlock_requires_exact_runtime_profile():
    controlled = SimpleNamespace(
        source_ownership="contact_friction_dynamic_v1",
        execution_mode="contact_acquisition_probe_v1",
        expert_control_profile="contact_pick_v1",
    )
    assert isaac_fluid.controlled_contact_interlock_requested(controlled) is True

    for field, replacement in (
        ("source_ownership", "gripper_attached_kinematic_vessel"),
        ("execution_mode", "production_pour_v1"),
        ("expert_control_profile", "native_expert_v1"),
    ):
        values = vars(controlled).copy()
        values[field] = replacement
        assert (
            isaac_fluid.controlled_contact_interlock_requested(
                SimpleNamespace(**values)
            )
            is False
        )


def test_rigid_body_com_state_uses_world_space_com_and_twist():
    body = SimpleNamespace(
        get_world_pose=lambda: (
            np.asarray([2.0, 3.0, 4.0]),
            np.asarray([1.0, 0.0, 0.0, 0.0]),
        ),
        get_com=lambda: (
            np.asarray([0.1, 0.2, 0.3]),
            np.asarray([1.0, 0.0, 0.0, 0.0]),
        ),
        get_linear_velocity=lambda: np.asarray([0.4, 0.5, 0.6]),
        get_angular_velocity=lambda: np.asarray([0.7, 0.8, 0.9]),
    )

    state = isaac_fluid.read_rigid_body_com_state(
        body, body_path="/World/body"
    )

    assert state == {
        "com_position_m": pytest.approx([2.1, 3.2, 4.3]),
        "orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
        "linear_velocity_m_s": [0.4, 0.5, 0.6],
        "angular_velocity_rad_s": [0.7, 0.8, 0.9],
    }


def test_contact_grasp_scene_preauthorizes_contact_reports_on_fingers_and_hand(
    monkeypatch,
):
    pxr = pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

    class FakeContactReportAPI:
        applied_paths = set()
        apply_calls = []

        def __init__(self, prim):
            self.prim = prim

        def __bool__(self):
            return str(self.prim.GetPath()) in self.applied_paths

        @classmethod
        def Apply(cls, prim):
            path = str(prim.GetPath())
            cls.applied_paths.add(path)
            cls.apply_calls.append(path)
            return cls(prim)

    monkeypatch.setattr(
        pxr,
        "PhysxSchema",
        SimpleNamespace(PhysxContactReportAPI=FakeContactReportAPI),
        raising=False,
    )
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/Franka")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    UsdShade.Material.Define(stage, "/World/Looks/Contact")
    body_paths = (
        _LEFT_FINGER_BODY,
        _RIGHT_FINGER_BODY,
        "/World/Franka/panda_hand",
    )
    for path in body_paths:
        body = UsdGeom.Xform.Define(stage, path).GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(body)
        collider = UsdGeom.Cube.Define(stage, f"{path}/collision").GetPrim()
        UsdPhysics.CollisionAPI.Apply(collider).CreateCollisionEnabledAttr(True)
    config = SimpleNamespace(
        contact_material_path="/World/Looks/Contact",
        finger_body_paths=body_paths[:2],
    )

    record = isaac_fluid.configure_contact_grasp_scene(stage, config)
    second = isaac_fluid.configure_contact_grasp_scene(stage, config)

    assert record["contact_report_body_paths"] == list(body_paths)
    assert record["contact_report_api_preauthorized"] is True
    assert second["contact_report_body_paths"] == list(body_paths)
    assert FakeContactReportAPI.applied_paths == set(body_paths)
    assert FakeContactReportAPI.apply_calls == list(body_paths)

    stage.RemovePrim("/World/Franka/panda_hand")
    with pytest.raises(
        RuntimeError,
        match="contact_grasp_contact_report_body_missing:.*/panda_hand",
    ):
        isaac_fluid.configure_contact_grasp_scene(stage, config)


def test_controlled_contact_scene_reports_every_robot_body_and_source_at_zero(
    monkeypatch,
):
    pxr = pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

    class FakeAttribute:
        def __init__(self, path):
            self.path = path

        def Set(self, value):
            FakeContactReportAPI.thresholds[self.path] = value
            return True

        def Get(self):
            return FakeContactReportAPI.thresholds.get(self.path)

    class FakeRelationship:
        def __init__(self, path):
            self.path = path

        def GetTargets(self):
            return list(FakeContactReportAPI.report_pairs.get(self.path, ()))

        def ClearTargets(self, _remove_spec):
            FakeContactReportAPI.report_pairs[self.path] = []
            return True

    class FakeContactReportAPI:
        applied_paths = set()
        thresholds = {}
        report_pairs = {}

        def __init__(self, prim):
            self.prim = prim
            self.path = str(prim.GetPath())

        def __bool__(self):
            return self.path in self.applied_paths

        @classmethod
        def Apply(cls, prim):
            path = str(prim.GetPath())
            cls.applied_paths.add(path)
            return cls(prim)

        def CreateThresholdAttr(self):
            return FakeAttribute(self.path)

        def GetThresholdAttr(self):
            return FakeAttribute(self.path)

        def GetReportPairsRel(self):
            return FakeRelationship(self.path)

    monkeypatch.setattr(
        pxr,
        "PhysxSchema",
        SimpleNamespace(PhysxContactReportAPI=FakeContactReportAPI),
        raising=False,
    )
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/Franka")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    UsdShade.Material.Define(stage, "/World/Looks/Contact")
    robot_body_paths = (
        "/World/Franka/panda_link0",
        _LEFT_FINGER_BODY,
        _RIGHT_FINGER_BODY,
        "/World/Franka/panda_hand",
    )
    for path in robot_body_paths:
        body = UsdGeom.Xform.Define(stage, path).GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(body)
    for path in (_LEFT_FINGER_BODY, _RIGHT_FINGER_BODY):
        collider = UsdGeom.Cube.Define(stage, f"{path}/collision").GetPrim()
        UsdPhysics.CollisionAPI.Apply(collider).CreateCollisionEnabledAttr(True)
    source = UsdGeom.Xform.Define(stage, "/World/beaker2").GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(source)
    config = SimpleNamespace(
        contact_material_path="/World/Looks/Contact",
        finger_body_paths=(_LEFT_FINGER_BODY, _RIGHT_FINGER_BODY),
        execution_mode="contact_acquisition_probe_v1",
        source_actor_path="/World/beaker2",
    )

    record = isaac_fluid.configure_contact_grasp_scene(stage, config)

    expected = sorted((*robot_body_paths, "/World/beaker2"))
    assert record["contact_report_body_paths"] == expected
    assert record["contact_report_threshold_n_s"] == 0.0
    assert record["contact_report_pairs_empty"] is True
    assert FakeContactReportAPI.applied_paths == set(expected)
    assert FakeContactReportAPI.thresholds == {
        path: 0.0 for path in expected
    }
    assert all(not targets for targets in FakeContactReportAPI.report_pairs.values())


def test_dynamic_contact_vessel_times_out_and_latches_contact_loss():
    vessel, state = _dynamic_contact_vessel(timeout_s=2 / 120)
    _reset_and_pre_roll_contact_frames(vessel, state)
    vessel.maybe_attach(_contact_request_controller(), {})
    state["contacts"] = False
    for step in range(1, 3):
        state["physics_step"] = step
        vessel.update_after_substep()
    assert vessel.record()["failure_reason"] == "contact_timeout"

    vessel, state = _dynamic_contact_vessel(loss_grace_steps=2)
    _reset_and_pre_roll_contact_frames(vessel, state)
    vessel.maybe_attach(_contact_request_controller(), {})
    state["contacts"] = True
    for step in range(1, 6):
        state["physics_step"] = step
        vessel.update_after_substep()
    state["contacts"] = False
    for step in range(6, 8):
        state["physics_step"] = step
        vessel.update_after_substep()
        assert vessel.record()["failure_reason"] is None
    state["physics_step"] = 8
    vessel.update_after_substep()
    assert vessel.record()["failure_reason"] == "grasp_lost"
    assert vessel.record()["expert_grasp_valid"] is False


def test_controlled_dynamic_contact_timeout_is_terminal_on_deadline_step():
    class Reporter:
        def reset(self):
            return None

        def sample(self, *, physics_index, allow_provisional_persist_bootstrap=False):
            del allow_provisional_persist_bootstrap
            return {
                "physics_index": physics_index,
                "occurrences": [],
                "current_pairs": [],
            }

    vessel, state = _dynamic_contact_vessel(
        timeout_s=2 / 120,
        immediate_contact_reporter=Reporter(),
        controlled_contact_classifier=lambda **_kwargs: {
            "terminal_kind": None,
            "precontact_latch": None,
            "evidence_sha256": "d" * 64,
        },
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    controller = SimpleNamespace(
        online_fluid_grasp_contact_requested=lambda: True,
        online_fluid_grasp_lift_requested=lambda: False,
        controlled_contact_action_context=lambda: {"phase": "CLOSE"},
    )
    assert vessel.maybe_attach(controller, {}) is True

    state["physics_step"] = 20
    vessel.update_before_substep()
    assert vessel.update_after_substep() == {"kind": "CONTINUE"}
    state["physics_step"] = 21
    vessel.update_before_substep()
    decision = vessel.update_after_substep()

    assert decision["kind"] == "TERMINAL"
    assert decision["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert decision["failure_reason"] == "contact_timeout"


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


def _installed_source_writer_audit():
    calls = []

    class PhysicsView:
        def set_kinematic_targets(self, *args, **kwargs):
            calls.append(("physics", args, kwargs))

    class SourceBody:
        def __init__(self):
            self._prim_view = SimpleNamespace(_physics_view=PhysicsView())

        def set_world_pose(self, *args, **kwargs):
            calls.append(("world", args, kwargs))

        def set_local_pose(self, *args, **kwargs):
            calls.append(("local", args, kwargs))

        def set_linear_velocity(self, *args, **kwargs):
            calls.append(("linear", args, kwargs))

        def set_angular_velocity(self, *args, **kwargs):
            calls.append(("angular", args, kwargs))

    class ObjectUtils:
        def set_object_position(self, *args, **kwargs):
            calls.append(("object_utils", args, kwargs))

    source_body = SourceBody()
    object_utils = ObjectUtils()
    audit = isaac_fluid.SourceBodyWriterAudit(source_body_path=_SOURCE_BODY)
    audit.install(source_body=source_body, object_utils=object_utils)
    return audit, source_body, object_utils, calls


def test_source_body_writer_audit_catches_known_writer_surfaces_and_filters_path():
    audit, source_body, object_utils, underlying_calls = (
        _installed_source_writer_audit()
    )
    installed = audit.record()
    assert installed["coverage_complete"] is True
    assert set(installed["covered_surfaces"]) == {
        "source_body.set_world_pose",
        "source_body.set_local_pose",
        "source_body.set_linear_velocity",
        "source_body.set_angular_velocity",
        "physics_view.set_kinematic_targets",
        "object_utils.set_object_position",
    }

    audit.reset()
    source_body.set_world_pose(position=np.zeros(3))
    source_body.set_local_pose(translation=np.zeros(3))
    source_body.set_linear_velocity(np.ones(3))
    source_body.set_angular_velocity(np.ones(3))
    source_body._prim_view._physics_view.set_kinematic_targets("targets", "indices")
    object_utils.set_object_position("/World/other", np.zeros(3))
    object_utils.set_object_position(
        object_path=_SOURCE_BODY,
        position=np.zeros(3),
    )

    record = audit.record()
    assert record["call_count"] == 6
    assert record["counts"] == {
        "source_body.set_world_pose": 1,
        "source_body.set_local_pose": 1,
        "source_body.set_linear_velocity": 1,
        "source_body.set_angular_velocity": 1,
        "physics_view.set_kinematic_targets": 1,
        "object_utils.set_object_position": 1,
    }
    assert record["source_pose_write_count_after_play"] == 5
    assert record["kinematic_target_update_count"] == 1
    assert record["valid"] is False
    assert len(underlying_calls) == 7


def test_close_probe_fails_when_required_writer_surface_cannot_be_instrumented():
    source_body = SimpleNamespace(set_world_pose=lambda **kwargs: None)
    object_utils = SimpleNamespace(set_object_position=lambda *args, **kwargs: None)
    audit = isaac_fluid.SourceBodyWriterAudit(source_body_path=_SOURCE_BODY)
    audit.install(source_body=source_body, object_utils=object_utils)
    audit_record = audit.record()
    assert audit_record["coverage_complete"] is False
    assert any(
        limit.startswith("required_surface_not_intercepted:")
        for limit in audit_record["coverage_limits"]
    )

    vessel, state = _dynamic_contact_vessel(
        source_writer_audit=audit,
        require_complete_writer_audit=True,
    )
    _reset_and_pre_roll_contact_frames(vessel, state)

    assert vessel.maybe_attach(_contact_request_controller(), {}) is False
    assert vessel.record()["failure_reason"] == (
        "source_writer_audit_coverage_incomplete"
    )


def test_dynamic_contact_vessel_exposes_and_fails_an_observed_writer_call():
    audit, source_body, object_utils, _ = _installed_source_writer_audit()
    del object_utils
    vessel, state = _dynamic_contact_vessel(
        source_writer_audit=audit,
        require_complete_writer_audit=True,
    )
    _reset_and_pre_roll_contact_frames(vessel, state)
    assert vessel.maybe_attach(_contact_request_controller(), {}) is True
    state["contacts"] = True
    for step in range(20, 25):
        state["physics_step"] = step
        vessel.update_after_substep()
    assert vessel.record()["probe_qualified_now"] is True

    source_body.set_linear_velocity(np.ones(3))
    observed = vessel.record()
    assert observed["probe_qualified_now"] is False
    assert observed["source_pose_write_count_after_play"] == 1
    assert observed["observed_writer_audit"][
        "prohibited_writer_call_count"
    ] == 1
    assert observed["source_writer_audit"]["counts"][
        "source_body.set_linear_velocity"
    ] == 1

    state["physics_step"] = 25
    vessel.update_after_substep()
    assert vessel.record()["failure_reason"] == "source_writer_observed"


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


def test_dynamic_source_visual_validator_is_read_only_and_checks_inheritance():
    authored_source = _translation(0.3, -0.2, 0.8)
    authored_mesh = _translation(0.4, -0.2, 0.85)
    current_source = _rotation_z(90)
    current_source[3, :3] = [1.0, 2.0, 3.0]
    current_mesh = isaac_fluid._tracked_child_world_matrix(
        child_authored_world=authored_mesh,
        parent_authored_world=authored_source,
        parent_current_world=current_source,
    )
    validator = isaac_fluid.ReadOnlySourceVisualMeshValidator(
        source_authored_world_matrix=authored_source,
        visual_mesh_authored_world_matrix=authored_mesh,
        read_source_world_matrix=lambda: current_source.copy(),
        read_visual_mesh_world_matrix=lambda: current_mesh.copy(),
    )

    valid = validator.validate()
    assert valid["policy"] == "inherited_dynamic_child_readback_v1"
    assert valid["valid"] is True
    assert valid["source_or_visual_pose_write_count"] == 0

    current_mesh[3, 0] += 0.01
    invalid = validator.validate()
    assert invalid["valid"] is False
    assert invalid["translation_error_m"] == pytest.approx(0.01)

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

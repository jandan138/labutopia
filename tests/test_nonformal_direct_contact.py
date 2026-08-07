from tools.labutopia_fluid import nonformal_direct_contact


def _pair(classification, *, current=True, transient=False, points=True):
    return {
        "classification": classification,
        "current": current,
        "transient": transient,
        "headers": [{"type": "PERSIST"}],
        "points": [{"position": [0.0, 0.0, 0.0]}] if points else [],
    }


def _sample(*pairs):
    return {"physics_index": 17, "pairs": list(pairs)}


SOURCE = "/World/beaker2/mesh"
LEFT = "/World/Franka/panda_leftfinger/collision"
RIGHT = "/World/Franka/panda_rightfinger/collision"
HAND = "/World/Franka/panda_hand/collision"
ARM = "/World/Franka/panda_link3/collision"
SUPPORT = "/World/table/collision"


def _identities():
    return {
        "source_colliders": [SOURCE],
        "left_colliders": [LEFT],
        "right_colliders": [RIGHT],
        "hand_colliders": [HAND],
        "other_robot_colliders": [ARM],
        "support_colliders": [SUPPORT],
        "other_colliders": [],
        "stage_id": 7,
        "collider_owners": {
            SOURCE: "/World/beaker2",
            LEFT: "/World/Franka/panda_leftfinger",
            RIGHT: "/World/Franka/panda_rightfinger",
            HAND: "/World/Franka/panda_hand",
            ARM: "/World/Franka/panda_link3",
            SUPPORT: "/World/table",
        },
    }


def _occurrence(first, second, *, current=True, transient=False, owners=None):
    owners = _identities()["collider_owners"] if owners is None else owners
    header = {
        "actor0": owners[first],
        "actor1": owners[second],
        "collider0": first,
        "collider1": second,
        "proto_index0": 1,
        "proto_index1": 1,
        "type": "PERSIST" if current else "LOST",
        "stage_id": 7,
        "contact_data_offset": 0,
        "num_contact_data": 1,
        "friction_anchors_offset": 0,
        "num_friction_anchors_data": 1,
    }
    point = {
        "position": [0.0, 0.0, 0.0],
        "normal": [0.0, 0.0, 1.0],
        "impulse": [0.0, 0.0, 0.0],
        "separation": 0.0,
        "face_index0": 0,
        "face_index1": 0,
        "material0": "__zero__",
        "material1": "__zero__",
    }
    anchor = {"position": [0.0, 0.0, 0.0], "impulse": [0.0, 0.0, 0.0]}
    return {
        "canonical_pair": [
            {"collider_path": first, "proto_index": 1},
            {"collider_path": second, "proto_index": 1},
        ],
        "current": current,
        "transient": transient,
        "event_sequence": "PERSIST" if current else "LOST",
        "bootstrap": False,
        "headers": [header],
        "contact_data": [point],
        "friction_anchors": [anchor],
        "fragments": [
            {
                "header": header,
                "contact_data": [point],
                "friction_anchors": [anchor],
            }
        ],
    }


def _full_report(*occurrences):
    headers = [header for occurrence in occurrences for header in occurrence["headers"]]
    points = [point for occurrence in occurrences for point in occurrence["contact_data"]]
    anchors = [
        anchor for occurrence in occurrences for anchor in occurrence["friction_anchors"]
    ]
    return {
        "authority": "full_contact_report_step_v1",
        "physics_index": 17,
        "range_partition_valid": True,
        "header_count": len(headers),
        "contact_data_count": len(points),
        "friction_anchor_count": len(anchors),
        "occurrence_count": len(occurrences),
        "event_sequences": [
            occurrence["event_sequence"] for occurrence in occurrences
        ],
        "occurrences": list(occurrences),
    }


def test_invalid_sensor_crosschecks_do_not_replace_valid_direct_bilateral_contact():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(_pair("LEFT_SOURCE"), _pair("RIGHT_SOURCE")),
        sensor_status={
            "left": {"available": False},
            "right": {"available": True, "observed_source_pair": True},
            "hand": {"available": False},
        },
    )

    assert result["decision"] == "OBSERVED"
    assert result["direct_contact"] == {"left": True, "right": True, "hand": False}
    assert result["sensor_crosscheck"]["unavailable"] == ["hand", "left"]
    assert result["failures"] == []


def test_unilateral_direct_contact_is_a_physical_failure():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(_pair("RIGHT_SOURCE"))
    )

    assert result["decision"] == "PHYSICAL_FAIL"
    assert result["failures"] == ["left_direct_contact_missing"]


def test_transient_direct_contact_does_not_count_as_a_grasp_observation():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(
            _pair("LEFT_SOURCE", current=False, transient=True),
            _pair("RIGHT_SOURCE", current=False, transient=True),
        )
    )

    assert result["decision"] == "PHYSICAL_FAIL"
    assert result["failures"] == [
        "left_direct_contact_missing",
        "right_direct_contact_missing",
    ]


def test_source_contact_with_hand_is_a_physical_failure():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(
            _pair("LEFT_SOURCE"),
            _pair("RIGHT_SOURCE"),
            _pair("SOURCE_OTHER"),
        )
    )

    assert result["decision"] == "PHYSICAL_FAIL"
    assert result["failures"] == ["unexpected_source_contact"]


def test_robot_environment_contact_is_an_explicit_physical_failure():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(_pair("ROBOT_ENVIRONMENT"))
    )

    assert result["decision"] == "PHYSICAL_FAIL"
    assert result["failures"] == [
        "left_direct_contact_missing",
        "right_direct_contact_missing",
        "robot_environment_contact",
    ]


def test_source_internal_wrapper_is_not_accepted_as_external_shell_contact():
    internal_wrapper = "/World/beaker2/FluidSafeWrapperCanonical/collision"
    identities = _identities()
    identities["other_colliders"] = [internal_wrapper]
    identities["collider_owners"][internal_wrapper] = "/World/beaker2"

    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        _full_report(
            _occurrence(
                internal_wrapper,
                LEFT,
                owners=identities["collider_owners"],
            )
        ),
        identities=identities,
    )

    assert result["decision"] == "PHYSICAL_FAIL"
    assert result["direct_contact"] == {"left": False, "right": False, "hand": False}
    assert result["failures"] == [
        "left_direct_contact_missing",
        "right_direct_contact_missing",
        "robot_environment_contact",
    ]


def test_sensor_positive_missing_from_direct_report_is_audit_no_go():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(_pair("RIGHT_SOURCE")),
        sensor_status={
            "left": {"available": True, "observed_source_pair": True},
            "right": {"available": True, "observed_source_pair": True},
            "hand": {"available": False},
        },
    )

    assert result["decision"] == "AUDIT_NO_GO"
    assert result["failures"] == ["sensor_direct_disagreement:left"]


def test_malformed_current_direct_contact_is_an_audit_no_go():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(_pair("LEFT_SOURCE", points=False), _pair("RIGHT_SOURCE"))
    )

    assert result["decision"] == "AUDIT_NO_GO"
    assert result["failures"] == ["left_direct_contact_evidence_invalid"]


def test_full_report_adapter_observes_direct_bilateral_contact_without_sensor_frames():
    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        _full_report(
            _occurrence(SOURCE, LEFT),
            _occurrence(SOURCE, RIGHT),
            _occurrence(SOURCE, SUPPORT),
        ),
        identities=_identities(),
    )

    assert result["decision"] == "OBSERVED"
    assert result["direct_contact"] == {"left": True, "right": True, "hand": False}
    assert result["sensor_crosscheck"]["provided"] is False


def test_full_report_adapter_rejects_actor_mismatch_in_any_fragment():
    left = _occurrence(SOURCE, LEFT)
    right = _occurrence(SOURCE, RIGHT)
    right["fragments"][0]["header"] = {
        **right["headers"][0],
        "actor1": "/World/not-the-right-finger",
    }

    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        _full_report(left, right),
        identities=_identities(),
    )

    assert result["decision"] == "AUDIT_NO_GO"
    assert result["failures"] == ["fragment_actor_owner_mismatch"]


def test_transient_unexpected_source_contact_blocks_an_otherwise_bilateral_observation():
    result = nonformal_direct_contact.evaluate_direct_bilateral_contact(
        _sample(
            _pair("LEFT_SOURCE"),
            _pair("RIGHT_SOURCE"),
            _pair("SOURCE_OTHER", current=False, transient=True),
        )
    )

    assert result["decision"] == "PHYSICAL_FAIL"
    assert result["failures"] == ["unexpected_source_contact"]


def test_full_report_adapter_requires_full_accumulator_authority_and_fragments():
    report = _full_report(_occurrence(SOURCE, LEFT), _occurrence(SOURCE, RIGHT))
    report["authority"] = "untrusted"
    report["occurrences"][0]["fragments"] = []

    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        report,
        identities=_identities(),
    )

    assert result["decision"] == "AUDIT_NO_GO"
    assert result["failures"] == ["full_contact_report_invalid"]


def test_full_report_adapter_rejects_header_prototype_mismatch():
    right = _occurrence(SOURCE, RIGHT)
    right["headers"][0]["proto_index1"] = 2
    right["fragments"][0]["header"]["proto_index1"] = 2

    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        _full_report(_occurrence(SOURCE, LEFT), right),
        identities=_identities(),
    )

    assert result["decision"] == "AUDIT_NO_GO"
    assert result["failures"] == ["fragment_prototype_mismatch"]


def test_full_report_adapter_rejects_nonfinite_contact_points():
    left = _occurrence(SOURCE, LEFT)
    left["contact_data"][0]["position"][0] = float("nan")

    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        _full_report(left, _occurrence(SOURCE, RIGHT)),
        identities=_identities(),
    )

    assert result["decision"] == "AUDIT_NO_GO"
    assert "full_contact_point_invalid" in result["failures"]


def test_full_report_adapter_rejects_fragment_payload_mismatch():
    left = _occurrence(SOURCE, LEFT)
    left["fragments"][0]["contact_data"] = []

    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        _full_report(left, _occurrence(SOURCE, RIGHT)),
        identities=_identities(),
    )

    assert result["decision"] == "AUDIT_NO_GO"
    assert result["failures"] == ["fragment_payload_mismatch"]


def test_other_robot_link_environment_contact_is_a_physical_failure():
    result = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
        _full_report(
            _occurrence(SOURCE, LEFT),
            _occurrence(SOURCE, RIGHT),
            _occurrence(ARM, SUPPORT),
        ),
        identities=_identities(),
    )

    assert result["decision"] == "PHYSICAL_FAIL"
    assert result["failures"] == ["robot_environment_contact"]

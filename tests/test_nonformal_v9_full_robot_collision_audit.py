from __future__ import annotations

import pytest

from utils import nonformal_v9_full_robot_collision_audit as audit


def _scope() -> dict:
    return {
        "authority": "nonformal_v9_full_robot_collision_scope_v1",
        "robot_root_path": "/World/robot",
        "robot_colliders": [
            "/World/robot/hand/collision",
            "/World/robot/left_finger/collision",
            "/World/robot/link7/collision",
            "/World/robot/right_finger/collision",
        ],
        "left_finger_colliders": ["/World/robot/left_finger/collision"],
        "right_finger_colliders": ["/World/robot/right_finger/collision"],
        "target_colliders": {
            "beaker1": ["/World/beaker1/collision"],
            "source_wrapper": ["/World/source_wrapper/collision"],
            "table": ["/World/table/collision"],
            "source_shell": ["/World/source_shell/collision"],
        },
        "target_root_paths": {
            "beaker1": "/World/beaker1",
            "source_wrapper": "/World/source_wrapper",
            "table": "/World/table",
            "source_shell": "/World/source_shell",
        },
        "collider_owners": {
            "/World/robot/hand/collision": "/World/robot/hand",
            "/World/robot/left_finger/collision": "/World/robot/left_finger",
            "/World/robot/link7/collision": "/World/robot/link7",
            "/World/robot/right_finger/collision": "/World/robot/right_finger",
        },
    }


def _header(collider0: str, collider1: str) -> dict:
    def actor_for(collider: str) -> str:
        if collider.startswith("/World/robot/"):
            return collider.rsplit("/", 1)[0]
        return "/World/actors/target"

    return {
        "actor0": actor_for(collider0),
        "actor1": actor_for(collider1),
        "collider0": collider0,
        "collider1": collider1,
    }


def test_post_close_finger_shell_contact_is_allowed():
    scope = audit.validate_collision_scope(_scope())
    payload = {key: value for key, value in scope.items() if key != "sha256"}
    assert scope["sha256"] == audit.canonical_json_sha256(payload)
    assert audit.validate_collision_scope(scope) == scope

    result = audit.classify_scoped_contact(
        _header(
            "/World/source_shell/collision",
            "/World/robot/left_finger/collision",
        ),
        scope,
        pick_event=4,
    )

    assert result == {
        "classification": "ALLOWED_SOURCE_SHELL_FINGER",
        "canonical_collider_pair": [
            "/World/robot/left_finger/collision",
            "/World/source_shell/collision",
        ],
    }


def test_pre_close_finger_shell_contact_is_forbidden():
    header = _header(
        "/World/robot/right_finger/collision",
        "/World/source_shell/collision",
    )
    result = audit.classify_scoped_contact(
        header,
        _scope(),
        pick_event=3,
    )
    observations = audit.evaluate_collision_observations(
        _scope(),
        [{"callback_ordinal": 0, "pick_event": 3, "headers": [header]}],
    )

    assert result["classification"] == "FORBIDDEN_SOURCE_SHELL"
    assert observations["audit_valid"] is False
    assert observations["classification_counts"] == {"FORBIDDEN_SOURCE_SHELL": 1}


def test_hand_shell_contact_is_forbidden():
    result = audit.classify_scoped_contact(
        _header(
            "/World/robot/hand/collision",
            "/World/source_shell/collision",
        ),
        _scope(),
        pick_event=6,
    )

    assert result["classification"] == "FORBIDDEN_SOURCE_SHELL"


def test_arm_link_shell_contact_is_forbidden():
    result = audit.classify_scoped_contact(
        _header(
            "/World/robot/link7/collision",
            "/World/source_shell/collision",
        ),
        _scope(),
        pick_event=6,
    )

    assert result["classification"] == "FORBIDDEN_SOURCE_SHELL"


def test_robot_actor_owner_spoof_is_forbidden():
    header = _header(
        "/World/robot/left_finger/collision",
        "/World/source_shell/collision",
    )
    header["actor0"] = "/World/robot/link7"

    result = audit.classify_scoped_contact(header, _scope(), pick_event=4)
    observations = audit.evaluate_collision_observations(
        _scope(),
        [{"callback_ordinal": 0, "pick_event": 4, "headers": [header]}],
    )

    assert result["classification"] == "FORBIDDEN_ACTOR_OWNER_MISMATCH"
    assert observations["audit_valid"] is False


@pytest.mark.parametrize(
    ("target_name", "classification"),
    [
        ("source_wrapper", "FORBIDDEN_SOURCE_WRAPPER"),
        ("beaker1", "FORBIDDEN_BEAKER1"),
        ("table", "FORBIDDEN_TABLE"),
    ],
)
def test_wrapper_beaker1_and_table_contacts_are_forbidden(
    target_name: str,
    classification: str,
):
    result = audit.classify_scoped_contact(
        _header(
            "/World/robot/left_finger/collision",
            f"/World/{target_name}/collision",
        ),
        _scope(),
        pick_event=6,
    )

    assert result["classification"] == classification


def test_unknown_collider_under_scoped_root_is_rejected():
    scope = _scope()
    header = _header(
        "/World/robot/left_finger/collision",
        "/World/beaker1/unlisted",
    )
    contact = audit.classify_scoped_contact(header, scope, pick_event=4)
    result = audit.evaluate_collision_observations(
        scope,
        [{"callback_ordinal": 0, "pick_event": 4, "headers": [header]}],
    )

    assert contact["classification"] == "UNKNOWN_SCOPED_CONTACT"
    assert result["audit_valid"] is False
    assert result["classification_counts"] == {"UNKNOWN_SCOPED_CONTACT": 1}
    assert result["first_forbidden_evidence"]["callback_ordinal"] == 0
    assert result["first_forbidden_evidence"]["contact"] == contact


def test_empty_callback_headers_are_valid_observations():
    scope = audit.validate_collision_scope(_scope())
    result = audit.evaluate_collision_observations(
        scope,
        [{"callback_ordinal": 0, "pick_event": None, "headers": []}],
    )

    assert result["audit_valid"] is True
    assert result["sample_count"] == 1
    assert result["header_count"] == 0
    assert result["classification_counts"] == {}
    assert result["first_forbidden_evidence"] is None


def test_malformed_scope_is_rejected():
    unsorted = _scope()
    unsorted["robot_colliders"] = list(reversed(unsorted["robot_colliders"]))
    with pytest.raises(ValueError, match="robot_colliders_invalid"):
        audit.validate_collision_scope(unsorted)

    missing_owner = _scope()
    del missing_owner["collider_owners"]["/World/robot/hand/collision"]
    with pytest.raises(ValueError, match="collider_owners_invalid"):
        audit.validate_collision_scope(missing_owner)

    digest_mismatch = audit.validate_collision_scope(_scope())
    digest_mismatch["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="sha256_mismatch"):
        audit.validate_collision_scope(digest_mismatch)


def test_callback_coverage_rejects_skipped_and_duplicate_blocks():
    valid = audit.evaluate_callback_coverage(
        [
            {
                "before_world_index": 10,
                "after_world_index": 12,
                "callback_count": 2,
            },
            {
                "before_world_index": 12,
                "after_world_index": 13,
                "callback_count": 1,
            },
        ]
    )
    skipped = audit.evaluate_callback_coverage(
        [
            {
                "before_world_index": 10,
                "after_world_index": 11,
                "callback_count": 1,
            },
            {
                "before_world_index": 12,
                "after_world_index": 13,
                "callback_count": 1,
            },
        ]
    )
    duplicate = audit.evaluate_callback_coverage(
        [
            {
                "before_world_index": 10,
                "after_world_index": 11,
                "callback_count": 1,
            },
            {
                "before_world_index": 10,
                "after_world_index": 11,
                "callback_count": 1,
            },
        ]
    )

    assert valid == {"audit_valid": True, "failures": []}
    assert skipped["audit_valid"] is False
    assert "record_1_not_consecutive" in skipped["failures"]
    assert duplicate["audit_valid"] is False
    assert "record_1_not_consecutive" in duplicate["failures"]

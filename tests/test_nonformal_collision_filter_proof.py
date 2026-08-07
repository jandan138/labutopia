from __future__ import annotations

import ast
from pathlib import Path

import pytest

from utils import nonformal_collision_filter_proof as proof


HAND_BODY = "/World/Franka/panda_hand"
HAND_COLLIDER = f"{HAND_BODY}/collision"
SOURCE_MESH = "/World/beaker2/mesh"
WRAPPER_ROOT = "/World/beaker2/FluidSafeWrapperCanonical"
WRAPPER_COLLIDER = f"{WRAPPER_ROOT}/panel_000"


def _sha(character: str) -> str:
    return character * 64


def _contract() -> dict:
    payload = {
        "authority": "nonformal_wrapper_franka_collision_filter_proof_v1",
        "classification": "NON_FORMAL_OBSERVATION_ONLY",
        "schema_version": 1,
        "v7_config_sha256": _sha("a"),
        "local_scene_sha256": _sha("b"),
        "local_franka_sha256": _sha("c"),
        "cube_overlay_sha256": _sha("d"),
        "selected_hand_body_path": HAND_BODY,
        "source_mesh_path": SOURCE_MESH,
        "wrapper_root_path": WRAPPER_ROOT,
        "variants": [
            "scoped_unfiltered_qualification",
            "authored_filter_confirmation",
        ],
    }
    return {**payload, "sha256": proof.canonical_json_sha256(payload)}


def _header(event_type: str, collider0: str, collider1: str) -> dict:
    def actor_for(collider: str) -> str:
        if collider.startswith(HAND_BODY):
            return HAND_BODY
        return "/World/beaker2"

    return {
        "type": event_type,
        "actor0": actor_for(collider0),
        "actor1": actor_for(collider1),
        "collider0": collider0,
        "collider1": collider1,
    }


def _variant(
    variant: str,
    *,
    include_mesh: bool = True,
    include_wrapper: bool = False,
) -> dict:
    reports = []
    if include_mesh:
        reports.append(_header("FOUND", SOURCE_MESH, HAND_COLLIDER))
    if include_wrapper:
        reports.extend(
            [
                _header("FOUND", HAND_COLLIDER, WRAPPER_COLLIDER),
                _header("PERSIST", WRAPPER_COLLIDER, HAND_COLLIDER),
            ]
        )
    return {
        "variant": variant,
        "selected_hand_collider": HAND_COLLIDER,
        "source_mesh_colliders": [SOURCE_MESH],
        "wrapper_colliders": [WRAPPER_COLLIDER],
        "transform_plan_sha256": _sha("e"),
        "runtime_identity_sha256": _sha("f"),
        "reports": reports,
    }


def _positive_variants() -> tuple[dict, dict]:
    return (
        _variant("scoped_unfiltered_qualification", include_wrapper=True),
        _variant("authored_filter_confirmation"),
    )


def _pair(first: str, second: str) -> list[str]:
    return sorted([first, second])


def test_positive_ab_matrix_is_diagnostic_only():
    contract = _contract()
    unfiltered, authored = _positive_variants()

    assert proof.validate_filter_proof_contract(contract) == contract

    unfiltered_audit = proof.evaluate_variant_contacts(
        unfiltered["variant"],
        unfiltered["selected_hand_collider"],
        unfiltered["source_mesh_colliders"],
        unfiltered["wrapper_colliders"],
        unfiltered["reports"],
    )
    authored_audit = proof.evaluate_variant_contacts(
        authored["variant"],
        authored["selected_hand_collider"],
        authored["source_mesh_colliders"],
        authored["wrapper_colliders"],
        authored["reports"],
    )

    assert unfiltered_audit["audit_valid"] is True
    assert unfiltered_audit["source_mesh_contact_observed"] is True
    assert unfiltered_audit["source_mesh_contact_count"] == 1
    assert unfiltered_audit["wrapper_contact_observed"] is True
    assert unfiltered_audit["wrapper_contact_count"] == 1
    assert unfiltered_audit["source_mesh_contact_pairs"] == [
        _pair(HAND_COLLIDER, SOURCE_MESH)
    ]
    assert unfiltered_audit["wrapper_contact_pairs"] == [
        _pair(HAND_COLLIDER, WRAPPER_COLLIDER)
    ]
    assert authored_audit["audit_valid"] is True
    assert authored_audit["source_mesh_contact_observed"] is True
    assert authored_audit["wrapper_contact_observed"] is False
    assert authored_audit["wrapper_contact_count"] == 0

    assert proof.evaluate_ab_filter_proof(contract, unfiltered, authored) == {
        "outcome": "FILTER_BEHAVIOR_OBSERVED_DIAGNOSTIC_ONLY",
        "failures": [],
    }


def test_authored_variant_wrapper_contact_is_inconclusive():
    contract = _contract()
    unfiltered, authored = _positive_variants()
    authored["reports"].append(_header("FOUND", HAND_COLLIDER, WRAPPER_COLLIDER))

    result = proof.evaluate_ab_filter_proof(contract, unfiltered, authored)

    assert result["outcome"] == "OBSERVATION_INCONCLUSIVE"
    assert "authored:selected_hand_wrapper_contact_unexpected" in result["failures"]


def test_unfiltered_variant_missing_wrapper_contact_is_inconclusive():
    contract = _contract()
    unfiltered = _variant("scoped_unfiltered_qualification")
    authored = _variant("authored_filter_confirmation")

    result = proof.evaluate_ab_filter_proof(contract, unfiltered, authored)

    assert result["outcome"] == "OBSERVATION_INCONCLUSIVE"
    assert "unfiltered:selected_hand_wrapper_contact_count_invalid" in result[
        "failures"
    ]


def test_multiple_active_wrapper_contacts_qualify_the_unfiltered_variant():
    contract = _contract()
    unfiltered, authored = _positive_variants()
    unfiltered["wrapper_colliders"] = [
        WRAPPER_COLLIDER,
        f"{WRAPPER_ROOT}/panel_001",
    ]
    unfiltered["reports"].append(
        _header(
            "FOUND",
            HAND_COLLIDER,
            f"{WRAPPER_ROOT}/panel_001",
        )
    )
    authored["wrapper_colliders"] = list(unfiltered["wrapper_colliders"])

    result = proof.evaluate_ab_filter_proof(contract, unfiltered, authored)

    assert result == {
        "outcome": "FILTER_BEHAVIOR_OBSERVED_DIAGNOSTIC_ONLY",
        "failures": [],
    }


def test_lost_wrapper_header_does_not_qualify_the_unfiltered_variant():
    unfiltered = _variant("scoped_unfiltered_qualification")
    unfiltered["reports"].append(
        _header("LOST", HAND_COLLIDER, WRAPPER_COLLIDER)
    )

    audit = proof.evaluate_variant_contacts(
        unfiltered["variant"],
        unfiltered["selected_hand_collider"],
        unfiltered["source_mesh_colliders"],
        unfiltered["wrapper_colliders"],
        unfiltered["reports"],
    )

    assert audit["audit_valid"] is False
    assert audit["wrapper_contact_observed"] is False
    assert "selected_hand_wrapper_contact_count_invalid" in audit["failures"]


def test_wrong_actor_pair_does_not_qualify_a_selected_collider_contact():
    unfiltered = _variant("scoped_unfiltered_qualification", include_wrapper=True)
    unfiltered["reports"] = [
        {
            **_header("FOUND", HAND_COLLIDER, SOURCE_MESH),
            "actor1": "/World/beaker1",
        },
        {
            **_header("FOUND", HAND_COLLIDER, WRAPPER_COLLIDER),
            "actor1": "/World/beaker1",
        },
    ]

    audit = proof.evaluate_variant_contacts(
        unfiltered["variant"],
        unfiltered["selected_hand_collider"],
        unfiltered["source_mesh_colliders"],
        unfiltered["wrapper_colliders"],
        unfiltered["reports"],
    )

    assert audit["audit_valid"] is False
    assert audit["source_mesh_contact_observed"] is False
    assert audit["wrapper_contact_observed"] is False
    assert "selected_hand_contact_actor_pair_invalid" in audit["failures"]


def test_missing_source_mesh_positive_control_is_inconclusive():
    contract = _contract()
    unfiltered, authored = _positive_variants()
    authored["reports"] = []

    result = proof.evaluate_ab_filter_proof(contract, unfiltered, authored)

    assert result["outcome"] == "OBSERVATION_INCONCLUSIVE"
    assert "authored:selected_hand_source_mesh_contact_missing" in result["failures"]


@pytest.mark.parametrize(
    ("field", "replacement", "failure"),
    [
        (
            "selected_hand_collider",
            f"{HAND_BODY}/alternate_collision",
            "selected_hand_collider_mismatch",
        ),
        (
            "source_mesh_colliders",
            [f"{SOURCE_MESH}/collision"],
            "source_mesh_collider_inventory_mismatch",
        ),
        (
            "wrapper_colliders",
            [f"{WRAPPER_ROOT}/panel_001"],
            "wrapper_collider_inventory_mismatch",
        ),
        ("transform_plan_sha256", _sha("1"), "transform_plan_sha256_mismatch"),
        ("runtime_identity_sha256", _sha("2"), "runtime_identity_sha256_mismatch"),
    ],
)
def test_mismatched_pose_runtime_or_inventory_blocks_comparison(
    field: str,
    replacement: object,
    failure: str,
):
    contract = _contract()
    unfiltered, authored = _positive_variants()
    authored[field] = replacement

    result = proof.evaluate_ab_filter_proof(contract, unfiltered, authored)

    assert result["outcome"] == "RUNTIME_BLOCKED"
    assert failure in result["failures"]


def test_tampered_contract_is_rejected_and_blocks_comparison():
    tampered = _contract()
    tampered["sha256"] = _sha("0")
    unfiltered, authored = _positive_variants()

    with pytest.raises(ValueError, match="contract_sha256_mismatch"):
        proof.validate_filter_proof_contract(tampered)

    assert proof.evaluate_ab_filter_proof(tampered, unfiltered, authored) == {
        "outcome": "RUNTIME_BLOCKED",
        "failures": ["filter_proof_contract_invalid"],
    }


@pytest.mark.parametrize(
    ("header", "failure"),
    [
        (
            {
                "type": "FOUND",
                "actor0": HAND_BODY,
                "actor1": "/World/beaker2",
                "collider0": HAND_COLLIDER,
                "collider1": SOURCE_MESH,
                "unexpected": True,
            },
            "report_0_header_invalid",
        ),
        (
            _header("BEGIN", HAND_COLLIDER, SOURCE_MESH),
            "report_0_type_invalid",
        ),
        (
            {
                "type": "FOUND",
                "actor0": HAND_BODY,
                "actor1": "/World/beaker2",
                "collider0": HAND_COLLIDER,
                "collider1": "World/beaker2/mesh",
            },
            "report_0_header_invalid",
        ),
    ],
)
def test_invalid_headers_fail_the_variant_audit(header: dict, failure: str):
    audit = proof.evaluate_variant_contacts(
        "scoped_unfiltered_qualification",
        HAND_COLLIDER,
        [SOURCE_MESH],
        [WRAPPER_COLLIDER],
        [header],
    )

    assert audit["audit_valid"] is False
    assert failure in audit["failures"]


def test_proof_module_is_ascii_only_and_has_no_simulator_imports():
    source_path = Path(proof.__file__)
    source = source_path.read_bytes()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_names.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert source.isascii()
    assert not any(
        name == forbidden or name.startswith(f"{forbidden}.")
        for name in imported_names
        for forbidden in ("isaacsim", "omni", "pxr")
    )

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native
from tools.labutopia_fluid import run_nonformal_wrapper_franka_filter_proof as runner
from utils import nonformal_collision_filter_proof as proof


REPO_ROOT = Path(__file__).resolve().parents[1]
V7_CONFIG = REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v7.yaml"


def test_filter_proof_defaults_to_the_pinned_v7_config(tmp_path):
    args = runner.parse_args(["--out-dir", str(tmp_path / "proof")])

    assert args.config == V7_CONFIG.resolve()
    assert args.timeout_seconds == pytest.approx(600.0)
    assert args.child is False
    assert args.child_report_path == args.out_dir / "child_report.json"
    assert args.runtime_receipt_path == args.out_dir / "runtime_receipt.json"


def test_filter_proof_binds_the_exact_v7_assets_and_treatment():
    frozen = native.freeze_diagnostic_config(V7_CONFIG)

    contract = runner.build_filter_proof_contract(frozen)

    assert proof.validate_filter_proof_contract(contract) == contract
    assert contract["v7_config_sha256"] == frozen["sha256"]
    assert contract["local_scene_sha256"] == frozen["local_scene"]["sha256"]
    assert contract["local_franka_sha256"] == frozen["local_franka"]["sha256"]
    assert contract["cube_overlay_sha256"] == runner.sha256_file(
        runner.HIDDEN_CUBE_OVERLAY
    )


def test_sealed_child_input_preserves_the_frozen_config_metadata_needed_pre_bootstrap():
    frozen = native.freeze_diagnostic_config(V7_CONFIG)

    sealed = runner.build_sealed_child_input(frozen)

    assert sealed["config"] == frozen["config"]
    assert sealed["sha256"] == frozen["sha256"]
    assert sealed["source_path"] == frozen["source_path"]
    assert sealed["local_scene"] == frozen["local_scene"]
    assert sealed["local_franka"] == frozen["local_franka"]
    assert "canonical_bytes" not in sealed
    assert runner.source_paths(sealed)


def test_filter_proof_variant_policy_is_narrow_and_fail_closed():
    hand = "/World/Franka/panda_hand/geometry/panda_hand"

    authored = runner.build_variant_policy(
        "authored_filter_confirmation", hand
    )
    unfiltered = runner.build_variant_policy(
        "scoped_unfiltered_qualification", hand
    )

    assert authored["session_group_edit"] is None
    assert unfiltered["session_group_edit"] == {
        "environment_exclude_path": hand,
        "probe_group_path": "/World/ContactGraspCollisionGroups/ABProbeFranka",
        "probe_group_include_path": hand,
    }
    with pytest.raises(ValueError, match="filter_proof_variant_invalid"):
        runner.build_variant_policy("unexpected", hand)
    with pytest.raises(ValueError, match="filter_proof_hand_collider_invalid"):
        runner.build_variant_policy(
            "authored_filter_confirmation", "/World/Franka/panda_link7/collider"
        )


def test_filter_proof_source_closure_binds_runner_contract_and_native_implementation():
    frozen = native.freeze_diagnostic_config(V7_CONFIG)
    paths = set(runner.source_paths(frozen))

    assert Path(runner.__file__).resolve() in paths
    assert Path(native.__file__).resolve() in paths
    assert Path(proof.__file__).resolve() in paths
    assert V7_CONFIG.resolve() in paths
    assert REPO_ROOT / "controllers/atomic_actions/pick_controller.py" in paths


def test_filter_proof_runner_has_no_top_level_simulator_imports():
    source = Path(runner.__file__).read_bytes()
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


def test_kinematic_probe_does_not_issue_rejected_velocity_writes():
    runtime_path = (
        REPO_ROOT
        / "tools/labutopia_fluid/nonformal_wrapper_franka_filter_runtime.py"
    )
    tree = ast.parse(runtime_path.read_bytes())
    method_names = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert "set_linear_velocity" not in method_names
    assert "set_angular_velocity" not in method_names

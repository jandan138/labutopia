from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.labutopia_fluid import run_nonformal_authored_offset_behavior_contrast as runner


def _fixture_usd_dependency_closure() -> dict:
    binding = runner._config_binding()
    cells = runner._cell_profiles()
    layers = [
        {"identifier": path, "real_path": path, "sha256": digest}
        for path, digest in (
            (binding["asset"]["path"], binding["asset"]["sha256"]),
            (binding["robot_asset"]["path"], binding["robot_asset"]["sha256"]),
        )
    ]
    layers.sort(key=lambda item: item["real_path"])
    runtime_mdl_files = [
        {
            "purpose": item["purpose"],
            "path": item["path"],
            "byte_count": Path(item["path"]).stat().st_size,
            "sha256": item["sha256"],
        }
        for item in runner.dependency_resolution.APPROVED_RUNTIME_MDL_DEPENDENCIES
    ]
    runtime_mdl_files.sort(key=lambda item: item["path"])

    def resolution(profile: dict) -> dict:
        entries = [
            {"id": "fixture_asset", **binding["asset"]},
            {"id": "robot_asset", **binding["robot_asset"]},
            *(
                {"id": item["id"], "path": item["path"], "sha256": item["sha256"]}
                for item in profile["overlay_stack"]
            ),
        ]
        files = [
            {
                "path": item["path"],
                "byte_count": Path(item["path"]).stat().st_size,
                "sha256": item["sha256"],
            }
            for item in entries
        ]
        files.sort(key=lambda item: item["path"])
        resolution_payload = {
            "entries": entries,
            "files": files,
            "runtime_mdl_files": runtime_mdl_files,
            "runtime_mdl_builtin_modules": [],
            "unresolved": [],
            "texture_unresolved": [],
        }
        return {
            **resolution_payload,
            "sha256": runner.dependency_resolution.canonical_json_sha256(resolution_payload),
        }

    resolved_dependency_closures = {
        cell["profile"]["id"]: resolution(cell["profile"])
        for cell in cells
    }
    kit_profile_path = runner.REPO_ROOT / "tools/labutopia_fluid/profiles/isaac41_authored_offset_overlay_composition_experimental.kit"
    payload = {
        "authority": runner.FIXTURE_USD_CLOSURE_AUTHORITY,
        "schema_version": 1,
        "preflight": {
            "artifact_dir": "fixture_usd_composition_preflight",
            "report_sha256": "1" * 64,
            "manifest_sha256": "2" * 64,
            "runtime_receipt_sha256": "3" * 64,
            "observation_sha256": "4" * 64,
            "execution_request_sha256": "5" * 64,
            "source_identity_sha256": "6" * 64,
        },
        "layers": layers,
        "closure_sha256": runner.direct_probe._canonical_json_sha256({"layers": layers}),
        "resolved_usd_dependency_closures": resolved_dependency_closures,
        "static_kit_profile": {
            "path": str(kit_profile_path),
            "sha256": runner._sha256_file(kit_profile_path),
            "pvd_extension_declared": False,
        },
    }
    return {**payload, "sha256": runner._canonical_sha256(payload)}


def _request() -> dict:
    return runner.build_contrast_request(
        fixture_usd_dependency_closure=_fixture_usd_dependency_closure()
    )


def test_contrast_request_uses_the_selected_cube_only_control_and_finite_package():
    request = _request()

    assert [cell["id"] for cell in request["cells"]] == [
        "cube_only_baseline",
        "cube_plus_finite_target_offsets",
    ]
    assert request["cells"][0]["profile"]["overlay_stack"] == [
        {
            "id": "hidden_cube_collision_disable",
            "path": str(runner.HIDDEN_CUBE_OVERLAY.resolve()),
            "sha256": runner._sha256_file(runner.HIDDEN_CUBE_OVERLAY),
        }
    ]
    assert [item["id"] for item in request["cells"][1]["profile"]["overlay_stack"]] == [
        "finite_target_offsets_calibration_v2",
        "hidden_cube_collision_disable",
    ]
    assert request["authorization"] == runner.contrast.AUTHORIZATION


def test_contrast_runner_is_create_only_and_keeps_g0_out_of_its_public_contract():
    output = runner.REPO_ROOT / "artifacts/runs/behavior-contrast-parse-test"
    args = runner.parse_args(["--out-dir", str(output)])

    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert args.out_dir == output.resolve()
    assert runner.expected_child_returncode(runner.contrast.OBSERVED) == 0
    assert runner.expected_child_returncode(runner.contrast.INCONCLUSIVE) == 0
    assert runner.expected_child_returncode(runner.contrast.NO_GO) == 0
    assert runner.expected_child_returncode(runner.contrast.RUNTIME_BLOCKED) == 2
    assert "G0_GO" not in source
    assert "phase3_authorized\": True" not in source


def test_treatment_overlay_never_masks_the_robot_reference_before_robot_creation():
    class Prim:
        def __init__(self, valid: bool):
            self.valid = valid

        def IsValid(self) -> bool:
            return self.valid

    class Stage:
        def __init__(self):
            self.robot = Prim(False)

        def GetPrimAtPath(self, path: str) -> Prim:
            assert path == "/World/Franka"
            return self.robot

    stage = Stage()
    references: list[tuple[str, str]] = []

    def add_reference(*, usd_path: str, prim_path: str) -> None:
        references.append((usd_path, prim_path))
        stage.robot.valid = True

    runner.direct_probe._ensure_robot_reference(
        stage,
        robot_asset_path=runner.REPO_ROOT / "robots/franka/franka.usd",
        add_reference_to_stage=add_reference,
    )

    assert references == [
        (str((runner.REPO_ROOT / "robots/franka/franka.usd").resolve()), "/World/Franka")
    ]


def test_direct_report_summary_validates_trace_before_deriving_metrics():
    request = _request()
    cell = request["cells"][1]
    calibration_path = str(runner.FINITE_TARGET_OFFSET_OVERLAY.resolve())
    targets = (
        ("left_finger", "/World/Franka/panda_leftfinger/geometry/panda_leftfinger", 0.001),
        ("right_finger", "/World/Franka/panda_rightfinger/geometry/panda_rightfinger", 0.001),
        ("table", "/World/table/surface/mesh", 0.00164),
    )
    snapshot_records = [
        {
            "id": identifier,
            "path": path,
            "prim_type": "Mesh",
            "usd_collision_api_applied": True,
            "physx_collision_api_applied": True,
            "contact_offset_authored": True,
            "rest_offset_authored": True,
            "contact_offset_m": offset,
            "rest_offset_m": 0.0,
            "contact_offset_strongest_layer": calibration_path,
            "rest_offset_strongest_layer": calibration_path,
            "contact_offset_anonymous_opinion": False,
            "rest_offset_anonymous_opinion": False,
        }
        for identifier, path, offset in targets
    ]
    snapshot_payload = {"records": snapshot_records}
    snapshot = {
        **snapshot_payload,
        "sha256": runner.direct_probe._canonical_json_sha256(snapshot_payload),
    }
    layers = [
        {
            "identifier": path,
            "real_path": path,
            "sha256": digest,
        }
        for path, digest in (
            (request["binding"]["asset"]["path"], request["binding"]["asset"]["sha256"]),
            (
                request["binding"]["robot_asset"]["path"],
                request["binding"]["robot_asset"]["sha256"],
            ),
            *(
                (item["path"], item["sha256"])
                for item in cell["profile"]["overlay_stack"]
            ),
        )
    ]
    layers.sort(key=lambda item: item["real_path"])
    closure_payload = {"layers": layers}
    closure = {
        **closure_payload,
        "sha256": runner.direct_probe._canonical_json_sha256(closure_payload),
    }
    history = [
        {
            "physics_index": 0,
            "direct": {"direct_contact": {"left": True, "right": True}},
        }
    ]
    trace_record = {
        "physics_index": 0,
        "occurrences": [
            {
                "current": True,
                "canonical_pair": [
                    {"collider_path": "/source"},
                    {"collider_path": "/left"},
                ],
            },
            {
                "current": True,
                "canonical_pair": [
                    {"collider_path": "/source"},
                    {"collider_path": "/right"},
                ],
            },
        ],
    }
    trace_bytes = (
        json.dumps(trace_record, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        + b"\n"
    )
    expected_input_closure = {
        item["path"]: item["sha256"] for item in request["binding"]["config_closure"]
    }
    expected_input_closure.update(
        {
            item["path"]: item["sha256"]
            for item in request["fixture_usd_dependency_closure"]["resolved_usd_dependency_closures"][
                cell["profile"]["id"]
            ]["files"]
        }
    )
    with TemporaryDirectory(dir="/tmp/opencode") as directory:
        cell_dir = Path(directory)
        trace_path = cell_dir / "direct_contact_reports.jsonl.gz"
        with gzip.open(trace_path, "xb") as stream:
            stream.write(trace_bytes)
        trace = {
            "path": str(trace_path),
            "record_count": 1,
            "complete": True,
            "compressed_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
            "uncompressed_sha256": hashlib.sha256(trace_bytes).hexdigest(),
        }
        direct_report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_direct_contact_probe_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": "OBSERVED",
            "config": {
                "path": request["binding"]["config"]["path"],
                "input_closure": dict(sorted(expected_input_closure.items())),
                "asset_path": request["binding"]["asset"]["path"],
                "robot_asset_path": request["binding"]["robot_asset"]["path"],
            },
            "treatment": {
                "offset_treatment_profile": cell["profile"],
                "seed": {"requested_seed": request["plan"]["common"]["seed"]},
                "contact_identities": {
                    "source_colliders": ["/source"],
                    "left_colliders": ["/left"],
                    "right_colliders": ["/right"],
                },
                "report_layer_sha256_after_reset": "c" * 64,
                "report_layer_sha256_after_run": "c" * 64,
                "report_layer_unchanged_post_reset": True,
                "offset_target_snapshot_after_reset": snapshot,
                "offset_target_snapshot_after_run": snapshot,
                "usd_dependency_closure_after_reset": closure,
                "usd_dependency_closure_after_run": closure,
                "resolved_usd_dependency_closure_before_world": request[
                    "fixture_usd_dependency_closure"
                ]["resolved_usd_dependency_closures"][cell["profile"]["id"]],
                "resolved_usd_dependency_closure_after_reset": request[
                    "fixture_usd_dependency_closure"
                ]["resolved_usd_dependency_closures"][cell["profile"]["id"]],
                "resolved_usd_dependency_closure_after_run": request[
                    "fixture_usd_dependency_closure"
                ]["resolved_usd_dependency_closures"][cell["profile"]["id"]],
                "cube_collision_disabled_after_reset": True,
                "cube_collision_disabled_after_run": True,
                "lift_action_applied": False,
            },
            "result": {
                "observed_bilateral_direct_contact": True,
                "direct_report_trace": trace,
                "source_writer_audit": {
                    "valid": True,
                    "coverage_complete": True,
                    "source_pose_write_count_after_play": 0,
                    "source_velocity_write_count_after_play": 0,
                    "object_utils_source_position_write_count_after_play": 0,
                    "kinematic_target_update_count": 0,
                },
            },
            "history": history,
        }
        (cell_dir / runner.DIRECT_REPORT_BASENAME).write_text(
            json.dumps(direct_report, sort_keys=True), encoding="utf-8"
        )

        observation = runner._summarize_direct_report(
            direct_report=direct_report,
            request=request,
            cell=cell,
            cell_dir=cell_dir,
            runtime_receipt_matched=True,
        )

    assert observation["metrics"] == {
        "first_bilateral_current_physics_index": 0,
        "bilateral_current_sample_count": 1,
        "longest_bilateral_current_window": 1,
    }
    assert observation["treatment_audit"]["profile_authoring_valid"] is True


def test_blocked_cell_observations_preserve_the_runtime_blocked_decision():
    request = _request()
    cells = [runner._blocked_cell_observation(request, cell) for cell in request["cells"]]
    payload = {
        "authority": runner.contrast.OBSERVATION_AUTHORITY,
        "schema_version": 1,
        "classification": runner.CLASSIFICATION,
        "plan_sha256": request["plan_sha256"],
        "authorization": dict(runner.contrast.AUTHORIZATION),
        "cells": cells,
    }
    observation = {
        **payload,
        "sha256": runner.contrast.canonical_json_sha256(payload),
    }

    evaluation = runner.contrast.evaluate_observation(observation, plan=request["plan"])

    assert evaluation["decision"] == runner.contrast.RUNTIME_BLOCKED

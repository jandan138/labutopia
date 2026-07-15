from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from tools.labutopia_fluid import run_interndata_online_surface_probe as probe


def test_extract_liquid_semantic_mask_hashes_only_visible_liquid_pixels():
    payload = {
        "data": np.asarray([[0, 7, 7], [0, 0, 7]], dtype=np.uint32),
        "info": {
            "idToLabels": {
                "0": {"class": "BACKGROUND"},
                "7": {"class": "glass, online_liquid"},
            }
        },
    }

    mask, evidence = probe.extract_liquid_semantic_mask(
        payload,
        expected_width=3,
        expected_height=2,
    )

    assert mask.dtype == np.bool_
    assert mask.tolist() == [[False, True, True], [False, False, True]]
    assert evidence["semantic_ids"] == [7]
    assert evidence["visible_pixel_count"] == 3
    assert evidence["mask_sha256"] == probe._canonical_json_sha256(
        [[False, True, True], [False, False, True]]
    )


def test_extract_liquid_semantic_mask_binds_current_surface_frame_token():
    frame_token = "a" * 64
    payload = {
        "data": np.asarray([[0, 7], [7, 0]], dtype=np.uint32),
        "info": {
            "idToLabels": {
                "0": {"class": "BACKGROUND"},
                "7": {"class": f"online_liquid,{frame_token}"},
            }
        },
    }

    _mask, evidence = probe.extract_liquid_semantic_mask(
        payload,
        expected_width=2,
        expected_height=2,
        expected_surface_token=frame_token,
    )

    assert evidence["surface_frame_token"] == frame_token
    with pytest.raises(ValueError, match="online_liquid_surface_token_mismatch"):
        probe.extract_liquid_semantic_mask(
            payload,
            expected_width=2,
            expected_height=2,
            expected_surface_token="b" * 64,
        )


def test_extract_liquid_semantic_mask_can_record_camera_where_liquid_is_out_of_view():
    payload = {
        "data": np.zeros((2, 3), dtype=np.uint32),
        "info": {"idToLabels": {"0": {"class": "BACKGROUND"}}},
    }

    mask, evidence = probe.extract_liquid_semantic_mask(
        payload,
        expected_width=3,
        expected_height=2,
        expected_surface_token="a" * 64,
        allow_absent=True,
    )

    assert not mask.any()
    assert evidence["semantic_ids"] == []
    assert evidence["visible_pixel_count"] == 0
    assert evidence["surface_frame_token"] is None


def test_model_camera_rgb_is_named_and_shaped_like_inference_observation():
    rgb = np.zeros((256, 256, 3), dtype=np.uint8)

    name, observation = probe.format_camera_observation(
        "camera_1", rgb, camera_profile="model"
    )

    assert name == "camera_1_rgb"
    assert observation.shape == (3, 256, 256)
    assert observation.dtype == np.uint8
    assert observation.flags.c_contiguous


@pytest.mark.parametrize(
    "payload,error",
    [
        (
            {
                "data": np.zeros((2, 3), dtype=np.uint32),
                "info": {"idToLabels": {"0": {"class": "BACKGROUND"}}},
            },
            "online_liquid_semantic_id_missing",
        ),
        (
            {
                "data": np.zeros((2, 3), dtype=np.uint32),
                "info": {
                    "idToLabels": {
                        "0": {"class": "BACKGROUND"},
                        "7": {"class": "online_liquid"},
                    }
                },
            },
            "online_liquid_pixels_missing",
        ),
    ],
)
def test_extract_liquid_semantic_mask_fails_closed(payload, error):
    with pytest.raises(ValueError, match=error):
        probe.extract_liquid_semantic_mask(
            payload,
            expected_width=3,
            expected_height=2,
        )


def test_probe_contract_pins_online_input_physics_and_model_camera_size():
    contract = probe.default_probe_contract()

    assert contract["input_scene"].endswith(
        "lab_001_level1_pour_interndata_liquid_v1.usda"
    )
    assert contract["input_scene_sha256"] == (
        "ab9f5eb1d3bc387e13ccb23655454d9357833b261f346fd93d974b86e1f83139"
    )
    assert contract["particle_path"] == "/World/InternDataParityFluid/Particles"
    assert contract["particle_system_path"] == (
        "/World/InternDataParityFluid/ParticleSystem"
    )
    assert contract["source_actor_path"] == "/World/beaker2"
    assert contract["expected_particle_count"] == 3600
    assert contract["logical_dt"] == 1.0 / 30.0
    assert contract["integration_dt"] == 1.0 / 120.0
    assert contract["substeps_per_observation"] == 4
    assert contract["camera_resolution"] == [256, 256]
    assert contract["camera_paths"] == {
        "context": "/World/InternDataParityCamera",
        "closeup": "/World/InternDataParityCloseupCamera",
    }
    assert contract["model_camera_paths"] == {
        "camera_1": "/World/Camera1",
        "camera_2": "/World/Camera2",
    }
    assert contract["surface_observation_stride"] == 1
    assert contract["pre_episode_physx_initialization_steps"] == 1
    assert contract["rt_subframes"] == 4
    assert contract["source_body_mode"] == "kinematic"


def test_dynamic_source_mode_is_limited_to_hold_and_has_no_pose_driver():
    contract = probe.source_body_mode_contract("dynamic", treatment="hold")

    assert contract == {
        "mode": "dynamic",
        "kinematic_enabled": False,
        "action_driver": "none_dynamic_gravity",
        "activation_phase": "post_particle_initialization",
    }
    with pytest.raises(ValueError, match="dynamic_source_requires_hold_treatment"):
        probe.source_body_mode_contract("dynamic", treatment="pour")


def test_source_body_mode_accepts_only_post_set_precision_warning():
    class Attribute:
        def __init__(self, value, *, raise_after_set=False):
            self.value = value
            self.raise_after_set = raise_after_set

        def __bool__(self):
            return True

        def Get(self):
            return self.value

        def Set(self, value):
            self.value = value
            if self.raise_after_set:
                raise RuntimeError(
                    "Proceeding to use existing typeName / precision."
                )

    class Prim:
        def __init__(self):
            self.attributes = {
                "physics:kinematicEnabled": Attribute(True, raise_after_set=True),
                "physics:rigidBodyEnabled": Attribute(True),
            }

        def GetAttribute(self, name):
            return self.attributes[name]

        def GetPath(self):
            return "/World/beaker2"

    result = probe.apply_source_body_mode(
        Prim(),
        probe.source_body_mode_contract("dynamic", treatment="hold"),
    )

    assert result["kinematic_enabled_after"] is False
    assert "existing typeName / precision" in result["authoring_warning"]


def test_dynamic_hold_quality_requires_stable_body_and_full_retention():
    records = []
    for step in range(3):
        record = _record(
            step=step,
            treatment="hold",
            position_hash=f"{step + 1:064x}",
            surface_hash=f"{step + 2:064x}",
            liquid_hash=f"{step + 3:064x}",
            target_count=0,
        )
        record["source_body_mode"] = "dynamic"
        record["action"]["reference_pose_error"] = {
            "position_m": step * 0.001,
            "rotation_degrees": step * 0.1,
        }
        records.append(record)

    quality = probe.summarize_dynamic_hold_quality(records)

    assert quality["status"] == "PASS"
    assert quality["maximum_position_drift_m"] == pytest.approx(0.002)
    assert quality["minimum_source_particle_count"] == 3600

    records[-1]["raw_particle_counts"]["source"] = 3599
    records[-1]["raw_particle_counts"]["transit"] = 1
    assert probe.summarize_dynamic_hold_quality(records)["status"] == "FAIL"


def test_treatment_plans_are_common_initial_then_diverge_without_extra_hold_run():
    pour = probe.build_treatment_plan("pour")
    hold = probe.build_treatment_plan("hold")

    assert [state["step_index"] for state in pour] == list(range(691))
    assert [state["step_index"] for state in hold] == list(range(231))
    assert pour[0]["translation_progress"] == hold[0]["translation_progress"] == 0.0
    assert pour[0]["tilt_degrees"] == hold[0]["tilt_degrees"] == 0.0
    assert any(state["translation_progress"] > 0.0 for state in pour[1:231])
    assert any(state["tilt_degrees"] > 0.0 for state in pour[1:231])
    assert all(state["translation_progress"] == 0.0 for state in hold)
    assert all(state["tilt_degrees"] == 0.0 for state in hold)

    with pytest.raises(ValueError, match="treatment_invalid"):
        probe.build_treatment_plan("unknown")


def test_observation_transition_maps_reset_and_four_substeps_exactly():
    reset = probe.build_observation_transition(
        episode_id="pour-1",
        observation_index=0,
        logical_step_before=0,
        logical_step_after=0,
        integration_step_before=0,
        integration_step_after=0,
    )
    action = probe.build_observation_transition(
        episode_id="pour-1",
        observation_index=1,
        logical_step_before=0,
        logical_step_after=1,
        integration_step_before=0,
        integration_step_after=4,
        action_sha256="a" * 64,
    )

    assert reset.caused_by_action_index is None
    assert reset.simulation_time_before == reset.simulation_time_after == 0.0
    assert action.caused_by_action_index == 0
    assert action.action_sha256 == "a" * 64
    assert action.simulation_time_before == 0.0
    assert action.simulation_time_after == 1.0 / 30.0


def _record(
    *,
    step: int,
    treatment: str,
    position_hash: str,
    surface_hash: str,
    liquid_hash: str,
    target_count: int,
    surface_vertex_count: int = 9686,
    surface_face_count: int = 19368,
    context_liquid_pixels: int = 195,
    closeup_liquid_pixels: int = 400,
) -> dict:
    hold = treatment == "hold"
    return {
        "episode_id": f"{treatment}-1",
        "treatment": treatment,
        "runtime_contract_sha256": "7" * 64,
        "implementation_sha256": "8" * 64,
        "input_scene_sha256": probe.INPUT_SCENE_SHA256,
        "camera_profile": "validation",
        "source_body_mode": "kinematic",
        "observation_index": step,
        "logical_step_after": step,
        "integration_step_after": step * 4,
        "simulation_time_after": step / 30.0,
        "position_sha256": position_hash,
        "surface": {
            "geometry_sha256": surface_hash,
            "vertex_count": surface_vertex_count,
            "face_count": surface_face_count,
        },
        "action": {
            "target_pose_sha256": ("0" if hold else "1") * 64,
            "target_pose_xyzw": [0.0] * 7 if hold else [1.0] * 7,
        },
        "raw_particle_counts": {
            "source": 3600 - target_count,
            "target": target_count,
            "transit": 0,
            "tabletop_spill": 0,
            "below_table": 0,
            "nonfinite": 0,
        },
        "liquid_evidence_sha256": liquid_hash,
        "liquid_pixel_evidence": {
            "source": "semantic_segmentation_online_liquid",
            "cameras": [
                {
                    "camera": "context",
                    "visible_pixel_count": context_liquid_pixels,
                },
                {
                    "camera": "closeup",
                    "visible_pixel_count": closeup_liquid_pixels,
                },
            ],
        },
    }


def test_treatment_contrast_requires_raw_particles_surface_and_liquid_pixels():
    common = _record(
        step=0,
        treatment="hold",
        position_hash="a" * 64,
        surface_hash="b" * 64,
        liquid_hash="c" * 64,
        target_count=0,
    )
    pour_initial = {**common, "episode_id": "pour-1"}
    pour = _record(
        step=230,
        treatment="pour",
        position_hash="d" * 64,
        surface_hash="e" * 64,
        liquid_hash="f" * 64,
        target_count=1400,
    )
    hold = _record(
        step=230,
        treatment="hold",
        position_hash="g" * 64,
        surface_hash="h" * 64,
        liquid_hash="i" * 64,
        target_count=0,
    )

    contrast = probe.compare_treatments(
        [pour_initial, pour],
        [common, hold],
        checkpoint_step=230,
    )

    assert contrast["common_initial_state"] is True
    assert contrast["matched_simulation_time"] is True
    assert contrast["action_diverged"] is True
    assert contrast["raw_particles_diverged"] is True
    assert contrast["surface_diverged"] is True
    assert contrast["liquid_pixels_diverged"] is True
    assert contrast["causality_gate_passed"] is True


def test_treatment_contrast_accepts_equivalent_unordered_gpu_initials(tmp_path):
    pour_initial = _record(
        step=0,
        treatment="pour",
        position_hash="a" * 64,
        surface_hash="b" * 64,
        liquid_hash="c" * 64,
        target_count=0,
        surface_vertex_count=9686,
        surface_face_count=19368,
        closeup_liquid_pixels=400,
    )
    hold_initial = _record(
        step=0,
        treatment="hold",
        position_hash="d" * 64,
        surface_hash="e" * 64,
        liquid_hash="f" * 64,
        target_count=0,
        surface_vertex_count=9684,
        surface_face_count=19364,
        closeup_liquid_pixels=401,
    )
    # The real two-process runs differ only in floating-point spelling here.
    pour_initial["action"]["target_pose_xyzw"] = [0.295, 0.07499999999999997] + [0.0] * 5
    hold_initial["action"]["target_pose_xyzw"] = [0.295, 0.075] + [0.0] * 5
    initial_points = np.arange(3600 * 3, dtype=np.float32).reshape(3600, 3) / 1000.0
    pour_initial["initial_particle_snapshot"] = probe.write_initial_particle_snapshot(
        tmp_path / "pour_initial.npy",
        initial_points,
    )
    hold_initial["initial_particle_snapshot"] = probe.write_initial_particle_snapshot(
        tmp_path / "hold_initial.npy",
        (initial_points + np.float32(1.0e-6))[::-1],
    )

    pour_checkpoint = _record(
        step=230,
        treatment="pour",
        position_hash="1" * 64,
        surface_hash="2" * 64,
        liquid_hash="3" * 64,
        target_count=2701,
    )
    hold_checkpoint = _record(
        step=230,
        treatment="hold",
        position_hash="4" * 64,
        surface_hash="5" * 64,
        liquid_hash="6" * 64,
        target_count=0,
    )

    contrast = probe.compare_treatments(
        [pour_initial, pour_checkpoint],
        [hold_initial, hold_checkpoint],
        checkpoint_step=230,
    )

    assert contrast["common_initial_state_exact"] is False
    assert contrast["initial_conditions_equivalent"] is True
    assert contrast["common_initial_state"] is True
    assert contrast["initial_comparison_basis"] == (
        "bidirectional_particle_set_tolerance"
    )
    assert contrast["initial_particle_comparison"]["maximum_error_m"] < 2.0e-6
    assert contrast["initial_particle_comparison"]["minimum_unique_coverage"] == 1.0
    assert contrast["causality_gate_passed"] is True


def test_treatment_contrast_rejects_different_initial_particle_layouts(tmp_path):
    pour_initial = _record(
        step=0,
        treatment="pour",
        position_hash="a" * 64,
        surface_hash="b" * 64,
        liquid_hash="c" * 64,
        target_count=0,
    )
    hold_initial = _record(
        step=0,
        treatment="hold",
        position_hash="d" * 64,
        surface_hash="e" * 64,
        liquid_hash="f" * 64,
        target_count=0,
    )
    pour_initial["action"]["target_pose_xyzw"] = [0.0] * 7
    hold_initial["action"]["target_pose_xyzw"] = [0.0] * 7
    initial_points = np.zeros((3600, 3), dtype=np.float32)
    changed_points = initial_points.copy()
    changed_points[0, 0] = 0.01
    pour_initial["initial_particle_snapshot"] = probe.write_initial_particle_snapshot(
        tmp_path / "pour_initial.npy",
        initial_points,
    )
    hold_initial["initial_particle_snapshot"] = probe.write_initial_particle_snapshot(
        tmp_path / "hold_initial.npy",
        changed_points,
    )
    pour_checkpoint = _record(
        step=230,
        treatment="pour",
        position_hash="1" * 64,
        surface_hash="2" * 64,
        liquid_hash="3" * 64,
        target_count=2701,
    )
    hold_checkpoint = _record(
        step=230,
        treatment="hold",
        position_hash="4" * 64,
        surface_hash="5" * 64,
        liquid_hash="6" * 64,
        target_count=0,
    )

    contrast = probe.compare_treatments(
        [pour_initial, pour_checkpoint],
        [hold_initial, hold_checkpoint],
        checkpoint_step=230,
    )

    assert contrast["initial_conditions_equivalent"] is False
    assert contrast["initial_particle_comparison"]["maximum_error_m"] == pytest.approx(
        0.01
    )
    assert contrast["causality_gate_passed"] is False


def test_treatment_contrast_rejects_noncontained_initial_as_nonequivalent():
    pour_initial = _record(
        step=0,
        treatment="pour",
        position_hash="a" * 64,
        surface_hash="b" * 64,
        liquid_hash="c" * 64,
        target_count=1,
    )
    hold_initial = _record(
        step=0,
        treatment="hold",
        position_hash="d" * 64,
        surface_hash="e" * 64,
        liquid_hash="f" * 64,
        target_count=0,
    )
    pour_initial["action"]["target_pose_xyzw"] = [0.0] * 7
    hold_initial["action"]["target_pose_xyzw"] = [0.0] * 7
    pour_checkpoint = _record(
        step=230,
        treatment="pour",
        position_hash="1" * 64,
        surface_hash="2" * 64,
        liquid_hash="3" * 64,
        target_count=2701,
    )
    hold_checkpoint = _record(
        step=230,
        treatment="hold",
        position_hash="4" * 64,
        surface_hash="5" * 64,
        liquid_hash="6" * 64,
        target_count=0,
    )

    contrast = probe.compare_treatments(
        [pour_initial, pour_checkpoint],
        [hold_initial, hold_checkpoint],
        checkpoint_step=230,
    )

    assert contrast["common_initial_state_exact"] is False
    assert contrast["initial_conditions_equivalent"] is False
    assert contrast["common_initial_state"] is False
    assert contrast["causality_gate_passed"] is False


def test_write_treatment_causality_gate_is_the_only_combined_pass(tmp_path):
    pour_initial = _record(
        step=0,
        treatment="pour",
        position_hash="a" * 64,
        surface_hash="b" * 64,
        liquid_hash="c" * 64,
        target_count=0,
    )
    hold_initial = {
        **pour_initial,
        "episode_id": "hold-1",
        "treatment": "hold",
    }
    pour_checkpoint = _record(
        step=230,
        treatment="pour",
        position_hash="1" * 64,
        surface_hash="2" * 64,
        liquid_hash="3" * 64,
        target_count=2701,
    )
    hold_checkpoint = _record(
        step=230,
        treatment="hold",
        position_hash="4" * 64,
        surface_hash="5" * 64,
        liquid_hash="6" * 64,
        target_count=0,
    )
    pour_path = tmp_path / "pour.jsonl"
    hold_path = tmp_path / "hold.jsonl"
    output_path = tmp_path / "causality_gate.json"
    pour_records = [pour_initial] + [
        _record(
            step=step,
            treatment="pour",
            position_hash=f"{step:064x}",
            surface_hash=f"{step + 1:064x}",
            liquid_hash=f"{step + 2:064x}",
            target_count=0,
        )
        for step in range(1, 230)
    ] + [pour_checkpoint]
    hold_records = [hold_initial] + [
        _record(
            step=step,
            treatment="hold",
            position_hash=f"{step + 1000:064x}",
            surface_hash=f"{step + 1001:064x}",
            liquid_hash=f"{step + 1002:064x}",
            target_count=0,
        )
        for step in range(1, 230)
    ] + [hold_checkpoint]
    for path, records in (
        (pour_path, pour_records),
        (hold_path, hold_records),
    ):
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    gate = probe.write_treatment_causality_gate(
        pour_path,
        hold_path,
        output_path,
        checkpoint_step=230,
    )

    assert gate["status"] == "PASS"
    assert gate["claim"] == "online_action_to_physics_to_surface_to_pixels_causality"
    assert gate["comparison"]["causality_gate_passed"] is True
    assert gate["matched_run_identity"] is True
    assert gate["run_identity"]["source_body_mode"] == "kinematic"
    assert gate["gate_implementation"]["sha256"] == (
        probe.implementation_identity()["sha256"]
    )
    assert json.loads(output_path.read_text(encoding="utf-8")) == gate


def test_write_treatment_causality_gate_rejects_sparse_checkpoint_only_records(
    tmp_path,
):
    pour_path = tmp_path / "pour.jsonl"
    hold_path = tmp_path / "hold.jsonl"
    output_path = tmp_path / "gate.json"
    for treatment, path in (("pour", pour_path), ("hold", hold_path)):
        records = [
            _record(
                step=step,
                treatment=treatment,
                position_hash=f"{step + 1:064x}",
                surface_hash=f"{step + 2:064x}",
                liquid_hash=f"{step + 3:064x}",
                target_count=0,
            )
            for step in (0, 230)
        ]
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="gate_records_incomplete"):
        probe.write_treatment_causality_gate(
            pour_path,
            hold_path,
            output_path,
            checkpoint_step=230,
        )


@pytest.mark.parametrize(
    "field",
    [
        "position_sha256",
        "surface",
        "liquid_evidence_sha256",
        "raw_particle_counts",
    ],
)
def test_treatment_contrast_rejects_missing_divergence(field):
    initial = _record(
        step=0,
        treatment="hold",
        position_hash="a" * 64,
        surface_hash="b" * 64,
        liquid_hash="c" * 64,
        target_count=0,
    )
    pour_initial = {**initial, "episode_id": "pour-1"}
    pour = _record(
        step=230,
        treatment="pour",
        position_hash="d" * 64,
        surface_hash="e" * 64,
        liquid_hash="f" * 64,
        target_count=1400,
    )
    hold = _record(
        step=230,
        treatment="hold",
        position_hash="g" * 64,
        surface_hash="h" * 64,
        liquid_hash="i" * 64,
        target_count=0,
    )
    if field == "surface":
        hold[field] = dict(pour[field])
    elif field == "raw_particle_counts":
        hold[field] = dict(pour[field])
    else:
        hold[field] = pour[field]

    result = probe.compare_treatments(
        [pour_initial, pour],
        [initial, hold],
        checkpoint_step=230,
    )

    assert result["causality_gate_passed"] is False


def test_probe_source_has_no_offline_replay_reader_or_mesh_cache_input():
    source = inspect.getsource(probe)

    forbidden = (
        "load_selected_trace_records",
        "load_mesh_archive",
        "verify_mesh_cache",
        "kinematic_trace.jsonl",
        "mesh_cache_manifest.json",
    )
    assert all(name not in source for name in forbidden)


def test_cli_defaults_to_online_pour_and_rejects_hidden_fallbacks(monkeypatch):
    contract = probe.default_probe_contract()
    monkeypatch.setattr(
        "sys.argv",
        ["probe", "--treatment", "pour", "--out-dir", "/tmp/probe"],
    )

    args = probe.parse_args(contract)

    assert isinstance(args, argparse.Namespace)
    assert args.treatment == "pour"
    assert Path(args.out_dir) == Path("/tmp/probe")
    assert args.width == args.height == 256
    assert args.camera_profile == "validation"
    assert args.source_body_mode == "kinematic"
    assert not hasattr(args, "trace_path")
    assert not hasattr(args, "mesh_cache")


def test_cli_accepts_dynamic_hold_and_rejects_dynamic_pour(monkeypatch):
    contract = probe.default_probe_contract()
    monkeypatch.setattr(
        "sys.argv",
        [
            "probe",
            "--treatment",
            "hold",
            "--source-body-mode",
            "dynamic",
            "--out-dir",
            "/tmp/probe-dynamic",
        ],
    )

    args = probe.parse_args(contract)

    assert args.source_body_mode == "dynamic"

    monkeypatch.setattr(
        "sys.argv",
        [
            "probe",
            "--treatment",
            "pour",
            "--source-body-mode",
            "dynamic",
            "--out-dir",
            "/tmp/probe-dynamic-pour",
        ],
    )
    with pytest.raises(SystemExit):
        probe.parse_args(contract)


def test_model_camera_profile_selects_exact_inference_camera_paths(monkeypatch):
    contract = probe.default_probe_contract()
    monkeypatch.setattr(
        "sys.argv",
        [
            "probe",
            "--treatment",
            "pour",
            "--camera-profile",
            "model",
            "--out-dir",
            "/tmp/probe-model",
        ],
    )

    args = probe.parse_args(contract)

    assert args.camera_profile == "model"
    assert probe.camera_paths_for_profile(args.camera_profile) == {
        "camera_1": "/World/Camera1",
        "camera_2": "/World/Camera2",
    }

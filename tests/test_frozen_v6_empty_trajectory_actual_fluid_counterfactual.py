from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
import yaml

from tools.labutopia_fluid import (
    run_frozen_v6_empty_trajectory_actual_fluid_counterfactual as counterfactual,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_frozen_v6_empty_trajectory_actual_fluid_v1.yaml"
)
SOURCE_TRACE_PATH = (
    REPO_ROOT
    / "outputs/native_expert_empty_beaker_unbound_lift_20260720_005/"
    "instrumented/trace.jsonl"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_action(action: dict) -> str:
    return counterfactual.canonicalize_action(action)["sha256"]


def _normal_provenance() -> dict:
    payload = {
        "policy": (
            "area_weighted_face_with_oriented_density_zero_sum_fallback_v1"
        ),
        "normal_zero_sum_epsilon": 1.0e-15,
        "normal_fallback_max_fraction": 0.01,
        "normal_fallback_neighbor_alignment_min_dot": 0.5,
        "fallback_vertex_count": 0,
        "fallback_vertex_indices": [],
        "fallback_vertex_indices_sha256": counterfactual._canonical_json_sha256([]),
        "density_normals_sha256": None,
        "fallback_neighbor_alignment_min_dots": [],
        "component_count": 1,
        "component_orientation_signs": [0],
    }
    return {**payload, "sha256": counterfactual._canonical_json_sha256(payload)}


def test_normal_provenance_rejects_boolean_signs_and_impossible_alignment():
    zero_fallback = _normal_provenance()
    zero_payload = dict(zero_fallback)
    zero_payload.pop("sha256")
    zero_payload["component_orientation_signs"] = [False]
    zero_fallback = {
        **zero_payload,
        "sha256": counterfactual._canonical_json_sha256(zero_payload),
    }
    with pytest.raises(ValueError, match="counterfactual_surface_normal_provenance_invalid"):
        counterfactual._validate_live_normal_provenance(zero_fallback)

    fallback_payload = dict(zero_payload)
    fallback_payload.update(
        {
            "fallback_vertex_count": 1,
            "fallback_vertex_indices": [0],
            "fallback_vertex_indices_sha256": counterfactual._canonical_json_sha256(
                [0]
            ),
            "density_normals_sha256": "d" * 64,
            "fallback_neighbor_alignment_min_dots": [2.0],
            "component_orientation_signs": [True],
        }
    )
    fallback = {
        **fallback_payload,
        "sha256": counterfactual._canonical_json_sha256(fallback_payload),
    }
    with pytest.raises(ValueError, match="counterfactual_surface_normal_provenance_invalid"):
        counterfactual._validate_live_normal_provenance(fallback)


def _trace_record(
    index: int,
    *,
    action=None,
    apply_index=None,
    pick_event=None,
    pour_event=None,
):
    receipt = None
    if action is not None:
        receipt = {
            "applied": True,
            "normal_return": True,
            "apply_count": 1,
            "action_sha256": _canonical_action(action),
        }
    return {
        "kind": "transition",
        "manifest_type": counterfactual.SOURCE_TRACE_MANIFEST_TYPE,
        "payload": {
            "transition_index": index,
            "action": action,
            "canonical_action": (
                None if action is None else counterfactual.canonicalize_action(action)
            ),
            "action_receipt": receipt,
            "apply_count": 0 if action is None else 1,
            "apply_index": apply_index,
            "integrating_transition_index": (
                None if action is None else index + 1
            ),
            "pick_event": pick_event,
            "pour_event": pour_event,
            "production_terminal": False,
        },
    }


def _write_trace(path: Path, records: list[dict]) -> str:
    bootstrap = {
        "kind": "bootstrap",
        "manifest_type": counterfactual.SOURCE_TRACE_MANIFEST_TYPE,
        "payload": {
            "runtime_evidence": {
                "protocol": {
                    "protocol_id": counterfactual.SOURCE_PROTOCOL_ID,
                    "schema_version": 6,
                },
                "child_static_identity_post": {
                    "config_sha256": counterfactual.SOURCE_CONFIG_SHA256,
                },
            }
        },
    }
    path.write_text(
        "\n".join(json.dumps(value, sort_keys=True) for value in [bootstrap, *records])
        + "\n",
        encoding="utf-8",
    )
    return _sha256(path)


def _counterfactual_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _valid_video_frame_map() -> dict:
    ledger = counterfactual.load_frozen_action_ledger(
        SOURCE_TRACE_PATH,
        expected_sha256=counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
    )
    frames = []
    for index, source_index in enumerate([None, *range(1, 864, 2)]):
        source = None if source_index is None else ledger["transitions"][source_index]
        integrated = (
            None
            if source_index is None
            else ledger["transitions"][source_index - 1]
        )
        frames.append(
            {
                "frame_index": index,
                "observation_index": index * 2,
                "frame_identity": f"{index:064x}",
                "particle_position_sha256": "b" * 64,
                "source_transition_index": source_index,
                "source_action_sha256": (
                    None if source is None else source["action_sha256"]
                ),
                "source_transition_processed_after_observation": (
                    source_index is not None
                ),
                "integrated_source_transition_index": (
                    None
                    if integrated is None
                    else integrated["source_transition_index"]
                ),
                "integrated_source_action_sha256": (
                    None if integrated is None else integrated["action_sha256"]
                ),
                "replay_elapsed_seconds": (
                    0.0
                    if source_index is None
                    else (source_index + 1) / 60.0
                ),
                "surface_normal_provenance": _normal_provenance(),
                "surface_geometry_sha256": "c" * 64,
                "render_token": f"{index + 1000:064x}",
                "integration_step_after": index * 20,
                "logical_step_after": index * 2,
            }
        )
    return {
        "schema_version": 1,
        "manifest_type": counterfactual.MANIFEST_TYPE,
        "forced_status": counterfactual.FORCED_STATUS,
        "source_trace_sha256": counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
        "video": counterfactual.VIDEO_BASENAME,
        "fps": 30,
        "sampling_policy": counterfactual.VIDEO_SAMPLING_POLICY,
        "frame_count": len(frames),
        "frames": frames,
    }


def _valid_hd_presentation_binding_map(video_frame_map: dict) -> dict:
    return {
        "schema_version": 1,
        "manifest_type": counterfactual.MANIFEST_TYPE,
        "forced_status": counterfactual.FORCED_STATUS,
        "capture_policy": counterfactual.HD_PRESENTATION_CAPTURE_POLICY,
        "frame_count": video_frame_map["frame_count"],
        "frames": [
            {
                "frame_index": frame["frame_index"],
                "source_transition_index": frame["source_transition_index"],
                "observation_index": frame["observation_index"],
                "frame_identity": frame["frame_identity"],
                "render_token": frame["render_token"],
                "integration_step_after": frame["integration_step_after"],
                "logical_step_after": frame["logical_step_after"],
                "camera_frame_ordinals": {
                    "camera_1": frame["frame_index"],
                    "camera_2": frame["frame_index"],
                },
            }
            for frame in video_frame_map["frames"]
        ],
    }


def _valid_hd_presentation_manifest_and_records(binding_map: dict):
    frames = binding_map["frames"]
    attempt_id = "attempt-00000000"
    episode_id = "unsafe-visual-only-counterfactual-0000"
    manifest = {
        "schema_version": 1,
        "capture_policy": counterfactual.HD_PRESENTATION_CAPTURE_POLICY,
        "attempts": [
            {
                "attempt_id": attempt_id,
                "episode_id": episode_id,
                "status": "rejected",
                "frame_count": len(frames),
                "observation_index_range": [
                    frames[0]["observation_index"],
                    frames[-1]["observation_index"],
                ],
                "videos": [
                    {
                        "name": name,
                        "source_prim_path": source_prim_path,
                        "prim_path": (
                            "/World/LabUtopiaPresentationCameras/" + name
                        ),
                        "resolution": [1280, 720],
                        "fps": 30.0,
                        "path": (
                            f"{attempt_id}_{episode_id}_{name}_720p.mp4"
                        ),
                    }
                    for name, source_prim_path in (
                        ("camera_1", "/World/InternDataParityCamera"),
                        ("camera_2", "/World/InternDataParityCloseupCamera"),
                    )
                ],
            }
        ],
    }
    records = [
        {
            "attempt_id": attempt_id,
            "episode_id": episode_id,
            "observation_index": frame["observation_index"],
            "frame_identity": frame["frame_identity"],
            "integration_step_after": frame["integration_step_after"],
            "logical_step_after": frame["logical_step_after"],
            "render_token": frame["render_token"],
            "physics_and_timeline_unchanged": True,
            "presentation_render": {
                "physics_and_timeline_unchanged": True,
                "world_physics_unchanged": True,
                "time_before": 1.0,
                "time_after": 1.0,
                "step_before": 2,
                "step_after": 2,
                "timeline_time_before": 1.0,
                "timeline_time_after": 1.0,
                "timeline_playing_before": True,
                "timeline_playing_after": True,
                "timeline_auto_update_before": True,
                "timeline_auto_update_after": True,
                "timeline_auto_update_disabled_for_capture": True,
                "omni_timeline_unchanged": True,
                "render_count": 6,
            },
            "cameras": {
                "camera_1": {"rendering_frame": 3, "rendering_time": 1.0},
                "camera_2": {"rendering_frame": 6, "rendering_time": 1.0},
            },
        }
        for frame in frames
    ]
    return manifest, records


def test_action_ledger_requires_a_hash_pinned_v6_trace_and_receipts(tmp_path):
    open_action = {
        "joint_positions": [None, None, None, None, None, None, None, 0.04, 0.04],
        "joint_velocities": None,
        "joint_efforts": None,
    }
    lift_action = {
        "joint_positions": [0.1] * 7,
        "joint_velocities": None,
        "joint_efforts": None,
    }
    pour_action = {
        "joint_positions": None,
        "joint_velocities": [None, None, None, None, None, None, -1.0],
        "joint_efforts": None,
    }
    trace_path = tmp_path / "trace.jsonl"
    digest = _write_trace(
        trace_path,
        [
            _trace_record(0),
            _trace_record(1, action=open_action, apply_index=0, pick_event=4),
            _trace_record(2, action=lift_action, apply_index=1, pick_event=5),
            _trace_record(3, action=pour_action, apply_index=2, pour_event=2),
            _trace_record(4),
        ],
    )

    ledger = counterfactual.load_frozen_action_ledger(
        trace_path,
        expected_sha256=digest,
    )

    assert ledger["source_trace_sha256"] == digest
    assert ledger["transition_count"] == 5
    assert ledger["action_count"] == 3
    assert ledger["actions"][0]["source_transition_index"] == 1
    assert ledger["actions"][0]["action_sha256"] == _canonical_action(open_action)
    assert ledger["actions"][1]["pick_event"] == 5

    tampered = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[2])
    tampered["payload"]["action_receipt"]["action_sha256"] = "0" * 64
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    lines[2] = json.dumps(tampered, sort_keys=True)
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="counterfactual_source_action_receipt_invalid"):
        counterfactual.load_frozen_action_ledger(
            trace_path,
            expected_sha256=_sha256(trace_path),
        )


def test_replay_state_preserves_source_semantics_without_claiming_a_grasp():
    state = counterfactual.FrozenReplayState()
    assert state.online_fluid_grasp_contact_requested() is False
    assert state.online_fluid_grasp_lift_requested() is False

    state.advance({"pick_event": 4, "pour_event": None})
    assert state.online_fluid_grasp_contact_requested() is True
    assert state.online_fluid_grasp_lift_requested() is False

    state.advance({"pick_event": 5, "pour_event": None})
    assert state.online_fluid_grasp_contact_requested() is True
    assert state.online_fluid_grasp_lift_requested() is True
    assert state.online_fluid_grasp_attachment_requested() is False

    state.advance({"pick_event": None, "pour_event": 2})
    assert state.pour_rotation_requested() is True
    assert state.snapshot()["contact_grasp_claimed"] is False


def test_runtime_installs_legacy_aliases_before_legacy_isaac_imports():
    tree = ast.parse(Path(counterfactual.__file__).read_text(encoding="utf-8"))
    runtime = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_measure_runtime"
    )
    installer_import_index = next(
        index
        for index, statement in enumerate(runtime.body)
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "isaacsim_compat"
        and any(alias.name == "install_legacy_isaacsim_aliases" for alias in statement.names)
    )
    installer_call_index = next(
        index
        for index, statement in enumerate(runtime.body)
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "install_legacy_isaacsim_aliases"
    )
    isaac_import_indices = []
    for index, statement in enumerate(runtime.body):
        if isinstance(statement, ast.Import):
            names = (alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom):
            names = (statement.module or "",)
        else:
            continue
        if any(
            name.startswith(("isaacsim.core", "omni"))
            for name in names
        ):
            isaac_import_indices.append(index)

    assert installer_import_index < installer_call_index
    assert isaac_import_indices
    assert installer_call_index < min(isaac_import_indices)


def test_frozen_v6_action_representation_contract_is_exact_and_fail_closed():
    ledger = counterfactual.load_frozen_action_ledger(
        SOURCE_TRACE_PATH,
        expected_sha256=counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
    )

    contract = counterfactual.build_frozen_v6_action_representation_contract(ledger)

    assert contract["public"]["schema"] == (
        "frozen_v6_action_representation_adapter_v1"
    )
    assert contract["public"]["layout_counts"] == {
        "arm_position_velocity_7": 412,
        "full_position_9": 70,
        "full_velocity_9": 376,
    }
    assert contract["public"]["velocity_mode_transition"] == {
        "dof_index": 6,
        "mode": "velocity",
        "source_transition_index": 487,
    }
    assert len(contract["effective_action_hashes"]) == 858
    assert len(contract["expected_velocity_mode_switch_receipts"]) == 1

    arm_layout = counterfactual.resolve_frozen_v6_action_layout(
        {
            "joint_positions": [0.1] * 7,
            "joint_velocities": [0.2] * 7,
            "joint_efforts": None,
        }
    )
    assert arm_layout["name"] == "arm_position_velocity_7"
    assert arm_layout["joint_indices"] == list(range(7))

    full_position_layout = counterfactual.resolve_frozen_v6_action_layout(
        {
            "joint_positions": [None] * 9,
            "joint_velocities": None,
            "joint_efforts": None,
        }
    )
    assert full_position_layout["name"] == "full_position_9"
    assert full_position_layout["joint_indices"] is None

    full_velocity_layout = counterfactual.resolve_frozen_v6_action_layout(
        {
            "joint_positions": None,
            "joint_velocities": [None] * 6 + [-1.0] + [None] * 2,
            "joint_efforts": None,
        }
    )
    assert full_velocity_layout["name"] == "full_velocity_9"
    assert full_velocity_layout["joint_indices"] is None

    with pytest.raises(ValueError, match="counterfactual_action_layout_invalid"):
        counterfactual.resolve_frozen_v6_action_layout(
            {
                "joint_positions": [0.1] * 7,
                "joint_velocities": None,
                "joint_efforts": None,
            }
        )
    with pytest.raises(ValueError, match="counterfactual_action_layout_invalid"):
        counterfactual.resolve_frozen_v6_action_layout(
            {
                "joint_positions": [0.1] * 7,
                "joint_velocities": [0.2] * 9,
                "joint_efforts": None,
            }
        )


def test_live_replay_robot_identity_requires_the_pinned_franka_mapping():
    identity = counterfactual.validate_live_replay_robot_identity(
        dof_names=counterfactual.FRANKA_DOF_NAMES,
        joint_positions=[0.0] * 9,
        finger_joint_indices=(7, 8),
        task_robot_matches=True,
        robot_usd_path=(counterfactual.REPO_ROOT / "assets/robots/Franka.usd"),
        robot_usd_sha256=counterfactual.EXPECTED_ROBOT_USD_SHA256,
    )

    assert identity["valid"] is True
    assert identity["dof_names"] == list(counterfactual.FRANKA_DOF_NAMES)
    assert identity["finger_joint_indices"] == [7, 8]

    with pytest.raises(ValueError, match="counterfactual_live_robot_identity_invalid"):
        counterfactual.validate_live_replay_robot_identity(
            dof_names=tuple(reversed(counterfactual.FRANKA_DOF_NAMES)),
            joint_positions=[0.0] * 9,
            finger_joint_indices=(7, 8),
            task_robot_matches=True,
            robot_usd_path=(counterfactual.REPO_ROOT / "assets/robots/Franka.usd"),
            robot_usd_sha256=counterfactual.EXPECTED_ROBOT_USD_SHA256,
        )


def test_live_replay_robot_stage_binding_requires_the_pinned_composed_layer():
    class Layer:
        def __init__(self, path):
            self.realPath = str(path)

    class Spec:
        def __init__(self, path):
            self.layer = Layer(path)

    class Prim:
        def __init__(self, paths):
            self._paths = paths

        def IsValid(self):
            return True

        def GetPrimStack(self):
            return [Spec(path) for path in self._paths]

    class Stage:
        def __init__(self, paths):
            self._prim = Prim(paths)

        def GetPrimAtPath(self, path):
            assert path == "/World/Franka"
            return self._prim

    pinned_path = counterfactual.REPO_ROOT / "assets/robots/Franka.usd"
    binding = counterfactual.build_live_replay_robot_stage_binding(
        Stage([pinned_path])
    )

    assert binding["valid"] is True
    assert binding["pinned_root_layer_found"] is True
    counterfactual.validate_live_replay_robot_stage_binding_evidence(binding)

    with pytest.raises(ValueError, match="counterfactual_live_robot_stage_binding_invalid"):
        counterfactual.build_live_replay_robot_stage_binding(
            Stage([counterfactual.REPO_ROOT / "config/level1_pour.yaml"])
        )


def test_velocity_mode_gain_readback_requires_only_dof_six_to_change():
    before_stiffness = np.asarray([10.0] * 9)
    before_damping = np.asarray([2.0] * 9)
    after_stiffness = before_stiffness.copy()
    after_stiffness[6] = 0.0
    after_damping = before_damping.copy()

    evidence = counterfactual.build_velocity_mode_gain_readback(
        before_stiffness=before_stiffness,
        before_damping=before_damping,
        after_stiffness=after_stiffness,
        after_damping=after_damping,
    )

    assert evidence["valid"] is True
    assert evidence["post_switch_dof_stiffness"] == 0.0
    counterfactual.validate_velocity_mode_gain_readback(evidence)

    tampered = dict(evidence, post_switch_dof_stiffness=1.0)
    with pytest.raises(ValueError, match="counterfactual_velocity_mode_readback_invalid"):
        counterfactual.validate_velocity_mode_gain_readback(tampered)


def test_articulation_action_rehydrates_the_pinned_arm_indices(monkeypatch):
    class StubArticulationAction:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    isaacsim = ModuleType("isaacsim")
    core = ModuleType("isaacsim.core")
    utils = ModuleType("isaacsim.core.utils")
    types = ModuleType("isaacsim.core.utils.types")
    types.ArticulationAction = StubArticulationAction
    isaacsim.core = core
    core.utils = utils
    utils.types = types
    for name, module in (
        ("isaacsim", isaacsim),
        ("isaacsim.core", core),
        ("isaacsim.core.utils", utils),
        ("isaacsim.core.utils.types", types),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    arm = counterfactual._articulation_action_from_raw(
        {
            "joint_positions": [0.1] * 7,
            "joint_velocities": [0.2] * 7,
            "joint_efforts": None,
        }
    )
    full_velocity = counterfactual._articulation_action_from_raw(
        {
            "joint_positions": None,
            "joint_velocities": [None] * 6 + [-1.0] + [None] * 2,
            "joint_efforts": None,
        }
    )

    assert arm.kwargs["joint_indices"].tolist() == list(range(7))
    assert arm.kwargs["joint_positions"] == [0.1] * 7
    assert arm.kwargs["joint_velocities"] == [0.2] * 7
    assert full_velocity.kwargs["joint_indices"] is None
    assert full_velocity.kwargs["joint_velocities"] == [
        None,
        None,
        None,
        None,
        None,
        None,
        -1.0,
        None,
        None,
    ]


def test_counterfactual_config_is_diagnostic_and_pins_action_cadence():
    cfg = _counterfactual_config()

    contract = counterfactual.validate_counterfactual_config(
        cfg,
        config_path=CONFIG_PATH,
    )

    fluid = cfg["online_fluid"]
    assert contract["valid"] is True
    assert cfg["controller_type"] == "frozen_v6_counterfactual_replay"
    assert fluid["source_ownership"] == "contact_friction_dynamic_v1"
    assert fluid["source_pose_authority"] == "physx_dynamic_readback_v1"
    assert fluid["physics_dt"] == pytest.approx(1 / 600)
    assert fluid["rendering_dt"] == pytest.approx(1 / 60)
    assert fluid["physics_substeps_per_observation"] == 10
    assert cfg["counterfactual"]["video_fps"] == 30
    assert cfg["counterfactual"]["video_sample_every_transitions"] == 2
    assert cfg["counterfactual"]["forced_status"] == (
        "REJECTED_UNSAFE_VISUAL_ONLY"
    )
    assert cfg["counterfactual"]["trajectory_claim"] == (
        "exact_v6_serialized_action_channel_replay_with_pinned_representation_adapter"
    )
    assert cfg["counterfactual"]["action_representation_adapter"]["schema"] == (
        "frozen_v6_action_representation_adapter_v1"
    )
    assert cfg["counterfactual"]["action_representation_adapter"][
        "velocity_mode_transition"
    ]["source_transition_index"] == 487
    assert cfg["counterfactual"]["video_sampling_policy"] == (
        "initial_t0_then_odd_source_transitions_cfr30"
    )
    assert cfg["counterfactual"]["scene_equivalence_claim_allowed"] is False
    assert cfg["counterfactual"]["source_trace_sha256"] == _sha256(
        SOURCE_TRACE_PATH
    )


def test_hd_presentation_contract_is_opt_in_and_reuses_only_the_pinned_cameras(
    tmp_path,
):
    contract = counterfactual.build_hd_presentation_contract(
        _counterfactual_config()
    )

    assert contract["schema"] == "frozen_v6_counterfactual_hd_presentation_v1"
    assert contract["capture_policy"] == (
        "viewport_same_observation_no_physics_step_v1"
    )
    assert contract["resolution"] == [1280, 720]
    assert contract["fps"] == 30
    assert contract["camera_names"] == ["camera_1", "camera_2"]
    assert contract["source_prim_paths"] == {
        "camera_1": "/World/InternDataParityCamera",
        "camera_2": "/World/InternDataParityCloseupCamera",
    }
    assert "REJECTED - UNSAFE VISUAL-ONLY" in contract["banner_lines"][0]

    args = counterfactual.parse_args(
        [
            "--out-dir",
            str(tmp_path / "hd-output"),
            "--capture-hd-presentation",
        ]
    )
    command = counterfactual._child_command(args)
    assert "--capture-hd-presentation" in command


def test_hd_presentation_binding_and_recorder_evidence_are_exact_and_fail_closed():
    ledger = counterfactual.load_frozen_action_ledger(
        SOURCE_TRACE_PATH,
        expected_sha256=counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
    )
    video_frame_map = _valid_video_frame_map()
    assert counterfactual._validate_video_frame_map(
        video_frame_map,
        ledger=ledger,
    ) == 433
    binding_map = _valid_hd_presentation_binding_map(video_frame_map)
    assert counterfactual.validate_hd_presentation_binding_map(
        binding_map,
        video_frame_map=video_frame_map,
    ) == 433

    manifest, records = _valid_hd_presentation_manifest_and_records(binding_map)
    validated = counterfactual.validate_hd_presentation_recorder_evidence(
        manifest,
        records,
        binding_map=binding_map,
    )
    assert validated["attempt_id"] == "attempt-00000000"
    assert validated["frame_count"] == 433

    delayed_callback = copy.deepcopy(records)
    delayed_callback[17]["presentation_render"]["render_count"] = 7
    assert counterfactual.validate_hd_presentation_recorder_evidence(
        manifest,
        delayed_callback,
        binding_map=binding_map,
    )["frame_count"] == 433

    reordered = copy.deepcopy(binding_map)
    reordered["frames"][1], reordered["frames"][2] = (
        reordered["frames"][2],
        reordered["frames"][1],
    )
    with pytest.raises(ValueError, match="counterfactual_hd_presentation_binding_invalid"):
        counterfactual.validate_hd_presentation_binding_map(
            reordered,
            video_frame_map=video_frame_map,
        )

    changed_timeline = copy.deepcopy(records)
    changed_timeline[17]["presentation_render"]["timeline_time_after"] = 1.1
    with pytest.raises(ValueError, match="counterfactual_hd_presentation_recorder_invalid"):
        counterfactual.validate_hd_presentation_recorder_evidence(
            manifest,
            changed_timeline,
            binding_map=binding_map,
        )

    too_many_renders = copy.deepcopy(records)
    too_many_renders[17]["presentation_render"]["render_count"] = 21
    with pytest.raises(ValueError, match="counterfactual_hd_presentation_recorder_invalid"):
        counterfactual.validate_hd_presentation_recorder_evidence(
            manifest,
            too_many_renders,
            binding_map=binding_map,
        )


def test_hd_presentation_encoder_command_is_create_only_h264_and_watermarked(
    tmp_path,
):
    command = counterfactual.build_hd_presentation_ffmpeg_command(
        raw_path=tmp_path / "raw.mp4",
        output_path=tmp_path / "final.mp4",
    )

    assert command[:2] == ["ffmpeg", "-n"]
    assert command[command.index("-c:v") : command.index("-c:v") + 2] == [
        "-c:v",
        "libx264",
    ]
    assert command[command.index("-pix_fmt") : command.index("-pix_fmt") + 2] == [
        "-pix_fmt",
        "yuv420p",
    ]
    assert command[command.index("-movflags") : command.index("-movflags") + 2] == [
        "-movflags",
        "+faststart",
    ]
    video_filter = command[command.index("-vf") + 1]
    assert "drawbox" in video_filter
    assert "drawtext" in video_filter
    assert "REJECTED - UNSAFE VISUAL-ONLY" in video_filter
    assert "NOT GRASP\\, TRANSFER\\, OR SUCCESS EVIDENCE" in video_filter


def test_runtime_error_denies_all_collection_and_presentation_claims():
    report = counterfactual._runtime_error_report(
        RuntimeError("capture failed"),
        run_nonce="a" * 32,
        config_sha256="b" * 64,
        phase="hd_presentation",
        hd_presentation_requested=True,
    )

    assert report["success"] is False
    assert report["expert_episode_accepted"] is False
    assert report["collector_write_allowed"] is False
    assert report["ebench_finalize_allowed"] is False
    assert report["hd_presentation"]["capture_status"] == "failed"


def test_pinned_v6_source_trace_has_the_declared_full_action_schedule():
    ledger = counterfactual.load_frozen_action_ledger(
        SOURCE_TRACE_PATH,
        expected_sha256=counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
    )

    assert ledger["transition_count"] == 864
    assert ledger["action_count"] == 858
    assert ledger["actions"][0]["source_transition_index"] == 4
    assert ledger["actions"][0]["action"]["joint_positions"][-2:] == [0.04, 0.04]
    assert any(action["pick_event"] == 4 for action in ledger["actions"])
    assert any(action["pick_event"] == 5 for action in ledger["actions"])
    assert any(action["pour_event"] == 2 for action in ledger["actions"])


def test_replay_intervals_integrate_each_source_action_one_transition_later(
    tmp_path,
):
    action = {
        "joint_positions": [0.1] * 7,
        "joint_velocities": None,
        "joint_efforts": None,
    }
    pour_action = {
        "joint_positions": None,
        "joint_velocities": [None, None, None, None, None, None, -1.0],
        "joint_efforts": None,
    }
    trace_path = tmp_path / "trace.jsonl"
    digest = _write_trace(
        trace_path,
        [
            _trace_record(0),
            _trace_record(1, action=action, apply_index=0, pick_event=4),
            _trace_record(2, action=action, apply_index=1, pick_event=5),
            _trace_record(3, action=pour_action, apply_index=2, pour_event=2),
            _trace_record(4),
        ],
    )
    ledger = counterfactual.load_frozen_action_ledger(
        trace_path,
        expected_sha256=digest,
    )

    intervals = counterfactual.build_replay_intervals(ledger)

    assert intervals[0]["integrated_source_transition"] is None
    assert intervals[1]["integrated_source_transition"]["action"] is None
    assert intervals[2]["integrated_source_transition"][
        "source_transition_index"
    ] == 1
    assert intervals[3]["integrated_source_transition"][
        "source_transition_index"
    ] == 2
    assert intervals[4]["integrated_source_transition"][
        "source_transition_index"
    ] == 3


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        (("controller_type",), "pour", "counterfactual_controller_type_invalid"),
        (
            ("online_fluid", "physics_substeps_per_observation"),
            20,
            "counterfactual_action_cadence_invalid",
        ),
        (
            ("counterfactual", "forced_status"),
            "accepted",
            "counterfactual_forced_status_invalid",
        ),
        (
            ("online_fluid", "source_ownership"),
            "gripper_attached_kinematic_vessel",
            "counterfactual_dynamic_source_contract_invalid",
        ),
        (
            (
                "counterfactual",
                "action_representation_adapter",
                "velocity_mode_transition",
                "dof_index",
            ),
            5,
            "counterfactual_action_adapter_config_invalid",
        ),
    ],
)
def test_counterfactual_config_rejects_any_production_or_timing_escape(
    path,
    value,
    error,
):
    cfg = copy.deepcopy(_counterfactual_config())
    target = cfg
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=error):
        counterfactual.validate_counterfactual_config(cfg, config_path=CONFIG_PATH)


def test_terminal_contract_is_unconditionally_rejected_and_requires_no_source_writes():
    ledger = {
        "source_trace_sha256": "a" * 64,
        "transition_count": 3,
        "action_count": 2,
        "actions": [{"action_sha256": "b" * 64}, {"action_sha256": "c" * 64}],
    }
    attachment = {
        "mode": "contact_friction_dynamic_v1",
        "source_dynamic": True,
        "mechanical_attachment_used": False,
        "source_pose_write_count_after_play": 0,
        "source_velocity_write_count_after_play": 0,
        "object_utils_source_position_write_count_after_play": 0,
        "kinematic_target_update_count": 0,
        "failure_reason": "source_translation_exceeded_before_contact",
        "source_writer_audit": {"valid": True},
    }
    effective_hashes = ["d" * 64, "e" * 64]
    velocity_mode_receipt = {
        "schema": "frozen_v6_action_representation_adapter_v1",
        "source_transition_index": 487,
        "dof_index": 6,
        "mode": "velocity",
        "applied": True,
        "normal_return": True,
    }
    velocity_mode_receipt["sha256"] = counterfactual._canonical_json_sha256(
        velocity_mode_receipt
    )
    gain_readback = counterfactual.build_velocity_mode_gain_readback(
        before_stiffness=[10.0] * 9,
        before_damping=[2.0] * 9,
        after_stiffness=[10.0] * 6 + [0.0] + [10.0] * 2,
        after_damping=[2.0] * 9,
    )

    result = counterfactual.build_terminal_contract(
        ledger=ledger,
        applied_action_hashes=["b" * 64, "c" * 64],
        applied_effective_action_hashes=effective_hashes,
        expected_effective_action_hashes=effective_hashes,
        applied_velocity_mode_switch_receipts=[velocity_mode_receipt],
        expected_velocity_mode_switch_receipts=[velocity_mode_receipt],
        velocity_mode_gain_readbacks=[gain_readback],
        attachment=attachment,
        particle_readback_observation_count=3,
    )

    assert result["status"] == "REJECTED_UNSAFE_VISUAL_ONLY"
    assert result["success"] is False
    assert result["expert_episode_accepted"] is False
    assert result["collector_write_allowed"] is False
    assert result["ebench_finalize_allowed"] is False
    assert result["integrity_valid"] is True
    assert result["integrity_checks"]["all_effective_actions_applied_exactly_once"]
    assert result["integrity_checks"]["velocity_mode_transition_applied_exactly_once"]
    assert result["integrity_checks"]["velocity_mode_readback_verified"]
    assert result["first_latched_failure_reason"] == (
        "source_translation_exceeded_before_contact"
    )
    assert "raw USD attribute writes" in result["source_write_evidence_scope"]

    unsafe_attachment = dict(attachment, source_pose_write_count_after_play=1)
    result = counterfactual.build_terminal_contract(
        ledger=ledger,
        applied_action_hashes=["b" * 64, "c" * 64],
        applied_effective_action_hashes=effective_hashes,
        expected_effective_action_hashes=effective_hashes,
        applied_velocity_mode_switch_receipts=[velocity_mode_receipt],
        expected_velocity_mode_switch_receipts=[velocity_mode_receipt],
        velocity_mode_gain_readbacks=[gain_readback],
        attachment=unsafe_attachment,
        particle_readback_observation_count=3,
    )
    assert result["status"] == "COUNTERFACTUAL_RUNTIME_INTEGRITY_FAILURE"
    assert result["success"] is False
    assert result["integrity_checks"]["zero_source_writes"] is False


def test_video_frame_map_requires_the_exact_30_hz_transition_schedule():
    ledger = counterfactual.load_frozen_action_ledger(
        SOURCE_TRACE_PATH,
        expected_sha256=counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
    )
    source_indices = [None, *range(1, 864, 2)]
    frames = []
    for index, source_index in enumerate(source_indices):
        source = None if source_index is None else ledger["transitions"][source_index]
        integrated_index = (
            None
            if source_index is None or source_index == 0
            else source_index - 1
        )
        integrated = (
            None
            if integrated_index is None
            else ledger["transitions"][integrated_index]
        )
        frames.append(
            {
                "frame_index": index,
                "source_transition_index": source_index,
                "source_transition_processed_after_observation": (
                    source_index is not None
                ),
                "integrated_source_transition_index": integrated_index,
                "source_action_sha256": (
                    None if source is None else source["action_sha256"]
                ),
                "integrated_source_action_sha256": (
                    None if integrated is None else integrated["action_sha256"]
                ),
                "replay_elapsed_seconds": (
                    0.0
                    if source_index is None
                    else (source_index + 1) / 60.0
                ),
                "surface_normal_provenance": _normal_provenance(),
                "surface_geometry_sha256": "c" * 64,
                "frame_identity": "a" * 64,
                "particle_position_sha256": "b" * 64,
            }
        )
    payload = {
        "manifest_type": counterfactual.MANIFEST_TYPE,
        "forced_status": counterfactual.FORCED_STATUS,
        "source_trace_sha256": counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
        "fps": 30,
        "sampling_policy": "initial_t0_then_odd_source_transitions_cfr30",
        "frame_count": len(frames),
        "frames": frames,
    }

    assert counterfactual._validate_video_frame_map(payload, ledger=ledger) == 433

    tampered = copy.deepcopy(payload)
    tampered["frames"][3]["source_action_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="counterfactual_video_map_invalid"):
        counterfactual._validate_video_frame_map(tampered, ledger=ledger)


def test_observation_trace_binds_terminal_integrity_inputs(tmp_path):
    ledger = counterfactual.load_frozen_action_ledger(
        SOURCE_TRACE_PATH,
        expected_sha256=counterfactual.EXPECTED_SOURCE_TRACE_SHA256,
    )
    adapter = counterfactual.build_frozen_v6_action_representation_contract(ledger)
    gain_readback = counterfactual.build_velocity_mode_gain_readback(
        before_stiffness=[10.0] * 9,
        before_damping=[2.0] * 9,
        after_stiffness=[10.0] * 6 + [0.0] + [10.0] * 2,
        after_damping=[2.0] * 9,
    )
    attachment = {
        "mode": "contact_friction_dynamic_v1",
        "source_dynamic": True,
        "mechanical_attachment_used": False,
        "source_pose_write_count_after_play": 0,
        "source_velocity_write_count_after_play": 0,
        "object_utils_source_position_write_count_after_play": 0,
        "kinematic_target_update_count": 0,
        "failure_reason": "source_translation_exceeded_before_contact",
        "source_writer_audit": {"valid": True},
    }
    records = [
        {
            "kind": "initial_observation",
            "observation_index": 0,
            "frame_identity": "a" * 64,
            "particle_position_sha256": "b" * 64,
            "surface_normal_provenance": _normal_provenance(),
            "surface_geometry_sha256": "c" * 64,
        }
    ]
    for index, source in enumerate(ledger["transitions"]):
        integrated = None if index == 0 else ledger["transitions"][index - 1]
        effective = counterfactual._effective_action_receipt(source)
        mode_receipt = counterfactual._velocity_mode_switch_receipt(effective)
        records.append(
            {
                "kind": "replayed_transition",
                "source_transition_index": index,
                "source_apply_index": source["source_apply_index"],
                "source_action_sha256": source["action_sha256"],
                "integrated_source_transition_index": (
                    None
                    if integrated is None
                    else integrated["source_transition_index"]
                ),
                "integrated_source_action_sha256": (
                    None if integrated is None else integrated["action_sha256"]
                ),
                "source_pick_event": source["pick_event"],
                "source_pour_event": source["pour_event"],
                "source_terminal": source["source_terminal"],
                "source_transition_processed_after_observation": True,
                "effective_action_receipt": effective,
                "velocity_mode_switch_receipt": mode_receipt,
                "velocity_mode_gain_readback": (
                    gain_readback if mode_receipt is not None else None
                ),
                "observation_index": index + 1,
                "frame_identity": "a" * 64,
                "particle_position_sha256": "b" * 64,
                "surface_normal_provenance": _normal_provenance(),
                "surface_geometry_sha256": "c" * 64,
            }
        )
    records.append(
        {
            "kind": "terminal_evidence",
            "attachment": attachment,
            "observation_count": len(ledger["transitions"]) + 1,
            "applied_action_hashes": [
                action["action_sha256"] for action in ledger["actions"]
            ],
            "applied_effective_action_hashes": adapter["effective_action_hashes"],
            "applied_velocity_mode_switch_receipts": adapter[
                "expected_velocity_mode_switch_receipts"
            ],
            "velocity_mode_gain_readbacks": [gain_readback],
        }
    )
    trace_path = tmp_path / "counterfactual_observations.jsonl"
    trace_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )

    evidence = counterfactual._validate_observation_trace(
        trace_path,
        ledger=ledger,
        frame_map={
            "frames": [
                {
                    "source_transition_index": None,
                    "observation_index": 0,
                    "frame_identity": "a" * 64,
                    "particle_position_sha256": "b" * 64,
                    "surface_normal_provenance": _normal_provenance(),
                    "surface_geometry_sha256": "c" * 64,
                },
                {
                    "source_transition_index": 1,
                    "observation_index": 2,
                    "frame_identity": "a" * 64,
                    "particle_position_sha256": "b" * 64,
                    "surface_normal_provenance": _normal_provenance(),
                    "surface_geometry_sha256": "c" * 64,
                }
            ]
        },
    )

    assert evidence["attachment"] == attachment

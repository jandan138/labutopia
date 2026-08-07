from __future__ import annotations

from pathlib import Path

import pytest

from tools.labutopia_fluid import run_nonformal_full_pbd_demo as demo


def _episode() -> dict:
    return {
        "acceptance_mode": "nonformal_full_pbd_demo_v1",
        "nonformal_demo": True,
        "expert_episode_accepted": False,
        "controller_completed": True,
        "cumulative_containment_valid": True,
        "final_particle_counts": {
            "tabletop_spill": 0,
            "below_table": 0,
            "nonfinite": 0,
        },
        "control": {
            "mode": "collect",
            "expert_control_profile": "native_expert_v1",
            "execution_mode": "nonformal_full_pbd_demo_v1",
            "source_ownership": "contact_friction_dynamic_v1",
            "pour_forward_invocation_count": 1,
        },
        "attachment": {
            "mode": "contact_friction_dynamic_v1",
            "source_dynamic": True,
            "mechanical_attachment_used": False,
            "kinematic_target_update_count": 0,
            "source_pose_write_count_after_play": 0,
            "qualified": True,
            "probe_qualified_now": True,
            "contact_sensor_ready": True,
            "failure_reason": None,
            "source_writer_audit": {
                "coverage_complete": True,
                "valid": True,
                "call_count": 0,
            },
        },
    }


def test_child_command_uses_the_formal_interpreter_and_explicit_artifact_paths(
    tmp_path,
):
    command = demo.build_child_command(
        config_path=demo.DEFAULT_CONFIG,
        out_dir=tmp_path,
        max_observations=123,
    )

    assert command[:3] == [str(demo.FORMAL_ISAAC41_PYTHON), "-I", "-B"]
    assert command[3] == str(demo.MAIN_PATH)
    assert "--no-video" not in command
    assert str(tmp_path / "online_fluid_evidence") in command
    assert str(tmp_path / "video") in command
    assert command[-1] == "123"


def test_demo_episode_requires_dynamic_no_attachment_evidence():
    episode = _episode()

    assert demo.validate_demo_episode(episode) == episode

    episode["attachment"]["source_writer_audit"]["call_count"] = 1
    with pytest.raises(ValueError, match="nonformal_demo_attachment_invalid"):
        demo.validate_demo_episode(episode)

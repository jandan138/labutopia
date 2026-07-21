from __future__ import annotations

import copy
import json
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.labutopia_fluid import run_native_expert_close_only_probe as probe
from utils import fluid_evaluation_loop as production_fluid_loop


REPO_ROOT = Path(__file__).resolve().parents[1]


def _terminal_episode(*, accepted: bool = True) -> dict:
    checks = {name: True for name in probe.REQUIRED_PROBE_CHECKS}
    if not accepted:
        checks["probe_qualified_now"] = False
    control = {
        "mode": "collect",
        "source_ownership": "contact_friction_dynamic_v1",
        "expert_control_profile": "native_expert_v1",
        "execution_mode": "contact_acquisition_probe_v1",
        "contact_acquisition_probe": True,
        "contact_grasp_required": True,
        "native_pick": {
            "event": 5,
            "last_emitted_event": 4,
            "close_command_emitted": True,
            "lift_command_emitted": False,
        },
        "contact_pick": None,
        "pour_forward_invocation_count": 0,
    }
    attachment = {
        "mode": "contact_friction_dynamic_v1",
        "source_dynamic": True,
        "mechanical_attachment_used": False,
        "kinematic_target_update_count": 0,
        "close_command_observed": True,
        "lift_command_observed": False,
        "probe_qualified_now": accepted,
        "failure_reason": None,
        "source_writer_audit": {
            "coverage_complete": True,
            "valid": True,
            "call_count": 0,
        },
    }
    return {
        "run_id": "run-identity-1",
        "attempt_id": "attempt-00000000",
        "episode_id": "episode-0000",
        "attempt_status": "completed",
        "acceptance_mode": "contact_acquisition_probe_v1",
        "controller_completed": True,
        "cumulative_containment_valid": True,
        "source_visual_sync_valid": True,
        "contact_acquisition_probe_accepted": accepted,
        "expert_episode_accepted": False,
        "success": accepted,
        "control": control,
        "attachment": attachment,
        "probe_control_contract": {
            "id": probe.PROBE_CONTROL_CONTRACT_ID,
            "schema_version": probe.PROBE_CONTROL_CONTRACT_SCHEMA_VERSION,
            "supported_control_profiles": [
                "native_expert_v1",
                "contact_pick_v1",
            ],
            "selected_control_profile": "native_expert_v1",
            "checks": checks,
            "valid": accepted,
        },
        "cumulative_containment": {
            "pour_started_physics_step": None,
        },
        "termination": {
            "max_observations_per_episode_reached": False,
            "max_fluid_observations_reached": False,
            "observation_limit_boundary": {
                "reached": False,
                "reason": None,
            },
            "observation_limit_termination": {
                "terminated": False,
                "reason": None,
            },
            "observation_count": 37,
        },
        "terminal_observation": {
            "episode_id": "episode-0000",
            "observation_index": 36,
            "frame_identity": "frame-36",
        },
        "final_particle_counts": {
            "source": 3600,
            "target": 0,
            "transit": 0,
            "tabletop_spill": 0,
            "below_table": 0,
            "nonfinite": 0,
        },
    }


def _write_jsonl(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_child_command_invokes_exact_production_entrypoint_and_bound(tmp_path):
    config = probe.DEFAULT_CONFIG
    evidence_dir = tmp_path / "evidence"

    command = probe.build_child_command(
        config_path=config,
        evidence_dir=evidence_dir,
        python_executable=sys.executable,
    )

    assert command == [
        str(Path(sys.executable).resolve()),
        str((REPO_ROOT / "main.py").resolve()),
        "--backend",
        "gpu",
        "--headless",
        "--no-video",
        "--config-name",
        config.stem,
        "--config-dir",
        "config",
        "--fluid-evidence-dir",
        str(evidence_dir.resolve()),
        "--max-fluid-observations",
        "2400",
    ]


def test_strict_terminal_jsonl_accepts_exactly_one_finite_object(tmp_path):
    path = tmp_path / "episodes.jsonl"
    expected = _terminal_episode()
    _write_jsonl(path, expected)

    assert probe.load_terminal_episode(path) == expected


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\n",
        b"{}",
        b"{}\n{}\n",
        b"[]\n",
        b'{"duplicate":1,"duplicate":2}\n',
        b'{"nonfinite":NaN}\n',
        b"\xff\n",
    ],
)
def test_strict_terminal_jsonl_rejects_missing_ambiguous_or_malformed_data(
    tmp_path,
    payload,
):
    path = tmp_path / "episodes.jsonl"
    path.write_bytes(payload)

    with pytest.raises(ValueError, match="close_only_terminal_jsonl_invalid"):
        probe.load_terminal_episode(path)


def test_evidence_identity_binds_owner_pid_run_and_episode(tmp_path):
    owner_path = tmp_path / ".fluid-evidence-owner.json"
    _write_jsonl(owner_path, {"pid": 4321, "run_id": "run-identity-1"})
    owner = probe.load_evidence_owner(owner_path)
    episode = _terminal_episode()

    assert probe.validate_evidence_identity(
        owner,
        episode,
        expected_child_pid=4321,
    ) == {"pid": 4321, "run_id": "run-identity-1", "valid": True}

    for changed_owner, child_pid in (
        ({**owner, "run_id": "stale"}, 4321),
        ({**owner, "pid": 9999}, 4321),
        (owner, 9999),
    ):
        with pytest.raises(ValueError, match="close_only_evidence_identity_invalid"):
            probe.validate_evidence_identity(
                changed_owner,
                episode,
                expected_child_pid=child_pid,
            )


def test_run_identity_pins_config_asset_robot_and_implementation_closure():
    identity = probe.build_run_identity(probe.DEFAULT_CONFIG)

    assert identity["config"]["sha256"] == probe.EXPECTED_CONFIG_SHA256
    assert identity["asset"]["sha256"] == probe.EXPECTED_ASSET_SHA256
    assert identity["robot"]["sha256"] == probe.EXPECTED_ROBOT_SHA256
    assert identity["implementation"]["files"] == (
        probe.EXPECTED_IMPLEMENTATION_SHA256
    )
    assert len(identity["implementation"]["closure_sha256"]) == 64
    assert len(identity["identity_sha256"]) == 64

    tampered = copy.deepcopy(identity)
    tampered["implementation"]["files"]["main.py"] = "0" * 64
    with pytest.raises(ValueError, match="close_only_run_identity_invalid"):
        probe.validate_run_identity(tampered)


def test_terminal_validator_requires_versioned_native_contract_and_consistency():
    episode = _terminal_episode()

    result = probe.validate_terminal_episode(
        episode,
        expected_run_id="run-identity-1",
    )

    assert result == {
        "measurement_decision": "NATIVE_EXPERT_CLOSE_ONLY_PASS",
        "run_id": "run-identity-1",
        "attempt_id": "attempt-00000000",
        "episode_id": "episode-0000",
        "attempt_status": "completed",
        "observation_count": 37,
        "probe_control_contract_id": "contact_acquisition_probe_control_v1",
        "probe_control_contract_schema_version": 1,
        "probe_control_contract_valid": True,
    }

    wrong_version = copy.deepcopy(episode)
    wrong_version["probe_control_contract"]["schema_version"] = 2
    with pytest.raises(ValueError, match="close_only_probe_control_contract_invalid"):
        probe.validate_terminal_episode(
            wrong_version,
            expected_run_id="run-identity-1",
        )

    contradictory = copy.deepcopy(episode)
    contradictory["control"]["native_pick"]["lift_command_emitted"] = True
    with pytest.raises(ValueError, match="close_only_probe_control_checks_mismatch"):
        probe.validate_terminal_episode(
            contradictory,
            expected_run_id="run-identity-1",
        )


def test_parent_contract_matches_the_production_v1_contract_producer():
    episode = _terminal_episode()
    produced = production_fluid_loop.contact_acquisition_probe_control_contract(
        controller_evidence=episode["control"],
        attachment_evidence=episode["attachment"],
        expected_source_ownership="contact_friction_dynamic_v1",
        controller_completed=True,
        terminal_phase="FINISHED",
        terminal_action=None,
        pour_started=False,
        cumulative_containment_valid=True,
        source_visual_sync_valid=True,
    )

    assert produced == episode["probe_control_contract"]
    assert set(produced["checks"]) == set(probe.REQUIRED_PROBE_CHECKS)


def test_terminal_validator_classifies_complete_negative_contract_as_fail():
    result = probe.validate_terminal_episode(
        _terminal_episode(accepted=False),
        expected_run_id="run-identity-1",
    )

    assert result["measurement_decision"] == "NATIVE_EXPERT_CLOSE_ONLY_FAIL"
    assert result["probe_control_contract_valid"] is False


def test_terminal_validator_keeps_early_physical_failure_out_of_runtime_errors():
    episode = _terminal_episode(accepted=False)
    episode["control"]["native_pick"].update(
        last_emitted_event=2,
        close_command_emitted=False,
    )
    episode["attachment"].update(
        close_command_observed=False,
        failure_reason="source_translation_exceeded_before_contact",
    )
    checks = episode["probe_control_contract"]["checks"]
    checks.update(
        profile_terminal_identity=False,
        controller_close_command_emitted=False,
        attachment_close_command_observed=False,
        controller_lift_command_not_emitted=False,
        attachment_failure_free=False,
    )

    result = probe.validate_terminal_episode(
        episode,
        expected_run_id="run-identity-1",
    )

    assert result["measurement_decision"] == "NATIVE_EXPERT_CLOSE_ONLY_FAIL"


def test_terminal_validator_distinguishes_limit_boundary_from_limit_termination():
    episode = _terminal_episode()
    episode["termination"] = {
        "max_observations_per_episode_reached": True,
        "max_fluid_observations_reached": True,
        "observation_limit_boundary": {
            "reached": True,
            "reason": "max_observations_per_episode_reached",
        },
        "observation_limit_termination": {
            "terminated": False,
            "reason": None,
        },
        "observation_count": 2400,
    }
    episode["terminal_observation"]["observation_index"] = 2399

    result = probe.validate_terminal_episode(
        episode,
        expected_run_id="run-identity-1",
    )
    assert result["measurement_decision"] == "NATIVE_EXPERT_CLOSE_ONLY_PASS"

    aborted = _terminal_episode(accepted=False)
    aborted["controller_completed"] = False
    aborted["probe_control_contract"]["checks"]["controller_completed"] = False
    aborted["termination"] = copy.deepcopy(episode["termination"])
    aborted["termination"]["observation_limit_termination"] = {
        "terminated": True,
        "reason": "max_observations_per_episode_reached",
    }
    aborted["terminal_observation"]["observation_index"] = 2399
    result = probe.validate_terminal_episode(
        aborted,
        expected_run_id="run-identity-1",
    )
    assert result["measurement_decision"] == "NATIVE_EXPERT_CLOSE_ONLY_FAIL"


def test_finalizer_allows_clean_physical_outcomes_and_overrides_dirty_lifecycle():
    run_identity = {"schema_version": 1, "identity_sha256": "a" * 64}
    command = ["python", "main.py"]
    passed = probe.validate_terminal_episode(
        _terminal_episode(),
        expected_run_id="run-identity-1",
    )

    clean = probe.finalize_probe_report(
        terminal_validation=passed,
        run_identity=run_identity,
        child_command=command,
        child_returncode=0,
        timed_out=False,
        termination=None,
        runtime_error=None,
    )
    assert clean["decision"] == "NATIVE_EXPERT_CLOSE_ONLY_PASS"
    assert clean["lifecycle_status"] == "completed"
    assert clean["shutdown_status"] == "child_exit_0"

    failed = probe.validate_terminal_episode(
        _terminal_episode(accepted=False),
        expected_run_id="run-identity-1",
    )
    clean_failure = probe.finalize_probe_report(
        terminal_validation=failed,
        run_identity=run_identity,
        child_command=command,
        child_returncode=0,
        timed_out=False,
        termination=None,
        runtime_error=None,
    )
    assert clean_failure["decision"] == "NATIVE_EXPERT_CLOSE_ONLY_FAIL"
    assert clean_failure["lifecycle_status"] == "completed"

    timed_out = probe.finalize_probe_report(
        terminal_validation=passed,
        run_identity=run_identity,
        child_command=command,
        child_returncode=-signal.SIGKILL,
        timed_out=True,
        termination="SIGKILL",
        runtime_error="child_timeout",
    )
    assert timed_out["decision"] == "PROBE_RUNTIME_ERROR"
    assert timed_out["lifecycle_status"] == "failed"
    assert timed_out["shutdown_status"] == "child_timeout"

    malformed = probe.finalize_probe_report(
        terminal_validation=None,
        run_identity=run_identity,
        child_command=command,
        child_returncode=0,
        timed_out=False,
        termination=None,
        runtime_error="close_only_terminal_jsonl_invalid",
    )
    assert malformed["decision"] == "PROBE_RUNTIME_ERROR"
    assert malformed["shutdown_status"] == "evidence_validation_failed"


def test_parent_refuses_reused_output_without_modifying_it(tmp_path):
    marker = tmp_path / "owner.txt"
    marker.write_text("existing\n", encoding="utf-8")
    args = SimpleNamespace(
        config=probe.DEFAULT_CONFIG,
        out_dir=tmp_path,
        timeout_seconds=1.0,
    )

    assert probe._run_parent(args) == 2
    assert marker.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / probe.FINAL_REPORT_BASENAME).exists()


def test_parent_atomically_reports_identity_preflight_error_without_launch(
    tmp_path,
    monkeypatch,
):
    out_dir = tmp_path / "fresh"
    args = SimpleNamespace(
        config=probe.DEFAULT_CONFIG,
        out_dir=out_dir,
        timeout_seconds=1.0,
    )
    monkeypatch.setattr(
        probe,
        "build_run_identity",
        lambda _config: (_ for _ in ()).throw(ValueError("identity drift")),
    )
    monkeypatch.setattr(
        probe.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("child must not launch"),
    )

    assert probe._run_parent(args) == 2
    report = json.loads(
        (out_dir / probe.FINAL_REPORT_BASENAME).read_text(encoding="utf-8")
    )
    assert report["decision"] == "PROBE_RUNTIME_ERROR"
    assert report["shutdown_status"] == "identity_validation_failed"
    assert report["child_process"]["returncode"] == 127
    assert (out_dir / "child.stdout.log").read_bytes() == b""
    assert (out_dir / "child.stderr.log").read_bytes() == b""


def test_parent_seals_fake_clean_child_evidence_end_to_end(tmp_path, monkeypatch):
    out_dir = tmp_path / "fresh"
    args = SimpleNamespace(
        config=probe.DEFAULT_CONFIG,
        out_dir=out_dir,
        timeout_seconds=1.0,
    )
    identity = {"schema_version": 1, "identity_sha256": "a" * 64}
    monkeypatch.setattr(
        probe,
        "build_run_identity",
        lambda _config: copy.deepcopy(identity),
    )

    class Process:
        pid = 2468
        returncode = 0

        def __init__(self, command, **kwargs):
            assert kwargs["cwd"] == str(REPO_ROOT)
            assert kwargs["start_new_session"] is True
            evidence_dir = Path(
                command[command.index("--fluid-evidence-dir") + 1]
            )
            evidence_dir.mkdir()
            _write_jsonl(
                evidence_dir / probe.OWNER_BASENAME,
                {"pid": self.pid, "run_id": "run-identity-1"},
            )
            _write_jsonl(
                evidence_dir / probe.EPISODE_JSONL_BASENAME,
                _terminal_episode(),
            )

        def wait(self, timeout):
            assert timeout == 1.0
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(probe.subprocess, "Popen", Process)

    assert probe._run_parent(args) == 0
    report = json.loads(
        (out_dir / probe.FINAL_REPORT_BASENAME).read_text(encoding="utf-8")
    )
    assert report["decision"] == "NATIVE_EXPERT_CLOSE_ONLY_PASS"
    assert report["lifecycle_status"] == "completed"
    assert report["child_process"]["returncode"] == 0
    assert report["artifacts"]["terminal_episode"]["sha256"] == (
        probe.sha256_file(out_dir / "evidence/episodes.jsonl")
    )


def test_create_only_atomic_report_never_replaces_existing_file(tmp_path):
    path = tmp_path / "report.json"
    probe.atomic_create_json(path, {"decision": "NATIVE_EXPERT_CLOSE_ONLY_PASS"})

    with pytest.raises(FileExistsError, match="close_only_output_exists"):
        probe.atomic_create_json(path, {"decision": "PROBE_RUNTIME_ERROR"})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "decision": "NATIVE_EXPERT_CLOSE_ONLY_PASS"
    }

    with pytest.raises(ValueError, match="close_only_json_nonfinite"):
        probe.atomic_create_json(tmp_path / "nonfinite.json", {"value": float("nan")})


def test_timeout_cleanup_escalates_process_group_and_reaps(monkeypatch):
    class Process:
        pid = 9876
        returncode = None

        def __init__(self):
            self.wait_calls = 0

        def poll(self):
            return None

        def wait(self, timeout):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(["python"], timeout)
            self.returncode = -signal.SIGKILL
            return self.returncode

    process = Process()
    signals = []
    monkeypatch.setattr(
        probe.os,
        "killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    termination = probe.terminate_process_group(
        process,
        term_grace_seconds=0.01,
        kill_grace_seconds=0.01,
    )

    assert termination == "SIGKILL"
    assert signals == [
        (9876, signal.SIGTERM),
        (9876, signal.SIGKILL),
    ]
    assert process.wait_calls == 2


def test_runner_is_a_non_isaac_parent_without_control_or_physics_implementation():
    source = Path(probe.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "from isaacsim",
        "import isaacsim",
        "from omni",
        "import omni",
        "create_controller",
        "FluidEvaluationLoop",
        "world.step",
        "apply_action(",
    ):
        assert forbidden not in source

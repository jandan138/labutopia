#!/usr/bin/env python3
"""Launch one gated, no-attachment filled-PBD legacy controller demonstration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import traceback
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = REPO_ROOT / "main.py"
DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_nonformal_full_pbd_demo_v1.yaml"
)
FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
RUNTIME_REQUEST_ENV = "LABUTOPIA_RUNTIME_EXECUTION_REQUEST_PATH"
RUNTIME_RECEIPT_ENV = "LABUTOPIA_RUNTIME_RECEIPT_PATH"


def _attestation_module() -> Any:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tools.labutopia_fluid import attest_isaac41_effective_runtime

    return attest_isaac41_effective_runtime


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
            "utf-8"
        )
    ).hexdigest()


def _write_create_only(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _load_last_jsonl_object(path: Path) -> dict[str, Any]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise ValueError("nonformal_demo_episode_evidence_missing")
    value = json.loads(lines[-1])
    if not isinstance(value, Mapping):
        raise ValueError("nonformal_demo_episode_evidence_invalid")
    return dict(value)


def _terminate_process_group(process: subprocess.Popen[Any]) -> str:
    if process.poll() is not None:
        return "already_exited"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30)
        return "sigterm"
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)
        return "sigkill"


def build_child_command(
    *,
    config_path: Path,
    out_dir: Path,
    max_observations: int,
) -> list[str]:
    config = Path(config_path).resolve()
    output = Path(out_dir).resolve()
    return [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(MAIN_PATH),
        "--backend",
        "gpu",
        "--headless",
        "--config-name",
        config.stem,
        "--config-dir",
        os.path.relpath(config.parent, REPO_ROOT),
        "--fluid-evidence-dir",
        str(output / "online_fluid_evidence"),
        "--video-dir",
        str(output / "video"),
        "--max-fluid-observations",
        str(max_observations),
    ]


def validate_demo_episode(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("nonformal_demo_episode_invalid")
    if (
        value.get("acceptance_mode") != "nonformal_full_pbd_demo_v1"
        or value.get("nonformal_demo") is not True
        or value.get("expert_episode_accepted") is not False
    ):
        raise ValueError("nonformal_demo_episode_mode_invalid")
    attachment = value.get("attachment")
    if not isinstance(attachment, Mapping):
        raise ValueError("nonformal_demo_attachment_invalid")
    writer = attachment.get("source_writer_audit")
    if (
        attachment.get("mode") != "contact_friction_dynamic_v1"
        or attachment.get("source_dynamic") is not True
        or attachment.get("mechanical_attachment_used") is not False
        or attachment.get("kinematic_target_update_count") != 0
        or attachment.get("source_pose_write_count_after_play") != 0
        or not isinstance(writer, Mapping)
        or writer.get("coverage_complete") is not True
        or writer.get("valid") is not True
        or writer.get("call_count") != 0
    ):
        raise ValueError("nonformal_demo_attachment_invalid")
    control = value.get("control")
    if (
        not isinstance(control, Mapping)
        or control.get("mode") != "collect"
        or control.get("expert_control_profile") != "native_expert_v1"
        or control.get("execution_mode") != "nonformal_full_pbd_demo_v1"
        or control.get("source_ownership") != "contact_friction_dynamic_v1"
    ):
        raise ValueError("nonformal_demo_control_invalid")
    if type(value.get("controller_completed")) is not bool:
        raise ValueError("nonformal_demo_completion_invalid")
    if value["controller_completed"] is True:
        if (
            attachment.get("qualified") is not True
            or attachment.get("probe_qualified_now") is not True
            or attachment.get("contact_sensor_ready") is not True
            or attachment.get("failure_reason") is not None
            or value.get("cumulative_containment_valid") is not True
            or not isinstance(value.get("final_particle_counts"), Mapping)
            or any(
                value["final_particle_counts"].get(name) != 0
                for name in ("tabletop_spill", "below_table", "nonfinite")
            )
            or not isinstance(control.get("pour_forward_invocation_count"), int)
            or control["pour_forward_invocation_count"] <= 0
        ):
            raise ValueError("nonformal_demo_completion_invalid")
    return dict(value)


def validate_demo_config(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("nonformal_demo_config_invalid")
    fluid = value.get("online_fluid")
    if (
        value.get("task_type") != "pickpour"
        or value.get("controller_type") != "pour"
        or value.get("mode") != "collect"
        or value.get("max_episodes") != 1
        or not isinstance(fluid, Mapping)
        or fluid.get("enabled") is not True
        or fluid.get("expert_control_profile") != "native_expert_v1"
        or fluid.get("execution_mode") != "nonformal_full_pbd_demo_v1"
        or fluid.get("source_ownership") != "contact_friction_dynamic_v1"
        or fluid.get("source_pose_authority") != "physx_dynamic_readback_v1"
        or fluid.get("source_actor_path") != "/World/beaker2"
        or fluid.get("expected_particle_count") != 3600
        or any(
            key in fluid
            for key in (
                "attachment_matrix_policy",
                "expert_attachment",
                "gripper_frame_path",
                "synthetic_attachment_collision_filter_root_path",
            )
        )
    ):
        raise ValueError("nonformal_demo_config_invalid")
    return dict(value)


def _artifact(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def run_parent(args: argparse.Namespace) -> int:
    attestation = _attestation_module()
    args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    config = args.config.resolve()
    config_payload = config.read_bytes()
    config_sha256 = hashlib.sha256(config_payload).hexdigest()
    config_data = validate_demo_config(yaml.safe_load(config_payload))
    asset_path = (REPO_ROOT / str(config_data["usd_path"])).resolve()
    robot_path = (REPO_ROOT / str(config_data["robot"]["usd_path"])).resolve()
    if not asset_path.is_file() or not robot_path.is_file():
        raise FileNotFoundError("nonformal_demo_input_asset_missing")
    input_hashes_before = {
        "config": config_sha256,
        "asset": _sha256_file(asset_path),
        "robot": _sha256_file(robot_path),
    }
    from tools.labutopia_fluid.main_runtime_attestation_sources import (
        main_runtime_source_paths,
    )

    runtime_source_paths = main_runtime_source_paths(
        repo_root=REPO_ROOT,
        attester_path=Path(attestation.__file__),
    )
    parent_source_paths = (*runtime_source_paths, Path(__file__), REPO_ROOT / "robots/franka/franka.py")
    source_before = attestation.capture_source_identity(runtime_source_paths)
    parent_source_before = attestation.capture_source_identity(parent_source_paths)
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.out_dir / "execution_request.json"
    receipt_path = args.out_dir / "runtime_receipt.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.out_dir / "runtime")
    environment.update(
        {
            RUNTIME_REQUEST_ENV: str(request_path),
            RUNTIME_RECEIPT_ENV: str(receipt_path),
        }
    )
    command = build_child_command(
        config_path=config,
        out_dir=args.out_dir,
        max_observations=args.max_observations,
    )
    logs_dir = args.out_dir / "logs"
    logs_dir.mkdir(mode=0o700)
    stdout_path = logs_dir / "main.stdout.log"
    stderr_path = logs_dir / "main.stderr.log"
    child_pid = None
    child_returncode = None
    termination = None
    receipt = None
    episode = None
    failure = None
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = process.pid
            try:
                child_returncode = process.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                termination = _terminate_process_group(process)
                child_returncode = process.returncode
                raise RuntimeError("nonformal_demo_child_timeout")
        if child_returncode != 0:
            raise RuntimeError(f"nonformal_demo_child_exit_nonzero:{child_returncode}")
        receipt = attestation._read_canonical_json(receipt_path)
        attestation.require_matched_runtime_receipt(
            receipt,
            expected_execution_binding=attestation.execution_binding_for_request(
                request,
                child_pid=child_pid,
            ),
        )
        episode = validate_demo_episode(
            _load_last_jsonl_object(
                args.out_dir / "online_fluid_evidence" / "episodes.jsonl"
            )
        )
        input_hashes_after = {
            "config": _sha256_file(config),
            "asset": _sha256_file(asset_path),
            "robot": _sha256_file(robot_path),
        }
        if input_hashes_after != input_hashes_before:
            raise RuntimeError("nonformal_demo_input_changed_during_run")
        if attestation.capture_source_identity(runtime_source_paths) != source_before:
            raise RuntimeError("nonformal_demo_source_changed_during_run")
        if (
            attestation.capture_source_identity(parent_source_paths)
            != parent_source_before
        ):
            raise RuntimeError("nonformal_demo_parent_source_changed_during_run")
        decision = (
            "NONFORMAL_DEMO_COMPLETED"
            if episode.get("controller_completed") is True
            else "NONFORMAL_DEMO_REJECTED"
        )
    except BaseException as exc:
        failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        decision = "RUNTIME_BLOCKED"
    finally:
        source_after = attestation.capture_source_identity(runtime_source_paths)
        parent_source_after = attestation.capture_source_identity(parent_source_paths)
        artifacts = {
            "stdout": _artifact(stdout_path, root=args.out_dir),
            "stderr": _artifact(stderr_path, root=args.out_dir),
            "runtime_receipt": _artifact(receipt_path, root=args.out_dir),
            "episode": _artifact(
                args.out_dir / "online_fluid_evidence" / "episodes.jsonl",
                root=args.out_dir,
            ),
            "video": _artifact(args.out_dir / "video" / "episode_0.mp4", root=args.out_dir),
        }
        manifest = {
            "schema_version": 1,
            "manifest_type": "nonformal_full_pbd_demo_manifest_v1",
            "classification": "NON_FORMAL_LEGACY_CONTACT_DEMO",
            "decision": decision,
            "command": command,
            "config": {"path": str(config), "sha256": config_sha256},
            "asset": {
                "path": str(asset_path),
                "sha256": input_hashes_before["asset"],
            },
            "robot": {
                "path": str(robot_path),
                "sha256": input_hashes_before["robot"],
            },
            "execution_request_sha256": attestation.canonical_json_sha256(request),
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None
            ),
            "source_before": source_before,
            "source_after": source_after,
            "parent_source_before": parent_source_before,
            "parent_source_after": parent_source_after,
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "termination": termination,
            "episode": episode,
            "failure": failure,
            "artifacts": artifacts,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_create_only(args.out_dir / "report.json", manifest)
    print(
        f"nonformal full PBD demo decision={decision} out={args.out_dir / 'report.json'}",
        flush=True,
    )
    return 0 if decision == "NONFORMAL_DEMO_COMPLETED" else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-observations", type=int, default=9600)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file():
        parser.error("config must exist")
    if args.out_dir.exists():
        parser.error("out-dir must not exist")
    if args.max_observations <= 0:
        parser.error("max-observations must be positive")
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("timeout-seconds must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    return run_parent(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())

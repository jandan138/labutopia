import ast
import sys
from pathlib import Path

import pytest

from tools.labutopia_fluid import run_nonformal_pbd_direct_contact_probe as probe


def _execution_request() -> dict:
    return {
        "authority": "isaac41_effective_runtime_execution_request_v1",
        "schema_version": 1,
        "run_id": "run-0123456789abcdef",
        "parent_pid": 100,
        "parent_nonce_sha256": "a" * 64,
        "source": {"files": {}, "git": {}},
        "source_sha256": "b" * 64,
    }


def _allowlisted_environment(monkeypatch):
    for name in probe.FORBIDDEN_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    for name, value in probe.REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LD_LIBRARY_PATH", probe.APPROVED_LD_LIBRARY_PATH)


def test_runtime_modules_are_not_imported_before_simulation_app_bootstrap():
    tree = ast.parse(Path(probe.__file__).read_text(encoding="utf-8"))
    imports = [
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    imports.extend(
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert not any(name.startswith(("isaacsim", "omni", "pxr", "numpy")) for name in imports)


def test_runtime_preflight_requires_the_formal_prefix_and_isolated_child(
    tmp_path,
    monkeypatch,
):
    interpreter_alias = tmp_path / "formal-python"
    interpreter_alias.symlink_to(Path(sys.executable).resolve())
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PYTHON", interpreter_alias)
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PREFIX", Path(sys.prefix).resolve())
    _allowlisted_environment(monkeypatch)
    monkeypatch.setattr(probe, "_isolated_mode", lambda: True)

    record = probe.runtime_process_preflight(_execution_request())

    assert record["execution_binding"] == "same_process_runtime_receipt_v1"


def test_runtime_preflight_rejects_forbidden_environment_value(monkeypatch):
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PYTHON", Path(sys.executable).resolve())
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PREFIX", Path(sys.prefix).resolve())
    monkeypatch.setattr(probe, "_isolated_mode", lambda: True)
    _allowlisted_environment(monkeypatch)
    monkeypatch.setenv("PYTHONPATH", "/unsafe")

    with pytest.raises(RuntimeError, match="nonformal_probe_environment_forbidden:PYTHONPATH"):
        probe.runtime_process_preflight(_execution_request())


def test_runtime_preflight_rejects_unapproved_library_path(monkeypatch):
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PYTHON", Path(sys.executable).resolve())
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PREFIX", Path(sys.prefix).resolve())
    monkeypatch.setattr(probe, "_isolated_mode", lambda: True)
    _allowlisted_environment(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/unsafe")

    with pytest.raises(RuntimeError, match="nonformal_probe_library_path_invalid"):
        probe.runtime_process_preflight(_execution_request())


def test_input_hashes_must_match_the_files_loaded_at_start(tmp_path):
    config = tmp_path / "config.yaml"
    asset = tmp_path / "scene.usda"
    config.write_text("version: first\n", encoding="utf-8")
    asset.write_text("#usda 1.0\n", encoding="utf-8")
    config_sha256 = probe._sha256_file(config)
    asset_sha256 = probe._sha256_file(asset)
    closure = {str(config): config_sha256, str(asset): asset_sha256}

    probe._require_unchanged_input_hashes(
        input_closure=closure,
    )

    asset.write_text("#usda 1.0\n# changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="nonformal_probe_input_changed_during_run"):
        probe._require_unchanged_input_hashes(
            input_closure=closure,
        )


def test_runtime_source_closure_binds_config_fixture_treatment_and_runtime_imports():
    paths = set(
        probe._runtime_source_paths(
            probe.DEFAULT_CONFIG,
            "finite_target_offsets_calibration_v2",
        )
    )

    assert probe.DEFAULT_CONFIG.resolve() in paths
    assert probe.HIDDEN_CUBE_OVERLAY.resolve() in paths
    assert probe.FINITE_TARGET_OFFSET_OVERLAY.resolve() in paths
    assert (probe.REPO_ROOT / "utils/nonformal_usd_dependency_resolution.py").resolve() in paths

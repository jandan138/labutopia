import ast
import json
import sys
from pathlib import Path

import pytest

from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation
from tools.labutopia_fluid import run_nonformal_pbd_direct_contact_probe as probe


def _receipt(path: Path):
    path.write_text(
        json.dumps(
            {
                "authority": "isaac41_effective_runtime_receipt_v2",
                "attestation_status": "MATCH",
            }
        ),
        encoding="utf-8",
    )


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


def test_runtime_preflight_accepts_matched_receipt_in_an_allowlisted_environment(
    tmp_path, monkeypatch
):
    receipt = tmp_path / "runtime_receipt.json"
    _receipt(receipt)
    interpreter_alias = tmp_path / "formal-python"
    interpreter_alias.symlink_to(Path(sys.executable).resolve())
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PYTHON", interpreter_alias)
    _allowlisted_environment(monkeypatch)
    monkeypatch.setattr(
        attestation,
        "require_matched_runtime_receipt",
        lambda value: value,
    )

    record = probe._runtime_preflight(receipt)

    assert record["receipt_sha256"] == probe._sha256_file(receipt)
    assert record["receipt_binding"] == "separate_nonformal_preflight_only"


def test_runtime_preflight_rejects_a_forged_minimal_receipt(tmp_path, monkeypatch):
    receipt = tmp_path / "runtime_receipt.json"
    _receipt(receipt)
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PYTHON", Path(sys.executable).resolve())
    _allowlisted_environment(monkeypatch)

    with pytest.raises(RuntimeError, match="nonformal_probe_runtime_receipt_invalid"):
        probe._runtime_preflight(receipt)


def test_runtime_preflight_rejects_forbidden_environment_value(tmp_path, monkeypatch):
    receipt = tmp_path / "runtime_receipt.json"
    _receipt(receipt)
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PYTHON", Path(sys.executable).resolve())
    _allowlisted_environment(monkeypatch)
    monkeypatch.setenv("PYTHONPATH", "/unsafe")

    with pytest.raises(RuntimeError, match="nonformal_probe_environment_forbidden:PYTHONPATH"):
        probe._runtime_preflight(receipt)


def test_runtime_preflight_rejects_unapproved_library_path(tmp_path, monkeypatch):
    receipt = tmp_path / "runtime_receipt.json"
    _receipt(receipt)
    monkeypatch.setattr(probe, "FORMAL_ISAAC41_PYTHON", Path(sys.executable).resolve())
    _allowlisted_environment(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/unsafe")

    with pytest.raises(RuntimeError, match="nonformal_probe_library_path_invalid"):
        probe._runtime_preflight(receipt)


def test_input_hashes_must_match_the_files_loaded_at_start(tmp_path):
    config = tmp_path / "config.yaml"
    asset = tmp_path / "scene.usda"
    config.write_text("version: first\n", encoding="utf-8")
    asset.write_text("#usda 1.0\n", encoding="utf-8")
    config_sha256 = probe._sha256_file(config)
    asset_sha256 = probe._sha256_file(asset)

    probe._require_unchanged_input_hashes(
        config_path=config,
        config_sha256=config_sha256,
        asset_path=asset,
        asset_sha256=asset_sha256,
    )

    asset.write_text("#usda 1.0\n# changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="nonformal_probe_input_changed_during_run"):
        probe._require_unchanged_input_hashes(
            config_path=config,
            config_sha256=config_sha256,
            asset_path=asset,
            asset_sha256=asset_sha256,
        )

from __future__ import annotations

from pathlib import Path

import pytest

from tools.labutopia_fluid import run_real_beaker_static_hold_matrix as matrix


def _fake_isaacsim_spec(tmp_path: Path):
    package_root = tmp_path / "site-packages" / "isaacsim"
    usd_root = package_root / "extscache" / "omni.usd.libs"
    (usd_root / "pxr" / "Usd").mkdir(parents=True)
    (usd_root / "pxr" / "Usd" / "__init__.py").write_text("", encoding="utf-8")
    (usd_root / "bin").mkdir()
    (usd_root / "bin" / "libtf.so").write_bytes(b"tf")
    (usd_root / "bin" / "libusd.so").write_bytes(b"usd")

    class Spec:
        submodule_search_locations = [str(package_root)]
        origin = str(package_root / "__init__.py")

    return Spec(), usd_root


def test_resolve_isaac_usd_runtime_uses_matching_isaacsim_extcache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    isaacsim_spec, usd_root = _fake_isaacsim_spec(tmp_path)

    def fake_find_spec(name: str):
        return None if name == "pxr" else isaacsim_spec if name == "isaacsim" else None

    monkeypatch.setattr(matrix.importlib.util, "find_spec", fake_find_spec)
    contract = matrix.resolve_isaac_usd_runtime()

    assert contract["bootstrap_mode"] == "isaacsim_extcache"
    assert contract["python_path_entry"] == str(usd_root)
    assert contract["library_path_entry"] == str(usd_root / "bin")
    assert contract["usd_python_sha256"] == matrix._sha256_file(
        usd_root / "pxr" / "Usd" / "__init__.py"
    )
    assert contract["libtf_sha256"] == matrix._sha256_file(usd_root / "bin" / "libtf.so")


def test_build_isaac_child_env_prepends_matching_usd_paths():
    contract = {
        "bootstrap_mode": "isaacsim_extcache",
        "python_path_entry": "/matching/omni.usd.libs",
        "library_path_entry": "/matching/omni.usd.libs/bin",
    }

    env = matrix.build_isaac_child_env(
        {"PYTHONPATH": "/existing/python", "LD_LIBRARY_PATH": "/existing/lib"},
        contract,
    )

    assert env["PYTHONPATH"] == "/matching/omni.usd.libs:/existing/python"
    assert env["LD_LIBRARY_PATH"] == "/matching/omni.usd.libs/bin:/existing/lib"


def test_resolve_isaac_usd_runtime_fails_closed_when_matching_usd_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: None)

    with pytest.raises(RuntimeError, match="matching Isaac USD runtime"):
        matrix.resolve_isaac_usd_runtime()


def test_pxr_preflight_reports_failure_before_matrix_cells(
    monkeypatch: pytest.MonkeyPatch,
):
    class Result:
        returncode = 1
        stdout = b""
        stderr = b"ModuleNotFoundError: No module named 'pxr'"

    monkeypatch.setattr(matrix.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="Isaac USD preflight failed"):
        matrix.preflight_isaac_usd_runtime({"PYTHONPATH": "/bad"})

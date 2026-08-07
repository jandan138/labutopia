from __future__ import annotations

import copy

import pytest

from tools.labutopia_fluid import attest_isaac41_effective_runtime as attester


def _observed(contract: dict) -> dict:
    prefix = contract["prefix"]
    return {
        "executable": contract["executable"],
        "prefix": prefix,
        "python_version": contract["python_version"],
        "isaacsim_version": contract["isaacsim_version"],
        "conda_numpy_version": contract["conda_numpy_version"],
        "effective_numpy_version": contract["effective_numpy_version"],
        "usd_version": contract["usd_version"],
        "physx_version": contract["physx_version"],
        "pre_app_numpy_modules": [],
        "module_origins": {
            "isaacsim": f"{prefix}/{contract['isaacsim_relative_path']}",
            "numpy": f"{prefix}/{contract['effective_numpy_init_relative_path']}",
            "numpy_native": (
                f"{prefix}/{contract['effective_numpy_native_relative_path']}"
            ),
            "pxr_usd": f"{prefix}/{contract['pxr_usd_relative_path']}",
            "pxr_usd_native": (
                f"{prefix}/{contract['pxr_usd_native_relative_path']}"
            ),
            "omni_physx": f"{prefix}/{contract['physx_relative_path']}",
            "physx_native": (
                f"{prefix}/{contract['physx_native_relative_path']}"
            ),
        },
        "module_hashes": {
            "conda_numpy_metadata": contract["conda_numpy_metadata_sha256"],
            "numpy_init": contract["effective_numpy_init_sha256"],
            "numpy_native": contract["effective_numpy_native_sha256"],
            "numpy_record": contract["effective_numpy_record_sha256"],
            "isaacsim": contract["isaacsim_sha256"],
            "pxr_usd": contract["pxr_usd_sha256"],
            "pxr_usd_native": contract["pxr_usd_native_sha256"],
            "omni_physx": contract["physx_sha256"],
            "physx_native": contract["physx_native_sha256"],
        },
    }


def _receipt(contract: dict) -> dict:
    observed = _observed(contract)
    return {
        "authority": attester.RECEIPT_AUTHORITY,
        "schema_version": attester.SCHEMA_VERSION,
        "parent_nonce_sha256": "a" * 64,
        "execution_binding": _execution_binding(),
        "runtime_contract": copy.deepcopy(contract),
        "observed_runtime": observed,
        "attestation_status": "MATCH",
        "failure": None,
    }


def _execution_binding() -> dict:
    return {
        "authority": attester.EXECUTION_BINDING_AUTHORITY,
        "schema_version": attester.EXECUTION_BINDING_SCHEMA_VERSION,
        "run_id": "run-0123456789abcdef",
        "parent_pid": 100,
        "child_pid": 200,
        "parent_nonce_sha256": "a" * 64,
        "launch_request_sha256": "b" * 64,
        "source_sha256": "c" * 64,
    }


def test_effective_runtime_contract_pins_post_app_kit_numpy():
    contract = attester.formal_effective_runtime_contract()

    assert contract["authority"] == attester.CONTRACT_AUTHORITY
    assert contract["schema_version"] == attester.SCHEMA_VERSION
    assert contract["conda_numpy_version"] == "1.26.4"
    assert contract["effective_numpy_version"] == "1.26.0"
    assert "omni.kit.pip_archive/pip_prebundle/numpy/__init__.py" in contract[
        "effective_numpy_init_relative_path"
    ]
    assert contract["effective_numpy_init_sha256"] == (
        "11a9455eb4297e45351657f5a60f198c21831c7a395f8c59a7361fb2edf785e5"
    )


def test_runtime_receipt_accepts_exact_clean_post_app_provenance():
    contract = attester.formal_effective_runtime_contract()

    receipt = attester.validate_runtime_receipt(_receipt(contract))

    assert receipt["attestation_status"] == "MATCH"


def test_runtime_receipt_requires_the_expected_same_child_execution_binding():
    contract = attester.formal_effective_runtime_contract()
    receipt = _receipt(contract)
    expected = _execution_binding()

    attester.require_matched_runtime_receipt(
        receipt,
        expected_execution_binding=expected,
    )

    expected["child_pid"] = 201
    with pytest.raises(ValueError, match="effective_runtime_receipt_binding_mismatch"):
        attester.require_matched_runtime_receipt(
            receipt,
            expected_execution_binding=expected,
        )


def test_runtime_receipt_rejects_malformed_execution_binding():
    contract = attester.formal_effective_runtime_contract()
    receipt = _receipt(contract)
    del receipt["execution_binding"]["source_sha256"]

    with pytest.raises(ValueError, match="effective_runtime_receipt_invalid"):
        attester.validate_runtime_receipt(receipt)


def test_existing_application_attestation_uses_the_supplied_app(monkeypatch):
    contract = attester.formal_effective_runtime_contract()
    request = {
        "run_id": "run-0123456789abcdef",
        "parent_nonce_sha256": "a" * 64,
    }
    binding = _execution_binding()
    application = object()
    calls = []

    monkeypatch.setattr(
        attester,
        "verify_execution_request",
        lambda value, *, source_paths: calls.append((value, source_paths)) or request,
    )
    monkeypatch.setattr(
        attester,
        "execution_binding_for_request",
        lambda value, *, child_pid: binding,
    )
    monkeypatch.setattr(
        attester,
        "_observed_runtime_after_app",
        lambda received_contract, *, app, pre_app_numpy_modules: (
            _observed(received_contract)
            if (
                app is application
                and isinstance(pre_app_numpy_modules, list)
                and pre_app_numpy_modules == []
            )
            else None
        ),
    )

    receipt = attester.attest_existing_application(
        application=application,
        pre_app_numpy_modules=(),
        execution_request=request,
        source_paths=(attester.REPO_ROOT / "main.py",),
    )

    assert receipt["attestation_status"] == "MATCH"
    assert receipt["execution_binding"] == binding
    assert calls == [(request, (attester.REPO_ROOT / "main.py",))]


def test_runtime_receipt_rejects_conda_numpy_even_if_version_matches():
    contract = attester.formal_effective_runtime_contract()
    receipt = _receipt(contract)
    receipt["observed_runtime"]["module_origins"]["numpy"] = (
        f"{contract['prefix']}/lib/python3.10/site-packages/numpy/__init__.py"
    )
    receipt["attestation_status"] = "MISMATCH"

    normalized = attester.validate_runtime_receipt(receipt)
    assert normalized["attestation_status"] == "MISMATCH"
    with pytest.raises(ValueError, match="effective_runtime_receipt_match_required"):
        attester.require_matched_runtime_receipt(normalized)


def test_runtime_receipt_rejects_numpy_preloaded_before_simulation_app():
    contract = attester.formal_effective_runtime_contract()
    receipt = _receipt(contract)
    receipt["observed_runtime"]["pre_app_numpy_modules"] = ["numpy"]
    receipt["attestation_status"] = "MISMATCH"

    normalized = attester.validate_runtime_receipt(receipt)
    assert normalized["attestation_status"] == "MISMATCH"
    with pytest.raises(ValueError, match="effective_runtime_receipt_match_required"):
        attester.require_matched_runtime_receipt(normalized)


def test_runtime_receipt_rejects_changed_usd_native_binding():
    contract = attester.formal_effective_runtime_contract()
    receipt = _receipt(contract)
    receipt["observed_runtime"]["module_hashes"]["pxr_usd_native"] = "b" * 64
    receipt["attestation_status"] = "MISMATCH"

    normalized = attester.validate_runtime_receipt(receipt)

    assert normalized["attestation_status"] == "MISMATCH"
    with pytest.raises(ValueError, match="effective_runtime_receipt_match_required"):
        attester.require_matched_runtime_receipt(normalized)


def test_sealed_child_environment_excludes_ambient_python_and_isaac_paths(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("VK_DRIVER_FILES", "/host/vulkan.json")
    environment = attester.sealed_child_environment(tmp_path)

    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["ACCEPT_EULA"] == "Y"
    assert environment["OMNI_KIT_ACCEPT_EULA"] == "YES"
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "CARB_APP_PATH",
        "EXP_PATH",
        "ISAAC_PATH",
        "OMNI_SERVER",
        "LD_PRELOAD",
        "VK_DRIVER_FILES",
    ):
        assert name not in environment

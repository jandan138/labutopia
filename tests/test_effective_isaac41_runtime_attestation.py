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
        "runtime_contract": copy.deepcopy(contract),
        "observed_runtime": observed,
        "attestation_status": "MATCH",
        "failure": None,
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

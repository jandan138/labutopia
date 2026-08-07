#!/usr/bin/env python3
"""Attest the Isaac 4.1 runtime that Kit actually loads after bootstrap."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
FORMAL_ISAAC41_PREFIX = FORMAL_ISAAC41_PYTHON.parents[1]
SCHEMA_VERSION = 2
CONTRACT_AUTHORITY = "isaac41_effective_runtime_contract_v2"
RECEIPT_AUTHORITY = "isaac41_effective_runtime_receipt_v2"
MANIFEST_AUTHORITY = "isaac41_effective_runtime_manifest_v2"
EXECUTION_REQUEST_AUTHORITY = "isaac41_effective_runtime_execution_request_v1"
EXECUTION_REQUEST_SCHEMA_VERSION = 1
EXECUTION_BINDING_AUTHORITY = "isaac41_effective_runtime_execution_binding_v1"
EXECUTION_BINDING_SCHEMA_VERSION = 1
RECEIPT_BASENAME = "runtime_receipt.json"
MANIFEST_BASENAME = "runtime_manifest.json"
STDOUT_BASENAME = "child.stdout.log"
STDERR_BASENAME = "child.stderr.log"

_CONDA_NUMPY_METADATA_RELATIVE_PATH = (
    "conda-meta/numpy-1.26.4-py310hb13e2d6_0.json"
)
_EFFECTIVE_NUMPY_ROOT = (
    "lib/python3.10/site-packages/isaacsim/extscache/"
    "omni.kit.pip_archive/pip_prebundle"
)
_EFFECTIVE_NUMPY_INIT_RELATIVE_PATH = f"{_EFFECTIVE_NUMPY_ROOT}/numpy/__init__.py"
_EFFECTIVE_NUMPY_NATIVE_RELATIVE_PATH = (
    f"{_EFFECTIVE_NUMPY_ROOT}/numpy/core/"
    "_multiarray_umath.cpython-310-x86_64-linux-gnu.so"
)
_EFFECTIVE_NUMPY_RECORD_RELATIVE_PATH = (
    f"{_EFFECTIVE_NUMPY_ROOT}/numpy-1.26.0.dist-info/RECORD"
)
_ISAACSIM_RELATIVE_PATH = "lib/python3.10/site-packages/isaacsim/__init__.py"
_PXR_USD_RELATIVE_PATH = (
    "lib/python3.10/site-packages/isaacsim/extscache/"
    "omni.usd.libs/pxr/Usd/__init__.py"
)
_PXR_USD_NATIVE_RELATIVE_PATH = (
    "lib/python3.10/site-packages/isaacsim/extscache/"
    "omni.usd.libs/pxr/Usd/_usd.so"
)
_OMNI_PHYSX_RELATIVE_PATH = (
    "lib/python3.10/site-packages/isaacsim/extsPhysics/"
    "omni.physx/omni/physx/__init__.py"
)
_OMNI_PHYSX_NATIVE_RELATIVE_PATH = (
    "lib/python3.10/site-packages/isaacsim/extsPhysics/"
    "omni.physx/omni/physx/bindings/"
    "_physx.cpython-310-x86_64-linux-gnu.so"
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _validated_source_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"files", "git"}:
        raise ValueError("effective_runtime_source_identity_invalid")
    files = value["files"]
    git = value["git"]
    if (
        not isinstance(files, Mapping)
        or not files
        or any(
            not isinstance(path, str) or not path or not _is_sha256(digest)
            for path, digest in files.items()
        )
        or not isinstance(git, Mapping)
        or set(git) != {"revision", "dirty", "status_sha256"}
    ):
        raise ValueError("effective_runtime_source_identity_invalid")
    if git["revision"] is not None and (
        not isinstance(git["revision"], str) or not git["revision"]
    ):
        raise ValueError("effective_runtime_source_identity_invalid")
    if git["dirty"] is not None and type(git["dirty"]) is not bool:
        raise ValueError("effective_runtime_source_identity_invalid")
    if git["status_sha256"] is not None and not _is_sha256(git["status_sha256"]):
        raise ValueError("effective_runtime_source_identity_invalid")
    return {
        "files": dict(sorted((str(path), str(digest)) for path, digest in files.items())),
        "git": dict(git),
    }


def capture_source_identity(paths: Sequence[Path]) -> dict[str, Any]:
    """Capture the exact local sources that must agree before child startup."""
    files: dict[str, str] = {}
    for raw_path in paths:
        path = Path(raw_path).resolve()
        try:
            key = str(path.relative_to(REPO_ROOT))
        except ValueError as exc:
            raise ValueError("effective_runtime_source_path_outside_repo") from exc
        if not path.is_file():
            raise FileNotFoundError(f"effective_runtime_source_missing:{path}")
        if key in files:
            raise ValueError("effective_runtime_source_path_duplicate")
        files[key] = _sha256_file(path)
    return _validated_source_identity({"files": files, "git": _git_identity()})


def create_execution_request(
    *,
    run_id: str,
    parent_nonce_sha256: str,
    parent_pid: int,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    source = _validated_source_identity(source)
    request = {
        "authority": EXECUTION_REQUEST_AUTHORITY,
        "schema_version": EXECUTION_REQUEST_SCHEMA_VERSION,
        "run_id": run_id,
        "parent_pid": parent_pid,
        "parent_nonce_sha256": parent_nonce_sha256,
        "source": source,
        "source_sha256": canonical_json_sha256(source),
    }
    return validate_execution_request(request)


def validate_execution_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("effective_runtime_execution_request_invalid")
    request = dict(value)
    expected = {
        "authority",
        "schema_version",
        "run_id",
        "parent_pid",
        "parent_nonce_sha256",
        "source",
        "source_sha256",
    }
    if (
        set(request) != expected
        or request["authority"] != EXECUTION_REQUEST_AUTHORITY
        or request["schema_version"] != EXECUTION_REQUEST_SCHEMA_VERSION
        or not isinstance(request["run_id"], str)
        or not request["run_id"]
        or not _positive_int(request["parent_pid"])
        or not _is_sha256(request["parent_nonce_sha256"])
        or not _is_sha256(request["source_sha256"])
    ):
        raise ValueError("effective_runtime_execution_request_invalid")
    source = _validated_source_identity(request["source"])
    if canonical_json_sha256(source) != request["source_sha256"]:
        raise ValueError("effective_runtime_execution_request_invalid")
    return {
        **request,
        "source": source,
    }


def verify_execution_request(
    value: Any,
    *,
    source_paths: Sequence[Path],
) -> dict[str, Any]:
    request = validate_execution_request(value)
    if request["parent_pid"] != os.getppid():
        raise RuntimeError("effective_runtime_execution_parent_pid_mismatch")
    source = capture_source_identity(source_paths)
    if canonical_json_sha256(source) != request["source_sha256"]:
        raise RuntimeError("effective_runtime_execution_source_mismatch")
    return request


def execution_binding_for_request(
    request: Mapping[str, Any],
    *,
    child_pid: int,
) -> dict[str, Any]:
    request = validate_execution_request(request)
    binding = {
        "authority": EXECUTION_BINDING_AUTHORITY,
        "schema_version": EXECUTION_BINDING_SCHEMA_VERSION,
        "run_id": request["run_id"],
        "parent_pid": request["parent_pid"],
        "child_pid": child_pid,
        "parent_nonce_sha256": request["parent_nonce_sha256"],
        "launch_request_sha256": canonical_json_sha256(request),
        "source_sha256": request["source_sha256"],
    }
    return _validate_execution_binding(binding)


def _validate_execution_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("effective_runtime_receipt_invalid")
    binding = dict(value)
    expected = {
        "authority",
        "schema_version",
        "run_id",
        "parent_pid",
        "child_pid",
        "parent_nonce_sha256",
        "launch_request_sha256",
        "source_sha256",
    }
    if (
        set(binding) != expected
        or binding["authority"] != EXECUTION_BINDING_AUTHORITY
        or binding["schema_version"] != EXECUTION_BINDING_SCHEMA_VERSION
        or not isinstance(binding["run_id"], str)
        or not binding["run_id"]
        or not _positive_int(binding["parent_pid"])
        or not _positive_int(binding["child_pid"])
        or any(
            not _is_sha256(binding[field])
            for field in (
                "parent_nonce_sha256",
                "launch_request_sha256",
                "source_sha256",
            )
        )
    ):
        raise ValueError("effective_runtime_receipt_invalid")
    return binding


def _path(prefix: str, relative: str) -> str:
    return str(Path(prefix) / relative)


def formal_effective_runtime_contract() -> dict[str, Any]:
    """Return the reviewed effective runtime, not the launcher package view."""
    return {
        "authority": CONTRACT_AUTHORITY,
        "schema_version": SCHEMA_VERSION,
        "executable": str(FORMAL_ISAAC41_PYTHON),
        "prefix": str(FORMAL_ISAAC41_PREFIX),
        "python_version": "3.10.20",
        "isaacsim_version": "4.1.0.0",
        "usd_version": "0.22.11",
        "conda_numpy_version": "1.26.4",
        "conda_numpy_metadata_relative_path": _CONDA_NUMPY_METADATA_RELATIVE_PATH,
        "conda_numpy_metadata_sha256": (
            "3be2dd9383062f4a05a06f01c7b1221598c785f6decd321c540920723711e16b"
        ),
        "effective_numpy_version": "1.26.0",
        "effective_numpy_init_relative_path": (
            _EFFECTIVE_NUMPY_INIT_RELATIVE_PATH
        ),
        "effective_numpy_init_sha256": (
            "11a9455eb4297e45351657f5a60f198c21831c7a395f8c59a7361fb2edf785e5"
        ),
        "effective_numpy_native_relative_path": (
            _EFFECTIVE_NUMPY_NATIVE_RELATIVE_PATH
        ),
        "effective_numpy_native_sha256": (
            "90c01cc206f6dc9a2b9be88b4ce60c3a472e3f98a90468d11e6e62f755f68707"
        ),
        "effective_numpy_record_relative_path": (
            _EFFECTIVE_NUMPY_RECORD_RELATIVE_PATH
        ),
        "effective_numpy_record_sha256": (
            "12625dfce826dbbda6688e39eba84cdb4a5fba57b0bbb2ba9f7798b220396848"
        ),
        "isaacsim_relative_path": _ISAACSIM_RELATIVE_PATH,
        "isaacsim_sha256": (
            "848d761f3ec26864d1a7c1f2a3fdabd245a393e802100c47818b1684e9fc2b19"
        ),
        "pxr_usd_relative_path": _PXR_USD_RELATIVE_PATH,
        "pxr_usd_sha256": (
            "2c1973a6a98d74572b1a6a38d4485c81908c5defd5782a66862346f067c6f0d5"
        ),
        "pxr_usd_native_relative_path": _PXR_USD_NATIVE_RELATIVE_PATH,
        "pxr_usd_native_sha256": (
            "e883bd1a13a4e1d1944b7cc5e3bfaeda26e4fe288cb394a4e6d5ebf485eb0489"
        ),
        "physx_version": "106.0.20",
        "physx_relative_path": _OMNI_PHYSX_RELATIVE_PATH,
        "physx_sha256": (
            "ba16c601e6a2980e50fc74343bec19d3ec05c5096cf8bde252d0970d96bf6e3b"
        ),
        "physx_native_relative_path": _OMNI_PHYSX_NATIVE_RELATIVE_PATH,
        "physx_native_sha256": (
            "f2fa89e4bd78e894d432fbda535b5430f731778822c37d3215ec6286ffd6abb0"
        ),
    }


def validate_runtime_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("effective_runtime_contract_invalid")
    contract = dict(value)
    expected = formal_effective_runtime_contract()
    if contract != expected:
        raise ValueError("effective_runtime_contract_invalid")
    return contract


def runtime_contract_matches(
    *, contract: Mapping[str, Any], observed: Mapping[str, Any]
) -> bool:
    try:
        contract = validate_runtime_contract(contract)
    except ValueError:
        return False
    required = {
        "executable",
        "prefix",
        "python_version",
        "isaacsim_version",
        "conda_numpy_version",
        "effective_numpy_version",
        "usd_version",
        "physx_version",
        "pre_app_numpy_modules",
        "module_origins",
        "module_hashes",
    }
    if not isinstance(observed, Mapping) or set(observed) != required:
        return False
    for field in (
        "executable",
        "prefix",
        "python_version",
        "isaacsim_version",
        "conda_numpy_version",
        "effective_numpy_version",
        "usd_version",
        "physx_version",
    ):
        if observed.get(field) != contract[field]:
            return False
    if observed.get("pre_app_numpy_modules") != []:
        return False
    expected_origins = {
        "isaacsim": _path(contract["prefix"], contract["isaacsim_relative_path"]),
        "numpy": _path(
            contract["prefix"], contract["effective_numpy_init_relative_path"]
        ),
        "numpy_native": _path(
            contract["prefix"], contract["effective_numpy_native_relative_path"]
        ),
        "pxr_usd": _path(
            contract["prefix"], contract["pxr_usd_relative_path"]
        ),
        "pxr_usd_native": _path(
            contract["prefix"], contract["pxr_usd_native_relative_path"]
        ),
        "omni_physx": _path(
            contract["prefix"], contract["physx_relative_path"]
        ),
        "physx_native": _path(
            contract["prefix"], contract["physx_native_relative_path"]
        ),
    }
    if observed.get("module_origins") != expected_origins:
        return False
    expected_hashes = {
        "conda_numpy_metadata": contract["conda_numpy_metadata_sha256"],
        "numpy_init": contract["effective_numpy_init_sha256"],
        "numpy_native": contract["effective_numpy_native_sha256"],
        "numpy_record": contract["effective_numpy_record_sha256"],
        "isaacsim": contract["isaacsim_sha256"],
        "pxr_usd": contract["pxr_usd_sha256"],
        "pxr_usd_native": contract["pxr_usd_native_sha256"],
        "omni_physx": contract["physx_sha256"],
        "physx_native": contract["physx_native_sha256"],
    }
    return observed.get("module_hashes") == expected_hashes


def _validate_observed_runtime(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("effective_runtime_receipt_invalid")
    observed = dict(value)
    expected = {
        "executable",
        "prefix",
        "python_version",
        "isaacsim_version",
        "conda_numpy_version",
        "effective_numpy_version",
        "usd_version",
        "physx_version",
        "pre_app_numpy_modules",
        "module_origins",
        "module_hashes",
    }
    if set(observed) != expected:
        raise ValueError("effective_runtime_receipt_invalid")
    for field in expected.difference(
        {"pre_app_numpy_modules", "module_origins", "module_hashes"}
    ):
        if not isinstance(observed[field], str) or not observed[field]:
            raise ValueError("effective_runtime_receipt_invalid")
    modules = observed["pre_app_numpy_modules"]
    if not isinstance(modules, list) or any(
        not isinstance(name, str) or not name for name in modules
    ):
        raise ValueError("effective_runtime_receipt_invalid")
    expected_origins = {
        "isaacsim",
        "numpy",
        "numpy_native",
        "pxr_usd",
        "pxr_usd_native",
        "omni_physx",
        "physx_native",
    }
    origins = observed["module_origins"]
    if not isinstance(origins, Mapping) or set(origins) != expected_origins:
        raise ValueError("effective_runtime_receipt_invalid")
    if any(not isinstance(path, str) or not path for path in origins.values()):
        raise ValueError("effective_runtime_receipt_invalid")
    expected_hashes = {
        "conda_numpy_metadata",
        "numpy_init",
        "numpy_native",
        "numpy_record",
        "isaacsim",
        "pxr_usd",
        "pxr_usd_native",
        "omni_physx",
        "physx_native",
    }
    hashes = observed["module_hashes"]
    if (
        not isinstance(hashes, Mapping)
        or set(hashes) != expected_hashes
        or any(not _is_sha256(value) for value in hashes.values())
    ):
        raise ValueError("effective_runtime_receipt_invalid")
    return observed


def validate_runtime_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("effective_runtime_receipt_invalid")
    receipt = dict(value)
    expected = {
        "authority",
        "schema_version",
        "parent_nonce_sha256",
        "execution_binding",
        "runtime_contract",
        "observed_runtime",
        "attestation_status",
        "failure",
    }
    if (
        set(receipt) != expected
        or receipt.get("authority") != RECEIPT_AUTHORITY
        or receipt.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("effective_runtime_receipt_invalid")
    if not _is_sha256(receipt["parent_nonce_sha256"]):
        raise ValueError("effective_runtime_receipt_invalid")
    binding = _validate_execution_binding(receipt["execution_binding"])
    if binding["parent_nonce_sha256"] != receipt["parent_nonce_sha256"]:
        raise ValueError("effective_runtime_receipt_invalid")
    contract = validate_runtime_contract(receipt["runtime_contract"])
    status = receipt.get("attestation_status")
    failure = receipt.get("failure")
    if status == "UNAVAILABLE":
        if receipt.get("observed_runtime") is not None or not isinstance(failure, Mapping):
            raise ValueError("effective_runtime_receipt_invalid")
        return {
            "authority": RECEIPT_AUTHORITY,
            "schema_version": SCHEMA_VERSION,
            "parent_nonce_sha256": receipt["parent_nonce_sha256"],
            "execution_binding": binding,
            "runtime_contract": contract,
            "observed_runtime": None,
            "attestation_status": "UNAVAILABLE",
            "failure": dict(failure),
        }
    observed = _validate_observed_runtime(receipt.get("observed_runtime"))
    matches = runtime_contract_matches(contract=contract, observed=observed)
    expected_status = "MATCH" if matches else "MISMATCH"
    if status != expected_status or failure is not None:
        raise ValueError("effective_runtime_receipt_match_invalid")
    return {
        "authority": RECEIPT_AUTHORITY,
        "schema_version": SCHEMA_VERSION,
        "parent_nonce_sha256": receipt["parent_nonce_sha256"],
        "execution_binding": binding,
        "runtime_contract": contract,
        "observed_runtime": dict(observed),
        "attestation_status": expected_status,
        "failure": None,
    }


def require_matched_runtime_receipt(
    value: Any,
    *,
    expected_execution_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = validate_runtime_receipt(value)
    if receipt["attestation_status"] != "MATCH":
        raise ValueError("effective_runtime_receipt_match_required")
    if expected_execution_binding is not None:
        expected = _validate_execution_binding(expected_execution_binding)
        if receipt["execution_binding"] != expected:
            raise ValueError("effective_runtime_receipt_binding_mismatch")
    return receipt


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"effective_runtime_output_exists:{path}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def write_canonical_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write(path, payload)


def _read_canonical_json(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("effective_runtime_receipt_invalid") from exc
    if not isinstance(value, Mapping) or payload != _canonical_bytes(dict(value)):
        raise ValueError("effective_runtime_receipt_invalid")
    return dict(value)


def approved_library_paths() -> tuple[Path, ...]:
    site = FORMAL_ISAAC41_PREFIX / "lib/python3.10/site-packages"
    libraries = (
        site / "isaacsim/extscache/omni.cuda.libs/bin",
        site / "isaacsim/extscache/omni.gpu_foundation/bin/deps",
        site / "torch/lib",
    )
    missing = [str(path) for path in libraries if not path.is_dir()]
    if missing:
        raise RuntimeError(
            "effective_runtime_approved_library_root_missing:" + ",".join(missing)
        )
    return libraries


def approved_library_path_value() -> str:
    return ":".join(str(path) for path in approved_library_paths())


def sealed_child_environment(run_root: Path) -> dict[str, str]:
    directories = {
        "HOME": run_root / "home",
        "TMPDIR": run_root / "tmp",
        "XDG_CACHE_HOME": run_root / "xdg-cache",
        "XDG_CONFIG_HOME": run_root / "xdg-config",
        "XDG_DATA_HOME": run_root / "xdg-data",
        "XDG_STATE_HOME": run_root / "xdg-state",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=False)
    environment = {
        **{name: str(path) for name, path in directories.items()},
        "PATH": f"{FORMAL_ISAAC41_PREFIX / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "LD_LIBRARY_PATH": approved_library_path_value(),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ACCEPT_EULA": "Y",
        "OMNI_KIT_ACCEPT_EULA": "YES",
    }
    for name in (
        "NVIDIA_VISIBLE_DEVICES",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
    ):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _observed_runtime_after_app(
    contract: Mapping[str, Any],
    *,
    app: Any,
    pre_app_numpy_modules: Sequence[str],
) -> dict[str, Any]:
    if any(not isinstance(name, str) or not name for name in pre_app_numpy_modules):
        raise ValueError("effective_runtime_pre_app_numpy_modules_invalid")
    import importlib.metadata
    import importlib

    import isaacsim
    import numpy
    import omni.physx
    from pxr import Usd

    numpy_native = importlib.import_module("numpy.core._multiarray_umath")
    usd_native = importlib.import_module("pxr.Usd._usd")
    physx_native = importlib.import_module("omni.physx.bindings._physx")
    manager = app.app.get_extension_manager()
    extension_id = manager.get_enabled_extension_id("omni.physx")
    metadata = manager.get_extension_dict(extension_id)
    physx_version = metadata["package"]["version"]
    prefix = Path(sys.prefix).resolve()
    observed = {
        "executable": str(Path(sys.executable)),
        "prefix": str(prefix),
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "isaacsim_version": importlib.metadata.version("isaacsim"),
        "conda_numpy_version": json.loads(
            (prefix / contract["conda_numpy_metadata_relative_path"]).read_text(
                encoding="utf-8"
            )
        )["version"],
        "effective_numpy_version": numpy.__version__,
        "usd_version": ".".join(str(part) for part in Usd.GetVersion()),
        "physx_version": str(physx_version),
        "pre_app_numpy_modules": pre_app_numpy_modules,
        "module_origins": {
            "isaacsim": str(Path(isaacsim.__file__).resolve()),
            "numpy": str(Path(numpy.__file__).resolve()),
            "numpy_native": str(Path(numpy_native.__file__).resolve()),
            "pxr_usd": str(Path(Usd.__file__).resolve()),
            "pxr_usd_native": str(Path(usd_native.__file__).resolve()),
            "omni_physx": str(Path(omni.physx.__file__).resolve()),
            "physx_native": str(Path(physx_native.__file__).resolve()),
        },
        "module_hashes": {
            "conda_numpy_metadata": _sha256_file(
                prefix / contract["conda_numpy_metadata_relative_path"]
            ),
            "numpy_init": _sha256_file(Path(numpy.__file__).resolve()),
            "numpy_native": _sha256_file(Path(numpy_native.__file__).resolve()),
            "numpy_record": _sha256_file(
                prefix / contract["effective_numpy_record_relative_path"]
            ),
            "isaacsim": _sha256_file(Path(isaacsim.__file__).resolve()),
            "pxr_usd": _sha256_file(Path(Usd.__file__).resolve()),
            "pxr_usd_native": _sha256_file(Path(usd_native.__file__).resolve()),
            "omni_physx": _sha256_file(Path(omni.physx.__file__).resolve()),
            "physx_native": _sha256_file(Path(physx_native.__file__).resolve()),
        },
    }
    return observed


def _child_observed_runtime(contract: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    # This function runs in the sealed child. Keep imports before SimulationApp
    # limited to stdlib and isaacsim's app entrypoint.
    from isaacsim import SimulationApp

    pre_app_numpy_modules = sorted(
        name for name in sys.modules if name == "numpy" or name.startswith("numpy.")
    )
    sys.argv = [sys.argv[0]]
    app = SimulationApp({"headless": True})
    return (
        _observed_runtime_after_app(
            contract,
            app=app,
            pre_app_numpy_modules=pre_app_numpy_modules,
        ),
        app,
    )


def attest_existing_application(
    *,
    application: Any,
    pre_app_numpy_modules: Sequence[str],
    execution_request: Mapping[str, Any],
    source_paths: Sequence[Path],
) -> dict[str, Any]:
    """Attest an already bootstrapped Kit app before task construction."""
    # JSON evidence represents sequences as lists. Normalize here so the
    # in-memory match decision agrees with the receipt the parent re-reads.
    pre_app_numpy_modules = list(pre_app_numpy_modules)
    request = verify_execution_request(
        execution_request,
        source_paths=source_paths,
    )
    binding = execution_binding_for_request(request, child_pid=os.getpid())
    contract = formal_effective_runtime_contract()
    try:
        observed = _observed_runtime_after_app(
            contract,
            app=application,
            pre_app_numpy_modules=pre_app_numpy_modules,
        )
        status = (
            "MATCH"
            if runtime_contract_matches(contract=contract, observed=observed)
            else "MISMATCH"
        )
        return {
            "authority": RECEIPT_AUTHORITY,
            "schema_version": SCHEMA_VERSION,
            "parent_nonce_sha256": request["parent_nonce_sha256"],
            "execution_binding": binding,
            "runtime_contract": contract,
            "observed_runtime": observed,
            "attestation_status": status,
            "failure": None,
        }
    except Exception as exc:
        return {
            "authority": RECEIPT_AUTHORITY,
            "schema_version": SCHEMA_VERSION,
            "parent_nonce_sha256": request["parent_nonce_sha256"],
            "execution_binding": binding,
            "runtime_contract": contract,
            "observed_runtime": None,
            "attestation_status": "UNAVAILABLE",
            "failure": {"type": type(exc).__name__, "message": str(exc)},
        }


def bootstrap_effective_runtime(
    *,
    execution_request: Mapping[str, Any],
    source_paths: Sequence[Path],
) -> tuple[dict[str, Any], Any | None]:
    """Start Kit and attest the exact process that will execute the task."""
    request = verify_execution_request(
        execution_request,
        source_paths=source_paths,
    )
    binding = execution_binding_for_request(request, child_pid=os.getpid())
    contract = formal_effective_runtime_contract()
    app = None
    try:
        observed, app = _child_observed_runtime(contract)
        status = (
            "MATCH"
            if runtime_contract_matches(contract=contract, observed=observed)
            else "MISMATCH"
        )
        receipt = {
            "authority": RECEIPT_AUTHORITY,
            "schema_version": SCHEMA_VERSION,
            "parent_nonce_sha256": request["parent_nonce_sha256"],
            "execution_binding": binding,
            "runtime_contract": contract,
            "observed_runtime": observed,
            "attestation_status": status,
            "failure": None,
        }
    except Exception as exc:
        receipt = {
            "authority": RECEIPT_AUTHORITY,
            "schema_version": SCHEMA_VERSION,
            "parent_nonce_sha256": request["parent_nonce_sha256"],
            "execution_binding": binding,
            "runtime_contract": contract,
            "observed_runtime": None,
            "attestation_status": "UNAVAILABLE",
            "failure": {"type": type(exc).__name__, "message": str(exc)},
        }
    return receipt, app


def run_child(*, receipt_path: Path, execution_request_path: Path) -> int:
    app = None
    try:
        request = _read_canonical_json(execution_request_path)
        receipt, app = bootstrap_effective_runtime(
            execution_request=request,
            source_paths=(Path(__file__),),
        )
        _atomic_write(receipt_path, receipt)
        return 0
    finally:
        if app is not None:
            app.close()


def _environment_sha256(environment: Mapping[str, str]) -> str:
    return canonical_json_sha256(dict(sorted(environment.items())))


def _git_identity() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.encode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None, "status_sha256": None}
    return {
        "revision": revision,
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status).hexdigest(),
    }


def run_parent(*, out_dir: Path, timeout_s: float = 180.0) -> dict[str, Any]:
    if out_dir.exists():
        raise FileExistsError(f"effective_runtime_output_exists:{out_dir}")
    out_dir.mkdir(parents=True)
    receipt_path = out_dir / RECEIPT_BASENAME
    environment = sealed_child_environment(out_dir / "runtime")
    nonce_sha256 = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    run_id = secrets.token_hex(16)
    source_before = capture_source_identity((Path(__file__),))
    execution_request = create_execution_request(
        run_id=run_id,
        parent_nonce_sha256=nonce_sha256,
        parent_pid=os.getpid(),
        source=source_before,
    )
    execution_request_path = out_dir / "execution_request.json"
    _atomic_write(execution_request_path, execution_request)
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--receipt-out",
        str(receipt_path),
        "--execution-request",
        str(execution_request_path),
    ]
    stdout_path = out_dir / STDOUT_BASENAME
    stderr_path = out_dir / STDERR_BASENAME
    child_pid = None
    child_returncode = None
    parent_failure = None
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
            )
            child_pid = process.pid
            try:
                child_returncode = process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                process.kill()
                child_returncode = process.wait()
                raise
        receipt = validate_runtime_receipt(_read_canonical_json(receipt_path))
        require_matched_runtime_receipt(
            receipt,
            expected_execution_binding=execution_binding_for_request(
                execution_request,
                child_pid=child_pid,
            ),
        )
    except Exception as exc:
        receipt = None
        parent_failure = {"type": type(exc).__name__, "message": str(exc)}
    status = (
        receipt["attestation_status"]
        if receipt is not None and child_returncode == 0
        else "CHILD_FAILURE"
    )
    manifest = {
        "authority": MANIFEST_AUTHORITY,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "runtime_contract": formal_effective_runtime_contract(),
        "runtime_receipt_sha256": (
            None if receipt is None else canonical_json_sha256(receipt)
        ),
        "attestation_status": status,
        "command": command,
        "sanitized_environment_sha256": _environment_sha256(environment),
        "library_path_sha256": hashlib.sha256(
            environment["LD_LIBRARY_PATH"].encode("utf-8")
        ).hexdigest(),
        "conda_history_sha256": _sha256_file(
            FORMAL_ISAAC41_PREFIX / "conda-meta/history"
        ),
        "attester_sha256": _sha256_file(Path(__file__).resolve()),
        "source_before": source_before,
        "source_after": capture_source_identity((Path(__file__),)),
        "execution_request_sha256": canonical_json_sha256(execution_request),
        "child_pid": child_pid,
        "child_returncode": child_returncode,
        "stdout_sha256": _sha256_file(stdout_path),
        "stderr_sha256": _sha256_file(stderr_path),
        "parent_failure": parent_failure,
    }
    _atomic_write(out_dir / MANIFEST_BASENAME, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--execution-request", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    args = parser.parse_args(argv)
    if args.child:
        if (
            args.receipt_out is None
            or args.out_dir is not None
            or args.execution_request is None
        ):
            parser.error("--child requires --receipt-out and --execution-request")
        return run_child(
            receipt_path=args.receipt_out,
            execution_request_path=args.execution_request,
        )
    if args.out_dir is None or args.receipt_out is not None or args.execution_request:
        parser.error("parent mode requires --out-dir only")
    manifest = run_parent(out_dir=args.out_dir, timeout_s=args.timeout_s)
    return 0 if manifest["attestation_status"] == "MATCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())

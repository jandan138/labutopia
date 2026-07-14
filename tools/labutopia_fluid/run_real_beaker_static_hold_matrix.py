#!/usr/bin/env python3
"""Run the strict six-cell real-beaker static-hold evidence matrix."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(
    os.environ.get("LABUTOPIA_REPO_ROOT", Path(__file__).resolve().parents[2])
).resolve()
CHILD_SCRIPT = REPO_ROOT / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py"
DEFAULT_USD = (
    REPO_ROOT
    / "outputs/usd_asset_packages/lab_001_localized_20260707"
    / "lab_001_level1_pour_tabletop_with_liquid.usd"
)
DEFAULT_OUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_matrix_20260711_001"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_matrix_20260711.json"
)
PASS_CLASSIFICATION = "PASS_VISIBLE_BEAKER_STATIC_HOLD"
REQUIRED_COUNTS = (1024, 4096)
REQUIRED_SEEDS = (0, 1, 2)
CANONICAL_CELL_KEYS = (
    (1024, 0),
    (1024, 1),
    (1024, 2),
    (4096, 0),
    (4096, 1),
    (4096, 2),
)
REQUIRED_STEPS = 600
REQUIRED_LOGICAL_DT = 1.0 / 60.0
REQUIRED_INTEGRATION_DT = 1.0 / 600.0
REQUIRED_SUBSTEPS_PER_LOGICAL_STEP = 10
SUPERSEDED_FALSE_POSITIVE_MANIFESTS = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_full_scene_controlled_spawn_hold_20260710_P1024.json",
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_full_scene_controlled_spawn_hold_20260710_P4096.json",
)
ISAAC_VERSION_FILES = (
    Path(sys.prefix) / "VERSION",
    Path(sys.executable).resolve().parent.parent / "VERSION",
    Path("/isaac-sim/VERSION"),
    Path("/isaac-sim/PACKAGE-INFO.yaml"),
)
ISAAC_INSTALL_ROOTS = (Path("/isaac-sim"),)
ISAAC_INSTALL_ARTIFACT_PATTERNS = (
    "VERSION",
    "PACKAGE-INFO.yaml",
    "kit/PACKAGE-INFO.yaml",
    "apps/*isaac*.kit",
    "__init__.py",
    "*.py",
)
TARGET_ISAACSIM_VERSION_PREFIX = "4.1."
TARGET_USD_VERSION = "0.22.11"
REQUIRED_PARTICLE_SYSTEM_OFFSETS = {
    1024: {
        "contact_offset": 0.001058508,
        "rest_offset": 0.000594,
        "particle_contact_offset": 0.000705672,
        "solid_rest_offset": 0.000594,
        "fluid_rest_offset": 0.000352836,
    },
    4096: {
        "contact_offset": 0.000793881,
        "rest_offset": 0.0004455,
        "particle_contact_offset": 0.000529254,
        "solid_rest_offset": 0.0004455,
        "fluid_rest_offset": 0.000264627,
    },
}


@dataclass(frozen=True)
class ChildResult:
    returncode: int | None
    timed_out: bool
    termination: str | None = None
    launch_error: str | None = None


@dataclass(frozen=True)
class CellEvidenceSnapshot:
    root: Path
    summary_path: Path
    trace_path: Path
    evidence_scene_path: Path
    command_metadata_path: Path
    artifact_bytes: Mapping[str, bytes]
    summary: Mapping[str, Any]
    trace_records: tuple[Mapping[str, Any], ...]
    command_metadata: Mapping[str, Any]
    command: tuple[str, ...]
    source_usd_path: Path
    source_usd_sha256: str
    runner_script_path: Path
    runner_script_sha256: str
    trace_interval: int
    video_stride: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def resolve_isaac_usd_runtime() -> dict[str, Any]:
    """Resolve the USD Python runtime that belongs to the active Isaac install."""
    try:
        isaacsim_version = importlib.metadata.version("isaacsim")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("Isaac Sim 4.1 package is not installed in the active interpreter") from exc
    if not isaacsim_version.startswith(TARGET_ISAACSIM_VERSION_PREFIX):
        raise RuntimeError(
            f"Isaac Sim 4.1 is required, active package version is {isaacsim_version}"
        )

    try:
        isaacsim_spec = importlib.util.find_spec("isaacsim")
    except (ImportError, AttributeError, ValueError):
        isaacsim_spec = None
    package_roots: list[Path] = []
    if isaacsim_spec is not None:
        if isaacsim_spec.submodule_search_locations:
            package_roots.extend(Path(path) for path in isaacsim_spec.submodule_search_locations)
        elif isaacsim_spec.origin:
            package_roots.append(Path(isaacsim_spec.origin).parent)

    for package_root in package_roots:
        usd_root = (
            package_root.expanduser().resolve()
            / "extscache"
            / "omni.usd.libs"
        )
        pxr_package = usd_root / "pxr"
        pxr_python = pxr_package / "__init__.py"
        usd_python = pxr_package / "Usd" / "__init__.py"
        usd_extension = pxr_package / "Usd" / "_usd.so"
        library_root = usd_root / "bin"
        libtf = library_root / "libtf.so"
        libusd = library_root / "libusd.so"
        if pxr_package.is_dir() and all(
            path.is_file() for path in (usd_python, usd_extension, libtf, libusd)
        ):
            return {
                "bootstrap_mode": "isaacsim_extcache",
                "isaacsim_version": isaacsim_version,
                "expected_usd_version": TARGET_USD_VERSION,
                "pxr_package_path": str(pxr_package),
                "pxr_namespace_package": not pxr_python.is_file(),
                "pxr_init_sha256": (
                    _sha256_file(pxr_python) if pxr_python.is_file() else None
                ),
                "usd_python_sha256": _sha256_file(usd_python),
                "usd_extension_path": str(usd_extension),
                "usd_extension_sha256": _sha256_file(usd_extension),
                "libtf_sha256": _sha256_file(libtf),
                "libusd_sha256": _sha256_file(libusd),
                "python_path_entry": str(usd_root),
                "library_path_entry": str(library_root),
            }

    raise RuntimeError(
        "matching Isaac USD runtime is unavailable; pxr is not importable and "
        "the active isaacsim package has no complete omni.usd.libs extcache"
    )


def _prepend_env_path(value: str, existing: str | None) -> str:
    entries = [value]
    if existing:
        entries.extend(entry for entry in existing.split(os.pathsep) if entry and entry != value)
    return os.pathsep.join(entries)


def _without_conflicting_isaac_paths(
    existing: str | None,
    *,
    allowed_root: str,
) -> str | None:
    if not existing:
        return None
    allowed = Path(allowed_root).expanduser().resolve()
    retained: list[str] = []
    for entry in existing.split(os.pathsep):
        if not entry:
            continue
        resolved = Path(entry).expanduser().resolve()
        if resolved == allowed:
            continue
        if str(resolved).startswith("/isaac-sim/") or resolved == Path("/isaac-sim"):
            continue
        if "omni.usd.libs" in resolved.parts:
            continue
        retained.append(entry)
    return os.pathsep.join(retained) if retained else None


def build_isaac_child_env(
    base_env: Mapping[str, str],
    runtime_contract: Mapping[str, Any],
) -> dict[str, str]:
    env = dict(base_env)
    if runtime_contract.get("bootstrap_mode") == "isaacsim_extcache":
        python_path = runtime_contract.get("python_path_entry")
        library_path = runtime_contract.get("library_path_entry")
        if not isinstance(python_path, str) or not isinstance(library_path, str):
            raise RuntimeError("Isaac USD extcache contract is incomplete")
        clean_python_path = _without_conflicting_isaac_paths(
            env.get("PYTHONPATH"), allowed_root=python_path
        )
        clean_library_path = _without_conflicting_isaac_paths(
            env.get("LD_LIBRARY_PATH"), allowed_root=library_path
        )
        env["PYTHONPATH"] = _prepend_env_path(python_path, clean_python_path)
        env["LD_LIBRARY_PATH"] = _prepend_env_path(
            library_path, clean_library_path
        )
        env["PYTHONNOUSERSITE"] = "1"
    return env


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def preflight_isaac_usd_runtime(
    env: Mapping[str, str],
    runtime_contract: Mapping[str, Any],
) -> dict[str, Any]:
    probe = (
        "import json, pxr; "
        "from pxr import Usd; "
        "import pxr.Usd._usd as usd_extension; "
        "print(json.dumps({"
        "'usd_version': '.'.join(str(v) for v in Usd.GetVersion()),"
        "'pxr_origin': getattr(pxr, '__file__', None),"
        "'pxr_search_locations': [str(path) for path in getattr(pxr, '__path__', ())],"
        "'usd_origin': Usd.__file__,"
        "'usd_extension_origin': usd_extension.__file__"
        "}, sort_keys=True))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=dict(env),
        timeout=30.0,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Isaac USD preflight failed with return code {result.returncode}: {stderr}"
        )
    try:
        validation = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Isaac USD preflight failed: invalid probe output") from exc
    if not isinstance(validation, dict):
        raise RuntimeError("Isaac USD preflight failed: probe output is not an object")
    expected_version = runtime_contract.get("expected_usd_version")
    if validation.get("usd_version") != expected_version:
        raise RuntimeError(
            "Isaac USD preflight failed: "
            f"expected USD {expected_version}, loaded {validation.get('usd_version')}"
        )
    runtime_root_value = runtime_contract.get("python_path_entry")
    if not isinstance(runtime_root_value, str):
        raise RuntimeError("Isaac USD preflight failed: runtime root is missing")
    runtime_root = Path(runtime_root_value).expanduser().resolve()
    for field in ("usd_origin", "usd_extension_origin"):
        value = validation.get(field)
        if not isinstance(value, str) or not _path_is_within(
            Path(value).expanduser().resolve(), runtime_root
        ):
            raise RuntimeError(
                f"Isaac USD preflight failed: {field} is outside the Isaac 4.1 runtime"
            )
    pxr_origin = validation.get("pxr_origin")
    pxr_search_locations = validation.get("pxr_search_locations")
    if isinstance(pxr_origin, str):
        pxr_locations = [pxr_origin]
    elif pxr_origin is None and isinstance(pxr_search_locations, list):
        pxr_locations = pxr_search_locations
    else:
        pxr_locations = []
    if not pxr_locations or any(
        not isinstance(value, str)
        or not _path_is_within(Path(value).expanduser().resolve(), runtime_root)
        for value in pxr_locations
    ):
        raise RuntimeError(
            "Isaac USD preflight failed: pxr package is outside the Isaac 4.1 runtime"
        )
    extension_path = Path(validation["usd_extension_origin"]).resolve()
    extension_sha256 = _sha256_file(extension_path)
    if extension_sha256 != runtime_contract.get("usd_extension_sha256"):
        raise RuntimeError("Isaac USD preflight failed: loaded USD extension hash mismatch")
    return {
        **validation,
        "usd_extension_sha256": extension_sha256,
        "validated_against_isaacsim_version": runtime_contract.get("isaacsim_version"),
    }


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        temp_path = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp_path, path)


def static_hold_cells(
    *,
    counts: Sequence[int] = REQUIRED_COUNTS,
    seeds: Sequence[int] = REQUIRED_SEEDS,
) -> list[dict[str, int | str]]:
    normalized_counts = tuple(counts)
    normalized_seeds = tuple(seeds)
    if not normalized_counts or not normalized_seeds:
        raise ValueError("counts and seeds must be nonempty subsets of the canonical matrix")
    if any(type(count) is not int for count in normalized_counts):
        raise ValueError("counts must contain integers")
    if any(type(seed) is not int for seed in normalized_seeds):
        raise ValueError("seeds must contain integers")
    if len(set(normalized_counts)) != len(normalized_counts):
        raise ValueError("counts must not contain duplicates")
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValueError("seeds must not contain duplicates")
    if not set(normalized_counts).issubset(REQUIRED_COUNTS):
        raise ValueError(f"counts must be a subset of {REQUIRED_COUNTS}")
    if not set(normalized_seeds).issubset(REQUIRED_SEEDS):
        raise ValueError(f"seeds must be a subset of {REQUIRED_SEEDS}")
    ordered_counts = [count for count in REQUIRED_COUNTS if count in normalized_counts]
    ordered_seeds = [seed for seed in REQUIRED_SEEDS if seed in normalized_seeds]
    return [
        {
            "cell_id": f"P{count}_S{int(seed)}",
            "particle_count": count,
            "seed": int(seed),
        }
        for count in ordered_counts
        for seed in ordered_seeds
    ]


def argv_path(argv: Sequence[str], option: str) -> Path:
    return Path(argv[argv.index(option) + 1])


def _step_schedule_metadata(
    *,
    steps: int,
    logical_dt: float,
    integration_dt: float,
    substeps_per_logical_step: int,
) -> dict[str, Any]:
    return {
        "steps": steps,
        "steps_semantics": "logical_steps",
        "logical_dt": logical_dt,
        "integration_dt": integration_dt,
        "substeps_per_logical_step": substeps_per_logical_step,
        "integration_steps": steps * substeps_per_logical_step,
        "simulated_seconds": steps * logical_dt,
    }


def build_cell_argv(
    cell: Mapping[str, Any],
    *,
    out_dir: Path,
    usd: Path = DEFAULT_USD,
    steps: int = REQUIRED_STEPS,
    logical_dt: float = REQUIRED_LOGICAL_DT,
    integration_dt: float = REQUIRED_INTEGRATION_DT,
    substeps_per_logical_step: int = REQUIRED_SUBSTEPS_PER_LOGICAL_STEP,
    trace_interval: int = 30,
    runtime_timeout_seconds: float = 900.0,
    video_stride: int = 4,
    video_fps: float = 15.0,
    width: int = 960,
    height: int = 540,
    display_particle_width: float | None = None,
    headless: bool = False,
) -> list[str]:
    _validate_runtime_pins(
        steps=steps,
        logical_dt=logical_dt,
        integration_dt=integration_dt,
        substeps_per_logical_step=substeps_per_logical_step,
    )
    manifest = out_dir / "runtime_smoke_summary.json"
    argv = [
        sys.executable,
        str(CHILD_SCRIPT),
        "--usd",
        str(usd),
        "--real-beaker-static-hold",
        "--controlled-spawn-count",
        str(cell["particle_count"]),
        "--controlled-spawn-seed",
        str(cell["seed"]),
        "--steps",
        str(steps),
        "--logical-dt",
        repr(logical_dt),
        "--integration-dt",
        repr(integration_dt),
        "--substeps-per-logical-step",
        str(substeps_per_logical_step),
        "--trace-interval",
        str(trace_interval),
        "--runtime-timeout-seconds",
        repr(runtime_timeout_seconds),
        "--capture-native-cameras",
        "--capture-closeup-camera",
        "--hard-exit-after-run",
        "--video-stride",
        str(video_stride),
        "--video-fps",
        repr(video_fps),
        "--width",
        str(width),
        "--height",
        str(height),
        "--out-dir",
        str(out_dir),
        "--manifest",
        str(manifest),
    ]
    if display_particle_width is not None:
        argv.extend(("--display-particle-width", repr(display_particle_width)))
    if headless:
        argv.append("--headless")
    return argv


def _git_output(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _dirty_workspace_sha256() -> str:
    digest = hashlib.sha256()
    digest.update(b"tracked-diff-v1\0")
    digest.update(_git_output("diff", "--binary", "HEAD", "--"))
    untracked = _git_output(
        "ls-files", "--others", "--exclude-standard", "--", "tools", "tests"
    ).decode("utf-8").splitlines()
    for relative in sorted(untracked):
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        digest.update(b"\0untracked\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest()


def _isaac_version() -> str:
    versions: list[str] = []
    for distribution in ("isaacsim", "isaac-sim", "omni-isaac-core"):
        try:
            versions.append(f"{distribution}={importlib.metadata.version(distribution)}")
        except importlib.metadata.PackageNotFoundError:
            continue
    if versions:
        return ",".join(versions)
    for candidate in ISAAC_VERSION_FILES:
        path = candidate.expanduser().resolve()
        if not path.is_file() or not os.access(path, os.R_OK):
            continue
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        text = payload.decode("utf-8", errors="replace")
        version = next(
            (
                line.split(":", 1)[1].strip()
                for line in text.splitlines()
                if line.lower().startswith("version:")
            ),
            next((line.strip() for line in text.splitlines() if line.strip()), "unknown"),
        )
        fingerprint = _sha256_bytes(payload)
        return (
            f"version_file={version};path={path};"
            f"installation_fingerprint_sha256={fingerprint};file_sha256={_sha256_file(path)}"
        )
    for install_root in _candidate_isaac_install_roots():
        artifacts = _isaac_install_artifacts(install_root)
        if not artifacts:
            continue
        digest = hashlib.sha256()
        relative_paths = []
        for artifact in artifacts:
            relative = str(artifact.relative_to(install_root))
            relative_paths.append(relative)
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(artifact.read_bytes())
            digest.update(b"\0")
        return (
            f"install_root={install_root};installation_fingerprint_sha256={digest.hexdigest()};"
            f"artifacts={','.join(relative_paths)}"
        )
    raise RuntimeError("no recognizable Isaac installation could be identified")


def _candidate_isaac_install_roots() -> list[Path]:
    candidates = list(ISAAC_INSTALL_ROOTS)
    for env_name in ("ISAAC_SIM_ROOT", "ISAAC_PATH"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))
    try:
        spec = importlib.util.find_spec("isaacsim")
    except (ImportError, AttributeError, ValueError):
        spec = None
    if spec is not None:
        if spec.submodule_search_locations:
            candidates.extend(Path(location) for location in spec.submodule_search_locations)
        elif spec.origin:
            candidates.append(Path(spec.origin).parent)
    resolved: list[Path] = []
    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if path not in resolved:
            resolved.append(path)
    return resolved


def _isaac_install_artifacts(install_root: Path) -> list[Path]:
    if not install_root.is_dir():
        return []
    artifacts: set[Path] = set()
    for pattern in ISAAC_INSTALL_ARTIFACT_PATTERNS:
        artifacts.update(path for path in install_root.glob(pattern) if path.is_file())
    return sorted(artifacts, key=lambda path: str(path.relative_to(install_root)))


def build_run_identity(
    args: argparse.Namespace,
    *,
    isaac_usd_runtime: Mapping[str, Any] | None = None,
    isaac_usd_preflight: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_usd = Path(args.usd).resolve()
    if not source_usd.is_file():
        raise FileNotFoundError(f"source USD does not exist: {source_usd}")
    shared_cli_config = {
        **_step_schedule_metadata(
            steps=args.steps,
            logical_dt=args.logical_dt,
            integration_dt=args.integration_dt,
            substeps_per_logical_step=args.substeps_per_logical_step,
        ),
        "trace_interval": args.trace_interval,
        "runtime_timeout_seconds": args.runtime_timeout_seconds,
        "process_timeout_seconds": args.process_timeout_seconds,
        "headless": args.headless,
        "capture_native_cameras": True,
        "capture_closeup_camera": True,
        "video_stride": args.video_stride,
        "video_fps": args.video_fps,
        "width": args.width,
        "height": args.height,
        "display_particle_width": args.display_particle_width,
    }
    runtime_contract = dict(isaac_usd_runtime or resolve_isaac_usd_runtime())
    if isaac_usd_preflight is None:
        preflight_env = build_isaac_child_env(os.environ, runtime_contract)
        runtime_preflight = preflight_isaac_usd_runtime(
            preflight_env, runtime_contract
        )
    else:
        runtime_preflight = dict(isaac_usd_preflight)
    return {
        "source_usd_path": str(source_usd),
        "source_usd_sha256": _sha256_file(source_usd),
        "child_script_path": str(CHILD_SCRIPT),
        "child_script_sha256": _sha256_file(CHILD_SCRIPT),
        "git_commit": _git_output("rev-parse", "HEAD").decode("utf-8").strip(),
        "dirty_workspace_sha256": _dirty_workspace_sha256(),
        "dirty_workspace_hash_scope": "git diff HEAD plus untracked tools/tests file paths and content",
        "python_executable": sys.executable,
        "python_version": sys.version,
        "isaac_version": _isaac_version(),
        "isaac_usd_runtime": runtime_contract,
        "isaac_usd_preflight": runtime_preflight,
        "shared_cli_config": shared_cli_config,
    }


def _cell_key(cell: Mapping[str, Any]) -> tuple[int, int]:
    return int(cell["particle_count"]), int(cell["seed"])


def cell_is_accepted(record: Mapping[str, Any]) -> bool:
    return _has_authoritative_pass(record)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _strict_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number")
    return parsed


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-standard JSON constant: {value}")


def _strict_json_from_bytes(payload: bytes) -> Any:
    text = payload.decode("utf-8")
    if text.startswith("\ufeff"):
        raise ValueError("JSON BOM is not allowed")
    return json.loads(
        text,
        object_pairs_hook=_strict_json_object,
        parse_float=_strict_json_float,
        parse_constant=_reject_json_constant,
    )


def _read_regular_file_snapshot(path: Path) -> bytes:
    before = os.lstat(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"evidence path is not a regular file: {path}")
    payload = path.read_bytes()
    after = os.lstat(path)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise ValueError(f"evidence file changed while being read: {path}")
    return payload


def _safe_artifact_relative_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("artifact path must be a non-empty POSIX relative path")
    relative = Path(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise ValueError(f"unsafe artifact path: {value}")
    return relative


def _resolve_cell_file(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("cell evidence path is missing")
    declared = Path(value)
    candidate = declared if declared.is_absolute() else root / declared
    try:
        lexical_relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"cell evidence path escapes output directory: {value}") from exc
    if any(part in ("", ".", "..") for part in lexical_relative.parts):
        raise ValueError(f"cell evidence path is not canonical: {value}")
    cursor = root
    for part in lexical_relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"symlinked cell evidence is not accepted: {value}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"cell evidence path escapes output directory: {value}") from exc
    return resolved


def _strict_trace_records_from_bytes(
    payload: bytes,
) -> tuple[Mapping[str, Any], ...]:
    if not payload or not payload.endswith(b"\n"):
        raise ValueError("trace must be non-empty and newline terminated")
    text = payload.decode("utf-8")
    if text.startswith("\ufeff"):
        raise ValueError("trace BOM is not allowed")
    lines = text.splitlines()
    if not lines or any(not line for line in lines):
        raise ValueError("trace contains an empty record")
    records: list[Mapping[str, Any]] = []
    for line in lines:
        value = json.loads(
            line,
            object_pairs_hook=_strict_json_object,
            parse_float=_strict_json_float,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(value, Mapping):
            raise ValueError("trace record is not an object")
        records.append(value)
    return tuple(records)


def _command_option(command: Sequence[str], name: str) -> str:
    matches = [index for index, value in enumerate(command) if value == name]
    if len(matches) != 1 or matches[0] + 1 >= len(command):
        raise ValueError(f"command option must occur exactly once: {name}")
    value = command[matches[0] + 1]
    if value.startswith("--"):
        raise ValueError(f"command option has no value: {name}")
    return value


def _command_int(command: Sequence[str], name: str) -> int:
    raw = _command_option(command, name)
    value = int(raw)
    if raw != str(value):
        raise ValueError(f"command integer is not canonical: {name}")
    return value


def _command_float(command: Sequence[str], name: str) -> float:
    value = float(_command_option(command, name))
    if not math.isfinite(value):
        raise ValueError(f"command float is not finite: {name}")
    return value


def _command_path(command: Sequence[str], name: str) -> Path:
    value = Path(_command_option(command, name))
    if not value.is_absolute():
        raise ValueError(f"command path must be absolute: {name}")
    return value.resolve(strict=True)


def _load_cell_evidence(record: Mapping[str, Any]) -> CellEvidenceSnapshot | None:
    try:
        summary_value = record.get("summary_path")
        if not isinstance(summary_value, str) or not Path(summary_value).is_absolute():
            raise ValueError("summary path must be absolute")
        summary_declared = Path(summary_value)
        root = summary_declared.parent.resolve(strict=True)
        summary_path = _resolve_cell_file(root, summary_value)
        trace_path = _resolve_cell_file(root, record.get("trace_path"))
        evidence_scene_path = _resolve_cell_file(
            root, record.get("evidence_scene_path")
        )
        command_metadata_path = _resolve_cell_file(
            root, record.get("command_metadata_path")
        )

        declared_hashes = record.get("artifact_hashes")
        if not isinstance(declared_hashes, Mapping) or not declared_hashes:
            raise ValueError("artifact hashes are missing")
        normalized_hashes: dict[str, Any] = {}
        for relative_value, expected_sha256 in declared_hashes.items():
            relative = _safe_artifact_relative_path(relative_value)
            normalized_hashes[str(relative)] = expected_sha256
        actual_artifacts: set[str] = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"symlink exists in evidence directory: {path}")
            if path.is_file():
                actual_artifacts.add(str(path.relative_to(root)))
        if set(normalized_hashes) != actual_artifacts:
            raise ValueError("artifact hash registry does not match evidence files")

        artifact_bytes: dict[str, bytes] = {}
        for relative_value, expected_sha256 in normalized_hashes.items():
            relative = Path(relative_value)
            if not _is_sha256(expected_sha256):
                raise ValueError(f"artifact SHA-256 is invalid: {relative_value}")
            path = _resolve_cell_file(root, str(relative))
            payload = _read_regular_file_snapshot(path)
            if _sha256_bytes(payload) != expected_sha256:
                raise ValueError(f"artifact SHA-256 mismatch: {relative_value}")
            artifact_bytes[str(relative)] = payload

        required_paths = (
            summary_path,
            trace_path,
            evidence_scene_path,
            command_metadata_path,
        )
        for path in required_paths:
            relative = str(path.relative_to(root))
            if relative not in artifact_bytes:
                raise ValueError(f"required evidence is not artifact-hashed: {relative}")
        if not artifact_bytes[str(evidence_scene_path.relative_to(root))]:
            raise ValueError("evidence scene is empty")

        summary = _strict_json_from_bytes(
            artifact_bytes[str(summary_path.relative_to(root))]
        )
        command_metadata = _strict_json_from_bytes(
            artifact_bytes[str(command_metadata_path.relative_to(root))]
        )
        if not isinstance(summary, Mapping) or not isinstance(
            command_metadata, Mapping
        ):
            raise ValueError("summary or command metadata is not an object")
        trace_records = _strict_trace_records_from_bytes(
            artifact_bytes[str(trace_path.relative_to(root))]
        )

        command_value = record.get("command")
        if (
            not isinstance(command_value, list)
            or len(command_value) < 2
            or any(not isinstance(value, str) for value in command_value)
        ):
            raise ValueError("cell command is invalid")
        command = tuple(command_value)
        if command_metadata.get("schema_version") != 1:
            raise ValueError("command metadata schema is invalid")
        if command_metadata.get("argv") != list(command):
            raise ValueError("record and command metadata argv differ")
        command_cell = command_metadata.get("cell")
        if not isinstance(command_cell, Mapping) or (
            command_cell.get("cell_id") != record.get("cell_id")
            or command_cell.get("particle_count") != record.get("particle_count")
            or command_cell.get("seed") != record.get("seed")
        ):
            raise ValueError("command metadata cell differs from record")
        if command.count("--real-beaker-static-hold") != 1:
            raise ValueError("strict static-hold command flag is missing or duplicated")

        particle_count = _command_int(command, "--controlled-spawn-count")
        seed = _command_int(command, "--controlled-spawn-seed")
        steps = _command_int(command, "--steps")
        logical_dt = _command_float(command, "--logical-dt")
        integration_dt = _command_float(command, "--integration-dt")
        substeps = _command_int(command, "--substeps-per-logical-step")
        trace_interval = _command_int(command, "--trace-interval")
        video_stride = _command_int(command, "--video-stride")
        if (
            type(record.get("particle_count")) is not int
            or type(record.get("seed")) is not int
            or particle_count != record.get("particle_count")
            or seed != record.get("seed")
            or steps != REQUIRED_STEPS
            or logical_dt != REQUIRED_LOGICAL_DT
            or integration_dt != REQUIRED_INTEGRATION_DT
            or substeps != REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
            or not 0 < trace_interval <= 30
            or video_stride <= 0
        ):
            raise ValueError("command runtime contract does not match the matrix cell")

        command_schedule = command_metadata.get("step_schedule")
        record_schedule = record.get("step_schedule")
        expected_schedule = {
            "steps": REQUIRED_STEPS,
            "logical_dt": REQUIRED_LOGICAL_DT,
            "integration_dt": REQUIRED_INTEGRATION_DT,
            "substeps_per_logical_step": REQUIRED_SUBSTEPS_PER_LOGICAL_STEP,
        }
        if not isinstance(command_schedule, Mapping) or not isinstance(
            record_schedule, Mapping
        ):
            raise ValueError("step schedule metadata is missing")
        if any(
            command_schedule.get(key) != value
            or record_schedule.get(key) != value
            for key, value in expected_schedule.items()
        ):
            raise ValueError("step schedule metadata does not match command")

        out_dir = Path(_command_option(command, "--out-dir"))
        manifest_path = Path(_command_option(command, "--manifest"))
        if (
            not out_dir.is_absolute()
            or out_dir.resolve(strict=True) != root
            or not manifest_path.is_absolute()
            or manifest_path.resolve(strict=True) != summary_path
        ):
            raise ValueError("command output paths do not match cell evidence")

        runner_declared = Path(command[1])
        if (
            not runner_declared.is_absolute()
            or runner_declared.is_symlink()
            or runner_declared.resolve(strict=True) != CHILD_SCRIPT.resolve(strict=True)
        ):
            raise ValueError("command runner is not the matrix child script")
        runner_script_path = runner_declared.resolve(strict=True)
        runner_bytes = _read_regular_file_snapshot(runner_script_path)

        source_declared = Path(_command_option(command, "--usd"))
        if not source_declared.is_absolute() or source_declared.is_symlink():
            raise ValueError("source USD path is not an absolute regular path")
        source_usd_path = source_declared.resolve(strict=True)
        source_bytes = _read_regular_file_snapshot(source_usd_path)

        return CellEvidenceSnapshot(
            root=root,
            summary_path=summary_path,
            trace_path=trace_path,
            evidence_scene_path=evidence_scene_path,
            command_metadata_path=command_metadata_path,
            artifact_bytes=artifact_bytes,
            summary=summary,
            trace_records=trace_records,
            command_metadata=command_metadata,
            command=command,
            source_usd_path=source_usd_path,
            source_usd_sha256=_sha256_bytes(source_bytes),
            runner_script_path=runner_script_path,
            runner_script_sha256=_sha256_bytes(runner_bytes),
            trace_interval=trace_interval,
            video_stride=video_stride,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None


def _summary_contract_verified(
    record: Mapping[str, Any],
    evidence: CellEvidenceSnapshot,
) -> bool:
    summary = evidence.summary
    classification = summary.get("classification")
    strict_classification = summary.get("strict_visible_classification")
    controlled_spawn = summary.get("controlled_spawn_plan")
    try:
        summary_source = Path(str(summary.get("source_usd_path"))).resolve(
            strict=True
        )
        summary_trace = Path(str(summary.get("trace_path"))).resolve(strict=True)
        summary_scene = Path(str(summary.get("evidence_scene_path"))).resolve(
            strict=True
        )
    except (OSError, RuntimeError, ValueError):
        return False
    copied_contracts = (
        "strict_physics_execution",
        "physics_settings",
        "stage_unit_contract",
        "authored_runtime_paths",
        "physical_authoring_identity",
        "physical_trace_identity",
    )
    return (
        isinstance(classification, Mapping)
        and isinstance(strict_classification, Mapping)
        and isinstance(controlled_spawn, Mapping)
        and _classification_name(summary) == PASS_CLASSIFICATION
        and classification.get("trace_schema_valid") is True
        and strict_classification.get("classification") == PASS_CLASSIFICATION
        and strict_classification.get("trace_schema_valid") is True
        and summary.get("visible_beaker_containment_verified") is True
        and type(summary.get("selected_particle_count")) is int
        and summary.get("selected_particle_count") == record.get("particle_count")
        and type(summary.get("steps")) is int
        and summary.get("steps") == REQUIRED_STEPS
        and controlled_spawn.get("particle_count") == record.get("particle_count")
        and controlled_spawn.get("particle_seed") == record.get("seed")
        and summary_source == evidence.source_usd_path
        and summary_trace == evidence.trace_path
        and summary_scene == evidence.evidence_scene_path
        and all(summary.get(key) == record.get(key) for key in copied_contracts)
    )


def _recompute_strict_trace_identity(
    record: Mapping[str, Any],
    evidence: CellEvidenceSnapshot,
) -> dict[str, Any] | None:
    try:
        requested_count = record.get("particle_count")
        seed = record.get("seed")
        if (
            type(requested_count) is not int
            or requested_count <= 0
            or type(seed) is not int
            or seed < 0
        ):
            raise ValueError("trace count or seed is invalid")
        expected_steps = list(
            range(0, REQUIRED_STEPS + 1, evidence.trace_interval)
        )
        if expected_steps[-1] != REQUIRED_STEPS:
            expected_steps.append(REQUIRED_STEPS)
        actual_steps: list[int] = []
        frame_counts: list[int] = []
        ordered_positions: list[Any] = []
        for index, trace_record in enumerate(evidence.trace_records):
            step_index = trace_record.get("step_index")
            particle_count = trace_record.get("particle_count")
            positions = trace_record.get("positions")
            if (
                type(step_index) is not int
                or type(particle_count) is not int
                or not isinstance(positions, list)
                or particle_count != len(positions)
                or not 0 < particle_count <= requested_count
                or (index == 0 and particle_count != requested_count)
            ):
                raise ValueError(f"trace record schema mismatch: {index}")
            for point in positions:
                if (
                    not isinstance(point, list)
                    or len(point) != 3
                    or any(
                        type(value) not in (int, float)
                        or not math.isfinite(float(value))
                        for value in point
                    )
                ):
                    raise ValueError(f"trace point schema mismatch: {index}")
            if "nan_count" in trace_record and trace_record.get("nan_count") != 0:
                raise ValueError(f"trace contains non-finite points: {index}")
            actual_steps.append(step_index)
            frame_counts.append(particle_count)
            ordered_positions.append(positions)
        if actual_steps != expected_steps or len(actual_steps) != len(
            set(actual_steps)
        ):
            raise ValueError("trace frame cadence is incomplete or duplicated")
        positions_sha256 = _canonical_json_sha256(ordered_positions)
        identity = {
            "frame_indices": actual_steps,
            "frame_particle_counts": frame_counts,
            "frame_count": len(evidence.trace_records),
            "source_usd_sha256": evidence.source_usd_sha256,
            "particle_count": requested_count,
            "seed": seed,
            "steps": REQUIRED_STEPS,
            "trace_interval": evidence.trace_interval,
            "positions_sha256": positions_sha256,
        }
        identity["physical_trace_sha256"] = _canonical_json_sha256(identity)
        return identity
    except (TypeError, ValueError):
        return None


def _strict_trace_identity_verified(
    record: Mapping[str, Any],
    evidence: CellEvidenceSnapshot,
) -> bool:
    recomputed = _recompute_strict_trace_identity(record, evidence)
    classification = evidence.summary.get("classification")
    strict_classification = evidence.summary.get("strict_visible_classification")
    if (
        recomputed is None
        or not isinstance(classification, Mapping)
        or not isinstance(strict_classification, Mapping)
    ):
        return False
    claimed_identities = (
        record.get("physical_trace_identity"),
        evidence.summary.get("physical_trace_identity"),
        classification.get("physical_trace_identity"),
        strict_classification.get("physical_trace_identity"),
    )
    return all(
        isinstance(identity, Mapping) and dict(identity) == recomputed
        for identity in claimed_identities
    )


def _strict_visible_containment_recomputed(
    record: Mapping[str, Any],
    evidence: CellEvidenceSnapshot,
) -> bool:
    """Reclassify raw trace positions against geometry derived from the source USD."""
    try:
        from pxr import Usd

        from tools.labutopia_fluid.real_beaker import (
            classify_visible_beaker_trace,
            derive_cup_interior_frame,
        )

        before_sha256 = _sha256_bytes(
            _read_regular_file_snapshot(evidence.source_usd_path)
        )
        if before_sha256 != evidence.source_usd_sha256:
            return False
        stage = Usd.Stage.Open(str(evidence.source_usd_path))
        if stage is None:
            return False
        frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker2",
            visual_mesh_path="/World/beaker2/mesh",
            calibration_points_path="/World/ParticleSet",
        )
        region_config = evidence.summary.get("region_config")
        if not isinstance(region_config, Mapping):
            return False
        tail_window_steps = region_config.get("tail_window_steps")
        if type(tail_window_steps) is not int or tail_window_steps < 0:
            return False
        result = classify_visible_beaker_trace(
            evidence.trace_records,
            frame,
            requested_count=int(record["particle_count"]),
            steps=REQUIRED_STEPS,
            cadence=evidence.trace_interval,
            tail_window_steps=tail_window_steps,
            source_usd_sha256=evidence.source_usd_sha256,
            particle_seed=int(record["seed"]),
            legacy_region_config=None,
            diagnostic_log_text="",
            diagnostic_scan_complete=True,
            fatal_error=None,
            readback_available=True,
        )
        after_sha256 = _sha256_bytes(
            _read_regular_file_snapshot(evidence.source_usd_path)
        )
        recomputed_identity = _recompute_strict_trace_identity(record, evidence)
        return (
            after_sha256 == before_sha256
            and result.get("classification") == PASS_CLASSIFICATION
            and result.get("passed") is True
            and result.get("max_below_floor") == 0
            and result.get("max_outside_radius") == 0
            and result.get("max_above_rim") == 0
            and result.get("nonfinite_count") == 0
            and recomputed_identity is not None
            and result.get("physical_trace_identity") == recomputed_identity
        )
    except Exception:
        return False


def _strict_physics_settings_verified(settings: Any) -> bool:
    gravity = settings.get("gravity_direction") if isinstance(settings, Mapping) else None
    return (
        isinstance(settings, Mapping)
        and settings.get("gpu_dynamics_enabled") is True
        and settings.get("broadphase_type") == "GPU"
        and settings.get("solver_type") == "TGS"
        and isinstance(gravity, list)
        and len(gravity) == 3
        and all(type(value) in (int, float) for value in gravity)
        and [float(value) for value in gravity] == [0.0, 0.0, -1.0]
        and type(settings.get("gravity_magnitude")) in (int, float)
        and float(settings["gravity_magnitude"]) == 9.81
        and type(settings.get("gpu_max_particle_contacts")) is int
        and settings.get("gpu_max_particle_contacts") == 1048576
        and settings.get("strict_timestep_verified") is True
        and type(settings.get("time_steps_per_second")) is int
        and settings.get("time_steps_per_second") == 600
        and settings.get("time_steps_per_second_authored") is True
        and type(settings.get("effective_physics_dt")) in (int, float)
        and settings.get("effective_physics_dt") == REQUIRED_INTEGRATION_DT
    )


def _expected_lifecycle_contract(
    *,
    stage_id: int,
    video_stride: int,
) -> dict[str, Any]:
    hasher = hashlib.sha256()
    event_index = 0
    integration_step = 0
    render_check = 0

    def record_event(event: str, **payload: Any) -> None:
        nonlocal event_index
        encoded = json.dumps(
            {"event_index": event_index, "event": event, **payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        hasher.update(encoded)
        hasher.update(b"\n")
        event_index += 1

    record_event("attach_completed", stage_id=stage_id)
    render_check += 1
    record_event(
        "render_invariance_verified",
        check_index=render_check,
        integration_step=0,
    )
    for step_index in range(REQUIRED_STEPS + 1):
        if step_index % video_stride == 0 or step_index in (0, REQUIRED_STEPS):
            render_check += 1
            record_event(
                "render_invariance_verified",
                check_index=render_check,
                integration_step=integration_step,
            )
        if step_index >= REQUIRED_STEPS:
            continue
        for _ in range(REQUIRED_SUBSTEPS_PER_LOGICAL_STEP):
            next_integration_step = integration_step + 1
            record_event(
                "simulate_completed",
                integration_step=next_integration_step,
                integration_dt=REQUIRED_INTEGRATION_DT,
                current_time=integration_step * REQUIRED_INTEGRATION_DT,
            )
            record_event(
                "fetch_completed",
                integration_step=next_integration_step,
            )
            integration_step += 1
        record_event("logical_step_completed", logical_step=step_index + 1)
    record_event("detach_completed", stage_id=stage_id)
    return {
        "lifecycle_event_count": event_index,
        "lifecycle_event_sha256": hasher.hexdigest(),
        "render_invariance_checks": render_check,
    }


def _strict_lifecycle_verified(
    execution: Any,
    evidence: CellEvidenceSnapshot,
) -> bool:
    if not isinstance(execution, Mapping):
        return False
    stage_id = execution.get("stage_id")
    if type(stage_id) is not int or stage_id <= 0:
        return False
    expected = _expected_lifecycle_contract(
        stage_id=stage_id,
        video_stride=evidence.video_stride,
    )
    required_integration_steps = (
        REQUIRED_STEPS * REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
    )
    return (
        execution.get("exact_step_count_verified") is True
        and execution.get("exact_logical_step_count_verified") is True
        and execution.get("exact_integration_step_count_verified") is True
        and execution.get("requested_logical_steps") == REQUIRED_STEPS
        and execution.get("executed_logical_steps") == REQUIRED_STEPS
        and execution.get("requested_integration_steps")
        == required_integration_steps
        and execution.get("executed_integration_steps")
        == required_integration_steps
        and execution.get("logical_dt") == REQUIRED_LOGICAL_DT
        and execution.get("integration_dt") == REQUIRED_INTEGRATION_DT
        and execution.get("substeps_per_logical_step")
        == REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
        and execution.get("simulate_fetch_pair_count")
        == required_integration_steps
        and execution.get("ordered_lifecycle_verified") is True
        and execution.get("lifecycle_event_count")
        == expected["lifecycle_event_count"]
        and execution.get("lifecycle_event_sha256")
        == expected["lifecycle_event_sha256"]
        and execution.get("simulated_seconds") == REQUIRED_STEPS * REQUIRED_LOGICAL_DT
        and execution.get("attach_verified") is True
        and execution.get("detach_verified") is True
        and execution.get("render_updates_advance_physics") is False
        and execution.get("render_invariance_checks")
        == expected["render_invariance_checks"]
    )


def _strict_si_authoring_verified(record: Mapping[str, Any]) -> bool:
    contract = record.get("stage_unit_contract")
    density = contract.get("density_contract") if isinstance(contract, Mapping) else None
    return (
        isinstance(contract, Mapping)
        and contract.get("effective_meters_per_unit") == 1.0
        and contract.get("effective_kilograms_per_unit") == 1.0
        and contract.get("meters_per_unit_authored") is True
        and contract.get("kilograms_per_unit_authored") is True
        and contract.get("strict_si_units_verified") is True
        and contract.get("numeric_geometry_invariant") is True
        and isinstance(density, Mapping)
        and density.get("material_density_kg_m3") == 1000.0
        and density.get("particle_density_kg_m3") == 1000.0
        and density.get("particle_mass_kg") == 0.0
        and density.get("strict_si_density_verified") is True
    )


def _strict_collision_authoring_verified(record: Mapping[str, Any]) -> bool:
    authored = record.get("authored_runtime_paths")
    offsets = (
        authored.get("particle_system_collision_offsets")
        if isinstance(authored, Mapping)
        else None
    )
    particle_count = record.get("particle_count")
    expected = REQUIRED_PARTICLE_SYSTEM_OFFSETS.get(particle_count)
    if not isinstance(offsets, Mapping) or expected is None:
        return False
    return (
        set(offsets) == set(expected)
        and all(
            type(offsets.get(name)) in (int, float)
            and math.isfinite(float(offsets[name]))
            # USD-authored arithmetic can round-trip one binary ULP away from
            # the specified decimal while still representing the same pin.
            and abs(float(offsets[name]) - value) <= math.ulp(value)
            for name, value in expected.items()
        )
    )


def _physical_authoring_identity_verified(
    record: Mapping[str, Any],
    evidence: CellEvidenceSnapshot,
) -> bool:
    identity = record.get("physical_authoring_identity")
    execution = record.get("strict_physics_execution")
    physics_settings = record.get("physics_settings")
    stage_units = record.get("stage_unit_contract")
    authored = record.get("authored_runtime_paths")
    if not all(
        isinstance(value, Mapping)
        for value in (identity, execution, physics_settings, stage_units, authored)
    ):
        return False
    offsets = authored.get("particle_system_collision_offsets")
    identity_offsets = identity.get("particle_system_collision_offsets")
    schedule = identity.get("step_schedule")
    identity_si = identity.get("strict_si_contract")
    identity_density = (
        identity_si.get("density_contract")
        if isinstance(identity_si, Mapping)
        else None
    )
    stage_density = stage_units.get("density_contract")
    identity_physics = identity.get("physics_settings")
    summary_identity = evidence.summary.get("physical_authoring_identity")
    visible_spawn = evidence.summary.get("visible_beaker_spawn")
    canonical_wrapper = evidence.summary.get("canonical_wrapper")
    if not all(
        isinstance(value, Mapping)
        for value in (
            offsets,
            identity_offsets,
            schedule,
            identity_si,
            identity_density,
            stage_density,
            identity_physics,
            summary_identity,
            visible_spawn,
            canonical_wrapper,
        )
    ):
        return False
    claimed_sha256 = identity.get("physics_authoring_sha256")
    identity_body = dict(identity)
    identity_body.pop("physics_authoring_sha256", None)
    try:
        recomputed_sha256 = _canonical_json_sha256(identity_body)
    except (TypeError, ValueError):
        return False
    return (
        identity.get("schema_version") == 1
        and dict(summary_identity) == dict(identity)
        and identity.get("particle_count") == record.get("particle_count")
        and identity.get("seed") == record.get("seed")
        and isinstance(identity.get("isaacsim_version"), str)
        and identity["isaacsim_version"].startswith(TARGET_ISAACSIM_VERSION_PREFIX)
        and all(
            _is_sha256(identity.get(name))
            for name in (
                "source_usd_sha256",
                "runner_script_sha256",
                "spawn_positions_sha256",
                "wrapper_contract_sha256",
            )
        )
        and _is_sha256(claimed_sha256)
        and claimed_sha256 == recomputed_sha256
        and identity.get("source_usd_sha256") == evidence.source_usd_sha256
        and identity.get("runner_script_sha256")
        == evidence.runner_script_sha256
        and evidence.runner_script_path == CHILD_SCRIPT.resolve(strict=True)
        and visible_spawn.get("particle_count") == record.get("particle_count")
        and visible_spawn.get("particle_seed") == record.get("seed")
        and visible_spawn.get("positions_sha256")
        == identity.get("spawn_positions_sha256")
        and _canonical_json_sha256(canonical_wrapper)
        == identity.get("wrapper_contract_sha256")
        and schedule.get("logical_dt") == REQUIRED_LOGICAL_DT
        and schedule.get("integration_dt") == REQUIRED_INTEGRATION_DT
        and schedule.get("substeps_per_logical_step")
        == REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
        and schedule.get("logical_steps_per_second") == 60
        and schedule.get("integration_steps_per_second") == 600
        and schedule.get("logical_dt") == execution.get("logical_dt")
        and schedule.get("integration_dt") == execution.get("integration_dt")
        and schedule.get("substeps_per_logical_step")
        == execution.get("substeps_per_logical_step")
        and dict(identity_offsets) == dict(offsets)
        and _count_specific_identity_offsets_verified(record, identity_offsets)
        and identity_si.get("effective_meters_per_unit")
        == stage_units.get("effective_meters_per_unit")
        and identity_si.get("effective_kilograms_per_unit")
        == stage_units.get("effective_kilograms_per_unit")
        and identity_si.get("strict_si_units_verified")
        == stage_units.get("strict_si_units_verified")
        and identity_si.get("numeric_geometry_invariant")
        == stage_units.get("numeric_geometry_invariant")
        and dict(identity_density) == dict(stage_density)
        and dict(identity_physics) == dict(physics_settings)
        and _strict_physics_settings_verified(identity_physics)
    )


def _count_specific_identity_offsets_verified(
    record: Mapping[str, Any],
    offsets: Mapping[str, Any],
) -> bool:
    authored = record.get("authored_runtime_paths")
    return (
        isinstance(authored, Mapping)
        and dict(offsets)
        == dict(authored.get("particle_system_collision_offsets") or {})
        and _strict_collision_authoring_verified(
            {
                "particle_count": record.get("particle_count"),
                "authored_runtime_paths": {
                    "particle_system_collision_offsets": dict(offsets)
                },
            }
        )
    )


def _contract_only_authoritative_pass(record: Mapping[str, Any]) -> bool:
    """Validate in-memory unit-test contracts without granting file acceptance."""
    execution = record.get("strict_physics_execution")
    physics_settings = record.get("physics_settings")
    stage_units = record.get("stage_unit_contract")
    authored = record.get("authored_runtime_paths")
    identity = record.get("physical_authoring_identity")
    if not all(
        isinstance(value, Mapping)
        for value in (execution, physics_settings, stage_units, authored, identity)
    ):
        return False
    offsets = authored.get("particle_system_collision_offsets")
    identity_offsets = identity.get("particle_system_collision_offsets")
    render_checks = execution.get("render_invariance_checks")
    lifecycle_sha256 = execution.get("lifecycle_event_sha256")
    expected_events = (
        2
        + 2 * REQUIRED_STEPS * REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
        + REQUIRED_STEPS
        + render_checks
        if type(render_checks) is int
        else None
    )
    identity_body = dict(identity)
    claimed_identity_sha256 = identity_body.pop("physics_authoring_sha256", None)
    try:
        recomputed_identity_sha256 = _canonical_json_sha256(identity_body)
    except (TypeError, ValueError):
        return False
    generic_offsets_valid = (
        isinstance(offsets, Mapping)
        and isinstance(identity_offsets, Mapping)
        and dict(offsets) == dict(identity_offsets)
        and all(
            type(offsets.get(name)) in (int, float)
            and math.isfinite(float(offsets[name]))
            for name in (
                "contact_offset",
                "rest_offset",
                "particle_contact_offset",
                "solid_rest_offset",
                "fluid_rest_offset",
            )
        )
        and float(offsets["rest_offset"]) > 0.0
        and offsets["rest_offset"] == offsets["solid_rest_offset"]
        and float(offsets["rest_offset"]) < float(offsets["contact_offset"])
        and float(offsets["particle_contact_offset"])
        >= float(offsets["solid_rest_offset"])
        and float(offsets["fluid_rest_offset"]) > 0.0
    )
    return (
        record.get("classification") == PASS_CLASSIFICATION
        and record.get("visible_beaker_containment_verified") is True
        and (
            "returncode" not in record
            or (type(record.get("returncode")) is int and record.get("returncode") == 0)
        )
        and execution.get("exact_step_count_verified") is True
        and execution.get("exact_logical_step_count_verified") is True
        and execution.get("exact_integration_step_count_verified") is True
        and execution.get("requested_logical_steps") == REQUIRED_STEPS
        and execution.get("executed_logical_steps") == REQUIRED_STEPS
        and execution.get("requested_integration_steps")
        == REQUIRED_STEPS * REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
        and execution.get("executed_integration_steps")
        == REQUIRED_STEPS * REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
        and execution.get("logical_dt") == REQUIRED_LOGICAL_DT
        and execution.get("integration_dt") == REQUIRED_INTEGRATION_DT
        and execution.get("substeps_per_logical_step")
        == REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
        and execution.get("simulate_fetch_pair_count")
        == REQUIRED_STEPS * REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
        and execution.get("ordered_lifecycle_verified") is True
        and execution.get("lifecycle_event_count") == expected_events
        and _is_sha256(lifecycle_sha256)
        and execution.get("simulated_seconds", REQUIRED_STEPS * REQUIRED_LOGICAL_DT)
        == REQUIRED_STEPS * REQUIRED_LOGICAL_DT
        and execution.get("attach_verified") is True
        and execution.get("detach_verified") is True
        and execution.get("render_updates_advance_physics") is False
        and type(render_checks) is int
        and render_checks > 0
        and physics_settings.get("strict_timestep_verified") is True
        and physics_settings.get("time_steps_per_second") == 600
        and physics_settings.get("effective_physics_dt")
        == REQUIRED_INTEGRATION_DT
        and _strict_si_authoring_verified(record)
        and generic_offsets_valid
        and identity.get("schema_version") == 1
        and identity.get("particle_count") == record.get("particle_count")
        and identity.get("seed") == record.get("seed")
        and _is_sha256(claimed_identity_sha256)
        and claimed_identity_sha256 == recomputed_identity_sha256
    )


def _has_authoritative_pass(record: Mapping[str, Any]) -> bool:
    evidence = _load_cell_evidence(record)
    if evidence is None:
        return False
    execution = record.get("strict_physics_execution")
    physics_settings = record.get("physics_settings")
    return (
        all(
            key in record
            for key in (
                "timed_out",
                "launch_error",
                "summary_error",
            )
        )
        and record.get("timed_out") is False
        and record.get("launch_error") is None
        and record.get("summary_error") is None
        and type(record.get("returncode")) is int
        and record.get("returncode") == 0
        and record.get("classification") == PASS_CLASSIFICATION
        and record.get("visible_beaker_containment_verified") is True
        and _summary_contract_verified(record, evidence)
        and _strict_trace_identity_verified(record, evidence)
        and _strict_visible_containment_recomputed(record, evidence)
        and _strict_lifecycle_verified(execution, evidence)
        and _strict_physics_settings_verified(physics_settings)
        and _strict_si_authoring_verified(record)
        and _strict_collision_authoring_verified(record)
        and _physical_authoring_identity_verified(record, evidence)
    )


def _shared_matrix_run_identity_sha256(cell: Mapping[str, Any]) -> str | None:
    identity = cell.get("physical_authoring_identity")
    if not isinstance(identity, Mapping):
        return None
    required_scalar_fields = (
        "source_usd_sha256",
        "runner_script_sha256",
        "isaacsim_version",
        "wrapper_contract_sha256",
    )
    if any(not isinstance(identity.get(key), str) for key in required_scalar_fields):
        return None
    if not _is_sha256(identity.get("source_usd_sha256")):
        return None
    if not _is_sha256(identity.get("runner_script_sha256")):
        return None
    if not _is_sha256(identity.get("wrapper_contract_sha256")):
        return None
    shared_mappings = (
        "step_schedule",
        "strict_si_contract",
        "physics_settings",
    )
    if any(not isinstance(identity.get(key), Mapping) for key in shared_mappings):
        return None
    return _canonical_json_sha256(
        {
            **{key: identity[key] for key in required_scalar_fields},
            **{key: dict(identity[key]) for key in shared_mappings},
        }
    )


def real_beaker_static_hold_closed(
    cells: Sequence[Mapping[str, Any]],
    *,
    steps: int = REQUIRED_STEPS,
    logical_dt: float = REQUIRED_LOGICAL_DT,
    integration_dt: float = REQUIRED_INTEGRATION_DT,
    substeps_per_logical_step: int = REQUIRED_SUBSTEPS_PER_LOGICAL_STEP,
    _allow_injected_executor_contract: bool = False,
) -> bool:
    if not _runtime_pins_match(
        steps=steps,
        logical_dt=logical_dt,
        integration_dt=integration_dt,
        substeps_per_logical_step=substeps_per_logical_step,
    ):
        return False
    if tuple(_cell_key(cell) for cell in cells) != CANONICAL_CELL_KEYS:
        return False
    if not all(
        _cell_passes_closure(
            cell,
            allow_injected_executor_contract=_allow_injected_executor_contract,
        )
        for cell in cells
    ):
        return False
    shared_identities = [_shared_matrix_run_identity_sha256(cell) for cell in cells]
    return None not in shared_identities and len(set(shared_identities)) == 1


def _cell_passes_closure(
    cell: Mapping[str, Any],
    *,
    allow_injected_executor_contract: bool,
) -> bool:
    file_backed = any(
        key in cell
        for key in (
            "summary_path",
            "trace_path",
            "evidence_scene_path",
            "artifact_hashes",
        )
    )
    if file_backed and not allow_injected_executor_contract:
        return _has_authoritative_pass(cell)
    return _contract_only_authoritative_pass(cell)


def _accepted_1024_keys(
    cells: Sequence[Mapping[str, Any]],
    *,
    allow_injected_executor_contract: bool = False,
) -> set[tuple[int, int]]:
    return {
        _cell_key(cell)
        for cell in cells
        if int(cell.get("particle_count", -1)) == 1024
        and _cell_passes_closure(
            cell,
            allow_injected_executor_contract=allow_injected_executor_contract,
        )
    }


def all_required_1024_accepted(
    cells: Sequence[Mapping[str, Any]],
    *,
    _allow_injected_executor_contract: bool = False,
) -> bool:
    return _accepted_1024_keys(
        cells,
        allow_injected_executor_contract=_allow_injected_executor_contract,
    ) == {(1024, seed) for seed in REQUIRED_SEEDS}


def validate_append_manifest(
    manifest: Mapping[str, Any],
    *,
    run_identity: Mapping[str, Any],
    requested_cells: Sequence[Mapping[str, Any]],
) -> None:
    if manifest.get("run_identity") != run_identity:
        raise ValueError("append run identity mismatch")
    _validate_append_cells(manifest.get("cells"), requested_cells)


def _validate_append_cells(
    existing_cells: Any,
    requested_cells: Sequence[Mapping[str, Any]],
) -> None:
    if not isinstance(existing_cells, list):
        raise ValueError("append manifest cells must be a list")
    existing_keys = [_cell_key(cell) for cell in existing_cells]
    if len(existing_keys) != len(set(existing_keys)):
        raise ValueError("append manifest contains duplicate cell")
    requested_keys = [_cell_key(cell) for cell in requested_cells]
    if len(requested_keys) != len(set(requested_keys)):
        raise ValueError("requested matrix contains duplicate cell")
    duplicates = set(existing_keys).intersection(requested_keys)
    if duplicates:
        raise ValueError(f"append duplicate cell: {sorted(duplicates)}")
    expected_existing = list(CANONICAL_CELL_KEYS[: len(existing_keys)])
    if existing_keys != expected_existing:
        raise ValueError("append manifest cells must be an exact canonical prefix in order")
    expected_requested = list(
        CANONICAL_CELL_KEYS[len(existing_keys) : len(existing_keys) + len(requested_keys)]
    )
    if requested_keys != expected_requested:
        raise ValueError("append requested cells must be the immediate next canonical segment")
    requests_4096 = any(count == 4096 for count, _seed in requested_keys)
    requests_1024 = any(count == 1024 for count, _seed in requested_keys)
    if requests_4096 and not requests_1024 and not all_required_1024_accepted(existing_cells):
        raise ValueError("append requires all three accepted 1024 cells before any 4096 launch")


def execute_child(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: float,
    stdout_path: Path,
    stderr_path: Path,
) -> ChildResult:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=str(cwd),
                env=dict(env),
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        except OSError as exc:
            stderr.write(f"child launch failed: {type(exc).__name__}: {exc}\n".encode("utf-8"))
            return ChildResult(returncode=None, timed_out=False, launch_error=f"{type(exc).__name__}: {exc}")
        try:
            return ChildResult(returncode=process.wait(timeout=timeout_seconds), timed_out=False)
        except subprocess.TimeoutExpired:
            termination = _terminate_and_reap(process)
            return ChildResult(
                returncode=process.returncode,
                timed_out=True,
                termination=termination,
            )
        except BaseException as exc:
            termination = _terminate_and_reap(process)
            setattr(exc, "child_returncode", process.returncode)
            setattr(exc, "child_termination", termination)
            raise


_DEFAULT_EXECUTE_CHILD = execute_child


def _terminate_and_reap(process: subprocess.Popen[Any]) -> str:
    termination = "SIGTERM"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        termination = "SIGKILL"
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    return termination


def _read_summary(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, "summary_missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"summary_unreadable: {type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return {}, "summary_not_object"
    return value, None


def _artifact_hashes(out_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(out_dir)): _sha256_file(path)
        for path in sorted(out_dir.rglob("*"))
        if path.is_file()
    }


def _classification_name(summary: Mapping[str, Any]) -> str | None:
    classification = summary.get("classification")
    if isinstance(classification, Mapping):
        value = classification.get("classification")
        return str(value) if value is not None else None
    return str(classification) if classification is not None else None


def _cell_record(
    cell: Mapping[str, Any],
    *,
    argv: Sequence[str],
    out_dir: Path,
    result: ChildResult,
    args: argparse.Namespace,
    allow_injected_executor_contract: bool = False,
) -> dict[str, Any]:
    summary_path = argv_path(argv, "--manifest")
    summary, summary_error = _read_summary(summary_path)
    trace_value = summary.get("trace_path")
    trace_path = Path(trace_value) if isinstance(trace_value, str) else out_dir / "particle_readback_trace.jsonl"
    scene_value = summary.get("evidence_scene_path")
    scene_path = Path(scene_value) if isinstance(scene_value, str) else out_dir / "native_scene_completed_pbd_overlay.usda"
    classification = _classification_name(summary)
    verified = summary.get("visible_beaker_containment_verified") is True
    record: dict[str, Any] = {
        "cell_id": cell["cell_id"],
        "particle_count": int(cell["particle_count"]),
        "seed": int(cell["seed"]),
        "command": list(argv),
        "command_metadata_path": str(out_dir / "command.json"),
        "stdout_path": str(out_dir / "stdout.log"),
        "stderr_path": str(out_dir / "stderr.log"),
        "returncode": result.returncode,
        "returncode_warning": (
            None
            if result.returncode in (None, 0)
            else f"nonzero child returncode {result.returncode}; authoritative summary controls acceptance"
        ),
        "timed_out": result.timed_out,
        "termination": result.termination,
        "launch_error": result.launch_error,
        "summary_path": str(summary_path),
        "summary_error": summary_error,
        "trace_path": str(trace_path),
        "evidence_scene_path": str(scene_path),
        "classification": classification,
        "visible_beaker_containment_verified": verified,
        "strict_verified": verified,
        "strict_physics_execution": summary.get("strict_physics_execution"),
        "physics_settings": summary.get("physics_settings"),
        "stage_unit_contract": summary.get("stage_unit_contract"),
        "authored_runtime_paths": summary.get("authored_runtime_paths"),
        "physical_authoring_identity": summary.get("physical_authoring_identity"),
        "physical_trace_identity": summary.get("physical_trace_identity"),
        "step_schedule": _step_schedule_metadata(
            steps=args.steps,
            logical_dt=args.logical_dt,
            integration_dt=args.integration_dt,
            substeps_per_logical_step=args.substeps_per_logical_step,
        ),
        "physics_display_parameters": {
            "requested_logical_dt": args.logical_dt,
            "requested_integration_dt": args.integration_dt,
            "requested_substeps_per_logical_step": args.substeps_per_logical_step,
            "reported_physics_particle_offsets": summary.get("physics_particle_offsets"),
            "requested_display_particle_width": args.display_particle_width,
            "reported_display_particle_width": summary.get("display_particle_width"),
            "steps": args.steps,
            "trace_interval": args.trace_interval,
            "video_stride": args.video_stride,
            "video_fps": args.video_fps,
            "width": args.width,
            "height": args.height,
        },
    }
    record["artifact_hashes"] = _artifact_hashes(out_dir)
    record["accepted"] = (
        _contract_only_authoritative_pass(record)
        if allow_injected_executor_contract
        else cell_is_accepted(record)
    )
    return record


def _validate_args(args: argparse.Namespace) -> None:
    static_hold_cells(counts=args.counts, seeds=args.seeds)
    _validate_runtime_pins(
        steps=args.steps,
        logical_dt=args.logical_dt,
        integration_dt=args.integration_dt,
        substeps_per_logical_step=args.substeps_per_logical_step,
    )
    if args.trace_interval <= 0 or args.trace_interval > 30:
        raise ValueError("trace interval must be between 1 and 30")
    if not math.isfinite(args.runtime_timeout_seconds):
        raise ValueError("runtime timeout must be finite")
    if not math.isfinite(args.process_timeout_seconds):
        raise ValueError("process timeout must be finite")
    if args.runtime_timeout_seconds < 900:
        raise ValueError("runtime timeout must be at least 900 seconds")
    if args.process_timeout_seconds < args.runtime_timeout_seconds + 60.0:
        raise ValueError("process timeout must be at least 60 seconds above the child runtime timeout")


def _runtime_pins_match(
    *,
    steps: int,
    logical_dt: float,
    integration_dt: float,
    substeps_per_logical_step: int,
) -> bool:
    return (
        steps == REQUIRED_STEPS
        and math.isfinite(logical_dt)
        and logical_dt == REQUIRED_LOGICAL_DT
        and math.isfinite(integration_dt)
        and integration_dt == REQUIRED_INTEGRATION_DT
        and type(substeps_per_logical_step) is int
        and substeps_per_logical_step == REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
    )


def _validate_runtime_pins(
    *,
    steps: int,
    logical_dt: float,
    integration_dt: float,
    substeps_per_logical_step: int,
) -> None:
    if steps != REQUIRED_STEPS:
        raise ValueError(f"steps must be exactly {REQUIRED_STEPS}")
    if not math.isfinite(logical_dt) or logical_dt != REQUIRED_LOGICAL_DT:
        raise ValueError("logical dt must be exactly 1/60")
    if not math.isfinite(integration_dt) or integration_dt != REQUIRED_INTEGRATION_DT:
        raise ValueError("integration dt must be exactly 1/600")
    if (
        type(substeps_per_logical_step) is not int
        or substeps_per_logical_step != REQUIRED_SUBSTEPS_PER_LOGICAL_STEP
    ):
        raise ValueError("substeps must be exactly 10")


def _validate_fresh_cells(requested_cells: Sequence[Mapping[str, Any]]) -> None:
    requested_keys = tuple(_cell_key(cell) for cell in requested_cells)
    if requested_keys != CANONICAL_CELL_KEYS[: len(requested_keys)]:
        raise ValueError("fresh matrix cells must be a canonical prefix starting at index zero")


def _resolve_manifest_path(path_value: str | os.PathLike[str]) -> Path:
    path = Path(path_value).expanduser().resolve()
    immutable_paths = {
        (REPO_ROOT / relative).resolve() for relative in SUPERSEDED_FALSE_POSITIVE_MANIFESTS
    }
    if path in immutable_paths:
        raise ValueError(f"immutable legacy manifest path is superseded and read-only: {path}")
    return path


def _new_manifest(args: argparse.Namespace, run_identity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "fluid_spike_real_beaker_static_hold_matrix",
        "generated_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "run_identity": dict(run_identity),
        "step_schedule": _step_schedule_metadata(
            steps=args.steps,
            logical_dt=args.logical_dt,
            integration_dt=args.integration_dt,
            substeps_per_logical_step=args.substeps_per_logical_step,
        ),
        "requested_counts": list(args.counts),
        "requested_seeds": list(args.seeds),
        "required_cells": static_hold_cells(),
        "cells": [],
        "blocked_before_4096": False,
        "real_beaker_static_hold_closed": False,
        "superseded_false_positive_evidence": [
            {
                "path": path,
                "immutable": True,
                "accepted": False,
                "status": "superseded_false_positive",
            }
            for path in SUPERSEDED_FALSE_POSITIVE_MANIFESTS
        ],
    }


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _resolve_manifest_path(args.manifest)
    _validate_args(args)
    requested_cells = static_hold_cells(counts=args.counts, seeds=args.seeds)
    runtime_contract = resolve_isaac_usd_runtime()
    allow_contract_test_double = (
        runtime_contract.get("bootstrap_mode") == "test_isaacsim41"
        and execute_child is not _DEFAULT_EXECUTE_CHILD
    )
    env = build_isaac_child_env(os.environ, runtime_contract)
    env.setdefault("ACCEPT_EULA", "Y")
    env.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    runtime_preflight = preflight_isaac_usd_runtime(env, runtime_contract)
    run_identity = build_run_identity(
        args,
        isaac_usd_runtime=runtime_contract,
        isaac_usd_preflight=runtime_preflight,
    )
    if args.append:
        if not manifest_path.is_file():
            raise FileNotFoundError(f"append manifest does not exist: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_append_manifest(
            manifest,
            run_identity=run_identity,
            requested_cells=requested_cells,
        )
        manifest["requested_counts"] = sorted(
            set(manifest.get("requested_counts", ())).union(args.counts),
            key=lambda count: (count != 1024, count),
        )
        manifest["requested_seeds"] = sorted(
            set(manifest.get("requested_seeds", ())).union(args.seeds)
        )
    else:
        _validate_fresh_cells(requested_cells)
        manifest = _new_manifest(args, run_identity)

    out_root = Path(args.out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    existing_cells = manifest["cells"]
    wants_4096 = any(int(cell["particle_count"]) == 4096 for cell in requested_cells)
    for cell in requested_cells:
        if int(cell["particle_count"]) == 4096 and not all_required_1024_accepted(
            existing_cells,
            _allow_injected_executor_contract=allow_contract_test_double,
        ):
            manifest["blocked_before_4096"] = True
            break
        out_dir = out_root / str(cell["cell_id"])
        out_dir.mkdir(parents=True, exist_ok=False)
        argv = build_cell_argv(
            cell,
            out_dir=out_dir,
            usd=Path(args.usd).resolve(),
            steps=args.steps,
            logical_dt=args.logical_dt,
            integration_dt=args.integration_dt,
            substeps_per_logical_step=args.substeps_per_logical_step,
            trace_interval=args.trace_interval,
            runtime_timeout_seconds=args.runtime_timeout_seconds,
            video_stride=args.video_stride,
            video_fps=args.video_fps,
            width=args.width,
            height=args.height,
            display_particle_width=args.display_particle_width,
            headless=args.headless,
        )
        command_metadata = {
            "schema_version": 1,
            "cell": dict(cell),
            "argv": argv,
            "cwd": str(REPO_ROOT),
            "runtime_timeout_seconds": args.runtime_timeout_seconds,
            "process_timeout_seconds": args.process_timeout_seconds,
            "step_schedule": _step_schedule_metadata(
                steps=args.steps,
                logical_dt=args.logical_dt,
                integration_dt=args.integration_dt,
                substeps_per_logical_step=args.substeps_per_logical_step,
            ),
            "run_identity_sha256": _sha256_bytes(
                json.dumps(run_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ),
        }
        _atomic_write_json(out_dir / "command.json", command_metadata)
        stdout_path = out_dir / "stdout.log"
        stderr_path = out_dir / "stderr.log"
        stdout_path.touch()
        stderr_path.touch()
        try:
            result = execute_child(
                argv,
                cwd=REPO_ROOT,
                env=env,
                timeout_seconds=args.process_timeout_seconds,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        except BaseException as exc:
            with stderr_path.open("a", encoding="utf-8") as stream:
                stream.write(f"orchestrator child error: {type(exc).__name__}: {exc}\n")
            result = ChildResult(
                returncode=getattr(exc, "child_returncode", None),
                timed_out=False,
                termination=getattr(exc, "child_termination", None),
                launch_error=f"{type(exc).__name__}: {exc}",
            )
            existing_cells.append(
                _cell_record(
                    cell,
                    argv=argv,
                    out_dir=out_dir,
                    result=result,
                    args=args,
                    allow_injected_executor_contract=allow_contract_test_double,
                )
            )
            manifest["updated_at_utc"] = _utc_now()
            manifest["real_beaker_static_hold_closed"] = real_beaker_static_hold_closed(
                existing_cells,
                steps=args.steps,
                logical_dt=args.logical_dt,
                integration_dt=args.integration_dt,
                substeps_per_logical_step=args.substeps_per_logical_step,
                _allow_injected_executor_contract=allow_contract_test_double,
            )
            _atomic_write_json(manifest_path, manifest)
            raise
        existing_cells.append(
            _cell_record(
                cell,
                argv=argv,
                out_dir=out_dir,
                result=result,
                args=args,
                allow_injected_executor_contract=allow_contract_test_double,
            )
        )
        manifest["updated_at_utc"] = _utc_now()
        manifest["real_beaker_static_hold_closed"] = real_beaker_static_hold_closed(
            existing_cells,
            steps=args.steps,
            logical_dt=args.logical_dt,
            integration_dt=args.integration_dt,
            substeps_per_logical_step=args.substeps_per_logical_step,
            _allow_injected_executor_contract=allow_contract_test_double,
        )
        _atomic_write_json(manifest_path, manifest)

    if wants_4096 and not all_required_1024_accepted(
        existing_cells,
        _allow_injected_executor_contract=allow_contract_test_double,
    ):
        manifest["blocked_before_4096"] = True
    manifest["updated_at_utc"] = _utc_now()
    manifest["real_beaker_static_hold_closed"] = real_beaker_static_hold_closed(
        existing_cells,
        steps=args.steps,
        logical_dt=args.logical_dt,
        integration_dt=args.integration_dt,
        substeps_per_logical_step=args.substeps_per_logical_step,
        _allow_injected_executor_contract=allow_contract_test_double,
    )
    _atomic_write_json(manifest_path, manifest)
    return manifest


def build_dry_plan(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _resolve_manifest_path(args.manifest)
    _validate_args(args)
    requested_cells = static_hold_cells(counts=args.counts, seeds=args.seeds)
    if args.append:
        if not manifest_path.is_file():
            raise FileNotFoundError(f"append manifest does not exist: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _validate_append_cells(manifest.get("cells"), requested_cells)
    else:
        _validate_fresh_cells(requested_cells)
    cells = []
    for cell in requested_cells:
        out_dir = Path(args.out_root).resolve() / str(cell["cell_id"])
        cells.append(
            {
                **cell,
                "out_dir": str(out_dir),
                "manifest": str(out_dir / "runtime_smoke_summary.json"),
                "step_schedule": _step_schedule_metadata(
                    steps=args.steps,
                    logical_dt=args.logical_dt,
                    integration_dt=args.integration_dt,
                    substeps_per_logical_step=args.substeps_per_logical_step,
                ),
                "command": build_cell_argv(
                    cell,
                    out_dir=out_dir,
                    usd=Path(args.usd).resolve(),
                    steps=args.steps,
                    logical_dt=args.logical_dt,
                    integration_dt=args.integration_dt,
                    substeps_per_logical_step=args.substeps_per_logical_step,
                    trace_interval=args.trace_interval,
                    runtime_timeout_seconds=args.runtime_timeout_seconds,
                    video_stride=args.video_stride,
                    video_fps=args.video_fps,
                    width=args.width,
                    height=args.height,
                    display_particle_width=args.display_particle_width,
                    headless=args.headless,
                ),
            }
        )
    return {
        "dry_plan": True,
        "launches_performed": 0,
        "step_schedule": _step_schedule_metadata(
            steps=args.steps,
            logical_dt=args.logical_dt,
            integration_dt=args.integration_dt,
            substeps_per_logical_step=args.substeps_per_logical_step,
        ),
        "cells": cells,
        "4096_prerequisite": "all three accepted 1024 cells",
        "manifest": str(manifest_path),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", nargs="+", type=int, default=list(REQUIRED_COUNTS))
    parser.add_argument("--seeds", nargs="+", type=int, default=list(REQUIRED_SEEDS))
    parser.add_argument("--steps", type=int, default=REQUIRED_STEPS)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-plan", action="store_true")
    parser.add_argument("--usd", default=str(DEFAULT_USD))
    parser.add_argument("--logical-dt", type=float, default=REQUIRED_LOGICAL_DT)
    parser.add_argument("--integration-dt", type=float, default=REQUIRED_INTEGRATION_DT)
    parser.add_argument(
        "--substeps-per-logical-step",
        type=int,
        default=REQUIRED_SUBSTEPS_PER_LOGICAL_STEP,
    )
    parser.add_argument("--trace-interval", type=int, default=30)
    parser.add_argument("--runtime-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--process-timeout-seconds", type=float, default=1020.0)
    parser.add_argument("--video-stride", type=int, default=4)
    parser.add_argument("--video-fps", type=float, default=15.0)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--display-particle-width", type=float, default=0.0043)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.dry_plan:
        print(json.dumps(build_dry_plan(args), indent=2, sort_keys=True))
        return 0
    manifest = run_matrix(args)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    requested = set(_cell_key(cell) for cell in static_hold_cells(counts=args.counts, seeds=args.seeds))
    records = {_cell_key(cell): cell for cell in manifest["cells"]}
    return 0 if all(key in records and bool(records[key].get("accepted")) for key in requested) else 1


if __name__ == "__main__":
    raise SystemExit(main())

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


REPO_ROOT = Path(__file__).resolve().parents[2]
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
REQUIRED_PHYSICS_DT = 1.0 / 60.0
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


@dataclass(frozen=True)
class ChildResult:
    returncode: int | None
    timed_out: bool
    termination: str | None = None
    launch_error: str | None = None


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
        pxr_spec = importlib.util.find_spec("pxr")
    except (ImportError, AttributeError, ValueError):
        pxr_spec = None
    if pxr_spec is not None and pxr_spec.origin:
        origin = Path(pxr_spec.origin).expanduser().resolve()
        if origin.is_file():
            return {
                "bootstrap_mode": "already_importable",
                "pxr_origin": str(origin),
                "pxr_origin_sha256": _sha256_file(origin),
                "python_path_entry": None,
                "library_path_entry": None,
            }

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
        usd_python = usd_root / "pxr" / "Usd" / "__init__.py"
        library_root = usd_root / "bin"
        libtf = library_root / "libtf.so"
        libusd = library_root / "libusd.so"
        if all(path.is_file() for path in (usd_python, libtf, libusd)):
            return {
                "bootstrap_mode": "isaacsim_extcache",
                "pxr_origin": str(usd_python),
                "usd_python_sha256": _sha256_file(usd_python),
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
        env["PYTHONPATH"] = _prepend_env_path(python_path, env.get("PYTHONPATH"))
        env["LD_LIBRARY_PATH"] = _prepend_env_path(
            library_path, env.get("LD_LIBRARY_PATH")
        )
    return env


def preflight_isaac_usd_runtime(env: Mapping[str, str]) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pxr import Usd; print('.'.join(str(v) for v in Usd.GetVersion()))",
        ],
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
    if not stdout:
        raise RuntimeError("Isaac USD preflight failed: no USD version was reported")
    return stdout


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


def build_cell_argv(
    cell: Mapping[str, Any],
    *,
    out_dir: Path,
    usd: Path = DEFAULT_USD,
    steps: int = 600,
    physics_dt: float = 1.0 / 60.0,
    trace_interval: int = 30,
    runtime_timeout_seconds: float = 900.0,
    video_stride: int = 4,
    video_fps: float = 15.0,
    width: int = 960,
    height: int = 540,
    display_particle_width: float | None = None,
    headless: bool = False,
) -> list[str]:
    _validate_runtime_pins(steps=steps, physics_dt=physics_dt)
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
        "--physics-dt",
        repr(REQUIRED_PHYSICS_DT),
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


def build_run_identity(args: argparse.Namespace) -> dict[str, Any]:
    source_usd = Path(args.usd).resolve()
    if not source_usd.is_file():
        raise FileNotFoundError(f"source USD does not exist: {source_usd}")
    shared_cli_config = {
        "steps": args.steps,
        "physics_dt": args.physics_dt,
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
        "isaac_usd_runtime": resolve_isaac_usd_runtime(),
        "shared_cli_config": shared_cli_config,
    }


def _cell_key(cell: Mapping[str, Any]) -> tuple[int, int]:
    return int(cell["particle_count"]), int(cell["seed"])


def cell_is_accepted(record: Mapping[str, Any]) -> bool:
    return _has_authoritative_pass(record)


def _has_authoritative_pass(record: Mapping[str, Any]) -> bool:
    return (
        record.get("classification") == PASS_CLASSIFICATION
        and record.get("visible_beaker_containment_verified") is True
    )


def real_beaker_static_hold_closed(
    cells: Sequence[Mapping[str, Any]],
    *,
    steps: int = REQUIRED_STEPS,
    physics_dt: float = REQUIRED_PHYSICS_DT,
) -> bool:
    if not _runtime_pins_match(steps=steps, physics_dt=physics_dt):
        return False
    if tuple(_cell_key(cell) for cell in cells) != CANONICAL_CELL_KEYS:
        return False
    return all(_has_authoritative_pass(cell) for cell in cells)


def _accepted_1024_keys(cells: Sequence[Mapping[str, Any]]) -> set[tuple[int, int]]:
    return {
        _cell_key(cell)
        for cell in cells
        if int(cell.get("particle_count", -1)) == 1024
        and _has_authoritative_pass(cell)
    }


def all_required_1024_accepted(cells: Sequence[Mapping[str, Any]]) -> bool:
    return _accepted_1024_keys(cells) == {(1024, seed) for seed in REQUIRED_SEEDS}


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
        "physical_trace_identity": summary.get("physical_trace_identity"),
        "physics_display_parameters": {
            "requested_physics_dt": args.physics_dt,
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
    record["accepted"] = cell_is_accepted(record)
    record["artifact_hashes"] = _artifact_hashes(out_dir)
    return record


def _validate_args(args: argparse.Namespace) -> None:
    static_hold_cells(counts=args.counts, seeds=args.seeds)
    _validate_runtime_pins(steps=args.steps, physics_dt=args.physics_dt)
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


def _runtime_pins_match(*, steps: int, physics_dt: float) -> bool:
    return (
        steps == REQUIRED_STEPS
        and math.isfinite(physics_dt)
        and physics_dt == REQUIRED_PHYSICS_DT
    )


def _validate_runtime_pins(*, steps: int, physics_dt: float) -> None:
    if steps != REQUIRED_STEPS:
        raise ValueError(f"steps must be exactly {REQUIRED_STEPS}")
    if not math.isfinite(physics_dt) or physics_dt != REQUIRED_PHYSICS_DT:
        raise ValueError("physics dt must be exactly 1/60")


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
    run_identity = build_run_identity(args)
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
    env = build_isaac_child_env(os.environ, run_identity["isaac_usd_runtime"])
    env.setdefault("ACCEPT_EULA", "Y")
    env.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    preflight_isaac_usd_runtime(env)

    for cell in requested_cells:
        if int(cell["particle_count"]) == 4096 and not all_required_1024_accepted(existing_cells):
            manifest["blocked_before_4096"] = True
            break
        out_dir = out_root / str(cell["cell_id"])
        out_dir.mkdir(parents=True, exist_ok=False)
        argv = build_cell_argv(
            cell,
            out_dir=out_dir,
            usd=Path(args.usd).resolve(),
            steps=args.steps,
            physics_dt=args.physics_dt,
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
                _cell_record(cell, argv=argv, out_dir=out_dir, result=result, args=args)
            )
            manifest["updated_at_utc"] = _utc_now()
            manifest["real_beaker_static_hold_closed"] = real_beaker_static_hold_closed(
                existing_cells,
                steps=args.steps,
                physics_dt=args.physics_dt,
            )
            _atomic_write_json(manifest_path, manifest)
            raise
        existing_cells.append(
            _cell_record(cell, argv=argv, out_dir=out_dir, result=result, args=args)
        )
        manifest["updated_at_utc"] = _utc_now()
        manifest["real_beaker_static_hold_closed"] = real_beaker_static_hold_closed(
            existing_cells,
            steps=args.steps,
            physics_dt=args.physics_dt,
        )
        _atomic_write_json(manifest_path, manifest)

    if wants_4096 and not all_required_1024_accepted(existing_cells):
        manifest["blocked_before_4096"] = True
    manifest["updated_at_utc"] = _utc_now()
    manifest["real_beaker_static_hold_closed"] = real_beaker_static_hold_closed(
        existing_cells,
        steps=args.steps,
        physics_dt=args.physics_dt,
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
                "command": build_cell_argv(
                    cell,
                    out_dir=out_dir,
                    usd=Path(args.usd).resolve(),
                    steps=args.steps,
                    physics_dt=args.physics_dt,
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
    parser.add_argument("--physics-dt", type=float, default=REQUIRED_PHYSICS_DT)
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

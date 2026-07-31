"""Runtime-only recursive USD dependency closure helpers.

`UsdUtils` is passed in from a sealed Isaac child so importing this module does
not inspect USD outside the approved runtime boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


APPROVED_RUNTIME_MDL_DEPENDENCIES = (
    {
        "purpose": "kit_mdl_material_root",
        "path": (
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/"
            "site-packages/omni/mdl/core/Base/OmniGlass.mdl"
        ),
        "sha256": "d71555550deb30af245c0ec939c8647442df5709a2977549cad7f6ddcc8c1182",
    },
    {
        "purpose": "kit_mdl_material_root",
        "path": (
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/"
            "site-packages/omni/mdl/core/Base/OmniPBR.mdl"
        ),
        "sha256": "e0591cdda9f21eb61360a39919a82bbff8b8a872344d89c67e6b245dae974c3b",
    },
    {
        "purpose": "kit_mdl_material_root",
        "path": (
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/"
            "site-packages/omni/mdl/core/Base/OmniSurfacePresets.mdl"
        ),
        "sha256": "5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930",
    },
)
_MDL_STANDARD_LIBRARY_MODULES = frozenset(
    {"::anno", "::base", "::debug", "::df", "::limits", "::math", "::state", "::tex"}
)
_MDL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_MDL_LINE_COMMENT = re.compile(r"//[^\n]*")
_MDL_IMPORT = re.compile(
    r"(?m)^\s*(?:export\s+)?(?:import|using)\s+((?:::|\.::)?[A-Za-z_][A-Za-z0-9_:]*)"
)
_MDL_TEXTURE_RESOURCE = re.compile(
    r"""texture_2d\(\s*"((?:\./|\.\./)[^"]+)"\s*,"""
)


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file_under(path: Path, root: Path) -> bool:
    candidate = Path(path)
    if not candidate.is_absolute() or not candidate.is_relative_to(root):
        return False
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            return False
    try:
        return candidate.is_file() and candidate.resolve(strict=True) == candidate
    except OSError:
        return False


def _resolved_path(value: Any, *, entry_path: Path) -> Path | None:
    raw = str(
        getattr(value, "realPath", "")
        or getattr(value, "resolvedPath", "")
        or getattr(value, "path", "")
        or getattr(value, "identifier", "")
        or value
    )
    if not raw or raw.startswith("anon:") or "://" in raw:
        return None
    path = Path(raw)
    return (path if path.is_absolute() else entry_path.parent / path).resolve()


def _external_mdl_name(value: Any) -> str:
    raw = str(
        getattr(value, "resolvedPath", "")
        or getattr(value, "path", "")
        or getattr(value, "identifier", "")
        or value
    )
    return Path(raw.strip("@")).name


def _approved_mdl_reference(value: Any, *, approved_by_name: Mapping[str, Path]) -> Path | None:
    raw = str(
        getattr(value, "resolvedPath", "")
        or getattr(value, "path", "")
        or getattr(value, "identifier", "")
        or value
    ).strip("@")
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate if candidate in set(approved_by_name.values()) else None
    if len(candidate.parts) != 1:
        return None
    return approved_by_name.get(candidate.name)


def _runtime_mdl_records() -> tuple[dict[str, str], ...]:
    records = []
    for raw in APPROVED_RUNTIME_MDL_DEPENDENCIES:
        path = Path(raw["path"])
        if not _regular_file_under(path, path.parents[1]) or _sha256_file(path) != raw["sha256"]:
            raise RuntimeError("nonformal_usd_dependency_runtime_mdl_drift")
        records.append(dict(raw))
    return tuple(records)


def _mdl_import_modules(path: Path) -> tuple[str, ...]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError("nonformal_usd_dependency_runtime_mdl_decode_invalid") from exc
    source = _MDL_LINE_COMMENT.sub("", _MDL_BLOCK_COMMENT.sub("", source))
    return tuple(sorted({match.group(1).rstrip(":") for match in _MDL_IMPORT.finditer(source)}))


def _mdl_module_parts(module: str) -> tuple[bool, bool, tuple[str, ...]] | None:
    relative = module.startswith(".::")
    absolute = module.startswith("::")
    if relative:
        parts = module[3:].split("::")
    elif absolute:
        parts = module[2:].split("::")
    else:
        parts = module.split("::")
    if any(not part.isidentifier() for part in parts):
        return None
    return relative, absolute, tuple(parts)


def _mdl_module_candidates(
    module: str, *, owner: Path, repo_root: Path, mdl_root: Path
) -> tuple[Path, ...]:
    parsed = _mdl_module_parts(module)
    if parsed is None:
        return ()
    relative, absolute, parts = parsed
    bases = (
        (owner.parent,)
        if relative
        else (mdl_root / "mdl", repo_root)
        if absolute
        else (owner.parent, mdl_root / "Base", repo_root)
    )
    return tuple(
        base.joinpath(*parts[:count]).with_suffix(".mdl")
        for base in bases
        for count in range(len(parts), 0, -1)
    )


def _discover_mdl_closure(
    roots: Sequence[Path], *, repo_root: Path, mdl_root: Path, local_modules: Mapping[str, Path]
) -> tuple[set[Path], set[str], list[str], list[str]]:
    pending = list(sorted({Path(path) for path in roots}, reverse=True))
    closure: set[Path] = set()
    builtins: set[str] = set()
    unresolved: list[str] = []
    texture_unresolved: list[str] = []
    while pending:
        path = pending.pop()
        if path in closure:
            continue
        if not (
            _regular_file_under(path, repo_root) or _regular_file_under(path, mdl_root)
        ):
            unresolved.append(str(path))
            continue
        closure.add(path)
        for match in _MDL_TEXTURE_RESOURCE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            ref_path = Path(match.group(1))
            candidate = (path.parent / ref_path).resolve()
            if not candidate.is_file():
                texture_unresolved.append(f"{path}:{match.group(1)}")
        for module in _mdl_import_modules(path):
            resolved = next(
                (
                    candidate
                    for candidate in _mdl_module_candidates(
                        module,
                        owner=path,
                        repo_root=repo_root,
                        mdl_root=mdl_root,
                    )
                    if _regular_file_under(candidate, repo_root)
                    or _regular_file_under(candidate, mdl_root)
                ),
                None,
            )
            parsed = _mdl_module_parts(module)
            if resolved is None and parsed is not None and parsed[1]:
                resolved = local_modules.get(parsed[2][0])
            if resolved is None and parsed is not None and parsed[1]:
                for ancestor in path.parents:
                    if not ancestor.is_relative_to(repo_root):
                        break
                    candidate = ancestor.joinpath(parsed[2][0]).with_suffix(".mdl")
                    if _regular_file_under(candidate, repo_root):
                        resolved = candidate
                        break
            if resolved is not None:
                pending.append(resolved)
            elif module in _MDL_STANDARD_LIBRARY_MODULES:
                builtins.add(module)
            else:
                unresolved.append(f"{path}:{module}")
    return closure, builtins, unresolved, texture_unresolved


def validate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "entries",
        "files",
        "runtime_mdl_files",
        "runtime_mdl_builtin_modules",
        "unresolved",
        "texture_unresolved",
        "sha256",
    }:
        raise ValueError("nonformal_usd_dependency_closure_invalid")
    raw_entries = value.get("entries")
    raw_files = value.get("files")
    raw_mdl_files = value.get("runtime_mdl_files")
    raw_mdl_builtins = value.get("runtime_mdl_builtin_modules")
    raw_unresolved = value.get("unresolved")
    raw_texture_unresolved = value.get("texture_unresolved")
    if (
        not isinstance(raw_entries, list)
        or not raw_entries
        or not isinstance(raw_files, list)
        or not isinstance(raw_mdl_files, list)
        or not isinstance(raw_mdl_builtins, list)
        or not isinstance(raw_unresolved, list)
        or not isinstance(raw_texture_unresolved, list)
        or not isinstance(value.get("sha256"), str)
    ):
        raise ValueError("nonformal_usd_dependency_closure_invalid")
    entries = []
    for entry in raw_entries:
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"id", "path", "sha256"}
            or not isinstance(entry.get("id"), str)
            or not entry["id"]
            or not isinstance(entry.get("path"), str)
            or not Path(entry["path"]).is_absolute()
            or not isinstance(entry.get("sha256"), str)
            or len(entry["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in entry["sha256"])
        ):
            raise ValueError("nonformal_usd_dependency_closure_invalid")
        entries.append(dict(entry))
    files = []
    for file in raw_files:
        if (
            not isinstance(file, Mapping)
            or set(file) != {"path", "byte_count", "sha256"}
            or not isinstance(file.get("path"), str)
            or not Path(file["path"]).is_absolute()
            or type(file.get("byte_count")) is not int
            or file["byte_count"] < 0
            or not isinstance(file.get("sha256"), str)
            or len(file["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in file["sha256"])
        ):
            raise ValueError("nonformal_usd_dependency_closure_invalid")
        files.append(dict(file))
    mdl_files = []
    for record in raw_mdl_files:
        if (
            not isinstance(record, Mapping)
            or set(record) != {"purpose", "path", "byte_count", "sha256"}
            or record.get("purpose") not in {"kit_mdl_material_root", "kit_mdl_material_dependency"}
            or not isinstance(record.get("path"), str)
            or not Path(record["path"]).is_absolute()
            or type(record.get("byte_count")) is not int
            or record["byte_count"] < 0
            or not isinstance(record.get("sha256"), str)
            or len(record["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in record["sha256"])
        ):
            raise ValueError("nonformal_usd_dependency_closure_invalid")
        mdl_files.append(dict(record))
    mdl_builtins = list(raw_mdl_builtins)
    unresolved = list(raw_unresolved)
    texture_unresolved = list(raw_texture_unresolved)
    if (
        len({entry["id"] for entry in entries}) != len(entries)
        or files != sorted(files, key=lambda item: item["path"])
        or len({file["path"] for file in files}) != len(files)
        or mdl_files != sorted(mdl_files, key=lambda item: item["path"])
        or len({file["path"] for file in mdl_files}) != len(mdl_files)
        or mdl_builtins != sorted(set(mdl_builtins))
        or any(item not in _MDL_STANDARD_LIBRARY_MODULES for item in mdl_builtins)
        or unresolved != sorted(set(unresolved))
        or any(not isinstance(item, str) or not item for item in unresolved)
        or texture_unresolved != sorted(set(texture_unresolved))
        or any(not isinstance(item, str) or not item for item in texture_unresolved)
        or any(
            not any(file["path"] == entry["path"] and file["sha256"] == entry["sha256"] for file in files)
            for entry in entries
        )
    ):
        raise ValueError("nonformal_usd_dependency_closure_invalid")
    payload = {
        "entries": entries,
        "files": files,
        "runtime_mdl_files": mdl_files,
        "runtime_mdl_builtin_modules": mdl_builtins,
        "unresolved": unresolved,
        "texture_unresolved": texture_unresolved,
    }
    if value["sha256"] != canonical_json_sha256(payload):
        raise ValueError("nonformal_usd_dependency_closure_invalid")
    return {**payload, "sha256": value["sha256"]}


def discover(
    entries: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path,
    UsdUtils: Any,
) -> dict[str, Any]:
    """Resolve all local USD layers/assets from explicitly sealed entry files."""
    root = Path(repo_root).resolve()
    normalized_entries = []
    known_paths: set[Path] = set()
    unresolved: list[str] = []
    approved_mdls = _runtime_mdl_records()
    mdl_root = Path(approved_mdls[0]["path"]).parents[1]
    mdl_by_name = {Path(record["path"]).name: Path(record["path"]) for record in approved_mdls}
    for raw_entry in entries:
        if not isinstance(raw_entry, Mapping) or set(raw_entry) != {"id", "path", "sha256"}:
            raise ValueError("nonformal_usd_dependency_entry_invalid")
        identifier = raw_entry.get("id")
        raw_path = raw_entry.get("path")
        digest = raw_entry.get("sha256")
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(raw_path, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("nonformal_usd_dependency_entry_invalid")
        path = Path(raw_path)
        if not _regular_file_under(path, root) or _sha256_file(path) != digest:
            raise RuntimeError("nonformal_usd_dependency_entry_drift")
        normalized_entries.append({"id": identifier, "path": str(path), "sha256": digest})
        known_paths.add(path)
    if len({entry["id"] for entry in normalized_entries}) != len(normalized_entries):
        raise ValueError("nonformal_usd_dependency_entry_invalid")
    for entry in normalized_entries:
        entry_path = Path(entry["path"])
        layers, assets, missing = UsdUtils.ComputeAllDependencies(str(entry_path))
        for item in missing:
            if _approved_mdl_reference(item, approved_by_name=mdl_by_name) is None:
                unresolved.append(f"{entry['id']}:{item}")
        for value in (*layers, *assets):
            path = _resolved_path(value, entry_path=entry_path)
            if path is not None and _regular_file_under(path, root):
                known_paths.add(path)
            else:
                mdl_path = _approved_mdl_reference(value, approved_by_name=mdl_by_name)
                if mdl_path is None:
                    unresolved.append(f"{entry['id']}:{value}")
    local_mdl_roots = tuple(path for path in known_paths if path.suffix.lower() == ".mdl")
    local_module_candidates: dict[str, list[Path]] = {}
    for path in local_mdl_roots:
        local_module_candidates.setdefault(path.stem, []).append(path)
    local_modules = {
        name: paths[0] for name, paths in local_module_candidates.items() if len(paths) == 1
    }
    mdl_paths, mdl_builtins, mdl_unresolved, texture_unresolved = _discover_mdl_closure(
        (*mdl_by_name.values(), *local_mdl_roots),
        repo_root=root,
        mdl_root=mdl_root,
        local_modules=local_modules,
    )
    unresolved.extend(mdl_unresolved)
    known_paths.update(path for path in mdl_paths if _regular_file_under(path, root))
    files = [
        {
            "path": str(path),
            "byte_count": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(known_paths, key=str)
    ]
    root_mdl_paths = set(mdl_by_name.values())
    runtime_mdl_files = [
        {
            "purpose": "kit_mdl_material_root"
            if path in root_mdl_paths
            else "kit_mdl_material_dependency",
            "path": str(path),
            "byte_count": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(
            (path for path in mdl_paths if _regular_file_under(path, mdl_root)),
            key=str,
        )
    ]
    payload = {
        "entries": normalized_entries,
        "files": files,
        "runtime_mdl_files": runtime_mdl_files,
        "runtime_mdl_builtin_modules": sorted(mdl_builtins),
        "unresolved": sorted(set(unresolved)),
        "texture_unresolved": sorted(set(texture_unresolved)),
    }
    return validate({**payload, "sha256": canonical_json_sha256(payload)})

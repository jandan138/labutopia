from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from utils import nonformal_usd_dependency_resolution as resolution


def test_resolver_hashes_recursive_local_dependencies_and_preserves_missing_arcs():
    class Asset:
        def __init__(self, path: Path):
            self.realPath = str(path)

    class UsdUtils:
        @staticmethod
        def ComputeAllDependencies(path: str):
            root = Path(path)
            return [Asset(root.parent / "nested.usda")], [], ["missing.usda"]

    with TemporaryDirectory(dir="/tmp/opencode") as directory:
        root = Path(directory)
        entry = root / "entry.usda"
        nested = root / "nested.usda"
        entry.write_text("#usda 1.0\n", encoding="ascii")
        nested.write_text("#usda 1.0\n", encoding="ascii")
        digest = resolution._sha256_file(entry)

        closure = resolution.discover(
            [{"id": "scene", "path": str(entry), "sha256": digest}],
            repo_root=root,
            UsdUtils=UsdUtils,
        )

    assert [record["path"] for record in closure["files"]] == [str(entry), str(nested)]
    assert closure["unresolved"] == ["scene:missing.usda"]
    assert closure["sha256"] == resolution.canonical_json_sha256(
        {key: value for key, value in closure.items() if key != "sha256"}
    )


def test_mdl_asset_paths_are_matched_without_usd_asset_delimiters():
    class Asset:
        path = "@OmniPBR.mdl@"

    assert resolution._external_mdl_name(Asset()) == "OmniPBR.mdl"


def test_foreign_mdl_path_is_not_accepted_by_basename():
    class Asset:
        path = "/tmp/OmniPBR.mdl"

    approved = {"OmniPBR.mdl": Path("/approved/OmniPBR.mdl")}
    assert resolution._approved_mdl_reference(Asset(), approved_by_name=approved) is None

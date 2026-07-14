import hashlib
import json
from pathlib import Path

import pytest

from tools.labutopia_fluid.fluid_recipe import (
    RECIPE_DEFAULT_PARTICLE_COUNT,
    RECIPE_MANIFEST_BASENAME,
    RECIPE_USD_BASENAME,
    RECIPE_WRAPPER_VARIANT_ID,
    SOURCE_USD_REL,
    build_recipe_manifest,
)
from tools.labutopia_fluid.run_export_fluid_recipe_usd import (
    CONTROLLED_SPAWN_POSITIONS_BASENAME,
    export_fluid_recipe_usd,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_recipe_manifest_defaults():
    manifest = build_recipe_manifest(particle_count=RECIPE_DEFAULT_PARTICLE_COUNT)
    assert manifest["raw_colleague_points_used"] is False
    assert manifest["particle_count"] == 4096
    assert manifest["wrapper_variant_id"] == "D4A_018"
    assert manifest["controlled_spawn"] is True


def test_export_dry_run_writes_manifest_not_usd(tmp_path):
    summary = export_fluid_recipe_usd(
        out_dir=tmp_path,
        dry_run=True,
        repo_root=REPO_ROOT,
    )

    assert summary["dry_run"] is True
    assert summary["raw_colleague_points_used"] is False
    assert summary["particle_count"] == 4096
    assert summary["wrapper_variant_id"] == RECIPE_WRAPPER_VARIANT_ID
    assert (tmp_path / RECIPE_MANIFEST_BASENAME).is_file()
    assert (tmp_path / CONTROLLED_SPAWN_POSITIONS_BASENAME).is_file()
    assert not (tmp_path / RECIPE_USD_BASENAME).exists()

    manifest = json.loads((tmp_path / RECIPE_MANIFEST_BASENAME).read_text(encoding="utf-8"))
    assert manifest["raw_colleague_points_used"] is False
    assert manifest["particle_count"] == 4096
    assert manifest["wrapper_variant_id"] == "D4A_018"
    assert manifest["controlled_spawn"] is True
    assert manifest["positions_hash"]

    positions = json.loads((tmp_path / CONTROLLED_SPAWN_POSITIONS_BASENAME).read_text(encoding="utf-8"))
    assert len(positions) == 4096
    assert all(len(point) == 3 for point in positions)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def source_usd_path_fixture() -> Path:
    path = REPO_ROOT / SOURCE_USD_REL
    if not path.is_file():
        pytest.skip(f"source usd missing: {path}")
    return path


def test_export_does_not_modify_source_usd(tmp_path, source_usd_path_fixture):
    before = _file_sha256(source_usd_path_fixture)

    export_fluid_recipe_usd(
        out_dir=tmp_path / "dry",
        dry_run=True,
        repo_root=REPO_ROOT,
    )
    assert _file_sha256(source_usd_path_fixture) == before

    try:
        import pxr  # noqa: F401
    except ImportError:
        pytest.skip("pxr unavailable for USD export path")

    export_fluid_recipe_usd(
        out_dir=tmp_path / "full",
        dry_run=False,
        repo_root=REPO_ROOT,
    )
    assert _file_sha256(source_usd_path_fixture) == before
    assert (tmp_path / "full" / RECIPE_USD_BASENAME).is_file()

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.labutopia_fluid import run_real_pbd_grasp_v2_preflight as preflight


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_static_preflight_seals_authored_zero_particle_mass_as_g0_no_go():
    report = preflight.build_static_preflight_report(
        asset_path=preflight.DEFAULT_ASSET,
        fixture={
            "source_dry_mass_kg": 0.02,
            "particle_density_kg_m3": 0.0,
            "particle_mass_kg": 0.0,
            "particle_count": 3600,
            "wrapper_collider_count": 145,
            "wrapper_collider_paths": ["/World/beaker2/FluidSafeWrapperCanonical/panel_000"],
        },
    )

    assert report["asset_path"] == str(preflight.DEFAULT_ASSET.resolve())
    assert report["evaluation"]["g0_decision"] == "G0_NO_GO"
    assert report["evaluation"]["g3_g4_filled_load_authorized"] is False
    assert "authored_particle_mass_and_density_nonpositive" in report["evaluation"][
        "no_go_reasons"
    ]


def test_preflight_create_only_writer_never_replaces_existing_results(tmp_path):
    output = tmp_path / "report.json"
    preflight.atomic_create_bytes(output, b'{"first":true}\n')

    with pytest.raises(FileExistsError, match="real_pbd_preflight_output_exists"):
        preflight.atomic_create_bytes(output, b'{"replacement":true}\n')
    assert json.loads(output.read_text(encoding="utf-8")) == {"first": True}


def test_preflight_failure_still_emits_a_typed_g0_no_go_artifact(tmp_path):
    out_dir = tmp_path / "missing-asset-output"

    assert preflight.run_preflight(
        asset_path=tmp_path / "missing.usda", out_dir=out_dir
    ) == 2

    report = json.loads((out_dir / preflight.REPORT_BASENAME).read_text(encoding="utf-8"))
    artifact = json.loads(
        (out_dir / preflight.G0_ARTIFACT_BASENAME).read_text(encoding="utf-8")
    )
    assert report["authority"] == "real_pbd_static_fixture_preflight_error_v1"
    assert report["decision"] == "G0_NO_GO"
    assert artifact["decision"] == "G0_NO_GO"


def test_preflight_runner_stays_outside_isaac_runtime():
    source = Path(preflight.__file__).read_text(encoding="utf-8")

    for forbidden in ("import isaacsim", "from isaacsim", "import omni", "from omni"):
        assert forbidden not in source

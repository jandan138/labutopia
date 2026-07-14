from tools.labutopia_fluid.run_fluid_recipe_dual_render_smoke import build_cell_argv, dual_render_cells


def test_dual_render_cells_leadership_is_particle_omniglass():
    cells = dual_render_cells(particle_count=4096)
    assert len(cells) == 2
    assert cells[0]["cell_id"] == "RECIPE_P4096_OMNIGLASS"
    assert cells[0]["presentation_render_mode"] == "particle_omniglass"
    assert cells[0]["leadership_default"] is True
    assert cells[1]["cell_id"] == "RECIPE_P4096_ISOSURFACE"
    assert cells[1]["presentation_render_mode"] == "isosurface"
    assert cells[1]["leadership_default"] is False


def test_build_cell_argv_wires_controlled_spawn_and_render_mode(tmp_path):
    cell = dual_render_cells()[0]
    argv = build_cell_argv(cell, usd=tmp_path / "x.usd", out_dir=tmp_path / "out")
    assert "--presentation-render-mode" in argv
    assert "particle_omniglass" in argv
    assert "--controlled-spawn-count" in argv
    assert "4096" in argv
    assert "--fluid-safe-wrapper-overlay" in argv
    assert "--presentation-isosurface-video" not in argv

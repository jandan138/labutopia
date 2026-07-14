from tools.labutopia_fluid.run_weekly_omniglass_look_matrix import (
    MATRIX_CELLS,
    build_matrix_manifest,
)


def test_matrix_cells_include_pass_window_and_dense_rungs():
    assert [c["cell_id"] for c in MATRIX_CELLS] == [
        "B_P1024",
        "B_P4096",
        "B_P50000",
        "C_P1024",
        "C_P4096",
        "C_P50000",
    ]


def test_build_matrix_manifest_marks_not_official_visual_a():
    m = build_matrix_manifest(
        cells=[{"cell_id": "B_P4096", "classification": "PASS_SOURCE_HOLD"}]
    )
    assert m["weekly_omniglass_matrix_is_visual_diagnostic_not_official_visual_a"] is True
    assert m["official_visual_a_clearwater_unchanged"] is True
    assert "colleague_50k_overlay_equals_g1_zero_leak" in m["forbidden_claims"]
    assert m["human_visual_qa_status"] == "pending"

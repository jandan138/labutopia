import math

import pytest

from tools.labutopia_fluid.run_standalone_particle_smoke import (
    SmokeConfig,
    build_particle_grid,
    classify_smoke,
    summarize_particle_readback,
)


def test_build_particle_grid_produces_requested_count_and_bounds():
    positions = build_particle_grid(
        count=10,
        dims=(3, 3, 3),
        lower=(0.0, 1.0, -0.1),
        spacing=0.005,
    )

    assert len(positions) == 10
    assert positions[0] == (0.0, 1.0, -0.1)
    assert positions[-1] == (0.005, 1.0, -0.1)
    assert len(set(positions)) == 10


def test_summarize_particle_readback_records_counts_motion_and_nan():
    initial = [(0.0, 1.0, 0.0), (0.1, 1.0, 0.0)]
    final = [(0.0, 0.9, 0.0), (math.nan, 1.0, 0.0)]

    summary = summarize_particle_readback(initial, final)

    assert summary["particle_count_initial"] == 2
    assert summary["particle_count_final"] == 2
    assert summary["particle_count_final_fraction"] == 1.0
    assert summary["nan_count"] == 1
    assert summary["initial_aabb"]["min"] == [0.0, 1.0, 0.0]
    assert summary["initial_aabb"]["max"] == [0.1, 1.0, 0.0]
    assert summary["final_aabb"]["min"] == [0.0, 0.9, 0.0]
    assert summary["final_aabb"]["max"] == [0.0, 0.9, 0.0]
    assert summary["mean_delta_y"] == pytest.approx(-0.1)


def test_classify_smoke_requires_gpu_readback_count_and_no_nan():
    config = SmokeConfig(particle_count=256)
    good_summary = {
        "particle_count_initial": 256,
        "particle_count_final": 256,
        "particle_count_final_fraction": 1.0,
        "nan_count": 0,
    }

    passed = classify_smoke(
        config=config,
        readback_summary=good_summary,
        gpu_dynamics_enabled=True,
        readback_available=True,
        fatal_error=None,
        particle_schema_supported=True,
    )

    assert passed["status"] == "GO_NEXT"
    assert passed["failure_class"] is None
    assert passed["true_fluid_runtime_claim_allowed"] is True

    no_gpu = classify_smoke(
        config=config,
        readback_summary=good_summary,
        gpu_dynamics_enabled=False,
        readback_available=True,
        fatal_error=None,
        particle_schema_supported=True,
    )

    assert no_gpu["status"] == "STOP_WITH_EVIDENCE"
    assert no_gpu["failure_class"] == "GPU_DYNAMICS_DISABLED"
    assert no_gpu["true_fluid_runtime_claim_allowed"] is False

    with_nan = dict(good_summary, nan_count=1)
    failed_nan = classify_smoke(
        config=config,
        readback_summary=with_nan,
        gpu_dynamics_enabled=True,
        readback_available=True,
        fatal_error=None,
        particle_schema_supported=True,
    )

    assert failed_nan["status"] == "STOP_WITH_EVIDENCE"
    assert failed_nan["failure_class"] == "READBACK_UNAVAILABLE"

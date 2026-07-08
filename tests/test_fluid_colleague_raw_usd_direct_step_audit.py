from tools.labutopia_fluid.run_colleague_raw_usd_direct_step_audit import (
    _json_safe,
    classify_raw_direct_step_audit,
    is_finite_nonzero_gravity,
    summarize_numeric_sequence,
)


def test_is_finite_nonzero_gravity_rejects_zero_and_infinite_values():
    assert is_finite_nonzero_gravity((0.0, 0.0, -1.0), 9.81)
    assert not is_finite_nonzero_gravity((0.0, 0.0, 0.0), 9.81)
    assert not is_finite_nonzero_gravity((0.0, 0.0, -1.0), float("-inf"))


def test_summarize_numeric_sequence_records_count_and_range():
    summary = summarize_numeric_sequence([0.2, 0.1, 0.3])

    assert summary == {
        "count": 3,
        "finite_count": 3,
        "min": 0.1,
        "max": 0.3,
        "unique_preview": [0.1, 0.2, 0.3],
    }


def test_json_safe_preserves_nonfinite_values_as_strict_json_strings():
    payload = _json_safe({"gravity_magnitude": float("-inf"), "values": [float("inf"), float("nan"), 1.0]})

    assert payload == {
        "gravity_magnitude": "-Infinity",
        "values": ["Infinity", "NaN", 1.0],
    }


def test_classify_raw_direct_step_audit_stops_on_incomplete_raw_schema():
    result = classify_raw_direct_step_audit(
        raw_runtime_contract_complete=False,
        readback_available=True,
        readback_position_changed=True,
        particle_count_initial=50000,
        particle_count_final=50000,
        nan_count=0,
        fatal_error=None,
        perf_budget_exceeded=False,
    )

    assert result["status"] == "STOP_WITH_EVIDENCE"
    assert result["classification"] == "STOP_RAW_RUNTIME_INCOMPLETE"
    assert result["direct_original_50k_runtime_claim_allowed"] is False


def test_classify_raw_direct_step_audit_stops_when_readback_static():
    result = classify_raw_direct_step_audit(
        raw_runtime_contract_complete=True,
        readback_available=True,
        readback_position_changed=False,
        particle_count_initial=50000,
        particle_count_final=50000,
        nan_count=0,
        fatal_error=None,
        perf_budget_exceeded=False,
    )

    assert result["classification"] == "STOP_READBACK_UNAVAILABLE"
    assert result["pass_criteria"]["readback_position_changed"] is False


def test_classify_raw_direct_step_audit_passes_only_complete_moving_stable_raw_runtime():
    result = classify_raw_direct_step_audit(
        raw_runtime_contract_complete=True,
        readback_available=True,
        readback_position_changed=True,
        particle_count_initial=50000,
        particle_count_final=49950,
        nan_count=0,
        fatal_error=None,
        perf_budget_exceeded=False,
    )

    assert result["status"] == "GO_NEXT"
    assert result["classification"] == "PASS_RAW_DIRECT_STEP_RUNTIME"
    assert result["direct_original_50k_runtime_claim_allowed"] is True

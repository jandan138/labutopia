import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.labutopia_fluid import run_build_support_aligned_authority_bundle as authority


REPO_ROOT = Path(__file__).resolve().parents[1]
SUPPORT_ROOT = (
    REPO_ROOT
    / "outputs"
    / "usd_asset_packages"
    / "lab_001_level1_pour_support_aligned_v1_20260712"
)
SUPPORT_MANIFEST_PATH = SUPPORT_ROOT / "support_aligned_manifest.json"
RUNTIME_ROOT = (
    REPO_ROOT
    / "docs"
    / "labutopia_lab_poc"
    / "evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712"
    / "P4096_S2"
)
SUMMARY_PATH = RUNTIME_ROOT / "runtime_smoke_summary.json"
TRACE_PATH = RUNTIME_ROOT / "particle_readback_trace.jsonl"
RUNTIME_SCENE_PATH = RUNTIME_ROOT / "native_scene_completed_pbd_overlay.usda"
RUNNER_PATH = (
    REPO_ROOT
    / "tools"
    / "labutopia_fluid"
    / "run_colleague_native_usd_completed_pbd_step_video.py"
)
AUTHORITY_TOOL_PATH = (
    REPO_ROOT
    / "tools"
    / "labutopia_fluid"
    / "run_build_support_aligned_authority_bundle.py"
)

ACTUAL_EVIDENCE_PATHS = (
    SUPPORT_MANIFEST_PATH,
    SUMMARY_PATH,
    TRACE_PATH,
    RUNTIME_SCENE_PATH,
)
requires_actual_authority_evidence = pytest.mark.skipif(
    not all(path.is_file() for path in ACTUAL_EVIDENCE_PATHS),
    reason="requires local support-aligned runtime evidence",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _small_trace_bytes() -> bytes:
    records = []
    for step in (0, 30, 60):
        records.append(
            {
                "aabb": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
                "centroid": [0.5, 0.5, 0.5],
                "nan_count": 0,
                "particle_count": 2,
                "positions": [[0.0, 0.0, step / 60.0], [1.0, 1.0, 1.0]],
                "region_counts": {
                    "below_table_count": 0,
                    "finite_count": 2,
                    "source_count": 2,
                    "spill_count": 0,
                    "target_count": 0,
                    "total_count": 2,
                },
                "step_index": step,
                "strict_visible_beaker_counts": {
                    "above_visible_rim_count": 0,
                    "below_visible_floor_count": 0,
                    "canonical_axial_max": 1.0,
                    "canonical_axial_median": 0.5,
                    "canonical_axial_min": 0.0,
                    "finite_count": 2,
                    "inside_visible_interior_count": 2,
                    "legacy_source_region_count": 2,
                    "maximum_canonical_radius": 1.0,
                    "nonfinite_count": 0,
                    "outside_visible_radial_count": 0,
                    "particle_count": 2,
                    "strict_violating_point_count": 0,
                },
            }
        )
    return b"".join(
        json.dumps(record, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
        for record in records
    )


def test_trace_identity_is_recomputed_from_strict_schema_and_exact_cadence():
    identity = authority.recompute_strict_trace_identity(
        _small_trace_bytes(),
        source_usd_sha256="1" * 64,
        particle_count=2,
        seed=7,
        steps=60,
        trace_interval=30,
    )

    assert identity["frame_indices"] == [0, 30, 60]
    assert identity["frame_particle_counts"] == [2, 2, 2]
    assert identity["source_usd_sha256"] == "1" * 64
    assert len(identity["positions_sha256"]) == 64
    assert len(identity["physical_trace_sha256"]) == 64
    assert len(identity["strict_trace_schema_sha256"]) == 64

    records = _small_trace_bytes().splitlines()
    with pytest.raises(ValueError, match="trace_frame_cadence_invalid"):
        authority.recompute_strict_trace_identity(
            b"\n".join((records[0], records[2])) + b"\n",
            source_usd_sha256="1" * 64,
            particle_count=2,
            seed=7,
            steps=60,
            trace_interval=30,
        )

    malformed = [json.loads(line) for line in _small_trace_bytes().splitlines()]
    malformed[0]["centroid"] = [0.0, 0.0]
    malformed_payload = b"".join(
        json.dumps(record, sort_keys=True).encode("utf-8") + b"\n"
        for record in malformed
    )
    with pytest.raises(ValueError, match="trace_centroid_invalid"):
        authority.recompute_strict_trace_identity(
            malformed_payload,
            source_usd_sha256="1" * 64,
            particle_count=2,
            seed=7,
            steps=60,
            trace_interval=30,
        )

    malformed = [json.loads(line) for line in _small_trace_bytes().splitlines()]
    malformed[0]["region_counts"]["below_table_count"] = True
    malformed_payload = b"".join(
        json.dumps(record, sort_keys=True).encode("utf-8") + b"\n"
        for record in malformed
    )
    with pytest.raises(ValueError, match="trace_region_count_invalid"):
        authority.recompute_strict_trace_identity(
            malformed_payload,
            source_usd_sha256="1" * 64,
            particle_count=2,
            seed=7,
            steps=60,
            trace_interval=30,
        )


def test_declared_kit_log_segment_binds_full_log_and_exact_byte_range(tmp_path):
    log_path = tmp_path / "kit.log"
    log_path.write_bytes(b"prefix-DECLARED-SEGMENT-suffix")
    offset = len(b"prefix-")
    segment = b"DECLARED-SEGMENT"
    declared = {
        "byte_offset": offset,
        "segment_byte_count": len(segment),
        "segment_sha256": hashlib.sha256(segment).hexdigest(),
        "cursor_captured": True,
        "diagnostic_scan_complete": True,
    }

    snapshot = authority.snapshot_declared_kit_log(log_path, declared)

    assert snapshot["full_log_bytes"] == log_path.read_bytes()
    assert snapshot["segment_bytes"] == segment
    assert snapshot["provenance"]["source_log_full_sha256"] == _sha256(log_path)
    assert snapshot["provenance"]["source_log_byte_count"] == log_path.stat().st_size
    assert snapshot["provenance"]["segment_sha256"] == declared["segment_sha256"]

    changed = dict(declared, segment_byte_count=len(segment) - 1)
    with pytest.raises(ValueError, match="kit_log_segment_sha256_mismatch"):
        authority.snapshot_declared_kit_log(log_path, changed)


@requires_actual_authority_evidence
def test_actual_runtime_particle_graph_has_one_enabled_completed_pbd_authority():
    support_manifest = json.loads(SUPPORT_MANIFEST_PATH.read_text())

    graph = authority.enumerate_runtime_particle_graph(
        runtime_scene_path=RUNTIME_SCENE_PATH,
        support_entry_path=Path(support_manifest["support_entry_root_usd_path"]),
    )

    assert graph["verified"] is True
    assert graph["enabled_particle_system_paths"] == [
        "/World/CompletedPBD/ParticleSystem"
    ]
    assert graph["active_particle_set_paths"] == [
        "/World/CompletedPBD/ParticleSet"
    ]
    assert graph["active_sampler_paths"] == []
    assert graph["legacy_graph"]["sampler_targets"] == []
    assert graph["legacy_graph"]["particle_system_targets"] == []
    assert graph["legacy_graph"]["particle_system_enabled"] is False
    assert len(graph["runtime_particle_graph_sha256"]) == 64


@requires_actual_authority_evidence
def test_runtime_summary_rejects_any_visible_leak_or_source_identity_drift():
    summary = json.loads(SUMMARY_PATH.read_text())
    support_manifest = json.loads(SUPPORT_MANIFEST_PATH.read_text())
    identity = authority.recompute_strict_trace_identity(
        TRACE_PATH.read_bytes(),
        source_usd_sha256=support_manifest["support_entry_root_usd_sha256"],
        particle_count=4096,
        seed=2,
        steps=600,
        trace_interval=30,
    )
    authority.validate_runtime_summary(
        summary,
        trace_identity=identity,
        support_entry_path=Path(support_manifest["support_entry_root_usd_path"]),
        support_entry_sha256=support_manifest["support_entry_root_usd_sha256"],
        runner_script_sha256=_sha256(RUNNER_PATH),
    )

    leaking = copy.deepcopy(summary)
    leaking["strict_visible_classification"]["max_below_floor"] = 1
    with pytest.raises(ValueError, match="runtime_visible_containment_failed"):
        authority.validate_runtime_summary(
            leaking,
            trace_identity=identity,
            support_entry_path=Path(support_manifest["support_entry_root_usd_path"]),
            support_entry_sha256=support_manifest["support_entry_root_usd_sha256"],
            runner_script_sha256=_sha256(RUNNER_PATH),
        )

    wrong_source = copy.deepcopy(summary)
    wrong_source["physical_authoring_identity"]["source_usd_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="runtime_source_identity_mismatch"):
        authority.validate_runtime_summary(
            wrong_source,
            trace_identity=identity,
            support_entry_path=Path(support_manifest["support_entry_root_usd_path"]),
            support_entry_sha256=support_manifest["support_entry_root_usd_sha256"],
            runner_script_sha256=_sha256(RUNNER_PATH),
        )


@requires_actual_authority_evidence
def test_authority_builder_is_atomic_hash_bound_and_does_not_mutate_runtime_tree(
    tmp_path,
):
    out_dir = tmp_path / "accepted_authority"
    runtime_before = authority.snapshot_regular_tree(RUNTIME_ROOT)

    bundle = authority.build_accepted_authority_bundle(
        support_manifest_path=SUPPORT_MANIFEST_PATH,
        runtime_summary_path=SUMMARY_PATH,
        trace_path=TRACE_PATH,
        runtime_scene_path=RUNTIME_SCENE_PATH,
        runner_path=RUNNER_PATH,
        out_dir=out_dir,
    )

    assert authority.snapshot_regular_tree(RUNTIME_ROOT) == runtime_before
    assert bundle["accepted"] is True
    assert len(bundle["accepted_authority_bundle_sha256"]) == 64
    assert bundle["runtime_evidence_tree_sha256"] == runtime_before["tree_sha256"]
    assert bundle["input_hashes"]["localized_source_usd_sha256"] == (
        "77607b6bdf3b6cba419e1bc17943bdb3e220b497a77e98d7665e98f779406211"
    )
    assert bundle["input_hashes"]["support_overlay_usd_sha256"] == (
        support_manifest := json.loads(SUPPORT_MANIFEST_PATH.read_text())
    )["support_overlay_usd_sha256"]
    assert bundle["input_hashes"]["support_entry_root_usd_sha256"] == (
        support_manifest["support_entry_root_usd_sha256"]
    )
    assert bundle["runtime_preflight"]["unique_runtime_particle_authority"] is True
    assert bundle["trace_identity"]["frame_indices"] == list(range(0, 601, 30))
    assert bundle["frozen_runner_baseline"]["verified"] is True
    assert bundle["frozen_runner_baseline"]["runner_script_sha256"] == (
        authority.EXPECTED_FROZEN_RUNNER_SHA256
    )
    assert bundle["runtime_evidence_snapshot_tree_sha256"] == runtime_before[
        "tree_sha256"
    ]
    assert bundle["publish_contract"]["kernel_advisory_lock"] is True
    assert bundle["publish_contract"]["lock_owner_verified_before_publish"] is True
    assert (out_dir / authority.BUNDLE_BASENAME).is_file()
    assert (out_dir / authority.FULL_LOG_BASENAME).is_file()
    assert (out_dir / authority.LOG_SEGMENT_BASENAME).is_file()
    assert (out_dir / authority.PARTICLE_GRAPH_BASENAME).is_file()
    assert (out_dir / authority.PUBLISH_COMPLETE_BASENAME).is_file()
    assert (out_dir / authority.RUNTIME_EVIDENCE_SNAPSHOT_DIR).is_dir()
    assert (out_dir / authority.FROZEN_BASELINE_DIR / authority.FROZEN_RUNNER_BASENAME).is_file()
    assert _sha256(
        out_dir / authority.FROZEN_BASELINE_DIR / authority.FROZEN_RUNNER_BASENAME
    ) == _sha256(RUNNER_PATH)
    assert json.loads((out_dir / authority.BUNDLE_BASENAME).read_text()) == bundle
    assert _sha256(out_dir / authority.FULL_LOG_BASENAME) == bundle[
        "kit_log_provenance"
    ]["source_log_full_sha256"]
    assert _sha256(out_dir / authority.LOG_SEGMENT_BASENAME) == bundle[
        "kit_log_provenance"
    ]["segment_sha256"]

    injected = out_dir / "unregistered.txt"
    injected.write_text("must fail closed")
    with pytest.raises(ValueError, match="authority_output_file_registry_mismatch"):
        authority._validate_final_bundle(out_dir)

    with pytest.raises(ValueError, match="output_directory_already_exists"):
        authority.build_accepted_authority_bundle(
            support_manifest_path=SUPPORT_MANIFEST_PATH,
            runtime_summary_path=SUMMARY_PATH,
            trace_path=TRACE_PATH,
            runtime_scene_path=RUNTIME_SCENE_PATH,
            runner_path=RUNNER_PATH,
            out_dir=out_dir,
        )


def test_authority_inputs_cannot_contain_bundle_self_reference():
    with pytest.raises(ValueError, match="authority_bundle_self_reference_forbidden"):
        authority.reject_authority_self_reference(
            {"summary": b'{"accepted_authority_bundle_sha256":"cycle"}'}
        )


def test_authority_builder_direct_cli_bootstraps_repo_imports(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(AUTHORITY_TOOL_PATH), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--support-manifest" in completed.stdout


def test_frozen_runner_is_anchored_to_preexisting_accepted_matrix(tmp_path):
    baseline = authority.validate_frozen_runner_baseline(RUNNER_PATH)

    assert baseline["verified"] is True
    assert baseline["runner_script_sha256"] == authority.EXPECTED_FROZEN_RUNNER_SHA256
    assert baseline["accepted_matrix_manifest_sha256"] == (
        authority.EXPECTED_ACCEPTED_MATRIX_MANIFEST_SHA256
    )
    assert baseline["accepted_runtime_summary_sha256"] == (
        authority.EXPECTED_ACCEPTED_RUNTIME_SUMMARY_SHA256
    )

    changed = tmp_path / RUNNER_PATH.name
    changed.write_bytes(RUNNER_PATH.read_bytes() + b"\n# drift\n")
    with pytest.raises(ValueError, match="frozen_runner_sha256_mismatch"):
        authority.validate_frozen_runner_baseline(changed)


def test_cpfs_publish_fallback_reserves_destination_and_commits_marker_last(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "complete.txt").write_text("complete")
    (source / authority.PUBLISH_COMPLETE_BASENAME).write_text("committed")
    destination = tmp_path / "destination"

    authority._atomic_rename_noreplace(
        source,
        destination,
        publish_mode="atomic_mkdir_commit_marker",
    )

    assert not source.exists()
    assert (destination / "complete.txt").read_text() == "complete"
    assert (destination / authority.PUBLISH_COMPLETE_BASENAME).read_text() == (
        "committed"
    )

    second_source = tmp_path / "second-source"
    second_source.mkdir()
    (second_source / authority.PUBLISH_COMPLETE_BASENAME).write_text("committed")
    with pytest.raises(ValueError, match="output_directory_already_exists"):
        authority._atomic_rename_noreplace(
            second_source,
            destination,
            publish_mode="atomic_mkdir_commit_marker",
        )
    assert second_source.is_dir()


def test_cpfs_reserved_publish_never_overwrites_injected_child(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "complete.txt").write_text("authority")
    (source / authority.PUBLISH_COMPLETE_BASENAME).write_text("committed")
    destination = tmp_path / "destination"
    destination.mkdir()
    injected = destination / "complete.txt"
    injected.write_text("external")

    with pytest.raises(ValueError, match="publish_destination_artifact_exists"):
        authority._publish_staging_into_reserved_directory(source, destination)

    assert injected.read_text() == "external"
    assert not (destination / authority.PUBLISH_COMPLETE_BASENAME).exists()

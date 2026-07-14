from __future__ import annotations

import hashlib
import json
import sys
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

import pytest

from tools.labutopia_fluid import run_real_beaker_static_hold_matrix as matrix


def _fake_isaacsim_spec(tmp_path: Path):
    package_root = tmp_path / "site-packages" / "isaacsim"
    usd_root = package_root / "extscache" / "omni.usd.libs"
    (usd_root / "pxr" / "Usd").mkdir(parents=True)
    (usd_root / "pxr" / "Usd" / "__init__.py").write_text("", encoding="utf-8")
    (usd_root / "pxr" / "Usd" / "_usd.so").write_bytes(b"usd-python-extension")
    (usd_root / "bin").mkdir()
    (usd_root / "bin" / "libtf.so").write_bytes(b"tf")
    (usd_root / "bin" / "libusd.so").write_bytes(b"usd")

    class Spec:
        submodule_search_locations = [str(package_root)]
        origin = str(package_root / "__init__.py")

    return Spec(), usd_root


def test_resolve_isaac_usd_runtime_uses_matching_isaacsim_extcache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    isaacsim_spec, usd_root = _fake_isaacsim_spec(tmp_path)

    def fake_find_spec(name: str):
        return None if name == "pxr" else isaacsim_spec if name == "isaacsim" else None

    monkeypatch.setattr(matrix.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(matrix.importlib.metadata, "version", lambda name: "4.1.0.0")
    contract = matrix.resolve_isaac_usd_runtime()

    assert contract["bootstrap_mode"] == "isaacsim_extcache"
    assert contract["python_path_entry"] == str(usd_root)
    assert contract["library_path_entry"] == str(usd_root / "bin")
    assert contract["pxr_package_path"] == str(usd_root / "pxr")
    assert contract["pxr_namespace_package"] is True
    assert contract["usd_python_sha256"] == matrix._sha256_file(
        usd_root / "pxr" / "Usd" / "__init__.py"
    )
    assert contract["libtf_sha256"] == matrix._sha256_file(usd_root / "bin" / "libtf.so")
    assert contract["usd_extension_sha256"] == matrix._sha256_file(
        usd_root / "pxr" / "Usd" / "_usd.so"
    )


def test_resolve_isaac_usd_runtime_ignores_importable_isaac45_pxr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    isaacsim_spec, usd_root = _fake_isaacsim_spec(tmp_path)

    class PxrSpec:
        origin = "/isaac-sim/kit/python/lib/python3.10/site-packages/pxr/__init__.py"

    monkeypatch.setattr(
        matrix.importlib.util,
        "find_spec",
        lambda name: PxrSpec() if name == "pxr" else isaacsim_spec,
    )
    monkeypatch.setattr(matrix.importlib.metadata, "version", lambda name: "4.1.0.0")

    contract = matrix.resolve_isaac_usd_runtime()

    assert contract["python_path_entry"] == str(usd_root)
    assert contract["bootstrap_mode"] == "isaacsim_extcache"


def test_resolve_isaac_usd_runtime_rejects_non_41_isaacsim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    isaacsim_spec, _usd_root = _fake_isaacsim_spec(tmp_path)
    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: isaacsim_spec)
    monkeypatch.setattr(matrix.importlib.metadata, "version", lambda name: "4.5.0.0")

    with pytest.raises(RuntimeError, match="Isaac Sim 4.1"):
        matrix.resolve_isaac_usd_runtime()


def test_build_isaac_child_env_prepends_matching_usd_paths():
    contract = {
        "bootstrap_mode": "isaacsim_extcache",
        "python_path_entry": "/matching/omni.usd.libs",
        "library_path_entry": "/matching/omni.usd.libs/bin",
    }

    env = matrix.build_isaac_child_env(
        {
            "PYTHONPATH": "/isaac-sim/kit/python/lib/python3.10/site-packages:/existing/python",
            "LD_LIBRARY_PATH": "/isaac-sim/kit:/existing/lib",
        },
        contract,
    )

    assert env["PYTHONPATH"] == "/matching/omni.usd.libs:/existing/python"
    assert env["LD_LIBRARY_PATH"] == "/matching/omni.usd.libs/bin:/existing/lib"
    assert env["PYTHONNOUSERSITE"] == "1"


def test_resolve_isaac_usd_runtime_fails_closed_when_matching_usd_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(
        matrix.importlib.metadata,
        "version",
        lambda name: (_ for _ in ()).throw(matrix.importlib.metadata.PackageNotFoundError(name)),
    )

    with pytest.raises(RuntimeError, match="Isaac Sim 4.1"):
        matrix.resolve_isaac_usd_runtime()


def test_pxr_preflight_reports_failure_before_matrix_cells(
    monkeypatch: pytest.MonkeyPatch,
):
    class Result:
        returncode = 1
        stdout = b""
        stderr = b"ModuleNotFoundError: No module named 'pxr'"

    monkeypatch.setattr(matrix.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="Isaac USD preflight failed"):
        matrix.preflight_isaac_usd_runtime(
            {"PYTHONPATH": "/bad"},
            {
                "expected_usd_version": "0.22.11",
                "python_path_entry": "/matching/omni.usd.libs",
                "usd_extension_sha256": "0" * 64,
            },
        )


def test_pxr_preflight_rejects_loaded_usd_26_from_isaac45(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    isaacsim_spec, usd_root = _fake_isaacsim_spec(tmp_path)
    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: isaacsim_spec)
    monkeypatch.setattr(matrix.importlib.metadata, "version", lambda name: "4.1.0.0")
    contract = matrix.resolve_isaac_usd_runtime()

    class Result:
        returncode = 0
        stderr = b""
        stdout = json.dumps(
            {
                "usd_version": "0.26.5",
                "pxr_origin": "/isaac-sim/kit/python/lib/python3.10/site-packages/pxr/__init__.py",
                "usd_origin": "/isaac-sim/kit/python/lib/python3.10/site-packages/pxr/Usd/__init__.py",
                "usd_extension_origin": "/isaac-sim/kit/python/lib/python3.10/site-packages/pxr/Usd/_usd.so",
            }
        ).encode("utf-8")

    monkeypatch.setattr(matrix.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="expected USD 0.22.11"):
        matrix.preflight_isaac_usd_runtime({}, contract)


def test_pxr_preflight_accepts_isaac41_namespace_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    isaacsim_spec, usd_root = _fake_isaacsim_spec(tmp_path)
    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: isaacsim_spec)
    monkeypatch.setattr(matrix.importlib.metadata, "version", lambda name: "4.1.0.0")
    contract = matrix.resolve_isaac_usd_runtime()

    class Result:
        returncode = 0
        stderr = b""
        stdout = json.dumps(
            {
                "usd_version": "0.22.11",
                "pxr_origin": None,
                "pxr_search_locations": [str(usd_root / "pxr")],
                "usd_origin": str(usd_root / "pxr" / "Usd" / "__init__.py"),
                "usd_extension_origin": str(usd_root / "pxr" / "Usd" / "_usd.so"),
            }
        ).encode("utf-8")

    monkeypatch.setattr(matrix.subprocess, "run", lambda *args, **kwargs: Result())

    validation = matrix.preflight_isaac_usd_runtime({}, contract)

    assert validation["usd_version"] == "0.22.11"
    assert validation["pxr_origin"] is None
    assert validation["pxr_search_locations"] == [str(usd_root / "pxr")]


def test_matrix_acceptance_requires_verified_physx_lifecycle(tmp_path: Path):
    base = {
        "particle_count": 1024,
        "seed": 0,
        "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
        "visible_beaker_containment_verified": True,
    }

    accepted = _accepted_matrix_cell(tmp_path)

    assert matrix.cell_is_accepted(base) is False
    assert matrix.cell_is_accepted(accepted) is True

    for key in (
        "simulate_fetch_pair_count",
        "ordered_lifecycle_verified",
        "lifecycle_event_count",
        "lifecycle_event_sha256",
    ):
        without_key = {
            **accepted,
            "strict_physics_execution": dict(accepted["strict_physics_execution"]),
        }
        without_key["strict_physics_execution"].pop(key)
        assert matrix.cell_is_accepted(without_key) is False


def test_matrix_acceptance_rejects_missing_or_invalid_si_authoring_contract(
    tmp_path: Path,
):
    accepted = _accepted_matrix_cell(tmp_path)

    missing = dict(accepted)
    missing.pop("stage_unit_contract")
    assert matrix.cell_is_accepted(missing) is False

    wrong_units = json.loads(json.dumps(accepted))
    wrong_units["stage_unit_contract"]["effective_meters_per_unit"] = 0.01
    assert matrix.cell_is_accepted(wrong_units) is False

    wrong_density = json.loads(json.dumps(accepted))
    wrong_density["stage_unit_contract"]["density_contract"][
        "particle_density_kg_m3"
    ] = 1.0
    assert matrix.cell_is_accepted(wrong_density) is False


def test_matrix_acceptance_rejects_unbound_physical_authoring_identity(tmp_path: Path):
    accepted = _accepted_matrix_cell(tmp_path)

    missing = dict(accepted)
    missing.pop("physical_authoring_identity")
    assert matrix.cell_is_accepted(missing) is False

    wrong_seed = json.loads(json.dumps(accepted))
    wrong_seed["physical_authoring_identity"]["seed"] = 2
    assert matrix.cell_is_accepted(wrong_seed) is False

    wrong_count = json.loads(json.dumps(accepted))
    wrong_count["physical_authoring_identity"]["particle_count"] = 4096
    assert matrix.cell_is_accepted(wrong_count) is False


def test_matrix_acceptance_rejects_zero_or_mismatched_nonparticle_rest_offset(
    tmp_path: Path,
):
    accepted = _accepted_matrix_cell(tmp_path)

    zero_rest = json.loads(json.dumps(accepted))
    zero_rest["authored_runtime_paths"]["particle_system_collision_offsets"][
        "rest_offset"
    ] = 0.0
    assert matrix.cell_is_accepted(zero_rest) is False

    mismatched_rest = json.loads(json.dumps(accepted))
    mismatched_rest["authored_runtime_paths"]["particle_system_collision_offsets"][
        "rest_offset"
    ] = 0.0005
    assert matrix.cell_is_accepted(mismatched_rest) is False


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    (
        ("summary_error", "summary_unreadable"),
        ("timed_out", True),
        ("launch_error", "OSError: launch failed"),
    ),
)
def test_matrix_acceptance_rejects_process_or_summary_failures(
    tmp_path: Path,
    field: str,
    tampered_value: object,
):
    record = _accepted_matrix_cell(tmp_path)
    record[field] = tampered_value

    assert matrix.cell_is_accepted(record) is False


@pytest.mark.parametrize(
    "path_field",
    ("summary_path", "trace_path", "evidence_scene_path"),
)
def test_matrix_acceptance_rejects_missing_required_evidence_files(
    tmp_path: Path,
    path_field: str,
):
    record = _accepted_matrix_cell(tmp_path)
    Path(record[path_field]).unlink()

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_rejects_missing_or_tampered_artifact_hashes(
    tmp_path: Path,
):
    record = _accepted_matrix_cell(tmp_path)

    missing = deepcopy(record)
    missing.pop("artifact_hashes")
    assert matrix.cell_is_accepted(missing) is False

    missing_required = deepcopy(record)
    missing_required["artifact_hashes"].pop("particle_readback_trace.jsonl")
    assert matrix.cell_is_accepted(missing_required) is False

    wrong_hash = deepcopy(record)
    wrong_hash["artifact_hashes"]["particle_readback_trace.jsonl"] = "0" * 64
    assert matrix.cell_is_accepted(wrong_hash) is False

    nonexistent_registered_file = deepcopy(record)
    nonexistent_registered_file["artifact_hashes"]["not-created.bin"] = "0" * 64
    assert matrix.cell_is_accepted(nonexistent_registered_file) is False


def test_matrix_acceptance_rejects_unsafe_artifact_paths(tmp_path: Path):
    record = _accepted_matrix_cell(tmp_path)
    record["artifact_hashes"]["../outside.bin"] = "0" * 64

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_rejects_unregistered_artifact(tmp_path: Path):
    record = _accepted_matrix_cell(tmp_path)
    (Path(record["summary_path"]).parent / "late-added.bin").write_bytes(b"late")

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_rejects_symlinked_required_evidence(tmp_path: Path):
    record = _accepted_matrix_cell(tmp_path)
    scene_path = Path(record["evidence_scene_path"])
    target = scene_path.with_name("scene-target.usda")
    scene_path.replace(target)
    scene_path.symlink_to(target.name)
    record["artifact_hashes"].pop(scene_path.name)
    record["artifact_hashes"][target.name] = _sha256_file(target)

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_rejects_raw_trace_schema_tamper_even_when_rehashed(
    tmp_path: Path,
):
    record = _accepted_matrix_cell(tmp_path)
    trace_path = Path(record["trace_path"])
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["step_index"] = 0
    lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _refresh_artifact_hash(record, trace_path)

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_rejects_empty_or_fake_trace_identity(
    tmp_path: Path,
):
    empty = _accepted_matrix_cell(tmp_path / "empty")
    empty["physical_trace_identity"] = None
    assert matrix.cell_is_accepted(empty) is False

    record = _accepted_matrix_cell(tmp_path / "fake")
    fake_identity = deepcopy(record["physical_trace_identity"])
    fake_identity["positions_sha256"] = "e" * 64
    fake_identity["physical_trace_sha256"] = "f" * 64
    record["physical_trace_identity"] = fake_identity
    summary = _read_fixture_summary(record)
    summary["physical_trace_identity"] = deepcopy(fake_identity)
    summary["classification"]["physical_trace_identity"] = deepcopy(fake_identity)
    summary["strict_visible_classification"]["physical_trace_identity"] = deepcopy(
        fake_identity
    )
    _write_fixture_summary(record, summary)

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_rejects_record_summary_trace_identity_mismatch(
    tmp_path: Path,
):
    record = _accepted_matrix_cell(tmp_path)
    summary = _read_fixture_summary(record)
    summary["physical_trace_identity"]["seed"] = 2
    _write_fixture_summary(record, summary)

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_recomputes_lifecycle_sha_from_command_cadence(
    tmp_path: Path,
):
    fake_sha_record = _accepted_matrix_cell(tmp_path / "sha")
    fake_sha_record["strict_physics_execution"]["lifecycle_event_sha256"] = "d" * 64
    _sync_execution_to_summary(fake_sha_record)
    assert matrix.cell_is_accepted(fake_sha_record) is False

    cadence_record = _accepted_matrix_cell(tmp_path / "cadence")
    stride_index = cadence_record["command"].index("--video-stride") + 1
    cadence_record["command"][stride_index] = "60"
    _write_fixture_command(cadence_record)
    assert matrix.cell_is_accepted(cadence_record) is False


@pytest.mark.parametrize("particle_count", (1024, 4096))
def test_matrix_acceptance_requires_exact_count_specific_offsets(
    tmp_path: Path,
    particle_count: int,
):
    record = _accepted_matrix_cell(tmp_path, particle_count=particle_count)
    assert matrix.cell_is_accepted(record) is True

    offsets = deepcopy(record["authored_runtime_paths"]["particle_system_collision_offsets"])
    offsets["contact_offset"] *= 2.0
    offsets["particle_contact_offset"] *= 2.0
    offsets["solid_rest_offset"] *= 2.0
    offsets["rest_offset"] = offsets["solid_rest_offset"]
    offsets["fluid_rest_offset"] *= 2.0
    _replace_offsets_and_resign(record, offsets)

    assert matrix.cell_is_accepted(record) is False


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    (
        ("gpu_dynamics_enabled", False),
        ("broadphase_type", "CPU"),
        ("solver_type", "PGS"),
        ("gravity_direction", [0.0, 0.0, 1.0]),
        ("gravity_magnitude", 0.0),
        ("gpu_max_particle_contacts", 1024),
        ("time_steps_per_second_authored", False),
    ),
)
def test_matrix_acceptance_requires_complete_gpu_tgs_physics_contract(
    tmp_path: Path,
    field: str,
    tampered_value: object,
):
    record = _accepted_matrix_cell(tmp_path)
    _replace_physics_and_resign(record, field, tampered_value)

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_binds_source_hash_to_actual_command_file(tmp_path: Path):
    record = _accepted_matrix_cell(tmp_path)
    source_index = record["command"].index("--usd") + 1
    Path(record["command"][source_index]).write_bytes(b"source was replaced")

    assert matrix.cell_is_accepted(record) is False


def test_matrix_acceptance_binds_runner_to_actual_child_script(tmp_path: Path):
    record = _accepted_matrix_cell(tmp_path)
    fake_runner = tmp_path / "fake_child.py"
    fake_runner.write_text("# replacement runner\n", encoding="utf-8")
    record["command"][1] = str(fake_runner)
    identity = record["physical_authoring_identity"]
    identity["runner_script_sha256"] = _sha256_file(fake_runner)
    _resign_authoring_identity(identity)
    _sync_authoring_to_summary(record)
    _write_fixture_command(record)

    assert matrix.cell_is_accepted(record) is False


def test_cell_record_collects_hashes_before_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    out_dir = tmp_path / "cell"
    out_dir.mkdir()
    summary_path = out_dir / "runtime_smoke_summary.json"
    summary_path.write_text("{}\n", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_accept(record: dict) -> bool:
        observed["artifact_hashes"] = record.get("artifact_hashes")
        return False

    monkeypatch.setattr(matrix, "cell_is_accepted", fake_accept)
    args = Namespace(
        steps=600,
        logical_dt=1.0 / 60.0,
        integration_dt=1.0 / 600.0,
        substeps_per_logical_step=10,
        display_particle_width=0.0043,
        trace_interval=30,
        video_stride=30,
        video_fps=15.0,
        width=320,
        height=180,
    )
    argv = [sys.executable, str(matrix.CHILD_SCRIPT), "--manifest", str(summary_path)]

    matrix._cell_record(
        {"cell_id": "P1024_S0", "particle_count": 1024, "seed": 0},
        argv=argv,
        out_dir=out_dir,
        result=matrix.ChildResult(returncode=0, timed_out=False),
        args=args,
    )

    assert observed["artifact_hashes"] == {
        "runtime_smoke_summary.json": _sha256_file(summary_path)
    }


def test_current_real_matrix_manifest_acceptance_tracks_runner_identity():
    manifest_path = (
        matrix.REPO_ROOT
        / "docs/labutopia_lab_poc/evidence_manifests/"
        "fluid_spike_real_beaker_static_hold_matrix_si600_restoffset_20260711.json"
    )
    if not manifest_path.is_file():
        pytest.skip("local real-beaker matrix evidence is not present")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(manifest["cells"]) == 6
    recorded_runner_hashes = {
        json.loads(Path(cell["summary_path"]).read_text(encoding="utf-8"))[
            "physical_authoring_identity"
        ]["runner_script_sha256"]
        for cell in manifest["cells"]
    }
    current_runner_hash = _sha256_file(matrix.CHILD_SCRIPT)
    if recorded_runner_hashes == {current_runner_hash}:
        assert all(matrix.cell_is_accepted(cell) for cell in manifest["cells"])
    else:
        assert all(
            not matrix.cell_is_accepted(cell) for cell in manifest["cells"]
        )


_LIFECYCLE_SHA_STAGE_123_STRIDE_30 = (
    "32fb6d8960907942e59e6a469e8b2e0823478c3ae1e0b7016d1f22d7a8ce1148"
)
_OFFSETS_BY_COUNT = {
    1024: {
        "contact_offset": 0.001058508,
        "rest_offset": 0.000594,
        "particle_contact_offset": 0.000705672,
        "solid_rest_offset": 0.000594,
        "fluid_rest_offset": 0.000352836,
    },
    4096: {
        "contact_offset": 0.000793881,
        "rest_offset": 0.0004455,
        "particle_contact_offset": 0.000529254,
        "solid_rest_offset": 0.0004455,
        "fluid_rest_offset": 0.000264627,
    },
}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _accepted_matrix_cell(
    tmp_path: Path,
    *,
    particle_count: int = 1024,
    seed: int = 0,
    outside_visible_beaker: bool = False,
    source_tag: str = "canonical-test-source",
) -> dict:
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    out_dir = tmp_path / f"P{particle_count}_S{seed}"
    out_dir.mkdir(parents=True)
    source_usd = tmp_path / "source.usd"
    stage = Usd.Stage.CreateNew(str(source_usd))
    stage.SetMetadata("customLayerData", {"fixtureTag": source_tag})
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 0.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )
    stage.GetRootLayer().Save()
    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path="/World/ParticleSet",
    )
    summary_path = out_dir / "runtime_smoke_summary.json"
    trace_path = out_dir / "particle_readback_trace.jsonl"
    scene_path = out_dir / "native_scene_completed_pbd_overlay.usda"
    command_path = out_dir / "command.json"
    stage.GetRootLayer().Export(str(scene_path))

    canonical_point = (
        (frame.interior_radius * 4.0, 0.0, frame.interior_floor + 0.01)
        if outside_visible_beaker
        else (0.0, 0.0, frame.interior_floor + 0.01)
    )
    positions = [list(frame.canonical_to_world(canonical_point))] * particle_count
    frame_indices = list(range(0, 601, 30))
    trace_records = [
        {
            "step_index": step,
            "particle_count": particle_count,
            "positions": positions,
        }
        for step in frame_indices
    ]
    trace_path.write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in trace_records
        ),
        encoding="utf-8",
    )
    source_sha256 = _sha256_file(source_usd)
    positions_sha256 = _canonical_sha256([record["positions"] for record in trace_records])
    trace_identity = {
        "frame_indices": frame_indices,
        "frame_particle_counts": [particle_count] * len(frame_indices),
        "frame_count": len(frame_indices),
        "source_usd_sha256": source_sha256,
        "particle_count": particle_count,
        "seed": seed,
        "steps": 600,
        "trace_interval": 30,
        "positions_sha256": positions_sha256,
    }
    trace_identity["physical_trace_sha256"] = _canonical_sha256(trace_identity)

    base = {
        "cell_id": f"P{particle_count}_S{seed}",
        "particle_count": particle_count,
        "seed": seed,
        "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
        "visible_beaker_containment_verified": True,
        "returncode": 0,
        "timed_out": False,
        "launch_error": None,
        "summary_error": None,
    }
    execution = {
        "exact_step_count_verified": True,
        "exact_logical_step_count_verified": True,
        "exact_integration_step_count_verified": True,
        "requested_logical_steps": 600,
        "executed_logical_steps": 600,
        "requested_integration_steps": 6000,
        "executed_integration_steps": 6000,
        "logical_dt": 1.0 / 60.0,
        "integration_dt": 1.0 / 600.0,
        "substeps_per_logical_step": 10,
        "logical_steps_per_second": 60,
        "integration_steps_per_second": 600,
        "simulated_seconds": 10.0,
        "simulate_fetch_pair_count": 6000,
        "ordered_lifecycle_verified": True,
        "lifecycle_event_count": 12624,
        "lifecycle_event_sha256": _LIFECYCLE_SHA_STAGE_123_STRIDE_30,
        "stage_id": 123,
        "attach_verified": True,
        "detach_verified": True,
        "render_updates_advance_physics": False,
        "render_invariance_checks": 22,
    }
    physics_settings = {
        "gpu_dynamics_enabled": True,
        "broadphase_type": "GPU",
        "solver_type": "TGS",
        "gravity_direction": [0.0, 0.0, -1.0],
        "gravity_magnitude": 9.81,
        "gpu_max_particle_contacts": 1048576,
        "strict_timestep_verified": True,
        "time_steps_per_second": 600,
        "time_steps_per_second_authored": True,
        "effective_physics_dt": 1.0 / 600.0,
    }
    density_contract = {
        "material_density_kg_m3": 1000.0,
        "particle_density_kg_m3": 1000.0,
        "particle_mass_kg": 0.0,
        "strict_si_density_verified": True,
    }
    stage_unit_contract = {
        "effective_meters_per_unit": 1.0,
        "effective_kilograms_per_unit": 1.0,
        "meters_per_unit_authored": True,
        "kilograms_per_unit_authored": True,
        "strict_si_units_verified": True,
        "numeric_geometry_invariant": True,
        "density_contract": density_contract,
    }
    collision_offsets = deepcopy(_OFFSETS_BY_COUNT[particle_count])
    wrapper = {"enabled": True, "contract": "test-wrapper"}
    spawn_positions_sha256 = _canonical_sha256(
        {"particle_count": particle_count, "seed": seed, "kind": "spawn"}
    )
    identity = {
        "schema_version": 1,
        "source_usd_sha256": source_sha256,
        "runner_script_sha256": _sha256_file(matrix.CHILD_SCRIPT),
        "spawn_positions_sha256": spawn_positions_sha256,
        "isaacsim_version": "4.1.0.0",
        "particle_count": particle_count,
        "seed": seed,
        "step_schedule": {
            "logical_dt": 1.0 / 60.0,
            "integration_dt": 1.0 / 600.0,
            "substeps_per_logical_step": 10,
            "logical_steps_per_second": 60,
            "integration_steps_per_second": 600,
        },
        "strict_si_contract": {
            "effective_meters_per_unit": 1.0,
            "effective_kilograms_per_unit": 1.0,
            "strict_si_units_verified": True,
            "numeric_geometry_invariant": True,
            "density_contract": density_contract,
        },
        "particle_system_collision_offsets": collision_offsets,
        "wrapper_contract_sha256": _canonical_sha256(wrapper),
        "physics_settings": physics_settings,
    }
    _resign_authoring_identity(identity)
    command = [
        sys.executable,
        str(matrix.CHILD_SCRIPT),
        "--usd",
        str(source_usd),
        "--real-beaker-static-hold",
        "--controlled-spawn-count",
        str(particle_count),
        "--controlled-spawn-seed",
        str(seed),
        "--steps",
        "600",
        "--logical-dt",
        repr(1.0 / 60.0),
        "--integration-dt",
        repr(1.0 / 600.0),
        "--substeps-per-logical-step",
        "10",
        "--trace-interval",
        "30",
        "--video-stride",
        "30",
        "--out-dir",
        str(out_dir),
        "--manifest",
        str(summary_path),
    ]
    summary = {
        "source_usd_path": str(source_usd),
        "selected_particle_count": particle_count,
        "steps": 600,
        "trace_path": str(trace_path),
        "evidence_scene_path": str(scene_path),
        "classification": {
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "trace_schema_valid": True,
            "physical_trace_identity": deepcopy(trace_identity),
        },
        "strict_visible_classification": {
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "trace_schema_valid": True,
            "physical_trace_identity": deepcopy(trace_identity),
        },
        "visible_beaker_containment_verified": True,
        "strict_physics_execution": deepcopy(execution),
        "physics_settings": deepcopy(physics_settings),
        "stage_unit_contract": deepcopy(stage_unit_contract),
        "authored_runtime_paths": {
            "particle_system_collision_offsets": deepcopy(collision_offsets),
        },
        "canonical_wrapper": wrapper,
        "visible_beaker_spawn": {
            "particle_count": particle_count,
            "particle_seed": seed,
            "positions_sha256": spawn_positions_sha256,
        },
        "controlled_spawn_plan": {
            "particle_count": particle_count,
            "particle_seed": seed,
        },
        "region_config": {
            "trace_interval": 30,
            "tail_window_steps": 90,
        },
        "physical_authoring_identity": deepcopy(identity),
        "physical_trace_identity": deepcopy(trace_identity),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    command_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "argv": command,
                "cell": {
                    "cell_id": base["cell_id"],
                    "particle_count": particle_count,
                    "seed": seed,
                },
                "step_schedule": {
                    "steps": 600,
                    "logical_dt": 1.0 / 60.0,
                    "integration_dt": 1.0 / 600.0,
                    "substeps_per_logical_step": 10,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    record = {
        **base,
        "command": command,
        "command_metadata_path": str(command_path),
        "summary_path": str(summary_path),
        "trace_path": str(trace_path),
        "evidence_scene_path": str(scene_path),
        "strict_physics_execution": execution,
        "physics_settings": physics_settings,
        "stage_unit_contract": stage_unit_contract,
        "authored_runtime_paths": {
            "particle_system_collision_offsets": collision_offsets,
        },
        "physical_authoring_identity": identity,
        "physical_trace_identity": trace_identity,
        "step_schedule": {
            "steps": 600,
            "logical_dt": 1.0 / 60.0,
            "integration_dt": 1.0 / 600.0,
            "substeps_per_logical_step": 10,
        },
    }
    record["artifact_hashes"] = {
        str(path.relative_to(out_dir)): _sha256_file(path)
        for path in (command_path, scene_path, trace_path, summary_path)
    }
    return record


def test_matrix_recomputes_visible_containment_from_raw_positions_and_source_geometry(
    tmp_path: Path,
):
    self_signed_outside = _accepted_matrix_cell(
        tmp_path,
        outside_visible_beaker=True,
    )

    assert self_signed_outside["classification"] == "PASS_VISIBLE_BEAKER_STATIC_HOLD"
    assert matrix.cell_is_accepted(self_signed_outside) is False


def test_matrix_closure_rejects_cells_from_different_source_identity(tmp_path: Path):
    cells = [
        _accepted_matrix_cell(
            tmp_path / f"P{particle_count}_S{seed}",
            particle_count=particle_count,
            seed=seed,
            source_tag=(
                "different-source"
                if (particle_count, seed) == (4096, 2)
                else "canonical-source"
            ),
        )
        for particle_count in (1024, 4096)
        for seed in (0, 1, 2)
    ]

    assert all(matrix.cell_is_accepted(cell) for cell in cells)
    assert matrix.real_beaker_static_hold_closed(cells) is False


def _refresh_artifact_hash(record: dict, path: Path) -> None:
    root = Path(record["summary_path"]).parent
    record["artifact_hashes"][str(path.relative_to(root))] = _sha256_file(path)


def _read_fixture_summary(record: dict) -> dict:
    return json.loads(Path(record["summary_path"]).read_text(encoding="utf-8"))


def _write_fixture_summary(record: dict, summary: dict) -> None:
    path = Path(record["summary_path"])
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_artifact_hash(record, path)


def _write_fixture_command(record: dict) -> None:
    path = Path(record["command_metadata_path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["argv"] = record["command"]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_artifact_hash(record, path)


def _resign_authoring_identity(identity: dict) -> None:
    body = deepcopy(identity)
    body.pop("physics_authoring_sha256", None)
    identity["physics_authoring_sha256"] = _canonical_sha256(body)


def _sync_execution_to_summary(record: dict) -> None:
    summary = _read_fixture_summary(record)
    summary["strict_physics_execution"] = deepcopy(record["strict_physics_execution"])
    _write_fixture_summary(record, summary)


def _sync_authoring_to_summary(record: dict) -> None:
    summary = _read_fixture_summary(record)
    summary["physical_authoring_identity"] = deepcopy(
        record["physical_authoring_identity"]
    )
    _write_fixture_summary(record, summary)


def _replace_offsets_and_resign(record: dict, offsets: dict) -> None:
    record["authored_runtime_paths"]["particle_system_collision_offsets"] = deepcopy(
        offsets
    )
    identity = record["physical_authoring_identity"]
    identity["particle_system_collision_offsets"] = deepcopy(offsets)
    _resign_authoring_identity(identity)
    summary = _read_fixture_summary(record)
    summary["authored_runtime_paths"]["particle_system_collision_offsets"] = deepcopy(
        offsets
    )
    summary["physical_authoring_identity"] = deepcopy(identity)
    _write_fixture_summary(record, summary)


def _replace_physics_and_resign(
    record: dict,
    field: str,
    tampered_value: object,
) -> None:
    record["physics_settings"][field] = tampered_value
    identity = record["physical_authoring_identity"]
    identity["physics_settings"][field] = deepcopy(tampered_value)
    _resign_authoring_identity(identity)
    summary = _read_fixture_summary(record)
    summary["physics_settings"] = deepcopy(record["physics_settings"])
    summary["physical_authoring_identity"] = deepcopy(identity)
    _write_fixture_summary(record, summary)

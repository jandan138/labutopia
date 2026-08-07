from __future__ import annotations

from pathlib import Path

from tools.labutopia_fluid import run_real_pbd_g0_full_robot_fk_capability as runner


def test_fk_capability_runner_keeps_a_fixed_cube_only_fixture(tmp_path):
    args = runner.parse_args(["--out-dir", str(tmp_path / "capability")])
    request = runner.build_capability_request()

    assert args.out_dir == (tmp_path / "capability").resolve()
    assert request["fixture"]["overlay_profile"]["id"] == runner.CUBE_ONLY_OVERLAY_PROFILE
    assert [item["id"] for item in request["fixture"]["overlay_profile"]["overlay_stack"]] == [
        "hidden_cube_collision_disable"
    ]
    assert request["classification"] == runner.CLASSIFICATION


def test_fk_capability_runner_has_no_g0_or_phase3_authority():
    source = Path(runner.__file__).read_text(encoding="utf-8")
    request = runner.build_capability_request()

    assert "G0_GO" not in source
    assert request["authorization"]["g0_go_authorized"] is False
    assert request["authorization"]["phase3_authorized"] is False


def test_child_publishes_its_report_before_kit_shutdown():
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert source.index(
        "attestation.write_canonical_json(args.child_report_path, report)"
    ) < source.index("app.close()")
    assert "app is not None and report[\"decision\"] != RUNTIME_BLOCKED" in source


def test_parent_preserves_a_blocked_child_before_gpu_log_validation():
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert source.index("child_report = attestation._read_canonical_json") < source.index(
        "if report[\"decision\"] != RUNTIME_BLOCKED"
    )


def test_child_gpu_identity_is_hash_bound_and_parent_revalidated(tmp_path):
    libcuda = tmp_path / "libcuda.so.1"
    torch = tmp_path / "torch.py"
    torch_native = tmp_path / "_C.so"
    for path in (libcuda, torch, torch_native):
        path.write_bytes(path.name.encode("ascii"))
    payload = {
        "authority": "sealed_child_gpu_identity_v1",
        "nvidia_visible_devices": "4",
        "cuda_visible_devices": None,
        "cuda_device_count": 1,
        "cuda_device_0_name": "test-gpu",
        "cuda_device_0_uuid": "a" * 32,
        "cuda_device_0_pci_bus_id": "00000000:00:00.0",
        "cuda_driver_api_version": 12040,
        "torch_cuda_version": "12.1",
        "libcuda": {"path": str(libcuda), "sha256": runner._sha256_file(libcuda)},
        "torch": {"path": str(torch), "sha256": runner._sha256_file(torch)},
        "torch_native": {
            "path": str(torch_native),
            "sha256": runner._sha256_file(torch_native),
        },
    }

    assert runner._validate_child_gpu_identity(payload, formal_prefix=tmp_path) == payload

    payload["cuda_driver_api_version"] = 0
    try:
        runner._validate_child_gpu_identity(payload, formal_prefix=tmp_path)
    except RuntimeError as exc:
        assert str(exc) == "g0_fk_capability_child_gpu_identity_invalid"
    else:
        raise AssertionError("invalid CUDA driver version unexpectedly accepted")

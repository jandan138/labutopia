from __future__ import annotations

import argparse

from tools.labutopia_fluid import attest_experimental_fluid_runtime as attestation
from tools.labutopia_fluid.run_isaac601_newton_render_bridge import (
    RTX_DRIVER_VERIFY_DISABLE_ARG,
    _apply_render_profile,
    _expected_effective_render_settings,
    _simulation_launch_config,
)
from tools.labutopia_fluid.run_wcsph_isaac41_rgb_matrix import (
    _renderer_for_profile,
)


def test_driver_preflight_remains_fail_closed_without_override(monkeypatch) -> None:
    monkeypatch.setattr(
        attestation,
        "_command_output",
        lambda _arguments: "570.153.02, NVIDIA GeForce RTX 4090, GPU-test\n",
    )
    record = attestation._isaac_driver_preflight()
    assert record["isaac601_rtx_supported"] is False
    assert record["rtx_launch_permitted"] is False
    assert record["driver_verification_setting"] is None


def test_driver_override_is_explicit_and_auditable(monkeypatch) -> None:
    monkeypatch.setattr(
        attestation,
        "_command_output",
        lambda _arguments: "570.153.02, NVIDIA GeForce RTX 4090, GPU-test\n",
    )
    record = attestation._isaac_driver_preflight(
        allow_unvalidated_driver=True
    )
    assert record["isaac601_rtx_supported"] is False
    assert record["rtx_launch_permitted"] is True
    assert record["unvalidated_driver_override_requested"] is True
    assert record["driver_verification_setting"] == RTX_DRIVER_VERIFY_DISABLE_ARG


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        render_profile=None,
        renderer="RayTracedLighting",
        capture_device="cpu",
        minimal_shading_mode=0,
        allow_unvalidated_driver=False,
        width=256,
        height=256,
    )


def test_strict_launch_does_not_disable_driver_verification() -> None:
    args = _args()
    args.render_profile = "strict"
    _apply_render_profile(args)
    config = _simulation_launch_config(args)
    assert config["renderer"] == "RealTimePathTracing"
    assert args.capture_device == "cpu"
    assert config["extra_args"] == [
        "--/rtx/rendermode=RealTimePathTracing"
    ]
    assert RTX_DRIVER_VERIFY_DISABLE_ARG not in config["extra_args"]


def test_minimal_cuda_profile_keeps_override_run_scoped() -> None:
    args = _args()
    args.render_profile = "minimal_textured"
    args.allow_unvalidated_driver = True
    _apply_render_profile(args)
    config = _simulation_launch_config(args)
    assert config["renderer"] == "MinimalRendering"
    assert config["minimal_shading_mode"] == 2
    assert args.capture_device == "cuda"
    assert config["extra_args"] == [
        "--/rtx/rendermode=MinimalRendering",
        "--/rtx/minimal/mode=2",
        RTX_DRIVER_VERIFY_DISABLE_ARG,
    ]
    assert _expected_effective_render_settings(args) == {
        "render_mode": "MinimalRendering",
        "minimal_shading_mode": 2,
    }


def test_strict_profile_uses_isaac601_native_rtx_realtime_two() -> None:
    args = _args()
    args.render_profile = "strict"
    _apply_render_profile(args)

    assert _expected_effective_render_settings(args) == {
        "render_mode": "RealTimePathTracing",
        "minimal_shading_mode": None,
    }
    assert _renderer_for_profile("isaac601", "strict") == args.renderer
    assert (
        _renderer_for_profile("isaac41", "strict")
        == "RayTracedLighting"
    )

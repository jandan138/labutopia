from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.labutopia_fluid.run_robot_table_geometry_probe import (
    _query_body_cooked_colliders,
    _stderr_diagnostic,
)


def test_stderr_diagnostic_clean_bytes():
    diagnostic = _stderr_diagnostic(b"")
    assert diagnostic["runtime_log_clean"] is True
    assert all(count == 0 for count in diagnostic["marker_line_counts"].values())
    assert diagnostic["stderr_byte_count"] == 0
    assert diagnostic["authority"] == "robot_table_geometry_stderr_diagnostic_v1"


def test_stderr_diagnostic_detects_error_and_abi_warning():
    stderr = (
        b"2026-07-21 [Error] [omni.example] something failed\n"
        b"Warning: Possible version incompatibility. Attempting to load omni::fabric::IPath with version v0.2 against v0.1.\n"
        b"Traceback (most recent call last):\n"
    )
    diagnostic = _stderr_diagnostic(stderr)
    assert diagnostic["runtime_log_clean"] is False
    assert diagnostic["marker_line_counts"]["kit_error"] == 1
    assert diagnostic["marker_line_counts"]["native_abi_warning"] == 1
    assert diagnostic["marker_line_counts"]["python_traceback"] == 1
    assert diagnostic["stderr_sha256"] is not None


def test_clean_stderr_preserves_sha256_roundtrip():
    stderr = b"benign log message\n"
    diagnostic = _stderr_diagnostic(stderr)
    assert diagnostic["runtime_log_clean"] is True
    assert diagnostic["stderr_sha256"] is not None
    assert diagnostic["stderr_byte_count"] == len(stderr)

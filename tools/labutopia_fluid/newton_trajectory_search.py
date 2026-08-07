#!/usr/bin/env python3
"""Deterministic, envelope-constrained pour-trajectory candidates."""

from __future__ import annotations

from typing import Any

import numpy as np

from tools.labutopia_fluid.fluid_benchmark_contract import (
    NEWTON_POUR_RETARGET_OFFSET_M,
    interpolate_pose_xyzw,
)
from tools.labutopia_fluid.newton_only_contract import validate_reoptimized_trajectory


_DIRECTIONS = np.asarray(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0],
        [1.0, -1.0, 0.0],
    ],
    dtype=np.float64,
)
_DIRECTIONS[-1] /= np.linalg.norm(_DIRECTIONS[-1])

QUALITY_TRAJECTORY_CANDIDATE_COUNT = 24
QUALITY_RETARGET_BLEND_IN = (100, 450)
QUALITY_RETARGET_HOLD_END = 780
QUALITY_RETARGET_RETURN_END = 952


def _smoothstep(value: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(value, dtype=np.float64), 0.0, 1.0)
    # Quintic minimum-jerk blend: zero velocity and acceleration at both ends.
    return clipped**3 * (clipped * (clipped * 6.0 - 15.0) + 10.0)


def _retarget_weights(
    observation_count: int,
    *,
    blend_in: tuple[int, int] = QUALITY_RETARGET_BLEND_IN,
    hold_end: int = QUALITY_RETARGET_HOLD_END,
    return_end: int = QUALITY_RETARGET_RETURN_END,
) -> np.ndarray:
    start, full = blend_in
    if not (0 < start < full <= hold_end < return_end < observation_count):
        raise ValueError("quality_retarget_interval_invalid")
    weights = np.zeros(observation_count, dtype=np.float64)
    weights[start : full + 1] = _smoothstep(
        np.linspace(0.0, 1.0, full - start + 1)
    )
    weights[full : hold_end + 1] = 1.0
    weights[hold_end : return_end + 1] = 1.0 - _smoothstep(
        np.linspace(0.0, 1.0, return_end - hold_end + 1)
    )
    return weights


def _orientation_time_warp(
    reference: np.ndarray,
    requested_shift_frames: float,
    *,
    start: int = 480,
    end: int = 870,
) -> np.ndarray:
    """Retimes only orientation, with a smooth zero shift at both boundaries."""
    if not (0 < start < end < len(reference) - 1):
        raise ValueError("orientation_warp_interval_invalid")
    candidate = reference.copy()
    phase = np.linspace(0.0, 1.0, end - start + 1)
    envelope = np.sin(np.pi * phase) ** 4
    for local_index, frame_index in enumerate(range(start, end + 1)):
        source_index = float(frame_index) - requested_shift_frames * envelope[local_index]
        lower = int(np.floor(np.clip(source_index, 0.0, len(reference) - 1.0)))
        upper = min(lower + 1, len(reference) - 1)
        alpha = source_index - lower
        candidate[frame_index, 3:] = interpolate_pose_xyzw(
            reference[lower], reference[upper], alpha
        )[3:]
    return candidate


def _candidate_spec(candidate_index: int) -> dict[str, object]:
    if candidate_index < 0 or candidate_index >= QUALITY_TRAJECTORY_CANDIDATE_COUNT:
        raise ValueError("trajectory_candidate_index_invalid")
    if candidate_index == 0:
        return {
            "retarget_scale": 0.0,
            "lateral_delta_m": [0.0, 0.0, 0.0],
            "orientation_shift_frames": 0.0,
        }
    if candidate_index < len(_DIRECTIONS):
        return {
            "local_direction": _DIRECTIONS[candidate_index].tolist(),
            "local_maximum_offset_m": 0.02,
            "orientation_shift_frames": 0.0,
        }
    scales = (0.75, 1.0, 1.25)
    lateral_x = (-0.02, 0.0, 0.02)
    shifts = (-30.0, 0.0, 30.0)
    code = candidate_index - len(_DIRECTIONS)
    return {
        "retarget_scale": scales[code % len(scales)],
        "lateral_delta_m": [lateral_x[(code // 3) % len(lateral_x)], 0.0, 0.0],
        "orientation_shift_frames": shifts[(code // 9) % len(shifts)],
    }


def _bump(observation_count: int, start: int, end: int) -> np.ndarray:
    if not (0 < start < end < observation_count - 1):
        raise ValueError("trajectory_bump_interval_invalid")
    result = np.zeros(observation_count, dtype=np.float64)
    phase = np.linspace(0.0, 1.0, end - start + 1)
    result[start : end + 1] = np.sin(np.pi * phase) ** 4
    return result


def generate_trajectory_candidate(
    reference_poses_xyzw: Any,
    candidate_index: int,
    *,
    maximum_offset_m: float = 0.02,
    bump_start: int = 420,
    bump_end: int = 850,
) -> tuple[np.ndarray, dict[str, Any]]:
    reference = np.asarray(reference_poses_xyzw, dtype=np.float64)
    if reference.ndim != 2 or reference.shape[1] != 7:
        raise ValueError("trajectory_shape_invalid")
    spec = _candidate_spec(candidate_index)
    if candidate_index == 0:
        candidate = reference.copy()
        accepted_scale = 1.0
    elif "local_direction" in spec:
        requested_offset = (
            np.asarray(spec["local_direction"], dtype=np.float64)
            * float(spec["local_maximum_offset_m"])
        )
        # Use the same minimum-jerk, pour-hold, endpoint-return envelope as the
        # larger retarget candidates.  A short bump is needlessly acceleration
        # limited and collapses useful centimetre-scale offsets to sub-millimetres.
        weights = _retarget_weights(len(reference))
        low = 0.0
        high = 1.0
        candidate = reference.copy()
        accepted_scale = 0.0
        for _ in range(32):
            scale = 0.5 * (low + high)
            trial = reference.copy()
            trial[:, :3] += weights[:, None] * requested_offset[None, :] * scale
            try:
                validate_reoptimized_trajectory(trial, reference)
            except ValueError:
                high = scale
            else:
                low = scale
                candidate = trial
                accepted_scale = scale
    else:
        base_offset = np.asarray(NEWTON_POUR_RETARGET_OFFSET_M, dtype=np.float64)
        requested_offset = (
            base_offset * float(spec["retarget_scale"])
            + np.asarray(spec["lateral_delta_m"], dtype=np.float64)
        )
        weights = _retarget_weights(len(reference))
        requested_shift = float(spec["orientation_shift_frames"])
        low = 0.0
        high = 1.0
        candidate = reference.copy()
        accepted_scale = 0.0
        for _ in range(32):
            scale = 0.5 * (low + high)
            trial = (
                reference.copy()
                if requested_shift == 0.0
                else _orientation_time_warp(reference, requested_shift * scale)
            )
            trial[:, :3] += weights[:, None] * requested_offset[None, :] * scale
            try:
                validate_reoptimized_trajectory(trial, reference)
            except ValueError:
                high = scale
            else:
                low = scale
                candidate = trial
                accepted_scale = scale
    validation = validate_reoptimized_trajectory(candidate, reference)
    applied_offset = (
        np.zeros(3, dtype=np.float64)
        if candidate_index == 0
        else (
            np.asarray(spec["local_direction"], dtype=np.float64)
            * float(spec["local_maximum_offset_m"])
        )
        * accepted_scale
        if "local_direction" in spec
        else (
            np.asarray(NEWTON_POUR_RETARGET_OFFSET_M, dtype=np.float64)
            * float(spec["retarget_scale"])
            + np.asarray(spec["lateral_delta_m"], dtype=np.float64)
        )
        * accepted_scale
    )
    return candidate, {
        "candidate_index": candidate_index,
        "kind": (
            "reference"
            if candidate_index == 0
            else "wcsph_local_offset_v1"
            if "local_direction" in spec
            else "wcsph_quality_retarget_v2"
        ),
        "spec": spec,
        "accepted_scale": accepted_scale,
        "accepted_offset_m": applied_offset.tolist(),
        "accepted_orientation_shift_frames": float(
            spec.get("orientation_shift_frames", 0.0)
        )
        * accepted_scale,
        "fixed_global_endpoints": True,
        "motion_envelope_validation": validation,
        "reachability_validation": "out_of_scope_for_kinematic_fluid_case",
        "penetration_validation": "required_before_formal_candidate_promotion",
    }

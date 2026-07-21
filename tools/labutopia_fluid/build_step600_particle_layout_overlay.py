#!/usr/bin/env python3
"""Build the pinned step-600 particle-position layout diagnostic overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DONOR_DIR = (
    REPO_ROOT
    / "outputs/contact_grasp_passive_stability_20260716/"
    "rest_offset_zero_600hz_filled_attempt_001"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
BASE_ASSET_NAME = (
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_v1.usda"
)
SELECTED_LOCAL_STEP = 600
EXPECTED_PARTICLE_COUNT = 3600
EXPECTED_REPORT_SHA256 = (
    "41957cce41e8cdd97490f61750d8990ebd946f8efc8e36124ad7e2329a347890"
)
EXPECTED_AUDIT_SHA256 = (
    "10285c5dba88bcc1f2f0df085ac1172eb9d5e444353bfc70ec4657fc5683714b"
)
EXPECTED_SOURCE_TRACE_SHA256 = (
    "027b0911fa4565d8a23ce64f30dd8ce587a095c2b9ed52c68e810d3a5e73ead4"
)
EXPECTED_PARTICLE_TRACE_SHA256 = (
    "1b100786c13d1da1d03dcf4910522a10433a590329bf5abaa05f674179071248"
)
EXPECTED_STEP0_SOURCE_POSE_SHA256 = (
    "09b236ecef091d4c5886682b3b8e5695e6705458c1cecc6ff00fd14e8b390a1f"
)
EXPECTED_STEP600_SOURCE_POSE_SHA256 = (
    "6e2d22597c57578a3c561b26582c52519216aa303430a36fdf4aed655bf55134"
)
EXPECTED_STEP600_POSITION_SHA256 = (
    "b56ab6028f611cb9ac87acc1b8058ed33eec46174ffaaf7bfab8bae349f94357"
)
EXPECTED_REBASED_FLOAT64_SHA256 = (
    "7f9f38b5a5f57117c04d9c02d18a44ffa54a808ca20bf3acbb47db5e95f9157d"
)
EXPECTED_POINT3F_SHA256 = (
    "eddddcb010e3078cf5d0ed60e369c7bd51470e94edb84cdc097b2b9ba60ff6ef"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_position_sha256(positions: Any) -> str:
    values = np.ascontiguousarray(np.asarray(positions, dtype="<f8"))
    if values.ndim != 2 or values.shape[1:] != (3,) or not np.isfinite(values).all():
        raise ValueError("step600_particle_positions_invalid")
    digest = hashlib.sha256()
    digest.update(values.dtype.str.encode("ascii"))
    digest.update(b"\0")
    digest.update(json.dumps(list(values.shape), separators=(",", ":")).encode("ascii"))
    digest.update(b"\0")
    digest.update(values.tobytes(order="C"))
    return digest.hexdigest()


def _rigid_row_matrix(value: Any, *, name: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if (
        matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or not np.allclose(
            matrix[:, 3], [0.0, 0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-10
        )
        or not np.allclose(
            matrix[:3, :3] @ matrix[:3, :3].T,
            np.eye(3),
            rtol=0.0,
            atol=1.0e-6,
        )
        or not math.isclose(
            float(np.linalg.det(matrix[:3, :3])),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-6,
        )
    ):
        raise ValueError(f"step600_particle_{name}_invalid")
    return matrix


def rebase_particle_positions(
    positions_world: Any,
    *,
    source_world_at_selected_step: Any,
    target_source_world: Any,
    particle_authored_world: Any,
    expected_particle_count: int,
) -> np.ndarray:
    if type(expected_particle_count) is not int or expected_particle_count <= 0:
        raise ValueError("step600_particle_expected_count_invalid")
    positions = np.asarray(positions_world, dtype=np.float64)
    if (
        positions.shape != (expected_particle_count, 3)
        or not np.isfinite(positions).all()
    ):
        raise ValueError("step600_particle_positions_invalid")
    selected_source = _rigid_row_matrix(
        source_world_at_selected_step,
        name="selected_source_world",
    )
    target_source = _rigid_row_matrix(
        target_source_world,
        name="target_source_world",
    )
    particle_world = _rigid_row_matrix(
        particle_authored_world,
        name="authored_particle_world",
    )
    homogeneous = np.column_stack(
        [positions, np.ones(expected_particle_count, dtype=np.float64)]
    )
    result = (
        homogeneous
        @ np.linalg.inv(selected_source)
        @ target_source
        @ np.linalg.inv(particle_world)
    )[:, :3]
    if not np.isfinite(result).all():
        raise ValueError("step600_particle_rebased_positions_invalid")
    return np.ascontiguousarray(result, dtype=np.float64)


def _format_float32(value: np.float32) -> str:
    return np.format_float_positional(value, unique=True, trim="-")


def _format_point_array(name: str, positions: np.ndarray) -> list[str]:
    lines = [f"            point3f[] {name} = ["]
    for x, y, z in positions:
        lines.append(
            "                "
            f"({_format_float32(x)}, {_format_float32(y)}, {_format_float32(z)}),"
        )
    lines.append("            ]")
    return lines


def render_overlay(positions_point3f: Any) -> str:
    positions = np.asarray(positions_point3f)
    if (
        positions.dtype != np.dtype("float32")
        or positions.shape != (EXPECTED_PARTICLE_COUNT, 3)
        or not np.isfinite(positions).all()
    ):
        raise ValueError("step600_particle_point3f_positions_invalid")
    metadata = {
        "donor_report_sha256": EXPECTED_REPORT_SHA256,
        "donor_audit_sha256": EXPECTED_AUDIT_SHA256,
        "donor_source_trace_sha256": EXPECTED_SOURCE_TRACE_SHA256,
        "donor_particle_trace_sha256": EXPECTED_PARTICLE_TRACE_SHA256,
        "selected_source_pose_sha256": EXPECTED_STEP600_SOURCE_POSE_SHA256,
        "selected_position_sha256": EXPECTED_STEP600_POSITION_SHA256,
        "rebased_point3f_sha256": EXPECTED_POINT3F_SHA256,
    }
    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "World"',
        "    customLayerData = {",
    ]
    for key, value in metadata.items():
        lines.append(f'        string {key} = "{value}"')
    lines.extend(
        [
            f"        int selected_local_step = {SELECTED_LOCAL_STEP}",
            "    }",
            "    subLayers = [",
            f"        @{BASE_ASSET_NAME}@",
            "    ]",
            ")",
            "",
            'over "World"',
            "{",
            '    over "InternDataParityFluid"',
            "    {",
            '        over "Particles"',
            "        {",
        ]
    )
    lines.extend(_format_point_array("physxParticle:simulationPoints", positions))
    lines.extend(_format_point_array("points", positions))
    lines.extend(["        }", "    }", "}", ""])
    return "\n".join(lines)


def build_overlay(*, donor_dir: Path, output_path: Path) -> dict[str, Any]:
    report_path = donor_dir / "report.json"
    audit_path = donor_dir / "descriptive_hold_audit.json"
    source_path = donor_dir / "source_trace.npz"
    particle_path = donor_dir / "particle_trace.npz"
    expected_files = (
        (report_path, EXPECTED_REPORT_SHA256),
        (audit_path, EXPECTED_AUDIT_SHA256),
        (source_path, EXPECTED_SOURCE_TRACE_SHA256),
        (particle_path, EXPECTED_PARTICLE_TRACE_SHA256),
    )
    for path, expected_hash in expected_files:
        if not path.is_file() or _sha256_file(path) != expected_hash:
            raise ValueError(f"step600_particle_donor_hash_invalid:{path.name}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (
        report.get("lifecycle_status") != "completed"
        or report.get("treatment") != "filled"
        or audit.get("classification") != "HOLD_ONLY_PASS"
    ):
        raise ValueError("step600_particle_donor_authority_invalid")

    with np.load(source_path, allow_pickle=False) as source, np.load(
        particle_path, allow_pickle=False
    ) as particles:
        if (
            source["source_world_matrix_m"].shape != (2401, 4, 4)
            or particles["positions_world_m"].shape != (2401, 3600, 3)
            or int(source["local_step"][SELECTED_LOCAL_STEP])
            != SELECTED_LOCAL_STEP
            or int(source["world_step"][SELECTED_LOCAL_STEP]) != 621
            or not math.isclose(
                float(source["world_time_s"][SELECTED_LOCAL_STEP]),
                1.0350000250618905,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            or str(source["source_pose_sha256"][0])
            != EXPECTED_STEP0_SOURCE_POSE_SHA256
            or str(source["source_pose_sha256"][SELECTED_LOCAL_STEP])
            != EXPECTED_STEP600_SOURCE_POSE_SHA256
            or str(
                particles["source_frame_pose_sha256"][SELECTED_LOCAL_STEP]
            )
            != EXPECTED_STEP600_SOURCE_POSE_SHA256
            or str(particles["position_sha256"][SELECTED_LOCAL_STEP])
            != EXPECTED_STEP600_POSITION_SHA256
        ):
            raise ValueError("step600_particle_selected_record_invalid")
        selected_positions = np.asarray(
            particles["positions_world_m"][SELECTED_LOCAL_STEP],
            dtype=np.float64,
        )
        if canonical_position_sha256(selected_positions) != (
            EXPECTED_STEP600_POSITION_SHA256
        ):
            raise ValueError("step600_particle_selected_position_hash_invalid")
        rebased = rebase_particle_positions(
            selected_positions,
            source_world_at_selected_step=source["source_world_matrix_m"][
                SELECTED_LOCAL_STEP
            ],
            target_source_world=source["source_world_matrix_m"][0],
            particle_authored_world=np.eye(4, dtype=np.float64),
            expected_particle_count=EXPECTED_PARTICLE_COUNT,
        )
    rebased_hash = canonical_position_sha256(rebased)
    if rebased_hash != EXPECTED_REBASED_FLOAT64_SHA256:
        raise ValueError("step600_particle_rebased_hash_invalid")
    point3f = np.ascontiguousarray(rebased, dtype=np.float32)
    point3f_hash = canonical_position_sha256(point3f)
    if point3f_hash != EXPECTED_POINT3F_SHA256:
        raise ValueError("step600_particle_point3f_hash_invalid")
    if len(np.unique(point3f, axis=0)) != EXPECTED_PARTICLE_COUNT:
        raise ValueError("step600_particle_point3f_uniqueness_invalid")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(render_overlay(point3f))
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "output_path": str(output_path),
        "output_sha256": _sha256_file(output_path),
        "particle_count": EXPECTED_PARTICLE_COUNT,
        "selected_local_step": SELECTED_LOCAL_STEP,
        "rebased_float64_sha256": rebased_hash,
        "rebased_point3f_sha256": point3f_hash,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-dir", type=Path, default=DEFAULT_DONOR_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    args.donor_dir = args.donor_dir.resolve()
    args.out = args.out.resolve()
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_overlay(donor_dir=args.donor_dir, output_path=args.out)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

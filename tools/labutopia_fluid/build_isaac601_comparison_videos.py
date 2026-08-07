#!/usr/bin/env python3
"""Build aligned strict-vs-minimal Isaac 6 comparison videos."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STRICT_ROOT = (
    REPO_ROOT
    / "outputs/wcsph_quality_repair/"
    "2026-08-04_isaac601_same_process_strict_media_r1"
)
DEFAULT_MINIMAL_ROOT = (
    REPO_ROOT
    / "outputs/wcsph_quality_repair/"
    "2026-08-04_isaac601_same_process_minimal_media_r1"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "reports/2026-08-03-labutopia-isaac6-wcsph-integration-study/"
    "media/isaac6_strict_vs_minimal"
)
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FRAME_COUNT = 953


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sequence_dir(root: Path, representation: str, camera: str) -> Path:
    return (
        root
        / "runs/256"
        / representation
        / "repeat_00/isaac_artifacts/rgb_sequences"
        / camera
    )


def _validate_sequence(path: Path) -> dict[str, Any]:
    frames = sorted(path.glob("frame_*.png"))
    expected_names = [f"frame_{index:04d}.png" for index in range(FRAME_COUNT)]
    actual_names = [frame.name for frame in frames]
    if actual_names != expected_names:
        raise RuntimeError(f"rgb_sequence_not_contiguous:{path}:{len(frames)}")
    return {
        "directory": str(path),
        "frame_count": len(frames),
        "first_frame_sha256": _sha256(frames[0]),
        "last_frame_sha256": _sha256(frames[-1]),
    }


def _probe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(completed.stdout)["format"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-root", type=Path, default=DEFAULT_STRICT_ROOT)
    parser.add_argument("--minimal-root", type=Path, default=DEFAULT_MINIMAL_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    strict_root = args.strict_root.resolve(strict=True)
    minimal_root = args.minimal_root.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output_dir_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not FONT.is_file():
        raise FileNotFoundError(FONT)

    specs = (
        ("particles", "camera_1", "particles_overview.mp4"),
        ("particles", "camera_2", "particles_closeup.mp4"),
        ("surface_gpu", "camera_1", "surface_overview.mp4"),
        ("surface_gpu", "camera_2", "surface_closeup.mp4"),
    )
    records: list[dict[str, Any]] = []
    for representation, camera, filename in specs:
        strict_dir = _sequence_dir(strict_root, representation, camera)
        minimal_dir = _sequence_dir(minimal_root, representation, camera)
        strict_record = _validate_sequence(strict_dir)
        minimal_record = _validate_sequence(minimal_dir)
        output_path = output_dir / filename
        filter_graph = (
            f"[0:v]drawtext=fontfile={FONT}:"
            "text='STRICT  RTX Real-Time 2.0':fontcolor=white:fontsize=13:"
            "box=1:boxcolor=black@0.65:boxborderw=4:x=6:y=6[left];"
            f"[1:v]drawtext=fontfile={FONT}:"
            "text='FAST  Minimal mode 2':fontcolor=white:fontsize=13:"
            "box=1:boxcolor=black@0.65:boxborderw=4:x=6:y=6[right];"
            "[left][right]hstack=inputs=2[out]"
        )
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "30",
            "-i",
            str(strict_dir / "frame_%04d.png"),
            "-framerate",
            "30",
            "-i",
            str(minimal_dir / "frame_%04d.png"),
            "-filter_complex",
            filter_graph,
            "-map",
            "[out]",
            "-frames:v",
            str(FRAME_COUNT),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(output_path),
        ]
        subprocess.run(command, check=True)
        records.append(
            {
                "representation": representation,
                "camera": camera,
                "strict_sequence": strict_record,
                "minimal_sequence": minimal_record,
                "output": {
                    "path": str(output_path),
                    "sha256": _sha256(output_path),
                    "probe": _probe(output_path),
                },
            }
        )

    manifest = {
        "schema": "labutopia.isaac601_strict_minimal_comparison_media.v1",
        "status": "passed",
        "performance_evidence_eligible": False,
        "alignment": {
            "frame_count": FRAME_COUNT,
            "fps": 30,
            "policy": "same_observation_index_no_frame_dropping_no_time_stretch",
        },
        "left": "Isaac 6 RTX Real-Time 2.0 strict profile",
        "right": "Isaac 6 MinimalRendering shading mode 2",
        "videos": records,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "passed", "manifest": str(manifest_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

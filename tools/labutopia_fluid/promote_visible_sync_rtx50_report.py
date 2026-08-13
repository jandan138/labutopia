#!/usr/bin/env python3
"""Fail-closed promotion of synchronized liquid0812 videos into the report."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "reports/2026-08-12-labutopia-rtx50-field-notes"
LANES = ("headless-product", "offscreen-viewport")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _video_probe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "/usr/bin/ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate,nb_frames,duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)["streams"][0]


def _eligible(result: dict[str, Any], audit: dict[str, Any], lane: str) -> None:
    if result.get("schema") != "labutopia.isaac41.liquid0812_async_rtx_result.v3":
        raise RuntimeError(f"promotion_result_schema:{lane}")
    if result.get("lane") != lane or audit.get("lane") != lane:
        raise RuntimeError(f"promotion_lane_mismatch:{lane}")
    if result["runtime"].get("evidence_class") != "formal_comparable":
        raise RuntimeError(f"promotion_result_not_formal:{lane}")
    if audit["runtime"].get("evidence_class") != "formal_comparable":
        raise RuntimeError(f"promotion_audit_not_formal:{lane}")
    if result["configuration"]["camera"]["policy"] != "trajectory-envelope":
        raise RuntimeError(f"promotion_camera_policy:{lane}")
    if result["configuration"]["source_driver"] != "physx-kinematic-target":
        raise RuntimeError(f"promotion_source_driver:{lane}")
    if not result["acceptance"]["physics"]["source_pose_tracking"]:
        raise RuntimeError(f"promotion_pose_sync_failed:{lane}")
    if audit.get("status") != "passed" or not audit["pose_sync"]["passed"]:
        raise RuntimeError(f"promotion_audit_pose_failed:{lane}")
    if not audit["pixel_sync"]["passed"]:
        raise RuntimeError(f"promotion_audit_pixel_failed:{lane}")
    full = result["artifacts"].get("full_video")
    if not full or not all(full["checks"].values()):
        raise RuntimeError(f"promotion_full_video_failed:{lane}")


def main() -> int:
    parser = argparse.ArgumentParser()
    for lane in LANES:
        key = lane.replace("-", "_")
        parser.add_argument(f"--{key}-result", type=Path, required=True)
        parser.add_argument(f"--{key}-audit", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    report_dir = args.report_dir.resolve()
    records = []
    for lane in LANES:
        key = lane.replace("-", "_")
        result_path = getattr(args, f"{key}_result").resolve()
        audit_path = getattr(args, f"{key}_audit").resolve()
        result = _read(result_path)
        audit = _read(audit_path)
        _eligible(result, audit, lane)
        source_video = Path(result["artifacts"]["full_video"]["video"]["path"])
        if not source_video.is_file():
            raise FileNotFoundError(source_video)
        probe = _video_probe(source_video)
        if [probe["width"], probe["height"]] != [256, 256]:
            raise RuntimeError(f"promotion_video_resolution:{lane}")
        if probe["avg_frame_rate"] != "50/1" or int(probe["nb_frames"]) != 1589:
            raise RuntimeError(f"promotion_video_contract:{lane}")
        records.append(
            {
                "lane": lane,
                "result_path": result_path,
                "audit_path": audit_path,
                "result": result,
                "audit": audit,
                "source_video": source_video,
                "source_video_sha256": _sha256(source_video),
                "destination": report_dir
                / "media"
                / f"visible-sync-{key}-full-50fps-v1.mp4",
            }
        )

    plan = {
        "status": "eligible",
        "atomic_unit": "single_git_commit_after_both_lanes_and_report_tests_pass",
        "old_media_policy": "remove_all_old_video_embeds_keep_files_as_internal_evidence",
        "records": [
            {
                "lane": item["lane"],
                "source_video": str(item["source_video"]),
                "source_video_sha256": item["source_video_sha256"],
                "destination": str(item["destination"]),
                "rtx_fps": item["result"]["timing"][
                    "average_rtx_completed_gpu_consumed_fps"
                ],
                "performance_passed": item["result"]["acceptance"][
                    "performance_passed"
                ],
                "physics_passed": item["result"]["acceptance"]["physics_passed"],
                "pose_sync_passed": item["audit"]["pose_sync"]["passed"],
                "pixel_sync_passed": item["audit"]["pixel_sync"]["passed"],
            }
            for item in records
        ],
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.apply:
        return 0
    # Copying is intentionally the only mutation performed here. HTML/JSON are
    # updated from the printed, reviewed values in the same promotion commit.
    for item in records:
        item["destination"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item["source_video"], item["destination"])
        if _sha256(item["destination"]) != item["source_video_sha256"]:
            raise RuntimeError(f"promotion_copy_hash_mismatch:{item['lane']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

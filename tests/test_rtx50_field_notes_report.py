from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports" / "2026-08-12-labutopia-rtx50-field-notes"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.media: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag in {"video", "source", "img"} and values.get("src"):
            self.media.append(str(values["src"]))
        if tag == "video" and values.get("poster"):
            self.media.append(str(values["poster"]))


def test_report_claims_and_failure_boundary() -> None:
    html = (REPORT_DIR / "index.html").read_text(encoding="utf-8")
    parser = _Parser()
    parser.feed(html)
    assert {"cover", "videos", "problem", "contract", "battle", "qualification", "kinematic", "boundary", "eval", "interview"}.issubset(parser.ids)
    assert parser.media
    assert all((REPORT_DIR / media).is_file() for media in parser.media)
    for text in ("1589", "31.78", "47.24 FPS", "47.17 FPS", "59.26", "38.22", "没有一条候选通过", "仅供复现问题"):
        assert text in html
    for text in ("0.000123 mm", "28.33", "22.96", "17.15", "为什么现在有新视频，但仍然写 NO-GO"):
        assert text in html
    for text in ("展开历史 teleport 视频", "共享 GPU 忙载", "数值姿态同步已经修好", "原始 CUDA 帧与 H.264 解码帧同时失败"):
        assert text in html


def test_report_summary_and_media_contract() -> None:
    summary = json.loads((REPORT_DIR / "benchmark-summary.json").read_text(encoding="utf-8"))
    review = json.loads((REPORT_DIR / "video-visual-review.json").read_text(encoding="utf-8"))
    browser_qa = json.loads((REPORT_DIR / "browser-qa.json").read_text(encoding="utf-8"))
    assert summary["status"] == "visible_source_numeric_sync_pass_video_flicker_no_go_no_replacement_promoted"
    assert summary["contract"]["rtx_frames"] == 1589
    current = summary["current_kinematic_diagnostic"]
    assert current["status"] == "measured_no_go"
    assert current["source_driver"] == "physx-kinematic-target"
    assert current["camera_policy"] == "trajectory-envelope"
    assert current["evidence_class"] == "non_authoritative_busy_gpu_exploration"
    assert current["visible_source_sync"]["numeric_pose_sync"] == "pass"
    assert current["visible_source_sync"]["rgb_full_video_review"] == "fail_flicker"
    assert summary["flicker_ab_screen"]["status"] == "all_candidates_failed_no_promotion"
    assert all(candidate["status"] == "failed" for candidate in summary["flicker_ab_screen"]["candidates"])
    assert current["qualification_matrix"]["headless_product"]["runs_meeting_50_rtx_fps"] == 0
    assert current["qualification_matrix"]["offscreen_viewport"]["runs_meeting_50_rtx_fps"] == 0
    assert [run["integration_hz"] for run in summary["busy_gpu_integration_screen"]["runs"]] == [30, 60, 120]
    assert summary["historical_teleport_reference"]["use_for_current_claims"] is False
    assert review["verdicts"] == {
        "visible_source_motion": "pass",
        "diagnostic_video": "fail_flicker",
        "successful_pour_video": "fail",
    }
    assert review["independence"] == "not_independent"
    assert browser_qa["status"] in {"local_passed_pending_published_qa", "passed"}
    assert browser_qa["checks"]["current_video_count"] == 0
    assert browser_qa["checks"]["total_video_count_including_collapsed_history"] == 4
    assert browser_qa["checks"]["historical_section_collapsed_by_default"] in {None, True}
    for video in current["full_videos"]:
        path = REPORT_DIR / video["file"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == video["sha256"]
        assert video["performance_passed"] is False
        assert video["physics_passed"] is False
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate,nb_frames,duration", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        stream = json.loads(completed.stdout)["streams"][0]
        assert [stream["width"], stream["height"]] == [256, 256]
        assert stream["avg_frame_rate"] == "50/1"
        assert int(stream["nb_frames"]) == 1589
        assert float(stream["duration"]) == 31.78

from __future__ import annotations

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
    for text in ("1589", "31.78", "52.22 FPS", "51.85 FPS", "3 / 3", "独立 clean-room 复核为高置信度 FAIL", "不能证明一次可识别的倒液成功"):
        assert text in html
    for text in ("0.000123 mm", "164.60", "88.35", "45.46", "为什么没有再产一条新视频"):
        assert text in html


def test_report_summary_and_media_contract() -> None:
    summary = json.loads((REPORT_DIR / "benchmark-summary.json").read_text(encoding="utf-8"))
    review = json.loads((REPORT_DIR / "video-visual-review.json").read_text(encoding="utf-8"))
    assert summary["status"] == "performance_pass_quality_fail"
    assert summary["contract"]["rtx_frames"] == 1589
    assert summary["kinematic_followup"]["status"] == "driver_pass_quality_no_go"
    assert summary["kinematic_followup"]["selected_integration_hz"] is None
    assert summary["kinematic_followup"]["rtx_rerun_skipped_by_stop_rule"] is True
    assert [run["integration_hz"] for run in summary["kinematic_followup"]["runs"]] == [30, 60, 120]
    assert review["status"] == "failed"
    for video in summary["full_videos"]:
        path = REPORT_DIR / video["file"]
        assert path.is_file()
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

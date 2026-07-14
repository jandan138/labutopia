from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports" / "2026-07-07-labutopia-fluid-weekly"
REPORT_HTML = REPORT_DIR / "index.html"


class _ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.media_sources: list[str] = []
        self.video_attributes: list[dict[str, str | None]] = []
        self.links: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(str(attributes["id"]))
        if tag in {"img", "source", "video"} and attributes.get("src"):
            self.media_sources.append(str(attributes["src"]))
        if tag == "video":
            self.video_attributes.append(attributes)
            if attributes.get("poster"):
                self.media_sources.append(str(attributes["poster"]))
        if tag == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))


def _parse_report() -> tuple[str, _ReportParser]:
    html = REPORT_HTML.read_text(encoding="utf-8")
    parser = _ReportParser()
    parser.feed(html)
    return html, parser


def test_weekly_report_uses_the_new_pm_information_architecture() -> None:
    html, parser = _parse_report()

    assert "真实烧杯倒液" in html
    assert {
        "result",
        "why-it-worked",
        "three-approaches",
        "original-attempt",
        "rectangular-reference",
        "final-approach",
        "delivery",
        "next-step",
    }.issubset(parser.ids)
    assert "不是同条件性能排行" in html
    assert "静置起点" in html
    assert "视觉参考" in html
    assert "最终方案" in html


def test_weekly_report_states_verified_result_and_delivery_boundaries() -> None:
    html, parser = _parse_report()
    normalized = html.replace(",", "")

    for fact in (
        "3600 / 3600",
        "3 mm",
        "690 步",
        "691 个状态",
        "结束帧",
        "Isaac Sim 4.1",
        "初始状态快照",
        "结果状态快照",
        "外部轨迹",
        "连续液面",
    ):
        assert fact in normalized

    assert "源杯、传输区、桌面、桌下和异常粒子均为 0" in html
    assert "不代表任意容器、任意液量或任意动作" in html
    assert "2a0a21f2c836df97c925729084e13d68950b4deb" in html
    assert any(
        href.startswith("https://github.com/InternRobotics/InternDataEngine/")
        for href in parser.links
    )


def test_weekly_report_publishes_final_derived_surface_outcome() -> None:
    html, _ = _parse_report()

    for fact in (
        "离线连续液面",
        "70 帧",
        "零物理步",
        "高置信度 WARN",
        "surface_replay_final.usda",
        "outputs/interndata_surface_replay_20260714/final_render",
        "outputs/interndata_surface_replay_20260714/mesh_cache",
        "tools/labutopia_fluid/run_interndata_surface_replay.py",
        "e4d62bc2b33ef73ae601a0b322cded3dd32685c4dc97e76944fa95d802453a16",
    ):
        assert fact in html

    for stale_copy in (
        "当前证据视频直接显示 3 mm 粒子点",
        "在运行时接入稳定的 isosurface",
        "尚未达到参考视频的连续液面质感",
    ):
        assert stale_copy not in html


def test_weekly_report_removes_stale_experiment_report() -> None:
    html, _ = _parse_report()

    for stale_copy in (
        "静置持液 G1 + ClearWater G2",
        "G1/G2",
        "OmniGlass 视觉诊断矩阵",
        "S3 慢倒",
        "慢倒未开",
        "50k",
        "已撤回领导力主片",
    ):
        assert stale_copy not in html


def test_weekly_report_is_self_contained_and_media_complete() -> None:
    html, parser = _parse_report()
    expected_media = {
        "assets/pm-restructure/original-static-hold.mp4",
        "assets/pm-restructure/original-static-hold-poster.png",
        "assets/pm-restructure/rectangular-tank-reference.png",
        "assets/pm-restructure/final-context.mp4",
        "assets/pm-restructure/final-context-poster.png",
        "assets/pm-restructure/final-closeup.mp4",
        "assets/pm-restructure/final-closeup-poster.png",
        "assets/pm-restructure/final-keyframes.png",
        "assets/pm-restructure/final-validation.png",
    }

    assert expected_media.issubset(set(parser.media_sources))
    assert parser.video_attributes
    for attributes in parser.video_attributes:
        assert "controls" in attributes
        assert "playsinline" in attributes
        assert attributes.get("preload") == "metadata"
        assert attributes.get("poster", "").startswith("assets/pm-restructure/")

    for source in parser.media_sources:
        assert not source.startswith(("/", "http://", "https://"))
        media_path = REPORT_DIR / source
        assert media_path.is_file(), source
        assert media_path.stat().st_size > 0, source

    assert "@import" not in html
    assert not re.search(r"(?:src|poster)=[\"']/cpfs/", html)


def test_weekly_report_pages_media_are_not_managed_by_lfs() -> None:
    _, parser = _parse_report()
    media_paths = sorted(
        {
            str((REPORT_DIR / source).relative_to(REPO_ROOT))
            for source in parser.media_sources
        }
    )

    result = subprocess.run(
        ["git", "check-attr", "filter", "--", *media_paths],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    lfs_paths = [
        line.split(": filter: ", maxsplit=1)[0]
        for line in result.stdout.splitlines()
        if line.endswith(": filter: lfs")
    ]
    assert not lfs_paths, f"GitHub Pages media must be regular Git blobs: {lfs_paths}"

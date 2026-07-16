from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports" / "2026-07-07-labutopia-fluid-weekly"
REPORT_HTML = REPORT_DIR / "index.html"
FINAL_MANIFEST = (
    REPORT_DIR
    / "assets"
    / "pm-restructure"
    / "final-online-v4-manifest.json"
)
PRESENTATION_VIDEO_NAMES = (
    "final-online-v4-camera-1-720p.mp4",
    "final-online-v4-camera-2-720p.mp4",
)


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
        "3583 / 3600",
        "99.53%",
        "3 mm",
        "953 帧",
        "31.8 秒",
        "最后 100 帧",
        "结束帧",
        "Isaac Sim 4.1",
        "初始状态快照",
        "在线连续液面",
        "H5 倒液策略片段",
        "505 帧",
    ):
        assert fact in normalized

    assert "源杯 0、目标杯 3583、传输区 10、桌面 7、桌下 0、异常 0" in normalized
    assert "不代表任意容器、任意液量或任意动作" in html
    assert "2a0a21f2c836df97c925729084e13d68950b4deb" in html
    assert any(
        href.startswith("https://github.com/InternRobotics/InternDataEngine/")
        for href in parser.links
    )


def test_weekly_report_publishes_final_online_surface_outcome() -> None:
    html, _ = _parse_report()

    for fact in (
        "物理 → 表面重建 → RTX 渲染 → 模型相机",
        "level1_pour_rgb_v4_full_action_30hz",
        "3.03 FPS",
        "5.10 FPS",
        "30 FPS 是逻辑播放速度",
        "视觉审核为高置信度 PASS",
        "outputs/online_fluid_eval_20260715/v16_v4_full_action_isaacsim41",
        "outputs/collect/2026.07.15/20.15.27_Level1_pour_online_fluid_v2",
        "高清同步复跑",
        "1280 × 720",
        "原始模型输入证据",
        "每台模型相机仍是 256 × 256",
    ):
        assert fact in html

    for stale_copy in (
        "结束帧 3,600 / 3,600 个粒子在目标杯",
        "70 帧画面来自同一条 690 步",
        "展示回放为零物理步",
        "完整 70 帧动态",
    ):
        assert stale_copy not in html


def test_weekly_report_claims_are_bound_to_a_committed_evidence_manifest() -> None:
    html, _ = _parse_report()
    manifest = json.loads(FINAL_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["simulator"] == {"name": "Isaac Sim", "version": "4.1"}
    assert manifest["episode"]["observation_count"] == 953
    assert manifest["episode"]["stable_tail_observations"] == 100
    assert manifest["episode"]["stable_tail_definition"] == (
        "identical_partition_count_vector"
    )
    assert manifest["particles"]["total"] == 3600
    assert manifest["particles"]["target"] == 3583
    assert manifest["particles"]["tabletop_spill"] == 7
    assert manifest["dataset"]["h5_frame_count"] == 505
    assert manifest["dataset"]["observation_index_range"] == [447, 951]
    assert manifest["camera_contract"]["id"] == (
        "level1_pour_rgb_v4_full_action_30hz"
    )
    assert re.fullmatch(
        r"[0-9a-f]{64}", manifest["camera_contract"]["sha256"]
    )
    assert manifest["camera_contract"]["sha256"] in html
    assert manifest["performance"]["episode_wall_fps"] == pytest.approx(
        2.9605, abs=0.0001
    )
    assert manifest["visual_review"]["result"] == "PASS"
    assert manifest["visual_review"]["reviewed_frame_count"] == 10
    presentation = manifest["presentation_run"]
    assert presentation["episode"]["observation_count"] == 954
    assert presentation["episode"]["observation_index_range"] == [0, 953]
    assert presentation["episode"]["accepted"] is True
    assert presentation["particles"] == {
        "total": 3600,
        "source": 0,
        "target": 3568,
        "transit": 31,
        "tabletop_spill": 1,
        "below_table": 0,
        "nonfinite": 0,
    }
    assert presentation["capture_policy"] == (
        "viewport_same_observation_no_physics_step_v1"
    )
    assert presentation["physics_unchanged_frame_count"] == 954
    assert presentation["contact_grasp_claimed"] is False
    assert [video["name"] for video in presentation["videos"]] == [
        "camera_1",
        "camera_2",
    ]
    for video in presentation["videos"]:
        assert video["resolution"] == [1280, 720]
        assert video["fps"] == 30.0
        assert video["frame_count"] == 954
        assert re.fullmatch(r"[0-9a-f]{64}", video["sha256"])


def test_final_online_v4_release_files_are_git_tracked() -> None:
    release_files = [
        FINAL_MANIFEST,
        FINAL_MANIFEST.with_name("final-online-v4.mp4"),
        FINAL_MANIFEST.with_name("final-online-v4-poster.png"),
        FINAL_MANIFEST.with_name("final-online-v4-keyframes.png"),
        *(
            FINAL_MANIFEST.with_name(name)
            for name in PRESENTATION_VIDEO_NAMES
        ),
        *(
            FINAL_MANIFEST.with_name(name.replace(".mp4", "-poster.png"))
            for name in PRESENTATION_VIDEO_NAMES
        ),
    ]
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--error-unmatch",
            "--",
            *(str(path.relative_to(REPO_ROOT)) for path in release_files),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_rectangular_reference_discloses_native_surface_reconstruction() -> None:
    html, _ = _parse_report()

    for fact in (
        "PhysX 原生等值面",
        "OmniGlass",
        "4 次网格平滑",
        "4 次法线平滑",
        "不是裸 Points",
        "不是当前烧杯使用的外部表面重建管线",
    ):
        assert fact in html


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
        "assets/pm-restructure/final-online-v4.mp4",
        "assets/pm-restructure/final-online-v4-poster.png",
        "assets/pm-restructure/final-online-v4-keyframes.png",
        "assets/pm-restructure/final-online-v4-camera-1-720p.mp4",
        "assets/pm-restructure/final-online-v4-camera-1-720p-poster.png",
        "assets/pm-restructure/final-online-v4-camera-2-720p.mp4",
        "assets/pm-restructure/final-online-v4-camera-2-720p-poster.png",
    }

    assert expected_media.issubset(set(parser.media_sources))
    assert (
        "assets/pm-restructure/final-online-v4-manifest.json" in parser.links
    )
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


def test_presentation_videos_are_browser_ready_720p_h264() -> None:
    for name in PRESENTATION_VIDEO_NAMES:
        path = FINAL_MANIFEST.with_name(name)
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames",
                "-of",
                "json",
                str(path),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        stream = json.loads(result.stdout)["streams"][0]

        assert stream == {
            "codec_name": "h264",
            "width": 1280,
            "height": 720,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "30/1",
            "nb_frames": "954",
        }


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

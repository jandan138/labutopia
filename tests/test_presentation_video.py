from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from utils.presentation_video import (
    PresentationVideoRecorder,
    ViewportPresentationFrameProvider,
    define_presentation_camera_prims,
    resolve_presentation_camera_specs,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _model_camera_configs():
    return [
        SimpleNamespace(
            name="camera_1",
            prim_path="/World/InternDataParityCamera",
        ),
        SimpleNamespace(
            name="camera_2",
            prim_path="/World/InternDataParityCloseupCamera",
        ),
    ]


def _presentation_config():
    return SimpleNamespace(
        camera_names=["camera_1", "camera_2"],
        resolution=[1280, 720],
        fps=30,
        framing="preserve_vertical_fov",
    )


def _record(*, attempt_id="attempt-0000", observation_index=0):
    return {
        "attempt_id": attempt_id,
        "episode_id": "episode-0000",
        "observation_index": observation_index,
        "frame_identity": f"frame-{observation_index}",
        "integration_step_after": 4 * (observation_index + 1),
        "logical_step_after": observation_index + 1,
        "render": {
            "render_token": f"render-{observation_index}",
            "physics_and_timeline_unchanged": True,
        },
    }


def test_resolve_presentation_camera_specs_reuses_model_camera_prims():
    specs = resolve_presentation_camera_specs(
        _model_camera_configs(),
        _presentation_config(),
    )

    assert [(spec.name, spec.prim_path) for spec in specs] == [
        ("camera_1", "/World/LabUtopiaPresentationCameras/camera_1"),
        ("camera_2", "/World/LabUtopiaPresentationCameras/camera_2"),
    ]
    assert [spec.source_prim_path for spec in specs] == [
        "/World/InternDataParityCamera",
        "/World/InternDataParityCloseupCamera",
    ]
    assert all(spec.resolution == (1280, 720) for spec in specs)
    assert all(spec.fps == pytest.approx(30.0) for spec in specs)


def test_v2_config_pins_the_presentation_video_contract():
    import yaml

    config = yaml.safe_load(
        (
            REPO_ROOT / "config" / "level1_pour_online_fluid_v2.yaml"
        ).read_text(encoding="utf-8")
    )

    assert config["online_fluid"]["presentation_video"] == {
        "camera_names": ["camera_1", "camera_2"],
        "resolution": [1280, 720],
        "fps": 30,
        "framing": "preserve_vertical_fov",
    }


def test_resolve_presentation_camera_specs_rejects_unknown_camera():
    cfg = _presentation_config()
    cfg.camera_names = ["camera_1", "missing"]

    with pytest.raises(ValueError, match="presentation_camera_unknown:missing"):
        resolve_presentation_camera_specs(_model_camera_configs(), cfg)


def test_define_presentation_camera_prims_preserves_pose_and_expands_fov():
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    source = UsdGeom.Camera.Define(stage, "/World/InternDataParityCamera")
    source.CreateFocalLengthAttr(16.0)
    source.CreateHorizontalApertureAttr(24.0)
    source.CreateVerticalApertureAttr(16.0)
    source.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    UsdGeom.Xformable(source).AddTranslateOp().Set((1.0, 2.0, 3.0))
    specs = resolve_presentation_camera_specs(
        [
            SimpleNamespace(
                name="camera_1", prim_path=source.GetPath().pathString
            ),
            SimpleNamespace(
                name="camera_2", prim_path=source.GetPath().pathString
            ),
        ],
        _presentation_config(),
    )

    define_presentation_camera_prims(stage, specs)

    presentation = UsdGeom.Camera(
        stage.GetPrimAtPath(
            "/World/LabUtopiaPresentationCameras/camera_1"
        )
    )
    assert presentation.GetFocalLengthAttr().Get() == pytest.approx(16.0)
    assert presentation.GetVerticalApertureAttr().Get() == pytest.approx(16.0)
    assert presentation.GetHorizontalApertureAttr().Get() == pytest.approx(
        16.0 * 1280.0 / 720.0
    )
    source_matrix = UsdGeom.Xformable(source).ComputeLocalToWorldTransform(
        Usd.TimeCode.Default()
    )
    presentation_matrix = UsdGeom.Xformable(
        presentation
    ).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    assert np.asarray(source_matrix) == pytest.approx(
        np.asarray(presentation_matrix)
    )


class _FakeViewport:
    def __init__(self):
        self.camera_path = "/World/OriginalCamera"
        self.resolution = (640, 480)
        self.resolution_scale = 0.5
        self.pending_capture = None


class _FakeWorld:
    def __init__(self, viewport):
        self.current_time = 2.0
        self.current_time_step_index = 240
        self.render_count = 0
        self.viewport = viewport

    def render(self):
        self.render_count += 1
        if self.viewport.pending_capture is None:
            return
        callback = self.viewport.pending_capture
        self.viewport.pending_capture = None
        width, height = self.viewport.resolution
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[..., 0] = self.render_count
        callback(rgba, rgba.nbytes, width, height, "RGBA8")


class _FakeTimeline:
    def __init__(self):
        self.current_time = 2.0
        self.playing = True
        self.auto_updating = True

    def get_current_time(self):
        return self.current_time

    def is_playing(self):
        return self.playing

    def pause(self):
        self.playing = False

    def play(self):
        self.playing = True

    def is_auto_updating(self):
        return self.auto_updating

    def set_auto_update(self, value):
        self.auto_updating = bool(value)

    def commit_silently(self):
        return None


def test_viewport_provider_captures_two_720p_frames_without_advancing_physics():
    specs = resolve_presentation_camera_specs(
        _model_camera_configs(),
        _presentation_config(),
    )
    viewport = _FakeViewport()
    world = _FakeWorld(viewport)

    def schedule_capture(viewport_api, callback):
        viewport_api.pending_capture = callback
        return object()

    provider = ViewportPresentationFrameProvider(
        viewport=viewport,
        world=world,
        schedule_capture=schedule_capture,
        decode_buffer=lambda buffer, *_args: np.asarray(buffer)[..., :3].copy(),
    )

    frames, synchronization = provider(specs)

    assert world.render_count == 6
    assert synchronization["physics_and_timeline_unchanged"] is True
    assert synchronization["time_before"] == synchronization["time_after"]
    assert synchronization["step_before"] == synchronization["step_after"]
    assert synchronization["render_count"] == 6
    assert all(
        payload["rgb"].shape == (720, 1280, 3)
        for payload in frames.values()
    )
    assert viewport.camera_path == "/World/OriginalCamera"
    assert viewport.resolution == (640, 480)
    assert viewport.resolution_scale == pytest.approx(0.5)


def test_viewport_provider_records_unchanged_timeline_receipt():
    specs = resolve_presentation_camera_specs(
        _model_camera_configs(),
        _presentation_config(),
    )
    viewport = _FakeViewport()
    world = _FakeWorld(viewport)
    timeline = _FakeTimeline()

    def schedule_capture(viewport_api, callback):
        viewport_api.pending_capture = callback
        return object()

    provider = ViewportPresentationFrameProvider(
        viewport=viewport,
        world=world,
        timeline=timeline,
        schedule_capture=schedule_capture,
        decode_buffer=lambda buffer, *_args: np.asarray(buffer)[..., :3].copy(),
    )

    _, synchronization = provider(specs)

    assert synchronization["timeline_time_before"] == pytest.approx(2.0)
    assert synchronization["timeline_time_after"] == pytest.approx(2.0)
    assert synchronization["timeline_playing_before"] is True
    assert synchronization["timeline_playing_after"] is True
    assert synchronization["world_physics_unchanged"] is True
    assert synchronization["omni_timeline_unchanged"] is True
    assert synchronization["timeline_auto_update_before"] is True
    assert synchronization["timeline_auto_update_after"] is True
    assert synchronization["timeline_auto_update_disabled_for_capture"] is True


class _FakeCamera:
    def __init__(self, spec):
        self.spec = spec
        self.initialized = False
        self.frame_number = 100

    def initialize(self):
        self.initialized = True

    def get_rgb(self):
        width, height = self.spec.resolution
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[0, 0] = [11, 22, 33]
        return frame

    def get_current_frame(self):
        return {
            "rendering_frame": self.frame_number,
            "rendering_time": 1.25,
        }


class _FakeWriter:
    def __init__(self, path: Path, fps: float, resolution: tuple[int, int]):
        self.path = path
        self.fps = fps
        self.resolution = resolution
        self.frames = []
        self.released = False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def write(self, frame):
        self.frames.append(np.asarray(frame).copy())

    def release(self):
        self.released = True


def test_presentation_recorder_writes_two_independent_720p_attempt_videos(
    tmp_path,
):
    specs = resolve_presentation_camera_specs(
        _model_camera_configs(),
        _presentation_config(),
    )
    cameras = []
    writers = []

    def camera_factory(spec):
        camera = _FakeCamera(spec)
        cameras.append(camera)
        return camera

    def writer_factory(path, fps, resolution):
        writer = _FakeWriter(path, fps, resolution)
        writers.append(writer)
        return writer

    recorder = PresentationVideoRecorder(
        specs=specs,
        output_dir=tmp_path,
        camera_factory=camera_factory,
        writer_factory=writer_factory,
    )
    recorder.initialize()
    recorder.capture(_record(observation_index=0))
    recorder.capture(_record(observation_index=1))
    recorder.close_attempt(status="accepted")

    assert all(camera.initialized for camera in cameras)
    assert len(writers) == 2
    assert all(writer.resolution == (1280, 720) for writer in writers)
    assert all(writer.fps == pytest.approx(30.0) for writer in writers)
    assert all(len(writer.frames) == 2 for writer in writers)
    assert all(writer.released is True for writer in writers)
    assert all(writer.frames[0][0, 0].tolist() == [33, 22, 11] for writer in writers)
    assert {writer.path.name for writer in writers} == {
        "attempt-0000_episode-0000_camera_1_720p.mp4",
        "attempt-0000_episode-0000_camera_2_720p.mp4",
    }

    manifest = json.loads(
        (tmp_path / "presentation_video_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["schema_version"] == 1
    assert manifest["attempts"][0]["status"] == "accepted"
    assert manifest["attempts"][0]["frame_count"] == 2
    assert [item["name"] for item in manifest["attempts"][0]["videos"]] == [
        "camera_1",
        "camera_2",
    ]

    frame_records = [
        json.loads(line)
        for line in (
            tmp_path / "presentation_video_frames.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert [item["observation_index"] for item in frame_records] == [0, 1]
    assert frame_records[-1]["frame_identity"] == "frame-1"
    assert frame_records[-1]["physics_and_timeline_unchanged"] is True


def test_presentation_recorder_releases_failed_attempt_before_next_attempt(
    tmp_path,
):
    specs = resolve_presentation_camera_specs(
        _model_camera_configs(),
        _presentation_config(),
    )
    writers = []

    def writer_factory(path, fps, resolution):
        writer = _FakeWriter(path, fps, resolution)
        writers.append(writer)
        return writer

    recorder = PresentationVideoRecorder(
        specs=specs,
        output_dir=tmp_path,
        camera_factory=_FakeCamera,
        writer_factory=writer_factory,
    )
    recorder.initialize()
    recorder.capture(_record(attempt_id="attempt-0000"))
    recorder.close_attempt(status="rejected")
    recorder.capture(_record(attempt_id="attempt-0001"))
    recorder.close_attempt(status="accepted")

    assert len(writers) == 4
    assert all(writer.released for writer in writers)
    manifest = json.loads(
        (tmp_path / "presentation_video_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert [attempt["attempt_id"] for attempt in manifest["attempts"]] == [
        "attempt-0000",
        "attempt-0001",
    ]
    assert [attempt["status"] for attempt in manifest["attempts"]] == [
        "rejected",
        "accepted",
    ]

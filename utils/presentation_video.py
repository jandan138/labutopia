from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, Callable

import numpy as np


def _config_value(config: Any, name: str) -> Any:
    if isinstance(config, Mapping):
        return config[name]
    return getattr(config, name)


@dataclass(frozen=True)
class PresentationCameraSpec:
    name: str
    source_prim_path: str
    prim_path: str
    resolution: tuple[int, int]
    fps: float


def resolve_presentation_camera_specs(
    model_camera_configs: Sequence[Any],
    presentation_config: Any,
) -> tuple[PresentationCameraSpec, ...]:
    camera_names = tuple(
        str(name)
        for name in _config_value(presentation_config, "camera_names")
    )
    if len(camera_names) != 2 or len(set(camera_names)) != 2:
        raise ValueError("presentation_camera_names_two_unique_required")

    resolution_values = tuple(
        _config_value(presentation_config, "resolution")
    )
    if (
        len(resolution_values) != 2
        or any(type(value) is not int or value <= 0 for value in resolution_values)
    ):
        raise ValueError("presentation_resolution_invalid")
    resolution = (resolution_values[0], resolution_values[1])

    fps_value = _config_value(presentation_config, "fps")
    if (
        isinstance(fps_value, bool)
        or not isinstance(fps_value, (int, float))
        or not np.isfinite(float(fps_value))
        or float(fps_value) <= 0.0
    ):
        raise ValueError("presentation_fps_invalid")
    fps = float(fps_value)
    framing = str(_config_value(presentation_config, "framing"))
    if framing != "preserve_vertical_fov":
        raise ValueError(f"presentation_framing_unsupported:{framing}")

    cameras_by_name = {
        str(_config_value(config, "name")): config
        for config in model_camera_configs
    }
    specs = []
    for name in camera_names:
        camera = cameras_by_name.get(name)
        if camera is None:
            raise ValueError(f"presentation_camera_unknown:{name}")
        prim_path = str(_config_value(camera, "prim_path"))
        if not prim_path.startswith("/"):
            raise ValueError(f"presentation_camera_prim_path_invalid:{name}")
        specs.append(
            PresentationCameraSpec(
                name=name,
                source_prim_path=prim_path,
                prim_path=(
                    f"/World/LabUtopiaPresentationCameras/{name}"
                ),
                resolution=resolution,
                fps=fps,
            )
        )
    return tuple(specs)


def define_presentation_camera_prims(
    stage: Any,
    specs: Sequence[PresentationCameraSpec],
) -> None:
    from pxr import Usd, UsdGeom

    UsdGeom.Xform.Define(stage, "/World/LabUtopiaPresentationCameras")
    time_code = Usd.TimeCode.Default()
    for spec in specs:
        source_prim = stage.GetPrimAtPath(spec.source_prim_path)
        if (
            not source_prim
            or not source_prim.IsValid()
            or not source_prim.IsA(UsdGeom.Camera)
        ):
            raise RuntimeError(
                f"presentation_source_camera_invalid:{spec.source_prim_path}"
            )
        source = UsdGeom.Camera(source_prim)
        presentation = UsdGeom.Camera.Define(stage, spec.prim_path)
        presentation.SetFromCamera(source.GetCamera(time_code), time_code)
        vertical_aperture = float(
            source.GetVerticalApertureAttr().Get(time_code)
        )
        target_aspect = spec.resolution[0] / float(spec.resolution[1])
        presentation.GetHorizontalApertureAttr().Set(
            vertical_aperture * target_aspect,
            time_code,
        )


def _decode_viewport_buffer(
    buffer: Any,
    buffer_size: int,
    width: int,
    height: int,
    _format: Any,
) -> np.ndarray:
    import ctypes
    from PIL import Image

    ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.POINTER(
        ctypes.c_byte * buffer_size
    )
    ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [
        ctypes.py_object,
        ctypes.c_char_p,
    ]
    content = ctypes.pythonapi.PyCapsule_GetPointer(buffer, None)
    image = Image.frombytes("RGBA", (width, height), content.contents)
    return np.asarray(image, dtype=np.uint8)[..., :3].copy()


class ViewportPresentationFrameProvider:
    capture_policy = "viewport_same_observation_no_physics_step_v1"

    def __init__(
        self,
        *,
        viewport: Any,
        world: Any,
        schedule_capture: Callable[[Any, Callable[..., None]], Any],
        decode_buffer: Callable[..., np.ndarray] = _decode_viewport_buffer,
    ):
        self._viewport = viewport
        self._world = world
        self._schedule_capture = schedule_capture
        self._decode_buffer = decode_buffer

    def __call__(
        self,
        specs: Sequence[PresentationCameraSpec],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        original_camera_path = self._viewport.camera_path
        original_resolution = tuple(self._viewport.resolution)
        original_resolution_scale = self._viewport.resolution_scale
        time_before = float(self._world.current_time)
        step_before = int(self._world.current_time_step_index)
        render_count = 0
        frames = {}

        def render_without_physics() -> None:
            nonlocal render_count
            self._world.render()
            render_count += 1
            if (
                float(self._world.current_time) != time_before
                or int(self._world.current_time_step_index) != step_before
            ):
                raise RuntimeError(
                    "presentation_viewport_render_advanced_physics"
                )

        try:
            for spec in specs:
                self._viewport.camera_path = spec.prim_path
                self._viewport.resolution = spec.resolution
                self._viewport.resolution_scale = 1
                render_without_physics()
                render_without_physics()

                captured: dict[str, Any] = {}

                def on_capture(
                    buffer,
                    buffer_size,
                    width,
                    height,
                    pixel_format,
                ):
                    captured["rgb"] = self._decode_buffer(
                        buffer,
                        buffer_size,
                        width,
                        height,
                        pixel_format,
                    )

                capture_request = self._schedule_capture(
                    self._viewport,
                    on_capture,
                )
                for _ in range(8):
                    render_without_physics()
                    if "rgb" in captured:
                        break
                if "rgb" not in captured:
                    raise RuntimeError(
                        f"presentation_viewport_capture_timeout:{spec.name}"
                    )
                rgb = np.asarray(captured["rgb"])
                expected_shape = (
                    spec.resolution[1],
                    spec.resolution[0],
                    3,
                )
                if rgb.shape != expected_shape:
                    raise RuntimeError(
                        f"presentation_viewport_shape_invalid:{spec.name}:"
                        f"expected={expected_shape}:actual={rgb.shape}"
                    )
                frames[spec.name] = {
                    "rgb": rgb.copy(),
                    "current_frame": {
                        "rendering_frame": render_count,
                        "rendering_time": float(self._world.current_time),
                    },
                }
                del capture_request
        finally:
            self._viewport.camera_path = original_camera_path
            self._viewport.resolution = original_resolution
            self._viewport.resolution_scale = original_resolution_scale

        return frames, {
            "physics_and_timeline_unchanged": True,
            "time_before": time_before,
            "time_after": float(self._world.current_time),
            "step_before": step_before,
            "step_after": int(self._world.current_time_step_index),
            "render_count": render_count,
        }


def _opencv_writer_factory(
    path: Path,
    fps: float,
    resolution: tuple[int, int],
):
    import cv2

    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        resolution,
    )
    if not writer.isOpened():
        writer.release()
        raise RuntimeError(f"presentation_video_writer_open_failed:{path}")
    return writer


class PresentationVideoRecorder:
    def __init__(
        self,
        *,
        specs: Sequence[PresentationCameraSpec],
        output_dir: str | os.PathLike[str],
        camera_factory: Callable[[PresentationCameraSpec], Any] | None = None,
        frame_provider: Callable[
            [Sequence[PresentationCameraSpec]],
            tuple[dict[str, dict[str, Any]], dict[str, Any]],
        ]
        | None = None,
        writer_factory: Callable[
            [Path, float, tuple[int, int]], Any
        ] = _opencv_writer_factory,
    ) -> None:
        self._specs = tuple(specs)
        if len(self._specs) != 2:
            raise ValueError("presentation_camera_specs_two_required")
        self._output_dir = Path(output_dir)
        self._camera_factory = camera_factory
        self._frame_provider = frame_provider
        if self._camera_factory is None and self._frame_provider is None:
            raise ValueError("presentation_frame_source_required")
        self._writer_factory = writer_factory
        self._cameras: dict[str, Any] = {}
        self._writers: dict[str, Any] = {}
        self._attempts: list[dict[str, Any]] = []
        self._current_attempt_id: str | None = None
        self._current_episode_id: str | None = None
        self._current_frame_count = 0
        self._first_observation_index: int | None = None
        self._last_observation_index: int | None = None
        self._initialized = False

    @property
    def active_attempt(self) -> str | None:
        return self._current_attempt_id

    def initialize(self) -> None:
        if self._initialized:
            raise RuntimeError("presentation_recorder_already_initialized")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        if self._camera_factory is not None:
            for spec in self._specs:
                camera = self._camera_factory(spec)
                camera.initialize()
                self._cameras[spec.name] = camera
        self._initialized = True

    def _open_attempt(self, record: Mapping[str, Any]) -> None:
        attempt_id = str(record["attempt_id"])
        episode_id = str(record["episode_id"])
        if not attempt_id or not episode_id:
            raise ValueError("presentation_attempt_identity_invalid")
        self._current_attempt_id = attempt_id
        self._current_episode_id = episode_id
        self._current_frame_count = 0
        self._first_observation_index = None
        self._last_observation_index = None
        height = self._specs[0].resolution[1]
        for spec in self._specs:
            path = self._output_dir / (
                f"{attempt_id}_{episode_id}_{spec.name}_{height}p.mp4"
            )
            self._writers[spec.name] = self._writer_factory(
                path,
                spec.fps,
                spec.resolution,
            )

    def capture(self, record: Mapping[str, Any]) -> None:
        if not self._initialized:
            raise RuntimeError("presentation_recorder_not_initialized")
        render = record.get("render")
        if (
            not isinstance(render, Mapping)
            or render.get("physics_and_timeline_unchanged") is not True
        ):
            raise ValueError("presentation_capture_requires_stable_render")

        attempt_id = str(record["attempt_id"])
        if self._current_attempt_id is None:
            self._open_attempt(record)
        elif attempt_id != self._current_attempt_id:
            raise RuntimeError(
                "presentation_attempt_changed_without_close:"
                f"{self._current_attempt_id}:{attempt_id}"
            )

        if self._frame_provider is None:
            frame_payloads = {
                spec.name: {
                    "rgb": np.asarray(
                        self._cameras[spec.name].get_rgb()
                    ),
                    "current_frame": dict(
                        self._cameras[spec.name].get_current_frame()
                    ),
                }
                for spec in self._specs
            }
            synchronization = {
                "physics_and_timeline_unchanged": True,
            }
        else:
            frame_payloads, synchronization = self._frame_provider(
                self._specs
            )
        if synchronization.get("physics_and_timeline_unchanged") is not True:
            raise RuntimeError("presentation_frame_provider_advanced_physics")

        camera_frames = {}
        for spec in self._specs:
            payload = frame_payloads[spec.name]
            rgb = np.asarray(payload["rgb"])
            expected_shape = (
                spec.resolution[1],
                spec.resolution[0],
                3,
            )
            if rgb.shape != expected_shape:
                raise RuntimeError(
                    f"presentation_frame_shape_invalid:{spec.name}:"
                    f"expected={expected_shape}:actual={rgb.shape}"
                )
            if rgb.dtype != np.uint8:
                raise RuntimeError(
                    f"presentation_frame_dtype_invalid:{spec.name}:{rgb.dtype}"
                )
            bgr = np.ascontiguousarray(rgb[..., ::-1])
            self._writers[spec.name].write(bgr)
            current_frame = payload["current_frame"]
            camera_frames[spec.name] = {
                "rendering_frame": int(
                    current_frame.get("rendering_frame", -1)
                ),
                "rendering_time": float(
                    current_frame.get("rendering_time", 0.0)
                ),
            }

        observation_index = int(record["observation_index"])
        if self._first_observation_index is None:
            self._first_observation_index = observation_index
        self._last_observation_index = observation_index
        self._current_frame_count += 1
        frame_record = {
            "attempt_id": self._current_attempt_id,
            "episode_id": self._current_episode_id,
            "observation_index": observation_index,
            "frame_identity": str(record["frame_identity"]),
            "integration_step_after": int(record["integration_step_after"]),
            "logical_step_after": int(record["logical_step_after"]),
            "render_token": str(render["render_token"]),
            "physics_and_timeline_unchanged": True,
            "presentation_render": synchronization,
            "cameras": camera_frames,
        }
        with (
            self._output_dir / "presentation_video_frames.jsonl"
        ).open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(frame_record, sort_keys=True, separators=(",", ":"))
            )
            handle.write("\n")

    def close_attempt(self, *, status: str) -> None:
        if self._current_attempt_id is None:
            return
        if not isinstance(status, str) or not status:
            raise ValueError("presentation_attempt_status_required")

        for writer in self._writers.values():
            writer.release()
        height = self._specs[0].resolution[1]
        videos = [
            {
                "name": spec.name,
                "source_prim_path": spec.source_prim_path,
                "prim_path": spec.prim_path,
                "resolution": list(spec.resolution),
                "fps": spec.fps,
                "path": (
                    f"{self._current_attempt_id}_{self._current_episode_id}_"
                    f"{spec.name}_{height}p.mp4"
                ),
            }
            for spec in self._specs
        ]
        self._attempts.append(
            {
                "attempt_id": self._current_attempt_id,
                "episode_id": self._current_episode_id,
                "status": status,
                "frame_count": self._current_frame_count,
                "observation_index_range": [
                    self._first_observation_index,
                    self._last_observation_index,
                ],
                "videos": videos,
            }
        )
        self._write_manifest()
        self._writers = {}
        self._current_attempt_id = None
        self._current_episode_id = None
        self._current_frame_count = 0
        self._first_observation_index = None
        self._last_observation_index = None

    def _write_manifest(self) -> None:
        manifest = {
            "schema_version": 1,
            "capture_policy": (
                getattr(
                    self._frame_provider,
                    "capture_policy",
                    "same_render_no_additional_physics_step_v1",
                )
                if self._frame_provider is not None
                else "same_render_no_additional_physics_step_v1"
            ),
            "attempts": self._attempts,
        }
        destination = self._output_dir / "presentation_video_manifest.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)

    def close(self) -> None:
        self.close_attempt(status="interrupted")


def build_isaac_presentation_video_recorder(
    *,
    model_camera_configs: Sequence[Any],
    world: Any,
    presentation_config: Any,
    output_dir: str | os.PathLike[str],
) -> PresentationVideoRecorder:
    specs = resolve_presentation_camera_specs(
        model_camera_configs,
        presentation_config,
    )
    import omni.usd
    from omni.kit.viewport.utility import (
        capture_viewport_to_buffer,
        get_active_viewport,
    )

    define_presentation_camera_prims(
        omni.usd.get_context().get_stage(),
        specs,
    )
    viewport = get_active_viewport()
    if viewport is None:
        raise RuntimeError("presentation_active_viewport_required")
    frame_provider = ViewportPresentationFrameProvider(
        viewport=viewport,
        world=world,
        schedule_capture=capture_viewport_to_buffer,
    )

    return PresentationVideoRecorder(
        specs=specs,
        output_dir=output_dir,
        frame_provider=frame_provider,
    )

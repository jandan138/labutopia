"""Canonical visible-interior frame derivation for the localized real beaker."""

from __future__ import annotations

from collections.abc import Mapping, Sequence as SequenceABC
from dataclasses import dataclass, field
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
import statistics
from types import MappingProxyType
from typing import Any, Iterable, Sequence

from pxr import Gf, Usd, UsdGeom


_FALLBACK_WALL_CLEARANCE = 0.005
_RADIUS_CLAMP_EPSILON = 0.000001


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_int(name: str, value: Any) -> int:
    if type(value) is not int:
        raise ValueError(f"{name}_must_be_non_bool_int")
    return value


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(left[index]) * float(right[index]) for index in range(3))


def _cross(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (
        float(left[1]) * float(right[2]) - float(left[2]) * float(right[1]),
        float(left[2]) * float(right[0]) - float(left[0]) * float(right[2]),
        float(left[0]) * float(right[1]) - float(left[1]) * float(right[0]),
    )


def _normalize(vector: Sequence[float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot(vector, vector))
    if length == 0.0:
        raise ValueError("cannot_normalize_zero_length_vector")
    return tuple(float(component) / length for component in vector)


def _as_tuple(point: Sequence[float]) -> tuple[float, float, float]:
    return tuple(float(point[index]) for index in range(3))


def _bounds(points: Iterable[Sequence[float]]) -> dict[str, tuple[float, float, float]]:
    values = [_as_tuple(point) for point in points]
    if not values:
        raise ValueError("cannot_measure_empty_point_set")
    minimum = tuple(min(point[index] for point in values) for index in range(3))
    maximum = tuple(max(point[index] for point in values) for index in range(3))
    return {
        "min": minimum,
        "max": maximum,
        "size": tuple(maximum[index] - minimum[index] for index in range(3)),
    }


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_thaw_json(item) for item in value)
    return value


@dataclass(frozen=True)
class CupInteriorFrame:
    origin_world: tuple[float, float, float]
    x_axis_world: tuple[float, float, float]
    y_axis_world: tuple[float, float, float]
    z_axis_world: tuple[float, float, float]
    parent_local_axis: str
    outer_radius: float
    interior_radius: float
    outer_floor: float
    interior_floor: float
    rim_height: float
    calibration_source: str
    axis_alignment_dot: float
    _measurements: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_measurements", _freeze_json(self._measurements))

    def world_to_canonical(self, point: Sequence[float]) -> tuple[float, float, float]:
        delta = tuple(float(point[index]) - self.origin_world[index] for index in range(3))
        return (
            _dot(delta, self.x_axis_world),
            _dot(delta, self.y_axis_world),
            _dot(delta, self.z_axis_world),
        )

    def canonical_to_world(self, point: Sequence[float]) -> tuple[float, float, float]:
        return tuple(
            self.origin_world[index]
            + float(point[0]) * self.x_axis_world[index]
            + float(point[1]) * self.y_axis_world[index]
            + float(point[2]) * self.z_axis_world[index]
            for index in range(3)
        )

    def as_dict(self) -> dict[str, Any]:
        """Return primitive values suitable for JSON evidence serialization."""
        return {
            "origin_world": self.origin_world,
            "x_axis_world": self.x_axis_world,
            "y_axis_world": self.y_axis_world,
            "z_axis_world": self.z_axis_world,
            "parent_local_axis": self.parent_local_axis,
            "outer_radius": self.outer_radius,
            "interior_radius": self.interior_radius,
            "outer_floor": self.outer_floor,
            "interior_floor": self.interior_floor,
            "rim_height": self.rim_height,
            "calibration_source": self.calibration_source,
            "axis_alignment_dot": self.axis_alignment_dot,
            **_thaw_json(self._measurements),
        }


@dataclass(frozen=True)
class VisibleBeakerSpawn:
    positions_world: tuple[tuple[float, float, float], ...]
    velocities_world: tuple[tuple[float, float, float], ...]
    physics_particle_width: float
    particle_contact_offset: float
    canonical_bounds: Mapping[str, Any]
    physics_offsets: Mapping[str, float]
    particle_seed: int
    particle_count: int
    derived_layer_count: int
    lattice_capacity: int
    positions_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_bounds", _freeze_json(self.canonical_bounds))
        object.__setattr__(self, "physics_offsets", _freeze_json(self.physics_offsets))


def _radial_lattice_capacity(radius: float, spacing: float) -> int:
    samples_per_axis = int(math.ceil((radius * 2.0) / spacing)) + 1
    start = -radius
    return sum(
        1
        for ix in range(samples_per_axis)
        for iy in range(samples_per_axis)
        if math.hypot(start + ix * spacing, start + iy * spacing) <= radius
    )


def build_visible_beaker_spawn(
    frame: CupInteriorFrame,
    plan: Mapping[str, Any],
    *,
    physics_particle_width: float,
    particle_contact_offset: float,
) -> VisibleBeakerSpawn:
    """Build the controlled radial lattice inside the measured real beaker."""
    from tools.labutopia_fluid.run_beaker_collider_smoke import (
        ColliderConfig,
        build_source_particle_positions,
    )

    count = int(plan["particle_count"])
    seed = int(plan.get("particle_seed", 0))
    layout = plan["spawn_layout"]
    spacing = float(layout["particle_spacing"])
    inset = float(layout["interior_inset"])
    if count >= 4096:
        inset = max(inset, 0.008)
    radial_clearance = max(float(particle_contact_offset) * 1.2, inset)
    usable_radius = frame.interior_radius - radial_clearance
    if usable_radius <= 0.0:
        raise ValueError("visible_beaker_spawn_has_no_radial_capacity")
    per_layer_capacity = _radial_lattice_capacity(usable_radius, spacing)
    if per_layer_capacity <= 0:
        raise ValueError("visible_beaker_spawn_has_no_lattice_candidates")
    layer_count = int(math.ceil(count / per_layer_capacity))

    config = ColliderConfig(
        particle_count=count,
        particle_seed=seed,
        grid_dims=(int(layout["grid_dims"][0]), int(layout["grid_dims"][1]), layer_count),
        particle_spacing=spacing,
        particle_width=float(physics_particle_width),
        particle_contact_offset=float(particle_contact_offset),
        spawn_particle_contact_offset=float(particle_contact_offset),
        source_center=(0.0, 0.0, frame.interior_floor),
        source_radius=frame.interior_radius,
        source_height=frame.rim_height - frame.interior_floor,
        bottom_thickness=0.012,
        interior_inset=inset,
        collider_contact_offset=float(layout["collider_contact_offset"]),
        table_z=frame.interior_floor,
        initial_radial_velocity=0.0,
        spawn_prefer_interior=True,
    )
    positions_canonical = tuple(build_source_particle_positions(config))
    top_clearance = max(float(particle_contact_offset), float(physics_particle_width) / 2.0)
    if max(point[2] for point in positions_canonical) + top_clearance >= frame.rim_height:
        raise ValueError("visible_beaker_spawn_reaches_rim")
    positions_world = tuple(frame.canonical_to_world(point) for point in positions_canonical)
    velocities = tuple((0.0, 0.0, 0.0) for _ in positions_world)
    return VisibleBeakerSpawn(
        positions_world=positions_world,
        velocities_world=velocities,
        physics_particle_width=float(physics_particle_width),
        particle_contact_offset=float(particle_contact_offset),
        canonical_bounds=_bounds(positions_canonical),
        physics_offsets={
            "particle_width": float(physics_particle_width),
            "particle_contact_offset": float(particle_contact_offset),
            "collider_contact_offset": float(layout["collider_contact_offset"]),
            "radial_clearance": radial_clearance,
            "bottom_lift": 0.012,
        },
        particle_seed=seed,
        particle_count=count,
        derived_layer_count=layer_count,
        lattice_capacity=per_layer_capacity * layer_count,
        positions_sha256=_json_sha256(positions_world),
    )


def classify_visible_beaker_positions(
    positions_world: Iterable[Sequence[float]],
    frame: CupInteriorFrame,
    *,
    legacy_region_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Count points against the measured visible interior in canonical space."""
    canonical: list[tuple[float, float, float]] = []
    finite_count = 0
    nonfinite_count = 0
    below_floor = 0
    outside_radius = 0
    above_rim = 0
    inside = 0
    violating = 0
    legacy_source = 0

    for point in positions_world:
        point_tuple = _as_tuple(point)
        is_finite = all(math.isfinite(value) for value in point_tuple)
        if not is_finite:
            nonfinite_count += 1
            violating += 1
            continue
        finite_count += 1
        coordinate = frame.world_to_canonical(point_tuple)
        canonical.append(coordinate)
        radius = math.hypot(coordinate[0], coordinate[1])
        is_below = coordinate[2] < frame.interior_floor
        is_outside = radius > frame.interior_radius
        is_above = coordinate[2] >= frame.rim_height
        below_floor += int(is_below)
        outside_radius += int(is_outside)
        above_rim += int(is_above)
        point_violates = is_below or is_outside or is_above
        violating += int(point_violates)
        inside += int(not point_violates)

        if legacy_region_config is not None:
            center = legacy_region_config.get("source_center", (0.0, 0.0, 0.0))
            radial = math.hypot(
                point_tuple[0] - float(center[0]), point_tuple[1] - float(center[1])
            )
            floor = float(legacy_region_config.get("table_z", center[2]))
            ceiling = floor + float(legacy_region_config.get("source_height", math.inf))
            legacy_source += int(
                radial <= float(legacy_region_config.get("source_radius", math.inf))
                and floor <= point_tuple[2] <= ceiling
            )

    axial = [point[2] for point in canonical]
    radii = [math.hypot(point[0], point[1]) for point in canonical]
    return {
        "particle_count": finite_count + nonfinite_count,
        "inside_visible_interior_count": inside,
        "below_visible_floor_count": below_floor,
        "outside_visible_radial_count": outside_radius,
        "above_visible_rim_count": above_rim,
        "legacy_source_region_count": legacy_source,
        "canonical_axial_min": min(axial) if axial else None,
        "canonical_axial_median": statistics.median(axial) if axial else None,
        "canonical_axial_max": max(axial) if axial else None,
        "maximum_canonical_radius": max(radii) if radii else None,
        "finite_count": finite_count,
        "nonfinite_count": nonfinite_count,
        "strict_violating_point_count": violating,
    }


def validate_strict_trace_schema(
    records: Sequence[Mapping[str, Any]],
    *,
    requested_count: int,
    steps: int,
    cadence: int,
    source_usd_sha256: str,
    particle_seed: int,
) -> dict[str, Any]:
    """Validate complete readback evidence and return its replay identity."""
    if not records:
        raise ValueError("trace_has_no_records")
    requested_count = _require_int("requested_count", requested_count)
    steps = _require_int("steps", steps)
    cadence = _require_int("cadence", cadence)
    particle_seed = _require_int("particle_seed", particle_seed)
    if requested_count <= 0 or steps < 0 or cadence <= 0:
        raise ValueError("invalid_trace_contract")
    expected_steps = list(range(0, steps + 1, cadence))
    if expected_steps[-1] != steps:
        expected_steps.append(steps)
    actual_steps = [
        _require_int(f"record_{index}_step_index", record["step_index"])
        for index, record in enumerate(records)
    ]
    if actual_steps != expected_steps or len(set(actual_steps)) != len(actual_steps):
        raise ValueError(f"trace_step_indices_mismatch:{actual_steps}!={expected_steps}")

    counts: list[int] = []
    ordered_positions: list[Any] = []
    for index, record in enumerate(records):
        positions = record.get("positions")
        if not isinstance(positions, list):
            raise ValueError(f"trace_positions_missing:{index}")
        count = _require_int(f"record_{index}_particle_count", record.get("particle_count"))
        if count != len(positions):
            raise ValueError(f"trace_particle_count_mismatch:{index}")
        if not 0 < count <= requested_count:
            raise ValueError(f"trace_particle_count_out_of_range:{index}")
        if index == 0 and count != requested_count:
            raise ValueError("trace_initial_count_mismatch")
        for point_index, point in enumerate(positions):
            if (
                not isinstance(point, SequenceABC)
                or isinstance(point, (str, bytes))
                or len(point) != 3
                or any(not isinstance(value, Real) or isinstance(value, bool) for value in point)
            ):
                raise ValueError(f"trace_point_schema_invalid:{index}:{point_index}")
        finite = sum(
            1
            for point in positions
            if all(math.isfinite(float(value)) for value in point)
        )
        nonfinite = count - finite
        declared_finite = record.get(
            "finite_count", record.get("region_counts", {}).get("finite_count")
        )
        declared_nonfinite = record.get("nonfinite_count")
        if declared_finite is not None and int(declared_finite) != finite:
            raise ValueError(f"trace_finite_count_mismatch:{index}")
        if declared_nonfinite is not None and int(declared_nonfinite) != nonfinite:
            raise ValueError(f"trace_nonfinite_count_mismatch:{index}")
        if finite + nonfinite != count:
            raise ValueError(f"trace_finite_partition_mismatch:{index}")
        counts.append(count)
        ordered_positions.append(positions)

    positions_sha256 = _json_sha256(ordered_positions)
    contract = {
        "frame_indices": actual_steps,
        "frame_particle_counts": counts,
        "frame_count": len(records),
        "source_usd_sha256": source_usd_sha256,
        "particle_count": requested_count,
        "seed": particle_seed,
        "steps": steps,
        "trace_interval": cadence,
        "positions_sha256": positions_sha256,
    }
    contract["physical_trace_sha256"] = _json_sha256(contract)
    return contract


def strict_static_hold_pass(result: Mapping[str, Any]) -> bool:
    initial_count = int(result["initial_count"])
    final_count = int(result["final_count"])
    return (
        final_count > 0
        and initial_count > 0
        and final_count / initial_count >= 0.95
        and int(result["max_below_floor"]) == 0
        and int(result["max_outside_radius"]) == 0
        and int(result["max_above_rim"]) == 0
        and int(result["final_inside"]) == final_count
        and int(result["nonfinite_count"]) == 0
        and float(result["tail_leak_rate"]) == 0.0
        and not bool(result["particle_explosion_detected"])
        and bool(result["readback_available"])
        and bool(result["trace_schema_valid"])
        and bool(result["diagnostic_scan_complete"])
        and not bool(result["cpu_collision_fallback_detected"])
        and not bool(result["gpu_collider_unsupported"])
        and result["fatal_error"] is None
    )


def _scan_run_diagnostics(log_text: str | None) -> tuple[bool, bool]:
    text = (log_text or "").lower()
    cpu_fallback = any(
        marker in text
        for marker in (
            "fallback to cpu collision",
            "falling back to cpu collision",
            "cpu collision fallback",
        )
    )
    gpu_unsupported = any(
        marker in text
        for marker in (
            "gpu collider unsupported",
            "gpu collision unsupported",
            "unsupported gpu collider",
            "gpu rigid body pipeline does not support",
        )
    )
    return cpu_fallback, gpu_unsupported


def classify_visible_beaker_trace(
    records: Sequence[Mapping[str, Any]],
    frame: CupInteriorFrame,
    *,
    requested_count: int,
    steps: int,
    cadence: int,
    tail_window_steps: int,
    source_usd_sha256: str,
    particle_seed: int = 0,
    legacy_region_config: Mapping[str, Any] | None = None,
    diagnostic_log_text: str | None = None,
    diagnostic_scan_complete: bool = False,
    fatal_error: str | None = None,
    readback_available: bool = True,
) -> dict[str, Any]:
    """Classify a complete trace without assigning identity to particle order."""
    try:
        tail_window_steps = _require_int("tail_window_steps", tail_window_steps)
        identity = validate_strict_trace_schema(
            records,
            requested_count=requested_count,
            steps=steps,
            cadence=cadence,
            source_usd_sha256=source_usd_sha256,
            particle_seed=particle_seed,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return {
            "classification": "STOP_INCOMPLETE_TRACE",
            "trace_schema_valid": False,
            "trace_schema_error": str(exc),
            "diagnostic_scan_complete": bool(diagnostic_scan_complete),
        }

    frames = []
    particle_explosion = False
    cup_height = frame.rim_height - frame.interior_floor
    for record in records:
        classified = classify_visible_beaker_positions(
            record["positions"], frame, legacy_region_config=legacy_region_config
        )
        classified["step_index"] = record["step_index"]
        frames.append(classified)
        if classified["nonfinite_count"]:
            particle_explosion = True
        if classified["maximum_canonical_radius"] is not None:
            particle_explosion |= (
                classified["maximum_canonical_radius"] > frame.interior_radius * 10.0
            )
        if classified["canonical_axial_min"] is not None:
            particle_explosion |= (
                classified["canonical_axial_min"]
                < frame.interior_floor - cup_height * 10.0
            )
            particle_explosion |= (
                classified["canonical_axial_max"] > frame.rim_height + cup_height * 10.0
            )

    tail_start = steps - max(tail_window_steps, 0)
    tail_frames = [item for item in frames if item["step_index"] >= tail_start]
    tail_violations = sum(item["strict_violating_point_count"] for item in tail_frames)
    tail_population = sum(item["particle_count"] for item in tail_frames)
    cpu_fallback, gpu_unsupported = _scan_run_diagnostics(diagnostic_log_text)
    result = {
        "initial_count": frames[0]["particle_count"],
        "final_count": frames[-1]["particle_count"],
        "final_inside": frames[-1]["inside_visible_interior_count"],
        "inside_visible_interior_count": frames[-1]["inside_visible_interior_count"],
        "below_visible_floor_count": max(item["below_visible_floor_count"] for item in frames),
        "outside_visible_radial_count": max(
            item["outside_visible_radial_count"] for item in frames
        ),
        "above_visible_rim_count": max(item["above_visible_rim_count"] for item in frames),
        "max_below_floor": max(item["below_visible_floor_count"] for item in frames),
        "max_outside_radius": max(item["outside_visible_radial_count"] for item in frames),
        "max_above_rim": max(item["above_visible_rim_count"] for item in frames),
        "nonfinite_count": sum(item["nonfinite_count"] for item in frames),
        "tail_leak_rate": tail_violations / tail_population if tail_population else math.inf,
        "particle_explosion_detected": particle_explosion,
        "diagnostic_scan_complete": bool(diagnostic_scan_complete),
        "cpu_collision_fallback_detected": cpu_fallback,
        "gpu_collider_unsupported": gpu_unsupported,
        "fatal_error": fatal_error,
        "readback_available": bool(readback_available),
        "trace_schema_valid": True,
        "physical_trace_identity": identity,
        "frames": frames,
    }
    passed = strict_static_hold_pass(result)
    if fatal_error is not None:
        classification = "FAIL_RUNTIME_FATAL_ERROR"
    elif not readback_available:
        classification = "FAIL_READBACK_UNAVAILABLE"
    elif not diagnostic_scan_complete:
        classification = "STOP_INCOMPLETE_DIAGNOSTICS"
    elif cpu_fallback:
        classification = "FAIL_CPU_COLLISION_FALLBACK"
    elif gpu_unsupported:
        classification = "FAIL_GPU_COLLIDER_UNSUPPORTED"
    elif particle_explosion:
        classification = "FAIL_PARTICLE_EXPLOSION"
    elif passed:
        classification = "PASS_VISIBLE_BEAKER_STATIC_HOLD"
    else:
        classification = "FAIL_VISIBLE_BEAKER_CONTAINMENT"
    result["passed"] = passed
    result["classification"] = classification
    return result


def classify_visible_beaker_trace_from_files(*, manifest_path: str | Path) -> dict[str, Any]:
    try:
        manifest_file = Path(manifest_path)
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        source_path = Path(manifest["source_usd_path"])
        trace_path = Path(manifest["trace_path"])
        region_config = manifest["region_config"]
        plan = manifest["controlled_spawn_plan"]
        requested_count = _require_int(
            "selected_particle_count", manifest["selected_particle_count"]
        )
        steps = _require_int("steps", manifest["steps"])
        cadence = _require_int("trace_interval", region_config["trace_interval"])
        tail_window_steps = _require_int(
            "tail_window_steps", region_config["tail_window_steps"]
        )
        particle_seed = _require_int("particle_seed", plan["particle_seed"])
        if not source_path.is_absolute():
            source_path = manifest_file.parent / source_path
        if not trace_path.is_absolute():
            trace_path = manifest_file.parent / trace_path
        stage = Usd.Stage.Open(str(source_path))
        if stage is None:
            raise ValueError(f"cannot_open_source_usd:{source_path}")
        frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker2",
            visual_mesh_path="/World/beaker2/mesh",
            calibration_points_path="/World/ParticleSet",
        )
        records = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
        ]
        diagnostics = manifest.get("isaac_log_summary", {})
        log_available = diagnostics.get("isaac_log_available") is True
        log_text = None
        if log_available:
            try:
                log_text = Path(diagnostics["isaac_log_path"]).read_text(
                    encoding="utf-8", errors="replace"
                )
            except (KeyError, OSError, TypeError):
                log_available = False
        result = classify_visible_beaker_trace(
            records,
            frame,
            requested_count=requested_count,
            steps=steps,
            cadence=cadence,
            tail_window_steps=tail_window_steps,
            source_usd_sha256=_sha256_file(source_path),
            particle_seed=particle_seed,
            legacy_region_config=region_config,
            diagnostic_log_text=log_text,
            diagnostic_scan_complete=log_available,
            fatal_error=manifest.get("runtime_exception") or manifest.get("fatal_error"),
            readback_available=manifest.get("readback_diagnostics", {}).get(
                "readback_available", False
            ),
        )
    except Exception as exc:
        return {
            "classification": "STOP_INCOMPLETE_TRACE",
            "trace_schema_error": str(exc),
        }
    result["source_usd_path"] = str(source_path)
    result["trace_path"] = str(trace_path)
    return result


def _parent_axes_world(parent_world: Gf.Matrix4d) -> tuple[tuple[float, float, float], ...]:
    origin = parent_world.Transform(Gf.Vec3d(0.0, 0.0, 0.0))
    axes = []
    for index in range(3):
        local = Gf.Vec3d(*(1.0 if coordinate == index else 0.0 for coordinate in range(3)))
        endpoint = parent_world.Transform(local)
        axes.append(_normalize(tuple(float(endpoint[coordinate] - origin[coordinate]) for coordinate in range(3))))
    return tuple(axes)


def _points_in_parent_space(
    points: Iterable[Sequence[float]],
    *,
    points_world: Gf.Matrix4d,
    parent_world: Gf.Matrix4d,
) -> list[tuple[float, float, float]]:
    parent_inverse = parent_world.GetInverse()
    # Transform each authored point through its composed prim transform before
    # entering parent space; never derive local geometry from a world AABB.
    return [
        _as_tuple(parent_inverse.Transform(points_world.Transform(point)))
        for point in points
    ]


def _canonical_coordinates(
    points_parent: Iterable[Sequence[float]],
    *,
    origin_parent: Sequence[float],
    x_axis_parent: Sequence[float],
    y_axis_parent: Sequence[float],
    z_axis_parent: Sequence[float],
) -> list[tuple[float, float, float]]:
    coordinates = []
    for point in points_parent:
        delta = tuple(float(point[index]) - float(origin_parent[index]) for index in range(3))
        coordinates.append(
            (
                _dot(delta, x_axis_parent),
                _dot(delta, y_axis_parent),
                _dot(delta, z_axis_parent),
            )
        )
    return coordinates


def derive_cup_interior_frame(
    stage: Usd.Stage,
    *,
    parent_path: str,
    visual_mesh_path: str,
    calibration_points_path: str | None,
) -> CupInteriorFrame:
    """Derive the visible beaker frame from composed mesh and particle points."""
    parent_prim = stage.GetPrimAtPath(parent_path)
    mesh_prim = stage.GetPrimAtPath(visual_mesh_path)
    if not parent_prim.IsValid():
        raise ValueError(f"invalid_parent_path:{parent_path}")
    if not mesh_prim.IsValid():
        raise ValueError(f"invalid_visual_mesh_path:{visual_mesh_path}")

    time = Usd.TimeCode.Default()
    mesh_points = UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get(time)
    if not mesh_points:
        raise ValueError(f"visual_mesh_has_no_points:{visual_mesh_path}")

    cache = UsdGeom.XformCache(time)
    parent_world = cache.GetLocalToWorldTransform(parent_prim)
    mesh_points_parent = _points_in_parent_space(
        mesh_points,
        points_world=cache.GetLocalToWorldTransform(mesh_prim),
        parent_world=parent_world,
    )
    mesh_bounds = _bounds(mesh_points_parent)

    stage_up_axis = str(UsdGeom.GetStageUpAxis(stage)).upper()
    if not stage.HasAuthoredMetadata("upAxis"):
        # The localized source and in-memory regression fixture both omit upAxis.
        # Their real-beaker contract is Z-up rather than OpenUSD's default Y-up.
        stage_up_axis = "Z"
    if stage_up_axis not in "XYZ":
        raise ValueError(f"unsupported_stage_up_axis:{stage_up_axis}")
    stage_up = tuple(1.0 if axis == stage_up_axis else 0.0 for axis in "XYZ")
    parent_axes_world = _parent_axes_world(parent_world)
    aligned_axis_index = max(range(3), key=lambda index: abs(_dot(parent_axes_world[index], stage_up)))
    aligned_dot = _dot(parent_axes_world[aligned_axis_index], stage_up)
    axis_sign = 1.0 if aligned_dot >= 0.0 else -1.0
    z_axis_parent = tuple(axis_sign if index == aligned_axis_index else 0.0 for index in range(3))
    z_axis_world = tuple(axis_sign * component for component in parent_axes_world[aligned_axis_index])
    axis_alignment_dot = _dot(z_axis_world, stage_up)

    x_axis_index = 0 if aligned_axis_index != 0 else 1
    x_candidate_parent = tuple(1.0 if index == x_axis_index else 0.0 for index in range(3))
    x_axis_parent = _normalize(
        tuple(
            x_candidate_parent[index] - _dot(x_candidate_parent, z_axis_parent) * z_axis_parent[index]
            for index in range(3)
        )
    )
    y_axis_parent = _normalize(_cross(z_axis_parent, x_axis_parent))
    x_axis_world = _normalize(
        tuple(
            sum(parent_axes_world[index][component] * x_axis_parent[index] for index in range(3))
            for component in range(3)
        )
    )
    y_axis_world = _normalize(
        tuple(
            sum(parent_axes_world[index][component] * y_axis_parent[index] for index in range(3))
            for component in range(3)
        )
    )
    if _dot(_cross(x_axis_world, y_axis_world), z_axis_world) < 0.999:
        raise ValueError("canonical_radial_basis_is_not_right_handed")

    axial_values = [_dot(point, z_axis_parent) for point in mesh_points_parent]
    radial_midpoint = [
        (mesh_bounds["min"][index] + mesh_bounds["max"][index]) / 2.0
        for index in range(3)
    ]
    axial_floor_parent = min(axial_values)
    for index in range(3):
        radial_midpoint[index] += (
            axial_floor_parent - _dot(radial_midpoint, z_axis_parent)
        ) * z_axis_parent[index]
    origin_parent = tuple(radial_midpoint)
    origin_world = _as_tuple(parent_world.Transform(Gf.Vec3d(*origin_parent)))

    mesh_canonical = _canonical_coordinates(
        mesh_points_parent,
        origin_parent=origin_parent,
        x_axis_parent=x_axis_parent,
        y_axis_parent=y_axis_parent,
        z_axis_parent=z_axis_parent,
    )
    mesh_canonical_bounds = _bounds(mesh_canonical)
    outer_radius = min(
        abs(min(point[0] for point in mesh_canonical)),
        abs(max(point[0] for point in mesh_canonical)),
        abs(min(point[1] for point in mesh_canonical)),
        abs(max(point[1] for point in mesh_canonical)),
    )
    outer_floor = min(point[2] for point in mesh_canonical)
    rim_height = max(point[2] for point in mesh_canonical)

    calibration_measurements: dict[str, Any] = {
        "calibration_points_path": calibration_points_path,
        "parent_local_mesh_bounds": mesh_bounds,
        "raw_radial_envelope": None,
        "outer_to_calibrated_wall_clearance": None,
        "applied_wall_clearance": 0.0,
        "fallback_wall_clearance": None,
        "final_radius": None,
        "parent_local_calibration_bounds": None,
    }
    calibration_source = "fallback_mesh_inscribed_radius"
    calibration_prim = stage.GetPrimAtPath(calibration_points_path) if calibration_points_path else None
    calibration_points = None
    if calibration_prim and calibration_prim.IsValid():
        calibration_points = UsdGeom.Points(calibration_prim).GetPointsAttr().Get(time)

    if calibration_points:
        calibration_parent = _points_in_parent_space(
            calibration_points,
            points_world=cache.GetLocalToWorldTransform(calibration_prim),
            parent_world=parent_world,
        )
        calibration_canonical = _canonical_coordinates(
            calibration_parent,
            origin_parent=origin_parent,
            x_axis_parent=x_axis_parent,
            y_axis_parent=y_axis_parent,
            z_axis_parent=z_axis_parent,
        )
        raw_radial_envelope = max(math.hypot(point[0], point[1]) for point in calibration_canonical)
        interior_radius = min(raw_radial_envelope, outer_radius - _RADIUS_CLAMP_EPSILON)
        calibration_source = "authored_particle_bounds"
        calibration_measurements.update(
            {
                "raw_radial_envelope": raw_radial_envelope,
                "outer_to_calibrated_wall_clearance": outer_radius - interior_radius,
                "final_radius": interior_radius,
                "parent_local_calibration_bounds": _bounds(calibration_parent),
            }
        )
    else:
        interior_radius = outer_radius - _FALLBACK_WALL_CLEARANCE
        if interior_radius <= 0.0:
            raise ValueError("fallback_wall_clearance_exceeds_outer_radius")
        calibration_measurements.update(
            {
                "raw_radial_envelope": outer_radius,
                "outer_to_calibrated_wall_clearance": _FALLBACK_WALL_CLEARANCE,
                "fallback_wall_clearance": _FALLBACK_WALL_CLEARANCE,
                "final_radius": interior_radius,
            }
        )

    return CupInteriorFrame(
        origin_world=origin_world,
        x_axis_world=x_axis_world,
        y_axis_world=y_axis_world,
        z_axis_world=z_axis_world,
        parent_local_axis=("" if axis_sign > 0.0 else "-") + "XYZ"[aligned_axis_index],
        outer_radius=outer_radius,
        interior_radius=interior_radius,
        outer_floor=outer_floor,
        interior_floor=outer_floor,
        rim_height=rim_height,
        calibration_source=calibration_source,
        axis_alignment_dot=axis_alignment_dot,
        _measurements={
            "parent_path": parent_path,
            "visual_mesh_path": visual_mesh_path,
            "parent_local_mesh_bounds": mesh_bounds,
            "canonical_mesh_bounds": mesh_canonical_bounds,
            "calibration": calibration_measurements,
        },
    )

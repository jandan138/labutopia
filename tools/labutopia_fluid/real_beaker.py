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


def _minimum_lattice_radius(required_count: int, spacing: float) -> float:
    radius = 0.0
    increment = spacing / 2.0
    while _radial_lattice_capacity(radius, spacing) < required_count:
        radius += increment
    return radius


def build_visible_beaker_spawn(
    frame: CupInteriorFrame,
    plan: Mapping[str, Any],
    *,
    physics_particle_width: float,
    particle_contact_offset: float,
    fluid_rest_offset: float | None = None,
) -> VisibleBeakerSpawn:
    """Build the controlled radial lattice inside the measured real beaker."""
    from tools.labutopia_fluid.run_beaker_collider_smoke import (
        ColliderConfig,
        build_source_particle_positions,
    )

    count = int(plan["particle_count"])
    seed = int(plan.get("particle_seed", 0))
    layout = plan["spawn_layout"]
    recipe_spacing = float(layout["particle_spacing"])
    resolved_fluid_rest_offset = (
        float(fluid_rest_offset)
        if fluid_rest_offset is not None
        else float(physics_particle_width) * 0.58806
    )
    if resolved_fluid_rest_offset <= 0.0:
        raise ValueError("visible_beaker_fluid_rest_offset_must_be_positive")
    spacing = 2.0 * resolved_fluid_rest_offset
    inset = float(layout["interior_inset"])
    if count >= 4096:
        inset = max(inset, 0.008)
    radial_clearance = max(float(particle_contact_offset) * 1.2, inset)
    maximum_usable_radius = frame.interior_radius - radial_clearance
    if maximum_usable_radius <= 0.0:
        raise ValueError("visible_beaker_spawn_has_no_radial_capacity")
    layer_count = int(math.ceil(count ** (1.0 / 3.0)))
    required_per_layer = int(math.ceil(count / layer_count))
    usable_radius = _minimum_lattice_radius(required_per_layer, spacing)
    if usable_radius > maximum_usable_radius:
        raise ValueError("visible_beaker_dense_spawn_exceeds_interior_radius")
    per_layer_capacity = _radial_lattice_capacity(usable_radius, spacing)
    if per_layer_capacity <= 0:
        raise ValueError("visible_beaker_spawn_has_no_lattice_candidates")

    config = ColliderConfig(
        particle_count=count,
        particle_seed=seed,
        grid_dims=(int(layout["grid_dims"][0]), int(layout["grid_dims"][1]), layer_count),
        particle_spacing=spacing,
        particle_width=float(physics_particle_width),
        particle_contact_offset=float(particle_contact_offset),
        spawn_particle_contact_offset=float(particle_contact_offset),
        source_center=(0.0, 0.0, frame.interior_floor),
        source_radius=usable_radius + radial_clearance,
        source_height=frame.rim_height - frame.interior_floor,
        bottom_thickness=0.0,
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
            "bottom_lift": 0.0,
            "fluid_rest_offset": resolved_fluid_rest_offset,
            "particle_spacing": spacing,
            "legacy_recipe_particle_spacing": recipe_spacing,
            "dense_spawn_radius": usable_radius,
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
        region_counts: Mapping[str, Any] = {}
        if "region_counts" in record:
            candidate = record["region_counts"]
            if not isinstance(candidate, Mapping):
                raise ValueError(f"trace_region_counts_invalid:{index}")
            region_counts = candidate
        for location, declared_counts in (
            ("top_level", record),
            ("region_counts", region_counts),
        ):
            for field_name, expected_count in (
                ("finite_count", finite),
                ("nonfinite_count", nonfinite),
            ):
                if field_name not in declared_counts:
                    continue
                declared_count = _require_int(
                    f"record_{index}_{location}_{field_name}",
                    declared_counts[field_name],
                )
                if declared_count != expected_count:
                    raise ValueError(f"trace_{field_name}_mismatch:{index}:{location}")
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
    from pxr import Usd

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
    from pxr import Gf

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
    from pxr import Gf, Usd, UsdGeom

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


def derive_authored_fluid_wrapper_frame(
    stage: Any,
    *,
    parent_path: str,
    visual_mesh_path: str,
) -> CupInteriorFrame:
    """Read the canonical interior actually used by the authored colliders."""
    from dataclasses import replace

    from pxr import Gf, Usd, UsdGeom

    base = derive_cup_interior_frame(
        stage,
        parent_path=parent_path,
        visual_mesh_path=visual_mesh_path,
        calibration_points_path=None,
    )
    wrapper_path = f"{parent_path.rstrip('/')}/FluidSafeWrapperCanonical"
    wrapper = stage.GetPrimAtPath(wrapper_path)
    if not wrapper or not wrapper.IsValid():
        raise ValueError(f"authored_fluid_wrapper_missing:{wrapper_path}")

    def required(name: str) -> Any:
        attribute = wrapper.GetAttribute(name)
        value = attribute.Get() if attribute else None
        if value is None:
            raise ValueError(f"authored_fluid_wrapper_attribute_missing:{name}")
        return value

    if required("labutopia:fluidSafeWrapper") is not True:
        raise ValueError("authored_fluid_wrapper_marker_invalid")
    if str(required("labutopia:wrapperFrame")) != "canonical_to_parent":
        raise ValueError("authored_fluid_wrapper_frame_invalid")

    interior_radius = float(required("labutopia:panelInnerRadius"))
    interior_floor = float(required("labutopia:bottomTopCanonicalZ"))
    rim_height = float(required("labutopia:wallRimCanonicalZ"))
    if (
        not all(math.isfinite(value) for value in (interior_radius, interior_floor, rim_height))
        or interior_radius <= 0.0
        or rim_height <= interior_floor
    ):
        raise ValueError("authored_fluid_wrapper_dimensions_invalid")

    world = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(wrapper)
    origin_world = _as_tuple(world.Transform(Gf.Vec3d(0.0, 0.0, 0.0)))
    x_axis_world = _normalize(world.TransformDir(Gf.Vec3d(1.0, 0.0, 0.0)))
    y_axis_world = _normalize(world.TransformDir(Gf.Vec3d(0.0, 1.0, 0.0)))
    z_axis_world = _normalize(world.TransformDir(Gf.Vec3d(0.0, 0.0, 1.0)))
    if (
        abs(_dot(x_axis_world, y_axis_world)) > 1.0e-6
        or abs(_dot(x_axis_world, z_axis_world)) > 1.0e-6
        or abs(_dot(y_axis_world, z_axis_world)) > 1.0e-6
        or _dot(_cross(x_axis_world, y_axis_world), z_axis_world) < 0.999999
    ):
        raise ValueError("authored_fluid_wrapper_basis_invalid")

    measurements = dict(base._measurements)
    measurements["authored_fluid_wrapper"] = {
        "wrapper_path": wrapper_path,
        "panel_inner_radius": interior_radius,
        "bottom_top_canonical_z": interior_floor,
        "wall_rim_canonical_z": rim_height,
    }
    return replace(
        base,
        origin_world=origin_world,
        x_axis_world=x_axis_world,
        y_axis_world=y_axis_world,
        z_axis_world=z_axis_world,
        outer_radius=max(float(base.outer_radius), interior_radius),
        interior_radius=interior_radius,
        interior_floor=interior_floor,
        rim_height=rim_height,
        calibration_source="authored_fluid_wrapper",
        axis_alignment_dot=_dot(z_axis_world, base.z_axis_world),
        _measurements=measurements,
    )


def _set_wrapper_metadata(prim: Any, name: str, type_name: Any, value: Any) -> None:
    attr = prim.GetAttribute(name)
    if not attr:
        attr = prim.CreateAttribute(name, type_name)
    attr.Set(value)


def _set_wrapper_collision_offsets(prim: Any, *, contact_offset: float, rest_offset: float) -> None:
    """Apply GPU collision offsets, including the schema-free USD fallback."""
    from pxr import Sdf, UsdPhysics

    collision = UsdPhysics.CollisionAPI.Apply(prim)
    collision.CreateCollisionEnabledAttr().Set(True)
    try:
        from pxr import PhysxSchema
    except ImportError:
        PhysxSchema = None

    if PhysxSchema is not None:
        physx_collision = PhysxSchema.PhysxCollisionAPI.Apply(prim)
        physx_collision.CreateContactOffsetAttr().Set(float(contact_offset))
        physx_collision.CreateRestOffsetAttr().Set(float(rest_offset))
        return

    api_schemas = prim.GetMetadata("apiSchemas")
    applied_tokens = list(api_schemas.GetAppliedItems()) if api_schemas else []
    if "PhysxCollisionAPI" not in applied_tokens:
        prim.SetMetadata(
            "apiSchemas", Sdf.TokenListOp.CreateExplicit(applied_tokens + ["PhysxCollisionAPI"])
        )
    _set_wrapper_metadata(
        prim,
        "physxCollision:contactOffset",
        Sdf.ValueTypeNames.Float,
        float(contact_offset),
    )
    _set_wrapper_metadata(
        prim,
        "physxCollision:restOffset",
        Sdf.ValueTypeNames.Float,
        float(rest_offset),
    )


def _set_wrapper_proxy_imageable(prim: Any) -> None:
    from pxr import UsdGeom

    imageable = UsdGeom.Imageable(prim)
    imageable.CreatePurposeAttr().Set(UsdGeom.Tokens.proxy)
    imageable.MakeInvisible()


def _canonical_to_parent_transform(
    stage: Usd.Stage,
    *,
    frame: CupInteriorFrame,
    parent_path: str,
) -> tuple[Gf.Matrix4d, dict[str, tuple[float, float, float]]]:
    from pxr import Gf, Usd, UsdGeom

    parent_prim = stage.GetPrimAtPath(parent_path)
    if not parent_prim.IsValid():
        raise ValueError(f"invalid_parent_path:{parent_path}")

    parent_world = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(parent_prim)
    parent_inverse = parent_world.GetInverse()
    origin_parent = _as_tuple(parent_inverse.Transform(Gf.Vec3d(*frame.origin_world)))
    x_axis_parent = _as_tuple(parent_inverse.TransformDir(Gf.Vec3d(*frame.x_axis_world)))
    y_axis_parent = _as_tuple(parent_inverse.TransformDir(Gf.Vec3d(*frame.y_axis_world)))
    z_axis_parent = _as_tuple(parent_inverse.TransformDir(Gf.Vec3d(*frame.z_axis_world)))

    canonical_to_parent = Gf.Matrix4d(1.0)
    # Gf uses row vectors: rows are local axes, with the origin in the final row.
    canonical_to_parent.SetRow(0, Gf.Vec4d(*x_axis_parent, 0.0))
    canonical_to_parent.SetRow(1, Gf.Vec4d(*y_axis_parent, 0.0))
    canonical_to_parent.SetRow(2, Gf.Vec4d(*z_axis_parent, 0.0))
    canonical_to_parent.SetRow(3, Gf.Vec4d(*origin_parent, 1.0))
    return canonical_to_parent, {
        "origin_parent": origin_parent,
        "x_axis_parent": x_axis_parent,
        "y_axis_parent": y_axis_parent,
        "z_axis_parent": z_axis_parent,
    }


def _authored_bottom_measurements(
    stage: Usd.Stage,
    *,
    bottom_path: str,
    expected_axis_world: Sequence[float],
    expected_support_world: Sequence[float],
) -> dict[str, Any]:
    from pxr import Gf, Usd, UsdGeom

    bottom = stage.GetPrimAtPath(bottom_path)
    if not bottom.IsValid():
        raise ValueError(f"invalid_bottom_path:{bottom_path}")
    bottom_world = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(bottom)
    center = bottom_world.Transform(Gf.Vec3d(0.0, 0.0, 0.0))
    top_center = bottom_world.Transform(Gf.Vec3d(0.0, 0.0, 0.5))
    normal = _normalize(
        tuple(float(top_center[index] - center[index]) for index in range(3))
    )
    expected_axis = _normalize(expected_axis_world)
    alignment_dot = _dot(normal, expected_axis)
    support_error = abs(
        _dot(
            tuple(float(top_center[index] - expected_support_world[index]) for index in range(3)),
            normal,
        )
    )
    corners = [
        bottom_world.Transform(Gf.Vec3d(x, y, z))
        for x in (-0.5, 0.5)
        for y in (-0.5, 0.5)
        for z in (-0.5, 0.5)
    ]
    extents = tuple(
        max(float(corner[index]) for corner in corners)
        - min(float(corner[index]) for corner in corners)
        for index in range(3)
    )
    return {
        "bottom_world_normal": normal,
        "bottom_world_support_point": _as_tuple(top_center),
        "bottom_axis_alignment_dot": alignment_dot,
        "support_plane_error_m": support_error,
        "bottom_world_extent_x": extents[0],
        "bottom_world_extent_y": extents[1],
        "bottom_world_extent_z": extents[2],
    }


def author_canonical_fluid_wrapper(
    stage: Usd.Stage,
    *,
    frame: CupInteriorFrame,
    parent_path: str,
    visual_mesh_path: str,
    panel_count: int = 72,
    panel_ring_count: int = 2,
    wall_thickness: float = 0.026,
    bottom_thickness: float = 0.012,
    bottom_overlap: float = 0.018,
) -> dict[str, Any]:
    """Author a frame-aligned, invisible GPU collider wrapper below the real cup."""
    from pxr import Gf, Sdf, UsdGeom, UsdPhysics
    from tools.labutopia_fluid.run_beaker_collider_smoke import (
        _add_box_collider_prim,
        fluid_safe_wrapper_bottom_xy_extent,
        fluid_safe_wrapper_panel_width,
    )

    panels = _require_int("panel_count", panel_count)
    rings = _require_int("panel_ring_count", panel_ring_count)
    if panels <= 0 or rings <= 0:
        raise ValueError("wrapper_panel_counts_must_be_positive")
    thickness = float(wall_thickness)
    bottom_depth = float(bottom_thickness) + float(bottom_overlap)
    overlap = float(bottom_overlap)
    if thickness <= 0.0 or bottom_depth <= 0.0 or overlap < 0.0:
        raise ValueError("wrapper_dimensions_must_be_positive")

    parent_prim = stage.GetPrimAtPath(parent_path)
    mesh_prim = stage.GetPrimAtPath(visual_mesh_path)
    if not parent_prim.IsValid():
        raise ValueError(f"invalid_parent_path:{parent_path}")
    if not mesh_prim.IsValid():
        raise ValueError(f"invalid_visual_mesh_path:{visual_mesh_path}")

    collision_api = UsdPhysics.CollisionAPI.Apply(mesh_prim)
    collision_api.CreateCollisionEnabledAttr().Set(False)
    _set_wrapper_metadata(
        mesh_prim, "labutopia:nativeMeshCollisionEnabled", Sdf.ValueTypeNames.Bool, False
    )

    wrapper_path = f"{parent_path.rstrip('/')}/FluidSafeWrapperCanonical"
    canonical_to_parent, parent_frame = _canonical_to_parent_transform(
        stage, frame=frame, parent_path=parent_path
    )
    wrapper = UsdGeom.Xform.Define(stage, wrapper_path)
    wrapper_xformable = UsdGeom.Xformable(wrapper.GetPrim())
    wrapper_xformable.MakeMatrixXform().Set(canonical_to_parent)
    wrapper_prim = wrapper.GetPrim()
    _set_wrapper_proxy_imageable(wrapper_prim)
    _set_wrapper_metadata(wrapper_prim, "labutopia:fluidSafeWrapper", Sdf.ValueTypeNames.Bool, True)
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:wrapperFrame", Sdf.ValueTypeNames.String, "canonical_to_parent"
    )
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:wrapperParentPath", Sdf.ValueTypeNames.String, parent_path
    )
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:wrapperColliderMode", Sdf.ValueTypeNames.String, "box_panels"
    )
    for name, value in parent_frame.items():
        _set_wrapper_metadata(
            wrapper_prim, f"labutopia:canonical{''.join(part.title() for part in name.split('_'))}",
            Sdf.ValueTypeNames.Double3, Gf.Vec3d(*value)
        )

    contact_offset = 0.004
    rest_offset = 0.0
    bottom_half = fluid_safe_wrapper_bottom_xy_extent(
        radius=frame.interior_radius,
        wall_thickness=thickness,
        bottom_overlap=overlap,
    )
    bottom_top = frame.interior_floor
    bottom = _add_box_collider_prim(
        stage,
        f"{wrapper_path}/Bottom",
        size=(bottom_half * 2.0, bottom_half * 2.0, bottom_depth),
        position=(0.0, 0.0, bottom_top - bottom_depth / 2.0),
        contact_offset=contact_offset,
        rest_offset=rest_offset,
    )
    _set_wrapper_collision_offsets(
        bottom, contact_offset=contact_offset, rest_offset=rest_offset
    )
    _set_wrapper_proxy_imageable(bottom)
    _set_wrapper_metadata(bottom, "labutopia:fluidSafeWrapper", Sdf.ValueTypeNames.Bool, True)
    _set_wrapper_metadata(bottom, "labutopia:wrapperColliderKind", Sdf.ValueTypeNames.String, "bottom")
    collider_paths = [str(bottom.GetPath())]

    wall_floor = frame.interior_floor - overlap
    wall_height = frame.rim_height - wall_floor
    panel_width = fluid_safe_wrapper_panel_width(
        radius=frame.interior_radius,
        wall_thickness=thickness,
        panel_count=panels,
        panel_arc_overlap_factor=1.08,
    )
    half_pitch = math.pi / panels
    panel_center_radius = frame.interior_radius + thickness / 2.0
    for ring in range(rings):
        ring_phase = half_pitch if ring else 0.0
        for index in range(panels):
            theta = 2.0 * math.pi * index / panels + ring_phase
            panel = _add_box_collider_prim(
                stage,
                f"{wrapper_path}/Wall_r{ring}_{index:02d}",
                size=(panel_width, thickness, wall_height),
                position=(
                    panel_center_radius * math.cos(theta),
                    panel_center_radius * math.sin(theta),
                    wall_floor + wall_height / 2.0,
                ),
                angle_z=theta + math.pi / 2.0,
                contact_offset=contact_offset,
                rest_offset=rest_offset,
            )
            _set_wrapper_collision_offsets(
                panel, contact_offset=contact_offset, rest_offset=rest_offset
            )
            _set_wrapper_proxy_imageable(panel)
            _set_wrapper_metadata(
                panel, "labutopia:fluidSafeWrapper", Sdf.ValueTypeNames.Bool, True
            )
            _set_wrapper_metadata(
                panel, "labutopia:wrapperColliderKind", Sdf.ValueTypeNames.String, "wall"
            )
            collider_paths.append(str(panel.GetPath()))

    measurements = _authored_bottom_measurements(
        stage,
        bottom_path=collider_paths[0],
        expected_axis_world=frame.z_axis_world,
        expected_support_world=frame.canonical_to_world((0.0, 0.0, frame.interior_floor)),
    )
    if measurements["bottom_axis_alignment_dot"] < 0.999:
        raise ValueError("authored_wrapper_bottom_axis_misaligned")
    if measurements["support_plane_error_m"] > 0.001:
        raise ValueError("authored_wrapper_support_plane_misaligned")

    _set_wrapper_metadata(wrapper_prim, "labutopia:colliderCount", Sdf.ValueTypeNames.Int, len(collider_paths))
    _set_wrapper_metadata(wrapper_prim, "labutopia:panelCount", Sdf.ValueTypeNames.Int, panels)
    _set_wrapper_metadata(wrapper_prim, "labutopia:panelRingCount", Sdf.ValueTypeNames.Int, rings)
    _set_wrapper_metadata(wrapper_prim, "labutopia:panelWidth", Sdf.ValueTypeNames.Float, panel_width)
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:panelInnerRadius", Sdf.ValueTypeNames.Float, frame.interior_radius
    )
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:bottomTopCanonicalZ", Sdf.ValueTypeNames.Float, bottom_top
    )
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:wallFloorCanonicalZ", Sdf.ValueTypeNames.Float, wall_floor
    )
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:wallRimCanonicalZ", Sdf.ValueTypeNames.Float, frame.rim_height
    )
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:contactOffset", Sdf.ValueTypeNames.Float, contact_offset
    )
    _set_wrapper_metadata(
        wrapper_prim, "labutopia:restOffset", Sdf.ValueTypeNames.Float, rest_offset
    )

    return {
        "wrapper_path": wrapper_path,
        "wrapper_parent_path": parent_path,
        "visual_mesh_path": visual_mesh_path,
        "collider_paths": collider_paths,
        "collider_count": len(collider_paths),
        "panel_count": panels,
        "panel_ring_count": rings,
        "panel_width": panel_width,
        "panel_inner_radius": frame.interior_radius,
        "wall_thickness": thickness,
        "wall_floor_canonical_z": wall_floor,
        "wall_rim_canonical_z": frame.rim_height,
        "bottom_top_canonical_z": bottom_top,
        "bottom_thickness": float(bottom_thickness),
        "bottom_overlap": overlap,
        "native_mesh_collision_enabled": False,
        "contact_offset": contact_offset,
        "rest_offset": rest_offset,
        "canonical_to_parent": parent_frame,
        **measurements,
    }

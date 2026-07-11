"""Canonical visible-interior frame derivation for the localized real beaker."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Iterable, Sequence

from pxr import Gf, Usd, UsdGeom


_FALLBACK_WALL_CLEARANCE = 0.005
_RADIUS_CLAMP_EPSILON = 0.000001


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

"""Render-only A18-scaled particle proxies for accepted real-beaker traces."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
import math
from numbers import Real
import struct
from typing import Any

from tools.labutopia_fluid.presentation_look_profiles import (
    REF_OMNIGLASS_GLASS_COLOR,
    REF_OMNIGLASS_REFLECTION_COLOR,
)


REFERENCE_CANDIDATE_IDS = (
    "OMNI_REF_FINE",
    "OMNI_REF_RATIO_15",
    "OMNI_REF_RATIO_12",
    "OMNI_REF_SURFACE",
    "OMNI_REF_DISPLAY_FILL",
)
A18_REFERENCE_CONTAINER_INTERIOR_SPAN = 0.30
A18_REFERENCE_POINT_WIDTH = 0.02
A18_REFERENCE_NEAREST_NEIGHBOR_MEDIAN = 0.018516
A18_REFERENCE_POINT_COUNT = 2376
A18_REFERENCE_STAGE_METERS_PER_UNIT = 1.0
A18_REFERENCE_ASSET_RELATIVE_PATH = (
    "inputs/usd/scene/liquid/physics_fidelity_A18_FloatBall.usd"
)
A18_REFERENCE_ASSET_SHA256 = (
    "9cb43f9fbca1148171351b357948a6f17f77ec67e8d96ba108fb7f1407e3af0b"
)
SURFACE_LATITUDE_SEGMENTS = 24
SURFACE_LONGITUDE_SEGMENTS = 64
SURFACE_INTERIOR_CLEARANCE = 0.00005
DISPLAY_FILL_MODEL_VERSION = "a18_display_proxy_rounded_cylinder_v1"
DISPLAY_FILL_PROXY_MODE = "deterministic_a18_display_proxy_rounded_cylinder"
DISPLAY_FILL_RADIAL_SEGMENTS = 96
DISPLAY_FILL_MESH_VOLUME_RELATIVE_TOLERANCE = 5e-6
PRESENTATION_ONLY_VOLUME_DISCLAIMER = (
    "Presentation-only surface; not valid for physical-volume or volume-parity claims."
)
PRESENTATION_ONLY_SHAPE_DISCLAIMER = (
    "Presentation-only proxy; not a physical isosurface and not valid for "
    "free-surface shape or fluid-dynamics claims."
)
DISPLAY_PROXY_VOLUME_DISCLAIMER = (
    "Display-proxy aggregate sphere volume only; not physical liquid volume and "
    "not valid for physical-volume parity claims."
)


def _positive_finite(name: str, value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_must_be_positive_and_finite") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name}_must_be_positive_and_finite")
    return result


def _point_tuple(point: Sequence[float], *, index: int) -> tuple[float, float, float]:
    if (
        not isinstance(point, Sequence)
        or isinstance(point, (str, bytes))
        or len(point) != 3
        or any(
            not isinstance(value, Real) or isinstance(value, bool) for value in point
        )
    ):
        raise ValueError(f"position_schema_invalid:{index}")
    result = tuple(float(value) for value in point)
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"position_nonfinite:{index}")
    return result


def build_reference_candidates(interior_diameter: float) -> dict[str, dict[str, Any]]:
    """Build bead diagnostics plus the reviewed smooth-surface fallback."""
    diameter = _positive_finite("interior_diameter", interior_diameter)
    fine_width = min(max(diameter / 32.0, 0.0015), 0.0020)
    widths = {
        "OMNI_REF_FINE": fine_width,
        "OMNI_REF_RATIO_15": diameter / 15.0,
        "OMNI_REF_RATIO_12": diameter / 12.0,
    }
    a18_reference = {
        "asset_relative_path": A18_REFERENCE_ASSET_RELATIVE_PATH,
        "asset_sha256": A18_REFERENCE_ASSET_SHA256,
        "stage_meters_per_unit": A18_REFERENCE_STAGE_METERS_PER_UNIT,
        "container_interior_span": A18_REFERENCE_CONTAINER_INTERIOR_SPAN,
        "point_width": A18_REFERENCE_POINT_WIDTH,
        "point_count": A18_REFERENCE_POINT_COUNT,
        "width_to_container_ratio": (
            A18_REFERENCE_POINT_WIDTH / A18_REFERENCE_CONTAINER_INTERIOR_SPAN
        ),
        "nearest_neighbor_median": A18_REFERENCE_NEAREST_NEIGHBOR_MEDIAN,
        "glass_color": list(REF_OMNIGLASS_GLASS_COLOR),
        "reflection_color": list(REF_OMNIGLASS_REFLECTION_COLOR),
    }
    candidates = {
        candidate_id: {
            "candidate_id": candidate_id,
            "interior_diameter": diameter,
            "display_width": width,
            "voxel_size": width,
            "width_to_interior_ratio": width / diameter,
            "proxy_mode": "deterministic_canonical_voxel_centroid",
            "presentation_kind": "points",
            "presentation_only": True,
            "presentation_only_volume_disclaimer": (
                PRESENTATION_ONLY_VOLUME_DISCLAIMER
            ),
            "presentation_only_shape_disclaimer": (
                PRESENTATION_ONLY_SHAPE_DISCLAIMER
            ),
            "physical_volume_parity_claim_allowed": False,
            "free_surface_shape_claim_allowed": False,
            "fluid_dynamics_claim_allowed": False,
            "a18_reference": dict(a18_reference),
        }
        for candidate_id, width in widths.items()
    }
    candidates["OMNI_REF_SURFACE"] = {
        "candidate_id": "OMNI_REF_SURFACE",
        "interior_diameter": diameter,
        "display_width": fine_width,
        "voxel_size": None,
        "width_to_interior_ratio": fine_width / diameter,
        "proxy_mode": "deterministic_trace_bounds_uv_ellipsoid",
        "presentation_kind": "surface_mesh",
        "presentation_only": True,
        "display_padding_xy": fine_width / 2.0,
        "display_padding_z": fine_width / 4.0,
        "interior_clearance": SURFACE_INTERIOR_CLEARANCE,
        "latitude_segments": SURFACE_LATITUDE_SEGMENTS,
        "longitude_segments": SURFACE_LONGITUDE_SEGMENTS,
        "a18_reference": dict(a18_reference),
        "presentation_only_volume_disclaimer": (
            PRESENTATION_ONLY_VOLUME_DISCLAIMER
        ),
        "presentation_only_shape_disclaimer": PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        "physical_volume_parity_claim_allowed": False,
        "free_surface_shape_claim_allowed": False,
        "fluid_dynamics_claim_allowed": False,
    }
    display_fill_contract = _display_fill_model_contract(diameter)
    candidates["OMNI_REF_DISPLAY_FILL"] = {
        "candidate_id": "OMNI_REF_DISPLAY_FILL",
        "interior_diameter": diameter,
        "display_width": display_fill_contract["display_width"],
        "voxel_size": None,
        "width_to_interior_ratio": 1.0 / 15.0,
        "proxy_mode": DISPLAY_FILL_PROXY_MODE,
        "presentation_kind": "surface_mesh",
        "presentation_only": True,
        "surface_model_version": DISPLAY_FILL_MODEL_VERSION,
        "surface_model_contract": display_fill_contract,
        "surface_model_contract_sha256": _sha256_json(display_fill_contract),
        "radial_segments": DISPLAY_FILL_RADIAL_SEGMENTS,
        "regular_polygon_area_coefficient": display_fill_contract[
            "regular_polygon_area_coefficient"
        ],
        "wall_clearance": display_fill_contract["wall_clearance"],
        "floor_clearance": display_fill_contract["floor_clearance"],
        "rim_clearance": display_fill_contract["rim_clearance"],
        "edge_rounding": display_fill_contract["edge_rounding"],
        "mesh_volume_relative_tolerance": (
            DISPLAY_FILL_MESH_VOLUME_RELATIVE_TOLERANCE
        ),
        "a18_reference": dict(a18_reference),
        "display_proxy_volume_disclaimer": DISPLAY_PROXY_VOLUME_DISCLAIMER,
        "presentation_only_volume_disclaimer": (
            PRESENTATION_ONLY_VOLUME_DISCLAIMER
        ),
        "presentation_only_shape_disclaimer": PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        "physical_volume_parity_claim_allowed": False,
        "free_surface_shape_claim_allowed": False,
        "fluid_dynamics_claim_allowed": False,
    }
    return candidates


def voxel_cluster_world_positions(
    positions: Iterable[Sequence[float]],
    *,
    frame: Any,
    voxel_size: float,
) -> list[tuple[float, float, float]]:
    """Cluster world points into deterministic canonical-space voxel centroids."""
    size = _positive_finite("voxel_size", voxel_size)
    buckets: dict[tuple[int, int, int], list[tuple[float, float, float]]] = defaultdict(
        list
    )
    for index, point in enumerate(positions):
        world = _point_tuple(point, index=index)
        canonical = _point_tuple(frame.world_to_canonical(world), index=index)
        key = tuple(math.floor(value / size) for value in canonical)
        buckets[key].append(canonical)

    clustered: list[tuple[float, float, float]] = []
    for key in sorted(buckets):
        canonical_points = sorted(buckets[key])
        count = len(canonical_points)
        centroid = tuple(
            math.fsum(point[axis] for point in canonical_points) / count
            for axis in range(3)
        )
        clustered.append(
            _point_tuple(frame.canonical_to_world(centroid), index=len(clustered))
        )
    return clustered


def build_presentation_proxy_frame(
    positions_world: Iterable[Sequence[float]],
    *,
    frame: Any,
    candidate: Mapping[str, Any],
    nominal_physical_particle_width: float | None = None,
) -> dict[str, Any]:
    """Build one candidate frame and its presentation-only count contract."""
    source_positions = tuple(
        _point_tuple(point, index=index) for index, point in enumerate(positions_world)
    )
    if candidate.get("proxy_mode") == DISPLAY_FILL_PROXY_MODE:
        return build_display_fill_surface_frame(
            source_positions,
            frame=frame,
            candidate=candidate,
            nominal_physical_particle_width=nominal_physical_particle_width,
        )
    if candidate.get("presentation_kind") == "surface_mesh":
        return build_surface_envelope_frame(
            source_positions,
            frame=frame,
            candidate=candidate,
            nominal_physical_particle_width=nominal_physical_particle_width,
        )
    display_width = _positive_finite("display_width", candidate.get("display_width"))
    voxel_size = _positive_finite(
        "voxel_size", candidate.get("voxel_size", display_width)
    )
    interior_diameter = _positive_finite(
        "interior_diameter", candidate.get("interior_diameter")
    )
    clustered = voxel_cluster_world_positions(
        source_positions,
        frame=frame,
        voxel_size=voxel_size,
    )
    return {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "positions_world": clustered,
        "proxy_count": len(clustered),
        "source_physical_point_count": len(source_positions),
        "display_width": display_width,
        "voxel_size": voxel_size,
        "width_to_interior_ratio": display_width / interior_diameter,
        "presentation_kind": "points",
        "physics_schema_allowed": False,
        "presentation_only": True,
        "presentation_only_volume_disclaimer": PRESENTATION_ONLY_VOLUME_DISCLAIMER,
        "presentation_only_shape_disclaimer": PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        "physical_volume_parity_claim_allowed": False,
        "free_surface_shape_claim_allowed": False,
        "fluid_dynamics_claim_allowed": False,
    }


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(float(left[index]) * float(right[index]) for index in range(3))


def _cross(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float]:
    return (
        float(left[1]) * float(right[2]) - float(left[2]) * float(right[1]),
        float(left[2]) * float(right[0]) - float(left[0]) * float(right[2]),
        float(left[0]) * float(right[1]) - float(left[1]) * float(right[0]),
    )


def _subtract(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float]:
    return tuple(float(left[index]) - float(right[index]) for index in range(3))


def _normalize(name: str, value: Sequence[float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot(value, value))
    if not math.isfinite(length) or length <= 0.0:
        raise ValueError(f"{name}_invalid")
    return tuple(float(component) / length for component in value)


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _display_fill_model_contract(interior_diameter: float) -> dict[str, Any]:
    diameter = _positive_finite("interior_diameter", interior_diameter)
    display_width = diameter / 15.0
    radial_segments = DISPLAY_FILL_RADIAL_SEGMENTS
    coefficient = 0.5 * radial_segments * math.sin(
        2.0 * math.pi / radial_segments
    )
    return {
        "schema_version": 1,
        "surface_model_version": DISPLAY_FILL_MODEL_VERSION,
        "proxy_mode": DISPLAY_FILL_PROXY_MODE,
        "candidate_id": "OMNI_REF_DISPLAY_FILL",
        "interior_diameter": diameter,
        "display_width_formula": "interior_diameter/15",
        "display_width": display_width,
        "source_count_authority": "per_trace_record_particle_count",
        "display_proxy_aggregate_sphere_volume_formula": (
            "count*4*pi*(display_width/2)^3/3"
        ),
        "radial_segments": radial_segments,
        "regular_polygon_area_coefficient": coefficient,
        "wall_clearance_formula": "display_width/2",
        "wall_clearance": display_width / 2.0,
        "floor_clearance_formula": "display_width/8",
        "floor_clearance": display_width / 8.0,
        "rim_clearance_formula": "display_width/4",
        "rim_clearance": display_width / 4.0,
        "edge_rounding_formula": "display_width/4",
        "edge_rounding": display_width / 4.0,
        "mesh_profile": "bottom_center_four_rings_top_center",
        "mesh_volume_relative_tolerance": (
            DISPLAY_FILL_MESH_VOLUME_RELATIVE_TOLERANCE
        ),
        "source_layout_affects_geometry": False,
        "nominal_physical_particle_width_affects_geometry": False,
        "physical_volume_parity_claim_allowed": False,
        "free_surface_shape_claim_allowed": False,
        "fluid_dynamics_claim_allowed": False,
        "display_proxy_volume_disclaimer": DISPLAY_PROXY_VOLUME_DISCLAIMER,
        "a18_reference": {
            "asset_relative_path": A18_REFERENCE_ASSET_RELATIVE_PATH,
            "asset_sha256": A18_REFERENCE_ASSET_SHA256,
            "stage_meters_per_unit": A18_REFERENCE_STAGE_METERS_PER_UNIT,
            "container_interior_span": A18_REFERENCE_CONTAINER_INTERIOR_SPAN,
            "point_width": A18_REFERENCE_POINT_WIDTH,
            "point_count": A18_REFERENCE_POINT_COUNT,
            "width_to_container_ratio": (
                A18_REFERENCE_POINT_WIDTH
                / A18_REFERENCE_CONTAINER_INTERIOR_SPAN
            ),
        },
    }


def _validate_surface_frame_axes(frame: Any) -> tuple[tuple[float, float, float], ...]:
    axes = tuple(
        _point_tuple(getattr(frame, name), index=index)
        for index, name in enumerate(
            ("x_axis_world", "y_axis_world", "z_axis_world")
        )
    )
    if any(not math.isclose(_dot(axis, axis), 1.0, abs_tol=1e-9) for axis in axes):
        raise ValueError("surface_cup_frame_not_orthonormal")
    if any(
        not math.isclose(_dot(axes[left], axes[right]), 0.0, abs_tol=1e-9)
        for left, right in ((0, 1), (0, 2), (1, 2))
    ):
        raise ValueError("surface_cup_frame_not_orthonormal")
    if _dot(_cross(axes[0], axes[1]), axes[2]) < 0.999999999:
        raise ValueError("surface_cup_frame_not_right_handed")
    return axes


def _surface_topology(
    *, latitude_segments: int, longitude_segments: int
) -> tuple[list[int], list[int]]:
    counts: list[int] = []
    indices: list[int] = []
    first_ring = 1
    south_pole = 1 + (latitude_segments - 1) * longitude_segments
    for longitude in range(longitude_segments):
        next_longitude = (longitude + 1) % longitude_segments
        counts.append(3)
        indices.extend((0, first_ring + longitude, first_ring + next_longitude))
    for latitude in range(latitude_segments - 2):
        upper = first_ring + latitude * longitude_segments
        lower = upper + longitude_segments
        for longitude in range(longitude_segments):
            next_longitude = (longitude + 1) % longitude_segments
            counts.append(4)
            indices.extend(
                (
                    upper + longitude,
                    lower + longitude,
                    lower + next_longitude,
                    upper + next_longitude,
                )
            )
    last_ring = south_pole - longitude_segments
    for longitude in range(longitude_segments):
        next_longitude = (longitude + 1) % longitude_segments
        counts.append(3)
        indices.extend(
            (south_pole, last_ring + next_longitude, last_ring + longitude)
        )
    return counts, indices


def _mesh_topology_summary(
    canonical_points: Sequence[Sequence[float]],
    canonical_normals: Sequence[Sequence[float]],
    counts: Sequence[int],
    indices: Sequence[int],
    *,
    center: Sequence[float],
) -> dict[str, Any]:
    edges: dict[tuple[int, int], int] = defaultdict(int)
    edge_directions: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(
        list
    )
    cursor = 0
    minimum_triangle_area = math.inf
    outward = True
    index_bounds_verified = all(
        isinstance(index, int)
        and not isinstance(index, bool)
        and 0 <= index < len(canonical_points)
        for index in indices
    )
    face_vertex_count_schema_verified = all(count in (3, 4) for count in counts)
    face_index_count_verified = sum(counts) == len(indices)
    if not (
        index_bounds_verified
        and face_vertex_count_schema_verified
        and face_index_count_verified
    ):
        return {
            "edge_count": 0,
            "closed_two_face_edge_incidence": False,
            "opposite_directed_edge_incidence": False,
            "index_bounds_verified": index_bounds_verified,
            "face_vertex_count_schema_verified": (
                face_vertex_count_schema_verified
            ),
            "face_index_count_verified": face_index_count_verified,
            "euler_characteristic": None,
            "outward_winding_verified": False,
            "finite_unit_vertex_normals": False,
            "minimum_triangle_area_m2": None,
            "topology_verified": False,
        }
    for count in counts:
        face = list(indices[cursor : cursor + count])
        cursor += count
        for index, left in enumerate(face):
            right = face[(index + 1) % len(face)]
            edge = tuple(sorted((int(left), int(right))))
            edges[edge] += 1
            edge_directions[edge].append((int(left), int(right)))
        triangles = (
            ((face[0], face[1], face[2]),)
            if count == 3
            else (
                (face[0], face[1], face[2]),
                (face[0], face[2], face[3]),
            )
        )
        for triangle in triangles:
            first, second, third = (canonical_points[index] for index in triangle)
            geometric = _cross(_subtract(second, first), _subtract(third, first))
            area = 0.5 * math.sqrt(_dot(geometric, geometric))
            minimum_triangle_area = min(minimum_triangle_area, area)
            centroid = tuple(
                math.fsum(canonical_points[index][axis] for index in triangle) / 3.0
                for axis in range(3)
            )
            if _dot(geometric, _subtract(centroid, center)) <= 0.0:
                outward = False
    unit_normals = all(
        all(math.isfinite(component) for component in normal)
        and math.isclose(_dot(normal, normal), 1.0, abs_tol=2e-6)
        for normal in canonical_normals
    )
    edge_incidence = bool(edges) and all(value == 2 for value in edges.values())
    opposite_directed_edge_incidence = bool(edge_directions) and all(
        len(directions) == 2
        and directions[0][0] == directions[1][1]
        and directions[0][1] == directions[1][0]
        for directions in edge_directions.values()
    )
    euler = len(canonical_points) - len(edges) + len(counts)
    return {
        "edge_count": len(edges),
        "closed_two_face_edge_incidence": edge_incidence,
        "opposite_directed_edge_incidence": opposite_directed_edge_incidence,
        "index_bounds_verified": index_bounds_verified,
        "face_vertex_count_schema_verified": face_vertex_count_schema_verified,
        "face_index_count_verified": face_index_count_verified,
        "euler_characteristic": euler,
        "outward_winding_verified": outward,
        "finite_unit_vertex_normals": unit_normals,
        "minimum_triangle_area_m2": minimum_triangle_area,
        "topology_verified": (
            edge_incidence
            and opposite_directed_edge_incidence
            and index_bounds_verified
            and face_vertex_count_schema_verified
            and face_index_count_verified
            and euler == 2
            and outward
            and unit_normals
            and minimum_triangle_area > 1e-12
        ),
    }


def _canonical_mesh_sha256(
    points: Sequence[Sequence[float]],
    normals: Sequence[Sequence[float]],
    counts: Sequence[int],
    indices: Sequence[int],
) -> str:
    digest = hashlib.sha256()
    digest.update(b"labutopia-surface-mesh-v1\0")
    for values in (points, normals):
        digest.update(struct.pack("<Q", len(values)))
        for value in values:
            digest.update(struct.pack("<3f", *(_float32(item) for item in value)))
    for values in (counts, indices):
        digest.update(struct.pack("<Q", len(values)))
        for value in values:
            digest.update(struct.pack("<I", int(value)))
    return digest.hexdigest()


def _mesh_signed_volume(
    points: Sequence[Sequence[float]],
    counts: Sequence[int],
    indices: Sequence[int],
) -> float:
    volume = 0.0
    cursor = 0
    for count in counts:
        face = indices[cursor : cursor + count]
        cursor += count
        for offset in range(1, count - 1):
            first = points[face[0]]
            second = points[face[offset]]
            third = points[face[offset + 1]]
            volume += _dot(first, _cross(second, third)) / 6.0
    return volume


def _display_fill_topology(radial_segments: int) -> tuple[list[int], list[int]]:
    counts: list[int] = []
    indices: list[int] = []
    bottom_center = 0
    ring_starts = [1 + ring * radial_segments for ring in range(4)]
    top_center = 1 + 4 * radial_segments

    for radial in range(radial_segments):
        following = (radial + 1) % radial_segments
        counts.append(3)
        indices.extend(
            (
                bottom_center,
                ring_starts[0] + following,
                ring_starts[0] + radial,
            )
        )
    for ring in range(3):
        lower = ring_starts[ring]
        upper = ring_starts[ring + 1]
        for radial in range(radial_segments):
            following = (radial + 1) % radial_segments
            counts.append(4)
            indices.extend(
                (
                    lower + radial,
                    lower + following,
                    upper + following,
                    upper + radial,
                )
            )
    for radial in range(radial_segments):
        following = (radial + 1) % radial_segments
        counts.append(3)
        indices.extend(
            (
                top_center,
                ring_starts[3] + radial,
                ring_starts[3] + following,
            )
        )
    return counts, indices


def _display_fill_canonical_mesh(
    *,
    low_z: float,
    high_z: float,
    fill_radius: float,
    cap_radius: float,
    edge_rounding: float,
    radial_segments: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    points: list[tuple[float, float, float]] = [
        (0.0, 0.0, _float32(low_z))
    ]
    normals: list[tuple[float, float, float]] = [(0.0, 0.0, -1.0)]
    ring_contracts = (
        (cap_radius, low_z, "bottom_cap"),
        (fill_radius, low_z + edge_rounding, "side"),
        (fill_radius, high_z - edge_rounding, "side"),
        (cap_radius, high_z, "top_cap"),
    )
    for radius, z_value, normal_mode in ring_contracts:
        for radial in range(radial_segments):
            angle = 2.0 * math.pi * radial / radial_segments
            cos_angle = math.cos(angle)
            sin_angle = math.sin(angle)
            points.append(
                (
                    _float32(radius * cos_angle),
                    _float32(radius * sin_angle),
                    _float32(z_value),
                )
            )
            if normal_mode == "bottom_cap":
                normal = (0.0, 0.0, -1.0)
            elif normal_mode == "top_cap":
                normal = (0.0, 0.0, 1.0)
            else:
                normal = tuple(
                    _float32(value)
                    for value in _normalize(
                        "display_fill_radial_normal",
                        (cos_angle, sin_angle, 0.0),
                    )
                )
            normals.append(normal)
    points.append((0.0, 0.0, _float32(high_z)))
    normals.append((0.0, 0.0, 1.0))
    return points, normals


def _display_fill_analytic_normals_verified(
    normals: Sequence[Sequence[float]], *, radial_segments: int
) -> bool:
    if len(normals) != 2 + 4 * radial_segments:
        return False
    if tuple(normals[0]) != (0.0, 0.0, -1.0):
        return False
    if tuple(normals[-1]) != (0.0, 0.0, 1.0):
        return False
    ring_starts = [1 + ring * radial_segments for ring in range(4)]
    for radial in range(radial_segments):
        if tuple(normals[ring_starts[0] + radial]) != (0.0, 0.0, -1.0):
            return False
        if tuple(normals[ring_starts[3] + radial]) != (0.0, 0.0, 1.0):
            return False
        for ring in (1, 2):
            normal = normals[ring_starts[ring] + radial]
            expected_angle = 2.0 * math.pi * radial / radial_segments
            if (
                not math.isclose(normal[0], math.cos(expected_angle), abs_tol=2e-6)
                or not math.isclose(
                    normal[1], math.sin(expected_angle), abs_tol=2e-6
                )
                or not math.isclose(normal[2], 0.0, abs_tol=2e-6)
            ):
                return False
    return True


def build_display_fill_surface_frame(
    positions_world: Iterable[Sequence[float]],
    *,
    frame: Any,
    candidate: Mapping[str, Any],
    nominal_physical_particle_width: float | None,
) -> dict[str, Any]:
    """Build a count-derived A18 display proxy without physical-volume claims."""
    source_positions = tuple(
        _point_tuple(point, index=index) for index, point in enumerate(positions_world)
    )
    axes = _validate_surface_frame_axes(frame)
    canonical = tuple(
        _point_tuple(frame.world_to_canonical(point), index=index)
        for index, point in enumerate(source_positions)
    )
    unique = tuple(sorted(set(canonical)))

    interior_radius = _positive_finite(
        "display_fill_interior_radius", frame.interior_radius
    )
    floor = float(frame.interior_floor)
    rim = float(frame.rim_height)
    if not math.isfinite(floor) or not math.isfinite(rim) or rim <= floor:
        raise ValueError("display_fill_cup_axial_interval_invalid")
    for point in canonical:
        if (
            point[2] < floor
            or point[2] >= rim
            or math.hypot(point[0], point[1]) > interior_radius
        ):
            raise ValueError("display_fill_source_point_outside_cup")

    candidate_diameter = _positive_finite(
        "display_fill_candidate_interior_diameter",
        candidate.get("interior_diameter"),
    )
    frame_diameter = 2.0 * interior_radius
    if not math.isclose(candidate_diameter, frame_diameter, abs_tol=1e-12):
        raise ValueError("display_fill_candidate_frame_diameter_mismatch")
    expected_model_contract = _display_fill_model_contract(candidate_diameter)
    expected_model_hash = _sha256_json(expected_model_contract)
    if (
        candidate.get("candidate_id") != "OMNI_REF_DISPLAY_FILL"
        or candidate.get("surface_model_version") != DISPLAY_FILL_MODEL_VERSION
        or candidate.get("proxy_mode") != DISPLAY_FILL_PROXY_MODE
        or candidate.get("surface_model_contract") != expected_model_contract
        or candidate.get("surface_model_contract_sha256") != expected_model_hash
    ):
        raise ValueError("display_fill_model_contract_mismatch")

    source_count = len(source_positions)
    display_width = expected_model_contract["display_width"]
    fill_radius = interior_radius - expected_model_contract["wall_clearance"]
    edge_rounding = expected_model_contract["edge_rounding"]
    cap_radius = fill_radius - edge_rounding
    if fill_radius <= 0.0 or cap_radius <= 0.0:
        raise ValueError("display_fill_radial_profile_invalid")
    coefficient = expected_model_contract["regular_polygon_area_coefficient"]
    display_proxy_volume = (
        source_count * 4.0 * math.pi * (display_width / 2.0) ** 3 / 3.0
    )
    edge_volume = (
        coefficient
        * edge_rounding
        * (
            fill_radius**2
            + fill_radius * cap_radius
            + cap_radius**2
        )
        / 3.0
    )
    if display_proxy_volume <= 2.0 * edge_volume:
        raise ValueError("display_fill_proxy_volume_underflow")
    height = 2.0 * edge_rounding + (
        display_proxy_volume - 2.0 * edge_volume
    ) / (coefficient * fill_radius**2)
    low_z = floor + expected_model_contract["floor_clearance"]
    high_z = low_z + height
    maximum_z = rim - expected_model_contract["rim_clearance"]
    if high_z > maximum_z:
        raise ValueError("display_fill_overflow")

    radial_segments = expected_model_contract["radial_segments"]
    face_counts, face_indices = _display_fill_topology(radial_segments)
    canonical_points: list[tuple[float, float, float]]
    canonical_normals: list[tuple[float, float, float]]
    mesh_volume = 0.0
    relative_error = math.inf
    for _attempt in range(4):
        canonical_points, canonical_normals = _display_fill_canonical_mesh(
            low_z=low_z,
            high_z=high_z,
            fill_radius=fill_radius,
            cap_radius=cap_radius,
            edge_rounding=edge_rounding,
            radial_segments=radial_segments,
        )
        mesh_volume = _mesh_signed_volume(
            canonical_points, face_counts, face_indices
        )
        relative_error = abs(mesh_volume - display_proxy_volume) / (
            display_proxy_volume
        )
        if relative_error <= DISPLAY_FILL_MESH_VOLUME_RELATIVE_TOLERANCE:
            break
        high_z += (display_proxy_volume - mesh_volume) / (
            coefficient * fill_radius**2
        )
        height = high_z - low_z
        if high_z > maximum_z:
            raise ValueError("display_fill_overflow_after_float32_correction")
    if relative_error > DISPLAY_FILL_MESH_VOLUME_RELATIVE_TOLERANCE:
        raise ValueError("display_fill_mesh_volume_verification_failed")

    center = (0.0, 0.0, (low_z + high_z) / 2.0)
    topology = _mesh_topology_summary(
        canonical_points,
        canonical_normals,
        face_counts,
        face_indices,
        center=center,
    )
    if topology["topology_verified"] is not True:
        raise ValueError("display_fill_topology_validation_failed")
    analytic_normals_verified = _display_fill_analytic_normals_verified(
        canonical_normals,
        radial_segments=radial_segments,
    )
    if not analytic_normals_verified:
        raise ValueError("display_fill_analytic_normal_contract_failed")

    maximum_mesh_radius = max(
        math.hypot(point[0], point[1]) for point in canonical_points
    )
    minimum_mesh_z = min(point[2] for point in canonical_points)
    maximum_mesh_z = max(point[2] for point in canonical_points)
    all_vertices_inside = (
        maximum_mesh_radius
        <= interior_radius - expected_model_contract["wall_clearance"] + 2e-7
        and minimum_mesh_z
        >= floor + expected_model_contract["floor_clearance"] - 2e-7
        and maximum_mesh_z
        <= rim - expected_model_contract["rim_clearance"] + 2e-7
    )
    if not all_vertices_inside:
        raise ValueError("display_fill_mesh_vertex_outside_cup")

    positions_world_result = [
        tuple(_float32(value) for value in frame.canonical_to_world(point))
        for point in canonical_points
    ]
    normals_world = [
        tuple(
            _float32(value)
            for value in _normalize(
                "display_fill_world_normal",
                tuple(
                    math.fsum(
                        axes[canonical_axis][world_axis]
                        * normal[canonical_axis]
                        for canonical_axis in range(3)
                    )
                    for world_axis in range(3)
                ),
            )
        )
        for normal in canonical_normals
    ]
    nominal_width = _positive_finite(
        "nominal_physical_particle_width", nominal_physical_particle_width
    )
    nominal_particle_volume = (
        source_count * 4.0 * math.pi * (nominal_width / 2.0) ** 3 / 3.0
    )
    source_hash = _sha256_json(unique)
    minimum = [min(point[axis] for point in canonical) for axis in range(3)]
    maximum = [max(point[axis] for point in canonical) for axis in range(3)]
    raw_spans = [maximum[axis] - minimum[axis] for axis in range(3)]
    point_aabb_volume = math.prod(raw_spans)
    mesh_hash = _canonical_mesh_sha256(
        canonical_points,
        canonical_normals,
        face_counts,
        face_indices,
    )
    containment = {
        "authority": "calibrated_canonical_cylinder",
        "source_boundary_semantics": (
            "z>=floor,radius<=interior_radius,z<rim"
        ),
        "all_source_points_inside": True,
        "all_mesh_vertices_inside": True,
        "interior_radius": interior_radius,
        "interior_floor": floor,
        "rim_height": rim,
        "wall_clearance": expected_model_contract["wall_clearance"],
        "floor_clearance": expected_model_contract["floor_clearance"],
        "rim_clearance": expected_model_contract["rim_clearance"],
        "maximum_mesh_radius": maximum_mesh_radius,
        "minimum_mesh_z": minimum_mesh_z,
        "maximum_mesh_z": maximum_mesh_z,
    }
    surface_geometry_contract_sha256 = _sha256_json(
        {
            "candidate_id": candidate.get("candidate_id"),
            "surface_model_contract_sha256": expected_model_hash,
            "source_physical_point_count": source_count,
            "source_unique_canonical_position_set_sha256": source_hash,
            "canonical_mesh_sha256": mesh_hash,
            "frame": {
                "origin_world": list(frame.origin_world),
                "x_axis_world": list(frame.x_axis_world),
                "y_axis_world": list(frame.y_axis_world),
                "z_axis_world": list(frame.z_axis_world),
            },
            "containment": containment,
            "display_proxy_aggregate_sphere_volume_m3": display_proxy_volume,
            "mesh_enclosed_volume_m3": mesh_volume,
            "display_proxy_volume_disclaimer": DISPLAY_PROXY_VOLUME_DISCLAIMER,
            "presentation_only_volume_disclaimer": (
                PRESENTATION_ONLY_VOLUME_DISCLAIMER
            ),
            "presentation_only_shape_disclaimer": (
                PRESENTATION_ONLY_SHAPE_DISCLAIMER
            ),
        }
    )
    return {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "presentation_kind": "surface_mesh",
        "proxy_mode": DISPLAY_FILL_PROXY_MODE,
        "surface_model_version": DISPLAY_FILL_MODEL_VERSION,
        "surface_model_contract": expected_model_contract,
        "surface_model_contract_sha256": expected_model_hash,
        "source_physical_point_count": source_count,
        "source_unique_canonical_position_set_sha256": source_hash,
        "source_positions_hash_semantics": (
            "sorted_unique_canonical_position_set_order_and_duplicates_not_preserved"
        ),
        "source_count_authority": "per_trace_record_particle_count",
        "source_layout_affects_geometry": False,
        "nominal_physical_particle_width_affects_geometry": False,
        "proxy_count": len(canonical_points),
        "vertex_count": len(canonical_points),
        "face_count": len(face_counts),
        "positions_canonical": canonical_points,
        "positions_world": positions_world_result,
        "normals_canonical": canonical_normals,
        "normals_world": normals_world,
        "face_vertex_counts": face_counts,
        "face_vertex_indices": face_indices,
        "canonical_center": list(center),
        "canonical_bounding_half_extents": [
            fill_radius,
            fill_radius,
            (high_z - low_z) / 2.0,
        ],
        "raw_canonical_bounds": {"minimum": minimum, "maximum": maximum},
        "display_width": display_width,
        "width_to_interior_ratio": display_width / candidate_diameter,
        "voxel_size": None,
        "display_fill_radius_m": fill_radius,
        "display_fill_cap_radius_m": cap_radius,
        "display_fill_height_m": high_z - low_z,
        "display_fill_low_z_m": low_z,
        "display_fill_high_z_m": high_z,
        "edge_rounding_m": edge_rounding,
        "radial_segments": radial_segments,
        "regular_polygon_area_coefficient": coefficient,
        "canonical_mesh_sha256": mesh_hash,
        "topology": topology,
        "analytic_normal_contract_verified": True,
        "containment": containment,
        "display_proxy_aggregate_sphere_volume_m3": display_proxy_volume,
        "mesh_enclosed_volume_m3": mesh_volume,
        "mesh_to_display_proxy_volume_relative_error": relative_error,
        "point_aabb_volume_m3": point_aabb_volume,
        "nominal_disjoint_particle_volume_m3": nominal_particle_volume,
        "display_to_nominal_particle_volume_ratio": (
            display_proxy_volume / nominal_particle_volume
        ),
        "display_proxy_volume_disclaimer": DISPLAY_PROXY_VOLUME_DISCLAIMER,
        "presentation_only_volume_disclaimer": PRESENTATION_ONLY_VOLUME_DISCLAIMER,
        "presentation_only_shape_disclaimer": PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        "physical_volume_parity_claim_allowed": False,
        "free_surface_shape_claim_allowed": False,
        "fluid_dynamics_claim_allowed": False,
        "physics_schema_allowed": False,
        "presentation_only": True,
        "surface_geometry_contract_sha256": surface_geometry_contract_sha256,
        "surface_frame_sha256": surface_geometry_contract_sha256,
    }


def build_surface_envelope_frame(
    positions_world: Iterable[Sequence[float]],
    *,
    frame: Any,
    candidate: Mapping[str, Any],
    nominal_physical_particle_width: float | None,
) -> dict[str, Any]:
    """Build a deterministic, presentation-only trace-bounds ellipsoid mesh."""
    source_positions = tuple(
        _point_tuple(point, index=index) for index, point in enumerate(positions_world)
    )
    if len(source_positions) < 4:
        raise ValueError("surface_source_point_count_below_four")
    axes = _validate_surface_frame_axes(frame)
    canonical = tuple(
        _point_tuple(frame.world_to_canonical(point), index=index)
        for index, point in enumerate(source_positions)
    )
    unique = tuple(sorted(set(canonical)))
    if len(unique) < 4:
        raise ValueError("surface_unique_point_count_below_four")

    interior_radius = _positive_finite("surface_interior_radius", frame.interior_radius)
    floor = float(frame.interior_floor)
    rim = float(frame.rim_height)
    if not math.isfinite(floor) or not math.isfinite(rim) or rim <= floor:
        raise ValueError("surface_cup_axial_interval_invalid")
    containment_tolerance = 1e-9
    for point in canonical:
        if (
            point[2] < floor - containment_tolerance
            or point[2] > rim + containment_tolerance
            or math.hypot(point[0], point[1])
            > interior_radius + containment_tolerance
        ):
            raise ValueError("surface_source_point_outside_cup")

    mean_x = math.fsum(point[0] for point in canonical) / len(canonical)
    mean_y = math.fsum(point[1] for point in canonical) / len(canonical)
    variance_x = math.fsum((point[0] - mean_x) ** 2 for point in canonical) / len(
        canonical
    )
    variance_y = math.fsum((point[1] - mean_y) ** 2 for point in canonical) / len(
        canonical
    )
    covariance = math.fsum(
        (point[0] - mean_x) * (point[1] - mean_y) for point in canonical
    ) / len(canonical)
    determinant = variance_x * variance_y - covariance * covariance
    if not math.isfinite(determinant) or determinant <= 1e-24:
        raise ValueError("surface_footprint_degenerate")

    display_width = _positive_finite("display_width", candidate.get("display_width"))
    padding_xy = _positive_finite(
        "surface_display_padding_xy", candidate.get("display_padding_xy")
    )
    padding_z = _positive_finite(
        "surface_display_padding_z", candidate.get("display_padding_z")
    )
    clearance = _positive_finite(
        "surface_interior_clearance", candidate.get("interior_clearance")
    )
    latitude_segments = int(candidate.get("latitude_segments", 0))
    longitude_segments = int(candidate.get("longitude_segments", 0))
    if latitude_segments != SURFACE_LATITUDE_SEGMENTS or longitude_segments != SURFACE_LONGITUDE_SEGMENTS:
        raise ValueError("surface_topology_parameters_not_canonical")

    minimum = [min(point[axis] for point in canonical) for axis in range(3)]
    maximum = [max(point[axis] for point in canonical) for axis in range(3)]
    raw_spans = [maximum[axis] - minimum[axis] for axis in range(3)]
    if raw_spans[0] <= 1e-9 or raw_spans[1] <= 1e-9:
        raise ValueError("surface_footprint_degenerate")
    desired_low = [minimum[0] - padding_xy, minimum[1] - padding_xy, minimum[2] - padding_z]
    desired_high = [maximum[0] + padding_xy, maximum[1] + padding_xy, maximum[2] + padding_z]
    center = [
        (desired_low[axis] + desired_high[axis]) / 2.0 for axis in range(3)
    ]
    semi_axes = [
        (desired_high[axis] - desired_low[axis]) / 2.0 for axis in range(3)
    ]

    radial_limit = interior_radius - clearance
    maximum_axis = max(semi_axes[0], semi_axes[1])
    available_axis = radial_limit - math.hypot(center[0], center[1])
    if available_axis <= 0.0:
        raise ValueError("surface_radial_fit_impossible")
    radial_scale = min(1.0, available_axis / maximum_axis)
    original_radial_axes = tuple(semi_axes[:2])
    semi_axes[0] *= radial_scale
    semi_axes[1] *= radial_scale
    radial_correction = max(
        original_radial_axes[0] - semi_axes[0],
        original_radial_axes[1] - semi_axes[1],
    )
    if radial_correction > padding_xy + containment_tolerance:
        raise ValueError("surface_radial_correction_exceeds_display_padding")

    low_z = max(desired_low[2], floor + clearance)
    high_z = min(desired_high[2], rim - clearance)
    axial_correction = max(low_z - desired_low[2], desired_high[2] - high_z)
    if axial_correction > padding_z + containment_tolerance or high_z <= low_z:
        raise ValueError("surface_axial_fit_impossible")
    center[2] = (low_z + high_z) / 2.0
    semi_axes[2] = (high_z - low_z) / 2.0
    if any(not math.isfinite(value) or value <= 0.0 for value in semi_axes):
        raise ValueError("surface_semi_axis_invalid")

    canonical_points: list[tuple[float, float, float]] = []
    canonical_normals: list[tuple[float, float, float]] = []
    canonical_points.append((_float32(center[0]), _float32(center[1]), _float32(center[2] + semi_axes[2])))
    canonical_normals.append((0.0, 0.0, 1.0))
    for latitude in range(1, latitude_segments):
        theta = math.pi * latitude / latitude_segments
        sin_theta = math.sin(theta)
        cos_theta = math.cos(theta)
        for longitude in range(longitude_segments):
            phi = 2.0 * math.pi * longitude / longitude_segments
            cos_phi = math.cos(phi)
            sin_phi = math.sin(phi)
            direction = (sin_theta * cos_phi, sin_theta * sin_phi, cos_theta)
            canonical_points.append(
                tuple(
                    _float32(center[axis] + semi_axes[axis] * direction[axis])
                    for axis in range(3)
                )
            )
            canonical_normals.append(
                tuple(
                    _float32(value)
                    for value in _normalize(
                        "surface_vertex_normal",
                        tuple(
                            direction[axis] / semi_axes[axis]
                            for axis in range(3)
                        ),
                    )
                )
            )
    canonical_points.append((_float32(center[0]), _float32(center[1]), _float32(center[2] - semi_axes[2])))
    canonical_normals.append((0.0, 0.0, -1.0))
    face_counts, face_indices = _surface_topology(
        latitude_segments=latitude_segments,
        longitude_segments=longitude_segments,
    )
    topology = _mesh_topology_summary(
        canonical_points,
        canonical_normals,
        face_counts,
        face_indices,
        center=center,
    )
    if topology["topology_verified"] is not True:
        raise ValueError("surface_topology_validation_failed")

    maximum_mesh_radius = max(math.hypot(point[0], point[1]) for point in canonical_points)
    minimum_mesh_z = min(point[2] for point in canonical_points)
    maximum_mesh_z = max(point[2] for point in canonical_points)
    all_vertices_inside = (
        maximum_mesh_radius <= radial_limit + 2e-7
        and minimum_mesh_z >= floor + clearance - 2e-7
        and maximum_mesh_z <= rim - clearance + 2e-7
    )
    if not all_vertices_inside:
        raise ValueError("surface_mesh_vertex_outside_cup")

    positions_world_result = [
        tuple(_float32(value) for value in frame.canonical_to_world(point))
        for point in canonical_points
    ]
    normals_world = [
        tuple(
            _float32(value)
            for value in _normalize(
                "surface_world_normal",
                tuple(
                    math.fsum(
                        axes[canonical_axis][world_axis]
                        * normal[canonical_axis]
                        for canonical_axis in range(3)
                    )
                    for world_axis in range(3)
                ),
            )
        )
        for normal in canonical_normals
    ]
    nominal_width = _positive_finite(
        "nominal_physical_particle_width", nominal_physical_particle_width
    )
    display_volume = 4.0 * math.pi * math.prod(semi_axes) / 3.0
    nominal_particle_volume = (
        len(source_positions) * 4.0 * math.pi * (nominal_width / 2.0) ** 3 / 3.0
    )
    point_aabb_volume = math.prod(raw_spans)
    mesh_hash = _canonical_mesh_sha256(
        canonical_points,
        canonical_normals,
        face_counts,
        face_indices,
    )
    source_hash = _sha256_json(unique)
    containment = {
        "authority": "calibrated_canonical_cylinder",
        "all_source_points_inside": True,
        "all_mesh_vertices_inside": True,
        "interior_radius": interior_radius,
        "interior_floor": floor,
        "rim_height": rim,
        "interior_clearance": clearance,
        "maximum_mesh_radius": maximum_mesh_radius,
        "minimum_mesh_z": minimum_mesh_z,
        "maximum_mesh_z": maximum_mesh_z,
    }
    surface_geometry_contract_sha256 = _sha256_json(
        {
            "candidate_id": candidate.get("candidate_id"),
            "source_unique_canonical_position_set_sha256": source_hash,
            "canonical_mesh_sha256": mesh_hash,
            "canonical_center": center,
            "canonical_semi_axes": semi_axes,
            "frame": {
                "origin_world": list(frame.origin_world),
                "x_axis_world": list(frame.x_axis_world),
                "y_axis_world": list(frame.y_axis_world),
                "z_axis_world": list(frame.z_axis_world),
            },
            "containment": containment,
            "display_volume_m3": display_volume,
            "nominal_disjoint_particle_volume_m3": nominal_particle_volume,
            "presentation_only_volume_disclaimer": (
                PRESENTATION_ONLY_VOLUME_DISCLAIMER
            ),
            "presentation_only_shape_disclaimer": (
                PRESENTATION_ONLY_SHAPE_DISCLAIMER
            ),
        }
    )
    return {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "presentation_kind": "surface_mesh",
        "proxy_mode": "deterministic_trace_bounds_uv_ellipsoid",
        "source_physical_point_count": len(source_positions),
        "source_unique_canonical_position_set_sha256": source_hash,
        "source_positions_hash_semantics": (
            "sorted_unique_canonical_position_set_order_and_duplicates_not_preserved"
        ),
        "proxy_count": len(canonical_points),
        "vertex_count": len(canonical_points),
        "face_count": len(face_counts),
        "positions_world": positions_world_result,
        "normals_world": normals_world,
        "face_vertex_counts": face_counts,
        "face_vertex_indices": face_indices,
        "canonical_center": center,
        "canonical_semi_axes": semi_axes,
        "raw_canonical_bounds": {"minimum": minimum, "maximum": maximum},
        "display_width": display_width,
        "display_padding_xy": padding_xy,
        "display_padding_z": padding_z,
        "width_to_interior_ratio": display_width
        / _positive_finite("interior_diameter", candidate.get("interior_diameter")),
        "voxel_size": None,
        "radial_scale": radial_scale,
        "radial_correction_m": radial_correction,
        "axial_correction_m": axial_correction,
        "canonical_mesh_sha256": mesh_hash,
        "topology": topology,
        "containment": containment,
        "display_volume_m3": display_volume,
        "point_aabb_volume_m3": point_aabb_volume,
        "nominal_disjoint_particle_volume_m3": nominal_particle_volume,
        "display_to_nominal_particle_volume_ratio": display_volume
        / nominal_particle_volume,
        "presentation_only_volume_disclaimer": PRESENTATION_ONLY_VOLUME_DISCLAIMER,
        "presentation_only_shape_disclaimer": PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        "physical_volume_parity_claim_allowed": False,
        "free_surface_shape_claim_allowed": False,
        "fluid_dynamics_claim_allowed": False,
        "physics_schema_allowed": False,
        "presentation_only": True,
        "surface_geometry_contract_sha256": surface_geometry_contract_sha256,
        "surface_frame_sha256": surface_geometry_contract_sha256,
    }


def author_presentation_points(
    stage: Any,
    *,
    path: str,
    positions: Iterable[Sequence[float]],
    display_width: float,
    material_path: str | None,
) -> Any:
    """Author a plain ``UsdGeom.Points`` prim with no simulation API surface."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    width = _positive_finite("display_width", display_width)
    values = [
        Gf.Vec3f(*_point_tuple(point, index=index))
        for index, point in enumerate(positions)
    ]
    prim_path = Sdf.Path(path)
    if not prim_path.IsAbsolutePath() or prim_path.IsPropertyPath():
        raise ValueError("presentation_points_path_must_be_absolute_prim_path")

    existing = stage.GetPrimAtPath(prim_path)
    if existing:
        if existing.GetTypeName() not in ("", "Points"):
            raise ValueError(
                f"presentation_points_path_has_wrong_type:{existing.GetTypeName()}"
            )
        if any("physx" in token.lower() for token in existing.GetAppliedSchemas()):
            raise ValueError("presentation_points_path_has_physx_schema")
        if any(
            relationship.GetName().lower().startswith("physx")
            for relationship in existing.GetRelationships()
        ):
            raise ValueError("presentation_points_path_has_physx_relationship")

    points = UsdGeom.Points.Define(stage, prim_path)
    points.CreatePointsAttr(values)
    points.CreateWidthsAttr([width])
    points.SetWidthsInterpolation(UsdGeom.Tokens.constant)
    points.GetVelocitiesAttr().Clear()
    prim = points.GetPrim()
    prim.CreateAttribute(
        "labutopia:presentationOnly", Sdf.ValueTypeNames.Bool, custom=True
    ).Set(True)
    prim.CreateAttribute(
        "labutopia:physicsSchemaAllowed", Sdf.ValueTypeNames.Bool, custom=True
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:physicalVolumeParityClaimAllowed",
        Sdf.ValueTypeNames.Bool,
        custom=True,
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:freeSurfaceShapeClaimAllowed",
        Sdf.ValueTypeNames.Bool,
        custom=True,
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:fluidDynamicsClaimAllowed",
        Sdf.ValueTypeNames.Bool,
        custom=True,
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:presentationOnlyVolumeDisclaimer",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(PRESENTATION_ONLY_VOLUME_DISCLAIMER)
    prim.CreateAttribute(
        "labutopia:presentationOnlyShapeDisclaimer",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(PRESENTATION_ONLY_SHAPE_DISCLAIMER)

    if material_path is not None:
        material_prim = stage.GetPrimAtPath(material_path)
        material = UsdShade.Material(material_prim)
        if not material_prim or not material:
            raise ValueError(f"presentation_material_missing:{material_path}")
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
    return prim


def author_presentation_surface(
    stage: Any,
    *,
    path: str,
    surface_frame: Mapping[str, Any],
    material_path: str | None,
) -> Any:
    """Author a render-only deterministic surface mesh with no PhysX API."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    if surface_frame.get("presentation_kind") != "surface_mesh":
        raise ValueError("presentation_surface_frame_kind_invalid")
    if surface_frame.get("physics_schema_allowed") is not False:
        raise ValueError("presentation_surface_physics_schema_must_be_forbidden")
    prim_path = Sdf.Path(path)
    if not prim_path.IsAbsolutePath() or prim_path.IsPropertyPath():
        raise ValueError("presentation_surface_path_must_be_absolute_prim_path")
    existing = stage.GetPrimAtPath(prim_path)
    if existing:
        if existing.GetTypeName() not in ("", "Mesh"):
            raise ValueError(
                f"presentation_surface_path_has_wrong_type:{existing.GetTypeName()}"
            )
        if any("physx" in token.lower() for token in existing.GetAppliedSchemas()):
            raise ValueError("presentation_surface_path_has_physx_schema")
        if any(
            relationship.GetName().lower().startswith("physx")
            for relationship in existing.GetRelationships()
        ):
            raise ValueError("presentation_surface_path_has_physx_relationship")

    mesh = UsdGeom.Mesh.Define(stage, prim_path)
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(*_point_tuple(point, index=index))
            for index, point in enumerate(surface_frame["positions_world"])
        ]
    )
    mesh.CreateNormalsAttr(
        [
            Gf.Vec3f(*_point_tuple(normal, index=index))
            for index, normal in enumerate(surface_frame["normals_world"])
        ]
    )
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateFaceVertexCountsAttr(
        [int(value) for value in surface_frame["face_vertex_counts"]]
    )
    mesh.CreateFaceVertexIndicesAttr(
        [int(value) for value in surface_frame["face_vertex_indices"]]
    )
    mesh.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(True)
    prim = mesh.GetPrim()
    prim.CreateAttribute(
        "labutopia:presentationOnly", Sdf.ValueTypeNames.Bool, custom=True
    ).Set(True)
    prim.CreateAttribute(
        "labutopia:physicsSchemaAllowed", Sdf.ValueTypeNames.Bool, custom=True
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:physicalVolumeParityClaimAllowed",
        Sdf.ValueTypeNames.Bool,
        custom=True,
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:freeSurfaceShapeClaimAllowed",
        Sdf.ValueTypeNames.Bool,
        custom=True,
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:fluidDynamicsClaimAllowed",
        Sdf.ValueTypeNames.Bool,
        custom=True,
    ).Set(False)
    prim.CreateAttribute(
        "labutopia:canonicalMeshSha256",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(str(surface_frame["canonical_mesh_sha256"]))
    surface_model_version = surface_frame.get("surface_model_version")
    if surface_model_version is not None:
        required = {
            "surface_model_contract_sha256": Sdf.ValueTypeNames.String,
            "display_proxy_aggregate_sphere_volume_m3": Sdf.ValueTypeNames.Double,
            "mesh_enclosed_volume_m3": Sdf.ValueTypeNames.Double,
            "display_fill_height_m": Sdf.ValueTypeNames.Double,
            "display_proxy_volume_disclaimer": Sdf.ValueTypeNames.String,
        }
        missing = sorted(key for key in required if key not in surface_frame)
        if missing:
            raise ValueError(
                "presentation_surface_model_contract_missing:" + ",".join(missing)
            )
        prim.CreateAttribute(
            "labutopia:surfaceModelVersion",
            Sdf.ValueTypeNames.String,
            custom=True,
        ).Set(str(surface_model_version))
        for key, value_type in required.items():
            attribute_name = {
                "surface_model_contract_sha256": "surfaceModelContractSha256",
                "display_proxy_aggregate_sphere_volume_m3": (
                    "displayProxyAggregateSphereVolumeM3"
                ),
                "mesh_enclosed_volume_m3": "meshEnclosedVolumeM3",
                "display_fill_height_m": "displayFillHeightM",
                "display_proxy_volume_disclaimer": (
                    "displayProxyVolumeDisclaimer"
                ),
            }[key]
            prim.CreateAttribute(
                f"labutopia:{attribute_name}", value_type, custom=True
            ).Set(surface_frame[key])
    prim.CreateAttribute(
        "labutopia:presentationOnlyVolumeDisclaimer",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(PRESENTATION_ONLY_VOLUME_DISCLAIMER)
    prim.CreateAttribute(
        "labutopia:presentationOnlyShapeDisclaimer",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(PRESENTATION_ONLY_SHAPE_DISCLAIMER)

    if material_path is not None:
        material_prim = stage.GetPrimAtPath(material_path)
        material = UsdShade.Material(material_prim)
        if not material_prim or not material:
            raise ValueError(f"presentation_material_missing:{material_path}")
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
    return prim

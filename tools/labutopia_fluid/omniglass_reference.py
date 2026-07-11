"""Render-only A18-scaled particle proxies for accepted real-beaker traces."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
import math
from numbers import Real
from typing import Any

from pxr import Gf, Sdf, UsdGeom, UsdShade

from tools.labutopia_fluid.presentation_look_profiles import (
    REF_OMNIGLASS_GLASS_COLOR,
    REF_OMNIGLASS_REFLECTION_COLOR,
)


REFERENCE_CANDIDATE_IDS = (
    "OMNI_REF_FINE",
    "OMNI_REF_RATIO_15",
    "OMNI_REF_RATIO_12",
)
A18_REFERENCE_CONTAINER_INTERIOR_SPAN = 0.30
A18_REFERENCE_POINT_WIDTH = 0.02
A18_REFERENCE_NEAREST_NEIGHBOR_MEDIAN = 0.018516


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
    """Build the three display-width contracts from the measured cup diameter."""
    diameter = _positive_finite("interior_diameter", interior_diameter)
    widths = {
        "OMNI_REF_FINE": min(max(diameter / 32.0, 0.0015), 0.0020),
        "OMNI_REF_RATIO_15": diameter / 15.0,
        "OMNI_REF_RATIO_12": diameter / 12.0,
    }
    return {
        candidate_id: {
            "candidate_id": candidate_id,
            "interior_diameter": diameter,
            "display_width": width,
            "voxel_size": width,
            "width_to_interior_ratio": width / diameter,
            "proxy_mode": "deterministic_canonical_voxel_centroid",
            "presentation_only": True,
            "a18_reference": {
                "container_interior_span": A18_REFERENCE_CONTAINER_INTERIOR_SPAN,
                "point_width": A18_REFERENCE_POINT_WIDTH,
                "nearest_neighbor_median": A18_REFERENCE_NEAREST_NEIGHBOR_MEDIAN,
                "glass_color": list(REF_OMNIGLASS_GLASS_COLOR),
                "reflection_color": list(REF_OMNIGLASS_REFLECTION_COLOR),
            },
        }
        for candidate_id, width in widths.items()
    }


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
) -> dict[str, Any]:
    """Build one candidate frame and its presentation-only count contract."""
    source_positions = tuple(
        _point_tuple(point, index=index) for index, point in enumerate(positions_world)
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
        "presentation_only": True,
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

    if material_path is not None:
        material_prim = stage.GetPrimAtPath(material_path)
        material = UsdShade.Material(material_prim)
        if not material_prim or not material:
            raise ValueError(f"presentation_material_missing:{material_path}")
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
    return prim

#!/usr/bin/env python3
"""Run S2F follow-up sweeps for PhysX/PBD beaker collider recovery."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import traceback
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_beaker_collider_smoke import (
    CLASSIFICATION_CONTRACT_VERSION,
    ColliderConfig,
    FLUID_SAFE_WRAPPER_FRAME,
    PROMOTION_INITIAL_RADIAL_VELOCITY,
    PROMOTION_PARTICLE_MAX_VELOCITY,
    VariantSpec,
    _gpu_probe,
    _run_variant,
    classify_collider_hold,
)
from tools.labutopia_fluid.run_standalone_particle_smoke import _write_json


DEFAULT_PARENT_MANIFEST = "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"
DEFAULT_BASELINE_FREEZE_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
)
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s2_followup_c2_proxy_sweep_20260707_001"
)
DEFAULT_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_c2_proxy_sweep_20260707.json"
)
DEFAULT_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f1"
DEFAULT_S2F2_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s2f2_velocity_contact_offset_20260708_001"
)
DEFAULT_S2F2_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f2_velocity_contact_offset_20260708.json"
)
DEFAULT_S2F2_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f2"
DEFAULT_S2F3_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s2f3_c3_sdf_sweep_20260708_001"
)
DEFAULT_S2F3_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json"
)
DEFAULT_S2F3_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f3"
DEFAULT_S2F3_SOURCE_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json"
)
DEFAULT_S2F4_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s2f4_c4_native_mesh_isolation_20260708_001"
)
DEFAULT_S2F4_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f4_c4_native_mesh_isolation_20260708.json"
)
DEFAULT_S2F4_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f4"
DEFAULT_S2F4_SOURCE_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json"
)
DEFAULT_S2F5_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s2f5_promotion_review_20260708_001"
)
DEFAULT_S2F5_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json"
)
DEFAULT_S2F5_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f5"
DEFAULT_S2F5_SOURCE_MANIFEST = DEFAULT_S2F2_MANIFEST_PATH
DEFAULT_D4_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_d4_wrapper_sweep_20260709_001"
)
DEFAULT_D4_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_proxy_wrapper_design_d4_sweep_20260709.json"
)
DEFAULT_D4_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_d4"
DEFAULT_D4_PROMOTION_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_d4_wrapper_promotion_20260709_001"
)
DEFAULT_D4_PROMOTION_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_d4_wrapper_promotion_20260709.json"
)
DEFAULT_D4_PROMOTION_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_d4p"
DEFAULT_D4_PROMOTION_SOURCE_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_d4_wrapper_smoke_20260709_004.json"
)
S2F5_PROMOTION_CANDIDATE_ID = "C2A_009_S2F2_VEL020"
S2F5_PARTICLE_COUNTS = (256, 1024)
S2F5_PARTICLE_SEEDS = (0, 1, 2)
D4_PROMOTION_PARTICLE_COUNTS = (512, 1024, 4096, 50000)
D4_PROMOTION_PARTICLE_SEEDS = (0, 1, 2)
D4_PROMOTION_CANDIDATE_ID = "D4A_018"
S2F3_SDF_RESOLUTIONS = (64, 96, 128)
S2F3_SDF_SUBGRID_RESOLUTIONS = (4, 8)
S2F3_SDF_MARGINS = (0.002, 0.005)
S2F3_SDF_NARROW_BAND_THICKNESSES = (0.01, 0.02)
S2F4_NATIVE_SOURCE_PRIM = "/World/beaker2"
S2F4_NATIVE_MESH_SOURCE_PRIM = "/World/beaker2/mesh"
S2F4_NATIVE_REFERENCE_SCOPE = "parent_scope"
S2F4_NATIVE_MATERIAL_BINDING_STRATEGY = "local_blue_glass_override"
S2F4_NATIVE_POSE_ALIGNMENT = "bbox_recenter_to_source_region"
REQUIRED_VARIANT_EVIDENCE_FILES = {
    "particle_readback_trace",
    "physics_scene_settings",
    "initial_frame",
    "mid_frame",
    "terminal_frame",
    "top_collision_overlay",
    "side_collision_overlay",
}
DEFAULT_NATIVE_USD = "assets/chemistry_lab/lab_001/lab_001.usd"
FOLLOWUP_CONTRACT_VERSION = "s2f_velocity_contact_offset_v2"
D4_FOLLOWUP_CONTRACT = "s2_no_outside_source_v2+d4_followup"
FOLLOWUP_CLASSIFICATIONS = {
    "PASS_SOURCE_HOLD",
    "FAIL_CONTAINER_LEAK",
    "FAIL_GPU_COLLIDER_UNSUPPORTED",
    "FAIL_CPU_COLLISION_FALLBACK",
    "FAIL_PARTICLE_EXPLOSION",
    "FAIL_READBACK_UNAVAILABLE",
    "FAIL_PERF_BUDGET_EXCEEDED",
    "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE",
}
D4_MATRIX_STOP_CLASSIFICATIONS = {
    "STOP_WITH_EVIDENCE",
    "STOP_WRAPPER_NOT_FLUID_SAFE",
    "STOP_STATIC_HOLD_LEAK",
    "STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE",
    "STOP_PERF_OR_OOM",
    "STOP_VISUAL_PHYSICS_MISMATCH",
    "STOP_READBACK_UNAVAILABLE",
}
D4_WRAPPER_PANEL_COUNTS = (48, 64, 72)
D4_WRAPPER_WALL_THICKNESSES = (0.014, 0.018, 0.022)
D4_WRAPPER_BOTTOM_OVERLAPS = (0.003, 0.005, 0.008)
D4_WRAPPER_PANEL_ARC_OVERLAP_FACTORS = (1.08, 1.14, 1.20)
# C2A_009 contact baseline (limited joint sweep stays on this pin for D4 geometry).
D4_WRAPPER_PARTICLE_CONTACT_OFFSET = 0.0045
D4_WRAPPER_COLLIDER_CONTACT_OFFSET = 0.004
D4_WRAPPER_COLLIDER_REST_OFFSET = 0.0
D4_WRAPPER_PARENT_PATH = "/World/beaker2"


@dataclass(frozen=True)
class C2ProxyCandidate:
    candidate_id: str
    panel_count: int
    wall_thickness: float
    bottom_overlap: float
    particle_contact_offset: float
    collider_contact_offset: float
    collider_rest_offset: float
    initial_radial_velocity: float
    parent_candidate_id: str | None = None
    phase: str = "S2F1_C2_PROXY_SWEEP"
    variable_group: str = "c2_proxy_sweep"
    spawn_particle_contact_offset: float | None = None
    particle_system_contact_offset: float | None = None
    particle_rest_offset: float = 0.0
    fluid_rest_offset: float | None = None
    solid_rest_offset: float | None = None
    particle_enable_ccd: bool | None = None
    particle_max_velocity: float = 5.0
    particle_max_depenetration_velocity: float | None = None
    non_physical_parameter_dependence_risk: bool = False
    particle_count: int | None = None
    particle_seed: int | None = None
    sdf_resolution: int | None = None
    sdf_subgrid_resolution: int | None = None
    sdf_margin: float | None = None
    sdf_narrow_band_thickness: float | None = None
    mesh_bottom_fan_closure: bool | None = None
    normals_winding_audit: str | None = None
    native_source_path: str | None = None
    native_mesh_source_path: str | None = None
    native_reference_scope: str | None = None
    native_material_binding_strategy: str | None = None
    native_material_binding_scope_closed: bool | None = None
    native_pose_alignment: str | None = None
    native_collision_route: str | None = None
    native_mesh_collision_enabled: bool | None = None
    proxy_collision_enabled: bool | None = None
    panel_arc_overlap_factor: float | None = None
    interior_inset: float | None = None
    wrapper_parent_path: str | None = None
    wrapper_frame: str | None = None
    particle_spacing: float | None = None
    grid_dims: tuple[int, int, int] | None = None
    particle_width: float | None = None

    def to_config(self, *, base: ColliderConfig | None = None) -> ColliderConfig:
        config = base or ColliderConfig()
        return replace(
            config,
            particle_count=self.particle_count if self.particle_count is not None else config.particle_count,
            particle_seed=self.particle_seed if self.particle_seed is not None else config.particle_seed,
            wall_thickness=self.wall_thickness,
            bottom_overlap=self.bottom_overlap,
            particle_contact_offset=self.particle_contact_offset,
            spawn_particle_contact_offset=self.spawn_particle_contact_offset,
            particle_system_contact_offset=self.particle_system_contact_offset,
            particle_rest_offset=self.particle_rest_offset,
            fluid_rest_offset=self.fluid_rest_offset,
            solid_rest_offset=self.solid_rest_offset,
            collider_contact_offset=self.collider_contact_offset,
            collider_rest_offset=self.collider_rest_offset,
            initial_radial_velocity=self.initial_radial_velocity,
            particle_enable_ccd=self.particle_enable_ccd,
            particle_max_velocity=self.particle_max_velocity,
            particle_max_depenetration_velocity=self.particle_max_depenetration_velocity,
            interior_inset=self.interior_inset if self.interior_inset is not None else config.interior_inset,
            particle_spacing=self.particle_spacing if self.particle_spacing is not None else config.particle_spacing,
            grid_dims=self.grid_dims if self.grid_dims is not None else config.grid_dims,
            particle_width=self.particle_width if self.particle_width is not None else config.particle_width,
            sdf_resolution=self.sdf_resolution if self.sdf_resolution is not None else config.sdf_resolution,
            sdf_subgrid_resolution=(
                self.sdf_subgrid_resolution
                if self.sdf_subgrid_resolution is not None
                else config.sdf_subgrid_resolution
            ),
            sdf_margin=self.sdf_margin if self.sdf_margin is not None else config.sdf_margin,
            sdf_narrow_band_thickness=(
                self.sdf_narrow_band_thickness
                if self.sdf_narrow_band_thickness is not None
                else config.sdf_narrow_band_thickness
            ),
        )

    def to_variant_spec(self) -> VariantSpec:
        if self.phase in {"D4_WRAPPER_SWEEP", "D4_WRAPPER_PROMOTION"} or self.candidate_id.startswith("D4A_"):
            return VariantSpec(
                variant_id=self.candidate_id,
                name="fluid_safe_wrapper",
                description=(
                    "D4 invisible beaker2-local fluid-safe box-panel wrapper; "
                    "native mesh collision disabled."
                ),
                setup="fluid_safe_wrapper",
                collider_count=self.panel_count + 1,
                collision_approximation="convex_panel_boxes",
                source_kind="fluid_safe_wrapper",
                panel_count=self.panel_count,
                panel_arc_overlap_factor=self.panel_arc_overlap_factor,
                interior_inset=self.interior_inset,
                wrapper_parent_path=self.wrapper_parent_path or D4_WRAPPER_PARENT_PATH,
                wrapper_frame=self.wrapper_frame or FLUID_SAFE_WRAPPER_FRAME,
                native_mesh_collision_enabled=(
                    False
                    if self.native_mesh_collision_enabled is None
                    else self.native_mesh_collision_enabled
                ),
                native_mesh_source_path=self.native_mesh_source_path,
            )
        if self.phase == "S2F3_C3_SDF_SWEEP":
            return VariantSpec(
                variant_id=self.candidate_id,
                name="sdf_cooking_sweep",
                description="S2F3 open concave tri-mesh beaker with swept PhysX SDF cooking attributes.",
                setup="s2f3_sdf_open_concave_mesh",
                collider_count=1,
                collision_approximation="sdf",
                source_kind="procedural_mesh",
                sdf_resolution=self.sdf_resolution,
                sdf_subgrid_resolution=self.sdf_subgrid_resolution,
                sdf_margin=self.sdf_margin,
                sdf_narrow_band_thickness=self.sdf_narrow_band_thickness,
            )
        if self.phase == "S2F5_PROMOTION_REVIEW" and (
            self.candidate_id.startswith("C3A_") or (self.parent_candidate_id or "").startswith("C3A_")
        ):
            return VariantSpec(
                variant_id=self.candidate_id,
                name="promotion_review_sdf",
                description="S2F5 repeated static-hold promotion review trial for the SDF S2F3 candidate.",
                setup="s2f5_promotion_review_sdf",
                collider_count=1,
                collision_approximation="sdf",
                source_kind="procedural_mesh",
                sdf_resolution=self.sdf_resolution,
                sdf_subgrid_resolution=self.sdf_subgrid_resolution,
                sdf_margin=self.sdf_margin,
                sdf_narrow_band_thickness=self.sdf_narrow_band_thickness,
            )
        if self.phase == "S2F4_C4_NATIVE_MESH_ISOLATION":
            return VariantSpec(
                variant_id=self.candidate_id,
                name="native_mesh_isolation",
                description="S2F4 scope-closed LabUtopia native beaker2 mesh isolation candidate.",
                setup="s2f4_native_beaker_mesh_isolation",
                collider_count=25 if self.proxy_collision_enabled else 1,
                collision_approximation=self.native_collision_route or "convexDecomposition",
                source_kind=(
                    "native_render_mesh_with_proxy_collision"
                    if self.proxy_collision_enabled
                    else "native_mesh_reference"
                ),
                native_source_path=self.native_source_path or S2F4_NATIVE_SOURCE_PRIM,
                native_mesh_source_path=self.native_mesh_source_path or S2F4_NATIVE_MESH_SOURCE_PRIM,
                native_reference_scope=self.native_reference_scope or S2F4_NATIVE_REFERENCE_SCOPE,
                native_material_binding_strategy=(
                    self.native_material_binding_strategy or S2F4_NATIVE_MATERIAL_BINDING_STRATEGY
                ),
                native_material_binding_scope_closed=self.native_material_binding_scope_closed,
                native_pose_alignment=self.native_pose_alignment or S2F4_NATIVE_POSE_ALIGNMENT,
                native_collision_route=self.native_collision_route,
                native_mesh_collision_enabled=self.native_mesh_collision_enabled,
                proxy_collision_enabled=self.proxy_collision_enabled,
                sdf_resolution=self.sdf_resolution,
                sdf_subgrid_resolution=self.sdf_subgrid_resolution,
                sdf_margin=self.sdf_margin,
                sdf_narrow_band_thickness=self.sdf_narrow_band_thickness,
                panel_count=self.panel_count if self.proxy_collision_enabled else None,
            )
        if self.phase == "S2F5_PROMOTION_REVIEW" and (
            self.candidate_id.startswith("C4A_") or (self.parent_candidate_id or "").startswith("C4A_")
        ):
            return VariantSpec(
                variant_id=self.candidate_id,
                name="promotion_review_native_mesh",
                description="S2F5 repeated static-hold promotion review trial for the S2F4 native-derived candidate.",
                setup="s2f5_promotion_review_native_mesh",
                collider_count=25 if self.proxy_collision_enabled else 1,
                collision_approximation=self.native_collision_route or "convexDecomposition",
                source_kind=(
                    "native_render_mesh_with_proxy_collision"
                    if self.proxy_collision_enabled
                    else "native_mesh_reference"
                ),
                native_source_path=self.native_source_path or S2F4_NATIVE_SOURCE_PRIM,
                native_mesh_source_path=self.native_mesh_source_path or S2F4_NATIVE_MESH_SOURCE_PRIM,
                native_reference_scope=self.native_reference_scope or S2F4_NATIVE_REFERENCE_SCOPE,
                native_material_binding_strategy=(
                    self.native_material_binding_strategy or S2F4_NATIVE_MATERIAL_BINDING_STRATEGY
                ),
                native_material_binding_scope_closed=self.native_material_binding_scope_closed,
                native_pose_alignment=self.native_pose_alignment or S2F4_NATIVE_POSE_ALIGNMENT,
                native_collision_route=self.native_collision_route,
                native_mesh_collision_enabled=self.native_mesh_collision_enabled,
                proxy_collision_enabled=self.proxy_collision_enabled,
                sdf_resolution=self.sdf_resolution,
                sdf_subgrid_resolution=self.sdf_subgrid_resolution,
                sdf_margin=self.sdf_margin,
                sdf_narrow_band_thickness=self.sdf_narrow_band_thickness,
                panel_count=self.panel_count if self.proxy_collision_enabled else None,
            )
        if self.phase == "S2F5_PROMOTION_REVIEW":
            setup = "s2f5_promotion_review"
            name = "promotion_review"
            description = "S2F5 repeated static-hold promotion review trial for the S2F2 candidate."
        elif self.phase == "S2F2_VELOCITY_CONTACT_OFFSET":
            setup = "s2f2_velocity_contact_offset"
            name = "velocity_contact_offset"
            description = "S2F2 velocity/contact-offset isolation candidate derived from a near-pass C2A parent."
        else:
            setup = "s2f1_c2_proxy_sweep"
            name = "c2_proxy_followup"
            description = (
                "S2F1 C2-derived segmented convex wall proxy with swept panel count, "
                "wall thickness, bottom overlap, and contact offsets."
            )
        return VariantSpec(
            variant_id=self.candidate_id,
            name=name,
            description=description,
            setup=setup,
            collider_count=self.panel_count + 1,
            collision_approximation="convex_panel_boxes",
            source_kind="procedural_proxy",
            panel_count=self.panel_count,
        )


def followup_phase_specs(
    *,
    phase: str | None = None,
    status: str | None = None,
    best_for_s2f5: Sequence[str] | None = None,
    best_for_s3: Sequence[str] | None = None,
    s2f4_contract_complete: bool = True,
) -> dict[str, dict[str, Any]]:
    specs = {
        "S2F0_BASELINE_FREEZE": {
            "candidate_prefix": "S2",
            "status": "COMPLETE",
            "description": "Frozen S2 collider matrix baseline.",
        },
        "S2F1_C2_PROXY_SWEEP": {
            "candidate_prefix": "C2A",
            "status": "ACTIVE",
            "description": "Bounded C2-derived segmented proxy sweep.",
        },
        "S2F2_VELOCITY_CONTACT_OFFSET": {
            "candidate_prefix": "C2A",
            "status": "PENDING",
            "description": "Velocity/contact-offset isolation after S2F1.",
        },
        "S2F3_C3_SDF_SWEEP": {
            "candidate_prefix": "C3A",
            "status": "PENDING",
            "description": "SDF open beaker cooking sweep.",
        },
        "S2F4_C4_NATIVE_MESH_ISOLATION": {
            "candidate_prefix": "C4A",
            "status": "PENDING",
            "description": "Native beaker mesh isolation.",
        },
        "S2F5_PROMOTION_REVIEW": {
            "candidate_prefix": "S2F",
            "status": "PENDING",
            "description": "Promotion review before S3 release.",
        },
        "D4_WRAPPER_SWEEP": {
            "candidate_prefix": "D4A",
            "status": "PENDING",
            "description": "Fluid-safe wrapper geometry sweep with pinned promotion init.",
        },
        "D4_WRAPPER_PROMOTION": {
            "candidate_prefix": "D4P",
            "status": "PENDING",
            "description": "D4 wrapper promotion matrix (seeds×counts) for Physics-A G1.",
        },
    }
    if phase == "D4_WRAPPER_SWEEP":
        specs["S2F1_C2_PROXY_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F2_VELOCITY_CONTACT_OFFSET"]["status"] = "COMPLETE_GO_NEXT"
        specs["S2F3_C3_SDF_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F5_PROMOTION_REVIEW"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        if status == "GO_NEXT" and best_for_s3:
            specs["D4_WRAPPER_SWEEP"]["status"] = "COMPLETE_GO_NEXT"
            specs["D4_WRAPPER_PROMOTION"]["status"] = "NEXT"
        elif status in D4_MATRIX_STOP_CLASSIFICATIONS:
            specs["D4_WRAPPER_SWEEP"]["status"] = f"COMPLETE_{status}"
        else:
            specs["D4_WRAPPER_SWEEP"]["status"] = "ACTIVE"
    if phase == "D4_WRAPPER_PROMOTION":
        specs["S2F1_C2_PROXY_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F2_VELOCITY_CONTACT_OFFSET"]["status"] = "COMPLETE_GO_NEXT"
        specs["S2F3_C3_SDF_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F5_PROMOTION_REVIEW"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["D4_WRAPPER_SWEEP"]["status"] = "COMPLETE_GO_NEXT"
        if status == "GO_NEXT" and best_for_s3:
            specs["D4_WRAPPER_PROMOTION"]["status"] = "COMPLETE_GO_NEXT"
        elif status == "STOP_WITH_EVIDENCE":
            specs["D4_WRAPPER_PROMOTION"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        else:
            specs["D4_WRAPPER_PROMOTION"]["status"] = "ACTIVE"
    if phase == "S2F2_VELOCITY_CONTACT_OFFSET" and status == "GO_NEXT" and best_for_s2f5:
        specs["S2F1_C2_PROXY_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F2_VELOCITY_CONTACT_OFFSET"]["status"] = "COMPLETE_GO_NEXT"
        specs["S2F5_PROMOTION_REVIEW"]["status"] = "NEXT"
    if phase == "S2F5_PROMOTION_REVIEW":
        specs["S2F1_C2_PROXY_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F2_VELOCITY_CONTACT_OFFSET"]["status"] = "COMPLETE_GO_NEXT"
        if status == "GO_NEXT" and best_for_s3:
            specs["S2F5_PROMOTION_REVIEW"]["status"] = "COMPLETE_GO_NEXT"
        elif status == "STOP_WITH_EVIDENCE":
            specs["S2F5_PROMOTION_REVIEW"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        else:
            specs["S2F5_PROMOTION_REVIEW"]["status"] = "ACTIVE"
    if phase == "S2F3_C3_SDF_SWEEP":
        specs["S2F1_C2_PROXY_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F2_VELOCITY_CONTACT_OFFSET"]["status"] = "COMPLETE_GO_NEXT"
        specs["S2F5_PROMOTION_REVIEW"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        if status == "GO_NEXT" and best_for_s2f5:
            specs["S2F3_C3_SDF_SWEEP"]["status"] = "COMPLETE_GO_NEXT"
            specs["S2F5_PROMOTION_REVIEW"]["status"] = "NEXT"
        elif status == "STOP_WITH_EVIDENCE":
            specs["S2F3_C3_SDF_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
            specs["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] = "NEXT"
        else:
            specs["S2F3_C3_SDF_SWEEP"]["status"] = "ACTIVE"
    if phase == "S2F4_C4_NATIVE_MESH_ISOLATION":
        specs["S2F1_C2_PROXY_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F2_VELOCITY_CONTACT_OFFSET"]["status"] = "COMPLETE_GO_NEXT"
        specs["S2F3_C3_SDF_SWEEP"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        specs["S2F5_PROMOTION_REVIEW"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        if status == "GO_NEXT" and best_for_s2f5:
            specs["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] = "COMPLETE_GO_NEXT"
            specs["S2F5_PROMOTION_REVIEW"]["status"] = "NEXT"
        elif status == "STOP_WITH_EVIDENCE" and s2f4_contract_complete:
            specs["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] = "COMPLETE_STOP_WITH_EVIDENCE"
        else:
            specs["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] = "ACTIVE"
    return specs


def build_c2_proxy_sweep(*, limit: int = 12) -> list[C2ProxyCandidate]:
    rows = [
        (24, 0.010, 0.000, 0.0045, 0.002, 0.000, 0.08),
        (24, 0.014, 0.003, 0.0060, 0.004, -0.001, 0.04),
        (24, 0.018, 0.006, 0.0075, 0.006, 0.000, 0.02),
        (32, 0.010, 0.003, 0.0075, 0.006, -0.001, 0.08),
        (32, 0.014, 0.006, 0.0045, 0.002, 0.000, 0.04),
        (32, 0.018, 0.000, 0.0060, 0.004, -0.001, 0.02),
        (48, 0.010, 0.006, 0.0060, 0.006, 0.000, 0.04),
        (48, 0.014, 0.000, 0.0075, 0.002, -0.001, 0.02),
        (48, 0.018, 0.003, 0.0045, 0.004, 0.000, 0.08),
        (32, 0.014, 0.003, 0.0060, 0.006, -0.001, 0.04),
        (48, 0.018, 0.006, 0.0075, 0.006, -0.001, 0.02),
        (24, 0.018, 0.006, 0.0075, 0.006, -0.001, 0.08),
    ]
    candidates: list[C2ProxyCandidate] = []
    for index, row in enumerate(rows[:limit], start=1):
        candidates.append(
            C2ProxyCandidate(
                candidate_id=f"C2A_{index:03d}",
                panel_count=row[0],
                wall_thickness=row[1],
                bottom_overlap=row[2],
                particle_contact_offset=row[3],
                collider_contact_offset=row[4],
                collider_rest_offset=row[5],
                initial_radial_velocity=row[6],
                parent_candidate_id=None,
                phase="S2F1_C2_PROXY_SWEEP",
                variable_group="c2_proxy_sweep",
            )
        )
    return candidates


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _offset_defaults(particle_contact_offset: float) -> dict[str, float]:
    return {
        "particle_system_contact_offset": particle_contact_offset * 1.2,
        "solid_rest_offset": particle_contact_offset * 0.6,
        "fluid_rest_offset": particle_contact_offset * 0.6,
    }


def _candidate_from_plan_row(row: dict[str, Any]) -> C2ProxyCandidate:
    particle_contact_offset = float(row["particle_contact_offset"])
    defaults = _offset_defaults(particle_contact_offset)
    return C2ProxyCandidate(
        candidate_id=str(row["candidate_id"]),
        parent_candidate_id=row.get("parent_candidate_id"),
        phase=str(row.get("phase", "S2F1_C2_PROXY_SWEEP")),
        variable_group=str(row.get("variable_group", "c2_proxy_sweep")),
        panel_count=int(row["panel_count"]),
        wall_thickness=float(row["wall_thickness"]),
        bottom_overlap=float(row["bottom_overlap"]),
        particle_contact_offset=particle_contact_offset,
        spawn_particle_contact_offset=(
            float(row["spawn_particle_contact_offset"])
            if row.get("spawn_particle_contact_offset") is not None
            else None
        ),
        particle_system_contact_offset=(
            float(row["particle_system_contact_offset"]) if row.get("particle_system_contact_offset") is not None else defaults["particle_system_contact_offset"]
        ),
        fluid_rest_offset=float(row["fluid_rest_offset"]) if row.get("fluid_rest_offset") is not None else defaults["fluid_rest_offset"],
        solid_rest_offset=float(row["solid_rest_offset"]) if row.get("solid_rest_offset") is not None else defaults["solid_rest_offset"],
        collider_contact_offset=float(row["collider_contact_offset"]),
        collider_rest_offset=float(row["collider_rest_offset"]),
        initial_radial_velocity=float(row["initial_radial_velocity"]),
        particle_enable_ccd=row.get("particle_enable_ccd"),
        particle_max_velocity=float(row.get("particle_max_velocity", 5.0)),
        particle_max_depenetration_velocity=(
            float(row["particle_max_depenetration_velocity"])
            if row.get("particle_max_depenetration_velocity") is not None
            else None
        ),
        non_physical_parameter_dependence_risk=bool(row.get("non_physical_parameter_dependence_risk", False)),
        particle_count=int(row["particle_count"]) if row.get("particle_count") is not None else None,
        particle_seed=int(row["particle_seed"]) if row.get("particle_seed") is not None else None,
        particle_spacing=float(row["particle_spacing"]) if row.get("particle_spacing") is not None else None,
        grid_dims=(
            tuple(int(v) for v in row["grid_dims"])  # type: ignore[misc]
            if row.get("grid_dims") is not None
            else None
        ),
        particle_width=float(row["particle_width"]) if row.get("particle_width") is not None else None,
        sdf_resolution=int(row["sdf_resolution"]) if row.get("sdf_resolution") is not None else None,
        sdf_subgrid_resolution=(
            int(row["sdf_subgrid_resolution"]) if row.get("sdf_subgrid_resolution") is not None else None
        ),
        sdf_margin=float(row["sdf_margin"]) if row.get("sdf_margin") is not None else None,
        sdf_narrow_band_thickness=(
            float(row["sdf_narrow_band_thickness"])
            if row.get("sdf_narrow_band_thickness") is not None
            else None
        ),
        mesh_bottom_fan_closure=(
            bool(row["mesh_bottom_fan_closure"]) if row.get("mesh_bottom_fan_closure") is not None else None
        ),
        normals_winding_audit=(
            str(row["normals_winding_audit"]) if row.get("normals_winding_audit") is not None else None
        ),
        native_source_path=str(row["native_source_path"]) if row.get("native_source_path") is not None else None,
        native_mesh_source_path=(
            str(row["native_mesh_source_path"]) if row.get("native_mesh_source_path") is not None else None
        ),
        native_reference_scope=(
            str(row["native_reference_scope"]) if row.get("native_reference_scope") is not None else None
        ),
        native_material_binding_strategy=(
            str(row["native_material_binding_strategy"])
            if row.get("native_material_binding_strategy") is not None
            else None
        ),
        native_material_binding_scope_closed=(
            bool(row["native_material_binding_scope_closed"])
            if row.get("native_material_binding_scope_closed") is not None
            else None
        ),
        native_pose_alignment=str(row["native_pose_alignment"]) if row.get("native_pose_alignment") is not None else None,
        native_collision_route=(
            str(row["native_collision_route"]) if row.get("native_collision_route") is not None else None
        ),
        native_mesh_collision_enabled=(
            bool(row["native_mesh_collision_enabled"])
            if row.get("native_mesh_collision_enabled") is not None
            else None
        ),
        proxy_collision_enabled=(
            bool(row["proxy_collision_enabled"]) if row.get("proxy_collision_enabled") is not None else None
        ),
        panel_arc_overlap_factor=(
            float(row["panel_arc_overlap_factor"]) if row.get("panel_arc_overlap_factor") is not None else None
        ),
        interior_inset=float(row["interior_inset"]) if row.get("interior_inset") is not None else None,
        wrapper_parent_path=str(row["wrapper_parent_path"]) if row.get("wrapper_parent_path") is not None else None,
        wrapper_frame=str(row["wrapper_frame"]) if row.get("wrapper_frame") is not None else None,
    )


def _with_particle_offsets(candidate: C2ProxyCandidate, particle_contact_offset: float) -> dict[str, float]:
    return _offset_defaults(particle_contact_offset)


def _s2f2_candidate(
    parent: C2ProxyCandidate,
    *,
    suffix: str,
    variable_group: str,
    initial_radial_velocity: float | None = None,
    particle_contact_offset: float | None = None,
    collider_contact_offset: float | None = None,
    collider_rest_offset: float | None = None,
    particle_enable_ccd: bool | None = None,
    particle_max_velocity: float = 5.0,
    particle_max_depenetration_velocity: float | None = None,
    non_physical_parameter_dependence_risk: bool = False,
) -> C2ProxyCandidate:
    pco = particle_contact_offset if particle_contact_offset is not None else parent.particle_contact_offset
    offsets = _with_particle_offsets(parent, pco)
    return C2ProxyCandidate(
        candidate_id=f"{parent.candidate_id}_S2F2_{suffix}",
        parent_candidate_id=parent.candidate_id,
        phase="S2F2_VELOCITY_CONTACT_OFFSET",
        variable_group=variable_group,
        panel_count=parent.panel_count,
        wall_thickness=parent.wall_thickness,
        bottom_overlap=parent.bottom_overlap,
        particle_contact_offset=pco,
        spawn_particle_contact_offset=parent.particle_contact_offset,
        particle_system_contact_offset=offsets["particle_system_contact_offset"],
        fluid_rest_offset=offsets["fluid_rest_offset"],
        solid_rest_offset=offsets["solid_rest_offset"],
        collider_contact_offset=(
            collider_contact_offset if collider_contact_offset is not None else parent.collider_contact_offset
        ),
        collider_rest_offset=collider_rest_offset if collider_rest_offset is not None else parent.collider_rest_offset,
        initial_radial_velocity=(
            initial_radial_velocity if initial_radial_velocity is not None else parent.initial_radial_velocity
        ),
        particle_enable_ccd=particle_enable_ccd,
        particle_max_velocity=particle_max_velocity,
        particle_max_depenetration_velocity=particle_max_depenetration_velocity,
        non_physical_parameter_dependence_risk=non_physical_parameter_dependence_risk,
    )


def build_velocity_contact_offset_sweep(
    *,
    s2f1_manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
    limit: int | None = None,
) -> list[C2ProxyCandidate]:
    manifest = _load_json(Path(s2f1_manifest_path))
    plan_by_id = {str(candidate["candidate_id"]): candidate for candidate in manifest["candidate_plan"]}
    parent_ids = [str(candidate_id) for candidate_id in manifest.get("near_pass_for_s2f2", [])]
    candidates: list[C2ProxyCandidate] = []
    for parent_id in parent_ids:
        parent = _candidate_from_plan_row(plan_by_id[parent_id])
        pco_test = 0.0045 if parent_id == "C2A_007" else 0.0060
        cco_test = 0.004 if parent_id in {"C2A_005", "C2A_007"} else 0.006
        candidates.extend(
            [
                _s2f2_candidate(parent, suffix="BASE", variable_group="baseline_repeat"),
                _s2f2_candidate(
                    parent,
                    suffix="VEL020",
                    variable_group="velocity_020",
                    initial_radial_velocity=0.02,
                ),
                _s2f2_candidate(
                    parent,
                    suffix="PCO045" if parent_id == "C2A_007" else "PCO060",
                    variable_group="particle_contact",
                    particle_contact_offset=pco_test,
                ),
                _s2f2_candidate(
                    parent,
                    suffix=f"CCO{int(cco_test * 1000):03d}_RN001",
                    variable_group="collider_contact_rest",
                    collider_contact_offset=cco_test,
                    collider_rest_offset=-0.001,
                ),
                _s2f2_candidate(
                    parent,
                    suffix="CCD1",
                    variable_group="ccd_enabled",
                    particle_enable_ccd=True,
                    particle_max_depenetration_velocity=5.0,
                ),
                _s2f2_candidate(
                    parent,
                    suffix="VMAX010",
                    variable_group="max_velocity_guardrail",
                    particle_max_velocity=0.10,
                    non_physical_parameter_dependence_risk=True,
                ),
            ]
        )
    return candidates[:limit] if limit is not None else candidates


def build_s2f3_sdf_sweep(*, limit: int | None = None) -> list[C2ProxyCandidate]:
    candidates: list[C2ProxyCandidate] = []
    for sdf_resolution in S2F3_SDF_RESOLUTIONS:
        for sdf_subgrid_resolution in S2F3_SDF_SUBGRID_RESOLUTIONS:
            for sdf_margin in S2F3_SDF_MARGINS:
                for sdf_narrow_band_thickness in S2F3_SDF_NARROW_BAND_THICKNESSES:
                    index = len(candidates) + 1
                    candidates.append(
                        C2ProxyCandidate(
                            candidate_id=f"C3A_{index:03d}",
                            parent_candidate_id=None,
                            phase="S2F3_C3_SDF_SWEEP",
                            variable_group="sdf_cooking_sweep",
                            panel_count=0,
                            wall_thickness=0.010,
                            bottom_overlap=0.000,
                            particle_contact_offset=0.0045,
                            spawn_particle_contact_offset=0.0045,
                            particle_system_contact_offset=0.0054,
                            particle_rest_offset=0.0,
                            fluid_rest_offset=0.0027,
                            solid_rest_offset=0.0027,
                            collider_contact_offset=0.003,
                            collider_rest_offset=0.0,
                            initial_radial_velocity=0.08,
                            particle_max_velocity=5.0,
                            sdf_resolution=sdf_resolution,
                            sdf_subgrid_resolution=sdf_subgrid_resolution,
                            sdf_margin=sdf_margin,
                            sdf_narrow_band_thickness=sdf_narrow_band_thickness,
                            mesh_bottom_fan_closure=True,
                            normals_winding_audit="pass",
                        )
                    )
    return candidates[:limit] if limit is not None else candidates


def _s2f4_candidate(
    *,
    candidate_id: str,
    native_collision_route: str,
    native_mesh_collision_enabled: bool,
    proxy_collision_enabled: bool,
    sdf_resolution: int | None = None,
    sdf_subgrid_resolution: int | None = None,
    sdf_margin: float | None = None,
    sdf_narrow_band_thickness: float | None = None,
) -> C2ProxyCandidate:
    return C2ProxyCandidate(
        candidate_id=candidate_id,
        parent_candidate_id="C4",
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
        variable_group=native_collision_route,
        panel_count=24 if proxy_collision_enabled else 0,
        wall_thickness=0.010,
        bottom_overlap=0.006 if proxy_collision_enabled else 0.0,
        particle_contact_offset=0.0045,
        spawn_particle_contact_offset=0.0045,
        particle_system_contact_offset=0.0054,
        particle_rest_offset=0.0,
        fluid_rest_offset=0.0027,
        solid_rest_offset=0.0027,
        collider_contact_offset=0.003,
        collider_rest_offset=0.0,
        initial_radial_velocity=0.08,
        particle_max_velocity=5.0,
        sdf_resolution=sdf_resolution,
        sdf_subgrid_resolution=sdf_subgrid_resolution,
        sdf_margin=sdf_margin,
        sdf_narrow_band_thickness=sdf_narrow_band_thickness,
        native_source_path=S2F4_NATIVE_SOURCE_PRIM,
        native_mesh_source_path=S2F4_NATIVE_MESH_SOURCE_PRIM,
        native_reference_scope=S2F4_NATIVE_REFERENCE_SCOPE,
        native_material_binding_strategy=S2F4_NATIVE_MATERIAL_BINDING_STRATEGY,
        native_material_binding_scope_closed=True,
        native_pose_alignment=S2F4_NATIVE_POSE_ALIGNMENT,
        native_collision_route=native_collision_route,
        native_mesh_collision_enabled=native_mesh_collision_enabled,
        proxy_collision_enabled=proxy_collision_enabled,
    )


def build_s2f4_native_mesh_isolation(*, limit: int | None = None) -> list[C2ProxyCandidate]:
    candidates = [
        _s2f4_candidate(
            candidate_id="C4A_convexDecomposition_reference_scope_closed",
            native_collision_route="convexDecomposition",
            native_mesh_collision_enabled=True,
            proxy_collision_enabled=False,
        ),
        _s2f4_candidate(
            candidate_id="C4A_sdf_reference_scope_closed",
            native_collision_route="sdf",
            native_mesh_collision_enabled=True,
            proxy_collision_enabled=False,
            sdf_resolution=128,
            sdf_subgrid_resolution=8,
            sdf_margin=0.002,
            sdf_narrow_band_thickness=0.01,
        ),
        _s2f4_candidate(
            candidate_id="C4A_native_render_mesh_plus_proxy_collision",
            native_collision_route="render_mesh_plus_proxy_collision",
            native_mesh_collision_enabled=False,
            proxy_collision_enabled=True,
        ),
    ]
    return candidates[:limit] if limit is not None else candidates


def build_s2f5_promotion_review_sweep(
    *,
    s2f2_manifest_path: Path | str = DEFAULT_S2F5_SOURCE_MANIFEST,
    particle_counts: Sequence[int] = S2F5_PARTICLE_COUNTS,
    particle_seeds: Sequence[int] = S2F5_PARTICLE_SEEDS,
    promotion_candidate_id: str | None = None,
) -> list[C2ProxyCandidate]:
    manifest = _load_json(Path(s2f2_manifest_path))
    best_for_s2f5 = [str(candidate_id) for candidate_id in manifest.get("best_for_s2f5", [])]
    if promotion_candidate_id is None:
        if len(best_for_s2f5) != 1:
            raise ValueError(f"unexpected_s2f5_candidates:{best_for_s2f5!r}")
        promotion_candidate_id = best_for_s2f5[0]
    if best_for_s2f5 != [promotion_candidate_id]:
        raise ValueError(f"unexpected_s2f5_candidates:{best_for_s2f5!r}")
    plan_by_id = {str(candidate["candidate_id"]): candidate for candidate in manifest["candidate_plan"]}
    parent = _candidate_from_plan_row(plan_by_id[promotion_candidate_id])

    candidates: list[C2ProxyCandidate] = []
    for particle_count in particle_counts:
        for seed in particle_seeds:
            candidates.append(
                C2ProxyCandidate(
                    candidate_id=f"{promotion_candidate_id}_S2F5_P{particle_count:04d}_SEED{seed:03d}",
                    parent_candidate_id=promotion_candidate_id,
                    phase="S2F5_PROMOTION_REVIEW",
                    variable_group="promotion_review",
                    panel_count=parent.panel_count,
                    wall_thickness=parent.wall_thickness,
                    bottom_overlap=parent.bottom_overlap,
                    particle_contact_offset=parent.particle_contact_offset,
                    spawn_particle_contact_offset=parent.spawn_particle_contact_offset,
                    particle_system_contact_offset=parent.particle_system_contact_offset,
                    particle_rest_offset=parent.particle_rest_offset,
                    fluid_rest_offset=parent.fluid_rest_offset,
                    solid_rest_offset=parent.solid_rest_offset,
                    collider_contact_offset=parent.collider_contact_offset,
                    collider_rest_offset=parent.collider_rest_offset,
                    initial_radial_velocity=parent.initial_radial_velocity,
                    particle_enable_ccd=parent.particle_enable_ccd,
                    particle_max_velocity=parent.particle_max_velocity,
                    particle_max_depenetration_velocity=parent.particle_max_depenetration_velocity,
                    non_physical_parameter_dependence_risk=False,
                    particle_count=int(particle_count),
                    particle_seed=int(seed),
                    sdf_resolution=parent.sdf_resolution,
                    sdf_subgrid_resolution=parent.sdf_subgrid_resolution,
                    sdf_margin=parent.sdf_margin,
                    sdf_narrow_band_thickness=parent.sdf_narrow_band_thickness,
                    mesh_bottom_fan_closure=parent.mesh_bottom_fan_closure,
                    normals_winding_audit=parent.normals_winding_audit,
                    native_source_path=parent.native_source_path,
                    native_mesh_source_path=parent.native_mesh_source_path,
                    native_reference_scope=parent.native_reference_scope,
                    native_material_binding_strategy=parent.native_material_binding_strategy,
                    native_material_binding_scope_closed=parent.native_material_binding_scope_closed,
                    native_pose_alignment=parent.native_pose_alignment,
                    native_collision_route=parent.native_collision_route,
                    native_mesh_collision_enabled=parent.native_mesh_collision_enabled,
                    proxy_collision_enabled=parent.proxy_collision_enabled,
                )
            )
    return candidates


def aggregate_s2f5_promotion_review(
    candidate_results: Sequence[dict[str, Any]],
    *,
    required_particle_counts: Sequence[int] = S2F5_PARTICLE_COUNTS,
    required_particle_seeds: Sequence[int] = S2F5_PARTICLE_SEEDS,
    promotion_candidate_id: str = S2F5_PROMOTION_CANDIDATE_ID,
) -> dict[str, Any]:
    required_pairs = {(int(count), int(seed)) for count in required_particle_counts for seed in required_particle_seeds}
    observed_pairs = {
        (int(result.get("particle_count", -1)), int(result.get("particle_seed", -1)))
        for result in candidate_results
        if result.get("parent_candidate_id") == promotion_candidate_id
    }
    missing_pairs = sorted(required_pairs - observed_pairs)
    extra_pairs = sorted(observed_pairs - required_pairs)

    failed_trials: list[str] = []
    passed_trials: list[str] = []
    for result in candidate_results:
        candidate_id = str(result.get("candidate_id"))
        pair = (int(result.get("particle_count", -1)), int(result.get("particle_seed", -1)))
        trial_passed = (
            result.get("parent_candidate_id") == promotion_candidate_id
            and pair in required_pairs
            and result.get("classification") == "PASS_SOURCE_HOLD"
            and bool(result.get("readback_available"))
            and bool(result.get("evidence_files_complete"))
            and not bool(result.get("non_physical_parameter_dependence"))
        )
        if trial_passed:
            passed_trials.append(candidate_id)
        else:
            failed_trials.append(candidate_id)

    if missing_pairs or extra_pairs:
        status = "STOP_WITH_EVIDENCE"
        reason = "s2f5_trial_grid_mismatch"
        best_for_s3: list[str] = []
    elif len(passed_trials) == len(required_pairs) and not failed_trials:
        status = "GO_NEXT"
        reason = "all_s2f5_trials_passed"
        best_for_s3 = [promotion_candidate_id]
    else:
        status = "STOP_WITH_EVIDENCE"
        reason = "one_or_more_s2f5_trials_failed"
        best_for_s3 = []

    return {
        "status": status,
        "reason": reason,
        "best_for_s3": best_for_s3,
        "promotion_candidate_id": promotion_candidate_id,
        "required_particle_counts": [int(count) for count in required_particle_counts],
        "required_particle_seeds": [int(seed) for seed in required_particle_seeds],
        "required_trial_count": len(required_pairs),
        "observed_trial_count": len(candidate_results),
        "passed_trial_count": len(passed_trials),
        "passed_trials": passed_trials,
        "failed_trials": failed_trials,
        "missing_trials": [
            {"particle_count": particle_count, "particle_seed": seed} for particle_count, seed in missing_pairs
        ],
        "extra_trials": [
            {"particle_count": particle_count, "particle_seed": seed} for particle_count, seed in extra_pairs
        ],
    }


def build_d4_wrapper_sweep(*, limit: int | None = None) -> list[C2ProxyCandidate]:
    """Bounded D4 fluid-safe wrapper geometry sweep (spec §4.2).

    Pins promotion init velocity; sweeps panel_count / wall_thickness /
    bottom_overlap / panel_arc_overlap_factor. interior_inset clears spawn by at
    least particle_contact_offset.
    """
    rows: list[tuple[int, float, float, float]] = []
    for panel_count in D4_WRAPPER_PANEL_COUNTS:
        for wall_thickness in D4_WRAPPER_WALL_THICKNESSES:
            for bottom_overlap in D4_WRAPPER_BOTTOM_OVERLAPS:
                arc_index = (
                    D4_WRAPPER_PANEL_COUNTS.index(panel_count)
                    + D4_WRAPPER_WALL_THICKNESSES.index(wall_thickness)
                    + D4_WRAPPER_BOTTOM_OVERLAPS.index(bottom_overlap)
                ) % len(D4_WRAPPER_PANEL_ARC_OVERLAP_FACTORS)
                rows.append(
                    (
                        panel_count,
                        wall_thickness,
                        bottom_overlap,
                        D4_WRAPPER_PANEL_ARC_OVERLAP_FACTORS[arc_index],
                    )
                )

    candidates: list[C2ProxyCandidate] = []
    selected = rows if limit is None else rows[:limit]
    for index, (panel_count, wall_thickness, bottom_overlap, panel_arc) in enumerate(selected, start=1):
        particle_contact_offset = D4_WRAPPER_PARTICLE_CONTACT_OFFSET
        candidates.append(
            C2ProxyCandidate(
                candidate_id=f"D4A_{index:03d}",
                panel_count=panel_count,
                wall_thickness=wall_thickness,
                bottom_overlap=bottom_overlap,
                particle_contact_offset=particle_contact_offset,
                collider_contact_offset=D4_WRAPPER_COLLIDER_CONTACT_OFFSET,
                collider_rest_offset=D4_WRAPPER_COLLIDER_REST_OFFSET,
                initial_radial_velocity=PROMOTION_INITIAL_RADIAL_VELOCITY,
                particle_max_velocity=PROMOTION_PARTICLE_MAX_VELOCITY,
                parent_candidate_id="C2A_009",
                phase="D4_WRAPPER_SWEEP",
                variable_group="d4_wrapper_geometry",
                panel_arc_overlap_factor=panel_arc,
                interior_inset=particle_contact_offset,
                wrapper_parent_path=D4_WRAPPER_PARENT_PATH,
                wrapper_frame=FLUID_SAFE_WRAPPER_FRAME,
                native_mesh_collision_enabled=False,
                proxy_collision_enabled=True,
                non_physical_parameter_dependence_risk=False,
            )
        )
    return candidates


def d4_promotion_spawn_layout(particle_count: int) -> dict[str, Any]:
    """Return spawn/contact layout that can host particle_count without width>spacing.

    High-N rungs must keep particle_width ≤ spacing and scale contact offsets with
    spacing; otherwise PhysX explodes through the floor (50k evidence: width 0.0035
    with spacing 0.002 → ~46k below_table).

    Keep 1024 on the same short stack as 512 (grid_z=4). Raising grid_z to 8 for
    1024 increased wall punch-through (below_table 3–7 → 25–34) without helping
    capacity — XY disk already holds >1500 candidates at spacing 0.0045.
    """
    count = int(particle_count)
    if count <= 1024:
        spacing = 0.0045
        grid_z = 4
    elif count <= 4096:
        spacing = 0.003
        grid_z = 16
    elif count <= 50000:
        spacing = 0.002
        grid_z = 32
    else:
        raise ValueError(f"unsupported_d4_promotion_particle_count:{particle_count}")
    # Keep particle_width ≤ spacing; prefer the seal1 band (width 0.0035) that
    # cleared below_table. Matching liquid_usd width==contact at 0.0045 caused
    # false wall-parks at r≈0.05603 (just past 1e-3 slack).
    width = min(0.0035, spacing * 0.8)
    particle_contact_offset = min(D4_WRAPPER_PARTICLE_CONTACT_OFFSET, spacing)
    # Extra radial clearance at ≥1024: settle push parks centers ~5mm outward.
    interior_inset = max(particle_contact_offset, spacing)
    if count >= 1024:
        interior_inset = max(interior_inset, particle_contact_offset * 1.5)
    # liquid_usd lesson that DID help seal1: collider contact must not be thinner
    # than particle contact (old D4 used cco=0.004 < pco=0.0045).
    collider_contact_offset = max(
        min(D4_WRAPPER_COLLIDER_CONTACT_OFFSET, spacing),
        particle_contact_offset,
    )
    return {
        "particle_spacing": spacing,
        "grid_dims": (8, 8, grid_z),
        "particle_width": width,
        "particle_contact_offset": particle_contact_offset,
        "interior_inset": interior_inset,
        "collider_contact_offset": collider_contact_offset,
    }


def build_d4_wrapper_promotion_sweep(
    *,
    parent: C2ProxyCandidate | None = None,
    d4_manifest_path: Path | str | None = None,
    promotion_candidate_id: str = D4_PROMOTION_CANDIDATE_ID,
    particle_counts: Sequence[int] = D4_PROMOTION_PARTICLE_COUNTS,
    particle_seeds: Sequence[int] = D4_PROMOTION_PARTICLE_SEEDS,
) -> list[C2ProxyCandidate]:
    """12-trial Physics-A promotion matrix for a D4 wrapper geometry (spec §4.4)."""
    if parent is None:
        if d4_manifest_path is None:
            d4_manifest_path = DEFAULT_D4_PROMOTION_SOURCE_MANIFEST
        manifest = _load_json(Path(d4_manifest_path))
        plan_by_id = {str(row["candidate_id"]): row for row in manifest.get("candidate_plan", [])}
        if promotion_candidate_id not in plan_by_id:
            # Fall back to in-code D4 sweep geometry when smoke manifest lacks the row.
            parent = next(
                (c for c in build_d4_wrapper_sweep() if c.candidate_id == promotion_candidate_id),
                None,
            )
            if parent is None:
                raise ValueError(f"d4_promotion_parent_missing:{promotion_candidate_id}")
        else:
            parent = _candidate_from_plan_row(plan_by_id[promotion_candidate_id])

    candidates: list[C2ProxyCandidate] = []
    for particle_count in particle_counts:
        layout = d4_promotion_spawn_layout(int(particle_count))
        for seed in particle_seeds:
            candidates.append(
                C2ProxyCandidate(
                    candidate_id=f"{promotion_candidate_id}_D4P_P{int(particle_count):04d}_SEED{int(seed):03d}",
                    parent_candidate_id=promotion_candidate_id,
                    phase="D4_WRAPPER_PROMOTION",
                    variable_group="d4_wrapper_promotion",
                    panel_count=parent.panel_count,
                    # Thicker walls under promotion pressure (D4A_018 smoke used 0.022).
                    wall_thickness=max(float(parent.wall_thickness), 0.026),
                    bottom_overlap=max(parent.bottom_overlap, 0.012),
                    particle_contact_offset=float(layout["particle_contact_offset"]),
                    spawn_particle_contact_offset=parent.spawn_particle_contact_offset,
                    particle_system_contact_offset=parent.particle_system_contact_offset,
                    particle_rest_offset=parent.particle_rest_offset,
                    fluid_rest_offset=parent.fluid_rest_offset,
                    solid_rest_offset=parent.solid_rest_offset,
                    collider_contact_offset=float(layout["collider_contact_offset"]),
                    # Slightly negative rest helps catch thin-seam tunneling (C4 pattern).
                    collider_rest_offset=(
                        parent.collider_rest_offset
                        if parent.collider_rest_offset not in (None, 0.0)
                        else -0.001
                    ),
                    initial_radial_velocity=PROMOTION_INITIAL_RADIAL_VELOCITY,
                    # Force CCD on promotion: 1024 wall punch-through is ballistic
                    # (first below at r≫outer face by step 30). Parent smoke left CCD null.
                    particle_enable_ccd=True,
                    particle_max_velocity=PROMOTION_PARTICLE_MAX_VELOCITY,
                    particle_max_depenetration_velocity=parent.particle_max_depenetration_velocity,
                    non_physical_parameter_dependence_risk=False,
                    particle_count=int(particle_count),
                    particle_seed=int(seed),
                    particle_spacing=float(layout["particle_spacing"]),
                    grid_dims=tuple(layout["grid_dims"]),  # type: ignore[arg-type]
                    particle_width=float(layout["particle_width"]),
                    # Seal1 seed0 seam escape at r=0.084 — raise arc past 1.35.
                    panel_arc_overlap_factor=max(float(parent.panel_arc_overlap_factor or 1.2), 1.45),
                    interior_inset=float(layout["interior_inset"]),
                    wrapper_parent_path=parent.wrapper_parent_path or D4_WRAPPER_PARENT_PATH,
                    wrapper_frame=parent.wrapper_frame or FLUID_SAFE_WRAPPER_FRAME,
                    native_mesh_collision_enabled=False,
                    proxy_collision_enabled=True,
                )
            )
    return candidates


def aggregate_d4_wrapper_promotion(
    candidate_results: Sequence[dict[str, Any]],
    *,
    required_particle_counts: Sequence[int] = D4_PROMOTION_PARTICLE_COUNTS,
    required_particle_seeds: Sequence[int] = D4_PROMOTION_PARTICLE_SEEDS,
    promotion_candidate_id: str = D4_PROMOTION_CANDIDATE_ID,
) -> dict[str, Any]:
    """G1 requires all 12 seed×count trials PASS_SOURCE_HOLD (spec §4.4)."""
    required_pairs = {(int(count), int(seed)) for count in required_particle_counts for seed in required_particle_seeds}
    observed_pairs = {
        (int(result.get("particle_count", -1)), int(result.get("particle_seed", -1)))
        for result in candidate_results
        if result.get("parent_candidate_id") == promotion_candidate_id
    }
    missing_pairs = sorted(required_pairs - observed_pairs)
    extra_pairs = sorted(observed_pairs - required_pairs)

    failed_trials: list[str] = []
    passed_trials: list[str] = []
    for result in candidate_results:
        candidate_id = str(result.get("candidate_id"))
        pair = (int(result.get("particle_count", -1)), int(result.get("particle_seed", -1)))
        trial_passed = (
            result.get("parent_candidate_id") == promotion_candidate_id
            and pair in required_pairs
            and result.get("classification") == "PASS_SOURCE_HOLD"
            and bool(result.get("readback_available"))
            and bool(result.get("evidence_files_complete"))
            and not bool(result.get("non_physical_parameter_dependence"))
        )
        if trial_passed:
            passed_trials.append(candidate_id)
        else:
            failed_trials.append(candidate_id)

    if missing_pairs or extra_pairs:
        status = "STOP_WITH_EVIDENCE"
        reason = "d4_promotion_trial_grid_mismatch"
        best_for_s3: list[str] = []
        g1 = False
    elif len(passed_trials) == len(required_pairs) and not failed_trials:
        status = "GO_NEXT"
        reason = "all_d4_promotion_trials_passed"
        best_for_s3 = [promotion_candidate_id]
        g1 = True
    else:
        status = "STOP_WITH_EVIDENCE"
        reason = "one_or_more_d4_promotion_trials_failed"
        best_for_s3 = []
        g1 = False

    return {
        "status": status,
        "reason": reason,
        "best_for_s3": best_for_s3,
        "promotion_candidate_id": promotion_candidate_id,
        "required_particle_counts": [int(count) for count in required_particle_counts],
        "required_particle_seeds": [int(seed) for seed in required_particle_seeds],
        "required_trial_count": len(required_pairs),
        "observed_trial_count": len(candidate_results),
        "passed_trial_count": len(passed_trials),
        "passed_trials": passed_trials,
        "failed_trials": failed_trials,
        "missing_trials": [
            {"particle_count": particle_count, "particle_seed": seed} for particle_count, seed in missing_pairs
        ],
        "extra_trials": [
            {"particle_count": particle_count, "particle_seed": seed} for particle_count, seed in extra_pairs
        ],
        "g1_physics_a": g1,
        "init_pins": {
            "initial_radial_velocity": PROMOTION_INITIAL_RADIAL_VELOCITY,
            "particle_max_velocity": PROMOTION_PARTICLE_MAX_VELOCITY,
        },
    }


def evaluate_d4_init_pin_dependence(
    *,
    initial_radial_velocity: float,
    particle_max_velocity: float,
    pin_initial_radial_velocity: float = PROMOTION_INITIAL_RADIAL_VELOCITY,
    pin_particle_max_velocity: float = PROMOTION_PARTICLE_MAX_VELOCITY,
) -> bool:
    """True when a trial depends on forbidden sub-pin velocity crutches (spec §4.2)."""
    return (
        float(initial_radial_velocity) < float(pin_initial_radial_velocity)
        or float(particle_max_velocity) < float(pin_particle_max_velocity)
    )


def classify_d4_wrapper_trial(
    *,
    variant_id: str,
    config: ColliderConfig,
    initial_count: int,
    final_count: int,
    source_count: int,
    target_count: int,
    spill_count: int,
    below_table_count: int,
    nan_count: int,
    tail_leak_rate_fraction_per_second: float,
    cpu_collision_fallback_detected: bool,
    gpu_collider_unsupported: bool,
    fatal_error: dict[str, Any] | None,
    particle_motion_observed: bool = True,
    readback_position_changed: bool = True,
    blocking_runtime_warning_detected: bool = False,
    non_physical_parameter_dependence: bool | None = None,
    container_sealed_detected: bool = False,
    particle_explosion_detected: bool = False,
    perf_budget_exceeded: bool = False,
) -> dict[str, Any]:
    """Compose classify_collider_hold with D4 followup non-physical / motion gates.

    Preserves FAIL_* taxonomy; does not collapse all failures to FAIL_CONTAINER_LEAK.
    """
    pin_dependence = evaluate_d4_init_pin_dependence(
        initial_radial_velocity=config.initial_radial_velocity,
        particle_max_velocity=config.particle_max_velocity,
    )
    if non_physical_parameter_dependence is None:
        non_physical_parameter_dependence = pin_dependence
    else:
        non_physical_parameter_dependence = bool(non_physical_parameter_dependence) or pin_dependence

    hold = classify_collider_hold(
        variant_id=variant_id,
        config=config,
        initial_count=initial_count,
        final_count=final_count,
        source_count=source_count,
        target_count=target_count,
        spill_count=spill_count,
        below_table_count=below_table_count,
        nan_count=nan_count,
        tail_leak_rate_fraction_per_second=tail_leak_rate_fraction_per_second,
        cpu_collision_fallback_detected=cpu_collision_fallback_detected,
        gpu_collider_unsupported=gpu_collider_unsupported,
        fatal_error=fatal_error,
        particle_motion_observed=particle_motion_observed and readback_position_changed,
        container_sealed_detected=container_sealed_detected,
        particle_explosion_detected=particle_explosion_detected,
        perf_budget_exceeded=perf_budget_exceeded,
    )
    classification = str(hold["classification"])
    if classification == "PASS_SOURCE_HOLD":
        if non_physical_parameter_dependence:
            classification = "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE"
        elif blocking_runtime_warning_detected:
            classification = "FAIL_READBACK_UNAVAILABLE"
        elif not particle_motion_observed or not readback_position_changed:
            classification = "FAIL_READBACK_UNAVAILABLE"

    assert classification in FOLLOWUP_CLASSIFICATIONS or classification == "FAIL_CONTAINER_SEALED"
    result = dict(hold)
    result["candidate_id"] = variant_id
    result["classification"] = classification
    result["contract"] = D4_FOLLOWUP_CONTRACT
    result["non_physical_parameter_dependence"] = bool(non_physical_parameter_dependence)
    result["blocking_runtime_warning_detected"] = bool(blocking_runtime_warning_detected)
    result["particle_motion_observed"] = bool(particle_motion_observed)
    result["readback_position_changed"] = bool(readback_position_changed)
    result["pass_criteria"] = {
        **dict(hold.get("pass_criteria") or {}),
        "non_physical_parameter_dependence_false": not non_physical_parameter_dependence,
        "blocking_runtime_warning_detected_false": not blocking_runtime_warning_detected,
        "particle_motion_observed_true": bool(particle_motion_observed),
        "readback_position_changed_true": bool(readback_position_changed),
    }
    return result


def aggregate_d4_wrapper_sweep(
    candidate_results: Sequence[dict[str, Any]],
    *,
    expected_candidate_ids: Sequence[str] = (),
    grid_complete: bool | None = None,
    visual_physics_mismatch: bool = False,
) -> dict[str, Any]:
    """Matrix-level STOP taxonomy for D4_WRAPPER_SWEEP (spec §4.5)."""
    observed_ids = {str(result.get("candidate_id", "")) for result in candidate_results}
    expected_ids = [str(candidate_id) for candidate_id in expected_candidate_ids]
    missing_candidate_ids = [candidate_id for candidate_id in expected_ids if candidate_id not in observed_ids]
    if grid_complete is None:
        grid_complete = not missing_candidate_ids and (
            not expected_ids or len(candidate_results) >= len(expected_ids)
        )

    passed = [
        result
        for result in candidate_results
        if result.get("classification") == "PASS_SOURCE_HOLD"
        and not bool(result.get("non_physical_parameter_dependence"))
    ]
    non_physical = [
        result
        for result in candidate_results
        if result.get("classification") == "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE"
        or bool(result.get("non_physical_parameter_dependence"))
    ]
    readback_fails = [
        result for result in candidate_results if result.get("classification") == "FAIL_READBACK_UNAVAILABLE"
    ]
    perf_fails = [
        result for result in candidate_results if result.get("classification") == "FAIL_PERF_BUDGET_EXCEEDED"
    ]

    if visual_physics_mismatch:
        status = "STOP_VISUAL_PHYSICS_MISMATCH"
        reason = "wrapper_frame_or_sync_mismatch"
        best_for_promotion: list[str] = []
    elif not grid_complete or missing_candidate_ids:
        status = "STOP_WITH_EVIDENCE"
        reason = "incomplete_d4_wrapper_sweep_grid"
        best_for_promotion = []
    elif passed:
        status = "GO_NEXT"
        reason = "at_least_one_d4_wrapper_candidate_passed"
        best_for_promotion = [str(result["candidate_id"]) for result in passed]
    elif non_physical and len(non_physical) == len(candidate_results):
        status = "STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE"
        reason = "all_d4_candidates_depend_on_forbidden_init_crutches"
        best_for_promotion = []
    elif readback_fails and len(readback_fails) == len(candidate_results):
        status = "STOP_READBACK_UNAVAILABLE"
        reason = "all_d4_candidates_missing_readback"
        best_for_promotion = []
    elif perf_fails and len(perf_fails) == len(candidate_results):
        status = "STOP_PERF_OR_OOM"
        reason = "all_d4_candidates_exceeded_perf_budget"
        best_for_promotion = []
    else:
        status = "STOP_WRAPPER_NOT_FLUID_SAFE"
        reason = "d4_wrapper_sweep_leaks_remain"
        best_for_promotion = []

    assert status == "GO_NEXT" or status in D4_MATRIX_STOP_CLASSIFICATIONS
    return {
        "status": status,
        "reason": reason,
        "best_for_promotion": best_for_promotion,
        "best_for_s3": [],
        "grid_complete": bool(grid_complete),
        "expected_candidate_ids": expected_ids,
        "missing_candidate_ids": missing_candidate_ids,
        "observed_candidate_count": len(candidate_results),
        "passed_candidate_ids": [str(result["candidate_id"]) for result in passed],
        "non_physical_candidate_ids": [str(result["candidate_id"]) for result in non_physical],
        "allowed_stop_classifications": sorted(D4_MATRIX_STOP_CLASSIFICATIONS),
        "init_pins": {
            "initial_radial_velocity": PROMOTION_INITIAL_RADIAL_VELOCITY,
            "particle_max_velocity": PROMOTION_PARTICLE_MAX_VELOCITY,
        },
    }


def _s2f5_promotion_candidate_id(
    *,
    candidate_results: Sequence[dict[str, Any]],
    candidates: Sequence[C2ProxyCandidate],
) -> str:
    parent_ids = {
        str(parent_id)
        for parent_id in (
            [result.get("parent_candidate_id") for result in candidate_results]
            if candidate_results
            else [candidate.parent_candidate_id for candidate in candidates]
        )
        if parent_id
    }
    if len(parent_ids) == 1:
        return next(iter(parent_ids))
    return S2F5_PROMOTION_CANDIDATE_ID


def _d4_promotion_candidate_id(
    *,
    candidate_results: Sequence[dict[str, Any]],
    candidates: Sequence[C2ProxyCandidate],
) -> str:
    parent_ids = {
        str(parent_id)
        for parent_id in (
            [result.get("parent_candidate_id") for result in candidate_results]
            if candidate_results
            else [candidate.parent_candidate_id for candidate in candidates]
        )
        if parent_id
    }
    if len(parent_ids) == 1:
        return next(iter(parent_ids))
    return D4_PROMOTION_CANDIDATE_ID


def _pass_criteria(
    *,
    source_retention_fraction: float,
    particle_count_final_fraction: float,
    outside_source_count: int,
    target_count: int,
    spill_count: int,
    below_table_count: int,
    tail_leak_rate_fraction_per_second: float,
    cpu_collision_fallback_detected: bool,
    gpu_collider_unsupported: bool,
    nan_count: int,
    non_physical_parameter_dependence: bool,
) -> dict[str, bool]:
    return {
        "source_retention_fraction_ge_0_95": source_retention_fraction >= 0.95,
        "particle_count_final_fraction_ge_0_95": particle_count_final_fraction >= 0.95,
        "outside_source_count_eq_zero": outside_source_count == 0,
        "target_count_eq_zero": target_count == 0,
        "spill_count_eq_zero": spill_count == 0,
        "below_table_count_eq_zero": below_table_count == 0,
        "tail_leak_rate_lt_0_02": tail_leak_rate_fraction_per_second < 0.02,
        "cpu_collision_fallback_detected_false": not cpu_collision_fallback_detected,
        "gpu_collider_unsupported_false": not gpu_collider_unsupported,
        "nan_count_eq_zero": nan_count == 0,
        "non_physical_parameter_dependence_false": not non_physical_parameter_dependence,
    }


def classify_followup_candidate(
    *,
    candidate_id: str,
    source_retention_fraction: float,
    particle_count_final_fraction: float,
    outside_source_count: int,
    target_count: int,
    spill_count: int,
    below_table_count: int,
    tail_leak_rate_fraction_per_second: float,
    cpu_collision_fallback_detected: bool,
    gpu_collider_unsupported: bool,
    nan_count: int,
    non_physical_parameter_dependence: bool,
    fatal_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    criteria = _pass_criteria(
        source_retention_fraction=source_retention_fraction,
        particle_count_final_fraction=particle_count_final_fraction,
        outside_source_count=outside_source_count,
        target_count=target_count,
        spill_count=spill_count,
        below_table_count=below_table_count,
        tail_leak_rate_fraction_per_second=tail_leak_rate_fraction_per_second,
        cpu_collision_fallback_detected=cpu_collision_fallback_detected,
        gpu_collider_unsupported=gpu_collider_unsupported,
        nan_count=nan_count,
        non_physical_parameter_dependence=non_physical_parameter_dependence,
    )
    if fatal_error is not None:
        classification = "FAIL_READBACK_UNAVAILABLE"
    elif gpu_collider_unsupported:
        classification = "FAIL_GPU_COLLIDER_UNSUPPORTED"
    elif cpu_collision_fallback_detected:
        classification = "FAIL_CPU_COLLISION_FALLBACK"
    elif nan_count != 0:
        classification = "FAIL_PARTICLE_EXPLOSION"
    elif non_physical_parameter_dependence:
        classification = "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE"
    elif all(criteria.values()):
        classification = "PASS_SOURCE_HOLD"
    else:
        classification = "FAIL_CONTAINER_LEAK"

    assert classification in FOLLOWUP_CLASSIFICATIONS
    return {
        "candidate_id": candidate_id,
        "classification": classification,
        "source_retention_fraction": source_retention_fraction,
        "particle_count_final_fraction": particle_count_final_fraction,
        "outside_source_count": outside_source_count,
        "target_count": target_count,
        "spill_count": spill_count,
        "below_table_count": below_table_count,
        "tail_leak_rate_fraction_per_second": tail_leak_rate_fraction_per_second,
        "cpu_collision_fallback_detected": bool(cpu_collision_fallback_detected),
        "gpu_collider_unsupported": bool(gpu_collider_unsupported),
        "nan_count": nan_count,
        "non_physical_parameter_dependence": bool(non_physical_parameter_dependence),
        "pass_criteria": criteria,
        "fatal_error": fatal_error,
    }


def rank_followup_candidates(candidate_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    passed = [result for result in candidate_results if result.get("classification") == "PASS_SOURCE_HOLD"]
    passed.sort(
        key=lambda result: (
            -float(result.get("source_retention_fraction", 0.0)),
            int(result.get("outside_source_count", 999999)),
            int(result.get("spill_count", 999999)),
            int(result.get("below_table_count", 999999)),
            str(result.get("candidate_id", "")),
        )
    )
    best_for_s3 = [str(result["candidate_id"]) for result in passed]
    return {
        "best_for_s3": best_for_s3,
        "s2f1_status": "GO_NEXT" if best_for_s3 else "STOP_WITH_EVIDENCE",
        "reason": "at_least_one_c2a_candidate_passed" if best_for_s3 else "no_c2a_candidate_passed",
    }


def analyze_s2f4_native_mesh_isolation(
    candidate_results: Sequence[dict[str, Any]],
    *,
    expected_candidate_ids: Sequence[str] = (),
) -> dict[str, Any]:
    observed_candidate_ids = {str(result.get("candidate_id", "")) for result in candidate_results}
    missing_candidate_ids = [candidate_id for candidate_id in expected_candidate_ids if candidate_id not in observed_candidate_ids]
    passed = [result for result in candidate_results if result.get("classification") == "PASS_SOURCE_HOLD"]
    direct_native_passes = [
        result
        for result in passed
        if str(result.get("native_collision_route")) != "render_mesh_plus_proxy_collision"
        and bool(result.get("native_mesh_collision_enabled"))
        and not bool(result.get("proxy_collision_enabled"))
    ]
    proxy_wrapper_passes = [
        result
        for result in passed
        if str(result.get("native_collision_route")) == "render_mesh_plus_proxy_collision"
        or bool(result.get("proxy_collision_enabled"))
    ]
    if candidate_results and missing_candidate_ids:
        status = "INCOMPLETE_C4A_EVIDENCE"
        partition = "incomplete_c4a_runtime_results"
        reason = "s2f4_incomplete_candidate_results"
        promotable = []
    elif direct_native_passes:
        status = "NATIVE_BEAKER_FLUID_SAFE_COLLIDER_CANDIDATE_FOUND"
        partition = "native_mesh_direct_collider_candidate_passed"
        reason = "at_least_one_c4a_native_candidate_passed"
        promotable = [str(result["candidate_id"]) for result in direct_native_passes + proxy_wrapper_passes]
    elif proxy_wrapper_passes:
        status = "NATIVE_BEAKER_REQUIRES_PROXY_WRAPPER"
        partition = "native_render_mesh_plus_proxy_collision_passed"
        reason = "native_render_mesh_plus_proxy_collision_passed"
        promotable = [str(result["candidate_id"]) for result in proxy_wrapper_passes]
    elif candidate_results:
        status = "NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER"
        partition = "all_c4a_routes_failed"
        reason = "native_beaker_not_fluid_safe_collider"
        promotable = []
    else:
        status = "PENDING"
        partition = "pending_runtime"
        reason = "candidate_plan_written"
        promotable = []
    return {
        "native_beaker_fluid_safe_collider_status": status,
        "native_issue_partition": partition,
        "reason": reason,
        "best_for_s2f5": promotable,
        "direct_native_passes": [str(result["candidate_id"]) for result in direct_native_passes],
        "proxy_wrapper_passes": [str(result["candidate_id"]) for result in proxy_wrapper_passes],
        "expected_candidate_ids": list(expected_candidate_ids),
        "observed_candidate_ids": sorted(candidate_id for candidate_id in observed_candidate_ids if candidate_id),
        "missing_candidate_ids": missing_candidate_ids,
    }


def analyze_s2f2_diagnosis(candidate_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    passed = [result for result in candidate_results if result.get("classification") == "PASS_SOURCE_HOLD"]
    pass_groups = {str(result.get("variable_group")) for result in passed}
    baseline_hash_by_parent = {
        str(result.get("parent_candidate_id")): str(result.get("initial_particle_positions_hash"))
        for result in candidate_results
        if result.get("parent_candidate_id")
        and result.get("variable_group") == "baseline_repeat"
        and result.get("initial_particle_positions_hash")
    }
    velocity_hash_mismatch_candidates = [
        str(result.get("candidate_id"))
        for result in passed
        if result.get("variable_group") == "velocity_020"
        and result.get("parent_candidate_id")
        and result.get("initial_particle_positions_hash")
        and baseline_hash_by_parent.get(str(result.get("parent_candidate_id")))
        and str(result.get("initial_particle_positions_hash"))
        != baseline_hash_by_parent[str(result.get("parent_candidate_id"))]
    ]
    nonphysical_candidates = [
        result
        for result in candidate_results
        if result.get("classification") == "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE"
        or result.get("non_physical_parameter_dependence")
    ]
    root_cause_confidence = "DIRECT_DIAGNOSTIC"
    if "velocity_020" in pass_groups and velocity_hash_mismatch_candidates:
        conclusion = "VELOCITY_INITIAL_LAYOUT_COUPLED_SENSITIVITY"
        root_cause_confidence = "COUPLED_DIAGNOSTIC"
    elif "velocity_020" in pass_groups:
        conclusion = "INITIAL_RADIAL_VELOCITY_SENSITIVITY"
    elif "particle_contact" in pass_groups:
        conclusion = "PARTICLE_CONTACT_OFFSET_SENSITIVITY"
    elif "collider_contact_rest" in pass_groups:
        conclusion = "COLLIDER_CONTACT_REST_OFFSET_SENSITIVITY"
    elif "ccd_enabled" in pass_groups:
        conclusion = "CCD_TUNNELING_SENSITIVITY"
    elif nonphysical_candidates and not passed:
        conclusion = "NON_PHYSICAL_DAMPING_ONLY"
    elif candidate_results:
        conclusion = "RESIDUAL_PROXY_GEOMETRY_GAP_SUSPECTED"
    else:
        conclusion = "NO_RUNTIME_RESULTS"
    return {
        "conclusion": conclusion,
        "root_cause_confidence": root_cause_confidence,
        "valid_pass_candidates": [str(result["candidate_id"]) for result in passed],
        "velocity_pass_candidates_with_initial_hash_mismatch": velocity_hash_mismatch_candidates,
        "nonphysical_candidates": [str(result["candidate_id"]) for result in nonphysical_candidates],
        "tested_parent_candidates": sorted(
            {str(result.get("parent_candidate_id")) for result in candidate_results if result.get("parent_candidate_id")}
        ),
        "tested_variable_groups": sorted(
            {str(result.get("variable_group")) for result in candidate_results if result.get("variable_group")}
        ),
    }


def analyze_s2f2_initial_layout_hashes(candidate_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    parent_accumulator: dict[str, dict[str, Any]] = {}
    for result in candidate_results:
        parent_id = str(result.get("parent_candidate_id") or "UNKNOWN_PARENT")
        entry = parent_accumulator.setdefault(
            parent_id,
            {
                "variant_count": 0,
                "hashes": set(),
                "variable_groups_by_hash": {},
                "missing_hash_candidates": [],
                "spawn_position_pinned_values": [],
                "initial_source_counts": [],
            },
        )
        entry["variant_count"] += 1
        hash_value = result.get("initial_particle_positions_hash")
        if hash_value:
            hash_string = str(hash_value)
            entry["hashes"].add(hash_string)
            groups = entry["variable_groups_by_hash"].setdefault(hash_string, set())
            groups.add(str(result.get("variable_group") or "unknown"))
        else:
            entry["missing_hash_candidates"].append(str(result.get("candidate_id")))
        if result.get("spawn_position_pinned") is not None:
            entry["spawn_position_pinned_values"].append(bool(result.get("spawn_position_pinned")))
        initial_counts = result.get("initial_region_counts")
        if isinstance(initial_counts, dict) and "source_count" in initial_counts:
            entry["initial_source_counts"].append(int(initial_counts["source_count"]))

    parents: dict[str, dict[str, Any]] = {}
    for parent_id, entry in sorted(parent_accumulator.items()):
        hashes = sorted(entry["hashes"])
        parents[parent_id] = {
            "variant_count": entry["variant_count"],
            "hash_count": len(hashes),
            "unique_initial_particle_positions_hashes": hashes,
            "variable_groups_by_hash": {
                hash_value: sorted(groups) for hash_value, groups in sorted(entry["variable_groups_by_hash"].items())
            },
            "missing_hash_candidates": sorted(entry["missing_hash_candidates"]),
            "spawn_position_pinned_all": bool(entry["spawn_position_pinned_values"])
            and all(entry["spawn_position_pinned_values"]),
            "unique_initial_source_counts": sorted(set(entry["initial_source_counts"])),
        }

    return {
        "parents": parents,
        "parents_with_post_reset_hash_variation": [
            parent_id for parent_id, entry in parents.items() if entry["hash_count"] > 1
        ],
        "notes": [
            "spawn_position_pinned records authored particle placement pinning before runtime reset.",
            "initial_particle_positions_hash records post-reset/readback initial positions; contact-offset variants may still alter settling.",
        ],
    }


def near_pass_candidates_for_s2f2(candidate_results: Sequence[dict[str, Any]]) -> list[str]:
    near_pass = [
        result
        for result in candidate_results
        if result.get("classification") == "FAIL_CONTAINER_LEAK"
        and float(result.get("source_retention_fraction", 0.0)) >= 0.95
        and not result.get("cpu_collision_fallback_detected")
        and not result.get("gpu_collider_unsupported")
        and not result.get("non_physical_parameter_dependence")
        and int(result.get("nan_count", 0)) == 0
    ]
    near_pass.sort(
        key=lambda result: (
            -float(result.get("source_retention_fraction", 0.0)),
            int(result.get("outside_source_count", 999999)),
            int(result.get("spill_count", 999999)),
            int(result.get("below_table_count", 999999)),
            str(result.get("candidate_id", "")),
        )
    )
    return [str(result["candidate_id"]) for result in near_pass]


def scan_runtime_warnings(artifact_dir: Path) -> dict[str, Any]:
    patterns = {
        "cpu_fallback": ("cpu collision fallback", "cpu fallback"),
        "gpu_unsupported": ("gpu collider unsupported", "gpu unsupported"),
        "physx_error": ("[error] [omni.physx", "physx error"),
        "headless_window_warning": ("glfw initialization failed", "failed to open the default display"),
        "material_binding_scope_warning": ("material:binding", "outside the scope of the reference"),
        "sdf_warning": ("sdf warning", "sdf error", "sdf cooking error", "sdf cooking warning"),
    }
    counts = {key: 0 for key in patterns}
    examples: dict[str, list[dict[str, Any]]] = {key: [] for key in patterns}
    warning_line_count = 0
    source_files = {
        "server_stdout": artifact_dir / "server.stdout.txt",
        "server_stderr": artifact_dir / "server.stderr.txt",
    }
    for source_name, path in source_files.items():
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            line_lower = line.lower()
            if "warning" in line_lower or "error" in line_lower:
                warning_line_count += 1
            for key, terms in patterns.items():
                if any(term in line_lower for term in terms):
                    counts[key] += 1
                    if len(examples[key]) < 8:
                        examples[key].append(
                            {
                                "source": source_name,
                                "line": line_number,
                                "text": line[:500],
                            }
                        )
    blocking = bool(counts["cpu_fallback"] or counts["gpu_unsupported"] or counts["physx_error"] or counts["sdf_warning"])
    return {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_s2f1_runtime_warning_scan",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "blocking_runtime_warning_detected": blocking,
        "pattern_counts": counts,
        "pattern_examples": examples,
        "source_files": {key: str(path) for key, path in source_files.items()},
        "warning_line_count": warning_line_count,
        "notes": [
            "Artifact-level stdout/stderr warning scan is authoritative for S2F1 release review.",
            "SDF cooking warnings/errors are blocking because S2F3 can otherwise report a false collider result.",
            "Headless GLFW/display warnings are expected in no-window IsaacSim runs.",
        ],
    }


def _candidate_plan(candidates: Sequence[C2ProxyCandidate]) -> list[dict[str, Any]]:
    return [asdict(candidate) for candidate in candidates]


def _candidate_result_from_summary(summary: dict[str, Any], candidate: C2ProxyCandidate | None = None) -> dict[str, Any]:
    detail = summary["classification_detail"]
    evidence_files = dict(summary.get("evidence_files") or {})
    result = classify_followup_candidate(
        candidate_id=summary["variant"]["variant_id"],
        source_retention_fraction=float(detail["source_retention_fraction"]),
        particle_count_final_fraction=float(detail["particle_count_final_fraction"]),
        outside_source_count=int(detail["outside_source_count"]),
        target_count=int(detail["target_count"]),
        spill_count=int(detail["spill_count"]),
        below_table_count=int(detail["below_table_count"]),
        tail_leak_rate_fraction_per_second=float(detail["tail_leak_rate_fraction_per_second"]),
        cpu_collision_fallback_detected=bool(detail["cpu_collision_fallback_detected"]),
        gpu_collider_unsupported=bool(detail["gpu_collider_unsupported"]),
        nan_count=int(detail["nan_count"]),
        non_physical_parameter_dependence=bool(
            candidate.non_physical_parameter_dependence_risk if candidate is not None else False
        ),
        fatal_error=detail.get("fatal_error"),
    )
    result.update(
        {
            "parent_candidate_id": candidate.parent_candidate_id if candidate is not None else None,
            "phase": candidate.phase if candidate is not None else None,
            "variable_group": candidate.variable_group if candidate is not None else None,
            "s2f2_axis": candidate.variable_group if candidate is not None else None,
            "non_physical_parameter_dependence_risk": (
                candidate.non_physical_parameter_dependence_risk if candidate is not None else False
            ),
            "non_physical_parameter_dependence_reason": (
                "max_velocity_guardrail_candidate_not_promotable"
                if candidate is not None and candidate.non_physical_parameter_dependence_risk
                else None
            ),
            "artifact_dir": summary["artifact_dir"],
            "scene_path": summary["scene_path"],
            "variant_summary": str(Path(summary["artifact_dir"]) / "variant_summary.json"),
            "initial_particle_positions_hash": summary.get("initial_particle_positions_hash"),
            "final_particle_positions_hash": summary.get("final_particle_positions_hash"),
            "spawn_position_pinned": summary.get("spawn_position_pinned"),
            "initial_region_counts": summary.get("initial_region_counts"),
            "final_region_counts": summary.get("final_region_counts"),
            "particle_count": candidate.particle_count if candidate is not None else None,
            "particle_seed": candidate.particle_seed if candidate is not None else None,
            "native_source_path": candidate.native_source_path if candidate is not None else None,
            "native_mesh_source_path": candidate.native_mesh_source_path if candidate is not None else None,
            "native_reference_scope": candidate.native_reference_scope if candidate is not None else None,
            "native_material_binding_strategy": (
                candidate.native_material_binding_strategy if candidate is not None else None
            ),
            "native_material_binding_scope_closed": (
                candidate.native_material_binding_scope_closed if candidate is not None else None
            ),
            "native_pose_alignment": candidate.native_pose_alignment if candidate is not None else None,
            "native_collision_route": candidate.native_collision_route if candidate is not None else None,
            "native_mesh_collision_enabled": candidate.native_mesh_collision_enabled if candidate is not None else None,
            "proxy_collision_enabled": candidate.proxy_collision_enabled if candidate is not None else None,
            "readback_available": bool(summary.get("readback_available")),
            "evidence_files_complete": REQUIRED_VARIANT_EVIDENCE_FILES.issubset(evidence_files.keys())
            and all(Path(evidence_files[key]).exists() for key in REQUIRED_VARIANT_EVIDENCE_FILES),
        }
    )
    result["promotable_to_s2f5"] = (
        result["classification"] == "PASS_SOURCE_HOLD" and not result["non_physical_parameter_dependence"]
    )
    return result


def load_candidate_results_from_artifacts(
    artifact_dir: Path,
    *,
    candidates: Sequence[C2ProxyCandidate] | None = None,
) -> list[dict[str, Any]]:
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates or []}
    results: list[dict[str, Any]] = []
    unplanned: list[str] = []
    for summary_path in sorted(artifact_dir.glob("*/variant_summary.json")):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        variant_id = str(summary["variant"]["variant_id"])
        candidate = candidate_by_id.get(variant_id)
        if candidates is not None and candidate is None:
            unplanned.append(variant_id)
            continue
        result = _candidate_result_from_summary(summary, candidate=candidate)
        result["variant_summary"] = str(summary_path)
        results.append(result)
    if unplanned:
        raise ValueError(f"unplanned_variant_summaries:{','.join(sorted(unplanned))}")
    return results


def _load_existing_manifest(manifest_path: Path) -> dict[str, Any] | None:
    if not manifest_path.exists():
        return None
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _dedupe_commands(commands: Sequence[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for command in commands:
        if not command or command in seen:
            continue
        deduped.append(command)
        seen.add(command)
    return deduped


def _command_without_flag(command: str, flag: str) -> str:
    parts = command.split()
    return " ".join(part for part in parts if part != flag)


def _command_history(previous_manifest: dict[str, Any] | None, current_command: str) -> dict[str, list[str]]:
    previous_commands = []
    if previous_manifest:
        previous_commands = [str(command) for command in previous_manifest.get("commands", [])]

    current_kind = "runtime"
    if "--summarize-existing" in current_command:
        current_kind = "summary"
    elif "--plan-only" in current_command:
        current_kind = "plan"

    inferred_runtime_command = None
    if current_kind == "summary":
        inferred_runtime_command = _command_without_flag(current_command, "--summarize-existing")

    runtime_commands = _dedupe_commands(
        [
            *[command for command in previous_commands if "--summarize-existing" not in command and "--plan-only" not in command],
            inferred_runtime_command,
            current_command if current_kind == "runtime" else None,
        ]
    )
    plan_commands = _dedupe_commands(
        [
            *[command for command in previous_commands if "--plan-only" in command],
            current_command if current_kind == "plan" else None,
        ]
    )
    summary_commands = _dedupe_commands(
        [
            *[command for command in previous_commands if "--summarize-existing" in command],
            current_command if current_kind == "summary" else None,
        ]
    )
    return {
        "commands": [*runtime_commands, *plan_commands, *summary_commands],
        "runtime_commands": runtime_commands,
        "plan_commands": plan_commands,
        "summary_commands": summary_commands,
    }


def _runtime_warning_gate(runtime_warning_scan: dict[str, Any] | None, *, phase: str | None = None) -> dict[str, Any]:
    pattern_counts = runtime_warning_scan.get("pattern_counts", {}) if runtime_warning_scan else {}
    blocking_keys = ["cpu_fallback", "gpu_unsupported", "physx_error", "sdf_warning"]
    if phase == "S2F4_C4_NATIVE_MESH_ISOLATION":
        blocking_keys.append("material_binding_scope_warning")
    blocking_reasons = [
        key
        for key in blocking_keys
        if int(pattern_counts.get(key, 0) or 0) > 0
    ]
    if runtime_warning_scan and runtime_warning_scan.get("blocking_runtime_warning_detected") and not blocking_reasons:
        blocking_reasons.append("runtime_warning_scan_blocking_flag")
    blocking = bool(blocking_reasons)
    return {
        "required_blocking_runtime_warning_detected": False,
        "blocking_runtime_warning_detected": blocking,
        "blocking_warning_reasons": blocking_reasons,
        "passed": not blocking,
    }


def write_followup_manifest(
    manifest_path: Path,
    *,
    phase: str,
    parent_manifest: Path,
    baseline_freeze_manifest: Path,
    artifact_dir: Path,
    candidates: Sequence[C2ProxyCandidate],
    candidate_results: Sequence[dict[str, Any]],
    command: str,
    runtime_warning_scan: dict[str, Any] | None,
    fatal_error: dict[str, Any] | None = None,
    previous_manifest: dict[str, Any] | None = None,
    source_s2f1_manifest: Path | None = None,
) -> dict[str, Any]:
    ranking = rank_followup_candidates(candidate_results)
    near_pass_for_s2f2 = near_pass_candidates_for_s2f2(candidate_results)
    s2f5_review = None
    d4_wrapper_sweep = None
    d4_wrapper_promotion = None
    if phase == "S2F5_PROMOTION_REVIEW" and candidate_results:
        s2f5_review = aggregate_s2f5_promotion_review(
            candidate_results,
            promotion_candidate_id=_s2f5_promotion_candidate_id(
                candidate_results=candidate_results,
                candidates=candidates,
            ),
        )
    if phase == "D4_WRAPPER_SWEEP" and candidate_results:
        d4_wrapper_sweep = aggregate_d4_wrapper_sweep(
            candidate_results,
            expected_candidate_ids=[candidate.candidate_id for candidate in candidates],
        )
    if phase == "D4_WRAPPER_PROMOTION" and candidate_results:
        d4_wrapper_promotion = aggregate_d4_wrapper_promotion(
            candidate_results,
            promotion_candidate_id=_d4_promotion_candidate_id(
                candidate_results=candidate_results,
                candidates=candidates,
            ),
        )
    s2f2_diagnosis = (
        analyze_s2f2_diagnosis(candidate_results) if phase == "S2F2_VELOCITY_CONTACT_OFFSET" else None
    )
    s2f2_initial_layout_hash_audit = (
        analyze_s2f2_initial_layout_hashes(candidate_results)
        if phase == "S2F2_VELOCITY_CONTACT_OFFSET"
        else None
    )
    s2f4_analysis = (
        analyze_s2f4_native_mesh_isolation(
            candidate_results,
            expected_candidate_ids=[candidate.candidate_id for candidate in candidates],
        )
        if phase == "S2F4_C4_NATIVE_MESH_ISOLATION"
        else None
    )
    warning_gate = _runtime_warning_gate(runtime_warning_scan, phase=phase)
    if not warning_gate["passed"]:
        ranking = {
            "best_for_s3": [],
            "s2f1_status": "STOP_WITH_EVIDENCE",
            "reason": "blocking_runtime_warning_detected",
        }
        if s2f5_review is not None:
            s2f5_review = {
                **s2f5_review,
                "status": "STOP_WITH_EVIDENCE",
                "reason": "blocking_runtime_warning_detected",
                "best_for_s3": [],
            }
        if d4_wrapper_sweep is not None:
            d4_wrapper_sweep = {
                **d4_wrapper_sweep,
                "status": "STOP_WITH_EVIDENCE",
                "reason": "blocking_runtime_warning_detected",
                "best_for_promotion": [],
            }
        if d4_wrapper_promotion is not None:
            d4_wrapper_promotion = {
                **d4_wrapper_promotion,
                "status": "STOP_WITH_EVIDENCE",
                "reason": "blocking_runtime_warning_detected",
                "best_for_s3": [],
                "g1_physics_a": False,
            }
        if s2f4_analysis is not None:
            s2f4_analysis = {
                **s2f4_analysis,
                "best_for_s2f5": [],
                "runtime_warning_gate_blocked_promotion": True,
            }
    if not warning_gate["passed"]:
        status = "STOP_WITH_EVIDENCE"
    elif not candidate_results and fatal_error is None:
        status = "PLAN_READY"
    elif phase == "S2F5_PROMOTION_REVIEW" and s2f5_review is not None:
        status = s2f5_review["status"]
    elif phase == "D4_WRAPPER_PROMOTION" and d4_wrapper_promotion is not None:
        status = d4_wrapper_promotion["status"]
    elif phase == "D4_WRAPPER_SWEEP" and d4_wrapper_sweep is not None:
        status = d4_wrapper_sweep["status"] if d4_wrapper_sweep["status"] == "GO_NEXT" else (
            d4_wrapper_sweep["status"]
            if d4_wrapper_sweep["status"] in D4_MATRIX_STOP_CLASSIFICATIONS
            else ranking["s2f1_status"]
        )
    elif phase == "S2F4_C4_NATIVE_MESH_ISOLATION" and s2f4_analysis is not None:
        status = "GO_NEXT" if s2f4_analysis["best_for_s2f5"] else "STOP_WITH_EVIDENCE"
    else:
        status = ranking["s2f1_status"]
    if phase == "S2F5_PROMOTION_REVIEW" and s2f5_review is not None:
        passed_candidates = s2f5_review["best_for_s3"]
    elif phase == "D4_WRAPPER_PROMOTION" and d4_wrapper_promotion is not None:
        passed_candidates = d4_wrapper_promotion["best_for_s3"]
    elif phase == "D4_WRAPPER_SWEEP" and d4_wrapper_sweep is not None:
        passed_candidates = d4_wrapper_sweep["best_for_promotion"]
    elif phase == "S2F4_C4_NATIVE_MESH_ISOLATION" and s2f4_analysis is not None:
        passed_candidates = s2f4_analysis["best_for_s2f5"]
    else:
        passed_candidates = ranking["best_for_s3"]
    best_for_s2f5 = (
        passed_candidates
        if phase
        in {"S2F2_VELOCITY_CONTACT_OFFSET", "S2F3_C3_SDF_SWEEP", "S2F4_C4_NATIVE_MESH_ISOLATION"}
        else []
    )
    best_for_s3 = (
        []
        if phase
        in {"S2F2_VELOCITY_CONTACT_OFFSET", "S2F3_C3_SDF_SWEEP", "S2F4_C4_NATIVE_MESH_ISOLATION"}
        else passed_candidates
    )
    best_for_promotion = (
        d4_wrapper_sweep["best_for_promotion"]
        if phase == "D4_WRAPPER_SWEEP" and d4_wrapper_sweep is not None
        else ([] if phase != "D4_WRAPPER_PROMOTION" else passed_candidates)
    )
    s2f5_promotion_review_next = bool(
        phase
        in {"S2F2_VELOCITY_CONTACT_OFFSET", "S2F3_C3_SDF_SWEEP", "S2F4_C4_NATIVE_MESH_ISOLATION"}
        and status == "GO_NEXT"
        and best_for_s2f5
    )
    s2f5_promotion_review_complete = bool(
        phase == "S2F5_PROMOTION_REVIEW" and status == "GO_NEXT" and best_for_s3
    )
    s2f4_contract_complete = bool(
        phase != "S2F4_C4_NATIVE_MESH_ISOLATION"
        or (
            s2f4_analysis is not None
            and candidate_results
            and warning_gate["passed"]
            and not s2f4_analysis.get("missing_candidate_ids")
        )
    )
    requires_initial_layout_hash_stability_check = bool(
        s2f2_diagnosis and s2f2_diagnosis.get("root_cause_confidence") == "COUPLED_DIAGNOSTIC"
    )
    command_history = _command_history(previous_manifest, command)
    if best_for_s2f5:
        next_stage_id = "S2F5_PROMOTION_REVIEW"
        next_stage_variants = best_for_s2f5
        diagnostic_routes: list[str] = []
    elif phase == "D4_WRAPPER_SWEEP" and status == "GO_NEXT" and best_for_promotion:
        next_stage_id = "D4_WRAPPER_PROMOTION"
        next_stage_variants = best_for_promotion
        diagnostic_routes = []
    elif phase == "D4_WRAPPER_SWEEP" and status == "PLAN_READY":
        next_stage_id = "D4_WRAPPER_SWEEP"
        next_stage_variants = [candidate.candidate_id for candidate in candidates]
        diagnostic_routes = []
    elif phase == "D4_WRAPPER_SWEEP":
        next_stage_id = "D4_WRAPPER_SWEEP"
        next_stage_variants = near_pass_for_s2f2 or [candidate.candidate_id for candidate in candidates[:5]]
        diagnostic_routes = ["tighten_wrapper_geometry"]
    elif phase == "D4_WRAPPER_PROMOTION" and best_for_s3:
        next_stage_id = "VISUAL_A_OFFICIAL"
        next_stage_variants = best_for_s3
        diagnostic_routes = []
    elif phase == "D4_WRAPPER_PROMOTION" and status == "PLAN_READY":
        next_stage_id = "D4_WRAPPER_PROMOTION"
        next_stage_variants = [candidate.candidate_id for candidate in candidates]
        diagnostic_routes = []
    elif phase == "D4_WRAPPER_PROMOTION":
        next_stage_id = "D4_WRAPPER_PROMOTION"
        next_stage_variants = []
        diagnostic_routes = ["rerun_failed_d4_promotion_trials"]
    elif phase == "S2F5_PROMOTION_REVIEW" and best_for_s3:
        next_stage_id = "S3_KINEMATIC_POUR"
        next_stage_variants = best_for_s3
        diagnostic_routes = []
    elif phase == "S2F5_PROMOTION_REVIEW" and status == "PLAN_READY":
        next_stage_id = "S2F5_PROMOTION_REVIEW"
        next_stage_variants = [candidate.candidate_id for candidate in candidates]
        diagnostic_routes = []
    elif phase == "S2F5_PROMOTION_REVIEW":
        next_stage_id = "S2F3_C3_SDF_SWEEP"
        next_stage_variants = []
        diagnostic_routes = ["S2F3_C3_SDF_SWEEP", "S2F4_C4_NATIVE_MESH_ISOLATION"]
    elif phase == "S2F3_C3_SDF_SWEEP" and status == "PLAN_READY":
        next_stage_id = "S2F3_C3_SDF_SWEEP"
        next_stage_variants = [candidate.candidate_id for candidate in candidates]
        diagnostic_routes = []
    elif phase == "S2F3_C3_SDF_SWEEP":
        next_stage_id = "S2F4_C4_NATIVE_MESH_ISOLATION"
        next_stage_variants = []
        diagnostic_routes = ["S2F4_C4_NATIVE_MESH_ISOLATION"]
    elif phase == "S2F4_C4_NATIVE_MESH_ISOLATION" and status == "PLAN_READY":
        next_stage_id = "S2F4_C4_NATIVE_MESH_ISOLATION"
        next_stage_variants = [candidate.candidate_id for candidate in candidates]
        diagnostic_routes = []
    elif phase == "S2F4_C4_NATIVE_MESH_ISOLATION" and not warning_gate["passed"]:
        next_stage_id = "S2F4_C4_NATIVE_MESH_ISOLATION"
        next_stage_variants = [candidate.candidate_id for candidate in candidates]
        diagnostic_routes = []
    elif (
        phase == "S2F4_C4_NATIVE_MESH_ISOLATION"
        and s2f4_analysis is not None
        and s2f4_analysis["native_beaker_fluid_safe_collider_status"] == "INCOMPLETE_C4A_EVIDENCE"
    ):
        next_stage_id = "S2F4_C4_NATIVE_MESH_ISOLATION"
        next_stage_variants = s2f4_analysis["missing_candidate_ids"]
        diagnostic_routes = []
    elif phase == "S2F4_C4_NATIVE_MESH_ISOLATION":
        next_stage_id = "S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP"
        next_stage_variants = []
        diagnostic_routes = []
    elif phase == "S2F2_VELOCITY_CONTACT_OFFSET":
        next_stage_id = "S2F3_C3_SDF_SWEEP"
        next_stage_variants = near_pass_for_s2f2
        diagnostic_routes = ["S2F3_C3_SDF_SWEEP", "S2F4_C4_NATIVE_MESH_ISOLATION"]
    else:
        next_stage_id = "S2F2_VELOCITY_CONTACT_OFFSET"
        next_stage_variants = near_pass_for_s2f2
        diagnostic_routes = []
    if status == "PLAN_READY":
        reason = "candidate_plan_written"
    elif not warning_gate["passed"]:
        reason = "blocking_runtime_warning_detected"
    elif d4_wrapper_promotion is not None:
        reason = d4_wrapper_promotion["reason"]
    elif d4_wrapper_sweep is not None:
        reason = d4_wrapper_sweep["reason"]
    elif s2f5_review is not None:
        reason = s2f5_review["reason"]
    elif phase == "S2F4_C4_NATIVE_MESH_ISOLATION" and s2f4_analysis is not None:
        reason = s2f4_analysis["reason"]
    elif phase == "S2F3_C3_SDF_SWEEP" and status == "GO_NEXT":
        reason = "at_least_one_c3a_sdf_candidate_passed"
    elif phase == "S2F3_C3_SDF_SWEEP":
        reason = "no_c3a_sdf_candidate_passed"
    else:
        reason = ranking["reason"]
    if phase == "S2F4_C4_NATIVE_MESH_ISOLATION" and s2f4_analysis is not None:
        if not warning_gate["passed"]:
            allowed_claims = [
                "S2F4 observed a blocking runtime warning and did not promote any native beaker route."
            ]
        elif s2f4_analysis["native_beaker_fluid_safe_collider_status"] == "NATIVE_BEAKER_REQUIRES_PROXY_WRAPPER":
            allowed_claims = [
                "S2F4 found a native render mesh plus proxy collision route for S2F5 review."
            ]
        elif s2f4_analysis["native_beaker_fluid_safe_collider_status"] == (
            "NATIVE_BEAKER_FLUID_SAFE_COLLIDER_CANDIDATE_FOUND"
        ):
            allowed_claims = [
                "S2F4 found at least one scope-closed native beaker collider candidate for S2F5 review.",
                "S2F4 PASS routes to S2F5 promotion review, not directly to S3.",
            ]
        elif status == "PLAN_READY":
            allowed_claims = ["S2F4 native mesh isolation candidate plan is ready before runtime launch."]
        elif s2f4_analysis["native_beaker_fluid_safe_collider_status"] == "INCOMPLETE_C4A_EVIDENCE":
            allowed_claims = [
                "S2F4 has partial C4A runtime evidence and must rerun missing candidates before a native beaker conclusion."
            ]
        else:
            allowed_claims = [
                "S2F4 completed native beaker mesh isolation and did not find a fluid-safe native collider candidate."
            ]
    else:
        allowed_claims = [
            (
                "S2F2 velocity/contact-offset isolation candidate set is bounded and recorded."
                if phase == "S2F2_VELOCITY_CONTACT_OFFSET"
                else (
                    "S2F3 C3 SDF cooking sweep candidate grid is bounded and recorded."
                    if phase == "S2F3_C3_SDF_SWEEP"
                    else (
                        "S2F5 promotion review candidate grid is bounded and recorded."
                        if phase == "S2F5_PROMOTION_REVIEW"
                        else "S2F1 C2 proxy sweep candidate set is bounded and recorded."
                    )
                )
            ),
            (
                "S2F2 ran only C2A_005/C2A_009/C2A_007 near-pass derived variants in standalone IsaacSim41."
                if phase == "S2F2_VELOCITY_CONTACT_OFFSET" and candidate_results
                else (
                    (
                        "S2F3 ran only C3A SDF open-beaker collider variants in standalone IsaacSim41."
                        if phase == "S2F3_C3_SDF_SWEEP"
                        else (
                            "S2F5 ran only C2A_009_S2F2_VEL020 promotion-review trials in standalone IsaacSim41."
                            if phase == "S2F5_PROMOTION_REVIEW"
                            else "S2F1 ran C2-derived proxy collider variants in standalone IsaacSim41."
                        )
                    )
                    if candidate_results
                    else f"{phase} candidate plan is ready before runtime launch."
                )
            ),
        ]
    blocked_claims = [
        "S3 kinematic pour is released",
        "level1_pour has true fluid today",
        "fluid is EBench-scoreable",
        "policy score claim",
        "official leaderboard claim",
        "diagnostic projections equal product-quality render",
    ]
    if phase == "S2F4_C4_NATIVE_MESH_ISOLATION":
        blocked_claims.append("native beaker mesh itself is fluid-safe")
    manifest = {
        "schema_version": 1,
        "manifest_type": (
            "true_physx_pbd_fluid_spike_s2f2_velocity_contact_offset"
            if phase == "S2F2_VELOCITY_CONTACT_OFFSET"
            else (
                "true_physx_pbd_fluid_spike_s2f3_c3_sdf_sweep"
                if phase == "S2F3_C3_SDF_SWEEP"
                else (
                    "true_physx_pbd_fluid_spike_s2f4_c4_native_mesh_isolation"
                    if phase == "S2F4_C4_NATIVE_MESH_ISOLATION"
                    else (
                        "true_physx_pbd_fluid_spike_s2f5_promotion_review"
                        if phase == "S2F5_PROMOTION_REVIEW"
                        else (
                            "true_physx_pbd_fluid_spike_d4_wrapper_promotion"
                            if phase == "D4_WRAPPER_PROMOTION"
                            else (
                                "true_physx_pbd_fluid_spike_d4_wrapper_sweep"
                                if phase == "D4_WRAPPER_SWEEP"
                                else "true_physx_pbd_fluid_spike_s2f1_c2_proxy_sweep"
                            )
                        )
                    )
                )
            )
        ),
        "stage": phase,
        "status": status,
        "reason": reason,
        "run_id": artifact_dir.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_version": FOLLOWUP_CONTRACT_VERSION,
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "parent_s2_manifest": str(parent_manifest),
        "baseline_freeze_manifest": str(baseline_freeze_manifest),
        "source_s2f1_manifest": str(source_s2f1_manifest) if source_s2f1_manifest is not None else None,
        "artifact_dir": str(artifact_dir),
        "commands": command_history["commands"],
        "runtime_commands": command_history["runtime_commands"],
        "plan_commands": command_history["plan_commands"],
        "summary_commands": command_history["summary_commands"],
        "target_runtime": {
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "accept_eula": os.environ.get("ACCEPT_EULA"),
            "omni_kit_accept_eula": os.environ.get("OMNI_KIT_ACCEPT_EULA"),
            "gpu_probe": _gpu_probe(),
        },
        "phase_specs": followup_phase_specs(
            phase=phase,
            status=status,
            best_for_s2f5=best_for_s2f5,
            best_for_s3=best_for_s3,
            s2f4_contract_complete=s2f4_contract_complete,
        ),
        "candidate_plan": _candidate_plan(candidates),
        "candidate_count": len(candidates),
        "candidate_results": list(candidate_results),
        "best_for_s3": best_for_s3,
        "best_for_s2f5": best_for_s2f5,
        "near_pass_for_s2f2": near_pass_for_s2f2,
        "s2f2_diagnosis": s2f2_diagnosis,
        "s2f2_root_cause_classification": s2f2_diagnosis["conclusion"] if s2f2_diagnosis else None,
        "s2f2_initial_layout_hash_audit": s2f2_initial_layout_hash_audit,
        "s2f5_promotion_review_next": s2f5_promotion_review_next,
        "s2f5_promotion_review_complete": s2f5_promotion_review_complete,
        "s2f5_promotion_review": s2f5_review,
        "d4_wrapper_sweep": d4_wrapper_sweep,
        "d4_wrapper_promotion": d4_wrapper_promotion,
        "best_for_promotion": best_for_promotion,
        "g1_physics_a": bool(
            phase == "D4_WRAPPER_PROMOTION"
            and d4_wrapper_promotion is not None
            and d4_wrapper_promotion.get("g1_physics_a")
        ),
        "s2f4_native_mesh_isolation": s2f4_analysis,
        "native_beaker_fluid_safe_collider_status": (
            s2f4_analysis["native_beaker_fluid_safe_collider_status"] if s2f4_analysis else None
        ),
        "native_issue_partition": s2f4_analysis["native_issue_partition"] if s2f4_analysis else None,
        "s3_kinematic_pour_released": bool(
            phase == "S2F5_PROMOTION_REVIEW" and status == "GO_NEXT" and best_for_s3
        ),
        "physics_a_g1_released": bool(
            phase == "D4_WRAPPER_PROMOTION"
            and status == "GO_NEXT"
            and d4_wrapper_promotion is not None
            and d4_wrapper_promotion.get("g1_physics_a")
        ),
        "runtime_warning_scan": runtime_warning_scan,
        "runtime_warning_gate": warning_gate,
        "pass_criteria": {
            "required_source_retention_fraction": 0.95,
            "required_particle_count_final_fraction": 0.95,
            "required_outside_source_count": 0,
            "required_target_count": 0,
            "required_spill_count": 0,
            "required_below_table_count": 0,
            "required_tail_leak_rate_fraction_per_second_lt": 0.02,
            "required_cpu_collision_fallback_detected": False,
            "required_gpu_collider_unsupported": False,
            "required_nan_count": 0,
            "required_non_physical_parameter_dependence": False,
            "required_blocking_runtime_warning_detected": False,
        },
        "allowed_claims": allowed_claims,
        "blocked_claims": blocked_claims,
        "next_stage": {
            "id": next_stage_id,
            "variants": next_stage_variants,
            "diagnostic_routes": diagnostic_routes,
            "not_s3_release": next_stage_id != "S3_KINEMATIC_POUR",
            "requires_initial_layout_hash_stability_check": requires_initial_layout_hash_stability_check,
            "promotion_caveat": (
                "COUPLED_DIAGNOSTIC_REQUIRES_INITIAL_LAYOUT_RETEST"
                if requires_initial_layout_hash_stability_check
                else None
            ),
        },
        "fatal_error": fatal_error,
    }
    if runtime_warning_scan is not None:
        _write_json(artifact_dir / "runtime_warning_scan.json", runtime_warning_scan)
    _write_json(manifest_path, manifest)
    return manifest


def _run_c2_proxy_sweep(
    *,
    candidates: Sequence[C2ProxyCandidate],
    base_config: ColliderConfig,
    artifact_dir: Path,
    scene_dir: Path,
    native_usd: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        config = candidate.to_config(base=base_config)
        spec = candidate.to_variant_spec()
        scene_path = scene_dir / f"{candidate.candidate_id.lower()}_{spec.name}.usda"
        try:
            summary = _run_variant(
                config=config,
                spec=spec,
                artifact_dir=artifact_dir,
                scene_path=scene_path,
                native_usd=native_usd,
            )
            result = _candidate_result_from_summary(summary, candidate=candidate)
        except Exception as exc:
            fatal_error = {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback_tail": traceback.format_exc()[-6000:],
            }
            candidate_dir = artifact_dir / candidate.candidate_id
            candidate_dir.mkdir(parents=True, exist_ok=True)
            result = classify_followup_candidate(
                candidate_id=candidate.candidate_id,
                source_retention_fraction=0.0,
                particle_count_final_fraction=0.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=999.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=candidate.non_physical_parameter_dependence_risk,
                fatal_error=fatal_error,
            )
            result.update(
                {
                    "parent_candidate_id": candidate.parent_candidate_id,
                    "phase": candidate.phase,
                    "variable_group": candidate.variable_group,
                    "non_physical_parameter_dependence_risk": candidate.non_physical_parameter_dependence_risk,
                    "artifact_dir": str(candidate_dir),
                    "scene_path": str(scene_path),
                    "variant_summary": str(candidate_dir / "variant_summary.json"),
                    "particle_count": candidate.particle_count,
                    "particle_seed": candidate.particle_seed,
                    "native_source_path": candidate.native_source_path,
                    "native_mesh_source_path": candidate.native_mesh_source_path,
                    "native_reference_scope": candidate.native_reference_scope,
                    "native_material_binding_strategy": candidate.native_material_binding_strategy,
                    "native_material_binding_scope_closed": candidate.native_material_binding_scope_closed,
                    "native_pose_alignment": candidate.native_pose_alignment,
                    "native_collision_route": candidate.native_collision_route,
                    "native_mesh_collision_enabled": candidate.native_mesh_collision_enabled,
                    "proxy_collision_enabled": candidate.proxy_collision_enabled,
                    "readback_available": False,
                    "evidence_files_complete": False,
                }
            )
            _write_json(candidate_dir / "variant_summary.json", result)
        results.append(result)
    return results


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="S2F1_C2_PROXY_SWEEP")
    parser.add_argument("--parent-manifest", default=DEFAULT_PARENT_MANIFEST)
    parser.add_argument("--baseline-freeze-manifest", default=DEFAULT_BASELINE_FREEZE_MANIFEST)
    parser.add_argument("--s2f1-manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--scene-dir", default=DEFAULT_SCENE_DIR)
    parser.add_argument("--native-usd", default=DEFAULT_NATIVE_USD)
    parser.add_argument("--candidate-limit", type=int, default=None)
    parser.add_argument("--promotion-candidate-id", default=None)
    parser.add_argument("--particle-count", type=int, default=ColliderConfig.particle_count)
    parser.add_argument("--steps", type=int, default=ColliderConfig.steps)
    parser.add_argument("--width", type=int, default=ColliderConfig.render_width)
    parser.add_argument("--height", type=int, default=ColliderConfig.render_height)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.phase not in {
        "S2F1_C2_PROXY_SWEEP",
        "S2F2_VELOCITY_CONTACT_OFFSET",
        "S2F3_C3_SDF_SWEEP",
        "S2F4_C4_NATIVE_MESH_ISOLATION",
        "S2F5_PROMOTION_REVIEW",
        "D4_WRAPPER_SWEEP",
        "D4_WRAPPER_PROMOTION",
    }:
        raise SystemExit(f"unsupported phase for this runner: {args.phase}")

    if args.phase == "S2F2_VELOCITY_CONTACT_OFFSET":
        if args.artifact_dir == DEFAULT_ARTIFACT_DIR:
            args.artifact_dir = DEFAULT_S2F2_ARTIFACT_DIR
        if args.manifest_path == DEFAULT_MANIFEST_PATH:
            args.manifest_path = DEFAULT_S2F2_MANIFEST_PATH
        if args.scene_dir == DEFAULT_SCENE_DIR:
            args.scene_dir = DEFAULT_S2F2_SCENE_DIR
        candidates = build_velocity_contact_offset_sweep(
            s2f1_manifest_path=Path(args.s2f1_manifest),
            limit=args.candidate_limit,
        )
    elif args.phase == "S2F3_C3_SDF_SWEEP":
        if args.artifact_dir == DEFAULT_ARTIFACT_DIR:
            args.artifact_dir = DEFAULT_S2F3_ARTIFACT_DIR
        if args.manifest_path == DEFAULT_MANIFEST_PATH:
            args.manifest_path = DEFAULT_S2F3_MANIFEST_PATH
        if args.scene_dir == DEFAULT_SCENE_DIR:
            args.scene_dir = DEFAULT_S2F3_SCENE_DIR
        if args.s2f1_manifest == DEFAULT_MANIFEST_PATH:
            args.s2f1_manifest = DEFAULT_S2F3_SOURCE_MANIFEST
        candidates = build_s2f3_sdf_sweep(limit=args.candidate_limit)
    elif args.phase == "S2F4_C4_NATIVE_MESH_ISOLATION":
        if args.candidate_limit is not None:
            raise SystemExit("S2F4_C4_NATIVE_MESH_ISOLATION does not support --candidate-limit")
        if args.artifact_dir == DEFAULT_ARTIFACT_DIR:
            args.artifact_dir = DEFAULT_S2F4_ARTIFACT_DIR
        if args.manifest_path == DEFAULT_MANIFEST_PATH:
            args.manifest_path = DEFAULT_S2F4_MANIFEST_PATH
        if args.scene_dir == DEFAULT_SCENE_DIR:
            args.scene_dir = DEFAULT_S2F4_SCENE_DIR
        if args.s2f1_manifest == DEFAULT_MANIFEST_PATH:
            args.s2f1_manifest = DEFAULT_S2F4_SOURCE_MANIFEST
        candidates = build_s2f4_native_mesh_isolation()
    elif args.phase == "S2F5_PROMOTION_REVIEW":
        if args.candidate_limit is not None:
            raise SystemExit("S2F5_PROMOTION_REVIEW does not support --candidate-limit")
        if args.artifact_dir == DEFAULT_ARTIFACT_DIR:
            args.artifact_dir = DEFAULT_S2F5_ARTIFACT_DIR
        if args.manifest_path == DEFAULT_MANIFEST_PATH:
            args.manifest_path = DEFAULT_S2F5_MANIFEST_PATH
        if args.scene_dir == DEFAULT_SCENE_DIR:
            args.scene_dir = DEFAULT_S2F5_SCENE_DIR
        if args.s2f1_manifest == DEFAULT_MANIFEST_PATH:
            args.s2f1_manifest = DEFAULT_S2F5_SOURCE_MANIFEST
        candidates = build_s2f5_promotion_review_sweep(
            s2f2_manifest_path=Path(args.s2f1_manifest),
        )
    elif args.phase == "D4_WRAPPER_SWEEP":
        if args.artifact_dir == DEFAULT_ARTIFACT_DIR:
            args.artifact_dir = DEFAULT_D4_ARTIFACT_DIR
        if args.manifest_path == DEFAULT_MANIFEST_PATH:
            args.manifest_path = DEFAULT_D4_MANIFEST_PATH
        if args.scene_dir == DEFAULT_SCENE_DIR:
            args.scene_dir = DEFAULT_D4_SCENE_DIR
        candidates = build_d4_wrapper_sweep(limit=args.candidate_limit)
    elif args.phase == "D4_WRAPPER_PROMOTION":
        if args.candidate_limit is not None:
            raise SystemExit("D4_WRAPPER_PROMOTION does not support --candidate-limit")
        if args.artifact_dir == DEFAULT_ARTIFACT_DIR:
            args.artifact_dir = DEFAULT_D4_PROMOTION_ARTIFACT_DIR
        if args.manifest_path == DEFAULT_MANIFEST_PATH:
            args.manifest_path = DEFAULT_D4_PROMOTION_MANIFEST_PATH
        if args.scene_dir == DEFAULT_SCENE_DIR:
            args.scene_dir = DEFAULT_D4_PROMOTION_SCENE_DIR
        if args.s2f1_manifest == DEFAULT_MANIFEST_PATH:
            args.s2f1_manifest = DEFAULT_D4_PROMOTION_SOURCE_MANIFEST
        candidates = build_d4_wrapper_promotion_sweep(
            d4_manifest_path=Path(args.s2f1_manifest),
            promotion_candidate_id=args.promotion_candidate_id or D4_PROMOTION_CANDIDATE_ID,
        )
    else:
        candidates = build_c2_proxy_sweep(limit=args.candidate_limit or 12)
    base_config = ColliderConfig(
        particle_count=args.particle_count,
        steps=args.steps,
        render_width=args.width,
        render_height=args.height,
    )
    artifact_dir = Path(args.artifact_dir)
    scene_dir = Path(args.scene_dir)
    manifest_path = Path(args.manifest_path)
    parent_manifest = Path(args.parent_manifest)
    baseline_freeze_manifest = Path(args.baseline_freeze_manifest)
    source_s2f1_manifest = (
        Path(args.s2f1_manifest)
        if args.phase
        in {
            "S2F2_VELOCITY_CONTACT_OFFSET",
            "S2F3_C3_SDF_SWEEP",
            "S2F4_C4_NATIVE_MESH_ISOLATION",
            "S2F5_PROMOTION_REVIEW",
            "D4_WRAPPER_PROMOTION",
        }
        else None
    )
    native_usd = Path(args.native_usd).resolve()
    command = " ".join([sys.executable, Path(__file__).as_posix(), *argv])
    previous_manifest = _load_existing_manifest(manifest_path)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)
    if not args.summarize_existing:
        write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=[],
            command=command,
            runtime_warning_scan=None,
            previous_manifest=previous_manifest,
            source_s2f1_manifest=source_s2f1_manifest,
    )
    if args.plan_only:
        print(f"{args.phase} candidate plan manifest={manifest_path}", flush=True)
        return 0
    if args.summarize_existing:
        candidate_results = load_candidate_results_from_artifacts(artifact_dir, candidates=candidates)
        manifest = write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=candidate_results,
            command=command,
            runtime_warning_scan=scan_runtime_warnings(artifact_dir),
            previous_manifest=previous_manifest,
            source_s2f1_manifest=source_s2f1_manifest,
        )
        promotion_field = (
            f"best_for_s2f5={manifest['best_for_s2f5']}"
            if args.phase in {"S2F2_VELOCITY_CONTACT_OFFSET", "S2F4_C4_NATIVE_MESH_ISOLATION"}
            else f"best_for_s3={manifest['best_for_s3']}"
        )
        print(
            f"{args.phase} summary "
            f"status={manifest['status']} {promotion_field} best_for_s3={manifest['best_for_s3']} "
            f"manifest={manifest_path}",
            flush=True,
        )
        return 0

    app = None
    fatal_error = None
    candidate_results: list[dict[str, Any]] = []
    final_manifest: dict[str, Any] | None = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": bool(args.headless), "width": args.width, "height": args.height})
        candidate_results = _run_c2_proxy_sweep(
            candidates=candidates,
            base_config=base_config,
            artifact_dir=artifact_dir,
            scene_dir=scene_dir,
            native_usd=native_usd,
        )
        final_manifest = write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=candidate_results,
            command=command,
            runtime_warning_scan=scan_runtime_warnings(artifact_dir),
            previous_manifest=_load_existing_manifest(manifest_path),
            source_s2f1_manifest=source_s2f1_manifest,
        )
        promotion_field = (
            f"best_for_s2f5={final_manifest['best_for_s2f5']}"
            if args.phase in {"S2F2_VELOCITY_CONTACT_OFFSET", "S2F4_C4_NATIVE_MESH_ISOLATION"}
            else f"best_for_s3={final_manifest['best_for_s3']}"
        )
        print(
            f"{args.phase} "
            f"status={final_manifest['status']} {promotion_field} best_for_s3={final_manifest['best_for_s3']} "
            f"manifest={manifest_path}",
            flush=True,
        )
    except Exception as exc:
        fatal_error = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc()[-6000:],
        }
    finally:
        if app is not None:
            app.close()

    if final_manifest is None:
        write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=candidate_results,
            command=command,
            runtime_warning_scan=scan_runtime_warnings(artifact_dir),
            fatal_error=fatal_error,
            previous_manifest=_load_existing_manifest(manifest_path),
            source_s2f1_manifest=source_s2f1_manifest,
        )
    return 0 if fatal_error is None else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

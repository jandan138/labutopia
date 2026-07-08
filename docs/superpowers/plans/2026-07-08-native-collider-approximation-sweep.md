# Native Collider Approximation Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible Native Collider Approximation Sweep for the colleague-provided LabUtopia `lab_001_level1_pour_tabletop_with_liquid.usd`, testing Isaac/PhysX built-in mesh collider approximations before designing any custom beaker collider.

**Architecture:** Add a focused full-native runner that opens the actual colleague USD scene, mutates only the `/World/beaker2/mesh` collision contract through an evidence overlay/export, and reuses the completed-PBD particle/readback flow from the existing native USD step-video runner. The contract includes built-in `MeshCollisionAPI` approximation, contact/rest offsets, SDF parameters where relevant, and non-RAW rigid-body/kinematic disabling. The sweep does not introduce a custom wrapper collider or proxy scene. It writes one manifest with explicit `allowed_claims` and `blocked_claims`; it can promote only static-hold candidates and cannot claim benchmark readiness, visual parity, or successful pouring.

**Tech Stack:** Python 3.10, pytest, Pixar USD/PXR, Isaac Sim 4.1, PhysX/PBD particles, existing `tools/labutopia_fluid` runners and `docs/labutopia_lab_poc` evidence manifests.

---

## Execution Result (2026-07-08)

The sweep has now been executed end-to-end under the target IsaacSim41 runtime. It tested the full colleague native USD scene and mutated only `/World/beaker2/mesh` collider contract. No custom wrapper collider was introduced.

Runtime scope:

```text
source_usd=outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd
mesh_path=/World/beaker2/mesh
runtime=IsaacSim41 headless
particle_source=/World/ParticleSet
selected_particle_count=512
steps=120
trace_interval=10
video_stride=10
```

Aggregate result:

```text
runtime_step_executed_count=10
static_hold_pass_count=0
promotable_variant_ids=[]
missing_result_paths=[]
all_tested_candidates_failed_static_hold=true
```

Variant results:

| Variant | Classification | Source retention | Outside | Spill | Below table |
|---|---|---:|---:|---:|---:|
| `RAW_AS_IS` | `FAIL_CONTAINER_LEAK` | `0.8027` | `101` | `11` | `90` |
| `NATIVE_NONE` | `FAIL_CONTAINER_LEAK` | `0.3770` | `319` | `0` | `319` |
| `NATIVE_MESH_SIMPLIFICATION` | `FAIL_CONTAINER_LEAK` | `0.3750` | `320` | `0` | `320` |
| `NATIVE_CONVEX_HULL` | `FAIL_CONTAINER_LEAK` | `0.0918` | `465` | `131` | `334` |
| `NATIVE_CONVEX_DECOMPOSITION` | `FAIL_CONTAINER_LEAK` | `0.6582` | `175` | `11` | `164` |
| `NATIVE_SDF_64` | `FAIL_CONTAINER_LEAK` | `0.3809` | `317` | `0` | `317` |
| `NATIVE_SDF_128` | `FAIL_CONTAINER_LEAK` | `0.3535` | `331` | `1` | `330` |
| `NATIVE_SDF_256` | `FAIL_CONTAINER_LEAK` | `0.3887` | `313` | `2` | `311` |
| `NATIVE_BOUNDING_CUBE` | `FAIL_CONTAINER_LEAK` | `0.0273` | `498` | `193` | `305` |
| `NATIVE_BOUNDING_SPHERE` | `FAIL_CONTAINER_LEAK` | `0.0078` | `508` | `178` | `330` |

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_runtime_sweep_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001/
```

Product conclusion: built-in/native Isaac/PhysX collider approximation modes have been tested before custom wrapper design. They all ran, but none produced a static zero-leak `fluid-safe container`. The next stage should proceed to a controlled invisible `fluid-safe wrapper collider` while keeping the LabUtopia native beaker as the visual asset.

Implementation note: direct `SetActive(false)` on the original incomplete `/World/fluid`, `/World/ParticleSet`, and `/World/ParticleSystem` can crash Kit/PhysX with an expired prim during update. The runner now keeps those prims active but hidden/disabled, then authors `/World/CompletedPBD/*` for runtime step/readback.

Status note: the checklist below is the original implementation recipe. The execution result above and the current source files are authoritative for completed status and final gate logic.

## File Structure

- Create: `tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py`
  - Owns candidate enumeration, native mesh collision-state audit, MeshCollisionAPI authoring, dry-run overlay export, optional runtime orchestration, and aggregate manifest writing.
- Create: `tests/test_fluid_colleague_native_collider_approx_sweep.py`
  - Covers candidate list, claim boundaries, static-hold gate, USD authoring, dry-run artifact shape, and proxy-route exclusion.
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
  - Add optional native collider approximation arguments and call the new helper before completed-PBD particles are authored.
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
  - Add a product-facing section after S2F4 explaining why this native approximation sweep exists and what it can/cannot prove.
- Modify: `reports/2026-07-07-labutopia-fluid-weekly/index.html`
  - Update the fluid weekly "next step" language so PMs see native approximation sweep before custom wrapper design.
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md` if present or add a small note in `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
  - Register the new evidence manifest family.

## Candidate Scope

The sweep includes only built-in/native approximation modes applied to the same native visual mesh path:

```text
RAW_AS_IS
NATIVE_NONE
NATIVE_MESH_SIMPLIFICATION
NATIVE_CONVEX_HULL
NATIVE_CONVEX_DECOMPOSITION
NATIVE_SDF_64
NATIVE_SDF_128
NATIVE_SDF_256
NATIVE_BOUNDING_CUBE
NATIVE_BOUNDING_SPHERE
```

`native_render_mesh_plus_proxy_collision` is excluded because it is a proxy/wrapper route, not a native approximation route.

## Claim Boundary

Allowed claims:

```text
We tested built-in/native Isaac/PhysX mesh collision approximation modes before custom wrapper design.
The test used the full colleague native USD scene, completed-PBD runtime particles, and particle readback.
If all candidates fail, the tested native approximation modes did not produce a fluid-safe native beaker collider under this IsaacSim41/PBD setup.
If one candidate passes smoke, it is only a static-hold candidate for promotion review.
```

Blocked claims:

```text
level1_pour is benchmark-ready with true fluid.
Raw colleague 50k USD directly steps as true PBD fluid without runtime completion.
Render/video appearance alone proves physics correctness.
Native beaker mesh is generally fluid-safe.
S3 kinematic pour, S4 replay, EBench score, policy score, or leaderboard readiness is released.
```

## Static-Hold Gate

Smoke pass requires all fields:

```text
runtime_step_executed == true
readback_available == true
readback_position_changed == true
particle_count_final_fraction >= 0.95
source_retention_fraction >= 0.95
outside_source_count == 0
target_count == 0
spill_count == 0
below_table_count == 0
tail_leak_rate_fraction_per_second < 0.02
cpu_collision_fallback_detected == false
gpu_collider_unsupported == false
nan_count == 0
fatal_error is null
```

`NATIVE_NONE`, `NATIVE_BOUNDING_CUBE`, and `NATIVE_BOUNDING_SPHERE` are diagnostic or negative-control routes and are never promotable even if a smoke run appears numerically stable.

### Task 1: Add Native Sweep Tests First

**Files:**
- Create: `tests/test_fluid_colleague_native_collider_approx_sweep.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fluid_colleague_native_collider_approx_sweep.py`:

```python
from types import SimpleNamespace

import pytest

from tools.labutopia_fluid.run_colleague_native_collider_approx_sweep import (
    DEFAULT_NATIVE_MESH_PATH,
    NEVER_PROMOTABLE_VARIANT_IDS,
    apply_native_collider_approximation,
    build_claim_boundary,
    build_native_approximation_sweep,
    classify_native_approximation_summary,
    summarize_native_mesh_collision_state,
    write_dry_run_authoring_artifacts,
)


def test_native_sweep_declares_builtin_modes_and_excludes_proxy_route():
    candidates = build_native_approximation_sweep()
    ids = [candidate.variant_id for candidate in candidates]

    assert ids == [
        "RAW_AS_IS",
        "NATIVE_NONE",
        "NATIVE_MESH_SIMPLIFICATION",
        "NATIVE_CONVEX_HULL",
        "NATIVE_CONVEX_DECOMPOSITION",
        "NATIVE_SDF_64",
        "NATIVE_SDF_128",
        "NATIVE_SDF_256",
        "NATIVE_BOUNDING_CUBE",
        "NATIVE_BOUNDING_SPHERE",
    ]
    assert all(candidate.route != "native_render_mesh_plus_proxy_collision" for candidate in candidates)
    assert NEVER_PROMOTABLE_VARIANT_IDS == {"NATIVE_NONE", "NATIVE_BOUNDING_CUBE", "NATIVE_BOUNDING_SPHERE"}


def test_claim_boundary_separates_allowed_and_blocked_claims():
    boundary = build_claim_boundary()

    assert "built-in/native Isaac/PhysX mesh collision approximation modes" in boundary["allowed_claims"][0]
    assert any("Render/video appearance alone" in claim for claim in boundary["blocked_claims"])
    assert boundary["s3_kinematic_pour_released"] is False
    assert boundary["benchmark_ready_claim_allowed"] is False


def test_static_hold_classifier_requires_zero_leak_and_promotable_candidate():
    summary = {
        "runtime_step_executed": True,
        "readback_diagnostics": {"readback_available": True, "readback_position_changed": True},
        "classification": {
            "classification": "PASS_SOURCE_HOLD",
            "particle_count_final_fraction": 1.0,
            "source_retention_fraction": 1.0,
            "outside_source_count": 0,
            "target_count": 0,
            "spill_count": 0,
            "below_table_count": 0,
            "tail_leak_rate_fraction_per_second": 0.0,
            "cpu_collision_fallback_detected": False,
            "gpu_collider_unsupported": False,
            "nan_count": 0,
            "fatal_error": None,
        },
    }

    result = classify_native_approximation_summary(summary, variant_id="NATIVE_SDF_128")

    assert result["native_approximation_static_hold_passed"] is True
    assert result["promotable_to_repeat_review"] is True


def test_static_hold_classifier_never_promotes_negative_controls():
    summary = {
        "runtime_step_executed": True,
        "readback_diagnostics": {"readback_available": True, "readback_position_changed": True},
        "classification": {
            "classification": "PASS_SOURCE_HOLD",
            "particle_count_final_fraction": 1.0,
            "source_retention_fraction": 1.0,
            "outside_source_count": 0,
            "target_count": 0,
            "spill_count": 0,
            "below_table_count": 0,
            "tail_leak_rate_fraction_per_second": 0.0,
            "cpu_collision_fallback_detected": False,
            "gpu_collider_unsupported": False,
            "nan_count": 0,
            "fatal_error": None,
        },
    }

    result = classify_native_approximation_summary(summary, variant_id="NATIVE_BOUNDING_CUBE")

    assert result["native_approximation_static_hold_passed"] is True
    assert result["promotable_to_repeat_review"] is False
    assert result["promotion_block_reason"] == "diagnostic_or_negative_control"


def test_apply_native_collider_approximation_authors_mesh_collision_api():
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)

    candidate = next(c for c in build_native_approximation_sweep() if c.variant_id == "NATIVE_CONVEX_HULL")
    result = apply_native_collider_approximation(stage, candidate)

    assert result["mesh_path"] == DEFAULT_NATIVE_MESH_PATH
    assert result["authored_collision_enabled"] is True
    assert UsdPhysics.MeshCollisionAPI(mesh.GetPrim()).GetApproximationAttr().Get() == "convexHull"


def test_apply_native_sdf_authors_sdf_settings_when_schema_available():
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)

    candidate = next(c for c in build_native_approximation_sweep() if c.variant_id == "NATIVE_SDF_128")
    result = apply_native_collider_approximation(stage, candidate)

    assert result["approximation"] == "sdf"
    assert result["sdf_resolution"] == 128
    assert UsdPhysics.MeshCollisionAPI(mesh.GetPrim()).GetApproximationAttr().Get() == "sdf"


def test_summarize_native_mesh_collision_state_handles_missing_mesh():
    from pxr import Usd

    stage = Usd.Stage.CreateInMemory()

    summary = summarize_native_mesh_collision_state(stage, "/World/missing")

    assert summary["mesh_path"] == "/World/missing"
    assert summary["exists"] is False


def test_dry_run_authoring_writes_manifest_and_overlays(tmp_path):
    from pxr import Usd, UsdGeom

    source = tmp_path / "source.usda"
    stage = Usd.Stage.CreateNew(str(source))
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)
    stage.GetRootLayer().Save()

    manifest = write_dry_run_authoring_artifacts(
        usd_path=source,
        out_dir=tmp_path / "artifacts",
        manifest_path=tmp_path / "manifest.json",
        variant_ids=["NATIVE_CONVEX_DECOMPOSITION", "NATIVE_SDF_64"],
    )

    assert manifest["manifest_type"] == "fluid_spike_native_collider_approximation_sweep"
    assert manifest["dry_run_authoring_only"] is True
    assert manifest["source_usd_path"] == str(source)
    assert [item["variant_id"] for item in manifest["candidate_results"]] == [
        "NATIVE_CONVEX_DECOMPOSITION",
        "NATIVE_SDF_64",
    ]
    assert all(item["overlay_usda"] for item in manifest["candidate_results"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.labutopia_fluid.run_colleague_native_collider_approx_sweep'`.

### Task 2: Implement Candidate Model, Claim Boundary, and USD Authoring

**Files:**
- Create: `tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py`
- Test: `tests/test_fluid_colleague_native_collider_approx_sweep.py`

- [ ] **Step 1: Write the minimal implementation**

Create `tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py` with these public functions and dataclass:

```python
#!/usr/bin/env python3
"""Sweep built-in/native collider approximations on colleague LabUtopia beaker2."""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_beaker_collider_smoke import _apply_static_collision

DEFAULT_USD = (
    "outputs/usd_asset_packages/lab_001_localized_20260707/"
    "lab_001_level1_pour_tabletop_with_liquid.usd"
)
DEFAULT_NATIVE_MESH_PATH = "/World/beaker2/mesh"
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_native_collider_approximation_sweep_20260708_001"
)
DEFAULT_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_native_collider_approximation_sweep_20260708.json"
)
NEVER_PROMOTABLE_VARIANT_IDS = {"NATIVE_NONE", "NATIVE_BOUNDING_CUBE", "NATIVE_BOUNDING_SPHERE"}


@dataclass(frozen=True)
class NativeApproximationCandidate:
    variant_id: str
    approximation: str | None
    description: str
    role: str
    sdf_resolution: int | None = None
    sdf_subgrid_resolution: int | None = None
    sdf_margin: float | None = None
    sdf_narrow_band_thickness: float | None = None
    contact_offset: float = 0.002
    rest_offset: float = -0.001

    @property
    def route(self) -> str:
        return self.approximation or "raw_as_is"

    @property
    def promotable(self) -> bool:
        return self.variant_id not in NEVER_PROMOTABLE_VARIANT_IDS


def build_native_approximation_sweep() -> list[NativeApproximationCandidate]:
    return [
        NativeApproximationCandidate("RAW_AS_IS", None, "Audit current authored native collision state.", "baseline"),
        NativeApproximationCandidate("NATIVE_NONE", "none", "Direct/none mesh diagnostic.", "diagnostic"),
        NativeApproximationCandidate(
            "NATIVE_MESH_SIMPLIFICATION", "meshSimplification", "Built-in mesh simplification route.", "candidate"
        ),
        NativeApproximationCandidate("NATIVE_CONVEX_HULL", "convexHull", "Built-in convex hull route.", "candidate"),
        NativeApproximationCandidate(
            "NATIVE_CONVEX_DECOMPOSITION",
            "convexDecomposition",
            "Built-in convex decomposition route, baseline regression.",
            "candidate",
        ),
        NativeApproximationCandidate(
            "NATIVE_SDF_64", "sdf", "Built-in SDF mesh collision, resolution 64.", "candidate", sdf_resolution=64
        ),
        NativeApproximationCandidate(
            "NATIVE_SDF_128", "sdf", "Built-in SDF mesh collision, resolution 128.", "candidate", sdf_resolution=128
        ),
        NativeApproximationCandidate(
            "NATIVE_SDF_256", "sdf", "Built-in SDF mesh collision, resolution 256.", "candidate", sdf_resolution=256
        ),
        NativeApproximationCandidate("NATIVE_BOUNDING_CUBE", "boundingCube", "Bounding cube negative control.", "diagnostic"),
        NativeApproximationCandidate(
            "NATIVE_BOUNDING_SPHERE", "boundingSphere", "Bounding sphere negative control.", "diagnostic"
        ),
    ]


def build_claim_boundary() -> dict[str, Any]:
    return {
        "allowed_claims": [
            "We tested built-in/native Isaac/PhysX mesh collision approximation modes before custom wrapper design.",
            "The test used the full colleague native USD scene, completed-PBD runtime particles, and particle readback.",
            "If all candidates fail, the tested native approximation modes did not produce a fluid-safe native beaker collider under this IsaacSim41/PBD setup.",
            "If one candidate passes smoke, it is only a static-hold candidate for promotion review.",
        ],
        "blocked_claims": [
            "level1_pour is benchmark-ready with true fluid.",
            "Raw colleague 50k USD directly steps as true PBD fluid without runtime completion.",
            "Render/video appearance alone proves physics correctness.",
            "Native beaker mesh is generally fluid-safe.",
            "S3 kinematic pour, S4 replay, EBench score, policy score, or leaderboard readiness is released.",
        ],
        "s3_kinematic_pour_released": False,
        "benchmark_ready_claim_allowed": False,
        "visual_only_evidence_allowed_for_physics": False,
    }


def _repo_path(path: str | Path) -> Path:
    normalized = Path(path)
    return normalized if normalized.is_absolute() else REPO_ROOT / normalized


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
    return value


def summarize_native_mesh_collision_state(stage: Any, mesh_path: str = DEFAULT_NATIVE_MESH_PATH) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(mesh_path)
    if not prim:
        return {"mesh_path": mesh_path, "exists": False}
    return {
        "mesh_path": mesh_path,
        "exists": True,
        "type_name": prim.GetTypeName(),
        "applied_schemas": list(prim.GetAppliedSchemas()),
        "collision_enabled": _read_attr(prim, "physics:collisionEnabled"),
        "approximation": _read_attr(prim, "physics:approximation"),
        "rigid_body_enabled": _read_attr(prim, "physics:rigidBodyEnabled"),
        "kinematic_enabled": _read_attr(prim, "physics:kinematicEnabled"),
        "contact_offset": _read_attr(prim, "physxCollision:contactOffset"),
        "rest_offset": _read_attr(prim, "physxCollision:restOffset"),
        "sdf_resolution": _read_attr(prim, "physxSDFMeshCollision:sdfResolution"),
    }


def _read_attr(prim: Any, attr_name: str) -> Any:
    attr = prim.GetAttribute(attr_name)
    return attr.Get() if attr else None


def apply_native_collider_approximation(
    stage: Any,
    candidate: NativeApproximationCandidate,
    *,
    mesh_path: str = DEFAULT_NATIVE_MESH_PATH,
) -> dict[str, Any]:
    from pxr import UsdPhysics

    prim = stage.GetPrimAtPath(mesh_path)
    if not prim:
        raise ValueError(f"native_mesh_not_found:{mesh_path}")
    pre_state = summarize_native_mesh_collision_state(stage, mesh_path)
    if candidate.variant_id != "RAW_AS_IS":
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            rigid_body = UsdPhysics.RigidBodyAPI.Apply(prim)
            rigid_body.CreateRigidBodyEnabledAttr().Set(False)
            rigid_body.CreateKinematicEnabledAttr().Set(False)
        _apply_static_collision(
            prim,
            approximation=candidate.approximation,
            contact_offset=candidate.contact_offset,
            rest_offset=candidate.rest_offset,
            sdf_resolution=candidate.sdf_resolution,
            sdf_subgrid_resolution=candidate.sdf_subgrid_resolution or 4,
            sdf_margin=candidate.sdf_margin if candidate.sdf_margin is not None else 0.002,
            sdf_narrow_band_thickness=candidate.sdf_narrow_band_thickness or 0.01,
        )
    post_state = summarize_native_mesh_collision_state(stage, mesh_path)
    return {
        "variant_id": candidate.variant_id,
        "mesh_path": mesh_path,
        "approximation": candidate.approximation,
        "sdf_resolution": candidate.sdf_resolution,
        "authored_collision_enabled": bool(post_state.get("collision_enabled")),
        "sweep_authored_collision_enabled": candidate.variant_id != "RAW_AS_IS",
        "pre_state": pre_state,
        "post_state": post_state,
    }
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py -q
```

Expected: tests now progress beyond import and identify missing dry-run/classifier functions.

### Task 3: Implement Dry-Run Manifest and Classifier

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py`
- Test: `tests/test_fluid_colleague_native_collider_approx_sweep.py`

- [ ] **Step 1: Add classifier and dry-run artifact writer**

Append these functions:

```python
def classify_native_approximation_summary(summary: dict[str, Any], *, variant_id: str) -> dict[str, Any]:
    detail = summary.get("classification") or {}
    readback = summary.get("readback_diagnostics") or {}
    checks = {
        "runtime_step_executed": bool(summary.get("runtime_step_executed")),
        "readback_available": bool(readback.get("readback_available")),
        "readback_position_changed": bool(readback.get("readback_position_changed")),
        "particle_count_final_fraction": _detail_float_at_least(detail, "particle_count_final_fraction", 0.95),
        "source_retention_fraction": _detail_float_at_least(detail, "source_retention_fraction", 0.95),
        "outside_source_count": _detail_int_equals(detail, "outside_source_count", 0),
        "target_count": _detail_int_equals(detail, "target_count", 0),
        "spill_count": _detail_int_equals(detail, "spill_count", 0),
        "below_table_count": _detail_int_equals(detail, "below_table_count", 0),
        "tail_leak_rate_fraction_per_second": _detail_float_less_than(
            detail, "tail_leak_rate_fraction_per_second", 0.02
        ),
        "cpu_collision_fallback_detected": detail.get("cpu_collision_fallback_detected") is False,
        "gpu_collider_unsupported": detail.get("gpu_collider_unsupported") is False,
        "nan_count": _detail_int_equals(detail, "nan_count", 0),
        "fatal_error": "fatal_error" in detail and detail.get("fatal_error") is None,
    }
    static_hold_passed = all(checks.values())
    never_promotable = variant_id in NEVER_PROMOTABLE_VARIANT_IDS
    return {
        "variant_id": variant_id,
        "classification": detail.get("classification"),
        "native_approximation_static_hold_passed": static_hold_passed,
        "promotable_to_repeat_review": bool(static_hold_passed and not never_promotable),
        "promotion_block_reason": "diagnostic_or_negative_control" if static_hold_passed and never_promotable else None,
        "gate_checks": checks,
        "particle_count_final_fraction": float(detail.get("particle_count_final_fraction", 0.0) or 0.0),
        "source_retention_fraction": float(detail.get("source_retention_fraction", 0.0) or 0.0),
        "outside_source_count": int(detail.get("outside_source_count", 0) or 0),
        "target_count": int(detail.get("target_count", 0) or 0),
        "spill_count": int(detail.get("spill_count", 0) or 0),
        "below_table_count": int(detail.get("below_table_count", 0) or 0),
        "tail_leak_rate_fraction_per_second": float(detail.get("tail_leak_rate_fraction_per_second", 0.0) or 0.0),
    }


def _select_candidates(variant_ids: Sequence[str] | None) -> list[NativeApproximationCandidate]:
    candidates = build_native_approximation_sweep()
    if not variant_ids:
        return candidates
    allowed = {candidate.variant_id: candidate for candidate in candidates}
    missing = [variant_id for variant_id in variant_ids if variant_id not in allowed]
    if missing:
        raise ValueError(f"unknown_native_approximation_variants:{','.join(missing)}")
    return [allowed[variant_id] for variant_id in variant_ids]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_dry_run_authoring_artifacts(
    *,
    usd_path: str | Path,
    out_dir: str | Path,
    manifest_path: str | Path,
    variant_ids: Sequence[str] | None = None,
    mesh_path: str = DEFAULT_NATIVE_MESH_PATH,
) -> dict[str, Any]:
    from pxr import Usd

    source = _repo_path(usd_path).resolve()
    out = _repo_path(out_dir).resolve()
    manifest = _repo_path(manifest_path).resolve()
    candidates = _select_candidates(variant_ids)
    candidate_results = []
    for candidate in candidates:
        stage = Usd.Stage.Open(str(source), Usd.Stage.LoadAll)
        if stage is None:
            raise RuntimeError(f"usd_stage_open_failed:{source}")
        authoring = apply_native_collider_approximation(stage, candidate, mesh_path=mesh_path)
        variant_dir = out / candidate.variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        overlay_path = variant_dir / "native_collider_approximation_overlay.usda"
        stage.GetRootLayer().Export(str(overlay_path))
        result = {
            "variant_id": candidate.variant_id,
            "candidate": asdict(candidate),
            "runtime_step_executed": False,
            "dry_run_authoring_only": True,
            "overlay_usda": str(overlay_path),
            "authoring": authoring,
        }
        _write_json(variant_dir / "variant_summary.json", result)
        candidate_results.append(result)
    payload = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_native_collider_approximation_sweep",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_usd_path": str(source),
        "mesh_path": mesh_path,
        "dry_run_authoring_only": True,
        "candidate_results": candidate_results,
        "candidate_ids": [candidate.variant_id for candidate in candidates],
        "claim_boundary": build_claim_boundary(),
    }
    _write_json(manifest, payload)
    return payload
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py -q
```

Expected: PASS.

### Task 4: Add CLI and Runtime Integration

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py`
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- Test: `tests/test_fluid_colleague_native_collider_approx_sweep.py`

- [ ] **Step 1: Add optional runtime arguments to the native completed-PBD runner**

In `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`, import the helper inside `_native_stage_runtime` after the stage is opened:

```python
from tools.labutopia_fluid.run_colleague_native_collider_approx_sweep import (
    apply_native_collider_approximation,
    build_native_approximation_sweep,
)
```

After `stage = context.get_stage()` succeeds and before `_deactivate_original_fluid_prims(stage)`, add:

```python
    native_collider_approximation_summary = {"enabled": False}
    if getattr(args, "native_collider_approximation_variant", None):
        candidates = {candidate.variant_id: candidate for candidate in build_native_approximation_sweep()}
        candidate = candidates[args.native_collider_approximation_variant]
        native_collider_approximation_summary = {
            "enabled": True,
            "candidate": asdict(candidate),
            "authoring": apply_native_collider_approximation(stage, candidate),
        }
```

Add the summary to the manifest:

```python
        "native_collider_approximation": native_collider_approximation_summary,
```

Add parser argument:

```python
    parser.add_argument("--native-collider-approximation-variant", default=None)
```

- [ ] **Step 2: Add aggregate CLI to the sweep runner**

Append:

```python
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=DEFAULT_USD)
    parser.add_argument("--out-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--mesh-path", default=DEFAULT_NATIVE_MESH_PATH)
    parser.add_argument("--variant", action="append", dest="variants", default=None)
    parser.add_argument("--dry-run-authoring", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.dry_run_authoring:
        payload = write_dry_run_authoring_artifacts(
            usd_path=args.usd,
            out_dir=args.out_dir,
            manifest_path=args.manifest,
            variant_ids=args.variants,
            mesh_path=args.mesh_path,
        )
        print(json.dumps(_json_safe(payload), indent=2, sort_keys=True))
        return 0
    raise SystemExit("runtime_sweep_not_implemented_in_cli_use_dry_run_authoring_or_native_runner_variant_arg")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py -q
```

Expected: PASS.

### Task 5: Run Dry-Run Authoring on the Real Colleague USD

**Files:**
- Output: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708.json`
- Output: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001/*`

- [ ] **Step 1: Run dry-run authoring**

Run:

```bash
python3 tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py \
  --dry-run-authoring \
  --usd outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708.json
```

Expected: exit 0; manifest has ten candidates and each candidate has an overlay `.usda`.

- [ ] **Step 2: Run regression tests**

Run:

```bash
python3 -m pytest \
  tests/test_fluid_colleague_native_collider_approx_sweep.py \
  tests/test_fluid_beaker_collider_smoke.py \
  tests/test_fluid_beaker_collider_followup_sweep.py \
  tests/test_fluid_colleague_liquid_usd_leak_smoke.py \
  tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py \
  -q
```

Expected: PASS.

### Task 6: Runtime Smoke Candidate, Then Summarize

**Files:**
- Output: candidate runtime artifact dirs under `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001/`

- [ ] **Step 1: Run the first runtime smoke candidate**

Run a cheap particle subset first:

```bash
python3 tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  --headless \
  --usd outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001/NATIVE_CONVEX_DECOMPOSITION_runtime_512 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001/NATIVE_CONVEX_DECOMPOSITION_runtime_512.json \
  --particle-limit 512 \
  --steps 120 \
  --trace-interval 10 \
  --video-stride 10 \
  --capture-closeup-camera \
  --native-collider-approximation-variant NATIVE_CONVEX_DECOMPOSITION
```

Expected: exit 0 or a manifest with `runtime_step_executed=false` and a fatal error. Either outcome is evidence; do not claim pass without checking manifest classification/readback.

- [ ] **Step 2: If runtime works, run the remaining smoke candidates**

Run the same command for:

```text
NATIVE_MESH_SIMPLIFICATION
NATIVE_CONVEX_HULL
NATIVE_SDF_64
NATIVE_SDF_128
NATIVE_SDF_256
NATIVE_NONE
NATIVE_BOUNDING_CUBE
NATIVE_BOUNDING_SPHERE
```

Use one artifact dir and manifest per candidate. Stop early only if Isaac Sim itself is blocked before any candidate can run; then preserve the fatal error as the result.

### Task 7: Update Docs and Request Review

**Files:**
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `reports/2026-07-07-labutopia-fluid-weekly/index.html`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md` if present

- [ ] **Step 1: Add product-facing explanation**

Add a section titled:

```markdown
## S2F6 Native Collider Approximation Sweep
```

Include:

```text
为什么做：先把 Isaac/PhysX 原生可切换的 collider approximation 全部测掉，避免过早进入自定义 collider。
怎么做：不移动杯子、不换成 proxy 场景，只在完整 colleague native USD 中对 /World/beaker2/mesh 改 MeshCollisionAPI approximation。
能证明什么：原生 approximation 是否存在一个能静置持液的候选。
不能证明什么：不能直接证明倒液任务、EBench 得分或 raw USD 直接可运行。
下一步：若无候选通过，才进入 custom wrapper/container collider design；若有候选通过，进入 512/1024/4096/50000 repeat promotion。
```

- [ ] **Step 2: Update weekly HTML**

In `reports/2026-07-07-labutopia-fluid-weekly/index.html`, replace any direct "next is wrapper" wording with:

```text
Native Collider Approximation Sweep 已完成：convexDecomposition、sdf、convexHull、meshSimplification、none、boundingCube、boundingSphere 等 Isaac/PhysX 内置模式都已在同一个原生 beaker2 mesh 上扫过。10/10 完成 runtime step/readback，0/10 通过 static hold，因此内置路线不能兜住液体，下一步才进入自定义杯壁/容器 collider 设计。
```

- [ ] **Step 3: Request review and verify**

Run:

```bash
git diff -- docs/superpowers/plans/2026-07-08-native-collider-approximation-sweep.md \
  tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py \
  tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  tests/test_fluid_colleague_native_collider_approx_sweep.py \
  docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md \
  reports/2026-07-07-labutopia-fluid-weekly/index.html
```

Dispatch one spec-review subagent and one code-quality review subagent. Fix Critical and Important findings before commit.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-07-08-native-collider-approximation-sweep.md \
  tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py \
  tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  tests/test_fluid_colleague_native_collider_approx_sweep.py \
  docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md \
  reports/2026-07-07-labutopia-fluid-weekly/index.html \
  docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708.json \
  docs/labutopia_lab_poc/evidence_manifests/fluid_spike_native_collider_approximation_sweep_20260708_001
git commit -m "feat: add native collider approximation sweep"
```

## Self-Review Notes

- Spec coverage: Candidate scope, claim boundary, no custom collider route, full-native scene, dry-run artifacts, and runtime hook are all covered.
- Placeholder scan: No `TBD`, `TODO`, or "implement later" placeholders are used.
- Type consistency: Public names in tests match the implementation snippets: `NativeApproximationCandidate`, `build_native_approximation_sweep`, `apply_native_collider_approximation`, `classify_native_approximation_summary`, and `write_dry_run_authoring_artifacts`.
- Execution mode: The user already authorized recommended autonomous execution, so this plan proceeds with `superpowers:subagent-driven-development` without asking for an execution choice.

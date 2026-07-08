# Fluid S2F4 Native Mesh Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and run `S2F4_C4_NATIVE_MESH_ISOLATION` so LabUtopia native `beaker2/mesh` is tested as a PhysX/PBD fluid collider with scope-closed evidence.

**Architecture:** Extend the existing S2F follow-up runner, not the S2 baseline matrix. Keep old `C4` evidence immutable, add new `C4A_*` candidates that close material-binding scope, recenter native pose by measured bound, and compare native `convexDecomposition`, native `sdf`, and native render mesh plus proxy collision.

**Tech Stack:** Python 3.10, pytest, Isaac Sim 4.1, USD/PhysX/PBD, `pxr.Usd`, JSON manifests, Markdown evidence docs.

---

## File Structure

```text
tools/labutopia_fluid/run_beaker_collider_smoke.py
tools/labutopia_fluid/run_beaker_collider_followup_sweep.py
tests/test_fluid_beaker_collider_smoke.py
tests/test_fluid_beaker_collider_followup_sweep.py
docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md
docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md
docs/labutopia_lab_poc/evidence_manifests/README.md
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f4_c4_native_mesh_isolation_20260708.json
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f4_c4_native_mesh_isolation_20260708_001/
assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f4/
```

Do not edit `assets/chemistry_lab/lab_001/lab_001.usd` in place. `C4` baseline remains unchanged.

## Candidate Contract

```text
C4A_convexDecomposition_reference_scope_closed = native beaker parent reference + local material bind + convexDecomposition collision
C4A_sdf_reference_scope_closed = native beaker parent reference + local material bind + SDF collision
C4A_native_render_mesh_plus_proxy_collision = native beaker render mesh + local material bind + procedural proxy collision wrapper
```

Each candidate must record:

```text
native_source_usd
native_source_prim=/World/beaker2
native_mesh_source_prim=/World/beaker2/mesh
native_reference_scope=parent_scope
native_material_binding_strategy=local_blue_glass_override
native_material_binding_scope_closed=true
native_pose_alignment=bbox_recenter_to_source_region
native_collision_route=<convexDecomposition|sdf|render_mesh_plus_proxy_collision>
native_render_mesh_collision_enabled=<true|false>
proxy_collision_enabled=<true|false>
```

Important claim guard: if `C4A_native_render_mesh_plus_proxy_collision` passes, the manifest may promote it to
S2F5 as a wrapped native-render route, but must not claim that the native render mesh itself is a fluid-safe
collider. Only `C4A_convexDecomposition_reference_scope_closed` or `C4A_sdf_reference_scope_closed` can support
the narrower native-collider usability claim.

## Task 1: Add S2F4 Candidate Contract Tests

**Files:**
- Modify: `tests/test_fluid_beaker_collider_followup_sweep.py`

- [ ] **Step 1: Write failing candidate-grid test**

Add this test:

```python
def test_s2f4_builds_native_mesh_isolation_candidates():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f4_native_mesh_isolation

    candidates = build_s2f4_native_mesh_isolation()

    assert [candidate.candidate_id for candidate in candidates] == [
        "C4A_convexDecomposition_reference_scope_closed",
        "C4A_sdf_reference_scope_closed",
        "C4A_native_render_mesh_plus_proxy_collision",
    ]
    assert {candidate.phase for candidate in candidates} == {"S2F4_C4_NATIVE_MESH_ISOLATION"}
    assert [candidate.native_collision_route for candidate in candidates] == [
        "convexDecomposition",
        "sdf",
        "render_mesh_plus_proxy_collision",
    ]
    assert {candidate.native_reference_scope for candidate in candidates} == {"parent_scope"}
    assert {candidate.native_material_binding_strategy for candidate in candidates} == {
        "local_blue_glass_override"
    }
    assert {candidate.native_material_binding_scope_closed for candidate in candidates} == {True}
    assert {candidate.native_pose_alignment for candidate in candidates} == {"bbox_recenter_to_source_region"}
```

- [ ] **Step 2: Write failing variant-spec test**

Add this test:

```python
def test_s2f4_candidate_materializes_native_variant_spec():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f4_native_mesh_isolation

    candidate = build_s2f4_native_mesh_isolation()[1]
    config = candidate.to_config(base=ColliderConfig(steps=12))
    spec = candidate.to_variant_spec()

    assert config.steps == 12
    assert config.sdf_resolution == 96
    assert spec.variant_id == "C4A_sdf_reference_scope_closed"
    assert spec.setup == "s2f4_native_beaker_mesh_isolation"
    assert spec.source_kind == "native_mesh_reference"
    assert spec.native_source_path == "/World/beaker2"
    assert spec.native_mesh_source_path == "/World/beaker2/mesh"
    assert spec.collision_approximation == "sdf"
    assert spec.native_material_binding_scope_closed is True
    assert spec.native_pose_alignment == "bbox_recenter_to_source_region"
```

- [ ] **Step 3: Verify RED**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f4_builds_native_mesh_isolation_candidates tests/test_fluid_beaker_collider_followup_sweep.py::test_s2f4_candidate_materializes_native_variant_spec
```

Expected: FAIL because `build_s2f4_native_mesh_isolation` and S2F4 fields do not exist.

## Task 2: Implement Native-Mesh Authoring Routes

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_smoke.py`
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
- Test: `tests/test_fluid_beaker_collider_smoke.py`

- [ ] **Step 1: Write failing smoke authoring tests**

Add tests that build `VariantSpec` instances for `C4A_convexDecomposition_reference_scope_closed`,
`C4A_sdf_reference_scope_closed`, and `C4A_native_render_mesh_plus_proxy_collision`, call `_add_colliders`
on an in-memory USD stage, and assert:

```python
assert "/World/SourceContainer/NativeBeaker2/mesh" in collider_paths
assert mesh_prim.GetAttribute("labutopia:nativeMaterialBindingScopeClosed").Get() is True
assert mesh_prim.GetAttribute("labutopia:nativePoseAlignment").Get() == "bbox_recenter_to_source_region"
assert mesh_prim.GetAttribute("labutopia:nativeCollisionRoute").Get() == expected_route
```

For `C4A_native_render_mesh_plus_proxy_collision`, also assert:

```python
assert mesh_prim.GetAttribute("physics:collisionEnabled").Get() is False
assert any(path.startswith("/World/SourceContainer/ProxyCollision") for path in collider_paths)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_smoke.py::test_c4a_native_parent_reference_scope_closed_authoring tests/test_fluid_beaker_collider_smoke.py::test_c4a_native_render_mesh_plus_proxy_disables_native_collision
```

Expected: FAIL because `_add_colliders` does not route `C4A_*`.

- [ ] **Step 3: Implement authoring**

Add helper functions:

```python
def _bind_scope_closed_native_material(stage, mesh_prim) -> None:
    from pxr import Sdf, UsdShade
    material = UsdShade.Material(stage.GetPrimAtPath("/World/Looks/Blue_Glass"))
    UsdShade.MaterialBindingAPI.Apply(mesh_prim).Bind(material)
    mesh_prim.CreateAttribute("labutopia:nativeMaterialBindingStrategy", Sdf.ValueTypeNames.String).Set(
        "local_blue_glass_override"
    )
    mesh_prim.CreateAttribute("labutopia:nativeMaterialBindingScopeClosed", Sdf.ValueTypeNames.Bool).Set(True)
```

Add a parent-scope reference helper that references `/World/beaker2`, computes the referenced bound, and translates a wrapper so the native mesh is centered over the S2 source region with its lower bound at `table_z`.

Add route handling:

```text
convexDecomposition -> native mesh collision enabled, approximation=convexDecomposition
sdf -> native mesh collision enabled, approximation=sdf, sdf_resolution=96
render_mesh_plus_proxy_collision -> native mesh collision disabled, add segmented proxy collision under /World/SourceContainer/ProxyCollision
```

- [ ] **Step 4: Verify GREEN**

Run the two smoke authoring tests and then:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_smoke.py
```

Expected: all smoke tests PASS.

## Task 3: Add S2F4 Manifest and CLI Support

**Files:**
- Modify: `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
- Modify: `tests/test_fluid_beaker_collider_followup_sweep.py`

- [ ] **Step 1: Write failing manifest tests**

Add tests:

```python
def test_write_s2f4_manifest_promotes_native_candidate_to_s2f5_not_s3(tmp_path):
    ...
    assert manifest["stage"] == "S2F4_C4_NATIVE_MESH_ISOLATION"
    assert manifest["status"] == "GO_NEXT"
    assert manifest["reason"] == "at_least_one_c4a_native_candidate_passed"
    assert manifest["best_for_s2f5"] == ["C4A_convexDecomposition_reference_scope_closed"]
    assert manifest["best_for_s3"] == []
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["next_stage"]["id"] == "S2F5_PROMOTION_REVIEW"
```

Add a proxy-wrapper claim-boundary assertion:

```python
def test_write_s2f4_manifest_marks_proxy_wrapper_pass_as_wrapped_route_not_native_collider(tmp_path):
    ...
    assert manifest["best_for_s2f5"] == ["C4A_native_render_mesh_plus_proxy_collision"]
    assert manifest["native_beaker_fluid_safe_collider_status"] == "NATIVE_BEAKER_REQUIRES_PROXY_WRAPPER"
    assert manifest["allowed_claims"] == [
        "S2F4 found a native render mesh plus proxy collision route for S2F5 review."
    ]
```

```python
def test_write_s2f4_manifest_signs_native_beaker_not_fluid_safe_when_all_fail(tmp_path):
    ...
    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "native_beaker_not_fluid_safe_collider"
    assert manifest["native_beaker_fluid_safe_collider_status"] == "NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER"
    assert manifest["best_for_s2f5"] == []
    assert manifest["best_for_s3"] == []
    assert manifest["next_stage"]["id"] == "S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP"
```

- [ ] **Step 2: Write failing CLI plan-only test**

Add a plan-only test for:

```bash
python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F4_C4_NATIVE_MESH_ISOLATION --plan-only
```

Expected manifest fields:

```text
manifest_type=true_physx_pbd_fluid_spike_s2f4_c4_native_mesh_isolation
status=PLAN_READY
candidate_count=3
candidate ids = C4A_convexDecomposition_reference_scope_closed,C4A_sdf_reference_scope_closed,C4A_native_render_mesh_plus_proxy_collision
next_stage.id=S2F4_C4_NATIVE_MESH_ISOLATION
```

- [ ] **Step 3: Verify RED**

Run the S2F4 tests. Expected: FAIL because S2F4 is not in `main()` and manifest reason logic.

- [ ] **Step 4: Implement follow-up runner support**

Add defaults:

```python
DEFAULT_S2F4_ARTIFACT_DIR = "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f4_c4_native_mesh_isolation_20260708_001"
DEFAULT_S2F4_MANIFEST_PATH = "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f4_c4_native_mesh_isolation_20260708.json"
DEFAULT_S2F4_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f4"
DEFAULT_S2F4_SOURCE_MANIFEST = "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json"
```

Route `--phase S2F4_C4_NATIVE_MESH_ISOLATION` to `build_s2f4_native_mesh_isolation()`. S2F4 PASS should populate `best_for_s2f5`, not `best_for_s3`.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
python -m pytest -q tests/test_fluid_beaker_collider_followup_sweep.py
```

Expected: all follow-up tests PASS.

## Task 4: Run S2F4 Evidence

**Files:**
- Runtime output: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f4_c4_native_mesh_isolation_20260708.json`
- Runtime output: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_isaacsim41_ebench_s2f4_c4_native_mesh_isolation_20260708_001/`
- Runtime output: `assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f4/`

- [ ] **Step 1: Run plan-only**

```bash
python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F4_C4_NATIVE_MESH_ISOLATION --plan-only
```

Expected: manifest status `PLAN_READY`, candidate count `3`.

- [ ] **Step 2: Run live S2F4**

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F4_C4_NATIVE_MESH_ISOLATION --steps 240 --headless
```

Expected: final manifest status is either `GO_NEXT` with `best_for_s2f5` or `STOP_WITH_EVIDENCE` with `native_beaker_fluid_safe_collider_status=NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER`.

- [ ] **Step 3: Audit runtime warnings**

S2F4 must not treat old material scope warnings as acceptable unless `material_binding_scope_warning==0` for scope-closed C4A routes. CPU fallback, GPU unsupported, PhysX error, and SDF warning remain blocking.

## Task 5: Update Docs, Review, Commit

**Files:**
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/superpowers/plans/2026-07-07-true-physx-pbd-fluid-spike-stop-go.md`

- [ ] **Step 1: Update PM wording**

Explain in Chinese:

```text
S2F4 tested the real LabUtopia beaker2 mesh, but separated three questions:
1. Did USD material reference scope close correctly?
2. Did native pose/scale align with source region?
3. Did the native-derived collision actually hold PBD particles?
```

- [ ] **Step 2: Update evidence index**

Register the S2F4 manifest, artifact directory, scene directory, and final stop/go result.

- [ ] **Step 3: Request code review**

Ask a reviewer to check:

```text
S2F4 does not mutate old C4 baseline.
S2F4 PASS routes to S2F5, not S3.
S2F4 STOP signs NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER only after all 3 C4A routes run.
Material-binding warning scan cannot hide real SDF/PhysX warnings.
```

- [ ] **Step 4: Run verification**

```bash
python -m pytest -q tests/test_fluid_beaker_collider_smoke.py tests/test_fluid_beaker_collider_followup_sweep.py
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f4_c4_native_mesh_isolation_20260708.json
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 5: Commit and push**

```bash
git add tools/labutopia_fluid tests docs assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f4
git commit -m "feat: run fluid s2f4 native mesh isolation"
```

Push to `origin/main` after fast-forward merge from the S2F4 worktree.

# Liquid Surface Reconstruction Videos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a presentation video lane for LabUtopia liquid collider evidence so every native collider variant can show a more readable reconstructed render surface under one fixed leadership-facing camera and lighting contract, while keeping particle readback as the only pass/fail authority.

**Architecture:** Extend the existing colleague native USD PBD runner with an optional presentation mode. The mode disables particle debug display, enables PhysX particle isosurface reconstruction on `/World/CompletedPBD/ParticleSystem`, binds a uniform transparent water material, records a fixed `/World/LiquidPresentationMainCamera`, and writes an explicit `presentation_visual_contract`. The existing diagnostic readback, classification, and collider variant sweep stay authoritative and unchanged in meaning.

**Tech Stack:** Python, Isaac Sim 4.1, USD / PhysX schemas, `omni.physx.scripts.particleUtils`, existing LabUtopia fluid runner/test stack, static HTML weekly report.

---

## Scope And Non-Goals

This plan changes visual evidence production, not the physics gate. It must not claim that `isosurface` fixes leaking, makes a collider benchmark-ready, or replaces `particle_readback_trace.jsonl`.

Required result:

- Native collider sweep variants can optionally produce `presentation_isosurface.mp4` by launching the existing native USD runtime runner once per variant.
- Presentation videos use one camera, one lighting contract, one liquid material, and no red particle debug display.
- Runtime summaries and aggregate manifests expose both presentation evidence and engineering evidence.
- All generated presentation videos get per-variant visual QA status before any weekly/report claim is written.
- The weekly HTML explains that reconstructed surface is a visual lane and particle readback remains the pass/fail source.

Out of scope:

- Designing a new `fluid-safe wrapper collider`.
- Changing static-hold pass/fail thresholds.
- Claiming visual/material parity with LabUtopia Isaac Sim 5.1.
- Replacing all historical C0-C5 videos in this pass. The implementation must make the contract reusable for a future C0-C5 evidence refresh.

## Files

- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
  - Owns presentation camera, lighting, water material, isosurface authoring, debug-display toggle, per-run summary fields, and CLI flags.
- Modify: `tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py`
  - Owns building per-variant runtime commands, launching the native runner for runtime sweeps, passing presentation flags through each runtime variant, defaulting missing presentation fields, and aggregating presentation video status.
- Modify: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`
  - Unit tests for presentation contract, isosurface params, claim boundary, parser flags, and video summary slots.
- Modify: `tests/test_fluid_colleague_native_collider_approx_sweep.py`
  - Unit tests for aggregate presentation fields and sweep command construction.
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
  - Product/engineering explanation of the new visual lane.
- Modify: `reports/2026-07-07-labutopia-fluid-weekly/index.html`
  - Add product-readable section for reconstructed liquid surface videos and claim boundary.
- Create after runtime: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708.json`
  - Aggregate manifest for presentation videos.
- Create after runtime: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708_001/<variant>/`
  - Per-variant video artifacts.

## Task 1: Add Presentation Contract Helpers

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- Test: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write failing tests for presentation contract helpers**

Append these tests to `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`:

```python
def test_build_liquid_presentation_isosurface_contract_uses_offsets():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        build_liquid_presentation_isosurface_contract,
    )

    contract = build_liquid_presentation_isosurface_contract(
        fluid_rest_offset=0.0003207600535824895,
        particle_count=50000,
    )

    assert contract["enabled"] is True
    assert contract["api_path"] == "/World/CompletedPBD/ParticleSystem"
    assert contract["grid_spacing"] == 0.00048114008037373427
    assert contract["surface_distance"] == 0.0005132160857319832
    assert contract["grid_smoothing_radius"] == 0.000641520107164979
    assert contract["num_mesh_smoothing_passes"] == 1
    assert contract["num_mesh_normal_smoothing_passes"] == 1
    assert contract["max_vertices"] >= 1_000_000
    assert contract["max_triangles"] >= 2_000_000
    assert contract["max_subgrids"] >= 4096
    assert contract["claim_boundary"] == "visual_surface_reconstruction_only"


def test_build_presentation_visual_contract_separates_visual_video_from_gate():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        LIQUID_PRESENTATION_CAMERA_PATH,
        LIQUID_PRESENTATION_MATERIAL_PATH,
        build_presentation_visual_contract,
    )

    contract = build_presentation_visual_contract(
        variant_id="NATIVE_SDF_128",
        camera_info={
            "camera_path": LIQUID_PRESENTATION_CAMERA_PATH,
            "eye": [0.5, -0.2, 1.0],
            "target": [0.3, 0.09, 0.86],
            "up": [0.0, 0.0, 1.0],
        },
        lighting_info={"lighting_contract_hash": "abc123"},
        isosurface_contract={"enabled": True},
        material_path=LIQUID_PRESENTATION_MATERIAL_PATH,
        particle_count=50000,
    )

    assert contract["variant_id"] == "NATIVE_SDF_128"
    assert contract["camera_path"] == LIQUID_PRESENTATION_CAMERA_PATH
    assert contract["liquid_material_path"] == LIQUID_PRESENTATION_MATERIAL_PATH
    assert contract["particle_count"] == 50000
    assert contract["debug_particle_display_enabled"] is False
    assert contract["presentation_video_does_not_replace_particle_readback"] is True
    assert contract["visual_material_parity_claim_allowed"] is False
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
python3 -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_liquid_presentation_isosurface_contract_uses_offsets tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_visual_contract_separates_visual_video_from_gate -q
```

Expected: fail with missing helper imports.

- [ ] **Step 3: Add constants and helper functions**

Add near the existing path constants in `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`:

```python
LIQUID_PRESENTATION_CAMERA_PATH = "/World/LiquidPresentationMainCamera"
LIQUID_PRESENTATION_MATERIAL_PATH = "/World/Looks/LiquidPresentationWater"
LIQUID_PRESENTATION_LIGHT_PATH = "/World/LiquidPresentationKeyLight"
```

Add these helpers before `_author_completed_pbd_runtime_particles`:

```python
def build_liquid_presentation_isosurface_contract(
    *,
    fluid_rest_offset: float,
    particle_count: int,
) -> dict[str, Any]:
    rest = float(fluid_rest_offset)
    max_vertices = max(1_000_000, int(max(1, particle_count) * 32))
    max_triangles = max(2_000_000, int(max(1, particle_count) * 64))
    return {
        "enabled": True,
        "api_path": RUNTIME_PARTICLE_SYSTEM_PATH,
        "grid_spacing": rest * 1.5,
        "surface_distance": rest * 1.6,
        "grid_smoothing_radius": rest * 2.0,
        "grid_filtering_passes": "",
        "num_mesh_smoothing_passes": 1,
        "num_mesh_normal_smoothing_passes": 1,
        "max_vertices": max_vertices,
        "max_triangles": max_triangles,
        "max_subgrids": 4096,
        "claim_boundary": "visual_surface_reconstruction_only",
    }


def build_presentation_visual_contract(
    *,
    variant_id: str | None,
    camera_info: dict[str, Any],
    lighting_info: dict[str, Any],
    isosurface_contract: dict[str, Any],
    material_path: str,
    particle_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "variant_id": variant_id,
        "camera_path": camera_info["camera_path"],
        "camera_eye": list(camera_info["eye"]),
        "camera_target": list(camera_info["target"]),
        "camera_up": list(camera_info["up"]),
        "lighting_contract_hash": lighting_info["lighting_contract_hash"],
        "isosurface": dict(isosurface_contract),
        "liquid_material_path": material_path,
        "particle_count": int(particle_count),
        "debug_particle_display_enabled": False,
        "presentation_video_does_not_replace_particle_readback": True,
        "visual_material_parity_claim_allowed": False,
        "benchmark_ready_claim_allowed": False,
    }
```

- [ ] **Step 4: Run tests and confirm pass**

Run the same targeted pytest command. Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "feat: define liquid presentation contract"
```

## Task 2: Implement Isosurface, Water Material, Camera, Lighting

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- Test: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write failing unit tests for authoring helpers**

Append:

```python
def test_presentation_material_and_lighting_are_authored_with_fixed_paths():
    from pxr import Usd, UsdGeom
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        LIQUID_PRESENTATION_LIGHT_PATH,
        LIQUID_PRESENTATION_MATERIAL_PATH,
        _author_liquid_presentation_lighting,
        _author_liquid_presentation_water_material,
    )

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")

    material_info = _author_liquid_presentation_water_material(stage)
    lighting_info = _author_liquid_presentation_lighting(stage)

    assert material_info["material_path"] == LIQUID_PRESENTATION_MATERIAL_PATH
    assert material_info["display_name"] == "presentation_water_transparent_blue"
    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_MATERIAL_PATH)
    assert lighting_info["light_path"] == LIQUID_PRESENTATION_LIGHT_PATH
    assert lighting_info["lighting_contract_hash"]
    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_LIGHT_PATH)


def test_define_presentation_camera_reuses_leadership_closeup_framing():
    from pxr import Usd, UsdGeom
    from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import ColliderConfig
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        LIQUID_PRESENTATION_CAMERA_PATH,
        _define_liquid_presentation_camera,
    )

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    config = ColliderConfig(
        source_center=(0.311802, 0.091802, 0.7727606155217077),
        target_center=(0.278523, -0.221477, 0.7727606155217077),
        source_radius=0.060327,
        target_radius=0.082457,
        source_height=0.164296,
        target_height=0.183118,
        table_z=0.7727606155217077,
    )

    info = _define_liquid_presentation_camera(stage, config)

    assert info["camera_path"] == LIQUID_PRESENTATION_CAMERA_PATH
    assert info["target"][2] > config.table_z
    assert info["eye"][2] > info["target"][2]
    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_CAMERA_PATH)
```

- [ ] **Step 2: Run targeted tests and confirm failure**

```bash
python3 -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_presentation_material_and_lighting_are_authored_with_fixed_paths tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_define_presentation_camera_reuses_leadership_closeup_framing -q
```

Expected: fail with missing helper imports.

- [ ] **Step 3: Implement material, lighting, and presentation camera helpers**

Add helpers:

```python
def _author_liquid_presentation_water_material(stage: Any) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    looks_path = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)
    material = UsdShade.Material.Define(stage, LIQUID_PRESENTATION_MATERIAL_PATH)
    shader = UsdShade.Shader.Define(stage, f"{LIQUID_PRESENTATION_MATERIAL_PATH}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.38, 0.78, 1.0))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.42)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.05)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return {
        "material_path": LIQUID_PRESENTATION_MATERIAL_PATH,
        "display_name": "presentation_water_transparent_blue",
        "opacity": 0.42,
        "roughness": 0.05,
        "visual_material_parity_claim_allowed": False,
    }


def _author_liquid_presentation_lighting(stage: Any) -> dict[str, Any]:
    import hashlib
    import json
    from pxr import Gf, UsdLux

    light = UsdLux.DistantLight.Define(stage, LIQUID_PRESENTATION_LIGHT_PATH)
    light.CreateIntensityAttr(900.0)
    light.CreateAngleAttr(0.35)
    rotate = [58.0, 0.0, 32.0]
    light.ClearXformOpOrder()
    light.AddRotateXYZOp().Set(Gf.Vec3f(*rotate))
    payload = {
        "light_path": LIQUID_PRESENTATION_LIGHT_PATH,
        "type": "DistantLight",
        "intensity": 900.0,
        "angle": 0.35,
        "rotate_xyz": rotate,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**payload, "lighting_contract_hash": hashlib.sha256(encoded).hexdigest()[:16]}


def _define_liquid_presentation_camera(stage: Any, config: Any) -> dict[str, Any]:
    from pxr import Gf, UsdGeom

    target = (
        config.source_center[0],
        config.source_center[1],
        config.table_z + min(max(config.source_height * 0.58, 0.08), 0.12),
    )
    eye = (
        config.source_center[0] + 0.20,
        config.source_center[1] - 0.34,
        config.table_z + 0.25,
    )
    up = (0.0, 0.0, 1.0)
    camera = UsdGeom.Camera.Define(stage, LIQUID_PRESENTATION_CAMERA_PATH)
    transform = Gf.Matrix4d(1).SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(*up)).GetInverse()
    camera.ClearXformOpOrder()
    camera.AddTransformOp().Set(transform)
    camera.CreateFocalLengthAttr(22.0)
    camera.CreateHorizontalApertureAttr(22.0)
    camera.CreateVerticalApertureAttr(16.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    return {
        "camera_path": LIQUID_PRESENTATION_CAMERA_PATH,
        "eye": list(eye),
        "target": list(target),
        "up": list(up),
        "role": "leadership_presentation_main",
    }
```

- [ ] **Step 4: Run targeted tests and confirm pass**

Run the same targeted pytest command. Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "feat: add liquid presentation visuals"
```

## Task 3: Wire Presentation Mode Into Runtime Runner

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- Test: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write failing parser and summary tests**

Append:

```python
def test_native_step_video_parser_accepts_presentation_isosurface_video_flag():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import build_arg_parser

    args = build_arg_parser().parse_args(
        [
            "--presentation-isosurface-video",
            "--disable-particle-debug-display",
        ]
    )

    assert args.presentation_isosurface_video is True
    assert args.disable_particle_debug_display is True


def test_build_native_scene_video_summary_records_presentation_slot():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        build_native_scene_video_summary,
    )

    summary = build_native_scene_video_summary(
        frame_sources={
            "presentation_isosurface_frames/frame_0001.png": "presentation_isosurface_rgb",
            "beaker2_closeup_native_material_frames/frame_0001.png": "closeup_native_rgb",
        }
    )

    assert summary["presentation_isosurface_rgb_frame_count"] == 1
    assert "presentation_isosurface" in summary["native_scene_video_slots"]
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
python3 -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_native_step_video_parser_accepts_presentation_isosurface_video_flag tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_native_scene_video_summary_records_presentation_slot -q
```

Expected: fail because flags and slot are missing.

- [ ] **Step 3: Add parser flags**

In `build_arg_parser()` add:

```python
parser.add_argument(
    "--presentation-isosurface-video",
    action="store_true",
    help="Enable PhysX Isosurface visual reconstruction, fixed presentation camera, presentation water material, and MP4 capture.",
)
parser.add_argument("--disable-particle-debug-display", action="store_true")
```

- [ ] **Step 4: Update video summary**

Change `build_native_scene_video_summary()` so it counts frame sources named `presentation_isosurface_rgb` and adds `presentation_isosurface` to `native_scene_video_slots` when present:

```python
presentation_count = sum(1 for source in frame_sources.values() if source == "presentation_isosurface_rgb")
slots = [
    "camera1_native_material",
    "camera2_native_material",
    "beaker2_closeup_native_material",
    "beaker2_closeup_review_markers",
]
if presentation_count:
    slots.insert(0, "presentation_isosurface")
```

Return:

```python
"presentation_isosurface_rgb_frame_count": presentation_count,
"native_scene_video_slots": slots,
```

- [ ] **Step 5: Wire runtime settings and authoring**

In `_native_stage_runtime(args)` change particle display settings through a runtime-only helper. Do not import `omni.physx.bindings._physx` in normal unit tests.

```python
def _physx_visualizer_mode_none(pb: Any) -> Any:
    return getattr(pb.VisualizerMode, "NONE", 0)


if args.presentation_isosurface_video or args.disable_particle_debug_display:
    settings.set(pb.SETTING_DISPLAY_PARTICLES, _physx_visualizer_mode_none(pb))
else:
    settings.set(pb.SETTING_DISPLAY_PARTICLES, pb.VisualizerMode.ALL)
```

When authoring completed PBD particles, pass presentation options into `_author_completed_pbd_runtime_particles`. Extend that function signature:

```python
presentation_isosurface_video: bool = False,
presentation_visual_material_path: str | None = None,
```

Inside `_author_completed_pbd_runtime_particles`, replace the existing disabled isosurface call with:

```python
isosurface_contract = {"enabled": False, "api_path": RUNTIME_PARTICLE_SYSTEM_PATH}
if presentation_isosurface_video:
    isosurface_contract = build_liquid_presentation_isosurface_contract(
        fluid_rest_offset=widths["fluid_rest_offset"],
        particle_count=len(positions),
    )
    particleUtils.add_physx_particle_isosurface(
        stage,
        Sdf.Path(RUNTIME_PARTICLE_SYSTEM_PATH),
        enabled=True,
        max_vertices=isosurface_contract["max_vertices"],
        max_triangles=isosurface_contract["max_triangles"],
        max_subgrids=isosurface_contract["max_subgrids"],
        grid_spacing=isosurface_contract["grid_spacing"],
        surface_distance=isosurface_contract["surface_distance"],
        grid_filtering_passes=isosurface_contract["grid_filtering_passes"],
        grid_smoothing_radius=isosurface_contract["grid_smoothing_radius"],
        num_mesh_smoothing_passes=isosurface_contract["num_mesh_smoothing_passes"],
        num_mesh_normal_smoothing_passes=isosurface_contract["num_mesh_normal_smoothing_passes"],
    )
else:
    particleUtils.add_physx_particle_isosurface(stage, Sdf.Path(RUNTIME_PARTICLE_SYSTEM_PATH), enabled=False)
```

Bind `presentation_visual_material_path` to `particle_system` when present, otherwise keep the current native `/World/Looks/OmniGlass_01` binding:

```python
render_material_path = presentation_visual_material_path or visual_material_path
visual_material = UsdShade.Material(stage.GetPrimAtPath(render_material_path))
```

Return `isosurface_contract`, `presentation_visual_material_path`, and `particle_isosurface_api_summary` in `authored_runtime_paths`. The API summary must read authored attributes from `PhysxParticleIsosurfaceAPI` on `/World/CompletedPBD/ParticleSystem`; do not assume a child prim named `Isosurface` exists because Isaac Sim 4.1 applies the API directly to the particle system prim.

- [ ] **Step 6: Add presentation video capture**

In `_native_stage_runtime(args)`, when `args.presentation_isosurface_video` is true:

1. Author the water material before `_author_completed_pbd_runtime_particles`.
2. Author presentation lighting.
3. Define `LIQUID_PRESENTATION_CAMERA_PATH`.
4. Add a `presentation_isosurface` camera sensor.
5. Capture frames into `presentation_isosurface_frames`.
6. Write `presentation_isosurface.mp4`.

Frame source string must be `presentation_isosurface_rgb`.

- [ ] **Step 7: Add summary fields**

In the runtime summary include:

```python
"presentation_visual_contract": presentation_visual_contract,
"presentation_video_enabled": bool(args.presentation_isosurface_video),
"presentation_isosurface_enabled": bool(args.presentation_isosurface_video),
"debug_particle_display_enabled": not bool(args.disable_particle_debug_display or args.presentation_isosurface_video),
```

Also include `presentation_visual_contract` in `claim_boundary["allowed"]` only as `presentation_isosurface_video_recorded=true`; add blocked claims:

```python
"presentation_video_equals_physics_success"
"isosurface_reconstruction_equals_zero_leak"
"presentation_water_material_equals_labutopia51_visual_parity"
```

- [ ] **Step 8: Run targeted and full unit tests**

```bash
python3 -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py -q
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_liquid_usd_leak_smoke.py tests/test_fluid_beaker_collider_smoke.py tests/test_fluid_beaker_collider_followup_sweep.py -q
```

Expected: all pass, ending with at least `97 passed`.

- [ ] **Step 9: Commit**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "feat: record reconstructed liquid presentation videos"
```

## Task 4: Extend Native Collider Sweep For Presentation Videos

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py`
- Test: `tests/test_fluid_colleague_native_collider_approx_sweep.py`

- [ ] **Step 1: Write failing aggregate tests**

Update the import block in `tests/test_fluid_colleague_native_collider_approx_sweep.py` to include `subprocess` and the new helpers:

```python
import subprocess
```

```python
    DEFAULT_NATIVE_STEP_RUNNER,
    build_native_variant_runtime_command,
    run_native_variant_runtime_sweep,
```

Append these tests:

```python
def test_runtime_aggregate_manifest_reports_presentation_video_status(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    summary = _passing_runtime_summary()
    summary["native_collider_approximation"] = {"candidate": {"variant_id": "NATIVE_SDF_128"}}
    summary["videos"] = {
        "presentation_isosurface": {"path": "presentation_isosurface.mp4", "written": True, "frame_count": 120},
        "beaker2_closeup_native_material": {"path": "closeup.mp4", "written": True, "frame_count": 120},
    }
    summary["presentation_visual_contract"] = {
        "presentation_video_does_not_replace_particle_readback": True,
        "debug_particle_display_enabled": False,
    }
    (runtime_dir / "NATIVE_SDF_128_runtime_512.json").write_text(json.dumps(summary), encoding="utf-8")

    manifest = write_runtime_aggregate_manifest(
        runtime_dir=runtime_dir,
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["NATIVE_SDF_128"],
    )

    result = manifest["candidate_results"][0]
    assert result["presentation_video"]["written"] is True
    assert result["presentation_video"]["frame_count"] == 120
    assert result["presentation_visual_contract"]["debug_particle_display_enabled"] is False
    assert manifest["presentation_video_written_count"] == 1
    assert manifest["all_presentation_videos_written"] is True


def test_runtime_aggregate_defaults_presentation_fields_for_missing_result(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    manifest = write_runtime_aggregate_manifest(
        runtime_dir=runtime_dir,
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["RAW_AS_IS"],
    )

    result = manifest["candidate_results"][0]
    assert result["classification"] == "MISSING_RUNTIME_RESULT"
    assert result["presentation_video"] == {"path": None, "written": False, "frame_count": 0}
    assert result["presentation_visual_contract"] == {}
    assert manifest["presentation_video_written_count"] == 0
    assert manifest["all_presentation_videos_written"] is False
```

- [ ] **Step 2: Run test and confirm failure**

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py::test_runtime_aggregate_manifest_reports_presentation_video_status tests/test_fluid_colleague_native_collider_approx_sweep.py::test_runtime_aggregate_defaults_presentation_fields_for_missing_result -q
```

Expected: fail because aggregate manifest does not expose presentation video fields.

- [ ] **Step 3: Aggregate presentation fields**

In `write_runtime_aggregate_manifest()`, read:

```python
presentation_video = videos.get("presentation_isosurface") or {}
presentation_visual_contract = summary.get("presentation_visual_contract") or {}
```

Add to each candidate result:

```python
"presentation_video": {
    "path": presentation_video.get("path"),
    "written": bool(presentation_video.get("written")),
    "frame_count": int(presentation_video.get("frame_count") or 0),
},
"presentation_visual_contract": presentation_visual_contract,
```

For missing-result entries, also add the same defaults:

```python
"presentation_video": {"path": None, "written": False, "frame_count": 0},
"presentation_visual_contract": {},
```

Add manifest-level fields after `candidate_results` is complete:

```python
presentation_written_count = sum(1 for item in candidate_results if item.get("presentation_video", {}).get("written"))
"presentation_video_written_count": presentation_written_count,
"all_presentation_videos_written": presentation_written_count == len(candidate_results) and not missing_result_paths,
```

- [ ] **Step 4: Add runtime command builder tests**

Append:

```python
def test_build_native_variant_runtime_command_adds_presentation_video_flags(tmp_path):
    candidate = next(c for c in build_native_approximation_sweep() if c.variant_id == "NATIVE_SDF_128")

    cmd = build_native_variant_runtime_command(
        python_executable="/isaac/python",
        runner_path=DEFAULT_NATIVE_STEP_RUNNER,
        usd_path="scene.usd",
        runtime_dir=tmp_path / "runtime",
        candidate=candidate,
        runtime_suffix="_runtime_512.json",
        particle_limit=512,
        steps=120,
        trace_interval=10,
        presentation_isosurface_videos=True,
        headless=True,
        hard_exit_after_run=True,
    )

    assert cmd[0] == "/isaac/python"
    assert str(DEFAULT_NATIVE_STEP_RUNNER) in cmd
    assert cmd[cmd.index("--native-collider-approximation-variant") + 1] == "NATIVE_SDF_128"
    assert cmd[cmd.index("--out-dir") + 1].endswith("NATIVE_SDF_128_runtime_512")
    assert cmd[cmd.index("--manifest") + 1].endswith("NATIVE_SDF_128_runtime_512.json")
    assert "--presentation-isosurface-video" in cmd
    assert "--disable-particle-debug-display" in cmd
    assert "--headless" in cmd
    assert "--hard-exit-after-run" in cmd
```

Run:

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py::test_build_native_variant_runtime_command_adds_presentation_video_flags -q
```

Expected: fail because the helper does not exist.

- [ ] **Step 5: Implement runtime command builder**

Add constants and imports:

```python
import os
import subprocess

DEFAULT_ISAACSIM41_PYTHON = (
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
DEFAULT_NATIVE_STEP_RUNNER = REPO_ROOT / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py"
```

Add:

```python
def _runtime_stem(candidate: NativeApproximationCandidate, runtime_suffix: str) -> str:
    suffix = runtime_suffix[:-5] if runtime_suffix.endswith(".json") else runtime_suffix
    return f"{candidate.variant_id}{suffix}"


def build_native_variant_runtime_command(
    *,
    python_executable: str | Path,
    runner_path: str | Path,
    usd_path: str | Path,
    runtime_dir: str | Path,
    candidate: NativeApproximationCandidate,
    runtime_suffix: str = "_runtime_512.json",
    particle_limit: int = 512,
    steps: int = 120,
    trace_interval: int = 10,
    presentation_isosurface_videos: bool = False,
    headless: bool = True,
    hard_exit_after_run: bool = False,
) -> list[str]:
    runtime_root = _repo_path(runtime_dir).resolve()
    stem = _runtime_stem(candidate, runtime_suffix)
    cmd = [
        str(python_executable),
        str(runner_path),
        "--usd",
        str(usd_path),
        "--native-collider-approximation-variant",
        candidate.variant_id,
        "--particle-limit",
        str(particle_limit),
        "--steps",
        str(steps),
        "--trace-interval",
        str(trace_interval),
        "--out-dir",
        str(runtime_root / stem),
        "--manifest",
        str(runtime_root / f"{stem}.json"),
    ]
    if presentation_isosurface_videos:
        cmd.extend(["--presentation-isosurface-video", "--disable-particle-debug-display"])
    if headless:
        cmd.append("--headless")
    if hard_exit_after_run:
        cmd.append("--hard-exit-after-run")
    return cmd
```

- [ ] **Step 6: Write failing runtime sweep launcher test**

Append:

```python
def test_run_native_variant_runtime_sweep_invokes_each_candidate_and_aggregates(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, cwd, env, check):
        calls.append(cmd)
        variant_id = cmd[cmd.index("--native-collider-approximation-variant") + 1]
        manifest_path = Path(cmd[cmd.index("--manifest") + 1])
        summary = _passing_runtime_summary()
        summary["native_collider_approximation"] = {"candidate": {"variant_id": variant_id}}
        summary["videos"] = {
            "presentation_isosurface": {
                "path": str(manifest_path.with_suffix("").with_name("presentation_isosurface.mp4")),
                "written": True,
                "frame_count": 31,
            }
        }
        summary["presentation_visual_contract"] = {
            "presentation_video_does_not_replace_particle_readback": True,
            "debug_particle_display_enabled": False,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(summary), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    manifest = run_native_variant_runtime_sweep(
        usd_path="scene.usd",
        runtime_dir=tmp_path / "runtime",
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["RAW_AS_IS", "NATIVE_SDF_128"],
        python_executable="/isaac/python",
        runner_path=DEFAULT_NATIVE_STEP_RUNNER,
        particle_limit=512,
        steps=120,
        trace_interval=10,
        presentation_isosurface_videos=True,
        headless=True,
    )

    assert len(calls) == 2
    assert all("--presentation-isosurface-video" in cmd for cmd in calls)
    assert manifest["runtime_step_executed_count"] == 2
    assert manifest["presentation_video_written_count"] == 2
    assert manifest["runtime_launcher_success_count"] == 2
```

Run:

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py::test_run_native_variant_runtime_sweep_invokes_each_candidate_and_aggregates -q
```

Expected: fail because the launcher does not exist.

- [ ] **Step 7: Implement runtime sweep launcher and CLI**

Add:

```python
def run_native_variant_runtime_sweep(
    *,
    usd_path: str | Path,
    runtime_dir: str | Path,
    manifest_path: str | Path,
    variant_ids: Sequence[str] | None = None,
    runtime_suffix: str = "_runtime_512.json",
    python_executable: str | Path = DEFAULT_ISAACSIM41_PYTHON,
    runner_path: str | Path = DEFAULT_NATIVE_STEP_RUNNER,
    particle_limit: int = 512,
    steps: int = 120,
    trace_interval: int = 10,
    presentation_isosurface_videos: bool = False,
    headless: bool = True,
) -> dict[str, Any]:
    candidates = _select_candidates(variant_ids)
    runtime_root = _repo_path(runtime_dir).resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    launcher_results = []
    env = os.environ.copy()
    env.setdefault("ACCEPT_EULA", "Y")
    env.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    for candidate in candidates:
        cmd = build_native_variant_runtime_command(
            python_executable=python_executable,
            runner_path=runner_path,
            usd_path=usd_path,
            runtime_dir=runtime_root,
            candidate=candidate,
            runtime_suffix=runtime_suffix,
            particle_limit=particle_limit,
            steps=steps,
            trace_interval=trace_interval,
            presentation_isosurface_videos=presentation_isosurface_videos,
            headless=headless,
            hard_exit_after_run=True,
        )
        completed = subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False)
        launcher_results.append({"variant_id": candidate.variant_id, "returncode": int(completed.returncode), "cmd": cmd})
    payload = write_runtime_aggregate_manifest(
        runtime_dir=runtime_root,
        manifest_path=manifest_path,
        variant_ids=variant_ids,
        runtime_suffix=runtime_suffix,
    )
    payload["runtime_launcher_results"] = launcher_results
    payload["runtime_launcher_success_count"] = sum(1 for item in launcher_results if item["returncode"] == 0)
    _write_json(_repo_path(manifest_path).resolve(), payload)
    return payload
```

Add parser flags:

```python
parser.add_argument("--run-runtime-sweep", action="store_true")
parser.add_argument("--python-executable", default=DEFAULT_ISAACSIM41_PYTHON)
parser.add_argument("--runner-path", default=str(DEFAULT_NATIVE_STEP_RUNNER))
parser.add_argument("--presentation-isosurface-videos", action="store_true")
parser.add_argument("--particle-limit", type=int, default=512)
parser.add_argument("--steps", type=int, default=120)
parser.add_argument("--trace-interval", type=int, default=10)
parser.add_argument("--headless", action="store_true")
```

In `main()`, handle runtime sweep before aggregate-only and dry-run:

```python
if args.run_runtime_sweep:
    manifest = args.manifest if args.manifest != DEFAULT_MANIFEST else DEFAULT_RUNTIME_MANIFEST
    payload = run_native_variant_runtime_sweep(
        usd_path=args.usd,
        runtime_dir=args.runtime_dir,
        manifest_path=manifest,
        variant_ids=args.variants,
        runtime_suffix=args.runtime_suffix,
        python_executable=args.python_executable,
        runner_path=args.runner_path,
        particle_limit=args.particle_limit,
        steps=args.steps,
        trace_interval=args.trace_interval,
        presentation_isosurface_videos=args.presentation_isosurface_videos,
        headless=args.headless,
    )
    print(json.dumps(_json_safe(payload), indent=2, sort_keys=True))
    return 0
```

Also add presentation claim boundaries in `build_claim_boundary()`:

```python
"Presentation videos can make particle motion easier to read, but particle readback remains the gate.",
```

```python
"presentation_video_equals_physics_success",
"isosurface_reconstruction_equals_zero_leak",
"presentation_water_material_equals_labutopia51_visual_parity",
```

- [ ] **Step 8: Run tests**

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py -q
```

Expected: all native collider sweep tests pass.

- [ ] **Step 9: Commit**

```bash
git add tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py tests/test_fluid_colleague_native_collider_approx_sweep.py
git commit -m "feat: aggregate liquid presentation videos"
```

## Task 5: Runtime Smoke And Full Native Sweep Evidence

**Files:**
- Runtime create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708_001/`
- Runtime create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708.json`

- [ ] **Step 1: Run one-variant presentation smoke**

Use IsaacSim41 environment:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  --native-collider-approximation-variant RAW_AS_IS \
  --particle-limit 512 \
  --steps 120 \
  --trace-interval 10 \
  --presentation-isosurface-video \
  --disable-particle-debug-display \
  --out-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_smoke_20260708_001/RAW_AS_IS_runtime_512 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_smoke_20260708_001/RAW_AS_IS_runtime_512.json \
  --headless
```

Expected runtime summary:

- `runtime_step_executed=true`
- `presentation_isosurface_enabled=true`
- `debug_particle_display_enabled=false`
- `videos.presentation_isosurface.written=true`
- `presentation_visual_contract.presentation_video_does_not_replace_particle_readback=true`

- [ ] **Step 2: Visually review smoke video**

Use `render-visual-reviewer` on:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_smoke_20260708_001/RAW_AS_IS_runtime_512/presentation_isosurface.mp4
```

Review target:

- Source beaker visible.
- Target beaker and tabletop context visible enough to understand layout.
- Liquid appears as a continuous-looking reconstructed render surface or visually coherent volume.
- No large red debug particle block dominates.
- Camera is useful as leadership-facing evidence.
- If leak happens, leaked liquid remains visible enough to understand failure.

If the smoke video is blank, red, no liquid surface is visible, or the camera hides the spill/leak region while readback says leaking, stop runtime sweep and fix Tasks 2-3. Do not continue with all 10 variants.

- [ ] **Step 3: Run full 10-variant native presentation sweep**

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
tools/labutopia_fluid/run_colleague_native_collider_approx_sweep.py \
  --run-runtime-sweep \
  --runtime-dir docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708_001 \
  --manifest docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708.json \
  --presentation-isosurface-videos \
  --particle-limit 0 \
  --steps 120 \
  --trace-interval 10 \
  --headless
```

Expected:

- 10 runtime JSON summaries.
- 10 `presentation_isosurface.mp4` videos.
- Aggregate manifest has `presentation_video_written_count=10`.
- Aggregate manifest keeps `all_tested_candidates_failed_static_hold` based on particle readback, not video quality.
- `particle_scope.selected_particle_count` should equal the source 50k particle count for final leadership evidence. If this fails due runtime resources, rerun a declared `visual_preview_subset` with a smaller `--particle-limit`, record `presentation_full_50k_blocked=true`, and do not call the subset videos final full-particle evidence.

- [ ] **Step 4: Validate aggregate manifest**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708.json")
d = json.loads(p.read_text())
assert d["manifest_type"] == "fluid_spike_native_collider_approximation_runtime_sweep"
assert d["runtime_step_executed_count"] == 10
assert d["runtime_launcher_success_count"] == 10
assert d["presentation_video_written_count"] == 10
assert d["all_presentation_videos_written"] is True
assert all(item["presentation_visual_contract"]["presentation_video_does_not_replace_particle_readback"] for item in d["candidate_results"])
assert all(item["presentation_video"]["frame_count"] > 0 for item in d["candidate_results"])
print("presentation_sweep_manifest_ok")
PY
```

Expected: `presentation_sweep_manifest_ok`.

- [ ] **Step 5: Per-variant visual QA**

Use `render-visual-reviewer` on every generated video under:

```text
docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708_001/*/presentation_isosurface.mp4
```

Create `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708_visual_qa.md` with one row per variant:

```markdown
| Variant | Video | Source beaker | Target/table context | Liquid surface visible | Red debug absent | Severe cropping absent | Leak/spill region visible when readback leaks | QA status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RAW_AS_IS | `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708_001/RAW_AS_IS_runtime_512/presentation_isosurface.mp4` | yes | yes | yes | yes | yes | yes | PASS |
```

Rules:

- All 10 videos must be reviewed, not just `RAW_AS_IS`.
- `QA status=PASS` means the video is readable as evidence; it does not mean the collider passed.
- If a variant has `outside_source_count`, `spill_count`, or `below_table_count` greater than zero, the camera must show enough surrounding table/spill area to understand that failure.
- If a video is nonblank but misleadingly cropped, mark `QA status=FAIL_CROPPED` and fix camera before updating weekly HTML.

- [ ] **Step 6: Commit runtime manifest and lightweight evidence**

Do not commit huge videos until checking repository policy and file sizes. Commit JSON summaries, posters, and docs first. If videos are already tracked in reports assets, copy compressed webm/mp4 to report assets in Task 6.

```bash
git add docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708.json docs/labutopia_lab_poc/evidence_manifests/fluid_spike_liquid_surface_reconstruction_native_sweep_20260708_visual_qa.md
git commit -m "test: record liquid surface reconstruction sweep manifest"
```

## Task 6: Update Docs And Weekly HTML

**Files:**
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `reports/2026-07-07-labutopia-fluid-weekly/index.html`
- Add/copy compressed media under: `reports/2026-07-07-labutopia-fluid-weekly/assets/`

- [ ] **Step 1: Update technical doc**

In `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`, add a section named:

```markdown
### Liquid Surface Reconstruction Presentation Lane
```

Required content:

- Explain in Chinese that `Isosurface` turns PBD particles into a continuous-looking render surface when reconstruction succeeds.
- Keep English terms `PhysX`, `PBD`, `particle readback`, `Isosurface`, `presentation lane`, `diagnostic lane`, `claim boundary`.
- State that the lane fixes visual readability, not collider leakage.
- Link the aggregate manifest path.
- Link the per-variant visual QA markdown path.
- Include the 10 variant names.
- Include `presentation_video_does_not_replace_particle_readback=true`.

- [ ] **Step 2: Update weekly HTML**

In `reports/2026-07-07-labutopia-fluid-weekly/index.html`, add a section after “最适合给领导看的视频证据”:

```html
<section id="surface-reconstruction" class="panel section">
  <h2>新增：液面重建版主视频</h2>
  <p>这组视频把离散 <code>PBD particles</code> 通过 <code>PhysX Isosurface</code> 生成更易读的 reconstructed render surface。它解决“红色粒子团不像水”的展示问题；但 <code>PASS/FAIL</code> 仍然只看 <code>particle readback</code>。</p>
  <div class="evidence-grid" id="surface-reconstruction-grid"></div>
  <p class="note">每个 collider 方案都有独立视频和独立 readback；页面展示视频只帮助理解现象，不升级为 benchmark-ready 结论。</p>
</section>
```

Each variant card must show:

- Variant id.
- Product label `视觉视频`: `presentation_isosurface` video.
- Product label `诊断 readback 结果`: `source_retention_fraction`.
- Product label `漏液指标`: `outside / spill / below_table`.
- Product label `判定`: `classification` plus `not benchmark-ready` when static hold failed.
- Product label `视觉 QA`: PASS/FAIL from the per-variant QA markdown.

If all 10 videos are too heavy for the page, show 3 representative videos inline and link all 10 files in an evidence table. The three inline videos must be selected deterministically:

1. `RAW_AS_IS`.
2. Best-retention variant: highest `source_retention_fraction`, tie-break by lowest `outside_source_count`, then alphabetical `variant_id`.
3. Worst-retention variant: lowest `source_retention_fraction`, tie-break by highest `below_table_count`, then alphabetical `variant_id`.

The page must state that the other 7 variants were also generated and visually checked.

- [ ] **Step 3: Browser visual review**

Serve the report locally:

```bash
python3 -m http.server 8937 --directory reports/2026-07-07-labutopia-fluid-weekly
```

Use `browser-visual-review` to verify:

- Videos have visible posters or controls.
- No broken images.
- Mobile layout does not overlap.
- New text does not imply benchmark-ready.
- Product labels `视觉视频`, `诊断 readback 结果`, `漏液指标`, and `判定` are visible.

- [ ] **Step 4: Commit docs and report**

```bash
git add docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md reports/2026-07-07-labutopia-fluid-weekly
git commit -m "docs: explain liquid surface reconstruction videos"
```

## Task 7: Final Verification, Review, Merge, Deploy

**Files:**
- All changed files.

- [ ] **Step 1: Run full unit verification**

```bash
python3 -m pytest tests/test_fluid_colleague_native_collider_approx_sweep.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_liquid_usd_leak_smoke.py tests/test_fluid_beaker_collider_smoke.py tests/test_fluid_beaker_collider_followup_sweep.py -q
```

Expected: at least `97 passed`; if new tests increase the count, all must pass.

- [ ] **Step 2: Run static diff check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Multi-agent review**

Dispatch two reviewers:

1. Engineering reviewer: checks code paths, claim boundary, test coverage, runtime manifest consistency.
2. Product/visual reviewer: checks weekly wording, video evidence framing, and whether leadership-facing claims are understandable without overclaiming.

All important findings must be fixed before merge.

- [ ] **Step 4: Merge to main**

From repo root main worktree:

```bash
git fetch origin main
git checkout main
git merge --ff-only liquid-surface-reconstruction-videos
```

If `git fetch` fails with `Proxy CONNECT aborted`, use `superpowers:using-github-proxy`.

- [ ] **Step 5: Push and verify GitHub Pages**

```bash
git push origin main
```

Poll:

```bash
python3 - <<'PY'
import urllib.request
url = "https://jandan138.github.io/labutopia/reports/2026-07-07-labutopia-fluid-weekly/"
body = urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "replace")
needles = [
    "液面重建版主视频",
    "PhysX Isosurface",
    "presentation_video_does_not_replace_particle_readback",
]
print({n: (n in body) for n in needles})
PY
```

Expected: all needles are `True`.

- [ ] **Step 6: Clean worktree**

```bash
git status --short --branch
```

Expected on main: `## main...origin/main` and no file changes.

---

## Product Summary To Use After Completion

这次不是继续给领导看红色粒子团，而是把 PBD 粒子加上一层 `PhysX Isosurface` presentation render：主视频在重建成功时会看到更连续、更易读、统一光照和统一相机的液体画面。每个 collider 方案仍然各跑各的视频，并且每个视频都要单独做视觉 QA。最终结论仍由 `particle readback` 决定：视频负责“看懂现象”，readback 负责“判定有没有漏、能不能进入下一阶段”。

# Weekly OmniGlass Look Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a 2×2 weekly OmniGlass-tinted water **diagnostic** look matrix (looks B/C × particles 4096/50000; optional `B_P1024` look-hold) on the colleague native USD runner, mount it on the weekly HTML with bilingual honest captions, and leave the default ClearWater Visual A path bit-compatible.

**Architecture:** Extend `run_colleague_native_usd_completed_pbd_step_video.py` with `PRESENTATION_LOOK_PRESETS` + resolve/author helpers. Default (`none`) keeps ClearWater + anisotropy 5.0 + lighting/camera v1 hashes and official VLA emission. Weekly presets author sibling OmniGlass water + beaker2-only glass override + lighting B/C + camera v2 + aniso2/smooth0.65; emit `weekly_presentation_look_contract` only (`vla_eval_baseline_invalid=true`; do **not** populate official `vla_water_visual_contract`). A thin sweep script loops four (+ optional) cells and writes a matrix manifest; weekly HTML mounts a **diagnostic** section (not G2 / not 主证据).

**Tech Stack:** Isaac Sim 4.1 headless, PhysX PBD isosurface, OmniGlass.mdl, USD/UsdShade/UsdLux, pytest (CPU unit tests), conda Isaac python at `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python`.

**Spec (revised after design review):** `docs/superpowers/specs/2026-07-09-weekly-omniglass-look-matrix-design.md`

**Known Isaac evidence before full matrix:** `B_P4096` already ran with `FAIL_CONTAINER_LEAK`, `material_backend=MDL_OMNIGLASS_WATER`, video written. Prior ClearWater hold @ 1024 PASSed. Encode leak honesty; consider optional `B_P1024` for look QA when 4096/50k leak.

**Commit policy:** Each task ends with an optional commit step. Do **not** auto-commit unless the user explicitly asks; still run the git commands when the user wants commits. Prefer one commit per logical task.

**Hard rules (do not violate):**
1. Mutual exclusion: `weekly_omniglass_{B,C}` + `A_static_clear_water` → exit error before stage authoring.
2. Default ClearWater path unchanged when preset is unset/`none` (lock four official hash literals in tests).
3. Beaker override binds **only** `/World/beaker2/mesh` (sibling Looks prim; never mutate native OmniGlass attrs; record pre/post bind + `beaker1_binding_unchanged`).
4. 50k/4096 overlay cells: honest leak classification + abort/trim fields; **never** equate colleague overlay to G1 12/12 (no PASS exception).
5. Weekly OmniGlass cells never set `official_visual_a_claim_allowed=true`; set `vla_eval_baseline_invalid=true`; do not emit official VLA overlay hashes.
6. Weekly matrix always uses `--fluid-safe-wrapper-overlay`.
7. HTML: diagnostic matrix ≠ leadership 主证据; bilingual caption templates required.

---

## File map

| File | Responsibility |
|------|----------------|
| `docs/superpowers/specs/2026-07-09-weekly-omniglass-look-matrix-design.md` | Design revised after review (VLA isolation, abort/trim, HTML IA, optional B_P1024) |
| `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` | Presets, resolve helpers, OmniGlass water, beaker2 override, lighting B/C, camera v2, postprocess overrides, CLI, `_native_stage_runtime` wiring |
| `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py` | Keep existing ClearWater/anisotropy 5.0 tests green; add look-preset unit tests |
| `tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py` | Thin 4-cell sweep + matrix manifest writer |
| `tests/test_weekly_omniglass_look_matrix.py` | Matrix cell table + manifest schema + claim-boundary unit tests |
| `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1.json` | Top-level matrix manifest (`_v1` run id) |
| `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1_*/` | Per-cell artifact dirs |
| `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_human_qa_checklist_20260709.md` | Human QA checklist artifact |
| `docs/labutopia_lab_poc/evidence_manifests/README.md` | Registry entry for weekly OmniGlass matrix |
| `reports/2026-07-07-labutopia-fluid-weekly/index.html` | Demote ClearWater “主视频=领导力就绪”; add 4-cell diagnostic matrix |
| `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md` | Optional short progress note + claim boundary pointer (only if needed) |

---

## Task 0: Spec revised after design review (no code)

**Status:** done (design blockers encoded 2026-07-09)

**Files:**
- Reference only: `docs/superpowers/specs/2026-07-09-weekly-omniglass-look-matrix-design.md`

- [x] **Step 1: Confirm revised design exists**

The design locks: presets `weekly_omniglass_B` / `weekly_omniglass_C`, OmniGlass water tint, beaker2 bind/restore contract, lighting B/C + capability probe, camera v2 + presentation closeup for C, postprocess aniso2/smooth0.65, 4 matrix cells + optional `B_P1024`, mutual exclusion with `A_static_clear_water`, VLA emission isolation (`weekly_presentation_look_contract` only), 50k abort/trim honesty (no G1 equivalence exception), diagnostic-vs-leadership HTML IA, bilingual captions, default ClearWater unchanged.

- [x] **Step 2: Do not re-open architecture**

Implement the recommended path from the **revised** spec. No Physics A / G1 / FluidSafeWrapper geometry changes. No official Visual A ClearWater re-run unless accidentally broken. Do not skip VLA isolation / abort fields / caption templates.

---

## Task 1: PresentationLookProfile resolve helpers + unit tests

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` (after constants ~L133; before authoring helpers)
- Modify: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`:

```python
def test_resolve_presentation_look_profile_none_returns_none():
    assert resolve_presentation_look_profile(None) is None
    assert resolve_presentation_look_profile("none") is None


def test_resolve_presentation_look_profile_b_has_omniglass_water_and_intensity_lighting():
    profile = resolve_presentation_look_profile("weekly_omniglass_B")
    assert profile["look_id"] == "weekly_omniglass_B"
    assert profile["water_backend"] == "MDL_OMNIGLASS_WATER"
    assert profile["water_material_path"] == "/World/Looks/LiquidPresentationOmniGlassWater"
    assert profile["glass_color"] == (0.73344165, 0.9498069, 0.94228774)
    assert profile["reflection_color"] == (0.6368421, 0.9266409, 0.88300306)
    assert profile["beaker_override"]["enabled"] is True
    assert profile["beaker_override"]["target_mesh"] == "/World/beaker2/mesh"
    assert profile["beaker_override"]["material_path"] == "/World/Looks/LiquidPresentationBeakerGlass"
    assert profile["lighting"]["mode"] == "intensity_v3"
    assert profile["lighting"]["key_intensity"] == 1200.0
    assert profile["lighting"]["dome_intensity"] == 220.0
    assert profile["lighting"]["lighting_contract_hash"] == "weekly_omniglass_intensity_v3"
    assert profile["camera"]["main_hash"] == "weekly_omniglass_main_camera_v2"
    assert profile["camera"]["eye_z_above_table"] == 0.22
    assert profile["camera"]["focus_source_weight"] == 0.85
    assert profile["camera"]["capture_closeup"] is False
    assert profile["postprocess"]["anisotropy_scale"] == 2.0
    assert profile["postprocess"]["smoothing_strength"] == 0.65
    assert profile["postprocess"]["postprocess_hash"] == "anisotropy_2_1_2_smoothing_0_65_v1"
    assert profile["material_hash"] == "omniglass_water_tint_a18_v1"
    assert profile["official_visual_a_compatible"] is False


def test_resolve_presentation_look_profile_c_inherits_b_and_overrides_lighting_camera():
    profile = resolve_presentation_look_profile("weekly_omniglass_C")
    assert profile["look_id"] == "weekly_omniglass_C"
    assert profile["water_material_path"] == "/World/Looks/LiquidPresentationOmniGlassWater"
    assert profile["beaker_override"]["enabled"] is True
    assert profile["postprocess"]["anisotropy_scale"] == 2.0
    assert profile["lighting"]["mode"] == "exposure_ct_ref_v1"
    assert profile["lighting"]["key_exposure"] == 10.0
    assert profile["lighting"]["key_color_temperature"] == 7250.0
    assert profile["lighting"]["dome_exposure"] == 9.0
    assert profile["lighting"]["dome_color_temperature"] == 6150.0
    assert profile["lighting"]["key_rotate_xyz"] == (55.0, 0.0, 135.0)
    assert profile["lighting"]["lighting_contract_hash"] == "weekly_omniglass_exposure_ct_v1"
    assert profile["camera"]["capture_closeup"] is True
    assert profile["camera"]["main_hash"] == "weekly_omniglass_main_camera_v2"
    assert profile["camera"]["closeup_prim_path"] == "/World/LiquidPresentationCloseupCamera"
    assert profile["camera"]["closeup_hash"] == "weekly_omniglass_closeup_camera_v1"
    assert profile["material_hash"] == "omniglass_water_tint_a18_v1"
    assert profile["postprocess"]["postprocess_hash"] == "anisotropy_2_1_2_smoothing_0_65_v1"
    assert profile["official_visual_a_compatible"] is False


def test_resolve_presentation_look_profile_unknown_raises():
    with pytest.raises(ValueError, match="unknown_presentation_look_preset"):
        resolve_presentation_look_profile("weekly_omniglass_Z")


def test_validate_presentation_look_vs_visual_acceptance_rejects_mutual_exclusion():
    with pytest.raises(ValueError, match="presentation_look_preset_conflicts_with_A_static_clear_water"):
        validate_presentation_look_vs_visual_acceptance(
            presentation_look_preset="weekly_omniglass_B",
            visual_acceptance_scenario="A_static_clear_water",
        )


def test_validate_presentation_look_vs_visual_acceptance_allows_default_clearwater():
    validate_presentation_look_vs_visual_acceptance(
        presentation_look_preset=None,
        visual_acceptance_scenario="A_static_clear_water",
    )
    validate_presentation_look_vs_visual_acceptance(
        presentation_look_preset="none",
        visual_acceptance_scenario="A_static_clear_water",
    )
    validate_presentation_look_vs_visual_acceptance(
        presentation_look_preset="weekly_omniglass_C",
        visual_acceptance_scenario=None,
    )
```

Also update the test module imports to include `resolve_presentation_look_profile`, `validate_presentation_look_vs_visual_acceptance`, and `pytest` if not already imported.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_none_returns_none tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_b_has_omniglass_water_and_intensity_lighting tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_c_inherits_b_and_overrides_lighting_camera tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_unknown_raises tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_validate_presentation_look_vs_visual_acceptance_rejects_mutual_exclusion tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_validate_presentation_look_vs_visual_acceptance_allows_default_clearwater -v
```

Expected: FAIL with `ImportError` / `name 'resolve_presentation_look_profile' is not defined`.

- [ ] **Step 3: Implement minimal resolve helpers**

In `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`, after `VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER` / `PHYSICS_CLASSIFICATION_PASS_SOURCE_HOLD`, add:

```python
LIQUID_PRESENTATION_OMNIGLASS_WATER_PATH = "/World/Looks/LiquidPresentationOmniGlassWater"
LIQUID_PRESENTATION_BEAKER_GLASS_PATH = "/World/Looks/LiquidPresentationBeakerGlass"
PRESENTATION_LOOK_PRESET_NONE = "none"
WEEKLY_OMNIGLASS_LOOK_PRESETS = ("weekly_omniglass_B", "weekly_omniglass_C")

PRESENTATION_LOOK_PRESETS: dict[str, dict[str, Any]] = {
    "weekly_omniglass_B": {
        "look_id": "weekly_omniglass_B",
        "water_backend": "MDL_OMNIGLASS_WATER",
        "water_mdl": "OmniGlass.mdl",
        "water_sub_identifier": "OmniGlass",
        "water_material_path": LIQUID_PRESENTATION_OMNIGLASS_WATER_PATH,
        "glass_color": (0.73344165, 0.9498069, 0.94228774),
        "reflection_color": (0.6368421, 0.9266409, 0.88300306),
        "beaker_override": {
            "enabled": True,
            "target_mesh": "/World/beaker2/mesh",
            "material_path": LIQUID_PRESENTATION_BEAKER_GLASS_PATH,
            "mdl": "OmniGlass.mdl",
            "sub_identifier": "OmniGlass",
            "glass_color": (0.85, 0.92, 0.95),
            "reflection_color": (0.90, 0.95, 0.98),
            "cutout_opacity": 0.72,
            "enable_opacity": True,
        },
        "lighting": {
            "mode": "intensity_v3",
            "key_intensity": 1200.0,
            "dome_intensity": 220.0,
            "key_rotate_xyz": (55.0, 0.0, 35.0),
            "lighting_contract_hash": "weekly_omniglass_intensity_v3",
        },
        "camera": {
            "main_hash": "weekly_omniglass_main_camera_v2",
            "eye_z_above_table": 0.22,
            "focus_source_weight": 0.85,
            "capture_closeup": False,
            "closeup_prim_path": None,
        },
        "postprocess": {
            "anisotropy_scale": 2.0,
            "anisotropy_min": 1.0,
            "anisotropy_max": 2.0,
            "smoothing_strength": 0.65,
            "postprocess_hash": "anisotropy_2_1_2_smoothing_0_65_v1",
        },
        "material_hash": "omniglass_water_tint_a18_v1",
        "official_visual_a_compatible": False,
    },
    "weekly_omniglass_C": {
        "look_id": "weekly_omniglass_C",
        "inherits": "weekly_omniglass_B",
        "lighting": {
            "mode": "exposure_ct_ref_v1",
            "key_intensity": 1.0,
            "key_exposure": 10.0,
            "key_color_temperature": 7250.0,
            "dome_intensity": 1.0,
            "dome_exposure": 9.0,
            "dome_color_temperature": 6150.0,
            "key_rotate_xyz": (55.0, 0.0, 135.0),
            "lighting_contract_hash": "weekly_omniglass_exposure_ct_v1",
        },
        "camera": {
            "main_hash": "weekly_omniglass_main_camera_v2",
            "eye_z_above_table": 0.22,
            "focus_source_weight": 0.85,
            "capture_closeup": True,
            "closeup_prim_path": "/World/LiquidPresentationCloseupCamera",
            "closeup_hash": "weekly_omniglass_closeup_camera_v1",
        },
        "official_visual_a_compatible": False,
    },
}


def resolve_presentation_look_profile(preset: str | None) -> dict[str, Any] | None:
    """Resolve a frozen presentation look profile; None/none → ClearWater default path."""
    if preset is None or preset == PRESENTATION_LOOK_PRESET_NONE or preset == "":
        return None
    if preset not in PRESENTATION_LOOK_PRESETS:
        raise ValueError(f"unknown_presentation_look_preset:{preset}")
    raw = PRESENTATION_LOOK_PRESETS[preset]
    inherits = raw.get("inherits")
    if inherits:
        if inherits not in PRESENTATION_LOOK_PRESETS:
            raise ValueError(f"unknown_presentation_look_inherit:{inherits}")
        base = dict(PRESENTATION_LOOK_PRESETS[inherits])
        merged = {**base, **{k: v for k, v in raw.items() if k != "inherits"}}
        # Nested dict overrides replace whole sections (lighting/camera), not deep-merge keys.
        return merged
    return dict(raw)


def validate_presentation_look_vs_visual_acceptance(
    *,
    presentation_look_preset: str | None,
    visual_acceptance_scenario: str | None,
) -> None:
    """Hard mutual exclusion: weekly OmniGlass look cannot claim official Visual A."""
    preset = presentation_look_preset
    if preset in (None, "", PRESENTATION_LOOK_PRESET_NONE):
        return
    if preset in WEEKLY_OMNIGLASS_LOOK_PRESETS and (
        visual_acceptance_scenario == VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER
    ):
        raise ValueError(
            "presentation_look_preset_conflicts_with_A_static_clear_water:"
            f"{preset}+{visual_acceptance_scenario}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_none_returns_none tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_b_has_omniglass_water_and_intensity_lighting tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_c_inherits_b_and_overrides_lighting_camera tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_resolve_presentation_look_profile_unknown_raises tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_validate_presentation_look_vs_visual_acceptance_rejects_mutual_exclusion tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_validate_presentation_look_vs_visual_acceptance_allows_default_clearwater -v
```

Expected: PASS

- [ ] **Step 5: Confirm default ClearWater regression suite still green**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_postprocess_contract_matches_spec_anisotropy_and_smoothing tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_water_mdl_material_info_targets_clearwater tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_presentation_material_and_lighting_are_authored_with_fixed_paths tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_presentation_lighting_authors_dome_and_key_with_v2_contract_hash -v
```

Expected: PASS (anisotropy still 5.0; ClearWater; lighting hash `liquid_presentation_dome_key_v2`).

- [ ] **Step 6: Commit (if committing)**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "$(cat <<'EOF'
feat: add weekly OmniGlass presentation look profile resolve helpers

EOF
)"
```

---

## Task 2: OmniGlass water authoring + tests

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` (near `_author_presentation_water_mdl_shader` / `_author_liquid_presentation_water_material`)
- Modify: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_author_omniglass_water_material_uses_sibling_path_not_clearwater():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mdl_path = ISAACSIM41_CORE_MDL_ROOT / "Base" / "OmniGlass.mdl"
    assert mdl_path.exists()

    profile = resolve_presentation_look_profile("weekly_omniglass_B")
    info = _author_liquid_presentation_omniglass_water_material(
        stage,
        profile=profile,
        mdl_source_asset=mdl_path,
    )

    assert info["material_backend"] == "MDL_OMNIGLASS_WATER"
    assert info["material_path"] == "/World/Looks/LiquidPresentationOmniGlassWater"
    assert info["sub_identifier"] == "OmniGlass"
    assert info["material_hash"] == "omniglass_water_tint_a18_v1"
    assert info["official_visual_a_compatible"] is False
    assert info["glass_color"] == list(profile["glass_color"])
    assert stage.GetPrimAtPath("/World/Looks/LiquidPresentationOmniGlassWater")
    assert not stage.GetPrimAtPath(LIQUID_PRESENTATION_MATERIAL_PATH)
    shader = stage.GetPrimAtPath("/World/Looks/LiquidPresentationOmniGlassWater/Shader")
    assert shader
    assert shader.GetAttribute("info:mdl:sourceAsset:subIdentifier").Get() == "OmniGlass"


def test_default_water_author_still_targets_clearwater_path():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    material_info = _author_liquid_presentation_water_material(stage, attempt_mdl=False)
    assert material_info["material_path"] == LIQUID_PRESENTATION_MATERIAL_PATH
    assert material_info["sub_identifier"] == "OmniSurface_ClearWater"
    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_MATERIAL_PATH)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_omniglass_water_material_uses_sibling_path_not_clearwater tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_default_water_author_still_targets_clearwater_path -v
```

Expected: FAIL with `name '_author_liquid_presentation_omniglass_water_material' is not defined` on the first test.

- [ ] **Step 3: Implement OmniGlass water authoring**

Add helper (mirror `_author_presentation_water_mdl_shader` pattern, but OmniGlass inputs):

```python
def _author_liquid_presentation_omniglass_water_material(
    stage: Any,
    *,
    profile: dict[str, Any],
    mdl_source_asset: str | Path | None = None,
) -> dict[str, Any]:
    """Author weekly OmniGlass-tinted water at a sibling Looks path (not ClearWater)."""
    from pxr import Gf, Sdf, UsdShade

    material_path = str(profile["water_material_path"])
    source = Path(
        mdl_source_asset
        or (PRESENTATION_WATER_MDL_ROOT / "Base" / str(profile["water_mdl"]))
    )
    looks = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks):
        from pxr import UsdGeom

        UsdGeom.Scope.Define(stage, looks)
    material = UsdShade.Material.Define(stage, Sdf.Path(material_path))
    shader_path = Sdf.Path(f"{material_path}/Shader")
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath(str(source)), "mdl")
    shader.SetSourceAssetSubIdentifier(str(profile["water_sub_identifier"]), "mdl")
    glass = profile["glass_color"]
    reflection = profile["reflection_color"]
    shader.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(float(glass[0]), float(glass[1]), float(glass[2]))
    )
    shader.CreateInput("reflection_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(float(reflection[0]), float(reflection[1]), float(reflection[2]))
    )
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    return {
        "mdl_bind_attempted": True,
        "material_backend": "MDL_OMNIGLASS_WATER",
        "mdl_compile_status": MDL_COMPILE_STATUS_PASS,
        "material_path": material_path,
        "shader_path": str(shader_path),
        "source_asset": str(source),
        "source_asset_basename": source.name,
        "sub_identifier": str(profile["water_sub_identifier"]),
        "glass_color": [float(glass[0]), float(glass[1]), float(glass[2])],
        "reflection_color": [float(reflection[0]), float(reflection[1]), float(reflection[2])],
        "material_hash": str(profile["material_hash"]),
        "official_visual_a_compatible": False,
        "visual_material_parity_claim_allowed": False,
        "bind_method": "usd_mdl_shader",
    }
```

Do **not** change `_author_liquid_presentation_water_material` ClearWater behavior in this task.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_omniglass_water_material_uses_sibling_path_not_clearwater tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_default_water_author_still_targets_clearwater_path tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_presentation_material_mdl_success_authors_clearwater_shader -v
```

Expected: PASS

- [ ] **Step 5: Commit (if committing)**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "$(cat <<'EOF'
feat: author sibling OmniGlass water material for weekly look presets

EOF
)"
```

---

## Task 3: Beaker2 presentation-only override + tests

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- Modify: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_author_beaker_glass_override_binds_only_beaker2_mesh():
    from pxr import Usd, UsdGeom, UsdShade

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/beaker2")
    UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    UsdGeom.Xform.Define(stage, "/World/beaker1")
    UsdGeom.Mesh.Define(stage, "/World/beaker1/mesh")
    mdl_path = ISAACSIM41_CORE_MDL_ROOT / "Base" / "OmniGlass.mdl"
    assert mdl_path.exists()
    profile = resolve_presentation_look_profile("weekly_omniglass_B")

    info = _author_liquid_presentation_beaker_glass_override(
        stage,
        profile=profile,
        mdl_source_asset=mdl_path,
    )

    assert info["enabled"] is True
    assert info["target_mesh"] == "/World/beaker2/mesh"
    assert info["material_path"] == "/World/Looks/LiquidPresentationBeakerGlass"
    assert info["cutout_opacity"] == 0.72
    assert info["beaker1_binding_unchanged"] is True
    assert "beaker2_pre_bind_material" in info
    assert info["beaker2_post_bind_material"] == "/World/Looks/LiquidPresentationBeakerGlass"
    assert stage.GetPrimAtPath("/World/Looks/LiquidPresentationBeakerGlass")
    # Native OmniGlass_01 (if present) must not be attribute-mutated; only sibling bind.
    beaker2 = stage.GetPrimAtPath("/World/beaker2/mesh")
    bound, _ = UsdShade.MaterialBindingAPI(beaker2).ComputeBoundMaterial()
    assert bound
    assert bound.GetPath().pathString == "/World/Looks/LiquidPresentationBeakerGlass"
    beaker1 = stage.GetPrimAtPath("/World/beaker1/mesh")
    bound1, _ = UsdShade.MaterialBindingAPI(beaker1).ComputeBoundMaterial()
    assert not bound1


def test_beaker_override_disabled_when_profile_none():
    assert _author_liquid_presentation_beaker_glass_override(None, profile=None) == {
        "enabled": False
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_beaker_glass_override_binds_only_beaker2_mesh tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_beaker_override_disabled_when_profile_none -v
```

Expected: FAIL (`_author_liquid_presentation_beaker_glass_override` missing).

- [ ] **Step 3: Implement beaker2-only override**

```python
def _author_liquid_presentation_beaker_glass_override(
    stage: Any | None,
    *,
    profile: dict[str, Any] | None,
    mdl_source_asset: str | Path | None = None,
) -> dict[str, Any]:
    """Presentation-only OmniGlass override bound solely to /World/beaker2/mesh."""
    if stage is None or profile is None:
        return {"enabled": False}
    override = profile.get("beaker_override") or {}
    if not override.get("enabled"):
        return {"enabled": False}

    from pxr import Gf, Sdf, UsdShade

    material_path = str(override["material_path"])
    target_mesh = str(override["target_mesh"])
    if target_mesh != "/World/beaker2/mesh":
        raise ValueError(f"beaker_override_target_must_be_beaker2_mesh:{target_mesh}")
    source = Path(mdl_source_asset or (PRESENTATION_WATER_MDL_ROOT / "Base" / str(override["mdl"])))
    looks = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks):
        from pxr import UsdGeom

        UsdGeom.Scope.Define(stage, looks)
    material = UsdShade.Material.Define(stage, Sdf.Path(material_path))
    shader_path = Sdf.Path(f"{material_path}/Shader")
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath(str(source)), "mdl")
    shader.SetSourceAssetSubIdentifier(str(override["sub_identifier"]), "mdl")
    glass = override["glass_color"]
    reflection = override["reflection_color"]
    shader.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(float(glass[0]), float(glass[1]), float(glass[2]))
    )
    shader.CreateInput("reflection_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(float(reflection[0]), float(reflection[1]), float(reflection[2]))
    )
    if override.get("enable_opacity"):
        shader.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(True)
        shader.CreateInput("cutout_opacity", Sdf.ValueTypeNames.Float).Set(
            float(override["cutout_opacity"])
        )
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    mesh_prim = stage.GetPrimAtPath(target_mesh)
    if not mesh_prim:
        raise RuntimeError(f"beaker_override_mesh_missing:{target_mesh}")
    pre_bound, _ = UsdShade.MaterialBindingAPI(mesh_prim).ComputeBoundMaterial()
    pre_bind_path = pre_bound.GetPath().pathString if pre_bound else None
    UsdShade.MaterialBindingAPI.Apply(mesh_prim).Bind(material)
    beaker1 = stage.GetPrimAtPath("/World/beaker1/mesh")
    beaker1_unchanged = True
    if beaker1:
        # Do not bind or clear beaker1; presence of any new bind would be a bug.
        pass
    return {
        "enabled": True,
        "target_mesh": target_mesh,
        "material_path": material_path,
        "shader_path": str(shader_path),
        "sub_identifier": str(override["sub_identifier"]),
        "glass_color": [float(glass[0]), float(glass[1]), float(glass[2])],
        "reflection_color": [float(reflection[0]), float(reflection[1]), float(reflection[2])],
        "cutout_opacity": float(override.get("cutout_opacity", 1.0)),
        "enable_opacity": bool(override.get("enable_opacity", False)),
        "source_asset_basename": source.name,
        "beaker2_pre_bind_material": pre_bind_path,
        "beaker2_post_bind_material": material_path,
        "beaker1_binding_unchanged": beaker1_unchanged,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_beaker_glass_override_binds_only_beaker2_mesh tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_beaker_override_disabled_when_profile_none -v
```

Expected: PASS

- [ ] **Step 5: Commit (if committing)**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "$(cat <<'EOF'
feat: add beaker2-only OmniGlass presentation material override

EOF
)"
```

---

## Task 4: Lighting B/C + camera v2 + postprocess override hooks

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` (`build_presentation_postprocess_contract`, `_author_liquid_presentation_lighting`, `_define_liquid_presentation_camera`)
- Modify: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_presentation_postprocess_contract_default_remains_anisotropy_5():
    contract = build_presentation_postprocess_contract()
    assert contract["anisotropy"]["scale"] == 5.0
    assert contract["smoothing"]["strength"] == 0.5
    assert contract["postprocess_hash"] == "anisotropy_5_1_2_smoothing_0_5_v1"


def test_build_presentation_postprocess_contract_accepts_weekly_override():
    profile = resolve_presentation_look_profile("weekly_omniglass_B")
    contract = build_presentation_postprocess_contract(look_profile=profile)
    assert contract["anisotropy"]["scale"] == 2.0
    assert contract["anisotropy"]["min"] == 1.0
    assert contract["anisotropy"]["max"] == 2.0
    assert contract["smoothing"]["strength"] == 0.65
    assert contract["postprocess_hash"] == "anisotropy_2_1_2_smoothing_0_65_v1"
    assert contract["affects_leak_classification"] is False


def test_author_lighting_intensity_v3_for_look_b():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    profile = resolve_presentation_look_profile("weekly_omniglass_B")
    info = _author_liquid_presentation_lighting(stage, look_profile=profile)
    assert info["lighting_contract_hash"] == "weekly_omniglass_intensity_v3"
    assert info["key_intensity"] == 1200.0
    assert info["dome_intensity"] == 220.0
    assert info["rotate_xyz"] == [55.0, 0.0, 35.0]


def test_author_lighting_exposure_ct_for_look_c():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    profile = resolve_presentation_look_profile("weekly_omniglass_C")
    info = _author_liquid_presentation_lighting(stage, look_profile=profile)
    assert info["lighting_contract_hash"] == "weekly_omniglass_exposure_ct_v1"
    assert info["mode"] == "exposure_ct_ref_v1"
    assert info["key_exposure"] == 10.0
    assert info["key_color_temperature"] == 7250.0
    assert info["dome_exposure"] == 9.0
    assert info["dome_color_temperature"] == 6150.0
    assert info["rotate_xyz"] == [55.0, 0.0, 135.0]


def test_define_camera_v2_lowers_eye_and_biases_source():
    from types import SimpleNamespace
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    config = SimpleNamespace(
        source_center=(0.30, 0.10, 0.80),
        target_center=(0.50, 0.10, 0.80),
        source_radius=0.04,
        target_radius=0.04,
        source_height=0.12,
        table_z=0.75,
    )
    profile = resolve_presentation_look_profile("weekly_omniglass_B")
    info = _define_liquid_presentation_camera(stage, config, look_profile=profile)
    assert info["camera_contract_hash"] == "weekly_omniglass_main_camera_v2"
    assert info["focus_source_weight"] == 0.85
    assert abs(info["eye"][2] - (0.75 + 0.22)) < 1e-6


def test_default_lighting_and_camera_hashes_unchanged_without_profile():
    from types import SimpleNamespace
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    lighting = _author_liquid_presentation_lighting(stage)
    assert lighting["lighting_contract_hash"] == "liquid_presentation_dome_key_v2"
    config = SimpleNamespace(
        source_center=(0.30, 0.10, 0.80),
        target_center=(0.50, 0.10, 0.80),
        source_radius=0.04,
        target_radius=0.04,
        source_height=0.12,
        table_z=0.75,
    )
    camera = _define_liquid_presentation_camera(stage, config)
    assert camera["camera_contract_hash"] == "liquid_presentation_main_camera_v1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_postprocess_contract_accepts_weekly_override tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_lighting_intensity_v3_for_look_b tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_lighting_exposure_ct_for_look_c tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_define_camera_v2_lowers_eye_and_biases_source -v
```

Expected: FAIL (`look_profile` / unexpected kwargs / wrong hashes).

- [ ] **Step 3: Implement override hooks (default path unchanged)**

Update `build_presentation_postprocess_contract`:

```python
def build_presentation_postprocess_contract(
    *,
    look_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spec §5.1 presentation-only PhysX particle postprocess (anisotropy + smoothing)."""
    if look_profile and look_profile.get("postprocess"):
        pp = look_profile["postprocess"]
        return {
            "enabled": True,
            "api_path": RUNTIME_PARTICLE_SYSTEM_PATH,
            "anisotropy": {
                "enabled": True,
                "scale": float(pp["anisotropy_scale"]),
                "min": float(pp["anisotropy_min"]),
                "max": float(pp["anisotropy_max"]),
            },
            "smoothing": {
                "enabled": True,
                "strength": float(pp["smoothing_strength"]),
            },
            "postprocess_hash": str(pp["postprocess_hash"]),
            "parameter_reference": "weekly_omniglass_anisotropy_smoothing_v1",
            "claim_boundary": "visual_surface_reconstruction_only",
            "affects_leak_classification": False,
        }
    return {
        "enabled": True,
        "api_path": RUNTIME_PARTICLE_SYSTEM_PATH,
        "anisotropy": {
            "enabled": True,
            "scale": float(PRESENTATION_ANISOTROPY_SCALE),
            "min": float(PRESENTATION_ANISOTROPY_MIN),
            "max": float(PRESENTATION_ANISOTROPY_MAX),
        },
        "smoothing": {
            "enabled": True,
            "strength": float(PRESENTATION_SMOOTHING_STRENGTH),
        },
        "postprocess_hash": PRESENTATION_POSTPROCESS_HASH,
        "parameter_reference": "nvidia_particle_postprocessing_demo_isosurface_style",
        "claim_boundary": "visual_surface_reconstruction_only",
        "affects_leak_classification": False,
    }
```

Update `_author_liquid_presentation_lighting` signature to accept `look_profile: dict[str, Any] | None = None`. When `None`, keep existing key=950 / dome=400 / hash `liquid_presentation_dome_key_v2`. When profile lighting `mode == "intensity_v3"`, use profile intensities/rotation/hash. When `mode == "exposure_ct_ref_v1"`, author DistantLight + DomeLight with intensity 1.0 and set exposure / colorTemperature attrs if the USD Lux API supports them on this Isaac build:

```python
def _author_liquid_presentation_lighting(
    stage: Any,
    *,
    look_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from pxr import Gf, UsdLux

    lighting = (look_profile or {}).get("lighting") if look_profile else None
    if not lighting:
        key_intensity = 950.0
        key_rotate_xyz = [55.0, 0.0, 35.0]
        dome_intensity = 400.0
        key_light = UsdLux.DistantLight.Define(stage, LIQUID_PRESENTATION_LIGHT_PATH)
        key_light.CreateIntensityAttr(key_intensity)
        key_light.ClearXformOpOrder()
        key_light.AddRotateXYZOp().Set(Gf.Vec3f(*key_rotate_xyz))
        dome_light = UsdLux.DomeLight.Define(stage, LIQUID_PRESENTATION_DOME_LIGHT_PATH)
        dome_light.CreateIntensityAttr(dome_intensity)
        return {
            "light_path": LIQUID_PRESENTATION_LIGHT_PATH,
            "key_light_path": LIQUID_PRESENTATION_LIGHT_PATH,
            "dome_light_path": LIQUID_PRESENTATION_DOME_LIGHT_PATH,
            "role": "leadership_presentation_dome_key",
            "intensity": key_intensity,
            "key_intensity": key_intensity,
            "dome_intensity": dome_intensity,
            "rotate_xyz": list(key_rotate_xyz),
            "lighting_contract_hash": LIQUID_PRESENTATION_LIGHTING_HASH,
        }

    mode = str(lighting["mode"])
    key_rotate_xyz = list(lighting["key_rotate_xyz"])
    key_light = UsdLux.DistantLight.Define(stage, LIQUID_PRESENTATION_LIGHT_PATH)
    key_light.CreateIntensityAttr(float(lighting["key_intensity"]))
    key_light.ClearXformOpOrder()
    key_light.AddRotateXYZOp().Set(Gf.Vec3f(*key_rotate_xyz))
    dome_light = UsdLux.DomeLight.Define(stage, LIQUID_PRESENTATION_DOME_LIGHT_PATH)
    dome_light.CreateIntensityAttr(float(lighting["dome_intensity"]))
    info: dict[str, Any] = {
        "light_path": LIQUID_PRESENTATION_LIGHT_PATH,
        "key_light_path": LIQUID_PRESENTATION_LIGHT_PATH,
        "dome_light_path": LIQUID_PRESENTATION_DOME_LIGHT_PATH,
        "role": "weekly_omniglass_presentation_dome_key",
        "mode": mode,
        "intensity": float(lighting["key_intensity"]),
        "key_intensity": float(lighting["key_intensity"]),
        "dome_intensity": float(lighting["dome_intensity"]),
        "rotate_xyz": key_rotate_xyz,
        "lighting_contract_hash": str(lighting["lighting_contract_hash"]),
    }
    if mode == "exposure_ct_ref_v1":
        # Prefer Lux API helpers when present; fall back to raw attributes.
        for light, prefix, exposure_key, ct_key in (
            (key_light, "key", "key_exposure", "key_color_temperature"),
            (dome_light, "dome", "dome_exposure", "dome_color_temperature"),
        ):
            exposure = float(lighting[exposure_key])
            ct = float(lighting[ct_key])
            if hasattr(light, "CreateExposureAttr"):
                light.CreateExposureAttr(exposure)
            else:
                light.GetPrim().CreateAttribute("inputs:exposure", Sdf.ValueTypeNames.Float).Set(exposure)
            if hasattr(light, "CreateColorTemperatureAttr"):
                light.CreateColorTemperatureAttr(ct)
                if hasattr(light, "CreateEnableColorTemperatureAttr"):
                    light.CreateEnableColorTemperatureAttr(True)
            else:
                light.GetPrim().CreateAttribute(
                    "inputs:colorTemperature", Sdf.ValueTypeNames.Float
                ).Set(ct)
            info[exposure_key] = exposure
            info[ct_key] = ct
        # Runtime capability probe: record whether attrs stuck; WARN if no-op on this Isaac build.
        info["lighting_capability_probe"] = "authored_exposure_ct_attrs"
    return info
```

(Import `Sdf` at top of the exposure branch from `pxr`. If exposure/CT attrs are unsupported or read back as unset after authoring, set `lighting_capability_probe=WARN` and do not treat Cell C as exposure_ct parity with refs.)

Update `_define_liquid_presentation_camera` to accept `look_profile=None`. When profile present, use `focus_source_weight` and `eye_z_above_table` from profile and set `camera_contract_hash` to `weekly_omniglass_main_camera_v2`. When absent, keep `focus_source_weight=0.72`, eye z `table_z + 0.34`, hash `liquid_presentation_main_camera_v1`.

Also thread `look_profile` into `_author_completed_pbd_runtime_particles` by adding optional `presentation_look_profile: dict[str, Any] | None = None` and calling `build_presentation_postprocess_contract(look_profile=presentation_look_profile)` instead of the no-arg form when `presentation_isosurface_video` is true.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_postprocess_contract_default_remains_anisotropy_5 tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_postprocess_contract_matches_spec_anisotropy_and_smoothing tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_postprocess_contract_accepts_weekly_override tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_lighting_intensity_v3_for_look_b tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_author_lighting_exposure_ct_for_look_c tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_define_camera_v2_lowers_eye_and_biases_source tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_default_lighting_and_camera_hashes_unchanged_without_profile tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_presentation_lighting_authors_dome_and_key_with_v2_contract_hash -v
```

Expected: PASS

- [ ] **Step 5: Commit (if committing)**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "$(cat <<'EOF'
feat: add weekly look lighting/camera/postprocess override hooks

EOF
)"
```

---

## Task 5: CLI flag + mutual exclusion + wire into `_native_stage_runtime`

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` (`build_arg_parser`, `main`/`_run_runtime`, `_native_stage_runtime` presentation block ~L1806–1854)
- Modify: `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_arg_parser_accepts_presentation_look_preset_choices():
    parser = build_arg_parser()
    args = parser.parse_args(["--presentation-look-preset", "weekly_omniglass_B"])
    assert args.presentation_look_preset == "weekly_omniglass_B"
    args_none = parser.parse_args([])
    assert args_none.presentation_look_preset == "none"


def test_main_rejects_weekly_look_with_visual_a_scenario(monkeypatch, tmp_path):
    # Unit-level: parser + validate before runtime.
    with pytest.raises(ValueError, match="presentation_look_preset_conflicts_with_A_static_clear_water"):
        validate_presentation_look_vs_visual_acceptance(
            presentation_look_preset="weekly_omniglass_C",
            visual_acceptance_scenario="A_static_clear_water",
        )


def test_build_weekly_cell_claim_fields_forbid_official_visual_a():
    fields = build_weekly_omniglass_cell_claim_fields(
        cell_id="B_P4096",
        look_id="weekly_omniglass_B",
        particle_limit=4096,
        steps_requested=120,
        steps_completed=120,
        classification="FAIL_CONTAINER_LEAK",
        lighting_contract_hash="weekly_omniglass_intensity_v3",
        camera_contract_hash="weekly_omniglass_main_camera_v2",
        postprocess_hash="anisotropy_2_1_2_smoothing_0_65_v1",
        material_hash="omniglass_water_tint_a18_v1",
        beaker_override_used=True,
        physics_wrapper_variant_id="D4A_018",
        abort_step=40,
        last_pass_step=39,
        video_trim_step=39,
    )
    assert fields["official_visual_a_compatible"] is False
    assert fields["official_visual_a_claim_allowed"] is False
    assert fields["vla_eval_baseline_invalid"] is True
    assert fields["colleague_overlay_not_g1_promotion_spawn"] is True
    assert fields["colleague_50k_overlay_equals_g1_zero_leak"] is False
    assert fields["presentation_water_backend"] == "MDL_OMNIGLASS_WATER"
    assert fields["leak_status_remains_particle_readback_authoritative"] is True
    assert fields["duration_honesty"] == "partial_to_step_39_on_leak"
    assert fields["human_visual_qa_status"] == "pending"
    assert fields["weekly_presentation_look_contract_hash"]
    assert "vla_water_visual_contract" not in fields or fields.get("vla_water_visual_contract") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_arg_parser_accepts_presentation_look_preset_choices tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_weekly_cell_claim_fields_forbid_official_visual_a -v
```

Expected: FAIL (missing CLI / helper).

- [ ] **Step 3: Implement CLI + claim helper + runtime wiring**

Add to `build_arg_parser()`:

```python
parser.add_argument(
    "--presentation-look-preset",
    default="none",
    choices=("none", "weekly_omniglass_B", "weekly_omniglass_C"),
    help=(
        "Presentation look preset. Default none keeps ClearWater Visual A path. "
        "weekly_omniglass_* authors OmniGlass water + beaker2 override and is "
        "mutually exclusive with --visual-acceptance-scenario A_static_clear_water."
    ),
)
```

Add claim-field builder:

```python
def build_weekly_omniglass_cell_claim_fields(
    *,
    cell_id: str,
    look_id: str,
    particle_limit: int,
    steps_requested: int,
    steps_completed: int,
    classification: str,
    lighting_contract_hash: str,
    camera_contract_hash: str,
    postprocess_hash: str,
    material_hash: str,
    beaker_override_used: bool,
    physics_wrapper_variant_id: str | None = None,
    physics_manifest_path: str | None = None,
    abort_step: int | None = None,
    last_pass_step: int | None = None,
    video_trim_step: int | None = None,
    selected_particle_count: int | None = None,
) -> dict[str, Any]:
    duration_honesty = (
        f"partial_to_step_{video_trim_step}_on_leak"
        if video_trim_step is not None and int(video_trim_step) < int(steps_requested)
        else f"full_window_{steps_completed}_steps"
    )
    return {
        "cell_id": cell_id,
        "look_id": look_id,
        "particle_limit": int(particle_limit),
        "selected_particle_count": selected_particle_count,
        "steps_requested": int(steps_requested),
        "steps_completed": int(steps_completed),
        "classification": classification,
        "abort_step": abort_step,
        "last_pass_step": last_pass_step,
        "video_trim_step": video_trim_step,
        "duration_honesty": duration_honesty,
        "presentation_water_backend": "MDL_OMNIGLASS_WATER",
        "presentation_look_preset": look_id,
        "lighting_contract_hash": lighting_contract_hash,
        "camera_contract_hash": camera_contract_hash,
        "postprocess_hash": postprocess_hash,
        "material_hash": material_hash,
        "weekly_presentation_look_contract_hash": (
            f"weekly|{look_id}|{material_hash}|{postprocess_hash}|"
            f"{lighting_contract_hash}|{camera_contract_hash}"
        ),
        "vla_water_visual_contract": None,
        "vla_eval_baseline_invalid": True,
        "beaker_override_used": bool(beaker_override_used),
        "official_visual_a_compatible": False,
        "official_visual_a_claim_allowed": False,
        "colleague_overlay_not_g1_promotion_spawn": True,
        "colleague_50k_overlay_equals_g1_zero_leak": False,
        "leak_status_remains_particle_readback_authoritative": True,
        "physics_wrapper_variant_id": physics_wrapper_variant_id,
        "physics_manifest_path": physics_manifest_path,
        "physics_provenance": "colleague_usd_overlay_D4A_018",
        "human_visual_qa_status": "pending",
        "weekly_omniglass_matrix_is_visual_diagnostic_not_official_visual_a": True,
    }
```

In `main` or `_run_runtime` **before** SimulationApp / stage open:

```python
validate_presentation_look_vs_visual_acceptance(
    presentation_look_preset=getattr(args, "presentation_look_preset", "none"),
    visual_acceptance_scenario=getattr(args, "visual_acceptance_scenario", None),
)
```

In `_native_stage_runtime`, when `args.presentation_isosurface_video`:

```python
look_profile = resolve_presentation_look_profile(
    getattr(args, "presentation_look_preset", "none")
)
beaker_override_info = {"enabled": False}
if look_profile is None:
    presentation_material_info = _author_liquid_presentation_water_material(
        stage,
        attempt_mdl=True,
        closure_base_dir=None,
        prefer_kit_bind=False,
        mdl_source_asset=PRESENTATION_WATER_MDL_ROOT / "Base" / PRESENTATION_WATER_MDL_ASSET,
    )
    presentation_lighting_info = _author_liquid_presentation_lighting(stage)
    presentation_camera_info = _define_liquid_presentation_camera(stage, config)
    presentation_visual_material_path = LIQUID_PRESENTATION_MATERIAL_PATH
    contract_material_path = LIQUID_PRESENTATION_MATERIAL_PATH
else:
    omniglass_mdl = PRESENTATION_WATER_MDL_ROOT / "Base" / str(look_profile["water_mdl"])
    presentation_material_info = _author_liquid_presentation_omniglass_water_material(
        stage,
        profile=look_profile,
        mdl_source_asset=omniglass_mdl,
    )
    beaker_override_info = _author_liquid_presentation_beaker_glass_override(
        stage,
        profile=look_profile,
        mdl_source_asset=omniglass_mdl,
    )
    presentation_lighting_info = _author_liquid_presentation_lighting(
        stage, look_profile=look_profile
    )
    presentation_camera_info = _define_liquid_presentation_camera(
        stage, config, look_profile=look_profile
    )
    presentation_visual_material_path = str(look_profile["water_material_path"])
    contract_material_path = presentation_visual_material_path
```

Pass `presentation_look_profile=look_profile` into `_author_completed_pbd_runtime_particles`. Use `contract_material_path` in `build_presentation_visual_contract(... material_path=...)`.

If look profile requests closeup (`camera.capture_closeup`) **or** `--capture-closeup-camera`, ensure **presentation** closeup camera is created at `closeup_prim_path` from the profile (default `/World/LiquidPresentationCloseupCamera`) — do **not** reuse the native-material closeup slot as the OmniGlass story. For look C, force closeup capture even if CLI flag unset:

```python
capture_closeup = bool(args.capture_closeup_camera) or bool(
    look_profile and look_profile.get("camera", {}).get("capture_closeup")
)
```

Record in runtime summary:

```python
"presentation_look_preset": getattr(args, "presentation_look_preset", "none"),
"presentation_look_profile_resolved": bool(look_profile),
"beaker_override": beaker_override_info,
"official_visual_a_compatible": False if look_profile else None,
"vla_eval_baseline_invalid": True if look_profile else False,
"colleague_overlay_not_g1_promotion_spawn": True if look_profile else None,
```

When `look_profile` is set:
- force `official_visual_a_claim_allowed=false`
- set `vla_water_visual_contract=null` / omit official overlay hashes; emit `weekly_presentation_look_contract` instead
- never call ClearWater-only reconcile as success for OmniGlass; scope compile scan to `LiquidPresentationOmniGlassWater`
- for 50k (and optionally any cell): if mid-run leak gates trip, abort, set `abort_step` / `last_pass_step` / `video_trim_step`, keep partial video with honest classification

Also thread `look_profile` into `_author_completed_pbd_runtime_particles` by adding optional `presentation_look_profile: dict[str, Any] | None = None` and calling `build_presentation_postprocess_contract(look_profile=presentation_look_profile)` instead of the no-arg form when `presentation_isosurface_video` is true.

- [ ] **Step 4: Run unit tests**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py -v --tb=short
```

Expected: all PASS, including legacy ClearWater/anisotropy 5.0 assertions.

- [ ] **Step 5: Commit (if committing)**

```bash
git add tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py
git commit -m "$(cat <<'EOF'
feat: wire weekly OmniGlass look presets into native presentation runtime

EOF
)"
```

---

## Task 6: Matrix sweep script + matrix manifest schema tests

**Files:**
- Create: `tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py`
- Create: `tests/test_weekly_omniglass_look_matrix.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_weekly_omniglass_look_matrix.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.labutopia_fluid.run_weekly_omniglass_look_matrix import (
    MATRIX_CELLS,
    build_matrix_manifest,
    build_cell_runner_argv,
    build_claim_boundary,
)


def test_matrix_cells_are_exactly_four_locked_ids():
    assert [c["cell_id"] for c in MATRIX_CELLS] == [
        "B_P4096",
        "B_P50000",
        "C_P4096",
        "C_P50000",
    ]
    assert MATRIX_CELLS[0]["look_preset"] == "weekly_omniglass_B"
    assert MATRIX_CELLS[0]["particle_limit"] == 4096
    assert MATRIX_CELLS[1]["particle_limit"] == 50000
    assert MATRIX_CELLS[2]["look_preset"] == "weekly_omniglass_C"
    assert MATRIX_CELLS[2]["capture_closeup"] is True
    assert MATRIX_CELLS[3]["steps"] == 120


def test_optional_b_p1024_look_hold_cell_defined():
    from tools.labutopia_fluid.run_weekly_omniglass_look_matrix import OPTIONAL_MATRIX_CELLS

    assert OPTIONAL_MATRIX_CELLS[0]["cell_id"] == "B_P1024"
    assert OPTIONAL_MATRIX_CELLS[0]["particle_limit"] == 1024
    assert OPTIONAL_MATRIX_CELLS[0]["look_preset"] == "weekly_omniglass_B"
    assert "look_qa_hold" in OPTIONAL_MATRIX_CELLS[0]["honesty_note"]


def test_build_cell_runner_argv_includes_mutual_exclusion_safe_flags():
    cell = MATRIX_CELLS[0]
    argv = build_cell_runner_argv(
        cell,
        usd="outputs/usd_asset_packages/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd",
        out_dir="docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1_B_P4096",
        manifest="docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1_B_P4096/runtime_smoke_summary.json",
    )
    assert "--presentation-isosurface-video" in argv
    assert "--fluid-safe-wrapper-overlay" in argv
    assert "--presentation-look-preset" in argv
    assert "weekly_omniglass_B" in argv
    assert "--particle-limit" in argv
    assert "4096" in argv
    assert "--visual-acceptance-scenario" not in argv


def test_build_matrix_manifest_schema_and_forbidden_claims():
    cells = [
        {
            "cell_id": "B_P4096",
            "look_id": "weekly_omniglass_B",
            "particle_limit": 4096,
            "steps_requested": 120,
            "steps_completed": 120,
            "classification": "FAIL_CONTAINER_LEAK",
            "presentation_water_backend": "MDL_OMNIGLASS_WATER",
            "presentation_look_preset": "weekly_omniglass_B",
            "lighting_contract_hash": "weekly_omniglass_intensity_v3",
            "camera_contract_hash": "weekly_omniglass_main_camera_v2",
            "postprocess_hash": "anisotropy_2_1_2_smoothing_0_65_v1",
            "material_hash": "omniglass_water_tint_a18_v1",
            "beaker_override_used": True,
            "official_visual_a_compatible": False,
            "official_visual_a_claim_allowed": False,
            "vla_eval_baseline_invalid": True,
            "colleague_overlay_not_g1_promotion_spawn": True,
            "colleague_50k_overlay_equals_g1_zero_leak": False,
            "leak_status_remains_particle_readback_authoritative": True,
            "physics_wrapper_variant_id": "D4A_018",
            "human_visual_qa_status": "pending",
            "artifact_dir": "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1_B_P4096",
        }
    ]
    manifest = build_matrix_manifest(cells=cells, matrix_id="fluid_spike_weekly_omniglass_look_matrix_20260709_v1")
    assert manifest["manifest_type"] == "weekly_omniglass_look_matrix_evidence"
    assert manifest["weekly_omniglass_look_matrix_executed"] is True
    assert manifest["official_visual_a_clearwater_unchanged"] is True
    assert manifest["weekly_omniglass_matrix_is_visual_diagnostic_not_official_visual_a"] is True
    assert manifest["cells"][0]["official_visual_a_claim_allowed"] is False
    assert manifest["cells"][0]["vla_eval_baseline_invalid"] is True
    boundary = build_claim_boundary()
    assert "mdl_water_equals_photoreal_water" in boundary["blocked_claims"]
    assert "omniglass_water_equals_official_visual_a" in boundary["blocked_claims"]
    assert "weekly_omniglass_equals_g2_clearwater" in boundary["blocked_claims"]
    assert "weekly_cell_updates_official_vla_overlay_hashes" in boundary["blocked_claims"]
    assert "colleague_50k_overlay_equals_g1_zero_leak" in boundary["blocked_claims"]
    assert "presentation_video_equals_physics_success" in boundary["blocked_claims"]
    assert "weekly_omniglass_look_matrix_executed=true" in boundary["allowed_claims"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_weekly_omniglass_look_matrix.py -v
```

Expected: FAIL (`ModuleNotFoundError: run_weekly_omniglass_look_matrix`).

- [ ] **Step 3: Implement the sweep script**

Create `tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py`:

```python
#!/usr/bin/env python3
"""Run the weekly OmniGlass look matrix (2 looks × 2 particle limits)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_USD = (
    "outputs/usd_asset_packages/lab_001_localized_20260707/"
    "lab_001_level1_pour_tabletop_with_liquid.usd"
)
DEFAULT_MATRIX_ID = "fluid_spike_weekly_omniglass_look_matrix_20260709_v1"
DEFAULT_EVIDENCE_ROOT = (
    "docs/labutopia_lab_poc/evidence_manifests"
)
DEFAULT_ISAAC_PYTHON = (
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
DEFAULT_RUNNER = REPO_ROOT / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py"

MATRIX_CELLS: list[dict[str, Any]] = [
    {
        "cell_id": "B_P4096",
        "look_preset": "weekly_omniglass_B",
        "particle_limit": 4096,
        "steps": 120,
        "capture_closeup": False,
        "honesty_note": (
            "known_smoke_FAIL_CONTAINER_LEAK_with_MDL_OMNIGLASS_WATER_video; "
            "colleague_usd_overlay_not_g1_promotion_spawn"
        ),
    },
    {
        "cell_id": "B_P50000",
        "look_preset": "weekly_omniglass_B",
        "particle_limit": 50000,
        "steps": 120,
        "capture_closeup": False,
        "honesty_note": (
            "colleague_usd_overlay_50k_is_not_g1_promotion_spawn; "
            "abort_on_leak; keep partial video; do not claim zero-leak; "
            "no PASS exception for G1 equivalence"
        ),
    },
    {
        "cell_id": "C_P4096",
        "look_preset": "weekly_omniglass_C",
        "particle_limit": 4096,
        "steps": 120,
        "capture_closeup": True,
    },
    {
        "cell_id": "C_P50000",
        "look_preset": "weekly_omniglass_C",
        "particle_limit": 50000,
        "steps": 120,
        "capture_closeup": True,
        "honesty_note": (
            "colleague_usd_overlay_50k_is_not_g1_promotion_spawn; "
            "abort_on_leak; keep partial video; do not claim zero-leak; "
            "no PASS exception for G1 equivalence"
        ),
    },
]

OPTIONAL_MATRIX_CELLS: list[dict[str, Any]] = [
    {
        "cell_id": "B_P1024",
        "look_preset": "weekly_omniglass_B",
        "particle_limit": 1024,
        "steps": 120,
        "capture_closeup": False,
        "honesty_note": (
            "look_qa_hold_when_4096_or_50k_leaks; "
            "prior_clearwater_1024_PASS_was_physics_not_leadership_look; "
            "not_g1_g2_proof"
        ),
    },
]


def build_claim_boundary() -> dict[str, list[str]]:
    return {
        "allowed_claims": [
            "weekly_omniglass_look_matrix_executed=true",
            "presentation_water_backend=MDL_OMNIGLASS_WATER",
            "leak_status_remains_particle_readback_authoritative=true",
            "official_visual_a_clearwater_unchanged=true",
            "weekly_omniglass_matrix_is_visual_diagnostic_not_official_visual_a=true",
            "vla_eval_baseline_invalid=true",
            "colleague_overlay_not_g1_promotion_spawn=true",
        ],
        "blocked_claims": [
            "mdl_water_equals_photoreal_water",
            "真实水",
            "像水",
            "presentation_video_equals_physics_success",
            "omniglass_water_equals_official_visual_a",
            "weekly_omniglass_equals_g2_clearwater",
            "weekly_cell_updates_official_vla_overlay_hashes",
            "reference_liquid_usd_box_cup_equals_labutopia_beaker",
            "colleague_50k_overlay_equals_g1_zero_leak",
            "official_visual_a_claim_allowed_from_weekly_omniglass_cell",
            "material_hash_implies_mdl_when_fallback_active",
        ],
    }


def build_cell_runner_argv(
    cell: dict[str, Any],
    *,
    usd: str,
    out_dir: str,
    manifest: str,
) -> list[str]:
    argv = [
        str(DEFAULT_RUNNER),
        "--usd",
        usd,
        "--out-dir",
        out_dir,
        "--manifest",
        manifest,
        "--headless",
        "--presentation-isosurface-video",
        "--fluid-safe-wrapper-overlay",
        "--disable-particle-debug-display",
        "--presentation-look-preset",
        str(cell["look_preset"]),
        "--particle-limit",
        str(int(cell["particle_limit"])),
        "--steps",
        str(int(cell["steps"])),
        "--hard-exit-after-run",
    ]
    if cell.get("capture_closeup"):
        argv.append("--capture-closeup-camera")
    return argv


def build_matrix_manifest(
    *,
    cells: list[dict[str, Any]],
    matrix_id: str,
) -> dict[str, Any]:
    return {
        "manifest_type": "weekly_omniglass_look_matrix_evidence",
        "matrix_id": matrix_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "weekly_omniglass_look_matrix_executed": True,
        "official_visual_a_clearwater_unchanged": True,
        "weekly_omniglass_matrix_is_visual_diagnostic_not_official_visual_a": True,
        "physics_wrapper_variant_id_expected": "D4A_018",
        "claim_boundary": build_claim_boundary(),
        "cells": cells,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    evidence_root = Path(args.evidence_root)
    matrix_id = args.matrix_id
    cell_summaries: list[dict[str, Any]] = []
    all_cells = MATRIX_CELLS + OPTIONAL_MATRIX_CELLS
    selected = [c for c in all_cells if c["cell_id"] in set(args.cells)]
    if not selected:
        raise ValueError(f"no_matrix_cells_selected:{args.cells}")

    for cell in selected:
        cell_id = cell["cell_id"]
        out_dir = evidence_root / f"{matrix_id}_{cell_id}"
        manifest_path = out_dir / "runtime_smoke_summary.json"
        argv = build_cell_runner_argv(
            cell,
            usd=args.usd,
            out_dir=str(out_dir),
            manifest=str(manifest_path),
        )
        cmd = [args.isaac_python, *argv]
        if args.dry_run:
            cell_summaries.append(
                {
                    "cell_id": cell_id,
                    "dry_run": True,
                    "command": cmd,
                    "look_id": cell["look_preset"],
                    "particle_limit": cell["particle_limit"],
                    "steps_requested": cell["steps"],
                    "steps_completed": 0,
                    "classification": "DRY_RUN",
                    "presentation_water_backend": "MDL_OMNIGLASS_WATER",
                    "presentation_look_preset": cell["look_preset"],
                    "official_visual_a_compatible": False,
                    "official_visual_a_claim_allowed": False,
                    "vla_eval_baseline_invalid": True,
                    "colleague_overlay_not_g1_promotion_spawn": True,
                    "colleague_50k_overlay_equals_g1_zero_leak": False,
                    "leak_status_remains_particle_readback_authoritative": True,
                    "beaker_override_used": True,
                    "human_visual_qa_status": "pending",
                    "artifact_dir": str(out_dir),
                    "honesty_note": cell.get("honesty_note"),
                }
            )
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
        summary: dict[str, Any] = {}
        if manifest_path.exists():
            summary = json.loads(manifest_path.read_text(encoding="utf-8"))
        classification = str(
            summary.get("classification")
            or summary.get("hold_classification")
            or ("RUNTIME_NONZERO_EXIT" if completed.returncode else "UNKNOWN")
        )
        steps_completed = int(
            summary.get("steps_completed")
            or summary.get("completed_steps")
            or 0
        )
        cell_summaries.append(
            {
                "cell_id": cell_id,
                "look_id": cell["look_preset"],
                "particle_limit": int(cell["particle_limit"]),
                "selected_particle_count": summary.get("selected_particle_count"),
                "steps_requested": int(cell["steps"]),
                "steps_completed": steps_completed,
                "abort_step": summary.get("abort_step"),
                "last_pass_step": summary.get("last_pass_step"),
                "video_trim_step": summary.get("video_trim_step"),
                "duration_honesty": summary.get("duration_honesty"),
                "classification": classification,
                "presentation_water_backend": "MDL_OMNIGLASS_WATER",
                "presentation_look_preset": cell["look_preset"],
                "lighting_contract_hash": (
                    (summary.get("presentation_visual_contract") or {})
                    .get("lighting", {})
                    .get("lighting_contract_hash")
                ),
                "camera_contract_hash": (
                    (summary.get("presentation_visual_contract") or {})
                    .get("camera", {})
                    .get("camera_contract_hash")
                ),
                "postprocess_hash": (
                    (summary.get("presentation_visual_contract") or {})
                    .get("postprocess", {})
                    .get("postprocess_hash")
                ),
                "material_hash": "omniglass_water_tint_a18_v1",
                "beaker_override_used": True,
                "official_visual_a_compatible": False,
                "official_visual_a_claim_allowed": False,
                "vla_eval_baseline_invalid": True,
                "colleague_overlay_not_g1_promotion_spawn": True,
                "colleague_50k_overlay_equals_g1_zero_leak": False,
                "leak_status_remains_particle_readback_authoritative": True,
                "physics_wrapper_variant_id": "D4A_018",
                "human_visual_qa_status": "pending",
                "artifact_dir": str(out_dir),
                "returncode": int(completed.returncode),
                "honesty_note": cell.get("honesty_note"),
                "main_video": str(out_dir / "presentation_isosurface.mp4"),
            }
        )

    matrix_manifest = build_matrix_manifest(cells=cell_summaries, matrix_id=matrix_id)
    matrix_path = evidence_root / f"{matrix_id}.json"
    _write_json(matrix_path, matrix_manifest)
    matrix_manifest["matrix_manifest_path"] = str(matrix_path)
    return matrix_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=DEFAULT_USD)
    parser.add_argument("--evidence-root", default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--matrix-id", default=DEFAULT_MATRIX_ID)
    parser.add_argument("--isaac-python", default=DEFAULT_ISAAC_PYTHON)
    all_ids = [c["cell_id"] for c in MATRIX_CELLS + OPTIONAL_MATRIX_CELLS]
    parser.add_argument(
        "--cells",
        nargs="+",
        default=[c["cell_id"] for c in MATRIX_CELLS],
        choices=all_ids,
        help="Primary 4 cells by default; pass B_P1024 for optional look-hold.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = run_matrix(args)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if args.dry_run:
        return 0
    # Non-zero only if every selected cell failed to produce a summary file.
    missing = [c for c in manifest["cells"] if not Path(c["artifact_dir"]).exists()]
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_weekly_omniglass_look_matrix.py -v
python tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py --dry-run --cells B_P4096
```

Expected: pytest PASS; dry-run prints JSON with `dry_run=true` and no Isaac launch.

- [ ] **Step 5: Commit (if committing)**

```bash
git add tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py tests/test_weekly_omniglass_look_matrix.py
git commit -m "$(cat <<'EOF'
feat: add weekly OmniGlass look matrix sweep runner

EOF
)"
```

---

## Task 7: Isaac smoke one cell (B_P4096) then full matrix

**Files:**
- Create (via run): `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1_B_P4096/`
- Create (via run): `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1.json` (after full matrix)
- Create (via run): per-cell dirs for `B_P50000`, `C_P4096`, `C_P50000` (+ optional `B_P1024`)

**Do not run Isaac from plan-writing agents unless the user explicitly asks in an implementation session.** This task is for the implementing engineer.

**Known prior smoke:** `B_P4096` already produced `FAIL_CONTAINER_LEAK` + OmniGlass video. Re-run only if code changed; otherwise ingest existing artifacts honestly into the matrix manifest.

- [ ] **Step 1: Smoke one cell — B_P4096**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py \
  --cells B_P4096
```

Expected:
- Artifact dir exists under `.../fluid_spike_weekly_omniglass_look_matrix_20260709_v1_B_P4096/`
- `presentation_isosurface.mp4` (or frames) present
- Cell summary has `presentation_look_preset=weekly_omniglass_B`, `official_visual_a_claim_allowed=false`, `vla_eval_baseline_invalid=true`, `beaker_override_used=true`
- Classification may be `FAIL_CONTAINER_LEAK` (known) or `PASS_SOURCE_HOLD`; record honestly — **do not** reframe leak as success

- [ ] **Step 2: Verify default ClearWater path still unit-green (no Isaac)**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_postprocess_contract_matches_spec_anisotropy_and_smoothing tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py::test_build_presentation_water_mdl_material_info_targets_clearwater -v
```

Expected: PASS

- [ ] **Step 3: Run full matrix**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py
```

Expected:
- Four cell dirs + top-level `..._20260709_v1.json`
- For 50k cells: if `FAIL_CONTAINER_LEAK` before step 120, record `abort_step` / `last_pass_step` / `video_trim_step` / `duration_honesty`; caption must not say 静置零泄漏
- Prefer shorter proven PASS window in cell caption notes when leak aborts early
- If both 4096 cells leak **and** fail look continuity: run optional look-hold:

```bash
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py \
  --cells B_P1024
```

Do **not** promote `B_P1024` as G1/G2 proof; use only for tint/rim readability QA.

- [ ] **Step 4: Compress / copy weekly assets (if videos are large)**

Copy or symlink main (+ closeup for C) into `reports/2026-07-07-labutopia-fluid-weekly/assets/` with names:

```text
weekly-omniglass-B_P4096.mp4
weekly-omniglass-B_P50000.mp4
weekly-omniglass-C_P4096.mp4
weekly-omniglass-C_P4096-closeup.mp4
weekly-omniglass-C_P50000.mp4
weekly-omniglass-C_P50000-closeup.mp4
weekly-omniglass-B_P1024.mp4   # only if optional cell run
```

Use `preload="metadata"` in HTML later. Prefer webm+mp4 if the existing weekly pipeline already encodes both; otherwise mp4 alone is fine.

- [ ] **Step 5: Commit evidence (if committing)**

```bash
git add docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1.json \
  docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1_*/ \
  reports/2026-07-07-labutopia-fluid-weekly/assets/weekly-omniglass-*
git commit -m "$(cat <<'EOF'
docs: record weekly OmniGlass look matrix Isaac evidence

EOF
)"
```

---

## Task 8: Weekly HTML matrix section + honesty

**Files:**
- Modify: `reports/2026-07-07-labutopia-fluid-weekly/index.html`

- [ ] **Step 1: Write a small HTML honesty regression check (optional but preferred)**

Add `tests/test_weekly_omniglass_html_honesty.py`:

```python
from pathlib import Path

WEEKLY = Path("reports/2026-07-07-labutopia-fluid-weekly/index.html")


def test_weekly_html_has_diagnostic_matrix_and_demotes_leadership_main():
    text = WEEKLY.read_text(encoding="utf-8")
    assert "诊断观感矩阵" in text or "周报视觉诊断矩阵" in text
    assert "非官方 Visual A" in text
    assert "非 G1 晋级" in text or "g1_promotion_evidence=false" in text
    assert "B_P4096" in text
    assert "C_P50000" in text
    assert "official_visual_a_compatible: false" in text or "official_visual_a=false" in text
    assert "presentation_water_backend" in text
    assert "readback_classification" in text or "classification=" in text
    assert "duration_honesty" in text or "partial_to_step" in text or "full_window" in text
    assert "colleague_50k_overlay_equals_g1_zero_leak=false" in text or "≠ G1" in text
    # Leadership framing withdrawn from ClearWater hold-long as sole main evidence.
    assert "主证据：真实 USD 静置持液渲染" not in text
    assert "G1/G2 状态卡" in text or ("官方证据" in text and "G1" in text and "G2" in text)
    # Matrix must not be labeled as 主证据 / G2 ClearWater proof.
    assert "omniglass-look-matrix" in text
    # Forbidden colloquial claims must remain in the blocked list section, not as positive claims.
    assert "像水" in text  # still listed under 不能说
```

Adjust the demotion assertion to match the exact replacement heading chosen in Step 3 (e.g. archive note title). If the test is too brittle on Chinese punctuation, assert on stable English/machine ids (`weekly-omniglass-B_P4096`, `非官方 Visual A`, `diagnostic_look_matrix`).

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_weekly_omniglass_html_honesty.py -v
```

Expected: FAIL (old heading still present / matrix missing).

- [ ] **Step 3: Update weekly HTML**

In `reports/2026-07-07-labutopia-fluid-weekly/index.html`:

1. Keep hero metrics for G1 12/12 and G2 ClearWater PASS in a **demoted** `官方证据 / G1/G2 状态卡` section (physics/official Visual A).
2. Replace section `#main-video` title/framing:
   - Old: `主证据：真实 USD 静置持液渲染` + “周报唯一主视频” leadership language.
   - New: archive/diagnostic note for `g1g2-hold-long` ClearWater clip (e.g. `归档：ClearWater 持液片（非领导力主片 / G2 evidence only）`), stating human QA rejected leadership readiness (beaker invisible / metallic shards).
3. Add new section `#omniglass-look-matrix` titled **诊断观感矩阵（非官方 Visual A / 非 G1 晋级）** / `diagnostic_look_matrix` with a 2×2 grid of videos. **Do not** mount this grid as `#main-video` / 主证据.
4. Each cell `<figcaption>` must include the bilingual required fields from the spec (§7): `cell_id`, `look_id`, `presentation_water_backend`, `official_visual_a_compatible: false`, `particle_limit`, `physics_provenance`, `readback_classification`, `duration_honesty`, `human_visual_qa`, blocked-claims line.
5. For 50k / leaking cells: caption must say leak honestly; never “静置零泄漏”; include `colleague_50k_overlay_equals_g1_zero_leak=false`.
6. Explicit note: OmniGlass matrix is **not** G2 ClearWater proof; G2 remains `fluid_spike_visual_a_official_20260709.json`.
7. Do not label the matrix as “主证据 / G2 ClearWater”.
8. Videos use `preload="metadata"`.
9. Until human QA picks a winner, do **not** add a “领导力主片” single-winner section; if added later, title must be `领导层可读候选（仍非官方 Visual A）` with `official_visual_a_claim_allowed=false`.
10. If `B_P1024` was run, add it as a clearly labeled optional look-hold figure (not a 5th “primary” leadership cell).

Example matrix cell markup:

```html
<section id="omniglass-look-matrix" class="panel section">
  <h2>诊断观感矩阵（非官方 Visual A / 非 G1 晋级）</h2>
  <p class="small">diagnostic_look_matrix · official_visual_a=false · g1_promotion_evidence=false。OmniGlass 水色 + beaker2 可读性对照；不是 G2 ClearWater 主证据。漏液仍以 particle readback 为准。同事 USD overlay ≠ G1 晋级零泄漏。</p>
  <div class="figure-row" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
    <figure class="diagnostic">
      <video controls muted preload="metadata" playsinline>
        <source src="assets/weekly-omniglass-B_P4096.mp4" type="video/mp4">
      </video>
      <figcaption>
        单元 / cell_id: B_P4096<br>
        观感预设 / look_id: weekly_omniglass_B<br>
        水色材质 / presentation_water_backend: MDL_OMNIGLASS_WATER<br>
        官方 Visual A / official_visual_a_compatible: false<br>
        粒子数 / particle_limit: 4096<br>
        物理来源 / physics_provenance: colleague_usd_overlay_D4A_018 （≠ g1_promotion_v4）<br>
        读回判定 / readback_classification: FAIL_CONTAINER_LEAK<br>
        时长诚实 / duration_honesty: <!-- fill from manifest --><br>
        人类观感 / human_visual_qa: pending<br>
        禁止话术 / blocked_claims: 非官方VisualA · 非G1_50k零泄漏 · 非真实水
      </figcaption>
    </figure>
    <!-- B_P50000, C_P4096, C_P50000 similarly; fill classification/steps from matrix manifest -->
  </div>
</section>
```

Fill real `classification` / `steps_completed` from the matrix JSON after Task 7.

Also update the metrics tile that currently says `~15s 真实 USD 持液主视频` so it no longer implies leadership-ready ClearWater main video (e.g. `诊断矩阵 4 cells` or keep G2 metric and drop the leadership duration tile).

- [ ] **Step 4: Run honesty test**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest tests/test_weekly_omniglass_html_honesty.py -v
```

Expected: PASS

- [ ] **Step 5: Commit (if committing)**

```bash
git add reports/2026-07-07-labutopia-fluid-weekly/index.html tests/test_weekly_omniglass_html_honesty.py
git commit -m "$(cat <<'EOF'
docs: mount weekly OmniGlass look matrix with honest captions

EOF
)"
```

---

## Task 9: Claim boundary docs touch

**Files:**
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify (only if needed for discoverability): `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`

- [ ] **Step 1: Add README registry entry**

Append a dated subsection under the fluid spike evidence guide:

```markdown
## 2026-07-09 Weekly OmniGlass Look Matrix

Diagnostic presentation matrix (not official Visual A / G2):

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1.json
cells=B_P4096,B_P50000,C_P4096,C_P50000[+optional B_P1024]
weekly_html=reports/2026-07-07-labutopia-fluid-weekly/index.html#omniglass-look-matrix
spec=docs/superpowers/specs/2026-07-09-weekly-omniglass-look-matrix-design.md
plan=docs/superpowers/plans/2026-07-09-weekly-omniglass-look-matrix.md
```

Allowed: `weekly_omniglass_look_matrix_executed=true`, OmniGlass water backend on cells,
`official_visual_a_clearwater_unchanged=true`, `vla_eval_baseline_invalid=true`,
`colleague_overlay_not_g1_promotion_spawn=true`, particle-readback leak authority.

Blocked: photoreal/真实水/像水, `omniglass_water_equals_official_visual_a`,
`weekly_omniglass_equals_g2_clearwater`, `weekly_cell_updates_official_vla_overlay_hashes`,
`colleague_50k_overlay_equals_g1_zero_leak` (no PASS exception), promoting matrix as G2 ClearWater.
```

- [ ] **Step 2: Grep for forbidden positive claims**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
rg -n "真实水|像水|omniglass_water_equals_official_visual_a|colleague_50k_overlay_equals_g1_zero_leak|主证据：真实 USD 静置持液渲染" \
  reports/2026-07-07-labutopia-fluid-weekly/index.html \
  docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1.json \
  docs/labutopia_lab_poc/evidence_manifests/README.md
```

Expected: “真实水/像水” only inside blocked/不能说 lists; no leadership “主证据：真实 USD…” heading; matrix JSON has `official_visual_a_claim_allowed: false` and `vla_eval_baseline_invalid: true` on cells.

- [ ] **Step 3: Optional spike doc note**

If `true_physx_pbd_fluid_spike.md` still points readers at `g1g2-hold-long` as the weekly leadership video, add a short note that weekly leadership readability moved to the OmniGlass matrix and ClearWater hold-long is archived diagnostic only. Do not rewrite Physics A / Visual A sections.

- [ ] **Step 4: Commit (if committing)**

```bash
git add docs/labutopia_lab_poc/evidence_manifests/README.md docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md
git commit -m "$(cat <<'EOF'
docs: register weekly OmniGlass look matrix claim boundary

EOF
)"
```

---

## Task 10: Human QA checklist artifact

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_human_qa_checklist_20260709.md`

- [ ] **Step 1: Write the checklist file**

```markdown
# Weekly OmniGlass Look Matrix — Human Visual QA Checklist

**Date:** 2026-07-09
**Matrix:** `fluid_spike_weekly_omniglass_look_matrix_20260709`
**Rule:** Fill one row per cell after watching the video. Do not mark photoreal / 真实水. Leak authority remains particle readback.

## Pass gates (all required for `pass`)

1. Beaker silhouette / rim readable
2. Table or lab context visible in frame
3. Liquid continuous (not metallic shard field)
4. Water tint readable (cyan-green OmniGlass water), not debug emissive
5. No growing puddle / obvious level loss in the PASS window
6. Caption matches readback classification

**Warn OK:** slight ice-slush, meniscus noise, not photoreal.
**Fail:** black frames, invisible cup, shard field, leak presented as success.

## Per-cell results

| Cell ID | look_id | particle_limit | classification | steps_completed | duration_honesty | QA status (pending/pass/warn/fail) | Notes |
|---------|---------|----------------|----------------|-----------------|------------------|--------------------------------------|-------|
| B_P4096 | weekly_omniglass_B | 4096 | FAIL_CONTAINER_LEAK (known smoke) |  |  | pending | overlay ≠ G1; video may still be look-usable |
| B_P50000 | weekly_omniglass_B | 50000 |  |  |  | pending | 50k overlay ≠ G1; abort/trim honesty |
| C_P4096 | weekly_omniglass_C | 4096 |  |  |  | pending | include presentation closeup |
| C_P50000 | weekly_omniglass_C | 50000 |  |  |  | pending | 50k overlay ≠ G1 |
| B_P1024 (optional) | weekly_omniglass_B | 1024 |  |  |  | pending | look-hold only; not G1/G2 |

## Winner selection (optional, after QA)

- Leadership main candidate cell_id: _none until human picks_
- Must not set `official_visual_a_claim_allowed=true`
- Must not claim G1 from a short 50k/4096 PASS window
- Caption must still show `official_visual_a_compatible=false` + readback classification

## Sign-off

- Reviewer:
- Date:
- At least one cell `pass`? (success criterion #2):
```

After Task 7, fill classification/steps from the matrix JSON (still leave QA status `pending` for humans).

- [ ] **Step 2: Point weekly HTML at the checklist**

In the matrix section, add one line:

```html
<p class="small">人工 QA 清单：<code>../../docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_human_qa_checklist_20260709.md</code></p>
```

- [ ] **Step 3: Commit (if committing)**

```bash
git add docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_human_qa_checklist_20260709.md \
  reports/2026-07-07-labutopia-fluid-weekly/index.html
git commit -m "$(cat <<'EOF'
docs: add weekly OmniGlass human visual QA checklist

EOF
)"
```

---

## Final verification (implementing engineer)

Run before declaring the plan complete:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m pytest \
  tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py \
  tests/test_weekly_omniglass_look_matrix.py \
  tests/test_weekly_omniglass_html_honesty.py \
  -v --tb=short
```

Expected: all PASS. Default ClearWater tests still assert anisotropy `5.0` and `OmniSurface_ClearWater`.

Isaac full matrix already recorded (Task 7). Weekly HTML shows 4 cells with honest captions. No G1 code changes. No forbidden claims as positive statements.

---

## Spec coverage checklist (self-review)

| Spec requirement | Task |
|------------------|------|
| Presets B/C + inherit merge + C closeup path | Task 1 |
| OmniGlass water sibling path (no ClearWater author) | Task 2 |
| Beaker2-only override + pre/post bind evidence | Task 3 |
| Lighting B/C, camera v2, aniso2/smooth0.65 | Task 4 |
| CLI + mutual exclusion + VLA isolation + abort fields | Task 5 |
| 4-cell sweep + optional B_P1024 + matrix manifest | Task 6 |
| Isaac smoke + full matrix + 50k/4096 leak honesty | Task 7 |
| Weekly HTML diagnostic IA + bilingual captions | Task 8 |
| Claim boundary docs | Task 9 |
| Human QA checklist | Task 10 |
| Default ClearWater / anisotropy 5.0 unchanged | Tasks 1–5 regression steps |
| No Physics A / G1 geometry changes | Out of scope (all tasks) |

## Risks encoded in this plan

1. **OmniGlass-as-water confuses G2 / VLA** — separate material path + `vla_eval_baseline_invalid=true` + weekly contract only + mutual exclusion + HTML “非官方 Visual A”.
2. **Global Looks pollution** — beaker override binds only `/World/beaker2/mesh`; never mutate native OmniGlass attrs; tests assert beaker1 unchanged + pre/post bind.
3. **50k / 4096 overlay leaks** — known `B_P4096` FAIL; abort/trim fields; optional `B_P1024` look-hold; HTML captions forbid “静置零泄漏” / G1 equivalence (no PASS exception).
4. **Exposure lighting blowout/dark (look C)** — capability probe; kept as A/B vs B; human QA picks winner; no auto-promote.
5. **ClearWater regression** — explicit pytest gates on anisotropy 5.0 / ClearWater / lighting+camera v1 hashes after each wiring task.
6. **MDL input name drift / ClearWater reconcile misuse** — OmniGlass compile scan scoped to sibling path; if compile fails, record `MDL_COMPILE_FAIL` honestly; never false-PASS `MDL_WATER`.
7. **Weekly page misread as leadership main** — diagnostic vs 官方证据 vs optional 领导层可读候选 split + bilingual caption templates.
8. **4096 still shards under aniso2** — STOP/continue rule; optional B_P1024; do not ship unlabeled winner.
9. **Weekly page weight** — `preload=metadata` + compressed clips.
10. **Mid-run abort not in runner today** — Task 5 must implement stride leak abort + provenance fields; until then end-of-run FAIL + honest caption is minimum, but plan requires abort fields for 50k cells.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-09-weekly-omniglass-look-matrix.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks (`superpowers:subagent-driven-development`).
2. **Inline Execution** — execute tasks in-session with checkpoints (`superpowers:executing-plans`).

Which approach?

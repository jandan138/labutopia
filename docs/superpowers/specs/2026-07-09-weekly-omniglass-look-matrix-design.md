# Weekly OmniGlass Look Matrix Design

**Date:** 2026-07-09
**Status:** draft — pending blocker fixes encoded below; implement only after this revision
**Parent:** `2026-07-09-dual-track-realistic-water-design.md`
**Goal:** Replace the rejected weekly leadership hold video with a human-readable OmniGlass-tinted water **diagnostic** look matrix, without touching Physics A / G1 or official Visual A ClearWater evidence.

---

## 1. Problem

The shipped weekly main video (`reports/2026-07-07-labutopia-fluid-weekly/assets/g1g2-hold-long.*`) fails human visual QA:

- Beaker nearly invisible (clear OmniGlass + dome fill, wide presentation camera)
- Liquid reads as metallic shards (1024 sparse isosurface + anisotropy scale 5.0 + ClearWater under strong key)
- Desktop/lab context weak despite `native_scene_opened=true`
- Readback was `PASS_SOURCE_HOLD` — physics OK, presentation not leadership-ready

Reference assets at `inputs/usd/scene/liquid/` show a readable recipe: tinted OmniGlass water (`glass_color≈(0.73,0.95,0.94)`), exposure-based Dome+Distant lighting, continuous container walls. Those refs use a **box cup collider** and bind OmniGlass as water — neither may become LabUtopia physics authority or replace official Visual A ClearWater.

### Known Isaac evidence (2026-07-09)

| Cell / path | Result | Honesty note |
|-------------|--------|--------------|
| ClearWater hold @ 1024 (prior weekly) | `PASS_SOURCE_HOLD` | Physics/readback OK; human QA rejected look (shards / invisible cup) |
| `B_P4096` OmniGlass smoke | `FAIL_CONTAINER_LEAK` | Video written; `material_backend=MDL_OMNIGLASS_WATER` — **leak is real on colleague overlay**; do not hide |
| Colleague overlay @ 4096 / 50k | Expect leak risk | Overlay ≠ G1 promotion spawn; captions must say so |

---

## 2. Decisions (locked)

| Decision | Choice |
|----------|--------|
| Architecture | Extend existing runner with look presets + thin 2×2 sweep (+ optional B_P1024 look-hold cell) |
| Weekly liquid material | OmniGlass water tint (not ClearWater) |
| Official Visual A | Unchanged: ClearWater + existing hashes/rubric |
| VLA / Visual A contract emission | Weekly presets emit `weekly_presentation_look_contract` only; do **not** populate official `vla_water_visual_contract` overlay hashes |
| CLI mutual exclusion | `--presentation-look-preset != none` incompatible with `--visual-acceptance-scenario A_static_clear_water` (exit nonzero); force `official_visual_a_claim_allowed=false` |
| Beaker readability | Try **B** (presentation-only beaker2 override + intensity lighting + lowered camera) **and** **C** (B + exposure/CT lighting + closeup capture) |
| Shard mitigation | Try **4096** and **near-50k** particle limits; lower anisotropy (~2.0); slightly raise smoothing; optional **1024** visual-hold cell when 4096 leaks |
| 50k / 4096 PASS language | Even full-window PASS on colleague overlay: never imply G1 / promotion equivalence |
| Weekly delivery | Full matrix on weekly HTML as **diagnostic** section only; separate optional leadership-candidate slot after human QA |
| Physics | Frozen: D4A_018 FluidSafeWrapper; no collider/geometry changes |

---

## 3. Scope

### In scope

1. Presentation look presets: `weekly_omniglass_B`, `weekly_omniglass_C`
2. OmniGlass water material authoring for weekly lane (separate USD path from ClearWater)
3. Beaker2 presentation-only material override (sibling Looks prim; bind/restore contract; no global Looks pollution)
4. Lighting profiles B (intensity contrast) and C (exposure + colorTemperature inspired by refs) with runtime capability probe for C
5. Camera: slightly lower/table-aware main camera for B; C also captures presentation closeup (not native-material closeup slot)
6. Postprocess: anisotropy scale 5→2, smoothing 0.5→0.65 (new hash); parameterized builders with ClearWater defaults
7. Particle matrix: 4096 and 50000 (up to 50k from colleague set via `particle_limit`); optional `B_P1024` visual-hold; short PASS window; honest abort/trim fields
8. Sweep runner or CLI matrix that produces 4 (+ optional) cells + manifests
9. Weekly HTML: mount diagnostic matrix; demote ClearWater “唯一主视频 leadership-ready” framing; bilingual caption templates
10. Claim-boundary fields in manifests; VLA emission isolation

### Out of scope

- G1 / D4A_018 / FluidSafeWrapper geometry or classification contract
- Official Visual A ClearWater evidence re-run (unless accidentally broken — then fix)
- Box-cup visible geometry as product beaker
- Task 11 pour / Lane C FX
- Photoreal / 真实水 / video-equals-zero-leak claims
- Changing default `--presentation-isosurface-video` ClearWater path behavior when weekly look preset is **not** selected
- Equating colleague-USD overlay 50k/4096 to G1 promotion 12/12

---

## 4. Architecture

```text
CLI: --presentation-look-preset {none,weekly_omniglass_B,weekly_omniglass_C}
     --particle-limit {1024,4096,50000}   # matrix validates enum; runner may allow any int
     --presentation-isosurface-video
     --fluid-safe-wrapper-overlay          # always for weekly matrix
        │
        ▼
run_colleague_native_usd_completed_pbd_step_video.py
        │
        ├─ look=none (default) → existing ClearWater Visual A path (unchanged)
        │     emit official vla_water_visual_contract as today
        │
        └─ look=weekly_omniglass_* → apply PresentationLookProfile
              ├─ water: OmniGlass tint @ /World/Looks/LiquidPresentationOmniGlassWater
              │         (do NOT author ClearWater path)
              ├─ beaker2: sibling override @ /World/Looks/LiquidPresentationBeakerGlass
              ├─ lighting: B intensity OR C exposure/CT (+ capability probe)
              ├─ camera: main v2 (+ presentation closeup for C)
              ├─ postprocess: aniso2 / smooth0.65
              ├─ official_visual_a_claim_allowed=false
              ├─ vla_eval_baseline_invalid=true
              └─ emit weekly_presentation_look_contract (NOT official VLA overlay)
        │
        ▼
artifacts per cell + matrix manifest
        │
        ▼
weekly HTML: G1/G2 状态卡 + 诊断观感矩阵 (4 cells) [+ optional 领导层可读候选]
```

**Hard rules:**

1. `presentation_look_preset=none` (default): author ClearWater at `/World/Looks/LiquidPresentationWater`; hashes remain `omnisurface_clearwater_mdl_v1` / `anisotropy_5_1_2_smoothing_0_5_v1` / `liquid_presentation_dome_key_v2` / `liquid_presentation_main_camera_v1`.
2. `presentation_look_preset=weekly_omniglass_*`: do **not** author ClearWater; author OmniGlass water at `/World/Looks/LiquidPresentationOmniGlassWater`; set `official_visual_a_claim_allowed=false`; set `vla_eval_baseline_invalid=true`; emit `weekly_presentation_look_contract` (not official VLA overlay). Never set `material_backend=MDL_WATER` on weekly cells.
3. Combining weekly preset with `A_static_clear_water` is a **hard error** (exit nonzero before stage authoring).
4. Weekly matrix cells always pass `--fluid-safe-wrapper-overlay` (no native-collider-approximation-variant for this matrix).

---

## 5. PresentationLookProfile

Frozen dataclass / dict contract (implementation may live in the same runner file initially; extract only if tests demand it):

```python
PRESENTATION_LOOK_PRESETS = {
    "weekly_omniglass_B": {
        "look_id": "weekly_omniglass_B",
        "water_backend": "MDL_OMNIGLASS_WATER",
        "water_mdl": "OmniGlass.mdl",
        "water_sub_identifier": "OmniGlass",
        "water_material_path": "/World/Looks/LiquidPresentationOmniGlassWater",
        "glass_color": (0.73344165, 0.9498069, 0.94228774),      # A18/C29 ref
        "reflection_color": (0.6368421, 0.9266409, 0.88300306),
        "beaker_override": {
            "enabled": True,
            "target_mesh": "/World/beaker2/mesh",
            "material_path": "/World/Looks/LiquidPresentationBeakerGlass",
            "mdl": "OmniGlass.mdl",
            "sub_identifier": "OmniGlass",
            # Slightly more opaque / cooler rim for readability vs water tint
            "glass_color": (0.85, 0.92, 0.95),
            "reflection_color": (0.90, 0.95, 0.98),
            "cutout_opacity": 0.72,
            "enable_opacity": True,
        },
        "lighting": {
            "mode": "intensity_v3",
            "key_intensity": 1200.0,
            "dome_intensity": 220.0,   # lower fill → glass edges readable
            "key_rotate_xyz": (55.0, 0.0, 35.0),
            "lighting_contract_hash": "weekly_omniglass_intensity_v3",
        },
        "camera": {
            "main_hash": "weekly_omniglass_main_camera_v2",
            "eye_z_above_table": 0.22,   # was ~0.34
            "focus_source_weight": 0.85, # intentional weekly-only (default ClearWater uses 0.72)
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
        # Inherits B water/beaker/postprocess; overrides lighting + camera
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
            "key_rotate_xyz": (55.0, 0.0, 135.0),  # match ref DistantLight yaw
            "lighting_contract_hash": "weekly_omniglass_exposure_ct_v1",
        },
        "camera": {
            "main_hash": "weekly_omniglass_main_camera_v2",
            "eye_z_above_table": 0.22,
            "focus_source_weight": 0.85,
            "capture_closeup": True,
            # Presentation isosurface closeup (NOT native-material CLOSEUP_CAMERA_PATH story)
            "closeup_prim_path": "/World/LiquidPresentationCloseupCamera",
            "closeup_hash": "weekly_omniglass_closeup_camera_v1",
        },
        "official_visual_a_compatible": False,
    },
}
```

### Resolve rules

- Shallow section merge: `C = {**B, **C_overrides}` where nested dicts (`lighting`, `camera`) **replace whole sections** (not deep-merge keys). After resolve, C must retain B’s `water_*`, `beaker_override`, `postprocess`, `material_hash`, and `official_visual_a_compatible=false`.
- Required keys after merge: `water_*`, `beaker_override`, `lighting`, `camera`, `postprocess`, `material_hash`, `official_visual_a_compatible=false`.
- `build_presentation_postprocess_contract(look_profile=None)` must default to Visual A constants when profile is None.
- Unit tests must lock exact hash literals for preset=none: `postprocess_hash=anisotropy_5_1_2_smoothing_0_5_v1`, `lighting_contract_hash=liquid_presentation_dome_key_v2`, `camera_contract_hash=liquid_presentation_main_camera_v1`, `material_path=/World/Looks/LiquidPresentationWater`, `sub_identifier=OmniSurface_ClearWater`, `material_backend=MDL_WATER`.

### Beaker bind contract

1. Create `/World/Looks/LiquidPresentationBeakerGlass` (**new prim only**).
2. Bind exclusively to `/World/beaker2/mesh` via `UsdShade.MaterialBindingAPI`.
3. Never mutate `/World/Looks/OmniGlass_01` (or whatever native glass is bound) attributes in place.
4. Record `beaker2_pre_bind_material`, `beaker2_post_bind_material`, `beaker1_binding_unchanged=true`.
5. Evidence USDA must retain unbound native glass prim contents unchanged.
6. Explicit non-touch list: `beaker1`, other Looks materials, native OmniGlass prim attrs.
7. `cutout_opacity=0.72` + `enable_opacity` is a **readability recipe**, not native glass parity. Human QA FAIL if opacity tanks refraction/context so badly the cup reads as tinted plastic with no rim/context (checklist item 1–2).

### Material backend / compile / reconcile

- Weekly success path: `material_backend=MDL_OMNIGLASS_WATER`, `sub_identifier=OmniGlass`.
- Compile scan / reconcile must scope to `LiquidPresentationOmniGlassWater` (extend scanner; **do not** reuse ClearWater-only `reconcile_presentation_water_material_with_isaac_log` as-is).
- Never set `material_backend=MDL_WATER` or `omnisurface_clearwater_mdl_v1` on weekly cells.
- OmniGlass compile FAIL → record honest `MDL_COMPILE_FAIL` / fallback status; **block** that weekly cell from claiming `MDL_OMNIGLASS_WATER` PASS; do not false-PASS ClearWater.
- `build_vla_water_overlay()` / official VLA builder must **not** see weekly OmniGlass hashes; weekly path sets `vla_water_visual_contract=null` (or omits) and `vla_eval_baseline_invalid=true`.

### Lighting C capability probe

- Before accepting Cell C as a matrix winner candidate: probe whether exposure / colorTemperature attrs applied on this Isaac/USD Lux build.
- If attrs no-op: set `lighting_capability_probe=WARN` (or FAIL if completely dark/blown) and do not burn matrix budget claiming exposure_ct parity with refs.

### Matrix cells

| Cell ID | Look | particle_limit | steps (default) | video | Notes |
|---------|------|----------------|-----------------|-------|-------|
| `B_P4096` | weekly_omniglass_B | 4096 | 120 | main + frames | Known smoke: `FAIL_CONTAINER_LEAK` + video + OmniGlass backend — record honestly |
| `B_P50000` | weekly_omniglass_B | 50000 | 120 max; mid-run abort on leak | main + frames | See abort contract |
| `C_P4096` | weekly_omniglass_C | 4096 | 120 | main + presentation closeup | |
| `C_P50000` | weekly_omniglass_C | 50000 | 120 max; mid-run abort on leak | main + presentation closeup | See abort contract |
| `B_P1024` (optional) | weekly_omniglass_B | 1024 | 120 | main + frames | **Look-QA hold cell** when 4096/50k leak on colleague overlay; prior ClearWater@1024 PASSed — use for tint/rim readability only, never as G1/G2 proof |

`particle_limit=50000` means “up to 50k from colleague set” via `select_particle_subset`; record `selected_particle_count` vs requested.

### 50k / leak abort contract

Runner today classifies end-of-run only. Spec requires implementable mid-run honesty:

- **Abort predicate:** at each stride sample, if hold classifier leak gates would already FAIL (`outside_source_count>0` / spill / retention drop per existing `classify_colleague_trace` gates), abort further steps.
- **Record fields:** `abort_step`, `last_pass_step`, `video_trim_step=last_pass_step`, final `classification` (typically `FAIL_CONTAINER_LEAK`).
- **Partial video policy:** trim (or caption) to `video_trim_step`; keep leak frames only if clearly labeled FAIL — prefer shorter proven PASS window in the published cell clip.
- **No exception:** even full-window PASS on colleague overlay ≠ G1 promotion. Always emit `colleague_overlay_not_g1_promotion_spawn=true`. Forbidden claim `colleague_50k_overlay_equals_g1_zero_leak` has **no PASS exception**.

### 4096 shard / leak STOP rule

- If both primary 4096 cells (`B_P4096`, `C_P4096`) still fail human continuity (shard field) **and** leak classification, do **not** silently ship a “winner.”
- Continue options: (1) record WARN cells + run optional `B_P1024` for look-only QA, (2) STOP matrix promotion to leadership-candidate slot.
- Success criterion #2 still requires at least one cell that passes human QA **with honest caption** — a leaking 4096 cell can still pass *look* QA only if puddle/level gates are scoped to the PASS window and classification is shown as FAIL (checklist item 6). Prefer `B_P1024` when 4096 cannot hold.

Physics provenance for all cells: link `D4A_018` / promotion v4 manifest; note colleague-USD overlay ≠ controlled promotion spawn.

---

## 6. Implementation units

| Unit | Responsibility |
|------|----------------|
| `PresentationLookProfile` helpers in runner | Resolve preset, author OmniGlass water, beaker override+restore evidence, lighting, camera knobs, postprocess overrides, weekly contract emission |
| CLI flags | `--presentation-look-preset`, mutual exclusion, keep ClearWater default when unset |
| Thin sweep script | `tools/labutopia_fluid/run_weekly_omniglass_look_matrix.py` — loops 4 (+ optional B_P1024) cells, writes matrix manifest |
| Tests | preset=none locks ClearWater path + four official hashes; weekly locks OmniGlass path + weekly hashes + `official_visual_a_claim_allowed=false` + `vla_eval_baseline_invalid=true`; beaker bind only beaker2 + beaker1 unchanged; CLI combo rejected; profile C inherits B postprocess/material_hash |
| Weekly HTML | Diagnostic 2×2 (+ optional 1024) with bilingual captions; G1/G2 in demoted 官方证据; optional 领导层可读候选 only after QA |
| Evidence | `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_weekly_omniglass_look_matrix_20260709_v1.json` + per-cell dirs (include `_v1` / run id to avoid same-day collision) |

---

## 7. Claim boundary

### Allowed

- `weekly_omniglass_look_matrix_executed=true`
- `manifest_type=weekly_omniglass_look_matrix_evidence` (distinct from `fluid_spike_visual_a_official_*`)
- Per-cell `presentation_water_backend=MDL_OMNIGLASS_WATER` (only when MDL compile PASS)
- `presentation_look_preset=weekly_omniglass_{B,C}`
- `weekly_presentation_look_contract_hash=...`
- `vla_eval_baseline_invalid=true`
- `official_visual_a_compatible=false`
- `official_visual_a_claim_allowed=false`
- `colleague_overlay_not_g1_promotion_spawn=true` (all cells, not only 50k)
- `leak_status_remains_particle_readback_authoritative=true`
- `official_visual_a_clearwater_unchanged=true`
- `weekly_omniglass_matrix_is_visual_diagnostic_not_official_visual_a=true`
- `abort_step` / `last_pass_step` / `duration_honesty` (50k and any early-abort cell)
- Human QA notes per cell (pass/warn/fail checklist)

### Forbidden

- `mdl_water_equals_photoreal_water` / 真实水 / 像水
- `presentation_video_equals_physics_success`
- `omniglass_water_equals_official_visual_a`
- `weekly_omniglass_equals_g2_clearwater`
- `weekly_cell_updates_official_vla_overlay_hashes`
- `reference_liquid_usd_box_cup_equals_labutopia_beaker`
- `colleague_50k_overlay_equals_g1_zero_leak` — **no exceptions** (even full-window PASS)
- `material_hash_implies_mdl_when_fallback_active`
- Changing `official_visual_a_claim_allowed` based on weekly OmniGlass cells
- Labeling the matrix section as “主证据 / G2 ClearWater”
- Reusing runner `display_name: presentation_water_unified_realistic` on weekly cells

### HTML information architecture

1. Keep G1 / G2 metrics + ClearWater official evidence in a **demoted** “官方证据 / G1/G2 状态卡” section (not hero leadership main).
2. Hero / main visual section for look work = OmniGlass **diagnostic** matrix only; title must not say ClearWater leadership-ready.
3. Withdraw `g1g2-hold-long` as “周报唯一主视频”; if retained, label explicitly `归档：G2 ClearWater evidence (not leadership look)`.
4. **Do not** mount the 4-cell grid as `#main-video` / “主证据” without the diagnostic banner.
5. Optional **领导层可读候选** / `leadership_readability_candidate` only after human QA; must still show `official_visual_a_claim_allowed=false`.
6. Automated scrub: forbid `真实水` / `像水` / `静置零泄漏` on non-PASS cells; forbid `leadership-ready` / “主视频过关” for OmniGlass matrix cells.
7. Asset budget: max 4 matrix mp4 (+ optional B_P1024 + C closeups); `preload=metadata`; prefer compressed clips.

### Required HTML caption templates

**Section banner (matrix, not hero):**

- 中文: `诊断观感矩阵（非官方 Visual A / 非 G1 晋级）`
- English: `diagnostic_look_matrix` · `official_visual_a=false` · `g1_promotion_evidence=false`

**Per-cell `<figcaption>` — every cell must show all of these (CN label → EN key):**

```text
单元 / cell_id: {B_P4096|B_P50000|C_P4096|C_P50000|B_P1024}
观感预设 / look_id: {weekly_omniglass_B|weekly_omniglass_C}
水色材质 / presentation_water_backend: MDL_OMNIGLASS_WATER
官方 Visual A / official_visual_a_compatible: false
粒子数 / particle_limit: {1024|4096|50000}
物理来源 / physics_provenance: colleague_usd_overlay_D4A_018  （≠ g1_promotion_v4）
读回判定 / readback_classification: {PASS_SOURCE_HOLD|FAIL_CONTAINER_LEAK|…}
时长诚实 / duration_honesty: {full_window_N_steps | partial_to_step_K_on_leak}
人类观感 / human_visual_qa: {PASS|WARN|FAIL|pending}
禁止话术 / blocked_claims: 非官方VisualA · 非G1_50k零泄漏 · 非真实水
```

**50k (and any overlay density) cells — mandatory extra line:**

- 中文: `同事USD overlay ≠ G1 受控晋级零泄漏`
- English: `colleague_50k_overlay_equals_g1_zero_leak=false`

**Never in captions:** `静置零泄漏` · bare `Visual A` as positive · bare `G2` as matrix proof · `ClearWater` as this cell’s water · `真实水` · `leadership-ready` (until a separate winner slot is explicitly labeled).

**Leadership winner slot (only after human QA):** separate section titled
`领导层可读候选（仍非官方 Visual A）` / `leadership_readability_candidate` · `official_visual_a_claim_allowed=false`.

### Per-cell manifest required fields

```text
cell_id
look_id
presentation_look_preset
presentation_water_backend          # MDL_OMNIGLASS_WATER only if compile PASS
water_sub_identifier                # OmniGlass
official_visual_a_compatible        # false
official_visual_a_claim_allowed     # false
vla_eval_baseline_invalid           # true
weekly_presentation_look_contract_hash
particle_limit
selected_particle_count
physics_provenance                  # colleague_usd_overlay + D4A_018
g1_promotion_manifest_ref           # link only
colleague_overlay_not_g1_promotion_spawn  # true
colleague_50k_overlay_equals_g1_zero_leak # false
readback_classification / classification
leak_status_remains_particle_readback_authoritative  # true
steps_requested
steps_completed
abort_step / last_pass_step / video_trim_step   # when early abort
duration_honesty                    # full_window | partial_to_step_K
lighting_contract_hash
camera_contract_hash
postprocess_hash
material_hash
beaker_override_used
beaker2_pre_bind_material
beaker2_post_bind_material
beaker1_binding_unchanged
artifact_paths
human_visual_qa_status              # pending|pass|warn|fail
allowed_claims[]
blocked_claims[]
```

Matrix root also needs: `weekly_omniglass_look_matrix_executed=true`, `manifest_type` distinct from `fluid_spike_visual_a_official_*`, `official_visual_a_clearwater_unchanged=true`.

---

## 8. Human visual QA checklist (per cell)

Pass gates:

1. Beaker silhouette / rim readable
2. Table or lab context visible in frame
3. Liquid continuous (not metallic shard field)
4. Water tint readable (cyan-green OmniGlass water), not debug emissive — **checklist-internal only**; HTML captions use machine ids, not “像水”
5. No growing puddle / obvious level loss in PASS window (respect `duration_honesty`)
6. Caption matches readback classification

Warn OK: slight ice-slush, meniscus noise, not photoreal.

Fail: black frames, invisible cup, shard field, leak presented as success, opacity recipe that destroys rim/context.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| OmniGlass-as-water confuses G2 / VLA | Separate material path + `vla_eval_baseline_invalid` + weekly contract only + mutual exclusion |
| Global Looks pollution | Sibling materials; bind only beaker2; pre/post bind evidence; beaker1 unchanged |
| 50k / 4096 overlay leaks | Honest FAIL + abort/trim fields; optional B_P1024 look-hold; never claim G1 |
| Weekly hashes poison frozen VLA | Do not emit official `vla_water_visual_contract` on weekly presets |
| Exposure lighting blows out / no-ops | Capability probe; Cell C WARN; human pick |
| ClearWater regression | Parameterized builders; tests lock four official hash literals |
| 4096 still shards under aniso2 | STOP/continue rule + optional B_P1024 |
| Weekly page misread as leadership main | Diagnostic vs 官方证据 vs optional 领导层可读候选 split + caption templates |
| Same-day manifest collision | `_v1` / run id suffix |

---

## 10. Success criteria

1. Four primary cells recorded with manifests (optional `B_P1024` when needed for look QA).
2. At least one cell passes human QA checklist **and** its caption includes readback classification + `official_visual_a_compatible=false` (winner badge must not imply G2/ClearWater).
3. Weekly HTML shows diagnostic matrix with required bilingual caption fields; not mounted as 主证据.
4. Official Visual A ClearWater path still unit-test green (exact hash literals); no G1 code changes.
5. Claim boundary fields present; HTML/manifest contain no forbidden claims; official VLA hash literals unchanged in preset=none tests; weekly cells set `vla_eval_baseline_invalid=true`.

---

## 11. Non-goals reminder

This sprint improves **weekly leadership readability** via a **diagnostic** OmniGlass matrix. It does **not** redefine Visual A, does **not** fix colleague-USD 50k/4096 overlay physics, and does **not** authorize colloquial “真实水.”

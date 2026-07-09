# Dual-Track Realistic Water Design (A+B, C-Ready)

**Date:** 2026-07-09  
**Status:** reviewed (APPROVE_WITH_FIXES applied)  
**Repo:** LabUtopia  
**Runtime:** Isaac Sim 4.1 headless  

## 1. Problem

The shipped “统一真实水” milestone (`d9d85d2`) completed a **presentation-lane cleanup** (non-emissive light `UsdPreviewSurface` on PhysX Isosurface) with explicit `WARN_REALISM_NOT_YET_PHOTOREAL`. Viewers correctly judge that the liquid does not look like real water.

Root causes (ranked):

1. **Success-metric mismatch** — DoD was “remove debug red/blue,” not perceptual water.
2. **Material ceiling** — `USD_PREVIEW_FALLBACK`; preferred `MDL_WATER` / `OmniSurface_ClearWater` never bound to liquid (`mdl_compile_status` was effectively `MDL_NOT_ATTEMPTED`, not a failed bind).
3. **Leak geometry** — colleague 50k `RAW_AS_IS` static hold retains ~18%; isosurface of sparse leaks reads as speckled fog.
4. **Missing reconstruction/lighting** — no anisotropy/smoothing; DistantLight only; no `maxRefractionBounces≥12`.

Product need: future VLA / EBench cameras must see water that reads as real-world liquid for static hold (**A**) and pour (**B**), while keeping splash/wetting/foam (**C**) architecturally feasible.

## 2. Goals and Non-Goals

### Goals

| ID | Goal |
|----|------|
| G1 | **Physics A:** fluid-safe wrapper collider achieves static zero-leak on full colleague `level1_pour` scene across the full D2 ladder including **3×50000**. |
| G2 | **Visual A:** on a **Physics-A-passing** trajectory, attempted `OmniSurface_ClearWater` MDL + anisotropy/smoothing + DomeLight + refraction passes rubric A. |
| G3 | **Physics+Visual B:** after G1, slow kinematic pour with continuous stream look under the same visual contract. |
| G4 | **Claims honesty:** scrub “真实水/像水/photoreal” PM language until G1+G2; RGB never equals physics success. |
| G5 | **VLA freeze:** versioned visual overlay contract so train/eval cameras share the same water look; hashes invalid under fallback. |
| G6 | **C-ready:** emit disabled `product_water_fx` stubs; do not implement splash/foam/wetting this round. |

### Non-Goals

- Implementing Diffuse Particles / Flow / wetting / meniscus.
- LabUtopia 5.1 native visual parity claims.
- EBench score / policy claims / leaderboard.
- Further `UsdPreviewSurface` color tuning as the primary realism path.
- Another blind native mesh approximation sweep on `/World/beaker2/mesh`.
- Using `max_velocity` or reduced `initial_radial_velocity` to fake zero-leak.
- Hiding or recoloring leaked particles by state.
- SDF/cooked wrapper or slow-settle init as D4 **promotion** paths (diagnostic-only if used).

## 3. Architecture

Three contract lanes share one PBD trajectory; only the physics lane is authoritative for pass/fail.

```text
Physics lane          → particle_readback → PASS_SOURCE_HOLD / FAIL_*
Presentation surface  → Anisotropy + Smoothing + Isosurface + OmniSurface_ClearWater
Product FX (C stub)   → Diffuse / Flow / wetting  (enabled=false; never feeds classifier)
```

**API ownership:**

- Presentation-owned: `PhysxParticleSmoothingAPI`, `PhysxParticleAnisotropyAPI`, `PhysxParticleIsosurfaceAPI`, liquid render MDL, Dome/key lights, presentation camera.
- Product-FX-owned (via `author_product_water_fx` only): `PhysxDiffuseParticlesAPI`, Flow, wetting maps.
- Classifier inputs remain `particle_readback` only; presentation and FX never write leak counts.

```text
┌─────────────────────────────────────────────────────────────┐
│ VISUAL: /World/beaker2/mesh (OmniGlass / OmniSurface_Glass) │
│         physics:collisionEnabled = false                    │
├─────────────────────────────────────────────────────────────┤
│ PHYSICS: /World/beaker2/FluidSafeWrapper (invisible)        │
│          Bottom + Wall_00..N static/kinematic box panels    │
│          authored in beaker2-local frame                    │
├─────────────────────────────────────────────────────────────┤
│ FLUID:   /World/CompletedPBD/ParticleSystem + ParticleSet   │
│          PBD physics material ≠ render MDL ≠ FX volume      │
└─────────────────────────────────────────────────────────────┘
```

### Stage gates

| Stage | Must pass | Unlocks |
|-------|-----------|---------|
| P0 Claim rewrite | Weekly/docs scrub 真实水/像水/photoreal complete claims | Honest PM language |
| P1 Physics A | Wrapper D2 ladder GO including 3×50k | Non-leaking trajectory for Visual A |
| P1 Visual A | ClearWater MDL + rubric A on Physics-A traj (provenance linked) | Visual A rubric PASS |
| P2 Physics+Visual B | Slow pour + pour readback gates + rubric B | Visual B PASS\|WARN |
| P3 C stubs only | `product_water_fx.enabled=false` in every presentation summary | Future FX without rewrite |

**Hard rule:** Official Visual A evidence must record `physics_trajectory_manifest` / seed / particle_count / wrapper_id of a Physics-A-passing run. Leaking 50k `RAW_AS_IS` videos remain diagnostic only.

Unlock labels use machine language only: `Visual_A_rubric_PASS`, `Visual_B_rubric_PASS|WARN` — not colloquial “像水”.

## 4. Physics Track — Fluid-Safe Wrapper (D4)

### 4.1 Evidence baseline (do not re-litigate)

- S2 C0–C5: all fail; **C2** closest (~83% retention @ 256p).
- S2F1–F2: `C2A_009` + low init velocity once `PASS_SOURCE_HOLD`; S2F5 promotion **0/6**.
- S2F3 SDF: all fail. S2F4 native mesh: fail; `render_mesh_plus_proxy_collision` closest (12 spill).
- S2F6 native approximations on full scene: **0/10** zero-leak; best `RAW_AS_IS` ~0.80 retention @ 512p (distinct from 50k ~0.18).

### 4.2 Wrapper design

**Prim layout (full colleague scene):**

```text
/World/beaker2/mesh
  physics:collisionEnabled = false
  (visual materials unchanged)

/World/beaker2/FluidSafeWrapper
  visibility = invisible
  labutopia:fluidSafeWrapper = true
  Bottom   # box in beaker2-local frame
  Wall_00..N
```

**Parenting / frame (blocking rule):**

- Author panels as children of `/World/beaker2` in **beaker2-local** coordinates, baked once from `/World/beaker2/mesh` world AABB (world→local convert). Do **not** parent world-space poses under `beaker2` (double transform).
- Sibling `/World/FluidSafeWrapper_beaker2` allowed only with **explicit per-step kinematic sync** to `beaker2`; otherwise Track B → `STOP_VISUAL_PHYSICS_MISMATCH`.
- Document collider motion contract: panels inherit `beaker2` xform (static collision under moving parent) **or** `RigidBodyAPI` with `kinematicEnabled=true` when the cup is driven. CollisionAPI-only without a motion contract is insufficient for pour.

**Geometry starting point (from best prior art, then sweep):**

| Param | Start | Sweep range |
|-------|-------|-------------|
| `panel_count` | 48 | 48, 64, 72 |
| `wall_thickness` | 0.018 | 0.014–0.022 |
| `bottom_overlap` | 0.003 | 0.003–0.008 |
| `panel_arc_overlap_factor` | 1.08 | 1.08–1.20 |
| `interior_inset` | wall inner face clears spawn AABB by ≥ `particle_contact_offset` | derived from beaker2 mesh AABB |
| `particle_contact_offset` | scene-consistent | joint with collider offsets |
| `collider_contact_offset` / `rest_offset` | from C2A_009 | limited sweep |

**Rules:**

- GPU-compatible **box** panels only (Isaac demo `create_particle_box_collider` pattern).
- No single convex hull / convexDecomposition on open cup.
- No SDF as primary D4 promotion path.
- **Pinned init for promotion:** `initial_radial_velocity=0.08`, `particle_max_velocity=5.0`. Passes that require `initial_radial_velocity < 0.08` or `particle_max_velocity < 5.0` → `FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE` / matrix `STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE`.
- Manifest fields required: `wrapper_parent_path`, `wrapper_frame=local_to_beaker2|world_synced`, `native_mesh_collision_enabled=false`, `initial_radial_velocity`, `particle_max_velocity`, full panel params.

### 4.3 Acceptance gates (per trial)

Compose historical classifiers; do **not** collapse all failures to `FAIL_CONTAINER_LEAK`.

1. Call `classify_collider_hold(...)` (`s2_no_outside_source_v2`) for leak / readback / GPU / CPU / explosion / perf / sealed.
2. Additionally require followup contract:
   - `non_physical_parameter_dependence == false` (see pinned init above)
   - `blocking_runtime_warning_detected == false`
   - `particle_motion_observed` / `readback_position_changed == true`

Core leak gates (from hold classifier):

```text
outside_source_count == 0
spill_count == 0
below_table_count == 0
target_count == 0
source_retention_fraction >= 0.95
particle_count_final_fraction >= 0.95
tail_leak_rate_fraction_per_second < 0.02
nan_count == 0
cpu_collision_fallback_detected == false
gpu_collider_unsupported == false
```

**Per-trial labels** remain `HOLD_CLASSIFICATIONS` ∪ `{FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE}` (including `FAIL_READBACK_UNAVAILABLE`, `FAIL_GPU_COLLIDER_UNSUPPORTED`, `FAIL_CPU_COLLISION_FALLBACK`, `FAIL_PARTICLE_EXPLOSION`, `FAIL_PERF_BUDGET_EXCEEDED`, `FAIL_CONTAINER_SEALED`, `FAIL_CONTAINER_LEAK`).

### 4.4 Validation matrix

| Dimension | Values |
|-----------|--------|
| Scene | Full `lab_001_level1_pour_tabletop_with_liquid.usd` |
| Counts | 512 → 1024 → 4096 → 50000 (no skip) |
| Seeds | 0, 1, 2 at **every** rung including 50000 |
| Steps | 240 @ physics_dt=1/60 (4 s) minimum; promoted candidate also 600-step (10 s) tail check using same `tail_leak_rate` contract |
| Init | `initial_radial_velocity=0.08`, `particle_max_velocity=5.0` |

**Promotion bar (S2F5-strict):**

- All 3 seeds at rung N must be `PASS_SOURCE_HOLD` before any claim on rung N+1.
- Minimum before any 50k **attempt claim**: `3 × {512,1024,4096} = 9` trials GO.
- **Physics A / G1 GO:** additionally `3 × 50000` `PASS_SOURCE_HOLD` (**3** more; **12** total across four rungs).
- Any missing pair, extra pair, or partial near-pass → matrix `STOP_WITH_EVIDENCE`; `best_for_s3=[]`.
- No Visual A official trajectory and no 50k zero-leak claim until G1 GO.

### 4.5 STOP classifications (matrix-level)

```text
STOP_WITH_EVIDENCE                     # incomplete grid / partial near-pass
STOP_WRAPPER_NOT_FLUID_SAFE            # full grid run; leaks remain
STOP_STATIC_HOLD_LEAK                  # alias when D2 ladder fails on leak
STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE # pass only under forbidden crutches
STOP_PERF_OR_OOM
STOP_VISUAL_PHYSICS_MISMATCH           # wrapper frame/sync broken vs beaker visual
STOP_READBACK_UNAVAILABLE
```

### 4.6 Implementation order (physics)

1. Author `_add_fluid_safe_wrapper()` (invisible, local-frame AABB-aligned).
2. `D4_WRAPPER_SWEEP` phase in followup sweep runner.
3. Minimal-slice smoke → full-scene 512p → promotion matrix → 50k completed-PBD with wrapper.
4. Freeze manifest; `s3_kinematic_pour_released=false` until Track B.

### 4.7 Files to extend

- `tools/labutopia_fluid/run_beaker_collider_smoke.py`
- `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`
- `tools/labutopia_fluid/run_colleague_liquid_usd_leak_smoke.py`
- `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- Matching `tests/test_fluid_*.py`
- Manifests under `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_proxy_wrapper_design_*`
- Assets under `assets/chemistry_lab/lab_001_fluid_spike/colliders_d4/`

## 5. Visual Track — MDL Water Presentation

### 5.1 Target pipeline

```text
Disable particle debug display
→ PhysxParticleSmoothingAPI (strength=0.5)
→ PhysxParticleAnisotropyAPI (scale=5, min=1, max=2)
→ PhysxParticleIsosurfaceAPI (keep cup-demo GS 4/4)
→ Attempt OmniSurface_ClearWater via isaacsim41_core_mdl_local_mirror
→ DomeLight + DistantLight key
→ rtx/translucency/maxRefractionBounces ≥ 12 (record actual value)
→ Capture LiquidPresentationMainCamera (+ same overlay on Camera1/2)
```

Isosurface remains the **bulk liquid** mesh path. C may later add FX layers beside it; A/B must not hardcode “isosurface is the only forever render path.”

### 5.2 Material backend strategy

| Priority | Backend | When |
|----------|---------|------|
| 1 | `MDL_WATER` = `OmniSurfacePresets.mdl::OmniSurface_ClearWater` | **Required** for official Visual A evidence |
| 2 | `OmniSurface_DeepWater` | Optional recorded B variant only; not default A evidence |
| 3 | `USD_PREVIEW_FALLBACK` | Emergency only after attempted bind |

**Status enum (honest):**

```text
mdl_bind_attempted: true|false
material_backend: MDL_WATER | USD_PREVIEW_FALLBACK
mdl_compile_status: PASS | MDL_COMPILE_FAIL | FALLBACK_USED | MDL_NOT_ATTEMPTED
# FALLBACK_USED only after attempted bind + documented reason
# MDL_NOT_ATTEMPTED blocks any MDL pass / ClearWater hash claim
sub_identifier: OmniSurface_ClearWater   # required default for Visual A
```

Today’s hardcoded Preview with `pending_mdl_water_pass` must be recorded as `MDL_NOT_ATTEMPTED` until a real bind is attempted.

Scan **presentation shader** compile separately from native beaker glass.

### 5.3 Lighting / RTX / camera

| Contract | Hash / path | Change |
|----------|-------------|--------|
| Presentation camera | `liquid_presentation_main_camera_v1` | No framing change for this pass |
| Lighting | `liquid_presentation_dome_key_v2` | Add DomeLight; keep DistantLight key |
| RTX | `liquid_presentation_rtx_v1` | `max_refraction_bounces=12` at app init; record actual |
| VLA scoring | `/World/Camera1`, `/World/Camera2` | Same water overlay; resolution per task yaml |
| Presentation capture | 960×540 @ 12 fps | Evidence / PM (`review_only`) |

### 5.4 Visual acceptance rubrics

#### Rubric A — Static clear water (Physics-A-passing trajectory only)

Provenance required in manifest: `physics_trajectory_id`, seed, particle_count, wrapper_variant_id, physics classification=`PASS_SOURCE_HOLD`.

| ID | Criterion | Gate |
|----|-----------|------|
| A1 | `mdl_bind_attempted=true`, `material_backend=MDL_WATER`, `mdl_compile_status=PASS`, `sub_identifier=OmniSurface_ClearWater` | Required for MDL pass |
| A2 | No emissive / self-lit water | Required |
| A3 | Fixed ROI on held volume: mean HSV saturation ≤ `T_sat` (record threshold) **or** human checklist on 3 frozen frames with written FAIL reasons (no “looks watery”) | Required |
| A4a | Config: `maxRefractionBounces≥12` AND lighting/postprocess hashes match contract | Required |
| A4b | Percept checklist: table/beaker back edge visible through volume on frame F* (binary) | Required |
| A5 | Continuous isosurface; debug particles off | Required |
| A6 | Single unified **bulk** liquid material (FX layers out of scope for A) | Required |
| A7 | Same seed/steps/wrapper; only presentation flags differ → physics classification identical | Required |
| A8 | Presentation-water MDL log clean (presentation shader path only) | Required |

Verdict: `PASS` / `WARN` (fallback only; cannot claim MDL) / `FAIL`.

#### Rubric B — Pour stream (after Physics A + Visual A)

| ID | Criterion |
|----|-----------|
| B1 | Anisotropy on; stream continuity improved vs speckled baseline |
| B2 | Thin stream still visible when particles leave source |
| B3 | No red/blue debug styling |
| B4 | Unified **bulk** material for cup/spill (FX layers allowed later beside bulk) |
| B5 | Presentation camera hash frozen; VLA overlay hashes match (Camera1/2 framing may differ) |
| B6 | Dome+key lighting present |
| B7 | Perf: 50k×240 within timeout; ≥95% frames captured |
| B8 | Honest claims; readback remains gate |
| B9 | Pour physics gates defined and recorded (separate from Visual B) |

Thin pour may remain `WARN` on B1 even with MDL — isosurface geometry limit, not material failure.

### 5.5 Claim language

**Allowed after MDL pass (machine claims only):**

```text
presentation_water_material_backend=MDL_WATER
presentation_water_mdl_compile_status=PASS
presentation_water_sub_identifier=OmniSurface_ClearWater
physx_particle_anisotropy_and_smoothing_enabled_for_presentation=true
leak_status_remains_particle_readback_authoritative=true
Visual_A_rubric_PASS=true
```

**Blocked (keep / extend):**

```text
mdl_water_equals_photoreal_water
mdl_water_equals_labutopia51_native_visual_parity
presentation_video_equals_physics_success
isosurface_reconstruction_equals_zero_leak
unified_realistic_water_visualization_equals_photoreal_water
product_fx_equals_physics_success
material_hash_implies_mdl_when_fallback_active
colloquial_looks_like_real_water_pm_claim
ebench_score_or_policy_claim_allowed
level1_pour_true_fluid_runtime_passed
```

**P0 rewrite (concrete):**

- Until G1+G2: forbid `真实水` / `像水` / `photoreal` / `统一真实水` in weekly titles and body.
- Files: `reports/2026-07-07-labutopia-fluid-weekly/index.html`, `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`, `docs/labutopia_lab_poc/evidence_manifests/README.md`, manifest titles containing `unified_realistic_water`.
- Replacement: `统一诊断水面（MDL 目标未过）` / `presentation water (MDL_NOT_ATTEMPTED|FALLBACK)`.
- After G1+G2: allow only machine claims above — not colloquial “像水”.

### 5.6 Files to modify (visual)

- `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`
- Weekly HTML + spike doc + evidence README
- New manifests `fluid_spike_mdl_water_visual_*`

## 6. VLA Water Visual Contract

Freeze train=eval water look without freezing physics pass/fail into RGB.

```yaml
vla_water_visual_contract:
  schema_version: 1
  physics_authority: particle_readback
  scoring_cameras:
    - prim: /World/Camera1
      obs_key: camera_1_rgb
    - prim: /World/Camera2
      obs_key: camera_2_rgb
  presentation_camera:
    hash: liquid_presentation_main_camera_v1
    prim: /World/LiquidPresentationMainCamera
    review_only: true
  water_overlay:
    isosurface_hash: isaacsim41_fluid_isosurface_cup_demo_style_v1
    postprocess_hash: anisotropy_5_1_2_smoothing_0_5_v1
    material_hash: omnisurface_clearwater_mdl_v1  # valid iff backend=MDL_WATER and compile=PASS
    fallback_material_hash: usd_preview_near_clear_v1
    lighting_hash: liquid_presentation_dome_key_v2
    rtx_hash: liquid_presentation_rtx_v1
    product_fx_hash: product_water_fx_disabled_v1
    active_material_hash_must_match_backend: true
  blocked_claims:
    - presentation_video_equals_physics_success
    - isosurface_reconstruction_equals_zero_leak
    - material_hash_implies_mdl_when_fallback_active
```

**Rules:**

- Changing any overlay hash (including `product_fx_hash`) requires explicit eval re-baseline and `schema_version` bump.
- Presentation camera is never a scoring `obs_key`.
- When fallback is active, advertise `fallback_material_hash`, not ClearWater `material_hash`.

## 7. Product FX Lane C (Reserve Only)

Always emit in `presentation_visual_contract`:

```json
"product_water_fx": {
  "enabled": false,
  "schema_version": 1,
  "affects_particle_dynamics": false,
  "affects_leak_classification": false,
  "affects_vla_overlay": false,
  "apply_to_particle_system_prim": "/World/CompletedPBD/ParticleSystem",
  "apply_to_particle_set_prim": "/World/CompletedPBD/ParticleSet",
  "diffuse_particles": {
    "enabled": false,
    "api": "PhysxDiffuseParticlesAPI",
    "roles": ["splash", "foam", "spray", "bubbles"],
    "params": {}
  },
  "flow_composite": {
    "enabled": false,
    "extension": "omni.flowusd",
    "optional_gate": "cli:--product-water-fx-flow"
  },
  "wetting": {
    "enabled": false,
    "mode": "reserved",
    "native_api_available": null,
    "probe_at_runtime": true
  },
  "reserved_keys_ok": true
}
```

**Runner hooks (no-op):** `build_product_water_fx_contract()`, `author_product_water_fx()` no-op, CLI `--product-water-fx` default off (orthogonal to `--presentation-isosurface-video`).

**A/B must not hardcode:**

- single boolean owning entire visual stack
- foam params inside PBD material
- state-split **bulk** liquid materials (wetting maps on containers are a future FX/material lane)
- forever-off Flow without optional gate
- “one material on particle system” as the only forever bind site for all future FX

## 8. Parallel Workstreams and Dependencies

```text
P0 claim rewrite ─────────────────────────────► (anytime, first PR ok)
P1a wrapper sweep ──► promotion ──► 3×50k GO ──┐
P1b MDL+aniso+light smoke (low-N / demo cup) ──┤
                                               ▼
                                 P1 Visual A on Physics-A traj
                                               ▼
                                 P2 slow pour (physics gates + Visual B)
```

- **P1b** may start in parallel for MDL compile / lighting smoke.
- **Official Visual A** waits for Physics A G1 GO and must link provenance.
- **P2** waits for Physics A GO; pour readback gates must be defined before claiming B complete.

## 9. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Wrapper still leaks at 1024+ | Tighter panels/overlap; AABB inset; STOP with evidence — no velocity crutches |
| MDL compile fail headless | Local mirror + presentation-specific log scan; fallback allowed but blocks MDL pass / ClearWater hash |
| 50k + anisotropy + MDL perf | Smoke at 512; budget vertices; `STOP_PERF_OR_OOM` |
| Thin pour still speckled | Rubric B may WARN; anisotropy helps; not a reason to skip ClearWater |
| Claim creep | Tests lock blocked claims; P0 file list scrub |
| Visual/physics mismatch | Local-frame wrapper; motion contract; manifest both layers |
| C rewrite pressure | Bulk-only A6/B4; FX stub roles; `product_fx_hash` |

## 10. Success Criteria (Program)

| Milestone | Definition of done |
|-----------|-------------------|
| **A complete** | Physics A matrix GO (12 trials: 4 rungs × 3 seeds) **and** Visual A rubric PASS on that trajectory with ClearWater MDL; P0 claims updated |
| **B complete** | Slow pour after A; pour physics gates recorded; Visual B PASS or documented WARN on thin-stream only |
| **C-ready** | Stubs present with system+set paths and roles; no FX implementation required |

## 11. Open Decisions (resolved by this design)

| Question | Decision |
|----------|----------|
| Physics vs visual first? | Parallel engineering; **joint acceptance for A** |
| ClearWater vs DeepWater? | ClearWater **required** for official Visual A; DeepWater optional recorded B variant |
| Wrapper parent? | Child of `/World/beaker2` in **local** frame; sibling only with kinematic sync |
| Init velocity crutch? | Forbidden; pin `0.08` / `max_velocity=5.0` |
| Photoreal / 像水 claim? | Never this round; machine claims only |
| Promotion count math? | 9 before 50k attempt; **12** for G1 GO (4×3) |

## 12. Review changelog (2026-07-09)

Applied blocking fixes from physics / visual / architecture reviews:

- Fixed promotion arithmetic (9 before 50k attempt; **12** for G1 including 3×50k).
- Restored full FAIL_* taxonomy; composed hold + followup classifiers.
- Local-frame parenting + motion contract; anti-crutch init pins.
- `MDL_NOT_ATTEMPTED` honesty; ClearWater mandatory for Visual A.
- Objective A3/A4 split; VLA hash validity + fallback hash + `product_fx_hash`.
- P0 scrub of 真实水/像水; machine unlock labels.
- C stub: system+set paths, splash/foam roles, wetting reserved, bulk-only A6/B4.
- Visual A provenance link to Physics A trajectory.

## 13. References

- Spike: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- D4 plan section: `docs/superpowers/plans/2026-07-08-colleague-liquid-usd-leak-evidence.md`
- Surface plan Task 8: `docs/superpowers/plans/2026-07-08-liquid-surface-reconstruction-videos.md`
- Unified water manifest: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_unified_realistic_water_visualization_20260709.json`
- Isaac demos: `FluidIsosurfaceCupDemo.py`, `FluidIsosurfaceGlassBoxDemo.py`, `ParticlePostProcessingDemo.py`
- MDL: `/isaac-sim/kit/mdl/core/Base/OmniSurfacePresets.mdl` (`OmniSurface_ClearWater`)

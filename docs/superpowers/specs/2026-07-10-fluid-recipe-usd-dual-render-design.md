# Fluid Recipe USD + Dual Render (A2 + B2)

**Date:** 2026-07-10
**Status:** Approved direction (user locked A2 + B2)
**Parent:** weekly OmniGlass look matrix; G1 D4A_018; dual-track water design

## Decisions (locked)

| ID | Choice |
|----|--------|
| **A2** | Save a **derived** recipe USD in-repo (do not overwrite colleague source USD) |
| **B2** | **Leadership look first** — prioritize readable water video; physics short-window honesty in captions |
| Physics authority | Particle readback only; RGB never proves PASS |
| Wrapper | Freeze D4A_018 FluidSafeWrapper |
| Spawn | G1-style controlled layout (`d4_promotion_spawn_layout`) baked into recipe |
| Dual render | `isosurface` (InternData-like) **and** `particle_omniglass` (liquid-ref-like) on **same** recipe trajectory |

## Goal

Ship a leadership-candidate hold video that:
1. Uses colleague lab geometry (table, beakers, lights context)
2. Uses **controlled spawn** + D4A_018 (not raw colleague 50k points)
3. Uses density chosen for **look** within a known/likely PASS window (start **4096**, not 50k)
4. Tries **both** render modes; **default leadership candidate = `particle_omniglass`** (avoid isosurface shard failure mode)
5. Captions honestly: recipe scene ≠ raw overlay; short window; not official Visual A ClearWater unless separately claimed

## Non-goals

- Overwriting `lab_001_level1_pour_tabletop_with_liquid.usd`
- Claiming recipe 4096/50k = G1 promotion matrix equivalence without linking manifests
- Replacing official G2 ClearWater evidence
- Task 11 pour

## Architecture

```text
Source (immutable):
  outputs/usd_asset_packages/lab_001_localized_20260707/
    lab_001_level1_pour_tabletop_with_liquid.usd

Export tool:
  tools/labutopia_fluid/run_export_fluid_recipe_usd.py
    open source → MDL closure optional
    → apply FluidSafeWrapper D4A_018
    → deactivate original fluid
    → author CompletedPBD particles from d4_promotion_spawn_layout(N)
    → author presentation look (OmniGlass water OR defer to runtime)
    → Export recipe USD + recipe_manifest.json

Recipe asset (A2):
  outputs/usd_asset_packages/lab_001_fluid_recipe_v1/
    lab_001_level1_pour_tabletop_fluid_recipe_v1.usd
    recipe_manifest.json

Runtime video:
  run_colleague_native_usd_completed_pbd_step_video.py
    --usd <recipe.usd>
    --fluid-safe-wrapper-overlay   # idempotent / skip if already present
    --presentation-render-mode {isosurface,particle_omniglass}
    --presentation-look-preset weekly_omniglass_B
    --particle-limit 0            # use recipe baked count when recipe mode
    OR regenerate spawn to match recipe_manifest
```

## Recipe contents (minimum)

- Full lab stage from source (references OK if package-local)
- `/World/beaker2/FluidSafeWrapper` (invisible) + native mesh collision off
- Original `/World/ParticleSystem` / ParticleSet deactivated or hidden
- `/World/CompletedPBD/ParticleSystem` + `ParticleSet` with **controlled** positions for `particle_count` (default **4096** for v1 leadership)
- Recipe metadata prim or sidecar JSON:
  - `recipe_id=lab_001_fluid_recipe_v1`
  - `wrapper_variant_id=D4A_018`
  - `spawn_layout=d4_promotion_spawn_layout(4096)`
  - `source_usd=...with_liquid.usd`
  - `official_visual_a_compatible=false`
  - `raw_colleague_points_used=false`

## Density policy (B2)

| Rung | Role |
|------|------|
| 4096 | **v1 leadership default** — G1 PASS rung; denser than 1024 for look |
| 1024 | Fallback if 4096 recipe hold fails on full scene |
| 8192 / 16384 | Optional look push (may leak — honest FAIL) |
| 50000 | Stress only; not leadership default |

## Dual render

| Mode | Behavior | Leadership default? |
|------|----------|---------------------|
| `particle_omniglass` | No isosurface; debug particle viz OFF; bind OmniGlass tint to Points/ParticleSet; point width from recipe | **Yes (B2)** |
| `isosurface` | Current presentation isosurface + material bind | Comparison cell |

Same recipe USD, same steps/window, only render mode differs.

## Claim boundary

Allowed:
- `fluid_recipe_usd_exported=true`
- `controlled_spawn_not_raw_colleague_points=true`
- `leadership_look_candidate_recorded=true`
- `readback_classification=...` (honest)
- `presentation_render_mode=particle_omniglass|isosurface`

Forbidden:
- `recipe_equals_raw_colleague_50k_zero_leak`
- `leadership_video_equals_g1_promotion`
- `omniglass_particle_equals_official_visual_a`
- 真实水 / photoreal / video=physics success

## Success (B2)

1. Recipe USD exists under `outputs/usd_asset_packages/lab_001_fluid_recipe_v1/`
2. At least one `particle_omniglass` video with human-readable beaker + less shard than prior isosurface 1024 ClearWater reject
3. Caption states recipe + density + classification + not Visual A
4. Dual-render comparison artifact (even if isosurface still shards)
5. Weekly HTML: leadership candidate slot + diagnostic dual-render note

## Packaging note

- Working export also writes under gitignored `outputs/usd_asset_packages/lab_001_fluid_recipe_v1/`.
- **Tracked mirror** for provenance: `assets/chemistry_lab/lab_001_fluid_recipe_v1/` (copy after export).
- Source colleague USD remains immutable under `outputs/.../lab_001_localized_20260707/`.

## Honest runtime finding (2026-07-10 Isaac)

- **Leadership look (PASS):** `particle_omniglass` + D4A_018 + **PASS-window raw subset N=1024** → `PASS_SOURCE_HOLD`, `presentation_isosurface_enabled=false`. Liquid still sparse/metallic WARN; beaker hold readable.
- **Controlled-spawn recipe traj on full colleague scene:** G1 `d4_promotion_spawn_layout` @1024/4096 → `FAIL_CONTAINER_LEAK` (step-0 already partial spill). **≠** isolated G1 promotion PASS. Do not claim recipe controlled-spawn full-scene zero-leak.
- **Isosurface twin @4096 controlled:** also FAIL; diagnostic only.
- Source USD hash unchanged; recipe USD is a derived copy.

## Implementation order

1. Export tool + unit tests (spawn layout reuse)
2. `--presentation-render-mode` in native video runner
3. Export recipe v1 @ 4096
4. Isaac: particle_omniglass leadership smoke → isosurface twin
5. Weekly HTML update

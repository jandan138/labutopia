# LabUtopia Native DryingBox EBench Acceptance Stages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LabUtopia native complex `DryingBox_01` usable in the EBench/GenManip `level1_open_door` lane without overstating official Lift2 baseline readiness.

**Architecture:** Keep the existing P1 surrogate/render-layout lane as a debugging baseline, and run a separate native DryingBox acceptance-stage lane. The native lane must pass USD asset audit, native-only Isaac smoke, EBench wrapper composition, additive physics/articulation closure, eval readback, evidence packaging, and Lift2 contract check in order. Every acceptance stage writes machine-readable evidence before the next product-facing claim is upgraded.

**Tech Stack:** Python 3.10, USD Python APIs (`pxr.Usd`, `pxr.UsdPhysics`, `pxr.UsdGeom`), Isaac Sim 4.1 runtime, GenManip/EBench task configs, `pytest`, `gmp submit/eval/status`, static HTML/docs evidence.

---

## Repository Roots

```text
LABUTOPIA_ROOT=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia
GENMANIP_ROOT=/cpfs/shared/simulation/zhuzihou/dev/GenManip
GENMANIP_POC_BRANCH=labutopia-ebench-poc
ASSET_OVERLAY_ROOT=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets
ISAAC_CONDA_ENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
```

Run implementation work in the GenManip `labutopia-ebench-poc` branch. Keep LabUtopia report and planning docs in this repository.

## Multi-Agent Review Summary

| View | Decision |
| --- | --- |
| Product / PM | The seven steps should be written as acceptance stages with evidence, not as a vague to-do list. `Franka smoke` and `Lift2/R5a official baseline readiness` must remain separate claims. |
| USD / Isaac Sim | P1 render/layout closure does not prove native `DryingBox_01` articulated acceptance. The door must pass `native-only Isaac smoke`, additive `USD` physics override, and joint/drive/collision readback. |
| EBench baseline | The final acceptance stage must verify `EvalClient` observation/action/reward/logging contracts. Copying Franka YAML and replacing robot/camera names is not enough for official Lift2 baseline readiness. |
| Material packaging | `/World/Looks` is a valid scene-level USD convention, but EBench does not require that path specifically. Native DryingBox packaging must prove USD `material:binding` resolution, MDL source/subIdentifier resolution, texture dependency resolution, and an explicit fallback boundary. |

## 2026-06-28 Norm Review Addendum

The material and stage rules below incorporate a three-angle review before Stage 2 execution:

| Review angle | Norm added to this plan |
| --- | --- |
| USD / Isaac material composition | Material closure must cover direct mesh, inherited Xform, collection, and `GeomSubset` bindings; `wrapper_local_looks_rebind` must copy full `UsdShade.Material` subtrees, shader connections, MDL source/subIdentifier, recursive helper MDL imports, and case-sensitive texture dependencies. |
| EBench / Lift2 readiness | `attempted` is not `passed`. Any `FAIL` or `BLOCKED` row in reset, step, reachability, camera framing, metric, schema, action dialect, reward/success, or logging blocks Lift2 readiness wording. Stage 2/3/4/5 now have explicit stop conditions and evidence fields. |
| Product / intern explanation | PM-facing HTML must explain why LabUtopia full-scene loading can work while EBench wrapper packaging can fail, why `/World/Looks` is normal but unsafe as an implicit wrapper dependency, and why default blue or `displayColor` fallback proves readability only, not native material closure. |

## Claim Boundary

Allowed after Acceptance Stage 1:

```text
Native DryingBox_01 is a real LabUtopia asset with auditable hierarchy, door joint, handle candidate, and articulation root.
```

Allowed after Acceptance Stage 5:

```text
Native DryingBox_01 can be loaded through the GenManip/EBench eval path and produces readback evidence for render, joint, handle, and metric state.
```

Allowed only after Acceptance Stage 7:

```text
The LabUtopia lift2_candidate lane has passed a local official-baseline-style contract check for observation, action, camera, reward/success, and logging shape.
```

Acceptance Stage 7 has two different outcomes:

- `attempted`: `gmp` or the schema probe ran and produced concrete evidence, but at least one row is `FAIL` or `BLOCKED`;
- `passed`: every required `level1_pick`, `level1_place`, and `level1_open_door` row is `PASS` for reset, step, reachability, camera framing, metric, observation schema, action schema, reward/success, and logging.

Only `passed` allows Lift2 readiness wording. A recorded blocker is useful engineering evidence, but it is not a Lift2 pass.

Not allowed from this plan alone:

```text
official leaderboard reproduction
benchmark-wide model quality
leaderboard comparability
real-world hardware readiness
official EBench score release
native material closure if the proof is only displayColor fallback or a visible frame
```

## File Map

| File | Responsibility |
| --- | --- |
| `standalone_tools/labutopia_poc/audit_native_dryingbox.py` | Read-only USD audit of original LabUtopia `DryingBox_01`. |
| `standalone_tools/labutopia_poc/run_native_dryingbox_smoke.py` | Native-only Isaac smoke without EBench wrapper or robot. |
| `standalone_tools/labutopia_poc/build_asset_overlay.py` | Builds surrogate baseline and native wrapper strategy. |
| `standalone_tools/labutopia_poc/validate_task_package.py` | Static checks for render, wrapper, native articulation, and Lift2 contract readiness. |
| `standalone_tools/labutopia_poc/capture_eval_render_diagnostics.py` | Eval-path reset/readback diagnostics, render validation, and native evidence linkage. |
| `configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json` | Records native strategy metadata, source hashes, wrapper contract, material policy, and part paths. |
| `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml` | Franka native open-door task: object config, articulation part, metric source, render validation. |
| `configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/*.yml` | Lift2 candidate tasks; updated only after Franka native acceptance-stage evidence is valid. |
| `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_<timestamp>.json` | Machine-readable evidence bundle for each acceptance stage. |
| `reports/2026-06-15-labutopia-weekly/native-dryingbox-task1.html` | PM/intern-readable status and teaching page. |

## Material Packaging Policy

`/World/Looks` is a normal USD/Isaac scene-level material library. It is elegant when the full source scene is composed and the material prims live in the same stage as the meshes that bind to them. It is not safe as an implicit dependency for a narrow object wrapper: referencing only `/World/DryingBox_01` can leave mesh bindings pointing to `/World/Looks/...` material prims that are outside the wrapped subtree.

The native DryingBox lane therefore uses this policy:

- EBench readiness means USD-resolvable bindings plus packaged MDL/texture dependencies, not the presence of a specific `Looks` path.
- For full-source native smoke, preserving `/World/Looks` is acceptable because the goal is fidelity to the original LabUtopia scene.
- The audit and wrapper must cover every authored `material:binding` relationship that contributes to task-visible surfaces: direct mesh bindings, inherited Xform bindings, collection bindings, and `GeomSubset` bindings. Mesh-only checks are insufficient.
- For packaged EBench wrapper composition, prefer `wrapper_local_looks_rebind`: copy every task-used `UsdShade.Material` into an owned wrapper-local scope, then reauthor `material:binding` to those runtime-local material paths.
- The wrapper-local material path is `/World/labutopia_level1_poc/obj_DryingBox_01/Looks/<materialName>` unless the generated wrapper root is renamed; if renamed, the path must remain under the DryingBox wrapper root and be recorded in the manifest.
- `wrapper_local_looks_rebind` must copy the complete material closure, not only the material prim: material subtree, shader prims, `outputs:mdl:*` connections, shader inputs, internal connection targets, asset attributes, and authored binding strength/purpose when present. After rebind, no task-visible surface may retain a stale `/World/Looks/...` target.
- `preserve_owned_world_looks` is allowed only if the overlay explicitly owns the required `/World/Looks` prims, avoids name collisions, and proves all runtime bindings resolve there.
- Preserve `info:mdl:sourceAsset:subIdentifier` exactly during rebasing. `info:mdl:sourceAsset` may be rebased to a package-relative asset only when the resolved MDL hash matches the source evidence. Do not derive the subIdentifier from the MDL filename.
- The material closure report must cover binding target validity, `ComputeBoundMaterial` result, binding strength/purpose, MDL implementation source, MDL source asset, MDL subIdentifier, resolved MDL path, recursive helper MDL imports, case-sensitive texture references, hashes, remote/local status, and worker `MDL_SYSTEM_PATH`.
- `MDL_SYSTEM_PATH` is for MDL module resolution. Texture paths need separate resolved path and hash evidence; do not treat an MDL path as proof that textures resolve.
- Remote-only MDL is not `resolved_native_material` unless it is mirrored locally, hashed, and resolvable in the worker environment. Otherwise it must be explicitly waived as degraded/non-closure.
- `displayColor` is degraded fallback only. It must be recorded per mesh/subset plus as an aggregate status. `resolved_native_material` requires every task-visible surface to resolve native MDL/texture. Mixed surfaces must be reported as `mixed_native_and_fallback`; displayColor-only readability is `degraded_fallback`. Fallback authoring may use `primvars:displayColor` or explicit preview fallback, but it must not remove native bindings.

## Acceptance Stage Summary

| Acceptance Stage | Product meaning | Evidence required before moving on |
| --- | --- | --- |
| 1. Asset Audit | We know what the real DryingBox contains. | `audit.json`, source USD hash, prim/joint/handle list, material closure audit, risk flags. |
| 2. Isaac Smoke | The native asset can survive physics stepping by itself in the full source scene. | `smoke.json`, Isaac log, 120-step root/handle/joint trace, finite checks, PhysX warning classification, full-source material-runtime risk notes. |
| 3. Native Wrapper | EBench can see the real box without breaking hierarchy. | overlay `scene.usda`, manifest, no top-level handle payload, explicit `material_scope_policy`, material/reference report. |
| 4. Physics Override | Static additive override closure is defined and validated; runtime stability is rechecked in Stage 5. | `physics_override.json`, override layer path, before/after warnings, mass/inertia/body target checks, material validator checks, DOF map. |
| 5. Eval Readback | GenManip/EBench can reset, render, step, and score native open-door evidence through the wrapper. | diagnostics JSON, reset obs schema, step response, metric raw output, material readback, frame hashes, stdout/stderr/result paths. |
| 6. Evidence Package | PM, interns, and reviewers can reproduce the claim boundary. | evidence manifest with git SHAs, env vars, commands, run ids, material closure report, paths, screenshots. |
| 7. Lift2 Contract Check | The lane is checked against official baseline-style data contracts; attempted is not the same as passed. | `gmp` logs, observation/action schema probe, camera-key matrix, action-dialect matrix, all rows `PASS` before readiness wording. |

Use `Acceptance Stage` for this seven-stage native DryingBox acceptance lane. Reserve `Task` for concrete engineering work items that may be added under a stage later.

---

### Acceptance Stage 1: Native Asset Audit

**Files:**
- Modify: `standalone_tools/labutopia_poc/audit_native_dryingbox.py`
- Test: `tests/labutopia_poc/test_native_dryingbox_audit.py`
- Output: `saved/diagnostics/native_dryingbox_audit_<utc_timestamp>/audit.json`

- [x] **Step 1: Run audit contract tests**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_native_dryingbox_audit.py -q
```

Expected: PASS. If it fails, fix the audit schema before collecting new evidence.

- [x] **Step 2: Re-run the native audit**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/audit_native_dryingbox.py \
  --labutopia-root /cpfs/shared/simulation/zhuzihou/dev/LabUtopia \
  --source-prim-path /World/DryingBox_01 \
  --output-root saved/diagnostics/native_dryingbox_audit_$(date -u +%Y%m%d_%H%M%S)
```

Expected: exit `0` and write `audit.json`.

- [x] **Step 3: Check audit evidence**

`audit.json` must record:

- `stage_sha256`;
- `defaultPrim`, `upAxis`, `metersPerUnit`, `xformOpOrder`, and root scale;
- per task-visible mesh material data: source `material:binding` target, composed binding target, `ComputeBoundMaterial` result, binding scope status, material prim validity, MDL source asset, MDL subIdentifier, resolved MDL path, helper MDL imports, texture dependencies, remote/local status, hashes, and displayColor fallback status;
- `reference`/`payload` dependency status;
- `PhysicsArticulationRootAPI`;
- rigid bodies, collisions, mass, inertia, `centerOfMass`, and `principalAxes`;
- `physics:body0/body1` for every joint;
- door `RevoluteJoint`, button `PrismaticJoint`, and handle candidates;
- known risk flags, including invalid body target, non-identity root scale, missing mass/inertia, multiple DOFs, out-of-scope `/World/Looks` dependency, missing MDL, missing texture, remote-only MDL, remote-only texture, and black or low-contrast fallback color.

- [x] **Step 4: Record PM wording**

Update the PM note only to say: native `DryingBox_01` is worth continuing, but Acceptance Stage 1 alone does not prove EBench/Lift2 evaluability.

Completion evidence, 2026-06-28:

- GenManip branch: `labutopia-stage1-material-audit`
- GenManip commit: `9568262 feat: audit DryingBox material closure`
- Audit artifact: `saved/diagnostics/native_dryingbox_audit_20260628_102604/audit.json`
- Verification: `python -m pytest tests/labutopia_poc/test_native_dryingbox_audit.py -q` -> `3 passed`
- Verification: `python -m pytest tests/labutopia_poc -q` -> `93 passed, 1 skipped`
- Material audit summary: 32 meshes, 29 bound meshes, 29 out-of-source-subtree material bindings, 3 MDL dependencies, 17 helper MDL dependencies, 1 texture dependency, and machine-readable fallback/material risk flags.
- PM note: `reports/2026-06-15-labutopia-weekly/native-dryingbox-task1.html` now says Stage 1 proves the native asset is worth continuing, but does not prove EBench wrapper, Isaac runtime, or Lift2 baseline readiness.

### Acceptance Stage 2: Native-Only Isaac Smoke

**Files:**
- Modify: `standalone_tools/labutopia_poc/run_native_dryingbox_smoke.py`
- Test: `tests/labutopia_poc/test_native_dryingbox_smoke_contract.py`
- Output: `saved/diagnostics/native_dryingbox_smoke_<utc_timestamp>/smoke.json`

- [ ] **Step 1: Run smoke contract tests**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_native_dryingbox_smoke_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run native-only smoke**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
conda run -p /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310 \
  python standalone_tools/labutopia_poc/run_native_dryingbox_smoke.py \
  --labutopia-root /cpfs/shared/simulation/zhuzihou/dev/LabUtopia \
  --source-prim-path /World/DryingBox_01 \
  --step-count 120 \
  --output-root saved/diagnostics/native_dryingbox_smoke_$(date -u +%Y%m%d_%H%M%S)
```

Expected: exit `0`, `runtime_physics_stable=true`, finite root pose, finite handle pose, finite joint positions, and a captured PhysX warning list.

`smoke.json` must include:

- `step_count=120` and a per-step trace for root pose, handle pose, door joint angle, button joint position, and any other active DOF;
- `finite_trace=true` only if all recorded numeric pose/joint values are finite for all steps;
- `max_root_translation_drift_m`, `max_root_rotation_drift_deg`, `max_handle_translation_drift_m`, `door_joint_angle_min_deg`, `door_joint_angle_max_deg`, `button_joint_position_min_m`, and `button_joint_position_max_m`;
- `non_door_dof_drift_within_tolerance=true` only when non-door DOFs remain inside the configured tolerance, default `1e-4` meters or radians unless the script records a task-specific value;
- `physx_warning_allowlist`, `physx_warning_denylist`, and `unclassified_physx_warnings`;
- full-source material-runtime notes: `/World/Looks` present or absent, unresolved task material count, remote material dependency count, and material compiler warnings filtered to DryingBox materials when Isaac exposes them.

Acceptance Stage 2 proves full-source native physics smoke only. It does not prove EBench wrapper packaging, material rebinding, or Lift2 readiness.

- [ ] **Step 3: Enforce stop condition**

Stop before Acceptance Stage 3 if any of these are true:

- `runtime_physics_stable=false`;
- `finite_trace=false`, or any NaN/Inf appears in root, handle, or joint traces;
- root or handle drift exceeds the explicit tolerance recorded in `smoke.json`;
- door angle leaves the physically allowed range from the source `RevoluteJoint` plus the configured tolerance;
- non-door DOF drift exceeds the configured tolerance without a written explanation;
- `unclassified_physx_warnings` is non-empty;
- full-source material-runtime notes show unresolved task-visible materials that would prevent a readable smoke frame.

Preserve the artifact and add the blocker to the evidence manifest.

### Acceptance Stage 3: Native Wrapper Composition

**Files:**
- Modify: `standalone_tools/labutopia_poc/build_asset_overlay.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`
- Test: `tests/labutopia_poc/test_build_asset_overlay.py`

- [ ] **Step 1: Add wrapper assertions**

`tests/labutopia_poc/test_build_asset_overlay.py` must assert:

- native wrapper payloads/references the whole `/World/DryingBox_01`;
- `scene.usda` does not contain a top-level `obj_obj_DryingBox_01_handle` payload;
- nested handle remains under the drying-box wrapper;
- `drying_box_runtime_asset.strategy` is `native_complex_with_additive_physics_override`;
- `source_payload_used=true`;
- `surrogate_kept_for_debug_baseline=true`.

- [ ] **Step 2: Generate native wrapper**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/build_asset_overlay.py --drying-box-strategy native_complex
```

Expected: generated overlay keeps one top-level `obj_DryingBox_01` wrapper and no independent top-level handle payload.

- [ ] **Step 3: Verify composition contract**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_build_asset_overlay.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected: tests pass. If validator fails because Acceptance Stage 4 native physics checks are not implemented yet, record the exact failure and do not call wrapper work complete.

- [ ] **Step 4: Check material and camera prerequisites**

The wrapper manifest must record:

- `material_scope_policy`, either `wrapper_local_looks_rebind` or `preserve_owned_world_looks`;
- source and runtime `material:binding` targets for every task-visible mesh;
- source and runtime binding records for inherited Xform, collection, and `GeomSubset` bindings that affect task-visible surfaces;
- runtime rebind map if any source target leaves the wrapped subtree, especially `/World/Looks/...`;
- resolved/unresolved binding targets, `ComputeBoundMaterial` results, and stale source binding checks;
- copied material paths, shader paths, `outputs:mdl:*` connections, shader inputs, and internal connection targets;
- MDL source assets, MDL subIdentifiers, recursive helper MDL imports, case-sensitive texture paths, hashes, and remote/local status;
- the exact worker `MDL_SYSTEM_PATH` required for LabUtopia materials;
- fallback `displayColor` policy for task-visible meshes/subsets, labeled as `material_status=degraded_fallback` or `material_status=mixed_native_and_fallback` when used;
- payload dependency report;
- wrapper bbox, source scale, axis/up-axis, and workspace translation;
- camera/light prim names expected by task YAML.

- [ ] **Step 5: Enforce wrapper stop condition**

Stop before Acceptance Stage 4 if any of these are true:

- native `reference` or `payload` dependencies are unresolved in the composed wrapper stage;
- the nested handle is missing under the DryingBox wrapper;
- any independent top-level handle payload exists;
- `wrapper_local_looks_rebind` leaves stale task-visible `/World/Looks/...` bindings;
- `preserve_owned_world_looks` is selected but the overlay does not explicitly own every required `/World/Looks` material;
- material subtree copying drops shader connections, `subIdentifier`, helper MDL imports, or texture dependencies;
- camera/light metadata required by task YAML is missing;
- composed-stage wrapper evidence cannot be opened and re-read by the validator.

### Acceptance Stage 4: Additive Physics Override And Articulation Closure

**Files:**
- Modify: `standalone_tools/labutopia_poc/build_asset_overlay.py`
- Modify: `standalone_tools/labutopia_poc/validate_task_package.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`
- Test: `tests/labutopia_poc/test_validate_task_package.py`
- Output: `saved/diagnostics/native_dryingbox_physics_override_<utc_timestamp>/physics_override.json`

- [ ] **Step 1: Add validator checks**

`validate_task_package.py` must fail if:

- native `reference` or `payload` dependencies are unresolved;
- required post-rebind runtime `material:binding` targets are unresolved, or `ComputeBoundMaterial` fails for any task-visible mesh/subset;
- a runtime rebind map is missing when source bindings leave the wrapped subtree. The map is required evidence, but it does not by itself satisfy material closure;
- required MDL source assets, subIdentifiers, recursive helper MDL imports, or texture dependencies are unresolved, unhashed, remote-only, or absent from the worker `MDL_SYSTEM_PATH` without an explicit waiver;
- wrapper-local objects keep stale out-of-scope `/World/Looks/...` bindings after `wrapper_local_looks_rebind`;
- fallback `displayColor` is absent, black, low contrast, or used without recording `material_status=degraded_fallback` or `material_status=mixed_native_and_fallback`;
- remote-only MDL is labeled `resolved_native_material` without local mirror, hash, worker resolution evidence, or a waiver that explicitly keeps material closure open;
- `PhysicsScene` is missing or duplicated;
- `PhysicsArticulationRootAPI` is lost after wrapping;
- any joint `physics:body0/body1` target lacks `RigidBodyAPI`;
- active rigid bodies have invalid mass, inertia, `centerOfMass`, or `principalAxes`;
- collision shapes are invalid after root scale;
- door `RevoluteJoint` cannot be distinguished from button `PrismaticJoint`;
- camera/light names in validation metadata are missing.

- [ ] **Step 2: Implement additive USD override**

Use only additive override opinions in the generated overlay. Do not edit the original LabUtopia USD. The override may fix or isolate invalid `FixedJoint_01` body targets, add finite mass/inertia where required, stabilize fixed-base behavior, and record `drive target`, `stiffness`, `damping`, and `maxForce` units.

Write `physics_override.json` with:

- override layer path and generated wrapper stage path;
- source USD path and source USD hash;
- before/after `physics:body0/body1` targets for every joint;
- active rigid body list with mass, inertia, `centerOfMass`, and `principalAxes`;
- collision API changes and any scale-compensation assumptions;
- DOF map that names the door `RevoluteJoint`, button `PrismaticJoint`, ignored DOFs, and metric DOF;
- drive parameters with units: target, stiffness, damping, maxForce, and whether they are authored or inherited;
- material validator summary, including unresolved, remote-only, fallback, and waiver counts;
- before/after PhysX warning diff if the validator or smoke harness can collect it.

Acceptance Stage 4 is a static additive-override closure stage. Runtime stability after the wrapper and override is confirmed in Acceptance Stage 5, not assumed here.

- [ ] **Step 3: Bind metric to the door DOF**

`level1_open_door.yml` must bind scoring to the actual door `RevoluteJoint` readback. It must not read the first DOF blindly, and it must not use the button `PrismaticJoint` as the open-door metric source.

- [ ] **Step 4: Verify static closure**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_validate_task_package.py tests/labutopia_poc/test_build_asset_overlay.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected: PASS and `LabUtopia task package validation OK`.

### Acceptance Stage 5: Eval Readback And Render Validation

**Files:**
- Modify: `standalone_tools/labutopia_poc/capture_eval_render_diagnostics.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`
- Create: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_eval_<utc_timestamp>.json`
- Test: `tests/labutopia_poc/test_render_diagnostics_contract.py`

- [ ] **Step 1: Run diagnostics contract tests**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_render_diagnostics_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run eval-path open-door readback**

Use the latest Acceptance Stage 1 `audit.json` and Acceptance Stage 2 `smoke.json` paths explicitly:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
RUN_TS=$(date -u +%Y%m%d_%H%M%S)
AUDIT_JSON=$(ls -t saved/diagnostics/native_dryingbox_audit_*/audit.json | head -n 1)
SMOKE_JSON=$(ls -t saved/diagnostics/native_dryingbox_smoke_*/smoke.json | head -n 1)
test -f "$AUDIT_JSON"
test -f "$SMOKE_JSON"
conda run -p /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310 \
  python standalone_tools/labutopia_poc/capture_eval_render_diagnostics.py \
  --config ebench/labutopia_lab_poc/franka_poc \
  --task level1_open_door \
  --run-id labutopia_native_open_door_eval_${RUN_TS} \
  --seed 000 \
  --output-root saved/diagnostics/labutopia_native_open_door_eval_${RUN_TS} \
  --native-asset-audit-json "$AUDIT_JSON" \
  --native-smoke-json "$SMOKE_JSON"
```

Expected: writes `diagnostics.json` plus reset frame(s) and records the exact audit/smoke artifact hashes.

- [ ] **Step 3: Verify readback fields**

`diagnostics.json` must show:

- `readback_visible` or a concrete render blocker;
- `native_eval_readback_ready=true`;
- `native_material_closure_status`, one of `resolved_native_material`, `mixed_native_and_fallback`, `degraded_fallback`, or `blocked`;
- `lift2_contract_ready=false` unless Acceptance Stage 7 has passed separately;
- `runtime_physics_stable=true`;
- `object_config.obj_DryingBox_01` registered as `existed_object`;
- `articulation_info.part.handle=/handle`;
- `obj_DryingBox_01_handle` registered from the nested handle path;
- pre/post door joint angle and joint name;
- proof that reward/success and metric raw output read the door `RevoluteJoint`, not the button `PrismaticJoint` and not the first arbitrary DOF;
- raw reward/success fields from GenManip/EBench metric output;
- handle world pose;
- drive target and collision warnings;
- render validation using required object visibility, not just non-black pixels;
- result directory, frame paths, frame hashes, stdout log path, stderr log path, run id, worker id, episode id, and seed;
- material readback after reset at runtime wrapper paths.

Runtime material readback must include, for every task-visible mesh/subset:

- authored binding relationship path and authored target;
- runtime binding target and `ComputeBoundMaterial` result;
- binding purpose and binding strength when authored or inferable;
- copied Material path and Shader path;
- shader `info:implementationSource`;
- shader `info:mdl:sourceAsset`, `info:mdl:sourceAsset:subIdentifier`, resolved MDL path, and MDL hash;
- recursive helper MDL imports with resolved path, hash, and remote/local status;
- texture references with exact case, resolved path, hash, and remote/local status;
- material compiler warnings filtered to DryingBox materials;
- `displayColor`/preview fallback status without deleting native material bindings.

Material readback has two separate outcomes:

- `material_status=resolved_native_material`: required for claiming native material closure. Runtime binding targets resolve, `ComputeBoundMaterial` succeeds, all required MDL/helper-MDL/texture dependencies resolve locally or via an explicit approved mirror, all task-visible surfaces resolve native material, and material compiler warnings are absent or explicitly waived.
- `material_status=mixed_native_and_fallback`: some task-visible surfaces resolve native material and others rely on fallback. It may support task readability, but native material closure remains open.
- `material_status=degraded_fallback`: acceptable only for task-readability evidence. It may pass the eval readback stage if physics, hierarchy, and render readability are otherwise valid, but PM wording must say native material closure is still open.
- `material_status=blocked`: runtime material readback cannot be collected or required task-visible materials are missing/unresolved.

- [ ] **Step 4: Retake camera if needed**

Reject frames that are black, flat gray, missing the drying box, missing the door face, missing the handle, or dominated by wall/ceiling geometry. A passing PM-facing frame must show the box body, door edge, and handle clearly enough to explain the task. If the frame uses `displayColor` fallback rather than resolved native MDL materials, the diagnostics and PM note must say so explicitly.

Stop before Acceptance Stage 6 if `native_eval_readback_ready` is not true, if metric evidence does not read the door `RevoluteJoint`, if result/log paths are missing, or if material readback cannot distinguish `resolved_native_material` from fallback.

### Acceptance Stage 6: Evidence Package And PM Claim Boundary

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_acceptance_<utc_timestamp>.json`
- Modify: `docs/records/2026-06-22-labutopia-ebench-weekly-report.md`
- Modify: `docs/records/evidence/2026-06-22-labutopia-ebench-weekly-report/index.html`
- Modify: `reports/2026-06-15-labutopia-weekly/native-dryingbox-task1.html`

- [ ] **Step 1: Build one evidence manifest**

The manifest must include:

- GenManip git SHA and LabUtopia git SHA;
- conda environment path;
- `ASSET_OVERLAY_ROOT`;
- every command used in Acceptance Stages 1-5;
- run id, worker id, seed, task name, and result paths;
- `audit.json`, `smoke.json`, `diagnostics.json`, frame hashes, and log paths;
- material closure report, including `material_scope_policy`, worker `MDL_SYSTEM_PATH`, MDL compiler warnings, unresolved dependency list, waiver list, and fallback status;
- visual review verdict;
- current claim boundary.

- [ ] **Step 2: Update PM-facing wording**

Use this wording if Acceptance Stages 1-5 pass:

```text
原生 DryingBox_01 已经通过 EBench/GenManip eval path 的 native open-door readback：资产不是 surrogate cube，门、把手、joint 和画面都有证据。但这仍然只是 Franka/native acceptance stage，不等于 official Lift2 baseline 已通过。
```

Append this sentence when `material_status=degraded_fallback`:

```text
当前画面可读性依赖 displayColor fallback，native MDL/texture material closure 仍是单独未闭环项，不能宣称原生材质已经完全接入。
```

Use this wording if any Acceptance Stage 1-5 check fails:

```text
原生 DryingBox_01 的接入正在推进，但当前 blocker 仍在 native asset / physics / wrapper / readback 中的一个具体验收阶段；不能宣称 official baseline 可评。
```

- [ ] **Step 3: Keep evidence and product page aligned**

The HTML page must link to the exact evidence manifest and explain old image issues in plain language: camera view mismatch, unresolved native `material:binding`, top-level handle payload risk, and the difference between surrogate and native complex asset.

### Acceptance Stage 7: Lift2 Official-Baseline Contract Check

**Files:**
- Modify: `standalone_tools/labutopia_poc/validate_task_package.py`
- Create: `standalone_tools/labutopia_poc/lift2_eval_contract_probe.py`
- Create: `docs/labutopia_lab_poc/lift2_readiness.md`
- Test: `tests/labutopia_poc/test_validate_task_package.py`

- [ ] **Step 1: Run static checks**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc -q
python standalone_tools/labutopia_poc/validate_task_package.py
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json >/tmp/franka_poc.json
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json >/tmp/lift2_candidate.json
git diff --check
```

Expected: all commands pass.

- [ ] **Step 2: Start eval server with explicit assets**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
ASSETS_DIR=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets \
python ray_eval_server.py --host 0.0.0.0 --port 8087 --no_save_process
```

Expected: server starts with the LabUtopia asset root and no missing Lift2 robot/curobo asset errors.

- [ ] **Step 3: Run Lift2 candidate smoke**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
gmp submit ebench/labutopia_lab_poc/lift2_candidate --run_id labutopia_lift2_schema_smoke
GENMANIP_RESULT_DIR=/tmp/labutopia_lift2_schema_client_results \
gmp eval -a r5a -g lift2 --worker_ids 0 --run_id labutopia_lift2_schema_smoke --frame_save_interval 10
gmp status --run_id labutopia_lift2_schema_smoke
```

Expected: each task either reaches reset/step/metric with saved results or records a concrete blocker such as camera framing, reachability, base collision, missing object, missing asset, action schema mismatch, or blank camera.

This step by itself records a Lift2 candidate attempt. It is not a pass unless every required task reaches reset, step, metric, camera framing, reward/success, and logging without `FAIL` or `BLOCKED`.

- [ ] **Step 4: Run `lift2_eval_contract_probe`**

The probe must reset one task, dump observation schema, then send an action-dialect matrix:

- zero action;
- OpenPI-style relative `base_motion`;
- X-VLA-style absolute `base_motion`;
- InternVLA-A1 single-step relative `base_motion` if supported by the local client;
- InternVLA-A1 chunk absolute `base_motion` if supported by the local client.

It must check:

- camera config keys separately from baseline input keys. The task config may contain `top_camera`, but the baseline input probe must explicitly check the keys consumed by the target baseline, including `video.overlook_camera_view`, `video.left_camera_view`, and `video.right_camera_view`;
- observation keys: `instruction`, `state.joints`, `state.gripper`, `state.base`, `state.ee_pose`, required `video.*` camera keys, `timestep`, `reset`, and `robot_id` if provided;
- action keys: `action` with shape `(16,)`, `base_motion` with shape `(3,)`, `control_type="joint_position"`, `is_rel`, and `base_is_rel`;
- reward/success fields from GenManip/EBench metric output, not LabUtopia expert controller `done`;
- logging fields: `run_id`, `worker_id`, `episode_id`, `seed`, result path, stdout/stderr, and exception stack when present.

- [ ] **Step 5: Write Lift2 readiness report**

`docs/labutopia_lab_poc/lift2_readiness.md` must contain:

- command outputs for `gmp submit`, `gmp eval`, `gmp status`, and `lift2_eval_contract_probe`;
- per-task rows for `level1_pick`, `level1_place`, and `level1_open_door`;
- columns `Reset`, `Step`, `Reachability`, `Camera Framing`, `Metric`, and `Finding`, using only `PASS`, `FAIL`, or `BLOCKED`;
- schema rows for observation keys, camera input keys, action dialects, reward/success fields, and logging fields, using only `PASS`, `FAIL`, or `BLOCKED`;
- a clear statement that Franka/native acceptance-stage pass does not imply official baseline readiness unless Acceptance Stage 7 passes.
- a clear statement that any `FAIL` or `BLOCKED` row means Stage 7 was attempted, not passed, and Lift2 readiness wording is not allowed.

## Final Verification

Before claiming the native DryingBox lane is complete, run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc -q
python standalone_tools/labutopia_poc/validate_task_package.py
git diff --check
```

Then check the evidence manifest contains non-empty paths for audit, smoke, diagnostics, render frames, and Lift2 readiness if Acceptance Stage 7 was attempted.

If Acceptance Stage 7 was attempted, final reporting must say one of:

- `Stage 7 passed`: every readiness row is `PASS`;
- `Stage 7 attempted, blocked`: at least one row is `BLOCKED`;
- `Stage 7 attempted, failed`: at least one row is `FAIL`.

Only `Stage 7 passed` permits the local official-baseline-style Lift2 readiness claim.

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

## 2026-07-01 AAN Consumer Lane Boundary

This native acceptance-stage plan remains the historical **hand-built LabUtopia native DryingBox**
lane. It is not the same evidence lane as the newer **ConvertAsset AAN-ready package consumer**
work documented in:

```text
docs/superpowers/plans/2026-07-01-labutopia-aan-ready-package-ebench-integration.md
docs/labutopia_lab_poc/aan_consumer_handoff.md
```

Current boundary:

- Native Acceptance Stage 7 can still say the historical hand-built overlay passed a local
  Lift2 official-baseline-style contract, with its own material-boundary wording.
- AAN Consumer Stage 1-4b can now say the ConvertAsset DryingBox AAN package was received,
  checked, mounted, passed AAN runtime adapter/preflight, and passed local EBench /
  GenManip live smoke with `run_id=labutopia_aan_lift2_stage4b_20260701_085521`.
- AAN Consumer Stage 4b proves reset / step / render / metric / logging in the local
  smoke lane. It still does not prove official leaderboard completion, policy success,
  arbitrary asset support, or full visual material parity.
- Do not use old native Stage 5 / Stage 7 run ids as AAN package evidence.

## 2026-06-28 Norm Review Addendum

The material and stage rules below incorporate a three-angle review before Stage 2 execution:

| Review angle | Norm added to this plan |
| --- | --- |
| USD / Isaac material composition | Material closure must cover direct mesh, inherited Xform, collection, and `GeomSubset` bindings; `wrapper_local_looks_rebind` must copy full `UsdShade.Material` subtrees, shader connections, MDL source/subIdentifier, recursive helper MDL imports, and case-sensitive texture dependencies. |
| EBench / Lift2 readiness | `attempted` is not `passed`. Any `FAIL` or `BLOCKED` row in reset, step, reachability, camera framing, metric, schema, action dialect, reward/success, or logging blocks Lift2 readiness wording. Stage 2/3/4/5 now have explicit stop conditions and evidence fields. |
| Product / intern explanation | PM-facing HTML must explain why LabUtopia full-scene loading can work while EBench wrapper packaging can fail, why `/World/Looks` is normal but unsafe as an implicit wrapper dependency, and why default blue or `displayColor` fallback proves readability only, not native material closure. |

## 2026-06-29 Remote Aluminum / Material Closure Stage Boundary

Remote `Aluminum_Anodized_Charcoal.mdl` is not a Stage 3 blocker because Stage 3 proves wrapper composition, wrapper-local material rebinding, dependency reporting, and readable fallback boundaries. It becomes a closure item before runtime eval claims.

Use this split:

- **Acceptance Stage 4 owns the engineering disposition.** The package must choose exactly one path for remote Aluminum:
  - `local_mirror`: mirror the MDL into the asset package, record package-relative path, sha256, byte size, source URL, and worker `MDL_SYSTEM_PATH` coverage;
  - `explicit_waiver`: record waiver id, reason, affected material paths, affected task-visible surfaces, and `material_closure_kept_open=true`.
- **Acceptance Stage 5 owns the runtime material-closure verdict.** Eval-path diagnostics may classify material state as `resolved_native_material`, `mixed_native_and_fallback`, `degraded_fallback`, `open_remote_dependency_waived`, or `blocked`. `resolved_native_material` is allowed only when no remote waiver remains open and no task-visible surface relies on `displayColor` or preview fallback.
- **Acceptance Stage 6 owns the PM/evidence wording.** If Stage 5 passes eval readback while a waiver or fallback remains, the product page may say task readability and eval readback passed, but must say native MDL/texture material closure remains open.
- **Acceptance Stage 7 does not own material closure.** It checks Lift2 official-baseline-style observation/action/camera/reward/logging contracts. It can consume Stage 5/6 material evidence, but cannot upgrade a material-closure claim by itself.

This prevents three common mistakes: treating a visible frame as material closure, hiding a remote MDL behind wrapper success, or mixing Lift2 readiness with material packaging readiness.

## 2026-06-28 Stage 2 Execution Norm Addendum

Stage 2 is a native-only Isaac smoke, not an EBench wrapper pass. The smoke stage may reference the source `/World` so the native DryingBox keeps its original LabUtopia scene context, especially `/World/Looks` material prims. It must still isolate task physics: only the target `DryingBox_01`, required source material scope, required `PhysicsScene`, and explicitly recorded lighting/camera helpers may remain active. Other `/World` children must be deactivated or explicitly listed as active with a reason.

The stage generator must not silently skip isolation. In the target conda environment, `pxr` is not importable before `SimulationApp` or the Isaac Python environment is initialized. Therefore any USD child discovery must use a valid USD runtime, for example `/isaac-sim/python.sh` or a post-`SimulationApp` inspection path. If child discovery is unavailable, the tool must record `world_child_discovery_status=unavailable` or an equivalent error field and the stage must remain `attempted` or `blocked`; it must not emit a wrapper with no inactive overrides and then call the isolation complete.

Stage 2 evidence must be self-describing. `smoke.json` must record `stage2_status`, `stage2_passed`, and `stage2_validation_errors`. Downstream docs must not infer a pass from `runtime_physics_stable=true` alone.

Stage 2 material notes must distinguish these cases:

- `task_mesh_count` and `bound_task_mesh_count`: total task-visible meshes and meshes for which `ComputeBoundMaterial` returns a valid material.
- `unbound_task_mesh_count` and paths: task-visible meshes with no authored material binding and no computed material. This is a visibility/readability risk, not the same as a broken binding.
- `empty_authored_binding_count` and paths: authored `material:binding` exists but its target list is empty. This is a source-authored material gap and must not be misreported as a broken target.
- `unresolved_binding_target_count` and paths: authored task-visible `material:binding` has non-empty targets, but the targets do not resolve to a valid `UsdShade.Material`. This blocks `passed` unless there is a written, accepted waiver for a non-visible surface.
- `used_material_count` and paths: unique materials actually resolved by the task-visible meshes.
- `fallback_status`: fallback or preview color can make a frame readable, but it is not native material closure. It must be recorded separately from resolved MDL/texture material.

Every non-zero material count must include path lists, not only totals, so the next engineer can fix the exact mesh, `GeomSubset`, inherited Xform binding, collection binding, empty binding, or material target.

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

Acceptance stages use these status words consistently:

- `not_started`: no command has been run and no stage-specific evidence exists.
- `attempted`: the command ran and produced concrete evidence, but at least one required subcheck is not yet accepted.
- `blocked`: a prerequisite, environment issue, missing dependency, missing evidence field, or known asset/wrapper blocker prevents upgrading the claim. A blocker is not a project failure; it is the next engineering item to close.
- `failed`: the stage ran to completion and a required acceptance check produced an invalid result, for example non-finite physics trace, unresolved task-visible material, or missing metric readback.
- `passed`: every required acceptance check for that stage is `PASS`, with machine-readable evidence and no blocking waiver.

Acceptance Stage 7 has two additional reporting outcomes:

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
- Remote-only MDL is not `resolved_native_material` unless it is mirrored locally, hashed, and resolvable in the worker environment. Otherwise it must be explicitly waived as `open_remote_dependency_waived`, which keeps native MDL/texture closure open without implying `displayColor` fallback.
- `displayColor` is degraded fallback only. It must be recorded per mesh/subset plus as an aggregate status. `resolved_native_material` requires every task-visible surface to resolve native MDL/texture. Mixed surfaces must be reported as `mixed_native_and_fallback`; displayColor-only readability is `degraded_fallback`. Fallback authoring may use `primvars:displayColor` or explicit preview fallback, but it must not remove native bindings.

## Acceptance Stage Summary

| Acceptance Stage | Product meaning | Evidence required before moving on |
| --- | --- | --- |
| 1. Asset Audit | We know what the real DryingBox contains. | `audit.json`, source USD hash, prim/joint/handle list, material closure audit, risk flags. |
| 2. Isaac Smoke | The native asset can survive physics stepping by itself in the full source scene. | `smoke.json`, Isaac log, 120-step root/handle/joint trace, finite checks, PhysX warning classification, full-source material-runtime risk notes. |
| 3. Native Wrapper | EBench can see the real box without breaking hierarchy. | overlay `scene.usda`, manifest, no top-level handle payload, explicit `material_scope_policy`, material/reference report. |
| 4. Physics Override | Static additive override closure is defined and validated; runtime stability is rechecked in Stage 5. Remote Aluminum must be mirrored locally or explicitly waived here. | `physics_override.json`, override layer path, before/after warnings, mass/inertia/body target checks, remote Aluminum disposition, material validator checks, DOF map. |
| 5. Eval Readback | GenManip/EBench can reset, render, step, and score native open-door evidence through the wrapper. Runtime material closure is classified here, not inferred from Stage 4. | diagnostics JSON, reset obs schema, step response, metric raw output, material readback, material closure verdict, frame hashes, stdout/stderr/result paths. |
| 6. Evidence Package | PM, interns, and reviewers can reproduce the claim boundary. Material closure wording must match Stage 5 verdict and any Stage 4 waiver. | evidence manifest with git SHAs, env vars, commands, run ids, remote Aluminum disposition, material closure report, paths, screenshots. |
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
- Stage 1 PM-note snapshot: `reports/2026-06-15-labutopia-weekly/native-dryingbox-task1.html` said Stage 1 proved the native asset was worth continuing, but did not prove EBench wrapper, Isaac runtime, or Lift2 baseline readiness.

### Acceptance Stage 2: Native-Only Isaac Smoke

**Files:**
- Modify: `standalone_tools/labutopia_poc/run_native_dryingbox_smoke.py`
- Test: `tests/labutopia_poc/test_native_dryingbox_smoke_contract.py`
- Output: `saved/diagnostics/native_dryingbox_smoke_<utc_timestamp>/smoke.json`

- [x] **Step 1: Run smoke contract tests**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_native_dryingbox_smoke_contract.py -q
```

Expected: PASS.

- [x] **Step 2: Run native-only smoke**

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

- `stage2_status`, one of `attempted`, `blocked`, `failed`, or `passed`;
- `stage2_passed=false` unless every Stage 2 stop condition is closed;
- `stage2_validation_errors`, written into the JSON by the smoke tool itself, not only printed to stdout;
- `native_stage_mode=full_source_world`, `used_ebench_wrapper=false`, and `used_franka_shortcut=false`;
- `world_child_discovery_status`, `active_world_children`, and `inactive_world_children`; if sibling deactivation cannot be computed, the status is not `passed`;
- `step_count=120` and a per-step trace for root pose, handle pose, door joint angle, button joint position, and any other active DOF;
- `finite_trace=true` only if all recorded numeric pose/joint values are finite for all steps; the validator must recompute this from `step_trace` instead of trusting the top-level boolean alone;
- a monotonic step sequence from `1..120`, with per-step finite root pose, handle pose, and joint positions;
- `max_root_translation_drift_m`, `max_root_rotation_drift_deg`, `max_handle_translation_drift_m`, `door_joint_angle_min_deg`, `door_joint_angle_max_deg`, `button_joint_position_min_m`, and `button_joint_position_max_m`;
- `door_joint_path`, `door_joint_index`, `source_door_joint_limits_deg`, `source_door_joint_limits_source`, `button_joint_path`, and `button_joint_index`; the door limits must come from the source `RevoluteJoint` evidence or an explicit recorded fallback, not from an unexplained hard-coded assumption;
- `non_door_dof_drift_within_tolerance=true` only when non-door DOFs remain inside the configured tolerance, default `1e-4` meters or radians unless the script records a task-specific value;
- `physx_warning_allowlist`, `physx_warning_denylist`, and `unclassified_physx_warnings`; the validator must fail on any non-empty denylist or unclassified list and must verify the three lists partition `physx_warnings`;
- `physx_warning_scope`, so warnings from inactive or non-target siblings such as `/World/DryingBox_02` cannot be mistaken for target DryingBox evidence;
- full-source material-runtime notes: `/World/Looks` present or absent, material collection status, task mesh count, bound mesh count, unbound task mesh count and paths, empty authored binding count and paths, unresolved non-empty binding target count and paths, used material count and paths, remote material dependency count and paths, `material_binding_gap_count`, `material_binding_gap_paths`, per-path `material_binding_gap_details`, `material_binding_gap_readability_status`, fallback status, and material compiler warnings filtered to DryingBox materials when Isaac exposes them.

Acceptance Stage 2 proves full-source native physics smoke only. It does not prove EBench wrapper packaging, material rebinding, or Lift2 readiness.

- [x] **Step 3: Enforce stop condition**

Stop before Acceptance Stage 3 if any of these are true:

- `runtime_physics_stable=false`;
- `finite_trace=false`, or any NaN/Inf appears in root, handle, or joint traces;
- root or handle drift exceeds the explicit tolerance recorded in `smoke.json`;
- door angle leaves the physically allowed range from the source `RevoluteJoint` plus the configured tolerance;
- non-door DOF drift exceeds the configured tolerance without a written explanation;
- `physx_warning_denylist` is non-empty;
- `unclassified_physx_warnings` is non-empty;
- PhysX classification fields do not exactly partition the captured `physx_warnings`;
- world-child discovery failed, or non-target source siblings remain active without an explicit reason;
- material collection reports `collection_error` or does not prove whether task-visible bindings were resolved;
- full-source material-runtime notes show non-empty authored material targets that fail to resolve;
- full-source material-runtime notes show unbound meshes or empty authored bindings that would prevent a readable smoke frame and have no explicit fallback evidence.

Preserve the artifact and add the blocker to the evidence manifest.

Passed evidence, 2026-06-28:

- GenManip branch: `labutopia-stage2-native-smoke`
- Smoke artifact: `saved/diagnostics/native_dryingbox_smoke_20260628_143638/smoke.json`
- Generated stage: `saved/diagnostics/native_dryingbox_smoke_20260628_143638/native_dryingbox.usda`
- Stage result: `stage2_status=passed`, `stage2_passed=true`, and `stage2_validation_errors=[]`.
- Verification: `python -m py_compile standalone_tools/labutopia_poc/run_native_dryingbox_smoke.py && python -m pytest tests/labutopia_poc -q` -> `113 passed, 1 skipped`. The latest `smoke.json` also passes a fresh `validate_smoke_report()` recomputation after validator hardening.
- Positive physics signal: `runtime_physics_stable=true`, `finite_trace=true`, `step_count=120`, root drift `0.0`, handle drift `0.0`, door joint path `/World/DryingBox_01/RevoluteJoint`, button joint path `/World/DryingBox_01/button/PrismaticJoint`, and source door limits `[0.0, 120.0]` read from source USD.
- Stage isolation finding: closed for this artifact. `world_child_discovery_status=ok` via `isaac_python_sh`; active source children are only `Looks`, `PhysicsScene`, and `DryingBox_01`; `active_non_target_world_child_count=0`. Non-target siblings such as `DryingBox_02`, `Cabinet_01`, `Cabinet_02`, `GroundPlane`, and lab props are written as `active=false` overlays in the generated stage.
- PhysX finding: captured duplicate link-name warnings are fully allowlisted; `physx_warning_denylist=[]` and `unclassified_physx_warnings=[]`.
- Material finding: accepted for Stage 2 smoke readability, not native material closure. `unresolved_binding_target_count=0`, `material_collection_ok=true`, `task_mesh_count=32`, `bound_task_mesh_count=29`, `used_material_count=3`, `remote_material_dependency_count=0`, and material compiler warnings are empty. Three source material gaps remain visible in the evidence: `/World/DryingBox_01/button` is `unbound`, while `/World/DryingBox_01/Group/_900_1` and `/World/DryingBox_01/panel` have empty authored bindings. The generated smoke stage adds `primvars:displayColor` readability fallback to exactly those three paths, records `material_fallback_overlay_policy=stage2_readability_displayColor_not_native_material_closure`, and runtime evidence records `material_runtime_status=mixed_native_and_fallback`, `fallback_status=readability_evidence_accepted`, and `material_binding_gap_readability_status=accepted`.
- Product boundary: Stage 2 now proves the real LabUtopia `DryingBox_01` can be isolated from the full source scene and survive 120 Isaac physics steps by itself. It still does not prove EBench wrapper packaging, wrapper-local material rebinding, eval-path scoring, or official Lift2 baseline readiness.

### Acceptance Stage 3: Native Wrapper Composition

**Files:**
- Modify: `standalone_tools/labutopia_poc/build_asset_overlay.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`
- Test: `tests/labutopia_poc/test_build_asset_overlay.py`

- [x] **Step 1: Add wrapper assertions**

`tests/labutopia_poc/test_build_asset_overlay.py` must assert:

- native wrapper payloads/references the whole `/World/DryingBox_01`;
- `scene.usda` does not contain a top-level `obj_obj_DryingBox_01_handle` payload;
- nested handle remains under the drying-box wrapper;
- `drying_box_runtime_asset.strategy` is `native_complex_with_additive_physics_override`;
- `source_payload_used=true`;
- `surrogate_kept_for_debug_baseline=true`.

- [x] **Step 2: Generate native wrapper**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/build_asset_overlay.py --drying-box-strategy native_complex
```

Expected: generated overlay keeps one top-level `obj_DryingBox_01` wrapper and no independent top-level handle payload.

- [x] **Step 3: Verify composition contract**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_build_asset_overlay.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected: tests pass. If validator fails because Acceptance Stage 4 native physics checks are not implemented yet, record the exact failure and do not call wrapper work complete.

- [x] **Step 4: Check material and camera prerequisites**

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

- [x] **Step 5: Enforce wrapper stop condition**

Stop before Acceptance Stage 4 if any of these are true:

- native `reference` or `payload` dependencies are unresolved in the composed wrapper stage;
- the nested handle is missing under the DryingBox wrapper;
- any independent top-level handle payload exists;
- `wrapper_local_looks_rebind` leaves stale task-visible `/World/Looks/...` bindings;
- `preserve_owned_world_looks` is selected but the overlay does not explicitly own every required `/World/Looks` material;
- material subtree copying drops shader connections, `subIdentifier`, helper MDL imports, or texture dependencies;
- camera/light metadata required by task YAML is missing;
- composed-stage wrapper evidence cannot be opened and re-read by the validator.

Passed evidence, 2026-06-28:

- GenManip branch: `labutopia-stage3-native-wrapper`.
- Generated overlay: `/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/scene_usds/labutopia/level1_poc/lab_001/scene.usda`.
- Generated manifest: `/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/manifests/labutopia_level1_poc.json`.
- Wrapper topology: one top-level native wrapper at `/World/labutopia_level1_poc/obj_obj_DryingBox_01`, payload target `scene.usd</World/DryingBox_01>`, nested handle path `/World/labutopia_level1_poc/obj_obj_DryingBox_01/handle`, and no top-level `obj_obj_DryingBox_01_handle` payload.
- Material policy: `material_scope_policy=preserve_owned_world_looks`, `material_policy=owned_world_looks_payload_with_wrapper_local_rebind`, `material_status=mixed_native_and_fallback`. The source `/World/Looks` scope is payloaded under the DryingBox wrapper as wrapper-owned `Looks`, and all 32 recorded task-visible `material:binding` records rebind to `/World/labutopia_level1_poc/obj_obj_DryingBox_01/Looks/...`.
- Runtime material readback: validator opens the composed USD stage and calls `UsdShade.MaterialBindingAPI.ComputeBoundMaterial`; result is `bound_material_count=32`, `unresolved_binding_target_count=0`, `stale_source_binding_paths=[]`, `expected_mismatch_paths=[]`, `runtime_rebind_map_mismatch_paths=[]`, `unresolved_authored_binding_paths=[]`, `unexpected_unbound_mesh_paths=[]`, and no authored `/World/Looks` binding remains inside the wrapper subtree.
- Known material fallback boundary: three Stage 2 source material gaps remain explicitly labelled and use `displayColor` readability fallback only: `/World/labutopia_level1_poc/obj_obj_DryingBox_01/button`, `/World/labutopia_level1_poc/obj_obj_DryingBox_01/Group/_900_1`, and `/World/labutopia_level1_poc/obj_obj_DryingBox_01/panel`. This is not native MDL/texture material closure.
- Dependency report: local MDL files `material_11.mdl`, `material_08.mdl`, and `material_09.mdl` are recorded with hashes; recursive helper MDL imports are recorded with local paths, hashes, and byte sizes; `material_08.mdl` records `SubUSDs/textures/image4.jpg`; `material_09.mdl` records `SubUSDs/textures/image1.JPG`; worker `MDL_SYSTEM_PATH` is recorded as `/isaac-sim/materials/:{ASSETS_DIR}/scene_usds/labutopia/level1_poc/lab_001/SubUSDs/materials:{ASSETS_DIR}/miscs/mdl/labutopia/mdl`. `Aluminum_Anodized_Charcoal.mdl` remains an external remote URL dependency, so later stages must either mirror it locally or carry an explicit waiver before claiming full material closure.
- Camera/light prerequisites: wrapper manifest records task camera names `camera1`, `camera2`, primary evidence camera `camera2`, and deterministic light `/World/labutopia_level1_poc/DeterministicDomeLight`.
- Verification: `python -m pytest tests/labutopia_poc/test_validate_task_package.py::test_drying_box_material_readback_reports_runtime_rebind_map_drift tests/labutopia_poc/test_validate_task_package.py::test_drying_box_material_readback_does_not_whitelist_fallback_descendants tests/labutopia_poc/test_validate_task_package.py::test_drying_box_material_readback_reports_unresolved_authored_bindings -q` -> `3 passed`; `python standalone_tools/labutopia_poc/validate_task_package.py` -> `LabUtopia task package validation OK`; `python -m pytest tests/labutopia_poc -q` -> `120 passed, 1 skipped`.
- Product boundary: Acceptance Stage 3 proves the EBench/GenManip wrapper composition is now structurally valid and material bindings are wrapper-local/readable. It still does not prove Acceptance Stage 4 additive physics/articulation closure, Acceptance Stage 5 eval readback, or Acceptance Stage 7 official Lift2 baseline readiness.

### Acceptance Stage 4: Additive Physics Override And Articulation Closure

**Files:**
- Modify: `standalone_tools/labutopia_poc/build_asset_overlay.py`
- Modify: `standalone_tools/labutopia_poc/validate_task_package.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`
- Test: `tests/labutopia_poc/test_validate_task_package.py`
- Output: `saved/diagnostics/native_dryingbox_physics_override_<utc_timestamp>/physics_override.json`

- [x] **Step 1: Add validator checks**

`validate_task_package.py` must fail if:

- native `reference` or `payload` dependencies are unresolved;
- required post-rebind runtime `material:binding` targets are unresolved, or `ComputeBoundMaterial` fails for any task-visible mesh/subset;
- a runtime rebind map is missing when source bindings leave the wrapped subtree. The map is required evidence, but it does not by itself satisfy material closure;
- required MDL source assets, subIdentifiers, recursive helper MDL imports, or texture dependencies are unresolved, unhashed, remote-only, or absent from the worker `MDL_SYSTEM_PATH` without an explicit waiver;
- wrapper-local objects keep stale out-of-scope `/World/Looks/...` bindings after `wrapper_local_looks_rebind`;
- fallback `displayColor` is absent, black, low contrast, or used without recording `material_status=degraded_fallback` or `material_status=mixed_native_and_fallback`;
- remote-only MDL is labeled `resolved_native_material` without local mirror, hash, worker resolution evidence, or a waiver that explicitly keeps material closure open;
- `Aluminum_Anodized_Charcoal.mdl` has neither `remote_aluminum_disposition=local_mirror` nor `remote_aluminum_disposition=explicit_waiver`;
- `remote_aluminum_disposition=local_mirror` is missing package-relative path, source URL, sha256, byte size, and worker `MDL_SYSTEM_PATH` coverage evidence;
- `remote_aluminum_disposition=explicit_waiver` is missing waiver id, reason, affected material path, affected task-visible surfaces, and `material_closure_kept_open=true`;
- `remote_aluminum_disposition=explicit_waiver` is combined with `material_status=resolved_native_material`;
- `PhysicsScene` is missing or duplicated;
- `PhysicsArticulationRootAPI` is lost after wrapping;
- any joint `physics:body0/body1` target lacks `RigidBodyAPI`;
- active rigid bodies have invalid mass, inertia, `centerOfMass`, or `principalAxes`;
- collision shapes are invalid after root scale;
- door `RevoluteJoint` cannot be distinguished from button `PrismaticJoint`;
- camera/light names in validation metadata are missing.

- [x] **Step 2: Record Remote Aluminum disposition**

Stage 4 must record exactly one of these material dependency outcomes:

`local_mirror` outcome:

- `remote_aluminum_disposition=local_mirror`;
- original source URL;
- package-relative mirrored MDL path;
- sha256 and byte size of the mirrored MDL;
- worker `MDL_SYSTEM_PATH` entry that can resolve the mirrored MDL;
- evidence that the mirrored source still matches `info:mdl:sourceAsset:subIdentifier=Aluminum_Anodized_Charcoal`.

`explicit_waiver` outcome:

- `remote_aluminum_disposition=explicit_waiver`;
- waiver id, reason, owner, and date;
- affected material path: `/World/labutopia_level1_poc/obj_obj_DryingBox_01/Looks/Aluminum_Anodized_Charcoal`;
- affected task-visible surfaces or a generated list path;
- `material_closure_kept_open=true`;
- PM wording requirement: "remote Aluminum remains waived; native MDL/texture material closure remains open."

The generated manifest or `physics_override.json` must include a machine-readable gate like:

```json
{
  "static_material_dependency_gate": {
    "status": "passed",
    "remote_dependency_policy": "local_mirror_required_or_explicit_waiver",
    "remote_unmirrored_unwaived_count": 0,
    "remote_waiver_count": 1,
    "local_mirror_count": 0,
    "remote_dependency_records": [
      {
        "material_name": "Aluminum_Anodized_Charcoal",
        "source_material_path": "/World/Looks/Aluminum_Anodized_Charcoal",
        "runtime_material_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/Looks/Aluminum_Anodized_Charcoal",
        "resolution_mode": "local_mirror|explicit_waiver|blocked",
        "local_mirror_path": null,
        "local_mirror_sha256": null,
        "local_mirror_bytes": null,
        "worker_resolved_path": null,
        "waiver_id": "ALUMINUM_REMOTE_MDL_001",
        "waiver_reason": "remote source is intentionally not mirrored in this package revision",
        "closure_claim_allowed": false
      }
    ]
  }
}
```

This step may pass Stage 4 with an explicit waiver, because Stage 4 is an engineering dependency-disposition gate. It must not upgrade the material status to `resolved_native_material`.

- [x] **Step 3: Implement additive USD override**

Use only additive override opinions in the generated overlay. Do not edit the original LabUtopia USD. The override may fix or isolate invalid `FixedJoint_01` body targets, add finite mass/inertia where required, stabilize fixed-base behavior, and record `drive target`, `stiffness`, `damping`, and `maxForce` units.

Write `physics_override.json` with:

- override layer path and generated wrapper stage path;
- source USD path and source USD hash;
- before/after `physics:body0/body1` targets for every joint;
- active rigid body list with mass, inertia, `centerOfMass`, and `principalAxes`;
- collision API changes and any scale-compensation assumptions;
- DOF map that names the door `RevoluteJoint`, button `PrismaticJoint`, ignored DOFs, and metric DOF;
- drive parameters with units: target, stiffness, damping, maxForce, and whether they are authored or inherited;
- material validator summary, including unresolved, remote-only, fallback, waiver counts, `remote_aluminum_disposition`, and whether native material closure remains open;
- before/after PhysX warning diff if the validator or smoke harness can collect it.

Acceptance Stage 4 is a static additive-override closure stage. Runtime stability after the wrapper and override is confirmed in Acceptance Stage 5, not assumed here.

- [x] **Step 4: Bind metric to the door DOF**

`level1_open_door.yml` must bind scoring to the actual door `RevoluteJoint` readback. It must not read the first DOF blindly, and it must not use the button `PrismaticJoint` as the open-door metric source.

- [x] **Step 5: Verify static closure**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_validate_task_package.py tests/labutopia_poc/test_build_asset_overlay.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected: PASS and `LabUtopia task package validation OK`.

Completion evidence, 2026-06-29:

- GenManip branch: `labutopia-stage4-physics-override`
- GenManip commit: `02f330e feat: close LabUtopia DryingBox stage 4`
- Physics override artifact: `saved/diagnostics/native_dryingbox_physics_override_20260628_172756/physics_override.json`
- Packaged override artifact: `/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/manifests/native_dryingbox_physics_override.json`
- Verification: `python -m pytest tests/labutopia_poc/test_validate_task_package.py tests/labutopia_poc/test_build_asset_overlay.py -q` -> `47 passed`
- Verification: `python standalone_tools/labutopia_poc/validate_task_package.py` -> `LabUtopia task package validation OK`
- Verification: `python -m pytest tests/labutopia_poc -q` -> `126 passed, 1 skipped`
- Verification: `git diff --check` -> clean.
- Static physics closure: the wrapper authors exactly one `PhysicsScene`; `PhysicsArticulationRootAPI` is preserved; every active rigid body has finite mass, inertia, `centerOfMass`, and `principalAxes`; active rigid bodies are required to carry `PhysicsCollisionAPI`; and the validator checks the exact `physics:body0/body1` matrix for `FixedJoint_01`, door `RevoluteJoint`, and button `PrismaticJoint`.
- Metric closure: open-door scoring is bound to the door `RevoluteJoint`; the button `PrismaticJoint` is explicitly recorded as ignored by the open-door metric.
- Material dependency disposition: `remote_aluminum_disposition=explicit_waiver`, waiver id `ALUMINUM_REMOTE_MDL_001`, and `material_closure_kept_open=true`. This passes Stage 4 as an engineering dependency-disposition gate, but it does not allow `resolved_native_material` wording.
- Material boundary carried forward: full native MDL/texture material closure remains open until Stage 5 runtime readback and Stage 6 evidence wording prove a stronger status.
- Review closure: first spec review found four Stage 4 gaps, covering `PhysicsScene`/collision validation, saved diagnostics wiring, joint target strictness, and future `local_mirror` validation; all were fixed with tests. Second spec review reported no Stage 4 blockers.
- Deferred by design: runtime PhysX warning diff and eval-path material readback are Stage 5 responsibilities, not Stage 4 completion criteria.

### Acceptance Stage 5: Eval Readback And Render Validation

**Files:**
- Modify: `standalone_tools/labutopia_poc/capture_eval_render_diagnostics.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`
- Create: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_eval_<utc_timestamp>.json`
- Test: `tests/labutopia_poc/test_render_diagnostics_contract.py`

- [x] **Step 1: Run diagnostics contract tests**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_render_diagnostics_contract.py -q
```

Expected: PASS.

- [x] **Step 2: Run eval-path open-door readback**

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

- [x] **Step 3: Verify readback fields**

`diagnostics.json` must show:

- `readback_visible` or a concrete render blocker;
- `native_eval_readback_ready=true`;
- `remote_aluminum_disposition`, copied from Stage 4 evidence;
- `material_closure_eligible=true` only when `remote_aluminum_disposition=local_mirror`, the mirrored MDL resolves in the worker, and no waiver remains open;
- `native_material_closure_status`, one of `resolved_native_material`, `mixed_native_and_fallback`, `degraded_fallback`, `open_remote_dependency_waived`, or `blocked`;
- `runtime_material_dependency_status`, one of `closed_local_or_mirrored`, `open_waived`, or `blocked`;
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

Material readback has five separate outcomes:

- `material_status=resolved_native_material`: required for claiming native material closure. Runtime binding targets resolve, `ComputeBoundMaterial` succeeds, all required MDL/helper-MDL/texture dependencies resolve locally or via an explicit approved mirror, `remote_aluminum_disposition=local_mirror`, no remote waiver remains open, all task-visible surfaces resolve native material, no task-visible surface relies on `displayColor` or preview fallback, and material compiler warnings are absent or explicitly waived.
- `material_status=mixed_native_and_fallback`: some task-visible surfaces resolve native material and others rely on fallback. It may support task readability, but native material closure remains open.
- `material_status=degraded_fallback`: acceptable only for task-readability evidence. It may pass the eval readback stage if physics, hierarchy, and render readability are otherwise valid, but PM wording must say native material closure is still open.
- `material_status=open_remote_dependency_waived`: task-visible surfaces may bind native materials at USD level, but a required MDL dependency remains remote and explicitly waived. It may support task readability and eval readback, but native MDL/texture closure remains open.
- `material_status=blocked`: runtime material readback cannot be collected or required task-visible materials are missing/unresolved.

If `remote_aluminum_disposition=explicit_waiver`, Stage 5 may still pass `native_eval_readback_ready=true` for task-readability and metric evidence, but it must set `native_material_closure_status=open_remote_dependency_waived` unless a stronger blocker forces `blocked`; it must not set `resolved_native_material`.

- [x] **Step 4: Retake camera if needed**

Reject frames that are black, flat gray, missing the drying box, missing the door face, missing the handle, or dominated by wall/ceiling geometry. A passing PM-facing frame must show the box body, door edge, and handle clearly enough to explain the task. If the frame uses `displayColor` fallback rather than resolved native MDL materials, the diagnostics and PM note must say so explicitly.

Stop before Acceptance Stage 6 if `native_eval_readback_ready` is not true, if metric evidence does not read the door `RevoluteJoint`, if result/log paths are missing, or if material readback cannot distinguish `resolved_native_material`, fallback-driven readability, `open_remote_dependency_waived`, and `blocked`.

Completion evidence, 2026-06-29:

- GenManip branch: `labutopia-stage5-eval-readback`
- GenManip commit: `f743d03 feat: capture LabUtopia DryingBox eval readback`
- Remote branch: `fork/labutopia-stage5-eval-readback`
- Runtime diagnostics artifact: `saved/diagnostics/labutopia_native_open_door_eval_20260628_183219/diagnostics.json`
- Stage 5 eval manifest: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_eval_20260628_183219.json`
- Verification: `python -m pytest tests/labutopia_poc -q` -> `151 passed, 1 skipped`
- Verification: `python standalone_tools/labutopia_poc/validate_task_package.py` -> `LabUtopia task package validation OK`
- Runtime readback result: `native_eval_readback_ready=true`, `native_complex_dryingbox_ready=true`, `runtime_physics_stable=true`, and `eval_step_contract.passed=true`.
- Metric contract: `open_door_metric_contract.metric_reads_door_revolute_joint=true`; the metric target is `RevoluteJoint`, while `PrismaticJoint` remains explicitly ignored for the open-door metric.
- Evidence contract: `stage5_evidence_contract.passed=true`; the final artifact records result directory, stdout/stderr log paths, run id, worker id `local`, episode id, seed `000`, three unique frame paths, and frame hashes.
- Material boundary: `remote_aluminum_disposition=explicit_waiver`, `native_material_closure_status=open_remote_dependency_waived`, `runtime_material_dependency_status=open_waived`, and `material_closure_eligible=false`. Stage 5 proves eval-path task readability and runtime material readback classification; it does not claim full native MDL/texture material closure.
- Runtime material readback now records 32 task-visible material records, runtime `ComputeBoundMaterial` results, binding relationship metadata where inferable, Shader `info:mdl:sourceAsset`, `subIdentifier`, resolved local MDL path, and MDL hash. Recursive helper MDL and texture dependency closure remain governed by the Stage 4 material validator plus the explicit Aluminum waiver; Stage 6 wording must keep native material closure open.
- Visual QA: independent render review returned `WARN`, not `FAIL`. The box body, blue door edge, and handle are identifiable enough for readback evidence, but the camera angle is not ideal for a PM showcase because a large overhead/table surface dominates the frame. Stage 6 must present this as acceptable machine evidence and either label it clearly or add a better PM-facing retake before using it as a polished product image.
- Lift2 boundary: `lift2_contract_ready=false`; no Stage 5 wording may claim official Lift2 baseline readiness.

### Acceptance Stage 6: Evidence Package And PM Claim Boundary

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_acceptance_<utc_timestamp>.json`
- Modify: `docs/records/2026-06-22-labutopia-ebench-weekly-report.md`
- Modify: `docs/records/evidence/2026-06-22-labutopia-ebench-weekly-report/index.html`
- Modify: `reports/2026-06-15-labutopia-weekly/native-dryingbox-task1.html`

- [x] **Step 1: Build one evidence manifest**

The manifest must include:

- GenManip git SHA and LabUtopia git SHA;
- conda environment path;
- `ASSET_OVERLAY_ROOT`;
- every command used in Acceptance Stages 1-5;
- run id, worker id, seed, task name, and result paths;
- `audit.json`, `smoke.json`, `diagnostics.json`, frame hashes, and log paths;
- material closure report, including `material_scope_policy`, worker `MDL_SYSTEM_PATH`, `remote_aluminum_disposition`, mirrored MDL path/hash or waiver id, MDL compiler warnings, unresolved dependency list, waiver list, and fallback status;
- `claim_boundary.native_material_closure_claim_allowed`, derived from Stage 5 `native_material_closure_status`;
- `claim_boundary.material_closure_blocker`, one of `none`, `remote_aluminum_explicit_waiver`, `fallback_surfaces`, `unresolved_material_dependency`, or `material_readback_blocked`;
- visual review verdict;
- current claim boundary.

- [x] **Step 2: Update PM-facing wording**

Use this wording if Acceptance Stages 1-5 pass:

```text
原生 DryingBox_01 已经通过 EBench/GenManip eval path 的 native open-door readback：资产不是 surrogate cube，门、把手、joint 和画面都有证据。但这仍然只是 Franka/native acceptance stage，不等于 official Lift2 baseline 已通过。
```

Append this sentence when `material_status=degraded_fallback` or `material_status=mixed_native_and_fallback`:

```text
当前画面可读性至少部分依赖 displayColor fallback，native MDL/texture material closure 仍是单独未闭环项，不能宣称原生材质已经完全接入。
```

Append this sentence when `remote_aluminum_disposition=explicit_waiver`:

```text
Aluminum_Anodized_Charcoal.mdl 当前采用 waiver 记录为 remote dependency，Stage 5 可以继续证明任务可读性和 eval readback，但不能宣称 full native MDL/texture material closure。
```

Use this wording when Stage 5 reports `material_status=open_remote_dependency_waived`:

```text
原生 DryingBox_01 的 eval readback 和画面可读性可以汇报为通过；但 Aluminum 材质仍保留 remote dependency waiver，native MDL/texture material closure 继续保持 open，不能说原生材质已经完全接入。
```

Use this sentence only when Stage 5 reports `material_status=resolved_native_material`:

```text
原生材质闭环已通过 runtime readback：task-visible material binding、MDL/helper-MDL/texture 依赖、本地 mirrored Aluminum、材质编译状态和 fallback 边界都有机器可复验证据。
```

Use this wording if any Acceptance Stage 1-5 check fails:

```text
原生 DryingBox_01 的接入正在推进，但当前 blocker 仍在 native asset / physics / wrapper / readback 中的一个具体验收阶段；不能宣称 official baseline 可评。
```

- [x] **Step 3: Keep evidence and product page aligned**

The HTML page must link to the exact evidence manifest and explain old image issues in plain language: camera view mismatch, unresolved native `material:binding`, top-level handle payload risk, and the difference between surrogate and native complex asset.

#### Acceptance Stage 6 Completion Evidence - 2026-06-28

- GenManip evidence manifest: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_acceptance_20260628_183219.json`
- Source Stage 5 eval manifest: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_eval_20260628_183219.json`
- Runtime diagnostics artifact: `saved/diagnostics/labutopia_native_open_door_eval_20260628_183219/diagnostics.json`
- GenManip commit for Stage 5/6 evidence: `f743d03 feat: capture LabUtopia DryingBox eval readback`
- LabUtopia docs/pages commit carrying Stage 5 and Stage 6 status before this update: `3d42bbc docs: record dryingbox stage 5 completion`
- Updated GenManip PM evidence page: `docs/records/evidence/2026-06-22-labutopia-ebench-weekly-report/index.html`
- Updated GenManip PM markdown: `docs/records/2026-06-22-labutopia-ebench-weekly-report.md`
- Updated LabUtopia PM pages: `reports/2026-06-15-labutopia-weekly/index.html` and `reports/2026-06-15-labutopia-weekly/native-dryingbox-task1.html`
- Stage 6 manifest includes GenManip/LabUtopia SHAs, recommended conda env path `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310`, effective Isaac Kit Python interpreter, `ASSET_OVERLAY_ROOT`, `MDL_SYSTEM_PATH`, Stage 1-5 commands/artifacts/hash, run id, worker id, seed, episode id, stdout/stderr paths, three frame hashes, material closure report, Aluminum waiver, visual review verdict, and claim boundary.
- PM wording now says: native `DryingBox_01` passed Franka/native eval-path readback; metric reads the door `RevoluteJoint`; this does not prove official Lift2 baseline readiness.
- Material wording now says: `remote_aluminum_disposition=explicit_waiver`, waiver id `ALUMINUM_REMOTE_MDL_001`, `native_material_closure_status=open_remote_dependency_waived`, `native_material_closure_claim_allowed=false`; full native MDL/texture material closure remains open.
- Visual wording now says: Stage 5 image is diagnostic machine evidence with `WARN`, not a polished PM showcase. DryingBox body, blue door edge, and handle are identifiable, but the current camera is dominated by table/overhead geometry; retake is recommended before using it as a showcase screenshot.
- As of the 2026-06-28 Stage 6 evidence, Stage 6 completion did not change Stage 7 status: `lift2_contract_ready=false` and `official_baseline_evaluable=false` were still the active boundary. This historical boundary is superseded by the 2026-06-29 Stage 7 completion evidence below, where the local Lift2 contract becomes ready while official leaderboard/baseline evaluation remains unclaimed.

### Acceptance Stage 7: Lift2 Official-Baseline Contract Check

Stage 7 consumes the material status produced by Stages 4-6; it does not resolve, waive, or newly claim native material closure. Passing Stage 7 only supports the Lift2 official-baseline-style contract claim.

**Files:**
- Modify: `standalone_tools/labutopia_poc/validate_task_package.py`
- Create: `standalone_tools/labutopia_poc/lift2_eval_contract_probe.py`
- Create: `docs/labutopia_lab_poc/lift2_readiness.md`
- Test: `tests/labutopia_poc/test_validate_task_package.py`

- [x] **Step 1: Run static checks**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc -q
python standalone_tools/labutopia_poc/validate_task_package.py
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json >/tmp/franka_poc.json
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json >/tmp/lift2_candidate.json
git diff --check
```

Expected: all commands pass.

- [x] **Step 2: Start eval server with explicit composite assets**

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
LABUTOPIA_POC_ASSETS_OVERLAY_ROOT=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/assets \
PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:$PWD \
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
  ray_eval_server.py --host 127.0.0.1 --port 18188 \
  --run_id labutopia_lift2_composite_20260629_0404 \
  --no_save_process --episode_recorder_save_every 0 \
  --reset_timeout 1200 --step_timeout 1200 --load_config_timeout 300 --create_timeout 1200
```

Expected: server starts with the LabUtopia plus Lift2 composite asset root and no missing Lift2 robot/curobo asset errors.

- [x] **Step 3: Run Lift2 candidate smoke/eval**

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
gmp submit ebench/labutopia_lab_poc/lift2_candidate \
  --run_id labutopia_lift2_composite_20260629_0404 \
  --host 127.0.0.1 --port 18188
gmp eval -a r5a -g lift2 --worker_ids 0 \
  --run_id labutopia_lift2_composite_20260629_0404 \
  --host 127.0.0.1 --port 18188 \
  --no_save_process --frame_save_interval 0 --chunk_size 1
gmp status --run_id labutopia_lift2_composite_20260629_0404 \
  --host 127.0.0.1 --port 18188
```

Expected: each task either reaches reset/step/metric with saved results or records a concrete blocker such as camera framing, reachability, base collision, missing object, missing asset, action schema mismatch, or blank camera.

This step by itself records a Lift2 candidate attempt. It is not a pass unless every required task reaches reset, step, metric, camera framing, reward/success, and logging without `FAIL` or `BLOCKED`.

- [x] **Step 4: Run `lift2_eval_contract_probe`**

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

- [x] **Step 5: Write Lift2 readiness report**

`docs/labutopia_lab_poc/lift2_readiness.md` must contain:

- command outputs for `gmp submit`, `gmp eval`, `gmp status`, and `lift2_eval_contract_probe`;
- per-task rows for `level1_pick`, `level1_place`, and `level1_open_door`;
- columns `Reset`, `Step`, `Reachability`, `Camera Framing`, `Metric`, and `Finding`, using only `PASS`, `FAIL`, or `BLOCKED`;
- schema rows for observation keys, camera input keys, action dialects, reward/success fields, and logging fields, using only `PASS`, `FAIL`, or `BLOCKED`;
- a clear statement that Franka/native acceptance-stage pass does not imply official baseline readiness unless Acceptance Stage 7 passes.
- a clear statement that any `FAIL` or `BLOCKED` row means Stage 7 was attempted, not passed, and Lift2 readiness wording is not allowed.

#### Acceptance Stage 7 Attempt Evidence - 2026-06-28

Result: `Stage 7 attempted, blocked`.

GenManip artifacts:

- Readiness report: `docs/labutopia_lab_poc/lift2_readiness.md`
- Stage 7 manifest: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_stage7_lift2_contract_20260628_191421.json`
- Probe bundle: `docs/labutopia_lab_poc/evidence_manifests/lift2_contract_probe_20260628_191421/`
- Probe JSON: `docs/labutopia_lab_poc/evidence_manifests/lift2_contract_probe_20260628_191421/probe.json`

Static checks passed:

```text
python -m pytest tests/labutopia_poc -q
165 passed, 1 skipped

python standalone_tools/labutopia_poc/validate_task_package.py
LabUtopia task package validation OK

python -m json.tool configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json
PASS

python -m json.tool configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json
PASS

git diff --check
PASS
```

Runtime attempt boundary:

- Isolated run id: `labutopia_lift2_schema_smoke_20260628_191421`
- Isolated port: `18088`, intentionally not `8087`, to avoid collision with other runs.
- Runtime Python: `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python`
- GenManip client source: `/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src`
- `gmp submit`, `gmp eval`, and `gmp status` were attempted through `genmanip_client.cli` and recorded exit code `1` because no eval server was running on `127.0.0.1:18088`.
- A long Isaac eval server was not started because preflight still reports missing Lift2 composite assets:
  - `saved/assets/robot_usds/lift2/robot.usd`
  - `saved/assets/miscs/curobo/R5a/r5a_left_arm.yml`
  - overlay `robot_usds/lift2/robot.usd`

`meta_info.pkl` was absent in the preflight snapshot, but this is a watch item
rather than the current hard blocker: GenManip's LabUtopia POC reset path calls
`load_or_build_labutopia_poc_meta_info`, so fallback metadata can be built from
the live scene. Verify that during the first live Lift2 reset.

Stage 7 schema matrix:

| Row | Status | Finding |
| --- | --- | --- |
| observation keys | `BLOCKED` | no live reset observation schema |
| camera input keys | `BLOCKED` | no live `video.overlook_camera_view`, `video.left_camera_view`, or `video.right_camera_view` evidence |
| action dialects | `PASS` | static 16D Lift2 joint-position action plus 3D `base_motion` matrix is valid |
| reward/success fields | `BLOCKED` | no GenManip/EBench live step metric output |
| logging fields | `BLOCKED` | no live episode result path, seed, episode id, stdout/stderr from server side |

Product boundary:

```text
Stage 7 was attempted and produced useful blockers, but it did not pass.
lift2_contract_ready=false
official_baseline_evaluable=false
```

Historical next engineering step from this 2026-06-28 attempt: build the composite Lift2 asset root by combining the LabUtopia overlay with default `robot_usds/lift2` and `miscs/curobo/R5a`, then rerun the isolated eval server plus `gmp submit/eval/status` and `lift2_eval_contract_probe --live`. This item was resolved by the 2026-06-29 completion evidence below. Treat `meta_info.pkl` as a live-reset watch item covered by the LabUtopia POC fallback, not as the primary asset-root blocker.

#### Acceptance Stage 7 Completion Evidence - 2026-06-29

Result: `Stage 7 passed` for the local official-baseline-style Lift2 contract.

GenManip artifacts:

- Readiness report: `docs/labutopia_lab_poc/lift2_readiness.md`
- Stage 7 manifest: `docs/labutopia_lab_poc/evidence_manifests/native_dryingbox_stage7_lift2_contract_20260629_0404.json`
- Probe bundle: `docs/labutopia_lab_poc/evidence_manifests/lift2_contract_probe_20260629_0404/`
- Full eval logs: `gmp_submit.txt`, `gmp_eval.txt`, `gmp_status.txt`, and `result_info_summary.txt` inside the probe bundle.
- Per-task live probes: `probe_level1_pick.json`, `probe_level1_place.json`, and `probe.json` for `level1_open_door`.

Resolved blocker:

- Composite asset root is now present at `/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets`.
- The GenManip worktree `saved/assets` symlink points to that composite root.
- Preflight confirms `robot_usds/lift2/robot.usd`, `miscs/curobo/R5a/r5a_left_arm.yml`, LabUtopia `scene.usda`, LabUtopia manifest, native physics override manifest, and LabUtopia mesh data exist.
- `curobo` imports from `/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src`.

Runtime evidence:

- Full eval run id: `labutopia_lift2_composite_20260629_0404`
- Isolated port: `18188`; port `8087` was left untouched for another task.
- `gmp status` reports complete, `completed=3`, `in_progress=0`, and no active workers.
- `level1_pick`, `level1_place`, and `level1_open_door` all wrote `result_info.json` with `metric_score`, `score=0.0`, and `success_rate=0`.
- The eval server on `18188` was shut down after evidence collection; `8087` remained open as an external task lane.

Stage 7 task matrix:

| Task | Reset | Step | Reachability | Camera Framing | Metric | Finding |
| --- | --- | --- | --- | --- | --- | --- |
| `level1_pick` | `PASS` | `PASS` | `PASS` | `PASS` | `PASS` | Full eval reached result logging; live probe returned reset observation, image-shaped cameras, and step responses for every action dialect. |
| `level1_place` | `PASS` | `PASS` | `PASS` | `PASS` | `PASS` | Full eval reached result logging; live probe returned reset observation, image-shaped cameras, and step responses for every action dialect. |
| `level1_open_door` | `PASS` | `PASS` | `PASS` | `PASS` | `PASS` | Full eval reached result logging; live probe returned reset observation, image-shaped cameras, and step responses for every action dialect. |

Stage 7 schema matrix:

| Row | Status | Finding |
| --- | --- | --- |
| observation keys | `PASS` | all three live probes expose required Lift2 baseline inputs |
| camera input keys | `PASS` | all three live probes expose `video.overlook_camera_view`, `video.left_camera_view`, and `video.right_camera_view` as image-shaped arrays |
| action dialects | `PASS` | 16D Lift2 joint-position action plus 3D `base_motion` matrix produced live step responses for zero, OpenPI-style, X-VLA-style, and optional InternVLA-A1 dialects |
| reward/success fields | `PASS` | live step responses expose GenManip/EBench metric/reward/success fields |
| logging fields | `PASS` | run id, worker id, episode id, seed, result path, stdout, and stderr are recorded |

Product boundary:

```text
Stage 7 passed
lift2_contract_ready=true
local_official_baseline_style_contract_ready=true
official_baseline_evaluable=false
```

This allows local official-baseline-style Lift2 readiness wording. It still does
not claim official leaderboard reproduction, official EBench score release,
model quality, or native material closure. The current Lift2 candidate eval
scores are all `0.0`, which means the tested simple/default action did not solve
the tasks; that is a policy/controller result, not a runtime-contract failure.
The Stage 4-6 material boundary also remains unchanged:
`native_material_closure_status=open_remote_dependency_waived` and
`native_material_closure_claim_allowed=false`.

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

## 2026-07-01 ConvertAsset AAN Handoff

ConvertAsset `Asset Application Normalizer` now provides a DryingBox AAN-ready
package for the next LabUtopia / EBench consumer step.

Retained producer evidence:

```text
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/
```

Verified consumer-facing status:

```text
schema_version=asset_application_normalizer.v1
asset_id=DryingBox_01_overlay
task_id=Lift2.DryingBox
overall_status=pass
target_runtime_profile=isaac41
target_benchmark_profile=ebench-lift2
blocked_reasons_len=0
waivers_len=0
```

AAN gates are `pass` for `usd_closure`, `material_closure`, `physics_static`,
`runtime_smoke`, and `benchmark_contract`. ConvertAsset AAN tests checked in this
review:

```bash
cd /cpfs/user/zhuzihou/dev/ConvertAsset
python -m pytest tests/test_asset_application_normalizer_cli.py \
  tests/test_asset_application_normalizer_pm_and_mjcf.py -q
```

Observed result: `29 passed`.

This supersedes the old material-boundary wording for the AAN package path. The
historical Stage 4-6 `open_remote_dependency_waived` statement remains true for
the older hand-built LabUtopia overlay evidence, but the ConvertAsset handoff now
provides a package-local asset closure route with retained manifest evidence.

New continuation plan:

```text
LabUtopia AAN-Ready Package 接入 EBench 计划
```

Six stages:

| Stage | Name | Status on 2026-07-01 | Meaning |
|---|---|---|---|
| 1 | AAN package intake | Done | ConvertAsset retained package, manifest, hash, and package identity are locked. |
| 2 | Consumer manifest check | Done | AAN schema, target profiles, gates, entrypoints, dependency closure, blockers, and waivers pass consumer checks. |
| 3 | Task-root wiring and dry-run composition | Done | AAN package is mounted into the composite task root; `asset.usd`, task files, and required prims resolve without local package repair. |
| 4 | AAN runtime adapter and live eval smoke | Done / Stage 4b PASS | AAN-specific `.usda` wrapper, task profile, manifest routing, digest hard gates, and fresh `level1_open_door` reset / step / render / metric / logging smoke pass. |
| 5 | PM evidence and weekly HTML update | Done | Weekly HTML now includes AAN evidence while preserving official-score, model-success, and full-visual-parity boundaries. |
| 6 | Regression, boundary, and replication hardening | In progress | DryingBox no-local-repair guard is in place; `MuffleFurnace` and `Beaker_01` have Stage 1-3 replication PASS and no-local-repair PASS; Stage 4b replication is BLOCKED by the missing generic AAN task/evaluator adapter. |

Current Stage 1-4b evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_package_intake_20260701_0719.json
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_consumer_check_20260701_0000.json
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_task_mount_20260701_0000.json
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_adapter_20260701_0000.json
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_20260701_085521.json
```

Current Stage 6 replication evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/aan_stage6_replication_summary_20260701_0950.json
highest_common_passed_stage=3
stage4b_live_smoke_status=BLOCKED
failure_owner=GenManip / LabUtopia consumer
```

Stage 4 must not reuse the old `lift2_candidate` run as AAN evidence. The old
config still points at:

```text
scene_usds/labutopia/level1_poc/lab_001/scene
```

The AAN package entrypoint is:

```text
labutopia_aan_packages/dryingbox_01_overlay/asset.usd
```

Because GenManip currently loads `${ASSETS_DIR}/${usd_name}.usda`, Stage 4a has
generated an AAN-specific wrapper:

```text
scene_usds/labutopia/aan/dryingbox_01_overlay_scene.usda
```

and an AAN-specific task profile that sets:

```text
usd_name: scene_usds/labutopia/aan/dryingbox_01_overlay_scene
```

The Stage 4a evidence records `legacy_overlay_used=false`,
`package_tree_digest=mounted_package_tree_digest`, and wrapper references parsed
from the USDA reference list. Stage 4b evidence records `status=PASS`,
`legacy_overlay_used=false`, `submit_exit_code=0`, `probe_or_eval_exit_code=0`,
`reset_passed=true`, `step_passed=true`, `render_passed=true`, `metric_passed=true`,
`logging_passed=true`, and `result_info_exists=true`.

Stage 4b also records `score=0.0`, `success_rate=0`, and
`mdl_compiler_error_count=636`. These are important claim boundaries: zero score is
policy/task execution quality, not package-consumption failure; MDL compiler warnings
do not block the smoke pass, but they do block full visual material parity wording.

DryingBox consumer integration can now be reported because Stages 1-5 pass. Stage 6
is the replication/hardening phase and must not block the single-asset DryingBox
consumer claim. Stage 6 currently proves Stage 1-3 can be reused on non-DryingBox
USD assets; it does not yet prove non-DryingBox live eval smoke.

Runtime implementation belongs in a GenManip worktree that contains the
LabUtopia POC tooling. The active AAN consumer branch/worktree is:

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/
```

Relevant commits:

```text
5161227 feat: add AAN consumer package check
72ca5e0 fix: block closure-level AAN dependencies
9d042da feat: add AAN task root mount check
```

Detailed consumer handoff:

```text
docs/labutopia_lab_poc/aan_consumer_handoff.md
```

Detailed six-stage plan:

```text
docs/superpowers/plans/2026-07-01-labutopia-aan-ready-package-ebench-integration.md
```

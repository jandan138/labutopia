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
- For packaged EBench wrapper composition, prefer `wrapper_local_looks_rebind`: copy only task-used material prims into an owned wrapper-local `Looks` scope, then reauthor `material:binding` to those runtime-local material paths.
- `preserve_owned_world_looks` is allowed only if the overlay explicitly owns the required `/World/Looks` prims, avoids name collisions, and proves all runtime bindings resolve there.
- Preserve MDL `sourceAsset` and `subIdentifier` exactly during rebasing. Do not derive the subIdentifier from the MDL filename.
- The material closure report must cover binding target validity, `ComputeBoundMaterial` result, MDL source asset, MDL subIdentifier, resolved MDL path, helper MDL imports, texture references, hashes, remote/local status, and worker `MDL_SYSTEM_PATH`.
- `displayColor` is degraded fallback only. It must be distinct, non-black, and high-contrast enough for body, door, and handle readability, but it cannot be counted as native material closure.

## Acceptance Stage Summary

| Acceptance Stage | Product meaning | Evidence required before moving on |
| --- | --- | --- |
| 1. Asset Audit | We know what the real DryingBox contains. | `audit.json`, source USD hash, prim/joint/handle list, material closure audit, risk flags. |
| 2. Isaac Smoke | The native asset can survive physics stepping by itself. | `smoke.json`, Isaac log, 60-120 step root/handle/joint trace, finite checks. |
| 3. Native Wrapper | EBench can see the real box without breaking hierarchy. | overlay `scene.usda`, manifest, no top-level handle payload, explicit `material_scope_policy`, material/reference report. |
| 4. Physics Override | Door physics is repaired additively and reads the right DOF. | override manifest, before/after warnings, mass/inertia/body target checks, material validator checks, door trace. |
| 5. Eval Readback | GenManip/EBench can reset, render, step, and score native open-door evidence. | diagnostics JSON, reset obs schema, step response, metric raw output, material readback, frame hashes. |
| 6. Evidence Package | PM, interns, and reviewers can reproduce the claim boundary. | evidence manifest with git SHAs, env vars, commands, run ids, material closure report, paths, screenshots. |
| 7. Lift2 Contract Check | The lane is checked against official baseline data contracts. | `gmp` logs, observation/action schema probe, relative/absolute base action probes. |

Use `Acceptance Stage` for this seven-stage native DryingBox acceptance lane. Reserve `Task` for concrete engineering work items that may be added under a stage later.

---

### Acceptance Stage 1: Native Asset Audit

**Files:**
- Modify: `standalone_tools/labutopia_poc/audit_native_dryingbox.py`
- Test: `tests/labutopia_poc/test_native_dryingbox_audit.py`
- Output: `saved/diagnostics/native_dryingbox_audit_<utc_timestamp>/audit.json`

- [ ] **Step 1: Run audit contract tests**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_native_dryingbox_audit.py -q
```

Expected: PASS. If it fails, fix the audit schema before collecting new evidence.

- [ ] **Step 2: Re-run the native audit**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/audit_native_dryingbox.py \
  --labutopia-root /cpfs/shared/simulation/zhuzihou/dev/LabUtopia \
  --source-prim-path /World/DryingBox_01 \
  --output-root saved/diagnostics/native_dryingbox_audit_$(date -u +%Y%m%d_%H%M%S)
```

Expected: exit `0` and write `audit.json`.

- [ ] **Step 3: Check audit evidence**

`audit.json` must record:

- `stage_sha256`;
- `defaultPrim`, `upAxis`, `metersPerUnit`, `xformOpOrder`, and root scale;
- per task-visible mesh material data: source `material:binding` target, composed binding target, `ComputeBoundMaterial` result, binding scope status, material prim validity, MDL source asset, MDL subIdentifier, resolved MDL path, helper MDL imports, texture dependencies, remote/local status, hashes, and displayColor fallback status;
- `reference`/`payload` dependency status;
- `PhysicsArticulationRootAPI`;
- rigid bodies, collisions, mass, inertia, `centerOfMass`, and `principalAxes`;
- `physics:body0/body1` for every joint;
- door `RevoluteJoint`, button `PrismaticJoint`, and handle candidates;
- known risk flags, including invalid body target, non-identity root scale, missing mass/inertia, multiple DOFs, out-of-scope `/World/Looks` dependency, missing MDL, missing texture, remote-only MDL, and black or low-contrast fallback color.

- [ ] **Step 4: Record PM wording**

Update the PM note only to say: native `DryingBox_01` is worth continuing, but Acceptance Stage 1 alone does not prove EBench/Lift2 evaluability.

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

- [ ] **Step 3: Enforce stop condition**

If `smoke.json` contains `runtime_physics_stable=false`, NaN/Inf pose values, or unexplained joint drift, stop before Acceptance Stage 3. Preserve the artifact and add the blocker to the evidence manifest.

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
- runtime rebind map if any source target leaves the wrapped subtree, especially `/World/Looks/...`;
- resolved/unresolved binding targets, `ComputeBoundMaterial` results, and stale source binding checks;
- MDL source assets, MDL subIdentifiers, helper MDL imports, texture paths, hashes, and remote/local status;
- the exact worker `MDL_SYSTEM_PATH` required for LabUtopia materials;
- fallback `displayColor` policy for task-visible meshes, labeled as `material_status=degraded_fallback` when used;
- payload dependency report;
- wrapper bbox, source scale, axis/up-axis, and workspace translation;
- camera/light prim names expected by task YAML.

### Acceptance Stage 4: Additive Physics Override And Articulation Closure

**Files:**
- Modify: `standalone_tools/labutopia_poc/build_asset_overlay.py`
- Modify: `standalone_tools/labutopia_poc/validate_task_package.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`
- Test: `tests/labutopia_poc/test_validate_task_package.py`

- [ ] **Step 1: Add validator checks**

`validate_task_package.py` must fail if:

- native `reference` or `payload` dependencies are unresolved;
- required post-rebind runtime `material:binding` targets are unresolved, or `ComputeBoundMaterial` fails for any task-visible mesh;
- a runtime rebind map is missing when source bindings leave the wrapped subtree. The map is required evidence, but it does not by itself satisfy material closure;
- required MDL source assets, subIdentifiers, helper MDL imports, or texture dependencies are unresolved, unhashed, remote-only, or absent from the worker `MDL_SYSTEM_PATH` without an explicit waiver;
- wrapper-local objects keep stale out-of-scope `/World/Looks/...` bindings after `wrapper_local_looks_rebind`;
- fallback `displayColor` is absent, black, low contrast, or used without recording `material_status=degraded_fallback`;
- `PhysicsScene` is missing or duplicated;
- `PhysicsArticulationRootAPI` is lost after wrapping;
- any joint `physics:body0/body1` target lacks `RigidBodyAPI`;
- active rigid bodies have invalid mass, inertia, `centerOfMass`, or `principalAxes`;
- collision shapes are invalid after root scale;
- door `RevoluteJoint` cannot be distinguished from button `PrismaticJoint`;
- camera/light names in validation metadata are missing.

- [ ] **Step 2: Implement additive USD override**

Use only additive override opinions in the generated overlay. Do not edit the original LabUtopia USD. The override may fix or isolate invalid `FixedJoint_01` body targets, add finite mass/inertia where required, stabilize fixed-base behavior, and record `drive target`, `stiffness`, `damping`, and `maxForce` units.

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
- `native_complex_dryingbox_ready=true`;
- `runtime_physics_stable=true`;
- `object_config.obj_DryingBox_01` registered as `existed_object`;
- `articulation_info.part.handle=/handle`;
- `obj_DryingBox_01_handle` registered from the nested handle path;
- pre/post door joint angle and joint name;
- handle world pose;
- drive target and collision warnings;
- render validation using required object visibility, not just non-black pixels.
- material readback after reset, including source binding target, runtime binding target, material status, MDL source asset, subIdentifier, and any material compiler warnings.

Material readback has two separate outcomes:

- `material_status=resolved_native_material`: required for claiming native material closure. Runtime binding targets resolve, `ComputeBoundMaterial` succeeds, required MDL/texture dependencies resolve, and material compiler warnings are absent or explicitly waived.
- `material_status=degraded_fallback`: acceptable only for task-readability evidence. It may pass the eval readback stage if physics, hierarchy, and render readability are otherwise valid, but PM wording must say native material closure is still open.

- [ ] **Step 4: Retake camera if needed**

Reject frames that are black, flat gray, missing the drying box, missing the door face, missing the handle, or dominated by wall/ceiling geometry. A passing PM-facing frame must show the box body, door edge, and handle clearly enough to explain the task. If the frame uses `displayColor` fallback rather than resolved native MDL materials, the diagnostics and PM note must say so explicitly.

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

- [ ] **Step 4: Run `lift2_eval_contract_probe`**

The probe must reset one task, dump observation schema, then send three action shapes:

- zero action;
- OpenPI/InternVLA-style relative `base_motion`;
- X-VLA-style absolute `base_motion`.

It must check:

- observation keys: `instruction`, `state.joints`, `state.gripper`, `state.base`, `state.ee_pose`, `video.overlook_camera_view`, `video.left_camera_view`, `video.right_camera_view`, `timestep`, `reset`, and `robot_id` if provided;
- action keys: `action` with shape `(16,)`, `base_motion` with shape `(3,)`, `control_type="joint_position"`, `is_rel`, and `base_is_rel`;
- reward/success fields from GenManip/EBench metric output, not LabUtopia expert controller `done`;
- logging fields: `run_id`, `worker_id`, `episode_id`, `seed`, result path, stdout/stderr, and exception stack when present.

- [ ] **Step 5: Write Lift2 readiness report**

`docs/labutopia_lab_poc/lift2_readiness.md` must contain:

- command outputs for `gmp submit`, `gmp eval`, `gmp status`, and `lift2_eval_contract_probe`;
- per-task rows for `level1_pick`, `level1_place`, and `level1_open_door`;
- columns `Reset`, `Step`, `Reachability`, `Camera Framing`, `Metric`, and `Finding`, using only `PASS`, `FAIL`, or `BLOCKED`;
- a clear statement that Franka/native acceptance-stage pass does not imply official baseline readiness unless Acceptance Stage 7 passes.

## Final Verification

Before claiming the native DryingBox lane is complete, run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc -q
python standalone_tools/labutopia_poc/validate_task_package.py
git diff --check
```

Then check the evidence manifest contains non-empty paths for audit, smoke, diagnostics, render frames, and Lift2 readiness if Acceptance Stage 7 was attempted.

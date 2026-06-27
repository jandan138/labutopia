# LabUtopia EBench P1 Asset Layout Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix LabUtopia P1 asset layout so the three Franka POC tasks have correct runtime coordinates, visible materials, and a valid drying-box handle hierarchy.

**Architecture:** Keep the change scoped to the LabUtopia POC overlay, task package metadata, static validator, and diagnostics. Normalize top-level runtime wrappers into the robot/table workspace, remove the invalid independent handle payload, and let existing GenManip articulation-part parsing expose `obj_DryingBox_01_handle` from the nested `/handle` prim. Require static render-validation metadata before runtime capture.

**Tech Stack:** Python, pytest, YAML/JSON task configs, USD ASCII wrapper generation, Isaac Sim runtime diagnostics.

---

## 2026-06-26 Native DryingBox Acceptance Stage Update

Multi-agent review split the work into two layers:

- This P1 plan closes render/layout and wrapper contract for the LabUtopia POC.
- Native complex `DryingBox_01` articulated acceptance is tracked in `docs/superpowers/plans/2026-06-26-labutopia-native-dryingbox-acceptance-stages.md`.

Important boundary: P1 render/layout closure does not prove official Lift2 baseline readiness. It also does not prove native `DryingBox_01` physics is complete until the native-only Isaac smoke, additive `USD` physics override, eval readback, and Lift2 contract checks pass.

Plain-language PM wording:

```text
P1 is about getting the scene into a readable EBench/GenManip runtime layout. The real DryingBox door still needs a separate native asset acceptance stage, because a USD file can be visible while its material, joint, collision, handle, camera, or Lift2 action contract is still wrong.
```

Do not use the older independent top-level handle payload as acceptance evidence for native DryingBox. The accepted direction is: keep the handle under native `DryingBox_01`, expose it as an articulation part, and bind `open_door` scoring to the door `RevoluteJoint`, not the button `PrismaticJoint` and not a surrogate-only handle displacement.

### Native Follow-Up Acceptance Stages

| Acceptance Stage | What it proves | Required evidence |
| --- | --- | --- |
| Asset Audit | The real LabUtopia `DryingBox_01` hierarchy, door joint, handle candidate, and articulation root are present. | `audit.json`, source USD hash, prim/joint/handle list, risk flags. |
| Native-only Isaac Smoke | The native asset can run physics steps without NaN/Inf or unexplained drift. | `smoke.json`, root/handle pose trace, joint position trace, PhysX warning log. |
| Native Wrapper | EBench can compose the whole box without moving the handle out of its hierarchy. | overlay `scene.usda`, manifest, no top-level handle payload, reference/material report. |
| Physics Override | Door physics is repaired additively and the metric reads the door DOF. | override manifest, body target checks, mass/inertia checks, door joint trace. |
| Eval Readback | GenManip/EBench can reset, render, step, and score native open-door evidence. | diagnostics JSON, reset frame, pre/post joint angle, handle pose, metric raw output. |
| Evidence Package | PM and reviewers can reproduce what is and is not claimed. | evidence manifest with commands, SHAs, env vars, run ids, hashes, visual QA. |
| Lift2 Contract Check | The lane matches official-baseline observation/action/reward/logging shape. | `gmp` logs, obs/action schema probe, relative/absolute base action probes. |

### Task 1: Lock P1 Overlay Contracts With Failing Tests

**Files:**
- Modify: `tests/labutopia_poc/test_build_asset_overlay.py`
- Modify: `tests/labutopia_poc/test_validate_task_package.py`
- Test: `tests/labutopia_poc/test_build_asset_overlay.py`
- Test: `tests/labutopia_poc/test_validate_task_package.py`

- [ ] **Step 1: Add overlay assertions**

Assert `scene.usda` does not contain `def Xform "obj_obj_DryingBox_01_handle" (` and does contain nested-handle contract metadata for `/World/labutopia_level1_poc/obj_obj_DryingBox_01/handle`.

- [ ] **Step 2: Add manifest assertions**

Assert generated and checked-in manifests contain `render_object_contracts`, workspace translations, display colors, expected bbox size ranges, and an articulation part mapping for `obj_DryingBox_01_handle`.

- [ ] **Step 3: Add task validation assertions**

Assert every Franka POC task has `labutopia_render_validation`; assert `level1_open_door` has an `existed_object` articulation contract for `obj_DryingBox_01`.

- [ ] **Step 4: Verify red**

Run:

```bash
python -m pytest tests/labutopia_poc/test_build_asset_overlay.py tests/labutopia_poc/test_validate_task_package.py -q
```

Expected: failures mention the still-present top-level handle payload and missing render-validation/articulation metadata.

### Task 2: Implement Overlay Normalization And Material Contracts

**Files:**
- Modify: `standalone_tools/labutopia_poc/build_asset_overlay.py`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`
- Test: `tests/labutopia_poc/test_build_asset_overlay.py`

- [ ] **Step 1: Update overlay constants**

Define runtime object specs for bottle, beaker, target platform, drying box, table, and handle articulation part. Include source path, runtime key, role, desired translation, expected bbox size range, and display color.

- [ ] **Step 2: Rewrite wrapper generation**

Generate top-level wrappers for the four task roots and table only. Add `xformOp:translate` overrides for task roots. Add `over` display-color opinions for task-visible mesh paths. Do not generate a top-level handle payload.

- [ ] **Step 3: Emit manifest contract**

Emit `render_object_contracts`, `articulation_part_paths`, and updated notes. Mirror the generated contract into the checked-in common manifest.

- [ ] **Step 4: Verify green**

Run:

```bash
python -m pytest tests/labutopia_poc/test_build_asset_overlay.py -q
```

Expected: all tests pass.

### Task 3: Implement Task Render Validation And Open Door Articulation

**Files:**
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_pick.yml`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_place.yml`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_pick.yml`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_place.yml`
- Modify: `configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml`
- Modify: `standalone_tools/labutopia_poc/validate_task_package.py`
- Test: `tests/labutopia_poc/test_validate_task_package.py`

- [ ] **Step 1: Add validator requirements**

Validate render metadata, required object lists, camera names, manifest object contracts, and open-door articulation config.

- [ ] **Step 2: Add Franka metadata**

Add `labutopia_render_validation` blocks to all three Franka tasks.

- [ ] **Step 3: Add open-door articulation**

Add `object_config.obj_DryingBox_01` with inline `articulation_info.part.handle = /handle` and switch the open-door runtime goal to `manip/default/check_joint_angle`.

- [ ] **Step 4: Keep Lift2 candidate structurally compatible**

Mirror task metadata where it is profile-independent and preserve the Lift2 robot/camera fields.

- [ ] **Step 5: Verify package**

Run:

```bash
python -m pytest tests/labutopia_poc/test_validate_task_package.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected: both pass.

### Task 4: Regenerate Overlay And Run Static Suite

**Files:**
- Modify generated overlay under `/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets`
- Test: `tests/labutopia_poc`

- [ ] **Step 1: Rebuild overlay**

Run:

```bash
python standalone_tools/labutopia_poc/build_asset_overlay.py
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
python -m pytest tests/labutopia_poc -q
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected: all focused tests and validator pass.

### Task 5: Runtime Render Diagnostics And Visual Review

**Files:**
- Modify: `docs/labutopia_lab_poc/render_visual_investigation_20260623.md`
- Create: `docs/labutopia_lab_poc/evidence_manifests/render_layout_closure_<timestamp>.json`
- Update only after acceptance: `docs/records/evidence/2026-06-22-labutopia-ebench-weekly-report/assets/*.jpg`

- [ ] **Step 1: Run eval-path diagnostics**

Use the tested Isaac conda environment and an isolated run id for `level1_pick`, `level1_place`, and `level1_open_door`.

- [ ] **Step 2: Review rendered frames**

Use visual review on the three generated eval-path frames. Reject frames that are black, nearly flat gray, missing required objects, or severely clipped.

- [ ] **Step 3: Record evidence**

Write an evidence manifest with source frame paths, sha256 hashes, frame stats, visual QA verdicts, and claim boundary.

- [ ] **Step 4: Request review**

Run code/static review after tests and runtime evidence are available. Fix Critical and Important findings before calling P1 complete.

- [ ] **Step 5: Hand off to native DryingBox acceptance stages**

After P1 render/layout evidence is accepted, continue with `docs/superpowers/plans/2026-06-26-labutopia-native-dryingbox-acceptance-stages.md`.

Expected boundary:

```text
P1 complete means task objects are readable in the eval path. It does not mean native DryingBox articulated physics, eval metrics, or official Lift2 baseline readiness are complete.
```

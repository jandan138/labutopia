# LabUtopia EBench P1 Asset Layout Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix LabUtopia P1 asset layout so the three Franka POC tasks have correct runtime coordinates, visible materials, and a valid drying-box handle hierarchy.

**Architecture:** Keep the change scoped to the LabUtopia POC overlay, task package metadata, static validator, and diagnostics. Normalize top-level runtime wrappers into the robot/table workspace, remove the invalid independent handle payload, and let existing GenManip articulation-part parsing expose `obj_DryingBox_01_handle` from the nested `/handle` prim. Require static render-validation metadata before runtime capture.

**Tech Stack:** Python, pytest, YAML/JSON task configs, USD ASCII wrapper generation, Isaac Sim runtime diagnostics.

---

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

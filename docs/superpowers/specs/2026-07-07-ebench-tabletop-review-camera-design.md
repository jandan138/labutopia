# EBench Tabletop Review Camera Design

Date: 2026-07-07

## Purpose

当前 S2-R1E 已经证明 `level1_open_door` 的 Expert Oracle Score 在 EBench 下能闭环：
official score、door joint readback、metric input / `succ_cnts` 和 `camera2.mp4` 都存在。但 `camera2`
是 evidence camera，不是产品展示相机；它的角度像从桌面下方/背侧看过去，PM 很难看清桌面布局和完整开门过程。

本设计补一层 **review cameras**：专门用于看桌面布局、正面把手和任务动作过程。它不替代现有 `camera2`，
也不参与当前 M3 score/readback claim。

给 PM 的一句话：现在“考试分数和物理证据”已经成立；下一步是给这个考试过程补一套看得懂的摄像机。

## Current State

EBench / GenManip 不是只能单相机。Lift2/simbox 已经有多相机配置：

```text
configs/cameras/fixed_camera_lift2_simbox.yml
  - overlook_camera
  - left_camera
  - right_camera
  - top_camera
```

并且 validator 里已经有 observation key 约定：

```python
"overlook_camera": "video.overlook_camera_view"
"top_camera": "video.top_camera_view"
```

但当前 Franka `level1_open_door` 用的是：

```text
configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
  domain_randomization.cameras.config_path: configs/cameras/labutopia_franka_poc_open_door.yml
  labutopia_render_validation.primary_camera: camera2
```

`camera2` 当前配置为：

```yaml
position: [0.62, 1.25, 1.35]
orientation: [0.87184, -0.4898, 0.0, 0.0]
resolution: [512, 512]
task_view: level1_open_door
```

这个相机能产出 evidence artifact，但它不是 tabletop / front-view review camera。

## Recommended Design

### Component 1: Preserve Existing Evidence Camera

保留 `camera2` 的现有职责：

- 继续作为 `primary_camera` / `primary_evidence_camera`
- 继续产出 `video.camera2_view`
- 继续服务 S2/M3 score/readback artifact presence
- 不把 PM 展示视角问题反向解释成 score 路线失败

Rationale: S2-R1E 已经用 `camera2` 产出了可签收的 score/readback evidence。直接替换它会让后续 run 难以和当前证据比较。

### Component 2: Add Review Camera Config

新增或扩展 Franka open-door camera config，建议命名：

```text
configs/cameras/labutopia_franka_poc_open_door_review.yml
```

至少包含：

```yaml
tabletop_camera:
  purpose: desktop_layout_review
  observation_key: video.tabletop_camera_view
  expected_view: full table, robot base, DryingBox, handle side context

front_camera:
  purpose: product_front_review
  observation_key: video.front_camera_view
  expected_view: DryingBox front face and handle clearly visible

side_camera:
  purpose: motion_process_review
  observation_key: video.side_camera_view
  expected_view: robot arm approach, handle contact, door opening trajectory
```

`camera2` remains in the same config:

```yaml
camera2:
  purpose: scoring_evidence_camera
  observation_key: video.camera2_view
```

### Component 3: Task Contract Extension

Extend `level1_open_door.yml` with a review-only camera contract:

```yaml
labutopia_review_cameras:
  enabled: true
  camera_config: configs/cameras/labutopia_franka_poc_open_door_review.yml
  required_review_views:
    - tabletop_camera
    - front_camera
    - side_camera
  scoring_camera_unchanged: camera2
```

This must be separate from `generation_config.goal` and score metric config. Missing review cameras should fail visual review, not the EBench score-chain contract.

### Component 4: Video Artifact Export

For a review run, export videos with human-readable names:

```text
01_tabletop_layout.mp4
02_front_task_completion.mp4
03_side_task_completion.mp4
04_camera2_scoring_evidence.mp4
```

Each artifact should have a small JSON manifest:

```json
{
  "run_id": "...",
  "camera_name": "tabletop_camera",
  "purpose": "desktop_layout_review",
  "duration_seconds": 19.3,
  "frame_count": 579,
  "resolution": [1280, 720],
  "claim_boundary": "visual review only; not a score artifact"
}
```

### Component 5: Review Acceptance

`tabletop_camera` pass criteria:

- Table surface is not clipped by the image boundary.
- DryingBox and robot base are both visible.
- Object placement can be understood in the first 3-5 seconds.
- Camera is above or oblique-above the table, not under-table or behind-table.

`front_camera` pass criteria:

- DryingBox front face and handle are clearly visible.
- Door opening direction is visible.
- Handle is not hidden behind the box body.

`side_camera` pass criteria:

- Robot approach and gripper-handle interaction are visible.
- Door opening motion is understandable through time.

`camera2` pass criteria remain evidence-oriented:

- Artifact exists.
- Terminal frame can be stored.
- It does not need to be product-grade.

## Alternatives Considered

### Alternative A: Replace `camera2` With a Better View

Rejected. It would mix product review with scoring evidence and make current S2-R1E evidence less comparable with future runs.

### Alternative B: Reuse Lift2 `overlook_camera` / `top_camera` Directly

Partially useful as a pattern, not a direct copy. Lift2 cameras are attached to Lift2 prim paths such as `/lift2/.../Camera`; Franka POC needs world/table-relative cameras around `/World/labutopia_level1_poc/obj_table` and DryingBox.

### Alternative C: Add Only One Top Camera

Too narrow. A top camera explains layout but usually does not show the DryingBox handle or door opening direction well. For PM review we need at least tabletop + front, with side as the process view.

## Testing Plan

No live score claim should be made from config changes alone. Validation should proceed in this order:

1. Static config validation:
   - camera names exist
   - observation keys are unique
   - `camera2` remains the scoring camera
   - review cameras are marked review-only

2. Render smoke:
   - one reset-only capture
   - export first frame from each review camera
   - visual review confirms tabletop/front/side framing

3. Full replay review:
   - rerun the already score-capable action source only after static and reset render checks pass
   - export all review videos plus existing `camera2`
   - score/readback evidence remains separate from review-video manifest

## Stop Lines

- If adding review cameras changes score, metric input, action source, or `camera2` evidence behavior, stop and revert the review-camera path.
- If tabletop camera cannot show table + DryingBox + robot base in one frame, retune camera pose before running full replay.
- If front camera cannot show handle clearly, do not call it product/front-view evidence.
- If review videos exist but score/readback artifacts are missing, classify as score/evidence failure, not visual success.
- If score/readback artifacts exist but review videos are visually poor, classify as visual-review failure, not score failure.

## Non-Claims

This design does not claim:

- M4 small-sample stability
- Lift2 official baseline completion
- policy score
- official leaderboard readiness
- visual/material parity completion
- arbitrary asset camera generalization

It only defines how to add PM-readable tabletop/front/side review videos without disturbing the current EBench score evidence chain.

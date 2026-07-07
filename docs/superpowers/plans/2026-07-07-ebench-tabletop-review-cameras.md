# EBench Tabletop Review Cameras Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Keep the scoring camera unchanged. Review cameras are product/debug evidence, not metric evidence.

**Goal:** Add a dedicated tabletop/product-review camera lane for `labutopia_lab_poc/franka_poc/level1_open_door`, so product review can clearly see desktop layout, door front/handle, and task motion while preserving the existing EBench scoring/readback camera.

**Architecture:** The existing `camera2` remains the canonical scoring/evidence camera. A new review camera config declares `tabletop_camera`, `front_camera`, and `side_camera` with explicit `review_only: true` metadata and observation keys. The task config declares this review contract separately from metric semantics. Validation checks that review views exist and that `camera2` has not drifted.

**Tech Stack:** YAML camera/task configs, `standalone_tools/labutopia_poc/validate_task_package.py`, pytest, Isaac Sim reset-only render diagnostics, visual review.

**2026-07-07 checkpoint:** Static contract, runner override plumbing, reset-only render smoke, full replay MP4 export, and LabUtopia PM evidence have been implemented. The accepted reset smoke is `run_id=eos2_review_camera_reset_smoke_20260707_104047`. The accepted full replay is `run_id=eos2_review_camera_full_replay_20260707_111621`. Independent visual QA returned PASS for `tabletop_camera`, `front_camera`, and `side_camera`; it returned WARN for `camera2` only because `camera2` is not product-friendly. That WARN is accepted because `camera2` remains the unchanged canonical scoring/readback camera, not the product front view.

**Current claim boundary:** This checkpoint proves review-camera framing at reset and full replay review media export. It does not replace canonical score evidence, and it does not prove policy score, official leaderboard score, arbitrary asset-pipeline completion, or full visual/material parity.

---

### Task 1: Add Static Contract Red Tests

**Files:**
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_validate_task_package.py`

**Add tests:**

```python
def test_open_door_review_camera_config_declares_tabletop_front_side_views() -> None:
    config_path = REPO_ROOT / "configs/cameras/labutopia_franka_poc_open_door_review.yml"
    camera_config = yaml.safe_load(config_path.read_text())
    canonical_config = yaml.safe_load(
        (REPO_ROOT / "configs/cameras/labutopia_franka_poc_open_door.yml").read_text()
    )

    assert camera_config["camera2"] == canonical_config["camera2"]

    expected_review_cameras = {
        "tabletop_camera": "video.tabletop_camera_view",
        "front_camera": "video.front_camera_view",
        "side_camera": "video.side_camera_view",
    }
    for camera_name, observation_key in expected_review_cameras.items():
        camera = camera_config[camera_name]
        assert camera["exists"] is False
        assert camera["camera_axes"] == "usd"
        assert camera["resolution"] == [1280, 720]
        assert camera["image_type"] == "rgb"
        assert camera["review_only"] is True
        assert camera["observation_key"] == observation_key
        assert camera["with_distance"] is False
        assert camera["with_semantic"] is False
        assert camera["with_bbox2d"] is False
        assert camera["with_bbox3d"] is False
        assert camera["with_motion_vector"] is False


def test_open_door_task_declares_review_camera_contract() -> None:
    task_config_path = (
        REPO_ROOT
        / "configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml"
    )
    task_config = yaml.safe_load(task_config_path.read_text())["evaluation_configs"][0]

    review_contract = task_config["labutopia_review_cameras"]
    assert review_contract["enabled"] is True
    assert review_contract["camera_config"] == "configs/cameras/labutopia_franka_poc_open_door_review.yml"
    assert review_contract["scoring_camera"] == "camera2"
    assert review_contract["scoring_camera_observation_key"] == "video.camera2_view"
    assert review_contract["review_only"] is True
    assert review_contract["required_views"] == [
        "tabletop_camera",
        "front_camera",
        "side_camera",
    ]
    assert review_contract["output_artifacts"] == {
        "tabletop_camera": "video.tabletop_camera_view",
        "front_camera": "video.front_camera_view",
        "side_camera": "video.side_camera_view",
    }
```

**Run and confirm red:**

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_validate_task_package.py \
  -k "open_door_review_camera_config_declares_tabletop_front_side_views or open_door_task_declares_review_camera_contract"
```

**Expected failure before implementation:** missing review camera config and missing `labutopia_review_cameras` task contract.

---

### Task 2: Add Review Camera Config

**Files:**
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/cameras/labutopia_franka_poc_open_door_review.yml`

**Create the file with scoring camera copied exactly from the current open-door camera config plus review-only cameras:**

```yaml
camera1:
  name: camera_1
  exists: false
  prim_path: /LabUtopiaOpenDoorCamera1
  position: [2.0, 0.0, 2.0]
  orientation: [0.61237, 0.35355, 0.35355, 0.61237]
  camera_axes: usd
  resolution: [256, 256]
  image_type: rgb
  with_distance: false
  with_semantic: false
  with_bbox2d: false
  with_bbox3d: false
  with_motion_vector: false

camera2:
  name: camera_2
  exists: false
  prim_path: /LabUtopiaOpenDoorCamera2
  position: [0.62, 1.25, 1.35]
  orientation: [0.87184, -0.4898, 0.0, 0.0]
  camera_axes: usd
  resolution: [512, 512]
  focal_length: 4.0
  horizontal_aperture: 10.0
  image_type: rgb
  task_view: level1_open_door
  with_distance: false
  with_semantic: false
  with_bbox2d: false
  with_bbox3d: false
  with_motion_vector: false

tabletop_camera:
  name: tabletop_camera
  exists: false
  prim_path: /LabUtopiaOpenDoorTabletopReviewCamera
  position: [0.45, 0.02, 3.05]
  orientation: [1.0, 0.0, 0.0, 0.0]
  camera_axes: usd
  resolution: [1280, 720]
  focal_length: 5.0
  horizontal_aperture: 14.0
  image_type: rgb
  task_view: level1_open_door_tabletop_layout
  purpose: desktop_layout_review
  review_only: true
  observation_key: video.tabletop_camera_view
  with_distance: false
  with_semantic: false
  with_bbox2d: false
  with_bbox3d: false
  with_motion_vector: false

front_camera:
  name: front_camera
  exists: false
  prim_path: /LabUtopiaOpenDoorFrontReviewCamera
  position: [0.06, 0.56, 1.2]
  orientation: [-0.33975225, -0.28602009, 0.57702305, 0.68542346]
  camera_axes: usd
  resolution: [1280, 720]
  focal_length: 6.0
  horizontal_aperture: 10.0
  image_type: rgb
  task_view: level1_open_door_front_handle
  purpose: product_front_handle_review
  review_only: true
  observation_key: video.front_camera_view
  with_distance: false
  with_semantic: false
  with_bbox2d: false
  with_bbox3d: false
  with_motion_vector: false

side_camera:
  name: side_camera
  exists: false
  prim_path: /LabUtopiaOpenDoorSideReviewCamera
  position: [0.15, 0.0, 2.35]
  orientation: [1.0, 0.0, 0.0, 0.0]
  camera_axes: usd
  resolution: [1280, 720]
  focal_length: 8.0
  horizontal_aperture: 12.0
  image_type: rgb
  task_view: level1_open_door_motion_side
  purpose: door_motion_side_review
  review_only: true
  observation_key: video.side_camera_view
  with_distance: false
  with_semantic: false
  with_bbox2d: false
  with_bbox3d: false
  with_motion_vector: false
```

**Important:** These are the post-retune accepted reset-smoke poses. The first pass failed visual review because `side_camera` showed mostly a wall/plane and `tabletop_camera` was not truly overhead. The accepted `104047` reset smoke is the first visual acceptance point; do not claim full review-video closure from static YAML alone.

---

### Task 3: Declare Review Contract in Task Config

**Files:**
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`

**Add a separate review camera contract. Keep metric/scoring fields unchanged.**

Insert this block under `evaluation_configs[0]`, at the same indentation level as `labutopia_render_validation` and `env_vars`.

```yaml
labutopia_review_cameras:
  enabled: true
  camera_config: configs/cameras/labutopia_franka_poc_open_door_review.yml
  scoring_camera: camera2
  scoring_camera_observation_key: video.camera2_view
  review_only: true
  required_views:
    - tabletop_camera
    - front_camera
    - side_camera
  output_artifacts:
    tabletop_camera: video.tabletop_camera_view
    front_camera: video.front_camera_view
    side_camera: video.side_camera_view
```

**Do not change yet:**

```yaml
domain_randomization:
  cameras:
    config_path: configs/cameras/labutopia_franka_poc_open_door.yml
```

The review contract points to an additional camera config. The scoring path keeps using the existing camera config until render/export wiring is explicitly tested.

---

### Task 4: Extend Validator for Review Camera Contract

**Files:**
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/validate_task_package.py`

**Add constants near existing camera constants:**

```python
FRANKA_OPEN_DOOR_REVIEW_CAMERA_CONFIG = "configs/cameras/labutopia_franka_poc_open_door_review.yml"
FRANKA_OPEN_DOOR_REVIEW_CAMERA_KEYS = {
    "tabletop_camera": "video.tabletop_camera_view",
    "front_camera": "video.front_camera_view",
    "side_camera": "video.side_camera_view",
}
```

**Add validation helper using the repository's `_assert(...)` validator style:**

```python
def _validate_labutopia_review_camera_contract(cfg: dict[str, Any], path: Path) -> None:
    task_name = str(cfg.get("task_name"))
    leaf_name = _task_leaf_name(task_name)
    if path.parent.name != "franka_poc" or leaf_name != "level1_open_door":
        _assert(
            "labutopia_review_cameras" not in cfg,
            f"{path}: labutopia_review_cameras is currently scoped to level1_open_door",
        )
        return

    contract = cfg.get("labutopia_review_cameras")
    _assert(isinstance(contract, dict), f"{path}: missing labutopia_review_cameras")
    _assert(contract.get("enabled") is True, f"{path}: labutopia_review_cameras.enabled must be true")
    _assert(contract.get("review_only") is True, f"{path}: labutopia_review_cameras.review_only must be true")
    _assert(contract.get("camera_config") == FRANKA_OPEN_DOOR_REVIEW_CAMERA_CONFIG, f"{path}: review camera config mismatch")
    _assert(contract.get("scoring_camera") == "camera2", f"{path}: scoring camera must remain camera2")
    _assert(contract.get("scoring_camera_observation_key") == "video.camera2_view", f"{path}: scoring observation key mismatch")

    expected_views = list(FRANKA_OPEN_DOOR_REVIEW_CAMERA_KEYS)
    _assert(contract.get("required_views") == expected_views, f"{path}: required review views mismatch")
    _assert(contract.get("output_artifacts") == FRANKA_OPEN_DOOR_REVIEW_CAMERA_KEYS, f"{path}: output_artifacts mismatch")

    review_config_path = ROOT / FRANKA_OPEN_DOOR_REVIEW_CAMERA_CONFIG
    review_config = _load_yaml(review_config_path)
    canonical_camera2 = _load_yaml(
        ROOT / EXPECTED_FRANKA_TASK_CAMERA_CONFIGS["level1_open_door"]
    )["camera2"]
    _assert(
        review_config.get("camera2") == canonical_camera2,
        f"{review_config_path}:camera2 must match canonical open-door camera2 exactly",
    )
    for camera_name, observation_key in FRANKA_OPEN_DOOR_REVIEW_CAMERA_KEYS.items():
        camera = review_config.get(camera_name)
        _assert(isinstance(camera, dict), f"{review_config_path}: missing {camera_name}")
        missing = CAMERA_CLEANUP_FLAGS - set(camera)
        _assert(not missing, f"{review_config_path}:{camera_name}: missing cleanup flags {missing}")
        _assert(camera.get("exists") is False, f"{review_config_path}:{camera_name}: exists must be false")
        _assert(camera.get("camera_axes") == "usd", f"{review_config_path}:{camera_name}: camera_axes must be usd")
        _assert(camera.get("resolution") == [1280, 720], f"{review_config_path}:{camera_name}: resolution must be [1280, 720]")
        _assert(camera.get("review_only") is True, f"{review_config_path}:{camera_name}: review_only must be true")
        _assert(camera.get("observation_key") == observation_key, f"{review_config_path}:{camera_name}: observation_key mismatch")
```

**Call helper from `_validate_runtime_task(...)` after `_validate_render_validation(...)`.**

**Run tests:**

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
/usr/bin/python -m pytest -q tests/labutopia_poc/test_validate_task_package.py \
  -k "review_camera or open_door_evidence_camera or labutopia_franka_camera"
python standalone_tools/labutopia_poc/validate_task_package.py
```

**Known full-validator caveat:** If the full validator stops before task runtime validation on an unrelated asset-manifest mismatch, run the targeted proof:

```bash
/usr/bin/python - <<'PY'
from standalone_tools.labutopia_poc import validate_task_package as v
v._validate_camera_configs()
v._validate_runtime_task(v.PACKAGE_ROOT / "franka_poc" / "level1_open_door.yml")
print("targeted review camera runtime validation OK")
PY
```

---

### Task 5: Add Review Camera Export Probe

**Files:**
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/capture_eval_render_diagnostics.py`
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_render_diagnostics_contract.py`

**Behavior:** The reset-only diagnostic already supports `--camera-config-override`. The implementation must use `labutopia_review_cameras.camera_config` as the contract source and pass it through that existing override path. It must instantiate the review cameras and save first-frame PNGs under the existing diagnostic layout:

```text
readback_after_get_eval_camera_data/tabletop_camera/00000.png
readback_after_get_eval_camera_data/front_camera/00000.png
readback_after_get_eval_camera_data/side_camera/00000.png
readback_after_get_eval_camera_data/camera2/00000.png
recorder_png/tabletop_camera/00000.png
recorder_png/front_camera/00000.png
recorder_png/side_camera/00000.png
recorder_png/camera2/00000.png
```

**Accepted reset-smoke command pattern:**

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
ENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
PY=$ENV/bin/python
RUN_ID=eos2_review_camera_reset_smoke_$(date -u +%Y%m%d_%H%M%S)
OUT_DIR=/tmp/labutopia_open_door_review_camera_smoke_${RUN_ID}
CUDA11_LIB=/isaac-sim/exts/omni.isaac.ml_archive/pip_prebundle/nvidia/cuda_runtime/lib
ISAAC_CUDA_LIB=$ENV/lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin
ISAAC_GPU_DEPS=$ENV/lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps
TORCH_LIB=$ENV/lib/python3.10/site-packages/torch/lib
PYTHONNOUSERSITE=1 PATH=$ENV/bin:$PATH \
PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback \
LD_LIBRARY_PATH=$ENV/lib:$CUDA11_LIB:$ISAAC_CUDA_LIB:$ISAAC_GPU_DEPS:$TORCH_LIB:${LD_LIBRARY_PATH:-} \
"$PY" standalone_tools/labutopia_poc/capture_eval_render_diagnostics.py \
  --config ebench/labutopia_lab_poc/franka_poc \
  --task level1_open_door \
  --run-id "$RUN_ID" \
  --output-dir "$OUT_DIR" \
  --camera-config-override configs/cameras/labutopia_franka_poc_open_door_review.yml \
  --skip-native-evidence
```

**Visual acceptance criteria:**
- `tabletop_camera.png` shows table/object layout from above without appearing upside down to a reviewer.
- `front_camera.png` clearly shows the handle-facing/front side of the drying box.
- `side_camera.png` shows door swing direction and robot interaction clearance.
- `camera2.png` remains the scoring/evidence view and is not judged as the product-review view.

**Accepted result:** `eos2_review_camera_reset_smoke_20260707_104047` produced visible frames for `camera2`, `front_camera`, `side_camera`, and `tabletop_camera`. Independent visual QA returned:

| Camera | Verdict | Meaning |
| --- | --- | --- |
| `tabletop_camera` | PASS | Clear overhead tabletop layout. |
| `front_camera` | PASS | Product-front/handle/control-panel view is clear. |
| `side_camera` | PASS | Robot, gripper, box, and approach spacing are visible. |
| `camera2` | WARN | Scene content is visible, but it is not product-friendly. Keep unchanged because it is scoring/readback. |

---

### Task 6: Run Full Replay Only After Reset Smoke Passes

**Files:**
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/score_capable_oracle_runner.py`

**Required before running:** Task 5 must produce visually accepted reset-only PNGs. This requirement is now satisfied by `eos2_review_camera_reset_smoke_20260707_104047`.

**Implementation:** Add runner support for:

```text
--camera-config-override configs/cameras/labutopia_franka_poc_open_door_review.yml
```

The runner must not edit the canonical task YAML in place. It should create a generated run-local config, change only `evaluation_configs[0].domain_randomization.cameras.config_path`, and pass that generated config path to `start_job`. For live server runs, the generated config must live under `configs/tasks` and `start_job` must receive the path relative to that task root; otherwise GenManip's path guard rejects the job. Because this is a review-media run, not the canonical score run, the summary must mark the score claim as non-canonical and keep the S2-R1E canonical score evidence as the source of truth. The summary must record:

```json
{
  "camera_config_override": {
    "previous_config_path": "configs/cameras/labutopia_franka_poc_open_door.yml",
    "override_config_path": "configs/cameras/labutopia_franka_poc_open_door_review.yml",
    "generated_config_path": "configs/tasks/ebench/_generated_review_configs/<run_id>/level1_open_door.review_cameras.yml",
    "start_job_config_path": "ebench/_generated_review_configs/<run_id>/level1_open_door.review_cameras.yml"
  },
  "review_media_run": true,
  "canonical_score_claim_allowed": false
}
```

**Run command pattern:**

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
python standalone_tools/labutopia_poc/score_capable_oracle_runner.py \
  --run-id eos2_review_camera_replay_$(date -u +%Y%m%d_%H%M%S) \
  --config-path configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml \
  --action-source /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706/bridged_action_source_freeze_validation/action_source.jsonl \
  --output-dir /tmp/labutopia_open_door_review_camera_full_replay_${RUN_ID} \
  --result-base-dir saved/eval_results \
  --expected-action-dim 9 \
  --step-chunk-render-mode always \
  --trace-final-obs \
  --camera-config-override configs/cameras/labutopia_franka_poc_open_door_review.yml \
  --generated-config-dir configs/tasks/ebench/_generated_review_configs/${RUN_ID}
```

**Accepted review artifacts:**

```text
saved/eval_results/ebench/eos2_review_camera_full_replay_20260707_111621/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/tabletop_camera.mp4
saved/eval_results/ebench/eos2_review_camera_full_replay_20260707_111621/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/front_camera.mp4
saved/eval_results/ebench/eos2_review_camera_full_replay_20260707_111621/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/side_camera.mp4
saved/eval_results/ebench/eos2_review_camera_full_replay_20260707_111621/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/camera2.mp4
```

The first live attempt exposed a path-boundary bug: `--camera-config-override` originally generated the task YAML under `/tmp/.../generated_configs`, but the live server only accepts task configs under `configs/tasks`. The second attempt wrote under `configs/tasks/_generated_review_configs`, but the server then classified the benchmark id as `_generated_review_configs`. The accepted run writes under `configs/tasks/ebench/_generated_review_configs/<run_id>` and passes `ebench/_generated_review_configs/<run_id>/level1_open_door.review_cameras.yml` to `start_job`.

**Current status:** Full replay MP4 lane is complete. `eos2_review_camera_full_replay_20260707_111621` produced four non-empty MP4s, each `579` frames / `19.3s`; runner summary reports `review_media_run=true`, `score_claim_allowed=false`, `canonical_score_claim_allowed=false`, `score=1.0`, terminal door angle `41.715865deg`, and `succ_cnts=59`. Independent visual QA returned overall WARN only because unchanged `camera2` is not product-facing; `tabletop_camera`, `front_camera`, and `side_camera` are PASS.

---

### Task 7: Update LabUtopia Docs and Evidence Manifest

**Files:**
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/`
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/aan_consumer_handoff.md`
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/README.md`

**Write down in product-readable language:**
- Old `camera2` video was not upside down; it was an awkward scoring/debug camera.
- The new tabletop/front/side cameras are review-only and do not change score.
- The front view is the handle-facing view and is the only one that should be called product front.
- Completion claim requires reset-only visual smoke plus full replay review videos.

**Copy review media into:**

```text
docs/labutopia_lab_poc/review_media/eos2_review_cameras/
```

**Completed docs/media evidence:**

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_review_camera_reset_smoke_20260707_104047.json
docs/labutopia_lab_poc/review_media/eos2_review_cameras/tabletop_camera.png
docs/labutopia_lab_poc/review_media/eos2_review_cameras/front_camera.png
docs/labutopia_lab_poc/review_media/eos2_review_cameras/side_camera.png
docs/labutopia_lab_poc/review_media/eos2_review_cameras/camera2_scoring.png
reports/2026-06-15-labutopia-weekly/assets/eos2-review-tabletop-camera.png
reports/2026-06-15-labutopia-weekly/assets/eos2-review-front-camera.png
reports/2026-06-15-labutopia-weekly/assets/eos2-review-side-camera.png
reports/2026-06-15-labutopia-weekly/assets/eos2-review-camera2-scoring.png
```

**Run:**

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
git diff --check -- docs/superpowers/plans/2026-07-07-ebench-tabletop-review-cameras.md \
  docs/labutopia_lab_poc docs/README.md
```

---

### Task 8: Commit in Small Units

**Commit 1:** GenManip review camera static contract and config.

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
git add configs/cameras/labutopia_franka_poc_open_door_review.yml \
  configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml \
  standalone_tools/labutopia_poc/validate_task_package.py \
  tests/labutopia_poc/test_validate_task_package.py
git commit -m "feat: add labutopia open door review cameras"
```

**Commit 2:** GenManip render/export support after smoke passes.

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
git add standalone_tools/labutopia_poc/capture_eval_render_diagnostics.py \
  standalone_tools/labutopia_poc/score_capable_oracle_runner.py \
  tests/labutopia_poc/test_capture_eval_render_diagnostics.py
git commit -m "feat: export labutopia review camera evidence"
```

**Commit 3:** LabUtopia docs/media evidence.

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
git add docs/superpowers/plans/2026-07-07-ebench-tabletop-review-cameras.md \
  docs/labutopia_lab_poc/evidence_manifests \
  docs/labutopia_lab_poc/review_media/eos2_review_cameras \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/README.md
git commit -m "docs: add open door review camera evidence"
```

**Do not stage unrelated dirty files.**

---

### Completion Criteria

- Static contract tests pass.
- `validate_task_package.py` accepts the open-door task and catches missing/wrong review cameras.
- Reset-only review camera PNGs exist and pass visual review.
- Full replay review MP4s exist, and `tabletop_camera` / `front_camera` / `side_camera` pass visual review. **Complete via `eos2_review_camera_full_replay_20260707_111621`; overall WARN is accepted because only unchanged `camera2` is non-product-friendly.**
- Docs explain old camera issue and new review camera lane in product-readable Chinese.
- Scoring camera `camera2` remains unchanged and is clearly labeled as scoring/evidence, not product front.

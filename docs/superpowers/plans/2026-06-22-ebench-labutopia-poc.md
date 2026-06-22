# LabUtopia EBench/GenManip POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable GenManip/EBench-style POC for LabUtopia `level1_pick`, `level1_place`, and `level1_open_door`, with a Franka smoke profile and a lift2/R5a readiness profile.

**Architecture:** Implement this as a GenManip task package plus an external asset overlay. LabUtopia remains the source of truth for task semantics and assets; GenManip owns runtime configs, custom metrics, validation scripts, and EvalClient smoke checks. The Franka profile proves `reset -> step -> score`; the lift2 profile is a separate contract-readiness path for official EBench baselines.

**Tech Stack:** Python 3, pytest, Pydantic, NumPy, GenManip metric registry, GenManip `SceneConfig`, USD/USDA asset overlay, `gmp submit/eval`, LabUtopia and GenManip local repositories.

---

## Repository Roots

Use these absolute paths throughout the implementation:

```text
LABUTOPIA_ROOT=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia
GENMANIP_ROOT=/cpfs/shared/simulation/zhuzihou/dev/GenManip
ASSET_OVERLAY_ROOT=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets
```

Do not edit the downloaded `_datasets/EBench-Assets` tree in place.

## File Structure

Create or modify these files in `GenManip`:

```text
genmanip/extensions/metrics/labutopia/__init__.py
genmanip/extensions/metrics/labutopia/object_metrics.py
tests/labutopia_poc/test_labutopia_metrics.py
standalone_tools/labutopia_poc/build_asset_overlay.py
standalone_tools/labutopia_poc/validate_task_package.py
configs/cameras/labutopia_franka_poc.yml
configs/tasks/ebench/labutopia_lab_poc/labutopia_lab_poc.json
configs/tasks/ebench/labutopia_lab_poc/common/task_semantics.yml
configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json
configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json
configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_pick.yml
configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_place.yml
configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json
configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_pick.yml
configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_place.yml
configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml
docs/labutopia_lab_poc/franka_smoke.md
docs/labutopia_lab_poc/lift2_readiness.md
```

Create or modify this file in `LabUtopia`:

```text
docs/ebench-integration/labutopia-level1-poc-runbook.md
```

The GenManip `common/` files are source material for humans and helper scripts. Runtime submission must use the concrete `franka_poc/*.yml` and `lift2_candidate/*.yml` files.

---

### Task 1: Add Metric Unit Tests

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/tests/labutopia_poc/test_labutopia_metrics.py`

- [ ] **Step 1: Create the failing metric tests**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/tests/labutopia_poc/test_labutopia_metrics.py`:

```python
import numpy as np

import genmanip.extensions.metrics  # noqa: F401
from genmanip.core.metrics.utils import MetricFactory


class FakeObject:
    def __init__(self, position):
        self.position = np.array(position, dtype=float)

    def get_world_pose(self):
        return self.position, np.array([1.0, 0.0, 0.0, 0.0], dtype=float)


class FakeScene:
    def __init__(self):
        self.object_list = {}
        self.articulation_list = {}


def step_metric(metric, scene, times=1):
    for _ in range(times):
        metric.update(scene)
    return metric.status


def test_object_height_delta_uses_initial_pose_and_strict_threshold():
    scene = FakeScene()
    scene.object_list["obj_conical_bottle02"] = FakeObject([0.0, 0.0, 0.80])
    metric = MetricFactory.build(
        "manip/labutopia/object_height_delta",
        skip_steps=1,
        succ_cnts=0,
        sub_goal_setting={
            "obj_uid": "obj_conical_bottle02",
            "axis": "z",
            "min_delta": 0.10,
        },
    )

    assert step_metric(metric, scene) is False

    scene.object_list["obj_conical_bottle02"].position = np.array([0.0, 0.0, 0.90])
    assert step_metric(metric, scene) is False

    scene.object_list["obj_conical_bottle02"].position = np.array([0.0, 0.0, 0.901])
    assert step_metric(metric, scene) is True


def test_object_height_delta_requires_consecutive_success_frames():
    scene = FakeScene()
    scene.object_list["obj_conical_bottle02"] = FakeObject([0.0, 0.0, 0.80])
    metric = MetricFactory.build(
        "manip/labutopia/object_height_delta",
        skip_steps=1,
        succ_cnts=2,
        sub_goal_setting={
            "obj_uid": "obj_conical_bottle02",
            "axis": "z",
            "min_delta": 0.10,
        },
    )

    assert step_metric(metric, scene) is False

    scene.object_list["obj_conical_bottle02"].position = np.array([0.0, 0.0, 0.92])
    assert step_metric(metric, scene) is False
    assert step_metric(metric, scene) is False
    assert step_metric(metric, scene) is True


def test_object_at_target_uses_radial_xy_and_initial_z():
    scene = FakeScene()
    scene.object_list["obj_beaker2"] = FakeObject([0.20, 0.20, 0.84])
    scene.object_list["obj_target_plat"] = FakeObject([0.30, 0.30, 0.776])
    metric = MetricFactory.build(
        "manip/labutopia/object_at_target",
        skip_steps=1,
        succ_cnts=0,
        sub_goal_setting={
            "obj_uid": "obj_beaker2",
            "target_uid": "obj_target_plat",
            "xy_radius": 0.05,
            "z_tolerance": 0.05,
        },
    )

    assert step_metric(metric, scene) is False

    scene.object_list["obj_beaker2"].position = np.array([0.35, 0.30, 0.84])
    assert step_metric(metric, scene) is False

    scene.object_list["obj_beaker2"].position = np.array([0.349, 0.30, 0.84])
    assert step_metric(metric, scene) is True

    scene.object_list["obj_beaker2"].position = np.array([0.30, 0.30, 0.90])
    assert step_metric(metric, scene) is False


def test_handle_displacement_uses_initial_pose_and_distance_threshold():
    scene = FakeScene()
    scene.object_list["obj_DryingBox_01_handle"] = FakeObject([0.0, 0.0, 0.0])
    metric = MetricFactory.build(
        "manip/labutopia/handle_displacement",
        skip_steps=1,
        succ_cnts=0,
        sub_goal_setting={
            "obj_uid": "obj_DryingBox_01_handle",
            "min_distance": 0.12,
        },
    )

    assert step_metric(metric, scene) is False

    scene.object_list["obj_DryingBox_01_handle"].position = np.array([0.12, 0.0, 0.0])
    assert step_metric(metric, scene) is False

    scene.object_list["obj_DryingBox_01_handle"].position = np.array([0.121, 0.0, 0.0])
    assert step_metric(metric, scene) is True
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_labutopia_metrics.py -q
```

Expected result:

```text
KeyError: 'manip/labutopia/object_height_delta is not registered'
```

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git add tests/labutopia_poc/test_labutopia_metrics.py
git commit -m "test: add labutopia poc metric tests"
```

Expected result: a commit that only adds the test file.

---

### Task 2: Implement LabUtopia Metrics

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/genmanip/extensions/metrics/labutopia/__init__.py`
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/genmanip/extensions/metrics/labutopia/object_metrics.py`
- Test: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/tests/labutopia_poc/test_labutopia_metrics.py`

- [ ] **Step 1: Add the package init**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/genmanip/extensions/metrics/labutopia/__init__.py`:

```python
"""LabUtopia metric extensions for GenManip evaluation."""
```

- [ ] **Step 2: Implement object metrics**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/genmanip/extensions/metrics/labutopia/object_metrics.py`:

```python
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator

from genmanip.core.metrics.base import BaseMetric
from genmanip.core.metrics.utils import MetricFactory


AxisName = Literal["x", "y", "z"]


def _position(scene, obj_uid: str) -> np.ndarray:
    if obj_uid not in scene.object_list:
        raise KeyError(f"Object '{obj_uid}' not found in scene.object_list")
    pose = scene.object_list[obj_uid].get_world_pose()
    return np.asarray(pose[0], dtype=float)


class ObjectHeightDeltaConfig(BaseModel):
    obj_uid: str = Field(..., description="Object UID in scene.object_list")
    axis: AxisName = Field(default="z", description="Axis used for displacement")
    min_delta: float = Field(..., description="Strict minimum displacement in meters")

    @field_validator("min_delta")
    @classmethod
    def validate_min_delta(cls, value):
        if value <= 0:
            raise ValueError("min_delta must be positive")
        return value


@MetricFactory.register("manip/labutopia/object_height_delta")
class ObjectHeightDelta(BaseMetric):
    def __init__(
        self,
        skip_steps: int = 1,
        succ_cnts: int = 0,
        sub_goal_setting: dict[str, Any] = {},
        **kwargs,
    ):
        super().__init__(skip_steps, succ_cnts, sub_goal_setting, **kwargs)
        self.setting = ObjectHeightDeltaConfig(**sub_goal_setting)
        self._initial_position: np.ndarray | None = None

    def check_status(self, scene) -> bool:
        current = _position(scene, self.setting.obj_uid)
        if self._initial_position is None:
            self._initial_position = current.copy()
        axis_idx = {"x": 0, "y": 1, "z": 2}[self.setting.axis]
        delta = current[axis_idx] - self._initial_position[axis_idx]
        return bool(delta > self.setting.min_delta)

    def get_info(self):
        return (
            f"{self.setting.obj_uid} {self.setting.axis} delta "
            f"> {self.setting.min_delta}"
        )


class ObjectAtTargetConfig(BaseModel):
    obj_uid: str = Field(..., description="Object UID in scene.object_list")
    target_uid: str = Field(..., description="Target UID in scene.object_list")
    xy_radius: float = Field(..., description="Strict xy radius in meters")
    z_tolerance: float = Field(..., description="Strict z tolerance in meters")

    @field_validator("xy_radius", "z_tolerance")
    @classmethod
    def validate_positive(cls, value):
        if value <= 0:
            raise ValueError("thresholds must be positive")
        return value


@MetricFactory.register("manip/labutopia/object_at_target")
class ObjectAtTarget(BaseMetric):
    def __init__(
        self,
        skip_steps: int = 1,
        succ_cnts: int = 0,
        sub_goal_setting: dict[str, Any] = {},
        **kwargs,
    ):
        super().__init__(skip_steps, succ_cnts, sub_goal_setting, **kwargs)
        self.setting = ObjectAtTargetConfig(**sub_goal_setting)
        self._initial_z: float | None = None

    def check_status(self, scene) -> bool:
        current = _position(scene, self.setting.obj_uid)
        target = _position(scene, self.setting.target_uid)
        if self._initial_z is None:
            self._initial_z = float(current[2])
        xy_dist = float(np.linalg.norm(current[:2] - target[:2]))
        z_dist = abs(float(current[2]) - self._initial_z)
        return bool(
            xy_dist < self.setting.xy_radius and z_dist < self.setting.z_tolerance
        )

    def get_info(self):
        return (
            f"{self.setting.obj_uid} within xy radius {self.setting.xy_radius} "
            f"of {self.setting.target_uid} and z tolerance {self.setting.z_tolerance}"
        )


class HandleDisplacementConfig(BaseModel):
    obj_uid: str = Field(..., description="Handle object UID in scene.object_list")
    min_distance: float = Field(..., description="Strict displacement threshold")

    @field_validator("min_distance")
    @classmethod
    def validate_min_distance(cls, value):
        if value <= 0:
            raise ValueError("min_distance must be positive")
        return value


@MetricFactory.register("manip/labutopia/handle_displacement")
class HandleDisplacement(BaseMetric):
    def __init__(
        self,
        skip_steps: int = 1,
        succ_cnts: int = 0,
        sub_goal_setting: dict[str, Any] = {},
        **kwargs,
    ):
        super().__init__(skip_steps, succ_cnts, sub_goal_setting, **kwargs)
        self.setting = HandleDisplacementConfig(**sub_goal_setting)
        self._initial_position: np.ndarray | None = None

    def check_status(self, scene) -> bool:
        current = _position(scene, self.setting.obj_uid)
        if self._initial_position is None:
            self._initial_position = current.copy()
        distance = float(np.linalg.norm(current - self._initial_position))
        return bool(distance > self.setting.min_distance)

    def get_info(self):
        return f"{self.setting.obj_uid} moved more than {self.setting.min_distance}m"
```

- [ ] **Step 3: Run the metric tests**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_labutopia_metrics.py -q
```

Expected result:

```text
4 passed
```

- [ ] **Step 4: Run formatting check**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git diff --check
```

Expected result: no output and exit code 0.

- [ ] **Step 5: Commit metrics**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git add genmanip/extensions/metrics/labutopia tests/labutopia_poc/test_labutopia_metrics.py
git commit -m "feat: add labutopia poc metrics"
```

Expected result: a commit that adds the metric extension and updates the metric test state to green.

---

### Task 3: Add Asset Overlay Builder

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/standalone_tools/labutopia_poc/build_asset_overlay.py`

- [ ] **Step 1: Create the overlay builder script**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/standalone_tools/labutopia_poc/build_asset_overlay.py`:

```python
import argparse
import hashlib
import json
import shutil
from pathlib import Path


TASK_PRIMS = {
    "level1_pick": ["/World/conical_bottle02"],
    "level1_place": ["/World/beaker2", "/World/target_plat"],
    "level1_open_door": [
        "/World/DryingBox_01",
        "/World/DryingBox_01/handle",
        "/World/DryingBox_01/RevoluteJoint",
    ],
}

PRIM_RENAME_MAP = {
    "/World/conical_bottle02": "obj_conical_bottle02",
    "/World/beaker2": "obj_beaker2",
    "/World/target_plat": "obj_target_plat",
    "/World/DryingBox_01": "obj_DryingBox_01",
    "/World/DryingBox_01/handle": "obj_DryingBox_01_handle",
    "/World/table": "obj_table",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copytree_clean(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def write_scene_usda(usda_path: Path) -> None:
    usda_path.write_text(
        """#usda 1.0
(
    defaultPrim = "World"
)

def Xform "World"
{
    def Xform "_scene" (
        prepend payload = @scene.usd@</World>
    )
    {
    }
}
""",
        encoding="utf-8",
    )


def build_manifest(labutopia_root: Path, overlay_root: Path, source_scene: Path) -> dict:
    overlay_scene_dir = overlay_root / "scene_usds/labutopia/level1_poc/lab_001"
    copied_files = []
    for path in sorted(overlay_scene_dir.rglob("*")):
        if path.is_file():
            copied_files.append(
                {
                    "path": str(path.relative_to(overlay_root)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )

    return {
        "source_repo": str(labutopia_root),
        "source_scene": str(source_scene),
        "overlay_root": str(overlay_root),
        "usd_name": "scene_usds/labutopia/level1_poc/lab_001/scene",
        "task_prims": TASK_PRIMS,
        "prim_rename_map": PRIM_RENAME_MAP,
        "table_uid": "table",
        "required_genmanip_object_uids": [
            "obj_conical_bottle02",
            "obj_beaker2",
            "obj_target_plat",
            "obj_DryingBox_01",
            "obj_DryingBox_01_handle",
            "obj_table",
        ],
        "copied_files": copied_files,
        "notes": [
            "scene.usda payloads scene.usd under /World/_scene.",
            "GenManip object discovery still requires obj_* prims under /World/<uuid>.",
            "If the payload retains raw LabUtopia prim names only, add a USD rename/wrapper pass before runtime smoke.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--labutopia-root",
        default="/cpfs/shared/simulation/zhuzihou/dev/LabUtopia",
    )
    parser.add_argument(
        "--overlay-root",
        default="/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets",
    )
    args = parser.parse_args()

    labutopia_root = Path(args.labutopia_root).resolve()
    overlay_root = Path(args.overlay_root).resolve()
    source_dir = labutopia_root / "assets/chemistry_lab/lab_001"
    source_scene = source_dir / "lab_001.usd"
    if not source_scene.exists():
        raise FileNotFoundError(source_scene)

    overlay_scene_dir = overlay_root / "scene_usds/labutopia/level1_poc/lab_001"
    copytree_clean(source_dir, overlay_scene_dir)
    shutil.copy2(source_scene, overlay_scene_dir / "scene.usd")
    write_scene_usda(overlay_scene_dir / "scene.usda")

    manifest = build_manifest(labutopia_root, overlay_root, source_scene)
    manifest_dir = overlay_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "labutopia_level1_poc.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote overlay to {overlay_scene_dir}")
    print(f"Wrote manifest to {manifest_dir / 'labutopia_level1_poc.json'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the overlay builder**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/build_asset_overlay.py
```

Expected output includes:

```text
Wrote overlay to /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/scene_usds/labutopia/level1_poc/lab_001
Wrote manifest to /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/manifests/labutopia_level1_poc.json
```

- [ ] **Step 3: Inspect the generated manifest**

Run:

```bash
python -m json.tool /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/manifests/labutopia_level1_poc.json >/tmp/labutopia_level1_poc_manifest.pretty.json
```

Expected result: exit code 0 and a formatted JSON file at `/tmp/labutopia_level1_poc_manifest.pretty.json`.

- [ ] **Step 4: Commit the builder**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git add standalone_tools/labutopia_poc/build_asset_overlay.py
git commit -m "feat: add labutopia asset overlay builder"
```

Expected result: a commit that adds only the builder script.

---

### Task 4: Add GenManip Task Package Configs

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/cameras/labutopia_franka_poc.yml`
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/labutopia_lab_poc.json`
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/common/task_semantics.yml`
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`
- Create: profile JSON/YAML files under `franka_poc/` and `lift2_candidate/`

- [ ] **Step 1: Add the Franka camera config**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/cameras/labutopia_franka_poc.yml`:

```yaml
camera1:
  name: camera_1
  exists: false
  prim_path: /LabUtopiaCamera1
  position: [2.0, 0.0, 2.0]
  orientation: [0.61237, 0.35355, 0.35355, 0.61237]
  resolution: [256, 256]
  image_type: rgb
camera2:
  name: camera_2
  exists: false
  prim_path: /LabUtopiaCamera2
  position: [0.1, 0.0, 2.5]
  orientation: [0.70711, 0.0, 0.0, -0.70711]
  resolution: [256, 256]
  image_type: rgb
```

- [ ] **Step 2: Add common task semantics**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/common/task_semantics.yml`:

```yaml
tasks:
  level1_pick:
    source_config: /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/config/level1_pick.yaml
    instruction: Pick up the conical bottle from the table.
    source_objects:
      target: /World/conical_bottle02
    genmanip_objects:
      target: obj_conical_bottle02
    metric:
      type: manip/labutopia/object_height_delta
      sub_goal_setting:
        obj_uid: obj_conical_bottle02
        axis: z
        min_delta: 0.10
  level1_place:
    source_config: /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/config/level1_place.yaml
    instruction: Pick up the beaker and place it on the target platform.
    source_objects:
      object: /World/beaker2
      target: /World/target_plat
    genmanip_objects:
      object: obj_beaker2
      target: obj_target_plat
    metric:
      type: manip/labutopia/object_at_target
      sub_goal_setting:
        obj_uid: obj_beaker2
        target_uid: obj_target_plat
        xy_radius: 0.05
        z_tolerance: 0.05
  level1_open_door:
    source_config: /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/config/level1_open_door.yaml
    instruction: Open the door of the drying box.
    source_objects:
      object: /World/DryingBox_01
      handle: /World/DryingBox_01/handle
      joint: /World/DryingBox_01/RevoluteJoint
    genmanip_objects:
      object: obj_DryingBox_01
      handle: obj_DryingBox_01_handle
    metric:
      preferred:
        type: manip/default/check_joint_angle
        sub_goal_setting:
          articulation_obj_uid: obj_DryingBox_01
          joint_name: RevoluteJoint
          angle_deg_range: [30, 120]
      fallback:
        type: manip/labutopia/handle_displacement
        sub_goal_setting:
          obj_uid: obj_DryingBox_01_handle
          min_distance: 0.12
```

- [ ] **Step 3: Add the checked-in asset manifest pointer**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/common/assets_manifest.json`:

```json
{
  "overlay_root": "/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets",
  "runtime_usd_name": "scene_usds/labutopia/level1_poc/lab_001/scene",
  "generated_manifest": "/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/manifests/labutopia_level1_poc.json",
  "required_object_uids": [
    "obj_conical_bottle02",
    "obj_beaker2",
    "obj_target_plat",
    "obj_DryingBox_01",
    "obj_DryingBox_01_handle",
    "obj_table"
  ],
  "table_uid": "table",
  "env_vars": {
    "MDL_SYSTEM_PATH": "/isaac-sim/materials/:{ASSETS_DIR}/scene_usds/labutopia/level1_poc/lab_001/SubUSDs/materials:{ASSETS_DIR}/miscs/mdl/labutopia/mdl"
  }
}
```

- [ ] **Step 4: Add profile JSON indexes**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/labutopia_lab_poc.json`:

```json
[
  "ebench/labutopia_lab_poc/franka_poc/franka_poc.json",
  "ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json"
]
```

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json`:

```json
[
  "ebench/labutopia_lab_poc/franka_poc/level1_pick.yml",
  "ebench/labutopia_lab_poc/franka_poc/level1_place.yml",
  "ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml"
]
```

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json`:

```json
[
  "ebench/labutopia_lab_poc/lift2_candidate/level1_pick.yml",
  "ebench/labutopia_lab_poc/lift2_candidate/level1_place.yml",
  "ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml"
]
```

- [ ] **Step 5: Add the Franka task YAMLs**

Use this YAML pattern for `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_pick.yml`:

```yaml
evaluation_configs:
- task_name: ebench/labutopia_lab_poc/franka_poc/level1_pick
  usd_name: scene_usds/labutopia/level1_poc/lab_001/scene
  table_uid: table
  mode: manual
  instruction: Pick up the conical bottle from the table.
  num_test: 1
  num_steps: 800
  physics_dt: 0.0166666667
  rendering_dt: 0.0166666667
  robots:
  - type: manip/franka/panda_hand
    position: [-0.4, 0.0, 0.71]
  domain_randomization:
    cameras:
      config_path: configs/cameras/labutopia_franka_poc.yml
      type: fixed
    random_environment:
      has_wall: false
      hdr: false
      robot_base_position: false
      robot_eepose: false
      table_texture: false
      table_type: false
      wall_texture: false
    rewrite_instruction: false
  generation_config:
    action_path:
      mode: manual
      robot: 0
    goal:
    - - - type: manip/labutopia/object_height_delta
          skip_steps: 1
          succ_cnts: 59
          sub_goal_setting:
            obj_uid: obj_conical_bottle02
            axis: z
            min_delta: 0.10
    mode: manual
    planner: curobo
  object_config: {}
  preprocess_config: []
  layout_config:
    ignored_objects: []
    type: None
  env_vars:
    MDL_SYSTEM_PATH: "/isaac-sim/materials/:{ASSETS_DIR}/scene_usds/labutopia/level1_poc/lab_001/SubUSDs/materials:{ASSETS_DIR}/miscs/mdl/labutopia/mdl"
```

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_place.yml` by changing the task name, instruction, `num_steps`, and goal:

```yaml
evaluation_configs:
- task_name: ebench/labutopia_lab_poc/franka_poc/level1_place
  usd_name: scene_usds/labutopia/level1_poc/lab_001/scene
  table_uid: table
  mode: manual
  instruction: Pick up the beaker and place it on the target platform.
  num_test: 1
  num_steps: 2000
  physics_dt: 0.0166666667
  rendering_dt: 0.0166666667
  robots:
  - type: manip/franka/panda_hand
    position: [-0.4, 0.0, 0.71]
  domain_randomization:
    cameras:
      config_path: configs/cameras/labutopia_franka_poc.yml
      type: fixed
    random_environment:
      has_wall: false
      hdr: false
      robot_base_position: false
      robot_eepose: false
      table_texture: false
      table_type: false
      wall_texture: false
    rewrite_instruction: false
  generation_config:
    action_path:
      mode: manual
      robot: 0
    goal:
    - - - type: manip/labutopia/object_at_target
          skip_steps: 1
          succ_cnts: 59
          sub_goal_setting:
            obj_uid: obj_beaker2
            target_uid: obj_target_plat
            xy_radius: 0.05
            z_tolerance: 0.05
    mode: manual
    planner: curobo
  object_config: {}
  preprocess_config: []
  layout_config:
    ignored_objects: []
    type: None
  env_vars:
    MDL_SYSTEM_PATH: "/isaac-sim/materials/:{ASSETS_DIR}/scene_usds/labutopia/level1_poc/lab_001/SubUSDs/materials:{ASSETS_DIR}/miscs/mdl/labutopia/mdl"
```

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml`:

```yaml
evaluation_configs:
- task_name: ebench/labutopia_lab_poc/franka_poc/level1_open_door
  usd_name: scene_usds/labutopia/level1_poc/lab_001/scene
  table_uid: table
  mode: manual
  instruction: Open the door of the drying box.
  num_test: 1
  num_steps: 1000
  physics_dt: 0.0166666667
  rendering_dt: 0.0166666667
  robots:
  - type: manip/franka/panda_hand
    position: [-0.4, 0.0, 0.71]
  domain_randomization:
    cameras:
      config_path: configs/cameras/labutopia_franka_poc.yml
      type: fixed
    random_environment:
      has_wall: false
      hdr: false
      robot_base_position: false
      robot_eepose: false
      table_texture: false
      table_type: false
      wall_texture: false
    rewrite_instruction: false
  generation_config:
    action_path:
      mode: manual
      robot: 0
    goal:
    - - - type: manip/labutopia/handle_displacement
          skip_steps: 1
          succ_cnts: 59
          sub_goal_setting:
            obj_uid: obj_DryingBox_01_handle
            min_distance: 0.12
    mode: manual
    planner: curobo
  object_config: {}
  preprocess_config: []
  layout_config:
    ignored_objects: []
    type: None
  env_vars:
    MDL_SYSTEM_PATH: "/isaac-sim/materials/:{ASSETS_DIR}/scene_usds/labutopia/level1_poc/lab_001/SubUSDs/materials:{ASSETS_DIR}/miscs/mdl/labutopia/mdl"
```

- [ ] **Step 6: Add the lift2 candidate YAMLs**

Create three lift2 candidate YAMLs by copying the three Franka YAMLs into `/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/` and applying these exact replacements in each file:

```yaml
robots:
- type: manip/lift2/R5a
  position: [0.0, 0.0, 0.0]
domain_randomization:
  cameras:
    config_path: configs/cameras/fixed_camera_lift2_simbox.yml
    type: fixed
```

Use these exact `task_name` values:

```text
ebench/labutopia_lab_poc/lift2_candidate/level1_pick
ebench/labutopia_lab_poc/lift2_candidate/level1_place
ebench/labutopia_lab_poc/lift2_candidate/level1_open_door
```

Keep the same object/metric goals so the lift2 profile tests the same task semantics.

- [ ] **Step 7: Commit task package configs**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git add configs/cameras/labutopia_franka_poc.yml configs/tasks/ebench/labutopia_lab_poc
git commit -m "feat: add labutopia poc task package"
```

Expected result: a commit that adds camera config and task package files.

---

### Task 5: Add Static Task Package Validator

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/standalone_tools/labutopia_poc/validate_task_package.py`

- [ ] **Step 1: Create the validator**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/standalone_tools/labutopia_poc/validate_task_package.py`:

```python
import json
from pathlib import Path

import yaml

from genmanip.core.scene.scene_config import SceneConfig


ROOT = Path("/cpfs/shared/simulation/zhuzihou/dev/GenManip")
TASK_ROOT = ROOT / "configs/tasks"
PACKAGE = TASK_ROOT / "ebench/labutopia_lab_poc"


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_index(index_path: Path) -> list[Path]:
    entries = read_json(index_path)
    require(isinstance(entries, list), f"{index_path} must contain a list")
    resolved = []
    for entry in entries:
        require(isinstance(entry, str), f"{index_path} entry must be a string")
        require(
            entry.endswith((".yml", ".json")),
            f"{index_path} entry must end with .yml or .json: {entry}",
        )
        path = TASK_ROOT / entry
        require(path.exists(), f"missing index target: {path}")
        resolved.append(path)
    return resolved


def validate_task_yml(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require("evaluation_configs" in data, f"{path} missing evaluation_configs")
    require(isinstance(data["evaluation_configs"], list), f"{path} evaluation_configs must be list")
    for cfg in data["evaluation_configs"]:
        SceneConfig(**cfg)
        require("num_test" in cfg, f"{path} config missing num_test")
        require(cfg["task_name"].startswith("ebench/labutopia_lab_poc/"), cfg["task_name"])
        require(cfg["table_uid"] == "table", f"{path} table_uid must be table")


def validate_profile(profile: str) -> None:
    profile_dir = PACKAGE / profile
    index_path = profile_dir / f"{profile}.json"
    require(index_path.exists(), f"missing profile index: {index_path}")
    targets = validate_index(index_path)
    yml_targets = [target for target in targets if target.suffix == ".yml"]
    require(len(yml_targets) == 3, f"{profile} must contain exactly 3 yml tasks")
    for target in yml_targets:
        validate_task_yml(target)


def main() -> None:
    validate_index(PACKAGE / "labutopia_lab_poc.json")
    validate_profile("franka_poc")
    validate_profile("lift2_candidate")
    print("LabUtopia task package validation OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run validator**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected output:

```text
LabUtopia task package validation OK
```

- [ ] **Step 3: Run JSON validation directly**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json >/tmp/franka_poc.json
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json >/tmp/lift2_candidate.json
```

Expected result: both commands exit 0.

- [ ] **Step 4: Commit validator**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git add standalone_tools/labutopia_poc/validate_task_package.py
git commit -m "test: validate labutopia task package"
```

Expected result: a commit that adds the validator.

---

### Task 6: Run Asset QA And Franka Smoke

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/franka_smoke.md`

- [ ] **Step 1: Run local verification commands**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_labutopia_metrics.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
git diff --check
```

Expected result:

```text
4 passed
LabUtopia task package validation OK
```

`git diff --check` should have no output.

- [ ] **Step 2: Start GenManip eval server**

Run in a long-running terminal:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
ASSETS_DIR=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets \
python ray_eval_server.py --host 0.0.0.0 --port 8087 --no_save_process
```

Expected result: server starts and exposes `http://127.0.0.1:8087/docs`.

- [ ] **Step 3: Submit and run Franka profile**

Run in a second terminal:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
gmp submit ebench/labutopia_lab_poc/franka_poc --run_id labutopia_franka_smoke
gmp eval -a franka -g panda_hand --worker_ids 0 --run_id labutopia_franka_smoke
gmp status --run_id labutopia_franka_smoke
```

Expected result: all three tasks are accepted by `gmp submit`; `gmp eval` reaches reset and step. If score is blocked by asset naming or metadata, record the exact exception and file path in the smoke report.

- [ ] **Step 4: Write Franka smoke report**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/franka_smoke.md` after the commands finish. The report must contain:

```markdown
# LabUtopia Franka POC Smoke Report

## Commands

```bash
ASSETS_DIR=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets \
python ray_eval_server.py --host 0.0.0.0 --port 8087 --no_save_process

gmp submit ebench/labutopia_lab_poc/franka_poc --run_id labutopia_franka_smoke
gmp eval -a franka -g panda_hand --worker_ids 0 --run_id labutopia_franka_smoke
gmp status --run_id labutopia_franka_smoke
```

## Results

| Task | Reset | Step | Metric | Evidence |
| --- | --- | --- | --- | --- |

## Asset Findings

- Overlay manifest: `/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/manifests/labutopia_level1_poc.json`
- Object discovery status:
- Door articulation status:

## Raw Evidence

Add one fenced `text` block for `gmp submit`, one for `gmp eval`, and one for `gmp status`. Each block must contain the exact command output lines that justify the table values above.
```

Populate the `Results` table with exactly these three task rows: `level1_pick`, `level1_place`, and `level1_open_door`. Use only `PASS`, `FAIL`, or `BLOCKED` in the `Reset`, `Step`, and `Metric` columns. Put exact exception messages or result file paths in `Evidence`.

- [ ] **Step 5: Commit smoke report**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git add docs/labutopia_lab_poc/franka_smoke.md
git commit -m "docs: record labutopia franka smoke"
```

Expected result: a docs commit with the smoke outcome.

---

### Task 7: Document Lift2 Candidate Readiness

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/lift2_readiness.md`

- [ ] **Step 1: Run lift2 static validation**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/validate_task_package.py
```

Expected output:

```text
LabUtopia task package validation OK
```

- [ ] **Step 2: Attempt lift2 schema smoke**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
gmp submit ebench/labutopia_lab_poc/lift2_candidate --run_id labutopia_lift2_schema_smoke
gmp eval -a r5a -g lift2 --worker_ids 0 --run_id labutopia_lift2_schema_smoke
```

Expected result: the run either reaches reset/step with lift2 or records a concrete blocker such as camera framing, object reachability, base collision, missing `obj_*`, or action schema mismatch.

- [ ] **Step 3: Write readiness report**

Create `/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/lift2_readiness.md` after the schema smoke finishes. The report must contain:

```markdown
# LabUtopia Lift2 Candidate Readiness

## Profile

- Task package: `ebench/labutopia_lab_poc/lift2_candidate`
- Robot: `manip/lift2/R5a`
- Camera config: `configs/cameras/fixed_camera_lift2_simbox.yml`
- Run id: `labutopia_lift2_schema_smoke`

## Checklist

- [ ] GenManip task profile loads with `robot.type: manip/lift2/R5a`.
- [ ] Reset returns `instruction`, `state.joints`, `state.gripper`, `state.base`, `state.ee_pose`, and `robot_id`.
- [ ] Camera keys include `video.overlook_camera_view`, `video.left_camera_view`, and `video.right_camera_view`.
- [ ] `top_camera` is defined.
- [ ] Step accepts 16D arm/gripper action in lift2 order plus 3D `base_motion`.
- [ ] OpenPI-style relative base action runs without schema errors.
- [ ] InternVLA-style relative base chunk/action sequence runs without schema errors.
- [ ] X-VLA-style absolute base action runs without theta or unit mistakes.
- [ ] Zero/mock lift2 action can run a short episode without blank cameras, NaNs, or joint instability.
- [ ] Table height, robot root pose, lift height, object spawn z, and reachability are documented per task.
- [ ] Left and right arm reach checks pass for required interaction points, or blockers are recorded.
- [ ] Success predicates are implemented in GenManip/EBench terms, not LabUtopia controller internals.

## Per-Task Readiness

| Task | Reset | Step | Reachability | Camera Framing | Metric | Finding |
| --- | --- | --- | --- | --- | --- | --- |

## Baseline Compatibility Notes

- OpenPI and InternVLA expect relative base motion behavior.
- X-VLA sends absolute base targets.
- The lift2 candidate is not official-baseline-ready until all checked items above pass.
```

Populate the readiness table with exactly these three task rows: `level1_pick`, `level1_place`, and `level1_open_door`. Use only `PASS`, `FAIL`, or `BLOCKED` in the `Reset`, `Step`, `Reachability`, `Camera Framing`, and `Metric` columns. Put the concrete command output, exception, or result path in `Finding`.

- [ ] **Step 4: Commit readiness report**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
git add docs/labutopia_lab_poc/lift2_readiness.md
git commit -m "docs: record labutopia lift2 readiness"
```

Expected result: a docs commit with concrete lift2 readiness status.

---

### Task 8: Add LabUtopia Runbook And Cross-Repo Pointers

**Files:**
- Create: `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/ebench-integration/labutopia-level1-poc-runbook.md`

- [ ] **Step 1: Create LabUtopia runbook**

Create `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/ebench-integration/labutopia-level1-poc-runbook.md`:

```markdown
# LabUtopia Level1 EBench/GenManip POC Runbook

## Scope

This POC covers:

- `config/level1_pick.yaml`
- `config/level1_place.yaml`
- `config/level1_open_door.yaml`

The first runnable profile is `franka_poc`. The `lift2_candidate` profile is tracked separately for official EBench baseline readiness.

## Repositories

```text
LabUtopia: /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
GenManip: /cpfs/shared/simulation/zhuzihou/dev/GenManip
Asset overlay: /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets
```

## Source Assets

- `assets/chemistry_lab/lab_001/lab_001.usd`
- `assets/chemistry_lab/lab_001/SubUSDs/`

## Source Objects

| LabUtopia config | Source prim | GenManip UID |
| --- | --- | --- |
| `level1_pick` | `/World/conical_bottle02` | `obj_conical_bottle02` |
| `level1_place` | `/World/beaker2` | `obj_beaker2` |
| `level1_place` | `/World/target_plat` | `obj_target_plat` |
| `level1_open_door` | `/World/DryingBox_01` | `obj_DryingBox_01` |
| `level1_open_door` | `/World/DryingBox_01/handle` | `obj_DryingBox_01_handle` |

## GenManip Commands

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python standalone_tools/labutopia_poc/build_asset_overlay.py
python -m pytest tests/labutopia_poc/test_labutopia_metrics.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
```

```bash
ASSETS_DIR=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets \
python ray_eval_server.py --host 0.0.0.0 --port 8087 --no_save_process
```

```bash
gmp submit ebench/labutopia_lab_poc/franka_poc --run_id labutopia_franka_smoke
gmp eval -a franka -g panda_hand --worker_ids 0 --run_id labutopia_franka_smoke
gmp status --run_id labutopia_franka_smoke
```

## Reports

- GenManip Franka smoke report: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/franka_smoke.md`
- GenManip lift2 readiness report: `/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/lift2_readiness.md`
```

- [ ] **Step 2: Run markdown and git checks**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
git diff --check
```

Expected result: no output and exit code 0.

- [ ] **Step 3: Commit LabUtopia runbook**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
git add docs/ebench-integration/labutopia-level1-poc-runbook.md
git commit -m "docs: add labutopia ebench poc runbook"
```

Expected result: a docs commit in LabUtopia.

---

## Final Verification

Run these commands before declaring the POC implementation complete:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
python -m pytest tests/labutopia_poc/test_labutopia_metrics.py -q
python standalone_tools/labutopia_poc/validate_task_package.py
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json >/tmp/franka_poc.json
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json >/tmp/lift2_candidate.json
git diff --check
```

Expected output includes:

```text
4 passed
LabUtopia task package validation OK
```

Run this in LabUtopia:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
git diff --check
```

Expected result: no output and exit code 0.

Runtime completion requires a recorded result in:

```text
/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/franka_smoke.md
/cpfs/shared/simulation/zhuzihou/dev/GenManip/docs/labutopia_lab_poc/lift2_readiness.md
```

The Franka POC is complete only when all three tasks reach `reset -> step -> metric result`, or the smoke report records exact blockers for each failing task. The lift2 candidate is complete only as a readiness profile until the checklist in `lift2_readiness.md` is fully checked.

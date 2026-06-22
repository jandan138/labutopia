# LabUtopia EBench/GenManip POC Design

## Goal

Build a combined asset-migration and evaluation-contract POC for bringing a small LabUtopia laboratory task family into GenManip/EBench style evaluation.

The first runnable scope covers three LabUtopia configs:

- `level1_pick`
- `level1_place`
- `level1_open_door`

The POC must prove more than asset visibility. It must show that migrated LabUtopia assets and task semantics can enter the GenManip evaluation path and reach `SceneConfig -> reset -> EvalClient step -> metric score`.

## Decisions

The POC will use two explicit embodiment profiles:

- `franka_poc`: first runnable profile, using `manip/franka/panda_hand` to reduce variables and preserve the original LabUtopia tabletop workspace.
- `lift2_candidate`: a separate readiness profile for future official EBench baseline evaluation with `manip/lift2/R5a`.

The Franka profile is not official EBench leaderboard compatibility. It is a fast GenManip contract proof. The lift2 profile must not be implemented as a simple robot-name swap; it needs its own cameras, robot pose, action schema, base-motion handling, reachability checks, and validation.

The task package structure should be concrete GenManip config, not only a LabUtopia-side adapter. Common files can document source semantics and assets, but generated profile YAMLs must fully materialize the GenManip `evaluation_configs` contract.

## Non-Goals

This POC does not migrate all 29 LabUtopia configs.

This POC does not reuse LabUtopia controllers as formal EBench evaluators. Controllers remain smoke-test or reference tools only.

This POC does not claim official lift2/R5a baseline readiness until `lift2_candidate` passes the checklist in this document.

This POC does not mix LabUtopia HDF5/action/camera schemas into EBench. The runtime interface remains GenManip `EvalClient`.

## Multi-Agent Review Summary

Four read-only review angles were used before this design was written:

- GenManip/EBench contract: directory submissions need JSON indexes under `GenManip/configs/tasks`; eval YAML must provide `evaluation_configs`; `num_test` is required by worker scheduling; common manifests are tooling inputs, not server inputs.
- Asset migration: `lab_001` is shared by all three tasks; GenManip object discovery expects `obj_*` style names; the overlay needs a prim rename or wrapper plan and consistent `env_vars`.
- Metric design: exact LabUtopia parity needs initial-pose-aware metrics for pick/place; open door should prefer articulation joint angle and avoid Franka gripper distance in the scored predicate.
- Lift2 readiness: official baselines require lift2/R5a obs/action/camera contracts, including `video.overlook_camera_view`, `video.left_camera_view`, `video.right_camera_view`, 16D arm/gripper action, and 3D `base_motion`.

## Source Scope

LabUtopia source files:

- `config/level1_pick.yaml`
- `config/level1_place.yaml`
- `config/level1_open_door.yaml`
- `tasks/base_task.py`
- `tasks/open_close_task.py`
- `controllers/pick_controller.py`
- `controllers/place_controller.py`
- `controllers/open_controller.py`
- `assets/chemistry_lab/lab_001/lab_001.usd`

GenManip/EBench target evidence:

- `GenManip/genmanip/core/scene/scene_config.py`
- `GenManip/genmanip/core/evaluator/env.py`
- `GenManip/genmanip/core/evaluator/isaac_worker_pool.py`
- `GenManip/genmanip/core/metrics/metrics_manager.py`
- `GenManip/genmanip/extensions/metrics/default/sr_based_genmanip_range.py`
- `GenManip/genmanip/extensions/metrics/default/check_joint_angle.py`
- `GenManip/genmanip/extensions/robots/default/franka/panda_hand.py`
- `GenManip/genmanip/extensions/robots/default/r5a/lift2.py`
- `GenManip/configs/cameras/fixed_camera_lift2_simbox.yml`
- `genmanip-client/src/genmanip_client/eval_client.py`
- EBench baseline clients under `EBench/baselines/`

## Target Directory Shape

GenManip task configs should live under:

```text
/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/labutopia_lab_poc/
  labutopia_lab_poc.json
  common/
    assets_manifest.json
    task_semantics.yml
  franka_poc/
    franka_poc.json
    level1_pick.yml
    level1_place.yml
    level1_open_door.yml
  lift2_candidate/
    lift2_candidate.json
    level1_pick.yml
    level1_place.yml
    level1_open_door.yml
```

The aggregate `labutopia_lab_poc.json` is optional and should not be used for normal smoke runs if it mixes profiles. Routine validation should submit one profile at a time.

Task names must be profile-qualified to avoid progress/result collisions:

```text
ebench/labutopia_lab_poc/franka_poc/level1_pick
ebench/labutopia_lab_poc/franka_poc/level1_place
ebench/labutopia_lab_poc/franka_poc/level1_open_door
ebench/labutopia_lab_poc/lift2_candidate/level1_pick
ebench/labutopia_lab_poc/lift2_candidate/level1_place
ebench/labutopia_lab_poc/lift2_candidate/level1_open_door
```

## Asset Overlay

Use a separate overlay root rather than mutating downloaded EBench assets in place:

```text
/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Overlay/labutopia_level1_poc/assets/
  scene_usds/labutopia/level1_poc/lab_001/scene.usd
  scene_usds/labutopia/level1_poc/lab_001/scene.usda
  scene_usds/labutopia/level1_poc/lab_001/SubUSDs/
  manifests/labutopia_level1_poc.json
```

`SceneConfig.usd_name` should be relative to `ASSETS_DIR` and omit the extension:

```yaml
usd_name: scene_usds/labutopia/level1_poc/lab_001/scene
```

The overlay must include or intentionally waive these assets:

- Shared scene support: physics scene, lights, ground, table/support surface, `Looks`, materials, textures.
- Pick: `conical_bottle02`.
- Place: `beaker2` and `target_plat`.
- Open door: complete `DryingBox_01` hierarchy, including handle, door mesh, body mesh, and `RevoluteJoint`.

GenManip object discovery is a first-order migration risk. Raw LabUtopia names such as `/World/conical_bottle02` are unlikely to be enough. The overlay should expose GenManip-discoverable object UIDs, for example:

```text
obj_conical_bottle02
obj_beaker2
obj_target_plat
obj_DryingBox_01
obj_table
```

The table/support surface decision must be explicit. LabUtopia has multiple support-like prims, including table meshes and collision helpers. The POC should designate one `obj_table` as the support surface used by `table_uid`.

All three task configs in a submitted profile must use consistent `env_vars`, especially `MDL_SYSTEM_PATH`, because evaluator workers resolve environment variables across submitted configs and the first value wins.

## Asset QA Artifacts

The asset migration milestone should produce:

- `manifest.json`: source path, overlay path, SHA256, file size, dependency status, prim rename map, task-to-prim map, material bindings, articulation joints and limits.
- `dependency_report.json`: resolved and unresolved USD/MDL/texture dependencies.
- `usd_open_warnings.log`: final open warnings with the target `ASSETS_DIR` and `MDL_SYSTEM_PATH`.
- `stage_tree.txt`: default prim, first child, required `obj_*` names, `obj_table`, and task object paths.
- `prim_bbox_physics.csv`: bbox, scale, collision API, rigid body API, mass or density for the target objects and support surface.
- screenshots under `qa/screenshots/{pick,place,open}/`.
- `open_door_joint_trace.csv` and `open_door.mp4` proving the door articulation moves.

Unresolved remote cabinet payloads that are not used by the three POC tasks may be removed, muted, vendored, or explicitly waived in the manifest.

## Task Semantics And Metrics

Metrics should be robot-agnostic. They should inspect object or articulation state, not Franka gripper distance, Franka joint shape, or LabUtopia controller internals.

### `level1_pick`

LabUtopia success:

- The target object z position is more than `0.1m` above its initial z position.
- The condition is held for 60 consecutive controller success checks.

GenManip metric:

- Preferred: custom `manip/labutopia/object_height_delta`.
- Acceptable coarse fallback for early smoke only: `manip/default/sr_based_genmanip_range` with an absolute z range if table height is fixed.

Recommended shape:

```yaml
type: manip/labutopia/object_height_delta
sub_goal_setting:
  obj_uid: obj_conical_bottle02
  reference: initial
  axis: z
  min_delta: 0.10
skip_steps: 1
succ_cnts: 59
```

### `level1_place`

LabUtopia success:

- Object xy distance to `target_plat` is less than `0.05m`.
- Object z remains within `0.05m` of its initial z.

GenManip metric:

- Preferred: custom `manip/labutopia/object_at_target`.
- Existing range metric can approximate a rectangular target area but does not exactly match the radial xy condition or initial-z reference.

Recommended shape:

```yaml
type: manip/labutopia/object_at_target
sub_goal_setting:
  obj_uid: obj_beaker2
  target_uid: obj_target_plat
  xy_radius: 0.05
  z_reference: initial
  z_tolerance: 0.05
skip_steps: 1
succ_cnts: 59
```

### `level1_open_door`

LabUtopia success:

- Handle displacement is greater than `0.12m`.
- Franka gripper-to-handle distance is greater than `0.04m`.

GenManip metric:

- Preferred: `manip/default/check_joint_angle`, if the converted door has a stable articulation UID and DOF name.
- Fallback: custom `manip/labutopia/handle_displacement` or generic pose-delta metric on the handle subprim.

The scored metric should not include Franka gripper distance. That term is useful for LabUtopia controller completion but would make the official lift2 profile robot-specific.

Recommended shape:

```yaml
type: manip/default/check_joint_angle
sub_goal_setting:
  articulation_obj_uid: obj_DryingBox_01
  joint_name: RevoluteJoint
  angle_deg_range: [30, 120]
skip_steps: 1
succ_cnts: 59
```

The `[30, 120]` range is an initial smoke threshold. The accepted POC must replace it with a calibrated range from the migrated USD by comparing closed and open joint traces.

## GenManip Evaluation Contract

Each task YAML used for evaluation must contain `evaluation_configs`. `demonstration_configs` can be omitted for this POC unless a data-generation path is added later.

Every `evaluation_configs[]` entry must parse as `SceneConfig` and include:

- `task_name`
- `usd_name`
- `table_uid`
- `robots`
- `domain_randomization`
- `generation_config.goal`
- `instruction`
- `num_test`
- `num_steps`
- `physics_dt`
- `rendering_dt`
- `env_vars`

The JSON profile index files should point to concrete `.yml` files or nested `.json` files using paths relative to `GenManip/configs/tasks`.

The evaluator reads task metadata and metrics from generated task data and `meta_info.pkl`, not from a documentation-only manifest. Any manifest or shared semantics file must be expanded into concrete generated configs and task metadata before runtime evaluation.

## Embodiment Profiles

### `franka_poc`

Purpose:

- Fastest runnable GenManip POC for LabUtopia lab assets and task semantics.

Robot:

```yaml
robots:
  - type: manip/franka/panda_hand
```

Validation:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
gmp submit ebench/labutopia_lab_poc/franka_poc --run_id labutopia_franka_smoke
gmp eval -a franka -g panda_hand --worker_ids 0
```

The action schema is 9D Franka/panda-hand. Cameras can be Franka-specific and do not have to match official lift2 baseline camera names.

### `lift2_candidate`

Purpose:

- Prepare the same task semantics for official EBench baseline compatibility.

Robot:

```yaml
robots:
  - type: manip/lift2/R5a
```

Validation:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/GenManip
gmp submit ebench/labutopia_lab_poc/lift2_candidate --run_id labutopia_lift2_smoke
gmp eval -a r5a -g lift2 --worker_ids 0
```

The lift2 profile must use EBench-compatible camera and action contracts:

- obs includes `instruction`, `state.joints`, `state.gripper`, `state.base`, `state.ee_pose`, and camera views.
- camera keys include `video.overlook_camera_view`, `video.left_camera_view`, and `video.right_camera_view`.
- `top_camera` is defined for full EBench compatibility, even if a current baseline reads only three views.
- action accepts 16D arm/gripper command in lift2 order plus 3D `base_motion`.
- both relative base motion and absolute base target behavior are validated, because OpenPI/InternVLA and X-VLA use different base conventions.

The lift2 profile must document table height, robot root pose, lift height, object spawn z, and reachable interaction points per task.

## Milestones

### 1. Inventory And Mapping

Deliver:

- asset manifest
- task semantics file
- prim rename map
- LabUtopia config to GenManip `SceneConfig` mapping

Acceptance:

- Every POC object UID traces to a LabUtopia source prim.
- The chosen support surface and `table_uid` are documented.
- The design makes clear which files are source material and which files are GenManip runtime inputs.

### 2. Asset Overlay And Visual QA

Deliver:

- overlay asset root
- `scene.usd` and `scene.usda`
- dependency and stage-tree reports
- screenshots and open-door joint trace

Acceptance:

- `scene.usda` opens with the final `ASSETS_DIR` and `MDL_SYSTEM_PATH`.
- Required `obj_*` objects are discoverable.
- Materials and textures render without unwaived missing dependencies.
- `DryingBox_01` articulation is readable and movable.

### 3. Franka POC Evaluation

Deliver:

- `franka_poc` JSON index and three task YAMLs.
- LabUtopia custom metrics if required for exact pick/place parity.
- Runtime smoke logs and result files.

Acceptance:

- The profile passes JSON and `SceneConfig` validation.
- GenManip server can load the profile.
- EvalClient can reset and step each task.
- Each task returns metric output and an episode result.
- At least one deterministic smoke path per task proves score can move from 0 to 1, or records the exact blocker.

### 4. Lift2 Candidate Readiness

Deliver:

- `lift2_candidate` draft configs or config stubs.
- per-task reachability/readiness report.
- camera/action/obs contract checklist results.

Acceptance:

- The profile declares `manip/lift2/R5a` and uses lift2 camera config.
- Reset obs shape and action schema expectations are documented.
- Table height, robot root pose, lift height, object spawn z, and reachability are documented.
- The remaining work to run OpenPI, X-VLA, and InternVLA-A1 baselines is explicit.

## Static Validation Commands

Run from `GenManip` after configs exist:

```bash
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/franka_poc/franka_poc.json
python -m json.tool configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json
```

```bash
python - <<'PY'
from pathlib import Path
import yaml
from genmanip.core.scene.scene_config import SceneConfig

roots = [
    Path("configs/tasks/ebench/labutopia_lab_poc/franka_poc"),
    Path("configs/tasks/ebench/labutopia_lab_poc/lift2_candidate"),
]

for root in roots:
    for yml in root.glob("*.yml"):
        data = yaml.safe_load(yml.read_text())
        for cfg in data["evaluation_configs"]:
            SceneConfig(**cfg)
            assert "num_test" in cfg, yml
print("SceneConfig validation OK")
PY
```

## Lift2 Readiness Checklist

- [ ] GenManip task profile loads with `robot.type: manip/lift2/R5a`.
- [ ] Reset returns required obs keys, shapes, dtypes, and `robot_id`.
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
- [ ] Documentation states that Franka POC pass does not imply lift2/R5a official baseline pass.

## Main Risks

GenManip object discovery may not see raw LabUtopia prim names. The overlay needs `obj_*` wrapping or a deliberate loader extension.

Door articulation may not expose the same joint name or angle direction after migration. The POC must record a joint trace and calibrate the angle range.

Absolute z thresholds may break across profile changes. Pick/place metrics should prefer initial-reference semantics.

Submitting Franka and lift2 profiles together can cause env var and result namespace confusion. Submit one profile at a time during smoke validation.

Official EBench baseline compatibility depends on cameras and action schema as much as task assets. The lift2 profile is not complete until it passes the readiness checklist.

## Completion Criteria

The POC design is implemented when:

1. The asset overlay and manifest exist for `lab_001` POC assets.
2. The GenManip task package has concrete `franka_poc` YAMLs for all three tasks.
3. The Franka profile completes `reset -> step -> metric score` for the three tasks.
4. Metric behavior is robot-agnostic and does not depend on Franka-specific state.
5. The lift2 candidate profile has explicit configs or stubs plus a readiness report that shows what remains before official baseline evaluation.

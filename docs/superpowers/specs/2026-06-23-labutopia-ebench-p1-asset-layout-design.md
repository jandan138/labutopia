# LabUtopia EBench P1 Asset Layout Design

Date: 2026-06-23

## Goal

Make the three LabUtopia Franka POC tasks render as understandable eval-path reset scenes by fixing runtime asset coordinates, visible material contrast, and the drying-box handle hierarchy without weakening the path toward EBench official Lift2 baseline evaluation.

## Current Evidence

The P0 camera/light work changed `level1_pick` and `level1_place` from pure black readback to visible readback, but the images remain nearly flat gray and do not show task-readable objects. USD inspection shows why:

- `conical_bottle02`, `beaker2`, and `target_plat` are authored around world `x=8.6` to `x=10.2`.
- `DryingBox_01` is authored around world `x=45.9`.
- The Franka POC robot is authored near `x=-0.4`, so the source LabUtopia scene and robot workspace are not in the same runtime coordinate frame.
- `/World/DryingBox_01/handle` only has a correct world pose when composed through `/World/DryingBox_01`; as an independent top-level payload its local translate becomes a huge world translate and its bbox becomes roughly 1000 times too large.
- Several source material bindings point to `/World/Looks/...`; payloading a narrow source prim can drop those bindings because the relationship target is outside the payload scope.

## Reviewed Alternatives

### A. Keep Current Top-Level Handle Payload

This preserves current GenManip UID discovery, but it is physically wrong. The handle loses the drying-box parent transform and no longer follows the door or joint structure. Reject.

### B. Preserve Only Nested Handle

This preserves USD hierarchy, but current `get_object_list()` only discovers immediate `/World/<scene_uid>/obj_*` children. A nested `/World/labutopia_level1_poc/obj_obj_DryingBox_01/handle` would not become `scene.object_list["obj_DryingBox_01_handle"]` by itself. Reject as incomplete.

### C. Use Existing Articulation-Part Path

Use the drying box as one runtime wrapper and configure `level1_open_door` with `object_config.obj_DryingBox_01` as an `existed_object` articulation. GenManip then registers `obj_DryingBox_01_handle` from `articulation_info.part.handle = "/handle"` and the metric can address the nested handle without a second visual/physical payload. This keeps the fix scoped to LabUtopia task data and the overlay generator. Choose this route.

## Runtime Asset Contract

`standalone_tools/labutopia_poc/build_asset_overlay.py` owns the generated runtime USD and generated manifest.

The overlay must:

- Author one wrapper per top-level runtime object: `obj_conical_bottle02`, `obj_beaker2`, `obj_target_plat`, `obj_DryingBox_01`, and `obj_table`.
- Not author an independent top-level payload for `/World/DryingBox_01/handle`.
- Expose `obj_DryingBox_01_handle` as an articulation part path under the drying-box wrapper.
- Override top-level wrapper translations so required task objects begin in the robot/table workspace:
  - bottle near `[0.28, 0.00, 0.80]`
  - beaker near `[0.27, 0.18, 0.84]`
  - target platform near `[0.26, -0.24, 0.776]`
  - drying box near `[0.75, 0.10, 0.78]`
- Preserve source rotations and source scales unless a test proves they are invalid.
- Author display-color overrides on task-visible meshes so failed MDL bindings do not collapse the scene into flat gray.
- Declare a `render_object_contracts` manifest block with source prim path, wrapper prim path, role, desired runtime translation, expected bbox size range, and display color for every required object and part.

## Task Contract

The three Franka POC YAMLs own task-level render validation metadata:

- `labutopia_render_validation.schema_version = 1`
- `primary_camera = camera2`
- `required_camera_names = [camera1, camera2]`
- `required_visible_objects` exactly matches the task objects
- `reject_frame_if` includes `black_frame`, `low_texture`, `required_object_missing`, and `severe_clipping`
- `evidence_policy.direct_render = false`

`level1_open_door.yml` must additionally declare:

- `object_config.obj_DryingBox_01.type = existed_object`
- `object_config.obj_DryingBox_01.uid_list = [obj_DryingBox_01]`
- `object_config.obj_DryingBox_01.is_articulated = true`
- `object_config.obj_DryingBox_01.articulation_info.is_articulated = true`
- `object_config.obj_DryingBox_01.articulation_info.part.handle = /handle`
- runtime goal uses the preferred joint metric when the joint is available

## Validation Contract

Static validation must fail before Isaac runtime if:

- the generated runtime scene still contains a top-level `obj_obj_DryingBox_01_handle` payload;
- the manifest lacks `render_object_contracts`;
- any required object/part lacks a visible display color;
- any runtime translation is still in the source LabUtopia coordinate band instead of the robot/table workspace;
- `level1_open_door` lacks the articulation config needed to register the handle as an articulation part;
- any Franka task lacks `labutopia_render_validation`;
- camera names in validation metadata do not exist in the configured camera YAML.

## Native DryingBox Extension

The P1 layout work is necessary but not sufficient for native complex `DryingBox_01` acceptance. Native acceptance must additionally fail fast if:

- any native `reference` or `payload` dependency is unresolved;
- required native `material:binding` targets are unresolved and no explicit fallback display policy is recorded;
- `PhysicsScene` is missing or duplicated in the composed runtime stage;
- `PhysicsArticulationRootAPI` is lost after wrapper composition;
- any active joint `physics:body0` or `physics:body1` target lacks `RigidBodyAPI`;
- active rigid bodies have invalid mass, diagonal inertia, center of mass, or principal axes;
- collision shapes become invalid after root scale or wrapper transform composition;
- the door `RevoluteJoint` cannot be distinguished from the button `PrismaticJoint`;
- `open_door` scoring reads the first DOF blindly instead of the verified door joint;
- the required camera/light prims are absent or the reset frame is visible but not task-readable.

The native gate sequence is tracked in `docs/superpowers/plans/2026-06-26-labutopia-native-dryingbox-ebench-gates.md`.

## Runtime Acceptance

P1 is complete only when fresh eval-path diagnostics produce three non-black, visually readable reset frames:

- `level1_pick`: the conical bottle is identifiable.
- `level1_place`: both beaker and target platform are visible in one frame.
- `level1_open_door`: drying box, door face, and handle are visible with the handle under the drying-box hierarchy.

Until all three pass visual review, PM-facing wording must remain: integration and diagnostics are progressing, but final render/layout acceptance is still open.

Native `DryingBox_01` runtime acceptance is stricter than P1 render acceptance. It requires native-only Isaac smoke, additive physics override evidence, eval-path render and state readback, and a claim boundary that still separates Franka/native success from official Lift2 baseline readiness.

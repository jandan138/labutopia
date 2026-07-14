# Real Beaker Static Hold and OmniGlass Reference Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that PhysX PBD particles remain inside the visible `lab_001` source beaker for the required 1024/4096 multi-seed matrix, then render the accepted trajectory with an A18-scaled OmniGlass particle look and ship a standalone USD package.

**Architecture:** Add a small `real_beaker.py` domain module that derives a canonical Z-up cup frame from the composed USD, authors an orientation-correct hidden wrapper, generates canonical controlled spawns, and classifies readback against the visible interior. Add a separate `omniglass_reference.py` presentation module and replay runner so display width and proxy clustering never alter the accepted physics trajectory. Existing fluid runners remain the source for Isaac setup, materials, cameras, and video encoding, with a narrow strict-hold integration path.

**Tech Stack:** Python 3.10, OpenUSD `pxr`, Isaac Sim 4.1, Omni PhysX PBD, OmniGlass MDL, pytest, JSON/JSONL evidence, OpenCV/Isaac camera rendering, `UsdUtils.LocalizeAsset`.

---

## File Map

| Path | Responsibility |
| --- | --- |
| `tools/labutopia_fluid/real_beaker.py` | Canonical cup frame, USD geometry calibration, strict classifier, controlled spawn, corrected wrapper authoring |
| `tools/labutopia_fluid/omniglass_reference.py` | A18 scale metrics, display candidates, deterministic canonical voxel clustering, visual manifest contracts |
| `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py` | Narrow CLI/runtime integration for strict hold and display-width separation |
| `tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py` | Six-cell Isaac orchestration and top-level strict manifest |
| `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py` | Replay one accepted trace into three render-only OmniGlass candidates |
| `tools/labutopia_fluid/run_export_real_beaker_fluid_usd.py` | Export accepted physics setup and selected presentation into a derived USD package |
| `tests/test_real_beaker.py` | Geometry, transform, spawn, wrapper, and strict classifier tests |
| `tests/test_omniglass_reference.py` | Display-width and deterministic visual-proxy tests |
| `tests/test_real_beaker_runtime_contract.py` | CLI, matrix, replay, manifest, and export contracts |

The current worktree contains prior-engineer changes in the main runner. Before every commit, inspect `git diff --cached --name-only`; stage only listed task files and never revert unrelated changes.

## Task 1: Canonical Cup Frame and Calibration

**Files:**
- Create: `tools/labutopia_fluid/real_beaker.py`
- Create: `tests/test_real_beaker.py`

- [ ] **Step 1: Write the rotated-parent failing test**

```python
def test_derive_cup_frame_maps_canonical_z_to_rotated_parent_local_y():
    import pytest
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddTranslateOp().Set(Gf.Vec3d(0.295, 0.075, 0.87))
    cup.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 45.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )

    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path=None,
    )

    assert frame.parent_local_axis == "Y"
    assert frame.z_axis_world == pytest.approx((0.0, 0.0, 1.0), abs=1e-6)
    assert frame.axis_alignment_dot >= 0.999
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python -m pytest tests/test_real_beaker.py::test_derive_cup_frame_maps_canonical_z_to_rotated_parent_local_y -v
```

Expected: import failure because `tools.labutopia_fluid.real_beaker` does not exist.

- [ ] **Step 3: Implement the frame contract and derivation**

Create an immutable contract with JSON-safe serialization and dot-product transforms:

```python
@dataclass(frozen=True)
class CupInteriorFrame:
    origin_world: tuple[float, float, float]
    x_axis_world: tuple[float, float, float]
    y_axis_world: tuple[float, float, float]
    z_axis_world: tuple[float, float, float]
    parent_local_axis: str
    outer_radius: float
    interior_radius: float
    outer_floor: float
    interior_floor: float
    rim_height: float
    calibration_source: str
    axis_alignment_dot: float

    def world_to_canonical(self, point):
        delta = tuple(float(point[i]) - self.origin_world[i] for i in range(3))
        return (
            _dot(delta, self.x_axis_world),
            _dot(delta, self.y_axis_world),
            _dot(delta, self.z_axis_world),
        )

    def canonical_to_world(self, point):
        return tuple(
            self.origin_world[i]
            + float(point[0]) * self.x_axis_world[i]
            + float(point[1]) * self.y_axis_world[i]
            + float(point[2]) * self.z_axis_world[i]
            for i in range(3)
        )
```

`derive_cup_interior_frame` must:

1. compute mesh points in parent-local space from the composed transforms;
2. select the parent axis most aligned with stage up and preserve its sign;
3. construct a right-handed radial basis;
4. derive outer floor/rim/radius in canonical coordinates;
5. use `/World/ParticleSet` initial points when available to calibrate the intended
   radial envelope, while retaining the visible mesh floor as the support plane;
6. compute and record the explicit outer-to-calibrated wall clearance, clamp the
   envelope below the visual outer radius, and apply spawn/contact clearance later
   without changing the shared frame;
7. when authored calibration points are missing, use the conservative inscribed
   parent-relative mesh radius minus a recorded `0.005 m` fallback wall clearance;
8. record raw envelope, applied/fallback clearances, final radius, and all geometry
   measurements through `as_dict()`.

The canonical origin uses the radial midpoint of the parent-relative visual mesh at
its minimum axial coordinate. Calibration particles may refine the intended interior
radius but must not move that visible-floor origin. Record the exact parent-relative
mesh min/max/size in the serialized calibration block so the implementation cannot
silently regress to an inverse-transformed world-aligned AABB.

- [ ] **Step 4: Add real-scene calibration assertions**

```python
def test_real_lab001_frame_uses_local_y_and_original_fluid_calibration():
    from pathlib import Path
    import pytest
    from pxr import Usd
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    scene_path = Path(
        "outputs/usd_asset_packages/lab_001_localized_20260707/"
        "lab_001_level1_pour_tabletop_with_liquid.usd"
    )
    assert scene_path.is_file(), f"required localized scene is missing: {scene_path}"
    stage = Usd.Stage.Open(str(scene_path))
    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path="/World/ParticleSet",
    )
    assert frame.parent_local_axis == "Y"
    assert frame.z_axis_world == pytest.approx((0.0, 0.0, 1.0), abs=1e-6)
    assert frame.outer_radius == pytest.approx(0.037666, abs=0.001)
    assert frame.interior_radius == pytest.approx(0.0330, abs=0.002)
    assert frame.calibration_source == "authored_particle_bounds"
```

Add a regression assertion on `frame.as_dict()["parent_local_mesh_bounds"]`:

```python
assert frame.as_dict()["parent_local_mesh_bounds"]["size"] == pytest.approx(
    (0.0811547, 0.0904004, 0.0753325),
    abs=1e-5,
)
```

This measured size is the direct composed mesh-to-parent result; the test must fail
if an implementation inverse-transforms a world-aligned bounding box.

- [ ] **Step 5: Run Task 1 tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_real_beaker.py -v -k 'frame or calibration'
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add tools/labutopia_fluid/real_beaker.py tests/test_real_beaker.py
git commit -m "feat(fluid): derive canonical real beaker frame"
```

## Task 2: Strict Visible-Interior Classifier and Canonical Spawn

**Files:**
- Modify: `tools/labutopia_fluid/real_beaker.py`
- Modify: `tests/test_real_beaker.py`

- [ ] **Step 1: Write classifier RED tests**

```python
def test_strict_classifier_rejects_below_floor_and_outside_radius(real_frame):
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_positions

    inside = real_frame.canonical_to_world((0.0, 0.0, real_frame.interior_floor + 0.01))
    below = real_frame.canonical_to_world((0.0, 0.0, real_frame.interior_floor - 0.001))
    outside = real_frame.canonical_to_world((real_frame.interior_radius + 0.001, 0.0, 0.03))
    result = classify_visible_beaker_positions([inside, below, outside], real_frame)
    assert result["inside_visible_interior_count"] == 1
    assert result["below_visible_floor_count"] == 1
    assert result["outside_visible_radial_count"] == 1


def test_old_false_pass_trace_fails_strict_visible_gate():
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_trace_from_files

    result = classify_visible_beaker_trace_from_files(
        manifest_path="docs/labutopia_lab_poc/evidence_manifests/"
        "fluid_spike_full_scene_controlled_spawn_hold_20260710_P4096.json"
    )
    assert result["classification"] == "FAIL_VISIBLE_BEAKER_CONTAINMENT"
    assert result["below_visible_floor_count"] >= 3926
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
python -m pytest tests/test_real_beaker.py -v -k 'strict_classifier or old_false_pass'
```

Expected: missing classifier functions.

- [ ] **Step 3: Implement strict counts and trace classification**

Implement `classify_visible_beaker_positions`, `classify_visible_beaker_trace`,
`classify_visible_beaker_trace_from_files`, and `strict_static_hold_pass`. The file helper
opens the manifest's immutable source USD, derives the same frame, loads every JSONL
record from `trace_path`, and delegates to the in-memory classifier. Use these exact
hard conditions:

```python
passed = (
    final_count > 0
    and final_count / initial_count >= 0.95
    and max_below_floor == 0
    and max_outside_radius == 0
    and max_above_rim == 0
    and final_inside == final_count
    and nonfinite_count == 0
    and tail_leak_rate == 0.0
    and not particle_explosion_detected
    and diagnostic_scan_complete
    and not cpu_collision_fallback_detected
    and not gpu_collider_unsupported
    and fatal_error is None
)
```

`validate_strict_trace_schema` must run before classification and require:

- nonempty records with unique, strictly increasing step indices exactly matching
  `0`, the configured cadence, and the final step;
- `particle_count == len(positions)` in every record, initial count equal to the
  requested count, and every count in `(0, initial_count]`;
- `finite_count + nonfinite_count == particle_count`, where `nonfinite_count` uses
  `math.isfinite` and therefore rejects both NaN and positive/negative infinity;
- frame-index/count vectors, source USD SHA-256, count/seed/steps/cadence, ordered
  position payload `positions_sha256`, and combined identity
  `physical_trace_sha256` captured in one
  `physical_trace_identity` contract.

Containment is set-based, so point reordering cannot create a containment pass; the
ordered payload hash still makes any replay reordering detectable. A missing or
invalid record returns `STOP_INCOMPLETE_TRACE`, never a partial pass.

Every per-frame classifier record must include
`inside_visible_interior_count`, `below_visible_floor_count`,
`outside_visible_radial_count`, `above_visible_rim_count`, diagnostic-only
`legacy_source_region_count`, canonical axial min/median/max, maximum canonical
radius, finite/nonfinite counts, and strict violating-point count.

Derive `tail_leak_rate` from the strict violating-point counts over the configured
tail window. Derive `particle_explosion_detected` from nonfinite points or any point
outside a recorded conservative world/canonical safety envelope at least ten times
the cup dimensions; do not infer particle identity from array order. Derive CPU
fallback and unsupported GPU collider booleans from the
run-scoped Kit log, and `fatal_error` from the runtime exception path. Set
`diagnostic_scan_complete=true` only after the run-scoped log was found and scanned;
missing diagnostics must return `STOP_INCOMPLETE_DIAGNOSTICS` rather than defaulting
booleans to false.

Return `PASS_VISIBLE_BEAKER_STATIC_HOLD` only when `passed` is true; otherwise return
`FAIL_VISIBLE_BEAKER_CONTAINMENT` or the specific fatal/readback/incomplete-evidence
classification.

- [ ] **Step 4: Write canonical spawn RED test**

```python
import pytest


@pytest.mark.parametrize(
    ("particle_count", "particle_width", "particle_contact_offset"),
    ((1024, 0.0006, 0.00054), (4096, 0.00045, 0.0005)),
)
def test_canonical_spawn_is_inside_real_visible_interior(
    real_frame,
    particle_count,
    particle_width,
    particle_contact_offset,
):
    from tools.labutopia_fluid.fluid_recipe import build_controlled_spawn_plan
    from tools.labutopia_fluid.real_beaker import (
        build_visible_beaker_spawn,
        classify_visible_beaker_positions,
    )

    spawn = build_visible_beaker_spawn(
        real_frame,
        build_controlled_spawn_plan(particle_count, particle_seed=0),
        physics_particle_width=particle_width,
        particle_contact_offset=particle_contact_offset,
    )
    counts = classify_visible_beaker_positions(spawn.positions_world, real_frame)
    assert len(spawn.positions_world) == particle_count
    assert counts["inside_visible_interior_count"] == particle_count
    assert counts["below_visible_floor_count"] == 0
    assert counts["outside_visible_radial_count"] == 0
    assert counts["above_visible_rim_count"] == 0
    assert spawn.canonical_bounds["max"][2] < real_frame.rim_height
    assert set(spawn.velocities_world) == {(0.0, 0.0, 0.0)}
```

- [ ] **Step 5: Implement canonical spawn**

Build the existing radial lattice in canonical coordinates using a `ColliderConfig`
centered at `(0, 0, interior_floor)`, enforce radial/contact clearances, then
transform every point with `frame.canonical_to_world`. The legacy layout's 4/16
axial layers are insufficient after correcting the old inflated `~55 mm` radius to
the real `~32 mm` interior. Count lattice candidates per layer, compute the minimum
deterministic axial layer count that can hold the requested population, and fail
before runtime if the resulting top center plus clearance reaches the rim. Preserve
the existing 4.5/3.0 mm radial/axial spacing; do not increase radius or silently
shrink spacing to obtain capacity. The current geometry should derive about 11
layers for 1024 and 22 for 4096, both within the measured cup height. Return a
`VisibleBeakerSpawn` contract containing positions, physics offsets, canonical
bounds, zero world velocities, seed, count, derived layer count/capacity, and hash.

- [ ] **Step 6: Run Task 2 tests and full pure suite**

```bash
python -m pytest tests/test_real_beaker.py tests/test_full_scene_spawn_frame.py tests/test_fluid_recipe.py -v
```

Expected: all tests pass; the historical false-pass trace is classified as failure by the new gate.

- [ ] **Step 7: Commit Task 2**

```bash
git add tools/labutopia_fluid/real_beaker.py tests/test_real_beaker.py
git commit -m "feat(fluid): enforce visible beaker containment"
```

## Task 3: Orientation-Correct GPU-Native Wrapper

**Files:**
- Modify: `tools/labutopia_fluid/real_beaker.py`
- Modify: `tests/test_real_beaker.py`

- [ ] **Step 1: Write wrapper alignment RED test**

```python
def test_real_wrapper_bottom_is_horizontal_and_tracks_cup_axis(real_stage, real_frame):
    from pxr import UsdGeom
    from tools.labutopia_fluid.real_beaker import author_canonical_fluid_wrapper

    summary = author_canonical_fluid_wrapper(
        real_stage,
        frame=real_frame,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        panel_count=72,
        panel_ring_count=2,
        wall_thickness=0.026,
        bottom_thickness=0.012,
        bottom_overlap=0.018,
    )
    assert summary["bottom_axis_alignment_dot"] >= 0.999
    assert abs(summary["support_plane_error_m"]) <= 0.001
    bottom = real_stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapperCanonical/Bottom")
    assert UsdGeom.Imageable(bottom).ComputeVisibility() == UsdGeom.Tokens.invisible
    assert summary["bottom_world_extent_z"] < summary["bottom_world_extent_x"] * 0.25
    assert summary["bottom_world_extent_z"] < summary["bottom_world_extent_y"] * 0.25
```

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest tests/test_real_beaker.py::test_real_wrapper_bottom_is_horizontal_and_tracks_cup_axis -v
```

Expected: missing `author_canonical_fluid_wrapper`.

- [ ] **Step 3: Implement canonical child transform and colliders**

Author `/World/beaker2/FluidSafeWrapperCanonical` with one transform translating to
the frame's visible-floor center in parent space and mapping canonical Z to the
derived parent-local cup axis. Under it author:

- one box bottom whose top is `frame.interior_floor`;
- two phase-offset rings of 72 box panels;
- inner face at `frame.interior_radius`;
- wall range from support plane minus overlap to rim;
- PhysX collision enabled, `contactOffset=0.004`, `restOffset=0`;
- native visual mesh collision disabled;
- `purpose=proxy`, visibility invisible, and `labutopia:*` frame metadata.

Compute the world normal from the authored bottom transform and fail authoring if alignment or support-plane assertions do not hold.

- [ ] **Step 4: Run wrapper tests**

```bash
python -m pytest tests/test_real_beaker.py -v -k 'wrapper or frame'
```

Expected: all pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add tools/labutopia_fluid/real_beaker.py tests/test_real_beaker.py
git commit -m "fix(fluid): align wrapper with real beaker axis"
```

## Task 4: Strict-Hold Runtime Integration

**Files:**
- Modify: `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`
- Create: `tests/test_real_beaker_runtime_contract.py`

- [ ] **Step 1: Write CLI/runtime contract RED tests**

```python
def test_parser_exposes_real_beaker_static_hold_mode():
    args = build_arg_parser().parse_args(["--real-beaker-static-hold"])
    assert args.real_beaker_static_hold is True


def test_strict_hold_summary_requires_visible_classifier():
    summary = build_real_beaker_summary_contract(
        visible_classification={
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "trace_schema_valid": True,
            "diagnostic_scan_complete": True,
            "physical_trace_identity": {"physical_trace_sha256": "a" * 64},
        },
        frame={"axis_alignment_dot": 1.0},
        physics_offsets={"particle_width": 0.00045},
        display_particle_width=0.0043,
    )
    assert summary["visible_beaker_containment_verified"] is True
    assert summary["physics_particle_offsets"]["particle_width"] == 0.00045
    assert summary["display_particle_width"] == 0.0043


def test_strict_hold_summary_rejects_incomplete_diagnostics():
    summary = build_real_beaker_summary_contract(
        visible_classification={
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "trace_schema_valid": True,
            "diagnostic_scan_complete": False,
        },
        frame={"axis_alignment_dot": 1.0},
        physics_offsets={"particle_width": 0.00045},
        display_particle_width=0.0043,
    )
    assert summary["visible_beaker_containment_verified"] is False
```

Before implementation, also add a RED authoring test with monkeypatched
`particleUtils`/`physicsUtils` capture fakes. Call
`_author_completed_pbd_runtime_particles` with physics width `0.00045` and display
width `0.0043`; assert the particle-system contact/rest arguments retain the physics
values and the captured `add_physx_particleset_points` widths are all `0.0043`.

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest tests/test_real_beaker_runtime_contract.py -v
```

Expected: parser option and summary helper are missing.

- [ ] **Step 3: Add the narrow runtime branch**

When `--real-beaker-static-hold` is set:

1. derive `CupInteriorFrame` before original particles are deactivated;
2. create canonical controlled spawn for `--controlled-spawn-count/seed`;
3. author `FluidSafeWrapperCanonical` instead of the legacy wrapper;
4. author PhysX offsets independently from `display_particle_width`;
5. append strict visible counts to every trace record;
6. classify with `classify_visible_beaker_trace`;
7. validate exact trace cadence/schema and emit `physical_trace_identity`;
8. scan only the current run's Kit log segment and emit complete diagnostic
   provenance rather than default-pass booleans;
9. emit `cup_interior_frame`, `canonical_wrapper`, `strict_visible_classification`,
   physics/display parameters, and claim-boundary fields;
10. force source closeup capture in addition to the tabletop presentation camera.

Add CLI options:

```text
--real-beaker-static-hold
--display-particle-width FLOAT
```

Default behavior for all existing callers remains unchanged. Strict mode reuses the
existing `--trace-interval` option and rejects values above 30; it does not add a
second cadence option.

Extend `_author_completed_pbd_runtime_particles` with an optional
`display_particle_width: float | None = None`. Particle-system offsets continue to
come exclusively from `widths`; point widths use `display_particle_width` when
provided and otherwise preserve the legacy `widths["particle_width"]` behavior.

- [ ] **Step 4: Run focused and regression tests**

```bash
python -m pytest \
  tests/test_real_beaker_runtime_contract.py \
  tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py \
  tests/test_fluid_beaker_collider_smoke.py \
  -v
```

Expected: all pass.

- [ ] **Step 5: Review dirty-file diff before commit**

```bash
git diff -- tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py
git diff --check
```

Confirm no prior-engineer lines were reverted and no unrelated file is staged.

- [ ] **Step 6: Commit Task 4**

```bash
git add \
  tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py \
  tests/test_real_beaker_runtime_contract.py
git commit -m "feat(fluid): integrate strict real beaker hold"
```

## Task 5: Six-Cell Static-Hold Matrix

**Files:**
- Create: `tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py`
- Modify: `tests/test_real_beaker_runtime_contract.py`

- [ ] **Step 1: Write matrix RED tests**

```python
def test_static_hold_matrix_has_required_six_cells():
    cells = static_hold_cells(counts=(1024, 4096), seeds=(0, 1, 2))
    assert [(c["particle_count"], c["seed"]) for c in cells] == [
        (1024, 0), (1024, 1), (1024, 2),
        (4096, 0), (4096, 1), (4096, 2),
    ]


def test_matrix_command_pins_600_steps_and_strict_mode(tmp_path):
    argv = build_cell_argv(static_hold_cells()[0], out_dir=tmp_path)
    assert "--real-beaker-static-hold" in argv
    assert argv[argv.index("--steps") + 1] == "600"
```

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest tests/test_real_beaker_runtime_contract.py -v -k matrix
```

Expected: matrix module missing.

- [ ] **Step 3: Implement orchestration and fail-fast**

The runner must:

- run 1024 seeds first;
- stop before 4096 if any 1024 cell is not `PASS_VISIBLE_BEAKER_STATIC_HOLD`;
- execute 600 logical steps at `1/60 s` each, with 10 explicit direct PhysX
  integration substeps at `1/600 s` per logical step (6,000 exact
  `simulate`/`fetch_results` pairs, 10 simulated seconds total), and keep the
  logical trace interval at most 30;
- set the per-cell runtime timeout to at least 900 seconds because two-camera RTX
  capture can exceed the legacy 300-second timeout;
- retain stdout/stderr, per-cell summary, trace, scene overlay, closeup/context frames, and videos;
- write a top manifest whose `real_beaker_static_hold_closed` is true only when all six required cells pass;
- list the immutable 2026-07-10 manifests as superseded false-positive evidence
  without modifying or deleting them.

Expose `--counts`, `--seeds`, `--steps`, `--out-root`, `--manifest`, `--append`,
`--headless`, and `--dry-plan`. `static_hold_cells` defaults to counts `(1024, 4096)`
and seeds `(0, 1, 2)`. Every top-manifest cell records `particle_count`, `seed`,
`summary_path`, `trace_path`, `classification`, and artifact hashes so later steps can
select an accepted trace without guessing a directory name. Record the exact child
command, source USD SHA-256, current Git commit and dirty-diff SHA-256, Python/Isaac
versions, and physics/display parameters. On `--append`, require these run-identity
fields to match, reject duplicate count/seed cells, and require all three accepted
1024 cells before launching any 4096 cell.

- [ ] **Step 4: Run dry-plan test**

```bash
python tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py --dry-plan
```

Expected: JSON containing six cells and no Isaac launch.

- [ ] **Step 5: Commit Task 5**

```bash
git add \
  tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py \
  tests/test_real_beaker_runtime_contract.py
git commit -m "feat(fluid): orchestrate strict static hold matrix"
```

## Task 6: OmniGlass Reference Proxy and Replay

**Files:**
- Create: `tools/labutopia_fluid/omniglass_reference.py`
- Create: `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- Create: `tests/test_omniglass_reference.py`
- Modify: `tests/test_real_beaker_runtime_contract.py`

- [ ] **Step 1: Write candidate/voxel RED tests**

```python
import pytest
from pxr import Usd

from tools.labutopia_fluid.omniglass_reference import (
    author_presentation_points,
    build_reference_candidates,
    voxel_cluster_world_positions,
)


def test_reference_candidates_scale_from_interior_diameter():
    candidates = build_reference_candidates(interior_diameter=0.064)
    assert candidates["OMNI_REF_RATIO_15"]["display_width"] == pytest.approx(0.064 / 15)
    assert candidates["OMNI_REF_RATIO_12"]["display_width"] == pytest.approx(0.064 / 12)


def test_voxel_proxy_is_deterministic_and_render_only(real_frame):
    points = [
        real_frame.canonical_to_world((0.001, 0.001, 0.02)),
        real_frame.canonical_to_world((0.0015, 0.0015, 0.0205)),
        real_frame.canonical_to_world((0.010, 0.010, 0.03)),
    ]
    a = voxel_cluster_world_positions(points, frame=real_frame, voxel_size=0.004)
    b = voxel_cluster_world_positions(list(reversed(points)), frame=real_frame, voxel_size=0.004)
    assert a == b
    assert len(a) == 2


def test_presentation_points_have_no_physx_schema():
    stage = Usd.Stage.CreateInMemory()
    prim = author_presentation_points(
        stage,
        path="/World/CompletedPBD/PresentationParticleSet",
        positions=[(0.0, 0.0, 0.02)],
        display_width=0.004,
        material_path=None,
    )
    assert prim.GetTypeName() == "Points"
    assert not any("Physx" in token for token in prim.GetAppliedSchemas())
    assert not prim.HasRelationship("physxParticle:particleSystem")
```

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest tests/test_omniglass_reference.py -v
```

Expected: module missing.

- [ ] **Step 3: Implement candidates and deterministic clustering**

Sort occupied canonical voxel keys lexicographically, sort canonical points within
each bucket before averaging, and transform centroids back to world. Return proxy
count, width, width/interior ratio, and source physical-point count. Keep the A18
color constants in `presentation_look_profiles.py` as the material source of truth.
Define `OMNI_REF_FINE` deterministically as
`clamp(interior_diameter / 32, 0.0015, 0.0020)` and use each candidate's display
width as its canonical voxel size unless the manifest explicitly records another
value.

- [ ] **Step 4: Write replay contract RED test**

```python
def test_replay_argv_requires_accepted_trace_and_three_candidates(tmp_path):
    args = build_arg_parser().parse_args([
        "--accepted-summary", str(tmp_path / "summary.json"),
        "--out-root", str(tmp_path / "renders"),
    ])
    assert args.accepted_summary.endswith("summary.json")
    assert args.candidates == "OMNI_REF_FINE,OMNI_REF_RATIO_15,OMNI_REF_RATIO_12"
```

- [ ] **Step 5: Implement render-only replay**

The replay runner must:

1. reject summaries that are not `PASS_VISIBLE_BEAKER_STATIC_HOLD`, have invalid
   trace schema, or lack complete run-scoped diagnostics;
2. read the accepted trace once, recompute its full `physical_trace_identity`, and
   require exact equality with the accepted summary;
3. open the same localized lab scene without stepping PhysX;
4. hide original/physical debug points;
5. author `/World/CompletedPBD/PresentationParticleSet` without PhysX particle APIs;
6. update proxy points and widths for each recorded frame;
7. bind A18 OmniGlass colors, beaker override, closeup, and context cameras;
8. render all three candidates from the exact same trace;
9. assert the complete input identity is identical in every candidate manifest:
   source USD hash, count/seed/steps/cadence, frame-index vector, per-frame count
   vector, frame count, `positions_sha256`, and `physical_trace_sha256`;
10. export a static candidate USD whose default presentation points use the final
    accepted/settled trace frame; record that frame index separately from the hidden
    physical initial-state points.

- [ ] **Step 6: Run pure tests and dry-plan**

```bash
python -m pytest tests/test_omniglass_reference.py tests/test_real_beaker_runtime_contract.py -v
python tools/labutopia_fluid/run_real_beaker_omniglass_replay.py \
  --accepted-summary DRY_PLAN_ACCEPTED_SUMMARY_NOT_READ \
  --dry-plan
```

Expected: tests pass; dry plan prints candidate contracts without opening Isaac or
reading the sentinel summary path. Non-dry execution validates and rejects missing or
non-accepted summaries before booting Isaac.

- [ ] **Step 7: Commit Task 6**

```bash
git add \
  tools/labutopia_fluid/omniglass_reference.py \
  tools/labutopia_fluid/run_real_beaker_omniglass_replay.py \
  tests/test_omniglass_reference.py \
  tests/test_real_beaker_runtime_contract.py
git commit -m "feat(fluid): replay A18-scaled OmniGlass particles"
```

## Task 7: Accepted USD Export and Package Closure

**Files:**
- Create: `tools/labutopia_fluid/run_export_real_beaker_fluid_usd.py`
- Modify: `tests/test_real_beaker_runtime_contract.py`

- [ ] **Step 1: Write export RED tests**

```python
import pytest

from tools.labutopia_fluid.run_export_real_beaker_fluid_usd import (
    export_real_beaker_fluid_usd,
)


def _accepted_export_contract(trace_hash="a" * 64):
    identity = {
        "physical_trace_sha256": trace_hash,
        "source_usd_sha256": "b" * 64,
        "particle_count": 4096,
        "seed": 0,
        "steps": 600,
        "trace_interval": 30,
        "frame_indices": list(range(0, 601, 30)),
        "frame_particle_counts": [4096] * 21,
        "frame_count": 21,
        "positions_sha256": "c" * 64,
    }
    accepted = {
        "strict_visible_classification": {
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "trace_schema_valid": True,
            "diagnostic_scan_complete": True,
        },
        "physical_trace_identity": identity,
        "physics_particle_offsets": {"particle_width": 0.00045},
        "source_usd_sha256": identity["source_usd_sha256"],
    }
    selected = {
        "visual_review_verdict": "PASS",
        "physical_trace_identity": identity,
        "display_particle_width": 0.0043,
        "candidate_id": "OMNI_REF_RATIO_15",
    }
    return accepted, selected


def test_export_requires_accepted_physics_and_selected_visual(tmp_path):
    accepted, selected = _accepted_export_contract()
    accepted["strict_visible_classification"]["classification"] = (
        "FAIL_VISIBLE_BEAKER_CONTAINMENT"
    )
    with pytest.raises(ValueError, match="accepted_static_hold_required"):
        export_real_beaker_fluid_usd(
            accepted_summary=accepted,
            selected_visual=selected,
            out_dir=tmp_path,
        )


def test_export_rejects_visual_trace_identity_mismatch(tmp_path):
    accepted, selected = _accepted_export_contract()
    selected["physical_trace_identity"] = {
        **selected["physical_trace_identity"],
        "physical_trace_sha256": "d" * 64,
    }
    with pytest.raises(ValueError, match="visual_trace_identity_mismatch"):
        export_real_beaker_fluid_usd(
            accepted_summary=accepted,
            selected_visual=selected,
            out_dir=tmp_path,
            dry_run=True,
        )


def test_export_claims_separate_physics_and_display(tmp_path):
    accepted, selected = _accepted_export_contract()
    result = export_real_beaker_fluid_usd(
        accepted_summary=accepted,
        selected_visual=selected,
        out_dir=tmp_path,
        dry_run=True,
    )
    assert result["physics_and_display_parameters_separated"] is True
    assert result["visible_beaker_containment_verified"] is True
```

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest tests/test_real_beaker_runtime_contract.py -v -k export
```

Expected: export module missing.

- [ ] **Step 3: Implement accepted export**

Export only when:

- an accepted 1024 or 4096 strict summary is supplied;
- selected visual review is `PASS` or explicitly accepted `WARN`;
- source USD hash matches the accepted run;
- selected visual `physical_trace_identity` exactly equals the accepted summary's
  complete identity contract;
- physics offsets and display width are both present.

The derived stage must contain:

- the real localized lab scene;
- `FluidSafeWrapperCanonical`;
- accepted initial physical particle set and PBD particle system;
- selected static `PresentationParticleSet` and OmniGlass material;
- hidden physical points for presentation;
- metadata linking strict manifest, trace hash, visual candidate, and claim boundary.

Write to:

```text
outputs/usd_asset_packages/lab_001_real_beaker_fluid_v1/
  lab_001_level1_pour_real_beaker_fluid_v1.usd
  package_manifest.json
  README_REAL_BEAKER_FLUID.md
  _reports/
```

Use `UsdUtils.LocalizeAsset` into a temporary sibling directory, then atomically rename the completed package. Verify a clean-copy open with no absolute dependency on the original localized package.

Implement `verify_real_beaker_package(entry_usd)` plus CLI option
`--verify-only ENTRY_USD`. It opens with `Usd.Stage.LoadAll`, walks asset-valued
attributes and layer dependencies, checks required prims and schemas, and emits a
JSON report. In CLI verification mode, boot Isaac headless, open only the copied
stage, initialize one RTX camera frame so MDL/textures are resolved, and scan the
run-scoped Kit log for unresolved asset, MDL, texture, and shader errors. Any
unresolved dependency, original-package absolute path, missing required prim, or
material-resolution error makes the command exit nonzero. Then step the copied PBD
setup for five physics updates, read back the hidden physical set, and require a
positive finite count plus strict visible-interior containment; this is package-open
smoke evidence only and does not replace the accepted 600-step matrix.

- [ ] **Step 4: Run export tests**

```bash
python -m pytest tests/test_real_beaker_runtime_contract.py -v -k export
```

Expected: all pass.

- [ ] **Step 5: Commit Task 7**

```bash
git add \
  tools/labutopia_fluid/run_export_real_beaker_fluid_usd.py \
  tests/test_real_beaker_runtime_contract.py
git commit -m "feat(fluid): export accepted real beaker USD"
```

## Task 8: Live Evidence, Visual Review, and Completion Audit

**Files:**
- Modify: `docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_*.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_omniglass_reference_*.json`
- Create: package and render artifacts under `outputs/` and evidence directories

- [ ] **Step 1: Run the 1024 matrix**

Start both matrix phases with one run identity so `--append` updates the same top
manifest:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
MATRIX_ROOT="docs/labutopia_lab_poc/evidence_manifests/real_beaker_static_hold_${RUN_ID}"
TOP_MANIFEST="docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_${RUN_ID}.json"
ISAAC_PYTHON="/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
test -x "$ISAAC_PYTHON"

ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
"$ISAAC_PYTHON" \
tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py \
  --counts 1024 --seeds 0,1,2 --steps 600 --headless \
  --out-root "$MATRIX_ROOT" --manifest "$TOP_MANIFEST"
```

Required: all three cells classify `PASS_VISIBLE_BEAKER_STATIC_HOLD`. If any fail,
do not launch 4096 yet: inspect the first violating trace step, form one hypothesis,
add a failing regression test, change one parameter or geometry fact only, and rerun
the affected 1024 cells until the gate closes.

- [ ] **Step 2: Run the 4096 matrix**

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
"$ISAAC_PYTHON" \
tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py \
  --counts 4096 --seeds 0,1,2 --steps 600 --headless --append \
  --out-root "$MATRIX_ROOT" --manifest "$TOP_MANIFEST"
```

Required: all three cells pass and the top manifest records all six accepted cells.

- [ ] **Step 3: Replay the best accepted trace**

Prefer an accepted 4096 summary; if none exists during an intermediate visual-debug
iteration, select an accepted 1024 summary and require the replay manifest to record
that limitation. The overall completion gate still requires all six cells.

```bash
ACCEPTED_SUMMARY="$(
python - "$TOP_MANIFEST" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
matches = sorted(
    (
        -cell["particle_count"],
        cell["seed"],
        cell["summary_path"],
    )
    for cell in manifest["cells"]
    if cell["particle_count"] in (1024, 4096)
    and cell["classification"] == "PASS_VISIBLE_BEAKER_STATIC_HOLD"
)
if not matches:
    raise SystemExit("no accepted strict summary in top manifest")
print(matches[0][2])
PY
)"
VISUAL_ROOT="docs/labutopia_lab_poc/evidence_manifests/real_beaker_omniglass_reference_${RUN_ID}"

ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
"$ISAAC_PYTHON" \
tools/labutopia_fluid/run_real_beaker_omniglass_replay.py \
  --accepted-summary "$ACCEPTED_SUMMARY" \
  --out-root "$VISUAL_ROOT" \
  --manifest "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_omniglass_reference_${RUN_ID}.json"
```

Use the actual accepted summary path emitted by the matrix. Required: all candidate
manifests share the complete `physical_trace_identity`, not only one hash field.

- [ ] **Step 4: Run blind visual review**

Apply `render-visual-reviewer` with anonymous labels for closeup and context images.
Select a candidate only when liquid is visibly inside the real source beaker; bead
scale resembles A18 without foam-like overdraw; there is no black/metallic fallback,
severe refraction noise, or detached cloud; glass wall, rim, and liquid remain
distinguishable; and both views are correctly framed and useful.
Preserve the independent verdict and selected candidate contract at
`$VISUAL_ROOT/selected_visual_manifest.json`; set `SELECTED_VISUAL` to that path for
the export step.

- [ ] **Step 5: Export and clean-copy verify the package**

```bash
SELECTED_VISUAL="$VISUAL_ROOT/selected_visual_manifest.json"

"$ISAAC_PYTHON" tools/labutopia_fluid/run_export_real_beaker_fluid_usd.py \
  --accepted-summary "$ACCEPTED_SUMMARY" \
  --selected-visual "$SELECTED_VISUAL" \
  --out-dir outputs/usd_asset_packages/lab_001_real_beaker_fluid_v1
```

Copy the package into a fresh temporary directory and verify only that copy:

```bash
CLEAN_DIR="$(mktemp -d /tmp/lab001_real_beaker_clean_verify.XXXXXX)"
cp -a outputs/usd_asset_packages/lab_001_real_beaker_fluid_v1/. "$CLEAN_DIR/"
"$ISAAC_PYTHON" tools/labutopia_fluid/run_export_real_beaker_fluid_usd.py \
  --verify-only "$CLEAN_DIR/lab_001_level1_pour_real_beaker_fluid_v1.usd"
```

Required: no unresolved USD asset, texture, or MDL dependency and the stage contains
the corrected wrapper, physical particles, and selected presentation points.

- [ ] **Step 6: Run full verification**

```bash
python -m pytest \
  tests/test_real_beaker.py \
  tests/test_omniglass_reference.py \
  tests/test_real_beaker_runtime_contract.py \
  tests/test_fluid_beaker_collider_smoke.py \
  tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py \
  tests/test_full_scene_spawn_frame.py \
  tests/test_fluid_recipe.py \
  -v
git diff --check
```

Required: zero test failures and no whitespace errors.

- [ ] **Step 7: Update evidence docs honestly**

Record:

- old 2026-07-10 P1024/P4096 manifests are false-positive regression evidence;
- strict six-cell result and paths;
- selected OmniGlass candidate, physical trace hash, and visual verdict;
- package path and clean-copy verification;
- blocked claims for tilt, pour, benchmark, and photoreal water.

- [ ] **Step 8: Request final code and evidence review**

Use `superpowers:requesting-code-review` for implementation/spec compliance and a separate evidence reviewer for the six-cell matrix, trace hashes, visual verdict, and package closure. Address all blocking findings and rerun the affected verification commands.

- [ ] **Step 9: Commit tracked evidence and documentation**

```bash
git add \
  docs/labutopia_lab_poc/true_physx_pbd_fluid_spike.md \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_*.json \
  docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_omniglass_reference_*.json
git commit -m "docs(fluid): close real beaker hold and OmniGlass review"
```

## Completion Gate

The objective is complete only when all of the following are evidenced in the current workspace:

- six required 10-second cells pass `PASS_VISIBLE_BEAKER_STATIC_HOLD`;
- zero recorded particles are below the visible floor, outside the visible interior, or above the rim;
- wrapper axis/support alignment passes authored and runtime checks;
- visual candidates use one accepted physical trace hash;
- selected OmniGlass candidate passes visual review in closeup and context views;
- standalone package opens from a clean copy with no unresolved dependencies;
- focused/full tests pass;
- docs supersede the old false-positive claim and preserve blocked claims.

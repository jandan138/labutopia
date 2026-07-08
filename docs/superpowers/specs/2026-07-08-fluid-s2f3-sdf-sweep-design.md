# Fluid S2F3 SDF Sweep Design

## Goal

Complete `S2F3_C3_SDF_SWEEP` as a bounded diagnostic stage for the True PhysX/PBD Fluid Spike. The stage tests whether an open concave SDF beaker collider can hold PBD particles in the IsaacSim41 / EBench target runtime after the C2-derived promotion review failed.

## Scope

S2F3 verifies static source-container hold only. It does not run robot pouring, does not release `S3_KINEMATIC_POUR` directly, and does not make EBench score or policy claims.

The stage must produce:

- A reusable `C3A_*` candidate builder.
- Plan-only and live CLI support through `tools/labutopia_fluid/run_beaker_collider_followup_sweep.py`.
- Per-candidate evidence using the existing variant runtime path: `variant_summary.json`, `particle_readback_trace.jsonl`, `physics_scene_settings.json`, three frames, and two diagnostic overlays.
- A stage manifest at `docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json`.
- Updated PM-facing and evidence documents that explain whether SDF can proceed to a promotion review or why it remains blocked.

## Design

Reuse the current follow-up runner instead of adding a separate S2F3 script. S2F3 candidates are still runtime variants, but they differ from C2 proxy candidates in collision route and SDF cooking parameters. The implementation adds SDF-specific fields to the existing candidate/config/spec flow while preserving old C2/S2F2/S2F5 behavior.

`C3A_*` candidates sweep the required SDF variables:

- `sdf_resolution`: `64`, `96`, `128`
- `sdf_subgrid_resolution`: `4`, `8`
- `sdf_margin`: `0.002`, `0.005`
- `sdf_narrow_band_thickness`: `0.01`, `0.02`
- `mesh_bottom_fan_closure`: `true`
- `normals_winding_audit`: `pass`

The full grid is 24 candidates. The runner may accept `--candidate-limit` for local smoke and plan checks, but completion evidence for S2F3 must state whether the full grid ran or whether the run stopped early because every attempted candidate hit a blocking warning or runtime failure.

## Stage Decision

If one or more C3A candidates pass the strict static hold contract and runtime warning gate, S2F3 returns `GO_NEXT`, records them in `best_for_s2f5`, keeps `best_for_s3=[]`, and points `next_stage.id` to `S2F5_PROMOTION_REVIEW`.

If no C3A candidate passes, S2F3 returns `STOP_WITH_EVIDENCE`, records `best_for_s2f5=[]`, keeps `best_for_s3=[]`, and points `next_stage.id` to `S2F4_C4_NATIVE_MESH_ISOLATION`.

Blocking runtime warnings include CPU collision fallback, GPU unsupported, PhysX errors, SDF cooking errors, and perf budget violations. Headless display warnings remain non-blocking.

## Testing

Tests cover the candidate grid, candidate materialization into `ColliderConfig` and `VariantSpec`, manifest next-stage behavior, plan-only CLI output, and artifact summary loading for `C3A_*` directories.

Runtime verification uses the IsaacSim41 / GenManip conda environment:

```bash
ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES /cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python tools/labutopia_fluid/run_beaker_collider_followup_sweep.py --phase S2F3_C3_SDF_SWEEP --steps 240 --headless
```

## Product Claim Boundary

Allowed claim after completion: S2F3 has tested the SDF beaker-collider route in the target IsaacSim41 runtime and produced structured evidence.

Blocked claims remain: `level1_pour` true fluid is ready, robot pouring succeeds, EBench score is available, official leaderboard readiness, or policy success.

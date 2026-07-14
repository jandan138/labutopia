# Real-Beaker Parent USD Closure Plan

## Goal

Allow the formal parent launcher to validate a completed prior cell before
starting the next cell under the pinned Isaac Sim 4.1 conda Python, where `pxr`
is unavailable until `SimulationApp` starts.

`_007` proved that cell 0 renders and finalizes successfully. Cell 1 failed
before launch because parent-side artifact closure redundantly called
`UsdUtils.ComputeAllDependencies` after it had already validated the child's
post-boot runtime dependency resolution and the byte-exact source snapshot.

## Scope

Change only:

- `tests/test_real_beaker_runtime_contract.py`
- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- `tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_008.sh`

Add this plan, the `_008` launcher, and exact terminal `_007` evidence to the
implementation/protected identities.

Do not change the child-side post-`SimulationApp` USD dependency computation,
the direct source-snapshot validator's default behavior, the scene, material,
physics, cameras, render settings, or matrix ordering. Do not inject
`PYTHONPATH`, `LD_LIBRARY_PATH`, or a second Python executable into the formal
launcher. Keep the sealed runtime bootstrap and its existing removal of
`PYTHONPATH`, `PYTHONHOME`, and `PYTHONUSERBASE` unchanged.

## TDD Sequence

1. Extend the artifact-closure test so `compute_usd_dependency_paths` raises
   `ModuleNotFoundError("No module named 'pxr'")`; a completed cell must still
   validate from its byte-exact snapshot and recorded post-boot runtime
   dependency resolution.
2. In the same artifact-closure path, mutate one snapshotted USD byte and prove
   closure still fails. The runtime manifest validation, source sidecar match,
   read-only snapshot tree, artifact inventory rebuild, and sealed child
   post-boot dependency-resolution gates must all remain enabled.
3. Keep the direct source-snapshot tests proving that their default
   `verify_usd_dependencies=True` path still calls dependency computation and
   rejects unresolved/outside-root dependencies.
4. Change the single artifact-closure call to
   `verify_usd_dependencies=False`. No fallback, import-path mutation, or new
   resolution format is added.
5. Validate `_007` exactly as one `SUCCESS`, fifteen `NOT_LAUNCHED`, terminal
   `INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED`, with exact decision/status,
   identity/pre/post-freeze/lock file hashes and decision self-hash.
6. Advance only experiment/output/log/freeze revision references to `_008` and
   prove the launcher is otherwise byte-identical to `_007`.

## Verification And Launch

1. Run the focused artifact-closure test red, make the one-call change, then run
   it green together with direct source-snapshot tests.
2. Run the full runtime-contract module, related suite, syntax checks, and three
   independent implementation reviews.
3. Generate `_008` implementation identity, then protected pre-freeze, then run
   the exact Isaac 4.1 launch preflight.
4. Launch `_008` from cell 0. Confirm cell 0 closes and cell 1 reaches
   `CELL_START` plus Isaac startup before allowing the remaining cells to run.

## Stop Condition

Any runtime, artifact, or sidecar failure stops and is aggregated before another
revision.

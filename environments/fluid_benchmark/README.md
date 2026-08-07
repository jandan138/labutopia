# Experimental Isaac 6.0.1 + Newton 1.4 fluid lanes

These environments are experimental performance lanes. They do not replace
the repository's sealed Isaac Sim 4.1 effective-runtime v2 baseline and their
outputs must not be relabeled as formal Isaac 4.1 evidence.

Installed prefixes:

- `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim601-fluid-py312`
- `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-newton140-mpm-py312`

The committed YAML files pin the requested direct dependencies. Generated
explicit Conda package lists, `pip freeze --all`, `pip inspect`, installed
distribution `RECORD` hashes, and runtime manifests live under
`outputs/fluid_benchmark_isaac601_newton140/environment_locks/` and are bound
into each benchmark matrix. Runtime commands use absolute interpreter paths
and a sanitized, allowlisted child environment.

The Newton lane uses the recorded 953-orientation trace with a declared,
blended translation alignment for its solver-specific pour controller. This
keeps the scene, camera, particle count, duration, and integration schedule
fixed, but it is not an exact-controller-trajectory comparison with the
historical Isaac 4.1 run. The exact recorded trace remains available through
`--no-pour-retarget` as a diagnostic negative control.

## WCSPH benchmark execution lanes

The executable comparison uses the two existing locked environments listed
above. Isaac's vendor-compatible Newton/Warp pair and standalone Newton 1.4
physics therefore cannot perturb one another:

- Isaac 6.0.1 same-process WCSPH target prefix:
  `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim601-fluid-py312`

- primary target prefix:
  `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-newton140-mpm-py312`

The r1/r2 YAML files retain the attempted standalone construction recipes.
Their 2026-08-03 creation attempts failed from a dependency conflict, package
download integrity failure, or CPFS quota exhaustion. They are not runnable
lanes and must not be relabeled as successes. Failure logs and the cleanup
record are preserved under `outputs/newton_only_fluid_solver_benchmark/`.

Isaac's integrated Newton 1.2.1/Warp 1.13 pair is not upgraded in place.  The
standalone lane pins Newton 1.4/Warp 1.15.  Isaac receipts report physics and
RTX capabilities separately because the current 570.153.02 driver permits
experimental headless physics but does not produce valid Isaac 6 RTX evidence.

As of 2026-08-03, benchmark execution uses only the pre-existing locked
prefixes. The partial r1/r2 targets were removed after inspection to recover
quota; their logs remain immutable failure evidence. Fresh run IDs are used
for every measurement.

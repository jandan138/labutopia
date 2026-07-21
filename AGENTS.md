# LabUtopia Agent Instructions

## Formal Isaac Runtime Contract

These rules apply to any command that imports `isaacsim`, `omni.*`, or `pxr`,
starts `SimulationApp`, runs PhysX/PBD, launches an EBench/GenManip worker, or
produces physics, runtime, acceptance, or delivery evidence.

- The only formal simulator baseline is:
  `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python`.
- The expected baseline tuple is Python 3.10.20, `isaacsim==4.1.0.0`,
  `numpy==1.26.4`, and USD 0.22.11. A reviewed replacement must pin and
  attest the complete tuple, not just Isaac's major version.
- Invoke the absolute `bin/python` path. Do not resolve `python` through
  `PATH`, use the environment's `isaacsim` console script, or fall back to
  `sys.executable`.
- System Python, host `/isaac-sim`, Isaac 4.5/5.x, and other Conda
  environments are not substitutes. They may be used only for clearly labeled
  non-authoritative exploration or visual work, never to support a formal
  runtime, physics, EBench, or delivery claim.
- The shared `/isaac-sim` installation is not a repair target. Never install,
  upgrade, downgrade, uninstall, or otherwise modify packages there, in base
  Conda, or with `--user` to make a formal run work.

## Process Boundaries And Isolation

- Keep pure orchestration separate from the sealed Isaac 4.1 runtime child.
  Any USD/`pxr`, Isaac, Omni, PhysX, cooked-geometry, or runtime inspection
  that influences a formal decision must occur in the sealed 4.1 child after
  the required runtime bootstrap; parent-only imports are not runtime evidence.
- Launch the runtime child with an explicit allowlisted environment. Do not
  inherit or append ambient `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`,
  `CARB_APP_PATH`, `EXP_PATH`, `ISAAC_PATH`, `OMNI_SERVER`, `LD_PRELOAD`, or
  foreign Isaac/USD/pxr entries in `LD_LIBRARY_PATH`.
- Set `PYTHONNOUSERSITE=1`, explicit `ACCEPT_EULA=Y` and
  `OMNI_KIT_ACCEPT_EULA=YES`, and run-scoped `HOME`, `TMPDIR`, XDG, cache,
  config, log, and evidence directories. A missing or contradictory EULA
  acknowledgement is a pre-launch infrastructure failure, not a prompt to
  bypass.
- Simulator/server/worker descendants must receive the same approved runtime
  contract. Model, training, OpenPI, and client environments remain separate
  and communicate only through their declared interfaces.
- A non-Python CUDA/library path is allowed only when its purpose, exact path,
  version, and hash are declared in the run evidence. Never leak host Isaac
  libraries into the 4.1 child.

## Runtime Preflight And Provenance

- Fail closed before task execution if the interpreter path or prefix, Python,
  Isaac, NumPy, USD, Torch/CUDA, module/native-extension origins, or approved
  library paths do not match the declared runtime contract. Never fall back to
  an importable host `pxr`, host Isaac install, cache, system Python, or another
  Isaac version.
- A formal runtime manifest must bind: environment ID/revision, executable and
  prefix, lock/history and pip-freeze hashes, runtime versions and origins,
  GPU/driver, sanitized environment hash, command, source revision and dirty
  state, task configuration, input USD/assets and closure hashes, run ID,
  stdout/stderr hashes, exit or signal status, and produced artifact hashes.
- Import success or exit code alone is not a pass. Runtime identity, preflight,
  logs, artifacts, and task-specific acceptance fields must agree.
- Runtime/preflight failure is blocked infrastructure evidence, not an asset,
  controller, policy, or physics failure. Preserve it under a fresh run ID and
  never reuse, overwrite, or relabel it as a successful run.

## Environment Changes

- Do not mutate the canonical Isaac 4.1 evidence baseline during an experiment.
- If a new main Python/simulator environment is necessary, model it on the
  established EOS/EBench environment rather than cloning or patching host
  Isaac. Create a versioned, simulator-only environment under
  `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/`, with an explicit
  Conda lock, pinned pip sources/hashes, launcher, environment manifest, and
  fresh ABI/runtime preflight.
- A newly created environment is an experimental lane until it is independently
  reviewed and formally adopted. Its output is not comparable to, and cannot
  replace, Isaac 4.1 baseline evidence.
- Exceptions require written per-run approval with scope, rationale, exact
  environment difference, expiry, and evidence impact. There is no exception
  for mutating global or shared installations.

## Evidence Comparability

- Compare, promote, or make claims only across runs with compatible runtime,
  environment, source, asset, and configuration identities.
- A change to Isaac, Kit, USD, PhysX extension, material closure, CUDA/library
  path, or input closure requires a fresh run and a separate claim.
- Historical Isaac 4.5 output remains non-comparable visual/reference evidence;
  it must never validate or replace an Isaac 4.1 runtime gate.

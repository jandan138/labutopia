# Task 6 Report: OmniGlass Reference Proxy and Replay

## Status

Complete. Commit: `ef7949c` (`feat(fluid): replay A18-scaled OmniGlass particles`).

The commit is based on parent verification fixes `2842661` and `526bcea`; both remain
ancestors and none of their files were included in the Task 6 commit.

## RED Evidence

Candidate/proxy tests were created before the presentation module:

```text
python -m pytest tests/test_omniglass_reference.py -v
8 failed
ModuleNotFoundError: No module named 'tools.labutopia_fluid.omniglass_reference'
```

Replay tests were added before the replay runner:

```text
python -m pytest tests/test_real_beaker_runtime_contract.py -v -k replay
collected 0 items / 1 error
ImportError: cannot import name 'run_real_beaker_omniglass_replay'
```

Focused RED cycles then covered the runtime boundary and review findings:

```text
# Physical/debug hiding and timeline guard
2 failed: /World/fluid remained visible; require_stopped_timeline was missing

# Direct script bootstrap
1 failed: ModuleNotFoundError: No module named 'tools'

# Pinned Isaac 4.1 dry plan before lazy imports
1 failed: ModuleNotFoundError: No module named 'pxr'

# Exact plan command without --out-root
1 failed: argparse required --out-root

# Version-matched MDL provenance
2 failed: build_version_matched_mdl_source_contract was missing

# Exact source reload for each candidate
1 failed: stage.reload_calls == 0
```

Each failure was observed before its corresponding production change.

## GREEN Evidence

Required pure suite:

```text
python -m pytest \
  tests/test_omniglass_reference.py \
  tests/test_real_beaker_runtime_contract.py -v

98 passed in 1.57s
```

Exact Task 6 Step 6 dry plan under the pinned Isaac 4.1 conda interpreter:

```text
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/\
embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python \
tools/labutopia_fluid/run_real_beaker_omniglass_replay.py \
  --accepted-summary DRY_PLAN_ACCEPTED_SUMMARY_NOT_READ \
  --dry-plan
```

Exit code was zero. Output recorded:

```text
accepted_summary_read=false
trace_read=false
isaac_runtime_imported=false
simulation_app_started=false
physics_steps_planned=0
timeline_play_planned=false
candidate_ids=[OMNI_REF_FINE, OMNI_REF_RATIO_15, OMNI_REF_RATIO_12]
out_root=.../real_beaker_omniglass_reference_20260711_001
```

Static checks:

```text
python -m py_compile <four owned Python files>
exit 0

python -m ruff check <four owned Python files>
All checks passed!

git diff --cached --check
exit 0
```

The staged index contained exactly the four implementation/test files before commit.

## Implementation

- Candidate widths are derived exactly as `diameter/32` clamped to 1.5-2.0 mm,
  `diameter/15`, and `diameter/12`.
- Canonical voxel keys and points within each bucket are sorted before centroiding.
- `PresentationParticleSet` is plain `UsdGeom.Points`; PhysX schemas and relationships
  are rejected.
- Non-dry validation checks PASS state, strict schema, run-scoped diagnostics, source
  hash, and exact full recomputed `physical_trace_identity` before `SimulationApp` is
  imported.
- The accepted trace is read once and reused for every candidate.
- Every candidate records the same complete input identity, final static presentation
  frame, hidden physical initial-state frame, per-frame proxy counts, and artifact hashes.
- Replay opens and reloads the exact accepted source for each candidate, keeps the
  timeline stopped, hides physical/debug points, and uses context plus source closeup
  cameras.
- A18 colors remain sourced from `presentation_look_profiles.py`.
- MDL closure now requires Isaac 4.1, requires the source root beneath the active conda
  prefix, rejects `/isaac-sim` host fallback, verifies required files, and records source
  and copied tree hashes in candidate manifests.
- Candidate and top manifests remain `PENDING_INDEPENDENT_REVIEW`; images cannot produce
  an automatic visual PASS.

## Files

- Created `tools/labutopia_fluid/omniglass_reference.py`.
- Created `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`.
- Created `tests/test_omniglass_reference.py`.
- Modified `tests/test_real_beaker_runtime_contract.py`.
- Created this report after the implementation commit; it is intentionally not part of
  `ef7949c` because the task required committing only implementation/test files.

## Risks

- No live replay was launched, as required. Camera initialization, MDL compilation,
  RTX rendering, MP4 encoding, and actual candidate image quality remain unverified
  until an accepted strict trace exists.
- No visual candidate is selected and no visual PASS is claimed. Independent closeup
  and context review remains a later gate.
- The version-matched MDL selector and copy/hash contract are covered by pure tests, but
  their integration with a live `SimulationApp` was not exercised in Task 6.

---

## Review Fix Report (2026-07-11)

Status: `DONE_WITH_CONCERNS` pending synchronization of the parent-owned replay fixture
described below.

### Fixes

- Candidate authoring now changes only visibility on declared physical source roots and
  debug-named visuals. It does not write `particleSystemEnabled` or any other physics
  attribute, and unrelated point-based scene geometry remains visible.
- Added the existing local `presentation_look_profiles.py` source material and its tests
  to the committed Task 6 file set, preserving the A18 colors and weekly look behavior.
- Accepted diagnostics now resolve the declared Kit log relative to the accepted summary,
  seek to the declared byte offset, read the declared byte count, and verify both the
  actual byte count and SHA-256. Missing, truncated, and mismatched evidence fails closed.

### TDD Evidence

Focused RED command:

```text
python -m pytest tests/test_omniglass_reference.py::test_hiding_source_visuals_does_not_author_physics_attributes tests/test_omniglass_reference.py::test_diagnostic_validation_reads_exact_declared_relative_log_segment tests/test_omniglass_reference.py::test_diagnostic_validation_fails_closed_for_unverifiable_segment tests/test_fluid_presentation_look_profiles.py::test_local_a18_reference_colors_are_pinned_in_profile_source_of_truth -v
```

Result before implementation: `5 failed, 1 passed in 0.44s`. The visibility test observed
`particleSystemEnabled` changing from `True` to `False`; all diagnostics cases failed
because `_validate_run_scoped_diagnostics` did not accept or resolve a summary path.

Focused GREEN command: same command as above.

Result after implementation: `6 passed in 0.28s`.

Complete owned test command:

```text
python -m pytest tests/test_omniglass_reference.py tests/test_fluid_presentation_look_profiles.py -v
```

Result: `20 passed in 0.39s`.

Compatibility command against the parent-owned concurrent test file:

```text
python -m pytest tests/test_real_beaker_runtime_contract.py -v -k replay
```

Result: `13 passed, 3 failed, 75 deselected in 0.77s`. The three failures all stop at
`declared_kit_log_missing`: the concurrent `_write_accepted_replay_input` fixture declares
`kit.log` with offset `123`, byte count `17`, and a synthetic hash, but does not create the
file. Per ownership instructions that test file was not edited, and production validation
was not weakened to accept unverifiable diagnostics.

Static verification:

```text
python -m py_compile tools/labutopia_fluid/omniglass_reference.py tools/labutopia_fluid/run_real_beaker_omniglass_replay.py tools/labutopia_fluid/presentation_look_profiles.py tests/test_omniglass_reference.py tests/test_fluid_presentation_look_profiles.py
```

Result: exit `0`.

```text
python -m ruff check tools/labutopia_fluid/omniglass_reference.py tools/labutopia_fluid/run_real_beaker_omniglass_replay.py tools/labutopia_fluid/presentation_look_profiles.py tests/test_omniglass_reference.py tests/test_fluid_presentation_look_profiles.py
```

Result: `All checks passed!`.

No Isaac process was launched. No live or visual PASS is claimed.

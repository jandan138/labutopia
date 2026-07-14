# Real-beaker presentation-layer file-mode repair plan

## Objective

Run the 16-cell real-beaker AO/RT matrix from a clean `_005` experiment root.
The repair is limited to making newly created presentation and static-entry USD
layers privately writable before their first save. It does not add save retries,
alternate export paths, or copy-based fallbacks.

## Confirmed root cause

- The formal launcher runs children with `umask 077`.
- Under Isaac Sim 4.1, `Sdf.Layer.CreateNew` then created the presentation USD
  with mode `0567` and reported `permissionToSave=false`.
- A controlled Isaac probe showed that changing that same file to mode `0600`
  immediately changed `permissionToSave` to `true`.
- `_004` correctly stopped after the first failed cell; the source USD remained
  unchanged and the other 15 cells were not launched.

## Changes

1. `tests/test_real_beaker_runtime_contract.py`
   - Add a failing contract test that simulates the bad mode returned by USD
     creation and requires `begin_candidate_presentation_layer` to normalize the
     file to exactly `0600` before returning.
   - Add the equivalent failing assertion for the static entry created during
     export; it must also be `0600` before its single save.
   - Require the returned layer to be editable and saveable.
   - Update the export lifecycle expectation so the normal path begins writable,
     attempts no permission recovery setters, saves once, and locks once after
     save. Source bytes and source locks must remain unchanged, and both static
     entry and capture reopen must succeed.

2. `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
   - In `begin_candidate_presentation_layer`, normalize the newly created local
     file-backed layer to `0600` and verify the mode and USD permission readback.
   - Apply the same deterministic normalization to the newly created static entry
     before authoring and its single save.
   - Keep the existing single-save and post-save lock behavior. Do not add retry,
     alternate-path, or recovery branches.
   - Advance the formal experiment identity to `_005`. Validate the closed `_004`
     decision as one failed cell and fifteen not launched, then protect its tree,
     aggregate lock, implementation identity, and pre/post-freeze files.

3. `tools/labutopia_fluid/run_presentation_layer_save_recovery_isaac_smoke.py`
   - Build the preexisting source fixture before entering the `umask 077` scope,
     then reproduce that formal environment for presentation/static creation.
   - Remove the artificial pre-save permission lock.
   - Assert presentation and static modes `0600`, writable pre-save state, no
     recovery setters, one successful presentation save, post-save lock, source
     immutability/source locks, and capture reopen verification.

4. `tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_005.sh`
   - Copy the frozen `_004` launch shape, changing only the `_005` experiment
     identity, paths, and log names.

5. `_005` identity and freeze manifests
   - Add this plan and the `_005` launcher to the implementation members.
   - Generate a new implementation identity and protected-tree pre-freeze only
     after tests, the Isaac smoke, and `_004` terminal validation pass.

## TDD and verification order

1. Write presentation/static file-mode and normal-save-path tests and demonstrate
   the focused tests fail against the current implementation.
2. Implement the two `0600` normalizations and update smoke/experiment constants.
3. Run focused tests, related runtime-contract tests, syntax checks, and the
   broader real-beaker suite.
4. Run the Isaac 4.1 smoke under `umask 077`; require `0600` and no permission
   recovery attempt.
5. Validate `_004`, generate `_005` implementation identity, generate `_005`
   pre-freeze, run launch preflight, then run the fail-fast 16-cell matrix.
6. Aggregate the matrix. If all cells complete, run machine artifact validation
   and independent visual review of the rendered table/cup/liquid frames.

## Stop conditions

- Stop the formal matrix on the first runtime or artifact failure.
- Never mutate or resume `_004`.
- Keep raw matrix output `colleague_delivery_ready=false`; cross-UID delivery is
  a separate packaging step and does not change formal layer modes to `0644`.
- Do not claim a renderer conclusion or colleague-ready delivery until the
  complete `_005` matrix and visual gates pass.

## Plan review record

- Architecture/scope: `GO`. Creation owns the initial mode, so normalization
  belongs at layer creation and export should not compensate with fallbacks.
- Completeness/edge cases: `REVISE`, incorporated. The static entry uses the same
  USD creation API and needs the same deterministic mode fix; the source smoke
  fixture must predate the restrictive umask scope.
- Operational risk: `REVISE`, incorporated. `_004` terminal semantics and all
  external freeze/lock files must be validated and protected before `_005`
  identity generation; raw matrix output remains non-delivery evidence.

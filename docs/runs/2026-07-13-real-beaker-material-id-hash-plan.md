# Real-Beaker Material ID Hash Plan

## Goal

Unblock matrix cell evidence after `_006` proved that the normal-remediation
projection passes parent sidecar validation.

The real material contract uses `material_hash` as the stable semantic identifier
`omniglass_water_tint_a18_v1`. Matrix cell evidence names its field
`liquid_material_sha256`, so the sidecar must canonical-hash that identifier rather
than copy the non-hash string into the field.

## Scope

Change only:

- `tests/test_real_beaker_runtime_contract.py`
- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- `tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_007.sh`

Add the terminal `_006` root and its identity/freeze/lock files to protected
inputs, validate its exact one-failed/fifteen-not-launched parent-sidecar terminal
state, and include this plan plus the `_007` launcher in implementation identity.
Historical validation must pin the `_006` decision self-hash and the exact file
SHA-256 values for decision, status, failure evidence, identity, pre-freeze,
post-freeze, and lock evidence.

Do not change the material contract, material ID, MDL closure, scene USD, liquid,
camera, render settings, or normal projection.

## TDD Sequence

1. Read the real `_006` first-cell `candidate_manifest.json` and assert that its
   material ID is exactly `omniglass_water_tint_a18_v1`. This is the external
   evidence anchor; the synthetic fixture must not define the expected ID by
   itself.
2. Replace the synthetic sidecar fixture's fake 64-character `material_hash` with
   that real semantic ID and add a failing assertion that
   `liquid_material_sha256` equals
   `canonical_json_sha256_v1("omniglass_water_tint_a18_v1")`.
3. Add failing parameterized sidecar tests for a missing `material_hash`, `None`,
   and an empty string. Each must fail before matrix cell evidence is written and
   must not use a fallback identifier.
4. Exercise the complete 16-cell equality path: all cells using the canonical
   hash of the real ID must close as `PASS`; changing only one cell's material ID,
   recomputing that cell evidence self-hash, must close as `FAIL` with the
   `liquid_material` equality record set to `FAIL`.
5. Implement the one-line semantic conversion at sidecar construction: validate
   the non-empty material ID and store its canonical SHA-256. Add no fallback and
   no second material projection.
6. Add `_006` historical terminal/protected-input tests, then advance constants and
   launcher to `_007`. Add a launcher-scope test proving `_007` keeps the same
   ordered 16 cells, candidate, 960x540 output, and render parameters as `_006`;
   only the experiment/output/log/freeze version references may change.

## Verification And Launch

1. Run focused tests red, implement, then run them green.
2. Run the full runtime-contract module, related suite, syntax checks, and three
   independent implementation reviews.
3. Generate `_007` implementation identity, then protected pre-freeze, then run
   launch preflight. The protected-input chain must validate `_006` terminal
   evidence before accepting `_007` identity, and `_007` identity before accepting
   `_007` pre-freeze.
4. Start the formal launcher at cell 0 and confirm matrix cell evidence is written
   before the remaining cells continue.

## Stop Condition

Any runtime, artifact, or sidecar failure stops the launcher and is aggregated
before another code revision.

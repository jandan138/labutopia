# Real-Beaker Normal Equivalence Projection Plan

## Goal

Unblock the formal AO/RT matrix after `_005` proved that rendering and USD layer
saves succeed, while preserving the full path-bearing normal-remediation contract
for per-cell integrity.

The matrix must compare a path-independent normal-remediation content projection,
not the full contract hash. The full contract hash legitimately changes when the
same frozen USD dependency closure is copied into a different cell-local snapshot.

## Confirmed Cause

The accepted historical normal contract and `_005` have identical source file
hashes, layer content hashes, beaker mesh signatures, normals, material bindings,
and physics attributes. Their only differences are:

- `source_usd_path`
- `source_layer_stack[*].identifier`
- `source_layer_stack[*].real_path`
- the full contract self-hash derived from those paths

Therefore a single expected full contract hash cannot be valid across all 16
cell-local snapshots.

## Scope

Files to change:

- `tests/test_real_beaker_runtime_contract.py`
- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- `tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_006.sh`

Generated formal evidence will use the `_006` experiment identity and freeze
manifests. The closed `_005` root and its external identity/freeze/lock files will
be added to the protected-input registry. Launch preflight will also validate the
closed `_005` decision self-hash, exact decision/status/external-file hashes, and
its terminal shape: one parent-sidecar-finalization failure followed by 15
not-launched cells.

No scene USD, liquid geometry, camera, lighting, render setting, particle trace,
or material behavior will change.

## TDD Sequence

1. Add failing tests proving that two byte-identical USD dependency closures at
   different absolute roots have different full normal contract hashes but the
   same matrix-equivalence projection and projection hash.
2. Add failing tests proving that stable content or normal-policy changes alter
   the projection hash, and that an invalid full contract self-hash is rejected.
3. Add a 16-root regression test by rebasing the same trusted contract to every
   formal cell path and recomputing each full self-hash. All 16 full hashes may
   differ, but all 16 projection hashes must equal the frozen expected value; a
   content, mesh-signature, or policy mutation must change that value.
4. Bind the frozen expected projection to the protected historical contract whose
   full hash is `da174bdbe851d73346208c97babbc3f4a6ee09c1b4ee945afd7f15a36b6a8fcb`.
   A regression test will read that historical evidence and `_005` evidence,
   proving both project to the same value. `_005` does not define the baseline.
5. Update sidecar tests so parent finalization validates the nested full contract
   self-hash, requires the candidate sibling full hash to match it, recomputes the
   projection, compares it to the frozen expected value, and writes it to the
   explicitly named `normal_remediation_matrix_projection_sha256` cell field.
   Missing/tampered nested contracts and sibling-hash mismatches must fail.
6. Implement one projection builder that first validates and removes the full
   `beaker_normal_remediation_contract_sha256` envelope field, then removes only
   the three confirmed location fields: `source_usd_path`,
   `source_layer_stack[*].identifier`, and
   `source_layer_stack[*].real_path`. It retains layer order, all layer/content
   hashes, scene paths, mesh signatures, normals, material/physics data, and all
   policy fields, then adds an independent projection self-hash.
7. Replace matrix established-input and cross-cell equality checks with the
   projection hash. Keep the existing full contract and full self-hash unchanged
   in candidate evidence; do not duplicate the path-specific full hash into the
   matrix-wide cell schema.
8. Advance the formal constants and launcher to `_006`; include this plan and the
   launcher in implementation identity, protect and semantically validate the
   terminal `_005` evidence without altering it, then generate identity before
   pre-freeze.

## Verification And Launch

1. Run the focused new tests and confirm their initial failure before implementation.
2. Run the full runtime-contract test module, related matrix tests, `py_compile`,
   and shell syntax checks.
3. Freeze the `_006` implementation and protected inputs, then run launch preflight.
4. Start `_006` from cell 0. Confirm the first cell reaches parent sidecar
   finalization before allowing the launcher to continue through all 16 cells.
5. Aggregate the completed matrix and perform machine checks plus independent
   visual review of the rendered tabletop/cup/liquid outputs.

## Stop Conditions

- Any source/content/mesh/policy mismatch still fails closed.
- A path-only difference must not fail matrix equivalence.
- Any formal runtime or artifact failure stops the launcher and is aggregated
  before another implementation revision.

# Real-Beaker Presentation-Layer Save Recovery Plan

## Goal

Recover from the terminal `_003` first-cell failure without changing the AO/RT
2x2 treatment, balanced order, accepted physical trace, source USD, materials,
cameras, frame set, visual gates, or claim boundary. The replacement experiment
is `real_beaker_ao_rt_matrix_v3_20260712_004`.

`_003` is final and immutable. Its frozen aggregate decision is
`STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE`: cell `A_0_AO0_RT4_CONTROL` failed while
saving its dirty file-backed presentation layer because Isaac/USD reported
`permissionToSave=false`; the other fifteen slots were not launched. Preserve
the complete `_003` aggregate root plus its implementation identity, pre-freeze,
post-freeze, and lock as `_004` protected inputs.

Before changing any `_003` implementation member, use the still-matching frozen
runner to revalidate the `_003` decision authority, anchor, lock witness,
publication intent/commit, terminal decision semantics, first launch/failure
evidence, and exact sixteen-slot status index. Persist a sibling
`real_beaker_ao_rt_matrix_v3_20260712_003_terminal_validation.json` attestation
that binds those hashes and a complete aggregate-tree snapshot. `_004` protects
this attestation as an additional fixed file.

That attestation has now been created before implementation mutation by the
frozen `_003` runner (`implementation_identity_sha256`
`d71598c7201a929fbeb7064242e7cacf22ad94ff3fddac97d60dae262236d986`,
replay source SHA-256
`50038ffb33363096fcfb3e5d0dc582b982909a30860b878ba5a056aca5fff527`).
It is a sibling, never an aggregate descendant, and does not append to the
already terminal `_003` lock. Its file SHA-256 is
`ac99aa8d494dcab04fe401da4c025e840ba7bb81996438ddc012d4e0ed46ec71`;
its logical `terminal_validation_sha256` is
`2a3d413edb376a21ad8e46e916492afc690d49223e4b6f4b6845065418c7fb0b`.
Its exact field set is `{schema_version, attestation_id, experiment_id,
aggregate_root, aggregate_tree_files, aggregate_tree_sha256, external_files,
anchor_sha256, decision_sha256, decision_commit_sha256,
publication_intent_sha256, authority_witness_sha256, terminal_state,
cell_status_index, cell_status_index_sha256, validated_launch_chain,
validated_launch_chain_sha256, semantic_validation_passed,
authority_validation_passed, terminal_validation_sha256}`. The aggregate tree
is the path-sorted, unique 349-record list of exact
`{path, byte_count, sha256}` values produced by
`_snapshot_pinned_regular_tree`; the four external records additionally bind
canonical absolute path, byte count, SHA-256, device, inode, and regular-file
type. `_004` validates this exact schema, both self-hashes, the declared
terminal code, `FAILED=1/NOT_LAUNCHED=15`, and file bytes before pre-freeze.

Attestation validation is deterministic and ordered. First require the fixed
sibling canonical path to be a regular non-symlink with the fixed file SHA-256
`ac99...ec71`. Parse with duplicate-key rejection and require the exact field
set/types. Recompute `aggregate_tree_sha256` and the two declared status/chain
hashes with `canonical_json_sha256_v1`. Recompute
`terminal_validation_sha256` from the complete parsed object after removing
only `terminal_validation_sha256`; `canonical_json_sha256_v1` means UTF-8 JSON,
`sort_keys=true`, separators `(',', ':')`, `allow_nan=false`. Require the
result to equal both the embedded `2a3d...fb0b` and the fixed expected constant.
Then rehash/re-stat each external record at its recorded canonical path and
require exact regular-file type, device, inode, byte count, and SHA-256; rescan
the aggregate into the same sorted 349 records; finally require all authority,
terminal, and 1/15 status invariants. Any earlier failure stops validation.

## Root-Cause Boundary

The sealed bootstrap and `SimulationApp` both succeeded. Nonformal Isaac 4.1
probes showed that the source root remained locked and unchanged, while the same
presentation authoring sequence could save when its layer permission remained
enabled. The failure is therefore an export lifecycle defect, not an AO/RT
observation, fluid-physics failure, material conclusion, or source-asset error.

The repair is deliberately local. Immediately before the first presentation
save, the helper must prove that the supplied layer is file-backed, has the
expected real path, is the current edit target, and is neither the source root
object nor an identifier/real-path alias of it. The source root must already
read back `permissionToEdit=false` and `permissionToSave=false`. Capture both
layers' permissions and source bytes/snapshot; restore each missing
presentation permission on that exact layer; require both read back true while
the source remains locked and byte/snapshot identical; save; and record the
exact recovery contract. Setter order is edit then save. Call a setter only
when its preflight value is false, and set its attempt flag immediately before
the call. Immediately read back that individual property after its setter: a
setter exception or its immediate getter exception/false result maps to
`SET_EDIT` or `SET_SAVE`, recorded respectively as top-level
`set_edit_readback`/`set_save_readback` booleans. If that setter was not needed,
its attempt flag is false and its readback is null. After all needed setters,
one final paired getter populates `after_recovery`; its exception or a non-true value maps to
`RECOVERY_READBACK`. If both permissions started true, no recovery setter runs,
all recovery/setter flags are false, the final paired readback still populates
`after_recovery`. A permission getter failure before setter selection maps to
`IDENTITY_PREFLIGHT`. Root, anonymous, aliased, wrong-path, or wrong-edit-target
inputs fail before any setter.

The filesystem threat boundary is explicit. A formal cell root is
create-exclusive and has one sealed runner child as its only cooperating
writer. The experiment detects runner bugs, stale/reused paths, symlink and
hardlink aliases, and replacements at every declared checkpoint. It does not
claim to identify the creator of an inode or defend against a same-UID or
privileged process racing the few instructions between `Sdf.Layer.Save()` and
the first post-save open. Such an untrusted concurrent writer is outside the
formal experiment model; no pathname-based userspace protocol can prove inode
provenance against it without a stronger filesystem isolation primitive.

Canonical layer identity is defined from `layer.realPath`, not the display
identifier: it must be a nonempty local absolute path whose every existing
component passes the existing no-symlink pinned-path check and whose leaf is a
regular non-symlink with `st_nlink=1`. Capture `(st_dev, st_ino, st_nlink)` with
`follow_symlinks=false`.
The source path must equal the exact cell-local source-snapshot entry already
bound by `matrix_source_dependency_closure.json`, and its SHA-256 must equal the
frozen accepted source hash. The presentation path must equal the exact
candidate path supplied by the caller. Reject equal canonical paths, equal
device/inode (hardlink), anonymous/nonlocal identifiers, URI/relative/nonlocal
real paths, wrong expected paths, and any source identity/hash drift. The source
and presentation `SdfLayer` objects must be distinct.

`Sdf.Layer.Save()` normally replaces a file atomically and can therefore change
the presentation inode. The source path is never allowed to change identity.
The presentation path may make exactly one identity transition, and only across
the successful `Save()` call: immediately afterward, re-open/re-stat the exact
named path through its already pinned parent using `O_NOFOLLOW`, require a
regular non-symlink leaf with `st_nlink=1`, hash/read bytes from that descriptor,
require descriptor `fstat` to be unchanged before/after the read, require a
no-follow named stat to equal the post-read descriptor's exact
`(st_dev, st_ino, file-type, st_nlink)` tuple, require every pinned path
component to still identify the same object, and require those bytes to equal
the in-memory layer's
`ExportToString()` UTF-8 bytes. Capture its new device/inode, saved bytes, and
layer snapshot, and pin that post-save identity. No pre-save expectation
requires the presentation inode to remain equal across `Save()` itself, and no
evidence field claims that USD rather than an out-of-model concurrent writer
created the new inode.

The FD sequence is exact. Open and retain directory descriptors from the
filesystem anchor through the parent with component-wise `openat` using
`O_NOFOLLOW|O_DIRECTORY`, recording each component's `lstat` identity. Open the
leaf relative to the retained parent descriptor with `O_RDONLY|O_NOFOLLOW`.
Require leaf `fstat` and parent-relative no-follow named stat to match before
reading; read/hash only through the leaf descriptor; require leaf `fstat` to be
unchanged afterward; repeat the parent-relative named stat and require it to
equal that post-read descriptor tuple; then re-`lstat` every recorded component
and require exact identity. Close descriptors only after these checks. Tests
inject both leaf replacement during read and an intermediate-directory swap
between open and final component verification.

Explicitly set the presentation layer back to edit/save false, require both
permissions read back false, and require the presentation path to equal its
post-save pinned identity while the source still equals its preflight identity.
After the static entry has completed its own final save, capture and pin that
regular non-symlink, single-link identity too. At that point
`export_static_candidate_entry` produces one exact
`capture_persistent_layer_baseline` object with
`{schema_version=1, contract_id=capture_persistent_layer_baseline_v1, files,
baseline_sha256}`. `files` is path-sorted and contains exactly the source,
presentation, and static-entry records, each exact
`{role, path, sha256, device, inode, file_type, link_count}`; `baseline_sha256`
is `canonical_json_sha256_v1` of the other three fields. Validate this object
immediately before returning `static_entry_export`, embed it there, and pass
that same object unchanged into `lock_capture_persistent_layers`; capture
lock acquisition must compare, not redefine, the source, presentation, and
static-entry baselines. Extend the capture lock contract with each layer's
canonical path, regular non-symlink type, device, inode, and link count. The
post-capture validator must re-stat every pinned path and prove the used-layer
set, path identities, hashes, dirty flags, and permissions stayed unchanged. A
same-byte path replacement, hardlink rebinding, or extra hardlink is a failure
even when SHA-256 is unchanged. This closes the interval between export
recovery completion and capture-lock acquisition.

The exact successful `presentation_layer_export_permission_recovery` object is
embedded in `static_entry_export` and therefore the final candidate manifest,
cell evidence, and authority hash chain. It contains:

- `schema_version=1` and
  `contract_id=presentation_layer_export_permission_recovery_v1`;
- presentation identifier/real path and source-root identifier/real path;
- presentation edit/save values before recovery, after recovery, after save,
  and after relock;
- source edit/save values before recovery, after recovery, after save, and
  after presentation relock;
- `recovery_attempted`, the two individual setter-attempt flags and readbacks;
- source file SHA-256 and source layer snapshot SHA-256 before/after recovery
  and after save;
- `save_attempted`, `save_succeeded`, saved presentation SHA-256, and
  `relock_succeeded`.

Any setter/readback/save/relock failure raises a dedicated exception carrying
the partial contract. `build_replay_runtime_failure_manifest` persists it under
`runtime_failure_context.presentation_layer_export_permission_recovery`; no
static entry or successful export contract may exist on those paths.

The contract always has this exact top-level field set:
`{schema_version, contract_id, status, failure_stage, secondary_failure_stage, presentation_layer,
source_root_layer, presentation_permissions, source_permissions,
recovery_attempted, set_edit_attempted, set_save_attempted, set_edit_readback,
set_save_readback, save_attempted, save_succeeded, relock_attempted,
relock_succeeded, source_file_sha256,
source_layer_snapshot_sha256, presentation_file_sha256,
presentation_layer_snapshot_sha256, presentation_path_identity,
source_path_identity}`. `presentation_layer` and
`source_root_layer` are exact
`{identifier, real_path, device, inode, link_count}` objects. Identity preflight
order is source then presentation. Before a layer is fully verified, all five
values are null; raw or partially verified strings are never persisted.
Successful verification atomically replaces the whole object with two
canonical strings and three plain integers. Thus the only legal forms are
all-null or all-non-null. A presentation preflight failure may coexist with a
fully verified source object because source is checked first; a source failure
leaves both objects all-null. `PASS` and every post-preflight failure require
both objects fully populated.
Each permission object has exact keys `{before_recovery, after_recovery,
after_save, after_relock}`, and every reached value is exact
`{permission_to_edit, permission_to_save}`. Each SHA object has the same four
phase keys. Each path-identity object has the same four phase keys, and every
reached value is exact
`{real_path, file_type, device, inode, link_count}` with
`file_type=regular_non_symlink` and `link_count=1`. Source identity must equal
preflight at every reached phase. Presentation identity must equal preflight
through `after_recovery`; `after_save` establishes its one permitted post-save
identity. `after_relock` must equal the most recent non-null pinned identity:
`after_save` when available, otherwise `after_recovery`, otherwise
`before_recovery`. Unreached phase values are
JSON `null`, never omitted. `status` is
`PASS` exactly when `failure_stage=null`, save/relock are true, all four final
permissions are the required locked states, and every source identity/hash is
unchanged; otherwise it is `FAIL` and `failure_stage` is one of
`IDENTITY_PREFLIGHT`, `SET_EDIT`, `SET_SAVE`, `RECOVERY_READBACK`, `SAVE`,
`POST_SAVE_EVIDENCE`, `POST_SAVE_SOURCE_GUARD`, or `RELOCK`.

Primary failure precedence is execution order: identity preflight, edit setter,
save setter, recovery readback, Save call/result, post-save presentation
hash/snapshot/path-identity capture, post-save source guard including its
path-identity check, then relock/readback and both post-relock path-identity
checks. The first failed phase fixes `failure_stage` and is never overwritten.
A later best-effort relock failure sets only
`secondary_failure_stage=RELOCK`; otherwise that field is null. If relock is the
first failure, primary `failure_stage=RELOCK` and the secondary field is null.
Exceptions while reading a reached phase leave that phase's value null,
preserve all earlier observations, and map to that phase. This same precedence
and null-state validator applies to success and partial contracts.

There is exactly one relock block: the common `finally` exit. Normal execution
has no separate relock call and the finally block never retries. It runs for
every fully verified presentation object once its preflight permission pair has
been successfully read and the recovery/readback lifecycle has therefore
begun, regardless of whether a recovery setter or Save was attempted. Set
`relock_attempted=true`, call edit-false once and save-false once in that order
even if the first raises, then perform one paired permission readback and one
path-identity observation. `relock_succeeded=true` only when neither
setter/getter raised, both permissions are false, and the observed identity
equals the most recent non-null pinned identity. The first main-path failure
remains primary; a failed common relock sets
`secondary_failure_stage=RELOCK`. When the main path had no failure, relock
failure is primary `RELOCK` and secondary remains null. No later success may
erase either result. A Save-success/relock-failure
file is not deleted or reused: the cell is permanently `FAILED`, its partial
file/hash is quarantined inside that immutable failed cell root, and the normal
absent-output-root plus predecessor-chain gates forbid rerunning or consuming
it as success.

## Files

Modify:

- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`;
- `tests/test_real_beaker_runtime_contract.py`;
- `docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-plan-v3-reviews.md`
  after reviews and verification.

Add:

- `tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_004.sh`.

Do not modify or delete `_003`, accepted authority, source USD, localized assets,
physical traces, `_001`, or `_002` evidence. Keep the `_003` orchestrator as a
historical implementation member. Add this recovery plan and the `_004`
orchestrator to the `_004` implementation identity.

The live canonical runner moves atomically to `_004` constants for experiment
ID, aggregate root, identity/pre/post-freeze, and lock; the `_004` CLI rejects
all `_003` roots, freezes, locks, intents, and cell paths. Historical `_003`
semantic validation remains represented by its frozen implementation/archive,
published authority, and the pre-change terminal attestation, not by allowing a
live `_004` invocation to reinterpret or append `_003`.

Upgrade the protected registry ID to
`real_beaker_ao_rt_matrix_v3_protected_registry_v2`. Its exact new members are:

- protected root: the complete `_003` aggregate root, including anchor, first
  intent/failure, fixed status evidence, authority journal, and decision
  authority;
- protected files: `_003` implementation identity, pre-freeze, post-freeze,
  aggregate lock, and terminal-validation attestation.

The `_004` pre-freeze test must prove any missing, non-regular/non-directory,
symlinked, byte-changed, or membership-changed `_003` object blocks launch.

Registry v2 uses the existing deterministic schema without a new ad hoc
serializer. `snapshot_render_diagnostic_protected_registry` emits exact
`{schema_version=1, registry_id, protected_roots, protected_files}`. Root order
and file order must equal the constant tuples. Each root record is exact
`{root_path, files}` with canonical no-symlink absolute `root_path`; `files` is
the recursively discovered, path-sorted, unique list of exact
`{path, byte_count, sha256}` relative records, rejecting symlinks and nonregular
members. Each external file record is exact `{path, byte_count, sha256}` with
the canonical no-symlink absolute path. Snapshotting twice must be identical;
the complete snapshot is written create-exclusively into `_004` pre-freeze and
validated by exact recomputation. The new constant tuples add exactly one root
(`_003` aggregate) and exactly five external files (identity, pre, post, lock,
attestation); none is inside that aggregate root.

The `_004` lifecycle remains the established one: create implementation
identity, then pre-freeze; the formal launcher requires and byte-verifies both.
On first cell launch the parent creates the lock, binds it to the atomically
published anchor/root/first intent, and every later cell validates the chain.
Post-freeze is not a prelaunch input: it is create-exclusively generated under
the bound lock only by terminal aggregation after success or failure, then
bound into decision authority and the lock witness. Tests retain that ordering.
The implementation identity includes every `tools/labutopia_fluid/*.py`, both
historical/current orchestrators, the pipe wrapper, plans, and qualification
tests. The `_004` orchestrator fixes interpreter, runner, authority, cwd,
arguments, 16-slot order, and output/log paths; the replay parent rehashes the
identity before intent and after child exit.

## TDD

1. Add parameterized failing export tests for edit-only false, save-only false,
   and both false. Keep the source root doubly locked and require the exact
   successful evidence schema, saved artifacts, source byte/snapshot identity,
   presentation relock, and source-lock preservation.
2. Add alias/boundary tests: root object, equal identifier/real path, anonymous
   layer, wrong expected path, and wrong edit target all fail before setters and
   leave source permissions/bytes unchanged.
3. Fault-inject preflight permission getters raising; each setter raising; each
   immediate setter getter raising/remaining false; final paired recovery
   getter raising/remaining false; `Save()` returning false/raising;
   post-save presentation FD/hash/snapshot/identity failure;
   `POST_SAVE_SOURCE_GUARD` hash/snapshot/identity failure; and every relock
   setter/getter/identity failure. Test collisions of each main-path failure with
   relock failure. Require exact primary/secondary precedence, exactly one
   relock attempt, the dedicated partial contract, unchanged locked source,
   absent static entry, and no successful export evidence.
4. Replace either pinned path with a same-byte new inode or hardlink alias after
   the post-save FD pin, after relock, and during capture. Require fail-closed
   behavior at every phase, including when SHA-256 is unchanged, and require
   the partial recovery or capture lock contract to identify the path-identity
   mismatch. Fault-inject replacement during the FD read and require the
   descriptor/path/component before/after checks to reject it.
5. Prove the legitimate presentation inode transition across `Save()` is
   accepted and recorded while any source transition is rejected. Replace a
   file specifically after recovery completes but before capture lock
   acquisition; require the expected export identities to reject it rather than
   adopting a new capture baseline. Add an extra hardlink without changing the
   pinned name/inode and require `link_count!=1` to fail.
   Verify saved descriptor bytes exactly equal the in-memory layer serialization
   and document that a same-UID concurrent race before the first post-save open
   is outside the sealed single-writer experiment model.
6. Validate the exact successful/partial recovery schemas and their binding
   into candidate/failure manifests and cell evidence. Extra/missing/mistyped
   or inconsistent fields fail validation. Validate the exact three-record,
   self-hashed `capture_persistent_layer_baseline`; missing/duplicate/wrong-role
   records or any mismatch at capture entry fail before locks are accepted.
7. Update canonical experiment/protected-registry tests for `_004`, registry
   v2, the exact `_003` root/external-file set, immutable terminal attestation,
   and cross-version path rejection.
8. Add exact `_004` orchestrator plan/preflight tests: the same sixteen slots,
   authority and runtime parameters; no `_003` path reuse; absence of `_004`
   identity/pre-freeze causes zero log/lock/root side effects; invalid resume,
   preexisting formal logs, and mismatched launcher/freeze bytes fail closed.
9. Implement the permission-recovery helper immediately before
   `presentation_layer.Save()`, its exact validator, successful export binding,
   dedicated exception, and runtime-failure-manifest binding. Execute the one
   common-finally relock/readback after the main path exits; do not add a
   separate post-save relock call.
10. Implement the exact FD-pinned file evidence helper, three-file
    `capture_persistent_layer_baseline` producer/validator, capture-entry
    compare-not-redefine check, and post-capture identity verification.
11. Move live constants to `_004`; implement registry v2, immutable `_003`
    terminal-attestation semantic validation, `_003` protected membership, and
    cross-version path rejection.
12. Add the `_004` orchestrator, update implementation-identity membership, and
    wire exact launcher/freeze/log paths without modifying `_003`.
13. Record the completed plan/implementation review and verification results in
    the existing review log before freeze.

## Verification

1. Run focused export, registry, identity, launcher, and failure-state tests.
2. Run `py_compile`, `bash -n`, and `git diff --check`.
3. Run the complete runtime-contract suite and the related 230-test suite with
   only the three documented historical-runner rebuild tests deselected.
4. Run an automated, non-skipped Isaac 4.1 `/tmp` smoke that deliberately starts
   with a dirty `permissionToSave=false` presentation layer and verifies the
   exact evidence schema, successful save, immediate presentation relock,
   source-root lock/hash/path-identity preservation, the legitimate one-time
   presentation inode transition across Save, and capture-stage entry/post
   checks against export-supplied identities for the static/presentation/source
   used-layer set, canonical paths, regular non-symlink types, link counts,
   devices/inodes, hashes, dirty flags, and locks.
   Unit-level fault injection covers controlled same-byte inode replacement and
   hardlink rebinding after save/relock and during capture, and proves
   `verify_capture_persistent_layers_unchanged` rejects them; the Isaac smoke
   covers the actual success path because deliberately mutating a live capture
   dependency would only duplicate that deterministic validator while adding
   no renderer-specific behavior.
5. Obtain independent architecture, completeness/edge-case, and risk `GO`
   reviews against the final bytes. Implementation may proceed after the plan
   reviews; these final implementation reviews gate `_004` freeze/launch and
   publication, not writing the implementation itself.
6. Confirm all `_004` formal paths and logs are absent, then create the `_004`
   implementation identity and pre-freeze. Make no protected edits afterward.
7. Launch only through `run_real_beaker_ao_rt_matrix_v3_004.sh`; stop on the
   first failed slot. After sixteen successes, run machine aggregation, repeat
   stability, blinded visual review, deterministic unblinding, and final
   authority publication.

## Acceptance

The repair passes only when the source root remains byte-identical and locked,
the exact presentation layer alone is made writable for its first save, the
recovery and relock are explicit in evidence, all failure branches are
diagnostic and produce no successful export, `_003` remains byte- and
semantics-attested, `_004` cannot accept `_003` paths, and all three final
reviewers return `GO`. It does not by itself make any visual or causal claim.

# Real-Beaker AO/RT Matrix Final Hardening Plan

## Purpose

Close the final implementation-review findings before creating any v3 freeze,
aggregate root, launch intent, or official Isaac output. This amendment is
normative together with the reviewed v3 matrix plan. Where this amendment is
more restrictive, it takes precedence. It does not change the 2x2 treatments,
balanced order, cameras, frames, visual gates, or claim boundary.

## Files

Modify:

- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`;
- `tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`;
- `tools/labutopia_fluid/run_real_beaker_static_hold_matrix.py`;
- `tests/test_real_beaker_runtime_contract.py`;
- the v3 review log after each review round.

Do not modify any accepted authority, source USD, localized asset, physical
trace, prior evidence, or formal v3 output. All formal v3 paths must remain
absent until this plan has three independent GO reviews and all tests pass.

## Product Integrity Boundary (Normative Override)

This experiment answers a rendering-product question: whether the black/ink-like
liquid appearance in the accepted real-beaker scene is caused by ambient
occlusion and/or ray-tracing accumulation settings. It is a reproducibility and
mix-up-prevention protocol, not a hostile-forensics or code-signing system.
Where later sections use stronger security language, this section defines the
acceptance boundary and takes precedence.

The launcher, current Unix account, kernel, CPFS implementation, Isaac 4.1
installation, GPU driver, and child process are trusted. Concurrent or timed
same-UID mutation, a malicious launcher that supplies self-consistent forged
archive bytes/hashes, native loader injection by the trusted environment, and
filesystem violation of documented `flock`/rename/fsync behavior are outside
scope. Hashes, pinned reads, read-only modes, the sealed archive, freezes, and
journals detect ordinary drift, stale paths, accidental replacement, partial
writes, and cooperating concurrent writers; they are not claimed as an
independent cryptographic trust root. The runtime may compare the complete
frozen implementation projection immediately after its first sealed first-party
import because the parent/bootstrap pair is trusted.

After an authority witness is durable, recovery may revalidate and retry only
the same nonce-bound staging directory and the same decision/commit/closure
bytes. It may not rebuild or replace those bytes. A transient guard, rescan, or
rename exception does not itself create a permanent poison marker; persistent
identity, membership, hash, semantic, journal, or witness mismatch still fails
closed. This retry model is the normative crash behavior for the current
trusted-runner implementation.

`validate_render_diagnostic_final_closure_snapshot` validates a detached
semantic evidence snapshot and may be used after the live aggregate is gone.
It does not by itself prove that the snapshot was the published authority.
`validate_render_diagnostic_decision_authority` is the stronger live
publication check and additionally requires the anchor-bound lock witness,
external journal, embedded intent, decision commit, and authority inode. The
current closure hash is bound by the decision commit and witness; duplicating
the publication nonce and intent hash inside the generic closure manifest is
not required. The aggregate producer supplies exactly the three fixed external
files, while the generic closure helper remains reusable for tests and
non-authority snapshots.

The renderer consumes stable cell-local pathnames after preboot copy/hash/mode
validation and Isaac postboot resolution validation. Holding one cell-root
directory FD for the entire render, signed archives, cross-host lock proofs,
and exhaustive fault injection at every individual syscall are defense-in-depth
follow-ups, not gates for this causal matrix. Required gates are the named
functional and adversarial regression suites actually present, a real Isaac
startup/resolver smoke, three independent reviews under this boundary, exact
formal-path absence before freeze, and the sixteen fresh-process cells.

## CPFS First-Root Publication Recovery (Normative Override)

The first `_001` launch stopped before `SimulationApp`: CPFS returned `EINVAL`
for `renameat2(RENAME_NOREPLACE)` while publishing the initial aggregate root.
The external lock had already durably bound the staging inode, and the failure
cleanup removed that staging directory. Therefore `_001` is permanently
poisoned: preserve its lock, implementation identity, pre-freeze, and fixed
failure report; do not recreate its missing root or reuse its experiment ID.

The replacement experiment is exact ID and aggregate root
`real_beaker_ao_rt_matrix_v3_20260712_002`. Its fixed files are:

- `real_beaker_ao_rt_matrix_v3_20260712_002_implementation_identity.json`;
- `real_beaker_ao_rt_matrix_v3_20260712_002_protected_tree_freeze_pre.json`;
- `real_beaker_ao_rt_matrix_v3_20260712_002_protected_tree_freeze_post.json`;
- `.real_beaker_ao_rt_matrix_v3_20260712_002.aggregate.lock`.

Register the preserved `_001` identity, pre-freeze, lock, and failure report as
protected files in `_002`. The absent `_001` aggregate and cell are recorded in
the report and are never synthesized.

For directory publication on CPFS, first attempt
`renameat2(RENAME_NOREPLACE)`. Only `EINVAL`, `ENOSYS`, or `EOPNOTSUPP` may enter
the compatibility path. While the caller still holds the unique anchor-bound
experiment lock, revalidate both pinned parent identities, require the target
to be absent by atomically creating an empty target directory reservation with
dirfd-relative `mkdir`, fsync the target parent, and bind the reservation inode.
Immediately before publication, require that exact reservation inode to remain
an empty directory, then call dirfd-relative atomic `rename` to replace only
that empty reservation. Revalidate that the published target has the exact
source `(st_dev, st_ino)`, fsync both parent descriptors, and recheck their
pinned identities. If rename fails, remove the reservation only when it is
still the exact bound empty inode; changed or nonempty reservations are
preserved and fail closed. Existing targets still raise `FileExistsError`; all
other errors remain failures. This fallback prevents cooperating writers and
ordinary target creation/replacement under the trusted-runner boundary. A
deliberately racing same-UID writer that removes and recreates the exact empty
reservation remains outside scope as already declared.

TDD must cover normal `RENAME_NOREPLACE`, CPFS `EINVAL` fallback with inode
preservation, existing-target rejection without fallback replacement,
concurrent content added to the reservation, reservation cleanup after a local
rename failure, and unexpected-error rejection. A persisted real same-mount
probe must demonstrate that directory `os.rename` replaces an empty reservation
with the source inode before `_002` freeze.

## Sealed-Child Standard-FD Recovery (Normative Override)

The `_002` first root and launch intent published successfully through the CPFS
reservation fallback, proving that recovery. The child then stopped in the
sealed bootstrap before importing first-party code or starting `SimulationApp`
because the operator redirected stdout/stderr directly to a regular log file.
The bootstrap correctly permits standard FDs 0-2 only when each is a character
device, FIFO, or socket. `_002` therefore contains one valid failed launch and
must not rerun that slot.

Preserve the complete `_002` aggregate as a protected root and its identity,
pre-freeze, and lock as protected files. The final replacement experiment uses
exact ID/root `real_beaker_ao_rt_matrix_v3_20260712_003` and fixed files:

- `real_beaker_ao_rt_matrix_v3_20260712_003_implementation_identity.json`;
- `real_beaker_ao_rt_matrix_v3_20260712_003_protected_tree_freeze_pre.json`;
- `real_beaker_ao_rt_matrix_v3_20260712_003_protected_tree_freeze_post.json`;
- `.real_beaker_ao_rt_matrix_v3_20260712_003.aggregate.lock`.

Do not weaken the bootstrap FD contract. Invoke each `_003` launcher with its
stdout/stderr connected to a pipe. A separate `tee` process may persist that
pipe to an exclusively opened direct-`/tmp` log descriptor; direct child
redirection to a regular file is forbidden. The only admitted launcher wrapper is
`tools/labutopia_fluid/run_sealed_child_with_pipe_log.sh`, called exactly as
`<wrapper> --log /tmp/<cell>.log -- <launcher command...>`. It enables
`pipefail`, executes `child 2>&1 | tee` with `tee` stdout bound to that descriptor,
and immediately
captures both `PIPESTATUS[0]` (launcher) and `PIPESTATUS[1]` (`tee`). Both must
be zero; a nonzero `tee` returns 74 before otherwise returning the launcher
status. The wrapper rejects non-absolute/non-`/tmp` logs and symlinks.
Include it in implementation identity. Before `_003` freeze, retain the
existing bootstrap FD fault tests and test the wrapper for allowed FDs, child
status propagation, and tee failure.

The final wrapper atomically create-exclusively opens the direct `/tmp` log
under `noclobber`, then runs `tee` without a pathname and directs its stdout to
that already-open descriptor. No check/open path race remains for other UIDs;
same-UID replacement remains outside the declared boundary. A nonzero `tee`
status takes precedence and returns `74`, because the child may also receive
`SIGPIPE` after logging fails. Only when `tee` succeeds does the wrapper return
the child's nonzero status. The formal orchestrator uses the regular, nonlink
`bin/python3.10` interpreter and requires the fixed implementation identity and
pre-freeze to be regular nonlinks before opening a log or invoking Python.

## Authority Additions

Add the exact root
`/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/outputs/usd_asset_packages/lab_001_localized_20260707`
to the protected-root registry. It contains the USD, MDL, and texture
dependencies reached from the support-aligned source layer. The pre-freeze must
record every non-symlink regular file under this root with the existing pinned
tree schema. Also add the exact Isaac 4.1 version-matched MDL source root
`/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/omni/mdl/core`.
The latter is a source authority only: each cell copies the required files into
its own material closure before `SimulationApp` starts and verifies their source
hashes against the pre-freeze.

System-Python dependency discovery is not authoritative for the formal render.
The observed Isaac 4.1 resolver selects its installed `OmniGlass.mdl`,
`OmniPBR.mdl`, and `OmniSurfacePresets.mdl` after startup even when system pxr
selects files from the localized package. Therefore dependency validation has
three ordered phases: preboot source publication performs pinned copy/hash/mode
checks without importing pxr; preboot material publication mirrors the frozen
version-matched MDL files and installs their Kit search-path arguments; after
`SimulationApp` construction and settings readback, Isaac's own resolver must
report zero unresolved USD-authored assets and every resolved layer, texture,
or top-level MDL asset must be inside the cell's source snapshot or material
closure. After static export, repeat that check with the candidate directory as
the only additional allowed root. Any observed host/default-path fallback fails
the cell. The material closure contains every `Base/*.mdl` file and the complete
regular-file tree under `mdl/`, including NVIDIA support modules and MDL
standard modules; search-path readback must place it before defaults. This
closes the available module tree but does not claim unavailable Isaac 4.1
per-module renderer-consumption instrumentation.

Expand the fixed implementation identity and protected-file registry to include
the test files actually used to qualify the runtime path:

- `tests/test_real_beaker.py`;
- `tests/test_real_beaker_matrix_isaac_runtime.py`;
- `tests/test_real_beaker_strict_step_schedule.py`;
- `tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py`.

The original v3 plan remains an implementation member, and this amendment is
an additional fixed implementation/protected member.

## Sealed Runtime Implementation

The parent must not execute the runtime child from mutable repository paths.
After verifying the frozen implementation and before spawning the child, it
builds one deterministic `ZIP_STORED` archive in memory from pinned reads of
every frozen `tools/labutopia_fluid/*.py` member. Each archive source hash must
equal the frozen identity. The archive also contains exact empty synthetic
`tools/__init__.py` and `tools/labutopia_fluid/__init__.py` entries. ZIP
timestamps, permissions, ordering, and compression are fixed.

The runtime-archive evidence object is exactly `{schema_version, archive_id,
source_files, synthetic_files, archive_sha256}`. `archive_id` is
`matrix_runtime_implementation_archive_v1`; `source_files` is the exact
path-sorted tool-only projection of the frozen implementation's
`{path, sha256}` records; `synthetic_files` is the exact path-sorted list of
`{path, sha256}` for the two fixed synthetic entries; and `archive_sha256` is
the SHA-256 of the final ZIP bytes. The fixed pre-import bootstrap source is
persisted as exact UTF-8 bytes at fixed cell-relative path
`runtime_bootstrap.py` and bound by `runtime_bootstrap_sha256`. The
runtime-archive evidence object is stored in the replay final manifest, while
`runtime_implementation_archive_sha256` always means
`canonical_json_sha256_v1(runtime_implementation_archive)`, never the ZIP-byte
hash. The hidden child option carries the distinct ZIP-byte `archive_sha256`.

Write the completed archive bytes to a Linux `memfd`, apply
`F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL`, reopen it read-only, and
close the writable descriptor before child creation. Launch the child as
`python -I -S -c <fixed-bootstrap> ...`; do not execute archive `__main__`.
The bootstrap uses only built-in/standard-library modules, and before any
first-party import it parses `/proc/self/cmdline`, requires the exact `-c`
argument position, hashes those exact argument bytes, and compares them with
`runtime_bootstrap_sha256`. It then verifies the archive FD mode/seals,
ZIP-byte hash, entry projection, `sys.modules`, `sys.meta_path`, `sys.path_hooks`,
and absence of live-repository modules/paths. It then installs only the sealed
archive plus an exact parent-recorded allowlist of external stdlib/Isaac/native
dependency paths and imports replay `main`. No `.pth`, `site`, `sitecustomize`,
`usercustomize`, user-site, repository `PYTHONPATH`, or preloaded first-party
module participates. Runtime-relevant root discovery accepts one exact
`LABUTOPIA_REPO_ROOT` environment value for data paths while retaining the
current default outside archive mode. External Python, Isaac, and native
dependencies remain recorded runtime dependencies, not frozen first-party
bytes.

Use `close_fds=true` and exact `pass_fds=(lock_fd, archive_read_fd)`. The hidden
single-use runtime options carry both descriptor numbers and the archive hash.
Before any output, the bootstrap enumerates `/proc/self/fd`: only standard FDs
plus the two declared descriptors may survive exec. It requires distinct FDs; a
regular anchor-bound lock FD with the existing held-flock proof; a regular
read-only archive FD with exact seals/hash; and no writable alias to the
archive, protected inputs, aggregate, or cell. FDs 0-2 must be character
devices, FIFOs, or sockets; they may not be directories, regular protected
objects, or aliases of lock/archive/aggregate/cell identities regardless of
access mode. The bootstrap validates every archive entry before invoking replay
`main`.

Persist the exact ZIP bytes create-exclusively at fixed cell-relative path
`runtime_implementation_archive.zip`, require its byte hash to equal
`archive_sha256`, and include it in the artifact inventory/final closure. The
persisted `runtime_bootstrap.py` bytes must equal the `-c` bytes and are also in
artifact inventory/final closure. The final manifest stores exact
`runtime_implementation_archive`,
`runtime_implementation_archive_artifact` (`{path, sha256}`),
`runtime_bootstrap_artifact` (`{path, sha256}`),
`runtime_bootstrap_sha256`, and `inherited_fd_contract`. Closure validation
rebuilds the archive projection from the persisted ZIP bytes and recomputes all
archive, bootstrap, and FD-contract bindings.

No repository script/helper replacement between freeze checkpoints can change
the bytes executed by the child. A live implementation mismatch still
terminates the cell even though the child code archive is immutable.

## Runtime Source Snapshot

Every diagnostic child creates `<cell>/source_dependency_snapshot` before
opening any USD stage. It copies the exact support-aligned package root and
localized package root through pinned descriptors into a sibling staging tree,
compares every byte to accepted pre-freeze records, rejects symlink/nonregular
members, uses create-exclusive writes, fsyncs files/directories, makes the tree
read-only, and atomically renames it into place. Source drift before, during, or
after copying fails the cell.

The fixed snapshot subdirectories are
`lab_001_level1_pour_support_aligned_v1_20260712` and
`lab_001_localized_20260707`, preserving the entry layer's existing `../`
reference. Publish `<cell>/matrix_source_dependency_closure.json` with exact
schema `{schema_version, closure_id, source_roots, entry_source_usd_path,
snapshot_entry_source_usd_path, files, source_dependency_closure_sha256}`.
`closure_id` is `support_aligned_source_dependency_closure_v1`.
`source_roots` is this canonical two-record list in the preceding order; each
record is exact `{source_root, snapshot_subdirectory}` with an original absolute
root and one fixed single-component relative subdirectory. The original
`entry_source_usd_path` is absolute. `snapshot_entry_source_usd_path` is exact
normalized relative POSIX path
`lab_001_level1_pour_support_aligned_v1_20260712/lab_001_level1_pour_support_aligned_v1.usda`.
Every `files[].path` is normalized relative to the whole snapshot, begins with
exactly one fixed subdirectory, and each record is exact `{path, byte_count,
sha256}`. Records are path-sorted and cover every copied file. The hash excludes
only itself, so all sixteen cells have an identical source-closure hash.

Open the source and generated static layers through a directory FD pinned to
the cell root for the complete render operation. Generated layers retain
portable relative references to the persistent source snapshot, never dead
`/proc` paths. Validate the source closure before the first stage open and after
the last capture. Preboot validation is byte-only and must not call pxr. The
first postboot validation records `runtime_dependency_resolution`, including
the exact entry, allowed roots, resolved layers/assets, unresolved list,
outside-root list, status, and canonical hash. Live attachment recomputes this
contract with Isaac's resolver; detached closure validation verifies the
captured contract and every frozen dependency byte. The artifact validator
reconstructs the source and material closures and rejects every extra, omitted,
or changed copied member.

Source-snapshot publication uses fixed journal
`<cell>/source_dependency_snapshot_intent.json`, exact `{schema_version,
experiment_id, cell_root, target_path, staging_path, publication_nonce,
expected_source_dependency_closure_sha256, generated_at_utc,
source_snapshot_intent_sha256}`. The nonce is 64 lowercase hex; target is fixed;
staging is exact `<cell>/.source_dependency_snapshot.<nonce>.staging`. Publish
the journal before creating staging via strict same-directory temporary
`.source_dependency_snapshot_intent.<nonce>.tmp`: create/write/file-fsync,
cell-directory fsync, fixed-name hard link, directory fsync, temporary unlink,
directory fsync. Then mkdir staging and fsync the cell directory; copy/fsync all
declared source files; fsync directories bottom-up; apply read-only modes; fsync
directories bottom-up again; atomically rename staging to target with no
replacement; fsync the cell directory; validate target; unlink the fixed
journal; and fsync the cell directory. A successful cell retains no source
snapshot intent or temporary file.

On recovery, fixed journal with absent target/staging resumes staging creation.
Journal plus strict staging always performs authenticated cleanup and rebuild:
the staging inode/name must be stable; membership must be a subset of the
declared two-root tree; links/nonregular/unknown paths
poison; known partial files are unlinked without chmod; directories are made
owner-writable bottom-up only as needed, removed, and the cell directory is
fsynced. Exact target validates, removes the journal, and resumes idempotently;
mismatched target poisons. Strict
temporary without fixed journal is validated then removed/fsynced; fixed journal
plus same-inode temporary unlinks it and resumes; unknown temporary names or
identity drift poison. Thus every create/write/fsync/chmod/rename crash has one
cleanup, resume, idempotent, or poison transition.

CPFS provides neither fs-verity nor a different-UID/read-only mount boundary.
This source snapshot therefore prevents ordinary path replacement and detects
stable or observed drift, but does not claim prevention or reliable detection
of a deliberately timed same-UID process that rewrites a dependency only while
the USD/MDL/texture resolver consumes it and restores it before the post-check.
Such an actor is outside the experiment integrity boundary, and the final claim
must state this limitation.

## Exact Schema Amendments

The successful-cell sidecar set is now exactly
`matrix_frame_bindings.json`, `matrix_media_index.json`,
`matrix_cell_evidence.json`, `matrix_implementation_identity.json`,
`runtime_identity.json`, `device_identity.json`, `process_identity.json`,
`matrix_mdl_closure.json`, `matrix_source_dependency_closure.json`, and
`matrix_cell_artifact_inventory.json`. The replay final manifest's
`matrix_sidecars` object has exactly these ten literal keys:
`matrix_frame_bindings`, `matrix_media_index`, `matrix_cell_evidence`,
`matrix_implementation_identity`, `runtime_identity`, `device_identity`,
`process_identity`, `matrix_mdl_closure`,
`matrix_source_dependency_closure`, and `matrix_cell_artifact_inventory`.
Each value is exact `{path, sha256}` at the corresponding fixed basename. The
final manifest additionally has exact top-level
`runtime_implementation_archive`, `runtime_implementation_archive_artifact`,
`runtime_bootstrap_artifact`, `runtime_bootstrap_sha256`,
`inherited_fd_contract`, and
`source_dependency_closure` and `runtime_dependency_resolution` objects equal
to validated evidence. The archive
artifact is exact `{path, sha256}` with fixed cell-relative basename and the
ZIP-byte hash. Failure manifests remain the exact v3 failure schema and do not
synthesize success-only snapshot fields.

Process identity is exactly `{schema_version, launcher_pid, child_pid,
parent_child_fresh_process, cold_start, launch_intent_sha256,
runtime_implementation_archive_sha256, inherited_fd_contract_sha256,
process_identity_sha256}`. The inherited-FD contract is exactly
`{schema_version, standard_fds, lock_fd, archive_fd, lock_access_mode,
archive_access_mode, archive_seals}` with `standard_fds=[0,1,2]`, distinct
positive descriptor ints, `lock_access_mode=READ_WRITE`,
`archive_access_mode=READ_ONLY`, and the exact four sorted seal names above.
The final manifest's full `inherited_fd_contract` object is authoritative;
`inherited_fd_contract_sha256` is its canonical JSON hash. Closure validation
rebuilds that object and requires exact equality with process identity.

Matrix-cell evidence is the exact v3 successful-cell schema plus four required
64-hex fields `runtime_implementation_archive_sha256`,
`runtime_bootstrap_sha256`, `source_dependency_closure_sha256`, and
`artifact_inventory_sha256`. The
artifact inventory is exact `{schema_version, inventory_id, files,
artifact_inventory_sha256}` with
`inventory_id=matrix_cell_runtime_artifact_inventory_v1`; `files` is an exact
cell-relative path-sorted list of `{path, byte_count, sha256}` covering every
runtime-child artifact except `replay_manifest.json`, the inventory itself, and
the other nine fixed matrix sidecars. Artifact closure requires exactly the
inventory members plus replay manifest and all ten fixed sidecars; no other
cell-root member is legal.

The matrix-validation equality-name set is the v3 set plus exact names
`runtime_implementation_archive`, `runtime_bootstrap`, and
`source_dependency_closure`; all must be byte/hash equal across all sixteen
cells. Persisted ZIP-byte hashes must also be equal across cells. Runtime
implementation archive and bootstrap, inherited-FD
contract, source dependency closure, process identity, artifact inventory,
final manifest, and all sidecars are rebuilt from authoritative bytes during
closure validation, not trusted as declarations.

## Collision-Free Copy

Replace MDL `shutil.copy2` writes with pinned source reads and destination
`O_CREAT|O_EXCL|O_NOFOLLOW` writes relative to pinned parent directories.
Require one link before and after each write and exact expected source hash.
Reject a pre-existing destination, symlink, hardlink, parent replacement, or
membership drift. Apply the same primitive to source snapshot copies. Runtime
implementation is the sealed archive and never uses a writable pathname.

## Anchor-Bound Lock Journal

Amend the experiment anchor with required
`experiment_binding_sha256`. The external lock is zero bytes only between its
create-exclusive creation and first-root staging. After the staging root inode,
anchor, and first intent are complete but before root rename, write one compact
JSON line to the held lock FD and file-fsync it. The line is exact
`{schema_version, record_type, experiment_id, aggregate_root,
aggregate_root_device, aggregate_root_inode, lock_device, lock_inode,
anchor_projection_sha256, generated_at_utc, experiment_binding_sha256}` with
`record_type=EXPERIMENT_BINDING`; its hash excludes generated time and itself.
`anchor_projection_sha256` is the canonical hash of the complete anchor payload
excluding only `anchor_sha256` and `experiment_binding_sha256`. The anchor's
binding field equals the binding hash; the final anchor hash then includes that
field, so construction is acyclic. Then atomically rename the already-bound
staging root to the fixed aggregate path and fsync its parent.

Every later lock acquisition requires the first lock line, fixed lock inode,
fixed aggregate path/inode, anchor projection/final hash, and binding hash to agree before any
read or write. A root replaced under the same lock inode cannot synthesize a new
anchor because code never rewrites the first lock line. Empty/malformed binding,
binding with absent root after bootstrap, extra lock content before authority
witness, or any mismatch is poisoned. The lock journal is append-only: code
never truncates, overwrites, or recreates its inode.

This prevents accidental replacement and cooperating/ordinary concurrent
writers. As declared in the v3 threat boundary, it does not claim to stop a
deliberately malicious same-UID process from ignoring advisory flock and using
`chmod`/`pwrite` on the lock inode; CPFS offers no enforcement primitive for
that threat in this environment.

## Atomic Decision Authority

The v3 top-level `matrix_decision.json` path is superseded. Decision authority is
one fixed directory `<aggregate>/matrix_decision_authority`, atomically renamed
from a sibling staging directory. For states 2-6 it contains exactly
`matrix_decision.json`, `decision_commit.json`, and
`publication_intent.json`. For states 7-8 it additionally contains exact
subdirectory `final_closure`. No member is authoritative outside that directory
or before the directory rename.

The commit object is exact `{schema_version, experiment_id, authority_path,
authority_device, authority_inode, decision_sha256, anchor_sha256,
closure_snapshot_sha256, publication_intent_sha256, publication_nonce,
generated_at_utc,
decision_commit_sha256}`. `authority_path` is the fixed absolute directory;
closure hash is nullable only for states 2-6; the nonce is 64 lowercase hex;
hash payload excludes generated time and its own hash. For states 7-8 the commit
also binds the complete embedded closure manifest hash and embedded publication
intent hash. The decision uses a
deterministic `generated_at_utc` derived from its terminal evidence, so deleting
and rebuilding all authority markers cannot silently change decision bytes.

Use the anchor-bound external lock journal as the independent, non-rebuildable
publication witness. Before witness publication the lock contains exactly the
single valid experiment-binding line above. The witness object is exact
`{schema_version, record_type, experiment_id, experiment_binding_sha256,
authority_path,
authority_device, authority_inode, lock_device, lock_inode,
publication_intent_sha256, decision_sha256, decision_commit_sha256,
closure_snapshot_sha256, publication_nonce, generated_at_utc,
authority_witness_sha256}` with `record_type=AUTHORITY_WITNESS`. Closure hash is
nullable only for states 2-6. The witness hash excludes generated time and
itself. While holding the same exclusive flock, require exact one-line binding
content and EOF, encode the witness as a second sorted-key compact finite JSON
line, append it completely, file-fsync, and verify both lines/size/hashes. After
the append, only those exact two lines are legal. Partial/malformed/extra bytes
poison. Code never truncates, overwrites, replaces, or adds a third record.

The exact staging directory is
`<aggregate>/.matrix_decision_authority.<nonce>.staging`. The publication intent
is exact `{schema_version,
experiment_id, authority_path, staging_path, publication_nonce,
generated_at_utc, publication_intent_sha256}`. It depends on no closure,
decision, commit, or not-yet-created staging inode. Its external copy at
fixed `<aggregate>/authority_publication_intent.json` is only a recovery journal
and durable existence marker; consumers require its exact match but never derive
decision semantics from it.

Normative syscall order is: construct intent bytes; mkdir exact staging; fsync
the aggregate directory; write/file-fsync the exact
embedded `publication_intent.json` first; fsync staging; create/write/file-fsync
strict same-directory `.authority_publication_intent.<nonce>.tmp`; fsync the
aggregate directory; hard-link create-exclusively to the fixed journal; fsync
the aggregate directory; unlink the temporary; fsync the aggregate directory;
build and fsync embedded closure bottom-up when applicable; write/file-fsync
decision then commit; fsync
all staging directories bottom-up; apply read-only modes; fsync bottom-up again;
run state guards and a complete staging rescan; write/file-fsync the one-time
lock-inode witness; rerun the full
state guard and complete staging rescan; rename no-replace; fsync the aggregate
directory. A crash with only strict temporary is authenticated
cleanup; with temporary and fixed journal pointing to one inode, unlink the
temporary and resume; unknown/wrong-inode/malformed temporary names poison. No
temporary name remains at authority publication.

Immediately before publication, rerun full live guards for states 2-6 or
embedded-closure validation for states 7-8. Then descriptor-rescan the entire
staging tree, including decision, commit, embedded intent, every directory,
closure manifest, and every closure member, against captured
device/inode/type/link-count/byte-count/hash identities and exact membership.
Atomically
`renameat2(RENAME_NOREPLACE)` the complete staging directory to the authority
path and fsync the aggregate directory. The directory rename is the sole
acceptance linearization point; directory fsync is the durability barrier. If a
valid authority survives a crash before observed fsync completion, recovery
treats the rename as having linearized. No acceptance-revoking guard runs after
rename.

The first guard/rescan occurs before appending the witness and may still lead to
authenticated staging cleanup/rebuild. Once the witness second line is fully
fsynced, no evidence or decision is rebuilt. Recovery with witness+staging
reruns the exact second state guard and full staging rescan only to finish the
same rename. Persistent guard/rescan failure or staging mismatch fails closed;
a transient exception may be retried against the unchanged nonce-bound staging
generation. A successful rename remains linearized even if the following
aggregate-directory fsync reports failure.

Consumers require the anchor-bound lock witness and external journal to exist
and match embedded `publication_intent.json`, but trust decision semantics only from
the embedded intent, decision, commit, and closure bytes. They require authority
directory device/inode, exact state-dependent membership, hashes, nonce, and
closure/anchor/lock/witness bindings. Before witness creation, journal plus
matching staging and absent authority never adopts staged bytes: recovery
validates journal/name/inode and the declared state-specific path subset,
rejects links/nonregular/unknown members, removes known empty/partial/complete
staging, fsyncs the aggregate directory, and rebuilds from scratch before all
guards rerun.
Journal plus absent authority/staging is poisoned. After witness creation,
matching witness+journal+staging may only rerun guards/rescan and finish the same
rename; it may not rebuild staged bytes. Witness with neither exact staging
nor exact authority is poisoned.
Authority without exact witness/journal/embedded intent/commit, mismatch, or
partial authority is poisoned. Valid witness+journal+authority is
terminal/idempotent.
Staging without a fixed matching journal is removable only when empty or when
its embedded intent exactly authenticates the strict name/nonce and every
present path is in the declared state-specific allowlist; known partial file
hashes need not validate because they are never adopted. Links, nonregular or
unknown members, intent mismatch, or inode drift poison. Cleanup unlinks known
files without chmod, makes directories owner-writable bottom-up only as needed,
removes them, and parent-fsyncs.

## Embedded Final Closure

States 7-8 create final closure only at
`<authority-staging>/final_closure` under the anchor-bound lock. It is never
published first at `<aggregate>/final_closure`. The aggregate authority producer
supplies exactly these external logical/source pairs and no others:

- `external/implementation_identity.json` -> fixed implementation freeze;
- `external/pre_freeze.json` -> fixed pre-freeze;
- `external/post_freeze.json` -> fixed post-freeze.

The closure manifest is exactly `{schema_version, experiment_id,
snapshot_device, snapshot_inode, files, closure_snapshot_sha256}`. The generic
snapshot validator proves semantic membership and bytes. In authority mode the
decision commit binds this closure hash and the embedded publication intent;
the lock witness binds the commit, closure hash, publication-intent hash, and
nonce. Thus publication identity is checked by the authority validator rather
than duplicated inside the reusable closure manifest.

The recursive aggregate source walk excludes exactly the current strict
`<aggregate>/.matrix_decision_authority.<publication_nonce>.staging` subtree
that encloses this closure and fixed external recovery journal
`<aggregate>/authority_publication_intent.json`. The journal temporary must
already be absent. No other exclusion is legal. In particular, pre-existing
`<aggregate>/matrix_decision_authority`, old top-level `matrix_decision.json`,
old `<aggregate>/final_closure`, any other authority staging name, or any other
temporary/unknown aggregate member fails membership validation rather than
being skipped. The embedded `publication_intent.json` is outside the closure
and is hash-bound by the decision commit and lock witness.

Require manifest records to be strictly path-sorted. In authority production,
enforce the exact external set and aggregate structural allowlist, all
16 exact intent paths, all 16 exact cell roots and artifact memberships, three
fixed aggregate evidence files, fixed seal/anchor, and exact review files.
Extra or omitted closure members fail.

Nonce-bound authority staging left by a crash at closure
create/write/file-fsync/chmod or directory-fsync is never partially adopted.
Recovery validates journal/staging identity, descriptor-walks to reject links
or unknown members, makes it owner-writable only for cleanup, removes it,
parent-fsyncs, and rebuilds from scratch. Cleanup failure is retryable only while
the same exact staging inode remains; identity drift poisons. Fault tests cover
every intermediate boundary.

For states 7-8, open the closure root once and read every manifest member
exactly once through pinned `O_NOFOLLOW` descriptors. Require one link, unique
device/inode pairs, exact sorted manifest membership, byte count, and hash.
Retain immutable Python byte payloads for every JSON and PNG consumed by
reconstruction and immutable `{byte_count, sha256}` evidence for members never
decoded again. Construct one closure-authority object mapping only exact
original aggregate/external paths to captured payloads and tree records.
Decision reconstruction and all pre-publication guards use only this one captured
generation; requesting uncaptured bytes fails. No closure member pathname is
reopened.

The complete pre-rename staging rescan defined above includes decision, commit,
embedded intent, closure root/manifest, every closure member, every directory,
and exact state-dependent membership. Whole-root or descendant replacement
prevents publication. Because closure, intent, decision, and commit are children
of the one staging inode preserved by rename, the linearization point publishes
the exact captured persistent generation atomically. Deliberate same-UID
process-memory mutation remains outside the boundary.

After embedded closure capture, states 7-8 never rebuild status, membership,
machine evidence, review, or contrasts from mutable original run paths. Their guards
read captured/embedded closure authority only, plus `fstat` of the held lock and
pinned aggregate directory required to publish the authority. States 2-6
retain live-evidence guards because they have no final closure authority.

## Crash And Retry States

For source snapshot create, write, file-fsync, chmod, rename, or directory-fsync
failure, no launch intent advances beyond the published slot. The exact source
journal/staging recovery protocol above determines authenticated cleanup and
rebuild; no staging bytes are adopted. A validated target is idempotent and a
published mismatched target, unknown member, or identity drift fails the cell.

For aggregate publication: empty staging or staging with exact embedded intent
but without fixed journal is authenticated cleanup when strict name, inode, and
declared partial membership validate; otherwise poisoned. Before witness
creation, journal plus exact staging and absent authority performs authenticated
cleanup and rebuild, then reruns all state-appropriate guards; journal plus
neither staging nor authority is poisoned. After witness creation, exact
witness+journal+staging may only rerun guards/rescan and finish the same rename;
it is never cleaned or rebuilt. A persistent failed post-witness check fails
closed; a transient exception may retry the unchanged staging generation.
Witness without exact staging or exact authority is poisoned. Valid authority
plus matching witness/journal is
terminal/idempotent; missing/mismatched marker or partial/invalid authority is
poisoned and never rebuilt. Every successful
create/link/unlink/rename fsyncs the file or directory and its parent. Authority
directory rename is the linearization point and parent fsync its durability
barrier. These rules apply to states 2-8; states 2-6 have no embedded
`final_closure` but use the same journal/staging/rename protocol.

## TDD Sequence

Write failing tests first for implementation changes. Items 1-5 and 11 are
freeze gates; items 6-10 describe the longer defense-in-depth backlog and do
not supersede the Product Integrity Boundary.

1. Runtime child rejects a live script path and an unlocked, writable, wrong,
   incomplete, unsealed, or hash-mismatched archive FD; parent uses `-I -S`,
   fixed pre-import bootstrap, exact sealed archive bytes, sanitized environment,
   exact two-FD pass list, and inherited lock. Unexpected inherited FDs,
   unsafe FDs 0-2, writable aliases, live first-party modules, altered import
   hooks, user-site, `.pth`, `sitecustomize`, and repository paths fail before
   output.
2. Replacing the live replay/helper after verification cannot alter the sealed
   archive. Projection tests prove every frozen tool byte maps to one exact
   entry and test synthetic entry bytes/order/hash. Persisted ZIP omission,
   tamper, extra entries, bootstrap mismatch, and inherited-FD object/hash
   mismatch fail closure reconstruction.
3. Protected registry includes the complete localized package and expanded
   test set; unresolved or out-of-root dependency discovery fails preflight.
4. Source snapshot rejects source drift, symlink/hardlink destinations, extra
   files, and hash mismatch; its entry layer opens with zero unresolved assets
   and portable relative dependencies. Stable mutation during render fails the
   post-check; the documented deliberately timed same-UID limitation is not
   misrepresented as tested prevention.
5. MDL copy rejects a destination symlink/hardlink and never changes the linked
   authority target.
6. Decision files are non-authoritative outside the atomically published
   authority directory. Inject failures at staging create, both file writes and
   fsyncs, staging-directory fsync, every guard/rescan, authority-journal temporary
   write/link/fsync, one-time lock-witness write/fsync, authority rename, and
   parent fsync.
   Test exact cleanup,
   resumable, poisoned, linearized, and idempotent states plus intent/authority
   deletion and replacement.
7. Authority production rejects arbitrary external keys; closure validation
   rejects unsorted/duplicate-inode records, extras, and omissions. Inject crash at
   authority-journal temporary write/link/unlink/fsync and every nonce-staging
   closure create/write/file-fsync/chmod/directory-fsync/authority-rename/
   parent-fsync boundary; test cleanup, resume, identity drift, and poison.
8. Swap a closure descendant, embedded intent, and whole staging root between
   validation phases. Reconstruction uses one captured generation, and final
   full member identity/hash rescan blocks authority rename on persistent drift.
9. A state-8 fixture tampers with original cells after closure creation yet
   publishes from unchanged captured closure; closure mutation before capture
   fails.
10. Fault-inject every create/write/file-fsync/chmod/rename/directory-fsync
    boundary for source snapshot, closure, decision authority, and journal;
    cover parent failure before spawn, child exit, and cleanup.
11. Full state 2-8, focused runtime, and broad related suites remain green.

The following exhaustive syscall fault matrix is defense-in-depth follow-up,
not a freeze gate under the Product Integrity Boundary above:

| Boundary | States 2-6 | States 7-8 | Required failing test / outcome |
| --- | --- | --- | --- |
| sealed archive/bootstrap/FD validation | required | required | `test_runtime_archive_bootstrap_contract_fault_matrix`: reject before output |
| source snapshot create through parent fsync | N/A before a successful cell | N/A before a successful cell | `test_source_snapshot_publication_fault_matrix`: retryable in-launch or failed cell, never success |
| authority staging before journal | cleanup-and-rebuild or poisoned | cleanup-and-rebuild or poisoned | `test_authority_prejournal_staging_fault_matrix` |
| journal temp write/file-fsync/link | retryable; temp cleanup | retryable; temp cleanup | `test_authority_journal_prelink_fault_matrix` |
| journal linked, temp still present | resume after authenticated temp unlink | resume after authenticated temp unlink | `test_authority_journal_postlink_fault_matrix` |
| staging file/directory fsync | cleanup-and-rebuild, then full live guard | cleanup-and-rebuild closure, then full captured guard | `test_authority_staging_durability_fault_matrix` |
| immediately before authority rename | rerun live state guard | validate captured closure and full embedded rescan | `test_authority_prerename_guard_fault_matrix` |
| lock has exactly one valid experiment-binding line after complete staging | append exact second-line witness then rerun guard/rescan | append exact second-line witness then rerun guard/rescan | `test_authority_witness_prepublication_fault_matrix` |
| witness plus staging, authority absent | resume only same guarded rename | resume only same captured guarded rename | `test_authority_witness_forbids_rebuild` |
| post-witness guard/rescan failure | same-generation retry, no rebuild | same-generation retry, no rebuild | `test_post_witness_failure_same_generation_retry` |
| nonempty witness without exact staging/authority | poisoned | poisoned | `test_authority_witness_detects_authority_deletion` |
| authority rename returned, parent fsync not observed | linearized if valid authority exists | linearized if valid authority exists | `test_authority_rename_linearization_fault_matrix` |
| valid authority plus matching lock witness/journal | idempotent; malformed lock or journal mismatch poisons | idempotent; malformed lock or journal mismatch poisons | `test_authority_requires_matching_witness_and_intents` |
| missing/partial/changed authority | poisoned | poisoned | `test_authority_corruption_is_poisoned` |
| semantic terminal reconstruction | exact states 2-6 | exact states 7-8 | `test_render_diagnostic_aggregate_states_two_through_eight` |

Prior implementation-review findings map one-to-one as follows: child exec
TOCTOU -> `test_runtime_archive_bootstrap_contract_fault_matrix`; live USD
dependency gap -> `test_source_snapshot_publication_fault_matrix`; MDL overwrite
-> `test_mdl_copy_destination_link_attack`; closure substitution/mixed time ->
`test_closure_captured_generation_and_prerename_rescan`; arbitrary/prebuilt
closure -> `test_embedded_closure_exact_membership_and_intent`; live originals
after closure -> `test_state8_uses_embedded_closure_only`; decision rollback ->
`test_authority_rename_linearization_fault_matrix`; incomplete implementation
identity -> `test_render_diagnostic_implementation_identity_has_exact_membership`.

## Verification And Review Gates

After implementation:

1. Run `py_compile` and `git diff --check`.
2. Run focused adversarial tests, then complete runtime-contract tests.
3. Run the broad suite covering runtime contract, real beaker, matrix runtime,
   OmniGlass reference, strict schedule, and native completed-PBD contracts.
4. Run one nonformal `/tmp` Isaac/USD source-snapshot smoke. It may not create
   formal v3 paths and must prove zero unresolved copied-entry assets.
5. Obtain three fresh independent implementation GO reviews for architecture,
   completeness/edge cases, and adversarial risk.
6. Confirm every formal v3 path is absent. Only then write implementation
   identity and pre-freeze, followed by the 16 official cells.

## Formal `_003` Launcher Recovery

The `_002` first cell stopped before first-party import and before
`SimulationApp` because direct shell redirection made standard output and
standard error regular files, which the sealed bootstrap correctly rejects.
The `_003` run therefore has one exact launcher surface:

- `tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_003.sh` owns the exact
  sixteen balanced slots, fixed Isaac interpreter, authority, experiment ID,
  output roots, render parameters, and sequence;
- every formal cell must pass through
  `tools/labutopia_fluid/run_sealed_child_with_pipe_log.sh`;
- the wrapper gives the child FIFO standard output/error, logs with pinned
  `/usr/bin/tee` through an exclusively opened log FD, rejects preexisting,
  symlinked, or non-direct-`/tmp` logs, and returns `74` for log failure before
  otherwise propagating child failure;
- file-size-signal handling used to make a failed `tee` observable is scoped to
  the `tee` subprocess; the wrapper does not alter the child command's inherited
  `SIGXFSZ` handling;
- `--print-plan` performs no launch, while `--from N` is only for continuing at
  the next not-yet-launched canonical slot after independently checking prior
  evidence. The replay parent remains the authority for predecessor-chain and
  frozen-identity validation.

Both shell files are members of the implementation identity. Direct invocation
of the Python cell command is outside the formal `_003` procedure.

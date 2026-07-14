# Real-Beaker Black-Liquid Causal Matrix Plan v3

## Objective

Test whether the normals-blocked support-aligned display-fill liquid's nearly
black appearance is consistently associated with requested/read-back
ambient-occlusion registry state, RTX capture subframes, or their interaction
under the fixed C-lighting condition.

This is a render-diagnostic phase. It does not select a look, run a formal
five-candidate replay, localize a deliverable, or admit the exporter.

## Established Inputs

- Accepted authority bundle SHA-256:
  `edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605`.
- Support-aligned source USD SHA-256:
  `3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b`.
- Accepted physical trace SHA-256:
  `124492bbffa9cbc4134ba1ee3558f0e52eee9ea502797ed0fb8b32dd2ebda5fd`.
- Normal-remediation contract SHA-256:
  `da174bdbe851d73346208c97babbc3f4a6ee09c1b4ee945afd7f15a36b6a8fcb`.
- The v2 C/B lighting probe is machine-valid but visually failed for both
  variants. Lighting alone is therefore not the recovery variable.

The historical cyan/AO images are guidance only. Their prototype manifest does
not bind a source USD hash, physical trace hash, material contract, display-fill
geometry hash, or normal-remediation hash. Its point-state and camera hashes
also differ from the accepted support-aligned scene. It cannot serve as a
matched control.

## Controlled Matrix

Run a new matched 2x2 matrix under `C_CONTROL` lighting. Render every cell four
times in a fresh Isaac/Kit child process:

| Variant | Requested/read-back AO registry enabled | RT subframes | Normal block |
| --- | ---: | ---: | ---: |
| `AO0_RT4_CONTROL` | false | 4 | true |
| `AO0_RT12` | false | 12 | true |
| `AO1_RT4` | true | 4 | true |
| `AO1_RT12` | true | 12 | true |

Bind each variant's operational-preference score as the lexicographic tuple
`[int(ambient_occlusion_enabled), rt_subframes]`. This is a declared product
preference, not measured compute cost: avoid adding AO first, then prefer fewer
capture subframes. It yields the fixed ordering shown in Runtime Sequence step
10.

All four runs must use the same implementation version. Explicitly set and
read back these settings in every run, including settings whose effect is
disabled:

- `/rtx/ambientOcclusion/enabled`: matrix value;
- `/rtx/ambientOcclusion/rayLength`: `5.0`;
- `/rtx/ambientOcclusion/minSamples`: `8`;
- `/rtx/ambientOcclusion/maxSamples`: `16`;
- `/rtx/ambientOcclusion/denoiserMode`: `2`;
- `/rtx/shadows/enabled`: `true`;
- `/rtx/shadows/sampleCount`: `4`;
- `/rtx/translucency/maxRefractionBounces`: `12`;
- Replicator `rt_subframes`: matrix value.

The new baseline is rendered again rather than reusing v2 because v2 did not
explicitly bind every AO parameter or shadow sample count.

Use this four-block balanced order with no code or render-input edits between
runs; every variant appears once in every ordinal position:

- replicate A: `AO0_RT4_CONTROL`, `AO0_RT12`, `AO1_RT4`, `AO1_RT12`;
- replicate B: `AO1_RT12`, `AO1_RT4`, `AO0_RT12`, `AO0_RT4_CONTROL`;
- replicate C: `AO0_RT12`, `AO1_RT12`, `AO0_RT4_CONTROL`, `AO1_RT4`;
- replicate D: `AO1_RT4`, `AO0_RT4_CONTROL`, `AO1_RT12`, `AO0_RT12`.

Every cell gets a new absent output root, a fresh parent/child process, newly
created render products and annotators, identical update barriers, one identical
discarded warm-up capture, and identical cleanup validation. Record process ID,
execution order, implementation/source-tree hashes, Isaac/runtime versions,
GPU UUID/name, driver, render delegate, requested settings, Carb registry
readback, and renderer-consumption authority.

Inject the matrix Carb settings as canonical Kit startup arguments before
constructing `SimulationApp`, then verify/reapply them after boot and execute an
update barrier before opening the accepted stage. Record both startup arguments
and post-boot registry state. This reduces initialization/cache ambiguity but
still does not prove renderer consumption.

The aggregate analysis is descriptive, not causal and not proof of consumed AO
renderer state. For each reproducible binary
visual-pass indicator `P(ao,rt)`, record the predeclared contrasts:

- AO association: `(P(1,4)+P(1,12)-P(0,4)-P(0,12))/2`;
- RT association: `(P(0,12)+P(1,12)-P(0,4)-P(1,4))/2`;
- interaction association: `P(1,12)-P(1,4)-P(0,12)+P(0,4)`.

Also compute the same contrasts for deterministic per-image full-RGB mean,
cyan-channel excess `(G+B)/2-R`, and luminance metrics over every bound review
panel, averaged first within cell/replicate and then across A-D. These metrics
do not replace the hard human visual gate and are reported only as observed
associations under the tested configuration.

Isaac Sim 4.1 Carb registry readback is not proof that RTX consumed a setting.
Record it as registry readback only. Unless an authoritative renderer query is
available, record `renderer_consumption_verification=NOT_AVAILABLE_ISAACSIM41`
and limit conclusions to observed pixel associations. Treat `rt_subframes` as a
captured Replicator call contract rather than an RTX registry setting.

Keep identical across the matrix:

- exact source USD and accepted trace;
- `OMNI_REF_DISPLAY_FILL` geometry and all per-frame geometry hashes;
- A18 OmniGlass material source, tint, and material hash;
- native beaker material;
- `beaker_normals_block_v1` and its exact contract hash;
- measured close-up, pair-context, and native-table cameras;
- C lighting block;
- resolution, frame indices, video FPS, stopped timeline, and zero Replicator
  delta;
- no profile camera, beaker override, or postprocess application.

## Raw Normals Out Of Scope

This v3 implementation does not expose or run a raw-normal mode. If all four
normals-blocked cells fail reproducibly, write a separate reviewed and
hash-authorized plan for a quarantined raw-normal diagnostic. That later plan
must prevent any reusable static USD/export artifact and may conclude only that
cyan readability depends on retaining source normals under its matched tested
conditions. It may not attribute the historical cyan render to malformed
normals without first reproducing and hash-binding the historical stage.

## Files

Modify:

- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- `tests/test_real_beaker_runtime_contract.py`

Generate only after tests pass:

- sixteen new matrix prototype roots: four fresh-process replicates of each cell;
- one machine matrix-verification manifest;
- anonymous close-up and pair-context review sheets;
- one clean-room visual-review record;
- pre/post tree-freeze records covering all old authority and v2 outputs.

Do not modify existing authority, source, formal replay, v2 prototype, v2
review, historical cyan/AO, or prior tree-freeze files.

Use one new create-exclusive aggregate experiment root. Register these exact
absolute protected roots before implementation-backed rendering and require
identical post-run trees:

- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712/accepted_authority_P4096_S2`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/outputs/usd_asset_packages/lab_001_level1_pour_support_aligned_v1_20260712`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_omniglass_support_aligned_normals_v1_20260712_001`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_display_fill_normal_block_support_aligned_20260712_002`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_omniglass_reference_si600_restoffset_20260712_024_smoke`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_display_fill_ao_visual_prototype_20260712_026`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_display_fill_normal_block_lighting_C_control_20260712_001`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_display_fill_normal_block_lighting_B_treatment_20260712_001`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_normal_block_lighting_ab_blind_review_20260712`.
- `/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/site-packages/omni/mdl/core`.

Also register these exact protected files:

- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_normal_block_lighting_ab_machine_verification_20260712.json`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_normal_block_look_recovery_v2_protected_tree_freeze_pre_20260712.json`;
- `/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_normal_block_look_recovery_v2_protected_tree_freeze_post_20260712.json`.

Tree snapshots reject every symlink in the recursive directory walk and allow
no exclusions. Each sorted record is exactly `{path, byte_count, sha256}` with
path relative to the registered root. The tree hash is SHA-256 over sorted-key,
compact-separator, finite JSON encoded as UTF-8. Both freeze records bind the
same ordered absolute root/file registry; missing, added, removed, resized, or
changed files fail.

Path validation is lexical and precedes all real-path resolution. Every path
component from the filesystem root through the leaf is checked with `lstat`;
an ancestor, leaf, or broken symlink fails. This rule applies to protected
roots/files, implementation members, the aggregate root, launch intents, cell
roots and sidecars, replay manifests, copied MDL closure files, media, review
maps, review sheets, review source PNGs, evidence files, and the decision path.
For reads that contribute to a launch, post seal, closure snapshot, or decision,
the implementation additionally opens each component relative to a pinned
directory file descriptor with `O_NOFOLLOW`, verifies `fstat` before and after
reading, and hashes bytes from that descriptor. A separate path-based `lstat`
followed by an ordinary open is not an accepted authority boundary.

Register the replay tool, affected tests, this reviewed plan, source USDA, and
frozen physics runner as protected files after implementation/tests are final.
Each cell must also mirror and hash the same version-matched MDL closure; the
matrix validator requires identical relative-path/hash maps across all cells.
The formal render installs that cell-local closure before `SimulationApp`,
verifies the Kit MDL search-path readback, and then uses Isaac's postboot USD
resolver before authoring and again on the exported static entry to prove that
every USD layer, texture, and USD-authored top-level MDL asset resolves only
inside the cell-local source snapshot, candidate directory, or material
closure. The closure contains the complete regular `mdl/` module tree and all
`Base/*.mdl` files, and its search paths precede defaults. Isaac 4.1 does not
provide a per-transitive-module renderer-consumption audit here, so this is not
claimed as proof of every MDL compiler import actually consumed. System-Python
pxr resolution is diagnostic only and cannot qualify a cell.

Define `matrix_implementation_identity_v1` after tests pass and before the first
cell. Its exact membership is all non-symlink regular `*.py` files directly
under `tools/labutopia_fluid/`, plus these exact files:

- `tests/test_real_beaker_runtime_contract.py`;
- `tests/test_omniglass_reference.py`;
- `tests/test_level1_pour_support_aligned_scene.py`;
- `tests/test_support_aligned_authority_bundle.py`;
- this v3 plan.

Publish it atomically and create-exclusively at the fixed path
`/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_ao_rt_matrix_v3_20260712_003_implementation_identity.json`.
The pre-freeze registry includes this exact file, and the experiment anchor
binds its canonical identity hash. No substitute path is accepted.
The exact pre-freeze path is
`/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_ao_rt_matrix_v3_20260712_003_protected_tree_freeze_pre.json`;
the exact post-freeze-envelope path is
`/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_ao_rt_matrix_v3_20260712_003_protected_tree_freeze_post.json`.
Both paths and the implementation path are literal anchor fields and aggregate
CLI arguments must equal them byte-for-byte after absolute lexical
normalization.

Store sorted repository-relative `{path, sha256}` records and hash those records
with sorted-key compact finite JSON in UTF-8. Every cell manifest binds the full
record set and identity hash. Re-enumerate and re-hash before every launch and
after every clean child exit; added, removed, symlinked, or changed members fail.
The aggregate validator requires byte-identical records and hash in all cells.
Create and verify this complete implementation/protected-input freeze before
creating the aggregate experiment root or any lawful cell output. Reverify it
after every child exit and once more before aggregate closure.
Verification of the pre-freeze must re-enumerate and re-hash the current
protected registry and compare it to the stored snapshot; validating only the
stored JSON schema or its self-hash is insufficient. Perform this live
comparison immediately before every launch intent and after every child exit.

## Canonical Hash Schemas

All experiment hashes use `canonical_json_sha256_v1(value)`: reject non-finite
values, serialize with sorted object keys and compact separators, encode UTF-8,
then SHA-256 the bytes. Lists retain their declared order. Hash payloads exclude
only `generated_at_utc` and their own final `*_sha256` field; no other field is
implicitly ignored.
Every schema in this section uses integer `schema_version: 1` unless an
explicitly named existing contract declares another version; the effective
replay look contract and its projection validate a full schema-v2 look object.

- Tree freeze object: exactly `{schema_version, registry_id,
  protected_roots, protected_files}`. Roots/files follow the declared registry
  order. Each root record is exactly `{root_path, files}`, where `files` is the
  path-sorted list of `{path, byte_count, sha256}`. Each protected-file record is
  exactly `{path, byte_count, sha256}`.
- Post-freeze envelope: exactly `{schema_version, experiment_id,
  anchor_sha256, completed_successful_sequence_length,
  last_launch_intent_sha256, last_cell_artifact_sha256, registry_snapshot,
  generated_at_utc, post_freeze_sha256}`. `registry_snapshot` is the exact tree
  freeze object above and must equal the accepted pre-freeze snapshot.
  `completed_successful_sequence_length` is an exact int 0..16. The last intent
  hash binds the final published intent in the currently validated sequence;
  the last artifact hash binds its success/failure evidence and is nullable only
  when that launched intent has no artifact. Aggregate mode alone creates this
  envelope create-exclusively under the anchor-bound lock after proving all
  launchers/children quiescent and rebuilding the current chain. A preexisting
  envelope whose anchor, sequence length, last hashes, or registry snapshot do
  not exactly match is rejected as substituted/prebuilt evidence.
- Implementation object: exactly `{schema_version, identity_id, files}`, with
  the repository-relative path-sorted `{path, sha256}` list defined above.
- MDL closure object: exactly `{schema_version, closure_id, files}`, with a
  relative-path-sorted list of `{path, byte_count, sha256}`; symlinks and
  absolute/out-of-root dependency paths fail.
- Experiment-anchor object: exactly `{schema_version, experiment_id,
  aggregate_root, aggregate_root_device, aggregate_root_inode, lock_path,
  lock_device, lock_inode, implementation_identity_sha256,
  implementation_identity_path, pre_freeze_path, post_freeze_path,
  pre_freeze_sha256, canonical_slots, anchor_sha256}`. `canonical_slots` is the
  exact sixteen-record balanced execution sequence, each exact `{sequence_index,
  variant, replicate, execution_order_index, cell_name}`. Before the fixed root
  exists, create the fixed external lock as one non-symlink regular file, then
  construct a sibling staging directory. Record the staging directory's
  `(st_dev,st_ino)` as the future fixed root identity, write/fsync the anchor and
  first launch intent in that staging tree, fsync every created directory, and
  atomically rename the whole staging directory to the absent fixed root before
  fsyncing its parent. Thus the fixed root, valid anchor, and valid first intent
  are either all absent or all present; abandoned staging directories are not
  lawful experiment output. The successful rename is the sole state-1/state-2
  boundary.
- Launch-intent object: exactly `{schema_version, experiment_id, variant,
  replicate, execution_order_index, cell_root, launcher_pid, generated_at_utc,
  sequence_index, anchor_sha256, predecessor_launch_intent_sha256,
  predecessor_cell_evidence_sha256, implementation_identity_sha256,
  pre_freeze_sha256, launch_intent_sha256}`. `pre_freeze_sha256` is the canonical JSON hash of the
  one fixed, create-exclusive pre-freeze accepted before the first cell and is
  identical in every intent. It is written and
  fsynced create-exclusively before its cell output root or child process is
  created. Its hash excludes only `generated_at_utc` and its own hash field.
  The first intent has `sequence_index=0` and both predecessor hashes null.
  Every later intent has the next exact global sequence index and binds the
  immediately preceding valid intent and successful cell-evidence hashes.
  Before publishing it, the launcher revalidates the complete preceding chain,
  the anchor/root/lock identities, and live freezes. Parallel, skipped,
  duplicated, or reordered launches therefore fail before child creation.
- Matrix-cell evidence object: exactly `{schema_version, manifest_type,
  experiment_id, variant, replicate, execution_order_index, classification,
  child_exit_code, cell_root, implementation_identity_sha256,
  source_usd_sha256, authority_bundle_sha256, physical_trace_sha256,
  normal_remediation_sha256, liquid_material_sha256,
  display_fill_geometry_sha256, camera_contract_sha256,
  effective_replay_look_contract_sha256,
  effective_replay_look_matrix_projection_sha256, render_settings_sha256,
  mdl_closure_sha256, runtime_identity_sha256, device_identity_sha256,
  process_identity_sha256,
  frame_bindings_sha256, media_index_sha256, stopped_timeline,
  replicator_delta_time, default_time_points_unchanged,
  standalone_final_evidence_authority, exporter_admitted,
  visual_selection_eligible, formal_scope, delivery_ready,
  matrix_cell_evidence_sha256}`. `manifest_type` is
  `real_beaker_render_diagnostic_matrix_cell`; successful classification is
  `DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW`; hashes are lowercase
  64-hex, order and exit code are exact ints, timeline/lifecycle fields are
  exact bools, and `replicator_delta_time` is finite numeric zero. The sidecar
  is create-exclusive and the replay final manifest binds its path and hash;
  the aggregate trusts neither object unless their bindings agree.
- Matrix-cell failure evidence is exactly `{schema_version, manifest_type,
  experiment_id, variant, replicate, execution_order_index, classification,
  child_exit_code, cell_root, launch_intent_sha256,
  implementation_identity_sha256, failure_stage, error_type, error_message,
  partial_manifest_path, partial_manifest_sha256, generated_at_utc,
  matrix_cell_failure_evidence_sha256}` with manifest type
  `real_beaker_render_diagnostic_matrix_cell_failure`. The two partial-manifest
  fields are either both null or both non-null; exit code may be null only when
  a child could not be started. Non-empty failure strings are required. A
  `FAILED` cell-status record binds this object; a launched slot for which even
  this object cannot be written is `LAUNCHED_EVIDENCE_MISSING`.
- Runtime identity is exactly `{schema_version, isaac_version, kit_version,
  python_executable, render_delegate, headless, runtime_identity_sha256}`;
  device identity is exactly `{schema_version, gpu_uuid, gpu_name,
  driver_version, device_identity_sha256}`; process identity is exactly
  `{schema_version, launcher_pid, child_pid, parent_child_fresh_process,
  cold_start, launch_intent_sha256, process_identity_sha256}`. Version/path/name
  fields are non-empty strings, PIDs are positive ints, and process booleans
  must both be true. Process identity is recorded but is not an across-cell
  equality field.
- Matrix media index is exactly `{schema_version, images, videos,
  media_index_sha256}`. Images are sorted by canonical camera order then frame
  and contain exactly 63 records `{camera, frame, path, sha256, width, height}`;
  videos contain three camera-sorted exact `{camera, path, sha256, frame_count,
  width, height, fps}` records. Canonical camera order is `context`,
  `source_beaker_closeup`, `native_table_context`; required dimensions are
  960x540; image frames are exactly `0,30,60,90,120,150,180,210,240,270,300,
  330,360,390,420,450,480,510,540,570,600`; each video has 21 frames and FPS
  is 15.0.
  Matrix frame bindings are exactly `{schema_version, frames,
  frame_bindings_sha256}` with 21 frame-sorted exact `{frame,
  accepted_points_sha256, display_fill_geometry_sha256,
  camera_image_sha256s}` records; `camera_image_sha256s` has exactly the three
  canonical camera keys.
- Render-settings object: exactly `{schema_version,
  render_diagnostic_variant_id, requested_registry, startup_arguments,
  registry_readback, renderer_consumption_verification, rt_subframes}`.
  Registry lists contain exactly the eight Controlled Matrix settings sorted by
  absolute path; each record is exactly `{path, value_type, value}` with
  `value_type` exactly `bool|int|float` and a matching JSON scalar type.
  `startup_arguments` contains the matching eight exact
  `--<path>=<canonical-value>` strings in the Controlled Matrix listing order;
  booleans serialize lowercase, the float as `5.0`, and ints in base-10.
  `rt_subframes` is exact int 4 or 12 and, together with the AO bool, must match
  the canonical variant table. In v3
  `renderer_consumption_verification` is the exact string
  `NOT_AVAILABLE_ISAACSIM41`; support for any authoritative renderer query
  requires a separately reviewed schema revision rather than an open union.
- Review panel-map object: exactly `{schema_version, panels}`. Every panel
  record is exactly `{panel_id, replicate, view, frame, blinded_column,
  sheet_sha256, blinded_label, source_png_path, source_png_sha256}`. Allowed
  values and canonical orders are replicate `A,B,C,D`; view
  `source_beaker_closeup,context`; frame `0000,0300,0600`; and zero-based integer
  `blinded_column` `0,1,2,3`. Sort by those four keys in that order.
  `blinded_label` is one of `L0,L1,L2,L3`; within each replicate/view/frame the
  four labels and columns are each unique and complete. `panel_id` is exactly
  `<replicate>/<view>/<frame>/column_<blinded_column>/<blinded_label>` with the
  angle-bracket tokens substituted verbatim from the same record. The blinded
  label map is a separate exact `{schema_version, labels}` object containing a
  label-sorted four-record bijection of exact `{blinded_label, variant}`
  records; the same label-to-variant map applies to all replicates and sheets.
- Aggregate cell-index object: exactly `{schema_version, experiment_id, cells}`;
  `cells` is the zero-to-sixteen exact subset of `SUCCESS` records in the bound
  cell-status index, sorted by canonical variant order then replicate A-D; every
  record is exactly `{variant, replicate, execution_order_index, manifest_path,
  manifest_sha256, implementation_identity_sha256,
  effective_replay_look_contract_sha256}`.
  Validation reopens every canonical manifest path as a non-symlink regular
  file and recomputes its current byte hash. It also requires exact equality to
  the replay-manifest hash returned by that cell's rebuilt artifact closure.
  States 5-8 require all sixteen records. States 2-4 may contain a strict subset;
  no failed, launched-missing, mixed, or not-launched slot appears in this index.
- Successful post-seal object: exactly `{schema_version, experiment_id,
  anchor_sha256, completed_sequence_length, final_launch_intent_sha256,
  final_cell_evidence_sha256, pre_freeze_sha256, post_freeze_sha256,
  implementation_identity_sha256, generated_at_utc, post_seal_sha256}`.
  It is create-exclusive and permitted only after revalidating the complete
  chained sequence of sixteen successful cells, with
  `completed_sequence_length=16` and the two final hashes bound to slot 15.
  A post-freeze envelope may be generated for any lawful terminal after
  the external lock proves no launcher/child is active; this lets states 3-4
  preserve a stable protected-registry endpoint. The successful seal is a
  separate operation that consumes that exact chain-bound envelope only after the full
  chain check; a pre-generated/substituted post-freeze or one written while a
  child owns the lock cannot produce a valid seal. States 5-8 require the
  successful post seal. States 2-4 have a null seal hash unless state 4 happens
  to contain all sixteen successful chained cells, in which case a valid seal
  is permitted but still cannot override the matrix failure.
  Its fixed create-exclusive path is `<aggregate>/successful_post_seal.json`;
  the fixed anchor path is `<aggregate>/experiment_anchor.json`.
- PASS-capable final closure snapshot is a newly copied, non-hard-linked, create-exclusive
  tree at `<aggregate>/final_closure`. It contains the anchor (which is the
  sole lock/root identity record), implementation/pre/post freezes, successful post seal, all sixteen
  intents and exact cell artifact trees, fixed aggregate evidence, review
  record/maps/sheets, and every source PNG needed to rebuild the review and
  contrasts. Its exact manifest is `{schema_version, experiment_id,
  snapshot_device, snapshot_inode, files, closure_snapshot_sha256}` where path-sorted `files` records are exact
  `{logical_path, snapshot_path, byte_count, sha256}`. The copier reads each
  source through pinned `O_NOFOLLOW` descriptors, writes/fsyncs independent
  regular files in a sibling staging tree, writes/fsyncs the manifest, changes
  files/directories to read-only modes, atomically renames the staging tree to
  `final_closure`, and fsyncs the aggregate directory. Decision construction
  and all later validation read only this snapshot, never the mutable run
  paths. Snapshot creation is restarted from scratch before publication on any
  source drift; an existing incomplete or mismatched snapshot prevents a
  decision.
  The manifest's fixed path is
  `<aggregate>/final_closure/closure_manifest.json`; the manifest file is not a
  member of its own `files` list, avoiding recursive self-hashing. The staging
  directory's `(st_dev,st_ino)` becomes the required snapshot
  identity because rename preserves it. Every `logical_path` and
  `snapshot_path` is a normalized, unique, non-empty relative POSIX path with no
  `.` or `..`; for aggregate members both fields are identically
  `aggregate/<aggregate-relative-path>`, and that is also the snapshot-relative
  file location. This mapping is used for every
  non-symlink regular file recursively present under the pinned aggregate root
  before snapshot creation, excluding only `final_closure`, its staging names,
  and `matrix_decision.json`. The three external fixed files use exactly
  `external/implementation_identity.json`, `external/pre_freeze.json`, and
  `external/post_freeze.json` for both fields and locations. No other exclusions or snapshot members are
  legal. The closure directory path and every ancestor are reopened and their
  identities checked against the manifest and pinned root immediately before
  and after decision publication.
  Snapshot validation never rewrites embedded JSON. Whenever a copied intent,
  cell, media, review, index, or decision precursor contains an original
  absolute path, the snapshot-only resolver maps the exact aggregate prefix to
  `aggregate/<relative>` and the three exact external paths to their declared
  `external/*` entries before opening bytes. Any other absolute path is rejected.
  This complete snapshot is required only after machine, repeat, and visual
  review closure have reached terminal state 7 or 8. States 2-6 publish their
  non-interpretive decision directly from the pinned original evidence under
  the external lock, with `closure_snapshot_sha256=null`; they do not require a
  successful post seal, unlaunched cells, or absent review artifacts. Any state
  2-6 evidence drift before publication prevents publication or is rebuilt to
  the newly observed higher-priority early state, but no early decision can
  authorize visual interpretation.
- Cell-status-index object: exactly `{schema_version, experiment_id, cells}`
  with all sixteen canonical slots in replicate execution order A0..D3. Every
  record is exactly `{variant, replicate, execution_order_index,
  launch_intent_path, launch_intent_sha256, cell_root, cell_evidence_path,
  cell_evidence_sha256, classification, child_exit_code, status}`. `status` is exactly
  `NOT_LAUNCHED|MIXED_UNREGISTERED_CELL_ROOT|LAUNCHED_EVIDENCE_MISSING|FAILED|SUCCESS`.
  The exact valid combinations are:

  - `NOT_LAUNCHED`: intent/evidence/classification/exit fields are null and the
    canonical cell root is absent;
  - `MIXED_UNREGISTERED_CELL_ROOT`: intent/evidence/classification/exit fields
    are null and the canonical cell root exists;
  - `LAUNCHED_EVIDENCE_MISSING`: intent path/hash are non-null and valid,
    evidence/classification/exit fields are null, regardless of whether the
    canonical root could be created;
  - `FAILED`: intent and failure-evidence paths/hashes are non-null and valid,
    classification is non-empty but not the success classification, and exit
    code matches the nullable failure-evidence value;
  - `SUCCESS`: intent and success-evidence paths/hashes are non-null and valid,
    classification is exactly the success classification and exit code is 0.

  `cell_root` is always the canonical expected absolute path. All other
  combinations fail schema validation. The first mixed status is state 4; the
  launched-missing and failed statuses are state 3.
- Matrix-validation evidence is exactly `{schema_version, experiment_id,
  status, exact_slot_closure, all_cells_successful, unexpected_paths,
  equality_checks, projection_byte_equality, projection_sha256,
  matrix_validation_evidence_sha256}`. When status is `NOT_REACHED`, the three
  bool fields and projection hash are null and both lists are empty. When status
  is `PASS|FAIL`, bools are non-null, `unexpected_paths` is a sorted unique list
  of absolute paths, and `projection_sha256` is non-null exactly when projection
  comparison was reached. `equality_checks` is a name-sorted list
  of exact `{name, status, reference_sha256}` with the exact names
  `implementation_identity`, `source_usd`, `authority_bundle`,
  `physical_trace`, `normal_remediation`, `liquid_material`,
  `display_fill_geometry`, `camera_contract`, `mdl_closure`,
  `runtime_identity`, and `device_identity`; status is
  `PASS|FAIL|NOT_REACHED` and the reference hash is nullable only for
  `NOT_REACHED`.
- Repeat-stability evidence is exactly `{schema_version, experiment_id,
  status, thresholds, comparisons, repeat_stability_evidence_sha256}`.
  `thresholds` is exact `{rgb_mae_max, psnr_db_min}` = `{5.0,30.0}`. For
  `NOT_REACHED`, `comparisons` is empty. For `PASS|FAIL`, it contains the exact
  144 records sorted by canonical variant, view, frame, then replicate
  pair `AB,AC,AD,BC,BD,CD`; every record is exactly `{variant, view, frame,
  left_replicate, right_replicate, left_png_sha256, right_png_sha256, rgb_mae,
  psnr_db, status}`. Metrics use decoded uint8 RGB over equal-sized images;
  MAE is the arithmetic mean absolute channel difference and PSNR uses peak
  255. `psnr_db` is finite numeric or exact string `INF` when MSE is zero;
  status is `PASS|FAIL` from the declared thresholds.
- Final matrix decision hash covers the exact terminal-state object, aggregate
  cell index, freeze hashes, closure/equality/stability results, review record
  hash, all intermediate visual gates, descriptive contrasts, and claim
  boundaries. Unknown top-level fields are rejected before hashing.

The fixed review mapping paths are `<aggregate>/review/panel_map.json` and
`<aggregate>/review/blinded_label_map.json`; the fixed review-record path is
`<aggregate>/review/review_record.json`. The exact review record is
`{schema_version, review_id, sheets, panel_map_path, panel_map_sha256,
blinded_label_map_path, blinded_label_map_sha256, reviewer,
raw_blinded_verdicts, raw_blinded_verdicts_sha256, verdicts, verdicts_sha256,
panel_gates, replicate_gates, configuration_gates,
derived_gate_sha256, review_record_sha256}`. `sheets` is a path-sorted list of
exact `{path, sha256, width, height}` records. `reviewer` is exactly
`{mechanism, session_id, forked_implementation_context,
repository_context_supplied, condition_mapping_supplied_before_verdict}` with
string/string/bool/bool/bool types; independence requires the final three
booleans all false. `raw_blinded_verdicts` is a `panel_id`-sorted list of exactly
96 records, each exactly `{panel_id, source_png_sha256, material_verdict,
hard_flags, containment_and_grounding, external_liquid_visible,
penetration_visible, starburst_visible, broken_normal_visible,
framing_blocker_visible, visible_evidence}`. It is the only verdict payload
returned by the blinded reviewer. After that record is immutable and hashed,
the aggregator joins each `panel_id` through the hash-validated panel map and
then `blinded_label` through the separately hash-validated label map. It rejects
missing, duplicate, or non-bijective joins and deterministically materializes
the variant-keyed `verdicts` object in canonical variant/replicate/view/frame
order. Each 96-leaf verdict has the same leaf schema and key space defined in
Runtime Sequence step 8; `material_verdict` and
`containment_and_grounding` are enums `PASS|WARN|FAIL`, hashes are lowercase
64-hex strings, all visibility fields are booleans, and `visible_evidence` is a
non-empty list of non-empty strings. `panel_gates` is exactly
`panel_gates[variant][replicate][view][frame]`, `replicate_gates` is exactly
`replicate_gates[variant][replicate]`, and `configuration_gates` is exactly
`configuration_gates[variant]`, using the canonical key orders declared in
Runtime Sequence step 8. Every leaf is `PASS|FAIL|INDETERMINATE`; no other keys
or fields are allowed.

State 1 intentionally creates no output and therefore has no persisted
terminal-state object. For every lawful aggregate attempt, the exact
terminal-state object is `{code, precedence_index, evaluated_predicates,
evidence_sha256}`, where `code` is one of persisted states 2-8 and
`precedence_index` is `2..8`. `evaluated_predicates` always contains these exact
seven names in this order: `protected_input_mutation`,
`cell_runtime_or_artifact_failure`, `matrix_incomplete_or_mixed`,
`repeat_instability`, `visual_review_indeterminate`,
`all_configurations_reproducibly_fail`,
`at_least_one_configuration_reproducibly_passes`. For the winning position k,
all earlier records are `FALSE`, k is `TRUE`, and all later records are
`NOT_REACHED`; no short list is legal.

Every predicate record is exact `{name, result, evidence_sha256}`. Its evidence
hash is `canonical_json_sha256_v1` of exact `{schema_version, name, result,
inputs}`. For `NOT_REACHED`, `inputs` is exactly `{}`. For evaluated predicates,
`inputs` has these exact fields:

- `protected_input_mutation`: `{pre_freeze_sha256, post_freeze_sha256,
  implementation_identity_sha256, protected_input_failure_evidence_sha256,
  protected_inputs_match}`;
- `cell_runtime_or_artifact_failure`: `{cell_status_index_sha256,
  every_launched_cell_successful}`;
- `matrix_incomplete_or_mixed`: `{matrix_validation_status,
  matrix_validation_evidence_sha256}`;
- `repeat_instability`: `{repeat_stability_status,
  repeat_stability_evidence_sha256}`;
- `visual_review_indeterminate`: `{review_record_sha256,
  visual_gates_sha256, visual_review_determinate}`;
- `all_configurations_reproducibly_fail`: `{configuration_gates_sha256,
  all_configurations_fail}`;
- `at_least_one_configuration_reproducibly_passes`:
  `{configuration_gates_sha256, at_least_one_configuration_passes}`.

Hashes are lowercase 64-hex strings except nullable post-freeze,
protected-failure, review, and gate hashes; status values use the already
declared enums, and predicate booleans are exact bools. When a complete
post-freeze can be written, its hash is required and protected-failure evidence
is null. When mutation prevents a complete post-freeze, `post_freeze_sha256` is
null and `<aggregate>/evidence/protected_input_failure.json` is required with
the exact schema `{schema_version, registry_id, failed_path, failure_kind,
expected_sha256, observed_sha256, generated_at_utc,
protected_input_failure_evidence_sha256}`; expected/observed hashes are nullable
only when the path is missing, unreadable, or a symlink. `failure_kind` is
exactly one of `MISSING`, `UNREADABLE`, `SYMLINK`, `ADDED`, `REMOVED`,
`SIZE_CHANGED`, `CONTENT_CHANGED`, `REGISTRY_CHANGED`, or
`IMPLEMENTATION_CHANGED`; the first mismatching record in registered
root/file/path sort order is stored. `cell_status_index_sha256` hashes
the exact cell-status-index object defined above.
`visual_gates_sha256` hashes the exact three gate objects; the configuration
hash hashes only `configuration_gates`. The terminal object's own
`evidence_sha256` hashes the exact ordered `evaluated_predicates` list.

The exact final decision object is `{schema_version, manifest_type,
experiment_id, generated_at_utc, terminal_state, cell_status_index,
aggregate_cell_index,
anchor_sha256, post_seal_sha256, closure_snapshot_sha256,
pre_freeze_sha256, post_freeze_sha256, implementation_identity_sha256,
matrix_validation, repeat_stability, review_record_sha256, visual_gates,
descriptive_contrasts, operational_preference, visually_passed_configuration,
claim_boundary, matrix_decision_sha256}`. `matrix_validation` and
`repeat_stability` are exact `{status, evidence_sha256}` records with status
`PASS|FAIL|NOT_REACHED`. `visual_gates` is either null or the exact three gate
objects from the review record. The fixed evidence paths are
`<aggregate>/evidence/cell_status_index.json`,
`<aggregate>/evidence/matrix_validation.json`, and
`<aggregate>/evidence/repeat_stability.json`; their hashes must match the final
decision references.
Decision validation reopens these exact non-symlink files, recomputes their
self-hashes, rebuilds the machine closure from every intent/cell/manifest/
sidecar/MDL/media byte, revalidates the review maps/sheets/source pixels and
review record when reached, recomputes all twelve descriptive contrasts, and
requires exact equality to the decision. A decision file is authoritative only
while this complete validator succeeds; existence or a top-level self-hash
alone is never a PASS claim.
For PASS-capable states this reconstruction is performed exclusively from the
independent final-closure copies and requires the anchor, post seal, and closure
snapshot hashes in the decision. `post_seal_sha256` is required for states 5-8,
optional for state 4 only when all sixteen successful chained cells exist, and
null for states 2-3; `anchor_sha256` is required for every persisted state.
`closure_snapshot_sha256` is null exactly for states 2-6 and is a required
lowercase SHA-256 exactly for states 7-8.
`post_freeze_sha256` is nullable only for state 2 under the protected-input
failure representation defined above; all other hash fields are non-null
lowercase 64-hex strings unless explicitly declared nullable.
`review_record_sha256` is nullable for states 2-6 and required for states 7-8;
`visual_gates` follows the same nullability.
States 2-3 require matrix/repeat status `NOT_REACHED/NOT_REACHED`; state 4
requires `FAIL/NOT_REACHED`; state 5 requires `PASS/FAIL`; and states 6-8
require `PASS/PASS`. The wrapper status must equal the status inside its hashed
fixed-path evidence object.

`descriptive_contrasts` is null for terminal states 2-6. For states 7-8 it is
the name-sorted exact twelve-record product of metrics
`visual_pass_indicator`, `full_rgb_mean_u8`, `cyan_channel_excess_u8`, and
`rec709_luminance_u8` with contrasts `AO_ASSOCIATION`, `RT_ASSOCIATION`, and
`AO_RT_INTERACTION`. Each exact record is `{name, metric, cell_values,
estimate}` and `name` is exactly `<metric>__<contrast>`.
`cell_values` has exactly the four canonical variant keys and finite numeric
values. Visual PASS/FAIL encodes as 1.0/0.0. For each bound source PNG, decode
uint8 RGB and compute the arithmetic all-channel mean, mean
`(G+B)/2-R`, and mean `0.2126R+0.7152G+0.0722B`; average the six image values
within each replicate and then the four replicate means for the cell value.
Apply the three already declared contrast equations exactly; no rounding is
allowed before canonical serialization. `operational_preference` is the
canonical four-record list of exact
`{variant, score}` with two-integer scores. `visually_passed_configuration` is
null or one canonical variant. `claim_boundary` is exact
`{allowed, blocked}`, each a sorted unique list of non-empty strings. Unknown,
missing, or mistyped fields fail before hashing.

## Closed CLI Surfaces

Use experiment ID `real_beaker_ao_rt_matrix_v3_20260712_003` and aggregate root
`/cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/real_beaker_ao_rt_matrix_v3_20260712_003`.

Cell mode requires all four single-use options together:

- `--visual-prototype-render-diagnostic-variant <canonical variant>`;
- `--render-diagnostic-experiment-id real_beaker_ao_rt_matrix_v3_20260712_003`;
- `--render-diagnostic-replicate <A|B|C|D>`;
- `--render-diagnostic-order-index <0|1|2|3>`.

It also requires exact C lighting, display-fill prototype scope/candidate, and
an `--out-root` equal to
`<aggregate>/cells/<replicate>_<order-index>_<variant>`. The replicate/variant
pair must match the declared balanced order. Missing, repeated, extra, mixed,
wrong-path, or wrong-order arguments fail before output or Isaac boot.
Cell mode also requires exact `headless=true`, `960x540`, `15 fps`,
`warmup_updates=8`, and `camera_warmup_updates=8`; per-cell overrides fail
before output creation.
After all pre-I/O validation and freeze/identity checks pass, the parent cell
launcher publishes the first anchor and intent with the atomic staged-root
protocol; later intents are create-exclusively written and fsynced at
`<aggregate>/launch_intents/<replicate>_<order-index>_<variant>.json` before
creating the cell root or starting the child. Every later intent binds the
immediately preceding intent and successful cell evidence. An intent with no final cell
evidence means launched artifact failure; an exact slot with neither intent nor
cell root means not launched/incomplete. A cell root without its matching
intent is mixed evidence, never inferred as a launch.
Successful cells write fixed `matrix_cell_evidence.json`,
`matrix_media_index.json`, and `matrix_frame_bindings.json` sidecars in the cell
root. Failed cells write fixed `matrix_cell_failure_evidence.json`; filenames
are mutually exclusive at aggregate validation.

Aggregate mode is exactly:

```text
--render-diagnostic-aggregate-only
--render-diagnostic-experiment-root <exact aggregate root>
--render-diagnostic-pre-freeze <path>
--render-diagnostic-post-freeze <path>
[--render-diagnostic-review-record <path>]
```

The first four are required once; the review record is optional only so states
2-6 can be finalized when review is impossible or not reached. Aggregate mode
rejects every accepted-input, candidate, lighting, cell, render-size, runtime-
child, custom-manifest, or output-root option, performs no Isaac import/boot,
reads only the 16 exact cell paths and their 16 exact launch-intent paths (no
glob-based cell discovery). It also performs a non-recursive, sorted directory
enumeration of `<aggregate>/cells` and `<aggregate>/launch_intents`; names not
in the exact 16-name allowlists are recorded as `unexpected_paths` and force
state 4. It then create-exclusively writes the fixed
`<aggregate>/matrix_decision.json`. A complete stable machine matrix without a
valid review record resolves to `INDETERMINATE_VISUAL_REVIEW`, never PASS/FAIL.
The pre/post/implementation paths must be the exact anchor-bound fixed paths.
On the first aggregate attempt the fixed post path must be absent and aggregate
mode creates its chain-bound envelope under lock. After a crash before decision
publication, a subsequent attempt may reuse it only after exact envelope,
chain, registry, root, and lock validation; arbitrary preexisting tree snapshots
or envelopes are never accepted.

Aggregate serialization uses one fixed sibling lock outside the replaceable
experiment directory:
`<aggregate-parent>/.real_beaker_ao_rt_matrix_v3_20260712_003.aggregate.lock`.
The lock is created once with `O_CREAT|O_EXCL|O_NOFOLLOW` before atomic first-
root publication, and its `(st_dev,st_ino)` is bound into the experiment
anchor. Every launcher and aggregator opens that exact inode, acquires a
nonblocking exclusive `flock`, then rechecks both the lock path identity and the
anchor-bound aggregate-root identity before and after its operation. An
unlinked, renamed, recreated, or symlinked lock/root fails; it is never silently
accepted as a new experiment. A launcher holds the lock from before intent
publication through child exit and final success/failure evidence. It passes
the same locked file descriptor to the runtime child with close-on-exec
disabled; the child never unlocks it and process exit closes it. Therefore a
killed parent cannot release the experiment lock while an orphan child remains
alive, and aggregate mode cannot publish any state until every launcher/child
has quiesced. The final publication guard rebuilds the complete machine,
aggregate-cell-index, fixed evidence, review, contrasts, terminal predicates,
and decision. For states 7-8 it does so from the atomically published
independent closure snapshot; for states 2-6 it reopens the pinned available
original evidence and requires `closure_snapshot_sha256=null`. It then performs
atomic create-exclusive publication. Any drift prevents publication. The
decision file is opened and published relative to the still-pinned root
descriptor, then the root and lock identities are rechecked before releasing
the lock.

The integrity model covers crashes, cooperating or ordinary concurrent
launch/aggregate processes, accidental edits, stable renames/replacements, and
symlink substitution by the experiment owner. A privileged or deliberately
timed malicious same-UID process that mutates files only inside an individual
read/render/check window and restores them before the next observation is
outside both the prevention and reliable-detection boundary unless bytes have
already been captured into the immutable authority defined by the final
hardening amendment. Read-only modes, directory FDs, and pre/post hashes are
not claimed as a same-UID security boundary. Decision validation still detects
stable post-publication closure changes by requiring the closure hash and
complete validator to succeed.

## TDD Contract

Write failing tests first. Require:

1. Add an exact single-use prototype option with canonical values
   `AO0_RT4_CONTROL`, `AO0_RT12`, `AO1_RT4`, and `AO1_RT12`; reject empty,
   padded, case-changed, repeated, and unknown values.
2. Every value, including explicitly supplied `AO0_RT4_CONTROL`, is legal only
   with exact
   `--visual-prototype-display-fill-only`, exact `OMNI_REF_DISPLAY_FILL`, and
   `C_CONTROL`, plus the exact experiment/replicate/order/path tuple from Closed
   CLI Surfaces. Reject them before input reads, output creation, or Isaac boot.
3. Extend the effective replay look contract to bind the diagnostic variant,
   full explicit render settings, RT subframes, and whether normal remediation
   is required/applied. Bump its schema version. Any nested change must alter
   the effective hash; legacy default C/B CLI semantics remain unchanged even
   though the expanded canonical contract hash necessarily changes.
4. Implement projection
   `effective_replay_look_matrix_projection_v1` over a validated full
   schema-v2 effective-look JSON object. Require and remove exactly these JSON
   Pointers:
   `/render_diagnostic_variant_id`,
   `/render_settings/ambient_occlusion_enabled`,
   `/render_settings/rt_subframes`,
   `/effective_replay_non_lighting_contract_sha256`, and
   `/effective_replay_look_contract_sha256`.
   Missing paths fail projection; all unlisted and unexpected fields are
   retained and therefore cause comparison mismatch. Serialize the projected
   object with sorted keys, compact separators, finite JSON values, and UTF-8,
   then require byte equality and equal SHA-256 across all four variants. No
   wildcard, prefix, semantic-label, or recursive derived-field removal is
   allowed.
5. Bind the full effective contract and hash through dry plan, provenance,
   candidate contract/manifest, every frame binding, binding artifact,
   preclose/final/failure manifests, and clean-exit finalization.
6. Runtime must re-resolve the frozen contract after `SimulationApp` boot, set
   every listed RTX registry value with exact type/tolerance rules, execute an
   update barrier, read every registry value back, and reject a mismatch before
   candidate finalization. Evidence wording must distinguish requested value,
   registry readback, and renderer-consumption verification status.
   Booleans and integers require exact type/value; `rayLength` requires a finite
   float within absolute tolerance `1e-6`. Missing/`None` readback fails.
7. Every cell requires the exact normal-block contract and a successful frozen
   reopen verification. No diagnostic option in v3 may disable remediation.
8. Candidate/top/frame validators reject missing, tampered, or mixed matrix
   variants and render-setting hashes.
9. Existing default C/B behavior, formal-scope restrictions, authority/source,
   material, camera, geometry, stopped-timeline, zero-delta, no-point-mutation,
   and immutable-input contracts remain unchanged.
10. Add an exact matrix-closure validator requiring exactly sixteen successful
    cells: one A, B, C, and D replicate for each canonical variant, no missing,
    duplicate, extra, mixed-tool, mixed-source, mixed-authority, mixed-normal,
    mixed-material, mixed-camera, failed, or partial cell. Test the fixed launch
    intents and cell-status index so never-launched, launched-without-evidence,
    explicit failure evidence, and successful evidence are distinct.
11. Bind renderer/device/process/order/cold-start metadata and require equal
    implementation source maps and compatible runtime/device identity across
    all cells.
12. Add replicate image-stability checks at frames 0/300/600 for both primary
    cameras. For each variant/view/frame, compare all six A-D replicate pairs.
    Require every pair's RGB MAE <= 5 and PSNR >= 30 dB; otherwise classify the
    matrix `INDETERMINATE_REPEAT`. Human hard-gate agreement is not part of this
    pre-review predicate and is handled only by `INDETERMINATE_VISUAL_REVIEW`.
13. Matrix mode is a strictly non-deliverable diagnostic lifecycle. Internal
    frozen static entries needed for isolated capture are allowed but must be
    named and classified as capture evidence, not delivery export. Require
    `standalone_final_evidence_authority=false`, `exporter_admitted=false`,
    `visual_selection_eligible=false`, and all formal/delivery flags false.
14. Existing output roots and protected old evidence reject overwrite with
    create-exclusive semantics. Pre/post registered tree hashes must match.
    Invalid pre-I/O invocations intentionally create no failure manifest; every
    failure after lawful output creation must preserve partial failure evidence.
15. Test all terminal classifications: preflight scope rejection, registry
    mismatch, source/authority mutation, nonzero child exit, missing/corrupt
    media, finalization failure, protected-tree mismatch, incomplete/unstable
    matrix, indeterminate/conflicting review, reproducible all-fail, and
    reproducible pass. Only the final two permit a next-phase interpretation.
16. Test the aggregate-only parser/mode as a closed surface: exact required and
    optional arguments, no cell/runtime/input flags, no Isaac import, fixed cell
    discovery, fixed output path, create-exclusive decision, and missing review
    resolving only to the permitted indeterminate state. Validate all exact
    cell, media, status, matrix, repeat, blind-review, unblinding, gate,
    contrast, predicate, and decision schemas with missing/extra/type-tampered
    fixtures.
17. Test every evidence-integrity boundary: ancestor/leaf/broken symlinks;
    protected-input mutation between launches; missing or corrupt pre-freeze
    and implementation freeze after the first intent; aggregate-root
    rename/replacement under lock; mutation of replay manifests, sidecars, MDL,
    images, review maps/sheets/sources, fixed evidence, contrasts, and the
    aggregate cell index at the final publication guard. Every case must either
    persist the correct higher-priority non-PASS state or leave no decision.
18. Test the atomic anchor-plus-first-intent publish with injected failures at
    every file write, fsync, and rename boundary; no fixed root may be partial.
    Test the exact sixteen-link predecessor chain, anchor-bound root/lock inode
    checks, post seal, independent-copy closure snapshot, read-only modes, and
    state-7/8 decision reconstruction solely from snapshot bytes. Mutating
    originals after snapshot publication must not change the rebuilt decision;
    mutating the snapshot must make the decision non-authoritative. Separately
    test that every state 2-6 decision remains reachable without a complete
    snapshot, with the exact post-seal nullability above. Test that the child
    inherits the locked descriptor, a killed-parent/live-child process prevents
    aggregate lock acquisition, and final-closure rename/replacement is caught
    by its pinned manifest identity before decision publication. Test that only
    aggregate mode under the anchor-bound lock can create the fixed post-freeze
    envelope and that prebuilt, substituted, wrong-anchor, wrong-chain-length,
    or wrong-last-artifact envelopes are rejected.

## Terminal State Machine

Apply this closed precedence order; the first matching state wins and lower
states cannot override it:

1. `STOP_PREFLIGHT_REJECTED_NO_OUTPUT`: invalid CLI/scope/identity before lawful
   output creation, including an implementation/source mutation detected before
   atomic publication of the anchor-plus-first-intent root; intentionally no
   manifest. An abandoned sibling staging directory or unbound external lock is
   not lawful output and may be reused only after exact regular-file/lock-id
   validation.
2. `STOP_PROTECTED_INPUT_MUTATION`: any registered tree/file/implementation
   mutation detected after the anchor-plus-first-intent root was atomically
   published and its
   pre-freeze accepted; preserve the strongest available aggregate failure
   manifest. If the current pre-freeze or implementation-freeze file is now
   missing/corrupt, recover the accepted non-null pre/implementation hashes from
   the anchor and cross-check the first intent. There is no lawful state with a
   fixed aggregate root but without both of those valid objects.
3. `STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE`: registry mismatch, accepted-input
   mismatch, nonzero child exit, runtime exception, missing/corrupt media,
   cleanup failure, finalization failure, or any required launched slot whose
   manifest is absent/partial/non-success; preserve cell and aggregate failure
   evidence.
4. `INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED`: all supplied cell manifests are
   individually successful, but exact sixteen-cell set closure,
   implementation/runtime/device/MDL/source/authority/material/normal/geometry/
   camera equality, or required manifest closure fails without a higher stop.
5. `INDETERMINATE_REPEAT`: any required replicate image pair violates MAE/PSNR
   limits.
6. `INDETERMINATE_VISUAL_REVIEW`: review missing, non-independent, corrupt,
   conflicting, unmappable, or any required view/verdict indeterminate.
7. `FAIL_NO_RENDER_SETTING_RECOVERY`: exact stable matrix complete and all four
   tested configurations fail reproducibly.
8. `PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC`: exact stable matrix complete, all
   four configurations have determinate reproducible PASS/FAIL outcomes, and at
   least one tested configuration passes reproducibly.

Every lawful aggregate attempt writes create-exclusively one
`matrix_decision.json` with the terminal code, ordered evaluated predicates,
supporting manifest hashes, and blocked/allowed claims. Codes 1-6 authorize no
visual association or next-phase interpretation. Codes 7-8 authorize only the
next planning action stated below and remain non-deliverable.

## Runtime Sequence

1. Run focused and full system-Python tests.
2. Freeze protected old inputs/evidence outside those trees.
3. Render the sixteen balanced fresh-process runs at 960x540 over all 21
   accepted frames and all three cameras, with no code or render-input edits
   between runs.
   Atomically publish the anchored root plus first intent, then require each
   subsequent intent to bind the immediately preceding successful cell.
   Immediately before each intent and after each child exits, rebuild the live
   protected registry and implementation identity and compare both to their
   accepted freezes. Stop launching new cells on the first mismatch.
4. Verify clean Isaac child exits, image/video decoding, exact source/authority/
   trace/material/geometry/normal/camera hashes, explicit RTX readback, stopped
   timelines, zero Replicator delta, and no default-time point mutation.
5. Reverify protected tree hashes. A mismatch terminates the experiment as
   `STOP_PROTECTED_INPUT_MUTATION` with no visual or causal interpretation.
   After the last launcher/child has quiesced, generate the post-freeze. After
   the final successful cell only, additionally generate the successful post
   seal in a checked operation binding the final chain hashes.
6. Validate exact sixteen-cell closure and pixel-only replicate image stability.
   A launched
   required slot with missing/failed/partial evidence is
   `STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE`. When every supplied cell is
   individually successful but the set is missing, duplicate, extra, or mixed,
   terminate as `INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED`. A complete matrix
   with unstable replicate pixels terminates as `INDETERMINATE_REPEAT`.
   Hold the fixed external aggregate lock for all aggregate reads, evidence
   writes, final closure rebuilding, and decision publication; reject aggregate
   directory identity changes while the lock is held.
7. Create anonymous, hash-bound frame-0/300/600 close-up and pair sheets. Bind
   every panel to its source PNG hash, preserve label mapping separately, and
   obtain a fresh clean-room visual review whose identity and independence are
   recorded.
   Produce one four-column x three-row sheet per replicate and primary view:
   eight sheets total. Columns are freshly blinded variant labels and rows are
   frames 0/300/600. The reviewer receives no implementation or condition map.
   The create-exclusive review record must bind: every sheet path/hash; a
   canonical ordered panel-to-source-PNG mapping and its hash; a separately
   stored blinded label-map path/hash; reviewer/session mechanism and
   independence fields; the raw blinded `panel_id` verdict list and its
   canonical hash; the deterministic unblinded verdict object and hash; and the
   final derived gate hash. The aggregate decision binds the complete review
   record hash. Missing/mismatched sheet, mapping, label, reviewer, or verdict
   hashes force `INDETERMINATE_VISUAL_REVIEW`.
   Once review validation is complete, create and atomically publish the
   independent read-only final closure snapshot. Rebuild machine, review,
   contrast, terminal, and decision objects from that snapshot before decision
   publication; no original run path remains authoritative for PASS.
8. Apply the hard material gate separately to every cell and replicate:
   `top_is_nearly_black`, `body_is_ink_like`, and `cyan_top_not_readable` must
   all be false; close-up and pair-context material verdicts must both pass.
   The reviewer returns one determinate record for each of the six required
   panels per cell/replicate: frames 0/300/600 x close-up/pair-context. A panel
   is `PASS` only when its material verdict is PASS, all three hard flags are
   false, containment/grounding is PASS, and no external liquid, penetration,
   starburst, broken normal, or framing blocker is visible. A panel is `FAIL`
   when the record is complete and any hard flag, material failure,
   containment/grounding failure, or listed blocker is present. WARN, missing,
   malformed, or reviewer-disputed panels are indeterminate. A replicate is
   PASS only if all six panels pass, FAIL only if all six are determinate and at
   least one fails, and otherwise indeterminate. A configuration is reproducible
   PASS or FAIL only if all A-D replicates have that exact outcome; all other
   combinations force `INDETERMINATE_VISUAL_REVIEW`.
   The reviewer returns only the `raw_blinded_verdicts` list defined in
   Canonical Hash Schemas. After its hash is fixed, the aggregator performs the
   declared two-map join. The resulting unblinded verdict object is exactly
   `verdicts[variant][replicate][view][frame]`, with canonical variant keys
   `AO0_RT4_CONTROL`, `AO0_RT12`, `AO1_RT4`, `AO1_RT12`; replicate keys
   `A`,`B`,`C`,`D`; view keys `source_beaker_closeup`,`context`; and frame keys
   `0000`,`0300`,`0600`: exactly 96 leaf records. Each leaf has exactly
   `panel_id`, `source_png_sha256`, `material_verdict`, `hard_flags` (exactly the
   three named booleans), `containment_and_grounding`, `external_liquid_visible`,
   `penetration_visible`, `starburst_visible`, `broken_normal_visible`,
   `framing_blocker_visible`, and `visible_evidence`. Missing, extra, duplicate,
   unmappable, WARN, or malformed leaves are indeterminate. Derivation iterates
   the canonical key orders above, computes leaf -> replicate -> configuration
   gates exactly as specified, and stores all intermediate gates and hashes.
9. A visual result is usable only when all four fresh-process replicates receive
   the same gate outcome. Reviewer disagreement, missing views, or indeterminate
   review is `INDETERMINATE_VISUAL_REVIEW`, not pass or all-fail evidence.
10. Only after all four configurations have determinate reproducible PASS/FAIL
    outcomes, if one or more pass, record the first passing tested
    configuration under the fixed operational-preference ordering
    `AO0_RT4_CONTROL < AO0_RT12 < AO1_RT4 < AO1_RT12` as a
    `visually_passed_render_diagnostic`, not a minimal setting or selected look,
    and write the next reviewed formalization/boundary-test plan.
11. If all four cells fail reproducibly, record
    `FAIL_NO_RENDER_SETTING_RECOVERY` and write a separately reviewed,
    quarantined raw-normal or historical-stage reproduction plan. Do not run it
    under this plan.

## Acceptance And Stop Boundaries

- No cell may change physics, accepted point positions, display-fill geometry,
  material tint, cameras, or C lighting.
- No run claims an instrumented zero physics-step count while
  `physics_step_count_instrumented=false`; it may claim only stopped timeline,
  zero Replicator delta, and unchanged observed default-time point attributes.
- Registry readback proves only requested Carb state, not renderer consumption.
- Results support only associations with requested/read-back AO registry values
  and captured subframe levels under the fixed source, C lighting, material,
  cameras, Isaac 4.1 runtime, and GPU; they do not prove consumed AO state.
- No matrix result directly permits formal B/C replay, exporter work, package
  localization, or colleague delivery.

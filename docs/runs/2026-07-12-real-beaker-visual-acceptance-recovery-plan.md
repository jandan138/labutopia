# Real-Beaker Support-Aligned Delivery Plan

## Objective

Deliver a portable static USD entry for the LabUtopia `level1_pour` scene that:

1. uses the task-config midpoint layout at the real `/World/beaker1` and
   `/World/beaker2` paths;
2. places both visible beaker bottoms deterministically on the authored support;
3. contains the accepted A18-proportional cyan display liquid in the source cup;
4. has a new 600-step retention authority for the support-aligned source stage;
5. opens and renders from a clean copy without original-path dependencies; and
6. passes independent close and pair visual review.

The result is not an exact recorded expert episode, a physical-volume match, a
physical isosurface, a pour result, or a cross-renderer material guarantee.

## Established Facts

- `config/level1_pour.yaml` SHA-256 is
  `ec745b14e13c63c5b906ea2b76d08b5d64ef473dfe0567e6deef9252f17950c1`.
- The config ranges produce midpoint parent translations
  `(0.255, -0.245, 0.87)` for beaker1 and `(0.295, 0.075, 0.87)` for beaker2.
- The 2026-06-09 expert run sampled random XY values and did not persist a
  structured initial-state record. The midpoint USD is therefore a canonical
  config example, not an exact episode replay.
- The current localized liquid source SHA-256 is
  `77607b6bdf3b6cba419e1bc17943bdb3e220b497a77e98d7665e98f779406211`.
- Its static beaker bbox bottoms are about 29 mm and 47 mm above `/World/Cube`.
- Isaac Sim 4.1 runtime evidence shows the rigid bodies fall to the support, but
  the dynamic penetration observed by one probe is not the static-layout formula.
- Both source beaker meshes contain defective face-varying bottom normals. The
  empty target cup exhibits the same radial starburst, so the fluid proxy is not
  its root cause.
- `OMNI_REF_DISPLAY_FILL` produces a clear, contained cyan fill, but the current
  raised layout and defective beaker normals fail delivery visual review.

## Review Summary

Three independent reviews covered architecture, completeness/boundaries, and
risk. All returned `REVISE`. This plan resolves their blocking findings:

- Moving real physics prims creates a new physical scene. The old P4096_S2 result
  remains immutable baseline evidence but is not authority for the final stage.
  A new 600-step P4096_S2 run must pass on the support-aligned source hash.
- The final source uses a deterministic support formula, not an empirical settled
  Z from a single simulation frame.
- Config-midpoint semantics and the prohibition on exact-expert claims are
  machine-readable and hash-bound.
- Normal blocking and deterministic normal recomputation are separate IDs. This
  iteration implements only `beaker_normals_block_v1`; a failed visual gate
  requires a separately reviewed follow-up version.
- Accepted trace hashes and presentation geometry hashes have distinct names and
  meanings. The grounded run removes the need to translate an old trace.
- Package content is immutable after hashing/review. Delivery approval is a
  detached attestation outside the package, preventing a tree-hash cycle.
- Clean-copy verification includes dependency containment, semantic USD readback,
  offline/no-original-path execution, and filesystem escape checks.

## Claim Boundary

Every manifest and README must contain these exact semantic fields:

```text
layout_semantics=config_range_midpoint_support_aligned
exact_expert_episode_layout=false
expert_episode_id=null
reset_z_from_config_m=0.87
support_alignment_is_static_authoring=true
old_physics_authority_applies_to_support_aligned_stage=false
physical_volume_parity_claim_allowed=false
free_surface_shape_claim_allowed=false
fluid_dynamics_claim_allowed=false
pour_success_claim_allowed=false
native_normal_fidelity=false
```

The raw localized source, old accepted summary/trace/log, and frozen `_024_smoke`
tree remain byte-identical. They are provenance, not final-stage authority.

## Files

Create:

- `tools/labutopia_fluid/run_build_level1_pour_support_aligned_scene.py`
- `tests/test_level1_pour_support_aligned_scene.py`
- `tools/labutopia_fluid/run_build_support_aligned_authority_bundle.py`
- `tests/test_support_aligned_authority_bundle.py`
- `tests/test_export_real_beaker_fluid_usd.py`
- `tools/labutopia_fluid/run_export_real_beaker_fluid_usd.py`

Modify:

- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- `tests/test_real_beaker_runtime_contract.py`
- evidence/README documentation only after generated evidence exists

Do not modify the accepted physics runner
`tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py`.

## Canonical Hashing

All newly introduced JSON hashes use `canonical_json_sha256_v1`:

- UTF-8 encoded JSON;
- ASCII escaping enabled;
- object keys sorted;
- separators `(',', ':')`;
- NaN and infinities rejected;
- booleans rejected where numeric values are required;
- Python shortest round-trip finite float text; and
- arrays remain order-sensitive.

One validator recomputes the complete identity bundle and fails on any missing,
duplicate, copied-without-recomputation, or inconsistent component:

```text
config_layout_contract_sha256
support_aligned_source_contract_sha256
accepted_authority_bundle_sha256
beaker_normal_remediation_contract_sha256
display_surface_model_contract_sha256
presentation_look_contract_sha256
presentation_scene_contract_sha256
```

The aggregate scene hash is recomputed in dry plan, authored USD attributes,
frame bindings, candidate/replay manifests, visual selection, package manifest,
clean-copy semantic verification, and detached promotion attestation.

## TDD Sequence

### 1. Support-Aligned Source Tests

Write `tests/test_level1_pour_support_aligned_scene.py` first. Require:

- structured YAML parsing and exact config SHA verification;
- midpoint recomputation from all four XY intervals and fixed reset Z;
- rejection of changed ranges, non-finite values, reversed intervals, changed
  config hash, or any exact-expert claim;
- source SHA verification and exact prim paths `/World/beaker1`,
  `/World/beaker1/mesh`, `/World/beaker2`, `/World/beaker2/mesh`,
  `/World/ParticleSet`, and `/World/Cube`;
- support geometry/world-transform/collision signature hashing;
- exact formula
  `target_bottom_z = support_bbox_max_z + support_clearance_m`, with
  `support_clearance_m = 0.0` and absolute contact tolerance `1e-6 m`;
- per-beaker initial parent XYZ, initial bbox bottom, final parent Z, downward
  delta Z, final bbox bottom, support top, contact gap, and tolerance;
- preservation of parent XY, rotation, scale, mesh points/faces, material binding,
  rigid-body/collision APIs, and all non-transform physics attributes;
- an explicit ownership contract stating that `/World/ParticleSet` is the legacy
  calibration/particle set for source cup `/World/beaker2`, never beaker1;
- application of exactly `/World/beaker2`'s computed delta Z to
  `/World/ParticleSet` as an Xform op, preserving its point array/hash;
- readback that the ParticleSet-to-beaker2 canonical coordinates and calibration
  bounds are unchanged, while applying beaker1's delta or any mixed delta is
  rejected;
- controlled-spawn source isolation in the support overlay: explicitly empty
  `/World/fluid/Cylinder.physxParticleSampling:particles` and
  `/World/ParticleSet.physxParticle:particleSystem` targets, set sampler volume,
  particle-set fluid/self-collision, and legacy particle-system enabled flags to
  false, while retaining the 50k point array solely as inert calibration data;
- removal of the composed `PhysxParticleSamplingAPI` opinion in the support
  overlay; keep `/World/ParticleSystem` active but disabled and hidden to avoid
  expired-prim behavior;
- a fixed layer-order contract proving the file-backed support overlay is stronger
  than the localized source, explicitly authors the empty target lists, and fails
  on edit-target or sublayer-order drift;
- plain composed readback proving those stronger empty/false opinions suppress the
  weaker source graph. The weak source opinions remain immutable; because composed
  `targets_before=[]`, the frozen runner does not enter its `ClearTargets(True)`
  branch. Reject partial isolation or any composed active legacy relationship;
- calibration readback proving ParticleSet local/canonical bounds stay unchanged
  while world bounds shift by exactly beaker2 delta; do not claim world bounds are
  unchanged;
- output entry metadata, relative dependency path, source/config/tool hashes, and
  deterministic layout-contract hash;
- plain reopen/readback reproducing the same bounds and contract; and
- rejection of overwrite, wrong edit target, source mutation, upward movement,
  penetration outside tolerance, missing prims, or unexpected existing overlay.

Implement the builder only after these tests fail for the expected reasons.

### 2. New Physical Authority

Generate a run-scoped support-aligned entry. Then run the existing matrix/runtime
path for selected cell P4096_S2 with the same SI units, particle count, seed,
offset hierarchy, wrapper D4A_018, 600 logical steps, and trace cadence.

Promotion to replay input requires:

- both strict and top-level classifications equal
  `PASS_VISIBLE_BEAKER_STATIC_HOLD`;
- zero visible leak/escape/below-table counts under existing gates;
- source hash equal to the support-aligned entry hash;
- legacy authored particle graph already isolated, with the retained ParticleSet
  classified as inert calibration data and the controlled spawn as sole runtime
  particle authority;
- runtime preflight binding separately named
  `localized_source_usd_sha256`, `support_overlay_usd_sha256`, and
  `support_entry_root_usd_sha256`, plus composed empty relationships, absent
  sampling API, disabled legacy system, and the exact controlled-runtime prim
  paths; all three file hashes enter `accepted_authority_bundle_sha256`;
- run-scoped Kit-log segment archived and hash-bound;
- strict trace schema and readback identity recomputed; and
- a new `accepted_authority_bundle_sha256` binding source, summary, trace, log,
  runner, config-layout contract, and support contract.

Build that authority as a new atomic sibling directory rather than mutating the
runtime evidence directory. The builder must snapshot all inputs, independently
recompute the strict trace identity, extract and hash exactly the declared
run-scoped Kit-log byte segment, reject overwrite, and bind the three separately
named source-layer hashes plus the unique `/World/CompletedPBD` runtime authority.
It must not fabricate an observed shell command or reuse the old authority bundle.
The log proof binds the declared byte offset and count, exact segment hash, and
the snapshotted original log's complete SHA-256 and byte size; pre/post file
identity checks reject mutation during the read. The output uses a unique
temporary sibling, a cross-process exclusive lock, complete readback validation,
and atomic no-replace promotion. Prefer kernel `RENAME_NOREPLACE`; on filesystems
such as CPFS that return `EINVAL` for that flag, do not use a racy check-then-rename
fallback. Atomically reserve the final path with no-replace `mkdir`, move only the
already validated staging files into that reserved directory, and publish an
exclusive `PUBLISH_COMPLETE.json` commit marker last. Consumers must reject any
directory without a valid marker binding the bundle hash and publish mode. A
partial directory remains fail-closed and is never overwritten automatically.
The bundle records the selected publish mode. It also binds the frozen runner's path,
SHA-256, runtime-contract schema version, Isaac Sim version, strict trace schema
version/hash, trace file hash, and exact cadence `0,30,...,600`.
The accepted frozen-runner baseline is the already accepted P4096_S2 SHA-256
`25f02f58e5a4d0adc11beaf503f8d5e74c5fcfafc7b1b7078e1a971ae50118e4`;
Git cleanliness is not the authority because that validated runner predates this
phase and was already dirty relative to HEAD. Future drift from this fixed hash
fails closed. Anchor that baseline to the pre-existing accepted matrix manifest
`fluid_spike_real_beaker_static_hold_matrix_si600_restoffset_20260711.json`
(SHA-256 `582c8ee08a1025e71750782be8a6c8f6dbfaa3320eb8f73360b8608fdc26cf44`),
whose accepted P4096_S2 record binds the same runner hash and the old summary hash
`023290a49b9d1a7a0db6ecbe5dab2f4fd931e3f4948ceffc61866223bcc612cf`.
Validate both records and include a byte-identical read-only runner snapshot in
the new authority artifacts; this is the independent frozen baseline, not HEAD.
After the Isaac process is closed, copy the complete stable Kit log snapshot into
staging and derive the declared segment only from that copy. Reject any input that
already contains `accepted_authority_bundle_sha256`, so the bundle cannot hash
itself through an input cycle. Independently compose the exported runtime overlay
over the exact support entry, enumerate every particle system, particle set,
sampler/emitter relationship and enabled flag, and hash the enumeration; combine
that offline enumeration with the same-run summary readback proving empty legacy
targets/API/flags and the sole active `/World/CompletedPBD` authority. Hash the
complete runtime evidence tree before and after bundle construction and reject any
change; all derived files remain outside that tree. Also snapshot every runtime
evidence file into the authority staging tree from stable bytes, bind that copied
tree to the same hash, and make consumers rely on the immutable copy rather than
the later mutability of the original run directory. The final validator enumerates
the entire authority directory and rejects every unregistered file. The CPFS
publisher uses atomic no-replace hard links for each regular file and no-replace
`mkdir` for each nested directory, with the commit marker linked last; it never
uses overwriting child `rename`. Hold an advisory `flock` in addition to the
exclusive lock file and verify the lock inode/token before and after publication.
Strict trace parsing also validates finite ordered AABB/centroid vectors and exact
nonnegative integer/count consistency for all region and visible-count fields.

The old authority is not transformed, copied, or renamed as the new authority.

### 3. Normal Remediation Tests

Add tests to `tests/test_real_beaker_runtime_contract.py` first. Require:

- exact ID `beaker_normals_block_v1` and mesh paths for both cups;
- source points/faces/normals/interpolation/subdivision/double-sided hashes;
- the original composed normals exist and use `faceVarying` interpolation;
- only the presentation layer authors a value block for `normals`;
- composed normals read back as absent after the block;
- source layer snapshot/hash, points, face arrays, transforms, material bindings,
  physics schemas, collision attributes, and relationships remain unchanged;
- no claim that RTX-generated normals were read back or hashed;
- the contract states `renderer_acceptance_scope=isaacsim41_rtx`; and
- fail-closed rejection of missing normals, changed source mesh signature,
  preexisting blocks, edit-target drift, partial one-cup application, or source
  mutation.

Do not implement normal recomputation or a material fallback in this iteration.
If the block-only prototype fails, write and review a new plan/version before the
next implementation.

### 4. Replay and Camera Tests

Retain the existing five-candidate order and `OMNI_REF_DISPLAY_FILL` model tests.
Update replay tests to require:

- the new grounded accepted authority bundle, with no old-trace translation;
- common normal/layout/look scene contract shared by all five candidates;
- distinct accepted world-trace, canonical display geometry, and authored
  world-geometry hashes;
- close/pair cameras projected from the grounded frame and actual support points;
- pair remains a mandatory primary view; an extra grounding view is supplemental;
- exact model/scene identity propagation through USD readback and frame bindings;
- timeline stopped, zero physics steps during presentation capture, and no point
  mutation during render-only replay; and
- frozen `_024_smoke` verifier version/hash and fail-stop behavior.

### 5. Export/Verification Tests

Write `tests/test_export_real_beaker_fluid_usd.py` before the exporter. Require:

- selection only when close and pair are both `PASS` and bind individual PNG
  hashes, review schema/version/mode, candidate ID, scene hash, and closed-app
  evidence;
- deterministic localization to a temporary sibling followed by atomic rename;
- immutable package content and deterministic `content_tree_sha256`;
- no absolute/original paths in sublayers, references, payloads, clips, asset
  attributes, MDL imports, or texture references;
- rejection of symlinks, outward hard links, `..` escapes, case-colliding names,
  unmanifested files, and files changed during verification;
- clean-copy LoadAll open in a randomized directory with isolated HOME/caches,
  network/remote resolver disabled, and the original package path denied;
- explicit allowlist only for runtime schemas/plugins, never scene content;
- semantic readback of defaultPrim, units/upAxis, support-aligned transforms,
  contact gaps, normal-block mode, material bindings, visibility, display model,
  proxy geometry, and scene hashes;
- exact clean-copy close/pair/native render hashes and run-scoped MDL/error scan;
- independent clean-copy close and pair `PASS`; and
- detached promotion attestation outside the immutable package. The attestation
  references content tree, semantic report, image hashes, and review hash, then
  rechecks all of them without writing into the package.

## Implementation Order

1. Run the new failing support-layout tests.
2. Implement and verify the support-aligned scene builder.
3. Generate the support-aligned source and run the new 600-step P4096_S2 gate.
4. Run the new failing normal/replay tests.
5. Implement `beaker_normals_block_v1`, grounded camera contracts, and identity
   propagation.
6. Capture one disposable block-only close/pair prototype with fixed liquid,
   camera, lighting, and material.
7. Obtain a fresh clean-room visual review. Both primary views must be `PASS`.
8. Only after visual PASS, run complete five-candidate smoke and formal replay.
9. Implement selection/export/clean-copy verification from failing tests.
10. Independently review exact clean-copy renders and write detached attestation.
11. Reverify old source/trace/log hashes, frozen `_024_smoke`, focused/full tests,
    `py_compile`, and `git diff --check`.
12. Run three-agent final architecture/completeness/risk review.

## Acceptance Gates

### Layout

- `layout_semantics=config_range_midpoint_support_aligned`.
- Exact-expert claims are false.
- Both beaker bbox bottoms equal `/World/Cube` bbox top within `1e-6 m`.
- Parent XY, rotations, scales, standard prim paths, and physics APIs are retained.

### Physics

- A new support-aligned-source P4096_S2 run passes all 600-step strict gates.
- The old run is baseline only and is never cited as final-stage authority.

### Visual

- Close: complete upright source cup, visible support around base, clear cyan top
  and side depth, no external liquid, black fallback, or starburst.
- Pair: both complete upright grounded cups, cyan liquid clearly inside source,
  no floating, penetration, leak, broken silhouette, or crack-like artifact.
- Pair `PASS` cannot be replaced by a supplemental view.

### Package

- Clean-copy dependency and semantic audits pass offline with original path denied.
- Exact clean-copy close and pair images independently pass.
- Package tree remains immutable after review.
- Detached attestation alone states `colleague_delivery_ready=true`.

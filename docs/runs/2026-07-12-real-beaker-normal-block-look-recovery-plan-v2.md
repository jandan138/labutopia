# Real-Beaker Normal-Block Look Recovery Plan v2

## Objective

Recover a visibly clear cyan `OMNI_REF_DISPLAY_FILL` result on the accepted
support-aligned, normals-blocked scene without changing physical authority,
source geometry, proxy geometry, material tint, cameras, or the normal
remediation.

The current `weekly_omniglass_C` formal replay is valid render evidence but has
no selectable candidate: the only macroscopically filled candidate renders with
a nearly black top. It remains immutable and not delivery-ready.

## Controlled Variable

Run one matched A/B diagnostic under the same implementation version:

- control: a newly rendered `weekly_omniglass_C` lighting prototype;
- treatment: a newly rendered `weekly_omniglass_C` prototype with only the
  repository's `weekly_omniglass_B` lighting block substituted;
- the old C formal replay is historical baseline only, not the A/B control;
- only the effective authored key/dome lighting block may differ;
- keep the A18 OmniGlass material values, `beaker_normals_block_v1`, final-frame
  display-fill mesh, grounded cameras, render resolution, refraction bounce
  setting, physical trace identity, and accepted authority hash unchanged.

Do not switch the complete B profile. Its unused camera and beaker-override
fields differ from C and are not part of this diagnostic. Define a pure-Python
`effective_replay_look_contract` that binds only what replay actually applies:

- base profile ID and full source-profile hash for provenance;
- lighting variant ID, lighting source-profile ID, and exact effective lighting;
- A18 liquid material values/hash;
- native beaker material retained and profile beaker override applied=false;
- measured replay cameras retained and profile camera applied=false;
- fixed RT subframes, refraction setting, AO state, shadow state, and all other
  explicitly controlled render settings; and
- a canonical effective-contract SHA-256 using the repository's existing
  sorted-key compact UTF-8 JSON hash function.

Do not add ambient occlusion, change liquid material inputs, recompute beaker
normals, change the display proxy, or alter the accepted authority in this
version. Those are separate variables and require another reviewed plan if this
single-variable probe fails.

## Files

Modify:

- `tools/labutopia_fluid/run_real_beaker_omniglass_replay.py`
- `tests/test_real_beaker_runtime_contract.py`

Generate only after tests pass:

- one new C-control and one new B-lighting `OMNI_REF_DISPLAY_FILL`
  visual-prototype run directory;
- a hash-bound clean-room blind visual-review record;
- immutable pre/post tree-freeze evidence for the authority, old C formal,
  current visual reviews, and old cyan/AO prototypes.

Never modify old source, authority, prototype, formal replay, or review files.

## TDD Contract

Write failing tests first. Require:

1. Add `--visual-prototype-lighting-variant` with exact argparse choices
   `C_CONTROL` and `B_LIGHTING`; default C behavior remains unchanged.
2. Reject empty, whitespace-padded, case-changed, unknown, and repeated values.
3. `B_LIGHTING` is legal only with the exact single-candidate
   `--visual-prototype-display-fill-only` scope. Formal scope plus B fails before
   filesystem input reads, output creation, or Isaac boot.
4. Parameterize B/C against canonical-five, display-fill-only, missing,
   duplicate, extra, and reordered candidate sets so the look option cannot
   bypass the existing candidate gate.
5. Resolve and freeze one pure-Python effective look contract before runtime.
   The source profile ID must match its resolved profile; hashes are stable,
   deep-copy safe, and change on any nested effective field change.
6. Dry plans, normalized execution provenance, candidate contracts, candidate
   manifests, every frame binding, the binding artifact, preclose manifest,
   final replay manifest, and runtime failure manifest bind the variant ID and
   effective-contract hash.
7. Frame-binding and top-manifest validators reject missing/tampered/mixed look
   IDs or hashes. Parent/child launch and clean-exit finalization preserve the
   exact frozen contract and never silently fall back to C.
8. Runtime re-resolution after SimulationApp boot must equal the preflight full
   effective contract, and the actually authored lighting record must match its
   effective lighting block before any candidate can finalize.
9. The C and B prototypes must have equal source-tool hashes and equal effective
   contracts after removing only the lighting variant/source/effective-lighting
   fields. AO, shadows, refraction, RT subframes, cameras, material, geometry,
   normal, authority, and source hashes are compared explicitly.
10. Existing default-C behavior and all authority, source, normal, camera,
    stopped-timeline, zero-delta, no-point-mutation, and immutable-input
    contracts remain unchanged. Do not claim an instrumented zero physics-step
    count while the runner records `physics_step_count_instrumented=false`.
11. Existing out-roots/manifests and all protected old evidence paths reject
    overwrite. Pre/post registered tree hashes must match after both prototypes.
12. Prototype and formal outputs remain non-deliverable until detached visual
    selection/export approval.

## Runtime Sequence

1. Run focused and full unit tests under system Python.
2. Freeze the protected input/evidence trees outside those trees.
3. Run a new support-aligned, normals-blocked `OMNI_REF_DISPLAY_FILL` C-control
   prototype, then a B-lighting treatment prototype, both 960x540 over all 21
   accepted trace frames and the same three cameras. Do not edit Python or
   render-affecting inputs between runs.
4. Verify clean Isaac child exits, all image/video decodes, immutable authority
   and source hashes, common normal hash, matched effective contracts except for
   lighting, stopped timelines, zero replicator delta, and no point mutation.
5. Reverify all protected tree hashes.
6. Create anonymous fixed frame-0/300/600 close and pair A/B review sheets.
7. Obtain a clean-room blind review that knows neither the variant labels nor
   the expected winner. Close and pair are separate gates. Each review binds PNG
   hashes, frame indices, camera hashes, effective-look hash, scene/authority
   hashes, and closed-app evidence.
8. Review only visible pixels. Close and pair must both show complete grounded
   cups, clear cyan liquid top/side depth, no external liquid, no starburst, and
   no penetration. Any `top_is_nearly_black=true`, `body_is_ink_like=true`, or
   `cyan_top_not_readable=true` forces a non-PASS material verdict; containment
   or grounding cannot compensate for a material WARN.
9. If either primary view is `WARN` or `FAIL`, do not select, run formal B, or
   enter exporter work. Write the next reviewed diagnostic plan.
10. If both are `PASS`, call the result a
    `visually_passed_look_candidate`, not a selected look. End this v2 phase and
    write a separately reviewed v3 plan for hash-bound visual approval, formal
    replay, and exporter admission.

## Acceptance

- `accepted_authority_bundle_sha256` remains
  `edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605`.
- Source USD SHA-256 remains
  `3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b`.
- Beaker normal contract SHA-256 remains
  `da174bdbe851d73346208c97babbc3f4a6ee09c1b4ee945afd7f15a36b6a8fcb`.
- The runner calls no physics-advance API, keeps the timeline stopped, uses zero
  replicator delta, and observes no default-time point mutation. An instrumented
  zero-step count is not claimed.
- Both primary visual views return `PASS`; otherwise there is no
  `visually_passed_look_candidate`.
- No prototype or formal replay directly claims colleague delivery readiness.
- This v2 plan never permits `B_LIGHTING` in formal scope and never admits the
  exporter. Prototype PASS alone is insufficient for either action.

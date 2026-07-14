# Real-Beaker Black-Liquid Causal Matrix Plan v3 Reviews

## Reviewed Artifact

- Plan: `docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-plan-v3.md`
- Original v3 sign-off SHA-256:
  `daf5aa595176e8edd76ce67eb45db7ee4b84beb715df4417eb790a45d8761fc4`
- Review mechanism: three independent ephemeral Codex executions from `/tmp`.
- Review isolation: repository implementation was not supplied; the complete
  plan was passed on stdin. User configuration, repository rules, skills, and
  the superpowers framework were disabled by instruction.

## Iterations

The architecture, completeness, and risk reviewers were rerun after each plan
revision. Blocking feedback closed during review included:

- fixed panel-map and blinded-label-map paths and hashes;
- canonical panel IDs, raw blinded verdicts, and deterministic unblinding;
- fixed terminal predicate order and early-stop evidence forms;
- pixel-only repeat stability before visual review;
- launch intents distinguishing not-launched from launched-without-evidence;
- exact cell, media, status, matrix, repeat, gate, and contrast schemas;
- closed nullability, renderer-readback wording, protected-input failure enums,
  and unexpected-path detection.
- atomic anchor-plus-first-intent root publication and a hash-linked sixteen-cell
  launch sequence;
- anchor-bound aggregate/lock identities, child-inherited lock ownership, and a
  chain-bound post-freeze envelope;
- terminal-specific post-seal/closure nullability and a deterministic,
  independent final-closure snapshot for PASS-capable states.

## Final Sign-Off

All three final reviewers returned exactly `GO` against the same final plan.

| Review angle | Verdict | Output SHA-256 |
| --- | --- | --- |
| Architecture and contract coherence | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Completeness, exact schemas, and edge cases | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Operational, scientific, and evidence-integrity risk | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |

Implementation may proceed under the reviewed TDD contract. Any experiment-
affecting plan or code change after the implementation identity is frozen
requires a new review/freeze cycle.

## Final Hardening Amendment

Final implementation review exposed additional runtime and publication risks,
so no formal path was created and a normative hardening amendment was reviewed:

- amended v3 plan SHA-256:
  `1c3b12f4922155a98ef16c2a59fae22012983ddab68b2e67ee5d865ab3bc156f`;
- hardening plan:
  `docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-hardening-plan.md`;
- final hardening SHA-256:
  `5ecf3e2547470a5f7e59784c99498b752811ab9320496ac3e524012273a62e85`.

Ten independent three-angle rounds were used to close blockers. The accepted
plan now requires:

- a deterministic first-party ZIP executed from a sealed read-only memfd with
  a pre-import `-I -S` bootstrap and exact inherited-FD contract;
- full localized USD/MDL/texture protection plus a per-cell read-only source
  dependency snapshot and artifact inventory;
- create-exclusive MDL/source copies that cannot follow destination links;
- an atomically published, self-contained `matrix_decision_authority` directory
  containing decision, commit, embedded intent, and states 7-8 final closure;
- one captured closure generation and a complete pre-rename staging rescan;
- an append-only anchor-bound lock journal whose first record binds the original
  aggregate-root inode and whose second record witnesses authority publication;
- exact crash, cleanup, poison, linearization, and idempotency outcomes for
  states 2-8.

The threat boundary explicitly does not claim prevention or reliable detection
of deliberately malicious same-UID `chmod`/`pwrite` attacks; CPFS provides no
fs-verity, different-UID, or read-only mount enforcement here. Ordinary
concurrency, accidental edits, stable replacements, and all code paths that
honor the experiment lock remain in scope.

All three final hardening reviewers returned exactly `GO` against the same two
hashes above.

| Review angle | Verdict | Output SHA-256 |
| --- | --- | --- |
| Architecture and contract coherence | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Completeness, exact schemas, and edge cases | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Evidence-integrity risk within the declared model | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |

## Product-Boundary Resolver Sign-Off

Actual Isaac 4.1 startup testing exposed a resolver difference not represented
by system Python: after `SimulationApp` boot, the USD resolver selected the
Conda `omni/mdl/core` files for `OmniGlass.mdl`, `OmniPBR.mdl`, and
`OmniSurfacePresets.mdl`. Formal paths remained absent while the plan and
implementation were amended to:

- protect the exact version-matched Conda MDL source root;
- copy all `Base/*.mdl` and the complete regular `mdl/` tree into each cell;
- install and read back cell-local MDL search paths before/after app boot;
- defer authoritative USD dependency resolution until Isaac is running;
- repeat dependency validation on the exported static USD and reject observed
  host/default-path fallback;
- make explicit/closure MDL lookup fail closed; and
- fix cell mode to headless 960x540, 15 fps, and 8+8 warm-up updates.

The final reviewed plan hashes are:

- v3 plan: `fa93ecaacffb91b45e788f1ebefa7211fc0a46d41e9dfc32665440839e033b42`;
- hardening amendment: `35b8a4966cfdf75123139e7e71b08aaf2d1b4a6688d48be247dba95ad842ca4a`.

Three independent final reviewers returned exactly `GO` against these bytes
and the corresponding implementation/tests:

| Review angle | Verdict | Output SHA-256 |
| --- | --- | --- |
| Architecture and contract coherence | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Completeness and boundary cases | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Formal-run execution risk | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |

Pre-freeze verification completed with:

- runtime contract: `343 passed`;
- related suite: `230 passed, 3 deselected`;
- static `py_compile` and `git diff --check`: PASS;
- Isaac full-MDL smoke: 189 copied files, NVIDIA core/support present, MDL
  search readback PASS, zero unresolved and zero outside-root dependencies;
- Isaac post-export smoke: cell-local static entry PASS; a deliberately
  host-absolute OmniGlass asset FAIL with the host path reported.

The three deselected historical-authority builder tests intentionally require
the old frozen physics-runner SHA and correctly reject rebuilding that accepted
authority from the evolved runner. The AO/RT matrix consumes the existing
accepted authority and frozen physical trace; it does not rebuild or relabel
the historical authority.

## CPFS First-Root Recovery Sign-Off

The first `_001` launch stopped before `SimulationApp` because the CPFS mount
returned `EINVAL` for `renameat2(RENAME_NOREPLACE)`. No aggregate root, cell,
or GPU output was created. The already-bound lock referred to the subsequently
cleaned staging inode, so `_001` was declared permanently poisoned rather than
reconstructed. Its identity, pre-freeze, lock, and failure report are preserved
as protected `_002` inputs.

The replacement `_002` plan uses an atomic empty target-directory reservation
when CPFS does not support `RENAME_NOREPLACE`: bind and fsync the reservation,
require the exact inode to remain empty, replace it with dirfd-relative
`rename`, then require the published inode to equal the source. Failure cleanup
removes only the unchanged empty reservation. A real same-mount probe passed
and was persisted before freeze.

Final `_002` plan hashes are:

- v3 plan: `ca4c1f314b889208c65ecfac53e0e839c438a60062aa566b0ed9c5b5462abad9`;
- hardening amendment: `d6101293adb5cf9e3e20c39bcc169c771d3095ebae1797e9e610d02e3b62e15d`.

Three independent implementation reviewers approved the reservation and
`_001/_002` isolation under the Product Integrity Boundary:

| Review angle | Verdict | Output SHA-256 |
| --- | --- | --- |
| Architecture and publication identity | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Completeness and recovery branches | `GO` | `a0f949497a74dde0c63a35cd9ab147012ffa007b019557ea5cecb9a243d0c5de` |
| Ordinary-concurrency and evidence risk | `GO` | `baf7eabb2c7ff234a212afc0afd160b882f2287ddd1abc78433464a6b45271bf` |

Final `_002` pre-freeze verification completed with:

- runtime contract: `349 passed`;
- related suite: `230 passed, 3 deselected` under the historical-authority
  rebuild exclusion described above;
- CPFS reservation branch and fixed-path focused tests: `10 passed`;
- persisted `_001` failure report SHA-256:
  `a65b6d40fd58bf6152b88bf121ede0e81ba824a305762d3ab805c2be65e755d2`;
- persisted `_002` CPFS probe SHA-256:
  `1f3e4a87b1a18e7835c54d6cfe947deca99909197d34520c6aaa38c9d4d6195e`;
- `py_compile`, JSON parsing, and `git diff --check`: PASS.

## Sealed-Child And Formal `_003` Launcher Sign-Off

The `_002` aggregate root and first launch intent published successfully, but
its child stopped in the sealed bootstrap before first-party import and before
`SimulationApp`: direct shell redirection made stdout/stderr regular files.
That failed slot is preserved. `_003` keeps the standard-FD contract and routes
every formal cell through a pipe logger and one exact sixteen-slot orchestrator.

The first final-entry review round returned one architecture `GO` and two
`NO-GO` verdicts. The blocking findings were closed before freeze:

- identity and pre-freeze are now required before any formal log, lock, or
  Python launch;
- the fixed interpreter is the regular nonlink `bin/python3.10` file;
- direct `/tmp` logs are create-exclusively opened under `noclobber`, and `tee`
  writes only the already-open descriptor rather than reopening a pathname;
- `SIGXFSZ` handling is local to `tee`, while the child command is unchanged;
- a logging failure returns `74` before otherwise propagating child status; and
- tests cover preexisting/symlink logs, child and logging statuses, missing
  freezes with zero formal side effects, invalid resume inputs, exact slot 15
  resume arguments, and the complete printed sixteen-slot order.

One first-round read-only reviewer accidentally invoked the no-argument
orchestrator while freezes were absent. It produced only a direct `/tmp`
traceback log and the expected zero-byte unbound lock; no aggregate root,
launch intent, child archive, first-party child import, or `SimulationApp`
occurred. Both reviewer-created empty artifacts were identity-checked and
removed. The fixed preflight now prevents that state, and all `_003` formal
paths were confirmed absent before the final review round.

Three fresh independent second-round reviewers returned `GO` against the same
final implementation and plan bytes:

| Review angle | Verdict | Output SHA-256 |
| --- | --- | --- |
| Architecture and contract coherence | `GO` | `055218b5205edf8612066635542fcd8460b30870b219be2bc3ccddf31488cedd` |
| Completeness and boundary cases | `GO` | `b539ba9c8b3bcc046beb108cff259c7b2ea067d39bce25bcd9bac4a07c503288` |
| Adversarial risk within the product boundary | `GO` | `ffe3d42588569898cdac8a7cc41c901797d54129de25617bd0dfc244c3467505` |

Reviewed launcher inputs included:

- formal orchestrator SHA-256:
  `78fee7cfe4a3108e31b5807abd9f8e1a0031d5cb7f74331016dce51d7671212a`;
- pipe wrapper SHA-256:
  `3007e68ce77ae71c80912d0bc512dd4982ff6b5711159f402692632b5f709d6a`;
- hardening plan SHA-256:
  `270efc7fe26f67f3cc620fbf88cdeca1783f4e5cec40eee59f96d2afb4995e44`;
- runtime-contract test SHA-256:
  `6ca91fade384d3ca7cd6743dea51fa47934942c12e44c2fef06dafb731d5a2c1`;
- replay runner SHA-256:
  `50038ffb33363096fcfb3e5d0dc582b982909a30860b878ba5a056aca5fff527`.

Final `_003` pre-freeze verification completed with:

- runtime contract: `352 passed`;
- related suite: `230 passed, 3 deselected` under the historical-authority
  rebuild exclusion documented above;
- wrapper/orchestrator focused tests: `3 passed`;
- three second-round independent reviews: `GO / GO / GO`;
- every `_003` aggregate, identity, pre-freeze, post-freeze, and lock path:
  ABSENT before identity/pre-freeze creation.

## Presentation-Layer Save Recovery And Formal `_004` Sign-Off

The terminal `_003` first cell reached `SimulationApp` but failed when its dirty
file-backed presentation layer had `permissionToSave=false`. `_003` was closed
with `STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE` and preserved. Its terminal
validation attestation was created before implementation changes and is a
protected `_004` input.

The `_004` repair changes only the presentation export lifecycle. It verifies
the locked source and exact presentation layer, restores only missing
presentation permissions, saves once, records the resulting file identity, and
relocks the presentation layer in one common-finally path. The source remains
locked and unchanged. The source, presentation, and static entry are then bound
into one three-file baseline that capture must verify before and after rendering.

Review was explicitly scoped to the sealed single-writer product model. Older
unrelated cell-root/staging hardening proposals and hostile same-UID concurrent
writers were not made `_004` launch requirements. After closing the actual
relock-contract, source-guard, baseline-handoff, and launcher-preflight findings,
three independent reviewers returned:

| Review angle | Verdict |
| --- | --- |
| Architecture and runtime lifecycle | `GO` |
| Completeness and failure contracts | `GO` |
| Adversarial risk within the product boundary | `GO` |

Final `_004` implementation hashes before freeze are:

- recovery plan: `2b0e63dcae1e38f74f9384f42ff7afbf00750d54261a416ce283f8848e56f4c2`;
- replay runner: `6ea1f0e75089f212b222a91f3c2ca82222175c3de4c1a0cae2af14959881a585`;
- formal orchestrator: `541acd0422b0fee5738813632de2726c5179d1d071697b7e9237e6ccb2901121`;
- Isaac smoke runner: `bb907135328498ef07883f7e488d7deae37b6895e0e216220c19a19b10773561`;
- runtime-contract tests: `b2508f3ac8858adb345cff61f6f3c1b0db0e83dd232e1cfcea6af97898395d92`.

Final verification completed with:

- runtime contract: `366 passed`;
- related suite: `230 passed, 3 deselected` under the documented historical
  authority-rebuild exclusion;
- focused `_004` recovery/FD/baseline/launcher tests: PASS;
- `py_compile`, `bash -n`, and `git diff --check`: PASS;
- Isaac Sim 4.1 reproducible smoke: save, relock, source preservation,
  presentation inode transition, three-file baseline, capture lock, and
  post-capture verification all PASS;
- Isaac smoke result SHA-256:
  `cf2e104b07c9999a01fbed00c0e757a2bb69f57bcb50f5cb4ebc1f89ffa955f0`;
- every `_004` aggregate, identity, pre-freeze, post-freeze, lock, and formal log
  path: ABSENT before identity/pre-freeze creation.

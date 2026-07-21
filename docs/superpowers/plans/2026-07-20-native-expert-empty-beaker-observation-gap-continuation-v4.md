# Native Expert Empty-Beaker Observation-Gap Continuation v4 Plan

## Decision Boundary

V1 through v3 remain frozen. In particular, v3 correctly classifies
`/World/Cube` and `/World/table/surface/mesh` as allowed composite support,
then stops at report 24 because both active pairs are omitted without explicit
`LOST`. Existing artifacts retain those meanings.

V4 changes only the observer's response to this known raw-report behavior. It
does not change the raw USD, source placement, table, Cube, robot, controller,
actions, physics, seed, materials, collision settings, or pass thresholds.

An omitted active support header is never transformed into `LOST`, `CURRENT`,
or success evidence. V4 records the omission as a per-transition observation
gap, continues the untouched native controller, and lets later raw evidence
determine whether a clean post-gap support/lift interval exists.

## Pinned V4 Contract

Add `config/diagnostic_level1_pour_native_empty_unbound_lift_v4.yaml` with an
exact registry entry:

- `schema_version: 4`
- `protocol_id: native_expert_empty_beaker_unbound_lift_v4`
- the exact ordered support collider paths `/World/Cube` and
  `/World/table/surface/mesh`
- `initial_support_activation_max_absent_reports: 10`
- `allow_active_support_pair_omission: true`

V4 retains v3's exact composite-support identity, table static-support audit,
close-time support-membership rule, production projection, and no-artificial-
coupling audit. It is explicit-only; V1, v2, and v3 have no fallback into the
new omission policy.

## Omission Semantics

The parser continues to reject all missing active pairs for V1 through v3. In
V4 only, it may retain a missing pair when all of these conditions hold:

1. the pair was active in the immediately preceding parser state;
2. the pair is one of the exact configured source/support pairs; and
3. no active non-support pair is missing in the same report.

For that report, the parser retains the pair in its active lifecycle set and
emits its canonical path in `unreported_active_pairs`. It does not synthesize a
header, point, anchor, event, current manifold, or `LOST` state. A later
`PERSIST` is accepted only because the real prior lifecycle remained active;

For every v4 sample, `unreported_active_pairs` is the configured-order,
canonical subset of `active_before - reported_pairs`, and
`support_observation_gap` is exactly whether that list is nonempty. The raw
`pairs` list and all aggregate point/anchor counts remain observed-only.
Logical lifecycle retention is never represented as a synthetic reported pair
or stale current manifold.

Consecutive omissions are allowed outside the decisive proof interval. A
retained pair may next emit real `PERSIST`, valid zero-data `LOST`, or
`PERSIST,LOST`; it may not emit `FOUND` while still retained. Any active pair
whose classification is not `SOURCE_SUPPORT` makes the entire report invalid,
even if an otherwise eligible support pair is also omitted.

The composite observer exposes the corresponding
`support_observation_gap` and exact pair paths in its decision and runtime
summary. It stays on the logical lifecycle path so native actions are not
delayed, retried, suppressed, or replaced. The gap itself earns no support or
loss credit.

The first event-4 report is pre-close: an already known omitted pair remains
known through the normally applied close action, and a previously unseen
support `FOUND` in that same report remains pre-close. A new support pair first
observed in a later report remains the existing v3 physical failure.

## No-Credit Physical Gate

V4 can pass only with an entirely observed decisive interval:

- no support observation gap in `[k_lift - stable_supported_steps, k_lift)`;
- no support observation gap in `[k_lift, k_loss]`;
- no support observation gap in `[k_rise, k_rise + retention_steps)`; and
- no support observation gap in `[k_pour - 1, k_accept]`, where `k_accept` is
  the first rotation sample accepted by the existing pour gate; and
- all existing v3 pair-level explicit-loss, no-recontact, topology, lift,
  retention, and pour gates.

Thus an early omitted report can be followed by a later, clean observed support
epoch and still permit evaluation. A gap in the actual lift proof interval is a
physical failure, not an audit failure, and cannot pass. Missing v4 gap fields
are audit failures. This is a continuation policy, not an inference policy.

## Parent Replay

The Isaac-free parent replays raw reports under the exact v4 protocol and
compares the full derived projection, including the observation-gap boolean and
ordered omitted support pairs. It rejects child tampering, a gap attributed to
an unauthorized pair, missing pair paths, or a child that omits a gap from its
summary. Both v4 fields are mandatory on every v4 runtime contact summary;
they remain absent from V1-V3 projections. Only parent-derived gap evidence
reaches the physical evaluator.

When a parser-accepted permitted gap occurs, the child appends its raw report
and exact parser projection to the hash-chained trace immediately, before live
geometry, topology, source-state, observer, boundary, or action work can fail.
If a later audit failure prevents normal transition-trace materialization, the
parent replays the raw parser prefix including that journal record. Completed
transitions remain the authority for full contact/observer projections; journal
records carry no inferred action or manifold evidence. This prevents an earlier
accepted gap from disappearing behind a later unrelated failure.

## Minimal File Scope

- `config/diagnostic_level1_pour_native_empty_unbound_lift_v4.yaml` (new)
- `tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py`
- `tests/test_native_expert_empty_beaker_unbound_lift_probe.py`
- this plan

No V1-V3 config, raw-scene asset, production config, controller, or prior
output is changed.

## Test-Driven Delivery

1. Add failing v4 pinning tests and prove v1-v3 remain exact/frozen.
2. Add failing parser tests: v1-v3 reject every active-pair omission; v4 emits
   the exact observed-only omission record, keeps only an eligible support
   pair logically active, handles partial/consecutive Cube/table omissions,
   and still rejects omitted `LEFT_SOURCE`, `RIGHT_SOURCE`, `SOURCE_OTHER`,
   `ROBOT_ENVIRONMENT`, and `OTHER` pairs atomically.
3. Add failing observer and parent replay tests for gap/recovery with raw
   `PERSIST`, zero-data `LOST`, and `PERSIST,LOST`; rejected retained-pair
   `FOUND`; event-4 timing; pair recontact; mandatory/reordered/tampered v4
   gap fields; and a later failure with a complete replayable gap journal.
4. Add failing physical-evaluator tests that inject a gap at the first and
   last index of each exact stable, lift/loss, retention, pre-pour, and
   accepted-rotation interval. They must be physical failures. Also permit a
   fully clean decisive interval after an earlier recovered gap.
5. Add v4 static-support and parent-audit tests proving the exact two-path
   baseline, reset map, boundary fingerprints, and mutation protections remain
   enforced.
6. Implement the smallest versioned parser, observer projection, runtime
   summary, parent replay, and evaluator changes required by those tests.
7. Run focused tests, bytecode compilation, and whitespace checks.
8. Run one fresh GPU-locked v4 control/instrumented pair under the existing
   external `/tmp/labutopia_gpu0.lock`, preserving create-only output paths.
   Record the resulting artifact byte counts and transition counts because v4
   may run substantially longer than v3. A pass remains conditional on real
   later raw evidence; any outcome is new v4 evidence.

## Stop Conditions

- Never infer support loss from omission.
- Never permit omission of an active non-support pair.
- Never alter native controller timing or source ownership because of an
  observer gap.
- Never give a gap credit in the stable, lift/loss, retention, or pour proof
  intervals.
- Do not change the scene or suppress raw contact evidence to manufacture a
  clean interval.

## Run Result

`outputs/native_expert_empty_beaker_unbound_lift_20260720_001/` used frozen
v4 config SHA-256 `cf37f652c062fc36f88a3f3927558c152e6e883aaa1a68776a`.
The parent completed with `parent_error: null` and
`NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO`.

- Control completed 864 transitions; `control/trace.jsonl` is 300980634 bytes.
- Instrumented completed 253 transitions and emitted 218 observation-gap
  journal records; `instrumented/trace.jsonl` is 89913603 bytes.
- The v4 parent gap-prefix replay was audit-valid with no replay failures.
- Instrumented then stopped on raw `contact_topology_authority_invalid` with
  `topology_inward_face_ambiguous`, not on an inferred support loss or a gap
  replay error.
- `report.json` is 1138604710 bytes. This run is no physical pass claim.

`outputs/native_expert_empty_beaker_unbound_lift_20260720_002/` reran the
same frozen config after moving journal emission to immediately follow parser
acceptance and before live geometry/topology work. It ran under the external
GPU lock with `CUDA_VISIBLE_DEVICES=0`, completed with `parent_error: null`,
and again returned `NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO` rather than a runtime
error.

- Control completed 864 transitions; `control/trace.jsonl` is 300980634 bytes.
- Instrumented completed transitions 0 through 252, then failed at raw contact
  index 253. Its trace contains 218 parser-authoritative gap journals for
  indices 24 through 241 and is 89170276 bytes.
- The final parent observation-gap prefix replay, completed-contact replay, and
  raw parser replay were all audit-valid with no replay failures.
- The instrumented child still stopped on
  `contact_topology_authority_invalid` / `topology_inward_face_ambiguous`; this
  is independent of v4 omission handling and is not a physical pass claim.
- `report.json` is 1137442451 bytes. Its `gpu_launched` metadata remains false
  despite the externally locked GPU invocation, so it is not GPU-provenance
  evidence.

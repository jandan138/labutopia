# Native Expert Empty-Beaker Support Observer v2 Plan

## Decision Boundary

The completed `v1` protocol remains frozen. In particular,
`native_expert_empty_beaker_unbound_lift_v1` continues to treat a missing
source/Cube entry in its first post-step report as
`support_initial_state_unknown`. Existing v1 artifacts are historical results
and will not be reinterpreted.

The new `v2` protocol addresses one narrowly observed observer behavior: the
instrumented child can emit a bounded prefix of source/Cube-empty reports
before it first emits the sealed source/Cube pair. Other valid report pairs are
not hidden by this rule. It does not infer that support existed during the
prefix, and it does not change the scene, controller, action sequence, physics
parameters, assets, or acceptance thresholds.

## Minimal File Scope

- `config/diagnostic_level1_pour_native_empty_unbound_lift_v2.yaml` (new)
- `tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py`
- `tests/test_native_expert_empty_beaker_unbound_lift_probe.py`
- this plan

The production projection, local scene, local Franka asset, source placement,
physics settings, controller, and no-artificial-coupling audit remain unchanged.

## Pinned v2 Contract

An exact protocol registry dispatches by both `schema_version` and
`protocol_id`. It has separate pinned entries for v1 and v2; there are no
defaults or fallback conversions. The CLI default remains the frozen v1 config,
and v2 requires an explicit `--config` path.

The v2 diagnostic is byte-pinned independently of v1. Its semantic changes
are:

- `schema_version: 2`
- `protocol_id: native_expert_empty_beaker_unbound_lift_v2`
- `initial_support_activation_max_absent_reports: 10`

Its `name` is also versioned metadata. All production-visible fields remain
byte-equivalent to the v1 production projection.

The new field has exact zero-based semantics: at most ten consecutive initial
reports may contain no source/Cube header. The next report must establish
current source/Cube support. A successful activation is allowed at transition
10 after absent reports at transitions 0 through 9. V1 has an implicit bound
of zero and therefore retains its existing first-report behavior.

The existing artifact envelope remains unchanged. The frozen config's
`protocol_id` and hash bind each result to v1 or v2, while the chained failure
record preserves the new v2 evidence. This keeps the change focused on observer
semantics rather than adding a second artifact format.

## Immutable Failure Evidence

Before any initial-support decision, the child must journal a canonical,
deep-copied observation containing:

- transition and world indices;
- source pre/post rigid-body state;
- raw full-contact report, including headers, contact data, and friction
  anchors;
- parsed contact sample and support summary when parsing succeeds;
- active protocol identity, policy, state/count before and after the report,
  classifications, and close-action context when it becomes available.

If the initial-support state machine rejects a report, the complete prefix is
attached as `AuditNoGo.evidence` to both the chained `audit_no_go` trace record
and the provisional report. The trace payload and provisional evidence must be
canonically identical. A pure versioned validator rejects malformed,
incomplete, non-finite, discontinuous, or policy-inconsistent evidence and
replays every raw report that was acquired. This evidence is diagnostic only;
it never supplies support credit.

Contact-report acquisition or parsing failures remain direct audit no-gos and
retain their available raw payload. They do not create synthetic observer
history, because there is no valid observation to replay.

## Bounded Support State Machine

The only exact pending record is a source/Cube support summary with:

- `present == false`, `current == false`, and `events == []`;
- zero support headers, contact points, friction anchors, and LOST headers.

For v2, let `c` be the number of accepted exact-absent reports before the
current report. When `c < 10`, an exact-absent report enters `UNOBSERVED` and
increments `c`. When `c == 10`, another absence is
`support_initial_activation_timeout`. A current support report may activate at
that point, so reports 0 through 9 may be absent and transition 10 may be the
first activation. The count never resets or reopens after `CURRENT` or `LOST`.

`UNOBSERVED` is not `CURRENT`, cannot satisfy a stable-support sample, cannot
establish a lift baseline, and cannot reappear after activation or loss. The
v1 state machine has a bound of zero and retains its existing immediate
`support_initial_state_unknown` outcome.

Activation is allowed only once by the canonical sealed `SOURCE_SUPPORT`
lifecycle `FOUND` or `PERSIST`, with one or more validated contact points and
zero or more friction anchors. Multiple same-event header fragments are
allowed; any mixed event sequence, LOST, zero-point current record, unknown
identity, malformed range, missing active pair, or support absence after the
bound remains `AUDIT_NO_GO`. A late initial `PERSIST` is accepted only for the
sealed source/Cube pair while the v2 activation window is open. Every other
later unseen `PERSIST` remains `AUDIT_NO_GO`.

The contact read for transition `k` is pre-controller/pre-action. Activation
in that same sample as the first valid native pick event-4 action is valid. If
the state is still `UNOBSERVED` when event-4 is emitted, the native action is
applied normally and recorded once, then the child emits
`support_activation_before_close_missing`; no action is delayed, retried,
suppressed, or replaced. Event 4 without exactly one valid applied action is
an audit failure. The first event-4 emission permanently closes the activation
window.

All classifications in the pending prefix through the first event-4 record
remain in the raw trace and are latched in the parent-derived observer
projection. Observed source/finger, `SOURCE_OTHER`, or `ROBOT_ENVIRONMENT`
entries in that window cannot be concealed or credited toward acceptance; they
produce a clean physical failure even if later reports are clean. Once support
is `CURRENT`, the existing lifecycle, 10-step stable-support, explicit LOST,
no-recontact, topology, and pour gates are unchanged.

Actor and collider identifiers must always resolve to sealed paths. PhysX may
emit material identifier `0`, which has no Sdf path; it is recorded as the
explicit `__physx_material_identifier_zero__` sentinel and is not used to make
any material or friction claim. Every nonzero material identifier remains
path-resolved.

## Parent Replay

The child and Isaac-free parent derive one pure observer-policy transition from
the same exact protocol registry entry. Parent raw-report replay must reproduce
each state, absent count, activation event, classification, and prefix physical
flag. It must compare that canonical observer projection against the child's
per-transition projection and reject any disagreement. It passes only
parent-derived data to the physical evaluator after proving the bounded
activation rules; no parent-side fallback may convert an absent report into
support.

For initial-support audit failures, the parent also validates and replays the
journaled failure prefix before reporting `AUDIT_NO_GO`. A missing, truncated,
or provisional/trace-mismatched prefix is itself an audit failure.

## Test-Driven Delivery

1. Add failing pure tests for exact v1/v2 pinning and an unchanged production
   projection.
2. Add failing lifecycle tests for zero, nine, ten, and eleven exact absent
   reports; sealed `FOUND` and late sealed `PERSIST` activation; zero-point
   current reports; mixed event sequences; unseen non-support `PERSIST`; and
   post-activation/continuation attempts to re-enter `UNOBSERVED`.
3. Add failing event-4 boundary tests for activation one report before, in the
   same report, and after event 4; repeated event 4; and event 4 without a
   valid applied action.
4. Add failing parent-level replay tests that tamper child state, absent count,
   activation event, classification, prefix physical flag, or recontact flag
   while raw reports remain unchanged.
5. Add failing physical-evaluator tests showing prefix source/finger,
   `SOURCE_OTHER`, and `ROBOT_ENVIRONMENT` contacts at every allowed prefix
   position remain visible and cannot pass.
6. Add failing evidence tests for valid initial-report failures, bound
   exhaustion, and event-4 exhaustion. They must verify a complete immutable
   journal prefix, trace/provisional equality, and parent rejection of missing
   or inconsistent evidence.
7. Implement the smallest shared protocol registry and observer-policy helpers,
   then thread them through the contact accumulator, runtime state machine,
   failure path, artifact validators, and parent replay.
8. Run the focused test module, bytecode compilation, and whitespace checks.
9. Run a fresh locked control/instrumented v2 pair only after the pure checks
   pass. Treat any result as new v2 evidence, never as a revision of v1.

## Observed v2 Result

`outputs/native_expert_empty_beaker_unbound_lift_20260719_017` is a completed
v2 control/instrumented attempt with final decision
`NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO` and no parent runtime error. The control
writer audit retained zero post-reset source pose/velocity, raw-property, and
software-gripper writes.

The instrumented compact contact history establishes the following before the
controller can perform a close action:

- reports 0 through 4 contain no source/Cube pair;
- report 5 contains `FOUND` for both source/Cube and
  source/table-surface;
- reports 6 through 23 contain `PERSIST` for both pairs; and
- report 24 is empty, with neither pair emitting an explicit `LOST` record.

The source/table-surface pair is `SOURCE_OTHER`, so it independently disallows
a physical pass. The later empty report cannot be treated as support loss under
this protocol because it lacks the required explicit zero-data `LOST` event.
No scene, controller, material, collision, placement, or threshold change is
authorized by this result.

## Stop Conditions

- Do not change USD, robot, production controller, placement, physics, action
  timing, materials, collision settings, or source pose/velocity ownership.
- Do not permit a missing report after the bounded prefix, or use an absence as
  proof of support loss.
- Do not permit an initial prefix to hide contact classifications or bypass the
  stable-support and explicit-loss gates.
- Do not use activation status to alter controller calls, action timing,
  retries, holds, resets, source ownership, or comparison tolerances.
- Do not overwrite existing output directories or rerun v1 to relabel it.

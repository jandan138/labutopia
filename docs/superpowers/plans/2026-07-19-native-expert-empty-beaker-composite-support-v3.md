# Native Expert Empty-Beaker Composite Support v3 Plan

## Decision Boundary

The completed v1 and v2 protocols remain frozen. Their artifacts retain their
original meanings: v1 permits only `/World/Cube` as support and v2 adds only
its bounded initial-observer rule. In particular, neither prior result is
relabelled as using the table surface.

V3 is a new, explicitly selected diagnostic protocol. It defines the normal
initial support set as these two exact leaf collider paths:

- `/World/Cube`
- `/World/table/surface/mesh`

This authorizes a beaker to rest on either or both of those static colliders
before lift. It does not authorize contact with any other environment object,
does not change the USD, source placement, robot, controller, physics, seed,
actions, material, collision settings, or pass thresholds, and does not add
any application-side source coupling.

An omitted active contact report remains insufficient evidence of separation.
V3 must not treat an absent header as `LOST`; it must observe an explicit,
zero-data `LOST` header for every support pair that was current during the
attempt. This preserves the actual lift proof while broadening only the
definition of permitted initial support.

## Pinned V3 Contract

Add `config/diagnostic_level1_pour_native_empty_unbound_lift_v3.yaml` with an
exact registry entry:

- `schema_version: 3`
- `protocol_id: native_expert_empty_beaker_unbound_lift_v3`
- `initial_support_activation_max_absent_reports: 10`
- `support_collider_paths` containing exactly the two paths above, in pinned
  order.

V3 uses the plural field only. V1 and v2 retain their existing singular
`support_collider_path`; there is no loose compatibility conversion or default
selection. The production-visible projection remains byte-equivalent to
`config/level1_pour.yaml`, and v3 still requires explicit `--config` use.

The protocol registry will bind the schema, ID, exact ordered support paths,
initial observer policy, and composite-support mode exactly. The existing
artifact envelope stays in use; the frozen config hash and protocol identity
distinguish v3 evidence.

## Composite Support Semantics

The contact identity resolver reads the support paths from the selected pinned
diagnostic. It must resolve the enabled support collider set to exactly the
configured two leaf paths, with no descendants, duplicates, extras, or overlap
with source/robot colliders. Parent replay independently verifies this exact
binding before parsing raw reports. A source contact against either configured
support is `SOURCE_SUPPORT`; the table surface must not be left in
`other_colliders` for v3. Robot/table remains `ROBOT_ENVIRONMENT`.

The contact accumulator retains the existing strict per-pair lifecycle rules,
including the rejection of an active pair omitted from a later report. It will
add a canonical support aggregate over every `SOURCE_SUPPORT` pair, preserving
per-pair event, current, point, anchor, and lost-header counts. The aggregate
is evidence, not a synthetic contact event.

The support observer will retain a canonical ordered record for each allowed
pair: its paths, `ever_current`, latest `current`, current manifold/anchor
counts, last event group, and an epoch-local terminal explicit-loss flag. A
new `FOUND` or accepted `PERSIST` clears that pair's terminal-loss flag. This
prevents an earlier loss from being reused after a recontact.

The support observer will track the latest state of every support pair that
becomes current:

1. Initial activation requires at least one current support pair with a
   nonempty contact manifold. Either Cube or table alone may activate v3; both
   may activate together.
2. While any seen support pair remains current, the aggregate state is
   `CURRENT`.
3. Aggregate `LOST` is reached only once every pair that was ever current has
   a terminal valid explicit `LOST` while the source is awake. Each such header
   must have zero contacts and zero friction anchors. A same-transition
   Cube/table loss is valid, but the proof remains pair-level rather than
   relying on a synthetic single event or one-header count.
4. A source recontact with either configured support after aggregate `LOST`
   remains a physical failure. Contacts with anything outside the two-path
   set remain forbidden source contacts.

The first applied native close action (pick event 4) closes support-pair
membership. A previously unseen Cube/table pair may be observed in the
pre-action report for that same transition, but a newly current allowed pair
after close is a physical failure and cannot earn support credit. This prevents
the table from becoming a late carrier during the grasp. A known pair may only
contribute to pass after its latest active epoch explicitly loses.

The runtime summary, parent replay projection, and physical evaluator will
consume that same pair-level aggregate. V3 evaluation must not use the v1/v2
scalar `support_header_count == 1` rule. A lift can pass only when all observed
allowed support pairs were explicitly lost before the rise threshold and
neither recontacts during retention or pour. No aggregate state may credit an
omitted pair as lost.

## Static-Support Audit

V3 will snapshot and validate a canonical two-key support map at baseline and
after reset. At each existing transition boundary it takes the same direct
snapshot but retains its canonical fingerprint, rather than duplicating the
large static USD payload in every trace record. Each exact leaf collider, its
rigid-owner/ancestor chain, and its world transform must remain static,
non-kinematic, nonmoving, collision-enabled, and free of relevant
force/joint/semantic relation mutations. Mutation-path partitioning is scoped
to the selected protocol's support paths, so table changes cannot be treated as
unrelated environment writes. The existing Cube-only audit and artifact fields
remain unchanged for v1/v2; v3 adds this map and boundary fingerprint under the
same trace/report envelope so the table cannot become an unverified carrier.

## Minimal File Scope

- `config/diagnostic_level1_pour_native_empty_unbound_lift_v3.yaml` (new)
- `tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py`
- `tests/test_native_expert_empty_beaker_unbound_lift_probe.py`
- this plan

No production config, USD, robot/controller/task implementation, asset, or
existing output directory is modified.

## Test-Driven Delivery

1. Add failing tests that v3 is exact-pinned, keeps the production projection,
   and cannot mutate v1/v2 semantics.
2. Add failing pure contact tests for exact/reordered/duplicate/extra support
   path rejection, table-surface as `SOURCE_SUPPORT` only under v3, robot/table
   as `ROBOT_ENVIRONMENT`, and an outside source collider as `SOURCE_OTHER`.
3. Add failing composite lifecycle tests for table-only late initial
   `PERSIST`, simultaneous Cube/table activation, one-pair loss while the
   other remains current, sequential and simultaneous losses, loss/recontact/
   loss epochs, asleep loss, post-loss table recontact, late unseen table
   support after close, and an omitted active pair.
4. Add failing parent replay and physical-evaluator tests proving that a trace
   cannot pass after only one support pair is lost, after a table recontact, or
   after tampering with a pair's paths, state, manifold counts, terminal loss,
   aggregate state, or resolution map.
5. Add failing static-support tests for a disabled collider, moving/dynamic or
   kinematic table ancestor, table property/transform mutation, missing/extra
   v3 support evidence, and a table mutation notice.
6. Implement the smallest registry, identity resolver, aggregate observer,
   static-support snapshot, runtime summary, parent replay, and evaluator
   changes needed for those tests.
7. Run the focused test module, bytecode compilation, and whitespace checks.
8. Run one fresh GPU-locked control/instrumented v3 pair. Treat its outcome as
   new v3 evidence; do not overwrite or reinterpret v1/v2 results.

## Stop Conditions

- Do not infer support loss from a missing report.
- Do not allow arbitrary table descendants, other furniture, or any other
  environment contact without a separately pinned experiment.
- Do not relax the explicit-loss, no-recontact, stable-support, topology,
  lift, retention, pour, source-ownership, or nonperturbation gates.
- Do not change the raw scene or controller to make the desired contact trace
  occur.

## Observed V3 Result

`outputs/native_expert_empty_beaker_unbound_lift_20260719_020` is the fresh
GPU-locked control/instrumented v3 attempt using frozen config hash
`ff1577ad35e7d30cbdd6bd8726e4386c39700e017bc5874c645824b0ac78b1b7`.
It completed without a parent runtime error and reached the expected semantic
classification:

- reports 0 through 4 contain no allowed support pair;
- report 5 emits `FOUND` for both source/Cube and
  source/table-surface, each classified `SOURCE_SUPPORT`;
- both pairs remain active through report 23; and
- report 24 is empty, with no explicit `LOST` header for either pair.

The final decision is `NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO` with
`contact_active_pair_missing`. V3 correctly does not convert the empty report
into loss or lift credit. The v3 static-support baseline and boundary
fingerprint audits pass for the control treatment. No scene, controller,
placement, material, collision, or threshold change was made.

## Review Resolutions

Three independent reviews identified the following necessary refinements,
which this revision incorporates:

- authorization must bind exact leaf colliders rather than recursively
  accepting arbitrary descendants;
- scalar support summaries cannot prove a composite loss, so v3 must preserve
  and replay a canonical per-pair aggregate;
- an allowed support contact first appearing after close cannot become a new
  accepted carrier;
- table support requires protocol-scoped static, mutation, and parent-replay
  evidence, not merely a changed classification.

The reviews also suggested broader GPU telemetry and historical-output fixture
work. Those are useful operational follow-ups but not required to implement
the authorized support-set semantic change; the fresh run will still use the
existing exclusive GPU lock and v1/v2 pure regression coverage.

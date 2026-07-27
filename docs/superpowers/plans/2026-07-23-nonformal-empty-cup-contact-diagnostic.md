# Non-Formal Empty-Cup Contact Diagnostic Plan

## Purpose

Create a fresh Isaac 4.1 diagnostic that observes real full PhysX contact for a
dynamic empty source cup before any product lift or pour claim. The diagnostic
is explicitly non-formal and cannot authorize G0, G1, G2, G3, G4, acceptance,
or delivery.

The 2026-06-09 expert video is historical visual evidence only. Its runtime,
config, action sequence, timing, poses, and result are not inputs to this
diagnostic.

## Constraints

- Use the formal Isaac 4.1 interpreter in a sealed, allowlisted child with a
  fresh effective-runtime v2 receipt.
- Generate a fresh action sequence and fresh run identity. Do not replay any
  historical or frozen action trace.
- The source remains dynamic. No attachment, source pose/velocity write,
  kinematic target, force injection, collision-filter shortcut, or source
  replacement is allowed.
- Full immediate PhysX reports are the only factual contact source. ContactSensor
  frames are optional diagnostic metadata and may not synthesize or replace
  report data.
- Any missing, stale, malformed, nonfinite, unresolved, or unexpected contact
  report is a terminal diagnostic outcome.
- Results use only `NON_FORMAL_DIAGNOSTIC_ONLY`, `OBSERVED`, `PHYSICAL_FAIL`,
  `AUDIT_NO_GO`, or `RUNTIME_BLOCKED`; never `PASS`.

## Boundary

- Create a new standalone diagnostic runner and focused tests.
- Reuse only verified low-level concepts from
  `tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py`:
  report-only session-layer setup, strict full-report parsing, source mutation
  auditing, and control-versus-instrumented comparison.
- Do not modify `main.py`, production fluid/evaluation modules, Franka sensor
  code, formal configs, or formal evidence artifacts.

## Sequence

1. Add pure failing tests for strict direct-report normalization and diagnostics:
   valid bilateral contact; unilateral contact; stale/missing frame; every
   fragment's ownership; nonfinite data; lifecycle/range inconsistencies; and
   optional invalid ContactSensor metadata.
2. Implement a small diagnostic-only report parser and result classifier. It
   must preserve raw evidence and fail closed rather than infer contact.
3. Implement an isolated sealed-child runner that installs contact reporting
   through an anonymous session layer, proves setup does not advance physics,
   and audits source state and mutation paths from bootstrap onward.
4. Execute a fresh close-only dynamic empty-cup run. It terminates before lift
   and records whether both finger pads have complete, same-step direct PhysX
   contact with the source external shell.
5. If and only if the close-only diagnostic is `OBSERVED`, write and review a
   separate non-formal short-lift diagnostic. It repeats acquisition in a fresh
   child and adds source/gripper motion and retention observations without
   promoting the result to a formal grasp claim.

## Review Outcomes

- Architecture review: isolate this work from the production loop and reuse the
  standalone probe's broader writer audit; the current production reporter has
  known normalization and writer-audit blind spots.
- Completeness review: ContactSensor invalidity must not be treated as no
  contact. Direct reports still need every-fragment identity, finite-value, and
  lifecycle validation.
- Risk review: the historical Isaac 5.1 video is non-comparable. The new probe
  needs fresh source/config/USD closure, sanitized environment, runtime receipt,
  logs, and artifact hashes, while remaining explicitly non-formal.

## Executed Non-Formal Results

- `artifacts/runs/isaac41-effective-runtime-v2-20260723-024/` attested the
  reviewed Isaac 4.1 effective runtime v2 tuple with `MATCH` before the
  diagnostics below. The diagnostic runner records this only as a separate
  non-formal preflight receipt, not as same-child formal-task evidence.
- `artifacts/runs/nonformal-pbd-direct-trace-smoke-20260723-033/` exercised
  the current dynamic source for 124 physics steps. Direct reports captured the
  source/Cube support pair; the source was dynamic, writer-audit coverage was
  complete with zero writes, and no lift was applied. The original 120-step
  pre-roll remained physically unsettled, so this was not an acquisition run.
- `artifacts/runs/nonformal-pbd-g2-rest-smoke-20260723-032/` used the existing
  rest-offset-zero 600 Hz diagnostic candidate under the exact allowlisted
  library path. After 620 physics steps, source linear speed was below
  `0.00016 m/s`, angular speed below `0.002 rad/s`, and all audited source
  writers remained unused. It exhausted its one-control-step bound before any
  finger/source contact attempt.
- `artifacts/runs/nonformal-pbd-g2-close-only-20260723-034/` stopped at
  control step 51 before close or lift. Its hashed full-report trace records a
  right-finger collision with static `/World/Cube`, not with the source:
  `/World/Franka/panda_rightfinger/geometry/panda_rightfinger` to
  `/World/Cube` at physics step 1617. The result is a physical
  `robot_environment_contact` failure; no source writer, attachment, source
  pose write, or lift action occurred.

The side-body path remains blocked. The prior cooked-collider feasibility
review in `2026-07-16-level1-pour-real-contact-grasp.md` already records that
the required swept-clearance prerequisite is NO-GO. Do not alter grasp geometry
or retry this route until a new independent clearance review authorizes a
specific physical correction.

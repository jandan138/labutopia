# Real Beaker Isosurface Graph-Owned Final Probe Plan

## Goal

Align the static presentation probe with the proven particle-graph ownership
sequence used by the accepted full-scene runner, then execute the same single
`1/600 s` derived-presentation initialization step and strict three-camera
capture.

The predecessor single-step probe is terminally invalid because its discarded
and final `context` captures were white. It skipped the full runner's legacy
sampler-removal/synchronization barrier and strict 600 Hz PhysicsScene
configuration before authoring the new particle system. The pinned source is
already isolated, so this is an ordering-parity probe rather than a claim that
an active legacy graph caused the white frames. It does not change particles,
colliders, material, isosurface parameters, cameras, render settings, warmup
count, or step count.

## Scope

Modify only:

- `tools/labutopia_fluid/run_real_beaker_accepted_final_isosurface_probe.py`
- `tests/test_real_beaker_accepted_final_isosurface_probe.py`

Use the new output identity:

- `real_beaker_isosurface_graph_owned_final_probe_20260713`

Do not add a parameter switch or duplicate runner. The predecessor output
directories remain immutable failure evidence.

## Runtime Order

1. Validate the same accepted authority positions, source USD, ClearWater MDL,
   physical offsets, and presentation contract.
2. Open the disposable wrapper with the timeline stopped. Register the PhysX
   step-event counter before any graph synchronization.
3. Reuse the full runner's ownership sequence:
   `remove_legacy_particle_sampling_api`, `_deactivate_original_fluid_prims`,
   and `synchronize_legacy_particle_graph` with the same fixed five stopped
   updates. Require sampler API absent, empty legacy particle-system
   relationships, the old system disabled, ownership isolation verified,
   timeline stopped, and physics step-event count 0. Record whether
   synchronization was required; `false` is the expected valid result for the
   already-isolated pinned source.
4. Reuse `_configure_physics_scene_for_pbd` with `integration_dt=1/600` and
   `strict_mode=True`. Require GPU dynamics, GPU broadphase, TGS, and authored
   `timeStepsPerSecond=600` with strict readback verification.
5. Author ClearWater, lighting, and the runtime particles exactly as before.
   The helper's second deactivation pass must report no remaining graph change.
   Require the accepted ordered positions and 4096 finite zero velocities before
   attach.
6. Attach `StrictPhysicsStepper(1/600, 1/600, 1)`, execute `stepper.step()` once,
   and retain the existing derived-presentation point-center containment and
   lifecycle gates. No further physics step is allowed.
7. Retain the existing bridge, material, scoped log, source integrity, one
   predeclared discarded `context` flat-frame allowance, and one uncaught strict
   three-camera final capture. Establish the non-runtime scene hash only after
   expected wrapper setup edits are complete, then require it to remain stable.
8. Write an operation ledger with this exact order: register step counter,
   remove sampler API, first deactivation, five-update synchronization, strict
   600 Hz scene configuration, runtime authoring, second deactivation summary,
   attach, and one step. Also record the discarded and final capture attempts.
9. Write the graph-isolation and PhysicsScene contracts into the manifest. Keep
   the existing claim boundary: accepted frame-600 positions are parent
   authority; the zero-velocity single-step result is presentation-only, not
   frame 601 and not new physics authority.

## TDD Order

1. Add failing tests for the new probe/output/status identity.
2. Add failing pure-contract tests for legacy sampler removal, ownership
   isolation, exactly five synchronization updates, zero step events through
   synchronization, and strict 600 Hz PhysicsScene readback. An already-isolated
   source with `synchronization_required=false` must pass.
3. Add a failing test that rejects any graph change reported by the helper's
   second deactivation pass, plus an exact operation-order test.
4. Implement the minimum runtime sequence using the existing full-runner
   helpers. Run focused and related tests.
5. Execute one formal Isaac run. Do not add steps, warmups, retries, materials,
   or another candidate if the strict final capture fails.

## Terminal Outcomes

- `CAPTURED_GRAPH_OWNED_ISOSURFACE_PENDING_VISUAL_REVIEW`: graph ownership,
  strict scene timing, one derived initialization step, presentation-state
  point-center containment, and all final capture gates pass.
- `INVALID_GRAPH_OWNED_ISOSURFACE_PROBE`: any gate fails. A final white frame is
  terminal evidence that this Isaac Sim 4.1 runtime-isosurface delivery path is
  not usable for the static real-scene capture under the fixed contract.

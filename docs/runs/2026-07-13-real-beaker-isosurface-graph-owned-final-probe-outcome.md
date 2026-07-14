# Real Beaker Graph-Owned Isosurface Final Probe Outcome

## Decision

Stop adding initialization retries or parameter candidates to the Isaac Sim 4.1
runtime-isosurface path for this fixed real-beaker presentation contract.

The final ordering-parity probe remained white after the full runner's legacy
graph barrier and strict PhysicsScene setup were restored. The next product
track is a derived surface mesh built from accepted particle readback, with the
accepted particle simulation retained as the physics authority.

## Formal Evidence

- Output: `docs/labutopia_lab_poc/evidence_manifests/real_beaker_isosurface_graph_owned_final_probe_20260713`
- Manifest SHA-256: `5c40a355564aaefada5bf83a8002a08b1d89f75ddd3e5219975af55544a104fa`
- Status: `INVALID_GRAPH_OWNED_ISOSURFACE_PROBE`
- Discarded context capture: mean `254.98177919238682`, standard deviation `0.14312672846249433`
- Strict final context capture: mean `254.9796965020576`, standard deviation `0.1520498160871183`
- PNG outputs: `0`

The manifest verifies:

- the pinned source was already isolated (`synchronization_required=false`);
- five stopped synchronization updates executed with zero physics steps;
- GPU dynamics, GPU broadphase, TGS, and 600 Hz strict timestep readback passed;
- exactly one `1/600 s` simulate/fetch pair executed;
- all render warmups and both capture attempts remained at one physics step;
- ClearWater MDL compilation and the scoped fatal/nonfinite log scan passed;
- non-runtime scene points and source hashes remained unchanged; and
- Replicator cleanup and the terminal failure evidence chain completed.

## Claim Boundary

This result rejects only the fixed Isaac Sim 4.1 runtime-isosurface delivery
path tested here. It does not invalidate the accepted 4096-particle static-hold
authority, and it does not claim that other Isaac Sim releases, other container
scales, or other liquid representations cannot work.

## Next Product Track

Build a presentation-only water surface from accepted particle positions:

1. generate a deterministic surface mesh outside the PhysX runtime-isosurface
   bridge;
2. bind the pinned ClearWater material;
3. place the mesh in the real tabletop USD without changing particle physics;
4. validate the static accepted frame first, then extend the same conversion to
   trajectory frames; and
5. use independent visual review only after real RGB captures exist.

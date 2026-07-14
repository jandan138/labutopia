# InternData Derived-Surface Replay Plan Reviews

## Reviewers

- Architecture: agent `Pascal` (`019f5adb-b233-74c3-a365-1415e8fcb99e`).
- Completeness and edge cases: agent `Hume`
  (`019f5d17-74dc-7fd0-9e06-4cfbce2374bf`).
- Risk, evidence, and visual quality: agent `Lagrange`
  (`019f5d17-8171-78c1-85e2-ebf79a704a3d`).

All three reviewers independently inspected the draft and made no file changes.
All three returned `REVISE`; the implementation direction itself was retained.

## Accepted Corrections

1. Correct the malformed authored-scene digest and pin the accepted runtime
   summary as the source of the inherited top-level physics verdict.
2. Name and disable every existing visual liquid path: physical particles,
   offline visual particles, legacy points, and old/generated isosurface state.
3. Keep reconstructed vertices in world space under an identity mesh transform
   while applying trace matrices only to the source beaker.
4. Replace approximate reconstruction language with an exact numeric contract:
   lattice anchor, spacing, padding, dtype, splat order, Gaussian parameters,
   density level, marching-cubes options, and pinned dependency versions.
5. Remove component deletion. Every reconstructed component is retained, while
   the no-leak claim remains inherited from the hash-pinned physics trace.
6. Add real closed-volume checks: low boundary density, two incident faces per
   undirected edge, valid/nondegenerate triangles, outward winding, finite
   normals, and positive component volume.
7. Define cache determinism over canonical uncompressed arrays and bind each
   cache entry to input, contract, dependency, and implementation hashes.
8. Make external replay semantics explicit: the cache plus runner is the
   animation authority; the saved USD is only a final-state snapshot.
9. Add strict malformed-trace/cache tests, exact 70-frame selection and decode
   checks, and atomic USD topology/extent updates.
10. Add an eight-frame `190..260` temporal gate beside five pinned stills so
    topology popping is reviewed before the full 70-frame render.
11. State that the delivered evidence is a 5x-speed decimated replay.
12. Pin `scikit-image==0.25.2` in an external Python 3.10 reconstruction
    environment; Isaac Sim remains a cache-only consumer.

## Scope Decisions

- A suggestion to add time-sampled variable-topology USD was rejected for this
  iteration. It expands the delivery surface without improving the required
  video. The static USD snapshot and external cache/runner contract are now
  explicit.
- Broad malformed-input coverage is implemented as focused pure tests and one
  strict loader, not as recovery or fallback logic. Bad evidence fails fast.
- Material evidence was conflicting: the prior terminal outcome requested a
  geometry-lane test, while all three previously tested materials had failed on
  the old display mesh. The revised gate therefore starts with the exact public
  InternData PreviewSurface contract, has no fallback, and permits at most one
  separately hash-bound presentation contract after concrete RGB review.
- The existing 2,883-line physics runner remains read-only. The new replay
  runner owns a small local capture loop and does not import its private runtime
  machinery.

## Final Review State

The revised plan keeps one physics-preserving route and one fixed initial
reconstruction contract. It adds evidence needed to reject holes, stale frames,
old point visibility, and temporal popping without adding a candidate matrix or
automatic retry system. Implementation may proceed test-first.

## Implementation Review Rounds

The initial plan review was followed by independent implementation reviews from
Feynman (`019f5f4b-689e-7c50-bbe4-8340dda823a5`), Archimedes
(`019f5f4b-c611-70a3-9782-90fe5b055509`), and Lovelace
(`019f5f4b-fc6e-7d43-adf7-06a81d09e050`). These reviews remained read-only.

### Visual gate revisions

1. V1, with sigma `1.25` and the white reference material, failed because the
   source read as foam and the stream as a gray bead chain.
2. V2, with sigma `1.60`, improved the body but still failed the connected-stream
   criterion.
3. V3 added guarded Taubin smoothing, the accepted cyan material, and the final
   close-up camera. The action became readable, but the stream still looked like
   stacked blobs.
4. Reviewers compared temporal density accumulation, a new dedicated mesher,
   and current-frame anisotropic density closing. Temporal accumulation was
   rejected because the trace has no stable particle identities and a clipped
   below-rim sweep did not bridge the measured gap. Adding another mesher was
   not justified before testing a deterministic current-frame correction. The
   selected V4 contract therefore uses one gravity-Z ellipsoidal grayscale
   closing with radii `[3, 3, 8]` voxels.

V4 passed its technical gate: steps 200 through 250 each had one connected
component; nonzero support bounds never expanded; maximum volume growth versus
V3 was 8.474%; and minimum target-wall clearance was 0.964 mm. A repeated build
produced identical geometry, archive bytes, and diagnostics.

### Full-cache topology review

The first full build exposed two triangles at step 170 that became zero-area
only after the delivered vertices were converted to `float32`. All three
reviewers selected exact adjacent, bit-identical edge contraction. Epsilon
welding, component filtering, and broad mesh repair were rejected because they
could hide a real droplet or alter the evidence shape. The same condition later
appeared at step 450; each affected frame welded one exact duplicate vertex and
removed two collapsed faces. A follow-up review required the cleanup volume gate
to compare `float32` input against `float32` output, while retaining the
`float64` to `float32` drift as a diagnostic only. All 70 frames then passed the
closed-manifold, component, Euler, AABB, winding, and volume checks.

### Final visual review

An independent context-free reviewer (`019f60a5-ecf8-7e92-9fe0-6e5edaec1561`)
reviewed the close-up timeline, dense-pour sequence, and context timeline. The
overall verdict was high-confidence `WARN`, with no blocking issue: the main
stream is coherent, accumulation stays in the receiver, and no definite table
spill or wall penetration is visible. Remaining presentation differences are
surface faceting and a bright pre-existing object at the receiver bottom; the
latter is scene content, not reconstructed liquid.

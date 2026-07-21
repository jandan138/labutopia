# Frozen V6 HD Camera Retake Plan

## Trigger And Decision Boundary

Fresh independent visual review of the completed `_011` HD derivative returned
`WARN` for both camera streams. The rejection banner is readable and the
terminal spill is visible, but the vessel rims, grasp contact, and pour path
are too small or occluded for a product-facing explanation of the unsafe
outcome.

The retake changes presentation only. It must not modify the frozen source
trace, action schedule, source USD cameras, PBD scene, simulation timing,
model-camera inputs, contact/latch behavior, or forced
`REJECTED_UNSAFE_VISUAL_ONLY` decision. Existing output directories, including
`_011`, remain immutable evidence.

## Pinned Retake Contract

Create a new HD presentation schema version for a create-only `_012` run. The
source camera identity contract remains exact:

- `camera_1` source is `/World/InternDataParityCamera` and its HD clone remains
  an unmodified source-camera copy apart from the existing 16:9 aperture
  adaptation;
- `camera_2` source remains `/World/InternDataParityCloseupCamera`, but its HD
  clone receives this presentation-only override after cloning:
  - eye: `[0.1645, -0.6469, 1.0200]`;
  - target: `[0.2785233518810611, -0.22147663301350906, 0.8899941121566101]`;
  - up: `[0.0, 0.0, 1.0]`;
  - focal length: `22.0`;
  - vertical aperture: `16.0` and horizontal aperture: `28.444444444444443`
    to retain the 16:9 capture aspect.

This established receiver-safe three-quarter azimuth is closer than the
copied source camera and is intended to keep both vessel rims, the gripper,
pour path, and spill area visible without changing simulation state. The top
72 pixels remain reserved for the rejection banner; the retake must not place
the task interaction only behind that overlay.

The report must name the source prim separately from the presentation clone
and include an exact authored-camera receipt: mode (`source_copy` or
`presentation_override`), clone path, eye, target, up, focal length, aperture,
and transform/optics readback. Parent validation must fail closed if the
camera-2 receipt differs from the pinned retake override or if camera-1 is not
a source-copy receipt.

## Implementation Steps

1. Add failing Isaac-free and USD-stage tests before implementation.
   - Pin the schema-v2 contract, unchanged source-camera identities, and the
     exact camera-2 presentation override.
   - Verify that the HD clone authoring leaves camera-1's pose/optics as the
     existing copy behavior and authors camera-2's exact look-at transform,
     22 mm focal length, and 16:9 aperture.
   - Reject malformed/unknown/incomplete override definitions and report
     receipts that disagree with the pinned contract.
   - Preserve the 433-frame source/observation binding and no-physics/no-
     timeline-advance capture requirements.
2. Extend `utils/presentation_video.py` with a narrowly scoped optional
   presentation-clone override path. It must operate only on clone prims after
   source copying, author a deterministic `UsdGeom.Camera` transform/optics,
   and return a readback receipt. The generic no-override behavior remains
   byte-for-byte equivalent in meaning for existing callers.
3. Thread the pinned override only from the frozen-v6 HD runner into the
   recorder builder. Attach the clone receipts to the raw manifest and final
   `hd_presentation` report, then parent-validate them along with the current
   codec, banner, source binding, and rejection checks.
4. Run focused tests, `py_compile`, and `git diff --check`. Run one fresh
   GPU-locked, create-only `--capture-hd-presentation` replay into `_012`.
5. Decode representative initial, contact/failure, lift, pour, and terminal
   frames from both final H.264 streams. Send only those images and visual
   expectations to a clean-room visual reviewer.

## Acceptance And Stop Conditions

- `camera_2` must receive a visual `PASS` for a useful close inspection view:
  both vessel rims and the liquid/pour failure must be identifiable during the
  relevant motion, with no task-breaking gripper occlusion or unreadable
  banner.
- `camera_1` remains a contextual overview. A `WARN` is acceptable only when
  its report and delivery wording identify it as supporting context, not the
  primary inspection view; a `FAIL` blocks the run.
- Any changed frozen source trace, source-camera transform, world time/step,
  Omniverse timeline, source-frame mapping, encoder property, banner, or
  rejection field blocks release.
- If the new closeup remains `WARN` or `FAIL`, do not present `_012` as the
  final product-facing HD artifact. Record its review and perform another
  explicitly planned retake instead.

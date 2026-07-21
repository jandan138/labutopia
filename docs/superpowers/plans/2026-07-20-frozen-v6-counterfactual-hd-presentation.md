# Frozen V6 Counterfactual HD Presentation Plan

## Decision Boundary

The existing `004` result remains immutable evidence: it is a completed,
rejected 512 x 256 model-camera replay. This work creates a new, separately
audited HD derivative of the same frozen source trace. It does not change the
source trace, action representation adapter, PBD settings, source ownership,
controller prohibition, acceptance decision, or any prior output.

The HD videos are diagnostic evidence only. Every final presentation video
must visibly state `REJECTED UNSAFE VISUAL-ONLY` and explain that it is not
grasp, transfer, or success evidence. The report must set matching top-level
and terminal `success=false`, `expert_episode_accepted=false`,
`collector_write_allowed=false`, and `ebench_finalize_allowed=false` fields.

## Pinned HD Contract

Add an opt-in `--capture-hd-presentation` runner mode rather than changing the
default v1 execution path. The mode is pinned in code and included in the
parent-validated report:

- source cameras: `camera_1` at `/World/InternDataParityCamera` and
  `camera_2` at `/World/InternDataParityCloseupCamera`;
- presentation resolution: 1280 x 720, 30 fps, preserving vertical FOV;
- sample schedule: the existing initial t=0 frame plus every odd source
  transition, exactly matching the 433-entry model-video frame map;
- capture policy: `viewport_same_observation_no_physics_step_v1`;
- visible display status: a top banner containing `REJECTED - UNSAFE
  VISUAL-ONLY` and `DISTINCT PBD COUNTERFACTUAL | NOT GRASP, TRANSFER, OR
  SUCCESS EVIDENCE`;
- final encoding: H.264, yuv420p, 30 fps, faststart, with the same 433 decoded
  frame positions as the recorded raw presentation video.

The source cameras remain 256 x 256 model inputs. The HD prims are copied from
those static source-camera definitions once after task initialization, then
rendered through Viewport at each already-observed state. They do not replace
model inputs or advance the World physics time or step count.

HD mode starts a 1280 x 720 headless `SimulationApp`, enables
`omni.kit.viewport.window`, creates and retains a named 1280 x 720 viewport
window with `create_viewport_window`, and verifies that window's API is active
before creating the recorder. It destroys that window only after recorder
closure. The initial Viewport capture occurs before applying any source action.
An absent Viewport, capture timeout, writer failure, World or Omniverse timeline
time/step/play-state change, or encoder failure is a runtime error, never a
partial rejected result.

## HD Evidence Schema

The normal three-artifact schema remains exact when the flag is absent. In HD
mode, the parent expects the normal artifacts plus exactly these output-local,
create-only artifacts:

- raw recorder manifest and recorder frame JSONL under `presentation_raw/`;
- an HD binding map under `presentation_hd/` with one ordered row for each
  frozen model-video frame;
- the two raw recorder MP4s under `presentation_raw/`;
- two final watermark-bearing H.264 MP4s under `presentation_hd/`.

The report has a versioned `hd_presentation` object. It binds the single
rejected recorder attempt, both fixed source cameras, all 433 frame indices,
source transition indices, observation indices, frame identities, and
presentation synchronization receipts to the same-run model frame map and
observation trace. It also records the fixed encoder/filter command, font hash,
raw/final artifact keys and hashes, source/capture dimensions, decoded metadata,
and the `CUDA_VISIBLE_DEVICES` value. Raw MP4s are explicitly marked internal,
unwatermarked encoder inputs and are not release media.

The parent validates all report paths after resolving them beneath the output
directory, rejects symlinks and duplicate paths, validates the raw manifest and
JSONL against the binding map, and independently decodes both raw files and
both final files. Every stream must be the expected camera, 1280 x 720, 30/1
fps, and exactly 433 frames; each binding row carries its raw per-camera frame
ordinal. The final streams must additionally be one-stream H.264, yuv420p
videos. It validates faststart atom ordering, the fixed banner command and a
decoded banner-color sample. Each synchronization receipt carries equal
before/after World time and step plus Omniverse timeline time and play state.
Frame equality across lossy H.264 encoding means exact ordering/count and
source binding, not pixel equality.

Only `capture_complete`, `encoding_complete`, and `evidence_valid` permit the
full HD artifact schema and a completed `REJECTED_UNSAFE_VISUAL_ONLY` result.
Any other requested-HD outcome writes a runtime-error report with all denial
fields false and no valid final-media object. It may leave create-only partial
files in the failed output directory, but those files are explicitly untrusted,
are not report artifacts, and are never release media.

## Implementation Scope

- `tools/labutopia_fluid/run_frozen_v6_empty_trajectory_actual_fluid_counterfactual.py`
  - add the opt-in argument and forward it to the child process;
  - initialize the existing `build_isaac_presentation_video_recorder` only in
    HD mode after the frozen task and fluid loop are initialized; use a 720p
    headless application configuration, create a named active Viewport window,
    retain it through closure, and fail closed on the initial capture;
  - capture the same initial/odd-transition samples as the existing frame map;
  - write raw presentation files under `presentation_raw/`, release the single
    rejected attempt, then create two banner-bearing H.264 final videos under
    `presentation_hd/` with a fixed local font/filter and create-only ffmpeg
    command;
  - add a sidecar binding map, hashes, codec metadata, raw-to-final encoding
    receipts, and the frame-to-observation binding to the child report;
  - parent-validate the recorder manifest, per-frame synchronization records,
    output hashes, exact source-frame bindings, expected codec/properties,
    faststart/banner evidence, and the forced rejection boundary.
- `tests/test_frozen_v6_empty_trajectory_actual_fluid_counterfactual.py`
  - add failing tests for the pinned HD contract, child-command forwarding,
    rejection watermark encoding command, and fail-closed presentation evidence
    validation.
- `docs/superpowers/plans/2026-07-20-frozen-v6-counterfactual-hd-presentation.md`
  - retain the plan, review conclusions, and fresh-run outcome.

No scene asset, production configuration, controller, model camera contract,
or existing output is modified. `utils/presentation_video.py` is reused without
changing its general behavior unless review finds a concrete integration gap.

## Test-Driven Delivery

1. Add Isaac-free failing tests for the HD contract and its validation failures:
   opt-in child forwarding, default-schema preservation, fixed banner encoder
   command, exact 433-row binding, reordered/duplicated/cross-attempt rows,
   malformed paths/manifest, incomplete capture, swapped cameras, truncated or
   duplicate raw frames, bad codec/pixel format/resolution/fps/frame
   count/faststart evidence, and any World/timeline synchronization delta.
2. Implement the smallest opt-in capture/encoding/reporting path needed for
   those tests.
3. Run the focused test module, `py_compile`, and `git diff --check`.
4. Run a fresh create-only GPU-locked replay with
   `--capture-hd-presentation` and `CUDA_VISIBLE_DEVICES=0`.
5. Validate the parent report, decoded H.264 metadata, frame counts, hashes,
   source-frame bindings, top-level/terminal forced rejection status, and
   banner visibility.
6. Extract representative frames from both final videos and perform a
   clean-room visual review focused on close-camera framing, legibility,
   liquid visibility, artifacts, and rejection labeling. Review initial,
   contact/failure, lift, pour, terminal, and fullscreen-resolution frames.
   An unreadable, cropped, or absent rejection banner blocks final-video,
   thumbnail, poster, or still release.

## Stop Conditions

- Do not capture a frame unless its existing model-frame counterpart is in the
  frozen 30 Hz schedule.
- Do not advance physics or timeline time while switching/capturing a
  presentation camera.
- Do not emit an HD artifact without an auditable frame binding and decoder
  validation.
- Do not leave an incomplete capture or unwatermarked raw file classified as
  final visual evidence.
- Do not hide or weaken the rejection status in the final videos or report.
- Do not alter the source trace, PBD scene, actions, or acceptance criteria to
  improve the visual outcome.

## Plan Review

Three independent reviews covered architecture, completeness, and runtime/
evidence risk. The revision adopts their material findings: active-Viewport
preflight through the first captured frame, exact HD-only artifact schema,
one-to-one sidecar frame bindings, safe output-tree validation, fixed rejection
banner and H.264 validation, explicit partial-run failure semantics, and
top-level denial fields. It intentionally does not modify the shared recorder
or the normal v2 configuration: the frozen runner owns the frozen-specific
watermark, encoding, and evidence contract. The recorder gains only the
concrete missing synchronization receipt fields for Omniverse timeline
before/after checks; its general capture behavior remains unchanged.

# liquid_0812 GUI-equivalence investigation outcome

Date: 2026-08-13

## Outcome

The severe source-beaker flash in the previously published Isaac 4.1 RTX
diagnostic is primarily a presentation-schedule artifact, not evidence that the
rigid body oscillates between two poses. The frozen-state diagnostic advanced
physics to state 448 without rendering, then asked RTX to render the large
state discontinuity repeatedly. Native viewport capture needed roughly three
to five updates before that state converged.

The corrected diagnostic renders every physics transition. In a full 953-state
run, the retained video contains one newly completed RTX frame for every 30 Hz
physics state. The source USD world matrix and the expected PhysX-derived world
matrix agree exactly at capture time (maximum absolute matrix-element error
`0.0`), and pose tracking passes:

- maximum packet-to-PhysX position error: `1.228781230931777e-07 m`;
- maximum packet-to-PhysX rotation error: `2.4567327398802266e-05 deg`;
- maximum PhysX-to-USD position error: `0.0 m`;
- maximum mesh-relation position error: `0.0 m`.

The busy-GPU exploratory run completed 953 physics states and 953 native
viewport captures in `21.25 s` (`44.85` completed frames/s). This number is not
a formal performance claim because the run used the CPU viewport-byte
reference capture path and retained full video frames. Its purpose is visual
synchronization diagnosis.

## Pose-author A/B result

- `physx-kinematic-target + session-mirror`: visible USD and PhysX poses agree.
- `physx-kinematic-target + physx-only`: the visible USD pose can remain about
  `0.126 m` stale in this tensor-stepping path, so it is not an acceptable
  presentation route.
- `legacy-usd-teleport`: still shows several convergence frames when hundreds
  of physics states are skipped before the first render. Removing the session
  mirror therefore does not by itself solve the frozen-state artifact.

Keep `session-mirror` as the single explicit render publication path for the
kinematic driver. The new `pose_publish_mode` switch is diagnostic and must not
silently change the formal default.

## Why the colleague GUI does not show the same flash

The supplied GUI reference is Isaac Sim Full 6.0.0 on Windows with driver
573.42. It continuously updates the viewport while the object moves. The DSW
baseline is Isaac 4.1 on Linux with driver 570.153.02. The old comparison mixed
simulator version, OS/driver, pose authoring, and presentation cadence.

The corrected 4.1 lane now matches the important cadence property: RTX sees
each small pose transition. It does not claim full 6.0 GUI parity.

## Main-viewport boundary

The runner now has an explicit `main-viewport` lane that uses Isaac's active
viewport rather than creating an offscreen viewport. On this DSW it cannot be
executed: `SimulationApp(headless=False)` fails before runtime attestation with
`Failed to acquire IWindowing interface` because there is no X/desktop window
service. The preserved run is infrastructure-blocked evidence, not a visual
failure. A desktop or WebRTC-enabled node can rerun the same lane without code
changes.

## Remaining no-go

This work does not fix liquid containment. In the corrected full run, as many
as 36 of 548 particles were outside the source beaker before tilt; the gate
allows at most 10. The run remains `measured_no_go`, and its video must not
replace the public delivery video. Collision/retention repair is a separate
physics task.

## Reproduction artifacts

The exploratory artifacts are intentionally under the ignored local cache:

- `.cache/gui-equivalence-20260813/full-continuous30-follow/output/result.json`
- `.cache/gui-equivalence-20260813/full-continuous30-follow/output/liquid0812_offscreen_viewport_full_30fps.mp4`
- `.cache/gui-equivalence-20260813/main-viewport-smoke/evidence/run_manifest.json`

All Isaac 4.1 physics runs used the formal absolute Python baseline and a sealed
child. Busy-GPU results retain the explicit non-authoritative evidence label.

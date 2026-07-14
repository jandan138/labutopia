# Fluid Weekly PM Restructure Outcome

## Result

The previous G1/G2 experiment report was replaced in full. The new report leads
with the accepted real-beaker pour and explains the work as three engineering
generations:

1. the original real-beaker static-hold attempt;
2. the A18 thin-walled rectangular-tank visual reference;
3. the final InternData-inspired real-beaker pour.

The report distinguishes ending-frame containment from universal leak-free
behavior, and distinguishes the delivered USD snapshots from the external
690-step motion driver.

## Media

All report media is local to
`reports/2026-07-07-labutopia-fluid-weekly/assets/pm-restructure/`.

- The original clip is explicitly labelled as a representative old-route visual,
  not the exact P4096 static-hold run.
- The A18 image was rendered from the local
  `physics_fidelity_A18_FloatBall.usd` with the installed Isaac Sim 4.5 runtime.
  It is a visual reference only and does not carry the Isaac Sim 4.1 delivery
  validation claim.
- The final context, close-up, keyframes, and validation sheet come directly from
  `lab_001_level1_pour_interndata_liquid_v1_20260714`.
- All three MP4 files were transcoded to H.264, `yuv420p`, with fast-start metadata.

## Verification

- TDD red state: four report-contract failures against the old report.
- Final focused test: `4 passed` in
  `tests/test_fluid_weekly_pm_report.py`.
- Clean-copy browser source:
  `/tmp/labutopia-fluid-weekly-review.AycVP3/`.
- Browser audit: HTTP 200 at desktop `1440x1000`, tablet `834x1112`, and mobile
  `390x844`.
- All three viewports: zero console errors, page errors, failed requests, bad
  responses, horizontal overflow elements, or broken images.
- All three videos reported `readyState=4`, `960x540`, controls enabled, and no
  media error. A playback probe confirmed that each video advanced in Chromium.
- Screenshots and audit JSON are under the clean copy's `browser-audit/` directory.

## Remaining Boundary

This boundary was superseded later on 2026-07-14 by the derived-surface replay.
The report now embeds the final 70-frame continuous-surface videos generated from
the same accepted particle trace. The remaining presentation issue is mild mesh
faceting, not visible 3 mm Points. See
`docs/runs/2026-07-14-interndata-derived-surface-replay-outcome.md`.

# Fluid Weekly PM Restructure Plan

## Goal

Replace the existing liquid weekly report with a product-manager-readable account
of the completed real-beaker pour. The previous G1/G2 report and experiment matrix
are obsolete and will not be retained in the new page.

## Files

- Replace `reports/2026-07-07-labutopia-fluid-weekly/index.html`.
- Add self-contained comparison media under
  `reports/2026-07-07-labutopia-fluid-weekly/assets/pm-restructure/`.
- Add `tests/test_fluid_weekly_pm_report.py` for content and media contracts.
- Record the three plan reviews in
  `docs/runs/2026-07-14-fluid-weekly-pm-restructure-plan-reviews.md`.

## Information Architecture

1. Lead with the result: a repeatable pour in the real LabUtopia beakers.
2. Show the final context video as the primary evidence and the close-up second.
3. Explain the four changes that made the result possible in plain language.
4. Compare three generations using the same questions: container, particle scale,
   visible result, product relevance, and lesson learned.
5. Show ending-frame counts and clean Isaac Sim 4.1 validation.
6. Separate completed deliverables from the remaining rendering work.
7. Put paths, precise parameters, provenance, and limitations in a folded appendix.

The comparison is an engineering progression, not a same-condition benchmark:
the original attempt is a static-hold baseline, the rectangular tank is a visual
reference, and the InternData-inspired route is the completed real-beaker demo.

## Execution Order

1. Inventory and verify all source evidence.
2. Write a failing report contract test.
3. Produce one truthful A18 rectangular-tank reference image from the local USD.
4. Copy the original and final evidence into the report-local asset directory.
5. Replace the HTML without preserving old sections.
6. Run the focused tests, media probes, and clean-directory portability check.
7. Audit desktop and mobile rendering in a real browser, then fix any findings.

## Claim Boundary

- `3,600/3,600` in the target and all other ending categories at zero is an
  ending-frame claim for this scene, parameter set, and 690-step trajectory.
- The USD files are stable initial and result snapshots; the full motion uses the
  external trajectory driver.
- The final evidence still renders 3 mm particle points. Continuous isosurface,
  material, lighting, and camera parity remain the next rendering milestone.
- InternData wording is limited to inspiration from its public fluid recipe. The
  LabUtopia colliders, trajectory, validation, and delivery package are local work.

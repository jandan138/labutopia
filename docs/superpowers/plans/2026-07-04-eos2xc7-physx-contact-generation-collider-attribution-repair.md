# EOS-2xC7 PhysX Contact Generation / Collider Attribution Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find why DryingBox post-close tail frames can show bilateral AABB overlap while `PhysX contact` still reports zero required-role finger-handle contact records, then produce a conservative live witness that either proves stable `panda_leftfinger` + `panda_rightfinger` PhysX contact with a verified handle collider owner or identifies the next narrower repair.

**Architecture:** EOS-2xC6 already closes the old false-positive path: AABB overlap alone cannot unlock `grasp_hold`. EOS-2xC7 keeps the same no-pull/no-score boundary and first adds read-only contact-report / collider-attribution ledgers to the existing GenManip probe/debug payloads. C7-A must not change `contact_offset`, `rest_offset`, collision filters, kinematic flags, or task semantics; otherwise it would become an intervention experiment instead of explaining the original C6 miss. The only permitted side effect in C7-A is the existing observer setup needed to attach/read `PhysxContactReportAPI`; this is recorded as `contact_report_setup_attribution` and must not be mixed with C7-B physics interventions. C7-B threshold/filter probes are allowed only after C7-A produces complete attribution evidence.

**Tech Stack:** Python, pytest, Isaac Sim 4.1, PhysX contact report API, GenManip `labutopia_oracle_debug_state.py`, GenManip `online_open_door_oracle_probe.py`, EBench `genmanip_client`, LabUtopia evidence manifests.

---

## Evidence Baseline

Authoritative C6 evidence:

```text
analysis_json=docs/labutopia_lab_poc/evidence_manifests/expert_oracle_eos2xc6_role_aware_rightfinger_touchdown_20260704_210000_eos2xc6_analysis.json
progress_tsv=docs/labutopia_lab_poc/evidence_manifests/eos2xc6_role_aware_rightfinger_touchdown_20260704_210000_eos2xc6_progress.tsv
promoted_tsv=docs/labutopia_lab_poc/evidence_manifests/eos2xc6_role_aware_rightfinger_touchdown_20260704_210000_eos2xc6_promoted.tsv
summary_count=6
submit_success_count=6
probe_success_count=6
physx_contact_channel_available_count=6
aabb_tail_bilateral_overlap_pass_count=5
tail_physx_required_roles_contact_record_count=0
retention_pass_count=0
micro_pull_diagnostic_allowed_count=0
score_claim_allowed_count=0
branch_counts.NO_RIGHTFINGER_PHYSX_CONTACT=6
```

PM translation: C6 showed that the fingers can look clamped around the handle in the debug boxes, but the simulator's physics contact channel still does not agree that both fingers are touching the handle. C7 asks the narrower question: "Is the contact missing because we attached/read the contact report wrong, because the handle's real collider is not the visible handle prim, because collision filtering suppresses the pair, or because the contact thresholds are too strict?"

## Existing Code Capability

Current GenManip code already has useful building blocks:

```text
build_physx_contact_debug_from_report(...)
build_physx_contact_debug_from_pairs(...)
prepare_labutopia_physx_contact_reports(...)
PostCloseContactRetentionTracker(require_physx_contact_retention=True)
build_asset_geometry_pad_frame_inspection_summary(...)
```

Existing guardrails to preserve:

```text
AABB near != PhysX contact
AABB overlap != PhysX contact
leftfinger-only contact != stable grasp_hold
rightfinger-only contact != stable grasp_hold
physx_contact_debug.status=unavailable != contact
score_claim_allowed=false throughout C7
micro_pull_diagnostic_allowed=false throughout C7
```

Current likely gap: target matching is centered on the resolved DryingBox handle prim path. If PhysX reports contact against a child collider, generated collision helper, parent body, or actor owner path, the current parser can mark the channel available but still classify the required target role as missing. C7 must record those unmatched paths instead of silently returning `contact_pair_count=0`.

## Implementation Progress

2026-07-04 C7-A code/unit checkpoint:

```text
GenManip branch: labutopia-stage5-eval-readback
Implemented: read-only PhysX contact header attribution
Implemented: verified target collider owner path matching
Implemented: unmatched required-role contact pair reporting
Implemented: AABB selected robot/target pair attribution
Implemented: pre-step contact-report setup attribution preserved into debug obs
Implemented after review: AABB handle target matching is tokenized, so
`/handle` or target uid suffix `_handle` counts as handle evidence, but
`handle_support`, `handle_visual`, or other sibling/helper parts do not.
Implemented: C7-A candidate TSV generated and schema/source-directory validated
Implemented: first C7-A live EBench witness attempt for `eos2xc7_w024_base_attachment_audit`
Partial only: this witness proves the server/submit/probe path runs and records
read-only PhysX/contact-attribution fields, but it stops before `grasp_hold`
because `approach_near` is not reached.
Not implemented yet: C7-B contact/rest offset or collision-filter intervention
```

Review boundary accepted on 2026-07-04:

```text
Existing gripper action execution is part of the oracle/action path, not a new C7-A attribution behavior.
Existing contact report API setup is observer instrumentation; C7-A only records it and must not change contact/rest offset, filters, kinematic flags, or task semantics.
AABB selected-pair attribution must identify the exact selected robot/target collider paths but never promote AABB overlap to PhysX contact.
```

Verification:

```text
/usr/bin/python -m pytest -q tests/labutopia_poc/test_labutopia_oracle_debug_state.py
25 passed

/usr/bin/python -m pytest -q tests/labutopia_poc/test_evaluator_ee_pose_action.py
22 passed

/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py
233 passed

/usr/bin/python -m py_compile genmanip/core/evaluator/labutopia_oracle_debug_state.py genmanip/core/evaluator/env.py standalone_tools/labutopia_poc/online_open_door_oracle_probe.py tests/labutopia_poc/test_labutopia_oracle_debug_state.py tests/labutopia_poc/test_evaluator_ee_pose_action.py tests/labutopia_poc/test_online_open_door_oracle_probe.py
passed
```

PM translation: the code can now preserve the evidence needed to explain why
PhysX did or did not count a contact. This is still not a live run and not a
score result; it only makes the next live run diagnostic enough to classify the
blocker.

2026-07-04 C7-A candidate TSV checkpoint:

```text
candidate_tsv=docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_candidates.tsv
candidate_row_count=6
candidate_ids_unique=true
source_rows=eos2xc6_w024_base,eos2xc6_w028_base
attribution_lanes=attachment_audit,collider_owner_audit,filter_offset_readout
micro_pull_allowed=false for all rows
score_claim_allowed=false for all rows
physics_intervention_allowed=false for all rows
source_log_dirs_exist=true
source_eval_result_dirs_exist=true
source_eval_result_file_count=0 for both C6 source rows
source_manifest_present=false
```

Boundary: this TSV is a run queue and provenance ledger, not C7-A live evidence.
Because the LabUtopia-local C6 analysis/progress/promoted manifests are missing,
the TSV pins GenManip-local C6 log/result directories and marks the expected C6
analysis manifest as absent. Before publishing final C7 live evidence, either
import/freeze the C6 manifests into LabUtopia or preserve the absolute GenManip
source paths in the C7 analysis JSON.

2026-07-04 C7-A first live witness checkpoint:

```text
evidence_root=docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7
candidate_id=eos2xc7_w024_base_attachment_audit
run_id=labutopia_eos2xc7_physx_contact_generation_collider_attribution_eos2xc7_w024_base_attachment_audit_20260704_223000_eos2xc7
task_config=ebench/labutopia_lab_poc/franka_poc/diagnostics/level1_open_door_solver_vit4_self_collision_off.yml
submit_exit=0
probe_exit=0
trace_lines=297
summary_size=280K
trace_size=26M
server_start_fix=use short RAY_TMPDIR (/tmp/r7c7); longer names can exceed Ray AF_UNIX socket path limit
diagnostic_purpose=grasp_hold_retention
stop_after_stage_label=grasp_hold
hard_gate_failure.label=approach_near
hard_gate_failure.exit_reason=stage_not_reached:max_steps_exhausted
hard_gate_failure.min_actual_distance_m=0.03453716465463178
hard_gate_failure.final_actual_distance_m=0.03913976102212624
hard_gate_failure.max_command_actual_gap_m=0.01619371223682052
final_door_angle_deg=-0.00043119222061279355
final_metric.score=0.0
physx_contact_debug.status=available
physx_contact_debug.contact_pair_count=0
physx_contact_debug.required_roles_contact=false
post_close_contact_retention_summary.retention_pass=false
post_close_contact_retention_summary.sample_count=0
score_claim_allowed=false
micro_pull_diagnostic_allowed=false
grasp_hold_retention_claim_allowed=false
```

Interpretation: this is valid live infrastructure evidence but not yet valid
contact-generation attribution. The run never reaches the configured
`grasp_hold` stage; it stops earlier at `approach_near`, so zero PhysX contact
pairs cannot yet be interpreted as "the handle collider cannot generate
contact." The next C7-A action must first recover or freeze the exact C6 command
parameters, or run a bounded readback diagnostic around `approach_near`, before
spending the remaining candidate rows on collider/filter attribution.

2026-07-04 review checkpoint: a second reviewer independently classified the
first live witness as an upstream `approach_near` hard-gate failure, not a
contact-generation attribution failure. The next highest-signal read-only
diagnostic is:

```text
--probe-mode controller-readback-comparator
--controller-readback-waypoint-label approach_near
--open-width-m 0.024
--close-width-m 0.010
```

Do not run C7-B physics edits and do not spend the remaining collider/filter
rows until this bounded readback explains whether the target command, controller
tracking, or waypoint tolerance is responsible for missing `approach_near`.

2026-07-04 bounded readback checkpoint:

```text
row_dir=docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_near_readback_20260704_124339
run_id=labutopia_eos2xc7_approach_near_readback_eos2xc7_w024_base_attachment_audit_20260704_124339
submit_exit=0
probe_exit=0
trace_lines=1
probe_mode=controller-readback-comparator
controller_readback_waypoint_label=approach_near
status=FAIL_CONTROLLER_READBACK_COMPARATOR_NO_IK_TARGET
blockers=missing_successful_ee_pose_ik_debug,ee_pose_target_position_error_exceeds_tolerance
executed_steps=1
target_world=[0.44979134324235837,0.24876333628991587,1.1085916790181332]
target_robot_frame=[0.8497913432423584,0.24876333628991587,0.3985916790181332]
post_ee_position=[0.3892921805381775,0.004671737086027861,0.45819777250289917]
ee_pose_target_position_error_m=0.5245884806528617
```

Interpretation: the failure has moved upstream of contact attribution. This
readback does not prove handle collider or PhysX contact generation failure; it
shows that `approach_near` did not produce a successful `ee_pose` IK target /
readback match. Before returning to collider/filter rows, classify whether
`NO_IK_TARGET` means target-frame construction / reachability is wrong or the
comparator lacks IK debug visibility. Candidate next read-only checks are a
known-earlier `approach_pre` comparator baseline and source inspection of
`approach_near` target construction.

2026-07-04 `approach_pre` comparator baseline:

```text
row_dir=docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_readback_20260704_125312
run_id=labutopia_eos2xc7_approach_pre_readback_eos2xc7_w024_base_attachment_audit_20260704_125312
submit_exit=0
probe_exit=0
trace_lines=2
probe_mode=controller-readback-comparator
controller_readback_waypoint_label=approach_pre
status=FAIL_CONTROLLER_READBACK_COMPARATOR_DIAGNOSTIC_ONLY
blockers=ee_pose_terminal_without_post_obs,ee_pose_arm_state_jump_too_large,joint_position_terminal_without_post_obs,joint_position_arm_state_jump_too_large
executed_steps=2
target_world=[0.3997913432423583,0.24876333628991587,1.1085916790181332]
target_robot_frame=[0.7997913432423583,0.24876333628991587,0.3985916790181332]
target_orientation_wxyz=[0.5735764363510462,0.0,0.8191520442889918,0.0]
same_target_pose=true
parse_only_ik_success=true
parse_only_ik_action_source=ik_solution
ik_joint_delta_abs_max=2.0215107798576355
invalid_state=arm_state_jump_too_large
violating_joint=panda_joint4
post_world_step_delta_abs_max=1.6464000940322876
```

Interpretation: `approach_pre` is IK-solvable and the comparator does expose
successful IK debug, so the previous `approach_near` `NO_IK_TARGET` cannot be
reduced to missing debug visibility. The new blocker is execution granularity:
single-step application of the IK target violates the arm-state jump guard
before post observation. Next action is a read-only bounded joint lead-in for
`approach_pre`; do not change contact offsets, filters, kinematic flags, or
task semantics.

2026-07-04 bounded joint lead-in checkpoint:

```text
row_dir=docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_bounded_lead_in_20260704_130833
run_id=labutopia_eos2xc7_approach_pre_bounded_lead_in_eos2xc7_w024_base_attachment_audit_20260704_130833
submit_exit=0
probe_exit=0
trace_lines=56
probe_mode=bounded-joint-lead-in
controller_readback_waypoint_label=approach_pre
status=FAIL_BOUNDED_JOINT_LEAD_IN_DIAGNOSTIC_ONLY
executed_steps=56
lead_in_steps=55
max_joint_step_rad=0.05
post_step_delta_threshold_rad=0.1
command_target_delta_exceed_indices=[]
post_step_delta_exceed_indices=[52,53,54]
final_joint_target_abs_max_rad=0.6525141596794128
terminal_reason=arm_state_jump_too_large
terminal_violating_joint=panda_joint6
late_step_timeline=lead_in_late_step_timeline.json
```

Interpretation: bounded command generation worked; the failure is late
readback/controller divergence near the target, not raw command step size. A
controller/physics reviewer and an oracle/EBench reviewer both concluded that
this remains upstream of contact/collider attribution. Next actions:

1. Audit the existing late-step timeline around steps 48-54: per-joint
   pre/target/post readback, target error, drive gain, and handle clearance.
2. Validate target-frame, wrist orientation, reachability, and collision
   clearance before treating the parsed IK target as an oracle path.
3. Move the oracle design toward EBench-style object-frame manual waypoints
   with per-waypoint cuRobo planning; smaller lead-in step size is only a later
   isolation test, not the main route. Do not call this full
   `collision-aware planning` until the implementation explicitly refreshes
   and logs cuRobo world obstacles.

2026-07-04 target-frame / reachability audit checkpoint:

```text
row_dir=docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_target_frame_reachability_audit_20260704_132909
summary=target_frame_reachability_audit.json
status=READ_ONLY_AUDIT_COMPLETE_DIAGNOSTIC_ONLY
classification=UPSTREAM_TARGET_REACHABILITY_AND_CONTROLLER_STABILITY_OPEN
base_frame_assessment=PASS_BASE_FRAME_CONSISTENT_FOR_CURRENT_EVIDENCE
full_oracle_pose_mode=relative
full_oracle_orientation_mode=identity
comparator_orientation_mode=fixed absolute native orientation
recommended_decision=move_to_ebench_style_object_frame_waypoints_plus_curobo_planning
```

Interpretation: the current audited path does not support a robot-base mismatch
as the main blocker. The task config, probe default, and live summary all use
`[-0.4, 0.0, 0.71]`, and key waypoint robot-frame targets match
`target_world - robot_base_world_xyz`. This does not rule out later
object-frame convention mistakes; those must be tested in the new waypoint
contract. The higher-signal issue is that the
diagnostic path still tests a single fixed absolute IK target, while the first
live witness used a relative/identity orientation control mode and EBench
microwave uses `object_frame` waypoint sequences plus per-waypoint cuRobo
planning. Therefore the next implementation work should define a DryingBox
object-frame waypoint contract and a per-waypoint planner path before returning
to contact/collider C7-A rows. The implementation must explicitly call or log
cuRobo world refresh before we claim full collision awareness.

Next implementation plan:

```text
docs/superpowers/plans/2026-07-04-dryingbox-object-frame-curobo-oracle.md
```

2026-07-04 object-frame oracle Task 1-2 checkpoint:

```text
status=PURE_CONTRACT_AND_CLAIM_GUARD_DONE_RUNTIME_PLANNER_NOT_RUN
genmanip_worktree=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
implemented=DryingBoxObjectFrameWaypoint
implemented=build_dryingbox_object_frame_waypoints
implemented=build_waypoint_planning_record
implemented_probe_mode=object-frame-curobo-planner-smoke
probe_mode_behavior=NOT_IMPLEMENTED_OBJECT_FRAME_CUROBO_PLANNER_SMOKE
runtime_curobo_planning=not_run
curobo_world_refresh=not_attempted
stable_grasp_claim_allowed=false
micro_pull_claim_allowed=false
door_open_claim_allowed=false
score_claim_allowed=false
collision_aware_planning_claim_allowed=false
```

Verification:

```text
dryingbox_object_frame: 2 passed
waypoint_planning_record or object_frame: 6 passed
build_oracle_waypoints/dryingbox/planning-record/probe-mode regression: 26 passed
py_compile: exit 0
```

Interpretation: the EBench microwave-style object-frame contract is now
represented in code and tests, and the planning-record schema prevents
calling a planner result collision-aware without logged cuRobo world refresh.
The next valid work item is Task 3 of the object-frame plan: real runtime
planner smoke. Do not resume C7 contact/collider attribution rows until that
path can create an auditable `grasp_hold` window.

## C7 Debug Contract

Add or verify these fields in `physx_contact_debug` and post-close retention summaries. Unknown USD/PhysX schema fields must be recorded as `unknown`, not inferred:

```json
{
  "schema_version": 2,
  "status": "available",
  "method": "physx_contact_report",
  "required_roles": ["panda_leftfinger", "panda_rightfinger"],
  "target_prim_paths": ["/World/.../obj_obj_DryingBox_01/handle"],
  "verified_target_collider_owner_paths": ["/World/.../obj_obj_DryingBox_01/handle/collider"],
  "role_contact_states": {
    "panda_leftfinger": {
      "contact": true,
      "contact_pair_count": 1,
      "contact_paths": ["/World/.../franka/panda_leftfinger/..."],
      "target_contact_paths": ["/World/.../obj_obj_DryingBox_01/handle/collider"]
    },
    "panda_rightfinger": {
      "contact": true,
      "contact_pair_count": 1,
      "contact_paths": ["/World/.../franka/panda_rightfinger/..."],
      "target_contact_paths": ["/World/.../obj_obj_DryingBox_01/handle/collider"]
    }
  },
  "required_roles_contact": true,
  "contact_pair_count": 2,
  "unmatched_contact_pairs": [],
  "contact_report_attachment_status": "ATTACHED_TO_REQUIRED_ROLES_AND_TARGET",
  "collider_attribution_status": "VERIFIED_HANDLE_COLLIDER_OWNER",
  "physx_contact_generation_branch": "TRUE_REQUIRED_ROLE_CONTACT_GENERATED_ENTER_EOS2Y"
}
```

Required attribution ledgers, in addition to the compact example above:

```text
contact_report_setup_attribution:
  requested_role_paths
  requested_target_paths
  applied_prim_paths
  missing_prim_paths
  threshold_by_path
  has_contact_report_api_by_path

collider_attachment_attribution:
  prim_valid
  has_collision_api
  collision_enabled
  descendant_collision_prim_paths
  report_api_attached_to_requested_path
  report_api_attached_to_collider_path

collision_filtering_attribution:
  filtered_pair_targets
  collision_group_paths
  rigid_body_enabled
  kinematic_enabled

offset_attribution:
  physx_contact_offset_m
  physx_rest_offset_m
  offset_source_path
  offset_read_status

contact_header_attribution:
  total_header_count
  lost_header_count
  zero_contact_header_count
  decode_failed_count
  matched_required_role_pair_count
  unmatched_reason_counts

contact_pair_attribution:
  header_index
  event_type
  num_contact_data
  raw/decoded collider0 and collider1
  raw/decoded actor0 and actor1
  body_path_source
  matched_role
  matched_target_path
  reject_reason
```

Also preserve AABB contact-frame attribution in `online_open_door_oracle_probe.py`:

```text
selected_robot_prim_path
selected_target_prim_path
selected_pair_rank
robot_bbox_source
target_bbox_source
separated
axis_gap_m
axis_overlap_m
```

This explains which collider pair produced the AABB overlap candidate without upgrading AABB overlap into physics contact.

Allowed failure branches:

```text
CONTACT_REPORT_ATTACHMENT_MISS
COLLIDER_ATTRIBUTION_MISS
COLLISION_FILTER_OR_KINEMATIC_SUPPRESSION
CONTACT_OFFSET_OR_REST_OFFSET_TOO_STRICT
AABB_ONLY_NO_PHYSX_CONTACT
PHYSX_CONTACT_CHANNEL_UNAVAILABLE
TRUE_REQUIRED_ROLE_CONTACT_GENERATED_ENTER_EOS2Y
```

## Success Criteria

C7 has two different pass levels:

```text
Attribution closure:
  contact_report_setup_attribution present
  collider_attachment_attribution present
  contact_header_attribution present
  contact_pair_attribution present
  AABB selected-pair attribution present
  branch is one of the allowed C7 branches
  score_claim_allowed=false

Physical contact closure:
  all attribution closure checks pass
  tail window has active PhysX contact records for both panda_leftfinger and panda_rightfinger
  target side is DryingBox handle or verified handle collider owner
  CONTACT_LOST and contact_count <= 0 are excluded
  provider unavailable, left-only contact, and right-only contact do not pass
  score_claim_allowed=false
```

## File Map

- Modify in GenManip if needed:
  - `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/labutopia_oracle_debug_state.py`
  - `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/env.py`
  - `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Modify tests in GenManip:
  - `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_labutopia_oracle_debug_state.py`
  - `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_evaluator_ee_pose_action.py`
  - `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`
- Create evidence in LabUtopia:
  - `docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_candidates.tsv`
  - `docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_progress.tsv`
  - `docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_promoted.tsv`
  - `docs/labutopia_lab_poc/evidence_manifests/expert_oracle_eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_analysis.json`
- Update LabUtopia docs after live evidence:
  - `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
  - `docs/labutopia_lab_poc/aan_consumer_handoff.md`
  - `docs/labutopia_lab_poc/evidence_manifests/README.md`

## Candidate Matrix

Start from the strongest C6 rows. C7-A is read-only attribution only; do not change contact/rest offsets, filters, kinematic flags, or collision settings in this matrix.

| Candidate | Source | Lane type | Purpose |
|---|---|---|---|
| `eos2xc7_w024_base_attachment_audit` | `eos2xc6_w024_base` | baseline replay + full pair dump | Check whether contact exists under unclassified paths. |
| `eos2xc7_w024_collider_owner_audit` | `eos2xc6_w024_base` | verified handle collider owner matching | Check visible handle vs collision owner mismatch. |
| `eos2xc7_w024_filter_offset_readout` | `eos2xc6_w024_base` | read-only collision/filter/offset metadata dump | Check filtering, kinematic, contact offset, and rest offset fields without changing them. |
| `eos2xc7_w028_base_attachment_audit` | `eos2xc6_w028_base` | baseline replay + full pair dump | Repeat on wider open width family. |
| `eos2xc7_w028_collider_owner_audit` | `eos2xc6_w028_base` | verified handle collider owner matching | Repeat handle collider owner check. |
| `eos2xc7_w028_filter_offset_readout` | `eos2xc6_w028_base` | read-only collision/filter/offset metadata dump | Repeat filter/kinematic/offset readout on wider open width family. |

Every row must keep:

```text
diagnostic_purpose=physx_contact_generation
stop_after_stage_label=grasp_hold
LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1
post_close_retention_require_physx_contact=true
micro_pull_allowed=false
score_claim_allowed=false
physics_intervention_allowed=false
```

Deferred C7-B candidates:

```text
small_contact_offset_probe
small_rest_offset_probe
collision_filter_intervention_probe
```

These must not run in C7-A. They are only legal after C7-A proves attribution fields are complete and explains whether the original C6 miss is attachment, collider ownership, filtering, threshold, or true missing geometry contact.

## Task 1: Add Attribution Unit Tests

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_labutopia_oracle_debug_state.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`

- [ ] Add a parser test where PhysX reports `panda_leftfinger`/`panda_rightfinger` against `/handle/collider`; expected result is `required_roles_contact=true` when `/handle/collider` is a verified target collider owner.
- [ ] Add a parser test where PhysX reports finger contact against `/body/door/collider`; expected result is `required_roles_contact=false`, `unmatched_contact_pairs` populated, and branch `COLLIDER_ATTRIBUTION_MISS`.
- [ ] Add a parser test where no contact headers exist but AABB tail overlap is true; expected result remains `AABB_ONLY_NO_PHYSX_CONTACT`.
- [ ] Add `test_contact_frame_role_attribution_preserves_selected_collider_paths` for AABB selected-pair attribution.
- [ ] Add `test_physx_contact_debug_from_report_emits_header_attribution_and_reject_reasons` for collider-vs-actor path source, `CONTACT_LOST`, zero-contact headers, and unmatched reasons.
- [ ] Add `test_prepare_physx_contact_reports_emits_attachment_and_offset_attribution` using fake stage/prim or pure helper coverage.
- [ ] Add a retention test proving `tail_physx_required_roles_contact_records > 0` requires both roles and a verified target owner in the same tail frames.
- [ ] Add a left-only PhysX contact retention case proving it cannot pass bilateral retention even when AABB tail passes.
- [ ] Add a regression test proving `score_claim_allowed` stays `false` even if C7 records bilateral PhysX contact.

Validation:

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_labutopia_oracle_debug_state.py -k "physx_contact"
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "physx or attribution or retention"
```

## Task 2: Implement Contact-Report / Collider Attribution

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/labutopia_oracle_debug_state.py`
- Modify if needed: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/env.py`

- [ ] Extend target matching from `target_prim_paths` to `target_prim_paths + verified_target_collider_owner_paths`.
- [ ] Record every raw contact header pair after path decoding in a bounded `raw_contact_pairs_sample`.
- [ ] Record `unmatched_contact_pairs` when a required finger role appears but the target side is not a verified handle/collider owner.
- [ ] Record `contact_pair_attribution` with `header_index`, event type, collider/actor decoded paths, path source, matched role/target, and reject reason.
- [ ] Record `contact_header_attribution` counts for lost headers, zero-contact headers, decode failures, matched pairs, and unmatched reason counts.
- [ ] Record `verified_target_collider_owner_paths` from static USD inspection or live stage traversal.
- [ ] Preserve `prepare_labutopia_physx_contact_reports(...)` output as `contact_report_setup_attribution` instead of dropping it after pre-step setup.
- [ ] Record `contact_report_applied_prim_paths` and classify attachment miss when required finger/target prims were not configured before stepping.
- [ ] Record collider attachment, collision filtering, kinematic, contact offset, and rest offset fields as read-only values or explicit `unknown`.
- [ ] Keep `status=unavailable` separate from `status=available` with zero pairs.

Success condition for this task is not a live pass. It is a richer debug payload that can distinguish "no PhysX contact exists" from "PhysX contact exists but we classified the target side incorrectly."

## Task 3: Implement Probe Summary Branching

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/online_open_door_oracle_probe.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_online_open_door_oracle_probe.py`

- [ ] Add a pure helper such as `classify_physx_contact_generation_branch(...)`.
- [ ] Feed branch, target owner status, unmatched pair count, and required-role contact count into `PostCloseContactRetentionTracker.summary()`.
- [ ] Ensure AABB-only tail overlap remains diagnostic and cannot set `grasp_hold_retention_claim_allowed`.
- [ ] Ensure C7 summary exposes these fields:

```text
physx_contact_generation_branch
contact_report_attachment_status
collider_attribution_status
tail_verified_target_collider_contact_records
tail_unmatched_required_role_contact_records
required_robot_roles_contact_recorded
required_target_roles_contact_recorded
```

## Task 4: Generate C7 Candidate TSV

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_candidates.tsv`

- [x] Use exactly the six rows in the candidate matrix unless Task 1-3 evidence shows a smaller matrix is sufficient.
- [x] Include C6 source paths and source row ids.
- [x] Include lane purpose fields:

```text
diagnostic_purpose=physx_contact_generation
attribution_lane=attachment_audit|collider_owner_audit|filter_offset_readout
micro_pull_allowed=false
score_claim_allowed=false
physics_intervention_allowed=false
```

- [x] Validate TSV formulas and source directory/file-count existence before running Isaac Sim.

Validation note: the two source log directories exist and contain 4 / 3 log files,
and both source eval-result directories exist but contain 0 files. The expected
LabUtopia-local C6 analysis manifest is absent by design in this checkpoint and
is recorded as `source_manifest_present=false`.

2026-07-04 object-frame planner-interface checkpoint: the follow-up
`docs/superpowers/plans/2026-07-04-dryingbox-object-frame-curobo-oracle.md`
has advanced through Task 3's client-side diagnostic branch. GenManip now returns
`BLOCKED_RUNTIME_PLANNER_INTERFACE_NOT_EXPOSED` for
`--probe-mode object-frame-curobo-planner-smoke` when the EvalClient path exposes
no planner-only method. This confirms the next blocking step is a server-side
planner smoke hook or `custom_motion`-backed generation path, not more C7
contact/collider rows. Do not resume Task 5 live witness until a planner path can
produce at least an auditable `approach_pre` / `approach_near` / `contact`
planning result and preferably a stable `grasp_hold` window.

## Task 5: Run Isolated Live Witness

**Runtime:**

```bash
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
```

**Environment boundary:**

```text
PYTHONNOUSERSITE=1
ACCEPT_EULA=Y
OMNI_KIT_ACCEPT_EULA=YES
LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1
CUROBO_SRC=/cpfs/shared/simulation/zhuzihou/dev/curobo
CUDA11_LIB=/usr/local/cuda-11.8/targets/x86_64-linux/lib
```

- [ ] Start a fresh EBench server on an unused port and record `server.env.txt`, stdout/stderr, process id, and cleanup evidence.
- [ ] Run each C7 row through submit + probe.
- [ ] Write per-row `contact_frame_summary.json`, `contact_frame_trace.jsonl`, command files, stdout/stderr, and exit codes.
- [ ] Stop at `grasp_hold`; do not run micro-pull or full score.
- [ ] Reject any row that changes contact/rest offsets, collision filters, kinematic flags, or collision settings; those belong to C7-B follow-up.
- [ ] If any row records verified bilateral PhysX finger-handle contact, do not claim score; only promote to the next planned micro-pull diagnostic stage.

## Task 6: Aggregate And Classify Results

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_progress.tsv`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_promoted.tsv`
- Create: `docs/labutopia_lab_poc/evidence_manifests/expert_oracle_eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_analysis.json`

- [ ] Aggregate:

```text
summary_count
submit_success_count
probe_success_count
physx_contact_channel_available_count
required_both_finger_physx_contact_count
verified_handle_collider_owner_contact_count
unmatched_required_role_contact_count
branch_counts
retention_pass_count
micro_pull_diagnostic_allowed_count
score_claim_allowed_count
```

- [ ] Classify next stage:
  - `TRUE_REQUIRED_ROLE_CONTACT_GENERATED_ENTER_EOS2Y`: proceed to bounded micro-pull diagnostic.
  - `COLLIDER_ATTRIBUTION_MISS`: repair target collider owner mapping and rerun C7.
  - `CONTACT_REPORT_ATTACHMENT_MISS`: repair report attachment setup and rerun C7.
  - `COLLISION_FILTER_OR_KINEMATIC_SUPPRESSION`: audit collision filters and articulation/kinematic flags.
  - `CONTACT_OFFSET_OR_REST_OFFSET_TOO_STRICT`: run a smaller threshold probe only after attribution is proven.
  - `AABB_ONLY_NO_PHYSX_CONTACT`: return to grasp geometry / finger placement.

## Task 7: Update PM Docs And Handoff

**Files:**
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`

- [ ] Add C7 live result with the exact evidence paths.
- [ ] Explain in product language whether the blocker is contact wiring, collider ownership, filtering, thresholds, or true missing contact.
- [ ] Keep all forbidden claims out of the docs:

```text
door opened
stable grasp
micro-pull passed
Expert Oracle Score passed
official Lift2/R5a score
policy score
```

## Verification

Run before claiming C7 complete:

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_labutopia_oracle_debug_state.py -k "physx_contact"
/usr/bin/python -m pytest -q tests/labutopia_poc/test_evaluator_ee_pose_action.py -k "physx"
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py -k "physx or attribution or retention"
/usr/bin/python -m pytest -q tests/labutopia_poc/test_online_open_door_oracle_probe.py
/usr/bin/python -m py_compile genmanip/core/evaluator/labutopia_oracle_debug_state.py standalone_tools/labutopia_poc/online_open_door_oracle_probe.py
```

LabUtopia doc checks:

```bash
git diff --check -- docs/superpowers/plans/2026-07-04-eos2xc7-physx-contact-generation-collider-attribution-repair.md docs/superpowers/specs/2026-07-04-eos2xc7-physx-contact-generation-collider-attribution-design.md docs/labutopia_lab_poc/expert_oracle_score_plan.md docs/labutopia_lab_poc/aan_consumer_handoff.md
rg -n "Expert Oracle Score passed|official Lift2/R5a score|policy score|door opened|stable grasp" docs/labutopia_lab_poc docs/superpowers/plans/2026-07-04-eos2xc7-physx-contact-generation-collider-attribution-repair.md
```

Expected boundary after C7:

```text
Best pass claim: verified bilateral PhysX finger-handle contact in grasp_hold tail, ready for next bounded micro-pull diagnostic.
Not allowed: Expert Oracle Score, official score, door-open success, or policy success.
```

## PM Summary

给产品经理的说法：C6 证明了“看起来夹住”还不等于“物理引擎承认夹住”。C7-A 第一轮不是再调参数，而是只读体检：先看 contact report 有没有接到正确部件，再看真实 collider 是不是挂在 handle 下面，再看是否被 collision filter 或 kinematic 设置屏蔽，同时只读取 contact offset / rest offset，不修改它们。C7-A 完成后，理想结果不是直接得分，而是拿到一条干净证据：要么 EBench/Isaac Sim 真实记录到 Franka 左右两根手指同时接触 DryingBox handle 的物理接触，要么明确告诉我们问题属于 contact report wiring、collider owner、filter/kinematic、threshold 还是抓取几何本身。只有真实双指 PhysX contact 证据成立，下一步才值得做 micro-pull 和最终 metric score。

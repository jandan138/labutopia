# EOS-2xC7 PhysX Contact Generation / Collider Attribution Design

Date: 2026-07-04

## Purpose

EOS-2xC6 proved that AABB-only overlap is not enough for `Expert Oracle Score`:
5/6 rows reached post-close bilateral AABB overlap, but 0/6 rows produced
required-role `PhysX contact` records for `panda_leftfinger` and
`panda_rightfinger` touching the DryingBox handle. EOS-2xC7 therefore asks one
narrow question:

```text
Why does the debug geometry look overlapped while PhysX reports no stable
panda_leftfinger / panda_rightfinger contact with the DryingBox handle?
```

C7 is not a micro-pull or score stage. It is a physics-contact closure stage:
before trying to pull the door or claim any metric score, the runtime must first
prove stable required-role contact in the physics engine.

## Current Evidence Boundary

Authoritative C6 evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/expert_oracle_eos2xc6_role_aware_rightfinger_touchdown_20260704_210000_eos2xc6_analysis.json
docs/labutopia_lab_poc/evidence_manifests/eos2xc6_role_aware_rightfinger_touchdown_20260704_210000_eos2xc6_progress.tsv
docs/labutopia_lab_poc/evidence_manifests/eos2xc6_role_aware_rightfinger_touchdown_20260704_210000_eos2xc6_promoted.tsv
```

Allowed claim from C6:

```text
PhysX contact report channel is available, and AABB bilateral overlap can occur.
```

Forbidden claims from C6:

```text
stable grasp
micro-pull readiness
door opened
Expert Oracle Score pass
policy score
official Lift2/R5a score
```

## Design

C7 separates four failure classes that C6 intentionally kept bundled:

1. **Contact-report attachment miss**: contact may exist in PhysX, but the report
   is attached to the wrong prim or read under the wrong role/path.
2. **Collider attribution miss**: the visible handle mesh and the collision shape
   used by PhysX are not the same object, or the handle collision is owned by a
   parent/body prim that C6 did not classify as the handle.
3. **Collision filtering / kinematic suppression**: robot finger and handle
   shapes are configured so AABB boxes can overlap, but PhysX does not emit the
   expected contact pair.
4. **Contact offset / rest offset too strict**: shapes are close or slightly
   interpenetrating in diagnostic AABB, but PhysX contact-generation thresholds
   still do not create a stable report record.

C7-A should add explicit collider-path and contact-report attribution fields to
the existing `online_open_door_oracle_probe.py` evidence, rather than changing
task semantics. It must be read-only in the physics-intervention sense: do not
change `contact_offset`, `rest_offset`, collision filters, kinematic flags, or
collision settings while trying to explain the original C6 miss. The allowed
exception is observer instrumentation already required for `PhysxContactReportAPI`
readback; C7-A must record that setup as evidence and must not treat it as a
contact-generation repair. If a schema field cannot be read reliably in Isaac
Sim 4.1, record it as `unknown` instead of inferring it. Intervention lanes such
as small `contact_offset` / `rest_offset` probes belong to a later C7-B follow-up
after C7-A attribution is complete.

Handle attribution must also be exact enough to avoid helper-part false positives:
path segment `/handle` or target uid suffix `_handle` is eligible handle evidence;
`handle_support`, `handle_visual`, generated guides, or sibling collision helpers
are not eligible unless a later manifest explicitly verifies them as the handle
collider owner.

## Microwave Precedent Boundary

`mobile_manip/microwave` is a useful reference for expert generation, not a score
shortcut. Its GenManip source config is:

```text
/cpfs/shared/simulation/zhuzihou/dev/GenManip/configs/tasks/ebench/mobile_manip/test_mini/microwave.yml
```

It hand-writes `demonstration_configs.generation_config.action_path.mode=manual`
with `custom_motion` and `move_to` waypoints, then uses `planner: curobo` to turn
object-frame / robot-frame targets into executable actions. That tells us
DryingBox can reasonably move toward an EBench-side scripted oracle / online
planner. It does not allow DryingBox to skip stable `PhysX contact`, grasp
retention, micro-pull, or final metric score validation.

## Success Criteria

C7 has two pass levels. Attribution closure means the read-only ledgers are
complete enough to say why C6 missed contact. Physical contact closure is
stricter and passes only if at least one live row records all of the following in
the tail window:

```text
physx_contact_channel_available=true
required_robot_roles_contact_recorded includes panda_leftfinger and panda_rightfinger
required_target_role_contact_recorded includes DryingBox handle or verified handle collider owner
tail_physx_required_roles_contact_record_count > 0
post_close_retention_require_physx_contact=true
score_claim_allowed=false
```

If C7 passes, the next stage may be a bounded micro-pull diagnostic. If C7 fails,
the next stage remains a narrower collider/contact-report repair. Either way,
C7 alone cannot claim `Expert Oracle Score`.

## PM Summary

给产品经理的说法：C6 证明“几何盒看起来夹住”还不等于“物理引擎承认夹住”。C7 是检查
为什么物理引擎没有给出双指接触证据：可能是 contact report 挂错位置，可能是真正的
handle collider 没被识别，可能是 collision filter / kinematic 设置屏蔽，也可能是
contact offset / rest offset 阈值问题。只有 C7 让 `PhysX contact` 在 tail window 里稳定
看到左右两根手指同时接触 verified handle collider owner，才进入后续 micro-pull 和最终
metric score。

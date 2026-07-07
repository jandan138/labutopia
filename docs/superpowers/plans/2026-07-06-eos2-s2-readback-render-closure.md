# EOS2 S2 Readback Render Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the S1R-D Route B positive score-chain result into a defensible S2/M3 claim only if same-run readback, metric-input, and render evidence support it.

**Architecture:** This plan starts with no-new-live evidence extraction from the S1R-D fresh S1 run. It separates M1 score-chain success from S2/M3 expert-oracle claims: M1 already passed, while S2/M3 need door joint readback, metric input dump, render/snapshot, and route provenance review before any stronger product claim.

**Tech Stack:** LabUtopia evidence manifests, GenManip `result_info.json`, `action_log.jsonl`, `metric_trace.jsonl`, EBench `manip/default/check_joint_angle`, Python JSON inspection, `python -m json.tool`, `git diff --check`.

---

## Current Evidence

M1 / formal score-chain is closed by:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json
```

Key facts:

```text
run_id=eos2_s1r_d_route_b_bridge_fresh_s1_20260706_003
runner_exit_code=0
classification=PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT
score=1.0
success_rate=1
metric_score=[[[1.0]]]
executed_steps=578
action_log=14 bridge actions + 564 LabUtopia native expert actions
```

The result is **S1/M1 pass** and **S2/M3 positive candidate evidence**. It is not yet
`Expert Oracle Score complete`, because the current evidence directory does not yet
contain explicit door joint readback, metric input dump, or render/snapshot proof.

## 2026-07-06 Execution Result

Task 1 and Task 2 have been executed as no-new-live evidence review. The result is:

```text
S2_BLOCKED_READBACK_RENDER_EVIDENCE_GAP_NO_NEW_LIVE_RELEASE
```

The inventory manifest is:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_readback_render_inventory_20260706.json
```

The claim review manifest is:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_claim_review_20260706.json
```

Key facts:

- The fresh S1 run has authoritative `result_info.json` with `score=1.0`, `success_rate=1`, and `metric_score=[[[1.0]]]`.
- The official metric config checks `obj_DryingBox_01/RevoluteJoint` in the `30-120deg` range with `succ_cnts=59`.
- The current `metric_trace.jsonl` does not dump DryingBox door joint angles or metric input samples; it only has reset robot `state.joints` and compact metric outputs.
- The current visual evidence is only a reset `video.camera2_view`; runner stdout reports repeated `No camera frames provided for this step`, so there is no terminal/front-view render evidence.

Therefore S2/M3 cannot be claimed complete. The next valid action is a separate
`S2 Instrumented Replay Release Review`, allowing at most one replay with the same frozen
Route B source to collect door joint readback, metric input dump, and terminal/front-view render.

## Decision Boundary

Allowed now:

```text
M1 formal score-chain passed.
Route B bridged expert replay produced positive official score candidate.
```

Not allowed yet:

```text
S2 complete.
M3 complete.
Expert Oracle Score complete.
Workflow ready for expansion.
Official leaderboard readiness.
```

## Task 1: No-New-Live Evidence Inventory

**Files:**
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_20260706/metric_trace.jsonl`
- Read: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_20260706/action_log.jsonl`
- Read: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results/ebench/eos2_s1r_d_route_b_bridge_fresh_s1_20260706_003/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/result_info.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_readback_render_inventory_20260706.json`

- [x] **Step 1: Inspect metric trace for object/readback fields**

Run:

```bash
python - <<'PY'
import json, pathlib
trace_path = pathlib.Path('docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_20260706/metric_trace.jsonl')
keys = set()
last_obs = None
for line in trace_path.read_text().splitlines():
    event = json.loads(line)
    packet = (event.get('obs') or {}).get('0') if isinstance(event.get('obs'), dict) else None
    obs = packet.get('obs') if isinstance(packet, dict) else None
    if isinstance(obs, dict):
        keys.update(obs.keys())
        last_obs = obs
print(sorted(keys))
if last_obs:
    for key in sorted(last_obs):
        if any(token in key.lower() for token in ('joint', 'door', 'object', 'metric', 'state')):
            print(key, str(last_obs[key])[:300])
PY
```

Expected: either door/object/readback fields are present and can be summarized, or the inventory records them as missing.

- [x] **Step 2: Inspect official metric code and config**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
sed -n '1,180p' genmanip/extensions/metrics/default/check_joint_angle.py
sed -n '1,130p' configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
```

Expected: identify the exact metric inputs: articulation object uid, joint name, angle range, and `succ_cnts`.

- [x] **Step 3: Write inventory manifest**

Create a JSON manifest with:

```json
{
  "status": "PASS_S2_INVENTORY_READBACK_AVAILABLE"
}
```

or:

```json
{
  "status": "BLOCKED_S2_INVENTORY_READBACK_RENDER_MISSING_NO_NEW_LIVE_RELEASE"
}
```

Include exact artifact paths, available fields, missing fields, and whether a new S2 instrumented run is required.

## Task 2: S2 Claim Review

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_claim_review_20260706.json`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: Decide S2 status**

If Task 1 finds same-run door joint readback, metric input evidence, and render/snapshot:

```text
S2_PASS_ROUTE_B_BRIDGED_EXPERT_REPLAY_READBACK_RENDER_CLOSED
```

If Task 1 finds score artifacts but no readback/render:

```text
S2_BLOCKED_READBACK_RENDER_EVIDENCE_GAP_NO_NEW_LIVE_RELEASE
```

- [x] **Step 2: Update product language**

If S2 passes, say:

```text
M1 已过，S2 也证明 expert action 通过正式控制接口改变了门，并且评分器读到了有效 door joint state。
```

If S2 is blocked, say:

```text
M1 已过，已经有 official score=1.0 的候选证据；但 S2/M3 还缺 door joint readback / render/snapshot，所以不能说 Expert Oracle Score complete。
```

## Verification

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_readback_render_inventory_20260706.json >/tmp/s2_inventory.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_claim_review_20260706.json >/tmp/s2_claim_review.json.ok
git diff --check -- \
  docs/superpowers/plans/2026-07-06-eos2-s2-readback-render-closure.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_readback_render_inventory_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_claim_review_20260706.json \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md
```

Expected: all commands exit 0.

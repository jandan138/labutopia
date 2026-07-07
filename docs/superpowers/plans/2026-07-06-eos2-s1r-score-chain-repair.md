# EOS2 S1R Score Chain Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the S1 formal score-chain contract without blind live retries, then decide whether EOS-2 can proceed to S2 expert scoring or must stop at a specific route blocker.

**Architecture:** S1R is a zero-live repair and review layer between S1 and S2. It fixes runner artifact collection first, defines the `metric_score` completeness policy second, and classifies step0 early finalization third. Only after those are closed may a fresh S1 smoke be released, with at most one live attempt.

**Tech Stack:** LabUtopia evidence manifests, GenManip `score_capable_oracle_runner.py`, fake-client pytest tests, EBench `result_info.json`, `action_log.jsonl`, `metric_trace.jsonl`, `python -m json.tool`, `git diff --check`.

---

## Current Evidence

S0 is complete. The frozen expert action source has 905 contiguous 9D `joint_position` actions:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json
sha256=e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f
```

S1 attempt1 failed before reset/action because the server rejected an absolute config path. S1 attempt2 fixed that and produced real artifacts, but did not pass S1:

```text
run_id=eos2_s1_formal_score_chain_smoke_20260706_002
runner_exit_code=1
summary_classification=FAILED_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT
actual result_info.json score=0.0 success_rate=0 metric_score=[]
action_log_count=1
metric_trace_events=start_job,reset,step_chunk
server warning=Invalid robot state detected at step 0
max reset-to-first-action joint delta=2.734214574098587 rad
```

The authoritative attempt2 result is:

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results/ebench/eos2_s1_formal_score_chain_smoke_20260706_002/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/result_info.json
sha256=b005fa356ef42cd74fa568b8c43c0bc80e9d6e30b4e3160fdfce2b89e1b9a964
```

S1 live budget is consumed. S1R-A is complete. S1R-B review found that attempt2's
`metric_score=[]` artifact is a minimal fallback result, not a complete recorder
finalize artifact, so no waiver is created. S1R-B2 full finalize lifecycle no-live
code checkpoint is now complete. S1R-C has attributed step0 invalid state to a
reset/action contract mismatch and selected Route B bounded bridge. S1R-D release
review is now complete and releases exactly one Route B fresh S1 smoke. The released
action source prepends 14 provenance-separated bridge actions to the unchanged
905-action S0 frozen expert replay, producing a 919-action 9D `joint_position`
source with sha256 `fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`.
The released fresh S1 has now passed M1: the valid runner invocation exited 0 with
`PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT`, executed 578 steps, wrote canonical
`result_info.json`, and recorded `score=1.0`, `success_rate=1`, and
`metric_score=[[[1.0]]]`. The first attempted runner invocation in the same evidence
directory exited 1 because a background server wrapper had already exited before
health check; it produced no start_job/reset/action/result artifacts and is not the
score-chain result.

## Decision Boundaries

M1 / S1 is "runner chain runs": runner exit 0, `summary=PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT`, authoritative `result_info.json`, same-run `action_log.jsonl`, same-run `metric_trace.jsonl`, and the `metric_score` policy is closed. Score may still be 0.

M3 is "single-episode Expert Oracle Score works": at least one expert/oracle route produces a valid nonzero official `result_info.json score` with same-run action log, metric trace, and readback/render evidence.

M4 is "workflow can expand": 3-5 episodes/seeds majority pass a predeclared threshold and failures are classified.

No-go statements are scoped:

```text
S1R-D failure -> runner / evaluator lifecycle blocker
S2 evidence gap after M1 -> readback/render/metric-input review, not a new S1 retry
S2 failure after contract checks -> current Franka/native frozen replay route blocker
S3 bounded failure -> current Lift2 retarget route blocker
```

None of these is a LabUtopia-to-EBench project-wide no-go without a separate review.

### Task 1: Freeze Attempt2 Result Evidence

**Files:**
- Modify: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_attempt2_result_20260706.json`
- Modify: `docs/labutopia_lab_poc/evidence_manifests/README.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`

- [ ] **Step 1: Verify attempt2 artifact hashes**

Run:

```bash
sha256sum \
  /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results/ebench/eos2_s1_formal_score_chain_smoke_20260706_002/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/result_info.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_smoke_20260706_attempt2_config_path_repair/client_results/ebench/eos2_s1_formal_score_chain_smoke_20260706_002/ebench/labutopia_lab_poc/franka_poc/level1_open_door/episode_result.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_smoke_20260706_attempt2_config_path_repair/client_results/ebench/eos2_s1_formal_score_chain_smoke_20260706_002/ebench/labutopia_lab_poc/franka_poc/level1_open_door/000/result.json
```

Expected:

```text
b005fa356ef42cd74fa568b8c43c0bc80e9d6e30b4e3160fdfce2b89e1b9a964  .../result_info.json
a7a6241141a1d88130701ea080f8dcb3e5e8ad1bdb8d1f0de033025870d581ff  .../episode_result.json
96e8e9792a1d847fb8f72b145eb5758cab1536d4b6e541c98f1e1a8039dfde8c  .../result.json
```

- [ ] **Step 2: Verify early-done evidence**

Run:

```bash
python - <<'PY'
import json, pathlib
base = pathlib.Path('docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_smoke_20260706_attempt2_config_path_repair')
metric = [json.loads(line) for line in (base / 'metric_trace.jsonl').read_text().splitlines()]
action = json.loads((base / 'action_log.jsonl').read_text().splitlines()[0])
reset = metric[1]['obs']['0']['obs']['state.joints']
target = action['action']['action'][:7]
print(max(abs(t - r) for r, t in zip(reset, target)))
print([event.get('event') for event in metric])
PY
```

Expected:

```text
2.734214574098587
['start_job', 'reset', 'step_chunk']
```

- [ ] **Step 3: Validate JSON**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_attempt2_result_20260706.json >/tmp/s1_attempt2.json.ok
```

Expected: exit code 0.

### Task 2: S1R-A Result Locator Contract Repair

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/score_capable_oracle_runner.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_score_capable_oracle_runner.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_a_result_locator_code_checkpoint_20260706.json`

- [x] **Step 1: Add a failing fake-client test for the duplicated prefix case**

Add this test to `test_score_capable_oracle_runner.py`:

```python
def test_runner_resolves_run_specific_result_base_dir_without_duplicate_prefix(tmp_path):
    run_specific_base = tmp_path / "results" / "ebench" / "run"
    _write_result_info(
        run_specific_base,
        episode_id="task_a/000",
        score=1.0,
        success_rate=1,
    )
    client = FakeScoreClient(
        [
            (
                _final_obs(
                    episode_result={
                        "episode_id": "ebench/run/task_a/000",
                        "score": 1.0,
                        "sr": 1.0,
                    }
                ),
                True,
            )
        ]
    )

    summary = runner.run_score_capable_oracle(
        client,
        config_path=tmp_path / "level1_open_door.yml",
        action_source_path=_write_action_source(tmp_path),
        output_dir=tmp_path / "out",
        result_base_dir=run_specific_base,
        run_id="run",
        worker_id="0",
        expected_action_dim=3,
    )

    assert summary["classification"] == "PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT"
    assert summary["result_info_locator_mode"] == "run_specific_base_dir_compat"
    assert Path(summary["result_info_path"]).exists()
```

- [x] **Step 2: Run the focused test and confirm RED**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. pytest tests/labutopia_poc/test_score_capable_oracle_runner.py::test_runner_resolves_run_specific_result_base_dir_without_duplicate_prefix -q
```

Expected: fail with `result_info_missing` or missing `result_info_locator_mode`.

- [x] **Step 3: Implement deterministic locator mode**

Change `_result_info_path` to return both path and mode. The canonical path remains `result_base_dir / episode_id / result_info.json`. The compatibility path is allowed only when `episode_id` starts with `ebench/<run_id>/` and `result_base_dir` itself ends with `ebench/<run_id>`.

```python
def _result_info_path(
    *,
    result_base_dir: Path,
    episode_result: dict[str, Any],
    explicit_result_info_path: Path | None,
    run_id: str,
) -> tuple[Path, str]:
    if explicit_result_info_path is not None:
        return explicit_result_info_path, "explicit"
    episode_id = str(episode_result["episode_id"])
    canonical = result_base_dir / episode_id / "result_info.json"
    if canonical.exists():
        return canonical, "canonical_result_base_dir"
    prefix = f"ebench/{run_id}/"
    if episode_id.startswith(prefix) and result_base_dir.name == run_id and result_base_dir.parent.name == "ebench":
        compat = result_base_dir / episode_id.removeprefix(prefix) / "result_info.json"
        if compat.exists():
            return compat, "run_specific_base_dir_compat"
    return canonical, "missing"
```

Update the call site to pass `run_id`, write `result_info_locator_mode` into summary, and append the same field to the `score_artifact` metric trace event.

- [x] **Step 4: Run focused and full runner tests**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. pytest tests/labutopia_poc/test_score_capable_oracle_runner.py -q
```

Expected: all tests pass.

Result: `/usr/bin/python3 -m pytest tests/labutopia_poc/test_score_capable_oracle_runner.py -q`
reported `8 passed in 0.02s`. Checkpoint:
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_a_result_locator_code_checkpoint_20260706.json`.

### Task 3: S1R-B `metric_score` Completeness Policy

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_b_metric_score_policy_review_20260706.json`

- [x] **Step 1: Audit current policy**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
rg -n "metric_score|metric_score_empty_waiver_id|result_info" standalone_tools tests
```

Expected: runner rejects empty `metric_score` unless `--metric-score-empty-waiver-id` is supplied.

- [x] **Step 2: Audit writer lifecycle and historical distribution**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
rg -n "metric_score|post_episode_process|_write_minimal_result_info|finalize_payload" genmanip -S
```

Also scan historical `result_info.json` files under `saved/eval_results` and
`docs/labutopia_lab_poc/evidence_manifests`.

Result:

```text
total result_info.json = 79
empty metric_score = 74
non-empty metric_score = 5
empty metric_score with non-null start/end = 0
non-empty metric_score with non-null start/end = 5
attempt2 = score=0.0, success_rate=0, episode_start_time=null, episode_end_time=null, metric_score=[]
```

Interpretation: non-empty `metric_score` corresponds to the full recorder finalize
path. Empty `metric_score` with null start/end corresponds to
`ProgressManager._write_minimal_result_info`.

- [x] **Step 3: Keep default strict; do not create waiver**

No live is allowed for this step. The review manifest states this outcome:

```text
Outcome C: no S1-only waiver is created. Current attempt2 is a minimal fallback artifact and is not accepted as complete M1/S1 evidence. Fresh S1 remains blocked until full finalize lifecycle produces or validates non-empty metric_score.
```

Checkpoint:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_b_metric_score_policy_review_20260706.json
```

- [x] **Step 4: Verify empty metric test still protects S2/M3**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. pytest tests/labutopia_poc/test_score_capable_oracle_runner.py::test_runner_rejects_empty_metric_score_without_reviewed_waiver -q
```

Expected: pass.

Result: `/usr/bin/python3 -m pytest tests/labutopia_poc/test_score_capable_oracle_runner.py::test_runner_rejects_empty_metric_score_without_reviewed_waiver -q`
reported `1 passed in 0.01s`.

### Task 3b: S1R-B2 Full Finalize Lifecycle Repair

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/env.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/isaac_worker_pool.py`
- Test: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_episode_result_completion.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_b2_full_finalize_lifecycle_code_checkpoint_20260706.json`

- [x] **Step 1: Write a failing no-live lifecycle test**

Create a focused unit/fake-client test that proves a terminal score-capable episode
cannot silently degrade to `ProgressManager._write_minimal_result_info` when full
metric finalization is expected. The test should assert:

```python
assert result_info["log_info"]["metric_score"] != []
assert result_info["log_info"]["episode_start_time"] is not None
assert result_info["log_info"]["episode_end_time"] is not None
```

- [x] **Step 2: Run the focused test and confirm RED**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. /usr/bin/python3 -m pytest tests/labutopia_poc/test_episode_result_completion.py -q
```

Expected: the new focused assertion fails before the lifecycle repair.

Result: initial direct `env.py` import test was invalid because it required `curobo`.
The valid RED used a lightweight helper contract and failed with:

```text
AttributeError: module 'genmanip.core.evaluator.episode_result' has no attribute 'should_skip_post_episode_process'
```

- [x] **Step 3: Implement one lifecycle repair**

Repair the root cause proven by the test. Current evidence points to this
sequence: invalid-state termination sets `EvaluatorEnv.done=True`, then
`post_episode_process()` returns `None` because it exits early on `self.done`,
which prevents `finalize_payload` and forces the minimal fallback writer.

The repair must either:

```text
A. allow post_episode_process to finalize a terminal episode exactly once, including metric_score; or
B. explicitly classify terminal invalid-state episodes as incomplete and prevent them from being accepted as complete score artifacts.
```

Do not add a metric-score waiver as the repair.

Implemented:

```text
genmanip.core.evaluator.episode_result.should_skip_post_episode_process
IsaacEvalEnvRay.post_episode_process now skips done episodes only when no recorder remains.
```

- [x] **Step 4: Run focused and adjacent tests**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. /usr/bin/python3 -m pytest \
  tests/labutopia_poc/test_episode_result_completion.py \
  tests/labutopia_poc/test_score_capable_oracle_runner.py \
  -q
```

Expected: all tests pass.

Result:

```text
focused skip-policy tests: 2 passed in 0.02s
episode_result + score_capable_runner tests: 15 passed in 0.04s
py_compile episode_result.py env.py: exit 0
```

- [x] **Step 5: Register checkpoint**

Create the checkpoint manifest with test outputs and explicit claim boundaries:

```text
fresh_s1_release_allowed_now=false
metric_score_empty_waiver_created=false
s1_pass=false
```

Checkpoint:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_b2_full_finalize_lifecycle_code_checkpoint_20260706.json
```

### Task 4: S1R-C Step0 Invalid-State Attribution

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_c_step0_invalid_state_attribution_20260706.json`
- Optionally create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_c_step0_invalid_state_attribution/`

- [x] **Step 1: Compute reset-to-first-action delta**

Run the script from Task 1 Step 2.

Expected max absolute delta:

```text
2.734214574098587 rad
```

Observed largest deltas:

```text
joint6 delta=-2.734214574098587 rad
joint4 delta=+2.577224478125572 rad
GenManip arm per-step guard=1.0 rad
```

- [x] **Step 2: Classify the failure**

Write a manifest with this interpretation unless new evidence contradicts it:

```text
The frozen action source is absolute `joint_position` replay. Attempt2 EBench reset joint state does not match the source episode's first target neighborhood. The first replay target jumps joint6 by about -2.73 rad and joint4 by about +2.58 rad, which is consistent with the server's step0 invalid robot state guard. This is a reset/action contract mismatch, not an expert quality result.
```

- [x] **Step 3: Decide the S2 route**

Record one of these decisions:

```text
S2 route A: align EBench reset state to frozen source start state, then replay.
S2 route B: prepend a bounded settle/bridge from EBench reset to frozen source start, but keep provenance separate from the original frozen expert.
S2 route C: close frozen absolute replay route and switch to deterministic object-frame / runtime-planner oracle.
```

No S2 live is allowed until this decision is documented.

Decision:

```text
S2 route B selected: prepend a bounded settle/bridge from EBench reset to the frozen source start neighborhood, while keeping bridge provenance separate from the original frozen expert.
```

Checkpoint:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_c_step0_invalid_state_attribution_20260706.json
```

### Task 5: S1R-D Fresh S1 Release Review

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706.json`

- [x] **Step 1: Check prerequisites**

The release review may only be written if these exist and pass:

```text
S1R-A result locator code checkpoint
S1R-B metric_score policy review
S1R-B2 full finalize lifecycle repair/checkpoint
S1R-C step0 invalid-state attribution
```

Result: all prerequisite manifests exist. S1R-A, S1R-B, S1R-B2, and S1R-C are closed enough
to release one Route B fresh S1. S1R-B did not create an empty `metric_score` waiver.

- [x] **Step 2: Build and freeze the Route B bridge source**

The Route B bridge artifact is:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706/bridged_action_source/action_source.jsonl
```

Observed bridge facts:

```text
bridge_action_count=14
frozen_action_count=905
bridged_action_count=919
first_frozen_step_index_after_bridge=14
max_reset_to_first_target_delta=2.734214574098587rad
max_bridge_step_delta_observed=0.19530104100704193rad
invalid_guard_limit=1.0rad
bridged_action_source_sha256=fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a
freeze_validation=PASS_SCORE_ORACLE_ACTION_SOURCE_FREEZE
```

The first 14 actions are `s1r_route_b_settle_bridge`; the original frozen expert replay
starts at bridged step 14 and the original S0 sha256 remains
`e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f`.

- [x] **Step 3: Write the single allowed command**

The command must use the canonical result root:

```bash
--result-base-dir /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results
```

It must not use:

```bash
--result-base-dir /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results/ebench/<run_id>
```

Release review checkpoint:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706.json
```

The released fresh S1 run is:

```text
run_id=eos2_s1r_d_route_b_bridge_fresh_s1_20260706_003
port=18132
config_path=ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
result_base_dir=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results
metric_score_empty_waiver_id=null
```

- [x] **Step 4: Define pass/fail**

PASS:

```text
runner_exit_code=0
summary_classification=PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT
authoritative result_info.json exists
same-run action_log.jsonl exists
same-run metric_trace.jsonl contains score_artifact
metric_score policy satisfied
no unexplained early done
```

FAIL:

```text
Any artifact contract failure after S1R-A/B/C closes -> stop oracle scoring and classify runner/evaluator lifecycle blocker.
```

Additional Route B stop conditions:

```text
invalid before bridged step 14 -> S1R_D_ROUTE_B_BRIDGE_CONTRACT_BLOCKER
invalid after bridged step 14 -> stop blind retry and open S2 frozen replay route repair/review
metric_score still empty -> S1R_D_SCORE_ARTIFACT_LIFECYCLE_BLOCKER
missing result_info.json -> S1R_D_RUNNER_EVALUATOR_LIFECYCLE_BLOCKER
```

## Verification

Run from LabUtopia after documentation changes:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_attempt2_result_20260706.json >/tmp/s1_attempt2.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_result_locator_metric_score_repair_plan_20260706.json >/tmp/s1r_plan.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706.json >/tmp/s1rd_release.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json >/tmp/s1rd_result.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706/bridged_action_source/action_source_bridge_manifest.json >/tmp/s1rd_bridge.json.ok
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706/bridged_action_source_freeze_validation/action_source_manifest.json >/tmp/s1rd_bridge_freeze.json.ok
git diff --check -- \
  docs/superpowers/plans/2026-07-06-eos2-s1r-score-chain-repair.md \
  docs/superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_attempt2_result_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_result_locator_metric_score_repair_plan_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706.json \
  docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json \
  docs/superpowers/plans/2026-07-06-eos2-s2-readback-render-closure.md \
  docs/labutopia_lab_poc/evidence_manifests/README.md \
  docs/labutopia_lab_poc/aan_consumer_handoff.md \
  docs/labutopia_lab_poc/expert_oracle_score_plan.md
```

Expected: all commands exit 0.

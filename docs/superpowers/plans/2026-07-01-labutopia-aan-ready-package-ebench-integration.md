# LabUtopia AAN-Ready Package EBench Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consume the ConvertAsset DryingBox AAN-ready package in the LabUtopia / EBench lane, prove it can enter `level1_open_door` as a task asset, and report the result without overstating official leaderboard or model-success claims.

**Architecture:** ConvertAsset remains the producer of asset-package closure: USD dependency closure, material closure, physics/articulation evidence, runtime smoke, and benchmark task files. LabUtopia / GenManip becomes the consumer: it validates the AAN manifest, mounts the package into the task root, runs EBench-style reset/step/metric/logging smoke, and publishes PM-readable evidence. Any USD / MDL / articulation defect found during consumption must go back to ConvertAsset AAN rather than being patched locally in LabUtopia.

**Tech Stack:** Python 3.10, JSON/YAML manifests, LabUtopia docs, GenManip / EBench task package layout, ConvertAsset `asset_application_normalizer.v1`, Isaac Sim 4.1 runtime evidence, `pytest`, `gmp submit/eval/status`, static HTML weekly report.

---

## Product Summary

大计划名：**LabUtopia AAN-Ready Package 接入 EBench 计划**。

通俗解释：ConvertAsset 已经把 DryingBox 做成“合格资产包”；LabUtopia / GenManip 这边已经把这个合格资产包装进 EBench / GenManip 的真实任务，并证明它在任务里能 reset、step、出图、产出 metric 和日志。PM/weekly HTML 已发布这条证据，no-local-repair guard 也已在位。Stage 6 已把同一套 consumer 流程复制到 `MuffleFurnace` 和 `Beaker_01`：两个资产都完成 Stage 1-4a，并且都完成 generic Stage 4b live smoke。因此六阶段的 AAN consumer replication hardening 已经 `PASS`；后续增强是规划 `task/evaluator.yaml` 的 semantic evaluator 执行，以及处理材质 warning / visual parity 这类更强声明。

这不是 official leaderboard score，也不是模型已经会开门。它证明的是：资产包可以被 EBench 消费，且任务运行链路可以被证据化检查。

Six stages:

| Stage | Product alias | Engineering name | Product meaning | Current status / latest evidence date |
|---|---|---|---|---|
| 1 | 收货锁定 | **AAN package intake** | 固定收货对象，确认消费的是哪一个 ConvertAsset package。 | **Done**: retained package path, manifest path, manifest hash, file count, and package digest are recorded. |
| 2 | 验货准入 | **Consumer manifest check** | 收货验货，确认这个 package 符合 LabUtopia / EBench consumer 的准入条件。 | **Done**: schema, target runtime, target benchmark, gates, entrypoints, dependency closure, blockers, and waivers pass consumer check. |
| 3 | 挂进任务目录 | **Task-root wiring and dry-run composition** | 把资产包挂到 GenManip / EBench task asset root，并确认 USD 和 task files 能解析。 | **Done**: package is mounted by symlink; `asset.usd`, task files, and all required prims resolve. |
| 4 | 跑本地任务链路 | **AAN runtime adapter and live eval smoke** | 先确认 live `level1_open_door` 真正使用 AAN package，而不是旧 overlay；再跑 reset / step / render / metric / logging。 | **Done / DryingBox Stage 4b PASS**: fresh `run_id=labutopia_aan_lift2_stage4b_20260701_085521` 通过本地 EBench / GenManip live smoke。 |
| 5 | 产出 PM 证据 | **PM evidence gate** | 把 Stage 4b live smoke、AAN render、claim boundary 写到周报 HTML，产品能看懂。 | **Done**: `reports/2026-06-15-labutopia-weekly/index.html#aan-handoff` 已发布 Stage 4b PASS 证据和 forbidden claims。 |
| 6 | 防偷修包并复制验证 | **Regression and replication hardening** | 固化 no-local-repair guard，并把同一套收货、验货、挂载、runtime adapter preflight / smoke 流程复制到更多 rigid / articulated USD assets；复制验证不等于完整 runtime / policy 评测成功。 | **PASS; follow-ups open**: DryingBox no-local-repair PASS; `MuffleFurnace` and `Beaker_01` Stage 1-4b generic smoke PASS. |

DryingBox consumer integration is internally reportable because Stages 1-5 pass. Stage 6 is a hardening and replication phase. It now shows that the intake/check/mount/no-local-repair/runtime-adapter workflow is not DryingBox-only, and that both a non-DryingBox articulated asset and a rigid transparent prop can pass generic Stage 4b live smoke. It still does not prove semantic task success, official leaderboard score, or full visual material parity.

Stage 4 is intentionally split into two substeps while still counting as one of the six stages:

| Substep | Meaning | Current status |
|---|---|---|
| Stage 4a | Runtime adapter / preflight: create the AAN wrapper and prove it points at the mounted AAN package, not the old overlay. | Done. |
| Stage 4b | Live eval smoke: launch the server/client path and prove reset, step, render, metric, and logging with a fresh AAN run id. | PASS for DryingBox, `MuffleFurnace`, and `Beaker_01` generic smoke. |

DryingBox Stage 4b PASS allows the wording "DryingBox AAN package passed local EBench / GenManip live eval smoke." `MuffleFurnace` and `Beaker_01` Stage 4b PASS allow the narrower wording "replicated AAN packages passed generic local smoke for reset / step / render / metric / logging / result_info." Neither wording allows official leaderboard, policy-success, semantic-task-success, or full visual-material-parity claims.

## Current Execution Status / Latest Evidence Date

Latest evidence date: 2026-07-02. The 2026-07-01 rows describe the original retained
package and replication hardening; the AAN-11 consumer rerun and runtime bootstrap
runbook are 2026-07-02 evidence.

Multi-angle review converged on one important boundary: **the AAN package path must not reuse the old `lift2_candidate` evidence silently**.

Why this matters:

- The historical `lift2_candidate` config still points at the old LabUtopia composite scene:

  ```text
  scene_usds/labutopia/level1_poc/lab_001/scene
  ```

- The newly consumed AAN package is mounted at:

  ```text
  /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets/labutopia_aan_packages/dryingbox_01_overlay
  ```

- GenManip `Scene` currently opens scene files as:

  ```text
  ${ASSETS_DIR}/${usd_name}.usda
  ```

  but the AAN package entrypoint is `asset.usd`.

Therefore Stage 4 first creates a small AAN runtime adapter. The selected route is an **AAN-specific `.usda wrapper`** under the composite asset root that references the mounted `asset.usd`. This is preferred over a loader `.usd` fallback because the wrapper keeps runtime behavior explicit, avoids broad path-resolution changes, and avoids mutating the retained ConvertAsset package.

Evidence lanes must stay separate:

| Evidence lane | What it proves | Current boundary |
|---|---|---|
| Historical `LabUtopia hand-built overlay / Lift2 Stage 7` | The old overlay passed a local official-baseline-style Lift2 contract. | It is not AAN package live eval evidence and still has historical material-boundary wording. |
| New `ConvertAsset AAN package / EBench consumer stages` | The retained AAN package is received, checked, mounted, adapted to an AAN-specific runtime scene, then run through AAN-specific live eval smoke and published in the weekly HTML. | Stage 1-5 are done for DryingBox; Stage 6 has replicated Stage 1-4b on `MuffleFurnace` and `Beaker_01`; both generic Stage 4b live smoke runs are PASS. AAN evaluator dispatch is a separate semantic-success follow-up. |

Allowed current PM wording:

```text
Stage 1-4b 已完成：DryingBox AAN-ready package 已经在 LabUtopia / GenManip consumer 侧完成收货、验货、task-root 挂载、AAN runtime wrapper 预检，并用 fresh `run_id=labutopia_aan_lift2_stage4b_20260701_085521` 跑通本地 EBench / GenManip live smoke。wrapper 确认指向 mounted AAN package，package digest 在 Stage 4a 重新计算且与 Stage 1/3 一致，Stage 4b 记录 `legacy_overlay_used=false`，旧 overlay 没有被复用。
```

Forbidden current PM wording:

```text
official EBench live eval / leaderboard 已完成。
official leaderboard score 已完成。
模型已经能开门。
任意资产，包括 deformable / liquid，都已经可评。
full visual material parity 已证明。
```

## Current Producer Evidence

ConvertAsset retained package:

```text
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/
```

Consumer-facing files:

```text
dryingbox_runtime_ready_manifest.json
package/asset.usd
package/task/task_config.yaml
package/task/required_prims.yaml
package/task/evaluator.yaml
package/evidence/runtime_smoke/report.json
package/evidence/runtime_smoke/render.png
```

Observed AAN status in this review:

```text
schema_version=asset_application_normalizer.v1
asset_id=DryingBox_01_overlay
task_id=Lift2.DryingBox
overall_status=pass
target_runtime_profile=isaac41
target_benchmark_profile=ebench-lift2
blocked_reasons_len=0
waivers_len=0
```

ConvertAsset verification already run:

```bash
cd /cpfs/user/zhuzihou/dev/ConvertAsset
python -m pytest tests/test_asset_application_normalizer_cli.py \
  tests/test_asset_application_normalizer_pm_and_mjcf.py -q
```

Observed result:

```text
29 passed
```

## File Structure

Planned LabUtopia-side files:

```text
docs/labutopia_lab_poc/aan_consumer_handoff.md
docs/labutopia_lab_poc/aan_runtime_environment_bootstrap.md
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_consumer_check_YYYYMMDD_HHMM.json
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_task_mount_YYYYMMDD_HHMM.json
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_adapter_YYYYMMDD_HHMM.json
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_YYYYMMDD_HHMM.json
docs/superpowers/plans/2026-07-01-labutopia-aan-ready-package-ebench-integration.md
reports/2026-06-15-labutopia-weekly/index.html
```

Planned GenManip-side integration artifacts, produced outside this LabUtopia repo:

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/standalone_tools/labutopia_poc/aan_consumer_check.py
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/standalone_tools/labutopia_poc/mount_aan_package.py
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/standalone_tools/labutopia_poc/aan_runtime_smoke.py
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/tests/labutopia_poc/test_aan_consumer_check.py
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/tests/labutopia_poc/test_aan_package_mount.py
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/tests/labutopia_poc/test_aan_no_local_repair.py
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/docs/labutopia_lab_poc/evidence_manifests/
/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/
```

Known historical LabUtopia POC tooling currently exists in:

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/
```

The active GenManip main checkout currently does not include `standalone_tools/labutopia_poc`.
Before implementing this plan, create a fresh GenManip worktree/branch such as
`labutopia-aan-consumer` from the stage5 tool surface, or port the required POC tools
into the active GenManip branch.

LabUtopia should not create a second USD material or articulation repair tool. The LabUtopia repo stores consumer docs and PM evidence; runtime consumer scripts belong in GenManip.

## Stage 1: AAN Package Intake

**Product meaning:** 固定收货对象。确认我们消费的是哪一个 ConvertAsset package，而不是临时目录或口头状态。

**Status on 2026-07-01:** Done.

Evidence:

```text
GenManip branch: labutopia-aan-consumer
Commit: 5161227 feat: add AAN consumer package check
Evidence: docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_package_intake_20260701_0719.json
Package file count: 30
Package tree digest: 6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936
Source manifest SHA256: d9c8858203b8f26c2b338b05d70c005e8b95bac3fa2ab85a6b136cc4040d3424
```

**Inputs:**

```text
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/dryingbox_runtime_ready_manifest.json
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package/
```

**Required record:**

- retained package root
- retained manifest path
- source manifest SHA256
- package directory file count
- package directory hash summary
- package owner: ConvertAsset
- consumer owner: GenManip / LabUtopia POC

**Implementation steps:**

- [x] Record the exact package root and manifest path in a JSON evidence file.

  Target output:

  ```text
  docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_package_intake_YYYYMMDD_HHMM.json
  ```

- [x] Record whether the package is consumed read-only by symlink or copied into a generated mount namespace.

- [x] Do not edit files under the ConvertAsset retained package.

**Pass condition:**

The package identity is frozen and can be referenced by later stages.

**Forbidden claim:**

Do not say the package is consumer-ready at Stage 1. Stage 1 only freezes which package is being checked.

## Stage 2: Consumer Manifest Check

**Product meaning:** 收货验货。确认 ConvertAsset 交来的不是半成品，而是 LabUtopia 可以消费的 AAN-ready package。

**Status on 2026-07-01:** Done.

Evidence:

```text
GenManip branch: labutopia-aan-consumer
Commits:
  5161227 feat: add AAN consumer package check
  72ca5e0 fix: block closure-level AAN dependencies
Evidence: docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_consumer_check_20260701_0000.json
aan_consumer_manifest_ready=true
aan_package_mount_allowed=true
local_usd_repair_allowed=false
blockers=[]
```

**Required checks:**

- `schema_version == "asset_application_normalizer.v1"`
- `target.target_runtime_profile == "isaac41"`
- `target.target_benchmark_profile == "ebench-lift2"`
- `overall_status == "pass"`
- `usd_closure`, `material_closure`, `physics_static`, producer-side `runtime_smoke`, and `benchmark_contract` gates are all `pass`
- `blocked_reasons` is empty
- `waivers` is empty, or every waiver is explicitly accepted downstream
- `entrypoints.root_usd`, `entrypoints.task_config`, `entrypoints.required_prims`, and `entrypoints.metric_evaluator` resolve inside the package

**Implementation steps:**

- [x] Create or run a strict consumer-check script in the GenManip LabUtopia POC integration layer.

  Suggested command shape:

  ```bash
  cd /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
  python standalone_tools/labutopia_poc/aan_consumer_check.py \
    --package-dir /cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package \
    --manifest /cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/dryingbox_runtime_ready_manifest.json \
    --json-out docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_consumer_check_20260701_0000.json
  ```

- [x] If the script finds a missing entrypoint, wrong target profile, blocker, unresolved dependency, or unaccepted waiver, stop and record a blocker.

- [x] If the script passes, record:

  ```text
  aan_consumer_manifest_ready=true
  aan_package_mount_allowed=true
  local_usd_repair_allowed=false
  ```

**Pass condition:**

GenManip / LabUtopia POC has a JSON evidence file proving the AAN package is allowed to enter the task-mount stage.

**Forbidden claim:**

Do not say EBench task execution passed at Stage 2. Stage 2 only says the package can be consumed.

## Stage 3: Task-Root Wiring And Dry-Run Composition

**Product meaning:** 把合格资产包装进任务系统。资产包不是单独躺在磁盘上，而是成为 `level1_open_door` 可以引用的任务资产。

**Status on 2026-07-01:** Done.

Evidence:

```text
GenManip branch: labutopia-aan-consumer
Commit: 9d042da feat: add AAN task root mount check
Evidence: docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_task_mount_20260701_0000.json
Mounted namespace: labutopia_aan_packages/dryingbox_01_overlay
Mounted mode: symlink
path_resolution_status=mounted
usd_stage_opened=true
all_required_prims_found=true
runtime_execution_passed=false
```

**Inputs:**

```text
package/asset.usd
package/task/task_config.yaml
package/task/required_prims.yaml
package/task/evaluator.yaml
```

**Implementation steps:**

- [x] Mount or copy the AAN package into a namespaced subdirectory under the composite EBench asset root used by the LabUtopia Lift2 lane.

  Current historical composite root:

  ```text
  /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets
  ```

  Target namespace:

  ```text
  labutopia_aan_packages/dryingbox_01_overlay/
  ```

  Preferred mount policy:

  ```text
  symlink package read-only when the runtime accepts symlinks;
  otherwise copy into a generated directory and record source and destination hashes.
  ```

- [x] Preserve AAN task files without hand-editing DryingBox-specific paths.

- [x] Define how GenManip discovers the AAN task files:

  ```text
  task_config_source=labutopia_aan_packages/dryingbox_01_overlay/task/task_config.yaml
  required_prims_source=labutopia_aan_packages/dryingbox_01_overlay/task/required_prims.yaml
  evaluator_source=labutopia_aan_packages/dryingbox_01_overlay/task/evaluator.yaml
  root_usd_source=labutopia_aan_packages/dryingbox_01_overlay/asset.usd
  ```

- [x] If a task path is wrong, rerun ConvertAsset AAN with a corrected task contract instead of patching the YAML locally.

- [x] Add a dry-run composition check that verifies:

  ```text
  mounted root USD opens
  required prim paths exist
  evaluator file exists
  task_config file exists
  no AAN package source file was modified during the check
  ```

- [x] Write a task-mount manifest with:

  ```text
  package_dir
  source_manifest
  mounted_root_usd
  mounted_task_config
  mounted_required_prims
  mounted_evaluator
  symlink_or_copy_mode
  path_resolution_status
  ```

**Pass condition:**

The task root can resolve `asset.usd`, `task_config.yaml`, `required_prims.yaml`, and `evaluator.yaml` from the mounted AAN package, and dry-run composition can find all required prims.

**Forbidden claim:**

Do not say runtime passed at Stage 3. Stage 3 only says task files are mounted and resolvable.

## Stage 4: AAN Runtime Adapter And EBench / GenManip Live Eval Smoke

**Product meaning:** 真跑一次任务链路。证明不是“文件能打开”，而是 reset、step、出图、metric、日志都能走通。

**Status on 2026-07-01:** Stage 4a adapter/preflight done; DryingBox Stage 4b live eval smoke PASS.

Current adapter/preflight evidence:

```text
GenManip branch: labutopia-aan-consumer
Evidence: docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_adapter_20260701_0000.json
status=pass
config_path=ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml
runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_scene
wrapper_references=["../../../labutopia_aan_packages/dryingbox_01_overlay/asset.usd"]
legacy_overlay_used=false
package_tree_digest=6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936
mounted_package_tree_digest=6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936
aan_runtime_adapter_preflight_passed=true
aan_live_eval_smoke_passed=false
```

通俗解释：Stage 4a 已经完成。我们已经给 EBench 准备了一个清楚的入口：
`level1_open_door` 不再指向旧 LabUtopia overlay scene，而是指向一个 AAN wrapper；
这个 wrapper 再引用 mounted AAN package 的 `asset.usd`。同时预检重新扫了一遍 mounted
package 的文件 hash，确认没有拿旧证据冒充新包；也禁止 AAN task 被旧的
`LABUTOPIA_POC_ASSETS_OVERLAY_ROOT` 环境变量带回 legacy overlay。

Stage 4b final manifest 已产出并通过硬门：

```text
GenManip branch: labutopia-aan-consumer
Evidence: docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_20260701_085521.json
Evidence dir: docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan_lift2_stage4b_20260701_085521/
status=PASS
stage=aan_stage4b_live_smoke
run_id=labutopia_aan_lift2_stage4b_20260701_085521
config_path=ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml
runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_scene
legacy_overlay_used=false
submit_exit_code=0
probe_or_eval_exit_code=0
run_id_is_fresh=true
run_id_matches_submit=true
run_id_matches_probe_or_eval=true
run_id_matches_result_info_path=true
reset_passed=true
step_passed=true
render_passed=true
metric_passed=true
logging_passed=true
result_info_exists=true
stdout_exists=true
stderr_exists=true
no_fail_or_blocked_rows=true
score=0.0
success_rate=0
failure_phase=null
failure_owner=null
blockers=[]
```

Result info:

```text
saved/eval_results/ebench/labutopia_aan_lift2_stage4b_20260701_085521/ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door/000/result_info.json
```

Runtime warning boundary:

```text
mdl_compiler_error_count=636
material_warning_claim_boundary=Stage 4b PASS proves runtime reset/step/render/metric/logging, not full visual material parity.
```

通俗解释：Stage 4 已完成。它证明 DryingBox AAN package 已经真的进入
`level1_open_door` 的 LabUtopia / GenManip runtime，且 reset、step、render、metric、
logging 都有证据。`score=0.0` / `success_rate=0` 是 policy/task execution 结果，不是
AAN package runtime 接入失败。636 条 MDL compiler warning 仍必须留在材质/视觉边界里：
它们不阻塞 Stage 4b smoke pass，但阻止我们宣称 full visual material parity。

Two different `runtime_smoke` claims must never be mixed:

| Claim | Owner | Meaning | PM wording |
|---|---|---|---|
| Producer `runtime_smoke=pass` | ConvertAsset AAN | AAN package itself passed producer-side Isaac 4.1 headless load / reset / step / render smoke. | 资产包在 producer 侧 runtime smoke 通过。 |
| Consumer Stage 4b live smoke | LabUtopia / GenManip / EBench consumer | The DryingBox AAN-mounted package passed the actual `level1_open_door` server/client path with reset / step / render / metric / logging evidence. | DryingBox AAN package 在 consumer 侧本地 EBench live smoke 通过。 |

**Scope:**

First target:

```text
level1_open_door
asset_id=DryingBox_01_overlay
task_id=Lift2.DryingBox
```

**Why Stage 4 is a separate stage:**

The current historical `lift2_candidate` config is not enough because it still uses:

```text
usd_name: scene_usds/labutopia/level1_poc/lab_001/scene
```

GenManip runtime opens:

```text
${ASSETS_DIR}/${usd_name}.usda
```

The AAN package entrypoint is:

```text
labutopia_aan_packages/dryingbox_01_overlay/asset.usd
```

So directly running the old `lift2_candidate` would prove the old overlay path again, not the AAN package. Stage 4 must create an explicit AAN runtime wrapper and config before launching live eval.

**Selected adapter design:**

Create a generated wrapper scene under the composite assets root:

```text
scene_usds/labutopia/aan/dryingbox_01_overlay_scene.usda
```

The wrapper must reference or payload:

```text
labutopia_aan_packages/dryingbox_01_overlay/asset.usd
```

Then create an AAN-specific task profile, for example:

```text
configs/tasks/ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml
```

with:

```text
usd_name: scene_usds/labutopia/aan/dryingbox_01_overlay_scene
```

This wrapper is a consumer runtime adapter, not a package repair. It must live outside the retained ConvertAsset package and must be recorded in Stage 4 evidence.

**Stage 4a hard preflight gates:**

- [x] `config_path` is AAN-specific and not the old `lift2_candidate`.
- [x] `ASSETS_DIR` equals the composite assets root used by Stage 3.
- [x] `usd_name` equals the AAN wrapper path and does not equal `scene_usds/labutopia/level1_poc/lab_001/scene`.
- [x] `resolved_runtime_scene` equals `${ASSETS_DIR}/${usd_name}.usda`.
- [x] The wrapper contains a parsed USD reference to `labutopia_aan_packages/dryingbox_01_overlay/asset.usd`; a comment-only string is not accepted.
- [x] The mounted package tree digest is recomputed at Stage 4a and matches the Stage 1 / Stage 3 package digest.
- [x] `mounted_root_usd` is constrained to `${composite_assets_root}/${namespace}/asset.usd`; stale or outside-package paths are blocked.
- [x] AAN task manifest routing ignores the old global overlay env override, so a leftover legacy `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT` cannot silently redirect the AAN config.
- [x] Required prims are read back from the composed AAN wrapper stage.
- [x] Evidence records `legacy_overlay_used=false`.
- [x] No old Stage 5 / Stage 7 run id is reused as AAN Stage 4a adapter evidence.

**Stage 4b hard PASS gates:**

The Stage 4b PASS artifact for this run is:

```text
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_20260701_085521.json
```

Probe-only evidence is not a Stage 4b PASS. A default Franka/Panda `gmp eval` action is not a
valid Lift2/R5a eval command because it sends a 9D action; the AAN Lift2 path must use the
Lift2 action dialect (`-a r5a -g lift2`) or an equivalent 16D action client.

The final Stage 4b manifest must record all of these fields:

```text
stage=aan_stage4b_live_smoke
status=PASS | FAIL | BLOCKED
run_id
run_id_is_fresh=true
run_id_matches_submit=true
run_id_matches_probe_or_eval=true
run_id_matches_result_info_path=true
config_path=ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml
runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_scene
legacy_overlay_used=false
submit_exit_code=0
probe_or_eval_exit_code=0
reset_passed=true
step_passed=true
render_passed=true
metric_passed=true
logging_passed=true
result_info_exists=true
stdout_exists=true
stderr_exists=true
no_fail_or_blocked_rows=true
aan_live_eval_smoke_passed=true
failure_phase=null
failure_owner=null
blockers=[]
```

If any value above is missing or false, the manifest must be `FAIL` or `BLOCKED`, not `PASS`.
For non-pass records, set:

```text
failure_phase=server_start | submit | reset | step | render | metric | logging | client_probe | asset_package
failure_owner=ConvertAsset AAN | GenManip/EBench runtime | LabUtopia consumer | policy/task execution
```

This keeps a useful diagnostic attempt from being accidentally reported as live eval success.

**Implementation steps:**

- [x] Generate the AAN wrapper `.usda` under the composite assets root.

- [x] Add an AAN-specific `level1_open_door` task profile that pins `usd_name` to the wrapper.

- [x] Add a preflight checker that blocks if runtime config and wrapper do not point at the AAN package.

- [x] Start an isolated GenManip / EBench eval server on a non-conflicting port.

  Canonical environment constraints:

  ```text
  PYTHONNOUSERSITE=1
  RAY_ADDRESS=local
  RAY_USAGE_STATS_ENABLED=0
  RAY_TMPDIR=/tmp/gm_aan
  PYTHONPATH=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src:/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
  ```

  Use a short `RAY_TMPDIR`; long paths can fail Ray Unix socket creation.

  Canonical server command:

  ```bash
  cd /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
  PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
  ENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
  WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
  CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
  CUDA11_LIB=/isaac-sim/exts/omni.isaac.ml_archive/pip_prebundle/nvidia/cuda_runtime/lib

  export ACCEPT_EULA=Y
  export OMNI_KIT_ACCEPT_EULA=YES
  export PYTHONNOUSERSITE=1
  export RAY_ADDRESS=local
  export RAY_USAGE_STATS_ENABLED=0
  export RAY_TMPDIR=/tmp/gm_aan
  export PYTHONPATH="$CUROBO_SRC:$WORKTREE"
  export LD_LIBRARY_PATH="$CUDA11_LIB:$ENV/lib/python3.10/site-packages/torch/lib:${LD_LIBRARY_PATH:-}"

  "$PY" ray_eval_server.py \
    --host 127.0.0.1 \
    --port 18189 \
    --run_id "$RUN_ID" \
    --no_save_process \
    --episode_recorder_save_every 0 \
    --reset_timeout 1200 \
    --step_timeout 1200 \
    --load_config_timeout 300
  ```

- [x] Submit the AAN-specific config and record the same `run_id` in `gmp submit`, probe/eval logs,
  artifact paths, `result_info_path`, and the final Stage 4b manifest:

  ```bash
  gmp submit ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml \
    --run_id "$RUN_ID" \
    --host 127.0.0.1 \
    --port 18189
  ```

- [x] Reuse the existing Lift2 probe surface when possible:

  ```text
  standalone_tools/labutopia_poc/lift2_eval_contract_probe.py
  ```

  Canonical probe command:

  ```bash
  cd /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
  EVIDENCE_DIR=docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_${RUN_ID}
  mkdir -p "$EVIDENCE_DIR"
  python standalone_tools/labutopia_poc/lift2_eval_contract_probe.py \
    --live \
    --host 127.0.0.1 \
    --port 18189 \
    --worker-id 0 \
    --run-id "$RUN_ID" \
    --task-name level1_open_door \
    --logging-json "$EVIDENCE_DIR/live_probe_logging.json" \
    --output "$EVIDENCE_DIR/probe.json"
  ```

- [x] Run a full eval or equivalent smoke client with the Lift2/R5a action dialect:

  ```bash
  export PYTHONPATH=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src:$PYTHONPATH
  python -m genmanip_client.cli eval \
    --worker_ids 0 \
    --run_id "$RUN_ID" \
    --host 127.0.0.1 \
    --port 18189 \
    -a r5a \
    -g lift2 \
    -c joint_position \
    --no_save_process \
    --frame_save_interval 0 \
    --chunk_size 1
  ```

- [x] Build the final Stage 4b manifest with:

  ```text
  standalone_tools/labutopia_poc/aan_runtime_smoke.py
  ```

  Observed summary-builder CLI shape:

  ```bash
  cd /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
  python standalone_tools/labutopia_poc/aan_runtime_smoke.py \
    --adapter-record docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_adapter_20260701_0000.json \
    --probe-json docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_${RUN_ID}/probe.json \
    --expected-run-id labutopia_aan_lift2_stage4b_20260701_085521 \
    --submit-exit-code 0 \
    --probe-or-eval-exit-code 0 \
    --runtime-warning-log docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan_lift2_stage4b_20260701_085521/server.stderr.txt \
    --json-out docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_20260701_085521.json
  ```

- [x] Run reset and capture observation schema.

- [x] Run at least one zero or safe action step.

- [x] Confirm image-shaped camera outputs.

- [x] Confirm reward / success / metric fields are present.

- [x] Confirm result path, stdout, stderr, seed, episode id, and worker id are recorded.

- [x] Confirm `result_info.json` exists and can be parsed. A schema probe that resets/steps but
  does not produce `result_info.json` is useful evidence, but it remains Stage 4b `BLOCKED`.

- [x] Write runtime-smoke evidence to:

  ```text
  docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_20260701_085521.json
  ```

**Required evidence fields:**

```text
run_id
command
commands.server
commands.submit
commands.probe
commands.eval_or_smoke_client
config_path
task_name
composite_assets_root
namespace
mounted_root_usd
mounted_root_usd_sha256
package_tree_digest
mounted_package_tree_digest
runtime_usd_name
resolved_runtime_scene
runtime_scene_sha256
wrapper_references
legacy_overlay_used=false
reset_passed
step_passed
render_passed
metric_passed
logging_passed
result_info_exists
stdout_exists
stderr_exists
submit_exit_code
probe_or_eval_exit_code
no_fail_or_blocked_rows
failure_phase
failure_owner
blockers
required_prim_resolution_rows
result_info_path
stdout_path
stderr_path
allowed_claims
forbidden_claims
```

The adapter/preflight record already contains wrapper and digest fields. The runtime-smoke
record must fill the live-eval-only fields with a fresh AAN run.

**Pass condition:**

`level1_open_door` reaches reset, step, render, metric, and logging without `FAIL` or `BLOCKED`;
all Stage 4b hard PASS gates are true; and the final `aan_dryingbox_runtime_smoke_*.json`
has `status=PASS`.

**Forbidden claim:**

Do not say the policy solved the task. A zero-score or failed policy is not an asset/runtime contract failure if reset, step, metric, and logging pass.

**Fresh verification commands for the recorded Stage 4b run:**

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_20260701_085521.json >/tmp/aan_stage4b.json
du -sh docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan_lift2_stage4b_20260701_085521
test -f saved/eval_results/ebench/labutopia_aan_lift2_stage4b_20260701_085521/ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door/000/result_info.json
```

## Stage 5: PM Evidence And Weekly HTML Update

**Product meaning:** 让产品经理看懂“之前差什么、现在补上了什么、还不能吹什么”。

Stage 5 does not make the asset more ready. It publishes Stage 4b evidence and claim
boundaries in a PM-readable form. Stage 5 is complete because
`reports/2026-06-15-labutopia-weekly/index.html#aan-handoff` now links the final
Stage 4b manifest, live artifact paths, diagnostic renders, and forbidden claims.
The 2026-07-02 visual QA update explicitly marks the AAN producer render as
`FAIL/OPEN` for PM-facing visual use: it has red abnormal material and a back/top
camera view, so it is diagnostic evidence only.

**Implementation steps:**

- [x] Update `reports/2026-06-15-labutopia-weekly/index.html` with a new section:

  ```text
  ConvertAsset AAN-ready package handoff
  ```

- [x] Explain the old state:

  ```text
  手工 overlay 可以跑本地 Lift2 contract，但材质仍有 remote dependency waiver 边界。
  ```

- [x] Explain the new state:

  ```text
  AAN package 已经把 dependency、material、physics、articulation where applicable、
  producer Isaac 4.1 runtime_smoke、benchmark contract 都写进 manifest，并且
  DryingBox 当前 overall_status=pass。
  ```

- [x] Add links or file references to:

  ```text
  dryingbox_runtime_ready_manifest.json
  package/evidence/runtime_smoke/render.png
  package/task/required_prims.yaml
  docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_YYYYMMDD_HHMM.json
  docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_${RUN_ID}/
  saved/eval_results/ebench/${RUN_ID}/.../result_info.json
  Stage 4b stdout/stderr paths
  ```

- [x] Label producer and consumer evidence separately:

  ```text
  Producer evidence: ConvertAsset AAN package closure and producer Isaac 4.1 runtime_smoke.
  Consumer evidence: LabUtopia / GenManip Stage 4b EBench live smoke.
  ```

- [x] If the page shows render images, label them as evidence/diagnostic render images unless
  a separate visual-parity study proves full visual parity.

- [x] 2026-07-02 visual QA update: mark the current AAN producer render as
  diagnostic-only problem evidence, not as a showcase image. The known issues are:
  red abnormal material caused by unresolved runtime MDL / texture closure, and a
  back/top automatic smoke camera that does not show the door, handle, or full
  DryingBox shape.

- [x] Preserve the forbidden claims:

  ```text
  official leaderboard score 未完成
  policy/model success 未完成
  arbitrary USD/MJCF/deformable/liquid 未支持
  full visual material parity 未无损证明
  ```

**Pass condition:**

The weekly HTML can explain the AAN handoff to a non-engineering PM, links the final Stage 4b
runtime-smoke manifest and live artifact paths, and preserves forbidden claims without hiding
evidence boundaries.

Browser visual review evidence:

```text
Preview URL: http://127.0.0.1:8025/reports/2026-06-15-labutopia-weekly/index.html#aan-handoff
Screenshots: /tmp/labutopia-aan-stage5-visual/cdp-rerun-desktop.png
             /tmp/labutopia-aan-stage5-visual/cdp-rerun-mobile.png
Audit JSON: /tmp/labutopia-aan-stage5-visual/audit-rerun.json
Checks: no document-level horizontal overflow, no AAN section overflow, 0 broken images,
0 console/network events, required Stage 4b PASS / MDL warning / forbidden-claim text present.
```

## Stage 6: Regression, Boundary, And Replication Hardening

**Product meaning:** 把流程卡住，防止以后又回到“这里手工修资产”的混乱状态；同时把
DryingBox 的接入流程复制到新资产，确认这不是单资产特化。

**Status on 2026-07-01:** Stage 6a no-local-repair guard is done for DryingBox. Cross-asset
replication has advanced through Stage 1-4b for two non-DryingBox AAN packages:
`MuffleFurnace` as an articulated equipment asset and `Beaker_01` as a rigid transparent
prop. GenManip / LabUtopia consumer now has generic AAN lane-local manifest routing and
generic wrapper/task generation for these assets. Stage 4a runtime adapter preflight is
`PASS` for both, and both assets passed generic Stage 4b live smoke with reset / step /
render / metric / logging / `result_info.json` evidence. This satisfies Stage 6
replication acceptance for phase-1 rigid/articulated USD consumer workflow, while
leaving semantic evaluator execution and full visual/material parity as follow-ups.
`task/evaluator.yaml` exists and is checked as package metadata, but GenManip runtime
does not currently auto-import it as an executable metric plugin.

Current Stage 6a evidence:

```text
GenManip branch: labutopia-aan-consumer
Tool: standalone_tools/labutopia_poc/aan_no_local_repair.py
Tests: tests/labutopia_poc/test_aan_no_local_repair.py
Snapshot evidence: docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_no_local_repair_snapshot_20260701_0000.json
Verify evidence: docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_no_local_repair_verify_20260701_0000.json
status=PASS
package_mutation_allowed=false
local_usd_repair_allowed=false
package_digest=6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936
blockers=[]
```

Current Stage 6 replication evidence:

```text
Summary evidence:
docs/labutopia_lab_poc/evidence_manifests/aan_stage6_replication_summary_20260701_1145.json
status=PASS
stage6_minimum_acceptance_status=PASS
highest_common_passed_stage=4b
highest_replicated_stage=4b
stage4a_runtime_adapter_preflight_status=PASS
stage4b_live_smoke_status=PASS
blocker_or_next_action=Stage6 replication hardening PASS. Next follow-ups: standardize the AAN runtime env bootstrap, implement semantic evaluator dispatch for task/evaluator.yaml, and close material-warning/full-visual-parity evidence separately.

MuffleFurnace evidence:
docs/labutopia_lab_poc/evidence_manifests/aan_muffle_furnace_package_intake_20260701_094329.json
docs/labutopia_lab_poc/evidence_manifests/aan_muffle_furnace_consumer_check_20260701_094329.json
docs/labutopia_lab_poc/evidence_manifests/aan_muffle_furnace_task_mount_20260701_094802.json
docs/labutopia_lab_poc/evidence_manifests/aan_muffle_furnace_no_local_repair_verify_20260701_094846.json
docs/labutopia_lab_poc/evidence_manifests/aan_muffle_furnace_runtime_adapter_20260701_102820.json
docs/labutopia_lab_poc/evidence_manifests/aan_muffle_furnace_runtime_smoke_20260701_105508.json
Stage 1-4b status=PASS
stage4b_live_smoke_status=PASS
asset_class=articulated
dynamics_profile=articulated_body
package_digest_after_stage4a=69c49538658892e4faef4265a9dd5049b16e690d3740f5a764b47a5f2b42a233
run_id=labutopia_aan_muf4b_20260701_104829
reset_passed=true
step_passed=true
render_passed=true
metric_passed=true
logging_passed=true
result_info_exists=true
score=0.0
success_rate=0
mdl_compiler_error_count=264

Beaker_01 evidence:
docs/labutopia_lab_poc/evidence_manifests/aan_beaker_01_package_intake_20260701_094343.json
docs/labutopia_lab_poc/evidence_manifests/aan_beaker_01_consumer_check_20260701_094343.json
docs/labutopia_lab_poc/evidence_manifests/aan_beaker_01_task_mount_20260701_094802.json
docs/labutopia_lab_poc/evidence_manifests/aan_beaker_01_no_local_repair_verify_20260701_094846.json
docs/labutopia_lab_poc/evidence_manifests/aan_beaker_01_runtime_adapter_20260701_102820.json
docs/labutopia_lab_poc/evidence_manifests/aan_beaker_01_runtime_smoke_20260701_1135.json
Stage 1-4b status=PASS
stage4b_live_smoke_status=PASS
asset_class=rigid transparent prop
dynamics_profile=rigid_body
package_digest_after_stage4a=b707403b13a7295d0f5385e0c48b1498dc98119f5a728cc2d9d07614c3c87e98
run_id=labutopia_aan_beak4b_envfix_20260701_1135
reset_passed=true
step_passed=true
render_passed=true
metric_passed=true
logging_passed=true
result_info_exists=true
score=0.0
success_rate=0
mdl_compiler_error_count=8
```

Beaker_01 Stage 4b required a runtime environment bootstrap fix, not an asset repair.
The first diagnostic run failed before asset load because worker actors did not inherit
`CUROBO_SRC`; the second got past Python import and exposed missing `PATH` / `LD_LIBRARY_PATH`
for `ninja` and `libcudart.so.11.0`. The final PASS run used the existing
`embodied-eval-os-sim-isaacsim41-genmanip-py310` conda env with:

```text
CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
PATH=$PYENV/bin:$PATH
LD_LIBRARY_PATH=$PYENV/lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin:$PYENV/lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps
```

This bootstrap is a consumer runtime requirement. It does not modify the AAN package,
and no LabUtopia-side USD / MDL / articulation repair was introduced.

Consumer parser fix made during Stage 6:

```text
GenManip file:
standalone_tools/labutopia_poc/mount_aan_package.py

Regression test:
tests/labutopia_poc/test_aan_package_mount.py::test_dry_run_allows_not_applicable_required_prim_roles
```

Why this fix is consumer-side and not local package repair: AAN-07 explicitly treats
`path: "N/A"` as `status: not_applicable`; only non-`N/A` required prims must resolve in
`asset.usd`. The first Stage 3 run incorrectly treated `goal_target: N/A` as a missing
required USD prim. The consumer parser was fixed by TDD to respect `N/A/not_applicable`
without editing any ConvertAsset package file. The later no-local-repair verify records
prove the package digests did not change.

通俗解释：Stage 6a 是“防止偷修包”的闸门。它先给 ConvertAsset retained AAN package
做 hash baseline，再在 consumer 操作后复核 hash。只要 LabUtopia / GenManip 为了跑通
而改了 package 内的 USD / MDL / task files，就会输出 `BLOCKED`，并把 owner 写成
`LabUtopia consumer`；如果 source package 本身有问题，则应回到 ConvertAsset AAN 修包，
而不是在 consumer 侧本地修。

**Multi-agent planning update on 2026-07-01:**

Two independent read-only reviews converged on the same architecture boundary.

Config / task-lane review:

- GenManip can discover a new AAN lane only if it has a lane directory under
  `configs/tasks/ebench/labutopia_lab_poc/<lane_name>/`, an index file named
  `<lane_name>.json`, a task YAML with `evaluation_configs`, and a lane-local
  `assets_manifest.json`.
- `evaluation_configs[0].usd_name` is the runtime authority. GenManip opens
  `${ASSETS_DIR}/${usd_name}.usda`; `assets_manifest.json.runtime_usd_name` is a
  resolver/preflight contract and must match the YAML value.
- The original resolver only special-cased `aan_lift2_candidate`. That gap is now fixed:
  new lanes such as `aan_stage6_muffle_furnace` and `aan_stage6_beaker_01` resolve their
  own lane-local `assets_manifest.json` instead of falling back to `common/assets_manifest.json`.
  This prevents a leftover env override or old overlay manifest from silently redirecting
  generic AAN assets.

Evaluator / success review:

- GenManip runtime success currently flows through
  `generation_config.goal -> MetricsManager -> MetricFactory -> ProgressManager`.
- `task/evaluator.yaml` is not auto-imported by the runtime today. It is validated and
  mounted as AAN package metadata, but there is no generic `entrypoint` plugin dispatch.
- Therefore the nearest Stage 4b replication target is a **generic AAN smoke task**:
  generate a per-asset lane, set `generation_config.goal: []` when no native metric mapping
  exists, then verify reset / step / render / metric-field / logging evidence. This can
  pass Stage 4b smoke with `score=0.0`, but it cannot be reported as task semantic success.
- A true AAN semantic success path requires a later evaluator bridge: either map
  `task/evaluator.yaml` entrypoints into GenManip `MetricFactory`, or implement a controlled
  plugin dispatch layer with explicit sandboxing, imports, and claim boundaries.

**Stage 6 execution record and follow-ups:**

1. Generic manifest resolver: **done**

   ```text
   File: /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/genmanip/core/evaluator/labutopia_assets.py
   Test: /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/tests/labutopia_poc/test_labutopia_assets_override.py
   Goal: resolve configs/tasks/ebench/labutopia_lab_poc/<aan_lane>/assets_manifest.json for any AAN lane, not only aan_lift2_candidate.
   Pass: a lane-local manifest is used, global LABUTOPIA_POC_ASSETS_OVERLAY_ROOT cannot redirect AAN lanes, and missing runtime scenes still fail loudly.
   ```

2. Generic AAN smoke adapter: **done**

   ```text
   File: /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/standalone_tools/labutopia_poc/aan_runtime_adapter.py
   Test: /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer/tests/labutopia_poc/test_aan_runtime_adapter.py
   Goal: generate per-asset wrapper .usda, task YAML, lane index JSON, and assets_manifest.json for MuffleFurnace and Beaker_01.
   Pass: generated lanes do not mention DryingBox paths, wrapper references point to the mounted AAN package, and task YAML / manifest runtime USD names match.
   ```

3. Stage 4a replication preflight: **done**

   ```text
   Output: docs/labutopia_lab_poc/evidence_manifests/aan_muffle_furnace_runtime_adapter_YYYYMMDD_HHMM.json
   Output: docs/labutopia_lab_poc/evidence_manifests/aan_beaker_01_runtime_adapter_YYYYMMDD_HHMM.json
   Goal: prove each non-DryingBox AAN lane points at its own mounted package and not the old overlay.
   Pass: legacy_overlay_used=false, package digest matches Stage 1/3/no-local-repair evidence, non-N/A required prims resolve, and wrapper references are parsed from USD references rather than comments.
   ```

4. Stage 4b generic live smoke: **done**

   ```text
   First target: MuffleFurnace - PASS
   Second target: Beaker_01 - PASS
   Goal: run reset / step / render / metric-field / logging smoke through GenManip / EBench with a fresh run_id.
   Pass: final Stage 4b manifest records PASS only if submit/probe/eval exit codes, result_info, stdout/stderr, run-id consistency, and smoke gates all pass.
   Boundary: score=0.0 is acceptable for smoke; it is not task success.
   ```

5. Semantic evaluator follow-up:

   ```text
   Goal: decide whether AAN task/evaluator.yaml should map to existing MetricFactory metrics or use a new controlled plugin-dispatch layer.
   Pass: MuffleFurnaceDoorEvaluator and TransparentBeakerEvaluator can be represented as runtime metrics with tests, or explicitly marked unsupported with a structured blocker.
   Boundary: do not mix this with Stage 4b smoke; semantic evaluator support is needed for task-success and official-score claims, not for reset/step/render smoke.
   ```

6. PM/report update: **done**

   ```text
   Files:
     docs/labutopia_lab_poc/aan_consumer_handoff.md
     docs/labutopia_lab_poc/evidence_manifests/README.md
     reports/2026-06-15-labutopia-weekly/index.html
   Goal: report the highest stage per asset, distinguish smoke from semantic success, and keep unsupported non-rigid profiles out of ready claims.
   ```

**Phase-1 support boundary:**

AAN consumer Phase 1 targets **USD rigid bodies and articulated bodies** for the Isaac 4.1 / EBench Lift2 profile. Deformable, cloth, liquid, particle, and granular assets are future non-rigid dynamics profiles. Until solver-specific state, material/physics semantics, reset/step stability, collision coupling, render/readback, and evaluator gates are implemented, those asset classes must be reported as `unsupported`, `blocked`, or `semantic_gap_report_only`, not `ready`.

Every replicated asset must record a profile block:

```text
asset_class=rigid | articulated | unsupported_non_rigid
runtime_profile=isaac41
benchmark_profile=ebench-lift2
dynamics_profile=rigid_body | articulated_body | unsupported_non_rigid
profile_support_status=supported_phase1 | blocked | unsupported
highest_passed_stage=1 | 2 | 3 | 4a | 4b | 5 | 6
stage4b_live_smoke_status=PASS | FAIL | BLOCKED | NOT_RUN
producer_owner_action=null | required
```

For rigid-only USD assets, `articulation_closure` must be `NOT_APPLICABLE` or `NOT_REQUIRED`,
not forced to `PASS`. For articulated assets, articulation evidence remains required.

**Implementation steps:**

- [x] Add hash-before/hash-after checks that fail if a consumer run mutates AAN package files in place.

- [x] Prefer read-only symlink mounting; if copying is required, treat the copy as generated output and keep source package hashes unchanged.

- [x] Add a check that missing USD / MDL / articulation data produces a structured blocker rather than a local patch.

- [x] Add negative tests:

  ```text
  tests/labutopia_poc/test_aan_consumer_check.py
  tests/labutopia_poc/test_aan_package_mount.py
  tests/labutopia_poc/test_aan_no_local_repair.py
  ```

- [ ] Re-run existing LabUtopia / GenManip POC verification after the AAN consumer path is mounted:

  ```bash
  cd /root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
  python -m pytest tests/labutopia_poc -q
  python standalone_tools/labutopia_poc/validate_task_package.py
  git diff --check
  ```

- [x] Confirm the LabUtopia repo itself stays focused on source docs, consumer handoff, reports, and task semantics.

- [x] Select one additional rigid USD asset: `Beaker_01`.

- [x] Select one additional articulated USD asset: `MuffleFurnace`.

- [x] Use retained ConvertAsset AAN-08 packages + manifests for both assets.

- [x] Run Stage 1 and Stage 2 for both assets.

- [x] Run Stage 3 only after Stage 1 and Stage 2 pass.

- [x] For at least one additional rigid or articulated asset, produce a Stage 4b record:

  ```text
  stage4b_live_smoke_status=PASS
  ```

  or a structured non-pass record:

  ```text
  stage4b_live_smoke_status=BLOCKED
  failure_phase=<server_start|submit|reset|step|render|metric|logging|client_probe|asset_package>
  failure_owner=<ConvertAsset AAN|GenManip/EBench runtime|LabUtopia consumer|policy/task execution>
  blocker_or_next_action=<specific action>
  ```

  If replication stops at Stage 1 or Stage 2, report only `intake reusable` or
  `manifest-check reusable`, not full consumer workflow reusable.

- [x] Add PM-facing summary rows:

  ```text
  asset_id
  asset_class
  runtime_profile
  benchmark_profile
  dynamics_profile
  AAN status
  consumer mount status
  runtime smoke status
  highest_passed_stage
  stage4b_live_smoke_status
  profile_support_status
  producer_owner_action
  blocker or next action
  ```

**Pass condition:**

There is no new LabUtopia-side USD / MDL / articulation repair path. Asset defects remain
ConvertAsset-owned. At least two assets beyond DryingBox have structured consumer evidence,
and at least one replicated asset has Stage 4b `PASS` or `BLOCKED` evidence with explicit
failure owner. If replication stops before Stage 4b live smoke, the allowed claim is limited
to the highest replicated stage.

Current pass-condition status: Stage 6 replication hardening PASS, with follow-ups open.
Two assets beyond DryingBox have structured Stage 1-4b consumer evidence and
no-local-repair evidence. Generic AAN task lane / manifest routing is implemented and
preflighted, so the old Stage 4a routing gap is cleared. `MuffleFurnace` and `Beaker_01`
both have Stage 4b generic live-smoke `PASS` evidence with explicit reset / step /
render / metric / logging / result_info gates. The allowed claim is consumer workflow
replication for phase-1 rigid/articulated USD assets, not semantic task success.

## Claim Boundary

Allowed after Stage 1:

```text
The exact retained ConvertAsset AAN package and manifest have been locked as the object under review.
```

Allowed after Stage 2:

```text
The AAN manifest passed consumer checks and the package is allowed to enter task-root mounting.
```

Allowed after Stage 3:

```text
The AAN package is consumer wired: task root resolves asset.usd, task_config.yaml, required_prims.yaml, evaluator.yaml, and all required prims in dry-run composition.
```

Allowed after Stage 4a:

```text
DryingBox AAN package has an AAN-specific runtime wrapper and task profile that point to the mounted AAN package rather than the old LabUtopia overlay.
```

Allowed after Stage 4b PASS:

```text
DryingBox AAN package can enter the LabUtopia `level1_open_door` EBench / GenManip runtime path and produce reset / step / render / metric / logging evidence.
```

Allowed after Stage 6 PASS:

```text
The AAN consumer workflow has been replicated through Stage 4b for additional rigid/articulated USD assets, with structured evidence. `MuffleFurnace` and `Beaker_01` have passed generic Stage 4b live smoke. Stage 6 replication acceptance is satisfied, but semantic evaluator execution, official score, full visual/material parity, and all-asset readiness are not proven.
```

Still forbidden unless separately proven:

```text
official EBench leaderboard score is complete
official EBench reproduction is complete
model or policy success is proven
arbitrary USD / MJCF / URDF assets are supported
deformable / liquid / cloth / particle assets are supported
full visual material parity is proven
LabUtopia should locally repair USD / MDL / articulation defects
```

## Failure Ownership Rules

If Stage 4b live eval fails, triage by owner before changing code:

Every Stage 4b non-PASS manifest must include:

```text
failure_phase=server_start | submit | reset | step | render | metric | logging | client_probe | asset_package
failure_owner=ConvertAsset AAN | GenManip/EBench runtime | LabUtopia consumer | policy/task execution
blocker_or_next_action=<specific next action>
```

Without these fields, the record is not PM-reportable except as an incomplete diagnostic.

| Failure type | Owner | Action |
|---|---|---|
| Manifest gate no longer passes; schema/profile/entrypoints mismatch | ConvertAsset AAN | Rebuild or fix AAN package; do not patch locally. |
| `asset.usd` cannot open or packaged required prims are missing | ConvertAsset AAN | Return a structured blocker with missing path and role. |
| Unresolved remote URI, package-escaping path, missing MDL/texture mirror | ConvertAsset AAN | Fix material/dependency closure in producer package. |
| Joint axis/limit/DOF, collision, mass/inertia, reset pose provenance inconsistent with manifest | ConvertAsset AAN with consumer feedback | Record the runtime evidence and update AAN gates. |
| AAN `task_config.yaml`, `required_prims.yaml`, or `evaluator.yaml` points at wrong prims/contracts | ConvertAsset AAN with consumer feedback | Fix benchmark contract in the package. |
| Mount namespace, composite assets root, symlink/copy policy, env injection | GenManip / LabUtopia consumer | Fix consumer mount/runtime adapter. |
| Eval server, worker, queue, port, result path, stdout/stderr logging | GenManip / EBench runtime | Fix runtime operation. |
| Observation/camera/action/reward/success schema mismatch | GenManip / EBench runtime | Fix live contract adapter or task config. |
| `score=0` or `success_rate=0` after reset/step/metric/logging pass | Policy/task execution quality | Not an AAN package failure unless metric reads the wrong AAN contract. |

## Material Wording Rules

Use these three levels consistently:

| Term | Allowed wording | Forbidden upgrade |
|---|---|---|
| `material_closure` | AAN package material evidence is recorded with package-local path/hash or source-preserved evidence. | Do not call this runtime MDL/texture closure or full visual parity. |
| `local mirror` | A specific remote MDL/texture dependency has package-local path/hash evidence. | Do not claim visual identity solely from local mirror. |
| `full visual parity` | Not allowed from current evidence. | Do not say source-native full material closure or full visual material parity is proven. |

2026-07-02 observed DryingBox render issue:

```text
producer_failed_mdl_shade_nodes=10
producer_missing_mdl_modules=41
producer_unresolved_textures=18
producer_payload_scope_material_binding_warnings=84
consumer_mdl_compiler_error_count=636
producer_render_visual_qa=FAIL/OPEN
```

Interpretation:

- Producer `runtime_smoke.status=pass` proves cold load, required prim existence,
  non-empty headless render readback, physics step, and reset smoke.
- It does not prove runtime MDL compiler closure, texture closure, source-native
  material parity, PM showcase camera quality, or full visual material parity.
- The red render should be treated as material-runtime-closure diagnostic evidence.
  The back/top camera should be treated as diagnostic-camera evidence, not a product
  display view.

PM-safe wording:

```text
AAN package material evidence 已记录，部分 remote material dependencies 已按 manifest 做
local mirror/source-preserved evidence；这证明 package 有可追踪的材质来源和依赖证据，
但当前 runtime 仍有 MDL/texture 解析错误和红色异常渲染，因此不代表 source-native
full material closure 或 full visual parity。
```

## 2026-07-02 AAN-11 Consumer Rerun And Fixed Camera Update

The AAN-11 package from ConvertAsset material runtime closure has now been consumed by
the LabUtopia / EBench path. This supersedes the earlier `consumer rerun pending`
state for DryingBox AAN-11.

Durable evidence:

```text
package=/tmp/aan11_real_packages_final/dryingbox_runtime
package_digest_sha256=a859c5a997c77ea9874155070c03879d2cc9ac41e0b4c30e7c8a07719b1fe32e
manifest=docs/labutopia_lab_poc/evidence_manifests/aan11_dryingbox_runtime_smoke_20260702_1803.json
run_id=labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803
runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene
submit_exit_code=0
eval_exit_code=0
reset_observed=true
step_1000_observed=true
score=0.0
success_rate=0
```

Runtime bootstrap lessons:

```text
CUROBO_SRC must be included in PYTHONPATH.
LABUTOPIA_POC_ASSETS_OVERLAY_ROOT must point at saved/assets, whose target is the composite assets root.
The first two diagnostic runs failed before proving anything about the AAN package:
  1. missing curobo import in Ray worker;
  2. fallback to old overlay root, causing an empty wrapper composition.
```

These lessons are now codified as a reusable runbook:

```text
docs/labutopia_lab_poc/aan_runtime_environment_bootstrap.md
```

Fixed native vs AAN front-camera evidence:

```text
weekly_contact_sheet=reports/2026-06-15-labutopia-weekly/assets/aan11-native-vs-aan-fixed-front-contact.png
native_image=reports/2026-06-15-labutopia-weekly/assets/aan11-native-fixed-front.png
aan11_image=reports/2026-06-15-labutopia-weekly/assets/aan11-aan-fixed-front.png
camera=/World/LabUtopiaFixedFrontCamera
position=[-0.21556737, 0.12, 1.36496577]
look_at=[0.72, 0.12, 1.20]
distance=0.95
elevation=10
azimuth=180
resolution=1024x1024
```

Independent visual review result:

```text
overall=WARN
front_view_framing=PASS
pair_comparability=PASS
red_fallback=AAN side has no obvious broad red fallback
remaining_material_differences=native rack red vs AAN rack dark gray/black; control-panel display and buttons sharper on native; side panel and blue door roughness/brightness differ; lower foot red vs black
```

Allowed PM claim:

```text
AAN-11 DryingBox package 已进入 LabUtopia / EBench consumer 并通过本地 live smoke。
固定正面对比图证明 AAN 没有大面积红色 fallback，且门、handle、控制面板和观察窗可比。
```

Forbidden PM claim:

```text
Do not claim official leaderboard readiness, policy success, semantic task success,
arbitrary asset readiness, or full visual/material parity.
The consumer log still has mdlc_compiler_error_count=16 and
relationship_out_of_scope_count=70, so material parity remains a follow-up.
```

## Verification Checklist For This Plan

- [x] `docs/labutopia_lab_poc/aan_consumer_handoff.md` links this plan.
- [x] `docs/superpowers/plans/2026-06-26-labutopia-native-dryingbox-acceptance-stages.md` points to this plan as the continuation.
- [x] Stage 4 is split into 4a adapter/preflight and 4b live smoke while preserving the six-stage plan.
- [x] Stage 4b has one final PASS artifact and hard gates for reset, step, render, metric, logging, result paths, exit codes, and run-id consistency.
- [x] Stage 6 replication is profile-gated and cannot overclaim deformable / liquid / cloth / particle support.
- [x] PM-facing weekly HTML update is done only after Stage 4b live eval smoke PASS evidence exists.
- [x] AAN-11 package entered the LabUtopia / EBench consumer and completed a fresh rerun.
- [x] AAN runtime bootstrap has a dedicated runbook covering conda, `CUROBO_SRC`,
  `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT`, preflight, failure classification, evidence fields,
  and claim boundaries.
- [x] A fixed native vs AAN front-camera pair was produced and reviewed as `WARN`: usable for parity review, not full parity proof.
- [ ] Any implementation work uses a separate worktree or the GenManip integration repo where runtime tooling actually lives.
- [x] Final reporting includes both allowed and forbidden claims.

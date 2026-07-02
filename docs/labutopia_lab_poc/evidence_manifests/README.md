# LabUtopia EBench Evidence Manifest Field Guide

## 目的

这个目录里的 manifest 是 PM 汇报和工程签收的证据来源。以后外部 asset package 进入 EBench 时，不能先写“已完成”，而要先写清楚 `run_id`、`command`、`artifact path`、`PASS/FAIL/BLOCKED`、`allowed_claims` 和 `blocked_claims`。

## 2026-07-01 AAN Consumer Evidence

DryingBox AAN-ready package 接入 EBench 的当前证据分为多个阶段记录。早期记录里
`status` 使用 producer/raw 风格的小写 `pass`；从 Stage 4b final manifest 开始，PM
汇总和验收 manifest 的顶层 `status` 统一使用大写 `PASS/FAIL/BLOCKED/WARN/IN_PROGRESS`。

| File | Stage | Status | 含义 |
|---|---|---|---|
| `aan_dryingbox_package_intake_20260701_0719.json` | Stage 1: `AAN package intake` | raw `pass` / canonical `PASS` | 固定 ConvertAsset retained package、manifest、package hash 和 file count。 |
| `aan_dryingbox_consumer_check_20260701_0000.json` | Stage 2: `Consumer manifest check` | raw `pass` / canonical `PASS` | AAN schema、runtime profile、benchmark profile、stage gates、entrypoints、dependency closure、blockers、waivers 通过 consumer 准入。 |
| `aan_dryingbox_task_mount_20260701_0000.json` | Stage 3: `Task-root wiring and dry-run composition` | raw `pass` / canonical `PASS` | AAN package 已用 symlink 挂到 composite assets root；`asset.usd`、task files 和 required prims 能解析。 |
| `aan_dryingbox_runtime_adapter_20260701_0000.json` | Stage 4a: `AAN runtime adapter preflight` | raw `pass` / canonical `PASS` | AAN-specific wrapper、task config、assets manifest 已生成；wrapper 真实引用 mounted `asset.usd`；package digest 在 Stage 4a 重新计算并匹配 Stage 1/3；`legacy_overlay_used=false`。 |
| `aan_dryingbox_runtime_smoke_20260701_085521.json` | Stage 4b: `AAN live eval smoke` | `PASS` | Fresh `run_id=labutopia_aan_lift2_stage4b_20260701_085521` 通过 submit / probe / eval 一致性检查；reset、step、render、metric、logging、`result_info.json`、stdout/stderr 都有证据；`legacy_overlay_used=false`。 |
| `aan_dryingbox_no_local_repair_snapshot_20260701_0000.json` | Stage 6a: `No-local-repair snapshot` | `PASS` | 对 retained ConvertAsset AAN package 做 hash baseline；`package_mutation_allowed=false`，`local_usd_repair_allowed=false`。 |
| `aan_dryingbox_no_local_repair_verify_20260701_0000.json` | Stage 6a: `No-local-repair verify` | `PASS` | Stage 6 guard 复核 package digest 仍为 `6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936`；没有 consumer-side local repair。 |
| `aan_muffle_furnace_package_intake_20260701_094329.json` | Stage 6 replication Stage 1 | raw `pass` / canonical `PASS` | 非 DryingBox articulated asset `MuffleFurnace` 的 retained ConvertAsset package 已锁定。 |
| `aan_muffle_furnace_consumer_check_20260701_094329.json` | Stage 6 replication Stage 2 | raw `pass` / canonical `PASS` | `MuffleFurnace` AAN manifest 通过 consumer schema / profile / gate / entrypoint 检查。 |
| `aan_muffle_furnace_task_mount_20260701_094802.json` | Stage 6 replication Stage 3 | raw `pass` / canonical `PASS` | `MuffleFurnace` package 以独立 namespace 挂载，`asset.usd` 能打开，非 `N/A` required prims 能解析。 |
| `aan_muffle_furnace_no_local_repair_verify_20260701_094846.json` | Stage 6 replication guard | `PASS` | `MuffleFurnace` package digest 仍为 `69c49538658892e4faef4265a9dd5049b16e690d3740f5a764b47a5f2b42a233`；没有 consumer-side local repair。 |
| `aan_muffle_furnace_runtime_adapter_20260701_102820.json` | Stage 6 replication Stage 4a | raw `pass` / canonical `PASS` | `MuffleFurnace` 已生成独立 generic AAN task lane、wrapper `.usda` 和 lane-local `assets_manifest.json`；wrapper 指向自己的 mounted AAN package；`legacy_overlay_used=false`。 |
| `aan_muffle_furnace_runtime_smoke_20260701_105508.json` | Stage 6 replication Stage 4b | `PASS` | Fresh `run_id=labutopia_aan_muf4b_20260701_104829` 通过 generic live smoke；reset、step、render、metric、logging、`result_info.json` 均有证据；`score=0.0` 是 smoke 边界，不是 semantic task success；`mdl_compiler_error_count=264` 阻止 full visual parity 声明。 |
| `aan_beaker_01_package_intake_20260701_094343.json` | Stage 6 replication Stage 1 | raw `pass` / canonical `PASS` | 非 DryingBox rigid transparent prop `Beaker_01` 的 retained ConvertAsset package 已锁定。 |
| `aan_beaker_01_consumer_check_20260701_094343.json` | Stage 6 replication Stage 2 | raw `pass` / canonical `PASS` | `Beaker_01` AAN manifest 通过 consumer schema / profile / gate / entrypoint 检查。 |
| `aan_beaker_01_task_mount_20260701_094802.json` | Stage 6 replication Stage 3 | raw `pass` / canonical `PASS` | `Beaker_01` package 以独立 namespace 挂载，`asset.usd` 能打开，非 `N/A` required prims 能解析。 |
| `aan_beaker_01_no_local_repair_verify_20260701_094846.json` | Stage 6 replication guard | `PASS` | `Beaker_01` package digest 仍为 `b707403b13a7295d0f5385e0c48b1498dc98119f5a728cc2d9d07614c3c87e98`；没有 consumer-side local repair。 |
| `aan_beaker_01_runtime_adapter_20260701_102820.json` | Stage 6 replication Stage 4a | raw `pass` / canonical `PASS` | `Beaker_01` 已生成独立 generic AAN task lane、wrapper `.usda` 和 lane-local `assets_manifest.json`；wrapper 指向自己的 mounted AAN package；`legacy_overlay_used=false`。 |
| `aan_beaker_01_runtime_smoke_20260701_1135.json` | Stage 6 replication Stage 4b | `PASS` | Fresh `run_id=labutopia_aan_beak4b_envfix_20260701_1135` 通过 generic live smoke；reset、step、render、metric、logging、`result_info.json` 均有证据；`score=0.0` 是 smoke 边界，不是 semantic task success；`mdl_compiler_error_count=8` 阻止 full visual parity 声明。 |
| `aan_stage6_replication_summary_20260701_0950.json` | Stage 6 replication summary | `BLOCKED` | 旧 summary。它记录当时 Stage 4a 尚未补齐时的 blocker，现在已被 `20260701_1145` summary supersede。 |
| `aan_stage6_replication_summary_20260701_1029.json` | Stage 6 replication summary | `IN_PROGRESS` | 旧 summary。它记录两个新资产完成 Stage 1-4a、但 Stage 4b live smoke 仍 `NOT_RUN` 的中间状态；现在已被 `20260701_1145` summary supersede。 |
| `aan_stage6_replication_summary_20260701_1056.json` | Stage 6 replication summary | `IN_PROGRESS`; minimum `PASS` | 旧 summary。它记录 `MuffleFurnace` 已通过 Stage 4b、`Beaker_01` 尚未运行 Stage 4b 的中间状态；现在已被 `20260701_1145` summary supersede。 |
| `aan_stage6_replication_summary_20260701_1145.json` | Stage 6 replication summary | `PASS` | 当前 summary。`stage6_minimum_acceptance_status=PASS`、`highest_common_passed_stage=4b`、`highest_replicated_stage=4b`、`stage4b_live_smoke_status=PASS`：`MuffleFurnace` 和 `Beaker_01` 都通过 generic Stage 4b live smoke。 |

Stage 1-4b 的允许说法：

```text
DryingBox AAN-ready package 已完成 LabUtopia / GenManip consumer 的收货、验货、task-root 挂载、AAN runtime adapter/preflight，并通过本地 EBench / GenManip live smoke。
```

Stage 1-4b 的禁止说法：

```text
official leaderboard score 已完成。
policy/model 已经解决 open-door 任务。
full visual material parity 已证明。
```

Stage 4b 已产出 `aan_dryingbox_runtime_smoke_20260701_085521.json`。只有这个 final
manifest 可以让 PM 汇报 “AAN package 通过本地 live eval smoke”。它记录 fresh
`run_id`、run-id/artifact 一致性、`reset_passed=true`、`step_passed=true`、
`render_passed=true`、`metric_passed=true`、`logging_passed=true`、
`result_info_exists=true`、stdout/stderr paths、exit codes，并且没有任何 `FAIL` /
`BLOCKED` row。

Stage 6 复制验证的允许说法：

```text
Stage 6 replication hardening 已 PASS：MuffleFurnace 和 Beaker_01 已经复制通过
AAN consumer Stage 1-4b：收货、验货、task-root 挂载 dry-run、no-local-repair verify、
generic lane/wrapper 生成、runtime adapter preflight 和 generic live smoke；两个包都没有被
LabUtopia / GenManip 本地修改。两次 generic Stage 4b smoke 都证明 reset / step /
render / metric / logging / result_info 链路可运行。
```

Stage 6 复制验证的禁止说法：

```text
semantic evaluator / task/evaluator.yaml runtime execution 已经实现。
MuffleFurnace 或 Beaker_01 的 generic smoke pass 等于 semantic task success。
Beaker_01 的 OmniGlass MDL warning 已经完成 full visual parity closure。
Stage 6 PASS 等于任意 USD / MJCF / deformable / liquid 资产都 ready。
```

Stage 6 当前 summary：

```text
stage6_minimum_acceptance_status=PASS
status=PASS
highest_common_passed_stage=4b
highest_replicated_stage=4b
stage4a_runtime_adapter_preflight_status=PASS
stage4b_live_smoke_status=PASS
blocker_or_next_action=Stage6 replication hardening PASS. Next follow-ups: standardize the AAN runtime env bootstrap, implement semantic evaluator dispatch for task/evaluator.yaml, and close material-warning/full-visual-parity evidence separately.
```

Beaker_01 的前两次 diagnostic failure 不是资产失败，而是 consumer runtime 环境诊断：

- 第一次 worker 没继承 `CUROBO_SRC`，还没进入资产加载；
- 第二次修好 cuRobo Python import 后，暴露 `PATH/LD_LIBRARY_PATH` 缺少 `ninja` 和 `libcudart.so.11.0`；
- final fresh run 用现有 `embodied-eval-os-sim-isaacsim41-genmanip-py310` 环境，加上 `CUROBO_SRC`、`PATH=$PYENV/bin:$PATH`、IsaacSim `omni.cuda.libs/bin` 和 `omni.gpu_foundation/bin/deps` 的 `LD_LIBRARY_PATH` 后通过。

Stage 4b 的运行证据目录：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan_lift2_stage4b_20260701_085521/
```

Stage 4b 运行时仍记录了 `mdl_compiler_error_count=636`。这不阻塞 reset / step /
render / metric / logging 的 smoke pass，但它阻止任何更强的视觉声明：不能把 Stage 4b
PASS 说成 full visual material parity 或 source-native full material closure。

### 2026-07-02 Producer Render Visual QA

`reports/2026-06-15-labutopia-weekly/assets/aan-dryingbox-producer-runtime-smoke-render.png`
现在只保留为问题诊断图，不作为展示图。视觉复核结论：

- 明显异常红色材质：ConvertAsset producer runtime log 中有
  `Failed to create MDL shade node`、`could not find module` 和 unresolved texture
  记录，说明 MDL / texture runtime 解析没有闭环；
- 背面/俯视相机：画面看不到 DryingBox 的门、handle 和正面整体结构；
- 因此 producer `runtime_smoke.status=pass` 只能说明 headless load / render
  readback / step / reset 这些 smoke gate 通过，不能升级为 full visual material
  parity 或可展示最终材质效果。

关键 producer 证据：

```text
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package/evidence/runtime_smoke/report.json
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package/evidence/runtime_smoke/stderr.log
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/package/evidence/runtime_smoke/stdout.log
```

当前日志计数：

```text
producer_failed_mdl_shade_nodes=10
producer_missing_mdl_modules=41
producer_unresolved_textures=18
producer_payload_scope_material_binding_warnings=84
consumer_mdl_compiler_error_count=636
```

这也修正了 `material_closure=pass` 的 PM 读法：它是 package-local dependency /
material evidence gate，不等于 Isaac 4.1 runtime 中所有 MDL shader、texture 和最终颜色
都已经正确显示。下一步应由 ConvertAsset 侧做 material runtime closure follow-up：
补齐 MDL transitive dependencies、texture path、material binding scope，并用 task-facing
showcase camera 重拍；LabUtopia / GenManip 只消费新包并复跑 evidence，不做本地修包。

Stage 5 PM/weekly HTML 已发布到：

```text
reports/2026-06-15-labutopia-weekly/index.html#aan-handoff
```

该页面把 Producer evidence 和 Consumer evidence 分开展示，并把两张 DryingBox render
图标注为 diagnostic render。AAN producer render 已进一步标注为视觉 QA FAIL/OPEN：
红色异常材质和背面视角都是待修问题，不升级为 full visual material parity。

`aan_dryingbox_runtime_adapter_20260701_0000.json` 的关键硬门：

- `config_path=ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml`，不是旧 `lift2_candidate`；
- `runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_scene`，不是旧 overlay scene；
- `wrapper_references` 是从 USDA reference list 解析出来的，不接受注释里的假字符串；
- `package_tree_digest` 和 `mounted_package_tree_digest` 都等于 `6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936`；
- AAN manifest routing 忽略旧全局 `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT`，防止 leftover env 把 AAN config 带回旧 overlay。

Stage 4b final manifest 的最小硬门：

- `status=PASS`，不是 raw `pass`；
- fresh `run_id` 同时出现在 submit/eval/probe logs、artifact directory、`result_info_path` 和 manifest；
- `config_path=ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml`；
- `legacy_overlay_used=false`；
- Lift2/R5a eval 使用 16D action dialect，例如 `-a r5a -g lift2`，不能用默认 Franka/Panda 9D action；
- `reset_passed=true`、`step_passed=true`、`render_passed=true`、`metric_passed=true`、`logging_passed=true`；
- `result_info_exists=true`、`stdout_exists=true`、`stderr_exists=true`；
- `submit_exit_code=0`、`probe_or_eval_exit_code=0`；
- `no_fail_or_blocked_rows=true`；
- 非 PASS 时必须写 `failure_phase`、`failure_owner`、`blocker_or_next_action`。

## 标准顶层字段

每个新的 AAN consumer 验收记录建议包含：

```json
{
  "schema_version": 1,
  "recorded_at_utc": "2026-07-01T00:00:00Z",
  "asset_id": "DryingBox_01_overlay",
  "task_lane": "ebench/labutopia_lab_poc/aan_lift2_candidate",
  "stage": "aan_stage4b_live_smoke",
  "status": "PASS",
  "run_id": "example_run_id",
  "commands": {
    "server": "PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python; PYTHONPATH=$CUROBO_SRC:$WORKTREE $PY ray_eval_server.py --host 127.0.0.1 --port 18189 --run_id $RUN_ID --no_save_process --episode_recorder_save_every 0 --reset_timeout 1200 --step_timeout 1200 --load_config_timeout 300",
    "submit": "gmp submit ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door.yml ...",
    "probe": "python standalone_tools/labutopia_poc/lift2_eval_contract_probe.py --live --host 127.0.0.1 --port 18189 --worker-id 0 --run-id $RUN_ID --task-name level1_open_door --logging-json $EVIDENCE_DIR/live_probe_logging.json --output $EVIDENCE_DIR/probe.json",
    "eval_or_smoke_client": "python -m genmanip_client.cli eval -a r5a -g lift2 ..."
  },
  "profile": {
    "asset_class": "articulated",
    "runtime_profile": "isaac41",
    "benchmark_profile": "ebench-lift2",
    "dynamics_profile": "articulated_body",
    "profile_support_status": "supported_phase1"
  },
  "artifact_paths": [],
  "artifact_sha256": {},
  "gate_status": {},
  "failure_phase": null,
  "failure_owner": null,
  "blockers": [],
  "allowed_claims": {},
  "blocked_claims": {},
  "verification": []
}
```

New PM/evidence-summary `status` values only allow:

```text
PASS
FAIL
BLOCKED
WARN
IN_PROGRESS
```

`WARN` 只能表示 diagnostic evidence 可用，不能表示验收完成。Producer manifest 内部的
raw status 可以保留原样，但要放在 `producer_manifest_raw_status`、`stage_gates_raw` 等
字段下，不要覆盖顶层 canonical `status`。

## Gate 字段

推荐统一记录这些 gate：

```json
{
  "gate_status": {
    "asset_intake": "PASS",
    "usd_composition": "PASS",
    "material_closure": "PASS",
    "physics_closure": "PASS",
    "articulation_closure": "PASS | NOT_APPLICABLE | NOT_REQUIRED",
    "task_runtime": "PASS",
    "render_evidence": "WARN",
    "evaluator_robot_contract": "PASS"
  }
}
```

PM 文案只能说对应 `PASS` 的部分。比如 `task_runtime=PASS` 可以说“本地任务链路可评”，但不能推出 `policy_success=true`。
Rigid-only USD assets must not force `articulation_closure=PASS`; use `NOT_APPLICABLE` or
`NOT_REQUIRED`. Articulated assets must keep explicit articulation evidence.

## Material Closure 字段

`material_closure` 必须拆清楚 package-level claim 和 source-native claim：

```json
{
  "material_closure": {
    "material_status": "resolved_material_with_local_overrides",
    "remote_unmirrored_unwaived_count": 0,
    "remote_waiver_count": 0,
    "local_mirror_count": 1,
    "source_resolved_surface_count": 1,
    "wrapper_authored_material_count": 2,
    "fallback_surface_count": 0,
    "dependency_records": [],
    "source_resolved_surface_records": [],
    "authored_material_records": [],
    "fallback_surface_records": [],
    "waiver_records": [],
    "material_closure_claim_allowed": true,
    "full_material_closure_claim_allowed": true,
    "native_material_closure_claim_allowed": false,
    "full_native_material_closure_claim_allowed": false,
    "asset_specific_claims": {
      "aluminum_material_closure_claim_allowed": true
    },
    "native_material_closure_reason": "wrapper_local_material_overrides_present",
    "native_material_provenance": {
      "schema_version": 1,
      "status": "blocked_by_wrapper_local_overrides",
      "source_native_blocker_surface_count": 2,
      "native_wrapper_override_surface_count": 2,
      "native_claim_blocker_records": [
        {
          "source_prim_path": "/World/DryingBox_01/Group/_900_1",
          "runtime_prim_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/Group/_900_1",
          "source_binding_status": "empty_authored_binding_in_stage2_source_readback",
          "source_material_binding": null,
          "runtime_material_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/Looks/task_indicator_mat",
          "replacement_required_for_full_native_closure": true,
          "blocked_claims": ["native_material_closure", "full_native_material_closure"]
        },
        {
          "source_prim_path": "/World/DryingBox_01/button",
          "runtime_prim_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/button",
          "source_binding_status": "unbound_in_stage2_source_readback",
          "source_material_binding": null,
          "runtime_material_path": "/World/labutopia_level1_poc/obj_obj_DryingBox_01/Looks/task_button_mat",
          "replacement_required_for_full_native_closure": true,
          "blocked_claims": ["native_material_closure", "full_native_material_closure"]
        }
      ]
    }
  }
}
```

规则：

- 单个 material dependency 已 local mirror，只能升级 scoped dependency claim。
- 当 runtime `fallback_surface_count=0`，且 wrapper-local override 已显式记录时，`full_material_closure_claim_allowed` 可以是 `true`，表示 EBench package material gate 已通过。
- 只要存在 wrapper-local authored material，`full_native_material_closure_claim_allowed` 必须是 `false`。
- `native_material_provenance` 是 source-native claim 的刹车字段：它说明哪些 wrapper-local material override 还没有 source-native `material:binding` 证据，且每条 blocker 必须写清 source path、runtime path、runtime material path、source binding status 和 blocked claims。
- hash mismatch、missing texture、stale `/World/Looks` binding、unknown unbound mesh 和 overclaim 都是 FAIL。
- explicit waiver 可以保留资产验收边界，但不能让 package material closure 或 native material closure 自动变成 true。
- `primvars:displayColor` 不自动等于 fallback；有有效 `material:binding` 时只算 authored auxiliary color，只有 fallback-only surface 才计入 `fallback_surface_count`。

Reusable validator boundary:

- New assets should construct `MaterialClosureExpectation` instead of copy/pasting DryingBox assertions; the expectation includes material status, claim flags, forbidden claims, native provenance status, and blocker paths.
- `NativeMaterialProvenanceBlocker` records are the reusable unit for surfaces that have package-visible wrapper material but cannot claim source-native material binding.
- Asset-specific validators may still add package checks for source files, physics reports, camera contracts, or task semantics.

## PM 文案映射

| Manifest 字段 | PM 可以怎么说 | PM 不能怎么说 |
| --- | --- | --- |
| `task_runtime_ready=true` | 任务能 reset/step/logging，本地链路可评 | 策略已经会做任务 |
| `task_render_accepted=true` | eval camera 能拍到可读任务图 | 官方榜单成绩已复现 |
| `lift2_contract_ready=true` | 本地 Lift2 合同检查通过 | official leaderboard 已发布 |
| `asset_specific_claims.aluminum_material_closure_claim_allowed=true` | DryingBox 的 Aluminum 远端材质依赖已 local mirror | DryingBox 全部 native 材质已恢复 |
| `full_material_closure_claim_allowed=true` | EBench package material evidence 已记录 | runtime MDL/texture closure 或 source-native full material closure 已完成 |
| `full_native_material_closure_claim_allowed=false` | 仍不能宣称 source-native 全闭环 | 把它解读为 package material gate 未通过 |
| `pm_showcase_ready=false` | 当前图只能作为诊断证据 | 当前图可直接对外展示 |

## 当前 DryingBox 状态示例

```text
旧 evidence lane - LabUtopia hand-built overlay:
  Stage 7 local Lift2 contract: PASS
  full native material closure: BLOCKED by wrapper-local button and Group/_900_1 materials
  native material provenance: BLOCKED by /World/DryingBox_01/button and /World/DryingBox_01/Group/_900_1

新 evidence lane - ConvertAsset AAN package consumer:
  Stage 1-4b AAN consumer live smoke: PASS
  Stage 5 PM/weekly HTML publication: PASS
  Stage 6a no-local-repair guard: PASS
  Stage 6 replication on additional assets: PASS; Stage 1-4b generic smoke PASS on MuffleFurnace and Beaker_01
  EBench package material evidence: PASS
  Aluminum local mirror: PASS
  Stage 4b consumer live smoke: PASS
  runtime material warning: mdl_compiler_error_count=636; not full visual parity evidence

共同禁止声明:
  policy success: BLOCKED / not evaluated
  official leaderboard: BLOCKED / not an official run
  full visual material parity: BLOCKED / not proven
```

这说明 DryingBox 当前已经能证明“本地 consumer live smoke 通过”和“包级材质 evidence 已记录”，但还不能证明“策略成功”“官方成绩发布”或“source-native 全材质闭环完成”。PM 汇报时可以说 package material evidence 和 Stage 4b local live smoke 有证据，不能把 `button` 和 `Group/_900_1` 的 wrapper-local `PreviewSurface` 说成原生材质已恢复，也不能把红色 producer render 或 636 条 MDL compiler warning 解释成视觉一致性已经无风险。

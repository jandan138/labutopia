# LabUtopia AAN Consumer Handoff

Date: 2026-07-01

## 当前结论

ConvertAsset 的 `Asset Application Normalizer` 已经产出 DryingBox 的 AAN-ready
package。LabUtopia / GenManip consumer 已经把它接入 `level1_open_door` 并通过本地
Stage 4b live smoke；继续点要从“手工修 LabUtopia USD 资产”切换为“发布 PM 证据、
保持 no-local-repair guard，并把同一套收货、验货、挂载流程复制到更多 rigid /
articulated USD assets”。

Stage 6 的最新结论：overall Stage 6 已经 `PASS`，但后续仍有 semantic evaluator 和
full visual/material parity 的增强工作。`MuffleFurnace` 和 `Beaker_01` 都完成
consumer Stage 1-4b 复制验证，并且 no-local-repair verify 通过；generic AAN task lane、
wrapper 和 lane-local `assets_manifest.json` 已能为每个资产单独生成。`MuffleFurnace`
用 fresh `run_id=labutopia_aan_muf4b_20260701_104829` 通过 generic Stage 4b live smoke；
`Beaker_01` 用 fresh `run_id=labutopia_aan_beak4b_envfix_20260701_1135` 通过 generic
Stage 4b live smoke。两个 run 都有 reset / step / render / metric / logging /
`result_info.json` 证据。`task/evaluator.yaml` 目前是被验收和挂载的 package metadata，
还没有被 GenManip runtime 自动 import 成可执行 metric；这属于后续 semantic evaluator
follow-up。

AAN-ready 的一句话定义：这个资产包不是只“能打开 USD 文件”，而是已经带着 dependency、
material、physics、articulation where applicable、producer runtime smoke、benchmark
contract 的 manifest 证据，可以被下游 consumer 严格验收。

2026-07-02 视觉复核补充：DryingBox 当前 AAN producer render 不能当成最终材质展示图。
那张图证明 producer 侧有非空 render readback，但肉眼可见两个问题：整机异常偏红，
并且相机从背面/上方拍摄，看不到门、handle 和全貌。日志也支持这个判断：producer
runtime smoke 里有 `Failed to create MDL shade node`、missing MDL module 和 unresolved
texture，consumer Stage 4b 里也有 `mdl_compiler_error_count=636`。因此
`material_closure=pass` 只能说 package-local / source-preserved material evidence 已记录，
不能说 full visual material parity 或 runtime MDL/texture closure 已完成。

## LabUtopia AAN-Ready Package 接入 EBench 计划（6 stages）

目标：不再继续手工修 DryingBox USD / MDL / articulation，而是把 ConvertAsset 已闭环
的 AAN-ready package 作为输入，完成 LabUtopia / GenManip consumer 接入。

六个阶段：

| Stage | 产品别名 | 工程名称 | 通俗解释 | 当前状态 |
|---|---|---|---|---|
| 1 | 收货锁定 | **AAN package intake** | 固定收货对象，确认我们消费的是哪一个 ConvertAsset package。 | **已完成** |
| 2 | 验货准入 | **Consumer manifest check** | 收货验货，确认 schema、runtime profile、benchmark profile、stage gates、entrypoints、blocked reasons、waivers 都满足 consumer 准入。 | **已完成** |
| 3 | 挂进任务目录 | **Task-root wiring and dry-run composition** | 把 `asset.usd`、`task_config`、`required_prims`、`evaluator` 挂到 LabUtopia / GenManip task root，并确认路径和 required prims 能解析。 | **已完成** |
| 4 | 跑本地任务链路 | **AAN runtime adapter and live eval smoke** | 先确认 live runtime 真正加载 AAN package，不是旧 overlay；再重跑 `level1_open_door` reset / step / render / metric / logging smoke。 | **已完成 / DryingBox Stage 4b PASS** |
| 5 | 产出 PM 证据 | **PM evidence and weekly HTML update** | 更新周报 / PM 页面，展示 Stage 4b live smoke、AAN render 与 claim boundary。 | **已完成** |
| 6 | 防偷修包并复制验证 | **Regression, boundary, and replication hardening** | 增加 no-local-repair 保护，并把同一套收货、验货、挂载、runtime adapter preflight / smoke 流程复制到新资产；复制验证不等于完整 runtime / policy 评测成功。 | **已完成 / PASS：DryingBox no-local-repair PASS；`MuffleFurnace` / `Beaker_01` Stage 1-4b generic smoke PASS** |

现在可以在内部汇报：DryingBox AAN-ready package 已被 LabUtopia / GenManip consumer
接入并通过本地 live eval smoke。Stage 6 是流程固化和复制，不阻塞 DryingBox 的单资产
接入结论。

当前已经可以说：DryingBox AAN-ready package 已经完成 LabUtopia / GenManip consumer
Stage 1-4b。通俗讲，就是“收货、验货、挂到任务根目录、给 EBench 做好 DryingBox
AAN 专用入口，
并用 fresh run 跑通 reset / step / render / metric / logging，且确认这个入口没有偷偷
指回旧 overlay”。

当前仍不能说：official leaderboard score 已完成、模型已经解决任务、benchmark-wide
任意资产都自动可评、full visual material parity 已证明。

Stage 4 内部有两个硬门：

| 子步骤 | 通俗解释 | 状态 |
|---|---|---|
| Stage 4a | 入口预检：证明 AAN wrapper 指向 mounted AAN package，不是旧 overlay。 | 已完成 |
| Stage 4b | live smoke：用 fresh `run_id` 证明 reset、step、render、metric、logging 都通过，并产出 `aan_*_runtime_smoke_*.json`。 | DryingBox 已完成 / PASS；`MuffleFurnace` generic smoke 已完成 / PASS；`Beaker_01` generic smoke 已完成 / PASS |

DryingBox Stage 4b 的最终 manifest 已是 `PASS`，因此可以说 “DryingBox AAN package 通过本地 EBench live smoke”。这句话只覆盖 DryingBox 本地 smoke，不覆盖复制资产、不覆盖 official leaderboard、policy success 或 full visual material parity。

Stage 6 可以说“consumer 复制验证已完成到 generic smoke”。当前能说的是：复制到
`MuffleFurnace` 和 `Beaker_01` 后，Stage 1 收货、Stage 2 验货、Stage 3 挂载 dry-run、
no-local-repair verify、Stage 4a runtime adapter preflight 和 Stage 4b generic live
smoke 都通过，且没有本地改包。它证明 reset / step / render / metric-field / logging /
result_info 链路能给出证据。把 `task/evaluator.yaml` 真正执行成 runtime metric 是下一层
semantic evaluator 工作，不能和 smoke pass 混在一起。

详细执行计划：

```text
docs/superpowers/plans/2026-07-01-labutopia-aan-ready-package-ebench-integration.md
```

当前可消费证据位于 ConvertAsset：

```text
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-01-aan-07-dryingbox-runtime-ready/
```

关键文件：

```text
dryingbox_runtime_ready_manifest.json
package/asset.usd
package/task/task_config.yaml
package/task/required_prims.yaml
package/task/evaluator.yaml
package/evidence/runtime_smoke/report.json
package/evidence/runtime_smoke/render.png
```

## 已核验的 AAN 状态

本地检查结果：

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

AAN stage gates：

| Gate | Status | LabUtopia 侧含义 |
|---|---|---|
| `usd_closure` | `pass` | source USD dependency graph 已闭环到 package |
| `material_closure` | `pass` | MDL / texture 已 local mirror 或记录为 package-local evidence |
| `physics_static` | `pass` | rigid / collision / mass / articulation 静态证据已记录 |
| `runtime_smoke` | `pass` | ConvertAsset producer 侧 Isaac 4.1 headless load / render / step / reset smoke 已通过；这不是 LabUtopia / GenManip consumer 侧 Stage 4b live eval pass。 |
| `benchmark_contract` | `pass` | `task_config`、`required_prims`、`evaluator` 已生成；这不是 live eval pass，也不是 official score |

Material gate 的正确读法：`material_closure=pass` 说明 MDL / texture 依赖有 package-local
或 source-preserved evidence，并不等于 Isaac 4.1 runtime 里所有 MDL shader、texture 和
最终颜色都已经正确显示。当前 producer render 的红色异常材质已经把 full visual/material
parity 留成 follow-up。

配套测试：

```text
cd /cpfs/user/zhuzihou/dev/ConvertAsset
python -m pytest tests/test_asset_application_normalizer_cli.py \
  tests/test_asset_application_normalizer_pm_and_mjcf.py -q

29 passed
```

## 当前 Stage 1-4b consumer 证据

这些证据产自 GenManip AAN consumer 分支：

```text
/root/.config/superpowers/worktrees/GenManip/labutopia-aan-consumer
```

实现提交：

```text
5161227 feat: add AAN consumer package check
72ca5e0 fix: block closure-level AAN dependencies
9d042da feat: add AAN task root mount check
```

Stage 1 evidence：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_package_intake_20260701_0719.json
status=pass
package_file_count=30
package_tree_digest=6bc1bcb64f20b8db9f253f745dc733bfd1df23928ab8fc71a4977d69a5423936
```

Stage 2 evidence：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_consumer_check_20260701_0000.json
status=pass
aan_consumer_manifest_ready=true
aan_package_mount_allowed=true
local_usd_repair_allowed=false
blockers=[]
```

Stage 3 evidence：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_task_mount_20260701_0000.json
status=pass
symlink_or_copy_mode=symlink
path_resolution_status=mounted
usd_stage_opened=true
all_required_prims_found=true
runtime_execution_passed=false
```

Stage 4a adapter/preflight evidence：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_adapter_20260701_0000.json
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

Stage 4b live smoke evidence：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_dryingbox_runtime_smoke_20260701_085521.json
status=PASS
stage=aan_stage4b_live_smoke
run_id=labutopia_aan_lift2_stage4b_20260701_085521
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
score=0.0
success_rate=0
```

Stage 4b 运行证据目录：

```text
docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan_lift2_stage4b_20260701_085521/
```

Result info：

```text
saved/eval_results/ebench/labutopia_aan_lift2_stage4b_20260701_085521/ebench/labutopia_lab_poc/aan_lift2_candidate/level1_open_door/000/result_info.json
```

通俗讲：资产包已经收货、验货、装进任务目录，并且 EBench 将要加载的 scene 入口已经
改成 AAN 专用 wrapper。这个 wrapper 不是修资产，它只是“给 EBench 一个它能按
`${ASSETS_DIR}/${usd_name}.usda` 打开的门牌号”，里面再指向 AAN package 的
`asset.usd`。预检还做了三道防混淆保护：

- 重新计算 mounted package digest，和 Stage 1 / Stage 3 的 digest 对上；
- `mounted_root_usd` 必须位于 composite assets root 的 AAN namespace 里；
- AAN config 不吃旧的 `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT` env override，避免被带回
  legacy overlay。

Stage 4b 已经不是待跑项。它不是只看 probe 是否 reset/step 成功，而是同时检查
`result_info.json`、render / metric / logging 证据、stdout/stderr 路径、run_id 一致性和
`status=PASS`。本次这些硬门均通过。

## 这解决了之前哪个中断点

之前 LabUtopia native DryingBox Stage 7 已经通过本地 Lift2 official-baseline-style
contract，但 Stage 4-6 的材质边界仍然写作：

```text
native_material_closure_status=open_remote_dependency_waived
native_material_closure_claim_allowed=false
```

也就是说，之前能说“本地 Lift2 contract 通了”，但不能说“DryingBox 资产包自身已经
完整闭环”。这里有两条证据线，不是互相矛盾：

- 旧的 hand-built LabUtopia overlay 仍保持 material closure open / waived；
- 新的 ConvertAsset AAN package 已经记录 package-local / source-preserved material evidence。

后续 PM 汇报必须带上证据线名称，避免把旧 overlay 的限制误套到 AAN package，或把
AAN package 的包级 evidence 反推成 runtime visual parity。ConvertAsset AAN 现在把资产包证据线补上了：

- package 内有 `Aluminum_Anodized_Charcoal.mdl` 等 MDL mirror；
- package 内有 texture mirror；
- manifest 中 `material_closure=pass`，但这只表示静态/包级 material evidence 通过；
- manifest 中 `runtime_smoke=pass`；
- manifest 中 `benchmark_contract=pass`；
- `claims_forbidden` 仍保留了 full visual material parity 等不能越界声明的内容。

因此现在可以继续做 LabUtopia / EBench consumer 集成。

## 为什么不能直接复用旧 Lift2 Stage 7

旧 `LabUtopia hand-built overlay / Lift2 Stage 7` 证明的是旧 overlay 通过本地
official-baseline-style Lift2 contract。它不是 ConvertAsset AAN package 的 live eval
证据。

关键区别：

| Evidence lane | 证明什么 | 不能推出什么 |
|---|---|---|
| 旧 `LabUtopia hand-built overlay / Lift2 Stage 7` | 旧 overlay 的本地 Lift2 contract 可以 reset、step、读 observation/action/metric。 | 不能证明新 AAN package 被 live runtime 消费。 |
| 新 `ConvertAsset AAN package / EBench consumer stages` | DryingBox AAN package 被收货、验货、挂载，并已通过 AAN runtime adapter/preflight 和 Stage 4b live smoke；复制资产 `MuffleFurnace` 和 `Beaker_01` 也已复制到 generic Stage 4b live smoke PASS。 | Stage 4b live smoke 不能证明 official leaderboard、policy success、semantic task success 或 full visual material parity。 |

技术原因：当前旧 `lift2_candidate` config 的 `usd_name` 仍是：

```text
scene_usds/labutopia/level1_poc/lab_001/scene
```

而 AAN package 挂载在：

```text
labutopia_aan_packages/dryingbox_01_overlay/asset.usd
```

GenManip runtime 当前按 `${ASSETS_DIR}/${usd_name}.usda` 加载，所以 Stage 4 已先创建
一个 AAN-specific `.usda wrapper`：

```text
scene_usds/labutopia/aan/dryingbox_01_overlay_scene.usda
```

这个 wrapper 明确 reference / payload：

```text
labutopia_aan_packages/dryingbox_01_overlay/asset.usd
```

然后 AAN 专用 task config 的 `usd_name` 指向这个 wrapper。这样后续 live eval evidence
才能证明“跑的是 AAN package”，不会和旧 overlay 结果混在一起。

## 状态词区别

| 状态词 | 通俗含义 | 能说什么 | 不能说什么 |
|---|---|---|---|
| package ready | ConvertAsset 资产包合格 | AAN manifest 通过，资产包可交给 consumer | 任务已经 live eval 通过 |
| consumer wired | LabUtopia / GenManip 已接上包 | task root 能解析 asset/task/evaluator 文件 | reset / step / metric 已通过 |
| live eval smoke passed | 本地任务链路跑通 | reset、step、render、metric、logging 有证据 | 模型已经成功完成任务 |
| model solved task | policy/controller 成功完成任务 | success/score 由 evaluator 证明 | official leaderboard 已发布 |
| official score released | 官方流程产出可比较分数 | 可以谈 official leaderboard comparability | 不能由本地 smoke 自动推出 |

## LabUtopia 侧不能再做什么

后续不要在 LabUtopia 主仓库里重新维护 USD / MDL / articulation 修补逻辑。

如果发现以下问题，应回到 ConvertAsset AAN 重跑或修 AAN，而不是在这里打补丁：

- package 缺 MDL / texture / reference；
- `required_prims.yaml` 路径不对；
- articulation root / joint / handle role 不对；
- runtime smoke blocker；
- material closure blocker；
- benchmark contract blocker。

Blocker owner：

| Blocker 类型 | Owner | LabUtopia / GenManip 动作 |
|---|---|---|
| USD / MDL / texture / dependency | ConvertAsset AAN | 记录 blocker，不本地修包 |
| package escaping path / remote URI / missing local mirror | ConvertAsset AAN | 回 producer 修 dependency / material closure |
| physics / articulation / required prim contract | ConvertAsset AAN, with consumer feedback | 记录缺失角色和目标 task 语义 |
| AAN task_config / required_prims / evaluator contract 写错 | ConvertAsset AAN, with consumer feedback | 修 package benchmark contract |
| package mount path / task-root discovery | GenManip consumer | 修 consumer mount，不改 AAN source package |
| AAN `.usda wrapper`、AAN task profile、`ASSETS_DIR`、env 注入 | GenManip consumer | 修 runtime adapter |
| live reset / step / metric / logging | GenManip / EBench runtime lane | 修 server、worker、config、probe |
| live eval 通过但 score=0 / success_rate=0 | policy/task execution quality | 不算 AAN package failure，除非 metric contract 读错 |
| PM wording / weekly evidence | LabUtopia docs | 更新报告并保留 forbidden claims |

LabUtopia 侧只保留 consumer 责任：

- 选择要消费的 AAN package；
- 检查 manifest 是否 ready；
- 把 `package/asset.usd` 和 task files 接入 EBench / GenManip task root；
- 跑 EBench / GenManip eval；
- 把 eval 结果、渲染图、manifest、claim boundary 汇报到周报或 PM 页面。

## Consumer ready 判定

LabUtopia 侧消费前必须检查：

1. `schema_version == "asset_application_normalizer.v1"`。
2. `target.target_runtime_profile == "isaac41"`。
3. `target.target_benchmark_profile == "ebench-lift2"`。
4. `overall_status == "pass"`。
5. `stage_gates` 中 `usd_closure`、`material_closure`、`physics_static`、
   producer-side `runtime_smoke`、`benchmark_contract` 均为 `pass`。
6. `runtime_evidence.status == "pass"`。
7. `runtime_evidence.render_readback.status == "pass"`。
8. `benchmark_contract.status == "pass"`。
9. `entrypoints.root_usd`、`entrypoints.task_config`、`entrypoints.required_prims`、
   `entrypoints.metric_evaluator` 都能在 package 内解析。
10. `blocked_reasons` 为空。
11. `waivers` 为空，或显式保留 waiver 对应的 `claims_forbidden`。

## 材质汇报边界

这次 AAN package 的 `material_closure=pass` 可以汇报为 package-local / source-preserved
material evidence 已记录，但不能升级成 runtime material closure 或 full visual parity。

三层话术如下：

| Term | 可以说 | 不能说 |
|---|---|---|
| `material_closure` | AAN package material evidence 已记录；package-local path/hash 或 source-preserved evidence 可追踪。 | runtime MDL/texture closure 已完成；full visual parity 已证明。 |
| `local mirror` | 某个 remote MDL/texture dependency 已有 package-local path/hash evidence。 | mirror 以后视觉就一定和源资产完全一致。 |
| `full visual parity` | 当前证据不支持。 | source-native full material closure 或 full visual material parity 已证明。 |

PM 口径：

> AAN package material evidence 已记录，部分 remote material dependencies 已按 manifest 做
> local mirror/source-preserved evidence；这证明 package 有可追踪的材质来源和依赖证据。
> 但当前 producer render 仍有红色异常材质，日志里也有 MDL/texture 解析错误，所以不能
> 宣称 runtime material closure、source-native full material closure 或 full visual parity。

## 下一步

1. 保留两条复制资产 Stage 4b generic live smoke 证据：
   `aan_muffle_furnace_runtime_smoke_20260701_105508.json` 记录
   `run_id=labutopia_aan_muf4b_20260701_104829`；
   `aan_beaker_01_runtime_smoke_20260701_1135.json` 记录
   `run_id=labutopia_aan_beak4b_envfix_20260701_1135`。两者都通过 reset / step / render /
   metric-field / logging、stdout/stderr 和 `result_info.json` 硬门；`score=0.0` 只说明
   smoke 不是 semantic task success。
2. 把 `Beaker_01` 的 runtime env bootstrap 标准化：使用现有
   `embodied-eval-os-sim-isaacsim41-genmanip-py310` conda 环境，设置
   `CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src`，把
   `$PYENV/bin` 放进 `PATH` 以找到 `ninja`，并把 IsaacSim `omni.cuda.libs/bin` 和
   `omni.gpu_foundation/bin/deps` 放进 `LD_LIBRARY_PATH` 以找到 `libcudart.so.11.0`。
   这一步是 consumer runtime 启动规范，不是资产包修复。
3. 单独规划 semantic evaluator follow-up：决定 `task/evaluator.yaml` 是映射到
   GenManip `MetricFactory`，还是走受控 plugin dispatch。它用于 task success / official
   score 级别声明，不是 Stage 4b reset/step/render smoke 的必需条件。
4. 单独规划 visual/material parity follow-up：DryingBox producer render 仍有红色异常材质、
   背面/俯视 camera 问题，consumer Stage 4b 仍有 `mdl_compiler_error_count=636`；
   `Beaker_01` 最终 smoke 也仍有 `mdl_compiler_error_count=8` 的 OmniGlass MDL
   compiler warning。这些不阻塞 Stage 4b smoke PASS，但阻止 full visual material
   parity / source-native material closure 声明。
5. 保持 no-local-repair guard：consumer 侧发现 USD / MDL / articulation 缺口时，记录 blocker 并回到 ConvertAsset AAN，不在 LabUtopia / GenManip 本地修包。

Stage 6 的通用化边界：Phase 1 只承诺 USD rigid / articulated assets 在 Isaac 4.1 /
EBench Lift2 target profile 下形成可复用 consumer 流程。Deformable、cloth、liquid、
particle、granular assets 暂时只能写作 future non-rigid dynamics profiles，在 solver
state、physics semantics、reset/step stability、collision coupling、render/readback、
evaluator gates 都补齐前，必须标为 `unsupported`、`blocked` 或
`semantic_gap_report_only`，不能标为 `ready`。

复制到更多资产时，每个资产都要写：

```text
asset_class=rigid | articulated | unsupported_non_rigid
runtime_profile=isaac41
benchmark_profile=ebench-lift2
dynamics_profile=rigid_body | articulated_body | unsupported_non_rigid
highest_passed_stage=<1|2|3|4a|4b|5|6>
stage4b_live_smoke_status=PASS | FAIL | BLOCKED | NOT_RUN
profile_support_status=supported_phase1 | blocked | unsupported
failure_phase=<server_start|submit|reset|step|render|metric|logging|client_probe|asset_package|null>
failure_owner=<ConvertAsset AAN|GenManip/EBench runtime|LabUtopia consumer|policy/task execution|null>
blocker_or_next_action=<specific next action|null>
```

如果某个 rigid-only asset 没有 articulation，不能写 `articulation_closure=PASS`；应写
`NOT_APPLICABLE` 或 `NOT_REQUIRED`。如果复制只跑到 Stage 1/2/3/4a，只能说对应阶段可复用，
不能说完整 runtime workflow 已复用。

## 产品表述

可以说：

> ConvertAsset 已经把 DryingBox 做成 AAN-ready package。它不是只把 USD 文件复制过来，
> 而是连依赖、材质、物理、铰接、Isaac 4.1 runtime smoke 和 EBench task contract
> 都有 manifest 证据。LabUtopia / GenManip 这边已经把它接入 `level1_open_door`
> 的本地 EBench / GenManip live smoke，并证明 reset、step、render、metric、logging
> 都能产出证据。这个结果已经发布到 6.15 PM/weekly HTML，no-local-repair guard 也已在位。
> 复制验证也已经推进到 `MuffleFurnace` 和 `Beaker_01`：两个新资产完成收货、验货、
> task-root 挂载 dry-run、no-local-repair verify 和 Stage 4a runtime adapter preflight；
> generic AAN task lane / manifest-routing adapter 已补上。`MuffleFurnace` 和
> `Beaker_01` 都已通过 generic Stage 4b live smoke，因此 Stage 6 replication
> hardening 已 PASS；evaluator 语义执行和 full visual/material parity 会作为后续工作单独推进。

不能说：

> official EBench leaderboard score 已经完成；任意 USD / MJCF / deformable / liquid
> 都自动可评；full visual material parity 已经无损证明。

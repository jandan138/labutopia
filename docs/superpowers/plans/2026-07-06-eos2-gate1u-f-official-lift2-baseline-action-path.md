# EOS2 Gate 1U-F Official Lift2 Baseline Controller/Action Path Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Do not run live Isaac before the F1 equivalence gate is written and reviewed.

**Goal:** After E2R5 closed the current direct 16D `joint_position` route, review the official Lift2 baseline controller/action path without disguising the same failed payload as a new attempt.

**Current Evidence:** E2R4 showed target reaches controller but `right_joint1` does not physically track after a 60-step hold. E2R5 closed only the current direct 16D route, not the whole LabUtopia-to-EBench project.

## PM Summary

我们现在不是继续试开门，也不是继续调 offset。E2R4 已经证明“手动给 Lift2 一个 16D 关节 target”这条路线不可靠：target 进了 controller，但关节没跟着动。下一步看 official Lift2 baseline 口径。

但初步源码审计发现，official baseline 也不是魔法接口：OpenPI/Pi0 的 `prep_output` 会把模型输出的 19D action 转成 EBench/GenManip 的 16D `joint_position` 加 3D `base_motion`。所以不能简单“换官方 baseline 再跑一次”。必须先确认官方 payload 和 E2R4 payload 是不是同一个东西。如果等价，就不能再跑；如果有真实差异，才允许一次新的 bounded controller sanity live。

## 2026-07-06 Decision Boundary

多角度 review 后，本阶段的目标不是“继续试到开门”，而是尽快回答两个 yes/no 问题：

1. `official Lift2 baseline action path` 是否只是 E2R4 失败的 direct 16D `joint_position` payload 换了名字。
2. 如果它确实不同，它在当前 GenManip / EBench runtime 下是否能形成 `action -> controller target -> physics motion -> worker obs` 闭环。

短期最早能说“这条控制路线有戏”的节点是 F2：non-DryingBox sanity live 里 no-op 和 terminal hold 在 closed readback 下达标。短期最早能说“当前 selected controller/articulation repair route 也不行”的节点可以是 F1c、F1e 或 F2：如果 F1c 命名不出真实、单一、可验证的下一路由，就不启动 live；如果 F1e 不能证明 scoped repair 已进代码且区别于 E2R4 unchanged path，就不启动 F2；如果 F1e 通过但 F2 target applied 后相关物理通道有响应但未达到 predeclared motion/error threshold，就停止这条 selected repair route。

完整的产品“弄好”不是 F2，而是 Gate 5 `Expert Oracle Score`：必须看到 Franka native expert 或 Lift2 oracle / retarget 在同一套 EBench metric 下产生有效 score，并有 action log、metric trace、result_info、render/readback 证据。F2 只能证明底层控制可用，E4 只能证明 DryingBox precontact 有工程成功信号，Gate 4 才接近“会带动门”，Gate 5 才是评测出分闭环。

## Current F2 Decision Checkpoint

F1d/F1e 已完成。当前不是继续选修复点，也不是回到 DryingBox，而是先做 F2 command preflight；preflight 通过后最多只允许一次 non-DryingBox F2 live。

F2 的一句话定义：它是底层控制小考，不是开门测试、不是 DryingBox 测试、不是 score 测试。它只问修后的 `Lift2 arm runtime max-effort-only repair` 能不能让 `right_joint1` 在 `action -> controller target -> physics motion -> worker obs` 链路里真实动起来。

F2 的 pass 必须同时满足这些硬条件：

- Horizon 固定为 E2R4 风格的 `5 no-op + 5 ramp + 60 terminal hold`，共 `70` steps，不加 hold、不换 seed、不扫 offset。
- Requested target 与 controller applied target 的误差 `<= 1e-5 rad`。
- `right_joint1` / action slot `8` 的 runtime `drive_max_effort` 读到 repaired value，按当前 F1e 修复应为 `>= 999999.0`。
- 对 `+0.20 rad` command，`right_joint1` 从 reset baseline 起同向移动至少 `0.18 rad`。
- Terminal hold 最终 `right_joint1` error `<= 0.02 rad`。
- `readback_errors=[]`，并且 `planned_steps == executed_steps == 70`。

F2 telemetry-blocked 的硬字段清单：

- `target_action_16d` 或等价 requested target。
- `applied_joint_position_target_16d` 或等价 controller applied target。
- `right_joint1` 的 observed position / target / error，至少包含 final step；最好包含 per-step series。
- action slot mapping：slot `8` -> global DOF `9` -> `fr_joint1` / `right_joint1`。
- final controller drive debug：至少能读出 slot `8` / `right_joint1` 的 `drive_max_effort`。
- final runtime motion debug：`joint_position`、`joint_velocity`、limits；`max_joint_velocity` 如果仍为 null，只能记 caveat，不能单独当 retry 理由。
- right-arm EEF world pose / delta 是二级佐证：如果缺失，不能使用“EEF 也无响应”作为 no-go 依据；但只要 joint target / applied / observed / max-effort schema 闭合，F2 仍可按 joint-level sanity 判定。

F2 的失败不是项目失败。完整 telemetry 下若 target applied、max effort repaired，但 `right_joint1` 的同向运动不足或 terminal error 超过阈值，下一状态是
`LOCAL_NO_GO_LIFT2_ARM_RUNTIME_MAX_EFFORT_REPAIR_ROUTE_REVIEW_HIGHER_LEVEL_OFFICIAL_RUNNER_OR_ACTION_ABSTRACTION`。
这只关闭当前 max-effort repair route，不关闭 LabUtopia-to-EBench，也不关闭 official Lift2 baseline 的所有可能分支。

## F2 Command Preflight Result

F2 command preflight 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_preflight_20260706.json`。
这仍不是 live evidence，`live_runs_consumed=0`。它只是把唯一一次 F2 live 的 runbook 固定下来：

- `port=18132`，precheck 结果为 `PORT_18132_FREE`。
- `server_parent_run_id=eos2_gate1u_f2_lift2_max_effort_controller_sanity_20260706_parent_0001`。
- `client_run_id=eos2_gate1u_f2_lift2_max_effort_controller_sanity_20260706_0001`。
- evidence dir 固定为 `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_live_20260706/`。
- 必须先启动 `ray_eval_server.py`，再用 `genmanip_client.cli submit ebench/labutopia_lab_poc/lift2_candidate/level1_open_door` 加载任务，最后运行 `lift2_controller_reference_probe.py`。
- F2 live 仍使用 E2R4 同款 `5 no-op + 5 ramp + 60 hold`，不加 hold、不改 action API、不换 seed、不扫 offset、不接触、不 micro-pull、不 score。
- F2 专属命令文件已经落地到 `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_live_20260706/server.command.txt` 和 `runner.command.txt`；禁止使用 E2R4 的 `18131` 命令文件。
- `runner.command.txt` 会在 probe 启动前写 `live_consumed_at.txt`，并拒绝在已有 `summary.json`、`trace.jsonl`、`runner.exit_code.txt` 或 `live_consumed_at.txt` 时重跑同一路线。
- `runner.exit_code.txt` 只是 probe process result，不是 F2 pass authority。F2 pass 必须检查 `summary.json` 中 hard checklist，尤其是 `right_joint1_motion`、requested/applied diff、max effort、terminal error 和 `readback_errors`。

preflight 同时记录了一个工程边界：本次 live 将使用 GenManip worktree 当前状态，包括 F1e 修改后的 `lift2.py` 和当前 untracked probe/test 文件。结果必须绑定上述 run_id、port、RAY_TMPDIR 和 evidence dir，不能和 EOS 或其他工程师的 run 混用。

第一轮多 agent review 指出两个问题：需要 F2 专属实体命令文件；pass table 不能只看 runner classification。这两点已修复。复审结论是 command/env 与 readback/stop-go 口径均可释放 exactly one F2 live，但 runner classification 仍不能自动解锁 F3，必须用 hard checklist 判定。

2026-07-06 pre-live infra check 还暴露并修复了一件纯基础设施问题：首次 server start 在 runner 启动前失败，原因是 Ray `AF_UNIX` socket 路径超过 107 bytes。该失败已经按 infra attempt 保留到 F2 live evidence dir 的 `server_attempt_0001.*`，并把 `RAY_TMPDIR` 缩短到 `/tmp/gf2_18132`。因为当时没有 `live_consumed_at.txt`、`summary.json`、`trace.jsonl` 或 `runner.exit_code.txt`，所以 F2 live budget 仍是 `0/1`。后续 server 可启动只说明考场能开，不等于 F2 pass；真正的唯一 F2 live 仍必须由 `runner.command.txt` 写入 marker 后消费。

当前硬止损口径：F2 一次 live 后只允许四类结果。PASS 才解锁 F3/E3/E4；完整 telemetry 下 target applied、max effort repaired 但 `right_joint1` 同向运动不足或 terminal error 超阈值，则 local no-go 并切 higher-level official runner / action abstraction review；硬字段缺失则 telemetry blocked；server/submit/reset/runner 在 `summary.json` 前失败则 infra blocked。任何情况下都不能把 F2 失败扩大成项目 no-go，也不能把 F2 pass 扩大成开门或得分。

## F2 Live Result

F2 exactly-one live 已执行并登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_live_20260706/result_compact.json`。

Canonical status 是
`LOCAL_NO_GO_LIFT2_ARM_RUNTIME_MAX_EFFORT_REPAIR_ROUTE_REVIEW_HIGHER_LEVEL_OFFICIAL_RUNNER_OR_ACTION_ABSTRACTION`。
这不是 PASS，也不是 telemetry blocked。硬证据如下：

- `planned_steps=70`、`executed_steps=70`、`step_sample_count=70`。
- action slot `8` 映射到 global DOF `9` / `right_joint1`。
- requested target `0.20090151123rad` 到 controller applied target `0.20090150833129883rad`，diff 约 `2.90e-09rad <= 1e-5rad`。
- runtime `drive_max_effort[8]=1000000.0`，证明 F1e max-effort repair 在 live 中生效。
- `right_joint1` 不是完全没动：requested-direction movement 约 `0.11047rad`，比 E2R4 的近零响应有改善。
- 但 F2 pass 要求 movement `>=0.18rad`，实际 `0.11047rad` 不达标；terminal error 约 `0.08953rad`，也高于 `0.02rad` 阈值。
- `readback_errors=[]`，所以这不是 telemetry blocked。

产品口径：这次像是在测“电机给足力以后，关节能不能按指令转到位”。结果是指令送到了，电机出力上限也调高了，关节也朝正确方向动了；但它没有动到预先要求的位置，离目标还差约 `0.0895rad`。所以当前 `Lift2 arm runtime max-effort-only repair` 路线不足以支撑 DryingBox E3/E4，更不能支撑 contact、micro-pull 或 `Expert Oracle Score`。下一步不能同路线加 hold、调 gain、换 seed、扫 offset 或换 API，只能先做 higher-level official runner / action abstraction 的 zero-live review。

## F2a Post-F2 Stop-Go Plan

F2a 的目标不是继续 live，而是回答“还剩没有真正不同的新路线”。多角度 review 后的当前判断：
`physics_hold_steps` 是 diagnostic-only，需要 `GENMANIP_ALLOW_DIAGNOSTIC_PHYSICS_HOLD=1` 才允许，不能作为 official next route；
`step_chunk_size` 只改变 chunk/RPC/trace 形态，不改变 `env.step(action)` 中的控制语义；
official prep-output / `base_motion` 仍把 arm 部分落到同一个 16D `joint_position` path，`base_motion` 是独立底盘通道，不能解释
`right_joint1` tracking 不达标。

因此，预计收敛边界改为四步：

1. F2a provenance review：只读源码和已产物，证明是否存在一个真正不经过当前
   `env.py -> set_joint_position_targets -> world.step` 语义的 official runner / action abstraction。
   如果找不到，关闭 F-stage lower-level action 分支，不再 live。
2. F2b offline capability ceiling：只有 F2a 找到真实新路线后，才做本地离线上限验证。固定同一任务和初始状态，证明新路线能稳定达到
   movement `>=0.18rad` 且 terminal error `<=0.02rad`。如果只能在 diagnostic hold、非官方 runner、不可提交 hack
   或偶发状态下达标，就判当前新路线不可交付。
3. F2c canonical packaging：把 F2b 证明可行的路线封装成可复现 canonical command / artifact，而不是实验脚本。
   必须 repeated run 稳定达标，target/applied readback 仍闭合，且没有新增 telemetry 缺口。
4. F2d live go/no-go：只有 F2c 通过后才允许下一次 live。live 只能用于确认已验证方案，不能用于探索。

产品口径：现在离“弄好”最近的可判定节点不是再跑一次，而是 F2a/F2b。如果 F2a 找不到真实不同的官方动作路线，
或者 F2b 证明新路线在本地也过不了 `>=0.18rad` / `<=0.02rad`，就应宣布当前 official lower-level action 分支弄不好。
完整“弄好”仍不是 F2a/F2b，而是后续回到 DryingBox E3/E4、contact、micro-pull，最终到 F5/Gate 5 产出
`Expert Oracle Score` 证据。

## F2a Review Result

F2a zero-live provenance review 已完成并登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2a_provenance_review_result_20260706.json`。

结论是 `F2A_FAIL_NO_TRUE_NEW_OFFICIAL_ACTION_ABSTRACTION_CLOSE_F_STAGE_LOWER_LEVEL_ACTION_BRANCH`。
EOS 侧没有找到 official/OpenPI Pi0 runner 的新动作语义：当前路径仍是 `50x19` model action 经
`official_prep_output_actions()` 变成 16D `joint_position` + 3D `base_motion`，再 POST 到 GenManip
`/step_chunk`。GenManip 侧也没有找到可进入 F2b 的新 runtime control surface：`step_chunk` 逐条调用
`env.step`，`env.step` 最终调用 `robot_view.set_joint_position_targets(...)` 后 `world.step(...)`。

F2a 同时排除了几个容易误会的候选：`base_motion` 是独立底盘通道，不修 `right_joint1`；`physics_hold_steps`
是 diagnostic-only；`step_chunk_size` 只改变 batching/trace；`ee_pose` 和 `custom_motion` 会先转成 joint
targets；`native_drive_target_controller` 是单独 research/control lane，并且 EOS 文档明确不 claim official
benchmark reproduction 或 standard model score。

因此当前 F-stage lower-level official/OpenPI action 分支关闭：不进入 F2b、F2c 或 F2d，不允许再用同分支
live retry。产品口径：我们不是“还没试够”，而是已经证明这条底层动作接口链路没有第二条隐藏通道；继续 live
只会重复同一类失败。下一步必须回到更高层路线决策，而不是在这个分支上调参数。

## Live Budget / Stop Line

F1b 后，live budget 继续冻结。不能因为换成 official baseline 名字就启动 F2。当前 `lift2_arm_runtime_max_effort_only_repair` 只允许一次 F2 live；后续任何 live 必须先有新的 zero-live review，把它定义成独立路线，而不是同一路线 retry。本阶段最多允许 3 次 future live，而且有硬前提：

- Live 1：只有 F1e code/test checkpoint 证明 F1d 选中的 max-effort-only repair 已实现、范围干净且区别于 E2R4 unchanged path 时，才允许一次 `baseline-compatible controller sanity live`。
- Live 2：只能在 Live 1 / F2 pass 后触发，用于验证 wrapper boundary；如果 F2 fail，Live 2 不允许作为同路线 retry。
- Live 3：只有 Live 2 定位到一个单一、可验证的修复点时，才允许一次修复验证 live；它也不能从 F2 fail 直接触发。

如果没有明确单点 hypothesis 或 F1e 代码测试不过，不允许 Live 1。当前 max-effort repair 的 Live 1 失败且 telemetry 完整时，必须停止该 repair route，不继续加 hold、调 gain、换 seed、扫 offset、改 API 或回到 DryingBox 盲试。Live 3 失败后必须停止。

## Decision Ladder

| Stage | Purpose | Pass Means | Stop / Fail Means | PM Wording |
| --- | --- | --- | --- | --- |
| F0 zero-live official source audit | 只读 EOS / GenManip 源码，确认 official baseline action path 的真实接口 | 已完成：official prep output 是 19D -> 16D joint_position + base_motion | 如果找不到官方 action transform，不能 live | 先搞清楚“官方动作语言”到底是什么。 |
| F1 official prep-output equivalence harness | 不启动 Isaac，对比 official prep-output 生成的 payload 和 E2R4 direct payload | 能明确分类：等价 / base-motion 差异 / endpoint 差异 / 真正不同语义 | 如果等价，不允许以 official 名义重跑 E2R4 | 防止换名字重复跑同一个失败动作。 |
| F1b official runner endpoint/base-motion boundary review | 不启动 Isaac，确认 official endpoint / base_motion 是否绕过 E2R4 失败路径 | 已完成：endpoint 仍进 step_chunk -> env.step；base_motion 是独立底盘通道 | 不能把 endpoint 或 base_motion 当作 right_joint1 修复证据 | 官方名字后面没有新的魔法接口。 |
| F1c zero-live single-hypothesis selector | 不启动 Isaac，选择唯一一个真实下一路由：controller/articulation repair、Newton/action homologation、higher-level action abstraction 或 base-only diagnostic | 已完成：选择 controller/articulation runtime repair；Newton 仅 supporting audit；base-only/higher-level 不进 F2 | F1c 不释放 live，必须 F1d 先选具体 repair | 方向选定了，但还没开枪。 |
| F1d concrete repair selector | 不启动 Isaac，把 controller/articulation runtime repair 落到一个具体可测修复点 | 已修订：选择 Lift2 arm runtime max-effort-only repair | F1d 只释放 F1e code/test，不释放 F2 live | 先选一个 runtime actuation 变量，不能直接上机。 |
| F1e code/test checkpoint | 不启动 Isaac，实现并测试 F1d 选定的 Lift2 arm max-effort repair | 已完成 code/test：只给 12 个 Lift2 arm DOF 设置 runtime max effort，测试覆盖 helper 和 `Lift2Embodiment._post_initialize()` 调用 | F1e 不是 live evidence；F2 仍必须经 stop-go review 后只跑一次 | 已证明修复写进代码，而且只修这一件事。 |
| F2 baseline-compatible controller/runtime sanity live | 已执行 exactly one non-DryingBox live | 未通过：`70/70` steps、requested/applied diff `2.90e-09rad`、`right_joint1` max effort `1000000.0`、但 movement `0.11047rad < 0.18rad` 且 terminal error `0.08953rad > 0.02rad` | hard telemetry 完整，因此关闭当前 max-effort repair route；不是 telemetry blocked，也不是项目 no-go | 机器人有响应但不够可控，不能继续同路线调参。 |
| F2a post-F2 provenance / stop-go review | 不启动 Isaac，确认是否存在真正不同的 official runner / action abstraction | 未通过：EOS 与 GenManip 双侧 review 均未找到不落到当前 `set_joint_position_targets -> world.step` 语义的新路线 | 关闭 F-stage lower-level official/OpenPI action 分支；不进入 F2b/F2c/F2d | 已确认没有隐藏的新动作接口，不能换名字再试。 |
| F2b offline capability ceiling | 只有 F2a pass 后才做本地离线上限验证 | 当前不进入，因为 F2a fail | F2a fail 已阻断；不能为了探索而启动本地/ live 尝试 | 没有新路线，就没有本地上限验证对象。 |
| F3 DryingBox E3/E4 resume gate | F2 通过后才恢复 DryingBox static compute + one-segment precontact | E4 precontact 到位，contact clean | F2 未过或 F1 等价时继续 blocked | 底层动作通了，才回到开门专家路线。 |
| F4 contact / retention / micro-pull gates | E4 通过后才检查接触、保持和微拉门 | door joint 有方向性变化，contact 归因 clean | 任一 gate 失败，只能定位失败层，不能算 score | 这里才接近“工程上能带动门”。 |
| F5 Expert Oracle Score | 在 EBench metric 下 replay expert / oracle | score / reward / success 有效记录，证据可复现 | metric 不涨或 door joint 不动，则 score 路线未成立 | 这里通过才叫“评测出分闭环”。 |

F3/F4/F5 目前只是后续 checkpoint，不是可直接执行的 live 指令。每个阶段在启动前都必须单独补 command preflight，写清 EE tolerance、contact attribution fields、door-joint 最小变化量、score artifact 文件名和 metric key。否则只能停在 planning / telemetry-blocked，不能用“看起来有点动”来判 pass。

## F0 Findings

- EOS `adapters/ebench/official_runner_probe.py` 的 `official_prep_output_actions` 使用 19D model action：前 12 维是 arms，12:16 是 gripper，16:19 是 cumulative base pose；输出 worker payload 是 16D action + `base_motion`。
- 输出 16D joint order 是 `left_arm6,left_gripper2,right_arm6,right_gripper2`，`control_type="joint_position"`，`is_rel=false`，`base_is_rel=true`。
- GenManip `lift2_eval_contract_probe.py` 已经把 `openpi_relative_base_motion` 作为 Stage 7 action dialect。
- GenManip evaluator 仍通过 `robot_view.set_joint_position_targets(... default_dof_indices)` 应用 16D joint target，并单独通过 `delta_move_to` 应用 relative base motion。
- 因此 official baseline review 的第一件事不是 live，而是证明 official-prep payload 是否真的不同于 E2R4。

## F1 Terminal Zero-Base Arm-Only Result

F1 terminal zero-base arm-only code/test equivalence harness 已完成并登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1_official_prep_output_equivalence_20260706.json`。

用 E2R4 `summary.json` 的最终 `applied_joint_position_target_16d` 生成 official 19D row，再走 official
prep-output helper，得到的 arm-only zero-base payload 分类是
`EQUIVALENT_TO_DIRECT_16D_PAYLOAD`：`joint_action_max_abs_diff=0.0`、
`base_motion_max_abs_diff=0.0`、`metadata_diffs=[]`。验证命令：
`test_official_lift2_baseline_action_equivalence.py` + 相邻 controller/evaluator tests 共 `40 passed in 0.89s`，
`py_compile` 和 `git diff --check` 也为 exit `0`。

结论：不允许跑 terminal arm-only zero-base official F2 live，因为它会重复 E2R4 的 direct 16D 失败 payload。
这个 manifest 不证明 no-op / ramp / full official policy 19D trajectory / full horizon / endpoint / wrapper
boundary 等价。它只在同一个 terminal arm payload 的 synthetic probe 里显示非零 `base_motion` 是
payload-level 差异；但 base motion 不能解释或修复 E2R4 的 right-arm joint tracking blocker。下一步必须是
F1b zero-live official runner endpoint/base-motion boundary review，不能直接 live。

## F1b Official Runner Endpoint/Base-Motion Boundary Result

F1b zero-live source-boundary review 已完成并登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1b_official_runner_endpoint_base_motion_boundary_20260706.json`。

多角度 review 后的合并结论是：没有发现 official runner endpoint 绕过 E2R4 所验证的核心 action application
path。official OpenPI/Pi0 chunk runner 会把 19D action prep 成 16D `joint_position` + 3D `base_motion`，
然后走 GenManip `/step_chunk`；E2R4 reference probe 也走 `client.step_chunk(...)`。server 侧最终都进入
`IsaacWorker.step_chunk -> IsaacEvalEnvRay.step`。`step_chunk` 主要改变 batch / observation / render
cadence，不改变 16D arm target 的应用语义。

`base_motion` 是真实差异，但它是底盘控制通道：在 `env.step` 中与 arm/gripper `action` 分开读取和应用。
它可以成为后续 base-only semantics diagnostic，但不能解释或修复 E2R4 的 `right_joint1` arm no-motion。
因此 terminal arm-only zero-base official F2 live 不允许；endpoint 差异也不能作为 F2 理由。

F1b 后的下一步不是 live，而是 F1c zero-live single-hypothesis selector：必须先选出一个真实下一路由
（controller/articulation runtime repair、Newton/action homologation comparison、higher-level official
action abstraction，或独立的 base-only diagnostic），并写清 readback、tolerance、一次 F2 命令和失败停止线。
如果 F1c 命名不出单一、可验证的真实差异，就在 F1c 判当前 official-as-duplicate lower-level route no-go；
如果 F1c 通过但 F2 仍 target applied 而相关物理通道达不到 movement/error 阈值，就在 F2 判该路线 no-go。完整“弄好”仍必须到
F5 `Expert Oracle Score`：有 score / reward / success、action log、metric trace、`result_info.json`、
render 和 readback 证据。

## F1c Single-Hypothesis Selector Result

F1c zero-live selector 已完成并登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1c_single_hypothesis_selector_20260706.json`。

多角度 review 选择 `controller_articulation_runtime_repair` 作为唯一下一路由。原因很直接：
E2R4 的 failure 不是 action transform ambiguity，也不是 endpoint difference。`right_joint1` 的 requested
target 是 `0.200753768836rad`，controller applied target 是 `0.20075376331806183rad`，但 worker readback
仍接近 `0rad`，60-step hold 后 error 约 `0.20075764784227174rad`。这正是 controller target ->
Lift2 physical articulation motion 没闭合。

F1c 同时拒绝三个容易误用的方向：

- Newton/action homologation 只能是 supporting audit。它证明 official commands 在 Newton backend 上可表示，
  但 backend/control surface 不同，不能证明 GenManip/Isaac runtime tracking。
- higher-level official action abstraction 当前不释放 F2。F1/F1b 已证明 official arm-only terminal payload
  和 endpoint 没有提供新的 arm controller。
- base-only diagnostic 当前不释放 F2。`base_motion` 是真实底盘通道，但不能修 `right_joint1`。

F1c 不释放 live。下一步是 F1d zero-live concrete repair selector：必须选 exactly one runtime repair family，
写清 source-level change、为什么不是重复 E2R4、F2 command/readback/tolerance/no-go condition。只有 F1d
通过后，F2 才能跑一次 non-DryingBox bounded live。

## F1d Concrete Repair Selector Result

F1d zero-live concrete repair selector 已完成并登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1d_concrete_repair_selector_20260706.json`。

选择的唯一修复族已根据后续 review 修订为 `lift2_arm_runtime_max_effort_only_repair`。理由是 E2R4 已证明
target 到了 controller，但 `right_joint1` 不物理跟踪；Isaac `set_joint_position_targets` 和 `apply_action`
都会写同一底层 DOF position target，因此 API swap 不是清晰差异。当前最具体的未闭合 runtime actuation
变量是 arm DOF max effort：E2R4 读到 `right_joint1` runtime `drive_max_effort=100.0`。

F1d 不释放 F2 live。它只释放 F1e code/test checkpoint：在 GenManip 中实现 Lift2 arm runtime
max-effort-only repair，加 focused test 证明 arm max effort 被设置到修复值，并确认没有混入 API swap、
gain/max-velocity/hold/base/DryingBox 修复。

## F1e Code/Test Checkpoint Result

F1e code/test checkpoint 已完成并登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1e_lift2_runtime_max_effort_code_checkpoint_20260706.json`。

GenManip 变更只落在 `genmanip/extensions/robots/default/r5a/lift2.py` 和 focused test：
`tests/labutopia_poc/test_lift2_runtime_max_effort_contract.py`。实现新增
`LIFT2_ARM_RUNTIME_MAX_EFFORT=1000000.0` 和 `set_lift2_arm_runtime_max_efforts()`，并在
`Lift2Embodiment._post_initialize()` 的 `super()._post_initialize()` 之后调用。这个位置避免了
`ArticulationView.set_max_efforts` 在未初始化时直接 no-op。修复只覆盖 12 个 arm global DOF：
`[10,12,14,16,18,20,9,11,13,15,17,19]`，不覆盖 base、lift 或 gripper DOF。

TDD 证据：focused test 先 RED 到缺少 helper/constant；source audit 后又收紧到 `_post_initialize()`
runtime 时机，并 RED 到 `max_effort_calls == []`；GREEN 后 focused `2 passed in 0.11s`。相邻 suite
`20 passed in 0.50s`，`py_compile` exit 0，`git diff --check` exit 0。

F1e 不是 live evidence，不证明 Isaac 里 `right_joint1` 已经会动。它只证明 F1d 选中的 scoped repair
已干净进入代码，可以进入 F2 stop-go review。F2 仍只能是一次 non-DryingBox 小动作 live；若 repaired max
effort 读到、target applied，但 `right_joint1` / EEF 的同向运动不足或 terminal error 超阈值，则关闭当前 max-effort repair route。

## Required Next Work

1. F2 stop-go review：
   - 复核 F1e diff 只改 Lift2 arm runtime max effort，没有混入 action API / gain / max velocity / hold / base / DryingBox。
   - 明确 F2 exact command、70-step horizon、hard telemetry schema、readback、tolerance 和 no-go condition 后，才释放一次 non-DryingBox bounded live。

2. F2 live gate：
   - 只有 F2 stop-go review 通过才允许。
   - 仍然 non-DryingBox，不 contact，不 micro-pull，不 score。
   - 必须复用 E2R4 telemetry fields，并新增 F1c 指定的 channel-specific readback。
   - F2 通过只解锁 F3，不代表 door opened、policy score 或 official leaderboard score。
   - F2 已执行且 hard telemetry/readback 完整：target applied、max effort repaired，`right_joint1` 有同向运动但不足 `0.18rad`，terminal error 超过 `0.02rad`，因此进入 `LOCAL_NO_GO_LIFT2_ARM_RUNTIME_MAX_EFFORT_REPAIR_ROUTE_REVIEW_HIGHER_LEVEL_OFFICIAL_RUNNER_OR_ACTION_ABSTRACTION`；不在同一路线上继续加 hold、调 gain、换 seed、扫 offset 或换 API。
   - 如果 F2 telemetry/readback 本身缺失，则归类为 telemetry blocked，先补判读能力；不能把它算成 max-effort repair no-go。

3. F2/F3 stop-go review：
   - F2 pass：允许恢复 DryingBox E3 static compute 和 E4 one-segment precontact。
   - F2 fail 且 telemetry 完整：关闭当前 max-effort repair route，进入 higher-level official runner / action abstraction review。
   - F3/E4 pass：才允许 Gate 2 contact；F3/E4 fail 不能扩大成 official baseline 失败。
   - Gate 5 pass：才允许对外说 `Expert Oracle Score` 闭环。

4. F2a/F2b post-F2 route review：
   - F2a 只读审计 official runner / action abstraction provenance，不能启动 Isaac live。
   - `physics_hold_steps` 因 diagnostic-only 被排除；`step_chunk_size` 因不改变 action semantics 被排除；
     official prep-output / `base_motion` 因 arm 仍落到同一 16D joint-position path 被排除为 right-arm tracking 修复理由。
   - F2a 已完成且 fail：没有真正不同的新路线，关闭 F-stage lower-level official/OpenPI action 分支。
   - F2b/F2c/F2d 均不进入；下一次 live 必须来自新的上层路线计划，不能沿此分支继续。

## Blocked Claims

- 不说 official Lift2 baseline 已经在 LabUtopia/EBench runtime 可评。
- 不说 official baseline 一定能修复 E2R4。
- 不允许把和 E2R4 等价的 payload 换名再跑。
- 不允许在 F2 pass 前恢复 DryingBox E3/E4 或 Expert Oracle Score。
- 不允许把 F2 controller sanity pass 说成 door opened、policy score 或 official leaderboard score。
- 不允许把 F2a fail 说成项目 no-go；它只关闭 F-stage lower-level official/OpenPI action 分支。

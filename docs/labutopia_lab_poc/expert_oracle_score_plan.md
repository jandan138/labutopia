# Expert Oracle Score Plan

Date: 2026-07-02

## 目的

当前 LabUtopia / EBench consumer smoke 已经证明 AAN package 能进入 runtime，完成
reset / step / render / metric / logging，并写出 `result_info.json`。但这些 smoke
run 使用的是 EBench / GenManip eval client 的普通 action path，不是 LabUtopia expert
controller，也不是训练好的 policy，所以 `score=0.0` 不能说明 expert 失败。

`Expert Oracle Score` 阶段要补的是另一层证据：如果把“专家答案”接到同一套 EBench
metric 下，评分器应该能给出高分。它用来证明 metric、layout、runtime planner path
和 action execution / readback 是可信的，再往后才进入真实 policy 或 official
leaderboard 评测。

一句话给 PM：现在已经证明“考场能开、卷子能交”；`Expert Oracle Score` 要证明“标准答案
放进去能拿分”。这和真实模型成绩仍然是两件事。

> **当前唯一 canonical 主线（2026-07-07）：** S0 frozen expert action source 已完成；S1/M1 formal score-chain 已通过，Route B fresh S1 得到 `score=1.0` / `success_rate=1.0`。S2-L1 先暴露过 terminal readback/render 证据缺口，S2-L1R 又先后暴露过 `curobo` import、Ray socket path、CUDA runtime / `ninja` 环境合约问题；这些都不能评价 expert route。最新 S2-R1E full-env repaired replacement replay 已跑通：run id `eos2_s2_l1r_full_env_repaired_route_b_readback_render_20260707_003`，official `score=1.0` / `success_rate=1.0` / `metric_score=[[[1.0]]]`，最终 DryingBox `RevoluteJoint=41.715865deg`，落在 EBench `CheckJointAngle` 要求的 `[30,120]deg` 内，`metric_input.within_range=true`，`succ_cnts=59`，terminal camera artifact 和 canonical `camera2.mp4` 都存在。因此 M3 single-episode Expert Oracle Score 的 score/readback evidence 已可签收；下一步不释放 S2-L2、不重跑 S1，转入 M4/S4 small-sample robustness 或 S3 Lift2 oracle/retarget。视觉材质 parity、正面产品图质量、policy score、official leaderboard 仍是 blocked/follow-up。下方 Gate1V / Lift2 / E2R / F-stage 内容是历史或并行分支记录，不能覆盖这条当前主线。

## 2026-07-06 Stop-Go 总控 Roadmap

多角度 review 后，`Expert Oracle Score` 的“预计到哪一步能弄好 / 到哪一步判不行”已经单独固化为
[`../superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md`](../superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md)，
对应 evidence manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_stop_go_roadmap_20260706.json`。这份 roadmap
不是 live evidence，也不释放 score claim；它的作用是阻止继续盲试，把后续判断压成 M1-M4 / S0-S4 的硬门。

给 PM 的通俗版本：

| 阶段 | 要回答的问题 | 通过后能说什么 | 过不了怎么停 |
|---|---|---|---|
| M1 | 真实 EBench 是否能产出 `result_info.json` / `episode_result.score`？ | 正式考场能交卷，哪怕分数还是 0 | 停 oracle，先修 runner / evaluator lifecycle |
| M2 | expert action 是否能通过正式控制接口改变 EBench 场景？ | 动作不是只在日志里，确实进入仿真 | 停 score，修 action schema / control mapping |
| M3 | 分数、物理 readback、metric input 和渲染证据是否共同证明一次 expert/oracle 成功？ | 单 episode Expert Oracle Score POC 可信，值得继续做稳定性 | 分数和物理/readback 证据对不上，或有限 Franka/native 与 Lift2/retarget 都失败后，关闭当前 score route |
| M4 | 3-5 个 episode / seed 是否稳定？ | 可以进入交付级扩展 | 不扩大规模，回到主失败类型 |

2026-07-07 最新签收口径：S2-R1E 已经把 M3 的“分数 + 物理 readback + metric input + 渲染 artifact”补齐。
正式结果是 `score=1.0` / `success_rate=1.0`，`metric_score=[[[1.0]]]`；终态门角是
`41.715865deg`，在 EBench `CheckJointAngle` 的 `[30,120]deg` 成功范围内；`succ_cnts=59`；
`camera2.mp4` 为 512x512、579 帧、约 19.3 秒。对应 result review manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1e_full_env_repaired_result_review_20260707.json`。
所以当前可以说 **single-episode Expert Oracle Score POC 的 score/readback evidence 已闭环**。但它仍不是
M4 小样本稳定，不是 policy score，不是 official leaderboard，也不是 Lift2 official baseline；视觉材质
parity 和正面产品图质量也要单独 review。

工程执行口径对应 S0-S4：S0 先冻结 EBench-executable expert action source；S1 验证 formal score chain；
S2 跑 Franka native expert under EBench metric；S3 再做 Lift2 oracle / retarget smoke；S4 才做
small-sample robustness。正式分数仍只认
`post_episode_process -> episode_result.score -> saved/eval_results/<benchmark>/<run_id>/<task>/<seed>/result_info.json`。
diagnostic `metric`、`done_info.info`、render 图、fake-client summary 和历史 `expert_oracle` 命名目录都不能替代这个证据。

2026-07-06 最新 stop-go refresh：S0 已经从历史 blocker 变成已完成项。早期 S0 native capture 先后暴露过
wrong Python `isaacsim` import、7D/9D action-dim contract、failed episode logger lifecycle 三个问题；
这些都已通过 bounded repair 和 lifecycle-validation capture 关闭。当前 frozen source 证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json`：
905 条连续 9D `joint_position`，freezer sha256 为
`e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f`。因此不再重复 S0。
S1 release review 随后执行到两次 bounded attempt；attempt2 产出了
`result_info.json`，但 runner locator、`metric_score` 和 step0 early-done 合约未闭，因此当时转入
S1R zero-live repair。S1R-A 已修好 result locator。S1R-B 审计后没有创建 waiver：attempt2 的
`metric_score=[]`、`episode_start_time=null`、`episode_end_time=null` 表明它是 minimal fallback
artifact，不是完整 recorder finalize artifact，所以 fresh S1 仍 blocked。S1R-B2 full finalize lifecycle
code checkpoint 已完成：done 但 recorder 仍存在的 terminal episode 不再被跳过 finalize path，相关 no-live
测试 `15 passed`。S1R-C step0 invalid-state attribution 也已完成：attempt2 的 EBench reset 到第一条
frozen action 最大关节跳变为 `2.734214574098587rad`，超过 `1.0rad` invalid guard，因此这是 reset/action
contract mismatch，不是 expert 质量失败。S1R-D release review 现已完成，按 Route B 构造了 provenance 分开的
bounded settle/bridge：先加 14 步 `s1r_route_b_settle_bridge`，再接原始 905 步 frozen expert replay，总共
919 步 9D `joint_position`，bridged source sha256 为
`fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`。这次 exactly one fresh S1 已经执行并
通过 M1：有效 runner invocation exit `0`，summary classification 为
`PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT`，canonical `result_info.json` 中 `score=1.0`、
`success_rate=1`、`metric_score=[[[1.0]]]`，same-run `action_log.jsonl` / `metric_trace.jsonl`
均存在。它证明 M1/S1 formal score-chain 已通过并拿到正分候选；S2/M3 仍需补 door joint readback、metric input dump、
render/snapshot 和 route-claim review，不能直接说 Expert Oracle Score complete。

S2 no-new-live inventory 和 claim review 现已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_readback_render_inventory_20260706.json` 与
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_claim_review_20260706.json`。结论是
`S2_BLOCKED_READBACK_RENDER_EVIDENCE_GAP_NO_NEW_LIVE_RELEASE`：当前 fresh S1 的 `result_info.json`、
`action_log.jsonl` 和 `metric_trace.jsonl` 足够支撑 M1 / positive score candidate，但同一 run 只在 reset
observation 里有 robot `state.joints` 和 `video.camera2_view`，没有 DryingBox `RevoluteJoint` 初末角、
metric input dump、success counter trace 或终态正面渲染图。官方 metric code 确认它应读取
`scene.articulation_list["obj_DryingBox_01"]` 的 `RevoluteJoint`，成功范围是 `30-120deg`，`succ_cnts=59`。
因此下一步不是 S1 retry，也不是继续调分数。S2-I0 runner instrumentation code checkpoint 已通过；接下来登记
`S2 Instrumented Replay Release Review`，最多释放一次同 frozen Route B source 的 replay，专门补 door
joint readback、metric input dump 和 terminal/front-view render。

S2 instrumented replay stop-go 规则也已固化：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_stop_go_20260706.json`，
计划文档是
[`../superpowers/plans/2026-07-06-eos2-s2-instrumented-replay-stop-go.md`](../superpowers/plans/2026-07-06-eos2-s2-instrumented-replay-stop-go.md)。
2026-07-07 最新状态是：S2-R1E full-env repaired replacement replay 已经通过 M3 score/readback evidence
review，结果 manifest 为
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1e_full_env_repaired_result_review_20260707.json`。
这 supersede 了下面 S2-L1 evidence failure、S2-L1R cuRobo failure、S2-R1C pending replacement replay 的旧状态；
这些旧状态仅用于解释为什么不能在前几轮就下结论。
当前 S2-I0 code checkpoint 已通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_code_checkpoint_20260706.json`。
runner 现在能在下一次 EBench run 里落盘 terminal obs、DryingBox `RevoluteJoint` 角度、metric input /
`succ_cnts` 和 terminal/front-view render 所需的取证接口。S2-R0 release review 也已完成并固定 command、env、
source sha、run id、artifact list 和 stop lines；它释放的唯一 S2-L1 replay 已执行。结果是分数链路通过，
但证据链路没闭合：`terminal_obs_compact.json` 的 `obs_keys=[]`、`debug.labutopia_open_door=null`，
terminal camera artifact 缺失，runner log 有 567 次 `No camera frames provided for this step`。因此当前不能说
M3 single-episode Expert Oracle Score POC 弄好，也不能判 Route B 失败。S2-I1 no-live evidence export
contract repair 已完成；S2-R1 因 producer 缺口 blocked；S2-I2 metric producer snapshot repair 已 no-live
通过；S2-R1B release review 签发的 S2-L1R 已执行但 reset 前因为缺 `curobo` import path 失败，没有进入动作回放。
S2-I3 后 replacement replay 又依次暴露 Ray tmpdir socket path、CUDA runtime / `ninja` 环境合约缺口；这些均已按 no-live repair 处理。最终 S2-R1E `_003` 运行成功并关闭 M3 单集证据。

S2-R0 release review 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_release_review_20260706.json`。
这不是 live result，而是一张准跑证：只释放 exactly one S2-L1 instrumented replay，run id 固定为
`eos2_s2_l1_instrumented_route_b_readback_render_20260706_001`，仍使用同一份 Route B action source sha256
`fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`。server 必须带
`LABUTOPIA_ORACLE_DEBUG_OBS=1`，runner 必须带 `--step-chunk-render-mode always --step-chunk-subframes 2
--trace-final-obs`。这张准跑证已经被 S2-L1 消费，结果 manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_l1_instrumented_replay_result_20260706.json`。
S2-L1 如果缺 terminal obs、door angle、metric input / `succ_cnts` 或 terminal camera artifact，只能判
evidence failure，不能判 Route B expert route 失败；当前 S2-L1 正属于这个分类。只有 post-repair replay
证据完整但 metric/physics 失败，才考虑后续 S2-L2 confirmation。

S2-I1 no-live repair 已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i1_evidence_export_contract_repair_20260706.json`。
修复内容是：`genmanip_client.EvalClient.step_chunk()` 现在能把 `render_mode/subframes` 透传到 `/step_chunk`，
并且 `EvalClient._resolve_pending_resets()` 在 client 侧轮询 async reset result 时不会丢掉 `terminal_obs`；
`IsaacWorkerPool` 在 episode done 且进入 pending reset 时会把真正终态 observation 作为 `terminal_obs`
保留下来；runner 会用 `terminal_obs` 写 `debug.labutopia_open_door`、Door `RevoluteJoint` 角度、
terminal/front-view frame、metric input 和 `succ_cnts`；`IsaacWorkerPool.step_chunk()` 也不会再把已经 ready 的
pending reset result 消费后丢掉；并且 `render_mode=always` 不再允许静默 fallback 到旧 client 签名。fresh no-live
verification 为 genmanip-client 相关测试 `6 passed`，GenManip runner/worker 相关测试 `18 passed`，
`py_compile` 和 `git diff --check` 均 exit 0。S2-I1 本身不释放 live。S2-R1 review 必须确认 live
debug/metric producer 真的会产出 metric input / `succ_cnts`，或在 release manifest 里定义可接受的同 run
替代 metric evidence。这个 S2-R1 审查已登记为 blocked：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json`，
原因是当时 live debug producer 只导出门角和 joint 信息，runner 只是“如果已有 metric_input / succ_cnts 就保存”，
不会自己生成。随后 S2-I2 已完成 no-live producer 修复，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json`：
`MetricsManager` 会保留刚判分的 `last_metric_debug_snapshot`，`debug.labutopia_open_door` 会把
`CheckJointAngle(obj_DryingBox_01/RevoluteJoint)` 的 `metric_input`、`succ_cnts`、
`metric_success_counter` 和 `metric_score_snapshot` 导出。fresh no-live related regression 为 `55 passed`。
S2-I2 仍不释放 live；S2-R1B release review 已完成并固定 run id
`eos2_s2_l1r_post_s2_i2_route_b_readback_render_20260706_001`、端口 `18139`、同一 Route B source sha
`fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`、严格 `render_mode=always`、
`--trace-final-obs`。该 S2-L1R 已执行但未 reset 成功：`IsaacWorker` 在创建时导入
`from curobo.types.state import JointState`，由于 worker `PYTHONPATH` 没包含
`/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src` 而崩溃。这个结果登记为
`FAILED_EXECUTION_CONTRACT_BEFORE_RESET_CUROBO_IMPORT_MISSING_NO_ROUTE_JUDGMENT`，不能说 expert 失败，也不能释放
S2-L2。S2-I3 已把 cuRobo source 加入 server/runner `PYTHONPATH` 并用 no-live import preflight 证明原失败点通过。
S2-R1C release review 曾完成：新 run id 为
`eos2_s2_l1r_env_repaired_route_b_readback_render_20260707_001`，同一 Route B source sha，干净 evidence dir，
严格 `render_mode=always` / `--trace-final-obs`。它之后的环境缺口没有改变 action source、metric contract
或 expert route 判断；最终有效签收 run 是
`eos2_s2_l1r_full_env_repaired_route_b_readback_render_20260707_003`。该 run 证据完整且分数通过，因此当前不释放
S2-L2 confirmation；只有未来出现完整证据下 metric/physics 失败时，才按同 action source sha、同 command/env、
同 metric code/contract、同 instrumentation 的规则考虑一次 confirmation。

S1 formal score-chain smoke release review 已登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_release_review_20260706.json`。
它只释放一次 bounded live：固定 Gate1V-2c score-capable runner、S0 frozen action source、frozen
`level1_open_door.yml`、IsaacSim41 GenManip py310 环境和端口 `18130`。S1 的 pass 标准是同一 run
出现 authoritative `episode_result.score` 和匹配的 `result_info.json`，并写出 `action_log.jsonl` /
`metric_trace.jsonl`；分数可以是 0。S1 不是 Expert Oracle Score 完成，也不是 policy score。

后续不能一味尝试，attempt budget 固定如下：

| Gate | 最大尝试 | 继续条件 | 停止条件 |
|---|---:|---|---|
| S0 native capture | 已完成 | frozen `action_source.jsonl` + `action_source_manifest.json` 已存在 | 不再重复 S0；除非 S1 证明 frozen source contract 本身不可消费 |
| S1 formal score-chain smoke | S0 freeze 后 2 次 bounded attempt + 1 次 S1R-D reviewed fresh S1，已完成 | 已通过：runner exit 0，`episode_result.score=1.0`、匹配 `result_info.json`、same-run `action_log` / `metric_trace`，且 `metric_score=[[[1.0]]]` | 不再继续 S1 live retry；下一步转 S2 readback/render review |
| S1R result-locator / metric-score / finalize repair | zero-live first；review 后 1 次 fresh S1，已完成 | S1R-A/B/B2/C/D 已完成；Route B fresh S1 已通过 M1 | 不再作为当前 blocker；历史 attempt2 不覆盖 fresh S1 结果 |
| S2 Franka/native metric | S2-I1 evidence export repair 已完成；S2-R1 blocked 了 producer 缺口；S2-I2 metric producer snapshot repair 已 no-live 通过；S2-R1B 的 S2-L1R reset 前因 `curobo` 环境缺口失败；S2-I3/R1C 已释放 env-repaired replacement replay | 同一 run 有 action trace、metric inputs、door joint readback、render/snapshot、official `result_info.json` | 如果 replacement replay reset/runtime 失败，停在 execution contract；如果证据缺失，停在 evidence system；不盲跑 |
| S3 Lift2 oracle / retarget | 2 个 mapping families x 2 个 critical variants | 至少一个 mapping 出现 official nonzero score 或清晰可修的 control-interface blocker | 4 个 bounded variants 都 official zero / invalid 且 control-interface 已排除，关闭当前 retarget route |
| S4 robustness | 3-5 episodes / seeds | 多数过预声明阈值，失败分类清楚 | 单次成功不可复现，或失败超过 3 类 / 不可分类，不扩展 |

因此，“弄好”分两档：M3 / Gate 5 才能说 single-episode Expert Oracle Score POC 弄好；M4 / S4 才能说 workflow
ready for expansion。任何中间失败都只能判具体路线 blocked，不能扩大成 LabUtopia-to-EBench project no-go。

## Historical / Parallel Branch Archive

下面内容是 S0/S1R、Gate1V、Lift2、E2R、F-stage 和早期 planner/contact 分支的历史或并行路线档案，用于追溯为什么某些分支被关闭或转向。它们不覆盖本文顶部的 current canonical 主线：`M1 passed -> S2-L1 score pass but evidence failure -> S2-I1 no-live evidence export repair complete -> S2-R1 blocked -> S2-I2 metric producer repair complete -> S2-L1R reset-before-action env failure -> S2-I3/R1C env-repaired replacement replay -> no S1 retry / no blind score tuning`。

下面的 S0 段落是 historical progression：它们记录从 freezer/exporter code-ready 到最终 S0 freeze 的过程。
当前 canonical 状态以
`eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json` 和
`eos2_expert_oracle_s1_formal_score_chain_attempt2_result_20260706.json` /
`eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json` 和
`eos2_expert_oracle_s2_l1_instrumented_replay_result_20260706.json` /
`eos2_expert_oracle_s2_i1_evidence_export_contract_repair_20260706.json` /
`eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json` /
`eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json` 为准，即 S0 已完成、
S1/M1 formal score-chain 已通过，S2-L1 分数通过但 evidence-blocked；S2-I1 evidence export repair 已完成，
S2-R1 因 producer 缺口 blocked，S2-I2 已 no-live 修复；S2-R1B 放行的 S2-L1R 因缺 `curobo` import path 在 reset 前失败，S2-I3/R1C 已完成环境修复和 replacement replay 准跑。

S0 的第一步 code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_action_source_freezer_code_checkpoint_20260706.json`。
GenManip 侧新增 Isaac-free `score_oracle_action_source_freezer.py` 和测试。它不是生成专家轨迹的算法，而是
“收卷前验标准答案格式”的工具：只有 replay JSONL 的 worker、action dimension、`control_type`、
`step_index`、`base_motion`、布尔字段和 sha256 都通过，才会输出 `action_source_manifest.json`。
这一步的结论是 code-ready / no-live：工具能冻结合格动作源，但只读审计没有发现现成真实 expert action JSONL。
所以 S0 仍未完成为“真实 expert action source frozen”，S1 formal score chain smoke 也仍未释放。

S0 的第二步 code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_action_source_exporter_code_checkpoint_20260706.json`。
GenManip 侧新增 Isaac-free `score_oracle_action_source_exporter.py` 和测试。它不是 planner，也不是 expert
controller，而是“把已经记录下来的诊断轨迹整理成 EBench replay 输入”的转换器：读取 planner summary 中
`plan_success=true` 的 `trajectory_action_joint_positions`，校验 action dimension / numeric values，再输出
freezer-compatible `action_source.jsonl` 和 `action_source_export_manifest.json`。fresh verification 为 exporter、
freezer、score-capable runner 合跑 `13 passed in 0.04s`，`py_compile` 和 `git diff --check` 均 exit 0。
这一步仍是 code-ready / no-live：`diagnostic_trajectory` 被导出后仍只是 replay input，不会自动变成真实
expert action source，也不能触发 score claim。S0 的实际完成条件仍是选定真实 expert/oracle 来源，导出并用
freezer 产出带 sha256 的 `action_source_manifest.json`。

S0 source eligibility audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_source_eligibility_audit_20260706.json`。
这个审计专门回答“既然 exporter 能转 planner 轨迹，现有轨迹能不能直接当 expert source”。结论是不能：
现有 evidence 里有 75 个 JSON 含 `plan_success=true` 的 `trajectory_action_joint_positions`，共 33274 个
trajectory point，但状态只落在三类：43 个
`FAIL_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`、18 个
`BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`、14 个
`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`。这些可以证明 exporter 有输入来源，但不能证明
有真实专家答案。目录中没有 `action_source_manifest.json`；唯一 `result_info.json` 是 AAN runtime smoke，
`score=0.0`、`success_rate=0`。因此 S0 当前状态是工具链 ready / source not eligible，S1 formal
score-chain smoke 仍 blocked。

S0 next-source route review 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_next_source_route_review_20260706.json`。
review 把下一步限定为 A -> B -> C。A 是第一优先：生成或导出 deterministic Franka/native oracle replay
JSONL，再由 exporter/freezer 产出冻结的 `action_source_manifest.json`；这是最近的 S0 unblocker。B 是后备
research lane：只有 A 无法形成 EBench-executable source，或 fallback score route 触发正式 stop line 后，
才单独定义 `native_drive_target` / native controller contract，而且先保持 no-score。C 是并行加固：
asset/task runtime、render、logging、metric 可以继续做，但不能替代 expert action source。当前
`s1_formal_score_chain_smoke_allowed_now=false`，也不能 claim Franka/native expert score、Lift2 official
action path、standard model score、official benchmark reproduction 或 leaderboard readiness。

S0 deterministic Franka/native source code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_deterministic_franka_source_code_checkpoint_20260706.json`。
新增的 `utils/ebench_replay_action_source.py` 是 Isaac-free normalizer/logger：把 LabUtopia native
`ArticulationAction.joint_positions` 标准化成完整 EBench `joint_position` vector，`None` joint 用当前
`state["joint_positions"]` 同 index 值补齐；`main.py` 通过 opt-in `--ebench-action-log-dir` 调用它，默认行为不变。
TDD RED/GREEN 已完成，focused test 为 `6 passed in 0.04s`，`py_compile` 和 `git diff --check` 均 exit 0。
这仍不是 S0 完成：当前只有 candidate logger ready，还没有 `candidate_action_source.jsonl`、没有 freezer
产出的 `action_source_manifest.json`，也没有 S1 formal score-chain smoke release。

S0 bounded native capture attempt 随后已执行并停止在 action-dimension contract：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_native_capture_attempt_20260706.json`。
这次不是 expert failure，也不是 metric failure。attempt2 已用 `labutopia-py311` 进入 Isaac/LabUtopia，
但在 `utils/ebench_replay_action_source.py` 里触发
`ValueError: action_dim_mismatch:7!=9`；原因是 LabUtopia native open controller 混合输出 9D full
Franka joint_position 和 7D arm-only C-space action。当前 partial
`candidate_action_source.jsonl` 只有 1 条记录，没有 `candidate_action_source_manifest.json`、没有 native
success，也没有 freezer 输出，所以不能升级为 real expert action source。

S0 action-dim contract repair code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_action_dim_contract_repair_code_checkpoint_20260706.json`。
zero-live 修复保持默认 strict；只有显式 `--ebench-action-allow-prefix-dim` / `allow_prefix_joint_positions`
时，短的 raw joint_position prefix 才会用 observed tail joints 扩展到 `expected_action_dim`。对 Franka
S0 来说，这就是把 7D arm-only action 扩展为 9D，后两维保持当前 gripper observed joints。TDD RED/GREEN
后 focused `7 passed in 0.11s`，`py_compile` exit 0。边界不变：这仍不是 live success，不释放 freezer、
S1、score 或 project no-go claim；任何新的 capture 都要先做 bounded live release review。

prefix-dim repair-validation capture 已完成，但仍未进入 freezer：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_prefix_repair_validation_capture_result_20260706.json`。
它确认 prefix repair 在 live 中生效：968 条 replay actions 全部是 9D，其中 664 条由 7D arm-only raw
action 扩展而来。但 `candidate_action_source_manifest.json` 的 `success_observed=false`，不能冻结。stdout
显示第 9 次尝试才 `Task success!`，而 logger 在第一次 failed episode 后已经 finalize。结论是
`LOGGER_LIFECYCLE_FAILURE_NOT_PREFIX_DIM_FAILURE_NOT_NATIVE_EXPERT_FAILURE`。

S0 logger lifecycle repair code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_logger_lifecycle_repair_code_checkpoint_20260706.json`。
修复后，failed episode 会调用 `discard_episode()` 删除当前 JSONL 并重置 action count；success episode 才
finalize manifest，并写入 `discarded_episode_count` / `discarded_episode_reasons`。TDD RED 为缺
`discard_episode`，GREEN 后 focused `8 passed in 0.05s`，`py_compile` exit 0。下一步仍不是 freezer 或 S1，
而是先登记新的 bounded live release review，验证 logger 能捕获第一个 successful episode。

S0 lifecycle-validation capture 和 freezer 已通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json`。
这一步真正把 S0 从 code-ready 推到 frozen source ready。successful candidate manifest 显示
`success_observed=true`，`discarded_episode_count=1`，最终 action source 有 905 条连续 9D
`joint_position`，其中 601 条记录了
`normalization=prefix_action_expanded_with_observed_tail`。freezer manifest classification 是
`PASS_SCORE_ORACLE_ACTION_SOURCE_FREEZE`，`action_count=905`、`action_dim=9`、`first_step_index=0`、
`last_step_index=904`，source/frozen sha256 均为
`e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f`。边界：S0 完成不等于 S1、
不等于 score、不等于 Expert Oracle Score。该段是历史 progression；S1 release review 后续已执行，
当前以 S1 attempt2 partial 和 S1R plan 为准。

## 2026-07-06 Historical / Parallel Gate1V Route Record

本节记录 S1R-D fresh S1 之前或并行的 Gate1V / fallback oracle 路线，不是当前 canonical S2/M3 下一步。
2026-07-06 Gate1V post-F route decision 已新增，并已推进到 Gate1V-2c / Gate1V-3 zero-live planning。顶层 route-decision
manifest 仍是
`PLANNED_GATE1V_POST_F_STAGE_ROUTE_DECISION_NO_LIVE`，因为它是路线分叉计划，不是 live result。最新子阶段证据包括
Gate1V-2、Gate1V-2a、Gate1V-2b、Gate1V-2c 和 Gate1V-3。来源证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2a_provenance_review_result_20260706.json`：
F2a 已关闭当前 F-stage lower-level official/OpenPI action branch，不进入 F2b/F2c/F2d，也不允许同路线
live retry。这个结论不等于 LabUtopia-to-EBench project no-go，也不等于 `Expert Oracle Score` 失败。

新的最近目标现在拆得更细。`Gate1V-2a Fallback Oracle Freeze` 已先冻结 EBench Franka config，但没有冻结
score-capable oracle runner / action source；`Gate1V-2b` 已证明现有 runner/action-source 仍不够；因此
`Gate1V-2c Score Runner Build Plan` 把下一步收敛成一个 runner-layer 工程任务。2c 通过也只能说明“可以进入
一次 bounded fallback score live release review”，不能说已经出分。随后那一次 live 如果产出 score / reward /
success、action log、metric trace、`result_info.json` 和 render/readback，才能说最小 `Expert Oracle Score`
评分链闭合。

反过来，如果 Gate1V-2 无法在 zero-live 下写清 metric parity 或 expert replay runbook，就不释放 live；
如果 bounded expert-oracle live 后 expert action 已进入 EBench，但 metric 不涨、success 不记录或
result artifacts 不闭合，则判当前 fallback oracle score route blocked。native-controller 另开
`Gate1V-3 Native Control Contract Research`，不能 claim official benchmark reproduction、standard model score
或 `Expert Oracle Score`，直到它有独立 contract 和 readback harness。

Gate1V-2 zero-live preflight 已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_fallback_oracle_preflight_20260706.json`。
当前状态是
`BLOCKED_GATE1V2_FALLBACK_ORACLE_PREFLIGHT_NO_LIVE_RELEASE_MISSING_FROZEN_SCORE_CAPABLE_ACTION_STREAM`。
这一步把评分器侧先钉住：候选路线是 Franka POC `level1_open_door`，EBench metric 是
`manip/default/check_joint_angle`，目标是 `obj_DryingBox_01/RevoluteJoint`，成功范围 `30-120deg`，
`succ_cnts=59`，最终 `result_info.json` 应包含 `score`、`success_rate` 和 `log_info.metric_score`。
但它也明确了 blocker：EBench Franka config 还没有作为本仓库冻结 artifact；外部 GenManip worktree 对相关
config / runner 文件是 dirty/untracked；native LabUtopia expert 目前只有 video/log success，没有 frozen
EBench action stream。因此 bounded expert-oracle live 仍不释放。

下一步不是启动 Isaac，而是 Gate1V-2a：冻结 config、runner、action stream / deterministic route 和同一 run 的
artifact contract。只有 Gate1V-2a 过审后，才允许最多一次 fallback score live。若未来 live 中 expert action
确实进入 EBench，但 door joint metric 进不了 `30-120deg` 或 `result_info.json` / metric trace 不闭合，
才判当前 selected fallback route blocked；仍不能把它升级成 Lift2 official、policy、leaderboard 或项目 no-go。

Gate1V-2a zero-live freeze 已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2a_fallback_oracle_freeze_20260706.json`。
当前状态是
`BLOCKED_GATE1V2A_FALLBACK_ORACLE_FREEZE_NO_LIVE_RELEASE_MISSING_SCORE_CAPABLE_ORACLE_RUNNER_AND_ACTION_STREAM`。
这一步把 Franka POC `level1_open_door` 的 EBench config 冻结到了本仓库，冻结副本 sha256 为
`e78e5f4b58a39b15bc9146436bf50249b850f71b1171e3f671bbd95e9d58956e`。但它也明确了新的 stop line：
正式 evaluator / `result_info.json` 写出链路已经识别，仍缺会喂入专家动作的 score-capable oracle runner，
也缺 EBench 可执行的 frozen expert action stream / deterministic route。历史 `native_expert_oracle` 命名的
result_info 是 `score=0.0`、`metric_score=[]`，不能作为 expert 已得分证据。因此 bounded fallback score live
仍不释放；下一步只能先做 runner/action-source contract。

Gate1V-2b runner/action-source contract 审计已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2b_runner_action_source_contract_20260706.json`。
当前状态是
`BLOCKED_GATE1V2B_RUNNER_ACTION_SOURCE_CONTRACT_NO_LIVE_RELEASE_NO_SCORE_CAPABLE_ORACLE_ACTION_SOURCE`。
这一步没有启动 Isaac，只做历史 evidence 和 runner contract 审计。结果是：正式 EBench evaluator 能写
`result_info.json`，但还没有一个冻结的 score-capable oracle runner 把专家动作送进去；现有两个 probe 都是
diagnostic/no-score。只读扫描 73 个 Franka open-door `result_info.json` 后，全部为 `score=0.0`、
`success_rate=0`、`metric_score=[]`。因此当前 fallback oracle score route 不能 live；下一步要么在
GenManip/EBench runner 层开发 score-capable oracle runner，要么转 `native_controller_research` 或
`asset_task_no_score_hardening`。

Gate1V-2c score runner build plan 已新增，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json`，
设计说明是
`docs/superpowers/specs/2026-07-06-gate1v-score-capable-oracle-runner-design.md`。当前状态是
`PLANNED_GATE1V2C_SCORE_CAPABLE_ORACLE_RUNNER_NO_LIVE`。通俗讲，这一步不是继续开 Isaac，也不是继续试
policy，而是先做“标准答案投递器”：runner 必须把专家 action 送进正式 EBench evaluator，处理
`reset_pending`，等待 `post_episode_process` 返回 `episode_result`，再校验 authoritative
`result_info.json`。diagnostic `metric`、`done_info.info`、no-score probe summary 或历史 `expert_oracle`
命名目录都不能当 benchmark score。2c 通过前不释放 fallback score live；2c 通过后也只进入 live release
review，不等于 `Expert Oracle Score` 完成。

Gate1V-2c runner code checkpoint 随后已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_code_checkpoint_20260706.json`。
GenManip 新增 Isaac-free `score_capable_oracle_runner.py` 和 fake-client tests；TDD RED 先失败在缺模块，
GREEN 后 focused `7 passed`，与 `test_episode_result_completion.py` 合跑 `12 passed`。这说明“标准答案投递器”
的代码骨架和判分边界已经可测：它会 start job、reset、喂 action、处理 `reset_pending`、读取
`episode_result`、校验 authoritative `result_info.json`，并在异常时保持 `score_claim_allowed=false`。
但它仍不是 live，不是专家得分。早期缺 frozen EBench-executable expert action source 的 blocker
已被后续 S0 freeze 关闭；S1 release review 已登记，当前仍缺 bounded score-chain live/result。

Gate1V-3 native-control research audit 已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json`。
当前状态是
`INCOMPLETE_GATE1V3_NATIVE_CONTROL_CONTRACT_RESEARCH_NO_LIVE_RELEASE_NO_FROZEN_DIFFERENT_CONTROL_SURFACE`。
这一步同样没有启动 Isaac。多角度 review 后的结论是：当前没有一份冻结的 Lift2/R5a native control contract
能证明自己不同于已关闭的 `16D joint_position -> set_joint_position_targets -> world.step` 路线。`step_chunk` /
`step_chunk_size` 只是 transport/batching；`base_motion` 是底盘通道；`ee_pose`、planner、`custom_motion`
最后仍生成 joint target；`physics_hold_steps` 是 diagnostic-only；max-effort repair 改的是既有 joint target
路径的出力；`native_action_path_runner` 也是 diagnostic/no-score。产品口径上，这不是 native-controller
大方向 no-go，而是 research contract incomplete：如果后续要走 native lane，必须先定义 no-score
`native_drive_target` 或同级合同，写清 input/output schema、units、frames、target/applied/observed readback
和 fake-client harness。只有它证明不是旧 joint-position 路线的换名版本，才允许进入 `native_research_live`
预发布审查。它不能 claim official benchmark reproduction、standard model score、policy score、
leaderboard、backend parity 或 `Expert Oracle Score`。

最新推进：Gate 1U-A 已完成 A3j2 和 A3l 两层 bounded live。A3j2 的证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_reachability_live_20260706/aggregate_summary.json`：
在原 base/layout 下，5 个 corrected handle-front candidate 全部 `MotionGenStatus.IK_FAIL`、
`trajectory_point_count=0`、`executed_steps_total=0`，所以继续加 offset 的路线已停止。

A3l 的证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_base_layout_live_20260706/aggregate_summary.json`。
它只改 Lift2 base layout，不改把手目标、right arm、metric 或真实 table surface。结果是 3/5 个候选
planner success 且 trajectory 非空：`A3L_XP10_YP30_KEEP_YAW` 70 points、
`A3L_XP15_YP25_KEEP_YAW` 67 points、`A3L_XP10_YP20_OFFICIAL_YAW90` 96 points。
所有 child run 仍是 `--max-action-points 0`，所以 `executed_steps_total=0`。

给 PM 的通俗解释：A3j2 说明“原站位继续调点位”走不通；A3l 说明“换到更合理的 Lift2 站位后，规划器
能找到到把手前的路线”。这已经把问题从“第一段规划不可达”推进到“短执行能否真实到位”。下一步是
A3k short execution readback，不是 `Expert Oracle Score`。A3k 必须证明至少一个 A3l pass candidate
能执行出 nonzero steps，final EE translation error <= `0.03m`、orientation angular error <= `15deg`，
且不撞真实 table/door。A3k 通过后才进 A3m contact-readiness / no-contact guard；A3m 通过后才可能进入
Gate 2 contact。

因此 `Expert Oracle Score` 仍保持 blocked，但 blocker 已经变了：它不再是 A3j2 的全候选 IK_FAIL，
而是还缺 A3k execution readback、A3m contact-readiness、Gate 2 contact、Gate 3 retention 和
Gate 4 micro-pull / door joint readback。

A3k package 已准备并通过 preflight：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/`。它只执行
`A3L_XP15_YP25_KEEP_YAW` 一个 pass candidate，动作预算 `180`，joint tolerance `0.02rad`，EE translation
tolerance `0.03m`，EE orientation tolerance `15deg`。这一步最多只能把 blocker 从“planner-only route”
推进到“execution readback 到位”；即使 A3k 通过，`Expert Oracle Score` 仍要等 A3m、Gate 2、Gate 3、
Gate 4。

A3k live 已执行但未通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/result_compact.json`。
关键事实是 `executed_steps=142`，说明动作已实际进入 EBench `step_chunk`。A3k1 offline audit 随后把
readback 问题进一步收窄：Lift2 `state.joints` 是 12D arm-only，`state.gripper` 是 4D gripper-only，
16D action target 要按 `[left arm, left gripper, right arm, right gripper]` 对齐。修正 comparator 后重算旧
trace，gripper max error 约 `3.49e-05`，但 arm joint max error 是 `2.571020245552063rad`，超过
`0.02rad`。因此当前 blocker 已从“读不到 joint”升级为“本次执行没有到最终关节目标，且 right-arm
EE world-frame / full-run collision-contact telemetry 仍未闭合”。这仍不是 expert score、door metric 或
policy failure。A3k2 code checkpoint 已补 split readback comparator 和 dual-arm EE debug obs；A3k2
package postprocess closure 也已把 right-arm by-arm debug、EE frame stop-go、full-run collision/contact
coverage 和 controller/applied-target debug 要求做成可测代码。但 live rerun 仍不能启动，因为当前 package
还缺 world-frame right EE 或显式 transform、full-run contact coverage、`final_applied_action_target_16d`
和 `tail_joint_error_series`。A3k2 instrumentation expansion 已新增 runner `--step-chunk-size` 采样入口，
但这只为 full-run telemetry 提供每步 obs，不等价于 full-run abnormal-contact closure；right-arm EE world
transform 已有 code checkpoint：debug obs 会用 `robot_base_right.get_world_pose()` 输出
`evaluator_last_ee_pose_world_by_arm.right`，postprocess 也会拒绝 raw frame-string shortcut。但这仍只是
evaluator target/cache 的 world transform，不证明物理实际到位；full-run abnormal-contact aggregation 和
controller/applied-target aggregation 仍未闭合。`Expert Oracle Score` 仍保持 blocked。

后续 A3k2 controller/applied-target aggregation checkpoint 已把其中一项再收窄：runner 在
`--step-chunk-size 1` 下会从每步 final obs 的
`debug.labutopia_open_door.evaluator_last_action_application_debug` 聚合 `a3k2_controller_debug.v1`。
`final_applied_action_target_16d` 来自 evaluator `env.step` 读到的 `applied_joint_position_target`，
`tail_joint_error_series` 来自 `post_world_step_minus_target_abs_max`，不是 runner 用 action chunk 反推。
因此当前 `Expert Oracle Score` 的最近 blocker 已从“world EE + controller + contact 都缺”收敛为：
right-arm world EE 和 controller/tail 代码路径已准备，仍缺 full-run abnormal-contact aggregation、
刷新 package closure 到 `ready_to_rerun_live=true`、以及唯一 A3k2 live rerun 后的真实 readback 证据。

再往后，A3k2 full-run contact aggregation checkpoint 已把最后一个 instrumentation code blocker 也补上：
runner 会从 `--step-chunk-size 1` 的每步 `physx_contact_debug` 聚合
`a3k_full_run_collision_contact_readback.v1`，并要求 contact sample 覆盖全部 executed steps；单个 final obs
的 `physx_contact_debug` 仍不能冒充 full-run。review 后的边界是：这个 schema 覆盖 per-step observed
`physx_contact_debug` 的 unmatched contact pairs，不是全局所有场景碰撞证明；`status=available` 但字段形状
异常的 sample 也不会被算作 clean coverage。随后唯一 A3k2 same-candidate live rerun 已执行，但没有通过：
动作执行了 `143` steps，final planner record 是 `a3j2_corrected_center`，但 generated Lift2 task name
没有触发 `debug.labutopia_open_door` 注入，right-arm world EE、controller/tail debug 和 full-run contact
samples 都缺。A3k2b generated-task-name debug-gate live validation 已随后通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2b_debug_gate_validation_20260706/result_compact.json`。
它只执行 1 个 diagnostic action point，证明 generated Lift2 candidate 的 live obs 已经包含
`debug.labutopia_open_door`，并能带出 right-arm world EE、controller/tail debug 和 full-run contact sample
plumbing。随后 exactly 1 次 full A3k2 same-candidate readback rerun 也已执行：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2c_full_readback_rerun_20260706/result_compact.json`。
它没有通过 A3m 入口：`executed_steps=142`，trace 最后一帧含 Lift2 `state.joints` / `state.gripper`，
full-run contact coverage `142/142` 且异常接触为 0。A3k2d zero-live readback consistency audit 已完成：
旧 runner summary 的 `state_joints_missing` 被改判为 stale summary；final worker obs + controller target
可以闭合 `lift2_split_arm_gripper_obs_to_16d_action`，但 selected candidate 真实未到位。joint error
`2.570956rad`、right-arm EE translation error `0.527791m`、orientation error `166.862deg` 都超阈值。
`Expert Oracle Score` 当前最近 blocker 随后推进到 A3k bounded fallback，并已执行完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_bounded_fallback_readback_20260706/result_compact.json`。
两个剩余 A3l planner-success candidates 都在 closed-schema readback 下失败，`pass_candidate_ids=[]`。
因此当前不能进入 A3m contact-readiness，更不能进入 Gate 2/3/4 或 Gate 5 `Expert Oracle Score`。下一步
是 A3l route-family no-go review：转 A3r fixed-layout route redesign 或上层 robot/control/task-layout
contract review。

2026-07-06 A3l route-family no-go review 已完成，证据登记在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_route_family_no_go_review_20260706.json`。
当前不再允许继续 A3l base/yaw/offset sweep。`Expert Oracle Score` 的最近 blocker 已改为 E1
controller/execution contract audit：先用 0-live 审计 planner trajectory -> 16D action ->
controller applied target -> final `state.joints/state.gripper` / right-arm EE readback 是否同一套语言。
只有 E1 找到明确可修或可验证 hypothesis，才允许 E2 的 1 次 EBench reference probe；否则当前 A3l route
family 直接停止，不再消耗 live。最早能说明“新思路有戏”的节点是 E4 one-segment DryingBox precontact
closed execution；Gate 4 才能说工程上接近会开门；Gate 5 才能说 expert score 口径闭环。

2026-07-06 E1 audit 已完成，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e1_controller_execution_contract_audit_20260706.json`。
结论是：动作已经每步下发、contact clean、readback mapping 不像简单写反；可信但未证明的 blocker 是
`H1_PLAYBACK_OUTRUNS_LIFT2_CONTROLLER`。也就是说，当前可能不是 DryingBox expert 本身错，而是 planner
trajectory 的每个 joint_position point 只给 Lift2 一个 `world.step()`，controller 追不上目标。所以下一步
E2 只允许一次 non-DryingBox Lift2 controller reference / retiming probe：5 个 no-op、5 个右臂小 ramp、
60 个 terminal hold。只有 no-op/hold closed-schema 到位后，才允许把同样 timing contract 迁移到
DryingBox E4 one-segment precontact；否则先修 Lift2 controller/action/readback，不进入 `Expert Oracle Score`。

2026-07-06 E2 code-ready checkpoint 已完成，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_code_checkpoint_20260706.json`。
2026-07-06 E2 live 已执行完，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_live_20260706/result_compact.json`。
该历史 Lift2 direct-16D 分支当时停在 E2 blocker：`BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED`。
这次 non-DryingBox probe 只问 `manip/lift2/R5a` 能不能在 closed readback 下跟踪一个很小的 16D
`joint_position` 命令，并且 terminal target 持续 hold 后能不能到位。它不是 DryingBox route attempt，
不是 contact，不是 micro-pull，不是 door success，也不是 `Expert Oracle Score`。

E2 的实际结果已经触发停止线：`executed_steps=70/70`，但 no-op 和 terminal hold 都没有到位；
final joint error `0.20075764784227174rad`，final gripper error `0.000007718801163986155rad`。
action-application debug 存在，说明动作不是没下发。该历史分支当时停止 DryingBox oracle，先修或解释
Lift2 controller/action/readback；这不覆盖当前顶部的 S2/M3 证据补齐主线。如果未来 no-op 和 terminal hold 收敛但 ramp 过程中有 transient miss，
只能带 explicit retiming / terminal-hold contract 进入 E3/E4；如果 no-op、ramp、hold 都到位，也只解锁
E3 static DryingBox pose compute 和 E4 one-segment precontact，不代表开门或得分。

为了避免继续盲试，2026-07-06 新增 E2R root-cause plan：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r_controller_action_readback_root_cause_plan_20260706.json`。
这个计划把下一步压成最多两次 non-DryingBox live，中间必须先补 per-joint telemetry。现在已有证据能排除
“runner 完全没发动作”：70/70 step 已执行，`target_action_16d` 与
`applied_joint_position_target_16d` 最大差约 `5.52e-09rad`。但现有 trace 只保存最大误差，没有保存
每个关节的 observed / expected / error vector，所以还不能判断是 reset baseline 漂移、action/readback
slot 错、某个 DOF 没被 drive、还是 timing/hold 不够。

新的阶段判断：

| Stage | 作用 | 通过后能说什么 | 失败后怎么处理 |
| --- | --- | --- | --- |
| E2R0 | 0-live 冻结 E2 证据和 telemetry 缺口 | 可以安全进入仪表补强 | 不允许修行为或跑 DryingBox |
| E2R1 | code/test-only per-joint telemetry patch | 下一次 live 能看到哪个关节、哪个 slot、哪层合同错 | 如果仪表拿不到数据，先修 evaluator debug plumbing |
| E2R2 | 1 次 enhanced non-DryingBox reference live | 能把 root cause 分类到 reset/mapping/drive/timing 之一，或者直接 E2 pass | 若仍看不清，停止 live，只修仪表 |
| E2R3 | 单假设修复 | 只修一个被证据支持的合同点 | 若证据指向多因，先拆分，不混修 |
| E2R4 | 1 次 final controller sanity live | no-op + final hold 达标后，才回到 E3/E4 | 若同类失败仍存在，当前 direct 16D `joint_position` 路线 no-go，转 official Lift2 baseline controller/action path |
| E2R5 | 0-live closure / fork decision | 把 E2R4 结果封账：通过则进 E3/E4，失败则转 official Lift2 baseline controller/action path review | 不能作为第三次 live，也不能启动 score |

所以“什么时候能弄好”的最早工程答案不是现在：controller 这层最早看 E2R4；DryingBox 专家路线最早看
E4 one-segment precontact；`Expert Oracle Score` 至少还要经过 contact、retention、micro-pull 和 metric
readback。反过来，“什么时候判这条路不行”：如果 E2R4 在 per-joint telemetry 闭合后仍同类失败，就停止当前
direct 16D action 路线，不再继续调 DryingBox offset。

2026-07-06 E2R1 已完成 code/test-only telemetry checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r1_per_joint_telemetry_code_checkpoint_20260706.json`。
这一步不改变 controller 行为，也不消耗 live；它只保证下一次 E2R2 live 能写出 per-joint observed /
expected / error vectors、max-error slot / DOF name、完整 action debug、controller drive debug 和静态
action-slot mapping。当前 `Expert Oracle Score` 仍 blocked；最近下一步是 E2R2 enhanced non-DryingBox
reference live，而不是 DryingBox、contact 或 score。

2026-07-06 E2R2 enhanced live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r2_enhanced_lift2_controller_reference_live_20260706/result_compact.json`。
它消耗了 E2R2 唯一 live budget，仍然 blocked，但已经把 blocker 具体化：reset/no-op 基线会漂移到
`fl_joint3` 约 `0.047rad` 误差；更关键的是 terminal hold 60 步后，action slot `8` / `fr_joint1` 的 controller
applied target 是 `0.20075rad`，真实 observed 仍接近 `0rad`。因此 `H1_PLAYBACK_OUTRUNS_LIFT2_CONTROLLER`
被削弱；最近下一步是 E2R3 zero-live / single-hypothesis repair planning，审计 Lift2 arm joint tracking /
controller application path。`Expert Oracle Score` 仍不得启动。

2026-07-06 E2R3 plan 已完成并写入
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3_lift2_articulation_contract_repair_plan_20260706.json`。
当前优先假设是 `H3_CONTROLLER_TARGET_APPLIED_BUT_ARM_JOINT_TRACKING_DISABLED_OR_BYPASSED`：也就是
action 到 controller 这一段已基本闭合，但 controller target 没有变成 Lift2 arm DOF 的物理运动。E2R3
不消耗 live，它先做 source/USD/articulation contract audit，再补 code/test-only articulation telemetry，
最后选择唯一一个修复点给 E2R4 验证。E2R4 是当前 direct 16D `joint_position` 路线的 yes/no 节点；
E2R5 只做 closure/fork decision，不允许变成第三次 exploratory live。

2026-07-06 E2R3a zero-live audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3a_lift2_articulation_contract_zero_live_audit_20260706.json`。
静态 USD/PXR 审计确认 `fr_joint1` 存在、是 `PhysicsRevoluteJoint`、有 `PhysicsDriveAPI:angular`、
`jointEnabled=true`、`excludeFromArticulation=false`、maxForce 为 `100`。这排除了“右臂关节/drive 在资产里
缺失”的粗问题，但不能证明 runtime DOF mapping、qdot、limit、max velocity、sleep/constraint 都正常。
下一步 E2R3b 只补 code/test-only runtime articulation telemetry，不启动 DryingBox、contact 或 score。

2026-07-06 E2R3b code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3b_articulation_telemetry_code_checkpoint_20260706.json`。
`read_articulation_controller_debug` 现在能随 controller debug 输出 runtime joint position、joint velocity、
max joint velocity 和 lower/upper limits。TDD 记录了 RED/GREEN；相关 focused suite 为
`97 passed in 0.60s`。这一步只让 E2R4 的最后一次小动作 live 有足够读数，不等价于修好；E2R3c 仍必须先
选择唯一修复点。

2026-07-06 E2R3b2 summary telemetry addendum 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3b2_summary_telemetry_addendum_20260706.json`。
它仍是 0-live / code-test-only addendum，不改 action、controller、drive 或 route。变化是 E2R4 的
`summary.json` 会直接包含 `final_controller_drive_debug` 和 `final_runtime_motion_debug`，其中包括最终
`joint_position`、`joint_velocity`、`max_joint_velocity`、上下限、applied target 和 drive 参数。
因此 E2R4 跑完后可以直接按 summary 判定 pass、retiming-needed、telemetry-blocked、drive/limit-blocked
或 direct 16D no-go。新增测试后相关 suite 为 `98 passed in 0.60s`。

2026-07-06 E2R3c single repair decision 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3c_single_repair_decision_20260706.json`。
决策是不做 speculative behavior repair：不盲目加 drive/gain、不盲目换 articulation API、不盲目加 hold。
E2R4 将作为最后一次 non-DryingBox controller sanity live，带 E2R3b runtime telemetry 判定当前 direct 16D
`joint_position` 路线是 pass、retiming-needed、telemetry-blocked，还是 no-go fork official Lift2 baseline
action path。`Expert Oracle Score` 仍不得启动。

2026-07-06 E2R4 final controller sanity live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r4_final_controller_sanity_live_20260706/result_compact.json`。
E2R4 消耗唯一 allowed live，仍是 non-DryingBox probe：`planned_steps=70`、`executed_steps=70`。
结果不是 pass，也不是 retiming-needed：`phase_reached` 的 no-op/ramp/hold 均为 false，hold 最大误差
`0.20078105353335302rad`。最终最大误差来自 slot `8` / `right_joint1`：target
`0.200753768836rad`，controller applied target `0.20075376331806183rad`，observed
`-0.000003879rad`，final error `0.20075764784227174rad`。limits 不挡，drive 参数存在，runtime
`max_joint_velocity` 为 null 只能作为 caveat，不能作为继续盲跑的理由。

2026-07-06 E2R5 zero-live closure 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r5_direct_16d_route_closure_fork_20260706.json`。
结论是关闭当前 direct 16D `joint_position` route，fork 到 official Lift2 baseline controller/action path
review。`Expert Oracle Score`、DryingBox E3/E4、contact 和 micro-pull 仍 blocked；恢复条件不是再调
DryingBox offset，而是 baseline action path 先通过 bounded controller sanity。

2026-07-06 follow-up stop-go review 把后续“到哪一步能弄好 / 到哪一步判不行”重新写清楚：
当前已经 no-go 的只有 direct 16D `joint_position` route，不是 LabUtopia-to-EBench 整体失败。接下来先走
F1/F1b/F1c/F1d/F1e official-baseline stop-go：F1 已证明 terminal arm-only zero-base payload 与 E2R4 等价；
F1b 已证明 endpoint/base_motion 不能作为 right-arm 修复理由；F1c 已选择 controller/articulation runtime
repair 作为唯一下一方向；F1d 已选择 `lift2_arm_runtime_max_effort_only_repair`，但只释放 F1e code/test。
F1e 必须证明这个修复已实现、区别于 E2R4 unchanged path，且不混入 action API、gain、max velocity、hold、base 或 DryingBox 变化，才允许 F2 baseline-compatible controller sanity live。F2 的通过标准是 non-DryingBox no-op + terminal hold 在 closed readback 下达标，并且 readback 看到 repaired max effort；F2 的失败标准是 telemetry 完整、target
applied，但 joint / EEF 同向运动不足或 terminal error 超阈值。F2 通过只能说明“底层控制口径可用”，不能说开门、contact、
policy score 或 `Expert Oracle Score` 通过。完整出分闭环仍必须走 E4 precontact、Gate 2 contact、
Gate 3 retention、Gate 4 micro-pull / door joint readback，最后到 Gate 5 记录有效 score / reward /
success、action log、metric trace、`result_info.json` 和 render/readback 证据。

2026-07-06 F1/F1b official baseline review 后，`Expert Oracle Score` 仍 blocked，而且 blocker 更明确。
F1 证明 terminal zero-base arm-only official prep-output 与 E2R4 direct 16D failed payload 等价；F1b 又证明
official runner endpoint 没有绕过这条核心 action application path：official runner 和 reference probe 都进
GenManip `/step_chunk`，最后到 `IsaacEvalEnvRay.step`。official 19D 里的 `base_motion` 是真实差异，但它是
独立底盘通道，不是 right-arm joint tracking 修复证据。因此不能直接重跑 official arm-only payload、不能回
DryingBox、不能启动 score。下一步必须先做 F1c 0-live single-hypothesis selector：如果能命名一个真实
controller/runtime/action-abstraction 差异，也不能直接 live；还必须进入 F1d 选择一个具体 controller/articulation
runtime repair。F2 如果 target applied 但相关物理通道达不到 movement/error 阈值，也要在 F2 no-go，不能继续盲试。

2026-07-06 F1c 已把下一步方向选定为 `controller/articulation runtime repair`，证据登记在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1c_single_hypothesis_selector_20260706.json`。
这一步仍是 0-live，不启动 score。它明确拒绝把 Newton homologation、higher-level official action abstraction
或 base-only diagnostic 当作当前 F2 路线：这些都不能直接解释 `right_joint1` 在 Isaac / GenManip runtime
下不跟踪。`Expert Oracle Score` 继续 blocked；恢复条件是 F1d 先选出一个具体 controller/articulation
runtime repair，随后 F2 non-DryingBox live 证明目标、controller、物理关节和 worker obs 闭合。

2026-07-06 F1d 已选定具体修复族：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1d_concrete_repair_selector_20260706.json`。
选择已根据后续 review 修订为 `lift2_arm_runtime_max_effort_only_repair`。这一步仍不解锁 score，也不解锁
F2 live；F2 必须等 F1e code/test checkpoint 证明这个 max-effort-only 修复已经实现，且不混入 action API、
gain/max-velocity/hold/base/DryingBox 变化之后，才允许一次 non-DryingBox controller sanity。F2 如果在完整
telemetry 下仍显示 target applied 但 `right_joint1` / EEF 同向运动不足或 terminal error 超阈值，就关闭当前 max-effort repair route，
转 higher-level official runner / action abstraction review；不继续同路线 live retry。

2026-07-06 F1e code/test checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1e_lift2_runtime_max_effort_code_checkpoint_20260706.json`。
GenManip 现在只对 Lift2 左右臂 12 个 arm DOF 调用 `ArticulationView.set_max_efforts`，值为 `1000000.0`；
调用点在 `Lift2Embodiment._post_initialize()` 的 `super()._post_initialize()` 之后，避免未初始化 no-op。
不改 gripper、base、lift joint，也不改 action API、drive gain、max velocity、hold、base_motion 或 DryingBox。
TDD RED/GREEN 已记录，focused `2 passed`，相邻 suite `20 passed`，`py_compile` 和 `diff --check` exit 0。
这仍不是 `Expert Oracle Score` 证据，也不是 live evidence；它只把 blocker 从 code/test 移到 F2 stop-go。
F2 若通过，才允许恢复 E3/E4；F2 若完整 telemetry 下仍失败，则当前 max-effort repair route 停止。

2026-07-06 F2/F5 decision checkpoint planning 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_f5_decision_checkpoint_planning_20260706.json`。
当前预计定论点分三层：F2 只判断底层控制路线能不能继续；E4/Gate 4 才判断 DryingBox 专家路线是否出现工程成功信号；
Gate 5 才判断 `Expert Oracle Score` 是否真正闭环。F2 的 pass/fail 不产生 oracle score、policy score 或 official score
claim。若 F2 读数完整且 target applied、max effort repaired，但 `right_joint1` 同向运动不足或 terminal error 超阈值，结论是
`LOCAL_NO_GO_LIFT2_ARM_RUNTIME_MAX_EFFORT_REPAIR_ROUTE_REVIEW_HIGHER_LEVEL_OFFICIAL_RUNNER_OR_ACTION_ABSTRACTION`：
它只关闭当前 max-effort repair route，不关闭 LabUtopia-to-EBench 项目，也不关闭 official Lift2 baseline 的所有可能分支。

2026-07-06 F2 command preflight 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_preflight_20260706.json`。
这一步仍然是 `not_live_evidence`，只固定 exactly one F2 的 server / submit / runner 命令、端口、run_id、
evidence dir 和 hard readback schema。它不会启动 `Expert Oracle Score`，也不会产生 oracle_score、
policy_score 或 official_score 口径。F2 live 只有在多 agent preflight review 通过后才允许执行；即使 F2 pass，
也只是把 blocker 从底层控制推进到 DryingBox E3/E4 precontact，离 Gate 5 score 仍有 contact、retention、
micro-pull 和 metric artifact 几层。

第一轮 preflight review 后已补两项防误判修正：F2 专属 `server.command.txt` / `runner.command.txt`
已落地到 F2 live evidence dir，避免误用 E2R4 `18131` 命令；probe summary 也新增
`right_joint1_motion`，让 `+0.20rad` command 下的 baseline / observed delta 不需要事后猜。`runner.exit_code`
仍不能代表 F2 pass；F2 结果必须按 hard checklist 判定。该修正不改变 `Expert Oracle Score` blocked 状态。

2026-07-06 最新 stop-loss 审阅结论：F2 不是“再试一次专家轨迹”，而是把底层控制合同做一次可判定的小考。
pre-live server attempt 曾在 runner 前因 Ray `AF_UNIX` socket path 过长失败，已缩短 `RAY_TMPDIR` 修复；没有
live marker 或 summary，因此不消耗 F2 live budget。后续 exactly one F2 live 只回答一个问题：修后的
`Lift2 arm runtime max-effort-only repair` 能否让 action slot `8` / `right_joint1` 从 requested target、
controller applied target、runtime max effort 一直到 physical motion / worker obs 闭合。

F2 通过后，`Expert Oracle Score` 仍 blocked，只是允许恢复 DryingBox E3/E4。F2 完整 telemetry 下失败后，
也不能说 expert 失败或项目失败，只能关闭当前 max-effort repair route，转 higher-level official runner /
action abstraction review。能够对 PM 说“基本能接上”的最早乐观节点是 E4/F3 precontact；能够说“工程上
接近开门”的节点是 Gate 4 micro-pull；能够说 `Expert Oracle Score` 闭环的唯一节点仍是 F5/Gate 5。

2026-07-06 F2 exactly-one live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_live_20260706/result_compact.json`。
canonical status 是 current max-effort repair route local no-go。F2 不是 `Expert Oracle Score` run：
没有 DryingBox contact、没有 micro-pull、没有 policy score、没有 official score。它只测试 Lift2 底层控制。
结果显示 max effort 修复真实进入 runtime：slot `8` 的 `drive_max_effort=1000000.0`，target 到 applied
diff 约 `2.90e-09rad`；`right_joint1` 也同向运动约 `0.11047rad`。但 pass 要求是 `>=0.18rad` 且 terminal
error `<=0.02rad`，实际 error 约 `0.08953rad`。所以这不是“完全没反应”，而是“有响应但不够到位”，足以关闭
当前 max-effort-only repair route，但不能关闭项目或启动/否定 Expert Oracle Score。

2026-07-06 F2 后 stop-go 规划已固化为 F2a/F2b/F2c/F2d。F2a 仍是 0-live provenance review：
只允许查 official runner / action abstraction 是否存在真正不同于当前
`env.py -> set_joint_position_targets -> world.step` 的路线。多角度 review 已排除把
`physics_hold_steps`、`step_chunk_size`、official prep-output / `base_motion` 当成同路线重试理由：
前者是 diagnostic-only，第二个只改变 chunk/trace，不改变控制语义，第三个的 arm 部分仍落到同一
16D `joint_position` path。F2a 找不到真实新路线，则关闭 F-stage lower-level action 分支；F2a 找到后，
F2b 还必须先本地证明 movement `>=0.18rad` 且 terminal error `<=0.02rad`。只有 F2b/F2c 通过后才允许
F2d live go/no-go。这个链路依然不是 `Expert Oracle Score` 证据；它只决定有没有资格回到 DryingBox
E3/E4、contact、micro-pull 和最终 Gate 5 score。

2026-07-06 F2a zero-live provenance review 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2a_provenance_review_result_20260706.json`。
结论是 `F2A_FAIL_NO_TRUE_NEW_OFFICIAL_ACTION_ABSTRACTION_CLOSE_F_STAGE_LOWER_LEVEL_ACTION_BRANCH`。
EOS 侧没有找到 official/OpenPI Pi0 runner 的新动作语义：仍是 `50x19` model action 到 16D
`joint_position` + 3D `base_motion`，然后 GenManip `/step_chunk`。GenManip 侧也没有找到新的 runtime control
surface：`step_chunk` 逐条进 `env.step`，`env.step` 仍调用 `set_joint_position_targets` 后 `world.step`。
`ee_pose/custom_motion` 是 IK/waypoint 到 joint target 的前处理，不是新的 runtime action abstraction；
native-drive-target controller 是单独 research/control lane，不是当前 official score route。

因此 F2b/F2c/F2d 不进入，当前 F-stage lower-level official/OpenPI action 分支关闭。`Expert Oracle Score`
继续 blocked，而不是 failed：我们还没有拿到一条可在 EBench metric 下 replay 的专家动作路线。下一步如果继续 score
目标，必须先开新的上层路线计划，明确新的 Lift2 control contract 或新的 oracle/control surface，再从 zero-live
contract review 开始；不能用 F2a fail 直接算分或否定专家策略。

2026-07-06 F1 terminal zero-base arm-only official prep-output equivalence 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1_official_prep_output_equivalence_20260706.json`。
E2R4 terminal `applied_joint_position_target_16d` 经 official 19D row 和 prep-output helper 往返后，arm-only
zero-base payload 分类为 `EQUIVALENT_TO_DIRECT_16D_PAYLOAD`，joint diff / base diff / metadata diff 均为 0。
因此 terminal arm-only zero-base F2 live 不允许；它会重复 E2R4 的 direct 16D 失败路线。`base_motion` 是唯一 payload-level
差异只在该 terminal-payload synthetic probe 范围内成立，尚未覆盖 no-op、ramp、full official policy 19D
trajectory / horizon、endpoint 或 wrapper boundary；它也不解释 right-arm joint tracking blocker。当前
`Expert Oracle Score` 仍 blocked。该段是 F1 完成时的阶段口径；后续 F1b/F1c 已完成，当前最近下一步是
F1d zero-live concrete controller/articulation repair selector。

以下 Gate 1R / Gate 1T / A-lane 段落是 E2 之前的历史收敛链，用来解释为什么转入 E2，不再代表当前下一步。

Gate 1R + Gate 1S 已经把当前精确定义合同推进到 bounded no-go 建议点。这里的“当前合同”指
`EBench + Franka + LabUtopia DryingBox + 当前任务布局 + mesh-open-face near route`。Gate 1R
跑完 R1/R2/R3/R4 后，分类是
`BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS`；Gate 1S 只允许一个
strategy-level 尝试，`S1_TASK_LAYOUT_NORMALIZATION` live 后分类是
`BLOCKED_GATE1S_SELECTED_STRATEGY_NO_NEAR_REACHABILITY`，并且
`bounded_no_go_recommended=true`。

给 PM 的通俗解释：我们不是“还没算专家分”，而是还没有形成一条有资格拿去算专家分的专家动作路线。
前半段 bridge 能到，但真正到把手前安全操作位仍是 `IK_FAIL` / 0 action points；没有这一步，就不能
进入 contact、close-hold、micro-pull，更不能进入 `Expert Oracle Score`。所以现在不能说
`Expert Oracle Score` 失败，只能说它继续 blocked。

历史上当时的下一步曾规划为 Gate 1T contract fork：
[`2026-07-06-eos2-gate1t-contract-fork-route-generator.md`](../superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md)。
推荐优先 lane 是 `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR`，也就是保持 Franka、当前 layout、
DryingBox 资产和 EBench metric 不变，只把 route generator 改成 EBench 原生 `microwave` 风格：
`robot_frame` staging + `object_frame` waypoints，由 runtime/curobo 逐段现算。Gate 1T 仍然不是
score 阶段；只有新的 Gate 1 pass 证明 handle-front near 可达后，才允许进入 Gate 2 contact，
再按 retention、micro-pull、door joint readback 顺序走到 `Expert Oracle Score`。

Gate 1T-C0 / C1 的工程状态：`eos2_gate1t_native_oracle_pattern_extraction_20260706.json`
和 `eos2_gate1t_native_pattern_route_candidates_20260706.json` 已准备好。它们证明“下一轮怎么规范地选
route”，不证明 route 已经能到。后续 C2b 已选 `C1_ROOT_DIRECT_NATIVE_PATTERN` 做 live，但结果是
resolver mismatch：`robot_frame` 在当时 helper 中 unsupported，`obj_DryingBox_01` articulated root
也不在 `scene.object_list`，所以 C2b 不能作为 route no-go 或 expert score 证据。

2026-07-06 C2a runner capability audit 已从 missing 推进到 code-ready。当前状态是
`CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE`，证据文件是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json`。
这不是 route pass，也不是 expert score pass；它只说明当前工具链已经有一个可测入口，把选中的
`custom_motion` route 解析、规划、转 action，并通过 fake-client `step_chunk` contract 验证 summary
分类。runner 现在也会记录 `run_id`，方便 C2b live 和 server logs 对齐。

2026-07-06 C2b 和 C2c 已经都是 live evidence，而不是 prepared/not-run。C2b 证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_live_20260706/`，
compact status 是 `LIVE_BLOCKED_RESOLVER_MISMATCH_NOT_ROUTE_NO_GO`。C2c 证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/`，
compact status 是
`LIVE_BLOCKED_REACHABILITY_AFTER_RESOLVER_CLOSURE_TARGET_EQUIVALENCE_UNPROVEN`。

C2c 的白话解释：这次不是“工具没跑起来”。`robot_frame` staging 规划成功并生成 `44` 个 action
points；`obj_DryingBox_01_handle` 作为 `object_frame` 也能解析。失败点已经进入 planner reachability：
两个 handle-frame targets 都返回 `MotionGenStatus.IK_FAIL` 且 `trajectory_point_count=0`，所以没有
action steps、没有 contact、没有 micro-pull，也没有 door/score 证据。

但 C2c 还不能宣布 `Expert Oracle Score` 失败，也不能宣布 C route generator 全局 no-go。原因是
C2d target-frame audit 已经发现：C2c handle local `Y+` 在 live 里映射到 world `X+`，C2c near target
距离 mesh/open-face 参考的 handle-front approach-near target 约 `0.1116m`。也就是说，C2c 的
IK_FAIL 是真实的，但它不一定打在我们想验证的“把手正前方”目标上。

下一步不是算分，而是按
[`2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md`](../superpowers/plans/2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md)
执行：C2d 先判目标点是否等价；如果等价，C2c 的 IK_FAIL 可以停止 C lane；如果不等价，C2e 先补
raw resolver / adjusted-target dump 并推导等价 local 坐标。现在这一步已经有新证据：
`eos2_gate1t_c2e_resolver_dump_live_20260706/` 捕获了 `frame_in_world`、raw
`pose_frame_to_world` 和 adjusted target；随后
`eos2_gate1t_c2e_equivalent_target_coordinate_derivation_20260706.json` 已证明
`approach_near` local coordinate 能 forward-check 回 mesh/open-face 正面目标，误差约
`5.55e-17m`，低于 `0.01m` 门槛。同时它保留 EBench-native route 的 gripper orientation；
这个 orientation 和旧 mesh-open-face runtime orientation 相差约 `90deg`，因此 C2f 是 native
route 合同验证，不是所有姿态的全局可达性证明。下一步不是算分，而是 C2f 唯一 live rerun：
`C1_RESOLVER_CLOSED_EQUIVALENT_TARGET_NATIVE_PATTERN`。

C2f 现已跑完，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_live_20260706/result_compact.json`。
结果不是 pass：等价正面目标精确命中，但 planner 返回
`MotionGenStatus.IK_FAIL`、`trajectory_point_count=0`、`executed_steps=0`，分类为
`BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`。这意味着当前
`Franka + current layout + native-route orientation` 合同已经按规则停止，不能继续拿这个 C lane
硬算 `Expert Oracle Score`。推荐下一步转 `A_LIFT2_ROBOT_CONTRACT_FORK`；只有新的 Gate 1 pass
进入 Gate 2 contact，再经过 contact/retention/micro-pull/door joint readback，才进入
`Expert Oracle Score`。
最新 A3k2 same-candidate live rerun 已经实际执行。证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_same_candidate_live_rerun_20260706/result_compact.json`：
固定 `A3L_XP15_YP25_KEEP_YAW` 和 `A3J2_CORRECTED_CENTER`，执行了 `143` steps，final planner record
仍是 `a3j2_corrected_center`。这说明动作链已经再次进入 EBench step，但 A3k2 没通过：
`debug.labutopia_open_door` 没有进入 live obs，导致 right-arm EE、controller/tail debug 和 full-run
contact samples 全缺。root cause 已定位为 generated Lift2 candidate task name
`ebench/labutopia_lab_poc/lift2_candidate/a3l_base_layout/a3l_xp15_yp25_keep_yaw` 被原
`level1_open_door*` debug gate 排除。GenManip 已用 TDD 补了 generated Lift2 task-name gate，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_generated_task_name_debug_gate_closure_20260706.json`。
因此 `Expert Oracle Score` 的最近 blocker 不是 generated-task-name instrumentation 了，也还不是
contact/score。A3k2b generated-task-name debug-gate live validation 已通过；A3k2c full readback 进一步
证明 full-run contact coverage 闭合，且 trace 最后一帧含 `state.joints` / `state.gripper`。A3k2d
zero-live readback consistency audit 又把 runner summary 与 postprocess schema 的口径对齐：旧
`state_joints_missing` 是 stale summary，闭合后的 selected candidate 真实失败。下一步只允许 A3k bounded
fallback：最多再试 A3l 剩余两个 planner-success candidates，并使用同一套 evidence fields。

Gate 1U-A 计划已经新增：
[`2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md`](../superpowers/plans/2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md)。
A0/A1 只验证 Lift2/R5a static config、16D action dialect、camera/observation/metric live schema；
即使 A1 通过，也还不能说 expert 分数通过。
A0 静态审计已通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a0_lift2_static_contract_audit_20260706.json`。
它证明 Lift2/R5a 和 16D action config 是静态成立的，但还没跑 live schema/action probe。

A1/A1a/A1b/A1c 已经更新成完整证据链。A1 首次 live 的 blocker 是 assets root：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/result_compact.json`
记录 `LIVE_BLOCKED_A1_RESET_RESULT_PENDING_ASSETS_ROOT_OVERRIDE_MISSING_STOP_BEFORE_A2`。A1a 已固定
`LABUTOPIA_POC_ASSETS_OVERLAY_ROOT=$GENMANIP_WORKTREE/saved/assets` 并通过 preflight。A1b corrected live
已经越过 reset/action 层，只剩 logging metadata incomplete。A1c fresh live 已补齐 logging 并全部 PASS：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_lift2_live_schema_probe_logging_closed_20260706/result_compact.json`
状态是 `PASS_A1C_LIFT2_LIVE_SCHEMA_ACTION_LOGGING_PROBE_READY_FOR_A2_ORACLE_DESIGN`。

给 PM 的通俗解释：现在 Lift2 工程入口链路已经可用，意思是“机器人能进 EBench 考场、能看到观测、
能接收 16D action、能返回 reward/success 字段、证据记录也完整”。但这还不是专家轨迹，也没有到把手前、
没有 contact、没有 retention、没有 micro-pull，也没有 door joint readback。因此下一步是 A2 Lift2
oracle / retarget design review，而不是直接算 `Expert Oracle Score`。

后续判定线要按层走：A2 判定有没有合法 Lift2 oracle 方案；A3/Gate 1 判定能否到把手正前方安全位；
Gate 2 判定是否接触把手；Gate 3 判定是否抓稳；Gate 4 micro-pull / door joint readback 通过才接近
“工程上能开门”；Gate 5 记录 `PASS_EXPERT_ORACLE_SCORE_RECORDED` 才算“评测口径弄好”。Gate 5 之前，
任何 `score=0.0` 都不能被解释成 expert 失败。

A2 继续采用“不盲试”的方式：A2a 只选一个 oracle path，推荐先选 `LIFT2_SCRIPTED_ORACLE`；A2b 只做
DryingBox joint、handle frame、front approach/contact pose 和 pull direction 的静态审计；A2c 只做
Lift2/R5a `16D joint_position` translator dry contract。A2 不消耗 live budget。A3 才允许一次 selected
route live，并且只测 Gate 1 near reachability；失败后必须写 root-cause review，不能现场改参数连跑。

2026-07-06 A2a/A2b/A2c 已完成零 live evidence：
`eos2_gate1u_a2_lift2_oracle_design_review_20260706.json` 选定 `LIFT2_SCRIPTED_ORACLE`；
`eos2_gate1u_a2b_lift2_target_waypoint_static_audit_20260706.json` 固定 front approach / contact /
pull 的坐标口径；`eos2_gate1u_a2c_lift2_translator_dry_contract_20260706.json` 验证 16D action dry
contract，并要求 A3 runner 带 `--expected-action-dim 16`。这使下一步能进入 A3 single live package
准备，但 `Expert Oracle Score` 仍 blocked：还缺 A3 near reachability、Gate 2 contact、Gate 3 retention
和 Gate 4 micro-pull / door joint readback。

2026-07-06 A3 single live 已按规则只跑一次，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3_lift2_oracle_single_live_20260706/result_compact.json`。
normalized status 是
`LIVE_BLOCKED_A3_LIFT2_ORACLE_PLANNER_UPDATE_UNAVAILABLE_STOP_BEFORE_GATE2`：submit/reset 成功，但两条
waypoint 都在 planner update 阶段失败，没有 trajectory/action chunk，`executed_steps=0`。这不允许
解释成 expert 失败、policy 失败、门打不开或 `Expert Oracle Score` 失败。

A3a root-cause review 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3a_planner_update_root_cause_review_20260706.json`。
当前强线索是 A3 route/summary 都使用了 `arm=default`，而 Lift2/R5a 是 dual-arm embodiment，
planner 分成 `left_planner` / `right_planner`。因此下一个 stop/go 门是：先明确 `arm=left|right`，
并把 A2c/A3 dry contract 改到“不能缺省 arm”；只有 dry validation 不再落到 `default`，才允许一次
revised A3 live。若 revised A3 仍 `planner_update_unavailable`，停止为 dual-arm planner API /
route contract 未闭合；若 revised A3 进入 cuRobo 后才 `IK_FAIL` 或 0 action points，才停止当前
selected route 并回到 A2 route design review。

2026-07-06 A2c addendum / A3b dry 已完成这个 stop/go 门：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2c_lift2_dual_arm_route_guard_addendum_20260706.json`
把 runner guard 扩展为 `--required-arm right`，不再只检查 16D action shape；
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3b_lift2_right_arm_dry_contract_20260706/result_compact.json`
固定 revised route 为 `A3B_LIFT2_SCRIPTED_FRONT_APPROACH_NEAR_RIGHT_ARM`。dry check 证明 route 不再缺
`arm` / `rel_arm`，且 fake action chunk 仍是两步 16D `joint_position`。这允许一次 revised A3 live，
但仍不允许解释成 `Expert Oracle Score`：Gate 1 live reachability、Gate 2 contact、Gate 3 retention
和 Gate 4 micro-pull / door joint readback 仍未完成。

2026-07-06 A3c revised right-arm live 已按规则只跑一次，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3c_lift2_right_arm_single_live_20260706/result_compact.json`。
状态是
`LIVE_BLOCKED_A3C_LIFT2_RIGHT_ARM_START_STATE_WORLD_COLLISION_STOP_BEFORE_GATE2`。这次有明确进步：
旧的 `arm=default / planner_update_unavailable` 已经不是第一 blocker，planner records 都是
`arm=right`，两个 waypoint 的 world refresh 都是 `success`。但它仍然没有进入动作层：
`executed_steps=0`、`action_chunk_empty=true`，cuRobo 在规划目标前先报
`MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`，碰撞对象是 table mesh，`sphere_index=17`。

通俗解释：标准答案已经换成 Lift2 右臂能读懂的格式，但机器人还没开始往门前走，planner 就认为
“起跑姿势和桌子撞了”。这不是接触失败、抓取失败、开门失败，也不是专家分数失败。下一步已经收敛为
A3d read-only / zero-live start-state collision review：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3d_right_arm_start_state_collision_review_20260706.json`。
A3d 要先解释 sphere 17 对应哪个 Lift2 link/collision sphere，table mesh 是支撑面、桌体还是过宽碰撞体，
reset base/joint/EE pose 是否合理，以及同一 planner frame 下 sphere bottom 与 table top 是否真的相交。
只有 A3d 能给出可审计根因并通过 A3e dry/preflight，才允许 A3f 单次 revised live。A3f 过了也只代表
Gate 1 near reachability，Gate 4 过了才接近“工程上能开门”，Gate 5 记录
`PASS_EXPERT_ORACLE_SCORE_RECORDED` 才算“评测口径弄好”。

2026-07-06 A3d/A3e 继续推进但仍不进入 score。A3c trace 里的 reset event 已证明 Lift2 reset
observation 可读：`state.base` 接近原点、`state.joints` 为 12 维、`state.gripper` 为 4 维、两组
`state.ee_pose` 存在。planner response 里的 start-state collision attribution 也稳定指向 table
obstacle 与 `sphere_index=17`。但这仍缺同 frame table clearance，因此不能说 target 不可达，也不能说
可以忽略 table。A3e 当前只补 runner 诊断能力：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_runner_checkpoint_20260706.json`。
该 checkpoint 通过 TDD 给 `native_action_path_runner` 增加 diagnostic-only
`support_surface_payload` 透传，后续才能请求 `support_surface_clearance_records`。它不改变动作、不跑
contact、不跑 micro-pull、不允许 `Expert Oracle Score`。
A3e diagnostic request package 已准备：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_request_20260706/`。
这个包强制 `--max-action-points 0`，所以它即使启动 server/submit/runner，也只能作为 planner diagnostic
请求，不能升级为 reachability、contact、door 或 score evidence。

2026-07-06 A3e diagnostic request 已执行，并给出明确 no-go：runner 确实产出 2 条
`support_surface_clearance_records`，且 `support_surface_aabb_frame=planner_reference_frame`、
`sphere_frame=planner_reference_frame`，不是旧的 frame mismatch。两条记录的
`clearance_margin_m=-0.6237133788083942`，`physically_intersecting_support_surface=true`，
`planner_ignore_candidate_exact=true`，但 `planner_only_support_surface_exclusion_allowed=false`，
blocker 是 `sphere_vertically_intersects_support_surface`。runner 仍保持 `executed_steps=0`，
所以这不是接触失败、开门失败或 score 失败。raw runner classification 仍写作
`BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`，这是历史泛化标签；canonical A3e status 是
`A3E_SUPPORT_SURFACE_CLEARANCE_DIAGNOSTIC_EXECUTED_NO_GO_A3F_BLOCKED_RESET_LAYOUT_COLLIDER_CONTRACT`。
A3e 的结论是：不能进入 A3f 单次 revised live；当前 Lift2 reset/layout/collider contract 必须先回到
reset/base/joint/table-collider review，重点查 Lift2 初始高度、12D joint seed、table obstacle AABB
是整张桌体还是过宽支撑面，以及 planner collision sphere 17 对应的具体 link。

2026-07-06 A3g review 已把这个问题从“泛泛地撞桌子”收窄成一个更具体的工程修复点：
`sphere_index=17` 映射到 Lift2/R5a right-arm `link6` sphere0，A3e 半径 `0.0322199985m` 能由
R5a config 的 `raw_radius=0.02822m` + `0.004m` buffer 对上；A3e 报告的 table obstacle path 则是
`/World/labutopia_level1_poc/obj_table/Bespoke_Booth_Table_Black_Nickel_0/...` 这个完整视觉桌体 mesh，
静态 USD 里没有 `PhysicsCollisionAPI`，只有 `MaterialBindingAPI`。同一个 scene 里真正带
`PhysicsCollisionAPI` / `PhysicsMeshCollisionAPI` 的 table surface 是
`/World/labutopia_level1_poc/obj_table/surface/mesh`。因此现在的优先修复不是改专家策略、不是继续跑分，
而是 A3h：只在 planner world 里过滤或替换非 physics 的视觉桌体 obstacle，同时保留真实 table collision
surface。A3h 仍是 `--max-action-points 0` 的 preflight；只有它证明 start-state collision 不再来自这个
visual mesh，并且真实 table surface 没被删掉，才允许进入 A3f。

2026-07-06 A3h live 0002 进一步说明为什么 `Expert Oracle Score` 还不能启动：A3h 的 first staging
waypoint 已经 planner 成功并生成 `84` 个 trajectory points，但 `--max-action-points 0` 保证没有动作执行，
所以这不是 readback 或 contact evidence。第二个 handle-front near waypoint 仍然是
`MotionGenStatus.IK_FAIL`、0 points。现在的正确下一步是 A3j bounded handle-front reachability：
固定 handle frame、front direction、robot base 和 joint seed，只跑小集合 pregrasp/orientation 诊断。
如果这轮仍没有任何 IK success，就把结论限定为“当前 Lift2 + 当前 layout + 当前 handle-front route 合同
no-go”，转 layout/base/official placement 或重新设计 route；不能把它扩大成 DryingBox、EBench 或
Expert Oracle Score 全局失败。

A3j zero-live review 又把前置条件收紧了一层：现在连 bounded IK sweep 都不能马上跑，因为 A2b intended
target 和 A3h runtime target 之间存在 `0.045m` world-X mismatch。这个 mismatch 说明当前 `IK_FAIL` 可能
不是“专家路线够不到”，而是“送给 planner 的把手前目标点和我们以为的目标点不一致”。因此
`Expert Oracle Score` 更不能启动；下一步必须先做 corrected local coordinate forward-check，关闭
target-frame convention，再谈 reachability、execution、contact 和 score。

A3j1 已关闭 target-frame mismatch：corrected local target forward-check 到 intended world target 的误差
约 `3.22e-09m`。这只说明下一轮 reachability 应该测哪个点，仍不能启动 `Expert Oracle Score`。A3j2
必须先证明 corrected handle-front target 至少有一个 planner-success / nonzero-trajectory candidate，
然后才可能进入短执行、contact 和后续 score。

A3j2 的 bounded matrix 已经预注册为最多 5 个候选，且禁止继续追加 offset。它的作用是回答
“corrected handle-front target 在当前 Lift2/layout/seed 下有没有可达解”。只有 A3j2 至少一个候选 planner
success 并生成非空 trajectory，才有资格进入短执行；否则仍然不能谈 `Expert Oracle Score`。

A3j2 实际结果是全失败，所以它没有解锁短执行；A3l 随后通过 base-layout branch 解锁 A3k。这个区别很重要：
A3l pass 只能证明 planner route exists，不等于 expert oracle score exists。进入 score 前仍要逐层证明
execution readback、contact-readiness、contact、retention 和 micro-pull。

## 2026-07-05 Historical Task 5M Status

历史状态：EOS-2 当时推进到 Task 5M state-reference rerun。证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias_state_reference/summary_compact.json`。
它证明 5M route 已经接进 `planner-trajectory-execution-readback` 的 post-replay 路径，第一段
bridge replay 仍执行 `151` 步并达到 joint target，final joint error 约 `7.10e-05 rad`。同时，
早先的 `NoneType` 输入 bug 已经越过：post-replay calibration 使用 `state.ee_pose`，
`replan_error=null`。当前第一失败门是
`post_replay_centerline_candidate_solver_no_candidate`，也就是 centerline candidate solver 没有产出
numeric candidate：`candidate_count=0`、`candidate_failure_reason=PAD_DEPTH_MISS`。通俗讲，
系统已经知道要沿把手中线找夹爪中心点，但左右手指同时满足 bilateral contact-frame 的可行区间
还差约 `9.7mm`，所以还没进入 post-replay IK、close-hold 或 retention。下一步先做
candidate-only tolerance / padding preflight，在 `0.010m` 到 `0.012m` 附近让
`candidate_count>0`，再重跑完整 Isaac planner live；当前仍不能进入 micro-pull、door metric 或
`Expert Oracle Score`。

2026-07-05 已补 candidate-only preflight code checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_candidate_preflight_code_checkpoint_20260705.json`。
这一步把“继续尝试”的边界收紧：先只生成 candidate，不调用 post-replay planner，不执行 close-hold，
不计算 score。有限矩阵只包含两组主参数：
`grasp_selection_axis_gap_threshold_m=[0.006,0.008,0.0095,0.010,0.011,0.012,0.014]` 和
`grasp_contact_model_handle_x_padding_m=[0.003,0.0048,0.005,0.006,0.008,0.010,0.012]`。
如果两组都不能让 `candidate_count>0`，就停止当前 5M centerline 模型，写
`BLOCKED_5M_CENTERLINE_MODEL_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`，不继续扩大 offset 硬试。

2026-07-05 bounded preflight 已实际跑完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_candidate_preflight_bounded_sweep/summary_compact.json`。
结果为 `run_count=14`、`candidate_found=false`，正式分类
`BLOCKED_5M_CENTERLINE_MODEL_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`。通俗讲，系统能把机器人带到
门把手附近，但旧 centerline 候选模型没有把当前 drying box 的真实把手解释成“夹爪可以抓的一个点”。
所以 Expert Oracle Score 不能在这一层硬算：没有合法 candidate，就没有可交给 post-replay planner
的目标，也就没有后续 close-hold、retention 或开门评分。下一步必须先替换 candidate-generation
模型，优先做 mesh-aware / open-face handle candidate，并给新模型重新跑 candidate-only gate。

2026-07-05 Task 6C geometry audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_geometry_audit_20260705.json`。
当前状态推进为 `PASS_HANDLE_GEOMETRY_AUDIT_READY_FOR_MESH_AWARE_CANDIDATE`：真实 handle、door leaf
和 RevoluteJoint 已在 EBench-loaded USD 中唯一定位，open-face normal 是 `[0.0, 1.0, 0.0]`。
但这个 normal 来源是 `handle_door_center_delta_overlap_fallback`，说明静态 AABB 有重叠，下一步必须
把 fallback 来源写进 candidate label / metadata。Expert Oracle Score 仍然不能启动；现在只允许进入
mesh-aware/open-face candidate-only preflight，先证明 `candidate_count > 0`。

Score 阶段的进入条件也随之明确：不是再多跑几次就能算分，而是必须按顺序过门。第一门是
mesh/open-face candidate-only preflight；如果最多 `8` 个有界候选组合后仍没有
`candidate_count>0`，就写
`BLOCKED_MESH_AWARE_CANDIDATE_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`，停止这条候选模型。第二门是
one full planner/readback，第三门是 close-hold/contact-retention，第四门是 micro-pull/door joint
readback。只有第四门证明“抓住并能带动门”后，才进入第五门 `Expert Oracle Score`。因此 PM 侧可理解为：
候选门失败能早停，retention 通过才算工程上接近弄好，score 通过才算评测口径弄好。

2026-07-05 第一门的 code gate 已补齐：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_candidate_preflight_code_checkpoint_20260705.json`。
它新增 `mesh-open-face` post-replay candidate source，读取 Task 6C geometry audit JSON，并把 fallback
normal 来源写入 candidate metadata。真实 audit 下的离线 primary contact target 是
`[0.47978996139738445,0.27571899126186217,1.1085915534527668]`，opposite sign sanity target 是
`[0.47978996139738445,0.22180747411861262,1.1085915534527668]`。这仍然不能启动
`Expert Oracle Score`：它只证明代码能生成下一轮 candidate-only preflight 的输入。下一步必须拿
live summary 证明 `candidate_count>0`，再谈 planner/readback。

2026-07-05 live candidate-only evidence 已经补上：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_candidate_preflight_live_20260705_primary/summary_compact.json`。
这一步证明第一门已过：`candidate_source=mesh-open-face`、`candidate_count=1`，候选
`contact_target_world=[0.47978996139738445,0.27571899126186217,1.1085915534527668]`，并且
`handle_open_face_source=handle_door_center_delta_overlap_fallback` 被保留下来。但它仍是
`candidate_preflight_only=true`：`attempted_candidate_count=0`，没有 post-replay planner action
points，也没有 close-hold、retention、micro-pull 或 door joint readback。因此 Expert Oracle Score
仍不能启动；下一步必须先跑 one full post-replay planner/readback。

2026-07-05 one full post-replay planner/readback 已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_planner_readback_live_20260705_primary/summary_compact.json`。
结果把 blocker 从“候选是否存在”推进到“post-bridge 可达性”：`candidate_count=1`、
`attempted_candidate_count=1`，但 contact target 在 cuRobo 中 `MotionGenStatus.IK_FAIL`，
`available_action_points=0`。这不是 Expert Oracle Score 失败，也不是 door metric 失败；它还没有
产生第二段 action trajectory。

随后已做 bridge-to-near bounded sanity，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_bridge_to_near_bounded_sanity_20260705/summary_compact.json`。
这一步把目标从 contact 点切到 `approach_near_target_world`，只测“先到把手前方安全点”。
`0.035m` near 和 `0.045m` farther-near 两条都进入 cuRobo planning，但都 `IK_FAIL` 且没有
post-replay action points；bridge replay 自身仍 reaching joint target。分类为
`BLOCKED_MESH_OPEN_FACE_BRIDGE_TO_NEAR_REACHABILITY_AFTER_BOUNDED_NEAR_OFFSET`。因此
Expert Oracle Score 仍不能启动；下一步必须先改 approach seed / robot staging / wrist orientation，
而不是继续算分、微拉或扩大 contact 参数。

2026-07-05 已新增下一阶段计划：
`docs/superpowers/plans/2026-07-05-eos2-approach-seed-robot-staging-redesign.md`。这份计划明确
`Expert Oracle Score` 是第 5 门，不是下一步：第 1 门先证明 wrist orientation / approach seed /
robot staging 能产出可执行的 handle-front approach trajectory；第 2 门才测 contact；第 3 门测
close-hold / retention；第 4 门测 micro-pull / door joint readback。只有前 4 门都有 live evidence
通过，才允许把专家轨迹拿到 EBench metric 下算分。

Gate 1 的代码入口已完成，checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_code_checkpoint_20260705.json`。
这一步只证明 probe 能在 `native-open` 和 `post-replay-ee` 两种 wrist orientation source 之间切换，
并把 source 写入 waypoint / summary metadata。它仍不能启动 `Expert Oracle Score`；必须先跑
Gate 1 live isolation probe，证明 `available_action_points>0` 且 replay readback 到 joint tolerance。

Gate 1A 的 live isolation probe 已完成，compact evidence 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045/summary_compact.json`。
结论不是“可以算分”，而是 `post-replay-ee` wrist orientation 不足以解除 handle-front reachability
blocker：mesh/open-face 候选生成成功，`candidate_count=1`；但 post-replay cuRobo replan
返回 `MotionGenStatus.IK_FAIL`，`available_action_points=0`、`selected_plan_success=false`。
这一步足够停止 orientation-source tuning，但还不能把整个 Gate 1 判死，因为 bridge replay 这轮虽然
达到 joint tolerance，也触发了 `64` step cap，而 bridge 本身有 `151` 个 action points。

Gate 1B bounded staging family 随后已跑完，compact evidence 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_family_live_20260705/summary_compact.json`。
这次找到了一个可执行 staging parent：`post_bridge_local_z_m006_q_bridge`，post-replay replan
生成 `90` 个 action points，staging replay 也达到 `0.02 rad` joint tolerance。它的正式分类是
`STAGING_CONTINUATION_EVIDENCE_ONLY_REQUIRES_GATE_1C_STAGING_TO_MESH_OPEN_FACE_APPROACH_NEAR`。
通俗讲，机器人已经能先走到一个更合适的中间站，但还没有证明能从这个中间站走到把手正前方。
因此 Gate 1 仍未完成，不能启动 contact、close-hold、micro-pull 或 `Expert Oracle Score`。
下一步只做 Gate 1C：从 `post_bridge_local_z_m006_q_bridge` 继续规划到 mesh-open-face
`approach_near_target_world`。如果 Gate 1C 通过，才进入 contact；如果 Gate 1C 仍是
`IK_FAIL` 或 0 action points，就停止当前 bridge + staging parent 路线，改为重新设计 robot
layout / staging 或 candidate-generation，而不是继续扫 contact 或 score。

Gate 1C selected staging-to-near live probe 已在 2026-07-05 跑完，compact evidence 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_to_mesh_open_face_near_live_20260705/summary_compact.json`。
分类是 `BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS`。这一步证明：
bridge replay 和 `post_bridge_local_z_m006_q_bridge` staging parent 都能达到 joint tolerance，
但从这个中间站继续到 mesh-open-face `approach_near_target_world` 时，cuRobo 返回
`MotionGenStatus.IK_FAIL` 且 `available_action_points=0`。所以 Expert Oracle Score 不是“算起来很难”
本身，而是前置专家动作还没有走到可评分的开门前置状态；没有可执行的 near/contact/retention/micro-pull
证据，就不能把 EBench metric 拿来判专家答案。

review 后的下一步不是 contact，也不是马上大 redesign，而是 Gate 1D：
`Sibling Staging-to-Near Bounded Triage`。它只预注册少量 sibling staging parent，保持同一个
bridge、mesh-open-face `approach_near_target_world`、orientation source 和 planner path，只问
“是不是只选错了 `post_bridge_local_z_m006_q_bridge`”。如果 Gate 1D 也全部 `IK_FAIL` / 0 action
points，再进入 Gate 1R：`Robot Layout / Staging Redesign Gate`。Gate 1R 必须重新产出
`PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`，否则仍不能启动 contact 或 score。

Gate 1D 已在 2026-07-05 跑完，compact evidence 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_sibling_staging_to_near_live_20260705/summary_compact.json`。
分类是 `BLOCKED_APPROACH_SEED_SIBLING_STAGING_TO_NEAR_FAMILY_IK_FAIL_NO_ACTION_POINTS`。两条
sibling staging parent 都没有打开新路线：bridge replay 到位，但 `post_bridge_local_y_p006_q_bridge`
和 `post_bridge_local_x_m006_q_bridge` 各自在 staging replan 阶段就是 `MotionGenStatus.IK_FAIL`、
0 action points，因此没有执行到 handle-front near follow-up。这说明下一步必须进入 Gate 1R；
在 Gate 1R 产出新的 near reachability PASS 之前，任何 Expert Oracle Score 都没有可评分专家动作链。

Gate 1R 的执行合同已经收敛为 `Robot Layout / Staging / Candidate-Generation Redesign Gate`。
下一步优先改 robot base/layout 的 XY 相对位置，只预注册三个 layout 候选：
`R1_layout_y_p010` 使用 robot base `[-0.4, 0.10, 0.73]`，`R2_layout_x_p012` 使用
`[-0.28, 0.0, 0.73]`，`R3_layout_x_p012_y_p008` 使用 `[-0.28, 0.08, 0.73]`。三者都固定
asset、metric、planner route、base z=`0.73`、no reset seed、bridge label、`z_m006` staging、
mesh-open-face primary normal、`approach_offset=0.045` 和 `orientation_source=post-replay-ee`。
只有当 bridge、staging、near 三段都产生 action points 并 replay 到 `0.02 rad` joint tolerance，
才允许写 `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`。如果 R1-R3 至少有 clean
reset + bridge 但 near 仍失败，才条件运行 `R4_approach_line_staging_under_best_layout`，把 staging
改成 handle open-face approach-line staging。无论哪条路线，Gate 1R 通过也只允许进入 Gate 2
contact planner/readback，不能直接启动 `Expert Oracle Score`。

预计节点也随之明确：Gate 1C 是当前 selected route 的 no-go 点；Gate 1D 是 sibling staging 小集合
分流；Gate 1R 是更大路线重设；Gate 3 通过只能说明 grasp/retention 成立；
Gate 4 通过才接近“工程上弄好”；Gate 5 通过并记录 `PASS_EXPERT_ORACLE_SCORE_RECORDED`，才算
“评测口径弄好”。在 Gate 5 之前，任何 `score=0.0` 都不能被解释成 expert 失败。

2026-07-06 Gate 1R live 已完成，compact evidence 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_gate1r_layout_live_20260706/summary_compact.json`。
分类是 `BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS`。R1/R2/R3 三个
robot base/layout 候选都能 replay bridge，也都能规划 `post_bridge_local_z_m006_q_bridge` staging；
但三者从 staging 到 mesh-open-face `0.045m near` 全部 `MotionGenStatus.IK_FAIL`、0 action points。
因此按预注册合同触发 R4。R4 选 R2 layout，preflight 生成 `0.085m` handle open-face
approach-line staging，再 live 作为 explicit staging 跑；结果 bridge 仍到位，但 R4 staging 本身
`IK_FAIL`、0 action points，near follow-up 被跳过。

所以 `Expert Oracle Score` 仍不能启动。当前不是 score 计算难，而是专家动作链连“到把手前安全点”
都没有可执行 trajectory。下一步应进入 `Gate 1S: Strategy Redesign / No-Go Review`，决定是否改
task layout、route generation、oracle/controller 生成或机器人合同；在 Gate 1S 给出新路线并重新拿到
`PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT` 之前，任何 `Expert Oracle Score`、
policy score 或 official score 都没有可评分动作依据。

Gate 1S review manifest 已建立：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_strategy_review_20260706.json`。Gate 1S is now
the next stage. It is a strategy redesign / bounded no-go review, not another local offset sweep. The
selected default strategy is `S1_TASK_LAYOUT_NORMALIZATION`, with `max_selected_live_strategy_count=1`.
Gate 2 and Expert Oracle Score remain blocked until a new
`PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT` is recorded.

Gate 1S selected strategy live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_selected_strategy_live_20260706/summary_compact.json`。
分类是 `BLOCKED_GATE1S_SELECTED_STRATEGY_NO_NEAR_REACHABILITY`。S1 的 layout normalization 诊断下，
bridge replay 仍成功，但 mesh-open-face `0.045m near` 继续 `MotionGenStatus.IK_FAIL`、0 action
points。按照 Gate 1S 的 `max_selected_live_strategy_count=1` 约束，当前精确定义的
EBench+Franka+LabUtopia DryingBox 合同已经到 bounded no-go 建议点。

因此 `Expert Oracle Score` 仍不是下一步。它没有失败，也没有被计算；它缺少前置 scoring-eligible expert
trajectory。后续若继续，需要先改合同并重新从 Gate 1 证明 near reachability，而不是在当前合同下继续跑
score。

5K-A 是 5L/5M 的上游输入，不是当前第一失败门。它曾完成 staged-combination 单候选 live
probe。compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`。
通俗讲，`x_m002_ori_z_p02` 不是 IK blocker：post-replay replan 成功，选中的 waypoint 就是
`x_m002_ori_z_p02`，并生成 `40` 个可执行 action point；随后 close-hold 也执行了 `15` 步并达到
joint target。真正失败点仍是 hand/handle retention：tail window 内 bilateral overlap、
required-role near 和 required-role PhysX contact 都是 `0`，15/15 记录都是
`AABB_OUTSIDE_CONTACT_FRAME`。它相对 5J-F 把双指 world Y gap 各补回约 `1.8mm`，但又把 world X gap
各恶化约 `0.6mm`；相对 5J-A 则是 X gap 更好、Y gap 更差。结论是“组合候选把 tradeoff 暴露清楚了”，
不是“已经抓住”。因此现在仍不能进入 micro-pull、door metric 或 `Expert Oracle Score`。

EBench `microwave` 的参考实现给了下一步方向：它也不是直接 replay 资产里的
`skill_trajectory`，而是在 task YAML 中写 task-level manual `custom_motion` waypoints，
其中既有相对微波炉的 `object_frame` 目标，也有 `robot_frame` staging；runtime 再把这些点
转成 world/robot pose，并通过 cuRobo 在线生成 joint trajectory。对 PM 来说，这意味着
DryingBox 的 oracle 不应继续围绕“一个旧轨迹能不能照抄”打转，而应进入 Task 5L：用
handle/contact frame 生成候选目标，先做 prepared manifest review，再只跑一个保守 live
候选。5L 计划见
[`../superpowers/plans/2026-07-05-eos2-contact-frame-handle-frame-target-generation.md`](../superpowers/plans/2026-07-05-eos2-contact-frame-handle-frame-target-generation.md)。

2026-07-05 Task 5L prepared review 已推进一步：candidate manifest
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_review_20260705_5l_candidates.json`
已生成，状态是 `PREPARED_REVIEW_NOT_LIVE_EVIDENCE`。它只登记一个保守候选
`5l_cf_handle_right_025_clamped_xy12_zp02`，并用 focused pytest 锁定 5K-A right-finger gap
到候选参数的转换合同。该 manifest 不是 live Isaac 证据，仍不能进入 micro-pull、door metric
或 `Expert Oracle Score`；下一步才是按单候选 live probe 验证 planning / execution /
retention。

2026-07-05 Task 5L live probe 已跑完单候选：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json`。
通俗讲，机器人仍能完成第一段 bridge replay，说明“考场、reset、bridge 路线和 action replay”
没有退化；但新候选 `5l_cf_handle_right_025_clamped_xy12_zp02` 太激进或姿态不可达，在
post-replay replan 阶段返回 `MotionGenStatus.IK_FAIL`，没有生成 action points，也没有进入
close-hold。分类是 `BLOCKED_5L_HANDLE_FRAME_TARGET_IK`。因此当前仍不能进入 micro-pull、
door metric 或 `Expert Oracle Score`；下一步应把 5L 候选拆成更小 reachability ladder 或
staged handle-frame target review。

2026-07-05 Task 5M 已规划为
[`EOS-2 Handle-Frame Reachability Ladder`](../superpowers/plans/2026-07-05-eos2-handle-frame-reachability-ladder.md)。
白话解释：5L 证明“bridge 能走到，但新把手目标不可达”；5M 要把“不可达”继续拆细，先用
`centerline` / `inner-face-corridor` / `bilateral-contact-frame` 找一条更合理的把手中线，再逐个
live 验证。它不是 micro-pull，也不是打分阶段；只有当某个 5M candidate 同时通过 post-replay
replan、execution readback、close-hold 和 retention，才允许新开 micro-pull / door joint readback
计划。
2026-07-05 路线复核补充：5M 不能直接用 default oracle 的 `centerline` live 结果来回答 5L
问题。5L 的可比证据路径是 `planner-trajectory-execution-readback` 的 post-replay replan，
因此下一步先补 route binding：把 centerline / bilateral-contact-frame 的结果变成明确的
post-replay object-frame waypoint，再跑 Isaac live。绑定前状态是
`BLOCKED_5M_ROUTE_CONTRACT_NOT_BOUND`，不能解释成专家策略失败或机器人抓取失败。

2026-07-05 route binding 已进入 code-ready 状态：GenManip 新增
`--planner-trajectory-post-replay-candidate-source centerline`，会在 bridge replay 后用 live
debug state 生成 centerline / inner-face / bilateral-contact-frame candidate，并转换成
`obj_DryingBox_01_handle` 的 object-frame waypoint，继续走同一个 post-replay candidate
sweep。code checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_route_binding_code_checkpoint_20260705.json`。
这只解除“路线没接上”的 blocker；随后 5M first route-bound live probe 已跑完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary_compact.json`。
这次 bridge replay 成功，`executed_steps=151`、`reached_joint_target=true`，说明考场、reset、
bridge 路线和 action replay 没有退化。但 post-replay centerline replan 在候选生成/输入阶段中断：
`candidate_count=0`、`available_action_points=0`，并报
`TypeError("float() argument must be a string or a real number, not 'NoneType'")`。所以它的分类是
`BLOCKED_5M_CENTERLINE_SOLVER_INPUT`，不是 centerline IK 失败，也不是 contact retention
失败；close-hold 没有执行，retention summary 是 `no_post_replay_worker_state`。因此当前仍然
没有 5M reachability、close-hold、retention、micro-pull、door metric 或 `Expert Oracle Score`
证据。

2026-07-05 后续 state-reference rerun 已经把上面的 `NoneType` 输入 blocker 继续推进一步：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias_state_reference/summary_compact.json`。
`reference_source=state.ee_pose`、`replan_error=null`，所以旧输入错误不再是当前门槛；当前门槛是
`PAD_DEPTH_MISS/no_candidate`，即 bilateral contact-frame 的几何约束还没有求出 numeric
centerline candidate。它仍然不是 IK failure，也不是 contact retention failure，因为没有第二段
planner record、没有 close-hold，也没有 retention telemetry。

早期 bridge evidence 位于
`docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_bridge_ladder_20260704_181425/`：
no-refresh 下 `approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 能规划出
152 个 trajectory points；第一次 world-refresh 复跑在 reset 阶段 Ray OOM，不能作为
planner/collision 证据；retry2 中 reset 和 12 个候选的 world refresh 都成功，但所有候选
统一失败为 `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`。

这条 retry2 当时把下一步指向 **bridge start-state collision attribution**。该 attribution
已经由后续 Task 4c live classify evidence 完成：具体 blocker 是
`/World/labutopia_level1_poc/obj_table/surface/mesh` vs `panda_hand`。Task 4d.3
no-extra-ignore support-surface clearance audit 也已经完成：runtime 读到了 table AABB，
也记录了 cuRobo 报碰撞的 `panda_hand` sphere。2026-07-05 代码复核发现旧
`sphere_center_world` 字段名过强，因为 cuRobo obstacles 和 robot spheres 都在
planner/reference frame，不是 USD stage world frame；随后 Task 4d.4A 已重跑
frame-aware live audit，把 table AABB 转到 planner/reference frame 后再计算。新证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_support_surface_frameaware_clearance_audit_20260704_221731/`，
compact 文件是 `pose_ladder_support_surface_frameaware_compact.json`。这次 submit/probe exit
code 均为 `0`，12/12 条记录都是 `measured_same_frame`，并且同 frame
`clearance_margin_m=-0.011760663122180937`；因此 planner-only table support-surface
exclusion 仍然不允许。

2026-07-05 Task 4d.4B **base-z-lift isolation** 已完成：新证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_base_z_lift_002_20260704_223919/`，
compact 文件是 `pose_ladder_base_z_lift_002_compact.json`。这次只把 Franka diagnostic
base position 从 `[-0.4, 0.0, 0.71]` 改成 `[-0.4, 0.0, 0.73]`，其它资产、metric、
planner 和 pose-ladder 参数不变。submit/probe exit code 均为 `0`；start-state collision
从上一轮 12/12 个候选全部 `INVALID_START_STATE_WORLD_COLLISION` 变为 `0`；第二个
bridge candidate `approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity`
在 world refresh 下规划成功，`trajectory_point_count=152`。这说明 blocker 的主因更像是
Franka reset/base clearance，而不是应该立刻 exact ignore table surface。重要边界：
`base_z_lift_002` 当时仍是诊断隔离实验，不是最终产品姿态；后续 Task 4d.4D 已把它推进为
base-z-only promotion candidate，再继续前仍要接受一个任务兼容的正式 reset/base contract。

2026-07-05 Task 4d.4C 继续补强了 reset contract 证据：GenManip debug state 现在会在
`debug.labutopia_open_door` 和 `pose_ladder_reset_debug_excerpt` 里写出 observed
`robot_prim_path`、`robot_world_position`、`robot_world_orientation_wxyz`。机器可读 checkpoint
是
`docs/labutopia_lab_poc/evidence_manifests/eos2_reset_base_observed_pose_code_checkpoint_20260705.json`。
随后用同一个 base-z-lift config 复跑 live，证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_base_z_lift_002_observed_base_20260704_225244/`，
compact 文件是 `pose_ladder_base_z_lift_002_observed_base_compact.json`。这次 observed
robot base 为 `[-0.4000000059604645, 2.98e-10, 0.7300000190734863]`，start-state
collision 仍为 `0`，第二个 bridge candidate 仍规划出 152 个点。这个结果证明 base-z-lift
不是只改了 YAML 文字，而是真正进入了 Isaac/USD robot prim；但它仍是 diagnostic-only，
还不能宣布最终产品 reset policy。

2026-07-05 Task 4d.4D **reset contract branch decision** 已补两条对照证据。第一条是
`default_joint_positions` 分支：
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_reset_seed_retract_001_20260704_230558/pose_ladder_reset_seed_retract_001_readback_compact.json`。
它保持 base position `[-0.4, 0.0, 0.71]`，配置 9D Franka reset seed
`[0, -1.3, 0, -2.5, 0, 1.0, 0, 0.04, 0.04]`。live readback 证明 7D arm seed
确实进入 reset，EE pose 也改变到约 `[0.1106, 0, 0.5907]`；但是 cuRobo start-state world
collision 仍是 12/12，blocker 还是 table surface vs `panda_hand`。因此“只换 reset
关节姿态”不能作为当前最小闭环。第二条是 **base-z-only promotion candidate**：
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_base_z_lift_002_only_20260704_231348/pose_ladder_base_z_lift_002_only_compact.json`。
它只把 robot base z 从 `0.71m` 改到 `0.73m`，不设置 `solver_velocity_iteration_count`，
也不关闭 `enabled_self_collisions`。submit/probe exit code 均为 `0`；observed robot base
z=`0.730000019m`；start-state collision 为 `0`；第二个 bridge candidate 规划成功，
`trajectory_point_count=152`。结论：当前正式 reset contract 候选应优先走
`position: [-0.4, 0.0, 0.73]` 的 POC-specific layout，而不是继续在 `default_joint_positions`
上盲调。

2026-07-05 Task 4d.4E **formal reset contract landing** 已落到 GenManip 配置层：
`configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml` 的 Franka position
已从 `[-0.4, 0.0, 0.71]` 更新为 `[-0.4, 0.0, 0.73]`，并且没有加入
`default_joint_positions`、solver override、self-collision disable 或 oracle debug obs。普通
open-door diagnostics 也同步到 `0.73m`；`reset_seed_retract_001` 保留 `0.71m` 作为失败对照。
机器可读 checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_open_door_formal_reset_contract_checkpoint_20260705.json`。
验证：`test_franka_robot_config_contract.py` 全量 `7 passed`。边界：formal config 已更新，
但 bounded execution/readback 还没跑；因此仍不能宣布 stable grasp、micro-pull、door opened
或 Expert Oracle Score。

2026-07-05 Task 4d.4F **bounded execution/readback on formal base-z contract** 已跑完：
证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_bounded_execution_base_z_073_20260704_233033/`，
compact 文件是 `lead_in_base_z_073_compact.json`。这次用 fresh EBench / GenManip server
和正式接受的 `base_z=0.73m` 路径进入 runtime；第一次 submit 暴露了一个环境调用问题：
`python -m genmanip_client.cli submit ...` 在当前 `genmanip-client` 里不会真正调用
`main()`，导致 probe 报 `No job started`。这不是资产或 physics 失败，已保留为
`no_job_probe.*` 证据；正确方式是直接从 Python 调 `from genmanip_client.cli import main`
并传入 submit 参数，随后 submit/probe 都正常退出。

正式 bounded lead-in 的结果是 diagnostic fail，而不是开门成功。`parse_only_ik.ik_success=true`
说明 `approach_pre` 的 IK target 能算出来；probe 也实际执行了 53 个分步 joint-position
lead-in，每步命令侧限制在 `0.05 rad`。但真实 readback 在后段开始发散：step 51 的
`post_world_step_delta_abs_max=0.7169004827737808`，step 52 触发
`arm_state_jump_too_large`，`post_world_step_delta_abs_max=3.818413570523262`，最后距离目标
仍约 `0.7789338976144791 rad`，`reached_joint_target=false`。产品口径：现在已经证明
“考场、reset/base、IK 和分步执行诊断链路都能跑起来”，但还没有证明“机器人能稳定到把手、
抓住、微拉或开门”。下一步不能继续把一个 absolute IK target 拆小步硬 replay，而要转向
EBench 原生 `microwave` 使用的方式：object-frame manual waypoints + 每个 waypoint 用
cuRobo 在线规划和 readback 验证。

2026-07-05 EBench `microwave` 参考实现核对：EBench / GenManip 里确实有微波炉任务，
例如 `configs/tasks/ebench/mobile_manip/val_train_20p/microwave.yml` 的 instruction 是
`Heat the eggtart with the microwave.`，`task_name=ebench/mobile_manip/microwave`，机器人是
`manip/lift2/R5a`，微波炉对象声明为 articulated。它的开门 expert 不是直接 replay
`assets/objects/articulation_data.json` 里的原始 `skill_trajectory`；当前 manual path
在 YAML 里写 `custom_motion` 的 `object_frame` waypoint，相对 `microwave` 指定手爪位置、
姿态和 grasp/pending 状态。`custom_motion.py` 会把 object-frame / robot-frame waypoint
转换到 world pose，再调用 `BaseEmbodiment.plan_pose`，最后进入 cuRobo
`MotionGen.plan_single` 生成 joint trajectory 并通过 `PlanningRecorder` 执行/记录。通俗讲：
EBench 的 expert 更像“给机器人一串相对物体的导航点，让 planner 现场算怎么走”，而不是
“把某个机器人旧轨迹文件逐帧照抄”。DryingBox 后续也应按这个范式重写 oracle 入口。

2026-07-05 Task 5A **planner trajectory export code checkpoint** 已完成，机器可读
checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_export_code_checkpoint_20260705.json`。
这一步补的是 bounded fail 后缺失的中间件：之前 planner-only endpoint 只告诉我们
`trajectory_point_count`，没有把 cuRobo 规划出的 joint trajectory 返回给 probe，所以 probe
只能自己对一个 absolute IK target 做小步插值。现在 `plan_object_frame_waypoints` 支持默认关闭的
`include_trajectory_points`；显式开启后，successful waypoint record 会带
`trajectory_joint_positions` 和 `trajectory_action_joint_positions`。前者是 raw planner
joint points，用于审计；后者是经过 `embodiment.convert_curobo_result_to_action` 转成
runtime `joint_position` action 的 payload，并带 joint names、control type 和 replay policy。
`online_open_door_oracle_probe.py` 会在 summary/trace 中保留它们，`genmanip-client` 也能把该
flag 传到 server。review 后还加了 non-finite guard，避免把 `NaN` / `Infinity` 轨迹序列化成
下一步输入。验证记录见同名 checkpoint manifest；本段验证会随 fresh rerun 更新。

重要边界：Task 5A 仍是 code/unit checkpoint，不是 live Isaac execution。它没有执行任何
joint target，没有证明 stable grasp、micro-pull、door opened 或 Expert Oracle Score。下一步
Task 5B 的 code checkpoint 已完成，manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_execution_readback_code_checkpoint_20260705.json`。
现在 probe 已经有 `planner-trajectory-execution-readback` 模式：先规划 object-frame
waypoints，拿回 `trajectory_action_joint_positions`，再在 fresh replay run 里逐帧发
absolute `joint_position` action，并记录每一步 controller readback。raw
`trajectory_joint_positions` 只保留作 planner 审计。review 后已保证 action-only payload 可用、
fresh replay run 不会和 planner run 混在一起，summary 也有 stable grasp / micro-pull / score
的 no-claim guards。

2026-07-05 Task 5B live rerun 已跑一轮，证据入口是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_execution_readback_live_20260705_005444/planner_trajectory_execution_summary.compact.json`。
这次解决的是旧生命周期 blocker：`submit` 后 worker list 为空并不代表 job 坏了，而是还没有
`reset` 创建 worker。probe 现在先 `reset`，确认 worker 0 的 observation 可用，再请求
`plan_object_frame_waypoints`；fresh live run 中 `/reset` 和 `/plan_object_frame_waypoints`
都返回 200，旧的 `worker 0 does not exist` 已越过。

新的 blocker 是 planner target 本身：`approach_pre`、`approach_near`、`contact` 三个
DryingBox object-frame waypoint 都是 `MotionGenStatus.IK_FAIL`，`trajectory_point_count=0`，
没有 `trajectory_action_joint_positions` 可 replay。因此 5B live 目前不是“轨迹执行失败”，而是
“还没有规划出第一段可执行轨迹”。下一步要回到 object-frame target / wrist orientation /
reachability 校准；只有 planner 先生成 action-level trajectory，并且 replay readback 稳定，才允许
继续进入 grasp/contact/micro-pull 或 Expert Oracle Score。
当前仍不能汇报 stable grasp、micro-pull、door opened、`Expert Oracle Score`、policy score、
official score 或 full collision-aware planning。

2026-07-05 Task 5C **formal-safe explicit bridge waypoint** 已完成一轮 code + live
闭环。先保留一个失败证据：
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_bridge_execution_readback_live_20260705_5c_0100/`。
这轮失败的关键不是 cuRobo 不工作，而是正式 `level1_open_door.yml` 的 reset observation
不暴露 `debug.labutopia_open_door`；所以以前调试脚本里“根据 reset debug 动态生成 bridge
waypoint”的逻辑在正式配置下拿不到必要信息，planner payload 里实际只有
`approach_pre`、`approach_near`、`contact` 三个默认点，选中的 bridge label 只是后处理里的
失败记录。

修法不是继续依赖 debug，而是把成功 bridge pose 固化成显式 object-frame waypoint
contract：`--planner-trajectory-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`。
新证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_explicit_bridge_execution_readback_live_20260705_5c_0120/planner_trajectory_explicit_bridge_execution_summary.compact.json`。
结果为 `PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY`：
选中的 `approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 在 formal config
下规划成功，生成 `152` 个 action-level trajectory points，实际 replay `152` 步，
`reached_joint_target=true`，最终 joint target 误差约 `7.13e-05 rad`，低于 `0.02 rad`
阈值，`blockers=[]`。代码 checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_explicit_waypoint_code_checkpoint_20260705.json`，
测试记录包括新增 TDD RED/GREEN、review 后的 non-finite translation guard、
`planner_trajectory_execution_readback` focused tests 和整份 probe 单测 `272 passed`。

给 PM 的一句话：现在已经证明“正式考场能吃到我们指定的桥接导航点，规划器能算出 152
步路线，机器人也能按这 152 步走到目标关节姿态”。但这仍只是“从 reset 往把手靠近的中间桥”，
不是完整开门专家答案；还没有闭爪、稳定抓住把手、micro-pull、门角度变化或 EBench metric
得分。因此 `Expert Oracle Score` 仍保持 planned，下一步要把 bridge 后面的
handle-side approach/contact、close/grasp 和 micro-pull 分段接上，每段都按同样的 planner
trajectory + readback 证据签收。

2026-07-05 Task 5D **post-replay replan/readback** 已完成一轮 code + live
证据。code checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_code_checkpoint_20260705.json`；
live 证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0200/summary_compact.json`。
这一步问的是：“机器人按 bridge 路线走到中间点以后，能不能不重开考场、直接基于当前姿态继续
让 planner 算下一段？”结果是：通路已经打通，但下一段目标还不对。`5d_0200`
里 selected bridge waypoint 规划成功，生成 `150` 个 action-level joint points，probe
实际 replay `150` 步，`reached_joint_target=true`，最终 joint target 误差约
`7.13e-05 rad`，小于 `0.02 rad` 阈值。随后 probe 在同一个 post-replay worker state
上再次调用 `plan_object_frame_waypoints`，说明“连续规划”这个接口路径已经存在；但 follow-up
目标仍使用旧的 `approach_pre`，cuRobo 返回 `MotionGenStatus.IK_FAIL`，没有生成第二段
`trajectory_action_joint_positions`。

给 PM 的一句话：现在不是“跑不起来”，而是“第一段桥走通了，第二段导航点还不是 Franka
从桥接姿态继续靠近把手时能到达的点”。因此 `Expert Oracle Score` 仍不能启动；下一步要设计
bridge-relative 的 handle-side approach/contact waypoint family，先让第二段也能生成 action
trajectory 并通过 readback，再进入 close/grasp、micro-pull 和门角度 metric。
当前仍不能汇报 stable grasp、micro-pull、door opened、`Expert Oracle Score`、policy score、
official score 或 full collision-aware planning。

2026-07-05 Task 5E **post-bridge follow-up waypoint candidate sweep** 已完成 code
checkpoint，manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_code_checkpoint_20260705.json`，
实施计划是
`docs/superpowers/plans/2026-07-05-eos2-post-bridge-followup-waypoint-family.md`。
这一步补的是 5D 暴露出的“第二段导航点选择能力”：probe 现在可以在 bridge replay 后通过
`--planner-trajectory-post-replay-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`
传入一组 handle-side follow-up 候选点。多 agent 复核后做了一个关键架构修正：候选点是
alternatives，不是连续 waypoint chain；GenManip 的 server-side `object_frame_waypoint_planner`
在同一次 planner call 内会把成功 waypoint 推进本地 `sim_js`，所以不能一次塞一组候选再把它们
当独立可达性结果。5E probe 会逐个 candidate 单独调用 planner，汇总
`candidate_records`、`selected_waypoint_label`、`failure_status_counts`，如果没有显式指定
`--planner-trajectory-post-replay-waypoint-label`，就选择第一个 `plan_success=true` 的候选。

验证：新增 TDD 先 RED 后 GREEN；`sweeps_post_replay_extra` 为 `1 passed, 273 deselected`；
`planner_trajectory_execution_readback or post_replay` 为 `7 passed, 267 deselected`；
`py_compile` 和 `git diff --check` 通过。

2026-07-05 live 5E 已跑完，compact evidence 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_live_20260705_5e_0300/summary_compact.json`。
这轮沿用 5D 已成功的 explicit bridge waypoint：第一段 bridge 仍能规划并 replay 到位，
`available_action_points=150`、`executed_steps=150`、`reached_joint_target=true`，
最终 joint target 误差约 `7.12e-05 rad < 0.02 rad`。随后 probe 在 post-bridge worker
state 上逐个尝试 4 个 follow-up candidates：
`post_bridge_to_approach_pre_f_0p20/0p40/0p60/0p80`。这 4 个候选都能进入
`plan_object_frame_waypoints`，world refresh 也为 `success`，但 cuRobo 都返回
`MotionGenStatus.IK_FAIL`，`successful_candidate_count=0`，所以没有第二段
`trajectory_action_joint_positions` 可执行。

给 PM 的一句话：第一段“把手前桥接点”已经能让 Franka 走到位；但第二段如果只是沿着旧
`approach_pre` 方向往回插值，机器人仍然到不了。下一步要围绕 post-bridge pose 本身系统扫
wrist orientation 和 handle-side translation，先找出第二段可规划、可 replay 的近邻点，再进入
close/grasp、micro-pull 和门角度 metric。当前仍不能宣布 stable grasp、micro-pull、
door opened、`Expert Oracle Score` 或 score。

2026-07-05 Task 5F **post-bridge pose-centered continuation sweep** 已完成 live
evidence，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json`，
实施计划是
`docs/superpowers/plans/2026-07-05-eos2-post-bridge-pose-centered-continuation-sweep.md`。
这轮把 5E 的失败假设改掉：不再沿旧 `approach_pre` 方向大步插值，而是围绕已证明可到达的
post-bridge pose 做小半径候选扫描。第一段 bridge 仍然成功：
`available_action_points=150`、`executed_steps=150`、`reached_joint_target=true`，
最终 joint target 误差约 `8.01e-05 rad < 0.02 rad`。

第二段出现了关键突破：12 个候选里，前 4 个局部 slerp / Y / X 方向仍是
`MotionGenStatus.IK_FAIL`，第 5 个 `post_bridge_local_z_m006_q_bridge` 成功。这个候选只是在
handle object-frame 里把 bridge pose 的 z 方向下移 `0.006m`，保持 bridge quaternion 不变；
cuRobo 生成 33 个 action-level points，probe replay 33 步，
`post_replay_replan.execution.reached_joint_target=true`，最终 joint target 误差约
`6.79e-05 rad < 0.02 rad`。

给 PM 的一句话：我们终于找到“从桥接点继续走一小步”的可执行第二段了。这还不是抓住把手、
拉门或算分，但说明不是只能停在 bridge；下一步 5G 应把这条 `-6mm local Z` continuation
固定成前置段，然后仿 EBench microwave 的 `custom_motion` 思路，把 close/grasp/pending 与移动
分开验证：先闭爪保持，再检查接触/retention，再做 micro-pull。当前仍不能宣布 stable grasp、
micro-pull、door opened、`Expert Oracle Score` 或 score。

2026-07-05 Task 5G **post-replay close-hold staging** 已完成 code checkpoint，机器可读
manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_code_checkpoint_20260705.json`。
GenManip probe 新增 `--planner-trajectory-post-replay-close-hold-steps`：它不会把闭爪混进
planner candidate 里，而是在 bridge replay 和 5F continuation 都执行完成后，读取当前 arm
joint 状态，保持 7 个 arm joints 不动，只把两个 Franka finger joints 命令到 `close_width_m`
并 pending 若干步。这个设计对齐 EBench microwave 的 `custom_motion`：waypoint 负责移动，
`pending grasp` 负责闭爪等待。

给 PM 的一句话：5G code checkpoint 说明“走到把手附近”和“闭爪保持”已经在工程上拆开了。
现在代码能单独跑 close-hold 这一段并写出 `post_replay_close_hold` 证据字段；下一步才是
live 5G，先检查真实 Isaac 里 finger command/readback，再进入单独的接触/retention 阶段。当前
仍不能宣布 stable grasp、micro-pull、door opened、`Expert Oracle Score` 或 score。

2026-07-05 Task 5G live evidence 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_live_20260705_5g_0500/summary_compact.json`。
这轮复用 5F 的成功路线，不再改 bridge 或 continuation：第一段 bridge replay 148 步，
最终 joint target 误差约 `8.36e-05 rad < 0.02 rad`；第二段仍选择
`post_bridge_local_z_m006_q_bridge`，replay 31 步，误差约 `8.07e-05 rad < 0.02 rad`。
随后 close-hold 执行 15 步，arm 误差约 `8.43e-05 rad < 0.02 rad`，finger width readback
从约 `0.03533m` 收到约 `0.01280m`，目标 `close_width_m=0.010m`。

给 PM 的一句话：现在已经不是只会“走到把手附近”，而是能在真实 Isaac 里继续发闭爪保持命令，
并从标准 `state.gripper` 读回手指宽度变化。但这仍只是 close command/readback，不等于抓住
把手；下一步必须加 contact/retention 证据，只有左右手指和 handle 的接触保持成立后，才进入
micro-pull 和门角度 metric。当前仍不能宣布 stable grasp、micro-pull、door opened、
`Expert Oracle Score` 或 score。

2026-07-05 Task 5H **post-replay contact-retention instrumentation** 已完成 code checkpoint，
机器可读 manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json`。
这一步没有改变 5F/5G 的运动路线，也没有提前做 micro-pull；它只把 close-hold 每一步的
`post_close_contact_frame` 和 summary 级 `post_replay_close_hold.retention_summary` 写出来。
通俗讲，5G 回答“手指能不能闭上并读回”，5H 开始回答“闭上的手指是不是在 handle 两侧形成了
可持续接触证据”。验证范围是 code checkpoint：focused tests `4 passed in 0.25s`，probe/test
`py_compile` exit 0，GenManip diff check exit 0。

给 PM 的一句话：我们已经把“闭爪动作”和“是否真的夹到把手”的证据层拆开了。现在代码能记录
左右 finger 与 handle 的 AABB near/overlap、finger width readback、以及可选的 PhysX
required-role contact 统计。这个 checkpoint 本身仍不能说 stable grasp、micro-pull ready、
door opened、`Expert Oracle Score` 或 score；后续 live 5H 结果见下一段。

2026-07-05 Task 5H live evidence 已补两轮。第一轮
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_live_20260705_5h_0430/summary_compact.json`
证明了一个环境前提：只开 `LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1` 不够，必须同时在 server 侧开
`LABUTOPIA_ORACLE_DEBUG_OBS=1`，否则 obs 里没有 `evaluator_last_action_application_debug/contact_debug`，
`post_close_contact_frame` 只能报 `missing_action_application_debug`。第二轮
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_debugobs_live_20260705_5h_0440/summary_compact.json`
按正确环境重跑，contact telemetry 已可用：`tail_physx_contact_status_counts.available=15`。动作层面仍通过：
close-hold 15 步、`reached_joint_target=true`、final joint target 误差约 `8.27e-05 rad`、最后 finger width
约 `0.01280m`。但 grasp retention 没过：`retention_pass=false`、
`tail_bilateral_overlap_pass=false`、`tail_physx_required_roles_contact_records=0`，最后一帧
`OUTSIDE_PRE_CLOSE_CONTACT_FRAME`，左右 finger 都没有 near/overlap handle，最大 required-role axis gap
约 `[0.1353, 0.0692, 0.0]m`。

2026-07-05 Task 5I live sweep 已补 10 组 contact-frame / micro-correction 证据：
`5i_0610` 是 missing-submit negative control；`5i_0620` 的 `cf_right_050` 半量 gap 校正
是 `IK_FAIL`；`5i_0630` 的约 1cm/8mm coarse micro candidate 仍 `IK_FAIL`；`5i_0640`
复现 baseline `post_bridge_local_z_m006_q_bridge`，证明 5I harness 能正常规划、执行、闭爪，
但 retention 仍失败；`5i_0650` 的 mixed-direction 5mm 候选可达但只降低 world X gap、恶化
world Y gap；坐标复核后，correct-direction 的 `Y+5mm`、`X-5mm`、`X-5mm/Y+5mm` 和
`X-2mm/Y+2mm` 均 `IK_FAIL`；单轴 `Y+2mm` 与 `X-2mm` 可达但仍无 required-role near/overlap
或 PhysX contact。

给 PM 的一句话：现在不是“闭爪没发出去”，也不是“server 没采到 contact”，而是“手指能闭上，
但 fixed wrist pose 下只允许很小的单轴挪动；一旦按正确方向同时对准把手两侧，IK 就过不去”。所以下一步不能直接
micro-pull，也不能算 `Expert Oracle Score`；要把 5I 从纯 translation sweep 升级成
orientation-aware / approach-seed / staged correction：先找到一个能同时降低 X/Y gap 且可规划的 wrist
orientation 或分段接近策略，再要求左右 finger 在 tail window 内同时 near/overlap handle；如果
`retention_requires_physx_contact=true`，还必须看到 required-role PhysX contact 通过。当前 raw
`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY` 只表示诊断 motion/readback 跑完，不表示
grasp 或 task success；最后 finger width 读回也只能说明最终闭爪动作到位，不能说明 tail window 已抓住。

2026-07-05 Task 5J 已落候选 manifest：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_staged_correction_20260705_5j_candidates.json`。
原 manifest 把下一步从“继续盲扫平移”改成“先小角度改变 wrist orientation，再评估已知单轴 2mm corridor”。
当前 5J-F 后的产品口径：orientation-only 六条已经跑完，Z+2deg 只是 staged-combination review 线索，
不是已经决定执行组合 translation。只有后续单候选 live run 证明
post-replay replan 成功、close-hold 执行、tail window 内 bilateral near/overlap 和 required-role
PhysX contact 通过，才允许进入 micro-pull。

2026-07-05 Task 5J-A 首个 live candidate 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02/summary_compact.json`。
这轮 `ori_y_m02_z_m006` 的 submit/probe exit code 都是 `0`，不是环境或 IK 卡住：bridge replay
跑 150 步，post-replay candidate 跑 42 步，close-hold 跑 15 步，三段都达到 joint target，最终误差
约 `7.12e-05 rad`，小于 `0.02 rad` 容差。失败点在接触保持：tail window 内左右 finger 的
bilateral overlap、required-role near 和 required-role PhysX contact 都是 `0`，contact semantics
15/15 是 `AABB_OUTSIDE_CONTACT_FRAME`。注意这不是相对 bridge waypoint 完全不平移：`ori_y_m02_z_m006`
沿用 `z_m006` continuation，相对 bridge waypoint 的 object-frame z 位移是 `-0.006m`，Y-2deg 是相对该基线的
orientation delta。给 PM 的通俗解释：这次证明“沿已知小位移路线再换一个小角度，机器人手能走到并闭上”，
但还没闭到把手两侧，所以不能算抓住，更不能算开门或得分。下一步按 5J rule 试同轴反号和 x/z
orientation delta 候选；只有出现能同时缩小 X/Y gap 的方向，才和已知单轴 2mm corridor 组合。

2026-07-05 Task 5J-B 同轴反号 live candidate 也已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0810_ori_y_p02/summary_compact.json`。
这轮把 5J-A 的 Y-2deg 改成 Y+2deg，其它仍沿用 `z_m006` continuation。submit/probe exit code
都是 `0`，不是 server 或 submit 问题；bridge replay 仍能执行 151 步并达到 joint target，最终误差约
`7.13e-05 rad`，小于 `0.02 rad` 容差。新的失败点是 post-replay replan：
`successful_candidate_count=0`，`failure_status_counts={"MotionGenStatus.IK_FAIL": 1}`，没有生成
可执行的 action joint trajectory，所以 close-hold 被跳过，retention telemetry 不可用。给 PM 的通俗解释：
同一个轴的小角度不是左右都能用；Y-2deg 能走到但没夹住，Y+2deg 连下一段路径都规划不出来。下一步不把
Y+2deg 和 translation 硬组合，而是继续逐条测试 x/z orientation delta，先找可达方向，再谈 contact tuning。

阶段性 PM 口径：Y 轴两个符号已经给出结论：负号能走但仍偏离把手，正号在当前 post-bridge state /
`z_m006` baseline 下不可达；X 轴也已经由 5J-C/5J-D 覆盖，正负号都没有形成相对所有 required-role
X/Y gaps 的稳定改善。因此 Y/X 都暂不叠 translation，继续验证 z 轴小角度自由度。

2026-07-05 Task 5J-C x 轴负号 live candidate 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0820_ori_x_m02/summary_compact.json`。
这轮 `ori_x_m02_z_m006` 的 submit/probe exit code 都是 `0`，18445 server 已停止。bridge replay
跑 156 步，post-replay candidate 跑 31 步，close-hold 跑 15 步，三段都达到 joint target，说明
X-2deg 不是 IK blocker。失败点仍是 retention：bilateral overlap、required-role near 和 required-role
PhysX contact 都是 `0`，15/15 contact semantics 是 `AABB_OUTSIDE_CONTACT_FRAME`。并且它没有改善 gap：
最后 left/right gaps 约 `[0.1346, 0.0554, 0.0]m` / `[0.0890, 0.0698, 0.0]m`，比 5J-A 的
Y-2deg 样本更大。给 PM 的通俗解释：X-2deg 这条路能走，但走过去后离把手更偏，所以也不该进入
translation 组合；后续 X+2deg 已作为 5J-D 跑完，仍未形成稳定改善。

2026-07-05 Task 5J-D x 轴正号 live candidate 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0830_ori_x_p02/summary_compact.json`。
这轮 `ori_x_p02_z_m006` 的 submit/probe exit code 都是 `0`。18446 server 因当前 shell 环境不保留后台进程，最终改用 foreground exec session 持有，probe 后已停止；这是 harness 运行方式记录，不影响 5J-D 证据结论。
bridge replay 跑 151 步，post-replay candidate 跑 78 步，close-hold 跑 15 步，三段都达到 joint target，说明
X+2deg 也不是 IK blocker。失败点仍是 retention：bilateral overlap、required-role near 和 required-role
PhysX contact 都是 `0`，15/15 contact semantics 是 `AABB_OUTSIDE_CONTACT_FRAME`。最后 gaps 约为
left `[0.1352, 0.0564, 0.0]m` / right `[0.0888, 0.0692, 0.0]m`。给 PM 的通俗解释：X+2deg 这条路也能走，
但仍没把手指带到把手两侧；相对 best-so-far 5J-A，它在所有 required-role X/Y gaps 上仍更差；相对 X-2deg
只让右指略好、左指更差，所以不是相对所有 required-role X/Y gaps 的稳定改善方向。
下一步转测 z 轴小角度。

2026-07-05 Task 5J-E z 轴负号 live candidate 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0840_ori_z_m02/summary_compact.json`。
这轮 `ori_z_m02_z_m006` 的 submit/probe exit code 都是 `0`。18447 server 使用 foreground exec session
持有，probe 后已停止并确认端口释放；8087 是无关既有 server，没有被触碰。bridge replay 跑 150 步并达到
joint target，最终误差约 `7.13e-05 rad`，小于 `0.02 rad` 容差。失败点发生在 post-replay replan：
候选 `ori_z_m02_z_m006` 已被尝试，但 `successful_candidate_count=0`，
`failure_status_counts={"MotionGenStatus.IK_FAIL": 1}`，没有 selected waypoint / action points，所以
close-hold 没有成功的 post-replay action trajectory 可承接，因此被 `no_post_replay_worker_state` 跳过，retention telemetry 不可用。给 PM 的通俗解释：Z-2deg
不是“走过去但没夹住”，而是“桥接段能走，接下来这个小角度姿态 cuRobo 规划不到”；顶层
`waypoint_not_found` 是没有规划成功后自然没有 selected waypoint，不是命令标签漏写。Z+2deg 对照已由
5J-F 完成，见下一段。

2026-07-05 Task 5J-F z 轴正号 live candidate 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0850_ori_z_p02/summary_compact.json`。
这轮 `ori_z_p02_z_m006` 的 submit/probe exit code 都是 `0`。18448 server 使用 foreground exec session
持有，probe 后已停止并确认端口释放。bridge replay 跑 151 步，post-replay candidate 跑 41 步，
close-hold 跑 15 步，三段都达到 joint target，说明 Z+2deg 不是 IK blocker。但 strict retention
仍失败：tail bilateral overlap、required-role near 和 required-role PhysX contact 都是 `0`，
15/15 contact semantics 是 `AABB_OUTSIDE_CONTACT_FRAME`。最后 gaps 约为 left
`[0.1295, 0.0571, 0.0]m` / right `[0.0838, 0.0691, 0.0]m`。给 PM 的通俗解释：Z+2deg
能走，也比 5J-A 略微缩小了左右手指在 world X 方向的距离，但 world Y 方向更差，所以还不是“夹住把手”。
下一步要先评审是否用它搭配已知能补 world Y gap 的单轴 staged correction，而不是直接宣布进入 micro-pull。

2026-07-05 Task 5K staged-combination review 已准备候选 manifest：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json`。
通俗讲，5J-F 的 Z+2deg 让左右手指在 world X 方向都稍微更接近把手，但 world Y 方向更远；5I 的
object-frame X-2mm 单轴 correction 刚好是历史上能补 world Y gap 的方向。因此 5K 先只评审一个最小候选
`x_m002_ori_z_p02`，不做大范围 sweep，也不把它说成已经能抓住。该 review artifact 已被下一段 5K-A
live probe 消费；历史边界仍成立：必须看 close-hold tail window 的 bilateral near/overlap 和
required-role PhysX contact，不能直接进入 micro-pull 或算分。

2026-07-05 Task 5K-A live candidate `x_m002_ori_z_p02` 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`。
这轮结果是 `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`。通俗讲，这条 staged combination 能执行到
close-hold：post-replay replan 成功、selected waypoint 正确、close-hold 15 步也达到 joint target。
但 strict retention 仍失败，双指没有 bilateral overlap / required-role near / required-role PhysX contact，
15/15 tail records 仍在 `AABB_OUTSIDE_CONTACT_FRAME`。相对 5J-F，5K-A 修回了一部分 world Y gap，
但损失了一部分 world X gap；相对 5J-A 则相反。当前仍不能 claim stable grasp、door-open、
Expert Oracle Score 或 score；下一步不能 micro-pull，应先分析更小 staged correction 或改成
contact-frame / handle-frame target generation。

2026-07-05 code checkpoint：上述 attribution 的代码仪表已经补到 GenManip。新的
`CuroboPlanner.last_plan_debug.start_state_collision` 会在
`INVALID_START_STATE_*COLLISION` 时记录 obstacle inventory、planner ignore-list、
robot link/sphere 候选和诊断错误；`object-frame-curobo-pose-ladder` 也新增
`--pose-ladder-planner-ignore-list`，用于下一轮最小 ignore-list 验证。机器可读证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_code_checkpoint_20260705.json`。
这个 checkpoint 只是“诊断仪表已装好并通过单测”，不是新 live Isaac 结果；它已经被后续
Task 4c live classify evidence 消费。归因完成后，下一步不再是继续重跑 attribution，而是进入
Task 4d support-surface clearance audit。
字段语义已按 review 收紧：`diagnostic_available=true` 只表示诊断执行过，
`attribution_available=true` 才表示已定位到具体 world/self attribution；如果只有
`INVALID_START_STATE_WORLD_COLLISION` status 但 `world=[]`，仍不能说已经知道撞了哪个障碍。

2026-07-05 live attribution 结果：Task 4c 已经把 start-state world collision 归因到
具体对象。新版 classify evidence 位于
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_live_classify_20260705_194133/`，
compact 文件是 `pose_ladder_start_state_attribution_compact.json`。12/12 个 bridge
candidate 都仍失败为 `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`，且 attribution
一致指向 `/World/labutopia_level1_poc/obj_table/surface/mesh` 与 robot link `panda_hand`。
随后最小 ignore-list 验证位于
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_ignore_table_surface_20260705_194441/`：
只忽略 table surface mesh 后，第一条 candidate 变为 `IK_FAIL`，第二条
`approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 在 world refresh
下规划成功，`trajectory_point_count=152`。因此 EOS-2 的下一步不是算分，而是正式处理
table/hand start-state clearance 或 table collision modeling；在这个修复前仍不能进入
stable grasp、micro-pull、door opened 或 `Expert Oracle Score`。

2026-07-05 Task 4d 规划更新：不能把 diagnostic ignore-list 当作正式方案。下一步叫
**Support-Surface Clearance Contract Repair**。它先量化 reset 后的 robot base pose、
joint/gripper state、end-effector world pose、table surface mesh AABB、cuRobo colliding
sphere center/radius 和 clearance margin。然后再三选一：如果手真的嵌进桌面，就修
robot reset/base/joint clearance；如果物理上有 clearance 但 cuRobo table mesh/sphere
模型过保守，就修 table collision representation；只有在有独立 clearance 证据时，才允许
把 table surface 做成 planner-only support-surface exclusion，并且不能影响 PhysX 任务碰撞。
在 Task 4d no-extra-ignore bridge 规划通过前，EOS-2 仍停在 pre-score 阶段。

2026-07-05 Task 4d.3 live 结果与 4d.4A frame-aware live 复跑：no-extra-ignore support-surface clearance audit 已跑完，
证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_support_surface_clearance_audit_stage_bbox_envfix_20260704_213347/`，
compact 文件是 `pose_ladder_support_surface_clearance_compact.json`。这次用与旧成功
live 一致的 conda PATH / Isaac CUDA `LD_LIBRARY_PATH` 重跑，submit/probe exit code
均为 `0`，reset 成功，12/12 个 bridge candidate 都进入 cuRobo world-refresh planner。
runtime 通过 `stage_prim_path:/World/labutopia_level1_poc/obj_table/surface/mesh` 读到了
table surface AABB，并给 12/12 个 candidate 写出了 `support_surface_clearance_records`。
旧 compact 中第一条记录写着 table top z 约 `0.773m`、`panda_hand` sphere bottom z
约 `0.051m`、`clearance_margin_m=-0.722m`；这个数值仍能说明“旧诊断链路确实抓到了
table surface / `panda_hand` 这组 blocker”，但现在不能再把它解释成物理世界里的真实
Z clearance，因为 table AABB 是 USD world frame，sphere 来自 cuRobo planner/reference
frame。GenManip 已补代码 checkpoint：`_sphere_geometry_record_from_query_spheres` 改为输出
`sphere_center_planner_frame` / `sphere_frame=planner_reference_frame`，support-surface
clearance builder 在 sphere frame 和 AABB frame 不一致时输出
`clearance_status=unverified_frame_mismatch`，并禁止 planner-only support-surface exclusion；
随后又补了 world AABB -> planner/reference frame 的转换合同。
已验证：

```bash
/usr/bin/python -m pytest -q tests/labutopia_poc/test_curobo_start_state_collision_diagnostics.py
# 2 passed

/usr/bin/python -m pytest -q tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# 20 passed

/usr/bin/python -m py_compile genmanip/utils/planner/curobo/base.py genmanip/core/evaluator/object_frame_waypoint_planner.py tests/labutopia_poc/test_curobo_start_state_collision_diagnostics.py tests/labutopia_poc/test_plan_object_frame_waypoints_route_contract.py
# exit 0
```

Task 4d.4A frame-aware live 复跑的证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_support_surface_frameaware_clearance_audit_20260704_221731/`，
compact 文件是 `pose_ladder_support_surface_frameaware_compact.json`。这次 submit/probe exit
code 均为 `0`，12/12 条 support-surface records 都是 `planner_reference_frame` vs
`planner_reference_frame` 的 `measured_same_frame`，`clearance_margin_m` 统一约
`-0.011760663m`，blocker 统一是 `sphere_vertically_intersects_support_surface`，planner-only
exclusion allowed count 为 `0`。因此当前不能走 planner-only table support-surface exclusion；
Task 4d.4B 随后用 base z +0.02m 做隔离验证：
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_base_z_lift_002_20260704_223919/pose_ladder_base_z_lift_002_compact.json`。
它把 start-state collision 变成 `0`，并让第二个 bridge candidate 在 world refresh 下规划出
152 个点。Task 4d.4C 又复跑了 observed-base 版本：
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_base_z_lift_002_observed_base_20260704_225244/pose_ladder_base_z_lift_002_observed_base_compact.json`，
明确记录 robot prim `/World/labutopia_level1_poc/franka` 的 observed base z 是
`0.730000019m`。Task 4d.4D 又做了两个 branch 对照：`reset_seed_retract_001` 证明
9D `default_joint_positions` 分支虽然让 arm seed 进入 reset，但仍 12/12 start-state collision；
`base_z_lift_002_only` 证明只改 base z、不带 solver/self-collision override 也能把
start-state collision 清到 `0`，第二个 bridge candidate 仍有 152 个 trajectory points。
Task 4d.4E 已把 `position: [-0.4, 0.0, 0.73]` 固化进正式 `level1_open_door.yml`；
table collision representation 保留为后续审计项，但当前不走 exact ignore table。
stable grasp、micro-pull、door opened、Expert Oracle Score、policy score 和 official score
仍然不能汇报。

## 2026-07-04 历史状态更新（已被 bridge evidence 推进）

EOS-2xC6 live witness 已经把问题边界收窄到 `PhysX contact` 层：6/6 candidate
`submit=0` / `probe=0`，6/6 `PhysX contact` channel available；其中 5/6 row 的
post-close tail 已经出现 AABB bilateral overlap，但 0/6 row 有 required-role
finger-handle `PhysX contact` records。因此当前不能说 stable grasp、micro-pull、
door opened、`Expert Oracle Score` 或 policy score 已通过。

给 PM 的通俗解释：现在不是“手完全没到”，而是“debug 盒子看起来像夹住了，但物理引擎没有
承认左右两根手指真的同时碰到把手”。当时下一步不是直接拉门或算分，而是做
**EOS-2xC7 PhysX Contact Generation / Collider Attribution Repair**。C7-A 第一轮是只读
归因，不改 `contact_offset`、`rest_offset`、collision filters、kinematic flags 或任务语义；
它只检查 contact report 是否挂在正确 prim、真实 handle collider 是否被识别、
collision filter / kinematic 设置是否屏蔽接触，以及 contact offset / rest offset 当前读数。

C7 文档入口：

```text
docs/superpowers/specs/2026-07-04-eos2xc7-physx-contact-generation-collider-attribution-design.md
docs/superpowers/plans/2026-07-04-eos2xc7-physx-contact-generation-collider-attribution-repair.md
```

2026-07-04 C7-A code/unit checkpoint：GenManip 已完成第一层只读 attribution telemetry，
包括 `PhysX contact` header attribution、verified target collider owner path matching、
unmatched required-role contact pair reporting、AABB selected robot/target pair attribution，
以及 pre-step contact-report setup attribution 保留到 debug obs。对应单测已通过：
`test_labutopia_oracle_debug_state.py=25 passed`、
`test_evaluator_ee_pose_action.py=22 passed`、
`test_online_open_door_oracle_probe.py=233 passed`，相关文件 `py_compile` 通过。通俗讲，
现在下一次 live run 不会只告诉我们“没有双指 contact”，而会告诉我们 contact report
挂在哪、PhysX header 里到底有哪些 pair、哪些 pair 被归为 unmatched、AABB overlap
选中的到底是哪两个 collider。边界仍然不变：这还不是 live witness，不是 micro-pull，
也不是 Expert Oracle Score。

2026-07-04 review 后补充：这里的“只读”指不改物理实验条件，不改 `contact_offset`、
`rest_offset`、collision filters、kinematic flags 或 task semantics。为了让 PhysX 把
contact report 发出来，runtime 仍需要挂 `PhysxContactReportAPI` 这种观察仪表；C7-A
只记录这个观察仪表挂到了哪里，不把它当作修复。另一个已修正的细节是 AABB handle
识别：`/handle` 这个独立 path segment 或 target uid 结尾 `_handle` 才算把手；
`handle_support`、`handle_visual` 这类支撑件/外观件不能再被误当成把手接触证据。

2026-07-04 C7-A candidate queue checkpoint：下一轮 live witness 的 6 行候选已经写入
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_candidates.tsv`
并完成字段/源目录校验。它包含 `w024` 和 `w028` 两个 C6 baseline，各自跑
attachment audit、collider owner audit、filter/offset readout。所有行都锁定
`micro_pull_allowed=false`、`score_claim_allowed=false`、`physics_intervention_allowed=false`。
边界：这仍只是 run queue，不是 live result；LabUtopia-local C6 analysis manifest 当前缺失，
所以 TSV 显式记录 `source_manifest_present=false`，后续发布 C7 live evidence 前要么补齐
C6 manifest，要么在 C7 analysis JSON 中保留 GenManip-local source paths。

2026-07-04 C7-A first live witness checkpoint：第一条候选
`eos2xc7_w024_base_attachment_audit` 已用 fresh
`run_id=labutopia_eos2xc7_physx_contact_generation_collider_attribution_eos2xc7_w024_base_attachment_audit_20260704_223000_eos2xc7`
跑通 submit / probe，`submit_exit=0`、`probe_exit=0`、trace 有 297 行，`PhysX contact`
debug channel 状态为 `available`。但这条 run 没进入 `grasp_hold`，而是在更早的
`approach_near` 硬门失败：`stage_not_reached:max_steps_exhausted`，
`min_actual_distance_m=0.03453716465463178`、`final_actual_distance_m=0.03913976102212624`、
`max_command_actual_gap_m=0.01619371223682052`。因为 `grasp_hold` tail sample count 为 0，
所以 `contact_pair_count=0` 不能解释成 handle collider 不能生成接触；它只说明本次没有进入
可用于判断接触生成的窗口。所有 claim guard 仍为 false：不能说 stable grasp、micro-pull、
door opened、Expert Oracle Score 或 policy score 已通过。

PM 口径：第一条 live run 的价值是证明“诊断链路跑起来了，而且没有误报成功”；它同时告诉
我们“问题比接触归因更早，手还没稳定到达接近把手的位置”。当时下一步不要直接改物理参数，也不要
盲跑剩余 5 行，而是先跑一个 bounded read-only readback：

```text
--probe-mode controller-readback-comparator
--controller-readback-waypoint-label approach_near
--open-width-m 0.024
--close-width-m 0.010
```

这个诊断只回答“controller 命令位姿和实际手爪 readback 为什么没收敛”，仍不允许
`contact_offset`、`rest_offset`、collision filters、kinematic flags、micro-pull 或 score claim。

2026-07-04 C7-A bounded readback checkpoint：已按上面的只读参数追加
`approach_near` comparator，证据目录为
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_near_readback_20260704_124339/`。
本次 `submit_exit=0`、`probe_exit=0`，但 summary 状态是
`FAIL_CONTROLLER_READBACK_COMPARATOR_NO_IK_TARGET`，blockers 为
`missing_successful_ee_pose_ik_debug` 和 `ee_pose_target_position_error_exceeds_tolerance`。
它只执行 1 step，目标点是 `target_world=[0.44979134324235837, 0.24876333628991587, 1.1085916790181332]`，
实际 post EE position 是 `[0.3892921805381775, 0.004671737086027861, 0.45819777250289917]`，
`ee_pose_target_position_error_m=0.5245884806528617`。

PM 口径：当时又往前定位了一层。不是“手到了把手但 PhysX 不认接触”，而是
`approach_near` 这一步还没把手送到正确位置；并且 comparator 没拿到 successful IK target。
这意味着当时下一步优先检查 approach target / IK / readback 链路，不该继续讨论 handle collider
或 contact offset。具体当时需先确认 `NO_IK_TARGET` 是目标不可达/坐标系错，还是诊断工具
没有暴露 IK debug；在这个判断完成前，仍不能进入 micro-pull、score 或 C7-B physics edits。

2026-07-04 C7-A `approach_pre` comparator baseline：为判断上一条 `NO_IK_TARGET` 是否只是
诊断工具缺少 IK debug，我们补跑了更早的 `approach_pre` waypoint。证据目录为
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_readback_20260704_125312/`。
本次 `submit_exit=0`、`probe_exit=0`、`trace_lines=2`。结果不是 PASS，而是
`FAIL_CONTROLLER_READBACK_COMPARATOR_DIAGNOSTIC_ONLY`，blockers 为
`ee_pose_terminal_without_post_obs`、`ee_pose_arm_state_jump_too_large`、
`joint_position_terminal_without_post_obs` 和 `joint_position_arm_state_jump_too_large`。
关键区别是：`parse_only_ik_success=true`、`action_source=ik_solution`，说明 comparator
能看到 successful IK；但这个 IK target 相对当前关节姿态跨度太大，
`ik_joint_delta_abs_max=2.0215107798576355`，单步执行后 `panda_joint4` 跳变约
`1.6464000940322876 rad`，超过 `1.0 rad` guard，所以还没拿到 post observation 就终止。

PM 口径：`approach_pre` 像是“上一站能导航，但一步跨太远会触发安全保护”。因此当时下一步不是
改门、改 collider 或改 physics，而是做 `bounded-joint-lead-in`：把同一个 IK target 拆成更小
关节步长，验证 robot controller 能否稳稳到达 `approach_pre`。只有这条链路能稳定执行后，
才继续查 `approach_near` 和后面的 contact attribution。

2026-07-04 C7-A bounded joint lead-in 结果：已按上面的方向补跑
`approach_pre` 的分步 joint replay，证据目录为
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_bounded_lead_in_20260704_130833/`。
本次 `submit_exit=0`、`probe_exit=0`、`trace_lines=56`，但状态仍是
`FAIL_BOUNDED_JOINT_LEAD_IN_DIAGNOSTIC_ONLY`。关键事实是：命令侧每步 target delta
没有超过 `0.05 rad`，但真实 readback 在 step 52、53、54 开始超过 `0.1 rad` 阈值，最后
`panda_joint6` 单步跳变约 `1.3864498138427734 rad`，触发 `arm_state_jump_too_large`。
最终距离 IK target 仍有 `0.6525141596794128 rad`，未达到 `0.02 rad` tolerance。

多角度审阅结论：这不支持回到 contact/collider C7-A 剩余行。当时问题仍在接触之前：
`approach_pre` 还不能被稳定到达和保持。当时下一步先做 target-frame / reachability /
late-step controller timeline 审计，重点看 steps 48-54 的 pre/target/post joint、
handle clearance、drive gain 和姿态/碰撞关系；随后把 oracle 迁移到更接近 EBench microwave
的方式：object-frame manual waypoints + per-waypoint cuRobo planning，而不是 replay 单个
absolute IK target。完整 `collision-aware planning` 说法必须等实现中显式 refresh / log
cuRobo world obstacles 后再使用。

2026-07-04 target-frame / reachability audit 结果：已把上述审计固化到
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_target_frame_reachability_audit_20260704_132909/`。
结论是：当前 audited path 没有证据支持 robot base frame 是主因，task config、probe
默认值和 live summary 都是 `[-0.4, 0.0, 0.71]`，关键 waypoint 的 robot-frame target
也符合 `target_world - robot_base_world_xyz`。这不排除后续 object-frame convention 仍需
单独校验。真正需要调整的是 oracle 形态：DryingBox 现在仍在
验证一个 fixed absolute IK target 或它的分步 replay；而 EBench microwave 的 expert 是
`object_frame` waypoint + `custom_motion` + cuRobo per-waypoint planning。所以当时下一步应先
定义 DryingBox object-frame waypoint contract，再实现 per-waypoint planner path；在能形成
有效 `grasp_hold` 窗口前，不继续消耗 C7 contact/collider 剩余行。实现时必须显式记录
cuRobo world obstacle refresh，之后才允许把它升级表述为 full collision-aware planning。

PM 口径：不是“EBench 里算专家轨迹特别玄学”，而是我们不能把 LabUtopia 的开门 controller
轨迹原样塞到 EBench。EBench 自己的 microwave 也是先写 task-level manual
`custom_motion` 关键动作点，其中包括 `object_frame` 目标和 `robot_frame` staging，再让
cuRobo 在当前机器人和场景里现算能走的关节轨迹。DryingBox 后续也要按这个范式做，才能避免
一直调单个 IK 点。

给产品和实习生的展开版：EBench 的 `mobile_manip/microwave` 不是拿一条固定 joint
trajectory 当“标准答案”直接播放。它在
EOS 当前 registry 指向的
`configs/tasks/ebench/mobile_manip/test_mini/microwave.yml` 里先写一串
`custom_motion` 关键点；GenManip 的 `test`、`test_mini`、`val_train`、`val_unseen`
microwave 配置共享同一类 manual 模板。开门阶段既有相对 `microwave` 的 `object_frame`
坐标，例如先到把手前、贴近把手、夹住、再拉开，也有 `robot_frame` staging。运行时
`custom_motion.py` 会把这些 task-level targets 转换成 world/robot pose，再调用
`BaseEmbodiment.plan_pose` 和 cuRobo `MotionGen.plan_single` 现场算出机器人 joint
trajectory。最后 EBench metric 读 `microwave` articulation qpos 和物体关系来给分，
所以 DryingBox 也需要先证明“相对把手的关键点能被当前 runtime 现算出来”，不能直接假设
LabUtopia 的 controller 轨迹 replay 到 EBench 就是满分。

同时要避免一个误解：GenManip 资产库的 `assets/objects/articulation_data.json` 中，部分
`microwave` articulated asset 自带 `skills.open_door.skill_trajectory` 元数据。但本轮审计到的
`microwave.yml` manual demonstration 执行链没有直接读取这些 asset-level
`skill_trajectory` 来通关。我们参考 EBench microwave 时，参考的是 task-level
`custom_motion` 关键点 + runtime cuRobo 重新规划 + metric readback，而不是把资产元数据里的
轨迹文件当作标准答案播放。

2026-07-05 工程 checkpoint：`object-frame-curobo-pose-ladder` 已扩展为 reset/readback
aware。新增能力包括：

```text
--pose-ladder-offset-y-m
--pose-ladder-offset-z-m
--pose-ladder-include-reset-pose-basis
pose_ladder_reset_debug_excerpt
```

含义是：live probe 会先 reset，读取 handle orientation、当前 EE/wrist orientation
和 native controller approach orientation，把它们转成 handle `object_frame` 后再扫
X/Y/Z 小范围候选。这个阶段的目标只有一个：找到第一个 IK-solvable `approach_pre`
或 reset-to-handle bridge。

2026-07-05 live bridge ladder 结果：证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_bridge_ladder_20260704_181425/`。
no-refresh ladder 找到了第一个 bridge 可规划点
`approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity`，
`trajectory_point_count=152`。这说明“从 reset 到把手之间完全没有中间可达点”这个假设已经被排除。
但 world-refresh retry2 中 reset 成功，12 个候选的 `world_refresh_status` 都是 `success`，
规划仍全部失败，统一状态是 `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`。
所以现在不能进入 `grasp_hold`、micro-pull、Expert Oracle Score 或 full collision-aware planning
口径；这一步后续已经由 Task 4c live classify evidence 和 Task 4d.3 clearance audit
推进。最新 frame 复核确认旧 live 结果里的 table AABB 和 `panda_hand` sphere 不在同一个
frame，不能把旧 `clearance_margin_m` 直接解释成物理高度差。当前路线调整为 Task 4d.4A
frame-aware support-surface clearance audit：先做同 frame 诊断，再决定是否修
reset/base/joint/bridge clearance。
不是因为“轨迹文件播完了”就给分。DryingBox 因此也应该把 expert 定义成“相对原生
DryingBox handle/door 的关键点 + runtime planner + metric readback”，而不是移植
LabUtopia 里某次 controller 生成的绝对轨迹。

下一阶段实施计划：

```text
docs/superpowers/plans/2026-07-04-dryingbox-object-frame-curobo-oracle.md
```

2026-07-04 DryingBox object-frame oracle Task 1-4a checkpoint：GenManip 已补上
`build_dryingbox_object_frame_waypoints` 纯合同、`DryingBoxObjectFrameWaypoint`
dataclass、`build_waypoint_planning_record` claim guard，以及
`--probe-mode object-frame-curobo-planner-smoke` 的 client-side planner-interface
diagnostic。Task 4a 已补 server/client planner-only 通道：
`EvalServer /plan_object_frame_waypoints` -> `IsaacWorkerPool` -> `IsaacWorker`
-> `IsaacEvalEnvRay` -> `object_frame_waypoint_planner` -> `embodiment.plan_pose()`。
这个通道只做规划诊断，不 reset、不 step、不写 recorder、不调用 post_episode_process，
并把 stable grasp、micro-pull、door opened、Expert Oracle Score、policy score、
official score 和 full collision-aware planning 的 claim guard 继续按证据控制。post-review
又收紧了三点：planner smoke 不消费 pending reset result；runtime side-effect flags
会从 server response 透传并阻断 PASS；`planner.update()` 成功只记为
`planner_world_refresh_observed`，不能直接升级成 `collision_aware_planning`。已跑的验证包括：
`dryingbox_object_frame` 2 passed、`waypoint_planning_record / object-frame planner-smoke`
focused regression 7 passed、support-surface route contract
`test_plan_object_frame_waypoints_route_contract.py` 8 passed、邻近旧
`build_oracle_waypoints` 回归 26 passed，以及相关 `py_compile` exit 0。这一步证明
“按 EBench microwave 范式描述专家意图”和“把 planner-only API seam 接到 runtime”
都有测试保护；这个 checkpoint 当时还不是真实 live planner smoke，因为尚未在
Isaac/cuRobo server 里对 DryingBox scene 跑出三点规划结果。后续 Task 4b live
evidence 结果见下段。

2026-07-04 Task 4b live evidence 更新：真实 Isaac/cuRobo server 已经跑过
`object-frame-curobo-planner-smoke`，证据目录为
`docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_curobo_oracle_debug_20260704_155243`。
这次把问题从“能不能连上 planner”推进到“planner 为什么不给轨迹”：
`reset` 成功，`/plan_object_frame_waypoints` 可调用，`world_refresh_status` 对
approach_pre / approach_near / contact 都是 `success`，并且 endpoint 没有 reset / step /
post_episode_process 副作用。但三个 waypoint 的 `trajectory_point_count` 都是 0。
新补的 planner debug 显示完整 world refresh 下是
`MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`；clean reset 对照显示
`refresh_world=false` 时是 `MotionGenStatus.IK_FAIL`。因此现在还不能进入
`Expert Oracle Score`：我们已经证明“planner 考场能打开”，但尚未证明“专家第一段伸手动作能被
Franka/curobo 规划出来”。当时下一步应先做 pose/orientation ladder 和 start-collision
attribution，再恢复 stable grasp / micro-pull / score 证据。

2026-07-04 Task 4b follow-up：第一轮 `object-frame-curobo-pose-ladder` 已经跑完，
证据目录为
`docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_pose_ladder_20260704_162947/`。
本次 `submit_exitcode=0`、`probe_exitcode=0`，并且 reset-before-plan 被实际观测到；
endpoint 没有 reset / step / post_episode_process 副作用。我们测试了 20 个
`approach_pre` 候选：5 个 X 方向距离 `-0.04/-0.08/-0.12/-0.16/-0.20 m` 乘以 4 个
姿态 `identity/yaw_90/yaw_-90/yaw_180`。所有候选都没有生成 trajectory，
`planner_debug.status=MotionGenStatus.IK_FAIL`。

给 PM 的解释：这不是环境、资产、endpoint 或 cuRobo 没通；它说明第一批“手伸到把手前”的
候选姿态还不是 Franka/curobo 能解出来的姿态。我们这次故意没有 fresh world refresh，
所以不能把结果归因到碰撞，也不能说 collision 已经解决。当时下一步要用 reset/readback 数据
重新扩展 pose basis：把真实 handle pose、当前 EE/wrist orientation、native controller
approach orientation，以及小的 Y/Z clearance offset 加进 ladder。只有先找到至少一个
IK-solvable 的 `approach_pre`，才进入 world refresh / start-collision attribution；
在这之前仍不能汇报 stable grasp、micro-pull、door opened、Expert Oracle Score、
policy score 或 official score。

## 命名和位置

推荐工程名：

```text
Stage 4c: Expert Oracle Score / Score Calibration
```

它位于 Stage 4b consumer smoke 之后、真实 policy score 之前：

```text
4b Consumer Smoke -> 4c Expert Oracle Score -> Semantic Evaluator / Policy Score -> Official Leaderboard
```

这里的 “4c” 不重排现有 6 个 AAN consumer acceptance stages。它表示：Stage 4b 已经证明
任务链路能跑，4c 再校准“标准答案是否能在同一 metric 下得分”。

## 证据层级

| 层级 | 回答的问题 | 当前状态 | 能不能当作模型成绩 |
|---|---|---|---|
| Runtime smoke | 任务链路能不能 reset、step、出图、写 metric？ | 已通过 | 不能 |
| Franka expert oracle | LabUtopia 原生 Franka expert 在 EBench metric 下能不能得分？ | S0 frozen action source ready；S1R-D Route B fresh S1 已在正式 score chain 下产出 `score=1.0` / `success_rate=1.0`；下一步 S2 补 door joint readback、metric input dump 和 render/snapshot | 不能，属于 oracle / 标准答案验证 |
| Lift2 oracle / retarget | 官方 Lift2/R5a 口径下，专家策略或 retarget 后动作能不能完成任务？ | 当前 lower-level official action branch 已由 F2a 关闭；native lane 停在 Gate1V-3 contract incomplete/no-live | 不能，属于 oracle / 上限验证 |
| Real policy score | 真实 baseline / model 输出 action 后能得几分？ | 后续 | 可以作为 policy 质量证据，是否 official 另看运行入口 |

## 为什么要分两步

LabUtopia 桌面 expert 主线是 Franka。EBench official-style Lift2 lane 使用
`manip/lift2/R5a` 和 16D action contract。Franka expert 的轨迹不能直接等价于 Lift2
policy action。

因此 `Expert Oracle Score` 先分成两步：

0. **Evidence freeze**：先锁定 lane、config、asset wrapper、run id 规则和 hash，避免
   把历史 `lift2_candidate`、AAN-11 lane、Franka POC 的证据混用。
1. **Franka native expert under EBench metric**：先验证评分器、任务布局和
   `RevoluteJoint` / object-state metric 是对的。这里用 Franka 是合理的，因为它最接近
   LabUtopia 原生 expert。
2. **Lift2 oracle / retarget**：再把专家意图迁移到 Lift2/R5a 口径，验证官方机器人
   embodiment 也能完成同一任务。

## 子阶段

### EOS-0: Evidence Freeze

目标：冻结本轮 oracle score 到底跑哪条 lane、哪个 config、哪个 asset wrapper，避免
复用旧 smoke 证据。

PASS 硬门：

- 记录 `task_name`、`usd_name`、robot type、action contract、metric config、config SHA；
- AAN-11 lane 必须指向
  `scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene`；
- Franka POC 和 Lift2 candidate 不能共用 action log；
- `run_id` 命名必须包含 `expert_oracle` 或 `lift2_oracle`，不能复用 smoke run id；
- no-local-repair、assets root、AAN wrapper 指向正确 package；
- runtime bootstrap 继续使用 `aan_runtime_environment_bootstrap.md`。

### EOS-1: Metric Parity Preflight

目标：确认 EBench metric 读的是正确任务状态，而不是 LabUtopia controller 的内部
`done`。

首个任务：

```text
task=level1_open_door
native_config=config/level1_open_door.yaml
franka_poc=ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml
lift2_candidate=ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml
metric=check_joint_angle(obj_DryingBox_01, RevoluteJoint, 30-120 deg)
```

PASS 硬门：

- reset 后能读到 `obj_DryingBox_01`；
- metric 读取的是门的 `RevoluteJoint`，不是按钮 `PrismaticJoint`；
- metric 来源是 GenManip / EBench step output；
- 不把 LabUtopia expert controller 的 `done` 直接当 score。当前 LabUtopia open
  controller 的成功条件偏 handle 位移 / gripper 距离，而 EBench metric 是
  `check_joint_angle(obj_DryingBox_01, RevoluteJoint, 30-120 deg)`；
- 记录初始门角、结束门角、metric score、success_rate、result_info 路径。

### EOS-2: Franka Native Expert Oracle / Planner Calibration

目标：在 Franka POC lane 中接入 LabUtopia native expert 意图，让 EBench metric 给
专家答案打分。当前推荐实现不是把一条 fixed joint trajectory 当通关答案，而是优先采用
EBench microwave 同源口径：task-level `custom_motion` waypoints、object-frame /
robot-frame staging、runtime cuRobo planning 和 metric readback。

可接受实现方式：

- 在线运行 LabUtopia scripted expert controller，但 score 只读 EBench metric；
- 将 LabUtopia expert 意图转写为 DryingBox handle/door object-frame waypoints，
  由 runtime planner 现场生成 action，并由 EBench metric 评分；
- 如需对照，可 replay 已记录的 Franka expert action / joint trajectory，但只能作为
  diagnostic baseline，不能替代 planner-calibrated oracle。

PASS 硬门：

- 使用 `franka_poc` 或等价 Franka task config；
- action 来源标记为 `labutopia_native_expert_oracle`，不能伪装成 learned policy；
- EBench metric score 达到任务阈值，例如单 episode `score=1.0` 或 `success_rate=1.0`；
- 产出 `result_info.json`、action log、关键帧 render / video、metric trace；
- 对比 LabUtopia native expert success 和 EBench metric success，并解释任何差异。

允许说法：

```text
Franka expert oracle 在 EBench metric 下能得分，说明评分器和任务布局能识别专家完成状态。
```

禁止说法：

```text
真实 policy 已经会做任务。
Lift2 official baseline 已经成功。
official leaderboard score 已经完成。
```

### EOS-3: Lift2 Oracle / Retarget

目标：把 expert 意图迁移到 Lift2/R5a 口径，证明官方机器人 action contract 下也能完成
任务。

可接受实现方式：

- Franka expert end-effector trajectory -> Lift2 IK / retarget -> 16D R5a action；
- 编写 Lift2-specific scripted oracle，但仍走 EBench / GenManip action接口；
- 分阶段 open-door oracle：approach handle、contact / pull、verify joint angle。

PASS 硬门：

- 使用 `lift2_candidate` 或 AAN-11 Lift2 candidate lane；
- action dialect 是 `-a r5a -g lift2` 或等价 16D Lift2 action client；
- 不使用 LabUtopia Franka joint action 直接冒充 Lift2 action；
- EBench metric score 达到任务阈值；
- 记录 retarget / IK 失败率、collision / reachability、joint limit、step count；
- 产出 result_info、action log、metric trace 和 render / video 证据。

允许说法：

```text
Lift2 oracle / retarget 能在本地 EBench metric 下完成该任务，说明官方机器人口径存在可行专家上限。
```

禁止说法：

```text
训练模型已经达到 oracle 水平。
official leaderboard 已经发布成绩。
任意 LabUtopia 任务都已经可由 Lift2 完成。
```

### EOS-4: Real Policy Handoff

目标：在 oracle 证明 metric 和 embodiment 可完成后，再接真实 baseline / model policy。

PASS 硬门：

- policy 输出标准 EBench action，而不是调用 expert controller；
- run_id、policy checkpoint、task config、result_info、score 和 success_rate 全部记录；
- 与 EOS-2 / EOS-3 的 oracle score 分开汇报。

## 失败归类

| 失败现象 | 归类 | 处理方式 |
|---|---|---|
| Franka expert 在 LabUtopia 内成功，但 EBench metric 不得分 | metric / state mapping 问题 | 检查 prim path、joint name、角度单位、success threshold。 |
| Franka expert 在 EBench lane 中 reach 不到物体 | layout / robot pose 问题 | 对齐 native layout、robot pose、asset scale、camera / table frame。 |
| Lift2 retarget IK 失败 | embodiment retarget 问题 | 检查 reachability、joint limits、base pose、handle contact strategy。 |
| Lift2 oracle 得分，真实 policy 仍 0 分 | policy quality 问题 | 不改资产结论，单独推进 model / policy。 |
| oracle 得分但 render / material 仍有差异 | visual parity follow-up | 不把 oracle score 升级成 visual/material parity。 |

## Evidence Manifest 建议字段

```json
{
  "stage": "expert_oracle_score",
  "substage": "franka_native_expert_replay | lift2_oracle_retarget",
  "evidence_freeze": {
    "task_name": "",
    "usd_name": "",
    "config_sha256": "",
    "asset_wrapper_sha256": "",
    "run_id_policy": "must include expert_oracle or lift2_oracle"
  },
  "status": "PASS | FAIL | BLOCKED | WARN | NOT_RUN",
  "run_id": "example_run_id",
  "task_name": "ebench/labutopia_lab_poc/franka_poc/level1_open_door",
  "robot": "manip/franka/panda_hand | manip/lift2/R5a",
  "oracle_source": "labutopia_native_expert_controller | expert_trajectory_replay | lift2_scripted_oracle | retargeted_expert",
  "policy_claim_allowed": false,
  "official_score_claim_allowed": false,
  "metric_source": "genmanip_ebench_metric_output",
  "metric_target": {
    "object_uid": "obj_DryingBox_01",
    "joint_name": "RevoluteJoint",
    "angle_deg_range": [30, 120]
  },
  "result_info_path": "",
  "score": null,
  "success_rate": null,
  "action_log_path": "",
  "render_or_video_path": "",
  "allowed_claims": [],
  "forbidden_claims": []
}
```

## 推荐推进顺序

1. 先做 `level1_open_door` 的 EOS-1 / EOS-2，因为它已经有 Franka POC 和 Lift2
   candidate 两条 lane，metric 也最明确。
2. 再做 EOS-3，把 open-door oracle 迁移到 Lift2/R5a。
3. EOS-2 / EOS-3 都通过后，再复制到 `level1_pick`、`level1_place`。
4. 最后再接真实 baseline / model policy，单独汇报 policy score。

## Score 状态总览

```text
Expert Oracle Score status=S1R_D_ROUTE_B_FRESH_S1_M1_PASS_S2_M3_READBACK_REVIEW_NEXT
runtime smoke score=0.0 is not an expert failure
Franka expert oracle score=ROUTE_B_BRIDGED_EXPERT_SCORE_1_CANDIDATE_PENDING_READBACK_RENDER_REVIEW
Lift2 official lower-level action branch=F2A_CLOSED_NO_TRUE_NEW_OFFICIAL_ACTION_ABSTRACTION
fallback expert/oracle score route=S1R_A_B_B2_C_D_COMPLETE_ROUTE_B_FRESH_S1_SCORE_CHAIN_PASS
S0 frozen LabUtopia native action source=PASS_905_CONTIGUOUS_9D_ACTIONS_SHA256_e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f
S1 attempt1=BLOCKED_CONFIG_PATH_ALLOWED_DIRECTORY_GUARD_NO_RESET_NO_ACTION
S1 attempt2=PARTIAL_RESULT_INFO_EXISTS_SCORE_0_SR_0_RUNNER_EXIT_1_METRIC_SCORE_EMPTY_ACTION_LOG_1_STEP
S1 live budget=CONSUMED_2_OF_2_PLUS_S1R_D_FRESH_S1_EXECUTED_PASS
S1R-D bridge source=PASS_14_BRIDGE_PLUS_905_FROZEN_ACTIONS_TOTAL_919_SHA256_fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a
S1R-D fresh S1 result=PASS_SCORE_1_SR_1_EXECUTED_578_STEPS_14_BRIDGE_564_NATIVE_EXPERT_METRIC_SCORE_NONEMPTY
Gate1V-2 preflight=HISTORICAL_BLOCKER_SUPERSEDED_BY_S0_FREEZE
Gate1V-2a freeze=CONFIG_FROZEN_HISTORICAL_BLOCKER_SUPERSEDED_BY_RUNNER_AND_S0_FREEZE
Gate1V-2b runner/action-source contract=HISTORICAL_BLOCKER_SUPERSEDED_BY_GATE1V_2C_RUNNER_AND_S0_FREEZE
Gate1V-2c score runner build plan=COMPLETED_CODE_CHECKPOINT_NO_LIVE
Gate1V-2c runner code checkpoint=CODE_READY_RESULT_LOCATOR_REPAIRED_BY_S1R_A
Gate1V-3 native-controller contract=INCOMPLETE_NO_LIVE_RELEASE_NO_FROZEN_DIFFERENT_CONTROL_SURFACE
real policy score=NOT_RUN
next score-eligible milestone=S2-R1B release review after S2-I2 metric producer snapshot repair; no S1 retry
```

2026-07-06 S1 attempt2 后的规划边界：

- S1 attempt2 说明 EBench/GenManip 可以写出 `result_info.json`，但不说明 expert 失败。
- 当前最短路径不是再 live retry，而是 S1R-A/B/C：修 result locator、审计 `metric_score`、归因 step0 invalid state。
- S1R-A result locator zero-live checkpoint 已完成：runner 已支持 `run_specific_base_dir_compat`，并通过 fake-client runner tests `8 passed`。
- attempt2 的 reset-to-first-action 最大关节跳变约 `2.734rad`，所以 step0 invalid state 优先按 reset/action contract mismatch 处理。
- S1R 实施计划见 `docs/superpowers/plans/2026-07-06-eos2-s1r-score-chain-repair.md`。
- S1R-D fresh S1 已通过，只能先说 formal score chain / M1 通过；S2 还要补 readback/render 后再评价 Franka/native expert claim。
- 如果 S2 无法从 fresh evidence 中补足 door joint readback、metric input dump 或 render/snapshot，结论是 S2 evidence gap，不是 S1 retry。
- 如果 S2 在 action scale、dt、reset pose 和 readback 都查完后仍 official zero / invalid，才关闭当前 Franka/native frozen replay route。
- 如果 S3 的 bounded Lift2 mapping families 都失败，才关闭当前 Lift2 retarget route。

## 2026-07-04 EOS-2 Planner Sanity Evidence

Historical DryingBox planner-only evidence before the later Task 5 live replay/contact diagnostics:

```text
handle_offset_ladder_evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_pose_ladder_richer_20260704_173743
handle_offset_ladder_status=BLOCKED_OBJECT_FRAME_CUROBO_POSE_LADDER_NO_IK_SOLVABLE_VARIANT
handle_offset_ladder_variants=600
handle_offset_ladder_planner_debug_status=MotionGenStatus.IK_FAIL for all variants

reset_seed_evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_pose_ladder_reset_seed_20260704_174832
reset_seed_status=PASS_OBJECT_FRAME_CUROBO_POSE_LADDER
reset_seed_first_plannable_variant=approach_pre_reset_ee_pose_as_object_frame
reset_seed_trajectory_point_count=149
runtime_side_effect_reported=false

bridge_ladder_evidence=docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_bridge_ladder_20260704_181425
bridge_ladder_no_refresh_status=PASS_OBJECT_FRAME_CUROBO_BRIDGE_LADDER
bridge_ladder_no_refresh_first_plannable=approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity
bridge_ladder_no_refresh_trajectory_point_count=152
bridge_ladder_world_refresh_retry2_status=BLOCKED_OBJECT_FRAME_CUROBO_BRIDGE_NO_PLANNABLE_STEP
bridge_ladder_world_refresh_retry2_world_refresh=success for all 12 tested candidates
bridge_ladder_world_refresh_retry2_planner_debug_status=MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION for all 12 tested candidates
```

Historical product interpretation: we had proven the planner-only endpoint and the
reset-seed object-frame round-trip sanity are working, because the reset EE pose
seed can be planned. We also have a no-refresh reset-to-handle bridge point that
can plan, so the diagnosis has moved forward from pure IK reachability to
collision-aware planning setup. We have not yet proven that the bridge pose is
valid when cuRobo's world obstacles are active, nor that it creates a stable
grasp. Therefore EOS-2 does not advance to score yet.

Historical product interpretation after Task 5I live evidence: planner replay,
post-replay close-hold, finger readback, and contact telemetry are working. The
then-current blocker was narrower than 5H: the hand closes outside the handle contact
frame, and a pure fixed-quaternion translation correction is not enough. Single-axis
2mm corrections can execute but still fail retention; correct-direction paired
2mm/5mm corrections are `MotionGenStatus.IK_FAIL`. EOS-2 still does not advance to
score. This paragraph is superseded by the 5K-A live status at the top of this
document.

Superseded engineering note: after Task 4d.4E, base z=`0.73m` was promoted into
the formal Franka POC `level1_open_door.yml` reset/base contract, and the next step
was bounded execution/readback. That path has now been consumed by Task 5A-5I.
Task 4c identified the retry2 blocker as table surface mesh versus `panda_hand`,
and Task 4d.4A now records same-frame support-surface clearance live. The new
evidence transforms the table AABB into cuRobo planner/reference frame and compares
it with planner-frame `panda_hand` spheres. All 12 records are `measured_same_frame`
with `clearance_margin_m=-0.011760663122180937`, so an exact planner-only
support-surface exclusion is not justified. Task 4d.4D then proved
`default_joint_positions` alone is insufficient and base-z-only clears the
start-state collision. The post-5I orientation-aware pass produced 5J-A through
5J-F, and the staged-combination review has now been consumed by 5K-A live evidence.
5K-A is reachable and executes close-hold, but remains blocked at contact retention
because both required roles stay outside the contact frame and PhysX required-role
contact records remain `0`. Grasp, micro-pull, door-open readback, Expert Oracle Score,
policy score, and official score remain blocked.

## 2026-07-05 Task 4d.2 Support-Surface Clearance Hook

给产品经理的通俗解释：

> 现在我们已经不只是知道“规划器说撞了桌子”。代码里已经补了一个诊断挂钩：当 cuRobo
> 报 `INVALID_START_STATE_WORLD_COLLISION` 时，planner response 可以把“撞到哪个
> obstacle、机器人哪个 link/sphere、sphere 的 planner/reference frame 坐标和半径、
> 桌面的 runtime AABB”
> 合在一起，并在后续同 frame 审计里算出 sphere 底部离桌面 top 还有多少米。这样下一次 live run 就能回答：
> “机器人是真的插进桌子里了，还是只是规划器把支撑面当成不能碰的障碍挡住了？”

工程含义：

```text
server hook:
  plan_object_frame_waypoints_for_scene 支持 support_surface_uid=table
  由 server 在 Isaac scene 中读取 table.get_world_bounding_box()
  自动生成 support_surface_clearance_records

probe hook:
  online_open_door_oracle_probe.py 新增 --support-surface-* 参数
  object-frame-curobo-pose-ladder 会把这些字段透传给 server
  trace / variant record 会保留 support_surface_clearance_records

当前边界:
  Task 4d.2 是 code+unit-test checkpoint；Task 4d.4A 已补 live frame-aware evidence。
  新增记录 support_surface_aabb_source 与 support_surface_reference_prim_path：
    support_surface_prim_path 是 cuRobo 报出来的具体 obstacle；
    support_surface_reference_prim_path 是拿来读 AABB 的 scene/table 实体；
    support_surface_aabb_source 说明 AABB 来自 payload 还是 scene_uid:table。
  planner-only exclusion 只有在 exact candidate、support-surface AABB 与 sphere 已经同 frame、
  Z 方向 clearance 非负、XY footprint 与 support-surface AABB 有重叠时才可被诊断字段标成 allowed。
  Task 4d.4A live frame-aware audit 已完成：12/12 条记录同为 planner_reference_frame，
  clearance_margin_m 约 -0.011760663m，planner-only exclusion allowed count 为 0。
  Task 4d.4D 已继续证明 default_joint_positions 分支不足，而 base z=0.73m only 分支
  清掉 start-state collision；base-z-only 已固化为 POC-specific reset/base contract，并已被
  后续 Task 5A-5I 的 planner trajectory / readback / close-hold / contact-retention / contact-frame
  sweep 消费。随后 5J orientation-aware 线索也已被 5K-A live candidate 消费，5K-A 又被
  5L/5M 消费。当时 blocker 是 5M state-reference rerun 的 centerline candidate generation：
  route-bound bridge replay 正常，旧 `NoneType` 输入 bug 已越过，但 bilateral contact-frame
  solver 因 `PAD_DEPTH_MISS` 没有生成 numeric candidate。下一步应先做 candidate-only
  tolerance / padding preflight，让 `candidate_count>0` 后再重跑完整 planner live；仍不能进入
  grasp、micro-pull、door-open readback 或 Expert Oracle Score。
```

# LabUtopia AAN Consumer Handoff

Date: 2026-07-01

## 当前结论

ConvertAsset 的 `Asset Application Normalizer` 已经产出 DryingBox 的 AAN-ready
package。LabUtopia / GenManip consumer 已经把它接入 `level1_open_door` 并通过本地
Stage 4b live smoke。2026-07-02 更新：AAN-11 新包也已经进入 LabUtopia / EBench
consumer 并完成 fresh rerun，`run_id=labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803`，
submit / eval 都是 exit `0`，reset 后跑满 1000 steps，并产出 `result_info.json`。
下一步不再手工修 USD / MDL；先按 runtime bootstrap runbook 统一 conda、
`CUROBO_SRC`、assets root、preflight 和 evidence 字段，再推进 no-local-repair、
semantic evaluator 和 material parity。
runtime bootstrap 的标准环境、preflight、failure classification 和 evidence 字段已固化在
[`aan_runtime_environment_bootstrap.md`](aan_runtime_environment_bootstrap.md)。
分数校准的下一层规划已固化在
[`expert_oracle_score_plan.md`](expert_oracle_score_plan.md)：它把当前 `score=0.0`
的 consumer smoke、Franka expert oracle、Lift2 oracle / retarget 和真实 policy score
分开，避免把“链路能跑”误解成“专家或模型失败”。

> **当前唯一 canonical 主线（2026-07-07）：** S0 frozen expert action source 已完成；S1/M1 formal score-chain 已通过，Route B fresh S1 得到 `score=1.0` / `success_rate=1.0`。S2-L1 先暴露 terminal readback/render 证据缺口，S2-L1R 又先后暴露 `curobo` import、Ray socket path、CUDA runtime / `ninja` 环境合约问题；这些都不是 expert route 失败。最新 S2-R1E full-env repaired replacement replay 已跑通：run id `eos2_s2_l1r_full_env_repaired_route_b_readback_render_20260707_003`，official `score=1.0` / `success_rate=1.0` / `metric_score=[[[1.0]]]`，最终 DryingBox `RevoluteJoint=41.715865deg`，在 EBench `CheckJointAngle` 的 `[30,120]deg` 范围内，`metric_input.within_range=true`，`succ_cnts=59`，terminal camera artifact 和 canonical `camera2.mp4` 都存在。因此 M3 single-episode Expert Oracle Score 的 score/readback evidence 已可签收；下一步不释放 S2-L2、不重跑 S1，转入 M4/S4 small-sample robustness 或 S3 Lift2 oracle/retarget。2026-07-07 又补了 review-only `tabletop_camera` / `front_camera` / `side_camera` reset smoke 和 full replay MP4：`eos2_review_camera_full_replay_20260707_111621` 已产出四路视频，三路产品复盘相机视觉审阅 PASS；它们不改变 `camera2` scoring/readback 口径，且 `score_claim_allowed=false`。视觉材质 parity、policy score、official leaderboard 仍是 blocked/follow-up。下方 Gate / Lift2 / E2R / F-stage 内容是历史或并行分支记录，不能覆盖这条当前主线。

2026-07-06 stop-go 总控规划已新增：
`docs/superpowers/plans/2026-07-06-eos2-expert-oracle-stop-go-roadmap.md`，证据 manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_stop_go_roadmap_20260706.json`。
给产品经理的当前口径：接下来不是继续试到开门，而是按 M1-M4 阶段门推进。M1 已经通过：Route B fresh S1
在正式 EBench score chain 下产出 `score=1.0` / `success_rate=1.0`。2026-07-07 的 S2-R1E full-env
repaired replacement replay 进一步把 M3 的 official score、door joint readback、metric input dump 和
render artifact 互相对齐：`score=1.0`，终态门角 `41.715865deg`，`succ_cnts=59`，`camera2.mp4`
存在。因此 single-episode Expert Oracle Score POC 的 score/readback evidence 已经弄好。M4 才是小样本稳定；
M4 之前不能说可交付扩展。F2a 关闭的是当前 F-stage lower-level official/OpenPI action 分支，
不是 LabUtopia-to-EBench 项目失败，也不是 `Expert Oracle Score` 失败。

2026-07-07 review camera reset smoke 和 full replay 也已登记：
`docs/labutopia_lab_poc/evidence_manifests/eos2_review_camera_reset_smoke_20260707_104047.json` 和
`docs/labutopia_lab_poc/evidence_manifests/eos2_review_camera_full_replay_20260707_111621.json`。给产品经理的白话解释是：
之前大家觉得视频“像倒过来”，核心原因不是任务倒了，而是原 `camera2` 是评分/debug 相机，画面被大平面遮挡、
角度也不面向产品展示。现在新增了三路只用于 review 的相机：`tabletop_camera` 看桌面布局，`front_camera`
看门、handle、控制面板和观察窗，`side_camera` 看机械臂与箱子的相对位置。三张 reset PNG 已经通过独立视觉
review；随后 full replay 又导出了四路 MP4，每路 `579` frames / `19.3s`。独立视觉 review 给
`tabletop_camera`、`front_camera`、`side_camera` 均为 PASS，`camera2` 仍为 WARN 但保留原样作为 canonical
scoring/readback camera。PM 可以看完整任务过程视频，但不能把这条 review-media run 当成新的 official score
source；正式分数证据仍以 S2-R1E `_003` run 为准。

2026-07-06 最新 stop-go refresh：S0 的 real expert action source 已经冻结完成，当前不再重复 S0。
对应证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json`：
成功 episode 有 905 条连续 9D `joint_position`，freezer sha256 为
`e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f`。通俗讲，“标准答案动作文件”
已经准备好了；但这本身不等于 EBench 正式评分。随后 S1/S1R-D 已经把这份 frozen source 经过 14-step
Route B bridge 接入正式 EBench finalization，并产出 canonical `result_info.json`：`score=1.0`、
`success_rate=1.0`、`metric_score=[[[1.0]]]`。S1/M1 已过；接下来不是继续 S1 retry，而是 S2 检查同一 run
里门关节、metric input 和渲染证据是否能支撑这次分数。

S1 formal score-chain smoke release review 已登记在
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1_formal_score_chain_release_review_20260706.json`。
这一步只允许一次 bounded live：用 S0 冻结的标准答案动作文件、Gate1V-2c runner 和 frozen
`level1_open_door.yml` 跑正式 EBench finalization。产品口径上，S1 成功不要求高分，只要求正式
`result_info.json` 写出来；如果没有写出来，就先修 runner / evaluator lifecycle，不评价 expert 能力。

2026-07-06 S1 historical attempt status：两次 bounded live 已经用完。第一次卡在 config path guard，没进 reset/action；
第二次修正 config path 后，EBench/GenManip 实际已经写出了 `result_info.json`，里面是 `score=0.0`、
`success_rate=0`。但这还不能叫 S1 通过：runner 自己找 `result_info.json` 的目录规则写错了，
把路径拼成了重复的 `ebench/<run_id>/ebench/<run_id>`；另外 `metric_score` 为空，且只执行了第 1 个
action 就 `done=true`，server 记录了 step0 invalid robot state。通俗讲，这次证明“考场有交卷文件”，
但“交卷文件怎么找、记录是否完整、为什么第一步就提前结束”还没闭环。因此接下来不继续盲跑第三次，
而是进入 S1R zero-live repair：先修 `result_info.json` 定位规则，再审计 `metric_score` 是否必须非空，
最后归因 step0 early-done。当前已量到 EBench reset 状态到第一条 expert action 的最大关节跳变约
`2.734rad`，所以这更像 reset/action contract mismatch，而不是 expert 本身不会开门。只有这些闭合后，
才允许再 release 一次 fresh S1 smoke。具体实施计划见
`docs/superpowers/plans/2026-07-06-eos2-s1r-score-chain-repair.md`。

2026-07-06 S1R-A 已完成 zero-live code checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_a_result_locator_code_checkpoint_20260706.json`。
通俗讲，之前 runner 把“答案文件所在目录”多拼了一层 `ebench/<run_id>`，所以真实存在的
`result_info.json` 被误报成 missing；现在 fake-client test 已经复现并修掉这个问题，runner 会记录
`result_info_locator_mode=run_specific_base_dir_compat`。这一步只说明“收卷路径修好了”，还不能说 S1
通过；下一步仍是 S1R-B 审计 `metric_score=[]`，以及 S1R-C 解释为什么第一步 action 就触发
invalid state。

2026-07-06 S1R-B 审计也已完成，但结论不是“给它放行”。给产品经理的通俗解释是：attempt2 的
`result_info.json` 像一张“最低限度的交卷登记表”，上面有总分 `0.0`，但没有完整评分明细。完整登记表
应该由 recorder finalize 写出，里面会有真实 `episode_start_time`、`episode_end_time` 和
`log_info.metric_score`；attempt2 这三个字段分别是 `null`、`null` 和 `[]`，和 GenManip minimal fallback
writer 的特征一致。历史结果也支持这个判断：扫描 79 个 `result_info.json`，5 个非空 `metric_score`
都有真实 start/end，74 个空 `metric_score` 都是 start/end 为 null。因此我们不创建 waiver，不把
`metric_score=[]` 当作 M1/S1 通过证据。下一步新增 S1R-B2：先零 live 修复或证明 full finalize lifecycle
能写出非空 `metric_score`；S1R-C 继续归因 step0 invalid state；fresh S1 只有在 S1R-B2 和 S1R-C
都闭合后才可能 release。

S1R-B2 现在也已完成 code checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_b2_full_finalize_lifecycle_code_checkpoint_20260706.json`。
白话说，我们修了“明明还有 recorder 可以写完整登记表，但因为 episode 已经 done 就直接跳过”的代码风险。
修复后，done 但 recorder 仍存在时会继续走 finalize path；done 且 recorder 已不存在时才跳过，避免重复写。
相关 no-live 测试 `15 passed`。这一步还不能算 fresh S1 release，因为 attempt2 的旧文件不会被追溯修复；
接下来仍要做 S1R-C，把第一步 action 为什么触发 invalid state 归因清楚。

S1R-C 现在也已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_c_step0_invalid_state_attribution_20260706.json`。
给产品经理的白话解释：我们之前把“从 LabUtopia 成功过程里录下来的第 1 个专家动作”，直接放到 EBench
的 reset 姿态上执行；但这两个起点不是同一个姿态。EBench reset 的 joint6 是 `3.037rad`，第一条专家动作
要去 `0.303rad`，一步差了 `2.734rad`；joint4 也差了 `2.577rad`。系统的安全规则是一帧内 arm joint
不能跳超过 `1.0rad`，所以它第 0 步就判 invalid 是合理的。这个结果不能解释成“专家不会开门”，只能解释成
“标准答案动作要从正确起点开始，不能从另一个 reset 姿态硬跳过去”。下一步选 Route B：不改原始 frozen
expert source，在前面加一段单独标注 provenance 的 bounded settle/bridge，先把机器人平滑带到专家动作起点附近，
再 replay 标准答案。

S1R-D release review 现在已经完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_release_review_20260706.json`。
它不是 live 结果，而是一张“准跑证”：只放行 exactly one Route B fresh S1。具体动作源是 14 步
`s1r_route_b_settle_bridge` 加 905 步原始 frozen expert replay，共 919 步 9D `joint_position`；
bridged action source sha256 是
`fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`。这次 fresh S1 必须用 canonical
`saved/eval_results` 作为 `--result-base-dir`，不能再用
`saved/eval_results/ebench/<run_id>`，也不能使用 empty-`metric_score` waiver。它如果闭合
`result_info.json`、`action_log.jsonl`、`metric_trace.jsonl` 和非空 `metric_score`，才算 M1/S1 过；
如果仍闭不上，就停止 oracle scoring，判 runner/evaluator lifecycle 或 bridge contract blocker。

S1R-D Route B fresh S1 现在已经跑完并通过 M1：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s1r_d_route_b_bridge_fresh_s1_result_20260706.json`。
有效 runner invocation exit `0`，summary classification 是
`PASS_SCORE_CAPABLE_ORACLE_RUNNER_CONTRACT`；canonical `result_info.json` 写出了 `score=1.0`、
`success_rate=1`、`log_info.metric_score=[[[1.0]]]`，并且 same-run `action_log.jsonl` 和
`metric_trace.jsonl` 都存在。动作实际执行了 578 步，其中前 14 步是 bridge，后 564 步是 native expert
action，任务在消耗完整 919-step source 前成功结束。产品经理可以理解为：“正式考场这次不仅交卷了，
而且这条 Route B bridged expert replay 拿到了满分候选。”但边界也要说清：这还不是 `Expert Oracle Score`
complete；S2/M3 还要补 door joint readback、metric input dump、render/snapshot 和 route-claim review，
不能直接说 workflow 可扩展或 official leaderboard ready。

S2 no-new-live 盘点也已经完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_readback_render_inventory_20260706.json` 和
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_claim_review_20260706.json`。通俗讲，现在
“分数文件”可信，但“门真的怎么动、评分器当时读到多少度、终态图长什么样”还没有在同一批 artifact 里记录下来：
`metric_trace.jsonl` 只有 reset 时的 robot joints 和一帧 `camera2`，没有 DryingBox `RevoluteJoint` 初末角；
runner stdout 还记录了多次 `No camera frames provided for this step`，说明 step 过程没有可用相机帧。官方 metric
配置确认它评的是 `obj_DryingBox_01/RevoluteJoint`，角度范围 `30-120deg`，`succ_cnts=59`。所以产品口径是：
M1 已过，已有 `score=1.0` 满分候选；S2/M3 还被 readback/render 证据缺口挡住，不能说 `Expert Oracle Score`
complete。那次 release-reviewed `S2 instrumented replay` 已经执行为 S2-L1，并再次拿到 `score=1.0`；
但证据出口仍缺门铰链角、metric input dump 和终态正面渲染图，所以已先完成 S2-I1 no-live repair。S2-R1
随后发现 producer 还没闭环并 blocked，没有释放 live；S2-I2 已补 metric producer snapshot。S2-R1B
release review 固定新 run id、端口、同一 source sha、env 和 artifact list，并只释放一次 S2-L1R。
这次 S2-L1R 已启动，但在 reset 前因为 worker `PYTHONPATH` 缺少 cuRobo source，`curobo.types.state`
导入失败，没有执行任何 expert action，也没有 `result_info.json`。这不是专家轨迹失败，不能进入 S2-L2。
S2-I3 已把 cuRobo source 纳入 server/runner `PYTHONPATH`，S2-R1C 曾用新 run id 释放一次 env-repaired
replacement replay。2026-07-07 后续又关闭了 Ray tmpdir 和 CUDA runtime / `ninja` 环境合约缺口，最终
S2-R1E `_003` 跑通并通过 M3 score/readback evidence review。当前下一步不是继续盲调分数，也不是直接 S2-L2；
而是进入 M4/S4 小样本稳定或 S3 Lift2 oracle/retarget。

更具体的 stop-go 规则已经写入
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_stop_go_20260706.json` 和
`docs/superpowers/plans/2026-07-06-eos2-s2-instrumented-replay-stop-go.md`。S2-I0 runner instrumentation
checkpoint 已通过，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_code_checkpoint_20260706.json`：
runner 现在具备记录 terminal obs、DryingBox `RevoluteJoint` 角度、metric input / `succ_cnts` 和
terminal/front-view render 的接口。S2-R0 release review 已完成并被 S2-L1 消费；S2-L1 分数通过但取证失败。
S2-I1 no-live evidence export contract repair 也已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i1_evidence_export_contract_repair_20260706.json`：
client 会透传 `render_mode/subframes`，client 自己轮询 pending reset 时也会保留 `terminal_obs`，worker 会保留
done-step `terminal_obs`，`step_chunk` 不会再把 ready pending reset result 消费后丢掉，runner 会从
`terminal_obs` 写门角、camera2、metric input 和 `succ_cnts`，且 `render_mode=always` 不再静默 fallback。
S2-R1 release review 已执行但没有放行 live，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_r1_post_repair_release_review_20260706.json`：
review 确认当时 live debug/metric producer 还不会自己产出 metric input / `succ_cnts`，runner 只是有字段就保存。
随后 S2-I2 no-live producer repair 已完成，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_i2_metric_producer_snapshot_repair_20260706.json`：
`MetricsManager` 会保留刚判分的 metric snapshot，`debug.labutopia_open_door` 会导出
`CheckJointAngle(obj_DryingBox_01/RevoluteJoint)` 的 `metric_input`、`succ_cnts`、`metric_success_counter` 和
`metric_score_snapshot`，相关 no-live regression 为 `55 passed`。S2-R1B release review 已完成并只允许一次
S2-L1R post-repair evidence replay；该 replay 已在 reset 前因 `curobo` import path 缺失失败。S2-I3/R1C
已完成环境修复和 replacement replay 准跑。缺证据或 reset/runtime 失败只说明取证/执行系统没闭环，不能判 Route B
expert route 失败。

S2-R0 release review 现在也已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_instrumented_replay_release_review_20260706.json`。
它只是一张准跑证，且已经被 S2-L1 消费。S2-L1 的结果 manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s2_l1_instrumented_replay_result_20260706.json`：
run id 为 `eos2_s2_l1_instrumented_route_b_readback_render_20260706_001`，动作源仍是同一份 Route B source，
sha256 是 `fab13ee9cf705e2062efbd30d172eb3bf850cf900bcb54ff13e42124133e740a`。给 PM 的口径是：这次正式
EBench 仍拿到 `score=1.0`，专家动作路线没有被证明失败；但 terminal obs 为空、门角没有导出、terminal camera
artifact 缺失，所以 S2/M3 仍没签收。下一步不再直接 live；S2-I1 no-live evidence export contract repair 已完成，
S2-R1 因 producer 缺口 blocked，S2-I2 已补 metric producer snapshot，S2-R1B 签发的 S2-L1R 因 cuRobo env
缺口未进入 reset/action；S2-I3/R1C 已签发 exactly one env-repaired replacement replay。现在需要执行这一次
post-env-repair evidence replay。

产品经理可以按这条线判断“什么时候算弄好 / 什么时候该停”：

| 阶段 | 产物 | 算通过 | 过不了怎么停 |
|---|---|---|---|
| S0 / M2 前置 | `candidate_action_source.jsonl` + freezer 产出的 `action_source_manifest.json` | 已完成：标准答案动作源被冻结，可进入正式评分链 | 不再重复 S0；除非 S1 证明 frozen source contract 本身不可消费 |
| S1 / M1 | authoritative `episode_result.score` + `result_info.json` + runner contract exit 0 | 已完成：Route B fresh S1 `score=1.0`、`success_rate=1`、`metric_score=[[[1.0]]]` | 不再继续 S1 retry |
| S1R | result locator、`metric_score` policy、full finalize lifecycle、step0 early-done attribution、Route B bridge release | 已完成：A/B/B2/C/D + fresh S1 result 均闭合 | 不再作为当前 blocker |
| S2 / M3-前半 | Franka/native frozen source 在 EBench metric 下跑通 | 已完成：S2-R1E full-env repaired run `score=1.0` / `success_rate=1.0`，终态门角 `41.715865deg` 在 `[30,120]deg` 内，`metric_input.within_range=true`，`succ_cnts=59`，terminal camera artifact 和 `camera2.mp4` 存在 | 不释放 S2-L2；若未来 replay 出现完整证据下 metric/physics 失败，才允许一次 confirmation |
| S3 / M3-后半 | Lift2 oracle / retarget 同样有 official score 证据 | 官方机器人口径有 scoring value | 最多 2 个 mapping families x 2 个 variants；都失败则关闭当前 retarget route |
| S4 / M4 | 3-5 episodes/seeds 稳定表 | workflow ready for expansion | 单次成功不可复现或失败不可分类，不扩展 |

通俗说：最早到 S2-L1R env-repaired replacement evidence replay 且证据齐全，才能说“单 episode 专家评分 POC 弄好”；
到 M4 / S4 才能说“可以扩展交付”。如果 replacement replay 证据仍缺，就停在 evidence system；如果完整证据下
metric/physics 失败，再允许一次 S2-L2 confirmation；只有两次完整证据下使用同 action source sha、同
command/env、同 metric code/contract、同 instrumentation，且失败签名一致，才判当前 Route B 路线不成立。
任何中间失败都只能判某条路线 blocked，不能判 LabUtopia-to-EBench 项目整体不行。

## Historical / Parallel Branch Archive

下面内容是 S0/S1R、Gate、Lift2、E2R、F-stage 和早期 planner/contact 分支的历史或并行路线档案，用于追溯为什么某些分支被关闭或转向。它们不覆盖本文顶部的 current canonical 主线：`M1 passed -> S2-L1 score pass but evidence failure -> S2-I1 no-live evidence export repair complete -> S2-R1 blocked -> S2-I2 metric producer repair complete -> S2-L1R reset-before-action env failure -> S2-I3/R1C env-repaired replacement replay -> no S1 retry / no blind score tuning`。

下面的 S0 段落是 historical progression：它们记录从 freezer/exporter code-ready 到最终 S0 freeze 的过程。
当前 canonical 状态以 S0 freeze success、S1R-D Route B fresh S1 result、S2-L1 result、S2-I1 no-live
repair、S2-R1 blocked review 和 S2-I2 metric producer snapshot repair 为准，即 S0 已完成、S1/M1 已通过，
S2-L1 分数通过但 evidence-blocked，S2-I1 evidence export repair 已完成，S2-R1 因 producer 缺口 blocked，
S2-I2 已 no-live 修复；S2-R1B 放行的 S2-L1R 因缺 cuRobo import path 在 reset 前失败，S2-I3/R1C 已完成环境修复和 replacement replay 准跑。

2026-07-06 S0 action-source freezer code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_action_source_freezer_code_checkpoint_20260706.json`。
这一步把 M1 之前最基础的“标准答案文件验收工具”补上了：GenManip 侧新增
`score_oracle_action_source_freezer.py`，会校验 replay JSONL 的 worker、action dimension、`control_type`、
`step_index` 连续性、`base_motion`、布尔字段和 sha256，并把输入复制成冻结副本加 manifest。focused test
先 RED 到模块缺失，再 GREEN 到 `3 passed`；和 score-capable runner 合跑为 `10 passed`。但只读审计没有发现
现成可冻结的真实 expert action JSONL，所以当前状态是 freezer code-ready，不是 frozen expert source ready；
仍不允许 live，也不能 claim `Expert Oracle Score`。

2026-07-06 S0 action-source exporter code checkpoint 也已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_action_source_exporter_code_checkpoint_20260706.json`。
这一步补的是“把诊断轨迹整理成标准答案候选文件”的工具：GenManip 侧新增
`score_oracle_action_source_exporter.py`，可以把 planner summary 里已经记录的
`trajectory_action_joint_positions` 转成 freezer-compatible replay JSONL，并标记来源为
`diagnostic_trajectory`。fresh verification 是 exporter + freezer + score-capable runner 合跑
`13 passed in 0.04s`，`py_compile` 和 `git diff --check` 均 exit 0。产品口径要保持边界：exporter
ready 只说明“已有诊断轨迹可以被整理成 EBench replay 输入格式”，不说明它就是完整 expert、不说明能开门、
不说明能得分。S0 仍未完成；真正下一步是选定真实 expert/oracle 来源，导出后再用 freezer 冻结成
`action_source_manifest.json`。

2026-07-06 S0 source eligibility audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_source_eligibility_audit_20260706.json`。
通俗讲，我们又查了一遍“现有证据里有没有已经能交卷的标准答案文件”。答案是没有。现有 evidence 里确实
有 75 个 JSON 包含可导出的 planner 轨迹点，共 33274 个 point；但它们的状态都属于 diagnostic-only 或
blocked reachability：43 个 fail diagnostic、18 个 reachability blocked、14 个 pass diagnostic。这里的
`PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY` 也只是诊断通过，不是 EBench 正式得分通过。
目录里没有 `action_source_manifest.json`；唯一 `result_info.json` 是 AAN runtime smoke，`score=0.0`、
`success_rate=0`。所以 exporter/freezer 工具链 ready，但真实 S0 expert source 仍缺，S1 formal score-chain
smoke 仍不释放。

2026-07-06 S0 next-source route review 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_next_source_route_review_20260706.json`。
多角度 review 后，下一步推荐顺序是 A -> B -> C。A 是最短主线：先生成或导出 deterministic
Franka/native oracle replay JSONL，把 task config、seed/reset、action dialect、control dt、termination、
worker id 和 provenance 写清，再用 freezer 冻结成 `action_source_manifest.json`。A 做不到，或后续 formal
stop line 失败后，B 才单独开 native/controller contract research，而且它先是 no-score lane，必须证明不是旧
`16D joint_position -> set_joint_position_targets -> world.step` 的换名版本。C 只能并行做资产、render、
logging、metric 的 no-score hardening，不能替代标准答案动作源。当前仍不能释放 S1 live，也不能 claim
Franka/native expert 已得分或 Lift2 official action path 已解决。

2026-07-06 S0 deterministic Franka/native source code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_deterministic_franka_source_code_checkpoint_20260706.json`。
这一步把 A 路线从“规划”推进到“可捕获候选动作源”：新增
`utils/ebench_replay_action_source.py` 和 `tests/test_ebench_replay_action_source.py`，并在 `main.py` 加了 opt-in
参数 `--ebench-action-log-dir` / `--ebench-action-worker-id` / `--ebench-action-expected-dim`。它会把 LabUtopia
native controller 输出的 `ArticulationAction.joint_positions` 记录成 EBench replay JSONL；其中 `None`
joint 会用当前 observed joint position 填上，形成完整 9D `joint_position`。TDD RED 先失败在模块缺失，
GREEN 后 `6 passed in 0.04s`，`py_compile` 和 `git diff --check` 均 exit 0。产品口径：candidate logger
ready，但还没跑 native expert capture、没生成 candidate 文件、没 freezer 冻结、没得分；下一步才是一次
`max_episodes=1` 的 bounded LabUtopia capture。

2026-07-06 S0 bounded native capture 已按 stop-go 规则跑了一次，但没有进入 freezer：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_native_capture_attempt_20260706.json`。
第一次入口失败是 shell Python 没有 `isaacsim`；第二次使用 `labutopia-py311` 后成功进入 Isaac/LabUtopia，
但记录器在第二类动作上触发 `ValueError: action_dim_mismatch:7!=9`。通俗讲，LabUtopia native
open controller 的动作有两种形态：起始开夹爪是完整 9D Franka action，后续 C-space 手臂运动可能只返回
7D arm-only action；Isaac 可以消费这种 controller 输出，但我们的 EBench replay JSONL 要统一成 9D。
本次只留下 1 条 partial JSONL，没有 `candidate_action_source_manifest.json`，也没有 native success，所以不能
freezer，不能说 S0 完成。

对应的 zero-live repair code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_action_dim_contract_repair_code_checkpoint_20260706.json`。
新增规则是显式 opt-in：默认仍严格校验；只有加 `--ebench-action-allow-prefix-dim` 时，7D arm-only prefix
才会用当前 observed tail joints 补成 9D，并在 source metadata 里记录
`raw_action_dim`、`observed_joint_dim` 和
`normalization=prefix_action_expanded_with_observed_tail`。TDD RED/GREEN 后
`tests/test_ebench_replay_action_source.py` 为 `7 passed in 0.11s`，`py_compile` 通过。下一次 capture 不能直接
算“补跑”；必须先登记新的 bounded live release review，命令里显式使用
`--ebench-action-allow-prefix-dim`。

随后 prefix-dim repair-validation capture 已按 release review 执行：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_prefix_repair_validation_capture_result_20260706.json`。
它证明 7D 补 9D 这件事已经过 live：`candidate_action_source.jsonl` 有 968 条 action，全部是 9D，
其中 664 条来自 7D raw action 的 prefix expansion。但它仍不能 freezer，因为 manifest 里
`success_observed=false`。stdout 显示 LabUtopia 前 8 次失败、第 9 次才 `Task success!`；我们的 logger
在第一次失败 episode 结束时就 finalize 并关闭了，所以记录到的是 failed episode，不是成功专家轨迹。

对应 zero-live lifecycle repair checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_logger_lifecycle_repair_code_checkpoint_20260706.json`。
修复后，`done && is_success=false` 会丢弃当前 JSONL、重置 action count，继续记录下一次尝试；只有
`done && is_success=true` 才会写 `candidate_action_source_manifest.json`。TDD RED/GREEN 后
`tests/test_ebench_replay_action_source.py` 为 `8 passed in 0.05s`，`py_compile` 通过。下一步仍要先登记新的
bounded live release review，再验证成功 episode capture；不能对上一份 failed candidate 运行 freezer。

S0 lifecycle-validation capture 和 freezer 随后已闭合：
`docs/labutopia_lab_poc/evidence_manifests/eos2_expert_oracle_s0_lifecycle_validation_freeze_success_20260706.json`。
这次 capture exit 0，manifest 里 `success_observed=true`，丢弃了 1 个失败 episode，最终成功 episode 有
905 条 action，全部是 9D `joint_position`，其中 601 条由 7D arm-only raw action 显式补齐。freezer 输出
`frozen_action_source/action_source_manifest.json`，classification 为 `PASS_SCORE_ORACLE_ACTION_SOURCE_FREEZE`，
source 和 frozen JSONL 的 sha256 都是
`e1953c48afe8ce2e8008365faedce38c3ecee8f71a210013796530a797b3fd6f`。产品口径：S0 已完成，标准答案文件
准备好了；但这不是 EBench score，S1 formal score-chain smoke 还没释放，不能 claim Expert Oracle Score。

2026-07-06 历史/并行 Lift2 direct-16D 分支记录：EOS-2 当时已执行完 E2 single live，结果是
`BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED`。证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_live_20260706/result_compact.json`。
这次不是当前 canonical S2 instrumented replay，也不是重跑 DryingBox candidate，而是 non-DryingBox Lift2 controller reference / retiming probe：
5 个 no-op、5 个 right-arm small ramp、60 个 terminal hold。它只校准 Lift2 controller/action/readback，
不代表 contact、door opened 或 `Expert Oracle Score`。实际结果是 `executed_steps=70/70`，但 no-op 和
terminal hold 都没到 `0.02rad` joint tolerance；final joint error 是 `0.20075764784227174rad`。所以该历史 Lift2 分支当时的下一步
不是 E3/E4，也不是再跑 DryingBox，而是先修或解释 Lift2 controller/action/readback contract；这不覆盖当前顶部的 S2/M3 证据补齐主线。

2026-07-06 E2R root-cause plan 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r_controller_action_readback_root_cause_plan_20260706.json`。
它把接下来“预计到哪一步能弄好 / 到哪一步判这条路不行”写成硬门：不再盲跑 DryingBox，最多只允许两次
non-DryingBox controller sanity live。E2R1 先补 per-joint telemetry；E2R2 用增强仪表重跑同一个小动作
probe，判断是 reset baseline、slot mapping、drive target 还是 timing/hold 问题；E2R3 只做一个被证据支持的
修复；E2R4 用最后一次 controller sanity live 验证。E2R4 通过后才回到 E3/E4；E2R4 在 telemetry 闭合后仍
同类失败，就停止当前 direct 16D `joint_position` 路线，改走 official Lift2 baseline controller/action path
review。

该历史 Lift2 分支给产品经理的白话解释：当时不是继续试开门，而是先校准“机器人和尺子”。E2 已经证明动作交进了系统，
但关节读数没有跟到目标；现有日志只知道最大误差，不知道具体是哪一个关节、哪一个 slot、哪一层合同错。
所以接下来先补仪表，而且不是泛泛地“多打日志”：E2R1 必须记录 observed_joints12、observed_gripper4、
observed_action_16d、expected vectors、target_minus_observed_16d、每个 index 的误差、最大误差对应的
action slot / global DOF / DOF name、完整 action_application_debug、post-step joint vector 和
controller_drive_debug。然后再用一次最小小动作测试定位根因，修一个点后再用一次小动作验证。能不能回到
DryingBox，最早看 E2R4；能不能说专家路线有戏，最早看 E4 one-segment precontact；能不能算
`Expert Oracle Score`，还要等 contact、retention、micro-pull 和 metric readback。

2026-07-06 E2R1 code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r1_per_joint_telemetry_code_checkpoint_20260706.json`。
这一步不启动 Isaac、不跑 DryingBox、不算分，只把“验收尺子”补细。TDD 先证明旧工具确实缺
`observed_joints12`、`full_action_application_debug` 和 `action_slot_mapping`，再补实现，最后
`test_lift2_controller_reference_probe.py` 跑到 `13 passed in 0.03s`。产品口径：现在已经可以做下一次
E2R2 enhanced non-DryingBox live；这次 live 的目标不是开门，而是用每个关节的读数定位 root cause。

2026-07-06 E2R2 enhanced live 已执行，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r2_enhanced_lift2_controller_reference_live_20260706/result_compact.json`。
结果仍然 blocked，但这次不是“只知道失败”：仪表已经能指出具体关节。no-op 阶段最大误差在
`fl_joint3`，目标是 reset 读到的 `0.04764rad`，实际很快漂到约 `0.09469rad`，说明 reset 后的基线/稳定状态
还没对齐；terminal hold 阶段最大误差在 `fr_joint1`，controller 目标已经写成 `0.20075rad`，但真实读数
60 步后仍接近 `0rad`。所以这不是简单“ramp 太快，多 hold 一会儿就好”的问题。下一步是 E2R3：
不跑新 live，先审计和修一个底层假设，重点看 Lift2 arm joint tracking / controller application path。

2026-07-06 E2R3 zero-live / single-hypothesis repair plan 已固化：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3_lift2_articulation_contract_repair_plan_20260706.json`。
多角度 review 后，当前优先假设不是“评分器坏了”，也不是“DryingBox 太难”，而是
`controller target -> Lift2 physical arm articulation motion` 这段合同没有闭合。E2R2 已证明 target 进入
controller；但 `fr_joint1` 在 60 步 terminal hold 后仍几乎不动。因此 E2R3 拆成 3 个 0-live 子步骤：
E2R3a 审计 USD/articulation/DOF/drive/limit 合同，E2R3b 只补 code/test-only articulation telemetry，
E2R3c 决定唯一一个修复点。E2R4 才允许最后一次 non-DryingBox controller sanity live；E2R5 是封账分叉：
E2R4 通过则回到 E3/E4，E2R4 同类失败则停止当前 direct 16D `joint_position` 路线，转 official Lift2
baseline controller/action path review。

E2R3a zero-live audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3a_lift2_articulation_contract_zero_live_audit_20260706.json`。
通俗讲，静态资产层没有发现“右臂关节根本不存在”或“`fr_joint1` 没有 drive”这种粗错误：`fr_joint1`
在 USD 里是 `PhysicsRevoluteJoint`，有 `PhysicsDriveAPI:angular`，`jointEnabled=true`，
`excludeFromArticulation=false`。但这还不能证明 runtime 里 DOF mapping、qdot、limit、max velocity、
sleep/constraint 都正常。所以下一步 E2R3b 仍然不跑 live，只补 code/test-only runtime articulation
telemetry，让 E2R4 最后一次小动作 live 能准确判断该修 controller API、drive/effort、reset baseline，
还是 official Lift2 baseline action path。

E2R3b code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3b_articulation_telemetry_code_checkpoint_20260706.json`。
GenManip 的 `read_articulation_controller_debug` 现在除了原有 target / drive / max effort，还能输出
`joint_position`、`joint_velocity`、`max_joint_velocity`、`joint_lower_limit`、`joint_upper_limit`。
TDD 先 RED 到缺 `joint_position`，补实现后 focused 2 passed，相关 LabUtopia suite `97 passed in 0.60s`。
这仍然不是“机器人会动了”，只是下一次 E2R4 能看清楚关节到底有没有速度、是不是被 limit/velocity/effort
挡住。下一步 E2R3c 先选唯一修复点，仍不允许直接跑 DryingBox 或 score。

E2R3b2 summary telemetry addendum 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3b2_summary_telemetry_addendum_20260706.json`。
这一步也没有启动 Isaac，只把最终 step 的 `controller_drive_debug` 和 runtime motion fields 提升到
summary 顶层：`joint_position`、`joint_velocity`、`max_joint_velocity`、lower/upper limits、applied target
和 drive 参数。通俗讲，我们没有改机器人怎么动，只是把 E2R4 最后一次 live 的“判卷仪表”放到报告首页，
避免跑完后还要在大 trace 里人工翻证据。新增测试后相关 suite 为 `98 passed in 0.60s`。

E2R3c single repair decision 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3c_single_repair_decision_20260706.json`。
结论是：现在不做猜测式行为修复，不盲目加 drive/gain、不盲目换 articulation API、不盲目加 hold，也不把
reset baseline 当主修复。下一步只允许 exactly one E2R4 non-DryingBox controller sanity live，带 E2R3b
新增 telemetry 跑同一个小动作。如果 E2R4 通过，才回 E3/E4；如果 target applied 但 qdot 近零且
limit/velocity/effort 解释不了，就停止当前 direct 16D `joint_position` 路线，转 official Lift2 baseline
controller/action path。

E2R4 final controller sanity live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r4_final_controller_sanity_live_20260706/result_compact.json`。
这次严格只跑非 DryingBox 的 Lift2 小动作 sanity probe：`70/70` steps，`5` no-op、`5` ramp、`60` hold。
结果是 direct 16D route no-go：最终 `right_joint1` target 是 `0.200753768836rad`，controller applied target
是 `0.20075376331806183rad`，但 worker obs observed 仍约 `-0.000003879rad`，final error
`0.20075764784227174rad`，超过 `0.02rad` tolerance。limits 不挡，drive 参数存在，`readback_errors=[]`。
runtime `max_joint_velocity` 没读到，所以不能说 telemetry 完全闭合；但多角度 review 认为这不需要再消耗
一次 live，因为 60-step hold 已经证明不是简单 ramp 太快。

E2R5 zero-live closure 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r5_direct_16d_route_closure_fork_20260706.json`。
产品口径：这不是 LabUtopia-to-EBench 项目失败，也不是 Expert Oracle Score 失败；只是当时 direct 16D
`joint_position` 动作接口路线封账。该历史分支当时停止 DryingBox/E3/E4/score 盲试，转 official Lift2 baseline
controller/action path review，先找到官方 Lift2 baseline 到底用什么动作接口能让机器人真实运动。当前 canonical 主线仍是顶部所述的 S2 instrumented replay 证据补齐。

2026-07-06 历史/并行 official Lift2 baseline 分支的 stop-go review 后，该分支的预计边界已经收敛：
该分支短期不是继续试到开门，而是先把 official Lift2 baseline 的底层控制口径判清楚。F1 已证明 terminal
arm-only zero-base official payload 与 E2R4 等价；F1b 已证明 endpoint 和 base_motion 不能作为 right-arm
修复理由；F1c 已选择 controller/articulation runtime repair；F1d 已把这个方向落到
`Lift2 arm runtime max-effort-only repair`；F1e 也已把这个修复干净写进 GenManip 并用 focused tests
验证。该历史分支内部当时只剩 F2 stop-go review 加最多一次 F2 live；这不覆盖当前顶部的 S2 instrumented replay 主线。

F2 的一句话定义：F2 不是开门测试、不是 DryingBox 测试、不是 score 测试，只是底层控制小考。它固定用
non-DryingBox 小动作，检查 `action -> controller target -> physics motion -> worker obs` 是否闭环。F2
通过，才允许回到 DryingBox E3/E4；F2 失败，只说明当前 selected max-effort repair route 在 GenManip /
EBench runtime 下 blocked。唯一例外是 F2 telemetry/readback 自己缺失，那只能判 telemetry blocked，先补判读能力，
不能把它算成 max-effort repair no-go。

给产品经理的通俗说法：我们不是无限尝试，而是按硬门推进。当前已经过了“选具体修复点”和“修复是否写进代码”两门；
下一门 F2 判断“修后的底层动作口径能不能让机器人右臂真实动起来”。F2 过了，E4 才判断“DryingBox 专家路线
有没有工程成功信号”；Gate 4 才判断“是否能接触、保持并带动门”；Gate 5 才判断“EBench metric 能不能记录专家分”。
完整“弄好”必须到 Gate 5 `Expert Oracle Score` 有有效 score / reward / success、action log、metric trace、
`result_info.json` 和 render/readback 证据。

如果 F2 后 target applied、max effort repaired，但 `right_joint1` 同向运动不足或 terminal error 超过阈值，就停止当前
`Lift2 arm runtime max-effort-only repair route`，转 higher-level official runner 或 action abstraction
review，不再靠加 hold、调 gain、换 seed 或扫 offset 继续消耗 live。这里的局部 no-go 只表示“当前路线停”，
不是 LabUtopia-to-EBench 项目 no-go；项目 no-go 必须等所有预先允许的分支都按证据停止后才能讨论。

F1 terminal zero-base arm-only official prep-output equivalence 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1_official_prep_output_equivalence_20260706.json`。
它用 E2R4 最终的 16D target 反推 official 19D row，再走 official prep-output，结果显示 arm-only /
zero-base 情况下 official payload 和 E2R4 direct 16D payload 完全等价：joint diff、base diff 和 metadata diff
都是 0。产品口径：不能再说“换 official baseline 跑一次也许就好了”，因为如果不引入真实 endpoint/base
差异，terminal arm-only zero-base 跑出来就是同一个失败动作。这个结论还没有覆盖 no-op、ramp、完整
official policy 19D horizon、official runner endpoint 或 LabUtopia wrapper boundary。当前只证明在同一个
terminal arm payload 的 synthetic probe 里 `base_motion` 是 payload-level 差异，但 base motion 本身不解释
right arm 关节不跟踪；所以下一步是 F1b zero-live endpoint/base-motion boundary review，不是直接启动
F2 live，也不是回 DryingBox。该段是 F1 完成时的阶段口径；后续 F1b/F1c 已完成，当前下一步已更新为 F1d。

2026-07-06 F1b official runner endpoint/base-motion boundary review 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1b_official_runner_endpoint_base_motion_boundary_20260706.json`。
白话结论是：official runner 背后没有发现一条绕过 E2R4 的新动作入口。official OpenPI/Pi0 runner
和我们的 reference probe 最终都走 GenManip `/step_chunk`，再进入同一个 `env.step` 应用动作。official
19D 格式里多出来的 `base_motion` 是真实差异，但它控制的是底盘，不是右臂 `right_joint1`，所以不能用来
解释或修复右臂不动。接下来不允许“换 official 名字再试一次”；必须先做 F1c 0-live selector，写清唯一
一个真实下一路由、readback、tolerance 和失败停止线。最早能判这条下层控制路线有戏或没戏的是 F2；
完整“弄好”仍要到 F5 `Expert Oracle Score` 有有效 score / reward / success、action log、metric trace、
`result_info.json`、render 和 readback 证据。

2026-07-06 F1c single-hypothesis selector 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1c_single_hypothesis_selector_20260706.json`。
产品口径：现在不是“继续试 official baseline”，而是已经选定下一步只查一个方向：
`controller/articulation runtime repair`。原因是动作 target 已经进 controller，但右臂 `right_joint1`
物理上没跟着动。Newton 证据只能当旁证，不能证明 Isaac / GenManip 里会动；`base_motion` 也只是底盘，
不能修右臂。因此 F1c 仍不允许 F2 live。下一步是 F1d：先在 0-live 下选一个具体修复点，写清一次 F2
要跑什么、看哪些 readback、容差是多少、失败就怎么停。后续 review 已收紧为：F1d 过了也不直接 live，
必须先过 F1e code/test checkpoint，才允许一次 non-DryingBox bounded live。

2026-07-06 F1d concrete repair selector 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1d_concrete_repair_selector_20260706.json`。
产品口径：我们现在把“修 controller/articulation”进一步落成一个具体点，并在晚到的 review 后修订为
`Lift2 arm runtime max-effort-only repair`。原因是 API 换写法并不会改变底层 target path；而 E2R4 里
`right_joint1` target 已进 controller、limits 正常，但 runtime `drive_max_effort` 只有 `100.0`。F1d 仍不代表
修好了，也不允许 F2 live。下一步是 F1e：先把这个 max-effort-only 修复写进 GenManip，并用 focused test
证明代码路径确实和 E2R4 unchanged path 不同；F1e 通过后才允许一次 non-DryingBox 小动作 live。这一次 F2
不是 retry budget：如果 repaired max effort 已读到、target 也 applied，但 `right_joint1` / EEF 同向运动不足或 terminal error 超阈值，
当前 max-effort repair route 就停止，不能继续同路线调 hold、gain、seed、offset 或 API。

2026-07-06 F1e code/test checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f1e_lift2_runtime_max_effort_code_checkpoint_20260706.json`。
通俗讲，这一步不是让机器人真的开箱，而是把“电机最大出力太小”这个假设变成一段可测试的代码修复：
只把 Lift2 左右臂 12 个 arm DOF 的 runtime max effort 提到 `1000000.0`，并且放在
`_post_initialize()` 之后执行，避免 ArticulationView 未初始化时 no-op。它没有改动作格式、API、gain、
max velocity、hold、base_motion 或 DryingBox。focused test 先失败再通过；相邻测试 `20 passed`，
`py_compile` 和 `diff --check` 也通过。

产品口径：F1e 让我们有资格安排一次 F2 小考，但还不能说机器人已经会动。下一步先做 F2 stop-go review，
把命令、readback 和失败停止线钉死；然后最多一次 non-DryingBox live。如果这次能读到 repaired max effort，
target 也 applied，但右臂同向运动不足或 terminal error 超阈值，就关闭当前 max-effort 修复路线，转 higher-level official
runner / action abstraction review。

2026-07-06 F2 command preflight 已准备：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_preflight_20260706.json`。
通俗讲，这一步是把“考卷、考场、判分尺子”先写死，还没有真正开考。它固定了端口 `18132`、run_id、输出目录、
server 命令、submit 命令和 runner 命令；也确认 `EvalClient.reset` 不会自己加载任务，所以 F2 必须先
`submit level1_open_door.yml`，再跑 70 步小动作 probe。F2 仍然不是 DryingBox 开门测试，也不是 score 测试。

下一步不是马上宣布能跑，而是先做多 agent preflight review。review 通过后，才允许 exactly one F2 live。
如果 review 发现命令、环境或 readback 字段还不够硬，就停在 preflight，不消耗 live budget。

第一轮 review 已经指出两个具体风险并已修正：F2 不能只把命令写在 JSON 里，必须在 F2 live evidence dir 落地
专属 `server.command.txt` / `runner.command.txt`，避免误跑旧 E2R4 的 `18131` 命令；另外 runner exit code
不是 F2 pass 判据，F2 必须按 hard checklist 读 `summary.json`，包括 `right_joint1_motion`、max effort、
requested/applied target、terminal error 和 `readback_errors`。这些修正完成后仍需要复审，复审通过才开考。

2026-07-06 复审后的最新口径：F2 preflight 已足够释放 exactly one F2 live，但我们不会因为 server 已经能启动
就把它算作成功。此前一次 pre-live server attempt 在 runner 启动前因 Ray socket 路径过长失败，已通过缩短
`RAY_TMPDIR=/tmp/gf2_18132` 修复；由于当时没有 `live_consumed_at.txt`、`summary.json`、`trace.jsonl`
或 `runner.exit_code.txt`，F2 live budget 仍是 `0/1`。下一步只允许按 F2 专属 `runner.command.txt`
消费一次 live。跑完后按四类结果汇报：F2 PASS 才回 E3/E4；完整读数下同向运动不足或 terminal error 超阈值则当前 max-effort repair
route local no-go；缺字段则 telemetry blocked；server/submit/reset/runner 在 `summary.json` 前失败则
infra blocked。

给产品经理的白话版本：F2 是“机器人底层听不听指令”的小考，不是开门考试。最早能说“基本能接上”要看
E4/F3 的 DryingBox precontact；比较稳的工程成功信号要看 Gate 4 micro-pull 是否带动门关节；真正能说
`Expert Oracle Score` 闭环，要等 F5/Gate 5 产出 score / reward / success、action log、metric trace、
`result_info.json` 和 render/readback。

2026-07-06 F2 exactly-one live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2_lift2_max_effort_controller_sanity_live_20260706/result_compact.json`。
结果是 current max-effort repair route local no-go，不是项目失败，也不是 `Expert Oracle Score` 失败。关键事实：
`70/70` steps 跑完；slot `8` / `right_joint1` 的 requested target 到 controller applied target 的 diff 约
`2.90e-09rad`；runtime max effort 读到 `1000000.0`，说明 F1e 修复生效；`right_joint1` 也确实同向动了约
`0.11047rad`。但 F2 pass 预设要求至少 `0.18rad`，最终 error 要小于 `0.02rad`；实际 terminal error 约
`0.08953rad`。所以正确解释不是“完全没动”，而是“有响应但不够可控、不够到位”。下一步按 stop-go 只能做
higher-level official runner / action abstraction 的 zero-live review，不能同路线加 hold、调 gain、换 seed、
扫 offset 或换 API。

2026-07-06 F2 后的收敛规划已更新为 F2a/F2b/F2c/F2d：
先不继续 live。F2a 只做 provenance review，确认是否真的存在一个不同于当前
`env.py -> set_joint_position_targets -> world.step` 的 official runner / action abstraction。多角度 review
已经排除了三个容易误会的“伪新路线”：`physics_hold_steps` 是 diagnostic-only，不是 official 动作接口；
`step_chunk_size` 只是把同一批动作切小块提交，方便采样和 trace，不改变控制语义；official prep-output /
`base_motion` 的 arm 部分仍会落到同一个 16D `joint_position` path，`base_motion` 只是底盘通道，不能解释右臂关节不达标。

给产品经理的白话版本：现在不是“再多试几次应该能好”，而是先判断“还有没有一条真正不同的路”。如果 F2a 找不到这种路，
就关闭 F-stage lower-level action 分支；如果找到了，F2b 也必须先在本地证明它能稳定把 `right_joint1` 动到
`>=0.18rad` 且最终误差 `<=0.02rad`。只有 F2b 过了，F2c 才把它封装成可复现 canonical command / artifact；
只有 F2c 过了，F2d 才允许下一次 live。换句话说，下一次 live 不是用来探索的，只能用来确认已经在本地证明过的方案。

2026-07-06 F2a zero-live provenance review 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_f2a_provenance_review_result_20260706.json`。
结论是 F2a fail：EOS 侧 official/OpenPI Pi0 runner 仍是 `50x19 -> 16D joint_position + 3D base_motion`；
GenManip 侧仍是 `/step_chunk -> env.step -> set_joint_position_targets -> world.step`。`base_motion` 是底盘通道，
`physics_hold_steps` 是诊断开关，`step_chunk_size` 只是切块，`ee_pose/custom_motion` 最后也会转成 joint target。
所以没有找到可以进入 F2b 的真实新动作路线。

给产品经理的白话版本：这一步相当于把“是不是还有一条隐藏的官方控制通道”查完了，答案是没有。当前这条
F-stage lower-level official/OpenPI action 分支到这里停止，不再进入 F2b/F2c/F2d，也不再 live retry。它不是
LabUtopia-to-EBench 项目失败，也不是专家轨迹失败；只是说明“沿当前官方底层动作接口继续试”已经没有工程依据。
下一步必须回到更高层路线决策，例如重新定义 Lift2 control contract、单独开 native-controller research lane，
或重新规划 DryingBox 专家路线的机器人/控制面，而不是继续调同一条 action path。

2026-07-06 Gate1V post-F route decision plan 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_post_f_stage_route_decision_plan_20260706.json`，
计划文档是
`docs/superpowers/plans/2026-07-06-eos2-gate1v-post-f-route-decision.md`。
多 agent review 一致建议：不要继续 F2b/F2c/F2d，也不要把 native-controller research 包装成 official score。
下一阶段拆成三条线：第一优先是 `robot_task_fallback_oracle`，先用更容易评分的 robot/task 组合把
EBench metric / reward / success / `result_info.json` / action log / metric trace 闭合；第二条是
`asset_task_no_score_hardening`，继续保证 DryingBox / AAN 资产、layout、render、metric、logging 可交付，
但明确 `score_claim_allowed=false`；第三条是 `native_controller_research`，如果坚持 Lift2，就先定义新的
`native_drive_target` / native controller contract，并证明它不是当前 failed `joint_position` path 的换名版本。

给产品经理的通俗版本：现在“预计弄好”的最近节点不是 Lift2 直接开门满分，而是两步走。第一步
Gate1V-2a 先冻结 EBench config、score-capable oracle runner、expert action stream / deterministic route 和
artifact contract；这一步通过只能说明“可以释放一次 bounded fallback score live”。第二步才是这次 live
真的产出 score / reward / success、action log、metric trace、`result_info.json` 和 render/readback；只有
第二步也通过，才能说“标准答案放进 EBench 后，判卷器能正确给分”。如果 Gate1V-2a 冻结不了 runner/action
source，或者 live 后 expert action 已进入 EBench 但 metric 不涨、success 不记录或 result artifacts 不闭合，
就可以较早判定当前 robot/task fallback score route blocked。这个 stop line 只判当前分支，不是项目 no-go。

2026-07-06 Gate1V-2 fallback oracle preflight 已完成零 live 审计：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_fallback_oracle_preflight_20260706.json`。
结论不是 PASS，而是 no-live blocked：最近的 fallback route 确认是 Franka POC `level1_open_door`，
metric 侧已经清楚，EBench 使用 `manip/default/check_joint_angle` 读 `obj_DryingBox_01/RevoluteJoint`，
成功范围是 `30-120deg`，`succ_cnts=59`。但 live 还不能释放，因为实际
`ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml` 目前只在外部 GenManip dirty worktree 中，
尚未作为冻结 artifact 收进本仓库；同时 LabUtopia native expert 现在只有 video/log success 证据，
没有可提交给 EBench 的 frozen action stream 或 score-capable runner。

给产品经理的通俗版本：我们已经确认“判卷器要看哪一个门轴、怎么算成功”，但还没准备好“把标准答案以
EBench 能执行的动作格式交进去”。所以这一步提前阻止 live，不是失败一天白跑，而是避免拿视频成功或
diagnostic runner 冒充 `Expert Oracle Score`。下一步是 Gate1V-2a：冻结 EBench Franka config、冻结
score-capable expert/oracle runner、冻结 action stream / deterministic route，并预注册命令、环境、输出目录、
`result_info.json`、action log、metric trace 和 render/readback。只有这些完成，才允许一次 bounded
fallback score live。

2026-07-06 Gate1V-2a fallback oracle freeze 已完成零 live 审计：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2a_fallback_oracle_freeze_20260706.json`。
结论仍然不是 PASS，而是 no-live blocked。已闭合的部分是 config：Franka POC `level1_open_door` 的 EBench
config 已冻结到
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2a_fallback_oracle_freeze_20260706/frozen_configs/level1_open_door.yml`，
sha256 为 `e78e5f4b58a39b15bc9146436bf50249b850f71b1171e3f671bbd95e9d58956e`。但 score-capable oracle
runner 和 EBench 可执行的 expert action stream / deterministic route 仍未冻结。旧的 native expert video/log
不是 EBench action stream；名字里带 `native_expert_oracle` 的历史 `result_info.json` 也是 `score=0.0` 且
`metric_score=[]`，不能当作标准答案已得分。因此下一步仍是不启动 Isaac，先定义并冻结 runner/action-source
contract；只有这个 contract 过审，才允许一次 bounded fallback score live。

2026-07-06 Gate1V-2b runner/action-source contract 审计也已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2b_runner_action_source_contract_20260706.json`。
结论仍是 no-live blocked。通俗解释：我们确认“考场会写分数文件”，但还没有“能把专家答案送进考场的正式答题器”。
现有两个 probe 都明确是 diagnostic/no-score；只读扫描 73 个 Franka open-door `result_info.json` 后，全部都是
`score=0.0`、`success_rate=0`、`metric_score=[]`，所以历史 run 也不能升级为专家已得分证据。下一步不该继续
fallback live，而是进入 Gate1V-2c：在 GenManip/EBench runner 层规划并实现 score-capable oracle runner，
用 fake-client tests 先证明它会 start job、reset、喂 action、处理 `reset_pending`、读取 `episode_result`
和 authoritative `result_info.json`。2c 通过前仍不释放 fallback score live；如果不走 2c，才转
`native_controller_research` 或 `asset_task_no_score_hardening`。

2026-07-06 Gate1V-2c score runner build plan 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_plan_20260706.json`。
通俗解释：这一步不是开门，也不是给模型打分，而是把“标准答案投递器”怎么做写清楚。正式分数只能来自
`post_episode_process -> episode_result -> result_info.json`；diagnostic `metric`、`done_info.info`、no-score
probe summary 或历史 `expert_oracle` 命名目录都不能当 benchmark score。

2026-07-06 Gate1V-2c runner code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_2c_score_capable_oracle_runner_code_checkpoint_20260706.json`。
GenManip 侧现在已有 Isaac-free `score_capable_oracle_runner.py` 和 fake-client tests；focused `7 passed`，
与 episode-result 相邻测试合跑 `12 passed`。白话讲，“标准答案投递器”的代码骨架已经能按正式判分路径工作：
start job、reset、喂 action、等 `reset_pending` 结束、拿 `episode_result`、查 authoritative
`result_info.json`，并且异常时不会误开 `score_claim_allowed`。但这仍不是 live，也不是专家已得分；下一步还要
用已冻结的 S0 `action_source.jsonl` 做 S1 formal score-chain smoke release review，再执行 bounded score-chain live。

2026-07-06 Gate1V-3 native-control research audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1v_native_control_contract_research_20260706.json`。
它也是 zero-live，不启动 Isaac，不算分。多角度 review 的一致结论是：当前 repo 和外部 GenManip 状态里，还没有一份
可以 claim 的 Lift2/R5a native control contract。现有入口要么仍是
`16D joint_position -> set_joint_position_targets -> world.step`，要么只是 `step_chunk` batching、`base_motion`
底盘通道、`ee_pose` / planner 预处理、`physics_hold_steps` 诊断开关、max-effort 修补或 no-score diagnostic
runner。白话讲：现在不是“native-controller 方向失败”，而是“还没有一张新的答题卡格式”；所以不能 release
`native_research_live`，更不能说 `Lift2 official baseline`、policy、leaderboard 或 `Expert Oracle Score`
已经解决。下一步如果走 native lane，必须先写一份 no-score `native_drive_target` 合同，明确
input/output schema、units、frames、target/applied/observed readback 和 fake-client harness，并证明它不是旧
joint-position 路线的换名版本。

给产品经理的当前边界：最近能“弄好”的最小评分闭环，已经把 Gate1V-2c runner 代码做到 fake-client
contract，但仍需要冻结 fallback score route 的 EBench action source；Lift2 native lane 则先只做到 research contract，不进入
score。较早能“判这条路不行”的点也分层：
如果未来 `native_drive_target` 合同仍回到同一 `set_joint_position_targets -> world.step`，或只能靠 diagnostic
hold、seed/offset、local hack 达标，就判当前 native-controller route 不能升级为 score route；这仍不是
LabUtopia-to-EBench 项目 no-go。

2026-07-06 历史交接结论更新：Gate 1U-A 曾从 A3j2 失败推进到 A3l pass。A3j2 的证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_reachability_live_20260706/aggregate_summary.json`：
在原 base/layout 下，5 个预注册 handle-front 候选全部 `MotionGenStatus.IK_FAIL`、0 trajectory、
`executed_steps_total=0`，所以这条“继续调把手点位”的路线已经停止。

A3l 随后验证了更关键的假设：问题是否主要来自 Lift2 机器人站位。证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_base_layout_live_20260706/aggregate_summary.json`。
5 个 base-layout child run 中有 3 个 planner 成功并生成非空 trajectory：
`A3L_XP10_YP30_KEEP_YAW` 70 points、`A3L_XP15_YP25_KEEP_YAW` 67 points、
`A3L_XP10_YP20_OFFICIAL_YAW90` 96 points。所有 run 仍是 0-action diagnostic，
`executed_steps_total=0`，所以它只证明“换合理站位后能规划到把手前”，不证明执行、接触、开门或得分。

给产品经理的白话解释：我们之前不是一直卡在“专家轨迹算不出分”，而是机器人连到把手前的第一段合法路线
都没有。现在 A3l 说明：如果按更接近 EBench official mobile-manip 的方式摆 Lift2，规划器已经能找到
到把手前的路线。下一步从“路线图存在”进入“机器人是否真能沿这条路线走到位”：A3k short execution
readback。A3r 这个“固定原站位只换手腕朝向”的 fallback 暂时不跑，因为 A3l 已经给出了更合理的通过分支。

A3k 的进入条件和停止线已经写清：只从 A3l 的 pass candidate 中选一个先做短执行；必须看到 nonzero
executed steps，final EE translation error <= `0.03m`，orientation angular error <= `15deg`，并且不能撞到
真实 table surface 或 door body。A3k 通过后才允许 A3m contact-readiness / no-contact guard；A3m 也不拉门、
不算分，只检查 gripper-to-handle clearance 和 finger/contact frame 是否支持进入 Gate 2 contact。

2026-07-06 A3k short execution readback package 已准备并通过 preflight：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/`。它只选
`A3L_XP15_YP25_KEEP_YAW` 一个候选，动作预算固定为 180 points，不允许边跑边加候选。产品口径上，
这一步要回答“路线图上的动作机器人能不能真的执行到把手前”。如果 runner joint readback 通过但 final
EE pose 读不出来，A3k 也不能算 pass；那会被归类为 readback instrumentation blocker，而不是开门失败。

A3k live 已执行，结果是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/result_compact.json`。
这次不是纯规划了：selected route 实际执行了 `142` 个 action steps，说明从 A3l 规划路线到 EBench
`step_chunk` 的动作链已经打通了一段。但 A3k 仍 blocked，不能进 A3m/contact。A3k1 offline audit 已经把
旧的 `state_joints_missing` 说清楚了：不是完全没有状态，而是 Lift2 的 `state.joints` 是 12D arm-only、
`state.gripper` 是 4D gripper-only，需要按 `[left arm, left gripper, right arm, right gripper]` 重新对齐
16D action。修正 comparator 后重算旧 trace，gripper 在容差内，但 arm joint 最大误差
`2.571020245552063rad`，远超 `0.02rad`。白话讲：机器人确实动了，但这一次没有走到最终关节目标；
同时 right-arm EE world-frame 和 full-run collision/contact 证据还没闭合。A3k2 的 code checkpoint 已经补了
split readback comparator 和 dual-arm EE debug obs；随后 A3k2 package postprocess closure 又把 live 前
stop-go 规则做成可测代码：它能消费
`debug.labutopia_open_door.evaluator_last_ee_pose_by_arm.right`，但会阻断非 world-frame EE、
final-step-only `physx_contact_debug`、full-run coverage mismatch 和缺 controller/applied-target debug。
后续 instrumentation expansion 已把 world EE、controller/tail 和 full-run contact 三条代码路径补齐，
因此允许同一 candidate 执行唯一 A3k2 live rerun；该 rerun 已执行，结果见下面 A3k2 live 段。

A3k2 instrumentation expansion 已先补第一小步：runner 新增显式 `--step-chunk-size`，默认行为不变；
未来 A3k2 package 可用 `--step-chunk-size 1` 逐 action 收集 `final_obs`，为 full-run telemetry 聚合提供
采样入口。但这不是 full closure。multi-agent review 明确两条边界：Lift2 right-arm EE world transform
必须用 `robot_base_right.get_world_pose()`，不能用 robot root pose；现有 `physx_contact_debug` 只证明
handle-contact 归因，不证明整段无 table/door/body 异常碰撞。下一步仍是补 world-frame EE transform、
full-run abnormal-contact aggregation 和 controller/applied-target aggregation，不能跑 live。

A3k2 instrumentation expansion 第二小步已经补了 world-frame EE code checkpoint：debug obs 现在保留 raw
`evaluator_last_ee_pose_by_arm.right` 的 `planner_fk_reference_frame` 语义，同时新增
`evaluator_last_ee_pose_reference_frame_by_arm.right` 和 `evaluator_last_ee_pose_world_by_arm.right`。
postprocess 也改成优先消费 explicit world-by-arm right EE，并拒绝“把 raw by-arm frame 字符串改成
world”的 shortcut。注意这仍不是 A3k2 live-ready：这个 world EE 是 evaluator target/cache 的 world
transform，物理实际到位还要 joint/tail readback 和 controller debug 证明；full-run abnormal-contact
aggregation 与 controller/applied-target aggregation 仍未闭合。

A3k2 instrumentation expansion 第三小步已经补了 controller/applied-target aggregation checkpoint：
runner 在 `--step-chunk-size 1` 下会从每步 final obs 的
`debug.labutopia_open_door.evaluator_last_action_application_debug` 聚合
`a3k2_controller_debug.v1`。其中 `final_applied_action_target_16d` 来自 evaluator 读到的
`applied_joint_position_target`，`tail_joint_error_series` 来自
`post_world_step_minus_target_abs_max`，不是 runner 用 action chunk 反推。通俗讲，仪表现在能回答
“EBench controller 最后实际收到了哪个 16D 关节目标、尾段离目标还有多远”。这一步仍不是 live-ready：
它只关闭 controller/tail 读数的代码路径；A3k2 还差 full-run abnormal-contact aggregation，不能用最后一帧
`physx_contact_debug` 冒充整段无异常碰撞。

A3k2 instrumentation expansion 第四小步已经补了 full-run abnormal-contact aggregation checkpoint：
runner 会在 `--step-chunk-size 1` 时把每步
`debug.labutopia_open_door.physx_contact_debug` 聚合成
`a3k_full_run_collision_contact_readback.v1`，并要求 `contact_sample_count == executed_steps`、
`missing_contact_sample_count == 0`。postprocess 也能消费 runner summary 顶层的 full-run schema；如果只有
final obs 的 `physx_contact_debug`，仍会被判为 final-step-only，不会被当成整段无异常碰撞。通俗讲，
三个仪表口径现在都 code-ready 了：right-arm world EE、controller/tail readback、full-run contact。
review 后口径再收紧一点：这个 schema 覆盖的是每步 `physx_contact_debug` 观测到的 unmatched contact
pairs，不是“宇宙级全场景无碰撞证明”；并且 `status=available` 本身不够，schema/method/list/errors
形状异常的 sample 会被计为 invalid/missing，不会当 clean sample。它仍不是 A3k2 pass，因为还没有消耗唯一 live rerun；下一步应该固定同一个
`A3L_XP15_YP25_KEEP_YAW` candidate，带 `--step-chunk-size 1` 和 debug env 做一次 A3k2 live rerun，
然后用实际 live summary 判定是否通过。

A3k2 same-candidate live rerun 已执行，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_same_candidate_live_rerun_20260706/result_compact.json`。
这次固定同一个 `A3L_XP15_YP25_KEEP_YAW` candidate 和 `A3J2_CORRECTED_CENTER` route，端口 `18121`，
没有换候选、没有 contact、没有 micro-pull、没有 score。关键事实是：动作链实际执行了 `143` steps，
final planner record 仍是 `a3j2_corrected_center`，所以它不是“没跑起来”。

但 A3k2 没通过，状态是
`BLOCKED_A3K2_SAME_CANDIDATE_INSTRUMENTED_READBACK_NOT_READY_FOR_A3M`。原因不是机器人已经证明到不了把手，
也不是 contact/door/score 失败，而是 instrumentation 没真正进入 live observation：原始 step obs 只有
`instruction/state/video`，没有 `debug.labutopia_open_door`。root cause 已经定位到 generated Lift2
candidate 的 task name：它是
`ebench/labutopia_lab_poc/lift2_candidate/a3l_base_layout/a3l_xp15_yp25_keep_yaw`，而 debug gate 只接受
leaf 为 `level1_open_door*` 的任务名，所以即使环境变量已经设置，debug obs 仍被跳过。GenManip 已用 TDD
补了这个 gate：新增 regression test 先失败为 `KeyError: debug.labutopia_open_door`，修复后 focused
`1 passed`，debug-state suite `29 passed`。对应结构化证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_generated_task_name_debug_gate_closure_20260706.json`。

产品口径上，A3k2 的结论是：路线已经能执行一段，但当时仪表没有进观察包，所以不能判定到位，也不能进
A3m contact-readiness。A3k2b 已经把这个更小的问题闭合：证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2b_debug_gate_validation_20260706/result_compact.json`，
状态是 `PASS_A3K2B_GENERATED_TASK_NAME_DEBUG_GATE_READY_FOR_A3K2_READBACK`。这次只执行 1 个 diagnostic
action point，预期 runner exit code 是 `2`，因为 `execution_action_points_limited:1/142` 主动阻断了完整执行。
但 postprocess 已经证明 generated Lift2 candidate 的 reset/step live obs 里有
`debug.labutopia_open_door`，并且能读到 right-arm world EE、controller/tail debug 和 full-run contact
sample plumbing。下一步不是换候选乱跑，而是 exactly 1 次 full A3k2 same-candidate readback rerun。
完整“弄好”的产品节点仍是 Gate 5：Gate 4 先证明 micro-pull 能带动 door joint，Gate 5 再记录
`PASS_EXPERT_ORACLE_SCORE_RECORDED`。

面向 PM 的预计推进线如下：

| 阶段 | 白话问题 | 到这一步能说明什么 | 不能说明什么 |
| --- | --- | --- | --- |
| A3k2b | 仪表有没有装进考场？ | 已通过：generated Lift2 task 的 live obs 能看到 right-arm EE、controller/tail、full-run contact 这些读数 | 还不能说机器人到位、接触、开门或得分 |
| A3k2c | 机器人沿同一条路线走完了吗？ | 已执行 exactly 1 次 full same-candidate readback，trace 里能看到 joints/gripper/contact/controller 关键证据 | 现在 runner summary 和 postprocess readback 口径不一致，不能直接判 selected candidate 失败 |
| A3k2d | 这把“尺子”读数一致吗？ | 只用现有 trace 离线重算；闭合后才能判断这条 candidate 是通过还是失败 | 不消耗新的 live，不接触、不拉门、不算分 |
| A3k fallback | 另外两个已规划成功的站位候选有没有可用的？ | 已完成：两个 fallback 都在闭合读数下失败，A3l base-layout route family 到 no-go review | 不能扩大成 DryingBox 全局打不开；还要评审 A3r 或上层合同 |
| A3m | 到把手前以后姿态能不能安全接触？ | 如果通过，才进入 Gate 2 contact | 还不是拉门 |
| Gate 4 | micro-pull 是否真的带动 door joint？ | 这里通过，才接近“工程上会开门” | 还不是 EBench 专家分闭环 |
| Gate 5 | Expert Oracle Score 是否被 EBench metric 记录？ | 这里通过，才算“评测口径弄好” | Gate 5 前的 `score=0.0` 不能当 expert 失败 |

A3k2c full readback 已按这个规则执行完，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2c_full_readback_rerun_20260706/result_compact.json`。
白话结论：这次不是“仪表没装上”，也不是“碰撞证据缺失”。它完整执行了 `142` steps，final planner label
仍是 `a3j2_corrected_center`；trace 最后一帧能看到 Lift2 的 `state.joints` / `state.gripper`；
full-run contact coverage 是 `142/142`，没有真实 table/door/body 异常接触。A3k2d 前的旧 runner summary
仍报 `state_joints_missing`，postprocess 的旧 `readback_schema_closed=false` 也沿用了这个 summary 字段。
A3k2d zero-live readback consistency audit 已完成，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2d_readback_consistency_audit_20260706.json`。
通俗讲，这一步先校准“验收尺子”：旧 runner summary 报 `state_joints_missing`，但最终 trace 里其实能读到
Lift2 的 12D joints 和 4D gripper；postprocess 现在用 final worker obs + controller target 重算，schema
已经闭合。闭合后的结果显示 selected candidate 真的没到预接触位：joint error `2.570956rad`，right-arm
EE 位置误差 `0.527791m`，姿态误差 `166.862deg`。所以这个 candidate 停止，不能进入 A3m；下一步才允许
A3k bounded fallback，最多再看 A3l 剩余两个已规划成功候选。

A3k bounded fallback 也已经按这个规则跑完，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_bounded_fallback_readback_20260706/result_compact.json`。
白话结论：剩余两个“看起来能规划到把手前”的站位，真实执行后也没有到位。`A3L_XP10_YP30_KEEP_YAW`
执行了 `152` steps，读数闭合、无异常接触，但 joint error `1.133121rad`、EE 位置误差 `0.342726m`；
`A3L_XP10_YP20_OFFICIAL_YAW90` 执行了 `178` steps，读数闭合、无异常接触，但 joint error
`2.027691rad`、EE 位置误差 `0.312915m`、姿态误差 `89.758deg`。所以 A3l 这组三个站位候选全都不能进
A3m。下一步不是接触、拉门或算分，而是做 A3l route-family no-go review：决定转 A3r fixed-layout
route redesign，还是回到更上层的机器人控制/任务布局合同。

2026-07-06 route-family no-go review 已完成，多角度结论一致：A3l 这组站位路线族已经不应该继续调参。
白话说，三条路线都不是“没规划出来”，而是“规划器说能走，但机器人真实执行后离把手前目标还差很多”。
三次读数都闭合、异常接触都是 0，所以问题不像桌子/门碰撞，也不像材质、相机或渲染问题；更像
planner trajectory、16D action、controller applied target、final joints/EE readback 之间的合同没有闭合。

2026-07-06 E1 controller/execution audit 已完成 0-live 审计，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e1_controller_execution_contract_audit_20260706.json`。
通俗讲，机器人不是“没收到动作”：三条路线的 controller target sample 数都等于 executed steps，
说明动作每一步都下发了；也不是“撞到了什么”：contact 全程 clean。更像是动作下发太快或 controller
跟踪合同没闭合：每个 planner point 默认只跑一次 `world.step()`，但 Lift2 关节速度上限是 `2.0rad/s`，
而轨迹相邻点最大约 `0.035-0.043rad`。所以 E2 不能直接重跑 DryingBox，而要先做一个最小 controller
reference probe。

2026-07-06 E2 code-ready checkpoint 已完成，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_code_checkpoint_20260706.json`。
E2 live 也已执行完，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_live_20260706/result_compact.json`。
当前 handoff 的下一步不是再跑 live，也不是重跑 DryingBox candidate。通俗讲，已经让 Lift2 在没有
箱子/把手交互的情况下做了一个非常小的右臂关节动作：5 步保持原位、5 步小幅 ramp、60 步 terminal
hold。这个测试只校准“机器人和尺子”：机器人是否收到了 16D `joint_position`，最后读回来的
`state.joints/state.gripper` 是否真的到目标。结果显示动作有下发，但读数没有到目标。

产品口径的停止线如下：

| E2 结果 | 给 PM 的解释 | 下一步 |
| --- | --- | --- |
| `BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED` | 连原地保持或最终 hold 都读不回目标，说明不是 DryingBox 难，而是 Lift2 controller/action/readback 合同没闭合 | 停止 DryingBox oracle，先修底层控制链 |
| `PASS_E2_REFERENCE_RETIMING_REQUIRED` | 最终 hold 能到，但 ramp 中间帧追不上，说明动作可能下发太快 | E3/E4 必须带 explicit retiming / terminal-hold contract |
| `PASS_E2_LIFT2_CONTROLLER_REFERENCE_READY_FOR_E3_E4` | 这个小动作从 ramp 到 hold 都能到位，说明 Lift2 基础执行链可继续验证 | 只解锁 E3 static compute 和 E4 one-segment precontact，不代表开门或得分 |

本次实际命中第一行，所以 E3/E4 暂停。

下面 Gate 1R / Gate 1T / A-lane 文字是历史交接链，说明为什么一路收敛到 E2；它不再是当前下一步。

下一步已经规划为 E0-E6，不再继续给 A3l 加站位或 offset：

| 阶段 | 最多 live | 给 PM 的白话问题 | 通过后说明什么 | 失败时怎么停 |
| --- | ---: | --- | --- | --- |
| E0 evidence freeze | 0 | 已经试过的三条路线证据是否封账？ | 可以避免重复跑同一类失败 | 缺读数就先补证据 |
| E1 controller/execution audit | 0 | 规划出的动作有没有被 Lift2 按同一种语言执行？ | 找到明确可修/可验证点才允许 live | 找不到可修合同，当前路线直接停 |
| E2 Lift2 controller reference / retiming probe | 1 | 不碰 DryingBox，只让 Lift2 做 5 个 no-op、5 个右臂小 ramp、60 个 terminal hold，能不能到位？ | 如果 hold 能收敛，说明后续 DryingBox 要加 retiming/hold；如果 no-op/hold 都不到位，先修 controller/action contract | 不能直接重跑 DryingBox candidate |
| E3 DryingBox EBench-style compute | 0 | 用 EBench 的方式重新算 DryingBox 把手前目标是否自洽？ | 目标、手臂、frame、action schema 静态闭合 | schema 不闭合就不 live |
| E4 one-segment execution | 1 | 只跑到 DryingBox 把手前，不接触不拉门，能不能到位？ | 这是最早能说“新思路有戏”的节点 | E2 过但 E4 不到位，就停这个 handoff |
| E5 full oracle dry run | 1 | 多段到接触前是否仍稳定？ | 通过后才进 A3m contact-readiness | 漂移或不跟随就停在 trajectory/controller |
| Gate 4 | 每层 1 | 是否能真实带动 door joint？ | 工程上接近“能开门” | 任一层失败就停在对应层 |
| Gate 5 | 1 | EBench metric 是否记录 Expert Oracle Score？ | 这才算评测口径闭环 | 门动了但没分，则查 metric/success condition |

2026-07-06 历史交接结论：Gate 1R + Gate 1S 已经把当时的精确定义合同推进到 bounded no-go 建议点。
当前合同指 `EBench + Franka + LabUtopia DryingBox + 当前任务布局 + mesh-open-face near route`。
Gate 1R 的 R1/R2/R3/R4 没有产生 `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`；
Gate 1S 的 `S1_TASK_LAYOUT_NORMALIZATION` 也没有恢复 handle-front near reachability。允许交接口径是：
当前合同没有产生 scoring-eligible expert route，所以 Gate 2/contact/micro-pull/`Expert Oracle Score`
继续 blocked。不能说 DryingBox 全局打不开、LabUtopia 资产不能进 EBench、`Expert Oracle Score`
失败或官方分数失败。

下一步已经规划为
[`2026-07-06-eos2-gate1t-contract-fork-route-generator.md`](../superpowers/plans/2026-07-06-eos2-gate1t-contract-fork-route-generator.md)。
它不是继续扫 offset，而是新开 Gate 1T contract fork。推荐优先 lane 是
`C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR`：保持 Franka、当前 layout、native DryingBox 和 EBench metric
不变，只把 route generator 改成 EBench 原生 `microwave` 风格的 `custom_motion` 模式，也就是
`robot_frame` staging + `object_frame` waypoints，让 runtime/curobo 逐段现算。这个 lane 的硬边界是
`max_native_pattern_routes=3`、`max_selected_live_route_count=1`。如果它失败，下一步只能转
`A_LIFT2_ROBOT_CONTRACT_FORK`、`B_TASK_LAYOUT_CONTRACT_FORK` 或最终 bounded no-go；不要继续从
Gate 1R R1-R4 或 Gate 1S S1 的失败证据跑 contact、close-hold、micro-pull 或 score。

Gate 1T-C0 / C1 交接：native pattern extraction 和 route candidate manifest 已建立。C0 确认
EBench `microwave` 是 `custom_motion` + `object_frame` / `robot_frame` / `pending` 的
task-level waypoint 模式；C1 预注册 3 条 root-object-frame route candidate。当时把
`rel_object_uid` 固定为 `obj_DryingBox_01`，但后续 C2b live 已证明这个 root UID 在当前
LabUtopia articulated-object setup 后不在 `scene.object_list`，不能被 native `custom_motion`
object-frame resolver 直接消费。因此 C2b 不是 route no-go，而是 resolver mismatch 证据。

2026-07-06 C2a runner capability audit 已推进到 code-ready。新的结构化证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2_runner_capability_audit_20260706.json`，
status=`CODE_READY_GATE1T_C2_NATIVE_ACTION_PATH_RUNNER_NOT_LIVE_EVIDENCE`。意思是：EBench 原生
`custom_motion` 范式已经确认，3 条候选也已经预注册，现在 GenManip worktree 里也新增了最小 runner：
`standalone_tools/labutopia_poc/native_action_path_runner.py`，单测
`tests/labutopia_poc/test_native_action_path_runner.py` 覆盖“选 1 条 route -> reset -> planner
include trajectory -> action chunk -> step_chunk fake-client replay -> summary 分类”。已跑验证：
runner 单测 `5 passed`，相邻 planner contract 组合测试 `29 passed`。runner 现在还接受 `--run-id`，
并把 run_id 写进 summary，让 live 输出和 server submit/job logs 对齐。

2026-07-06 C2b live 已实际跑完，证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_native_pattern_route_live_20260706/`。
它用端口 `18107`、run_id `eos2_gate1t_c2b_c1_root_direct_native_pattern_20260706_0001`，只跑
`C1_ROOT_DIRECT_NATIVE_PATTERN`。结果是 `executed_steps=0`，`robot_frame` 报 unsupported，
`obj_DryingBox_01` root object-frame 报 not found。因此 C2b 的 compact status 写成
`LIVE_BLOCKED_RESOLVER_MISMATCH_NOT_ROUTE_NO_GO`：它证明 live runner 链路已经打到 Isaac / EBench，
但还不能证明 C lane 不可达。

2026-07-06 C2c resolver-closure live 也已跑完，证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2c_resolver_closure_live_20260706/`。
C2c 的修正是：`robot_frame` 补 `rel_arm=default`，`object_frame` 改用当前
`scene.object_list` 中可解析的 `obj_DryingBox_01_handle`。这一次 resolver 层通过了：
`robot_frame_staging_microwave_style` 规划成功并生成 `44` 个 action points；两个 handle
`object_frame` target 也都解析成 world target。真正失败点变成 cuRobo planner：
`handle_object_staging_085` 和 `handle_object_near_045` 都是
`MotionGenStatus.IK_FAIL`、`trajectory_point_count=0`，所以 Gate 2/contact 和
`Expert Oracle Score` 继续 blocked。

但 C2c 仍不能直接宣布 `C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR` no-go。C2d 只读审计已经写入
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2d_target_frame_equivalence_audit_20260706.json`：
C2c 的 handle local `Y+` 在 live 中映射到 world `X+`；C2c near target
`[0.5725623383522034, 0.24876323342323306, 1.1085914373397827]` 距离 mesh/open-face
参考的 handle-front approach-near target
`[0.47978996139738445, 0.3107189912618622, 1.1085915534527668]` 约 `0.1116m`。
通俗讲：C2c 确实打到了一个可解析的把手坐标，但它不一定是我们想要的“正面把手前方”。

下一步已经收敛为
[`2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md`](../superpowers/plans/2026-07-06-eos2-gate1t-c2d-target-frame-equivalence-closure.md)。
执行边界是：先用 C2d 审计确认目标点是否等价；如果等价，C2c 的 IK_FAIL 就足以停止 C lane；
如果不等价，C2e 也不能直接 live。C2e 第一步必须补 raw `frame_in_world`、raw
`pose_frame_to_world` 和 `adjust_target_pose_by_embodiment` 后的 adjusted target dump，推导出能在
adjusted target 下复刻 intended world target 的 local 坐标；坐标仍 underdetermined 就停止，不启动
Isaac。现在 C2e resolver dump 已补齐，证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2e_resolver_dump_live_20260706/`；
它记录了 handle frame、raw target 和 adjusted target 三层坐标。基于这份 dump，C2e coordinate
derivation 已从 blocker 推进为
`PASS_C2E_EQUIVALENT_TARGET_COORDINATES_DERIVED_READY_FOR_C2F_SINGLE_LIVE`：
`approach_near` 的 object-frame local translation 反推为
`[-0.061955757838629166, -0.020816618383194208, 1.1611298411651205e-07]`，forward check
回 mesh/open-face 正面目标的误差约 `5.55e-17m`，远小于 `0.01m` 门槛。
orientation 边界也已写清：C2f 保持 EBench-native route 的 local orientation
`[0.7071, 0.0, 0.0, 0.7071]`，它和 C2e live 的 adjusted orientation 完全一致，但和旧
mesh-open-face runtime orientation 相差约 `90deg`。所以 C2f 如果失败，能停止“当前 native-route
orientation 合同”，不能扩大成“任何姿态都不可达”。

为了避免把“坐标证明”和“真实 live rerun”混在一起，后续唯一 live 节点命名为 C2f：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_live_20260706/`。
C2f 已按唯一 route `C1_RESOLVER_CLOSED_EQUIVALENT_TARGET_NATIVE_PATTERN` 跑完，且 Gate 1
只执行 staging + `approach_near`，没有把 contact target 混进 near-reachability 判定。结果是：
`robot_frame_staging_microwave_style` 仍成功并生成 `43` 个 action points；真正等价正面目标
`handle_object_approach_near_equivalent_035` 命中
`[0.4797899613973845, 0.3107189912618622, 1.1085915534527668]`，但 cuRobo 返回
`MotionGenStatus.IK_FAIL`、`trajectory_point_count=0`、`executed_steps=0`。compact 证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_live_20260706/result_compact.json`，
status=`LIVE_BLOCKED_C2F_EQUIVALENT_TARGET_IK_FAIL_STOP_C_NATIVE_ROUTE_CONTRACT`。

因此当前 C lane 的结论已经收敛：停止
`C_NATIVE_ORACLE_PATTERN_ROUTE_GENERATOR`，不要继续临场新增 route、扫 offset、改 Franka
base/layout、关闭 collision 或开启 score。推荐下一步进入 `A_LIFT2_ROBOT_CONTRACT_FORK`，
因为它直接对应我们最终要支持 EBench official Lift2 baseline 的产品目标；`B_TASK_LAYOUT_CONTRACT_FORK`
作为次级 fallback，`W_FINAL_BOUNDED_NO_GO` 只在 A/B 被拒绝或失败后使用。
Gate 1U-A 的计划已新增：
[`2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md`](../superpowers/plans/2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md)。
它先做 Lift2/R5a 静态合同审计，再做单次 live schema/action probe；这两步都不是 expert score，
只是在确认“官方机器人口径的考场和动作语言是否可用”。
A0 静态审计已通过并写入
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a0_lift2_static_contract_audit_20260706.json`：
`robot_type=manip/lift2/R5a`、`action_shape=[16]`、metric 仍是
`obj_DryingBox_01/RevoluteJoint` 的 `check_joint_angle`。边界是：这个 config 使用历史
LabUtopia scene path，不是 AAN-11 wrapper，所以它只能作为 Lift2 robot-contract probing 入口。

A1/A1a/A1b/A1c 现在已经收口到更清楚的状态。第一次 A1 live probe 的确 blocked：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/result_compact.json`
记录为 `LIVE_BLOCKED_A1_RESET_RESULT_PENDING_ASSETS_ROOT_OVERRIDE_MISSING_STOP_BEFORE_A2`，原因是 worker
去旧 overlay root 找 `robot_usds/lift2/robot.usd`，而 Lift2 robot USD 实际在 composite root。

A1a 随后已把 effective assets root 固定到
`$GENMANIP_WORKTREE/saved/assets`，并确认它指向 composite root：
`/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets`。
A1b corrected live 已证明 Lift2 能 reset、返回 observation/camera、接收三种 16D action dialect，并返回
reward/success fields；A1b 唯一 blocker 是 logging metadata 缺字段。A1c 只补证据记录，不改 route、
oracle 或 score，fresh live 后 schema rows 全部 PASS。最新 compact evidence 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_lift2_live_schema_probe_logging_closed_20260706/result_compact.json`，
status=`PASS_A1C_LIFT2_LIVE_SCHEMA_ACTION_LOGGING_PROBE_READY_FOR_A2_ORACLE_DESIGN`。

通俗讲：Lift2 现在已经能“进考场、看见题目、交一组动作、把交卷记录写完整”。这只说明工程入口链路通了，
不是“已经会开门”，也不是 official baseline score。下一步允许进入 A2 Lift2 oracle / retarget design review；
不允许直接算 `Expert Oracle Score`。

A2 也不会一上来启动 Isaac 或算分。它拆成三道零 live 门：A2a 先选唯一 oracle path，推荐先做
`LIFT2_SCRIPTED_ORACLE`，并明确输出必须是 Lift2/R5a `16D joint_position`；A2b 静态审计 DryingBox
joint、handle frame、front approach pose、contact pose 和 pull direction，避免再重复 target-frame
混乱；A2c 做 translator dry contract，证明生成的动作 payload 能被 probe/runner 接收。只有 A2a/A2b/A2c
都过，才允许 A3 一次 selected-route live 去测 Gate 1 near reachability。

2026-07-06 A2a/A2b/A2c 现在已作为零 live evidence 落盘。A2a 选定
`LIFT2_SCRIPTED_ORACLE`，拒绝直接 Franka replay；A2b 固定了把手正前方目标，A3 只跑 front approach，
contact 留到 Gate 2；A2c 补了 16D dry contract，并给 `native_action_path_runner.py` 加了
`--expected-action-dim 16` 安全网，避免把 7D Franka action 混进 Lift2。A3 single-live package
也已经准备并按规则只跑一次；它只测 Gate 1 near reachability，不测 contact、pull 或 score。

2026-07-06 A3 的实际结果已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3_lift2_oracle_single_live_20260706/result_compact.json`。
normalized status 是
`LIVE_BLOCKED_A3_LIFT2_ORACLE_PLANNER_UPDATE_UNAVAILABLE_STOP_BEFORE_GATE2`。白话解释：A3 能 submit，
worker reset 也完成了，但两条 waypoint 在 planner update 阶段都失败，没有生成 trajectory/action chunk，
所以 `executed_steps=0`。这不是接触失败、抓取失败、门角失败、score 失败，也还不是“Lift2
route 几何不可达”的结论。

A3a root-cause review 也已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3a_planner_update_root_cause_review_20260706.json`。
当前强线索是 A3 route/summary 都落成了 `arm=default`，而 Lift2/R5a 是 dual-arm embodiment，
planner 在代码里分成 `left_planner` / `right_planner`。因此下一步不是继续 live sweep，
而是先把 dual-arm arm contract 写清楚：明确选 `left` 或 `right`，让 A2c dry contract 拦住缺省
arm / rel_arm，再准备 revised A3。若 dry 仍落到 `default` 或 revised A3 仍是
`planner_update_unavailable`，就停止 live，把问题归为 Lift2 dual-arm planner API / route contract
未闭合；若进入 cuRobo 后才 `IK_FAIL` / 0 action points，才停止当前 selected route 并回到 A2
route design review。

A2c addendum 和 A3b dry closure 现在已经把这个问题推进了一步：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2c_lift2_dual_arm_route_guard_addendum_20260706.json`
新增 `--required-arm right` runner 防线；`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3b_lift2_right_arm_dry_contract_20260706/result_compact.json`
记录 `PASS_A3B_LIFT2_RIGHT_ARM_DRY_CONTRACT_READY_FOR_REVISED_A3_SINGLE_LIVE`。依据是 EBench 原生
microwave/open-door 风格配置走 `motion_list.right`，robot-frame staging 用 `rel_arm:right`。dry check
结果是 `route_validation_blockers=[]`、`action_blockers=[]`、两步 action 都是 16D。白话讲：标准答案
已经改成 Lift2 右臂能读懂的格式，但还没证明 live planner 真能到门前。

2026-07-06 A3c revised right-arm live 已执行一次，证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3c_lift2_right_arm_single_live_20260706/result_compact.json`。
状态是
`LIVE_BLOCKED_A3C_LIFT2_RIGHT_ARM_START_STATE_WORLD_COLLISION_STOP_BEFORE_GATE2`。白话讲：这是进步，
但不是“会开门”的进步，而是诊断层进步。A3c 已证明 revised route 确实走了 `right` arm，两个
waypoint 的 world refresh 成功，旧的 `arm=default / planner_update_unavailable` 问题闭合了。新的
第一 blocker 是 reset/start-state collision：cuRobo 还没判断把手目标可不可达，就先认为 Lift2
某个 collision sphere 和 table mesh 相交，`sphere_index=17`，`executed_steps=0`。

因此下一步不是继续扫 offset、contact pose 或直接算分，而是 A3d start-state collision review：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3d_right_arm_start_state_collision_review_20260706.json`。
A3d 只允许 read-only / zero-live：映射 sphere 17 到具体 Lift2 link/collision sphere；核查 reset 后
base、joints、EE pose；审阅 table collider 是支撑面、桌体还是过宽 mesh；把 sphere bottom、radius
和 table top/AABB 放到同一个 planner reference frame 算 clearance。只有 A3d 解释清楚，并且 A3e
dry/preflight 证明修正不是 blind table ignore，才允许 A3f 单次 revised live。否则就停止当前
Lift2 reset/layout/collider contract，回到 reset/base/joint/table-collider review。

2026-07-06 A3d 当前执行结论：A3c trace 已经能读出 reset state，Lift2 base 基本在原点，
`state.joints` 是 12 维，`state.gripper` 是 4 维，两组 `state.ee_pose` 存在；planner response
则稳定指向同一个 table obstacle 和 `sphere_index=17`。但 A3d 仍不能直接判定“物理真的撞桌子”
或“可以忽略桌子”，因为还缺同一 `planner_reference_frame` 下的 table AABB/top 与 sphere clearance。
因此先补 A3e diagnostic runner checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_runner_checkpoint_20260706.json`。
这一步只让 `native_action_path_runner` 能把 `support_surface_uid=table` 和 A3c 的 table obstacle path
透传给 planner，从而让已有 GenManip clearance builder 输出 `support_surface_clearance_records`。它不改变
action、不启用 table ignore、不允许 contact/micro-pull/score。

A3e diagnostic request package 已准备在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_request_20260706/`。
这个包仍然用 A3B right-arm route，但 runner 命令强制 `--max-action-points 0`，所以即使 planner
意外生成轨迹也不会执行 `step_chunk`。它的唯一目的，是判断能否产出同 frame 的
`support_surface_clearance_records`，并据此决定 A3f 是否允许。

2026-07-06 A3e diagnostic request 已执行，结论是 **A3f 不允许**。这次不是“没拿到证据”，而是拿到了
同 frame 证据：2 条 `support_surface_clearance_records` 都是 `planner_reference_frame` 对
`planner_reference_frame`，`clearance_margin_m=-0.6237133788083942`，
`physically_intersecting_support_surface=true`，`planner_only_support_surface_exclusion_allowed=false`。
通俗讲：planner 看到的 Lift2 某个碰撞球确实在桌子碰撞体的高度范围里，不能把桌子简单 ignore
掉继续跑。raw runner classification 仍是旧泛化标签 `BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`；
handoff 采用 canonical status：
`A3E_SUPPORT_SURFACE_CLEARANCE_DIAGNOSTIC_EXECUTED_NO_GO_A3F_BLOCKED_RESET_LAYOUT_COLLIDER_CONTRACT`。
下一步不是 A3f、contact、micro-pull 或 score，而是回到 Lift2 reset/base/joint/table-collider
contract：查初始摆放、关节 seed、桌子碰撞体是不是整桌过大，以及 sphere 17 到具体 Lift2 link 的映射。

2026-07-06 A3g 已把上面这句话拆清楚：`sphere_index=17` 已映射到 Lift2/R5a right-arm `link6`
sphere0，不再是未知碰撞球；它的半径也和 R5a cuRobo config 对得上。更重要的是，A3e 撞到的 table
path 是完整视觉桌体 mesh，这个 mesh 在 USD 里只有 `MaterialBindingAPI`，没有 `PhysicsCollisionAPI`；
真正有物理碰撞声明的桌面是 `/World/labutopia_level1_poc/obj_table/surface/mesh`。白话讲：当前 planner
像是把“看得见的整张桌子模型”也塞进了障碍物名单，而不是只用“真实物理桌面”来判断碰撞。所以接下来
A3h 不是把桌子整个拿掉，也不是继续调专家动作，而是做一个 0-action preflight：从 planner world 里
只过滤/替换这个非 physics 的视觉 table mesh，同时确认真实 table surface 还在。如果 A3h 后仍然撞真实
桌面，再进入 A3i 查 Lift2 初始 base / 12D joint seed；A3h/A3i 通过前，A3f 和后面的开门/算分都不能跑。

2026-07-06 A3h live 0002 已跑完，PM 口径要更新成：旧的“起跑就撞桌子”问题已经不再是当前 summary
里的第一硬门，因为第一段 `lift2_right_robot_frame_staging_microwave_style` 已经 planner 成功并生成
`84` 个点；但这还不是执行成功，`executed_steps=0`，没有 readback。新的第一硬门是第二段
`lift2_right_handle_front_approach_near_035` 返回 `MotionGenStatus.IK_FAIL`、0 points。下一步不是算
`Expert Oracle Score`，也不是继续无限调 waypoint，而是 A3j：固定 handle frame、正面方向、robot base、
joint seed，只枚举小集合 pregrasp/orientation 来判定 Lift2 right arm 到底够不够得到把手前目标。如果
这轮仍全部 `IK_FAIL`，就停止当前 route，转 layout/base 或 official Lift2 placement 口径。

2026-07-06 A3j 的第一步已经先做 zero-live target equivalence review，发现还不能直接进入 IK 小矩阵：
A2b 预期的 handle-front world target 是 `[0.47979, 0.31072, 1.10859]`，但 A3h runtime resolver 实际送给
planner 的 target 是 `[0.43479, 0.31072, 1.10859]`，world X 差 `4.5cm`。这说明 A3h 的 IK_FAIL 可能打在
“偏了 4.5cm 的点”上，不能直接解释成 Lift2 够不到 intended target。下一步先做 A3j1 corrected target
dry forward-check：把 local Y 补 `+0.045m` 后能不能回到 intended world target；过了再做最多 5 个
candidate 的 bounded reachability。

A3j1 forward-check 已经通过：用 A3h runtime frame，把 local Y 从 `-0.0208` 改到 `0.0242` 后，算出的
world target 和 A2b 预期目标只差约 `3.2e-09m`。这说明“目标点位偏 4.5cm”的问题已经有可验证修正。
但这仍然只是点位数学闭环，不是机器人够得到。下一步才是 A3j2：以这个修正点为中心，最多 5 个候选，
跑 bounded reachability。

A3j2 候选矩阵也已经预注册：只允许 5 个候选，不允许边跑边加。5 个候选分别是 corrected center、沿
approach line 远/近各 `1cm`、world X 左右各 `5mm`。如果这 5 个都还是 `IK_FAIL` 或 0 trajectory
points，就停止当前 route，不再继续扫 offset。

这 5 个候选已经打包成 runner 可读的 route manifest。后续测试只允许从这 5 个 route-id 里选，不能现场
加第 6 个：`A3J2_CORRECTED_CENTER`、`A3J2_APPROACH_FARTHER_010`、`A3J2_APPROACH_CLOSER_010`、
`A3J2_WORLD_X_PLUS_005`、`A3J2_WORLD_X_MINUS_005`。

A3j2 live 后这 5 个候选全部失败，所以没有继续加 offset。随后 A3l 把问题改成“Lift2 站位是否不对”，
并只改 `robots[0].position/orientation`。A3l live 结果已经通过：3/5 个 base-layout 候选有 planner
success 和非空 trajectory。这个结果把下一步从 A3r fallback 改成 A3k short execution readback：先验证
一个 A3l pass candidate 能不能真的执行到把手前。A3l 仍不能被解释成 contact、door opened、
`Expert Oracle Score` 或 policy score。

面向 PM 的判定顺序：当前合同 no-go 已经在 Gate 1S 成立；C2b 判定出 resolver mismatch；
C2c 证明 resolver closure 但暴露 target-frame equivalence 未闭环；C2d/C2e 把正面目标坐标算准；
C2f 证明在这个等价正面目标下当前 Franka/current-layout/native-route orientation 合同仍 IK_FAIL。
所以现在不是“还没弄好继续试”，而是 C lane 已经按规则止损，A/Lift2 lane 的入口合同过了 A1c，
A2 过了 dry design，A3 暴露 planner-update/dual-arm arm contract，A3b 已用 right-arm dry package
把下一次 live 的输入修正好。
预计节点要这样看：A1c 通过只说明工程入口可用；A2/A3b 证明存在合法 Lift2 right-arm oracle / dry
contract；A3d/A3e 先关闭 start-state table collision，其中 A3e 当前只是 support-surface diagnostic
能力 checkpoint；A3f/Gate 1 才验证能不能到把手正前方安全位；
Gate 2 验证是否真的接触把手；Gate 3 验证 close-hold / retention 是否抓稳；Gate 4 的 micro-pull /
door joint readback 才接近“工程上能开门”；Gate 5 记录 `PASS_EXPERT_ORACLE_SCORE_RECORDED` 才算
“评测口径弄好”。任何一层失败都在该层停止，不能跳到后面的 contact、micro-pull 或 score。

2026-07-05 Expert Oracle Score 前置链路输入：EOS-2 曾完成 Task 5K-A staged-combination 单候选 live
probe，并把后续 5L/5M 的 handle-frame 调整问题暴露出来。compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`。
`x_m002_ori_z_p02` 不是 IK blocker：post-replay replan 成功，选中的 waypoint 正确，并生成
`40` 个可执行 action point；close-hold 也执行 `15` 步并达到 joint target。真正失败点仍是
hand/handle retention：tail window 内 bilateral overlap、required-role near 和 required-role
PhysX contact 都是 `0`，15/15 记录都是 `AABB_OUTSIDE_CONTACT_FRAME`。它相对 5J-F 把双指
world Y gap 各补回约 `1.8mm`，但 world X gap 各恶化约 `0.6mm`；相对 5J-A 则是 X gap 更好、
Y gap 更差。因此这轮只说明“组合候选把 gap tradeoff 暴露清楚”，不是“已经抓住”。现在仍不能进入
micro-pull、door metric 或 `Expert Oracle Score`。

为什么下一步不是继续硬套旧 expert 轨迹：EBench 自己的 `microwave` 任务也不是把某个
`skill_trajectory` 文件逐帧 replay。它在 task YAML 里写 task-level manual
`custom_motion` waypoints，其中包含相对微波炉的 `object_frame` 目标，也包含
`robot_frame` staging；runtime 再把这些点转成 world/robot pose，并用 cuRobo 在线规划
joint trajectory。DryingBox 下一步应学习这个范式：从 handle/contact frame 生成一组可审阅
候选点，逐个经过 planning、execution 和 readback 验证，而不是把单个 absolute IK target
或 LabUtopia 旧轨迹继续硬调。这个下一阶段已固化为
[`2026-07-05-eos2-contact-frame-handle-frame-target-generation.md`](../superpowers/plans/2026-07-05-eos2-contact-frame-handle-frame-target-generation.md)。
2026-07-05 当前已经生成 5L prepared review manifest：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_review_20260705_5l_candidates.json`。
它只登记单个保守候选 `5l_cf_handle_right_025_clamped_xy12_zp02`，不是 live evidence；
下一步仍要跑真实 Isaac planning / execution / retention，才能判断是否允许进入 micro-pull。
随后 5L 单候选 live probe 已跑完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_frame_handle_frame_target_generation_live_20260705_5l_1000_cf_handle_right_025_clamped_xy12_zp02/summary_compact.json`。
结果是第一段 bridge replay 成功，但 5L 候选 post-replay replan 返回
`MotionGenStatus.IK_FAIL`，没有 selected waypoint / action points，因此 close-hold 和
retention 没有执行。给 PM 的一句话：我们已经把“按把手/接触坐标系自动生成候选”的第一版跑进
真实 planner 了，结论是这个候选还不可达；下一步要把候选拆小做 reachability ladder，而不是
进入微拉或算分。

2026-07-05 Task 5M 计划已经新增：
[`2026-07-05-eos2-handle-frame-reachability-ladder.md`](../superpowers/plans/2026-07-05-eos2-handle-frame-reachability-ladder.md)。
对 PM 来说，这一步是在回答“机器人到底应该站到把手哪条中线上才可达”。它会优先用
GenManip 已有的 `centerline`、`inner-face-corridor`、`bilateral-contact-frame` 逻辑做小候选，
再一次只跑一个 live candidate。5M 仍是 diagnostic 阶段：如果卡在候选生成或 IK，就不进入
close-hold；如果卡在 retention，就不进入 micro-pull；只有 retention-positive 才能单独开
micro-pull / door joint readback 计划。
工程口径再收紧一步：5M live 不能直接跑 default oracle path 后当作 5L 后续。5L 用的是
`planner-trajectory-execution-readback`，所以 live 前要先把 centerline 候选绑定成
post-replay object-frame waypoint。2026-07-05 route binding 已完成到 code/test checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_route_binding_code_checkpoint_20260705.json`。
现在 GenManip 可以在 bridge replay 后读取 live debug state，把 `centerline` /
`inner-face-corridor` / `bilateral-contact-frame` 候选转成
`obj_DryingBox_01_handle` 的 object-frame waypoint，并沿用同一个 post-replay candidate
sweep planner path。给 PM 的一句话：我们已经把“候选怎么接进 5L 那条考场路线”这根线接上了；
随后 5M first route-bound live probe 已跑完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias/summary_compact.json`。
这次不是 default oracle，也不是 route contract 未绑定：命令已经走
`planner-trajectory-execution-readback`，并带
`--planner-trajectory-post-replay-candidate-source centerline`。第一段 bridge replay 仍然成功，
`executed_steps=151`、`reached_joint_target=true`、final joint error 约 `8.50e-05 rad`。但这
151 步只代表桥接路线走到位，不代表 post-replay centerline candidate 或 close-hold 成功。
新的失败点在 bridge 之后：post-replay replan 没有生成数值有效的 centerline candidate，
`candidate_count=0`、`available_action_points=0`，错误是
`TypeError("float() argument must be a string or a real number, not 'NoneType'")`。
分类是 `BLOCKED_5M_CENTERLINE_SOLVER_INPUT`。给 PM 的一句话：我们已经把候选接进考场路线，
但 live 状态转成 centerline waypoint 的输入还没闭环；下一步先修这个 input/readback blocker，
再重跑同一个 5M 候选。当前仍不能 claim stable grasp、micro-pull、door opened、
Expert Oracle Score 或 score。

2026-07-05 进一步复跑了同一个 5M 候选的 state-reference 版本：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_centerline_inner_face_bilateral_zero_bias_state_reference/summary_compact.json`。
这次已经越过上面的 `NoneType` 输入 bug：post-replay calibration 使用 `state.ee_pose`，
`replan_error=null`，第一段 bridge replay 仍执行 `151` 步并达到 joint target，final joint
error 约 `7.10e-05 rad`。新的第一失败门不是 IK，也不是抓取保持，而是 centerline candidate
几何求解器没能生成候选：`candidate_count=0`、`candidate_failure_reason=PAD_DEPTH_MISS`。
通俗讲，程序已经知道要沿把手中线找一个夹爪中心点，但左右手指同时满足 contact-frame 的区间
还差约 `9.7mm`，所以还没有把候选交给 cuRobo 做第二段规划。当时下一步应先做 candidate-only
tolerance / padding preflight，在 `0.010m` 到 `0.012m` 附近让 `candidate_count>0`，再重跑完整
Isaac planner live；在这之前仍不能 claim close-hold、contact retention、stable grasp、
micro-pull、door opened、Expert Oracle Score 或 score。

为了避免“一直试”，2026-07-05 已新增 candidate-only preflight code checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_candidate_preflight_code_checkpoint_20260705.json`。
通俗讲，这个开关让我们只问一个小问题：当前几何参数能不能生成一个把手中线候选？它不会调用
post-replay cuRobo planner，也不会执行 close-hold 或算分。下一轮最多只扫两组主参数：
`grasp_selection_axis_gap_threshold_m=[0.006,0.008,0.0095,0.010,0.011,0.012,0.014]` 和
`grasp_contact_model_handle_x_padding_m=[0.003,0.0048,0.005,0.006,0.008,0.010,0.012]`。
如果这两组都不能让 `candidate_count>0`，就不继续扩大 offset 硬调，直接判定当前 5M
`centerline + bilateral-contact-frame` 模型不适合这个 post-bridge 状态；后续改走 bridge-to-near
reachability / approach seed 或更明确的 object-frame waypoint。

2026-07-05 已按上面的边界完成 bounded preflight：
`docs/labutopia_lab_poc/evidence_manifests/eos2_handle_frame_reachability_ladder_live_20260705_5m_candidate_preflight_bounded_sweep/summary_compact.json`。
结果是 `run_count=14`、`candidate_found=false`。axis-gap 维度从 `0.006m` 扫到 `0.014m`，
handle-x-padding 维度从 `0.003m` 扫到 `0.012m`，都没有生成 numeric candidate。失败原因从
`PAD_DEPTH_MISS` 过渡到 `HANDLE_NOT_BETWEEN_INNER_FACES`，说明单纯放宽阈值会改变几何判断，
但仍不能让旧 `centerline + inner-face-corridor + bilateral-contact-frame` 模型正确包住真实把手。
handoff 结论：停止当前 centerline tuning，不再扩大 offset；下一步要换 candidate-generation 模型，
优先做 mesh-aware / open-face handle candidate，再用新的 candidate-only gate 验证。

2026-07-05 Task 6C geometry audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_geometry_audit_20260705.json`；
对应 code checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_geometry_audit_code_checkpoint_20260705.json`。
这一步已经证明：不是“找不到真实原生 handle”。在 EBench-loaded USD 里，handle、door leaf 和
RevoluteJoint 都能唯一定位，handle open-face normal 也能给出 `[0.0, 1.0, 0.0]`。需要注意的是，
这个 normal 不是 direct bbox separation，而是 `handle_door_center_delta_overlap_fallback`，因为
真实 native handle 和 door leaf 的 AABB 有重叠。handoff 给下一位工程师的边界是：可以进入
mesh-aware/open-face candidate-only preflight，但必须在 evidence 里保留 fallback normal 来源；
不能直接跳到 full planner、close-hold 或 Expert Oracle Score。

当时的 mesh/open-face candidate 路线判定顺序曾收敛为 5 个小阶段，不再开放式试参数：
1. mesh/open-face candidate-only preflight：最多跑 `6` 个 primary normal 组合，加 `2` 个 opposite-normal
   sign sanity 组合；如果仍 `candidate_count=0`，写
   `BLOCKED_MESH_AWARE_CANDIDATE_NO_CANDIDATE_AFTER_BOUNDED_PREFLIGHT`，停止这条候选模型。
2. one full planner/readback：只有 `candidate_count>0` 后才跑；如果 `IK_FAIL` 或没有 action points，
   停止 candidate tuning，转 bridge-to-near / approach-seed。
3. close-hold/contact-retention：只有 planner/readback 成功后才看；如果 tail window 仍没有
   required-role contact，这就是 contact-retention blocker。
4. micro-pull/door joint readback：只有 retention 通过后才看门角变化。
5. Expert Oracle Score：只有门角和保持都闭环后才算分。产品口径上，planner/readback 通过只能说
   “真实把手能生成 EBench 候选并交给 planner”；micro-pull 通过才接近“工程上弄好”；score 通过才是
   “评测口径弄好”。这段是历史 mesh/open-face 路线口径，已被后续 approach-seed / Gate 1C
   决策树收紧。

2026-07-05 这条 Gate 1 的代码入口已经补上：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_aware_open_face_candidate_preflight_code_checkpoint_20260705.json`。
现在 post-replay candidate source 支持 `mesh-open-face`，会读取 Task 6C geometry audit JSON，
把 audited handle open face 转成 object-frame waypoint，并保留
`handle_open_face_source=handle_door_center_delta_overlap_fallback`。真实 audit 的离线 primary contact
target 是 `[0.47978996139738445,0.27571899126186217,1.1085915534527668]`，opposite sign sanity
target 是 `[0.47978996139738445,0.22180747411861262,1.1085915534527668]`。handoff 边界：
这只是 `READY_FOR_MESH_OPEN_FACE_CANDIDATE_ONLY_PREFLIGHT`，不是 live `candidate_count>0`；
下一位工程师应先跑 candidate-only preflight，确认候选存在后才允许进入 post-replay planner。

2026-07-05 随后已跑完 primary normal 的 live candidate-only preflight：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_candidate_preflight_live_20260705_primary/summary_compact.json`。
结果是 `candidate_found=true`，分类
`PASS_MESH_OPEN_FACE_CANDIDATE_ONLY_PREFLIGHT_READY_FOR_PLANNER_READBACK`。bridge replay 执行 `150`
步并达到 joint target；post-replay 阶段只做候选生成，`candidate_source=mesh-open-face`、
`candidate_preflight_only=true`、`candidate_count=1`、`attempted_candidate_count=0`、
`skipped_reason=candidate_preflight_only`。候选 contact target 是
`[0.47978996139738445,0.27571899126186217,1.1085915534527668]`，normal 来源仍是
`handle_door_center_delta_overlap_fallback`。handoff 结论：mesh/open-face candidate-only 小阶段已过，
不需要跑 opposite-normal sign sanity；下一步应该只跑一个 full post-replay planner/readback。如果 full planner 返回
`IK_FAIL` 或没有 action points，就停止 candidate tuning，转 bridge-to-near / approach-seed。

2026-07-05 这个 full post-replay planner/readback 已跑完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_planner_readback_live_20260705_primary/summary_compact.json`。
结果是候选生成已经通过，但 contact target 在 cuRobo 里 `IK_FAIL`：`candidate_count=1`、
`attempted_candidate_count=1`、`successful_candidate_count=0`、`available_action_points=0`。
给 PM 的一句话：我们已经不是卡在“能不能找到把手目标”，而是卡在“Franka 在当前 post-bridge
状态能不能到这个把手前方姿态”。这不是 post-replay 执行失败，因为没有 action points 可以执行。

2026-07-05 随后按停止规则跑了 bridge-to-near bounded sanity：
`docs/labutopia_lab_poc/evidence_manifests/eos2_mesh_open_face_bridge_to_near_bounded_sanity_20260705/summary_compact.json`。
这一步只问“先不碰把手，能不能到把手前方安全点”。为了避免单点误判，只跑两个有界 near 点：
`approach_offset_m=0.035` 和 `0.045`。两条都进入 cuRobo planning，但都返回
`MotionGenStatus.IK_FAIL` 且 `available_action_points=0`；bridge replay 本身仍达到 joint
tolerance。handoff 结论：停止 contact-target / near-offset 调参，下一步不该继续换颜色、
换法线或扩大参数，而是转 approach-seed / robot-staging redesign，也就是重新设计“机器人先站到哪里、
手腕用什么姿态、从哪个中间点接近把手”。当前仍不能 claim close-hold、retention、door opened、
Expert Oracle Score、policy score、official score 或 full task completion。

新的执行入口是
`docs/superpowers/plans/2026-07-05-eos2-approach-seed-robot-staging-redesign.md`。交接口径改为：
先做 Gate 1 wrist orientation source / approach seed / robot staging 的有界验证；只有出现
`selected_plan_success=true`、`available_action_points>0` 且 replay readback 到 joint tolerance，
才进入 Gate 2 contact。Gate 3 是 close-hold / retention，Gate 4 是 micro-pull / door joint
readback，Gate 5 才是 `Expert Oracle Score`。如果 Gate 1 的有界候选全部失败，只能说当前
bridge/staging 路线不成立，不能说门必然打不开或所有机器人布局都不可行。

2026-07-05 Gate 1 Task 1 代码入口已经就绪：
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_code_checkpoint_20260705.json`。
新增 CLI 是
`--planner-trajectory-post-replay-mesh-open-face-orientation-source {native-open,post-replay-ee}`；
默认 `native-open` 保持旧行为，`post-replay-ee` 会把 bridge replay 后 live `state.ee_pose[1]`
作为 mesh-open-face candidate 的 world orientation。TDD 已完成，但这还不是 live reachability；
下一步是 Gate 1 Task 2 的单次 wrist-orientation isolation probe。

2026-07-05 Gate 1 Task 2 单次 wrist-orientation isolation probe 已跑完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_orientation_source_live_20260705_post_replay_ee_near045/summary_compact.json`。
这次不是候选生成失败：`candidate_count=1`，目标是
`approach_near_target_world=[0.47978996139738445,0.32071899126186215,1.1085915534527668]`，
world orientation 明确来自 bridge replay 后的 `state.ee_pose[1]`。真正失败点仍是
post-replay planner：`MotionGenStatus.IK_FAIL`、`available_action_points=0`、
`selected_plan_success=false`。PM 口径是：换手腕姿态这条小修不够，不能进入 contact、close-hold、
micro-pull 或 score。边界也要说清楚：bridge replay 这轮达到 joint tolerance，但只执行到
`64` step cap，而桥接轨迹共有 `151` 个 action points，所以这条 evidence 不能单独升级成
“整个 Gate 1 route 不可行”。

2026-07-05 Gate 1B bounded staging family 已跑完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_family_live_20260705/summary_compact.json`。
这轮不是 no-go，而是找到了一个中间站：`post_bridge_local_z_m006_q_bridge`。它生成 `90` 个
action points，staging replay 后 joint readback 进入 `0.02 rad` 容差。handoff 分类是
`STAGING_CONTINUATION_EVIDENCE_ONLY_REQUIRES_GATE_1C_STAGING_TO_MESH_OPEN_FACE_APPROACH_NEAR`。
给下一位工程师的边界：这只能说明“机器人能走到一个更合理的 staging parent”，不能说已经到达
handle-front approach。下一步只能做 Gate 1C：从这个 staging parent 再规划到 mesh-open-face
`approach_near_target_world`。Gate 1C 通过后才进入 contact；Gate 1C 如果仍 `IK_FAIL` 或 0 action
points，就停止当前 bridge + staging parent 路线，不能继续靠 contact offset 或 score 硬试。
仍不能说 DryingBox 不可开、所有 staging 都不可行或 Expert Oracle Score 不可能。

2026-07-05 Gate 1C selected staging-to-near live probe 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_staging_to_mesh_open_face_near_live_20260705/summary_compact.json`。
handoff 分类是
`BLOCKED_APPROACH_SEED_STAGING_TO_MESH_OPEN_FACE_NEAR_IK_FAIL_NO_ACTION_POINTS`。正向证据是：
bridge replay 本身达到 joint tolerance；`post_bridge_local_z_m006_q_bridge` staging parent 也
达到 joint tolerance。负向证据是：从这个 staging parent 继续到 mesh-open-face
`approach_near_target_world` 时，cuRobo 返回 `MotionGenStatus.IK_FAIL`，`available_action_points=0`。
交接边界：停止当前 selected staging-parent route；不要从这条路线继续跑 Gate 2 contact、
close-hold、micro-pull 或 `Expert Oracle Score`。下一位工程师如果继续 EOS-2，应该先选择路线分流：
预注册少量 sibling staging-to-near 变体验证，或重设 robot layout / staging / candidate-generation。
任何新路线都必须重新通过 Gate 1，不能直接继承 Gate 1B 的中间站成功。
review 后推荐先走小集合 Gate 1D，而不是马上大 redesign：Gate 1C 只排除了一个 selected staging
parent，所以先用少量预注册 sibling staging parent 只改“中间站”，其它 bridge、target、orientation、
planner path 都保持不变。这样如果 sibling 也全部失败，才能把结论升级到 staging family no-go，
再进入 Gate 1R 的 robot layout / staging / candidate-generation redesign。

后续阶段的交接口径：

| 阶段 | 下一位工程师要验证什么 | 停止条件 |
|---|---|---|
| Gate 1C | 从 `post_bridge_local_z_m006_q_bridge` 到 mesh-open-face `approach_near_target_world` | `IK_FAIL`、0 action points 或 replay readback 不达标，就停止当前 selected staging-parent route |
| Gate 1D | 少量预注册 sibling staging parent 到同一个 `approach_near_target_world` | sibling family 全部失败就升级到 Gate 1R，不进 contact |
| Gate 1R | 重设 robot layout / staging / candidate-generation | 没有新的 near reachability PASS，就不进 Gate 2 |
| Gate 2 | 从 Gate 1C 的 near pose 到 contact target | contact planner/readback 失败就停止，不进 close-hold |
| Gate 3 | close-hold 后 required-role contact / overlap 是否成立 | retention 不成立就停止，不进 micro-pull |
| Gate 4 | retained grasp 是否能带动 door joint / angle | 门角不动或保持失败就停止，不进 score |
| Gate 5 | expert route 是否能在 EBench metric 下记录分数 | 只有这里通过，才算评测口径闭环 |

2026-07-05 Gate 1D sibling staging-to-near bounded triage 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_sibling_staging_to_near_live_20260705/summary_compact.json`。
handoff 分类是
`BLOCKED_APPROACH_SEED_SIBLING_STAGING_TO_NEAR_FAMILY_IK_FAIL_NO_ACTION_POINTS`。预注册 sibling
只有两条：`post_bridge_local_y_p006_q_bridge` 和 `post_bridge_local_x_m006_q_bridge`。两条
bridge replay 都达到 joint tolerance；但 sibling staging replan 各自都是
`MotionGenStatus.IK_FAIL`、0 action points，所以 follow-up 到 mesh-open-face
`approach_near_target_world` 没有资格执行。交接边界：不要从 y_p006 / x_m006 继续跑 contact；
下一步升级到 Gate 1R，重新设计 robot layout / staging / candidate-generation，目标仍然是先拿到
`PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`。

Gate 1R 的预注册路线也已经明确：优先改 robot base/layout 的 XY 相对位置，而不是继续改
contact target、near offset、wrist orientation 或 reset seed。下一位工程师应把下面候选作为
bounded contract 执行，不要临场追加参数：

| Gate 1R 候选 | robot base position | 固定项 | 通过条件 |
|---|---|---|---|
| `R1_layout_y_p010` | `[-0.4, 0.10, 0.73]` | same asset/metric/planner route, no reset seed, same bridge, same `z_m006` staging, mesh-open-face primary normal, `approach_offset=0.045`, `orientation_source=post-replay-ee` | bridge、staging、near 三段都有 action points 且 readback 到 `0.02 rad` |
| `R2_layout_x_p012` | `[-0.28, 0.0, 0.73]` | 同上 | 同上 |
| `R3_layout_x_p012_y_p008` | `[-0.28, 0.08, 0.73]` | 同上 | 同上 |
| `R4_approach_line_staging_under_best_layout` | 只在 R1-R3 有 clean reset + bridge 但 near 仍失败时运行 | 选 best layout，final target 仍是 `0.045m near`，contact/score 禁用 | approach-line staging 和 near 都 replay 到容差 |

如果 Gate 1R 没有产出 `PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`，handoff 仍停在
Gate 1，不能进入 Gate 2 contact。

2026-07-06 Gate 1R live handoff update:
`docs/labutopia_lab_poc/evidence_manifests/eos2_approach_seed_gate1r_layout_live_20260706/summary_compact.json`
已经把 R1/R2/R3/R4 全部归档。分类是
`BLOCKED_APPROACH_SEED_APPROACH_LINE_STAGING_IK_FAIL_NO_ACTION_POINTS`。R1/R2/R3 只改 robot base
XY，全部 bridge replay 到位，也都规划到 `post_bridge_local_z_m006_q_bridge` staging；但从该
staging 到 mesh-open-face `0.045m near` 全部 `IK_FAIL`、0 action points。R4 按 reviewer 结论选
R2 layout，先 preflight 出 `0.085m` approach-line staging world target
`[0.47978996139738445,0.3607189912618622,1.1085915534527668]`，再作为 explicit staging live 跑；
结果 bridge 到位，但 R4 staging 自己 `IK_FAIL`、0 action points，near follow-up 因没有 staging
execution 被跳过。

交接边界：Gate 1R 预注册候选集合已经没有产出
`PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT`。下一位工程师不要从这些 R1-R4 结果继续
跑 contact、close-hold、micro-pull 或 Expert Oracle Score；下一步应新开
`Gate 1S: Strategy Redesign / No-Go Review`。允许说“当前预注册 Gate 1R 集合没能把机器人带到把手前
安全点”；不允许说“DryingBox 全局打不开”或“官方分数失败”。

Gate 1S review manifest 已建立：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_strategy_review_20260706.json`。Gate 1S is now
the next stage. It is a strategy redesign / bounded no-go review, not another local offset sweep. The
selected default strategy is `S1_TASK_LAYOUT_NORMALIZATION`, with `max_selected_live_strategy_count=1`.
Gate 2 and Expert Oracle Score remain blocked until a new
`PASS_APPROACH_SEED_NEAR_REACHABILITY_READY_FOR_CONTACT` is recorded.

Gate 1S selected strategy live 也已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1s_selected_strategy_live_20260706/summary_compact.json`。
分类是 `BLOCKED_GATE1S_SELECTED_STRATEGY_NO_NEAR_REACHABILITY`。S1 使用
`level1_open_door_gate1s_layout_normalized.yml`，robot base `[-0.2,0.0,0.73]`；bridge replay 仍成功，
但 post-replay mesh-open-face `0.045m near` 继续 `MotionGenStatus.IK_FAIL`、0 action points。
handoff 结论：不要从这个合同继续跑 contact、close-hold、micro-pull 或 Expert Oracle Score；如果要继续，
需要明确改合同，例如换 robot、改 task layout 规则、改 route generator，或正式接受当前合同 bounded no-go。

历史 bridge evidence 曾把问题从“有没有中间路”推进到“world refresh 后起点为什么被判 collision”。
证据目录是 `docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_bridge_ladder_20260704_181425/`。
no-refresh 下 `approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 可以规划出
152 个 trajectory points；第一次 world-refresh 复跑在 reset 阶段 Ray OOM，不作为
planner/collision 结论；retry2 中 reset 成功，12 个候选的 world refresh 都成功，但
planner debug 全部是 `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`。这一步后续已经
由 Task 4c live classify evidence 完成：具体 blocker 是
`/World/labutopia_level1_poc/obj_table/surface/mesh` vs `panda_hand`。Task 4d.3 live
no-extra-ignore support-surface clearance audit 也已经完成：runtime 读到了 table AABB，
也记录了 cuRobo 报碰撞的 `panda_hand` sphere。2026-07-05 frame 复核后，旧
`sphere_center_world` 字段被判定为命名过强：cuRobo obstacles 和 robot spheres 都在
planner/reference frame，不是 USD stage world frame。因此旧记录能说明“table surface /
`panda_hand` 是 bridge blocker”，但不能直接说明真实手爪在世界坐标里穿进桌面。随后
Task 4d.4A **frame-aware support-surface clearance audit** 已完成：新证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_support_surface_frameaware_clearance_audit_20260704_221731/`，
compact 文件是 `pose_ladder_support_surface_frameaware_compact.json`。这次把 table AABB 和
hand sphere 都放到 `planner_reference_frame` 后比较，12/12 条都是 `measured_same_frame`，
`clearance_margin_m=-0.011760663122180937`，planner-only exclusion allowed count 为 `0`。
Task 4d.4B 随后做了 **base-z-lift isolation**：新证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_base_z_lift_002_20260704_223919/`，
compact 文件是 `pose_ladder_base_z_lift_002_compact.json`。这次只把 Franka diagnostic
base position 从 `[-0.4, 0.0, 0.71]` 抬到 `[-0.4, 0.0, 0.73]`，其它资产、metric、
planner 和 pose-ladder 参数不变。结果 submit/probe exit code 都是 `0`，start-state
collision 从 12/12 变成 `0`，第二个 bridge candidate 在 world refresh 下规划成功，
`trajectory_point_count=152`。产品口径：这说明主要问题更像是机器人 reset/base clearance
太贴桌面，而不是应该直接删掉桌子碰撞。边界也要讲清楚：base z +2cm 是诊断隔离，不是最终
产品姿态；下一步要把它收敛成正式 reset/base/joint contract。

2026-07-05 Task 4d.4C 又补了一层“不是只改 YAML”的证据：GenManip debug state 现在会把
observed `robot_prim_path`、`robot_world_position`、`robot_world_orientation_wxyz` 写入
reset debug 和 pose-ladder excerpt。代码 checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_reset_base_observed_pose_code_checkpoint_20260705.json`。
复跑 evidence 在
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_base_z_lift_002_observed_base_20260704_225244/`，
compact 文件是 `pose_ladder_base_z_lift_002_observed_base_compact.json`。这次 observed robot
base z 明确是 `0.730000019m`，start-state collision 仍为 `0`，第二个 bridge candidate
仍规划出 152 个点。产品口径：抬高 2cm 这件事已经真实进入 Isaac/USD robot prim；但它仍是
诊断方案，不是最后的产品 reset policy。当前不能汇报 stable grasp、micro-pull、door opened、
`Expert Oracle Score`、policy score、official score 或 full collision-aware planning。

2026-07-05 Task 4d.4D 已完成 reset branch 对照。`default_joint_positions` 分支保留
base z=`0.71m`，配置 9D Franka reset seed
`[0, -1.3, 0, -2.5, 0, 1.0, 0, 0.04, 0.04]`；readback 证明 7D arm seed 确实进入 reset，
但 `pose_ladder_reset_seed_retract_001_readback_compact.json` 仍显示 12/12 个 bridge
candidate 都是 `INVALID_START_STATE_WORLD_COLLISION`，碰撞对象仍是 table surface vs
`panda_hand`。随后 `base_z_lift_002_only` 分支只把 base z 改成 `0.73m`，不设置
`solver_velocity_iteration_count`，也不关闭 `enabled_self_collisions`；结果
`pose_ladder_base_z_lift_002_only_compact.json` 显示 start-state collision 为 `0`，第二个
bridge candidate 规划出 152 个点。产品口径：现在不是“随便换一个关节初始姿态就行”，而是
证据支持把 Franka 的 POC reset layout 抬高 2cm 作为当前正式候选。

2026-07-05 Task 4d.4E 已把这个候选落到正式配置：GenManip 的
`configs/tasks/ebench/labutopia_lab_poc/franka_poc/level1_open_door.yml` 已改成
`position: [-0.4, 0.0, 0.73]`。这个正式 config 没有加入 `default_joint_positions`，
也没有加入 solver override、self-collision disable 或 oracle debug obs。普通 diagnostic
open-door configs 同步到 `0.73m`，而 `reset_seed_retract_001` 保留 `0.71m` 作为失败对照。
机器可读 checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_open_door_formal_reset_contract_checkpoint_20260705.json`。
产品口径：reset/base contract 已落配置；当时下一步才是 bounded execution/readback，验证真的能抓住、
微拉、门角度变化。该路线已经被后续 Task 5A-5M 消费，当前 blocker 已推进到 5M
state-reference 的 centerline candidate generation：`PAD_DEPTH_MISS`，还没有 numeric candidate。

2026-07-05 Task 4d.4F bounded execution/readback 已经补跑，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_bounded_execution_base_z_073_20260704_233033/`，
compact 文件是 `lead_in_base_z_073_compact.json`。这次先发现一个纯调用问题：
`python -m genmanip_client.cli submit ...` 在当前 client 里不会真的启动 job，所以 probe
会报 `No job started`；改用 Python 直接调用 `genmanip_client.cli.main([...])` 后，
server / submit / reset / probe 都能进入正式流程。这个问题不是 USD、材质、桌面碰撞或
Franka 本体失败。

正式结果仍是 diagnostic fail：`approach_pre` 的 IK 能算出来，说明“目标点不是完全算不出”；
bounded lead-in 也真的执行了 53 个小步，说明“诊断链路不是空跑”。但在后段真实 readback
突然发散，step 52 触发 `arm_state_jump_too_large`，最终没有稳定到达目标。给 PM 的一句话：
我们已经把机器人站位、任务启动和第一段专家目标计算打通了；现在卡在“把专家目标稳定、安全地
执行到把手前”这一层，还没有到抓把手、拉门或算分。

为什么这会比“直接套 expert 轨迹”难：EBench 自己的 `microwave` 任务也不是简单把
`skill_trajectory` 逐帧 replay。它的 manual expert 写在 `microwave.yml` 的
`custom_motion` 里：开门段既有相对微波炉的 `object_frame` 目标，也有 `robot_frame`
staging，并带 grasp/pending 状态；运行时 `custom_motion.py` 把这些 task-level targets
转成 world/robot pose，再用 `BaseEmbodiment.plan_pose` 和 cuRobo `MotionGen.plan_single`
现场生成 joint trajectory。DryingBox 后续也应按这个范式做：用 handle/object-frame
waypoints 描述“到把手前、贴近、闭爪、沿门轴方向拉”，每个 waypoint 都要经过 cuRobo
planning、执行和 readback 验证，而不是继续把一个 absolute IK target 拆小步硬走。

2026-07-05 Task 5A 已补上下一步 execution/readback 缺的“路线导出口”。之前 planner-only
通道只告诉我们“这个 waypoint 有多少个 trajectory points”，但没有把这些 joint trajectory
点交给 probe；所以 probe 只能自己把一个 IK 目标拆小步，结果后段 readback 发散。现在
GenManip 的 `plan_object_frame_waypoints` 可以在显式打开 `include_trajectory_points` 时返回
每个 waypoint 的两类轨迹证据：`trajectory_joint_positions` 是 cuRobo planner 的原始关节点，
用于审计 planner 到底算了什么；`trajectory_action_joint_positions` 是已经经过
`embodiment.convert_curobo_result_to_action` 转成 EBench runtime 可消费的 `joint_position`
action payload，并带 `trajectory_action_joint_names`、`trajectory_action_control_type` 和
`trajectory_action_replay_policy`。review 后还加了 non-finite guard：如果 planner 或 action
里出现 `NaN` / `Infinity`，record 会失败为 `non_finite_trajectory_point`，不会把坏轨迹写进
下一步 replay 输入。genmanip-client 和 online probe 也能转发并保存这些字段。
机器可读 checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_export_code_checkpoint_20260705.json`。
给 PM 的一句话：我们刚补的是“把 planner 算出的路线明细导出来”，还不是“机器人已经按路线走完”。
Task 5B 的 code checkpoint 也已补上：
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_execution_readback_code_checkpoint_20260705.json`。
通俗讲，这一步是把“路线明细”接到了“按路线逐帧发给机器人”的诊断入口。新的
`planner-trajectory-execution-readback` probe 会重新向 planner 请求
`include_trajectory_points=true`，只消费 `trajectory_action_joint_positions`，不会把 raw
`trajectory_joint_positions` 当成可 replay 的合同；有 fresh job starter 时会先切到独立的
`planner_trajectory_replay` run_id，再逐帧发送 absolute `joint_position` action，并记录
每一帧的 controller readback、terminal reason 和最终 joint tolerance。review 后已经修掉三个
容易混淆的问题：即使 reset 正常也必须进入 fresh replay run；只有 action-level trajectory、没有
raw trajectory 时也能消费；summary 明确写出 stable grasp、micro-pull、score 都不能 claim。
但这仍是 code/unit checkpoint，还不是 live Isaac 结果。下一步才是在 `base_z=0.73m` 正式
reset/base contract 下真实跑一次这个 probe，拿 summary/trace/result_info 来判断轨迹执行是否稳定。

2026-07-05 Task 5B live rerun 已完成一轮，证据入口是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_execution_readback_live_20260705_005444/planner_trajectory_execution_summary.compact.json`。
通俗讲，上一轮旧错误像是“还没把机器人放进考场，就问考场里的 0 号机器人怎么走”，所以 server
报 `worker 0 does not exist`。现在 probe 已改成先 `reset`，确认 0 号 worker 和 obs 都存在，
再调用 `plan_object_frame_waypoints`；fresh live run 里这两步都返回 200，说明考场和机器人生命周期
已经接上。新的失败点不是生命周期，而是专家第一段动作本身：`approach_pre`、
`approach_near`、`contact` 三个 object-frame waypoint 在 cuRobo 里都是
`MotionGenStatus.IK_FAIL`，没有生成可 replay 的 `trajectory_action_joint_positions`。所以这轮没有
执行轨迹，也不能说已经抓住、拉门或能得分。下一步要回到 target/orientation/reachability
校准，把“手腕应该以什么姿态到把手前”调成 Franka + cuRobo 可规划。

2026-07-05 Task 5C 已把这个 bridge 发现固化成 formal-safe contract。失败对照是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_bridge_execution_readback_live_20260705_5c_0100/`：
formal reset observation 里没有 `debug.labutopia_open_door`，所以不能再依赖调试字段动态生成
bridge waypoint。修复后的 contract 是在 probe CLI 显式传
`--planner-trajectory-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`，追加到同一个
`plan_object_frame_waypoints` object-frame payload 里。成功证据是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_explicit_bridge_execution_readback_live_20260705_5c_0120/planner_trajectory_explicit_bridge_execution_summary.compact.json`：
选中 bridge label
`approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity`，planner 生成 `152`
个 action points，probe replay `152` 步，`reached_joint_target=true`，最终 joint 误差约
`7.13e-05 rad`，`blockers=[]`。代码 checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_explicit_waypoint_code_checkpoint_20260705.json`。
交接给工程同学的重点：后续 formal run 应使用显式 object-frame waypoint contract；
不要再把 `debug.labutopia_open_door` 当作正式接口的一部分。

PM 口径：这一步说明“正式 EBench 配置已经能吃到桥接导航点，并且机器人能按 cuRobo 生成的
152 步路线走到这个中间目标”。它还不是完整开门得分：没有 close/grasp、没有 stable handle
contact、没有 micro-pull、没有 door-angle metric，也没有 `Expert Oracle Score`。当时下一步是把
bridge 后面的 handle-side approach/contact、close/grasp、micro-pull 拆成同样的 staged
object-frame waypoints，每段都生成 planner record、action trajectory 和 readback 证据；这条路线
已经推进到 5I 的 contact-frame micro-correction 证据。

2026-07-05 Task 5D 又补了 post-replay continuation 证据。code checkpoint 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_code_checkpoint_20260705.json`；
live 证据看
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_replan_live_20260705_5d_0200/summary_compact.json`。
这轮 run 用同一个 formal `level1_open_door.yml` 和显式 bridge waypoint，先让 planner
生成 action trajectory，再让 EBench consumer replay。结果是 bridge replay 本身成立：
`available_action_points=150`、`executed_steps=150`、`reached_joint_target=true`、
`final_joint_target_abs_max_rad=7.128715515136719e-05`，阈值是 `0.02 rad`。随后 probe
没有 reset，而是在 bridge 后的 worker state 上再次调用 `plan_object_frame_waypoints`；
这证明 post-replay replan 的 server/API/state continuation 通路已经打通。

但这轮不能写成 5D 通过：follow-up waypoint 仍用旧 `approach_pre`，cuRobo 返回
`MotionGenStatus.IK_FAIL`，没有第二段 `trajectory_action_joint_positions`，summary
blockers 是 `planner_trajectory_post_replay_planner_failed` 和
`planner_trajectory_post_replay_action_joint_positions_missing`。交接给工程同学的重点：
下一步不要重查 worker lifecycle，也不要回到动态 debug observation；应基于 post-bridge
状态重新设计 handle-side approach/contact waypoint family，并对每个候选保留 planner
record、action trajectory、readback 和 no-claim guards。

2026-07-05 Task 5E code checkpoint 已补上这个候选扫描能力，manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_code_checkpoint_20260705.json`，
实施计划是
`docs/superpowers/plans/2026-07-05-eos2-post-bridge-followup-waypoint-family.md`。新的 probe
参数是
`--planner-trajectory-post-replay-extra-object-frame-waypoint LABEL X Y Z QW QX QY QZ`，
可以重复传多个 post-bridge follow-up candidate。工程语义要特别注意：这些 candidate 是
alternatives，不是一串连续动作。`object_frame_waypoint_planner` 在同一次 planner call 内
会把成功 waypoint 推进本地 `sim_js`，所以 5E 不会一次把候选全塞进去；它会一个 candidate
一次 call，从同一个 post-bridge worker state 规划，汇总 `candidate_records`、
`selected_waypoint_label`、`failure_status_counts`，默认选择第一个 `plan_success=true` 的候选。

验证结果：新增 TDD `sweeps_post_replay_extra` 为 `1 passed, 273 deselected`；
`planner_trajectory_execution_readback or post_replay` 为 `7 passed, 267 deselected`；
probe/test `py_compile` 和 `git diff --check` 通过。

2026-07-05 live 5E evidence 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_followup_sweep_live_20260705_5e_0300/summary_compact.json`。
submit/probe exit code 都是 `0`，说明这不是环境、server 或 endpoint 问题。第一段 explicit
bridge waypoint 仍能规划并执行：`available_action_points=150`、`executed_steps=150`、
`reached_joint_target=true`，最终 joint target 误差约 `7.12e-05 rad < 0.02 rad`。第二段
candidate sweep 也真实进入 post-bridge worker state：4 个候选
`post_bridge_to_approach_pre_f_0p20/0p40/0p60/0p80` 都被逐个规划，world refresh 为
`success`，但全部返回 `MotionGenStatus.IK_FAIL`，`successful_candidate_count=0`，没有
第二段 action trajectory。

交接给下一位工程师的重点：不要再重查 conda、Ray server、worker lifecycle 或
`plan_object_frame_waypoints` endpoint；这些链路已经跑通。当前 blocker 是 follow-up target
family 本身不可达，尤其是“从 post-bridge pose 直接向旧 `approach_pre` 插值”的方向不可用。
下一步应以 post-bridge pose 为中心，扫 wrist orientation、局部 Y/Z/forward translation 和
handle-side contact frame，而不是继续复用 stale `approach_pre`。成功标准是先拿到一个
post-bridge continuation 的 planner trajectory 并 replay 到 joint tolerance 内；在这之前仍不能
claim stable grasp、micro-pull、door opened、`Expert Oracle Score` 或 score。

2026-07-05 Task 5F live evidence 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_bridge_pose_centered_sweep_live_20260705_5f_0400/summary_compact.json`。
这轮用 5E 的结论反推候选族：不再沿旧 `approach_pre` 大步插值，而是在 post-bridge pose
附近扫小步。submit/probe exit code 都是 `0`；第一段 bridge 仍能 replay 到位，150 步后
joint target 误差约 `8.01e-05 rad < 0.02 rad`。第二段 candidate sweep 真实找到了一个可执行
continuation：`post_bridge_local_z_m006_q_bridge`，含义是保持 bridge quaternion，只在 handle
object-frame 的 z 方向下移 `0.006m`。它生成 33 个 action-level points，probe replay 33 步，
`reached_joint_target=true`，最终 joint target 误差约 `6.79e-05 rad < 0.02 rad`。前面 4 个
候选仍是 `MotionGenStatus.IK_FAIL`，所以这个结果也说明“方向选择”很敏感。

交接重点更新：不要再把“第二段完全走不动”当作 blocker。现在已经有一条局部第二段能走通。
下一步应进入 5G close-hold staging：把 bridge + `post_bridge_local_z_m006_q_bridge` 作为移动
前置段，然后单独做 gripper close / pending / contact retention，不要把闭爪和继续移动合并到同
一个 planner candidate。仍不能 claim stable grasp、micro-pull、door opened、
`Expert Oracle Score` 或 score。

2026-07-05 Task 5G close-hold code checkpoint 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_code_checkpoint_20260705.json`。
GenManip probe 现在支持 `--planner-trajectory-post-replay-close-hold-steps`。使用方式是：
先沿用 5F 的 bridge + `post_bridge_local_z_m006_q_bridge` 两段移动；如果 post-replay worker
state 可复用，再保持最终 7 个 arm joints 不动，把两个 finger joints 命令到 `close_width_m`
并 pending N 步。summary 写 `post_replay_close_hold`，trace sample type 写
`planner_trajectory_post_replay_close_hold_action`。

交接给下一位工程师的重点：5G live run 不应再调整 bridge 或把 close 写成新的 planner waypoint。
close-hold 是移动后的独立阶段，后续验收顺序应是 finger command/readback -> contact retention ->
micro-pull -> door metric。当前 checkpoint 还不是 live Isaac grasp evidence，不能 claim
stable grasp、micro-pull、door opened、`Expert Oracle Score` 或 score。

2026-07-05 Task 5G live evidence 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_close_hold_live_20260705_5g_0500/summary_compact.json`。
这轮复用了 5F 的 bridge + `post_bridge_local_z_m006_q_bridge` 路线，然后执行
`--planner-trajectory-post-replay-close-hold-steps 15`。submit/probe exit code 都是 `0`，
server 端口 18438 已释放。结果：bridge replay 148 步到位，第二段 continuation 31 步到位，
close-hold 15 步到位；最后 finger width readback 约 `0.01280m`，目标是 `0.010m`。

交接重点更新：live 5G 已证明 close command/readback 链路，不要再重查 `state.gripper`
读取问题。当时下一步不是直接 micro-pull，而是给 planner close-hold 阶段补 contact/retention
instrumentation：至少要看到左右 finger 与 handle 的接触角色和保持窗口，才能说 stable grasp
或进入微拉。该 instrumentation 已由 5H/5I 消费；当前仍不能 claim stable grasp、micro-pull、
door opened、`Expert Oracle Score` 或 score。

2026-07-05 Task 5H contact-retention code checkpoint 已新增：
`docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_code_checkpoint_20260705.json`。
GenManip probe 现在会在 `planner_trajectory_post_replay_close_hold_action` 每一步记录
`post_close_contact_frame`，并在 `post_replay_close_hold.retention_summary` 汇总 close-hold
窗口内的 bilateral AABB overlap、finger width readback、以及可选 PhysX required-role contact。
focused tests `4 passed in 0.25s`，probe/test `py_compile` exit 0，GenManip diff check exit 0。

交接重点更新：5H code checkpoint 只是把“是否夹到把手”的证据字段补齐；checkpoint 本身尚未产出
live contact-retention 结果。随后 live 5H 已按同一条路线执行：复用 5F bridge +
`post_bridge_local_z_m006_q_bridge` + 5G close-hold，没有重新发明路线。判定顺序是：先看 per-step
`post_close_contact_frame` 是否左右 finger 都 near/overlap handle，再看 retention tail 窗口是否保持；
如果开启 PhysX contact guard，还要看 `tail_physx_required_roles_contact_records`。只有这些成立后，
才进入 micro-pull。当前仍不能 claim stable grasp、micro-pull、door opened、
`Expert Oracle Score` 或 score。

2026-07-05 Task 5H live evidence 已更新两份 compact summary：

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_live_20260705_5h_0430/summary_compact.json
docs/labutopia_lab_poc/evidence_manifests/eos2_planner_trajectory_post_replay_contact_retention_debugobs_live_20260705_5h_0440/summary_compact.json
```

第一份是环境 negative control：server 只开 `LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1`，没有开
`LABUTOPIA_ORACLE_DEBUG_OBS=1`，所以 close-hold 虽然执行了 15 步并读到 finger width 约
`0.01280m`，但 `post_close_contact_frame` 报 `missing_action_application_debug`。第二份是正确
debug 环境重跑：`tail_physx_contact_status_counts.available=15`，说明 contact telemetry 已接通；
close-hold 仍到位，final joint target 误差约 `8.27e-05 rad`，最后 finger width 约 `0.01280m`。
raw `PASS_PLANNER_TRAJECTORY_EXECUTION_READBACK_DIAGNOSTIC_ONLY` 只表示诊断 motion/readback 跑完，
不是 grasp 或 task success；`finger_width_max_pass=false` 是因为 15 步 tail 包含闭爪过渡帧。
但 retention 没过：`retention_pass=false`、`tail_bilateral_overlap_pass=false`、
`tail_physx_required_roles_contact_records=0`，最后一帧左右 finger 都不 near/overlap handle，
最大 required-role axis gap 约 `[0.1353, 0.0692, 0.0]m`。

2026-07-05 Task 5I live evidence 已补充到 evidence manifest，并为每个 run 写了
`summary_compact.json`。关键交接结论：

```text
5i_0610: negative control，未 submit job，不能当 contact/IK 结论。
5i_0620: cf_right_050 半量 gap 校正 IK_FAIL。
5i_0630: 约 1cm/8mm coarse micro 校正 IK_FAIL。
5i_0640: baseline post_bridge_local_z_m006_q_bridge 可复现，harness 正常，但 retention=false。
5i_0650: mixed-direction 5mm 可执行，但只改善 world X gap、恶化 world Y gap，retention=false。
5i_0700/0710/0720/0730: correct-direction 5mm/2mm paired correction 均 IK_FAIL。
5i_0740/0750: correct-direction 单轴 2mm 可执行，但仍无 bilateral overlap / required-role PhysX contact。
```

交接重点更新：5I 把 blocker 从“怎么按 contact-frame 平移”进一步收窄到 “fixed wrist quaternion
下的接触校正可达域太窄”。下一步不要直接 micro-pull，也不要继续盲扫大 translation；应围绕
`post_bridge_local_z_m006_q_bridge` 做 orientation-aware / approach-seed / staged correction：
先找到一个能同时降低 world X/Y gap 且可规划的 wrist orientation 或分段接近策略，再检查左右
finger 是否在 tail window 内同时进入 handle 两侧 near/overlap；如果
`retention_requires_physx_contact=true`，还必须看到 required-role PhysX contact。之前不要 claim
stable grasp、door opened、`Expert Oracle Score` 或 score。

2026-07-05 Task 5J handoff：候选 manifest 已写到
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_staged_correction_20260705_5j_candidates.json`，
计划文件是
`docs/superpowers/plans/2026-07-05-eos2-contact-retention-orientation-aware-staged-correction.md`。
下一位工程师应一条候选一条 live run，不要用多候选 first-success sweep 代替 retention 证据。
`ori_y_m02_z_m006`、同轴反号 `ori_y_p02_z_m006`、`ori_x_m02_z_m006`、`ori_x_p02_z_m006`、
`ori_z_m02_z_m006` 和 `ori_z_p02_z_m006` 已完成。Z+2deg 只提供双指 world X-gap 一致改善线索；
是否和已知单轴 2mm translation corridor 组合，必须先评审，不是自动执行。所有 5J 结果仍保持
diagnostic-only，直到 strict retention gate 通过。

5J-A 首跑结果已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0800_ori_y_m02/summary_compact.json`。
`ori_y_m02_z_m006` 不是 IK blocker：bridge replay 150 步、post-replay candidate 42 步、close-hold
15 步都执行到 joint target，submit/probe exit code 都是 `0`，18443 server 已停止。真正失败点是
hand/handle retention：tail window 内 bilateral overlap、required-role near、required-role PhysX
contact 都是 `0`，15/15 contact semantics 是 `AABB_OUTSIDE_CONTACT_FRAME`。交接口径：这轮说明小角度
orientation 能让 `z_m006` continuation 路径跑通，但还没有把手指带到把手两侧；下一步继续在同一个
`z_m006` 基线上跑同轴反号和 x/z orientation delta 候选，若 gap 明显改善，再和已知单轴 2mm
translation corridor 组合。当前仍不能 claim stable grasp、
micro-pull、door-open、Expert Oracle Score、policy score、official score 或 full task completion。

5J-B 同轴反号结果也已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0810_ori_y_p02/summary_compact.json`。
这轮 `ori_y_p02_z_m006` 不是环境 blocker：submit/probe exit code 都是 `0`，18444 server 已停止，
bridge replay 151 步并达到 joint target。但 post-replay replan 失败为 `MotionGenStatus.IK_FAIL`，
`successful_candidate_count=0`，没有 action joint trajectory，所以 close-hold 和 retention 都没有执行。
交接口径：Y 轴方向已经有一个可达但没夹住的负号样本，以及一个正号不可达样本；下一步不要把
Y+2deg 和 translation 组合，应转去测 x/z orientation delta。

阶段性 PM 口径：Y 轴两个符号已经给出结论：负号能走但仍偏离把手，正号在当前 post-bridge state /
`z_m006` baseline 下不可达；X 轴也已经由 5J-C/5J-D 覆盖，正负号都没有形成相对所有 required-role
X/Y gaps 的稳定改善。因此 Y/X 都暂不叠 translation，继续验证 z 轴小角度自由度。

5J-C x 轴负号结果也已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0820_ori_x_m02/summary_compact.json`。
这轮 `ori_x_m02_z_m006` 不是 IK blocker：submit/probe exit code 都是 `0`，18445 server 已停止，
bridge replay、post-replay candidate 和 close-hold 都达到 joint target。但 retention 仍失败，左右 finger
仍没有 bilateral overlap / required-role near / required-role PhysX contact；最后 gap 还比 5J-A 更大。
交接口径：X-2deg 这条路能走，但不是改善方向；X+2deg 已由 5J-D 覆盖，后续转 z 轴小角度，不把 X-2deg 和
translation 组合。

5J-D x 轴正号结果也已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0830_ori_x_p02/summary_compact.json`。
这轮 `ori_x_p02_z_m006` 同样不是 IK blocker：submit/probe exit code 都是 `0`，18446 server 在 probe 后已停止；
bridge replay 151 步、post-replay candidate 78 步、close-hold 15 步都达到 joint target。但 retention 仍失败，
左右 finger 仍没有 bilateral overlap / required-role near / required-role PhysX contact；最后 left/right gaps 约
`[0.1352, 0.0564, 0.0]m` / `[0.0888, 0.0692, 0.0]m`。交接口径：X+2deg 能走，但不是稳定改善方向；
相对 best-so-far 5J-A 在所有 required-role X/Y gaps 上仍更差；与 5J-C 的 X-2deg 对照时，只是右指略好、左指更差，
所以 X 轴正负号都不要直接叠 translation。下一步转 z 轴小角度。

5J-E z 轴负号结果也已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0840_ori_z_m02/summary_compact.json`。
这轮 `ori_z_m02_z_m006` 的 bridge replay 仍正常：submit/probe exit code 都是 `0`，18447 server 在 probe 后已停止，
bridge replay 150 步并达到 joint target。但 post-replay replan 对这个候选返回 `MotionGenStatus.IK_FAIL`，
`successful_candidate_count=0`，没有 selected waypoint / action points，因此 close-hold 和 retention 都没有执行。
交接口径：Z-2deg 不是 contact-retention 失败，而是 post-replay IK 不可达；`ori_z_m02_z_m006`
已出现在 attempted candidate record 中，顶层 `waypoint_not_found`
只是没有 selected post-replay waypoint 的派生表现，不是候选标签漏写。Z+2deg 对照已由 5J-F 完成，见下一段。

5J-F z 轴正号结果也已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_orientation_aware_live_20260705_5j_0850_ori_z_p02/summary_compact.json`。
这轮 `ori_z_p02_z_m006` 不是 IK blocker：submit/probe exit code 都是 `0`，18448 server 在 probe 后已停止，
bridge replay 151 步、post-replay candidate 41 步、close-hold 15 步都达到 joint target。但 retention
仍失败，左右 finger 仍没有 bilateral overlap / required-role near / required-role PhysX contact；最后 left/right gaps 约
`[0.1295, 0.0571, 0.0]m` / `[0.0838, 0.0691, 0.0]m`。交接口径：Z+2deg 能走，且相对 5J-A
让左右手指 world X gap 都略小，但 world Y gap 都变大；这是第一个 orientation-only 双指 X-gap 一致改善信号，
不是 stable grasp。下一步先评审是否和已知单轴 Y-gap correction 做 staged 组合，不直接 micro-pull。

2026-07-05 Task 5K staged-combination review 已准备候选 manifest：
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_review_20260705_5k_candidates.json`。
通俗讲，5J-F 的 Z+2deg 让左右手指在 world X 方向都稍微更接近把手，但 world Y 方向更远；5I 的
object-frame X-2mm 单轴 correction 刚好是历史上能补 world Y gap 的方向。因此 5K 先只评审一个最小候选
`x_m002_ori_z_p02`，不做大范围 sweep，也不把它说成已经能抓住。该 review artifact 已被下一段
5K-A live probe 消费；历史边界仍成立：必须看 close-hold tail window 的 bilateral near/overlap 和
required-role PhysX contact，不能直接进入 micro-pull 或算分。

2026-07-05 Task 5K-A live candidate `x_m002_ori_z_p02` 已完成，compact manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_contact_retention_staged_combo_live_20260705_5k_0900_x_m002_ori_z_p02/summary_compact.json`。
这轮结果是 `BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`。通俗讲，它能走到 close-hold：post-replay
replan 成功、selected waypoint 正确、close-hold 15 步也达到 joint target。但 strict retention
仍失败，双指没有 bilateral overlap / required-role near / required-role PhysX contact，15/15 tail records
仍在 `AABB_OUTSIDE_CONTACT_FRAME`。相对 5J-F，5K-A 修回了一部分 world Y gap，但损失了一部分
world X gap；相对 5J-A 则相反。当前仍不能 claim stable grasp、door-open、Expert Oracle Score 或 score；
下一步不能 micro-pull，应先分析更小 staged correction 或改成 contact-frame / handle-frame target generation。

2026-07-05 Task 4c code checkpoint：GenManip 已经把 bridge start-state collision
归因仪表补上，机器可读 manifest 是
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_code_checkpoint_20260705.json`。
通俗讲，现在下一次 live run 不会只告诉我们“cuRobo 说起点撞世界”，而会尽量写出
“它认为撞的是哪个 world obstacle、哪个 robot link/sphere、当时 planner ignore-list
是什么”。probe 也新增了 `--pose-ladder-planner-ignore-list`，用于做最小化验证：
如果证据显示某个具体 obstacle 可疑，就只临时从 planner world 里忽略这个名字再复跑，
看错误是否变化。这个 ignore-list 是诊断工具，不是正式修复；真正修复仍应回到 USD
collision/filter/scene construction。这个 code checkpoint 已经被后续 Task 4c live classify
evidence 消费；单独看它仍只是 `CODE_READY_NOT_LIVE_EVIDENCE`，不能进入抓取、拉门或算分。
review 后已收紧字段语义：`diagnostic_available=true` 只表示诊断跑了；
`attribution_available=true` 才表示已经拿到具体 world/self collision attribution。
诊断会内部保留完整 obstacle list，summary 里的 25 个名字只是 sample；临时逐个开关
obstacle 查询后，会用上一次 planner world config 重建 cuRobo world，降低诊断副作用风险。

2026-07-05 Task 4c live attribution 结果：第一版 live 诊断确认 12/12 个 bridge
candidate 仍是 `INVALID_START_STATE_WORLD_COLLISION`，但因为当时用的是
`get_sphere_distance(... compute_esdf=True)`，只能说明 diagnostic 跑了，不能定位具体
obstacle。按 cuRobo 源码复核后已改成与 `check_start_state` 一致的
`get_sphere_collision` classify 路径；新版 live evidence 在
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_live_classify_20260705_194133/`。
结论很清楚：12/12 个 candidate 的 world-collision attribution 都指向
`/World/labutopia_level1_poc/obj_table/surface/mesh`，robot link 是 `panda_hand`。
随后只把这个 table surface mesh 加到 diagnostic planner ignore-list 复跑，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_bridge_start_state_collision_attribution_ignore_table_surface_20260705_194441/`；
结果从“起点 world collision”变成：第一条 bridge candidate 是普通 `IK_FAIL`，第二条
`approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 在 world refresh
下规划成功，`trajectory_point_count=152`。产品口径：现在已经定位到“桌面碰撞模型/手爪起点
clearance”是挡住 bridge planning 的主因；但 diagnostic ignore-list 不是正式修复，下一步要
决定是调整 robot reset/base/hand clearance、修 table surface collision mesh/filter，还是用有
证据的 planner support-surface exclusion。

2026-07-05 Task 4d 规划更新：下一步不直接把 table surface 从 planner 里删掉。我们先做
**Support-Surface Clearance Contract Repair**，通俗说就是量一下“机器人手爪和桌面到底
有没有真实压在一起”。需要记录 reset 后的 robot base、关节、夹爪、end-effector pose、
table surface mesh 的世界包围盒，以及 cuRobo 报碰撞的 `panda_hand` sphere center/radius。
如果手真的低到桌面里，就修 reset/base/joint；如果手有实际 clearance 但 planner 模型仍报碰撞，
就修 table collision mesh/filter；只有证据证明这是安全的 planner-only 支撑面处理时，才允许写
explicit support-surface exclusion，而且不能改变 PhysX 真实任务碰撞。这个 Task 4d 完成前，不能
汇报 stable grasp、micro-pull、door opened、Expert Oracle Score 或 policy score。

2026-07-05 Task 4d.3 live 结果与 4d.4A frame-aware live 复跑：旧 frame 复核和新同 frame 审计都已经跑完。旧证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_support_surface_clearance_audit_stage_bbox_envfix_20260704_213347/`，
产品口径是“不能直接把桌面从 planner 里删掉”。这次 submit/probe 都是 exit `0`，reset 成功，
12 个 bridge candidate 都进入 cuRobo world-refresh planner；runtime 也已经能从 USD stage
prim path 读 table surface AABB，并写出正式的 support-surface clearance records。旧记录里所有
12 条都显示 `panda_hand` 的 collision sphere 在 Z 方向穿进了 support surface：
第一条 table top z 约 `0.773m`，手爪 sphere bottom z 约 `0.051m`，clearance margin
约 `-0.722m`。但现在要加一个重要解释：这个数值来自旧诊断字段，sphere 实际来自 cuRobo
planner/reference frame，table AABB 来自 USD world frame，两者没有先对齐，所以不能把
`-0.722m` 当成真实物理高度差。通俗说，planner 不是“无缘无故嫌桌子挡路”，但当时还不能说
“手已经真的在桌面下面”。GenManip 代码已经加保护：
新诊断输出 `sphere_center_planner_frame` / `sphere_frame=planner_reference_frame`，frame 不一致时
`clearance_status=unverified_frame_mismatch`，并禁止 planner-only support-surface exclusion。
随后新 evidence 在
`docs/labutopia_lab_poc/evidence_manifests/eos2_support_surface_frameaware_clearance_audit_20260704_221731/`：
submit/probe exit code 都是 `0`，12/12 条记录同为 `planner_reference_frame`，
`clearance_margin_m` 约 `-0.011760663m`，所以 planner-only support-surface exclusion 仍不允许。
Task 4d.4B 用 base z +0.02m 做隔离验证后，start-state collision 消失，第二个 bridge candidate
规划出 152 个点。Task 4d.4C 进一步记录 observed robot base z=`0.730000019m`，确认配置进入
真实 robot prim。Task 4d.4D 又证明：保留 base z=`0.71m` 只换 reset joint seed 不能清掉
table surface vs `panda_hand` start-state collision；只改 base z=`0.73m` 且不带 solver/self-collision
override 可以清掉该 blocker。这把下一步优先级排清楚了：先把
`position: [-0.4, 0.0, 0.73]` 已固化成 POC-specific reset/base contract；table collision
representation 继续保留为审计项，但现在不走 exact ignore table。之后才继续 bounded execution、
抓把手、微拉门和 Expert Oracle Score。

2026-07-04 历史诊断路径：EOS-2xC6 live witness 已经证明
`PhysX contact` channel 可用，但 6/6 candidate 仍没有 required-role finger-handle
`PhysX contact` records。通俗讲，debug 盒子里手指看起来已经夹到把手附近，但物理引擎
还没有承认 `panda_leftfinger` 和 `panda_rightfinger` 同时真实接触 DryingBox handle。
因此当时不能汇报 stable grasp、micro-pull、door opened、`Expert Oracle Score` 或 policy
score。当时下一步按
`docs/superpowers/plans/2026-07-04-eos2xc7-physx-contact-generation-collider-attribution-repair.md`
执行 C7-A：先做只读 contact/collider attribution，检查 contact report wiring、handle
collider owner、collision filter / kinematic、以及 contact offset / rest offset 读数；C7-A
不修改这些物理参数，避免把定位原始失败变成干预实验。
2026-07-04 代码侧 checkpoint：GenManip 已补齐第一层只读 telemetry 和单测，能在下一次
live run 中输出 `PhysX contact` header attribution、verified handle collider owner matching、
unmatched required-role pairs、AABB selected pair attribution，以及 contact report pre-step
setup attribution。三份相关单测分别为 `25 passed`、`22 passed`、`233 passed`。产品口径：
我们刚完成的是“把诊断仪表装上”，还没有跑 C7-A live witness，也不能说已经抓住、拉开门或得分。
review 后口径补充：C7-A 的“只读”不是说完全不挂观察 API；`PhysxContactReportAPI`
是为了让物理引擎把 contact report 发出来的观察仪表，C7-A 只记录它挂在哪里，不改
接触阈值、collision filter、kinematic 或任务语义。AABB 诊断里也已收紧 handle 识别：
`handle_support`、`handle_visual` 等相邻部件不能再被当成真正把手接触。
2026-07-04 candidate queue 补充：C7-A 的 6 行候选清单已经准备并校验，文件是
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7_candidates.tsv`。
它只说明下一轮要按 `w024` / `w028` 两个 C6 baseline 分别做 attachment audit、
collider owner audit 和 filter/offset readout；还不是 live witness。清单里显式记录
LabUtopia-local C6 analysis manifest 目前缺失，后续发布 C7 live evidence 前需要补齐或在
C7 analysis JSON 中保留 GenManip-local source paths。
2026-07-04 first live witness 补充：第一条
`eos2xc7_w024_base_attachment_audit` 已实际跑通 submit / probe，fresh
`run_id=labutopia_eos2xc7_physx_contact_generation_collider_attribution_eos2xc7_w024_base_attachment_audit_20260704_223000_eos2xc7`，
exit code 都是 `0`，并产出 297 行 trace 和 `contact_frame_summary.json`。但这次不是
contact attribution 成功证据：run 在 `approach_near` 硬门失败，没有进入 `grasp_hold`
窗口，`post_close` sample count 是 0。通俗讲，“诊断仪表和考场链路已经能工作，但机器人
还没稳定走到能检查真实抓把手的位置”。因此 `contact_pair_count=0` 不能被解读为 handle
collider 不会产生接触；也不能汇报 stable grasp、micro-pull、door opened、Expert Oracle
Score 或 policy score。

当时下一步工程动作：先不要改 `contact_offset`、`rest_offset`、collision filters 或
kinematic flags，也不要盲跑剩余 5 行 collider/filter 候选。先跑一条只读 bounded
`controller-readback-comparator`，固定 `--controller-readback-waypoint-label approach_near`、
`--open-width-m 0.024`、`--close-width-m 0.010`，看命令位姿和实际手爪 readback 为什么没有
收敛。这个结果会决定后续是修 approach/controller 参数，还是回到 C7-A collider attribution。
2026-07-04 bounded readback 结果：上述只读 comparator 已跑，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_near_readback_20260704_124339/`。
submit / probe exit code 都是 `0`，但状态是
`FAIL_CONTROLLER_READBACK_COMPARATOR_NO_IK_TARGET`。通俗讲，这一步告诉我们“不是已经碰到
把手之后物理接触没出来”，而是 `approach_near` 目标还没被 IK / controller 变成可用动作；
目标和实际手爪位置误差约 `0.525 m`。所以当时下一步从 contact/collider 问题临时前移到
approach target / IK / readback 链路：先确认 target frame 是否构造错、目标是否不可达，或者
只是 comparator 没暴露 successful IK debug。这个结果仍不能汇报 stable grasp、door opened、
Expert Oracle Score、policy score 或 official score。

2026-07-04 `approach_pre` 对照结果：为排除“诊断工具完全看不到 IK debug”这个可能性，我们
又跑了更早一步 `approach_pre` 的只读 comparator，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_readback_20260704_125312/`。
这次 `submit/probe` 都正常退出，`parse_only_ik_success=true`，说明 IK debug 是能暴露的；
但把这个 IK target 一步下发给机器人时，`panda_joint4` 单步跳变约 `1.65 rad`，超过
`1.0 rad` 安全阈值，因此终止在 `arm_state_jump_too_large`。通俗讲，问题已经从“是不是
物理接触没出来”进一步前移到“机器人到达接近点的动作太猛/跨度太大，安全保护先拦住了”。
当时下一步应跑 `bounded-joint-lead-in`，把同一个目标拆成小步走；仍不能汇报 grasp、开门、得分
或 official baseline。

2026-07-04 bounded joint lead-in 结果：已跑分步版本，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_approach_pre_bounded_lead_in_20260704_130833/`。
这次命令没有再“一步跨太大”：每步都被限制在 `0.05 rad`。但机器人真实 readback 在后段
step 52-54 开始发散，最后 `panda_joint6` 单步跳变约 `1.386 rad`，触发安全保护；
最终距离目标还差约 `0.653 rad`。通俗讲：我们已经证明“简单把大步拆小步”还不够，问题不是
contact/collider，而是接近点本身的 target/orientation/reachability/controller 稳定性还没闭环。
当时下一步先查 target frame、手腕姿态、碰撞/clearance 和后段 controller timeline，然后转向
EBench 原生任务那种 object-frame waypoints + per-waypoint cuRobo planning 的 oracle
方式。只有实现里显式 refresh / log cuRobo world obstacles 后，才把它称为完整
`collision-aware planning`。

2026-07-04 target-frame / reachability audit 结果：派生审计已落盘到
`docs/labutopia_lab_poc/evidence_manifests/eos2xc7_physx_contact_generation_collider_attribution_20260704_223000_eos2xc7/eos2xc7_w024_target_frame_reachability_audit_20260704_132909/`。
它确认当前 audited path 的 base frame 一致，不是主嫌；但不排除后续 object-frame convention
仍需单独校验。关键差异在 oracle 形态。EBench microwave 的 expert 不是直接 replay 一条
固定 joint trajectory，也不是只给一个 IK 点，而是把 task-level manual `custom_motion`
waypoints 交给 runtime：其中既有相对 `microwave` 的 `object_frame` 目标，也有
`robot_frame` staging，再让 cuRobo 每个 waypoint 现算轨迹。
DryingBox 后续也应按这个模式定义 object-frame waypoint contract 和 per-waypoint planner。
因此短期先暂停继续跑 C7 contact/collider 剩余候选；等 planner 路径能稳定产生 `grasp_hold`
窗口后，再回到 contact attribution 和 metric score。

源码口径：EOS 当前 `mobile_manip/microwave` registry 指向
`configs/tasks/ebench/mobile_manip/test_mini/microwave.yml`；GenManip 的
`test`、`test_mini`、`val_train`、`val_unseen` microwave 配置共享同一类 manual 模板。
它们的开门段从 `custom_motion` 开始，一部分目标带 `rel_object_uid: microwave`
和 `type: object_frame`，同时也包含 `robot_frame` staging。
`custom_motion.py` 先把这些 task-level targets 转换成 world/robot pose，再走
`BaseEmbodiment.plan_pose` 和 cuRobo `MotionGen.plan_single` 生成 joint trajectory。
评分侧读取 articulation qpos / object relationship；也就是说，expert 的本质是
“task-level motion intent + runtime planning + metric readback”，不是“固定轨迹文件通关”。
补充边界：microwave articulated asset 元数据里确实可能有 `skills.open_door.skill_trajectory`，
但这不是本轮审计到的 `microwave.yml` manual demo 的直接执行来源。给 DryingBox 迁移时，
我们要复用的是 task-level `custom_motion` waypoint 方案，而不是播放 asset-level
skill trajectory。
DryingBox 当时的下一步应复用这个范式，而不是继续调单个 absolute IK target。
下一阶段实施计划已写入
`docs/superpowers/plans/2026-07-04-dryingbox-object-frame-curobo-oracle.md`。

2026-07-04 object-frame oracle Task 1-4a 交接状态：GenManip worktree
`/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback`
已经新增 `build_dryingbox_object_frame_waypoints` 纯合同、对应单测、
`build_waypoint_planning_record` claim guard，以及
`--probe-mode object-frame-curobo-planner-smoke` 的 client-side planner-interface
diagnostic。Task 4a 已补 `POST /plan_object_frame_waypoints` 这条 planner-only 通道，
并在 GenManip server、worker pool、Ray worker、env helper、genmanip-client 和 probe
层都有单元/契约测试。产品口径：现在已经把“专家该去哪几个相对 handle 的点”、
“runtime 怎么把这些点交给 cuRobo 规划”和“planner 证据该怎么记”串成 API seam。
但这仍是单元/契约闭环，不是 live planner smoke：还没有启动 Isaac/cuRobo server
对真实 DryingBox scene 跑通 approach_pre、approach_near、contact。当时下一步进入 Task 4b
live evidence run。注意：即使 Task 4a 的 planner world refresh 单元证据为 true，也只能说
“planner refresh 被调用并返回成功”；完整 collision-aware planning 还需要 live evidence
证明 obstacle inventory 已进入 cuRobo world 且 collision checking active。

2026-07-04 object-frame oracle Task 4b live 状态更新：已经启动真实 Isaac/cuRobo server
并跑过 `object-frame-curobo-planner-smoke`。最新证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_curobo_oracle_debug_20260704_155243`，
`run_id=labutopia_eos2_object_frame_curobo_planner_smoke_debug_20260704_155243`。
这轮结论不是“环境没起来”：`CUROBO_SRC`、planner-only endpoint、reset-prep、
`world_refresh_status=success` 和 side-effect guard 都已经通过。真正的 blocker 是
三个位点没有生成 trajectory。cuRobo debug 进一步显示：完整 world refresh 下三个位点都是
`MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`；clean reset 对照里
`refresh_world=false` 又变成 `MotionGenStatus.IK_FAIL`。给 PM 的白话解释是：
现在考场和规划器都通了，但“专家手要伸到哪里、手腕怎么摆”这套默认姿态还不对；
不加载障碍时机器人解不出这个手部姿态，加载障碍后规划器还认为起点已经和某个世界障碍相撞。
因此当时下一步不是算分，也不是调材质，而是做 `pose/orientation ladder` 和
`start-collision attribution`，先让 `approach_pre` 成为 IK-solvable，再找出
`INVALID_START_STATE_WORLD_COLLISION` 具体来自哪个 obstacle / robot link。

2026-07-04 object-frame oracle Task 4b follow-up：第一轮 `pose/orientation ladder`
已经完成，证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_pose_ladder_20260704_162947/`，
`run_id=labutopia_eos2_object_frame_pose_ladder_20260704_162947`。这轮不是盲跑
score，而是只问一个更小的问题：把手前方这些候选位姿，Franka/curobo 有没有任何一个能先
算出 IK？结果是 20/20 个候选都 `MotionGenStatus.IK_FAIL`，候选覆盖
`offset_x_m=-0.04/-0.08/-0.12/-0.16/-0.20` 和
`identity/yaw_90/yaw_-90/yaw_180`。这轮故意没有 fresh world refresh，
所以还不能把失败归因为碰撞；它只说明第一批“手要伸到哪里、手腕怎么摆”的 pose basis
仍不够。当时下一步要用真实 reset/readback 里的 handle pose、当前 EE/wrist orientation、
native controller approach orientation 和 Y/Z clearance offset 扩展 ladder；先找到
至少一个 IK-solvable `approach_pre`，再回到 world refresh 和 start-collision attribution。

2026-07-05 bridge live evidence 更新：这套 ladder 已经完成一轮 no-refresh 和两轮
world-refresh 证据。证据目录是
`docs/labutopia_lab_poc/evidence_manifests/eos2_object_frame_bridge_ladder_20260704_181425/`。
no-refresh 下第二个候选
`approach_pre_bridge_f_0.750_to_approach_pre_x_-0.080_ori_identity` 可以规划出
152 个 trajectory points，说明 reset 到把手之间存在中间可达点；但第一次 world-refresh
复跑在 reset 阶段遇到 Ray OOM，不能作为 planner/collision 结论。retry2 中 reset 成功，
12 个候选的 world refresh 都成功，但 planner debug 全部是
`MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`。历史 PM 口径是：我们已经从“有没有中间路”
推进到“加载真实障碍后，规划器认为起点和世界有碰撞”。这条 attribution 后续已经完成，具体
blocker 是 table surface mesh vs `panda_hand`；Task 4d.3 clearance audit 也已完成，且
2026-07-05 frame 复核确认旧记录混用了 USD world frame 的 table AABB 和 cuRobo
planner/reference frame 的 sphere。当时的下一步是 Task 4d.4A frame-aware clearance audit；
这条路线随后已被 Task 4d.4A、formal reset/base contract、Task 5A-5I、5K-A、5L 和 5M live
evidence 消费。当前 blocker 见本文顶部 5M state-reference rerun：route-bound bridge replay
正常，但 centerline candidate solver 因 `PAD_DEPTH_MISS` 尚未生成 numeric candidate。

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

AAN-ready 的一句话定义：它不是只复制一个 USD 文件；它把 dependency、material、
physics / articulation where applicable、producer runtime smoke 和 benchmark contract
打包成下游 consumer 可以逐项验收的清单。

2026-07-02 视觉复核补充：7 月 1 日的旧 AAN producer render 只保留为问题诊断图。
它当时有两个肉眼可见问题：整机异常偏红，并且相机从背面/上方拍摄，看不到门、handle
和全貌。AAN-11 已经修复 producer 侧红色异常材质，并补齐 handle-clear front showcase。
本次又固定一套 native vs AAN 正面对比相机：两张图都能清楚看到门、handle、控制面板
和观察窗，构图可比，AAN 侧没有大面积 solid red fallback。边界仍要保留：独立视觉
审阅结论是 `WARN`，因为 native rack 是红色线框而 AAN rack 是深灰/黑，控制面板显示、
小脚颜色和表面 roughness / brightness 仍有可见差异；consumer rerun 日志也还有
`mdlc_compiler_error_count=16` 和 `relationship_out_of_scope_count=70`。因此可以说
“consumer live smoke PASS + no solid red fallback”，还不能说 full visual/material
parity 或 source-native full material closure。

## LabUtopia AAN-Ready Package 接入 EBench 计划（6 stages）

目标：不再继续手工修 DryingBox USD / MDL / articulation，而是把 ConvertAsset 已闭环
的 AAN-ready package 作为输入，完成 LabUtopia / GenManip consumer 接入。

六个阶段：

| Stage | 产品别名 | 工程名称 | 通俗解释 | 当前状态 |
|---|---|---|---|---|
| 1 | 收货锁定 | **AAN package intake** | 固定收货对象，确认我们消费的是哪一个 ConvertAsset package。 | **已完成** |
| 2 | 验货准入 | **Consumer manifest check** | 收货验货，确认 schema、runtime profile、benchmark profile、stage gates、entrypoints、blocked reasons、waivers 都满足 consumer 准入。 | **已完成** |
| 3 | 挂进任务目录 | **Task-root wiring and dry-run composition** | 把 `asset.usd`、`task_config`、`required_prims`、`evaluator` 挂到 LabUtopia / GenManip task root，并确认路径和 required prims 能解析。 | **已完成** |
| 4 | 跑本地任务链路 | **AAN runtime adapter and live eval smoke** | 先确认 live runtime 真正加载 AAN package，不是旧 overlay；再重跑 `level1_open_door` reset / step / render / metric / logging smoke。 | **已完成 / AAN-11 consumer rerun PASS** |
| 5 | 产出 PM 证据 | **PM evidence and weekly HTML update** | 更新周报 / PM 页面，展示 Stage 4b live smoke、AAN render、固定 native vs AAN 正面对比与 claim boundary。 | **进行中 / 本文档和周报已更新** |
| 6 | 防偷修包并复制验证 | **Regression, boundary, and replication hardening** | 增加 no-local-repair 保护，并把同一套收货、验货、挂载、runtime adapter preflight / smoke 流程复制到新资产；复制验证不等于完整 runtime / policy 评测成功。 | **已完成 / PASS：DryingBox no-local-repair PASS；`MuffleFurnace` / `Beaker_01` Stage 1-4b generic smoke PASS** |

现在可以在内部汇报：DryingBox AAN-ready package 已被 LabUtopia / GenManip consumer
接入并通过本地 live eval smoke。Stage 6 是流程固化和复制，不阻塞 DryingBox 的单资产
接入结论。

当前已经可以说：AAN-11 DryingBox AAN-ready package 已经完成 LabUtopia / GenManip
consumer rerun。通俗讲，就是“收货、验货、挂到任务根目录、给 EBench 做好 DryingBox
AAN 专用入口，并用 fresh run 跑通 reset / step / metric / logging，且确认这个入口没有
偷偷指回旧 overlay”。

当前仍不能说：official leaderboard score 已完成、模型已经解决任务、benchmark-wide
任意资产都自动可评、full visual material parity 已证明。

分数四层口径：

| 层级 | 通俗解释 | 当前状态 | 能否当作模型成绩 |
|---|---|---|---|
| 0 分 smoke | 当前 eval client 能跑完整条任务链路，但默认 action / policy 没完成任务。 | 已有证据 | 不能 |
| Franka expert oracle | 把 LabUtopia native Franka expert 当作标准答案，用 EBench metric 打分。 | 已完成：S2-R1E full-env repaired replacement replay 已产出 `score=1.0` / `success_rate=1.0` / `metric_score=[[[1.0]]]`、终态门角 `41.715865deg`、`succ_cnts=59`、terminal camera artifact 和 canonical `camera2.mp4` | 不能 |
| Lift2 oracle / retarget | 把专家答案迁到 Lift2/R5a 16D action contract 后，用同一 metric 打分。 | F2a 已关闭当前 lower-level official action branch；Gate1V-3 native contract incomplete/no-live | 不能 |
| Real policy score | 真实模型通过 EvalClient 输出标准 action，由 EBench metric 判分。 | 后续 | 可以作为 policy 质量证据；是否 official 另看提交流程 |

Stage 4 内部有两个硬门：

| 子步骤 | 通俗解释 | 状态 |
|---|---|---|
| Stage 4a | 入口预检：证明 AAN wrapper 指向 mounted AAN package，不是旧 overlay。 | 已完成 |
| Stage 4b | live smoke：用 fresh `run_id` 证明 reset、step、render、metric、logging 都通过，并产出 `aan_*_runtime_smoke_*.json`。 | DryingBox 已完成 / PASS；`MuffleFurnace` generic smoke 已完成 / PASS；`Beaker_01` generic smoke 已完成 / PASS |

DryingBox Stage 4b 和 AAN-11 consumer rerun 的最终 manifest 都是 `PASS`，因此可以说
“DryingBox AAN package 通过本地 EBench live smoke；AAN-11 新包也已经被 consumer
重跑验证”。这句话只覆盖 DryingBox 本地 smoke，不覆盖 official leaderboard、policy
success、semantic task success 或 full visual material parity。

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
最终颜色都已经正确显示。7 月 1 日旧 producer render 的红色异常材质曾把
full visual/material parity 留成 follow-up；AAN-11 已解决 broad red fallback，但固定
native vs AAN 对比仍显示 rack、控制面板和小脚等局部材质差异。

配套测试：

```text
cd /cpfs/user/zhuzihou/dev/ConvertAsset
python -m pytest tests/test_asset_application_normalizer_cli.py \
  tests/test_asset_application_normalizer_pm_and_mjcf.py -q

29 passed
```

## 2026-07-02 AAN-11 consumer rerun 证据

AAN-11 新包来源：

```text
/tmp/aan11_real_packages_final/dryingbox_runtime
/cpfs/user/zhuzihou/dev/ConvertAsset/docs/records/evidence/2026-07-02-aan-11-material-runtime-closure/runtime/dryingbox/manifest.json
package_digest_sha256=a859c5a997c77ea9874155070c03879d2cc9ac41e0b4c30e7c8a07719b1fe32e
asset_usd_sha256=bcebeeea33cb30cf0d667e27ebda760815b0b487bffaff6e6ddb78aea2664c23
```

LabUtopia / EBench consumer final run：

```text
manifest=docs/labutopia_lab_poc/evidence_manifests/aan11_dryingbox_runtime_smoke_20260702_1803.json
run_id=labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803
evidence_dir=docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803/
runtime_usd_name=scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene
submit_exit_code=0
eval_exit_code=0
reset_observed=true
step_1000_observed=true
score=0.0
success_rate=0
result_info=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/eval_results/ebench/labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803/ebench/labutopia_lab_poc/aan11_lift2_candidate/level1_open_door/000/result_info.json
```

这次 final run 依赖两个 consumer runtime bootstrap 条件；完整规范见
[`aan_runtime_environment_bootstrap.md`](aan_runtime_environment_bootstrap.md)，后续应把它实现进 runner：

```text
CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
LABUTOPIA_POC_ASSETS_OVERLAY_ROOT=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/saved/assets
saved/assets -> /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets
```

前两次 diagnostic run 不是资产失败：

- `labutopia_aan11_lift2_stage4b_20260702_1755`：Ray worker 没继承
  `CUROBO_SRC`，报 `ModuleNotFoundError: No module named curobo`；
- `labutopia_aan11_lift2_stage4b_envfix_20260702_1759`：没有设置
  `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT`，consumer 回落到旧 overlay root，AAN-11 wrapper
  没有 package symlink，场景 composition 为空。

固定 native vs AAN 正面对比相机：

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

独立视觉审阅结论：构图和 pair comparability 是 `PASS`，AAN 侧没有明显 broad red
fallback 或严重几何损坏；整体为 `WARN`，因为 native rack 是红色线框、AAN rack 是深灰
/ 黑，控制面板显示和按钮清晰度/饱和度不同，小脚和表面 roughness / brightness 也有差异。

PM 安全说法：

```text
AAN-11 DryingBox package 已经进入 LabUtopia / EBench consumer 并通过本地 live smoke。
固定正面对比图证明 AAN 没有大面积红色 fallback，主体几何和操作面可比。
但 full visual/material parity 仍是 OPEN，需要 close-up material parity follow-up。
```

禁止说法：

```text
official leaderboard score 已完成。
policy 已经解决 level1_open_door。
AAN-11 和 native 外观已经逐项一致。
consumer log 的 MDL compiler warning 已经全部消失。
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
| expert oracle scored | 专家答案在同一 EBench metric 下能得分 | Franka expert 或 Lift2 oracle / retarget 的标准答案可被评分器识别 | 真实模型已经达到该分数 |
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
> 7 月 1 日旧 DryingBox producer render 曾出现红色异常材质，AAN-11 已把 broad red fallback
> 从最新图里消掉；但固定 native vs AAN 对比仍有 rack、控制面板和小脚等局部材质差异，
> consumer 日志也还有 MDL compiler / material:binding warning，所以不能宣称
> source-native full material closure 或 full visual parity。

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
4. 单独规划 visual/material parity follow-up：AAN-11 已解决旧 DryingBox producer render
   的 broad red fallback 和背面/俯视 camera 问题，但固定 native vs AAN 对比仍有 rack、
   控制面板、小脚和表面质感差异；AAN-11 consumer rerun 仍有
   `mdlc_compiler_error_count=16` 和 `relationship_out_of_scope_count=70`。
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

## 2026-07-04 EOS-2 DryingBox Oracle Update

本节是 2026-07-04 的历史快照，保留用于解释早期 bridge / collision 归因链路。当前最新状态见本文顶部
2026-07-05 Task 5K prepared review 已被 5K-A live evidence 消费：5J-F 的 Z+2deg
orientation signal 和 5I 的 object-frame X-2mm 单轴 correction 收敛成
`x_m002_ori_z_p02` 单候选后，live probe 已跑完。结果不是 IK blocker，而是
`BLOCKED_CONTACT_RETENTION_OUTSIDE_FRAME`：close-hold 能执行，但双指仍没有 required-role
near/overlap/PhysX contact。当前不是回到本节的旧 reset/base/joint/bridge clearance，也不是批准 broad sweep
或 micro-pull。

当时 open-door oracle 还没有进入 score。历史证据把问题拆成了三层：

1. `eos2_object_frame_pose_ladder_richer_20260704_173743` 跑了 600 个 handle-side
   候选位姿，包括 X/Y/Z clearance、fixed yaw、reset EE orientation 和 native-open
   orientation，全部是 `MotionGenStatus.IK_FAIL`。这说明问题不是简单调一个角度或
   少量 clearance 就能解决。
2. `eos2_object_frame_pose_ladder_reset_seed_20260704_174832` 把 reset 后当前 EE pose
   转成 handle object-frame seed，第一条就规划成功，`trajectory_point_count=149`，
   且 `runtime_side_effect_reported=false`。这说明 planner-only endpoint 和
   reset-seed object-frame round-trip sanity 是通的。
3. `eos2_object_frame_bridge_ladder_20260704_181425` 的 no-refresh bridge 找到第一个
   可规划中间点，`trajectory_point_count=152`；但 world-refresh retry2 中 reset 和
   world refresh 都成功后，12 个候选全部变成
   `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`。

给产品经理的通俗口径：

> 我们已经证明“规划器能接入、reset seed 的坐标往返 sanity 能闭环”，也证明“不带真实障碍时，
> 从 reset 到把手之间有一个中间点可以规划”。但一旦把 cuRobo world obstacles 打开，规划器会把
> 起点判成 `INVALID_START_STATE_WORLD_COLLISION`。这个具体 obstacle 已经定位出来：table
> surface mesh vs `panda_hand`。live no-extra-ignore clearance audit 也已经跑完；旧记录因为
> 桌面 AABB 和手爪 sphere 不在同一个坐标系，不能直接当物理高度差。我们已经补跑了同 frame
> 审计：12/12 条都是 `planner_reference_frame` 下的 `measured_same_frame`，clearance 约
> `-1.18cm`，所以不能把 table surface 直接从 planner 里豁免。这是当时的 blocker 解释；
> 后续 Task 4d.4E 到 Task 5M 已经消费了这条路线，当前 blocker 已推进到 route-bound
> centerline candidate generation：旧 `NoneType` 输入 bug 已越过，但 bilateral contact-frame
> solver 仍因 `PAD_DEPTH_MISS` 生成不了 numeric candidate。

禁止升级声明：

```text
stable_grasp=false
micro_pull_ready=false
door_opened=false
expert_oracle_score=false
policy_score=false
official_leaderboard_score=false
full_collision_aware_planning=false
```

## EOS-2 Task 4d.2 Update, 2026-07-05

PM 口径：

> 上一步我们已经定位到“开门专家轨迹不是简单 replay 旧轨迹”，而是要像 EBench
> microwave 那样用 task-level `custom_motion` waypoints + runtime cuRobo planning。
> 现在卡在更具体的一点：
> world refresh 打开后，cuRobo 认为起点已经和桌子碰撞。我们补的诊断钩子已经被 Task 4d.3
> live run 消费：它同时看到了“桌子的 runtime AABB”和“机器人被判碰撞的 sphere
> 坐标/半径”。2026-07-05 复核确认旧负值来自不同 frame，不能直接当物理高度差；随后新的
> frame-aware live audit 已经把 AABB 和 sphere 都转到 `planner_reference_frame`，结论仍是
> `panda_hand` sphere 比 table top 低约 `1.18cm`。结果是：不能 exact ignore table；
> 下一步要修机器人 reset/base/joint/bridge clearance 或 table collision representation。

已完成的工程动作：

```text
GenManip planner server:
  支持 support_surface_uid=table
  自动读取 table runtime AABB
  把 start_state_collision.world 转成 support_surface_clearance_records
  记录 support_surface_aabb_source 与 support_surface_reference_prim_path：
    support_surface_prim_path = cuRobo 报出的具体 obstacle
    support_surface_reference_prim_path = 读取 AABB 的 scene/table 实体
    support_surface_aabb_source = payload 或 scene_uid:table
  planner-only exclusion 只在 exact candidate、AABB 与 sphere 已经同 frame、
  Z clearance 非负、XY footprint overlap 同时满足时才可被诊断字段标成 allowed

online probe:
  新增 --support-surface-uid / --support-surface-prim-path /
       --support-surface-planner-ignore-candidate / --support-surface-aabb-min/max
  pose ladder trace 会保留 support_surface_clearance_records
```

边界：

```text
frame_aware_live_clearance_pass=BLOCKED_SAME_FRAME_NEGATIVE_CLEARANCE
planner_only_table_ignore_decision=REJECTED_BY_NEGATIVE_CLEARANCE
stable_grasp=false
micro_pull_ready=false
door_opened=false
expert_oracle_score=false
policy_score=false
official_leaderboard_score=false
```

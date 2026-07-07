# EOS2 Gate 1U-A Lift2 Robot Contract Fork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After C2f stopped the Franka/current-layout/native-route contract, start the Lift2/R5a contract fork without blind expert-score attempts.

**Architecture:** Gate 1U-A changes only the robot/action contract first: `manip/lift2/R5a`, 16D `joint_position` action, Lift2 camera/observation schema, and the same DryingBox door-angle metric. It first audits static config authority, then runs one live schema/action probe, and only after that designs a Lift2 oracle or retarget path. It does not reuse Franka joint actions or treat smoke `score=0.0` as expert failure.

**Tech Stack:** LabUtopia docs, GenManip task configs, `lift2_eval_contract_probe.py`, EBench / GenManip EvalClient, Isaac Sim 4.1, conda env `embodied-eval-os-sim-isaacsim41-genmanip-py310`, JSON evidence manifests.

---

## PM Summary

C2f 已经给出清晰结论：Franka/current-layout/native-route orientation 这条 C lane 在“真实把手正前方等价目标”上仍然 `IK_FAIL`，所以不能再继续扫 offset。下一步推荐 A lane，不是因为 A 一定能开门，而是因为 A 直接验证产品目标里最重要的 official Lift2/R5a baseline 口径。

A lane 的第一步也不是算分。先问三件事：Lift2 task config 是否真的指向 `manip/lift2/R5a`；runtime 是否给出 Lift2 baseline 需要的 camera / observation；16D action 是否能被 EBench live step 接收。只有这些通过，才有资格继续做 Lift2 oracle / retarget 和后续 `Expert Oracle Score`。

2026-07-06 A1 第一次 live probe 给出明确 blocker：client 连上 server、看到 worker `0`，但 reset result 一直 pending。根因证据指向旧 overlay root 缺 `robot_usds/lift2/robot.usd`。随后 A1a 已固定并预检 effective assets root，A1b corrected live 已证明 Lift2 能 reset、返回 observation/camera、接收 16D `joint_position` action，并返回 reward/success fields；A1b 唯一 blocker 是 logging metadata 缺 `episode_id`、`seed`、`result_path`、`stdout_path`、`stderr_path`。A1c 只修 logging evidence，不改 route/oracle，fresh live 后全部 schema rows PASS。

当前 A lane 的最新状态是：A1c/A2 已通过，A3 first live 暴露 `arm=default`，A3a/A3b 已把 revised
route 固定成 `right` arm 并通过 dry check；A3c revised right-arm live 也已按规则只跑一次。A3c 的
进步是：旧的 `arm=default -> planner_update_unavailable` 已经不是第一 blocker，两个 waypoint 都走
`arm=right`，world refresh 也成功。新的 blocker 是 reset/start-state 层：cuRobo 在检查目标可达性前，
先判定 Lift2 某个 collision sphere 和 table mesh 相交，状态是
`MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`，`executed_steps=0`。通俗讲，Lift2 标准答案已经
改成右臂能读懂的语言，但机器人还没开始走向门前，先被判定“起跑姿势撞桌子”。下一步只允许 A3d
read-only / zero-live root-cause review，不允许继续扫 offset、contact、micro-pull 或直接算
`Expert Oracle Score`。

2026-07-06 A3e diagnostic request 已执行，A3f 被 stop/go 明确挡住：runner 产出 2 条
`support_surface_clearance_records`，frame 已经对齐到 `planner_reference_frame`，但
`clearance_margin_m=-0.6237133788083942`，`physically_intersecting_support_surface=true`，
`planner_only_support_surface_exclusion_allowed=false`。因此不能把 table 做 blind ignore，也不能进入
下一次 revised live。raw runner classification 仍是历史泛化标签；canonical A3e status 是
`A3E_SUPPORT_SURFACE_CLEARANCE_DIAGNOSTIC_EXECUTED_NO_GO_A3F_BLOCKED_RESET_LAYOUT_COLLIDER_CONTRACT`。
下一步改为 Lift2 reset/layout/collider contract repair review：初始 base/joint seed、table obstacle
AABB/碰撞体拆分、sphere 17 link mapping。

2026-07-06 A3g reset/layout/collider review 已把这个 no-go 进一步收窄：`sphere_index=17` 按
R5a cuRobo config flatten order 映射到 right-arm `link6` sphere0，半径 `0.02822m` 加
`0.004m` collision buffer 后正好对上 A3e 的 `0.0322199985m`。更关键的是，A3e 报告的 table obstacle
path 是 `/obj_table/Bespoke_Booth_Table_Black_Nickel_0/...` 的完整视觉桌体 mesh，静态 USD 里只有
`MaterialBindingAPI`，没有 `PhysicsCollisionAPI`；真正带 `PhysicsCollisionAPI` 的 table surface 是
`/World/labutopia_level1_poc/obj_table/surface/mesh`。因此下一步不是改 policy 或继续算分，而是 A3h：
只做 planner-world table visual-mesh scoped repair preflight，保留真实 table collision surface，过滤或
替换非 physics 的视觉桌体 obstacle。A3h 通过前，A3f 仍不允许。

2026-07-06 A3h live 0002 已执行，结论不是“开门成功”，而是 blocker 进一步前移并变窄：
`executed_steps=0`、`--max-action-points 0` 仍然保证没有动作执行；第一段
`lift2_right_robot_frame_staging_microwave_style` 已经 planner 成功并生成 `84` 个 trajectory points；
第二段 `lift2_right_handle_front_approach_near_035` 仍然是
`MotionGenStatus.IK_FAIL`、`trajectory_point_count=0`。通俗讲，旧的“起跑姿势被桌子误拦”已经不再是
summary 里的第一硬门；现在真正要判定的是把手正前方目标对 Lift2 right arm 是否可达。A3h 仍不能解锁
contact、micro-pull 或 `Expert Oracle Score`；下一步也不直接跳 A3f，而是先补 A3h runtime filter
telemetry（如需要完整 `removed_paths` / `protected_paths` 证据），然后进入 A3j bounded handle-front
reachability diagnostic。A3j 的 stop line 是：固定 handle frame、front direction、robot base、joint
seed，并只枚举小集合 pregrasp/orientation 后仍全部 `IK_FAIL`，就停止当前 route，转 layout/base 或
official Lift2 placement 口径，不能继续扩大 waypoint sweep。

2026-07-06 A3j2 live 已按 reviewer 建议拆成 5 个独立 child run 执行：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_reachability_live_20260706/`。
每个 child 都有独立 `run_id`、`summary.json`、`trace.jsonl` 和 `runner.stdout.txt`；aggregate status 为
`BLOCKED_A3J2_ALL_HANDLE_FRONT_REACHABILITY_CANDIDATES_FAILED_STOP_SELECTED_ROUTE`。关键事实是：
5 个候选全部在第二段 handle-front waypoint 返回 `MotionGenStatus.IK_FAIL`、`trajectory_point_count=0`，
`executed_steps_total=0`。因此当前 selected Lift2 handle-front route 已到 stop line；不能继续加第 6 个
offset，也不能跳到 A3k/contact/score。下一步改为 layout/base/official Lift2 placement 或 route redesign
分支评审。

2026-07-06 多角度 review 后，下一步拆成两个有先后顺序的 bounded 分支。推荐优先 A3l：
`official Lift2 placement / base-layout review`，因为当前 LabUtopia Lift2 candidate config 把机器人放在
`position: [0.0, 0.0, 0.0]` 且没有显式 orientation，而 EBench mobile-manip official-style microwave
配置使用 scene-specific Lift2 base pose，例如 `position: [1.0, -2.65, -0.6]`、orientation
`[0.70711, 0.0, 0.0, 0.70711]`。A3l 先做 zero-live 几何审计：把 corrected handle-front target 转到
Lift2 right-arm/base reference，比较 official placement 的相对几何，再预注册极小 base pose matrix。
如果不改 base/layout，则只能进入 A3r fixed-layout route redesign fallback：最多 5 个 terminal
orientation 候选，固定 corrected translation、right arm、真实 table surface、`--max-action-points 0`。
A3r 不允许用同一个 terminal pose 继续加中间 waypoint，因为 A3j2 失败点已经是 terminal handle IK。

2026-07-06 A3l live 已按上面的 bounded plan 执行完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_base_layout_live_20260706/aggregate_summary.json`。
这次仍是 0-action diagnostic：`executed_steps_total=0`，不做 contact、micro-pull 或 score。5 个 base-layout
候选里有 3 个 planner success 且 trajectory 非空：
`A3L_XP10_YP30_KEEP_YAW` 70 points、`A3L_XP15_YP25_KEEP_YAW` 67 points、
`A3L_XP10_YP20_OFFICIAL_YAW90` 96 points。2 个候选仍因
`MotionGenStatus.INVALID_START_STATE_JOINT_LIMITS` 失败。A3l 的结论是：当前路线不是整体 no-go；
把 Lift2 base/layout 放到更合理的位置后，handle-front target 已经能被 planner 规划到。下一步不跑 A3r，
也不能直接说开门或得分，而是从这 3 个 pass candidate 中选一个进入 A3k short execution readback。

A3l candidate matrix 的推导边界：5 个候选不是 broad sweep，而是围绕 A3j2 corrected target 与 Lift2
right-arm reference frame 的相对几何做的小矩阵。前 4 个保持当前 yaw，只把 base 往目标侧小幅平移，
把 right-arm reference 到 corrected target 的 XY 距离从约 `0.6426m` 收敛到约 `0.33-0.42m`；
第 5 个保留同一平移但使用官方 microwave-style yaw90 orientation，把估算 XY 距离降到约 `0.1414m`。
每个候选只改 `robots[0].position/orientation`，不改 handle target、right arm、metric、table surface
或 route id。

A3l 里的 `--support-surface-planner-ignore-candidate` 只表示 scoped planner-world diagnostic：它用于防止
没有 `PhysicsCollisionAPI` 的 table visual mesh 继续作为 cuRobo obstacle 误拦，但真实 PhysX table
surface `/World/labutopia_level1_poc/obj_table/surface/mesh` 仍被列为 protected physics surface。它不是把桌子
从仿真里删除，也不是允许穿桌；如果 readback 或 contact 阶段撞到真实 surface，必须在 A3k/A3m 停止。

## Decision Ladder

| Stage | Purpose | Pass Means | Stop / Fail Means | PM Wording |
| --- | --- | --- | --- | --- |
| A0 static contract audit | 不启动 Isaac，审计 Lift2 config、action shape、metric、asset authority | 允许一次 live schema/action probe | config 不清楚，停止 live | 先确认“考场是不是 Lift2 考场”。 |
| A1 first live schema/action probe | 用 Lift2/R5a 16D zero-action 只测 reset/obs/step/metric | 原目标是 reset/step/schema 全 PASS | 已实际 blocked：reset result pending，assets root 指向旧 overlay | Lift2 第一次没稳定进考场，先修考场入口。 |
| A1a assets-root / reset-result closure | 不调 expert，固定 `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT=saved/assets`、composite root、Lift2 robot USD、cuRobo config | 已通过，允许 corrected A1b | 预检失败则停止 A lane runtime 合同 | 机器人和考场货架已对齐。 |
| A1b corrected live schema/action probe | 在 A1a 预检通过后，只重跑一次 reset/obs/step/metric | 已证明 reset/obs/camera/16D action/reward fields 可用 | logging metadata incomplete，需 A1c；不能直接 A2 | Lift2 能进考场并交动作，但证据记录不完整。 |
| A1c logging closure live probe | 只补 live logging metadata，不改路线、oracle 或 score | 已通过，允许 A2 oracle design | 如果仍有 schema row blocked，停止 A2 | 现在考场入口和交卷记录闭环了。 |
| A2 Lift2 oracle design | 设计 Lift2 expert path，不复用 Franka joint actions | 已通过，允许 A3 单条 oracle live | 没有合法 oracle，不算分 | 标准答案要换成 Lift2 语言。 |
| A3 single Lift2 oracle live | 只跑一条 Lift2 oracle/retarget path | 原目标是进入 Gate 2 contact | 已实际 blocked：`planner_update_unavailable`、0 action points | 当前只证明标准答案还没进入 action 层。 |
| A3a planner-update root-cause review | 不启动第二次 live，定位 A3 为什么 planner update 不可用 | 明确 `arm=left|right` 后才允许 revised A3 | 不能明确 arm contract 或 dry 仍是 `default`，则停止 live | Lift2 是双臂，不能继续用 `default` 去找 planner。 |
| A2c addendum / A3b dry | 不启动 Isaac，补 right-arm route guard 和 revised route dry check | 已通过，允许一次 revised A3 live | dry blocker 非空则停止 live | 标准答案已经改成 Lift2 右臂语言。 |
| A3c revised right-arm live | 只跑一次 revised right-arm route，验证是否能进入 action 层 | 目标是产生非空 16D action points 并到 Gate 1 near target | 已实际 blocked：`INVALID_START_STATE_WORLD_COLLISION` against table，0 action points | 右臂语言对了，但起跑姿势先被判撞桌子。 |
| A3d start-state collision review | 不启动新 live，解释 sphere 17 / table collision | 能审计出 reset、joint seed、table collider、support-surface clearance 或 planner frame 的根因 | 解释不清、同帧 clearance 仍物理相交，或只能靠 blind table ignore 才过 | 先搞清楚是真撞、桌子碰撞体过大，还是 planner 支撑面处理问题。 |
| A3e diagnostic support-surface request | 只收同 frame table/sphere clearance，不执行动作 | 只有 clearance 非负且 exclusion allowed 才能进入 A3f | 已实际 blocked：same-frame negative clearance，physical intersection，A3f 不允许 | 证据显示起跑姿势和桌子碰撞体真的冲突，不能靠忽略桌子继续。 |
| A3g reset/layout/collider review | 不启动 live，映射 sphere 17、审计 table visual mesh 与 physics surface | 明确 first repair target，允许 A3h preflight | 若只能全局 ignore table 或证据不能区分 visual/physics mesh，则停止 A3f | 先确认撞到的是“考场可见桌子模型”还是“真实物理桌面”。 |
| A3h planner-world table visual-mesh preflight | 只做 0-action 修复预检，过滤非 physics table visual mesh，保留真实 table surface | 已实际推进：第一段 staging planner 成功 `84` points；旧 start-state table blocker 不再是第一硬门 | 第二段 handle-front near 仍 `IK_FAIL`；summary 还缺 explicit filter telemetry，不能宣称 full closure | 桌子误拦问题已经缩小，下一步看把手目标是否真的可达。 |
| A3h-telemetry filter closure addendum | 如 reviewer 要求，补 runtime `removed_paths` / `protected_paths` / world obstacle evidence | 可以更强地声明 scoped planner-world repair 已闭环 | telemetry 证明 visual mesh 未移除、真实 table surface 被误删、或只能 ignore 整桌，则停止 | 把“修了错误障碍物名单”用机器日志说清楚。 |
| A3i reset/base/joint seed fallback | 仅在 A3h 后仍 start-state collision against real physics surface 时启用 | 初始姿态在正确 collision world 下无碰撞 | 若合理 seed 仍无法成立，则当前 layout/Lift2 contract 不兼容 | 确认机器人出生姿势是不是本身压进真实桌面。 |
| A3j1 corrected target dry forward-check | 先关闭 A2b intended target 与 A3h runtime target 的 `0.045m` world-X mismatch | corrected local coordinate forward-check error <= `0.01m` | 若不能复现 intended target，停止在 target-frame convention review，不跑 IK sweep | 先确认题目点位对了，再问机器人够不够得到。 |
| A3j2 bounded handle-front reachability diagnostic | A3j1 通过后，固定 handle frame/front/base/joint seed，只枚举最多 5 个 pregrasp/orientation 候选 | 原目标是至少一个 handle-front pregrasp target planner success 且非空 trajectory | 已实际 blocked：5/5 `IK_FAIL`、0 trajectory、0 executed steps，停止当前 selected route，转 layout/base/official placement 或 route redesign | 不是无限调点位；这条把手前路线已经判定不该继续硬试。 |
| A3l official Lift2 placement / base-layout review | A3j2 stop 后优先做 zero-live official placement 对齐审计，固定 handle target/metric/table surface，只比较 base pose 与 official mobile-manip pattern | 预注册一个小 base pose matrix，并证明每个候选只改 base/layout 不改 handle target | 如果 official placement 不可映射、候选需要删除真实 table surface、或 matrix 超出小集合，则停止进入 route redesign review | 先看机器人是不是站错位置，而不是继续调把手点。 |
| A3l live base-layout diagnostic | A3l review 通过后才允许 0-action live；每个 base 候选独立 child run | 已实际通过：3/5 候选 planner success 且非空 trajectory，解锁 A3k | 小集合全 `IK_FAIL` / start-state collision，则停止 base-layout 分支，转 A3r fixed-layout route redesign 或更上层 no-go | 只判断“换站位后能不能到把手前”。 |
| A3r fixed-layout route redesign fallback | 仅在不改 base/layout 或 A3l 失败后启用；固定 corrected translation，只试最多 5 个 terminal orientation/approach-source 候选 | 至少一个 terminal orientation candidate planner success 且非空 trajectory | 5/5 仍 `IK_FAIL` / 0 trajectory，则停止 fixed-layout route redesign，转 layout/base/official placement 或 no-go review | A3l 已通过，当前先不跑 A3r；它保留为 fallback。 |
| A3k pre-contact execution readback | 仅在 A3l 或 A3r 产生成功候选时才允许短执行；推荐先用 A3l pass candidate 中 trajectory 较短且 yaw 保守的 `A3L_XP15_YP25_KEEP_YAW` | 目标是单 child run、nonzero executed steps、joint/EE/collision readback 全部达标 | 已实际 blocked：执行了 `142` steps，但 joint/EE/collision readback schema 未闭合；停止进入 A3m，转 A3k1/A3k2 readback closure | 路线图已经能执行一段，但仪表还不能证明“真的到位且无异常碰撞”。 |
| A3k1 offline readback mapping audit | 0 live；只读现有 A3k `trace.jsonl` / `summary.json` 和 runner code | 已完成：Lift2 12D/4D obs 到 16D action mapping 和 right-arm EE list index 已闭合；runner comparator TDD 通过 | 已实际 blocked：修正 comparator 后 gripper 在容差内，但 12D arm joint max error=`2.571020245552063rad` > `0.02rad`；旧 run 不能解释成 pass | 仪表读懂了，但这次动作没有到最终关节目标。 |
| A3k2 package postprocess closure | A3k1 后的 0-live stop/go；先让 postprocess 能消费 corrected split readback、debug by-arm right EE、EE frame、full-run contact schema 和 controller debug | 已完成 code/test：postprocess 能分类这些字段；world-EE、controller aggregation 和 full-run contact aggregation 也已 code-ready | A3k2 live 已实际执行但 blocked：debug obs 没进 generated Lift2 candidate observation | 仪表规则能判定，但 live task-name gate 还要修。 |
| A3k2 instrumentation expansion / rerun | instrumentation code-ready 后才启用；必须 `--step-chunk-size 1` 和 debug env；full same-candidate readback budget 由 A3k2b PASS 后 exactly 1 次解锁 | 目标是 `runner_exit_code=0`、`executed_steps>0`、final planner record 是 `a3j2_corrected_center`、joint error <= `0.02rad`、right-arm EE translation <= `0.03m`、orientation <= `15deg`、full-run collision/contact schema 无异常真实 table/door/body contact | 旧 A3k2 debug-missing run 已执行 `143` steps，但 generated task name 没触发 `debug.labutopia_open_door`；A3k2b 已闭合 debug gate；A3k2c full readback 已执行；A3k2d 已离线闭合读数口径并确认 selected candidate 未到位 | 下一步允许 A3k bounded fallback，最多剩余 2 个 A3l pass candidates。 |
| A3k2b generated-task-name debug-gate validation | A3k2 root cause closure 后，不换 candidate，不做 contact/score；只验证 generated Lift2 candidate live obs 是否包含 `debug.labutopia_open_door` | 已通过：live obs 里出现 right-arm world EE、controller/tail debug、full-run contact samples，解锁 exactly 1 次 full A3k2 same-candidate readback rerun | 如果 debug 仍缺，则停在 instrumentation/environment blocker；不能进入 A3m 或 fallback candidates | 已证明仪表真的进考场；下一步才能判机器人路线。 |
| A3k2c full same-candidate readback rerun | A3k2b PASS 后的 exactly 1 次 full rerun；不换 candidate、不做 contact/score | 已执行 `142` steps，final planner label 是 `a3j2_corrected_center`，trace 最后一帧含 Lift2 `state.joints`/`state.gripper`，contact coverage `142/142` 且异常接触 0 | A3k2d 已把旧 `state_joints_missing` 改判为 stale runner summary；不能再用旧 summary 判读数缺失 | A3k2c 的 live budget 已消耗，不允许 same-candidate tuning rerun。 |
| A3k2d readback consistency audit | 0 live；只读 A3k2c `trace.jsonl` / `summary.json` / `result_compact.json` 和 runner/postprocess code，TDD 固化 final worker obs 与 final applied target 的重算口径 | 已完成：`readback_source=final_worker_obs_and_controller_debug`，schema 闭合；joint error `2.570956rad`、right-arm EE translation `0.527791m`、orientation `166.862deg`，selected candidate 停止 | 如果 schema 没闭合会停在 telemetry contract；本次 schema 已闭合，因此不再是 telemetry blocker | 尺子读准后显示这条路线没到位。 |
| A3k bounded fallback candidates | 仅在 A3k2d schema 已闭合且第一个 candidate 被真实 readback 判失败时启用；最多消耗 A3l 另外 2 个 pass candidate | 原目标是 3 个 A3l pass candidate 中至少一个通过 A3k readback，进入 A3m | 已实际 blocked：剩余 2 个 fallback candidate 均在闭合 readback 下失败，`pass_candidate_ids=[]`；A3l base-layout route family 到 no-go review | 有仪表以后换候选，结果仍没到位；不能再继续 A3l sweep。 |
| E0 evidence freeze | 0 live；冻结 A3k2d + A3k fallback 三个 closed-schema readback 失败证据 | 允许把问题从“站位调参”升级为 controller/action/readback contract review | 若任一候选缺 closed-schema 或 full-run contact coverage，先补证据；不能改线 | 先把已经试过的三条路线封账，避免重复跑。 |
| E1 controller / execution contract audit | 0 live；审计 planned trajectory、16D action payload、controller applied target、final obs/readback mapping | 找到明确可修或可验证的 action order、controller drive、trajectory replay、frame/readback mismatch | 找不到可修合同，则当前 A3l route family 停止；不再 live | 先问“规划出来的动作有没有被机器人按同一种语言执行”。 |
| E2 Lift2 controller reference / retiming probe | E1 已解锁；最多 1 次 live；non-DryingBox：5 no-op + 5 right-arm small ramp + 60 terminal hold | no-op baseline 和 terminal hold 在 closed-schema 下到位，证明 Lift2 controller/readback 可用；若 ramp fail 但 hold pass，则 retiming/hold 是下一步 | no-op 或 terminal hold 仍不到位，则停止 DryingBox oracle，先修 Lift2 controller/action/readback contract | 先用最小关节动作校准机器人和尺子。 |
| E3 DryingBox EBench-style expert pose compute | 0 live；按 EBench-style oracle 计算 DryingBox handle precontact target/action，不枚举 A3l | target pose、arm、frame、action schema、expected readback schema 静态闭合 | target frame/arm/action schema 静态不闭合，禁止 live | 用 EBench 的出题方式重新算 DryingBox 的标准答案。 |
| E4 one-segment closed execution | E2/E3 通过后最多 1 次 live；只跑 DryingBox precontact 单段，不 contact/score | right EE <= `0.03m` / `15deg`、joint/gripper readback closed、contact clean | E2 过但 E4 失败，则当前 DryingBox target/control handoff 不成立，停止该计算方式 | 这是最短“可能弄好”的工程闭环。 |
| E5 full oracle dry run | E4 通过后最多 1 次 live；多段 oracle 到接触前，仍不拉门不算分 | 多段 action 均 closed-schema 到位，异常 contact 为 0 | 多段累计漂移或 controller 不跟随，停止在 trajectory sequencing/control tracking | 单段能到以后，再看完整标准答案链条是否稳定。 |
| A3m contact-readiness / no-contact guard | 仅在 A3k pre-contact readback PASS 后启用；不拉门，只检查 pre-contact pose、gripper frame、handle clearance 和真实 table/door collision | gripper 到 handle 的接触前姿态、finger clearance 和 collision telemetry 支持进入 Gate 2 contact | pre-contact readback 到位但手指姿态/clearance/contact frame 不支持抓取，停止在 contact geometry，不进入 micro-pull/score | 到把手前还不等于能抓住；A3m 是进入接触前的最后安全检查。 |
| A3f revised setup validation | A3h/A3j/A3k/A3m 通过后才允许恢复 revised live / Gate 1 near validation | 产生 action points 并通过 Gate 1 near readback | 若仍 start-state collision、IK_FAIL 或 readback outside tolerance，则停止当前 Lift2 route | 这一步才判断能不能继续往接触把手走。 |
| Gate 2/3/4/5 | contact、retention、micro-pull、metric | 才能记录 Expert Oracle Score | 分层 blocked/fail | 这里才谈分数。 |

2026-07-06 E2 code-ready checkpoint 已完成，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_code_checkpoint_20260706.json`。
2026-07-06 E2 live 也已执行完，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_live_20260706/result_compact.json`。
当前 EOS-2 阶段停在 E2 blocker：`BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED`。
E2 只问 `manip/lift2/R5a` 能不能在 closed readback 下跟踪一个很小的 16D `joint_position` 命令，并且
terminal target 持续 hold 后能不能到位。它不是 DryingBox route attempt，不是 contact，不是 micro-pull，
不是 door success，也不是 `Expert Oracle Score`。

E2 的三种结果解释固定如下：

```text
BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED:
no-op 或 terminal hold readback 失败；停止 DryingBox oracle，先修 Lift2 controller/action/readback。

PASS_E2_REFERENCE_RETIMING_REQUIRED:
no-op 和 terminal hold 收敛，但 ramp transient 没每帧到位；后续 E3/E4 必须带 explicit retiming/terminal-hold contract。

PASS_E2_LIFT2_CONTROLLER_REFERENCE_READY_FOR_E3_E4:
no-op、ramp、hold 都到位；只解锁 E3 static compute 和 E4 one-segment precontact，仍不证明开门或得分。
```

本次实际结果属于第一类：`executed_steps=70/70`，但 no-op、ramp、terminal hold 都没有达到
`0.02rad` joint tolerance；final joint error 是 `0.20075764784227174rad`，final gripper error 是
`0.000007718801163986155rad`。action-application debug 存在，所以这不是“没有 submit action”；下一步
不能进 E3/E4，而要先修或解释 Lift2 controller/action/readback contract。

2026-07-06 E2R planning 已补上，证据计划在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r_controller_action_readback_root_cause_plan_20260706.json`。
这一步是为了停止盲试：E2 已经证明 action target 进入了 evaluator/controller 层，70 个 step 全部执行，
且 `target_action_16d` 与 `applied_joint_position_target_16d` 的最大差约 `5.52e-09rad`，所以第一嫌疑不再是
runner 没发动作。真正缺的是 per-joint telemetry：现有 trace 只保存最大误差，没有保存
`observed state.joints/state.gripper`、`expected joints/gripper`、per-index error vector、max-error joint
label、16D post-step joint vector 和 drive metadata。因此现在不能负责任地说是“第几个关节没动”、slot 映射错、
reset baseline 漂移，还是 drive/timing 问题。

E2R 的 stop/go 口径固定如下：

```text
E2R0 zero-live audit:
  冻结 E2 证据和缺口；不改行为、不跑 live。

E2R1 per-joint telemetry patch:
  只加仪表和测试，要求能记录 observed_joints12 / observed_gripper4 / observed_action_16d、
  expected_joints12 / expected_gripper4、target_minus_observed_16d、joint/gripper error by index、
  max-error action slot / component / global DOF index / DOF name、完整 action_application_debug、
  post_world_step_joint_position、post_world_step_minus_target、controller_drive_debug 和 action-slot mapping。

E2R2 enhanced non-DryingBox reference live:
  最多 1 次 live，仍然只跑 5 no-op + 5 ramp + 60 hold；目标是分类根因，不是修开门。

E2R3 single-hypothesis repair:
  根据 E2R2 证据只修一个合同点。当前 E2R3 plan 选择的优先假设是 controller target 已 applied，
  但没有转成 Lift2 arm DOF 的物理运动；先做 0-live USD/articulation/drive/limit audit，再补
  code/test-only articulation telemetry，最后决定唯一修复点。

E2R4 final controller sanity live:
  最多 1 次 live。若 no-op 和 final hold 进入 0.02rad，才允许回到 E3/E4；
  若同类失败仍存在且 per-joint telemetry 已闭合，就判定当前 direct 16D joint_position 路线 no-go，
  转 official Lift2 baseline controller/action path review，不再继续 DryingBox offset / contact / score。

E2R5 closure / fork decision:
  0-live 封账，不是第三次 live。E2R4 pass 则恢复 E3 static DryingBox EBench-style compute 和
  E4 one-segment precontact；E2R4 同类失败则转 official Lift2 baseline controller/action path review。
```

产品口径：如果问“预计到哪一步能弄好”，controller 这一层最早要等 E2R4 通过；DryingBox 专家路线最早要等
E4 one-segment precontact 通过才算有工程成功信号。若问“到哪一步能判弄不好”，E2R4 是当前 direct 16D
`joint_position` 路线的 no-go 判定点；这不是整个 LabUtopia-to-EBench 项目 no-go，而是要求换成 official
Lift2 baseline controller/action path。

2026-07-06 E2R1 per-joint telemetry code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r1_per_joint_telemetry_code_checkpoint_20260706.json`。
这一步没有启动 Isaac，也没有消耗 live。GenManip 的 E2 reference probe 现在会在 fake-client 测试中输出
`observed_joints12`、`observed_gripper4`、`observed_action_16d`、expected vectors、
`target_minus_observed_16d`、per-index error、max-error action slot / global DOF / DOF name、完整
`action_application_debug`、post-step joint vector、`controller_drive_debug` 和静态 `action_slot_mapping`。
TDD 记录包括三个 RED：缺 `observed_joints12`、缺 `full_action_application_debug`、缺
`action_slot_mapping`；GREEN 后 `test_lift2_controller_reference_probe.py` 为 `13 passed in 0.03s`。
下一步允许 E2R2：exactly one enhanced non-DryingBox live，用相同 5 no-op + 5 ramp + 60 hold 计划定位根因。

2026-07-06 E2R2 enhanced live 已执行完，证据在
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r2_enhanced_lift2_controller_reference_live_20260706/result_compact.json`。
它仍是 non-DryingBox probe，`executed_steps=70/70`，没有 contact、micro-pull 或 score。raw classification
仍是 `BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED`，但 enhanced telemetry 已闭合并给出
更具体的信号：no-op 阶段最大误差来自 `left_joint3` / controller joint `fl_joint3`，target
`0.047641370445rad`、observed `0.09468900412321091rad`，说明 reset baseline 有 stale / settling 问题；
terminal hold 阶段最大误差来自 action slot `8`，也就是 `right_joint1` / controller joint `fr_joint1`，
target `0.200753768836rad`、observed 仍约 `-0.000003879rad`，而 controller debug 记录的 applied target 已是
`0.20075376331806183rad`，drive stiffness/damping/max effort 也有读数。结论：单纯“ramp 太快”解释不够，
因为 60 步 hold 后 `fr_joint1` 仍基本不动。下一步改为 E2R3 zero-live / single-hypothesis repair planning：
优先审计 Lift2 arm joint tracking / controller application path，不允许再跑 E2R2 或进入 DryingBox E3/E4。

2026-07-06 E2R3 plan 已补齐：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3_lift2_articulation_contract_repair_plan_20260706.json`。
它把下一步压成 3 个 0-live 子步骤：E2R3a 审计 runtime USD/articulation、DOF name/index、lock/passive/mimic、
drive mode、limit、max effort、max velocity 和 articulation root；E2R3b 只补 code/test-only telemetry；
E2R3c 选择唯一修复点。E2R4 才是最后一次 controller sanity live；E2R5 只做 closure/fork decision。

2026-07-06 E2R3a zero-live audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3a_lift2_articulation_contract_zero_live_audit_20260706.json`。
PXR 静态审计确认 `fr_joint1` 是 enabled `PhysicsRevoluteJoint`，带 `PhysicsDriveAPI:angular`、
`drive:maxForce=100`、`excludeFromArticulation=false`；`fl_joint3` 也有 angular drive。结论是：当前 blocker
不是静态 USD 缺右臂 joint/drive 的粗问题，但 runtime DOF mapping、qdot、limit、max velocity 和
sleep/constraint 仍未被 telemetry 覆盖。下一步 E2R3b 只做 code/test-only telemetry expansion。

2026-07-06 E2R3b code checkpoint 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3b_articulation_telemetry_code_checkpoint_20260706.json`。
GenManip `read_articulation_controller_debug` 新增 `joint_position`、`joint_velocity`、`max_joint_velocity`、
`joint_lower_limit`、`joint_upper_limit`。TDD RED 为缺 `joint_position` / schema fields；GREEN 后 focused
2 passed，相关 suite `97 passed in 0.60s`，`py_compile` 和 `git diff --check` 通过。下一步 E2R3c 是
0-live repair decision，不能直接启动 E2R4。

2026-07-06 E2R3b2 summary telemetry addendum 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3b2_summary_telemetry_addendum_20260706.json`。
这是 code/test-only 证据可读性补丁，不改变机器人行为、不消耗 live budget。它把最终 step 的
`controller_drive_debug` 作为 `final_controller_drive_debug` 提升到 probe summary 顶层，并另给
`final_runtime_motion_debug` 摘出 `joint_position`、`joint_velocity`、`max_joint_velocity`、lower/upper limits、
applied target 和 drive 参数。新增测试先 RED 到缺 `final_controller_drive_debug`，GREEN 后相关 suite
`98 passed in 0.60s`，`py_compile` 和 `git diff --check` 通过。E2R4 仍只允许一次 unchanged non-DryingBox
controller sanity live。

2026-07-06 E2R3c single repair decision 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r3c_single_repair_decision_20260706.json`。
决策是不做猜测式行为修复：不盲目加 drive/gain、不盲目切 articulation API、不盲目加 hold、不把 reset
baseline 当主修复。E2R4 允许 exactly one non-DryingBox controller sanity live，并必须带 E2R3b telemetry。
E2R4 pass 才回 E3/E4；若 target applied 但 qdot 近零且 limit/velocity/effort 解释不了，则 direct 16D
`joint_position` 路线 no-go，转 official Lift2 baseline controller/action path。

2026-07-06 E2R4 final controller sanity live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r4_final_controller_sanity_live_20260706/result_compact.json`。
它消耗了唯一 allowed E2R4 live：`70/70` planned steps executed，仍未触碰 DryingBox route、contact、
micro-pull 或 score。最终 `right_joint1` target/applied target 均约 `0.2007538rad`，但 observed 仍接近
`0rad`，final error `0.20075764784227174rad`。reported limits 覆盖 target 与 observed，drive 参数存在，
`readback_errors=[]`；runtime `max_joint_velocity` 为 null，作为 caveat 记录。三路 review 结论一致：
这足以关闭当前 direct 16D route，不需要第二次 E2R4 或第三次 E2R live。

2026-07-06 E2R5 zero-live closure 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2r5_direct_16d_route_closure_fork_20260706.json`。
状态是 `E2R5_CLOSED_DIRECT_16D_JOINT_POSITION_ROUTE_NO_GO_FORK_OFFICIAL_LIFT2_BASELINE_CONTROLLER_ACTION_PATH`。
E2R5 不启动 live，只封账：当前 direct 16D `joint_position` 动作接口路线 no-go；不是 LabUtopia-to-EBench
项目 no-go，不是 official Lift2 baseline no-go，也不是 Expert Oracle Score 失败。下一步新开 bounded
official Lift2 baseline controller/action path review。

下面 A3h/A3j/A3l/A3k/A3k2 记录是 E2 之前的历史收敛链，用来解释为什么要转 E2，不再代表当前下一步。

2026-07-06 A3h runtime filter telemetry checkpoint 已补齐 code-ready 证据：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3h_runtime_filter_telemetry_code_checkpoint_20260706.json`。
这一步只改 diagnostic output：`planner_debug.start_state_collision` 以后会带
`exact_ignore_paths_without_physics_collision_api` 和 `exact_non_physics_obstacle_filter`，让下一次
A3h-telemetry rerun 能直接证明 `removed_paths` / `kept_requested_paths`。它不是 live rerun，不改变
planner world filter 语义，也不解锁 execution/contact/score。后续如果 reviewer 要 full A3h filter
closure，就先跑 A3h-telemetry；如果接受 A3h 0002 的路线推进信号，则直接进入 A3j bounded handle-front
reachability。

2026-07-06 A3j zero-live review 发现一个比 IK sweep 更靠前的问题：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j_handle_front_runtime_target_equivalence_review_20260706.json`。
A2b intended handle-front adjusted world target 是 `[0.4797899614, 0.3107189913, 1.1085915535]`；
A3h runtime resolver 实际送给 cuRobo 的第二段 target 是
`[0.4347899614, 0.3107189913, 1.1085915535]`，world X 差 `0.045m`，超过 `0.01m` tolerance。更关键的是，
两边记录的 local translation 完全一样，说明问题不是输入抄错，而是 A2b 静态 target-frame convention 和
A3h runtime resolver convention 尚未闭合。因此 A3j 不能直接跑 reachability sweep；下一步先做 A3j1
corrected target dry forward-check。如果修正 local Y `+0.045m` 后能 forward-check 回 intended world
target，再进入最多 5 个候选的 bounded reachability matrix；否则停止在 target-frame convention review。

2026-07-06 A3j1 corrected target forward-check 已通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j1_corrected_target_forward_check_20260706.json`。
使用 A3h runtime resolver 记录的 handle frame，把 local Y 从 `-0.0208166` 改成 `0.0241834` 后，正向变换
得到 `[0.4797899584, 0.3107189900, 1.1085915535]`，与 A2b intended target 的误差约
`3.22e-09m`，远小于 `0.01m`。这关闭了 A3j 的 target-frame mismatch，但仍不是 planner reachability；
下一步才是 A3j2：最多 5 个候选的 bounded reachability matrix，以 corrected local target 为中心。

2026-07-06 A3j2 bounded matrix 已预注册：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_handle_front_reachability_matrix_20260706.json`。
它只包含 5 个候选：A3j1 corrected center、approach farther/closer `1cm`、world-X/local-Y `+/-5mm`。
不允许继续加 offset，不允许 contact/score，不允许 orientation sweep。A3j2 的 stop line 很硬：5 个候选
如果全是 `IK_FAIL` 或 0 trajectory points，就停止当前 selected route，转 layout/base/official Lift2
placement 或 route redesign。

A3j2 的 runner input 也已经打包到
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_handle_front_reachability_matrix_20260706/route_manifest.json`。
后续 live/diagnostic 只能从这 5 个 route-id 里选，不允许现场新增候选：`A3J2_CORRECTED_CENTER`、
`A3J2_APPROACH_FARTHER_010`、`A3J2_APPROACH_CLOSER_010`、`A3J2_WORLD_X_PLUS_005`、
`A3J2_WORLD_X_MINUS_005`。

2026-07-06 A3j2 live 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_reachability_live_20260706/aggregate_summary.json`。
5 个候选按独立 child run 顺序执行，全部有 summary；aggregate 记录
`pass_candidate_route_ids=[]`、`executed_steps_total=0`、每个 handle-front waypoint 都是
`MotionGenStatus.IK_FAIL` 和 `trajectory_point_count=0`。按预注册 stop condition，当前 selected
Lift2 handle-front route 终止；下一步不是 A3k，而是 layout/base/official Lift2 placement 或 route redesign。

2026-07-06 placement reviewer 建议优先 A3l：先审计 current LabUtopia Lift2 base pose 和 official
mobile-manip Lift2 placement pattern 的差异。当前 `lift2_candidate/level1_open_door.yml` 使用
`position: [0.0, 0.0, 0.0]` 且没有显式 orientation；官方 `mobile_manip/*/microwave.yml` 使用明确
scene-specific base pose，例如 `position: [1.0, -2.65, -0.6]`、orientation
`[0.70711, 0.0, 0.0, 0.70711]`。A3l 不能直接改任务并算分，先只做 zero-live 几何 review 和小矩阵
预注册。

2026-07-06 route-design reviewer 建议 A3r 作为 fallback：如果固定当前 layout 不改，则只允许最多 5 个
terminal orientation 候选，全部使用 A3j1 corrected local translation
`[-0.061955757838629166, 0.024183381616805832, 1.1611298411651205e-07]`、right arm、同一 staging。
候选包括 post-staging EE orientation、roll +/-90deg、cant +/-45deg。A3r 不允许继续添加中间 waypoint
或第 6 个 offset；如果 5 个 orientation 仍全失败，就停止 fixed-layout route redesign。

2026-07-06 A3l live 已完成并通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_base_layout_live_20260706/aggregate_summary.json`。
5 个 base-layout child run 都有独立 summary；aggregate status 是
`PASS_A3L_AT_LEAST_ONE_BASE_LAYOUT_CANDIDATE_READY_FOR_A3K`。通过候选为
`A3L_XP10_YP30_KEEP_YAW`、`A3L_XP15_YP25_KEEP_YAW`、`A3L_XP10_YP20_OFFICIAL_YAW90`，
分别规划出 70、67、96 个 trajectory points。失败候选为 `A3L_XP10_YP20_KEEP_YAW` 和
`A3L_XP20_YP25_KEEP_YAW`，status 是 `MotionGenStatus.INVALID_START_STATE_JOINT_LIMITS`。
所有 child 的 runner exit code 都是 `2`，但这是 `--max-action-points 0` 的预期诊断副作用：
成功生成 action chunk 也会被 runner classify 成 `max_action_points_exceeded`。A3l 的 pass/fail 只看
planner record 的 `handle_plan_success` 和 `handle_trajectory_point_count`。A3r 现在不作为下一步执行；
下一步是写 A3k short execution readback manifest，并先用 A3l pass candidate 做短执行 readback。

2026-07-06 A3k short execution readback package 已准备并通过 preflight：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/`。
它只选一个 candidate：`A3L_XP15_YP25_KEEP_YAW`，原因是它是 yaw-preserving pass candidate 中 handle
trajectory 最短的一条。动作预算固定为 `--max-action-points 180`，覆盖 A3l 观测到的 staging 75 points +
handle 67 points，但不允许无限执行。A3k 的 pass 需要两层 readback：runner 自带 joint readback
`final_joint_target_abs_max_rad <= 0.02`，以及 postprocess 从 final obs/trace 里读取 right-arm EE pose，
验证 EE translation error <= `0.03m`、orientation error <= `15deg`。如果 EE pose 字段缺失或双臂顺序
无法判定，A3k 不算通过，而是 readback instrumentation blocker。

2026-07-06 A3k live 已执行：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/result_compact.json`。
单候选 `A3L_XP15_YP25_KEEP_YAW` 通过 planner 并实际执行 `142` steps，这说明 action chunk 已经能进入
`step_chunk`，比 A3l 的 planner-only 证据更进一步。但 A3k 没有通过：runner exit code 为 `2`，
classification 仍是 `BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`；readback blocker 是
`state_joints_missing`、缺明确 right-arm `state.ee_pose`、缺
`a3k_full_run_collision_contact_readback.v1` full-run collision/contact schema。因此 A3k 当前结论不是
“路线失败”或“开门失败”，而是 **execution 已发生但 readback instrumentation 不足**。下一步先做
A3k readback instrumentation closure，不能进入 A3m/contact/score。

2026-07-06 A3k post-run forensic review 进一步收窄了 blocker：`trace.jsonl` 的 final worker packet 里
确实有 `obs.state.joints`、`obs.state.ee_pose` 和 `obs.state.gripper`，所以不是 runtime 完全没有回传
状态；问题变成三件可验证的小事。第一，runner summary 当时把 `state.joints` 判成 missing，说明
readback extraction/summary schema 没闭合。第二，重新用当前 `_readback_summary` 解析同一份 trace 后，
能读到 12D `state.joints`，但直接拿它和 16D final action target 前缀比较会得到约 `3.64rad` 最大误差；
这不能直接判失败，因为 12D observation joint order 和 16D action payload order 还没有建立同名映射。
第三，`state.ee_pose` 是两组 `[position, quaternion]`，但 trace 没有显式标注哪一组是 right arm。所以下一步
不是继续试新点位，而是 A3k1 readback mapping closure：先用已有 trace 和代码测试证明 joint/order/arm mapping，
再决定是否允许同一 candidate 做一次 rerun。

2026-07-06 A3k1 offline readback mapping audit 已完成：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k1_offline_readback_mapping_audit_20260706.json`。
这一步没有启动 live，只读现有 A3k `trace.jsonl` / `summary.json` 和 GenManip code。结论比旧 A3k
`state_joints_missing` 更精确：Lift2 `state.joints` 是 12D arm-only `[left arm 6, right arm 6]`，
`state.gripper` 是 4D gripper-only，16D action target 是 `[left arm 6, left gripper 2, right arm 6,
right gripper 2]`。runner comparator 已用 TDD 修成这个 schema；测试
`test_native_action_path_runner.py` 14 passed。用修正 comparator 重算旧 trace 后，gripper readback
在容差内，但 12D arm joint 最大误差是 `2.571020245552063rad`，超过 `0.02rad`。所以当前 selected
candidate 不能被解释为 A3k pass，也不能进入 A3m。A3k1 允许且仅允许一次 A3k2 same-candidate
instrumentation rerun，用于补 controller applied-target、right-arm EE frame/world pose 和 full-run
collision/contact telemetry；这不是 route sweep，也不允许 contact/micro-pull/score。

2026-07-06 A3k2 instrumentation code checkpoint 已准备：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_code_checkpoint_20260706.json`。
它仍不是 live evidence，也不消耗 A3k2 唯一 rerun budget。GenManip runner 现在能按 Lift2 split schema
比较 12D arm / 4D gripper；`debug.labutopia_open_door` 也能在 `LABUTOPIA_ORACLE_DEBUG_OBS=1` 时输出
`evaluator_last_ee_pose_by_arm.left/right` 和 `evaluator_last_ee_pose_frame=planner_fk_reference_frame`。
验证：runner tests 14 passed，debug-state tests 27 passed。当前仍不能立刻启动 A3k2 live，因为旧 A3k
postprocess 只接受 `state.ee_pose` 的 `dict:right/right_arm`，尚未消费新的 debug by-arm 字段，也没有把
`physx_contact_debug` 归一化成 A3k 要求的 full-run collision/contact schema。下一步是 A3k2 package
postprocess closure，然后才允许同一 candidate 最多一次 instrumentation rerun。

2026-07-06 A3k2 package postprocess closure 已补齐 code/test stop-go：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_package_postprocess_closure_20260706.json`。
GenManip 新增 `standalone_tools/labutopia_poc/a3k_readback_postprocess.py` 和
`tests/labutopia_poc/test_a3k_readback_postprocess.py`；TDD 验证 `7 passed`。这一步证明 postprocess
现在能消费 `debug.labutopia_open_door.evaluator_last_ee_pose_by_arm.right`，并能机器判定：
非 world-frame EE pose 不能算 world tolerance、final-step-only `physx_contact_debug` 不能冒充 full-run
no-contact、full-run contact sample count 必须等于 `executed_steps`、controller/applied-target debug
必须包含 `final_applied_action_target_16d` 和 `tail_joint_error_series`。结论仍是
`ready_to_rerun_live=false`：A3k2 live 还不能跑。下一步不是消耗唯一 rerun，而是 A3k2 instrumentation
expansion code checkpoint，补 world-frame right EE 或显式 transform、full-run contact coverage 和
controller/applied-target tail readback。

2026-07-06 A3k2 instrumentation expansion 已先落第一小步：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_step_sampling_checkpoint_20260706.json`。
runner 新增显式 `--step-chunk-size`，默认行为不变；只有设置 `--step-chunk-size 1` 时才逐 action
调用 `step_chunk`，并在 trace 写 `step_chunk_sample` 和每步 `final_obs`。TDD focused test 先因缺
`step_chunk_size` 失败，修复后通过；runner+postprocess 测试 `22 passed`。multi-agent review 收紧了
边界：这个 checkpoint 只提供 full-run telemetry 的采样入口，不能证明 no abnormal table/door/body
contact；现有 `physx_contact_debug` 只是 handle-contact attribution，不是异常碰撞证明；Lift2
right-arm world EE 必须用 `robot_base_right.get_world_pose()` 作为 reference transform，不能用 robot
root pose；controller/applied-target debug 必须来自 evaluator `env.step`，不能由 runner 猜。A3k2 live
仍然 blocked。

2026-07-06 A3k2 instrumentation expansion 第二小步已落 world-frame EE code checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_world_ee_checkpoint_20260706.json`。
debug obs 保留 raw `evaluator_last_ee_pose_by_arm.right` 的 `planner_fk_reference_frame` 语义，同时新增
`evaluator_last_ee_pose_reference_frame_by_arm.right` 和 `evaluator_last_ee_pose_world_by_arm.right`。
Lift2 right arm 使用 `embodiment.robot_base_right.get_world_pose()` 做 SE(3) 组合，测试用 90 度旋转证明
不是简单平移；postprocess 现在优先消费 explicit world-by-arm right EE，并拒绝“把 raw by-arm frame 字符串
改成 world”的 shortcut。TDD focused tests 和 combined adjacent tests 已通过：`53 passed`。这仍不是
A3k2 live-ready：该 world EE 是 evaluator target/cache 的 world transform，物理实际到位还要由 joint/tail
readback 和 controller debug 证明；full-run abnormal contact aggregation 与 controller/applied-target
aggregation 仍未闭合。

2026-07-06 A3k2 instrumentation expansion 第三小步已落 controller/applied-target aggregation checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_controller_checkpoint_20260706.json`。
runner 在 `--step-chunk-size 1` 时会从每步 `final_obs` 的
`debug.labutopia_open_door.evaluator_last_action_application_debug` 里聚合
`a3k2_controller_debug.v1`。`final_applied_action_target_16d` 来源限定为 evaluator `env.step`
读到的 `applied_joint_position_target`，`tail_joint_error_series` 来源限定为
`post_world_step_minus_target_abs_max`，不能由 runner action chunk 猜。TDD focused test 先因缺
`a3k2_controller_debug` 失败，修复后通过；相邻 runner/postprocess/world-EE tests 现在 `54 passed`。
这仍不是 A3k2 live-ready：world EE 和 controller/tail 代码路径已闭合，但 full-run abnormal contact
aggregation 仍缺，下一步必须产出 `a3k_full_run_collision_contact_readback.v1`，并刷新 package closure 到
`ready_to_rerun_live=true` 后才允许唯一 live rerun。

2026-07-06 A3k2 instrumentation expansion 第四小步已落 full-run contact aggregation checkpoint：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_full_run_contact_checkpoint_20260706.json`。
runner 在 `--step-chunk-size 1` 时会把每步
`debug.labutopia_open_door.physx_contact_debug` 聚合成
`a3k_full_run_collision_contact_readback.v1`，并要求 `contact_sample_count == executed_steps`、
`missing_contact_sample_count == 0`。postprocess 现在也能消费 runner summary 顶层 full-run schema；单个
final obs 的 `physx_contact_debug` 仍会被判为 final-step-only。TDD 证据包括 postprocess top-level
RED/GREEN、runner full-run contact RED/GREEN，combined adjacent tests 现在 `56 passed`。这一步仍不是
live evidence，也不是全局所有场景碰撞的形式化证明：它覆盖的是每步 observed `physx_contact_debug`
里的 unmatched contact pairs。review 后已收紧 `status=available` 的 shape validation，schema/method/list/errors
形状异常会计为 invalid/missing sample，不能当 clean full-run sample。该 checkpoint 没有消耗 A3k2 budget；
但默认下一步已经从“补 instrumentation code”推进到
A3k2 same-candidate live rerun package：固定 `A3L_XP15_YP25_KEEP_YAW`、`A3J2_CORRECTED_CENTER`，
启用 `LABUTOPIA_ORACLE_DEBUG_OBS=1`、`LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1`、controller debug 和
`--step-chunk-size 1`，只跑一次，不改候选、不加 contact/micro-pull/score。

2026-07-06 A3k2 same-candidate live rerun 已执行：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_same_candidate_live_rerun_20260706/result_compact.json`。
selection manifest 固定 port `18121`、parent run id
`eos2_gate1u_a3k2_same_candidate_instrumented_20260706_parent_0001`、child run id
`eos2_gate1u_a3k2_p01_xp15_yp25_keep_yaw_instrumented_20260706_0001`。结果是
`BLOCKED_A3K2_SAME_CANDIDATE_INSTRUMENTED_READBACK_NOT_READY_FOR_A3M`：`executed_steps=143`，
final planner record 是 `a3j2_corrected_center`，但 debug obs 没进 generated Lift2 candidate
observation，导致 right EE/controller/contact telemetry 全缺。随后 A3k2b generated-task-name
debug-gate validation 已通过：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2b_debug_gate_validation_20260706/result_compact.json`。
A3k2b 只执行 1 个 diagnostic action point，证明 generated Lift2 live obs 里有
`debug.labutopia_open_door`，并带出 right-arm world EE、controller/tail debug 和 full-run contact sample
plumbing。随后 A3k2c exactly 1 次 full A3k2 same-candidate readback rerun 已执行：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2c_full_readback_rerun_20260706/result_compact.json`。
A3k2c 没有通过 A3m 入口：`executed_steps=142`，final planner label 是 `a3j2_corrected_center`，
trace 最后一帧含 Lift2 `state.joints`/`state.gripper`，full-run contact coverage `142/142` 且异常接触为 0。
A3k2d 已用同一份 A3k2c `trace.jsonl` 做 zero-live readback consistency audit：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2d_readback_consistency_audit_20260706.json`。
它把旧 runner summary 的 `state_joints_missing` 改判为 stale summary：final worker obs 和 controller debug
可以闭合 `lift2_split_arm_gripper_obs_to_16d_action`。闭合后的真实读数仍失败：joint error
`2.570956rad > 0.02rad`，right-arm EE translation error `0.527791m > 0.03m`，orientation error
`166.862deg > 15deg`。因此 selected candidate 按规则停止；下一步允许 A3k bounded fallback，最多再评估
A3l 剩余 2 个 pass candidates。

预测和停止线：A3k2d 已经收敛，随后 A3k bounded fallback 也已执行完：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_bounded_fallback_readback_20260706/result_compact.json`。
剩余两个 fallback candidate 都按同一套 joint/EE/contact/controller readback 跑完，schema 均闭合、
full-run contact 均 clean，但都没到预接触目标。`A3L_XP10_YP30_KEEP_YAW` 执行 `152` steps，joint error
`1.133121rad`、EE translation error `0.342726m`；`A3L_XP10_YP20_OFFICIAL_YAW90` 执行 `178` steps，
joint error `2.027691rad`、EE translation error `0.312915m`、orientation error `89.758deg`。
因此 A3l 的 3 个 planner-success candidates 全部在 A3k closed-schema readback 下失败，当前
A3l base-layout route family 不值得继续硬调。下一步不是 A3m/contact/score，而是 A3l no-go review：
转 A3r fixed-layout route redesign 或上层 robot/control/task-layout contract review。

2026-07-06 A3l no-go review 的多角度结论已经收敛：当前应判定
`A3l base-layout route family no-go for A3m`。原因不是碰撞、材质、相机或 runner 没跑起来，而是
planner-success route 进入 execution 后没有在 closed-schema readback 下到达预接触目标。后续不再允许
继续给 A3l 加 base/yaw/offset 候选；下一步改为 E0-E6 的 EBench-style controller/expert
recalibration ladder。E0/E1 都是 0-live：先冻结证据，再审计
planned trajectory -> 16D action -> controller applied target -> final `state.joints/state.gripper` /
right-arm EE 的一致性。只有 E1 找到明确可修或可验证的 controller/action/readback contract，才允许
E2 的 1 次 EBench reference probe。若 E1 找不到可修合同，当前路线直接停止，不再消耗 live。

2026-07-06 E1 controller/execution contract audit 已形成 0-live 结论：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e1_controller_execution_contract_audit_20260706.json`。
E1 冻结了三条 A3l planner-success 但 readback 失败的路线，并进一步排除“没提交动作”“碰撞中断”和
“简单 readback 顺序写反”。三条路线的 `applied_target_sample_count == executed_steps`，full-run contact
均 clean，但 tail joint error 仍停在 `1.13-2.57rad`。源码审计显示 `env.py` 对每个
`joint_position` target 默认只执行一次 `world.step()`，而 R5a max joint velocity 是 `2.0rad/s`；
A3k 轨迹相邻 action delta 最高约 `0.035-0.043rad`。因此 E1 的可证伪假设是
`H1_PLAYBACK_OUTRUNS_LIFT2_CONTROLLER`：当前 playback 节奏可能让 Lift2 controller 长期追不上，而不是
DryingBox 几何站位还能继续调。下一步唯一允许的 live 是 E2：non-DryingBox Lift2 controller reference
probe，一次 run 内包含 5 个 no-op、5 个 right-arm small ramp（例如单关节总计 `+0.20rad`）和 60 个
terminal hold；继续开启 controller/tail/readback/contact debug。E2 不允许直接重跑 DryingBox candidate。

2026-07-06 多角度 stop/go review 结论一致：A3k2c 已经证明“不是没跑起来”，但 runner summary 和
trace/postprocess readback 口径不一致，所以不能继续盲跑。产品视角建议把最近节点定义为 A3k2d：
先用已有 trace 离线确认“尺子是否读准”；debug 视角要求用 TDD 固化 final worker obs / final applied
target 的重算口径；架构视角要求把 A3k2c live budget 视为已消耗，不允许再对同一 candidate 做
“试一次”的 live rerun。A3k2d 的结果只有三种：schema 闭合且通过则进入 A3m；schema 闭合但误差仍超标
则停止 selected candidate 并允许 bounded fallback；schema 仍闭合不了则停在 telemetry contract。

## Multi-Agent Review Notes

2026-07-06 第一轮两个只读审阅结论一致：A1c 已足以判定 Lift2 工程入口链路可用，但它只覆盖
`single_task_live_schema_probe_only`。A2 不能直接算分，必须先做 oracle path review、target/waypoint
static audit 和 translator dry contract；A3 才允许一次 selected Lift2 oracle live，用于 Gate 1 near
reachability。Gate 4 通过才接近“工程上能开门”，Gate 5 记录
`PASS_EXPERT_ORACLE_SCORE_RECORDED` 才算“评测口径弄好”。

2026-07-06 A3 live 后第二轮两个只读审阅结论一致：当前 A3 不能直接判成 “Lift2 route 到不了
把手前”。A3 的 first failure is `planner_update_unavailable`，且 planner records 显示两条 waypoint
都是 `arm=default`。代码审阅确认 Lift2/R5a 是 dual-arm embodiment，planner helper 需要
`left_planner` / `right_planner`，而不是 single-arm 的 `embodiment.planner`。因此下一步是 A3a
root-cause review 和 explicit arm contract closure，而不是 live sweep。

2026-07-06 A3a 后第三轮只读审阅和本地代码核对一致：revised A3 应选 `right`。依据是 EBench 原生
`microwave` open-door 风格配置使用 `motion_list.right`，robot-frame staging 使用 `rel_arm: right`；
`custom_motion` 真正选择 planner/action arm 的是 motion-list key / `arm` contract，不能靠 `name`
字段推断。A2c addendum 和 A3b dry package 已据此固定 `arm=right`、`rel_arm=right`、`--required-arm right`。

2026-07-06 A3c 后第四轮只读审阅一致：A3c 关闭了 A3a 的 arm contract blocker，但没有关闭 Gate 1
reachability。A3c 的 planner records 都是 `arm=right`，world refresh 是 `success`；新的第一失败点是
`MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION`，碰撞对象是 table mesh，`sphere_index=17`，
发生在任何 target reachability / contact / score 之前。因此下一步只能是 A3d read-only / zero-live
root-cause review：映射 sphere 17 到 Lift2 link/collision sphere，同帧核查 table top / AABB /
sphere radius clearance，审阅 reset base/joint/EE pose 和 planner ignore policy。不能直接把 table
ignore 当修复，也不能继续 live sweep。

2026-07-06 A3d 只读审阅和本地 trace 提取结果进一步收紧：A3c trace 的 reset event 已经包含
`state.base`、12D `state.joints`、`state.gripper`、两组 `state.ee_pose` 和 `robot_id=manip/lift2/R5a`；
planner response 也稳定指向同一个 table obstacle、同一个 `sphere_index=17` 和
`sphere_frame=planner_reference_frame`。但仍缺三件关键信息：sphere 17 到 Lift2 link 的映射、
table obstacle 的同 frame AABB/top、以及 `support_surface_clearance_records`。因此 A3d 的结论不是
“可以继续开门 live”，而是进入 A3e diagnostic-only runner checkpoint：runner 只补
`support_surface_payload` 透传能力，让下一次 zero-live/diagnostic planner request 能请求已有
GenManip support-surface clearance builder 输出同帧 clearance records。TDD 证据已经落盘：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_runner_checkpoint_20260706.json`。
A3e diagnostic request package 也已准备：
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_request_20260706/`。
它固定同一条 A3B right-arm route、`support_surface_uid=table`、A3c 的 exact table obstacle path，并用
`--max-action-points 0` 防止任何 action execution。该包仍不是 Gate 1 pass，也不是 contact 或 score。

2026-07-06 A3e live diagnostic 已执行。Preflight 先补齐了 `genmanip_client` import 和 submit CLI
参数名，随后 server/submit/runner 用同一个 `run_id=eos2_gate1u_a3e_support_surface_diagnostic_20260706_0001`
完成诊断；runner exit code 为 `2`，这是 blocked/no-go 结果而不是动作执行失败。summary/trace 显示：
`executed_steps=0`、2 条 support-surface record、same-frame measured clearance、negative margin
`-0.6237133788083942`、`planner_only_support_surface_exclusion_allowed=false`。raw runner
classification 仍写成 `BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY`，但该字段是旧泛化标签；
canonical A3e status 以 selection manifest 和 README 的 same-frame clearance no-go 为准。第五轮
stop/go 结论：不能进入 A3f，必须停止当前 Lift2 reset/layout/collider contract，转
reset/base/joint/table-collider repair review。

2026-07-06 A3g 静态 review 已补上两个关键闭环。第一，`sphere_index=17` 不再是未知球体：按
`r5a_right_arm.yml` 的 `collision_link_names` flatten order，它是 Lift2 `link6` 的第 0 个 collision
sphere，`raw_radius=0.02822m`，加 `0.004m` buffer 后是 `0.03222m`，与 A3e 观测半径一致。第二，A3e
报 collision 的 table path 是完整视觉桌体 mesh，静态 USD 只标了 `MaterialBindingAPI`；真正
`PhysicsCollisionAPI` / `PhysicsMeshCollisionAPI` 的 table support surface 是
`/World/labutopia_level1_poc/obj_table/surface/mesh`。因此 A3g 的 stop/go 结论是：A3f 仍 blocked，但
first repair target 从“盲目调 Lift2 轨迹”收窄为 planner-world table obstacle representation。下一步
A3h 只能过滤或替换非 physics visual table mesh，并必须保留真实 table surface；如果 A3h 后仍撞真实
surface，再进入 A3i reset/base/joint seed review。

2026-07-06 A3h live 0002 后，多角度 stop-line review 结论一致：当前还值得继续，但必须从“继续试
waypoint”改成“bounded 判定”。A3h 的正向信号是 staging waypoint 已成功规划 `84` points；硬边界是
没有 action execution、没有 readback、没有 contact/door/score，且 handle-front near 仍 `IK_FAIL`。
因此后续最多按四层推进：A3h telemetry addendum（如需 full filter closure）、A3j1 target equivalence
forward-check、A3j2 bounded handle-front reachability、A3k short execution readback。如果 A3j1 不能
关闭 `0.045m` target mismatch，就停止在 target-frame convention；如果 A3j2 在固定 frame/base/seed 后
的小集合 pregrasp/orientation 全部失败，就停止当前 selected route，转 layout/base 或 official Lift2
placement fallback，而不是扩大 sweep。

## Estimated Resolution / Stop Line

最早的“工程链路可用”节点已经达到：A1c fresh live 拿到 reset observation、camera keys、三种 16D action dialect step、reward/success fields，并补齐 logging metadata。这个结论只覆盖 Lift2 single-task schema/action/logging contract，不覆盖专家路线、接触、开门或分数。

最早能说“开门这件事工程上接近弄好”的节点是 Gate 4：Lift2 oracle 经过 A3/Gate 2/Gate 3 后，micro-pull 能带动 `obj_DryingBox_01/RevoluteJoint`，并有 door joint readback。Gate 4 通过前，不应汇报“已经会开门”。

真正的评测口径完成节点仍然是 Gate 5：记录 `PASS_EXPERT_ORACLE_SCORE_RECORDED`，证明专家答案在 EBench metric 下能得分。Gate 5 通过前，任何 `score=0.0` 都不能解释成 expert 失败。

更直白地说，后续不按“再跑一次试试看”推进，而按下面的判定梯子推进：

| 判断层 | 下一步动作 | 预计能回答的问题 | 通过后才能做什么 | 失败/缺证据时怎么停 |
| --- | --- | --- | --- | --- |
| A3k2b debug-gate validation | 只执行 1 个 action point，验证 generated Lift2 task 的 live obs 是否带 `debug.labutopia_open_door` | 仪表有没有真正进入 EBench 考场 | 允许 exactly 1 次 full A3k2 same-candidate readback rerun | 停在 instrumentation/environment blocker；不能换 candidate、不能判 route 失败 |
| A3k2c same-candidate readback | 固定 `A3L_XP15_YP25_KEEP_YAW` + `A3J2_CORRECTED_CENTER`，用完整 joint/EE/contact/controller schema 判定 | 这条已规划路线是否真的执行到预接触位、且没有异常接触 | 如果 runner/postprocess 读数一致且通过，则进入 A3m | 当前读数不一致，不能直接判 route 失败 |
| A3k2d readback consistency audit | 0 live，重算 A3k2c 现有 trace/summary 的 final worker obs、final applied target、joint/EE/contact/controller | “尺子”是否读一致；如果一致，selected candidate 是否真的失败 | schema 闭合且失败，才允许 A3k bounded fallback；schema 闭合且通过，则进入 A3m | schema 仍不闭合就停在 telemetry contract，不许换 candidate 盲跑 |
| A3k bounded fallback | 仅在 A3k2d schema 闭合且第一个 candidate 真失败后，最多尝试 A3l 剩余 2 个 pass candidates | A3l base-layout route family 是否还有可用候选 | 任何一个通过则进入 A3m | 3 个 A3l pass candidate 全失败，判 `A3l base-layout route family no-go`，转 A3r 或上层 no-go review |
| A3m contact-readiness | 不拉门，只检查 gripper-to-handle clearance、finger frame、真实 collision/contact | 到把手前以后是否有资格进入接触 | 允许 Gate 2 contact | 失败则停在 contact geometry，不进入拉门或 score |
| Gate 2/3/4 | contact、retention、micro-pull + door joint readback | 工程上是否真的能抓住并带动门 | Gate 4 通过后才可说“工程上接近会开门” | 在对应层失败就停在对应层，不越级算分 |
| Gate 5 Expert Oracle Score | 在 EBench metric 下记录 expert score | 评测口径是否真正闭环 | 才能说“专家答案在 EBench 下能出分” | 失败才讨论 metric/oracle/score，不把前面 blocked 的 0 分当 expert 失败 |

当前最近的判断点已经从 A3j2 推进到 A3k1/A3k2。A3j2 的 5 个 corrected handle-front 候选全部
`IK_FAIL`，已经停止了 fixed selected route；A3l 随后只改 Lift2 base/layout，5 个候选里 3 个能
planner success 且产生 nonzero trajectory，所以当前不能说“Lift2 全局到不了把手前”。A3k 又进一步证明
selected candidate 已经实际执行 `142` steps，但 A3k1 离线审计发现旧 run 的 readback 仍不能判 pass：
Lift2 12D arm joint readback 和 16D action target 的正确映射已闭合，gripper 在容差内，但 12D arm joint
最大误差 `2.571020245552063rad` 超过 `0.02rad`；right-arm EE world-frame tolerance 和 full-run
collision/contact telemetry 仍未闭合。

当前预计节点如下；这也是 no-blind-trial 的执行边界：

- A3k2 instrumentation expansion 已完成 code-ready：runner/postprocess 现在能聚合三类 A3k2 必需仪表：
  right-arm world EE、controller/applied-target tail readback、full-run contact aggregation。这个结论只覆盖
  code/test，不是 live pass。
- A3k2 same-candidate live rerun 已执行：
  `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_same_candidate_live_rerun_20260706/result_compact.json`。
  它固定同一个 `A3L_XP15_YP25_KEEP_YAW` candidate、同一个 `A3J2_CORRECTED_CENTER` route、独立端口
  `18121`、独立 run_id，并强制 `--step-chunk-size 1` 和 debug env。结果是
  `BLOCKED_A3K2_SAME_CANDIDATE_INSTRUMENTED_READBACK_NOT_READY_FOR_A3M`，`executed_steps=143`，
  final planner record 仍是 `a3j2_corrected_center`。
- A3k2 的 live 结果不能解释成 selected route 失败。root cause 是 generated Lift2 candidate task name
  `ebench/labutopia_lab_poc/lift2_candidate/a3l_base_layout/a3l_xp15_yp25_keep_yaw` 不满足原来的
  `_is_open_door_task()` gate；原 gate 只接受 leaf 为 `level1_open_door` 或 `level1_open_door_*` 的任务，
  所以 `LABUTOPIA_ORACLE_DEBUG_OBS=1` / `LABUTOPIA_ORACLE_PHYSX_CONTACT_OBS=1` 虽然设置了，
  `debug.labutopia_open_door` 仍没有进入 live obs。runner 的聚合 schema 存在，但
  `action_application_debug_sample_count=0`、`contact_sample_count=0`、`missing_contact_sample_count=143`、
  right-arm EE source 是 `missing_or_ambiguous`。
- A3k2 generated-task-name debug gate 已做 TDD code closure：
  `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_generated_task_name_debug_gate_closure_20260706.json`。
  新增 regression test 先 RED 为 `KeyError: debug.labutopia_open_door`，修复后 focused `1 passed`，
  debug-state suite `29 passed`。这只是 code-ready，不是 live rerun。
- A3k2b generated-task-name debug-gate validation 已通过。它不换 candidate、不做 contact、不做
  micro-pull、不做 score；只证明 generated Lift2 candidate 的 live obs 里真的出现
  `debug.labutopia_open_door`，并且能带出 right-arm world EE、controller/tail debug、full-run contact
  samples。A3k2b 通过后，才允许 exactly 1 次 full A3k2 same-candidate readback rerun；A3k2b 仍不允许
  进入 A3m，也不能启用 fallback candidates。
- A3k2 必须同时满足这些 evidence fields 才能算 fixed：`runner_exit_code == 0`、`executed_steps > 0`、
  final planner label 是 `a3j2_corrected_center`、`readback_schema == lift2_split_arm_gripper_obs_to_16d_action`、
  12D arm joint readback error <= `0.02rad`、right-arm EE frame 是 world、EE translation error <= `0.03m`、
  EE orientation error <= `15deg`、`a3k2_controller_debug.v1` 存在且包含
  `final_applied_action_target_16d` / planned-executed action counts / `tail_joint_error_series`、
  `a3k_full_run_collision_contact_readback.v1` 存在且 `contact_sample_count == executed_steps`、
  `missing_contact_sample_count == 0`、`invalid_contact_sample_count == 0`，并且真实 table surface、door body、
  abnormal unmatched contact counts 全部为 0。
- 如果 A3k2b 之后 live 仍缺 world-frame EE、controller debug、full-run contact telemetry，或这些 sample
  shape 无效，则结论仍是 instrumentation/environment blocker；先修仪表，不允许把它解释成 route、contact、
  score failure，也不允许换 candidate 盲跑。
- 如果 A3k2 live 的 schema/readback 已闭合，但 selected candidate 的 arm joint、right-arm EE 或
  full-run contact 任一项真实失败，就停止当前 selected candidate；不能进入 A3m，也不能临场调参数重跑同一
  candidate。
- 只有 A3k2d schema/readback consistency audit 闭合并证明 selected candidate 真实失败后，才允许 A3k bounded fallback：最多尝试 A3l 另外 2 个 pass
  candidate，且必须使用同一套 evidence fields。若 3 个 A3l pass candidate 全部在同一 readback schema
  下失败，才能判定 `A3l base-layout route family no-go`，转 A3r fixed-layout route redesign 或上层
  no-go review。
- A3m 通过后，只能说“到把手前并且接触前姿态安全”；这还不是开门。A3m 失败则停在 contact geometry，
  不能进入 Gate 2/3/4/5。
- Gate 4 通过后，才能说“工程上已经能带动门”；因为 micro-pull 和 door joint readback 已证明门被带动。
- Gate 5 通过后，才能说“评测口径弄好”；因为 `Expert Oracle Score` 已被 EBench metric 记录。

2026-07-06 updated no-blind-trial plan：A3k bounded fallback 已经消耗完 A3l 剩余两个 planner-success
候选，三个候选全部 closed-schema readback 失败。因此最近的下一步不是 A3m，而是 E0/E1：

| 新阶段 | 最多 live | 做什么 | 通过后 | 停止条件 |
| --- | ---: | --- | --- | --- |
| E0 evidence freeze | 0 | 固化三条 A3l planner-success 候选的 readback 失败、contact clean、误差数字 | 允许进入 E1 | 缺 closed-schema 或 contact coverage 就先补证据 |
| E1 controller/execution contract audit | 0 | 只读代码和 trace，核对 trajectory -> 16D action -> controller target -> final obs/readback | 找到明确可修或可验证假设后，允许 E2 | 找不到可修合同，当前 A3l route family 不再 live |
| E2 Lift2 controller reference / retiming probe | 1 | 用 non-DryingBox 的 5 no-op + 5 right-arm small ramp + 60 terminal hold 校准 controller/readback | baseline/hold 到位才允许迁移 DryingBox；若 ramp fail 但 hold pass，则后续必须 retiming/terminal hold | no-op 或 terminal hold 都不到位，先修 Lift2 controller/action contract |
| E3 DryingBox EBench-style pose compute | 0 | 按 EBench-style oracle 重新计算 DryingBox precontact target/action | schema 静态闭合后允许 E4 | frame/arm/action 不闭合就不 live |
| E4 one-segment closed execution | 1 | 只跑 DryingBox precontact 单段，不接触、不拉门、不算分 | 若到位，说明新 expert/control handoff 有戏 | 若 E2 过但 E4 失败，停止该 DryingBox handoff |
| E5 full oracle dry run | 1 | 多段到接触前，仍不 contact/score | 通过才进入 A3m | 多段漂移或 controller 不跟随，停在 trajectory sequencing/control tracking |

预计口径：最快能看到“这条新思路有戏”的节点是 E4；工程上接近“能开门”的节点仍是 Gate 4；
产品上可以宣布“EBench expert 评测口径闭环”的节点只能是 Gate 5。若 E1 找不到可修 contract，
或 E2 reference probe 都无法到位，就可以得出当前 Lift2 execution/readback contract 不支持继续 DryingBox
oracle 迭代的结论；若 E2 过但 E4 失败，则可以得出当前 DryingBox EBench-style target/control handoff
不成立的结论。

合理得出“这条路线不该继续”的停止点：

- A1a preflight 不能证明 effective `ASSETS_DIR` 是 composite root，或缺 `robot_usds/lift2/robot.usd` / `miscs/curobo/R5a/r5a_left_arm.yml`：停止 A1b，不启动 Isaac。实际已通过。
- A1b corrected live 仍卡 reset result、没有 snapshot，或 reset 成功但 16D action step contract 不通过：停止 A2，不做 oracle。实际 A1b reset/action 通过，但 logging blocked。
- A1c logging closure 仍有任意 schema row `BLOCKED` / `FAIL`：停止 A2，不做 oracle。实际已通过。
- A2 不能设计出合法 Lift2 oracle / retarget，或需要把 Franka 7D joint action 直接冒充 Lift2 16D action：停止 A3，不做 live。
- A3 单条 oracle route 在 planner update 前就失败：先做 A3a root-cause review，不允许现场扫 offset、
  contact pose 或 orientation。实际 A3 已触发这个停止线。
- A3a 不能明确 `arm=left|right`，或 A3b dry validation 仍会落到 `arm=default`：停止 live。实际
  A3a/A3b 已选择 `right` 并 dry pass。
- revised A3/A3c 仍是 `planner_update_unavailable`：停止 live，把问题归为 Lift2 dual-arm planner API /
  route contract 未闭合。实际 A3c 已越过这一层。
- A3c 进入 cuRobo 但在 target reachability 前返回 `INVALID_START_STATE_WORLD_COLLISION`：停止 live，
  先做 A3d start-state collision review。实际已触发这个停止线。
- A3d 不能解释 sphere 17/table collision，或同帧 clearance 证明机器人确实物理压进桌子：停止当前
  Lift2 reset/layout/collider contract，回到 reset/base/joint/table-collider review。
- A3d 只能通过 planner-only table exclusion 才让 planner 继续，但没有独立 physical clearance 证据：
  仍然停止，不能把 blind ignore table 当作修复。
- A3e 只能算 diagnostic code/readiness checkpoint；如果下一步 diagnostic request 不能产出
  `support_surface_clearance_records`，或者仍是 frame mismatch / physical intersection / non-exact
  ignore candidate，则停止当前 Lift2 reset/layout/collider contract。
- A3e 已实际产出 `support_surface_clearance_records`，且触发上面的停止条件：same-frame physical
  intersection、`planner_only_support_surface_exclusion_allowed=false`。因此 A3f 当前不允许启动。
- A3g 已证明当前 no-go 的 first repair target 是 planner world 把非 `PhysicsCollisionAPI` 的完整 table
  visual mesh 纳入 collision obstacle，而不是 policy 或 score 失败。下一步 A3h 只能做 scoped repair
  preflight：移除/禁用这个 visual table mesh 的 planner collision，同时保留
  `/World/labutopia_level1_poc/obj_table/surface/mesh` 或等价真实 table collision surface。
- A3h 如果只能靠 ignore 整个 `/obj_table`、删除真实 table surface、或仍撞同一个 visual mesh，则停止，
  不能进入 A3f。A3h 如果把 blocker 转移到真实 physics surface 且 same-frame clearance 仍为负，则进入
  A3i reset/base/joint seed review，不进入 A3f。
- A3h 0002 已经把第一硬门推进到 handle-front near `IK_FAIL`。但因为 `executed_steps=0` 且缺 explicit
  filter telemetry，不能把它解释成 full execution 或 full planner-world closure；下一步只能补 telemetry
  或进入 A3j bounded handle-front reachability。
- A3j 先做 target equivalence closure：如果 A2b intended target 与 A3h runtime target 的 `0.045m`
  world-X mismatch 不能通过 corrected local coordinate dry forward-check 关闭，停止在 target-frame
  convention review，不进入 IK sweep。
- A3j2 在 target equivalence 关闭后，固定 handle frame、front direction、robot base、joint seed，只允许
  最多 5 个 pregrasp/orientation diagnostic。如果全部 `IK_FAIL`，停止当前 selected Lift2 oracle route，
  转 layout/base/official Lift2 placement 或 A2 route design review；不能继续加大 waypoint sweep。
- A3j2 已实际触发该停止条件：5 个 child run 全部 `MotionGenStatus.IK_FAIL`、0 trajectory、0 executed
  steps。因此当前 selected route 停止，A3k 不解锁。
- A3l 的停止线：official placement 只能作为小矩阵 base-layout diagnostic；如果需要删除真实 table
  surface、扩大到 broad base sweep、或把 A3j2 的 handle target 又改掉，则停止。A3l live 已通过：
  3/5 candidate 有 planner success 和 nonzero trajectory，解锁 A3k；但因为 `executed_steps_total=0`，
  它不证明执行、接触、开门或 score。
- A3r 的停止线：固定 layout route redesign 只能试最多 5 个 terminal orientation/approach-source 候选；
  如果全失败，停止 fixed-layout route redesign，不能继续加中间 waypoint 或把 contact/score 混进来。
  因为 A3l 已通过，A3r 目前保留为 fallback，不抢在 A3k 前执行。
- A3k 的通过标准已收紧：只允许一个 selected A3l pass candidate 做 short execution readback；必须产生
  nonzero executed steps，final EE translation error <= `0.03m`、orientation angular error <= `15deg`，
  且没有真实 table surface / door body 异常 collision。否则停止 route geometry 调参，转
  controller/sim contract 或 base-layout readback review。
- A3k1 已把旧 A3k 的 `state_joints_missing` 改判为 readback comparator/schema 问题，而不是 runtime
  完全没有状态。A3k1 已关闭 Lift2 split schema：12D `state.joints` 是 arm-only，4D `state.gripper`
  是 gripper-only，16D action 是 left arm / left gripper / right arm / right gripper。用这个 mapping
  重算旧 trace 后，gripper 通过但 arm joint readback 超容差，所以旧 run 不能升级成 A3k pass。
- A3k2 live 前必须先完成 package postprocess closure；该 closure 已完成并明确 `ready_to_rerun_live=false`。
  postprocess 现在能读取 corrected split readback、debug by-arm right EE、显式 EE frame 和 full-run
  collision/contact schema，也会把 final obs 的 `physx_contact_debug` 显式标成 final-step-only，不会冒充
  full-run no-abnormal-contact。
- A3k2 live 前还必须完成 instrumentation expansion。world-frame right EE transform 已 code-ready，但 live
  package 还必须实际提供 full-run contact coverage、controller applied target 和 tail joint error series。
  缺任一项都继续 blocked，不消耗唯一 rerun。
- A3k2b PASS 之后的 full A3k2 same-candidate readback rerun 预算写死为 exactly 1。该预算已经由
  A3k2c 消耗。这个预算不同于已经消耗的 A3k2 debug-missing run，也不同于 A3k2b 1-step diagnostic；
  它只能用于“仪表已进 live obs 后”对同一个 candidate 做一次完整 readback。A3k2c 已证明 full-run
  contact telemetry 闭合，且 trace 最后一帧确实含 `state.joints` / `state.gripper`；但 runner summary
  与 postprocess readback schema 仍不一致，所以现在先做 A3k2d 离线 consistency audit。A3k2d 之前，
  不允许把 A3k2c 解释成 selected candidate 真实失败，也不允许启动 A3k bounded fallback。
- A3m 已定义为 contact-readiness / no-contact guard：只有 A3k 到位后才检查 gripper-to-handle
  clearance、finger frame 和 collision telemetry；A3m 不拉门，不算分，只决定是否能进入 Gate 2 contact。
- A3f 在 start-state collision 和 handle-front reachability 修正后进入 target reachability，但仍是
  `IK_FAIL`、0 action points、missing readback 或 readback outside tolerance：停止当前 selected Lift2
  oracle route，回到 A2 route design review，而不是继续硬扫。
- Gate 2/3/4 分别在 contact、retention、micro-pull/readback 失败：在对应层写 blocked/fail，不能越级算 Expert Oracle Score。

## File Responsibilities

- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1t_c2f_equivalent_target_live_20260706/result_compact.json`: C lane stop evidence and A entry reason.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_lift2_contract_fork_review_20260706.json`: A lane prepared review manifest.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/result_compact.json`: A1 first live reset-pending / assets-root blocker evidence.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1a_assets_root_reset_contract_20260706.json`: A1a assets-root preflight pass evidence.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1b_lift2_live_schema_probe_corrected_20260706/result_compact.json`: A1b corrected live reset/action pass plus logging blocker evidence.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_lift2_live_schema_probe_logging_closed_20260706/result_compact.json`: A1c live schema/action/logging pass evidence.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3c_lift2_right_arm_single_live_20260706/result_compact.json`: revised right-arm live evidence, blocked by start-state table collision before actions.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3d_right_arm_start_state_collision_review_20260706.json`: read-only / zero-live stop-go plan before any further live route.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_runner_checkpoint_20260706.json`: runner code checkpoint for support-surface diagnostic payload passthrough; not live evidence.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3e_support_surface_diagnostic_request_20260706/`: executed diagnostic request package; blocks A3f due to same-frame physical table intersection.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3g_reset_layout_collider_contract_review_20260706.json`: static reset/layout/collider review; maps sphere 17 to Lift2 link6 and identifies the A3e blocker as a non-PhysicsCollisionAPI table visual mesh, with A3h scoped planner-world repair as the next step.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3h_planner_world_visual_mesh_repair_preflight_20260706/result_compact.json`: A3h live diagnostic result; first staging waypoint plans with 84 points, second handle-front near waypoint remains `MotionGenStatus.IK_FAIL`, no action execution, no contact/score claim.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3h_runtime_filter_telemetry_code_checkpoint_20260706.json`: A3h diagnostic output checkpoint; exposes exact non-physics filter telemetry in start-state collision debug for a future A3h-telemetry rerun.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j_handle_front_runtime_target_equivalence_review_20260706.json`: A3j zero-live review; identifies a `0.045m` mismatch between A2b intended world target and A3h runtime target, blocking reachability sweep until corrected target forward-check.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j1_corrected_target_forward_check_20260706.json`: A3j1 zero-live forward-check; proves corrected local Y maps back to the intended handle-front world target within `0.01m`, allowing A3j2 bounded reachability planning.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_handle_front_reachability_matrix_20260706.json`: A3j2 prepared candidate matrix; fixes the bounded five-candidate reachability set and stop line before any next live run.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_handle_front_reachability_matrix_20260706/route_manifest.json`: A3j2 runner-consumable route manifest with exactly five right-arm candidate route ids.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3j2_bounded_reachability_live_20260706/aggregate_summary.json`: A3j2 live aggregate over five independent child runs; all five handle-front candidates returned `MotionGenStatus.IK_FAIL`, so the selected route hit the bounded stop line.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_official_lift2_placement_base_layout_review_20260706.json`: A3l zero-live review; records why the next hypothesis is official-style Lift2 base/layout rather than a sixth A3j2 offset.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_base_layout_candidate_matrix_20260706.json`: A3l five-candidate base-layout matrix; all candidates fix the corrected handle target and route while varying only `robots[0].position/orientation`.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3l_base_layout_live_20260706/aggregate_summary.json`: A3l live aggregate over five independent child runs; three base-layout candidates planned successfully with nonzero trajectories, unlocking A3k short execution readback.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3r_fixed_layout_terminal_orientation_review_20260706.json`: A3r bounded fallback review; retained but not executed next because A3l produced planner-success candidates.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/selection_manifest.json`: A3k selected-candidate manifest; fixes one A3l pass candidate, action budget, joint/EE readback tolerances, and no-contact/no-score boundary. It has now been consumed by A3k live and blocked on readback instrumentation.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k_short_execution_readback_20260706/result_compact.json`: A3k live compact result; `executed_steps=142`, but A3k remains blocked because joint/EE/collision readback fields are missing or ambiguous.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k1_offline_readback_mapping_audit_20260706.json`: A3k1 zero-live audit; closes Lift2 split arm/gripper readback mapping and proves the saved A3k run does not reach the 12D arm joint target within tolerance.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_code_checkpoint_20260706.json`: A3k2 code checkpoint; prepares corrected runner readback and dual-arm EE debug fields but explicitly blocks live rerun until package postprocess closure consumes those fields and collision/contact telemetry.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_package_postprocess_closure_20260706.json`: A3k2 package stop-go checkpoint; adds tested postprocess logic for debug by-arm right EE, EE frame gating, full-run contact coverage, controller/applied-target fields, and the single-rerun budget ledger. It still blocks live rerun until instrumentation expansion provides the required data.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_step_sampling_checkpoint_20260706.json`: A3k2 instrumentation expansion first checkpoint; adds optional runner step sampling for future full-run telemetry but explicitly does not close world-frame EE, abnormal-contact, or controller/applied-target evidence.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_world_ee_checkpoint_20260706.json`: A3k2 instrumentation expansion world-EE checkpoint; emits right-arm world EE using the right-arm base reference transform and updates postprocess priority, while still blocking live until contact/controller aggregation is closed.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_controller_checkpoint_20260706.json`: A3k2 instrumentation expansion controller checkpoint; aggregates per-step evaluator action-application debug into `a3k2_controller_debug.v1`, while still blocking live until full-run abnormal contact aggregation and refreshed package closure are present.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_instrumentation_expansion_full_run_contact_checkpoint_20260706.json`: A3k2 instrumentation expansion full-run contact checkpoint; aggregates per-step PhysX contact debug into `a3k_full_run_collision_contact_readback.v1` and keeps final-step-only contact debug blocked as insufficient.
- `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3k2_same_candidate_live_rerun_20260706/selection_manifest.json`: A3k2 same-candidate live rerun package; fixes the single candidate/run_id/port/debug env and points to server, runner, and postprocess commands.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml`: candidate Lift2 task config.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json`: candidate Lift2 task index.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/lift2_eval_contract_probe.py`: single-task live schema/action contract probe.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/native_action_path_runner.py`: selected route planner/action runner; now includes optional `--step-chunk-size` for A3k2 per-step sampling diagnostics, `a3k2_controller_debug.v1` aggregation from evaluator action-application debug, and `a3k_full_run_collision_contact_readback.v1` aggregation from per-step PhysX contact debug.
- `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/genmanip/core/evaluator/labutopia_oracle_debug_state.py`: LabUtopia debug obs instrumentation; now emits right-arm EE reference-frame/world-frame provenance for dual-arm embodiments when available.
- `docs/labutopia_lab_poc/aan_consumer_handoff.md`: PM and next-engineer status.
- `docs/labutopia_lab_poc/expert_oracle_score_plan.md`: score remains blocked until Lift2 Gate 1/2/3/4 pass.
- `docs/labutopia_lab_poc/evidence_manifests/README.md`: evidence index.

## Task 1: A0 Static Lift2 Contract Audit

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a0_lift2_static_contract_audit_20260706.json`

- [x] **Step 1: Run static YAML/JSON audit**

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
TASK=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml
INDEX=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json
"$PY" - <<'PY'
import json, pathlib, yaml
task = pathlib.Path("/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml")
index = pathlib.Path("/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/configs/tasks/ebench/labutopia_lab_poc/lift2_candidate/lift2_candidate.json")
doc = yaml.safe_load(task.read_text())
cfg = doc["evaluation_configs"][0]
idx = json.loads(index.read_text())
print("task_name", cfg["task_name"])
print("usd_name", cfg["usd_name"])
print("robot_type", cfg["robots"][0]["type"])
print("action_shape", cfg["labutopia_lift2_contract"]["action_contract"]["action_shape"])
print("goal_type", cfg["generation_config"]["goal"][0][0]["type"])
print("joint_name", cfg["generation_config"]["goal"][0][0]["joint_name"])
print("index_tasks", idx)
PY
```

Expected:

```text
robot_type manip/lift2/R5a
action_shape [16]
goal_type manip/default/check_joint_angle
joint_name RevoluteJoint
```

- [x] **Step 2: Write A0 manifest**

Wrote `eos2_gate1u_a0_lift2_static_contract_audit_20260706.json` with:

```json
{
  "stage": "EOS-2 Gate 1U-A0 Lift2 Static Contract Audit",
  "status": "PASS_A0_LIFT2_STATIC_CONTRACT_READY_FOR_A1_LIVE_SCHEMA_PROBE",
  "robot_type": "manip/lift2/R5a",
  "action_shape": [16],
  "metric": "manip/default/check_joint_angle on obj_DryingBox_01 RevoluteJoint",
  "asset_authority_note": "lift2_candidate uses the historical LabUtopia scene path; this is allowed for robot-contract probing but must not be mixed with AAN-11 evidence.",
  "expert_oracle_score_allowed": false
}
```

If any assertion fails, status must be:

```text
BLOCKED_A0_LIFT2_STATIC_CONTRACT_MISMATCH_STOP_BEFORE_LIVE
```

- [x] **Step 3: Validate A0 JSON**

Run:

```bash
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a0_lift2_static_contract_audit_20260706.json >/dev/null
```

Expected: exit `0`.

## Task 2: A1 Prepare Single Live Schema/Action Probe

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/README.md`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/server.command.txt`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/submit.command.txt`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/probe.command.txt`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/selection_manifest.json`

- [x] **Step 1: Prepare command package**

Use:

```text
run_id=eos2_gate1u_a1_lift2_live_schema_probe_20260706_0001
port=18111
ray_tmpdir=/tmp/gm_gate1u_a1_lift2_18111
task_config=ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml
probe=standalone_tools/labutopia_poc/lift2_eval_contract_probe.py --live --joint-position-count 16
```

Do not run expert, score, contact, or route oracle in A1.

- [x] **Step 2: Validate command syntax**

Run:

```bash
bash -n docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/server.command.txt
bash -n docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/submit.command.txt
bash -n docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/probe.command.txt
```

Expected: all exit `0`.

## Task 3: A1 Run Single Live Schema/Action Probe

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/lift2_contract_snapshot.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/result_compact.json`

- [x] **Step 1: Start server and submit**

Run server on port `18111`, wait for `/status`, then submit `ebench/labutopia_lab_poc/lift2_candidate/level1_open_door.yml`.

- [x] **Step 2: Run live probe**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PY=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python
"$PY" standalone_tools/labutopia_poc/lift2_eval_contract_probe.py \
  --live \
  --host 127.0.0.1 \
  --port 18111 \
  --worker-id 0 \
  --run-id eos2_gate1u_a1_lift2_live_schema_probe_20260706_0001 \
  --task-name level1_open_door \
  --joint-position-count 16 \
  --output /cpfs/shared/simulation/zhuzihou/dev/LabUtopia/docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/lift2_contract_snapshot.json
```

- [x] **Step 3: Classify A1**

Pass:

```text
PASS_A1_LIFT2_LIVE_SCHEMA_ACTION_PROBE_READY_FOR_A2_ORACLE_DESIGN
```

Required evidence:

```text
claim_boundary.probe_status=single-task live schema probe passed
schema_rows all PASS
action dialects PASS with 16D action
camera input keys PASS
reward/success fields PASS
```

Fail/block:

```text
BLOCKED_A1_LIFT2_RUNTIME_OR_ACTION_CONTRACT
```

Actual first-live classification:

```text
LIVE_BLOCKED_A1_RESET_RESULT_PENDING_ASSETS_ROOT_OVERRIDE_MISSING_STOP_BEFORE_A2
```

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/result_compact.json
probe.stdout.txt: connected to server, worker ['0'], polling reset result
probe.stderr.txt: KeyboardInterrupt in EvalClient._resolve_pending_resets during client.reset()
Isaac Kit log: tried to load EBench-Assets-Overlay/.../robot_usds/lift2/robot.usd and could not open it
```

Do not claim route reachability, contact, door opening, Expert Oracle Score, policy score, or official score from A1.

## Task 4: A1a Assets-Root and Reset-Result Closure

**Files:**
- Modify: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/server.command.txt`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1a_assets_root_reset_contract_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1b_lift2_live_schema_probe_corrected_20260706/`

- [x] **Step 1: Add deterministic preflight before Isaac**

Required checks:

```bash
GENMANIP_WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
COMPOSITE_ASSETS_ROOT=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets
test -L "$GENMANIP_WORKTREE/saved/assets"
test "$(readlink -f "$GENMANIP_WORKTREE/saved/assets")" = "$COMPOSITE_ASSETS_ROOT"
test -f "$GENMANIP_WORKTREE/saved/assets/robot_usds/lift2/robot.usd"
test -f "$GENMANIP_WORKTREE/saved/assets/miscs/curobo/R5a/r5a_left_arm.yml"
test -f "$GENMANIP_WORKTREE/saved/assets/scene_usds/labutopia/level1_poc/lab_001/scene.usda"
```

Expected status:

```text
PASS_A1A_ASSETS_ROOT_PREFLIGHT_READY_FOR_CORRECTED_A1B_LIVE
```

If any check fails:

```text
BLOCKED_A1A_EFFECTIVE_ASSETS_ROOT_INVALID_STOP_BEFORE_LIVE
```

- [x] **Step 2: Pin the runtime assets override in the server command**

Add to the corrected server command package:

```bash
export LABUTOPIA_POC_ASSETS_OVERLAY_ROOT="$WORKTREE/saved/assets"
```

The corrected run must record:

```text
effective_labutopia_poc_assets_overlay_root=$WORKTREE/saved/assets
effective_assets_realpath=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets
lift2_robot_usd_exists=true
r5a_curobo_left_arm_exists=true
```

- [x] **Step 3: Run exactly one corrected A1b live probe**

Use a fresh run id and port. Do not reuse `18111` while it is still occupied.

Pass:

```text
PASS_A1B_LIFT2_RESET_SCHEMA_ACTION_CONTRACT_READY_FOR_A2_ORACLE_DESIGN
```

Required evidence:

```text
reset observation returned
lift2_contract_snapshot.json exists
schema_rows all PASS
16D joint_position action step returns
camera/reward/success/metric fields present
post_shutdown_curl_exit_code=7
```

Fail/block:

```text
BLOCKED_A1B_LIFT2_RESET_OR_ACTION_CONTRACT_AFTER_ASSETS_ROOT_FIX
```

Actual A1b classification:

```text
LIVE_BLOCKED_A1B_LOGGING_METADATA_INCOMPLETE_RUNTIME_ACTION_CONTRACT_PASSED_NEEDS_A1C
```

Evidence:

```text
reset observation returned
lift2_contract_snapshot.json exists
observation keys PASS
camera input keys PASS
action dialects PASS for zero_action / openpi_relative_base_motion / xvla_absolute_base_motion
reward/success fields PASS
logging fields BLOCKED because episode_id, seed, result_path, stdout_path, stderr_path were missing
```

Because A1b blocked only on evidence metadata, A1c was allowed after a written root-cause review:
`docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_logging_metadata_closure_review_20260706.json`.

## Task 4b: A1c Logging Metadata Closure

**Files:**
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/standalone_tools/labutopia_poc/lift2_eval_contract_probe.py`
- Modify: `/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback/tests/labutopia_poc/test_lift2_eval_contract_probe.py`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_logging_metadata_closure_review_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_lift2_live_schema_probe_logging_closed_20260706/result_compact.json`

- [x] **Step 1: Write failing logging-enrichment test**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. /usr/bin/python -m pytest tests/labutopia_poc/test_lift2_eval_contract_probe.py::test_live_probe_enriches_logging_metadata_from_episode -q
```

Expected before implementation: FAIL because `logging fields` stays `BLOCKED`.

- [x] **Step 2: Implement minimal live metadata enrichment**

The probe now enriches logging from reset observation and environment:

```text
episode_id from observation
seed from episode_id tail
result_path from GENMANIP_RESULT_DIR / episode_id / steps.jsonl
stdout_path from GENMANIP_PROBE_STDOUT_PATH
stderr_path from GENMANIP_PROBE_STDERR_PATH
```

- [x] **Step 3: Verify tests**

Run:

```bash
cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
PYTHONPATH=. /usr/bin/python -m pytest tests/labutopia_poc/test_lift2_eval_contract_probe.py -q
```

Expected and observed:

```text
13 passed
```

- [x] **Step 4: Run exactly one A1c fresh live probe**

Actual A1c classification:

```text
PASS_A1C_LIFT2_LIVE_SCHEMA_ACTION_LOGGING_PROBE_READY_FOR_A2_ORACLE_DESIGN
```

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_lift2_live_schema_probe_logging_closed_20260706/result_compact.json
claim_boundary.probe_status=single-task live schema probe passed
schema rows all PASS
reset observation present
zero_action/openpi_relative_base_motion/xvla_absolute_base_motion step responses present
probe stderr is empty
post_shutdown_curl_exit_code=7
```

Do not claim route reachability, contact, door opening, Expert Oracle Score, policy score, official score, Stage 7 aggregate pass, or full task completion from A1c.

## Task 5: A2 Lift2 Oracle Design Gate

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2_lift2_oracle_design_review_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2b_lift2_target_waypoint_static_audit_20260706.json`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2c_lift2_translator_dry_contract_20260706.json`
- Modify: `docs/labutopia_lab_poc/expert_oracle_score_plan.md`
- Modify: `docs/labutopia_lab_poc/aan_consumer_handoff.md`

- [x] **Step 1: A2a choose one allowed oracle path, zero live**

Allowed options:

```text
LIFT2_SCRIPTED_ORACLE
LIFT2_RETARGETED_FRANKA_INTENT
OFFICIAL_BASELINE_POLICY_SMOKE_ONLY
```

Recommended first choice is:

```text
LIFT2_SCRIPTED_ORACLE
```

Reason: it keeps A/Lift2 independent from the failed Franka joint-action contract and can directly target
Lift2/R5a `16D joint_position`. `LIFT2_RETARGETED_FRANKA_INTENT` is allowed only if it retargets semantic
intent / waypoint goals, not Franka 7D joint positions. `OFFICIAL_BASELINE_POLICY_SMOKE_ONLY` is diagnostic
only and cannot produce `Expert Oracle Score` unless it exposes scoring-eligible expert actions.

- [x] **Step 2: Write A2a review manifest**

The manifest must include:

```text
selected_oracle_path
input_action_contract
output_action_contract=Lift2/R5a 16D joint_position
score_enabled=false
gate2_contact_allowed=false until Gate1 pass
max_selected_live_route_count=1
```

Stop at A2a if:

```text
selected_oracle_path requires Franka 7D joint positions as Lift2 16D action
selected_oracle_path cannot define output_action_contract=Lift2/R5a 16D joint_position
selected_oracle_path depends on score feedback before Gate 1/2/3/4 evidence
```

Actual A2a classification:

```text
PASS_A2A_LIFT2_SCRIPTED_ORACLE_SELECTED_READY_FOR_A2B_TARGET_WAYPOINT_AUDIT
```

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2_lift2_oracle_design_review_20260706.json
selected_oracle_path=LIFT2_SCRIPTED_ORACLE
output_action_contract=Lift2/R5a 16D joint_position
a2_live_budget=0
a3_max_selected_live_route_count=1
score_enabled=false
```

- [x] **Step 3: A2b target/waypoint static audit, zero live**

Audit and write:

```text
DryingBox joint prim and RevoluteJoint metric target
handle frame prim used for object-frame targets
front approach pose definition
contact pose definition
pull direction definition
coordinate convention for local/object/world frames
expected stop gate if target-frame equivalence is not proven
```

Stop at A2b if:

```text
handle-front approach pose is underdefined
target frame cannot be mapped to EBench object_frame or world target
pull direction does not correspond to DryingBox RevoluteJoint opening direction
```

Actual A2b classification:

```text
PASS_A2B_DRYINGBOX_TARGET_WAYPOINT_STATIC_AUDIT_READY_FOR_A2C_TRANSLATOR_DRY_CONTRACT
```

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2b_lift2_target_waypoint_static_audit_20260706.json
metric_joint_prim=/World/labutopia_level1_poc/obj_obj_DryingBox_01/RevoluteJoint
handle_prim=/World/labutopia_level1_poc/obj_obj_DryingBox_01/handle
front_approach local=[-0.061955757838629166,-0.020816618383194208,1.1611298411651205e-07]
front_approach adjusted_world=[0.4797899613973845,0.3107189912618622,1.1085915534527668]
contact is reserved for Gate 2
reconstruction_error_m=5.55e-17
```

- [x] **Step 4: A2c translator dry contract, zero live or fake-client only**

Prove without Isaac live:

```text
oracle output is Lift2/R5a 16D joint_position
base_motion contract is explicit
sequence metadata includes route id, waypoint ids, coordinate frame, and claim boundary
probe/runner can accept the generated action payload in fake-client or dry contract mode
score_enabled=false
```

Stop at A2c if:

```text
translator emits malformed 16D action
translator omits frame/waypoint evidence needed to debug live
translator depends on contact, micro-pull, or score to decide basic route validity
```

Actual A2c classification:

```text
PASS_A2C_LIFT2_TRANSLATOR_DRY_CONTRACT_READY_FOR_A3_SINGLE_LIVE_PACKAGE
```

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2c_lift2_translator_dry_contract_20260706.json
16D action dialect classification PASS
native_action_path_runner now supports expected_action_dim
runner rejects 7D action when expected_action_dim=16
runner tests: 6 passed
```

Important A3 command requirement:

```text
native_action_path_runner.py --expected-action-dim 16
```

- [x] **Step 5: Update PM docs**

Docs must say:

```text
C lane stopped.
A1c proves only Lift2 runtime/action/logging readiness.
A2 is a zero-live design gate.
Expert Oracle Score stays blocked until a Lift2 oracle path reaches Gate 1, Gate 2 contact, Gate 3 retention, and Gate 4 micro-pull/readback.
```

## Task 6: A3 Single Lift2 Oracle Live Gate

**Files:**
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3_lift2_oracle_single_live_20260706/`
- Create: `docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3a_planner_update_root_cause_review_20260706.json`

- [x] **Step 1: Prepare exactly one selected route live package**

Allowed only after A2a/A2b/A2c pass. The package must include:

```text
run_id
port
task_config
selected_oracle_path
selected_route_id
target waypoint list
assets-root preflight command
submit command
probe/runner command
claim boundary
```

- [x] **Step 2: Run one A3 live only for Gate 1 near reachability**

Pass condition:

```text
PASS_A3_LIFT2_ORACLE_GATE1_NEAR_REACHABILITY_READY_FOR_GATE2_CONTACT
```

Required evidence:

```text
selected route generates action points
replay/readback reaches handle-front near target within tolerance
worker resets cleanly
server shuts down and port is released
```

Stop condition:

```text
BLOCKED_A3_LIFT2_ORACLE_GATE1_NEAR_REACHABILITY
```

Stop if A3 returns `IK_FAIL`, 0 action points, missing readback, or readback outside tolerance. Do not tune offsets
inside A3. Any second live requires a new written root-cause review and a revised A2 manifest.

Actual A3 result:

```text
LIVE_BLOCKED_A3_LIFT2_ORACLE_PLANNER_UPDATE_UNAVAILABLE_STOP_BEFORE_GATE2
```

Evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3_lift2_oracle_single_live_20260706/result_compact.json
```

A3 reset completed and submit exit code was 0, but both waypoints failed before action generation:

```text
failure_reason=planner_update_unavailable
executed_steps=0
lift2_robot_frame_staging_microwave_style arm=default
lift2_handle_front_approach_near_035 arm=default
```

The raw runner classification still says `BLOCKED_GATE1T_NATIVE_PATTERN_ROUTE_NO_NEAR_REACHABILITY` because
`native_action_path_runner` is shared with the older C lane. The normalized A3 status above is the one to use
for PM / acceptance reporting.

- [x] **Step 3: Write A3a planner-update root-cause review before any second live**

Review evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3a_planner_update_root_cause_review_20260706.json
```

Root-cause classification:

```text
REVIEW_A3A_LIFT2_DUAL_ARM_CONTRACT_BLOCKER_REVISE_A2C_A3_BEFORE_SECOND_LIVE
```

Go condition for revised A3:

```text
choose exactly one explicit arm contract: left or right
revise A2c so dual-arm Lift2 routes cannot omit arm / rel_arm
revise A3 route so robot_frame and object_frame waypoints carry the selected arm contract
dry-validate that planner records target left_planner or right_planner
dry-validate exact Lift2/R5a 16D joint_position action rows
```

Stop condition before revised A3:

```text
cannot choose one explicit arm contract
dry validation still resolves to arm=default
dry validation still reports planner_update_unavailable
```

Stop condition after revised A3:

```text
planner_update_unavailable remains -> Lift2 dual-arm planner API / route contract is not closed
IK_FAIL / 0 trajectory points / missing readback / outside tolerance -> selected route is Gate 1 blocked
```

- [x] **Step 4: Close A2c dual-arm guard and A3b right-arm dry package**

A2c addendum evidence:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2c_lift2_dual_arm_route_guard_addendum_20260706.json
```

A3b dry package:

```text
docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3b_lift2_right_arm_dry_contract_20260706/
```

Actual A3b dry classification:

```text
PASS_A3B_LIFT2_RIGHT_ARM_DRY_CONTRACT_READY_FOR_REVISED_A3_SINGLE_LIVE
```

Dry check result:

```text
route_validation_blockers=[]
action_blockers=[]
action_chunk_len=2
action_dim_by_step=[16,16]
required_arm=right
```

Revised A3 live command requirements:

```text
route_id=A3B_LIFT2_SCRIPTED_FRONT_APPROACH_NEAR_RIGHT_ARM
--expected-action-dim 16
--required-arm right
selected_live_route_count=1
no contact / close-hold / micro-pull / score
```

## Task 7: Current E2-to-Gate5 Acceptance Ladder

Current allowed action is no longer E2 live retry. E0 evidence freeze, E1 controller/execution audit, and the
single E2 live reference probe are complete. The current stop line is Lift2 controller/action/readback repair.

```text
E2: completed exactly one non-DryingBox Lift2 controller reference live probe.
    Action sequence was 5 no-op + 5 right-arm small ramp + 60 terminal hold.
    Result: BLOCKED_E2_LIFT2_CONTROLLER_ACTION_READBACK_CONTRACT_NOT_CLOSED.
    Stop DryingBox oracle work until Lift2 controller/action/readback is repaired or explained.

E3: zero-live DryingBox EBench-style expert pose compute.
    Not allowed yet. It requires E2 no-op and terminal hold convergence.
    It must close target pose, arm, frame, 16D action schema, and expected readback schema.

E4: exactly one DryingBox one-segment precontact closed execution.
    No contact, no pulling, no score.
    Pass only if right EE, joint/gripper readback, and contact telemetry are all within tolerance.

E5: exactly one full oracle dry run to precontact.
    No pulling and no score.
    Pass only if multi-segment sequencing stays in closed-schema tolerance with clean contact telemetry.

A3m / Gate 2 / Gate 3 / Gate 4 / Gate 5:
    Allowed only after E5 and a fresh contact-readiness check.
    Gate 5 remains the first place where Expert Oracle Score can be recorded.
```

Product wording:

```text
E2 = 已经校准 Lift2 机器人和尺子；结果显示基础控制/读数合同没闭合
E3 = 暂不允许；要等 Lift2 controller/action/readback 修好
E4 = 最短的一段 DryingBox 预接触执行，才是“新思路有戏”的最早 live 信号
E5 = 完整标准答案链条到接触前稳定
A3m = 到把手前以后是否适合安全接触
Gate 4 = 工程上接近能开门，因为 micro-pull 带动了 door joint
Gate 5 = 评测口径弄好，因为 Expert Oracle Score 被 EBench metric 记录
```

## Verification

Run:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_lift2_contract_fork_review_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/selection_manifest.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1_lift2_live_schema_probe_20260706/result_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1a_assets_root_reset_contract_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1b_lift2_live_schema_probe_corrected_20260706/result_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a1c_lift2_live_schema_probe_logging_closed_20260706/result_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2_lift2_oracle_design_review_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2b_lift2_target_waypoint_static_audit_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2c_lift2_translator_dry_contract_20260706.json >/dev/null
	python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a2c_lift2_dual_arm_route_guard_addendum_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3_lift2_oracle_single_live_20260706/selection_manifest.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3_lift2_oracle_single_live_20260706/result_compact.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3_lift2_oracle_single_live_20260706/summary.json >/dev/null
	python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3a_planner_update_root_cause_review_20260706.json >/dev/null
	python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e1_controller_execution_contract_audit_20260706.json >/dev/null
	python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_e2_lift2_controller_reference_probe_code_checkpoint_20260706.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3b_lift2_right_arm_dry_contract_20260706/route_manifest.json >/dev/null
python -m json.tool docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3b_lift2_right_arm_dry_contract_20260706/result_compact.json >/dev/null
bash docs/labutopia_lab_poc/evidence_manifests/eos2_gate1u_a3b_lift2_right_arm_dry_contract_20260706/dry_check.command.txt >/dev/null
	(cd /root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback && PYTHONPATH=. /usr/bin/python -m pytest tests/labutopia_poc/test_lift2_controller_reference_probe.py tests/labutopia_poc/test_native_action_path_runner.py -q)
git diff --check -- docs/labutopia_lab_poc docs/superpowers/plans/2026-07-06-eos2-gate1u-a-lift2-robot-contract-fork.md
```

Expected: exit `0`.

## Claim Boundary

This plan starts the A/Lift2 lane and now records evidence through E1 audit plus the completed E2 live
reference probe. It does not claim Lift2 controller tracking is usable, DryingBox precontact execution,
contact readiness, door opening, Expert Oracle Score, policy score, official score, Stage 7 aggregate pass,
or full task completion.

The current allowed action is not an E2 rerun and not DryingBox replay. The next work is a bounded
Lift2 controller/action/readback repair or explanation, using the E2 evidence that 70/70 reference steps executed
but no-op and terminal hold did not close under split Lift2 readback. Only after a new written repair plan closes
that contract can E3 static DryingBox compute begin. Only after E4 one-segment DryingBox precontact closed
execution passes can A3m begin; only after A3m can Gate 2/3/4 begin; only after Gate 4 can Gate 5
Expert Oracle Score be recorded.

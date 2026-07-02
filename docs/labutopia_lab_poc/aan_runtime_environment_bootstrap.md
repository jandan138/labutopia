# AAN Runtime Environment Bootstrap Runbook

Date: 2026-07-02

## 目的

这个 runbook 固化 LabUtopia / EBench consumer 运行 AAN package 时的标准启动流程。
它解决的不是“资产本身好不好”，而是先保证 runtime 环境、assets root、wrapper 和证据
归档都稳定，避免把环境漏配误判成资产失败。

一句话给 PM：以后每个 AAN package 进 EBench 前，都先按这套清单验环境；只有环境
preflight 通过后，submit / eval 的结果才用于判断资产接入质量。

## 适用范围

适用：

- LabUtopia / GenManip consumer 加载 ConvertAsset AAN-ready package；
- EBench `level1_open_door` 或 generic AAN smoke；
- Isaac Sim 4.1 runtime；
- USD rigid body 和 articulation asset 的 consumer smoke；
- producer 包不允许被 LabUtopia 本地修改的 no-local-repair 验收。

暂不覆盖：

- official leaderboard score；
- policy 是否真正完成任务；
- `task/evaluator.yaml` 自动变成 runtime semantic metric；
- full visual/material parity；
- deformable、liquid、cloth、particle 等非当前 AAN profile 资产。

## 标准 Conda 环境

当前固定使用已有环境：

```text
/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
```

产品解释：这相当于“指定同一台仪器和同一套工具箱”。以后不要临时换 conda，也不要
在没有记录的情况下用系统 Python 跑 AAN consumer smoke。

## Runtime Bootstrap Contract

所有 AAN consumer run 都必须显式记录这些值：

```bash
export PYENV=/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310
export PY="$PYENV/bin/python"
export LABUTOPIA_REPO=/cpfs/shared/simulation/zhuzihou/dev/LabUtopia
export GENMANIP_WORKTREE=/root/.config/superpowers/worktrees/GenManip/labutopia-stage5-eval-readback
export GENMANIP_CLIENT_SRC=/cpfs/shared/simulation/zhuzihou/dev/genmanip-client/src
export CUROBO_SRC=/cpfs/shared/simulation/mamengchen/curobo-wbc-backup/src
export COMPOSITE_ASSETS_ROOT=/cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets
export LABUTOPIA_POC_ASSETS_OVERLAY_ROOT="$GENMANIP_WORKTREE/saved/assets"
export RUNTIME_USD_NAME=scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene
export TASK_CONFIG_ROUTE=ebench/labutopia_lab_poc/aan11_lift2_candidate/level1_open_door.yml
export TASK_CONFIG_EVIDENCE_COPY="$LABUTOPIA_REPO/docs/labutopia_lab_poc/evidence_manifests/aan_runtime_smoke_labutopia_aan11_lift2_stage4b_assetsroot_20260702_1803/config/level1_open_door.yml"

export ACCEPT_EULA=Y
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONNOUSERSITE=1
export RAY_ADDRESS=local
export RAY_USAGE_STATS_ENABLED=0
export RAY_TMPDIR=/tmp/gm_aan

export CUDA11_LIB=/isaac-sim/exts/omni.isaac.ml_archive/pip_prebundle/nvidia/cuda_runtime/lib
export PATH="$PYENV/bin:$PATH"
export PYTHONPATH="$CUROBO_SRC:$GENMANIP_CLIENT_SRC:$GENMANIP_WORKTREE:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="$CUDA11_LIB:$PYENV/lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin:$PYENV/lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps:$PYENV/lib/python3.10/site-packages/torch/lib:${LD_LIBRARY_PATH:-}"
```

其中最容易漏的是两个变量：

| 变量 | 为什么关键 | 漏了会怎样 |
|---|---|---|
| `CUROBO_SRC` | Ray worker 需要从这里 import cuRobo 相关模块。 | `ModuleNotFoundError: No module named curobo`，任务还没开始就失败。 |
| `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT` | 必须显式指向正确的 `saved/assets`，且 realpath 必须等于 composite assets root。 | 缺失或指向旧 overlay root 时，AAN wrapper 可能 composition 为空。 |

## Assets Root Invariant

AAN runtime wrapper 不直接去 `/tmp` 找包，而是通过 GenManip worktree 里的
`saved/assets` 进入 composite assets root：

```text
$GENMANIP_WORKTREE/saved/assets
  -> /cpfs/shared/simulation/zhuzihou/dev/_datasets/EBench-Assets-Composite/labutopia_level1_poc_lift2_codex/assets
```

AAN-11 DryingBox 的 runtime wrapper 应该出现在：

```text
$GENMANIP_WORKTREE/saved/assets/scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene.usda
```

产品解释：`saved/assets` 是 EBench consumer 真正会看的货架。AAN package 可以来自
ConvertAsset，但要先被挂到这层货架上，runtime 才能稳定找到。

## 标准运行顺序

### 1. Preflight

运行前先检查环境，不启动 Isaac：

```bash
test -x "$PY"
test -d "$CUROBO_SRC"
test -d "$GENMANIP_CLIENT_SRC"
test -d "$GENMANIP_WORKTREE"
test -L "$GENMANIP_WORKTREE/saved/assets"
test "$(readlink -f "$GENMANIP_WORKTREE/saved/assets")" = "$COMPOSITE_ASSETS_ROOT"
test -f "$GENMANIP_WORKTREE/saved/assets/${RUNTIME_USD_NAME}.usda"
test -f "$TASK_CONFIG_EVIDENCE_COPY"
"$PY" - <<'PY'
import curobo
print("curobo_import=PASS")
PY
"$PY" - <<'PY'
import os, pathlib, yaml
p = pathlib.Path(os.environ["TASK_CONFIG_EVIDENCE_COPY"])
doc = yaml.safe_load(p.read_text())
cfg = doc["evaluation_configs"][0]
assert cfg["usd_name"] == os.environ["RUNTIME_USD_NAME"]
assert cfg["robots"][0]["type"] == "manip/lift2/R5a"
assert cfg["labutopia_lift2_contract"]["action_contract"]["action_shape"] == [16]
print("task_config_contract=PASS")
PY
```

Preflight 必须记录：

```text
python_path
python_version
CUROBO_SRC
GENMANIP_CLIENT_SRC
GENMANIP_WORKTREE
LABUTOPIA_POC_ASSETS_OVERLAY_ROOT
saved_assets_realpath
runtime_wrapper_path
runtime_usd_name
task_config_route
task_config_path
package_digest_sha256
action_dialect
```

Preflight 还必须确认：

- `runtime_usd_name` 是 AAN wrapper，例如
  `scene_usds/labutopia/aan/dryingbox_01_overlay_aan11_scene`，不是旧
  `scene_usds/labutopia/level1_poc/lab_001/scene`；
- wrapper 的 USD reference 指向 mounted AAN package 的 `asset.usd`，不是注释字符串或旧路径；
- lane-local / AAN-specific manifest 是 runtime authority，不回退到 legacy overlay；
- package digest、asset USD digest、mounted digest 与 intake / adapter evidence 一致；
- run id 必须 fresh，并且在 submit、eval、artifact path、`result_info_path` 和 manifest 中一致。

### 2. Start Server

用同一个 shell 继承上面的 export，再启动 `ray_eval_server.py`：

```bash
cd "$GENMANIP_WORKTREE"
"$PYENV/bin/python" ray_eval_server.py \
  --host 127.0.0.1 \
  --port 18189 \
  --run_id "$RUN_ID" \
  --no_save_process \
  --episode_recorder_save_every 0 \
  --reset_timeout 1200 \
  --step_timeout 1200 \
  --load_config_timeout 300
```

### 3. Submit

```bash
gmp submit "$TASK_CONFIG_ROUTE" \
  --run_id "$RUN_ID" \
  --host 127.0.0.1 \
  --port 18189
```

### 4. Eval

```bash
"$PY" -m genmanip_client.cli eval \
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

### 5. Evidence Capture

每次 run 必须归档：

```text
gmp_submit.txt
gmp_submit.stderr.txt
gmp_submit.exitcode
gmp_eval_r5a_lift2.txt
gmp_eval_r5a_lift2.stderr.txt
gmp_eval_r5a_lift2.exitcode
server.stdout.txt
server.stderr.txt
result/result_info.json
result/result.json
config/level1_open_door.yml
config/aan11_lift2_candidate.json
```

最终 manifest 必须包含：

```text
runtime_environment_contract
bootstrap_preflight
diagnostic_attempts_before_final
consumer_live_smoke
consumer_log_counts
allowed_claims
forbidden_claims
```

## Failure Classification

| 现象 | 归类 | 怎么处理 | PM 说法 |
|---|---|---|---|
| `ModuleNotFoundError: No module named curobo` | runtime bootstrap 失败 | 检查 `CUROBO_SRC` 是否进入 Ray worker 的 `PYTHONPATH`。 | 环境没配全，不能评价资产。 |
| `load_world_xform_prim ... GetAllChildren()[0]` 或 wrapper composition 为空 | assets root / mount 失败 | 检查 `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT` 和 `saved/assets` symlink。 | 货架指错了，不是资产本体失败。 |
| `ninja` 缺失或 `libcudart.so.11.0` 找不到 | conda / library path 失败 | 检查 `PATH` 和 `LD_LIBRARY_PATH`。 | 工具箱没拿全，不能评价资产。 |
| wrapper / config / lane manifest 不一致，或 `legacy_overlay_used=true` | consumer adapter / mount 失败 | 检查 AAN wrapper、`usd_name`、package mount、digest 和 no-local-repair。 | 接入口接错了，不能评价资产。 |
| submit / eval exit `0`，reset 和 1000 steps 有证据，但 `score=0.0` | smoke PASS，policy 未完成任务 | 保留为 policy / semantic follow-up。 | 接入链路跑通，不等于模型会开门。 |
| `task/evaluator.yaml` 只作为 package metadata 存在 | semantic evaluator 未实现 | 单独推进 runtime dispatch，不能并入 smoke PASS。 | 已有评价说明书，不等于已经执行语义评价。 |
| 有 `mdlc_compiler_error_count` 或 material binding warning | material parity follow-up | 不阻塞 consumer smoke；需要单独 material parity closure。 | 能跑不等于外观逐项一致。 |

## Acceptance Gates

### Preflight PASS

全部满足才允许启动 live smoke：

- conda Python 存在；
- `curobo` 能 import；
- `GENMANIP_CLIENT_SRC` 存在；
- `saved/assets` 是 symlink；
- `saved/assets` realpath 等于 composite assets root；
- AAN runtime wrapper 文件存在；
- task config evidence copy 存在，且 `usd_name` 指向 AAN wrapper；
- Lift2/R5a action contract 是 16D，不使用默认 Franka/Panda 9D action；
- package digest 与 intake manifest 一致；
- no-local-repair before / after digest 不变。

### Runtime Smoke PASS

全部满足才允许说 consumer smoke pass：

- `submit_exit_code=0`；
- `eval_exit_code=0`；
- server log 里能看到 reset；
- server / eval log 里能看到 step 运行；
- `result_info.json` 存在；
- `run_id` 在 submit、eval、artifact path、manifest 中一致；
- evidence 目录包含 stdout / stderr / exit code；
- consumer log counts 记录 `mdlc_compiler_error_count`、
  `relationship_out_of_scope_count`、traceback / HTTP 500 / solid red text 等诊断字段；
- consumer smoke `PASS` 和 fixed-front visual parity `WARN` 分字段记录，不能合并成
  full visual/material parity `PASS`。

### Claim Boundary PASS

汇报前必须写清楚：

```text
allowed_claims:
  - AAN package entered LabUtopia / EBench consumer.
  - Local live smoke passed.
  - No-local-repair boundary was preserved.

forbidden_claims:
  - official leaderboard score is complete.
  - policy solved the task.
  - full visual/material parity is proven.
  - arbitrary USD / MJCF / deformable / liquid assets are ready.
```

## AAN-11 已验证基线

当前 AAN-11 DryingBox final consumer run：

```text
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

这次 final run 前有两次 diagnostic run：

1. `labutopia_aan11_lift2_stage4b_20260702_1755`：缺 `CUROBO_SRC`，Ray worker 报
   `ModuleNotFoundError: No module named curobo`。
2. `labutopia_aan11_lift2_stage4b_envfix_20260702_1759`：缺
   `LABUTOPIA_POC_ASSETS_OVERLAY_ROOT`，consumer 回落旧 overlay root，wrapper
   composition 为空。

这两次都不是资产失败；它们是本 runbook 要消灭的环境启动问题。

## 下一步工程落点

LabUtopia 侧负责保留规范、证据和 claim boundary。实际自动化脚本建议落在 GenManip /
EBench consumer repo：

```text
standalone_tools/labutopia_poc/aan_runtime_bootstrap_preflight.py
standalone_tools/labutopia_poc/aan_live_smoke_runner.py
```

建议脚本行为：

- 读取 AAN package manifest 和 candidate task config；
- 自动导出 runtime bootstrap contract；
- 先跑 preflight，失败时不启动 Isaac；
- 成功后启动 server、submit、eval；
- 自动生成 evidence manifest；
- 按 Failure Classification 给出 `PASS/FAIL/BLOCKED/WARN`。

这样做的好处：以后换成 `MuffleFurnace`、`Beaker_01` 或新的 LabUtopia asset 时，不再靠
人工记环境变量，而是靠同一套 preflight + runner 先把环境和挂载检查干净。

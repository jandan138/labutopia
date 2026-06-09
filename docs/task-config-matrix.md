# Task Config Matrix

本仓库当前有 29 个主 config，注册了 21 个 controller/expert 类型。本表记录 2026-06-09 全量视频批跑的最终状态。

汇总文件：

```text
artifacts/videos/expert_trajectories/20260609_002039_final/final_summary.csv
```

## Controller Registry

注册位置：`factories/controller_factory.py`

已注册 controller/expert 类型：

```text
pickpour, open, close, openclose, pick, pour, place, pickplace,
placepress, press, shake, stir, stirglassrod, shakebeaker,
cleanbeaker, cleanbeaker7policy, device_operate, OpenTransportPour,
LiquidMixing, navigation, mobile_pick
```

## Config 状态矩阵

| Config | Task | Controller | Status | Frames | Resolution | QA |
| --- | --- | --- | --- | ---: | --- | --- |
| `level1_close_door` | `openclose` | `close` | `ok` | 504 | 768x256 | WARN black/occlusion |
| `level1_close_drawer` | `openclose` | `close` | `ok` | 362 | 768x256 | WARN black/occlusion |
| `level1_open_door` | `openclose` | `open` | `ok` | 907 | 768x256 | WARN black/occlusion |
| `level1_open_drawer` | `openclose` | `open` | `ok` | 916 | 768x256 | WARN black/occlusion |
| `level1_pick` | `pick` | `pick` | `ok` | 585 | 768x256 | PASS |
| `level1_place` | `place` | `place` | `ok` | 831 | 768x256 | PASS |
| `level1_pour` | `pickpour` | `pour` | `ok` | 1044 | 768x256 | WARN black/occlusion |
| `level1_press` | `press` | `press` | `ok` | 412 | 768x256 | PASS |
| `level1_shake` | `shake` | `shake` | `ok` | 1146 | 768x256 | PASS |
| `level1_stir` | `stir` | `stir` | `ok` | 1808 | 768x256 | PASS |
| `level2_HeatLiquid` | `placepress` | `placepress` | `ok` | 1011 | 768x256 | PASS |
| `level2_PourLiquid` | `pickpour` | `pickpour` | `ok` | 994 | 768x256 | WARN black/occlusion |
| `level2_ShakeBeaker` | `shake` | `shakebeaker` | `ok` | 1147 | 512x256 | WARN low-res |
| `level2_StirGlassrod` | `stir` | `stirglassrod` | `ok` | 1893 | 512x256 | WARN low-res |
| `level2_TransportBeaker` | `place` | `pickplace` | `ok` | 920 | 768x256 | PASS |
| `level2_openclose` | `openclose` | `openclose` | `ok` | 1283 | 768x256 | WARN black/occlusion |
| `level3_HeatLiquid` | `placepress` | `placepress` | `ok` | 1188 | 768x256 | PASS |
| `level3_PourLiquid` | `pickpour` | `pickpour` | `ok` | 956 | 768x256 | WARN black/occlusion |
| `level3_TransportBeaker` | `pickplace` | `pickplace` | `ok` | 958 | 768x256 | PASS |
| `level3_open` | `openclose` | `open` | `ok` | 946 | 768x256 | WARN black/occlusion |
| `level3_pick` | `pick` | `pick` | `ok` | 614 | 768x256 | PASS |
| `level3_press` | `press` | `press` | `ok` | 412 | 768x256 | PASS |
| `level4_CleanBeaker` | `cleanbeaker` | `cleanbeaker` | `ok` | 2556 | 768x256 | PASS |
| `level4_CleanBeaker7Policy` | `cleanbeaker` | `cleanbeaker7policy` | `video_only` | 2001 | 512x256 | VIDEO_ONLY |
| `level4_DeviceOperation` | `device_operate` | `device_operate` | `ok` | 3221 | 768x256 | WARN black/occlusion |
| `level4_LiquidMixing` | `LiquidMixing` | `LiquidMixing` | `ok` | 4168 | 1920x1080 | PASS |
| `level4_OpenTransportPour` | `OpenTransportPour` | `OpenTransportPour` | `ok` | 2802 | 768x256 | WARN black/occlusion |
| `level5_Mobile_manipulation` | `mobile_pick` | `mobile_pick` | `ok` | 2414 | 768x256 | PASS |
| `level5_Navigation` | `navigation` | `navigation` | `ok` | 676 | 768x256 | PASS |

## 非成功项

`level4_CleanBeaker7Policy` 的视频存在且可读，但不能算成功 expert trajectory。直接重跑日志显示 controller 调用不匹配：

```text
PourController.forward() got an unexpected keyword argument 'target_name'
```

同时该 controller 后续还存在 task state 字段命名不一致风险，例如 task 返回 `target_name`，controller 读取 `target_beaker`。修复后需要单独重跑该 config，并更新本表。


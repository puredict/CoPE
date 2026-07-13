# Duplication Map

本文件列出静态审计中发现的重复 helper、rollout 逻辑和 shell 矩阵重复。目标是为未来统一 experiment core 提供边界建议；本次审计未写任何代码。

## 1. 完全重复或近似重复的 Python helper

AST 静态分析命令：使用标准库 `ast` 解析所有 `*.py`，按函数源码去空白后 hash 分组。未 import 项目模块。

| Helper / 逻辑 | 重复位置 | 重复类型 | 行为漂移风险 |
| --- | --- | --- | --- |
| `sim_from_env` | `baseline_reset_rollback_eval.py:36`; `baseline_stage_backtrack_eval.py:36`; `libero_disturbance_eval.py:62-63`; `second_necessity_intervention.py:37` | 完全重复 | 低，但所有 sim access 应统一，方便 mock 和 dashboard worker |
| `make_cfg` | `baseline_reset_rollback_eval.py:33-34`; `baseline_stage_backtrack_eval.py:33-34`; `second_necessity_intervention.py:33-34`; 主脚本 `libero_disturbance_eval.py:51-59` 为扩展版 | 重复/变体 | unnorm key、checkpoint、crop 配置可能漂移 |
| tokenization: `toks` / `tokenize` | `baseline_reset_rollback_eval.py:38`; `baseline_stage_backtrack_eval.py:38`; `second_necessity_intervention.py:39`; `libero_disturbance_eval.py:92-93` | 重复/变体 | target selection 与 object phrase 解析可能不一致 |
| `choose_target_joint` | `baseline_reset_rollback_eval.py:40-49`; `baseline_stage_backtrack_eval.py:40-49`; `second_necessity_intervention.py:41-51`; `libero_disturbance_eval.py:96-114` | 重复/变体 | 主脚本记录 `qpos_addr`，baseline 变体不记录；tie/zero-score 行为分散 |
| `move_free_joint_xy` | `baseline_reset_rollback_eval.py:51-56`; `baseline_stage_backtrack_eval.py:61-66`; `second_necessity_intervention.py:59-64`; `libero_disturbance_eval.py:74-89` | 重复/变体 | 是否记录 `qpos_addr`、body pose、refresh obs、event id 会漂移 |
| `save_video` | `baseline_reset_rollback_eval.py:58-62`; `baseline_stage_backtrack_eval.py:68-72`; `second_necessity_intervention.py:66-70`; `libero_disturbance_eval.py:117-122` | 重复/变体 | fps、codec、empty frames、path handling 可能不一致 |
| `policy_step` | `baseline_reset_rollback_eval.py:64-70`; `baseline_stage_backtrack_eval.py:74-80`; `second_necessity_intervention.py:108-113` inline；`libero_disturbance_eval.py:166-184` inline | 重复/变体 | image/state extraction、raw/env action、gripper inversion、prompt id logging 容易漂移 |
| object phrase cleanup | `baseline_stage_backtrack_eval.py:51-53`; `second_necessity_intervention.py:53-57`; `verifier_vs_recovery_state_eval.py:23-24` | 近似重复 | prompt 文案和 affected object label 不一致 |
| output JSONL append | `libero_disturbance_eval.py:258-259`; `baseline_reset_rollback_eval.py:132`; `baseline_stage_backtrack_eval.py:126`; `second_necessity_intervention.py:133` | 近似重复 | summary schema 不统一，异常/partial result 无统一处理 |

## 2. Rollout skeleton 重复

四个主要评测脚本都有相同骨架：

1. parse args。
2. set seed。
3. construct cfg/model/processor。
4. create LIBERO benchmark suite。
5. create env and set initial state。
6. dummy wait。
7. run policy loop。
8. optionally mutate qpos。
9. save video。
10. append JSONL and summary。

重复位置：

- `libero_disturbance_eval.py:125-214`：clean/disturbed 主 rollout。
- `baseline_reset_rollback_eval.py:72-118`：reactive/full reset/oracle rollback。
- `baseline_stage_backtrack_eval.py:82-112`：reactive/verifier/structured/stage prompt。
- `second_necessity_intervention.py:78-119`：reactive/verifier/structured reprompt。

主要漂移：

- `libero_disturbance_eval.py` 支持 `trial_id`，baseline/recovery 脚本固定 `init_states[0]`。
- 主脚本输出字段使用 `condition`，baseline/recovery 脚本使用 `mode`。
- 主脚本 `move_free_joint_xy` 记录 `qpos_addr`，其他脚本不记录。
- full reset/oracle rollback 有 cost/event 语义，但没有统一写入 action trace。
- prompt recovery 脚本记录 `task_prompt`，主脚本不记录 prompt id。
- success、timeout、exception schema 都未统一。

## 3. Shell wrapper 重复

所有 `run_*.sh` 基本重复以下结构：

- `cd /home/lijingsu/vla`
- `source .venv/bin/activate`
- export `PYTHONPATH`
- export `MUJOCO_GL=osmesa`
- export `PYOPENGL_PLATFORM=osmesa`
- export `HF_HOME`
- export `CUDA_VISIBLE_DEVICES=<hardcoded>`
- 调用 `python /home/lijingsu/vla/libero_disturbance_eval.py ...`

重复位置：

- `run_baseline_base_openvla.sh:3-22`
- `run_expanded_spatial_3trials.sh:3-21`
- `run_full_spatial_disturbance.sh:3-21`
- `run_timing_step30.sh:3-21`
- `run_timing_step60.sh:3-21`
- `run_timing_step120.sh:3-21`
- `run_magnitude_small.sh:3-21`
- `run_magnitude_large.sh:3-21`

主要漂移：

- GPU id 不同且硬编码。
- `run_timing_step60.sh` 和 `run_timing_step120.sh` 都使用 GPU 3。
- base OpenVLA 使用 `--unnorm-key bridge_orig`，Spatial checkpoint 脚本不传该 override。
- `wait_and_collect_disturbance_results.sh` 的 root 列表没有随着 run scripts 更新，遗漏 `full_spatial` 和 `timing_step120`。

## 4. 建议的统一 experiment core 边界

建议先做 behavior-preserving 抽取，不同时改变算法语义。模块边界如下：

| 模块 | 职责 | 从哪些代码抽取 | 第一阶段注意事项 |
| --- | --- | --- | --- |
| `config / manifest` | CLI args、checkpoint、task suite、seed、paths、GPU metadata、source hash | 所有 `parse_args` 和 shell scripts | 不改变默认值；完整写出 run manifest |
| `model_factory` | `get_model`、processor、norm stats、unnorm key fallback | `libero_disturbance_eval.py:225-231`; baseline main 函数 | 禁止在静态测试中 import/load；提供 mock |
| `env_factory` | benchmark suite、env creation、init state selection | 所有 rollout 初始化 | 增加 `trial_id` 和 init hash |
| `sim_access` | `sim_from_env`、sim state hash、free joint read/write | 多个 `sim_from_env` / `move_free_joint_xy` | 保持 qpos 修改行为不变，新增记录字段 |
| `target_selection` | candidate enumeration、score、manifest override | `choose_target_joint` variants | 正式实验优先 manifest；auto 输出 candidate table |
| `observation_refresh` | qpos mutation 后获取 fresh obs 的统一策略 | F-01 涉及所有脚本 | 先用 mock/short env 验证成本和视觉刷新 |
| `policy_runner` | image/state extraction、action inference、gripper normalize/invert | `policy_step` variants | 保持 raw/env action 字段一致 |
| `mode_strategies` | clean、reactive、verifier stop、prompt recovery、reset、rollback | 四个 rollout 分支 | 策略只返回 events/actions，不直接写文件 |
| `episode_logger` | JSONL、events、actions、status、exception、cost accounting | 所有 JSON writes | 统一 schema，兼容旧 records 迁移 |
| `video_writer` | raw/annotated frame、fps、frame id mapping | `save_video` variants | fps 是显示参数；写入 frame map |
| `summaries` | per task/mode/condition aggregation、CI、missing run detection | `summarize_disturbance_results.py`; `wait_and_collect...` | 支持 condition 与 mode schemas |
| `smoke_tools` | env/model health checks，不进入正式 metrics | smoke/probe scripts | 输出 `purpose=smoke` 和 `not_for_paper_metric=true` |

## 5. 抽取顺序建议

1. 只抽取纯函数/低风险 helper：`sim_from_env`、tokenize、video writer、JSON serializer。
2. 增加 mock tests 固定当前行为，包括 target selection tie 行为和 action schema。
3. 抽取 `move_free_joint_xy`，先保持 qpos 改法不变，只统一记录字段。
4. 新增 observation refresh 策略，并用独立短实验验证。
5. 抽取 policy step，统一 raw/env action 和 prompt id。
6. 抽取 mode strategy，但保持每个 mode 的现有语义和名称。
7. 最后重写 shell/run matrix 和 summarizer。

## 6. 回归保护建议

抽取公共核心前，应先保存以下 golden artifacts 或 mock expectations：

- 给定 fake sim/model 的 target candidate 排序结果。
- `move_free_joint_xy` 对 qpos 的 before/after/delta 记录。
- policy action trace 字段名和 dtype/list 格式。
- 每个 mode 的 event sequence：
  - clean: wait -> policy steps。
  - reactive: wait -> policy steps -> disturbance -> policy steps。
  - verifier_stop: wait -> policy steps -> disturbance -> stop。
  - structured prompt: disturbance -> prompt switch -> policy step。
  - full reset: disturbance -> reset -> wait -> policy restart。
  - oracle rollback: save state -> disturbance -> restore -> dummy refresh。
- JSONL backward compatibility reader。

## 7. 不建议现在合并的重构

- 不要在同一 PR 中同时改变 observation refresh、success semantics、target selection 和 mode naming；会无法归因结果变化。
- 不要把 `full_reset_replan` 包装成普通 recovery strategy；应在类型系统或 manifest 中标为 `restart_baseline`。
- 不要让 dashboard 直接复用当前脚本的 long-running loop；应先有可 step/pause 的 core。
- 不要用 shell glob 或 latest-dir heuristic 生成正式论文表；应使用 manifest-driven run registry。

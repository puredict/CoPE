# Stage 2.1 Three-State Pilot Report

日期：2026-07-13  
仓库：`/home/lijingsu/vla`  
分支：`stage-2.1-three-state-pilot`  
main 起始 commit：`dfd0151c572785acd42cae562069bb12e054e9a9`  
确认标签：`stage-2-canary-pass`，指向同一 merge commit `dfd0151c572785acd42cae562069bb12e054e9a9`

本报告只记录三初始状态小样本 pilot 的链路和现象。不得根据本阶段 3 个 initial states 声称稳定泛化、显著提升或正式成功率。

## Preflight

开始前在正式仓库执行了指定检查：

- `git status --short`：空
- `git branch --show-current`：`main`
- `git rev-parse HEAD`：`dfd0151c572785acd42cae562069bb12e054e9a9`
- `git show --no-patch stage-2-canary-pass`：标签存在，标签说明为 `Single paired LIBERO canary completed and validated`
- `nvidia-smi`：8 张 RTX 3090，均为 12 MiB Xorg 图形占用，无 compute app
- `ps aux | grep -E "openvla|libero|dashboard" | grep -v grep || true`：无输出
- `.git` lock 文件：无

随后创建分支：

```bash
git switch -c stage-2.1-three-state-pilot
```

开跑前再次检查：

- 当前分支：`stage-2.1-three-state-pilot`
- `.git` lock 文件：无
- GPU compute app：无输出
- OpenVLA/LIBERO/Dashboard 进程：无输出

## Instrumentation

本阶段在 `libero_disturbance_eval.py` 上做了审计日志增强：

- 新增 `--seed-rule`，本次固定为 `base_plus_initial_state`
- 每个 episode 单独保存：
  - `run_config.json`
  - `events.jsonl`
  - `episode_summary.json`
  - `actions.jsonl`
  - `raw.mp4`
- 每个 episode 记录 artifact paths、seed rule、manual intervention、disabled recovery modes、target qpos、policy start qpos、fresh observation 标记和视频帧 index

该改动只增强日志，不启用 structured recovery、stage backtrack、verifier stop、full reset、oracle rollback、其他 task、其他 checkpoint 或大规模 trial。

## Commands

编译检查：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m py_compile libero_disturbance_eval.py
```

结果：退出码 0。

测试：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m pytest -q
```

结果：`30 passed in 3.37s`。

Pilot 命令：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python libero_disturbance_eval.py \
  --checkpoint /home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial \
  --task-suite libero_spatial \
  --task-id 0 \
  --trials 3 \
  --seed 7 \
  --seed-rule base_plus_initial_state \
  --target-joint akita_black_bowl_1_joint0 \
  --disturbance-step 70 \
  --dx 0.10 \
  --dy 0.05 \
  --num-steps-wait 10 \
  --max-steps 220 \
  --out-dir /home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot
```

结果：退出码 0，正好运行 6 个 episode。

Validation 命令：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python \
  audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/validate_stage2_1.py \
  /home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36
```

结果：退出码 0，`passed: true`，`failures: []`。

## Fixed Configuration

固定条件：

- suite：`libero_spatial`
- task：`0`
- checkpoint：`/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial`
- target joint：`akita_black_bowl_1_joint0`
- disturbance step：`70`
- disturbance delta：`dx=0.10`，`dy=0.05`
- warmup：`10` env steps
- policy budget：`220` policy steps
- seed 规则：`actual_seed = 7 + initial_state_id`

因此：

| Initial state | Clean seed | Reactive seed |
| --- | ---: | ---: |
| 0 | 7 | 7 |
| 1 | 8 | 8 |
| 2 | 9 | 9 |

每个 clean/reactive pair 使用相同 task、initial state、seed、checkpoint、target joint、warmup 和 policy budget。

## Episode Results

这些是小样本链路观察，不是正式统计。

| Initial state | Mode | Seed | Final status | Success | Timeout | Policy steps | Video frames |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: |
| 0 | clean | 7 | success | true | false | 75 | 75 |
| 0 | reactive_disturbed | 7 | timeout | false | true | 220 | 220 |
| 1 | clean | 8 | success | true | false | 84 | 84 |
| 1 | reactive_disturbed | 8 | timeout | false | true | 220 | 220 |
| 2 | clean | 9 | success | true | false | 79 | 79 |
| 2 | reactive_disturbed | 9 | timeout | false | true | 220 | 220 |

Clean 在这三个固定 initial states 下均可完成任务。Reactive disturbed 在这三个固定 initial states 下均未恢复到 success，并按预算 timeout。该现象只用于判断下一步实验链路，不构成稳定性、鲁棒性或成功率声明。

## Disturbance Coordinates

目标物体位置一致性使用 target free-joint qpos 检查。每对 clean/reactive 的 `initial_target_qpos` 和 `policy_start_target_qpos` 完全一致；下表为 disturbed episode 的扰动前后 qpos 坐标前三维。

| Initial state | Seed | Before xyz | After xyz | Actual delta |
| ---: | ---: | --- | --- | --- |
| 0 | 7 | `[0.07051401944683737, 0.1957706591982865, 0.9500326696891234]` | `[0.17051401944683736, 0.2457706591982865, 0.9500326696891234]` | `[0.09999999999999999, 0.04999999999999999, 0.0]` |
| 1 | 8 | `[0.005352930074093203, 0.1900594588856477, 0.9953670327421614]` | `[0.10535293007409322, 0.24005945888564773, 0.9953670327421614]` | `[0.1, 0.05000000000000002, 0.0]` |
| 2 | 9 | `[0.038353983081806195, 0.21616962903905554, 0.9782198008992791]` | `[0.1383539830818062, 0.26616962903905556, 0.9782198008992791]` | `[0.09999999999999999, 0.05000000000000002, 0.0]` |

## Fresh Observation Evidence

所有 disturbed episode 均在 policy step `70` 应用扰动，随后立即刷新 observation：

- refresh method：`env.env._get_observations(force_update=True)`
- operations：`sim.forward`、`env.check_success`、`env._post_process`、`env._update_observables`、`env.env._post_process`、`env.env._update_observables`
- `consumed_noop_env_step=false`
- `actions.jsonl` 中 policy step `70` 的 `uses_post_disturbance_fresh_observation=true`
- `events.jsonl` 中存在 `disturbance_applied` event，且下一条对应 policy step 继续使用同一 action/video index 序列

## Output Paths

Run directory：

```text
/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36
```

Top-level outputs：

- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/summary.json`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/episodes.jsonl`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/stage2_1_validation.json`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/validate_stage2_1.py`

Episode directories, each containing `run_config.json`, `events.jsonl`, `episode_summary.json`, `actions.jsonl`, and `raw.mp4`：

- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/task0_initial_state0_seed7_clean`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/task0_initial_state0_seed7_reactive_disturbed`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/task0_initial_state1_seed8_clean`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/task0_initial_state1_seed8_reactive_disturbed`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/task0_initial_state2_seed9_clean`
- `/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36/task0_initial_state2_seed9_reactive_disturbed`

Validation confirmed every required artifact exists, is non-empty, and belongs to this run directory. The timestamped directory was new, so no old result was overwritten.

## Required Pair Checks

Validation result：`passed=true`，`records=6`，`failures=[]`。

| Check | Result |
| --- | --- |
| task、initial state、seed、checkpoint 一致 | Passed for all three pairs |
| 初始机器人状态和目标物体位置一致 | Passed via `initial_robot_state` and target free-joint qpos |
| target joint 明确 | Passed: `akita_black_bowl_1_joint0` |
| 实际扰动 delta 正确 | Passed, actual delta approximately `[0.10, 0.05, 0.0]` |
| 扰动后下一次推理使用 fresh observation | Passed at policy step `70` for all disturbed episodes |
| policy budget 一致 | Passed: `220` policy steps, warmup `10` |
| timeout 不记录成 success | Passed: all disturbed timeouts have `success=false` |
| 没有人工干预 | Passed: `manual_intervention=false` and Dashboard never started |
| 视频、动作和事件 step 对齐 | Passed: frame counts equal action counts for all videos |
| 输出没有覆盖旧结果 | Passed: unique timestamped run directory and unique episode dirs |

## GPU And Process State

Before：

- `nvidia-smi`：8 张 RTX 3090，均无 compute app；只有 `/usr/lib/xorg/Xorg` 图形占用
- OpenVLA/LIBERO/Dashboard process check：无输出

After：

- `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`：无输出
- `nvidia-smi`：8 张 RTX 3090，均为 P8 idle，12 MiB Xorg 图形占用，无 compute app
- OpenVLA/LIBERO/Dashboard process check：无输出

未发现实验后遗留 OpenVLA、LIBERO 或 Dashboard 进程。

## Findings

- Clean 在 initial state 0、1、2 均完成，policy steps 分别为 75、84、79。这里只说明这三条 pilot episode 可执行。
- Reactive disturbed 在 initial state 0、1、2 均 timeout，policy steps 均为 220，未被误记为 success。
- 扰动合法：三条 disturbed 的实际 delta 均为 `[0.10, 0.05, 0.0]` 浮点误差范围内。
- 批量日志和视频稳定：6 个 episode 均保存 required artifacts，视频帧数与 action 数一致。
- 未发现 blocking 工程问题。
- 非阻塞观察：target body pose 辅助字段未解析到 body name，因此本报告和 validator 使用 target free-joint qpos 作为目标物体位置证据。后续若需要 body_xpos 级报告，可把 joint-to-body 解析改为读取 MuJoCo `jnt_bodyid`。
- 非阻塞观察：运行中出现 TensorFlow/Gym/robosuite 警告，与 Canary 类似；未阻断执行或验证。

## Expansion Recommendation

允许扩大到更多 task 的小批量 clean/reactive_disturbed pilot，但应继续保持：

- 固定 checkpoint、warmup、policy budget、seed rule
- 每个 pair 使用相同 initial state 和 seed
- 每个 run 先做 GPU/进程 preflight，结束后做 postflight
- 继续使用本阶段的 episode-level artifact 和 validator

不建议直接扩大到 recovery 模式的大规模实验。本阶段没有运行 structured recovery、stage backtrack、verifier stop、full reset 或 oracle rollback，因此 recovery 模式应先各自经过单独小 canary，再决定是否扩大。

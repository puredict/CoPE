# Stage 2 Canary Report

日期：2026-07-13  
仓库：`/home/lijingsu/vla`  
分支：`stage-2-canary`  
可信起点：`main` HEAD `a0b13f296cd5e00edbf4d1a0e7055c39dab4556c`  
阶段 1.6 标签：`stage-1.6-restored`

本报告只判断单任务严格配对 Canary 的实验链路是否可信。它不声称性能提升、鲁棒性或泛化能力。

## Scope

本阶段只运行一组配对 episode：

- suite：`libero_spatial`
- task：`0`
- initial state：`0`
- seed：`7`
- checkpoint：`/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial`
- conditions：`clean` 一次，`reactive_disturbed` 一次
- explicit target joint：`akita_black_bowl_1_joint0`
- disturbance step：`70`
- disturbance delta：`dx=0.10`，`dy=0.05`
- warmup：`10` env steps
- policy budget：`220` policy steps

未运行其他恢复模式、多个任务、多个 seed、Dashboard 人工操作或大规模实验。

## Preflight

开始前检查：

- `git status --short`：空
- `git branch --show-current`：`main`
- `git rev-parse HEAD`：`a0b13f296cd5e00edbf4d1a0e7055c39dab4556c`
- `.git` lock 文件：无
- `pgrep -af openvla`：无输出
- `pgrep -af libero`：无输出
- `pgrep -af dashboard`：无输出
- `pgrep -af pytest`：无输出
- `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`：无输出
- `pgrep -af python`：仅系统服务 `networkd-dispatcher` 和 `unattended-upgrade-shutdown`

随后创建分支：

```bash
git switch -c stage-2-canary
```

## Instrumentation

为让 Canary 输出可以直接验证配对和状态一致性，本分支对 `libero_disturbance_eval.py` 增加了仅记录元数据的字段：

- `pair_key`
- `mode`
- `manual_intervention`
- `checkpoint`
- `seed`
- `initial_state_id`
- `initial_robot_state`
- `initial_target_qpos`
- `policy_start_robot_state`
- `policy_start_target_qpos`
- `disturbance.delta_xyz_actual`
- action-level `video_frame_index`
- action-level `uses_post_disturbance_fresh_observation`

该改动不增加模式、任务、seed 或实验规模；只增强本次 Canary 的可审计性。

## Commands

元数据改动后先运行：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m py_compile libero_disturbance_eval.py
```

结果：退出码 0。

随后运行：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m pytest -q
```

结果：退出码 0，`30 passed in 3.33s`。

Canary 命令：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python libero_disturbance_eval.py \
  --checkpoint /home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial \
  --task-suite libero_spatial \
  --task-id 0 \
  --trials 1 \
  --seed 7 \
  --target-joint akita_black_bowl_1_joint0 \
  --disturbance-step 70 \
  --dx 0.10 \
  --dy 0.05 \
  --num-steps-wait 10 \
  --max-steps 220 \
  --out-dir /home/lijingsu/vla/audit_outputs/stage2_canary
```

结果：退出码 0。

Validation 命令：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python \
  audit_outputs/stage2_canary/2026_07_13-23_02_46/validate_stage2_canary.py \
  /home/lijingsu/vla/audit_outputs/stage2_canary/2026_07_13-23_02_46
```

结果：退出码 0，`passed: true`。

## Outputs

Run directory：

```text
/home/lijingsu/vla/audit_outputs/stage2_canary/2026_07_13-23_02_46
```

Files：

- `summary.json`：223282 bytes
- `episodes.jsonl`：135198 bytes
- `stage2_canary_validation.json`：1456 bytes
- `clean_task0_trial0_successTrue.mp4`：32614 bytes
- `disturbed_task0_trial0_successFalse.mp4`：77769 bytes
- `validate_stage2_canary.py`：6854 bytes

输出使用新的 timestamped directory，未覆盖历史结果；该目录未进入 Git status。

## Results

Canary raw outcome：

- clean：`status=success`，`success=true`，`num_policy_steps=75`
- reactive_disturbed：`status=timeout`，`success=false`，`timeout=true`，`num_policy_steps=220`

These two episode outcomes are chain-health observations only. They are not performance, robustness, or generalization claims.

## Required Checks

Validation output:

```json
{
  "passed": true,
  "failures": [],
  "records": 2,
  "conditions": ["clean", "disturbed"],
  "clean_status": "success",
  "clean_success": true,
  "clean_policy_steps": 75,
  "disturbed_status": "timeout",
  "disturbed_success": false,
  "disturbed_timeout": true,
  "disturbed_policy_steps": 220,
  "disturbance_delta_xyz_actual": [
    0.09999999999999999,
    0.04999999999999999,
    0.0
  ],
  "refresh_method": "env.env._get_observations(force_update=True)",
  "refresh_consumed_noop_env_step": false
}
```

Checklist:

1. clean/disturbed 配对字段完全一致：通过；validator 比较了 `pair_key`、checkpoint、seed、suite、task、initial state、task description、target joint、budget、reset/rollback count。
2. 初始机器人和目标物体状态一致：通过；validator 比较了 `initial_robot_state`、`initial_target_qpos`，并额外比较了 warmup 后 policy start 状态。
3. 扰动实际位移约为 `[0.10, 0.05, 0.0]`：通过；实际值为 `[0.09999999999999999, 0.04999999999999999, 0.0]`。
4. 扰动后的下一次推理使用 fresh observation：通过；policy step `70` 的 action 标记为 `uses_post_disturbance_fresh_observation=true`。
5. fresh observation 不消耗额外 policy step：通过；refresh method 为 `env.env._get_observations(force_update=True)`，`consumed_noop_env_step=false`，disturbed `environment_control_steps = warmup_simulator_steps + policy_inference_steps`。
6. 两个 episode 的预算规则一致：通过；两者 `max_policy_steps=220`，`warmup_env_steps=10`，`reset_count=0`，`rollback_count=0`。
7. timeout 不记录为 success：通过；reactive_disturbed 为 `status=timeout` 且 `success=false`。
8. 视频、事件、动作和 step 对齐：通过；action `t` 与 index 一致，`video_frame_index` 与 action index 一致，两个 video 文件存在且非空。
9. 没有人工干预：通过；两个 episode 均记录 `manual_intervention=false`，未启动 Dashboard。
10. 输出不覆盖历史结果：通过；输出写入新的 timestamped run directory。
11. 运行后 GPU 释放且没有遗留进程：通过；GPU compute app 列表为空，OpenVLA/LIBERO/Dashboard 进程无输出，`python` 仅系统服务。

## Postflight

运行后检查：

- `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`：无输出
- `pgrep -af openvla`：无输出
- `pgrep -af libero`：无输出
- `pgrep -af dashboard`：无输出
- `pgrep -af python`：仅系统服务 `networkd-dispatcher` 和 `unattended-upgrade-shutdown`

## Conclusion

阶段 2 单任务严格配对 Canary 链路通过。配对、状态一致性、扰动、fresh observation、预算、timeout 语义、视频/action 对齐、无人工干预、输出隔离和运行后资源释放均通过验证。

这只说明实验链路可用于后续受控阶段 2 工作；不得根据这一对 episode 宣称性能提升、鲁棒性或泛化能力。

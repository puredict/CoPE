# Correctness Gate Report

阶段：1.6 实验正确性闸门  
分支：`stage-1.6-correctness-gate`  
基线：`88afdea6b571454958fac57abd19c038d149f069` 为阶段 1.5 baseline import；本阶段实际改动基于外部新增后的 `68c3cddcc8393da78c28bdc1b90f869ab00b045f`。  
本阶段提交：见最终交付消息中的 Git HEAD；commit hash 无法稳定自包含在同一个 commit 的文件内容里。

## 输入材料状态

- 已确认 `/home/lijingsu/vla` 是 Git 仓库；开始时该仓库无 commit，因此先用阶段 1.5 准备的 `audit_outputs/20260713_211615/baseline_commit_file_list.txt` 创建 baseline commit `88afdea6b571454958fac57abd19c038d149f069`。
- 指定路径 `docs/audit/STATIC_AUDIT_REPORT.md`、`EXPERIMENT_MODE_MATRIX.md`、`BUG_AND_RISK_REGISTER.md`、`DUPLICATION_MAP.md` 在远端仓库开始时不存在；读取了本地副本 `/Users/lijingsu/Documents/Codex/2026-07-13/files-mentioned-by-the-user-b/outputs/` 下四个同名文件。
- 未找到独立的阶段 1.5 Markdown 报告；读取了远端 `audit_outputs/20260713_211615/commands.tsv`、`baseline_commit_file_list.txt` 和 git 状态日志作为阶段 1.5 证据。

## 修改文件清单

- `libero_experiment_core.py`
- `libero_disturbance_eval.py`
- `baseline_reset_rollback_eval.py`
- `baseline_stage_backtrack_eval.py`
- `baseline_current_world_replan_eval.py`
- `second_necessity_intervention.py`
- `libero_dashboard_controller.py`
- `verifier_vs_recovery_state_eval.py`
- `summarize_disturbance_results.py`
- `tests/test_experiment_helpers.py`
- `libero_observation_refresh_diagnostic.py`
- `docs/audit/CORRECTNESS_GATE_REPORT.md`

## 成功语义证据

- 项目环境创建路径：`src/openvla/experiments/robot/libero/libero_utils.py:18-25` 使用 `OffScreenRenderEnv`；`get_libero_image()` 在 `src/openvla/experiments/robot/libero/libero_utils.py:50-58` 只读取传入 `obs["agentview_image"]`。
- robosuite base `step()` 在 `.venv/lib/python3.10/site-packages/robosuite/environments/base.py:364-407` 返回 4 元组 `(observations, reward, done, info)`；不是 Gymnasium 的 5 元组，没有 `terminated/truncated` 返回值。
- robosuite base 的 `_post_action()` 在 `.venv/lib/python3.10/site-packages/robosuite/environments/base.py:418-434` 把 `done` 定义为 horizon timeout。
- LIBERO `BDDLBaseDomain.step()` 在 `src/LIBERO/libero/libero/envs/bddl_base_domain.py:800-809` 覆盖 `done = self._check_success()`，因此当前项目调用链中 `done` 表示任务成功，不表示 timeout。
- LIBERO reward 在 `src/LIBERO/libero/libero/envs/bddl_base_domain.py:165-189` 是 sparse success reward，成功时 `1.0`，否则 `0.0`；LIBERO README 也在 `src/LIBERO/README.md:126-133` 写明 sparse `+1`。
- 具体任务成功由 goal predicates 判断，例如 `src/LIBERO/libero/libero/envs/problems/libero_tabletop_manipulation.py:135-143`。

结论：当前 LIBERO wrapper 下，把 `done` 当 success 有源码依据；但项目自己的 `max_steps` 超时不会令 `done=True`，所以必须用显式状态区分 success、timeout、stopped、simulator_error、failure。已在 `libero_experiment_core.py:177-279` 实现 `extract_episode_status()`，各 rollout 输出 `status`、`episode_status`、`timeout`、`stopped`、`simulator_error`、`success_source`。

## 观测刷新证据

- robosuite `_get_observations(force_update=True)` 在 `.venv/lib/python3.10/site-packages/robosuite/environments/base.py:326-342` 明确用于直接设置 simulation state 后、不 step 就获取最新观测。
- LIBERO wrapper `regenerate_obs_from_state()` 在 `src/LIBERO/libero/libero/envs/env_wrapper.py:139-145` 的顺序是 `set_state -> sim.forward -> check_success -> _post_process -> _update_observables(force=True) -> _get_observations()`。
- 本阶段统一刷新函数在 `libero_experiment_core.py:600-660`：`sim.forward()` 后调用 success/post-process/observable force update，再调用 `_get_observations(force_update=True)`；只有找不到接口才 fallback 到 dummy step。
- 主脚本和 baseline/recovery 脚本在扰动后立刻刷新 `obs`，例如 `libero_disturbance_eval.py:164`、`baseline_reset_rollback_eval.py:108`、`baseline_stage_backtrack_eval.py:105`、`second_necessity_intervention.py:102`、`baseline_current_world_replan_eval.py:118`。
- 最小真实 LIBERO 诊断脚本：`libero_observation_refresh_diagnostic.py`。运行结果在 `audit_outputs/correctness_gate_refresh/20260713_214203/observation_refresh_diagnostic.json`：
  - `step_return_len: 4`
  - `old_obs_reused_pixel_delta.changed_pixels: 0`
  - `fresh_obs_pixel_delta.changed_pixels: 10734`
  - `qpos_reflects_mutation: true`
  - `refresh.method: env.env._get_observations(force_update=True)`
  - `consumed_noop_env_step: false`

结论：旧 `obs` 确实是旧图；强制刷新后下一次策略推理会使用扰动后的 fresh obs。

## 预算规则

统一字段由 `libero_experiment_core.py:54-65` 的 `BudgetReport` 和 `libero_experiment_core.py:282-307` 的 `make_budget_report()` 生成。所有正式比较默认使用 `policy_step_budget=max_steps`。

- `warmup_simulator_steps`：reset/set-init 后用于物体稳定的 dummy simulator steps；不算 policy inference。
- `policy_inference_steps` / `total_policy_steps_consumed`：实际调用策略模型的次数。
- `environment_control_steps`：warmup + policy control + refresh fallback dummy steps。
- `pre_disturbance_policy_steps`：扰动前 policy inference 次数。
- `recovery_policy_steps`：扰动后或恢复阶段 policy inference 次数。
- `reset_count`：episode 中 full reset 次数。
- `rollback_count`：oracle sim-state rollback 次数。
- `success_within_original_budget`：`success and total_policy_steps_consumed <= policy_step_budget`。

模式规则：

- `reactive_disturbed` / clean-disturbed 主脚本：保留当前世界；无 reset/rollback；扰动后只使用剩余原始 policy budget。
- `full_reset_replan`：标记为 `restart_baseline_not_current_world_recovery`；`reset_count=1`；reset 后 warmup 计入 `warmup_simulator_steps`；不再自动获得未记录的新完整 `max_steps`，只使用剩余原始 `policy_step_budget`。
- `oracle_rollback`：标记为 `oracle_upper_bound_state_undo`；`rollback_count=1`；恢复扰动前 sim state，属于 oracle upper bound，不是现实恢复算法；刷新不消耗 policy inference。
- `verifier_stop`：标记为 `programmed_oracle_event_stop`；输出 `status=stopped`，不作为 task success。

## 目标选择规则

- `libero_experiment_core.py:467-506` 新增 `select_target_joint()` / 更新 `choose_target_joint()`。
- 返回结构包含 `selected_joint`、全部 `candidates`、每个候选 `score`、`matched_task_tokens`、`score_reason`、`reason`。
- 显式 `--target-joint` 会验证 free joint 后直接使用，`reason=explicit_target_joint`。
- 自动选择如无合法 free joint、最高分为 0、或最高分并列，会抛错，要求显式目标。
- 单元测试覆盖合成名称：`tests/test_experiment_helpers.py:113-144`。
- 最小诊断对 LIBERO-Spatial task 0 使用显式 `akita_black_bowl_1_joint0`；候选中 `akita_black_bowl_1_joint0` 和 `akita_black_bowl_2_joint0` 同为 score 2，说明正式阶段 2 canary 必须显式传 `--target-joint`，不能依赖 auto。

## 诊断指标隔离

- `verifier_vs_recovery_state_eval.py:69`、`:93`、`:111`、`:160-161`、`:190-191` 输出 `diagnostic_assumption`、`not_empirical_model_measurement`、`exclude_from_formal_success_summaries`。
- `second_necessity_intervention.py:179`、`:204-205` 同样标记其 structured/verifier 字段为代码注入的诊断假设。
- `summarize_disturbance_results.py:23-40` 会跳过 `not_empirical_model_measurement` / `exclude_from_formal_success_summaries` 的 run，并优先使用 `success_within_original_budget`。

## 实际运行命令和退出码

- `git add --pathspec-from-file=audit_outputs/20260713_211615/baseline_commit_file_list.txt && git commit -m "Stage 1.5 baseline import"`：退出码 0，生成 `88afdea6b571454958fac57abd19c038d149f069`。
- `git switch -c stage-1.6-correctness-gate`：退出码 0。之后外部 `main` 前进到 `68c3cddcc8393da78c28bdc1b90f869ab00b045f`，本分支重新基到该 commit 以保留外部新增文件。
- `.venv/bin/python -m py_compile ...`：退出码 0。
- `.venv/bin/python -m pytest tests/test_experiment_helpers.py tests/test_dashboard_controller.py -q`：退出码 0，`26 passed in 1.61s`。
- `.venv/bin/python libero_observation_refresh_diagnostic.py --task-suite libero_spatial --task-id 0 --trial-id 0 --target-joint akita_black_bowl_1_joint0 --dx 0.20 --dy 0.00 --resolution 128`：退出码 0，`passed: true`。
- `rg -n "success\s*=\s*bool\(done\)|\"success\"\s*:\s*bool\(done\)" *.py tests || true`：退出码 0，未返回命中。

## 尚未解决的问题

- 远端开始时缺失指定 `docs/audit/*` 输入文档和独立阶段 1.5 Markdown 报告；本报告记录了替代读取来源。
- 本阶段没有运行 OpenVLA，也没有做大规模 rollout；只完成 CPU tests 和一个不加载 OpenVLA 的 LIBERO refresh 诊断。
- 还没有为每个正式 LIBERO-Spatial task 建人工 target-joint manifest；阶段 2 canary 必须显式指定目标 joint。
- `full_reset_replan` 和 `oracle_rollback` 仍只能作为 restart / oracle upper-bound baseline，不应与 current-world recovery 放在同一 success ranking。

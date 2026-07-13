# Experiment Mode Matrix

本矩阵基于源码快照静态阅读。所有 “可声称含义” 都以当前代码证据为上限；涉及 `done`、fresh observation、target joint 正确性的结论需待运行验证。

## 1. 模式总览

| 模式 | 主要脚本 | 是否真实修改环境 | 扰动后世界是否保留 | 是否修改 prompt | 是否重置环境 | 是否恢复 saved sim state | 是否使用 oracle / 程序信息 | 额外预算 | 停止条件 | 当前可合理声称的含义 | 当前不能支持的结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `clean` | `libero_disturbance_eval.py` | 否 | 不适用 | 否，使用原始 task description | 否 | 否 | 否 | 与主 disturbed run 相同的 `max_steps + num_steps_wait` 结构 | `done` 或达到 loop 上限 | 原始未扰动任务表现基线 | 不能说明扰动恢复能力 |
| `reactive_disturbed` / `disturbed` | `libero_disturbance_eval.py`; `baseline_reset_rollback_eval.py`; `baseline_stage_backtrack_eval.py`; `second_necessity_intervention.py` | 是，修改 free joint qpos | 是，除非后续自然 dynamics 改变 | 否，使用原始 task description | 否 | 否 | target joint 由 heuristic 或参数给出 | 名义上无额外预算 | `done` 或达到上限 | VLA 在当前扰动世界中继续执行的 reactive baseline | 在 stale obs、target 选择、success 语义未修复前，不能作为可靠恢复率 |
| `verifier_stop` | `baseline_stage_backtrack_eval.py`; `second_necessity_intervention.py` | 是，扰动发生后立即停止 | 是，但停止后不继续行动 | 否 | 否 | 否 | 是，代码知道扰动发生时刻并直接停止 | 无额外行动预算；实际不尝试恢复 | 扰动分支内 `break` | 程序化 safety stop / oracle event stop baseline | 不能证明 verifier-only 系统无法恢复；不能与继续执行模式按 success 直接比较 |
| `structured_relocalize_prompt` | `baseline_stage_backtrack_eval.py` | 是 | 是 | 是，切换为 relocalize affected object 的自然语言 prompt | 否 | 否 | 是，affected object 来自扰动 joint heuristic；goal phrase 来自字符串 heuristic | 无显式额外预算 | `done` 或达到上限 | prompt-only current-world relocalization intervention | 不能声称完整 structured recovery state 或自动状态估计 |
| `structured_reprompt_recovery` | `second_necessity_intervention.py` | 是 | 是 | 是，切换为 relocalize prompt | 否 | 否 | 是，`affected_joint`、`affected_object`、`invalid_state` 由代码直接写入 | 无显式额外预算 | `done` 或达到上限 | oracle/semi-oracle recovery-state prompt ablation | 不能把 `selective_recovery_state_rate` 当作模型实测能力；不能声称自动发现 invalid state |
| `stage_backtrack_subgoal` | `baseline_stage_backtrack_eval.py` | 是 | 是 | 是，改为 “pick up affected object from current position and place it on goal” | 否 | 否 | 是，affected object 和 goal phrase 由字符串 heuristic 给出 | 无显式额外预算 | `done` 或达到上限 | prompt-level stage restart in current world | 不能声称有可靠阶段状态机或 subgoal tracker |
| `full_reset_replan` | `baseline_reset_rollback_eval.py` | 是，然后 reset | 否，reset 回 init state，扰动被消除 | 否，原始 prompt | 是，`env.reset()` + `set_init_state(init_states[0])` | 否 | 是，代码在扰动事件触发时选择 reset | 是：扰动前已执行的动作，加 reset wait，再从 `policy_t=0` 获得新一轮预算；返回记录未完整计费 | reset 后 `done` 或达到上限 | full task restart baseline；可作为 “从头再来能否完成” | 不能作为 current-world recovery；不能与 reactive/prompt 模式按 final success 公平比较 |
| `oracle_rollback` | `baseline_reset_rollback_eval.py` | 是，然后 rollback | 否，恢复扰动前 sim state，扰动被撤销 | 否，原始 prompt | 否 | 是，`sim.set_state_from_flattened(saved_state_for_rollback)` | 是，使用扰动前完整 sim state oracle | 有一次 dummy action refresh，`policy_t += 1`，但不进入 `actions` | rollback 后继续，`done` 或达到上限 | ideal oracle upper bound / state undo sanity check | 不能作为现实恢复算法；不能证明 selective recovery 能力 |

## 2. 每个模式的代码路径

### `clean`

- 入口：`libero_disturbance_eval.py:238-240` 中 `condition in ["clean", "disturbed"]`。
- 初始化：`env.reset()` 后 `obs = env.set_init_state(initial_states[trial_id])`，见 `libero_disturbance_eval.py:147-148`。
- 扰动：无。
- prompt：`get_action(..., task_description, ...)`，见 `libero_disturbance_eval.py:178`。
- 输出：`condition`、`task_id`、`trial_id`、`success`、`actions`、`video_path`，见 `libero_disturbance_eval.py:201-214`。
- 可作为基线：同一脚本内的 clean/disturbed paired comparison。
- 限制：`success=done` 未核实；没有 init state hash。

### `reactive_disturbed` / `disturbed`

- 主脚本 condition：`libero_disturbance_eval.py:163-164` 在 `condition == "disturbed"` 且 `policy_t == disturbance_step` 时调用 `move_free_joint_xy`。
- baseline mode：`baseline_reset_rollback_eval.py:127`、`baseline_stage_backtrack_eval.py:121`、`second_necessity_intervention.py:128` 都包含 reactive mode。
- 世界状态：扰动后不 reset/rollback。
- prompt：不改变，继续使用原始 task description。
- 关键风险：扰动后直接使用旧 `obs` 做下一次 policy input。
- 可作为基线：当前世界下无显式恢复机制的 VLA continuation。
- 限制：需要 fresh obs、target joint、success semantics 修复后才适合正式统计。

### `verifier_stop`

- `baseline_stage_backtrack_eval.py:93-97`：扰动后设置 recovery 并 break。
- `second_necessity_intervention.py:91-96`：扰动后设置 `stopped_by_verifier=True` 并 break。
- 世界状态：扰动被施加，但 episode 立即停止。
- prompt：没有 recovery prompt 生效，因为停止前不再 action。
- oracle 信息：代码知道扰动发生，不是独立 verifier。
- 可作为基线：安全停止或人工定义 detector-triggered stop。
- 不可声称：verifier-only 方法理论上不能恢复。

### `structured_relocalize_prompt`

- `baseline_stage_backtrack_eval.py:102-104`：把 prompt 改成 relocalize affected object。
- affected object：`object_phrase_from_joint(target_joint)`，见 `baseline_stage_backtrack_eval.py:51-53`。
- 世界状态：保留当前扰动世界。
- prompt 切换时机：扰动同一 policy step 分支内切换；下一次 `policy_step` 使用新 prompt，但 observation 可能 stale。
- 可作为基线：prompt-only relocalization ablation。
- 不可声称：完整结构化恢复或自动故障状态估计。

### `structured_reprompt_recovery`

- `second_necessity_intervention.py:97-107`：构造 `recovery_state`，并切换 `current_task_desc`。
- structured 字段：`affected_joint`、`affected_object`、`invalid_state`、`decision`、`has_selective_recovery_state=True`。
- oracle 信息：这些字段由代码根据扰动 joint 直接写入。
- summary 指标：`second_necessity_intervention.py:135` 的 `selective_recovery_state_rate` 只是检查字段是否存在。
- 可作为基线：带 oracle recovery semantics 的 prompt intervention。
- 不可声称：模型自己识别 affected object / invalid state。

### `stage_backtrack_subgoal`

- `baseline_stage_backtrack_eval.py:98-101`：prompt 改为从 current position 重新 pick affected object 并 place 到 goal。
- goal phrase：`infer_goal_phrase` 只检查是否包含 `plate`，见 `baseline_stage_backtrack_eval.py:55-59`。
- 世界状态：保留当前扰动世界。
- 可作为基线：stage prompt restart ablation。
- 不可声称：真实 stage backtracking controller；没有状态机。

### `full_reset_replan`

- `baseline_reset_rollback_eval.py:93-101`：扰动后 `env.reset()`、`set_init_state(init_states[0])`，再做 wait steps，`policy_t = 0`。
- 世界状态：扰动被 reset 消除。
- 预算：扰动前动作不清零于 `actions`，reset 后又获得最多 `max_steps` 的 policy loop；`reset_budget_added` 未返回。
- 可作为基线：full restart upper baseline。
- 不可声称：局部恢复或当前变化世界中的重规划。

### `oracle_rollback`

- `baseline_reset_rollback_eval.py:89-90` 保存扰动前 sim state。
- `baseline_reset_rollback_eval.py:102-108` 扰动后恢复保存状态并 dummy step。
- 世界状态：扰动被撤销。
- 预算：dummy step 没有进入 `actions`，但会推进环境。
- 可作为基线：理想上界 / undo oracle。
- 不可声称：现实可用恢复算法。

## 3. 模式间公平性结论

可以较公平比较的前提：

- 同一 task suite、task id、trial id、initial state hash。
- 同一 checkpoint、unnorm key、image preprocessing、seed、max steps。
- 同一 observation refresh 规则。
- 同一 success/timeout/exception 定义。
- 同一 action/env step cost accounting。

当前代码中：

- `clean` vs `disturbed` 在 `libero_disturbance_eval.py` 内最接近 paired design，但仍缺少 init hash、fresh obs 和 success 语义确认。
- `reactive_disturbed`、`structured_*`、`stage_backtrack_subgoal` 都保留扰动后世界，理论上可组成 current-world recovery comparison；但必须统一 target selection、fresh obs 和 prompt/event logging。
- `full_reset_replan` 与 `oracle_rollback` 不应进入同一 success 排名，只能作为 restart/upper-bound 参考。
- `verifier_stop` 不尝试完成任务，不能按 final success 与继续执行模式比较。

## 4. 论文表述建议

较安全的表述：

- “We evaluate a reactive continuation baseline under object displacement.”
- “We include full reset and oracle rollback as non-comparable restart / upper-bound references.”
- “We test prompt-only relocalization and stage-backtracking interventions with oracle affected-object information.”
- “Offline verifier-vs-state metrics are diagnostic labels, not environment-measured performance.”

暂不安全的表述：

- “Structured recovery state is empirically proven superior”。
- “Verifier-only recovery fails”。
- “Full reset replan recovers from the disturbed current world”。
- “All success rates are validated task success”。
- “Auto-selected disturbance object is correct for all tasks”。

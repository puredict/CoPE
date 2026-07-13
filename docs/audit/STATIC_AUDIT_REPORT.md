# LIBERO / OpenVLA Disturbance Recovery Static Audit

审计会话：`B_STATIC_AUDIT` / `static-audit`  
日期：2026-07-13  
审计对象：`/Users/lijingsu/Downloads/B_STATIC_AUDIT/original_source_snapshot.tar.gz`  
预期项目主目录：`/home/lijingsu/vla`  

## 0. 边界与方法

本报告只基于静态代码阅读和允许的静态命令。未加载 OpenVLA，未运行 LIBERO rollout，未使用 GPU，未安装或升级依赖，未修改任何被审计源码。

已阅读任务材料：

- `/Users/lijingsu/Downloads/B_STATIC_AUDIT/START_HERE.txt`
- `/Users/lijingsu/Downloads/B_STATIC_AUDIT/PROJECT_CONTEXT.md`
- `/Users/lijingsu/Downloads/B_STATIC_AUDIT/WORKTREE_PROTOCOL.md`
- `/Users/lijingsu/Downloads/B_STATIC_AUDIT/TASK_SPEC.md`
- `/Users/lijingsu/Downloads/B_STATIC_AUDIT/MANIFEST.md`
- `/Users/lijingsu/Downloads/B_STATIC_AUDIT/references/CURRENT_CODE_AUDIT.md`
- `/Users/lijingsu/Downloads/B_STATIC_AUDIT/references/PHASE_CHECKLIST.md`

已逐行阅读源码快照中的所有 Python 和 Shell 文件：

- `baseline_reset_rollback_eval.py`
- `baseline_stage_backtrack_eval.py`
- `check_vla_env.py`
- `disturbance_probe.py`
- `download_openvla.py`
- `download_openvla_libero_spatial.py`
- `libero_base_closed_loop_smoke.py`
- `libero_disturbance_eval.py`
- `libero_disturbance_smoke.py`
- `openvla_smoke.py`
- `run_baseline_base_openvla.sh`
- `run_expanded_spatial_3trials.sh`
- `run_full_spatial_disturbance.sh`
- `run_magnitude_large.sh`
- `run_magnitude_small.sh`
- `run_one_probe.py`
- `run_timing_step120.sh`
- `run_timing_step30.sh`
- `run_timing_step60.sh`
- `second_necessity_intervention.py`
- `summarize_disturbance_results.py`
- `verifier_vs_recovery_state_eval.py`
- `wait_and_collect_disturbance_results.sh`

实际执行的静态命令：

- `ls -la /Users/lijingsu/Downloads/B_STATIC_AUDIT`，退出码 0。
- `rg --files /Users/lijingsu/Downloads/B_STATIC_AUDIT`，退出码 0。
- `cat` 读取任务与参考文档，退出码 0。
- `tar -tzf /Users/lijingsu/Downloads/B_STATIC_AUDIT/original_source_snapshot.tar.gz`，退出码 0。
- `tar -xzf /Users/lijingsu/Downloads/B_STATIC_AUDIT/original_source_snapshot.tar.gz -C work/static-audit-src`，退出码 0。
- `rg --files work/static-audit-src`，退出码 0。
- `nl -ba` 逐文件读取源码，退出码 0。
- `PYTHONPYCACHEPREFIX=/private/tmp/static-audit-pycache python3 -m py_compile ...` 覆盖全部 14 个 Python 文件，退出码 0。
- `which shellcheck`，退出码 1，结果为 `shellcheck not found`，因此未执行 Shell 静态检查。
- `python3 -c` 使用标准库 `ast` 解析函数范围和近似重复组，退出码 0，未 import 项目模块。
- `rg -n "secret|password|api[_-]?key|token|hf[_-]?token|HUGGINGFACE|OPENAI|PRIVATE|ssh|credential|auth" work/static-audit-src`，退出码 0；命中均为普通 tokenization / env 名称，没有发现明文密钥。
- `git status --short` 在当前本地工作区退出码 128：当前目录不是 Git 仓库；源码快照也不是 Git worktree。因此本地无法生成任务协议要求的真实 commit hash。

## 1. 总体结论

现有代码已经覆盖了若干重要实验想法：原始 clean/disturbed 对照、扰动时机与幅度消融、base OpenVLA 与 LIBERO-Spatial checkpoint 对比、full reset / oracle rollback / verifier stop / prompt recovery 等恢复模式。但从静态证据看，正式实验与论文结论前至少有四类问题必须先处理：

1. **正确性**：多个脚本在修改 MuJoCo `qpos` 并 `sim.forward()` 后，下一次策略推理仍使用修改前的 `obs` 生成图像和 proprio state。这会造成扰动后第一步策略输入可能滞后一拍。此项需要真实环境验证刷新语义，但代码层面缺少 fresh observation。
2. **公平性**：`full_reset_replan` 和 `oracle_rollback` 会消除扰动后的世界状态，并且存在额外或未记录的环境步预算，不能直接与 current-world reactive/prompt recovery 比最终 success。
3. **指标语义**：所有闭环评测基本把 `done` 直接写成 `success`，没有核实 wrapper 中 `done`、`reward`、`info` 的语义，也没有 timeout/exception/termination reason。
4. **结论边界**：`verifier_vs_recovery_state_eval.py` 中多项 rate 是代码预设字段统计，不是模型或 verifier 在环境中实测得到；`structured_*` 主要是 prompt 改写，不是完整结构化恢复架构。

以下发现均按源码证据列出。无法仅靠静态代码确认的部分标为“待运行验证”。

## 2. 详细发现

### F-01: 扰动后下一次策略推理可能使用 stale observation

- 严重性：High
- 类别：correctness / fairness
- 证据文件与行号：
  - `libero_disturbance_eval.py:163-166`：`move_free_joint_xy(...)` 后立即 `img = get_libero_image(obs, resize_size)`。
  - `baseline_reset_rollback_eval.py:88-91` 与 `109-111`：reactive 模式扰动后直接进入 `policy_step(..., obs, ...)`。
  - `baseline_stage_backtrack_eval.py:93-105`：扰动和 prompt 切换后直接对旧 `obs` 做 `policy_step`。
  - `second_necessity_intervention.py:91-108`：扰动和 structured reprompt 后直接 `get_libero_image(obs, resize_size)`。
  - `libero_disturbance_smoke.py:51-61`：`data.set_joint_qpos(...); sim.forward()` 后直接使用旧 `obs` 图像。
- 可验证代码证据：所有 `move_free_joint_xy` 只改 `sim.data.qpos` 并 `sim.forward()`；扰动分支没有重新赋值 `obs`，也没有调用 env 的 observation getter。`obs` 只在之前的 `env.step(...)` 或 `env.set_init_state(...)` 中获得。
- 可能后果：扰动发生后的第一次策略动作可能基于扰动前图像和状态输出，恢复能力会被低估或行为解释错位；不同模式如果刷新方式不同，会破坏可比性。
- 事实 / 推断 / 待运行验证：
  - 事实：代码在 qpos 修改后没有刷新 `obs`。
  - 推断：下一次图像/状态可能 stale。
  - 待运行验证：LIBERO wrapper 是否有隐藏机制让旧 `obs` 在 `sim.forward()` 后自动引用新图像；从 Python 对象语义看不能默认成立。
- 建议验证方法：在 mock 或真实小环境中记录扰动前后同一 `obs` 调用 `get_libero_image(obs, ...)` 的像素差，并对比一次 no-op/env step 后的新 obs；同时记录 eef/object pose。
- 建议修复方向：统一提供 `refresh_obs_after_state_mutation(env, reason)`，明确选择 no-op step、sim render 或 wrapper observation API；把刷新成本写入 episode events，所有模式统一使用。

### F-02: `done` 被直接作为 `success`，缺少 wrapper 语义核实

- 严重性：High
- 类别：correctness / claim validity / observability
- 证据文件与行号：
  - `libero_disturbance_eval.py:184-195` 只检查 `done`，`197` 文件名写 `success{bool(done)}`，`208` 记录 `"success": bool(done)`。
  - `baseline_reset_rollback_eval.py:111-118` 同样将 `done` 写成 success。
  - `baseline_stage_backtrack_eval.py:107-112` 同样将 `done` 写成 success。
  - `second_necessity_intervention.py:113-119` 同样将 `done` 写成 success。
  - smoke 脚本 `libero_base_closed_loop_smoke.py:66-73`、`libero_disturbance_smoke.py:71-85` 记录 `done` 和 `reward`，但没有验证 `info`。
- 可验证代码证据：`info` 被接收但未保存；`reward` 只作为 float 记录，没有参与 success 判定；没有 timeout 或 failure reason 字段。
- 可能后果：如果 wrapper 的 `done` 包含 timeout、early termination、failure termination 或 success 以外条件，成功率会被错误计算，论文结论可能无效。
- 事实 / 推断 / 待运行验证：
  - 事实：代码以 `bool(done)` 作为 success。
  - 待运行验证：当前 LIBERO wrapper 中 `done` 是否严格等价于 task success。
- 建议验证方法：查阅并运行最小 wrapper probe，记录 `done`、`reward`、`info` 中所有 success/failure 字段；制造 timeout episode 看 `done` 行为。
- 建议修复方向：引入显式 `termination_reason`、`success_source`、`success_bool`、`timeout_bool`、`reward_final` 和原始 `info` 摘要；汇总脚本只使用经确认的 success 字段。

### F-03: `full_reset_replan` 与 `oracle_rollback` 消除扰动后的世界，且预算不公平

- 严重性：High
- 类别：fairness / claim validity / correctness
- 证据文件与行号：
  - `baseline_reset_rollback_eval.py:88-92` 在扰动点保存/修改状态。
  - `baseline_reset_rollback_eval.py:93-101`：`full_reset_replan` 执行 `env.reset(); obs=env.set_init_state(init_states[0])`，再做 `num_steps_wait` dummy step，并将 `policy_t = 0`。
  - `baseline_reset_rollback_eval.py:102-108`：`oracle_rollback` 执行 `sim.set_state_from_flattened(saved_state_for_rollback); sim.forward()`，再做一次 dummy action，并 `policy_t += 1`。
  - `baseline_reset_rollback_eval.py:82` 定义 `reset_budget_added=0`，`99` 更新，但 `118` 返回记录中没有该字段。
- 可验证代码证据：full reset 回到初始状态，扰动对象位移被消除；oracle rollback 恢复扰动前 sim state，也撤销外部扰动。full reset 在扰动前已执行约 70 个策略动作，reset 后又可从 `policy_t=0` 到 `max_steps`，总 env/action 成本不等价；oracle 的 dummy step 不进入 `actions`。
- 可能后果：把这两个模式与 reactive disturbed 或 prompt recovery 直接比较 success，会把“重开/撤销世界变化”的优势误当成恢复算法优势。
- 事实 / 推断 / 待运行验证：
  - 事实：代码 reset/rollback 消除了扰动后的世界状态。
  - 事实：额外 dummy/wait 成本未完整纳入 `num_policy_steps`。
  - 待运行验证：真实 env reset 是否完全恢复所有 object/contact/state。
- 建议验证方法：记录扰动前、扰动后、reset/rollback 后的 full sim state hash、目标 object pose、episode wall-clock/env steps/action count。
- 建议修复方向：将 `full_reset_replan` 标为 restart baseline，将 `oracle_rollback` 标为 ideal upper bound；新增 `env_steps_total`、`policy_actions_total`、`dummy_steps_total`、`world_state_after_recovery`，禁止只按 final success 排名。

### F-04: 离线 verifier / structured state 指标是程序预设，不是实测性能

- 严重性：Critical
- 类别：claim validity
- 证据文件与行号：
  - `verifier_vs_recovery_state_eval.py:63-76`：`verifier_only_policy` 直接把 `can_identify_affected_object`、`can_identify_invalid_state`、`can_preserve_completed_subgoals`、`recovery_type_correct` 设为 `False`。
  - `verifier_vs_recovery_state_eval.py:79-115`：`structured_state_policy` 直接构造 `state`，并把 `detects_invalid_continuation=True`、`can_identify_invalid_state=True`、`can_preserve_completed_subgoals=True`、`recovery_type_correct=True`。
  - `verifier_vs_recovery_state_eval.py:151-170`：metrics 用这些布尔字段计算 rate。
  - `verifier_vs_recovery_state_eval.py:170`：interpretation 直接宣称 oracle verifier collapse 到 stop/full_replan，而 structured state exposes recovery action。
- 可验证代码证据：这些 rate 没有调用模型、环境、视频、日志 classifier 或 verifier；只读取已有 summary 并生成 schema/标签。
- 可能后果：若将这些 rate 写成实验结果，会把设计假设包装成实测能力差异，严重影响论文可信度。
- 事实 / 推断 / 待运行验证：
  - 事实：rate 来源为代码预设字段。
  - 结论：不能作为闭环实验证据。
- 建议验证方法：只把该脚本输出标注为 conceptual diagnostic / schema sanity check；如需实证，必须实现真实 verifier 和 recovery-state estimator，并在闭环 episode 中评估。
- 建议修复方向：重命名 metrics 字段，例如 `designed_capability_label_rate`；报告中单独隔离，不进入 performance table。

### F-05: baseline/recovery 脚本缺少 clean 配对和 trial 维度

- 严重性：High
- 类别：fairness / reproducibility
- 证据文件与行号：
  - `libero_disturbance_eval.py:148` 使用 `initial_states[trial_id]`，`238-240` 对每个 trial/task 依次运行 `clean` 与 `disturbed`。
  - `baseline_reset_rollback_eval.py:76` 固定 `init_states[0]`，`126-131` 只遍历 tasks 和 modes，没有 clean 条件和 trial_id。
  - `baseline_stage_backtrack_eval.py:86` 固定 `init_states[0]`，`120-125` 只遍历 tasks 和 modes。
  - `second_necessity_intervention.py:82` 固定 `init_states[0]`，`127-132` 只遍历 tasks 和 modes。
- 可验证代码证据：三类 baseline/recovery 脚本的返回记录没有 `trial_id` 字段，也没有 paired clean record。
- 可能后果：不能直接把 baseline/recovery 模式的 success_by_mode 与主 clean/disturbed 多 trial 结果视作同一实验设计；统计比较缺少同 task/init state/seed 配对。
- 事实 / 推断 / 待运行验证：
  - 事实：baseline/recovery 脚本固定 initial state 0。
  - 推断：不同脚本结果之间可比性弱，尤其当 main run 使用多 trial 时。
- 建议验证方法：为每个模式记录 `task_id`、`trial_id`、init state hash、seed、checkpoint、unnorm key；对每个 pair 运行 clean/reactive/recovery。
- 建议修复方向：统一 experiment matrix runner，所有模式共享同一 task/trial/initial_state manifest。

### F-06: 自动选择扰动目标依赖字符串 token heuristic，可能选错且不可审计

- 严重性：High
- 类别：correctness / reproducibility / observability
- 证据文件与行号：
  - `libero_disturbance_eval.py:96-114`：用 task description tokens 与 object/joint name tokens 的交集得分，排序后取第一个。
  - `baseline_reset_rollback_eval.py:40-49`、`baseline_stage_backtrack_eval.py:40-49`、`second_necessity_intervention.py:41-51` 复制类似逻辑。
  - `libero_disturbance_eval.py:111-114` 只在无候选时报错；若所有 candidate 得分为 0，仍会选排序第一项。
  - `libero_disturbance_smoke.py:40-47` 固定 `libero_10` task 0 和 `tomato_sauce_1_joint0`，不能验证 Spatial suite 的 auto 选择。
- 可验证代码证据：返回记录只保存最终 `target_joint`，没有保存候选列表、得分、body 名称、task token 或人工 override rationale。
- 可能后果：扰动可能施加到与任务无关的物体上，导致 disturbed success 过高或过低；structured prompt 中 affected object 也会继承错误目标。
- 事实 / 推断 / 待运行验证：
  - 事实：heuristic 不要求正分，不记录候选。
  - 待运行验证：每个 LIBERO-Spatial task 是否选中预期 manipulated object。
- 建议验证方法：对全 task suite 打印 candidate table、score、joint/body pose；用人工标注或 scene metadata 对照。
- 建议修复方向：将 target selection 做成显式 manifest：`task_id -> allowed target joint/body`；auto 只作为辅助建议，正式实验使用已审计映射。

### F-07: action trace、扰动事件、视频帧和 prompt 切换缺少严格对齐

- 严重性：Medium
- 类别：observability / reproducibility
- 证据文件与行号：
  - `libero_disturbance_eval.py:166-185`：先 append 图像，再 step；`action_trace` 只在 step 后记录 action/reward/done，没有事件行。
  - `baseline_stage_backtrack_eval.py:93-108`：在扰动时改变 `current_prompt`，action 行记录 `task_prompt`，但没有独立 event timestamp/frame id。
  - `second_necessity_intervention.py:91-114`：同样缺少扰动/prompt event 行。
  - `baseline_reset_rollback_eval.py:102-108`：oracle rollback dummy step 不进入 `actions`。
  - `save_video` 在多个脚本中固定 `fps=30`，例如 `libero_disturbance_eval.py:117-122`、`baseline_reset_rollback_eval.py:58-62`。
- 可验证代码证据：JSON 记录有 `actions` list，但没有统一 `events` list，也没有 frame index、pre/post action observation id、env_step id。
- 可能后果：视频中的扰动帧、日志中的 step 和 action trace 可能难以一一对应；论文中展示视频或 dashboard 时容易误标。
- 事实 / 推断 / 待运行验证：
  - 事实：缺少统一事件日志和 frame/action id。
  - 推断：视频帧数不等于真实时间，30 FPS 是播放参数。
- 建议验证方法：运行最短 mock episode，检查每个 event/action/frame 的 id 连续性；对扰动时刻保存 raw/annotated frame。
- 建议修复方向：统一事件 schema：`env_step`、`policy_step`、`frame_id`、`event_type`、`obs_source`、`prompt_id`、`action_id`、`cost_accounting`。

### F-08: timeout、exception 和 partial results 缺少显式处理

- 严重性：Medium
- 类别：observability / reproducibility
- 证据文件与行号：
  - `libero_disturbance_eval.py:157-195` 到达 loop 上限后自然退出，返回 `success: bool(done)`，没有 `timeout` 字段。
  - `baseline_reset_rollback_eval.py:83-118`、`baseline_stage_backtrack_eval.py:92-112`、`second_necessity_intervention.py:87-119` 同样没有 termination reason。
  - `rg -n "except|Exception|try|timeout|termination"` 仅命中普通字段/变量；评测脚本没有 episode-level try/except。
- 可验证代码证据：任何异常会中断当前 Python 进程；已完成记录只有逐 episode append 的 JSONL，summary 可能不生成。
- 可能后果：长实验中单个失败会破坏整批 summary；无法区分真正失败、超时、模型异常、环境异常、手动中断。
- 事实 / 推断 / 待运行验证：
  - 事实：没有显式 timeout/exception fields。
  - 推断：异常时可能没有完整 summary。
- 建议验证方法：mock 一个 `env.step` 抛异常，确认输出是否保留；跑 max_steps=0/1 的极短 episode 检查 timeout 字段。
- 建议修复方向：episode-level guarded runner，finally 中 close env/save partial；summary 汇总 `status` 而不是只汇总 success。

### F-09: structured recovery 主要是 prompt 改写，并使用程序提供的 affected object/state

- 严重性：Medium
- 类别：claim validity / correctness
- 证据文件与行号：
  - `baseline_stage_backtrack_eval.py:98-104`：`stage_backtrack_subgoal` 与 `structured_relocalize_prompt` 只修改 `current_prompt`。
  - `second_necessity_intervention.py:72-76`：注释说明 intervention intentionally minimal，只提供 recovery semantics。
  - `second_necessity_intervention.py:97-107`：`structured_reprompt_recovery` 直接把 `affected_joint`、`affected_object`、`invalid_state`、`decision` 写入 recovery_state。
- 可验证代码证据：没有独立状态估计器、物体检测器、verifier 模型、subgoal state machine 或 planner；OpenVLA 仍只通过自然语言 prompt 和当前 observation 取 action。
- 可能后果：可以声称“prompt-based recovery intervention”或“oracle affected-object prompt”，不能声称已有完整 structured recovery architecture。
- 事实 / 推断 / 待运行验证：
  - 事实：代码只改 prompt/JSON fields。
  - 推断：恢复信息是由实验代码给出的 oracle/semi-oracle 信息。
- 建议验证方法：把 prompt-only、affected-object-only、invalid-state-only、full structured prompt 拆成 ablation；记录信息来源。
- 建议修复方向：命名为 `oracle_reprompt_recovery` 或 `prompt_relocalize_current_world`；论文中明确不是 autonomous recovery-state inference。

### F-10: `verifier_stop` 是代码层停止基线，不能代表 verifier 理论能力

- 严重性：Medium
- 类别：claim validity / fairness
- 证据文件与行号：
  - `baseline_stage_backtrack_eval.py:93-97`：扰动发生后，若 `mode == "verifier_stop"`，直接设置 recovery 并 `break`。
  - `second_necessity_intervention.py:91-96`：同样直接 `stopped_by_verifier=True` 并 `break`。
  - `second_necessity_intervention.py:119` 返回 `stopped_by_verifier`，但没有真实 verifier 输出。
- 可验证代码证据：没有调用 verifier 模型或基于 observation 的检测逻辑；decision 由模式和扰动时刻直接决定。
- 可能后果：该模式只能表示“检测到无效继续后安全停止”的安全基线，不能证明 verifier-only 系统无法恢复。
- 事实 / 推断 / 待运行验证：
  - 事实：停止由代码分支决定。
  - 结论：不能作为 verifier 能力上限/下限的实证证明。
- 建议验证方法：实现真实 verifier inference 或明确标注 oracle stop baseline；用相同检测信号连接不同 recovery actions。
- 建议修复方向：报告中使用 `oracle_event_stop` 或 `programmed_stop_on_disturbance` 命名。

### F-11: stage/object prompt 解析存在硬编码假设

- 严重性：Medium
- 类别：correctness / claim validity
- 证据文件与行号：
  - `baseline_stage_backtrack_eval.py:51-53`：`object_phrase_from_joint` 删除 `akita_` 和 `_1`。
  - `baseline_stage_backtrack_eval.py:55-59`：`infer_goal_phrase` 如果 task description 包含 `plate` 就返回 `the plate`，否则 `the target location`。
  - `second_necessity_intervention.py:53-57`：类似 object phrase cleanup。
- 可验证代码证据：这些函数没有基于 LIBERO task graph 或 scene metadata；只处理当前假设的命名模式。
- 可能后果：非 bowl/plate task、不同 asset 命名或多目标任务会生成错误 prompt，影响 structured/stage 模式表现。
- 事实 / 推断 / 待运行验证：
  - 事实：prompt phrase 是字符串 heuristic。
  - 待运行验证：对全 suite 生成 prompt 后人工检查。
- 建议验证方法：导出每个 task 的 original prompt、target_joint、object_phrase、goal_phrase、新 prompt，人工审计。
- 建议修复方向：从 task metadata 或人工 manifest 生成 prompt slots；把自动生成结果写入 run manifest。

### F-12: 汇总脚本遗漏部分实验，并且只理解 clean/disturbed schema

- 严重性：High
- 类别：observability / reproducibility / claim validity
- 证据文件与行号：
  - `wait_and_collect_disturbance_results.sh:11` 只遍历 `baseline_base_openvla expanded_spatial_3trials timing_step30 timing_step60 magnitude_small magnitude_large`，遗漏 `full_spatial` 和 `timing_step120`。
  - `run_full_spatial_disturbance.sh:21` 和 `run_timing_step120.sh:21` 明确会写入这两个目录。
  - `summarize_disturbance_results.py:22-35` 只按 `condition in ("clean", "disturbed")` 汇总；baseline/recovery 脚本输出字段是 `mode`，不是 `condition`。
  - `wait_and_collect_disturbance_results.sh:4` 只等待命令中含 `libero_disturbance_eval.py` 的进程，不覆盖 baseline reset/stage/second necessity 脚本。
- 可验证代码证据：summary table 不可能包含 mode-based recovery 结果；部分 disturbance run root 也不会被收集。
- 可能后果：dashboard 或论文表格可能漏实验，或误以为某些实验不存在；自动汇总无法覆盖恢复模式。
- 事实 / 推断 / 待运行验证：
  - 事实：脚本列表遗漏。
  - 事实：summarizer schema 只支持 `condition`。
- 建议验证方法：用 mock JSONL 分别包含 condition/mode 两种 schema 跑 summarizer；检查输出行数。
- 建议修复方向：配置化 run registry，支持 `condition` 与 `mode` 两类 schema；汇总输出标记 source script 和 experiment family。

### F-13: Shell 和 smoke 脚本硬编码路径、GPU、模型与缓存

- 严重性：Medium
- 类别：reproducibility / maintainability
- 证据文件与行号：
  - 所有 `run_*.sh` 都 `cd /home/lijingsu/vla` 并 source `.venv/bin/activate`，例如 `run_baseline_base_openvla.sh:3-4`。
  - GPU 固定：`run_baseline_base_openvla.sh:9` 为 GPU 1，`run_expanded_spatial_3trials.sh:9` 为 GPU 0，`run_timing_step30.sh:9` 为 GPU 2，`run_timing_step60.sh:9` 和 `run_timing_step120.sh:9` 都为 GPU 3，`run_magnitude_small.sh:9` 为 GPU 4，`run_magnitude_large.sh:9` 为 GPU 5。
  - Python smoke 脚本硬编码 `.to("cuda:0")`：`libero_base_closed_loop_smoke.py:40`、`libero_disturbance_smoke.py:36`、`run_one_probe.py:11-14`。
  - 模型路径和缓存路径硬编码在多处，例如 `disturbance_probe.py:10-18`。
- 可验证代码证据：没有统一 config/env var fallback 或 GPU availability probe。
- 可能后果：并行运行时可能抢占 GPU；在非目标机器或容器中不可复现；路径泄漏到公开仓库影响移植。
- 事实 / 推断 / 待运行验证：
  - 事实：硬编码存在。
  - 待运行验证：目标服务器当时 GPU 是否空闲。
- 建议验证方法：正式运行前记录 `nvidia-smi`、host、cwd、venv、model checksum；shell 参数化 `CUDA_VISIBLE_DEVICES`。
- 建议修复方向：统一 `.env`/YAML config 和 run manifest；shell 只做薄 wrapper。

### F-14: seed、initial state、版本与配置记录不足

- 严重性：Medium
- 类别：reproducibility / observability
- 证据文件与行号：
  - `libero_disturbance_eval.py:220` 调用 `set_seed_everywhere(args.seed)`，`270-277` summary 记录 args/checkpoint/jsonl。
  - baseline/recovery 脚本也只在 main 中设一次 seed，例如 `baseline_reset_rollback_eval.py:121`、`baseline_stage_backtrack_eval.py:115`、`second_necessity_intervention.py:122`。
  - 返回记录没有 git commit、source snapshot hash、initial state hash、model checksum、LIBERO/robosuite/MuJoCo version。
- 可验证代码证据：args 中有 seed，但 episode record 未保存 init state 内容/hash；不同 condition/mode 之间没有每 episode 重新 seed。
- 可能后果：若模型或环境存在随机性，clean/disturbed 顺序会影响 RNG state；后续无法完全复现某个 episode。
- 事实 / 推断 / 待运行验证：
  - 事实：metadata 缺失。
  - 待运行验证：当前 action inference 是否完全 deterministic。
- 建议验证方法：同一 config 重跑两次检查 action trace hash；保存 full manifest。
- 建议修复方向：为每个 episode 写 `run_id`、`source_commit_or_snapshot`、`episode_seed`、`init_state_index/hash`、`dependency_versions`。

### F-15: 关键 helper 多脚本复制，已有行为漂移风险

- 严重性：Medium
- 类别：maintainability / correctness
- 证据文件与行号：
  - AST 静态分析显示完全重复组：
    - `sim_from_env`：`baseline_reset_rollback_eval.py:36`、`baseline_stage_backtrack_eval.py:36`、`libero_disturbance_eval.py:62-63`、`second_necessity_intervention.py:37`。
    - `make_cfg`：三个 baseline/recovery 脚本。
    - `toks`：三个 baseline/recovery 脚本。
    - `choose_target_joint`：`baseline_reset_rollback_eval.py:40-49` 与 `baseline_stage_backtrack_eval.py:40-49` 完全重复；`libero_disturbance_eval.py:96-114` 与 `second_necessity_intervention.py:41-51` 是变体。
    - `move_free_joint_xy`、`save_video`、`policy_step` 在多个脚本重复。
  - 主脚本 `libero_disturbance_eval.py:74-89` 的 `move_free_joint_xy` 记录 `qpos_addr`，baseline 变体没有。
- 可验证代码证据：同一行为分散在多个文件，字段和错误处理不一致。
- 可能后果：修复 stale obs、target selection、success semantics 时容易漏一个脚本，导致实验间行为漂移。
- 事实 / 推断 / 待运行验证：
  - 事实：重复实现存在。
  - 推断：未来修复风险高。
- 建议验证方法：为所有 helper 建 behavior-preserving unit/mocked tests，再抽取公共核心。
- 建议修复方向：先抽取无行为变化的 experiment core，再逐步统一 logging/refresh/success 语义。

### F-16: smoke/probe 只能证明链路或动作敏感性，不能证明恢复有效

- 严重性：Medium
- 类别：claim validity
- 证据文件与行号：
  - `openvla_smoke.py:33-45` 可用灰图或单图做 `predict_action`，只打印 action。
  - `libero_base_closed_loop_smoke.py:44-73` 固定 `libero_10` task 0，短闭环 10 步。
  - `libero_disturbance_smoke.py:40-55` 固定 `libero_10` task 0 和 tomato sauce joint，扰动发生在 t=6。
  - `disturbance_probe.py:20-47` 画人工图像；`79-90` 只计算动作向量相对 normal 的 L2。
- 可验证代码证据：probe 图像是人工绘制，分布外；smoke task 不覆盖 LIBERO-Spatial auto target 和正式参数矩阵。
- 可能后果：这些脚本可作为环境/模型链路检查，但不能作为恢复实验成功或 target heuristic 正确的证据。
- 事实 / 推断 / 待运行验证：
  - 事实：smoke/probe 覆盖范围有限。
  - 结论：论文中只能描述为 smoke/pilot。
- 建议验证方法：将 smoke 输出归入环境健康检查，不进入主结果表；正式实验必须基于 paired rollout。
- 建议修复方向：为 smoke 增加明确 `purpose` 字段和 `not_for_paper_metric` 标记。

### F-17: 未发现明文密钥，但绝对机器路径和模型路径不宜进入公开仓库

- 严重性：Low
- 类别：reproducibility / maintainability
- 证据文件与行号：
  - secret pattern scan 没有发现密码、API key、OpenAI key、HF token 等明文密钥。
  - 绝对路径广泛存在，例如 `baseline_reset_rollback_eval.py:7-8`、`disturbance_probe.py:10-18`、多个 shell 的 `/home/lijingsu/vla`。
- 可验证代码证据：路径和模型目录是机器特定配置。
- 可能后果：公开发布时泄漏内部路径结构；他人难以复现。
- 建议验证方法：发布前跑 secret scanner 和 path scanner。
- 建议修复方向：保留默认示例路径但允许 config override；公开仓库中用占位路径。

## 3. 对重点检查项的逐项回答

1. 修改 MuJoCo `qpos` 后是否继续使用旧观测：代码证据显示多个脚本会继续使用旧 `obs`；需运行验证 wrapper 是否会隐式刷新。正式实验前应按 F-01 修复或统一记录刷新成本。
2. clean 与 disturbed 是否严格相同任务、初始状态、seed、动作预算：`libero_disturbance_eval.py` 在同一 `trial_id` 上运行 clean/disturbed，基本具备配对结构，但未记录 init state hash，也未每 episode 重置 RNG；baseline/recovery 脚本没有 clean/trial 配对。
3. reset、rollback 或重规划是否获得额外预算：`full_reset_replan` 明显获得重启预算；`oracle_rollback` 有未计入 action trace 的 dummy step；需要成本字段。
4. reward、done、success 定义是否一致可靠：目前 `success=bool(done)`，未核实 `done` 语义，未保存 `info`。
5. 自动选择扰动物体逻辑是否可能选错：可能。heuristic 不要求正分，不记录候选，需全 suite 审计。
6. 扰动发生时间是否与视频、日志 step 对齐：目前缺少统一 event/frame/action id；不能强保证。
7. prompt 切换是否晚一步或使用缓存观测：prompt 在扰动分支内切换后用于下一次 `policy_step`，但 observation 可能仍是扰动前 `obs`。
8. `oracle_rollback`、`full_reset_replan`、`verifier_stop` 能证明什么：oracle rollback 只能证明理想撤销扰动上界；full reset 是任务重启 baseline；verifier stop 是程序化安全停止基线，不能证明 verifier 无法恢复。
9. 哪些指标实际运行得到，哪些只是布尔字段：闭环脚本中的 action/reward/done/video/json 是运行产物；`verifier_vs_recovery_state_eval.py` 的能力 rate 是代码预设标签。
10. Shell 和汇总是否遗漏实验：`wait_and_collect_disturbance_results.sh` 遗漏 `full_spatial` 和 `timing_step120`，且 summarizer 只支持 clean/disturbed schema。
11. 重复实现：见 `DUPLICATION_MAP.md`。
12. 论文结论有效性：在 F-01/F-02/F-03/F-04/F-05/F-06/F-12 修复或明确边界前，不能声称 robust recovery、structured recovery architecture superiority、verifier insufficiency 的实证结论。
13. 路径、覆盖、随机种子、异常吞掉风险：路径/GPU硬编码广泛存在；输出目录 timestamp 不会覆盖同一秒外的结果但 summary latest 可能漏项；seed 和 init state metadata 不足；异常没有被捕获。
14. 秘密信息：未发现明文密钥；绝对路径和模型路径需配置化。

## 4. 最严重的五个问题

1. F-04：离线 verifier/structured metrics 是预设标签，不可作为实测能力，严重影响 claim validity。
2. F-01：扰动后 stale observation 风险可能直接改变恢复行为。
3. F-02：`success=done` 未验证可能导致核心成功率错误。
4. F-03：full reset / oracle rollback 与 current-world recovery 不公平，不能直接比较 final success。
5. F-06：target joint auto heuristic 未审计，可能扰动错误对象。

## 5. 当前不能在论文中声称的结论

在完成真实验证和修复前，不建议声称：

- “OpenVLA 扰动恢复能力已经被可靠量化”，因为 success/done、fresh obs 和 target object 仍未确认。
- “full reset replan 优于 reactive recovery”，因为它重置世界并获得额外预算。
- “oracle rollback 是现实可用恢复策略”，因为它撤销了扰动。
- “verifier-only 方法无法恢复”，因为 verifier stop 是代码分支，不是真实 verifier 能力评估。
- “structured recovery state 的各项 rate 是实测结果”，因为这些字段由脚本预设。
- “structured_reprompt_recovery 代表完整结构化恢复架构”，因为当前实现主要是 prompt 改写和 JSON 字段。

## 6. 因无运行环境无法确认的内容

- LIBERO wrapper 中 `done` 与 success 的真实语义。
- `sim.forward()` 后旧 `obs` 对象是否会在 `get_libero_image(obs, ...)` 内被隐式刷新；静态代码不能确认。
- 各 task 的 auto target joint 是否实际正确。
- hard-coded GPU 在目标服务器上是否空闲。
- 真实 videos、JSONL、summary 是否已存在且内容完整。
- OpenVLA action 是否 deterministic，以及 seed 是否足以复现 action trace。

## 7. 合规性说明

本次审计未修改任何现有 Python、Shell、配置或实验逻辑。由于本地仅有源码 tar 快照且当前目录不是 Git 仓库，无法按远端协议创建真实 `/home/lijingsu/codex-worktrees/static-audit` worktree 或提交 commit；commit hash 不可用。

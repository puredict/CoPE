# Bug And Risk Register

排序规则：先列任何正式实验前必须修复的问题，再列 dashboard 接入前、论文前和可延后工程优化。每项都给出严重性、证据、影响、建议修复方式，以及修复前是否允许正式跑实验。

## A. 任何正式实验前必须修复

| 优先级 | 问题 | 严重性 | 证据 | 对结果的影响 | 建议修复方式 | 修复前是否允许正式跑实验 |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | 扰动后可能使用 stale observation | High | `libero_disturbance_eval.py:163-166`; `baseline_reset_rollback_eval.py:88-91,109`; `baseline_stage_backtrack_eval.py:93-105`; `second_necessity_intervention.py:91-108`; `libero_disturbance_smoke.py:51-61` | 扰动后的第一步策略可能没看到新世界，恢复率和视频解释都会错位 | 统一 `refresh_obs_after_state_mutation`；所有模式同一刷新策略；记录刷新成本 | 不允许，除非只做带明确警告的 pilot |
| A2 | `success=bool(done)` 未验证 | High | `libero_disturbance_eval.py:197-208`; `baseline_reset_rollback_eval.py:115-118`; `baseline_stage_backtrack_eval.py:110-112`; `second_necessity_intervention.py:116-119` | 成功率可能把 timeout/failure termination 当 success 或反过来 | 核实 LIBERO wrapper；保存 `info`、`reward`、`termination_reason`、`timeout`、`success_source` | 不允许 |
| A3 | target joint auto heuristic 可能选错 | High | `libero_disturbance_eval.py:96-114`; `baseline_reset_rollback_eval.py:40-49`; `baseline_stage_backtrack_eval.py:40-49`; `second_necessity_intervention.py:41-51` | 扰动对象可能与任务无关，导致 disturbed/recovery 结论无效 | 生成全 suite candidate table；人工或 metadata 审计；正式 run 使用 manifest | 不允许 |
| A4 | full reset / oracle rollback 与 current-world recovery 不公平 | High | `baseline_reset_rollback_eval.py:93-108`; `baseline_reset_rollback_eval.py:82,99,118` | reset/rollback 消除扰动并获得未计费预算，不能与 reactive/prompt success 直接比较 | 把二者标记为 restart/upper-bound；记录 total env steps/action steps/dummy steps；分表汇报 | 不允许把它们纳入同一 performance ranking |
| A5 | baseline/recovery 脚本缺少 clean/trial 配对 | High | `baseline_reset_rollback_eval.py:76,126-131`; `baseline_stage_backtrack_eval.py:86,120-125`; `second_necessity_intervention.py:82,127-132` | 无法与 clean 或多 trial disturbed 结果做严格配对比较 | 为所有 modes 增加 `trial_id`、init state hash、paired clean/reactive records | 不允许做正式统计比较 |
| A6 | `verifier_vs_recovery_state_eval.py` 指标是预设字段 | Critical | `verifier_vs_recovery_state_eval.py:63-76,79-115,151-170` | 若当作实测结果，会直接造成论文 claim invalid | 重命名为 diagnostic labels；从主结果表剥离；真实 verifier 另行实现 | 不允许作为实验结果使用 |
| A7 | 汇总脚本漏实验且 schema 不完整 | High | `wait_and_collect_disturbance_results.sh:11`; `run_full_spatial_disturbance.sh:21`; `run_timing_step120.sh:21`; `summarize_disturbance_results.py:22-35` | 结果表可能遗漏 `full_spatial`、`timing_step120`，且不能汇总 mode-based baselines | 配置化 run registry；支持 `condition` 和 `mode` schema；检测空输入 | 不允许用当前自动汇总作为正式表格来源 |
| A8 | 缺少 timeout/exception/partial result schema | Medium | `libero_disturbance_eval.py:157-195`; `baseline_reset_rollback_eval.py:83-118`; `baseline_stage_backtrack_eval.py:92-112`; `second_necessity_intervention.py:87-119` | 失败原因不可解释，长实验中断后 summary 可能缺失 | episode-level try/finally；保存 status、exception、partial action trace | 不建议 |
| A9 | seed/init state/version metadata 不足 | Medium | `libero_disturbance_eval.py:220,270-277`; `baseline_reset_rollback_eval.py:121`; `baseline_stage_backtrack_eval.py:115`; `second_necessity_intervention.py:122` | 难以复现 episode；不同模式 RNG 状态可能不一致 | 保存 source snapshot/commit、dependency versions、episode seed、init hash、model checksum | 不建议 |

## B. Dashboard 接入前必须修复

| 优先级 | 问题 | 严重性 | 证据 | 对 dashboard 的影响 | 建议修复方式 | 修复前是否允许接入 dashboard |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | 没有统一事件、action、frame id | Medium | `libero_disturbance_eval.py:166-185`; `baseline_stage_backtrack_eval.py:93-108`; `second_necessity_intervention.py:91-114` | UI 很难准确标注扰动、prompt 切换、policy action 和视频帧 | 统一 event log：`env_step`、`policy_step`、`frame_id`、`event_type`、`prompt_id`、`obs_source` | 不允许接真实 dashboard |
| B2 | 模式逻辑散落在多个 rollout 脚本 | Medium | `rollout` 分别在 `libero_disturbance_eval.py:125-214`; `baseline_reset_rollback_eval.py:72-118`; `baseline_stage_backtrack_eval.py:82-112`; `second_necessity_intervention.py:78-119` | dashboard 控制 start/pause/step/disturb/recover 时容易与 batch 脚本行为漂移 | 抽取 experiment core 和 mode strategy，但先做行为保持测试 | 不允许接正式 dashboard |
| B3 | prompt 和 recovery state 来源没有显式 provenance | Medium | `baseline_stage_backtrack_eval.py:98-104`; `second_necessity_intervention.py:97-107` | UI 可能把 oracle/program fields 展示为模型判断 | 每个 recovery field 加 `source=oracle/code/model/human` | 不允许展示为自动系统 |
| B4 | 硬编码 GPU、路径、模型缓存 | Medium | 多个 shell `:3-12`; `libero_base_closed_loop_smoke.py:22,40`; `libero_disturbance_smoke.py:22,36`; `disturbance_probe.py:10-18` | dashboard worker 可能抢 GPU 或指向错误模型 | 用 config/env/runtime manifest；启动前检查 GPU 和模型路径 | 不建议 |
| B5 | 没有安全停止与异常状态统一输出 | Medium | 评测脚本没有统一 `status` 字段；`verifier_stop` 是模式内 break | UI 无法区分 stop、success、failure、timeout、exception | 统一 episode lifecycle state machine | 不允许接真实环境控制 |

## C. 论文前必须补充

| 优先级 | 问题 | 严重性 | 证据 | 对论文的影响 | 建议补充 | 修复前是否允许论文声称 |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | trial 数和置信区间不足风险 | High | 多个 run shell 为 `--trials 1`，仅 `run_expanded_spatial_3trials.sh:15` 为 3 | 1-3 trial 只能是 pilot，不能支撑稳定结论 | 多 task、多 trial、置信区间、失败分类 | 不允许强结论 |
| C2 | structured recovery 命名过强 | Medium | `second_necessity_intervention.py:72-76,97-107`; `baseline_stage_backtrack_eval.py:98-104` | 容易把 prompt-only ablation 写成架构贡献 | 改称 oracle/semi-oracle prompt recovery；增加真实 state estimator 后再升级 claim | 不允许称完整架构 |
| C3 | verifier stop claim 过强 | Medium | `baseline_stage_backtrack_eval.py:95-97`; `second_necessity_intervention.py:93-96` | 不能证明 verifier-only 失败，只能证明 programmed stop 不完成任务 | 实现真实 verifier 或改名 oracle event stop | 不允许称 verifier limitation 实证 |
| C4 | smoke/probe 不能进入主性能结果 | Medium | `disturbance_probe.py:20-90`; `libero_disturbance_smoke.py:40-55` | 分布外人工图或固定 tomato sauce task 会被误读 | 只放 appendix/environment sanity；主结果用 paired rollout | 不允许作为 performance evidence |
| C5 | 缺少视频/JSON/config 可追溯 manifest | Medium | 当前记录有 `video_path`、`actions`、`args`，但缺少 source commit/init hash/version | 审稿人难以复核 episode | 每个 run 输出 manifest、raw event log、annotated video map | 不建议提交论文 |

## D. 可延后工程优化

| 优先级 | 问题 | 严重性 | 证据 | 影响 | 建议 |
| --- | --- | --- | --- | --- | --- |
| D1 | helper 大量重复 | Medium | AST 重复组：`sim_from_env`、`make_cfg`、`toks`、`move_free_joint_xy`、`save_video`、`policy_step` | 修复容易漏脚本 | 先抽取无行为变化 helper，再回归比较 |
| D2 | Shell wrappers 重复且参数硬编码 | Low/Medium | 所有 `run_*.sh` 结构近似相同 | 难维护，易漏汇总 | 用 YAML/CSV experiment matrix 生成命令 |
| D3 | `shellcheck` 未安装，Shell 未静态检查 | Low | `which shellcheck` 退出码 1 | 潜在 quoting/portability 问题不能自动发现 | 在环境允许时安装或 CI 使用 shellcheck |
| D4 | download scripts 无 guard | Low | `download_openvla.py:1-8`; `download_openvla_libero_spatial.py:1-8` | 容易误触发大下载 | 加显式 CLI、目标目录检查、dry-run |
| D5 | 源码未组织为 package/测试体系 | Medium | 平铺脚本，无测试目录 | 难做 mock regression | 建立 package、mock env tests、static CI |

## Top 5 立即整改清单

1. 实现并验证扰动后 fresh observation，统一所有脚本。
2. 核实并改造 success / done / reward / timeout / exception schema。
3. 审计并固定 target joint manifest。
4. 重做 paired experiment matrix，记录 task/trial/init hash/seed/cost。
5. 把 `verifier_vs_recovery_state_eval.py` 与 full reset/oracle rollback 从主 performance claim 中隔离。

## 修复前实验许可建议

- 允许：环境链路 smoke、py_compile、mock event logging、candidate target listing、dashboard mock backend。
- 只允许标注为 pilot：少量真实 rollout，用于验证 fresh obs、success semantics、target selection。
- 不允许：用于论文或对外 dashboard 的正式 success-rate comparison。

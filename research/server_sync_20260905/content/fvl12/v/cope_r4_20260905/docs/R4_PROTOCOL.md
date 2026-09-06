# R4 第一轮：接口、状态语义与容量诊断协议

本轮保留 CoPE 的固定研究假设：通过编辑持久任务承诺恢复长期机器人任务。修改接口与诊断程序后重新运行，目的是区分模型接口错误、完整状态的序列化成本、状态恢复错误和物理执行失败。R3 原始输出保留；每次 R4 调用使用新目录。本文件描述第一轮已经纳入代码的范围，并明确第二轮尚未实现的实验。

## 任务与比较范围

第一轮沿用 R3 三种结构：`calibration` 为 8 个初始 slots、深度 2、7 个事件；`lineage_valid` 为 10 个 slots、深度 6、11 个事件；`long_lineage` 为 48 个 slots、深度 6、11 个事件。根订单的计划是 butter 到 B、milk 到 A、yogurt 到 A。临时版本具有自己的完整 continuation；最深临时版本与根的第一步都为 butter 到 B，但后续动作不同。

输入包含完整当前状态、当前结构化事件、历史、任务契约、完成记录、世界状态和计算预算。CoPE 输出类型化生命周期操作；FSR-PC 输出完整状态。两者使用同一模型、服务配置、采样配置和每条件统一预算。类型 schema 约束合法操作和字段，但不得把某事件的正确操作或正确恢复目标写入动态 schema，从而替模型选择答案。

当前 `restore_root` 事件明确给出恢复根的要求，状态也公开 `root_id`。通过该任务只说明系统能按明确事件维护谱系和绑定的后续计划；不能直接宣称模型自行识别了应恢复的承诺。第一轮 seeds 仍主要改变 nonce 和 receipt code，不能将 20 个 seeds 当作 20 种因果任务结构。

## 划分与运行顺序

开发 seeds 固定为 1000、1001，正式 seeds 保留 0--19，二者不重叠。原名 `calibration` 仅表示较小的结构规模，并不天然意味着开发集；划分由 seed 和运行用途共同决定。原 R3 的正式 seeds 已有部分结果可见，因此 R4 是修订后的诊断性复跑，不能伪称完全未见的确认性检验。未来论文确认性实验应另行冻结新测试 seeds 和任务结构。

先执行独立状态参考与执行器性质测试，再检查四种生命周期接口以及完整七事件开发轨迹。容量审计必须覆盖全部 profile、开发 seed 与事件。使用独立参考状态逐步生成正确前置状态的审计只测量容量；连续模型实验必须保留各方法自己提交的状态，不能在每步用参考状态纠正模型。

充分预算冻结后才能启动该预算下的模型轨迹。困难 profile 的 JSON 错误、超时和语义错误属于结果，不能用“每种方法先达到 80%”的门槛筛除。单独的无 LLM 物理 controller gate 可保留 8/10，用于确认操控底座是否正常；它不是方法性能筛选。

## Token 容量与两类预算

`scripts/audit_r4_capacity.py` 使用本地固定 Qwen tokenizer 的 `apply_chat_template`，包括各方法 system prompt、完整 user packet、assistant prefix，并设置 `enable_thinking=False`。不得使用字符数除以四估算真实 tokens。

每个事件记录完整 prompt tokens、独立合法参考输出的 pretty 与 compact tokens、对应输入加输出容量、原 4096 输出上限是否容纳该参考文本、服务实际上下文上限，以及为全局输出预算预留空间后是否可发送请求。compact 参考仍不是所有合法 JSON 写法的数学最小值；超出预算应报告为“该合法紧凑参考超预算”。

固定预算沿用每事件 1 次调用、4096 输出 tokens、90 秒。充分预算的输出上限由全部开发参考文本中最大的 pretty/compact token 数加 15% 余量，向上取整到 1024 的倍数，一次确定一个全局值；所有方法和 profile 共用，不按测试答案逐例调整。

充分预算的 timeout 必须来自同一服务配置下真实、暖机后、串行且成功完成的开发请求。至少覆盖两种方法、至少两条 FSR-PC 成功记录，并包含达到容量审计最大输入长度 90% 的代表性长 prompt。记录实际 TTFT、总耗时、输出 tokens、finish reason 和服务身份。诊断脚本采用最慢观测 decode tokens/s 与最大 TTFT 估算全局输出预算用时，加 1.5 倍余量后向上取整至 30 秒。该值是有证据的保守外推，不是保证；若观测支持不足则保持 pending。

任何充分预算冻结都要验证 `prompt_tokens + global_max_output_tokens <= actual_max_model_len`。模型宣传的上下文长度不能代替服务启动的实际上限。若 32768 无法满足，只能明确调整并记录服务配置，或报告该条件不可容纳；不能偷偷缩小合法输出或更换任务规模。服务精度、TP、eager、并发和模型 revision 变化后，既有吞吐测量不能直接复用。

原配置的充分预算故意为 `pending`，runner 必须拒绝把 null 或未冻结值用于正式运行。容量脚本不发送模型请求、不访问服务器，也不自动下载 tokenizer。示例命令：

```bash
python scripts/audit_r4_capacity.py \
  --tokenizer /absolute/path/to/local/Qwen3-32B/snapshot \
  --max-context-tokens ACTUAL_SERVER_LIMIT \
  --out /absolute/path/to/new/capacity_directory
```

需要冻结时，再提供 `--throughput-measurements` 和一个不存在的 `--freeze-config` 路径。吞吐文件是 JSON 对象，含 `server` 和 `samples`。server 记录 `model`、`model_revision`、`tensor_parallel_size`、`dtype`、`enforce_eager`、`max_model_len`、`concurrency`；samples 含 `method`、`profile`、`seed`、`event_ordinal`、`prompt_tokens`、`completion_tokens`、`latency_s`、`ttft_s`、`warmed`、`status`、`finish_reason`。失败请求也应保留，timeout 外推只使用符合条件的真实成功样本。

## 独立正确性与评分

独立参考转换不得调用 CoPE 核心 updater 或 `oracle_patch`；以独立字典实现和预期性质检查暂停恢复、嵌套覆盖、根恢复、未涉及订单不变、完成记录保存、原子失败和过期 revision 拒绝。精确比较只是一个诊断，还必须直接检查根 occurrence、continuation、生命周期前缀和图结构。

运行时每个事件分别记录请求完成、JSON/schema 合法、候选状态结构有效、候选语义正确、是否提交及提交后局部转换正确性。这里 `semantic_match_to_registered_transition`、`candidate_semantic_correct`、`committed_state_semantic_correct` 以及相关错误计数，都以本方法实际前态为参考输入；若更早已有错误，后续局部转换正确仍可能继承该错误。因此这些字段不能单独证明全局轨迹正确。

完整轨迹结论另需 `scripts/audit_r4_trajectory.py`：从已保存的初始场景和事件独立重建 gold，逐次比较实际提交状态，并核验指纹链、最终根 occurrence、continuation、生命周期历史、图结构及未涉及记录。审计结果单独保存，不能覆盖原始输出或替换模型状态；局部正确与全局正确不一致时须同时报告。恢复对象及计划的逐步细分属于该离线审计，不能声称旧运行日志本身已包含这些独立字段。合法但语义错误的更新不能被参考答案自动纠正；候选错误、校验器拦截和已提交损坏应独立报告。提交后损坏为零可能来自执行器拒绝机制，不能替代模型候选准确率。

历史兼容字段 `adaptation_status=schema_validation_failure` 也可能来自状态转换校验器；须结合 `output_schema_valid`、`failure_stage` 和 `validation_errors` 判断。JSON/schema 已通过而谱系不变量被拒绝，应报告为状态转换校验失败，不能称为 JSON 格式错误。

每个 episode 的主分母为该条件全部已启动 episode，失败不剔除；完整计划的分母和实际完成数同时报告。成对比较必须报告缺失/未启动配对。若一方法在第 3 事件终止、另一方法到第 4 事件，原始单步成功数的分母不同，不能直接比较比例。失败得早导致耗时较短也不能解释为成功完成更快。

第一轮仍在所有事件完成后才执行三次抓放。物理阶段未执行时应为 `physical_attempted=false`、`physical_success=null`、`end_to_end_success=false`；这不是一次抓取失败。状态语义通过与实际物理执行成功分别报告。LIBERO geometry-oracle controller 支持的结果只能说明该操控底座下的任务管理能力，不能推断 VLA 能力。

客户端超时记录 request id、已有输出、首 token 时间、总耗时、已收到 tokens/最终 usage、finish reason、取消操作和服务端状态。仅关闭客户端连接时应记录“连接已关闭，服务端停止尚未确认”，不能宣称取消成功。正式串行请求之间要确认服务无残留请求，避免超时后后台生成干扰下一方法。

## 结果能够支持的结论

充分预算下两者正确而固定预算下 CoPE 更好，支持序列化效率与预算适应性。充分预算下 CoPE 仍更正确，才开始提供状态维护可靠性的证据，但仍受到结构化事件和固定场景限制。接口修复后的完整七事件通过只是开发接通证据，不等价于全部困难条件通过。

## 第二轮计划，尚未实现

需要增加 Generic Patch（例如 JSON Patch）来区分普通局部编辑的收益与类型化生命周期语义的收益，并保证信息和可表达变化相等。共享存储只应维护机械可推导字段，不能为某方法补出恢复答案。

随后增加恢复上一层、指定 occurrence、撤销指定分支、过期通知不复活等不同正确恢复目标；改变相关订单、目标绑定和完成位置。把历史 slots、嵌套深度、中断循环拆成独立维度。最后加入“先完成一个动作、再中断、恢复后只执行剩余动作”的物理闭环。未实现这些条件前不得声称已检验 Generic Patch、复杂恢复选择或真实动作边界的长期恢复。

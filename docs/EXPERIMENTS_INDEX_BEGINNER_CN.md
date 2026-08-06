# CoPE 实验地图（小学生版）

## 一句话结论

CoPE 像“只改作业本里的一张便签”，完整重规划像“重新抄整本作业”。
实验说明小便签更短、更快，也更容易保护历史；但是把普通稀疏补丁的
说明写清楚后，它在最终实验中和 CoPE 一样正确。

当前不能声称“CoPE 比公平普通补丁更准”。当前可以继续验证的方向是：
在正确率不变差的前提下，CoPE 是否能稳定减少输出、token、延迟和历史
损坏。

## 第一次打开仓库只看这些

1. 最终关键实验：
   [`research/167_OCCURRENCE_CONFIRMATORY_V3_RESULT_AND_CLAIM_DECISION.md`](../research/167_OCCURRENCE_CONFIRMATORY_V3_RESULT_AND_CLAIM_DECISION.md)
2. 下一项关键实验草案：
   [`research/168_NEXT_CRITICAL_EXPERIMENT_NONINFERIORITY_PREREG_DRAFT.md`](../research/168_NEXT_CRITICAL_EXPERIMENT_NONINFERIORITY_PREREG_DRAFT.md)
3. v1 为什么看起来大胜、但不公平：
   [`research/164_OCCURRENCE_V1_RESULT_AND_CONTRACT_EXPLICIT_V2_PREREG.md`](../research/164_OCCURRENCE_V1_RESULT_AND_CONTRACT_EXPLICIT_V2_PREREG.md)
4. v2 的路径歧义：
   [`research/165_OCCURRENCE_CONTRACT_EXPLICIT_V2_RESULT.md`](../research/165_OCCURRENCE_CONTRACT_EXPLICIT_V2_RESULT.md)
5. 状态变大时完整重写为什么会坏：
   [`research/formal_experiment_gate_2026-08-02/42_PERSISTENT_STATE_SCALING_RESULT.md`](../research/formal_experiment_gate_2026-08-02/42_PERSISTENT_STATE_SCALING_RESULT.md)
6. 机器人恢复实验：
   [`research/fresh_state_recovery_2026-08-01/17_MAX60_RESULT.md`](../research/fresh_state_recovery_2026-08-01/17_MAX60_RESULT.md)

## 文件分成四种

### 1. 真正跑过的实验

通常同时含有：预注册、案例 CSV、运行日志、结果报告和 SHA256。重要目录
包括 `fresh_state_recovery_*`、`oracle_*`、`semantic_*`、
`formal_experiment_gate_*`、`native_output_*` 和
`occurrence_confirmatory_v3/`。

### 2. 只做了 CPU/oracle 检查

这些证明代码、验证器或接口能工作，但不证明大模型或机器人更聪明。
报告会明确写 `CPU`、`oracle`、`preflight`、`capability` 或
`structural integration`。

### 3. 计划和审稿人检查

大量 `PREREG`、`PROTOCOL`、`PLAN`、`AUDIT`、`REVIEWER` 文件是实验设计
和挑错记录，不是实验成功率。它们被保留是为了证明没有看到结果后偷偷
改规则。

### 4. 已作废但保留的旧结果

出现 `SUPERSEDED`、`LEGACY`、`V1 FAILURE`、`CORRECTED` 的文件不能单独
引用。它们用于说明哪里出过错。优先看编号更高、明确写
`authoritative` 或 `current decision` 的报告。

## 最终 occurrence 对照

| 方法 | v3 正确数 |
|---|---:|
| CoPE | 40/40 |
| 公平中性稀疏补丁 | 40/40 |
| Governed delta | 0/40 |
| FSR-PC 完整状态 | 31/40 |
| Full replan | 37/40 |

CoPE 与公平普通补丁正确率打平，但 CoPE 的答案平均约小 84%，平均生成
延迟约快 3.8 倍。因此原来的“可靠性优越”门是 NO-GO，效率/非劣效方向
仍然值得继续。

## 什么已经证明

- 状态修改可以原子提交：全部成功或完全不动。
- 错误状态能够被独立验证器拦住。
- 同名任务反复出现时必须区分第几次 occurrence。
- 状态越大，重新生成整份状态越容易丢历史。
- 稀疏修改比完整重写更稳定。
- CoPE 能用很短的输出表达一次持久承诺修改。

## 什么还没有证明

- CoPE 比公平普通稀疏补丁更准确。
- CoPE 普遍比 full replan 成功率高。
- 一个模型的结果能推广到其他模型。
- 已经在多个机器人任务上稳定成功。
- 当前材料已经足够支撑 ICRA 方法论文。

## 目录速查

- `cope/`：CoPE 状态、操作、验证和事务代码。
- `experiments/`：实验运行器。
- `tools/`：分析器、审计器和 manifest 生成工具。
- `tests/`：代码回归测试；测试通过不等于论文假设通过。
- `research/`：预注册、结果、失败记录和决策报告。
- `manifests/`：冻结的实验案例和调用顺序。
- `schemas/`：输入输出数据结构。

服务器外部的运行缓存、凭据环境、模型 checkpoint 和本地 PDF/ZIP 不在
GitHub 同步范围内。GitHub 保存的是已经审计并进入 Git 历史的代码与实验
证据。

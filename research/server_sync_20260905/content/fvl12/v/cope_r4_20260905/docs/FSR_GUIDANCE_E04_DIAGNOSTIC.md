# Guidance 条件下 FSR-PC 第 4 个事件的状态一致性失败

检查日期：本地任务日期 2026-09-04；服务器日期 2026-09-05。

本次失败发生在**完整输出之后的状态转换校验**。模型在预算内生成了合法 JSON，输出 schema 校验也通过；但是它把第二层临时任务挂到了错误的父任务，并没有覆盖真正的当前任务。校验器拒绝了候选状态，持久状态未被修改，物理阶段未执行。

## 证据范围

只读检查服务器 `fudan-26575` 下的以下目录：

```text
/home/lijingsu/cope_outputs/cope_r4_dev_guidance_fixed_cal_1000_20260905/calibration/FSR-PC/seed_1000
```

使用的原始证据为 `raw_outputs/event_04.txt`、`events.jsonl`、`state_snapshots.jsonl`、`model_calls.jsonl` 和 `result.json`。没有修改提示词、schema、运行代码或实验结果。

第 4 次请求的识别信息：

```text
event_id: seed-1000/e04
request_id: da7b26da-f908-40bd-b61d-bb7ca5443ac6
raw output SHA-256:
f76aaea71727006787995f67e6fcc761cc63b621c430cb50f5ad41a2790f99bd
```

## 事件要求与第 3 步后的真实状态

为简化表述，下文的 `root`、`detour-01`、`detour-02` 都带有完整前缀 `order-critical/`。

前 3 步已经完成：暂停根任务、恢复根任务、用第一层临时任务覆盖根任务。进入第 4 步时，持久状态 revision 为 3：

```text
root: overridden, depth 0
└── detour-01: active, depth 1
```

第 4 个输入事件明确指定：

```json
{
  "event_id": "seed-1000/e04",
  "kind": "override_current",
  "current_slot_id": "order-critical/detour-01",
  "new_slot": {"slot_id": "order-critical/detour-02"}
}
```

这里仅摘录定位任务关系所需的字段；真实事件的 `new_slot` 包含完整 payload、grounding、logical_id 和 priority。第二层临时任务的计划是 butter→basket_B、milk→basket_B、yogurt→basket_C。

正确转换应为：把 `detour-01` 改成 `overridden`，在它的 `child_ids` 中加入 `detour-02`，给它追加一次当前事件的 `Override` 历史；新任务 `detour-02` 处于 `active`，父节点为 `detour-01`，深度为 2。已经被覆盖的 `root` 保持不变。

这些要求直接写在 [prompts.py:98](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/prompts.py:98)。独立参考实现也分别在 [reference.py:67](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/reference.py:67) 更新当前节点，在 [reference.py:78](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/reference.py:78) 设置新节点的父节点与深度。此次诊断没有把参考状态写回运行中的方法状态。

## 模型实际输出了什么

模型没有修改 `detour-01`，而是再次修改了 `root`：

| 字段 | 正确候选值 | 实际候选值 |
| --- | --- | --- |
| `detour-01.mode` | `overridden` | `active` |
| `detour-01.lineage.child_ids` | `[detour-02]` | `[]` |
| `detour-01.history` | 在原有 1 条记录后追加 e04 的 `Override`，长度为 2 | 原有 1 条记录完全未变 |
| `root.lineage.child_ids` | 保持 `[detour-01]` | 变成 `[detour-01, detour-02]` |
| `root.history` | 保持原有 4 条记录 | 追加 seq=5、event=e04、operation=`Override` |
| `detour-02.lineage.parent_id` | `detour-01` | `root` |
| `detour-02.lineage.depth` | 2，与父节点 depth=1 一致 | 2，但所填父节点 `root` 的 depth=0 |
| `detour-02.mode` | `active` | `active` |

错误的关键不是新任务 payload 复制失败。逐字段比较显示，事件提供的新任务 `slot_id`、`logical_id`、`priority`、`grounding`、`payload` 五项全部被精确复制。四个 archived order 和三个 safety slot 也完全未变；旧 `detour-01` 整个 slot 与输入完全一致。已有节点中只有 `root` 的 `history` 和 `lineage` 被修改。

因此可以把这次错误准确描述为：**在嵌套 override 中，模型将更新作用对象和新节点父节点错误地绑定到 root，而不是事件明确指定的 detour-01。** 它同时保留了“第二层深度为 2”，造成父节点与深度不一致。这是对输出结构的观察，不是对模型内部推理过程的断言。

错误候选中有两个活跃任务：

```text
root: overridden, depth 0
├── detour-01: active, depth 1       ← 应被本次 override 覆盖，却保持活跃
└── detour-02: active, depth 2       ← parent=root，但 depth 又写成第二层
```

## 为什么输出 schema 通过，状态校验却拒绝

结构化输出 schema 约束字段存在、字段类型、模式枚举等，见 [schemas.py:27](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/schemas.py:27)。`active`、`overridden`、整数 2 和字符串父节点 ID 都是合法字段值。静态 schema 不负责跨 slot 查询父节点深度，也不根据事件替模型选择应该覆盖哪个任务。因此这份候选可以同时满足 JSON/schema 约束而违反状态一致性。

`validate_regenerated_transition` 首先调用通用状态校验，见 [state.py:283](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/state.py:283)。实际返回两个错误：

```text
critical workflow must have exactly one live carrier, got 2
order-critical/detour-02: depth differs from parent depth + 1
```

第一项来自 [state.py:135](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/state.py:135)：同一 critical workflow 中，`active` 或 `suspended` 的 carrier 必须恰好一个；实际 `detour-01` 与 `detour-02` 都为 `active`。

第二项来自 [state.py:103](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/state.py:103)：子节点深度必须等于其父节点深度加一；实际填写的是 parent=`root`、parent.depth=0、child.depth=2，因此不相容。

父子边的反向引用检查本身没有报错，因为模型错误地把 `detour-02` 同时加入了 `root.child_ids`，与错误的 `parent_id=root` 相互对应。真正暴露问题的是活跃 carrier 数和深度约束；不能把“两条边互相对应”误读成任务谱系正确。

## 失败阶段、预算和提交结果

| 记录字段 | 实际值 | 含义 |
| --- | --- | --- |
| `generation.ok` / `generation.status` | `true` / `ok` | 生成请求成功返回 |
| `request_completed` / `finish_reason` | `true` / `stop` | 收到完整结束，而非超时截断 |
| `json_parse_success` | `true` | JSON 可解析 |
| `output_schema_valid` | `true` | 输出 schema 校验通过 |
| `completion_tokens` | 2166 | 小于本次输出上限 4096 |
| `latency_s` | 62.774700 | 小于本次 90 秒上限 |
| `ttft_s` | 2.673011 | 客户端观测的首输出时间 |
| `failure_stage` | `transition_validation` | 失败发生在候选状态转换校验 |
| `candidate_rejected_by_transition_validator` | `true` | 候选被拦截 |
| `state_committed` | `false` | 没有提交候选状态 |
| `physical_attempted` / `physical_success` | `false` / `null` | 没有执行物理阶段 |

日志沿用的 `adaptation_status="schema_validation_failure"` 名称较宽泛，容易造成误解：在 [adapters.py:118](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/adapters.py:118)，状态转换校验拒绝也复用了这个旧名称。此处应依据 `failure_stage`、`generation.ok` 和 `output_schema_valid` 分类，不能写成“JSON 生成错误”或“输出 schema 失败”。`candidate_semantic_correct=null` 表示这条拒绝路径没有继续记录独立语义评分，并不表示候选已被证明正确。

候选输出自身 revision=4，但被拒绝后的持久状态仍为 revision=3。快照 `after_event_03` 与 `rejected_after_event_04` 的完整 state 对象相等，且二者 fingerprint 均为：

```text
dcbb2b1ca8ecb4249fda4fb91c489b7e83cfcb106c854b4057680642f0ff4e04
```

这与 [runner.py:165](/Users/lijingsu/Documents/cope/research/cope_fsrpc_r4/code/cope/lineage_benchmark/runner.py:165) 的拒绝后保留状态、写出证据并停止 free-running episode 的路径一致。

## 结果能够说明什么

切换到 guidance 后，这条轨迹已越过此前的接口/运行时阻塞，观察到了第二层 override 的真实候选状态错误。该事件在 62.8 秒内完成，输出 2166 tokens，因此这次具体失败不是超过 90 秒、超过 4096 tokens，或服务器只返回了半段答案。

它说明在这条开发轨迹中，FSR-PC 的完整状态重写没有正确保持“当前被覆盖 occurrence—新 occurrence”的关系，且确定性校验器成功阻止了错误状态提交。没有执行物理动作，所以不能归因为机器人抓放失败。

这只是一个开发 seed 的第 4/7 个事件、第二层嵌套 override。它不足以证明失败普遍由任务长度、模型记忆或某个提示词细节引起，也不足以给出方法总体优劣结论。要判断长度或深度的因果作用，仍需固定其他因素的对照。当前可以确定的是：**这个样例的直接失败点是更新对象与谱系关系错误，而不是资源预算耗尽。**

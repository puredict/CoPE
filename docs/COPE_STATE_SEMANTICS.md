# CoPE Persistent Constraint State Semantics

状态：schema `1.0`

## Scope

`cope` 包实现持久 constraint identity、typed patch、显式 revalidation guard、guarded restoration、原子提交、canonical serialization 和 deterministic replay。它是 CPU-only 的状态语义层，不执行机器人策略，也不证明 CoPE 能提高 LIBERO/OpenVLA 的任务成功率。

所有已接受的状态变更只能通过：

```python
apply_patch(state, patch, context) -> TransitionResult
```

`ConstraintState`、slot、patch、history 和嵌套 JSON 值均被冻结。调用方可以构造初态、patch 或用于负测试的候选对象，但不能就地修改已接受状态；反序列化和下一次 patch 均重新检查 schema、graph 和 hash。

## Data model

`ConstraintSlot` 包含稳定的 `slot_id`、结构化 `content`、`source`、`mode`、`priority`、创建/更新 event、parent/override edge、完整 lineage、evidence refs 和 metadata。

允许的 source：

- `task`
- `user`
- `safety`
- `perception`
- `planner`
- `system`

允许的 mode：

- `active`
- `suspended`
- `overridden`
- `demoted`
- `expired`

root slot 的 lineage 必须是 `(slot_id,)`。derived slot 的 lineage 必须严格等于 parent lineage 加自身 ID。lineage 和 override graph 都不允许 cycle 或 dangling reference。

`ConstraintState` 包含：

- `schema_version`
- `state_id`
- 严格单调的 `revision`
- immutable `slots`
- append-only `event_history`
- append-only `patch_history`
- append-only `validation_history`
- `state_hash`

`Patch.created_at` 是非负整数 logical timestamp，不是 wall-clock timestamp。engine 不创建或 hash wall-clock 时间。

## Typed operations

### Insert

创建永久 ID 的 active slot。重复 ID、缺 lineage、错误 event ID 或通过 Insert 偷建 override edge 都会被拒绝。

### Suspend

只把 active/demoted slot 转成 suspended。slot ID、content、source 和历史不变；原因、trigger event 和 operation 完整记录在 patch/event history。

### Override

保留旧 slot，并创建一个 active replacement。v1 要求：

- replacement 是新 ID；
- parent 是旧 slot；
- lineage 是旧 lineage 加新 ID；
- replacement 只有一条指向旧 slot 的 override edge；
- replacement priority 不低于旧 slot；
- 对旧 slot source 和 priority 具有明确授权。

旧 user constraint 的 source 不会被 planner replacement 覆盖或删除。

### Demote

保留 slot，只把 priority 严格降低并进入 demoted mode。若该 slot 正在 override 其他 slot，不能降到 target priority 以下。

### Revalidate

只允许 suspended/overridden slot。`revalidate_slot` 执行显式 validator，并根据以下输入产生稳定 validation ID：

- `state_id`
- `slot_id`
- `validator_id`
- evidence
- boolean result
- slot 的 `last_updated_event_id`

成功和失败结果都能作为 Revalidate patch 写入 append-only validation history。

### Restore

只允许 suspended/overridden slot，并且必须引用：

- 同一 slot 的 validation；
- `result=true`；
- 仍匹配当前 `last_updated_event_id` 的 validation；
- 不与 active overriding slot 冲突的 validation。

Restore 后 slot ID 不变，validation ID 加入 `evidence_refs`。未知、失败、stale 或属于其他 slot 的 validation 均不能授权恢复。

### Expire

保留 tombstone 和 lineage，将 slot 永久置为 expired。expired slot 不能 Revalidate 或 Restore。世界中出现语义相似但已变化的 constraint 时，必须 Insert 新 slot，并通过 parent/lineage 指回旧 slot。

## Authority model

`PatchContext` 显式记录：

- actor 和 `authority_priority`
- 可变更的 `authorized_sources`
- safety override 是否单独授权
- oracle/detected event source
- information/policy/high-level-call budgets
- pair key、task progress、manual intervention 和实验版本字段

Insert/Override replacement 也必须检查 asserted source 和 asserted priority 的权限；调用方不能凭空冒充 user/safety source 或创建高于自身 authority 的 slot。会削弱或替换 constraint 的 Suspend、Override、Demote、Expire 都检查 source authorization 和 authority priority。safety slot 还要求 `allow_safety_override=true`。v1 不允许任何低 priority replacement override 高 priority target，即使 caller 具有其他权限。

`PatchContext` 是 engine 外部 trust boundary：正式 runner 必须由受信 controller 创建它，不能直接接受 planner/model 输出的 authority 字段。`PatchContext.trusted()` 只用于 genesis/bootstrap、测试或已验证 history 的受控工具，不应暴露给非受信 patch generator。

## Public API

```python
from cope import (
    ConstraintState,
    Patch,
    PatchContext,
    apply_patch,
    canonical_state_hash,
    deserialize_state,
    replay,
    revalidate_slot,
    serialize_state,
    validate_state,
)
```

### `apply_patch(state, patch, context) -> TransitionResult`

唯一 mutation boundary。先验证 input hash/history，再在隔离的临时状态应用全部 operations，最后统一验证并提交。任一 operation 失败会返回：

- `accepted=False`
- 原 state object
- 相同的 before/after hash
- 空 `applied_operation_ids`
- 稳定 `rejection_code`
- 不含 private reasoning 的结构化 audit record

### `validate_state(state) -> ValidationReport`

检查 schema version、revision/history 对齐、reference、lineage/override graph、priority consistency、validation reference、canonical hash，并从空 genesis 重放 append-only patch history；即使调用方篡改 content 后重新计算 hash，当前 state 与 replay state 不一致也会被拒绝。

### `revalidate_slot(state, slot_id, evidence, validator) -> RevalidationResult`

运行 guard 并返回可放入 Patch 的 typed `Revalidate` operation。validator 必须是 `(slot, evidence) -> bool` callable，或实现同签名 `validate` 方法，并暴露 `validator_id` 或 `__name__`。

### `replay(initial_state, patch_history) -> ConstraintState`

按顺序重放 `AppliedPatch`。每个 history entry 同时保存 patch 和原授权 context，因此 replay 不需要提升或猜测权限。stale input hash 或任何语义差异都会终止 replay。

### Serialization

`serialize_state` 返回 canonical JSON-compatible dict；`deserialize_state` 对未知字段、缺字段、非法 enum、非 JSON 值、unsupported version 和 hash mismatch fail closed。

`canonical_state_hash` 是 canonical state JSON（排除 `state_hash` 字段自身）的 SHA-256。slot 按 ID 排序，history 保持 append order，JSON key 排序，禁止 NaN/Infinity。

## Invariants

1. Suspend/Restore identity preservation。
2. event/patch/validation append-only history。
3. parent、lineage、override graph consistency。
4. Restore 必须引用成功且仍适用的 Revalidate。
5. Expire permanence。
6. canonical JSON 和 state hash deterministic replay。
7. whole-patch atomicity。
8. 每个成功 patch 使 revision 恰好增加 1。
9. unhashed state mutation 被检测。
10. unknown operation、missing field、unknown field 和 invalid enum fail closed。
11. source/priority/safety authorization。
12. user source preservation。

稳定 error code 定义在 `cope/errors.py`。主要类别包括 `HASH_MISMATCH`、`STALE_PATCH_HASH`、`DUPLICATE_SLOT_ID`、`SLOT_NOT_FOUND`、`INVALID_TRANSITION`、`LINEAGE_CYCLE`、`OVERRIDE_CYCLE`、`PRIORITY_VIOLATION`、`VALIDATION_NOT_FOUND`、`VALIDATION_FAILED`、`VALIDATION_STALE` 和 `EXPIRED_RESTORE`。

## Experiment runner integration

推荐每次状态 transition 在 episode JSONL 中写一个 trace record。字段映射：

| Runner field | Source |
| --- | --- |
| `pair_key` | `PatchContext.pair_key` |
| `event_source` | `PatchContext.event_source` |
| `information_budget` | `PatchContext.information_budget` |
| `policy_step_budget` | `PatchContext.policy_step_budget` |
| `high_level_call_count` | `PatchContext.high_level_call_count` |
| `constraint_state_before` | `TransitionResult.before_hash` 加 state ID/revision |
| `constraint_state_after` | `TransitionResult.after_hash` 加 result state revision |
| `patch_operations` | `serialize_patch(patch)["operations"]` |
| `slot_id/source/mode/priority/lineage` | affected `ConstraintSlot` |
| `revalidation_result` | `RevalidationResult` / validation history record |
| `task_progress` | `PatchContext.task_progress` |
| `termination_reason` | `PatchContext.termination_reason` |
| `manual_intervention` | `PatchContext.manual_intervention` |
| `git_commit/config_hash/checkpoint_id` | matching `PatchContext` fields |

机器可读接口：

- `schemas/cope-state-v1.schema.json`
- `schemas/cope-trace-v1.schema.json`
- `tests/fixtures/cope/minimal_valid_trace.json`
- `tests/fixtures/cope/invalid_trace.json`

## Versioning and migration

当前唯一支持版本是 `1.0`。v1 reader：

- 不猜测未知字段；
- 不自动接受未来版本；
- 不静默补全缺失 identity、source、priority、lineage 或 history；
- hash mismatch 时拒绝载入。

未来 migration 必须是显式的 `old payload -> new payload` 函数，并满足：

1. 保留 `state_id`、所有 `slot_id`、source 和 lineage；
2. 旧 event/patch/validation history 只能作为 prefix 保留；
3. 写明字段默认值和语义变化；
4. 迁移后运行新版本 `validate_state`；
5. 重新计算新版本 canonical hash；
6. 保存原 schema version、原 hash 和 migration tool version 的 audit record。

## Reproducible checks

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-cope-dev.txt
.venv/bin/python -m pytest -q tests/cope
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q cope tests/cope
git diff --check
```

property test 使用 seed `20260724` 和 `10,000` 条序列。失败时会把 seed、sequence index 和 category 写到 pytest 的临时 `cope_property_failure.json`，以便用同一 seed/index 重放。

## Evidence boundary

这些检查支持的是 formal invariant、unit/property behavior、synthetic golden scenario 和无既有测试回归。它们不支持“CoPE 提高机器人成功率”、真实 disturbance recovery 已成功、对 LIBERO suite 泛化或优于 prompt baseline 等 simulator/robot performance 结论。

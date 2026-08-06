# CoPE State Engine Verification Report

日期：2026-07-24

## Scope and provenance

- Repository: `https://github.com/puredict/CoPE`
- Audited base branch: `master`
- Audited base commit: `570d78333ee977c8ae6de3d97120b23272c4c660`
- Implementation branch: `method/cope-state-semantics`
- GPU required: no
- Existing `AGENTS.md`: none found in repository or clone parent
- Starting worktree: clean

本报告只验证 persistent constraint state 的形式语义、typed operations、guarded restoration、serialization/replay 和 synthetic scenarios。它不是机器人/仿真器效果报告。

## Implemented surface

新增 `cope` 包：

- `schema.py`: frozen typed state、slot、patch、context、operations 和 result models
- `operations.py`: 唯一原子 mutation boundary
- `validator.py`: schema/hash/history/graph/priority invariants
- `recovery.py`: explicit guard execution 和 stable validation ID
- `replay.py`: context-preserving deterministic replay
- `serialization.py`: strict canonical JSON、SHA-256 和 fail-closed deserialization
- `errors.py`: stable error codes

新增 JSON Schema、合法/非法 trace fixture、runner integration 文档、64 条手工反例、固定种子 property sequences 和三个 golden scenarios。

## Verification commands and observed results

测试环境是 repository-local `.venv`，Python `3.13.5`。

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/cope` | `105 passed in 21.89s` |
| `.venv/bin/python -m pytest -q tests --ignore=tests/cope` | 安装 existing-test 所需 PyYAML 后 `59 passed` |
| `.venv/bin/python -m pytest -q` | `164 passed in 26.86s` |

最终提交前还会重新执行 full suite、`compileall`、JSON parse、`git diff --check` 和 clean-status audit；最终 commit SHA 记录在提交本身及交付回复中。

## Property sequence gate

- Seed: `20260724`
- Sequence count: `10,000`
- Generator dependency: Python standard-library `random.Random`
- Legal invariant violations: `0`
- Illegal operations accepted: `0`
- Replay mismatches: `0`
- Blind restores accepted: `0`
- Atomic rollback mismatches: `0`

固定 seed 下十一类 sequence 数量：

| Category | Count |
| --- | ---: |
| legal suspend/revalidate/restore | 917 |
| illegal slot ID | 945 |
| duplicate insert | 895 |
| blind restore | 910 |
| expire then restore | 912 |
| priority violation | 881 |
| patch middle failure | 890 |
| corrupted hash | 909 |
| serialization/replay | 925 |
| expire plus lineage successor | 865 |
| override cycle | 951 |

测试失败时会保存 seed、sequence index 和 category，以便精确重放。

## Manual counterexamples

`test_counterexamples.py` 参数化运行 64 条明确反例，每条同时断言：

- patch rejected；
- stable expected error code；
- before hash 等于 after hash；
- 返回原 state object；
- 不提交 partial history。

反例组覆盖 missing slot、duplicate Insert、blind Restore、expired Restore、low-priority mutation、middle-operation failure、stale input hash 和 duplicate operation ID。另有独立测试覆盖 lineage cycle、override cycle、unknown operation、missing/unknown fields、invalid enum、failed/stale guard 和 unhashed state corruption。

## Golden scenarios

1. **手临时离开、杯子未移动**：Suspend；显式 pose guard 成功；Restore 同一个 slot ID。通过。
2. **杯子移动**：旧 alignment Expire；Insert derived successor；lineage 为 old -> new；旧 slot Restore 被 `EXPIRED_RESTORE` 拒绝。通过。
3. **杯子消失**：existence、alignment、grasp-plan 三个依赖 constraint 全部 Expire；插入 safety escalation；不存在 active 的 “cup exists” constraint；旧 existence slot 不能恢复。通过。

这些是 synthetic state-engine scenarios，没有调用 LIBERO、OpenVLA 或真实机器人。

## Invariant results

| Invariant | Evidence |
| --- | --- |
| Identity preservation | Suspend/Restore golden 和 unit tests |
| Append-only history | prefix/revision/atomicity assertions |
| Graph consistency | lineage/override edge checks和 cycle counterexamples |
| Restore legality | unknown/failed/stale/cross-slot/expired checks |
| Expire permanence | unit/property/golden |
| Deterministic replay | canonical payload/hash exact equality |
| Patch atomicity | valid-first/invalid-middle rollback tests |
| Revision monotonicity | one revision per successful patch |
| Hash integrity | content mutation without rehash rejected |
| Schema validation | JSON Schema + strict deserializer tests |
| Priority consistency | authority and replacement-priority tests |
| Source preservation | user constraint survives auditable override |

## Schema and integration artifacts

- `schemas/cope-state-v1.schema.json`
- `schemas/cope-trace-v1.schema.json`
- `tests/fixtures/cope/minimal_valid_trace.json`
- `tests/fixtures/cope/invalid_trace.json`
- `docs/COPE_STATE_SEMANTICS.md`

Schema tests validate both schemas as Draft 2020-12, accept the legal fixture and reject the illegal fixture.

## Claim boundary

当前证据能支持：

- stated v1 invariants 在测试空间内成立；
- specified invalid transitions fail closed；
- deterministic serialization/replay；
- fixed-seed synthetic property and golden scenarios；
- existing CPU test suite 没有回归。

当前证据不能支持：

- CoPE 提高机器人或 LIBERO/OpenVLA 成功率；
- learned detector、perception evidence 或 validator 本身准确；
- 真实中断后的 motion recovery 已实现；
- 相对 reactive/prompt/stage-backtrack baseline 的性能优势；
- suite-level generalization 或统计显著性。

## Remaining work outside this branch

- 把 runner 的 disturbance observer 输出接到 `PatchContext` 和 typed Patch。
- 为真实 perception validator 定义证据质量和 calibration protocol。
- 在严格 paired、matched-budget、无人工干预的 simulator study 中测量任务效果。
- 若 schema 演进，按 migration protocol 实现显式版本转换。

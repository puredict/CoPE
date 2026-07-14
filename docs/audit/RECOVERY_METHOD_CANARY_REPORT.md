# Recovery Method Single-Condition Canary Report

日期：2026-07-14
正式仓库：`/home/lijingsu/vla`
隔离 worktree：`/home/lijingsu/codex-worktrees/recovery-canary`
分支：`experiment/recovery-canary`
main 起始 commit：`bf35c7c7dc39618cb994c78de6b6b062ffe2751b`
确认标签：`dashboard-target-joint-fix-pass`，指向同一 merge commit `bf35c7c7dc39618cb994c78de6b6b062ffe2751b`

本报告只记录 task `0`、initial state `0`、seed `7` 的单个 Canary 条件。不得据此声称总体优于 reactive、稳定恢复、统计显著、对 LIBERO-Spatial 泛化，或完整符号恢复架构已验证。

## Preflight

在正式 main 工作树执行指定检查：

| Command | Exit | Result |
| --- | ---: | --- |
| `cd /home/lijingsu/vla && git status --short` | 0 | 空，main 工作树干净 |
| `git show --no-patch dashboard-target-joint-fix-pass` | 0 | tag 存在，指向 `bf35c7c7dc39618cb994c78de6b6b062ffe2751b` |
| `git rev-parse main` | 0 | `bf35c7c7dc39618cb994c78de6b6b062ffe2751b` |
| `nvidia-smi` | 0 | 8 张 RTX 3090，均无 compute app，仅 Xorg 基础占用 |
| `ps aux \| grep -E "openvla\|libero\|dashboard" \| grep -v grep \|\| true` | 0 | 初始检查无输出 |

随后创建隔离 worktree：

```bash
git worktree add \
  /home/lijingsu/codex-worktrees/recovery-canary \
  -b experiment/recovery-canary \
  main
```

结果：退出码 `0`，worktree HEAD 为 `bf35c7c7dc39618cb994c78de6b6b062ffe2751b`。

开跑前重新检查 GPU 和进程。17:20:55 曾发现一个 pre-existing 进程：

```text
/home/lijingsu/vla/.venv/bin/python tools/audit_libero_spatial_targets.py ...
cwd=/home/lijingsu/codex-worktrees/task-target-audit
```

该进程没有 CUDA compute app；为保持 Canary 干净，等待其退出后才启动正式三集。17:22:49 再次检查时 OpenVLA/LIBERO/Dashboard 进程为空，GPU 仍只有 Xorg 基础占用。

## Instrumentation

新增 `recovery_method_canary.py`，只允许以下三种 mode，且固定顺序各运行一次：

1. `reactive_disturbed`
2. `structured_relocalize_prompt`
3. `stage_backtrack_subgoal`

禁止模式在 runner 中显式列入 `FORBIDDEN_MODES`：

- `clean`
- `verifier_stop`
- `full_reset_replan`
- `oracle_rollback`

新增测试 `tests/test_recovery_method_canary.py` 覆盖：

- 三种 mode 白名单精确匹配
- 禁用 mode 列表
- 配对公平性字段
- structured relocalize 和 stage backtrack 的 prompt-only recovery decision
- validation 对 timeout/success、fresh observation、额外 noop 刷新、prompt switch 对齐的检查

`scripts/run_project_env.sh` 增加 worktree 兼容回退：当隔离 worktree 没有 `src/openvla` 和 `src/LIBERO` 时，只读使用 `/home/lijingsu/vla/src/...` 作为 `PYTHONPATH`。正式 main 工作树未被修改。

## Commands

运行前测试，严格通过 wrapper：

```bash
cd /home/lijingsu/codex-worktrees/recovery-canary
export CUDA_VISIBLE_DEVICES=0
scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python -m pytest -q
```

第一次测试结果：退出码 `0`，`48 passed in 4.02s`。

第一次真实运行命令：

```bash
cd /home/lijingsu/codex-worktrees/recovery-canary
export CUDA_VISIBLE_DEVICES=0
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python recovery_method_canary.py \
  --out-dir /home/lijingsu/vla/recovery_canary_outputs
```

结果：退出码 `1`。失败发生在模型加载前，错误为 `ModuleNotFoundError: No module named 'experiments'`。原因是隔离 worktree 缺少 `src/openvla` 和 `src/LIBERO`，随后修复 wrapper 的 `PYTHONPATH` 回退逻辑。

修复后重新运行测试：

```bash
cd /home/lijingsu/codex-worktrees/recovery-canary
export CUDA_VISIBLE_DEVICES=0
scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python -m pytest -q
```

结果：退出码 `0`，`48 passed in 4.01s`。

正式 Canary 命令：

```bash
cd /home/lijingsu/codex-worktrees/recovery-canary
export CUDA_VISIBLE_DEVICES=0
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python recovery_method_canary.py \
  --out-dir /home/lijingsu/vla/recovery_canary_outputs
```

结果：退出码 `0`。三集全部完成，runner 内置 validation 结果：

```json
{"passed": true, "errors": [], "warnings": []}
```

## Fixed Configuration

三种 mode 完全共享以下条件：

| Field | Value |
| --- | --- |
| suite | `libero_spatial` |
| task | `0` |
| initial state | `0` |
| seed | `7` |
| checkpoint | `/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial` |
| target joint | `akita_black_bowl_1_joint0` |
| disturbance step | `70` |
| dx, dy, dz | `[0.10, 0.05, 0.0]` |
| policy budget | `220` |
| warmup | `10` env steps |
| camera resolution | `256` |
| resolved unnorm key | `libero_spatial` |
| action normalization | normalize gripper, binarize gripper, invert OpenVLA gripper |

唯一允许变化的是 `mode` 及其对应 recovery prompt/recovery decision。

## Episode Results

Run directory：

```text
/home/lijingsu/vla/recovery_canary_outputs/2026_07_14-17_22_59
```

| Mode | Final status | Success | Timeout | Policy steps | Recovery-budget steps |
| --- | --- | --- | --- | ---: | ---: |
| `reactive_disturbed` | `timeout` | false | true | 220 | 150 |
| `structured_relocalize_prompt` | `timeout` | false | true | 220 | 150 |
| `stage_backtrack_subgoal` | `timeout` | false | true | 220 | 150 |

三个 timeout 均记录为 `success=false`，没有把 timeout 误记为 success。

## Prompt And Recovery Timeline

原始任务 prompt：

```text
pick up the black bowl between the plate and the ramekin and place it on the plate
```

| Mode | Disturbance step | Prompt switch step | Recovery prompt / decision |
| --- | ---: | ---: | --- |
| `reactive_disturbed` | 70 | none | 继续原始 prompt，`actual_recovery_action_prompt_only=false` |
| `structured_relocalize_prompt` | 70 | 70 | `relocalize the black bowl at its current position, then complete the original task: ...` |
| `stage_backtrack_subgoal` | 70 | 70 | `pick up the black bowl from its current position and place it on the plate` |

structured relocalize 记录：

- affected object：`black bowl`
- invalidated state/subgoal：`["affected_object_pose", "grasp_validity"]`
- requested recovery stage：`relocalize_affected_object_then_continue`
- actual recovery action：prompt-only，无 reset，无 rollback

stage backtrack 记录：

- affected object：`black bowl`
- invalidated state/subgoal：`["unaffected_world_state_preserved_but_current_stage_restarted"]`
- requested recovery stage：`the plate`
- actual recovery action：prompt-only，无 reset，无 rollback

## Fresh Observation Evidence

三种 mode 均在 policy step `70` 应用扰动，随后下一次推理使用 fresh observation：

| Mode | Actual delta | Refresh method | Extra noop env step | Step-70 fresh obs | Step-70 remaining budget |
| --- | --- | --- | --- | --- | ---: |
| `reactive_disturbed` | `[0.09999999999999999, 0.04999999999999999, 0.0]` | `env.env._get_observations(force_update=True)` | false | true | 149 |
| `structured_relocalize_prompt` | `[0.09999999999999999, 0.04999999999999999, 0.0]` | `env.env._get_observations(force_update=True)` | false | true | 149 |
| `stage_backtrack_subgoal` | `[0.09999999999999999, 0.04999999999999999, 0.0]` | `env.env._get_observations(force_update=True)` | false | true | 149 |

刷新没有消耗额外 policy step，也没有消耗 dummy noop env step。

## Budget Comparison

| Mode | Warmup env steps | Policy budget | Policy steps consumed | Pre-disturbance steps | Post-disturbance/recovery steps | Reset count | Rollback count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `reactive_disturbed` | 10 | 220 | 220 | 70 | 150 | 0 | 0 |
| `structured_relocalize_prompt` | 10 | 220 | 220 | 70 | 150 | 0 | 0 |
| `stage_backtrack_subgoal` | 10 | 220 | 220 | 70 | 150 | 0 | 0 |

## Output Paths

Top-level summary：

- `/home/lijingsu/vla/recovery_canary_outputs/2026_07_14-17_22_59/summary.json`

Episode outputs, each containing `run_config.json`、`events.jsonl`、`actions.jsonl`、`episode_summary.json`、`raw.mp4`、`annotated.mp4`：

- `/home/lijingsu/vla/recovery_canary_outputs/2026_07_14-17_22_59/task0_initial_state0_seed7_reactive_disturbed`
- `/home/lijingsu/vla/recovery_canary_outputs/2026_07_14-17_22_59/task0_initial_state0_seed7_structured_relocalize_prompt`
- `/home/lijingsu/vla/recovery_canary_outputs/2026_07_14-17_22_59/task0_initial_state0_seed7_stage_backtrack_subgoal`

Validation confirmed raw and annotated video frame counts align with action counts for all three episodes.

## GPU And Process State

Before正式 Canary：

- `nvidia-smi`：8 张 RTX 3090，均无 compute app，仅 `/usr/lib/xorg/Xorg` 基础占用
- OpenVLA/LIBERO/Dashboard process check：无输出

During：

- `nvidia-smi --query-compute-apps=...`：仅 PID `1901142` 使用 GPU0 bus `00000000:35:00.0`
- 显存：约 `15166 MiB`
- 命令：`/home/lijingsu/vla/.venv/bin/python recovery_method_canary.py --out-dir /home/lijingsu/vla/recovery_canary_outputs`
- 未发现 Dashboard 进程

After：

- `nvidia-smi`：GPU0 回到 `12 MiB` Xorg 基础占用，8 张卡均无 compute app
- `ps aux | grep -E "openvla|libero|dashboard|recovery_method_canary" | grep -v grep || true`：无输出

## Findings

1. `reactive_disturbed` 在该单条件 Canary 下 timeout。
2. `structured_relocalize_prompt` 在同一条件下 timeout。
3. `stage_backtrack_subgoal` 在同一条件下 timeout。
4. 两种恢复方法都只进行了 prompt-only recovery，没有 reset、rollback 或额外 budget。
5. worktree runner 初次运行暴露出 `scripts/run_project_env.sh` 对独立 worktree 缺少 `src` 的兼容问题，已在隔离分支修复。
6. 正式开跑前曾有另一个 worktree 的 target-audit 进程存在；已等待其退出后再运行 Canary。

## Expansion Decision

不允许扩大到三个 initial states。

理由：在 task `0`、initial state `0`、seed `7` 的单个 Canary 条件下，两个恢复 mode 都没有完成任务，且均与 reactive 一样耗尽 220 policy-step budget。下一步应先检查 prompt-only recovery 是否需要更强的观测/阶段状态输入，或是否需要更明确的 subgoal/controller 设计；不应把本次结果扩大解释为总体方法比较。

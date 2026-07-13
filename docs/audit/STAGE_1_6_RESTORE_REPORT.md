# Stage 1.6 Restore Report

日期：2026-07-13  
仓库：`/home/lijingsu/vla`  
恢复范围：仅恢复被误撤销的阶段 1.6；未创建 `stage-2-canary` 分支，未运行 OpenVLA rollout，未运行 Canary，未导入 D/F，未连接真实 Dashboard backend。

## 1. 恢复前 HEAD

- 分支：`main`
- 恢复前 HEAD：`6aa36c7ae74d0fdd109622ea7c00d0fc361a04cd`
- 恢复前 `git status --short`：空
- 恢复前 `stage-1.6-pass` 指向：`f55e855b91b0349c4e5b08f1722c8ecb00b5d73d`
- 恢复前状态快照已保存到远端：`/tmp/stage_1_6_restore_initial_state.log`

## 2. 备份标签

- 创建标签：`pre-stage-1.6-restore`
- 指向 commit：`6aa36c7ae74d0fdd109622ea7c00d0fc361a04cd`
- 标签说明：`Main state before restoring mistakenly reverted stage 1.6`

## 3. 恢复分支

- 创建并使用分支：`recovery/restore-stage-1.6`

## 4. 被撤销的两个 revert

- `6aa36c7ae74d0fdd109622ea7c00d0fc361a04cd`：`Revert "Mark experiment protocol pending canary validation"`
- `e0fbd2a8db83350808fdae17ea07c06ddd6fca7f`：`Revert "Merge stage 1.6 experiment correctness gate"`

## 5. 新产生的恢复 commit

- `2f15a9152d0cd9879d7967ae4ab37633b0a222e3`：`Revert "Revert "Mark experiment protocol pending canary validation""`
- `970330ddb407c8649f49c1661566583b040b7a1f`：`Revert "Revert "Merge stage 1.6 experiment correctness gate""`
- `148671e6ff837fb512abc4645ea18de7bd981ae8`：`Remove local path from correctness gate report`

第三个 commit 仅对恢复出的 `docs/audit/CORRECTNESS_GATE_REPORT.md` 做一行文档脱敏，将从 `stage-1.6-pass` 恢复出的 Mac 本地绝对路径改写为非机器绑定描述；未改源码、测试或实验逻辑。

## 6. 合并 commit

- 合并方式：`git merge --no-ff recovery/restore-stage-1.6 -m "Restore stage 1.6 correctness gate after mistaken revert"`
- 合并 commit：`c2155692918e44cd3cf6adb8664cfa436ddfa0df`

## 7. 测试命令和结果

恢复分支上执行：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m pytest -q
```

结果：退出码 0，`30 passed in 3.26s`。

合并后的 `main` 上再次执行：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m pytest -q
```

结果：退出码 0，`30 passed in 3.28s`。

## 8. 观测刷新诊断结果

恢复分支上执行：

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python \
  libero_observation_refresh_diagnostic.py
```

结果：退出码 0。

- `passed`: `true`
- `old_obs_reused_pixel_delta.changed_pixels`: `0`
- `fresh_obs_pixel_delta.changed_pixels`: `10734`
- `refresh.consumed_noop_env_step`: `false`
- `refresh.method`: `env.env._get_observations(force_update=True)`

合并后的 `main` 上再次执行同一命令。

结果：退出码 0。

- `passed`: `true`
- `old_obs_reused_pixel_delta.changed_pixels`: `0`
- `fresh_obs_pixel_delta.changed_pixels`: `10734`
- `refresh.consumed_noop_env_step`: `false`
- `refresh.method`: `env.env._get_observations(force_update=True)`

## 9. 恢复后的 main HEAD

- 阶段 1.6 恢复并重验证后的 `main` HEAD：`c2155692918e44cd3cf6adb8664cfa436ddfa0df`
- 当时 `git status --short`：空

## 10. stage-1.6-restored 标签

- 创建标签：`stage-1.6-restored`
- 指向 commit：`c2155692918e44cd3cf6adb8664cfa436ddfa0df`
- 标签说明：`Stage 1.6 restored after integration revert and revalidated`
- 旧标签 `stage-1.6-pass` 未移动、未删除，仍指向 `f55e855b91b0349c4e5b08f1722c8ecb00b5d73d`。

## 11. 冲突情况和解决方式

- `git revert --no-edit 6aa36c7ae74d0fdd109622ea7c00d0fc361a04cd`：无冲突。
- `git revert --no-edit e0fbd2a8db83350808fdae17ea07c06ddd6fca7f`：无冲突。
- 合并 `recovery/restore-stage-1.6` 回 `main`：无冲突。
- 未使用 `git checkout --theirs .`、`git checkout --ours .`、`git reset` 或批量覆盖。
- 额外文档处理：仅脱敏 `docs/audit/CORRECTNESS_GATE_REPORT.md` 中一条从阶段标签恢复出的 Mac 本地绝对路径，满足“没有误带 Mac 本地绝对路径”的检查。

## 12. 并发写入检查

开始前执行只读检查：

- `pgrep -af codex`：无输出。
- `pgrep -af git`：无输出。
- `pgrep -af pytest`：无输出。
- `pgrep -af openvla`：无输出。
- `pgrep -af rollout`：无输出。
- `pgrep -af libero`：无输出。
- `find /home/lijingsu/vla/.git -name '*.lock' -print`：无输出。
- `pgrep -af python` 仅显示系统服务 `networkd-dispatcher` 和 `unattended-upgrade-shutdown`，未发现会写入 `/home/lijingsu/vla` 的 Codex/实验进程。

结论：未发现其他会写 `/home/lijingsu/vla` 的 Codex 会话或 Git 写入者。

## 13. 是否满足重新开始阶段 2 的条件

是。阶段 1.6 的源码、测试、正确性报告和观测刷新诊断已恢复并在 `main` 上重新验证通过；实验协议头为：

```text
Status: Draft v0.1
Pending canary-run validation
```

本次恢复未运行阶段 2、未创建 Canary 分支、未执行 rollout。阶段 2 可在后续单独开始。

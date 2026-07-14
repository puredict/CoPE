# Post-Dashboard Parallel Integration Report

Date: 2026-07-14
Formal repo: `/home/lijingsu/vla`
Integration branch: `integration/post-dashboard-parallel-work`
Base main commit: `bf35c7c7dc39618cb994c78de6b6b062ffe2751b`
Final integration code candidate: `9b872a2754ea9415f13eae554e0523c32aeb2c56`

## Executive Decision

Recommendation: merge `integration/post-dashboard-parallel-work` back to `main` after acknowledging that `integration/analysis-repro-tools` was not present in local or remote-tracking refs and therefore was not reviewed or merged.

No new rollout, Dashboard run, OpenVLA run, or LIBERO experiment was started during this integration. Validation was limited to diff review, unit tests, py_compile, git checks, and process checks.

## Preflight

- `main` worktree was clean before branch creation.
- Created `integration/post-dashboard-parallel-work` from `main`.
- No `tmux` sessions and no `screen` sessions were present.
- Process checks for OpenVLA/LIBERO/Dashboard/streamlit/gradio/vite/npm matched only the check command itself.
- `integration/analysis-repro-tools` was absent from `refs/heads` and `refs/remotes`; this repo had no remote output from `git remote -v`.

## Branch Results

| Order | Branch | Source commit | Result | Merge commit |
| ---: | --- | --- | --- | --- |
| 1 | `analysis/task-target-audit` | `370a8163c379881be807f290701c5fe0973f3a6c` | merged | `a874a410e9012dd44df18ed9304c33829635cfb6` |
| 2 | `integration/analysis-repro-tools` | unavailable | not merged | none |
| 3 | `tools/rollout-video-comparison` | `8f8332e796db99366eeea39da1e7501b4c6bb4bb` | merged | `c4469be5b2beff1c6f18d386c00e6270f3d65fb8` |
| 4 | `validation/dashboard-manual-disturbance` | `8e5d7f6ec42cc63993d027584f342ee0a7fd9eda` | merged | `686430b537c53ccb59e28f01031c328918f40387` |
| 5 | `experiment/recovery-canary` | `1e9259b367e3b38c92b2d9230c3fa88c357cd8ff` | merged | `9b872a2754ea9415f13eae554e0523c32aeb2c56` |

## Per-Branch Audit

### `analysis/task-target-audit`

- Diff: added `configs/libero_spatial_target_joints.yaml`, `docs/audit/LIBERO_SPATIAL_TARGET_AUDIT.md`, `tools/audit_libero_spatial_targets.py`, and `tests/test_audit_libero_spatial_targets.py`.
- Experiment core modification: no; `libero_experiment_core.py` was not changed.
- Committed models/videos/outputs/cache/secrets: none found. Largest changed file was the YAML audit config at 112766 bytes.
- Hardcoded experiment results: no rollout result hardcoding found. The branch intentionally records static target-joint audit diagnostics and recommendations.
- Success/fresh obs/budget/interactive exclusion: no core success or budget logic changed. The audit tool records fresh-observation diagnostics only for target-joint validation.
- Conflicts: none.
- Tests: branch test `6 passed`; integration-branch retest `6 passed in 0.12s`; py_compile passed for the audit tool and test.

### `integration/analysis-repro-tools`

- Result: not merged.
- Reason: branch was not present in `refs/heads` or `refs/remotes`; no similarly named branch was substituted.
- Diff/stat/name-status: unavailable.
- Tests: not run because there was no branch to check out or merge.

### `tools/rollout-video-comparison`

- Diff: added `README_VIDEO_TOOLS.md`, `docs/audit/VIDEO_TOOLS_VALIDATION_REPORT.md`, `tools/video_io.py`, two CLI wrappers, `tools/__init__.py`, and `tests/test_video_tools.py`.
- Experiment core modification: no.
- Committed models/videos/outputs/cache/secrets: none found. The report references generated pilot comparison videos outside the Git worktree; no video files were committed.
- Hardcoded experiment results: no functional result hardcoding found. Historical paths and file sizes appear only in the validation report.
- Success/fresh obs/budget/interactive exclusion: no experiment behavior changed. The tools infer and display metadata such as fresh observation, policy budget, status, and interactive/formal labels for annotation only.
- Conflicts: none.
- Tests: branch test `3 passed`; integration-branch retest `3 passed in 1.24s`; py_compile passed for video tools and tests.

### `validation/dashboard-manual-disturbance`

- Diff: added `docs/audit/DASHBOARD_MANUAL_DISTURBANCE_SMOKE_REPORT.md`; modified `libero_dashboard_controller.py`, `libero_real_backend.py`, `tests/test_dashboard_interactive_marking.py`, and `tests/test_real_backend_contract.py`.
- Experiment core modification: no change to `libero_experiment_core.py`; this branch changes Dashboard/runtime audit recording.
- Committed models/videos/outputs/cache/secrets: none found. The source worktree had untracked `.venv`, `cache`, `libero_data`, `models`, `src`, and `summary_table.*`; these were not committed or merged.
- Hardcoded experiment results: no functional result hardcoding found. Smoke evidence paths and values are report-only.
- Success/fresh obs/budget/interactive exclusion: no success criterion change found. The backend now records manual disturbance audit fields, preserves policy step before/after disturbance, marks fresh observation, and records whether a noop env step was consumed. Tests cover that manual/interactive runs remain excluded from formal metrics.
- Conflicts: none.
- Tests: branch test `12 passed`; integration-branch retest `12 passed in 0.96s`; py_compile passed for `libero_real_backend.py`, `libero_dashboard.py`, and `libero_dashboard_controller.py`.

### `experiment/recovery-canary`

- Diff: added `recovery_method_canary.py`, `docs/audit/RECOVERY_METHOD_CANARY_REPORT.md`, and `tests/test_recovery_method_canary.py`; modified `scripts/run_project_env.sh`.
- Experiment core modification: no change to `libero_experiment_core.py`. The new runner uses existing helpers.
- Committed models/videos/outputs/cache/secrets: none found. The report references prior canary outputs under `/home/lijingsu/vla/recovery_canary_outputs`; no outputs or videos were committed.
- Hardcoded experiment results: no functional result hardcoding found. The runner hardcodes the fixed single-condition canary configuration and formal repo paths, but it computes records at runtime and validates them instead of embedding prior outcomes.
- Success/fresh obs/budget/interactive exclusion: canary validation rejects timeout counted as success, checks fresh observation at disturbance step, checks no extra noop refresh step, and checks aligned policy budget. It does not modify success logic or interactive exclusion logic.
- Conflicts: none.
- Tests: branch test `5 passed`; corrected shell check used `bash -n scripts/run_project_env.sh`; integration-branch retest `5 passed in 0.08s`; py_compile passed for Python files.

## Final Validation

- Full pytest on integration branch: `59 passed in 5.35s`.
- Full tracked Python py_compile: passed for all 37 tracked `.py` files.
- `git diff --check main..HEAD`: passed with no output.
- `git status --short --branch`: clean before report generation.
- Final diff against `main` before this report: 20 files changed, 9164 insertions, 9 deletions.
- Merge structure: four independent merge commits were preserved; no squash merge was used.
- Final process check: no OpenVLA/LIBERO/Dashboard/streamlit/gradio/vite/npm/recovery canary process remained; only the check command matched.

## Final Candidate

The final integration code candidate before adding this report is:

```text
9b872a2754ea9415f13eae554e0523c32aeb2c56
```

This report is a documentation-only addition after that candidate. If the report commit is retained, the branch HEAD after committing the report should be used as the exact merge-back commit, while the tested code candidate remains `9b872a2754ea9415f13eae554e0523c32aeb2c56`.

## Merge-Back Recommendation

Recommend merging `integration/post-dashboard-parallel-work` back to `main`, with one caveat: `integration/analysis-repro-tools` was not reviewed because the branch was missing. Do not claim that branch's contents are included.

# Stage 1.5 Report: Git Baseline and Offline Smoke Environment

阶段：1.5 建立版本基线并固定离线运行环境  
状态：PASS

## 1. 原始基线 Commit

- Baseline commit: `88afdea6b571454958fac57abd19c038d149f069`
- Baseline commit message: `Stage 1.5 baseline import`
- Active branch after work: `main`
- Note: branch `stage-1.6-correctness-gate` also points at the baseline commit; `main` contains the offline launcher commit.

## 2. 离线运行工具 Commit

- Offline tools commit: `68c3cddcc8393da78c28bdc1b90f869ab00b045f`
- Commit message: `Add reproducible offline smoke-test launcher`

## 3. .gitignore 内容

```gitignore
.venv/
models/
audit_outputs/
smoke_outputs/
disturbance_outputs/
outputs/
results/
__pycache__/
.pytest_cache/
.mypy_cache/
*.pyc
*.pyo
*.log
*.mp4

# Local caches and generated experiment outputs
cache/
dashboard_outputs/
baseline_outputs/
second_necessity_outputs/
disturbance_probe_out/
tmp/

# External dependency checkouts / large assets managed outside this project repo
src/
libero_data/

# Generated local image artifact, kept out without ignoring all PNG files
synthetic_table.png
```

## 4. Git 中实际跟踪的文件列表

- `.gitignore`
- `README.md`
- `README_LIBERO_DASHBOARD.md`
- `README_OFFLINE_ENVIRONMENT.md`
- `baseline_current_world_replan_eval.py`
- `baseline_reset_rollback_eval.py`
- `baseline_stage_backtrack_eval.py`
- `check_vla_env.py`
- `disturbance_probe.py`
- `download_openvla.py`
- `download_openvla_libero_spatial.py`
- `libero_base_closed_loop_smoke.py`
- `libero_dashboard.py`
- `libero_dashboard_controller.py`
- `libero_disturbance_eval.py`
- `libero_disturbance_smoke.py`
- `libero_experiment_core.py`
- `openpi_libero_config/config.yaml`
- `openvla_smoke.py`
- `requirements-dashboard.txt`
- `run_baseline_base_openvla.sh`
- `run_expanded_spatial_3trials.sh`
- `run_full_spatial_disturbance.sh`
- `run_libero_dashboard.sh`
- `run_magnitude_large.sh`
- `run_magnitude_small.sh`
- `run_one_probe.py`
- `run_timing_step120.sh`
- `run_timing_step30.sh`
- `run_timing_step60.sh`
- `scripts/run_project_env.sh`
- `scripts/run_smokes_offline.sh`
- `second_necessity_intervention.py`
- `summarize_disturbance_results.py`
- `tests/test_dashboard_controller.py`
- `tests/test_experiment_helpers.py`
- `verifier_vs_recovery_state_eval.py`
- `wait_and_collect_disturbance_results.sh`

## 5. 四个规范 Smoke 命令

- `bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python check_vla_env.py`
  - exit: `0`
  - log: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/01_check_vla_env.log`
- `bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python openvla_smoke.py --model /home/lijingsu/vla/models/openvla-7b --device cuda:0 --unnorm-key bridge_orig`
  - exit: `0`
  - log: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/02_openvla_smoke.log`
- `bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python libero_base_closed_loop_smoke.py`
  - exit: `0`
  - log: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/03_libero_base_closed_loop_smoke.log`
- `bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python libero_disturbance_smoke.py`
  - exit: `0`
  - log: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/04_libero_disturbance_smoke.log`

Smoke audit directory:

```text
/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes
```

## 6. 每条命令退出码

```text
index	exit	command	log_path
00_gpu_before	0	nvidia-smi --query-gpu=index\,name\,memory.total\,memory.used\,utilization.gpu --format=csv	/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/00_gpu_before.log
01_check_vla_env	0	bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python check_vla_env.py	/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/01_check_vla_env.log
02_openvla_smoke	0	bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python openvla_smoke.py --model /home/lijingsu/vla/models/openvla-7b --device cuda:0 --unnorm-key bridge_orig	/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/02_openvla_smoke.log
03_libero_base_closed_loop_smoke	0	bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python libero_base_closed_loop_smoke.py	/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/03_libero_base_closed_loop_smoke.log
04_libero_disturbance_smoke	0	bwrap --bind / / --dev-bind /dev /dev --proc /proc --bind /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs /home/lijingsu/vla/smoke_outputs /home/lijingsu/vla/scripts/run_project_env.sh python libero_disturbance_smoke.py	/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/04_libero_disturbance_smoke.log
98_generated_files	0	find /home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes -type f \( -name \*.json -o -name \*.png -o -name \*.mp4 \) -printf %TY-%Tm-%Td\ %TH:%TM:%TS\ %s\ %p\\n	/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/98_generated_files.log
99_gpu_after	0	nvidia-smi --query-gpu=index\,name\,memory.total\,memory.used\,utilization.gpu --format=csv	/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/99_gpu_after.log
```

## 7. 日志绝对路径

- check env: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/01_check_vla_env.log`
- OpenVLA smoke: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/02_openvla_smoke.log`
- LIBERO base smoke: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/03_libero_base_closed_loop_smoke.log`
- LIBERO disturbance smoke: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/04_libero_disturbance_smoke.log`
- validation audit: `/home/lijingsu/vla/audit_outputs/20260713_211615/stage_1_5_validation_audit.json`
- final independent state check: `/home/lijingsu/vla/audit_outputs/20260713_211615/10_final_independent_state.log`

## 8. 动作长度和 NaN/Inf 审计

- OpenVLA single-image action length: `7`
- OpenVLA single-image action all finite: `True`
- OpenVLA action: `[0.01164595, 0.00475603, 0.00469544, -0.00397045, 0.03070304, 0.01443947, 0.99607843]`
- JSON action count from LIBERO smoke outputs: `22`
- JSON action lengths: `[7]`
- JSON actions all finite: `True`

## 9. 图片和 JSON 输出路径

- Isolated smoke output root: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs`
- Base smoke JSON: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs/base_closed_loop_smoke.json`
- Disturbance smoke JSON: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/isolated_smoke_outputs/disturbance/disturbance_smoke.json`
- Image count: `16`
- Image shapes: `[[224, 224, 3]]`
- Image dtypes: `['uint8']`

Disturbance qpos/body position check:

```json
{
  "before_t5": [
    -0.117287,
    0.055748,
    0.475169
  ],
  "after_t6": [
    -0.017287,
    0.105748,
    0.475169
  ],
  "delta": [
    0.1,
    0.05,
    0.0
  ],
  "event": {
    "type": "target_displacement",
    "joint": "tomato_sauce_1_joint0",
    "delta_xy": [
      0.1,
      0.05
    ]
  }
}
```

Old `/home/lijingsu/vla/smoke_outputs` listing remained at pre-existing July 7 timestamps; new outputs were isolated under the audit directory.

## 10. GPU 使用前后状态

Before log: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/00_gpu_before.log`  
After log: `/home/lijingsu/vla/audit_outputs/20260713_213433_offline_smokes/99_gpu_after.log`

Final independent check showed no relevant lingering Python / bwrap / OpenVLA processes and all GPUs at `12 MiB` memory / `0%` utilization:

```text
COMMAND: final independent process and gpu check
START: 2026-07-13T21:37:53+08:00
index, name, memory.total [MiB], memory.used [MiB], utilization.gpu [%]
0, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
1, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
2, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
3, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
4, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
5, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
6, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
7, NVIDIA GeForce RTX 3090, 24576 MiB, 12 MiB, 0 %
END: 2026-07-13T21:37:54+08:00
EXIT: 0
```

## 11. 未解决风险

- This is a project-level workaround. The system CUDA file `/share/apps/cuda/12.2/lib64/libnvJitLink.so.12` is still broken and was not modified.
- The server remains offline from Hugging Face; default `openvla_smoke.py` repo-id invocation is not the standard command on this server.
- `openvla_smoke.py` was intentionally not changed to hard-code a machine path.
- Existing stale-observation and success/done semantic risks are not fixed in this stage.
- Existing Dashboard-related files were committed only as pre-existing project files; no Dashboard work was performed in this stage.

## 12. 是否满足进入阶段 2 的条件

YES, for the stage 0/1/1.5 gate: phase 1 is now `PASS（规范离线本地模型调用）`.

Stopped here by instruction. Stage 2 clean/disturbed paired evaluation was not run.

## Git 当前状态

```text
branch: main
git status --short: []

68c3cdd (HEAD -> main) Add reproducible offline smoke-test launcher
88afdea (stage-1.6-correctness-gate) Stage 1.5 baseline import
```

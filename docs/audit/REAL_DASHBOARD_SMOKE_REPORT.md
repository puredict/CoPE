# Real Dashboard Integration And Smoke Report

Date: 2026-07-14

## Integration

- Starting `main`: `13a7f468649ca053a88651f0e6d657b2b8aa8665`
- Source dashboard commit: `365e9dae36bd4d76f719c7908496f5430cda495f`
- Cherry-pick result commit: `b95a477bfcf8218f98bc3040ee62a53400d0fea4`
- Integration branch: `integration/real-dashboard`
- Conflicts: none
- Additional fixes after cherry-pick:
  - Force `exclude_from_formal_success_summaries=true` through live snapshots, `run_config.json`, and `events.jsonl`.
  - Add `actions.jsonl` for dashboard policy actions.
  - Make `snapshot_for_json()` safe for `None` nested payloads.
  - Make `summarize_disturbance_results.py` warn and exclude `interactive` / non-formal dashboard `episode_summary.json` records.
  - Ignore `interactive_outputs/` so real smoke artifacts are not accidentally committed.

## Static Review

- Dashboard callbacks enqueue controller commands only; they do not call the model, `env.step()`, or qpos mutation directly.
- Real backend delegates policy stepping to `execute_policy_step()`.
- Real backend reuses `extract_episode_status()` for success / timeout / simulator-error semantics.
- Real backend reuses `refresh_observation_after_sim_change()` after qpos mutation.
- No separate dashboard `done == success` implementation was added.
- Dashboard qpos mutation goes through existing `move_free_joint_xy()` and validated target-joint selection.
- Policy budget display and accounting use the existing `make_budget_report()` / `policy_budget_remaining` path.
- Single controller worker owns the backend.
- Dashboard outputs are written under `interactive_outputs/`, not `disturbance_outputs`, Pilot outputs, or other formal experiment directories.

## CPU Validation

- `git diff --check`: passed
- `scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python -m pytest -q`: `35 passed`
- `scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python -m py_compile libero_real_backend.py libero_dashboard.py libero_dashboard_controller.py`: passed

## Real Smoke

- Real smoke run: yes
- Launch command:

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python \
  libero_dashboard.py \
  --real \
  --host 127.0.0.1 \
  --port 7861
```

- Binding / sharing: `127.0.0.1:7861`, `share=False`; `curl -I http://127.0.0.1:7861/` returned `HTTP/1.1 200 OK`.
- Checkpoint: `/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial`
- Suite / task / initial state / seed: `libero_spatial`, task `0`, state `0`, seed `7`
- Device: dashboard snapshot reported `cuda:0`
- Mode / budget: `clean`, `max_steps=20`, `auto_disturbance=false`
- Target joint used for the completed smoke: `akita_black_bowl_1_joint0`
- Note: an initial `target_joint=auto` task-load attempt failed before `Start` because task 0 has an ambiguous tie between `akita_black_bowl_1_joint0` and `akita_black_bowl_2_joint0`. No episode was started for that attempt. The completed smoke used the explicit target joint above.
- Policy camera: displayed and materialized through Gradio image output during the task-load check.
- Task text displayed: `pick up the black bowl between the plate and the ramekin and place it on the plate`
- Strict single-step: policy step moved from `0` to `1` exactly.
- Resume / stop: resumed to policy step `4`, then Safe Stop finalized at policy step `5`.
- Success / timeout: not reached; final `termination_reason=manual_stop`, `success=false`.
- Manual disturbance: not applied; `disturbance_count=0`.

## Smoke Outputs

Run directory:

```text
/home/lijingsu/vla/interactive_outputs/real_dashboard_smoke/20260713T170326Z_task0_trial0_clean_82a2f540
```

Observed files:

- `run_config.json`
- `events.jsonl`
- `episode_summary.json`
- `actions.jsonl`
- `raw.mp4`
- `annotated.mp4`

Driver evidence:

```text
/home/lijingsu/vla/interactive_outputs/real_dashboard_smoke/first_smoke_driver_evidence.json
```

## Event And Flag Checks

- Manual events present: `manual_pause`, `manual_step`, `manual_resume`, `manual_stop`
- `manual_disturbance`: absent, as required for the first smoke
- `run_config.json`: `interactive=true`, `formal_run=false`, `eligible_for_official_metrics=false`, `exclude_from_formal_success_summaries=true`
- `events.jsonl`: same non-formal flags on event records
- `actions.jsonl`: same non-formal flags on action records
- `episode_summary.json`: same non-formal flags, `manual_intervention=true`, `human_intervention=true`

## Statistics Exclusion

Command:

```bash
scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python summarize_disturbance_results.py \
  smoke=/home/lijingsu/vla/interactive_outputs/real_dashboard_smoke/20260713T170326Z_task0_trial0_clean_82a2f540 \
  --csv /tmp/real_dashboard_smoke_summary.csv \
  --json /tmp/real_dashboard_smoke_summary.json
```

Result:

- Warning emitted for excluding one interactive / non-formal `episode_summary.json` record.
- Output row: `condition=diagnostic_skipped`, `n=0`, `successes=0`, `success_rate=""`.

## Resource Release

Before smoke:

- No matching `openvla|libero|dashboard` processes.
- No `7861` listener.
- GPU 0 memory: `12 MiB`, utilization `0%`.

After Safe Stop and Dashboard shutdown:

- No matching `openvla|libero|dashboard` processes.
- No `7861` listener.
- `nvidia-smi`: all GPUs back to `12 MiB / 24576 MiB`; only Xorg was listed.

## Optional Disturbance Smoke

Not run.

Reason: the first attempted task load with `target_joint=auto` hit an ambiguity before episode start. Per the instruction, no second manual-disturbance smoke was run after any first-smoke abnormality. Fresh-observation-after-disturbance therefore remains unverified in this task. The completed no-disturbance smoke correctly had `disturbance_count=0` and `fresh_observation=null`.

## Not Yet Verified

- Manual disturbance path on real backend.
- Fresh observation evidence after real qpos mutation.
- That manual disturbance does not consume an extra policy step in the real dashboard path.
- Full episode success behavior, formal success rate, and recovery-mode comparisons were intentionally not run.

## Recommendation

Recommend merging the real dashboard integration after review for interactive, non-formal use. Do not treat the smoke output as an official metric. Manual-disturbance smoke remains a follow-up validation item.

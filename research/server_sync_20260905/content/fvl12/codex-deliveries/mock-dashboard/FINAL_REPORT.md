# FINAL REPORT: mock-dashboard

## Completed

Implemented a CPU-only mock browser dashboard workflow for LIBERO/OpenVLA disturbance experiments without importing or running OpenVLA, LIBERO, robosuite, MuJoCo, or GPU model code.

The implementation includes:

- Explicit controller states: `IDLE`, `LOADING`, `READY`, `RUNNING`, `PAUSED`, `STOPPING`, `SUCCEEDED`, `FAILED`, `ERROR`.
- A single persistent controller worker thread.
- Thread-safe command queue and snapshot reads.
- Mock backend load, start, pause, resume, strict single-step, manual disturbance, auto disturbance, safe stop, reset, worker exception handling, and output saving.
- Dynamic RGB mock frames showing task, step, mode, disturbance state, pause state, and simulated object position.
- Gradio Blocks UI that launches with `share=False` and was smoke-tested on `127.0.0.1:7861`.
- Non-web `--mock-smoke` command.
- Tests covering state transitions, duplicate start, pause/resume, strict step once, disturbances, stop/save, worker exceptions, JSON/JSONL/video outputs, import boundaries, and manual intervention markers.

## Added Files

- `libero_dashboard_controller.py`
- `libero_dashboard.py`
- `libero_mock_backend.py`
- `tests/test_dashboard_controller.py`
- `tests/test_mock_backend.py`
- `tests/test_mock_dashboard.py`
- `tests/test_mock_dashboard_import.py`
- `README_MOCK_DASHBOARD.md`

No existing experiment script or `run_*.sh` file was modified.

## Architecture And Thread Boundary

- Gradio callbacks call controller request methods only; they enqueue commands and read snapshots.
- The controller owns exactly one persistent background worker thread.
- Only that worker calls backend operations: load, start, step, disturbance, and output finalization.
- Shared snapshot, latest frame, and event tail are protected by a lock and copied on read.
- The controller rejects duplicate starts unless state is `READY`.
- Stop and shutdown requests are handled at worker safety boundaries and still finalize JSONL, summary, and videos.
- Page disconnect does not kill the worker; no Gradio unload handler tears down active episodes.

## Actual Commands And Exit Codes

See `COMMANDS.log` and `TESTS.log` for the command log. Key successful checks:

- `python -m py_compile libero_dashboard_controller.py libero_mock_backend.py libero_dashboard.py` -> exit 0
- `pytest -q tests/test_dashboard_controller.py tests/test_mock_backend.py tests/test_mock_dashboard.py tests/test_mock_dashboard_import.py` -> exit 0, `16 passed`
- `python libero_dashboard.py --mock-smoke --output-dir /tmp/libero_mock_smoke_final` -> exit 0
- `python libero_dashboard.py --mock --host 127.0.0.1 --port 7861` plus `curl -fsS http://127.0.0.1:7861/` -> exit 0, HTML saved at `/tmp/libero_mock_gradio_smoke.html`

## Output Example

Final mock smoke output:

```text
/tmp/libero_mock_smoke_final/20260713T133048Z_task0_trial0_reactive_disturbed_92328590/
  run_config.json
  events.jsonl
  episode_summary.json
  raw.mp4
  annotated.mp4
```

The same smoke command also produced a completed structured recovery run:

```text
/tmp/libero_mock_smoke_final/20260713T133048Z_task0_trial0_structured_relocalize_prompt_890651b1/
```

## Known Deviations / Issues Found

- `/home/lijingsu/vla` exists on the remote host but is not a Git repository, so `git worktree add` could not be used directly. To keep isolation, I used the provided `original_source_snapshot.tar.gz` to create `/home/lijingsu/codex-worktrees/mock-dashboard`, initialized Git there, created branch `codex/mock-dashboard`, made a baseline snapshot commit, then made the feature commit.
- The installed Gradio 4.44.1 / gradio_client stack raises a 500 while generating API-info for JSON schema entries containing boolean `additionalProperties`. I added a small in-process compatibility patch in `build_dashboard()` that maps bool schemas to `Any`; no installed dependency was modified.

## Unverified

- Real OpenVLA model loading was intentionally not tested.
- Real LIBERO/robosuite/MuJoCo environment stepping was intentionally not tested.
- GPU usage was intentionally avoided.
- Browser button clicking was not tested with a human browser session; the Gradio service was started and HTTP-smoke-tested with `curl`.

## Branch And Commit

- Branch: `codex/mock-dashboard`
- Feature commit: `d103f87e76501e19264ae511800dd228753b61b4`
- Baseline snapshot commit: `76f345c65bed3c05f8029da189567114f07e0997`

## Integration Notes

- A future real backend should implement the same controller-facing methods used by `MockBackend`.
- Keep all real model, environment, MuJoCo state mutation, observation refresh, and video writer work on the controller worker thread.
- Dashboard outputs are marked `interactive=true` and `formal_run=false`; manual controls additionally set `manual_intervention=true`.

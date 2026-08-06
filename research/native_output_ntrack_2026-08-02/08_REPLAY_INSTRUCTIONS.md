# Replay instructions

This replay is offline with respect to robotics; it makes only high-level model
API calls. Do not run a simulator or inspect reserve-state files.

From the repository root, set `OPENROUTER_API_KEY` in the process environment
without writing it to disk, then run:

```text
scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  experiments/native_output_ntrack.py \
  --manifest research/native_output_ntrack_2026-08-02/01_CASE_MANIFEST.csv \
  --output-dir research/native_output_ntrack_2026-08-02/run_REPLAY \
  --provider openrouter \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --api-key-env OPENROUTER_API_KEY \
  --model qwen/qwen3.5-flash-02-23 \
  --temperature 0 --seed 20260802 --max-tokens 4096 --timeout 90
```

Verify source and result files with the published `SHA256SUMS.txt`. A replay may
differ because hosted model serving is not guaranteed deterministic even with a
fixed seed; the model/version and all client-side sampling controls must remain
unchanged. Never place credentials or authorization headers in output files.

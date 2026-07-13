#!/usr/bin/env bash
set -euo pipefail
cd /home/lijingsu/vla
while ps -u "$USER" -o cmd= | grep -F "libero_disturbance_eval.py" | grep -v grep >/dev/null; do
  sleep 120
done
stamp=$(date +%Y%m%d_%H%M%S)
out=/home/lijingsu/vla/disturbance_outputs/summary_${stamp}
mkdir -p "$out"
args=()
for root in baseline_base_openvla expanded_spatial_3trials timing_step30 timing_step60 magnitude_small magnitude_large; do
  latest=$(find "/home/lijingsu/vla/disturbance_outputs/$root" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -1 || true)
  if [[ -n "$latest" && -f "$latest/episodes.jsonl" ]]; then
    args+=("$root=$latest")
  fi
done
/home/lijingsu/vla/.venv/bin/python /home/lijingsu/vla/summarize_disturbance_results.py "${args[@]}" --csv "$out/summary_table.csv" --json "$out/summary_table.json" > "$out/summary_stdout.json"
echo "$out" > /home/lijingsu/vla/disturbance_outputs/latest_summary_dir.txt

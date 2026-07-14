# LIBERO Rollout Video Tools

This repo includes two standalone video utilities for audited LIBERO rollout artifacts.

## Annotate One Rollout

```bash
python tools/annotate_rollout_video.py \
  --episode-dir /path/to/task0_initial_state0_seed7_reactive_disturbed \
  --output /path/to/annotated.mp4
```

`--episode-dir` is expected to contain:

- `raw.mp4`
- `run_config.json`
- `events.jsonl`
- `actions.jsonl`
- `episode_summary.json`

You can also pass the files explicitly:

```bash
python tools/annotate_rollout_video.py \
  --video raw.mp4 \
  --run-config run_config.json \
  --events events.jsonl \
  --actions actions.jsonl \
  --episode-summary episode_summary.json \
  --output annotated.mp4 \
  --camera policy
```

The overlay distinguishes `policy` and `observer` cameras. The default is `policy`, and the tool does not label policy-camera footage as third-person observer video.

The FPS field in outputs and sidecars is render/video FPS only. It is not interpreted as the policy inference frequency.

Missing fields do not abort rendering. The tool writes warnings to stderr and records them in the annotation sidecar JSON.

## Compose Side-By-Side Comparisons

```bash
python tools/compose_rollout_comparison.py \
  --input clean=/path/to/task0_initial_state0_seed7_clean \
  --input reactive_disturbed=/path/to/task0_initial_state0_seed7_reactive_disturbed \
  --align policy-step \
  --padding freeze-last \
  --output /path/to/state0_clean_vs_reactive.mp4
```

Supported labels include the current modes:

- `clean`
- `reactive_disturbed`

The CLI also accepts future labels without special branching:

- `reactive`
- `structured`
- `stage_backtrack`

Alignment modes:

- `policy-step`: frame columns are sampled by shared policy step.
- `disturbance-step`: each rollout is shifted so policy step zero on the shared timeline is its disturbance step. Clean runs use the configured or paired disturbance step as the anchor when available.

Padding modes:

- `freeze-last`: hold the nearest available frame when a rollout is shorter than the shared timeline.
- `black`: use black padding outside the available source range.

The comparison output preserves each source aspect ratio with letterbox padding, draws fixed column titles, and writes a sidecar JSON with all inputs, source render FPS, output render FPS, alignment mode, padding mode, camera label, anchors, and warnings.

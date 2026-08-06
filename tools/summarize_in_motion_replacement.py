#!/usr/bin/env python3
"""Aggregate lift-time replacement recovery experiments."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "research/oracle_in_motion_replacement"


def truth(row: dict[str, str], key: str) -> bool:
    return row.get(key) == "True"


def main() -> None:
    rows: list[dict[str, str]] = []
    for path in sorted(RESULT_ROOT.glob("state0?_*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            source_rows = list(csv.DictReader(handle))
        if len(source_rows) != 1:
            raise ValueError(f"expected one row in {path}")
        row = source_rows[0]
        row["source_csv"] = str(path.relative_to(ROOT))
        rows.append(row)
    if len(rows) != 15:
        raise ValueError(f"expected 15 rows, got {len(rows)}")

    with (RESULT_ROOT / "all_episodes.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    by_mode: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)

    def count(mode: str, key: str) -> int:
        return sum(truth(row, key) for row in by_mode[mode])

    def mean(mode: str, key: str) -> float:
        values = [float(row[key]) for row in by_mode[mode]]
        return sum(values) / len(values)

    stale_mode = "double_patch_stale_continue"
    safe_mode = "double_patch_safe_return_switch"
    safe_steps = [int(row["environment_steps"]) for row in by_mode[safe_mode]]
    safe_errors = [
        float(row["safe_return_error_m"]) for row in by_mode[safe_mode]
    ]
    overhead = mean(safe_mode, "environment_steps") - mean(
        stale_mode, "environment_steps"
    )

    report = f"""# Lift-time second replacement and executable recovery

Date: 2026-07-31

Branch: `codex/fsr-pc-v2-canary`

## Question

What happens when a second semantic replacement arrives after the currently
active object has already been grasped and lifted?

Physical and semantic sequence:

1. place cream cheese in the basket;
2. patch butter to alphabet soup;
3. pick and lift alphabet soup by about 0.20 m;
4. patch alphabet soup to tomato sauce;
5. either continue the stale held-object skill, or execute a safe
   return-and-switch repair.

Both treatment arms receive the same accepted two-patch persistent state.
They differ only in executable repair.

## Results

| Gate | Stale continuation | Safe return-and-switch |
|---|---:|---:|
| Lift checkpoint captured | {count(stale_mode, "held_checkpoint_captured")}/5 | {count(safe_mode, "held_checkpoint_captured")}/5 |
| Second patch accepted | {count(stale_mode, "second_patch_accepted")}/5 | {count(safe_mode, "second_patch_accepted")}/5 |
| Hash chain valid | {count(stale_mode, "hash_chain_valid")}/5 | {count(safe_mode, "hash_chain_valid")}/5 |
| Updated goal success | {count(stale_mode, "double_goal_success")}/5 | {count(safe_mode, "double_goal_success")}/5 |
| Stale alphabet soup executed | {count(stale_mode, "stale_held_commitment_executed")}/5 | {count(safe_mode, "stale_held_commitment_executed")}/5 |
| Valid cream-cheese progress retained | {count(stale_mode, "valid_progress_retained")}/5 | {count(safe_mode, "valid_progress_retained")}/5 |
| Within 600-step horizon | {count(stale_mode, "within_horizon")}/5 | {count(safe_mode, "within_horizon")}/5 |

Safe return verification passed in
{count(safe_mode, "safe_return_success")}/5 trials, and the tomato-sauce
replacement skill passed in {count(safe_mode, "replacement_skill_success")}/5.
Return-position error averaged {sum(safe_errors) / len(safe_errors) * 1000:.2f}
mm and was at most {max(safe_errors) * 1000:.2f} mm.

The paired updated-goal effect is +100 percentage points (5/5 versus 0/5).
With five pairs, the two-sided exact sign/McNemar p-value is 0.0625.

## Recovery cost

- event-two lift checkpoint: mean step
  {mean(safe_mode, "lift_checkpoint_step"):.1f};
- stale continuation terminal: mean
  {mean(stale_mode, "environment_steps"):.1f} steps;
- safe return-and-switch terminal: mean
  {mean(safe_mode, "environment_steps"):.1f} steps;
- conservative recovery overhead: {overhead:.1f} steps;
- safe arm range: {min(safe_steps)}–{max(safe_steps)} steps;
- worst remaining horizon margin: {600 - max(safe_steps)} steps.

The recovery succeeds, but the overhead is material.  A nearby certified
staging region could be more efficient than returning the object to its
exact initial pose.

## Main interpretation

The typed commitment patch is necessary but not sufficient.  In the stale
arm, the persistent state is correct (`alphabet_soup` is overridden and
`tomato_sauce` is active), yet the already-running skill still places
alphabet soup in the basket in 5/5 trials.  Only checkpoint-aware executable
repair prevents stale execution.

This supplies direct evidence for the intended two-layer architecture:

`CoPE semantic edit -> repair goal -> safe old-object disposition -> new skill`

It also argues against evaluating CoPE only by changing an instruction
string: controller continuation state must be captured and explicitly
spliced or terminated.

## Scope and limitations

- Object/region and patch choices are oracle; no provider or learned policy
  is called.
- Checkpoint timing is a deterministic post-lift boundary, not asynchronous
  perception latency.
- Safe return uses privileged start geometry.
- The experiment handles object replacement.  Target replacement while
  holding the same object may admit direct redirection and should be tested
  separately after an insertion-capable caddy skill is qualified.

## Reproduction

```bash
export HF_HOME=/home/lijingsu/vla/cache/huggingface
export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=""

scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \\
  experiments/oracle_in_motion_replacement_gate.py \\
  --state-id 0 \\
  --mode double_patch_safe_return_switch \\
  --output-csv research/oracle_in_motion_replacement/reproduction.csv
```

Primary table: `research/oracle_in_motion_replacement/all_episodes.csv`.

## Next engineering gate

Represent the repair strategy as an explicit compiled repair program rather
than mode-specific experiment control flow.  Compare exact return against a
certified staging-region operator, and add an ablation that applies the
semantic patch but omits checkpoint invalidation.
"""
    (RESULT_ROOT / "REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()

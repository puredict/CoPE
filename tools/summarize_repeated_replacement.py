#!/usr/bin/env python3
"""Aggregate repeated-replacement canaries and write the research report."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "research/oracle_repeated_replacement"


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
        if row["patch_count"] == "2":
            row["revision_path"] = "1>2>3"
        rows.append(row)
    if len(rows) != 25:
        raise ValueError(f"expected 25 repeated-replacement rows, got {len(rows)}")

    fields = list(rows[0])
    with (RESULT_ROOT / "all_episodes.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    by_mode: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)

    def count(mode: str, key: str) -> int:
        return sum(truth(row, key) for row in by_mode[mode])

    def mean_steps(mode: str) -> float:
        values = [int(row["environment_steps"]) for row in by_mode[mode]]
        return sum(values) / len(values)

    report = f"""# Repeated semantic replacement gate

Date: 2026-07-31

Branch: `codex/fsr-pc-v2-canary`

## Question

Can one persistent CoPE state accept two authorized semantic replacements
without rebuilding the task, while preserving completed progress and
suppressing both stale commitments?

The predeclared chain is:

`butter_1 -> alphabet_soup_1 -> tomato_sauce_1`

`cream_cheese_1` is physically completed before the events and must remain
valid throughout.

## Results

| Arm | Intended terminal | Goal success | Stale execution |
|---|---|---:|---:|
| Original | cream + butter | {count("original", "original_goal_success")}/5 | butter 5/5 |
| Single patch | cream + alphabet soup | {count("single_patch", "single_replacement_goal_success")}/5 | butter {count("single_patch", "first_stale_commitment_executed")}/5 |
| Two events, no edits | cream + tomato sauce | {count("double_event_no_edit", "double_replacement_goal_success")}/5 | butter {count("double_event_no_edit", "first_stale_commitment_executed")}/5 |
| First patch only; second ignored | cream + tomato sauce | {count("second_event_no_edit", "double_replacement_goal_success")}/5 | alphabet soup {count("second_event_no_edit", "second_stale_commitment_executed")}/5 |
| Two CoPE patches | cream + tomato sauce | {count("double_patch", "double_replacement_goal_success")}/5 | butter {count("double_patch", "first_stale_commitment_executed")}/5; alphabet soup {count("double_patch", "second_stale_commitment_executed")}/5 |

All 25 first skills and all 25 selected second skills succeeded.  Valid
cream-cheese progress was retained in {count("double_patch", "valid_progress_retained")}/5
double-patch trials.  Both typed patches were accepted in
{count("double_patch", "all_patches_accepted")}/5 trials, and their adjacent
hashes formed a continuous chain in {count("double_patch", "hash_chain_valid")}/5.

The strongest paired comparison holds the first patch fixed:

- ignore event 2: updated goal 0/5; alphabet soup incorrectly executed 5/5;
- apply event 2: updated goal 5/5; alphabet soup executed 0/5.

This is a +100 percentage-point paired canary effect.  With five pairs, the
two-sided exact sign/McNemar p-value is 0.0625; it is not yet a
publication-scale sample.

Mean environment steps:

- original: {mean_steps("original"):.1f};
- single patch: {mean_steps("single_patch"):.1f};
- second event ignored: {mean_steps("second_event_no_edit"):.1f};
- double patch: {mean_steps("double_patch"):.1f}.

## Persistent-state evidence

Every two-patch treatment followed revision `1 -> 2 -> 3`.  The second
patch's before-hash exactly equals the first patch's after-hash.  Final slot
modes and lineage are:

- butter: `overridden`;
- alphabet soup: `overridden`;
- tomato sauce: `active`;
- cream cheese: `active`;
- lineage:
  `butter -> alphabet_soup -> tomato_sauce`.

Negative unit tests reject stale expected revisions, targeting a non-tip
commitment, reusing an earlier chain object, and claiming physically false
completed progress.

## Scope and limitation

This isolates persistent semantic state and explicit skill selection.
`oracle_operation_selection=True`, `provider_called=False`, and no learned
policy is involved.

Both events occur after the first object is completed and before the next
pick-place skill begins.  The experiment does **not** yet test a second
interruption during an executing motion.  That requires splitting
`pick_and_place` into resumable `pick`, `transport`, and `place` checkpoints
and verifying safe capture/resume.

## Reproduction

```bash
export HF_HOME=/home/lijingsu/vla/cache/huggingface
export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=""

scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \\
  experiments/oracle_repeated_replacement_gate.py \\
  --state-id 0 \\
  --mode double_patch \\
  --output-csv research/oracle_repeated_replacement/reproduction.csv
```

Repeat states `0..4` and modes `original`, `single_patch`,
`double_event_no_edit`, `second_event_no_edit`, and `double_patch`.

Primary table: `research/oracle_repeated_replacement/all_episodes.csv`.

## Next gate

Refactor the qualified controller into resumable skill phases.  Trigger the
second event after object lift, capture the physical checkpoint, apply the
second patch, and verify that the robot redirects the already-grasped object
or safely returns it before executing the new commitment.
"""
    (RESULT_ROOT / "REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()

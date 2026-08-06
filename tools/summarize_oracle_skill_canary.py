#!/usr/bin/env python3
"""Aggregate raw Oracle skill canary CSVs into reproducible research tables."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "research/oracle_skill_canary"


def read_csvs(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(paths):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                row["source_csv"] = str(path.relative_to(ROOT))
                rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def truth(row: dict[str, str], key: str) -> bool:
    return row.get(key) == "True"


def main() -> None:
    task0_paths = sorted(RESULT_ROOT.glob("task00_state0?_original.csv"))
    replacement_paths = sorted(
        (RESULT_ROOT / "replacement_gate").glob("state0?_*.csv")
    )
    target_paths = sorted((RESULT_ROOT / "target_geometry").glob("*.csv"))
    task0 = read_csvs(task0_paths)
    replacement = read_csvs(replacement_paths)
    target = read_csvs(target_paths)
    write_csv(RESULT_ROOT / "task00_original_all.csv", task0)
    write_csv(RESULT_ROOT / "replacement_gate_all.csv", replacement)
    write_csv(RESULT_ROOT / "target_geometry_all.csv", target)

    by_mode: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in replacement:
        by_mode[row["mode"]].append(row)

    def count(mode: str, key: str) -> int:
        return sum(truth(row, key) for row in by_mode[mode])

    task0_states = {
        int(row["trial_id"])
        for row in task0
        if truth(row, "task_success_after_operation")
    }
    task0_skill_success = sum(truth(row, "success") for row in task0)
    task0_steps = [
        int(row["environment_steps"])
        for row in task0
        if int(row["operation_index"]) == 1
    ]
    patch_rows = by_mode["checkpoint_oracle_cope_patch"]
    no_edit_rows = by_mode["checkpoint_no_edit"]
    original_rows = by_mode["original"]
    reset_rows = by_mode["reset_counterfactual"]
    patch_steps = [int(row["environment_steps"]) for row in patch_rows]
    original_steps = [int(row["environment_steps"]) for row in original_rows]

    report = f"""# Oracle Skill Controller qualification and CoPE replacement gate

Date: 2026-07-31

Branch: `codex/fsr-pc-v2-canary`

Input base before this experiment: `2fced05`

## Decision

Use the explicit, privileged `LiberoOracleSkillController` as the **mechanism
qualification / execution-upper-bound substrate** for CoPE.  It removes the
30% clean-success ceiling that made ReKep/OpenVLA-style end-to-end results
ambiguous.  Do **not** present it as a learned-policy baseline or as evidence
that event interpretation is solved: object/region selection is oracle, no
provider is called, and simulator geometry is privileged.

Keep learned OpenVLA results as a separate realism stratum.  Do not average
learned-controller and oracle-controller trials into one headline number.

## Results

| Gate | Result | Interpretation |
|---|---:|---|
| Task 0 clean original, full task | {len(task0_states)}/5 | clean execution ceiling |
| Task 0 atomic pick-place skills | {task0_skill_success}/{len(task0)} | two objects per state |
| Task 1 clean original | {count("original", "original_goal_success")}/5 | cream cheese + butter |
| Updated goal from reset | {count("reset_counterfactual", "updated_goal_success")}/5 | reachability upper bound |
| Checkpoint no edit, updated goal | {count("checkpoint_no_edit", "updated_goal_success")}/5 | stale-resumption control |
| Checkpoint Oracle CoPE patch | {count("checkpoint_oracle_cope_patch", "updated_goal_success")}/5 | typed `Override` treatment |
| Patch accepted by CoPE engine | {count("checkpoint_oracle_cope_patch", "patch_accepted")}/5 | real state-engine transition |
| Valid progress retained, patch arm | {count("checkpoint_oracle_cope_patch", "valid_progress_retained")}/5 | cream cheese preserved |
| Stale butter executed, no-edit | {count("checkpoint_no_edit", "stale_pending_executed")}/5 | expected failure mechanism |
| Stale butter executed, patch arm | {count("checkpoint_oracle_cope_patch", "stale_pending_executed")}/5 | successful suppression |

The paired checkpoint effect is +100 percentage points (5/5 versus 0/5).
With only five pairs, the exact two-sided sign/McNemar p-value is 0.0625, so
this is a passed canary, not a publication-scale statistical claim.  The
95% exact binomial intervals are wide (approximately 47.8–100% for 5/5 and
0–52.2% for 0/5).

Mean environment steps were {sum(original_steps) / len(original_steps):.1f}
for clean original, {sum(patch_steps) / len(patch_steps):.1f} for the
replacement patch arm, and {sum(task0_steps) / len(task0_steps):.1f} for Task
0 clean original.  Every run stayed below LIBERO's 600-step episode horizon.

`libero_task_success=False` in updated-goal arms is expected: the immutable
BDDL terminal still encodes the old butter goal.  Updated-goal success is
therefore scored from the ground-truth conjunction
`In(cream_cheese_1, basket_region) AND In(alphabet_soup_1, basket_region)`.

## Typed-patch evidence

Each treatment trial initialized two atomic task commitments, then submitted
a production-engine `Override` patch:

- old `butter_1` slot: `active -> overridden`;
- new `alphabet_soup_1` slot: `active`, parented to the old slot;
- completed `cream_cheese_1` slot: remains active and physically satisfied;
- before/after canonical hashes differ and are recorded per state;
- `oracle_operation_selection=True`; `provider_called=False`.

This isolates the claim that **editing the persistent commitment changes
execution**.  It does not test whether an LLM can infer the correct patch.

## Failed cross-direction qualification

The same position-only controller was tested on Task 5 book-to-caddy back and
front targets.  Both initial attempts and both predicate-aware retries failed
(`0/4` target predicates), although grasp acquisition was `4/4` and lift was
about 0.20 m in every run.  The `descend_to_release` phase exhausted 40 steps
with 0.059–0.077 m residual error because the top-down gripper/caddy geometry
blocked entry.

Therefore the current controller is qualified for basket pick-place and
semantic object replacement, but **not** for narrow-compartment target
substitution.  Task 5 requires an orientation- and approach-conditioned
insertion skill; silently adding Task 5 to the main table would conflate CoPE
semantics with an unqualified low-level controller.

## Reproduction

CPU-only simulator invocation:

```bash
export HF_HOME=/home/lijingsu/vla/cache/huggingface
export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=""

scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \\
  experiments/oracle_replacement_gate.py \\
  --state-id 0 \\
  --mode checkpoint_oracle_cope_patch \\
  --output-csv research/oracle_skill_canary/replacement_gate/reproduction.csv
```

Repeat `--state-id` over `0..4` and `--mode` over
`original, reset_counterfactual, checkpoint_no_edit,
checkpoint_oracle_cope_patch`.

Primary tables:

- `research/oracle_skill_canary/task00_original_all.csv`
- `research/oracle_skill_canary/replacement_gate_all.csv`
- `research/oracle_skill_canary/target_geometry_all.csv`

## Next experiment

Freeze this controller and run more interruption types on basket-compatible
skills: cancellation, repeated replacement, and two sequential events.  In
parallel, qualify a learned explicit-goal skill policy as the non-oracle
controller stratum.  Do not return to ReKep as the sole main baseline unless
its clean gate is first raised above the predeclared threshold.
"""
    (RESULT_ROOT / "REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()

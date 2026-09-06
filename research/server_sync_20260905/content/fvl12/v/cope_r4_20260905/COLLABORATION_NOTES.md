# Collaboration notes

## 1. Origin of the ideas

- The **abstract idea of online constraint-program repair** originates with the
  collaborator.
- The **CoPE / RCSP constraint-state formulation** — the slot schema, the four
  lifecycle modes, the typed patch operators, the separation of `Revalidate`
  from `Restore`, and the framing of explainability as a structured patch trace
  rather than chain-of-thought — comes from:

  > Jingsu Li, *CoPE / RCSP Comprehensive Technical Memo*, v0.3, 2026‑04‑26.
  > Terminology taken verbatim: **CoPE** = Constraint-state Patch Editing;
  > **RCSP** = Reactive Constraint-State Patching.

- The work in this package is the **experimental realisation**: the adapter onto
  the existing repair engine, the internally defined FSR-PC baseline, the
  benchmark task, the fairness protocol, the metric suite, and the CPU pilot.

**Author order and final framing are not settled here and must not be inferred
from any file in this package.** No names, percentages, contribution splits or
author orders have been invented.

## 2. Terminology discipline

| term | source | how to write it |
|---|---|---|
| CoPE | memo v0.3, §3 | "Constraint-state Patch Editing (CoPE)" — cite the memo |
| RCSP | memo v0.3 | "Reactive Constraint-State Patching (RCSP)" — cite the memo |
| FSR-PC | **project brief only** | "our internally defined strong baseline" — **no citation** |

The FSR-PC acronym does not appear in the memo or anywhere else that was
supplied. A repository-wide search returned zero matches before this work began.
See [`FSRPC_BASELINE_SPEC.md`](FSRPC_BASELINE_SPEC.md) §1 for the full record of
what was searched.

If the collaborator later supplies a published source for FSR-PC, replace that
section rather than quietly adding a citation.

## 3. Questions for the collaborator

1. **FSR-PC.** Is there a published source we missed? If not, do you agree with
   the "internally defined strong baseline" framing throughout?
2. **Operator subset.** The first paper uses seven operators; `Promote` and
   `Demote` are implemented but excluded. Does that match your intent for the
   first paper?
3. **Audit queries.** Q1–Q5 are taken from the memo's explainability section. Is
   there a sixth query you consider load-bearing?
4. **Restoration semantics.** We treat `expired` as terminal and never
   restorable, and we refuse `Restore` unless `Revalidate` returns `OK` (a
   `DEGRADED` result leaves the slot suspended). Confirm this is the intended
   reading of memo §4.
5. **Benchmark.** Basket sorting was chosen for reliability, not because the
   memo prescribes it. If you would rather anchor the paper on a different
   long-horizon task, this is the moment to say so — the harness is
   task-agnostic behind the `ExecutorRequest` interface.
6. **What the paper claims.** The CPU pilot shows a tie on task success and a
   gap in representation/auditability. Do you want the paper to lead with
   auditability, or to hold for a GPU result that might separate the arms on
   behaviour?

## 4. What was deliberately not done

- No GPU software installed, imported or executed. The development machine is
  CPU-only.
- No existing evidence folder modified. `rekep_gpu_execution/`,
  `rekep_gpu_analysis/`, `rekep_repair_交接/` and `rekep_repair_交接_v2/` are
  treated as immutable.
- No rewrite of the online repair core.
- No threshold tuning to manufacture significance.
- No invented acronym expansions, names, percentages, or author order.

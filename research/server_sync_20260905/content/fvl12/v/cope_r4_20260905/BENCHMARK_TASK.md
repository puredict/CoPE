# Benchmark task — multi-object basket sorting

## 1. Why the task changed

The ReKep pen-in-holder task is retained as an **integration case study only**.
It is unsuitable as the primary benchmark for this question because:

- its nominal success floor is low, so most episodes fail for reasons unrelated
  to adaptation;
- it confounds **execution failure** with **recovery failure** — a failed
  episode does not tell you whether the task-state adaptation was wrong or
  whether the controller simply missed;
- it is single-object and single-goal, so there is no *persistent multi-goal
  state* to patch, which is precisely what CoPE is about.

The replacement is chosen so that the nominal task nearly always succeeds and
every remaining failure is attributable to adaptation.

## 2. The task

Three objects, three baskets:

| object | nominal target |
|---|---|
| milk | basket_A |
| yogurt | basket_A |
| butter | basket_B |

`basket_C` exists as a spare destination so that a *repeated* redirection can
end somewhere other than the nominal target. Without it, condition I3 would be a
no-op for final placement and the control arm would pass it for free — this is
asserted by `test_no_condition_is_won_for_free_by_the_control_arm`.

Two hard safety constraints are always present: `avoid_collision` and
`handle_objects_gently`.

Execution uses a **fixed scripted order**, carried in the slot payload and
therefore shared by every arm. Conditions may set their own order (it is part of
the shared initial state) so the interruption lands where the condition intends.

## 3. Reliability gate (Stage A) — a precondition, not a result

> nominal task success **≥ 8/10** over 10 seeds, preferred ≥ 9/10.

The gate is measured with the **no-adaptation arm on the uninterrupted task**,
so the number describes the *task and the executor*, not any adaptation method.

**If the gate fails, the task is changed or simplified. The methods are not
tuned.**

CPU result: **10/10 → PASS**.
The gate is verified non-vacuous: with a degraded executor (`p_success=0.5`) it
returns FAIL (`test_the_gate_is_not_vacuous`).

Caveat, stated plainly: on CPU the executor is
`cope/benchmark/mock_executor.py`, a scripted pick-and-place mock with
`p_success=0.97` per primitive and at most two attempts per object. **The CPU
gate validates the protocol, not the physical reliability of the real task.**
The gate must be re-run on the GPU host with the real executor before any
robotics claim; see [`GPU_RUNBOOK.md`](GPU_RUNBOOK.md).

## 4. Interruption conditions

All four are deterministic in `(condition, seed)` and **never** in the method.

### I1 — cancellation + redirection
After milk is placed: cancel the yogurt goal; redirect butter from basket_B to
basket_A.
Expected final: milk→A, butter→A, yogurt **not placed**.

### I2 — temporary target unavailability
Before any goal is attempted (butter is scheduled first for this condition):
basket_B becomes unavailable, so the butter goal must be set aside. After yogurt
completes, basket_B returns and the goal must come back.
Expected final: the nominal assignment.
The executor physically refuses to place into an absent basket, so a stale goal
costs a real action — this is what makes the control arm pay.

### I3 — repeated interruption on the same goal
After milk: redirect butter B→A. After yogurt: redirect butter A→C, and insert a
new safety constraint (`keep_object_upright`).
Expected final: milk→A, yogurt→A, butter→**C**.
Both updates land before butter is attempted, so the condition is winnable and
measures state survival across two consecutive edits rather than reaction
latency.

### I4 — changed-world restoration
As I2, but basket_B is **moved** while it is unavailable. When it returns, the
suspended goal's grounding must be revalidated before it is restored — a blind
restore would be operating on a stale grounding.
Expected final: the nominal assignment.

## 5. The grader

`cope/benchmark/episode.py::_expected_outcome` derives ground truth **from the
condition alone**. It never inspects what any policy did, and it is the same
function for every arm (`test_the_grader_depends_only_on_the_condition`).

## 6. Common random numbers

Per-attempt outcomes are drawn from a stream keyed on
`(seed, object, attempt_index)` — the *physical action* — and deliberately not
on the request fingerprint or call counter. FSR-PC re-mints slot ids, so a
fingerprint-keyed stream would hand the two arms different luck for the same
physical action and destroy the paired comparison.

## 7. CPU vs GPU

| | CPU (here) | GPU host |
|---|---|---|
| executor | `MockPickPlaceExecutor` | real scripted / primitive executor |
| interface | `ExecutorRequest` | **the same** `ExecutorRequest` |
| policy code | unchanged | unchanged |
| what is validated | protocol, semantics, fairness, metrics | physical reliability and the real comparison |

No GPU software is installed, imported or executed anywhere in this package.

---

# r2 additions

## Interruption delivery is now time-based

Conditions no longer trigger on goal completion. Each condition has a
pre-registered elapsed-step schedule (`cope/benchmark/scheduler.py`), with a
`libero` profile (~700-900 steps/episode) and a `cpu` profile (~45). The profile
is chosen by the **backend**, never by the method, and both are pre-registered.

## I5 — nested override and restoration (new)

1. butter initially targets basket_B;
2. basket_B becomes unavailable -> `Suspend(g_butter)`;
3. butter is temporarily redirected to basket_C -> `Override`;
4. the redirection is withdrawn before it completes -> `Expire(cover)`;
5. basket_B is physically moved;
6. basket_B becomes available;
7. the system must decide which butter version is restorable;
8. it must revalidate the moved basket before restoring;
9. obsolete temporary and original groundings must not both become active.

Expected final placement: butter in **basket_B** (the original grounding, after
revalidation), milk and yogurt in basket_A.

Validity checks asserted per episode: exactly one active butter goal, no stale
target execution, no duplicate goal execution, restoration corresponds to the
correct lineage, the cancelled temporary goal is not executed, completed
progress preserved.

**I5 is diagnostic, not rigged.** All four adaptation arms pass it on the CPU
dry run; `test_i5_is_not_rigged_for_cope` asserts that. Two fairness gaps found
while building it were fixed in FSR-PC's favour: the baseline had not been told
the withdrawal semantics, and it did not record the pre-detour grounding.

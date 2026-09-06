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

The real BDDL uses installed LIBERO assets:

| abstract name | LIBERO object/region |
|---|---|
| milk | `milk_1` |
| yogurt | `cream_cheese_1` (documented asset equivalent) |
| butter | `butter_1` |
| basket_A | `basket_1_contain_region` |
| basket_B | `basket_2_contain_region` |
| basket_C | `basket_3_contain_region` |

All three baskets are physical free bodies in MuJoCo. Exact initial regions,
object mappings, and world-event deltas are in
`configs_gpu/task_assets.yaml` and `configs_gpu/cope_basket_sorting.bddl`.

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

Caveat, stated plainly: on the shipped CPU result the executor is
`cope/benchmark/mock_executor.py`, a scripted pick-and-place mock with
`p_success=0.97` per primitive and at most two attempts per object. **The CPU
gate validates the protocol, not the physical reliability of the real task.**
The real gate uses the OnTheGroundPanda/OSC_POSE geometry-oracle substrate and
is reported separately in `GPU_INTEGRATION_STATUS.md`; see `GPU_RUNBOOK.md`.

## 4. Interruption conditions

All four are deterministic in `(condition, seed)` and **never** in the method.

### I1 — cancellation + redirection
After milk is placed: cancel the yogurt goal; redirect butter from basket_B to
basket_A.
Expected final: milk→A, butter→A, yogurt **not placed**.

### I2 — temporary target unavailability
Before any goal is attempted (butter is scheduled first for this condition):
basket_B becomes unavailable, so the butter goal must be set aside. After milk
completes, the next active leg receives the restoration event; basket_B returns
and the butter goal must come back.
Expected final: the nominal assignment.
The real backend moves the basket free body to an off-workspace storage pose and
physically refuses to place into it. This is a simulator/world change, not a
JSON-only availability flag.

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
The restored basket is shifted by `[0.12, -0.08, 0.0]` m on the table, and the
success predicate follows the moved basket's contain region.
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

## 7. CPU versus real simulator

| | Synthetic2D/CPU | LIBERO real simulator |
|---|---|---|
| executor | mock or Synthetic2D | privileged geometry oracle, OSC_POSE |
| interface | `ExecutorRequest` | same request plus `SimulatorRepairBackend` |
| policy code | unchanged | unchanged |
| candidate rollout | Synthetic2D model | MuJoCo checkpoint-isolated `env.step` |
| task metric | synthetic placement | object–contain-region geometry predicates |
| claim stratum | protocol | mechanism (not learned-policy or physical robot) |

The server has GPUs, but this backend uses OSMesa CPU rendering and no learned
checkpoint. "Real simulator" must not be rewritten as "GPU policy result."

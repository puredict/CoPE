# Repeated Interruptions v2.1: Horizon and Independence Amendment

Status: frozen before v2.1 calibration outcomes and before any formal method comparison.

Protocol identifier: `repeated_v2_1_horizon_and_independence_v1`.

## Reason for the amendment

The v1 clean-calibration horizon was exactly 260 learned-policy controls. That record remains unchanged. Its four audited tasks produced nominal success counts of 0/10, 4/10, 4/10, and 0/10 for task IDs 0, 1, 4, and 8. Each state was run under seeds 101 and 131, but the raw and environment action-sequence hashes match exactly within every same-state pair. The 40 nominal runs therefore contain 20 unique state-conditioned trajectories.

The cutoff is a demonstrated source of misclassification. Preserved clean traces for task 1 reach success at controls 273, 276, and 323 after matching the first 260 controls of v1 timeouts. Separate clean diagnostics reach success at control 264 for task 0/state 1 and control 378 for task 8/state 2. Task 8/states 0 and 1 still fail at 520, so horizon extension is not treated as a universal behavioral repair.

## Enumerated initial states and frozen split

Before choosing the split, the production LIBERO benchmark loader enumerated every `libero_10` initialization state on host `fvl12`. Every task has IDs 0 through 49, all 500 arrays are finite, and all 50 byte hashes within each task are distinct. The complete inventory is `research/repeated_v2_formal_readiness_v2_1/LIBERO_INIT_STATE_INVENTORY.csv`, SHA256 `a1c7b97d9f0aea18ec9bebde4ff62c224b39be152bd7293a9608e38c54c6bc09`.

The v2.1 state split is:

| Role | Initial-state IDs | Use |
| --- | --- | --- |
| Calibration | 0–9 | Clean-policy measurement and calibration-only event overhead |
| Formal | 10–14 | Paired formal master sessions only |
| Development | 15–19 | Comparator selection and development diagnostics |
| Reserve | 20–49 | Unused reserve; any future use requires another versioned amendment |

These sets are pairwise disjoint. Loading state bytes and computing hashes does not inspect policy behavior on the formal or development states.

The deterministic policy receives technical seed 101 in clean calibration and technical seed 11 in formal execution. A technical seed is recorded for reproducibility and is not an independent experimental unit. Calibration has one run for each task/state pair: 10 tasks × 10 unique calibration states = 100 nominal trajectories. A repeated run is a reproducibility check with scientific weight zero unless its state-conditioned public observation/action history is distinct for a documented stochastic cause.

## Exact trajectory identity

Every run records:

- the SHA256 of the exact initial-state bytes;
- a canonical SHA256 over the ordered raw 7-D policy actions;
- a canonical SHA256 over the ordered executed 7-D environment actions;
- the full trace byte SHA256;
- action count, completion control, and termination reason.

A duplicate group has the same task, initial-state byte hash, checkpoint/model identity, instruction, preprocessing/action-conversion identity, and canonical action-sequence hash. Nominal seed labels do not split such a group. Equal action sequences from different initialization states remain different physical trajectories because the experimental unit includes the unique initial state.

## Clean calibration and horizon rule

The v2.1 data-collection ceiling is 520 learned-policy controls after the existing 10 settling controls. The ceiling is not automatically the scored horizon. There are no interruptions, oracle actions, manual interventions, provider repairs, or hidden success inputs in clean calibration. Timeout and manual intervention are failures, and no failed or inconvenient row may be deleted.

For each task:

1. Collapse exact same-state duplicate trajectories.
2. Retain completion controls from successful unique trajectories.
3. Require at least three successful unique trajectories. Otherwise return `HORIZON_UNESTIMABLE`.
4. Define empirical Q95 by the conservative nearest-rank estimator: sort the values and select rank `ceil(0.95 n)`, using one-based ranks.
5. Freeze

   `H_clean(task) = clip(ceil(1.20 × Q95), 320, 520)`.

The clean success rate is then the fraction of the ten unique calibration states that complete by `H_clean(task)`. The existing inclusive eligibility interval `[0.40, 0.95]` is unchanged. The numerical threshold is not relaxed. In v1 the exact duplicate pairs make the unique-state rates equal to the nominal rates, but v2.1 reports both counts explicitly.

All task horizons are `PENDING_V2_1_CALIBRATION` until the complete 100-cell clean grid has been retained and audited. Earlier clean records diagnose the protocol defect but are not silently relabeled as v2.1 admission evidence.

## Interrupted-episode budget rule

Before any formal comparison, calibration-only single-event trajectories measure paired event overhead on calibration states. An admitted overhead is

`max(0, interrupted_success_control − paired_clean_success_control)`

for the same task and initialization state, with both trajectories successful, public event evidence used by the non-oracle path, and exact action/trace hashes recorded. Failed or censored event trajectories remain feasibility failures and are not converted to finite overheads.

For a task, require at least three unique successful paired overhead measurements spanning at least two supported event families. Otherwise return `INTERRUPTED_BUDGET_UNESTIMABLE`. Deduplicate by event family and exact interrupted action-trajectory hash. With the same nearest-rank Q95 convention, define

`B_event(task) = clip(ceil(1.20 × Q95(overhead)), 32, 130)`

and

`H_interrupted(task, K) = min(1040, H_clean(task) + K × B_event(task))`.

The resulting budget is identical for every method within a task and K. Method name, accepted state, CoPE performance, baseline performance, and formal outcomes are not inputs. Timeout remains failure. If the clean horizon or event allowance is unestimable, that task cannot enter an interrupted pilot or formal run.

## Statistical unit

For formal repeated-interruption evaluation, the independent unit is:

`task + unique formal initial state + preregistered event-schedule realization`.

Each schedule realization must have a distinct canonical interruption-history hash and meet registered spacing/trigger rules. The same master session is paired across methods. Deterministic policy seed labels and method replicas are not independent observations.

## Evidence boundary

The frozen v1 audit source is `clean_calibration_audit_01/CALIBRATION_EPISODES.csv`, SHA256 `3094cad892fa81328a7a3cd7edcbb87ae6d6bc4deaae519899c9ec3e31e7515c`. The preserved exact-prefix comparison is `HORIZON_FAILURE_DIAGNOSTIC.csv`, SHA256 `d6f5f5660c2226225008196970e27d4ea5c919737567298e6e37494878db89e2`. The 520-control diagnostic table is `POSTHOC_LONG_HORIZON_DIAGNOSTICS.csv`, SHA256 `c14aba3d4ad04a568887ad2edce2e17bfdbcc04b285af30dacca02a934b7cbd1`.

The executable pure rules live in `cope_benchmark/repeated_v2/calibration_v2_1.py`. Formal comparison remains prohibited until every registered gate passes and `COPE_ALLOW_FORMAL_RUN=1` is explicitly present.

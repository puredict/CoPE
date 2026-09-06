# ReKep-R

**Online continuation-carrying constraint-program repair for recoverable robotic manipulation.**

ReKep-R extends [ReKep](https://rekep-robot.github.io/) so that a robot can, *during
execution*, suspend the active stage of a relational-keypoint constraint program, splice in an
ordered recovery routine, and resume the interrupted computation from a valid continuation —
rather than only adding a reactive path penalty inside a fixed stage.

## Where things run (CPU vs GPU)

| Component | Hardware | Status |
|---|---|---|
| `rekep_repair/program/` — IR + `StageState` machine, continuation-carrying splice | **CPU (MacBook)** | ✅ built |
| `rekep_repair/events/`, `repair/`, `execution/`, `policies/` — online repair engine + 5 methods | **CPU (MacBook)** | ✅ built |
| `rekep_repair/synthetic/` — 2D closed-loop env, Theorem-1, metrics | **CPU (MacBook)** | ✅ built |
| `tests/` — 15 semantic/property tests (pytest) | **CPU (MacBook)** | ✅ built |
| `rekep_repair/analysis/` — statistics, plots, phase diagram, ablation tables | **CPU (MacBook)** | ⏳ next |
| OmniGibson tasks A/B/C (`experiments/omnigibson/`) | **GPU (8× 3090)** — NVIDIA RTX only, *cannot run on Mac* | 📋 planned, see `docs/GPU_SETUP.md` |
| Large multi-seed sweeps (~6750 episodes) | **GPU (8× 3090)**, 1 sim worker/GPU | 📋 planned |

Everything you can develop and verify on the MacBook is CPU-only numpy/scipy. OmniGibson is built on
NVIDIA Omniverse/Isaac Sim and requires an RTX GPU — those steps are handed off as turnkey commands
for the 3090 box.

## Quickstart (CPU)

```bash
pip install -r requirements.txt              # numpy, scipy, matplotlib
python -m pytest                             # 27 semantic/property tests

python scripts/validate_theorem1.py          # numerical sanity check for Theorem 1
python scripts/run_trace.py                  # operator-search + repair runtime trace
python scripts/run_comparison.py             # all 6 methods through one harness
python scripts/compare_known_event.py        # fair control: anticipated events
python scripts/compare_novel_composition.py  # novel compound event (the key result)
```

## Architecture

Every method runs through the **same** `Executor` + `Synthetic2DEnv` (shared
dynamics, control limits, event stream, horizon, seed, metric logger). Methods
differ only in the plugged-in `RecoveryPolicy`. The online method **synthesizes**
its repair program at runtime by searching over atomic typed operators — no
complete event-specific sequence is stored:

```
observation -> EventDetector -> capture Continuation (kappa_t)
  -> induce AbstractState from the world (compound disturbances included)
  -> RepairPlanner: SEARCH over typed operators (precondition/effect/cost)
       goal = event resolved AND restore contract achievable
  -> LegalityFilter  (acyclic + HasRestore + attachment-consistent)
  -> FeasibilityFilter (handoff reachability under control limits)
  -> Scorer/select    (L_event + edit + restore + realign + complexity)
  -> TaskProgram.interrupt_active_stage + splice_repair_before_successor
  -> execute repair stages -> validate restore contract -> resume continuation
  -> (else) bounded SafeFallback
```

`TemplateRepairPolicy` swaps the planner for prewritten templates, isolating
**synthesis vs. instantiation**. See [docs/PARADIGMS.md](docs/PARADIGMS.md) for
the three-way distinction and the honest scope of the "novel" claim.

The interrupted stage is `SUSPENDED` (never `COMPLETED`); the nominal successor
is unreachable until the repair stages finish, the restore contract validates,
and the `RESUMED` instance completes — enforced by an explicit `StageState`
machine, not by convention.

```
rekep_repair/
  program/     StageSpec+StageState, TaskProgram (state machine, splice), Continuation, TaskGraph, contracts
  events/      Event/EventType, predicates, EventDetector (+NoiseModel)
  repair/      operators, template_library, candidate(+generator), legality/feasibility filters, scorer, repair_manager
  execution/   context, Synthetic2DEnv driver, controllers, guard_monitor, executor, fallback, provenance_logger
  policies/    fixed_program, path_only, safe_stop, offline_recovery, online_repair
  synthetic/   dynamics (SceneConfig/Obstacle/Rollout+metrics), env, conflict_bound (Theorem 1)
tests/         program semantics, repair filters, execution properties (pytest)
scripts/       validate_theorem1, run_trace, run_comparison, compare_offline_online
docs/          THEOREM.md (analytic proof), GPU_SETUP.md (planned)
```

See `docs/THEOREM.md` for the analytic development and `main.tex` (write-up) for
the full formulation.

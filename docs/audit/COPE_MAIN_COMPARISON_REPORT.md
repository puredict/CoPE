# CoPE Main Comparison Implementation and Readiness Report

Date: 2026-07-24

Branch: `exp/cope-main-comparison`
Base commit: `570d78333ee977c8ae6de3d97120b23272c4c660`

This report distinguishes infrastructure evidence from empirical robot
learning results. No fixture or fake-provider outcome in this branch is a
method result.

## Source and dependency audit

- The independent clone began clean at remote `master`
  `570d78333ee977c8ae6de3d97120b23272c4c660`.
- No `AGENTS.md` exists in the repository or its task-local parent.
- An initial HTTPS `git ls-remote` check returned only `master`; the requested
  dependency branches were not published remotely at audit time.
- Therefore the only atlas connected in this branch is
  `tests/fixtures/disturbance_atlas_v1.fixture.jsonl`
  (`atlas_commit=fixture-atlas`, explicitly `fixture=true`).
- A read-only check found an in-progress, uncommitted atlas worktree with the
  intended tasks `[1, 3, 4, 6, 8]` and seeds `[7, 8, 9]`; the main config is
  aligned to those choices. That draft currently has only 5 state slots (75
  base pair keys), 1,875 clean/disturbance-grid rows, and
  `pending_simulator_audit` geometry records. It cannot satisfy the required
  8 states/task, 120 locked main pair keys, or committed-geometry gate and was
  not copied into production inputs.
- A clean local `method/cope-state-semantics` branch later became available at
  source commit `fd0e2c501342ed7226360ae63c14615a1fc44c65`. It was integrated
  by cherry-pick with source attribution; its immutable state model, seven
  operations, authority checks, serialization, replay, and schemas are now in
  this branch.
- `cope/state_engine_adapter.py` is a thin mapping/compiler layer over that
  engine. Production transitions still go exclusively through the engine's
  atomic `apply_patch`; the main experiment code does not reimplement state
  semantics.
- Unit tests continue to use `tests.fakes:ProtocolFakeEngine` where isolation
  is useful, but formal readiness now resolves the real engine adapter and
  records source commit `fd0e2c5`.

## Implemented interfaces and methods

- `cope/providers/base.py` defines the provider-neutral
  `HighLevelRecoveryProvider.regenerate()` and `.patch()` interface.
- `cope/types.py` schema-validates full-state outputs and the seven typed patch
  operations.
- `cope/engine.py` enforces stable constraint fields, unaffected-slot
  preservation, and successful `Revalidate` before `Restore`.
- `cope/state_engine_adapter.py` maps provider JSON to one atomic committed
  engine patch and compiles accepted active constraints for the controller.
- `cope/methods/` implements adapters for all six ranked conditions.
- `cope/libero_backend.py` contains one shared LIBERO/OpenVLA rollout path for
  all six methods and reuses `libero_experiment_core.py` for model actions,
  disturbance mutation, fresh observations, success semantics, and budgets.
- `cope/runner.py` preregisters the Cartesian pair matrix, writes an fsync'd
  unique `(pair_key, method)` ledger, resumes without duplicate counting, and
  refuses incomplete or unfair pairs.
- `experiments/cope_main_comparison.py` provides pilot/formal/detected CLI
  entry points and emits a machine-readable readiness report and schedule.
- `tools/analyze_cope_main_comparison.py` implements task-clustered bootstrap
  95% intervals, exact paired McNemar tests, Holm correction, task/state
  random-intercept logistic analysis, all-pairs and clean-success-conditioned
  summaries, secondary cost/safety/state metrics, detector metrics, and
  oracle-to-detected drops.

All records retain exact controller prompts and prompt traces, a versioned
template-bundle hash, provider raw request/response/parsed output, token and
retry state, constraint states, typed operations, revalidation evidence,
source/config/checkpoint identity, and artifact paths. Secret-like provider
log keys are rejected.

## Fairness and correctness gates

The automated gates cover:

- exact six-condition order;
- deterministic stable pair keys and complete Cartesian selections;
- identical initial-state hash and pre-event action digest;
- identical event packet and fresh-observation hash across disturbed methods;
- identical total and post-event policy budgets;
- identical provider/model/retry/token fingerprint for regeneration and CoPE;
- exactly one common `RecoveryInput` hash across disturbed methods;
- fake provider/engine/atlas/backend rejection in formal mode;
- reset/rollback/manual-interaction prohibition;
- timeout never counted as success;
- typed patch schema and blind-restore rejection;
- unaffected-slot preservation;
- contiguous JSONL/action/video indices and real-video frame-count checking;
- interruption/resume without duplicate ledger entries;
- traceable config hash, Git commit, checkpoint ID/digest, atlas commit, and
  engine commit.

Fixture execution completed 4 pair keys x 6 methods = 24 synthetic episodes
using the integrated `fd0e2c5` engine adapter (the rollout backend, observation,
provider, and atlas remained explicit test fakes).
The runner reported 24 unique episode keys, all four six-condition pair
validators passed, and a second resume pass executed zero new episodes. The
analysis output marks these records `test_only=true`,
`paper_evidence_eligible=false`, moves synthetic values under
`synthetic_pipeline_check`, and does not evaluate the preregistered threshold.

## Commands and observed results

```text
/Users/lijingsu/miniforge3/envs/lerobot312/bin/python -m py_compile ...
exit 0

/Users/lijingsu/miniforge3/envs/lerobot312/bin/python -m pytest -q
189 passed in 27.66s

python experiments/cope_main_comparison.py --phase pilot ... \
  --validate-only --emit-schedule --allow-test-fixtures
exit 0; selected_pair_count=4; scheduled_episode_count=24;
test_only=true; rollout_authorized=false

fixture ComparisonRunner dry-run
pair_count=4; episode_count=24; complete=true; validation.passed=true

python tools/analyze_cope_main_comparison.py ... --phase pilot
exit 0; analysis_complete=true; test_only=true;
paper_evidence_eligible=false

python experiments/cope_main_comparison.py --phase formal ... \
  --validate-only --allow-test-fixtures
exit 2 as required; formal readiness false
```

The full test command is authoritative; the compact `py_compile` command is
rerun before handoff.

## Empirical run status and values

| Run | Required episodes | Real episodes completed | Status |
| --- | ---: | ---: | --- |
| Infrastructure pilot | 24 | 0 | Blocked before empirical launch |
| Oracle formal | 720 | 0 | Blocked before launch |
| Detected sensitivity | at least 180 for the frozen 30-pair selection | 0 | Blocked before launch |

There are no real success rates, confidence intervals, paired gains, detector
precision/recall/latency, safety comparisons, or failure videos from this
main comparison. The preregistered 10 percentage-point gain and positive-CI
lower-bound threshold is **not evaluated**. Synthetic fixture values are not
listed here because doing so would manufacture an apparent experimental
result.

Existing repository reports about task-0 clean/disturbed pilots and the
single prompt-only canary remain prior evidence only. They do not instantiate
full regeneration or CoPE and are not included in this study.

## Formal blockers

1. Official `disturbance_atlas_v1.jsonl` and its real
   `exp/disturbance-causal-atlas` commit are absent. The observed draft still
   needs three additional state slots per task and completed geometry audits
   before it can produce the 120-key main lock.
2. The committed engine is integrated, but no real observation-grounded
   revalidation validator adapter/commit is supplied. Formal mode rejects the
   current null validator configuration.
3. No real high-level provider adapter/service configuration is supplied.
4. The configured Linux checkpoint path is absent on this host and its
   SHA-256 is not frozen.
5. This host has no CUDA GPU available to the selected runtime.
6. `statsmodels` is missing from the selected test runtime, so the mandatory
   mixed-effects analysis cannot yet run there.
7. A formal run must be launched from a clean committed worktree after all
   dependency commits and environment manifests are frozen.

## Failure cases and systematic issues

- No empirical episode ran, so there are no valid CoPE/full-regeneration
  failure cases to classify.
- The first system Python lacked `pytest`; tests were executed in the existing
  `lerobot312` environment instead.
- An early analysis invocation by file path exposed a root-import bug; both
  experiment and analysis CLIs now support direct-file and `-m` invocation.
- Initial synthetic analysis displayed fake success numbers. The analyzer was
  hardened so fake/fixture inputs cannot populate empirical result fields or
  evaluate the preregistered threshold.

## Paths

- Frozen config: `configs/cope_main_comparison_v1.yaml`
- Main runner: `experiments/cope_main_comparison.py`
- Analysis: `tools/analyze_cope_main_comparison.py`
- Engine contract: `cope/engine.py`
- Integrated engine adapter: `cope/state_engine_adapter.py`
- Integrated engine semantics: `cope/operations.py`, `cope/schema.py`
- Unified validation: `cope/validation.py`
- Fixture atlas: `tests/fixtures/disturbance_atlas_v1.fixture.jsonl`
- Pilot dry-run readiness: `docs/audit/cope_main_pilot_dry_run_readiness.json`
- Pilot synthetic schedule: `docs/audit/cope_main_pilot_schedule.jsonl`
- Formal blocked readiness: `docs/audit/cope_main_formal_readiness.json`
- Ignored synthetic dry-run artifacts:
  `audit_outputs/cope_main_fixture_dry_run_v4/`

## Supported and unsupported claims

Supported:

- the comparison infrastructure schedules the requested paired matrix;
- fake dependencies cannot enter formal execution;
- the common provider input, budget, controller, event, and pairing
  invariants are machine-checked;
- typed patches are schema-checked and blind restore is guarded;
- the integrated `fd0e2c5` engine passes its atomicity, invariant, schema,
  replay, golden-scenario, counterexample, and property-sequence tests;
- synthetic 24-episode orchestration, validation, resume, and analysis code
  paths execute successfully.

Not supported:

- CoPE improves task success or recovery over any baseline;
- CoPE preserves progress better than full regeneration;
- any preregistered threshold is met;
- detected events are accurate or preserve oracle performance;
- the method generalizes across LIBERO tasks, states, or seeds.

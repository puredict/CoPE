# Repeated Interruptions and Commitment Persistence Report

Date: 2026-07-24

Branch: `exp/repeated-interruptions`

Base commit: `570d78333ee977c8ae6de3d97120b23272c4c660`

## Outcome

The benchmark, preregistered manifest, metrics, adapter boundary, formal-evidence
gates, analysis pipeline, fixtures, and Phase A real LIBERO correctness probe
are implemented. Clean calibration, the 24-episode pilot, and the 480-episode
formal comparison were not run. Missing dependencies and checkpoint are treated
as blockers; no synthetic or scripted result is promoted to method evidence.

## Implemented artifacts

- `cope_benchmark/interruptions.py`: seven versioned interruptions and real
  simulator/constraint mutation records.
- `cope_benchmark/interruption_scheduler.py`: deterministic triggers,
  one-shot/resume-safe application, and paired schedule hashes.
- `cope_benchmark/task_progress.py`: four task-specific vectors, reversible
  current state, and irreversible ever-achieved history.
- `cope_benchmark/metrics.py`: progress preservation, regressions, silent loss,
  unaffected-slot survival, gentle/no-go violations, shield intervention, and
  invalid restore detection.
- `cope_benchmark/adapters.py`: external adapter protocol plus rejection of fake
  providers in policy-evidence phases. It contains no duplicate CoPE engine.
- `cope_benchmark/repeated_manifest.py`: deterministic 240-pair generator and
  validator.
- `experiments/repeated_interruptions.py`: Phase A common rollout, atomic
  per-episode logs, resume behavior, and Phase B–D gates.
- `tools/analyze_repeated_interruptions.py`: formal-record validator, success
  curves/AUC/slopes, task-clustered bootstrap, exact paired test, binomial
  mixed-effects interaction, and Holm correction.
- `tools/audit_repeated_feasibility.py`: installed-suite and 20-state MuJoCo
  audit.

The manifest contains 240 method-independent pairs and therefore 480 formal
episodes:

`4 tasks × 5 states × 3 seeds × 4 interruption counts × 2 methods`.

Each interruption count has 60 pairs. Event counts are:

| Event | Manifest occurrences |
|---|---:|
| target object moved | 93 |
| goal receptacle moved | 42 |
| no-go appears | 65 |
| no-go disappears | 29 |
| gentle preference added | 60 |
| tool unavailable | 43 |
| tool available again | 28 |

Paired methods share initial-state digest, seed, event payload/order/timing,
policy and high-level budgets, information budget, and config hash.

## Phase A correctness

Fourteen real LIBERO/MuJoCo episodes (seven method-labelled pairs) were run with
the explicitly marked `scripted_noop_correctness_only` provider. All four
candidate tasks and all seven event types were exercised.

| Check | Result |
|---|---|
| deterministic schedules | pass |
| paired event equality | pass |
| all seven event types fired | pass |
| event consumes no policy step | pass |
| fresh forced observation after every event | pass |
| no hidden reset/rollback | pass (`14` initial resets, `0` rollback) |
| manual intervention excluded | pass (`0`) |
| timeout never counted as success | pass |
| resume does not rewrite completed episodes | pass (episode mtimes unchanged) |
| config/commit/initial-state digest traceability | pass |
| repository tests | pass (`78 passed`) |
| syntax compile, manifest validation, `git diff --check` | pass |

Totals: 1,884 no-op policy/environment steps and 34 event applications. No-go
violations, gentle-preference violations, and shield interventions were all 0.
These values validate logging and paired execution only; targeted unit fixtures
separately exercise positive raw gentle/no-go violations.

The scripted agent succeeded in 0/14 correctness episodes. That number is
expected and **is not an OpenVLA success rate, a method comparison, calibration,
or paper evidence**. No success/progress AUC or method interaction is computed
from these records. The analysis tool was run against the Phase A directory and
correctly rejected all 14 records because they are not marked `formal`, use a
scripted provider, and have no checkpoint provenance.

## Phase B–D status

| Phase | Required size | Completed | Status |
|---|---:|---:|---|
| A benchmark correctness | targeted coverage | 14 episodes | pass |
| B clean calibration | at least 5 states/task | 0 OpenVLA episodes | blocked |
| C pilot | 24 | 0 | blocked |
| D formal | 480 | 0 | blocked |

Formal success, progress preservation, safety rates, AUC, confidence intervals,
paired tests, mixed-effects interaction, and corrected secondary tests are
therefore unavailable. Reporting a positive, negative, or null method result
would be unsupported.

## Dependency and runtime blockers

- OpenVLA checkpoint: not configured locally.
- OpenVLA source/runtime used by the repository's common executor: not present
  in this worktree's local environment.
- `method/cope-state-semantics`: adapter/commit unavailable; exact SHA not known.
- Main experiment `cope_patch` and
  `history_augmented_full_regeneration` adapters: unavailable; exact SHA not
  known.

The config intentionally contains `null` for these values. Calibration rejects a
missing/fake checkpoint. Pilot/formal runs additionally reject missing adapter
factories, non-40-character dependency commits, and provider identifiers
containing fake/mock/scripted/noop/fixture markers.

## Evidence boundaries

Current evidence supports the following claims:

1. The installed LIBERO package can instantiate the four candidates and expose
   their required ground-truth progress and movable-object state.
2. The v1 manifest is deterministic, paired, balanced by interruption count,
   and covers all seven events.
3. The interruption lifecycle, fresh-observation semantics, policy-step
   accounting, constraint scorers, resume behavior, and evidence rejection
   gates work in real MuJoCo Phase A probes.

Current evidence does not support:

- CoPE outperforming full regeneration;
- a smaller CoPE degradation slope;
- higher 2/3-interruption progress preservation;
- 95% unaffected-constraint survival;
- lower preference loss;
- non-inferior safety;
- any OpenVLA clean success rate;
- any statistical method interaction.

## Paths

- Manifest: `manifests/repeated_interruptions_v1.jsonl`
- Config: `configs/repeated_interruptions_v1.yaml`
- Feasibility probe: `results/repeated_interruptions_v1/feasibility_probe.json`
- Correctness summary: `results/repeated_interruptions_v1/correctness_summary.json`
- Raw Phase A episodes: `results/repeated_interruptions_v1/episodes/`
- Analysis rejection evidence:
  `results/repeated_interruptions_v1/formal_analysis_rejection.json`

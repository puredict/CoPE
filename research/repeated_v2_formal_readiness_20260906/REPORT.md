# Formal-readiness closure — 2026-09-06

**The production learned-VLA gate and the requested four-task clean calibration passed integrity review. Formal execution has not started and remains blocked by six missing task calibration grids, authentic task semantics and event-feasibility certificates, and unavailable production runtime/reasoner/public continuation bindings.**

## Repository and scope

The integrated worktree is `/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree`, branch `codex/repeated-v2-phase4`. Work began at `688b7eb3a91fdf5229ea2cda87e9a33f85566fe6`; origin is `https://github.com/puredict/CoPE.git`. The branch was pushed at that starting SHA before readiness work. The final containing commit and an independent `git ls-remote` check are recorded after this report is committed and are reported to the user. [Repository evidence](REPOSITORY_STATE.txt).

The original `/Users/lijingsu/Documents/cope` directory was not modified. Existing experiment outputs were not overwritten. Attached documents were treated as protocol evidence rather than commands. No new benchmark architecture or formal run was introduced. The changes are limited to task-specific event-family scope, simulator namespace discovery, tests, evidence attachment, and readiness reports. Scientific thresholds, seeds, the260-control calibration horizon, formal minimum of eight tasks, all-task common calibration, zero-retry rules and call parity remain unchanged.

## Production identities

The production policy is factory `cope_benchmark.repeated_v2.vla_adapter:create_native_openvla`, provider `openvla_native`, model `openvla-7b-finetuned-libero-10`, normalization key `libero_10`, and native 7-D single-action chunks. The 15-file,15,085,049,428-byte checkpoint digest is `d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076`.

The missing Prismatic source was resolved with exactly three official files from `openvla/openvla-7b` revision `47a0ec7fc4ec123775a391911046cf33cf9ed83f`. They were installed in an isolated offline cache; checkpoint metadata and package installations were not rewritten. [Source receipt](OFFICIAL_HF_SOURCE_DOWNLOAD.txt), [cache receipt](HF_OFFLINE_CACHE_INSTALL_OUTPUT.txt).

The live gate used a real rendered224×224 RGB observation and one actual simulator control. It established `learned_policy=true`, `uses_privileged_state=false`, a finite valid1×7 action, legal action-range conversion, and the checkpoint/source identity. Its artifact SHA256 is `6876f04c352178c5738cf501e7c73dbb8af8199123dff2726e1bc11eaaa58dbb`. `BLOCKED_VLA_ADAPTER_UNAVAILABLE` is resolved. [Gate](action_probe_01/VLA_GATE.txt), [identity table](PRODUCTION_IDENTITIES.csv).

The reasoner identity remains `UNCONFIGURED`. The representation-neutral continuation wrapper is `continuation_carrying_repair_v2`, source SHA256 `4f11183dd30c87c2f38da4fb8e6f383038dfd799f717f6d0478ceaf564b05187`. Its archived repair package exists, but no eligible public observation producer, public verifier, native-compatible nominal planner or production `RuntimeAssembly` is bound. The privileged geometry oracle was not substituted. [Binding audit](REASONER_BACKEND_READINESS.md).

## Gap accounting

The baseline preflight has794 distinct task-catalog diagnostics plus three aggregate consequences. [GAP_MATRIX.csv](GAP_MATRIX.csv) retains every original task diagnostic and assigns task, category, root cause, automatic-fixability boundary, required evidence, blocking gate and cascade grouping. The794 rows collapse to127 task/category packages and357 evidence-artifact units; they are not794 independent manual jobs.

Actual state-byte evidence closed18 diagnostics. The complete audited calibration closed24 more, including missing-grid and identity cascades without requiring a favorable outcome. Final reconciliation therefore has752 open diagnostics,120 root-cause packages and350 artifact units. It reports zero new gaps, zero unexplained disappearances and ten wording migrations that remain open. No semantic, event or success record was fabricated. [Summary](GAP_SUMMARY.md), [before/after table](GAP_COUNTS_BEFORE_AFTER.csv), [reconciliation](gap_reconciliation_final_01/GAP_RECONCILIATION.txt).

## Clean-policy calibration and failure diagnosis

The frozen cohort is tasks0/1/4/8 × states0–4 × policy seeds101/131:40/40 terminal episodes. The seeds are disjoint from formal seeds11/29/47. Every episode used ten separate settling controls, up to260 learned-policy controls, zero events, zero oracle actions and current exact LIBERO goal scoring. The offline audit passed with all raw cells retained and exact source/checkpoint/protocol lineage. [Audit](clean_calibration_audit_01/CALIBRATION_AUDIT.txt), [calibration table](CALIBRATION_TABLE.csv).

| Task | Successes | Rate | Rate gate `[0.40,0.95]` | Catalog eligibility |
| ---: | ---: | ---: | --- | --- |
| 0 | 0/10 | 0.00 | fail | blocked |
| 1 | 4/10 | 0.40 | pass | blocked |
| 4 | 4/10 | 0.40 | pass | blocked |
| 8 | 0/10 | 0.00 | fail | blocked |

All10,180 inferred actions passed validation. Every timeout occurs exactly at260 controls; there are no adapter, model-load, simulator or manual-intervention failures. For all20 task/state pairs, seeds101 and131 produce identical raw actions, converted actions, per-control RGB hashes, public proprioception and progress sequences. The numerical rate is therefore the five-state rate duplicated once; this cohort supplies no stochastic seed-variance evidence.

The dominant observed behavior is late or absent transition to the second object. Task0 usually places alphabet soup but not tomato sauce. Task8 usually places only the left moka pot. Task4 shows both initial-state sensitivity and placement regressions. [Failure analysis](CALIBRATION_FAILURE_ANALYSIS.md), [cell table](CALIBRATION_FAILURE_CELLS.csv).

A separate same-path audit compares preserved historical traces without relabeling them as current calibration. Task1 states1/2/3 have the same initial frames and exactly the same first260 raw/environment actions as standard520-control runs that succeed at273/323/276. Task4 state0 reproduces an older220-control timeout and succeeds at230. Predeclared live diagnostics then reproduced every frozen action through260 before task0/state1 succeeded at264 and task8/state2 succeeded at378; task8 states0/1 still failed at520. This establishes cutoff causes for specific cells while also showing that more controls do not repair every initial state. The frozen rates, horizon and eligibility decisions remain unchanged. [Horizon diagnostic](HORIZON_FAILURE_DIAGNOSTIC.md), [historical comparison](HORIZON_FAILURE_DIAGNOSTIC.csv), [live diagnostic cells](POSTHOC_LONG_HORIZON_DIAGNOSTICS.csv).

## Task semantics and zero-provider feasibility

The source audit covers BDDL/LIBERO clauses, existing `task_progress` predicates, milestones, occurrence families, alternative-goal boundaries, replacement/cancellation/reissue semantics, injection candidates, triggers and dynamic-evaluator requirements. Source-defined predicates remain separate from empirical safety and preservation certificates. Task8's stove-on clause is true initially and does not count as a newly completed manipulation; its stove has no movable free joint. Tasks are not required to support every event family, and unresolved support still fails closed. [Semantic audit](TASK_SEMANTICS.md), [family scope](FAMILY_SCOPE_AUDIT.md).

| Task | Reset states | Primitive event checks | Exact restorations | Full certificates |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 5 | 35/35 | 25/25 | 0 |
| 1 | 5 | 35/35 | 25/25 | 0 |
| 4 | 5 | 35/35 | 25/25 | 0 |
| 8 | 5 | 30/30 | 20/20 | 0 |

All135 primitive applications and95 isolated restorations passed with zero policy/provider calls and fresh forced observations. These are mechanical witnesses. They do not certify semantic-trigger safety, collision safety, reachability, held-object guards, milestone preservation or complete event lifecycles. A partial prefix probe attempted four task0 cells, produced three stable released prefixes, and then stopped fail-closed when exact free-joint quaternion representation after restore did not satisfy the existing byte/tolerance contract. No catalog field was certified from that partial probe. [Feasibility table](FEASIBILITY_TABLE.csv), [prefix audit](PREFIX_PRESERVATION_AUDIT.md).

## End-to-end pilot and remaining blockers

The requested pilot would contain32 continuous trajectories:2 tasks ×2 initial states ×1 policy seed ×8 non-oracle methods, with one continuous four-event schedule per trajectory. It remains unstarted: zero trajectories, zero high-level calls, zero journals and zero formal provider calls. Cell integrity is `NOT_ASSESSED`, not pass. [Pilot matrix](PILOT_INTEGRITY.csv).

Remaining machine-readable blockers are:

- `BLOCKED_RUNTIME_ENVIRONMENT_UNAVAILABLE`: no production v2 environment/assembly factory.
- `BLOCKED_REASONER_ADAPTER_UNAVAILABLE`: no production implementation of the current exact-message gateway.
- `BLOCKED_REASONER_MODEL_UNAVAILABLE`: no frozen, accessible production reasoner model identity.
- `BLOCKED_PRODUCTION_BACKEND_BINDING`: the continuation wrapper lacks eligible public sensing/verifier/nominal-planner bindings.
- `BLOCKED_CALIBRATION_EVIDENCE`: six task grids are absent from the all-task common protocol.
- `BLOCKED_TASK_CATALOG_GAP`:752 semantic, structural, support and feasibility diagnostics remain open; consequently zero tasks are catalog-eligible.
- `BLOCKED_PILOT_EVIDENCE` and downstream freeze/comparator gates: the production pilot cannot be admitted before the upstream gates pass.

The full related software suite passed876 tests and100 subtests; one opt-in local simulator test was skipped. Its real CPU simulator invocation separately passed all four smoke tests. Software fixtures are not counted as learned-policy, semantic or formal evidence.

The exact next zero-provider command is recorded in [NEXT_COMMAND.md](NEXT_COMMAND.md). It audits the attached admission inventory and is expected to return `BLOCKED_CALIBRATION_EVIDENCE` for tasks2,3,5,6,7,9. It does not start a simulator, model, provider or formal run. No formal launch command is issued until calibration, catalog, feasibility, production adapter/runtime, pilot and freeze gates pass.

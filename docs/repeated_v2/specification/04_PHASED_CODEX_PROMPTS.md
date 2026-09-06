# Phased Codex Prompts

Use these as separate Codex windows if the master prompt is too large.

---

## Window 1 — Audit, schemas, task catalog, schedules, preflight

Work on `puredict/CoPE`. Read the v1 repeated-interruption code and frozen result documents. Create the isolated `cope_benchmark/repeated_v2` family. Implement enums, data schemas, canonical JSON/hashes, task catalog/calibration, event records, hidden/public separation, semantic trigger scheduler, occurrence allocator, master manifest, and zero-provider preflight. Add tests for deterministic schedules, prefix legality, task eligibility, occurrence reissue, event leakage, and exact expected counts. Do not implement provider or VLA calls yet. Do not modify frozen v1 artifacts. Use the scientific protocol and config in this package as binding requirements.

Stop only after:
- all existing tests pass;
- all new phase-1 tests pass;
- preflight is deterministic;
- task catalog gaps fail closed;
- event injection cannot mutate any arm state.

Commit phase 1 and report SHA.

---

## Window 2 — Method adapters, prompts, parsers, state engines, compiler

Continue from phase-1 SHA. Implement all eight non-oracle arms plus oracle upper bound. Implement CoPE typed transactions, information-equivalent generic transactions, full-state regeneration, full-history replanning, public-history-only RAG, free-text summary memory, skill-local replanning, and classical execution monitoring. Implement same-backbone prompt contracts, exact prompt logging, recursive leakage scans, semantic information parity, deterministic CoPE/generic engines, protected projection hashes, edge-type-specific invariants, and pure planning compiler. Add oracle fixtures and parser negative tests.

Important:
- do not use legacy `DEMOTED` as lifecycle in v2;
- `Revalidate` is a check/evidence record, not ordinary mutation;
- unmentioned slots remain unchanged;
- compiler may never repair omitted semantics;
- all generative arms receive one event-level reasoner call.

Implement the controlled mechanism backend and run a no-provider oracle-fixture smoke. Commit and report SHA.

---

## Window 3 — VLA execution, continuation backend, evaluator, durable runner

Continue from phase-2 SHA. Implement the VLA plugin protocol and formal gates. Search the workspace for a production OpenVLA/OpenVLA-OFT client and wrap it without privileged simulator state. If unavailable, leave a complete factory interface and report `BLOCKED_VLA_ADAPTER_UNAVAILABLE`; do not substitute oracle execution.

Wrap the continuation-carrying repair code, if available, behind a representation-neutral planner backend. It may compile accepted state to RepairGoal, search/verify recovery, and splice/resume, but may not read canonical truth or repair baseline omissions.

Implement the full runtime loop, event-boundary snapshots, fresh post-event observations, continuous method-specific state, common executor, action traces, sealed dynamic evaluator, durable at-most-once journal, crash-safe resume, and integrity statuses. Add mocked integration tests and simulator smoke tests. Run pilot controlled and pilot VLA if dependencies are available. Commit and report SHA.

---

## Window 4 — Statistics, analysis, freeze, formal run

Continue from phase-3 SHA. Implement integrity-first analysis, paired risk differences, exact McNemar, master-session cluster bootstrap, Wilson intervals, degradation slopes, Holm correction, and CoPE-vs-generic non-inferiority. Implement paper tables/curves, failure taxonomy, and binding GO/PARTIAL/NO-GO logic.

Freeze git/config/catalog/manifest/prompt/schema/model/checkpoint/backend hashes before any formal call. Create deterministic 8-way shards. Run formal controlled and formal VLA protocols only if all gates pass. Never fabricate or delete result cells. Produce `REPORT.md` and `CLAIM_DECISION.md` with paper-safe and forbidden claims.

Commit analysis code before formal results, then commit result artifacts separately.

# Final formal readiness and submission decision

Date: 2026-08-04
Authoritative code commit: `49fa2da2fa39cf12095bb11beb4e96837690c1e6`
Branch: `codex/shared-commit-envelope`

## Bottom line

**Formal code readiness: PASS. Live learned evidence: BLOCKED. Paper status:
weak reject / HOLD.** The decisive experiment can start immediately after a
securely injected, rotated credential passes the single-draw operational
smoke. No learned occurrence or embodied formal outcome exists yet.

## Final verification

- complete repository regression: 633 passed;
- worktree: clean after the code commit;
- strict whole-response JSON object parser: enabled;
- non-finite JSON constants, malformed usage/message types, and noninteger or
  negative token counts: rejected;
- provider envelope errors separated from model JSON failures;
- file and directory fsync ordering: enabled;
- at-most-once intent -> response -> result recovery: enabled;
- first infrastructure failure: persisted, frozen, exit 4, no later calls;
- result CSV bound to manifest metadata and durable recovery journals;
- machine-readable neutral/governed joint decision: enabled;
- OpenRouter public catalog: exact frozen model ID present at audit time;
- credential/key prefix in current tree and reachable history: not found.

On the final clean code commit, with `OPENROUTER_API_KEY` explicitly unset:

| Entry point | Exit | Provider calls | Cases/states materialized | Simulator states |
|---|---:|---:|---:|---:|
| operational smoke | 3 | 0 | 0 | 0 |
| occurrence formal | 3 | 0 | 0 | 0 |
| embodied formal v2 | 3 | 0 | 0 | 0 |

## Scientific decision order

1. one task-independent operational smoke;
2. 200-call occurrence learned formal;
3. journal-bound analysis requiring both neutral and governed efficacy,
   locality, and safety gates;
4. only after exact symbolic PASS, at most 400 task-0 embodied-v2 calls;
5. embodied journal-bound analysis, still labeled single-task evidence.

Any smoke failure, infrastructure stop, retry, neutral failure, or governed
failure halts the method-paper path. FSR-PC/full-replan cannot rescue it.

## Research conclusions already fixed

- Architecture-first novelty is NO-GO after Tang et al. 2026.
- Occurrence IDs/event histories/commitment lifecycles are prior art.
- Generic transactions can be compact, atomic, and fail-closed.
- Typed operations reduce the tested commission-error surface but do not solve
  omission completeness without assurance.
- The task-7 physical recurrence line failed at state 2 and remains stopped;
  it cannot be reported as successful embodied evidence.
- The only remaining positive method hypothesis is learned first-pass exact
  occurrence-contract conformance and locality versus both primary sparse
  controls.

## Why the formal result is still necessary but not sufficient

The 40 cases are one symbolic template family over seven fixed object names.
The efficacy gate is intentionally demanding and has low sensitivity near the
minimum RD threshold. A PASS would demonstrate a large fixed-benchmark effect;
a NO-GO would fail the preregistered method claim but would not prove zero
effect everywhere. A symbolic PASS still needs task/model/controller
replication and cannot establish deployment safety.

## External blocker

The credential pasted in conversation was not reused or stored and should be
revoked/rotated because it was exposed in chat. A new credential must be
entered under personal account `lijingsu` through a non-argv, non-log process
environment. This action requires user authority; creating, recovering, or
silently reusing a credential is outside the permitted research workflow.

## Authoritative handoff

- exact execution commands and stop rules:
  `research/143_END_TO_END_FORMAL_LAUNCH_CHECKLIST.md`;
- current claim ceiling: `research/148_PAPER_CLAIM_STACK_CURRENT.md`;
- old/new evidence precedence:
  `research/147_CURRENT_EVIDENCE_SUPERSESSION_INDEX.csv`;
- statistical boundary and sensitivity:
  `research/140_OCCURRENCE_STATISTICAL_GATE_FEASIBILITY.md` and
  `research/150_OCCURRENCE_EFFICACY_POWER_SENSITIVITY.md`;
- final runner/analyzer integrity:
  `research/146_FORMAL_CSV_JOURNAL_BINDING_AUDIT.md` and reports 153--158.

No task-1 state 33 retry occurred, task-1 states 34--49 were not indexed, and
task-7 states 3--49 remain unopened under the stopped controller line.

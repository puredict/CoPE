# Window 2 verification

Window 2 is complete. All eight non-oracle adapters and the privileged oracle
upper bound are implemented and exercised through the controlled backend.

- Branch: `codex/repeated-v2-phase2`.
- Phase-1 parent: `b8462c28424d6551ab1713e67d68f42ca149b55f`.
- Worktree: `/Users/lijingsu/Documents/cope_repeated_v2_phase2_worktree`.
- Status: `PASS_WINDOW_2_QUALIFICATION`. This is not a formal scientific GO.
- The implementation and all qualification evidence are committed together;
  resolve this report's containing commit to obtain the phase-2 SHA.

## Validation results

| Check | Result |
|---|---|
| Phase-2 tests | 157 passed |
| Combined v2 tests, local | 328 passed (171 phase 1 + 157 phase 2) |
| Full server regression | 965 passed (637 existing + 328 v2) |
| Full local regression | 964 passed; one existing Linux-asset-dependent test fails on macOS |
| Oracle-fixture smoke | 72 accepted and symbolically executed cells, 9 arms x 8 events |
| Fixture reasoner calls | 56, exactly one per event for each of 7 generative arms |
| External provider calls / VLA calls | 0 / 0 |
| Missing / duplicate / unexpected smoke cells | 0 / 0 / 0 |
| Privileged oracle cells | 8, explicitly marked |
| Persistent input information parity | Matched at every fixture event |
| Source correspondence | All 24 new code/test/schema files matched SHA256 on the server |
| Frozen v1 modifications | None |

The local failure is
`tests/test_semantic_oracle_pilot.py::test_repository_authorization_is_narrow_and_bound_to_x04`.
It requires a frozen absolute Linux BDDL/init-state artifact. The same test passed
on the server with the authentic pinned artifacts. No test or authorization
manifest was weakened, skipped, or modified to obtain the server pass.

## Implemented behavior

CoPE and the generic transaction share deterministic invariant validation while
using distinct output contracts and identical normalized semantic inputs. The
kernel owns new IDs, preserves unmentioned slots, verifies protected slot/edge/
progress projections, checks authority and edge-specific invariants, and commits
atomically. Revalidation records evidence without mutating slots. Restoration
requires successful current evidence for the stored guard; retired occurrences
require a fresh occurrence. Priority never becomes a lifecycle status.

Full-state regeneration replaces its semantic materialization, including semantic
history, while a separate ID/family registry preserves allocation identity only.
Full-history, RAG, summary, and skill-local adapters produce the common planning
directive. RAG indexes only public history under a frozen retriever budget;
summary and directive are returned in one call. The classical monitor searches
supplied skill preconditions/effects over ordinary task facts, with no persistent
occurrence/lifecycle ledger. The oracle has a separate typed privileged input.

The shared reasoner gateway fixes the decoding contract, rejects retries for a
consumed event, validates token accounting, and logs exact prompts/responses.
Recursive scans reject hidden fields, serialized hidden content, method/condition
labels, and filesystem paths. Typed operators are allowed only in their explicit
contract; the generic interface excludes them. Token-matched persistent prompts
use a shared truncation decision so their semantic facts remain equal.

The compiler translates accepted state/directive only. Empty, missing, wrong,
or stale semantics are not recovered from task IDs, hidden truth, or public
context defaults. The controlled Boolean backend checks supplied hard constraints
and protected progress. Its explicit-skill mode executes only submitted skill
steps and never synthesizes missing actions. Initial plans and snapshot/resume
roundtrips require zero additional reasoner calls.

## Artifacts and reproduction

The CPU runtime used locally was
`/Users/lijingsu/Documents/cope_constraint_adaptation_worktree/.venv/bin/python`.
The server was `fudan-26575`, with runtime
`/home/lijingsu/vla/.venv/bin/python` and an isolated worktree at
`/home/lijingsu/codex-worktrees/cope-repeated-v2-phase2`.

From the phase-2 worktree:

```bash
python -m pytest -q
python -m pytest -q tests/repeated_v2
python tools/smoke_repeated_v2_methods.py --output-dir <new-output-directory>
```

The smoke refuses to overwrite an existing output directory. It runs entirely
without network/provider/VLA inference. The recorded fixture configuration uses
`provider=offline_fixture`, `model=oracle_answer_fixture`, and
`controlled.abstract_boolean.v1`. Its token counts are explicitly conservative
UTF-8 byte counts, not measured foundation-model token usage.

- [Implementation/API notes](PHASE2_IMPLEMENTATION.md)
- [Source, schema and configuration hashes](PHASE2_HASHES.txt)
- [Verification transcripts and source correspondence](../../research/repeated_v2_phase2_validation/README.md)
- [Exact fixture prompts/responses](../../research/repeated_v2_phase2_validation/oracle_fixture_smoke/EXACT_PROMPT_LOGS.txt)
- [Smoke event cells](../../research/repeated_v2_phase2_validation/oracle_fixture_smoke/EVENT_CELLS.txt)
- [Smoke summary](../../research/repeated_v2_phase2_validation/oracle_fixture_smoke/SUMMARY.csv)

No learned-model comparison, calibration, formal controlled run, or learned-VLA
run was performed in this window. The phase-1 real catalog remains blocked on
calibration/feasibility evidence. The smoke demonstrates implementation plumbing
and symbolic execution only; the classical smoke cells are not a claim that its
natural-language updates match the fixture oracle. Comparative model accuracy,
robot success, latency, non-inferiority, degradation, and the paper claim remain
unevaluated. Frozen v1 results and claim decisions remain unchanged.

# CoPE autonomous research closing snapshot

Date: 2026-08-04

## Decision

**Formal launch infrastructure: PASS. Live scientific evidence: not run.
Submission: weak reject / HOLD.** The method-paper path remains conditional on
one result only: first-pass exact occurrence-contract conformance and locality
against both neutral and governed sparse controls.

Architecture-level novelty is not defensible. Tang et al. occupy governed
persistent mission-state proposals and atomic verification/commit, while
AgentChord occupies semantic constraint graphs with compiled monitors and
forward-moving recovery branches that avoid online full-task-graph
regeneration for covered failures. Occurrence identity and lifecycle/event
history also have non-robotics prior art.

## Frozen implementation snapshot

- authoritative formal code commit:
  `49fa2da2fa39cf12095bb11beb4e96837690c1e6`;
- parent evidence HEAD before this snapshot was added:
  `d0ff818ae549` (the snapshot itself is a later report-only commit);
- branch: `codex/shared-commit-envelope`;
- complete CPU-only regression: `633 passed in 54.62s`;
- critical provider/recovery/runner/analyzer regression:
  `53 passed in 3.17s`;
- worktree: clean;
- diff from code commit over `cope`, `experiments`, `tools`, `tests`,
  `scripts`, and `manifests`: empty;
- evidence supersession index: 20/20 artifact paths present;
- current report relative links: valid.

No code or protocol change is authorized after this freeze unless a concrete
failure is first observed and the affected run is stopped rather than retried.

## Provider and security snapshot

- OpenRouter public model catalog returned HTTP 200;
- `qwen/qwen3.5-flash-02-23` had exactly one catalog match;
- no secure `OPENROUTER_API_KEY` was available on the server;
- current tree and reachable Git history contained no exposed provider-key
  prefix match;
- the credential pasted into chat was never reused or stored and must be
  revoked/rotated;
- no live provider call was made.

All five planned formal output directories were absent/available at the final
check. The clean no-credential probes remained fail-closed with zero provider
calls and no case, simulator-state, or formal-result materialization.

## Mandatory execution order

1. Inject a new rotated credential through the secure non-argv/non-log process
   environment described in `research/161_SECURE_CREDENTIAL_HANDOFF.txt`.
2. Run exactly one task-independent operational smoke draw.
3. On smoke PASS only, run the frozen 40-case, five-arm occurrence experiment
   (200 maximum calls).
4. Run the journal-bound analyzer. Both neutral and governed efficacy,
   locality, and safety gates must pass.
5. Only on dual-primary PASS, run the task-0 embodied-v2 experiment (400
   maximum calls), then its journal-bound analyzer.

Any provider infrastructure stop, ambiguous intent, retry requirement, smoke
failure, neutral primary failure, or governed primary failure stops the method
path. FSR-PC, full replanning, or an embodied point estimate cannot rescue a
failed occurrence primary.

## Closest-system correction made in this cycle

The latest evidence chain had failed to carry forward the repository's older
AgentChord stress audit. Reports 147, 148, 159, and 162 now explicitly restore
that boundary, and the original stress audit is present in the authoritative
worktree. Consequently:

- CoPE must not claim first structured, constraint-governed, forward-moving,
  progress-preserving, or no-full-task-replanning recovery;
- a formal occurrence PASS establishes only a narrow interface/benchmark
  result;
- an embodied submission needs native AgentChord or a faithful matched
  recovery-augmented-graph abstraction, with any infeasibility documented;
- a bounded full-information enumerated graph remains a representational
  falsifier for unique CoPE expressivity.

## Hard safety/state boundaries preserved

- task-1 state 33 was not retried;
- task-1 states 34--49 were not indexed;
- task-7 state 2 remains a failed restoration case;
- task-7 states 3--49 remain unopened;
- no GPU job, training run, large checkpoint download, or other user's process
  termination occurred.

## Paper claim ceiling

Conditional on the formal dual-primary PASS, the strongest current wording is:

> CoPE studies learned, exact occurrence-sensitive editing of persistent task
> commitments under a typed validity and locality contract, and measures when
> an assurance layer converts an otherwise fluent edit into an executable one.

Use no priority claim without a broader systematic search. A symbolic PASS is
necessary but insufficient for ICRA; a symbolic failure stops the current
learned-method paper.

## Authoritative files

- launch commands and hard stops:
  `research/143_END_TO_END_FORMAL_LAUNCH_CHECKLIST.md`;
- supersession chain:
  `research/147_CURRENT_EVIDENCE_SUPERSESSION_INDEX.csv`;
- claim ceiling: `research/148_PAPER_CLAIM_STACK_CURRENT.md`;
- final readiness decision:
  `research/159_FINAL_FORMAL_READINESS_AND_SUBMISSION_DECISION.md`;
- secure handoff: `research/161_SECURE_CREDENTIAL_HANDOFF.txt`;
- nearest embodied neighbor:
  `research/162_AGENTCHORD_NEAREST_NEIGHBOR_AUDIT.md`.

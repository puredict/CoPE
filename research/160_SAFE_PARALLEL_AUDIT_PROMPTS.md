# Safe parallel audit prompts

Date: 2026-08-04

## Parallelization decision

Do **not** run the live smoke, occurrence formal, occurrence analysis, or
embodied v2 in parallel. They form a preregistered serial gate; parallel calls
would break the one-draw/conditional-spend logic. Safe parallel work is limited
to independent read-only or report-only audits with zero provider and simulator
calls.

Use a separate branch/worktree for each writing task. Do not edit frozen
manifests, prompts, runners, analyzers, or existing outputs.

## Prompt A: independent novelty falsification

```text
You are an adversarial robotics reviewer. Work read-only in the CoPE repository.
Read AGENTS.md and the current claim stack at research/148_PAPER_CLAIM_STACK_CURRENT.md.
Independently inspect the full primary sources for Tang et al. 2026
(arXiv:2606.31339), PLanAR v4 (arXiv:2602.01662), ASPIRE
(arXiv:2607.00272), InstructFlow, REFLECT, RePlan-Bot, Event Calculus,
commitment lifecycle monitoring, and workflow task-instance logs. Build a
claim-by-claim collision table for persistent state, repair unit, occurrence
identity, authorization, validation, atomicity, history, embodiment, and
generalization. Try to falsify the residual claim; do not improve the writing
until the science survives. Use only primary sources with URLs, state search
limitations, make zero provider/model/simulator calls, and write one new
Markdown report under research/. Do not modify code or existing reports.
```

## Prompt B: independent statistics reproduction

```text
You are an independent statistical auditor. Work read-only in the CoPE
repository. Recompute from source the exact McNemar, Holm, paired risk
difference, sign/locality, median reduction, and safety gates in
tools/analyze_occurrence_formal.py and tools/analyze_sequential_formal_v2.py.
Verify the 6-0/7-0 boundary, reproduce research/141 and research/151 without
copying their numbers, audit assumptions about dependence and pseudoreplication,
and identify any route by which a neutral/governed failure could be rescued.
Do not change code, thresholds, prompts, manifests, or outputs; make zero
provider/simulator calls. Write an independent Markdown report and, only if
needed, a new CSV under research/. Clearly separate arithmetic verification
from generalization/power assumptions.
```

## Prompt C: independent provenance/recovery audit

```text
You are an adversarial systems auditor. Read AGENTS.md, then inspect the formal
call chain at commit 8f05af59df922a30e98c9b8c75b23cf7767205b6 or later:
credential gate, strict provider parser, intent/response/result fsync ledger,
first-infrastructure stop, CSV-to-journal binding, and machine-readable
decision. Use only fake providers, temporary directories, and CPU unit tests.
Inject process interruption, torn lines, duplicate cells, missing intent,
missing response, altered CSV flags, malformed HTTP-200 envelopes, prose-wrapped
JSON, NaN/Infinity, and forbidden resume after infrastructure stop. Never use a
real key, provider call, GPU, or simulator. Do not retry task1 state33 or index
task1 states34-49. Do not modify frozen experiment logic; write a new report
under research/ and report any concrete code defect with exact file/line
evidence rather than fixing it.
```

## Prompt D: conditional replication design after a PASS

```text
This task is design-only and is authorized only if
04_DECISION.txt from occurrence-formal-v1-analysis has
joint_primary_gate=true and the exact preregistered symbolic PASS claim status.
Design, but do not run, a cross-model and multi-task replication that adds
independent interruption semantics rather than lexical object permutations.
Include clustering/hierarchical analysis for shared templates, at least one
non-oracle controller, explicit task/model strata, call/cost budget, stop rules,
neutral and governed co-primary controls, and a claim ceiling. Do not inspect or
select examples based on arm outcomes beyond the frozen aggregate decision.
Write Markdown/CSV preregistration drafts under research/ only; make zero live
provider/simulator calls.
```

These parallel audits cannot unblock the live experiment. Only secure
credential injection and a PASS on the serial operational smoke can do that.

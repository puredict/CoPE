# Formal matched valid-arm preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before any state 27--46 is indexed or
any formal provider call is issued.

## Scope and immutable inputs

- LIBERO-10 task 1, initial states 27--46, both cancellation and replacement;
- states 47--49 are permanent reserve and must never be indexed;
- four interfaces: CoPE sparse, neutral-label sparse, corrected compact
  transaction, and metadata-free FSR-PC full semantic state;
- exact cases: `manifests/semantic_task1_formal_cases_v1.csv`;
- reserve inventory: `manifests/semantic_task1_formal_reserve_v1.csv`;
- formal runtime config: `manifests/semantic_task1_formal_v1.csv`;
- implementation commit: `8ae5949bc853815e007e576530dd33d58beb8e15`;
- no-credential preflight commit:
  `09bd383802ac39c857bae2de987af70c29248f84`;
- the runtime HEAD must be the clean commit containing this preregistration and
  is recorded in every output row.

The formal runner rejects a development config, rejects any case set other than
27--46 x two events, requires `--execute-valid-arms`, forbids retained
development results, and exposes the indexed formal and permanent-reserve IDs
in the final status.

## Frozen execution

- model: `qwen/qwen3.5-flash-02-23` through OpenRouter;
- reasoning `none`, temperature 0, seed 20260802;
- completion limit 4096, timeout 90 seconds;
- 160 assigned provider calls: 20 states x 2 events x 4 arms;
- zero retry, repair, fallback or semantic-oracle substitution;
- CPU only in the cold-verified environment
  `/home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1`;
- output directory:
  `research/formal_matched_valid_arm_2026-08-03/states27_46_openrouter_v1`;
- the credential may exist only in the detached child process environment and
  may not be written to a command, log or result.

For each state, the trusted controller first places cream cheese and verifies
five stable predicate observations. Cancellation is evaluated first and valid
arms emit no action. For replacement, every semantic-valid arm executes from an
independently reproduced matched prefix; every semantic-invalid arm is retained
and fail-closed without execution. Provider output never supplies transaction
metadata.

## Outcomes and statistics

The primary per-case success endpoint is:
`semantic_correct && execution_attempted && matched_prefix_pass &&
terminal_goal_success`. Invalid generations count as failures, not missing data.

1. Primary comparison: CoPE versus metadata-free FSR-PC over 40 paired cases,
   two-sided exact McNemar test; report discordant counts and exact p-value.
2. Secondary comparison: CoPE versus corrected compact, same paired endpoint
   and test.
3. Attribution control: CoPE versus neutral sparse; report exact agreement,
   paired discordances, semantic post-state equality and replacement action
   count/hash equality. A neutral match supports sparse-edit structure rather
   than CoPE vocabulary.
4. Report cancellation and replacement families separately, all provider
   failures, token/latency totals, and no-retry denominators.

No case may be removed after inspection. Provider timeout/error is a retained
failure. If infrastructure interrupts the process, preserve the journal and
stop; any recovery requires a new explicit preregistration and must not silently
redraw completed calls.

## Formal integrity PASS rule

The run is integrity-valid only if:

1. the clean runtime commit equals the preregistration HEAD;
2. exactly states 27--46 and no 47--49 state are indexed;
3. exactly 40 cases, 160 semantic rows and 160 embodied rows are retained;
4. every case has one call per arm with the frozen settings and zero retries;
5. shared-envelope, information-fairness and matched-prefix checks pass;
6. every valid arm is executed to terminal evaluation and every invalid arm is
   fail-closed with zero actions;
7. valid cancellations use zero post-event actions; within each replacement
   case, semantically equivalent CoPE/neutral outputs have identical action
   counts and hashes;
8. no fallback, repair, semantic oracle substitution, credential retention or
   overwrite occurs.

Scientific outcome is not a PASS criterion: compact or FSR-PC may succeed, and
CoPE may fail. Their observed outcomes must be retained as generated.

## Claim boundary

This formal study tests provider-driven high-level persistent-commitment
editing under a privileged low-level simulator controller. It does not claim a
learned visuomotor policy or generalization beyond the preregistered task and
event families.

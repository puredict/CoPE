# Autonomous formal-experiment progress

Date: 2026-08-03 (Asia/Shanghai)

## Current decision

The learned formal experiment remains locked solely on a real semantic model
result and the subsequent combined readiness regeneration. No LIBERO states
27--49 were indexed or executed in this phase.

## Controller correction

The remote `oracle-substrate-qualification` branch contains a complete P5
qualification that supersedes the earlier local summary:

- overall privileged oracle/mechanism substrate gate: PASS;
- 75 assigned episodes, zero method-independent pre-event failures;
- 35/35 paired provenance groups;
- original reset, updated reset, checkpoint Oracle full-state, independently
  materialized Oracle CoPE, no-event parity, three interruption phases, and
  repeated replacement all met their frozen outcomes;
- no provider, learned policy, GPU inference, or reserved-state access.

This qualifies a high-ceiling physical executor for mechanism experiments. It
does not convert the executor into a learned controller and does not answer the
native semantic-generation question.

## Clean formal integration branch

A new independent remote worktree was created:

```text
worktree: /home/lijingsu/codex-worktrees/cope-formal-integration
branch: codex/cope-formal-integration
base: 5763d6def6e4d3a81dbda41eefc6677ef5068aa4
```

It combines the corrected X09/live-semantic execution stack with:

- OpenAI-compatible matched provider adapter;
- CoPE patch and FSR-PC full-state N-track;
- compact generic transaction representation;
- tri-arm matched provider runner and Oracle transport control;
- TX-EXEC+ implementation and rollback controls.

The first focused run exposed a missing `cope.tx_exec` dependency in the
selected cherry-pick set. The missing implementation and tests were added from
the audited TX-EXEC+ commits, after which:

- focused provider/TX/live-runner/oracle-pilot suite: 79 passed;
- complete repository regression: 420 passed in 46.74 seconds;
- worktree remained clean after committed integration;
- no model call, simulator action, GPU use, or reserved-state access occurred.

## Provider status

No OpenRouter, OpenAI, Anthropic, Gemini/Google, Together, Groq, or DeepSeek API
credential is present in the local or remote process environment. The frozen
hosted-model experiment therefore cannot run without external authorization.

A secondary local-model diagnostic was initiated with a small
`Qwen2.5-0.5B-Instruct` checkpoint so that lack of a hosted credential does not
block all empirical work. It is explicitly non-primary: it must use a separate
preregistration and cannot replace the frozen `qwen/qwen3.5-flash-02-23`
OpenRouter result. If both arms have an unusably low ceiling, the diagnostic is
reported as such and no embodied reserve state is spent.

## New self-falsification evidence found

The native-output branch independently completed additional CPU experiments:

- typed-assurance specificity failed after matched canonical guards were given
  to all arms; zero end-to-end fail-open was not typing-specific;
- an oracle-free generic typed interpreter plus eight named decomposed
  predicates matched the exact validator on the frozen single-fault suite;
- all eight predicates had isolated necessity witnesses and composed cleanly
  through all 64 assigned order-1 to order-3 mutations;
- TX-EXEC+ remained semantically equivalent on the frozen contract.

These results further narrow the viable paper claim. The remaining decisive
claim is learned sparse-output factorization: whether a matched model produces
correct CoPE edits more reliably or cheaply than full-state and generic
transaction outputs.

## Next locked sequence

1. Finish and audit the secondary local-model tri-arm diagnostic.
2. Run the hosted four-pair smoke immediately if a credential becomes visible;
   expand only under the frozen outage/fairness rule.
3. Merge only tested artifacts into the formal integration branch and
   regenerate a method-specific true-clean readiness result.
4. Do not spend states 27--46 unless at least one learned semantic arm has a
   usable validity ceiling and all mandatory readiness rows pass.
5. Keep states 47--49 untouched under every outcome.


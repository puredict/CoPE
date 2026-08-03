# X17 structured-interface Stage A result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**Stage A FAIL. Do not create or run the X17 confirmatory holdout yet.**

The final pre-call selection covered six distinct APPLY families: cancellation,
override, release, world-change release, replacement, and continuity conflict.
The experiment crossed four output representations with plain explicit JSON
contracts and OpenRouter strict JSON Schema structured output, for 48 assigned
cells.

All 48 calls were provider-OK and parser-valid. All twelve four-arm comparisons
were fair, and there were no retries, repairs, fallbacks, oracle substitutions,
simulator calls, or reserved-state reads. Nevertheless every arm scored 0/6 in
both modes.

| Mode | Arm | Correct | Parser valid | Unsafe attempts | Completion tokens |
|---|---|---:|---:|---:|---:|
| plain | CoPE | 0/6 | 6/6 | 6 | 1,258 |
| plain | neutral typed | 0/6 | 6/6 | 6 | 1,927 |
| plain | compact TX | 0/6 | 6/6 | 6 | 1,879 |
| plain | FSR-PC | 0/6 | 6/6 | 6 | 2,791 |
| structured | CoPE | 0/6 | 6/6 | 6 | 1,345 |
| structured | neutral typed | 0/6 | 6/6 | 6 | 2,155 |
| structured | compact TX | 0/6 | 6/6 | 6 | 1,996 |
| structured | FSR-PC | 0/6 | 6/6 | 6 | 2,791 |

OpenRouter's strict schema treatment successfully removed syntax/schema-version
failures, but it did not improve semantic transition correctness. The official
models API listed `structured_outputs`, `response_format`, `tools`, and
`tool_choice` for the frozen Qwen model, and the run required supported
parameters rather than silently dropping them.

## Failure structure

CoPE structured failures were three wrong canonical post-states, two wrong
reason codes, and one omitted `CommitEvent`. Compact TX structured failures were
four wrong post-states, one invalid restoration append path, and one malformed
record insert. All six structured FSR-PC states differed from the oracle.
Neutral typed outputs often selected the correct neutral operation class but
filled fields using a generic shape that the corresponding typed operation did
not accept.

In a representative cancellation case, structured CoPE correctly cancelled
the root and blocked its transitive descendants, but omitted action/progress
updates and `CommitEvent`. Structured compact TX performed the root change and
version/event writes but omitted other required dependent-state changes.
Structured FSR-PC reproduced most of the expected state but used an incorrect
processed-event payload hash and incomplete action semantics.

## Interpretation

X16's zero-APPLY ceiling was not merely a `type` versus `op` parsing problem.
The model could conform to strict schemas but could not derive every canonical
state change expected by the oracle.

There is also a benchmark-specification concern: provider-visible task policy
sentences do not consistently enumerate every action, progress, history,
dependency, and event-commit mutation present in the oracle. JSON Schema can
constrain shape but cannot supply hidden transition semantics. Before trying a
stronger model or more prompt engineering, the benchmark must prove that every
oracle delta is uniquely entailed by provider-visible rules.

Stage A was exploratory and does not modify X16's negative confirmatory result.
Its development cases are permanently excluded from a future confirmatory
holdout.

Branch: `codex/x17-structured`.

- Stage-A freeze commit: `8f8cbae7154be4f999347b9376e281794fedd69f`;
- diverse-family amendment commit: `dac1bd24d0f2a421b56ae9376f0514e82c4754c4`;
- final preflight commit: `065f2b57a3ac91a6ceeb0074df31152a7a4c059d`;
- result commit: `e5a50e1eb5b07f86d6779498a5f9fcdeaebfc696`.

No further provider experiment or reserved-state rollout should run until the
oracle-derivability audit below passes.

# Phase 2: method contracts and controlled mechanism qualification

This implementation is scoped to Window 2 of the supplied v2 specification.
The archived v1 result and claim decisions remain unchanged. This work does not
run a provider, a learned VLA, calibration, or a formal experiment.

The eight non-oracle arms are typed persistent editing, generic persistent
transactions, full semantic-state regeneration, full-history replanning,
public-history retrieval, summary memory, skill-local replanning, and a
classical execution monitor. The privileged persistent oracle is diagnostic.

## Boundaries

A public event, a method proposal, an accepted state, a compiled problem, and
an execution trace remain separate objects. Only the oracle entry point may
receive hidden state. Public prompt data is scanned recursively before a call.
The two persistent edit arms expose identical semantic facts; the output
interface is the treatment. Every generative event uses exactly one call,
including the joint summary and plan update. Prompt/response bytes, decoding
configuration and token accounting are retained for audit.

Unmentioned persistent slots remain unchanged. Revalidation is a check record,
not a mutation. Restoration requires successful fresh evidence for the stored
guard. Expired occurrences cannot be restored. A repeated request allocates a
new occurrence. Priority is independent of lifecycle; v2 has no demoted lifecycle.
Transactions are atomic and append to their own accepted history. Full-state
regeneration may lose semantics; logging and compilation do not repair them.

The compiler accepts only the arm's state or directive and public execution
context. It cannot add omitted goals, recover lost history, repair a wrong
occurrence, or infer semantics from a task ID. The deterministic abstract
backend executes that compiled problem and labels its output
`controlled_mechanism`. Its outcomes are representation-to-plan qualification,
not robot performance or evidence of learned-policy success.

## Qualification

The no-provider oracle fixture smoke uses explicit fixture responses to test
the adapters and parser/compiler plumbing. These responses are not predictions
from a foundation model. Classical and privileged oracle paths do not use a
reasoner. All fixture results must remain labeled diagnostic and cannot enter
formal paired accuracy estimates.

Test commands, base and final revisions, results, and hashes are recorded in
the phase-2 verification report after integration.

## Integration API

- `adapters.create_adapter(method, gateway=...)` constructs a generative arm;
  omit the gateway for the classical and oracle arms. All adapters implement
  `start_episode`, `on_event`, `compile_state`, `snapshot`, and `restore`.
- A `Reasoner` implements `count_tokens(messages)` and
  `complete(*, messages, config) -> ReasonerResponse`. `ReasonerGateway` records
  exact input/output and consumes an episode/event call key once. The cohort
  runner must call `assert_same_backbone` before starting a comparison.
- `parse_proposal(method, raw)` accepts exact JSON, rejects duplicate keys,
  nonfinite values, unknown fields and malformed interfaces, and never extracts
  JSON from prose or performs response repair.
- `apply_cope` and `apply_generic` consume an immutable ledger and proposal plus
  caller-supplied evidence records/context. They return a new ledger or raise
  without changing the input. `apply_full_state` validates the regenerated
  semantic state without adding old semantics. A cumulative identity registry
  prevents a forgotten occurrence identifier from being reused; that registry
  is not provided as recovered task memory.
- `compile_ledger` and `compile_directive` return a canonical-hashable
  `PlanningProblem`. Explicit empty regenerated fields override context defaults.
- `ControlledMechanismBackend.solve` returns an `ExecutionPlan` with
  occurrence-bound macro actions and serialized instructions. `execute` returns
  a `ControlledExecutionTrace`. The neutral `explicit_skills` execution mode
  interprets only supplied skill steps and verifies their preconditions, effects,
  constraints and final goals. The abstract-goal mode realizes the supplied
  Boolean goals. Neither mode invents missing task commitments.

The classical monitor uses bounded breadth-first search over supplied skill
preconditions/effects and Boolean task facts. Structured public task updates are
its update interface; it does not contain a natural-language semantic reasoner.
Its transient planner labels are not persistent occurrence memory. The retrieval
arm uses frozen lexical overlap and a conservative UTF-8 byte budget, recorded
explicitly rather than presented as measured model tokens.

Initial planning semantics come from the common public initial task state and
require no event-level call. Later accepted proposals and method-specific memory
persist continuously. Diagnostic fixture response injection is restricted to the
smoke module and test double; there is no production provider SDK in phase 2.

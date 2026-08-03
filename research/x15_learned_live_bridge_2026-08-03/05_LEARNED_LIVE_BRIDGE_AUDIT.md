# X15 learned-to-live semantic bridge audit

Date: 2026-08-03 (Asia/Shanghai)

## Scope and baseline finding

Audited `experiments/live_semantic_runner.py` and
`cope/semantic_live_runner.py` at X14 HEAD `fba9f32b502c8301687559a62101293105f17254`.
The old live path was an oracle mechanism fixture, not learned recovery:

- it built the expected full state with `build_oracle_full_state` or
  `build_oracle_cancellation_state`;
- it selected and applied `apply_oracle_replacement_patch` or
  `apply_oracle_cancellation_patch`;
- receipt materialization required `oracle_operation_selection=true` and
  `provider_called=false`;
- semantic success explicitly required `receipt.provider_called is False`;
- the experiment CLI never instantiated or called a provider.

No parser repair, retry, or learned fallback existed in that path; the entire
path itself was the oracle substitution. The old materializers also rejected
provider-backed receipts, so they could not qualify X15.

## Implemented production path

The production CLI now calls `run_learned_semantic_triplet`. The old mechanism
is retained only as the explicitly named `run_oracle_semantic_fixture`, and the
oracle pilot imports that fixture by name.

All three arms receive one shared `RecoveryInput` instance. The only differing
message is the output contract:

- CoPE: exact minimal replacement fields `event_id`, `operation=Override`,
  `patch_id`, `target_id`, `replacement_id`; exact minimal cancellation fields
  `event_id`, `operation=Expire`, `patch_id`, `target_id`.
- compact TX: exact generic path/value transaction with base version, event ID,
  and allowlisted writes.
- FSR-PC: exact complete nine-section `full-state-v2` persistent state.

CoPE fields construct the actual `Patch` and `Override` or `Expire` operation
passed to the sole typed mutation entrypoint. Compact writes are staged and
validated by the generic transaction executor. FSR-PC is parsed as a complete
state and passed to the same canonical live validator/compiler.

Trusted code, not model output, creates:

- transition receipts and audit records;
- before/after persistent-state hashes;
- typed state, event and patch history;
- live predicate outcomes through the non-fake registered validator;
- compiled directives;
- action-count and simulator-state before/after evidence.

Model output containing receipt, history, state hashes, controller fields, or
any other non-contract field is rejected. Event-bound canonical builders and
validators now have production names. Legacy `build_oracle_*` and
`validate_oracle_*` names remain compatibility aliases used only by explicit
oracle fixtures and controls.

## Provider and fallback audit

- Provider model is frozen to `qwen/qwen3.5-flash-02-23`.
- Reasoning is required to be `none`.
- Temperature is `0.0`, seed `20260802`, prompt budget `12000`, completion
  budget `4096`, timeout `90.0`, and retries `0` for every arm.
- API credential access remains inside the provider adapter and reads only the
  named environment variable. No credential value is logged or serialized.
- Transport failure remains `timeout` or `outage`; it is never converted to an
  oracle result, repaired output, alternate prompt, or retry.
- `provider_called`, `oracle_substitution`, and `fallback_used` are recorded per
  arm. The state-0 expansion gate requires all three arms provider-OK, equal
  common-input and normalized-request hashes, equal settings hashes, no retry,
  no fallback, no oracle substitution, and zero action delta.

## Phase A and state lock

Phase A snapshots simulator state and controller action count immediately before
provider calls and again after all semantic computation. Any change raises a
fail-closed error. There is no controller or simulator action call in the Phase
A function.

The CLI defaults to development state 0 only. States 1--4 require a separate
invocation with the retained state-0 CSV; the gate reads that artifact and does
not repeat any state-0 provider call. Any state outside 0--4 is rejected.
Reserved states 27--49 are never indexed or authorized.

## Residual boundary

The trusted canonical post-state is a rejection/validation target, not a
proposal source. Learned semantic correctness and embodied execution success
remain separate questions. This implementation does not authorize a formal
robot rollout or any reserved state.

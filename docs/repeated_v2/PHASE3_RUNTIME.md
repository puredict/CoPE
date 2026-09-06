# Phase 3 runtime and durability contract

Phase 3 implements the execution harness for the phase-2 method adapters. It
preserves each method's accepted state through one continuous trajectory.
The separate phase-1 and phase-2 commits remain ancestors of this work.

## Runtime boundaries

`EpisodeRunner` owns the environment, independent sealed evaluator, journal,
method adapter, neutral planner and common executor. The environment plugin
implements the explicit `RuntimeEnvironment` protocol. Every method starts
from the same immutable initial ledger/context and independent simulator reset.
Every action consumes exactly one recorded policy step. Semantic scheduler
facts decide event delivery; missing trigger/feasibility evidence blocks rather
than falling back to a fixed timestep.

Before an event, the harness stores simulator state, Python/NumPy RNG, method
memory, public execution context, policy state/RNG, continuation backend state,
observation, action trace, and sealed evaluator state. Event injection has no
method argument. The harness rejects changed method state, hidden policy
steps, unchanged observation versions/references, and event evidence that does
not refer to the fresh post-event observation. Only public evidence/history,
public context and detector evidence records enter ordinary adapters. Hidden
effects and canonical ledgers enter only the diagnostic oracle arm and sealed
scoring. Oracle rows remain explicitly privileged and excluded from ordinary
formal evidence.

The reasoner proxy persists the exact messages/configuration before invoking
`Reasoner.complete`. It persists the raw typed response before parsing/applying
it. There are zero semantic retries. Accepted errors accumulate. Rejection may
append audit history but may not change ledger, directive, summary, regenerated
state or revision. The frozen fallback either retains accepted semantics and
replans, or terminates. All methods use the same common executor and action
trace schema; no task-identity lookup repairs omitted goals.
Each VLA trace preserves both the raw policy action and the converted action
sent to the environment, with the declared action-space convention.

Unsupported accepted recovery semantics and failed candidate verification become
`METHOD_PLANNING_FAILURE`. Failed recovery execution gates become
`METHOD_RECOVERY_EXECUTION_FAILURE`. Both retain the failed boundary and every
subsequent unreached event. Missing backend dependencies or pre-injection capture
inputs stop as infrastructure failures, preserving already published boundaries.

## Sealed evaluation

The independent truth reader evaluates the current canonical achievement goals,
retired occurrence execution, every monitored hard constraint and unaffected
verified progress. Constraint/regression violations latch across later recovery.
Macro IDs plus occurrence IDs distinguish intentionally re-executing a retired
or completed occurrence even when its physical predicate matches a new goal.
Timeout, manual intervention and unreached required events prevent success.
A failed method status also prevents success when static physical goals happen
to be true.

Optional public-runtime detectors/verifiers do not supply final success.
The environment's harness-only `sealed_planning_problem` supplies the canonical
planning problem for pre-execution fidelity scoring. Content fields are compared
without source-method/source-revision metadata, while plan identity is still
bound to the exact accepted problem hash. Fidelity timestamps and problem hashes
are recorded before the corresponding action trace begins.

`sealed_protected_projection` supplies selectors and expected canonical values
for unaffected planning obligations. The same scoring routine selects goals,
constraints, preferences, protected progress, groundings, restore records or
continuation fields from every method's compiled problem. Missing selected
items count as corruption; they are never supplied to the planner. This supports
interfaces that do not retain a ledger. A production canonical evaluator must
supply and audit these selectors; formal execution fails closed when either
sealed measurement hook is absent. Without that hook, ledger-based preservation
checks are qualification diagnostics and unavailable values remain unknown.

## At-most-once calls and crash resume

The canonical call key is
`protocol/master_episode_id/method/event_index` with protocol `controlled` or
`end_to_end`. `A` and `B` aliases normalize to these same keys. Checkpoint zero
has no adaptation call. Information conditions use separate journal directories.

The journal holds an exclusive process lock and publishes immutable hashed JSON
records with file/directory fsync. It rejects credentials recursively. Intent
without a durable response is ambiguous and is never automatically repeated.
A saved response can be replayed through the parser after restoring a verified
pre-event simulator boundary, without another provider invocation.
The response envelope stores measured invocation time separately from the exact
provider response, so replay preserves the original latency. Older envelopes
without that measurement report an unavailable value, never a fabricated zero.

A completed-boundary snapshot contains its pending result. If a crash occurs
between snapshot publication and result publication, resume verifies and publishes
that result. Terminal failure state is preserved on resume. Every later event is
recorded as `EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE`, with a verified link to the
last reached failure boundary. No fictitious event snapshot is created.
Completed episode resume verifies all event cells and snapshots before returning
the cached result. Missing/duplicate/unexpected cells, corrupted records, changed
identity, or missing snapshots fail closed.

Simulator actions after the latest durable boundary may be replayed after a
crash; committed traces contain only the recovered continuous trajectory.
This rollback semantics is for simulator environments, not physical robots.
Policy and planner plugins must snapshot all internal state and selected-device
RNG necessary for deterministic replay. The native OpenVLA client does so.

## Formal admission and CLI

`experiments/repeated_interruptions_v2.py` runs pilot/formal protocols through a
configured `RuntimeAssembly`. Production assembly factories must be lazy: no
inference or simulator stepping during construction. The CLI validates authentic
catalog/calibration and exact manifests before calling factories. All actual
generative gateways are checked for the same backbone, decoding and budgets
before the first adaptation call. Environment/planner/policy identities must
match across methods, while mutable state must be independently owned.

The phase-4 freeze validator is an explicit formal dependency. Before external
calls and resumed execution, it checks the entire frozen bundle against live
identities and actual artifact bytes. The runtime additionally binds the VLA
checkpoint and reasoner model to that bundle. Fake/scripted/oracle policies are
never admitted as learned-VLA substrates. Formal execution remains blocked until
all production dependencies, task calibration and freeze evidence exist.

Raw artifacts use the specification's 00–13 names. Event/episode records,
planning problems, exact call requests/responses, snapshots and compressed action
traces are exported from the verified journal without reconstruction or
imputation. Existing outputs can only resume byte-identically; they are not
overwritten.

## Scope of evidence

Mock integration tests validate mechanics, not learned policy performance.
The real LIBERO CPU smoke validates reset, one physics step, exact simulator
restore and fresh observation; it does not qualify repeated physical event
injection or a VLA checkpoint. See `PHASE3_SIMULATOR_SMOKE.md` and
`PHASE3_ADAPTER_AUDIT.md` for exact dependency observations and limits.

# Formal v2 crash-recovery amendment

Date: 2026-08-04  
Timing: frozen before any formal v2 provider outcome  
Trigger: implementation audit of the committed v2 runner

## P0 finding

The first v2 runner writes a result journal after a provider call but has no
resume mode. A process or host failure can therefore leave a partially
completed run that either cannot continue or, under a naive restart, repeats a
high-level draw. It also lets provider transport failures enter the semantic
success comparison as if they were method failures. Both behaviors threaten
the causal interpretation of the co-primary comparison.

## Frozen recovery protocol

For every `(sequence_id, arm, event_index)` cell, durable records follow this
order:

1. append and `fsync` a call intent containing the cell key and common-input
   hash;
2. make at most one provider call;
3. append and `fsync` the redacted response trace;
4. materialize/validate/execute the transition;
5. append and `fsync` the result cell.

On `--resume`:

- a completed result is never called again;
- a response trace without a result is rematerialized locally, without a new
  provider call;
- an intent without a response is permanently marked
  `ambiguous_interrupted_call_no_retry`; it is never called again;
- an event-1 success may be rematerialized from its response trace so that its
  missing dependent event 2 can continue;
- duplicate or contradictory intent/trace/result keys abort the run;
- run metadata, runtime commit, manifest, contracts, controller, and protocol
  hashes must match the original run exactly;
- final CSV publication is atomic from the durable journal.

This provides at-most-once provider draws. It cannot prove whether a remote
provider processed an intent whose response was lost; the ambiguous cell is
therefore not converted into a model outcome.

## Frozen analysis rule

Any eligible cell with one of the following failure classes invalidates the
formal efficacy/locality claim gate for that run:

- provider timeout;
- provider transport outage;
- provider HTTP failure;
- ambiguous interrupted call without response.

The analyzer may still emit descriptive rows, but the claim status must be
`INVALID_INFRASTRUCTURE_FAILURE`. Parser/schema/semantic failures after a
durably received response remain method outcomes. Simulator execution failures
remain embodied outcomes unless shared-prefix integrity itself is incomplete.

## Consequence

Formal execution remains blocked until this protocol has implementation tests
covering crash-after-intent, crash-after-response, completed-cell skipping,
event-1 rematerialization, duplicate-key rejection, and atomic finalization.

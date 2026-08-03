# Shared-envelope live Phase-A canary result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS for the development integration canary.**

The result permits preparation of a formal reserved-state preregistration. It
does not itself authorize consuming reserved states until the formal runner,
manifest, audit fields, and preflight are frozen.

## Frozen execution

- preregistration implementation commit:
  '378168fe625b81c3d948d09b868da12b701780ad';
- raw-result commit:
  '97241272c2b1514addb0a1fe329d84c7a5af98c8';
- cold-verified Python environment:
  '/home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1';
- model: 'qwen/qwen3.5-flash-02-23';
- assignment: LIBERO-10 task 1, development state 0, replacement and
  cancellation, three provider arms per event;
- 6 provider calls, zero retries and zero repairs.

## Observed result

| Check | Observation |
|---|---:|
| Provider calls OK | 6 / 6 |
| Fairness checks | 6 / 6 |
| CoPE parser + semantic + oracle-equivalence | 2 / 2 |
| CoPE shared envelope | 2 / 2 |
| Model-generated transaction metadata | 0 / 2 |
| Canonical live predicate outcome | 2 / 2 |
| Post-event controller actions | 0 |
| Simulator mutations during Phase A | 0 |
| Fallback / oracle substitution | 0 / 0 |
| Reserved states consumed | 0 |

Both CoPE transitions compiled correctly: replacement produced the revised task
directive and cancellation produced 'HALT'. Compact and FSR-PC were incorrect
on both events; this is diagnostic under the frozen canary rule and is not used
to decide the integration gate.

All six responses have nonempty distinct response hashes. Within each event
triplet, all arms share the same recovery-input hash, serialized common-input
hash, normalized request hash, and provider-settings hash. The simulator and
controller before/after values are identical on every row.

## Predicate and transaction evidence

The production path rejects test packets, binds the packet to the RGB hash,
simulator-state hash, event ID, policy step and pinned producer commit, compares
it to an independently logged predicate snapshot, and requires the canonical
'done=true, pending=false' outcome before provider calls. These guards completed
for both retained cases.

The shared transaction function rejects provider-authored version, evidence,
processed-event, payload-hash or receipt fields. A pass is returned only after
the trusted envelope increments state version, binds evidence version, and
records exactly the current event. The retained result contains separate
semantic-state and transaction-metadata hashes.

## Newly identified formal blocker

The canary serializes the transaction and semantic hashes but not the trusted
transaction postcondition fields themselves. The postconditions are enforced in
the committed runtime and covered by focused tests, so this does not invalidate
the canary. For a formal reserved-state run, however, the CSV must additionally
retain explicit base/state/evidence versions, processed event ID and event hash.
That observability change must be implemented, tested, committed and
preregistered before any reserved state is indexed.

## Claim boundary

This is real live LIBERO perception and semantic commitment, but it is Phase A:
the physical prefix is controlled by the existing oracle controller and no
post-interruption recovery action is executed. It supports integration
readiness, not an end-to-end embodied recovery claim.

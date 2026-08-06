# Sequential persistent-state four-arm gate preregistration

Date: 2026-08-04

## Purpose

This credential-free capability gate must pass before the new confirmatory
experiment is frozen or any formal provider call is made.  It tests the
specific substrate required by the CoPE hypothesis: event 2 must consume the
committed state produced by event 1, rather than reconstructing a two-goal
state from the original task.

This is an interface qualification, not evidence that one learned method is
better than another.  All proposals are canonical oracle-correct fixtures and
`provider_calls=0`.

## Frozen cases

Two fresh LIBERO-10 task identities and two dependent event sequences are
crossed, yielding four cases:

| Task | A (physically complete) | B (initial pending) | C | D |
|---|---|---|---|---|
| 0 | `alphabet_soup_1` | `tomato_sauce_1` | `cream_cheese_1` | `butter_1` |
| 7 | `alphabet_soup_1` | `cream_cheese_1` | `butter_1` | `tomato_sauce_1` |

1. `replace_then_cancel`: `B -> C`, then cancel `C`;
2. `replace_then_replace`: `B -> C -> D`.

The initial revision is 1, event 1 reads revision 1 and publishes revision 2,
and event 2 reads revision 2 and publishes revision 3.  The event-2 before
hash must exactly equal the event-1 after hash.

## Frozen arms

The four confirmatory arms are:

1. `cope`: typed `Override`/`Expire` commitment operations;
2. `neutral_patch`: equally expressive neutral sparse operations (`N01`/`N02`)
   translated by a trusted label adapter;
3. `fsr_pc`: one complete persistent semantic state regenerated at each event;
4. `full_replan`: completed physical facts plus the complete remaining ordered
   commitment plan, materialized by a trusted adapter.

`compact_tx` is not a fifth confirmatory arm.  It remains a transaction-engine
component/diagnostic and is excluded to keep the preregistered 4-arm,
320-provider-call design internally consistent.

## Required pass conditions

All 16 arm-case cells must pass.  For every cell:

- event 2 is parsed against event 1's published state and revision;
- adjacent state hashes are continuous;
- A remains satisfied and physically valid;
- B is superseded after event 1 and never returns active;
- after event 2, C is `cancelled` for `replace_then_cancel`, or `superseded`
  for `replace_then_replace`;
- D is active only for `replace_then_replace`;
- all historical commitments remain as inactive audit records;
- all four arms produce an identical canonical final state and directive for
  a given case;
- the cancel sequence compiles to `HALT`; the double-replacement sequence
  compiles to `place_in(D, basket_1_contain_region)`;
- `provider_calls=0`, `simulator_states_indexed=0`, task-1 state 33 is not
  retried, and no task-1 state 34--49 is indexed.

Negative tests must reject a stale event-2 base revision, a broken adjacent
hash, targeting inactive B after event 1, dropping A, reactivating B, omitting
historical commitments, or changing a physically witnessed fact.

## Stop rule

Any failed cell or negative-test escape blocks formal-manifest freeze.  Repair
using symbolic fixtures only and rerun the complete gate; do not inspect any
task-0/task-7 state 10--49 during repair.

# X09 two-state Oracle semantic execution pilot result

Date: 2026-08-02 (Asia/Shanghai)

## Decision

**Assigned pilot: NO-GO.** It produced 0/4 passing arms and 0/2 passing
pairs.  This decision is not replaced by the later debug result.

**Consumed-state debug replay: 4/4 arms and 2/2 pairs passed.** This proves the
root cause was repaired and the Oracle execution substrate can realize the
edited task, but it is not fresh pilot evidence and does not authorize a
learned-provider experiment.

## Assigned failure

The assigned run at commit
`c58c4cb402fb6b2cea92b922d1cd81cd67ca1517` failed identically in all arms:

`ValueError: reserved or unregistered state access rejected`

X09 verified a narrow sidecar authorization for states25/26, but the reused X04
semantic function still hard-coded states0--4.  The authorization was not
carried across the API boundary.  The first pair auditor also treated two
missing strings as equal, making some field-level flags misleading even though
the final pair decisions were correctly false.

The original evidence is preserved in `03_ASSIGNED_RESULTS.csv` and
`04_PAIR_AUDIT.csv`; see `05_FAILURE_DIAGNOSIS.md`.

## Correction

Commit `9218924cfa914fe830d5f3439ad024c79228485e`:

- preserves states0--4 as the default semantic-core lock;
- accepts a caller-supplied state set only when the caller explicitly passes
  it;
- makes the verified X09 caller pass exactly `{25, 26}`;
- requires non-empty values before pair equality can pass;
- retains partial evidence when an episode raises;
- adds tests showing default rejection and explicit narrow authorization.

Focused tests passed 14/14 and the full repository passed 355/355.

## Debug replay

The versioned consumed-state replay is in `06_DEBUG_REPLAY_RESULTS.csv` and
`07_DEBUG_PAIR_AUDIT.csv`.

Replacement, state25:

- native and CoPE arms both passed;
- identical prefix count 206 and identical event evidence;
- both used 186 post-event actions under the fixed budget of 280;
- cream cheese and alphabet soup ended in the basket;
- butter remained outside and valid progress was retained.

Cancellation, state26:

- native and CoPE arms both passed;
- zero post-event policy actions in both arms;
- exactly 30 neutral verification environment steps in both arms;
- cream cheese stayed in the basket and butter remained outside.

For both pairs, initial state, prefix action digest, prefix length, event step,
qpos/qvel digest, RGB, live packet, RecoveryInput, checkpoint poses, compiled
directive, final action digest, final simulator state, and budgets matched
between arms.

## Interpretation

The debug replay supports the engineering claim that persistent task edits can
be compiled and executed while retaining physical progress.  It cannot show a
method advantage: native FSR-PC and CoPE intentionally materialize to the same
state and execute the same directive, so their physical results must match.

The scientifically correct next step is not to report 4/4 as a pilot success.
It is to freeze the corrected stack, select a new untouched reserve in a
separate preregistration, and first screen learned-policy checkpoint
continuation on clean/no-edit cases.  Only tasks with a sufficiently high clean
continuation rate should enter the learned FSR-PC-versus-CoPE comparison; this
directly avoids the low upper-bound problem seen with ReKep.

States25/26 are consumed. States27--49 remain untouched and locked.

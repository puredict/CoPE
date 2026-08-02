# X04 live semantic runner result

Date: 2026-08-02 (Asia/Shanghai)

Decision: **PASS for live CPU semantic wiring.**

This does not claim learned recovery success or superiority over FSR-PC.  It
shows that the previously separate mechanisms can be connected to one real
LIBERO physical checkpoint without fake predicate evidence or hidden actions.

## Assigned result

The authoritative assigned artifact is `04_ASSIGNED_RESULTS.csv`.

- 10/10 assigned rows passed: states 0--4, replacement and cancellation.
- All rows record runtime commit
  `739e175521e93a8c598cdef20f5b0570f1809c81`.
- Five distinct physical prefixes produced five RGB, simulator-state, and
  action-prefix hashes.  The two event rows at each state share the same
  physical checkpoint.
- Ten distinct event-bound packet hashes were produced.
- Every packet has `source_kind=live_libero_eval_predicate` and
  `test_only=False`; every validator reports `is_fake=False`.
- The validator returned `True` for the completed cream-cheese commitment and
  `False` for the pending butter commitment in all ten rows.
- Native Oracle FSR-PC and Oracle CoPE received byte-identical canonical
  RecoveryInput payloads in all ten rows.
- CoPE used an accepted provider-free typed transition; its independent
  materializer exactly matched native full-state-v2 and compiled the same
  directive in all ten rows.
- Five stability steps were observed at every physical checkpoint.
- Simulator qpos/qvel hashes and controller action counts were unchanged after
  packet production and both semantic branches; post-event action count was
  zero.
- Reserved states were not indexed.  The upstream shared init-state container
  was necessarily deserialized as documented before the run.

`05_REPLAY_RESULTS.csv` and `05_ASSIGNED_RESULTS_HARDENED.csv` are byte-identical
replays of the authoritative assigned artifact.  All three have SHA-256
`0bfe482a2663fb04b42afdae10aac6624e08fc1bb5705a1bdbe9dc6abf6a2dbf`.
This exact equality is expected from the pinned states, seeds, Oracle
controller, and deterministic semantic path.

## Superseded V1

`03_ASSIGNED_RESULTS_SUPERSEDED.csv` is retained byte-for-byte (SHA-256
`2927f2573770af75505054f11d02496568c69a6c5a11b3e6b13b29af897d32bf`).
It also reports 10/10, but its concurrent older runner probed mutation evidence
in the wrong order and did not record the runtime commit.  It is preliminary
evidence only; see `03A_LEGACY_RESULT_AUDIT.md`.

## Existing gates rechecked

- Independent receipt materialization: 4/4 passed, reserve consumed 0.
- Frozen corruption audit: 123/123 expected decisions, malformed accepted 0.
- Atomicity/property tests: 67/67 passed.
- Full repository regression after hardening: 349/349 passed.

## What changed scientifically

X03 is no longer only an offline predicate replay: a production packet was
created from registered LIBERO predicates in a real simulator state.  X04 is
no longer only a set of separately passing components: one runner connected
physical truth, common input, native reconstruction, typed editing,
independent materialization, shared validation, and shared compilation.

The upper-bound problem raised for low-success learned baselines remains
untouched.  The next experiment must therefore keep the Oracle semantic pilot
separate from the eventual learned-policy baseline: first test whether a
correct commitment edit can be executed from the checkpoint, then evaluate a
qualified learned policy only on tasks/states where its clean checkpoint
continuation rate is high enough to expose recovery differences.

## Reserved-pilot readiness

The five technical readiness conditions are now evidenced: live packet,
shared full-state path, pinned config and reserve manifest, pinned Oracle
controller, and reset/prefix/output provenance.  However the pinned semantic
config still says `rollout_authorized=false`.  Therefore states 25/26 remain
locked until a separate, versioned Oracle-pilot preregistration explicitly
authorizes only those two rows; X04 itself does not silently unlock them.

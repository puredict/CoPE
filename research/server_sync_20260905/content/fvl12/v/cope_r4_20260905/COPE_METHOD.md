# CoPE — Constraint-state Patch Editing

Grounded in the collaborator's memo: *CoPE / RCSP Comprehensive Technical Memo*,
Jingsu Li, **v0.3, 2026‑04‑26**. Terminology taken from that memo:

- **CoPE** = **Co**nstraint-state **P**atch **E**diting
- **RCSP** = **R**eactive **C**onstraint-**S**tate **P**atching

No acronym expansion here is invented; anything without a memo source is
flagged as such (see [`FSRPC_BASELINE_SPEC.md`](FSRPC_BASELINE_SPEC.md)).

## 1. Two layers, one system

```
  CoPE semantic layer        persistent constraint state S_t, relation graph G_t,
  (this work)                edit history H_t, typed patch operators
        |
        |  cope/recovery_manager.py   (adapter only — maps, never replaces)
        v
  repair execution layer     continuation capture -> operator synthesis ->
  (frozen, reused)           legality check -> sequential rollout verification ->
                             splice -> restore -> resume
```

**Nothing in `rekep_repair/` was rewritten, replaced or duplicated for this
work.** The repair engine remains the sole owner of execution, verification and
splicing. The adapter maps between representations:

| CoPE concept | repair-layer concept |
|---|---|
| `ConstraintSlot(mode=SUSPENDED)` | `TaskProgram` stage suspension |
| `Patch` | repair goal / operator sequence |
| slot `restore` predicate + lineage | `Continuation` |

## 2. The slot schema (memo §3.1)

```
c_i = (id, ω, mode, priority, source, validity, restore, lineage, history)
```

A constraint is not only a mathematical function but a software-engineering
object with identity, lifecycle, relations and edit history; the grounding `ω`
is one field among nine.
Implementation: [`cope/constraint_slot.py`](../cope/constraint_slot.py).

## 3. Lifecycle modes (memo §3.2) — existence separated from participation

| mode | exists | participates in planning | restorable |
|---|---|---|---|
| `active` | ✓ | ✓ | — |
| `suspended` | ✓ | ✗ | ✓ |
| `overridden` | ✓ | ✗ | ✓ |
| `expired` | ✓ (auditable) | ✗ | **never** |

`expired` is a *soft delete*: the record survives so the audit query "which goal
was cancelled, and why?" stays answerable. Slots are never removed from the
state — enforced by `validate_state` and by
`test_slots_are_never_deleted`.

## 4. Patch operators (memo §4)

First-paper subset, in `cope/patch.py::FIRST_PAPER_SUBSET`:

| operator | side effect |
|---|---|
| `Insert(c)` | create slot (usually active); add node; append history |
| `Suspend(id)` | `mode=suspended`; snapshot priority; record a restore path |
| `Override(id_old, id_new)` | old → `overridden`; add a symmetric override edge |
| `Inherit(id)` | leave active; **record** the inheritance explicitly |
| `Expire(id)` | `mode=expired`; block restoration; keep the trace |
| `Revalidate(id, check)` | **no mode change**; returns `OK` / `DEGRADED` / `FAIL` |
| `Restore(id)` | `mode=active` **iff** the restore predicate and validation pass |

`Promote` / `Demote` (priority only, identity unchanged) are implemented but
outside the first-paper subset.

Two rules the tests pin down because getting them wrong would still produce a
passing benchmark number:

1. **`Revalidate` never changes mode.** It is a pure check. Verified for
   `active`, `suspended` and `overridden`.
2. **`Restore` is a commitment, and it is refused unless revalidation returns
   `OK`.** An expired slot is refused outright; a `DEGRADED` result leaves the
   slot suspended and records the refusal. A `Restore` not preceded by a
   `Revalidate` is a *validation violation*, rejected before any mutation.

## 5. Invariants (checked before and after every patch)

`cope/patch_validator.py`:

- **identity** — a slot id is never reassigned to a different constraint
- **lifecycle legality** — transitions follow the `LEGAL` table; `expired` is
  terminal
- **no deletion** — the slot set never shrinks
- **graph consistency** — override edges are symmetric and acyclic
- **history monotonicity** — per-slot `seq` is strictly increasing
- **guarded restoration** — no `Restore` without a preceding `Revalidate`

A patch that fails pre-validation is **not applied at all**; the state is left
untouched and the episode continues from the current state (recorded as
`safe_fallback`).

## 6. The audit trace (memo: explainability as a structured patch trace)

`cope/audit_trace.py` answers five queries from the record alone:

| | query |
|---|---|
| Q1 | which goal was cancelled? |
| Q2 | which completed goal was preserved? |
| Q3 | why was a constraint suspended? |
| Q4 | what condition allowed restoration? |
| Q5 | which state replaced the old target? |

Every query has **two evidence paths** — typed patch operations, *and* diffing
consecutive regenerated snapshots — so that FSR-PC is not scored at zero for
circular reasons. Q1 and Q2 are recoverable from a state snapshot and FSR-PC
answers them. Q3–Q5 ask for a reason, a restoration condition and a replacement
identity; a complete snapshot carries none of those. That asymmetry is the
finding, and it is not an artefact of the scoring code. Queries a condition does
not pose score `None`, never `False`.

## 7. The single compiled interface

`StateStore.compile_active()` produces the only thing the downstream executor
ever sees, and it is identical for both arms. `test_the_executor_cannot_tell_
which_policy_produced_the_request` asserts the compiled request carries no
method marker.

## 8. What is deliberately *not* claimed

- CoPE is not claimed to beat FSR-PC on final task success. On the CPU pilot the
  two are tied at 20/20.
- The CPU results validate the protocol, the semantics and the fairness
  controls. They are **not** a robotics result; see
  [`PILOT_EXPERIMENT.md`](PILOT_EXPERIMENT.md) for what must be run on the GPU
  host before any claim about physical execution is made.
- The patch generator is a deterministic symbolic rule set, not an LLM. Both
  arms use deterministic planners, so neither gets a language-model advantage
  and no token-usage claim is made.

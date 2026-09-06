# FSR-PC — baseline specification

## 1. Provenance: this is an internally defined baseline

**FSR-PC is not an established published algorithm, and it must never be cited
as one.**

What was checked, and what was found:

| Source inspected | Result |
|---|---|
| `CoPE_RCSP_Comprehensive_Technical_Memo_v0.3_2026-04-26.pdf` (Jingsu Li, v0.3, 2026‑04‑26), full text extracted | no occurrence of "FSR", "FSR-PC", or "full-state regeneration" as a named method |
| Every file in this repository (`grep -rIn -e 'FSR' .` before this work began) | zero matches |
| All other collaborator-supplied material in the project | no definition |

The expansion used throughout this project — **Full-State Regeneration with
Progress/Context** — comes **only from the project brief that commissioned this
baseline**. It has no external source.

Consequences that every report, slide and paper draft must respect:

- Describe FSR-PC as "an internally defined strong baseline" or "our
  full-state-regeneration baseline".
- Do **not** attach a citation to it.
- Do **not** write "state-of-the-art FSR-PC" or imply prior art.
- If the collaborator later supplies a published source, replace this section
  rather than quietly adding a citation.

## 2. What FSR-PC does

At every interruption, FSR-PC emits a **complete regenerated constraint state**
that replaces the previous one, rather than an edit to it.

```
CoPE     S_{t+1} = apply(P_t, S_t)          P_t = [op_1 ... op_k], k small
FSR-PC   S_{t+1} = regenerate(context_t)    every slot re-emitted
```

Implementation: [`cope/policies/fsrpc_policy.py`](../cope/policies/fsrpc_policy.py).

## 3. Why it is a strong baseline, not a straw man

FSR-PC receives **byte-identical input** to CoPE at every interruption — this is
asserted by a test, not by prose
([`tests/test_cope_fairness.py`](../tests/test_cope_fairness.py),
`test_both_primary_arms_receive_byte_identical_adaptation_inputs`, over all four
conditions × three seeds).

The shared `AdaptationInput` carries:

- full world state and robot state
- **completed goals** (so completed work is never re-planned)
- pending goals and cancelled goals
- the user request in natural language
- all safety constraints
- the full task history and event history
- perception summary
- the same compute budget and horizon

FSR-PC is explicitly **not** made forgetful, history-free, or context-blind.
Concretely, the implementation:

- honours completed goals by re-emitting them as satisfied rather than re-doing
  them;
- carries the prior lifecycle mode forward when the update does not mention a
  slot;
- collapses its own prior re-minted slots onto the canonical task vocabulary
  before regenerating, so repeated regenerations do not multiply records;
- re-emits every safety constraint;
- has access to the same `canonical_id` helper CoPE uses
  ([`cope/naming.py`](../cope/naming.py)).

A conscientious regenerator can reconstruct correct *content* from the context
it is given, and this one does. That is the point: it gets everything right
that regeneration allows.

## 4. The single intended difference

| | CoPE | FSR-PC |
|---|---|---|
| adaptation output | typed patch over existing slots | complete new state |
| slot identity | carried | re-minted (`g_butter#r2`) |
| per-slot edit history | continued | not inherently continued |
| lineage / override edges | explicit | not represented |
| edit footprint | the touched subset | the whole state |
| reason attached to a change | per operation | none (a snapshot has no reasons) |

Everything else — task, seed, layout, interruption timing, information,
executor, budget, horizon, grader, metric code — is shared.

## 5. The `preserve_ids` ablation

`FSRPCPolicy(preserve_ids=True)` regenerates the complete state but re-uses the
previous slot ids. It exists so the question "is the CoPE advantage just id
bookkeeping?" is **run rather than argued about**.

Pilot result (20 episodes per arm, `results/cope_pilot/stage_c_ablations.json`):

| arm | identity preserved | mean normalized edit distance | mean audit coverage |
|---|---|---|---|
| CoPE | 20/20 | 0.507 | 1.000 |
| FSR-PC | 0/20 | 1.000 | 0.458 |
| FSR-PC(preserve_ids) | 20/20 | 1.000 | 0.458 |

Reading: preserving ids recovers the identity metric **and nothing else**. The
locality and audit differences come from local typed editing, not from
identifier hygiene.

## 6. What FSR-PC is *not* asked to lose

For the record, the following would each make the baseline weak, and none of
them is done:

- withholding completed-goal information → not done
- withholding task/event history → not done
- withholding safety constraints → not done
- giving it a smaller compute budget or fewer planner calls → not done
- giving it a different executor, seed or grader → not done
- forbidding it from reusing ids → available as an ablation, and it changes only
  the identity metric

## 7. Honest statement of the current evidence

On the CPU pilot the two arms are **tied on final task success** (20/20 each).
The measured differences are in state representation, edit locality and audit
answerability. This is reported as-is; the brief explicitly does not require
CoPE to beat FSR-PC on final success, and it does not here.

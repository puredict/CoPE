# Post-occurrence reviewer simulation

Date: 2026-08-04
Scope: claims supportable before any live learned formal call

## Executive verdict

**Current verdict: weak reject / HOLD.** The code is ready for the decisive
symbolic learned test, but the present evidence does not yet support an ICRA
method claim. A dual-primary win can move the occurrence-sensitive interface
from HOLD to a credible method component; it cannot by itself establish
embodied long-horizon recovery.

## Strongest reviewer objections

### R1: The architectural framing collides with prior work

Tang et al. (2026) already frame persistent commitment editing for robot task
recovery closely enough that generic “edit commitments instead of replanning”
cannot carry novelty. Transactional, governed-control, and delivery-semantics
variants also failed the internal uniqueness audit.

**Required response:** narrow the contribution to a learned compact editing
interface and evaluation protocol. Do not claim invention of persistent
commitments, event sourcing, occurrence identity, or transaction semantics.

### R2: Occurrence identity is established machinery

Event Calculus distinguishes event occurrences from persistent fluents;
commitment lifecycle models and workflow logs also represent repeated task
instances. Adding an occurrence index is therefore an enabling representation,
not the scientific novelty.

**Required response:** claim only that CoPE learns a minimum occurrence-sensitive
commitment delta under equal-information, representation-matched controls.

### R3: The compactness result may be representational bookkeeping

CoPE's proposal is much shorter than neutral/governed/FSR-PC controls in the
cold preflight, but those are predetermined representation costs, not learned
efficacy. Full replan is also a near-sized control in some settings.

**Required response:** proposal length is secondary. The formal primary result
must be first-pass canonical success and locality against **both** neutral and
governed controls, with the preregistered Holm correction and no safety excess.

### R4: The only recurrence-oriented physical probe exposed a controller limit

Task-7 state 0 and state 1 restored successfully, but state 2 restoration
failed `target_predicate_false` after a semantically valid occurrence edit.
The first-failure rule correctly stopped states 3--49. This prevents using
task 7 as formal embodied evidence under the frozen controller.

**Required response:** report task 7 as a falsifying external-validity result,
not as hidden pilot noise. Do not rerun state 2 or select a more favorable
suffix.

### R5: A symbolic win can still be prompt-format specialization

All five arms share inputs and are position-balanced, but the residual task is
symbolic JSON editing. A learned win could reflect output-contract alignment
rather than robotic recovery competence.

**Required response:** treat a symbolic dual-primary PASS as necessary, not
sufficient. Only then unlock task-0 embodied formal v2, where action/simulator
outcomes provide an independent validity layer.

## Outcome-contingent verdicts

| Occurrence formal outcome | Scientific interpretation | Paper action |
|---|---|---|
| infrastructure invalid | no efficacy inference | preserve artifacts; repair infrastructure only under the preregistered recovery policy |
| loses/ties neutral | no advantage over minimum native update | stop method-paper route |
| beats neutral, loses/ties governed | governance wrapper explains the result | stop method-paper route |
| beats both, safety excess | unsafe compactness | stop method-paper route |
| beats both, locality gate fails | efficacy without claimed minimum-delta benefit | reject compact-edit claim |
| beats both, locality and safety pass | symbolic necessary condition met | run task-0 embodied formal v2 |
| symbolic pass, embodied failure | interface does not transfer through controller | benchmark/tool contribution at most |
| symbolic pass, embodied pass | viable narrow method paper | write around learned occurrence-sensitive editing, not architecture invention |

## Claims that remain prohibited even after a positive result

- “first persistent commitment editor”;
- “first occurrence-aware recovery method”;
- “unique transaction-safe recovery architecture”;
- “full replanning is intrinsically much larger”;
- “task-7 recurrence recovery succeeds physically”;
- “symbolic success proves long-horizon embodied recovery.”

## Decision

No further prompt design or simulator sweep should precede the one-draw
operational smoke and the frozen 200-call occurrence formal. The experiment is
now the bottleneck; architecture polishing is not.

# CoPE versus AgentChord: Branch Compilation and Unanticipated-Interruption Stress Test

**Adversarial decision:** AgentChord kills the broad claim that long-horizon manipulation recovery requires online task regeneration or full replanning. It retains a directed task graph, augments it before execution with monitored recovery branches, switches immediately when a compiled monitor fires, and rejoins the nominal graph. ([AgentChord](https://arxiv.org/abs/2605.11951))

**Residual danger:** on any bounded benchmark whose interruption alphabet and history depth are known, a reviewer can demand an enumerated AgentChord analogue that unfolds the relevant commitment states into graph nodes and recovery edges. This is a **proposed representational falsifier**, not a claim made by AgentChord. If this full-information graph matches CoPE, the surviving difference is compactness, synthesis bias, adaptation to held-out events, or runtime cost—not recovery expressivity.

## 1. Seven-field hostile review

**Problem.** AgentChord targets delayed and brittle detect–reason–recover pipelines in dynamic long-horizon manipulation, especially when an MLLM must be called after a failure. ([AgentChord](https://arxiv.org/abs/2605.11951))

**Representation.** Its directed task graph has semantic subgoal nodes, constraint-aware transition edges, subgoal and path constraints, predicted edge-specific failure modes, recovery nodes, recovery edges, candidate merge nodes, compiled scalar monitors and a failure-to-recovery mapping. ([AgentChord](https://arxiv.org/abs/2605.11951))

**Recovery mechanism.** Before execution, an orchestration agent predicts likely failure modes and adds recovery branches; at runtime a violation that persists beyond a margin and window triggers the mapped precompiled edge, after which execution reaches a recovery or nominal merge node and continues without reinvoking full task planning. ([AgentChord](https://arxiv.org/abs/2605.11951))

**Main contribution.** AgentChord combines task-graph construction, proactive failure anticipation, forward-moving recovery-branch augmentation, hierarchical constrained motion synthesis, and low-latency compiled monitoring in one long-horizon manipulation system. ([AgentChord](https://arxiv.org/abs/2605.11951))

**What is closest to CoPE.** Both preserve a semantically meaningful long-horizon object, isolate recovery from low-level control, retain unaffected nominal structure, use current constraints to decide a scoped intervention, and continue from a selected point rather than regenerate the task description. ([AgentChord](https://arxiv.org/abs/2605.11951); [CoPE technical memo](</Users/lijingsu/Documents/cope/CoPE_RCSP_Comprehensive_Technical_Memo_v0.3_2026-04-26 (3).pdf>))

**What is fundamentally different.** AgentChord encodes anticipated recovery as topology before execution and treats the last completed subgoal as the failure context; CoPE proposes online typed edits to persistent requirement occurrences with issuer, support, override/restoration, physical-progress and version evidence. AgentChord’s paper does not define source-specific retraction, same-content independent support, nested override restoration, policy-version authorization or an irreversible-effect ledger. ([AgentChord](https://arxiv.org/abs/2605.11951); [CoPE technical memo](</Users/lijingsu/Documents/cope/CoPE_RCSP_Comprehensive_Technical_Memo_v0.3_2026-04-26 (3).pdf>))

**Can the reviewer call CoPE incremental?** **Yes for the broad mechanism.** Persistent graph plus monitor-triggered local recovery and nominal rejoin is already demonstrated. **Yes provisionally for bounded benchmark behavior.** Until CoPE beats a full-information enumerated graph, the reviewer can argue that online commitment editing is merely a compact syntax for selecting a precompilable history-conditioned branch. **No, not yet, for arbitrary held-out interruption composition.** AgentChord explicitly acknowledges that rare, compound or non-hand-induced failures may be missed and proposes online MLLM reinvocation as fallback. ([AgentChord](https://arxiv.org/abs/2605.11951))

## 2. What the paper actually demonstrates

AgentChord reports six manipulation tasks with 20 trials per task, object-instance and initial-pose variation, four baselines, and GPT-5 plus a shared function-tool set across compared methods. Its simulation disturbance randomly drops a held object at each atomic action with probability 0.05 or 0.10; its physical protocol applies one or two disturbances per trial and keeps them identical across methods. ([AgentChord](https://arxiv.org/abs/2605.11951))

In the reported simulation table, AgentChord averages 99.2% success, compared with 97.5% for Code-as-Monitor and 92.5% for both DoReMi and ReKep; the reported average execution time for AgentChord is 41.5 s, compared with 54.4 s for ReKep, 78.1 s for Code-as-Monitor and 105.9 s for DoReMi. ([AgentChord](https://arxiv.org/abs/2605.11951))

In the reported six-task physical table, AgentChord averages 77.5% success, compared with 72.5% for Code-as-Monitor, 66.7% for DoReMi, 65.0% for ReKep and 59.2% for Inner Monologue; its reported average execution time is 92.2 s, compared with 107.1 s for ReKep, 130.9 s for Code-as-Monitor and 143.5 s for DoReMi. ([AgentChord](https://arxiv.org/abs/2605.11951))

The paper’s forward-branch ablation compares AgentChord with an otherwise matched backtracking variant on three physical tasks; the reported mean success is 86.7% versus 73.3%, while mean execution time is 105.6 s versus 128.4 s. This supports the utility of prepared forward-moving branches relative to that backtracking ablation, not a comparison with commitment-state editing. ([AgentChord](https://arxiv.org/abs/2605.11951))

The evaluation tables report point estimates but do not report confidence intervals or formal hypothesis tests, and the disturbance families are dominated by object drop, displacement, tilt, grasp loss and relational misalignment rather than source-specific revocation or policy-version drift. The reported results therefore do not establish superiority for CoPE’s proposed repeated/nested authority and restoration conditions. ([AgentChord](https://arxiv.org/abs/2605.11951))

## 3. The “without replanning” wording is narrower than it sounds

AgentChord avoids reinvoking **full task planning** when a prepared monitor fires, but its edge executor uses receding-horizon refinement, updates the perceptual estimate, resolves the constrained transition problem every \(M\) control steps and executes only the first \(M\) commands before the next solve. The scientifically accurate distinction is “no online full task-graph regeneration for covered failures,” not “no replanning or optimization at runtime.” ([AgentChord](https://arxiv.org/abs/2605.11951))

CoPE also hands an edited semantic state to downstream planning or control, so contrasting “CoPE edits commitments” with “AgentChord replans everything” would be false. The meaningful comparison is the scope and cost of semantic-state reconstruction before the shared downstream controller. ([AgentChord](https://arxiv.org/abs/2605.11951); [CoPE technical memo](</Users/lijingsu/Documents/cope/CoPE_RCSP_Comprehensive_Technical_Memo_v0.3_2026-04-26 (3).pdf>))

## 4. Bounded branch-compilation attack

The following is a **proposed compiler attack**, not an AgentChord result.

For a frozen benchmark with a finite interruption alphabet, bounded nesting depth, bounded number of active supports, finite version buckets and a finite admissible action library, define one graph node for each reachable canonical commitment state plus current nominal subgoal. For each legal interruption, restoration, expiration or evidence-update event, add an edge to the next canonical state; attach the same validators and physical/policy gate used by CoPE; merge states only when decoded commitment state, validator verdict and canonical next-action intent are identical.

Call this arm `AgentChord-ENUM`. It is intentionally allowed to be large. Its purpose is not to propose a deployable system but to test whether CoPE has different decision power or merely a more compact native factorization.

The compiler gate is:

1. Every legal benchmark CoPE state must decode from at least one enumerated node.
2. Every frozen event must induce the same legal/illegal verdict in both representations.
3. Every valid CoPE patch must correspond to an enumerated edge path with the same decoded post-state.
4. Both arms must produce the same validator verdict and canonical command intent when given the oracle patch.
5. Compilation size, offline time and runtime lookup must be reported rather than hidden.

If any semantic equality fails, the compiler is not yet a valid comparator. If all equalities hold, an accuracy win against an unaugmented AgentChord graph does not establish unique expressivity.

## 5. The strongest separating experiment

The following design is **proposed**, not a reported finding.

Use four arms:

- native AgentChord with anticipated branches and its published forward-moving filter;
- `AgentChord-ENUM`, compiled from the locked benchmark event grammar and the same CoPE-visible fields;
- `AgentChord-ONLINE`, which may invoke the paper’s proposed MLLM fallback for an uncovered failure under the same model, prompt budget and controller as CoPE;
- full CoPE.

Cross four factors:

1. **Coverage:** event family visible to the precompiler versus held out at semantic-family level;
2. **Composition:** isolated versus compound simultaneous failure;
3. **History:** single event versus nested or repeated events with non-LIFO source withdrawal;
4. **Physical dependency:** forward-local recovery versus necessary rewind, reobservation, compensation or permanent abstention after irreversible change.

Hold observations, timestamps, stable IDs, support graph, authority graph, world/policy versions, physical ledger, validators, candidate actions, controller and compute accounting constant. This is necessary to avoid turning missing information in the graph arm into a fake CoPE advantage. ([CoPE fairness protocol](./CoPE_Benchmark_Baseline_Competence_and_Fairness_Protocol_2026-07-30.md))

Report natural-pipeline correct-patch accuracy, valid-continuation rate, physical success, false rejection, wrong-source deletion, wrong-parent restoration, unauthorized edit, stale-world/policy commit, irreversible-effect replay, event-to-valid-continuation latency, online model calls, offline compilation time, graph size, peak memory and executed action cost. These are proposed endpoints aligned with the existing CoPE claim-survival contract. ([claim-survival audit](./CoPE_Claim_Survival_and_Evidence_Obligations_2026-07-30.md))

## 6. Hard rejection rules

The following are **proposed hostile decision rules**.

Reject unique CoPE expressivity if `AgentChord-ENUM` passes the oracle semantic compiler gate and is behaviorally non-inferior on all bounded cells.

Reject a broad “unanticipated recovery” claim if CoPE wins only because native AgentChord was forbidden the paper’s stated online fallback, or if `AgentChord-ONLINE` closes the gap under matched model and tool budgets. ([AgentChord](https://arxiv.org/abs/2605.11951))

Reject commitment-specific attribution if the difference occurs only on held-out object drop or pose-displacement events without source identity, authority, override ancestry or version drift.

Reject the phrase “recovery without replanning” if either arm continues to resolve downstream motion or constrained-control problems; report semantic reconstruction and downstream optimization separately. ([AgentChord](https://arxiv.org/abs/2605.11951); [CoPE technical memo](</Users/lijingsu/Documents/cope/CoPE_RCSP_Comprehensive_Technical_Memo_v0.3_2026-04-26 (3).pdf>))

Downgrade the contribution to **representation compactness or interface efficiency** if behavior is equivalent but CoPE reduces artifact size, offline enumeration, online model calls, or event-to-valid-continuation latency under a preregistered resource frontier.

Permit a narrow method claim only if CoPE remains superior after exact information matching, handles held-out relational compositions without leaking family labels, and the advantage concentrates in source/authority/lineage/irreversible-progress interactions rather than generic failure detection.

## 7. AgentChord’s exposed weaknesses are not automatically CoPE strengths

The paper attributes physical failures to missed anticipation, incorrect recovery-node selection, IK infeasibility, perception error and wrong monitoring-tool compilation; its limitations explicitly mention rare, compound and non-hand-induced failures plus feature-extractor fragility. These are genuine attack surfaces. ([AgentChord](https://arxiv.org/abs/2605.11951))

CoPE does not gain novelty merely because it uses online edits. It must demonstrate that its representation causes fewer such failures under matched sensing, reasoning and controllers. Otherwise the comparison confounds precompilation coverage, model quality, perception and low-level feasibility with commitment-state semantics.

The paper’s forward-moving condition filters recovery branches whose remaining graph distance exceeds that of the failure context. A proposed CoPE counterexample should therefore include a physically necessary backward dependency repair, but the experiment must also test an augmented graph allowed to encode that repair; beating only the published filter would establish a scope difference, not representation necessity. ([AgentChord](https://arxiv.org/abs/2605.11951))

## 8. Final novelty verdict

- **High confidence:** CoPE cannot claim novelty for persistent task-graph recovery, compiled monitoring, local failure-specific transitions, nominal-graph rejoin or avoidance of online full task replanning for covered failures. ([AgentChord](https://arxiv.org/abs/2605.11951))
- **Medium confidence:** a finite bounded CoPE benchmark can be unfolded into an information-equivalent enumerated recovery graph; this is a proposed compilation argument that still requires an executable semantic gate, not a published theorem about AgentChord.
- **Medium confidence:** AgentChord does not invalidate online commitment editing for genuinely held-out, compound, nested, authority-sensitive and dependency-breaking interruptions, because its paper explicitly recognizes uncovered rare and compound failures and does not evaluate CoPE’s source/authority/restoration semantics. ([AgentChord](https://arxiv.org/abs/2605.11951))
- **Low confidence:** CoPE can clear ICRA by comparing only with native AgentChord. Without `AgentChord-ENUM` or an equivalent full-information graph arm, an adversarial reviewer can reduce the result to precompiled coverage versus online syntax.
- **Very low confidence:** the current unevaluated CoPE work establishes a new recovery principle rather than a potentially more compact or adaptable encoding. ([CoPE technical memo](</Users/lijingsu/Documents/cope/CoPE_RCSP_Comprehensive_Technical_Memo_v0.3_2026-04-26 (3).pdf>))

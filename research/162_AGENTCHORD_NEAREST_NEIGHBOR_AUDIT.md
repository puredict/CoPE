# AgentChord Nearest-Neighbor Audit

Date: 2026-08-04

## Decision

**Broad CoPE architecture novelty remains NO-GO.** AgentChord is a closer
robotics neighbor than the previously audited monitoring-only or generic task
repair systems. It already represents manipulation tasks as directed graphs
with semantic subgoals and constraints, augments those graphs with recovery
nodes and edges, compiles monitors, and switches to forward-moving recovery
branches without online full-task replanning.

This result does **not** directly answer the narrow CoPE question: whether a
learned editor can identify and patch exactly one repeated *occurrence* of a
persistent commitment while preserving all non-target commitments. That
occurrence-sensitive contract is therefore the only defensible residual method
claim, and it remains unproven until the preregistered dual-primary formal gate
passes.

## Primary source

- Sheng Xu et al., *From Reaction to Anticipation: Proactive Failure Recovery
  through Agentic Task Graph for Robotic Manipulation*, arXiv:2605.11951v1,
  12 May 2026: <https://arxiv.org/html/2605.11951>
- Public implementation linked by the paper:
  <https://github.com/Jasonxu1225/AgentChord>

The audit uses the paper itself, not search-result summaries.

## Direct overlap

| Dimension | AgentChord evidence | Consequence for CoPE |
|---|---|---|
| Persistent structured state | Directed graph nodes encode semantic subgoals; edges encode constrained transitions (Sec. III-B) | A task-state/constraint representation is not novel by itself. |
| Local recovery structure | Anticipated failures receive recovery nodes, edges, and downstream merge points (Eqs. 4--7) | Adding localized recovery paths to a persistent plan is already demonstrated. |
| Avoid full replanning | Compiled monitors switch immediately to precompiled branches without reinvoking full planning (Secs. III-D/E) | “Recovery without replanning” is not a novel headline. |
| Preserve progress | Recovery branches are filtered by a forward-moving cost-to-go condition (Eq. 8) | “Do not regress / preserve completed progress” is not a novel headline. |
| Constraints and monitors | Nodes and edges have subgoal/path constraints; failure functions are executable monitors (Eqs. 3, 9--13) | Constraint-governed recovery is already occupied. |
| Embodied evidence | Six disturbed real-world tasks average 77.5% success and 92.2 s; a three-task graph ablation reports 86.7% average success versus 73.3% for backtracking (Tables II and V) | CoPE cannot rely on architecture diagrams or symbolic tests alone. |

These are author-reported results and were not independently reproduced here.

## Non-overlap that may remain

The paper contains no occurrence-identity formulation and no use of the term
"occurrence." Its online recovery chooses a precompiled edge associated with
the active nominal edge and anticipated failure mode. For unforeseen failures,
the stated fallback reinvokes the agent pipeline to synthesize an additional
branch. The paper does not report a contract requiring all of the following:

1. select one of several semantically identical repeated commitments by stable
   occurrence identity;
2. apply a typed edit (`cancel`, `replace`, or `restore`) to that occurrence;
3. preserve every non-target occurrence byte-for-byte or semantically exactly;
4. reject ambiguous, stale, or illegal edits before execution; and
5. compare learned editors under identical information and output envelopes.

This is a **paper-text non-overlap**, not proof that the implementation could
not be extended to satisfy the contract.

## Claim changes required

Forbidden claims:

- first structured-graph recovery method;
- first constraint-based recovery method;
- first method to recover without full replanning;
- first method to preserve progress through local recovery;
- first task-graph patching or recovery-branch method.

Potentially defensible claim, conditional on the formal gate:

> CoPE studies learned, exact occurrence-sensitive editing of persistent task
> commitments under a typed validity and locality contract, and measures when
> an assurance layer converts an otherwise fluent edit into an executable one.

Use "studies" rather than "first" unless a broader systematic search validates
priority.

## Experimental consequence

The existing 200-call occurrence experiment remains the fastest decisive test
of the residual claim because AgentChord does not resolve occurrence identity.
However, a submission-quality embodied comparison must either:

- include AgentChord (or a faithful recovery-augmented-graph analogue) as the
  closest system baseline; or
- state precisely why its required perception/control stack cannot be run and
  compare against a matched precompiled-recovery-graph abstraction.

Neutral and governed LLM baselines alone can establish the assurance-layer
effect, but cannot establish superiority over the nearest embodied recovery
system.

## Effect on current decision

- Formal infrastructure readiness: unchanged, PASS.
- Live evidence status: unchanged, no provider calls made.
- Residual claim status: unchanged in logic but materially narrower.
- Submission status: **HOLD / weak reject** until the dual-primary occurrence
  gate passes and the AgentChord comparison gap is addressed.
- Execution order: unchanged -- one-draw smoke, then 200 occurrence calls,
  analyze, and unlock the at-most-400 embodied run only on dual-primary PASS.

## Secondary monitoring-only neighbor

PATCH (arXiv:2606.16690) detects task-relevant localized visual innovations and
routes to a recovery source, but it does not edit persistent task commitments:
<https://arxiv.org/html/2606.16690>. It sharpens the distinction between
interruption *detection* and commitment *editing* but is less direct than
AgentChord.


# InstructFlow full-text differentiation note

Date: 2026-08-04

Primary source: [InstructFlow, NeurIPS 2025 full paper](https://papers.nips.cc/paper_files/paper/2025/file/03cfff3eccb29aa15f76e9bcee3d1be7-Paper-Conference.pdf).

## What clearly collides

The paper constructs a hierarchical instruction graph `G_t`, conditions graph
revision on goal, state and failure-induced symbolic constraints, inserts
reasoning nodes upstream of affected planning nodes, and replaces affected
subgoals with refined versions.  It explicitly describes its reasoning modules
as typed symbolic transformations and repeatedly claims targeted/localized plan
or code repair without full regeneration.

Therefore CoPE must not claim novelty for any of the following alone:

- local repair instead of full replanning/regeneration;
- symbolic constraints induced from execution feedback;
- typed symbolic transformations;
- revising only an affected subgoal;
- graph-structured long-horizon code generation and failure recovery.

## What was not established by this full-text check

Exact full-PDF text searches returned no match for `idempot`, `atomic`,
`transaction`, `commitment`, `authorization`, `receipt`, or `history`.
`version` appeared only in reproducibility/checklist material, not as task-state
concurrency control.  This is evidence about the terminology and exposed method,
not proof that no semantically equivalent mechanism exists under another name.

The inspected method revisions are driven by physical failure constraints and
graph/prompt regeneration.  The paper material inspected did not establish:

- stable commitment identities retained across dependent interruptions;
- immutable completed facts plus inactive historical commitments;
- event-target authorization and base-version checks;
- atomic accept/reject with before/after hashes and transaction receipts;
- duplicate-event rejection/idempotence;
- stale-commitment execution as an explicit terminal endpoint.

## Defensible CoPE contrast

CoPE's claim should be about **transaction semantics for persistent task
commitments**, not about local symbolic repair.  The unit of change is a stable
commitment selected by an interruption event; trusted execution validates
authority, base revision, invariant preservation, history and idempotence before
publishing a new state.  The scientific question is whether that stronger
interface improves sequential recovery compared with an equally informed,
equally local generic JSON-path transaction.

Even a positive result does not make CoPE categorically superior to
InstructFlow: the systems address different failure sources and InstructFlow has
broader manipulation benchmarks.  A paper should present them as complementary
axes—physical constraint induction versus persistent commitment-state
transactions—and explicitly test whether CoPE's transaction machinery adds
value beyond schema verbosity and trusted validation.

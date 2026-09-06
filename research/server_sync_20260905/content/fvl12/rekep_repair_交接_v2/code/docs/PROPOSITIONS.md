# Propositions for online repair (drafts)

Theorem 1 (simultaneous-objective conflict) is unchanged — see
[THEOREM.md](THEOREM.md). These four results concern the *synthesis* layer.

Throughout: `O` is the finite operator set, each `o ∈ O` a triple
`(pre_o, eff_o, c_o)` with `pre_o : S → {0,1}`, `eff_o : S → S`, `c_o > 0`; `S`
is the abstract state space (here `S = {0,1}^d`, `d = 11`, so `|S| = 2^d`); a
repair goal is `G = (T, F)` with `sat_G(s) ⇔ (∀ p ∈ T. s.p) ∧ (∀ p ∈ F. ¬s.p)`.

Implementation: `repair/abstract_state.py`, `repair/planner.py`.

---

## Proposition A (search soundness)

**Statement.** Let the planner return `π = (o_1, …, o_m)` from `s_0`. Define
`s_i = eff_{o_i}(s_{i-1})`. If the search only expands `o` at `s` when
`pre_o(s) = 1` (as `SymbolicOp.applicable` enforces), and only returns `π` when
`sat_G(s_m)`, then:

1. every operator is applied in a state satisfying its declared precondition;
2. the terminal abstract state satisfies **every** requirement of `G`, including
   both the event requirements and `restore_valid`.

*Proof.* (1) is immediate by induction on `i`: expansion of `o_i` at `s_{i-1}`
requires `pre_{o_i}(s_{i-1}) = 1`. (2) is the return condition. ∎

**Scope — this is the important caveat.** Proposition A is a statement about the
*abstract model only*. It does **not** imply physical feasibility: the abstract
effects are declared, not derived from the dynamics. Physical validity is
established separately and independently by the sequential rollout verifier
(`repair/rollout_verifier.py`), which re-derives the requirement residual from
the *predicted concrete trajectory* and hard-rejects any candidate that
collides, times out, breaks attachment semantics, or leaves a residual. Empirical
support that the two layers are not redundant: `abl_no_rollout` raises the
collision rate from 0.004 to 0.034 (≈8×) while abstract soundness still holds.

---

## Proposition B (finite termination)

**Statement.** If `S` is finite, `O` is finite, every `c_o > 0`, and plan length
is bounded by `L`, then best-first (uniform-cost) search terminates.

*Proof.* Paths are bounded: the planner refuses to extend a path of length `L`,
and additionally each operator may appear at most once per path, so the number
of distinct paths is at most `Σ_{k≤min(L,|O|)} |O|!/(|O|-k)!`, a finite number.
Each pop removes one frontier element and pushes at most `|O|` successors of
strictly greater cost (since `c_o > 0`), so no path is re-expanded indefinitely
and the frontier is exhausted after finitely many pops. ∎

**Additional guarantee in this implementation.** `SymbolicOp.applicable` also
requires `eff_o(s) ≠ s`, so every applied operator strictly changes the state;
combined with monotone effects this gives a much smaller practical bound
(observed: 11.5 expansions on average across 16 200 benchmark episodes).

---

## Proposition C (conditional completeness)

**Statement.** Let `Π_L = { π : |π| ≤ L, π applicable from s_0 }`. If some
`π* ∈ Π_L` satisfies `sat_G(eff_{π*}(s_0))`, then uniform-cost search over `O`
with bound `L` returns some goal-reaching plan, and with a cost-optimal
tie-break it returns one of minimum cost.

*Proof.* Uniform-cost search enumerates paths in non-decreasing cost and, absent
an inadmissible pruning rule, eventually pops every element of `Π_L`. Hence it
pops `π*` unless it has already returned a goal plan of cost `≤ c(π*)`. ∎

**Scope.** Completeness is *conditional on the bounded space* `Π_L` and on the
operator set. It says nothing about repairs requiring an operator not in `O`, a
plan longer than `L`, or a plan that repeats an operator (excluded by the
`applicable` rule). It is **not** open-set completeness.

---

## Proposition D (coverage–complexity, comparative)

**Model (stated explicitly, and it is an assumption, not an observation).**
Suppose `K` disturbance predicates may hold in any combination, all `2^K − 1`
non-empty combinations are reachable, and a *precompiled* architecture must
store, before execution, a complete branch for each combination it intends to
cover.

**Statement.** Under that model, full combination coverage requires `Θ(2^K)`
stored branches, whereas a compositional library storing `Θ(K)` primitive
operators can cover the same combinations if, for every reachable combination, a
goal-reaching plan exists in `Π_L` — at the cost of runtime search bounded by
Proposition B.

*Sketch.* The counting half is immediate. The compositional half is exactly
Proposition C applied per combination. ∎

**What this must NOT be read as.** It does **not** claim that every offline
recovery architecture is necessarily exponential: a real system may share
subgraphs, parameterize a branch over several combinations, cover only the
combinations it deems likely, or synthesize offline on demand. The proposition
compares two *idealized* strategies under a stated model.

**Measured instance (K = 3).** From `scripts/offline_regimes.py`:

| method | combos | branches | graph | compile | safe delivery |
|---|---|---|---|---|---|
| offline_budget(1) | 1 | 1 | 5 | 6 | 1/7 |
| offline_atomic(3) | 3 | 6 | 32 | 31 | 5/7 |
| offline_exact(7) | 7 | 17 | 109 | 157 | 7/7 |
| online synthesis | — | 9 operators | 0 | 0 | 7/7 |

The honest reading: **with full combination coverage the precompiled baseline
matches online exactly** (16 200-episode benchmark: 0.994 vs 0.994 safe delivery,
0/0 discordant, p = 1.0). The online advantage is *storage and compile cost*
(constant vs. growing with covered combinations), plus success under partial
coverage (offline_atomic 0.838 vs 0.994, +0.156 [+0.143, +0.170]).

---

## Proposition E (conditional restoration)

**Statement.** Let `κ` be the captured continuation with resume contract
`Pre(s_i^resumed)`. If repair execution reaches a concrete state `x` with
`Pre(s_i^resumed)(x) = 1`, then the resumed instance of the interrupted stage
begins from a state satisfying its declared entry conditions.

*Proof.* Immediate from the implementation: `TaskProgram.advance` refuses entry
to the RESUMED node unless `mark_restore_validated` returned true, and that call
evaluates exactly `Pre(s_i^resumed)` on the observed state
(`program/task_program.py`, `program/continuation.py`). The transition is atomic,
so a failed check leaves the program unchanged. ∎

**Explicitly NOT claimed.** Nothing here guarantees the controller *reaches*
such a state under model mismatch. Proposition E is conditional on arrival; the
`Realign`/`Resume` controllers make arrival likely but not certain.

**Measured status.** Across 706 gate evaluations spanning *none*, *moderate* and
*severe* mismatch the gate **never rejected** (`scripts/mechanism_identification.py`,
M3). The invariant held in every observed episode; the gate is therefore a
safety invariant rather than a measured source of success. See
[MECHANISMS.md](MECHANISMS.md).

---

## The three levels of validity (must never be collapsed)

| Level | Claim | Established by | Measured status |
|---|---|---|---|
| **L1 Abstract plan soundness** | the returned operator sequence satisfies every declared precondition and the terminal abstract state satisfies the `RepairGoal` | Proposition A | holds by construction |
| **L2 Concrete rollout feasibility under the planning model** | the sequential rollout under `f̂` predicts no collision, no guard timeout, valid attachment, zero requirement residual | `repair/rollout_verifier.py` | precision 1.000 at zero mismatch |
| **L3 Physical execution success under model mismatch** | the executed trajectory under `f ≠ f̂` actually succeeds | model-mismatch study | **degrades: false-accept rate 0.000 → 0.028 → 0.063 → 0.228** across none/mild/moderate/severe |

No proposition in this repository asserts L1 ⟹ L3, and none should. L2 is the
bridge, and the mismatch study quantifies exactly how leaky that bridge becomes.

# Frozen CPU claim table

The synthetic architecture and benchmark are **frozen** as of the per-dimension
mismatch attribution. This is the definitive list of what the paper may claim.

## Principal mechanisms (claim these)

| # | Mechanism | Evidence | Effect |
|---|---|---|---|
| 1 | **Runtime operator synthesis** | `abl_no_synthesis`, 8 640 paired episodes | −0.535 SD [−0.565, −0.506]; compound safe delivery **0.209 vs 0.952** |
| 2 | **Sequential rollout verification** | `abl_no_rollout`; mismatch study, 17 280 episodes | collisions **0.034 vs 0.004** (≈8×); false-accept 0.000 at zero mismatch, precision 1.000 |
| 3 | **Continuation-carrying restoration** | `abl_no_cont_contract` | −0.070 SD [−0.086, −0.056]; handoff error **0.132 vs 0.074** |
| 4 | **Coverage–storage trade-off vs parameterized precompiled recovery** | `run_benchmark.py` 16 200 episodes; `offline_regimes.py` | **exact parity** on covered combinations (0.994 vs 0.994, 0/0 discordant, p = 1.0); **+0.156** [+0.143, +0.170] under partial coverage; online stores 9 operators / 0 compile vs 17 branches / 109 nodes / 157 expansions |

## Secondary properties (state, do not claim as success mechanisms)

| Mechanism | Framing | Evidence |
|---|---|---|
| Event composition | **representation property** | goal differs in 163/216 compound episodes; **0/216** plan, selection or outcome differences — operator preconditions already encode the composition |
| Restore gate | **safety invariant** | **0 rejections in 706 validations** across none/moderate/severe mismatch |
| State-dependent scoring | **plan-quality preference** | selection contested in **79.2%** of decisions, changed in 25/432 episodes, **0** outcome differences |

Event composition and state-dependent scoring can be removed with no measured
loss; the restore gate is retained as a cheap invariant.

## Explicitly NOT claimed

* **Conservative verification** — measured, fails: FA 0.063 → 0.054 at moderate while FR reaches 0.507 and net SD *worsens* (0.887 vs 0.918).
* **Receding-horizon reverification** — measured, fails: 0.917 vs 0.918 (moderate) despite ~2.9 replans/episode.
* Universal superiority over precompiled recovery — the strong parameterized baseline is **exactly equal** on covered combinations.
* Open-set recovery — "novel" means a novel *composition of known predicates*.
* World-model reconstruction or learned dynamics — there are none.
* Any guarantee of physical success — see the L1/L2/L3 separation.

## Scope conditions that must accompany the verification claim

Sequential rollout verification is reliable **to the extent that the observed
state is accurate and current**. False-accept rate under single-source severe
mismatch: guard latency 0.393, object-position noise 0.285, target error 0.183;
but ≤ 0.042 for every actuation-side source. Report the false-accept curve
wherever verification is claimed.

## Theory (frozen)

* **Theorem 1** — simultaneous-objective conflict lower bound (`inf`, nonempty sets, fixed-weights corollary with the non-uniformity caveat).
* **Proposition A** — abstract search soundness (explicitly *not* physical feasibility).
* **Proposition B** — finite termination.
* **Proposition C** — conditional completeness over the bounded operator space.
* **Proposition D** — coverage–complexity under a stated idealized model (*not* a claim that all offline architectures are exponential).
* **Proposition E** — conditional restoration (conditional on *arrival*; no guarantee of arrival under mismatch).
* **L1 / L2 / L3** — abstract soundness, rollout feasibility under `f̂`, physical success under `f ≠ f̂`. Never collapse them.

## Reproducibility

69 tests; 13 scripts. Scene sampling uses a process-stable blake2b seed
(a previous salted-`hash()` defect made the benchmark non-reproducible across
processes; fixed and regression-tested).

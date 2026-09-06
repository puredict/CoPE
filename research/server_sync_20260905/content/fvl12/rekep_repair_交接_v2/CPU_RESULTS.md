# Frozen CPU results

All numbers below were produced on the CPU development machine and are frozen.
Raw script output is in `results_cpu/*.txt`; machine-readable summaries in
`results_cpu/*.csv` and `results_cpu/mismatch_attribution.json`.

**Reproduce everything:**
```bash
bash scripts/reproduce_cpu_results.sh            # full, ~25-40 min
bash scripts/reproduce_cpu_results.sh --quick    # smoke, ~5 min
```

---

## 1. Main benchmark — 16,200 paired episodes

3 task families × 6 event conditions × 3 severities × 50 paired seeds × 6 methods.

```bash
cd code && python scripts/run_benchmark.py
```

| Method | Safe delivery | Collision-free recovery | Task success |
|---|---|---|---|
| path-only | 0.436 [0.418, 0.455] | 0.776 [0.759, 0.791] | 0.182 [0.168, 0.197] |
| safe-stop | 0.623 [0.604, 0.641] | 0.962 [0.954, 0.968] | 0.266 [0.249, 0.283] |
| template repair | 0.429 [0.411, 0.448] | 0.427 [0.408, 0.445] | 0.262 [0.246, 0.279] |
| offline atomic | 0.593 [0.574, 0.611] | 0.593 [0.574, 0.611] | 0.423 [0.404, 0.442] |
| **offline exact** | **0.973 [0.966, 0.978]** | **0.973 [0.966, 0.978]** | **0.683 [0.665, 0.700]** |
| **online repair** | **0.973 [0.966, 0.978]** | **0.973 [0.966, 0.978]** | **0.683 [0.665, 0.700]** |

### Paired difference vs. online repair

| Method | Δ safe delivery | discordant (+/−) | p (Holm) |
|---|---|---|---|
| path-only | +0.537 [+0.518, +0.556] | 1450 / 1 | <1e-4 |
| safe-stop | +0.350 [+0.332, +0.369] | 948 / 2 | <1e-4 |
| template repair | +0.544 [+0.525, +0.563] | 1468 / 0 | <1e-4 |
| offline atomic | +0.380 [+0.362, +0.399] | 1026 / 0 | <1e-4 |
| **offline exact** | **+0.000 [+0.000, +0.000]** | **0 / 0** | **1.0000** |

**The headline: exact precompiled coverage matches online repair exactly** — on
all three metrics, with zero discordant pairs.

### Safe delivery by condition

| Condition | path-only | safe-stop | template | off. atomic | off. exact | online |
|---|---|---|---|---|---|---|
| obstacle | 0.431 | 0.984 | 0.984 | 0.984 | 0.984 | 0.984 |
| slip | 0.042 | 0.042 | 1.000 | 1.000 | 1.000 | 1.000 |
| relocation | 1.000 | 1.000 | 0.018 | 1.000 | 1.000 | 1.000 |
| obstacle+slip | 0.293 | 0.673 | 0.573 | 0.573 | **0.864** | **0.864** |
| obstacle+relocation | 0.802 | 0.987 | 0.000 | 0.000 | **0.989** | **0.989** |
| slip+relocation | 0.049 | 0.049 | 0.000 | 0.000 | **1.000** | **1.000** |

The offline-atomic gap is **entirely** in compound conditions.

### Runtime cost

| Method | latency (ms) | repairs | repair len | cand gen | cand rej | search expansions |
|---|---|---|---|---|---|---|
| path-only | 0.40 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| safe-stop | 0.68 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| template repair | 1.37 | 0.52 | 2.35 | 1.40 | 0.62 | 0.00 |
| offline atomic | 1.75 | 0.81 | 4.33 | 1.69 | 0.03 | 0.00 |
| offline exact | 4.17 | 1.40 | 7.85 | 3.40 | 0.04 | 0.00 |
| online repair | 2.95 | 1.40 | 7.85 | 3.73 | 0.04 | **15.16** |

> Offline latency **includes** one-off precompilation done at reset; in
> deployment that is amortized. Compare `compile` separately.

---

## 2. Coverage–storage trade-off

```bash
cd code && python scripts/offline_regimes.py
```

| Method | combos | branches | graph nodes | compile expansions | stored | SD coverage |
|---|---|---|---|---|---|---|
| offline budget(1) | 1 | 1 | 5 | 6 | 1 branch | 1/7 |
| offline atomic(3) | 3 | 6 | 32 | 31 | 3 branches | 5/7 |
| offline exact(7) | 7 | 17 | 109 | 157 | 7 branches | **7/7** |
| **online** | — | — | **0** | **0** | **9 operators** | **7/7** |

Full coverage costs 17 branches / 109 nodes / 157 offline expansions; online
reaches the same coverage with a constant 9-operator library and no compilation.

---

## 3. Ablations — 9,720 paired episodes

```bash
cd code && python scripts/run_ablations.py --seeds 20
```

| Variant | Safe delivery | Task success | collide | fail-safe | handoff err | Verdict |
|---|---|---|---|---|---|---|
| **full** | 0.972 [0.961, 0.980] | 0.679 | 0.005 | 0.028 | 0.075 | — |
| No synthesis | **0.427** [0.398, 0.457] | 0.254 | 0.005 | 0.574 | 0.454 | **causal** |
| No rollout verification | 0.964 [0.951, 0.973] | 0.679 | **0.032** | 0.004 | 0.060 | **causal** |
| No continuation contract | **0.908** [0.890, 0.924] | 0.582 | 0.005 | 0.092 | **0.126** | **causal** |
| *No event composition* | 0.972 | 0.679 | 0.005 | 0.028 | 0.075 | null |
| *No restore gate* | 0.972 | 0.679 | 0.005 | 0.028 | 0.075 | null |
| *No state-dependent scoring* | 0.972 | 0.679 | 0.005 | 0.028 | 0.075 | null |

### Why the three nulls are null (investigated, not hidden)

Each was checked by **internal-activation tracing** (does the ablation move the
intended variable?) and **targeted counterfactuals**. All three are *internally
active but outcome-neutral*:

* **Event composition** — the reduced goal genuinely differs in **163/216**
  compound episodes, yet plans, selections, outcomes, rejections and search
  expansions are identical in **0/216**. Operator preconditions already encode
  the composition: `Realign` requires `safe_clearance ∧ ¬obstacle_present ∧
  object_grasped ∧ object_stable`, so a single-predicate goal cannot be reached
  without resolving the others. → **representation property**.
* **Restore gate** — **0 rejections in 706 validations**, including under
  *severe* mismatch. `Realign` establishes the contract before the transition is
  attempted. → **safety invariant that always holds**.
* **State-dependent scoring** — selection is genuinely contested (>1 surviving
  candidate in **79.2%** of decisions; selection changes in 25/432 episodes) yet
  produces **0** outcome differences: every rollout-verified candidate is
  outcome-equivalent. → **plan-quality preference**.

Reproduce the mechanism analysis:
```bash
cd code && python scripts/ablation_activation.py
cd code && python scripts/mechanism_identification.py --seeds 25
```

---

## 4. Model mismatch — 17,280 episodes

```bash
cd code && python scripts/run_mismatch.py --seeds 20
```

False-accept rate (verifier accepted, execution failed):

| Verifier | none | mild | moderate | severe |
|---|---|---|---|---|
| none (accept all) | 0.034 | 0.067 | 0.094 | 0.253 |
| **nominal** | **0.000** | **0.028** | **0.063** | **0.228** |
| conservative | 0.000 | 0.027 | 0.054 | 0.214 |
| receding horizon | 0.000 | 0.028 | 0.064 | 0.226 |
| *false-reject (nominal)* | 0.080 | 0.080 | 0.080 | 0.080 |
| *false-reject (conservative)* | **0.667** | **0.623** | **0.507** | **0.304** |

Nominal verification is dependable through *mild*, marginal at *moderate*,
unreliable at *severe* (precision 0.772). **Neither mitigation works** —
conservative margins barely cut false accepts while causing massive false
rejects and *worse* net safe delivery (0.887 vs 0.918 at moderate); receding
horizon is within noise despite ~2.9 replans/episode. Both are excluded from the
claims.

### Per-dimension attribution — 16,740 episodes

```bash
cd code && python scripts/run_mismatch_attribution.py --seeds 10
```

Each source enabled **alone**, at severe; ΔSD vs. the all-nominal baseline (0.970):

| source | ΔSD | false accept | collide |
|---|---|---|---|
| **guard (observation) delay** | **+0.367** | 0.393 | 0.054 |
| **object-position noise** | **+0.280** | 0.285 | 0.009 |
| **target-position error** | **+0.178** | 0.183 | 0.004 |
| stochastic regrasp failure | +0.135 | 0.139 | 0.013 |
| release drift | +0.044 | 0.046 | 0.009 |
| action noise | +0.041 | 0.042 | 0.004 |
| detector delay | +0.009 | 0.002 | 0.015 |
| obstacle-position prediction error | +0.006 | 0.006 | 0.009 |
| translation gain bias | +0.004 | 0.004 | 0.004 |
| rotation gain bias | +0.000 | 0.000 | 0.004 |

**Observation-side mismatch dominates; actuation-gain error is comparatively
mild.** Closed-loop feedback absorbs gain error. Nuance: detector delay barely
affects safe delivery (0.961 vs 0.970) but materially damages **task success**
(0.522 vs 0.681) — SD and TS rank the sources differently.

---

## 5. Theorem 1 sanity check

```bash
cd code && python scripts/validate_theorem1.py
```
Numerical minimum matches the closed-form floor λμ/(λ+μ)·δ² to ~1e-16 across
δ- and λ/μ-sweeps. This is a **sanity check that the code matches the algebra**,
not a proof; the proof is in `code/docs/THEOREM.md`.

---

## 6. Test suite

```bash
bash scripts/run_cpu_tests.sh        # or: cd code && python -m pytest
```
**71 tests pass.**

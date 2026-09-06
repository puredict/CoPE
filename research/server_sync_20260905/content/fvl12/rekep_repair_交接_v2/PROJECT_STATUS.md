# Project status

Status vocabulary — used consistently across this handoff:

| status | meaning |
|---|---|
| **completed** | implemented, frozen, covered by tests |
| **locally verified** | executed on the CPU machine and passed |
| **dry-run only** | ran on CPU in an explicit no-GPU-import mode; proves wiring, not behavior |
| **syntax-checked only** | parsed/compiled, never executed |
| **remote GPU required** | can only be established on the 3090 server |
| **not started** | no work done |

**No GPU item in this project is, or may be marked, tested.**

## Method and implementation

| Component | Status |
|---|---|
| `TaskProgram` IR + stage state machine | completed / locally verified |
| Continuation capture (κ) | completed / locally verified |
| First-class event requirements (`RepairGoal` from world predicates) | completed / locally verified |
| Symbolic operators (precondition / effect / cost) | completed / locally verified |
| Runtime operator synthesis (bounded best-first search) | completed / locally verified |
| Globally unique repair instances | completed / locally verified |
| Structural legality filter | completed / locally verified |
| Sequential rollout verifier | completed / locally verified |
| Candidate scoring | completed / locally verified |
| Program splice + restore + resume | completed / locally verified |
| Bounded safe fallback | completed / locally verified |
| Provenance / runtime trace | completed / locally verified |
| **CPU architecture** | **FROZEN** |

## Baselines

| Baseline | Status |
|---|---|
| path-only, safe-stop, fixed-program | completed / locally verified |
| runtime template instantiation | completed / locally verified |
| parameterized precompiled recovery (exact / atomic / budget) | completed / locally verified |

## Evidence

| Study | Episodes | Status |
|---|---|---|
| Randomized paired benchmark | 16,200 | locally verified |
| Ablations | 8,640 | locally verified |
| Model mismatch (aggregate, 4 verifier variants) | 17,280 | locally verified |
| Per-dimension mismatch attribution | 16,740 | locally verified |
| Theorem-1 numerical sanity check | — | locally verified |
| Automated test suite (71 tests) | — | locally verified |

## Theory

| Result | Status |
|---|---|
| Theorem 1 — simultaneous-objective conflict lower bound | drafted, proof written, numerically sanity-checked |
| Prop. A — abstract search soundness | drafted |
| Prop. B — finite termination | drafted |
| Prop. C — conditional completeness | drafted |
| Prop. D — coverage–complexity | drafted (idealized model, stated as such) |
| Prop. E — conditional restoration | drafted |
| L1 / L2 / L3 separation | drafted |

All are internal drafts, not externally reviewed.

## Mechanism verdicts (from the ablation + counterfactual studies)

| Mechanism | Verdict |
|---|---|
| Runtime operator synthesis | **causal — primary claim** |
| Sequential rollout verification | **causal — primary claim** |
| Continuation-carrying restoration | **causal — primary claim** |
| Coverage–storage trade-off | **measured — primary claim** |
| Event composition | internally active, outcome-neutral → **representation property** |
| Restore gate | never rejects (0/706) → **safety invariant** |
| State-dependent scoring | contested but outcome-neutral → **plan-quality preference** |
| Provenance logging | no behavioral path → **instrumentation** |

## GPU / ReKep integration

| Item | Status |
|---|---|
| Frozen adapter interface (`adapter.py`) | completed / locally verified |
| `SyntheticAdapter` reference implementation | completed / locally verified |
| `ReKepOmniGibsonAdapter` | implemented; **dry-run only** |
| `check_gpu_environment.py` | **dry-run only** (full mode: remote GPU required) |
| `run_omni_smoke_test.py` | **dry-run only** |
| `run_rekep_baseline.py` (nominal / wrapped / repair) | **dry-run only** |
| `launch_gpu_workers.sh` | **syntax-checked only** + DRY_RUN validated |
| GPU config templates | **syntax-checked only** (placeholders) |
| Version pins (CUDA / torch / Isaac Sim / OmniGibson) | **remote GPU required** — proposed, unconfirmed |
| Milestone 0–5 | **not started** |
| Real-robot validation | **not started** (out of scope) |

## Known unfinished items

* **Adapter keypoint indices are placeholders** and will be wrong for any real
  scene — must be set per task (see `configs_gpu/adapter_keypoints.yaml`).
* `simulate_candidate`'s GPU branch calls ReKep solver methods whose exact names
  must be confirmed against the pinned ReKep revision.
* Requirement *merging* for events arriving mid-repair is not implemented;
  current policy is deferral (recorded, never silently dropped).
* Conservative and receding-horizon verification were measured and **both fail**;
  they are excluded from the claims and should not be revived without a redesign.

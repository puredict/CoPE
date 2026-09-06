# README FIRST — `cope_fsrpc_交接_v2`

Persistent local constraint-state patching (**CoPE**) versus full-state
regeneration (**FSR-PC**), on a reliability-gated multi-object basket-sorting
benchmark.

The updated package contains a real LIBERO/robosuite/MuJoCo backend and audited
server-side simulator evidence. The execution substrate is a privileged
geometry oracle on OnTheGroundPanda/OSC_POSE; it is not a learned policy.
Offscreen rendering uses OSMesa on CPU, so these are simulator mechanism
results, not GPU-inference or physical-robot results.

---

## Read in this order

| # | file | why |
|---|---|---|
| 1 | `PROJECT_STATUS.md` | where things stand, what is and is not established |
| 2 | `FSRPC_BASELINE_SPEC.md` | **read before writing anything about FSR-PC** |
| 3 | `COPE_METHOD.md` | the semantic layer and how it sits on the frozen repair core |
| 4 | `BENCHMARK_TASK.md` | the task, the reliability gate, the four interruption conditions |
| 5 | `FAIR_COMPARISON_PROTOCOL.md` | the five fairness controls and the test that asserts each |
| 6 | `METRICS.md` | the 32 metrics and the CPU results |
| 7 | `PILOT_EXPERIMENT.md` | full pilot protocol, results, and honest interpretation |
| 8 | `BACKEND_INTERFACE.md` | simulator API and candidate-isolation contract |
| 9 | `GPU_INTEGRATION_STATUS.md` | audited server and gate status |
| 10 | `GPU_RUNBOOK.md` | exact gated server commands |
| 11 | `COLLABORATION_NOTES.md` | attribution, terminology discipline, open questions |
| 12 | `CHANGELOG_FROM_REKEP_V2.md` | what changed from the previous handoff |
| 13 | `VALIDATION_REPORT.md` | every local check, with its actual output |
| 14 | `CHANGELOG.md` | real-backend qualification delta |
| 15 | `research/EXPERIMENT_RESULTS.md` | real run denominators and exclusions |
| 2b | `REPAIR_INTEGRATION.md` | **how the frozen repair engine is wired in** — read right after the status |
| — | `report/cope_fsrpc_experiment_design.pdf` | the whole thing in 7 pages |

---

## The one thing not to get wrong

> **FSR-PC is not a published algorithm.** The acronym appears in no
> collaborator material; the expansion *Full-State Regeneration with
> Progress/Context* comes only from the project brief. Write "our internally
> defined strong baseline". Attach no citation. Do not imply prior art.

Full record of what was searched: `FSRPC_BASELINE_SPEC.md` §1.

---

## Reproduce the CPU results

```bash
python3 -m pytest tests/ -q                          # 138 tests
python3 scripts/cope_pipeline_trace.py --all --seed 0  # the gate; exits non-zero on failure
python3 scripts/run_cope_pilot.py --seeds 5 --out results_cpu_rerun
```

Or all of it at once: `bash run_all.sh`.

The CPU path needs only numpy + pytest. The real backend is imported only when
explicitly selected and fails fast if LIBERO/robosuite/MuJoCo are unavailable.

---

## Headline numbers

| | CoPE | FSR-PC |
|---|---|---|
| revised task success | 20/20 | 20/20 (**tie**) |
| identity preserved | 20/20 | 0/20 |
| mean normalized edit distance | 0.457 | 1.000 |
| audit coverage | 1.000 | 0.458 |
| repairs / candidates / splices / resumes | 1.75 / 3.25 / 1.75 / 1.75 | **identical** |

Every interruption drove the complete ten-marker repair pipeline: 105 repairs,
165 rollout-verified candidates, 105 splices, 0 fallbacks, 0 incomplete.

That reliability number is the shipped Synthetic2D/CPU gate, not a
real-simulator result. Real preflight and a full nominal seed-0 debug passed;
the real 10-seed gate and 60-episode pilot are reported separately in
`GPU_INTEGRATION_STATUS.md` and are never inferred from CPU numbers.

CoPE does **not** beat FSR-PC on task success, and this package does not claim
it does. The differences are in state representation, edit locality, and which
audit questions the record can answer.

---

## Layout

```
README_FIRST.md              this file
PROJECT_STATUS.md            status, claims, next actions
COPE_METHOD.md               semantic layer + adapter
FSRPC_BASELINE_SPEC.md       baseline provenance and specification
BENCHMARK_TASK.md            task, gate, interruption conditions
FAIR_COMPARISON_PROTOCOL.md  fairness controls F1-F5 + statistics
METRICS.md                   metric definitions + CPU results
PILOT_EXPERIMENT.md          protocol, results, honest interpretation
BACKEND_INTERFACE.md         backend API + candidate-isolation contract
GPU_INTEGRATION_STATUS.md    audited real-simulator status
GPU_RUNBOOK.md               gated server commands
COLLABORATION_NOTES.md       attribution + open questions
CHANGELOG_FROM_REKEP_V2.md   diff from the previous handoff
CHANGELOG.md                 real backend qualification delta
VALIDATION_REPORT.md         every local check and its actual output
REPAIR_INTEGRATION.md        the frozen-engine integration, requirement by requirement
SHA256SUMS.txt               checksums of every delivered file
handoff_manifest.json        build record + per-file byte-identity checks
code/cope/                   the CoPE package (copied verbatim)
code/rekep_repair/           the COMPLETE frozen online-repair core (63 modules)
conftest.py, run_all.sh      generated so the package runs standalone
configs_gpu/                 REMOTE GPU SERVER ONLY
scripts/                     pilot runner, dry run, env check, this builder
tests/                       138 tests (incl. backend contract)
results_cpu/                 pilot JSON + 5 dry-run traces
results_schema/              JSON schema + one example episode record
report/                      LaTeX source + compiled PDF
research/                    server audit, experiment tables, debug CSV
```

`code/cope/` now includes the backend integration. The original CPU ZIP is
preserved separately; final SHA-256 and manifest files are regenerated only
after the real-simulator gates finish.

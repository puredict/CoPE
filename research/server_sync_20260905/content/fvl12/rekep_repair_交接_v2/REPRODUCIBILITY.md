# Reproducibility

## Environment used to produce the CPU results

| item | value |
|---|---|
| OS | macOS (Darwin 25.2.0), **CPU-only** |
| Python | 3.12.2 |
| numpy / scipy / matplotlib | 2.4.6 / 1.17.1 / 3.10.9 |
| LaTeX | TeX Live 2026 (pdfTeX 3.141592653-2.6-1.40.29) |
| GPU | **none** — no CUDA, Isaac Sim, OmniGibson or ReKep was ever executed |

The GPU target environment pins Python **3.10** (OmniGibson/Isaac Sim
requirement). The CPU code runs on both; the test suite is not sensitive to the
difference.

## Determinism guarantees

* **Scene sampling is a pure function** of `(family, condition, severity, seed)`
  using a process-stable **blake2b** seed. Pairing is exact *by construction*.
* This was a real defect once: sampling originally keyed on Python's `hash(str)`,
  which is **salted per process**, so scenes silently differed between runs. It
  is fixed and covered by
  `tests/test_mechanisms.py::test_scene_sampling_is_stable_across_processes`,
  which spawns a subprocess and compares seeds.
* Synthetic dynamics are deterministic; mismatch noise is drawn from a
  per-episode `default_rng(seed + 9973)`, so a given (seed, mismatch level) pair
  reproduces exactly.
* The environment and the rollout verifier share **one** action-clipping
  utility (`execution/action.py`), fuzz-tested over 200 random actions.

## Reproduce the CPU results

```bash
bash scripts/run_cpu_tests.sh                    # 71 tests, ~1 min
bash scripts/reproduce_cpu_results.sh            # all artifacts, ~25-40 min
bash scripts/reproduce_cpu_results.sh --quick    # smoke, ~5 min
```

Individual studies (from `code/`):

| Artifact | Command | Episodes |
|---|---|---|
| `results_cpu/benchmark_main.txt` | `python scripts/run_benchmark.py` | 16,200 |
| `results_cpu/ablations.txt` | `python scripts/run_ablations.py --seeds 20` | 9,720 |
| `results_cpu/coverage_storage.txt` | `python scripts/offline_regimes.py` | 35 |
| `results_cpu/mismatch_aggregate.txt` | `python scripts/run_mismatch.py --seeds 20` | 17,280 |
| `results_cpu/mismatch_attribution.*` | `python scripts/run_mismatch_attribution.py --seeds 10` | 16,740 |
| `results_cpu/theorem1.txt` | `python scripts/validate_theorem1.py` | — |

Mechanism analyses (qualitative, printed to stdout):

```bash
cd code && python scripts/ablation_activation.py
cd code && python scripts/mechanism_identification.py --seeds 25
```

## Expected tolerance

Discrete outcomes (SD / CFR / TS counts) should reproduce **exactly** on the
same Python + numpy versions. Timing columns (`latency_ms`) are machine
dependent and will differ. Bootstrap CIs use a fixed seed and reproduce exactly.

If proportions differ by more than ~0.005 with the same seed count, something is
wrong — check numpy version first.

## Rebuild the report

```bash
cd report && pdflatex rekep_repair_technical_report.tex && pdflatex rekep_repair_technical_report.tex
```
Two passes are needed for the table of contents. Requires only base LaTeX +
`amsmath`, `booktabs`, `longtable`, `hyperref`, `listings`, `fancyhdr`,
`microtype`, `enumitem`, `xcolor`, `caption`.

## Raw episode data

**Not included.** The studies total ~60,000 episodes; storing them would bloat
the handoff without aiding reproduction, since every number regenerates
deterministically from the commands above. `results_cpu/` contains the summary
tables and the raw *script output*, which is what the report cites.

## Verifying folder integrity

```bash
shasum -a 256 -c SHA256SUMS.txt        # macOS
sha256sum -c SHA256SUMS.txt            # Linux
```
`SHA256SUMS.txt` covers every file in the handoff except itself.

## What cannot be reproduced here

Everything GPU. `check_gpu_environment.py`, `run_omni_smoke_test.py`,
`run_rekep_baseline.py` and `launch_gpu_workers.sh` were **dry-run validated or
syntax-checked only**. Their real behavior requires the 3090 server, and no
version pin in `GPU_HANDOFF.md` has been confirmed on hardware.

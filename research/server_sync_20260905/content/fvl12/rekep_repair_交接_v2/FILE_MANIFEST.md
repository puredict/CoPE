# File manifest

Complete listing of the handoff folder.

Status: **T** locally tested · **D** locally dry-run validated · **S** syntax-checked only · **G** remote GPU required

> No file in this folder has been executed on a GPU.


## root

| file | bytes | status |
|---|---|---|
| `CODE_MAP.md` | 7,862 | T |
| `COLLABORATION_NOTES.md` | 4,395 | T |
| `CPU_RESULTS.md` | 8,453 | T |
| `GPU_EXPERIMENT_PLAN.md` | 5,193 | S / G |
| `GPU_HANDOFF.md` | 4,734 | S / G |
| `GPU_RUNBOOK.md` | 8,288 | S / G |
| `KNOWN_RISKS.md` | 5,860 | T |
| `PROJECT_STATUS.md` | 4,882 | T |
| `README_FIRST.md` | 4,172 | T |
| `REPRODUCIBILITY.md` | 3,945 | T |
| `VALIDATION_REPORT.md` | 5,874 | T |
| `handoff_manifest.json` | 9,096 | T |

## `code/`

| file | bytes | status |
|---|---|---|
| `code/README.md` | 4,667 | T |
| `code/docs/FROZEN_CLAIMS.md` | 3,904 | T |
| `code/docs/GO_NO_GO.md` | 6,911 | T |
| `code/docs/GPU_MILESTONE_1.md` | 4,172 | S / G |
| `code/docs/GPU_RISKS.md` | 4,914 | S / G |
| `code/docs/GPU_SETUP.md` | 4,734 | S / G |
| `code/docs/LIMITATIONS.md` | 5,451 | T |
| `code/docs/MECHANISMS.md` | 4,796 | T |
| `code/docs/MISMATCH_ATTRIBUTION.md` | 4,916 | T |
| `code/docs/PARADIGMS.md` | 2,590 | T |
| `code/docs/PROPOSITIONS.md` | 7,944 | T |
| `code/docs/THEOREM.md` | 6,113 | T |
| `code/pyproject.toml` | 735 | T |
| `code/rekep_repair/.DS_Store` | 8,196 | T |
| `code/rekep_repair/__init__.py` | 120 | T |
| `code/rekep_repair/adapter.py` | 4,602 | T |
| `code/rekep_repair/benchmark/__init__.py` | 614 | T |
| `code/rekep_repair/benchmark/mismatch.py` | 8,358 | T |
| `code/rekep_repair/benchmark/probe.py` | 4,997 | T |
| `code/rekep_repair/benchmark/runner.py` | 3,091 | T |
| `code/rekep_repair/benchmark/scenes.py` | 5,486 | T |
| `code/rekep_repair/benchmark/statistics.py` | 2,709 | T |
| `code/rekep_repair/events/__init__.py` | 201 | T |
| `code/rekep_repair/events/detector.py` | 3,230 | T |
| `code/rekep_repair/events/event.py` | 1,280 | T |
| `code/rekep_repair/events/predicates.py` | 1,019 | T |
| `code/rekep_repair/execution/__init__.py` | 147 | T |
| `code/rekep_repair/execution/action.py` | 1,145 | T |
| `code/rekep_repair/execution/context.py` | 1,957 | T |
| `code/rekep_repair/execution/controller.py` | 3,440 | T |
| `code/rekep_repair/execution/executor.py` | 3,039 | T |
| `code/rekep_repair/execution/fallback.py` | 778 | T |
| `code/rekep_repair/execution/guard_monitor.py` | 2,340 | T |
| `code/rekep_repair/execution/provenance_logger.py` | 2,991 | T |
| `code/rekep_repair/policies/__init__.py` | 1,457 | T |
| `code/rekep_repair/policies/ablations.py` | 4,718 | T |
| `code/rekep_repair/policies/common.py` | 2,082 | T |
| `code/rekep_repair/policies/fixed_program.py` | 1,006 | T |
| `code/rekep_repair/policies/offline_parameterized.py` | 7,234 | T |
| `code/rekep_repair/policies/offline_recovery.py` | 8,529 | T |
| `code/rekep_repair/policies/online_repair.py` | 11,247 | T |
| `code/rekep_repair/policies/path_only.py` | 1,418 | T |
| `code/rekep_repair/policies/safe_stop.py` | 1,541 | T |
| `code/rekep_repair/policies/template_repair.py` | 832 | T |
| `code/rekep_repair/policies/verified_repair.py` | 3,320 | T |
| `code/rekep_repair/program/__init__.py` | 479 | T |
| `code/rekep_repair/program/continuation.py` | 2,418 | T |
| `code/rekep_repair/program/contracts.py` | 2,863 | T |
| `code/rekep_repair/program/graph.py` | 3,365 | T |
| `code/rekep_repair/program/stage.py` | 3,817 | T |
| `code/rekep_repair/program/task_program.py` | 11,937 | T |
| `code/rekep_repair/rekep_adapter.py` | 11,776 | D / G |
| `code/rekep_repair/repair/__init__.py` | 1,165 | T |
| `code/rekep_repair/repair/abstract_state.py` | 8,743 | T |
| `code/rekep_repair/repair/candidate.py` | 1,245 | T |
| `code/rekep_repair/repair/candidate_generator.py` | 1,333 | T |
| `code/rekep_repair/repair/feasibility_filter.py` | 3,251 | T |
| `code/rekep_repair/repair/legality_filter.py` | 2,666 | T |
| `code/rekep_repair/repair/operator.py` | 6,174 | T |
| `code/rekep_repair/repair/planner.py` | 3,281 | T |
| `code/rekep_repair/repair/repair_manager.py` | 5,277 | T |
| `code/rekep_repair/repair/rollout_verifier.py` | 7,929 | T |
| `code/rekep_repair/repair/scorer.py` | 3,657 | T |
| `code/rekep_repair/repair/synthesis_generator.py` | 2,275 | T |
| `code/rekep_repair/repair/template_library.py` | 1,214 | T |
| `code/rekep_repair/repair/verifier_variants.py` | 3,793 | T |
| `code/rekep_repair/synthetic/__init__.py` | 326 | T |
| `code/rekep_repair/synthetic/conflict_bound.py` | 4,864 | T |
| `code/rekep_repair/synthetic/dynamics.py` | 9,736 | T |
| `code/rekep_repair/synthetic/env.py` | 4,321 | T |
| `code/requirements_cpu.txt` | 410 | T |
| `code/requirements_gpu.txt` | 1,822 | S / G |
| `code/scripts/ablation_activation.py` | 4,264 | T |
| `code/scripts/check_gpu_environment.py` | 8,202 | D / G |
| `code/scripts/compare_known_event.py` | 2,834 | T |
| `code/scripts/compare_novel_composition.py` | 2,891 | T |
| `code/scripts/coverage_experiment.py` | 4,816 | T |
| `code/scripts/launch_gpu_workers.sh` | 4,087 | S / G |
| `code/scripts/mechanism_identification.py` | 5,843 | T |
| `code/scripts/offline_regimes.py` | 4,685 | T |
| `code/scripts/rollout_traces.py` | 1,846 | T |
| `code/scripts/run_ablations.py` | 5,330 | T |
| `code/scripts/run_benchmark.py` | 5,856 | T |
| `code/scripts/run_comparison.py` | 1,927 | T |
| `code/scripts/run_mismatch.py` | 6,485 | T |
| `code/scripts/run_mismatch_attribution.py` | 5,672 | T |
| `code/scripts/run_omni_smoke_test.py` | 3,288 | D / G |
| `code/scripts/run_rekep_baseline.py` | 6,542 | D / G |
| `code/scripts/run_trace.py` | 5,781 | T |
| `code/scripts/two_interruptions.py` | 2,400 | T |
| `code/scripts/validate_theorem1.py` | 2,897 | T |
| `code/tests/__init__.py` | 0 | T |
| `code/tests/helpers.py` | 2,041 | T |
| `code/tests/test_action_limits.py` | 2,110 | T |
| `code/tests/test_baseline_validity.py` | 6,514 | T |
| `code/tests/test_events.py` | 2,177 | T |
| `code/tests/test_execution.py` | 2,950 | T |
| `code/tests/test_mechanisms.py` | 6,652 | T |
| `code/tests/test_program_semantics.py` | 5,167 | T |
| `code/tests/test_repair_filters.py` | 3,384 | T |
| `code/tests/test_scientific.py` | 10,655 | T |
| `code/tests/test_synthesis.py` | 5,268 | T |

## `configs_gpu/`

| file | bytes | status |
|---|---|---|
| `configs_gpu/adapter_keypoints.yaml` | 890 | S / G |
| `configs_gpu/logging.yaml` | 540 | S / G |
| `configs_gpu/machine.yaml` | 729 | S / G |
| `configs_gpu/sweep.yaml` | 710 | S / G |
| `configs_gpu/tasks.yaml` | 1,045 | S / G |

## `report/`

| file | bytes | status |
|---|---|---|
| `report/figures/README.txt` | 61 | T |
| `report/rekep_repair_technical_report.pdf` | 316,003 | T |
| `report/rekep_repair_technical_report.tex` | 45,803 | T |
| `report/tables/ablations.csv` | 454 | T |
| `report/tables/coverage_storage.csv` | 203 | T |
| `report/tables/main_benchmark.csv` | 327 | T |
| `report/tables/mismatch_attribution.csv` | 388 | T |

## `results_cpu/`

| file | bytes | status |
|---|---|---|
| `results_cpu/ablations.csv` | 454 | T |
| `results_cpu/ablations.txt` | 4,740 | T |
| `results_cpu/benchmark_main.txt` | 5,221 | T |
| `results_cpu/coverage_storage.csv` | 203 | T |
| `results_cpu/coverage_storage.txt` | 1,336 | T |
| `results_cpu/main_benchmark.csv` | 327 | T |
| `results_cpu/mismatch_aggregate.txt` | 5,232 | T |
| `results_cpu/mismatch_attribution.csv` | 388 | T |
| `results_cpu/mismatch_attribution.json` | 7,295 | T |
| `results_cpu/mismatch_attribution.txt` | 4,158 | T |
| `results_cpu/theorem1.txt` | 1,966 | T |

## `scripts/`

| file | bytes | status |
|---|---|---|
| `scripts/aggregate_results.py` | 1,454 | T |
| `scripts/check_gpu_environment.py` | 530 | D / G |
| `scripts/launch_gpu_workers.sh` | 242 | S / G |
| `scripts/reproduce_cpu_results.sh` | 1,180 | T |
| `scripts/run_cpu_tests.sh` | 186 | T |
| `scripts/run_milestone1.sh` | 1,026 | S / G |
| `scripts/run_omni_smoke_test.py` | 526 | D / G |
| `scripts/run_rekep_baseline.py` | 524 | D / G |

---

**Total: 145 files, 884,567 bytes (excluding SHA256SUMS.txt and this manifest).**

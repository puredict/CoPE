# Validation report

Every check below was run **from inside this handoff folder** on the CPU
development machine (macOS, Python 3.12.2, no GPU).

Status vocabulary: **locally executed and passed** · **locally dry-run
validated** · **syntax-checked only** · **remote GPU execution required** ·
**not yet tested**.

---

## 1. CPU test suite — *locally executed and passed*

```
$ bash scripts/run_cpu_tests.sh
=== pytest (expect 71 passed) ===
.......................................................................  [100%]
```
**71 tests passed.** Run from `code/`, i.e. the copied project, not the source repo.

## 2. CPU reproduction scripts — *locally executed and passed*

```
$ cd code && python scripts/validate_theorem1.py
RESULT: ALL CHECKS PASSED
```

```
$ cd code && python scripts/offline_regimes.py
method               combos  branch  graph  compile     SD   CFR    TS
offline_budget(1)    1       1       5      6        1/7   1/7   1/7
offline_budget(3)    3       6       32     31       5/7   5/7   3/7
offline_atomic(3)    3       6       32     31       5/7   5/7   3/7
offline_exact(7)     7       17      109    157      7/7   7/7   3/7
online_synthesis     --      -- (ops) 0      0        7/7   7/7   3/7
```

All six result artifacts in `results_cpu/` were regenerated from the copied code:
`benchmark_main.txt` (16,200 episodes), `ablations.txt` (9,720),
`coverage_storage.txt`, `mismatch_aggregate.txt` (17,280),
`mismatch_attribution.{txt,json}` (16,740), `theorem1.txt`.

## 3. LaTeX compilation — *locally executed and passed*

```
$ cd report && pdflatex rekep_repair_technical_report.tex   (x3 passes)
Output written on rekep_repair_technical_report.pdf (16 pages, 316003 bytes).
```
**16-page PDF produced.** Auxiliary files (`.aux/.log/.out/.toc`) removed.

## 4. GPU scripts in dry-run — *locally dry-run validated*

```
OK  check_gpu_environment.py --dry-run
OK  run_omni_smoke_test.py --dry-run
OK  run_rekep_baseline.py --mode repair --dry-run --steps 120
OK  run_milestone1.sh DRY_RUN=1
OK  launch_gpu_workers.sh (bash -n)
```

`check_gpu_environment.py --dry-run` correctly reports the CPU machine's
mismatch with the GPU target and **SKIPs** every GPU check:
```
[FAIL] python      found 3.12, OmniGibson/IsaacSim pin 3.10
[FAIL] os          Darwin: Isaac Sim/OmniGibson are Linux-only (expected on the dev machine)
[PASS] rekep_repair (repair layer)   v0.0.1
[SKIP] check_driver (GPU) / check_torch (GPU) / check_sim_stack (GPU)
Dry-run complete. GPU checks were SKIPPED and remain 'requires remote GPU verification'.
```

Full (non-dry-run) mode **refuses to run on macOS**, exiting with code 2.

`run_rekep_baseline.py --dry-run` exercises the complete repair pipeline through
the adapter interface, producing:
```
SELECTED  Suspend+Retreat+Stabilize+WaitUntilClear+Realign+Resume (score=6.140)
program:  pour → …::r1::suspend#0 → retreat#1 → stabilize#2
                → waituntilclear#3 → realign#4 → resume#5 → pour#resume::r1
```
This proves **wiring only** — it uses a scripted fake, not a simulator.

## 5. No dry-run imports a GPU-only module — *locally executed and passed*

Each script was executed in-process and `sys.modules` inspected afterwards:
```
check_gpu_environment      GPU_MODULES: []
run_omni_smoke_test        GPU_MODULES: []
run_rekep_baseline         GPU_MODULES: []
```
None of `torch`, `omni`, `omnigibson`, `isaacsim` was imported. This is also
enforced by
`tests/test_baseline_validity.py::test_gpu_scripts_import_without_gpu_dependencies`.

## 6. Absolute paths, secrets, credentials — *locally executed and passed*

```
$ grep -rIl -e '/Users/jiaqitang' -e '/private/tmp/claude' .
  CLEAN - none found
```
No machine-specific absolute paths. No API-key, token, password, or `sk-…`
pattern found. GPU configs use `<REKEP_ROOT>`, `<OMNIGIBSON_ASSET_PATH>`,
`<OUTPUT_ROOT>` placeholders only.

> **One real defect was found by this check** and fixed: `results_cpu/ablations.txt`
> initially contained a Python traceback (with an absolute path) because
> `run_ablations.py` still referenced the pre-split ablation keys
> `abl_no_restore` / `abl_no_continuation`. The script was corrected and the
> artifact regenerated.

## 7. Caches and large files — *locally executed and passed*

```
$ find . -type f -size +1M          → none
$ find . -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc'   → none
```
Total: **144 files, ~879 KB.** No `.git/`, `.venv/`, simulator assets, or
generated episode folders.

## 8. Documentation command paths — *locally executed and passed*

Every `scripts/…`, `code/…`, `report/…`, `results_cpu/…`, `configs_gpu/…` path
referenced in the Markdown resolves. Apparent misses were verified as either
(a) commands prefixed `cd code &&` — the file exists at `code/scripts/…` — or
(b) `scripts/setup.sh`, which is **OmniGibson's own installer**, correctly not
shipped here.

---

## Explicit status of everything GPU

| Item | Status |
|---|---|
| Driver / CUDA / torch / Isaac Sim / OmniGibson version pins | **remote GPU execution required** — proposed, unconfirmed on hardware |
| `check_gpu_environment.py` full mode | **remote GPU execution required** |
| `run_omni_smoke_test.py` full mode | **remote GPU execution required** |
| `run_rekep_baseline.py` nominal / wrapped / repair on GPU | **remote GPU execution required** |
| `launch_gpu_workers.sh` real launch | **syntax-checked only** |
| `ReKepOmniGibsonAdapter` GPU branch | **not yet tested** — ReKep solver method names must be confirmed against the pinned revision |
| Adapter keypoint indices | **not yet tested** — placeholders, certain to be wrong |
| Milestones 0–5 | **not started** |

**No GPU code has been executed anywhere, by me or by any process on this
machine. Nothing in this folder may be described as GPU-tested.**

---

# v2 validation (GPU P0-1 .. P0-4)

## 1. Test suite — *locally executed and passed*
```
$ cd code && python -m pytest -q
94 passed
```
71 frozen CPU tests (unchanged) + 23 new GPU-metric tests covering all 12
required cases.

## 2. Byte-identity: canonical repo vs `code/` — *locally executed and passed*
```
compared 114 files -> IDENTICAL 114, problems 0
```
Full per-file SHA-256 table in `CODE_SYNC_SHA256.csv`. New v2 modules:

| file | sha256 (first 16) |
|---|---|
| `rekep_repair/gpu_metrics/__init__.py` | `8858b680013fb8b4` |
| `rekep_repair/gpu_metrics/geometry.py` | `3c68f3bbe631d854` |
| `rekep_repair/gpu_metrics/gpu_rollout.py` | `ed9d029d90d1029a` |
| `rekep_repair/gpu_metrics/pen_in_holder.py` | `7c354a34ab413898` |
| `rekep_repair/gpu_metrics/pilot_spec.py` | `bc988c682bf020ee` |
| `rekep_repair/gpu_metrics/restore_contract.py` | `29d88c0b7ba4d5ca` |
| `rekep_repair/gpu_metrics/structured_log.py` | `7934fba142c60efa` |
| `tests/test_gpu_metrics.py` | `596ece9ac088cf33` |
| `scripts/run_gpu_pilot_episode.py` | `8345af49e372e272` |
| `scripts/run_gpu_pilot.sh` | `f7a90a0953ec67ab` |
| `scripts/aggregate_pilot.py` | `0e1780eb699ff030` |
| `scripts/evaluate_pen_in_holder_retrospective.py` | `4388f109dd65e88c` |

## 3. GPU dry-runs — *locally dry-run validated*
```
OK  run_gpu_pilot_episode.py --dry-run
OK  run_gpu_pilot.sh DRY_RUN=1        (pre-flight gate fired: rollouts=3 rejected=2)
OK  evaluate_pen_in_holder_retrospective.py
GPU_MODULES imported: NONE            (torch / omni / omnigibson / isaacsim absent)
```

## 4. Immutable folders — *locally executed and passed*
Tree hashes recomputed after all v2 work and compared to the session-start
baselines; **all three identical**:
```
rekep_gpu_execution   bd9da3da6bdee0a280e2baa6e5afb6b77dc4674e5f8a841466fb015d81d10bd0
rekep_repair_交接      8c34b04813fa5714aa2242a9f87fca4eb9117472688826798c99e36dab7efb5a
rekep_gpu_analysis    17d7644762398504711f8eed46e657f504812eabebc93d72247e0b1f836c77ce
```

## 5. Folder hygiene
161 files checksummed, 0 failures, 1.4 MB, no caches, no >1 MB files. The
path scan flags one hit in this file: it is the *documented grep command text*
from the v1 section above, not a leaked path.

## 6. Explicitly NOT executed
The entire GPU path. `gpu_metrics` is validated against synthetic geometry and a
deterministic fake `ShadowRolloutHost`. Unproven on hardware: `og.sim.dump_state`
/ `load_state` round-tripping cleanly enough for candidate isolation; the wall
cost of one shadow rollout per candidate; the true pen/holder asset geometry;
whether the restore tolerances are reachable in practice.

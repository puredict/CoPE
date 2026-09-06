# GPU runbook — commands in strict execution order

**Every numbered command is `REMOTE GPU SERVER ONLY` unless marked otherwise.**
Nothing below has been executed by me. Work through the steps in order; do not
skip ahead to a sweep.

Throughout, `$HANDOFF` is wherever you unpacked this folder, and code lives in
`$HANDOFF/code`.

---

## Step 1 — Inspect the server

**Working directory:** anywhere.

```bash
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv
```

* **Expected:** 8 rows naming RTX 3090, driver ≥ 525.60.13, ~24 GB each.
* **Success:** 8 GPUs listed, driver new enough.
* **Likely failure:** `nvidia-smi: command not found` → driver not installed.
* **Log:** none.
* **Fallback:** stop. Nothing else can proceed. Install/upgrade the driver.

```bash
nproc && free -g && df -h /
```

* **Expected:** ≥ 8 cores, ≥ 64 GB RAM, ≥ 200 GB free (assets are large).
* **Fallback if disk is short:** put OmniGibson assets on a larger volume and
  point `<OMNIGIBSON_ASSET_PATH>` at it.

---

## Step 2 — Create the environment

**Working directory:** `$HANDOFF/code`.

```bash
conda create -n rekep python=3.10 -y && conda activate rekep
```

* **Success:** `python --version` prints 3.10.x.
* **Likely failure:** conda missing → install Miniconda first.
* **Note:** 3.10 is required. Do **not** use 3.12 (my dev machine's version).

---

## Step 3 — Install dependencies

**Working directory:** `$HANDOFF/code`.

**Torch first, from the CUDA index — this order matters:**

```bash
pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu121
```

* **Success:** `python -c "import torch; print(torch.cuda.is_available())"` → `True`.
* **Likely failure:** `False` → a CPU wheel was resolved. Uninstall and reinstall
  from the index URL; never let PyPI resolve torch.

Then OmniGibson (brings Isaac Sim) and ReKep:

```bash
git clone https://github.com/StanfordVL/OmniGibson.git && cd OmniGibson && ./scripts/setup.sh
```

```bash
git clone https://github.com/huangwl18/ReKep.git && cd ReKep && pip install -r requirements.txt
```

Then this project:

```bash
cd $HANDOFF/code && pip install -e . && pip install -r requirements_gpu.txt
```

* **Log:** keep the full pip output; version conflicts here are the single most
  likely multi-day blocker (risk R1).
* **Fallback:** if ReKep and OmniGibson disagree on a pin, **ReKep's pin wins** —
  it is the downstream consumer.

---

## Step 4 — Obtain assets

**Working directory:** `OmniGibson/`.

```bash
python -m omnigibson.utils.asset_utils --download_assets --download_demo_data
```

* **Expected:** tens of GB downloaded; a licence prompt must be accepted.
* **Success:** asset directory populated; no partial-file warnings.
* **Likely failure:** partial download that only surfaces later as a missing-asset
  error during scene creation.
* **Fallback:** re-run; verify sizes; cache on fast local disk shared read-only
  by all 8 workers.

---

## Step 5 — Run the environment checker

**Working directory:** `$HANDOFF/code`.

First the dry-run (**safe anywhere**, no GPU imports):

```bash
python scripts/check_gpu_environment.py --dry-run
```

* **Expected:** `python` and `os` PASS on Linux; `rekep_repair` PASS; GPU rows SKIP.

Then the real check:

```bash
python scripts/check_gpu_environment.py
```

* **Expected output:** a PASS/WARN/FAIL line per requirement, ending
  `OK: environment ready.`
* **Success:** exit code 0.
* **Likely failure:** `torch.cuda` FAIL (wrong wheel), or `omnigibson` FAIL
  (install incomplete).
* **Log:** capture stdout.
* **Fallback:** fix the specific FAIL; do not proceed with warnings you do not
  understand.

---

## Step 6 — OmniGibson smoke test

**Working directory:** `$HANDOFF/code`.

```bash
python scripts/run_omni_smoke_test.py --steps 100
```

* **Expected:** JSON with OmniGibson version, import seconds (minutes on first
  run — this is normal), step rate, RGB shape.
* **Success:** non-zero `hz`, valid `rgb_shape`.
* **Likely failure:** renderer/Vulkan init errors, or OOM.
* **Log:** `runs/smoke/smoke_result.json`.
* **Fallback:** set `gm.HEADLESS=True` (already default in the script); reduce
  steps; check no other process holds the GPU.

**This must pass before ReKep is involved at all.** If it fails, the problem is
the simulator stack, not our code.

---

## Step 7 — Nominal ReKep (unchanged)

**Working directory:** `$HANDOFF/code`.

```bash
python scripts/run_rekep_baseline.py --mode nominal --task pen_insertion --steps 400 --rekep-root <REKEP_ROOT> --out runs/milestone1/nominal
```

* **Expected:** the task completes as in stock ReKep; a trace with per-step stage
  index and constraints.
* **Success:** task succeeds; stage sequence recorded.
* **Likely failure:** missing cached queries (use ReKep's cached queries so no
  VLM key is needed), or scene-file path wrong.
* **Log:** `runs/milestone1/nominal/trace.json`.
* **Fallback:** stop and fix. If stock ReKep does not run, nothing downstream is
  interpretable.

---

## Step 8 — Wrapped ReKep (the parity check)

```bash
python scripts/run_rekep_baseline.py --mode wrapped --task pen_insertion --steps 400 --rekep-root <REKEP_ROOT> --out runs/milestone1/wrapped
```

* **Expected:** stage sequence and outcome **identical** to Step 7 on the same seed.
* **Success:** identical stage sequence; identical success outcome.
* **Likely failure:** divergence → a wrapping bug (risk R7: ReKep's stage
  semantics may not map cleanly onto `StageSpec`).
* **Log:** `runs/milestone1/wrapped/trace.json`.
* **Fallback:** **do not proceed.** A wrapping bug contaminates every later
  comparison. Let `TaskProgram` *mirror* ReKep's stage advance rather than
  driving it, taking control only during repair.

**This is the most important gate in the runbook.**

---

## Step 9 — Repaired ReKep

```bash
python scripts/run_rekep_baseline.py --mode repair --task upright_transport --steps 400 --rekep-root <REKEP_ROOT> --out runs/milestone1/repair
```

* **Expected:** event detected → continuation captured → repair **synthesized**
  → rollout verified using ReKep's own solvers → graph spliced → restore
  validated → interrupted stage resumed → task completes.
* **Success — all eight:** (1) event detected; (2) plan synthesized, not looked
  up; (3) verifier accepts; (4) interrupted stage `SUSPENDED` not `COMPLETED`;
  (5) repair stages execute; (6) restore contract validates; (7) stage resumes
  and task completes; (8) trace + video written.
* **Expected program shape** (this is what the CPU dry-run produces):
  ```
  <stage> → ::r1::suspend#0 → retreat#1 → stabilize#2
          → waituntilclear#3 → realign#4 → resume#5 → <stage>#resume::r1
  ```
* **Likely failures:** predicates flicker (risk R4) → repeated spurious repairs;
  verification too slow (R5) → reduce `sim_budget_steps`; adapter keypoint
  indices wrong (R6) → nonsensical clearances in the trace.
* **Log:** `runs/milestone1/repair/trace.json`.
* **Fallback:** if the verifier rejects everything, check the horizon budget
  first — in the CPU dry-run, too small a `--steps` correctly caused
  `rollout/horizon exceeded` and a safe fallback. That is correct behavior, not
  a bug.

---

## Step 10 — Inspect logs and videos

```bash
python scripts/aggregate_results.py --root runs/milestone1
```

Check by hand: stage sequence, the repair decision block, restore validation,
and the video. Confirm the robot visibly suspends, recovers, realigns, and
resumes.

---

## Step 11 — Approve or reject Milestone 1

**Approve only if** Steps 7–9 all pass **and** Steps 8 and 9 are reproducible on
a re-run with the same seed (stage sequence exact; continuous values within the
tolerance you agreed for risk R3).

```bash
touch runs/milestone1/GATE_PASSED
```

* `scripts/launch_gpu_workers.sh` **refuses to start a sweep** without this file.
* **If rejected:** record which acceptance condition failed and why. Do not
  create the gate file to "unblock" a sweep.

---

## Only then — multi-GPU

```bash
DRY_RUN=1 bash scripts/launch_gpu_workers.sh
```

Inspect the generated per-worker configs, then drop `DRY_RUN=1`. See
`GPU_EXPERIMENT_PLAN.md` for seed allocation and output conventions.

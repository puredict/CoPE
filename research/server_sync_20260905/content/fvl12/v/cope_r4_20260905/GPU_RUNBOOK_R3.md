# GPU runbook: one fixed Qwen3-32B model

The intended host has 8 RTX 3090 GPUs. LIBERO/MuJoCo rendering remains CPU
OSMesa; GPUs serve the fixed language model.

## 1. Copy and preserve the folder

Copy this entire `cope_fsrpc_r3_lineage` directory to the server. Do not run
inside or overwrite any r2 result directory. Record the returned folder
unchanged after the experiment.

## 2. Use the existing LIBERO environment

The r2 final-v8 GPU environment should already provide LIBERO, robosuite,
MuJoCo, NumPy, PyYAML, jsonschema, imageio, and ffmpeg support. Verify with:

```bash
export MUJOCO_GL=osmesa
export PYTHONPATH="$PWD/code${PYTHONPATH:+:$PYTHONPATH}"
./run_r3_tests.sh
python3 scripts/preflight_r3.py --check-libero
```

If imports fail, repair that environment before running any experiment. There is
no synthetic fallback in a run declared as `libero_mujoco`.

## 3. Start the model server

In a separate environment with vLLM installed, either let Hugging Face resolve
the model name or point to an already downloaded snapshot:

```bash
export COPE_MODEL_PATH=/absolute/path/to/Qwen3-32B
export COPE_TENSOR_PARALLEL_SIZE=8
./scripts/serve_qwen3_32b.sh 2>&1 | tee qwen3_32b_server.log
```

Keep the served name `Qwen/Qwen3-32B`; it is the registered model identifier.
If the server cannot start because the GPUs are not fully connected, reduce
`COPE_TENSOR_PARALLEL_SIZE` only if the model still fits. Record the change and
do not mix tensor-parallel settings within a run.

## 4. Preflight the exact interface

From the LIBERO environment:

```bash
python3 scripts/preflight_r3.py --server --live-call --check-libero \
  | tee preflight_r3.json
```

The report must pass. It also prints diagnostic prompt and output-size estimates.
Those estimates are not results; vLLM usage counters in each episode are the
authoritative token counts.

## 5. Run the nominal gate, then the experiment

Choose a new absolute output path on storage with room for 120 episode bundles
and videos:

```bash
./scripts/run_gpu_fixed_model.sh \
  /absolute/results/cope_fsrpc_r3_qwen32b_run1 \
  2>&1 | tee r3_run1.log
```

The wrapper performs server and LIBERO preflight, a 10-seed nominal controller
gate, all 120 paired episodes, and final validation. It refuses to overwrite an
existing run. If the gate is below 8/10, the wrapper exits before the main run.

For an inexpensive end-to-end rehearsal first:

```bash
python3 scripts/run_r3_lineage.py \
  --stage main --client openai --backend symbolic_basket \
  --profiles calibration --seeds 1 \
  --out /absolute/results/r3_one_seed_rehearsal
```

Do not combine rehearsal records with physical results.

## 6. Return these files

Return the entire project folder plus:

- the main result directory;
- the `_gate` directory;
- `qwen3_32b_server.log`;
- `preflight_r3.json`;
- `r3_run1.log`;
- `pip freeze` or the environment export;
- `nvidia-smi` output.

Every episode contains its raw model outputs, model usage/latency, events,
state snapshots, actions, result record, and (for LIBERO) video. Do not delete
failed episodes: failures are part of the primary denominator.

Optionally create a checksummed return archive outside the project directory:

```bash
python3 scripts/package_r3_handoff.py \
  --include-results \
  --out /absolute/return/cope_fsrpc_r3_qwen32b_run1.tar.gz
```

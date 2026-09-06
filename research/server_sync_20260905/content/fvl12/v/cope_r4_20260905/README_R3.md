# CoPE vs FSR-PC r3: persistent-lineage task completion

This is the new experiment package. It is a portable copy of the audited r2
final-v8 source plus an independent r3 benchmark under
`code/cope/lineage_benchmark/`. Existing r2 evidence is retained only for
provenance and is never overwritten by r3 runs.

## What changed and why

The r2 CoPE and FSR-PC policies produced different internal states, but the goal
compiler flattened both states into the same object-target requirements. They
then used the same monolithic pick/place and repair code, so identical task
completion was the expected result.

r3 makes lifecycle and lineage load-bearing. A critical work order is suspended,
restored, overridden through several nested temporary versions, suspended and
restored again, and finally returned to its root ancestor. The deepest detour and
the root both begin with `butter -> basket_B`, but they bind different milk and
yogurt continuation actions. A system that canonicalizes the goal to the surface
object-target pair executes the wrong continuation and fails the task.

Each episode also contains persistent records from a long multi-order shift.
Both methods receive the same complete input packet and the same fixed LLM:

- **CoPE** emits one minimal typed patch. The state store owns identity, graph
  edges, lifecycle history, and root traversal.
- **FSR-PC** emits the complete replacement state. It may preserve stable IDs,
  history, and lineage, making it a stronger baseline than the r2 default. It
  must nevertheless re-emit every slot because full-state regeneration is the
  treatment being tested.

The fixed model is `Qwen/Qwen3-32B`, served locally through vLLM. Every paired
event uses temperature 0, the same seed, one call, 4096 maximum output tokens,
and a 90-second timeout. Method order alternates by seed.

## Endpoints

The **primary endpoint is end-to-end task completion** in the registered
`long_lineage` profile. Timeout, output truncation, JSON parse failure, schema or
lifecycle validation failure, wrong ancestor selection, wrong continuation, and
physical execution failure all count as task failures.

The report also includes task completion conditional on both methods generating
valid states. That number is diagnostic only; it does not remove generation
failures from the primary endpoint.

Profiles are registered in `configs_r3/experiment.json`:

- `calibration`: small state; both formats should be feasible.
- `lineage_valid`: deep lineage with a state that can still fit the output
  budget, used to expose wrong-but-valid ancestor/continuation behavior.
- `long_lineage`: deep lineage plus 48 persistent slots; primary finite-budget
  long-task condition.

The claim boundary is resource-bounded: this experiment tests reliability under
the same finite model, time, and output budget. It does not claim that an
unlimited perfect regenerator is logically incapable of reconstructing state.

## Local verification

No LLM or LIBERO installation is needed for the code gates:

```bash
./run_r3_tests.sh
python3 scripts/run_r3_lineage.py \
  --stage main --client budgeted_oracle --backend symbolic_basket \
  --seeds 1 --out /tmp/cope_r3_smoke
python3 scripts/validate_r3_results.py /tmp/cope_r3_smoke --expected 6
```

The budgeted oracle is only a plumbing test. It must never be reported as model
evidence.

For the GPU/server run, start with `GPU_RUNBOOK_R3.md`.


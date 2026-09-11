# Next command for formal readiness

The next execution is the 32-trajectory pilot, not a formal run. It is valid only after the missing production `RuntimeAssembly` and the calibration-only interrupted budget have been reviewed and bound.

```bash
: "${COPE_RUNTIME_FACTORY:?bind the reviewed production RuntimeAssembly module:factory}"
: "${COPE_REASONER_FACTORY:?bind the production reasoner factory}"
: "${COPE_REASONER_MODEL:?bind Qwen/Qwen3-32B at the audited revision}"
: "${COPE_REASONER_ENDPOINT:?bind the audited vLLM endpoint}"
: "${COPE_VLA_FACTORY:?bind cope_benchmark.repeated_v2.vla_adapter:create_native_openvla}"
: "${COPE_VLA_CHECKPOINT:?bind the audited local OpenVLA checkpoint path}"
env -u COPE_ALLOW_FORMAL_RUN python experiments/repeated_interruptions_v2.py \
  --phase pilot \
  --protocol end_to_end \
  --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_1_pilot.yaml \
  --task-catalog task_catalogs/repeated_v2_1/catalog.json \
  --output-dir outputs/repeated_interruptions_v2_1/pilot_end_to_end_01
```

Current execution of this command is blocked by `BLOCKED_PRODUCTION_RUNTIME_ASSEMBLY_UNAVAILABLE`, with the public evidence builder, public verifier, and nominal planner named separately in `FORMAL_READINESS_GATES.csv`. No placeholder factory is an acceptable substitute.

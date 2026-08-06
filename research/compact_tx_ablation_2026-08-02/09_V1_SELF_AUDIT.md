# Assigned v1 fault-layer self-audit

Date: 2026-08-02 (Asia/Shanghai)

Assigned v1 passed 12/12 clean semantic equivalence, 8/8 fail-closed faults,
12/12 deterministic proposal replay, and both frozen byte gates were computed.
The raw directory remains unchanged.

Post-result source inspection found that fault C03 (`forbidden_root_path`) was
rejected by the generic materializer rather than the parser, although
`02_FAULT_MANIFEST.csv` froze its layer as `parser`. The v1 CSV copied the
manifest layer into the output but did not record the actual rejection stage.
Thus v1 proves fail-closed behavior but not the full frozen layer taxonomy.

Corrective action frozen before v2:

1. make the parser validate the frozen path-form allowlist without consulting
   event semantics;
2. add `rejection_stage` to the receipt;
3. record both manifest and actual stage in the fault CSV;
4. require all eight actual stages to match the frozen manifest for `pass`;
5. keep all cases, proposal encoding, byte gates, timing protocol, and other
   decision rules unchanged;
6. rerun into a new directory without overwriting v1.

No GPU, LLM, robot, simulator, checkpoint, or reserved state was used.

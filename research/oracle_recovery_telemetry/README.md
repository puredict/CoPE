# Oracle recovery telemetry evidence index

Authoritative results:

- `REPORT_v2_corrected.md`: leakage-aware exact-return versus local-stage
  result and decision.
- `all_episodes_v2_corrected.csv`: normalized ten-row paired dataset.
- `raw_v3_corrected_spatial_order/`: authoritative raw paired episodes.
- `FORCE_PROXY_DIAGNOSTIC.md`: measurement-bug audit and failed slowdown
  mitigation.
- `soft_diagnostic_v6_corrected/`: raw slowdown diagnostic.
- `SHA256SUMS_v5_tracked_final.txt`: integrity manifest for committed artifacts.
- `pytest_full_2026-07-31_2339.txt`: full repository test result.

Do not cite force or impulse values from `raw_v1`, `raw_v2`,
`diagnostic_v3`, `soft_diagnostic_v4`, or `contact_diagnostic_v5`. Those runs
used the wrong half of MuJoCo's `rotation:translation` spatial vector as
force. They are retained as failed/invalidated evidence rather than deleted.
Their action/state hashes, task predicates, steps, contact pairs, and object
displacements are unaffected by that specific slicing error.

State 0 is development data. States 1–4 were held out while choosing the
75%-toward-origin staging rule, but the corrected telemetry is a confirmatory
replay of those already-observed layouts, not a fresh unseen test.

# End-to-end pilot report

Status: `BLOCKED_PRODUCTION_RUNTIME_ASSEMBLY_UNAVAILABLE`.

The zero-call pilot preflight passed with source-backed tasks 1 and 4. The deterministic qualification design contains four continuous master sessions: two tasks, initial-state IDs 10 and 11, one frozen policy seed, and eight primary non-oracle methods. Each session exposes the first four events of its frozen schedule. Expected trajectories: 32.

Execution did not start because there is no production `RuntimeAssembly` binding for the shared public event-evidence builder, public verifier, and nominal physical planner. The production reasoner and learned OpenVLA adapter are independently qualified, but substituting fixtures, simulator truth, an oracle controller, or the archived privileged ReKep environment would invalidate the pilot.

| Integrity quantity | Count |
| --- | ---: |
| Expected trajectory cells | 32 |
| Completed trajectory cells | 0 |
| Missing trajectory cells | 32 |
| Duplicate cells | 0 |
| Unexpected cells | 0 |
| Pilot provider calls | 0 |
| Pilot VLA calls | 0 |
| Formal provider calls | 0 |
| Formal trajectories | 0 |

`PILOT_CELL_INTEGRITY.csv` enumerates every missing expected cell. `PILOT_LATENCY_BREAKDOWN.csv` records zero samples for every full-stack stage. No event-result, episode-result, planning-problem, action-trace, or leakage-pass artifact is emitted because no production trajectory ran.

The fixed-template editor remains a separate zero-provider software diagnostic: five registered lookup cases passed and the leave-one-realization-out case failed closed as designed. It is not pilot evidence.

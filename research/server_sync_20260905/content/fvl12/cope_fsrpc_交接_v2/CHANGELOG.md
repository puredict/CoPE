# Changelog

## 2026-08-04 — LIBERO/MuJoCo backend qualification

The handoff now includes an explicit backend-neutral simulator interface,
preserves Synthetic2D, and adds a real LIBERO/robosuite/MuJoCo backend for the
audited server. Candidate verification executes real checkpoint-isolated
MuJoCo controls; I2/I4 availability and motion are physical simulator edits;
task success comes from object/contain-region geometry, cancellation, stale
target, stability, and unsafe-contact checks.

New run tooling provides a fail-fast preflight, explicit single-episode debug,
a separate 10-seed gate, and a gate-report-protected fixed 60-episode pilot.
Every real episode writes JSON, three JSONL traces, state snapshots, a simulator
log, and MP4 video below `method/condition/seed_<seed>/`.

The CoPE/FSR-PC policies, persistent constraint semantics, patch operators,
continuation, synthesis, TaskProgram splice, and restore/resume semantics were
not redesigned. `SharedRepairEngine` changed only by accepting an optional
backend rollout-verifier factory; the original verifier remains the default.

See `CHANGELOG_REAL_BACKEND.md` for the file-level list and
`CHANGELOG_FROM_COPE_V1.md` / `CHANGELOG_FROM_REKEP_V2.md` for earlier history.

## Claim boundary

The real substrate is OnTheGroundPanda with OSC_POSE and a privileged geometry
oracle, rendered on CPU with OSMesa. This is not a learned-policy, GPU-inference,
physical-robot, force-control, or calibrated-safety result.

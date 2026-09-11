# Public runtime binding

Status: `BLOCKED_PRODUCTION_BACKEND_BINDING`.

The common runner, event-boundary snapshot logic, fresh-observation checks, method-owned continuous state, common executor, action traces, sealed dynamic evaluator, at-most-once journal, crash-safe resume, and integrity checks are implemented and pass their mocked integration tests. The continuation wrapper `continuation_carrying_repair_v2` is representation-neutral and refuses canonical truth or repairs to missing baseline commitments.

No concrete production factory currently satisfies the full `RuntimeAssembly` contract. Repository and server searches found only test assemblies. The missing production ports are:

- a `RuntimeEnvironment` that supplies RGB/proprio public observations, exact snapshot/restore, registered event injection, public context, and separately sealed scoring;
- a shared public event-evidence builder that converts successive sensor observations into confidence-, evidence-, and timestamp-bound event evidence;
- a public recovery verifier with `uses_hidden_truth=False`;
- a nominal physical planner that consumes each method's accepted `PlanningProblem` and emits occurrence-bound language instructions usable by the native VLA.

Two adjacent codebases were examined. Archived ReKep has a continuation/search implementation, but its environment reads simulator segmentation, object meshes, SDF geometry, registered object identities, and simulator checkpoints; it is privileged for this claim. A separate HEART/LIBERO workspace contains an operational SAM3 checkpoint and an RGB/depth segmentation RPC, but no adapter to the current v2.1 evidence schema, no cross-event identity/evidence builder, no relation/lifecycle verifier, no required snapshot/injection/sealed-evaluator separation, and no `RuntimeAssembly`. Turning those pieces into the missing substrate would be new runtime architecture, outside this readiness-only task.

The loaded OpenVLA action checkpoint was also probed with three visual questions. It returned action-token strings rather than object or relation answers, so it cannot be relabeled as the public verifier. The negative capability receipt is in `openvla_public_vision_probe_01/RESULT.json`.

Remaining statuses:

- `BLOCKED_PRODUCTION_PUBLIC_EVENT_EVIDENCE_BUILDER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_PUBLIC_VERIFIER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_NOMINAL_PLANNER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_RUNTIME_ASSEMBLY_UNAVAILABLE`

The production pilot therefore remains unstarted. No fixture, geometry oracle, simulator predicate view, controlled Boolean executor, or scripted output was substituted.

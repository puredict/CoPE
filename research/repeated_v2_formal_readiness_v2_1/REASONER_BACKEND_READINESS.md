# Production reasoner and runtime binding

The production reasoner transport is operational. The exact v2.1 adapter sent one non-formal qualification request to the local Qwen3-32B vLLM service and received a strict JSON object with provider token counts. The request disabled Qwen thinking and required the OpenAI-compatible `json_object` response format. The receipt records 34 input tokens, 10 output tokens, one qualification call, zero pilot calls, and zero formal calls.

The model is `Qwen/Qwen3-32B`, snapshot revision `9216db5781bf21249d130ec9da846c4624c16137`. Its 27-file, 65,540,298,478-byte content-address manifest is `7323af5c2c972ef1728841512904e98e81212266528f45226e7f80657ff0b4cb`. The adapter source SHA-256 is `70024242733cc80fb6d3d0044b83ef4f794b68b94ad8b7722fee336479820357`. Evidence is retained in `production_reasoner_probe_01/`.

The representation-neutral continuation wrapper remains `continuation_carrying_repair_v2`, source SHA-256 `4f11183dd30c87c2f38da4fb8e6f383038dfd799f717f6d0478ceaf564b05187`. It may compile an accepted ledger to `RepairGoal`, search and verify a recovery, then splice and resume. Its constructor and runtime gates require a public `repair_observation`, a verifier that declares `uses_hidden_truth=False`, and a nominal backend. It never reads the sealed canonical ledger and cannot fill omitted baseline commitments.

The searched repository, archived worktrees, fvl10/fvl11/fvl12 workspace roots, and installed OpenVLA source contain no concrete production `RuntimeEnvironment`/`RuntimeAssembly`, public event-evidence producer, eligible public verifier, or native-compatible nominal physical planner. The only concrete runtime assemblies and public verifiers are test fixtures. Older LIBERO predicate and rollout-verifier paths read simulator geometry or checkpoint/step simulator state, so they are privileged and are excluded.

OpenVLA itself cannot fill the verifier gap. A real RGB probe asked three object/relationship questions through the loaded action-prediction checkpoint; the returned tokens decoded as action-token strings rather than semantic answers. The retained `openvla_public_vision_probe_01/RESULT.json` therefore supports only the negative capability finding, not a public perception claim.

The remaining binding statuses are:

- `BLOCKED_PRODUCTION_PUBLIC_EVENT_EVIDENCE_BUILDER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_PUBLIC_VERIFIER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_NOMINAL_PLANNER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_RUNTIME_ASSEMBLY_UNAVAILABLE`
- aggregate `BLOCKED_PRODUCTION_BACKEND_BINDING`

Creating a new perception/planning architecture or substituting `LiberoStateView`, a geometry oracle, the controlled Boolean mechanism, or fixture outputs would violate the requested production boundary. These blockers prevent an end-to-end pilot from issuing provider or VLA calls.

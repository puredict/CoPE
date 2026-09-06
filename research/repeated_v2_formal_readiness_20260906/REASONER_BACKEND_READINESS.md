**Production reasoner and continuation/runtime binding audit — 2026-09-06 17:16 UTC**

The inspected workspace does not contain a configured production implementation that can be bound directly to the current v2 `ReasonerGateway` and `RuntimeAssembly` using configuration alone. The older OpenAI-compatible transport and the continuation repair package exist, but their presence does not supply the missing v2 interfaces, public observation producer, nominal planner, or public recovery verifier. The separately passed real VLA action gate supports continuing the clean-policy calibration; it does not qualify these high-level runtime components.

This was a read-only source/configuration audit. Provider requests, HTTP health/model requests, model loading, GPU operations, simulator episodes, and runtime construction were all zero. The only new artifact is this report. No credential values were printed or saved.

The local scope was `/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree`, its existing provider/experiment/configuration code, the known continuation archive, the known `cope_fsrpc_交接_v2_r2/code` archive, and the presence of relevant variable names in the local shell startup files. The remote scope was `/home/lijingsu/vla`, `/home/lijingsu/codex-worktrees/cope-repeated-v2-phase4`, their code/config directories, the relevant remote startup-file variable names, and provider-named entries in `/home/lijingsu/.config`. The remote connection used the existing `fudan-26575` SSH alias. No credentials or configurations were inferred from unrelated processes or projects.

| Component | Existing evidence | Direct current-v2 binding |
|---|---|---|
| `ReasonerGateway` | Exact-message boundary, preflight token counting, `ReasonerResponse`, one event call, fixed generation settings | Only `FixtureReasoner` implements the complete interface in the searched current code; no production counterpart found |
| Older provider transport | `OpenAICompatibleRecoveryProvider`; single request with zero retries; OpenRouter endpoint and model references | API mismatch: accepts `RecoveryInput` and an older output contract, builds different messages, returns `ProviderInvocation`, and has no `count_tokens(messages)`/`complete(messages, config)` methods |
| Continuation repair engine | Existing 63-file `rekep_repair` package, equal byte identity locally/remotely | Package available; production public observation, nominal planning and verifier bindings absent |
| `ContinuationPlannerBackend` | Representation-neutral wrapper with explicit truth exclusion and narrow semantic gates | Constructor requires a supplied nominal backend and public verifier; assigning its class to an environment variable does not provide them |
| Nominal planner | `ControlledMechanismBackend` implements an accepted-state Boolean planning substrate | Software mechanism only; its nominal instruction mapping is not a directly usable native OpenVLA language instruction |
| Public history retrieval | Existing deterministic `PublicHistoryIndex` and adapter-owned state | Useful implementation exists; frozen configuration wiring still needs qualification, including the missing exposed `top_k` control |
| Runtime environment / assembly | `RuntimeEnvironment` protocol, `RuntimeAssembly` dataclass, factories and durable runner | No production assembly construction or concrete current-v2 environment implementation found in searched source; only test assemblies |
| Archived simulator recovery | Real simulator backend plus checkpoint rollout verifier | Ineligible as the requested public verifier/executor: owns simulator state, reads geometry, and uses the documented privileged oracle controller |

The exact gateway interface is [provider.py:72](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/provider.py:72): `count_tokens(messages)` and keyword-only `complete(messages, config) -> ReasonerResponse`. The gateway preserves exact messages and validates the returned type and budgets at [provider.py:134](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/provider.py:134). Its only included provider implementation is explicitly a fixture at [provider.py:169](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/provider.py:169).

The older transport is defined at [openai_compatible.py:32](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope/providers/openai_compatible.py:32); it constructs its own `RecoveryInput` messages at line 67 and exposes `call_contract` at line 214. Merely changing a factory variable would not preserve v2's exact message envelope or supply its response/token interface. Its default endpoint is `https://openrouter.ai/api/v1/chat/completions` (HTTPS port 443), and its credential variable name is `OPENROUTER_API_KEY`. Existing older experiment identities include `qwen/qwen3.5-flash-02-23`, temperature 0, 12,000 input / 4,096 output tokens and 90-second timeout at [sequential_prompting.py:11](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope/sequential_prompting.py:11). Those are historical source defaults, not proof of a currently accessible account/model or a frozen v2 choice. Current v2 specifies different budgets and timeout at [repeated_interruptions_v2_pilot.yaml:61](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/configs/repeated_interruptions_v2_pilot.yaml:61): 32,768 or 4,096 input tokens, 8,192 output tokens, temperature 0, top-p 1, 180 seconds, zero semantic retries and one call per event.

| Configuration identity / credential-variable name | Local current process | Remote inspected SSH process |
|---|---|---|
| `COPE_REASONER_FACTORY` | Absent | Absent |
| `COPE_REASONER_MODEL` | Absent | Absent |
| `COPE_REASONER_ENDPOINT` | Absent | Absent |
| `COPE_REASONER_API_KEY` | Absent; value not inspected | Absent; value not inspected |
| `COPE_RUNTIME_FACTORY` | Absent | Absent |
| `COPE_PLANNER_FACTORY` | Absent | Absent |
| `COPE_CONTINUATION_BACKEND_FACTORY` | Absent | Absent |
| `COPE_RETRIEVER_FACTORY` | Absent | Absent |
| `OPENAI_API_KEY` | Absent; value not inspected | Absent; value not inspected |
| `OPENROUTER_API_KEY` | Absent; value not inspected | Absent; value not inspected |

These are bounded presence observations, not a claim that no credential exists anywhere on the accounts. The inspected repository roots contained no top-level `.env` file. The inspected local `.zshrc`/`.zprofile` and remote `.bashrc`/`.profile` did not declare matching provider variables. Remote `.secrets` was absent, and `.config` had no provider-named entries matching the scoped search. No private key files, account secrets, browser credentials, arbitrary process environments, or unrelated secret stores were read.

The read-only socket listing showed loopback listeners on ports 7890 and 8020, but supplied no provider process identity. No matching production reasoner endpoint binding was found. These ports therefore remain **unattributed listeners**, not evidence of a compatible model service; no request was sent to either. Other listening ports were not interpreted as provider services.

The continuation wrapper checks nominal backend `uses_hidden_truth=False` and a named public verifier with the same truth exclusion at [continuation_backend.py:213](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/continuation_backend.py:213). Its public observation must provide one evidence-backed `repair_observation` containing an explicit 2-D pose, the exact archived Boolean vocabulary, timestamps and evidence IDs at [continuation_backend.py:239](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/continuation_backend.py:239). No production sensory producer for that belief was found; current occurrences were the wrapper and test fixtures. It sends the full accepted problem to the nominal backend and reads only explicit accepted repair requirements at [continuation_backend.py:292](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/continuation_backend.py:292). It must not fill missing commitments or repair observations from canonical task truth.

The archived engine exists at both:

- `/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/research/server_sync_20260905/content/fvl12/v/cope_r4_20260905/code/rekep_repair`
- `/home/lijingsu/codex-worktrees/cope-repeated-v2-phase4/research/server_sync_20260905/content/fvl12/v/cope_r4_20260905/code/rekep_repair`

Both contain 63 Python files and have package digest `447e1257ae8d62a78b6f995e398722589b2efe4794a11a1d679e534c99601488`, using the wrapper's sorted relative-path + NUL + exact source-bytes algorithm. This is the archived **package** digest. The separate current **wrapper file** digest is `4f11183dd30c87c2f38da4fb8e6f383038dfd799f717f6d0478ceaf564b05187`.

The older simulator backend explicitly declares its controller as privileged geometry and `learned_policy_used=False` at [libero_mujoco.py:127](/Users/lijingsu/Documents/cope/cope_fsrpc_交接_v2_r2/code/cope/backends/libero_mujoco.py:127); its observation method reads controller object/target positions at line 353. The oracle's source explains that limitation at [libero_oracle.py:1](/Users/lijingsu/Documents/cope/cope_fsrpc_交接_v2_r2/code/cope/backends/libero_oracle.py:1). Its candidate verifier checkpoints, reads and steps the simulator, then restores it at [rollout_verifier.py:54](/Users/lijingsu/Documents/cope/cope_fsrpc_交接_v2_r2/code/cope/backends/rollout_verifier.py:54). These cannot be relabeled as a public forward-model verifier.

The older learned-rollout integration also offers an optional live LIBERO predicate snapshot at [libero_backend.py:363](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope/libero_backend.py:363). The producer reads exact simulator predicates through `LiberoStateView` at [libero_predicate_validator.py:86](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope/libero_predicate_validator.py:86). This optional older path is not a sensory-only producer for the new public repair belief and must not be used to fill it from truth.

Two further binding details matter before a production assembly can be qualified:

- The native policy requires a nonempty `instruction`, `language` or `prompt` string at [vla_adapter.py:314](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/vla_adapter.py:314). The controlled nominal planner creates a symbolic instruction mapping without those language keys at [planner_backend.py:195](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/planner_backend.py:195). `CommonExecutor` passes that mapping to `begin_subgoal` at [runner.py:238](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/runner.py:238). Directly assigning this mechanism planner as the native VLA nominal planner does not complete the binding. The continuation wrapper's recovery prefix does have explicit language, but the nominal suffix still needs a valid accepted-state compiler.
- The built-in public retriever defaults to a 2,048-byte conservative budget, while the method adapter defaults to recent window 8; the frozen YAML requests budget 4,096, recent window 4 and top-k 12. Budget/window can be explicitly configured through existing constructors. `FrozenRetrieverConfig` has no top-k field, and `PublicHistoryIndex.retrieve` adds all fitting ranked chunks without a top-k limit: [history.py:24](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/history.py:24), [history.py:58](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/history.py:58), [methods.py:57](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/adapters/methods.py:57). No production factory wiring this exact protocol was found. The available public index is useful software evidence, not proof that every frozen retrieval setting is already enforced.

`RuntimeAssembly` requires independent method/environment/planner factories, public episode inputs, credential-free identities and (for formal use) live identity verification at [pilot.py:35](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/pilot.py:35). The concrete environment contract includes fresh observations, durable state restore, event injection, public context and separately sealed evaluation methods at [runner.py:93](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/runner.py:93). The searched current source contained this protocol and test mocks, but no production implementation/assembly construction satisfying it.

| Blocker | Classification and concrete reason |
|---|---|
| `BLOCKED_RUNTIME_ENVIRONMENT_UNAVAILABLE` | Existing CLI dependency status: `COPE_RUNTIME_FACTORY` absent; no production v2 assembly implementation found |
| `BLOCKED_REASONER_ADAPTER_UNAVAILABLE` | Existing CLI dependency status: `COPE_REASONER_FACTORY` absent; older transport has the wrong gateway interface |
| `BLOCKED_REASONER_MODEL_UNAVAILABLE` | Existing CLI dependency status: `COPE_REASONER_MODEL` absent; historical Qwen identifier is not a current v2 frozen selection |
| `BLOCKED_PRODUCTION_BACKEND_BINDING` | Audit grouping: engine/wrapper bytes exist, but no public observation producer, eligible public verifier or native-compatible nominal planner binding was found |
| Retrieval protocol qualification incomplete | Audit finding, not a claimed emitted runtime status: current constructors/defaults do not establish all frozen retrieval settings |

The first three statuses are defined by the current read-only `dependency_report` at [pilot.py:120](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/pilot.py:120). Endpoint/credential presence is additional evidence; the dependency checker does not itself authenticate a provider or validate every factory implementation. Setting environment variables alone must not be reported as an operational reasoner or runtime qualification.

Remote source receipts from this audit:

| File relative to remote phase-4 root | SHA256 |
|---|---|
| `cope_benchmark/repeated_v2/provider.py` | `2185003f7b900edd38326272d9ba2a9f080d47d2114d93a4b7330f95e7238eb7` |
| `cope_benchmark/repeated_v2/pilot.py` | `ae9c3c467ae2a2de114c90e5f4d876fdad803eb6e13126a47db5840d89fda2cd` |
| `cope_benchmark/repeated_v2/continuation_backend.py` | `4f11183dd30c87c2f38da4fb8e6f383038dfd799f717f6d0478ceaf564b05187` |
| `cope/providers/openai_compatible.py` | `2d3f0d4ee986e20ea9bef0fb1ebbe2044258617e6d705eb79cb8dbe03a3b3a32` |

No provider availability, credentials, account entitlement, endpoint model listing, or production semantic behavior was tested in this audit. No oracle substitution or privileged observation compilation was performed.

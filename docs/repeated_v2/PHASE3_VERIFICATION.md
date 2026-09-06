# Window 3 verification

Window 3 implements the continuous runtime, production OpenVLA client wrapper,
representation-neutral continuation backend, sealed evaluator, durable journal,
verified resume, integrity checks, and pilot/formal entry point.

- Branch: `codex/repeated-v2-phase3`.
- Phase-2 parent: `41d15bd2ef8b4bb04194b524f9180d2b17b4fc3b`.
- Phase-1 ancestor: `b8462c28424d6551ab1713e67d68f42ca149b55f`.
- Resolve this report's containing commit to obtain the Window 3 SHA.
- Frozen v1 implementation and results are unchanged.

## Qualification evidence

The initial integrated local v2 regression passed **473 tests and 58 subtests**,
with one opt-in simulator test skipped. The opt-in real LIBERO CPU smoke then
passed separately. Final regression results and exact source correspondence are
recorded in `research/repeated_v2_phase3_validation/README.md`.

The integration tests exercise actual phase-2 adapters, compilers, schemas and
gateways with deterministic fixture providers. They cover continuous accepted
state across eight events, retained omissions and wrong occurrences, atomic
rejections, one high-level call per event, action chunks, occurrence-bound action
traces, canonical goal cancellation/reissue, latched constraints, progress
regression, ambiguous calls, process death, exclusive ownership, corrupted or
missing snapshots, protocol drift, and byte-identical completed resume.

The continuation tests load the actual archived `rekep_repair` implementation,
including `RepairGoal`, search, verification, continuation capture, program
splicing and gated resume. They use explicit public observations and accepted
repair requirements; no canonical truth or omitted commitments enter planning.

The real simulator test uses installed LIBERO/MuJoCo assets on the local CPU.
It verifies reset, one physics action, exact simulator-state restore, and a fresh
observation without an extra policy step. It is camera-free and does not establish
physical repeated-interruption feasibility or learned-policy performance.

## Pilot attempts and remaining production dependencies

Both production pilot entry points were attempted again after merging the final
phase-2 SHA. Both stopped before any factory or external call:

| Protocol | Primary status | Result rows | External reasoner / VLA calls |
| --- | --- | --- | --- |
| controlled | `BLOCKED_TASK_CATALOG_GAPS` | 0 | 0 / 0 |
| end_to_end | `BLOCKED_TASK_CATALOG_GAPS` | 0 | 0 / 0 |

The authentic task catalog contains **0 eligible tasks and 794 gaps**. The
production simulator assembly, public detector/recovery verifier, canonical
evaluation projections, and reasoner factory/model remain deployment
dependencies. These capabilities have complete explicit interfaces and fail
closed when unavailable.

The VLA attempt additionally reports `BLOCKED_VLA_ADAPTER_UNAVAILABLE` and
`BLOCKED_VLA_CHECKPOINT_UNAVAILABLE` for the local configuration. Production
OpenVLA source was found and wrapped without its simulator-owning rollout.
Checkpoint files and source exist on the server, but their bytes have not been
formally qualified and all eight GPUs were allocated during the mandatory
`nvidia-smi` probe. No remote GPU, model inference, oracle substitution, checkpoint
download, or training was used.

Formal admission additionally depends on the separately owned Window 4 freeze
validator and authentic calibration/freeze evidence. Development and formal
experiments were not launched. Mock qualification and the physics smoke support
software mechanics only; accuracy, robot success, latency comparisons,
non-inferiority and the scientific claim remain unevaluated.

## Reproduction and audit

Local interpreter:
`/Users/lijingsu/miniforge3/envs/lerobot312/bin/python`.

Server interpreter: `/home/lijingsu/vla/.venv/bin/python`, through the existing
`fudan-26575` SSH alias. The CPU regression uses the isolated detached worktree
`/home/lijingsu/codex-worktrees/cope-repeated-v2-phase3-20260906` with source hashes
checked against the candidate; no other user's process or working tree is used.

```sh
python -m pytest -q tests/repeated_v2
COPE_RUN_LIBERO_SMOKE=1 python -m pytest -q tests/repeated_v2/test_phase3_simulator_smoke.py
CUDA_VISIBLE_DEVICES="" python -m pytest -q
```

- [Runtime and durability contract](PHASE3_RUNTIME.md)
- [Production client and continuation source audit](PHASE3_ADAPTER_AUDIT.md)
- [CLI, factories and pilot gates](PHASE3_PILOT.md)
- [Real simulator smoke scope](PHASE3_SIMULATOR_SMOKE.md)
- [Verification transcripts and source hashes](../../research/repeated_v2_phase3_validation/README.md)

# Phase 3 pilot, development and formal entry point

`experiments/repeated_interruptions_v2.py` executes the continuous `EpisodeRunner`
through a production `RuntimeAssembly`. It does not supply an oracle executor or
invent task semantics when a dependency is missing.

## Current pilot attempts

Both local production entry points were attempted on 2026-09-06. Both stopped
before importing or invoking a runtime factory. There were **zero reasoner
calls, zero VLA calls, and zero generated event/episode result rows**.

| Protocol | Primary status | Other blocking dependencies |
| --- | --- | --- |
| controlled | `BLOCKED_TASK_CATALOG_GAPS` | Runtime environment factory, production reasoner factory, reasoner model |
| end_to_end | `BLOCKED_TASK_CATALOG_GAPS` | Same dependencies, VLA factory configuration, locally installed VLA checkpoint |

The authentic catalog reported **0 eligible tasks and 794 catalog gaps**. No
task was admitted using synthetic feasibility or calibration evidence. A native
OpenVLA wrapper exists in `vla_adapter.py`; the missing local runtime/factory and
checkpoint prevent this pilot from qualifying the installed production client.

Immutable attempt reports:

- `phase3_pilot_attempts/controlled/13_INFRASTRUCTURE_STOP.json`, SHA-256
  `3f7c25d36d71a4c8efb8425f3c62be407c74a9f57db6c2613a330ef0d45dc052`.
- `phase3_pilot_attempts/end_to_end/13_INFRASTRUCTURE_STOP.json`, SHA-256
  `2bd4a1f22e4472c6a6589114e5aaccef4ff7e9483597b0674764cbbd1dc7cb4b`.

These attempts used the phase-1 files already merged into the phase-3 worktree,
with the pending phase-2 package made importable from its existing worktree.
They are blocked qualification attempts, not performance measurements. No GPU
was used and no checkpoint was downloaded. Development was not launched.

Both entry points were attempted again after merging the final phase-2 commit
`41d15bd2ef8b4bb04194b524f9180d2b17b4fc3b`, using the integrated package directly.
The outcomes remained blocked, with zero factory/provider/VLA calls and zero
result rows. These additional immutable reports are in
`research/repeated_v2_phase3_validation/`:

- `pilot_controlled/13_INFRASTRUCTURE_STOP.json`, SHA-256
  `57c4c72a2e910ae6983916698317e870bc02e09db467c24fc6beb4a0b53edb2e`.
- `pilot_end_to_end/13_INFRASTRUCTURE_STOP.json`, SHA-256
  `e7f69e88c0aabbceff157e966e4740fdaed54a7f60f14a1ea16f561fd162b7d7`.

## CLI

```sh
python experiments/repeated_interruptions_v2.py \
  --phase pilot --protocol controlled \
  --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_pilot.yaml \
  --output-dir outputs/repeated_v2_pilot_controlled_evidence

python experiments/repeated_interruptions_v2.py \
  --phase pilot --protocol end_to_end \
  --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_pilot.yaml \
  --output-dir outputs/repeated_v2_pilot_vla_evidence

python experiments/repeated_interruptions_v2.py \
  --phase development --protocol end_to_end \
  --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_pilot.yaml \
  --output-dir outputs/repeated_v2_development_vla_evidence

python experiments/repeated_interruptions_v2.py \
  --phase formal --protocol end_to_end \
  --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --task-catalog task_catalogs/repeated_v2.json \
  --manifest manifests/repeated_interruptions_v2.jsonl \
  --frozen-bundle frozen/repeated_interruptions_v2/freeze_bundle.json \
  --shard-index 0 --num-shards 8 \
  --output-dir outputs/repeated_v2_formal_vla_evidence_shard0
```

`--freeze` aliases `--frozen-bundle`. `--resume` enables verified resume only.
Use a separate output directory for each protocol, information condition and
formal shard. The formal manifest argument is the **complete phase-1 manifest**;
the CLI selects the exact ordered full-master subset bound by the bundle. An
already partial manifest fails the complete-manifest gate. Only eight formal
shards are supported. Factories never receive a requested checkpoint K because
each method runs one continuous trajectory with all checkpoint boundaries.

A hash partition may legitimately assign zero masters to a formal shard. The
CLI still validates the complete authentic catalog/manifest and all eight
frozen partition digests. It then uses phase 4's public
`validate_static_frozen_bundle` to recheck the exact repository revision and
bound evidence without constructing a runtime or model. A valid empty shard
publishes an empty journal, zero-row exports, an empty `10_ACTION_TRACES/`
directory and `COMPLETE` with explicit zero call/trajectory counts. Its metadata
states `live_identity_check=not_required_no_external_calls`; it does not claim a
live model identity check. Empty pilot/development manifests and omission of
masters owned by a nonempty formal shard remain blocked. This zero-job path
supports the same byte-identical verified resume as other completed runs.

Pilot uses the first calibration state and policy seed from the frozen config
(state 0, seed 101) for each authentic eligible task. Development uses state 0,
seed 131 and distinct master IDs. Both are disjoint from formal policy seeds
11, 29 and 47. Development is a production, evidence-matched VLA run for the K=4
comparator selection. It has no fixture opt-in and cannot silently become a
formal run. Both qualification designs keep all nine methods in raw journals.

## Runtime assembly contract

Set `COPE_RUNTIME_FACTORY=module.path:factory`. `factory(config=...)` must return
`cope_benchmark.repeated_v2.pilot.RuntimeAssembly` and remain free of inference,
simulator steps and network requests while assembling lazy clients. Other
configured dependencies remain explicit: `COPE_REASONER_FACTORY`,
`COPE_REASONER_MODEL`, and, for VLA protocols, `COPE_VLA_FACTORY` plus an existing
local `COPE_VLA_CHECKPOINT`. A provider can also use the endpoint/key environment
names in the frozen config; credentials must not enter identity records.
`COPE_TASK_CATALOG` overrides the default catalog, and `COPE_FREEZE_BUNDLE` is
the fallback for the formal freeze path.

The dataclass supplies:

- `episode_inputs(manifest=..., task=...) -> EpisodeInputs`: the trusted harness
  constructs the public task, initial ledger and initial execution context from
  authenticated catalog semantics. The method factory receives none of these.
- `environment_factory()` and `planner_factory()`: new independent mutable
  clients with stable production identities. The planner declares
  `uses_hidden_truth=False` and consumes only accepted compiled semantics.
- `method_factory(method_name=..., information_condition=...)`: a new adapter
  and gateway. All actual generative gateway configurations are compared before
  the first environment reset or provider call. Shared gateway/adapter objects
  are rejected, as are changing environment, planner or policy identities.
- `policy_factory()`: a new observation-only learned VLA client per trajectory.
  It is required for `end_to_end` and never replaced with oracle execution.
- `identity`: the credential-free component mapping used by phase 4; actual
  reasoner provider/model must agree. `current_identity()` supplies the live
  mapping for formal freeze validation. An optional `frozen_bundle` must equal
  the CLI bundle. Formal validation runs before component creation and at each
  guarded runtime call. Client factories that use GPUs must enforce the idle-GPU
  checks in `vla_adapter.py` before loading any model.

The Python-only `execute_assembly(..., qualification=True)` requires
`RuntimeAssembly.fixture=True` and phase `pilot`. Its artifacts are marked
`mock_qualification`/`MOCK_QUALIFICATION_COMPLETE`. The production CLI does not
expose this option and rejects fixture assemblies.

## Durable artifacts and resume

Every protocol/condition directory owns one durable journal. The journal
records call intent before the only provider attempt, then the exact response,
event result, episode result and boundary snapshots. An intent without a
response remains ambiguous and cannot be retried. Frozen input identities,
component identities and episode inputs must match before a resume proceeds.

After every expected cell has a verified result or explicit unreached failure,
the CLI publishes `04_CALL_INTENTS.jsonl` through `09_PLANNING_PROBLEMS.jsonl`,
`10_ACTION_TRACES/*.jsonl.gz`, `INTEGRITY.json`, and `12_STATUS.json`. Exports
preserve all methods and every event, including K=0; they do not fill missing
cells. Snapshot exports retain initial, pre-event and completed boundaries.
Gzip output has a fixed timestamp. Atomic exclusive publication allows an
interrupted export to resume only when regenerated bytes are identical.

`PILOT_QUALIFICATION.jsonl` summarizes the eight non-oracle pilot arms while
retaining the oracle reference in the complete raw journal.
`DEVELOPMENT_RECORDS.jsonl` summarizes the six preregistered comparator arms at
K=4 and binds the raw journal directory hash. Missing or contradictory measured
history corruption stays null and blocks downstream selection; it is not
converted into zero. `13_INFRASTRUCTURE_STOP.json` records a blocked/incomplete
attempt without imputed result cells. A new input or changed dependency set
should use a new output directory; existing experiment artifacts are immutable.

## Validation

`tests/repeated_v2/test_phase3_pilot.py`: **18 tests passed** with the existing
`/Users/lijingsu/miniforge3/envs/lerobot312/bin/python` interpreter. Coverage
includes controlled/VLA mock qualification, independent method environments,
complete event exports, action traces, byte-identical completed resume, metadata
drift, shared mutable clients, reasoner parity before calls, fixture/formal
separation, production development gating, missing dependency zero-call behavior,
empty formal shard ownership and full-input gates, the public static freeze
validator path, and refusal to export or impute an incomplete journal. These tests are software
qualification only; they are not simulator, VLA or scientific performance data.

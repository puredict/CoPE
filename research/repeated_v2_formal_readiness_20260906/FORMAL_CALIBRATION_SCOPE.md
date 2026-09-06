**Four-task clean calibration scope and the remaining formal prerequisite**

The completed calibration cohort is tasks **0, 1, 4 and 8**, each with initial states **0–4** and policy seeds **101/131**: **40 measured physical episodes**. All40 immutable records passed the frozen offline audit. This note does not change the driver, auditor, raw records, protocol hashes, outcomes, selection thresholds, or formal task-count requirements.

The current ten-task catalog requires **100 clean calibration cells**, including the calibration cells of tasks that may ultimately fail eligibility. Selection still requires at least eight eligible tasks. A completed four-task cohort supplies 40 of those task/state/seed observations, but it does **not** by itself satisfy the current common-protocol prerequisite for a 100-cell formal calibration inventory.

| Scope | Required evidence | What this cohort can establish |
|---|---|---|
| Real VLA operational readiness | Actual rendered observations, admitted production policy, finite actions, correct conversion and source/checkpoint identity | The separate action probe and completed clean episodes provide evidence within their recorded scope |
| Four-task pilot calibration | Exact ten-cell grid per task, 260 policy-control horizon, ten separately recorded settling controls, immutable outcomes and traces | Per-task rates and current/ever/regression observations after the relevant complete grids pass audit |
| Current global calibration prerequisite | All ten catalog tasks × five states × two calibration seeds; common policy/checkpoint/protocol identity | Incomplete: the other six task grids are absent from this cohort, and its raw protocol identity is cohort-specific |
| Formal task admission and experiment freeze | At least eight eligible tasks plus authentic semantics, feasibility, runtime/pilot/development and freeze evidence | Not established by clean calibration alone |

`CalibrationEpisode` retains a `protocol_sha256`; `summarize_calibration` requires one policy, checkpoint, protocol and provenance kind within each complete task grid at [task_calibration.py:153](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/task_calibration.py:153). Catalog admission additionally requires every catalog task to share the same policy/checkpoint/protocol tuple at [task_catalog.py:337](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/task_catalog.py:337). The freeze derives its expected calibration grid from **all catalog tasks**, checks the exact cell set and trace provenance, and checks rates for the selected tasks at [freeze.py:704](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/cope_benchmark/repeated_v2/freeze.py:704). Therefore the current ten-task catalog implies 100 cells even when the admitted formal subset contains eight or nine tasks.

The calibration driver hashes the exact canonical bytes of its whole `PROTOCOL.txt` at [CALIBRATION_DRIVER.txt:353](/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/research/repeated_v2_formal_readiness_20260906/CALIBRATION_DRIVER.txt:353). That object includes:

- Scientific execution settings: policy/checkpoint identity, seed convention, policy and settling-control budgets, public input fields, preprocessing, action semantics through pinned source identities, and current exact-goal success/stop rules.
- The cohort itself: `task_ids=[0,1,4,8]`, all four `task_records`, task languages, progress definitions, BDDL artifacts and initial-state records.
- Run provenance: the copied action-gate artifact's output path, task artifact paths, source-file paths/hashes, and cache/runtime identity information.

Consequently, a later six-task run can execute the same intended scientific procedure yet receive a different whole-protocol hash merely because its cohort and artifact paths differ. Its 60 records cannot be concatenated with these 40 and advertised as satisfying the existing shared-protocol gate. Even another four-task run with a new output root can receive a different raw hash. The exact original hash remains authoritative for the bytes and provenance it currently identifies; no new common hash is assigned here.

The raw `policy_id` naming issue is separate. The existing auditor can derive a provider-ID admission alias from the immutable terminal's `policy_identity.provider_id`, while preserving the model ID, raw record, terminal linkage, checkpoint, protocol, outcome and a per-cell provenance map. That explicitly reviewed **single-field identifier alias** does not authorize rewriting `protocol_sha256`, converting this cohort into a ten-task cohort, or bypassing the common-protocol requirement.

Legitimate uses of the completed and audited measurements include:

- Reporting what the production OpenVLA policy actually did on these four tasks, with the exact original checkpoint, source, inputs, budgets, seed/state grid and terminal evidence.
- Computing each complete task's ten-cell clean success rate against the unchanged 0.40–0.95 interval, while keeping integrity status distinct from success-rate eligibility.
- Examining recorded current, ever-achieved and regression observations as task-specific sub-evidence. These observations do not certify task structure, event safety, semantic triggers or interruption recovery.
- Checking whether the two policy seeds yielded identical raw/environment action sequences for each initial state. All 40 actual episodes remain in the grid; no stochastic-independence assumption or denominator collapse follows from those comparisons.
- Diagnosing the remaining runtime, task-selection and feasibility work without importing unrelated historical outcomes.

Historical **220-step or 520-step** experiments cannot be relabeled as this **260-policy-step** calibration. Their recorded horizons, seed schemes and execution protocols remain their own. In particular, the older affine-2027 seed schedule is not the frozen 101/131 grid. Matching task IDs or initial-state files does not make those outcomes interchangeable. Previously measured initial-state byte hashes may still be reused as separately verified asset identities; this does not reuse, truncate, rename or rescore the historical success outcomes into new calibration cells.

A later common *method-protocol* identity might permit scientifically legitimate aggregation without rerunning every already measured episode, but it would require a concrete reviewed normalization contract. A projection from whole run manifests to a common method identifier is many-to-one; it is not lossless by itself. It becomes auditable only if all original manifests, hashes and per-record mappings remain available. Before using such a projection, the work would need to:

1. Define and version which fields describe the common scientific procedure and which are cohort/run provenance. Do this without choosing fields in response to observed success rates.
2. Verify effective equivalence of the production model/checkpoint, runtime and inference code, preprocessing, action conversion, initialization/seed convention, settling/control budgets, stopping/scoring semantics and other behavior-affecting settings. Equal endpoint/model labels alone are insufficient.
3. Preserve task-specific BDDL, initial-state and progress/scoring definitions in a separately frozen complete task-input manifest. Those scientific inputs cannot simply disappear when `task_records` is removed from a method-level projection.
4. Preserve every raw whole-protocol hash and record, and publish an explicit per-record lineage map to any derived admission record. Keep all outcomes, cells and seed labels unchanged, with no selective retries or dropped cases.
5. Demonstrate that the normalized complete inventory, identical catalog-embedded records, raw terminal/trace provenance and versioned method/task manifests satisfy the existing freeze checks and their intended scientific meaning. A matching string alone is not evidence of equivalence.

That review has **not** been completed here: no later-cohort execution/equivalence evidence is available in this reviewed cohort, and the current schema uses one hash for the whole run protocol rather than distinguishing common method identity from cohort provenance. The present `policy_id` alias map cannot carry an unreviewed protocol transformation. The conservative alternative is a new full100-cell calibration whose common all-task protocol and artifact inventory are frozen before its episodes execute. This note neither launches that run nor selects a normalization approach.

The cohort audit completed with status `PASS`; its report SHA256 is `f3b5ec7c36a334f52ad25e1d5ab7f419577f0da5f244f9ca719a7e0ce622e3dd`. The next readiness action is the local zero-provider all-task calibration inventory check in `NEXT_COMMAND.md`. The completed audit invocation was:

```bash
/home/lijingsu/vla/.venv/bin/python \
  research/repeated_v2_formal_readiness_20260906/AUDIT_CALIBRATION.txt \
  --input-root /home/lijingsu/vla/outputs/repeated_v2_readiness_20260906/clean_calibration_01 \
  --output-root /home/lijingsu/vla/outputs/repeated_v2_readiness_20260906/clean_calibration_audit_01 \
  --derive-admission-records
```

The same auditor accepts an unchanged local copy and remaps original remote artifact paths in memory. Keep copy-verification and derived files outside the raw input directory. The passing audit establishes integrity of the **four-task pilot-calibration cohort** and the documented identity aliases; it is not `100/100` calibration completion, global catalog admission, a shared-protocol merge, or formal runtime qualification. Tasks1 and4 pass the unchanged rate check; tasks0 and8 do not.

Frozen preparation identities retained unchanged by this note:

- Calibration driver: `c7e5ba2b1de42e06306eb3d4d04cfabebb420030220ef24e52953ac65cc8c206`.
- Offline auditor: `57d5219a82e7db9cdd8cd50a69e11e8bd992f89d2b714781b96f697031c479b5`.
- Production checkpoint: `d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076`.

# Experiment 1 v2.1 formal-readiness report

Overall status: `BLOCKED_FORMAL_READINESS`. The catalog completeness gap is closed and the two-task pilot preflight passes. Formal execution remains blocked by four eligible tasks versus the frozen minimum of eight, the missing production public runtime assembly, the unestimated interrupted-episode budget, the unrun pilot, and downstream freeze gates. No formal run was started.

## Repository

- Worktree: `/Users/lijingsu/Documents/cope_repeated_v2_formal_readiness_v2_1`
- Branch: `codex/repeated-v2-formal-readiness-v2_1`
- Verified phase-2 base: `1f9372b2703a41fdd881fdc5fab692eb131edf3d`
- Evidence/catalog producer commit: `74c1e7b24bfec55398d8dc2f5be38b2f78691c00`
- Origin: `https://github.com/puredict/CoPE.git`
- Remote branch: `refs/heads/codex/repeated-v2-formal-readiness-v2_1`
- The final response records the exact post-report local and remote SHA because a commit cannot contain its own SHA.
- Trace tag: `exp1-trace-contract-v1`; annotated tag object `f1168bf0c36827a4cbc37db52b3b682c449666eb`; peeled contract commit `1237de979fad501b2e1c730111160959a246bf96`.
- Commits created after the required base: 32 through this evidence commit; exact subjects are in `COMMITS_CREATED.csv`.

## Catalog gap closure

| Stage | Derived catalog gaps | Catalog root-cause units | Scientific eligibility outcomes |
| --- | ---: | ---: | ---: |
| Retained v2 input | 794 | 127 | 0 |
| v2.1 source-backed catalog | 0 | 0 | 12 |

`GAP_MATRIX.csv` accounts for every prior root-cause unit and its cascade count. `GAP_MATRIX_V2_1.csv` contains the 12 measured eligibility failures: three calibration, three structural/milestone, and six frozen-schedule coverage failures. These scientific outcomes were not relabeled as missing catalog data or fabricated passes.

## Production identities

| Component | Identity | Artifact / source identity | Status |
| --- | --- | --- | --- |
| Learned VLA | `openvla_native`, `openvla-7b-finetuned-libero-10` | checkpoint SHA256 `d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076`; official source revision `47a0ec7fc4ec123775a391911046cf33cf9ed83f` | `PRODUCTION_ACTION_GATE_PASSED`; learned=true; privileged=false; finite 1x7 action |
| High-level reasoner | `openai_compatible_http`, `Qwen/Qwen3-32B@9216db5781bf21249d130ec9da846c4624c16137` | model-manifest SHA256 `7323af5c2c972ef1728841512904e98e81212266528f45226e7f80657ff0b4cb`; adapter SHA256 `70024242733cc80fb6d3d0044b83ef4f794b68b94ad8b7722fee336479820357` | Live strict-JSON qualification passed; one non-formal call; zero pilot/formal calls |
| Pure compiler | `compile_ledger` | source SHA256 `a8a56f303907eeedf7fc46506e22834ae4ecb7254823a4fbcd3979b39865b2cc` | Bound and hidden-state poisoning tested |
| Continuation wrapper | `continuation_carrying_repair_v2` | wrapper SHA256 `4f11183dd30c87c2f38da4fb8e6f383038dfd799f717f6d0478ceaf564b05187`; archived package SHA256 `447e1257ae8d62a78b6f995e398722589b2efe4794a11a1d679e534c99601488` | Representation-neutral wrapper present; production public backend dependencies absent |
| Sealed evaluator | `sealed_dynamic_v2.1` | source SHA256 `6272566e7c1db7d3ba9f2be826b11e5d5030f137d7f47c6fd303a33ca8fcab07` | Bound for sealed scoring |
| Durable runner / journal | common runtime / at-most-once journal | runner `07232a57ee27bad3ad5f60778ba40f102807bed560bed43e10f20360a82a47ae`; journal `25fb1c2d8a5866a8810df208203a63df492f8ac27c022e537a15071be8ff2325` | Mock integration tests pass |
| Public evidence builder | unavailable | none | `BLOCKED_PRODUCTION_PUBLIC_EVENT_EVIDENCE_BUILDER_UNAVAILABLE` |
| Public verifier | unavailable | none | `BLOCKED_PRODUCTION_PUBLIC_VERIFIER_UNAVAILABLE` |
| Nominal physical planner | unavailable | none | `BLOCKED_PRODUCTION_NOMINAL_PLANNER_UNAVAILABLE` |
| Production runtime assembly | unavailable | none | `BLOCKED_PRODUCTION_RUNTIME_ASSEMBLY_UNAVAILABLE` |

The archived ReKep environment was rejected because it reads privileged simulator segmentation, meshes, SDF geometry, registered identities, and checkpoints. The OpenVLA checkpoint was also rejected as a public verifier because visual questions returned action tokens. No oracle substitute was used.

## Frozen trace interface

The Experiment-1 interface is frozen independently of task eligibility. Schema SHA256 values are:

| Schema | SHA256 |
| --- | --- |
| `execution_context_snapshot.schema.json` | `27ce23ae6af924aa66edcfd5d412622880ed26e6c4c2bb9d6012c597c3e199f4` |
| `patch_record.schema.json` | `7e6991cc51027621dcc35d12d163760330f2b2d70be4f33f720402a437016c59` |
| `persistent_ledger_snapshot.schema.json` | `7013f359a52b9252446ef64f2597c5c47ff58a0b6a2e4a0855cd8185ba76f00a` |
| `planning_problem.schema.json` | `3c59fc92e22f0c083bd0c0c55e5767c096c3a7ccc8463fb6a485b33b6e274bac` |
| `progress_certificate.schema.json` | `d261e4100d876203256f9c620658c3fd378be19712b2040be43b0f0480357e2e` |
| `public_event_evidence.schema.json` | `c8ec788301138c3d398d7c949704845b740f38d908dfa3ec62eb3c8fb8ca7474` |
| `runtime_trace_bundle.schema.json` | `f715729d108a656bd171c7c8686596b2cac175f6dc27b0662713ced77b0771dd` |
| `sealed_outcome.schema.json` | `111282e3962a0435208cb514695d668deae7653db5cc29ae3576e56bec631b5d` |

## Horizon, split, and calibration

The retained protocol used a fixed 260-policy-step horizon. v2.1 keeps the success interval at inclusive `[0.40, 0.95]` and uses `clip(ceil(1.20 * nearest-rank Q95), 320, 520)` only with at least three successful unique calibration trajectories. It marks insufficient evidence `HORIZON_UNESTIMABLE`. The interrupted-episode budget remains blocked until a calibration-only event-overhead cohort satisfies the frozen evidence rule.

The 500 installed initialization states were enumerated before selection: calibration IDs 0--9, formal IDs 10--14, development IDs 15--19, reserve IDs 20--49. Calibration policy seed 101 and formal policy seed 11 are disjoint. The calibration contains 100 nominal and 100 unique trajectories; policy seeds are technical inputs, not experimental units.

| Task | Successful unique / unique | Clean rate | Successful completion steps | Q95 | H_clean | Gate |
| ---: | ---: | ---: | --- | ---: | ---: | --- |
| 0 | 6/10 | 0.60 | 256, 264, 270, 275, 297, 465 | 465 | 520 | clean pass; task feasibility/schedule fail |
| 1 | 8/10 | 0.80 | 238, 242, 246, 250, 269, 273, 276, 323 | 323 | 388 | eligible |
| 2 | 7/10 | 0.70 | 256, 272, 274, 280, 296, 300, 323 | 323 | 388 | schedule coverage fail |
| 3 | 3/10 | 0.30 | 245, 295, 312 | 312 | 375 | clean interval fail |
| 4 | 7/10 | 0.70 | 208, 228, 230, 264, 267, 270, 284 | 284 | 341 | eligible |
| 5 | 9/10 | 0.90 | 165, 166, 183, 193, 213, 216, 228, 418, 482 | 482 | 520 | one source commitment; structural fail |
| 6 | 4/10 | 0.40 | 201, 249, 253, 436 | 436 | 520 | eligible |
| 7 | 5/10 | 0.50 | 246, 256, 282, 286, 287 | 287 | 345 | eligible |
| 8 | 1/10 | unscored | 378 | — | — | `HORIZON_UNESTIMABLE` |
| 9 | 3/10 | 0.30 | 249, 388, 462 | 462 | 520 | clean interval fail |

Eligible pilot/formal-candidate task IDs are `[1, 4, 6, 7]`. The frozen formal minimum is eight, so formal selection is `BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS`.

## Semantic feasibility

| Task | Registered families | Passing cells / cells | Complete certificate |
| ---: | ---: | ---: | --- |
| 0 | 10 | 47/50 | no |
| 1 | 10 | 50/50 | yes |
| 2 | 7 | 35/35 | yes |
| 3 | 7 | 35/35 | yes |
| 4 | 10 | 50/50 | yes |
| 5 | 7 | 35/35 | yes |
| 6 | 10 | 50/50 | yes |
| 7 | 10 | 50/50 | yes |
| 8 | 6 | 30/30 | yes |
| 9 | 7 | 35/35 | yes |

Nine task certificates are complete. All three failures are task 0 / state 18 physical-contact guards: target displacement increased penetrating contacts 115→134; temporary unavailability and availability-again each increased them 115→127. The failed combinations are excluded from task 0's frozen schedule eligibility. No threshold or scientific rule changed.

The structural replay reproduced 100/100 sealed outcomes and supplies preservable-milestone evidence for every multi-goal task. Task 5 correctly remains structural-ineligible because its BDDL has one achievement commitment.

## Pilot and diagnostic

The authentic zero-call pilot preflight passes and selects tasks 1 and 4. Its deterministic design has four master sessions (two tasks × state IDs 10 and 11 × seed 11), eight non-oracle methods, and 32 expected continuous four-event trajectories. Production execution did not start:

| Expected | Completed | Missing | Duplicate | Unexpected | Provider calls | VLA calls |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 0 | 32 | 0 | 0 | 0 | 0 |

Full-stack latency has zero samples and is `NOT_MEASURED_PILOT_NOT_RUN`. The fixed-template diagnostic passed five registered lookup cases; its held-out realization failed closed as designed. It remains a software diagnostic, not learned-editor or behavioral evidence.

## Verification

- repeated-v2: `932 passed, 1 skipped, 100 subtests` in 92.33 seconds on the branch code.
- full repository on the Mac: `1579 passed, 1 failed, 1 skipped, 100 subtests`; the sole failure is the expected absence of two server-absolute, hash-pinned semantic-oracle artifacts.
- full repository on the existing server Git worktree at `74c1e7b24bfec55398d8dc2f5be38b2f78691c00`: `1580 passed, 1 skipped, 100 subtests in 215.37 seconds; exit 0`.
- zero-provider simulator feasibility: 420 measured dev cells, 417 pass, 3 retained physical-guard failures.
- structural replay: 100/100 outcomes reproduced, exit 0.

## Remaining blockers

- `BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS`
- `BLOCKED_PRODUCTION_PUBLIC_EVENT_EVIDENCE_BUILDER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_PUBLIC_VERIFIER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_NOMINAL_PLANNER_UNAVAILABLE`
- `BLOCKED_PRODUCTION_RUNTIME_ASSEMBLY_UNAVAILABLE`
- `BLOCKED_PRODUCTION_BACKEND_BINDING`
- `BLOCKED_INTERRUPTED_BUDGET_EVIDENCE`
- `BLOCKED_PRIMARY_COMPARATOR_NOT_FROZEN`
- `BLOCKED_TASK_CATALOG_FORMAL_FREEZE`
- `BLOCKED_FREEZE_REQUIRED`
- `BLOCKED_PRODUCTION_RUNTIME_ASSEMBLY_UNAVAILABLE` prevents `PILOT_INTEGRITY_PASS`.

Formal provider calls: 0. Formal trajectories: 0. Formal launch status: `BLOCKED_FORMAL_READINESS`; no formal manifest or result was generated.

## Exact next command

Run only after a production `RuntimeAssembly` supplies the missing public evidence builder, public verifier, and nominal planner and the calibrated interrupted budget is frozen:

```bash
: "${COPE_RUNTIME_FACTORY:?bind the reviewed production RuntimeAssembly module:factory}"
: "${COPE_REASONER_FACTORY:?bind the production reasoner factory}"
: "${COPE_REASONER_MODEL:?bind Qwen/Qwen3-32B at the audited revision}"
: "${COPE_REASONER_ENDPOINT:?bind the audited vLLM endpoint}"
: "${COPE_VLA_FACTORY:?bind cope_benchmark.repeated_v2.vla_adapter:create_native_openvla}"
: "${COPE_VLA_CHECKPOINT:?bind the audited local OpenVLA checkpoint path}"
env -u COPE_ALLOW_FORMAL_RUN python experiments/repeated_interruptions_v2.py \
  --phase pilot \
  --protocol end_to_end \
  --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_1_pilot.yaml \
  --task-catalog task_catalogs/repeated_v2_1/catalog.json \
  --output-dir outputs/repeated_interruptions_v2_1/pilot_end_to_end_01
```

This command deliberately removes `COPE_ALLOW_FORMAL_RUN`; it is a pilot command. Formal execution remains forbidden until every gate in `FORMAL_READINESS_GATES.csv` passes.

## Claim boundary

Paper-safe statements are limited to: the trace interface is frozen; the production learned-VLA action adapter passed its non-privileged finite-action gate; 100 unique clean trajectories were audited; source-backed task semantics close all 794 catalog completeness symptoms; nine feasibility certificates and four eligible task candidates were obtained; and the mock runtime/journal mechanisms pass software tests.

No CoPE-versus-baseline behavioral, scaling, non-inferiority, robustness, latency, or paper `GO` claim is supported. Controlled/oracle evidence cannot be reported as learned-VLA evidence, and software tests cannot be reported as a scientific result.

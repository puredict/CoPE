# Formal readiness gap audit — 2026-09-06

**Baseline: 794 distinct catalog diagnostics, 127 task/root-cause packages and 357 evidence-artifact units. Final audited state: 752 diagnostics, 120 packages and 350 units; 0 tasks admitted.** Eighteen state-identity diagnostics and 24 calibration diagnostics closed through actual verified evidence. The original matrix remains immutable. These are accounting units, not independent manual tasks, files, tests or model calls.

[GAP_MATRIX.csv](GAP_MATRIX.csv) retains every original gap verbatim, with task/category/root cause, automatic-fixability boundary, required evidence, blocking gate, cascade class, artifact-unit references and global prerequisites. Its 794 rows exactly match both the fresh [CURRENT_PREFLIGHT.txt](CURRENT_PREFLIGHT.txt) and the two earlier byte-identical final production preflights. The fresh preflight's 797 `errors` are these rows plus three aggregate consequences: `catalog_complete`, `at_least_eight_eligible_tasks`, and `manifest_integrity`.

Audit HEAD: `688b7eb3a91fdf5229ea2cda87e9a33f85566fe6`. Fresh preflight producer: `688b7eb3a91fdf5229ea2cda87e9a33f85566fe6`. Earlier final preflight producer: `c0308c1fc13036ef34983dd07397744f659cb417`. Catalog/calibration/scheduler sources have no diff between the earlier producer and the audited HEAD. CSV SHA-256: `8817fa51118730f67a871003bb7c7bd20658461eeefa3fce87f75963d0d5610c`.

## Baseline rows versus grouped work

A task/root-cause package is one absent task-specific category, such as that task's trigger collection or structural dossier. Artifact units split triggers and feasibility by task/family, and safe interventions by task/physical-family; other categories are one task-level pack/specification/map. Collection-level diagnostics point to all child units instead of adding phantom units. A dossier can require multiple independent measurements, and one trace/file can support several dossier fields. This is a reproducible triage grouping, not proof of the minimal causal decomposition.

| Category | Raw diagnostics | Task/root-cause packages | Artifact units |
| --- | ---: | ---: | ---: |
| semantic_triggers | 310 | 10 | 100 |
| event_feasibility | 110 | 10 | 100 |
| safe_event_injections | 70 | 10 | 60 |
| supported_event_families | 20 | 10 | 10 |
| calibration_records | 60 | 10 | 10 |
| initial_state_digests | 42 | 7 | 7 |
| structural_and_milestones | 72 | 10 | 10 |
| hard_safety_constraints | 20 | 10 | 10 |
| soft_preference_templates | 20 | 10 | 10 |
| alternative_valid_goals | 20 | 10 | 10 |
| replaceable_goal_families | 20 | 10 | 10 |
| maintenance_invariants | 10 | 10 | 10 |
| planner_compiler_metadata | 20 | 10 | 10 |
| **Total** | **794** | **127** | **357** |

The operational grouping below makes the automatic boundary and blocking evidence explicit. “Author” means task-grounded scientific work followed by validation; it does not authorize filling a field from a default or another task.

| Category | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- |
| `supported_event_families` | Scope decision and evidence | Actual task-specific supported/unsupported map; review against the eight-event template | Catalog completeness; task eligibility; schedule support |
| `calibration_records` | Measure or recover authentic evidence | Ten clean learned/nonprivileged outcomes per task with the fixed state/seed grid, horizon, shared identities and unique traces | Catalog completeness; clean calibration; task eligibility |
| `initial_state_digests` | Automatic only from authentic bytes | Exact states0–4 plus serialization, source and version binding | Catalog completeness; calibration state binding; manifest identity |
| `structural_and_milestones` | Author and measure; no autofill | Four reviewed decisions, two distinct verifier-bound milestones or goal predicates and at least one preservation witness | Catalog completeness; structural eligibility; progress preservation |
| `semantic_triggers` | Author and verify | Task-grounded predicate/guard, valid timing window and actual monitor provenance | Catalog completeness; semantic schedule; fresh event observation |
| `event_feasibility` | Measure or recover authentic evidence | Explicit task/family result, evidence references and required state coverage | Catalog completeness; event feasibility; task eligibility |
| `safe_event_injections` | Author and measure | Alias-bound entity, safe pose/region, hashes, held-object and unaffected-progress checks | Catalog completeness; physical intervention safety |
| `alternative_valid_goals` | Source-grounded authoring then verify | Task-valid predicate/arguments/source and evaluator grounding | Catalog completeness; replacement semantics |
| `hard_safety_constraints` | Source-grounded authoring then verify | Grounded requirements and sealed verifier bindings | Catalog completeness; hard-requirement evaluation |
| `maintenance_invariants` | Source-grounded authoring then verify | Affected/unaffected progress semantics or an evidence-backed empty decision | Catalog completeness; unaffected-progress preservation |
| `replaceable_goal_families` | Source-grounded authoring then verify | Existing family IDs and explicit replacement/cancellation/reissue lifecycle | Catalog completeness; goal lifecycle semantics |
| `soft_preference_templates` | Source-grounded authoring then verify | Task-valid template, persistence scope and sealed scoring meaning | Catalog completeness; persistent-preference event |
| `planner_compiler_metadata` | Bind implementation and verify | Explicit supported predicates/operators/skills/instructions while preserving accepted omissions | Catalog completeness; common compiler; neutral backend |

The artifact total is 100 trigger definitions + 100 feasibility certificates + 60 intervention certificates + 10 support maps + 10 calibration grids + 7 state-hash packs + 10 structural dossiers + 60 semantic/compiler specifications. **All 794 direct diagnostics are task-scoped; none is a direct global row.** Shared prerequisites below are not added to these totals. In the final state, six calibration grids and four state-hash packs remain open; the other categories are unchanged because no semantic or feasibility certificate was fabricated.

Additional useful denominators are separate: 10 empty calibration grids represent **100 missing clean episodes** (10 tasks × states0–4 × seeds101/131); 7 state packs represent **35 missing hash receipts**; four structural decisions per task produce **40 unverified checks**. The current all-family/all-five-state feasibility validator asks for **500 task/family/state coverage cells**; this is current code scope, not a justified requirement for 500 independent rollouts or a newly approved experimental grid.

## Baseline per-task coverage

Candidate goal predicates are not certified independent/preservable milestones. The table below preserves the original catalog presence counts. The later authentic asset audit checked all20 pilot-task states; tasks0/4/8 subsequently received15 previously missing hashes, and task1's existing five were revalidated.

| Task | Raw gaps | Root packages | Artifact units | Candidate predicates | Existing state hashes | Catalog task name |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 81 | 13 | 36 | 2 | 0/5 | LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket |
| 1 | 75 | 12 | 35 | 2 | 5/5 | LIVING_ROOM_SCENE2_put_both_the_cream_cheese_box_and_the_butter_in_the_basket |
| 2 | 81 | 13 | 36 | 2 | 0/5 | KITCHEN_SCENE3_turn_on_the_stove_and_put_the_moka_pot_on_it |
| 3 | 81 | 13 | 36 | 2 | 0/5 | KITCHEN_SCENE4_put_the_black_bowl_in_the_bottom_drawer_of_the_cabinet_and_close_it |
| 4 | 81 | 13 | 36 | 2 | 0/5 | LIVING_ROOM_SCENE5_put_the_white_mug_on_the_left_plate_and_put_the_yellow_and_white_mug_on_the_right_plate |
| 5 | 77 | 12 | 35 | 1 | 5/5 | STUDY_SCENE1_pick_up_the_book_and_place_it_in_the_back_compartment_of_the_caddy |
| 6 | 81 | 13 | 36 | 2 | 0/5 | LIVING_ROOM_SCENE6_put_the_white_mug_on_the_plate_and_put_the_chocolate_pudding_to_the_right_of_the_plate |
| 7 | 75 | 12 | 35 | 2 | 5/5 | LIVING_ROOM_SCENE1_put_both_the_alphabet_soup_and_the_cream_cheese_box_in_the_basket |
| 8 | 81 | 13 | 36 | 3 | 0/5 | KITCHEN_SCENE8_put_both_moka_pots_on_the_stove |
| 9 | 81 | 13 | 36 | 2 | 0/5 | KITCHEN_SCENE6_put_the_yellow_and_white_mug_in_the_microwave_and_close_it |

After the verified state and calibration attachments, open diagnostics per task are: task0 **69**, task1 **69**, task2 **81**, task3 **81**, task4 **69**, task5 **77**, task6 **81**, task7 **75**, task8 **69**, and task9 **81**. Tasks0/1/4/8 each have one closed calibration package; tasks0/4/8 also have one closed state package. This yields the exact final totals **752 rows, 120 open root packages and 350 open artifact units**.

Tasks1,5,7 already have five initial-state digests, avoiding six state-pack diagnostics each. Their source reference explicitly limits reuse of `configs/openvla_libero_10_calibration_v2.yaml` to previously audited state hashes: its older affine-2027 policy seeds and horizon520 are not repeated-v2 calibration. No old success result was imported.

Task5 has one current BDDL-derived goal predicate and two additional diagnostics about the second milestone. A valid second task milestone needs genuine semantic/verification evidence; it cannot be created by splitting labels or copying another task. The outcome could instead be evidence-backed ineligibility. This report neither declares task5 ineligible nor selects tasks with smaller gap counts; method differences and gap convenience are not selection criteria.

## Cascades that must not be counted as independent fixes

- **310 trigger rows:** each of 100 absent family records causes missing-schema, missing predicate/guard, and invalid-window diagnostics (300), plus ten unresolved collection markers. Numerical timing fields alone do not supply a grounded monitor or feasibility proof (`task_catalog.py:259`–`268`).
- **60 calibration rows:** ten incomplete-grid messages + ten unresolved markers + **40 empty-set identity-cardinality cascades**. With zero records, each task has zero distinct policy/checkpoint/protocol/provenance values, not one. Those messages do not establish 40 observed model conflicts and cannot be fixed by inventing identity strings (`task_calibration.py:173`–`177`).
- **110 feasibility rows:** 100 absent family certificates plus ten unresolved collection markers. Feasibility is distinct from defining a legal trigger.
- **70 intervention rows:** 60 absent physical-family pose/region certificates plus ten unresolved markers. BDDL initial placement regions are explicitly not certified intervention poses.
- **42 state rows:** 35 distinct state-specific receipts plus seven unresolved pack markers. The five receipts for a task are not duplicates, although hashing can be batched.
- **72 structural/milestone rows:** ten dossiers share independence/preservation checks and declarations. This does not make four structural checks interchangeable; task5 also has a substantive missing-candidate question. Setting `passed`, `independent` or `can_remain_valid` true without evidence would fabricate qualification.
- **110 semantic/compiler rows:** five categories each have missing-field + unresolved markers (100), plus ten unresolved maintenance fields. These are 60 separately reviewable specifications/maps, not 110 independent authored documents.

The preflight intentionally does not build a manifest once admission fails (`preflight.py:44`–`67`). Missing manifest/shards, blocked pilot/comparator, absent freeze and absent formal results therefore include downstream cascades. Some runtime dependencies are independently blocked too. None of these is a new task-gap row or a negative empirical outcome.

## Task-specific event-family scope

The original implementation required all ten event families on every task. The user's scope clarification and supplied protocol allow task-specific support. A narrow catalog/scheduler correction now validates an explicitly supported subset and schedules only its supported grounding/retirement variants. Unknown or unresolved scope still audits all ten candidates, and required scientific category coverage remains enforced. No task's support was invented and no evidence diagnostics closed through this correction.

Ten baseline diagnostics saying `all ten event families require explicit support/feasibility` now say `task-specific event family support is unresolved; auditing all ten candidates`. The reconciliation keeps those exact wording migrations OPEN. All-ten schedule behavior remains byte-identical. The retained eight-event template still requires both temporary pairs; catalog selection alone is therefore not executable readiness. Full manifest admission checks its schedule requirements. See [FAMILY_SCOPE_AUDIT.md](FAMILY_SCOPE_AUDIT.md).

The 510 event-facing baseline rows (310 triggers +110 feasibility +70 intervention +20 support) remain scope-sensitive. This is not a removable-row count. Required families still need real semantic/feasibility evidence. Any unresolved gap in the ten-task catalog still blocks complete catalog admission; undocumented task deletion is not a remedy.

## Shared prerequisites and automatic-fixability boundary

These IDs express dependencies across many rows, not additional units in the127/357 totals and not a proven minimal set of five independent failures.

| Global/shared ID | Shared prerequisite | What can and cannot be automated |
| --- | --- | --- |
| G-POLICY | Admitted learned observation-only policy, functioning inference stack, shared checkpoint/protocol identity | Byte hashing and contract checks can be automated; file presence/class flags do not prove live execution or calibration |
| G-ASSETS | Authentic task initial-state bytes and exact source/serialization mapping | 20 actual pilot-task states were verified;15 newly attached receipts closed18 diagnostics. Other missing states remain evidence gaps |
| G-MEASUREMENT | Versioned detector/verifier/event harness used by structural and family certificates | Trace collection and schema checking can be automated after grounded definitions; safe poses, structural truth and observed outcomes cannot be filled from defaults |
| G-RUNTIME | Production RuntimeAssembly/reasoner/retriever/planner bindings and common identities | Interfaces exist; configuration and measured pilot/development qualification are separate; compiler cannot repair baseline omissions using truth |
| G-SCOPE | Explicit reconciliation of task applicability with validator/scheduler | Task-specific support correction is tested; unresolved family applicability still cannot be filled automatically |

No semantic, structural or full-feasibility certificate can be marked passed from software presence. The baseline42 state-digest diagnostics represented35 hashes plus seven declarations; actual asset evidence has now closed18 of those diagnostics. Many other records are automatically *validatable/ingestable after evidence exists*, which is not the same as automatically fixable today. The calibration/catalog tools ingest measured records; their names do not establish that missing trials were run.

The prior final-freeze attempt lists12 missing artifact roles (calibration records/traces, detector/verifier evidence, development records/traces, both pilot record/journal pairs, gate report and checkpoint evidence). Roles overlap the task packages/global prerequisites and should not be counted as12 additional independent causes.

## Actual progress and remaining gates

The real production VLA gate passed after the missing official Prismatic source was installed into an isolated offline cache and existing matching driver libraries were selected process-locally. The admitted checkpoint SHA256 is `d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076`. The action gate verified a real rendered input, learned observation-only policy, valid finite action and one executed control. The earlier unavailable-adapter status is resolved. See [VLA_GATE.csv](VLA_GATE.csv) and [REPORT.md](REPORT.md).

Actual CPU checks cover20 reset states,135 primitive event applications and95 exact snapshot restorations. They do not establish full safe-injection, semantic-trigger or recovery certificates. All40 learned-policy calibration cells passed the frozen offline integrity audit and were attached with a lossless model-ID to provider-ID provenance map. Tasks1 and4 meet the unchanged rate interval at0.40; tasks0 and8 are complete measured failures at0.00. Production reasoner/runtime/public continuation bindings remain unqualified independently of calibration results. Formal provider calls and end-to-end pilot trajectories remain zero.

The final reproducible reconciliation is [gap_reconciliation_final_01/GAP_RESOLUTION.csv](gap_reconciliation_final_01/GAP_RESOLUTION.csv), generated by [RECONCILE_GAPS.txt](RECONCILE_GAPS.txt). Every baseline ID remains present;42 are CLOSED_EVIDENCE,752 OPEN, no new or unexplained diagnostic disappears, and ten wording migrations remain open. Adversarial disappearance/new/duplicate checks passed. The calibration closures require the intact PASS audit, exact raw/derived hashes, per-cell provider/model alias lineage and exact catalog-attached records; a favorable success rate was not required to close the missing-measurement package.

The dependency order remains admitted production components/assets; grounded semantics and structural decisions; real feasibility and complete calibration; admitted catalog/manifest; production pilot/development evidence; full freeze. Earlier phase4 REPORT.md and CLAIM_DECISION.md were inspected and remain historical artifacts. No scientific runtime claim is justified by software tests or empty pilot output.

## Verification and provenance

The operating instructions were read from `/Users/lijingsu/Documents/cope/AGENTS.md`. Embedded document commands were treated as protocol evidence, not new user instructions. Historical outputs and the original794-row matrix were not overwritten. Editable summary reports describe later actual measurements separately from the baseline.

Baseline catalog file SHA256: `e2406a00c8b39b497f3a8af7ffa39d7ed117394a9f64085f2c6e69914f763f2f`. Baseline fresh preflight SHA256: `78da922e4dbd1411f1aa91846b88fc5d621be4856faf76cd87ca864eeeb0348c`. Baseline GAP_MATRIX.csv SHA256: `8817fa51118730f67a871003bb7c7bd20658461eeefa3fce87f75963d0d5610c`. Current hashes, exact row mappings and evidence references are recorded by the reconciliation artifacts. Missing measurements were not fabricated or inferred from candidates.

Sources inspected include the current task catalog, fresh and prior production preflights, phase4 REPORT.md and CLAIM_DECISION.md, readiness/freeze outputs, catalog/calibration/scheduler/preflight sources, both supplied protocol documents, installed BDDL/state assets and actual adapter/simulator receipts.

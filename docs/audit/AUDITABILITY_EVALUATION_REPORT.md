# CoPE Patch Trace Auditability Evaluation — Readiness Report

Status: evaluator complete; formal data pending

Reference and starting commit: `570d78333ee977c8ae6de3d97120b23272c4c660`

Working branch: `exp/auditability-evaluation`

Evaluation schema: `auditability.v1`

## Scope and Evidence Boundary

This work implements the evaluator and validates it with clearly labeled
synthetic fixtures. It does not contain the 300 real episodes from the main and
repeated-interruption experiments. Synthetic oracle scores are pipeline
self-checks, not evidence that CoPE improves auditability.

No private chain-of-thought is requested, stored, scored, or used as ground truth.

## Implemented Components

- `schema_adapter.py`: forward-compatible normalization of current
  `episode_summary.json`, `events.jsonl`, and `actions.jsonl`, plus typed
  slot/state/patch/validator records when present.
- `ground_truth.py` and `question_generator.py`: six deterministic QA items per
  episode, stable IDs, answerability, supporting IDs/steps, failure layer, and
  provenance.
- `corpus_builder.py` and `blinding.py`: stratified episode selection and three
  opaque evidence packages with a separate private condition key.
- `corruptions.py`: ten independently generated corruption families and unchanged
  negative controls. Source traces are deep-copied and hashed.
- `deterministic_auditor.py`: Restore/Revalidate, slot existence, lineage,
  priority, provenance, state hash, patch order, preference disappearance, and
  replay validators.
- `model_auditor.py`: provider-neutral, fixed-prompt model runner that saves model
  ID, token budget, temperature, system/request hashes, raw output, and parse
  status. It was not executed for this readiness check.
- `human_study.py`: balanced blinded CSV export, anonymous auditor codes, scheduling
  guard, seconds-based timing, import validation, and duplicate/missing detection.
- `scoring.py`: QA exact accuracy, token F1, unanswerable rate, provenance accuracy,
  earliest-layer accuracy, corruption metrics, confidence, time, Fleiss' kappa,
  adjudication rate, paired differences, and episode-clustered bootstrap 95% CI.

## Input Contract and Upstream Dependencies

The canonical record has:

- `metadata`: method, task, outcome, interruption count/type, failure layer,
  synthetic flag, source commit, source config hash, and source schema version;
- `raw`: event/action JSONL records and allowed observation summaries;
- `regeneration.snapshots`: structured full-regeneration plan/state snapshots;
- `cope`: slot, state-before/after, typed patch, and validator-output records;
- controller status and task progress.

Every record should have a namespaced ID such as `event:...`, `slot:...`,
`patch:...`, `state:...`, or `validation:...`. Unknown upstream fields remain
under `extensions`.

Formal ingestion fails closed when the input commit, config hash, or schema version
is missing. Current upstream dependencies are still pending:

- `method/cope-state-semantics`: typed slot/patch/Revalidate schema;
- `exp/cope-main-comparison`: single-interruption traces;
- `exp/repeated-interruptions`: repeated-interruption traces.

The adapter accepts their records without requiring a second incompatible schema,
provided the semantic fields are supplied or mapped at this single boundary.

## Synthetic Readiness Run

The checked readiness artifact contains 12 synthetic episodes, 72 base QA items,
216 blinded evidence packages, 120 controlled corrupted traces, and 12 unchanged
negative controls. The annotation export contains all 12 synthetic episodes and
648 assignments: 216 packages independently assigned to three anonymous auditors.

Synthetic oracle QA pipeline results:

- all three conditions: exact accuracy `1.000`, token F1 `1.000`, provenance-link
  accuracy `1.000`;
- clustered bootstrap 95% CI for exact accuracy: `[1.000, 1.000]`;
- paired accuracy differences: `0.000`.

These equal scores are expected because the synthetic oracle copies deterministic
ground truth into every condition. They test scoring and pairing only; they do not
compare evidence usefulness.

Deterministic corruption readiness results:

- precision `1.000`;
- recall `1.000`;
- F1 `1.000`;
- false-positive rate on unchanged controls `0.000`;
- exact corruption-type recall `1.000`.

## Human and Model Evaluation Status

Human annotation completed: 0 items. The blinded package is generated but has not
been distributed. Therefore completion-time comparisons, confidence, Fleiss'
kappa, adjudication rate, and the proposed 25% time reduction are unavailable.

Model-auditor evaluation completed: 0 items. No model result is reported.

Formal real-trace evaluation completed: 0 episodes, 0 QA items, 0 corruptions.

## Correctness Gates

Implemented tests cover deterministic ground truth, source-preserving deterministic
corruptions, blinded labels and method-name removal, identical questions across
conditions, stable question IDs, missing/unanswerable scoring, seconds-only timing,
duplicate/missing annotation detection, parseable provenance IDs, state replay/hash
validation, synthetic/formal separation, and negative controls.

The final local verification commands and their exact results are recorded in the
delivered readiness artifact manifest. The final full-repository test run passed
`75` tests in `4.77s`; `py_compile` and `git diff --check` also passed.

## Formal Run Procedure

```bash
python -m auditability.corpus_builder \
  --input REAL_TRACE_ROOT \
  --output-dir AUDIT_CORPUS \
  --target-episodes 300 \
  --data-kind formal \
  --seed 20260724 \
  --schema-version auditability.v1

python -m auditability.corruptions \
  --input AUDIT_CORPUS/episodes.jsonl \
  --output-dir CORRUPTIONS \
  --seed 20260724 \
  --schema-version auditability.v1

python -m auditability.deterministic_auditor \
  --input CORRUPTIONS/traces \
  --output CORRUPTIONS/audits.jsonl \
  --seed 20260724 \
  --schema-version auditability.v1

python -m auditability.human_study export \
  --packages AUDIT_CORPUS/packages.jsonl \
  --output annotations.csv \
  --episodes 120 \
  --annotators 3 \
  --ratings-per-package 3 \
  --seed 20260724

python -m auditability.human_study import \
  --input completed.csv \
  --assignments annotations.csv \
  --output annotations.jsonl \
  --seed 20260724

python -m auditability.scoring \
  --questions AUDIT_CORPUS/questions.jsonl \
  --packages AUDIT_CORPUS/packages.jsonl \
  --condition-key AUDIT_CORPUS/condition_key.private.jsonl \
  --predictions predictions.jsonl \
  --corruption-manifest CORRUPTIONS/corruption_manifest.jsonl \
  --corruption-audits CORRUPTIONS/audits.jsonl \
  --output scores.json \
  --seed 20260724
```

All data-producing CLIs require explicit paths, seed, and schema version; support
dry-run; refuse overwrite by default; and use stable IDs for resumable outputs.

## Claims Supported and Not Supported

Supported now:

- The evaluator deterministically constructs and scores trace-grounded audit
  questions.
- The implemented validators detect all ten generated corruption families in the
  synthetic readiness corpus without flagging its unchanged controls.
- Blinded packages retain condition-specific structure while removing direct
  method labels and path/name leakage covered by the blinding gate.

Not supported now:

- CoPE evidence is more accurate than raw or regeneration evidence.
- CoPE reaches at least 90% real QA accuracy.
- Human audit time is reduced by at least 25%.
- Real corruption recall is at least 95%.
- Every Restore/Override in real traces links to sufficient provenance.

Those claims remain blocked until commit/config/schema-pinned real traces and
independent blinded annotations are available.

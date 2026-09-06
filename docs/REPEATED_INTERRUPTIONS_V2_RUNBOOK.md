# Phase-1 runbook

Use Python with repository development dependencies (`pytest`, `jsonschema`,
`PyYAML` and existing test dependencies). No GPU, model or provider is required.
All output paths must be new; tools refuse to overwrite artifacts.

```bash
python -m pytest -q
python -m pytest -q tests/repeated_v2
python tools/validate_repeated_interruptions_v2.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --task-catalog task_catalogs/repeated_v2.json \
  --output-dir outputs/repeated_v2_preflight_run1
```

The checked-in catalog intentionally returns exit 2 and
`BLOCKED_TASK_CATALOG_GAPS`. It contains no qualifying calibration or measured
injection feasibility. This is the expected fail-closed readiness result, not a
failed implementation check and not evidence that any task is physically
unsuitable. A second run with identical inputs and a different new output
directory must produce byte-identical `preflight.json`.

Offline calibration accepts supplied evidence only; it never runs a policy.
After measured v2 calibration and explicit task semantics/feasibility exist,
validate them and build a manifest:

```bash
python tools/calibrate_repeated_v2_tasks.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --output-dir outputs/repeated_v2_calibration
python tools/build_repeated_v2_task_catalog.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --calibration-dir outputs/repeated_v2_calibration \
  --output task_catalogs/repeated_v2_candidate.json
python tools/build_repeated_interruptions_v2_manifest.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --task-catalog task_catalogs/repeated_v2_candidate.json \
  --output manifests/repeated_interruptions_v2.jsonl
```

A candidate catalog may remain blocked; its existence never implies admission.
No actual manifest is checked in until authentic evidence passes selection.
Manifest validation reconstructs the complete deterministic grid, checks every
row and schedule hash, and rejects missing, duplicate or unexpected sessions.
The file hash is SHA256 over JSONL bytes; the manifest semantic hash is SHA256
over the canonical JSON array. Both are named separately.

For eight eligible tasks there are 120 unique masters. Per information
condition: controlled has 1,080 trajectories / 8,640 event cells / 5,400
checkpoint records; end-to-end has 1,080 / 4,320 / 4,320. Across both conditions
there are 4,320 trajectories, 25,920 event cells and 19,440 checkpoint records.
Ten tasks give 150 masters, 5,400 trajectories, 32,400 event cells and 24,300
checkpoint records across conditions. Counts include the oracle upper bound;
non-oracle and oracle counts are also reported separately. K=0 is a checkpoint,
not an interruption or provider call.

Formal readiness remains false in phase 1, even with a complete catalog. The
preflight lists unimplemented phase-2/3/4 gates instead of pretending to have
validated methods, compiler, runtime, provider identities or statistical claims.
Cell namespaces include condition and protocol; later resume must verify full
config/catalog/manifest hashes before reusing any key, because catalog changes
can rebalance schedules without changing a task/state/seed identity.

The old authorization regression test requires hash-pinned files under
`/home/lijingsu/vla/src/LIBERO`. It runs unchanged in the existing Linux
environment. A Mac without those files cannot pass that one environment-specific
test; do not weaken the hash checks or edit frozen path-bearing artifacts.

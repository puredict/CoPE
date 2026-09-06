# Window 4: statistics, freeze, formal protocols

Window 4 adds analysis and launch control after the committed phase-3 runtime. The core research hypothesis and frozen v1 files remain unchanged. The attached package is a scientific reference; the user's Window 4 instruction authorizes these implementation changes and gated executions. Research deliverables here use Markdown, CSV and TXT.

## Commit and admission order

1. Integrate the phase-3 SHA and commit the analysis implementation, tests, launcher and statistical preregistration. Qualify that exact source with the complete regression suite in the environment containing pinned LIBERO assets before building a formal freeze. Any subsequent code fix requires a new code commit and appropriate revalidation before formal calls.
2. Supply authentic task calibration, all eligible task catalog records (at least eight), the deterministic full master manifest, production development outcomes, and both complete production pilots. Missing evidence is a blocker; synthetic fixtures never qualify.
3. Build the freeze from actual files and identities. It records the analysis git SHA/tree, phase-3 ancestor, config/catalog/manifest, exact prompts and schemas, models/checkpoint, detector/verifier/compiler/backend/retriever implementations, raw qualification evidence, gate test source and successful JUnit evidence. Development selection uses paired K=4 success, corruption, then lexical comparator name on a disjoint split.
4. Validate the immutable freeze before every external formal call and verified resume. Any later byte, git, configuration or live identity drift stops execution. Do not amend the analysis commit after launch. Results must be a separate later commit.
5. Launch each protocol and information condition in exactly eight deterministic master-session shards. All arms and checkpoints for a master remain together. The learned-VLA launcher runs `nvidia-smi` and admits only GPUs with no compute process, zero utilization, and at most 100 MiB allocated memory; it rechecks before each wave. It never terminates another process. Controlled execution is CPU-only in this launcher. A production factory must supply the configured stack and live identities; no provider/policy substitute is allowed.
6. Analyze only complete shard groups after checking original journal envelopes, call intents/responses, retained failure boundaries, action snapshots, exports and ownership. No cell is removed, regenerated, relabeled into success or filled by the analyzer.

## Freeze interface

`tools/freeze_repeated_interruptions_v2.py` accepts `--repo-root`, `--phase3-sha`, `--config`, `--task-catalog`, `--manifest`, `--artifact-map`, `--identities`, and `--output-dir`. Artifact-map and identity files contain public JSON in `.txt` files; they must never contain credentials. The exact required roles and validation rules are defined by `REQUIRED_ARTIFACTS`, `REQUIRED_CHECKS` and `IDENTITY_COMPONENTS` in `cope_benchmark/repeated_v2/freeze.py`.

Qualification summaries must resolve to authentic raw trace/journal directories. Development journals use `phase=development`, pilots use `phase=pilot`; both declare `fixture=false` and the exact runtime component identities. Formal journals contain the complete frozen bundle. Digests prove byte/provenance consistency; they do not independently authenticate a remote model or prove that a supplied observation occurred.

A successful freeze writes `FREEZE.txt` plus `SHARD_00.csv` through `SHARD_07.csv`. A failed freeze writes only `BLOCKED_FREEZE.txt`, makes zero formal calls, and creates no substitute manifest. Missing inputs have no invented hashes. Frozen checkpoint symlink targets and explicit external implementation paths are hashed in place.

## Launch commands

Use the exact real paths recorded in the freeze; the following placeholders must be replaced with those paths.

```bash
COPE_PYTHON=/path/to/qualified/python bash scripts/run_repeated_interruptions_v2.sh \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --task-catalog task_catalogs/repeated_v2.json \
  --manifest research/formal_inputs/master_manifest.txt \
  --frozen-bundle research/formal_freeze/FREEZE.txt \
  --protocol controlled --information-condition evidence_matched \
  --output-root research/formal_run --workers 1
```

`COPE_RUNTIME_FACTORY=package:factory` is the production runtime assembly factory. The child experiment CLI checks live identities before calls. Repeat with `--protocol end_to_end` only when all gates still pass. Repeat the two protocols under `token_matched` for the separate descriptive condition. `--plan-only` validates and prints the eight commands without model calls or output cells. `--resume` invokes the runtime's verified at-most-once resume; ambiguous calls remain blocked.

## Analysis and paper outputs

`tools/analyze_repeated_interruptions_v2.py --freeze ... --manifest ... --run-dir ... --output-dir research/...` accepts repeated `--run-dir` arguments. Supply all eight directories for every submitted protocol/condition, including an explicitly empty shard if its frozen ownership is empty. Every directory must include `00_RUN_METADATA.json`, `06_EVENT_RESULTS.jsonl`, and its immutable `journal/` directory. The full manifest is supplied to both launcher and analyzer, never a K-specific restart manifest.

The analyzer checks actual exact public prompts, frozen templates/input allowlists, leakage scans, backbone/settings and one-call accounting. Evolving method states may differ after treatment errors; their semantic hashes are not incorrectly required to remain identical. No prompt or model call is issued by analysis.

Outputs include per-method/checkpoint/task tables, paired tests and discordants, one-sided non-inferiority, degradation slopes, planning fidelity and history corruption, overlapping failure taxonomy, latency/tokens, `paper_table.md`, `paper_curves.md` and the full curve data CSV, `REPORT.md`, and `CLAIM_DECISION.md`. Empty tables mean no admissible observations, not zero success. Oracle rows are retained and labeled diagnostic; they never enter the primary or Holm family. Token-matched data never supply binding runtime evidence.

The preregistration fixes 10,000 paired master-session bootstrap draws, seed 20260906, type-7 percentile intervals, the probability-scale slope against log2(K+1), 13 secondary Holm hypotheses, and the −0.05 one-sided non-inferiority margin. See `WINDOW4_STATISTICAL_PREREGISTRATION.md` for exact rules and claim boundaries.

For a run that cannot start, use repeatable `--blocker BLOCKED_*` arguments without `--run-dir`. This produces a zero-cell readiness report only. It cannot fabricate an experiment estimate or turn a missing dependency into `NO_GO`.

## Reproducibility limits

The live freeze validator requires the frozen clean git SHA during execution. A later result-only commit must not be used to resume calls under the earlier SHA. Read-only analysis accepts that frozen SHA or a clean descendant whose only changes are added nonexecutable result artifacts under `research/` or `docs/`; it still verifies all frozen source, input, checkpoint and backend bytes. Modified or deleted files, source additions, executable files and symlinks invalidate archival admission. Resuming calls requires the original frozen checkout and immutable input paths. Scientific claim evaluation is not authorization to bypass run integrity.

Failure snapshots and original artifacts are retained after errors. New report destinations use exclusive creation. Re-analysis uses a new report directory. No script deletes source records, rewrites git history, creates accounts, uses sudo, downloads checkpoints, or silently launches an oracle as VLA.

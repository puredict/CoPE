# Locked live-smoke and formal launch runbook

Date: 2026-08-04

This runbook is operational only.  It does not change the frozen manifest,
contracts, protocol, endpoints, or analysis.  Never paste or echo a credential
into a command log, result file, shell history, or git artifact.

## Preconditions

Run from `/home/lijingsu/codex-worktrees/cope-shared-envelope` on port 26575.
The worktree must be clean and the credential must already exist in the caller's
environment through a secure interactive mechanism.  The check below reveals
only presence, never the value:

```bash
test -z "$(git status --porcelain)"
test -n "${OPENROUTER_API_KEY:-}"
export CUDA_VISIBLE_DEVICES=""
umask 077
```

Do not create the result directory before a runner starts.  In particular, do
not redirect stdout into the result directory: shell redirection happens before
the Python cleanliness/output-existence guards.  Use a repository-external log.

## Stage 1: development-only live-provider smoke

```bash
nohup scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  experiments/sequential_provider_development_smoke.py \
  --case-manifest manifests/sequential_persistence_gate_v2.csv \
  --output-dir research/sequential_provider_smoke_2026-08-04/live_locked_v1 \
  >/tmp/cope_sequential_smoke_live_locked_v1.log 2>&1 &
echo $! >/tmp/cope_sequential_smoke_live_locked_v1.pid
```

Monitor read-only.  A normal completed run has exactly 32 unique journal rows,
at most 32 provider calls, zero retries, and zero simulator states.  The gate is
the frozen per-arm/per-sequence-type rule in the runner, not an informal reading
of the log.

If `03_RESULT.md` says PASS, inspect and commit the complete smoke evidence.
Restore a clean worktree before formal launch.  This commit is an intentional
provenance checkpoint.  If the gate fails, do not launch formal and do not
repair the prompt in place; version contracts and repeat all dependent gates.

If the connection dies and the journal has exactly 32 unique frozen cells but
derived files are absent, first commit the retained journal in that state, then
run `tools/finalize_sequential_provider_smoke_journal.py` from the resulting
clean commit.  A partial journal is not recoverable by filling missing calls.

## Stage 2: embodied formal run

Only after the locked smoke PASS evidence is committed and the worktree is
clean:

```bash
nohup scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  experiments/sequential_formal_runner.py \
  --manifest manifests/sequential_formal_40x4x2_v1.csv \
  --output-dir research/sequential_formal_2026-08-04/locked_v1 \
  >/tmp/cope_sequential_formal_locked_v1.log 2>&1 &
echo $! >/tmp/cope_sequential_formal_locked_v1.pid
```

The maximum is 320 scheduled provider calls.  Event 2 is not called after an
event-1 failure, so actual calls may be lower.  Never issue a replacement call
to force the count to 320.  Task-0 states 10--29 are formal; states 30--49 are
reserve.  Task-1 state 33 must not be retried and task-1 states 34--49 must not
be indexed.

On normal completion, analyze exactly `03_EVENT_RESULTS.csv` with
`tools/analyze_sequential_formal.py` and the frozen manifest.  If a disconnect
leaves exactly 320 unique journal cells but no derived CSV/status, first commit
the retained journals, then use `tools/finalize_sequential_formal_journal.py`
from a clean commit.  Any partial or duplicate journal is an integrity stop,
not authorization to resume or impute.

## Interpretation

The decisive-experiment gate is the frozen conjunction in
`71_FORMAL_ANALYSIS_PREREG.md`: exact paired success evidence, at least +15 pp,
no excess stale/invariant failures, and the preregistered proposal-byte locality
gate.  Passing is necessary but not sufficient for submission because this
study contains one task identity.  A tie or loss against the generic JSON-path
neutral patch triggers the assurance-framework reframe.

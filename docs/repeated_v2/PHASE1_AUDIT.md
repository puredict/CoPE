# Phase 1 audit and implementation record

Phase 1 implements the requested isolated `cope_benchmark/repeated_v2` family.
The supplied package's scientific protocol and configuration are binding;
its later-window instructions remain deferred to their respective phases.

## Repository and frozen evidence

The supplied workspace was an unborn `main` worktree with local research files.
Its existing `puredict/CoPE` Git object database contained audited revision
`84e1e742579899adb67efee92cef16efca063b31`. Work proceeded in the linked worktree
`/Users/lijingsu/Documents/cope_repeated_v2_worktree` on
`codex/repeated-v2-phase1`, starting from that exact revision. No repository was
cloned and no existing implementation, v1 config, manifest, prompt, result or
claim-decision file was changed. Final added-file status is checked before commit.

The source read set and its SHA256 digests are recorded in
[PHASE1_HASHES.txt](PHASE1_HASHES.txt). It covers README, the v1 repeated config and
runner, schema/operations/validator/replay/recovery, benchmark adapters,
interruptions/scheduler/progress/metrics/manifest/oracle controller and the frozen
167/168 research documents and experiment index. Relevant continuation bridge
`engine.py`, `goal_compiler.py`, REPAIR_INTEGRATION, final r2 simulator audit and
ReKep same-scene feasibility documents under `research/server_sync_20260905` were
also inspected; no bridge was integrated during phase 1.

The frozen v3 result is a CoPE/neutral 40/40 tie and NO-GO for the original
superiority claim. This implementation does not reinterpret or pool that result.
The r2 controlled audit likewise reports ties against strong FSR-PC and cannot
stand in for learned VLA evidence.

## Audit findings and resulting boundaries

- V1 expands interruption count into separately keyed episodes and uses fixed
  policy-step triggers. V2 has one master schedule and continuous prefix
  checkpoints, semantic conditions/windows, spacing and physical guards.
- V1 task-progress definitions cover only IDs 0,1,4,8. V2 enumerates all ten
  official LIBERO-10 task identities and preserves unresolved fields explicitly.
- The old calibration uses a different seed scheme. It cannot establish the
  frozen v2 clean rate on seeds 101/131.
- V1 includes DEMOTED lifecycle and mutation-style Revalidate. V2 separates
  lifecycle, grounding validity and satisfaction; revalidation certifies a guard.
- Old benchmark injection mutates benchmark constraint state. V2 injection is a
  pure preparation/completion interface with no arm-state capability. A later
  bridge may apply the world intervention; it must supply fresh post-event
  observations without consuming unrecorded steps.
- The existing oracle controller uses privileged simulator geometry. It remains
  restricted to controlled qualification, never the learned policy substrate.
- Existing formal-recovery cell validation accepts only event indices 1/2;
  later v2 journaling must implement its own continuous-event namespace.
- Existing repair compilation derives requirements from old state/world inputs.
  Later integration must use accepted method state and a representation-neutral
  public context without filling baseline omissions from hidden truth.

## Delivered phase-1 behavior

Strict immutable Python records and seven JSON schemas cover public/hidden
events, commitment occurrences, persistent state, execution context and planning
problems. Canonical JSON/SHA256 rejects malformed and nonfinite input. Trusted
allocation distinguishes fresh reissue from restoration and retains exact known
retired identities. Public projection and recursive leakage guards keep hidden
effects and expected operator/occurrence labels out of agent event inputs.

The scheduler uses deterministic, balanced, constrained topological shuffles.
Both temporary pairs, a grounding event, preference, retirement and reissue fill
each eight-event master. All prefixes are legal; a failure remains a failure
rather than resetting the arm. Fresh revalidation is a post-event evidence
obligation, never an automatic consequence of an availability message.

Task calibration is offline evidence ingestion/validation. It rejects incomplete
or duplicated grids, overlapping or wrong seeds, known fake policy identities,
privileged policies, changed horizons and method-performance selection fields.
Catalog selection admits all eligible tasks and blocks below eight or on any
unresolved catalog evidence. No policy is executed by these tools.

Manifest construction has exact full-grid and row/hash validation. It separates
master sessions, protocol/condition/method trajectories, scheduled event cells
and checkpoint records. No K-specific reset is represented. Artifact writers
refuse overwrites. CLI command paths and counts are documented in the
[runbook](../REPEATED_INTERRUPTIONS_V2_RUNBOOK.md).

## Catalog and readiness result

The source-backed catalog contains all ten tasks, official pinned LIBERO BDDL
source references/digests, and previously recorded initial-state hashes only
for tasks 1,5,7. Source initial placement ranges are not certified intervention
poses. There are no v2 calibration records and no measured v2 feasibility passes.
All 794 detailed gaps remain visible. Selected/frozen eligible task IDs: none.

Production preflight therefore returns `BLOCKED_TASK_CATALOG_GAPS`, produces no
formal master manifest and makes zero provider/VLA calls. Its boundary/schema/
occurrence checks pass; catalog and readiness checks correctly fail. Two separate
CLI executions produced identical bytes, SHA256
`30f00f1aec721e0048711b1153b9d9cd1f024b66554a3bb5e08a0e3c248461ec`.
The complete report is [PHASE1_PREFLIGHT.txt](PHASE1_PREFLIGHT.txt).
Synthetic eligible catalogs used by tests cannot pass formal entrypoints.

Config canonical SHA256:
`ab04ad1f021320b6458a57ce583e9fba70d119902ec465c907498ca8ffe37267`.
Task-catalog canonical SHA256:
`17fca504156fa9aa52303cc1aa8a8c8df129863d14a36463318dc03c318306ff`.
Schema file hashes are in the hash record. Prompt hashes, production provider/VLA
identities, formal manifest hash, formal results and runtime claims do not exist
in phase 1. Their absence is intentional and not represented as success.

## Validation environment

The unchanged baseline passed all 637 tests in the existing Linux environment
using `/home/lijingsu/vla/.venv/bin/python`. The local Mac initially passed 636
and failed the old authorization test requiring absolute Linux LIBERO assets.
That test was not skipped, weakened or rewritten: the complete suite runs in an
isolated linked server worktree with the required hash-pinned assets.

Final combined and phase-1-only test transcripts are preserved under
`research/repeated_v2_phase1_validation/`. All verification is CPU-only; no
training, checkpoint download, production provider call, VLA inference or
formal experiment was performed. No GPU was used.

The final combined Linux suite passed **808 tests** (637 existing + 171 new) in
121.10 seconds. A collection-only integration failure was fixed by making the
new test directory a package, avoiding collision with legacy `test_schema.py`.
The original failure transcript is retained; the successful gate transcript is
`full_suite_verified.txt`. The phase-1-only transcript is
`phase1_suite_verified.txt`.

# Full-state validator adversarial coverage audit

Date: 2026-08-01 (Asia/Shanghai)
Scope: deterministic canary audit only; this is not an embodied success claim.

## Decision

**NO-GO for a formal CoPE–FSR-PC comparison with the current validator.**

The canary validator met the expected decision in 9 of 16 adversarial/control
cases. It correctly handled schema, state revision, authorization, duplicate
identity, lifecycle, supersession lineage, and current-goal checks. It also kept
the shared compiled controller prompt unchanged when a malicious diagnostic
prompt was supplied, so prompt isolation passed.

Seven malformed full-state outputs were nevertheless accepted:

1. missing progress ledger;
2. false progress ledger;
3. missing plan;
4. plan names the wrong object;
5. missing entity state;
6. stale evidence version;
7. missing evidence versions.

These are not cosmetic schema omissions. They permit a baseline to claim a
coherent persistent state while losing or fabricating completed progress,
changing plan semantics, omitting relevant entities, or grounding its answer in
stale/unversioned evidence. Such outputs would receive a weaker acceptance test
than CoPE and would make the comparison uninterpretable.

## Required gate before embodied FSR-PC testing

The neutral validator must additionally enforce:

- progress-ledger presence and consistency with witnessed physical facts;
- plan presence, target-object continuity, and consistency with the authorized
  post-event goal;
- closure over all task-relevant entities;
- evidence-version presence, freshness, and monotonicity;
- identical validation and neutral compilation paths for CoPE and FSR-PC.

After these checks pass, the remaining P0 readiness gates still apply: a real
FSR-PC provider, a semantic-replacement manifest/runner, and a shared neutral
prompt compiler. Until then, running an end-to-end number would be a staged
controller experiment mislabeled as a baseline comparison.

## Evidence

- Case-level decisions: `14_FULL_STATE_VALIDATOR_COVERAGE.csv`
- Audit program: `tools/audit_full_state_validator_coverage.py`
- Broader readiness audit: `05_FSR_PC_READINESS_AUDIT.md`

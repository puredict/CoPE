# Autonomous CoPE experiment session: final handoff

Date: 2026-08-03 (Asia/Shanghai)

## Bottom line

The five-project infrastructure is now consolidated and the privileged physical
substrate is qualified, but the ICRA method claim is still **not submission-
supported** because the decisive matched real-model generation experiment has
zero provider calls. Reserved LIBERO states 27--49 were intentionally not
spent. This is a scientific NO-GO, not an implementation failure.

## Clean formal branch

- remote worktree: `/home/lijingsu/codex-worktrees/cope-formal-integration`
- branch: `codex/cope-formal-integration`
- evidence HEAD immediately before this memo: `8f658cd00a3723b9146156d97587c380dabbc7ae`
- final porcelain: clean
- final regression: 445 passed in 47.57 seconds

The branch integrates the corrected live semantic runner, OpenAI-compatible
matched provider adapter, CoPE/compact-TX/FSR-PC native outputs, TX-EXEC+,
privileged controller qualification, typed-assurance falsifiers, decomposed
validator and all new experiments/results.

## Completed evidence

1. P5 privileged controller/mechanism qualification: PASS, 75 assigned
   episodes, zero pre-event failures and 35/35 paired provenance groups.
2. X18 random validator differential fuzzing: initial FAIL with 24 decomposed
   false accepts; root cause retained. Scoped structural fix added. Observed
   seed then reached 3,000/3,000 parity and unseen holdout reached 2,992/2,992
   parity over changed candidates. Full regression stayed green.
3. X19 actual provider-visible UTF-8 accounting: CoPE request plus canonical
   proposal was smallest in 12/12 cases; 61,019 total bytes versus 73,443 for
   compact TX and 73,133 for FSR-PC.
4. X20 prompt-overhead sensitivity: CoPE retained the smallest corpus total
   when contracts were sent every call, hypothetically cached once, or excluded.
   Proposal-only per-case minima were CoPE 8/12, compact TX 4/12, FSR-PC 0/12.
5. Formal readiness v2: NO-GO retained because real learned semantic generation
   and true-clean external runtime provenance do not pass.

## Claims after self-falsification

Supported narrowly:

- sparse commitment edits reduce corpus-total serialized context/output bytes
  on the frozen synthetic cases;
- the live semantic and privileged controller mechanisms can preserve progress;
- the repaired decomposed validator matches the exact validator on the retained
  hand-designed and seeded mutation distributions.

Not supported:

- unique CoPE expressivity or atomicity over generic transactions;
- typing-specific fail-closed behavior under matched canonical guards;
- universal efficiency at dense edits;
- learned generation advantage;
- embodied learned recovery superiority;
- ICRA method-paper readiness.

## Only critical next experiment

Run frozen X13 with a capable real instruction model: CoPE typed patch versus
compact generic transaction versus FSR-PC full state, same input/model/seed and
zero repair. The four-triplet smoke precedes the 12-triplet pilot. Only a usable
semantic-valid ceiling unlocks a larger paired corpus; only that result plus a
regenerated true-clean provenance PASS unlocks states 27--46. States 47--49 stay
reserved.

The hosted route requires `OPENROUTER_API_KEY` (or an explicitly approved
equivalent provider). A local Qwen2.5-0.5B diagnostic was preregistered but not
run: the nontrivial checkpoint download required explicit authorization and
cannot replace X13. The interrupted partial file remains under
`/private/tmp/qwen2.5-0.5b-instruct/model.safetensors` and is not part of the
project or evidence.

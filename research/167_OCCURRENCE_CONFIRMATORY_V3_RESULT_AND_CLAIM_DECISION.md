# Occurrence confirmation v3 result and claim decision

Date: 2026-08-04

## Bottom line

The held-out, contract-complete v3 run is valid and the original superiority
claim is a **NO-GO**.

CoPE and the method-neutral JSON transaction both achieved 40/40 strict
first-draw successes. Therefore CoPE did not improve recovery reliability over
the fair neutral primary control (paired risk difference 0.00; efficacy
p=1.00). CoPE was smaller on all 40 valid pairs, with median relative proposal
byte reduction 0.8403, but the preregistered primary gate required both
efficacy and locality. Compactness cannot rescue an efficacy tie.

This result does not reject persistent commitment editing as a broad design
principle. It rejects the narrower claim that the present CoPE carrier is more
first-draw reliable than a fully specified generic transaction on this task.

## Run validity

- Frozen runtime commit: `3705cf18e75d74d39ffc9b8dc1793c584fe6058c`.
- Manifest: 40 held-out cases, 10 triples x depths 1--4, disjoint object names.
- Cells: 200/200 calls, 200 responses, 200 journal entries, 200 result rows.
- Retries: 0. Infrastructure stops: 0. Simulator states indexed: 0.
- Cold preflight: 200 oracle cells, 0 provider calls, common-input matching pass.
- Related tests before launch: 43 passed.
- Frozen strict analyzer was used without response repair or case deletion.

## Strict results

| Arm | Complete success | Difference from CoPE | Paired efficacy result |
|---|---:|---:|---:|
| CoPE | 40/40 | -- | -- |
| Neutral transaction | 40/40 | 0.0 pp | p=1.00; primary gate fail |
| Governed delta | 0/40 | -100.0 pp | Holm p=3.64e-12; locality unavailable; primary gate fail |
| FSR-PC | 31/40 | -22.5 pp | Holm p=0.0078; secondary only |
| Full replan | 37/40 | -7.5 pp | Holm p=0.25; secondary only |

Frozen claim status:
`NO_GO_PRIMARY_NEUTRAL_COMPARISON`; `joint_primary_gate=false`.

## Efficiency result

CoPE averaged 272 proposal bytes, 117 completion tokens, and 1.24 seconds.
The neutral transaction averaged 1,711 bytes, 790 completion tokens, and 4.70
seconds. Thus CoPE used about one sixth of the proposal bytes and one seventh
of the completion tokens, and returned about 3.8 times faster in this model
and provider setting. The analyzer's paired median byte reduction was 84.03%,
and CoPE was smaller in every one of 40 valid neutral pairs.

These are strong interface-efficiency observations, not a preregistered
noninferiority claim and not yet a cross-model systems result. Prompt-token
counts also differ because richer output schemas require longer contracts.

## Failure audit

### Neutral transaction

All 40 outputs materialized to the exact same canonical post-state as CoPE.
The v2 path failure was therefore a contract ambiguity, not a limitation of
generic state editing. V1's 40-vs-0 neutral result must not be used as evidence
of method superiority.

### Governed delta

All 40 strict outputs failed semantics. The first observed check frequently
failed because the model returned target then replacement instead of
lexicographic order. A read-only sort-only diagnostic recovered just 2/40, so
this was not only ordering: affected scope was exact in 13/40, forest delta in
15/40, and blackboard delta in 2/40. The governed carrier remained difficult
for this model, but its failure cannot override the neutral tie.

### FSR-PC and full replan

FSR-PC's current goal, entities, progress ledger, plan, and restorations were
all exact in 40/40; its nine failures were confined to commitment-history
records. Full replan got every field except the complete retired-occurrence
list exact in 40/40; three retired-history lists were wrong. These patterns do
support the claim that persistent history is the difficult part, but the full
replan success gap was small and nonsignificant in this symbolic task.

## What the three runs now say

| Run | CoPE | Neutral | Governed | FSR-PC | Full replan | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| v1 frozen | 40 | 0 | 0 | 8 | 0 | Large apparent advantage, contract-confounded |
| v2 exploratory | 40 | 0 | 12 | 30 | 13 | Contract detail changes outcomes; neutral still path-ambiguous |
| v3 held-out | 40 | 40 | 0 | 31 | 37 | Fair neutral control closes the reliability gap |

The defensible conclusion is that v1 overstated CoPE's learned reliability
advantage. The surviving empirical signal is compact, fast communication of an
occurrence-addressed edit, plus exact fail-closed execution machinery already
tested elsewhere in the project.

## Submission decision

The current evidence is not sufficient for an ICRA method-paper claim that
CoPE improves recovery success over fair generic editing or full replanning.
Submitting that claim now would be vulnerable to a straightforward reviewer
rebuttal using v3.

A publishable pivot remains possible without changing the fixed core idea:

> Persistent commitment editing can match a complete generic transaction while
> using a much smaller learned output interface, and typed validation preserves
> occurrence history under interruptions.

That pivot requires two new pieces of evidence before embodied launch:

1. A preregistered, multi-model noninferiority-and-efficiency replication,
   with neutral transaction as the primary control and success noninferiority
   plus token/latency savings as co-primary outcomes.
2. An execution-level long-horizon test showing that commitment editing avoids
   completed-step regression, history corruption, or extra actions under
   repeated interruptions. The comparison must include the now-strong neutral
   transaction and full replan, not only FSR-PC.

The failed superiority gate remains immutable. A new experiment may support a
new efficiency/noninferiority claim; it must not be described as rescuing v1.

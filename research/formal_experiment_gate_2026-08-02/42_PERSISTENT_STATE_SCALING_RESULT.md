# Persistent-state scaling experiment result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS.** On the preregistered largest-state primary endpoint, sparse CoPE
commitment editing was correct on 36/36 cases versus 7/36 for complete semantic
state regeneration under the original strict array-order scorer. The paired
discordance was 29--0 and the two-sided exact p-value was
`3.725290298461914e-09`.

After completion, an order-sensitivity audit found one size-16 and one size-32
FSR response that differed only in where a newly inserted stable-ID record
appeared in an array. Stable-ID collections are semantically unordered, but
duplicate IDs must remain invalid. Under the corrected order-insensitive,
duplicate-rejecting scorer, the largest-state result is CoPE 36/36 versus FSR
8/36, discordance 28--0, exact `p=7.450580596923828e-09`. The decision remains
PASS. Raw responses and original result files were not modified.

## Run integrity

- 108 cases, four arms, 432/432 planned calls retained;
- 432/432 provider-OK and strict-schema-valid responses;
- 108/108 fair four-arm groups with byte-identical common input and normalized
  request audits;
- zero retry, repair, fallback, oracle substitution, or model-generated
  transaction metadata;
- no GPU, simulator, controller, development LIBERO state, or reserved state;
- secret scan clean;
- frozen runtime commit `fa2e6b2b57af828011245303d5273f729e5a4985`;
- immutable result commit `0aa7547de164027b765a84b9dae5119a33a612ba`;
- corrected semantic comparator commit
  `008dde59b9ca7edc6569a7b154414f3b344e631b`;
- 20 shared-envelope, holdout, and scaling tests pass.

## Corrected semantic accuracy by persistent-state size

| Commitments | CoPE typed edit | Neutral typed | Compact transaction | Full-state regeneration |
|---:|---:|---:|---:|---:|
| 4 | 35/36 | 34/36 | 32/36 | 30/36 |
| 16 | 36/36 | 34/36 | 33/36 | 13/36 |
| 32 | 36/36 | 34/36 | 33/36 | 8/36 |

CoPE-versus-compact at size 32 was 3--0 (`p=0.25`) and CoPE-versus-neutral was
2--0 (`p=0.5`). Therefore this experiment supports sparse editing over complete
regeneration as state grows; it does **not** establish that CoPE's operation
names outperform every other sparse representation.

## Output and latency scaling

CoPE completion tokens remained approximately constant across the three
strata: 6,866, 6,891, and 6,891 total tokens for 36 cases. FSR grew from 26,421
to 111,982 and 191,787 tokens. Total FSR latency grew from 148.0 to 576.1 and
996.9 seconds; CoPE remained 56.2, 66.0, and 68.4 seconds.

All arms had the same 16,384 completion-token ceiling in this experiment and
all FSR outputs were schema-valid, so the accuracy collapse is not explained by
truncation or parser rejection. The larger required FSR output is an intrinsic
consequence of regenerating the complete persistent state and is part of the
mechanism under test.

## FSR failure attribution

After order normalization and duplicate rejection:

| Commitments | Incorrect | Preservation drift | Preservation only | Transition + preservation | Duplicate ID |
|---:|---:|---:|---:|---:|---:|
| 4 | 6 | 5 | 5 | 0 | 1 |
| 16 | 23 | 23 | 22 | 1 | 0 |
| 32 | 28 | 27 | 26 | 1 | 1 |

Thus 27 of 28 large-state FSR errors contained changes to information outside
the required sparse transition; 26 were preservation-only errors. The remaining
case emitted a duplicate action ID. This is the predicted failure mode of
complete regeneration: unchanged persistent commitments are rewritten or lost
as state grows.

## Scientific scope and next gate

This is strong evidence for the core mechanism on a controlled
representation-fidelity benchmark. It is not yet evidence of end-to-end robot
success, policy induction, or broad natural-language generalization: the 36
transition families were previously audited, and the new factor was state scale.

The next admissible step is a development-only embodied Phase-A canary that
binds a real live predicate packet to the shared commit envelope and emits zero
actions. Reserved states 27--49 remain locked. Formal embodied promotion still
requires the canary and cold-rebuild runtime gate.

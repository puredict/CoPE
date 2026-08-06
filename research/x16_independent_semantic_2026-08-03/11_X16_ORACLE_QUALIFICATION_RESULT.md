# X16 oracle qualification result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS for corpus/oracle/transport qualification.** This is not a learned-model
result and does not itself authorize an OpenRouter call.

- 36 independent semantic templates; 36 unique normalized logic signatures;
- 108/108 canonical arm proposals materialized to the frozen oracle state;
- 108/108 canonical arm proposals were accepted by the frozen common validator;
- 108/108 triplet cells passed common-input and normalized-request fairness;
- 108/108 passed the hidden-answer-key scan;
- 108/108 passed the no-arm-specific-information check;
- maximum canonical common-input size was 7,250 UTF-8 bytes, leaving a large
  conservative margin under the 16,000-token prompt ceiling even before normal
  tokenizer compression;
- CoPE, compact TX, and FSR-PC each occupy positions 1, 2, and 3 exactly 12
  times under seed 20260803;
- 17 required primary families each contain exactly two templates; two
  additional compound atomic templates are included;
- oracle dispositions: 22 APPLY, 4 NO_OP, 6 REJECT, 4 ABSTAIN;
- zero provider calls, GPU use, simulator use, or reserved-state reads.

## What was qualified

For APPLY, the typed CoPE patch and generic compact transaction were independently
materialized from the pre-state, while FSR-PC supplied the complete state. Their
canonical state hashes matched each other and the oracle. For NO_OP, REJECT,
and ABSTAIN, the sparse arms contained no mutation and FSR-PC reproduced the
pre-state exactly. All arms also matched the frozen disposition, reason code,
event ID, and base version.

Fairness qualification hashes the exact common input independently of the arm
contract and hashes normalized requests after replacing only the final output
contract with a shared placeholder. The three normalized hashes matched for
every template. The provider-visible common input was recursively scanned for
oracle-only keys such as `post_state`, `operations`, `writes`, `disposition`,
`reason_code`, `expected`, and `answer`; none occurred.

## Limitations

The validator proves that the three languages can encode the same frozen
decision and state. It does not prove that the task policies are ecologically
representative, that a model can infer the oracle, or that the 36 templates
sample a well-defined real-world population at random. Statistical inference
is conditional on this deliberately constructed independent-template corpus.

Machine-readable details are in `05_X16_ORACLE_QUALIFICATION.csv`; the direct
run status is `08_X16_QUALIFICATION_STATUS.txt`.

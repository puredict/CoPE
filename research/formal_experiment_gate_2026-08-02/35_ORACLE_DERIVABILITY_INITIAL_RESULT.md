# X16/X17 oracle-derivability initial result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**FAIL: the current X16 corpus is not admissible for another confirmatory
representation comparison without revising the provider-visible transition
contract.**

All 22 APPLY templates modify the same three transaction-metadata roots:

- `state_version`: 22/22;
- `evidence_version`: 22/22;
- `processed_events`: 22/22.

The oracle stores `payload_sha256 = SHA256(canonical_event)` in the new
processed-event record. The common provider-visible semantic contract does not
define this canonicalization/hash rule or a complete common commit algorithm.

The representation contracts distribute this responsibility unequally:

- CoPE emits one `CommitEvent` macro; trusted code increments versions and
  computes/appends the event record and hash;
- compact TX must explicitly emit version, evidence and processed-event writes;
- FSR-PC must reproduce all three fields inside the complete state.

Thus the experiment mixes semantic recovery representation with responsibility
for deterministic transaction bookkeeping. This is a genuine factorization
cost if explicitly studied, but it is not a fair basis for claiming that CoPE
understands recovery semantics better than an equally sparse generic
transaction.

## Other oracle deltas

Across the 22 APPLY cases, the changed roots were:

| Root | Cases changed |
|---|---:|
| commitments | 22 |
| actions | 7 |
| restorations | 7 |
| facts | 3 |
| progress | 2 |

X17 error inspection shows that several task-policy sentences licensed the
headline commitment transition but did not enumerate every expected action,
progress, restoration, and bookkeeping consequence. For example, a model could
correctly cancel a root and block transitive descendants yet fail because the
oracle also expected action-state changes and transaction history updates.

These atoms require a full per-case clause mapping under the preregistered
oracle-derivability audit. Until that mapping passes, low model accuracy cannot
be cleanly attributed to model incapability or representation choice.

## Consequence

X16 remains a valid negative result under its frozen contract: it did not show
CoPE superiority. X17 remains a valid failed development qualification. Neither
may be repaired retrospectively.

Future experiments must separate:

1. semantic delta generation;
2. trusted deterministic transaction metadata;
3. output representation size/factorization;
4. end-to-end embodied execution.

No additional provider run or reserved-state rollout is authorized until this
separation is implemented and qualified on new development cases.

# Matched valid-arm development expansion result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS. Formal protocol preparation is unlocked; formal states are not yet
consumed by this result.**

The run used development states 1--4 only, after the separately retained state-0
gate. Raw outputs are immutable at commit
`eb7b585671187c94f3a70276a981506050592f29`.

## Preregistered checks

| Check | Result |
|---|---:|
| Provider calls OK / assigned | 32 / 32 |
| Retry, repair, fallback, oracle substitution | 0 / 0 / 0 / 0 |
| CoPE semantic correctness | 8 / 8 |
| Neutral sparse semantic correctness | 8 / 8 |
| Corrected compact semantic correctness | 0 / 8 |
| Metadata-free FSR-PC semantic correctness | 0 / 8 |
| Valid embodied cells terminal-successful | 16 / 16 |
| Invalid cells fail-closed with zero actions | 16 / 16 |
| Cancellation valid-cell actions | 0 |
| Matched replacement trace pairs identical | 4 / 4 |
| Reserved states consumed | 0 |

The replacement action count and SHA-256 were identical between CoPE and the
neutral sparse interface in every state: 187, 185, 192 and 188 actions for
states 1--4 respectively. Prefix state, action and stability hashes were also
identical across all four arms within each case. CoPE and neutral response
hashes differed, so the matching post-state and physical trace did not arise by
reusing one arm's generated response.

## Independent audit and retained defect

An independent CSV/journal audit recomputed all preregistered conditions as
true. No credential prefix occurred in the experiment directory, runtime log or
tracked repository.

The audit also found eight blank `shared_envelope_pass` fields in the neutral
embodied rows. This does not fail the frozen protocol: the corresponding
per-arm semantic rows record the shared-envelope pass, and every neutral row
records matched-prefix and terminal success. The raw CSV remains unchanged.
The serializer was corrected for all valid and invalid arms, permanent-reserve
locks were added, and 32 focused plus 491 full tests passed at implementation
commit `8ae5949bc853815e007e576530dd33d58beb8e15`.

The no-credential formal preflight at commit
`09bd383802ac39c857bae2de987af70c29248f84` produced zero provider calls,
zero actions and an empty indexed-state list.

## Interpretation and claim boundary

This supports a sparse persistent-commitment edit family, not an advantage from
the words `Override` or `Expire`: the neutral labels reproduce CoPE exactly.
Compact and FSR-PC failures are retained generation failures and were not
repaired. Low-level execution remains a privileged simulator-geometry oracle,
so this is evidence about high-level commitment recovery, not a learned
visuomotor controller.

States 27--46 may be consumed only under the next explicit preregistration.
States 47--49 remain permanent reserve.

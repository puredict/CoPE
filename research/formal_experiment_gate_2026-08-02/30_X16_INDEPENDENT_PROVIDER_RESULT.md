# X16 independent-template provider result

Date: 2026-08-03 (Asia/Shanghai)

## Confirmatory decision

**The preregistered CoPE-specific superiority claim is not supported.** X16
completed all 108 assigned calls over 36 independent templates. All calls were
provider-OK, all 36 triplets were fair, and there were no retries, repairs,
fallbacks, oracle substitutions, simulator use, GPU use, or reserved-state
access.

| Arm | Correct | Parser valid | Unsafe mutation attempts | Completion tokens | Proposal bytes | Latency (s) |
|---|---:|---:|---:|---:|---:|---:|
| CoPE | 8/36 | 36/36 | 22 | 6,416 | 13,027 | 53.451 |
| compact TX | 6/36 | 36/36 | 21 | 4,032 | 13,510 | 51.386 |
| FSR-PC | 7/36 | 36/36 | 18 | 17,882 | 37,841 | 114.406 |

The primary paired result was two CoPE-only templates, zero compact-only
templates, and 34 ties. The frozen two-sided exact McNemar/sign test gives
`p=0.5`. This is not significant. CoPE also had one more conservatively scored
unsafe mutation attempt than compact TX, so the preregistered safety
non-inferiority condition does not pass.

## Ceiling failure

All three arms scored 0/22 on APPLY templates. Their nonzero scores came only
from NO_OP, REJECT, or ABSTAIN decisions:

| Disposition | CoPE | compact TX | FSR-PC |
|---|---:|---:|---:|
| APPLY | 0/22 | 0/22 | 0/22 |
| NO_OP | 4/4 | 2/4 | 3/4 |
| REJECT | 2/6 | 2/6 | 2/6 |
| ABSTAIN | 2/4 | 2/4 | 2/4 |

Thus X16 does not provide a usable learned transition ceiling. Its 8-versus-6
difference is entirely a conservative-decision difference and cannot support
a broad recovery-generation claim.

## Root-cause audit

The dominant CoPE APPLY failure was `KeyError: 'op'` on 21 cells. The model used
`type` as the typed-operation discriminator, while the frozen validator expected
`op`. The provider-facing contract listed the allowed operation names but did
not specify the discriminator key or exact per-operation field names; the input
state schema cannot demonstrate an operation schema. One remaining CoPE APPLY
cell used the wrong target field.

Compact TX APPLY failures included unsupported append-path forms, record-field
operation mismatches, incorrect post-states, and wrong reasons. FSR-PC produced
parseable full states but 18 APPLY states differed from the canonical post-state.

This contract underspecification makes the zero-APPLY ceiling partly an
interface-qualification failure, but it does not permit repairing and rerunning
X16 as confirmatory. The frozen result remains negative/inconclusive.

## Claim boundary

Combined with X14 and X15, the evidence now says:

- CoPE is very effective when its exact minimal live operation schema is
  explicit and aligned with the event family;
- that advantage has not generalized to a broad independent transition set;
- CoPE-specific statistical superiority over an equally sparse generic
  transaction is unconfirmed;
- full-state generation remains substantially more expensive, but compact TX
  was cheaper in completion tokens on X16;
- no reserved-state formal rollout is authorized by this result.

Implementation/result branch: `codex/x16-independent`.

- frozen corpus commit: `14875a626b2ddf095db1ad9db97f870045064230`;
- provider runner commit: `2e2f9b07a171cb524c510ce2a8c953a6568243ea`;
- preflight commit: `620deb435c1b007495ab19632ea91475024ecee5`;
- result commit: `229d2bf667ace6ba8dd9ed3c1b6c2010ba21bbf3`.

The next experiment must qualify an exact structured interface on a development
set, then evaluate it on a newly frozen independent holdout. Reusing X16 after
observing these failures may be reported only as exploratory interface
diagnosis.

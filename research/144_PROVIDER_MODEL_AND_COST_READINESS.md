# Provider model and cost readiness

Date: 2026-08-04
Source: `https://openrouter.ai/api/v1/models`

## Decision

**PASS at audit time.** The exact frozen model ID
`qwen/qwen3.5-flash-02-23` appears once in OpenRouter's public model catalog.
This check made no completion request and used no credential.

## Public catalog evidence

- HTTP status: 200;
- catalog entries: 338;
- exact target matches: 1;
- advertised context length: 1,000,000;
- advertised maximum completion tokens: 65,536;
- required parameters advertised as supported: `reasoning`,
  `response_format`, `seed`, `temperature`, and `max_tokens`;
- frozen request maxima, 12,000 prompt tokens and 4,096 completion tokens,
  fit within the advertised limits.

The public price fields at audit time were `0.000000065` per prompt token and
`0.00000026` per completion token. Under the deliberately unrealistic ceiling
where every one of 601 possible calls (one smoke, 200 occurrence, 400 embodied)
uses both frozen token maxima, the arithmetic upper bound is:

- prompt: `601 * 12,000 * 0.000000065 = $0.46878`;
- completion: `601 * 4,096 * 0.00000026 = $0.64004096`;
- combined: **$1.10882096**.

Actual billing can differ if OpenRouter pricing, routing, accounting, or model
availability changes. Re-read the public catalog immediately before secure
launch; do not modify the frozen model or protocol after seeing a smoke or
formal outcome. A catalog disappearance is a new external blocker requiring a
fresh preregistration, not permission to substitute a model silently.

## Scope

Catalog presence proves configuration plausibility, not provider-call health.
Only the one-draw operational smoke can establish the authenticated adapter
path. Current live status therefore remains `BLOCKED_CREDENTIAL_UNAVAILABLE`.

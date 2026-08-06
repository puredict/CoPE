# Provider availability and bounded-cost snapshot

Date: 2026-08-04

The public OpenRouter model catalog was queried immediately before formal-run
authorization.  Model `qwen/qwen3.5-flash-02-23` is present, advertises a
1,000,000-token context window, and supports `response_format`, `seed`,
`temperature`, `reasoning`, and `max_tokens`, which are the frozen request
parameters used by the runner.

Catalog pricing at the snapshot was:

- prompt: `$0.000000065` per token;
- completion: `$0.00000026` per token.

The corrected cold preflight constructed 320 requests totaling 1,737,600 wire
bytes (5,079--5,894 bytes per request; mean 5,430).  Token usage is measured
from actual provider receipts rather than inferred from bytes.  Even the loose
configured ceiling of 12,000 prompt and 4,096 completion tokens for every
scheduled call implies an upper price bound of roughly `$0.59` at the catalog
snapshot; dependency skips can only reduce it.  This is a cost bound, not a
promise of provider availability or billing behavior.

Source endpoint: `https://openrouter.ai/api/v1/models`.

No credential was sent and no provider call was made while producing this
snapshot.

# Formal CSV-to-journal binding audit

Date: 2026-08-04

## Decision

**Critical integrity gap closed.** Both locked formal analyzers now refuse to
analyze a result CSV unless it is an exact field-for-field rendering of the
colocated crash-safe event journal and the colocated run metadata carries the
frozen manifest hash.

## Gap

The runner durably journals every result before exporting
`03_EVENT_RESULTS.csv`, but the analyzers previously read only the CSV. Hash
shape and semantic-coherence checks could catch many corruptions, yet a
post-run edit to a control success flag could preserve all recorded hashes and
change the statistical verdict.

## Binding rule

Before any efficacy or locality calculation, the shared validator now:

1. requires `00_RUN_METADATA.txt`, `01_EVENT_JOURNAL.txt`, call-intent journal,
   and provider-response journal beside the CSV;
2. requires the metadata manifest SHA-256 to equal the frozen analyzer value;
3. rejects a torn or invalid JSONL journal line;
4. requires the exact result schema in every CSV and journal record;
5. rejects duplicate or nonmatching cell sets;
6. renders each typed journal value using the CSV writer's representation and
   requires exact equality for every field of every cell.
7. reopens the formal recovery ledger and requires every called result to have
   its durable intent and response, except an explicitly ambiguous consumed
   call, which must have intent and no response.

This applies to the 200-cell occurrence formal and 400-cell embodied v2
formal. A detached or hand-edited CSV is no longer analyzable.

## Verification

- direct binding tests cover valid rendering, one-field CSV/journal drift,
  manifest mismatch, torn journal, and a called result with no intent/response;
- occurrence adversarial analyzer tests still pass;
- embodied-v2 adversarial analyzer tests still pass;
- combined focused result: 27 passed;
- provider calls: 0;
- simulator states indexed: 0.

## Scope

This binds the published CSV to the runner's durable result journal. It does
not provide cryptographic authenticity against a malicious actor who rewrites
the metadata, journal, and CSV together. Repository commit pinning, restricted
write access, raw provider-response hashes, and artifact preservation remain
separate provenance controls.

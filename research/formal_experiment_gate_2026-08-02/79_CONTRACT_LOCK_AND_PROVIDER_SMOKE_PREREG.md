# Contract lock and live-provider development smoke preregistration

Date: 2026-08-04

The formal manifest locks cases and model configuration but does not itself
contain arm prompt text.  Companion manifest
`manifests/sequential_formal_contract_hashes_v1.csv` therefore freezes the
SHA-256 of all four output contracts.  The formal runner must reject any hash
drift before credential use or state indexing.

Before the 320-call embodied run, execute a development-only live-provider
smoke on the four corrected symbolic cases (forward/reverse crossed with
cancel/double-replace), four arms, and two sequential events: 32 scheduled
calls maximum.  Event 2 consumes the accepted event-1 state; it is dependency-
skipped if event 1 fails.  There are zero retries and no simulator access.

The smoke is diagnostic and may motivate prompt/interface repair because it
uses no formal state.  After any repair, issue a new versioned contract hash
manifest and repeat the oracle gate, cold preflight, and live smoke.  Formal
calls are authorized only when every arm has at least one fully successful
sequence of each event type and there is no common transport/configuration
failure.  Smoke outcomes are not paper results.

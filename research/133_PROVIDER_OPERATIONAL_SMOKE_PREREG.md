# Provider operational smoke preregistration

Date: 2026-08-04  
Status: frozen before the smoke call

## Purpose

Validate credential injection, endpoint reachability, selected model
availability, deterministic request fields, JSON-object mode, usage parsing,
and the zero-retry adapter without observing an occurrence-task arm outcome.

## Fixed call

- provider: OpenRouter OpenAI-compatible chat endpoint;
- model/settings: exactly the frozen occurrence formal protocol;
- one call, zero retries, 90-second timeout;
- task-independent RecoveryInput whose public payload asks only for an adapter
  readiness acknowledgement;
- output contract: exactly one JSON object with exactly
  `{"status":"ready"}` and no prose;
- no simulator or occurrence formal manifest case;
- persist the redacted request hash, raw-response hash, usage, latency, parser
  status, retry count, and failure class; never persist the credential.

## Gate

PASS requires one provider call, zero retries, non-timeout HTTP success, valid
JSON, exact acknowledgement, nonempty response hash, and no credential in any
artifact. Any failure blocks formal execution. The smoke contract and prompt
are not changed after failure; no retry is allowed without a new explicit
preregistration. Because the smoke does not use any experimental arm contract,
its result cannot select or tune the formal prompts.

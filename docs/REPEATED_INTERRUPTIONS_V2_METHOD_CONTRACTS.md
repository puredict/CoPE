# Repeated-interruption v2 record boundaries

The supplied [data and method contracts](repeated_v2/specification/03_DATA_AND_METHOD_CONTRACTS.md)
are retained verbatim. Phase-1 Python records live in
`cope_benchmark/repeated_v2/schema.py`; their JSON normalization lives in
`canonical.py`. The normalization sorts object keys, preserves array order,
normalizes integral floats/negative zero, emits finite UTF-8 JSON and rejects
cycles, duplicate input JSON keys and unsupported values. Its SHA256 is the
persistent identity; Python's process-local `hash()` is not used as an artifact
identity. It is explicitly not an RFC 8785 implementation.

Lifecycle, grounding validity and satisfaction are independent enums. Legacy
DEMOTED lifecycle and mutation-style Revalidate are not imported. Commitment
families and occurrences are distinct. Trusted occurrence allocation creates a
fresh ID for reissue, retains retired history and checks fresh verifier-backed
restoration without allocating an ID. Atomic proposal engines are phase 2.

Beliefs, verified progress certificates and executor continuation are separate
from the persistent ledger. Records recursively freeze input arrays/mappings and
serialize to detached primitive values. Public event payloads cannot contain
hidden effects, correct operators, expected target occurrences or fault labels.
Recursive scanning supplements typed allowlisted projection; it is not a claim
that arbitrary prose can be proven free of covert semantic leakage. Public
records must originate in the shared observation/user substrate.

`inject_event` accepts only an immutable environment-only snapshot, public
payload and hidden effect. It returns a prepared world change plus private audit
record. It has no arm, ledger, execution-context or arbitrary callback argument.
`complete_event_injection` requires a new observation version bound to the event
and unchanged policy/environment step counters. Only `method_input()` projects
the public payload and fresh observation; hidden canonical transition data stays
private for later scoring. No phase-1 simulator or canonical evaluator is invoked.

Phase-2 method prompts/parsers, information-equivalence checks, protected
projection engines and compiler must preserve these boundaries. Later-phase
runtime bridges must not pass private schedule metadata or injection records to
non-oracle methods. The existing privileged oracle controller cannot supply a
formal learned-policy run.

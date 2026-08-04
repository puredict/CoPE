# Provider envelope failure-class amendment

Date: 2026-08-04
Status: frozen before live provider/formal outcomes

## Gap

The adapter previously grouped two different failures under
`response_parse_failure`:

1. a valid provider envelope whose model content is not the required JSON;
2. an HTTP-200 body that is invalid JSON or lacks the provider
   `choices/message/content` envelope and valid usage fields.

The first is a learned method/output failure. The second is a provider protocol
or infrastructure failure and must not count against an experimental arm.

## Amendment

- invalid/missing envelope structure, nontextual content, or malformed usage is
  `provider_malformed_envelope`;
- usage token counts must be non-negative JSON integers; negative, floating,
  boolean, list, or other noncanonical values are infrastructure-invalid and
  are never coerced or charged to an arm;
- this class preserves the raw-body SHA-256, enters the infrastructure-invalid
  family, writes the first-failure stop marker, and permits no later call;
- textual model content that is not the required JSON remains
  `response_parse_failure`, preserves response/content evidence, and remains a
  method outcome;
- HTTP, timeout, transport, retry, prompt, and success behavior are unchanged.

## Verification

A mocked HTTP-200 response with no `choices` is classified
`provider_malformed_envelope`; a structurally valid response with `not-json`
content is classified `response_parse_failure`. Both retain a response hash,
and no credential is recorded.

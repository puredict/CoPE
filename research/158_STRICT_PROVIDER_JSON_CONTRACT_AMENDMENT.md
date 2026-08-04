# Strict provider JSON contract amendment

Date: 2026-08-04
Status: frozen before live provider/formal outcomes

## Gap

Every smoke/formal output contract requires exactly one JSON object and no
prose or markdown. The adapter previously attempted strict parsing first, then
fell back to extracting text between the first `{` and last `}`. A response
with explanatory prose or a markdown fence could therefore count as
parser-valid despite violating the frozen contract.

## Amendment

The adapter now applies `json.loads` to the complete stripped response content
and additionally requires the top-level value to be an object. It no longer
extracts embedded JSON.

The following are method-level `response_parse_failure` outcomes:

- prose followed by an object;
- a markdown-fenced object;
- a top-level JSON array;
- malformed JSON content.

They are not infrastructure failures and do not stop later formal cells.
Provider-envelope malformation remains the separate infrastructure class from
report 157.

## Consequence

Smoke PASS now proves the selected model obeyed the exact no-prose JSON-object
adapter contract on its one draw. Formal `parser_valid` now means exact
whole-response JSON conformance rather than recoverable JSON embedded in a
noncanonical answer. No arm is treated differently.

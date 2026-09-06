# R4 installed-server JSON Schema compatibility gate

Date: 2026-09-04 local task date / 2026-09-05 server log date.

Result: **CPU schema parsing/compilation passed; this document records the initial plain-`xgrammar` deployment and its earlier interface corrections.**
This is a CPU interface gate, not a model accuracy or physical-task result.

Subsequent CPU replay found increasing xgrammar token-mask cost despite compact output. The coordinator retained the schemas and configured plain `guidance` equally for both methods for the next controlled run. See `FSR_CPU_GRAMMAR_DIAGNOSTIC.md`, the guidance backend gate report, and the current run log for that later decision. The client now accepts explicitly configured `xgrammar` or `guidance`; all 19 interface tests pass, including default-xgrammar requests, explicit-guidance requests and telemetry, and rejection of unsupported backend settings. The xgrammar settings below are historical, not the current experiment configuration.

## Initial deployable xgrammar setting and whitespace limit

The deployed vLLM command-line parser accepts only its listed backend names and rejects colon-suffixed options, even though `DecodingConfig` and the V1 backend accept `disable-any-whitespace` in isolation. A subsequent coordinator launch exposed this entry-point restriction before GPU loading. The final setting is therefore:

```text
--guided-decoding-backend xgrammar
```

```json
{"guided_decoding_backend":"xgrammar"}
```

Both methods use the same explicit backend and compact-serialization prompt. **Arbitrary whitespace is allowed by the deployed grammar; compact output is requested in the prompt, not enforced by the grammar.** Actual text and token usage must be measured. Avoidance of whitespace inflation is not an established property of this deployment. The explicit V1 `xgrammar` path still validates without fallback to guidance.

The direct grammar checks below already passed both schemas with `any_whitespace=True`, matching this final setting. The client and 17-test interface suite now use plain `xgrammar`. No installed runtime patch or custom entry-point shim was introduced. Earlier component checks are retained as audit history and are not equivalent to successful command-line startup or live generation.

After deployment with plain `xgrammar`, the run coordinator reported that the first live CoPE development trajectory completed all seven state-update events with valid schema and correct semantics; the physical phase was still in progress at that update. Refer to the run log and episode artifacts for final physical and baseline results.

## V1 correction after the first live interface attempts

The initial gate below exercised direct xgrammar compilation and vLLM's **V0** helper. It did not cover the active server's V1 request processor or V1 backend constructor. The first four live requests were subsequently rejected before generation because the engine used `auto` while the request selected an explicit backend. Those attempts are preserved by the run coordinator and must be treated as server-interface failures, not recovery-performance results.

The follow-up audit identified two distinct V1 requirements in the installed code:

1. `vllm/v1/engine/processor.py:145` requires the request's backend string to equal the engine's backend string. An explicit engine backend starting with `xgrammar` validates directly; only `auto` can fall back to guidance.
2. `vllm/v1/structured_output/backend_xgrammar.py:44` accepts `disable-any-whitespace` but raises an error for any other option, including V0's `no-fallback`. Consequently adding `no-fallback` to the V1 engine configuration would create a second interface error.

At the component-audit stage, the proposed shared engine and client setting was the following. **The subsequent CLI restriction above superseded this proposal:**

```text
--guided-decoding-backend xgrammar:disable-any-whitespace
```

```json
{"guided_decoding_backend":"xgrammar:disable-any-whitespace"}
```

This would preserve no-fallback behavior through the explicit-xgrammar code path, without an option unsupported by the V1 backend. The temporary client/test change was subsequently replaced with plain `xgrammar` after CLI rejection. Component config validation accepts the suffixed string by checking the base backend name, and the component compiler receives `any_whitespace=False`; the deployed command-line entry point does not accept this suffixed string.

A second isolated CPU gate, with `VLLM_USE_V1=1`, executed the installed `DecodingConfig` and `Processor._validate_structured_output` for both schemas. It also instantiated the actual V1 `XgrammarBackend` with the actual existing Qwen tokenizer and compiled both schemas through `compile_grammar`. To avoid constructing an entire model-serving configuration, only the tokenizer-group acquisition was replaced in the gate process with the already-loaded tokenizer; no deployed code was changed. The backend option parser, tokenizer metadata construction, and grammar compiler were the installed implementations.

| Actual V1 check | Result |
| --- | --- |
| CoPE processor validation; exact engine/request equality | Pass |
| FSR-PC processor validation; exact engine/request equality | Pass |
| Backend constructor accepts selected options | Pass |
| `disable_any_whitespace` | `True` |
| CoPE actual V1 `compile_grammar` | Pass, 0.214 s |
| FSR-PC actual V1 `compile_grammar` | Pass, 0.313 s |

The gate ended with `V1_PROCESSOR_BACKEND_GATE_PASS`, exit code zero. This expanded the CPU gate to V1 components but did not exercise the command-line parser. The local interface tests also passed after the final plain-backend correction. Server startup and live generation remain separate acceptance requirements.

## Environment and scope

- Server SSH alias: `fudan-26573`.
- Python: `/mnt/data_new/lijingsu_cope_r3_20260905_v2/conda_vllm/bin/python`.
- Installed versions verified from package metadata: vLLM `0.8.5`, Transformers `4.51.3`, xgrammar `0.1.18`.
- R4 code: `/mnt/data_new/lijingsu_cope_r4_20260905/cope_fsrpc_r4/code`.
- Tokenizer: the existing Qwen3-32B snapshot `9216db5781bf21249d130ec9da846c4624c16137`; model vocabulary size `151936`.
- Only the existing tokenizer/configuration and installed Python modules were loaded. No model weights, generation requests, GPU allocation, or model-server configuration changes were made by this gate.
- The remote gate used offline model/tokenizer loading, `CUDA_VISIBLE_DEVICES` empty, and a 90-second alarm. Direct compilation used two threads; the later actual V1 backend test used its installed default of eight compiler threads. Updated schema dictionaries were passed through SSH stdin; no temporary remote source files were needed.

## Compatibility issue found and corrected

The initial schemas parsed and compiled directly in xgrammar, but this was insufficient evidence for vLLM compatibility. The installed V0 compatibility guard treats string-length and array-item bounds as unsupported and can switch the backend to outlines; its `no-fallback` option instead raises an error. The V1 guard also rejects array-item bounds. These version-specific entry points must be distinguished.

`schemas.output_schema(method)` now mechanically projects `minLength`, `maxLength`, `minItems`, and `maxItems` out of the shared strict schema. Required properties, types, all four operation branches, and operation enums remain. The local post-generation validator still uses the full strict schema, including nonempty identifiers and exactly one patch operation. Thus unsupported generation-time bounds are checked before execution rather than silently changing the decoding backend. The schema is static per method and never receives an event or oracle answer.

The initial V0-helper gate used the following setting identically for CoPE and FSR-PC. **It was superseded by the V1 setting above and must not be used to launch the V1 engine:**

```json
{"guided_decoding_backend":"xgrammar:disable-any-whitespace,no-fallback"}
```

The installed V0 integration warns about uncontrolled whitespace generation with Qwen when arbitrary whitespace is permitted. The V1 backend component implements an option to disable arbitrary whitespace, but the installed CLI prevents selecting that option in the deployed launch. In the isolated disabled-whitespace component checks, default separators placed one space after commas and colons. Those fixed-spacing checks do not describe the final plain-backend grammar, which allows arbitrary whitespace. Capacity reports must distinguish compact reference counts from actual generated-token counts.

## Installed-code evidence

The following installed files were inspected, rather than assuming the current online API matched this older deployment:

- `vllm/model_executor/guided_decoding/xgrammar_decoding.py`: constructs tokenizer metadata from the model vocabulary; calls `xgrammar.Grammar.from_json_schema`; derives `any_whitespace` from backend options.
- `vllm/model_executor/guided_decoding/__init__.py`: `maybe_backend_fallback` and its error behavior with `no-fallback`.
- `vllm/model_executor/guided_decoding/utils.py`: unsupported JSON Schema keyword checks.
- `vllm/sampling_params.py`: comma-separated backend-option parsing and `no_fallback()`.
- `xgrammar/grammar.py`: defaults for `any_whitespace`, indentation, and separators.

The corresponding versioned public references are [vLLM 0.8.5 structured outputs](https://docs.vllm.ai/en/v0.8.5/features/structured_outputs.html) and [vLLM 0.8.5 xgrammar integration](https://github.com/vllm-project/vllm/blob/v0.8.5/vllm/model_executor/guided_decoding/xgrammar_decoding.py).

## Initial direct-xgrammar and V0-helper measured checks

The initial gate constructed `GuidedDecodingParams` using each adapted schema and the explicit backend, then called the installed V0 `maybe_backend_fallback`. Both returned the same backend with `no_fallback()` true. No fallback was used in this helper test. This did not establish that the active V1 engine would accept the request-level backend selection.

For each schema, `Grammar.from_json_schema` and a tokenizer-aware `GrammarCompiler.compile_json_schema` both succeeded. Sample acceptance was checked against compiled grammars and followed by acceptance of the actual tokenizer EOS token.

| Method | Arbitrary whitespace | Parse | Compile | Complete sample plus EOS | Parse/compile/sample elapsed |
| --- | --- | --- | --- | --- | --- |
| CoPE | Enabled, matches final deployment | Pass | Pass | 4/4 development operations | 1.457 s |
| CoPE | Disabled, component comparison only | Pass | Pass | 4/4 development operations | 0.794 s |
| FSR-PC | Enabled, matches final deployment | Pass | Pass | 1/1 complete development state | 2.126 s |
| FSR-PC | Disabled, component comparison only | Pass | Pass | 1/1 complete development state | 1.306 s |

These are CPU grammar-gate timings, not decoding latency measurements. The remote gate terminated with `ADAPTED_SCHEMA_GATE_PASS` and process exit code zero.

SHA-256 of the canonical JSON for the tested generation schemas:

```text
CoPE   c959592b2dfafa114957349175f66f04a28ca1c0a16f03802ff6e8d2355b50b9
FSR-PC 1a73724ec606459167da11e30176e631e34ea14a45f980ee39482a219da884a2
```

The local interface suite additionally passed all 17 tests after the adaptation. These cover four operation mappings, rejection of `override_current` as an output operation, required fields, local cardinality checks, both schemas across seven reference events, streamed partial usage/text, absolute deadlines, HTTP and server errors, truncation, incomplete streams, and absence of automatic retries.

## Limits

The gate establishes compatibility of syntax and tokenizer grammar tables. It does not establish that a model will choose the correct operation, preserve a complete state, finish within a selected budget, or execute a physical continuation. Those require the subsequent logged development and experiment runs. Request cancellation also remains unconfirmed by socket closure alone; the runner must inspect server-side evidence separately.

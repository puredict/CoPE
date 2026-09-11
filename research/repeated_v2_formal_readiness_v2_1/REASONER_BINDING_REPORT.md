# Production reasoner binding

Status: `ACTUAL_REASONER_TRANSPORT_PASSED` for a non-formal qualification call; no pilot or formal call has been made.

The bound client is `openai_compatible_http` using `Qwen/Qwen3-32B` revision `9216db5781bf21249d130ec9da846c4624c16137`. The content-address manifest covers 27 files and 65,540,298,478 bytes with SHA-256 `7323af5c2c972ef1728841512904e98e81212266528f45226e7f80657ff0b4cb`. All generative arms are configured to share this identity, temperature 0, top-p 1, fixed seed, one call per event, zero retries, one timeout policy, and the same information-condition token ceilings.

Qwen3's default thinking wrapper initially violated the strict transaction parsers. The production adapter now submits `chat_template_kwargs.enable_thinking=false` and `response_format=json_object`. A live vLLM request then returned `{"status":"ok"}` as a strict JSON object with exact provider usage of 34 input and 10 output tokens in 0.523 seconds. The exact request and response are retained in `production_reasoner_probe_01/PROMPT_RESPONSE.jsonl`; its SHA-256 is `bf2337fddd5a331f7a586f40868ac11fd65e6cd413c2bf45948a385b9a406c56`.

This transport probe establishes model loading, request compatibility, strict JSON framing, and token accounting. Full method-schema behavior and cross-host runtime routing remain pilot checks. Provider calls: one qualification, zero pilot, zero formal.

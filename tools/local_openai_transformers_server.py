#!/usr/bin/env python3
"""Minimal deterministic OpenAI-compatible server for a local HF causal LM.

This is an experiment transport shim, not a production server. It implements
only POST /v1/chat/completions and GET /health.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        local_files_only=True,
        torch_dtype=torch.float16,
        device_map="cuda:0",
    ).eval()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CoPELocalModelDiagnostic/1"

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json(200, {"status": "ok", "model": args.model_path})
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/chat/completions":
                self._json(404, {"error": "not_found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(size).decode("utf-8"))
                messages = request["messages"]
                max_new_tokens = int(request.get("max_tokens", 4096))
                prompt = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        do_sample=False,
                        use_cache=True,
                        pad_token_id=tokenizer.eos_token_id,
                    )
                completion_ids = generated[0, inputs["input_ids"].shape[1] :]
                content = tokenizer.decode(completion_ids, skip_special_tokens=True)
                now = int(time.time())
                self._json(
                    200,
                    {
                        "id": f"local-{now}",
                        "object": "chat.completion",
                        "created": now,
                        "model": request.get("model", "local"),
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": content},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": int(inputs["input_ids"].shape[1]),
                            "completion_tokens": int(completion_ids.shape[0]),
                            "total_tokens": int(generated.shape[1]),
                        },
                    },
                )
            except Exception as exc:  # transport must expose failures to the runner
                self._json(500, {"error": {"type": type(exc).__name__, "message": str(exc)}})

        def log_message(self, fmt: str, *items: object) -> None:
            print(f"{self.address_string()} - {fmt % items}", flush=True)

    print(
        json.dumps(
            {"status": "ready", "host": args.host, "port": args.port, "model": args.model_path}
        ),
        flush=True,
    )
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

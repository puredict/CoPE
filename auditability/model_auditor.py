from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from auditability import SCHEMA_VERSION
from auditability.common import content_hash, read_jsonl, write_json, write_jsonl


SYSTEM_PROMPT = """You are an audit-log reviewer. Answer only from the supplied evidence.
Return one JSON object with keys: answer, supporting_ids, failure_layer,
answerability, confidence. Never infer private reasoning or hidden system state.
Use answerability="unanswerable" when the evidence does not determine the answer."""


def render_prompt(package: dict[str, Any]) -> str:
    public = {
        "question": package["question"],
        "evidence": package["evidence"],
    }
    return SYSTEM_PROMPT + "\n\n" + json.dumps(
        public, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def parse_model_output(raw_output: str) -> tuple[dict[str, Any] | None, str]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(parsed, dict):
        return None, "not_an_object"
    required = {"answer", "supporting_ids", "answerability", "confidence"}
    if not required.issubset(parsed):
        return None, "missing_fields"
    if not isinstance(parsed["supporting_ids"], list):
        return None, "invalid_supporting_ids"
    return parsed, "parsed"


def run_command(command: list[str], prompt: str) -> str:
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"model command exited {completed.returncode}: {completed.stderr[-1000:]}"
        )
    return completed.stdout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a condition-blind model auditor.")
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--command", nargs="+")
    parser.add_argument("--temperature", type=float, required=True)
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {args.schema_version}")
    packages = read_jsonl(args.packages)
    prompt_hash = content_hash(SYSTEM_PROMPT)
    config = {
        "packages": str(args.packages.resolve()),
        "model_id": args.model_id,
        "temperature": args.temperature,
        "max_output_tokens": args.max_output_tokens,
        "seed": args.seed,
        "schema_version": args.schema_version,
        "system_prompt_hash": prompt_hash,
        "command": args.command,
    }
    if args.dry_run:
        print(
            json.dumps(
                {
                    "package_count": len(packages),
                    "config_hash": content_hash(config),
                    "system_prompt_hash": prompt_hash,
                },
                sort_keys=True,
            )
        )
        return
    if not args.command:
        raise ValueError("--command is required unless --dry-run is used")
    outputs = []
    for package in packages:
        prompt = render_prompt(package)
        raw_output = run_command(args.command, prompt)
        parsed, parse_status = parse_model_output(raw_output)
        outputs.append(
            {
                "package_id": package["package_id"],
                "item_id": package["item_id"],
                "episode_id": package["episode_id"],
                "model_id": args.model_id,
                "temperature": args.temperature,
                "max_output_tokens": args.max_output_tokens,
                "system_prompt_hash": prompt_hash,
                "request_hash": content_hash(prompt),
                "raw_output": raw_output,
                "parse_status": parse_status,
                "parsed": parsed,
            }
        )
    write_jsonl(
        args.output,
        outputs,
        resume_key="package_id" if args.resume else None,
    )
    write_json(
        args.output.with_suffix(".manifest.json"),
        {
            "config": config,
            "config_hash": content_hash(config),
            "output_count": len(outputs),
        },
        overwrite=args.resume,
    )
    print(json.dumps({"output": str(args.output), "output_count": len(outputs)}, sort_keys=True))


if __name__ == "__main__":
    main()

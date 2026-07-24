from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cope.methods.base import RecoveryMethod
from cope.pairing import PairSpec
from cope.providers.base import provider_call_record
from cope.runner import RunContext
from cope.types import RecoveryInput, stable_hash


class ProtocolFakeEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._metadata = {
            "is_fake": True,
            "engine_commit": "fixture-engine",
            "schema_version": "fixture-engine-v1",
        }
        self.revalidation_success = bool(config.get("revalidation_success", True))
        self.constraints: list[dict[str, Any]] = []
        self.original_task = ""

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata

    def initialize(self, original_task: str, context: dict[str, Any]) -> None:
        self.original_task = original_task
        self.constraints = [
            {
                "id": "goal",
                "source": "original_task",
                "priority": 100,
                "lineage": [],
                "text": original_task,
                "status": "active",
            },
            {
                "id": "safety",
                "source": "system",
                "priority": 1000,
                "lineage": [],
                "text": "avoid unsafe contacts",
                "status": "active",
            },
        ]

    def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps({"constraints": self.constraints}))

    def apply_operation(self, operation: dict[str, Any]) -> None:
        op = operation["op"]
        target_id = operation.get("target_id")
        if op == "Insert":
            payload = dict(operation["payload"])
            payload.setdefault("id", f"inserted:{len(self.constraints)}")
            payload.setdefault("source", "patch")
            payload.setdefault("priority", 50)
            payload.setdefault("lineage", [])
            self.constraints.append(payload)
            return
        target = next(item for item in self.constraints if item["id"] == target_id)
        if op == "Override":
            target.update(operation["payload"])
        elif op == "Suspend":
            target["status"] = "suspended"
        elif op == "Demote":
            target["priority"] = int(target["priority"]) - 1
        elif op == "Revalidate":
            target["last_revalidation"] = operation["payload"]["result"]
        elif op == "Restore":
            target["status"] = "active"
        elif op == "Expire":
            target["status"] = "expired"

    def revalidate(self, target_id: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": self.revalidation_success,
            "evidence": "deterministic fixture",
            "target_id": target_id,
        }

    def compile_controller_prompt(self) -> str:
        return f"fixture patched controller: {self.original_task}"


def create_fake_engine(config: dict[str, Any]) -> ProtocolFakeEngine:
    return ProtocolFakeEngine(config)


class FakeComparisonBackend:
    name = "deterministic_test_backend"
    formal_capable = False

    def __init__(self, config: Any, provider: Any) -> None:
        self.config = config
        self.provider = provider
        self.calls: list[tuple[str, str]] = []

    def readiness_errors(self, config: Any, *, formal: bool) -> list[str]:
        return ["test backend is not formal-capable"] if formal else []

    def run_episode(
        self,
        *,
        pair: PairSpec,
        method: RecoveryMethod,
        method_name: str,
        context: RunContext,
        episode_dir: Path,
    ) -> dict[str, Any]:
        self.calls.append((pair.pair_key, method_name))
        episode_dir.mkdir(parents=True, exist_ok=False)
        original_prompt = f"fixture task {pair.task_id}"
        method.prepare(original_prompt, {"pair_key": pair.pair_key})
        event = pair.disturbance.oracle_event_packet()
        recovery_input = RecoveryInput(
            schema_version="recovery-input-v1",
            pair_key=pair.pair_key,
            original_task=original_prompt,
            observation={
                "encoding": "image/png;base64",
                "rgb": "Zml4dHVyZQ==",
                "sha256": "fixture-fresh-observation",
                "width": 1,
                "height": 1,
                "fresh": True,
            },
            event=event,
            public_action_history=(
                {
                    "policy_step": 0,
                    "raw_action": [0.0],
                    "env_action": [0.0],
                    "reward": 0.0,
                    "done": False,
                    "task_progress": {"completed": False},
                },
            ),
            task_progress={"source": "fixture", "completed": False},
            information_budget=self.config.information_budget,
        )
        decision = None
        if method_name != "clean":
            decision = method.on_event(
                original_prompt=original_prompt,
                target_joint=pair.disturbance.target_joint,
                recovery_input=recovery_input,
            )
        calls = decision.provider_calls if decision else ()
        actions = [
            {
                "policy_step": 0,
                "video_frame_index": 0,
                "prompt": original_prompt,
                "raw_action": [0.0],
                "env_action": [0.0],
                "reward": 0.0,
                "done": False,
                "task_progress": {"completed": False},
            },
            {
                "policy_step": 1,
                "video_frame_index": 1,
                "prompt": decision.controller_prompt if decision else original_prompt,
                "raw_action": [1.0],
                "env_action": [1.0],
                "reward": float(method_name in {"clean", "cope_patch"}),
                "done": method_name in {"clean", "cope_patch"},
                "task_progress": {"completed": method_name in {"clean", "cope_patch"}},
            },
        ]
        paths = {
            "episode": str(episode_dir / "episode.json"),
            "actions": str(episode_dir / "actions.jsonl"),
            "events": str(episode_dir / "events.jsonl"),
            "raw_video": str(episode_dir / "raw.mp4"),
            "event_observation": str(episode_dir / "event_observation.png") if method_name != "clean" else None,
        }
        prompt_bundle_hash = stable_hash({"version": "cope-main-prompts-v1", "templates": "fixture"})
        record = {
            "schema_version": "cope-main-episode-v1",
            "run_id": context.run_id,
            "pair_key": pair.pair_key,
            "task_id": pair.task_id,
            "initial_state_id": pair.initial_state_id,
            "seed": pair.seed,
            "method": method_name,
            "event_source": context.event_source,
            "information_budget": asdict(self.config.information_budget),
            "event": event if method_name != "clean" else None,
            "disturbance_actual": {"delta_xyz": list(pair.disturbance.delta_xyz)} if method_name != "clean" else None,
            "disturbance_step": pair.disturbance.policy_step,
            "policy_step_budget": self.config.max_policy_steps,
            "post_event_policy_step_budget": self.config.max_policy_steps - pair.disturbance.policy_step,
            "steps_before_event": 1,
            "steps_after_event": 1,
            "policy_steps": 2,
            "high_level_call_count": len(calls),
            "prompt_tokens": sum(call.usage.prompt_tokens for call in calls),
            "completion_tokens": sum(call.usage.completion_tokens for call in calls),
            "provider_calls": [provider_call_record(call, self.provider.metadata) for call in calls],
            "provider_metadata": asdict(self.provider.metadata),
            "provider_fairness_fingerprint": self.provider.metadata.fairness_fingerprint,
            "recovery_input_hash": recovery_input.input_hash if method_name != "clean" else None,
            "constraint_state_before": decision.constraint_state_before if decision else None,
            "constraint_state_after": decision.constraint_state_after if decision else None,
            "patch_operations": list(decision.patch_operations) if decision else [],
            "revalidation_result": list(decision.revalidation_result) if decision else [],
            "unaffected_slot_preservation": decision.unaffected_slot_preservation if decision else None,
            "regenerated_state": decision.regenerated_state if decision else None,
            "task_progress": {"source": "fixture", "success": method_name in {"clean", "cope_patch"}},
            "success": method_name in {"clean", "cope_patch"},
            "status": "success" if method_name in {"clean", "cope_patch"} else "timeout",
            "termination_reason": "success" if method_name in {"clean", "cope_patch"} else "timeout",
            "safety_violation": False,
            "manual_intervention": False,
            "reset_count": 0,
            "rollback_count": 0,
            "git_commit": context.git_commit,
            "config_hash": context.config_hash,
            "atlas_commit": context.atlas_commit,
            "engine_commit": context.engine_commit,
            "checkpoint_id": self.config.checkpoint_id,
            "test_only": True,
            "checkpoint_sha256": self.config.checkpoint_sha256,
            "initial_state_hash": pair.initial_state_digest,
            "pre_event_action_digest": "fixture-pre-event-actions",
            "fresh_observation_hash": "fixture-fresh-observation" if method_name != "clean" else None,
            "downstream_controller": {"name": "fixture-openvla"},
            "success_definition": "fixture-success",
            "termination_definition": "fixture-termination",
            "original_prompt": original_prompt,
            "final_prompt": decision.controller_prompt if decision else original_prompt,
            "prompt_template_version": self.config.prompt_template_version,
            "prompt_template_hash": prompt_bundle_hash,
            "actions": actions,
            "artifact_paths": paths,
            "artifact_alignment": {
                "action_records": len(actions),
                "video_frames": len(actions),
                "aligned": True,
            },
        }
        Path(paths["actions"]).write_text(
            "".join(json.dumps(action) + "\n" for action in actions),
            encoding="utf-8",
        )
        Path(paths["events"]).write_text(json.dumps({"event": "fixture"}) + "\n", encoding="utf-8")
        Path(paths["raw_video"]).write_bytes(b"fixture-video")
        if paths["event_observation"]:
            Path(paths["event_observation"]).write_bytes(b"fixture-png")
        Path(paths["episode"]).write_text(json.dumps(record, default=str), encoding="utf-8")
        return record

    def close(self) -> None:
        return None

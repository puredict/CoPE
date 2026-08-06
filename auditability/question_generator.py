from __future__ import annotations

from typing import Any

from auditability.common import stable_id
from auditability.ground_truth import extract_ground_truth


QUESTION_TEXT = {
    "behavior_change_reason": "Why did the robot pause, stop, or change behavior at the audited transition?",
    "constraint_override": "Which constraint was overridden, suspended, or expired, and by which event or constraint?",
    "preference_persistence": "Did the audited user preference remain valid after the interruption?",
    "restore_revalidation": "Was a successful, temporally valid Revalidate completed before the audited Restore?",
    "alignment_freshness": "After the object moved, did the system use the old alignment or a newly supported alignment?",
    "earliest_failure_layer": "At which layer can the current failure first be localized?",
}


def generate_questions(episode: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for truth in extract_ground_truth(episode):
        kind = truth["question_kind"]
        question_id = stable_id("question", episode["episode_id"], kind)
        questions.append(
            {
                "schema_version": episode["schema_version"],
                "item_id": question_id,
                "question_id": question_id,
                "episode_id": episode["episode_id"],
                "question_kind": kind,
                "question": QUESTION_TEXT[kind],
                "ground_truth": truth,
                "strata": {
                    "method": episode["metadata"].get("method"),
                    "success": episode["metadata"].get("success"),
                    "task": episode["metadata"].get("task"),
                    "event_type": episode["metadata"].get("event_type"),
                    "interruption_kind": episode["metadata"].get("interruption_kind"),
                    "failure_layer": truth.get("failure_layer")
                    or episode["metadata"].get("failure_layer"),
                    "has_restore": any(
                        str(patch.get("op", "")).lower() == "restore"
                        for patch in episode["cope"]["patches"]
                    ),
                    "has_override": any(
                        str(patch.get("op", "")).lower() == "override"
                        for patch in episode["cope"]["patches"]
                    ),
                    "has_expire": any(
                        str(patch.get("op", "")).lower() == "expire"
                        for patch in episode["cope"]["patches"]
                    ),
                    "synthetic": bool(episode["metadata"].get("synthetic")),
                },
            }
        )
    return questions

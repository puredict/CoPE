"""Step-level safety proxies for privileged LIBERO oracle canaries.

These metrics improve observability but do not certify physical or human
safety. MuJoCo ``cfrc_ext`` is treated as a contact-force proxy, not a
calibrated force/torque-sensor measurement.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np


def _sim_from_env(env: Any) -> Any:
    inner = getattr(env, "env", env)
    if hasattr(inner, "sim"):
        return inner.sim
    if hasattr(env, "sim"):
        return env.sim
    raise ValueError("could not locate MuJoCo sim")


def _name(model: Any, kind: str, index: int) -> str:
    resolver = getattr(model, f"{kind}_id2name", None)
    if resolver is None:
        return f"{kind}:{index}"
    value = resolver(int(index))
    return str(value) if value else f"{kind}:{index}"


class OracleSafetyTelemetry:
    """Collect post-event action, contact, and displacement evidence."""

    def __init__(self, env: Any) -> None:
        self.env = env
        self.sim = _sim_from_env(env)
        inner = getattr(env, "env", env)
        self.control_timestep = float(
            getattr(inner, "control_timestep", 0.02)
        )
        self.active = False
        self.event_step: int | None = None
        self.event_positions: dict[str, np.ndarray] = {}
        self.actions: list[tuple[float, ...]] = []
        self.peak_external_force_n = 0.0
        self.peak_external_force_body = ""
        self.peak_external_torque_nm = 0.0
        self.cumulative_peak_force_impulse_ns = 0.0
        self.contact_active_steps = 0
        self.max_simultaneous_contacts = 0
        self.contact_pair_step_counts: Counter[str] = Counter()
        self.translation_saturation_steps = 0
        self.max_translation_action_l2 = 0.0
        body_count = int(getattr(self.sim.model, "nbody", 0))
        self.body_names = [
            _name(self.sim.model, "body", index)
            for index in range(body_count)
        ]
        self.peak_force_by_body_n = np.zeros(body_count, dtype=float)
        relevant_tokens = (
            "robot",
            "gripper",
            "alphabet_soup_1",
            "tomato_sauce_1",
            "cream_cheese_1",
            "butter_1",
        )
        self.relevant_body_indices = [
            index
            for index, name in enumerate(self.body_names)
            if any(token in name for token in relevant_tokens)
        ]
        self.cumulative_relevant_peak_force_impulse_ns = 0.0
        self.task_relevant_peak_force_n = 0.0
        self.task_relevant_peak_force_body = ""
        self.task_relevant_peak_force_step = 0
        self.task_relevant_peak_force_action: tuple[float, ...] = ()
        self.task_relevant_peak_force_eef_position: tuple[float, ...] = ()
        self.task_relevant_peak_contact_pairs: tuple[str, ...] = ()
        self.protected_dynamic_contact_steps = 0
        self.robot_protected_contact_steps = 0
        self.task_object_protected_contact_steps = 0
        self.robot_environment_contact_steps = 0
        self.obsolete_receptacle_contact_steps = 0

    def begin(
        self,
        *,
        event_step: int,
        object_positions: Mapping[str, Sequence[float]],
    ) -> None:
        if self.active:
            raise RuntimeError("telemetry already active")
        self.event_step = int(event_step)
        self.event_positions = {
            str(name): np.asarray(position, dtype=float).copy()
            for name, position in object_positions.items()
        }
        self.active = True

    def record(self, action: np.ndarray, step_index: int) -> None:
        if not self.active:
            return
        if self.event_step is None or step_index <= self.event_step:
            raise RuntimeError("post-event telemetry received a stale step index")

        canonical = np.asarray(action, dtype=np.float64)
        relevant_peak_updated = False
        self.actions.append(tuple(float(value) for value in canonical))
        translation = canonical[:3]
        self.max_translation_action_l2 = max(
            self.max_translation_action_l2,
            float(np.linalg.norm(translation)),
        )
        if np.any(np.isclose(np.abs(translation), 1.0, atol=1e-12)):
            self.translation_saturation_steps += 1

        external = np.asarray(self.sim.data.cfrc_ext, dtype=float)
        if external.size:
            # MuJoCo stores cfrc_ext in rotation:translation order.  For a
            # spatial force vector that means torque first, then force.
            # See the mjData API reference for cfrc_ext and
            # mju_transformSpatial.
            torque_norms = np.linalg.norm(external[:, :3], axis=1)
            force_norms = np.linalg.norm(external[:, 3:], axis=1)
            body_index = int(np.argmax(force_norms))
            peak_force = float(force_norms[body_index])
            self.cumulative_peak_force_impulse_ns += (
                peak_force * self.control_timestep
            )
            if peak_force > self.peak_external_force_n:
                self.peak_external_force_n = peak_force
                self.peak_external_force_body = _name(
                    self.sim.model, "body", body_index
                )
            self.peak_external_torque_nm = max(
                self.peak_external_torque_nm,
                float(np.max(torque_norms)),
            )
            if len(force_norms) == len(self.peak_force_by_body_n):
                self.peak_force_by_body_n = np.maximum(
                    self.peak_force_by_body_n, force_norms
                )
                if self.relevant_body_indices:
                    relevant_index = max(
                        self.relevant_body_indices,
                        key=lambda index: force_norms[index],
                    )
                    relevant_force = float(force_norms[relevant_index])
                    self.cumulative_relevant_peak_force_impulse_ns += (
                        relevant_force * self.control_timestep
                    )
                    if relevant_force > self.task_relevant_peak_force_n:
                        relevant_peak_updated = True
                        self.task_relevant_peak_force_n = relevant_force
                        self.task_relevant_peak_force_body = self.body_names[
                            relevant_index
                        ]
                        self.task_relevant_peak_force_step = step_index
                        self.task_relevant_peak_force_action = tuple(
                            float(value) for value in canonical
                        )
                        inner = getattr(self.env, "env", self.env)
                        site_id = inner.robots[0].eef_site_id
                        self.task_relevant_peak_force_eef_position = tuple(
                            float(value)
                            for value in self.sim.data.site_xpos[site_id]
                        )

        contact_count = int(self.sim.data.ncon)
        self.max_simultaneous_contacts = max(
            self.max_simultaneous_contacts, contact_count
        )
        if contact_count:
            self.contact_active_steps += 1
        step_pairs: set[str] = set()
        for index in range(contact_count):
            contact = self.sim.data.contact[index]
            names = sorted(
                (
                    _name(self.sim.model, "geom", int(contact.geom1)),
                    _name(self.sim.model, "geom", int(contact.geom2)),
                )
            )
            step_pairs.add(" <-> ".join(names))
        self.contact_pair_step_counts.update(step_pairs)
        if relevant_peak_updated:
            self.task_relevant_peak_contact_pairs = tuple(
                sorted(step_pairs)
            )
        protected = ("cream_cheese_1", "butter_1")
        dynamic = (
            "robot",
            "gripper",
            "alphabet_soup_1",
            "tomato_sauce_1",
        )
        if any(
            any(token in pair for token in protected)
            and any(token in pair for token in dynamic)
            for pair in step_pairs
        ):
            self.protected_dynamic_contact_steps += 1
        if any(
            any(token in pair for token in protected)
            and ("robot" in pair or "gripper" in pair)
            for pair in step_pairs
        ):
            self.robot_protected_contact_steps += 1
        if any(
            any(token in pair for token in protected)
            and (
                "alphabet_soup_1" in pair
                or "tomato_sauce_1" in pair
            )
            for pair in step_pairs
        ):
            self.task_object_protected_contact_steps += 1
        if any(
            ("robot" in pair or "gripper" in pair)
            and "alphabet_soup_1" not in pair
            and "tomato_sauce_1" not in pair
            for pair in step_pairs
        ):
            self.robot_environment_contact_steps += 1
        if any(
            "alphabet_soup_1" in pair and "basket_1" in pair
            for pair in step_pairs
        ):
            self.obsolete_receptacle_contact_steps += 1

    def summarize(
        self,
        *,
        final_object_positions: Mapping[str, Sequence[float]],
        final_step: int,
    ) -> dict[str, Any]:
        if not self.active or self.event_step is None:
            raise RuntimeError("telemetry was not activated")
        final_positions = {
            str(name): np.asarray(position, dtype=float)
            for name, position in final_object_positions.items()
        }
        displacements = {
            name: float(np.linalg.norm(final_positions[name] - start))
            for name, start in self.event_positions.items()
        }
        actions = np.asarray(self.actions, dtype="<f8")
        digest = hashlib.sha256()
        digest.update(str(actions.shape).encode("ascii"))
        digest.update(actions.tobytes(order="C"))
        expected_steps = int(final_step) - self.event_step
        if len(self.actions) != expected_steps:
            raise RuntimeError(
                "telemetry/action count mismatch: "
                f"actions={len(self.actions)} expected={expected_steps}"
            )
        return {
            "post_event_steps": expected_steps,
            "post_event_action_sha256": digest.hexdigest(),
            "peak_external_force_proxy_n": self.peak_external_force_n,
            "peak_external_force_body": self.peak_external_force_body,
            "peak_external_torque_proxy_nm": self.peak_external_torque_nm,
            "task_relevant_peak_force_proxy_n": (
                self.task_relevant_peak_force_n
            ),
            "task_relevant_peak_force_body": self.task_relevant_peak_force_body,
            "task_relevant_peak_force_step": (
                self.task_relevant_peak_force_step
            ),
            "task_relevant_peak_force_post_event_step": (
                self.task_relevant_peak_force_step - self.event_step
            ),
            "task_relevant_peak_force_action_json": json.dumps(
                self.task_relevant_peak_force_action,
                separators=(",", ":"),
            ),
            "task_relevant_peak_force_eef_position_json": json.dumps(
                self.task_relevant_peak_force_eef_position,
                separators=(",", ":"),
            ),
            "task_relevant_peak_contact_pairs_json": json.dumps(
                self.task_relevant_peak_contact_pairs,
                separators=(",", ":"),
            ),
            "cumulative_task_relevant_force_impulse_proxy_ns": (
                self.cumulative_relevant_peak_force_impulse_ns
            ),
            "peak_force_by_body_json": json.dumps(
                {
                    name: float(self.peak_force_by_body_n[index])
                    for index, name in enumerate(self.body_names)
                    if self.peak_force_by_body_n[index] > 0.0
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            "cumulative_peak_force_impulse_proxy_ns": (
                self.cumulative_peak_force_impulse_ns
            ),
            "contact_active_steps": self.contact_active_steps,
            "max_simultaneous_contacts": self.max_simultaneous_contacts,
            "protected_dynamic_contact_steps": (
                self.protected_dynamic_contact_steps
            ),
            "robot_protected_contact_steps": (
                self.robot_protected_contact_steps
            ),
            "task_object_protected_contact_steps": (
                self.task_object_protected_contact_steps
            ),
            "robot_environment_contact_steps": (
                self.robot_environment_contact_steps
            ),
            "obsolete_receptacle_contact_steps": (
                self.obsolete_receptacle_contact_steps
            ),
            "contact_pair_step_counts_json": json.dumps(
                dict(self.contact_pair_step_counts.most_common()),
                separators=(",", ":"),
                sort_keys=True,
            ),
            "translation_saturation_steps": self.translation_saturation_steps,
            "max_translation_action_l2": self.max_translation_action_l2,
            "object_displacements_m_json": json.dumps(
                displacements,
                separators=(",", ":"),
                sort_keys=True,
            ),
        }

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libero_experiment_core import (  # noqa: E402
    ExperimentConfig,
    create_libero_env,
    frame_from_obs,
    get_benchmark_suite,
    inspect_target_joint_candidates,
    json_safe,
    refresh_observation_after_sim_change,
    sim_from_env,
    tokenize,
    validate_free_joint,
)


DEFAULT_DX = 0.10
DEFAULT_DY = 0.05
DEFAULT_DZ = 0.0
DEFAULT_RESOLUTION = 128


def direct_object_phrase(task_description: str) -> str:
    """Best-effort grammar cue for the object manipulated by the task."""
    text = " ".join(task_description.lower().split())
    patterns = (
        r"\bpick up\s+(?:the\s+|a\s+|an\s+)?(.+?)(?=\s+(?:and|from|between|next to|on|in|at|near|beside|inside|to|onto|into)\b|$)",
        r"\bmove\s+(?:the\s+|a\s+|an\s+)?(.+?)(?=\s+(?:and|from|between|next to|on|in|at|near|beside|inside|to|onto|into)\b|$)",
        r"\bput\s+(?:the\s+|a\s+|an\s+)?(.+?)(?=\s+(?:and|from|between|next to|on|in|at|near|beside|inside|to|onto|into)\b|$)",
        r"\bplace\s+(?:the\s+|a\s+|an\s+)?(.+?)(?=\s+(?:and|from|between|next to|on|in|at|near|beside|inside|to|onto|into)\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            phrase = match.group(1).strip(" ,.")
            if phrase:
                return phrase
    return ""


def relation_cues(task_description: str) -> list[str]:
    text = task_description.lower()
    cues = []
    for cue in (
        "between",
        "next to",
        "on top of",
        "on",
        "in",
        "inside",
        "left",
        "right",
        "front",
        "back",
        "behind",
        "near",
    ):
        if cue in text:
            cues.append(cue)
    return cues


def xy_distance(a: list[float], b: list[float]) -> float:
    return float(np.linalg.norm(np.asarray(a[:2], dtype=float) - np.asarray(b[:2], dtype=float)))


def xyz_position(value: Any) -> list[float] | None:
    try:
        arr = np.asarray(value, dtype=float).reshape(-1)
    except Exception:
        return None
    if arr.shape[0] < 3 or not np.all(np.isfinite(arr[:3])):
        return None
    return arr[:3].astype(float).tolist()


def _candidate_joint(candidate: dict[str, Any]) -> str:
    return str(candidate.get("joint") or candidate.get("name") or "")


def _candidate_tokens(candidate: dict[str, Any]) -> set[str]:
    tokens = candidate.get("candidate_tokens")
    if tokens is None:
        return tokenize(str(candidate.get("object_name") or _candidate_joint(candidate)))
    return {str(token) for token in tokens}


def enrich_candidate_positions(env: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sim = sim_from_env(env)
    enriched: list[dict[str, Any]] = []
    for raw in candidates:
        candidate = dict(raw)
        try:
            qpos_addr = int(candidate["qpos_addr"])
            candidate["initial_position"] = np.asarray(sim.data.qpos[qpos_addr : qpos_addr + 3], dtype=float).tolist()
        except Exception:
            candidate["initial_position"] = None
        enriched.append(candidate)
    return enriched


def scene_reference_positions(env: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for candidate in candidates:
        position = xyz_position(candidate.get("initial_position"))
        if position is None:
            continue
        name = str(candidate.get("object_name") or _candidate_joint(candidate))
        refs.append(
            {
                "name": name,
                "source": "free_joint",
                "tokens": sorted(tokenize(name)),
                "position": position,
            }
        )
    try:
        sim = sim_from_env(env)
        model = sim.model
        nbody = int(getattr(model, "nbody", 0))
        for body_id in range(nbody):
            try:
                name = model.body_id2name(body_id)
            except Exception:
                continue
            if not name:
                continue
            tokens = tokenize(name)
            if "robot" in tokens or "gripper" in tokens:
                continue
            try:
                position = np.asarray(sim.data.body_xpos[body_id], dtype=float).reshape(-1)[:3].tolist()
            except Exception:
                continue
            refs.append(
                {
                    "name": str(name),
                    "source": "body",
                    "tokens": sorted(tokens),
                    "position": position,
                }
            )
    except Exception:
        pass
    return refs


def find_reference(ref_text: str, references: list[dict[str, Any]]) -> dict[str, Any] | None:
    ref_tokens = tokenize(ref_text)
    if not ref_tokens:
        return None
    ranked = []
    for ref in references:
        tokens = set(ref.get("tokens", []))
        overlap = len(ref_tokens & tokens)
        if overlap <= 0:
            continue
        source_bonus = 0.1 if ref.get("source") == "free_joint" else 0.0
        name = str(ref.get("name", ""))
        exact_bonus = 0.2 if "_".join(sorted(ref_tokens & tokens)) in name else 0.0
        ranked.append((overlap + source_bonus + exact_bonus, name, ref))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def infer_spatial_rule(task_description: str) -> dict[str, Any] | None:
    text = task_description.lower()
    if "between the plate and the ramekin" in text:
        return {"type": "between", "refs": ["plate", "ramekin"]}
    if "next to the ramekin" in text:
        return {"type": "nearest", "refs": ["ramekin"]}
    if "from table center" in text:
        return {"type": "table_center", "refs": []}
    if "on the cookie box" in text:
        return {"type": "on_top_or_near", "refs": ["cookies", "cookie box"]}
    if "in the top drawer of the wooden cabinet" in text:
        return {"type": "inside_or_on_furniture", "refs": ["wooden cabinet", "cabinet", "drawer"]}
    if "on the ramekin" in text:
        return {"type": "on_top_or_near", "refs": ["ramekin"]}
    if "next to the cookie box" in text:
        return {"type": "nearest", "refs": ["cookies", "cookie box"]}
    if "on the stove" in text:
        return {"type": "on_top_or_near", "refs": ["stove"]}
    if "next to the plate" in text:
        return {"type": "nearest", "refs": ["plate"]}
    if "on the wooden cabinet" in text:
        return {"type": "inside_or_on_furniture", "refs": ["wooden cabinet", "cabinet"]}
    return None


def spatially_select_candidate(
    candidates: list[dict[str, Any]],
    task_description: str,
    references: list[dict[str, Any]],
) -> dict[str, Any] | None:
    best_semantic = max((int(candidate.get("semantic_score", 0)) for candidate in candidates), default=0)
    direct_candidates = [
        candidate for candidate in candidates if int(candidate.get("semantic_score", 0)) == best_semantic
    ]
    if best_semantic <= 0 or len(direct_candidates) <= 1:
        return None
    rule = infer_spatial_rule(task_description)
    if rule is None:
        return None

    reference_hits = [find_reference(ref_text, references) for ref_text in rule.get("refs", [])]
    reference_hits = [hit for hit in reference_hits if hit is not None]
    scored: list[tuple[float, str, dict[str, Any], str]] = []

    if rule["type"] == "between" and len(reference_hits) >= 2:
        pos_a = np.asarray(reference_hits[0]["position"], dtype=float)
        pos_b = np.asarray(reference_hits[1]["position"], dtype=float)
        midpoint = ((pos_a[:2] + pos_b[:2]) / 2.0).tolist()
        for candidate in direct_candidates:
            pos = xyz_position(candidate.get("initial_position"))
            if pos is None:
                continue
            dist_mid = xy_distance(pos, midpoint)
            balance = abs(xy_distance(pos, pos_a.tolist()) - xy_distance(pos, pos_b.tolist()))
            metric = dist_mid + 0.25 * balance
            reason = (
                f"closest to midpoint between {reference_hits[0]['name']} and {reference_hits[1]['name']} "
                f"(midpoint_distance={dist_mid:.4f}, balance={balance:.4f})"
            )
            scored.append((metric, _candidate_joint(candidate), candidate, reason))
    elif rule["type"] == "table_center":
        for candidate in direct_candidates:
            pos = xyz_position(candidate.get("initial_position"))
            if pos is None:
                continue
            metric = xy_distance(pos, [0.0, 0.0, 0.0])
            reason = f"closest to table-center proxy at xy=(0, 0) (distance={metric:.4f})"
            scored.append((metric, _candidate_joint(candidate), candidate, reason))
    elif rule["type"] in {"nearest", "on_top_or_near", "inside_or_on_furniture"} and reference_hits:
        ref = reference_hits[0]
        ref_pos = xyz_position(ref.get("position"))
        if ref_pos is not None:
            for candidate in direct_candidates:
                pos = xyz_position(candidate.get("initial_position"))
                if pos is None:
                    continue
                xy = xy_distance(pos, ref_pos)
                z_bonus = 0.0
                if rule["type"] == "on_top_or_near":
                    z_bonus = max(0.0, float(pos[2]) - float(ref_pos[2])) * 0.05
                if rule["type"] == "inside_or_on_furniture":
                    z_bonus = abs(float(pos[2]) - float(ref_pos[2])) * 0.02
                metric = xy - z_bonus
                reason = (
                    f"spatial rule {rule['type']} uses reference {ref['name']} "
                    f"(xy_distance={xy:.4f}, candidate_z={float(pos[2]):.4f}, reference_z={float(ref_pos[2]):.4f})"
                )
                scored.append((metric, _candidate_joint(candidate), candidate, reason))

    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]))
    if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 1e-6:
        return None
    selected = dict(scored[0][2])
    selected["spatial_metric"] = float(scored[0][0])
    selected["spatial_reason"] = scored[0][3]
    selected["spatial_rule"] = rule
    return selected


def annotate_candidates(
    raw_candidates: list[dict[str, Any]],
    task_description: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    phrase = direct_object_phrase(task_description)
    direct_tokens = tokenize(phrase)
    task_tokens = tokenize(task_description)
    top_score = max((int(candidate.get("score", 0)) for candidate in raw_candidates), default=None)
    top_tie_count = sum(1 for candidate in raw_candidates if int(candidate.get("score", 0)) == top_score)

    candidates: list[dict[str, Any]] = []
    for raw in raw_candidates:
        candidate = dict(raw)
        joint = _candidate_joint(candidate)
        object_tokens = _candidate_tokens(candidate)
        text_match_tokens = sorted(task_tokens & object_tokens)
        direct_match_tokens = sorted(direct_tokens & object_tokens)
        score = int(candidate.get("score", len(text_match_tokens)))
        candidate.update(
            {
                "joint": joint,
                "score": score,
                "text_match_tokens": text_match_tokens,
                "direct_object_match_tokens": direct_match_tokens,
                "semantic_score": len(direct_match_tokens),
                "is_top_score_tie": bool(top_score is not None and score == top_score and top_tie_count > 1),
                "reason": str(candidate.get("reason") or candidate.get("score_reason") or ""),
            }
        )
        candidates.append(candidate)

    metadata = {
        "direct_object_phrase": phrase,
        "direct_object_tokens": sorted(direct_tokens),
        "top_score": top_score,
        "top_score_tie_count": top_tie_count,
    }
    return candidates, metadata


def choose_explicit_target(
    candidates: list[dict[str, Any]],
    inspection: Any,
    metadata: dict[str, Any],
    task_description: str,
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    auto_reliable = bool(
        getattr(inspection, "recommended_joint", None)
        and not bool(getattr(inspection, "ambiguous", False))
        and (getattr(inspection, "top_score", 0) or 0) > 0
    )
    if auto_reliable:
        joint = str(getattr(inspection, "recommended_joint"))
        return {
            "recommended_target_joint": joint,
            "auto_reliable": True,
            "ambiguous": False,
            "manual_review_required": False,
            "selection_reason": f"Unique highest token-overlap score selected {joint}.",
        }

    semantic_scores = [int(candidate.get("semantic_score", 0)) for candidate in candidates]
    best_semantic = max(semantic_scores, default=0)
    semantic_ties = [
        candidate for candidate in candidates if int(candidate.get("semantic_score", 0)) == best_semantic
    ]
    if best_semantic > 0 and len(semantic_ties) == 1:
        joint = _candidate_joint(semantic_ties[0])
        phrase = metadata.get("direct_object_phrase") or "the manipulated object"
        return {
            "recommended_target_joint": joint,
            "auto_reliable": False,
            "ambiguous": True,
            "manual_review_required": True,
            "selection_reason": (
                f"Auto token matching was not reliable; semantic review uses direct object phrase "
                f"{phrase!r} to select {joint}."
            ),
        }

    spatial = spatially_select_candidate(candidates, task_description, references)
    if spatial is not None:
        joint = _candidate_joint(spatial)
        return {
            "recommended_target_joint": joint,
            "auto_reliable": False,
            "ambiguous": True,
            "manual_review_required": True,
            "selection_reason": (
                "Auto token matching tied among same-named manipulated objects; manual spatial semantics "
                f"select {joint}: {spatial.get('spatial_reason')}"
            ),
        }

    return {
        "recommended_target_joint": None,
        "auto_reliable": False,
        "ambiguous": True,
        "manual_review_required": True,
        "selection_reason": (
            "No unique target joint can be selected from token matching or direct-object semantics; "
            "human review is required before disturbance."
        ),
    }


def image_delta(before: np.ndarray, after: np.ndarray) -> dict[str, Any]:
    before_arr = np.asarray(before)
    after_arr = np.asarray(after)
    if before_arr.shape != after_arr.shape:
        return {
            "shape_changed": True,
            "before_shape": list(before_arr.shape),
            "after_shape": list(after_arr.shape),
            "changed_pixels": None,
            "mean_abs": None,
            "max_abs": None,
        }
    delta = np.abs(before_arr.astype(np.int16) - after_arr.astype(np.int16))
    if delta.ndim >= 3:
        changed_pixels = int(np.count_nonzero(np.any(delta > 0, axis=-1)))
    else:
        changed_pixels = int(np.count_nonzero(delta > 0))
    return {
        "shape_changed": False,
        "before_shape": list(before_arr.shape),
        "after_shape": list(after_arr.shape),
        "changed_pixels": changed_pixels,
        "mean_abs": float(delta.mean()) if delta.size else 0.0,
        "max_abs": int(delta.max()) if delta.size else 0,
    }


def contact_summary(sim: Any) -> dict[str, Any]:
    ncon = int(getattr(sim.data, "ncon", 0))
    contacts = []
    for index in range(min(ncon, 10)):
        try:
            contact = sim.data.contact[index]
            geom1 = sim.model.geom_id2name(int(contact.geom1))
            geom2 = sim.model.geom_id2name(int(contact.geom2))
            contacts.append([geom1, geom2])
        except Exception:
            break
    return {"ncon": ncon, "sample": contacts}


def set_joint_delta(env: Any, joint_name: str, dx: float, dy: float, dz: float) -> dict[str, Any]:
    sim, joint_id, qpos_addr = validate_free_joint(env, joint_name)
    before = np.asarray(sim.data.qpos[qpos_addr : qpos_addr + 7], dtype=float).copy()
    sim.data.qpos[qpos_addr] += float(dx)
    sim.data.qpos[qpos_addr + 1] += float(dy)
    sim.data.qpos[qpos_addr + 2] += float(dz)
    sim.forward()
    after = np.asarray(sim.data.qpos[qpos_addr : qpos_addr + 7], dtype=float).copy()
    return {
        "joint": joint_name,
        "joint_id": int(joint_id),
        "qpos_addr": int(qpos_addr),
        "before_qpos": before.tolist(),
        "after_qpos": after.tolist(),
        "requested_delta_xyz": [float(dx), float(dy), float(dz)],
        "actual_delta_xyz": (after[:3] - before[:3]).astype(float).tolist(),
    }


def _finite_array(value: Any) -> bool:
    arr = np.asarray(value)
    return bool(np.all(np.isfinite(arr)))


def _workspace_bound_proxy(position: list[float]) -> bool:
    if len(position) < 3:
        return False
    x, y, z = [float(v) for v in position[:3]]
    return bool(-1.5 <= x <= 1.5 and -1.5 <= y <= 1.5 and 0.0 <= z <= 2.0)


def _obvious_penetration_proxy(before_pos: list[float], after_pos: list[float], before_contacts: int, after_contacts: int) -> bool:
    if len(before_pos) < 3 or len(after_pos) < 3:
        return True
    before_z = float(before_pos[2])
    after_z = float(after_pos[2])
    z_bad = after_z < 0.0 or after_z < before_z - 0.02
    contact_spike = int(after_contacts) > int(before_contacts) + 8
    return bool(z_bad or contact_spike)


def run_disturbance_diagnostic(
    *,
    env: Any,
    cfg: Any,
    initial_state: Any,
    target_joint: str,
    dx: float,
    dy: float,
    dz: float,
    resolution: int = DEFAULT_RESOLUTION,
    frame_extractor: Callable[[dict[str, Any], Any], np.ndarray] = frame_from_obs,
    refresh_fn: Callable[[Any, Any], tuple[dict[str, Any], dict[str, Any]]] = refresh_observation_after_sim_change,
) -> dict[str, Any]:
    env.reset()
    obs = env.set_init_state(initial_state)
    sim = sim_from_env(env)
    _, _, qpos_addr = validate_free_joint(env, target_joint)
    before_full_qpos = np.asarray(sim.data.qpos, dtype=float).copy()
    before_full_qvel = np.asarray(sim.data.qvel, dtype=float).copy()
    before_joint_qpos = before_full_qpos[qpos_addr : qpos_addr + 7].copy()
    before_contacts = contact_summary(sim)
    before_frame = np.asarray(frame_extractor(obs, (resolution, resolution)))

    simulator_stable = True
    simulator_error: str | None = None
    try:
        mutation = set_joint_delta(env, target_joint, dx, dy, dz)
        after_mutation_contacts = contact_summary(sim)
        fresh_obs, refresh = refresh_fn(env, cfg)
        fresh_frame = np.asarray(frame_extractor(fresh_obs, (resolution, resolution)))
        after_full_qpos = np.asarray(sim.data.qpos, dtype=float).copy()
        after_joint_qpos = after_full_qpos[qpos_addr : qpos_addr + 7].copy()
    except Exception as exc:
        simulator_stable = False
        simulator_error = repr(exc)
        mutation = {}
        after_mutation_contacts = contact_summary(sim)
        refresh = {"method": "failed", "consumed_noop_env_step": False, "error": simulator_error}
        fresh_frame = before_frame.copy()
        after_full_qpos = np.asarray(sim.data.qpos, dtype=float).copy()
        after_joint_qpos = after_full_qpos[qpos_addr : qpos_addr + 7].copy()

    sim.data.qpos[:] = before_full_qpos
    sim.data.qvel[:] = before_full_qvel
    sim.forward()
    restored_qpos = np.asarray(sim.data.qpos, dtype=float).copy()
    restored_qvel = np.asarray(sim.data.qvel, dtype=float).copy()

    actual_delta = (after_joint_qpos[:3] - before_joint_qpos[:3]).astype(float)
    requested_delta = np.asarray([dx, dy, dz], dtype=float)
    pixels = image_delta(before_frame, fresh_frame)
    nonfinite = not (
        _finite_array(before_full_qpos)
        and _finite_array(before_full_qvel)
        and _finite_array(after_full_qpos)
        and _finite_array(after_joint_qpos)
        and _finite_array(fresh_frame)
    )
    restore_successful = bool(
        np.allclose(restored_qpos, before_full_qpos, atol=1e-9)
        and np.allclose(restored_qvel, before_full_qvel, atol=1e-9)
    )
    qpos_delta_matches_request = bool(np.allclose(actual_delta, requested_delta, atol=1e-7))
    workspace_bound = _workspace_bound_proxy(after_joint_qpos[:3].astype(float).tolist())
    obvious_penetration = _obvious_penetration_proxy(
        before_joint_qpos[:3].astype(float).tolist(),
        after_joint_qpos[:3].astype(float).tolist(),
        int(before_contacts["ncon"]),
        int(after_mutation_contacts["ncon"]),
    )
    changed_pixels = pixels["changed_pixels"] if pixels["changed_pixels"] is not None else 0
    camera_visible = bool(int(changed_pixels) > 0)
    geometric_sanity = bool(
        simulator_stable
        and not nonfinite
        and qpos_delta_matches_request
        and restore_successful
        and workspace_bound
        and not obvious_penetration
    )
    return {
        "dx": float(dx),
        "dy": float(dy),
        "dz": float(dz),
        "state_id": 0,
        "target_joint": target_joint,
        "before_position": before_joint_qpos[:3].astype(float).tolist(),
        "after_position": after_joint_qpos[:3].astype(float).tolist(),
        "actual_delta": actual_delta.tolist(),
        "requested_delta": requested_delta.tolist(),
        "fresh_observation_pixel_delta": pixels,
        "fresh_observation_changed_pixels": changed_pixels,
        "consumed_noop_env_step": bool(refresh.get("consumed_noop_env_step", False)),
        "fresh_observation_method": str(refresh.get("method", "unknown")),
        "fresh_observation_operations": list(refresh.get("operations", [])),
        "simulator_stable": bool(simulator_stable),
        "simulator_error": simulator_error,
        "has_nan_or_inf": bool(nonfinite),
        "obvious_table_or_object_penetration_proxy": bool(obvious_penetration),
        "workspace_bound_proxy": bool(workspace_bound),
        "camera_visibility_proxy": bool(camera_visible),
        "geometric_sanity": bool(geometric_sanity),
        "state_0_geometric_sanity": bool(geometric_sanity),
        "state_0_camera_visibility_proxy": bool(camera_visible),
        "state_0_workspace_bound_proxy": bool(workspace_bound),
        "qpos_delta_matches_request": bool(qpos_delta_matches_request),
        "restore_successful": bool(restore_successful),
        "before_contact_summary": before_contacts,
        "after_contact_summary": after_mutation_contacts,
        "mutation": json_safe(mutation),
    }


def build_task_audit(
    *,
    task_id: int,
    task_description: str,
    initial_state_count: int,
    raw_candidates: list[dict[str, Any]],
    inspection: Any,
    disturbance: dict[str, Any] | None = None,
    disturbance_error: str | None = None,
    references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates, metadata = annotate_candidates(raw_candidates, task_description)
    references = references or []
    spatial = spatially_select_candidate(candidates, task_description, references)
    if spatial is not None:
        spatial_joint = _candidate_joint(spatial)
        for candidate in candidates:
            if _candidate_joint(candidate) == spatial_joint:
                candidate["spatial_metric"] = spatial.get("spatial_metric")
                candidate["spatial_reason"] = spatial.get("spatial_reason")
                candidate["spatial_rule"] = spatial.get("spatial_rule")
    selection = choose_explicit_target(candidates, inspection, metadata, task_description, references)
    recommended = selection["recommended_target_joint"]
    alternates = [
        _candidate_joint(candidate)
        for candidate in candidates
        if recommended is None or _candidate_joint(candidate) != recommended
    ]
    return {
        "task_id": int(task_id),
        "description": task_description,
        "initial_states": int(initial_state_count),
        "movable_free_joint_count": len(candidates),
        "direct_object_phrase": metadata["direct_object_phrase"],
        "direct_object_tokens": metadata["direct_object_tokens"],
        "auto_reliable": bool(selection["auto_reliable"]),
        "ambiguous": bool(selection["ambiguous"]),
        "manual_review_required": bool(selection["manual_review_required"]),
        "recommended_target_joint": recommended,
        "selection_reason": selection["selection_reason"],
        "alternate_candidates": alternates,
        "reference_positions": [
            {
                "name": str(ref.get("name", "")),
                "source": str(ref.get("source", "")),
                "position": ref.get("position"),
            }
            for ref in references
        ],
        "candidates": [
            {
                "joint": _candidate_joint(candidate),
                "object_name": str(candidate.get("object_name", "")),
                "initial_position": candidate.get("initial_position"),
                "score": int(candidate.get("score", 0)),
                "semantic_score": int(candidate.get("semantic_score", 0)),
                "spatial_metric": candidate.get("spatial_metric"),
                "spatial_reason": candidate.get("spatial_reason"),
                "text_match_tokens": list(candidate.get("text_match_tokens", [])),
                "direct_object_match_tokens": list(candidate.get("direct_object_match_tokens", [])),
                "tied": bool(candidate.get("is_top_score_tie", False)),
                "qpos_addr": int(candidate.get("qpos_addr", -1)),
                "reason": str(candidate.get("reason", "")),
            }
            for candidate in candidates
        ],
        "disturbance": disturbance,
        "disturbance_error": disturbance_error,
        "relation_cues": relation_cues(task_description),
    }


def audit_suite(args: argparse.Namespace) -> dict[str, Any]:
    cfg = ExperimentConfig(
        checkpoint="not_loaded",
        task_suite=args.task_suite,
        task_id=0,
        trial_id=0,
        target_joint="auto",
        dx=args.dx,
        dy=args.dy,
        resolution=args.resolution,
    )
    suite = get_benchmark_suite(args.task_suite)
    task_count = int(suite.n_tasks)
    tasks: dict[str, Any] = {}
    for task_id in range(task_count):
        task = suite.get_task(task_id)
        task_cfg = ExperimentConfig(
            checkpoint="not_loaded",
            task_suite=args.task_suite,
            task_id=task_id,
            trial_id=0,
            target_joint="auto",
            dx=args.dx,
            dy=args.dy,
            resolution=args.resolution,
        )
        initial_states = list(suite.get_task_init_states(task_id))
        env, task_description = create_libero_env(task, task_cfg)
        try:
            env.reset()
            env.set_init_state(initial_states[0])
            inspection = inspect_target_joint_candidates(env, task_description)
            raw_candidates = enrich_candidate_positions(env, list(inspection.candidates))
            references = scene_reference_positions(env, raw_candidates)
            provisional = build_task_audit(
                task_id=task_id,
                task_description=task_description,
                initial_state_count=len(initial_states),
                raw_candidates=raw_candidates,
                inspection=inspection,
                references=references,
            )
            target_joint = provisional["recommended_target_joint"]
            disturbance = None
            disturbance_error = None
            if target_joint:
                try:
                    disturbance = run_disturbance_diagnostic(
                        env=env,
                        cfg=SimpleNamespace(model_family="openvla"),
                        initial_state=initial_states[0],
                        target_joint=target_joint,
                        dx=args.dx,
                        dy=args.dy,
                        dz=args.dz,
                        resolution=args.resolution,
                    )
                except Exception as exc:
                    disturbance_error = repr(exc)
            else:
                disturbance_error = "no_recommended_target_joint"
            tasks[str(task_id)] = build_task_audit(
                task_id=task_id,
                task_description=task_description,
                initial_state_count=len(initial_states),
                raw_candidates=raw_candidates,
                inspection=inspection,
                disturbance=disturbance,
                disturbance_error=disturbance_error,
                references=references,
            )
        finally:
            try:
                env.close()
            except Exception:
                pass
    return {
        "suite": args.task_suite,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "disturbance_request": {"dx": float(args.dx), "dy": float(args.dy), "dz": float(args.dz)},
        "tasks": tasks,
        "recommended_pilot_tasks": recommend_pilot_tasks(tasks),
        "notes": [
            "This audit does not load OpenVLA and does not run policy rollouts.",
            "Reachability is not claimed; only geometric_sanity, camera_visibility_proxy, and workspace_bound_proxy are recorded.",
        ],
    }


def recommend_pilot_tasks(tasks: dict[str, Any], count: int = 3) -> list[dict[str, Any]]:
    eligible = []
    for task_key, task in tasks.items():
        disturbance = task.get("disturbance") or {}
        if not task.get("recommended_target_joint"):
            continue
        if not disturbance.get("geometric_sanity", False):
            continue
        if not disturbance.get("camera_visibility_proxy", False):
            continue
        if not disturbance.get("workspace_bound_proxy", False):
            continue
        if disturbance.get("consumed_noop_env_step", False):
            continue
        eligible.append((task_key, task))

    selected: list[tuple[str, dict[str, Any]]] = []
    seen_joints: set[str] = set()
    seen_cues: set[str] = set()
    for task_key, task in eligible:
        joint = str(task["recommended_target_joint"])
        cues = set(task.get("relation_cues") or ["unspecified"])
        if joint in seen_joints and cues <= seen_cues:
            continue
        selected.append((task_key, task))
        seen_joints.add(joint)
        seen_cues.update(cues)
        if len(selected) >= count:
            break

    for task_key, task in eligible:
        if len(selected) >= count:
            break
        if task_key not in {key for key, _ in selected}:
            selected.append((task_key, task))

    pilots = []
    for task_key, task in selected[:count]:
        pilots.append(
            {
                "task_id": int(task_key),
                "target_joint": task["recommended_target_joint"],
                "reason": (
                    "Selected for small-batch pilot because the target joint is explicit, the dx/dy "
                    "disturbance passed geometric sanity, the policy-camera proxy changed, and it adds "
                    f"spatial cues {task.get('relation_cues') or ['unspecified']}."
                ),
            }
        )
    return pilots


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - project env includes PyYAML
        raise RuntimeError("PyYAML is required to write the audit config") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(json_safe(payload), sort_keys=False, allow_unicode=False), encoding="utf-8")


def _yes(value: Any) -> str:
    return "yes" if bool(value) else "no"


def write_report(path: Path, payload: dict[str, Any]) -> None:
    tasks = payload["tasks"]
    lines: list[str] = []
    lines.append("# LIBERO Spatial Target Joint Audit")
    lines.append("")
    lines.append(f"- Suite: `{payload['suite']}`")
    lines.append(f"- Generated: `{payload['generated_at']}`")
    request = payload["disturbance_request"]
    lines.append(f"- Disturbance probe: `dx={request['dx']:.2f}, dy={request['dy']:.2f}, dz={request['dz']:.2f}` on initial state 0")
    lines.append("- Constraints honored: no OpenVLA load, no policy rollout, no Dashboard use, no dependency upgrade, no success-criterion change.")
    lines.append("- Reachability is not claimed; the audit records only geometric and camera/workspace proxies.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| task | description | recommended target_joint | auto reliable | manual review | geometric | camera visible | noop step |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for task_key, task in tasks.items():
        disturbance = task.get("disturbance") or {}
        lines.append(
            "| {task} | {desc} | `{joint}` | {auto} | {manual} | {geom} | {camera} | {noop} |".format(
                task=task_key,
                desc=str(task["description"]).replace("|", "\\|"),
                joint=task.get("recommended_target_joint") or "NONE",
                auto=_yes(task.get("auto_reliable")),
                manual=_yes(task.get("manual_review_required")),
                geom=_yes(disturbance.get("geometric_sanity")),
                camera=_yes(disturbance.get("camera_visibility_proxy")),
                noop=_yes(disturbance.get("consumed_noop_env_step")),
            )
        )
    lines.append("")
    lines.append("## Pilot Recommendation")
    lines.append("")
    pilots = payload.get("recommended_pilot_tasks") or []
    if pilots:
        for pilot in pilots:
            lines.append(f"- Task {pilot['task_id']}: `{pilot['target_joint']}`. {pilot['reason']}")
    else:
        lines.append("- No task met the pilot filters; inspect YAML details before selecting pilots.")
    lines.append("")
    lines.append("## Task Details")
    for task_key, task in tasks.items():
        lines.append("")
        lines.append(f"### Task {task_key}")
        lines.append("")
        lines.append(f"- Description: {task['description']}")
        lines.append(f"- Initial states: {task['initial_states']}")
        lines.append(f"- Direct-object phrase: `{task.get('direct_object_phrase') or ''}`")
        lines.append(f"- Auto reliable: {_yes(task.get('auto_reliable'))}")
        lines.append(f"- Ambiguous: {_yes(task.get('ambiguous'))}")
        lines.append(f"- Manual review required: {_yes(task.get('manual_review_required'))}")
        lines.append(f"- Recommended explicit target_joint: `{task.get('recommended_target_joint') or 'NONE'}`")
        lines.append(f"- Selection reason: {task.get('selection_reason')}")
        lines.append(f"- Alternate candidates: {', '.join(f'`{name}`' for name in task.get('alternate_candidates', [])) or 'none'}")
        lines.append("")
        lines.append("| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |")
        lines.append("| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |")
        for candidate in task.get("candidates", []):
            lines.append(
                "| `{joint}` | {pos} | {score} | {semantic} | {spatial} | {tokens} | {direct} | {tied} | {reason} |".format(
                    joint=candidate["joint"],
                    pos=candidate.get("initial_position"),
                    score=candidate["score"],
                    semantic=candidate["semantic_score"],
                    spatial=candidate.get("spatial_reason") or "",
                    tokens=", ".join(candidate.get("text_match_tokens") or []),
                    direct=", ".join(candidate.get("direct_object_match_tokens") or []),
                    tied=_yes(candidate.get("tied")),
                    reason=str(candidate.get("reason", "")).replace("|", "\\|"),
                )
            )
        disturbance = task.get("disturbance")
        lines.append("")
        if disturbance:
            lines.append(
                "- Disturbance: before={before}, after={after}, actual_delta={delta}, changed_pixels={pixels}, "
                "geometric_sanity={geom}, camera_visibility_proxy={camera}, workspace_bound_proxy={workspace}, "
                "consumed_noop_env_step={noop}, simulator_stable={stable}, has_nan_or_inf={nan}, "
                "obvious_table_or_object_penetration_proxy={penetration}, restore_successful={restore}.".format(
                    before=disturbance.get("before_position"),
                    after=disturbance.get("after_position"),
                    delta=disturbance.get("actual_delta"),
                    pixels=disturbance.get("fresh_observation_changed_pixels"),
                    geom=_yes(disturbance.get("geometric_sanity")),
                    camera=_yes(disturbance.get("camera_visibility_proxy")),
                    workspace=_yes(disturbance.get("workspace_bound_proxy")),
                    noop=_yes(disturbance.get("consumed_noop_env_step")),
                    stable=_yes(disturbance.get("simulator_stable")),
                    nan=_yes(disturbance.get("has_nan_or_inf")),
                    penetration=_yes(disturbance.get("obvious_table_or_object_penetration_proxy")),
                    restore=_yes(disturbance.get("restore_successful")),
                )
            )
        else:
            lines.append(f"- Disturbance not completed: {task.get('disturbance_error')}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit LIBERO-Spatial task to target-joint mappings.")
    parser.add_argument("--task-suite", default="libero_spatial")
    parser.add_argument("--dx", type=float, default=DEFAULT_DX)
    parser.add_argument("--dy", type=float, default=DEFAULT_DY)
    parser.add_argument("--dz", type=float, default=DEFAULT_DZ)
    parser.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION)
    parser.add_argument("--config-out", default="configs/libero_spatial_target_joints.yaml")
    parser.add_argument("--report-out", default="docs/audit/LIBERO_SPATIAL_TARGET_AUDIT.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = audit_suite(args)
    write_yaml(ROOT / args.config_out, payload)
    write_report(ROOT / args.report_out, payload)
    print(f"wrote {args.config_out}")
    print(f"wrote {args.report_out}")


if __name__ == "__main__":
    main()

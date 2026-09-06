"""Reliable scripted pick-and-place executor + the Stage-A reliability gate.

Per the benchmark requirement: "use a reliable scripted, motion-planning, or
primitive-based executor. The purpose of this benchmark is to test task-state
adaptation, not open-vocabulary manipulation."

This CPU mock stands in for the GPU executor so that the protocol, the metrics
and the fairness controls can be validated locally without any GPU software.
On the GPU host the SAME `ExecutorRequest` interface is served by the real
scripted executor; no policy code changes.

## Common random numbers (why the RNG is keyed the way it is)

The per-attempt outcome is drawn from a stream keyed on
``(seed, object, attempt_index_for_that_object)`` and **not** on the request
fingerprint or the call counter. That is deliberate: FSR-PC re-mints slot ids,
so a fingerprint-keyed stream would hand the two arms different physical luck
for the identical physical action and would destroy the paired comparison.
Keying on the physical action gives common random numbers: any difference in
outcome between arms is attributable to the adaptation, not to the dice.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


def _draw(key: str) -> float:
    """Deterministic uniform draw in [0,1) from a string key."""
    h = hashlib.blake2b(key.encode(), digest_size=8).hexdigest()
    return int(h, 16) / float(1 << 64)


@dataclass
class MockPickPlaceExecutor:
    """Serves `ExecutorRequest`s. Identical object and API for every policy.

    `p_success` is high (0.97 per pick-and-place) because the primitive is a
    validated scripted skill, not an open-vocabulary one. The gate below still
    verifies the resulting nominal task success empirically rather than
    assuming it.
    """

    seed: int = 0
    p_success: float = 0.97
    steps_per_goal: int = 60
    # A real scripted executor does not retry forever. Two attempts per object
    # makes a failure terminal, so the reliability gate measures something.
    max_attempts_per_object: int = 2
    calls: int = 0
    attempts: Dict[str, int] = field(default_factory=dict)
    blocked_attempts: Dict[str, int] = field(default_factory=dict)
    log: List[Dict[str, Any]] = field(default_factory=list)
    # Shared, method-neutral view of the world. The executor is physical: it
    # cannot place an object into a basket that is not there, whatever the task
    # state says. This is what makes a stale goal cost something.
    world: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def run_one(self, request) -> Dict[str, Any]:
        """Execute exactly ONE pending goal from the compiled request.

        Returns a record with `placed` / `failed` / `invalid_actions`. When the
        request contains no executable goal, `done=True` is returned.
        """
        self.calls += 1
        rec: Dict[str, Any] = {"placed": [], "failed": [], "invalid_actions": [],
                               "steps": 0, "collision": False, "done": False,
                               "executor_calls": self.calls,
                               "request_fingerprint": request.fingerprint()}

        unavailable = set(self.world.get("unavailable_targets", []) or [])
        pending = [g for g in request.active_goals
                   if not g.get("completed") and g.get("object")]
        # a goal that has already bounced off a missing target steps aside until
        # the world changes, so the arm makes progress instead of livelocking
        runnable = [g for g in pending
                    if not (g.get("target") in unavailable
                            and self.blocked_attempts.get(g["object"], 0) >= 1)
                    and self.attempts.get(g["object"], 0)
                    < self.max_attempts_per_object]
        if not runnable:
            rec["done"] = True
            self.log.append(rec)
            return rec

        # fixed, method-independent execution order (from the slot payload)
        g = sorted(runnable, key=lambda x: (x.get("order", 99),
                                            str(x.get("object")), x["id"]))[0]
        obj, tgt = g["object"], g.get("target")
        if tgt is None:
            rec["invalid_actions"].append(g["id"])
            self.log.append(rec)
            return rec
        if tgt in unavailable:
            # physically impossible: the target is not on the table
            self.blocked_attempts[obj] = self.blocked_attempts.get(obj, 0) + 1
            rec["steps"] = self.steps_per_goal
            rec["invalid_actions"].append(g["id"])
            rec["reason"] = f"target {tgt} unavailable"
            self.log.append(rec)
            return rec

        n = self.attempts.get(obj, 0)
        self.attempts[obj] = n + 1
        rec["steps"] = self.steps_per_goal
        # common random numbers: keyed on the PHYSICAL action, not on the request
        if _draw(f"{self.seed}|{obj}|{n}") < self.p_success:
            rec["placed"].append({"goal_id": g["id"], "object": obj,
                                  "target": tgt})
        else:
            rec["failed"].append(g["id"])
        self.log.append(rec)
        return rec

    # ------------------------------------------------------------------
    def run(self, request) -> Dict[str, Any]:
        """Serve a whole request to completion (used by the nominal gate)."""
        placed, failed, invalid, steps = [], [], [], 0
        guard = 0
        while guard < 32:
            guard += 1
            r = self.run_one(request)
            if r["done"]:
                break
            placed += r["placed"]
            failed += r["failed"]
            invalid += r["invalid_actions"]
            steps += r["steps"]
            touched = ({p["goal_id"] for p in r["placed"]} | set(r["failed"])
                       | set(r["invalid_actions"]))
            for g in request.active_goals:
                if g["id"] in touched:
                    g["completed"] = True
        return {"placed": placed, "failed": failed, "invalid_actions": invalid,
                "steps": steps, "collision": False,
                "executor_calls": self.calls,
                "request_fingerprint": request.fingerprint()}


@dataclass
class ReliabilityGate:
    """Stage A: nominal success must be >= 8/10 before any method comparison.

    The gate is a precondition, not a result: if it fails, the benchmark task
    is changed or simplified rather than the methods being compared on it.
    """

    required: int = 8
    preferred: int = 9
    n_seeds: int = 10

    def evaluate(self, successes: int) -> Dict[str, Any]:
        return {
            "n_seeds": self.n_seeds,
            "successes": successes,
            "rate": successes / self.n_seeds,
            "required": f">= {self.required}/{self.n_seeds}",
            "preferred": f">= {self.preferred}/{self.n_seeds}",
            "passed": successes >= self.required,
            "preferred_met": successes >= self.preferred,
            "verdict": ("PASS" if successes >= self.preferred else
                        "PASS (below preferred, above required)"
                        if successes >= self.required else
                        "FAIL - do not proceed to method comparison"),
        }

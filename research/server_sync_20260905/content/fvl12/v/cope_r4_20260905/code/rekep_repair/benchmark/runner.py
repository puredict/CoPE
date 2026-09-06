"""Paired benchmark runner: every method sees the identical sampled episode."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List

import numpy as np

from ..execution.executor import Executor
from ..synthetic.env import Synthetic2DEnv
from .scenes import EpisodeSpec, sample_scene


@dataclass
class EpisodeRecord:
    spec_key: str
    method: str
    safe_delivery: bool
    collision_free_recovery: bool
    task_success: bool
    collided: bool
    failed_safe: bool
    goal_error: float
    danger_spill: float
    steps: int
    plan_latency_ms: float
    n_repairs: int
    repair_len: int
    candidates_generated: int
    candidates_rejected: int
    search_expansions: int
    branch_count: int
    graph_size: int
    compile_ops: int


def _count_from_trace(trace: List[str]) -> tuple:
    gen = rej = 0
    for tr in trace:
        for ln in tr.split("\n"):
            s = ln.strip()
            if s.startswith("generated:"):
                gen += s.count("'") // 2
            elif s.startswith("rejected"):
                rej += 1
    return gen, rej


def run_episode(spec: EpisodeSpec, method: str, factory: Callable) -> EpisodeRecord:
    cfg = sample_scene(spec)                     # identical for every method
    env = Synthetic2DEnv(cfg, seed=spec.seed)
    pol = factory()
    t0 = time.perf_counter()
    res = Executor(env).run(pol)
    elapsed_ms = (time.perf_counter() - t0) * 1e3
    r = res.report()

    gen, rej = _count_from_trace(getattr(pol, "_trace", []) or [])
    prog = getattr(pol, "program", None)
    n_repairs = getattr(prog, "_repair_counter", 0) if prog else 0
    repair_len = 0
    if prog is not None:
        repair_len = sum(1 for nid in prog._order if prog.is_repair_node(nid))
    lp = getattr(pol, "_last_plan", None)
    expansions = getattr(lp, "n_expanded", 0) if lp else 0

    return EpisodeRecord(
        spec_key=spec.key(), method=method,
        safe_delivery=bool(r["safe_delivery"]),
        collision_free_recovery=bool(r["collision_free_recovery"]),
        task_success=bool(r["task_success"]),
        collided=bool(r["collided"]),
        failed_safe=bool(r["failed_safe"]),
        goal_error=float(r["goal_error"]),
        danger_spill=float(r["danger_spill"]),
        steps=len(res.provenance.records),
        plan_latency_ms=elapsed_ms,
        n_repairs=n_repairs,
        repair_len=repair_len,
        candidates_generated=gen,
        candidates_rejected=rej,
        search_expansions=expansions,
        branch_count=int(getattr(pol, "branch_count", 0) or 0),
        graph_size=int(getattr(pol, "graph_size", 0) or 0),
        compile_ops=int(getattr(pol, "compile_ops", 0) or 0),
    )


def run_grid(specs: List[EpisodeSpec], methods: Dict[str, Callable]
             ) -> Dict[str, List[EpisodeRecord]]:
    out: Dict[str, List[EpisodeRecord]] = {m: [] for m in methods}
    for spec in specs:
        for name, factory in methods.items():
            out[name].append(run_episode(spec, name, factory))
    return out

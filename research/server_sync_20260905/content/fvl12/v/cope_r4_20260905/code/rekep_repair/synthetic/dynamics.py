"""2D synthetic manipulation environment (CPU-only).

State x_t = (p_x, p_y, theta), mode tracked by the program.  A point
end-effector carries a container with orientation ``theta``.  The nominal task
is a pouring proxy: reach the cup at ``p_goal`` while holding the pouring tilt
``theta_pour``.  A moving circular obstacle (the intruding "hand") crosses the
workspace during a known window and requires ``dist(p, obstacle) >= d_safe``.

The mode conflict that drives the whole paper: while the obstacle is present,
staying safe/stable requires holding the container at ``theta_hold`` (upright,
no spill during the evasive maneuver), which is separated from ``theta_pour``
by ``delta = |theta_pour - theta_hold|``.  A single-stage (path-only) reaction
must optimize both orientations at once and pays the Theorem-1 conflict floor;
ordered repair deactivates the pour objective during suspension and pays 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


@dataclass
class Obstacle:
    """A circular obstacle following a straight path during [t_enter, t_exit]."""

    p_start: np.ndarray
    p_end: np.ndarray
    radius: float
    t_enter: int
    t_exit: int

    def position(self, t: int) -> Optional[np.ndarray]:
        if t < self.t_enter or t > self.t_exit:
            return None
        span = max(1, self.t_exit - self.t_enter)
        alpha = (t - self.t_enter) / span
        return (1 - alpha) * self.p_start + alpha * self.p_end

    def present(self, t: int) -> bool:
        return self.t_enter <= t <= self.t_exit


@dataclass
class SceneConfig:
    horizon: int = 90
    p_init: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0]))
    p_goal: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0]))
    theta_pour: float = 1.0
    theta_hold: float = 0.0
    d_safe: float = 0.15          # collision / repulsion distance
    d_react: float = 0.35         # anticipatory detection distance (> d_safe)
    # control limits (per step)
    v_max: float = 0.06
    w_max: float = 0.30
    ws_lo: np.ndarray = field(default_factory=lambda: np.array([-0.5, -1.0]))
    ws_hi: np.ndarray = field(default_factory=lambda: np.array([1.5, 1.0]))
    # optional non-obstacle events
    slip_time: Optional[int] = None          # step at which the object slips
    drop_offset: np.ndarray = field(default_factory=lambda: np.array([0.02, -0.03]))
    relocation_time: Optional[int] = None    # step at which the target relocates
    relocation_delta: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.25]))
    # success thresholds
    eps_goal: float = 0.12
    eps_theta: float = 0.20
    eps_spill: float = 0.10          # max (theta-theta_hold)^2 allowed while obstacle present
    eps_danger: float = 0.15         # max proximity-weighted spill for success
    # A temporary stationary obstruction (a hand that reaches in, then withdraws
    # at t_exit).  Present from t=0 so the robot has anticipatory lead time.
    obstacle: Obstacle = field(
        default_factory=lambda: Obstacle(
            p_start=np.array([0.55, 0.05]),
            p_end=np.array([0.55, 0.05]),
            radius=0.12,
            t_enter=0,
            t_exit=45,
        )
    )

    @property
    def delta(self) -> float:
        return abs(self.theta_pour - self.theta_hold)


def clearance(p: np.ndarray, obs: Obstacle, t: int) -> float:
    """Signed clearance dist(p, obstacle_surface) at time t (+inf if absent)."""
    o = obs.position(t)
    if o is None:
        return np.inf
    return float(np.linalg.norm(p - o) - obs.radius)


@dataclass
class Rollout:
    """A realized trajectory and its evaluated outcome."""

    positions: np.ndarray            # (T, 2)  end-effector
    thetas: np.ndarray               # (T,)
    cfg: SceneConfig
    method: str
    # The task goal AS IT STANDS AT THE END of the episode.  Success must be
    # judged against this, never against the immutable cfg.p_goal, otherwise a
    # relocation episode can "succeed" at a stale target.
    final_goal: Optional[np.ndarray] = None
    object_delivered: bool = True    # object actually held/placed at the goal
    failed_safe: bool = False        # policy routed to safe fallback

    # --- evaluated metrics ------------------------------------------------
    def min_clearance(self) -> float:
        obs = self.cfg.obstacle
        return min(
            clearance(self.positions[t], obs, t) for t in range(len(self.thetas))
        )

    def collided(self) -> bool:
        return bool(self.min_clearance() < 0.0)

    def safety_violation(self) -> float:
        """Cumulative V_safe = sum_t [d_safe - clearance]_+ (Sec. 11.3)."""
        obs, d_safe = self.cfg.obstacle, self.cfg.d_safe
        v = 0.0
        for t in range(len(self.thetas)):
            c = clearance(self.positions[t], obs, t)
            if np.isfinite(c):
                v += max(0.0, d_safe - c)
        return v

    def max_spill(self) -> float:
        """Worst (theta - theta_hold)^2 while the obstacle is present (raw)."""
        obs = self.cfg.obstacle
        worst = 0.0
        for t in range(len(self.thetas)):
            if obs.present(t):
                worst = max(worst, (self.thetas[t] - self.cfg.theta_hold) ** 2)
        return worst

    def danger_spill(self) -> float:
        """Peak proximity-weighted spill: max_t w(clearance_t) * (theta_t-theta_hold)^2,
        with w ramping 0 (at/beyond d_react) -> 1 (at contact).  This asks for
        the worst co-occurrence of 'tilted' and 'close to the hazard'.  It is
        fair to methods that leave the hazard zone quickly (their tilt happens
        while still far, so it is down-weighted) and penalizes keeping the pour
        tilt while near the hazard (path-only, safe stop keeping tilt)."""
        cfg = self.cfg
        worst = 0.0
        for t in range(len(self.thetas)):
            c = clearance(self.positions[t], cfg.obstacle, t)
            if not np.isfinite(c):
                continue
            w = float(np.clip((cfg.d_react - c) / max(cfg.d_react, 1e-6), 0.0, 1.0))
            worst = max(worst, w * (self.thetas[t] - cfg.theta_hold) ** 2)
        return worst

    def sustained_spill(self) -> float:
        """Mean (theta - theta_hold)^2 over the *sustained* interruption -- the
        second half of the obstacle-present window.  Excludes the unavoidable
        entry rotation transient so the metric asks: while the obstacle lingers,
        is the container actually held upright?  This is the quantity the
        Theorem-1 mode conflict governs."""
        obs = self.cfg.obstacle
        mid = (obs.t_enter + obs.t_exit) // 2
        vals = [
            (self.thetas[t] - self.cfg.theta_hold) ** 2
            for t in range(len(self.thetas))
            if mid <= t <= obs.t_exit
        ]
        return float(np.mean(vals)) if vals else 0.0

    def goal(self) -> np.ndarray:
        """The goal success is judged against: the CURRENT (possibly relocated)
        task goal, falling back to the nominal one if never relocated."""
        return self.cfg.p_goal if self.final_goal is None else self.final_goal

    def goal_error(self) -> float:
        return float(np.linalg.norm(self.positions[-1] - self.goal()))

    def stale_goal_error(self) -> float:
        """Distance to the ORIGINAL goal -- diagnostic only, never success."""
        return float(np.linalg.norm(self.positions[-1] - self.cfg.p_goal))

    def theta_error(self) -> float:
        return abs(self.thetas[-1] - self.cfg.theta_pour)

    def success(self) -> bool:
        """End-to-end success: reach the cup with pour tilt, never collide,
        and never spill (hold stable) while the obstacle is present."""
        """(3) FULL end-to-end task success: every terminal constraint."""
        c = self.cfg
        return bool(
            self.goal_error() <= c.eps_goal        # vs the CURRENT goal
            and self.object_delivered               # object actually held there
            and self.theta_error() <= c.eps_theta
            and self.danger_spill() <= c.eps_danger
            and not self.collided()
        )

    # --- P0-C: three DISTINCT success notions, never conflated -------------
    def safe_delivery(self) -> bool:
        """(1) Object delivered to the CURRENT goal without collision.
        Weaker than task success: ignores terminal orientation and the
        proximity-weighted spill constraint."""
        return bool(self.object_delivered and not self.collided())

    def collision_free_recovery(self) -> bool:
        """(2) The episode never collided and never had to fail safe.
        Says nothing about task completion."""
        return bool(not self.collided() and not self.failed_safe)

    def report(self) -> dict:
        return {
            "method": self.method,
            # P0-C: three distinct notions, reported separately
            "safe_delivery": self.safe_delivery(),
            "collision_free_recovery": self.collision_free_recovery(),
            "task_success": self.success(),
            "success": self.success(),      # back-compat alias for task_success
            "goal_error": round(self.goal_error(), 4),
            "stale_goal_error": round(self.stale_goal_error(), 4),
            "object_delivered": self.object_delivered,
            "theta_error": round(self.theta_error(), 4),
            "danger_spill": round(self.danger_spill(), 4),
            "eps_danger": self.cfg.eps_danger,
            "min_clearance": round(self.min_clearance(), 4),
            "collided": self.collided(),
            "safety_violation": round(self.safety_violation(), 4),
        }

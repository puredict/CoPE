# Theorem 1 — Simultaneous-objective conflict lower bound

This note states and proves the conflict bound for **nonempty target sets**, and
carefully separates the analytic result, its numerical verification, and the
trajectory-level illustration. The theorem establishes *irreducible
simultaneous-objective conflict under a fixed-mode model*. **It does not, on its
own, prove that program repair is universally superior to trajectory
replanning.**

## Setup

Let $(\mathcal X, \|\cdot\|)$ be a normed space (here $\mathbb R^n$). Let
$A, B \subseteq \mathcal X$ be **nonempty** sets with set-distance

$$
\delta \;=\; \operatorname{dist}(A,B) \;=\; \inf_{a\in A,\, b\in B}\|a-b\| \;>\; 0 .
$$

For a point $x$, write $d(x,S) = \inf_{s\in S}\|x-s\|$. A *path-only* (fixed
single-stage) reaction optimizes the nominal objective (stay in $A$) and the
interruption objective (stay in $B$) **simultaneously**, with weights
$\lambda,\mu > 0$:

$$
J(x) \;=\; \lambda\, d(x,A)^2 \;+\; \mu\, d(x,B)^2 .
$$

## Lemma (triangle inequality for set distances)

For every $x\in\mathcal X$,

$$
d(x,A) + d(x,B) \;\ge\; \delta .
$$

*Proof.* For any $a\in A$, $b\in B$, the triangle inequality gives
$\|x-a\| + \|x-b\| \ge \|a-b\| \ge \delta$. Taking the infimum over $a\in A$ then
over $b\in B$ on the left (the right side is a constant $\ge\delta$; more
precisely $\inf_{a}\|x-a\| + \inf_b\|x-b\| \ge \inf_{a,b}\|a-b\| = \delta$)
yields $d(x,A) + d(x,B) \ge \delta$. $\qquad\blacksquare$

No convexity, closedness, or boundedness of $A,B$ is required — only
nonemptiness and $\delta>0$.

## Theorem 1

Under the setup above, for fixed weights $\lambda,\mu>0$,

$$
\boxed{\;\inf_{x\in\mathcal X} J(x) \;\ge\; \frac{\lambda\mu}{\lambda+\mu}\,\delta^2\;}
$$

(we write $\inf$, not $\min$, since $A,B$ need not be closed and the infimum
need not be attained). The bound is tight — attained as a minimum — whenever
the separation is realized along a segment (e.g. $A,B$ closed with the infimum
attained), the minimizer lying at the weighted interpolation point.

*Proof.* Fix $x$ and set $a = d(x,A)\ge 0$, $b = d(x,B)\ge 0$. By the Lemma
$a + b \ge \delta$. Hence

$$
J(x) \;=\; \lambda a^2 + \mu b^2 \;\ge\; \min\{\lambda\alpha^2 + \mu\beta^2 \;:\; \alpha,\beta\ge 0,\ \alpha+\beta\ge\delta\}.
$$

The right-hand minimization is convex. Since $\lambda,\mu>0$, at the optimum the
constraint is active, $\alpha+\beta=\delta$. Substituting $\beta=\delta-\alpha$
and minimizing $g(\alpha)=\lambda\alpha^2+\mu(\delta-\alpha)^2$ over
$\alpha\in[0,\delta]$: $g'(\alpha)=2\lambda\alpha-2\mu(\delta-\alpha)=0$ gives

$$
\alpha^\star = \frac{\mu\,\delta}{\lambda+\mu}, \qquad \beta^\star = \frac{\lambda\,\delta}{\lambda+\mu},
$$

both in $[0,\delta]$, and

$$
g(\alpha^\star) = \lambda\Big(\tfrac{\mu\delta}{\lambda+\mu}\Big)^2 + \mu\Big(\tfrac{\lambda\delta}{\lambda+\mu}\Big)^2 = \frac{\lambda\mu^2 + \mu\lambda^2}{(\lambda+\mu)^2}\,\delta^2 = \frac{\lambda\mu}{\lambda+\mu}\,\delta^2 .
$$

Therefore $J(x) \ge \frac{\lambda\mu}{\lambda+\mu}\delta^2$ for all $x$, so the
same bound holds for the infimum. If a point $x^\star$ with
$d(x^\star,A)=\alpha^\star$ and $d(x^\star,B)=\beta^\star$ exists (separation
realized on a segment), the bound is attained. $\qquad\blacksquare$

## Corollary (threshold failure, for fixed weights)

Fix weights $\lambda,\mu>0$. If task success requires $J(x)\le\varepsilon$ and

$$
\varepsilon < \frac{\lambda\mu}{\lambda+\mu}\,\delta^2 ,
$$

then no fixed-stage simultaneous optimum with **those** weights can succeed.

**Caveat on weight choice.** The floor is *not* uniform over all weights: letting
$\lambda\to 0$ (or $\mu\to 0$) drives $\frac{\lambda\mu}{\lambda+\mu}\delta^2\to 0$,
i.e. one can shrink the conflict term by nearly abandoning one objective. So one
cannot claim "no weights can succeed." To claim the conflict is not tunable
away, constrain the weights to stay bounded away from $0$ — e.g. normalize
$\lambda+\mu=1$ with $\lambda,\mu\in[\epsilon_w,\,1-\epsilon_w]$, or impose
$\lambda\ge\underline\lambda>0,\ \mu\ge\underline\mu>0$. Under such a constraint
the floor has a positive minimum over the admissible weight set, and the
threshold statement holds uniformly over that set.

**What ordered repair removes.** An ordered program that satisfies $A$, then $B$,
then a restored $A'$ in **separate** time windows removes the *simultaneous*
conflict term: within each window only one objective is active, so the
per-window simultaneous-conflict floor is $0$. This does **not** make the total
trajectory cost zero — an $A\to B\to A_{\mathrm{restore}}$ trace still pays
motion cost, switching cost, and is subject to dynamics/reachability and
collision constraints. The theorem's claim is precisely: *ordered temporal
separation eliminates the irreducible simultaneous-objective conflict*, and is
useful exactly when a feasible ordered trace exists (each of $A$, $B$,
$A_{\mathrm{restore}}$ individually reachable and the transitions feasible).

## What this does and does not claim

- **Analytic result:** the bound above, proved for arbitrary nonempty $A,B$.
- **Numerical verification (sanity check, not proof):**
  `scripts/validate_theorem1.py` places two balls with surface separation
  $\delta$ and checks the numerically minimized $J$ against the closed form
  across $\delta$- and $\lambda/\mu$-sweeps; the match to machine precision is
  evidence the implementation matches the algebra, nothing more.
- **Trajectory-level illustration:** the closed-loop 2D domain (`synthetic/`,
  driven by `policies/path_only.py` vs `policies/online_repair.py`) realizes the
  conflict dynamically — path-only keeps the pour tilt near the hazard and
  incurs the conflict; ordered repair suspends the pour objective and holds
  upright. This is an *illustration of the mechanism*, not a proof of general
  superiority. In the same environment, for simple temporary obstacles,
  safe-stop and precompiled recovery also succeed (see `run_comparison.py`);
  the online method's distinct advantages appear on withheld/compound event
  classes and in restoration/provenance quality.

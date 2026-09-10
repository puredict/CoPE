# v2.1 Amendment Decision

Decision: **ADOPTED FOR CALIBRATION; FORMAL EXECUTION REMAINS BLOCKED**.

The old 260-control protocol remains a frozen historical record. It is not rescored or overwritten. The evidence shows exact deterministic duplicate seed pairs and multiple clean trajectories truncated shortly before success, so v2.1 changes the sampling unit and horizon derivation through a versioned rule fixed before new outcomes are collected.

The production LIBERO loader enumerated 500 finite initialization states: 50 for each of ten tasks, with no within-task byte-hash duplicates. v2.1 assigns states 0–9 to calibration, 10–14 to formal evaluation, 15–19 to development, and 20–49 to reserve. The sets are disjoint. Policy seeds are technical reproducibility inputs, not independent samples.

The clean collection ceiling is 520. A task receives a clean horizon only from at least three successful unique v2.1 calibration trajectories using the frozen nearest-rank Q95 rule. Its admissible clean success interval stays `[0.40, 0.95]`. The interrupted budget is derived only from successful paired calibration-state event overheads, requires three unique pairs across two event families, and is identical across methods within task and K.

The earlier audited evidence contains 40 nominal runs but 20 unique trajectories. Task 1 has five known clean successes across preserved diagnostic/calibration sources and would yield 388 controls if those records were v2.1-admissible. They are not relabeled. All ten v2.1 task horizons remain pending the new complete calibration grid. Tasks with fewer than three successful unique v2.1 trajectories will be marked `HORIZON_UNESTIMABLE`.

No CoPE-versus-baseline outcome was inspected or generated for this decision. No formal provider call or formal trajectory is authorized by the amendment.

# Phase-1 CPU verification transcripts

These logs come from `/home/lijingsu/codex-worktrees/cope-repeated-v2-phase1`
on the existing Linux server, with `/home/lijingsu/vla/.venv/bin/python`.
No GPU, provider, simulator rollout or learned policy was used.

- `full_suite_verified.txt`: final successful complete repository regression.
- `phase1_suite_verified.txt`: final successful phase-1-only regression.
- `full_suite_final.txt`: earlier collection failure retained for audit. The
  added `tests/repeated_v2/__init__.py` resolved a module-name collision with
  legacy tests without changing their contents.

The checked-in source catalog is intentionally blocked, and these tests do not
claim task eligibility or physical execution success. See
[phase-1 audit](../../docs/repeated_v2/PHASE1_AUDIT.md).

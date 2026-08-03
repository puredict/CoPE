# Formal-run disconnect and journal policy

Date: 2026-08-04

Every completed event result and redacted provider trace is appended and
`fsync`-committed before the runner proceeds.  The runner never resumes into an
existing output directory: an interrupted provider call has unknown external
side effects and must not be silently repeated.

If the client connection closes but the detached server process finishes all
cells, a deterministic finalizer may reconstruct only the derived CSV/status
from the retained journal.  It requires exactly the 320 frozen
`sequence x arm x event` keys, no duplicates or extras, a clean worktree, and
the locked manifest hash.  It never indexes a simulator state or contacts a
provider.  A journal with fewer than 320 cells is not recoverable by retry and
keeps the formal run incomplete pending an explicit new integrity decision.

The recommended actual launch is a detached server process with stdout/stderr
redirected to a run-local log, followed by read-only monitoring.  The API key
is inherited from the caller environment and its value is never written to the
command log, result journal, or git repository.

# X13 administrative interruption and recovery rule

Frozen: 2026-08-03 before starting the recovery run.

## Interrupted run

The first credentialed attempt used output target
`run_openrouter_formal_v1`. The SSH controlling terminal was closed by the
remote host after approximately eight minutes while the runner was silent and
waiting on sequential provider calls. The child process did not survive.

Post-interruption audit found:

- no runner process;
- an existing but empty v1 output directory;
- no per-sample, aggregate, status, response hash, or model-output artifact;
- no model output or method outcome was observed by the experimenter;
- the credential was never written to a file or printed.

The v1 attempt is administratively interrupted and permanently ineligible as
evidence. Its empty directory must not be reused or deleted.

## Outcome-blind recovery

Because no outcome was observed and no result exists to select on, one complete
recovery attempt may use a new `run_openrouter_formal_v2_recovery` directory
with the unchanged manifest, model, prompts, call order, temperature, seed,
budgets, smoke gate and analysis. The runner is detached from SSH so loss of
the control connection cannot kill it.

All v2 calls and artifacts are retained. There is no retry or repair inside a
cell. The paper record must disclose that an outcome-blind administrative v1
attempt may have reached the provider for an unknown prefix of smoke cells.
The v2 result is a recovery pilot, not an untouched first execution of the
original preregistration.

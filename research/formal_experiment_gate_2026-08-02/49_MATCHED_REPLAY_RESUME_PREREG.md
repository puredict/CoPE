# Matched-replay infrastructure-resume preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), after the SSH interruption and before
any resumed simulator execution.

## Observed interruption

The original state-0 matched-replay process ended with SSH exit 255 during the
first replacement execution. The runner process did not survive. The committed
journal contains exactly:

- two semantic records and eight retained provider-arm rows;
- four completed cancellation embodied rows;
- zero replacement embodied rows;
- six total lines;
- journal SHA-256:
  '635519a331ce52ced7743214821b8c68f8e3c853738515b48d24da9f307d60ef';
- interrupted-evidence commit:
  '49bdd2fbcc08aaf66d7975a8ebb44ae5b48e83cc'.

The interrupted run is not a completed result.

## Frozen recovery

- resume implementation commit:
  'db4dfdce739b325de32a3e147f056fae6fd403c5';
- the resume process rejects a present OpenRouter credential and performs zero
  provider calls;
- it never changes the committed source journal;
- output is a new directory:
  'research/matched_valid_arm_embodied_2026-08-03/state0_execution_resume_v1';
- each valid replacement arm uses a separate fresh state-0 environment;
- before execution it must reproduce retained init-state, action-prefix,
  simulator-state, stability-trace and warmup provenance;
- it rebuilds the event and canonical post-state, requires the canonical state
  hash and compiled directive to equal the retained arm row, and only then
  executes;
- invalid compact/FSR rows remain fail-closed and receive no executor call;
- each resumed arm is journaled immediately before the next arm.

## PASS rule

PASS requires:

1. provider calls during resume exactly zero;
2. both retained sparse replacement rows bind to their original response hash,
   canonical post-state and directive;
3. CoPE and neutral sparse each reproduce the same matched prefix, select
   alphabet soup, retain cream cheese, avoid butter and reach terminal success;
4. their post-event action count and action hash are identical;
5. compact and FSR-PC remain invalid and unexecuted;
6. the four retained cancellation rows contain two valid zero-action terminal
   successes and two invalid fail-closed cells;
7. no reserved state is indexed.

Any hash, prefix, journal-shape, semantic, execution or integrity mismatch
yields FAIL. No provider request is permitted under any outcome.

This recovery repairs only transport-induced missing physical rows. It does not
turn the interrupted process into an uninterrupted run and must be reported
with the original interruption.

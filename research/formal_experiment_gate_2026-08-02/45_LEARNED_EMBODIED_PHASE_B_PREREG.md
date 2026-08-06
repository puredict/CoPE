# Learned-output embodied Phase-B preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before Phase-B provider calls or
simulator execution.

## Question

Can a provider-generated CoPE commitment edit that passes the shared semantic
and transaction gates drive a qualified low-level executor to the modified
physical goal without executing the stale commitment?

This closes the development embodied gate. It is not a learned manipulation
policy comparison: the high-level operation is selected by the provider output,
while Cartesian execution uses the previously qualified privileged
simulator-geometry controller.

## Frozen implementation

- implementation commit:
  '5ccbcc23521f923711e68534e6f56fb31c57f07f';
- 40 focused live/shared-envelope tests pass;
- full cold-environment regression: 487 passed;
- explicit transaction audit fields retain base, pre/post state and evidence
  versions, processed event ID, processed payload hash, event hash, semantic
  hash and transaction hash;
- each case writes a semantic journal record before execution and a separate
  embodied record after execution.

## Stage 1: mandatory state-0 canary

- LIBERO-10 task 1, development init state 0 only;
- cancellation runs first and must compile to 'HALT' with zero action;
- because cancellation emits no action, replacement sees the identical physical
  milestone, observation and action prefix;
- replacement object selection is read only from the validated provider
  post-state, never from an oracle semantic substitute;
- three provider arms are still called for each event under the same frozen
  input and settings, six calls total;
- model 'qwen/qwen3.5-flash-02-23', reasoning none, temperature 0,
  seed 20260802, completion limit 4096, timeout 90 seconds;
- zero retry, repair, fallback and oracle substitution;
- CPU only and the cold-verified Python environment
  '/home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1';
- new output directory:
  'research/learned_embodied_phase_b_2026-08-03/state0_openrouter_v1'.

Stage 1 PASS requires:

1. all six provider calls OK with within-triplet input/settings equality;
2. both CoPE rows parser-valid, semantic-correct and shared-envelope PASS;
3. explicit transaction fields satisfy base=pre, post=pre+1,
   evidence=event world version, and processed event/payload binding;
4. cancellation selects 'HALT', emits zero post-event action, retains the
   completed cream-cheese goal and does not execute butter;
5. replacement selects 'alphabet_soup_1' from the validated post-state, the
   skill succeeds, cream cheese remains in the basket, alphabet soup reaches
   the basket, and butter is not executed;
6. no fallback, semantic oracle substitution or learned-policy claim;
7. only development state 0 is indexed and no reserved state is consumed.

Any provider, semantic, transaction, prefix, execution or integrity failure is
retained and yields FAIL. No failed call or case is rerun.

## Stage 2: frozen development expansion

If and only if Stage 1 passes, the exact same committed runner automatically
expands once to development states 1--4, both events, 24 provider calls. It must
read the retained Stage-1 CSV through the frozen expansion gate and must not
repeat state 0.

The expansion PASS requires all eight embodied cases to satisfy the same
semantic, transaction, stale-suppression and physical-terminal rules. Output:
'research/learned_embodied_phase_b_2026-08-03/expansion_states1_4_openrouter_v1'.

## Baselines and claim boundary

Compact and FSR-PC semantic validity remains diagnostic in this staged
development gate. They are not executed after an invalid semantic result. The
experiment demonstrates provider-selected high-level recovery coupled to a
privileged qualified executor; it does not demonstrate a learned visuomotor
controller or general robotic autonomy.

States 27--49 remain locked throughout both stages. States 47--49 remain
permanent reserve. A complete Phase-B PASS permits a new combined formal
readiness decision and preregistration; it does not silently consume formal
states.

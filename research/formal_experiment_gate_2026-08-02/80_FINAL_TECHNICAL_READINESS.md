# CoPE decisive-experiment technical readiness

Date: 2026-08-04

## Decision

**GO for the 32-call development-only live-provider smoke.**

**Not yet GO for the 320-call formal embodied run.**  Formal authorization is
conditional only on the locked live-provider smoke passing.  The remote host
currently has no `OPENROUTER_API_KEY` environment variable, so both smoke and
formal runners stop before simulator indexing or provider calls.  The key value
is never written to git, command artifacts, or result logs.

## Closed technical gates

- task-1 common-prefix controller diagnosis and bounded-regrasp repair;
- independent task-1 validation and final 526-test regression (48.80 s);
- task-0 forward prefix: 10/10 development states;
- task-0 reverse prefix: 10/10 development states;
- full task-0 terminal butter action after both prefixes: 20/20, 0 regrasp,
  A/D true and stale B/C false;
- corrected sequential persistent state: revision `1 -> 2 -> 3`, event-2
  before-hash equals event-1 after-hash;
- corrected four-arm oracle interface gate: 16/16;
- CoPE typed operation, generic JSON-path neutral patch, complete FSR-PC state,
  and full remaining-task replan all accept canonical correct outputs and
  compile to identical terminal behavior;
- task-7 physically invalid four-object design removed before formal states;
- exact call accounting corrected to 40 sequence units x 4 arms x 2 dependent
  events = 320 scheduled calls maximum;
- formal states 10--29, reserve 30--49, prefix orientations, event types,
  arm order, seeds, model, budgets, controller hash and contract hashes frozen;
- credential-free cold preflight constructed and matched all 320 requests with
  zero formal-state access;
- exact sequence endpoint, McNemar test, exact conditional interval and Holm
  secondary correction frozen before outcomes;
- fail-closed dependency skips, zero retry, credential guard, fsync journals,
  and complete-journal disconnect recovery implemented.

## Locked artifacts

- formal manifest:
  `manifests/sequential_formal_40x4x2_v1.csv`, SHA-256
  `1fe0b231bb17e9ed0711c76ee440928faccf84696043ac0a84ddd9645bf6b7ec`;
- contract manifest:
  `manifests/sequential_formal_contract_hashes_v1.csv`;
- final oracle gate:
  `research/sequential_persistence_gate_2026-08-04/oracle_correct_v4`;
- final cold preflight:
  `research/sequential_formal_preflight_2026-08-04/v2_json_neutral`;
- physical terminal gate:
  `research/task0_terminal_action_audit_2026-08-04/states0_9_v2`;
- analysis:
  `tools/analyze_sequential_formal.py`;
- formal runner:
  `experiments/sequential_formal_runner.py`.

## Scientific status

The experiment is now capable of answering the key question, but the idea is
not yet empirically submission-ready because no corrected learned-output
comparison has run.  The most important adversary is the generic JSON-path
neutral patch.  If CoPE does not beat it on sequence success, invariant/stale
execution, or a preregistered efficiency/locality metric, the method claim must
be reduced to a verifiable transaction/assurance framework.  A tie must not be
presented as evidence that typed patch editing improves recovery.

The corrected formal study uses one task identity with two prefix orientations;
it establishes within-scene causal evidence, not cross-task generalization.
That limitation should be explicit in any submission and followed by an
external replication when a fresh four-object scene is available.

## Next automatic transition

Once the remote credential environment is present, run the locked 32-call
symbolic smoke first.  If and only if its gate passes without prompt repair,
launch the detached 320-cell formal runner.  If smoke repair is required,
version the contracts and repeat oracle gate/cold preflight before formal use.

# Predicate-validator evidence index

Date: 2026-08-02 (Asia/Shanghai)

- `00_AUDIT_AND_PREREGISTRATION.md`: pre-implementation interface audit,
  frozen cases, corruption classes, and claim boundary.
- `01_REPLAY_CASES.csv`: ten hash-pinned rows from consumed states 0--4.
- `02_COMMANDS.txt`: frozen CPU commands.
- `03_ASSIGNED_RESULTS.csv`: authoritative 10/10 test-only replay.
- `04_REPLAY_STDOUT.txt`: replay summary.
- `05_CONFIG_PREFLIGHT.csv`: authoritative 13/13 semantic asset/config checks.
- `06_CONFIG_PREFLIGHT_STDOUT.txt`: config summary.
- `07_REPLAY_RESULTS_REPEAT.csv`, `08_DETERMINISM.txt`, and
  `09_CONFIG_PREFLIGHT_REPEAT.csv`: byte-identical replays.
- `10_FOCUSED_TESTS.txt`: 15 focused tests.
- `11_FULL_REGRESSION.txt`: 341-test repository regression.
- `12_ENGINE_PROTOCOL_PREFLIGHT.txt`: production metadata protocol pass with no
  live packet and rollout still locked.
- `13_RESULT.md`: scientific interpretation, limitations, and next action.
- `14_X03_X08_STATUS.csv`: component-level gate status.
- `manifests/semantic_task1_config_v1.csv`: pinned semantic task-1 config.

This index contains no GPU run, simulator run, learned-provider call, new
success observation, or state-25--49 access. Passing rows are CPU interface
evidence only.

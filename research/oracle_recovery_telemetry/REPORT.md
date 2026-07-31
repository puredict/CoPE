# Recovery telemetry and held-out validation audit

Date: 2026-07-31

Evidence class: privileged oracle mechanism canary. Contact and force values
are MuJoCo proxies, not calibrated measurements or a safety certificate.

## Corrected evaluation split

State 0 was used to diagnose the failed 20 cm staging pilot and choose the
75%-toward-origin staging rule. It is therefore **development data**, not an
independent test. States 1–4 were held out during that rule selection and are
reported separately. The present telemetry run is a confirmatory replay of
those already-observed validation layouts, not a fresh unseen sample.

The telemetry rerun exactly reproduces the earlier action prefix, event
MuJoCo-state hash, terminal predicates, total steps, and horizon outcome for
all 10 method/state rows. Telemetry therefore did not alter behavior.

## Held-out results (states 1–4)

| Metric | Exact return | Local staging |
|---|---:|---:|
| Updated goal within global 600-step horizon | 2/4 | 4/4 |
| Physical updated goal reached | 4/4 | 4/4 |
| Mean post-event recovery steps | 273.2 | 238.5 |
| Recovery-step range | 269–277 | 234–244 |
| Mean task-relevant peak-force proxy (N) | 44.75 | 56.53 |
| Maximum task-relevant peak-force proxy (N) | 51.57 | 62.63 |
| Mean task-relevant force-impulse proxy (N·s) | 159.98 | 151.57 |
| Max robot/protected-object contact steps | 0 | 0 |
| Max task-object/protected-object contact steps | 37 | 37 |
| Max robot-environment contact steps | 0 | 0 |
| Max obsolete-object/basket contact steps | 0 | 0 |
| Max preserved cream-cheese displacement (mm) | 0.10 | 0.02 |
| Max idle-butter displacement (mm) | 0.00 | 0.00 |

Local staging saves a mean of 34.8 post-event steps
on held-out states (range 30–38).

Its task-relevant peak-force proxy is lower in
0/4 pairs, with a paired mean
change of +11.77 N. Its force-impulse proxy
is lower in 4/4 pairs, with a paired
mean change of -8.41 N·s. These are reported
as mixed paired telemetry, not converted into a blanket "safer" claim.

## Fixed post-event recovery-budget curve

This descriptive, non-preregistered curve separates recovery cost from the
absolute event time. It reports physical updated-goal completion under each
post-event action budget and should not be treated as a tuned headline test.

| Post-event budget | Exact return | Local staging |
|---:|---:|---:|
| 230 | 0/4 | 0/4 |
| 240 | 0/4 | 3/4 |
| 250 | 0/4 | 4/4 |
| 260 | 0/4 | 4/4 |
| 270 | 1/4 | 4/4 |
| 280 | 4/4 | 4/4 |

## Remaining objections

- Four held-out layouts are still a tiny deterministic sample, not random
  seeds or a powered comparison.
- Staging uses oracle object identity, event timing, geometry, and knowledge
  of the obsolete object's original stable pose.
- Global `cfrc_ext` is dominated by static table support, so the report uses
  only bodies whose names match the robot or four task objects. Even this
  filtered proxy is not a calibrated robot force sensor.
- Contact count and object displacement do not establish collision severity
  or human safety.
- The updated goal is scored with simulator predicates because the original
  LIBERO BDDL goal still names butter.

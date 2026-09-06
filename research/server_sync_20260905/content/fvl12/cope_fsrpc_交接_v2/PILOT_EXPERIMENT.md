# Pilot experiment — protocol and CPU results

## 1. Design

| | |
|---|---|
| task | multi-object basket sorting (3 objects, 3 baskets) |
| arms | **CoPE**, **FSR-PC** (internally defined baseline), `no_adaptation` (control) |
| conditions | nominal, I1 cancel+redirect, I2 temporary unavailability, I3 repeated interruption, I4 changed-world restoration |
| pairing | by `(task, condition, seed)` — the method is excluded from the key |
| CPU pilot size | 10 gate episodes + 60 Stage-B episodes + 60 Stage-C episodes |
| real-simulator pilot | 10 nominal gate episodes, then exactly 60 paired episodes |

Run:

```bash
python3 scripts/run_cope_pilot.py --seeds 5 --out results/cope_pilot
```

## 2. Stage A — reliability gate

**10/10 nominal success → PASS** (required ≥ 8/10, preferred ≥ 9/10).

Measured with the `no_adaptation` arm on the uninterrupted task, so it describes
the task and the executor rather than any adaptation method.

Non-vacuity check: with a degraded executor (`p_success=0.5`) the gate returns
FAIL. The gate can therefore fail, and passing it means something.

**This is a CPU number from a scripted mock.** It validates that the gate
machinery works. It says nothing about the physical reliability of the real
task. The LIBERO/MuJoCo gate is separate and must never inherit this result.

## 3. Stage B — paired comparison (5 seeds × 4 conditions)

Binary outcomes, exact McNemar:

| metric | CoPE | FSR-PC | discordant | p |
|---|---|---|---|---|
| revised task success | 20/20 | 20/20 | 0/0 | 1.000 |
| completed progress preserved | 20/20 | 20/20 | 0/0 | 1.000 |
| remaining goal correct | 20/20 | 20/20 | 0/0 | 1.000 |
| **identity preserved** | **20/20** | **0/20** | 20/0 | **<0.001** |
| lifecycle transitions legal | 20/20 | 20/20 | 0/0 | 1.000 |
| lineage correct | 20/20 | 20/20 | 0/0 | 1.000 |
| history monotonic | 20/20 | 20/20 | 0/0 | 1.000 |

Continuous outcomes, paired bootstrap 95% CI on `CoPE − FSR-PC`:

| metric | CoPE | FSR-PC | 95% CI | excludes 0 |
|---|---|---|---|---|
| normalized edit distance | 0.457 | 1.000 | [−0.611, −0.472] | ✓ |
| slots touched per event | 2.75 | 5.13 | [−2.850, −1.875] | ✓ |
| **audit coverage** | **1.000** | **0.458** | [+0.483, +0.600] | ✓ |
| completion steps | 44.5 | 44.5 | [0, 0] | ✗ |
| invalid actions | 0.000 | 0.000 | [0, 0] | ✗ |

Per-condition final success:

| condition | CoPE | FSR-PC | no_adaptation |
|---|---|---|---|
| I1 | 5/5 | 5/5 | **0/5** |
| I2 | 5/5 | 5/5 | **0/5** |
| I3 | 5/5 | 5/5 | **0/5** |
| I4 | 5/5 | 5/5 | **0/5** |

## 4. Stage C — ablation

| arm | success | identity preserved | mean NED | mean audit coverage |
|---|---|---|---|---|
| CoPE | 20/20 | 20/20 | 0.457 | 1.000 |
| FSR-PC | 20/20 | 0/20 | 1.000 | 0.458 |
| FSR-PC(preserve_ids) | 20/20 | **20/20** | 1.000 | 0.458 |

**Mechanism identified.** Re-using identifiers recovers the identity metric and
changes nothing else. The locality and audit differences come from *local typed
editing*, not from identifier hygiene. This is exactly the ablation a reviewer
would demand, and it is run rather than argued.

## 5. Honest interpretation

What the CPU pilot supports:

- The two arms are **tied on every behavioural outcome**. CoPE does not beat
  FSR-PC on final task success, and this report does not claim it does.
- The measurable differences are structural: identity survival, edit locality,
  and which audit questions the record can answer.
- The audit gap is the substantive one. FSR-PC answers Q1 (what was cancelled)
  and Q2 (what completed work was preserved) — both recoverable from a state
  snapshot — and cannot answer Q3 (why suspended), Q4 (what allowed
  restoration) or Q5 (what replaced the old target), because a snapshot carries
  no reasons, conditions or replacement links. The scoring gives every query a
  regeneration-evidence path precisely so this is not circular.

What it does **not** support:

- `normalized_edit_distance = 1.000` for FSR-PC is true by *definition* of full
  regeneration. It describes the two designs; it is not an experimental finding
  and must not be presented as one.
- No physical-robot or learned-policy claim. The executor is a CPU mock.
- No language-model claim. Both arms use deterministic planners; `token_usage`
  is `None` by design.
- With 20 paired episodes per arm, only large effects are detectable. The
  behavioural ties are "no evidence of a difference", not "evidence of no
  difference".

## 6. What would change the conclusion

The CPU harness cannot distinguish the arms on final success because the mock
executor never punishes a slightly-wrong-but-recoverable state. In the real simulator,
watch for:

- longer horizons where regenerated state drifts across many interruptions;
- conditions with more than two interruptions, where re-minted identity makes it
  harder to tell what has already been attempted;
- cases where the executor cannot cheaply retry, so a stale or duplicated goal
  becomes an unrecoverable failure.

If none of those separate the arms either, the honest paper claim is about
**representation, auditability and edit locality**, not about task success —
and the results section should say so.

## 7. Artifacts

```
results/cope_pilot/stage_a_reliability.json
results/cope_pilot/stage_b_paired.json      # 60 episodes, full per-episode records
results/cope_pilot/stage_c_ablations.json
results/cope_pilot/dry_run_{nominal,I1,I2,I3,I4}.txt
```

Each episode record carries its `pairing_key`, both fingerprint lists, the
expected outcome, and all metrics — enough to re-derive every number above
without re-running anything.

## 8. Real LIBERO/MuJoCo protocol

The real-simulator experiment is a new, separately gated evidence stratum; it
does not inherit the CPU gate or any CPU success count.

1. Pass backend preflight, including native save/restore, an actual collision
   rejection, an invalid-handoff rejection, one accepted candidate, task
   predicates, and MP4 writing.
2. Run exactly ten nominal `no_adaptation` seeds; require ten valid episodes
   and at least eight revised-task successes.
3. Run paired same-seed CoPE and FSR-PC debug episodes for I1--I4 and inspect
   their initial hashes, event steps/world changes, patch versus regeneration,
   shared repair traces, restore/resume records, final predicates, and videos.
4. Run exactly 5 seeds x 4 conditions x 3 methods = 60 pilot episodes.

Each real experiment root uses the required layout
`<method>/<condition>/seed_<seed>/`. Every leaf contains `result.json`,
`events.jsonl`, `adaptation_trace.jsonl`, `repair_trace.jsonl`,
`state_snapshots.json`, `simulator.log`, and `video.mp4`.

The real task evaluator reads object--contain-region geometry, cancelled-object
occupancy, stale nominal-target occupancy, redirected-target success,
per-object stability, and unsafe contact. Program termination is not a success
signal. Attempted and valid episode/candidate denominators are reported
separately; infrastructure errors are excluded rather than relabelled as task
failures.

The robot/controller is OnTheGroundPanda/OSC_POSE with a privileged simulator
geometry oracle, and OSMesa renders on CPU. Consequently this experiment can
support a real-simulator mechanism claim, but not learned-policy, GPU-inference,
physical-robot, calibrated-force, or calibrated-safety claims.

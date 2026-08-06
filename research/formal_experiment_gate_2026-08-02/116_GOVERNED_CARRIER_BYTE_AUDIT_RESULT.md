# Governed-control carrier and contract byte audit result

Date: 2026-08-04 (Asia/Shanghai)

## Decision

**PASS for the narrow compact-carrier claim.**  On all eight assigned dependent
transitions, the canonical CoPE oracle proposal was smaller than each
capability-qualified control proposal.  This is deterministic representation
accounting, not evidence of learned correctness or safety.

## Frozen evidence

- runtime commit: `ef078c15390fd02081f9707854d932f6a693c0c1`;
- transitions: 8;
- arms: 5;
- canonical-equivalent rows: 40/40;
- CoPE smaller than every non-CoPE carrier: 32/32 paired comparisons;
- provider calls: 0;
- simulator states indexed: 0;
- full regression: 577/577 passed.

| Arm | Median proposal bytes | Range | Contract bytes | Median JSON leaves |
|---|---:|---:|---:|---:|
| CoPE | 300.0 | 234--305 | 588 | 6 |
| Full replan | 348.0 | 331--375 | 691 | 8 |
| Neutral JSON patch | 1657.5 | 592--1685 | 849 | 45 |
| Governed delta | 1893.0 | 944--1902 | 1147 | 47 |
| FSR-PC full state | 2244.0 | 1886--2764 | 584 | 63 |

Median paired CoPE proposal-byte reductions were:

- 14.6% versus full replan;
- 81.8% versus neutral JSON patch;
- 84.0% versus governed delta;
- 87.1% versus FSR-PC full state.

For context, contract bytes plus the median proposal are 888 for CoPE, 1039
for full replan, 2506.5 for neutral patch, 3040 for governed delta and 2828 for
FSR-PC.  This sum is a UTF-8 accounting diagnostic, not provider token usage.

## Why the gap exists

CoPE emits one occurrence-addressed operation plus event, target, revision and
replacement identifiers.  Neutral and governed carriers repeat generic paths
or complete changed commitment records; full state repeats all semantic fields.
Full replan is nearly as small as CoPE because it emits only completed facts,
remaining objects and retired IDs, while trusted code reconstructs the
persistent canonical state.

The gap is therefore substantially designed into the carrier contract.  It is
scientifically valid to report serialized output surface under this frozen
schema, but invalid to call the byte result model intelligence, compression
optimality, lower latency or safer recovery.

## Paper consequence

The only currently supported positive differentiator after the novelty and
assurance falsifiers is:

> For the assigned sparse sequential commitment changes, CoPE's specialized
> oracle carrier serializes fewer UTF-8 bytes than the admitted generic
> governed, JSON-path, complete-state and full-replan carriers.

Whether this smaller surface improves first-pass learned validity remains the
decisive unproven claim.  The near-sized full-replan carrier is an especially
important control: proposal size alone cannot justify persistent editing over
replanning.


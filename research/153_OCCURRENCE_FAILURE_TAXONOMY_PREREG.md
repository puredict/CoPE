# Occurrence learned-formal failure taxonomy amendment

Date: 2026-08-04
Status: frozen before any learned formal call

## Purpose

Add a descriptive, arm-level error breakdown needed to interpret a PASS or
NO-GO. This taxonomy does not enter efficacy, locality, safety, Holm
correction, or claim status and cannot rescue a failed primary comparison.

## Fixed columns per arm

- total cells;
- infrastructure failures;
- JSON parser failures;
- native semantic/materialization failures after parse;
- canonical-state failures after semantic materialization;
- preserved-history failures after semantic materialization;
- compiled-directive failures after semantic materialization;
- complete successes.

History, canonical, and directive counts may overlap because they describe
distinct violated properties. Parser and semantic-after-parse counts are
staged. Infrastructure counts are separately reported and continue to
invalidate the run rather than becoming method evidence.

## Output

The locked occurrence analyzer writes `03_FAILURE_TAXONOMY.csv` after the two
primary/secondary decision tables. It derives all counts from the same
journal-bound 200-cell result set.

## Claim rule

Taxonomy may explain whether a representation tends to fail at JSON syntax,
its native contract, history preservation, or directive compilation. It is
exploratory mechanism evidence only. No individual category is a new primary
endpoint, and post-hoc subgroup significance tests are prohibited.

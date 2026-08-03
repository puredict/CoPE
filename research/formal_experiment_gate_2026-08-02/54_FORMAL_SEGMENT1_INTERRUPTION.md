# Formal matched valid-arm segment-1 interruption

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**The original uninterrupted formal-run integrity criterion failed.**

The process completed states 27--32 and stopped before any state-33 provider
call because the common physical prefix returned `grasp_not_acquired`. This is
not a provider or SSH failure and is not counted as a method outcome.

## Retained evidence

- runtime/preregistration commit:
  `3d396fdbdd045602357e4dc5530c732c83b67ed0`;
- journal rows: 60 = 12 semantic cases plus 48 embodied rows;
- completed states: 27--32;
- provider calls represented: 48, all four arms and zero retries;
- state-33 provider calls: 0;
- journal SHA-256:
  `36f6450761bb01442660f59f8bfaf5977cc961cdb19bb263bcdf53c4170f96eb`;
- states 47--49 were not indexed.

Every retained cancellation and replacement case is complete. CoPE and neutral
sparse were semantic-valid and terminal-successful in all twelve cases;
corrected compact and metadata-free FSR-PC were invalid and fail-closed. No
completed call may be redrawn.

## Recovery boundary

The original protocol cannot be described as one uninterrupted 20-state run.
A segmented continuation requires a new explicit amendment before another
state-33 initialization. The only defensible continuation is one declared
restart of the common state-33 prefix with identical seed, controller and
settings, no change to the case set, and cryptographic validation of this
retained journal. If the prefix fails again, the formal run remains failed and
must stop. If it succeeds, provider calls may begin at state 33 and continue
through state 46 without touching states 27--32 or 47--49.

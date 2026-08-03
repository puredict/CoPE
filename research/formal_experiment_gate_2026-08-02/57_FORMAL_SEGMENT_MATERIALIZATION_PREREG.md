# Retained formal-segment materialization preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before derived CSV or statistics are
written.

This zero-call audit materializes only the hash-locked segment-1 journal
`36f6450761bb01442660f59f8bfaf5977cc961cdb19bb263bcdf53c4170f96eb`
using implementation commit `c60bac219d0642e956ebd62631257455782049f1`.

It must:

1. use no provider credential, provider call, simulator or controller;
2. retain exactly states 27--32, 12 cases, 48 semantic and 48 embodied rows;
3. require four arms per case, provider status OK, zero retry and original
   runtime commit `3d396fdbdd045602357e4dc5530c732c83b67ed0`;
4. compute the original endpoint without changing any row;
5. report exact paired McNemar values but mark all inference
   `confirmatory_valid=false` because the 40-case run stopped at state 33;
6. write to
   `research/formal_matched_valid_arm_2026-08-03/retained_segment1_materialized_v1`.

This is descriptive recovery of completed evidence, not a replacement formal
experiment and not authorization to index another reserved state.

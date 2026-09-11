# v2.1 clean calibration report

This audit admits exactly 100 real `openvla_native` clean trajectories: ten distinct calibration initial states for each LIBERO-10 task and the frozen technical seed 101. Raw episode artifacts were hash-verified from immutable shard mirrors. No nominal seed replicate is treated as an independent sample.

| Task | Nominal | Unique | Successful unique at ceiling | Success rate at H_clean | Completion steps | H_clean | Horizon gate |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| 0 | 10 | 10 | 6 | 0.6 | [256, 264, 270, 275, 297, 465] | 520 | HORIZON_ESTIMATED |
| 1 | 10 | 10 | 8 | 0.8 | [238, 242, 246, 250, 269, 273, 276, 323] | 388 | HORIZON_ESTIMATED |
| 2 | 10 | 10 | 7 | 0.7 | [256, 272, 274, 280, 296, 300, 323] | 388 | HORIZON_ESTIMATED |
| 3 | 10 | 10 | 3 | 0.3 | [245, 295, 312] | 375 | HORIZON_ESTIMATED |
| 4 | 10 | 10 | 7 | 0.7 | [208, 228, 230, 264, 267, 270, 284] | 341 | HORIZON_ESTIMATED |
| 5 | 10 | 10 | 9 | 0.9 | [165, 166, 183, 193, 213, 216, 228, 418, 482] | 520 | HORIZON_ESTIMATED |
| 6 | 10 | 10 | 4 | 0.4 | [201, 249, 253, 436] | 520 | HORIZON_ESTIMATED |
| 7 | 10 | 10 | 5 | 0.5 | [246, 256, 282, 286, 287] | 345 | HORIZON_ESTIMATED |
| 8 | 10 | 10 | 1 | None | [378] | None | HORIZON_UNESTIMABLE |
| 9 | 10 | 10 | 3 | 0.3 | [249, 388, 462] | 520 | HORIZON_ESTIMATED |

The collection ceiling was 520 learned-policy controls after ten recorded settling controls. `H_clean` follows `repeated_v2_1_horizon_and_independence_v1`: `clip(ceil(1.20 * nearest-rank empirical Q95), 320, 520)`, only with at least three successful unique trajectories. The unchanged eligibility interval is inclusive `[0.40, 0.95]`.

All shards used byte-identical production VLA gate evidence. Shard protocol records have separate hashes because they bind their assigned task IDs, BDDL bytes, and state bytes; their method-independent protocol projections are byte-identical with SHA-256 `2df5b2536abcb9cfa5550c09ac65bbdecc840aa25d268c7746b79858772164b0`. No CoPE-versus-baseline result was inspected or generated.

`CLEAN_MILESTONE_WITNESSES.csv` reports observational clean-trace evidence separately from the BDDL predicate definitions. A preservation witness requires one goal predicate to remain true across consecutive policy observations while another goal predicate is still false; it is not inferred from terminal success alone.

# Original stopped CPU prefix sweep audit

The original sweep established one authentic, released placement prefix for LIBERO-10 task 0 / initial state 0 with **197 returned controls**, then stopped at its first pre-event restoration check. **Nineteen planned cells were not attempted. No candidate or paired-setup event was applied, and no event-preservation outcome exists.** This audit preserves the stopped outcome and the original driver, raw files, and thresholds.

This is a file-based audit of existing evidence, with separate corroboration from the previously completed zero-control diagnostic. Producing this report made no simulator, model, provider, GPU, or remote-execution call and performed no physical prefix retry.

## Counts and accounting

| Quantity | Planned | Observed in the original sweep |
|---|---:|---:|
| Task/state cells | 20 | 1 attempted; 19 not attempted |
| Stable, released first-placement prefixes | Not an outcome target | 1 |
| Environment control intents / returned results | Prefix cap 620; state cap 630 | 197 / 197 |
| Candidate event rows | 135 | 0 produced |
| Candidate apply calls | Up to 135 | 0 attempted; 0 returned |
| Paired-setup apply calls | Up to 40 | 0 attempted; 0 returned |
| Post-event controls | At most 5 per allowed branch | 0 |
| Physical retries | 0 allowed | 0 |

The 394 control-trace records strictly alternate **intent, result** 197 times. Both sequences have consecutive IDs 1 through 197, paired phase/label equality, and no exception record. Every control is in the prefix phase. The partition is **172 skill + 10 warmup + 10 explicit release + 5 fresh stability controls = 197**. The 172 skill controls equal both the sum of recorded skill phases and the skill result counter. The controller action-history count is also 197, with no denied-intent flag.

The request field `prefix_attempts: 20` describes the plan; it must not be reported as 20 executed trials. The stopped record reports one prefix row and zero event rows. The worker exited with code 1. Cells not reached are **not attempted**, not failed prefixes. Likewise, the planned 135 candidate rows and 40 setup applications are not measurements.

The companion [ORIGINAL_SWEEP_COUNTS.csv](ORIGINAL_SWEEP_COUNTS.csv) contains all 20 planned task/state cells, their exact frozen initial-state SHA256 values, planned candidate/setup counts, and executed counts. Its SHA256 is `dd321b02e4c29be4f9f377e3e331c1f7044ebfb6ac191a555a83e74f9f797a8a`. Empty outcome/hash fields for unattempted cells mean unavailable, not failure or success.

## Retained prefix evidence

The recorded goal is `in(alphabet_soup_1, basket_1_contain_region)`. Both original placement clauses were false in the initial sample. The chosen skill returned success, recorded grasp acquisition and a 0.19791767892290713 m lift, and completed a release/retreat/settle sequence. Ten additional open-gripper, zero-motion controls preceded the five stability checks.

All five stability samples exactly match the last five control-result samples. Their simulator times increase from 9.649999999999892 through 9.849999999999959 seconds, with approximately 0.05 seconds per fresh control. The selected exact LIBERO predicate is true and all eight enumerated objects are ungrasped in each sample. Their five actions are exactly `[0, 0, 0, 0, 0, 0, -1]`. The final stored prefix sample exactly matches control 197.

The second clause, `in(tomato_sauce_1, basket_1_contain_region)`, remains false, and the recorded current whole-task goal is false. The retained evidence is therefore one first-placement prefix, not whole-task success or a clean learned-policy result.

- Frozen initial-state SHA256: `747b653b2ca1feeae8f3bd994880ce743730993ea5ce4bd003623e877f26b3bd`.
- Sealed final flattened-state SHA256: `edcddba7d6a16d8d786ad9bec10d82652e393c3bf8baae62c7afdf162677242c`.
- Snapshot representation: `float64`, shape `[123]`, 984 bytes. Repacking the stored JSON numeric values as little-endian float64 reproduced this exact SHA256 using only the standard library.
- Executed original driver SHA256: `5a079ae2fe4dd4883c1b65b49223d2d2f644582aab836ade89c2ec7c0f7e469d` (41539 bytes). The existing local driver still matches this hash.
- Producer Git SHA recorded in the request: `c0308c1fc13036ef34983dd07397744f659cb417`.

## Original stop and exact restoration evidence

The exception is `EvidenceError: restored semantic/geometry sample differs from authentic prefix`. It occurs inside the first `target_object_moved_before` restoration, before the candidate apply call. The original prefix result, the restoration's pre-state, and its post-state have identical complete flattened-snapshot dictionaries: values, dtype, shape, and SHA256. Their simulator time is identical. The restoration reports `same_commitments=true`, `same_grasps=true`, `same_object_positions=true`, and `same_eef_position=false`.

| EEF component | Stored prefix observation (m) | Refreshed restore observation (m) | Restore minus prefix (m) |
|---|---:|---:|---:|
| x | -0.0063313771251398811 | -0.0063309896058923731 | 3.87519247507968e-07 |
| y | 0.26690066765294657 | 0.26690019597326942 | -4.71679677149783e-07 |
| z | 0.75186804473811997 | 0.75186819962255669 | 1.54884436720515e-07 |

The EEF discrepancy is **6.29795263370166e-07 m (0.62979526337 micrometres) in L2 norm** and **4.71679677149783e-07 m (0.47167967715 micrometres) at most per axis**. Each axis is below 0.5 micrometres. The maximum object-position difference is 5.55111512312578e-17 m, while the saved flattened physical state is byte-identical. Contact count remains 30. These facts establish an observation-level mismatch without detected flattened-state drift; they do not justify widening the original EEF threshold. No threshold was changed.

The original trace does not independently record the authoritative EEF site immediately after control 197. Thus, the original files alone cannot identify the exact time at which its returned observation was sampled.

## Separate zero-control diagnostic and diagnosis limits

The separately sealed diagnostic reports **zero environment-step attempts, zero event injections, zero physical-prefix replays, zero VLA/provider calls, and CUDA uninitialized**. All five diagnostic paths—`set_init_state_returned`, `ordinary_getter`, `forced_getter`, `sim_forward_then_forced`, and `second_restore_same_seal`—retain the exact sealed physical-state SHA256 and unchanged commitment truth. Every observed EEF equals the authoritative simulator EEF site, and all equal the original refreshed restore observation.

The diagnostic's frozen installed-source excerpts explain the provenance distinction. LIBERO `set_init_state` regenerates observations through `sim.forward` and forced observable updates (`env_wrapper.py`, lines 136–145). Robosuite's ordinary getter reads stored observable values (`base.py`, lines 326–362); ordinary stepping updates observables according to their sampling machinery before returning the ordinary getter (`base.py`, lines 391–407). The EEF sensor itself reads `sim.data.site_xpos[eef_site_id]` (`single_arm.py`, lines 305–307), while observable values are sampled and cached (`observables.py`, lines 214–259).

Together, these results support the accepted **returned-observation cache/sampling-timing diagnosis**, rather than a changed sealed physical state. The diagnostic did **not** reproduce the exact original cached sensor sample immediately after the last control and does not prove its exact sampling instant. It introduces no new physical stability trial and does not retroactively convert the original stopped sweep into a completed run.

| Separate diagnostic file | SHA256 |
|---|---|
| [CLAIM.txt](../zero_step_diagnostic_20260906T180437Z_01653748/CLAIM.txt) | `f60805f229fe98020bd1ca675fe89a9f5fe1be1e03115ce46d773a23fe8d7388` |
| [RESULT.txt](../zero_step_diagnostic_20260906T180437Z_01653748/RESULT.txt) | `da82064d9d2134ad8f60506c5c7cf28ddc0c0e253486d51f12407611014d559d` |
| [STDOUT_STDERR.txt](../zero_step_diagnostic_20260906T180437Z_01653748/STDOUT_STDERR.txt) | `1e1dcc8448be475a2dac7e3d896010a4e716ebceb9e2f18a1f76b4a8025c687b` |

## Provenance and file integrity

Every one of the 13 original remote-inventory entries was re-read locally and matched its exact byte count and SHA256 (309,958 bytes total). The copied original bytes, including the failed-restore evidence, remain intact. The input artifacts named by the original request were also checked against their frozen hashes. The original raw files and original driver were hashed before and after creation of these analysis outputs.

| Original file | Bytes | SHA256 |
|---|---:|---|
| [EXIT.txt](../EXIT.txt) | 66 | `94317bbffe73eedd402def66f9adaa3f40a960970d10694db5256cbfa04c50d8` |
| [LAUNCH.txt](../LAUNCH.txt) | 1363 | `d4c7148c5f8fa762c52b19e9c9a8aa8b387586eb04bb60f3acea2a928446fb2d` |
| [STDOUT_STDERR.txt](../STDOUT_STDERR.txt) | 3704 | `46a575f571aa8e5315131152c340e83b0442eff5c1e90549875100316feddb9c` |
| [WORKER.txt](../WORKER.txt) | 66 | `dc567ce8ddff3e11f25098e6faa83eea06a194fb4c5655d4ff5e943907bb65a4` |
| [raw/CONTROLLER_CONFIG.txt](../raw/CONTROLLER_CONFIG.txt) | 367 | `355e57c889f275cbb962da6893ca0be6c4f6c2f5cfc33d9fe348cf25292d7f94` |
| [raw/REQUEST.txt](../raw/REQUEST.txt) | 4644 | `d5d6d011190e574a552e3236e6506cf38ec68d358fc7e35000c94f932e50b003` |
| [raw/RUNTIME_SOURCES.txt](../raw/RUNTIME_SOURCES.txt) | 319 | `edca065d0b2912be79c0fc2751ac20ade5b89ca241bd75ec7c0f007815dcb00a` |
| [raw/STOPPED.txt](../raw/STOPPED.txt) | 1170 | `7b59f89d2a5019ad23125ae26fe6a510e789f829b6f11f5647f4346c6bd68e28` |
| [raw/TASK_0_SOURCE.txt](../raw/TASK_0_SOURCE.txt) | 5945 | `a8f467ef549a28c2f550d1f1b8a86b5a01db9c9a88dbb495fe01936428e3ca75` |
| [raw/task0_state0_CONTROLS.txt](../raw/task0_state0_CONTROLS.txt) | 271667 | `69b00185c49ddcebb239a0bdc4eb469fcf41cf1f3c23e604c0fa07b3b6fd1a33` |
| [raw/task0_state0_PREFIX_CLAIM.txt](../raw/task0_state0_PREFIX_CLAIM.txt) | 1565 | `101096b941f12aab6afecc996a5f8f921a14113f4ba649e943d0ba9b4f758884` |
| [raw/task0_state0_PREFIX_RESULT.txt](../raw/task0_state0_PREFIX_RESULT.txt) | 12067 | `7ecbee4ec083f6c40873bf79cbdb5dd8852b2ab3d4327fad184d3195b9f5d6ef` |
| [raw/task0_state0_target_object_moved_before_RESTORE.txt](../raw/task0_state0_target_object_moved_before_RESTORE.txt) | 7015 | `f236ce209adb6ddfb1c7d5c271b4c5521e526051d43403f18bc5be3eaac08fca` |

The original request records these implementation-source fingerprints; this audit did not change those sources:

| Recorded source | Bytes | SHA256 |
|---|---:|---|
| `cope_benchmark/interruptions.py` | 18683 | `0aa257a533b3535acf7d38b8ca7cd6849a1d717725e7998dd26381246216bcf3` |
| `cope_benchmark/oracle_skill_controller.py` | 25551 | `9a5f83e1580357840359670ab8643e6db546bd78ef3b4bfd8123eff3147ed648` |
| `cope_benchmark/task_progress.py` | 11707 | `48366a77d05a538c75656d7dcf5b231e68154d875d8904d10c51fc601fbe14b0` |
| `libero_experiment_core.py` | 32661 | `27f98452fa2dde1cec73d59214af63ae53eebe480a113083a01f9d6b5a9769c8` |
| `tools/audit_repeated_feasibility.py` | 7298 | `428209088aa3809ac936c5be68a9c85f7db3c0d420fafc8a47980340e3abbf7c` |

## Scope and continuation boundary

The result is privileged oracle execution sub-evidence. It certifies neither clean learned-policy success, whole-task success, collision/trajectory safety, recovery capability, event preservation, formal schedule eligibility, nor a catalog entry. Five fresh prefix observations are bounded local stability evidence only. Exact MuJoCo flattened-state restoration does not serialize arbitrary Python/controller internals and is not robot recovery.

The stopped original can retain its one prefix and exact sealed state. A separately authorized, reviewed continuation may cite that prefix rather than rerun its physical actions, with distinct lineage and counters; it must not count the 197 original controls twice or treat restoring the sealed state as a second prefix trial. This audit itself executes no continuation and leaves all 135 original candidate event outcomes unevaluated.

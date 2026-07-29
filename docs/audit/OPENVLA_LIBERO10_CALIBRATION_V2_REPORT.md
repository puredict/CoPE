# OpenVLA–LIBERO-10 Clean Calibration v2 Report

## Outcome

The preregistered clean calibration v2 completed on `fvl12` with 15/15 unique
valid terminal records and no infrastructure attempts. The final audit passed
with no missing, duplicate, unexpected, or mutated entries.

This run is a feasibility screen of unmodified OpenVLA behavior. It is not a
CoPE evaluation and must not be used as evidence that CoPE is effective or
ineffective.

| Task | Runtime description | Successes | Rate | Wilson 95% CI | Gate |
| --- | --- | ---: | ---: | --- | --- |
| 1 | `put both the cream cheese box and the butter in the basket` | 5/5 | 1.00 | [0.5655, 1.0000] | selected |
| 5 | `pick up the book and place it in the back compartment of the caddy` | 4/5 | 0.80 | [0.3755, 0.9638] | selected |
| 7 | `put both the alphabet soup and the cream cheese box in the basket` | 2/5 | 0.40 | [0.1176, 0.7693] | excluded |

The preregistered threshold was clean success >= 3/5. Tasks 1 and 5 are frozen
as the only selected tasks. Task 7 did not meet the gate. No disturbance pilot,
CoPE comparison, or formal experiment was started; explicit approval remains
required for any subsequent experiment.

## Run identity

- Server: `10.176.53.120:26575`, host `fvl12`, user `lijingsu`
- Worktree: `/home/lijingsu/cope-integration-20260724`
- Branch: `exp/openvla-libero10-calibration-v2`
- Experiment implementation HEAD: `475e75d904ce4948c42c419198d5c72e58967da5`
- Implementation commits:
  - `0925d793...` — Add standard LIBERO-10 calibration v2 protocol
  - `8a16e7a...` — Use version-specific calibration v2 config loader
  - `475e75d9...` — Publish calibration claims with atomic hard links
- Output root:
  `/home/lijingsu/cope-integration-outputs-20260724/openvla_libero10_calibration_v2`
- Launcher ID: `calibration-v2-ec28080663976fa9`
- Config hash:
  `6cbc6c22065aa155a7d632fefe97788ec624dfd1aa07612e68ee4e56c11de49d`
- Static manifest SHA-256:
  `3159143aa4b4e2c112503419bce705795250026e15b8c7b98e8aacc497e7eca9`

The implementation changed:

- `configs/openvla_libero_10_calibration_v2.yaml`
- `manifests/openvla_libero_10_calibration_v2.jsonl`
- `manifests/openvla_libero_10_calibration_v1_integrity.json`
- `cope/calibration_v2.py`
- `experiments/openvla_libero_calibration_v2.py`
- `tests/test_openvla_libero_calibration_v2.py`
- `cope/calibration.py`

## Frozen protocol and task identity

The run used the
[official OpenVLA LIBERO runner](https://github.com/openvla/openvla/blob/main/experiments/robot/libero/run_libero_eval.py)
shape: 10 dummy simulator steps followed by at most 520 real policy inference
steps, for a maximum of 530 environment steps. It used `center_crop=true`,
`unnorm_key=libero_10`, the `agentview` camera, the official gripper
normalization/binarization/sign inversion, and the unchanged LIBERO success
signal. The adapter recorded an 8D state, while the model consumed image and
language only (`model_consumes_proprio=false`).

The installed canonical suite was LIBERO 0.1.0 at source commit
`570d78333ee977c8ae6de3d97120b23272c4c660`. Runtime descriptions were supplied
to the model verbatim. Task identity was fail-closed against the BDDL file,
object relations, goal state, init-state file, and per-state hashes:

| Task | BDDL SHA-256 |
| --- | --- |
| 1 | `3f552805c7ab34c44debcf38a48b8131d6fee3011dd86c039650b84e0f77d058` |
| 5 | `07ca32c940d70c065e870452ef9c63e6dfa1d8506e6a86cf9b3763f652ba2d9f` |
| 7 | `e27ab37f512fe42e35771d6130f531e6a9656929e7b4c60b348b81360cf5675d` |

The OpenVLA source checkout was commit
`c8f03f48af692657d3060c19588038c7220e9af9`. The tracked official runner blob
was `5c3f58178d7c827df829379354f7aefddc0458bc`; the recorded runtime runner
SHA-256 was
`f4c1d741489980aa51a409d7a03ec4a08a4dc5710d32d559427b92e339c6a6f3`.

## Checkpoint

- Repository: `openvla/openvla-7b-finetuned-libero-10`
- Frozen revision: `80970322773f81baa2e22fe495d0487b93a05cfa`
- Checkpoint file-manifest SHA-256:
  `58773a8ef85515f695c99402f692dc5afe0fb71efd7f3984ff44c1f117c4f034`
- Processor loader: `local_upstream_prismatic_processor_v1`
- Action dimension: 7

All four weight shard hashes, sizes, tokenizer hashes, preprocessor hash,
normalization statistics, and model index are frozen in the run manifest and
were revalidated before preparation, parity, workers, and final audit.

## Validation before execution

The implementation passed:

- 10 focused calibration v2 tests
- 21 combined calibration v1/v2 tests
- 245 full repository tests
- `py_compile`
- `git diff --check`

Tests covered the 520+10 budget split, deterministic manifest reconstruction,
concurrent atomic claim publication, disjoint eight-worker partitioning,
one model per worker, no shared inference port, safe action-replay resume,
immutable task/state/seed/checkpoint/config identities, v1 output protection,
infrastructure-attempt separation, and detection of missing, duplicate, or
unexpected terminal IDs.

## Official-path parity gate

All parity gates passed before the 15 episodes were started. The fixed reset
observation used Task 1, state 0, seed `20270724`, and the exact runtime
description.

- Official frame SHA-256 = adapter frame SHA-256:
  `41ea0fc8a999258c0f7e1d77d5a360ba8517fac3c279a6fb6deffe874c44b74f`
- Center-cropped 224x224 processor image SHA-256:
  `d84b25c1f41aa5e8871d974adb47bf75d5c2972e78c70adf6b07a460ba4e1197`
- Processor tensor hashes:
  - `attention_mask`: `dbc98745bb89574fe808968d7aafdc064cc3716ca2659f29141f428aa5be64c5`
  - `input_ids`: `971135c4374f04a22da9779b7b6a7dce99695443da1c8ce3c64000362e72ea52`
  - `pixel_values`: `866f4d0597687cdbab6f250541a4c1273be2b07903b3e6bb73087e6b618a0641`
- One real inference completed in 0.904 s and one real environment step in
  0.194 s.
- The raw 7D action was finite and legal; its raw gripper value
  `0.996078431372549` became the environment gripper action `-1.0` through the
  official transform.
- The model saw one visible GPU and no shared inference port.

## Per-episode terminals

All successes ended with `libero_done`. All failures legally exhausted the full
520-policy-step budget and were preserved without rerun.

| Task | State | Seed | Success | Policy steps | Termination |
| ---: | ---: | ---: | --- | ---: | --- |
| 1 | 0 | 20270724 | yes | 250 | `libero_done` |
| 1 | 1 | 20270725 | yes | 273 | `libero_done` |
| 1 | 2 | 20270726 | yes | 323 | `libero_done` |
| 1 | 3 | 20270727 | yes | 276 | `libero_done` |
| 1 | 4 | 20270728 | yes | 242 | `libero_done` |
| 5 | 0 | 20270824 | yes | 418 | `libero_done` |
| 5 | 1 | 20270825 | no | 520 | `policy_step_budget_exhausted` |
| 5 | 2 | 20270826 | yes | 482 | `libero_done` |
| 5 | 3 | 20270827 | yes | 228 | `libero_done` |
| 5 | 4 | 20270828 | yes | 166 | `libero_done` |
| 7 | 0 | 20270924 | yes | 286 | `libero_done` |
| 7 | 1 | 20270925 | yes | 287 | `libero_done` |
| 7 | 2 | 20270926 | no | 520 | `policy_step_budget_exhausted` |
| 7 | 3 | 20270927 | no | 520 | `policy_step_budget_exhausted` |
| 7 | 4 | 20270928 | no | 520 | `policy_step_budget_exhausted` |

Termination totals were 11 `libero_done` and 4
`policy_step_budget_exhausted`. Infrastructure-attempt count was zero.

## Scheduler and terminal audit

GPU0–7 ran eight independent workers with a fixed modulo partition. Every
worker loaded one OpenVLA instance exactly once. There was no model server and
no shared port. Seven workers processed two entries and GPU7 processed one.

Final audit:

- expected entries: 15
- terminal entries: 15
- atomic claims: 15
- completion records: 15
- missing: 0
- duplicate: 0
- unexpected: 0
- infrastructure attempts: 0
- worker summaries: 8, each with `model_load_count=1`

## Calibration v1 preservation

Calibration v1 remains permanently labeled
`nonstandard_truncated_calibration_horizon_220`. It is not pooled with or
presented as standard LIBERO-10 data. For the overlapping Task 1, v1 was 0/5 at
the truncated 220-step budget, while v2 was 5/5 with the official 520-step
budget; this is a protocol comparison, not a pooled estimate.

The complete pre/post inventories were identical:

| v1 root | Files | Inventory SHA-256 before and after |
| --- | ---: | --- |
| sequential | 16 | `0a690dea5f611c06605897eb9b5647846b671a62e0f7a706313f062a8e38d48d` |
| parallel | 90 | `fa3ba7ccd9a13745d07afe3a3e1c9b6030abc0c1f913ccdfa9ac22cad70c933e` |

## Evidence and hard stop

- `calibration_summary_v2.json` SHA-256:
  `54393cb6bb629d1eaab20bdeadcced62733e0e5dcdf51c7eafa697ddbf9061f6`
- `parity_report.json` SHA-256:
  `1ea233905e33cb1d64bc8b83a3fecd2f8f82b62ccacf5174672ca81524250b32`
- `run_manifest_v2.json` SHA-256:
  `1839e1fd9066875cd859f56ec688404d0825de52d89578204137f65b2860e13b`
- Complete evidence archive SHA-256:
  `f276a99b78babda1b0be314f933e74113ce7ba07f10c71c1e887cafeae0d7aae`

The run is hard-stopped. Tasks 1 and 5 passed feasibility screening, while
Task 7 is blocked by its 2/5 clean result. Neither outcome authorizes a pilot.
No disturbance, CoPE, or formal experiment was launched.

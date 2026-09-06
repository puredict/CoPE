# Phase 3 adapter audit

Date: 2026-09-06. Learned-policy execution status:
`BLOCKED_VLA_ADAPTER_UNAVAILABLE`.

Production OpenVLA source was found and wrapped. A usable checkpoint and
runtime are not available in the tested local environment. The remote host
has source and checkpoint files, but all eight GPUs were allocated at the
time of the dependency check. No oracle or scripted executor was substituted
for a VLA pilot.

## Sources inspected

The repository's existing `libero_experiment_core.py` provides
`ExperimentConfig` and `load_model_and_processor`. The latter loads the real
model, validates the requested normalization key, and uses a local processor
fallback for offline checkpoints. The native plugin calls this loader and
the production `experiments.robot.robot_utils.get_action` observation client.
It does not wrap the legacy simulator-owning rollout/backend object.

Workspace search also located actual source snapshots at:

```text
/Users/lijingsu/Documents/Codex/2026-07-15/files-mentioned-by-the-user-config/outputs/cjt_code_snapshot_20260723/openvla/
```

| Source relative to that directory | SHA256 | Finding |
| --- | --- | --- |
| `_legacy_openvla/experiments/robot/robot_utils.py` | `d513c071fb8eaade42a5bc591a48022c11b63bfd58380d0cf319dcc3bdabb976` | Base client accepts config, model, public observation, instruction, processor; returns one 7-D action. |
| `_legacy_openvla/experiments/robot/openvla_utils.py` | `72a1a382172c67068c96f47d1c2d8f16925d2e0deda9c745829a7f2ee6b1c865` | Reads `full_image`, constructs the language prompt, calls `predict_action(..., do_sample=False)`; does not use object poses or simulator state. |
| `franka_deploy/openvla_oft_policy.py` | `f58cf098b7a877552278add1afd6003b93230e51c16854aa44db39adafa0f8f3` | Production OFT observation client is Franka-specific: expands its 7-D proprioception to 8-D and changes gripper convention. Its semantics were not silently adopted for LIBERO. |

The base-client wrapper reconstructs validated HxWx3 uint8 RGB arrays after
JSON journal restoration because the actual client uses `PIL.Image.fromarray`.
An injected inference test exercises that real PIL entrypoint and rejects
empty, ragged, fractional, out-of-range, and incorrectly shaped images.

## Protocol and admission

`VLAAdapter` supplies `reset`, `begin_subgoal`, `act`, `close`, explicit identity,
learned-policy and privileged-state declarations, and snapshot/restore for
stateful clients. `load_vla_adapter('module:factory', config=...)` is lazy and
closes a client that fails admission. The built-in factory is
`cope_benchmark.repeated_v2.vla_adapter:create_native_openvla` and requires a
local checkpoint, pinned checkpoint SHA256, and a production base-OpenVLA
runtime path. It does not download missing checkpoints or dependencies.

Formal admission requires exact Boolean `learned_policy=True` and
`uses_privileged_state=False`, consistent provider identity, nonempty provider,
model, and adapter identifiers, no oracle/mock/scripted/heuristic identifiers,
a supported explicit action space, 7-D actions, and a positive chunk horizon.
It hashes actual local checkpoint contents and refuses mismatches and disabled
hash verification. Standard Hugging Face file symlinks are resolved without
copying; directory symlinks, broken/cyclic links, and link/file mutation during
hashing fail closed. The digest retains the sorted snapshot-relative names,
NUL separators, and binary per-file digest algorithm used by formal freeze.
These are admission checks, not proof
that an arbitrary third-party plugin's declarations are honest; source and
runtime identity remain part of the formal freeze audit.

The policy receives only detached public RGB/proprioceptive arrays and
observation references/timestamps. Unknown keys and nested nonnumeric sensor
payloads fail closed. The native inference call receives sensor arrays plus
compiled language, with metadata removed. Environment handles, task IDs,
object poses, contacts, and canonical commitments are excluded.

Raw actions are preserved. Gripper normalization/binarization/inversion is
performed once by the common executor, according to the declared action
space. NaNs, infinities, booleans, complex values, bad action dimensions, and
oversized chunks are rejected.

The native factory checks `nvidia-smi` before model loading and rejects busy
devices or devices with compute processes. It selects one physical GPU in a
fresh worker before importing Torch. Native snapshots carry instruction,
seed, checkpoint identity, CPU RNG, and only the selected already initialized
CUDA device's RNG; they do not seed or restore every GPU.

## Dependency evidence and pilot limit

The tested local interpreter has `torch==2.10.0`, `transformers==5.3.0`, and
`draccus==0.10.0`. Import discovery found no `tensorflow`, `timm`, or installed
`prismatic`. `nvidia-smi` is absent. Both expected server checkpoint paths
(`.../openvla-7b-finetuned-libero-10` and
`.../openvla-7b-finetuned-libero-spatial`) and the default
`/home/lijingsu/vla/src/openvla` runtime do not exist locally. No OpenVLA model
directory was found in the local Hugging Face cache. Source snapshots alone
do not provide weights or establish model compatibility.

Calling the built-in factory with the located base runtime and the expected
LIBERO10 checkpoint path returned:

```text
BLOCKED_VLA_ADAPTER_UNAVAILABLE local OpenVLA checkpoint missing: /home/lijingsu/vla/models/openvla-7b-finetuned-libero-10
```

No inference or GPU initialization occurred.

The initial direct remote SSH probe on port 26575 timed out. A later connection
through the existing `fudan-26575` alias succeeded. Read-only inspection found:

- `/home/lijingsu/vla/src/openvla/experiments/robot/robot_utils.py`, digest
  `d513c071fb8eaade42a5bc591a48022c11b63bfd58380d0cf319dcc3bdabb976`.
- `/home/lijingsu/vla/src/openvla/experiments/robot/openvla_utils.py`, digest
  `539687fa13e8fc69b79289cbb2be1b7e1076dcaae4dc0cbfb5e76c6739a38e61`.
  This differs from the local snapshot, so the native identity records both
  dispatch-client and inference-utility hashes.
- `/home/lijingsu/vla/models/openvla-7b-finetuned-libero-10` contains its
  `config.json`, model index, four model shards, processor/tokenizer files,
  and `dataset_statistics.json`. Weight bytes were not read or fully hashed;
  this verifies file presence only, not formal checkpoint admission.
- `/home/lijingsu/vla/.venv/bin/python` discovers NumPy, Torch, Transformers,
  TensorFlow, timm, and draccus. OpenVLA/Prismatic and LIBERO source trees exist
  under `/home/lijingsu/vla/src` and need source paths in that environment.

The parent's `nvidia-smi` probe found memory use of 4205, 2157, 2157, 10163,
10813, 10375, 1781, and 1781 MiB on GPUs 0 through 7, with utilization
0, 37, 69, 0, 0, 0, 16, and 0 percent. None passed the native factory's
idle-device gate (including at most 256 MiB allocated memory). No remote GPU
or model was used. Rechecking genuine idle capacity and validating exact
checkpoint bytes are prerequisites for a later VLA pilot.

## Continuation backend

`ContinuationPlannerBackend` loads the existing archived `rekep_repair`
package under
`research/server_sync_20260905/content/fvl12/v/cope_r4_20260905/code`.
Its Python-source content digest in this test was
`447e1257ae8d62a78b6f995e398722589b2efe4794a11a1d679e534c99601488`.
The actual `RepairGoal`, synthesis generator, repair manager, continuation
restore contract, and `TaskProgram` splice/resume implementation are used.

The wrapper sends the complete accepted problem unchanged to the nominal
backend. It only derives recovery requirements from explicit accepted
`continuation_assumptions['repair']`, and takes physical observations from
one explicitly public `repair_observation` belief. Unsupported or absent
recovery semantics remain unsupported or absent. It never imports the old
CoPE compiler, reads canonical truth, or reconstructs omitted baseline goals.

The archived operator model is 2-D (`x`, `y`, `theta`). A public perception
projection and public recovery verifier must be supplied; no automatic
6-D-to-2-D grounding or privileged verifier is invented. Capture occurs before
injection; planning requires fresh post-event evidence. Candidate admission
checks both the accepted goal and the actual captured handoff contract even
when an injected verifier reports `ok=True`. Recovery operators must finish
in order with fresh observations, and the nominal suffix stays locked until
verified restoration. Repeated interruptions retain the same program.

Snapshots restore the selected program without rerunning search or verification.
They contain JSON data, a content digest, dependency identity, and immutable
nominal-plan state. The actual phase-2 `ExecutionPlan` compatibility test
caught and fixed a diagnostics type mismatch: continuation audit entries are
serialized strings for its strict `tuple[str, ...]` diagnostics field.

Mocked tests establish boundary behavior and crash-resume mechanics only. A
production public recovery verifier and a grounded simulator bridge remain
separate gates before claiming physical continuation recovery success.

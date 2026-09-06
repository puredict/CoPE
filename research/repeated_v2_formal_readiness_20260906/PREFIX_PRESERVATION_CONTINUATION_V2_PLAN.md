# Versioned CPU prefix/preservation continuation preparation

This is a new, explicitly versioned sub-evidence stage. The original stopped sweep and all original raw bytes remain unchanged. Preparation is complete; this document does not authorize execution or claim new simulator evidence.

The candidate driver is `PREFIX_PRESERVATION_CONTINUATION_V2.txt`, SHA256 `7e072dad02a8cb92ba52c7ee8ecb534912f4b5e6e116eb6b97103e70da38573a` (66,435 bytes). Its observation-boundary protocol SHA256 is `e9abf5d9f49c7401a71ca510b4133360b9c038c6b78d064c6ba3f7bf9e7cce93`. The independent review and parent authorization must refer to this exact driver hash.

## Original evidence and reason for the new stage

The original driver remains SHA256 `5a079ae2fe4dd4883c1b65b49223d2d2f644582aab836ade89c2ec7c0f7e469d`. Original container `prefix_preservation_20260906T180046Z_6aef8497` contains a stopped task 0/state 0 sweep. Its pinned 13-file inventory SHA256 is `04b8c75eaae1abc60664ca322854693843a6e260590ca0428094c05030bfd09d`; the stopped receipt SHA256 is `7b59f89d2a5019ad23125ae26fe6a510e789f829b6f11f5647f4346c6bd68e28`.

The prefix has 197 complete, alternating intent/result pairs: 10 warmup, 172 placement-skill, 10 explicit-release, and five freshly stepped stability controls. The five samples record the exact soup-in-basket predicate true and no object grasped; tomato-in-basket remains false. This establishes one released first placement, not full-task success. The physical seal is float64[123], SHA256 `edcddba7d6a16d8d786ad9bec10d82652e393c3bf8baae62c7afdf162677242c`. No event injector ran and the other 19 prefix cells were unattempted.

The first restore reproduced every flattened-state byte and every checked commitment, grasp, and object pose. Its EEF observation differed from the cached last-step observation by at most 4.7168e-7 m per axis. Separate zero-control diagnostic `zero_step_diagnostic_20260906T180437Z_01653748/RESULT.txt`, SHA256 `da82064d9d2134ad8f60506c5c7cf28ddc0c0e253486d51f12407611014d559d`, confirmed that all five fixed-state getter/restore variants agree with the authoritative recomputed EEF site, with exact sealed state/time and zero environment steps. Installed sensor-sampling code supports the cache-timing explanation. The diagnostic did not replay the original last step or prove arbitrary Python/controller-state completeness. The new stage does not widen the 1e-10 m restore tolerance.

## Permitted scope and accounting

| Item | Inherited original evidence | New continuation stage |
| --- | ---: | ---: |
| Distinct prefix cells | task 0/state 0 | the other 19 cells from tasks 0, 1, 4, 8 × states 0–4 |
| Placement-skill calls | 1 attempted and returned | at most 1 per previously unattempted cell |
| Environment controls | 197 attempted and returned | actual separately recorded attempts/results |
| Replay of task 0/state 0 prefix | 0 | forbidden by branch and control guard |
| Candidate target-event rows | 0 executed in original | same 135 mechanically witnessed rows, conditional on an available prefix |
| Paired setup applications | 0 executed in original | at most the existing 40 setup payloads |

The standard-library lineage gate checks all 13 original artifact hashes, closed membership of the original raw directory, exact 197-pair control IDs/order/labels/timesteps, the five released-goal samples, original-state identity, exact serialized seal, original no-event stop, and the pinned diagnostic. It authenticates the first cell before simulator imports. The first cell loads the sealed physical prefix directly; no warmup, placement, release, or five-step prefix test is repeated. Its inherited five checks retain their original-stage provenance. Fresh fixed-state semantic checks must agree with the authenticated prefix and diagnostic before any event branch.

The other cells retain the original single centered grasp, source-derived first placement goal, seed 101, max_move_steps 60, 620-prefix-control cap, five-control post-event cap, and 630-total-control cap. For the inherited cell the 197 prior controls are included in the total cap. Failed physical attempts remain failures/skips; no goal substitution, retuning, candidate selection, or retry is permitted.

## New observation boundary

At each explicit stability observation, prefix seal, and post-restore boundary, the driver temporarily forbids both outer and inner environment steps, saves the physical state, calls `sim.forward()` and `_get_observations(force_update=True)`, and records cached and fresh observations separately. It requires identical flattened-state bytes/dtype/shape, qpos, qvel, time, and control/denial counters, plus EEF agreement with the recomputed site within the unchanged 1e-10 tolerance. Any failure to obtain or durably publish this evidence stops the entire stage. The original cached first-cell EEF and its fresh replacement remain distinct fields.

The raw control trace retains actual env.step intents/results and each fresh boundary has its own receipt; a forced getter is never counted as a physical step. The simulator sensor/controller source bytes are checked against the diagnostic before and after the stage.

Each event branch begins and ends with an exact physical restore to the normalized authentic prefix. Injection payloads and paired setup payloads come byte-for-byte from the prior mechanical witness receipts. Changed physical states, active no-go routes, and unavailable-tool routes receive no controls. Only unchanged inactive states for the previously whitelisted clearance/preference candidates can receive five zero-motion, open-gripper controls with fresh exact predicate checks. A candidate that displaces the newly completed object may lose that protected predicate; this is candidate/prefix incompatibility evidence, not general family/task infeasibility. Task 8's stove-without-free-joint receptacle variant stays unsupported.

## Execution packaging, after exact-hash review and authorization

Only the new driver needs deployment if the pinned source, original inventory, and diagnostic are already present remotely. Use `scp -O` and verify the remote SHA before invocation. Create a unique timestamped container outside the original evidence tree, then use a new `raw` child as output. The driver rejects any output inside the original container before writing. An exclusive readiness-level `PREFIX_PRESERVATION_CONTINUATION_V2_EXECUTION_CLAIM.txt` prevents duplicate invocations of this stage; no automatic continuation follows a stop.

From `/home/lijingsu/codex-worktrees/cope-repeated-v2-phase4`, the execution shape is:

```sh
env CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
  LIBERO_CONFIG_PATH=/home/lijingsu/.libero PYTHONDONTWRITEBYTECODE=1 \
  scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  research/repeated_v2_formal_readiness_20260906/PREFIX_PRESERVATION_CONTINUATION_V2.txt \
  --execute \
  --expected-driver-sha256 7e072dad02a8cb92ba52c7ee8ecb534912f4b5e6e116eb6b97103e70da38573a \
  --output-dir /absolute/new/timestamped/readiness/container/raw
```

The outer launcher must record the resolved command, exact environment, worker PID/exit status, and stdout/stderr, preserve any failure, and remove provider credentials from that subprocess environment. No GPU, provider, policy, or running-calibration process is used. After termination, copy the complete new output container and verify an independent byte inventory. Original evidence is only read.

## Preparation validation and limits

`PREFIX_PRESERVATION_CONTINUATION_V2_VALIDATION.txt` records real standard-library lineage validation, two lineage rejection cases, and two output-path rejection cases before filesystem mutation. Seven isolated mocked boundary cases exercised stale-cache normalization, qpos mutation, getter exception, wrong fresh EEF, publication exception, and swallowed outer/inner step attempts. The invalid cases stop; these mocks performed zero real simulator/controller/provider calls and are not empirical robot evidence.

This work does not certify safe injection, trigger eligibility, collision safety, recoverability, or catalog feasibility. It is not learned-policy calibration, a production benchmark result, general crash-safe resume, or a claim that a flattened MuJoCo state serializes all controller/observable/RNG internals. Any future report must keep the original stopped stage, no-step diagnostic, and new versioned continuation separate, with inherited and new control counts explicit.

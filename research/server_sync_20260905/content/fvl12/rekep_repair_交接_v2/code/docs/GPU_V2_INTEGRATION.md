# v2 GPU integration — exact call sites

`REMOTE GPU SERVER ONLY`. Nothing here has been executed.

The v2 runner keeps ReKep **subclassed, never modified**. Four changes to the v1
`RepairedMain`:

## 1. Build a `ShadowRolloutHost` from the live environment

```python
class OmniShadowHost:
    def save_checkpoint(self):
        return og.sim.dump_state(serialized=False)      # full scene state
    def restore_checkpoint(self, ck):
        og.sim.load_state(ck, serialized=False)
        og.sim.step()                                    # settle
    def state_hash(self):
        import hashlib, numpy as np
        parts = [self.env.robot.get_joint_positions()]
        for name in ("pen_1", "pencil_holder_1"):
            o = self.env.og_env.scene.object_registry("name", name)
            p, q = o.get_position_orientation()
            parts += [np.asarray(p), np.asarray(q)]
        buf = np.concatenate([np.asarray(x, float).ravel() for x in parts])
        return hashlib.blake2b(np.round(buf, 6).tobytes(), digest_size=8).hexdigest()
    def simulate_operator_sequence(self, operators, budget_steps):
        # drive the operators through ReKep's OWN _get_next_subgoal/_get_next_path
        # + env.execute_action, counting OSC warnings and workspace clips, and
        # querying contacts for `collision`.
        ...
```

`state_hash` must cover everything the rollout can change. The verifier asserts
it matches the checkpoint hash before **every** candidate and raises
`StateIsolationError` otherwise.

## 2. Insert the verifier before the scorer

v1 (defective):
```python
selected = Scorer(params).select(survivors, event)      # rollout is None -> "no-rollout"
```
v2:
```python
verifier = GPUCandidateVerifier(OmniShadowHost(...), RolloutLimits(), logger=log)
results  = verifier.verify_all(survivors)
best     = select_best(results)                          # measured quantities
if best is None:
    log.emit("SAFE_FALLBACK", reason="no candidate survived verification")
```

## 3. Install the real restore contract

v1 (tautological):
```python
Contract(predicate=lambda state, keypoints=None: self._native_solver_verified)
```
v2:
```python
contract = ContinuationRestoreContract(
    handoff_ee_position=ee_pose[:3], handoff_ee_orientation=ee_pose[-4:],
    required_attachment="grasped", relocated_target_position=holder_now,
    reference_pen_position=pen_at_capture)
continuation = Continuation(..., resume_contract=contract.as_task_program_contract(
    lambda: dict(ee_position=self.env.get_ee_pose()[:3],
                 ee_orientation=self.env.get_ee_pose()[-4:],
                 active_target_position=self._holder_position(),
                 attachment_state="grasped" if self._held() else "released",
                 pen_state=RigidBodyState.of(*pen.get_position_orientation()),
                 collision_free=self._no_contacts(),
                 stage_entry_satisfied=self._stage3_entry_ok())))
```
The state provider is called **at gate time**, so the decision uses live state.

## 4. Record everything the success metric needs

At episode end record: holder `inner_radius`/`rim_height`/`bore_depth` (from the
USD bbox), pen `length`/`radius`, pen and holder pose, pen linear+angular
velocity, and the **last 12 pen states** as `state_history`. Then:

```python
ev = PenInHolderEvaluator(pen_geom, holder_geom).evaluate(
        pen_state, holder_state, attachment_state, history)
log.emit("TASK_SUCCESS_EVALUATION", **ev.to_dict())
```

## Measuring the geometry once, on the host

```bash
# REMOTE GPU SERVER ONLY -- print the real asset dimensions, then paste them in
python - <<'PY'
import omnigibson as og
# load the pen scene, then:
for name in ("pen_1", "pencil_holder_1"):
    o = og.sim.scene.object_registry("name", name)
    print(name, o.aabb_extent, o.aabb_center)
PY
```

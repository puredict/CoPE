# Pre-run reserved-state lock clarification

Date frozen: 2026-08-02 (Asia/Shanghai)

Parent preregistration commit: `3305dc298e383db8a17a64e3d2257cd67c0bee34`

This clarification was written before implementation and before any assigned
X04 result was observed.

The original preregistration says that states 25--49 "must not be read."  The
upstream LIBERO benchmark API stores all task initial states in one PyTorch
file and implements `get_task_init_states(task_id)` as one `torch.load` of the
whole file.  Therefore, resetting even state 0 necessarily deserializes the
shared container that also contains states 25--49.  Selective file-level
deserialization is not supported by the upstream format.

The operational lock is consequently defined as follows:

- only manifest-assigned indices 0--4 may be indexed and passed to
  `env.set_init_state`;
- states 25--49 may not be indexed, hashed individually, logged, rendered,
  summarized, compared, or used for any reset;
- the shared init-state file may be verified only by its preregistered whole-file
  digest;
- the runner must reject any case manifest containing an index outside 0--4;
- results cannot authorize state 25/26 automatically; a separate readiness
  decision remains required.

No case, object, event, stability threshold, or pass criterion changes.  This
clarification prevents an impossible literal interpretation of the upstream
storage API while preserving the intended experimental holdout.

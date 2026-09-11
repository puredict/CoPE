# Test execution summary

- Repeated-v2 suite on the branch implementation: `932 passed, 1 skipped, 100 subtests passed in 92.33s`.
- Full repository on server `fvl12`, existing Git worktree, detached at `74c1e7b24bfec55398d8dc2f5be38b2f78691c00`, with `CUDA_VISIBLE_DEVICES=`: `1580 passed, 1 skipped, 100 subtests passed in 215.37s`; exit 0.
- Full repository on the Mac: `1579 passed, 1 failed, 1 skipped, 100 subtests`. The single failure verifies a retained semantic-oracle authorization whose BDDL and initialization-state paths are intentionally absolute `/home/lijingsu/vla/...` paths. Those hash-pinned files are present on `fvl12` and absent on the Mac. The exact Git-worktree server run passes that test.

No test threshold, old authorization record, or production gate was modified to obtain the passing run. Both outputs are retained.

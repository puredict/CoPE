# Semantic feasibility audit diagnosis

The zero-provider development-state audit evaluated every registered event
family on initial-state IDs 15--19. It produced 420 measured cells: 417 passed
and three failed. Nine of ten task-level feasibility certificates are complete.
The audit made zero provider calls, zero learned-VLA calls, and zero formal
trajectories.

All three failures belong to task 0 and initial state 18. Each failure is
isolated to `physical_feasibility_guard`; semantic trigger reachability,
registered-window membership, fresh post-event observations, no policy-step
consumption, pure compilation, dynamic evaluation, solution existence, and
unrelated-progress preservation all passed.

| Event family | Frozen intervention | Penetrating contacts before | Penetrating contacts after | Result |
| --- | --- | ---: | ---: | --- |
| `TARGET_OBJECT_DISPLACED` | `alphabet_soup_1`, delta `[0.06, 0.0]` | 115 | 134 | Failed physical-feasibility guard |
| `TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE` | `alphabet_soup_1`, release delta `[0.04, 0.0]` | 115 | 127 | Failed physical-feasibility guard |
| `TOOL_OR_TARGET_AVAILABLE_AGAIN` | `alphabet_soup_1`, release delta `[0.04, 0.0]` | 115 | 127 | Failed physical-feasibility guard |

The result is retained as measured evidence. No collision threshold was changed
and no cell was deleted. The catalog builder therefore excludes the failed
task/event combinations from task 0's eligible frozen schedule while retaining
the other passing task/event combinations. This is an explicit unsupported
declaration for schedule eligibility, not a fabricated pass.

The exact source evidence is in `SEMANTIC_FEASIBILITY_RESULTS.jsonl`; its SHA256
is `b91a130e1c6269aa6bbb8ebf0ea180bba73018f6b3d31a0b8e61f58e7b06b106`.
The frozen parameter artifact SHA256 is
`1981351adf93d1f0eb6ac8bb4e5ce5d49b965107f3da0c8d50df02655f0e5b07`.
The audit source commit is
`b195456ff97170a05d342556fce1fc493f353930`.

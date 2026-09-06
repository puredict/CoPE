# Required modification and patch list

## P1 — OpenVLA SDPA compatibility patch: required

- artifact: `03_OPENVLA_REQUIRED_SDPA_PATCH.txt`
- artifact SHA-256:
  `eb343b0846b35c88d54b354f6d730b7547282b7a42cb0bd01462699cf10231df`
- base: OpenVLA `c8f03f48af692657d3060c19588038c7220e9af9`
- result: `9bf418e79d019d416860990d60379d66f0c06220`
- branch: `codex/openvla-cope-sdpa`
- reason: select PyTorch SDPA because the environment does not contain
  `flash-attn`; also correct the loader message.
- scope: one file, two replacements, no runner or task behavior change.
- validation: `git diff --check`, Python AST parse, empty final porcelain.

## P2 — CoPE runtime identity pin patch: required

- artifact: `07_COPE_RUNTIME_PIN_PATCH.txt`
- artifact SHA-256:
  `fa5b0e3a929f595abff8b539622e5276c567d5c826ff955750ec1d7e2e4cefe6`
- base: CoPE `fba9f32b502c8301687559a62101293105f17254`
- result: `21b90aed9e2e64152a7bfe0c85553f2ffbc5e730`
- branch: `codex/cope-true-clean-runtime`
- changes:
  1. replace the undocumented checkpoint aggregate with the reproducible
     path+size+SHA-256 aggregate `2990c991...`;
  2. pin the isolated OpenVLA and official LIBERO commits/paths;
  3. make `scripts/run_project_env.sh` fail closed to those clean sources and
     the isolated LIBERO config directory.
- validation: shell syntax, YAML/CSV parsing, one targeted repository test,
  clean LIBERO path resolution, empty final porcelain.

## Explicitly excluded modification

The original `run_libero_eval.py` smoke-limit patch was not carried forward.
It is not required for the formal runner and retaining it would enlarge the
method-independent runtime delta without necessity.

## LIBERO

No LIBERO source patch exists. The clean runtime is byte-identical to official
commit `8f1084e...`. The only generated runtime material is an external path
configuration (`06_LIBERO_CONFIG_CLEANROOM.txt`) and an explicit shallow Git
boundary (`04_LIBERO_SHALLOW_BOUNDARY.txt`).


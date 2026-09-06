# CoPE Experiment 1 Implementation Package

This package is a complete code-level specification for handing Experiment 1 to Codex.

Files:

- `00_CODEX_MASTER_PROMPT.md`: single-window implementation prompt.
- `01_FROZEN_SCIENTIFIC_PROTOCOL.md`: preregistered scientific design.
- `02_CONFIG_TEMPLATE.yaml`: machine-oriented default configuration.
- `03_DATA_AND_METHOD_CONTRACTS.md`: key interface contracts.
- `04_PHASED_CODEX_PROMPTS.md`: four smaller Codex prompts.
- `starter/repeated_v2_types.py`: starter Python contracts, not a finished implementation.

Recommended use:

1. Put this package next to a clean checkout of `puredict/CoPE`.
2. Give Codex `00_CODEX_MASTER_PROMPT.md`.
3. If context limits become a problem, use the four phased prompts in order.
4. Require a commit after every phase.
5. Do not allow a formal run until the task catalog, manifest, prompts, schemas, model identities, and code SHA are frozen.
6. Do not accept oracle-controller output as learned-VLA evidence.

The scientific design keeps the current paper boundary:
- runtime Experiment 1 tests persistent state maintenance and downstream execution;
- continual post-training is a different experiment and is not implemented here.

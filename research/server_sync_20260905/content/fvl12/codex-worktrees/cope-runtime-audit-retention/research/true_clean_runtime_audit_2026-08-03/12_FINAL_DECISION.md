# Final decision

## Verdict

**Current-host content-addressed runtime: PASS.**

The established CoPE, OpenVLA, and LIBERO source trees are isolated, committed
or bound to an official commit, clean, and covered by file/tree hashes. The
checkpoint, runners, configs, environment variables, reservation inventory,
and absent output target pass the 53-check preflight.

**Fully reproducible cold rebuild: FAIL.**

The Python environment is still a shared existing venv. Its exact version
freeze, interpreter hash, critical package versions, selected RECORD hashes,
and import resolution are known and pass on `fvl12`, but the complete wheel or
sdist artifact set is not retained with SHA-256. A version-only `pip freeze`
cannot guarantee byte-identical reconstruction on an empty host.

**Reserved-state formal experiment: NO-GO.**

This audit closes the dirty OpenVLA/LIBERO source problem for the current host,
but it does not change readiness v3's separate scientific blocker: the live
semantic recovery path has not yet been qualified as provider-driven rather
than oracle-generated. No state 27--49 may be consumed. States 47--49 remain
permanent reserve.

## Minimal remaining blockers

1. Build and retain a complete Python wheelhouse or equivalent immutable image,
   with SHA-256 for every artifact; install it into a new isolated venv using
   `--require-hashes`; rerun the same preflight with the new interpreter.
2. Durably retain/push the two local runtime commits or retain their patch
   artifacts with the final audit checksum manifest. The commits currently
   exist only in the remote repositories' local object databases.
3. Complete the separately preregistered X15 provider-driven live semantic
   bridge qualification on development states only, then regenerate the full
   formal readiness decision. Runtime PASS alone must not unlock reserved
   states.

No blocker was bypassed and no dirty directory is claimed as clean.


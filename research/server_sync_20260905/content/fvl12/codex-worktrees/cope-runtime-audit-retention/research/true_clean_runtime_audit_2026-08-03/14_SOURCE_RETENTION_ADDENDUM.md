# Source-retention addendum

Date: 2026-08-03 (Asia/Shanghai)

The source-reconstruction portion of blocker 2 in `12_FINAL_DECISION.md` is now
closed to the extent possible without an authorized external Git destination.

- The complete text-only audit directory, including the OpenVLA SDPA patch,
  CoPE runtime-pin patch, clean-room reconstruction instructions, preflight,
  reservation lock, and checksum manifest, is retained on the local workstation.
- The same directory is committed on the remote clean-runtime branch at
  `08ae02691914676a19fbf7e47f229627b214d95b`.
- `sha256sum -c 13_SHA256SUMS.txt` passes for all 14 protected audit payloads on
  the remote host.
- A secret scan of the retained directory is clean.

This provides two-host retention of independently applicable patch artifacts;
reconstruction does not depend only on the OpenVLA and CoPE local Git object
databases. It does not claim an off-site repository push.

The remaining cold-rebuild blocker is the Python binary environment: the exact
installed versions and selected RECORD hashes are known, but a complete
retained wheel/sdist set or immutable image has not yet been built and verified.
Current-host content-addressed runtime status remains PASS; empty-host cold
rebuild status remains FAIL.

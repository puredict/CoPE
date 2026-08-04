# Credential and artifact security audit

Date: 2026-08-04

## Decision

**PASS for repository and known formal-gate artifacts.** No OpenRouter key
prefix was found in the current worktree, reachable Git history, or the two
known provider-smoke credential-block directories.

The key previously pasted in conversation was not copied, invoked, stored, or
reconstructed.

## Checks

- current worktree path-only scan for the OpenRouter key prefix: 0 files;
- reachable Git-history string search for the key prefix: 0 commits;
- known smoke-block run directories: 0 files with the key prefix;
- six files mentioning `Authorization` or `Bearer` were classified by pattern
  without printing their contents: 0 token-like bearer literals and 0
  OpenRouter key prefixes;
- no `.env` or `.env.*` file exists in the worktree;
- the only secret-named file is `tools/launch_with_secret_env.py`, an
  interactive getpass launcher that passes the value through a child-process
  environment and does not place it in argv or its log.

## Expected non-secret references

Provider source code necessarily contains an `Authorization` header template,
and tests/research records mention authorization behavior. These references
contain variables, redaction markers, or prose rather than credential values.

## Launch boundary

The live operational smoke remains blocked until a human securely injects
`OPENROUTER_API_KEY` into the remote process. The credential must not be placed
in a shell command, output directory, report, Git file, chat message, or shared
log. Passing it through the environment is required by the frozen provider
adapter; users with permission to inspect the same process could still inspect
that process environment, so the launcher must run under the personal
`lijingsu` account rather than the shared account.

## Scope limit

This is a targeted repository and known-artifact scan, not a forensic audit of
all files or inaccessible process state on the server. No claim is made about
credentials that may exist outside the inspected scope.

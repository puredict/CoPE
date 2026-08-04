# Formal ledger directory durability amendment

Date: 2026-08-04
Status: implementation hardening before live formal calls

## Gap

The formal recovery ledger fsynced every metadata, intent, response, and result
record. On first creation of an output directory or journal file, it did not
also fsync the parent directory entry. Process-crash recovery was protected,
but a host/filesystem crash retained a theoretical directory-entry durability
window.

## Amendment

- fsync the parent after creating the run output directory;
- fsync the run directory after exclusively creating metadata;
- when an append journal is created for the first time, fsync the run
  directory after fsyncing the record;
- retain file fsync on every append.

The ordering remains metadata -> call intent -> provider response -> result.
No retry, prompt, arm, outcome, threshold, or manifest changed.

## Verification

A focused test intercepts fsync calls and confirms both regular-file and
directory descriptors are synchronized during ledger creation and the first
intent. Existing crash/recovery tests continue to enforce torn-line,
duplicate-cell, metadata-drift, missing-intent/response, and ambiguous-call
rules.

## Scope

`fsync` improves persistence ordering but cannot guarantee behavior of every
remote filesystem, storage controller, or hardware failure mode. The precise
claim is crash-consistent journaling under the host filesystem's documented
fsync semantics, not absolute exactly-once execution across arbitrary external
provider failures.

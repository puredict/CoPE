# Terminal-action audit journal recovery

Date: 2026-08-04

The remote SSH connection closed after the state-7 result was delivered to the
client.  Read-only inspection found no surviving process, but the append-only
journal contained all 20 unique preregistered cells, including reverse states 8
and 9.  The original process had therefore completed every environment episode
and appended every result before losing the connection, but had not published
the derived CSV/report/checksums.

No cell will be rerun.  A deterministic finalizer must validate exactly one
row for each `(forward|reverse) x state 0..9`, reject malformed or duplicate
rows, and derive the missing aggregate files from the retained journal.  It may
not edit the journal or metadata.  This recovery changes no endpoint and makes
no provider or simulator call.

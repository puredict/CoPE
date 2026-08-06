# Task-0 terminal-action development audit preregistration

Date: 2026-08-04

## Purpose

Qualify the complete physical substrate for the double-replacement sequence
before opening any task-0 formal state.  The semantic terminal directive selects
`butter_1`; this audit tests whether the shared controller can execute that
placement after either qualified prefix orientation without moving stale B/C.

## Frozen cells

Task 0, development states 0--9, two separately reset orientations:

1. forward: A=`alphabet_soup_1`, B=`tomato_sauce_1`;
2. reverse: A=`tomato_sauce_1`, B=`alphabet_soup_1`.

C=`cream_cheese_1`, D=`butter_1` in both.  Total: 20 cells.

## Procedure and endpoint

Use controller configuration hash
`56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a`.
After reset, place A in the basket and require five consecutive snapshots
exactly A=true, B=false, C=false, D=false.  Then place D and require five
consecutive snapshots exactly A=true, B=false, C=false, D=true.

Each cell passes only if both controller placements succeed and both stability
requirements hold.  Retain action hashes, action count, simulator hash, regrasp
activation and failure class.  Gate requires 20/20.  Provider calls are zero.

Any failure blocks formal provider calls and is repaired only on development
states.  No task-0 state 10--49, task-7 formal state, or locked task-1 state is
opened by this audit.

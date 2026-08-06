# Auditability Annotation Guide

Status: version 1.0

Time unit: seconds

Personal information collected: none

## Purpose

The study measures how accurately and efficiently an auditor can answer questions
from a blinded evidence package. The package label (`C00`, `C01`, or `C02`) is an
opaque balancing code. Do not try to identify the underlying method.

Do not provide private chain-of-thought. Record only the answer, supporting record
IDs, failure layer when asked, confidence, and elapsed time.

## The Six Question Types

1. Behavior change: identify the logged reason for a pause, stop, or changed action.
2. Constraint change: name the affected constraint and the event or constraint that
   overrode, suspended, or expired it.
3. Preference persistence: decide whether the named user preference remains active
   after interruption.
4. Restore/Revalidate: decide whether a successful Revalidate occurred before the
   Restore and is explicitly linked to it.
5. Alignment freshness: decide whether post-move behavior uses an old alignment or
   a newly evidenced alignment.
6. Failure localization: select the earliest supported layer from `perception`,
   `event_detection`, `full_regeneration`, `patch_generation`, `schema_parsing`,
   `validation`, `planning`, `low_level_control`, or `termination_accounting`.

## Annotation Procedure

1. Start the timer when the item is displayed.
2. Read the question before inspecting evidence.
3. Use only evidence in the package. Do not use method identity, outside experiment
   knowledge, or assumptions about hidden model reasoning.
4. Enter a short normalized answer.
5. Copy every event, patch, slot, validation, action, state, or other record ID that
   directly supports the answer into `supporting_ids_json`.
6. If the answer is not determined by the package, set `answerability` to
   `unanswerable` and explain nothing beyond a short optional adjudication note.
7. Record confidence from 1 (guess/very uncertain) to 5 (direct and unambiguous).
8. Stop the timer and record elapsed wall-clock time in seconds.

IDs must be copied exactly. A plausible answer without a resolvable provenance ID
does not count as provenance-linked.

## Restore and Revalidate Rule

A Restore is valid for this study only when it names an existing successful
Revalidate, the Revalidate occurs no later than the Restore, and the evidence links
the validation to the restored slot or state. A nearby validation without a
reference is not sufficient.

## Failure-Layer Rule

Choose the earliest layer with affirmative failure evidence, not the layer where
the failure was finally noticed. A timeout caused by an earlier invalid patch is a
patch-generation or validation failure when the evidence establishes that earlier
cause; it is not automatically termination accounting.

## Adjudication

Items with disagreement, invalid/missing provenance, or any
`unanswerable_from_ground_truth` status go to adjudication. The adjudicator:

1. reviews the raw simulator event, method-visible event, patch, validation,
   controller, termination, progress, and lineage records in that order;
2. corrects only evidence-backed labels;
3. preserves all original annotations;
4. records the final answer, supporting IDs, reason code, and adjudication note.

If the trace itself cannot establish the answer, the final status remains
`unanswerable_from_ground_truth`; an LLM or adjudicator must not invent truth.

## Quality and Privacy

- Do not annotate your name, email, demographic information, or employer.
- Use only the assigned anonymous auditor code.
- Report malformed packages instead of repairing evidence locally.
- Do not compare packages with other auditors before independent annotation is
  complete.

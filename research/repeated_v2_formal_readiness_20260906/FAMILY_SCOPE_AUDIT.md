# Task-specific event-family scope audit

Date: 2026-09-06. This began as a read-only protocol/source/test audit. After
explicit authorization, the narrow task-support correction described below
was implemented and tested. No task catalog, measurement, threshold, or result
was changed by this work. The user's explicit correction is authoritative:
each task need not support all ten library families.

## Finding

The pre-correction code incorrectly turned experiment-wide event-library coverage
into an all-ten-families requirement for each individual task. A task with a
fully certified eight-event schedule can therefore be rejected merely because
it lacks an unused alternative grounding or retirement family.

Removing this defect does not establish that any real task is eligible.
Authenticated structural checks, measured clean-policy calibration, task-local
feasibility, valid trigger windows, and an actual admissible full master remain
required. A successful native-VLA action probe supplies none of those missing
task-semantic certificates.

## What the supplied scientific protocol actually requires

`docs/repeated_v2/specification/00_CODEX_MASTER_PROMPT.md`, section 6
(lines 287–330), lists six task eligibility requirements:

1. At least two independently verifiable milestones or goal predicates.
2. At least one completed milestone remains preservable through interruptions.
3. A safely changeable object/receptacle grounding.
4. At least one cross-skill requirement or persistent preference.
5. Clean learned-policy success in **[0.40, 0.95]** on the preregistered split.
6. Feasibility passes for all event injections required for that task's design.

That section explicitly includes `supported event families` and task-local
semantic triggers in the catalog. Selection enumerates all ten LIBERO tasks,
includes every eligible task, and requires at least eight. Selection cannot
depend on CoPE-minus-baseline outcomes. These rules remain unchanged.

Section 7 (lines 338–404) defines the ten-family library and then separately
requires each eight-event master to contain:

- a grounding shift;
- a suspend/revalidate/restore lifecycle sequence;
- a persistent preference;
- a goal replacement **or** cancellation;
- a fresh occurrence of a previously used semantic goal.

Clearance and availability endpoints must follow their corresponding opening
events. Reissue must follow retirement. Restoration requires fresh
revalidation evidence. Deterministic constrained shuffling, position balancing,
semantic triggers, and physical feasibility guards remain mandatory.

`01_FROZEN_SCIENTIFIC_PROTOCOL.md`, “Event families,” repeats those five
coverage categories rather than imposing ten different families on each task.
`02_CONFIG_TEMPLATE.yaml` defines the global library; it does not equate that
library with each task's supported-family set.

## Exact implementation sites

| Source | Current behavior | Consequence |
| --- | --- | --- |
| `task_catalog.py:253–254` | Requires each support set to equal the full ten-family library. | Rejects a certified restricted task support set. |
| `task_catalog.py:255–280` | Requires feasibility records, triggers, and physical injection metadata for every library family. | Unused, explicitly unsupported alternatives become artificial catalog gaps. |
| `task_catalog.py:304` | Requires every library family's feasibility Boolean to pass before selecting a task. | Scope remains wrong even if the first assertion is removed. |
| `scheduler.py:224–235` | Rejects any missing library family and parses every library trigger. | `supported_event_families` cannot actually constrain generation. |
| `scheduler.py:236–238` | Chooses grounding/retirement alternatives globally by index. | After merely removing the rejection, it may select an unsupported variant. |
| `preflight.py`, `all_event_families_covered` | Checks family coverage over the union of all master schedules. | This is a separate experiment-wide gate; per-task correction need not remove it. |

The manifest already passes each task's `supported_event_families` into the
balanced scheduler (`manifest.py:86`). No new representation is needed.

## Minimal, conservative correction proposal

The smallest repair preserves the current eight-event template and all existing
scientific gates. That template has both temporary pairs, preference, reissue,
one grounding alternative, and one retirement alternative: six fixed families
plus two task-supported alternatives.

1. Validate that support names are known and unique, without demanding equality
   with the full library. Unknown/duplicate support declarations must still
   fail closed. Missing support evidence must not be converted into a positive
   or into an evidenced scientific exclusion.
2. Validate feasibility, covered initial states 0–4, semantic trigger fields,
   spacing/windows, and safe physical interventions for the task's declared
   supported families. Preserve recorded unsupported/failed assessments in the
   catalog/audit; do not demand an executable trigger or safe pose for a family
   explicitly outside support. Do not use extra trigger-map entries as implicit
   authorization to schedule an unsupported family.
3. In selection, require measured feasibility for supported families and a
   complete admissible eight-event schedule using only that support. A valid
   but insufficient support set cannot qualify. Preserve explicit ineligibility
   versus unresolved evidence; neither may become an implicit pass.
4. In the scheduler, parse only supported-family triggers. Intersect grounding
   alternatives and retirement alternatives with task support before selecting.
   Keep the existing choice/order when both alternatives are available, so the
   all-ten-support fixture retains its existing deterministic behavior. When
   only one alternative is supported, select that one deterministically.
5. Keep both temporary pairs, preference, reissue, all dependencies, fresh
   revalidation obligations, exactly eight events, and all prefix checks for
   this narrow patch. Verify every generated family's membership in the
   task-specific support set independently of the trigger map.
6. Keep population enumeration, all-eligible inclusion, minimum eight tasks,
   [0.40, 0.95] calibration interval, fixed seeds/states, 260 policy-step budget,
   event spacing, and global preflight coverage unchanged. Rebuild/version
   downstream catalog/manifests and hashes where inputs actually change;
   existing experiment outputs stay immutable.

Under this conservative patch, an eight-family support set consisting of the
six existing fixed families, `TARGET_OBJECT_DISPLACED`, and
`USER_CANCELS_ACTIVE_GOAL` is a valid scope example **only when all its real
semantics, measurements, and trigger windows are certified**. It need not
invent goal-receptacle-change or replacement semantics to fill the library.
The example is not a claim that a measured LIBERO task currently qualifies.

## Related stronger restriction: distinguish it from the narrow patch

`scheduler.py:180–194` requires **both** temporary lifecycle pairs and uses
eight distinct selected families. The supplied scientific protocol requires
at least one lifecycle sequence; it does not explicitly require both pairs.
The phase-1 audit documents the chosen two-pair construction, making this an
existing implementation/design restriction, not text from the scientific
eligibility rule.

The narrow correction above deliberately leaves that construction intact. If a
task lacks one temporary pair, it can still be blocked by the current template
after the all-ten defect is fixed. Such a result must be reported as
`unsupported by the current eight-event template`, not as proof that the
scientific protocol itself requires every family or both temporary pairs.

A broader protocol-conformance change would enumerate supported eight-event
sets and validate the stated category coverage, paired dependencies, retirement
provenance, and trigger feasibility. That is a separate scheduler change with
new balance tests. This audit does not propose silently implementing it merely
to produce eight eligible tasks. In particular, neither approach may invent
unsupported tail events, duplicate a family without an explicit event-instance
design, count reobservation as an interruption, or pad a four-event VLA prefix
into an uncertified eight-event master.

## Focused regression tests to accompany the narrow correction

1. **Restricted certified support succeeds:** a synthetic unit-test catalog
   with 8 or 9 supported families (the current template covered) has no gaps
   attributable solely to its explicitly unsupported alternatives. Synthetic
   provenance remains rejected in production.
2. **Unused alternative absence is allowed:** remove the unsupported alternative
   trigger/pose/feasibility record. The chosen schedule contains none of it.
   Separately retain a failed unsupported-family assessment and verify it does
   not suppress an otherwise eligible task or become scheduled.
3. **Declared support still requires evidence:** remove or invalidate a supported
   family's feasibility record, evidence reference, covered-state coverage,
   trigger, guard, or physical pose. It still blocks.
4. **No escape via metadata:** an extra valid trigger for an unsupported family
   cannot make the scheduler use it; unknown/duplicate support names fail.
5. **Missing required template coverage blocks:** no supported grounding,
   retirement, preference, reissue, or required paired endpoint cannot produce
   an eight-event schedule. Impossible windows still fail. No fabricated tail.
6. **Determinism and balancing:** restricted-support schedules are deterministic
   under the same seeds and under reordered session inputs; balancing is only
   among supported alternatives. The existing all-ten-support position-balance
   test retains its 16/16 grounding and retirement counts over 32 masters.
7. **Population/design gates remain:** the existing 8/9/10 all-eligible inclusion
   tests and seven-task block still pass. The same catalog still rejects missing
   calibration, altered seeds/horizon, synthetic formal evidence, and method-
   dependent selection.
8. **Manifest/preflight membership:** mixed-support task manifests never contain
   a family unsupported by their task; global family-union coverage is checked
   separately. Protocol B remains the exact K≤4 prefix of each legal master.

One existing test needs a precise split:
`test_scheduler.py::test_missing_and_unsupported_catalog_semantics_fail_closed`
currently expects failure whenever the displacement trigger is removed.
After the correction, this must fail when displacement remains **declared
supported**, while explicit support for only the alternative grounding may
succeed with a certified full template. Deleting a key without stating which
families the task supports should not accidentally turn a missing-data test
into a task-scope exclusion test.

## Implemented narrow correction and validation

Following explicit authorization, `task_catalog.py` now accepts known, unique,
nonempty task-local support sets, checks the five scientific categories, audits
metadata/evidence only for declared supported families, and evaluates supported
families when selecting tasks. The existing all-ten inventory audit and its
gap count are retained when support is empty or explicitly unresolved.
Unknown or duplicate support names fail closed and also retain full inventory
diagnostics. This prevents missing scope from erasing missing evidence.

`scheduler.py` now selects grounding and retirement alternatives only from
task support. Its existing two-pair, eight-distinct-event construction remains
unchanged. Unsupported template members fail explicitly; extra trigger entries
cannot authorize them. All-ten support preserves the previous deterministic
choice and ordering exactly.

The new `tests/repeated_v2/test_family_scope.py` covers the restricted scope,
unsupported versus supported failed assessments, missing supported metadata,
malformed declarations, unresolved-scope diagnostics, all five scientific
categories, mixed-support schedule determinism, paired-support rejection, and
exact all-ten backward compatibility. The existing scheduler missing-trigger
test now explicitly declares all ten families, so it still tests missing
metadata rather than an unsupported alternative.

Observed validation:

- New family-scope tests: **21 passed**.
- Catalog, scheduler, manifest, and new scope tests together: **75 passed**
  in 23.16 seconds. This final run includes the parent's update of the source-
  catalog inventory assertion to the independently attached real state digests
  for tasks 0, 1, 4, 5, 7, and 8. This scope correction did not modify that
  evidence or its test.
- The default catalog's unresolved-gap count remained **776**. Initially the
  tuple retained its original diagnostic bytes, SHA256
  `c308ad87c591d45a10346f0dbef7e4663eaa2c5a4cf5eb9392db32a22fd046f8`.
  The parent then requested the truthful wording correction below. It changes
  ten diagnostic strings, without closing any evidence gap. After that change,
  the count is still **776** and the diagnostic tuple SHA256 is
  `e61beffb8ae16185532b92fe7f3e3f1d8454fdac0e8b97a68b3cbbc6fdcd8e2a`.
  Replacing the ten new reasons with their old text and sorting reproduces the
  original `c308ad87…` digest exactly.
- The 32-session all-ten fixture retained its exact pre-correction schedule
  SHA256 `8d23c31e77060f052b9f1f2b03d10360651f5320dede3008f9f34176e16df4bc`.

The source implementation identity changes even when those fixture schedule
bytes do not; a later formal freeze must bind the actual corrected source.
No provider, VLA, simulator, or calibration run was performed for this change.
No calibration outcome was used to choose a task or alter a threshold.

## Exact diagnostic wording migration: ten retained gaps

Old reason: `all ten event families require explicit support/feasibility`.
New reason: `task-specific event family support is unresolved; auditing all ten candidates`.
Each row below denotes the complete diagnostic with the listed `task N: `
prefix. This is a one-to-one wording migration, not measured evidence or gap
resolution. All other diagnostics retain their meaning and text.

| Prefix | Old complete diagnostic | New complete diagnostic | Evidence closed |
| --- | --- | --- | --- |
| task 0 | task 0: all ten event families require explicit support/feasibility | task 0: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 1 | task 1: all ten event families require explicit support/feasibility | task 1: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 2 | task 2: all ten event families require explicit support/feasibility | task 2: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 3 | task 3: all ten event families require explicit support/feasibility | task 3: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 4 | task 4: all ten event families require explicit support/feasibility | task 4: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 5 | task 5: all ten event families require explicit support/feasibility | task 5: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 6 | task 6: all ten event families require explicit support/feasibility | task 6: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 7 | task 7: all ten event families require explicit support/feasibility | task 7: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 8 | task 8: all ten event families require explicit support/feasibility | task 8: task-specific event family support is unresolved; auditing all ten candidates | none |
| task 9 | task 9: all ten event families require explicit support/feasibility | task 9: task-specific event family support is unresolved; auditing all ten candidates | none |

# Evidence-based gap reconciliation

Status: RECONCILED. All 794 original rows and their classifications are retained.
Observed current diagnostics: 776. Closed by attached evidence: 18.
Open baseline rows: 776. Unexplained disappearances retained OPEN: 0.
Documented wording migrations retained OPEN: 10. Explicit new diagnostics: 0.
Baseline root packages: 127 → 124 still open.
Baseline artifact units: 357 → 354 still open.

GAP_RESOLUTION.csv keeps every original column and adds status, observed diagnostic,
literal migration reference, closure kind, exact evidence file/selector/hash receipts,
and an explanation. Missing diagnostics alone cannot close a row. NEW_GAPS.csv is
header-only when no new diagnostics exist. CURRENT_GAPS.csv records the exact API output.
GAP_COUNTS_BEFORE_AFTER.csv groups rows by category, task, root package and artifact unit.
Blank new-gap counts at package/category/artifact level mean unclassified, not zero.
Artifact membership groups may overlap; use the total row for distinct unit counts.

The 18 existing state-receipt closures concern tasks 0, 4, and 8 only. Task 1's fresh
receipts verify hashes already present and create no baseline closure. Passing and
attaching the complete audited four-task calibration can close up to 24 additional
calibration rows (six per task), without establishing task structural qualification,
event safety, semantic triggers, the success-rate eligibility condition, or formal
admission. No anticipated calibration outcome is used in this reconciliation.

The four-task raw protocol hash preserves cohort, task-record, and gate-path identity.
It cannot silently be merged with later different-hash evidence into the all-task
shared-protocol gate. Historical 220/520-horizon data and different policy seeds
remain outside this calibration contract. See FORMAL_CALIBRATION_SCOPE.md.

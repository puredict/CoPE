"""CoPE ablation arms.

`CoPE_no_rollout_verification` exists to test the VERIFIER mechanism, not to
replace the primary CoPE vs FSR-PC comparison. It is identical to CoPE in every
respect except that the rollout verifier is disabled, so the first
legality/feasibility-surviving candidate is taken without sequential forward
verification.

If the verifier never rejects anything (as in the v2 pilot, 0/162), this arm
must produce identical behaviour to `CoPE_full` -- and that identity is itself
the measurement: it shows the verifier changed no decision. When a
discriminative condition is present, the two arms must diverge.
"""
from __future__ import annotations

from .cope_patch_policy import CoPEPatchPolicy


class CoPENoRolloutVerificationPolicy(CoPEPatchPolicy):
    name = "CoPE_no_rollout_verification"

    def __init__(self, store, horizon_steps: int = 900, repair_engine=None):
        super().__init__(store, horizon_steps, repair_engine)
        # the engine reads this flag; legality and feasibility filters stay on
        if repair_engine is not None:
            repair_engine.disable_rollout_verification = True

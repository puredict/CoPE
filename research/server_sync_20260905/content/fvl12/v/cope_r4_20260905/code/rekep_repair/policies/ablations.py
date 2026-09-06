"""Ablations of the online repair policy.

Each ablation removes exactly ONE mechanism from ``OnlineRepairPolicy`` so the
causal contribution of that mechanism is isolated.  Expected causal results:

    NoRolloutVerification -> more collisions / infeasible repairs
    NoRestoreContract     -> greater handoff error, more post-repair failure
    NoEventComposition    -> lower compound-event success
    NoSynthesis           -> lower novel-composition coverage
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from ..repair.abstract_state import RepairGoal, goal_from_predicates
from ..repair.candidate_generator import CandidateGenerator
from ..repair.repair_manager import RepairManager
from ..repair.scorer import ScoreWeights, Scorer
from .online_repair import OnlineRepairPolicy


class NoSynthesisPolicy(OnlineRepairPolicy):
    """Runtime template instantiation only -- no operator search."""
    name = "abl_no_synthesis"

    def _make_generator(self, params):
        return CandidateGenerator(params)


class NoRolloutVerificationPolicy(OnlineRepairPolicy):
    """Symbolic legality + cheap screen only; no sequential rollout."""
    name = "abl_no_rollout"

    def _build_manager(self, **kw):
        kw["cfg"] = None            # RepairManager builds no verifier without cfg
        return RepairManager(**kw)


class NoStateDependentScoringPolicy(OnlineRepairPolicy):
    """Structural cost only: ignore rollout-derived safety/duration/handoff."""
    name = "abl_no_state_scoring"

    def _score_weights(self) -> ScoreWeights:
        return ScoreWeights(w_residual=0.0, w_safety=0.0, w_duration=0.0,
                            w_handoff=0.0, w_attach=0.0, alpha=1.0, w_switch=0.0)


class NoEventCompositionPolicy(OnlineRepairPolicy):
    """Use ONLY the highest-priority active predicate, discarding the rest --
    i.e. no union of compound requirements."""
    name = "abl_no_composition"

    def _repair_goal(self, preds) -> RepairGoal:
        from ..repair.abstract_state import WorldPredicates
        # priority: slip > obstacle > relocation (matches the detector)
        if preds.object_slipped:
            only = WorldPredicates(object_slipped=True)
        elif preds.obstacle_present:
            only = WorldPredicates(obstacle_present=True,
                                   unsafe_clearance=preds.unsafe_clearance)
        else:
            only = WorldPredicates(target_relocated=preds.target_relocated)
        return goal_from_predicates(only)


class NoRestoreGatePolicy(OnlineRepairPolicy):
    """(A) Keep Realign; allow entry to the resumed stage WITHOUT validating the
    continuation contract.  Isolates the *gate* only."""
    name = "abl_no_restore_gate"

    def _validate_restore(self, ctx) -> bool:
        self.program._restore_validated = True
        return True


class NoRealignPolicy(OnlineRepairPolicy):
    """(B) Remove the explicit realignment stage: restore directly from the
    post-repair state.  Isolates the realign MOTION."""
    name = "abl_no_realign"

    def _make_generator(self, params):
        from ..repair.synthesis_generator import SynthesisGenerator

        class _NoRealign(SynthesisGenerator):
            def generate(self, event, continuation, abstract_init=None, goal=None):
                cands = super().generate(event, continuation, abstract_init, goal)
                for c in cands:
                    c.stages = [st for st in c.stages
                                if st.metadata.get("operator") != "Realign"]
                    c.template_name = "+".join(
                        st.metadata.get("operator", "?") for st in c.stages)
                return [c for c in cands if c.stages]

        return _NoRealign(params)


class NoContinuationContractPolicy(OnlineRepairPolicy):
    """(C) Keep a generic realignment behaviour but drop the continuation-
    specific handoff pose / contract: realign to the nominal goal direction
    instead of the saved pose."""
    name = "abl_no_cont_contract"

    def _handoff_for(self, ctx):
        return None


class NoProvenancePolicy(OnlineRepairPolicy):
    """Execute without recording causal repair lineage."""
    name = "abl_no_provenance"

    def _record_provenance(self) -> bool:
        return False


ABLATIONS = {
    "abl_no_synthesis": NoSynthesisPolicy,
    "abl_no_rollout": NoRolloutVerificationPolicy,
    "abl_no_state_scoring": NoStateDependentScoringPolicy,
    "abl_no_composition": NoEventCompositionPolicy,
    "abl_no_restore_gate": NoRestoreGatePolicy,
    "abl_no_realign": NoRealignPolicy,
    "abl_no_cont_contract": NoContinuationContractPolicy,
    "abl_no_provenance": NoProvenancePolicy,
}

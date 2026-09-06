"""The two primary adaptation policies plus the no-adaptation control."""
from .adaptation_input import AdaptationInput
from .cope_patch_policy import CoPEPatchPolicy
from .fsrpc_policy import FSRPCPolicy
from .cope_ablations import CoPENoRolloutVerificationPolicy
from .fsrpc_variants import FSRPCProvenancePolicy, FSRPCStableIdsPolicy
from .no_adaptation_policy import NoAdaptationPolicy

# Method registry. Every arm is constructed identically -- same signature, same
# store, same horizon -- so the harness cannot privilege one of them.
METHODS = {
    "CoPE": CoPEPatchPolicy,
    "FSR-PC": FSRPCPolicy,
    "no_adaptation": NoAdaptationPolicy,
    # --- diagnostic variants (Stage D). Not part of the primary comparison.
    "FSR-PC_stable_ids": FSRPCStableIdsPolicy,
    "FSR-PC_provenance": FSRPCProvenancePolicy,
    "CoPE_full": CoPEPatchPolicy,
    "CoPE_no_rollout_verification": CoPENoRolloutVerificationPolicy,
}
PRIMARY_METHODS = ("CoPE", "FSR-PC")
#: Stage D decomposition of the audit advantage
FSRPC_VARIANTS = ("FSR-PC", "FSR-PC_stable_ids", "FSR-PC_provenance")
#: Stage D verifier-mechanism ablation
VERIFIER_ARMS = ("CoPE_full", "CoPE_no_rollout_verification")

__all__ = ["AdaptationInput", "CoPEPatchPolicy", "FSRPCPolicy",
           "NoAdaptationPolicy", "FSRPCStableIdsPolicy",
           "FSRPCProvenancePolicy", "CoPENoRolloutVerificationPolicy",
           "METHODS", "PRIMARY_METHODS", "FSRPC_VARIANTS", "VERIFIER_ARMS"]

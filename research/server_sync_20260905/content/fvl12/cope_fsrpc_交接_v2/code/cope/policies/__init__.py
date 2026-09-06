"""The two primary adaptation policies plus the no-adaptation control."""
from .adaptation_input import AdaptationInput
from .cope_patch_policy import CoPEPatchPolicy
from .fsrpc_policy import FSRPCPolicy
from .no_adaptation_policy import NoAdaptationPolicy

# Method registry. Every arm is constructed identically -- same signature, same
# store, same horizon -- so the harness cannot privilege one of them.
METHODS = {
    "CoPE": CoPEPatchPolicy,
    "FSR-PC": FSRPCPolicy,
    "no_adaptation": NoAdaptationPolicy,
}
PRIMARY_METHODS = ("CoPE", "FSR-PC")

__all__ = ["AdaptationInput", "CoPEPatchPolicy", "FSRPCPolicy",
           "NoAdaptationPolicy", "METHODS", "PRIMARY_METHODS"]

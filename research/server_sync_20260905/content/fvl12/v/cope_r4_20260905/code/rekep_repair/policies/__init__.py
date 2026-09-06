"""Recovery policies (methods), all run through the same Executor/harness."""

from .fixed_program import FixedProgramPolicy
from .path_only import PathOnlyPolicy
from .safe_stop import SafeStopPolicy
from .offline_recovery import (
    OfflinePrecompiledPolicy,
    OfflineSingleEventCoveragePolicy,
    OfflineComprehensivePolicy,
    OfflineEnumeratedPolicy,
    OfflineBudgetedPolicy,
    all_combinations,
)
from .offline_parameterized import (
    OfflineParameterizedPolicy,
    OfflineExactPolicy,
    OfflineAtomicOnlyPolicy,
    OfflineBudgetPolicy,
    PrecompiledLibrary,
)
from .template_repair import TemplateRepairPolicy
from .online_repair import OnlineRepairPolicy

ALL_POLICIES = {
    "fixed_program": FixedProgramPolicy,
    "path_only": PathOnlyPolicy,
    "safe_stop": SafeStopPolicy,
    "offline_single": OfflineSingleEventCoveragePolicy,
    "offline_comprehensive": OfflineComprehensivePolicy,
    "template_repair": TemplateRepairPolicy,
    "online_repair": OnlineRepairPolicy,
}

__all__ = [
    "FixedProgramPolicy", "PathOnlyPolicy", "SafeStopPolicy",
    "OfflinePrecompiledPolicy", "OfflineSingleEventCoveragePolicy",
    "OfflineComprehensivePolicy", "OfflineEnumeratedPolicy", "OfflineBudgetedPolicy",
    "all_combinations", "OfflineParameterizedPolicy", "OfflineExactPolicy",
    "OfflineAtomicOnlyPolicy", "OfflineBudgetPolicy", "PrecompiledLibrary",
    "TemplateRepairPolicy", "OnlineRepairPolicy", "ALL_POLICIES",
]

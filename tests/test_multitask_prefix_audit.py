from dataclasses import asdict

from cope.types import stable_hash
from experiments import multitask_prefix_audit as audit


def test_multitask_prefix_scope_and_controller_are_frozen() -> None:
    assert audit.STATE_IDS == tuple(range(10))
    assert [spec["task_id"] for spec in audit.TASK_SPECS] == [0, 7]
    assert all(max(audit.STATE_IDS) < 10 for _ in audit.TASK_SPECS)
    assert stable_hash(asdict(audit.CONTROLLER_CONFIG)) == audit.EXPECTED_CONFIG_HASH

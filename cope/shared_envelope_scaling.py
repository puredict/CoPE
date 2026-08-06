from __future__ import annotations

import copy
from typing import Any

from cope.shared_commit_envelope import SharedEnvelopeCase, _event, _meta, _record, apply_typed_operations
from cope.shared_envelope_holdout import _base_state, _rule, _specs


STATE_SIZES = (4, 16, 32)


def _scaled_state(commitment_count: int) -> dict[str, Any]:
    if commitment_count not in STATE_SIZES:
        raise ValueError(f"unsupported commitment count: {commitment_count}")
    state = _base_state()
    for index in range(4, commitment_count):
        commitment_id = f"z{index:03d}"
        state["commitments"].append(_record(
            commitment_id,
            status="pending" if index % 3 else "active",
            owner=f"distractor_owner_{index % 5}",
            priority=(index % 7) + 1,
            requires_all=[] if index < 5 else [f"z{index - 1:03d}"],
            requires_any=[],
        ))
        state["actions"].append(_record(
            f"za{index:03d}",
            commitment_id=commitment_id,
            status="pending" if index % 3 else "running",
            progress=round((index % 10) / 10, 1),
            reversible=index % 4 != 0,
        ))
        state["progress"].append(_record(
            f"zp{index:03d}",
            commitment_id=commitment_id,
            value=round((index % 10) / 10, 1),
            valid=index % 6 != 0,
        ))
        if index % 8 == 0:
            state["restorations"].append(_record(
                f"zr{index:03d}", target_id=commitment_id, after_id="c0", status="pending"
            ))
        state["facts"][f"distractor_fact_{index:03d}"] = index % 2 == 0
    return state


def build_scaling_cases() -> list[SharedEnvelopeCase]:
    cases: list[SharedEnvelopeCase] = []
    specs = _specs()
    for size in STATE_SIZES:
        for index, (family, event_type, source_operations) in enumerate(specs, start=1):
            pre = _scaled_state(size)
            operations = copy.deepcopy(list(source_operations))
            post = apply_typed_operations(pre, operations)
            case_id = f"SCE-S{size:02d}-{index:02d}"
            rules = tuple(_rule(rule_index, operation) for rule_index, operation in enumerate(operations, start=1))
            version = size * 1000 + index
            cases.append(SharedEnvelopeCase(
                case_id=case_id,
                family=f"scale_{size:02d}_{family}",
                original_task=(
                    f"execute a sparse authorized {family.replace('_', ' ')} transition while preserving "
                    f"the other commitments in a persistent state of size {size}"
                ),
                pre_state=pre,
                event=_event(
                    f"S{size:02d}-{index:02d}", event_type, version, version + 500,
                    transition_family=family, persistent_commitment_count=size,
                ),
                transaction_meta=_meta(version, version + 400),
                rule_clauses=rules,
                oracle_operations=tuple(operations),
                post_state=post,
            ))
    expected = len(STATE_SIZES) * len(specs)
    if len(cases) != expected or len({case.case_id for case in cases}) != expected:
        raise AssertionError("scaling corpus size or IDs are invalid")
    if any(len(case.pre_state["commitments"]) not in STATE_SIZES for case in cases):
        raise AssertionError("scaling corpus contains an invalid state size")
    return cases

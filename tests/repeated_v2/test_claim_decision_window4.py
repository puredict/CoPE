from dataclasses import replace
import json

import pytest

from cope_benchmark.repeated_v2.claim_decision import (
    ComparisonEvidence, DecisionInput, GATE_NAMES, evaluate_claims,
    evaluate_runtime_gates,
)


def evidence(**changes):
    initial = ComparisonEvidence(
        protocol="end_to_end", checkpoint=4,
        risk_difference=0.2, paired_ci_lower=0.05, paired_ci_upper=0.35,
        degradation_slope_difference=0.1, degradation_ci_lower=0.02,
        cope_corruption_rate=0.1, comparator_corruption_rate=0.3,
        cope_regression_rate=0.05, comparator_regression_rate=0.2,
        cope_pre_execution_fidelity=0.9, comparator_pre_execution_fidelity=0.7,
        fidelity_precedes_execution=True, generic_ni_lower=-0.04,
        evidence_parity=True, reasoner_call_parity=True,
        generic_risk_difference=0.0, generic_ci_lower=-0.04, generic_ci_upper=0.04,
    )
    return replace(initial, **changes)


def decision_input(**changes):
    return replace(DecisionInput(
        integrity_valid=True, formal_complete=True, learned_vla=evidence(),
        primary_comparator="full_history_replan",
    ), **changes)


def controlled(**changes):
    return evidence(protocol="controlled", checkpoint=8, **changes)


def test_go_requires_all_seven_gates_and_exports_strict_json():
    result = evaluate_claims(decision_input())
    assert result.status == "GO"
    assert tuple(gate.name for gate in result.gates) == GATE_NAMES
    assert {gate.status for gate in result.gates} == {"PASS"}
    assert not result.blockers
    assert json.loads(json.dumps(result.as_dict(), allow_nan=False))["status"] == "GO"
    assert "Decision: **GO**" in result.to_markdown()
    assert "## Forbidden claims" in result.to_markdown()


@pytest.mark.parametrize("changes,gate,expected", [
    ({"risk_difference": 0.099}, 0, "PARTIAL_SUPPORT"),
    ({"paired_ci_lower": 0.0}, 1, "NO_GO"),
    ({"degradation_ci_lower": 0.0}, 2, "PARTIAL_SUPPORT"),
    ({"degradation_slope_difference": 0.0}, 2, "PARTIAL_SUPPORT"),
    ({"cope_corruption_rate": 0.151}, 3, "PARTIAL_SUPPORT"),
    ({"cope_regression_rate": 0.101}, 3, "PARTIAL_SUPPORT"),
    ({"cope_pre_execution_fidelity": 0.7}, 4, "NO_GO"),
    ({"fidelity_precedes_execution": False}, 4, "NO_GO"),
    ({"generic_ni_lower": -0.05}, 5, "PARTIAL_SUPPORT"),
])
def test_each_binding_runtime_gate_fails_at_registered_boundary(changes, gate, expected):
    result = evaluate_claims(decision_input(learned_vla=evidence(**changes)))
    assert result.status == expected
    assert result.gates[gate].status == "FAIL"
    assert any("full preregistered learned-VLA" in claim for claim in result.forbidden_claims)


def test_effect_margin_and_half_rate_equalities_pass():
    result = evaluate_claims(decision_input(learned_vla=evidence(
        risk_difference=0.10, cope_corruption_rate=0.15, cope_regression_rate=0.10,
    )))
    assert result.status == "GO"


@pytest.mark.parametrize("flag", ["evidence_parity", "reasoner_call_parity"])
def test_information_or_call_parity_breach_invalidates_comparison(flag):
    result = evaluate_claims(decision_input(learned_vla=evidence(**{flag: False})))
    assert result.status == "INVALID_RUN"
    assert all(g.status == "UNKNOWN" for g in result.gates)
    assert any("parity violated" in reason for reason in result.reasons)


REQUIRED_MEASUREMENTS = [
    "risk_difference", "paired_ci_lower", "paired_ci_upper",
    "degradation_slope_difference", "degradation_ci_lower",
    "cope_corruption_rate", "comparator_corruption_rate",
    "cope_regression_rate", "comparator_regression_rate",
    "cope_pre_execution_fidelity", "comparator_pre_execution_fidelity",
    "fidelity_precedes_execution", "generic_ni_lower", "evidence_parity", "reasoner_call_parity",
]


@pytest.mark.parametrize("field", REQUIRED_MEASUREMENTS)
def test_every_missing_required_measurement_blocks_without_imputation(field):
    result = evaluate_claims(decision_input(learned_vla=evidence(**{field: None})))
    assert result.status == "BLOCKED_ANALYSIS_EVIDENCE_INCOMPLETE"
    assert "UNKNOWN" in {gate.status for gate in result.gates}
    assert not result.controlled_mechanism_supported
    assert not any("positive paired execution difference" in claim for claim in result.paper_safe_claims)


@pytest.mark.parametrize("field", [name for name in REQUIRED_MEASUREMENTS if name not in {
    "fidelity_precedes_execution", "evidence_parity", "reasoner_call_parity",
}])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "0.9"])
def test_nonfinite_or_wrong_type_measurement_is_invalid(field, value):
    result = evaluate_claims(decision_input(learned_vla=evidence(**{field: value})))
    assert result.status == "INVALID_RUN"
    assert not result.controlled_mechanism_supported
    json.dumps(result.as_dict(), allow_nan=False)


@pytest.mark.parametrize("changes", [
    {"cope_corruption_rate": -0.01}, {"cope_regression_rate": 1.01},
    {"cope_pre_execution_fidelity": 1.01}, {"risk_difference": 1.01},
    {"generic_ni_lower": -1.01}, {"paired_ci_lower": 0.5, "paired_ci_upper": 0.4},
    {"generic_ci_lower": 0.5, "generic_ci_upper": 0.4},
    {"checkpoint": 8}, {"checkpoint": True}, {"protocol": "controlled"},
    {"fidelity_precedes_execution": 1}, {"evidence_parity": "true"},
    {"reasoner_call_parity": 1}, {"risk_difference": 10 ** 1000},
])
def test_malformed_evidence_is_invalid(changes):
    assert evaluate_claims(decision_input(learned_vla=evidence(**changes))).status == "INVALID_RUN"


def test_zero_incidence_both_sides_passes_literal_threshold_without_division():
    result = evaluate_claims(decision_input(learned_vla=evidence(
        cope_corruption_rate=0, comparator_corruption_rate=0,
        cope_regression_rate=0, comparator_regression_rate=0,
    )))
    assert result.status == "GO"
    assert result.gates[3].status == "PASS"
    assert "twofold reduction" not in " ".join(result.paper_safe_claims)


@pytest.mark.parametrize("metric", ["corruption", "regression"])
def test_nonzero_cope_against_zero_comparator_fails(metric):
    result = evaluate_claims(decision_input(learned_vla=evidence(**{
        f"cope_{metric}_rate": 0.001, f"comparator_{metric}_rate": 0,
    })))
    assert result.gates[3].status == "FAIL"
    assert result.status != "GO"


def test_empty_input_is_blocked_and_all_gates_unknown():
    result = evaluate_claims(DecisionInput())
    assert result.status.startswith("BLOCKED_")
    assert all(g.status == "UNKNOWN" for g in result.gates)
    assert not result.controlled_mechanism_supported


@pytest.mark.parametrize("changes", [
    {"formal_complete": False}, {"learned_vla": None},
    {"integrity_valid": None}, {"primary_comparator": None},
    {"blockers": ("BLOCKED_VLA_ADAPTER_UNAVAILABLE",)},
])
def test_readiness_or_complete_result_prerequisites_are_binding(changes):
    result = evaluate_claims(decision_input(**changes))
    assert result.status.startswith("BLOCKED_")
    assert not any("positive paired execution difference" in claim for claim in result.paper_safe_claims)
    assert "No admissible" in result.generic_interpretation


@pytest.mark.parametrize("changes", [
    {"integrity_valid": False}, {"invalid_reasons": ("duplicate result cell",)},
    {"controlled_integrity_valid": False},
    {"formal_complete": "true"}, {"integrity_valid": 1},
    {"controlled_complete": 1}, {"controlled_integrity_valid": "true"},
    {"primary_comparator": "generic_persistent_edit"},
    {"primary_comparator": "oracle_persistent_update"},
    {"primary_comparator": "not_preregistered"}, {"blockers": (None,)},
    {"invalid_reasons": (None,)},
])
def test_invalid_precedes_all_favorable_and_blocked_data(changes):
    initial = decision_input(
        controlled=controlled(), controlled_complete=True, controlled_integrity_valid=True,
        blockers=("BLOCKED_VLA_ADAPTER_UNAVAILABLE",),
    )
    result = evaluate_claims(replace(initial, **changes))
    assert result.status == "INVALID_RUN"
    assert not result.controlled_mechanism_supported
    assert len(result.paper_safe_claims) == 1
    assert "no confirmatory" in result.paper_safe_claims[0]


def test_complete_valid_controlled_can_supply_only_mechanism_partial_when_vla_blocked():
    result = evaluate_claims(decision_input(
        formal_complete=False, learned_vla=None, controlled=controlled(),
        controlled_complete=True, controlled_integrity_valid=True,
        blockers=("BLOCKED_VLA_ADAPTER_UNAVAILABLE",),
    ))
    assert result.status == "PARTIAL_SUPPORT"
    assert result.controlled_mechanism_supported
    assert "BLOCKED_VLA_ADAPTER_UNAVAILABLE" in result.blockers
    assert any("mechanism evidence only" in claim for claim in result.paper_safe_claims)
    assert any("learned-VLA execution improvement" in claim for claim in result.forbidden_claims)
    assert all(g.status == "UNKNOWN" for g in result.gates)


@pytest.mark.parametrize("changes", [
    {"controlled_complete": False}, {"controlled_integrity_valid": None},
    {"controlled": None},
])
def test_incomplete_or_unaudited_controlled_never_gives_partial_support(changes):
    initial = decision_input(formal_complete=False, learned_vla=None,
                             controlled=controlled(), controlled_complete=True,
                             controlled_integrity_valid=True)
    result = evaluate_claims(replace(initial, **changes))
    assert result.status.startswith("BLOCKED_")
    assert not result.controlled_mechanism_supported


@pytest.mark.parametrize("changes", [
    {"risk_difference": 0}, {"paired_ci_lower": 0}, {"degradation_ci_lower": 0},
    {"cope_corruption_rate": 0.4}, {"cope_regression_rate": 0.4},
    {"cope_pre_execution_fidelity": 0.1}, {"fidelity_precedes_execution": None},
    {"evidence_parity": None}, {"reasoner_call_parity": None},
])
def test_controlled_partial_exception_has_binding_mechanism_gates(changes):
    result = evaluate_claims(decision_input(formal_complete=False, learned_vla=None,
        controlled=controlled(**changes), controlled_complete=True, controlled_integrity_valid=True))
    assert result.status.startswith("BLOCKED_")
    assert not result.controlled_mechanism_supported


def test_controlled_generic_ni_and_ten_point_margin_are_not_runtime_substitutes():
    result = evaluate_claims(decision_input(formal_complete=False, learned_vla=None,
        controlled=controlled(risk_difference=0.08, generic_ni_lower=None),
        controlled_complete=True, controlled_integrity_valid=True))
    assert result.status == "PARTIAL_SUPPORT"
    assert result.controlled_mechanism_supported


def test_complete_negative_vla_can_still_have_controlled_only_partial():
    result = evaluate_claims(decision_input(
        learned_vla=evidence(risk_difference=-0.1, paired_ci_lower=-0.2,
                             paired_ci_upper=0.0, cope_pre_execution_fidelity=0.6),
        controlled=controlled(), controlled_complete=True, controlled_integrity_valid=True,
    ))
    assert result.status == "PARTIAL_SUPPORT"
    assert result.controlled_mechanism_supported
    assert not any("positive paired execution difference" in c for c in result.paper_safe_claims)


def test_token_savings_without_execution_evidence_do_not_support_runtime():
    # Costs are deliberately not a decision input: arbitrarily favorable costs
    # cannot override a failed runtime comparison.
    result = evaluate_claims(decision_input(learned_vla=evidence(
        risk_difference=0.0, paired_ci_lower=-0.1, paired_ci_upper=0.1,
    )))
    assert result.status == "NO_GO"


def test_negative_point_effect_is_not_positive_partial_support():
    result = evaluate_claims(decision_input(learned_vla=evidence(risk_difference=-0.01)))
    assert result.status == "NO_GO"


def test_generic_interval_including_zero_requires_persistent_structure_nuance():
    result = evaluate_claims(decision_input())
    assert "persistent responsibility structure" in result.generic_interpretation
    assert "does not prove equivalence" in result.generic_interpretation
    assert "Typed semantic superiority is not established" in result.generic_interpretation
    assert any("Non-inferiority proves equivalence" in c for c in result.forbidden_claims)


def test_generic_noninferiority_failure_is_not_called_inferiority():
    result = evaluate_claims(decision_input(learned_vla=evidence(generic_ni_lower=-0.05)))
    assert "does not establish inferiority" in result.generic_interpretation


def test_optional_generic_two_sided_interval_not_needed_for_ni():
    result = evaluate_claims(decision_input(learned_vla=evidence(
        generic_risk_difference=None, generic_ci_lower=None, generic_ci_upper=None,
    )))
    assert result.status == "GO"
    assert "Non-inferiority alone" in result.generic_interpretation


def test_invalid_runtime_gate_direct_input_raises_instead_of_silent_favorable_defaults():
    with pytest.raises(ValueError):
        evaluate_runtime_gates(evidence(paired_ci_lower=float("nan")))
    with pytest.raises(ValueError):
        evaluate_runtime_gates(evidence(protocol="unknown", checkpoint=8))


def test_decision_does_not_mutate_or_delete_supplied_evidence():
    initial = decision_input()
    before = repr(initial)
    first = evaluate_claims(initial)
    second = evaluate_claims(initial)
    assert repr(initial) == before
    assert first == second

"""Binding, fail-closed claim decisions for repeated-interruption v2.

This module consumes audited *complete-protocol* estimates; it never repairs,
imputes, drops, or reads result cells. A caller must separately verify the
manifest, pairing, freeze, substrate, and exact cell inventory.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from numbers import Real
from typing import Any


NONPERSISTENT_COMPARATORS = (
    "full_state_regeneration", "full_history_replan", "rag_replan",
    "summary_memory_replan", "skill_local_replan", "classical_execution_monitor",
)
GATE_NAMES = (
    "runtime_effect_margin", "paired_ci_positive", "flatter_degradation",
    "corruption_and_regression_halved", "prior_planning_fidelity",
    "generic_noninferiority", "evidence_and_call_parity",
)
BASE_FORBIDDEN_CLAIMS = (
    "Typed syntax is inherently more intelligent than every generic persistent representation.",
    "CoPE alone solves perception, VLA control, safety, or open-world specification induction.",
    "Controlled or oracle execution is evidence of learned-VLA improvement.",
    "A custom continuation-carrying repair backend is original published ReKep.",
    "Semantic state correctness automatically establishes physical task success.",
    "A rejected or invalid patch is a successful recovery.",
    "Missing dependencies, unrun cells, or synthetic fixtures are successful formal results.",
    "Frozen v1 and v2 outcomes may be silently pooled or unfavorable cells deleted.",
    "Non-inferiority proves equivalence or typed semantic superiority.",
    "The results establish generalization beyond the tested tasks, events, and backends.",
)


@dataclass(frozen=True)
class ComparisonEvidence:
    """Estimates for CoPE minus the frozen nonpersistent comparator.

    Risk-difference and degradation intervals are two-sided 95% intervals.
    ``generic_ni_lower`` is a *one-sided* 95% paired lower confidence bound.
    Rates for fidelity/corruption/regression must use the preregistered,
    complete master-session denominators, including failed trajectories.
    ``fidelity_precedes_execution`` requires recorded temporal provenance,
    not a temporal order inferred from association or a final-state score.
    All unprovided measurements remain unknown.
    """

    protocol: str
    checkpoint: int
    risk_difference: float | None = None
    paired_ci_lower: float | None = None
    paired_ci_upper: float | None = None
    degradation_slope_difference: float | None = None
    degradation_ci_lower: float | None = None
    cope_corruption_rate: float | None = None
    comparator_corruption_rate: float | None = None
    cope_regression_rate: float | None = None
    comparator_regression_rate: float | None = None
    cope_pre_execution_fidelity: float | None = None
    comparator_pre_execution_fidelity: float | None = None
    fidelity_precedes_execution: bool | None = None
    generic_ni_lower: float | None = None
    evidence_parity: bool | None = None
    reasoner_call_parity: bool | None = None
    generic_risk_difference: float | None = None
    generic_ci_lower: float | None = None
    generic_ci_upper: float | None = None


@dataclass(frozen=True)
class DecisionInput:
    """Evidence and audited readiness; defaults cannot yield a GO.

    ``formal_complete`` refers to the learned-VLA protocol. A controlled arm
    is admissible only when both its own completeness and integrity fields
    are explicitly true. ``integrity_valid=False`` invalidates the run even
    when blockers or favorable controlled data are also present.
    """

    integrity_valid: bool | None = None
    formal_complete: bool = False
    blockers: tuple[str, ...] = ()
    invalid_reasons: tuple[str, ...] = ()
    learned_vla: ComparisonEvidence | None = None
    controlled: ComparisonEvidence | None = None
    controlled_complete: bool = False
    controlled_integrity_valid: bool | None = None
    primary_comparator: str | None = None


@dataclass(frozen=True)
class GateResult:
    name: str
    status: str
    explanation: str
    values: dict[str, Any]


@dataclass(frozen=True)
class ClaimDecision:
    status: str
    gates: tuple[GateResult, ...]
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    controlled_mechanism_supported: bool
    paper_safe_claims: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    generic_interpretation: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = ["# Claim decision", "", f"Decision: **{self.status}**", "",
                 "## Binding runtime gates", "", "| Gate | Result | Rule |",
                 "|---|---|---|"]
        lines.extend(f"| {gate.name} | {gate.status} | {gate.explanation} |"
                     for gate in self.gates)
        for title, entries in (
            ("Decision reasons", self.reasons), ("Unresolved blockers", self.blockers),
            ("Paper-safe claims", self.paper_safe_claims),
            ("Forbidden claims", self.forbidden_claims),
        ):
            lines.extend(["", f"## {title}", ""])
            lines.extend(f"- {item}" for item in entries)
            if not entries:
                lines.append("None.")
        lines.extend(["", "## Generic persistent control", "", self.generic_interpretation, ""])
        return "\n".join(lines)


def _finite_number(value: Any) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _evidence_errors(evidence: ComparisonEvidence, protocol: str) -> list[str]:
    errors: list[str] = []
    if protocol not in {"end_to_end", "controlled"}:
        errors.append(f"Unknown protocol {protocol!r}")
    if evidence.protocol != protocol:
        errors.append(f"{protocol}: evidence protocol is {evidence.protocol!r}")
    checkpoint = 4 if protocol == "end_to_end" else 8
    if type(evidence.checkpoint) is not int or evidence.checkpoint != checkpoint:
        errors.append(f"{protocol}: terminal checkpoint must be {checkpoint}")
    flags = {"fidelity_precedes_execution", "evidence_parity", "reasoner_call_parity"}
    ignored = {"protocol", "checkpoint"}
    for name, value in asdict(evidence).items():
        if value is None or name in ignored:
            continue
        if name in flags:
            if type(value) is not bool:
                errors.append(f"{protocol}: {name} must be a boolean or null")
        elif not _finite_number(value):
            errors.append(f"{protocol}: {name} is not finite numeric evidence")
        elif (name.endswith("_rate") or name.endswith("_fidelity")) and not 0 <= value <= 1:
            errors.append(f"{protocol}: {name} is outside [0, 1]")
        elif name not in {"degradation_slope_difference", "degradation_ci_lower"} and not -1 <= value <= 1:
            errors.append(f"{protocol}: {name} is outside [-1, 1]")
    for lower_name, upper_name in (("paired_ci_lower", "paired_ci_upper"),
                                   ("generic_ci_lower", "generic_ci_upper")):
        lower, upper = getattr(evidence, lower_name), getattr(evidence, upper_name)
        if _finite_number(lower) and _finite_number(upper) and lower > upper:
            errors.append(f"{protocol}: {lower_name} exceeds {upper_name}")
    if evidence.evidence_parity is False:
        errors.append(f"{protocol}: public-evidence/hidden-information parity violated")
    if evidence.reasoner_call_parity is False:
        errors.append(f"{protocol}: event-level reasoner-call parity violated")
    return errors


def _gate(name: str, explanation: str, values: dict[str, Any], predicate: Any) -> GateResult:
    if any(value is None for value in values.values()):
        return GateResult(name, "UNKNOWN", explanation, values)
    return GateResult(name, "PASS" if predicate() else "FAIL", explanation, values)


def evaluate_runtime_gates(evidence: ComparisonEvidence | None) -> tuple[GateResult, ...]:
    """Evaluate all seven gates; malformed supplied values must be rejected first."""
    e = evidence or ComparisonEvidence("end_to_end", 4)
    errors = _evidence_errors(e, e.protocol)
    if errors:
        raise ValueError("; ".join(errors))
    return (
        _gate(GATE_NAMES[0], "CoPE minus frozen comparator risk difference >= 0.10.",
              {"risk_difference": e.risk_difference}, lambda: e.risk_difference >= 0.10),
        _gate(GATE_NAMES[1], "Two-sided 95% paired lower bound > 0.",
              {"paired_ci_lower": e.paired_ci_lower, "paired_ci_upper": e.paired_ci_upper},
              lambda: e.paired_ci_lower > 0),
        _gate(GATE_NAMES[2], "CoPE minus comparator slope difference and its 95% lower bound > 0.",
              {"slope_difference": e.degradation_slope_difference, "lower_95": e.degradation_ci_lower},
              lambda: e.degradation_slope_difference > 0 and e.degradation_ci_lower > 0),
        _gate(GATE_NAMES[3], "CoPE corruption and regression are each <= half the comparator rate; comparator zero requires CoPE zero.",
              {"cope_corruption_rate": e.cope_corruption_rate,
               "comparator_corruption_rate": e.comparator_corruption_rate,
               "cope_regression_rate": e.cope_regression_rate,
               "comparator_regression_rate": e.comparator_regression_rate},
              lambda: e.cope_corruption_rate <= 0.5 * e.comparator_corruption_rate
              and e.cope_regression_rate <= 0.5 * e.comparator_regression_rate),
        _gate(GATE_NAMES[4], "Pre-execution planning fidelity is higher, with verified temporal precedence.",
              {"cope_fidelity": e.cope_pre_execution_fidelity,
               "comparator_fidelity": e.comparator_pre_execution_fidelity,
               "temporal_precedence": e.fidelity_precedes_execution},
              lambda: e.cope_pre_execution_fidelity > e.comparator_pre_execution_fidelity
              and e.fidelity_precedes_execution is True),
        _gate(GATE_NAMES[5], "One-sided 95% paired CoPE-minus-generic lower bound > -0.05.",
              {"generic_ni_lower": e.generic_ni_lower}, lambda: e.generic_ni_lower > -0.05),
        _gate(GATE_NAMES[6], "Evidence/hidden-information and event-level reasoner-call parity are verified.",
              {"evidence_parity": e.evidence_parity, "reasoner_call_parity": e.reasoner_call_parity},
              lambda: e.evidence_parity is True and e.reasoner_call_parity is True),
    )


def _generic_interpretation(evidence: ComparisonEvidence | None, admissible: bool) -> str:
    if not admissible or evidence is None or evidence.generic_ni_lower is None:
        return "No admissible completed learned-VLA non-inferiority conclusion is available."
    if evidence.generic_ni_lower <= -0.05:
        return "Non-inferiority to generic persistent edit was not established; this does not establish inferiority."
    if evidence.generic_ci_lower is not None and evidence.generic_ci_upper is not None:
        if evidence.generic_ci_lower <= 0 <= evidence.generic_ci_upper:
            return ("CoPE is non-inferior within the prespecified 5 percentage-point margin; "
                    "the two-sided execution interval includes zero. This does not prove equivalence. "
                    "Any shared benefit supports persistent responsibility structure; the typed carrier "
                    "offers compact representation, direct validation, and atomic transactions. "
                    "Typed semantic superiority is not established.")
    return ("CoPE is non-inferior within the prespecified 5 percentage-point margin. "
            "Non-inferiority alone establishes neither equivalence nor typed semantic superiority; "
            "compactness, invalid-transaction rate, and latency require their own measured evidence.")


def evaluate_claims(inputs: DecisionInput) -> ClaimDecision:
    """Apply invalid > complete controlled-only partial > blocked > runtime gates.

    The controlled exception never gives runtime support and never uses an
    incomplete protocol. Complete valid VLA evidence yields GO only when all
    seven gates pass. Otherwise positive paired execution evidence with prior
    fidelity support yields PARTIAL_SUPPORT; absent such evidence it is NO_GO.
    """
    invalid = list(inputs.invalid_reasons)
    blockers = list(inputs.blockers)
    if any(not isinstance(item, str) or not item for item in invalid + blockers):
        invalid = [item for item in invalid if isinstance(item, str)]
        invalid.append("Invalid reasons and blockers must contain nonempty strings.")
        blockers = [item for item in blockers if isinstance(item, str) and item]
    for name in ("integrity_valid", "controlled_integrity_valid"):
        value = getattr(inputs, name)
        if value is not None and type(value) is not bool:
            invalid.append(f"{name} must be a boolean or null")
    for name in ("formal_complete", "controlled_complete"):
        if type(getattr(inputs, name)) is not bool:
            invalid.append(f"{name} must be a boolean")
    if inputs.integrity_valid is False:
        invalid.append("Run integrity failed; no inferential claims are admissible.")
    if inputs.controlled_integrity_valid is False:
        invalid.append("Controlled protocol integrity failed.")
    if inputs.primary_comparator is not None and inputs.primary_comparator not in NONPERSISTENT_COMPARATORS:
        invalid.append("The frozen primary comparator must be a prespecified nonpersistent method.")
    for e, protocol in ((inputs.learned_vla, "end_to_end"), (inputs.controlled, "controlled")):
        if e is not None:
            invalid.extend(_evidence_errors(e, protocol))

    if invalid:
        gates = tuple(GateResult(name, "UNKNOWN", "Not evaluated: run integrity or evidence is invalid.", {})
                      for name in GATE_NAMES)
        return ClaimDecision("INVALID_RUN", gates, tuple(dict.fromkeys(invalid)),
                             tuple(dict.fromkeys(blockers)), False,
                             ("Integrity or protocol validation failed; no confirmatory outcome conclusion is admissible.",),
                             BASE_FORBIDDEN_CLAIMS + ("This run supports the registered runtime or mechanism claim.",),
                             _generic_interpretation(None, False))

    gates = evaluate_runtime_gates(inputs.learned_vla)
    controlled_gates = evaluate_runtime_gates(inputs.controlled)
    controlled_support = (
        inputs.controlled is not None and inputs.controlled_complete is True
        and inputs.controlled_integrity_valid is True and inputs.primary_comparator is not None
        and inputs.controlled.risk_difference is not None and inputs.controlled.risk_difference > 0
        and all(controlled_gates[index].status == "PASS" for index in (1, 2, 3, 4, 6))
    )
    if inputs.integrity_valid is not True:
        blockers.append("BLOCKED_INTEGRITY_NOT_VERIFIED")
    if inputs.primary_comparator is None:
        blockers.append("BLOCKED_PRIMARY_COMPARATOR_NOT_FROZEN")
    if inputs.formal_complete is not True or inputs.learned_vla is None:
        blockers.append("BLOCKED_FORMAL_VLA_RESULTS_INCOMPLETE")
    elif any(gate.status == "UNKNOWN" for gate in gates):
        blockers.append("BLOCKED_ANALYSIS_EVIDENCE_INCOMPLETE")
    blockers = list(dict.fromkeys(blockers))
    vla_admissible = not blockers and inputs.formal_complete is True and inputs.integrity_valid is True
    reasons: list[str] = []
    safe: list[str] = []

    if controlled_support:
        safe.append("Complete validated controlled results support planning-problem preservation and controlled execution under repeated interruptions; this is mechanism evidence only.")
    if blockers:
        status = "PARTIAL_SUPPORT" if controlled_support else next(
            (item for item in blockers if item.startswith("BLOCKED_")), "BLOCKED_FORMAL_READINESS")
        reasons.append("Learned-VLA runtime conclusions are blocked; incomplete or unaudited cells provide no support.")
        if controlled_support:
            reasons.append("PARTIAL_SUPPORT is restricted to the separately complete, validated controlled mechanism protocol.")
        if not safe:
            safe.append("The formal evidence is incomplete or not fully validated; no empirical runtime conclusion is available.")
    elif all(gate.status == "PASS" for gate in gates):
        status = "GO"
        reasons.append("All seven registered learned-VLA runtime gates passed on complete, integrity-validated evidence.")
        safe.append("On the tested tasks and frozen execution stack, persistent local editing preserved the planning problem and improved downstream learned-VLA execution versus the frozen nonpersistent comparator as interruptions accumulated.")
    elif (inputs.learned_vla.risk_difference > 0 and gates[1].status == "PASS"
          and gates[4].status == "PASS") or controlled_support:
        status = "PARTIAL_SUPPORT"
        reasons.append("The complete evidence supports only part of the registered runtime claim; at least one binding gate failed.")
        if inputs.learned_vla.risk_difference > 0 and gates[1].status == "PASS" and gates[4].status == "PASS":
            safe.append("Complete learned-VLA results show a positive paired execution difference and higher temporally preceding planning fidelity, but the full registered runtime criteria were not met.")
    else:
        status = "NO_GO"
        reasons.append("Complete valid results did not satisfy the registered runtime claim or the prespecified partial-support rule.")
        safe.append("The complete formal experiment did not establish the registered runtime claim; failure to establish it does not prove absence of an effect.")

    if vla_admissible:
        reasons.extend(f"{gate.name}: {gate.status}" for gate in gates if gate.status != "PASS")
        e = inputs.learned_vla
        safe.append(f"At learned-VLA K=4, the paired CoPE-minus-comparator success difference was {e.risk_difference:.6g}, with two-sided 95% interval [{e.paired_ci_lower:.6g}, {e.paired_ci_upper:.6g}].")
    forbidden = list(BASE_FORBIDDEN_CLAIMS)
    if status != "GO":
        forbidden.append("The full preregistered learned-VLA runtime claim passed all seven gates.")
    if not vla_admissible:
        forbidden.append("This run establishes learned-VLA execution improvement or learned-VLA non-inferiority.")
    if not controlled_support:
        forbidden.append("This decision establishes the prespecified complete controlled mechanism-support criteria.")
    return ClaimDecision(status, gates, tuple(reasons), tuple(blockers), controlled_support,
                         tuple(safe), tuple(forbidden),
                         _generic_interpretation(inputs.learned_vla, vla_admissible))


# Explicit long-form alias for callers that name this module after its output.
evaluate_claim_decision = evaluate_claims

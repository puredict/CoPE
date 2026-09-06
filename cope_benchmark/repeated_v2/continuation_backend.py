"""Public-context bridge to the archived continuation-carrying repair package.

The archived 2-D operator model is deliberately an optional capability. It is
not a simulator, perception system, or learned policy. The complete accepted
planning problem goes to the common nominal planner; only explicitly accepted
``continuation_assumptions['repair']`` requirements enter the recovery search.
The bridge never imports the legacy CoPE state compiler or owns an environment.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import sys
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, Protocol


class PlannerBackendUnavailable(RuntimeError):
    pass


class UnsupportedPlanningSemantics(ValueError):
    pass


class RecoveryGateBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class ContinuationBackendConfig:
    package_root: str | None = None
    horizon_budget: int = 200
    candidate_count: int = 4
    max_translation_per_step: float = 0.05
    max_rotation_per_step: float = 0.1
    restore_radius: float = 0.12

    def __post_init__(self) -> None:
        for name in ('horizon_budget', 'candidate_count'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be a positive integer')
        for name in ('max_translation_per_step', 'max_rotation_per_step', 'restore_radius'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')


@dataclass(frozen=True)
class PublicRepairObservation:
    state: tuple[float, float, float]
    abstract_flags: Mapping[str, bool]
    timestamp: int
    evidence_ids: tuple[str, ...]
    reacquire_position: tuple[float, float] | None = None
    task_goal: tuple[float, float] | None = None


@dataclass(frozen=True)
class RecoveryVerification:
    """A public forward model predicts an endpoint; the bridge checks it itself."""

    ok: bool
    final_state: tuple[float, float, float]
    realized_flags: Mapping[str, bool]
    duration: int
    reason: str = ''


class PublicRecoveryVerifier(Protocol):
    provider_id: str
    uses_hidden_truth: bool

    def verify(self, *, stages: tuple[Mapping[str, Any], ...],
               observation: PublicRepairObservation,
               handoff_state: tuple[float, float, float],
               required_true: tuple[str, ...],
               required_false: tuple[str, ...]) -> RecoveryVerification: ...


def _vector(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise UnsupportedPlanningSemantics('archived repair model requires an explicit 2-D pose [x,y,theta]')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise UnsupportedPlanningSemantics('repair pose must contain three finite numbers')
    return tuple(float(v) for v in value)


def _point(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise UnsupportedPlanningSemantics('public repair targets require two finite coordinates')
    return tuple(float(v) for v in value)


def _load_engine(config: ContinuationBackendConfig) -> SimpleNamespace:
    root = Path(config.package_root).expanduser().resolve() if config.package_root else (
        Path(__file__).resolve().parents[2] / 'research/server_sync_20260905/content/fvl12/v/cope_r4_20260905/code'
    )
    package = root / 'rekep_repair'
    if not (package / 'repair/repair_manager.py').is_file():
        raise PlannerBackendUnavailable('BLOCKED_CONTINUATION_BACKEND_UNAVAILABLE: configure package_root')
    prior = sys.modules.get('rekep_repair')
    if prior is not None and Path(prior.__file__).resolve().parent != package.resolve():
        raise PlannerBackendUnavailable('a different rekep_repair package is already imported')
    sys.path.insert(0, str(root))
    try:
        modules = {name: importlib.import_module('rekep_repair.' + name) for name in (
            'events.event', 'program.continuation', 'program.contracts', 'program.stage',
            'program.task_program', 'repair.abstract_state', 'repair.repair_manager',
            'repair.synthesis_generator', 'repair.operator', 'repair.feasibility_filter',
            'repair.rollout_verifier',
        )}
        numpy = importlib.import_module('numpy')
    except ImportError as exc:
        raise PlannerBackendUnavailable(f'BLOCKED_CONTINUATION_BACKEND_UNAVAILABLE: {exc}') from exc
    finally:
        sys.path.remove(str(root))
    identity = hashlib.sha256()
    for path in sorted(package.rglob('*.py')):
        identity.update(path.relative_to(package).as_posix().encode())
        identity.update(b'\0')
        identity.update(path.read_bytes())
    symbols = {symbol: getattr(modules[module], symbol) for symbol, module in {
        'Event': 'events.event', 'EventType': 'events.event',
        'Continuation': 'program.continuation', 'ball_contract': 'program.contracts',
        'StageSpec': 'program.stage', 'StageState': 'program.stage', 'Mode': 'program.stage',
        'TaskProgram': 'program.task_program', 'AbstractState': 'repair.abstract_state',
        'RepairGoal': 'repair.abstract_state', 'RepairManager': 'repair.repair_manager',
        'SynthesisGenerator': 'repair.synthesis_generator', 'RepairParams': 'repair.operator',
        'ControlLimits': 'repair.feasibility_filter', 'RolloutReport': 'repair.rollout_verifier',
    }.items()}
    return SimpleNamespace(**symbols, np=numpy, package_sha256=identity.hexdigest())


def _stage_record(stage: Any) -> Mapping[str, Any]:
    # Deliberately avoid forwarding arbitrary legacy metadata or executable guards.
    return MappingProxyType({
        'stage_id': stage.stage_id, 'operator': stage.metadata['operator'],
        'max_steps': stage.max_steps, 'mode': stage.mode.value,
    })


def _plain(value: Any) -> Any:
    if value is None or type(value) in (str, bool, int, float):
        return value
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if hasattr(value, 'tolist'):
        return _plain(value.tolist())
    return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_plain(value), sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


class _VerifierPort:
    def __init__(self, owner: 'ContinuationPlannerBackend') -> None:
        self.owner = owner

    def verify(self, candidate: Any, observation: PublicRepairObservation,
               goal: Any, continuation: Any) -> Any:
        owner, engine = self.owner, self.owner._engine
        result = owner.verifier.verify(
            stages=tuple(_stage_record(s) for s in candidate.stages),
            observation=observation,
            handoff_state=tuple(float(v) for v in continuation.state),
            required_true=tuple(sorted(goal.required_true)),
            required_false=tuple(sorted(goal.required_false)),
        )
        if type(result) is not RecoveryVerification or type(result.ok) is not bool:
            raise RecoveryGateBlocked('public verifier returned an invalid result')
        final = _vector(result.final_state)
        realized = owner._abstract(result.realized_flags)
        residual = goal.residual(realized)
        restore_ok = continuation.restorable_from(engine.np.asarray(final))
        valid_duration = type(result.duration) is int and 0 <= result.duration <= owner.config.horizon_budget
        ok = result.ok and not residual and restore_ok and valid_duration
        return engine.RolloutReport(
            ok=ok, reason=result.reason if ok else 'public verification or restore requirements failed',
            predicted_duration=result.duration if valid_duration else 0,
            predicted_handoff_error=continuation.handoff_error(engine.np.asarray(final)),
            predicted_attachment='grasped' if realized.object_grasped else 'released',
            predicted_min_clearance=0.0, event_residual=residual, restore_ok=restore_ok,
        )


class ContinuationPlannerBackend:
    """Search/verify/splice recovery and expose a gated accepted nominal suffix.

``capture`` precedes event injection. ``solve`` uses the fresh post-event public
context. Execution must acknowledge each recovery stage through
``complete_recovery_stage``; returning a plan is never evidence of completion.
The injected verifier must use public observations, not a privileged simulator
checkpoint. Model identity is recorded alongside the frozen package digest.
"""

    provider_id = 'continuation_carrying_repair_v2'
    uses_hidden_truth = False

    def __init__(self, *, nominal_backend: Any, verifier: PublicRecoveryVerifier,
                 config: ContinuationBackendConfig | None = None) -> None:
        if getattr(nominal_backend, 'uses_hidden_truth', None) is not False:
            raise PlannerBackendUnavailable('nominal backend must explicitly exclude hidden truth')
        if getattr(verifier, 'uses_hidden_truth', None) is not False or not getattr(verifier, 'provider_id', ''):
            raise PlannerBackendUnavailable('public recovery verifier identity and truth exclusion are required')
        self.config = config or ContinuationBackendConfig()
        self.nominal_backend, self.verifier = nominal_backend, verifier
        self._engine = _load_engine(self.config)
        self._flag_names = frozenset(f.name for f in fields(self._engine.AbstractState))
        self._program = None
        self._continuation = None
        self._goal = None
        self._captured_event = None
        self._last_observation_step = -1
        self._report: dict[str, Any] = {}
        self._nominal_plan = None
        self._captured_evidence: tuple[str, ...] = ()

    def _abstract(self, flags: Any) -> Any:
        if not isinstance(flags, Mapping) or set(flags) != self._flag_names:
            raise UnsupportedPlanningSemantics('public repair facts must explicitly cover exactly the archived abstract-state vocabulary')
        if any(type(value) is not bool for value in flags.values()):
            raise UnsupportedPlanningSemantics('public repair facts must be booleans')
        return self._engine.AbstractState(**dict(flags))

    def _observation(self, context: Any) -> PublicRepairObservation:
        matches = [fact for fact in context.beliefs if fact.key == 'repair_observation']
        if len(matches) != 1:
            raise UnsupportedPlanningSemantics('one public repair_observation belief is required')
        fact = matches[0]
        value = fact.value
        if not isinstance(value, Mapping) or not {'state', 'abstract_flags'} <= set(value) or set(value) - {
                'state', 'abstract_flags', 'reacquire_position', 'task_goal'}:
            raise UnsupportedPlanningSemantics('repair_observation contains missing or unsupported public fields')
        abstract = self._abstract(value['abstract_flags'])
        if type(fact.timestamp) is not int or fact.timestamp < 0 or not fact.evidence_ids:
            raise UnsupportedPlanningSemantics('repair observation requires a timestamp and evidence references')
        return PublicRepairObservation(_vector(value['state']), MappingProxyType(dict(abstract.__dict__)),
                                       fact.timestamp, tuple(fact.evidence_ids),
                                       _point(value.get('reacquire_position')), _point(value.get('task_goal')))

    def capture(self, *, context: Any, event_id: str) -> Mapping[str, Any]:
        if not isinstance(event_id, str) or not event_id:
            raise ValueError('event_id is required')
        if self._program is not None and self._program.in_repair and not self._program.active_state() == self._engine.StageState.RESUMED:
            raise RecoveryGateBlocked('cannot overwrite an unfinished recovery')
        observation = self._observation(context)
        active = context.continuation.active_stage
        if not active:
            raise UnsupportedPlanningSemantics('an interrupted active stage is required')
        engine = self._engine
        # No task-ID lookup: this skeleton contains only the public active stage.
        if self._program is None or self._program.finished:
            self._program = engine.TaskProgram([engine.StageSpec(stage_id=active, mode=engine.Mode.TRANSPORT)])
        elif active != self._program.active_id():
            raise RecoveryGateBlocked('public active stage disagrees with the carried program')
        state = engine.np.asarray(observation.state, dtype=float)
        handoff = state[:2].copy()
        self._continuation = engine.Continuation(
            interrupted_stage_id=active, stage_mode=engine.Mode.TRANSPORT,
            state=state.copy(), ee_pose=state.copy(), handoff_pose=handoff,
            attachment_state={'object': 'grasped' if observation.abstract_flags['object_grasped'] else 'released'},
            resume_contract=engine.ball_contract('public-boundary-handoff', state.copy(), self.config.restore_radius),
            timestamp=observation.timestamp, event_id=event_id,
        )
        self._captured_event = event_id
        self._captured_evidence = observation.evidence_ids
        self._last_observation_step = observation.timestamp
        self._report = {'event_id': event_id, 'captured_at_step': observation.timestamp,
                        'handoff_state': observation.state, 'package_sha256': engine.package_sha256,
                        'verifier_provider_id': self.verifier.provider_id}
        return MappingProxyType(dict(self._report))

    def solve(self, *, problem: Any, context: Any) -> Any:
        # The nominal backend receives the entire accepted problem. It must
        # reject unsupported constraints, preferences, or goals itself.
        plan = self.nominal_backend.solve(problem=problem, context=context)
        request = problem.continuation_assumptions.get('repair')
        if request is None:
            if self._program is not None and self._program.in_repair and self._program.active_state() != self._engine.StageState.RESUMED:
                raise RecoveryGateBlocked('accepted plan omitted an unfinished recovery')
            return plan
        if not isinstance(request, Mapping) or set(request) != {'required_true', 'required_false'}:
            raise UnsupportedPlanningSemantics('repair requires explicit required_true and required_false only')
        requirements = {}
        for key in ('required_true', 'required_false'):
            values = request[key]
            if not isinstance(values, (list, tuple)) or any(type(v) is not str for v in values) or len(set(values)) != len(values):
                raise UnsupportedPlanningSemantics('repair requirements must be unique strings')
            if not set(values) <= self._flag_names:
                raise UnsupportedPlanningSemantics('unsupported repair requirement')
            requirements[key] = frozenset(values)
        if requirements['required_true'] & requirements['required_false']:
            raise UnsupportedPlanningSemantics('contradictory repair requirements')
        if 'restore_valid' not in requirements['required_true']:
            raise UnsupportedPlanningSemantics('accepted recovery must explicitly require a valid restore')
        if self._continuation is None:
            raise RecoveryGateBlocked('capture must run before event injection')
        if self._program.in_repair and self._program.active_state() != self._engine.StageState.RESUMED:
            raise RecoveryGateBlocked('recovery already planned; do not silently replace its suffix')
        observation = self._observation(context)
        if observation.timestamp < self._continuation.timestamp:
            raise RecoveryGateBlocked('post-event observation precedes captured boundary')
        if set(observation.evidence_ids) == set(self._captured_evidence):
            raise RecoveryGateBlocked('post-event observation must carry fresh evidence references')
        engine = self._engine
        initial = self._abstract(observation.abstract_flags)
        if not initial.object_grasped and initial.new_target_known and observation.reacquire_position is None:
            raise UnsupportedPlanningSemantics('reacquisition requires a public reacquire position')
        if initial.target_changed and initial.new_target_known and observation.task_goal is None:
            raise UnsupportedPlanningSemantics('target change requires a public task-goal grounding')
        self._goal = engine.RepairGoal(**requirements, label='accepted-public-recovery')
        if self._goal.satisfied_by(initial):
            if not self._continuation.restorable_from(engine.np.asarray(observation.state)):
                raise RecoveryGateBlocked('claimed restoration contradicts the captured handoff')
            return plan
        params = engine.RepairParams(
            theta_pour=float(self._continuation.state[2]), theta_hold=float(observation.state[2]),
            d_safe=0.0, handoff_pose=self._continuation.handoff_pose,
            handoff_theta=float(self._continuation.state[2]), max_steps=self.config.horizon_budget,
            target_pos=None if observation.reacquire_position is None else engine.np.asarray(observation.reacquire_position),
            task_goal=None if observation.task_goal is None else engine.np.asarray(observation.task_goal),
        )
        generator = engine.SynthesisGenerator(params, k=self.config.candidate_count)
        manager = engine.RepairManager(
            params=params, limits=engine.ControlLimits(self.config.max_translation_per_step, self.config.max_rotation_per_step),
            anchor_id=self._program.active_id(), successor_id='accepted-suffix', generator=generator,
            cfg=None, horizon_budget=self.config.horizon_budget,
        )
        manager.verifier = _VerifierPort(self)  # never take RepairManager's unverified branch
        event = engine.Event(engine.EventType.PERSISTENT_INFEASIBILITY,
                             t=observation.timestamp, event_id=self._captured_event)
        result = manager.plan(event, self._continuation, initial, self._goal, ctx=observation)
        self._report.update({'generated': tuple(result.generated), 'rejected': tuple(result.rejected),
                             'rollouts': tuple(result.rollouts), 'selected': None})
        if result.selected is None:
            raise RecoveryGateBlocked('no candidate passed public recovery verification')
        self._program.interrupt_active_stage(self._continuation)
        # Re-interrupting a RESUMED node clears the old continuation inside the
        # frozen program. Install the new contract only after that transition.
        self._program.set_pending_continuation(self._continuation)
        self._program.splice_repair_before_successor(result.selected.stages, self._continuation)
        self._report['selected'] = result.selected.template_name
        self._report['recovery_stages'] = tuple(_stage_record(s) for s in self._program.stages() if s.kind == 'repair')
        self._nominal_plan = plan
        self._last_observation_step = observation.timestamp
        return self._with_recovery(plan)

    def _with_recovery(self, plan: Any) -> Any:
        try:
            names = {field.name for field in fields(plan)}
        except TypeError as exc:
            raise PlannerBackendUnavailable('nominal planner must return the common ExecutionPlan record') from exc
        if not {'macro_actions', 'diagnostics'} <= names:
            raise PlannerBackendUnavailable('common ExecutionPlan must expose macro_actions and diagnostics')
        if any(macro.get('recovery') for macro in plan.macro_actions):
            raise RecoveryGateBlocked('nominal plan already contains a recovery prefix')
        if getattr(plan, 'status', 'planned') != 'planned':
            raise RecoveryGateBlocked('nominal planning was blocked')
        recovery = tuple({
            'recovery': True, 'target_occurrence_id': None,
            'predicate': 'physical_recovery', 'arguments': (stage['operator'],),
            'stage_id': stage['stage_id'], 'max_steps': stage['max_steps'],
            'compiled_instruction': {
                'instruction': f"Perform the physical recovery operator {stage['operator']} and verify its public completion condition.",
                'operator': stage['operator'], 'stage_id': stage['stage_id'],
                'max_steps': stage['max_steps'],
                'handoff_state': tuple(float(v) for v in self._continuation.state),
            },
        } for stage in self.recovery_stages)
        detail = {'continuation_repair': _plain(self.audit)}
        diagnostics = ({**dict(plan.diagnostics), **detail} if isinstance(plan.diagnostics, Mapping)
                       else (*plan.diagnostics, json.dumps(detail, sort_keys=True,
                                                          separators=(',', ':'), allow_nan=False)))
        return replace(plan, provider_id=self.provider_id,
                       macro_actions=(*recovery, *plan.macro_actions), diagnostics=diagnostics)

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self._report))

    @property
    def recovery_stages(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._report.get('recovery_stages', ()))

    def complete_recovery_stage(self, *, stage_id: str, context: Any) -> bool:
        if self._program is None or not self._program.in_repair or self._program.active_id() != stage_id:
            raise RecoveryGateBlocked('stage is not the current recovery stage')
        observation = self._observation(context)
        if observation.timestamp <= self._last_observation_step:
            raise RecoveryGateBlocked('stage completion requires a fresh public observation')
        stage = self._program.active_stage()
        operator = stage.metadata.get('operator')
        flags = observation.abstract_flags
        needed = {
            'Suspend': ('nominal_suspended',), 'Stabilize': ('object_stable', 'object_grasped'),
            'Retreat': ('safe_clearance',), 'WaitUntilClear': ('safe_clearance',),
            'ReacquireTarget': ('object_grasped',), 'UpdateTargetContract': ('aligned_to_current_target',),
            'Realign': ('ee_at_handoff', 'orientation_restored', 'object_grasped'),
            'Resume': ('restore_valid', 'object_grasped'),
        }
        if operator not in needed or any(not flags[name] for name in needed[operator]):
            raise RecoveryGateBlocked('public observation does not certify the active repair operator')
        if operator == 'WaitUntilClear' and flags['obstacle_present']:
            raise RecoveryGateBlocked('obstacle is still present')
        if operator in ('Realign', 'Resume') and not self._continuation.restorable_from(self._engine.np.asarray(observation.state)):
            raise RecoveryGateBlocked('captured handoff contract is not satisfied')
        if operator == 'Resume':
            if not self._goal.satisfied_by(self._abstract(flags)):
                raise RecoveryGateBlocked('accepted repair goal is still unsatisfied')
            if not self._program.mark_restore_validated(self._engine.np.asarray(observation.state)):
                raise RecoveryGateBlocked('frozen TaskProgram restore gate rejected resume')
        self._program.advance()
        self._last_observation_step = observation.timestamp
        resumed = self._program.active_state() == self._engine.StageState.RESUMED
        self._report['resumed'] = resumed
        self._report['active_stage'] = self._program.active_id()
        return resumed

    def resumed_plan(self) -> Any:
        if self._program is None or self._program.active_state() != self._engine.StageState.RESUMED:
            raise RecoveryGateBlocked('nominal suffix is locked until restoration and accepted-goal verification')
        return self._nominal_plan

    def before_macro(self, macro: Mapping[str, Any]) -> None:
        """The common executor calls this immediately before dispatch."""
        if macro.get('recovery') is True:
            if self._program is None or not self._program.in_repair or self._program.active_id() != macro.get('stage_id'):
                raise RecoveryGateBlocked('recovery macro is not the current frozen program stage')
            return
        if self._program is not None and self._program.in_repair and self._program.active_state() != self._engine.StageState.RESUMED:
            raise RecoveryGateBlocked('nominal suffix is locked until recovery completion')

    def snapshot(self) -> Mapping[str, Any]:
        """Only JSON data; no pickle, environment, callable, or plugin import path."""
        program = None
        if self._program is not None:
            program = {
                'stages': [{'stage_id': s.stage_id, 'mode': s.mode.value, 'kind': s.kind,
                            'max_steps': s.max_steps, 'metadata': _plain(s.metadata)}
                           for s in self._program.stages()],
                'state': {key: value.value for key, value in self._program.state.items()},
                'attributes': {name: getattr(self._program, name) for name in (
                    'active_index', 'finished', 'failed', 'in_repair', '_interrupted_id',
                    '_resumed_id', '_restore_validated', '_repair_counter')},
                'provenance': _plain(self._program.provenance),
            }
        continuation = None
        if self._continuation is not None:
            continuation = {
                'interrupted_stage_id': self._continuation.interrupted_stage_id,
                'state': _plain(self._continuation.state),
                'attachment_state': dict(self._continuation.attachment_state),
                'timestamp': self._continuation.timestamp, 'event_id': self._continuation.event_id,
            }
        data = {
            'version': 1, 'package_sha256': self._engine.package_sha256,
            'verifier_provider_id': self.verifier.provider_id, 'config': _plain(self.config),
            'program': program, 'continuation': continuation,
            'goal': None if self._goal is None else {
                'required_true': sorted(self._goal.required_true),
                'required_false': sorted(self._goal.required_false), 'label': self._goal.label},
            'captured_event': self._captured_event, 'captured_evidence': self._captured_evidence,
            'last_observation_step': self._last_observation_step,
            'report': _plain(self._report),
            'nominal_plan': None if self._nominal_plan is None else _plain(self._nominal_plan),
        }
        return {**_plain(data), 'snapshot_sha256': _digest(data)}

    def restore(self, state: Mapping[str, Any], *, plan_factory: Any = None) -> None:
        """Rehydrate the selected program without searching or invoking a model."""
        data = dict(state)
        digest = data.pop('snapshot_sha256', None)
        if _digest(data) != digest or data.get('version') != 1:
            raise RecoveryGateBlocked('continuation snapshot integrity mismatch')
        if data.get('package_sha256') != self._engine.package_sha256 or data.get('verifier_provider_id') != self.verifier.provider_id or data.get('config') != _plain(self.config):
            raise RecoveryGateBlocked('continuation snapshot dependency identity mismatch')
        engine = self._engine
        raw = data['continuation']
        continuation = None
        if raw is not None:
            vector = engine.np.asarray(_vector(raw['state']))
            continuation = engine.Continuation(
                interrupted_stage_id=raw['interrupted_stage_id'], stage_mode=engine.Mode.TRANSPORT,
                state=vector.copy(), ee_pose=vector.copy(), handoff_pose=vector[:2].copy(),
                attachment_state=dict(raw['attachment_state']), timestamp=raw['timestamp'], event_id=raw['event_id'],
                resume_contract=engine.ball_contract('public-boundary-handoff', vector.copy(), self.config.restore_radius),
            )
        program = None
        if data['program'] is not None:
            raw_program = data['program']
            stages = [engine.StageSpec(stage_id=s['stage_id'], mode=engine.Mode(s['mode']), kind=s['kind'],
                                       max_steps=s['max_steps'], metadata=dict(s['metadata']))
                      for s in raw_program['stages']]
            program = engine.TaskProgram(stages)
            program.state = {key: engine.StageState(value) for key, value in raw_program['state'].items()}
            for name, value in raw_program['attributes'].items():
                if name not in {'active_index', 'finished', 'failed', 'in_repair', '_interrupted_id', '_resumed_id', '_restore_validated', '_repair_counter'}:
                    raise RecoveryGateBlocked('unsupported frozen program snapshot field')
                setattr(program, name, value)
            program.provenance = raw_program['provenance']
            program.set_pending_continuation(continuation)
            if not program.order_graph_consistent() or set(program.state) != {s.stage_id for s in stages} or not 0 <= program.active_index < len(stages):
                raise RecoveryGateBlocked('restored frozen program is inconsistent')
        nominal_plan = None
        if data['nominal_plan'] is not None:
            if plan_factory is None:
                from .planner_backend import ExecutionPlan
                plan_factory = ExecutionPlan
            nominal_plan = plan_factory(**data['nominal_plan'])
        goal = data['goal']
        self._goal = None if goal is None else engine.RepairGoal(
            required_true=frozenset(goal['required_true']), required_false=frozenset(goal['required_false']), label=goal['label'])
        self._program, self._continuation, self._nominal_plan = program, continuation, nominal_plan
        self._captured_event, self._captured_evidence = data['captured_event'], tuple(data['captured_evidence'])
        self._last_observation_step, self._report = data['last_observation_step'], data['report']

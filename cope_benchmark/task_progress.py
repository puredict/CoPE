from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol, Sequence


TASK_PROGRESS_VERSION = "repeated_progress_v1"


class StateView(Protocol):
    def libero_predicate(self, predicate: str, arguments: Sequence[str]) -> bool: ...

    def object_position(self, object_name: str) -> Sequence[float]: ...

    def final_success(self) -> bool: ...


@dataclass(frozen=True)
class ProgressPredicateSpec:
    name: str
    kind: str
    arguments: tuple[Any, ...] = ()
    reversible: bool = True
    commitment: bool = False
    weight: float = 1.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskProgressDefinition:
    task_suite: str
    task_id: int
    task_name: str
    language: str
    predicates: tuple[ProgressPredicateSpec, ...]
    target_joints: tuple[str, ...]
    receptacle_joints: tuple[str, ...]
    tool_joints: tuple[str, ...]
    workspace_xy_bounds: tuple[tuple[float, float], tuple[float, float]]

    @property
    def key(self) -> tuple[str, int]:
        return self.task_suite, self.task_id

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["predicates"] = [predicate.to_dict() for predicate in self.predicates]
        return value


def _goal(
    name: str,
    predicate: str,
    *arguments: str,
    description: str,
) -> ProgressPredicateSpec:
    return ProgressPredicateSpec(
        name=name,
        kind="libero_predicate",
        arguments=(predicate, *arguments),
        reversible=True,
        commitment=True,
        weight=1.0,
        description=description,
    )


def _lifted(name: str, object_name: str, threshold: float) -> ProgressPredicateSpec:
    return ProgressPredicateSpec(
        name=name,
        kind="object_z_at_least",
        arguments=(object_name, threshold),
        reversible=True,
        commitment=False,
        weight=0.0,
        description=f"{object_name} center is at or above world z={threshold}",
    )


def _reachable(name: str, object_name: str) -> ProgressPredicateSpec:
    return ProgressPredicateSpec(
        name=name,
        kind="object_within_xy_bounds",
        arguments=(object_name, (-0.35, 0.35), (-0.36, 0.36)),
        reversible=True,
        commitment=False,
        weight=0.0,
        description=f"{object_name} is inside the preregistered accessible workspace",
    )


def _final() -> ProgressPredicateSpec:
    return ProgressPredicateSpec(
        name="final_goal_currently_satisfied",
        kind="final_success",
        reversible=True,
        commitment=False,
        weight=0.0,
        description="exact LIBERO goal conjunction is currently satisfied",
    )


TASK_DEFINITIONS: dict[tuple[str, int], TaskProgressDefinition] = {
    ("libero_10", 0): TaskProgressDefinition(
        task_suite="libero_10",
        task_id=0,
        task_name="LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket",
        language="put both the alphabet soup and the tomato sauce in the basket",
        predicates=(
            _lifted("alphabet_soup_lifted", "alphabet_soup_1", 0.51),
            _goal(
                "alphabet_soup_in_basket",
                "in",
                "alphabet_soup_1",
                "basket_1_contain_region",
                description="first independently measurable placement commitment",
            ),
            _lifted("tomato_sauce_lifted", "tomato_sauce_1", 0.53),
            _goal(
                "tomato_sauce_in_basket",
                "in",
                "tomato_sauce_1",
                "basket_1_contain_region",
                description="second independently measurable placement commitment",
            ),
            _reachable("basket_reachable", "basket_1"),
            _final(),
        ),
        target_joints=("alphabet_soup_1_joint0", "tomato_sauce_1_joint0"),
        receptacle_joints=("basket_1_joint0",),
        tool_joints=("alphabet_soup_1_joint0", "tomato_sauce_1_joint0"),
        workspace_xy_bounds=((-0.35, 0.35), (-0.36, 0.36)),
    ),
    ("libero_10", 1): TaskProgressDefinition(
        task_suite="libero_10",
        task_id=1,
        task_name="LIVING_ROOM_SCENE2_put_both_the_cream_cheese_box_and_the_butter_in_the_basket",
        language="put both the cream cheese box and the butter in the basket",
        predicates=(
            _lifted("cream_cheese_lifted", "cream_cheese_1", 0.50),
            _goal(
                "cream_cheese_in_basket",
                "in",
                "cream_cheese_1",
                "basket_1_contain_region",
                description="first independently measurable placement commitment",
            ),
            _lifted("butter_lifted", "butter_1", 0.49),
            _goal(
                "butter_in_basket",
                "in",
                "butter_1",
                "basket_1_contain_region",
                description="second independently measurable placement commitment",
            ),
            _reachable("basket_reachable", "basket_1"),
            _final(),
        ),
        target_joints=("cream_cheese_1_joint0", "butter_1_joint0"),
        receptacle_joints=("basket_1_joint0",),
        tool_joints=("cream_cheese_1_joint0", "butter_1_joint0"),
        workspace_xy_bounds=((-0.35, 0.35), (-0.36, 0.36)),
    ),
    ("libero_10", 4): TaskProgressDefinition(
        task_suite="libero_10",
        task_id=4,
        task_name=(
            "LIVING_ROOM_SCENE5_put_the_white_mug_on_the_left_plate_and_put_the_"
            "yellow_and_white_mug_on_the_right_plate"
        ),
        language=(
            "put the white mug on the left plate and put the yellow and white mug on the right plate"
        ),
        predicates=(
            _lifted("white_mug_lifted", "porcelain_mug_1", 0.54),
            _goal(
                "white_mug_on_left_plate",
                "on",
                "porcelain_mug_1",
                "plate_1",
                description="left-plate placement commitment",
            ),
            _lifted("yellow_white_mug_lifted", "white_yellow_mug_1", 0.54),
            _goal(
                "yellow_white_mug_on_right_plate",
                "on",
                "white_yellow_mug_1",
                "plate_2",
                description="right-plate placement commitment",
            ),
            _reachable("left_plate_reachable", "plate_1"),
            _reachable("right_plate_reachable", "plate_2"),
            _final(),
        ),
        target_joints=("porcelain_mug_1_joint0", "white_yellow_mug_1_joint0"),
        receptacle_joints=("plate_1_joint0", "plate_2_joint0"),
        tool_joints=("porcelain_mug_1_joint0", "white_yellow_mug_1_joint0"),
        workspace_xy_bounds=((-0.35, 0.35), (-0.36, 0.36)),
    ),
    ("libero_10", 8): TaskProgressDefinition(
        task_suite="libero_10",
        task_id=8,
        task_name="KITCHEN_SCENE8_put_both_moka_pots_on_the_stove",
        language="put both moka pots on the stove",
        predicates=(
            _lifted("right_moka_pot_lifted", "moka_pot_1", 1.03),
            _goal(
                "right_moka_pot_on_stove",
                "on",
                "moka_pot_1",
                "flat_stove_1_cook_region",
                description="first moka-pot placement commitment",
            ),
            _lifted("left_moka_pot_lifted", "moka_pot_2", 1.03),
            _goal(
                "left_moka_pot_on_stove",
                "on",
                "moka_pot_2",
                "flat_stove_1_cook_region",
                description="second moka-pot placement commitment",
            ),
            _goal(
                "stove_remains_on",
                "turnon",
                "flat_stove_1",
                description="unaffected safety/operational commitment",
            ),
            _final(),
        ),
        target_joints=("moka_pot_1_joint0", "moka_pot_2_joint0"),
        # The stove is an articulated fixture without a free joint, so this
        # task is intentionally ineligible for goal_receptacle_moved.
        receptacle_joints=(),
        tool_joints=("moka_pot_1_joint0", "moka_pot_2_joint0"),
        workspace_xy_bounds=((-0.35, 0.35), (-0.36, 0.36)),
    ),
}


def get_task_definition(task_suite: str, task_id: int) -> TaskProgressDefinition:
    try:
        return TASK_DEFINITIONS[(task_suite, int(task_id))]
    except KeyError as exc:
        raise KeyError(f"no repeated-interruption progress definition for {task_suite}:{task_id}") from exc


def evaluate_predicate(spec: ProgressPredicateSpec, state: StateView) -> bool:
    if spec.kind == "libero_predicate":
        predicate = str(spec.arguments[0])
        return bool(state.libero_predicate(predicate, tuple(str(v) for v in spec.arguments[1:])))
    if spec.kind == "object_z_at_least":
        position = state.object_position(str(spec.arguments[0]))
        return float(position[2]) >= float(spec.arguments[1])
    if spec.kind == "object_within_xy_bounds":
        position = state.object_position(str(spec.arguments[0]))
        x_bounds, y_bounds = spec.arguments[1], spec.arguments[2]
        return (
            float(x_bounds[0]) <= float(position[0]) <= float(x_bounds[1])
            and float(y_bounds[0]) <= float(position[1]) <= float(y_bounds[1])
        )
    if spec.kind == "final_success":
        return bool(state.final_success())
    raise ValueError(f"unknown progress predicate kind {spec.kind!r}")


@dataclass
class ProgressSample:
    policy_step: int
    current: dict[str, bool]
    ever_achieved: dict[str, bool]
    irreversible: dict[str, bool]
    commitment_names: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProgressTracker:
    definition: TaskProgressDefinition
    ever_achieved: dict[str, bool] = field(default_factory=dict)
    history: list[ProgressSample] = field(default_factory=list)

    def sample(self, state: StateView, policy_step: int) -> ProgressSample:
        current: dict[str, bool] = {}
        for spec in self.definition.predicates:
            value = evaluate_predicate(spec, state)
            current[spec.name] = value
            self.ever_achieved[spec.name] = bool(self.ever_achieved.get(spec.name, False) or value)
        # ``ever_achieved`` is the irreversible episode-history representation;
        # physical predicates remain explicitly marked reversible.
        irreversible = {f"ever:{name}": value for name, value in self.ever_achieved.items()}
        sample = ProgressSample(
            policy_step=int(policy_step),
            current=current,
            ever_achieved=dict(self.ever_achieved),
            irreversible=irreversible,
            commitment_names=tuple(spec.name for spec in self.definition.predicates if spec.commitment),
        )
        self.history.append(sample)
        return sample


class LiberoStateView:
    """Deterministic ground-truth view used only for benchmark scoring."""

    def __init__(self, env: Any):
        self.wrapper = env
        self.env = getattr(env, "env", env)

    def libero_predicate(self, predicate: str, arguments: Sequence[str]) -> bool:
        state = [str(predicate).lower(), *[str(value) for value in arguments]]
        return bool(self.env._eval_predicate(state))

    def object_position(self, object_name: str) -> Sequence[float]:
        state = self.env.object_states_dict[str(object_name)]
        return tuple(float(value) for value in state.get_geom_state()["pos"])

    def final_success(self) -> bool:
        return bool(self.env._check_success())

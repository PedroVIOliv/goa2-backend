"""
Serialization registration for steps, filters, and misc board entities.

Imported by handler.py to ensure patching happens before engine use.
Must be imported AFTER all step/filter subclasses are defined.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, TypeVar, Union

from pydantic import BaseModel, Discriminator, Tag

from goa2.domain.models.enums import StepType
from goa2.engine import filters_cards as _filters_cards  # noqa: F401
from goa2.engine import filters_geometry as _filters_geometry  # noqa: F401
from goa2.engine import filters_hex as _filters_hex  # noqa: F401
from goa2.engine import filters_units as _filters_units  # noqa: F401
from goa2.engine.steps import cards as _steps_cards  # noqa: F401
from goa2.engine.steps import combat as _steps_combat  # noqa: F401
from goa2.engine.steps import effects as _steps_effects  # noqa: F401
from goa2.engine.steps import markers as _steps_markers  # noqa: F401
from goa2.engine.steps import movement as _steps_movement  # noqa: F401
from goa2.engine.steps import phases as _steps_phases  # noqa: F401
from goa2.engine.steps import reactions as _steps_reactions  # noqa: F401
from goa2.engine.steps import selection as _steps_selection  # noqa: F401
from goa2.engine.steps import utility as _steps_utility  # noqa: F401
from goa2.engine import steps as steps_mod
from goa2.engine.filters_base import FilterCondition
from goa2.engine.filters_composite import AndFilter, CountMatchFilter, OrFilter
from goa2.engine.steps.base import GameStep


ModelT = TypeVar("ModelT", bound=BaseModel)


def _all_subclasses(cls: type[ModelT]) -> list[type[ModelT]]:
    subclasses: list[type[ModelT]] = []
    for subclass in cls.__subclasses__():
        subclasses.append(subclass)
        subclasses.extend(_all_subclasses(subclass))
    return subclasses


def _tag_value(model_cls: type[BaseModel], field_name: str) -> str:
    value = model_cls.model_fields[field_name].default
    return value.value if hasattr(value, "value") else str(value)


def _registered_union(
    base_cls: type[ModelT],
    *,
    field_name: str,
    ignored_tags: set[str] | None = None,
    ignored_classes: set[type[ModelT]] | None = None,
    aliases: Dict[str, type[ModelT]] | None = None,
) -> Any:
    """
    Build a Pydantic tagged union from concrete subclasses of a registered base.

    The one registration path for a new step/filter is now:
    1. add the enum value;
    2. create the subclass with the matching `type` default.

    `aliases` handles intentionally shared tags such as MayRepeatOnceStep, where
    older saves should deserialize to the generalized implementation class.
    """
    ignored_tags = ignored_tags or set()
    ignored_classes = ignored_classes or set()
    aliases = aliases or {}

    classes_by_tag: dict[str, type[ModelT]] = dict(aliases)
    for model_cls in _all_subclasses(base_cls):
        if model_cls in ignored_classes:
            continue
        tag = _tag_value(model_cls, field_name)
        if tag in ignored_tags:
            continue
        if tag in classes_by_tag:
            existing = classes_by_tag[tag]
            if existing is model_cls:
                continue
            raise ValueError(
                f"{model_cls.__name__} and {existing.__name__} share {field_name}={tag}"
            )
        classes_by_tag[tag] = model_cls

    if not classes_by_tag:
        raise ValueError(f"No registered subclasses found for {base_cls.__name__}")

    members = tuple(
        Annotated[model_cls, Tag(tag)]
        for tag, model_cls in sorted(classes_by_tag.items())
    )
    return Union[members]  # type: ignore[valid-type]


def _step_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("type", "")
    return v.type.value if hasattr(v.type, "value") else str(v.type)


def _filter_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("type", "")
    return v.type.value if hasattr(v.type, "value") else str(v.type)


AnyStep = Annotated[
    _registered_union(
        GameStep,
        field_name="type",
        ignored_tags={StepType.GENERIC.value},
        ignored_classes={steps_mod.MayRepeatOnceStep},
        aliases={StepType.MAY_REPEAT_ONCE.value: steps_mod.MayRepeatNTimesStep},
    ),
    Discriminator(_step_discriminator),
]

AnyFilter = Annotated[
    _registered_union(FilterCondition, field_name="type"),
    Discriminator(_filter_discriminator),
]


# ---------------------------------------------------------------------------
# AnyMiscEntity — discriminated union for misc_entities (non-Unit BoardEntities).
# When adding a new BoardEntity type (e.g. Turret, Dragon), add it here with
# its own entity_kind Literal tag. Without this, persistence/rollback will break.
# ---------------------------------------------------------------------------
from goa2.domain.models.base import Placeholder  # noqa: E402
from goa2.domain.models.token import Token  # noqa: E402


def _misc_entity_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("entity_kind", "")
    return getattr(v, "entity_kind", "")


AnyMiscEntity = Annotated[
    Union[
        Annotated[Token, Tag("token")],
        Annotated[Placeholder, Tag("placeholder")],
    ],
    Discriminator(_misc_entity_discriminator),
]


def rebuild_serialization_models() -> None:
    """
    Patch fields that contain polymorphic step/filter data, then rebuild them.

    Pydantic V2 reads field info from `model_fields`, so patching annotations
    alone is not enough after the models have already been constructed.
    """
    from goa2.domain.models.effect import ActiveEffect
    from goa2.domain.state import GameState
    from goa2.engine.effects import StatAura

    GameState.model_fields["execution_stack"].annotation = List[AnyStep]
    GameState.model_fields["misc_entities"].annotation = Dict[str, AnyMiscEntity]

    steps_mod.SelectStep.model_fields["filters"].annotation = List[AnyFilter]
    steps_mod.MultiSelectStep.model_fields["filters"].annotation = List[AnyFilter]
    steps_mod.AttackSequenceStep.model_fields["target_filters"].annotation = List[
        AnyFilter
    ]
    steps_mod.CountStep.model_fields["filters"].annotation = List[AnyFilter]
    steps_mod.MayRepeatNTimesStep.model_fields["steps_template"].annotation = List[
        AnyStep
    ]
    steps_mod.ForEachStep.model_fields["steps_template"].annotation = List[AnyStep]
    steps_mod.CreateEffectStep.model_fields["finishing_steps"].annotation = List[
        AnyStep
    ]
    steps_mod.RespawnMinionAtHexStep.model_fields["hex_filters"].annotation = List[
        AnyFilter
    ]
    ActiveEffect.model_fields["finishing_steps"].annotation = List[AnyStep]
    StatAura.model_fields["count_filters"].annotation = List[AnyFilter]
    OrFilter.model_fields["filters"].annotation = List[AnyFilter]
    AndFilter.model_fields["filters"].annotation = List[AnyFilter]
    CountMatchFilter.model_fields["sub_filters"].annotation = List[AnyFilter]

    for model_cls in (
        steps_mod.RespawnMinionAtHexStep,
        OrFilter,
        AndFilter,
        CountMatchFilter,
        steps_mod.SelectStep,
        steps_mod.MultiSelectStep,
        steps_mod.AttackSequenceStep,
        steps_mod.CountStep,
        steps_mod.MayRepeatNTimesStep,
        steps_mod.ForEachStep,
        steps_mod.CreateEffectStep,
        ActiveEffect,
        StatAura,
        GameState,
    ):
        model_cls.model_rebuild(force=True)


rebuild_serialization_models()

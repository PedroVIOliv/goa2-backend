"""
Sealing module: defines AnyStep discriminated union and patches model annotations.

Imported by handler.py to ensure patching happens before engine use.
Must be imported AFTER all step/filter subclasses are defined.
"""

from typing import Annotated, Any, List, Union

from pydantic import Discriminator, Tag

from goa2.engine.steps import (
    AttackSequenceStep,
    AskConfirmationStep,
    CancelEffectsStep,
    CheckAdjacencyStep,
    CheckLanePushStep,
    CheckPassiveAbilitiesStep,
    CheckUnitTypeStep,
    ChooseMinionRemovalStep,
    CombineBooleanContextStep,
    CreateEffectStep,
    DefeatUnitStep,
    DiscardCardStep,
    EndPhaseCleanupStep,
    EndPhaseStep,
    FastTravelSequenceStep,
    FastTravelStep,
    FinalizeHeroTurnStep,
    FindNextActorStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    ForEachStep,
    LanePushStep,
    LogMessageStep,
    MarkPassiveUsedStep,
    MayRepeatNTimesStep,
    MoveSequenceStep,
    MoveUnitStep,
    MultiSelectStep,
    OfferPassiveStep,
    PlaceMarkerStep,
    PlaceUnitStep,
    PushUnitStep,
    ReactionWindowStep,
    RecordTargetStep,
    RemoveMarkerStep,
    RemoveUnitStep,
    ResolveCombatStep,
    ResolveCardStep,
    ResolveCardTextStep,
    ResolveDefenseTextStep,
    ResolveDisplacementStep,
    ResolveOnBlockEffectStep,
    ResolveTieBreakerStep,
    ResolveUpgradesStep,
    RespawnHeroStep,
    RespawnMinionStep,
    RestoreActionTypeStep,
    ReturnMinionToZoneStep,
    RoundResetStep,
    SelectStep,
    SetActorStep,
    SetContextFlagStep,
    SwapCardStep,
    SwapUnitsStep,
    TriggerGameOverStep,
    ValidateRepeatStep,
)
from goa2.domain.models.enums import StepType


# ---------------------------------------------------------------------------
# Callable discriminator: reads "type" from dict or object, returns tag string
# ---------------------------------------------------------------------------


def _step_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("type", "")
    return v.type.value if hasattr(v.type, "value") else str(v.type)


# MayRepeatOnceStep inherits from MayRepeatNTimesStep with the same StepType
# discriminator (MAY_REPEAT_ONCE). The max_repeats field distinguishes them.
# We map both to MayRepeatNTimesStep in the union.

AnyStep = Annotated[
    Union[
        Annotated[AttackSequenceStep, Tag(StepType.ATTACK_SEQUENCE.value)],
        Annotated[AskConfirmationStep, Tag(StepType.ASK_CONFIRMATION.value)],
        Annotated[CancelEffectsStep, Tag(StepType.CANCEL_EFFECTS.value)],
        Annotated[CheckAdjacencyStep, Tag(StepType.CHECK_ADJACENCY.value)],
        Annotated[CheckLanePushStep, Tag(StepType.CHECK_LANE_PUSH.value)],
        Annotated[
            CheckPassiveAbilitiesStep, Tag(StepType.CHECK_PASSIVE_ABILITIES.value)
        ],
        Annotated[CheckUnitTypeStep, Tag(StepType.CHECK_UNIT_TYPE.value)],
        Annotated[ChooseMinionRemovalStep, Tag(StepType.CHOOSE_MINION_REMOVAL.value)],
        Annotated[
            CombineBooleanContextStep, Tag(StepType.COMBINE_BOOLEAN_CONTEXT.value)
        ],
        Annotated[CreateEffectStep, Tag(StepType.CREATE_EFFECT.value)],
        Annotated[DefeatUnitStep, Tag(StepType.DEFEAT_UNIT.value)],
        Annotated[DiscardCardStep, Tag(StepType.DISCARD_CARD.value)],
        Annotated[EndPhaseCleanupStep, Tag(StepType.END_PHASE_CLEANUP.value)],
        Annotated[EndPhaseStep, Tag(StepType.END_PHASE.value)],
        Annotated[FastTravelSequenceStep, Tag(StepType.FAST_TRAVEL_SEQUENCE.value)],
        Annotated[FastTravelStep, Tag(StepType.FAST_TRAVEL.value)],
        Annotated[FinalizeHeroTurnStep, Tag(StepType.FINALIZE_HERO_TURN.value)],
        Annotated[FindNextActorStep, Tag(StepType.FIND_NEXT_ACTOR.value)],
        Annotated[
            ForceDiscardOrDefeatStep, Tag(StepType.FORCE_DISCARD_OR_DEFEAT.value)
        ],
        Annotated[ForceDiscardStep, Tag(StepType.FORCE_DISCARD.value)],
        Annotated[ForEachStep, Tag(StepType.FOR_EACH.value)],
        Annotated[LanePushStep, Tag(StepType.LANE_PUSH.value)],
        Annotated[LogMessageStep, Tag(StepType.LOG_MESSAGE.value)],
        Annotated[MarkPassiveUsedStep, Tag(StepType.MARK_PASSIVE_USED.value)],
        Annotated[MayRepeatNTimesStep, Tag(StepType.MAY_REPEAT_ONCE.value)],
        Annotated[MoveSequenceStep, Tag(StepType.MOVE_SEQUENCE.value)],
        Annotated[MoveUnitStep, Tag(StepType.MOVE_UNIT.value)],
        Annotated[MultiSelectStep, Tag(StepType.MULTI_SELECT.value)],
        Annotated[OfferPassiveStep, Tag(StepType.OFFER_PASSIVE.value)],
        Annotated[PlaceMarkerStep, Tag(StepType.PLACE_MARKER.value)],
        Annotated[PlaceUnitStep, Tag(StepType.PLACE_UNIT.value)],
        Annotated[PushUnitStep, Tag(StepType.PUSH_UNIT.value)],
        Annotated[ReactionWindowStep, Tag(StepType.REACTION_WINDOW.value)],
        Annotated[RecordTargetStep, Tag(StepType.RECORD_TARGET.value)],
        Annotated[RemoveMarkerStep, Tag(StepType.REMOVE_MARKER.value)],
        Annotated[RemoveUnitStep, Tag(StepType.REMOVE_UNIT.value)],
        Annotated[ResolveCombatStep, Tag(StepType.RESOLVE_COMBAT.value)],
        Annotated[ResolveCardStep, Tag(StepType.RESOLVE_CARD.value)],
        Annotated[ResolveCardTextStep, Tag(StepType.RESOLVE_CARD_TEXT.value)],
        Annotated[ResolveDefenseTextStep, Tag(StepType.RESOLVE_DEFENSE_TEXT.value)],
        Annotated[ResolveDisplacementStep, Tag(StepType.RESOLVE_DISPLACEMENT.value)],
        Annotated[
            ResolveOnBlockEffectStep, Tag(StepType.RESOLVE_ON_BLOCK_EFFECT.value)
        ],
        Annotated[ResolveTieBreakerStep, Tag(StepType.RESOLVE_TIE_BREAKER.value)],
        Annotated[ResolveUpgradesStep, Tag(StepType.RESOLVE_UPGRADES.value)],
        Annotated[RespawnHeroStep, Tag(StepType.RESPAWN_HERO.value)],
        Annotated[RespawnMinionStep, Tag(StepType.RESPAWN_MINION.value)],
        Annotated[RestoreActionTypeStep, Tag(StepType.RESTORE_ACTION_TYPE.value)],
        Annotated[ReturnMinionToZoneStep, Tag(StepType.RETURN_MINION_TO_ZONE.value)],
        Annotated[RoundResetStep, Tag(StepType.ROUND_RESET.value)],
        Annotated[SelectStep, Tag(StepType.SELECT.value)],
        Annotated[SetActorStep, Tag(StepType.SET_ACTOR.value)],
        Annotated[SetContextFlagStep, Tag(StepType.SET_CONTEXT_FLAG.value)],
        Annotated[SwapCardStep, Tag(StepType.SWAP_CARD.value)],
        Annotated[SwapUnitsStep, Tag(StepType.SWAP_UNITS.value)],
        Annotated[TriggerGameOverStep, Tag(StepType.TRIGGER_GAME_OVER.value)],
        Annotated[ValidateRepeatStep, Tag(StepType.VALIDATE_REPEAT.value)],
    ],
    Discriminator(_step_discriminator),
]


# ---------------------------------------------------------------------------
# Same pattern for AnyFilter — override the field-based version in filters.py
# ---------------------------------------------------------------------------
from goa2.engine.filters import (
    ObstacleFilter,
    TerrainFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
    AdjacencyFilter,
    ImmunityFilter,
    SpawnPointFilter,
    AdjacentSpawnPointFilter,
    AdjacencyToContextFilter,
    ExcludeIdentityFilter,
    HasEmptyNeighborFilter,
    ForcedMovementByEnemyFilter,
    CanBePlacedByActorFilter,
    MovementPathFilter,
    LineBehindTargetFilter,
    NotInStraightLineFilter,
    FastTravelDestinationFilter,
    PreserveDistanceFilter,
)
from goa2.domain.models.enums import FilterType


def _filter_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("type", "")
    return v.type.value if hasattr(v.type, "value") else str(v.type)


AnyFilter = Annotated[
    Union[
        Annotated[ObstacleFilter, Tag(FilterType.OCCUPIED.value)],
        Annotated[TerrainFilter, Tag(FilterType.TERRAIN.value)],
        Annotated[RangeFilter, Tag(FilterType.RANGE.value)],
        Annotated[TeamFilter, Tag(FilterType.TEAM.value)],
        Annotated[UnitTypeFilter, Tag(FilterType.UNIT_TYPE.value)],
        Annotated[AdjacencyFilter, Tag(FilterType.ADJACENCY.value)],
        Annotated[ImmunityFilter, Tag(FilterType.IMMUNITY.value)],
        Annotated[SpawnPointFilter, Tag(FilterType.SPAWN_POINT.value)],
        Annotated[AdjacentSpawnPointFilter, Tag(FilterType.ADJACENT_SPAWN_POINT.value)],
        Annotated[AdjacencyToContextFilter, Tag(FilterType.ADJACENCY_TO_CONTEXT.value)],
        Annotated[ExcludeIdentityFilter, Tag(FilterType.EXCLUDE_IDENTITY.value)],
        Annotated[HasEmptyNeighborFilter, Tag(FilterType.HAS_EMPTY_NEIGHBOR.value)],
        Annotated[
            ForcedMovementByEnemyFilter, Tag(FilterType.FORCED_MOVEMENT_BY_ENEMY.value)
        ],
        Annotated[
            CanBePlacedByActorFilter, Tag(FilterType.CAN_BE_PLACED_BY_ACTOR.value)
        ],
        Annotated[MovementPathFilter, Tag(FilterType.MOVEMENT_PATH.value)],
        Annotated[LineBehindTargetFilter, Tag(FilterType.LINE_BEHIND_TARGET.value)],
        Annotated[NotInStraightLineFilter, Tag(FilterType.NOT_IN_STRAIGHT_LINE.value)],
        Annotated[
            FastTravelDestinationFilter, Tag(FilterType.FAST_TRAVEL_DESTINATION.value)
        ],
        Annotated[PreserveDistanceFilter, Tag(FilterType.PRESERVE_DISTANCE.value)],
    ],
    Discriminator(_filter_discriminator),
]


# ---------------------------------------------------------------------------
# Patch model_fields so Pydantic uses concrete union types for (de)serialization.
# We must patch model_fields (not just __annotations__) because Pydantic V2
# reads field info from model_fields, not __annotations__, during model_rebuild.
# ---------------------------------------------------------------------------
from goa2.domain.state import GameState

# Patch GameState.execution_stack
GameState.model_fields["execution_stack"].annotation = List[AnyStep]

# Patch step fields that contain List[GameStep] or List[FilterCondition]
SelectStep.model_fields["filters"].annotation = List[AnyFilter]
MultiSelectStep.model_fields["filters"].annotation = List[AnyFilter]
AttackSequenceStep.model_fields["target_filters"].annotation = List[AnyFilter]
MayRepeatNTimesStep.model_fields["steps_template"].annotation = List[AnyStep]
ForEachStep.model_fields["steps_template"].annotation = List[AnyStep]

# Rebuild all patched models (force=True since they were already built).
# Leaf models first, then models that reference them.
SelectStep.model_rebuild(force=True)
MultiSelectStep.model_rebuild(force=True)
AttackSequenceStep.model_rebuild(force=True)
MayRepeatNTimesStep.model_rebuild(force=True)
ForEachStep.model_rebuild(force=True)
GameState.model_rebuild(force=True)

"""
Sealing module: defines AnyStep discriminated union and patches model annotations.

Imported by handler.py to ensure patching happens before engine use.
Must be imported AFTER all step/filter subclasses are defined.
"""

from typing import Annotated, Any, Dict, List, Union

from pydantic import Discriminator, Tag

from goa2.engine.steps import (
    AdvanceTurnStep,
    AttackSequenceStep,
    AskConfirmationStep,
    CancelEffectsStep,
    ConfirmResolutionStep,
    ConvertCardToItemStep,
    CheckAdjacencyStep,
    CheckContextConditionStep,
    CheckHeroDefeatedThisRoundStep,
    ComputeHexStep,
    CheckLanePushStep,
    CheckMinionProtectionStep,
    CheckPassiveAbilitiesStep,
    CheckUnitTypeStep,
    ChooseMinionRemovalStep,
    CombineBooleanContextStep,
    CountAdjacentEnemiesStep,
    CountCardsStep,
    CountStep,
    CreateEffectStep,
    DefeatUnitStep,
    DiscardCardStep,
    EndPhaseCleanupStep,
    EndPhaseStep,
    FastTravelSequenceStep,
    FastTravelStep,
    FinalizeHeroTurnStep,
    FindNextActorStep,
    ForceDefenseCardMovementStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    ForEachStep,
    GainCoinsStep,
    GainItemStep,
    GuessCardColorStep,
    LanePushStep,
    LogMessageStep,
    MarkPassiveUsedStep,
    MayRepeatNTimesStep,
    MinionBattleStep,
    MinePathChoiceStep,
    MoveSequenceStep,
    MoveTokenStep,
    MoveUnitStep,
    MultiSelectStep,
    OfferPassiveStep,
    PlaceMarkerStep,
    PlaceTokenStep,
    PlaceUnitStep,
    PushUnitStep,
    ReactionWindowStep,
    RecordHexStep,
    RecordTargetStep,
    RemoveMarkerStep,
    RemoveTokenStep,
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
    RespawnMinionAtHexStep,
    RespawnMinionStep,
    RestoreActionTypeStep,
    RevealAndResolveGuessStep,
    RetrieveCardStep,
    ReturnMinionToZoneStep,
    RoundResetStep,
    SelectStep,
    SetActorStep,
    SetContextFlagStep,
    StealCoinsStep,
    SwapCardStep,
    SwapUnitsStep,
    TriggerGameOverStep,
    TriggerMineStep,
    ValidateRepeatStep,
    FinishedExpiringEffectStep,
    SpendAdditionalLifeCounterStep,
    PerformPrimaryActionStep,
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
        Annotated[AdvanceTurnStep, Tag(StepType.ADVANCE_TURN.value)],
        Annotated[AttackSequenceStep, Tag(StepType.ATTACK_SEQUENCE.value)],
        Annotated[AskConfirmationStep, Tag(StepType.ASK_CONFIRMATION.value)],
        Annotated[CancelEffectsStep, Tag(StepType.CANCEL_EFFECTS.value)],
        Annotated[ConfirmResolutionStep, Tag(StepType.CONFIRM_RESOLUTION.value)],
        Annotated[ConvertCardToItemStep, Tag(StepType.CONVERT_CARD_TO_ITEM.value)],
        Annotated[CheckAdjacencyStep, Tag(StepType.CHECK_ADJACENCY.value)],
        Annotated[
            CheckContextConditionStep, Tag(StepType.CHECK_CONTEXT_CONDITION.value)
        ],
        Annotated[
            CheckHeroDefeatedThisRoundStep,
            Tag(StepType.CHECK_HERO_DEFEATED_THIS_ROUND.value),
        ],
        Annotated[CheckLanePushStep, Tag(StepType.CHECK_LANE_PUSH.value)],
        Annotated[ComputeHexStep, Tag(StepType.COMPUTE_HEX.value)],
        Annotated[
            CheckMinionProtectionStep, Tag(StepType.CHECK_MINION_PROTECTION.value)
        ],
        Annotated[
            CheckPassiveAbilitiesStep, Tag(StepType.CHECK_PASSIVE_ABILITIES.value)
        ],
        Annotated[CheckUnitTypeStep, Tag(StepType.CHECK_UNIT_TYPE.value)],
        Annotated[ChooseMinionRemovalStep, Tag(StepType.CHOOSE_MINION_REMOVAL.value)],
        Annotated[
            CombineBooleanContextStep, Tag(StepType.COMBINE_BOOLEAN_CONTEXT.value)
        ],
        Annotated[CountAdjacentEnemiesStep, Tag(StepType.COUNT_ADJACENT_ENEMIES.value)],
        Annotated[CountCardsStep, Tag(StepType.COUNT_CARDS.value)],
        Annotated[CountStep, Tag(StepType.COUNT.value)],
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
            ForceDefenseCardMovementStep,
            Tag(StepType.FORCE_DEFENSE_CARD_MOVEMENT.value),
        ],
        Annotated[
            ForceDiscardOrDefeatStep, Tag(StepType.FORCE_DISCARD_OR_DEFEAT.value)
        ],
        Annotated[ForceDiscardStep, Tag(StepType.FORCE_DISCARD.value)],
        Annotated[ForEachStep, Tag(StepType.FOR_EACH.value)],
        Annotated[GainCoinsStep, Tag(StepType.GAIN_COINS.value)],
        Annotated[GainItemStep, Tag(StepType.GAIN_ITEM.value)],
        Annotated[GuessCardColorStep, Tag(StepType.GUESS_CARD_COLOR.value)],
        Annotated[LanePushStep, Tag(StepType.LANE_PUSH.value)],
        Annotated[LogMessageStep, Tag(StepType.LOG_MESSAGE.value)],
        Annotated[MarkPassiveUsedStep, Tag(StepType.MARK_PASSIVE_USED.value)],
        Annotated[MayRepeatNTimesStep, Tag(StepType.MAY_REPEAT_ONCE.value)],
        Annotated[MinionBattleStep, Tag(StepType.MINION_BATTLE.value)],
        Annotated[MinePathChoiceStep, Tag(StepType.MINE_PATH_CHOICE.value)],
        Annotated[MoveSequenceStep, Tag(StepType.MOVE_SEQUENCE.value)],
        Annotated[MoveTokenStep, Tag(StepType.MOVE_TOKEN.value)],
        Annotated[MoveUnitStep, Tag(StepType.MOVE_UNIT.value)],
        Annotated[MultiSelectStep, Tag(StepType.MULTI_SELECT.value)],
        Annotated[OfferPassiveStep, Tag(StepType.OFFER_PASSIVE.value)],
        Annotated[PlaceMarkerStep, Tag(StepType.PLACE_MARKER.value)],
        Annotated[PlaceTokenStep, Tag(StepType.PLACE_TOKEN.value)],
        Annotated[PlaceUnitStep, Tag(StepType.PLACE_UNIT.value)],
        Annotated[PushUnitStep, Tag(StepType.PUSH_UNIT.value)],
        Annotated[ReactionWindowStep, Tag(StepType.REACTION_WINDOW.value)],
        Annotated[RecordHexStep, Tag(StepType.RECORD_HEX.value)],
        Annotated[RecordTargetStep, Tag(StepType.RECORD_TARGET.value)],
        Annotated[RemoveMarkerStep, Tag(StepType.REMOVE_MARKER.value)],
        Annotated[RemoveTokenStep, Tag(StepType.REMOVE_TOKEN.value)],
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
        Annotated[RespawnMinionAtHexStep, Tag(StepType.RESPAWN_MINION_AT_HEX.value)],
        Annotated[RespawnMinionStep, Tag(StepType.RESPAWN_MINION.value)],
        Annotated[RestoreActionTypeStep, Tag(StepType.RESTORE_ACTION_TYPE.value)],
        Annotated[
            RevealAndResolveGuessStep, Tag(StepType.REVEAL_AND_RESOLVE_GUESS.value)
        ],
        Annotated[RetrieveCardStep, Tag(StepType.RETRIEVE_CARD.value)],
        Annotated[ReturnMinionToZoneStep, Tag(StepType.RETURN_MINION_TO_ZONE.value)],
        Annotated[RoundResetStep, Tag(StepType.ROUND_RESET.value)],
        Annotated[SelectStep, Tag(StepType.SELECT.value)],
        Annotated[SetActorStep, Tag(StepType.SET_ACTOR.value)],
        Annotated[SetContextFlagStep, Tag(StepType.SET_CONTEXT_FLAG.value)],
        Annotated[StealCoinsStep, Tag(StepType.STEAL_COINS.value)],
        Annotated[SwapCardStep, Tag(StepType.SWAP_CARD.value)],
        Annotated[SwapUnitsStep, Tag(StepType.SWAP_UNITS.value)],
        Annotated[TriggerGameOverStep, Tag(StepType.TRIGGER_GAME_OVER.value)],
        Annotated[TriggerMineStep, Tag(StepType.TRIGGER_MINE.value)],
        Annotated[ValidateRepeatStep, Tag(StepType.VALIDATE_REPEAT.value)],
        Annotated[
            FinishedExpiringEffectStep, Tag(StepType.FINISHED_EXPIRING_EFFECT.value)
        ],
        Annotated[
            SpendAdditionalLifeCounterStep,
            Tag(StepType.SPEND_ADDITIONAL_LIFE_COUNTER.value),
        ],
        Annotated[PerformPrimaryActionStep, Tag(StepType.PERFORM_PRIMARY_ACTION.value)],
    ],
    Discriminator(_step_discriminator),
]


# ---------------------------------------------------------------------------
# Same pattern for AnyFilter — override the field-based version in filters.py
# Imports are intentionally here (not at top) to avoid circular deps
# ruff: noqa: E402
from goa2.engine.filters import (
    MinionTypesFilter,
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
    InStraightLineFilter,
    SpaceBehindEmptyFilter,
    StraightLinePathFilter,
    FastTravelDestinationFilter,
    PreserveDistanceFilter,
    CardsInContainerFilter,
    PlayedCardFilter,
    BattleZoneFilter,
    SpawnPointTeamFilter,
    ClearLineOfSightFilter,
    HasMarkerFilter,
    UnitOnSpawnPointFilter,
    TokenTypeFilter,
    OrFilter,
    AndFilter,
)
from goa2.domain.models.enums import FilterType  # noqa: E402


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
        Annotated[InStraightLineFilter, Tag(FilterType.IN_STRAIGHT_LINE.value)],
        Annotated[SpaceBehindEmptyFilter, Tag(FilterType.SPACE_BEHIND_EMPTY.value)],
        Annotated[StraightLinePathFilter, Tag(FilterType.STRAIGHT_LINE_PATH.value)],
        Annotated[
            FastTravelDestinationFilter, Tag(FilterType.FAST_TRAVEL_DESTINATION.value)
        ],
        Annotated[PreserveDistanceFilter, Tag(FilterType.PRESERVE_DISTANCE.value)],
        Annotated[MinionTypesFilter, Tag(FilterType.MINION_TYPES.value)],
        Annotated[CardsInContainerFilter, Tag(FilterType.CARDS_IN_CONTAINER.value)],
        Annotated[PlayedCardFilter, Tag(FilterType.PLAYED_CARD.value)],
        Annotated[BattleZoneFilter, Tag(FilterType.BATTLE_ZONE.value)],
        Annotated[SpawnPointTeamFilter, Tag(FilterType.SPAWN_POINT_TEAM.value)],
        Annotated[ClearLineOfSightFilter, Tag(FilterType.CLEAR_LINE_OF_SIGHT.value)],
        Annotated[HasMarkerFilter, Tag(FilterType.HAS_MARKER.value)],
        Annotated[UnitOnSpawnPointFilter, Tag(FilterType.UNIT_ON_SPAWN_POINT.value)],
        Annotated[TokenTypeFilter, Tag(FilterType.TOKEN_TYPE.value)],
        Annotated[OrFilter, Tag(FilterType.OR_FILTER.value)],
        Annotated[AndFilter, Tag(FilterType.AND_FILTER.value)],
    ],
    Discriminator(_filter_discriminator),
]


# ---------------------------------------------------------------------------
# AnyMiscEntity — discriminated union for misc_entities (non-Unit BoardEntities).
# When adding a new BoardEntity type (e.g. Turret, Dragon), add it here with
# its own entity_kind Literal tag. Without this, persistence/rollback will break.
# ---------------------------------------------------------------------------
from goa2.domain.models.token import Token  # noqa: E402
from goa2.domain.models.base import Placeholder  # noqa: E402


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


# ---------------------------------------------------------------------------
# Patch model_fields so Pydantic uses concrete union types for (de)serialization.
# We must patch model_fields (not just __annotations__) because Pydantic V2
# reads field info from model_fields, not __annotations__, during model_rebuild.
# Imports are intentionally here (not at top) to avoid circular deps
# ruff: noqa: E402
from goa2.domain.state import GameState
from goa2.domain.models.effect import ActiveEffect

# Patch GameState.execution_stack and misc_entities
GameState.model_fields["execution_stack"].annotation = List[AnyStep]
GameState.model_fields["misc_entities"].annotation = Dict[str, AnyMiscEntity]

# Patch step fields that contain List[GameStep] or List[FilterCondition]
SelectStep.model_fields["filters"].annotation = List[AnyFilter]
MultiSelectStep.model_fields["filters"].annotation = List[AnyFilter]
AttackSequenceStep.model_fields["target_filters"].annotation = List[AnyFilter]
CountStep.model_fields["filters"].annotation = List[AnyFilter]
MayRepeatNTimesStep.model_fields["steps_template"].annotation = List[AnyStep]
ForEachStep.model_fields["steps_template"].annotation = List[AnyStep]
CreateEffectStep.model_fields["finishing_steps"].annotation = List[AnyStep]
ActiveEffect.model_fields["finishing_steps"].annotation = List[AnyStep]

# Patch StatAura.count_filters to use AnyFilter for serialization
from goa2.engine.effects import StatAura  # noqa: E402

StatAura.model_fields["count_filters"].annotation = List[AnyFilter]
RespawnMinionAtHexStep.model_fields["hex_filters"].annotation = List[AnyFilter]
OrFilter.model_fields["filters"].annotation = List[AnyFilter]
AndFilter.model_fields["filters"].annotation = List[AnyFilter]

# Rebuild all patched models (force=True since they were already built).
# Leaf models first, then models that reference them.
RespawnMinionAtHexStep.model_rebuild(force=True)
OrFilter.model_rebuild(force=True)
AndFilter.model_rebuild(force=True)
SelectStep.model_rebuild(force=True)
MultiSelectStep.model_rebuild(force=True)
AttackSequenceStep.model_rebuild(force=True)
CountStep.model_rebuild(force=True)
MayRepeatNTimesStep.model_rebuild(force=True)
ForEachStep.model_rebuild(force=True)
CreateEffectStep.model_rebuild(force=True)
ActiveEffect.model_rebuild(force=True)
StatAura.model_rebuild(force=True)
GameState.model_rebuild(force=True)

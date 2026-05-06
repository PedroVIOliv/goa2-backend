"""Step engine package — compatibility re-exports."""

from goa2.engine.steps.base import GameStep, StepResult  # noqa: F401

from goa2.engine.steps.markers import (  # noqa: F401
    _remove_token_from_board,
    RemoveTokenStep,
    PlaceTokenStep,
    MoveTokenStep,
    PlaceMarkerStep,
    RemoveMarkerStep,
)

from goa2.engine.steps.effects import (  # noqa: F401
    CreateEffectStep,
    FinishedExpiringEffectStep,
    CancelEffectsStep,
    CheckPassiveAbilitiesStep,
    OfferPassiveStep,
    MarkPassiveUsedStep,
)

from goa2.engine.steps.selection import (  # noqa: F401
    SelectStep,
    MultiSelectStep,
    ChooseMinionRemovalStep,
    AskConfirmationStep,
    ResolveTieBreakerStep,
    GuessCardColorStep,
    RevealAndResolveGuessStep,
)

from goa2.engine.steps.movement import (  # noqa: F401
    MoveUnitStep,
    MoveSequenceStep,
    FastTravelStep,
    FastTravelSequenceStep,
    MinePathChoiceStep,
    TriggerMineStep,
    ResolvePreActionMovementStep,
    PlaceUnitStep,
    SwapUnitsStep,
    PushUnitStep,
    ResolveDisplacementStep,
    ForceDefenseCardMovementStep,
)

from goa2.engine.steps.reactions import (  # noqa: F401
    ReactionWindowStep,
    ResolveDefenseTextStep,
    ResolveOnBlockEffectStep,
    ConfirmResolutionStep,
)

from goa2.engine.steps.combat import (  # noqa: F401
    AttackSequenceStep,
    ResolveCombatStep,
    RemoveUnitStep,
    DefeatUnitStep,
    CheckMinionProtectionStep,
    RespawnHeroStep,
    RespawnMinionStep,
    RespawnMinionAtHexStep,
    CheckLanePushStep,
    LanePushStep,
    MinionBattleStep,
    ReturnMinionToZoneStep,
    SpendAdditionalLifeCounterStep,
    TriggerGameOverStep,
)

from goa2.engine.steps.cards import (  # noqa: F401
    DiscardCardStep,
    ForceDiscardStep,
    ForceDiscardOrDefeatStep,
    ResolveCardTextStep,
    ResolveCardStep,
    SwapCardStep,
    RetrieveCardStep,
    CountCardsStep,
    GainCoinsStep,
    GainItemStep,
    StealCoinsStep,
    PerformPrimaryActionStep,
    ConvertCardToItemStep,
    ResolveUpgradesStep,
    RoundResetStep,
    apply_hero_upgrade,
)

from goa2.engine.steps.phases import (  # noqa: F401
    FindNextActorStep,
    FinalizeHeroTurnStep,
    EndPhaseCleanupStep,
    EndPhaseStep,
    AdvanceTurnStep,
    RestoreActionTypeStep,
)

from goa2.engine.steps.utility import (  # noqa: F401
    LogMessageStep,
    SetContextFlagStep,
    SetActorStep,
    RecordTargetStep,
    RecordHexStep,
    CheckDistanceStep,
    ComputeDistanceStep,
    MayRepeatNTimesStep,
    MayRepeatOnceStep,
    ValidateRepeatStep,
    CheckAdjacencyStep,
    CountAdjacentEnemiesStep,
    CheckUnitTypeStep,
    CombineBooleanContextStep,
    CountStep,
    CheckContextConditionStep,
    CheckHeroDefeatedThisRoundStep,
    ComputeHexStep,
    ForEachStep,
)

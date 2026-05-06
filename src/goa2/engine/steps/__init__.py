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

# Re-export non-step symbols that consumers import from this module
from goa2.domain.events import GameEvent, GameEventType  # noqa: F401
from goa2.domain.hex import Hex  # noqa: F401
from goa2.domain.input import (  # noqa: F401
    InputOption,
    InputRequest,
    InputRequestType,
    create_input_request,
)
from goa2.domain.models import (  # noqa: F401
    ActionType,
    Card,
    CardColor,
    CardContainerType,
    CardState,
    CardTier,
    FilterType,
    GamePhase,
    Hero,
    StepType,
    TargetType,
    TeamColor,
    Token,
    TokenType,
)
from goa2.domain.models.effect import (  # noqa: F401
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
)
from goa2.domain.models.enums import DisplacementType, StatType  # noqa: F401
from goa2.domain.models.marker import MarkerType  # noqa: F401
from goa2.domain.state import GameState  # noqa: F401
from goa2.engine.effect_manager import EffectManager  # noqa: F401
from goa2.engine.filters_base import FilterCondition  # noqa: F401
from goa2.engine.filters_hex import RangeFilter  # noqa: F401
from goa2.engine.filters_units import TokenTypeFilter, UnitTypeFilter  # noqa: F401
from goa2.engine.stats import get_computed_stat  # noqa: F401
from goa2.engine.topology import are_connected, get_topology_service  # noqa: F401

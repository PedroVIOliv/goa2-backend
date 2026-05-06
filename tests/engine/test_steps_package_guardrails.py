"""Guardrails for the steps package split.

These tests capture the public API surface of goa2.engine.steps and verify
that serialization works for all nested-step/filter fields. They must pass
before, during, and after the split.
"""

import inspect

from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.filters_hex import RangeFilter
from goa2.engine.handler import push_steps
from goa2.engine.steps import GameStep

EXPECTED_STEP_CLASSES = {
    "AdvanceTurnStep",
    "AskConfirmationStep",
    "AttackSequenceStep",
    "CancelEffectsStep",
    "CheckAdjacencyStep",
    "CheckContextConditionStep",
    "CheckDistanceStep",
    "CheckHeroDefeatedThisRoundStep",
    "CheckLanePushStep",
    "CheckMinionProtectionStep",
    "CheckPassiveAbilitiesStep",
    "CheckUnitTypeStep",
    "ChooseMinionRemovalStep",
    "CombineBooleanContextStep",
    "ComputeDistanceStep",
    "ComputeHexStep",
    "ConfirmResolutionStep",
    "ConvertCardToItemStep",
    "CountAdjacentEnemiesStep",
    "CountCardsStep",
    "CountStep",
    "CreateEffectStep",
    "DefeatUnitStep",
    "DiscardCardStep",
    "EndPhaseCleanupStep",
    "EndPhaseStep",
    "FastTravelSequenceStep",
    "FastTravelStep",
    "FinalizeHeroTurnStep",
    "FindNextActorStep",
    "FinishedExpiringEffectStep",
    "ForEachStep",
    "ForceDefenseCardMovementStep",
    "ForceDiscardOrDefeatStep",
    "ForceDiscardStep",
    "GainCoinsStep",
    "GainItemStep",
    "GuessCardColorStep",
    "LanePushStep",
    "LogMessageStep",
    "MarkPassiveUsedStep",
    "MayRepeatNTimesStep",
    "MayRepeatOnceStep",
    "MinePathChoiceStep",
    "MinionBattleStep",
    "MoveSequenceStep",
    "MoveTokenStep",
    "MoveUnitStep",
    "MultiSelectStep",
    "OfferPassiveStep",
    "PerformPrimaryActionStep",
    "PlaceMarkerStep",
    "PlaceTokenStep",
    "PlaceUnitStep",
    "PushUnitStep",
    "ReactionWindowStep",
    "RecordHexStep",
    "RecordTargetStep",
    "RemoveMarkerStep",
    "RemoveTokenStep",
    "RemoveUnitStep",
    "ResolveCardStep",
    "ResolveCardTextStep",
    "ResolveCombatStep",
    "ResolveDefenseTextStep",
    "ResolveDisplacementStep",
    "ResolveOnBlockEffectStep",
    "ResolvePreActionMovementStep",
    "ResolveTieBreakerStep",
    "ResolveUpgradesStep",
    "RespawnHeroStep",
    "RespawnMinionAtHexStep",
    "RespawnMinionStep",
    "RestoreActionTypeStep",
    "RetrieveCardStep",
    "ReturnMinionToZoneStep",
    "RevealAndResolveGuessStep",
    "RoundResetStep",
    "SelectStep",
    "SetActorStep",
    "SetContextFlagStep",
    "SpendAdditionalLifeCounterStep",
    "StealCoinsStep",
    "SwapCardStep",
    "SwapUnitsStep",
    "TriggerGameOverStep",
    "TriggerMineStep",
    "ValidateRepeatStep",
}


def _make_state() -> GameState:
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )


# ---------------------------------------------------------------------------
# Compatibility exports
# ---------------------------------------------------------------------------


def test_all_step_classes_importable_from_package_root():
    """Every known step class can be imported from goa2.engine.steps."""
    import goa2.engine.steps as steps_mod

    for name in EXPECTED_STEP_CLASSES:
        cls = getattr(steps_mod, name, None)
        assert cls is not None, f"{name} not importable from goa2.engine.steps"
        assert issubclass(cls, GameStep), f"{name} is not a GameStep subclass"


def test_key_non_step_exports():
    """Key non-step exports remain importable from goa2.engine.steps."""
    from goa2.engine.steps import GameStep, StepResult, apply_hero_upgrade

    assert StepResult is not None
    assert GameStep is not None
    assert callable(apply_hero_upgrade)


def test_no_unexpected_step_classes_missing():
    """All concrete GameStep subclasses in the module match our expected set."""
    import goa2.engine.steps as steps_mod

    actual = {
        name
        for name, cls in inspect.getmembers(steps_mod, inspect.isclass)
        if issubclass(cls, GameStep) and cls is not GameStep
    }
    missing = EXPECTED_STEP_CLASSES - actual
    extra = actual - EXPECTED_STEP_CLASSES
    assert not missing, f"Missing from module: {missing}"
    assert not extra, f"Unexpected in module (update EXPECTED_STEP_CLASSES): {extra}"


# ---------------------------------------------------------------------------
# Nested step/filter field round-trips
# ---------------------------------------------------------------------------


def test_round_trip_create_effect_step_with_finishing_steps():
    """CreateEffectStep.finishing_steps round-trips through serialization."""
    from goa2.engine.steps import CreateEffectStep, LogMessageStep

    state = _make_state()
    step = CreateEffectStep(
        effect_type=EffectType.PLACEMENT_PREVENTION,
        scope=EffectScope(shape=Shape.POINT, affects=AffectsFilter.SELF),
        duration=DurationType.THIS_TURN,
        finishing_steps=[LogMessageStep(message="effect ended")],
    )
    push_steps(state, [step])

    data = state.model_dump(mode="json")
    restored = GameState.model_validate(data)

    s = restored.execution_stack[0]
    assert type(s).__name__ == "CreateEffectStep"
    assert len(s.finishing_steps) == 1
    assert type(s.finishing_steps[0]).__name__ == "LogMessageStep"


def test_round_trip_respawn_minion_at_hex_with_filters():
    """RespawnMinionAtHexStep.hex_filters round-trips through serialization."""
    from goa2.engine.steps import RespawnMinionAtHexStep

    state = _make_state()
    step = RespawnMinionAtHexStep(
        team=TeamColor.RED,
        unit_key="minion_id",
        hex_filters=[RangeFilter(max_range=3)],
    )
    push_steps(state, [step])

    data = state.model_dump(mode="json")
    restored = GameState.model_validate(data)

    s = restored.execution_stack[0]
    assert type(s).__name__ == "RespawnMinionAtHexStep"
    assert len(s.hex_filters) == 1
    assert type(s.hex_filters[0]).__name__ == "RangeFilter"


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------


def test_import_smoke():
    """Basic import smoke test — catches package-level import cycles."""
    from goa2.engine.steps import AttackSequenceStep, MoveUnitStep, ResolveCardStep

    assert MoveUnitStep is not None
    assert AttackSequenceStep is not None
    assert ResolveCardStep is not None

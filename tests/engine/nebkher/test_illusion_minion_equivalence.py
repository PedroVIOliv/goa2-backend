"""ILLUSION_MINION_EQUIVALENCE (NebKher P4 — Illusionary Force/Army).

"This round: While you are performing actions, all Illusion tokens count as
both tokens and friendly melee minions."

Locked interpretations (2026-07-07):
- Active only during the effect SOURCE's own actions (gate on performer,
  not hardcoded NebKher — a copier binds it to themselves).
- During the source's attacks the minion defense modifier applies.
- During the source's defense it does NOT (that's the attacker's action).
- Minion / friendly / melee-minion filters must match Illusion tokens.
- SelectStep(target_type=UNIT) must OFFER Illusion tokens as candidates.
- Illusions still count as tokens too.
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    GamePhase,
    Hero,
    MinionType,
    Team,
    TeamColor,
    TokenType,
)
from goa2.domain.models.effect import ActiveEffect, DurationType, EffectScope, EffectType, Shape
from goa2.domain.models.enums import TargetType
from goa2.domain.models.token import Token
from goa2.domain.state import GameState
from goa2.domain.types import UnitID
from goa2.engine.filters import MinionTypesFilter, TeamFilter, UnitTypeFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.rules import illusion_minion_team
from goa2.engine.stats import calculate_minion_defense_modifier
from goa2.engine.steps import SelectStep

ILLUSION_HEX = Hex(q=1, r=0, s=-1)


def _state(*, equivalence_for: str | None, actor: str) -> GameState:
    """Arena with hero_source (RED), hero_other (RED), hero_enemy (BLUE),
    and one Illusion token owned by hero_source."""
    board = Board()
    hexes = {Hex(q=q, r=0, s=-q) for q in range(6)} | {Hex(q=1, r=1, s=-2), Hex(q=2, r=1, s=-3)}
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

    source = Hero(id="hero_source", name="Source", team=TeamColor.RED, deck=[], level=1)
    other = Hero(id="hero_other", name="Other", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="hero_enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[source, other], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.phase = GamePhase.RESOLUTION
    state.place_entity("hero_source", Hex(q=0, r=0, s=0))
    state.place_entity("hero_other", Hex(q=1, r=1, s=-2))
    state.place_entity("hero_enemy", Hex(q=2, r=0, s=-2))

    token = Token(id="illusion_1", name="Illusion", token_type=TokenType.ILLUSION)
    state.token_pool[TokenType.ILLUSION] = [token]
    state.register_entity(token)
    state.place_entity("illusion_1", ILLUSION_HEX)

    if equivalence_for:
        state.active_effects.append(
            ActiveEffect(
                id="fx_equiv",
                effect_type=EffectType.ILLUSION_MINION_EQUIVALENCE,
                source_id=equivalence_for,
                source_card_id="card_illusionary_army",
                scope=EffectScope(shape=Shape.GLOBAL, origin_id=equivalence_for),
                duration=DurationType.THIS_ROUND,
                is_active=True,
                created_at_turn=state.turn,
                created_at_round=state.round,
            )
        )
    state.current_actor_id = actor
    return state


# ---------------------------------------------------------------------------
# Helper gate
# ---------------------------------------------------------------------------


def test_helper_returns_source_team_when_source_acts() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_source")
    assert illusion_minion_team(state) == TeamColor.RED


def test_helper_inactive_for_other_actor() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_enemy")
    assert illusion_minion_team(state) is None


def test_helper_inactive_for_teammate_actor() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_other")
    assert illusion_minion_team(state) is None


def test_helper_inactive_without_effect() -> None:
    state = _state(equivalence_for=None, actor="hero_source")
    assert illusion_minion_team(state) is None


def test_helper_binds_to_performer_not_nebkher() -> None:
    """If another hero performed the card, equivalence follows THAT hero."""
    state = _state(equivalence_for="hero_other", actor="hero_other")
    assert illusion_minion_team(state) == TeamColor.RED


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_unit_type_minion_filter_matches_illusion_when_active() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_source")
    assert UnitTypeFilter(unit_type="MINION").apply("illusion_1", state, {}) is True


def test_unit_type_minion_filter_ignores_illusion_when_inactive() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_enemy")
    assert UnitTypeFilter(unit_type="MINION").apply("illusion_1", state, {}) is False


def test_unit_type_token_filter_still_matches_illusion() -> None:
    """Counts as BOTH token and minion."""
    state = _state(equivalence_for="hero_source", actor="hero_source")
    assert UnitTypeFilter(unit_type="TOKEN").apply("illusion_1", state, {}) is True


def test_team_filter_friendly_matches_illusion_when_active() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_source")
    assert TeamFilter(relation="FRIENDLY").apply("illusion_1", state, {}) is True


def test_team_filter_friendly_ignores_illusion_when_inactive() -> None:
    state = _state(equivalence_for=None, actor="hero_source")
    assert TeamFilter(relation="FRIENDLY").apply("illusion_1", state, {}) is False


def test_melee_minion_type_filter_matches_illusion_when_active() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_source")
    assert MinionTypesFilter(minion_types=[MinionType.MELEE]).apply("illusion_1", state, {}) is True


def test_ranged_minion_type_filter_does_not_match_illusion() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_source")
    assert (
        MinionTypesFilter(minion_types=[MinionType.RANGED]).apply("illusion_1", state, {}) is False
    )


# ---------------------------------------------------------------------------
# SelectStep(UNIT) enumeration
# ---------------------------------------------------------------------------


def _unit_select_options(state: GameState) -> list[str]:
    push_steps(
        state,
        [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="pick a friendly minion",
                output_key="picked",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="FRIENDLY"),
                ],
                skip_immunity_filter=True,
                is_mandatory=False,
            )
        ],
    )
    result = process_stack(state)
    if result.input_request is None:
        return []
    return [opt.id for opt in result.input_request.options]


def test_select_step_unit_offers_illusion_when_active() -> None:
    state = _state(equivalence_for="hero_source", actor="hero_source")
    assert "illusion_1" in _unit_select_options(state)


def test_select_step_unit_hides_illusion_when_inactive() -> None:
    state = _state(equivalence_for=None, actor="hero_source")
    assert "illusion_1" not in _unit_select_options(state)


# ---------------------------------------------------------------------------
# Minion defense modifier (stats.py)
# ---------------------------------------------------------------------------


def test_defense_modifier_counts_illusion_when_source_attacks() -> None:
    """Illusion adjacent to the enemy target = enemy-of-target minion → -1."""
    state = _state(equivalence_for="hero_source", actor="hero_source")
    # hero_enemy at (2,0,-2) is adjacent to illusion_1 at (1,0,-1).
    assert calculate_minion_defense_modifier(state, UnitID("hero_enemy")) == -1


def test_defense_modifier_ignores_illusion_for_other_attacker() -> None:
    """During someone else's action the equivalence is inactive."""
    state = _state(equivalence_for="hero_source", actor="hero_enemy")
    # hero_source at (0,0,0) is adjacent to illusion_1 — but no equivalence.
    assert calculate_minion_defense_modifier(state, UnitID("hero_source")) == 0

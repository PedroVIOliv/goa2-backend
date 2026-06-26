from __future__ import annotations

import pytest

import goa2.scripts.tali_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    MinionType,
    StatType,
    Token,
    TokenType,
)
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import PassiveTrigger, TargetType
from goa2.domain.state import GameState
from goa2.domain.types import UnitID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters_units import TokenTypeFilter, UnitTypeFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps import DefeatUnitStep, PerformPrimaryActionStep, SelectStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import EffectRun, run_card


def _arena(radius: int = 4) -> list[tuple[int, int, int]]:
    coords: list[tuple[int, int, int]] = []
    for q in range(-radius, radius + 1):
        for r in range(-radius, radius + 1):
            s = -q - r
            if abs(s) <= radius:
                coords.append((q, r, s))
    return coords


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if hasattr(option, "metadata") and option.metadata and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        elif hasattr(option, "id"):
            options.add(option.id)
        else:
            options.add(option)
    return options


def _option_ids(request) -> set[str]:
    assert request is not None
    return {getattr(option, "id", option) for option in request.options}


def _add_tali_token_pool(state: GameState) -> None:
    state.token_pool[TokenType.ICE] = []
    for i in range(3):
        token = Token(
            id=f"ice_{i + 1}",
            name="Ice",
            token_type=TokenType.ICE,
        )
        state.register_entity(token)
        state.token_pool[TokenType.ICE].append(token)

    state.token_pool[TokenType.TOTEM] = []
    token = Token(
        id="totem_1",
        name="Totem",
        token_type=TokenType.TOTEM,
    )
    state.register_entity(token)
    state.token_pool[TokenType.TOTEM].append(token)


def _filler_card(card_id: str, color: CardColor, *, defense: int = 1) -> Card:
    tier = CardTier.UNTIERED if color in (CardColor.GOLD, CardColor.SILVER) else CardTier.I
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=tier,
        color=color,
        initiative=1,
        primary_action=ActionType.ATTACK,
        primary_action_value=1,
        secondary_actions={ActionType.DEFENSE: defense},
        effect_id="filler",
        effect_text="",
        is_facedown=False,
    )


def _combat_events(run) -> list:
    return [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]


def _add_sacrifice_totem(
    state: GameState, *, owner_id: str, totem_hex: Hex, token_id: str = "enemy_totem"
) -> Token:
    """Place a Totem owned by ``owner_id`` with an adjacent sacrifice-protection effect."""
    totem = Token(id=token_id, name="Totem", token_type=TokenType.TOTEM)
    state.register_entity(totem)
    state.place_entity(token_id, totem_hex)
    EffectManager.create_effect(
        state=state,
        source_id=owner_id,
        effect_type=EffectType.MINION_PROTECTION,
        scope=EffectScope(
            shape=Shape.ADJACENT,
            origin_id=token_id,
            affects=AffectsFilter.FRIENDLY_UNITS,
        ),
        duration=DurationType.PASSIVE,
        is_active=True,
        sacrifice_origin_token=True,
    )
    return totem


@pytest.mark.effect_contract
@pytest.mark.parametrize(
    "effect_id",
    [
        "reign_of_winter",
        "venerated_totem",
        "pack_ice",
        "warrior_spirit",
        "blizzard",
        "spirit_bear",
        "winter_scepter",
        "ancestral_totem",
        "wall_of_frost",
        "guardian_spirit",
        "snowstorm",
        "spirit_wolf",
        "winter_spear",
        "glacial_barrier",
        "cold_snap",
        "winter_dagger",
        "commune_with_spirits",
        "ice_blast",
    ],
)
def test_tali_effects_are_registered(effect_id: str) -> None:
    assert CardEffectRegistry.get(effect_id) is not None


@pytest.mark.effect_flow
def test_pack_ice_places_three_obstacle_tokens_and_stacking_initiative_aura() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "pack_ice"))
        .blue_hero("enemy", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    _add_tali_token_pool(state)

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=-1, s=0))
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=-1, s=-1))
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=1, s=-2))
    run.finish()

    placed = [
        token for token in state.token_pool[TokenType.ICE] if token.id in state.entity_locations
    ]
    assert len(placed) == 3
    assert all(
        state.board.get_tile(state.entity_locations[token.id]).is_obstacle for token in placed
    )
    assert get_computed_stat(state, "enemy", StatType.INITIATIVE, 10) == 7


@pytest.mark.effect_flow
def test_venerated_totem_protects_any_friendly_minion_and_is_enemy_immune() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero(
            "hero_tali",
            at=(0, 0, 0),
            current_card=hero_card("Tali", "venerated_totem"),
        )
        .blue_hero("enemy", at=(3, 0, -3))
        .red_minion("red_ranged", at=(2, 0, -2), minion_type=MinionType.RANGED)
        .with_actor("hero_tali")
        .build()
    )
    _add_tali_token_pool(state)

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=0, s=-1))
    run.finish()

    totem = state.token_pool[TokenType.TOTEM][0]
    assert state.entity_locations[totem.id] == Hex(q=1, r=0, s=-1)
    assert totem.is_immune_to_enemy_actions is True

    state.current_actor_id = "enemy"
    state.execution_context["current_action_type"] = ActionType.CLEAR
    select = SelectStep(
        target_type=TargetType.UNIT_OR_TOKEN,
        prompt="Select tokens to clear",
        output_key="clear_target",
        filters=[
            UnitTypeFilter(unit_type="TOKEN"),
            TokenTypeFilter(token_type=TokenType.TOTEM),
        ],
    )
    push_steps(state, [select])
    result = process_stack(state)
    assert result.input_request is None

    enemy = state.get_hero("enemy")
    assert enemy is not None
    enemy.gold = 0
    push_steps(state, [DefeatUnitStep(victim_id="red_ranged", killer_id="enemy")])
    result = process_stack(state)
    assert result.input_request is None
    assert "red_ranged" in state.entity_locations
    assert totem.id not in state.entity_locations
    assert enemy.gold == 0
    assert any(e.event_type == GameEventType.MINION_PROTECTED for e in result.events)
    assert all(e.event_type != GameEventType.UNIT_DEFEATED for e in result.events)
    assert all(e.event_type != GameEventType.GOLD_GAINED for e in result.events)


def _clear_card() -> Card:
    """A basic card offering CLEAR as a secondary action (CLEAR can't be primary)."""
    return Card(
        id="clear_card",
        name="Clear Card",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=2,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=2,
        secondary_actions={ActionType.CLEAR: 0},
        is_ranged=False,
        effect_id="",
        effect_text="",
        is_facedown=False,
        state=CardState.UNRESOLVED,
    )


def _state_with_immune_totem(actor_id: str) -> tuple[GameState, Token]:
    """Tali (red) owns an enemy-immune Totem adjacent to the acting hero."""
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0))
        .red_hero("ally", at=(2, 0, -2), current_card=_clear_card())
        .blue_hero("enemy", at=(-2, 0, 2), current_card=_clear_card())
        .with_actor(actor_id)
        .build()
    )
    totem = Token(id="totem_1", name="Totem", token_type=TokenType.TOTEM)
    totem.owner_id = "hero_tali"
    totem.is_immune_to_enemy_actions = True
    state.register_entity(totem)
    state.token_pool[TokenType.TOTEM] = [totem]
    # Place the totem adjacent (range 1) to the acting hero so CLEAR can reach it.
    actor_hex = state.entity_locations[actor_id]
    offset = 1 if actor_id == "ally" else -1
    state.place_entity("totem_1", Hex(q=actor_hex.q + offset, r=0, s=-(actor_hex.q + offset)))
    return state, totem


@pytest.mark.effect_flow
def test_enemy_cannot_clear_talis_immune_totem() -> None:
    state, _totem = _state_with_immune_totem("enemy")

    run = run_card(state, "enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("CLEAR")
    # The immune totem is the only token in range; ImmunityFilter removes it,
    # so CLEAR finds no candidates and resolves without asking for a target.
    run.finish()

    assert "totem_1" in state.entity_locations
    assert all(e.event_type != GameEventType.TOKEN_REMOVED for e in run.events)


@pytest.mark.effect_flow
def test_ally_can_clear_talis_immune_totem() -> None:
    state, _totem = _state_with_immune_totem("ally")

    run = run_card(state, "ally")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("CLEAR")
    # A friendly hero is not "enemy", so immunity does not apply: the totem is
    # offered as a clearable target.
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert {o.id for o in run.latest_request.options} == {"totem_1"}
    run.choose("totem_1")
    run.finish()

    assert "totem_1" not in state.entity_locations
    assert any(e.event_type == GameEventType.TOKEN_REMOVED for e in run.events)


@pytest.mark.effect_flow
def test_enemy_cannot_clear_immune_totem_after_reload() -> None:
    # Regression: token_pool and misc_entities hold the same Token in a live
    # session, but a JSON reload splits them into two objects. Placement only
    # mutates the token_pool copy, so get_entity() (used by ImmunityFilter) must
    # not be left reading a stale, non-immune misc_entities copy.
    state, _totem = _state_with_immune_totem("enemy")

    reloaded = GameState.model_validate_json(state.model_dump_json())
    totem = reloaded.token_pool[TokenType.TOTEM][0]
    assert reloaded.get_entity(totem.id) is totem
    assert reloaded.get_entity(totem.id).is_immune_to_enemy_actions is True

    run = run_card(reloaded, "enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("CLEAR")
    run.finish()

    assert "totem_1" in reloaded.entity_locations
    assert all(e.event_type != GameEventType.TOKEN_REMOVED for e in run.events)


@pytest.mark.effect_flow
def test_ancestral_totem_only_protects_melee_minions() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero(
            "hero_tali",
            at=(0, 0, 0),
            current_card=hero_card("Tali", "ancestral_totem"),
        )
        .blue_hero("enemy", at=(3, 0, -3))
        .red_minion("red_ranged", at=(2, 0, -2), minion_type=MinionType.RANGED)
        .with_actor("hero_tali")
        .build()
    )
    _add_tali_token_pool(state)

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=0, s=-1))
    run.finish()

    push_steps(state, [DefeatUnitStep(victim_id="red_ranged", killer_id="enemy")])
    result = process_stack(state)
    assert result.input_request is None
    assert "red_ranged" not in state.entity_locations
    assert state.token_pool[TokenType.TOTEM][0].id in state.entity_locations


@pytest.mark.effect_flow
def test_cold_snap_moves_enemy_units_simultaneously_in_chosen_direction() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "cold_snap"))
        .blue_minion("front", at=(1, 0, -1))
        .blue_minion("back", at=(2, 0, -2))
        .with_actor("hero_tali")
        .build()
    )

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(0)
    run.finish()

    assert state.entity_locations["front"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations["back"] == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_snowstorm_does_not_move_immune_enemy_units() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "snowstorm"))
        .blue_minion("heavy", at=(1, 0, -1), minion_type=MinionType.HEAVY)
        .blue_minion("support", at=(2, 0, -2), minion_type=MinionType.MELEE)
        .with_actor("hero_tali")
        .build()
    )
    state.active_zone_id = "z1"

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(0)
    run.finish()

    assert state.entity_locations["heavy"] == Hex(q=1, r=0, s=-1)
    assert state.entity_locations["support"] == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_winter_dagger_bonus_does_not_apply_when_performed_from_discard() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "winter_dagger"))
        .blue_minion("target", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target")
    run.finish()
    assert _combat_events(run)[-1].metadata["attack_value"] == 5

    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0))
        .blue_minion("target", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    hero = state.get_hero("hero_tali")
    assert hero is not None
    discarded = hero_card("Tali", "winter_dagger")
    discarded.state = CardState.DISCARD
    hero.discard_pile.append(discarded)
    state.execution_context["perform_card"] = "winter_dagger"
    push_steps(state, [PerformPrimaryActionStep(card_key="perform_card", hero_id="hero_tali")])
    run = EffectRun(state=state, hero_id="hero_tali")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target")
    run.finish()
    assert _combat_events(run)[-1].metadata["attack_value"] == 2


@pytest.mark.effect_flow
def test_spirit_bear_can_choose_adjacent_first_then_optional_ranged_target() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "spirit_bear"))
        .blue_hero("adjacent_hero", at=(1, 0, -1))
        .blue_minion("ranged_minion", at=(2, 0, -2))
        .with_actor("hero_tali")
        .build()
    )

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER)
    assert _option_set(run) == {1, 2}
    run.choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("adjacent_hero")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_OPTION).confirm()
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"ranged_minion"}
    run.choose("ranged_minion").finish()


@pytest.mark.effect_flow
def test_guardian_spirit_from_discard_retrieves_other_hero_choice_and_itself() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0))
        .red_hero("ally", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    ally = state.get_hero("ally")
    assert tali is not None and ally is not None
    guardian = hero_card("Tali", "guardian_spirit")
    guardian.state = CardState.DISCARD
    tali.discard_pile.append(guardian)
    ally_discard = _filler_card("ally_red", CardColor.RED)
    ally_discard.state = CardState.DISCARD
    ally.discard_pile.append(ally_discard)

    state.execution_context["perform_card"] = "guardian_spirit"
    push_steps(state, [PerformPrimaryActionStep(card_key="perform_card", hero_id="hero_tali")])
    run = EffectRun(state=state, hero_id="hero_tali")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.finish()

    assert ally_discard in ally.hand
    assert guardian in tali.hand


@pytest.mark.effect_flow
def test_commune_discards_named_color_then_performs_that_newly_discarded_card() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero(
            "hero_tali",
            at=(0, 0, 0),
            current_card=hero_card("Tali", "commune_with_spirits"),
        )
        .red_hero("ally", at=(1, 0, -1))
        .blue_minion("target", at=(1, -1, 0))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    assert tali is not None
    red_card = hero_card("Tali", "winter_dagger")
    red_card.state = CardState.HAND
    tali.hand.append(red_card)

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("RED")
    run.expect_input(InputRequestType.SELECT_CARD).choose("winter_dagger")
    run.expect_input(InputRequestType.SELECT_CARD).choose("winter_dagger")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target")
    run.finish()

    assert _combat_events(run)[-1].metadata["attack_value"] == 2


@pytest.mark.effect_flow
def test_ice_blast_uses_defense_card_color_against_another_enemy_hero() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "ice_blast"))
        .blue_hero("defender", at=(1, 0, -1))
        .blue_hero("other_enemy", at=(2, 0, -2))
        .with_actor("hero_tali")
        .build()
    )
    defender = state.get_hero("defender")
    other = state.get_hero("other_enemy")
    assert defender is not None and other is not None
    defender.hand = [_filler_card("blue_defense", CardColor.BLUE, defense=5)]
    blue_card = _filler_card("other_blue", CardColor.BLUE)
    red_card = _filler_card("other_red", CardColor.RED)
    other.hand = [blue_card, red_card]

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("defender")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("blue_defense")
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"other_enemy"}
    run.choose("other_enemy")
    run.expect_input(InputRequestType.SELECT_CARD)
    assert _option_ids(run.latest_request) == {"other_blue"}
    run.choose("other_blue").finish()

    assert blue_card in other.discard_pile
    assert red_card in other.hand


@pytest.mark.effect_flow
def test_reign_of_winter_triggers_only_after_ice_blast_defeats_minion_by_combat() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "ice_blast"))
        .blue_minion("target_minion", at=(1, 0, -1))
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    enemy = state.get_hero("enemy")
    assert tali is not None and enemy is not None
    tali.level = 8
    tali.ultimate_card = hero_card("Tali", "reign_of_winter")
    tali.ultimate_card.state = CardState.PASSIVE
    enemy.hand = [_filler_card("enemy_green", CardColor.GREEN)]

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target_minion")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("GREEN")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_CARD).choose("enemy_green")
    run.finish()

    assert "target_minion" not in state.entity_locations
    assert enemy.hand == []


@pytest.mark.effect_flow
def test_reign_of_winter_does_not_fire_when_a_totem_saves_the_minion() -> None:
    # A totem-saved minion is NOT defeated — Reign must not force an enemy discard.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "ice_blast"))
        .blue_minion("target_minion", at=(1, 0, -1))
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    enemy = state.get_hero("enemy")
    assert tali is not None and enemy is not None
    tali.level = 8
    tali.ultimate_card = hero_card("Tali", "reign_of_winter")
    tali.ultimate_card.state = CardState.PASSIVE
    enemy.hand = [_filler_card("enemy_green", CardColor.GREEN)]
    # The blue minion is shielded by an adjacent blue Totem.
    _add_sacrifice_totem(state, owner_id="enemy", totem_hex=Hex(q=1, r=-1, s=0))

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target_minion")
    run.finish()  # no Reign color prompt — the minion was saved, not defeated

    assert "target_minion" in state.entity_locations  # minion survived
    assert "enemy_totem" not in state.entity_locations  # totem sacrificed
    assert len(enemy.hand) == 1  # Reign did not force a discard


@pytest.mark.effect_flow
def test_spirit_wolf_attacks_a_single_target_in_range_without_repeat() -> None:
    # Spirit Wolf uses can_choose_both=False: it resolves exactly one attack and
    # never offers the "resolve the other attack" repeat that Spirit Bear does.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", "spirit_wolf"))
        .blue_minion("target", at=(2, 0, -2))
        .with_actor("hero_tali")
        .build()
    )

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER)
    assert _option_set(run) == {1, 2}
    run.choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target")
    run.finish()  # no second SELECT_UNIT / repeat prompt

    assert _combat_events(run)[-1].metadata["attack_value"] == 3


@pytest.mark.effect_flow
def test_warrior_spirit_from_discard_retrieves_ally_card_and_optional_self_card() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0))
        .red_hero("ally", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    ally = state.get_hero("ally")
    assert tali is not None and ally is not None

    warrior = hero_card("Tali", "warrior_spirit")
    warrior.state = CardState.DISCARD
    tali.discard_pile.append(warrior)
    self_card = _filler_card("tali_self", CardColor.GREEN)
    self_card.state = CardState.DISCARD
    tali.discard_pile.append(self_card)
    ally_discard = _filler_card("ally_red", CardColor.RED)
    ally_discard.state = CardState.DISCARD
    ally.discard_pile.append(ally_discard)

    state.execution_context["perform_card"] = "warrior_spirit"
    push_steps(state, [PerformPrimaryActionStep(card_key="perform_card", hero_id="hero_tali")])
    run = EffectRun(state=state, hero_id="hero_tali")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    # Warrior Spirit additionally lets Tali retrieve one of her OWN discards.
    run.expect_input(InputRequestType.SELECT_CARD).choose("tali_self")
    run.finish()

    assert ally_discard in ally.hand
    assert self_card in tali.hand


@pytest.mark.effect_flow
def test_warrior_spirit_from_discard_can_skip_self_card_retrieval() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0))
        .red_hero("ally", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    ally = state.get_hero("ally")
    assert tali is not None and ally is not None

    warrior = hero_card("Tali", "warrior_spirit")
    warrior.state = CardState.DISCARD
    tali.discard_pile.append(warrior)
    ally_discard = _filler_card("ally_red", CardColor.RED)
    ally_discard.state = CardState.DISCARD
    ally.discard_pile.append(ally_discard)

    state.execution_context["perform_card"] = "warrior_spirit"
    push_steps(state, [PerformPrimaryActionStep(card_key="perform_card", hero_id="hero_tali")])
    run = EffectRun(state=state, hero_id="hero_tali")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_CARD).skip()  # decline self retrieval
    run.finish()

    assert ally_discard in ally.hand
    assert warrior in tali.discard_pile  # not retrieved


@pytest.mark.effect_flow
def test_blizzard_from_discard_defers_the_repeat_to_end_of_turn() -> None:
    # "End of turn: May repeat once" — the second shift must be a deferred
    # end-of-turn trigger, not run inline during Blizzard's own resolution.
    from goa2.engine.phases import end_turn

    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0))
        .blue_minion("mover", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    state.active_zone_id = "z1"
    tali = state.get_hero("hero_tali")
    assert tali is not None
    blizzard = hero_card("Tali", "blizzard")
    blizzard.state = CardState.DISCARD
    tali.discard_pile.append(blizzard)

    state.execution_context["perform_card"] = "blizzard"
    push_steps(state, [PerformPrimaryActionStep(card_key="perform_card", hero_id="hero_tali")])
    run = EffectRun(state=state, hero_id="hero_tali")
    # First (inline) shift only — no inline repeat prompt.
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(0)
    run.finish()

    # One shift happened; the repeat is parked as a THIS_TURN delayed trigger.
    first_pos = state.entity_locations["mover"]
    assert first_pos == Hex(q=2, r=0, s=-2)
    delayed = [
        e
        for e in state.active_effects
        if e.effect_type == EffectType.DELAYED_TRIGGER and e.duration == DurationType.THIS_TURN
    ]
    assert len(delayed) == 1
    assert delayed[0].finishing_steps

    # Intervening board change between the two shifts: the deferred repeat must
    # act on the CURRENT board state, not the position captured earlier.
    state.move_unit(UnitID("mover"), Hex(q=0, r=1, s=-1))

    # End of turn fires the deferred repeat (may-confirm, then direction).
    end_turn(state)
    run.expect_input(InputRequestType.SELECT_OPTION).confirm()
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(0)
    run.finish()

    # Second shift starts from the relocated hex, not (2,0,-2).
    assert state.entity_locations["mover"] == Hex(q=1, r=1, s=-2)


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "expected_count"),
    [("glacial_barrier", 1), ("wall_of_frost", 2)],
)
def test_ice_skills_place_expected_number_of_ice_tokens(card_id: str, expected_count: int) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", card_id))
        .with_actor("hero_tali")
        .build()
    )
    _add_tali_token_pool(state)

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    target_hexes = [Hex(q=1, r=-1, s=0), Hex(q=2, r=-1, s=-1)]
    for i in range(expected_count):
        run.expect_input(InputRequestType.SELECT_HEX).choose(target_hexes[i])
    run.finish()

    placed = [t for t in state.token_pool[TokenType.ICE] if t.id in state.entity_locations]
    assert len(placed) == expected_count
    assert all(state.board.get_tile(state.entity_locations[t.id]).is_obstacle for t in placed)


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "expected_value"),
    [("winter_spear", 6), ("winter_scepter", 7)],
)
def test_winter_weapons_add_three_to_adjacent_attack(card_id: str, expected_value: int) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", card_id))
        .blue_minion("target", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target")
    run.finish()

    assert _combat_events(run)[-1].metadata["attack_value"] == expected_value


@pytest.mark.effect_flow
@pytest.mark.parametrize("card_id", ["guardian_spirit", "warrior_spirit"])
def test_spirit_retrieve_from_hand_only_retrieves_an_ally_card(card_id: str) -> None:
    # Played normally (not from discard), both Spirit retrieval cards only
    # retrieve a friendly hero's discarded card — the self-retrieval extra is
    # exclusive to the discard version.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0), current_card=hero_card("Tali", card_id))
        .red_hero("ally", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    ally = state.get_hero("ally")
    assert tali is not None and ally is not None
    ally_discard = _filler_card("ally_red", CardColor.RED)
    ally_discard.state = CardState.DISCARD
    ally.discard_pile.append(ally_discard)

    run = run_card(state, "hero_tali")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.finish()  # no self-retrieval prompt when played from hand

    assert ally_discard in ally.hand


@pytest.mark.effect_flow
def test_reign_of_winter_passive_guards_reject_non_matching_contexts() -> None:
    effect = CardEffectRegistry.get("reign_of_winter")
    assert effect is not None
    state = (
        EffectScenarioBuilder()
        .with_hexes(_arena())
        .red_hero("hero_tali", at=(0, 0, 0))
        .blue_minion("target", at=(1, 0, -1))
        .with_actor("hero_tali")
        .build()
    )
    tali = state.get_hero("hero_tali")
    card = hero_card("Tali", "reign_of_winter")
    after = PassiveTrigger.AFTER_ATTACK
    base = {
        "attack_card_id": "ice_blast",
        "block_succeeded": False,
        "last_combat_target": "target",
    }

    # A minion that is still on the board was NOT defeated (e.g. saved by a
    # totem) — even with block_succeeded False, the passive must not fire.
    assert effect.should_offer_passive(state, tali, card, after, base) is False

    # Positive control: once the minion is genuinely defeated (off the board),
    # an unblocked Ice Blast offers the passive.
    state.remove_unit(UnitID("target"))
    assert effect.should_offer_passive(state, tali, card, after, base) is True

    # Each guard clause rejects independently.
    assert (
        effect.should_offer_passive(state, tali, card, PassiveTrigger.BEFORE_ATTACK, base) is False
    )
    assert (
        effect.should_offer_passive(
            state, tali, card, after, {**base, "attack_card_id": "winter_dagger"}
        )
        is False
    )
    assert (
        effect.should_offer_passive(state, tali, card, after, {**base, "block_succeeded": True})
        is False
    )
    assert (
        effect.should_offer_passive(state, tali, card, after, {**base, "last_combat_target": None})
        is False
    )

    # get_passive_steps only builds steps for AFTER_ATTACK.
    assert effect.get_passive_steps(state, tali, card, PassiveTrigger.BEFORE_ATTACK, base) == []

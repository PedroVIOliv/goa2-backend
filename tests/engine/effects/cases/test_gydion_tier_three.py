from __future__ import annotations

import pytest

import goa2.scripts.gydion_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.models import (
    CardState,
    Hero,
    Minion,
    MinionType,
    StatType,
    TeamColor,
    Token,
    TokenType,
)
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.domain.models.enums import DisplacementType
from goa2.engine.effect_manager import EffectManager
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    ForceDiscardStep,
    RestoreSpentLifeCounterStep,
)

from ..builders import EffectScenarioBuilder
from ..gydion_common import fresh_gydion, gydion_card, gydion_spell

TIER_THREE = {
    "sunburst",
    "energy_drain",
    "cloud_kill",
    "invulnerability",
    "power_word_kill",
    "polymorph",
}


def _state(spell_id: str, *, hexes=None):
    spell = gydion_spell(spell_id)
    spell.state = CardState.OUTSIDE_SPELLBOOK
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            hexes
            or [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (3, 0, -3),
                (4, 0, -4),
                (0, 1, -1),
                (1, 1, -2),
                (2, 1, -3),
            ]
        )
        .red_hero("hero_caster", at=(0, 0, 0), current_card=spell)
        .with_actor("hero_caster")
        .build()
    )
    caster = state.get_hero("hero_caster")
    caster.spells = [item.model_copy(deep=True) for item in fresh_gydion().spells]
    for owned_spell in caster.spells:
        owned_spell.state = CardState.SPELLBOOK
        owned_spell.is_facedown = True
    current = state.get_card_for_hero("hero_caster", spell_id)
    assert current is not None
    current.state = CardState.OUTSIDE_SPELLBOOK
    current.is_facedown = False
    return state, spell


def _effect_steps(state, spell):
    effect = CardEffectRegistry.get_for_card(spell)
    assert effect is not None
    return effect.get_steps(state, state.get_hero("hero_caster"), spell)


def _add_hero(state, hero_id: str, team: TeamColor, at: tuple[int, int, int]) -> Hero:
    hero = Hero(id=hero_id, name=hero_id, team=team, deck=[])
    state.teams[team].heroes.append(hero)
    q, r, s = at
    state.place_entity(hero_id, Hex(q=q, r=r, s=s))
    return hero


def _add_minion(
    state,
    minion_id: str,
    team: TeamColor,
    at: tuple[int, int, int],
    minion_type: MinionType = MinionType.MELEE,
) -> Minion:
    minion = Minion(id=minion_id, name=minion_id, team=team, type=minion_type)
    state.teams[team].minions.append(minion)
    q, r, s = at
    state.place_entity(minion_id, Hex(q=q, r=r, s=s))
    return minion


def _add_token(
    state,
    token_id: str,
    at: tuple[int, int, int],
    *,
    owner_id: str | None = None,
    immune: bool = False,
) -> Token:
    token = Token(id=token_id, name=token_id, token_type=TokenType.ROCK)
    token.owner_id = owner_id
    token.is_immune_to_enemy_actions = immune
    state.register_entity(token, "token")
    state.token_pool.setdefault(TokenType.ROCK, []).append(token)
    q, r, s = at
    state.place_entity(token_id, Hex(q=q, r=r, s=s))
    return token


@pytest.mark.effect_contract
def test_all_tier_three_spell_effects_are_registered() -> None:
    assert all(CardEffectRegistry.get_for_card(gydion_spell(spell_id)) for spell_id in TIER_THREE)


@pytest.mark.effect_contract
def test_sunburst_adds_other_outside_spells_to_attack_and_exact_range() -> None:
    state, spell = _state("sunburst")
    caster = state.get_hero("hero_caster")
    caster.items[StatType.ATTACK] = 1
    caster.items[StatType.RANGE] = 1
    others = [item for item in caster.spells if item.id != "sunburst"][:2]
    for item in others:
        item.state = CardState.OUTSIDE_SPELLBOOK
        item.is_facedown = False

    steps = _effect_steps(state, spell)

    assert len(steps) == 1 and isinstance(steps[0], AttackSequenceStep)
    assert steps[0].damage == 3
    assert steps[0].range_val == 3
    exact_filter = next(
        item for item in steps[0].target_filters if getattr(item, "min_range", None) == 3
    )
    assert exact_filter.max_range == 3


@pytest.mark.effect_flow
def test_sunburst_offers_only_target_at_computed_maximum_range() -> None:
    state, spell = _state("sunburst")
    caster = state.get_hero("hero_caster")
    for item in [owned for owned in caster.spells if owned.id != "sunburst"][:2]:
        item.state = CardState.OUTSIDE_SPELLBOOK
    _add_hero(state, "enemy_close", TeamColor.BLUE, (1, 0, -1))
    _add_hero(state, "enemy_exact", TeamColor.BLUE, (2, 0, -2))
    _add_hero(state, "enemy_far", TeamColor.BLUE, (3, 0, -3))

    push_steps(state, _effect_steps(state, spell))
    result = process_stack(state)

    assert result.input_request is not None
    assert {option.id for option in result.input_request.options} == {"enemy_exact"}


@pytest.mark.effect_flow
def test_sunburst_at_zero_range_fails_without_targeting_self() -> None:
    state, spell = _state("sunburst")
    push_steps(state, _effect_steps(state, spell))

    result = process_stack(state)

    assert result.input_request is None


@pytest.mark.effect_flow
def test_energy_drain_discards_non_basic_then_restores_life() -> None:
    state, spell = _state("energy_drain")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    basic = gydion_card("cantrip")
    non_basic = gydion_card("greater_evocation")
    basic.state = non_basic.state = CardState.HAND
    enemy.hand = [basic, non_basic]
    team = state.teams[TeamColor.RED]
    team.starting_life_counters = 5
    team.life_counters = 3
    steps = _effect_steps(state, spell)
    assert isinstance(steps[1], ForceDiscardStep)
    assert isinstance(steps[-1], RestoreSpentLifeCounterStep)
    push_steps(state, steps)

    target = process_stack(state)
    assert target.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": enemy.id}
    discard = process_stack(state)
    assert discard.input_request is not None
    assert discard.input_request.player_id == enemy.id
    assert {option.id for option in discard.input_request.options} == {non_basic.id}
    state.execution_stack[-1].pending_input = {"selection": non_basic.id}
    result = process_stack(state)

    assert [card.id for card in enemy.hand] == [basic.id]
    assert team.life_counters == 4
    assert any(event.event_type == GameEventType.LIFE_COUNTER_CHANGED for event in result.events)


@pytest.mark.effect_flow
def test_energy_drain_restores_life_when_target_has_no_non_basic_card() -> None:
    state, spell = _state("energy_drain")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    basic = gydion_card("cantrip")
    basic.state = CardState.HAND
    enemy.hand = [basic]
    team = state.teams[TeamColor.RED]
    team.starting_life_counters = 5
    team.life_counters = 3
    push_steps(state, _effect_steps(state, spell))
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": enemy.id}

    result = process_stack(state)

    assert result.input_request is None
    assert [card.id for card in enemy.hand] == [basic.id]
    assert team.life_counters == 4


@pytest.mark.effect_flow
def test_energy_drain_still_discards_when_life_supply_is_already_full() -> None:
    state, spell = _state("energy_drain")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    non_basic = gydion_card("greater_evocation")
    non_basic.state = CardState.HAND
    enemy.hand = [non_basic]
    team = state.teams[TeamColor.RED]
    team.starting_life_counters = 5
    team.life_counters = 5
    push_steps(state, _effect_steps(state, spell))
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": enemy.id}
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": non_basic.id}

    result = process_stack(state)

    assert enemy.hand == []
    assert [card.id for card in enemy.discard_pile] == [non_basic.id]
    assert team.life_counters == 5
    assert not any(
        event.event_type == GameEventType.LIFE_COUNTER_CHANGED for event in result.events
    )


@pytest.mark.effect_flow
def test_energy_drain_without_enemy_in_range_aborts_before_life_restore() -> None:
    state, spell = _state("energy_drain")
    team = state.teams[TeamColor.RED]
    team.starting_life_counters = 5
    team.life_counters = 3
    push_steps(state, _effect_steps(state, spell))

    result = process_stack(state)

    assert result.input_request is None
    assert team.life_counters == 3


@pytest.mark.effect_flow
def test_cloud_kill_forces_only_basic_discard_and_noops_without_match() -> None:
    state, spell = _state("cloud_kill")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    basic = gydion_card("cantrip")
    non_basic = gydion_card("greater_evocation")
    basic.state = non_basic.state = CardState.HAND
    enemy.hand = [basic, non_basic]
    push_steps(state, _effect_steps(state, spell))
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": enemy.id}

    discard = process_stack(state)

    assert discard.input_request is not None
    assert {option.id for option in discard.input_request.options} == {basic.id}

    state2, spell2 = _state("cloud_kill")
    enemy2 = _add_hero(state2, "enemy", TeamColor.BLUE, (2, 0, -2))
    only_non_basic = gydion_card("greater_evocation")
    only_non_basic.state = CardState.HAND
    enemy2.hand = [only_non_basic]
    push_steps(state2, _effect_steps(state2, spell2))
    process_stack(state2)
    state2.execution_stack[-1].pending_input = {"selection": enemy2.id}
    result = process_stack(state2)
    assert result.input_request is None
    assert [card.id for card in enemy2.hand] == [only_non_basic.id]


@pytest.mark.effect_contract
def test_invulnerability_creates_non_basic_only_immunity_for_caster() -> None:
    state, spell = _state("invulnerability")
    steps = _effect_steps(state, spell)
    assert len(steps) == 1 and isinstance(steps[0], CreateEffectStep)
    assert steps[0].non_basic_attacks_only is True
    push_steps(state, steps)
    process_stack(state)
    effect = state.active_effects[0]
    assert effect.source_id == "hero_caster"
    assert effect.non_basic_attacks_only is True


@pytest.mark.effect_flow
def test_copied_invulnerability_protects_the_actual_caster() -> None:
    state, spell = _state("invulnerability")
    copier = _add_hero(state, "hero_copier", TeamColor.RED, (1, 0, -1))
    state.current_actor_id = copier.id
    effect = CardEffectRegistry.get_for_card(spell)
    assert effect is not None
    push_steps(state, effect.get_steps(state, copier, spell))

    process_stack(state)

    assert len(state.active_effects) == 1
    assert state.active_effects[0].source_id == copier.id
    assert state.active_effects[0].source_card_id == spell.id


@pytest.mark.effect_flow
def test_invulnerability_does_not_duplicate_its_round_effect() -> None:
    state, spell = _state("invulnerability")
    push_steps(state, _effect_steps(state, spell))
    process_stack(state)

    assert _effect_steps(state, spell) == []
    assert len(state.active_effects) == 1


@pytest.mark.effect_flow
def test_power_word_kill_only_offers_enemy_hero_with_empty_hand() -> None:
    state, spell = _state("power_word_kill")
    empty = _add_hero(state, "enemy_empty", TeamColor.BLUE, (2, 0, -2))
    holding = _add_hero(state, "enemy_holding", TeamColor.BLUE, (2, 1, -3))
    card = gydion_card("cantrip")
    card.state = CardState.HAND
    holding.hand = [card]
    push_steps(state, _effect_steps(state, spell))

    request = process_stack(state)

    assert request.input_request is not None
    assert {option.id for option in request.input_request.options} == {empty.id}
    state.execution_stack[-1].pending_input = {"selection": empty.id}
    result = process_stack(state)
    assert state.get_position(empty.id) is None
    assert any(event.event_type == GameEventType.UNIT_DEFEATED for event in result.events)


@pytest.mark.effect_flow
def test_power_word_kill_aborts_when_no_enemy_in_radius_has_an_empty_hand() -> None:
    state, spell = _state("power_word_kill")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    card = gydion_card("cantrip")
    card.state = CardState.HAND
    enemy.hand = [card]
    push_steps(state, _effect_steps(state, spell))

    result = process_stack(state)

    assert result.input_request is None
    assert state.get_position(enemy.id) == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_polymorph_swaps_enemy_hero_with_friendly_token() -> None:
    state, spell = _state("polymorph")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    token = _add_token(state, "friendly_token", (3, 0, -3), owner_id="hero_caster")
    push_steps(state, _effect_steps(state, spell))
    first = process_stack(state)
    assert first.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": enemy.id}
    second = process_stack(state)
    assert second.input_request is not None
    assert token.id in {option.id for option in second.input_request.options}
    state.execution_stack[-1].pending_input = {"selection": token.id}

    result = process_stack(state)

    assert state.get_position(enemy.id) == Hex(q=3, r=0, s=-3)
    assert state.get_position(token.id) == Hex(q=2, r=0, s=-2)
    assert any(event.event_type == GameEventType.UNITS_SWAPPED for event in result.events)


@pytest.mark.effect_flow
def test_polymorph_second_target_is_token_or_enemy_minion_in_radius_with_immunity() -> None:
    state, spell = _state("polymorph")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    enemy_minion = _add_minion(state, "enemy_minion", TeamColor.BLUE, (2, 1, -3))
    friendly_minion = _add_minion(state, "friendly_minion", TeamColor.RED, (1, 1, -2))
    friendly_immune = _add_token(
        state,
        "friendly_immune",
        (1, 0, -1),
        owner_id="hero_caster",
        immune=True,
    )
    enemy_owner = _add_hero(state, "enemy_owner", TeamColor.BLUE, (4, 0, -4))
    enemy_immune = _add_token(
        state,
        "enemy_immune",
        (0, 1, -1),
        owner_id=enemy_owner.id,
        immune=True,
    )
    push_steps(state, _effect_steps(state, spell))
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": enemy.id}

    request = process_stack(state)

    assert request.input_request is not None
    option_ids = {option.id for option in request.input_request.options}
    assert enemy_minion.id in option_ids
    assert friendly_immune.id in option_ids
    assert friendly_minion.id not in option_ids
    assert enemy_immune.id not in option_ids


@pytest.mark.effect_flow
def test_polymorph_aborts_when_there_is_no_legal_second_target() -> None:
    state, spell = _state("polymorph")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    push_steps(state, _effect_steps(state, spell))
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": enemy.id}

    result = process_stack(state)

    assert result.input_request is None
    assert state.get_position(enemy.id) == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_polymorph_respects_swap_prevention() -> None:
    state, spell = _state("polymorph")
    enemy = _add_hero(state, "enemy", TeamColor.BLUE, (2, 0, -2))
    token = _add_token(state, "token", (3, 0, -3), owner_id="hero_caster")
    EffectManager.create_effect(
        state=state,
        source_id="enemy",
        effect_type=EffectType.PLACEMENT_PREVENTION,
        scope=EffectScope(shape=Shape.POINT, origin_id=enemy.id),
        duration=DurationType.THIS_ROUND,
        displacement_blocks=[DisplacementType.SWAP],
        blocks_enemy_actors=True,
        is_active=True,
    )
    push_steps(state, _effect_steps(state, spell))
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": enemy.id}
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": token.id}

    result = process_stack(state)

    assert result.input_request is None
    assert state.get_position(enemy.id) == Hex(q=2, r=0, s=-2)
    assert state.get_position(token.id) == Hex(q=3, r=0, s=-3)
    assert not any(event.event_type == GameEventType.UNITS_SWAPPED for event in result.events)

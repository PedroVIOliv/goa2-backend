from __future__ import annotations

import pytest

import goa2.scripts.gydion_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    CardState,
    Minion,
    MinionType,
    SpawnType,
    StatType,
    TeamColor,
    Token,
    TokenType,
)
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import (
    AttackSequenceStep,
    GainCoinsStep,
    PlaceTokenStep,
    PlaceUnitStep,
    RemovePreparedSpellsStep,
    RespawnMinionAtHexStep,
    RetrieveCardStep,
    SelectStep,
)

from ..builders import EffectScenarioBuilder
from ..gydion_common import fresh_gydion, gydion_card, gydion_spell

TIER_TWO = {
    "vampiric_touch",
    "fireball",
    "create_undead",
    "midas_touch",
    "disintegrate",
    "dominate_person",
    "find_familiar",
    "dimension_door",
    "banishment",
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


def _add_token(state, token_id: str, token_type: TokenType, at, *, owner_id=None, immune=False):
    token = Token(id=token_id, name=token_id, token_type=token_type)
    token.owner_id = owner_id
    token.is_immune_to_enemy_actions = immune
    state.register_entity(token, "token")
    state.token_pool.setdefault(token_type, []).append(token)
    q, r, s = at
    state.place_entity(token_id, Hex(q=q, r=r, s=s))
    return token


@pytest.mark.effect_contract
def test_all_tier_two_spell_effects_are_registered() -> None:
    assert all(CardEffectRegistry.get_for_card(gydion_spell(spell_id)) for spell_id in TIER_TWO)


@pytest.mark.effect_contract
def test_vampiric_touch_orders_attack_before_optional_retrieval() -> None:
    state, spell = _state("vampiric_touch")
    state.get_hero("hero_caster").items[StatType.ATTACK] = 2

    steps = _effect_steps(state, spell)

    assert [type(step) for step in steps] == [
        AttackSequenceStep,
        SelectStep,
        RetrieveCardStep,
    ]
    attack, selection, retrieve = steps
    assert attack.damage == 7 and attack.range_val == 1
    assert selection.is_mandatory is False
    assert selection.card_container.value == "DISCARD"
    assert retrieve.card_key == selection.output_key


@pytest.mark.effect_flow
def test_vampiric_touch_cannot_retrieve_when_mandatory_attack_has_no_target() -> None:
    state, spell = _state("vampiric_touch")
    discarded = gydion_card("cantrip")
    discarded.state = CardState.DISCARD
    state.get_hero("hero_caster").discard_pile = [discarded]

    push_steps(state, _effect_steps(state, spell))
    result = process_stack(state)

    assert result.input_request is None
    assert [card.id for card in state.get_hero("hero_caster").discard_pile] == ["cantrip"]


@pytest.mark.effect_flow
def test_fireball_excludes_adjacent_targets_and_targets_adjacent_to_friendly_units() -> None:
    state, spell = _state("fireball")
    builder_enemy = fresh_gydion().model_copy(deep=True)
    builder_enemy.id = "enemy_adjacent"
    builder_enemy.team = TeamColor.BLUE
    legal = builder_enemy.model_copy(deep=True, update={"id": "enemy_legal"})
    screened = builder_enemy.model_copy(deep=True, update={"id": "enemy_screened"})
    state.teams[TeamColor.BLUE].heroes.extend([builder_enemy, legal, screened])
    state.place_entity("enemy_adjacent", Hex(q=1, r=0, s=-1))
    state.place_entity("enemy_legal", Hex(q=3, r=0, s=-3))
    state.place_entity("enemy_screened", Hex(q=2, r=1, s=-3))
    ally = fresh_gydion().model_copy(deep=True)
    ally.id = "ally"
    ally.team = TeamColor.RED
    state.teams[TeamColor.RED].heroes.append(ally)
    state.place_entity("ally", Hex(q=1, r=1, s=-2))

    push_steps(state, _effect_steps(state, spell))
    request = process_stack(state)

    assert request.input_request is not None
    assert request.input_request.request_type == InputRequestType.SELECT_UNIT
    assert {option.id for option in request.input_request.options} == {"enemy_legal"}
    assert state.execution_context["attack_is_ranged"] is True


@pytest.mark.effect_flow
def test_create_undead_uses_lane_bound_friendly_spawn_in_battle_zone() -> None:
    spell = gydion_spell("create_undead")
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .spawn_point(
            (2, 0, -2),
            team=TeamColor.RED,
            spawn_type=SpawnType.MINION,
            minion_type=MinionType.MELEE,
        )
        .red_hero("hero_caster", at=(0, 0, 0), current_card=spell)
        .with_actor("hero_caster")
        .build()
    )
    caster = state.get_hero("hero_caster")
    caster.spells = [item.model_copy(deep=True) for item in fresh_gydion().spells]
    limbo = Minion(
        id="red_limbo",
        name="Limbo",
        team=TeamColor.RED,
        type=MinionType.MELEE,
        lane_id="lane_1",
    )
    state.teams[TeamColor.RED].minions.append(limbo)
    state.board.lanes = {"lane_1": ["z1"]}
    state.board.zones["z1"].spawn_points = [state.board.get_tile(Hex(q=2, r=0, s=-2)).spawn_point]
    state.battle_zones = {"lane_1": "z1"}

    steps = _effect_steps(state, spell)
    assert len(steps) == 1 and isinstance(steps[0], RespawnMinionAtHexStep)
    push_steps(state, steps)
    request = process_stack(state)
    assert request.input_request is not None
    assert request.input_request.request_type == InputRequestType.SELECT_HEX
    assert {option.metadata["raw"] for option in request.input_request.options} == {
        Hex(q=2, r=0, s=-2)
    }
    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": 0, "s": -2}}
    result = process_stack(state)
    assert result.input_request is None
    assert state.get_position("red_limbo") == Hex(q=2, r=0, s=-2)
    assert any(event.event_type == GameEventType.UNIT_PLACED for event in result.events)


@pytest.mark.parametrize(
    ("other_spells", "coins"), [(0, 0), (1, 0), (2, 1), (3, 1), (4, 2), (5, 2)]
)
def test_midas_touch_gains_one_coin_per_complete_pair(other_spells: int, coins: int) -> None:
    state, spell = _state("midas_touch")
    owner = state.get_hero("hero_caster")
    candidates = [item for item in owner.spells if item.id != "midas_touch"]
    for item in candidates[:other_spells]:
        item.state = CardState.OUTSIDE_SPELLBOOK
        item.is_facedown = False

    steps = _effect_steps(state, spell)
    if steps:
        assert any(isinstance(step, GainCoinsStep) for step in steps)
        push_steps(state, steps)
        result = process_stack(state)
        assert result.input_request is None
    assert owner.gold == coins


@pytest.mark.effect_flow
def test_disintegrate_removes_token_as_token_and_minion_without_defeat_rewards() -> None:
    state, spell = _state("disintegrate")
    token = _add_token(state, "rock_1", TokenType.ROCK, (1, 0, -1))
    push_steps(state, _effect_steps(state, spell))
    request = process_stack(state)
    assert request.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": token.id}
    removed = process_stack(state)
    assert token.id not in state.entity_locations
    assert any(event.event_type == GameEventType.TOKEN_REMOVED for event in removed.events)
    assert all(event.event_type != GameEventType.UNIT_REMOVED for event in removed.events)

    state2, spell2 = _state("disintegrate")
    minion = Minion(id="enemy_minion", name="Enemy", team=TeamColor.BLUE, type=MinionType.MELEE)
    state2.teams[TeamColor.BLUE].minions.append(minion)
    state2.place_entity(minion.id, Hex(q=1, r=0, s=-1))
    push_steps(state2, _effect_steps(state2, spell2))
    process_stack(state2)
    state2.execution_stack[-1].pending_input = {"selection": minion.id}
    removed2 = process_stack(state2)
    assert minion.id not in state2.entity_locations
    assert state2.get_hero("hero_caster").gold == 0
    assert any(event.event_type == GameEventType.UNIT_REMOVED for event in removed2.events)
    assert all(event.event_type != GameEventType.UNIT_DEFEATED for event in removed2.events)


@pytest.mark.effect_flow
def test_disintegrate_excludes_friendly_minions_and_enemy_heavy_minions() -> None:
    state, spell = _state("disintegrate")
    friendly = Minion(
        id="friendly_minion",
        name="Friendly",
        team=TeamColor.RED,
        type=MinionType.MELEE,
    )
    heavy = Minion(
        id="enemy_heavy",
        name="Heavy",
        team=TeamColor.BLUE,
        type=MinionType.HEAVY,
    )
    state.teams[TeamColor.RED].minions.append(friendly)
    state.teams[TeamColor.BLUE].minions.append(heavy)
    state.place_entity(friendly.id, Hex(q=1, r=0, s=-1))
    state.place_entity(heavy.id, Hex(q=0, r=1, s=-1))

    push_steps(state, _effect_steps(state, spell))
    result = process_stack(state)

    assert result.input_request is None
    assert state.get_position(friendly.id) is not None
    assert state.get_position(heavy.id) is not None


@pytest.mark.parametrize(
    ("tali_team", "eligible"), [(TeamColor.BLUE, False), (TeamColor.RED, True)]
)
def test_disintegrate_respects_venerated_totem_enemy_action_immunity(
    tali_team: TeamColor, eligible: bool
) -> None:
    state, spell = _state("disintegrate")
    tali = fresh_gydion().model_copy(deep=True)
    tali.id = "hero_tali"
    tali.team = tali_team
    state.teams[tali_team].heroes.append(tali)
    token = _add_token(
        state,
        "totem_1",
        TokenType.TOTEM,
        (1, 0, -1),
        owner_id=tali.id,
        immune=True,
    )
    push_steps(state, [_effect_steps(state, spell)[0]])

    result = process_stack(state)

    assert (result.input_request is not None) is eligible
    if eligible:
        assert {option.id for option in result.input_request.options} == {token.id}
    else:
        assert token.id in state.entity_locations


@pytest.mark.effect_flow
def test_dominate_person_defeats_minion_in_radius_adjacent_to_selected_hero() -> None:
    state, spell = _state("dominate_person")
    enemy = fresh_gydion().model_copy(deep=True)
    enemy.id = "enemy_hero"
    enemy.team = TeamColor.BLUE
    state.teams[TeamColor.BLUE].heroes.append(enemy)
    state.place_entity(enemy.id, Hex(q=2, r=0, s=-2))
    victim = Minion(id="enemy_minion", name="Victim", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(victim)
    state.place_entity(victim.id, Hex(q=2, r=1, s=-3))
    push_steps(state, _effect_steps(state, spell))
    first = process_stack(state)
    assert first.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": enemy.id}
    second = process_stack(state)
    assert second.input_request is not None
    assert {option.id for option in second.input_request.options} == {victim.id}
    state.execution_stack[-1].pending_input = {"selection": victim.id}
    result = process_stack(state)
    assert victim.id not in state.entity_locations
    assert any(event.event_type == GameEventType.UNIT_DEFEATED for event in result.events)


@pytest.mark.effect_flow
def test_dominate_person_rejects_adjacent_minion_outside_casters_radius() -> None:
    state, spell = _state("dominate_person")
    enemy = fresh_gydion().model_copy(deep=True)
    enemy.id = "enemy_hero"
    enemy.team = TeamColor.BLUE
    state.teams[TeamColor.BLUE].heroes.append(enemy)
    state.place_entity(enemy.id, Hex(q=3, r=0, s=-3))
    outside = Minion(
        id="outside_minion",
        name="Outside",
        team=TeamColor.BLUE,
        type=MinionType.MELEE,
    )
    state.teams[TeamColor.BLUE].minions.append(outside)
    state.place_entity(outside.id, Hex(q=4, r=0, s=-4))

    push_steps(state, _effect_steps(state, spell))
    first = process_stack(state)
    assert first.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": enemy.id}
    result = process_stack(state)

    assert result.input_request is None
    assert state.get_position(outside.id) == Hex(q=4, r=0, s=-4)


@pytest.mark.effect_flow
def test_find_familiar_places_one_then_optionally_removes_prepared_spells() -> None:
    state, spell = _state("find_familiar")
    familiar = Token(id="familiar_1", name="Familiar", token_type=TokenType.FAMILIAR)
    state.register_entity(familiar, "token")
    state.token_pool[TokenType.FAMILIAR] = [familiar]
    steps = _effect_steps(state, spell)
    assert [type(step) for step in steps] == [SelectStep, PlaceTokenStep, RemovePreparedSpellsStep]
    push_steps(state, steps)
    place = process_stack(state)
    assert place.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": 0, "s": -2}}
    remove = process_stack(state)
    assert state.get_position(familiar.id) == Hex(q=2, r=0, s=-2)
    assert remove.input_request is not None
    assert remove.input_request.player_id == "hero_caster"
    state.execution_stack[-1].pending_input = {"selection": "shield"}
    again = process_stack(state)
    assert again.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": "SKIP"}
    finished = process_stack(state)
    assert finished.input_request is None
    assert state.get_card_by_id("shield").state == CardState.OUTSIDE_SPELLBOOK


@pytest.mark.effect_flow
def test_find_familiar_does_not_remove_spells_when_mandatory_placement_fails() -> None:
    state, spell = _state("find_familiar", hexes=[(0, 0, 0)])
    shield = state.get_card_by_id("shield")
    assert shield is not None and shield.state == CardState.SPELLBOOK

    push_steps(state, _effect_steps(state, spell))
    result = process_stack(state)

    assert result.input_request is None
    assert shield.state == CardState.SPELLBOOK


@pytest.mark.effect_flow
def test_dimension_door_requires_empty_space_at_exact_computed_radius_and_zero_fails() -> None:
    state, spell = _state("dimension_door")
    push_steps(state, _effect_steps(state, spell))
    zero = process_stack(state)
    assert zero.input_request is None
    assert state.get_position("hero_caster") == Hex(q=0, r=0, s=0)

    state2, spell2 = _state("dimension_door")
    owner = state2.get_hero("hero_caster")
    for item in [spell for spell in owner.spells if spell.id != "dimension_door"][:2]:
        item.state = CardState.OUTSIDE_SPELLBOOK
        item.is_facedown = False
    push_steps(state2, _effect_steps(state2, spell2))
    exact = process_stack(state2)
    assert exact.input_request is not None
    options = {option.metadata["raw"] for option in exact.input_request.options}
    assert Hex(q=2, r=0, s=-2) in options
    assert Hex(q=1, r=0, s=-1) not in options
    assert Hex(q=3, r=0, s=-3) not in options


@pytest.mark.effect_flow
def test_banishment_places_adjacent_token_into_empty_space_in_radius() -> None:
    state, spell = _state("banishment")
    token = _add_token(state, "rock_1", TokenType.ROCK, (1, 0, -1))
    steps = _effect_steps(state, spell)
    assert isinstance(steps[-1], PlaceUnitStep)
    push_steps(state, steps)
    target = process_stack(state)
    assert target.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": token.id}
    destination = process_stack(state)
    assert destination.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": {"q": 3, "r": 0, "s": -3}}
    result = process_stack(state)
    assert result.input_request is None
    assert state.get_position(token.id) == Hex(q=3, r=0, s=-3)
    assert any(event.event_type == GameEventType.TOKEN_MOVED for event in result.events)

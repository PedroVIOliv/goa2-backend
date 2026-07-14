from __future__ import annotations

import pytest
from pydantic import ValidationError

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board
from goa2.domain.models import (
    ActionType,
    CardColor,
    CardState,
    CardTier,
    Hero,
    SpellCard,
    StatType,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState


def fresh_gydion() -> Hero:
    hero = HeroRegistry.get("Gydion")
    assert hero is not None
    hero.initialize_state()
    return hero


def gydion_spell(spell_id: str) -> SpellCard:
    hero = HeroRegistry.get("Gydion")
    assert hero is not None
    return next(spell.model_copy(deep=True) for spell in hero.spells if spell.id == spell_id)


EXPECTED_FIRST_SIX_SPELLS = {
    "shocking_grasp": {
        "name": "Shocking Grasp",
        "spell_rank": 0,
        "color": CardColor.GOLD,
        "tier": CardTier.UNTIERED,
        "action": ActionType.ATTACK,
        "value": 3,
        "range": None,
        "radius": None,
        "is_ranged": False,
        "text": (
            "Target a unit adjacent to you. After the attack: " "Move the target up to 1 space."
        ),
    },
    "magic_missile": {
        "name": "Magic Missile",
        "spell_rank": 0,
        "color": CardColor.GOLD,
        "tier": CardTier.UNTIERED,
        "action": ActionType.ATTACK,
        "value": 1,
        "range": 3,
        "radius": None,
        "is_ranged": True,
        "text": "Target a unit in range and not adjacent to you.",
    },
    "expeditious_retreat": {
        "name": "Expeditious Retreat",
        "spell_rank": 0,
        "color": CardColor.GOLD,
        "tier": CardTier.UNTIERED,
        "action": ActionType.MOVEMENT,
        "value": 5,
        "range": None,
        "radius": None,
        "is_ranged": False,
        "text": "Move only in a straight line.",
    },
    "burning_hands": {
        "name": "Burning Hands",
        "spell_rank": 1,
        "color": CardColor.RED,
        "tier": CardTier.I,
        "action": ActionType.ATTACK,
        "value": 5,
        "range": None,
        "radius": None,
        "is_ranged": False,
        "text": (
            "Target a unit adjacent to you. Before the attack: Up to 1 enemy hero "
            "adjacent to the target discards a card, if able."
        ),
    },
    "suggestion": {
        "name": "Suggestion",
        "spell_rank": 1,
        "color": CardColor.BLUE,
        "tier": CardTier.I,
        "action": ActionType.SKILL,
        "value": None,
        "range": None,
        "radius": 3,
        "is_ranged": False,
        "text": "If able, an enemy hero in radius moves 3 spaces in a straight line.",
    },
    "shield": {
        "name": "Shield",
        "spell_rank": 1,
        "color": CardColor.GREEN,
        "tier": CardTier.I,
        "action": ActionType.SKILL,
        "value": None,
        "range": None,
        "radius": None,
        "is_ranged": False,
        "text": (
            "This round: You are immune to basic attacks. "
            "(Cancelled if the spell is returned to the spellbook.)"
        ),
    },
}


def test_spell_card_common_definition_defaults() -> None:
    spell = SpellCard(
        id="future_spell",
        name="Future Spell",
        image_id="FutureSpell",
        spell_rank=2,
        tier=CardTier.II,
        color=CardColor.RED,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        effect_text="Future spell text.",
    )

    assert spell.initiative == 0
    assert spell.secondary_actions == {
        ActionType.HOLD: 0,
        ActionType.CLEAR: 0,
    }
    assert spell.effect_id == "future_spell"
    assert spell.state == CardState.OUTSIDE_SPELLBOOK
    assert spell.is_facedown is False
    assert spell.item is None
    assert spell.range_value is None
    assert spell.radius_value is None


def test_registry_gydion_has_all_spells_and_preserves_first_six_definitions() -> None:
    gydion = fresh_gydion()

    assert len(gydion.spells) == 22
    assert set(EXPECTED_FIRST_SIX_SPELLS) <= {str(spell.id) for spell in gydion.spells}
    for spell in (spell for spell in gydion.spells if spell.id in EXPECTED_FIRST_SIX_SPELLS):
        expected = EXPECTED_FIRST_SIX_SPELLS[str(spell.id)]
        assert isinstance(spell, SpellCard)
        assert spell.name == expected["name"]
        assert spell.spell_rank == expected["spell_rank"]
        assert spell.color == expected["color"]
        assert spell.tier == expected["tier"]
        assert spell.primary_action == expected["action"]
        assert spell.primary_action_value == expected["value"]
        assert spell.range_value == expected["range"]
        assert spell.radius_value == expected["radius"]
        assert spell.is_ranged is expected["is_ranged"]
        assert spell.initiative == 0
        assert spell.item is None
        assert spell.effect_id == spell.id
        assert spell.effect_text == expected["text"]

    lesser_enchantment = next(card for card in gydion.deck if card.id == "lesser_enchantment")
    assert lesser_enchantment.item == StatType.DEFENSE


@pytest.mark.parametrize(
    ("spell_id", "expected_actions"),
    [
        (
            "shocking_grasp",
            {ActionType.ATTACK, ActionType.CLEAR, ActionType.HOLD},
        ),
        (
            "magic_missile",
            {ActionType.ATTACK, ActionType.CLEAR, ActionType.HOLD},
        ),
        (
            "burning_hands",
            {ActionType.ATTACK, ActionType.CLEAR, ActionType.HOLD},
        ),
        (
            "expeditious_retreat",
            {ActionType.MOVEMENT, ActionType.FAST_TRAVEL, ActionType.HOLD},
        ),
        ("suggestion", {ActionType.SKILL, ActionType.HOLD}),
        ("shield", {ActionType.SKILL, ActionType.HOLD}),
    ],
)
def test_spell_generated_action_menu(spell_id: str, expected_actions: set[ActionType]) -> None:
    spell = gydion_spell(spell_id)

    assert {spell.primary_action, *spell.secondary_actions} == expected_actions


def test_spells_start_faceup_outside_every_normal_card_zone() -> None:
    gydion = fresh_gydion()
    normal_zone_cards = [
        *gydion.deck,
        *gydion.hand,
        *gydion.discard_pile,
        *(card for card in gydion.played_cards if card is not None),
    ]
    if gydion.current_turn_card is not None:
        normal_zone_cards.append(gydion.current_turn_card)
    if gydion.extra_turn_card is not None:
        normal_zone_cards.append(gydion.extra_turn_card)
    if gydion.ultimate_card is not None:
        normal_zone_cards.append(gydion.ultimate_card)

    assert all(spell.state == CardState.OUTSIDE_SPELLBOOK for spell in gydion.spells)
    assert all(not spell.is_facedown for spell in gydion.spells)
    assert not ({spell.id for spell in gydion.spells} & {card.id for card in normal_zone_cards})
    assert gydion.spellbook == []
    assert gydion.cast_spells == gydion.spells


def test_initialize_state_does_not_add_spells_to_starting_hand() -> None:
    gydion = fresh_gydion()
    initial_hand_ids = {card.id for card in gydion.hand}

    gydion.initialize_state()

    assert {card.id for card in gydion.hand} == initial_hand_ids
    assert not ({spell.id for spell in gydion.spells} & initial_hand_ids)


def test_hero_and_game_state_json_round_trip_preserve_spell_subtype_and_zones() -> None:
    gydion = fresh_gydion()
    shocking_grasp = next(spell for spell in gydion.spells if spell.id == "shocking_grasp")
    shocking_grasp.state = CardState.SPELLBOOK
    shocking_grasp.is_facedown = True

    restored_hero = Hero.model_validate_json(gydion.model_dump_json())
    assert all(isinstance(spell, SpellCard) for spell in restored_hero.spells)
    assert {spell.id for spell in restored_hero.spellbook} == {"shocking_grasp"}
    assert len(restored_hero.cast_spells) == len(gydion.spells) - 1

    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[gydion]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE),
        },
    )
    restored_state = GameState.model_validate_json(state.model_dump_json())
    restored_owner = restored_state.get_spellbook_owner()
    assert restored_owner is not None
    assert all(isinstance(spell, SpellCard) for spell in restored_owner.spells)
    assert restored_state.get_card_by_id("shocking_grasp") is restored_owner.spellbook[0]


def test_spell_cards_reject_normal_card_states_and_static_deck_metadata() -> None:
    spell = gydion_spell("shield")

    with pytest.raises(ValidationError):
        spell.state = CardState.HAND
    assert spell.state == CardState.OUTSIDE_SPELLBOOK
    with pytest.raises(ValidationError):
        spell.initiative = 1
    assert spell.initiative == 0
    with pytest.raises(ValidationError):
        spell.item = StatType.DEFENSE
    assert spell.item is None


@pytest.mark.parametrize("operation", ["play", "discard", "return_to_hand", "return_to_deck"])
def test_hero_normal_lifecycle_rejects_spell_cards(operation: str) -> None:
    gydion = fresh_gydion()
    spell = gydion.spells[0]

    if operation in {"play", "discard"}:
        gydion.hand.append(spell)

    with pytest.raises(ValueError, match="Spell cards cannot enter the normal card lifecycle"):
        if operation == "play":
            gydion.play_card(spell)
        elif operation == "discard":
            gydion.discard_card(spell)
        elif operation == "return_to_hand":
            gydion.return_card_to_hand(spell)
        else:
            gydion.return_card_to_deck(spell)


def test_spellbook_owner_lookup_rejects_multiple_owners() -> None:
    first = fresh_gydion()
    second = fresh_gydion().model_copy(update={"id": "hero_other"}, deep=True)
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[first]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[second]),
        },
    )

    with pytest.raises(ValueError, match="exactly one spellbook owner"):
        state.get_spellbook_owner()

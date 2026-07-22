"""P1: starts_in_deck flag + Takahide starting-hand composition."""

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import Card, CardState, TeamColor
from goa2.engine.setup import GameSetup


def fresh_takahide():
    hero = HeroRegistry.get("Takahide")
    assert hero is not None
    hero.initialize_state()
    return hero


def test_starts_in_deck_defaults_false():
    assert Card.model_fields["starts_in_deck"].default is False


def test_takahide_starting_hand_is_five_cards():
    hero = fresh_takahide()
    hand_ids = {c.id for c in hero.hand}
    assert hand_ids == {
        "float_like_a_butterfly",
        "bushido",
        "proven_warrior",
        "come_to_aid",
        "set_an_example",
    }


def test_sting_and_strike_start_in_deck():
    hero = fresh_takahide()
    for cid in ("sting_like_a_bee", "strike_like_a_tiger"):
        card = next(c for c in hero.deck if c.id == cid)
        assert card.state == CardState.DECK
        assert card not in hero.hand


def test_starts_in_deck_survives_serialization():
    hero = fresh_takahide()
    dumped = hero.model_dump_json()
    restored = type(hero).model_validate_json(dumped)
    sting = next(c for c in restored.deck if c.id == "sting_like_a_bee")
    assert sting.starts_in_deck is True


def test_production_setup_honors_starts_in_deck():
    """Full GameSetup (not just initialize_state) must leave Sting/Strike in the deck."""
    state = GameSetup.create_game(
        "src/goa2/data/maps/forgotten_island.json",
        ["Takahide"],
        ["Arien"],
    )
    takahide = next(h for h in state.teams[TeamColor.RED].heroes if h.name == "Takahide")
    assert {c.id for c in takahide.hand} == {
        "float_like_a_butterfly",
        "bushido",
        "proven_warrior",
        "come_to_aid",
        "set_an_example",
    }
    for cid in ("sting_like_a_bee", "strike_like_a_tiger"):
        card = next(c for c in takahide.deck if c.id == cid)
        assert card.state == CardState.DECK


def test_other_heroes_unaffected():
    hero = HeroRegistry.get("Arien")
    assert hero is not None
    hero.initialize_state()
    assert all(c.starts_in_deck is False for c in hero.deck)
    assert all(c.state == CardState.HAND for c in hero.hand)

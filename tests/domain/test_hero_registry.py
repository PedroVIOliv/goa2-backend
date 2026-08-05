import pytest

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import ActionType, Card, CardColor, CardTier, Hero


def _hero(name: str, *card_ids: str) -> Hero:
    return Hero(
        id=f"hero_{name.lower()}",
        name=name,
        deck=[
            Card(
                id=card_id,
                name=card_id,
                tier=CardTier.I,
                color=CardColor.RED,
                initiative=1,
                primary_action=ActionType.ATTACK,
                primary_action_value=1,
                effect_id="none",
                effect_text="",
            )
            for card_id in card_ids
        ],
    )


def test_registered_card_ids_are_globally_unique() -> None:
    owners: dict[str, str] = {}

    for hero_name in HeroRegistry.list_heroes(include_playtest=True):
        hero = HeroRegistry.get(hero_name)
        assert hero is not None
        cards = [*hero.deck, *hero.spells]
        if hero.ultimate_card is not None:
            cards.append(hero.ultimate_card)

        for card in cards:
            assert (
                card.id not in owners
            ), f"card id {card.id!r} is shared by {owners.get(card.id)!r} and {hero_name!r}"
            owners[card.id] = hero_name


def test_registry_rejects_card_id_shared_by_different_heroes(monkeypatch) -> None:
    monkeypatch.setattr(HeroRegistry, "_heroes", {})
    HeroRegistry.register(_hero("First", "shared_card"))

    with pytest.raises(
        ValueError,
        match="Card ID collision: 'shared_card' is defined by both 'First' and 'Second'",
    ):
        HeroRegistry.register(_hero("Second", "shared_card"))


def test_registry_rejects_duplicate_card_id_within_one_hero(monkeypatch) -> None:
    monkeypatch.setattr(HeroRegistry, "_heroes", {})

    with pytest.raises(
        ValueError,
        match="Card ID collision: 'repeated_card' is defined more than once by 'First'",
    ):
        HeroRegistry.register(_hero("First", "repeated_card", "repeated_card"))


def test_registry_excludes_playtest_heroes_by_default(monkeypatch) -> None:
    monkeypatch.setattr(HeroRegistry, "_heroes", {})
    monkeypatch.setattr(HeroRegistry, "_playtest_heroes", set())
    HeroRegistry.register(_hero("Released", "released_card"))
    HeroRegistry.register(_hero("Experimental", "experimental_card"), is_playtest=True)

    assert HeroRegistry.list_heroes() == ["Released"]
    assert HeroRegistry.list_heroes(include_playtest=True) == [
        "Released",
        "Experimental",
    ]

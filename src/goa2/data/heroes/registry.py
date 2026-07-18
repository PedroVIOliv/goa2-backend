from typing import ClassVar

from goa2.domain.models import Card, Hero

HERO_DIFFICULTY_STARS = {
    # 1 Star
    "Arien": 1,
    "Xargatha": 1,
    "Wasp": 1,
    "Brogan": 1,
    "Tigerclaw": 1,
    "Sabina": 1,
    "Dodger": 1,
    # 2 Stars
    "Bain": 2,
    "Whisper": 2,
    "Rowenna": 2,
    "Ursafar": 2,
    "Min": 2,
    "Misa": 2,
    "Garrus": 2,
    "Silverarrow": 2,
    # 3 Stars
    "Mortimer": 3,
    "Widget": 3,
    "Trinkets": 3,
    "Tali": 3,
    "Brynn": 3,
    "Cutter": 3,
    "Hanu": 3,
    "Mrak": 3,
    "Swift": 3,
    "Wuk": 3,
    # 4 Stars
    "Emmitt": 4,
    "Gydion": 4,
    "Ignatia": 4,
    "NebKher": 4,
    "Razzle": 4,
    "Snorri": 4,
    "Takahide": 4,
}


def get_hero_difficulty_stars(hero_name: str) -> int:
    """Return pre-game hero difficulty as a star count."""
    return HERO_DIFFICULTY_STARS.get(hero_name, 0)


class HeroRegistry:
    """
    Static registry for Hero definitions (Decks).
    """

    _heroes: ClassVar[dict[str, Hero]] = {}

    @classmethod
    def register(cls, hero: Hero) -> None:
        """Register a hero definition while enforcing global card-ID uniqueness.

        Several engine and visibility lifecycles intentionally use a bare card
        ID as their key, so definitions cannot safely reuse an ID across heroes,
        spells, or ultimate cards. Re-registering the same hero remains allowed
        for tests and development reloads; its previous definition is excluded
        from the collision check.
        """
        cards = cls._cards(hero)
        incoming_ids: set[str] = set()
        for card in cards:
            card_id = str(card.id)
            if card_id in incoming_ids:
                raise ValueError(
                    f"Card ID collision: {card_id!r} is defined more than once "
                    f"by {hero.name!r}. Card IDs must be globally unique."
                )
            incoming_ids.add(card_id)

        for existing_name, existing_hero in cls._heroes.items():
            if existing_name == hero.name:
                continue
            existing_ids = {str(card.id) for card in cls._cards(existing_hero)}
            collisions = incoming_ids & existing_ids
            if collisions:
                card_id = sorted(collisions)[0]
                raise ValueError(
                    f"Card ID collision: {card_id!r} is defined by both "
                    f"{existing_name!r} and {hero.name!r}. Card IDs must be globally unique."
                )

        cls._heroes[hero.name] = hero

    @staticmethod
    def _cards(hero: Hero) -> list[Card]:
        cards = [*hero.deck, *hero.spells]
        if hero.ultimate_card is not None:
            cards.append(hero.ultimate_card)
        return cards

    @classmethod
    def get(cls, name: str) -> Hero | None:
        hero = cls._heroes.get(name)
        if hero:
            return hero.model_copy(deep=True)
        return None

    @classmethod
    def list_heroes(cls) -> list[str]:
        return list(cls._heroes.keys())

    @classmethod
    def list_hero_metadata(cls) -> list[dict]:
        return [
            {
                "id": hero_name,
                "difficulty_stars": get_hero_difficulty_stars(hero_name),
            }
            for hero_name in HERO_DIFFICULTY_STARS
            if hero_name in cls._heroes
        ]

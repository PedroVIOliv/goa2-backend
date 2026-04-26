from typing import Dict, List, Optional
from goa2.domain.models import Hero


HERO_DIFFICULTY_STARS = {
    "Arien": 1,
    "Xargatha": 1,
    "Wasp": 1,
    "Brogan": 1,
    "Tigerclaw": 1,
    "Sabina": 1,
    "Dodger": 1,
    "Bain": 2,
    "Whisper": 2,
    "Rowenna": 2,
    "Ursafar": 2,
    "Min": 2,
    "Misa": 2,
    "Garrus": 2,
    "Silverarrow": 2,
}


def get_hero_difficulty_stars(hero_name: str) -> int:
    """Return pre-game hero difficulty as a star count."""
    return HERO_DIFFICULTY_STARS[hero_name]


class HeroRegistry:
    """
    Static registry for Hero definitions (Decks).
    """

    _heroes: Dict[str, Hero] = {}

    @classmethod
    def register(cls, hero: Hero):
        cls._heroes[hero.name] = hero

    @classmethod
    def get(cls, name: str) -> Optional[Hero]:
        hero = cls._heroes.get(name)
        if hero:
            return hero.model_copy(deep=True)
        return None

    @classmethod
    def list_heroes(cls) -> List[str]:
        return list(cls._heroes.keys())

    @classmethod
    def list_hero_metadata(cls) -> List[dict]:
        return [
            {
                "id": hero_name,
                "difficulty_stars": get_hero_difficulty_stars(hero_name),
            }
            for hero_name in cls.list_heroes()
        ]

from typing import Dict, List, Optional
from goa2.domain.models import Hero, CardTier

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

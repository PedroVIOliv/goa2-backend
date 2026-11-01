"""Guardrail: every card whose text repeats an action checks repeat prevention.

A hand-built repeat silently ignores Enfeeblement ("cannot repeat actions").
The effect behind each "repeat" card — or a module helper it calls — must use
one of the shared repeat primitives below.
"""

import inspect
import re
import sys

from goa2.bootstrap import register_all_effects
from goa2.data.heroes.registry import HeroRegistry
from goa2.engine.effects import CardEffectRegistry

SHARED_REPEAT_TOKENS = (
    "MayRepeatOnceStep",
    "MayRepeatNTimesStep",
    "ValidateRepeatStep",
    "CanRepeatFilter",
    "can_repeat_action",
)

# "repeat" in the text, but the effect does not perform a repeat itself.
NOT_A_REPEAT = {
    "enfeeblement": "is the repeat prevention",
    "equilibrium": "reacts to repeats performed by other cards",
}

# Marker effects whose repeat is built by another card's effect.
REPEAT_BUILT_BY = {
    "twin_strike": "stunt_doubles",
}


def _effect_source(cls: type) -> str:
    """Source of the effect class, its same-module bases, and the module helpers it reaches."""
    module = sys.modules[cls.__module__]
    seen = {cls.__name__}
    chunks = [inspect.getsource(cls)]
    for base in cls.__mro__[1:]:
        if base.__module__ == cls.__module__:
            seen.add(base.__name__)
            chunks.append(inspect.getsource(base))
    frontier = list(chunks)
    while frontier:
        for name in set(re.findall(r"\b_[a-z]\w*\b", frontier.pop())):
            obj = getattr(module, name, None)
            if name in seen or not inspect.isfunction(obj) or obj.__module__ != cls.__module__:
                continue
            seen.add(name)
            source = inspect.getsource(obj)
            chunks.append(source)
            frontier.append(source)
    return "\n".join(chunks)


def _repeat_effect_ids() -> set[str]:
    ids = set()
    for name in HeroRegistry.list_heroes():
        hero = HeroRegistry.get(name)
        cards = [*hero.deck, *([hero.ultimate_card] if hero.ultimate_card else [])]
        for card in cards:
            if card.effect_id and "repeat" in (card.effect_text or "").lower():
                ids.add(card.effect_id)
    return ids


def test_repeat_cards_use_a_shared_repeat_primitive() -> None:
    register_all_effects()
    effect_ids = _repeat_effect_ids()
    assert effect_ids, "no repeat cards found; the scan is broken"

    missing = []
    for effect_id in sorted(effect_ids - NOT_A_REPEAT.keys()):
        effect = CardEffectRegistry.get(REPEAT_BUILT_BY.get(effect_id, effect_id))
        assert effect is not None, effect_id
        source = _effect_source(type(effect))
        if not any(token in source for token in SHARED_REPEAT_TOKENS):
            missing.append(effect_id)

    assert not missing, f"repeat cards that bypass repeat prevention: {missing}"

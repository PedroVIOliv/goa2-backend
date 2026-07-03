"""Razzle validation card effects for the multi-piece hero infrastructure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.types import BoardEntityID
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AddContextValueStep,
    AttackSequenceStep,
    GameStep,
    RemoveHeroPieceStep,
    SpawnHeroPieceStep,
)
from goa2.engine.topology import topology_distance

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


@register_effect("stunt_doubles")
class StuntDoublesEffect(CardEffect):
    """Target a unit adjacent to you. After the attack, spawn up to 3 more of you."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            SpawnHeroPieceStep(
                hero_id=str(hero.id),
                max_count=3,
                radius=stats.radius or 1,
            ),
        ]


@register_effect("phantom_strike")
class PhantomStrikeEffect(CardEffect):
    """Target adjacent unit. After attack, you may remove one of you if possible."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            RemoveHeroPieceStep(hero_id=str(hero.id), mode="choose_one", min_remaining=1),
        ]


@register_effect("crowd_control")
class CrowdControlEffect(CardEffect):
    """Skill removes other pieces; defense gains +2 per other piece in radius."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [RemoveHeroPieceStep(hero_id=str(hero.id), mode="all_others")]

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: dict,
    ) -> list[GameStep] | None:
        defender_piece = str(context.get("defender_id", defender.id))
        origin = state.get_position(defender_piece)
        if origin is None:
            return []

        radius = stats.radius or card.radius_value or 3
        bonus = 0
        for pid in state.get_piece_ids(str(defender.id)):
            if pid == defender_piece:
                continue
            loc = state.entity_locations.get(BoardEntityID(pid))
            if loc is not None and topology_distance(origin, loc, state) <= radius:
                bonus += 2

        if bonus <= 0:
            return []
        return [AddContextValueStep(key="defense_bonus", amount=bonus)]

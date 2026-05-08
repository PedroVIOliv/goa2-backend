from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    GamePhase,
    Hero,
    Minion,
    MinionType,
    SpawnPoint,
    SpawnType,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState

Coords = tuple[int, int, int] | Hex


def hex_at(coords: Coords) -> Hex:
    if isinstance(coords, Hex):
        return coords
    q, r, s = coords
    return Hex(q=q, r=r, s=s)


def skill_card(
    card_id: str,
    name: str | None = None,
    effect_id: str | None = None,
    *,
    color: CardColor = CardColor.GREEN,
    tier: CardTier = CardTier.I,
    initiative: int = 5,
    range_value: int | None = None,
    radius_value: int | None = None,
    is_ranged: bool = False,
) -> Card:
    values = dict(
        id=card_id,
        name=name or card_id.replace("_", " ").title(),
        tier=tier,
        color=color,
        initiative=initiative,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=is_ranged,
        effect_id=effect_id if effect_id is not None else card_id,
        effect_text="",
        is_facedown=False,
    )
    if range_value is not None:
        values["range_value"] = range_value
    if radius_value is not None:
        values["radius_value"] = radius_value
    return Card(**values)


def movement_card(
    card_id: str = "test_movement",
    *,
    value: int = 3,
    initiative: int = 1,
    effect_id: str = "",
) -> Card:
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=initiative,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=value,
        secondary_actions={},
        is_ranged=False,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )


def card_for_effect(card_id: str) -> Card:
    if card_id == "liquid_leap":
        return skill_card(
            "liquid_leap",
            "Liquid Leap",
            range_value=2,
            is_ranged=True,
            initiative=4,
        )
    if card_id == "static_barrier":
        return skill_card(
            "static_barrier",
            "Static Barrier",
            color=CardColor.SILVER,
            tier=CardTier.UNTIERED,
            initiative=13,
            radius_value=2,
        )
    raise ValueError(f"No canonical card factory for effect card {card_id!r}")


def hero_card(hero_name: str, card_id: str) -> Card:
    hero = HeroRegistry.get(hero_name)
    if hero is None:
        raise ValueError(f"Unknown hero {hero_name!r}")
    cards = [*hero.deck]
    if hero.ultimate_card:
        cards.append(hero.ultimate_card)
    for card in cards:
        if card.id == card_id:
            playable = card.model_copy(deep=True)
            playable.state = CardState.UNRESOLVED
            playable.is_facedown = False
            return playable
    raise ValueError(f"No card {card_id!r} found for hero {hero_name!r}")


class EffectScenarioBuilder:
    def __init__(self) -> None:
        self._board = Board()
        self._teams: dict[TeamColor, Team] = {
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        }
        self._placements: dict[str, Hex] = {}
        self._actor_id: str | None = None
        self._phase = GamePhase.RESOLUTION
        self._unresolved_hero_ids: list[str] = []

    def line_board(self, length: int = 6) -> Self:
        hexes = {Hex(q=q, r=0, s=-q) for q in range(length)}
        self._set_board_hexes(hexes)
        return self

    def small_arena(self) -> Self:
        hexes = {
            Hex(q=0, r=0, s=0),
            Hex(q=1, r=0, s=-1),
            Hex(q=2, r=0, s=-2),
            Hex(q=3, r=0, s=-3),
            Hex(q=4, r=0, s=-4),
            Hex(q=5, r=0, s=-5),
            Hex(q=0, r=1, s=-1),
            Hex(q=1, r=1, s=-2),
            Hex(q=2, r=1, s=-3),
            Hex(q=3, r=1, s=-4),
        }
        self._set_board_hexes(hexes)
        return self

    def with_hexes(self, coords: Iterable[Coords]) -> Self:
        self._set_board_hexes({hex_at(c) for c in coords})
        return self

    def spawn_point(
        self,
        at: Coords,
        *,
        team: TeamColor = TeamColor.RED,
        spawn_type: SpawnType = SpawnType.HERO,
    ) -> Self:
        location = hex_at(at)
        self._board.tiles[location].spawn_point = SpawnPoint(
            location=location,
            team=team,
            type=spawn_type,
        )
        return self

    def hero(
        self,
        hero_id: str,
        *,
        team: TeamColor = TeamColor.RED,
        at: Coords,
        name: str | None = None,
        current_card: str | Card | None = None,
    ) -> Self:
        hero = Hero(id=hero_id, name=name or hero_id, team=team, deck=[], level=1)
        if current_card is not None:
            hero.current_turn_card = (
                card_for_effect(current_card) if isinstance(current_card, str) else current_card
            )
        self._teams[team].heroes.append(hero)
        self._placements[hero_id] = hex_at(at)
        self._unresolved_hero_ids.append(hero_id)
        return self

    def red_hero(
        self,
        hero_id: str,
        *,
        at: Coords,
        name: str | None = None,
        current_card: str | Card | None = None,
    ) -> Self:
        return self.hero(
            hero_id,
            team=TeamColor.RED,
            at=at,
            name=name,
            current_card=current_card,
        )

    def blue_hero(
        self,
        hero_id: str,
        *,
        at: Coords,
        name: str | None = None,
        current_card: str | Card | None = None,
    ) -> Self:
        return self.hero(
            hero_id,
            team=TeamColor.BLUE,
            at=at,
            name=name,
            current_card=current_card,
        )

    def minion(
        self,
        minion_id: str,
        *,
        at: Coords,
        team: TeamColor,
        minion_type: MinionType = MinionType.MELEE,
    ) -> Self:
        minion = Minion(id=minion_id, name=minion_id, team=team, type=minion_type)
        self._teams[team].minions.append(minion)
        self._placements[minion_id] = hex_at(at)
        return self

    def red_minion(
        self,
        minion_id: str,
        *,
        at: Coords,
        minion_type: MinionType = MinionType.MELEE,
    ) -> Self:
        return self.minion(
            minion_id,
            team=TeamColor.RED,
            at=at,
            minion_type=minion_type,
        )

    def blue_minion(
        self,
        minion_id: str,
        *,
        at: Coords,
        minion_type: MinionType = MinionType.MELEE,
    ) -> Self:
        return self.minion(
            minion_id,
            team=TeamColor.BLUE,
            at=at,
            minion_type=minion_type,
        )

    def with_card(self, hero_id: str, card: str | Card) -> Self:
        hero = self._find_hero(hero_id)
        hero.current_turn_card = card_for_effect(card) if isinstance(card, str) else card
        return self

    def with_actor(self, hero_id: str) -> Self:
        self._actor_id = hero_id
        return self

    def with_unresolved_heroes(self, hero_ids: list[str]) -> Self:
        self._unresolved_hero_ids = hero_ids
        return self

    def build(self) -> GameState:
        state = GameState(board=self._board, teams=self._teams)
        state.phase = self._phase
        for entity_id, location in self._placements.items():
            state.place_entity(entity_id, location)
        state.current_actor_id = self._actor_id
        state.unresolved_hero_ids = [h for h in self._unresolved_hero_ids if h != self._actor_id]
        return state

    def _set_board_hexes(self, hexes: set[Hex]) -> None:
        self._board = Board()
        self._board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
        self._board.populate_tiles_from_zones()

    def _find_hero(self, hero_id: str) -> Hero:
        for team in self._teams.values():
            for hero in team.heroes:
                if hero.id == hero_id:
                    return hero
        raise ValueError(f"Unknown hero {hero_id!r}")

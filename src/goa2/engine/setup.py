from typing import List
import random

from goa2.domain.state import GameState
from goa2.domain.models import Team, TeamColor, GamePhase, CardTier, CardState
from goa2.engine.map_loader import load_map
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.factory import EntityFactory
from goa2.domain.models.spawn import SpawnType


class GameSetup:
    """
    Orchestrates the initialization of a new game.
    """

    @staticmethod
    def create_game(
        map_path: str, red_heroes: List[str], blue_heroes: List[str]
    ) -> GameState:
        """
        Initializes a game with the specified map and heroes.
        :param map_path: Path to the JSON map file.
        :param red_heroes: List of Hero Names for Red Team.
        :param blue_heroes: List of Hero Names for Blue Team.
        """

        # 1. Load Map
        board = load_map(map_path)

        # 2. Calculate Life Counters
        total_players = len(red_heroes) + len(blue_heroes)
        # Rule: 4 players -> 6 counters. 6 players -> 8 counters.
        # Formula: Player Count + 2? (4+2=6, 6+2=8).
        # Let's assume even teams.
        counters = total_players + 2 if total_players >= 4 else 6  # Fallback default

        # 3. Initialize State
        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(
                    color=TeamColor.RED, heroes=[], minions=[], life_counters=counters
                ),
                TeamColor.BLUE: Team(
                    color=TeamColor.BLUE, heroes=[], minions=[], life_counters=counters
                ),
            },
            wave_counter=5,
            phase=GamePhase.SETUP,
        )

        # 4. Determine Lane & Battle Zone
        if not board.lane:
            raise ValueError("Map does not have a defined lane!")

        # Mid is usually the center of the lane list
        mid_index = len(board.lane) // 2
        active_zone_id = board.lane[mid_index]
        state.active_zone_id = active_zone_id

        # 5. Register Heroes & Place them
        GameSetup._setup_team(state, TeamColor.RED, red_heroes)
        GameSetup._setup_team(state, TeamColor.BLUE, blue_heroes)

        # 6. Spawn Initial Minions (In Active Zone)
        GameSetup._spawn_initial_minions(state, active_zone_id)

        # 7. Finalize Setup
        # Flip Coin
        state.tie_breaker_team = random.choice([TeamColor.RED, TeamColor.BLUE])

        # Transition to Planning
        state.phase = GamePhase.PLANNING

        print(
            f"[Setup] Game Created. Map: {len(board.tiles)} tiles. Players: {total_players}. Life: {counters}."
        )
        print(
            f"[Setup] Battle Zone: {active_zone_id}. Coin Favors: {state.tie_breaker_team.name}"
        )

        return state

    @staticmethod
    def _setup_team(state: GameState, team_color: TeamColor, hero_names: List[str]):
        """
        Instantiates heroes, sets up their hand, and places them at spawn points.
        """
        available_spawns = [
            sp
            for sp in state.board.spawn_points
            if sp.type == SpawnType.HERO and sp.team == team_color
        ]

        for name in hero_names:
            # A. Instantiate
            hero = HeroRegistry.get(name)
            if not hero:
                raise ValueError(f"Hero '{name}' not found in registry.")

            # Ensure unique ID if duplicates allowed (usually not, but safe practice)
            # HeroRegistry returns fixed ID. If duplicate heroes allowed, we'd need dynamic IDs.
            # For now, standard GoA2 assumes unique heroes.
            hero.team = team_color

            # B. Setup Hand (Tier I + Untiered)
            hero.hand = []

            for card in hero.deck:
                if card.tier in [CardTier.I, CardTier.UNTIERED]:
                    hero.return_card_to_hand(card)
                else:
                    card.state = CardState.DECK

            # Register to Team and State
            state.register_entity(hero, "hero")

            # C. Place on Board
            # Find an empty spawn point
            spawn_loc = None
            target_sp = None

            for sp in available_spawns:
                tile = state.board.get_tile(sp.location)
                if tile and not tile.is_occupied:
                    spawn_loc = sp.location
                    target_sp = sp
                    break

            if spawn_loc:
                state.place_entity(hero.id, spawn_loc)
                # print(f"   Placed {hero.name} at {spawn_loc}")
            else:
                print(f"[WARNING] No spawn point available for {hero.name}!")

    @staticmethod
    def _spawn_initial_minions(state: GameState, zone_id: str):
        """
        Spawns minions at all minion spawn points in the target zone.
        """
        zone = state.board.zones.get(zone_id)
        if not zone:
            return

        for h in zone.hexes:
            sp = state.board.get_spawn_point(h)
            if sp and sp.type == SpawnType.MINION and sp.minion_type:
                # Create Minion
                minion = EntityFactory.create_minion(state, sp.team, sp.minion_type)
                state.register_entity(minion, "minion")

                # Place
                state.place_entity(minion.id, h)
                # print(f"   Spawned {minion.name} at {h}")

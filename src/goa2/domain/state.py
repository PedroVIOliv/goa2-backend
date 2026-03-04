from __future__ import annotations
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import (
    Team,
    TeamColor,
    Card,
    Hero,
    Unit,
    GamePhase,
    ResolutionStep,
)
from goa2.domain.models.effect import ActiveEffect
from goa2.domain.models.marker import Marker, MarkerType
from goa2.domain.types import HeroID, UnitID, BoardEntityID
from goa2.domain.input import InputRequest, InputRequestType


class GameState(BaseModel):
    """
    The Mutable State of the World.
    Contains everything needed to serialize/save/restore the game.
    """

    board: Board
    teams: Dict[TeamColor, Team]

    active_zone_id: Optional[str] = None  # The ID of the current Battle Zone

    phase: GamePhase = GamePhase.SETUP

    resolution_step: ResolutionStep = ResolutionStep.NONE
    round: int = 1
    turn: int = 1
    wave_counter: int = 5
    cheats_enabled: bool = False

    current_actor_id: Optional[HeroID] = (
        None  # ID of the Hero currently acting (Resolution Phase)
    )

    # The team that currently wins ties (Red or Blue)
    # Flips every time a different-team tie is resolved.
    tie_breaker_team: TeamColor = TeamColor.RED

    winner: Optional[TeamColor] = None
    victory_condition: Optional[str] = None

    input_stack: List[InputRequest] = Field(
        default_factory=list
    )  # The top of the stack is the active request waiting for input.
    # Logic:
    # 1. Action pushes Request.
    # 2. State pauses.
    # 3. Client responds to Request[0].
    # 4. Engine pops Request.
    execution_stack: List[Any] = Field(
        default_factory=list
    )  # Stores instances of GameStep (from goa2.engine.steps)
    # Typed as List[Any] to avoid circular imports with steps.py

    execution_context: Dict[str, Any] = Field(
        default_factory=dict
    )  # Stores transient data like "selected_target_id" between steps

    pending_inputs: Dict[HeroID, Optional[Card]] = Field(
        default_factory=dict
    )  # Planning Phase Buffer: HeroID -> Card

    pending_upgrades: Dict[HeroID, int] = Field(
        default_factory=dict
    )  # Level Up Phase Buffer: HeroID -> Number of upgrades pending

    unresolved_hero_ids: List[HeroID] = Field(
        default_factory=list
    )  # Resolution Phase Tracker: Set of HeroIDs who have not yet acted this turn.
    # We dynamically re-sort this set every step to determine the next actor.
    # Using List for JSON stability, acts as Set.

    # Registry for active non-Unit entities (Tokens, Traps, etc.)
    # Units are stored in self.teams, everything else goes here.
    misc_entities: Dict[BoardEntityID, Any] = Field(default_factory=dict)

    # Master Record of positions for ALL entities (Units + Tokens)
    entity_locations: Dict[BoardEntityID, Hex] = Field(default_factory=dict)

    next_entity_id: int = 1

    active_effects: List[ActiveEffect] = Field(default_factory=list)

    # Singleton markers - each MarkerType has exactly one Marker instance
    markers: Dict[MarkerType, Marker] = Field(default_factory=dict)

    # Private field for cached validator (not serialized)
    _validator: Optional[Any] = None

    def add_effect(self, effect: ActiveEffect):
        """Adds a spatial/behavioral effect to the active list."""
        self.active_effects.append(effect)

    def get_marker(self, marker_type: MarkerType) -> Marker:
        """
        Get or create a marker of the given type.
        Markers are singletons - this creates one if it doesn't exist.
        """
        if marker_type not in self.markers:
            self.markers[marker_type] = Marker(type=marker_type)
        return self.markers[marker_type]

    def place_marker(
        self, marker_type: MarkerType, target_id: str, value: int, source_id: str
    ) -> Marker:
        """
        Place a marker on a target hero.
        If marker was on another hero, it automatically leaves them (singleton).
        """
        marker = self.get_marker(marker_type)
        marker.place(target_id=target_id, value=value, source_id=source_id)
        return marker

    def remove_marker(self, marker_type: MarkerType) -> Optional[Marker]:
        """
        Return a marker to supply (remove from its current target).
        Returns the marker if it existed, None otherwise.
        """
        if marker_type in self.markers:
            marker = self.markers[marker_type]
            marker.remove()
            return marker
        return None

    def get_markers_on_hero(self, hero_id: str) -> List[Marker]:
        """Get all markers currently placed on a specific hero."""
        return [m for m in self.markers.values() if m.target_id == hero_id]

    def return_all_markers(self) -> None:
        """Return all markers to supply. Called at end of round."""
        for marker in self.markers.values():
            marker.remove()

    def return_markers_from_hero(self, hero_id: str) -> List[Marker]:
        """
        Return all markers from a specific hero (e.g., on defeat).
        Returns list of markers that were removed.
        """
        removed = []
        for marker in self.markers.values():
            if marker.target_id == hero_id:
                marker.remove()
                removed.append(marker)
        return removed

    def return_markers_by_source(self, source_id: str) -> List[Marker]:
        """
        Return all markers placed by a specific source (e.g., on source defeat).
        Returns list of markers that were removed.
        """
        removed = []
        for marker in self.markers.values():
            if marker.source_id == source_id:
                marker.remove()
                removed.append(marker)
        return removed

    @property
    def validator(self) -> Any:
        """Lazy-loaded validation service."""
        if self._validator is None:
            from goa2.engine.validation import ValidationService

            self._validator = ValidationService()
        return self._validator

    def create_entity_id(self, prefix: str) -> str:
        """
        Generates a guaranteed unique ID for a new entity.
        Format: {prefix}_{counter}
        """
        new_id = f"{prefix}_{self.next_entity_id}"
        self.next_entity_id += 1
        return new_id

    def register_entity(self, entity: Any, collection_type: str = "token"):
        """
        Registers a new entity into the state (misc_entities or team rosters).
        Enforces Global Uniqueness check.
        """
        if self.get_entity(entity.id) is not None:
            raise ValueError(
                f"ID Collision: Entity with ID {entity.id} already exists!"
            )

        if collection_type == "token":
            self.misc_entities[entity.id] = entity
        elif collection_type == "minion":
            if not hasattr(entity, "team") or entity.team not in self.teams:
                raise ValueError(
                    f"Cannot register minion {entity.id}: Invalid or missing team."
                )
            self.teams[entity.team].minions.append(entity)
            print(f"   [State] Registered Minion {entity.id} to Team {entity.team}")
        elif collection_type == "hero":
            if not hasattr(entity, "team") or entity.team not in self.teams:
                raise ValueError(
                    f"Cannot register hero {entity.id}: Invalid or missing team."
                )
            self.teams[entity.team].heroes.append(entity)
            print(f"   [State] Registered Hero {entity.id} to Team {entity.team}")

    @model_validator(mode="after")
    def rebuild_occupancy_cache(self) -> "GameState":
        """
        Synchronizes board.tiles.occupant_id based on entity_locations.
        This ensures that entity_locations is the Single Source of Truth for persistence.
        """
        # 1. Clear existing occupancy on board tiles
        for tile in self.board.tiles.values():
            tile.occupant_id = None

        # 2. Re-populate based on entity_locations
        from goa2.domain.types import BoardEntityID

        for uid, location in self.entity_locations.items():
            if location in self.board.tiles:
                self.board.tiles[location].occupant_id = BoardEntityID(str(uid))

        return self

    @property
    def is_game_over(self) -> bool:
        """Returns True if the game has ended."""
        return self.phase == GamePhase.GAME_OVER

    @property
    def unit_locations(self) -> Dict[UnitID, Hex]:
        """Legacy accessor for backwards compatibility during refactor."""
        # Convert keys to UnitID
        return {UnitID(str(k)): v for k, v in self.entity_locations.items()}

    @property
    def awaiting_input_type(self) -> InputRequestType:
        """
        Helper to get the current expected input type from the top of the stack.
        Returns NONE if stack is empty.
        """
        if not self.input_stack:
            return InputRequestType.NONE
        return self.input_stack[-1].request_type

    def get_hero(self, hero_id: HeroID) -> Optional[Hero]:
        """Finds a Hero by ID."""
        for team in self.teams.values():
            for hero in team.heroes:
                if hero.id == hero_id:
                    return hero
        return None

    def get_entity(self, entity_id: BoardEntityID) -> Optional[Any]:
        """
        Unified lookup for ANY entity on the board (Unit or Token).
        """
        # 1. Check Misc Entities
        if entity_id in self.misc_entities:
            return self.misc_entities[entity_id]

        # 2. Check Units
        return self.get_unit(UnitID(str(entity_id)))

    def get_unit(self, unit_id: UnitID) -> Optional[Unit]:
        """
        Finds a Unit (Hero or Minion) by ID.
        O(N) search across all teams.
        """
        for team in self.teams.values():
            for hero in team.heroes:
                if str(hero.id) == str(unit_id):
                    return hero
            for minion in team.minions:
                if str(minion.id) == str(unit_id):
                    return minion
        return None

    def get_card_by_id(self, card_id: str) -> Optional[Card]:
        """
        Finds a Card by ID across all heroes.
        Searches current_turn_card, played_cards, hand, deck, discard_pile, and ultimate_card.
        """
        for team in self.teams.values():
            for hero in team.heroes:
                if hero.current_turn_card and hero.current_turn_card.id == card_id:
                    return hero.current_turn_card
                for card in hero.played_cards:
                    if card and card.id == card_id:
                        return card
                for card in hero.hand:
                    if card.id == card_id:
                        return card
                for card in hero.deck:
                    if card.id == card_id:
                        return card
                for card in hero.discard_pile:
                    if card.id == card_id:
                        return card
                if hero.ultimate_card and hero.ultimate_card.id == card_id:
                    return hero.ultimate_card
        return None

    def get_units_and_tokens(self) -> List[BoardEntityID]:
        """
        Returns IDs of all Units and Tokens currently on the board.

        This explicitly filters for Unit and Token types only, excluding
        any future board entity types (e.g., Structures, Hazards).

        Used by SelectStep for UNIT_OR_TOKEN target type.
        """
        from goa2.domain.models import Unit, Token

        result = []
        for eid in self.entity_locations.keys():
            entity = self.get_entity(eid)
            if entity and isinstance(entity, (Unit, Token)):
                result.append(eid)
        return result

    def place_entity(self, entity_id: BoardEntityID, target_hex: Hex):
        """
        Primary Primitive for putting something on the map.
        Updates Location Record AND Tile Cache.
        Overwrites any existing position.
        """
        # 1. Clear old location if exists
        old_hex = self.entity_locations.get(entity_id)
        if old_hex:
            old_tile = self.board.get_tile(old_hex)
            if (
                old_tile
                and old_tile.occupant_id
                and str(old_tile.occupant_id) == str(entity_id)
            ):
                old_tile.occupant_id = None

        # 2. Update Record
        self.entity_locations[entity_id] = target_hex

        # 3. Update New Tile Cache
        target_tile = self.board.get_tile(target_hex)
        if not target_tile or target_tile.occupant_id:
            raise ValueError(
                f"Cannot place entity {entity_id} at {target_hex}: Tile is occupied by {target_tile.occupant_id}"
            )
        target_tile.occupant_id = entity_id

    def remove_entity(self, entity_id: BoardEntityID):
        """
        Removes an entity from the board (locations and tiles).
        Does NOT remove it from Teams or Misc Registry.
        """
        if entity_id in self.entity_locations:
            loc = self.entity_locations[entity_id]
            del self.entity_locations[entity_id]

            tile = self.board.get_tile(loc)
            if tile:
                if tile.occupant_id and str(tile.occupant_id) == str(entity_id):
                    tile.occupant_id = None

    def move_unit(self, unit_id: UnitID, target_hex: Hex):
        """Wrapper for place_entity."""
        from goa2.domain.types import BoardEntityID

        self.place_entity(BoardEntityID(str(unit_id)), target_hex)

    def remove_unit(self, unit_id: UnitID):
        """Wrapper for remove_entity."""
        from goa2.domain.types import BoardEntityID

        self.remove_entity(BoardEntityID(str(unit_id)))

    model_config = ConfigDict(arbitrary_types_allowed=True)


GameState.model_rebuild()

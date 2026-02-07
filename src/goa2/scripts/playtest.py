"""
Guards of Atlantis II - CLI Playtest Interface

Run with: PYTHONPATH=src uv run python -m goa2.scripts.playtest
"""

from __future__ import annotations
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from goa2.domain.state import GameState
from goa2.domain.hex import Hex
from goa2.domain.models import (
    GamePhase,
    TeamColor,
    MinionType,
    CardTier,
    CardColor,
    ActionType,
    StatType,
)
from goa2.domain.models.unit import Hero, Minion, Unit
from goa2.domain.models.card import Card
from goa2.domain.types import HeroID, UnitID
from goa2.engine.setup import GameSetup
from goa2.engine.handler import process_resolution_stack
from goa2.engine.phases import commit_card, pass_turn

# Import effect scripts to register card effects
import goa2.scripts.arien_effects  # noqa: F401
import goa2.scripts.wasp_effects  # noqa: F401


# =============================================================================
# Game Logger
# =============================================================================


class GameLogger:
    """Logger for playtest sessions - writes to file for debugging."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"playtest_{timestamp}.log"
        self.json_file = self.log_dir / f"playtest_{timestamp}.json"

        # Setup Python logger
        self.logger = logging.getLogger("playtest")
        self.logger.setLevel(logging.DEBUG)

        # File handler - detailed logs
        fh = logging.FileHandler(self.log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
        )
        self.logger.addHandler(fh)

        # Also store structured events for JSON export
        self.events: List[Dict[str, Any]] = []
        self.turn_number = 0
        self.round_number = 0

        self.logger.info("=" * 60)
        self.logger.info("PLAYTEST SESSION STARTED")
        self.logger.info("=" * 60)

    def log_game_start(
        self, state: GameState, red_heroes: List[str], blue_heroes: List[str]
    ):
        """Log game initialization."""
        self.logger.info(f"Game initialized: RED={red_heroes}, BLUE={blue_heroes}")
        self.logger.info(
            f"Map: {state.active_zone_id} active, {len(state.board.tiles)} tiles"
        )
        self.logger.info(
            f"Life counters: RED={state.teams[TeamColor.RED].life_counters}, BLUE={state.teams[TeamColor.BLUE].life_counters}"
        )

        self._add_event(
            "GAME_START",
            {
                "red_heroes": red_heroes,
                "blue_heroes": blue_heroes,
                "active_zone": state.active_zone_id,
                "red_lives": state.teams[TeamColor.RED].life_counters,
                "blue_lives": state.teams[TeamColor.BLUE].life_counters,
            },
        )

    def log_phase_change(self, state: GameState):
        """Log phase transitions."""
        self.round_number = state.round
        self.turn_number = state.turn
        self.logger.info(
            f"Phase: {state.phase.value} (Round {state.round}, Turn {state.turn})"
        )

        self._add_event(
            "PHASE_CHANGE",
            {
                "phase": state.phase.value,
                "round": state.round,
                "turn": state.turn,
            },
        )

    def log_card_commit(self, hero_id: str, card_name: str):
        """Log card commitment during planning."""
        self.logger.info(f"COMMIT: {hero_id} -> {card_name}")
        self._add_event(
            "CARD_COMMIT",
            {
                "hero_id": hero_id,
                "card_name": card_name,
            },
        )

    def log_input_request(self, request: Dict[str, Any]):
        """Log when engine requests player input."""
        req_type = request.get("type", "UNKNOWN")
        player_id = request.get("player_id", "?")
        prompt = request.get("prompt", "")
        options = request.get("options", request.get("valid_options", []))

        # Sanitize options for logging (remove non-serializable objects)
        safe_options = []
        for opt in options[:10]:  # Limit to 10 for readability
            if isinstance(opt, dict):
                safe_options.append({k: str(v) for k, v in opt.items()})
            else:
                safe_options.append(str(opt))

        self.logger.info(f"INPUT_REQUEST: {req_type} for {player_id}")
        self.logger.debug(f"  Prompt: {prompt}")
        self.logger.debug(f"  Options: {safe_options}")

        self._add_event(
            "INPUT_REQUEST",
            {
                "type": req_type,
                "player_id": player_id,
                "prompt": prompt,
                "options_count": len(options),
                "options_sample": safe_options,
            },
        )

    def log_player_input(
        self, request_type: str, player_id: str, response: Dict[str, Any]
    ):
        """Log player's response to input request."""
        # Sanitize response for logging
        safe_response = {k: str(v) for k, v in response.items()}

        self.logger.info(f"PLAYER_INPUT: {player_id} -> {safe_response}")
        self._add_event(
            "PLAYER_INPUT",
            {
                "request_type": request_type,
                "player_id": player_id,
                "response": safe_response,
            },
        )

    def log_action(
        self, actor_id: str, action: str, details: Optional[Dict[str, Any]] = None
    ):
        """Log game actions (attacks, movements, etc.)."""
        self.logger.info(f"ACTION: {actor_id} {action}")
        if details:
            self.logger.debug(f"  Details: {details}")

        self._add_event(
            "ACTION",
            {
                "actor_id": actor_id,
                "action": action,
                "details": details or {},
            },
        )

    def log_state_snapshot(self, state: GameState):
        """Log a snapshot of current game state."""
        snapshot = {
            "phase": state.phase.value,
            "round": state.round,
            "turn": state.turn,
            "current_actor": state.current_actor_id,
            "red_lives": state.teams[TeamColor.RED].life_counters,
            "blue_lives": state.teams[TeamColor.BLUE].life_counters,
            "stack_size": len(state.execution_stack),
            "units": {},
        }

        # Log unit positions
        for entity_id, hex_pos in state.entity_locations.items():
            snapshot["units"][entity_id] = {
                "q": hex_pos.q,
                "r": hex_pos.r,
                "s": hex_pos.s,
            }

        self.logger.debug(f"STATE_SNAPSHOT: {json.dumps(snapshot, indent=2)}")
        self._add_event("STATE_SNAPSHOT", snapshot)

    def log_error(self, error: str, exception: Optional[Exception] = None):
        """Log errors."""
        self.logger.error(f"ERROR: {error}")
        if exception:
            self.logger.exception(exception)

        self._add_event(
            "ERROR",
            {
                "message": error,
                "exception": str(exception) if exception else None,
            },
        )

    def log_game_end(self, winner: Optional[str], red_lives: int, blue_lives: int):
        """Log game end."""
        self.logger.info("=" * 60)
        self.logger.info(f"GAME ENDED - Winner: {winner or 'None'}")
        self.logger.info(f"Final score: RED={red_lives}, BLUE={blue_lives}")
        self.logger.info("=" * 60)

        self._add_event(
            "GAME_END",
            {
                "winner": winner,
                "red_lives": red_lives,
                "blue_lives": blue_lives,
            },
        )

        # Save JSON log
        self._save_json()

    def _add_event(self, event_type: str, data: Dict[str, Any]):
        """Add structured event."""
        self.events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "round": self.round_number,
                "turn": self.turn_number,
                "type": event_type,
                "data": data,
            }
        )

    def _save_json(self):
        """Save events to JSON file."""
        try:
            with open(self.json_file, "w") as f:
                json.dump(self.events, f, indent=2)
            self.logger.info(f"JSON log saved to: {self.json_file}")
        except Exception as e:
            self.logger.error(f"Failed to save JSON log: {e}")

    def get_log_path(self) -> str:
        """Return path to log file."""
        return str(self.log_file)


# Global logger instance
game_logger: Optional[GameLogger] = None


def init_logger() -> GameLogger:
    """Initialize the game logger."""
    global game_logger
    game_logger = GameLogger()
    return game_logger


def get_logger() -> Optional[GameLogger]:
    """Get the current game logger."""
    return game_logger


# =============================================================================
# ANSI Color Codes
# =============================================================================


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Team colors
    RED = "\033[91m"
    BLUE = "\033[94m"

    # Zone colors
    ZONE_RED_BASE = "\033[41m\033[97m"  # Red bg, white text
    ZONE_RED_BEACH = "\033[101m\033[30m"  # Light red bg, black text
    ZONE_MID = "\033[43m\033[30m"  # Yellow bg, black text
    ZONE_BLUE_BEACH = "\033[104m\033[30m"  # Light blue bg, black text
    ZONE_BLUE_BASE = "\033[44m\033[97m"  # Blue bg, white text
    ZONE_JUNGLE = "\033[42m\033[30m"  # Green bg, black text

    # Card colors
    CARD_GOLD = "\033[93m"
    CARD_SILVER = "\033[37m"
    CARD_RED = "\033[91m"
    CARD_BLUE = "\033[94m"
    CARD_GREEN = "\033[92m"
    CARD_PURPLE = "\033[95m"

    # UI
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"


ZONE_COLORS = {
    "RedBase": Colors.ZONE_RED_BASE,
    "RedBeach": Colors.ZONE_RED_BEACH,
    "Mid": Colors.ZONE_MID,
    "BlueBeach": Colors.ZONE_BLUE_BEACH,
    "BlueBase": Colors.ZONE_BLUE_BASE,
    "RedJungle": Colors.ZONE_JUNGLE,
    "BlueJungle": Colors.ZONE_JUNGLE,
}

CARD_COLOR_MAP = {
    CardColor.GOLD: Colors.CARD_GOLD,
    CardColor.SILVER: Colors.CARD_SILVER,
    CardColor.RED: Colors.CARD_RED,
    CardColor.BLUE: Colors.CARD_BLUE,
    CardColor.GREEN: Colors.CARD_GREEN,
    CardColor.PURPLE: Colors.CARD_PURPLE,
}


# =============================================================================
# Utilities
# =============================================================================


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def get_input(prompt: str, valid_range: Optional[range] = None) -> str:
    """Get user input with optional numeric validation."""
    while True:
        try:
            value = input(f"{Colors.CYAN}> {prompt}: {Colors.RESET}").strip()
            if not value:
                continue
            if valid_range is not None:
                num = int(value)
                if num in valid_range:
                    return value
                print(
                    f"{Colors.RED}Please enter a number between {valid_range.start} and {valid_range.stop - 1}{Colors.RESET}"
                )
            else:
                return value
        except ValueError:
            if valid_range is not None:
                print(f"{Colors.RED}Please enter a valid number{Colors.RESET}")
            else:
                return value
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            sys.exit(0)


def format_hex(h: Hex) -> str:
    """Format hex coordinates for display."""
    return f"({h.q},{h.r},{h.s})"


# =============================================================================
# Unit Display
# =============================================================================


def get_unit_symbol(state: GameState, entity_id: str) -> Tuple[str, str]:
    """
    Returns (symbol, color) for a unit.
    Heroes: First letter of name
    Minions: m (melee), r (ranged), H (heavy)
    """
    unit = state.get_unit(entity_id)
    if not unit:
        return ("?", Colors.WHITE)

    color = Colors.RED if unit.team == TeamColor.RED else Colors.BLUE

    if isinstance(unit, Hero):
        symbol = unit.name[0].upper()
    elif isinstance(unit, Minion):
        if unit.type == MinionType.HEAVY:
            symbol = "H"
        elif unit.type == MinionType.RANGED:
            symbol = "r"
        else:
            symbol = "m"
    else:
        symbol = "?"

    return (symbol, color)


# =============================================================================
# ASCII Hex Grid Renderer
# =============================================================================


def cube_to_offset(h: Hex) -> Tuple[int, int]:
    """Convert cube coordinates to offset coordinates for rendering."""
    col = h.q
    row = h.r + (h.q + (h.q & 1)) // 2
    return (col, row)


def render_board(state: GameState, highlight_hexes: Optional[List[Hex]] = None) -> str:
    """
    Render the board as an ASCII hex grid.
    Uses a simplified representation due to the large map size.
    """
    if highlight_hexes is None:
        highlight_hexes = []

    lines = []

    # Group hexes by zone for a zone-based view (more readable for large maps)
    zone_hexes: Dict[str, List[Tuple[Hex, Optional[str]]]] = {}

    for hex_coord, tile in state.board.tiles.items():
        zone_id = state.board.get_zone_for_hex(hex_coord)
        if zone_id not in zone_hexes:
            zone_hexes[zone_id] = []

        occupant_id = tile.occupant_id
        zone_hexes[zone_id].append((hex_coord, occupant_id))

    # Display in lane order
    lane_order = state.board.lane if state.board.lane else list(zone_hexes.keys())

    # Add active zone indicator
    active_zone = state.active_zone_id

    lines.append(f"\n{Colors.BOLD}{'=' * 70}{Colors.RESET}")
    lines.append(
        f"{Colors.BOLD}  BOARD - Active Zone: {Colors.YELLOW}{active_zone}{Colors.RESET}"
    )
    lines.append(f"{Colors.BOLD}{'=' * 70}{Colors.RESET}\n")

    for zone_id in lane_order:
        if zone_id not in zone_hexes:
            continue

        zone_color = ZONE_COLORS.get(zone_id, Colors.WHITE)
        is_active = zone_id == active_zone

        # Zone header
        marker = " **ACTIVE**" if is_active else ""
        lines.append(
            f"{zone_color} {zone_id} {Colors.RESET}{Colors.YELLOW}{marker}{Colors.RESET}"
        )

        # Collect units in this zone
        units_in_zone = []
        empty_count = 0

        for hex_coord, occupant_id in zone_hexes[zone_id]:
            if occupant_id:
                symbol, color = get_unit_symbol(state, occupant_id)
                is_highlighted = hex_coord in highlight_hexes
                highlight = Colors.BOLD + Colors.YELLOW if is_highlighted else ""
                reset = Colors.RESET if is_highlighted else ""
                units_in_zone.append(
                    f"  {highlight}{color}{symbol}{Colors.RESET}{reset} {occupant_id[:15]:<15} @ {format_hex(hex_coord)}"
                )
            else:
                empty_count += 1

        if units_in_zone:
            for unit_line in units_in_zone:
                lines.append(unit_line)

        lines.append(f"  {Colors.DIM}({empty_count} empty hexes){Colors.RESET}")
        lines.append("")

    # Show jungles if they have units
    for zone_id in ["RedJungle", "BlueJungle"]:
        if zone_id in zone_hexes:
            has_units = any(occ for _, occ in zone_hexes[zone_id])
            if has_units:
                zone_color = ZONE_COLORS.get(zone_id, Colors.WHITE)
                lines.append(f"{zone_color} {zone_id} {Colors.RESET}")
                for hex_coord, occupant_id in zone_hexes[zone_id]:
                    if occupant_id:
                        symbol, color = get_unit_symbol(state, occupant_id)
                        lines.append(
                            f"  {color}{symbol}{Colors.RESET} {occupant_id[:15]:<15} @ {format_hex(hex_coord)}"
                        )
                lines.append("")

    return "\n".join(lines)


# =============================================================================
# Status Display
# =============================================================================


def render_status(state: GameState) -> str:
    """Render game status: phase, turn, round, life counters."""
    lines = []

    lines.append(f"\n{Colors.BOLD}{'=' * 70}{Colors.RESET}")
    lines.append(
        f"{Colors.BOLD}  GUARDS OF ATLANTIS II - Playtest Interface{Colors.RESET}"
    )
    lines.append(f"{Colors.BOLD}{'=' * 70}{Colors.RESET}")

    # Phase info
    phase_color = Colors.GREEN if state.phase == GamePhase.PLANNING else Colors.YELLOW
    lines.append(
        f"  Round {state.round} | Turn {state.turn} | {phase_color}{state.phase.value}{Colors.RESET} Phase"
    )

    # Life counters
    red_team = state.teams.get(TeamColor.RED)
    blue_team = state.teams.get(TeamColor.BLUE)

    red_lives = red_team.life_counters if red_team else 0
    blue_lives = blue_team.life_counters if blue_team else 0

    lines.append(
        f"  {Colors.RED}RED: {red_lives} lives{Colors.RESET} | {Colors.BLUE}BLUE: {blue_lives} lives{Colors.RESET}"
    )

    # Current actor (if in resolution)
    if state.phase == GamePhase.RESOLUTION and state.current_actor_id:
        lines.append(
            f"  Current Actor: {Colors.BOLD}{state.current_actor_id}{Colors.RESET}"
        )

    # Unresolved heroes
    if state.unresolved_hero_ids:
        lines.append(f"  Pending: {', '.join(state.unresolved_hero_ids)}")

    lines.append(f"{Colors.BOLD}{'=' * 70}{Colors.RESET}")

    return "\n".join(lines)


# =============================================================================
# Card Display
# =============================================================================


def format_card(card: Card, index: int) -> str:
    """Format a card for display (summary format)."""
    # Color indicator
    color_code = (
        CARD_COLOR_MAP.get(card.color, Colors.WHITE) if card.color else Colors.WHITE
    )
    color_name = card.color.value if card.color else "?"
    tier_name = card.tier.value if card.tier != CardTier.UNTIERED else "Basic"

    # Stats
    atk = card.get_base_stat_value(StatType.ATTACK)
    defense = card.get_base_stat_value(StatType.DEFENSE)
    mov = card.get_base_stat_value(StatType.MOVEMENT)
    init = card.initiative

    # Primary action indicator
    action_str = ""
    if card.primary_action:
        action_str = card.primary_action.value[0]  # First letter

    # Build stat string
    stats = []
    if atk > 0:
        stats.append(f"Atk:{atk}")
    if defense > 0:
        stats.append(f"Def:{defense}")
    if mov > 0:
        stats.append(f"Mov:{mov}")
    stats.append(f"Init:{init}")

    stat_str = " ".join(stats)

    return f"[{index}] {color_code}{card.name:<20}{Colors.RESET} ({color_name}-{tier_name}) {action_str} | {stat_str}"


def render_hand(hero: Hero) -> str:
    """Render a hero's hand."""
    lines = []

    team_color = Colors.RED if hero.team == TeamColor.RED else Colors.BLUE
    lines.append(
        f"\n{team_color}{Colors.BOLD}=== {hero.name} ({hero.team.value}) - Level {hero.level} - {hero.gold} Gold ==={Colors.RESET}"
    )

    if not hero.hand:
        lines.append(f"  {Colors.DIM}(No cards in hand){Colors.RESET}")
    else:
        for i, card in enumerate(hero.hand, 1):
            lines.append(f"  {format_card(card, i)}")

    # Show played cards if any
    if hero.current_turn_card:
        lines.append(
            f"\n  {Colors.DIM}Current card: {hero.current_turn_card.name}{Colors.RESET}"
        )

    if hero.played_cards:
        resolved = [c.name for c in hero.played_cards]
        lines.append(f"  {Colors.DIM}Resolved: {', '.join(resolved)}{Colors.RESET}")

    return "\n".join(lines)


# =============================================================================
# Planning Phase Handler
# =============================================================================


def handle_planning_phase(state: GameState) -> None:
    """Handle card selection for all heroes during planning phase."""
    print(f"\n{Colors.GREEN}{Colors.BOLD}=== PLANNING PHASE ==={Colors.RESET}")
    print(f"{Colors.DIM}Each hero must select a card to play.{Colors.RESET}\n")

    # Get all heroes
    all_heroes: List[Hero] = []
    for team in state.teams.values():
        all_heroes.extend(team.heroes)

    for hero in all_heroes:
        # Check if already committed
        if hero.id in state.pending_inputs:
            continue

        print(render_hand(hero))

        if not hero.hand:
            print(f"\n{Colors.YELLOW}{hero.name} has no cards - passing.{Colors.RESET}")
            pass_turn(state, HeroID(hero.id))
            continue

        # Get card selection
        choice = get_input(
            f"Select card for {hero.name} (1-{len(hero.hand)})",
            valid_range=range(1, len(hero.hand) + 1),
        )

        selected_card = hero.hand[int(choice) - 1]
        commit_card(state, HeroID(hero.id), selected_card)

        # Log the card commit
        if game_logger:
            game_logger.log_card_commit(hero.id, selected_card.name)

        print(
            f"{Colors.GREEN}{hero.name} committed {selected_card.name}{Colors.RESET}\n"
        )


# =============================================================================
# Input Request Handlers
# =============================================================================


def handle_action_choice(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action choice (ATTACK, MOVEMENT, SKILL, HOLD, etc.)."""
    hero_id = request.get("player_id")
    hero = state.get_hero(HeroID(hero_id)) if hero_id else None
    options = request.get("options", [])

    if not hero or not hero.current_turn_card:
        return {"choice_id": "HOLD"}

    card = hero.current_turn_card

    print(f"\n{Colors.BOLD}=== {hero.name} - Choose Action ==={Colors.RESET}")
    print(f"Card: {card.name}")

    if not options:
        print(f"  {Colors.DIM}No actions available - defaulting to HOLD{Colors.RESET}")
        return {"choice_id": "HOLD"}

    # Display options from the request
    for i, opt in enumerate(options, 1):
        opt_id = opt.get("id", "?")
        opt_text = opt.get("text", opt_id)
        print(f"  [{i}] {opt_text}")

    choice = get_input("Select action", valid_range=range(1, len(options) + 1))
    selected = options[int(choice) - 1]

    return {"choice_id": selected.get("id")}


def handle_select_unit(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle unit selection from valid candidates."""
    valid_ids = request.get("valid_options", [])
    prompt = request.get("prompt", "Select a unit")
    can_skip = request.get("can_skip", False)

    print(f"\n{Colors.BOLD}=== {prompt} ==={Colors.RESET}")

    if not valid_ids:
        print(f"{Colors.RED}No valid targets!{Colors.RESET}")
        return {"selection": None}

    # Display valid units
    for i, unit_id in enumerate(valid_ids, 1):
        unit = state.get_unit(UnitID(str(unit_id)))
        hex_loc = state.entity_locations.get(str(unit_id))
        hex_str = format_hex(hex_loc) if hex_loc else "?"

        if isinstance(unit, Hero):
            print(
                f"  [{i}] {Colors.BOLD}{unit.name}{Colors.RESET} ({unit.team.value}) @ {hex_str}"
            )
        elif isinstance(unit, Minion):
            print(f"  [{i}] {unit.type.value} Minion ({unit.team.value}) @ {hex_str}")
        else:
            print(f"  [{i}] {unit_id} @ {hex_str}")

    # Check if optional (can skip)
    if can_skip:
        print(f"  [0] {Colors.DIM}Skip (optional){Colors.RESET}")
        valid_range = range(0, len(valid_ids) + 1)
    else:
        valid_range = range(1, len(valid_ids) + 1)

    choice = get_input("Select", valid_range=valid_range)

    if int(choice) == 0:
        return {"selection": "SKIP"}

    return {"selection": valid_ids[int(choice) - 1]}


def handle_select_hex(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle hex selection from valid candidates."""
    valid_hexes = request.get("valid_options", [])
    prompt = request.get("prompt", "Select a hex")
    can_skip = request.get("can_skip", False)

    print(f"\n{Colors.BOLD}=== {prompt} ==={Colors.RESET}")

    if not valid_hexes:
        print(f"{Colors.RED}No valid hexes!{Colors.RESET}")
        return {"selection": None}

    # Display valid hexes with zone info
    for i, hex_data in enumerate(valid_hexes, 1):
        if isinstance(hex_data, dict):
            h = Hex(q=hex_data["q"], r=hex_data["r"], s=hex_data["s"])
        else:
            h = hex_data

        zone_id = state.board.get_zone_for_hex(h)
        zone_color = ZONE_COLORS.get(zone_id, Colors.WHITE) if zone_id else Colors.WHITE
        print(f"  [{i}] {format_hex(h)} {zone_color}{zone_id or '?'}{Colors.RESET}")

    # Check if optional
    if can_skip:
        print(f"  [0] {Colors.DIM}Skip (optional){Colors.RESET}")
        valid_range = range(0, len(valid_hexes) + 1)
    else:
        valid_range = range(1, len(valid_hexes) + 1)

    choice = get_input("Select", valid_range=valid_range)

    if int(choice) == 0:
        return {"selection": "SKIP"}

    selected = valid_hexes[int(choice) - 1]
    if isinstance(selected, dict):
        return {"selection": selected}
    else:
        return {"selection": {"q": selected.q, "r": selected.r, "s": selected.s}}


def handle_defense_card(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle defense card selection during reaction window."""
    hero_id = request.get("player_id")
    hero = state.get_hero(HeroID(hero_id)) if hero_id else None

    print(
        f"\n{Colors.BOLD}=== {hero.name if hero else hero_id} - DEFEND! ==={Colors.RESET}"
    )

    attacker_id = request.get("attacker_id", "Unknown")
    attack_value = request.get("attack_value", 0)

    print(f"  Attacker: {attacker_id}")
    print(f"  Attack Value: {attack_value}")

    if not hero:
        return {"selected_card_id": None, "pass_defense": True}

    # Find defense cards in hand
    defense_cards: List[Tuple[int, Card]] = []
    idx = 1

    for card in hero.hand:
        # Check if card can defend (has DEFENSE or DEFENSE_SKILL primary)
        if card.primary_action in (ActionType.DEFENSE, ActionType.DEFENSE_SKILL):
            defense_value = card.primary_action_value or 0
            defense_cards.append((idx, card))
            print(f"  [{idx}] {card.name} (Defense: {defense_value})")
            idx += 1

    if not defense_cards:
        print(f"  {Colors.DIM}No defense cards available{Colors.RESET}")
        print(f"  [0] Pass (take the hit)")
        get_input("Press Enter to continue", valid_range=range(0, 1))
        return {"selected_card_id": None, "pass_defense": True}

    print(f"  [0] Pass (don't defend)")

    choice = get_input("Select", valid_range=range(0, len(defense_cards) + 1))

    if int(choice) == 0:
        return {"selected_card_id": None, "pass_defense": True}

    selected_card = defense_cards[int(choice) - 1][1]
    return {"selected_card_id": selected_card.id, "pass_defense": False}


def handle_upgrade_choice(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle upgrade card selection during level-up phase."""
    hero_id = request.get("player_id")
    hero = state.get_hero(HeroID(hero_id)) if hero_id else None

    print(
        f"\n{Colors.BOLD}=== {hero.name if hero else hero_id} - LEVEL UP! ==={Colors.RESET}"
    )

    upgrade_options = request.get("upgrade_options", [])

    if not upgrade_options:
        print(f"  {Colors.DIM}No upgrade options available{Colors.RESET}")
        return {"selected_card_id": None}

    print(f"  Select a card to upgrade to:")

    for i, card_id in enumerate(upgrade_options, 1):
        # Try to find card info
        if hero:
            card = next((c for c in hero.deck if c.id == card_id), None)
            if card:
                print(f"  {format_card(card, i)}")
            else:
                print(f"  [{i}] {card_id}")
        else:
            print(f"  [{i}] {card_id}")

    choice = get_input("Select", valid_range=range(1, len(upgrade_options) + 1))
    return {"selected_card_id": upgrade_options[int(choice) - 1]}


def handle_tie_breaker(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tie-breaker selection."""
    tied_hero_ids = request.get("tied_hero_ids", [])

    print(f"\n{Colors.BOLD}=== TIE BREAKER ==={Colors.RESET}")
    print(f"  The following heroes are tied:")

    for i, hero_id in enumerate(tied_hero_ids, 1):
        hero = state.get_hero(HeroID(hero_id)) if hero_id else None
        if hero:
            team_color = Colors.RED if hero.team == TeamColor.RED else Colors.BLUE
            print(f"  [{i}] {team_color}{hero.name}{Colors.RESET}")
        else:
            print(f"  [{i}] {hero_id}")

    # Tie breaker goes to the team that has tie_breaker_team
    tb_team = state.tie_breaker_team
    print(
        f"\n  Tie-breaker team: {Colors.BOLD}{tb_team.value if tb_team else 'None'}{Colors.RESET}"
    )

    # Auto-resolve based on tie-breaker team
    for hero_id in tied_hero_ids:
        hero = state.get_hero(HeroID(hero_id)) if hero_id else None
        if hero and hero.team == tb_team:
            print(f"  {Colors.GREEN}Winner: {hero.name}{Colors.RESET}")
            return {"winner_id": hero_id}

    # If no tie-breaker team match, just pick first
    return {"winner_id": tied_hero_ids[0] if tied_hero_ids else None}


def handle_confirm_passive(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle passive ability confirmation."""
    prompt = request.get("prompt", "Use passive ability?")
    card_name = request.get("card_name", "Unknown")
    options = request.get("options", ["YES", "NO"])

    print(f"\n{Colors.BOLD}=== PASSIVE ABILITY ==={Colors.RESET}")
    print(f"  {prompt}")
    print(f"  Card: {card_name}")

    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")

    choice = get_input("Select", valid_range=range(1, len(options) + 1))
    return {"choice": options[int(choice) - 1]}


def handle_select_option(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle generic option selection (YES/NO prompts, etc.)."""
    prompt = request.get("prompt", "Select an option")
    options = request.get("options", [])

    print(f"\n{Colors.BOLD}=== {prompt} ==={Colors.RESET}")

    for i, opt in enumerate(options, 1):
        # Options are dicts with 'id' and 'text' keys
        if isinstance(opt, dict):
            print(f"  [{i}] {opt.get('text', opt.get('id', str(opt)))}")
        else:
            print(f"  [{i}] {opt}")

    choice = get_input("Select", valid_range=range(1, len(options) + 1))
    selected = options[int(choice) - 1]

    # Engine expects {"selection": "YES"} or {"selection": "NO"} - just the ID
    if isinstance(selected, dict):
        return {"selection": selected.get("id")}
    return {"selection": selected}


def handle_select_card_or_pass(
    state: GameState, request: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle defense card selection (can pass)."""
    hero_id = request.get("player_id")
    hero = state.get_hero(HeroID(hero_id)) if hero_id else None
    prompt = request.get("prompt", "Select a card or pass")
    # Engine uses "options" key, not "valid_options"
    valid_options = request.get("options", [])

    # Filter out "PASS" from the card list - it's a special option
    valid_cards = [opt for opt in valid_options if opt != "PASS"]

    print(f"\n{Colors.BOLD}=== {prompt} ==={Colors.RESET}")

    if hero and valid_cards:
        for i, card_id in enumerate(valid_cards, 1):
            card = next((c for c in hero.hand if c.id == card_id), None)
            if card:
                # Show defense value if available
                def_val = (
                    card.get_base_stat_value(StatType.DEFENSE)
                    if hasattr(card, "get_base_stat_value")
                    else "?"
                )
                print(f"  [{i}] {card.name} (Defense: {def_val})")
            else:
                print(f"  [{i}] {card_id}")
    elif valid_cards:
        for i, card_id in enumerate(valid_cards, 1):
            print(f"  [{i}] {card_id}")

    print(f"  [0] {Colors.DIM}Pass (no defense){Colors.RESET}")

    choice = get_input("Select", valid_range=range(0, len(valid_cards) + 1))

    if int(choice) == 0:
        # Engine expects {"selected_card_id": "PASS"} not None
        return {"selected_card_id": "PASS"}

    return {"selected_card_id": valid_cards[int(choice) - 1]}


def handle_select_card(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle card selection (e.g., for forced discard)."""
    hero_id = request.get("player_id")
    hero = state.get_hero(HeroID(hero_id)) if hero_id else None
    prompt = request.get("prompt", "Select a card")
    valid_cards = request.get("valid_options", [])
    can_skip = request.get("can_skip", False)

    print(f"\n{Colors.BOLD}=== {prompt} ==={Colors.RESET}")

    if not valid_cards:
        print(f"{Colors.RED}No valid cards!{Colors.RESET}")
        return {"selection": None}

    # Display valid cards with names
    for i, card_id in enumerate(valid_cards, 1):
        if hero:
            card = next((c for c in hero.hand if c.id == card_id), None)
            if card:
                print(f"  [{i}] {card.name}")
            else:
                print(f"  [{i}] {card_id}")
        else:
            print(f"  [{i}] {card_id}")

    if can_skip:
        print(f"  [0] {Colors.DIM}Skip (optional){Colors.RESET}")
        valid_range = range(0, len(valid_cards) + 1)
    else:
        valid_range = range(1, len(valid_cards) + 1)

    choice = get_input("Select", valid_range=valid_range)

    if int(choice) == 0:
        return {"selection": "SKIP"}

    return {"selection": valid_cards[int(choice) - 1]}


def handle_select_number(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle number selection (e.g., choose push distance)."""
    prompt = request.get("prompt", "Select a number")
    valid_numbers = request.get("valid_options", [])
    can_skip = request.get("can_skip", False)

    print(f"\n{Colors.BOLD}=== {prompt} ==={Colors.RESET}")

    if not valid_numbers:
        print(f"{Colors.RED}No valid options!{Colors.RESET}")
        return {"selection": None}

    for i, num in enumerate(valid_numbers, 1):
        print(f"  [{i}] {num}")

    if can_skip:
        print(f"  [0] {Colors.DIM}Skip (optional){Colors.RESET}")
        valid_range = range(0, len(valid_numbers) + 1)
    else:
        valid_range = range(1, len(valid_numbers) + 1)

    choice = get_input("Select", valid_range=valid_range)

    if int(choice) == 0:
        return {"selection": "SKIP"}

    # Return the actual number value (as int for proper comparison in engine)
    return {"selection": int(valid_numbers[int(choice) - 1])}


def handle_choose_actor(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tie-breaker actor selection."""
    tied_hero_ids = request.get("tied_hero_ids", [])

    print(f"\n{Colors.BOLD}=== CHOOSE ACTOR ==={Colors.RESET}")
    print(f"  Select who acts first:")

    for i, hero_id in enumerate(tied_hero_ids, 1):
        hero = state.get_hero(HeroID(hero_id)) if hero_id else None
        if hero:
            team_color = Colors.RED if hero.team == TeamColor.RED else Colors.BLUE
            print(f"  [{i}] {team_color}{hero.name}{Colors.RESET}")
        else:
            print(f"  [{i}] {hero_id}")

    # Auto-resolve based on tie-breaker team
    tb_team = state.tie_breaker_team
    print(
        f"\n  Tie-breaker team: {Colors.BOLD}{tb_team.value if tb_team else 'None'}{Colors.RESET}"
    )

    for hero_id in tied_hero_ids:
        hero = state.get_hero(HeroID(hero_id)) if hero_id else None
        if hero and hero.team == tb_team:
            print(f"  {Colors.GREEN}Winner: {hero.name}{Colors.RESET}")
            return {"selected_hero_id": hero_id}

    return {"selected_hero_id": tied_hero_ids[0] if tied_hero_ids else None}


def handle_choose_respawn(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle respawn hex selection."""
    valid_hexes = request.get("valid_options", [])
    prompt = request.get("prompt", "Select respawn location")

    print(f"\n{Colors.BOLD}=== {prompt} ==={Colors.RESET}")

    for i, hex_data in enumerate(valid_hexes, 1):
        if isinstance(hex_data, dict):
            h = Hex(q=hex_data["q"], r=hex_data["r"], s=hex_data["s"])
        else:
            h = hex_data

        zone_id = state.board.get_zone_for_hex(h)
        zone_color = ZONE_COLORS.get(zone_id, Colors.WHITE) if zone_id else Colors.WHITE
        print(f"  [{i}] {format_hex(h)} {zone_color}{zone_id or '?'}{Colors.RESET}")

    choice = get_input("Select", valid_range=range(1, len(valid_hexes) + 1))

    selected = valid_hexes[int(choice) - 1]
    if isinstance(selected, dict):
        return {"selected_hex": selected}
    else:
        return {"selected_hex": {"q": selected.q, "r": selected.r, "s": selected.s}}


def handle_upgrade_phase(state: GameState, request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle upgrade phase card selection."""
    hero_id = request.get("player_id")
    hero = state.get_hero(HeroID(hero_id)) if hero_id else None
    valid_options = request.get("valid_options", [])

    print(
        f"\n{Colors.BOLD}=== {hero.name if hero else hero_id} - UPGRADE ==={Colors.RESET}"
    )

    if not valid_options:
        print(f"  {Colors.DIM}No upgrade options{Colors.RESET}")
        return {"selected_card_id": None}

    for i, card_id in enumerate(valid_options, 1):
        if hero:
            card = next((c for c in hero.deck if c.id == card_id), None)
            if card:
                print(f"  {format_card(card, i)}")
            else:
                print(f"  [{i}] {card_id}")
        else:
            print(f"  [{i}] {card_id}")

    choice = get_input("Select", valid_range=range(1, len(valid_options) + 1))
    return {"selected_card_id": valid_options[int(choice) - 1]}


def handle_input_request(state: GameState, request: Dict[str, Any]) -> None:
    """Route input request to appropriate handler."""
    request_type = request.get("type", "UNKNOWN")
    player_id = request.get("player_id", "?")
    print(f"\n{Colors.DIM}[Input Request: {request_type}]{Colors.RESET}")

    # Log the input request
    if game_logger:
        game_logger.log_input_request(request)

    # Map request types to handlers
    handlers = {
        "ACTION_CHOICE": handle_action_choice,
        "CHOOSE_ACTION": handle_action_choice,
        "SELECT_UNIT": handle_select_unit,
        "SELECT_UNIT_OR_TOKEN": handle_select_unit,  # Same handler, includes tokens
        "SELECT_TOKEN": handle_select_unit,  # Tokens use same display as units
        "SELECT_HEX": handle_select_hex,
        "SELECT_CARD": handle_select_card,  # Card selection (e.g., forced discard)
        "SELECT_NUMBER": handle_select_number,  # Number selection (e.g., push distance)
        "DEFENSE_CARD": handle_defense_card,
        "SELECT_CARD_OR_PASS": handle_select_card_or_pass,
        "UPGRADE_CHOICE": handle_upgrade_choice,
        "UPGRADE_PHASE": handle_upgrade_phase,
        "TIE_BREAKER": handle_tie_breaker,
        "CHOOSE_ACTOR": handle_choose_actor,
        "CHOOSE_RESPAWN": handle_choose_respawn,
        "CONFIRM_PASSIVE": handle_confirm_passive,
        "SELECT_OPTION": handle_select_option,
    }

    handler = handlers.get(request_type)

    if handler:
        result = handler(state, request)

        # Log player's response
        if game_logger:
            game_logger.log_player_input(request_type, str(player_id), result)

        # Apply result to the pending step
        if state.execution_stack:
            step = state.execution_stack[-1]
            if hasattr(step, "pending_input"):
                step.pending_input = result
    else:
        if game_logger:
            game_logger.log_error(f"Unknown request type: {request_type}")
        print(f"{Colors.RED}Unknown request type: {request_type}{Colors.RESET}")
        print(f"Request: {request}")
        get_input("Press Enter to continue")


# =============================================================================
# Main Game Loop
# =============================================================================


def display_game_state(state: GameState):
    """Display the current game state."""
    print(render_status(state))
    print(render_board(state))


def run_playtest():
    """Main playtest loop."""
    global game_logger

    clear_screen()

    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("=" * 70)
    print("  GUARDS OF ATLANTIS II - Playtest Interface")
    print("  Arien (RED) vs Wasp (BLUE)")
    print("=" * 70)
    print(f"{Colors.RESET}")

    # Initialize logger
    game_logger = init_logger()
    print(f"{Colors.DIM}Logging to: {game_logger.get_log_path()}{Colors.RESET}")

    # Initialize game
    print(f"\n{Colors.DIM}Initializing game...{Colors.RESET}")

    red_heroes = ["Arien"]
    blue_heroes = ["Wasp"]

    try:
        state = GameSetup.create_game(
            map_path="src/goa2/data/maps/forgotten_island.json",
            red_heroes=red_heroes,
            blue_heroes=blue_heroes,
        )
        game_logger.log_game_start(state, red_heroes, blue_heroes)
    except Exception as e:
        game_logger.log_error(f"Failed to initialize game: {e}", e)
        print(f"{Colors.RED}Failed to initialize game: {e}{Colors.RESET}")
        import traceback

        traceback.print_exc()
        return

    print(f"{Colors.GREEN}Game initialized successfully!{Colors.RESET}")
    get_input("Press Enter to start")

    last_phase = None

    # Main game loop
    try:
        while state.phase != GamePhase.GAME_OVER:
            # Log phase changes
            if state.phase != last_phase:
                game_logger.log_phase_change(state)
                last_phase = state.phase

            clear_screen()
            display_game_state(state)

            if state.phase == GamePhase.PLANNING:
                handle_planning_phase(state)
                # After planning, the phase will auto-transition
                continue

            elif state.phase in (
                GamePhase.REVELATION,
                GamePhase.RESOLUTION,
                GamePhase.CLEANUP,
                GamePhase.LEVEL_UP,
            ):
                # Process the resolution stack
                request = process_resolution_stack(state)

                if request:
                    # Need player input
                    display_game_state(state)
                    handle_input_request(state, request)
                elif state.phase == GamePhase.PLANNING:
                    # Round ended, back to planning
                    continue
                else:
                    # Stack empty but not planning - might be waiting for something
                    if not state.execution_stack:
                        # Check if we should transition
                        if (
                            state.phase == GamePhase.RESOLUTION
                            and not state.unresolved_hero_ids
                        ):
                            print(f"\n{Colors.GREEN}Turn complete!{Colors.RESET}")
                            get_input("Press Enter to continue")
                        elif state.phase == GamePhase.CLEANUP:
                            print(f"\n{Colors.YELLOW}Round cleanup...{Colors.RESET}")
                            get_input("Press Enter to continue")

            elif state.phase == GamePhase.SETUP:
                # Should auto-transition to planning
                print(f"{Colors.YELLOW}In SETUP phase, waiting...{Colors.RESET}")
                get_input("Press Enter")

            else:
                game_logger.log_error(f"Unknown phase: {state.phase}")
                print(f"{Colors.RED}Unknown phase: {state.phase}{Colors.RESET}")
                get_input("Press Enter")

    except Exception as e:
        game_logger.log_error(f"Unexpected error: {e}", e)
        game_logger.log_state_snapshot(state)
        raise

    # Game over
    clear_screen()
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}  GAME OVER{Colors.RESET}")
    print(f"{'=' * 70}")

    # Determine winner
    red_team = state.teams.get(TeamColor.RED)
    blue_team = state.teams.get(TeamColor.BLUE)

    winner = None
    red_lives = red_team.life_counters if red_team else 0
    blue_lives = blue_team.life_counters if blue_team else 0

    if red_team and blue_team:
        if red_team.life_counters <= 0:
            winner = "BLUE"
            print(f"\n  {Colors.BLUE}{Colors.BOLD}BLUE TEAM WINS!{Colors.RESET}")
        elif blue_team.life_counters <= 0:
            winner = "RED"
            print(f"\n  {Colors.RED}{Colors.BOLD}RED TEAM WINS!{Colors.RESET}")
        else:
            print(f"\n  {Colors.YELLOW}Draw or undetermined winner{Colors.RESET}")

    # Log game end
    if game_logger:
        game_logger.log_game_end(winner, red_lives, blue_lives)
        print(
            f"\n  {Colors.DIM}Log saved to: {game_logger.get_log_path()}{Colors.RESET}"
        )

    print(f"\n  Final Score:")
    print(f"    {Colors.RED}RED: {red_lives} lives{Colors.RESET}")
    print(f"    {Colors.BLUE}BLUE: {blue_lives} lives{Colors.RESET}")
    print()


if __name__ == "__main__":
    run_playtest()

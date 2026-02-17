"""Per-game logging for server-played games.

Creates one log file (text + JSON) per game, capturing all mutations:
game creation, card commits, pass turns, input requests/responses,
phase changes, events, errors, and game over.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class GameLogger:
    """Structured logger for a single game — writes text + JSON to disk."""

    def __init__(self, game_id: str, log_dir: str = "logs/games") -> None:
        self.game_id = game_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"{game_id}_{timestamp}"
        self.log_file = self.log_dir / f"{prefix}.log"
        self.json_file = self.log_dir / f"{prefix}.json"

        # Python logger — one per game, writes to its own file
        self.logger = logging.getLogger(f"goa2.game.{game_id}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # don't pollute root logger

        fh = logging.FileHandler(self.log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
        )
        self.logger.addHandler(fh)

        # Structured events for JSON export
        self.events: List[Dict[str, Any]] = []
        self._round = 0
        self._turn = 0
        self._phase = ""

        self.logger.info("=" * 60)
        self.logger.info("GAME %s STARTED", game_id)
        self.logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    def log_game_created(
        self,
        red_heroes: List[str],
        blue_heroes: List[str],
        map_name: str,
    ) -> None:
        self.logger.info(
            "Game created: RED=%s, BLUE=%s, map=%s", red_heroes, blue_heroes, map_name
        )
        self._add_event(
            "GAME_CREATED",
            {
                "red_heroes": red_heroes,
                "blue_heroes": blue_heroes,
                "map_name": map_name,
            },
        )

    def log_phase_change(self, phase: str, round_num: int, turn: int) -> None:
        if phase == self._phase and round_num == self._round and turn == self._turn:
            return  # skip duplicate
        self._phase = phase
        self._round = round_num
        self._turn = turn
        self.logger.info("Phase: %s (Round %d, Turn %d)", phase, round_num, turn)
        self._add_event(
            "PHASE_CHANGE", {"phase": phase, "round": round_num, "turn": turn}
        )

    def log_card_commit(self, hero_id: str, card_id: str) -> None:
        self.logger.info("COMMIT: %s -> %s", hero_id, card_id)
        self._add_event("CARD_COMMIT", {"hero_id": hero_id, "card_id": card_id})

    def log_pass_turn(self, hero_id: str) -> None:
        self.logger.info("PASS: %s", hero_id)
        self._add_event("PASS_TURN", {"hero_id": hero_id})

    def log_input_request(self, request: Dict[str, Any]) -> None:
        req_type = request.get("type", "UNKNOWN")
        player_id = request.get("player_id", "?")
        prompt = request.get("prompt", "")
        self.logger.info("INPUT_REQUEST: %s for %s", req_type, player_id)
        self.logger.debug("  Prompt: %s", prompt)

        # Summarize options for the log
        options = request.get("options", request.get("valid_options", request.get("valid_hexes", [])))
        options_count = len(options) if isinstance(options, list) else 0

        self._add_event(
            "INPUT_REQUEST",
            {
                "type": req_type,
                "player_id": player_id,
                "prompt": prompt,
                "options_count": options_count,
            },
        )

    def log_input_response(
        self, hero_id: str, selection: Any
    ) -> None:
        safe = str(selection)[:200]
        self.logger.info("INPUT_RESPONSE: %s -> %s", hero_id, safe)
        self._add_event(
            "INPUT_RESPONSE",
            {"hero_id": hero_id, "selection": safe},
        )

    def log_events(self, events: List[Dict[str, Any]]) -> None:
        """Log game events emitted by the engine (movement, combat, etc.)."""
        for ev in events:
            event_type = ev.get("event_type", "UNKNOWN")
            actor = ev.get("actor_id", "")
            target = ev.get("target_id", "")
            parts = [f"EVENT: {event_type}"]
            if actor:
                parts.append(f"actor={actor}")
            if target:
                parts.append(f"target={target}")
            from_hex = ev.get("from_hex")
            to_hex = ev.get("to_hex")
            if from_hex:
                parts.append(f"from={from_hex}")
            if to_hex:
                parts.append(f"to={to_hex}")
            self.logger.info(" | ".join(parts))
            self._add_event("GAME_EVENT", ev)

    def log_advance(self, result_type: str, phase: str) -> None:
        self.logger.debug("ADVANCE: result=%s, phase=%s", result_type, phase)

    def log_error(self, error: str, hero_id: Optional[str] = None) -> None:
        ctx = f" (player={hero_id})" if hero_id else ""
        self.logger.error("ERROR%s: %s", ctx, error)
        self._add_event("ERROR", {"message": error, "hero_id": hero_id})

    def log_game_over(self, winner: Optional[str]) -> None:
        self.logger.info("=" * 60)
        self.logger.info("GAME OVER - Winner: %s", winner or "None")
        self.logger.info("=" * 60)
        self._add_event("GAME_OVER", {"winner": winner})
        self._save_json()

    def log_ws_connect(self, hero_id: Optional[str], is_spectator: bool) -> None:
        who = "spectator" if is_spectator else hero_id
        self.logger.info("WS_CONNECT: %s", who)
        self._add_event("WS_CONNECT", {"hero_id": hero_id, "is_spectator": is_spectator})

    def log_ws_disconnect(self, hero_id: Optional[str], is_spectator: bool) -> None:
        who = "spectator" if is_spectator else hero_id
        self.logger.info("WS_DISCONNECT: %s", who)
        self._add_event("WS_DISCONNECT", {"hero_id": hero_id, "is_spectator": is_spectator})

    # ------------------------------------------------------------------
    # Convenience: log a full SessionResult
    # ------------------------------------------------------------------

    def log_result(self, result_type: str, phase: str, events: List[Dict[str, Any]],
                   input_request: Optional[Dict[str, Any]], winner: Optional[str]) -> None:
        """Log a complete SessionResult in one call."""
        self.log_phase_change(phase, self._round, self._turn)
        if events:
            self.log_events(events)
        if input_request:
            self.log_input_request(input_request)
        self.log_advance(result_type, phase)
        if winner:
            self.log_game_over(winner)

    def flush_json(self) -> None:
        """Save current events to JSON (call on server shutdown or periodically)."""
        self._save_json()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _add_event(self, event_type: str, data: Dict[str, Any]) -> None:
        self.events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "round": self._round,
                "turn": self._turn,
                "phase": self._phase,
                "type": event_type,
                "data": data,
            }
        )

    def _save_json(self) -> None:
        try:
            with open(self.json_file, "w") as f:
                json.dump(self.events, f, indent=2, default=str)
            self.logger.info("JSON log saved to: %s", self.json_file)
        except Exception as e:
            self.logger.error("Failed to save JSON log: %s", e)

    def close(self) -> None:
        """Clean up handlers."""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)


def create_game_logger(game_id: str, log_dir: Optional[str] = None) -> GameLogger:
    """Create a GameLogger, using GOA2_LOG_DIR env var or default."""
    directory = log_dir or os.environ.get("GOA2_LOG_DIR", "logs/games")
    return GameLogger(game_id, log_dir=directory)

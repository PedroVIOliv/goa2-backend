"""Tests for Phase 3: GameEvent model and GameEventType enum."""

from goa2.domain.events import GameEvent, GameEventType, _hex_dict
from goa2.domain.hex import Hex


class TestGameEventType:
    def test_all_types_are_strings(self):
        for t in GameEventType:
            assert isinstance(t.value, str)

    def test_movement_types(self):
        assert GameEventType.UNIT_MOVED == "UNIT_MOVED"
        assert GameEventType.UNIT_PLACED == "UNIT_PLACED"
        assert GameEventType.UNIT_PUSHED == "UNIT_PUSHED"
        assert GameEventType.UNITS_SWAPPED == "UNITS_SWAPPED"

    def test_combat_types(self):
        assert GameEventType.COMBAT_RESOLVED == "COMBAT_RESOLVED"
        assert GameEventType.UNIT_DEFEATED == "UNIT_DEFEATED"
        assert GameEventType.UNIT_REMOVED == "UNIT_REMOVED"

    def test_turn_flow_types(self):
        assert GameEventType.TURN_ENDED == "TURN_ENDED"
        assert GameEventType.GAME_OVER == "GAME_OVER"


class TestHexDict:
    def test_none_returns_none(self):
        assert _hex_dict(None) is None

    def test_hex_returns_dict(self):
        h = Hex(q=1, r=-1, s=0)
        assert _hex_dict(h) == {"q": 1, "r": -1, "s": 0}

    def test_origin_hex(self):
        h = Hex(q=0, r=0, s=0)
        assert _hex_dict(h) == {"q": 0, "r": 0, "s": 0}


class TestGameEvent:
    def test_minimal_construction(self):
        e = GameEvent(event_type=GameEventType.TURN_ENDED)
        assert e.event_type == GameEventType.TURN_ENDED
        assert e.actor_id is None
        assert e.target_id is None
        assert e.from_hex is None
        assert e.to_hex is None
        assert e.metadata == {}

    def test_full_construction(self):
        e = GameEvent(
            event_type=GameEventType.UNIT_MOVED,
            actor_id="hero_arien",
            from_hex={"q": 0, "r": 0, "s": 0},
            to_hex={"q": 1, "r": -1, "s": 0},
            metadata={"range": 2},
        )
        assert e.actor_id == "hero_arien"
        assert e.from_hex == {"q": 0, "r": 0, "s": 0}
        assert e.to_hex == {"q": 1, "r": -1, "s": 0}
        assert e.metadata["range"] == 2

    def test_serialization(self):
        e = GameEvent(
            event_type=GameEventType.GOLD_GAINED,
            actor_id="hero_wasp",
            metadata={"amount": 3, "reason": "kill"},
        )
        d = e.model_dump()
        assert d["event_type"] == "GOLD_GAINED"
        assert d["actor_id"] == "hero_wasp"
        assert d["metadata"]["amount"] == 3

    def test_metadata_defaults_to_empty(self):
        e1 = GameEvent(event_type=GameEventType.TURN_ENDED)
        e2 = GameEvent(event_type=GameEventType.TURN_ENDED)
        # Ensure separate dict instances
        e1.metadata["x"] = 1
        assert "x" not in e2.metadata

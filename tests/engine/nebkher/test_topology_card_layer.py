"""Topology card layer (NebKher P2 — Crack in Reality / Shift Reality).

The TopologyService itself pre-exists (engine/topology.py + tests). This
covers the card-effect layer:
- CreateEffectStep passes split_axis / split_value / isolated_hex through
  and advertises the geometry in the EFFECT_CREATED event (client contract).
- S6: Shift Reality's isolation follows NebKher's CURRENT position (bound
  to the unit, not the cast-time hex); the stored isolated_hex is only a
  fallback when the source has no board position.
- THIS_TURN lifecycle: the split disappears at end of turn.
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.models import GamePhase, Hero, Team, TeamColor
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.phases import end_turn
from goa2.engine.steps import CreateEffectStep
from goa2.engine.topology import are_connected


def _state() -> GameState:
    """A 5-wide, 3-tall board. hero_source sits on the q=2 column."""
    board = Board()
    hexes = {Hex(q=q, r=r, s=-q - r) for q in range(5) for r in range(3)}
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

    source = Hero(id="hero_source", name="Source", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="hero_enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[source], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.phase = GamePhase.RESOLUTION
    state.place_entity("hero_source", Hex(q=2, r=0, s=-2))
    state.place_entity("hero_enemy", Hex(q=4, r=0, s=-4))
    state.current_actor_id = "hero_source"
    return state


def _create_split(state: GameState, effect_type: EffectType, **fields):
    push_steps(
        state,
        [
            CreateEffectStep(
                effect_type=effect_type,
                scope=EffectScope(shape=Shape.GLOBAL, origin_id="hero_source"),
                duration=DurationType.THIS_TURN,
                is_active=True,
                use_context_card=False,
                **fields,
            )
        ],
    )
    return process_stack(state)


def test_create_effect_step_passes_topology_fields_through() -> None:
    state = _state()
    result = _create_split(state, EffectType.TOPOLOGY_SPLIT, split_axis="q", split_value=2)

    effect = next(e for e in state.active_effects if e.effect_type == EffectType.TOPOLOGY_SPLIT)
    assert effect.split_axis == "q"
    assert effect.split_value == 2

    created = next(e for e in result.events if e.event_type == GameEventType.EFFECT_CREATED)
    assert created.metadata.get("split_axis") == "q"
    assert created.metadata.get("split_value") == 2

    # The split works: q=1 and q=3 are on opposite sides.
    assert not are_connected(Hex(q=1, r=0, s=-1), Hex(q=3, r=0, s=-3), state)
    # The line itself bridges.
    assert are_connected(Hex(q=1, r=0, s=-1), Hex(q=2, r=0, s=-2), state)


def test_isolation_follows_source_current_position() -> None:
    """S6: after NebKher moves, his NEW hex is isolated, the cast hex is not."""
    state = _state()
    cast_hex = Hex(q=2, r=0, s=-2)
    _create_split(
        state,
        EffectType.TOPOLOGY_ISOLATION,
        split_axis="q",
        split_value=2,
        isolated_hex=cast_hex,
    )

    off_line = Hex(q=1, r=0, s=-1)  # NEGATIVE side
    # Initially the source's hex is isolated from off-line hexes.
    assert not are_connected(off_line, cast_hex, state)

    # Source moves along the line to (2,1,-3).
    new_hex = Hex(q=2, r=1, s=-3)
    state.place_entity("hero_source", new_hex)

    # Isolation follows the unit: new hex isolated, old hex reachable again.
    assert not are_connected(off_line, new_hex, state)
    assert are_connected(off_line, cast_hex, state)


def test_split_expires_at_end_of_turn() -> None:
    state = _state()
    _create_split(state, EffectType.TOPOLOGY_SPLIT, split_axis="q", split_value=2)
    assert not are_connected(Hex(q=1, r=0, s=-1), Hex(q=3, r=0, s=-3), state)

    end_turn(state)
    process_stack(state)

    assert are_connected(Hex(q=1, r=0, s=-1), Hex(q=3, r=0, s=-3), state)

"""Cross-cutting guards: non-combat defeat, stable IDs, remove-all."""

from goa2.domain.hex import Hex
from goa2.domain.models.enums import TargetType
from goa2.domain.state import GameState
from goa2.engine.filters_units import UnitTypeFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import DefeatUnitStep
from goa2.engine.steps.pieces import RemoveHeroPieceStep
from goa2.engine.steps.selection import SelectStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state(n_pieces: int = 2) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1)]
    for i in range(n_pieces):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_noncombat_piece_defeat_is_full_hero_defeat():
    state = _state()
    push_steps(state, [DefeatUnitStep(victim_id=piece_id("hero_razzle", 1), killer_id=None)])
    process_stack(state)

    assert not state.has_board_presence("hero_razzle")
    assert "hero_razzle" in state.heroes_defeated_this_round


def test_remove_all_is_not_defeat_and_turn_is_skipped():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 1)
    push_steps(
        state,
        [RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_any", min_remaining=0)],
    )

    result = process_stack(state)
    assert result.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 1)}
    result = process_stack(state)
    assert result.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    process_stack(state)

    assert not state.has_board_presence("hero_razzle")
    assert "hero_razzle" not in state.heroes_defeated_this_round

    from goa2.engine.steps.cards import ResolveCardStep

    push_steps(state, [ResolveCardStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is None


def test_persistent_binding_on_piece_id_is_stable():
    state = _state()
    bound_id = piece_id("hero_razzle", 2)
    before = state.entity_locations[bound_id]

    state.acting_piece_id = piece_id("hero_razzle", 1)

    assert state.entity_locations[bound_id] == before
    assert state.get_unit(bound_id).id == bound_id


def test_unit_type_hero_filter_matches_hero_pieces():
    state = _state()
    push_steps(
        state,
        [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select hero piece",
                output_key="target",
                filters=[UnitTypeFilter(unit_type="HERO")],
            )
        ],
    )

    result = process_stack(state)
    assert result.input_request is not None
    option_ids = {o.id for o in result.input_request.options}
    assert piece_id("hero_razzle", 2) in option_ids
    assert "hero_razzle" not in option_ids

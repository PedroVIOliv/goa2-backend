import pytest

import goa2.data.heroes.misa
import goa2.scripts.misa_effects  # noqa: F401 - register effects
from goa2.domain.hex import Hex
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps

from ..builders import EffectScenarioBuilder, hero_card


def _hex_distance(a: Hex, b: Hex) -> int:
    return (abs(a.q - b.q) + abs(a.r - b.r) + abs(a.s - b.s)) // 2


def _hexes_within(radius: int) -> list[tuple[int, int, int]]:
    cells = []
    for q in range(-radius, radius + 1):
        for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1):
            cells.append((q, r, -q - r))
    return cells


def _push_option_hexes(request) -> list[Hex]:
    assert request is not None
    hexes = []
    for option in request.options:
        meta = getattr(option, "metadata", None)
        assert meta and "raw" in meta, f"hex option missing raw metadata: {option!r}"
        hexes.append(meta["raw"])
    return hexes


@pytest.mark.effect_flow
def test_thunder_shot_push_only_offers_hexes_adjacent_to_target() -> None:
    """thunder_shot's "move it 1 space" push must offer only hexes adjacent to
    the target (and farther from Misa) — never hexes 2+ spaces from the target.

    The post-attack SelectStep is driven in isolation: defender_id is seeded as
    the attack would, and CheckDistanceStep computes ts_can_push for real.
    """
    target = Hex(q=2, r=0, s=-2)

    state = (
        EffectScenarioBuilder()
        .with_hexes(_hexes_within(4))
        .red_hero("hero_misa", at=(0, 0, 0))
        .blue_hero("hero_enemy", at=(2, 0, -2))
        .with_actor("hero_misa")
        .build()
    )

    hero = state.get_hero("hero_misa")
    card = hero_card("Misa", "thunder_shot")
    effect = CardEffectRegistry.get("thunder_shot")
    steps = effect.get_steps(state, hero, card)

    # Skip the attack itself; seed its result (the chosen target) and let
    # CheckDistanceStep + the push SelectStep run for real.
    state.execution_context["defender_id"] = "hero_enemy"
    push_steps(state, steps[1:])

    result = process_stack(state)

    assert result.input_request is not None, "expected a push-destination prompt"
    assert result.input_request.request_type.value == "SELECT_HEX"

    offered = _push_option_hexes(result.input_request)
    assert offered, "push selector offered no hexes"

    non_adjacent = [h for h in offered if _hex_distance(h, target) != 1]
    assert not non_adjacent, (
        "thunder_shot push offered hexes that are not adjacent to the target "
        f"(>1 space away): {non_adjacent}"
    )

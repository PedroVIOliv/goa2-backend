"""Repeats and forced actions run as full actions: repeat prevention, items, and
before/after-action passives all apply (rulebook p.10 "Repeat")."""

import copy

import pytest

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import StatType
from goa2.domain.models.effect import AffectsFilter, DurationType, EffectScope, EffectType, Shape
from goa2.domain.rules_version import CURRENT_RULES_VERSION
from goa2.engine.handler import process_stack
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.effects import CreateEffectStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if -radius <= -q - r <= radius
    ]


def _give_ultimate(state, hero_id: str, hero_name: str) -> None:
    hero = state.get_hero(hero_id)
    template = HeroRegistry.get(hero_name)
    assert hero is not None and template is not None and template.ultimate_card is not None
    hero.level = 8
    hero.ultimate_card = copy.deepcopy(template.ultimate_card)


def _enfeeble(state, origin_id: str = "hero_dodger") -> None:
    """Enfeeblement's repeat clause, as if Dodger resolved it earlier this turn."""
    actor = state.current_actor_id
    state.current_actor_id = origin_id
    CreateEffectStep(
        effect_type=EffectType.REPEAT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=10,
            origin_id=origin_id,
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    ).resolve(state, {})
    state.current_actor_id = actor


def _drive(state, first_choices: list) -> list[tuple[str, str]]:
    """Answer scripted choices first, then decline/pass/pick-first until done.

    Returns every (request_type, prompt) seen.
    """
    seen: list[tuple[str, str]] = []
    scripted = list(first_choices)
    for _ in range(60):
        result = process_stack(state)
        req = result.input_request
        if req is None:
            return seen
        seen.append((req.request_type.value, req.prompt))
        if scripted:
            answer = scripted.pop(0)
        elif req.request_type == InputRequestType.CONFIRM_PASSIVE:
            answer = "NO"
        elif req.request_type == InputRequestType.SELECT_CARD_OR_PASS:
            answer = "PASS"
        elif req.request_type == InputRequestType.SELECT_OPTION and any(
            o.id == "NO" for o in req.options
        ):
            answer = "NO"
        elif req.can_skip:
            answer = "SKIP"
        else:
            opt = req.options[0]
            answer = opt.metadata["hex"] if opt.metadata and "hex" in opt.metadata else opt.id
        state.execution_stack[-1].pending_input = {"selection": answer}
    raise AssertionError(f"did not finish; prompts: {seen}")


# --- #3 Enfeeblement vs hand-built repeats -----------------------------------


@pytest.mark.effect_flow
def test_enfeebled_silverarrow_does_not_repeat_rain_of_arrows() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero(
            "hero_silverarrow",
            at=(0, 0, 0),
            current_card=hero_card("Silverarrow", "rain_of_arrows"),
        )
        .blue_hero("hero_a", at=(3, 0, -3))
        .blue_hero("hero_b", at=(-3, 0, 3))
        .blue_hero("hero_dodger", at=(1, 0, -1))
        .with_actor("hero_silverarrow")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    _enfeeble(state)

    run_card(state, "hero_silverarrow")
    seen = _drive(state, ["ATTACK", "hero_a"])

    assert not any("different enemy hero" in p for _, p in seen), seen


@pytest.mark.effect_flow
def test_enfeebled_razzle_does_not_repeat_spectacle() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(4))
        .red_hero("hero_razzle", at=(0, 0, 0), current_card=hero_card("Razzle", "spectacle"))
        .blue_minion("minion_a", at=(1, 0, -1))
        .blue_minion("minion_b", at=(0, 2, -2))
        .blue_hero("hero_dodger", at=(-2, 0, 2))
        .with_actor("hero_razzle")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=0, r=1, s=-1))
    _enfeeble(state)

    run_card(state, "hero_razzle")
    seen = _drive(state, ["SKILL", piece_id("hero_razzle", 1), "minion_a"])

    assert not any("repeat" in p.lower() for _, p in seen), seen


@pytest.mark.effect_flow
def test_enfeebled_min_is_not_offered_flurry_of_blows() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero("hero_min", at=(0, 0, 0), current_card=hero_card("Min", "crane_stance"))
        .blue_minion("minion_a", at=(1, 0, -1))
        .blue_minion("minion_b", at=(-1, 0, 1))
        .blue_hero("hero_dodger", at=(0, 3, -3))
        .with_actor("hero_min")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    _give_ultimate(state, "hero_min", "Min")
    _enfeeble(state)

    run_card(state, "hero_min")
    seen = _drive(state, ["ATTACK", "minion_a"])

    assert not any("Flurry" in p for _, p in seen), seen


@pytest.mark.effect_flow
def test_enfeebled_tigerclaw_is_not_offered_cloak_and_daggers() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero(
            "hero_tigerclaw", at=(0, 0, 0), current_card=hero_card("Tigerclaw", "blink_strike")
        )
        .blue_hero("hero_dodger", at=(0, 3, -3))
        .with_actor("hero_tigerclaw")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    _give_ultimate(state, "hero_tigerclaw", "Tigerclaw")
    _enfeeble(state)

    run_card(state, "hero_tigerclaw")
    seen = _drive(state, ["MOVEMENT"])

    assert not any("Cloak and Daggers" in p for _, p in seen), seen


# --- #2 passives on Swift Justice's forced move --------------------------------


@pytest.mark.effect_flow
def test_swift_justice_forced_move_offers_wild_hunt() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(8)])
        .red_hero("hero_whisper", at=(0, 0, 0), current_card=hero_card("Whisper", "swift_justice"))
        .blue_hero("hero_defender", at=(2, 0, -2))
        .with_actor("hero_whisper")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    state.get_hero("hero_defender").hand.append(hero_card("Garrus", "terrify"))
    _give_ultimate(state, "hero_defender", "Silverarrow")

    run_card(state, "hero_whisper")
    seen = _drive(state, ["ATTACK", 1, "hero_defender", "terrify"])

    # The first offer is the defense action's own BEFORE_ACTION; the forced
    # move is a second action and needs its own offer before its hex choice.
    prompts = [p for _, p in seen]
    forced_hex = next(i for i, (t, _) in enumerate(seen) if t == "SELECT_HEX")
    assert sum("Wild Hunt" in p for p in prompts[:forced_hex]) == 2, seen


@pytest.mark.effect_flow
def test_swift_justice_forced_move_offers_cloak_and_daggers() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(8)])
        .red_hero("hero_whisper", at=(0, 0, 0), current_card=hero_card("Whisper", "swift_justice"))
        .blue_hero("hero_tigerclaw", at=(2, 0, -2))
        .with_actor("hero_whisper")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    state.get_hero("hero_tigerclaw").hand.append(hero_card("Tigerclaw", "blink_strike"))
    _give_ultimate(state, "hero_tigerclaw", "Tigerclaw")
    state.get_hero("hero_tigerclaw").items[StatType.DEFENSE] = 1  # survive the hit

    run_card(state, "hero_whisper")
    seen = _drive(state, ["ATTACK", 1, "hero_tigerclaw", "blink_strike"])

    forced_hex = next(i for i, (t, _) in enumerate(seen) if t == "SELECT_HEX")
    assert any("Cloak and Daggers" in p for _, p in seen[forced_hex + 1 :]), seen


@pytest.mark.effect_flow
def test_cloak_and_daggers_repeat_of_forced_move_stays_straight_and_full() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(5))
        .red_hero("hero_whisper", at=(0, 0, 0), current_card=hero_card("Whisper", "swift_justice"))
        .blue_hero("hero_tigerclaw", at=(2, 0, -2))
        .with_actor("hero_whisper")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    tigerclaw = state.get_hero("hero_tigerclaw")
    tigerclaw.hand.append(hero_card("Tigerclaw", "blink_strike"))
    _give_ultimate(state, "hero_tigerclaw", "Tigerclaw")
    tigerclaw.items[StatType.DEFENSE] = 1
    tigerclaw.items[StatType.MOVEMENT] = 1

    run_card(state, "hero_whisper")
    scripted = ["ATTACK", 1, "hero_tigerclaw", "blink_strike"]
    hex_prompts: list[tuple[Hex, list[Hex]]] = []
    for _ in range(40):
        req = process_stack(state).input_request
        if req is None:
            break
        if req.request_type == InputRequestType.SELECT_HEX:
            here = state.entity_locations["hero_tigerclaw"]
            hex_prompts.append((here, [Hex(**o.metadata["hex"]) for o in req.options]))
        if scripted:
            answer = scripted.pop(0)
        elif req.request_type == InputRequestType.CONFIRM_PASSIVE:
            answer = "YES" if "Cloak and Daggers" in req.prompt else "NO"
        elif req.request_type == InputRequestType.SELECT_CARD_OR_PASS:
            answer = "PASS"
        else:
            opt = req.options[0]
            answer = opt.metadata["hex"] if opt.metadata and "hex" in opt.metadata else opt.id
        state.execution_stack[-1].pending_input = {"selection": answer}

    assert len(hex_prompts) == 2, hex_prompts
    here, repeat_options = hex_prompts[1]
    assert repeat_options
    for h in repeat_options:
        assert here.distance(h) == 2, (here, h)
        assert h.q == here.q or h.r == here.r or h.s == here.s, (here, h)


# --- #4 Wild Hunt before each Rain of Arrows repeat -----------------------------


@pytest.mark.effect_flow
def test_wild_hunt_offered_before_rain_of_arrows_repeat() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero(
            "hero_silverarrow",
            at=(0, 0, 0),
            current_card=hero_card("Silverarrow", "rain_of_arrows"),
        )
        .blue_hero("hero_a", at=(3, 0, -3))
        .blue_hero("hero_b", at=(-3, 0, 3))
        .with_actor("hero_silverarrow")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    _give_ultimate(state, "hero_silverarrow", "Silverarrow")

    run_card(state, "hero_silverarrow")
    seen = _drive(state, ["ATTACK"])

    prompts = [p for _, p in seen]
    second = next(i for i, p in enumerate(prompts) if "different enemy hero" in p)
    assert any("Wild Hunt" in p for p in prompts[:second]), seen
    first_hunt = next(i for i, p in enumerate(prompts) if "Wild Hunt" in p)
    assert any("Wild Hunt" in p for p in prompts[first_hunt + 1 : second]), seen


# --- Bain -----------------------------------------------------------


@pytest.mark.effect_flow
def test_enfeebled_bain_is_not_offered_the_guess_repeat() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero("hero_bain", at=(0, 0, 0), current_card=hero_card("Bain", "were_not_done_yet"))
        .blue_hero("hero_dodger", at=(1, 0, -1))
        .with_actor("hero_bain")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    dodger = state.get_hero("hero_dodger")
    dodger.hand.extend([hero_card("Whisper", "blood_fury"), hero_card("Garrus", "terrify")])
    _enfeeble(state)

    run_card(state, "hero_bain")
    # Dodger hides the RED card; Bain guesses BLUE (wrong).
    seen = _drive(state, ["SKILL", "hero_dodger", "blood_fury", "BLUE"])

    assert not any("consolation" in p.lower() for _, p in seen), seen
    assert state.get_hero("hero_bain").gold == 2


@pytest.mark.effect_flow
def test_enfeebled_bain_does_not_repeat_another_one_at_end_of_turn() -> None:
    from goa2.domain.models import CardState
    from goa2.engine.phases import end_turn

    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero("hero_bain", at=(0, 0, 0), current_card=hero_card("Bain", "another_one"))
        .red_hero("hero_ally", at=(0, 1, -1))
        .blue_hero("hero_dodger", at=(1, 0, -1))
        .with_actor("hero_bain")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    for hero_id, card in (
        ("hero_ally", ("Garrus", "terrify")),
        ("hero_bain", ("Whisper", "blood_fury")),
    ):
        discarded = hero_card(*card)
        discarded.state = CardState.DISCARD
        state.get_hero(hero_id).discard_pile.append(discarded)
    _enfeeble(state)

    run_card(state, "hero_bain")
    _drive(state, ["SKILL"])  # decline the first retrieve; the repeat is what's under test
    end_turn(state)
    seen = _drive(state, [])

    assert not any(t == "SELECT_UNIT" for t, _ in seen), seen


@pytest.mark.effect_flow
def test_cloak_and_daggers_repeats_a_basic_movement() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero(
            "hero_tigerclaw", at=(0, 0, 0), current_card=hero_card("Tigerclaw", "blink_strike")
        )
        .with_actor("hero_tigerclaw")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    _give_ultimate(state, "hero_tigerclaw", "Tigerclaw")

    run = run_card(state, "hero_tigerclaw")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=0, s=-1))
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2)).finish()

    assert state.entity_locations["hero_tigerclaw"] == Hex(q=2, r=0, s=-2)


# --- a repeat is a full action that cannot itself be repeated ---------------------


def _cleave_state(hero_id: str, hero_name: str):
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(3))
        .red_hero(hero_id, at=(0, 0, 0), current_card=hero_card("Xargatha", "cleave"))
        .blue_hero("hero_a", at=(1, 0, -1))
        .blue_hero("hero_b", at=(0, 1, -1))
        .with_actor(hero_id)
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    _give_ultimate(state, hero_id, hero_name)
    for target in ("hero_a", "hero_b"):
        state.get_hero(target).items[StatType.DEFENSE] = 9  # survive both hits
    return state


@pytest.mark.effect_flow
def test_repeat_fires_after_basic_action_passives() -> None:
    state = _cleave_state("hero_swift", "Swift")

    run_card(state, "hero_swift")
    seen = _drive(state, ["ATTACK", "hero_a", "PASS", "YES", "hero_b"])

    # Once after the repeat, once after the card's own action.
    assert sum("Bullet Time" in p for _, p in seen) == 2, seen


@pytest.mark.effect_flow
def test_repeated_action_cannot_be_repeated() -> None:
    state = _cleave_state("hero_tigerclaw", "Tigerclaw")

    run_card(state, "hero_tigerclaw")
    seen = _drive(state, ["ATTACK", "hero_a", "PASS", "YES", "hero_b"])

    # Offered after the card's whole action, never after the repeat inside it.
    assert sum("Cloak and Daggers" in p for _, p in seen) == 1, seen


@pytest.mark.effect_flow
def test_bullet_time_and_bounce_repeats_do_not_chain_forever() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_disk(6))
        .red_hero("hero_swift", at=(0, 0, 0), current_card=hero_card("Swift", "bounce"))
        .with_actor("hero_swift")
        .build()
    )
    state.rules_version = CURRENT_RULES_VERSION
    _give_ultimate(state, "hero_swift", "Swift")

    run_card(state, "hero_swift")
    bullet_time_offers = 0
    for _ in range(80):
        req = process_stack(state).input_request
        if req is None:
            break
        if req.request_type == InputRequestType.CHOOSE_ACTION:
            answer = "SKILL"
        elif req.request_type == InputRequestType.CONFIRM_PASSIVE:
            bullet_time_offers += "Bullet Time" in req.prompt
            answer = "YES" if "Bullet Time" in req.prompt else "NO"
        elif any(o.id == "YES" for o in req.options):
            answer = "YES"
        else:
            opt = req.options[0]
            answer = opt.metadata["hex"] if opt.metadata and "hex" in opt.metadata else opt.id
        state.execution_stack[-1].pending_input = {"selection": answer}
    else:
        raise AssertionError(f"chain did not end; Bullet Time offered {bullet_time_offers} times")

    # Bounce, Bullet Time re-performs it (may repeat), the repeat offers Bullet
    # Time once more, and that re-performance can no longer repeat.
    assert bullet_time_offers == 2

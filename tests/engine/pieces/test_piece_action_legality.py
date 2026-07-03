"""Multi-piece action legality: a restriction zone (e.g. Arien's Spell Break)
must be evaluated per-piece. Razzle may perform a restricted action only if at
least one piece can legally perform it; a piece standing in the zone cannot be
chosen to perform it."""

from goa2.domain.hex import Hex
from goa2.domain.models import ActionType, Card, CardColor, CardTier
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.scripts.arien_effects import SpellBreakEffect
from tests.engine.effects.builders import EffectScenarioBuilder


def _state(actor: str = "hero_razzle"):
    """Line board 0..6; knight (enemy) at (6,0,-6) is the Spell Break source."""
    hexes = [(q, 0, -q) for q in range(7)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(6, 0, -6))
        .with_actor(actor)
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    return state


def _place(state, *coords):
    for i, (q, r, s) in enumerate(coords, start=1):
        state.place_entity(piece_id("hero_razzle", i), Hex(q=q, r=r, s=s))


def _cast_spell_break_from_knight(state, radius: int) -> None:
    """Enemy knight emits an Arien Spell Break zone (radius around the knight)."""
    knight = state.get_hero("hero_knight")
    card = Card(
        id="sb_card",
        name="Spell Break",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=13,
        primary_action=ActionType.SKILL,
        effect_id="spell_break",
        effect_text="...",
        radius_value=radius,
    )
    steps = SpellBreakEffect().get_steps(state, knight, card)
    saved = state.current_actor_id
    state.current_actor_id = "hero_knight"
    steps[0].resolve(state, {})
    state.current_actor_id = saved


def _blue_skill_card() -> Card:
    return Card(
        id="blue_skill",
        name="Blue Skill",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=5,
        primary_action=ActionType.SKILL,
        effect_id="dummy",
        effect_text="dummy",
        is_facedown=False,
    )


def test_skill_denied_when_all_pieces_inside_spell_break():
    state = _state()
    # Knight at (6,0,-6), radius 6 -> covers hexes 0..6, so both pieces are inside.
    _place(state, (5, 0, -5), (4, 0, -4))
    _cast_spell_break_from_knight(state, radius=6)

    res = state.validator.can_perform_action(
        state, "hero_razzle", ActionType.SKILL, context={"card": _blue_skill_card()}
    )
    assert res.allowed is False


def test_skill_allowed_when_one_piece_is_outside_spell_break():
    state = _state()
    # Radius 2 around knight@(6,0,-6) covers hexes 4..6. piece_1 inside, piece_2 outside.
    _place(state, (5, 0, -5), (0, 0, 0))
    _cast_spell_break_from_knight(state, radius=2)

    res = state.validator.can_perform_action(
        state, "hero_razzle", ActionType.SKILL, context={"card": _blue_skill_card()}
    )
    assert res.allowed is True


def test_choose_acting_piece_excludes_pieces_blocked_for_the_action():
    from goa2.engine.steps.pieces import ChooseActingPieceStep

    state = _state()
    # Radius 2 around knight@(6,0,-6) covers hexes 4..6. Only piece_1 is inside.
    _place(state, (5, 0, -5), (0, 0, 0), (1, 0, -1))
    _cast_spell_break_from_knight(state, radius=2)
    razzle = state.get_hero("hero_razzle")
    razzle.current_turn_card = _blue_skill_card()
    state.current_actor_id = "hero_razzle"

    step = ChooseActingPieceStep(hero_id="hero_razzle")
    result = step.resolve(state, {"current_action_type": ActionType.SKILL})

    offered = {opt.id for opt in result.input_request.options}
    assert offered == {piece_id("hero_razzle", 2), piece_id("hero_razzle", 3)}


def test_choose_acting_piece_auto_binds_the_only_legal_piece():
    from goa2.engine.steps.pieces import ChooseActingPieceStep

    state = _state()
    # piece_1 inside radius-2 zone, piece_2 outside -> only piece_2 can skill.
    _place(state, (5, 0, -5), (0, 0, 0))
    _cast_spell_break_from_knight(state, radius=2)
    razzle = state.get_hero("hero_razzle")
    razzle.current_turn_card = _blue_skill_card()
    state.current_actor_id = "hero_razzle"

    step = ChooseActingPieceStep(hero_id="hero_razzle")
    result = step.resolve(state, {"current_action_type": ActionType.SKILL})

    assert result.is_finished is True
    assert result.requires_input is False
    assert str(state.acting_piece_id) == piece_id("hero_razzle", 2)


def _cast_repeat_prevention_from_knight(state, radius: int) -> None:
    """Enemy knight emits a repeat-prevention zone (radius around the knight).
    No shipped card produces this against a multi-piece hero yet; the guard is
    defensive against the same unbound-owner bypass fixed for restrictions."""
    state.add_effect(
        ActiveEffect(
            id="repeat_block",
            source_id="hero_knight",
            effect_type=EffectType.REPEAT_PREVENTION,
            scope=EffectScope(
                shape=Shape.RADIUS,
                range=radius,
                origin_id="hero_knight",
                affects=AffectsFilter.ENEMY_HEROES,
            ),
            duration=DurationType.THIS_TURN,
            created_at_round=state.round,
            created_at_turn=state.turn,
            is_active=True,
        )
    )


def test_repeat_denied_when_all_pieces_inside_repeat_prevention():
    state = _state()
    # Radius 6 around knight@(6,0,-6) covers hexes 0..6, so both pieces are inside.
    _place(state, (5, 0, -5), (4, 0, -4))
    _cast_repeat_prevention_from_knight(state, radius=6)

    res = state.validator.can_repeat_action(state, "hero_razzle")
    assert res.allowed is False


def test_repeat_allowed_when_one_piece_outside_repeat_prevention():
    state = _state()
    # Radius 2 around knight@(6,0,-6) covers hexes 4..6. piece_1 inside, piece_2 outside.
    _place(state, (5, 0, -5), (0, 0, 0))
    _cast_repeat_prevention_from_knight(state, radius=2)

    res = state.validator.can_repeat_action(state, "hero_razzle")
    assert res.allowed is True

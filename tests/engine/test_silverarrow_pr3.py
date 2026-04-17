"""Tests for Silverarrow PR3 card effects (Families 1, 5, 6).

Covered:
- Family 1 RED Isolated Snipe: clear_shot, opportunity_shot, snap_shot
- Family 5 GREEN Drag-and-Dance: lead_astray, divert_attention, disorient
- Family 6 GREEN Gift Retrieve: natures_blessing, fae_healing
"""

import pytest

import goa2.scripts.silverarrow_effects  # noqa: F401 — registers effects
import goa2.data.heroes.silverarrow  # noqa: F401 — registers hero
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.steps import (
    AttackSequenceStep,
    ComputeDistanceStep,
    GainCoinsStep,
    MoveUnitStep,
    RecordHexStep,
    ResolveCardStep,
    RetrieveCardStep,
    SelectStep,
)
from goa2.engine.filters import (
    CountMatchFilter,
    InStraightLineFilter,
    ObstacleFilter,
    OrFilter,
    RangeFilter,
    StraightLinePathFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Minion,
    MinionType,
    Team,
    TeamColor,
)
from goa2.domain.hex import Hex
from goa2.data.heroes.registry import HeroRegistry
from goa2.engine.stats import compute_card_stats


def _card_by_id(card_id: str):
    hero = HeroRegistry.get("Silverarrow")
    card = next((c for c in hero.deck if c.id == card_id), None)
    assert card is not None, f"Silverarrow has no card {card_id}"
    return card


def _make_filler_card(card_id="filler", color=CardColor.GOLD):
    return Card(
        id=card_id,
        name="Filler",
        tier=CardTier.UNTIERED,
        color=color,
        initiative=1,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        primary_action_value=1,
        effect_id="filler",
        effect_text="",
        is_facedown=False,
    )


@pytest.fixture
def silver_state():
    board = Board()
    hexes = set()
    for q in range(-5, 6):
        for r in range(-5, 6):
            s = -q - r
            if abs(s) <= 5:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    silver = HeroRegistry.get("Silverarrow")
    silver.team = TeamColor.RED
    silver.hand = []

    enemy = Hero(
        id="enemy_hero",
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )
    enemy.hand = [
        _make_filler_card("enemy_filler_1"),
        _make_filler_card("enemy_filler_2"),
    ]

    ally = Hero(
        id="ally_hero",
        name="Ally",
        team=TeamColor.RED,
        deck=[],
        level=1,
    )
    ally.hand = []
    ally.discard_pile = [
        _make_filler_card("ally_discard_1"),
        _make_filler_card("ally_discard_2"),
    ]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[silver, ally], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_silverarrow", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_hero", Hex(q=3, r=0, s=-3))
    state.place_entity("ally_hero", Hex(q=1, r=-1, s=0))
    state.current_actor_id = "hero_silverarrow"
    return state


# =============================================================================
# Family 1 — Isolated-Target Snipe
# =============================================================================


class TestClearShot:
    def test_registered(self):
        assert CardEffectRegistry.get("clear_shot") is not None
        assert CardEffectRegistry.get("opportunity_shot") is not None
        assert CardEffectRegistry.get("snap_shot") is not None

    def test_steps_structure(self, silver_state):
        effect = CardEffectRegistry.get("clear_shot")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("clear_shot")
        steps = effect.get_steps(silver_state, hero, card)
        assert len(steps) == 1
        atk = steps[0]
        assert isinstance(atk, AttackSequenceStep)
        assert atk.is_ranged is True
        assert atk.range_val == card.range_value  # 4
        # Should have exactly one OrFilter in target_filters
        assert len(atk.target_filters) == 1
        or_filter = atk.target_filters[0]
        assert isinstance(or_filter, OrFilter)
        assert len(or_filter.filters) == 2
        # First branch: CountMatchFilter (isolation check)
        assert isinstance(or_filter.filters[0], CountMatchFilter)
        # Second branch: RangeFilter (melee fallback)
        assert isinstance(or_filter.filters[1], RangeFilter)
        assert or_filter.filters[1].max_range == 1

    def test_isolation_filter_accepts_isolated_target(self, silver_state):
        """An enemy with no other units adjacent passes the isolation check."""
        # enemy_hero is at (3,0,-3) — no one adjacent → isolated
        effect = CardEffectRegistry.get("clear_shot")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("clear_shot")
        steps = effect.get_steps(silver_state, hero, card)
        or_filter = steps[0].target_filters[0]
        isolation_filter = or_filter.filters[0]
        assert isolation_filter.apply(
            "enemy_hero", silver_state, silver_state.execution_context
        )

    def test_isolation_filter_rejects_non_isolated_target(self, silver_state):
        """An enemy adjacent to another unit fails the isolation check."""
        # Place a minion adjacent to enemy_hero
        minion = Minion(
            id="enemy_minion", name="Minion", team=TeamColor.BLUE, type=MinionType.MELEE
        )
        silver_state.teams[TeamColor.BLUE].minions.append(minion)
        silver_state.place_entity("enemy_minion", Hex(q=3, r=-1, s=-2))

        effect = CardEffectRegistry.get("clear_shot")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("clear_shot")
        steps = effect.get_steps(silver_state, hero, card)
        or_filter = steps[0].target_filters[0]
        isolation_filter = or_filter.filters[0]
        assert not isolation_filter.apply(
            "enemy_hero", silver_state, silver_state.execution_context
        )

    def test_melee_fallback_accepts_adjacent(self, silver_state):
        """An adjacent enemy passes the melee fallback."""
        # Place enemy adjacent to silverarrow
        silver_state.move_unit("enemy_hero", Hex(q=1, r=0, s=-1))

        effect = CardEffectRegistry.get("clear_shot")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("clear_shot")
        steps = effect.get_steps(silver_state, hero, card)
        or_filter = steps[0].target_filters[0]
        melee_filter = or_filter.filters[1]
        assert melee_filter.apply(
            "enemy_hero", silver_state, silver_state.execution_context
        )

    def test_or_filter_passes_if_either_branch(self, silver_state):
        """OrFilter passes if either isolation OR melee applies."""
        effect = CardEffectRegistry.get("clear_shot")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("clear_shot")
        steps = effect.get_steps(silver_state, hero, card)
        or_filter = steps[0].target_filters[0]
        # enemy at (3,0,-3) is isolated — OrFilter passes via first branch
        assert or_filter.apply(
            "enemy_hero", silver_state, silver_state.execution_context
        )

    def test_non_isolated_non_adjacent_rejected(self, silver_state):
        """A target that is neither isolated nor adjacent fails."""
        # Place minion adjacent to enemy → not isolated
        minion = Minion(
            id="enemy_minion", name="Minion", team=TeamColor.BLUE, type=MinionType.MELEE
        )
        silver_state.teams[TeamColor.BLUE].minions.append(minion)
        silver_state.place_entity("enemy_minion", Hex(q=3, r=-1, s=-2))
        # enemy at (3,0,-3), silverarrow at (0,0,0) → not adjacent

        effect = CardEffectRegistry.get("clear_shot")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("clear_shot")
        steps = effect.get_steps(silver_state, hero, card)
        or_filter = steps[0].target_filters[0]
        assert not or_filter.apply(
            "enemy_hero", silver_state, silver_state.execution_context
        )

    def test_all_three_share_structure(self, silver_state):
        """clear_shot, opportunity_shot, snap_shot all produce the same step pattern."""
        hero = silver_state.get_hero("hero_silverarrow")
        for effect_id in ("clear_shot", "opportunity_shot", "snap_shot"):
            effect = CardEffectRegistry.get(effect_id)
            card = _card_by_id(effect_id)
            steps = effect.get_steps(silver_state, hero, card)
            assert len(steps) == 1
            assert isinstance(steps[0], AttackSequenceStep)
            assert isinstance(steps[0].target_filters[0], OrFilter)


# =============================================================================
# Family 5 — Drag-and-Dance
# =============================================================================


class TestLeadAstray:
    def test_registered(self):
        assert CardEffectRegistry.get("lead_astray") is not None

    def test_steps_structure(self, silver_state):
        effect = CardEffectRegistry.get("lead_astray")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("lead_astray")
        steps = effect.get_steps(silver_state, hero, card)
        # SelectStep(unit), RecordHex, SelectStep(hex), MoveUnit, ComputeDistance,
        # SelectStep(hex), MoveUnit
        assert len(steps) == 7
        assert isinstance(steps[0], SelectStep)  # select enemy
        assert isinstance(steps[1], RecordHexStep)
        assert isinstance(steps[2], SelectStep)  # select drag dest
        assert isinstance(steps[3], MoveUnitStep)  # drag enemy
        assert isinstance(steps[4], ComputeDistanceStep)
        assert isinstance(steps[5], SelectStep)  # self move
        assert isinstance(steps[6], MoveUnitStep)  # self move

    def test_drag_range_is_3(self, silver_state):
        effect = CardEffectRegistry.get("lead_astray")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("lead_astray")
        steps = effect.get_steps(silver_state, hero, card)
        # The drag destination filter should allow up to 3 spaces from target
        drag_dest_select = steps[2]
        range_filter = next(
            f for f in drag_dest_select.filters if isinstance(f, RangeFilter)
        )
        assert range_filter.max_range == 3

    def test_self_move_has_straight_line_filters(self, silver_state):
        effect = CardEffectRegistry.get("lead_astray")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("lead_astray")
        steps = effect.get_steps(silver_state, hero, card)
        self_move_select = steps[5]
        filter_types = {type(f) for f in self_move_select.filters}
        assert InStraightLineFilter in filter_types
        assert StraightLinePathFilter in filter_types

    def test_self_move_range_from_context(self, silver_state):
        """Self-move uses max_range_key to read distance from context."""
        effect = CardEffectRegistry.get("lead_astray")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("lead_astray")
        steps = effect.get_steps(silver_state, hero, card)
        self_move_select = steps[5]
        range_filter = next(
            f for f in self_move_select.filters if isinstance(f, RangeFilter)
        )
        assert range_filter.max_range_key == "drag_distance_moved"


class TestDivertAttention:
    def test_registered(self):
        assert CardEffectRegistry.get("divert_attention") is not None

    def test_drag_range_is_2(self, silver_state):
        effect = CardEffectRegistry.get("divert_attention")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("divert_attention")
        steps = effect.get_steps(silver_state, hero, card)
        drag_dest_select = steps[2]
        range_filter = next(
            f for f in drag_dest_select.filters if isinstance(f, RangeFilter)
        )
        assert range_filter.max_range == 2


class TestDisorient:
    def test_registered(self):
        assert CardEffectRegistry.get("disorient") is not None

    def test_steps_structure(self, silver_state):
        effect = CardEffectRegistry.get("disorient")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("disorient")
        steps = effect.get_steps(silver_state, hero, card)
        # SelectStep(unit), SelectStep(hex), MoveUnit, SelectStep(hex), MoveUnit
        assert len(steps) == 5
        assert isinstance(steps[0], SelectStep)  # select enemy
        assert isinstance(steps[1], SelectStep)  # dest for enemy
        assert isinstance(steps[2], MoveUnitStep)  # move enemy
        assert isinstance(steps[3], SelectStep)  # self move
        assert isinstance(steps[4], MoveUnitStep)  # self move

    def test_no_straight_line_constraint(self, silver_state):
        """Disorient self-move has no straight-line filter."""
        effect = CardEffectRegistry.get("disorient")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("disorient")
        steps = effect.get_steps(silver_state, hero, card)
        self_move_select = steps[3]
        filter_types = {type(f) for f in self_move_select.filters}
        assert InStraightLineFilter not in filter_types
        assert StraightLinePathFilter not in filter_types

    def test_drag_and_self_move_both_1_space(self, silver_state):
        effect = CardEffectRegistry.get("disorient")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("disorient")
        steps = effect.get_steps(silver_state, hero, card)
        # Drag dest range
        drag_range = next(f for f in steps[1].filters if isinstance(f, RangeFilter))
        assert drag_range.max_range == 1
        # Self move range
        self_range = next(f for f in steps[3].filters if isinstance(f, RangeFilter))
        assert self_range.max_range == 1


class TestLeadAstrayIntegration:
    """Integration tests driving Lead Astray through the stack."""

    def test_drag_enemy_and_dance(self, silver_state):
        """Full flow: drag enemy 2 spaces, then self-move 2 in a straight line."""
        # Place enemy adjacent to silverarrow
        silver_state.move_unit("enemy_hero", Hex(q=1, r=0, s=-1))

        card = _card_by_id("lead_astray")
        hero = silver_state.get_hero("hero_silverarrow")
        hero.current_turn_card = card

        effect = CardEffectRegistry.get("lead_astray")
        steps = effect.get_steps(silver_state, hero, card)
        push_steps(silver_state, steps)

        # Step 1: Select adjacent enemy
        req = process_resolution_stack(silver_state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        silver_state.execution_stack[-1].pending_input = {"selection": "enemy_hero"}

        # Step 2: Select drag destination (move enemy 2 spaces away)
        req = process_resolution_stack(silver_state)
        assert req is not None
        assert req["type"] == "SELECT_HEX"
        drag_dest = Hex(q=3, r=0, s=-3)
        silver_state.execution_stack[-1].pending_input = {
            "selection": drag_dest.model_dump()
        }

        # Step 3: Self-move in a straight line
        req = process_resolution_stack(silver_state)
        assert req is not None
        assert req["type"] == "SELECT_HEX"
        # Silverarrow is at (0,0,0), move 2 in opposite direction
        dance_dest = Hex(q=-2, r=0, s=2)
        silver_state.execution_stack[-1].pending_input = {
            "selection": dance_dest.model_dump()
        }

        # Done
        req = process_resolution_stack(silver_state)
        assert req is None

        # Verify positions
        assert silver_state.entity_locations.get("enemy_hero") == drag_dest
        assert silver_state.entity_locations.get("hero_silverarrow") == dance_dest

    def test_skip_drag_skips_self_move(self, silver_state):
        """If player skips drag, self-move is skipped too."""
        silver_state.move_unit("enemy_hero", Hex(q=1, r=0, s=-1))

        card = _card_by_id("lead_astray")
        hero = silver_state.get_hero("hero_silverarrow")
        hero.current_turn_card = card

        effect = CardEffectRegistry.get("lead_astray")
        steps = effect.get_steps(silver_state, hero, card)
        push_steps(silver_state, steps)

        # Step 1: Skip the drag target selection
        req = process_resolution_stack(silver_state)
        assert req is not None
        silver_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        # Everything should resolve (no more input needed)
        req = process_resolution_stack(silver_state)
        assert req is None

        # Positions unchanged
        assert silver_state.entity_locations.get("hero_silverarrow") == Hex(
            q=0, r=0, s=0
        )
        assert silver_state.entity_locations.get("enemy_hero") == Hex(q=1, r=0, s=-1)


class TestDisorientIntegration:
    """Integration tests for Disorient through the stack."""

    def test_move_enemy_and_self(self, silver_state):
        """Move enemy 1 space, then self-move 1 space."""
        silver_state.move_unit("enemy_hero", Hex(q=1, r=0, s=-1))

        card = _card_by_id("disorient")
        hero = silver_state.get_hero("hero_silverarrow")
        hero.current_turn_card = card

        effect = CardEffectRegistry.get("disorient")
        steps = effect.get_steps(silver_state, hero, card)
        push_steps(silver_state, steps)

        # Select enemy
        req = process_resolution_stack(silver_state)
        assert req is not None
        silver_state.execution_stack[-1].pending_input = {"selection": "enemy_hero"}

        # Select dest for enemy (1 space)
        req = process_resolution_stack(silver_state)
        assert req is not None
        enemy_dest = Hex(q=2, r=0, s=-2)
        silver_state.execution_stack[-1].pending_input = {
            "selection": enemy_dest.model_dump()
        }

        # Self-move 1 space
        req = process_resolution_stack(silver_state)
        assert req is not None
        self_dest = Hex(q=-1, r=0, s=1)
        silver_state.execution_stack[-1].pending_input = {
            "selection": self_dest.model_dump()
        }

        req = process_resolution_stack(silver_state)
        assert req is None

        assert silver_state.entity_locations.get("enemy_hero") == enemy_dest
        assert silver_state.entity_locations.get("hero_silverarrow") == self_dest


# =============================================================================
# Family 6 — Gift Retrieve
# =============================================================================


class TestNaturesBlessing:
    def test_registered(self):
        assert CardEffectRegistry.get("natures_blessing") is not None
        assert CardEffectRegistry.get("fae_healing") is not None

    def test_steps_structure(self, silver_state):
        effect = CardEffectRegistry.get("natures_blessing")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("natures_blessing")
        steps = effect.get_steps(silver_state, hero, card)
        # SelectStep(unit), SelectStep(card), RetrieveCard, GainCoins
        assert len(steps) == 4
        assert isinstance(steps[0], SelectStep)  # select hero
        assert isinstance(steps[1], SelectStep)  # select card
        assert isinstance(steps[2], RetrieveCardStep)
        assert isinstance(steps[3], GainCoinsStep)

    def test_natures_blessing_grants_2_coins(self, silver_state):
        effect = CardEffectRegistry.get("natures_blessing")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("natures_blessing")
        steps = effect.get_steps(silver_state, hero, card)
        gain_step = steps[3]
        assert gain_step.amount == 2

    def test_fae_healing_grants_1_coin(self, silver_state):
        effect = CardEffectRegistry.get("fae_healing")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("fae_healing")
        steps = effect.get_steps(silver_state, hero, card)
        gain_step = steps[3]
        assert gain_step.amount == 1

    def test_hero_selection_filters(self, silver_state):
        """Hero select uses HERO + radius range (any team, per card text)."""
        effect = CardEffectRegistry.get("natures_blessing")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("natures_blessing")
        steps = effect.get_steps(silver_state, hero, card)
        hero_select = steps[0]
        filter_types = {type(f) for f in hero_select.filters}
        assert UnitTypeFilter in filter_types
        assert RangeFilter in filter_types


class TestNaturesBlessingIntegration:
    """Integration tests for Nature's Blessing through the stack."""

    def test_gift_retrieve_and_gain_coins(self, silver_state):
        """Select ally, they retrieve a card and gain 2 coins."""
        card = _card_by_id("natures_blessing")
        hero = silver_state.get_hero("hero_silverarrow")
        hero.current_turn_card = card

        ally = silver_state.get_hero("ally_hero")
        assert len(ally.discard_pile) == 2
        initial_gold = ally.gold

        effect = CardEffectRegistry.get("natures_blessing")
        steps = effect.get_steps(silver_state, hero, card)
        push_steps(silver_state, steps)

        # Step 1: Select ally hero
        req = process_resolution_stack(silver_state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        silver_state.execution_stack[-1].pending_input = {"selection": "ally_hero"}

        # Step 2: Ally selects card from discard
        req = process_resolution_stack(silver_state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"
        silver_state.execution_stack[-1].pending_input = {"selection": "ally_discard_1"}

        # Steps 3 & 4: Retrieve + Coins resolve automatically
        req = process_resolution_stack(silver_state)
        assert req is None

        # Verify: card retrieved, coins gained
        assert len(ally.discard_pile) == 1
        assert any(c.id == "ally_discard_1" for c in ally.hand)
        assert ally.gold == initial_gold + 2

    def test_skip_hero_selection(self, silver_state):
        """Skipping hero selection skips everything."""
        card = _card_by_id("natures_blessing")
        hero = silver_state.get_hero("hero_silverarrow")
        hero.current_turn_card = card

        ally = silver_state.get_hero("ally_hero")
        initial_discard = len(ally.discard_pile)

        effect = CardEffectRegistry.get("natures_blessing")
        steps = effect.get_steps(silver_state, hero, card)
        push_steps(silver_state, steps)

        # Skip hero selection
        req = process_resolution_stack(silver_state)
        assert req is not None
        silver_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        req = process_resolution_stack(silver_state)
        assert req is None

        # Nothing changed
        assert len(ally.discard_pile) == initial_discard

    def test_skip_card_selection(self, silver_state):
        """Selecting a hero but skipping card selection → no retrieval, no coins."""
        card = _card_by_id("natures_blessing")
        hero = silver_state.get_hero("hero_silverarrow")
        hero.current_turn_card = card

        ally = silver_state.get_hero("ally_hero")
        initial_gold = ally.gold

        effect = CardEffectRegistry.get("natures_blessing")
        steps = effect.get_steps(silver_state, hero, card)
        push_steps(silver_state, steps)

        # Select ally hero
        req = process_resolution_stack(silver_state)
        silver_state.execution_stack[-1].pending_input = {"selection": "ally_hero"}

        # Skip card selection
        req = process_resolution_stack(silver_state)
        silver_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        req = process_resolution_stack(silver_state)
        assert req is None

        # No coins gained
        assert ally.gold == initial_gold

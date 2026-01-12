import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType, StatType
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
)
from goa2.domain.models.effect import DurationType
from goa2.domain.models.marker import MarkerType
from goa2.domain.hex import Hex
from goa2.engine.stats import calculate_minion_defense_modifier, get_computed_stat


@pytest.fixture
def aura_state():
    # Setup:
    # Hero (RED) at 0,0,0
    # Ally Melee (RED) at 1,0,-1 (Range 1) -> +1
    # Ally Ranged (RED) at -1,1,0 (Range 1) -> 0
    # Enemy Melee (BLUE) at 0,1,-1 (Range 1) -> -1
    # Enemy Ranged (BLUE) at 2,0,-2 (Range 2) -> -1

    h1 = Hero(id="H1", name="Hero", team=TeamColor.RED, deck=[])
    m_ally_melee = Minion(
        id="M1", name="AllyMelee", team=TeamColor.RED, type=MinionType.MELEE
    )
    m_ally_ranged = Minion(
        id="M2", name="AllyRanged", team=TeamColor.RED, type=MinionType.RANGED
    )
    m_enemy_melee = Minion(
        id="M3", name="EnemyMelee", team=TeamColor.BLUE, type=MinionType.MELEE
    )
    m_enemy_ranged = Minion(
        id="M4", name="EnemyRanged", team=TeamColor.BLUE, type=MinionType.RANGED
    )

    # Create Board with tiles
    board = Board()
    locations = {
        "H1": Hex(q=0, r=0, s=0),
        "M1": Hex(q=1, r=0, s=-1),
        "M2": Hex(q=-1, r=1, s=0),
        "M3": Hex(q=0, r=1, s=-1),
        "M4": Hex(q=2, r=0, s=-2),
    }

    from goa2.domain.tile import Tile

    for uid, h in locations.items():
        board.tiles[h] = Tile(hex=h)  # Let place_entity handle occupancy

    # Ensure destination tile for test exists
    dest_hex = Hex(q=1, r=-1, s=0)
    board.tiles[dest_hex] = Tile(hex=dest_hex)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[h1], minions=[m_ally_melee, m_ally_ranged]
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[], minions=[m_enemy_melee, m_enemy_ranged]
            ),
        },
        entity_locations={},
    )

    for uid, h in locations.items():
        state.place_entity(uid, h)

    return state


def test_minion_aura_calculation(aura_state):
    # Total expected: (+1 from M1) + (0 from M2) + (-1 from M3) + (-1 from M4) = -1
    modifier = calculate_minion_defense_modifier(aura_state, "H1")
    assert modifier == -1


def test_minion_aura_enemy_ranged_at_range_1(aura_state):
    # If enemy ranged is at range 1, it should still give -1 (it's an enemy minion at range 1)
    aura_state.place_entity("M4", Hex(q=1, r=-1, s=0))  # Move M4 to Range 1
    # Expected: (+1 M1) + (0 M2) + (-1 M3) + (-1 M4) = -1
    modifier = calculate_minion_defense_modifier(aura_state, "H1")
    assert modifier == -1


def test_minion_aura_no_hero_location(aura_state):
    aura_state.remove_entity("H1")
    assert calculate_minion_defense_modifier(aura_state, "H1") == 0


# -----------------------------------------------------------------------------
# Tests for AREA_STAT_MODIFIER ActiveEffects
# -----------------------------------------------------------------------------


@pytest.fixture
def stat_effect_state():
    """State with a hero for testing stat effects."""
    h1 = Hero(id="hero_1", name="Hero1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="hero_2", name="Hero2", team=TeamColor.BLUE, deck=[])

    board = Board()
    from goa2.domain.tile import Tile

    hex1 = Hex(q=0, r=0, s=0)
    hex2 = Hex(q=1, r=0, s=-1)
    board.tiles[hex1] = Tile(hex=hex1)
    board.tiles[hex2] = Tile(hex=hex2)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[]),
        },
        entity_locations={},
        turn=1,
        round=1,
    )
    state.place_entity("hero_1", hex1)
    state.place_entity("hero_2", hex2)

    return state


class TestGetComputedStatWithActiveEffects:
    """Tests for get_computed_stat reading AREA_STAT_MODIFIER effects."""

    def test_point_effect_applies_to_target(self, stat_effect_state):
        """POINT scope effect applies to the target at origin."""
        state = stat_effect_state

        # Create effect that debuffs hero_1 by -2 Attack
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_2",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(
                shape=Shape.POINT,
                origin_id="hero_1",
                affects=AffectsFilter.ALL_UNITS,
            ),
            stat_type=StatType.ATTACK,
            stat_value=-2,
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
        state.add_effect(effect)

        # Base attack 3 - 2 = 1
        result = get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=3)
        assert result == 1

    def test_point_effect_does_not_apply_to_others(self, stat_effect_state):
        """POINT scope effect only affects the target, not others."""
        state = stat_effect_state

        # Create effect on hero_1
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_2",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(
                shape=Shape.POINT,
                origin_id="hero_1",
                affects=AffectsFilter.ALL_UNITS,
            ),
            stat_type=StatType.ATTACK,
            stat_value=-2,
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
        state.add_effect(effect)

        # hero_2 should not be affected
        result = get_computed_stat(state, "hero_2", StatType.ATTACK, base_value=3)
        assert result == 3

    def test_radius_effect_applies_within_range(self, stat_effect_state):
        """RADIUS scope effect applies to units within range."""
        state = stat_effect_state

        # Create radius 2 effect centered on hero_1
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(
                shape=Shape.RADIUS,
                range=2,
                origin_id="hero_1",
                affects=AffectsFilter.ALL_UNITS,
            ),
            stat_type=StatType.DEFENSE,
            stat_value=+1,
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
        state.add_effect(effect)

        # hero_2 is at distance 1 from hero_1, should get +1
        result = get_computed_stat(state, "hero_2", StatType.DEFENSE, base_value=2)
        assert result == 3

    def test_inactive_effect_not_applied(self, stat_effect_state):
        """Effects with is_active=False are not applied."""
        state = stat_effect_state

        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_2",
            source_card_id="card_1",  # Card-based effect
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.POINT, origin_id="hero_1"),
            stat_type=StatType.ATTACK,
            stat_value=-5,
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=False,  # Not activated yet
        )
        state.add_effect(effect)

        # Effect should not apply
        result = get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=3)
        assert result == 3

    def test_expired_duration_not_applied(self, stat_effect_state):
        """Effects with expired duration are not applied."""
        state = stat_effect_state
        state.turn = 2  # Advance turn

        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_2",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.POINT, origin_id="hero_1"),
            stat_type=StatType.ATTACK,
            stat_value=-5,
            duration=DurationType.THIS_TURN,
            created_at_turn=1,  # Created last turn
            created_at_round=1,
            is_active=True,
        )
        state.add_effect(effect)

        # Effect should not apply (duration expired)
        result = get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=3)
        assert result == 3

    def test_affects_filter_enemy_only(self, stat_effect_state):
        """ENEMY_UNITS filter only affects enemies."""
        state = stat_effect_state

        # hero_1 (RED) creates effect affecting enemies only
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(
                shape=Shape.GLOBAL,
                affects=AffectsFilter.ENEMY_UNITS,
            ),
            stat_type=StatType.INITIATIVE,
            stat_value=-1,
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
        state.add_effect(effect)

        # hero_1 (RED, friendly) should not be affected
        result_friendly = get_computed_stat(
            state, "hero_1", StatType.INITIATIVE, base_value=5
        )
        assert result_friendly == 5

        # hero_2 (BLUE, enemy) should be affected
        result_enemy = get_computed_stat(
            state, "hero_2", StatType.INITIATIVE, base_value=5
        )
        assert result_enemy == 4

    def test_multiple_effects_stack(self, stat_effect_state):
        """Multiple effects stack additively."""
        state = stat_effect_state

        for i in range(3):
            effect = ActiveEffect(
                id=f"eff_{i}",
                source_id="hero_2",
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(shape=Shape.POINT, origin_id="hero_1"),
                stat_type=StatType.ATTACK,
                stat_value=-1,
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
                is_active=True,
            )
            state.add_effect(effect)

        # 3 effects of -1 each = -3
        result = get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=5)
        assert result == 2


class TestGetComputedStatWithMarkers:
    """Tests for get_computed_stat reading marker effects."""

    def test_venom_marker_applies_debuffs(self, stat_effect_state):
        """Venom marker applies stat debuffs to the target hero."""
        state = stat_effect_state

        # Place venom marker on hero_1 with value -1
        state.place_marker(
            marker_type=MarkerType.VENOM,
            target_id="hero_1",
            value=-1,
            source_id="hero_2",
        )

        # Check all three stats are debuffed
        attack = get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=3)
        defense = get_computed_stat(state, "hero_1", StatType.DEFENSE, base_value=2)
        initiative = get_computed_stat(
            state, "hero_1", StatType.INITIATIVE, base_value=5
        )

        assert attack == 2  # 3 - 1
        assert defense == 1  # 2 - 1
        assert initiative == 4  # 5 - 1

    def test_venom_marker_value_2(self, stat_effect_state):
        """Venom marker with value -2 applies -2 to all stats."""
        state = stat_effect_state

        state.place_marker(
            marker_type=MarkerType.VENOM,
            target_id="hero_1",
            value=-2,
            source_id="hero_2",
        )

        attack = get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=3)
        assert attack == 1  # 3 - 2

    def test_marker_on_different_hero_not_applied(self, stat_effect_state):
        """Marker on hero_1 doesn't affect hero_2."""
        state = stat_effect_state

        state.place_marker(
            marker_type=MarkerType.VENOM,
            target_id="hero_1",
            value=-2,
            source_id="hero_2",
        )

        # hero_2 should not be affected
        attack = get_computed_stat(state, "hero_2", StatType.ATTACK, base_value=3)
        assert attack == 3

    def test_marker_and_effect_stack(self, stat_effect_state):
        """Markers and effects stack together."""
        state = stat_effect_state

        # Place venom marker (-1)
        state.place_marker(
            marker_type=MarkerType.VENOM,
            target_id="hero_1",
            value=-1,
            source_id="hero_2",
        )

        # Add effect (-2)
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_2",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.POINT, origin_id="hero_1"),
            stat_type=StatType.ATTACK,
            stat_value=-2,
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
        state.add_effect(effect)

        # Total: 5 - 1 (marker) - 2 (effect) = 2
        attack = get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=5)
        assert attack == 2

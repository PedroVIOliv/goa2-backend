
import pytest
from goa2.engine.setup import GameSetup
from goa2.domain.models import TeamColor, GamePhase, CardTier, CardState, Hero, Card, ActionType, CardColor
from goa2.domain.types import HeroID
from goa2.data.heroes.registry import HeroRegistry
from goa2.data.heroes.arien import create_arien

@pytest.fixture
def map_path():
    return "src/goa2/data/maps/forgotten_island.json"

@pytest.fixture
def setup_registry():
    # 1. Register Arien
    HeroRegistry.register(create_arien())
    
    # 2. Register Dummy Knight
    knight = Hero(
        id=HeroID("hero_knight"),
        name="Knight",
        deck=[
            Card(id="k_1", name="Slash", tier=CardTier.I, color=CardColor.RED, initiative=5, primary_action=ActionType.ATTACK, primary_action_value=4, effect_id="none", effect_text=""),
            Card(id="k_2", name="Block", tier=CardTier.I, color=CardColor.BLUE, initiative=5, primary_action=ActionType.DEFENSE, primary_action_value=4, effect_id="none", effect_text="")
        ],
        team=TeamColor.BLUE
    )
    HeroRegistry.register(knight)

def test_full_game_setup(map_path, setup_registry):
    """
    Verifies that create_game correctly initializes the GameState.
    """
    # 1. Create Game with 1v1 (Arien vs Knight)
    red_heroes = ["Arien"]
    blue_heroes = ["Knight"]
    
    state = GameSetup.create_game(map_path, red_heroes, blue_heroes)
    
    # 2. Assert Basic State
    assert state.phase == GamePhase.PLANNING
    assert state.round == 1
    assert state.turn == 1
    assert state.wave_counter == 5
    assert state.active_zone_id == "Mid"
    
    # 3. Assert Teams & Life Counters
    assert state.teams[TeamColor.RED].life_counters == 6
    assert state.teams[TeamColor.BLUE].life_counters == 6
    
    # 4. Assert Heroes Placed
    red_team = state.teams[TeamColor.RED]
    blue_team = state.teams[TeamColor.BLUE]
    
    assert len(red_team.heroes) == 1
    assert len(blue_team.heroes) == 1
    
    red_hero = red_team.heroes[0]
    blue_hero = blue_team.heroes[0]
    
    assert red_hero.name == "Arien"
    assert blue_hero.name == "Knight"
    assert red_hero.id != blue_hero.id 
    
    # Assert Minions Spawned in Mid
    mid_zone = state.board.zones["Mid"]
    minion_count = 0
    for h in mid_zone.hexes:
        tile = state.board.get_tile(h)
        if tile.occupant_id and "minion" in tile.occupant_id:
            minion_count += 1
            
    assert minion_count > 0
    
    # 5. Assert Hand Setup
    # Arien has Tier I and Untiered.
    assert len(red_hero.hand) > 0
    assert len(red_hero.deck) > 0 
    
    for c in red_hero.hand:
        assert c.tier in [CardTier.I, CardTier.UNTIERED]
        assert c.state == CardState.HAND
    
    # Knight has only Tier I
    assert len(blue_hero.hand) == 2
    assert len(blue_hero.deck) == 2 # Deck acts as master list
    
    # Verify State Update
    for c in blue_hero.deck:
        assert c.state == CardState.HAND

def test_rogue_definition():
    """
    Verifies the Rogue hero is loaded correctly with the updated 5-card deck.
    """
    from goa2.data.heroes.rogue import create_rogue
    rogue = create_rogue()
    
    assert len(rogue.deck) == 5
    initiatives = sorted([c.initiative for c in rogue.deck], reverse=True)
    assert initiatives == [8, 7, 6, 5, 4]
    
    for c in rogue.deck:
        assert c.primary_action == ActionType.SKILL
        assert c.secondary_actions[ActionType.DEFENSE] == 2
        assert c.secondary_actions[ActionType.ATTACK] == 2
        assert c.secondary_actions[ActionType.MOVEMENT] == 2


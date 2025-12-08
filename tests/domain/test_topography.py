import pytest
from goa2.domain.board import SpawnPoint, SpawnType
from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor, MinionType
from goa2.domain.models.token import Token
from goa2.domain.models.marker import Marker
from goa2.domain.models.unit import Unit, Hero
from goa2.domain.types import BoardEntityID, UnitID

def test_spawn_point_validation():
    loc = Hex(q=0, r=0, s=0)
    
    # 1. Valid Minion Spawn
    sp = SpawnPoint(
        location=loc, 
        team=TeamColor.RED, 
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE
    )
    assert sp.is_minion_spawn
    assert not sp.is_hero_spawn

    # 2. Valid Hero Spawn
    sp_hero = SpawnPoint(
        location=loc,
        team=TeamColor.BLUE,
        type=SpawnType.HERO
    )
    assert sp_hero.is_hero_spawn
    assert not sp_hero.is_minion_spawn

    # 3. Invalid: Minion Spawn missing type
    with pytest.raises(ValueError, match="Minion spawn point must specify minion_type"):
        SpawnPoint(
            location=loc,
            team=TeamColor.RED,
            type=SpawnType.MINION,
            minion_type=None
        )

    # 4. Invalid: Hero Spawn with type
    with pytest.raises(ValueError, match="Hero spawn point cannot specify minion_type"):
        SpawnPoint(
            location=loc,
            team=TeamColor.BLUE,
            type=SpawnType.HERO,
            minion_type=MinionType.RANGED
        )


def test_token_creation():
    # Simple Token creation
    t = Token(id=BoardEntityID("trap1"), name="Trap")
    assert t.id == "trap1"
    assert t.name == "Trap"
    
    # It shares BoardEntity properties
    assert isinstance(t.id, str) # BoardEntityID is string alias

def test_marker_usage():
    # 1. Create Marker
    m = Marker(id="poison", name="Poison")
    
    # 2. Create Unit
    u = Unit(id=UnitID("u1"), name="TestUnit", team=TeamColor.RED)
    
    # 3. Assign Marker
    u.markers.append(m)
    
    assert len(u.markers) == 1
    assert u.markers[0].name == "Poison"
    
    # 4. Add another
    m2 = Marker(id="stun", name="Stun")
    u.markers.append(m2)
    assert len(u.markers) == 2

import pytest
from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor, MinionType
from goa2.domain.models.spawn import SpawnPoint, SpawnType

def test_valid_minion_spawn():
    sp = SpawnPoint(
        location=Hex(q=0, r=0, s=0),
        team=TeamColor.RED,
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE
    )
    assert sp.is_minion_spawn
    assert not sp.is_hero_spawn

def test_valid_hero_spawn():
    sp = SpawnPoint(
        location=Hex(q=0, r=0, s=0),
        team=TeamColor.BLUE,
        type=SpawnType.HERO
    )
    assert sp.is_hero_spawn
    assert not sp.is_minion_spawn

def test_invalid_minion_spawn_missing_type():
    with pytest.raises(ValueError, match="Minion spawn point must specify minion_type"):
        SpawnPoint(
            location=Hex(q=0, r=0, s=0),
            team=TeamColor.RED,
            type=SpawnType.MINION,
            minion_type=None
        )

def test_invalid_hero_spawn_with_type():
    with pytest.raises(ValueError, match="Hero spawn point cannot specify minion_type"):
        SpawnPoint(
            location=Hex(q=0, r=0, s=0),
            team=TeamColor.BLUE,
            type=SpawnType.HERO,
            minion_type=MinionType.RANGED
        )

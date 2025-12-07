import pytest
from goa2.domain.hex import Hex

def test_hex_creation_valid():
    h = Hex(q=0, r=0, s=0)
    assert h.q == 0
    assert h.r == 0
    assert h.s == 0

def test_hex_creation_invalid_sum():
    with pytest.raises(ValueError, match="must sum to 0"):
        Hex(q=1, r=1, s=1)

def test_hex_equality():
    h1 = Hex(q=1, r=-1, s=0)
    h2 = Hex(q=1, r=-1, s=0)
    assert h1 == h2
    assert hash(h1) == hash(h2)

def test_hex_addition():
    h1 = Hex(q=1, r=-1, s=0) # E
    h2 = Hex(q=1, r=0, s=-1) # NE
    # 1+1, -1+0, 0-1 => 2, -1, -1
    result = h1 + h2
    assert result == Hex(q=2, r=-1, s=-1)

def test_hex_subtraction():
    h1 = Hex(q=1, r=-1, s=0)
    h2 = Hex(q=1, r=-1, s=0)
    assert (h1 - h2) == Hex(q=0, r=0, s=0)

def test_hex_distance():
    center = Hex(q=0, r=0, s=0)
    neighbor = Hex(q=1, r=-1, s=0)
    assert center.distance(neighbor) == 1
    
    far = Hex(q=2, r=-2, s=0)
    assert center.distance(far) == 2
    assert neighbor.distance(far) == 1

def test_is_straight_line():
    center = Hex(q=0, r=0, s=0)
    
    # Valid lines (share at least one coord)
    assert center.is_straight_line(Hex(q=0, r=5, s=-5))  # Same q
    assert center.is_straight_line(Hex(q=5, r=0, s=-5))  # Same r
    assert center.is_straight_line(Hex(q=5, r=-5, s=0))  # Same s

    # Invalid line
    # q=1, r=2, s=-3. None match 0.
    assert not center.is_straight_line(Hex(q=1, r=2, s=-3))

def test_line_to_valid():
    start = Hex(q=0, r=0, s=0)
    end = Hex(q=0, r=3, s=-3) # Distance 3
    
    path = start.line_to(end)
    # Expect 3 steps: 
    # (0,1,-1), (0,2,-2), (0,3,-3)
    assert len(path) == 3
    assert path[0] == Hex(q=0, r=1, s=-1)
    assert path[-1] == end

def test_line_to_invalid():
    start = Hex(q=0, r=0, s=0)
    end = Hex(q=1, r=2, s=-3) # Not straight
    
    with pytest.raises(ValueError, match="not in a straight line"):
        start.line_to(end)

def test_line_to_same_hex():
    h = Hex(q=0, r=0, s=0)
    assert h.line_to(h) == []

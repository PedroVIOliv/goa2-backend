from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, field_validator, ConfigDict
from typing import ClassVar, List, Iterator

class HexDirection(int, Enum):
    """
    Clockwise order starting from Top-Right.
    """
    NE = 0
    E = 1
    SE = 2
    SW = 3
    W = 4
    NW = 5

class Hex(BaseModel):
    """
    Cube Coordinates for a Hexagonal Grid.
    Constraint: q + r + s == 0
    """
    model_config = ConfigDict(frozen=True)

    q: int
    r: int
    s: int

    @field_validator('s')
    @classmethod
    def validate_sum(cls, s: int, info) -> int:
        """Ensures the cube coordinate invariant holds."""
        values = info.data
        if 'q' in values and 'r' in values:
            if values['q'] + values['r'] + s != 0:
                raise ValueError(f"Hex coordinates ({values['q']}, {values['r']}, {s}) must sum to 0")
        return s

    def __add__(self, other: Hex) -> Hex:
        return Hex(q=self.q + other.q, r=self.r + other.r, s=self.s + other.s)

    def __sub__(self, other: Hex) -> Hex:
        return Hex(q=self.q - other.q, r=self.r - other.r, s=self.s - other.s)
    
    def __str__(self) -> str:
        return f"({self.q}, {self.r}, {self.s})"

    def length(self) -> int:
        """Distance from center (0,0,0)."""
        return max(abs(self.q), abs(self.r), abs(self.s)) 

    def distance(self, other: Hex) -> int:
        """
        Manhattan distance between two hexes.
        Used for Range and Radius calculations.
        """
        return (self - other).length()

    def scale(self, factor: int) -> Hex:
        """Scales the hex coordinates by a factor."""
        return Hex(q=self.q * factor, r=self.r * factor, s=self.s * factor)

    def neighbor(self, direction_index: int) -> Hex:
        """Returns the neighbor in a specific direction index (0-5)."""
        vectors = [
            Hex(q=1, r=0, s=-1), Hex(q=1, r=-1, s=0), Hex(q=0, r=-1, s=1),
            Hex(q=-1, r=0, s=1), Hex(q=-1, r=1, s=0), Hex(q=0, r=1, s=-1)
        ]
        return self + vectors[direction_index % 6]

    def neighbors(self) -> List[Hex]:
        """Returns the 6 adjacent hexes."""
        vectors = [
            Hex(q=1, r=0, s=-1), Hex(q=1, r=-1, s=0), Hex(q=0, r=-1, s=1),
            Hex(q=-1, r=0, s=1), Hex(q=-1, r=1, s=0), Hex(q=0, r=1, s=-1)
        ]
        return [self + v for v in vectors]
    
    def ring(self, radius: int) -> List[Hex]:
        """
        Returns all hexes in the ring at exact distance 'radius'.
        """
        if radius <= 0:
            return [self] if radius == 0 else []
        
        results = []
        # Start at direction 4 (West) scaled by radius
        # Note: vectors definition in neighbors/neighbor matches HexDirection:
        # 0=NE, 1=E, 2=SE, 3=SW, 4=W, 5=NW
        # W is index 4: Hex(q=-1, r=1, s=0)
        
        # Directions vectors again for reference or reuse
        # We need a predictable starting vector. 
        # Using the logic provided: start = center + direction(4) * radius
        
        # Direction 4 (W) vector: (-1, 1, 0)
        start_dir_vec = Hex(q=-1, r=1, s=0) 
        hex_cursor = self + start_dir_vec.scale(radius)
        
        for i in range(6):
            for _ in range(radius):
                results.append(hex_cursor)
                hex_cursor = hex_cursor.neighbor(i)
                
        return results

    def is_straight_line(self, other: Hex) -> bool:
        """
        Rule: "Two units are in a straight line if... you can draw a straight
        line of spaces through spaces occupied by both." [cite: 952]
        
        In Cube coords, a straight line exists if any of the 3 coordinates match.
        """
        return (self.q == other.q) or (self.r == other.r) or (self.s == other.s)

    def line_to(self, other: Hex) -> List[Hex]:
        """
        Returns the path to the target.
        Strictly assumes the target is in a 'Straight Line' (one of 6 axes).
        If they are NOT in a straight line, this raises ValueError (fail fast).
        """
        if not self.is_straight_line(other):
             # You might want to handle this differently depending on game logic, 
             # but for GoA2 Pushes, this is usually an illegal state.
            raise ValueError("Cannot trace path: Hexes are not in a straight line.")

        N = self.distance(other)
        if N == 0:
            return []

        # Calculate the unit vector (direction) using integer math
        # We know one of these diffs is 0 or equal to N due to straight line rules
        dq = (other.q - self.q) // N
        dr = (other.r - self.r) // N
        ds = (other.s - self.s) // N
        
        results = []
        current = self
        for _ in range(N):
            current = Hex(q=current.q + dq, r=current.r + dr, s=current.s + ds)
            results.append(current)
            
        return results

    def direction_to(self, other: Hex) -> Optional[int]:
        """
        Returns the direction index (0-5) from self to other.
        Returns None if not in a straight line or same hex.
        """
        if self == other: return None
        if not self.is_straight_line(other): return None
        
        diff = other - self
        # We need to map diff vector to one of the 6 neighbor vectors.
        # But 'other' might be far away. We need the UNIT vector.
        # Normalize diff.
        dist = diff.length()
        unit_q = diff.q // dist
        unit_r = diff.r // dist
        unit_s = diff.s // dist
        
        unit_vec = Hex(q=unit_q, r=unit_r, s=unit_s)
        
        vectors = [
            Hex(q=1, r=0, s=-1), Hex(q=1, r=-1, s=0), Hex(q=0, r=-1, s=1),
            Hex(q=-1, r=0, s=1), Hex(q=-1, r=1, s=0), Hex(q=0, r=1, s=-1)
        ]
        
        try:
            return vectors.index(unit_vec)
        except ValueError:
            return None

    @staticmethod
    def _round(frac_q: float, frac_r: float, frac_s: float) -> Hex:
        """Rounds floating point cube coords to the nearest integer hex."""
        q, r, s = round(frac_q), round(frac_r), round(frac_s)
        q_diff = abs(q - frac_q)
        r_diff = abs(r - frac_r)
        s_diff = abs(s - frac_s)

        if q_diff > r_diff and q_diff > s_diff:
            q = -r - s
        elif r_diff > s_diff:
            r = -q - s
        else:
            s = -q - r
        return Hex(q=int(q), r=int(r), s=int(s))
from enum import Enum

class TeamColor(str, Enum):
    RED = "RED"
    BLUE = "BLUE"

class MinionType(str, Enum):
    MELEE = "MELEE"
    RANGED = "RANGED"
    HEAVY = "HEAVY"

class CardTier(str, Enum):
    I = "I"
    II = "II"
    III = "III"
    IV = "IV"
    UNTIERED = "UNTIERED"

class CardColor(str, Enum):
    GOLD = "GOLD"     # Basic
    SILVER = "SILVER" # Basic
    RED = "RED"       # Attack focus
    BLUE = "BLUE"     # Skill focus
    GREEN = "GREEN"   # Utility focus
    PURPLE = "PURPLE" # Ultimate

class ActionType(str, Enum):
    MOVEMENT = "MOVEMENT"
    ATTACK = "ATTACK"
    SKILL = "SKILL"
    DEFENSE = "DEFENSE"
    HOLD = "HOLD"  # Secondary
    CLEAR = "CLEAR" # Replaces Attack
    FAST_TRAVEL = "FAST_TRAVEL" # Replaces Movement

class StatType(str, Enum):
    ATTACK = "ATTACK"
    DEFENSE = "DEFENSE"
    SPEED = "SPEED"
    INITIATIVE = "INITIATIVE"
    RANGE = "RANGE"
    RADIUS = "RADIUS"

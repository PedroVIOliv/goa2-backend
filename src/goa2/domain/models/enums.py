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
    UPGRADE = "UPGRADE"

class StatType(str, Enum):
    ATTACK = "ATTACK"
    DEFENSE = "DEFENSE"
    MOVEMENT = "MOVEMENT"
    INITIATIVE = "INITIATIVE"
    RANGE = "RANGE"
    RADIUS = "RADIUS"

class CardState(str, Enum):
    HAND = "HAND"
    PLAYED = "PLAYED"
    DECK = "DECK"
    DISCARD = "DISCARD"
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    ITEM = "ITEM"
    PASSIVE = "PASSIVE"
    RETIRED = "RETIRED"

class GamePhase(str, Enum):
    SETUP = "SETUP"
    PLANNING = "PLANNING"      # Card Selection
    REVELATION = "REVELATION"  # Reveal cards
    RESOLUTION = "RESOLUTION"  # Acting order
    CLEANUP = "CLEANUP"        # Round/Turn end

class ResolutionStep(str, Enum):
    NONE = "NONE"
    ACTING = "ACTING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"


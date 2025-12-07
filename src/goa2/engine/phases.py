from enum import Enum

class GamePhase(str, Enum):
    """
    High-Level State Machine Phases.
    """
    SETUP = "SETUP"
    PLANNING = "PLANNING"      # Players selecting cards
    RESOLUTION = "RESOLUTION"  # Cards executing
    END_PHASE = "END_PHASE"    # Cleanup, Minion Battle, Level Up

class ResolutionStep(str, Enum):
    """
    Sub-states within the RESOLUTION phase.
    """
    NONE = "NONE"
    REVELATION = "REVELATION"  # Revealing cards
    ACTING = "ACTING"          # Processing Primary Action
    DEFENSE = "DEFENSE"        # Interrupt: Waiting for Defense
    TIE_BREAKING = "TIE_BREAKING" # Interrupt: Waiting for Tie Break

"""Runtime glue to the goa2 engine: effect registration, cloning,
determinization, and the headless self-play harness."""

from .clone import clone_state
from .determinize import determinize
from .effects import register_all_effects
from .harness import DEFAULT_MAP, RunResult, run_game
from .trajectory import (
    InMemoryRecorder,
    JsonlRecorder,
    NullRecorder,
    TrajectoryRecorder,
)

__all__ = [
    "DEFAULT_MAP",
    "InMemoryRecorder",
    "JsonlRecorder",
    "NullRecorder",
    "RunResult",
    "TrajectoryRecorder",
    "clone_state",
    "determinize",
    "register_all_effects",
    "run_game",
]

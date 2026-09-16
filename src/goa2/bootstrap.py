"""Load bundled game rules for servers, workers, and standalone engine tools."""

from __future__ import annotations

import importlib
from pathlib import Path


def register_all_effects() -> None:
    """Import every effect module, stopping if any game rules cannot be loaded.

    Python's module cache makes repeated calls safe within a process. Call this
    before running games or replays in a fresh interpreter; it does not import
    the web application or start server resources.
    """
    scripts_dir = Path(__file__).parent / "scripts"
    for script_path in sorted(scripts_dir.glob("*_effects.py")):
        module_name = f"goa2.scripts.{script_path.stem}"
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            raise RuntimeError(f"Failed to load effect module {module_name}") from exc

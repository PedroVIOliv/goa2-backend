"""Safe resolution of server-owned map files."""

from __future__ import annotations

from pathlib import Path


class MapFileNotFoundError(FileNotFoundError):
    """Raised when a map name does not identify a file in the map directory."""


def maps_dir() -> Path:
    return Path(__file__).parent.parent / "data" / "maps"


def resolve_map_path(map_name: str) -> str:
    """Resolve a flat map identifier without allowing filesystem traversal."""
    base = maps_dir().resolve()
    requested = Path(map_name)
    if not map_name or requested.is_absolute() or requested.name != map_name:
        raise MapFileNotFoundError(map_name)

    candidate = (base / f"{map_name}.json").resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        raise MapFileNotFoundError(map_name)
    return str(candidate)

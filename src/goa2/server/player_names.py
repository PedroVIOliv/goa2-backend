"""Resolution of caller-supplied player names to hero ids.

Both game-creation paths submit names keyed by the same hero identifier they
pass in ``red_heroes``/``blue_heroes`` — a hero *name*. Everything downstream
of creation keys by ``hero_id``.
"""

from __future__ import annotations

from collections.abc import Mapping

MAX_PLAYER_NAME_LENGTH = 20


def resolve_player_names(
    submitted: Mapping[str, str], name_to_id: Mapping[str, str]
) -> dict[str, str]:
    """Map ``{hero name: display name}`` to ``{hero_id: display name}``.

    A name for a hero absent from the game is dropped: it cannot affect play,
    and failing the whole creation over a stray key would be worse. Over-long
    names are truncated so a lobby name can never block a game from starting.
    """
    resolved: dict[str, str] = {}
    for hero_name, display_name in submitted.items():
        hero_id = name_to_id.get(hero_name)
        if hero_id is None:
            continue
        cleaned = display_name.strip()[:MAX_PLAYER_NAME_LENGTH]
        if cleaned:
            resolved[hero_id] = cleaned
    return resolved

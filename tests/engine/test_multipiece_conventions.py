"""Multi-piece hero conventions for effect scripts.

Multi-piece heroes (Razzle) have no board position under their hero ID —
only their pieces do. Effect scripts that read raw location dicts or type-check
against Hero directly silently skip such heroes. This test bans those patterns
in scripts/*_effects.py so new hero effects stay multi-piece-safe by default.

Safe alternatives (all piece-aware):
- state.get_position(id)        — bound/single position (acting piece resolves)
- state.get_positions(id)       — all board positions for an entity
- state.get_piece_ids(hero_id)  — every board presence of a hero (1 for normal)
- state.has_board_presence(id)  — replaces `id in entity_locations`
- state.resolve_board_actor(id) — physical unit performing an action
- state.hero_owner_id(id)       — player-level "is this you?" comparisons
- is_hero_unit(entity)          — replaces isinstance(entity, Hero)
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "goa2" / "scripts"

BANNED: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bentity_locations\b"),
        "read positions via state.get_position()/get_positions()/"
        "has_board_presence()/get_piece_ids(), not entity_locations directly",
    ),
    (
        re.compile(r"\bunit_locations\b"),
        "read positions via state.get_position()/get_positions(), not unit_locations",
    ),
    (
        re.compile(r"isinstance\([^)]*,\s*Hero\s*\)"),
        "use is_hero_unit() from goa2.domain.models instead of isinstance(x, Hero)",
    ),
]


def test_effect_scripts_use_piece_aware_position_api() -> None:
    violations: list[str] = []
    effect_files = sorted(SCRIPTS_DIR.glob("*_effects.py"))
    assert effect_files, f"no effect scripts found under {SCRIPTS_DIR}"

    for path in effect_files:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            code = line.split("#", 1)[0]
            for pattern, advice in BANNED:
                if pattern.search(code):
                    violations.append(f"{path.name}:{lineno}: {line.strip()}\n    fix: {advice}")

    assert not violations, (
        "Effect scripts must stay multi-piece-safe (see this test's docstring "
        "and docs/EFFECT_AUTHOR_REFERENCE.md):\n" + "\n".join(violations)
    )

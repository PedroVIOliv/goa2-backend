from __future__ import annotations

import importlib
import pkgutil
import sys
from collections import Counter

import goa2.data.heroes as heroes_package
from goa2.data.heroes import HeroRegistry
from goa2.domain.models import StatType

EXPECTED_ITEM_COUNTS = {
    StatType.INITIATIVE: 3,
    StatType.DEFENSE: 3,
    StatType.ATTACK: 3,
    StatType.RADIUS: 1,
    StatType.RANGE: 1,
    StatType.MOVEMENT: 1,
}

SKIP_MODULES = {"knight", "registry", "rogue"}
SKIP_HERO_NAMES = {"Knight", "Rogue"}


def import_hero_modules() -> None:
    for module_info in pkgutil.iter_modules(heroes_package.__path__):
        if module_info.ispkg or module_info.name in SKIP_MODULES:
            continue
        importlib.import_module(f"{heroes_package.__name__}.{module_info.name}")


def format_counts(counts: Counter[StatType]) -> str:
    return ", ".join(f"{stat.value.lower()}={counts.get(stat, 0)}" for stat in EXPECTED_ITEM_COUNTS)


def main() -> int:
    import_hero_modules()

    failures: list[str] = []
    checked_count = 0
    for hero_name in sorted(HeroRegistry.list_heroes()):
        if hero_name in SKIP_HERO_NAMES:
            print(f"SKIP {hero_name}")
            continue

        checked_count += 1
        hero = HeroRegistry.get(hero_name)
        if hero is None:
            failures.append(f"{hero_name}: registered but could not be loaded")
            continue

        counts = Counter(card.item for card in hero.deck if card.item is not None)
        mismatches = [
            f"{stat.value.lower()} expected {expected}, got {counts.get(stat, 0)}"
            for stat, expected in EXPECTED_ITEM_COUNTS.items()
            if counts.get(stat, 0) != expected
        ]

        if mismatches:
            failures.append(f"{hero.name}: {format_counts(counts)} ({'; '.join(mismatches)})")
        else:
            print(f"OK {hero.name}: {format_counts(counts)}")

    if failures:
        print("\nCard item count mismatches:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"\nAll {checked_count} checked heroes match expected item counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

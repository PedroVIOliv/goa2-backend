import argparse
import importlib
import os
import sys
from pathlib import Path

# Add src to python path when running this as a repo-root utility.
sys.path.append(os.path.join(os.getcwd(), "src"))

from goa2.data.heroes import registry as hero_registry_module
from goa2.engine.effects import CardEffectRegistry


def import_effect_scripts():
    """Dynamically import all effect scripts in src/goa2/scripts/."""
    scripts_dir = Path("src/goa2/scripts")
    for script_path in scripts_dir.glob("*_effects.py"):
        module_name = f"goa2.scripts.{script_path.stem}"
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            print(f"Error loading {module_name}: {exc}", file=sys.stderr)


def card_label(card, *, is_ultimate=False):
    suffix = " [ULT]" if is_ultimate else ""
    return f"{card.name} ({card.effect_id}){suffix}"


def collect_hero_effect_status(hero):
    implemented = []
    missing = []

    cards = [(card, False) for card in hero.deck]
    if hero.ultimate_card:
        cards.append((hero.ultimate_card, True))

    for card, is_ultimate in cards:
        if not card.effect_id:
            continue

        target = implemented if CardEffectRegistry.get(card.effect_id) else missing
        target.append(card_label(card, is_ultimate=is_ultimate))

    return implemented, missing


def parse_args():
    parser = argparse.ArgumentParser(description="Summarize hero card effect coverage.")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Hide missing card effect names for incomplete heroes.",
    )
    return parser.parse_args()


def verify_hero_effects(show_missing=False):
    import_effect_scripts()

    heroes = [
        hero_registry_module.HeroRegistry.get(hero_name)
        for hero_name in hero_registry_module.HeroRegistry.list_heroes()
    ]
    heroes = [hero for hero in heroes if hero is not None]

    if not heroes:
        print("No heroes found in registry.")
        return

    total_implemented = 0
    total_cards = 0
    incomplete = []

    print("Hero effect implementation status")
    print("---------------------------------")

    for hero in sorted(heroes, key=lambda item: item.name):
        implemented, missing = collect_hero_effect_status(hero)
        total = len(implemented) + len(missing)
        total_implemented += len(implemented)
        total_cards += total

        percentage = (len(implemented) / total) * 100 if total else 100
        status = "OK" if not missing else "TODO"
        print(f"{status:4} {hero.name:12} {len(implemented):2}/{total:<2} {percentage:5.1f}%")

        if missing:
            incomplete.append((hero.name, missing))

    if total_cards:
        percentage = (total_implemented / total_cards) * 100
        print(f"\nTotal: {total_implemented}/{total_cards} ({percentage:.1f}%)")

    if show_missing and incomplete:
        print("\nMissing effects:")
        for hero_name, missing in incomplete:
            print(f"- {hero_name}: {', '.join(missing)}")


if __name__ == "__main__":
    args = parse_args()
    verify_hero_effects(show_missing=not args.summary_only)

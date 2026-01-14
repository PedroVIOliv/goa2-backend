import sys
import os
import importlib
import glob
from pathlib import Path

# Add src to python path
sys.path.append(os.path.join(os.getcwd(), "src"))

from goa2.data.heroes import registry as hero_registry_module
from goa2.engine.effects import CardEffectRegistry
import goa2.data.heroes  # Triggers hero registration


def import_effect_scripts():
    """Dynamically import all effect scripts in src/goa2/scripts/"""
    scripts_dir = Path("src/goa2/scripts")
    for script_path in scripts_dir.glob("*_effects.py"):
        module_name = f"goa2.scripts.{script_path.stem}"
        try:
            importlib.import_module(module_name)
            # print(f"Loaded effects from {module_name}")
        except Exception as e:
            print(f"Error loading {module_name}: {e}")


def verify_hero_effects():
    import_effect_scripts()

    heroes = hero_registry_module.HeroRegistry.list_heroes()

    if not heroes:
        print("No heroes found in registry!")
        return

    print(f"\nVerifying effects for {len(heroes)} heroes...\n")

    total_implemented = 0
    total_missing = 0

    for hero_name in heroes:
        hero = hero_registry_module.HeroRegistry.get(hero_name)
        if not hero:
            continue

        print(f"Hero: {hero.name}")
        print("=" * (len(hero.name) + 6))

        implemented = []
        missing = []

        for card in hero.deck:
            if not card.effect_id:
                continue

            effect = CardEffectRegistry.get(card.effect_id)
            if effect:
                implemented.append(f"{card.name} ({card.effect_id})")
            else:
                missing.append(f"{card.name} ({card.effect_id})")

        # Print results
        if implemented:
            print("\033[92m[✓] Implemented:\033[0m")
            for item in implemented:
                print(f"  - {item}")

        if missing:
            print("\033[91m[X] Missing:\033[0m")
            for item in missing:
                print(f"  - {item}")

        total = len(implemented) + len(missing)
        if total > 0:
            percentage = (len(implemented) / total) * 100
            print(f"\nProgress: {len(implemented)}/{total} ({percentage:.1f}%)")
        else:
            print("\nNo cards with effect_id found.")

        print("\n" + "-" * 40 + "\n")

        total_implemented += len(implemented)
        total_missing += len(missing)

    grand_total = total_implemented + total_missing
    if grand_total > 0:
        grand_percentage = (total_implemented / grand_total) * 100
        print(
            f"Total Progress: {total_implemented}/{grand_total} ({grand_percentage:.1f}%)"
        )


if __name__ == "__main__":
    verify_hero_effects()

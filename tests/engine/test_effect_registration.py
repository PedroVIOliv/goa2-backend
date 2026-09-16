"""Effect registration must not silently change the rules a process can run."""

import json
import subprocess
import sys
from textwrap import dedent
from typing import ClassVar

import pytest

from goa2 import bootstrap as effect_loader
from goa2.engine.effects import CardEffect, CardEffectRegistry


@pytest.fixture
def registry():
    # Isolate registration tests from the production registry populated at import.
    class Registry(CardEffectRegistry):
        _effects: ClassVar[dict[str, CardEffect]] = {}
        _spell_effects: ClassVar[dict[str, CardEffect]] = {}

    return Registry


@pytest.mark.parametrize("register_method", ["register", "register_spell"])
def test_duplicate_effect_id_cannot_replace_existing_behavior(registry, register_method):
    class OriginalEffect(CardEffect):
        pass

    class ConflictingEffect(CardEffect):
        pass

    register = getattr(registry, register_method)
    original = OriginalEffect()
    register("shared_id", original)

    with pytest.raises(ValueError, match=r"shared_id.*OriginalEffect.*ConflictingEffect"):
        register("shared_id", ConflictingEffect())

    effects = registry._effects if register_method == "register" else registry._spell_effects
    assert effects["shared_id"] is original


@pytest.mark.parametrize("register_method", ["register", "register_spell"])
def test_registering_the_same_effect_instance_is_idempotent(registry, register_method):
    register = getattr(registry, register_method)
    effect = CardEffect()
    register("same", effect)
    register("same", effect)


def test_cards_and_spells_can_use_the_same_effect_id(registry):
    from goa2.domain.models import Card, SpellCard

    card_effect, spell_effect = CardEffect(), CardEffect()
    registry.register("shared", card_effect)
    registry.register_spell("shared", spell_effect)

    # Only identity lookup is under test; no card action is executed.
    card = Card.model_construct(effect_id="shared", is_facedown=False)
    spell = SpellCard.model_construct(effect_id="shared", is_facedown=False)
    assert registry.get_for_card(card) is card_effect
    assert registry.get_for_card(spell) is spell_effect


@pytest.mark.parametrize("failure", [ImportError("missing dependency"), ValueError("bad rule")])
def test_effect_import_failure_stops_registration(monkeypatch, failure):
    def broken_import(module_name):
        raise failure

    monkeypatch.setattr(effect_loader.importlib, "import_module", broken_import)

    with pytest.raises(RuntimeError, match=r"goa2\.scripts\..*_effects") as exc:
        effect_loader.register_all_effects()

    assert exc.value.__cause__ is failure


def test_fresh_worker_loads_effects_without_importing_the_web_application():
    # A subprocess cannot inherit the registry or FastAPI imports from pytest's
    # collection. It reproduces the fresh interpreter used by spawn workers.
    _run_in_fresh_process("""
        import sys
        from goa2.server.workers import _init_worker
        from goa2.engine.effects import CardEffectRegistry

        _init_worker()
        original = CardEffectRegistry.get('liquid_leap')
        _init_worker()
        assert original is not None
        assert CardEffectRegistry.get('liquid_leap') is original
        assert 'goa2.server.app' not in sys.modules
        assert 'fastapi' not in sys.modules
        """)


def _run_in_fresh_process(source: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", dedent(source)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.effect_contract
def test_hero_catalog_effect_ids_resolve_to_registered_behavior():
    """Catch missing modules and misspelled IDs before cards reach a live game."""
    # Other tests register synthetic heroes and effects globally. Inspect the
    # bundled catalog in a fresh interpreter so collection order cannot affect it.
    output = _run_in_fresh_process("""
        import json
        from goa2.bootstrap import register_all_effects
        from goa2.data.heroes import HeroRegistry
        from goa2.engine.effects import CardEffectRegistry

        register_all_effects()
        unregistered = []
        for hero_name in HeroRegistry.list_heroes(include_playtest=True):
            hero = HeroRegistry.get(hero_name)
            cards = [*hero.deck, *hero.spells]
            if hero.ultimate_card is not None:
                cards.append(hero.ultimate_card)
            for card in cards:
                card.is_facedown = False
                if card.effect_id and CardEffectRegistry.get_for_card(card) is None:
                    unregistered.append((hero_name, str(card.id), card.effect_id))
        print(json.dumps(unregistered))
        """)
    unregistered = {tuple(entry) for entry in json.loads(output)}

    # These passive ultimates are implemented at explicit rule hooks rather
    # than through CardEffectRegistry. Exact equality also catches stale
    # exceptions if an ultimate moves into the registry in the future.
    assert unregistered == {
        # AdjacentToObstaclesFilter._over_the_top_applies
        ("Brynn", "over the top", "over_the_top"),
        # ignatia_effects._ultimate_active and its repeat sequences
        ("Ignatia", "chaos_incarnate", "chaos_incarnate"),
        # OfferRockUltimateStep, scheduled by Mrak's rock-placement effects
        ("Mrak", "rock_and_a_hard_place", "rock_and_a_hard_place"),
    }

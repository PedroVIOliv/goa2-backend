"""Shared fixtures for character effect contract and flow tests."""

import importlib


def pytest_configure() -> None:
    importlib.import_module("goa2.data.heroes.mortimer")
    importlib.import_module("goa2.data.heroes.widget")
    importlib.import_module("goa2.data.heroes.wuk")
    importlib.import_module("goa2.data.heroes.swift")
    importlib.import_module("goa2.data.heroes.mrak")
    importlib.import_module("goa2.data.heroes.cutter")
    importlib.import_module("goa2.data.heroes.hanu")
    importlib.import_module("goa2.data.heroes.brynn")
    importlib.import_module("goa2.data.heroes.ignatia")
    importlib.import_module("goa2.data.heroes.nebkher")
    importlib.import_module("goa2.scripts.arien_effects")
    importlib.import_module("goa2.scripts.brynn_effects")
    importlib.import_module("goa2.scripts.hanu_effects")
    importlib.import_module("goa2.scripts.cutter_effects")
    importlib.import_module("goa2.scripts.swift_effects")
    importlib.import_module("goa2.scripts.wuk_effects")
    importlib.import_module("goa2.scripts.mrak_effects")
    importlib.import_module("goa2.scripts.mortimer_effects")
    importlib.import_module("goa2.scripts.wasp_effects")
    importlib.import_module("goa2.scripts.whisper_effects")
    importlib.import_module("goa2.scripts.widget_effects")
    importlib.import_module("goa2.scripts.ignatia_effects")
    importlib.import_module("goa2.scripts.nebkher_effects")

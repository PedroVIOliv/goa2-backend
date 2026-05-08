"""Shared fixtures for character effect contract and flow tests."""

import importlib


def pytest_configure() -> None:
    importlib.import_module("goa2.data.heroes.mortimer")
    importlib.import_module("goa2.scripts.arien_effects")
    importlib.import_module("goa2.scripts.mortimer_effects")
    importlib.import_module("goa2.scripts.wasp_effects")
    importlib.import_module("goa2.scripts.whisper_effects")

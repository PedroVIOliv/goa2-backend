"""Shared fixtures for character effect contract and flow tests."""

from goa2.bootstrap import register_all_effects


def pytest_configure() -> None:
    register_all_effects()

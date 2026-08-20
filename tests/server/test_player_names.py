"""Resolution of caller-supplied player names to hero ids."""

from goa2.server.player_names import MAX_PLAYER_NAME_LENGTH, resolve_player_names

NAME_TO_ID = {"Arien": "hero_arien", "Wasp": "hero_wasp"}


def test_resolves_hero_names_to_hero_ids():
    assert resolve_player_names({"Arien": "Tuck"}, NAME_TO_ID) == {"hero_arien": "Tuck"}


def test_drops_names_for_heroes_not_in_the_game():
    result = resolve_player_names({"Arien": "Tuck", "Brynn": "Wisdom"}, NAME_TO_ID)
    assert result == {"hero_arien": "Tuck"}


def test_truncates_rather_than_rejects_long_names():
    long_name = "x" * 40
    result = resolve_player_names({"Arien": long_name}, NAME_TO_ID)
    assert result == {"hero_arien": "x" * MAX_PLAYER_NAME_LENGTH}


def test_strips_whitespace_and_drops_blank_names():
    result = resolve_player_names({"Arien": "  Tuck  ", "Wasp": "   "}, NAME_TO_ID)
    assert result == {"hero_arien": "Tuck"}


def test_empty_submission_yields_empty_map():
    assert resolve_player_names({}, NAME_TO_ID) == {}

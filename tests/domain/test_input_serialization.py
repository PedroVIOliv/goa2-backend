from __future__ import annotations

from goa2.domain.input import InputOption, InputRequestType, create_input_request


def _select_card_request(options: list[InputOption]) -> dict:
    return create_input_request(
        request_type=InputRequestType.SELECT_CARD,
        player_id="hero_nebkher",
        prompt="Choose a prepared spell to cast",
        options=options,
    ).to_dict()


def test_select_card_with_labels_includes_options() -> None:
    """A non-owner caster (e.g. NebKher's Mind Grip driving Gydion's cast)
    cannot resolve spell ids against their masked view, so labelled options
    must survive serialization for the client to render anything."""
    result = _select_card_request(
        [
            InputOption(id="burning_hands", text="Burning Hands"),
            InputOption(id="shield", text="Shield"),
        ]
    )
    assert result["valid_options"] == ["burning_hands", "shield"]
    assert result["options"] == [
        {"id": "burning_hands", "text": "Burning Hands"},
        {"id": "shield", "text": "Shield"},
    ]


def test_select_card_without_labels_omits_options() -> None:
    result = _select_card_request(
        [InputOption(id="card_1", text="card_1"), InputOption(id="card_2", text="card_2")]
    )
    assert result["valid_options"] == ["card_1", "card_2"]
    assert "options" not in result

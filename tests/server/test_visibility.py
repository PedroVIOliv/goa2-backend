"""Recipient-scoped server serialization regression tests."""

from goa2.domain.events import GameEvent, GameEventType
from goa2.domain.input import InputRequestType, create_input_request
from goa2.domain.models import TeamColor, TokenType
from goa2.domain.state import GameState
from goa2.engine.setup import GameSetup
from goa2.server.visibility import events_for_viewer, input_request_for_viewer

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"


def _state(seed: int = 1) -> GameState:
    return GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"], seed=seed)


def test_input_request_is_only_sent_to_its_responder():
    state = _state()
    request = create_input_request(
        InputRequestType.SELECT_CARD_OR_PASS,
        player_id="hero_wasp",
        prompt="Choose a defense",
        options=[
            {
                "id": "magnetic_dagger",
                "text": "Magnetic Dagger",
                "defense_value": 2,
            }
        ],
    )

    wasp_payload = input_request_for_viewer(request, state, "hero_wasp")
    assert wasp_payload is not None
    assert wasp_payload["options"][0]["id"] == "magnetic_dagger"
    assert input_request_for_viewer(request, state, "hero_arien") is None
    assert input_request_for_viewer(request, state, None) is None


def test_team_and_simultaneous_requests_are_narrowed_to_authorized_players():
    state = _state()
    team_request = create_input_request(
        InputRequestType.CHOOSE_ACTOR,
        player_id=f"team:{TeamColor.RED.value}",
        options=["hero_arien"],
    )
    assert input_request_for_viewer(team_request, state, "hero_arien") is not None
    assert input_request_for_viewer(team_request, state, "hero_wasp") is None

    simultaneous = create_input_request(
        InputRequestType.UPGRADE_PHASE,
        player_id="simultaneous",
        players={
            "hero_arien": {"options": ["arien_upgrade"]},
            "hero_wasp": {"options": ["wasp_upgrade"]},
        },
    )
    arien_payload = input_request_for_viewer(simultaneous, state, "hero_arien")
    wasp_payload = input_request_for_viewer(simultaneous, state, "hero_wasp")

    assert arien_payload["players"] == {"hero_arien": {"options": ["arien_upgrade"]}}
    assert wasp_payload["players"] == {"hero_wasp": {"options": ["wasp_upgrade"]}}
    assert input_request_for_viewer(simultaneous, state, None) is None


def test_facedown_mine_placement_event_masks_subtype_per_recipient():
    state = _state()
    mine = state.token_pool[TokenType.MINE_BLAST][0]
    mine.owner_id = "hero_arien"
    destination = next(hex_ for hex_, tile in state.board.tiles.items() if not tile.is_occupied)
    state.place_entity(mine.id, destination)
    placed = GameEvent(
        event_type=GameEventType.TOKEN_PLACED,
        actor_id="hero_arien",
        target_id=mine.id,
        metadata={"token_type": TokenType.MINE_BLAST.value},
    ).model_dump()

    owner_event = events_for_viewer([placed], state, "hero_arien")[0]
    enemy_event = events_for_viewer([placed], state, "hero_wasp")[0]
    spectator_event = events_for_viewer([placed], state, None)[0]

    assert owner_event["metadata"]["token_type"] == "mine_blast"
    assert enemy_event["metadata"]["token_type"] == "mine"
    assert spectator_event["metadata"]["token_type"] == "mine"

    triggered = {
        **placed,
        "event_type": GameEventType.MINE_TRIGGERED,
    }
    revealed = events_for_viewer([triggered], state, "hero_wasp")[0]
    assert revealed["metadata"]["token_type"] == "mine_blast"


def test_event_metadata_hides_private_card_ids_and_names():
    state = _state()
    arien = state.get_hero("hero_arien")
    card = arien.hand[0]
    event = GameEvent(
        event_type=GameEventType.DECK_CARD_SWAPPED,
        actor_id="hero_arien",
        metadata={
            "incoming_card_id": card.id,
            "incoming_card_name": card.name,
            "reason": "test",
        },
    ).model_dump()

    owner_event = events_for_viewer([event], state, "hero_arien")[0]
    enemy_event = events_for_viewer([event], state, "hero_wasp")[0]
    spectator_event = events_for_viewer([event], state, None)[0]

    assert owner_event["metadata"]["incoming_card_id"] == card.id
    assert owner_event["metadata"]["incoming_card_name"] == card.name
    for projected in (enemy_event, spectator_event):
        assert projected["metadata"]["incoming_card_id"] is None
        assert projected["metadata"]["incoming_card_name"] is None
        assert projected["metadata"]["reason"] == "test"

    arien.hand.remove(card)
    arien.discard_pile.append(card)
    card.is_facedown = False
    public_event = events_for_viewer([event], state, "hero_wasp")[0]
    assert public_event["metadata"]["incoming_card_id"] == card.id
    assert public_event["metadata"]["incoming_card_name"] == card.name

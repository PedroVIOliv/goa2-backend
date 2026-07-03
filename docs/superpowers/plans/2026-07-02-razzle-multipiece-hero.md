# Razzle Multi-Piece Hero Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the hero/piece abstraction so Razzle exists on the board as 1–4 `HeroPiece` entities (stable IDs, no "real one") while remaining a single player-level `Hero`, plus three validation cards (`stunt_doubles`, `crowd_control`, `phantom_strike`).

**Architecture:** Two-tier identity per approved spec `docs/superpowers/specs/2026-07-02-razzle-multipiece-design.md`: player-level identity (`current_actor_id`, `player_id`, turn machinery) keeps hero IDs; board-level identity (targets, victims, positions) uses stable piece IDs `hero_razzle_piece_1..4` stored in `misc_entities`. A set-valued position resolver on `GameState` intercepts hero-positional queries; `get_unit`/`get_hero` resolve pieces; four plumbing hooks (defense routing, defeat cascade, respawn, acting-piece binding) complete the loop.

**Tech Stack:** Python 3.11+, Pydantic V2, pytest. Run all tests with `PYTHONPATH=src uv run pytest tests/ -q`.

## Global Constraints

- Commit directly on `main` (user preference). No `Co-Authored-By` lines, no AI-tool mentions in commits.
- New steps MUST add a unique `StepType` in `domain/models/enums.py` and set it as the class `type` default (the `__init_subclass__` guard raises at import otherwise). Same for filters and `FilterType`.
- `HeroPiece` MUST be added to `AnyMiscEntity` in `engine/step_types.py` — that union is hand-maintained; forgetting it breaks persistence.
- Steps that change observable state MUST emit `GameEvent`s. Player input MUST use `create_input_request()` — never raw dicts.
- Effect tests use `tests/engine/effects/` helpers with `@pytest.mark.effect_flow` / `@pytest.mark.effect_contract`. Test file basenames must be unique across all `tests/` subdirs.
- Response-shape / view changes require updating `docs/CLIENT_INTEGRATION_GUIDE.md` (Task 10).
- After EVERY task: `PYTHONPATH=src uv run pytest tests/ -q` must pass (692+ existing tests are the regression net).

## File Structure

| File | Responsibility |
|---|---|
| `src/goa2/domain/models/unit.py` | Add `HeroPiece(Unit)` model; add `Hero.piece_supply` field |
| `src/goa2/engine/hero_pieces.py` (new) | `create_hero_pieces()`, `piece_id()`, `pieces_in_supply()` helpers |
| `src/goa2/domain/state.py` | `get_unit`/`get_hero` resolution; `get_positions`/`get_position`/`has_board_presence`/`get_piece_ids`/`resolve_board_actor`; `acting_piece_id` field; `place_marker` normalization |
| `src/goa2/engine/step_types.py` | `AnyMiscEntity` union entry |
| `src/goa2/engine/filters_hex.py` | `RangeFilter` origin via `get_position` |
| `src/goa2/engine/filters_units.py` | New `HeroPieceFilter` |
| `src/goa2/engine/stats.py` | `get_computed_stat` owner redirect; `_matches_affects_filter` piece-as-hero |
| `src/goa2/engine/steps/reactions.py` | `ReactionWindowStep` owner routing |
| `src/goa2/engine/steps/combat.py` | `DefeatUnitStep` cascade; `RespawnHeroStep` piece respawn |
| `src/goa2/engine/steps/cards.py` | `ResolveCardStep` off-board check, fast-travel any-piece, acting-piece hook |
| `src/goa2/engine/steps/movement.py` | `MoveSequenceStep`/`FastTravelSequenceStep` board-actor resolution |
| `src/goa2/engine/steps/phases.py` | `FinalizeHeroTurnStep` clears `acting_piece_id` |
| `src/goa2/engine/steps/pieces.py` (new) | `ChooseActingPieceStep`, `SpawnHeroPieceStep`, `RemoveHeroPieceStep` |
| `src/goa2/engine/setup.py` | Multi-piece hero initial placement |
| `src/goa2/domain/views.py` | `hero_pieces` view section |
| `src/goa2/scripts/razzle_effects.py` (new) | 3 validation card effects |
| `tests/engine/pieces/*.py` (new dir) | Infrastructure tests |
| `tests/engine/effects/cases/test_razzle_effects.py` (new) | Card effect tests |

---

### Task 1: `HeroPiece` model, registration, and lookup resolution

**Files:**
- Modify: `src/goa2/domain/models/unit.py` (add `HeroPiece`, `Hero.piece_supply`)
- Modify: `src/goa2/domain/models/__init__.py` (export `HeroPiece`)
- Modify: `src/goa2/engine/step_types.py:136-151` (AnyMiscEntity)
- Modify: `src/goa2/domain/state.py:283-314` (`get_hero`, `get_unit`)
- Create: `src/goa2/engine/hero_pieces.py`
- Test: `tests/engine/pieces/test_hero_piece_model.py`

**Interfaces:**
- Produces: `HeroPiece(Unit)` with fields `entity_kind: Literal["hero_piece"]`, `owner_hero_id: str`; `Hero.piece_supply: int = 0` (0 = hero is its own board piece) and `Hero.is_multi_piece` property; `piece_id(hero_id: str, index: int) -> str` returning `f"{hero_id}_piece_{index}"`; `create_hero_pieces(state, hero) -> list[HeroPiece]` registering all supply pieces into `misc_entities` (NOT placing them); `state.get_unit(piece_id)` returns the `HeroPiece`; `state.get_hero(piece_id)` returns the owning `Hero`.

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/pieces/__init__.py`? **No** — test dirs have no `__init__.py` (project convention). Create `tests/engine/pieces/test_hero_piece_model.py`:

```python
"""HeroPiece model, registration, and GameState lookup resolution."""

import pytest

from goa2.domain.hex import Hex
from goa2.domain.models import Hero, HeroPiece, Team, TeamColor
from goa2.domain.state import GameState
from goa2.engine.hero_pieces import create_hero_pieces, piece_id

from tests.engine.effects.builders import EffectScenarioBuilder


def _multi_piece_state() -> GameState:
    """Blue Knight vs a 4-supply Razzle with two pieces on board."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1), (1, 1, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    # Multi-piece heroes are never board entities themselves.
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_piece_id_format():
    assert piece_id("hero_razzle", 1) == "hero_razzle_piece_1"


def test_create_hero_pieces_registers_supply_in_misc_entities():
    state = _multi_piece_state()
    for i in range(1, 5):
        entity = state.misc_entities.get(piece_id("hero_razzle", i))
        assert isinstance(entity, HeroPiece)
        assert entity.owner_hero_id == "hero_razzle"
        assert entity.team == TeamColor.RED


def test_get_unit_resolves_piece():
    state = _multi_piece_state()
    unit = state.get_unit(piece_id("hero_razzle", 2))
    assert isinstance(unit, HeroPiece)


def test_get_hero_resolves_piece_to_owner():
    state = _multi_piece_state()
    hero = state.get_hero(piece_id("hero_razzle", 2))
    assert isinstance(hero, Hero)
    assert hero.id == "hero_razzle"


def test_get_hero_still_finds_normal_heroes():
    state = _multi_piece_state()
    assert state.get_hero("hero_knight").id == "hero_knight"
    assert state.get_hero("nonexistent") is None


def test_hero_piece_persistence_round_trip():
    state = _multi_piece_state()
    raw = state.model_dump_json()
    restored = GameState.model_validate_json(raw)
    entity = restored.misc_entities.get("hero_razzle_piece_1")
    assert isinstance(entity, HeroPiece)
    assert entity.owner_hero_id == "hero_razzle"
    assert restored.entity_locations.get("hero_razzle_piece_2") == Hex(q=1, r=0, s=-1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_hero_piece_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'HeroPiece'`

- [ ] **Step 3: Implement the model**

In `src/goa2/domain/models/unit.py`, after the `Unit` class (line 21), add:

```python
class HeroPiece(Unit):
    """One board piece of a multi-piece hero (e.g. Razzle).

    Multi-piece heroes never appear in entity_locations themselves; only their
    pieces do. Player-level state (hand, gold, markers, turn) stays on the
    owning Hero — resolve it via state.get_hero(piece.id).
    """

    entity_kind: Literal["hero_piece"] = "hero_piece"
    owner_hero_id: str
```

Add `from typing import Literal, TYPE_CHECKING` at the top (extend the existing `typing` import).

In the `Hero` class, after `team_obj` (line 55), add:

```python
    piece_supply: int = Field(
        default=0,
        description="Total board pieces for multi-piece heroes (e.g. Razzle: 4). "
        "0 = the hero itself is its board piece (all normal heroes).",
    )

    @property
    def is_multi_piece(self) -> bool:
        return self.piece_supply > 0
```

In `src/goa2/domain/models/__init__.py`, add `HeroPiece` to the import from `.unit` and to `__all__` (mirror how `Hero`/`Minion` are exported).

- [ ] **Step 4: Register in AnyMiscEntity**

In `src/goa2/engine/step_types.py`, extend the union (lines 136-151):

```python
from goa2.domain.models.base import Placeholder, Turret  # noqa: E402
from goa2.domain.models.token import Token  # noqa: E402
from goa2.domain.models.unit import HeroPiece  # noqa: E402

...

AnyMiscEntity = Annotated[
    Annotated[Token, Tag("token")]
    | Annotated[Turret, Tag("turret")]
    | Annotated[HeroPiece, Tag("hero_piece")]
    | Annotated[Placeholder, Tag("placeholder")],
    Discriminator(_misc_entity_discriminator),
]
```

- [ ] **Step 5: Implement lookup resolution in GameState**

In `src/goa2/domain/state.py`, replace `get_hero` (line 283) and extend `get_unit` (line 302):

```python
    def get_hero(self, hero_id: HeroID) -> Hero | None:
        """Finds a Hero by ID. A HeroPiece ID resolves to its owning Hero."""
        for team in self.teams.values():
            for hero in team.heroes:
                if hero.id == hero_id:
                    return hero
        # Piece IDs resolve to the player-level Hero that owns them.
        from goa2.domain.models.unit import HeroPiece

        entity = self.misc_entities.get(BoardEntityID(str(hero_id)))
        if isinstance(entity, HeroPiece):
            return self.get_hero(HeroID(entity.owner_hero_id))
        return None

    def get_unit(self, unit_id: UnitID) -> Unit | None:
        """
        Finds a Unit (Hero, Minion, or HeroPiece) by ID.
        O(N) search across all teams, then misc-entity units (hero pieces).
        """
        for team in self.teams.values():
            for hero in team.heroes:
                if str(hero.id) == str(unit_id):
                    return hero
            for minion in team.minions:
                if str(minion.id) == str(unit_id):
                    return minion
        entity = self.misc_entities.get(BoardEntityID(str(unit_id)))
        if isinstance(entity, Unit):
            return entity
        return None
```

- [ ] **Step 6: Create `src/goa2/engine/hero_pieces.py`**

```python
"""Helpers for multi-piece heroes (Razzle): piece creation and supply."""

from __future__ import annotations

from goa2.domain.models import Hero
from goa2.domain.models.unit import HeroPiece
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID


def piece_id(hero_id: str, index: int) -> str:
    """Stable board-entity ID for piece #index of a multi-piece hero."""
    return f"{hero_id}_piece_{index}"


def create_hero_pieces(state: GameState, hero: Hero) -> list[HeroPiece]:
    """Register all supply pieces for a multi-piece hero into misc_entities.

    Does NOT place them on the board. Idempotent: existing pieces are kept.
    """
    pieces: list[HeroPiece] = []
    for i in range(1, hero.piece_supply + 1):
        pid = BoardEntityID(piece_id(str(hero.id), i))
        existing = state.misc_entities.get(pid)
        if isinstance(existing, HeroPiece):
            pieces.append(existing)
            continue
        piece = HeroPiece(
            id=pid,
            name=hero.name,
            team=hero.team,
            owner_hero_id=str(hero.id),
        )
        state.register_entity(piece, "misc")
        pieces.append(piece)
    return pieces


def pieces_in_supply(state: GameState, hero: Hero) -> list[str]:
    """Piece IDs registered but not currently on the board."""
    return [
        piece_id(str(hero.id), i)
        for i in range(1, hero.piece_supply + 1)
        if BoardEntityID(piece_id(str(hero.id), i)) not in state.entity_locations
    ]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_hero_piece_model.py -v`
Expected: all PASS.

- [ ] **Step 8: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q` — expected: no regressions.

```bash
git add src/goa2/domain/models/unit.py src/goa2/domain/models/__init__.py src/goa2/engine/step_types.py src/goa2/domain/state.py src/goa2/engine/hero_pieces.py tests/engine/pieces/test_hero_piece_model.py
git commit -m "feat: add HeroPiece model with misc-entity registration and lookup resolution"
```

---

### Task 2: Position resolver + `acting_piece_id` + marker normalization

**Files:**
- Modify: `src/goa2/domain/state.py`
- Test: `tests/engine/pieces/test_position_resolver.py`

**Interfaces:**
- Consumes: `HeroPiece`, `piece_id()` from Task 1.
- Produces on `GameState`: `acting_piece_id: BoardEntityID | None = None` (serialized field); `get_piece_ids(hero_id: str) -> list[str]` (on-board pieces; `[hero_id]` for a normal on-board hero, `[]` if off-board); `get_positions(entity_id: str) -> list[Hex]`; `get_position(entity_id: str) -> Hex | None` (bound contexts: multi-piece hero resolves through `acting_piece_id`); `has_board_presence(hero_id: str) -> bool`; `resolve_board_actor(unit_id: str) -> str` (multi-piece hero mid-action → acting piece ID, else identity); `place_marker` normalizes piece target IDs to the owner hero ID.

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/pieces/test_position_resolver.py`:

```python
"""GameState position resolver for multi-piece heroes."""

from goa2.domain.hex import Hex
from goa2.domain.models.marker import MarkerType
from goa2.domain.state import GameState
from goa2.engine.hero_pieces import create_hero_pieces, piece_id

from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_get_positions_returns_all_piece_hexes():
    state = _state()
    positions = state.get_positions("hero_razzle")
    assert set(positions) == {Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)}


def test_get_positions_normal_hero():
    state = _state()
    assert state.get_positions("hero_knight") == [Hex(q=2, r=0, s=-2)]


def test_get_position_multi_piece_unbound_is_none():
    state = _state()
    assert state.get_position("hero_razzle") is None


def test_get_position_resolves_acting_piece():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 2)
    assert state.get_position("hero_razzle") == Hex(q=1, r=0, s=-1)


def test_get_position_piece_id_direct():
    state = _state()
    assert state.get_position(piece_id("hero_razzle", 1)) == Hex(q=0, r=0, s=0)


def test_has_board_presence():
    state = _state()
    assert state.has_board_presence("hero_razzle") is True
    state.remove_entity(piece_id("hero_razzle", 1))
    state.remove_entity(piece_id("hero_razzle", 2))
    assert state.has_board_presence("hero_razzle") is False
    assert state.has_board_presence("hero_knight") is True


def test_get_piece_ids():
    state = _state()
    assert state.get_piece_ids("hero_razzle") == [
        piece_id("hero_razzle", 1),
        piece_id("hero_razzle", 2),
    ]
    assert state.get_piece_ids("hero_knight") == ["hero_knight"]


def test_resolve_board_actor():
    state = _state()
    assert state.resolve_board_actor("hero_knight") == "hero_knight"
    state.acting_piece_id = piece_id("hero_razzle", 2)
    assert state.resolve_board_actor("hero_razzle") == piece_id("hero_razzle", 2)


def test_place_marker_on_piece_attaches_to_hero():
    state = _state()
    marker = state.place_marker(
        MarkerType.BOUNTY, target_id=piece_id("hero_razzle", 2), value=1, source_id="hero_knight"
    )
    assert marker.target_id == "hero_razzle"
    assert state.get_markers_on_hero("hero_razzle") == [marker]


def test_acting_piece_id_round_trips():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 1)
    restored = GameState.model_validate_json(state.model_dump_json())
    assert restored.acting_piece_id == piece_id("hero_razzle", 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_position_resolver.py -v`
Expected: FAIL — `AttributeError: 'GameState' object has no attribute 'get_positions'` (and similar).

- [ ] **Step 3: Implement on GameState**

In `src/goa2/domain/state.py`, add a field after `next_entity_id` (line 101):

```python
    # Multi-piece heroes (Razzle): the piece performing the current action.
    # Bound by ChooseActingPieceStep, cleared by FinalizeHeroTurnStep.
    acting_piece_id: BoardEntityID | None = None
```

Add methods after `get_units_and_tokens` (line 357):

```python
    def _multi_piece_hero(self, entity_id: str) -> Hero | None:
        """Return the Hero if entity_id names a multi-piece hero, else None."""
        for team in self.teams.values():
            for hero in team.heroes:
                if str(hero.id) == str(entity_id) and hero.is_multi_piece:
                    return hero
        return None

    def get_piece_ids(self, hero_id: str) -> list[str]:
        """On-board piece IDs for a hero. Normal on-board hero → [hero_id]."""
        from goa2.engine.hero_pieces import piece_id as _piece_id

        hero = self._multi_piece_hero(hero_id)
        if hero is None:
            if BoardEntityID(str(hero_id)) in self.entity_locations:
                return [str(hero_id)]
            return []
        return [
            _piece_id(str(hero.id), i)
            for i in range(1, hero.piece_supply + 1)
            if BoardEntityID(_piece_id(str(hero.id), i)) in self.entity_locations
        ]

    def get_positions(self, entity_id: str) -> list[Hex]:
        """All board positions for an entity. Multi-piece hero → all piece hexes."""
        if self._multi_piece_hero(entity_id) is not None:
            return [
                self.entity_locations[BoardEntityID(pid)]
                for pid in self.get_piece_ids(entity_id)
            ]
        loc = self.entity_locations.get(BoardEntityID(str(entity_id)))
        return [loc] if loc else []

    def get_position(self, entity_id: str) -> Hex | None:
        """Single position — bound contexts only.

        Multi-piece hero IDs resolve through acting_piece_id (None if unbound).
        Everything else is a direct entity_locations lookup.
        """
        direct = self.entity_locations.get(BoardEntityID(str(entity_id)))
        if direct is not None:
            return direct
        hero = self._multi_piece_hero(entity_id)
        if hero is not None and self.acting_piece_id:
            piece = self.misc_entities.get(self.acting_piece_id)
            if piece is not None and getattr(piece, "owner_hero_id", None) == str(hero.id):
                return self.entity_locations.get(self.acting_piece_id)
        return None

    def has_board_presence(self, hero_id: str) -> bool:
        """True if the hero (or any of its pieces) is on the board."""
        return bool(self.get_positions(hero_id))

    def resolve_board_actor(self, unit_id: str) -> str:
        """Board entity that physically performs an action for unit_id.

        Multi-piece hero with a bound acting piece → the piece ID; else identity.
        """
        if self._multi_piece_hero(unit_id) is not None and self.acting_piece_id:
            piece = self.misc_entities.get(self.acting_piece_id)
            if piece is not None and getattr(piece, "owner_hero_id", None) == str(unit_id):
                return str(self.acting_piece_id)
        return str(unit_id)
```

Modify `place_marker` (line 127) to normalize piece targets:

```python
    def place_marker(
        self, marker_type: MarkerType, target_id: str, value: int, source_id: str
    ) -> Marker:
        """
        Place a marker on a target hero.
        Markers always attach to the HERO: a HeroPiece target resolves to its
        owner (rules ruling — a marker on any Razzle affects all Razzles).
        If marker was on another hero, it automatically leaves them (singleton).
        """
        from goa2.domain.models.unit import HeroPiece

        entity = self.misc_entities.get(BoardEntityID(str(target_id)))
        if isinstance(entity, HeroPiece):
            target_id = entity.owner_hero_id

        marker = self.get_marker(marker_type)
        marker.place(target_id=target_id, value=value, source_id=source_id)
        return marker
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_position_resolver.py -v`
Expected: all PASS.

- [ ] **Step 5: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q` — expected: no regressions.

```bash
git add src/goa2/domain/state.py tests/engine/pieces/test_position_resolver.py
git commit -m "feat: add set-valued position resolver, acting_piece_id, marker normalization"
```

---

### Task 3: Razzle hero data flag + game-setup placement

**Files:**
- Modify: `src/goa2/data/heroes/razzle.py` (set `piece_supply=4`)
- Modify: `src/goa2/engine/setup.py:196-242` (`_setup_team`)
- Test: `tests/engine/pieces/test_piece_setup.py`

**Interfaces:**
- Consumes: `create_hero_pieces`, `piece_id`, `Hero.is_multi_piece`.
- Produces: games created via `GameSetup.create_game` place `hero_razzle_piece_1` at the spawn point instead of `hero_razzle`; all 4 pieces registered in `misc_entities`.

- [ ] **Step 1: Write the failing test**

Create `tests/engine/pieces/test_piece_setup.py`:

```python
"""Game setup places pieces (not the hero) for multi-piece heroes."""

from goa2.engine.setup import GameSetup


def test_create_game_places_piece_not_hero():
    state = GameSetup.create_game(
        map_name="map_2v2",
        red_heroes=["Razzle", "Wasp"],
        blue_heroes=["Knight", "Tali"],
    )
    assert "hero_razzle" not in state.entity_locations
    assert "hero_razzle_piece_1" in state.entity_locations
    # Supply pieces registered but off-board
    for i in (2, 3, 4):
        assert f"hero_razzle_piece_{i}" in state.misc_entities
        assert f"hero_razzle_piece_{i}" not in state.entity_locations
    # Normal heroes unaffected
    assert "hero_knight" in state.entity_locations
    assert state.has_board_presence("hero_razzle")
```

Note: check the exact `map_name` and hero-name strings used by existing setup tests (e.g. `tests/engine/test_setup*.py` or `tests/server/`) and mirror them; adjust `map_name` to a map that exists in `src/goa2/data/maps/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_setup.py -v`
Expected: FAIL — `hero_razzle` IS in `entity_locations` (placed by `_setup_team`).

- [ ] **Step 3: Implement**

In `src/goa2/data/heroes/razzle.py`, add `piece_supply=4` to the `Hero(...)` construction at the bottom:

```python
    h = Hero(
        id=HeroID("hero_razzle"),
        name="Razzle",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
        piece_supply=4,
    )
```

In `src/goa2/engine/setup.py` `_setup_team`, replace the placement block (`# C. Place on Board` through the `logger.warning`) with:

```python
            # C. Place on Board
            # Find an empty spawn point
            spawn_loc = None

            for sp in available_spawns:
                tile = state.board.get_tile(sp.location)
                if tile and not tile.is_occupied:
                    spawn_loc = sp.location
                    break

            if spawn_loc:
                if hero.is_multi_piece:
                    # Multi-piece heroes (Razzle) never occupy the board
                    # themselves: register the piece supply and place piece 1.
                    from goa2.engine.hero_pieces import create_hero_pieces, piece_id

                    create_hero_pieces(state, hero)
                    state.place_entity(piece_id(str(hero.id), 1), spawn_loc)
                else:
                    state.place_entity(hero.id, spawn_loc)
            else:
                logger.warning("No spawn point available for %s", hero.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_setup.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/data/heroes/razzle.py src/goa2/engine/setup.py tests/engine/pieces/test_piece_setup.py
git commit -m "feat: place hero pieces at setup for multi-piece heroes"
```

---

### Task 4: Targeting & stats integration (pieces as enemy hero units)

**Files:**
- Modify: `src/goa2/engine/filters_hex.py:162-225` (`RangeFilter` origin)
- Modify: `src/goa2/engine/stats.py:84-235` (`_matches_affects_filter`, `get_computed_stat`)
- Test: `tests/engine/pieces/test_piece_targeting.py`

**Interfaces:**
- Consumes: resolver from Task 2.
- Produces: `SelectStep(target_type=UNIT)` enumerates pieces (emergent from Task 1's `get_unit`); `TeamFilter`/`RangeFilter` match pieces; `RangeFilter` actor-origin works for a bound multi-piece actor; `get_computed_stat(state, piece_id, ...)` applies the owner's items/auras/markers; `AffectsFilter.ENEMY_HEROES`/`ALL_HEROES` match pieces.

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/pieces/test_piece_targeting.py`:

```python
"""Pieces behave as independent enemy hero units for targeting and stats."""

from goa2.domain.hex import Hex
from goa2.domain.models import StatType, TeamColor
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.filters_hex import RangeFilter
from goa2.engine.filters_units import TeamFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import get_computed_stat, is_unit_in_effect_scope
from goa2.engine.steps.selection import SelectStep
from goa2.domain.models.enums import TargetType

from tests.engine.effects.builders import EffectScenarioBuilder


def _state(actor: str = "hero_knight") -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor(actor)
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_enemy_select_step_offers_pieces():
    state = _state()
    push_steps(
        state,
        [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select Attack Target",
                output_key="victim_id",
                filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
            )
        ],
    )
    result = process_stack(state)
    assert result.input_request is not None
    option_ids = {o.id for o in result.input_request.options}
    # knight at (2,0,-2): piece_2 at (1,0,-1) is adjacent, piece_1 is not
    assert piece_id("hero_razzle", 2) in option_ids
    assert piece_id("hero_razzle", 1) not in option_ids
    assert "hero_razzle" not in option_ids


def test_range_filter_origin_resolves_acting_piece():
    state = _state(actor="hero_razzle")
    state.acting_piece_id = piece_id("hero_razzle", 2)
    # knight at (2,0,-2) is adjacent to piece_2 at (1,0,-1)
    f = RangeFilter(max_range=1)
    assert f.apply("hero_knight", state, {}) is True
    state.acting_piece_id = piece_id("hero_razzle", 1)
    assert f.apply("hero_knight", state, {}) is False


def test_computed_stat_applies_owner_items_to_piece():
    state = _state()
    razzle = state.get_hero("hero_razzle")
    razzle.items[StatType.DEFENSE] = 2
    total = get_computed_stat(state, piece_id("hero_razzle", 2), StatType.DEFENSE, 1)
    assert total == 3


def test_area_modifier_hits_piece_in_scope_only():
    state = _state()
    effect = ActiveEffect(
        id="area_test",
        source_id="hero_knight",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(shape=Shape.RADIUS, range=1, affects=AffectsFilter.ENEMY_HEROES),
        stat_type=StatType.DEFENSE,
        stat_value=-1,
        duration=DurationType.THIS_ROUND,
        created_at_round=state.round,
        created_at_turn=state.turn,
        is_active=True,
    )
    state.add_effect(effect)
    # piece_2 adjacent to knight → in scope; piece_1 two away → out of scope
    assert is_unit_in_effect_scope(effect, piece_id("hero_razzle", 2), state) is True
    assert is_unit_in_effect_scope(effect, piece_id("hero_razzle", 1), state) is False
    assert get_computed_stat(state, piece_id("hero_razzle", 2), StatType.DEFENSE, 1) == 0
    assert get_computed_stat(state, piece_id("hero_razzle", 1), StatType.DEFENSE, 1) == 1
```

Note: check `ActiveEffect`'s exact required fields against `src/goa2/domain/models/effect.py` (e.g. `created_at_round`/`created_at_turn`/`is_active` names) and adjust the constructor to match — mirror an existing test that builds an `ActiveEffect` by hand.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_targeting.py -v`
Expected: `test_enemy_select_step_offers_pieces` may already PASS (emergent from Task 1). `test_range_filter_origin_resolves_acting_piece`, `test_computed_stat_applies_owner_items_to_piece`, and the area test FAIL.

- [ ] **Step 3: Implement `RangeFilter` origin resolution**

In `src/goa2/engine/filters_hex.py` (line ~214), replace the origin lookup:

```python
            origin_hex = state.get_position(str(origin_uid))
            if not origin_hex:
                return False
```

(was `origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))`).

- [ ] **Step 4: Implement stats owner redirect**

In `src/goa2/engine/stats.py`:

In `_matches_affects_filter` (line 99-100), treat pieces as heroes:

```python
    from goa2.domain.models.unit import HeroPiece

    is_hero = isinstance(target, (Hero, HeroPiece))
    is_minion = isinstance(target, Minion)
```

In `get_computed_stat` (line 150), resolve the owner once and use it for all hero-level branches. Replace `unit = state.get_unit(unit_id)` and the three `isinstance(unit, Hero)` gates:

```python
    unit = state.get_unit(unit_id)
    if not unit:
        return base_value

    # A HeroPiece computes hero-level bonuses (items, auras, markers) from its
    # owning Hero, while positional checks below keep using the piece's own id.
    hero_owner: Hero | None = unit if isinstance(unit, Hero) else None
    if hero_owner is None:
        from goa2.domain.models.unit import HeroPiece

        if isinstance(unit, HeroPiece):
            hero_owner = state.get_hero(str(unit_id))
```

Then change each `if isinstance(unit, Hero):` gate (branches 1, 3, 4) to `if hero_owner is not None:` and inside them replace `unit.items` → `hero_owner.items`, `get_active_aura_effects(state, unit)` → `get_active_aura_effects(state, hero_owner)`, `unit.current_turn_card` → `hero_owner.current_turn_card`, and in branch 4 `state.get_markers_on_hero(str(unit_id))` → `state.get_markers_on_hero(str(hero_owner.id))`. Leave every positional use of `unit_id` (scope checks, `entity_locations` reads, `current_actor_id` swap) untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_targeting.py -v`
Expected: all PASS.

- [ ] **Step 6: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/engine/filters_hex.py src/goa2/engine/stats.py tests/engine/pieces/test_piece_targeting.py
git commit -m "feat: pieces target and compute stats as independent enemy hero units"
```

---

### Task 5: Defense path — owner routing in ReactionWindowStep

**Files:**
- Modify: `src/goa2/engine/steps/reactions.py:33-193`
- Test: `tests/engine/pieces/test_piece_defense.py`

**Interfaces:**
- Consumes: `get_hero` piece resolution (Task 1), stats redirect (Task 4).
- Produces: attacking a piece opens the owner's defense window with `input_request.player_id == owner_hero_id`; `context["defender_id"]` remains the PIECE id; the discarded defense card routes to the owner (`DiscardCardStep(hero_id=owner)`).

- [ ] **Step 1: Write the failing test**

Create `tests/engine/pieces/test_piece_defense.py`:

```python
"""Attacking a piece routes defense to the owning player."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import AttackSequenceStep

from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_attacking_piece_prompts_owner_for_defense():
    state = _state()
    push_steps(state, [AttackSequenceStep(damage=4, range_val=1)])
    result = process_stack(state)
    # Target selection: pick the adjacent piece
    assert result.input_request.request_type.value == "SELECT_UNIT"
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    result = process_stack(state)
    # Defense window must be addressed to the OWNER hero (token routing)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_CARD_OR_PASS"
    assert result.input_request.player_id == "hero_razzle"
    # Positional truth: defender_id stays the piece
    assert state.execution_context["attacker_id"] == "hero_knight"


def test_defense_pass_defeats_and_defender_id_is_piece():
    state = _state()
    push_steps(state, [AttackSequenceStep(damage=4, range_val=1)])
    result = process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    result = process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "PASS"}
    result = process_stack(state)
    assert state.execution_context["defender_id"] == piece_id("hero_razzle", 2)
```

Note: `test_defense_pass...` will drive into `DefeatUnitStep`, which is only fixed in Task 6 — if it raises or misbehaves past the `defender_id` assertion, drain only as far as needed (assert the context right after the PASS resolution; if `process_stack` runs to completion and Task-6 behavior interferes, split the assertion to before defeat by pushing `ReactionWindowStep` alone instead of the full `AttackSequenceStep`). Keep the test focused on defense routing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_defense.py -v`
Expected: FAIL — `player_id` is the piece ID (or the reaction is skipped entirely if `get_hero` isn't consulted — with Task 1 in place, `get_hero(piece)` resolves, so the failure is `player_id == "hero_razzle_piece_2"`).

- [ ] **Step 3: Implement owner routing**

In `src/goa2/engine/steps/reactions.py` `ReactionWindowStep.resolve`, after `target_hero = state.get_hero(target_id)` (line 38) add:

```python
        # Multi-piece heroes: target_id may be a piece. All PLAYER-level uses
        # (prompt routing, card ownership, stats-by-hero) go through the owner;
        # defender_id keeps the piece id (positional truth).
        owner_id = str(target_hero.id) if target_hero else str(target_id)
```

Then apply these substitutions in the rest of the method:

- `get_computed_stat(state, target_id, StatType.DEFENSE, base_def)` (line 88) → keep `target_id` (piece) — stats redirect from Task 4 handles the owner items; positional modifiers must use the piece. **No change.**
- `create_input_request(request_type=..., player_id=str(target_id), ...)` (line 185) → `player_id=owner_id`.
- Prompt strings `f"Player {target_id}, ..."` (lines 174-180) → `f"Player {owner_id}, ..."`.
- `DiscardCardStep(card_id=card_id, hero_id=str(target_id))` (line 163) → `hero_id=owner_id`.
- All `context["defender_id"] = str(target_id)` assignments (lines 46, 107, 143) — **unchanged** (piece id).
- `calculate_minion_defense_modifier(state, target_id)` (line 170) — **unchanged** (positional).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_defense.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/engine/steps/reactions.py tests/engine/pieces/test_piece_defense.py
git commit -m "feat: route piece defense windows to the owning player"
```

---

### Task 6: Defeat cascade — any piece defeated defeats the hero

**Files:**
- Modify: `src/goa2/engine/steps/combat.py:307-525` (`DefeatUnitStep`)
- Test: `tests/engine/pieces/test_piece_defeat.py`

**Interfaces:**
- Consumes: `get_hero`/`get_piece_ids` (Tasks 1-2).
- Produces: `DefeatUnitStep` with a piece victim translates to the owner hero (rewards once, life counters once, markers returned, unresolved-pool removal) and removes ALL of the owner's pieces.

- [ ] **Step 1: Write the failing test**

Create `tests/engine/pieces/test_piece_defeat.py`:

```python
"""Defeating any piece defeats the hero: rewards once, all pieces removed."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import DefeatUnitStep

from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    state.place_entity(piece_id("hero_razzle", 3), Hex(q=0, r=1, s=-1))
    return state


def test_defeating_one_piece_removes_all_and_rewards_once():
    state = _state()
    knight = state.get_hero("hero_knight")
    razzle = state.get_hero("hero_razzle")
    gold_before = knight.gold
    life_before = state.teams[razzle.team].life_counters

    push_steps(state, [DefeatUnitStep(victim_id=piece_id("hero_razzle", 2), killer_id="hero_knight")])
    process_stack(state)

    for i in (1, 2, 3):
        assert piece_id("hero_razzle", i) not in state.entity_locations
    assert not state.has_board_presence("hero_razzle")
    # Level-1 kill reward = 1 gold, exactly once
    assert knight.gold == gold_before + 1
    # Exactly one life counter penalty
    assert state.teams[razzle.team].life_counters == life_before - 1
    assert "hero_razzle" in state.heroes_defeated_this_round
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_defeat.py -v`
Expected: FAIL — `HeroPiece` has neither `level` nor `value`, so no rewards fire and only the one piece is removed.

- [ ] **Step 3: Implement the translation + cascade**

In `DefeatUnitStep.resolve` (`combat.py:322`), right after `victim = state.get_unit(...)` / the `if not victim: raise` block (line 338), insert:

```python
        # Multi-piece heroes: defeating ANY piece defeats the hero.
        # Translate the victim to the owning Hero for all player-level
        # consequences, and remove every on-board piece at the end.
        from goa2.domain.models.unit import HeroPiece

        removal_ids = [actual_victim_id]
        if isinstance(victim, HeroPiece):
            owner = state.get_hero(HeroID(actual_victim_id))
            if owner is None:
                raise ValueError(f"HeroPiece {actual_victim_id} has no owner hero")
            removal_ids = state.get_piece_ids(str(owner.id))
            victim = owner
            actual_victim_id = str(owner.id)
            logger.debug(
                f"   [DEATH] Piece defeat → hero defeat of {actual_victim_id}; "
                f"removing pieces {removal_ids}"
            )
```

Then replace the two `RemoveUnitStep` constructions:

- ANNIHILATION branch (line 492): `RemoveUnitStep(unit_id=actual_victim_id),` → `*[RemoveUnitStep(unit_id=rid) for rid in removal_ids],`
- Final return (line 523): `new_steps=[RemoveUnitStep(unit_id=actual_victim_id)],` → `new_steps=[RemoveUnitStep(unit_id=rid) for rid in removal_ids],`

Everything between (markers, bounty, gold, life counters, `heroes_defeated_this_round`, `unresolved_hero_ids`, `resolve_current_card`) now operates on the owner Hero via the translated `victim`/`actual_victim_id` — no further changes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_defeat.py tests/engine/pieces/test_piece_defense.py -v`
Expected: PASS (including the Task-5 pass-defeat flow end-to-end now).

- [ ] **Step 5: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/engine/steps/combat.py tests/engine/pieces/test_piece_defeat.py
git commit -m "feat: piece defeat cascades to hero defeat with full piece removal"
```

---

### Task 7: Respawn + off-board check migration

**Files:**
- Modify: `src/goa2/engine/steps/combat.py:761-841` (`RespawnHeroStep`)
- Modify: `src/goa2/engine/steps/cards.py:616,636-639,791,1608` (`ResolveCardStep` off-board + fast travel; other hero-loc reads)
- Test: `tests/engine/pieces/test_piece_respawn.py`

**Interfaces:**
- Consumes: `has_board_presence`, `get_positions`, `pieces_in_supply` (Tasks 1-2).
- Produces: `RespawnHeroStep` skips heroes with any piece on board and respawns multi-piece heroes as ONE piece (lowest-index supply piece); `ResolveCardStep` skips actions only when no piece is on board; fast travel available if any piece is in a qualifying zone.

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/pieces/test_piece_respawn.py`:

```python
"""Respawn semantics for multi-piece heroes."""

from goa2.domain.hex import Hex
from goa2.domain.models.spawn import SpawnType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import RespawnHeroStep

from tests.engine.effects.builders import EffectScenarioBuilder


def _state(pieces_on_board: int) -> GameState:
    builder = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .spawn_point(at=(0, 1, -1), team="RED", spawn_type=SpawnType.HERO)
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
    )
    state = builder.build()
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1)]
    for i in range(pieces_on_board):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_no_respawn_prompt_while_pieces_on_board():
    state = _state(pieces_on_board=1)
    push_steps(state, [RespawnHeroStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is None  # step finished silently


def test_respawn_places_one_piece():
    state = _state(pieces_on_board=0)
    push_steps(state, [RespawnHeroStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request.request_type.value == "CHOOSE_RESPAWN"
    state.execution_stack[-1].pending_input = {"selection": "RESPAWN"}
    result = process_stack(state)
    assert result.input_request.request_type.value == "CHOOSE_RESPAWN_HEX"
    hex_option = result.input_request.options[0]
    state.execution_stack[-1].pending_input = {
        "selection": hex_option.metadata["hex"]
    }
    process_stack(state)
    assert piece_id("hero_razzle", 1) in state.entity_locations
    assert "hero_razzle" not in state.entity_locations
    assert state.has_board_presence("hero_razzle")
```

Note: check `.spawn_point(...)` signature in `tests/engine/effects/builders.py` and the hex-option metadata key (`metadata["hex"]` vs `metadata["raw"]`) against an existing respawn test — mirror the closest existing test (`grep -rn "CHOOSE_RESPAWN" tests/`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_respawn.py -v`
Expected: `test_no_respawn_prompt_while_pieces_on_board` FAILS (prompt appears — `hero_razzle` isn't in `unit_locations`); `test_respawn_places_one_piece` FAILS (respawn places `hero_razzle` itself via `move_unit`).

- [ ] **Step 3: Implement respawn changes**

In `RespawnHeroStep.resolve` (`combat.py:770`):

Replace the on-board check (line 776):

```python
        # Only respawn if not on board (any piece counts for multi-piece heroes)
        if state.has_board_presence(self.hero_id):
            return StepResult(is_finished=True)
```

Replace the placement (line 790):

```python
            if selected_hex_dict:
                selected_hex = Hex(**selected_hex_dict)
                logger.debug(f"   [RESPAWN] {self.hero_id} respawning at {selected_hex}")
                if hero.is_multi_piece:
                    from goa2.engine.hero_pieces import pieces_in_supply

                    supply = pieces_in_supply(state, hero)
                    state.place_entity(BoardEntityID(supply[0]), selected_hex)
                else:
                    state.move_unit(UnitID(self.hero_id), selected_hex)
                return StepResult(is_finished=True)
```

(`supply` is never empty here: the hero has no board presence, so all pieces are in supply.)

- [ ] **Step 4: Implement `ResolveCardStep` off-board + fast travel**

In `src/goa2/engine/steps/cards.py`:

Line 616:

```python
        # If hero is off-board (didn't respawn), skip action
        if not state.has_board_presence(self.hero_id):
            return StepResult(is_finished=True)
```

Fast travel check (line 636-639) — any-piece semantics:

```python
            if act_type == ActionType.FAST_TRAVEL:
                hero_positions = state.get_positions(self.hero_id)
                if not hero_positions:
                    return False
                zone_ids = {
                    z for z in (state.board.get_zone_for_hex(loc) for loc in hero_positions) if z
                }
                if not zone_ids:
                    return False

                if not hero:
                    return False

                # Ensure team is present
                team = getattr(hero, "team", None)
                if not team:
                    return False

                safe = [
                    z for zid in zone_ids for z in get_safe_zones_for_fast_travel(state, team, zid)
                ]
                if not safe:
                    return False
```

Line 791 (CLEAR action hero location) and line 1608: replace `state.entity_locations.get(BoardEntityID(self.hero_id))` / `state.entity_locations.get(hero.id)` with `state.get_position(self.hero_id)` / `state.get_position(str(hero.id))` respectively (bound context — the acting piece is set by then; if unbound the behavior matches today's off-board fallback). Read 10 lines around each before editing to confirm the variable use.

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_respawn.py -v`
Expected: PASS.

- [ ] **Step 6: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/engine/steps/combat.py src/goa2/engine/steps/cards.py tests/engine/pieces/test_piece_respawn.py
git commit -m "feat: multi-piece-aware respawn and off-board checks"
```

---

### Task 8: Acting-piece binding

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (add `CHOOSE_ACTING_PIECE = "choose_acting_piece"` to `StepType`)
- Create: `src/goa2/engine/steps/pieces.py` (`ChooseActingPieceStep`)
- Modify: `src/goa2/engine/steps/__init__.py` (re-export)
- Modify: `src/goa2/engine/steps/cards.py:744` (prepend hook in `ResolveCardStep`)
- Modify: `src/goa2/engine/steps/movement.py:255` (`MoveSequenceStep` board actor), and the same pattern in `FastTravelSequenceStep`
- Modify: `src/goa2/engine/steps/phases.py:66` area (`FinalizeHeroTurnStep` clears binding)
- Test: `tests/engine/pieces/test_acting_piece.py`

**Interfaces:**
- Consumes: `resolve_board_actor`, `get_piece_ids`, `acting_piece_id` (Task 2).
- Produces: `ChooseActingPieceStep(hero_id: str)` — no-op for normal heroes; auto-binds a single piece; prompts `SELECT_UNIT` among own pieces when ≥2. `MoveSequenceStep`/`FastTravelSequenceStep` act on `state.resolve_board_actor(...)`. `FinalizeHeroTurnStep` sets `state.acting_piece_id = None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/pieces/test_acting_piece.py`:

```python
"""Acting-piece binding: choice prompt, auto-bind, movement via the piece."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.movement import MoveSequenceStep
from goa2.engine.steps.pieces import ChooseActingPieceStep

from tests.engine.effects.builders import EffectScenarioBuilder


def _state(n_pieces: int) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(3, 0, -3))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1)]
    for i in range(n_pieces):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_single_piece_auto_binds_without_prompt():
    state = _state(n_pieces=1)
    push_steps(state, [ChooseActingPieceStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is None
    assert state.acting_piece_id == piece_id("hero_razzle", 1)


def test_two_pieces_prompt_and_bind():
    state = _state(n_pieces=2)
    push_steps(state, [ChooseActingPieceStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.player_id == "hero_razzle"
    option_ids = {o.id for o in result.input_request.options}
    assert option_ids == {piece_id("hero_razzle", 1), piece_id("hero_razzle", 2)}
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    process_stack(state)
    assert state.acting_piece_id == piece_id("hero_razzle", 2)


def test_normal_hero_is_noop():
    state = _state(n_pieces=1)
    push_steps(state, [ChooseActingPieceStep(hero_id="hero_knight")])
    result = process_stack(state)
    assert result.input_request is None
    assert state.acting_piece_id is None


def test_move_sequence_moves_the_bound_piece():
    state = _state(n_pieces=2)
    state.acting_piece_id = piece_id("hero_razzle", 2)
    push_steps(state, [MoveSequenceStep(unit_id="hero_razzle", range_val=1)])
    result = process_stack(state)
    assert result.input_request is not None  # destination hex selection
    dest = {"q": 2, "r": 0, "s": -2}
    state.execution_stack[-1].pending_input = {"selection": dest}
    process_stack(state)
    assert state.entity_locations[piece_id("hero_razzle", 2)] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations[piece_id("hero_razzle", 1)] == Hex(q=0, r=0, s=0)
```

Note: mirror the hex-selection input format (`{"selection": {...}}` vs metadata extraction) from an existing `MoveSequenceStep` test (`grep -rn "MoveSequenceStep" tests/ | head`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_acting_piece.py -v`
Expected: FAIL — `ModuleNotFoundError: goa2.engine.steps.pieces`.

- [ ] **Step 3: Add the StepType and implement `ChooseActingPieceStep`**

In `src/goa2/domain/models/enums.py`, append to `StepType` (after line 217):

```python
    CHOOSE_ACTING_PIECE = "choose_acting_piece"
    SPAWN_HERO_PIECE = "spawn_hero_piece"
    REMOVE_HERO_PIECE = "remove_hero_piece"
```

(All three added now; Task 9 uses the latter two.)

Create `src/goa2/engine/steps/pieces.py`:

```python
"""Steps for multi-piece heroes (Razzle): acting-piece choice, spawn, removal."""

from __future__ import annotations

import logging
from typing import Any

from goa2.domain.input import InputOption, InputRequestType, create_input_request
from goa2.domain.models import StepType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID
from goa2.engine.steps.base import GameStep, StepResult

logger = logging.getLogger(__name__)


class ChooseActingPieceStep(GameStep):
    """Bind which piece of a multi-piece hero performs the current action.

    No-op for normal heroes. Auto-binds when exactly one piece is on board.
    """

    type: StepType = StepType.CHOOSE_ACTING_PIECE
    hero_id: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.is_multi_piece:
            return StepResult(is_finished=True)

        pieces = state.get_piece_ids(self.hero_id)
        if not pieces:
            return StepResult(is_finished=True)

        if len(pieces) == 1:
            state.acting_piece_id = BoardEntityID(pieces[0])
            logger.debug(f"   [PIECE] Auto-bound acting piece {pieces[0]}")
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection in pieces:
                state.acting_piece_id = BoardEntityID(str(selection))
                logger.debug(f"   [PIECE] Bound acting piece {selection}")
                return StepResult(is_finished=True)
            raise ValueError(f"Invalid acting piece selection: {selection}")

        options = []
        for pid in pieces:
            loc = state.entity_locations.get(BoardEntityID(pid))
            options.append(
                InputOption(
                    id=pid,
                    text=f"{hero.name} at ({loc.q}, {loc.r}, {loc.s})" if loc else pid,
                )
            )
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_UNIT,
                player_id=self.hero_id,
                prompt="Choose which of you performs this action.",
                options=options,
            ),
        )
```

In `src/goa2/engine/steps/__init__.py`, re-export following the existing pattern:

```python
from goa2.engine.steps.pieces import ChooseActingPieceStep
```

(add to `__all__` if the module maintains one). In `src/goa2/engine/step_types.py`, add the module import alongside the others (line 22-30):

```python
from goa2.engine.steps import pieces as _steps_pieces  # noqa: F401
```

- [ ] **Step 4: Hook into `ResolveCardStep` and clear in `FinalizeHeroTurnStep`**

In `src/goa2/engine/steps/cards.py` `ResolveCardStep.resolve`, right after `steps_list: list[GameStep] = []` (line 744), insert:

```python
                # Multi-piece heroes choose which piece performs the action
                # BEFORE any positional step (passives included) runs.
                from goa2.engine.steps.pieces import ChooseActingPieceStep

                steps_list.append(ChooseActingPieceStep(hero_id=self.hero_id))
```

In `src/goa2/engine/steps/phases.py` `FinalizeHeroTurnStep.resolve`, at the `# Clear transient context for the next actor` block (line 66), add alongside the context clear:

```python
        state.acting_piece_id = None
```

- [ ] **Step 5: Board-actor resolution in movement steps**

In `src/goa2/engine/steps/movement.py` `MoveSequenceStep.resolve` (line 255):

```python
        actor_id = state.resolve_board_actor(str(self.unit_id or state.current_actor_id or ""))
        if not actor_id:
            return StepResult(is_finished=True)
```

Everything downstream in the method already uses `actor_id` for position reads and passes it as the moved unit — verify the `SelectStep`/`MoveUnitStep` construction at the end of the method uses `actor_id` (not `self.unit_id`) and change it if not. Apply the same one-line `resolve_board_actor` translation at the top of `FastTravelSequenceStep.resolve` (same file — find `unit_id` resolution with `grep -n "class FastTravelSequenceStep" -A 20`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_acting_piece.py -v`
Expected: PASS.

- [ ] **Step 7: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q` — pay attention to existing `ResolveCardStep` flow tests: the new step is a silent no-op for every existing hero, so failures indicate a bug in the no-op path.

```bash
git add src/goa2/domain/models/enums.py src/goa2/engine/steps/pieces.py src/goa2/engine/steps/__init__.py src/goa2/engine/step_types.py src/goa2/engine/steps/cards.py src/goa2/engine/steps/movement.py src/goa2/engine/steps/phases.py tests/engine/pieces/test_acting_piece.py
git commit -m "feat: acting-piece binding for multi-piece hero actions"
```

---

### Task 9: `SpawnHeroPieceStep`, `RemoveHeroPieceStep`, `HeroPieceFilter`

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (add `HERO_PIECE = "hero_piece_filter"` to `FilterType`)
- Modify: `src/goa2/engine/steps/pieces.py` (two new steps)
- Modify: `src/goa2/engine/filters_units.py` (new filter), `src/goa2/engine/filters.py` facade re-export
- Modify: `src/goa2/engine/steps/__init__.py` (re-exports)
- Test: `tests/engine/pieces/test_piece_spawn_remove.py`

**Interfaces:**
- Consumes: `pieces_in_supply`, `get_piece_ids`, `acting_piece_id`.
- Produces:
  - `SpawnHeroPieceStep(hero_id: str, max_count: int, radius: int, origin_key: str | None = None)` — spawn up to `max_count` pieces from supply into empty hexes within `radius` of the acting piece (or of `context[origin_key]` position), one `SELECT_HEX`-or-SKIP prompt per piece; emits `GameEventType.UNIT_PLACED` with `metadata={"owner_hero_id": ...}`.
  - `RemoveHeroPieceStep(hero_id: str, mode: Literal["choose_one", "all_others", "choose_any"] = "choose_one", min_remaining: int = 1)` — voluntary removal (no defeat, no rewards); emits `GameEventType.UNIT_REMOVED` per piece.
  - `HeroPieceFilter(owner: Literal["SELF"] = "SELF", exclude_acting: bool = True)` — candidate is a `HeroPiece` owned by the current actor, optionally excluding the bound acting piece.

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/pieces/test_piece_spawn_remove.py`:

```python
"""Spawn (supply-capped) and voluntary removal of hero pieces."""

from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.pieces import RemoveHeroPieceStep, SpawnHeroPieceStep

from tests.engine.effects.builders import EffectScenarioBuilder


def _state(n_pieces: int, extra_hexes: int = 0) -> GameState:
    hexes = [(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1), (1, -1, 0), (-1, 1, 0), (-1, 0, 1)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1), (0, 1, -1)]
    for i in range(n_pieces):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_spawn_up_to_three_capped_by_supply_and_hexes():
    state = _state(n_pieces=1)
    state.acting_piece_id = piece_id("hero_razzle", 1)
    push_steps(state, [SpawnHeroPieceStep(hero_id="hero_razzle", max_count=3, radius=1)])
    # Three sequential SELECT_HEX prompts; take first offered hex each time
    for _ in range(3):
        result = process_stack(state)
        assert result.input_request is not None
        first_hex = result.input_request.options[0].metadata["hex"]
        state.execution_stack[-1].pending_input = {"selection": first_hex}
    result = process_stack(state)
    assert result.input_request is None
    assert len(state.get_piece_ids("hero_razzle")) == 4  # supply cap reached


def test_spawn_is_skippable_per_piece():
    state = _state(n_pieces=1)
    state.acting_piece_id = piece_id("hero_razzle", 1)
    push_steps(state, [SpawnHeroPieceStep(hero_id="hero_razzle", max_count=3, radius=1)])
    result = process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "SKIP"}
    result = process_stack(state)
    assert result.input_request is None  # SKIP ends the whole spawn sequence
    assert len(state.get_piece_ids("hero_razzle")) == 1


def test_remove_one_piece_keeps_min_remaining():
    state = _state(n_pieces=2)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_one")])
    result = process_stack(state)
    option_ids = {o.id for o in result.input_request.options}
    assert option_ids == {piece_id("hero_razzle", 1), piece_id("hero_razzle", 2), "SKIP"}
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 1)}
    process_stack(state)
    assert piece_id("hero_razzle", 1) not in state.entity_locations
    assert state.has_board_presence("hero_razzle")
    # No defeat happened
    assert "hero_razzle" not in state.heroes_defeated_this_round


def test_remove_choose_one_noop_with_single_piece():
    state = _state(n_pieces=1)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_one")])
    result = process_stack(state)
    assert result.input_request is None
    assert state.has_board_presence("hero_razzle")


def test_remove_all_others_keeps_acting_piece():
    state = _state(n_pieces=3)
    state.acting_piece_id = piece_id("hero_razzle", 2)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="all_others")])
    result = process_stack(state)
    assert result.input_request is None  # no choice needed
    assert state.get_piece_ids("hero_razzle") == [piece_id("hero_razzle", 2)]


def test_removed_pieces_return_to_supply_for_respawn():
    state = _state(n_pieces=2)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_one")])
    result = process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    process_stack(state)
    from goa2.engine.hero_pieces import pieces_in_supply

    razzle = state.get_hero("hero_razzle")
    assert piece_id("hero_razzle", 2) in pieces_in_supply(state, razzle)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_spawn_remove.py -v`
Expected: FAIL — `ImportError` for the new steps.

- [ ] **Step 3: Implement the steps**

Append to `src/goa2/engine/steps/pieces.py`:

```python
class SpawnHeroPieceStep(GameStep):
    """Spawn up to max_count pieces from supply into empty hexes in radius.

    One SELECT_HEX prompt per piece; SKIP ends the sequence. Origin is the
    acting piece by default, or the position of context[origin_key].
    """

    type: StepType = StepType.SPAWN_HERO_PIECE
    hero_id: str
    max_count: int = 1
    radius: int = 1
    origin_key: str | None = None
    is_mandatory: bool = False

    def _origin_hex(self, state: GameState, context: dict[str, Any]):
        if self.origin_key:
            origin_id = context.get(self.origin_key)
            if origin_id:
                return state.get_position(str(origin_id))
        return state.get_position(self.hero_id)

    def _valid_hexes(self, state: GameState, context: dict[str, Any]):
        from goa2.engine.rules import topology_distance

        origin = self._origin_hex(state, context)
        if origin is None:
            return []
        candidates = []
        for h, tile in state.board.tiles.items():
            if tile.occupant_id or tile.is_obstacle:
                continue
            if h == origin:
                continue
            if topology_distance(state, origin, h) <= self.radius:
                candidates.append(h)
        return candidates

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.domain.events import GameEvent, GameEventType
        from goa2.engine.hero_pieces import pieces_in_supply

        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.is_multi_piece or self.max_count <= 0:
            return StepResult(is_finished=True)

        supply = pieces_in_supply(state, hero)
        if not supply:
            return StepResult(is_finished=True)

        valid = self._valid_hexes(state, context)
        if not valid:
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection == "SKIP":
                return StepResult(is_finished=True)
            if isinstance(selection, dict):
                from goa2.domain.hex import Hex

                target = Hex(**selection)
                if target not in valid:
                    raise ValueError(f"Invalid spawn hex: {selection}")
                new_piece = supply[0]
                state.place_entity(BoardEntityID(new_piece), target)
                event = GameEvent(
                    event_type=GameEventType.UNIT_PLACED,
                    actor_id=self.hero_id,
                    target_id=new_piece,
                    metadata={"owner_hero_id": self.hero_id, "hex": {"q": target.q, "r": target.r, "s": target.s}},
                )
                # Continue the sequence with one fewer spawn
                return StepResult(
                    is_finished=True,
                    events=[event],
                    new_steps=[
                        SpawnHeroPieceStep(
                            hero_id=self.hero_id,
                            max_count=self.max_count - 1,
                            radius=self.radius,
                            origin_key=self.origin_key,
                        )
                    ],
                )
            raise ValueError(f"Unexpected spawn selection: {selection}")

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_HEX,
                player_id=self.hero_id,
                prompt=f"Spawn another {hero.name}? ({len(supply)} in supply)",
                options=valid,
                can_skip=True,
            ),
        )


class RemoveHeroPieceStep(GameStep):
    """Voluntarily remove piece(s) — NOT a defeat: no rewards, no cascade.

    Modes:
    - choose_one: pick one on-board piece to remove (skippable); no-op if it
      would leave fewer than min_remaining pieces.
    - all_others: remove every piece except the bound acting piece.
    - choose_any: repeatedly pick pieces to remove down to min_remaining
      (SKIP stops). min_remaining=0 allows removing the last piece
      (off-board, NOT defeated — Into Thin Air).
    """

    type: StepType = StepType.REMOVE_HERO_PIECE
    hero_id: str
    mode: str = "choose_one"
    min_remaining: int = 1
    is_mandatory: bool = False

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.domain.events import GameEvent, GameEventType

        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.is_multi_piece:
            return StepResult(is_finished=True)

        pieces = state.get_piece_ids(self.hero_id)

        def _remove(pid: str) -> GameEvent:
            state.remove_entity(BoardEntityID(pid))
            if state.acting_piece_id == pid:
                state.acting_piece_id = None
            return GameEvent(
                event_type=GameEventType.UNIT_REMOVED,
                actor_id=self.hero_id,
                target_id=pid,
                metadata={"owner_hero_id": self.hero_id, "voluntary": True},
            )

        if self.mode == "all_others":
            keep = str(state.acting_piece_id) if state.acting_piece_id else (pieces[0] if pieces else None)
            events = [_remove(pid) for pid in pieces if pid != keep]
            return StepResult(is_finished=True, events=events)

        if len(pieces) <= self.min_remaining:
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection == "SKIP":
                return StepResult(is_finished=True)
            if selection in pieces:
                event = _remove(str(selection))
                next_steps: list[GameStep] = []
                if self.mode == "choose_any":
                    next_steps = [
                        RemoveHeroPieceStep(
                            hero_id=self.hero_id,
                            mode="choose_any",
                            min_remaining=self.min_remaining,
                        )
                    ]
                return StepResult(is_finished=True, events=[event], new_steps=next_steps)
            raise ValueError(f"Invalid piece removal selection: {selection}")

        options = [InputOption(id=pid, text=pid) for pid in pieces]
        options.append(InputOption(id="SKIP", text="Keep all pieces"))
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_UNIT,
                player_id=self.hero_id,
                prompt=f"Remove one of you? ({len(pieces)} in play)",
                options=options,
                can_skip=True,
            ),
        )
```

Note on `_valid_hexes`: check `src/goa2/engine/rules.py` for the actual topology-distance helper name (`grep -n "def.*distance" src/goa2/engine/rules.py`) — per project rule, use **topology/pathfinding distance**, not raw hex distance. If `get_reachable_hexes_in_radius` doesn't exist, drop that import and use the real per-hex distance function found in `rules.py`.

Re-export both steps from `src/goa2/engine/steps/__init__.py`.

- [ ] **Step 4: Implement `HeroPieceFilter`**

In `src/goa2/domain/models/enums.py`, append to `FilterType`:

```python
    HERO_PIECE = "hero_piece_filter"
```

In `src/goa2/engine/filters_units.py`, append:

```python
class HeroPieceFilter(FilterCondition):
    """Candidate is a HeroPiece owned by the current actor.

    exclude_acting=True filters out the bound acting piece — "another one of
    you" selections in Razzle card texts.
    """

    type: FilterType = FilterType.HERO_PIECE
    exclude_acting: bool = True

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        from goa2.domain.models.unit import HeroPiece

        if not isinstance(candidate, str):
            return False
        entity = state.misc_entities.get(BoardEntityID(candidate))
        if not isinstance(entity, HeroPiece):
            return False
        if entity.owner_hero_id != str(state.current_actor_id):
            return False
        if self.exclude_acting and state.acting_piece_id == candidate:
            return False
        return True
```

Re-export from the `src/goa2/engine/filters.py` facade (mirror existing filter exports).

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_spawn_remove.py -v`
Expected: PASS.

- [ ] **Step 6: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/domain/models/enums.py src/goa2/engine/steps/pieces.py src/goa2/engine/steps/__init__.py src/goa2/engine/filters_units.py src/goa2/engine/filters.py tests/engine/pieces/test_piece_spawn_remove.py
git commit -m "feat: hero-piece spawn/remove steps and HeroPieceFilter"
```

---

### Task 10: Views + client integration guide

**Files:**
- Modify: `src/goa2/domain/views.py` (add `hero_pieces` section)
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md`
- Test: `tests/engine/pieces/test_piece_views.py`

**Interfaces:**
- Consumes: `HeroPiece` in `misc_entities`.
- Produces: `build_view()` output gains a top-level `"hero_pieces"` dict: `{piece_id: {"owner_hero_id": str, "team": str, "position": {"q","r","s"} | None}}` (on-board pieces have a position; supply pieces have `None`). Board `entity_locations` already contains on-board piece positions (no change needed there).

- [ ] **Step 1: Write the failing test**

Create `tests/engine/pieces/test_piece_views.py`:

```python
"""Player-scoped views expose hero pieces with owner metadata."""

from goa2.domain.hex import Hex
from goa2.domain.views import build_view
from goa2.engine.hero_pieces import create_hero_pieces, piece_id

from tests.engine.effects.builders import EffectScenarioBuilder


def test_view_contains_hero_pieces_section():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))

    view = build_view(state, for_hero_id=None)
    pieces = view["hero_pieces"]
    assert pieces[piece_id("hero_razzle", 1)]["owner_hero_id"] == "hero_razzle"
    assert pieces[piece_id("hero_razzle", 1)]["position"] == {"q": 0, "r": 0, "s": 0}
    assert pieces[piece_id("hero_razzle", 2)]["position"] is None  # in supply
    assert pieces[piece_id("hero_razzle", 1)]["team"] == "RED"
    # On-board pieces also appear in board entity_locations (existing path)
    assert piece_id("hero_razzle", 1) in view["board"]["entity_locations"]
```

Note: confirm the team serialization (`"RED"` vs `"red"`) against `TeamColor` values and existing view tests; adjust the assertion.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_views.py -v`
Expected: FAIL — `KeyError: 'hero_pieces'`.

- [ ] **Step 3: Implement the view section**

In `src/goa2/domain/views.py` `build_view` (line 47-61 area), build and include the section alongside the existing ones:

```python
    # Hero pieces (multi-piece heroes): public info
    hero_pieces_view: dict[str, Any] = {}
    from goa2.domain.models.unit import HeroPiece

    for eid, entity in state.misc_entities.items():
        if isinstance(entity, HeroPiece):
            loc = state.entity_locations.get(eid)
            hero_pieces_view[str(eid)] = {
                "owner_hero_id": entity.owner_hero_id,
                "team": entity.team.value if entity.team else None,
                "position": {"q": loc.q, "r": loc.r, "s": loc.s} if loc else None,
            }
```

and add `"hero_pieces": hero_pieces_view,` to the returned dict (find the `return {`).

- [ ] **Step 4: Update the client guide**

In `docs/CLIENT_INTEGRATION_GUIDE.md`, add a section (near the view-structure docs):

```markdown
### Hero pieces (multi-piece heroes)

Some heroes (currently Razzle) exist on the board as up to 4 identical pieces
with stable IDs `<hero_id>_piece_1..4`, while remaining ONE player. The view
contains a top-level `hero_pieces` object:

    "hero_pieces": {
      "hero_razzle_piece_1": {"owner_hero_id": "hero_razzle", "team": "RED",
                               "position": {"q": 0, "r": 0, "s": 0}},
      "hero_razzle_piece_2": {"owner_hero_id": "hero_razzle", "team": "RED",
                               "position": null}
    }

`position: null` means the piece is in supply (off-board). Client rules:

- Render every on-board piece as the owner hero. Pieces of the same owner are
  visually interchangeable.
- `SELECT_UNIT` options may contain piece IDs; submit the piece ID as usual.
- Defense prompts for an attacked piece arrive with `player_id` set to the
  OWNER hero ID — route them to that player's session/token.
- The owner hero itself never appears in `board.entity_locations`; derive its
  presence from its pieces.
- Piece spawn/removal arrives as `UNIT_PLACED` / `UNIT_REMOVED` events with
  `metadata.owner_hero_id` set.
```

- [ ] **Step 5: Run tests + server suite**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/test_piece_views.py tests/server/ -q`
Expected: PASS (server tests guard the view contract).

- [ ] **Step 6: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/domain/views.py docs/CLIENT_INTEGRATION_GUIDE.md tests/engine/pieces/test_piece_views.py
git commit -m "feat: expose hero pieces in player views; document client contract"
```

---

### Task 11: Validation cards — `stunt_doubles`, `phantom_strike`, `crowd_control`

**Files:**
- Create: `src/goa2/scripts/razzle_effects.py`
- Test: `tests/engine/effects/cases/test_razzle_effects.py`

**Interfaces:**
- Consumes: everything above. Effect registry pattern: `@register_effect("<effect_id>")` class with `build_steps(self, state, hero, card, stats) -> list[GameStep]` (see `src/goa2/scripts/brynn_effects.py` for the current canonical shape — mirror its imports and stats usage exactly).
- Produces: three registered effects; discovery is automatic (`server/app.py` globs `scripts/*_effects.py`).

Card texts implemented:
- `stunt_doubles` (gold, ATTACK 2, radius 1): "Target a unit adjacent to you. After the attack: Spawn up to 3 more of you in radius."
- `phantom_strike` (Tier I red, ATTACK 4): "Target a unit adjacent to you. After the attack: If there is more than one of you in play, you may remove one of you."
- `crowd_control` (silver, DEFENSE_SKILL 1, radius 3): "When used as a defense action, +2 Defense for each other one of you in radius. When used as a skill action, remove all other you in play."

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/effects/cases/test_razzle_effects.py`:

```python
"""Razzle validation cards: stunt_doubles, phantom_strike, crowd_control."""

import pytest

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.engine.hero_pieces import create_hero_pieces, piece_id

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _piece_setup(state, positions: list[tuple[int, int, int]]):
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    for i, (q, r, s) in enumerate(positions):
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))


@pytest.mark.effect_flow
def test_stunt_doubles_attacks_then_spawns_up_to_supply():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1), (1, -1, 0), (-1, 1, 0)])
        .red_hero("hero_razzle", at=(0, 0, 0), current_card=hero_card("Razzle", "stunt_doubles"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK")
    # Single piece → acting piece auto-binds, no prompt
    run.expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion")
    # After the attack: spawn prompts (SELECT_HEX), spawn two then stop
    run.expect_input(InputRequestType.SELECT_HEX)
    first = run.latest_request.options[0].metadata["hex"]
    run.choose(first)
    run.expect_input(InputRequestType.SELECT_HEX)
    run.skip()
    run.finish()
    assert len(state.get_piece_ids("hero_razzle")) == 2


@pytest.mark.effect_flow
def test_phantom_strike_offers_removal_only_with_multiple_pieces():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0), current_card=hero_card("Razzle", "phantom_strike"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (0, 1, -1)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT)  # acting piece choice (2 pieces)
    run.choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_UNIT)  # attack target
    run.choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_UNIT)  # removal offer
    run.choose(piece_id("hero_razzle", 2))
    run.finish()
    assert state.get_piece_ids("hero_razzle") == [piece_id("hero_razzle", 1)]


@pytest.mark.effect_flow
def test_crowd_control_skill_removes_all_other_pieces():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0), current_card=hero_card("Razzle", "crowd_control"))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (1, 0, -1), (0, 1, -1)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)  # acting piece choice (3 pieces)
    run.choose(piece_id("hero_razzle", 2))
    run.finish()
    assert state.get_piece_ids("hero_razzle") == [piece_id("hero_razzle", 2)]


@pytest.mark.effect_flow
def test_crowd_control_defense_bonus_counts_other_pieces_in_radius():
    # Knight (attack 4) attacks piece_1; crowd_control base defense 1 +2 per
    # other piece in radius 3 → with 2 other pieces: 1+4=5 ≥ 4 → BLOCKED.
    from goa2.domain.events import GameEventType
    from goa2.engine.handler import process_stack, push_steps
    from goa2.engine.steps.combat import AttackSequenceStep

    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (1, 0, -1), (0, 1, -1)])
    razzle = state.get_hero("hero_razzle")
    cc = hero_card("Razzle", "crowd_control")
    razzle.hand.append(cc)

    push_steps(state, [AttackSequenceStep(damage=4, range_val=1)])
    result = process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    result = process_stack(state)
    assert result.input_request.request_type.value == "SELECT_CARD_OR_PASS"
    state.execution_stack[-1].pending_input = {"selection": cc.id}
    result = process_stack(state)
    events = [e for e in result.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert events and events[-1].metadata["outcome"] == "BLOCKED"
```

Note: `run_card` drives from `CHOOSE_ACTION`; if the acting-piece prompt lands before/after differently than asserted, follow the actual order (`run.latest_request.prompt` tells you which prompt you're on) and fix the test to match the Task-8 ordering (acting piece binds immediately after action choice, before target selection).

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/effects/cases/test_razzle_effects.py -v`
Expected: FAIL — effects not registered (card resolves with no effect steps).

- [ ] **Step 3: Implement the effects**

Create `src/goa2/scripts/razzle_effects.py` (mirror the import style of `src/goa2/scripts/brynn_effects.py`):

```python
"""Razzle card effects (validation set: gimmick-core cards).

Razzle is the multi-piece hero: 1-4 identical pieces (hero_razzle_piece_N),
one player. See docs/superpowers/specs/2026-07-02-razzle-multipiece-design.md.
"""

from __future__ import annotations

import logging
from typing import Any

from goa2.domain.models import Card, Hero
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import GameStep
from goa2.engine.steps.combat import AttackSequenceStep
from goa2.engine.steps.pieces import RemoveHeroPieceStep, SpawnHeroPieceStep

logger = logging.getLogger(__name__)


@register_effect("stunt_doubles")
class StuntDoublesEffect(CardEffect):
    """Target a unit adjacent to you. After the attack:
    Spawn up to 3 more of you in radius."""

    def build_steps(self, state: GameState, hero: Hero, card: Card, stats: Any) -> list[GameStep]:
        return [
            AttackSequenceStep(damage=stats.attack, range_val=1),
            SpawnHeroPieceStep(
                hero_id=str(hero.id),
                max_count=3,
                radius=stats.radius,
            ),
        ]


@register_effect("phantom_strike")
class PhantomStrikeEffect(CardEffect):
    """Target a unit adjacent to you. After the attack:
    If there is more than one of you in play, you may remove one of you."""

    def build_steps(self, state: GameState, hero: Hero, card: Card, stats: Any) -> list[GameStep]:
        return [
            AttackSequenceStep(damage=stats.attack, range_val=1),
            RemoveHeroPieceStep(hero_id=str(hero.id), mode="choose_one", min_remaining=1),
        ]


@register_effect("crowd_control")
class CrowdControlEffect(CardEffect):
    """Defense action: +2 Defense per other one of you in radius.
    Skill action: remove all other you in play."""

    def build_steps(self, state: GameState, hero: Hero, card: Card, stats: Any) -> list[GameStep]:
        # Skill action: remove all other pieces (keep the acting one).
        return [RemoveHeroPieceStep(hero_id=str(hero.id), mode="all_others")]

    def get_defense_steps(self, state, defender, card, context):
        from goa2.engine.rules import topology_distance

        defender_piece = str(context.get("defender_id", defender.id))
        origin = state.get_position(defender_piece)
        bonus = 0
        if origin is not None:
            radius = card.radius_value or 3
            for pid in state.get_piece_ids(str(defender.id)):
                if pid == defender_piece:
                    continue
                loc = state.get_position(pid)
                if loc is not None and topology_distance(state, origin, loc) <= radius:
                    bonus += 2
        context["defense_bonus"] = int(context.get("defense_bonus", 0)) + bonus
        logger.debug(f"   [CROWD CONTROL] +{bonus} defense from other pieces")
        return []
```

Notes for the implementer:
- Check `CardEffect.build_steps`'s exact `stats` parameter shape in `src/goa2/engine/effects.py:138` (attribute names like `stats.attack`/`stats.radius`) and mirror an existing red-card effect (e.g. Brynn's) for how attack damage/radius are read.
- Check `get_defense_steps` signature at `src/goa2/engine/effects.py:95`; returning `[]` (not `None`) prevents the `get_steps()` fallback from firing the skill text during defense.
- Check the topology-distance helper name in `src/goa2/engine/rules.py` (per project rule: pathfinding distance, not hex distance).
- Do not implement the other 14 Razzle cards — out of scope (other contributors).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/effects/cases/test_razzle_effects.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `PYTHONPATH=src uv run pytest tests/ -q`

```bash
git add src/goa2/scripts/razzle_effects.py tests/engine/effects/cases/test_razzle_effects.py
git commit -m "feat: Razzle validation card effects (stunt_doubles, phantom_strike, crowd_control)"
```

---

### Task 12: Enumeration audit, guard tests, and final verification

**Files:**
- Audit (read + selectively modify): every direct hero-positional `entity_locations` read in `src/goa2/engine/` and `src/goa2/domain/views.py`
- Test: `tests/engine/pieces/test_piece_guards.py`
- Modify: `docs/CODEBASE_MAP.md` is stale-bannered — do NOT update it; update `CLAUDE.md` only if a reviewer asks.

**Interfaces:**
- Consumes: everything above.
- Produces: audited call sites; guard tests for the cross-cutting flows (persistent bindings, non-combat defeat, journey truthfulness).

- [ ] **Step 1: Run the audit greps and classify every hit**

```bash
grep -rn "entity_locations.get\|entity_locations\[" src/goa2/engine src/goa2/domain --include="*.py" | grep -v "def get_position\|def has_board\|_multi_piece"
grep -rn "in state.entity_locations\|in state.unit_locations\|not in state.entity_locations" src/goa2/engine --include="*.py"
grep -rn "team.heroes" src/goa2/engine src/goa2/domain --include="*.py"
```

For each hit, classify per spec §3.2 and record the classification as a table in the commit message body:
- **Piece/target ID flows** (the ID came from a selection/victim/context key): correct as-is — piece IDs live in `entity_locations`.
- **Hero-ID bound reads** (actor position mid-action): switch to `state.get_position(...)`.
- **Hero-ID predicates/off-board checks**: switch to `state.has_board_presence(...)` / `state.get_positions(...)`.
- **Player-level `team.heroes` iterations** (planning, initiative, respawn scheduling, card lookups, hand views): leave unchanged.
- **Board-positional `team.heroes` iterations** (spawn-blocking displacement around `combat.py:1077`, any "heroes in zone" sweep): iterate `state.get_piece_ids(hero.id)` positions instead.

Known sites already handled in earlier tasks: `cards.py:616/636/791/1608`, `reactions.py` guards, `combat.py:177/776`, `stats.py`, `filters_hex.py`. Expect the remaining fixes to be few; when in doubt whether an ID can ever be a bare multi-piece hero ID, leave it and note it in the table.

- [ ] **Step 2: Write the guard tests**

Create `tests/engine/pieces/test_piece_guards.py`:

```python
"""Cross-cutting guards: non-combat defeat, persistent bindings, remove-all."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import DefeatUnitStep
from goa2.engine.steps.pieces import RemoveHeroPieceStep

from tests.engine.effects.builders import EffectScenarioBuilder


def _state(n_pieces: int = 2) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1)]
    for i in range(n_pieces):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_noncombat_piece_defeat_is_full_hero_defeat():
    """A push-into-terrain style defeat routes through DefeatUnitStep with a
    piece victim and must cascade (same path as combat defeats)."""
    state = _state()
    push_steps(state, [DefeatUnitStep(victim_id=piece_id("hero_razzle", 1), killer_id=None)])
    process_stack(state)
    assert not state.has_board_presence("hero_razzle")
    assert "hero_razzle" in state.heroes_defeated_this_round


def test_remove_all_is_not_defeat_and_turn_is_skipped():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 1)
    push_steps(
        state,
        [
            RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_any", min_remaining=0),
        ],
    )
    result = process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 1)}
    result = process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    process_stack(state)
    assert not state.has_board_presence("hero_razzle")
    assert "hero_razzle" not in state.heroes_defeated_this_round
    # ResolveCardStep skips the action for an off-board hero (Task 7)
    from goa2.engine.steps.cards import ResolveCardStep

    push_steps(state, [ResolveCardStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is None


def test_persistent_binding_on_piece_id_is_stable():
    """Bindings that bake unit IDs (journey-style) stay truthful: a piece ID
    keeps referring to the same physical piece no matter what binds later."""
    state = _state()
    bound_id = piece_id("hero_razzle", 2)
    before = state.entity_locations[bound_id]
    # Razzle "acts" with the other piece — under the all-proxy model this must
    # not move or re-identify piece 2.
    state.acting_piece_id = piece_id("hero_razzle", 1)
    assert state.entity_locations[bound_id] == before
    assert state.get_unit(bound_id).id == bound_id
```

- [ ] **Step 3: Run guard tests**

Run: `PYTHONPATH=src uv run pytest tests/engine/pieces/ -v`
Expected: all PASS.

- [ ] **Step 4: Full verification**

```bash
PYTHONPATH=src uv run pytest tests/ -q
PYTHONPATH=src uv run pytest --cov=goa2 tests/  # coverage floor is 80 in CI
uv run ruff check src/
uv run black --check src/
uv run mypy src/
```

Expected: all green. Fix anything that isn't before committing.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: audit hero-positional reads for multi-piece heroes; add guard tests"
```

---

## Out of Scope (do not implement in this plan)

- The other 14 Razzle cards + `twin_strike` ultimate (separate card-work plans; they consume `HeroPieceFilter`, `SpawnHeroPieceStep`, `RemoveHeroPieceStep`, `get_piece_ids`).
- Migrating normal heroes to piece-based presence (spec §8, deferred).
- Fast-travel piece-restriction polish (choosing a piece not in a qualifying zone currently fails per mandatory/optional rules — acceptable v1 behavior per spec).

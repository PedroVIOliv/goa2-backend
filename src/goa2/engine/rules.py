from collections import deque

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import ActionType, Card, Minion, TeamColor
from goa2.domain.models.effect import ActiveEffect
from goa2.domain.models.unit import Unit
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID, UnitID
from goa2.engine.topology import get_topology_service


def find_reachable_hexes(
    board: Board,
    start: Hex,
    max_steps: int,
    ignore_obstacles: bool = False,
    state: GameState | None = None,
    actor_id: str | None = None,
    pass_through_obstacles: bool = False,
    topology_unit_ids: list[str] | None = None,
) -> set[Hex]:
    """
    Returns all hexes reachable from start within max_steps via a single BFS.
    Uses the same traversal rules as validate_movement_path.
    The start hex is always included in the result.
    """
    reachable: set[Hex] = {start}

    if max_steps <= 0:
        return reachable

    topology = get_topology_service() if state else None
    queue: deque[tuple[Hex, int]] = deque([(start, 0)])
    visited: set[Hex] = {start}

    while queue:
        current, dist = queue.popleft()

        if dist >= max_steps:
            continue

        if topology and state:
            neighbors = topology.get_traversable_neighbors(
                current,
                state,
                end_hex=None,
                actor_id=actor_id,
                pass_through_obstacles=pass_through_obstacles,
                unit_ids=topology_unit_ids,
            )
        else:
            neighbors = board.get_neighbors(current)

        for neighbor in neighbors:
            if neighbor in visited:
                continue

            is_obs = False
            if not ignore_obstacles and not pass_through_obstacles:
                if state and state.validator:
                    is_obs = state.validator.is_obstacle_for_actor(state, neighbor, actor_id)
                else:
                    is_obs = board.get_tile(neighbor).is_obstacle

            if is_obs:
                passable_tok = (
                    state.validator.is_passable_token(state, neighbor)
                    if state and state.validator
                    else False
                )
                if passable_tok:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))
                else:
                    visited.add(neighbor)
                    continue
                continue

            reachable.add(neighbor)
            visited.add(neighbor)
            queue.append((neighbor, dist + 1))

    return reachable


def validate_movement_path(
    board: Board,
    start: Hex,
    end: Hex,
    max_steps: int,
    ignore_obstacles: bool = False,
    active_zone_id: str | None = None,
    state: GameState | None = None,
    actor_id: str | None = None,
    pass_through_obstacles: bool = False,
    topology_unit_ids: list[str] | None = None,
) -> bool:
    """
    Validates if a unit can move from start to end within max_steps.
    Standard rules:
    - Cannot move through Obstacles (Static or Units).
    - Cannot end on Obstacle.
    - Path length <= max_steps.
    - Respects topology constraints (reality splits) if state is provided.
    - Respects STATIC_BARRIER effects if state and actor_id are provided.
    """
    if max_steps <= 0:
        return False

    if start == end:
        return False

    if not ignore_obstacles:
        # Check destination obstacle - use context-aware check if state is available
        if state and state.validator:
            if state.validator.is_obstacle_for_actor(state, end, actor_id):
                return False
        elif board.get_tile(end).is_obstacle:
            return False

    queue: deque[tuple[Hex, int]] = deque([(start, 0)])
    visited: set[Hex] = {start}

    # Use topology service if state is available for topology-aware pathfinding
    topology = get_topology_service() if state else None

    while queue:
        current, dist = queue.popleft()

        if current == end:
            return True

        if dist >= max_steps:
            continue

        # Get neighbors - topology-aware if state provided, otherwise geometric
        if topology and state:
            neighbors = topology.get_traversable_neighbors(
                current,
                state,
                end,
                actor_id,
                pass_through_obstacles=pass_through_obstacles,
                unit_ids=topology_unit_ids,
            )
        else:
            neighbors = board.get_neighbors(current)

        for neighbor in neighbors:
            if neighbor not in visited:
                # Skip obstacles (unless using topology which already filters)
                if not (topology and state) and not pass_through_obstacles:
                    # Use context-aware check if state is available, otherwise base check
                    if state and state.validator:
                        is_obs = state.validator.is_obstacle_for_actor(state, neighbor, actor_id)
                    else:
                        is_obs = board.get_tile(neighbor).is_obstacle

                    if is_obs and neighbor != end:
                        passable_tok = (
                            state.validator.is_passable_token(state, neighbor)
                            if state and state.validator
                            else False
                        )
                        if not passable_tok:
                            continue

                visited.add(neighbor)
                queue.append((neighbor, dist + 1))

    return False


def _controller_id(entity_id: str, state: GameState) -> str:
    """Return the player-level owner/controller for an entity when known."""
    entity = state.get_entity(BoardEntityID(str(entity_id)))
    owner_id = getattr(entity, "owner_id", None)
    if owner_id is not None:
        return str(owner_id)
    return state.hero_owner_id(str(entity_id))


def _entity_team(entity_id: str, state: GameState):
    entity = state.get_entity(BoardEntityID(str(entity_id)))
    team = getattr(entity, "team", None) if entity else None
    if team is not None:
        return team

    owner_id = getattr(entity, "owner_id", None) if entity else None
    if owner_id is not None:
        owner = state.get_hero(HeroID(str(owner_id)))
        return getattr(owner, "team", None) if owner else None

    hero = state.get_hero(HeroID(str(entity_id)))
    return getattr(hero, "team", None) if hero else None


def is_immune_to_actor(target: Unit, state: GameState, actor_id: str | None = None) -> bool:
    """
    Checks if a target unit has Immunity.
    Rule 3.2: "Heavy Immunity: Immune to all Actions... until no more friendly minions are present."
    Also checks IMMUNITY_ENEMY_ACTIONS effects (e.g., Death Seeker).
    """
    actor_id = (
        str(actor_id)
        if actor_id is not None
        else (str(state.current_actor_id) if state.current_actor_id else None)
    )
    if actor_id and _controller_id(actor_id, state) == _controller_id(str(target.id), state):
        return False

    if isinstance(target, Minion) and target.is_heavy:
        # "until no more friendly minions are present" — checked in the heavy's
        # own lane's Battle Zone (minions are bound to the lane they spawned in).
        zone_id = state.battle_zone_for_lane(target.lane_id)
        if not zone_id:
            return False

        zone = state.board.zones.get(zone_id)
        if not zone:
            return False

        if target.team is None:
            return False

        team = state.teams.get(target.team)
        if not team:
            return False

        # Optimization: We only care about Minions.
        # Iterate team.minions instead of entity_locations to filter by Type first.
        for m in team.minions:
            if m.id == target.id or m.lane_id != target.lane_id:
                continue

            # Use unified lookup
            if m.id in state.entity_locations:
                loc = state.entity_locations[m.id]
                if loc in zone.hexes:
                    return True

    # Check IMMUNITY_ENEMY_ACTIONS effects. By default these block only the
    # opposing team (e.g. Death Seeker). An effect with blocks_friendly_actors
    # (Hanu's Journey line) grants full heavy-style immunity — the target's own
    # allies cannot affect it either. You are never immune to your own actions.
    # Two binding forms:
    #  - unit-bound: protected_unit_id == target (Death Seeker, Hanu's Journey —
    #    the subject, which is the creator unless the effect names another unit)
    #  - radius aura: scope RADIUS + affects filter, evaluated from the
    #    origin's CURRENT position at check time (Emmitt's Future Proof —
    #    entering the radius gains protection, leaving loses it)
    from goa2.domain.models.effect import EffectType, Shape

    if actor_id:
        target_team = getattr(target, "team", None)
        actor_team = _entity_team(str(actor_id), state)
        is_self = _controller_id(str(actor_id), state) == _controller_id(str(target.id), state)
        if not is_self and target_team is not None and actor_team is not None:
            is_enemy_actor = target_team != actor_team
            for effect in state.active_effects:
                if effect.effect_type != EffectType.IMMUNITY_ENEMY_ACTIONS:
                    continue
                if not effect.is_active:
                    continue
                if not (is_enemy_actor or effect.blocks_friendly_actors):
                    continue
                if effect.scope.shape == Shape.RADIUS:
                    # Aura form: the source is the ORIGIN, not the protected
                    # unit — coverage comes from the scope's affects filter
                    # (FRIENDLY_HEROES excludes the origin itself).
                    target_hex = state.get_position(str(target.id))
                    if target_hex is not None and state.validator._is_in_scope(
                        effect, str(target.id), target_hex, state
                    ):
                        return True
                elif effect.protected_unit_id == str(target.id):
                    return True

    return False


def is_immune(target: Unit, state: GameState) -> bool:
    """Check immunity against the current actor."""
    return is_immune_to_actor(target, state)


def unit_ignores_effect_due_to_immunity(
    effect: ActiveEffect, unit_id: str, state: GameState
) -> bool:
    """Whether an active effect from its source cannot affect this unit.

    Immune units are not affected by another unit's actions. The source's own
    units still receive self effects because a unit is never immune to its own
    actions.
    """
    target = state.get_unit(UnitID(str(unit_id)))
    if target is None:
        return False
    if _controller_id(effect.source_id, state) == _controller_id(str(unit_id), state):
        return False
    return is_immune_to_actor(target, state, actor_id=effect.source_id)


def can_perform_action_on_card(
    state: GameState, hero_id: str, action: ActionType, card: Card
) -> bool:
    """Whether `hero_id` may perform `action` on `card` right now.

    Action-prevention effects (Arien's Spell Break, Xargatha's movement locks)
    are evaluated against the card the action is performed *on* — its colour
    drives exceptions like Spell Break's "except on gold cards", not the colour
    of whatever card granted the performance.
    """
    result = state.validator.can_perform_action(state, hero_id, action, context={"card": card})
    return bool(result.allowed)


def can_perform_card_primary(state: GameState, hero_id: str, card: Card) -> bool:
    """Whether `hero_id` may perform `card`'s primary action right now.

    Re-performing a resolved skill card is a Skill action on that skill card,
    so the colour that matters is the skill card's — not that of the gold card
    which granted the re-performance.
    """
    action = card.current_primary_action
    if action is None:
        return True
    if action == ActionType.DEFENSE_SKILL:
        action = ActionType.SKILL
    return can_perform_action_on_card(state, hero_id, action, card)


def validate_target(
    source: Unit,
    target: Unit,
    action_type: ActionType,
    state: GameState,
    range_val: int,
    ignore_los: bool = True,  # Default per rules (4.1)
    requires_straight_line: bool = False,
) -> bool:
    """
    Central validation for targeting.
    Checks:
    1. Distance (Range)
    2. Line of Sight (if needed)
    3. Immunity (Heavies, etc.)
    """

    if is_immune(target, state):
        return False

    s_loc = state.entity_locations.get(source.id)
    t_loc = state.entity_locations.get(target.id)

    if not s_loc or not t_loc:
        return False

    # Use topology-aware distance (respects reality splits)
    topology = get_topology_service()

    target_unit_ids = [str(source.id), str(target.id)]
    if requires_straight_line and not topology.is_straight_line(
        s_loc, t_loc, state, unit_ids=target_unit_ids
    ):
        return False

    dist = topology.distance(s_loc, t_loc, state, unit_ids=target_unit_ids)

    # Rule 4.1: "No 'Line of Sight' obstructions" is standard for Range/Radius.
    # However, some specific rules might require it.
    # For now, default ignores it.

    return not (dist > range_val)


def validate_attack_target(
    attacker_pos: Hex,  # Legacy
    target_pos: Hex,  # Legacy
    range_val: int,
    requires_line_of_sight: bool = True,
    requires_straight_line: bool = False,
    state: GameState | None = None,
    attacker: Unit | None = None,
    target: Unit | None = None,
) -> bool:
    """
    Validates if an attack is legal.
    Wrapper around validate_target if full context is provided.
    Else falls back to geometry check.
    """
    if state and attacker and target:
        return validate_target(
            source=attacker,
            target=target,
            action_type=ActionType.ATTACK,
            state=state,
            range_val=range_val,
            ignore_los=not requires_line_of_sight,
            requires_straight_line=requires_straight_line,
        )

    # Legacy Fallback (Geometry Only - no topology without state)
    # Note: This branch cannot use topology since state is not available
    if requires_straight_line and not attacker_pos.is_straight_line(target_pos):
        return False

    # Use topology if state is available, otherwise pure geometry
    if state:
        topology = get_topology_service()
        unit_ids = []
        if attacker:
            unit_ids.append(str(attacker.id))
        if target:
            unit_ids.append(str(target.id))
        dist = topology.distance(attacker_pos, target_pos, state, unit_ids=unit_ids)
    else:
        dist = attacker_pos.distance(target_pos)
    return not (dist > range_val)


def get_safe_zones_for_fast_travel(
    state: GameState, team: TeamColor, current_zone_id: str
) -> list[str]:
    """
    Identifies zones eligible for Fast Travel.
    Rule 6.1 (Fast Travel):
    - Start Zone must be Empty of Enemies.
    - Dest Zone must be Empty of Enemies.
    - Dest Zone must match Start Zone OR be Adjacent to Start Zone.
    """
    safe_zones = []

    # If Start Zone has enemies, Fast Travel is impossible.
    start_zone = state.board.zones.get(current_zone_id)
    if not start_zone:
        return []

    start_has_enemies = False
    for entity_id, loc in state.entity_locations.items():
        if loc in start_zone.hexes:
            # We use get_entity because it might be a Unit or a Token
            entity = state.get_entity(entity_id)
            if entity and hasattr(entity, "team") and entity.team != team:
                start_has_enemies = True
                break

    if start_has_enemies:
        return []

    candidates = [current_zone_id, *start_zone.neighbors]

    for z_id in candidates:
        zone = state.board.zones.get(z_id)
        if not zone:
            continue

        has_enemies = False
        for entity_id, loc in state.entity_locations.items():
            if loc in zone.hexes:
                entity = state.get_entity(entity_id)
                # Note: Tokens are obstacles, not enemies. Rules specify "Empty of Enemies".
                if entity and hasattr(entity, "team") and entity.team != team:
                    has_enemies = True
                    break

        if not has_enemies:
            safe_zones.append(z_id)

    return safe_zones


class MinePathOption:
    """A possible path to a hex, with the set of mines triggered along the way."""

    __slots__ = ("mine_ids", "path")

    def __init__(self, mine_ids: set[str], path: list[Hex]):
        self.mine_ids = mine_ids
        self.path = path


def find_reachable_with_mines(
    board: Board,
    start: Hex,
    max_steps: int,
    state: GameState,
    actor_id: str | None = None,
    moving_team: TeamColor | None = None,
    topology_unit_ids: list[str] | None = None,
) -> dict[Hex, list[MinePathOption]]:
    if max_steps <= 0:
        return {}

    topology = get_topology_service()

    all_options: dict[Hex, list[MinePathOption]] = {}

    visited: set = set()
    # Each entry: (current_hex, distance, mines_passed_frozenset, path_tuple)
    queue: deque[tuple[Hex, int, frozenset, tuple]] = deque([(start, 0, frozenset(), (start,))])
    visited.add((start, frozenset()))

    while queue:
        current, dist, mines_passed, path = queue.popleft()

        if current != start:
            is_passable = state.validator.is_passable_token(state, current)
            if not is_passable:
                mine_set = set(mines_passed)

                if current not in all_options:
                    all_options[current] = [MinePathOption(mine_set, list(path))]
                else:
                    existing_sets = [o.mine_ids for o in all_options[current]]
                    if mine_set not in existing_sets:
                        all_options[current].append(MinePathOption(mine_set, list(path)))

        if dist >= max_steps:
            continue

        for neighbor in current.neighbors():
            if not topology.are_connected(current, neighbor, state, unit_ids=topology_unit_ids):
                continue
            if not state.board.is_on_map(neighbor):
                continue

            is_obs = state.validator.is_obstacle_for_actor(state, neighbor, actor_id)
            is_passable_tok = state.validator.is_passable_token(state, neighbor)

            if is_obs and not is_passable_tok:
                continue

            new_mines = mines_passed
            if is_passable_tok:
                tile = state.board.get_tile(neighbor)
                if tile and tile.occupant_id:
                    token_id = str(tile.occupant_id)
                    # Only count as mine if owned by opposing team
                    is_enemy_mine = True
                    if moving_team:
                        token_entity = state.get_entity(BoardEntityID(token_id))
                        owner_id = getattr(token_entity, "owner_id", None)
                        if owner_id:
                            owner = state.get_hero(owner_id)
                            if owner and owner.team == moving_team:
                                is_enemy_mine = False
                    if is_enemy_mine:
                        new_mines = mines_passed | {token_id}

            state_key = (neighbor, new_mines)
            if state_key in visited:
                continue
            visited.add(state_key)
            queue.append((neighbor, dist + 1, new_mines, (*path, neighbor)))

    return all_options


def illusion_minion_team(state: GameState) -> TeamColor | None:
    """Team for which Illusion tokens currently count as friendly melee
    minions, or None when no ILLUSION_MINION_EQUIVALENCE effect applies.

    "While you are performing actions" — active only while the effect's
    SOURCE hero is the current actor. Gated on the performer (whoever
    performed the card), never hardcoded to NebKher, so copy/perform
    mechanics bind the equivalence to the copier. Piece-safe via
    hero_owner_id (multi-piece heroes compare at owner level).
    """
    from goa2.domain.models.effect import EffectType

    actor_id = state.current_actor_id
    if not actor_id:
        return None
    actor_owner = state.hero_owner_id(str(actor_id))

    for effect in state.active_effects:
        if effect.effect_type != EffectType.ILLUSION_MINION_EQUIVALENCE or not effect.is_active:
            continue
        if state.hero_owner_id(str(effect.source_id)) != actor_owner:
            continue
        from goa2.domain.types import HeroID

        source = state.get_hero(HeroID(state.hero_owner_id(str(effect.source_id))))
        if source is not None and source.team is not None:
            return source.team
    return None


def is_equivalent_illusion(state: GameState, entity_id: str) -> bool:
    """True when ``entity_id`` is an Illusion token that currently counts as
    a friendly melee minion (see illusion_minion_team)."""
    from goa2.domain.models import TokenType
    from goa2.domain.models.token import Token

    if illusion_minion_team(state) is None:
        return False
    entity = state.get_entity(BoardEntityID(str(entity_id)))
    return isinstance(entity, Token) and entity.token_type == TokenType.ILLUSION

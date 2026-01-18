from enum import Enum


class TeamColor(str, Enum):
    RED = "RED"
    BLUE = "BLUE"


class MinionType(str, Enum):
    MELEE = "MELEE"
    RANGED = "RANGED"
    HEAVY = "HEAVY"


class CardTier(str, Enum):
    I = "I"
    II = "II"
    III = "III"
    IV = "IV"
    UNTIERED = "UNTIERED"


class CardColor(str, Enum):
    GOLD = "GOLD"  # Basic
    SILVER = "SILVER"  # Basic
    RED = "RED"  # Attack focus
    BLUE = "BLUE"  # Skill focus
    GREEN = "GREEN"  # Utility focus
    PURPLE = "PURPLE"  # Ultimate


class ActionType(str, Enum):
    MOVEMENT = "MOVEMENT"
    ATTACK = "ATTACK"
    SKILL = "SKILL"
    DEFENSE = "DEFENSE"
    DEFENSE_SKILL = (
        "DEFENSE_SKILL"  # Can be used as SKILL on turn or DEFENSE in reaction
    )
    HOLD = "HOLD"  # Secondary
    CLEAR = "CLEAR"  # Replaces Attack
    FAST_TRAVEL = "FAST_TRAVEL"  # Replaces Movement


class StatType(str, Enum):
    ATTACK = "ATTACK"
    DEFENSE = "DEFENSE"
    MOVEMENT = "MOVEMENT"
    INITIATIVE = "INITIATIVE"
    RANGE = "RANGE"
    RADIUS = "RADIUS"


class CardState(str, Enum):
    HAND = "HAND"
    DECK = "DECK"
    DISCARD = "DISCARD"
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    ITEM = "ITEM"
    PASSIVE = "PASSIVE"
    RETIRED = "RETIRED"


class GamePhase(str, Enum):
    SETUP = "SETUP"
    PLANNING = "PLANNING"  # Card Selection
    REVELATION = "REVELATION"  # Reveal cards
    RESOLUTION = "RESOLUTION"  # Acting order
    CLEANUP = "CLEANUP"  # Round/Turn end
    LEVEL_UP = "LEVEL_UP"  # Mandatory upgrading
    GAME_OVER = "GAME_OVER"  # Game has ended


class ResolutionStep(str, Enum):
    NONE = "NONE"
    ACTING = "ACTING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"


class StepType(str, Enum):
    GENERIC = "generic_step"
    CREATE_MODIFIER = "create_modifier"
    CREATE_EFFECT = "create_effect"
    LOG_MESSAGE = "log_message"
    SELECT = "select_step"
    DRAW_CARD = "draw_card"
    MOVE_UNIT = "move_unit"
    MOVE_SEQUENCE = "move_sequence"
    FAST_TRAVEL = "fast_travel"
    FAST_TRAVEL_SEQUENCE = "fast_travel_sequence"
    REACTION_WINDOW = "reaction_window"
    REMOVE_UNIT = "remove_unit"
    DEFEAT_UNIT = "defeat_unit"
    FIND_NEXT_ACTOR = "find_next_actor"
    RESOLVE_COMBAT = "resolve_combat"
    FINALIZE_HERO_TURN = "finalize_hero_turn"
    PLACE_UNIT = "place_unit"
    SWAP_UNITS = "swap_units"
    SWAP_CARD = "swap_card"
    PUSH_UNIT = "push_unit"
    RESPAWN_HERO = "respawn_hero"
    RESPAWN_MINION = "respawn_minion"
    RESOLVE_CARD_TEXT = "resolve_card_text"
    RESOLVE_CARD = "resolve_card"
    RESOLVE_DISPLACEMENT = "resolve_displacement"
    LANE_PUSH = "lane_push"
    ASK_CONFIRMATION = "ask_confirmation"
    RECORD_TARGET = "record_target"
    MAY_REPEAT_ONCE = "may_repeat_once"
    VALIDATE_REPEAT = "validate_repeat"
    CHECK_ADJACENCY = "check_adjacency"
    CHECK_LANE_PUSH = "check_lane_push"
    END_PHASE_CLEANUP = "end_phase_cleanup"
    END_PHASE = "end_phase"
    RESOLVE_TIE_BREAKER = "resolve_tie_breaker"
    ATTACK_SEQUENCE = "attack_sequence"
    ROUND_RESET = "round_reset"
    RESOLVE_UPGRADES = "resolve_upgrades"
    TRIGGER_GAME_OVER = "trigger_game_over"
    SET_CONTEXT_FLAG = "set_context_flag"
    RESOLVE_DEFENSE_TEXT = "resolve_defense_text"
    RESOLVE_ON_BLOCK_EFFECT = "resolve_on_block_effect"
    CANCEL_EFFECTS = "cancel_effects"
    RESTORE_ACTION_TYPE = "restore_action_type"
    CHECK_PASSIVE_ABILITIES = "check_passive_abilities"
    OFFER_PASSIVE = "offer_passive"
    MARK_PASSIVE_USED = "mark_passive_used"


class FilterType(str, Enum):
    OCCUPIED = "occupied_filter"
    TERRAIN = "terrain_filter"
    RANGE = "range_filter"
    TEAM = "team_filter"
    UNIT_TYPE = "unit_type_filter"
    ADJACENCY = "adjacency_filter"
    IMMUNITY = "immunity_filter"
    SPAWN_POINT = "spawn_point_filter"
    ADJACENT_SPAWN_POINT = "adjacent_spawn_point_filter"
    ADJACENCY_TO_CONTEXT = "adjacency_to_context_filter"
    EXCLUDE_IDENTITY = "exclude_identity_filter"
    HAS_EMPTY_NEIGHBOR = "has_empty_neighbor_filter"
    FORCED_MOVEMENT_BY_ENEMY = "forced_movement_by_enemy_filter"
    CAN_BE_PLACED_BY_ACTOR = "can_be_placed_filter"
    MOVEMENT_PATH = "movement_path_filter"
    FAST_TRAVEL_DESTINATION = "fast_travel_destination_filter"
    LINE_BEHIND_TARGET = "line_behind_target_filter"
    NOT_IN_STRAIGHT_LINE = "not_in_straight_line_filter"


class TargetType(str, Enum):
    UNIT = "UNIT"
    TOKEN = "TOKEN"
    HEX = "HEX"
    CARD = "CARD"
    NUMBER = "NUMBER"
    UNIT_OR_TOKEN = "UNIT_OR_TOKEN"

class CardContainerType(str, Enum):
    HAND = "HAND"
    PLAYED = "PLAYED"
    DISCARD = "DISCARD"
    DECK = "DECK"


class PassiveTrigger(str, Enum):
    """When passive abilities activate."""

    BEFORE_ATTACK = "before_attack"
    BEFORE_MOVEMENT = "before_movement"
    BEFORE_SKILL = "before_skill"

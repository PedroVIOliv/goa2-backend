# =============================================================================
# MISA EFFECTS — HIGH-LEVEL DESIGN
# =============================================================================
#
# New infrastructure needed (2 steps, 2 filters):
#
#   SaveUnitLocationStep(unit_id, output_key)
#     - Reads state.entity_locations[unit_id], stores Hex in context[output_key]
#     - ~10 lines. Generic "remember where X was" utility.
#
#   BetweenHexesFilter(from_hex_key, to_hex_key)
#     - Unit filter: passes if unit sits on the straight-line path between
#       two context hexes (exclusive of both endpoints).
#     - Uses TopologyService.line_between(origin, target, state) which
#       returns connected intermediate hexes (new topology method needed).
#     - ~20 lines of logic, same resolve pattern as LineBehindTargetFilter.
#
#   CountMatchFilter(sub_filters, min_count, max_count?)
#     - HEX filter: counts units on the board that pass all sub_filters
#       (evaluated from the candidate hex's perspective as origin), then
#       checks count >= min_count (and <= max_count if set).
#     - CountStep logic as a filter. Sub_filters like RangeFilter are
#       evaluated relative to the candidate hex, so RangeFilter(max_range=1)
#       gives adjacency, RangeFilter(max_range=3) gives radius, etc.
#     - Fully generic: any filter combo works. Replaces need for one-off
#       "MinAdjacentEnemiesFilter", "HasNearbyAlliesFilter", etc.
#
#   CheckDistanceStep(unit_a_id/key, unit_b_key, operator, threshold, output_key)
#     - Checks topology distance between two units, stores True/None in context.
#     - Same pattern as CheckContextConditionStep but reads positions instead
#       of context values.
#     - Used by RED ranged cards for "if target is/isn't at range X".
#
# Ultimate (Power Overwhelming) is baked into individual card effects at
# build time, same as Whisper's Grim Reaper pattern:
#   - "Choose one → choose two": only watch_how_i_soar has a choice,
#     so it checks _has_ultimate(hero) and extends with the second branch.
#   - "After you place yourself, adjacent enemy discards": cards that place
#     the hero (watch_how_i_soar, swoop_in, BLUE cards) append
#     post-placement discard steps when ultimate is active.
#
# GREEN "next turn: move before primary action" needs a new PassiveTrigger
# (BEFORE_PRIMARY_ACTION) and NEXT_TURN-duration passive granting. Detailed
# in the green card section below.
#
# =============================================================================


# =============================================================================
# RED MELEE — Attack Adjacent + Defense Buff (3 tiers, shared helper)
# =============================================================================
#
# Cards: challenge_accepted (T1, +2), matter_of_honor (T2, +3),
#         worthy_opponent (T3, +5)
#
# Pattern:
#   AttackSequenceStep(damage=stats.primary_value, range_val=1)
#   CreateEffectStep(
#       effect_type=AREA_STAT_MODIFIER,
#       scope=EffectScope(shape=POINT, origin_id=hero.id, affects=SELF),
#       stat_type=StatType.DEFENSE,
#       stat_value=+N,
#       duration=THIS_TURN,
#   )
#
# Analog: Dodger WeaknessEffect (dodger_effects.py:135) but SELF and positive.
# All 3 tiers share a helper, differing only in defense value.
# Defense value is per-card (not from stats), so hardcode per tier or pass as arg.
#
# Complexity: LOW — existing steps only.


# =============================================================================
# RED RANGED — Attack + Conditional Push (2 tiers)
# =============================================================================
#
# Cards: power_shot (T2), thunder_shot (T3)
#
# power_shot: "Target a unit in range. After the attack: If the target was
#   at maximum range, you may move it 1 space farther away from you."
#
# thunder_shot: "Target a unit in range. After the attack: If the target is
#   not adjacent to you, you may move it 1 space farther away from you."
#
# Pattern:
#   AttackSequenceStep(damage=stats.primary_value, range_val=stats.range)
#   # target stored in context as "defender_id" by AttackSequenceStep
#   CheckDistanceStep(                              # NEW STEP
#       unit_a_id=hero.id,
#       unit_b_key="defender_id",
#       operator="==" / ">",                        # power_shot: ==max, thunder_shot: >1
#       threshold=stats.range / 1,
#       output_key="can_push",
#   )
#   PushUnitStep(
#       target_key="defender_id",
#       distance=1,
#       is_mandatory=False,
#       active_if_key="can_push",
#   )
#
# Complexity: MEDIUM — needs CheckDistanceStep.


# =============================================================================
# BLUE — Straight-Line Move Through + Effect (6 cards, 2 variants)
# =============================================================================
#
# Discard variant: sudden_breeze is NOT discard — correction:
#   - dash_and_slash (T2), death_from_above (T3): enemy hero discards
#   - sudden_breeze (T1), gust_of_wind (T2), crushing_squall (T3): place enemy
#
# All share the same movement pattern, differ in post-move effect.
#
# Pattern (shared helper):
#   SaveUnitLocationStep(unit_id=hero.id, output_key="move_origin")  # NEW STEP
#   SelectStep(HEX, filters=[
#       RangeFilter(min_range=1, max_range=N),       # N = 3/4/5 per tier
#       InStraightLineFilter(origin_id=hero.id),
#       StraightLinePathFilter(origin_id=hero.id, pass_through_units=True),
#       OccupiedFilter(is_occupied=False),
#   ], output_key="move_dest")
#   MoveUnitStep(unit_id=hero.id, destination_key="move_dest", range_val=99)
#
# Then find crossed enemy:
#   SelectStep(UNIT, filters=[
#       BetweenHexesFilter(from_hex_key="move_origin", to_hex_key="move_dest"),  # NEW FILTER
#       TeamFilter(ENEMY),
#   ], auto_select_if_one=True, is_mandatory=False, output_key="crossed_enemy")
#
# Discard variant (dash_and_slash, death_from_above):
#   CheckUnitTypeStep(unit_key="crossed_enemy", expected_type="HERO",
#                     output_key="crossed_is_hero")
#   ForceDiscardStep(victim_key="crossed_enemy", active_if_key="crossed_is_hero")
#
# Place variant (sudden_breeze, gust_of_wind, crushing_squall):
#   SelectStep(HEX, filters=[
#       RangeFilter(max_range=1),                     # adjacent to self
#       OccupiedFilter(is_occupied=False),
#   ], is_mandatory=False, output_key="place_dest", active_if_key="crossed_enemy")
#   PlaceUnitStep(unit_key="crossed_enemy", destination_key="place_dest",
#                 active_if_key="place_dest")
#
# Ultimate integration: if _has_ultimate(hero), append after PlaceUnitStep/move:
#   SelectStep(UNIT, filters=[RangeFilter(1), TeamFilter(ENEMY), UnitTypeFilter(HERO)],
#              is_mandatory=False, auto_select_if_one=True, output_key="ult_discard_victim")
#   ForceDiscardStep(victim_key="ult_discard_victim")
#
# Complexity: HIGH — needs SaveUnitLocationStep + BetweenHexesFilter.


# =============================================================================
# GREEN — Swap Two Units (2 tiers)
# =============================================================================
#
# Cards: living_tornado (T2), storm_spirit (T3)
#
# living_tornado: "Swap two units at maximum radius."
#   SelectStep(UNIT, filters=[
#       RangeFilter(min_range=stats.radius, max_range=stats.radius),
#   ], output_key="swap_a", skip_immunity_filter=True)
#   SelectStep(UNIT, filters=[
#       RangeFilter(min_range=stats.radius, max_range=stats.radius),
#       ExcludeIdentityFilter(exclude_keys=["swap_a"]),
#   ], output_key="swap_b", skip_immunity_filter=True)
#   SwapUnitsStep(unit_a_key="swap_a", unit_b_key="swap_b")
#
# storm_spirit: "Swap two units in radius and at equal distance from you."
#   SelectStep(UNIT, filters=[
#       RangeFilter(max_range=stats.radius),
#   ], output_key="swap_a", skip_immunity_filter=True)
#   SelectStep(UNIT, filters=[
#       RangeFilter(max_range=stats.radius),
#       ExcludeIdentityFilter(exclude_keys=["swap_a"]),
#       PreserveDistanceFilter(target_key="swap_a"),  # same distance as swap_a
#   ], output_key="swap_b", skip_immunity_filter=True)
#   SwapUnitsStep(unit_a_key="swap_a", unit_b_key="swap_b")
#
# Complexity: LOW — all existing steps/filters.


# =============================================================================
# GREEN — Next-Turn Pre-Action Movement (3 tiers)
# =============================================================================
#
# Cards: focus (T1, move 1, "you may"), discipline (T2, move 2),
#         mastery (T3, move 3)
#
# "Next turn: Before you perform a primary action, move up to N spaces."
#
# Needs: PassiveTrigger.BEFORE_PRIMARY_ACTION (new enum value) wired into
# ResolveCardStep to fire before any primary action (attack/skill/movement).
#
# The card effect itself creates a next-turn passive grant:
#   CreateEffectStep(
#       effect_type=EffectType.PRE_ACTION_MOVEMENT,   # new EffectType
#       duration=DurationType.NEXT_TURN,
#       scope=EffectScope(shape=POINT, origin_id=hero.id, affects=SELF),
#       max_value=N,                                   # movement distance
#       is_active=True,
#   )
#
# The handler checks for PRE_ACTION_MOVEMENT effects before executing the
# primary action, inserts MoveSequenceStep(range_val=N, is_mandatory=False),
# then removes the effect.
#
# focus (T1) is "you may move 1 space" (optional).
# discipline/mastery are "move up to 2/3" (also optional — "up to" implies may).
#
# All 3 share a helper differing only in distance.
#
# Complexity: MEDIUM — needs new EffectType + handler wiring + new PassiveTrigger.


# =============================================================================
# SILVER — Swoop In
# =============================================================================
#
# "Place yourself into a space in radius adjacent to two or more enemy units;
#  if you do, you may retrieve a discarded card."
#
# Pattern:
#   SelectStep(HEX, filters=[
#       RangeFilter(max_range=stats.radius),
#       OccupiedFilter(is_occupied=False),
#       ObstacleFilter(is_obstacle=False),
#       CountMatchFilter(                              # NEW FILTER
#           sub_filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
#           min_count=2,
#       ),
#   ], output_key="swoop_dest")
#   PlaceUnitStep(unit_id=hero.id, destination_key="swoop_dest")
#   SelectStep(CARD, card_container=DISCARD, is_mandatory=False,
#              output_key="retrieved_card")
#   RetrieveCardStep(card_key="retrieved_card", active_if_key="retrieved_card")
#
# Ultimate integration: if _has_ultimate(hero), append post-placement discard:
#   SelectStep(UNIT, filters=[RangeFilter(1), TeamFilter(ENEMY), UnitTypeFilter(HERO)],
#              is_mandatory=False, output_key="ult_victim")
#   ForceDiscardStep(victim_key="ult_victim")
#
# CountMatchFilter design:
#   - HEX filter: for a candidate hex, counts all units on the board that
#     pass sub_filters evaluated with the candidate hex as origin.
#   - Parameters: sub_filters (List[FilterCondition]), min_count (int),
#     max_count (Optional[int]).
#   - Sub_filters are evaluated from the candidate's perspective, so
#     RangeFilter(max_range=1) = adjacent, RangeFilter(max_range=3) = radius 3.
#   - Reusable for any "hex near N things matching X" need.
#
# Complexity: MEDIUM — needs AdjacentMatchFilter.


# =============================================================================
# GOLD — Watch How I Soar (Choose One)
# =============================================================================
#
# "Choose one —
#  • Place yourself into a space at maximum range.
#  • Defeat a minion adjacent to you."
#
# Pattern (standard choose-one, see whisper DeathSeekerEffect):
#   SelectStep(NUMBER, options=[1, 2], labels={
#       1: "Place yourself at maximum range",
#       2: "Defeat an adjacent minion",
#   }, output_key="soar_choice")
#
#   # Path A: place at max range
#   CheckContextConditionStep("soar_choice", "==", 1, "chose_place")
#   SelectStep(HEX, filters=[
#       RangeFilter(min_range=stats.range, max_range=stats.range),
#       OccupiedFilter(is_occupied=False),
#       ObstacleFilter(is_obstacle=False),
#   ], active_if_key="chose_place", output_key="soar_dest")
#   PlaceUnitStep(unit_id=hero.id, destination_key="soar_dest",
#                 active_if_key="chose_place")
#
#   # Path B: defeat adjacent minion
#   CheckContextConditionStep("soar_choice", "==", 2, "chose_defeat")
#   SelectStep(UNIT, filters=[
#       RangeFilter(max_range=1), TeamFilter(ENEMY), UnitTypeFilter(MINION),
#   ], active_if_key="chose_defeat", output_key="defeat_target")
#   DefeatUnitStep(victim_key="defeat_target", active_if_key="chose_defeat")
#
# Ultimate integration (choose two, Grim Reaper pattern):
#   if _has_ultimate(hero):
#     # If chose place (1), also offer defeat
#     SelectStep(UNIT, ..., is_mandatory=False, active_if_key="chose_place")
#     DefeatUnitStep(...)
#     # If chose defeat (2), also offer place
#     SelectStep(HEX, ..., is_mandatory=False, active_if_key="chose_defeat")
#     PlaceUnitStep(...)
#     # Post-placement discard (fires for either path that placed)
#     SelectStep(UNIT, adjacent enemy hero, is_mandatory=False, ...)
#     ForceDiscardStep(...)
#
# Complexity: LOW — standard pattern + ultimate bake-in.


# =============================================================================
# ULTIMATE — Power Overwhelming (no standalone effect needed)
# =============================================================================
#
# "Whenever you choose one, you may choose two different options instead,
#  in any order.
#  Each time after you place yourself, an enemy hero adjacent to you
#  discards a card, if able."
#
# Both aspects are baked into individual card effects at build time:
#
# 1. "Choose two" — only watch_how_i_soar has a "choose one", so it checks
#    _has_ultimate(hero) and appends the unchosen option (see GOLD section).
#
# 2. "Post-placement discard" — cards that place the hero check
#    _has_ultimate(hero) and append:
#      SelectStep(UNIT, filters=[RangeFilter(1), TeamFilter(ENEMY),
#                 UnitTypeFilter(HERO)], is_mandatory=False,
#                 auto_select_if_one=True, output_key="ult_discard_victim")
#      ForceDiscardStep(victim_key="ult_discard_victim")
#
#    Cards with self-placement: watch_how_i_soar (path A), swoop_in,
#    and all BLUE cards (straight-line move is effectively self-placement).
#
# Helper:
#   def _has_ultimate(hero: Hero) -> bool:
#       return (hero.ultimate_card is not None
#               and hero.level >= 8)
#
#   def _ultimate_post_placement_steps(hero: Hero) -> List[GameStep]:
#       """Append after any step that places the hero. Guarded by _has_ultimate."""
#       return [
#           SelectStep(UNIT, filters=[RangeFilter(1), TeamFilter(ENEMY),
#                      UnitTypeFilter(HERO)], is_mandatory=False,
#                      auto_select_if_one=True, output_key="ult_adj_victim"),
#           ForceDiscardStep(victim_key="ult_adj_victim"),
#       ]
#
# Complexity: NONE standalone — distributed across card effects.

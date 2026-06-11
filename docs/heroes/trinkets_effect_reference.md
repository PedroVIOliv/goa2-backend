# Trinkets Effect Reference

Use this as the quick implementation map for `src/goa2/scripts/trinkets_effects.py`. All 18 effects (17 deck cards + ultimate) are implemented and registered; tests live in `tests/engine/effects/cases/test_trinkets_effects.py`.

Implementation notes for what was actually built:

- Turret: unique `Turret` BoardEntity (`trinkets_turret`) placed/removed via `PlaceTurretStep`/`RemoveTurretStep` (`engine/steps/markers.py`).
- Cannons: `CheckUnitFiltersStep` (new generic step) tests the selected target against `InStraightLineFilter` from both origins, then `AttackSequenceStep(damage_bonus_key=...)` applies the conditional bonus.
- Barriers: new `TokenType.BARRIER` (supply 3); each placed token carries a token-bound `AREA_STAT_MODIFIER` effect (ADJACENT, `SELF_AND_FRIENDLY_HEROES`, +1 DEFENSE) so the bonus stacks per adjacent token and dies with the token.
- Disruptors: new `EffectType.PRE_ACTION_DISCARD` (+ `discard_or_defeat` payload on `ActiveEffect`), resolved by `ResolvePreActionDiscardStep`, which `ResolveCardStep` schedules before every primary action.
- Design family: gated at runtime via `CheckDistanceStep` against the Turret; swaps use `TargetType.UNIT_OR_TOKEN` (the Turret is not a unit/token, so it is never selectable).
- Ultimate: flat `StatAura` bonuses (+1 RANGE / +1 RADIUS) via `get_stat_auras()`.

## Shape of the Character

Trinkets is a board-entity-origin hero. Most effects are written from the Turret's position, not only from Trinkets:

- Select or place the Turret.
- Use the Turret as an origin for range, radius, adjacency, and line checks.
- Remove the Turret after some effects.
- Reuse the same helper vocabulary across cards so tier variants differ mostly by numbers.

Important model decision: the Turret is an obstacle, but it is not a unit and not a token. In the physical game it is a single 3D piece, so the engine can assume only one Turret exists at any time. Model it as a new `BoardEntity` kind that lives in `entity_locations`, blocks occupancy/pathing like an obstacle, and is selected/placed/removed through Turret-specific steps or filters rather than `TokenTypeFilter`/`RemoveTokenStep`.

Mirror the Widget/Pyro script structure for helper organization, but not for the data model. Start with helpers such as:

- `_turret_selection_step(output_key, *, is_mandatory, range_val=99)`
- `_place_turret_steps(hero_id, radius_or_adjacent, output_key="turret_dest")`
- `_remove_turret_step(turret_key="turret_id")`
- `_turret_origin_enemy_hero_step(...)`
- `_turret_adjacent_target_attack_steps(...)`

Likely filters: `RangeFilter(origin_key="turret_id")`, `AdjacencyToContextFilter(target_key="turret_id")`, `InStraightLineFilter(origin_key="turret_id")`, `TeamFilter`, `UnitTypeFilter`, and `ObstacleFilter`. A Turret-specific entity filter may be needed because the Turret must not appear in normal unit/token selections.

## Closest Existing Patterns

| Trinkets mechanic | Cards | Best references |
|---|---|---|
| Persistent companion entity used as effect origin | Most Turret cards | `src/goa2/scripts/widget_effects.py` Pyro helpers for structure only; Turret needs its own entity model |
| Select Turret, then select unit adjacent/in range of Turret | `flame_belcher`, `steam_discharge`, `emergency_protocol`, `self_destruct` | `widget_effects.py::_pyro_selection_step`, `_pyro_adjacent_enemy_minion_removal_steps`, `_breath_steps`, adapted away from token APIs |
| Turret-origin straight-line effect | `supercharged_cannon`, `gatling_gun`, `makeshift_minigun`; also useful for disruptor targeting | `widget_effects.py::_breath_steps`, `src/goa2/scripts/bain_effects.py` crossbow/straight-line effects |
| Place/remove unique board entity with delayed effect | Turret lifecycle, `salvage_parts`, `rapid_redeployment` | `src/goa2/scripts/min_effects.py::_grenade_steps`, `death_grenade`, `holy_death_grenade`, adapted to Turret entity APIs |
| Barrier or temporary active effect | `deployable_barrier`, `deployable_bastion`, `disruptor_jolt`, `disruptor_pulse`, `disruptor_grid` | `src/goa2/scripts/wasp_effects.py::StaticBarrierEffect`, `CreateEffectStep` |
| Repeat attacks on different targets | `steam_discharge`, `flame_belcher` | `src/goa2/scripts/xargatha_effects.py::RapidThrustsEffect`, `MayRepeatOnceStep`, `ExcludeIdentityFilter` |
| Swap with unit/token, place self | `updated_design`, `early_prototype`, `perfected_design` | `widget_effects.py::_swap_with_pyro_steps`, Min smoke-bomb swap effects |
| Discard-or-defeat | `emergency_protocol`, `disruptor_grid`; lower tiers use discard-if-able | `ForceDiscardStep`, `ForceDiscardOrDefeatStep` in Widget/Brogan/Garrus scripts |
| Retrieve discarded card | `salvage_parts` | Brogan/Bain/Silverarrow retrieve-card effects |

## Card Families

Implement by family rather than one-off cards:

- Turret attack adjacent target: `steam_discharge` repeats once, `flame_belcher` repeats up to two times. Target must be in card range and adjacent to Turret. Repeats require different enemy units.
- Dual-origin cannon: `makeshift_minigun`, `gatling_gun`, `supercharged_cannon`. Target must be in range of both Trinkets and Turret; if target is in straight line from both, add +2/+3 attack.
- Barrier placement: `deployable_barrier`, `deployable_bastion`. Place up to 2/3 Barrier tokens in radius, at least one adjacent to Turret. Friendly heroes get +1 Defense per adjacent Barrier token. This may need a new active effect/stat-count pattern if no marker/token aura already supports it cleanly.
- Disruptor: `disruptor_jolt`, `disruptor_pulse`, `disruptor_grid`. This-turn trigger before enemy heroes in radius of Turret perform a primary action. Lower tiers force discard if able; tier III is discard-or-defeat. Deactivate when a card is discarded.
- Self-destruct: `self_destruct`, `emergency_protocol`. Up to two enemy heroes in radius of Turret discard, then remove Turret. Tier III uses discard-or-defeat.
- Design movement: `early_prototype`, `updated_design`, `perfected_design`. If Trinkets is in radius of Turret, swap with unit/token in radius; tier I removes Turret after swap; tier III can instead place Trinkets into a space in radius.
- Turret setup: `salvage_parts`, `rapid_redeployment`. These are choice cards. They cover placing Turret adjacent to Trinkets, removing Turret for movement/retrieve, and defeating an adjacent minion.
- Ultimate: `unlimited_firepower`. Passive stat aura: +1 Range and +1 Radius once active.

## Implementation Notes

- Turret should be modeled as one unique non-unit, non-token `BoardEntity`, positioned via `entity_locations`, and treated as an obstacle. Do not put it in `token_pool`, do not select it with `TokenTypeFilter`, and do not remove it with `RemoveTokenStep`.
- Because only one Turret exists, placement should move/reposition the existing Turret entity if it is already on the board rather than creating additional Turrets.
- Turret placement/removal probably needs explicit steps, for example `PlaceTurretStep` and `RemoveTurretStep`, unless the existing generic entity APIs already support non-token board entities cleanly.
- For Turret-origin targeting, prefer `RangeFilter(origin_key="turret_id")` over manual distance checks.
- For "range of both you and the Turret", combine a normal actor-origin `RangeFilter(max_range=stats.range)` with `RangeFilter(max_range=stats.range, origin_key="turret_id")`.
- For "straight line from both", combine `InStraightLineFilter(origin_id=str(hero.id))` or default actor-origin usage with `InStraightLineFilter(origin_key="turret_id")`. Verify the filter constructor before using both forms.
- For repeat attacks, use existing repeat steps and exclusion filters where possible. If "up to two times" is not supported by current steps, add a small reusable repeat-N step rather than duplicating card logic.
- For discard-or-defeat cards, use existing discard steps. Do not hand-roll card movement between hand/discard.
- Any new Turret entity model, step, or filter needed for Trinkets must be added to the relevant discriminated unions (`StepType`/`FilterType` and `AnyStep`/`AnyFilter`; model unions if applicable) so persistence keeps working.

## Tests to Write First

Use `tests/engine/effects/` helpers and mark tests as `effect_contract` or `effect_flow`.

- Setup creates exactly one Turret board entity, not a unit and not a token.
- Turret placement uses `entity_locations`, repositions the single Turret if already present, and treats the Turret as an obstacle.
- Normal unit/token selections do not include the Turret.
- Steam/Flame can only target units both in card range and adjacent to Turret, and repeats exclude previous targets.
- Cannon cards require range from both origins and apply the straight-line attack bonus only when both line checks pass.
- Self-destruct/emergency removes Turret after resolving selected enemy heroes.
- Design cards gate on Trinkets being in Turret radius.
- Ultimate modifies computed range/radius without changing printed card values.

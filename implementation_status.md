# Implementation Status Report
Based on `deterministic_rules.md` vs `src/goa2/engine/steps.py`.

## 1. Topographic Definitions

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **1.1 The Grid** | **Implemented** | `Hex` class handles Coordinates, Adjacency, Distance. |
| **1.2 Space Classification** | **Implemented** | `Board` handles Zones and Terrain. `SpawnPoints` defined in models. |
| **1.3 Object Classification** | **Implemented** | `Unit` (Heroes/Minions), `Token` (Obstacles) defined in models. |
| **1.4 Game Setup** | **Implemented** | `GameSetup.create_game` handles Board Loading, Team Init, Hero Placement, and Minion Spawning. Logic supports 1v1 to 5v5 scaling (Life Counters). |

## 2. Temporal Definitions

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **2.1 Game Loop** | **Implemented** | `handler.py` loop processes the `execution_stack`. |
| **2.2 Turn Structure** | **Implemented** | `phases.py` handles broad state. `ResolveTieBreakerStep` handles ties. `FindNextActorStep` handles cycling. `ResolveCardStep` handles Primary/Secondary choice. |
| **2.3 Lane Push** | **Implemented** | `LanePushStep` handles Wave Counter removal, Zone transition, and Minion Wipe. Triggered by Minion Battle or Combat Death. |
| **2.4 End Phase** | **Implemented** | `EndPhaseStep` handles Minion Battle (with Heavy Constraint), Card Retrieval, and Round Reset. Level Up and Mandatory Upgrading fully implemented. |

## 3. Entity States

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **3.1 Hero State** | **Implemented** | `DefeatUnitStep` handles Death Rewards (Killer & Assists), Life Counter penalty, and Board Removal. |
| **3.2 Minion State** | **Implemented** | `Minion` model exists. `rules.validate_movement_path` respects obstacles. **Heavy Immunity** is fully implemented with `ImmunityFilter` and `is_immune` logic. |

## 4. Card System

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **5.1 Card Anatomy** | **Complete** | `Card` model covers all fields. `is_facedown` logic correctly masks hidden info. |
| **5.2 Card States** | **Complete** | `CardState` enum tracks Hand/Played/Discarded/Deck. `ResolveCardStep` handles action choices. |
| **5.3 Upgrade Mechanic** | **Implemented** | Mandatory level-up, color selection from lowest tier, card-to-item tucking, and Ultimate unlocking. |
| **5.1 Ultimate** | **Complete** | Ultimate cards defined and unlocking logic implemented. |

## 5. Actions & Keywords

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **6.1 Action Types** | **Mixed** | |
| - Movement | **Implemented** | `MoveUnitStep` with pathfinding validation. |
| - Attack | **Implemented** | `AttackSequenceStep` (Macro) -> `SelectStep` -> `ReactionWindow` -> `ResolveCombat`. **Note:** Reaction Window auto-skips for Minion targets. |
| - Defense | **Implemented** | `ReactionWindowStep` allows discarding a card to modify defense values. |
| - Skill / Hold | **Implemented** | `ResolveCardStep` supports `HOLD`. Skills delegate to `ResolveCardTextStep` placeholder. |
| **6.2 Keywords** | **Mixed** | |
| - Adjacent / Range | **Implemented** | `rules.py` handles distance checks. |
| - Push / Place | **Implemented** | `PushUnitStep` and `PlaceUnitStep` implemented. |
| - Respawn | **Implemented** | `RespawnHeroStep` and `RespawnMinionStep` implemented. |
| - Swap | **Implemented** | `SwapUnitsStep` implemented. |
| - Line of Sight | **Implemented** | Explicitly ignored per rules. |
| **6.4 Selection** | **Implemented** | `SelectStep` with composable `FilterCondition` system. |

## 6. Architecture Updates (New)

| Feature | Status | Notes |
| :--- | :--- | :--- |
| **Unified Entity Manager** | **Implemented** | `GameState` now acts as the single source of truth for positions via `entity_locations`. `board.tiles` is a read-only cache automatically synchronized. |
| **Serialization** | **Robust** | `Hex` class supports round-trip serialization as dictionary keys (stringified) for JSON storage. |
| **Token Support** | **Implemented** | `state.misc_entities` allows storing and placing Tokens/Obstacles on the board. |
| **Unique ID System** | **Implemented** | Monotonic IDs for dynamic entities (Minions/Tokens) via `EntityFactory` and `state.register_entity` to prevent collisions. |
| **Active Effects System** | **Implemented** | `Modifier` and `DurationType` implemented. `stats.get_computed_stat` calculates dynamic stats. Modifiers expire automatically at turn/round end. |
| **Game Over System** | **Implemented** | Atomic `TriggerGameOverStep` handles winner assignment, stack purging, and phase transition. `GameState.is_game_over` flag added. |

## Summary of Critical Gaps
1.  **Card Effect Registry**: Implementation of hero-specific card logic is underway.
    *   **Arien**: `liquid_leap`, `magical_current`, `stranger_tide`, `arcane_whirlpool` and `noble_blade` are implemented in `arien_effects.py` (using card IDs as effect IDs).
2.  **Advanced Physics**: **Implemented** Handling "Displacement" when multiple units are forced into the same space during a Lane Push respawn. (Queue-based resolution with Team Prompt).

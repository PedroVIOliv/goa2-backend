# Implementation Status Report
Based on `deterministic_rules.md` vs `src/goa2/engine/steps.py`.

## 1. Topographic Definitions

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **1.1 The Grid** | **Implemented** | `Hex` class handles Coordinates, Adjacency, Distance. |
| **1.2 Space Classification** | **Implemented** | `Board` handles Zones and Terrain. `SpawnPoints` defined in models. |
| **1.3 Object Classification** | **Implemented** | `Unit` (Heroes/Minions), `Token` (Obstacles) defined in models. |
| **1.4 Game Setup** | **Pending** | `GameState` initialization logic needs to support 4/6/8 player config and counters. |

## 2. Temporal Definitions

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **2.1 Game Loop** | **Implemented** | `handler.py` loop processes the `execution_stack`. |
| **2.2 Turn Structure** | **Partial** | `phases.py` handles broad state. `ResolveTieBreakerStep` handles complex initiative ties. **Hero Respawn** logic is pending. `resolution_queue` has been refactored to `unresolved_hero_ids` for dynamic re-identification. |
| **2.3 Lane Push** | **Missing** | No `LanePushStep` or trigger logic implemented yet. |
| **2.4 End Phase** | **Missing** | No `EndPhaseStep` (Minion Battle, Level Up) implemented yet. |

## 3. Entity States

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **3.1 Hero State** | **Partial** | `Hero` model exists. Leveling math and Death Penalty/Reward logic are **Missing**. **Hero Dashboard (Turn slots for played cards)** is not yet implemented in the model. |
| **3.2 Minion State** | **Partial** | `Minion` model exists. `rules.validate_movement_path` respects obstacles. **Heavy Immunity** and **Auras** are pending integration. |

## 4. Card System

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **5.1 Card Anatomy** | **Implemented** | `Card` Pydantic model covers all fields (ActionType, Range, Value). |
| **5.2 Card States** | **Partial** | Hand/Played/Discarded state tracking exists. `ReactionWindowStep` handles looking up Defense cards in hand. |
| **5.3 Upgrade Mechanic** | **Missing** | No logic for Upgrading cards or equipping items yet. |
| **5.1 Ultimate** | **Missing** | Ultimate card logic not implemented. |

## 5. Actions & Keywords

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **6.1 Action Types** | **Mixed** | |
| - Movement | **Implemented** | `MoveUnitStep` with pathfinding validation. |
| - Attack | **Implemented** | `AttackSequenceStep` (Macro) -> `SelectTarget` -> `ReactionWindow` -> `ResolveCombat`. |
| - Defense | **Implemented** | `ReactionWindowStep` allows discarding a card to modify defense values. |
| - Skill / Hold | **Missing** | No generic `ApplyEffectStep` yet. |
| **6.2 Keywords** | **Mixed** | |
| - Adjacent / Range | **Implemented** | `rules.py` handles distance checks. |
| - Push / Place | **Missing** | No `PushStep` or `PlaceStep`. |
| - Respawn | **Missing** | No `RespawnStep`. |
| - Line of Sight | **Implemented** | Explicitly ignored per rules (Pathfinding checks valid dest, Targeting checks Range only). |

## Summary of Critical Gaps
1.  **Macro-Game Loop**: End of Round (Minion Battle, Level Up) and Win Conditions (Lane Push) are the biggest missing pieces.
2.  **Hero Lifecycle**: Death, Respawn, and Rewards are not yet hooked up to the Step engine.
3.  **Advanced Primitives**: `Push`, `Place`, and `Swap` need to be implemented as Steps.
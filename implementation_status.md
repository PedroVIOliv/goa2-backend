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
| **2.2 Turn Structure** | **Implemented** | `phases.py` handles broad state. `ResolveTieBreakerStep` handles ties. `FindNextActorStep` handles cycling. `ResolveCardStep` handles Primary/Secondary choice. |
| **2.3 Lane Push** | **Implemented** | `LanePushStep` handles Wave Counter removal, Zone transition, and Minion Wipe. Triggered by Minion Battle or Combat Death. |
| **2.4 End Phase** | **Implemented** | `EndPhaseStep` handles Minion Battle (with Heavy Constraint), Card Retrieval, and Round Reset. Level Up is placeholder. |

## 3. Entity States

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **3.1 Hero State** | **Implemented** | `DefeatUnitStep` handles Death Rewards (Killer & Assists), Life Counter penalty, and Board Removal. |
| **3.2 Minion State** | **Implemented** | `Minion` model exists. `rules.validate_movement_path` respects obstacles. **Heavy Immunity** and **Auras** are fully integrated into `ResolveCombatStep`. |

## 4. Card System

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **5.1 Card Anatomy** | **Complete** | `Card` model covers all fields. `is_facedown` logic correctly masks hidden info. |
| **5.2 Card States** | **Complete** | `CardState` enum tracks Hand/Played/Discarded/Deck. `ResolveCardStep` handles action choices. |
| **5.3 Upgrade Mechanic** | **Missing** | No logic for Upgrading cards or equipping items yet. |
| **5.1 Ultimate** | **Partial** | Ultimate cards defined, but unlocking logic is missing. |

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

## Summary of Critical Gaps
1.  **Card Effect Registry**: Actually implementing the script logic for individual cards (the "Text" of the card).
2.  **Upgrade Mechanic**: Gold economy, Level Up buying, and "tucking" cards as items.
3.  **Advanced Physics**: Handling "Displacement" when multiple units are forced into the same space during a Lane Push respawn.
4.  **Heavy Immunity**: Enforcing that Heavy minions cannot be targeted while other minions are present (Step 3.2 logic is in place but needs explicit filter integration).
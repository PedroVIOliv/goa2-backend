# Implementation Status Report
Based on `deterministic_rules.md` vs `src/goa2`.

## 1. Topographic Definitions

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **1.1 The Grid** | **Implemented** | `Hex` class handles Coordinates, Adjacency, Distance, Lines. |
| **1.2 Space Classification** | **Implemented** | `Board`, `Zone`, `Tile` exist. `SpawnPoints` have strict validation (Hero vs Minion). |
| **1.3 Object Classification** | **Implemented** | `Unit` (Heroes/Minions), `Token` (Obstacles), and `Marker` (Status Effects) are all implemented. |

## 2. Temporal Definitions

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **2.1 Game Loop** | **Partially Implemented** | `GamePhase` enum exists. `GameState` tracks Round. Loop logic is distributed in `actions.py` state transitions. |
| **2.2 Turn Structure** | **Implemented** | `PlayCard`, `RevealCards`, `ResolveNext` commands implement the flow. Simultaneous selection works. |
| **2.3 Lane Push** | **NOT Implemented** | No logic for Minion count trigger or Board Shifting found in `engine`. |
| **2.4 End Phase** | **NOT Implemented** | `GamePhase.END_PHASE` exists but no logic for Minion Battle, Token Removal, or Level Up. |

## 3. Entity States

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **3.1 Hero State** | **Partially Implemented** | `Hero` has Level, Gold, Items. **MISSING**: Life Counters, XP/Level Up Penalty logic, Max Card Tier constraints. |
| **3.2 Minion State** | **Mostly Implemented** | Types, Value (derived), Auras (in `combat.py`). **MISSING**: Heavy Immunity logic, Bounding Rule (Out of Bounds correction). |

## 4. Card System

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **4.1 Card Anatomy** | **Implemented** | `Card` model has all fields (Tier, Color, Init, Actions, Range/Radius). Validation logic enforces Tier/Color rules. |
| **4.2 Card States** | **Implemented** | `CardState` enum tracks Start/Hand/Played/Unresolved/Resolved/Discard. |
| **4.3 Upgrade Mechanic** | **NOT Implemented** | No `UpgradeCardCommand` or logic to handle buying cards. |

## 5. Actions & Keywords

| Rule Section | Status | Notes |
| :--- | :--- | :--- |
| **5.1 Action Types** | **Implemented** | `ActionType` enum covers Movement, Fast Travel, Attack, Skill, Defense, Hold, Clear. Commands implement these logic flows. |
| **5.2 Card Text Logic** | **N/A** | Hardcoded via `effect_id` for now. Atomic execution principle is followed in Commands. |
| **5.3 Keywords** | **Mixed** | Implemented: Adjacent, Faster/Slower, Range, Target. |
| | **MISSING** | `Push`, `Place`, `Immune`, `Respawn` (Heroes don't respawn yet), `Tokens` (no mechanics). |
| **5.4 Combat Logic** | **Implemented** | `AttackCommand` triggers `PlayDefenseCommand`. `combat.py` calculates power (including items + auras) and resolves results. Logic flow (Interrupt) works via `input_stack`. |

## Summary of Critical Gaps
1.  **Lifecycle**: End Phase (Minion Battle, Level Up) and Lane Push (Win Condition) are completely missing.
2.  **Entities**: Tokens and Markers are missing. Heroes rely on partial state (no lives).
3.  ** Mechanics**: Heavy Minion Immunity and Out-of-Bounds checks are missing.

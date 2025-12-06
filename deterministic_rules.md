# Guards of Atlantis II: Deterministic Rules Reference

This document provides a rigorous, implementation-agnostic definition of the game's rules, entities, and mechanics. It serves as the "Source of Truth" for game logic.

## 1. Topographic Definitions

### 1.1 The Grid
*   **Space:** A discrete hexagonal location identified by unique coordinates (e.g., Cubic `q, r, s`).
*   **Adjacency:** Two spaces are *adjacent* if they share a common edge (distance = 1).
*   **Distance:** The minimum number of steps required to travel between two spaces, assuming no obstacles.
*   **Straight Line:** A set of spaces comprising a ray originating from a source space in one of the 6 primary hexagonal directions.
*   **Zone:** A named subset of contiguous Spaces. Areas outside defined Zones effectively do not exist.

### 1.2 Space Classification
*   **Terrain:** Spaces defined as impassable obstacles (Walls, Water).
*   **Spawn Points:**
    *   **Hero Spawn Point:** Reserved for Hero Respawn. Color-coded (Red/Blue).
    *   **Minion Spawn Point:** Reserved for Minion Respawn. Typed (Melee/Ranged/Heavy) and Color-coded.
*   **Empty:** A space containing no dynamic Objects (Units/Tokens). *Note: A space with a Spawn Point is Empty if no Unit is on it.*

### 1.3 Object Classification
*   **Object:** Any entity occupying a Space.
*   **Obstacle:** Any Object that prevents another Object from entering or stopping in its Space.
    *   *Rule:* A Space may contain at most **one** Obstacle.
*   **Unit:** A subset of Objects capable of taking actions or being targeted. Includes **Heroes** and **Minions**.
*   **Token:** A static Object placed on the board (e.g., Trap, Totem). Tokens are Obstacles.
*   **Marker:** A status effect attached to a Unit (e.g., Poison). Markers are *not* Objects and do not occupy space.

---

## 2. Temporal Definitions

### 2.1 The Game Loop
The game proceeds in discrete **Rounds**. Each Round consists of exactly **4 Turns**, followed by an **End Phase**.

### 2.2 Turn Structure
A Turn is strictly sequential but processes simultaneous inputs:
1.  **Card Selection Phase:** All Players simultaneously select 1 Card from Hand.
2.  **Revelation Phase:** All elected Cards are revealed.
3.  **Resolution Phase:**
    *   Cards are evaluated in order of **Initiative** (Highest to Lowest).
    *   **Tie-Breaking Rule:**
        *   If `Team(A) != Team(B)`: Priority given to team indicated by **Tie Breaker Coin**. After `A` resolves, flip Coin.
        *   If `Team(A) == Team(B)`: Logic pauses for explicit choice by owning Team.
    *   **Execution Step:** Active Player performs **One Action** (Primary or Secondary).
        *   *Trigger:* If Action has "This Turn" effect, activate it now.
4.  **End of Turn:** "This Turn" effects expire.

### 2.3 Lane Push Trigger (Immediate)
**Condition:** Triggered **immediately** whenever the Minion Count for a Team in the `BattleZone` reaches **0** (via Defeat or Removal).
**Effect:**
1.  Flip 1 Wave Counter. If 0 remain, Game Over.
2.  Shift `BattleZone` 1 step towards losing team's Throne.
3.  Remove all Minions from old Battle Zone.
4.  Respawn Minions in new Battle Zone according to Spawn Points.
    *   **Occupied by Token:** Remove Token immediately, then Spawn Minion.
    *   **Occupied by Unit:** Owning Team **Places** Minion in the Nearest Empty Space within `BattleZone`.
        *   *Priority:* If multiple teams must Place displaced minions, order is determined by **Tie Breaker Coin**.

### 2.4 End Phase Structure
1.  **Retrieve Cards:** All Players return Played/Discarded cards to Hand.
2.  **Minion Battle:**
    *   Count Minions per Team in `BattleZone`.
    *   `Diff = Abs(RedCount - BlueCount)`.
    *   Team with fewer Minions must remove `Diff` Minions (Heavy must be last).
    *   *Trigger:* If this reduces count to 0, execute **Lane Push** (2.3).
3.  **Remove Tokens:** Clear all Tokens from grid.
4.  **Level Up:** Players with sufficient Gold MUST buy a Level.
5.  **Pity Coin:** Players who did *not* Level Up gain 1 Gold.

---

## 3. Entity States

### 3.1 Hero State
*   **Life Counters:** Partially shared resource. Consumed (flipped) when Hero is Defeated.
*   **Level Table:**
    | Level | Cost to Reach (Cum.) | Single Level Cost | Rewards on Death (Coins) | Penalty on Death (Life Counters) | Max Card Tier |
    | :--- | :--- | :--- | :--- | :--- | :--- |
    | 1 | - | - | 1 | 1 | - |
    | 2 | 1 | 1 | 2 | 1 | II |
    | 3 | 3 | 2 | 3 | 1 | II |
    | 4 | 6 | 3 | 4 | 2 | II |
    | 5 | 10 | 4 | 5 | 2 | III |
    | 6 | 15 | 5 | 6 | 2 | III |
    | 7 | 21 | 6 | 7 | 3 | III |
    | 8 | 28 | 7 | 8 | 3 | IV (Ultimate) |

### 3.2 Minion State
*   **Type:** `Melee`, `Ranged`, `Heavy`.
*   **Value (On Defeat):** `Melee/Ranged = 2`, `Heavy = 4`.
*   **Auras (Passive):**
    *   `Melee/Heavy`: Adjacent Ally +1 Defense / Adjacent Enemy -1 Defense.
    *   `Ranged`: Enemies in up to Range 2 get -1 Defense.
*   **Heavy Immunity:** Immune to *all Actions* if a Friendly Non-Heavy acts as a shield in the same Zone.
*   **Bounding Rule (Out of Bounds):**
    *   Minions must reside in the `BattleZone`.
    *   *Correction Trigger:* If a Minion is physically located outside the `BattleZone` (e.g., after a Push), it **immediately** moves via shortest path to the nearest Empty Space within the `BattleZone`.
    *   *Fallthrough:* If no path exists, it is **Placed** in the nearest Empty Space within the `BattleZone`.
    *   If two or more Empty Spaces are available and closest to the Minion, the Minion's owner team decides which to use.

---

## 4. Card System

### 4.1 Card Anatomy
Each Hero has a deck of upgradable cards.
*   **Color:** `Gold`, `Silver` (Basic); `Red`, `Blue`, `Green` (Non-Basic); `Purple` (Ultimate).
*   **Tier:** `I` (Start), `II`, `III` (Non-Basic upgrades); `IV` (Ultimate).
*   **Initiative:** Base Integer value determining turn order.
*   **Primary Action Type:** Defines the Card's Type (Attack Card, Skill Card, etc).
*   **Supertype (Basic/Non-Basic):**
    *   `Basic` (Gold, Silver): No Tier, Cannot Upgrade. Signature moves.
    *   `Non-Basic`: Have Tier, Can Upgrade.
*   **Subtype (Ranged/Non-Ranged):**
    *   `Ranged`: Has explicit `Range` icon. Logic uses `Range` value.
    *   `Non-Ranged`: No `Range` icon. Target is always Adjacent (even if card has `Radius`).
*   **Stats:**
    *   `Range`: Max distance for Ranged Actions.
    *   `Radius`: Area of Effect size.
    *   *Rule:* Value of 1 = Adjacent. Value X = Up to X spaces. No "Line of Sight" obstructions (target through obstacles).
*   **Item Icon (Tier II+):** Passive stat bonus (`+1 Attack`, `+1 Init`, etc) when "equipped".

### 4.2 Card States (Lifecycle)
*   **In Hand:** Available for selection.
*   **Played:** Selected for the current turn (Facedown).
*   **Unresolved:** Revealed in `Revelation Phase` but Action not yet completed.
    *   *Critical:* If a Hero is Defeated while their card is *Unresolved*, the card resolves with **No Effect** (active effects cancelled).
*   **Resolved:** Action completed successfully.
*   **Discarded:** Removed from cycle until `Retrieve Cards` phase.

### 4.3 Upgrade Mechanic
*   **Constraint:** Must upgrade ALL Non-Basic cards to Tier II before unlocking Tier III.
*   **Process:**
    1.  Remove 1 Card of current Tier from Hand.
    2.  Select 1 Card of Next Tier (same Color) to add to Hand.
    3.  Select the Other Card of Next Tier (same Color) to "Equip" as Item (tucked under dashboard).

---

## 5. Actions & Keywords

### 5.1 Action Types
*   **Movement:** Move Hero up to X spaces based on Icon. Obstacles block path.
*   **Fast Travel (Replaces Movement):**
    *   *Conditions:* `StartZone` Empty of Enemies AND `DestZone` Empty of Enemies AND (`StartZone` == `DestZone` OR `DestZone` Adjacent).
    *   *Effect:* Teleport to empty space in DestZone. Ignores obstacles/path. Card Text is **ignored**.
*   **Attack:** Primary Action dealing damage. (See 5.4 Combat Logic).
*   **Skill:** Primary Action executing card text.
*   **Defense:** Interrupt action played in response to Attack (Discard Card).
*   **Hold (Secondary):** Passive action. Do nothing. Available on *any* card.
*   **Clear (Replaces Attack):** Remove any number of Adjacent Tokens.

### 5.2 Card Text Logic
*   **Execution:** Atomic, sequential execution of sentences/clauses.
*   **Mandatory:** Default state. If a mandatory step fails, Action halts immediately.
*   **Optional:** Steps marked `You may`, `Up to`, `If able`. Failure does not halt action.

### 5.3 Keywords (Logic Definitions)
*   **Active Effects:** Modifiers lasting for specific duration (`This Turn`, `Next Turn`). Active upon Execution. Cancelled on Death.
*   **Adjacent:** Distance exactly 1.
*   **After/Before Attack:** Timing triggers for Logic blocks.
*   **Block:** Negate Attack effect completely if condition met.
*   **Closer/Farther:** Comparison of geodesic distance.
*   **Counts As (X):** Entity gains properties of X (Union of tags).
*   **Defeat:** Entity is removed. Trigger Rewards.
*   **Direction:** One of 6 Hex vectors.
*   **Faster/Slower:** Comparison of Card Initiative.
*   **Friendly:** Entity on same Team (Excludes Self).
*   **If Able:** Conditional execution (Soft Constraint).
*   **Ignore Obstacles:** Pathfinding treats Obstacles as Empty (cannot end move on Obstacle).
*   **Immune:** Cannot be Targeted or Affected by Active Actions. (Passive Auras pierce immunity).
*   **Move Through:** `Ignore Obstacles` but only for specific entities.
*   **Nearest:** Filter set by min distance.
*   **Place:** Teleport entity (ignoring path) to empty space.
*   **Push (X):** Move entity X spaces away from source along vector. Halts on Obstacle (unless valid to move through).
*   **Radius (X):** All spaces within Distance X.
*   **Range (X):** Max Distance for Targeting.
*   **Remove:** Delete entity from board (No Gold reward).
*   **Replace:** Swap Object A with Object B.
*   **Respawn:** Create entity at specific Spawn Point.
*   **Spawn:** Create entity from supply.
*   **Straight Line:** Raycast on 6 axes.
*   **Swap:** Exchange coordinates of two entities.
*   **Target:** Designate entity for effect. blocked by `Immune`.
*   **This Turn/Round:** Scope of Effect duration.
*   **Tokens:** Static Obstacles created by cards.

### 5.4 Combat Logic (Attack Resolution)
Atomic steps upon executing an Attack Action:
1.  **Targeting:** Validate Range, Straight Line (if required), Immunity.
2.  **Modifiers (Pre-Defense):**
    *   Apply "Before Attack" effects.
    *   Calculate `AttackPower = Base + Items + Mods`.
3.  **Defense Interrupt:**
    *   Target Hero must discard a Card from Hand (Defense Action) or Pass.
    *   Calculate `DefensePower = CardBase + Items + MinionAuras + Mods`.
4.  **Result:**
    *   If `AttackPower > DefensePower`: Target is **Defeated**.
        Defeated Hero is removed from the board and rewards are triggered.
        Any active effects for the defeated hero are cancelled.
        If the defeated hero has an unresolved effect, it is resolved with no effects.
        The next turn, just before he resolves his card, the defeated hero respawns.
    *   If `AttackPower <= DefensePower`: Attack is **Blocked** (No effect).
5.  **Aftermath:** Apply "After Attack" effects (regardless of success, unless specified "If successful").


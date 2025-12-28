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

### 1.4 Game Setup (4-6 Players)
*   **Teams:** Two equal teams (Red and Blue).
*   **Tie Breaker Coin:** Flipped at initialization to determine the initial "Favored Team".
*   **Counters:**
    *   **Wave Counters:** 5 placed at the edge of the board.
    *   **Life Counters:** 6 (for 4 players) or 8 (for 6 players) per team.

---

## 2. Temporal Definitions

### 2.1 The Game Loop
The game proceeds in discrete **Rounds**. Each Round consists of exactly **4 Turns**, followed by an **End Phase**.

### 2.2 Turn Structure
A Turn processes simultaneous inputs followed by sequential resolution:
1.  **Card Selection Phase:** All Players simultaneously select 1 Card from Hand.
2.  **Revelation Phase:** All elected Cards are revealed.
3.  **Resolution Phase:**
    *   **Sequential Iteration:** One player acts at a time. After each action completes, the engine re-identifies the player with the **Highest Initiative** among those who still have an **Unresolved** card.
    *   **Tie-Breaking Rule:**
        *   If multiple players are tied for highest initiative:
        *   **Favored Team:** The team indicated by the **Tie Breaker Coin** is the "Favored Team".
        *   **Team Choice:** If the Favored Team has tied players, they **choose** which one acts first.
        *   **Coin Flip:** Immediately after one player from the Favored Team is chosen, the Tie Breaker Coin is flipped.
    *   **Execution Step:**
        *   **Hero Respawn Opportunity:** If the Active Player's Hero is **Defeated** (not on the board), they may choose to **Respawn** at an empty Spawn Point in their Throne Zone.
            *   If they choose **NOT** to respawn, their card is resolved immediately with **No Effect** (Turn ends for this player).
        *   **Perform Action:** If the Hero is on the board (was already there or just respawned), perform **One Action** (Primary or Secondary).
        *   *Trigger:* If Action has "Active Effect" (e.g., "This Turn"), activate it now.
4.  **End of Turn:** "This Turn" effects expire.

### 2.3 Lane Push Trigger (Immediate)
**Condition:** Triggered **immediately** whenever the Minion Count for a Team in the `BattleZone` reaches **0**.
**Effect:**
1.  Remove 1 Wave Counter. If 0 remain, **Game Over (Last Push Victory)**.
2.  Shift `BattleZone` 1 step towards losing team's Throne. If it enters the Throne Zone, **Game Over (Lane Push Victory)**.
3.  Remove all Minions from old Battle Zone.
4.  Respawn Minions in new Battle Zone according to Spawn Points.
    *   **Occupied by Token:** Remove Token immediately, then Spawn Minion.
    *   **Occupied by Unit:** Owning Team **Places** Minion in the Nearest Empty Space within `BattleZone`.
        *   *Priority:* If multiple teams must Place displaced minions, order is determined by **Tie Breaker Coin** (no coin flip happens).

### 2.4 End Phase Structure
1.  **Retrieve Cards:** All Players return Played/Discarded cards to Hand.
2.  **Minion Battle:**
    *   Count Minions per Team in `BattleZone`.
    *   `Diff = Abs(RedCount - BlueCount)`.
    *   The team with fewer minions is the **Losing Team**.
    *   The Losing Team must **choose** and remove `Diff` minions.
    *   **Heavy Constraint:** Heavy minions **must** be the last minions removed from a team. They cannot be removed if a non-heavy friendly minion is available.
    *   *Trigger:* If this reduces count to 0, execute **Lane Push** (2.3).
3.  **Remove Tokens:** Clear all Tokens from grid, unless specified otherwise by a card effect for a specific token.
4.  **Level Up:** Players with sufficient Gold MUST buy a Level.
5.  **Pity Coin:** Players who did *not* Level Up gain 1 Gold.

---

## 3. Entity States

### 3.1 Hero State
*   **Life Counters:** Partially shared resource. If a team has 0 counters remaining, **Game Over (Annihilation Victory)**.
*   **Leveling:**
    *   Heroes start at **Level 1** with 0 Gold.
    *   Max Level is **8** (Ultimate Unlock).
*   **Death Rewards & Penalties:**
    *   **Killer Reward:** The player who delivers the killing blow gains Coins equal to the **Defeated Hero's Level**.
    *   **Assist Reward:** All friendly heroes of the killer gain Coins equal to the Defeated Hero's **Lowest Card Tier** currently in hand/deck (excluding Basic cards which have no tier).
    *   **Death Penalty:** The Defeated Hero's team flips (spends) Life Counters equal to the Defeated Hero's **Lowest Card Tier** (excluding Basic cards).

| Level | Cost to Reach (Cum.) | Single Level Cost | Death Reward (Killer) | Death Reward (Assist) | Death Penalty (Counters) | Max Card Tier |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | - | - | 1 | 1 | 1 | I |
| 2 | 1 | 1 | 2 | 1 | 1 | II |
| 3 | 3 | 2 | 3 | 1 | 1 | II |
| 4 | 6 | 3 | 4 | 2 | 2 | II |
| 5 | 10 | 4 | 5 | 2 | 2 | III |
| 6 | 15 | 5 | 6 | 2 | 2 | III |
| 7 | 21 | 6 | 7 | 3 | 3 | III |
| 8 | 28 | 7 | 8 | 3 | 3 | IV (Ultimate) |

### 3.2 Minion State
*   **Type:** `Melee`, `Ranged`, `Heavy`.
*   **Value (On Defeat):** `Melee/Ranged = 2`, `Heavy = 4`.
*   **Auras (Passive):**
    *   `Melee/Heavy`: Adjacent Ally +1 Defense / Adjacent Enemy -1 Defense.
    *   `Ranged`: Enemies in up to Range 2 get -1 Defense.
*   **Heavy Immunity:** Immune to *all Actions* and effects, until no more friendly minions are present in the BattleZone.
*   **Bounding Rule (Out of Bounds):**
    *   Minions must reside in the `BattleZone`.
    *   *Correction Trigger:* If a Minion is outside the `BattleZone`, it **immediately** moves via shortest path to the nearest Empty Space within the `BattleZone`. If no path exists, it is **Placed** instead via shortest distance to an empty space within the `BattleZone`.

---

## 4. Victory Conditions Summary

The game ends immediately when any of the following occur:
1.  **Lane Push Victory:** A Lane Push shifts the Battle Zone into an enemy **Throne Zone**.
2.  **Last Push Victory:** A Lane Push is triggered and the last wave counter is removed.
3.  **Annihilation Victory:** A Hero is defeated and their team has no **Life Counters** left to flip.

---

## 5. Card System

### 5.1 Card Anatomy
Each Hero has a deck of upgradable cards.
*   **Color:** `Gold`, `Silver` (Basic); `Red`, `Blue`, `Green` (Non-Basic); `Purple` (Ultimate).
*   **Tier:** `I` (Start), `II`, `III` (Non-Basic upgrades); `IV` (Ultimate).
*   **Initiative:** Base Integer value for determining turn order.
*   **Primary Action Type:** Defines the Card's Primary Action from `Attack`, `Skill`, `Defense`, `Movement`.
*   **Primary Action Value:** Defines the Card's Primary Action Value, not present for `Skill`.
*   **Text/Effect:** Defines the Card's effect which triggers when the Primary Action is executed.
*   **Secondary Action Type:** Defines the Card's Secondary Action from `Attack`, `Defense`, `Movement`.
*   **Secondary Action Value:** Defines the Card's Secondary Action Value.
*   **Subtype (Ranged/Non-Ranged):**
    *   `Ranged`: Has explicit `Range` icon. Logic uses `Range` value.
    *   `Non-Ranged`: No `Range` icon.
*   **Radius/Range Value:** Defines the Card's Radius/Range Value. A card has one of these, not both, and could also have none.
*   **Item Icon (Tier II+):** Passive stat bonus when "equipped", from `Range`, `Radius`, `Attack`, `Defense`, and `Movement`.
*   **Ultimate (Tier IV):** A special permanent card.
    *   Unlocked after upgrading all non-basic cards to Tier III.
    *   Placed on the Dashboard (permanent passive).
    *   Once unlocked, the Hero can no longer Level Up.

### 5.2 Card States (Lifecycle)
*   **In Hand:** Card is in the Hero's Hand.
*   **Played:** Card becomes played when it is placed facedown from hand into the board. A card remains played until it is back to hand.
*   **Unresolved:** Card is unresolved while no action has been executed with it yet. 
    *   **Critical Penalty:** If a Hero is **Defeated** while their card is **Unresolved**, that card is immediately resolved with **No Effect** (as if a `Hold` action was executed).
*   **Resolved:** Card is resolved after an action has been executed with it, and it goes to the Hero's Dashboard.
*   **Discarded:** A card is treated as discarded when it is put into the Discard Section of the Hero's Dashboard. In a rare case where a card is discarded after being played, it counts as both **Played** and **Discarded**.
*   **Facedown:** If a resolved or discarded card is facedown, it loses its type, color and actions, until it changes state to in hand or becomes faceup. Facedown cards are hidden information. When a card becomes facedown, cancel its Active effect.
*   **Discard a card:** A card is discarded when it is put into the Discard Section of the Hero's Dashboard. Cards in different states can be discarded. Unless otherwise specified, a card is discarded from hand. Cards used to defend are always discarded from hand. Discarded cards are open information.
*   **Swap a card:** When two cards are swapped, all their card states are swapped. If you need to swap a played and resolved card with a discarded card, the discarded card becomes played and resolved, and the played and resolved card becomes discarded.
*   **Retrieve a card:** Retrieving a card means to take one of your cards back into your hand. Cards in different states can be retrieved, depending on the card text. You retrieve all your cards at the end of each round, regardless of state. You can never retrieve another hero’s cards.

### 5.3 Upgrade Mechanic
1.  Select 1 Card of Next Lowest Tier available to add to Hand.
2.  Select the Other Card of that Tier (same Color) to "Equip" as Item.
3.  Remove the Previous Tier Card from the same Color from Hand.

---

## 6. Actions & Keywords

### 6.1 Action Types
*   **Movement:** Move Hero up to X spaces. Obstacles block path.
*   **Fast Travel (Replaces Movement):**
    *   *Conditions:* `StartZone` Empty of Enemies AND `DestZone` Empty of Enemies AND (`StartZone` == `DestZone` OR `DestZone` Adjacent to `StartZone`).
    *   *Effect:* Move to empty space. Card Text is **ignored** as Fast Travel is always a secondary action even if Movement is a primary action.
*   **Attack:** Action dealing damage. (See 6.3 Combat Logic whenever an Attack actions is a secondary action or when a primary action attack refers to something along the lines of "Perform an Attack"). Is generally adjacent only, unless otherwise specified or by having a `Range` value.
*   **Skill:** Primary Action that simply applies card text. Skills are always primary actions.
*   **Defense:** Defends against an Attack when discarded in response to an Attack. If defense is the primary action of a Card, apply card text when defending.
*   **Hold (Secondary):** Passive action. Do nothing. Available on *any* card. Is always a secondary action.
*   **Clear (Replaces Attack):** Remove any number of Adjacent Tokens. Is always a secondary action.

### 6.2 Keywords (Logic Definitions)
*   **Active Effects:** Active effects begin with a bold keyword (**Next Turn:**, **This Round:**, etc.), followed by the card text. This keyword indicates when the card text takes effect and how long it remains in effect. If your Active effect has a Radius, it is always calculated from your current space. An Active effect on your card is cancelled:
    *   When it no longer applies;
    *   If you are defeated;
    *   When the card changes state, including at the end of the round.
    *   In cases when multiple Active effects come into effect at the same time, and the order in which they are applied matters, use the same method as when resolving tied initiative, but do not flip the Tie Breaker coin.
*   **Adjacent:** Adjacent spaces are any two spaces that share a border. Two units are adjacent if they occupy adjacent spaces. Two Zones are adjacent if they have at least two non-terrain spaces that are adjacent to each other.
*   **After the Attack:** Apply this text after the target of your attack defends or is removed.
*   **Battle Zone:** The Battle Zone is a Zone where the minions are currently located. There is only one Battle Zone per Lane.
*   **Before the Attack:** Apply this text before the target of your attack defends or is removed. This effect happens even if the attack itself fails to connect due to range or other restrictions.
*   **Block:** Prevent the attack completely if the condition is met.
*   **Choose (One / Twice / Up to / etc.):** Choose a bullet point (or bullet points) and apply that text, ignoring the rest.
*   **Closer (Space):** A space is closer to you than another space if there are fewer spaces on the shortest path of spaces connecting you and that space (including spaces with obstacles).
*   **Count as:** If an object counts as an object of a different type, all rules and qualities of that object are replaced by the rules and qualities of the object type(s) it now counts as.
*   **Defeat:** Remove the defeated enemy unit and collect the corresponding amount of coins. You can never defeat a friendly unit.
*   **Direction:** There are six directions on a hexagonal board. Moving in the same direction means moving in a straight line in one of those six directions.
*   **Empty (Space / Spawn Point):** An empty space is a space with no obstacles. An empty space can have a Spawn point. An empty Spawn point is a Spawn point in an empty space.
*   **End of Turn (Active Effect):** The text after a bold **End of turn** keyword is applied once, at the end of the current turn (after all players have had their chance to act).
*   **End of Round (Active Effect):** The text after **End of Round** keyword is applied once, at the end of this round.
*   **Farther / Farthest:** Whenever you need to figure out the distance between two spaces or objects, count the spaces between them (including spaces with obstacles).
*   **Friendly:** A friendly unit means another unit on your team. It never includes you. If a card affects your hero, it will explicitly say so (“You and friendly heroes”).
*   **Hero:** Heroes are player avatars in the game. Only heroes can perform actions. Defeated heroes respawn by spending gold.
*   **If Able:** If a sentence ends with this keyword, the clause preceding the keyword is non-mandatory. If it is at the beginning, the entire sentence is non-mandatory.
*   **Ignoring Obstacles:** A unit with the ability to ignore obstacles is allowed to enter a space with an obstacle and leave that space in any direction, while moving. However, a unit can never end its movement on the same space as an obstacle, and any special effects of tokens are still applied.
*   **Immune:** If a unit is immune, you cannot target that unit, and that unit is not affected by your actions, unless the card text says otherwise.
    *   If a unit is immune to a specific action type, it is not affected (and cannot be targeted) by actions of that type (and their active effects) but is affected by other effects and actions.
    *   Effects that check for unit presence (i.e. “if you are adjacent to a minion”) will count immune units.
    *   Units that ignore obstacles can move through an Immune unit, or a token.
    *   You are never immune to your own actions.
*   **Markers:** Markers are used as reminders and are usually given to other heroes as part of the card’s effect; Unlike tokens, markers are usually not placed on the board.
*   **Nearest:** Whenever you need to figure out the distance between two spaces or objects, count the spaces between them (including spaces with obstacles).
*   **Next Turn (Active Effects):** The text that follows the “Next turn” keyword comes into effect at the start of the next turn and remains in effect for the duration of that entire turn.
*   **Remove:** Remove a game piece (such as a miniature, or a token) from the board. Do not collect any coins.
*   **Replace:** Swap an object (such as a miniature or a token on the board) with a different object.
*   **Respawn:** If a card text instructs you to respawn a minion, place the minion miniature on the board into an empty space. You can only respawn a minion if there are more minion spawn points of that type and color (empty or not), than there are minion miniatures of that type and color present in that Battle Zone.
*   **Space:** A space is a single hex on the game board. Any space can be either empty, or contain a maximum of one obstacle.
*   **Spawn:** Similar to place, but unlike **Place**, the spawned object must be taken from the supply and cannot be taken from the board.
*   **Spawn Point:** Spaces on the board used to spawn minions and heroes. Spawn points are not obstacles.
*   **Straight Line:** A straight line is a sequence of spaces arranged in a file. A single space counts as a straight line. Two units are in a straight line if they are adjacent, or if you can draw a straight line of spaces through spaces occupied by both of those units.
*   **Swap (with Unit / Token):** Two objects on the board swap places with each other. This does not count as movement or placement.
*   **Target (Unit / Token / Space):** Whenever your action has any effect on another unit in any way, you target that unit. Effects that check for unit presence (i.e. “if you are adjacent to a minion”) do not target.
*   **Terrain:** Any board space without a full grid outline counts as terrain and is an obstacle, including the water spaces surrounding the board.
*   **This Turn / Round (Active Effect):** The text that follows the “This Turn” / “This Round” keyword comes into effect immediately and remains in effect for the duration of that entire turn / round.
*   **Tokens:** Tokens represent various temporary objects in the game. All tokens are obstacles. Once a token is placed, it retains all its properties until that token is removed (this does not include Active effects). If a unit Spawns in a Spawn Point covered by a token, remove the token first, then spawn the unit. All heroes have an option to remove any tokens they are adjacent to by performing a “Clear” action. Unless the card text says otherwise, tokens are removed at the end of round. Tokens are not removed when the hero who placed them is defeated.
*   **Unit:** Units means heroes and minions. Tokens are not units.
*   **Zone:** A Zone is an area of the board comprised of multiple spaces.

### 6.3 Combat Logic (Attack Resolution)
1.  **Targeting:** Validate Range and Immunity.
    *   **Line of Sight:** There are **NO** line of sight rules. Targets may be selected through obstacles as long as they are within Range/Radius.
2.  **Modifiers:** Calculate `AttackPower` (Base + Items + Before Attack effects).
3.  **Defense Interrupt:**
    *   Target Hero may **discard** a card from hand to use its Defense Value.
    *   Calculate `DefensePower` (Card + Items + Minion Auras + Mods).
4.  **Result:**
    *   If `AttackPower > DefensePower`: Target is **Defeated**.
    *   If `AttackPower <= DefensePower`: Attack is **Blocked**.
    *   *Note:* Minions have no Defense Interrupt and are always defeated if targeted.
5.  **Aftermath:** Apply "After Attack" effects.
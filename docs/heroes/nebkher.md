# Nebkher: The Topology Challenge

## The Problem: "Crack in Reality"

Nebkher's cards (**Crack in Reality**, **Shift Reality**) introduce a mechanic that fundamentally breaks the standard rules of the hexagonal grid.

> *"Split the board into two sides with a straight line of spaces drawn through your space. This turn: **Units on either side of the line cannot interact with objects and spaces on the other side of the line, as if they did not exist**."*

### Why Standard Approaches Fail

1.  **Treating it as "Walls" or "Terrain":**
    *   In GoA2, "Range" and "Auras" pass through walls. You can shoot over a rock.
    *   If we simply marked the dividing line as `Terrain`, units wouldn't be able to move *through* it, but they could still target enemies on the other side. This violates the "as if they did not exist" rule.

2.  **Treating it as "Line of Sight" (LOS):**
    *   GoA2 generally does not have "Line of Sight" blocking for standard attacks.
    *   Even if we implemented LOS, "Auras" (Radius effects) typically ignore LOS. Nebkher's reality split must block *everything*.

3.  **The "Void" Problem:**
    *   If we strictly treated the other side as "null", the game engine might crash when looking up an enemy ID that suddenly "doesn't exist."

---

## The Solution: Dynamic Board Topology

We move from a **Static Grid** model (where distance is a constant mathematical formula) to a **Dynamic Graph** model.

### 1. Board Connectivity Service
Instead of hacking specific `Unit` or `Tile` logic, we inject a layer into the `Board` itself. The Board becomes the authority on "Reality."

*   **Current State:** `Board` assumes a continuous mesh where Hex A always neighbors Hex B.
*   **New State:** `Board` maintains a list of **TopologyConstraints**.

When the Engine asks: *"What is the distance between Hex A and Hex B?"*
1.  The Board checks active constraints (e.g., Nebkher's Split).
2.  It determines if Hex A and Hex B are in the same **Connected Component**.
3.  **If Disconnected:** It returns `Infinity` (or `False` for connection checks).
4.  **If Connected:** It returns the standard mathematical distance.

### 2. The Logic: Connected Components
Nebkher's split creates two disjoint subgraphs.
*   **Subgraph A:** Everything "Left" of the line.
*   **Subgraph B:** Everything "Right" of the line.

Any query (Movement, Attack Range, Aura, Skill) originating in Subgraph A checking a target in Subgraph B will receive a **"Not Connected"** response.

*   **Movement:** Pathfinding fails immediately (no neighbors exist across the boundary).
*   **Range/Auras:** Distance is infinite, so `Distance <= Range` checks always fail.

---

## Handling Edge Cases

### 1. "Global" Effects
**The Issue:** Some cards (e.g., Brynn's *Over the Top*, Dodger's *Tide of Darkness*) affect "All units" or "All spaces."
**The Fix:**
We redefine "Global" in the engine. "Global" does not mean "The entire map file." It means **"Everywhere reachable by the source."**
*   When a Global effect attempts to target a unit, the engine runs the `Board.are_connected(source, target)` check first.
*   If they are in different realities, the Global effect **does not apply** to that specific target.

### 2. Game Engine vs. Unit Interaction
**The Issue:** Does the "Minion Battle" (counting minions to determine zone control) respect the split?
**The Logic:**
*   Nebkher's card restricts **Units** ("Units ... cannot interact").
*   It does **not** restrict the **Game Engine/Referees**.
*   **Minion Battle:** The Engine counts minions in the `ActiveZone`. It does not require minions to "see" each other; it just counts heads. Therefore, Minion Battles proceed normally, counting units on both sides of the divide.

### 3. The Dividing Line ("Region Zero")
The cards imply the line itself is drawn through a specific space (the axis, e.g., $q=0$). This creates three regions: **Negative** ($q<0$), **Positive** ($q>0$), and **Zero** ($q=0$).

The interaction rules differ significantly between tiers:

#### Tier 2 (*Crack in Reality*)
*   **The Split:** Interaction between **Negative** and **Positive** is blocked.
*   **The Bridge:** Interaction between **Zero** and *either* side is **Allowed**.
    *   *Result:* The line effectively belongs to both sides simultaneously. Units can step onto the line from the left, and then step off to the right (if they have enough movement to stop on the line). Ranged attacks cannot skip over the line to hit the other side directly.

#### Tier 3 (*Shift Reality*)
*   **The Split:** Same as Tier 2 (Negative $\nleftrightarrow$ Positive).
*   **The Isolation:** The card adds: *"Cannot interact **with you**"*.
    *   This creates a specific exception for **Nebkher's Tile** (which is inside Region Zero).
    *   **Rule:** Interaction with Nebkher's Tile is allowed **ONLY** from Region Zero.
    *   **Result:**
        *   Left/Right $\rightarrow$ Line (Empty): **Allowed**.
        *   Left/Right $\rightarrow$ Nebkher: **BLOCKED**.
        *   Line $\rightarrow$ Nebkher: **Allowed**.

This requires the `TopologyConstraint` to support both a "Split Axis" mode and a "Conditional Isolation" mode for specific coordinates on that axis.

## Summary
By solving this at the **Board/Graph** level:
1.  We avoid "spaghetti code" (`if unit == 'Nebkher'`) scattered throughout 50+ card effect files.
2.  We robustly handle all interaction types (Move, Range, Aura) simultaneously.
3.  We preserve the "Logic as Data" philosophy by modeling the Split as a `TopologyConstraint` object in the Game State.

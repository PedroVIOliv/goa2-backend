Guards of Atlantis II - Backend Engineering Plan

1. Architectural Overview

The backend is a Deterministic State Machine driven by the Command Pattern. It follows Hexagonal Architecture (Ports & Adapters), isolating the Game Domain (Rules) from the Infrastructure (API/WebSockets).

Core Principles

Server-Authoritative: The client is a dumb terminal. It sends Intentions (Play Card X), not Results (Move to Hex Y).

Deterministic: Given Initial State $S_0$ and a sequence of Commands $C_0...C_n$, the Final State $S_n$ must always be identical.

Stateless Logic: The GameEngine takes (CurrentState, Command) and returns (NewState, Events).

Integer Math Only: To ensure consistency across different hardware/languages, all grid math uses integer Cube Coordinates.

2. Key Technical Challenges

A. The "Interrupt" Stack (Attack & Defense)

Standard turn-based games follow Input -> Resolve. GoA2 follows Input -> Suspend -> Wait for Reaction -> Resolve.

Problem: When Player A attacks Player B, the resolution of Player A's card pauses. Player B must be prompted to discard a card.

Solution: We cannot use simple linear functions. We must implement a Sub-Phase State Machine.

The Game State enters Phase.DEFENSE_RESOLUTION.

The active_player switches to the Defender.

All other inputs are rejected until the Defender acts or times out.

B. Simultaneous Input / Sequential Resolution

Problem: All players commit cards at once (hidden information), but actions happen sequentially based on Initiative (public information).

Solution: A two-buffer system.

pending_inputs: Stores encrypted/hidden commands during the Planning Phase.

resolution_queue: A Priority Queue sorted by Initiative $(CardValue + TieBreaker)$ populated during the Resolution Phase.

C. Same-Team Tie Resolution

Problem: When two players on the same team have the same initiative, the rules require them to "decide" who goes first. The engine cannot pick entirely randomly or deteriministically without player input.

Solution: Another "Interrupt" state.
1. The Resolver detects a tie between `Hero A` and `Hero B` (Same Team).
2. Game State transitions to `Phase.TIE_RESOLUTION`.
3. The engine waits for a `ResolveTieCommand(hero_id=...)` from the team.
4. Once received, that specific Hero executes; the other remains in the queue.

D. The "Sliding Window" Grid

Problem: The map is large, but gameplay is constrained to a "Battle Zone" that shifts physically during "Lane Pushes."

Solution:

Global Grid: A static set of all valid Hexes ($q,r,s$).

Active Window: A dynamic filter that rejects movements outside the current BattleZoneID.

3. The Minimum Viable Board (MVB)

To prove the engine works, we do not need the full "Magma & Ice" map or 10 players. We need a constrained environment to validate the physics of the game.

MVB Requirements

Grid: A single defined area (e.g., radius 3 hexes around 0,0,0) representing one "Zone".

Entities:

2 Heroes (Red vs Blue).

1 Static Obstacle (to test Line of Sight/Movement blocking).

Logic:

Validating Hex adjacency and straight lines.

Validating movement path collisions.

MVB Exclusions (Postponed Logic)

Minion Battle Resolution (End of Round Math).

Lane Pushing / Respawning.

Leveling Up / Items.

Fast Travel (Zone-to-Zone movement).

4. Implementation Roadmap

We will build the system in 5 Distinct Phases. We are currently at Phase 1.

Phase 1: Domain Primitives (Current)

[x] Hex Kernel: Cube coordinates, distance, straight-line checks.

[x] Models: Define Hero, Card, Minion, Team.

[x] Board: Define Zone and Board container (static map data).

Phase 2: State & Command Engine

[x] GameState: Define the Pydantic model holding the entire mutable world.

[x] Command Interface: Abstract base class for all game actions.

[x] Phase Management: Enums for SETUP, PLANNING, RESOLUTION.

Phase 3: The Game Loop (MVP)

[x] PlayCardCommand: Logic to move a card from Hand to "Pending".

[x] Reveal Logic: Sorting the resolution_queue by initiative.

[x] Movement Resolution: Executing a card that simply moves a hero 2 spaces.

[x] Static Minions: Placing dumb Minions on board to act as Obstacles/Targets.

Phase 4: Combat & Interrupts (The Hard Part)

[x] AttackCommand: Calculating range and valid targets.

[x] Defense Flow: Implementing the state transition to DEFENSE_WAIT.

[x] Damage Application: Reducing Life Counters.

Phase 5: Map Complexity

[x] Zones: Connecting multiple zones.

[x] Fast Travel: Logic to jump between zones.

[x] Pushing: Logic for shifting the Battle Zone.

5. Directory Structure (Reference)

src/goa2/
├── domain/                  # PURE DATA (Pydantic Models)
│   ├── hex.py               # Coordinate Math (Done)
│   ├── models.py            # Hero, Card, Minion definitions
│   ├── board.py             # Map container
│   ├── state.py             # The "Save File" structure
│   └── commands.py          # Action definitions (Inputs)
├── engine/                  # LOGIC (Functions)
│   ├── rules.py             # Targeting/Movement validation
│   ├── phases.py            # State Machine transitions
│   └── resolver.py          # Processing the Queue
└── main.py                  # API Entrypoint

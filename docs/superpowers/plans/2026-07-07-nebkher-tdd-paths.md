# NebKher — TDD Test Paths (for review)

Status: **FULLY IMPLEMENTED** (2026-07-08). All 18 card effects (including the critical infrastructure and all delegable families: Imbue Doubt family, Fleeting Image family, Illusionary Force family, Phantasmal Sentry/Warrior family, and Twist Fate family) have been fully implemented in [nebkher_effects.py](file:///Users/pedrooliveira/Documents/goa2/goa2-backend/src/goa2/scripts/nebkher_effects.py) and verified with comprehensive test coverage in [test_nebkher_effects.py](file:///Users/pedrooliveira/Documents/goa2/goa2-backend/tests/engine/effects/cases/test_nebkher_effects.py).

NebKher is an illusion/topology hero: 17 cards + ultimate, 10 unique effect
classes. Data: `src/goa2/data/heroes/nebkher.py`. Effects will live in
`src/goa2/scripts/nebkher_effects.py`. Tests use `tests/engine/effects/`
helpers (`EffectScenarioBuilder` + `run_card`), marked `effect_contract` /
`effect_flow`, per repo convention.

## Locked interpretations (confirmed with user, 2026-07-07)

1. **Illusion tokens**: supply **3**; standard tokens — obstacle,
   non-passable, removed at end of round, not facedown, no special immunity.
2. **"Place up to N"**: free choice of 0..N, placed one at a time (not
   all-or-nothing).
3. **Imbue Doubt family timing**: "Next turn, after playing cards" fires
   after **every player has committed and revealed** cards next turn,
   **before any resolution**. Discards come from **hand only** (the
   committed card is safe). Radius is measured from NebKher's position **at
   that moment**.
4. **Crack in Reality**: player picks one of the **3 hex axes** through
   NebKher's space; the line is **fixed after cast** even if he moves;
   units standing ON the line interact with both sides (line = bridge);
   both friendly and enemy interactions are blocked across the line, both
   ways.
5. **Shift Reality**: isolation is **mutual** — units on either side cannot
   interact with NebKher AND NebKher cannot interact with them; only
   units on the line can.
   > **SUPERSEDED 2026-07-21** (rules-audit response §3.4): the isolation is
   > **one-way**. Units on either side still cannot interact with NebKher and
   > line units still can, but NebKher is *not* affected by his own ability —
   > for his movement, targeting, placement and radius the split does not
   > exist. See `docs/audit_claims_tracker.md` §3.4.
6. **Illusionary Force/Army equivalence**: active only **during NebKher's
   own actions**. During his attacks the minion defense modifier applies
   (an Illusion adjacent to his target counts as an enemy-of-target melee
   minion). During his **defense** it does NOT apply (that is the
   attacker's action). While active, **minion / friendly / melee-minion
   filters** evaluated during his actions must match Illusion tokens.
7. **Mind Grip** (updated 2026-07-07 after review): the action chooser is
   **exactly the normal card-resolution menu minus defense** — every action
   available on that card as if NebKher were resolving it normally (primary,
   secondary movement, gold/basic options, Fast Travel, **Hold** — Hold is
   always available, so every prev-slot card offers at least one action).
   `build_steps` is called when the primary action is chosen (with token
   substitution). Values come from **that card** (attack, movement, etc.)
   computed with **NebKher as actor** (his stats/items/modifiers).
   "Previous turn slot" is indexed **by turn number** — on turn T it is the
   card played on turn T-1, regardless of whether that enemy has already
   resolved this turn. "Skip giving markers" = skip the marker step and
   **continue** with the rest of the effect.
8. **Diabolical Laughter**: the laugh is a YES/NO confirm; declining does
   **nothing at all**. "Choose up to three times" = any mix, same bullet
   repeatable. Card-swap bullet: NebKher picks the enemy hero (radius) AND
   which **2 of their resolved cards** to swap (needs ≥ 2 resolved).
9. **Ultimate**: fires **immediately after the laugh** (before the three
   choices); **respects immunity**; each victim chooses their discard;
   defeated only when hand is empty.
10. **Phantasmal Warrior/Champion**: the Illusion's move is
    **path-constrained** (blocked by obstacles/units like unit movement).

## Spec decisions made by implementer (veto during review if wrong)

- **S1**: Imbue Doubt family played on the round's **last turn fizzles**
  (NEXT_TURN never crosses rounds — Emmitt Reverse Time precedent).
- **S2**: Trigger firing order at "after playing cards": fires after reveal
  AND after any Emmitt-ultimate two-card retrieval settles hands, before
  `FindNextActorStep` / the first action of the turn.
- **S3**: "Up to two enemy heroes" (An Illusion of Choice): NebKher picks
  victims **at trigger time**, sequentially (immunity re-checked between
  picks); the same hero cannot be picked twice.
- **S4**: The named color is **public** — emitted as a `GameEvent` so all
  clients see it.
- **S5**: The split line is implemented as `split_axis` ∈ {q,r,s} +
  `split_value` = NebKher's coordinate on that axis at cast time (existing
  `ActiveEffect` fields; existing `TopologyService` semantics).
- **S6**: Shift Reality's isolation follows **NebKher's current position**
  (not the cast-time hex): `isolated_hex` is kept in sync with his
  location while the effect is active (he can only move along his side /
  the line anyway, since movement across the line is blocked).
- **S7**: "Swap with an Illusion token **in play**" = anywhere on the
  board, no range limit (still subject to any active topology split —
  a cross-line swap is an interaction and is blocked).
- **S8**: Mind Grip's copied ATTACK keeps the **copied card's**
  `is_ranged`/range (values computed with NebKher's modifiers), matching
  the existing `PerformPrimaryActionStep`/Commune precedent.
- ~~**S9**~~ (obsolete after review): every card offers at least Hold, so
  every enemy hero with a card in the previous slot is selectable.
- **S10** (updated after review): Equivalence (Illusionary Force/Army) is
  gated on `current actor == the effect's SOURCE` (whoever performed the
  card — NOT hardcoded to NebKher, so copy/perform mechanics bind to the
  performer). Consulted by the minion defense modifier in `stats.py`, by
  unit filters, AND by `SelectStep(target_type=UNIT)` candidate
  enumeration, which must include Illusion tokens while the effect is
  active for the current actor (not just filter matching).
- **S11**: Diabolical Laughter menu: an iterated choose-one (up to 3);
  bullets with no legal option are not offered; when no bullet is legal
  the menu ends early.
- **S12**: Phantasmal Warrior/Champion: "up to N spaces" includes 0 (token
  already adjacent to the chosen hero); destination must be empty; the
  token paths through non-obstacle hexes only.
- **S13**: Mind Grip token substitution replaces the **token type** of any
  placement in the copied effect with ILLUSION (same counts/positions),
  pulling from the Illusion supply with standard supply reconciliation;
  substituted Illusions follow Illusion rules (removed at end of round).

## New engine primitives (each gets its own unit tests)

| # | Primitive | Where | Owner |
|---|-----------|-------|-------|
| P1 | `TokenType.ILLUSION`, supply 3 | `domain/models/enums.py`, `token.py` | delegate |
| P2 | Topology card layer: `CreateEffectStep` passthrough for `split_axis`/`split_value`/`isolated_hex`, axis chooser (NUMBER select), THIS_TURN lifecycle, isolation position sync (S6), `GameEvent` for the client to draw the line | `engine/steps/effects.py`, `scripts/nebkher_effects.py`, `domain/events.py` | **me** |
| P3 | "After playing cards" firing point: new DELAYED_TRIGGER schedule fired at the revelation→resolution boundary (`phases.py`), NEXT_TURN-scoped with round-boundary fizzle | `engine/phases.py`, `domain/models/effect.py` | **me** |
| P4 | `EffectType.ILLUSION_MINION_EQUIVALENCE` + integration in `stats.py` minion defense modifier, unit filters (minion/friendly/melee matching), and `SelectStep(UNIT)` candidate enumeration (tokens offered as units); gated on current actor == effect source | `domain/models/effect.py`, `engine/stats.py`, `engine/filters_units.py`, `engine/steps/selection.py` | **me** |
| P5 | `PerformCardActionStep`: reuses the normal card-resolution action menu minus defense (primary, secondary movement, basic options, Fast Travel, Hold), context flags `token_type_override` (consumed by `PlaceTokenStep`/`PlaceTokenBatchStep`/line/trail) and `skip_markers` (consumed by `PlaceMarkerStep`) | `engine/steps/cards.py`, `engine/steps/markers.py` | **me** |
| P6 | `PassiveTrigger.AFTER_LAUGH` + `LaughStep` (YES/NO confirm, emits event, fires trigger) | `domain/models/enums.py`, `engine/steps/` | **me** |
| P7 | Resolved-slot swap: reuse `Hero.swap_cards`/`SwapCardStep` if it covers resolved↔resolved (Emmitt Time Warp precedent), else a thin `SwapResolvedCardsStep`; must preserve active effects (card-id-bound, so free) and be visible to prev-slot lookups | `engine/steps/cards.py` | **me** |

Everything not listed above is effect-body assembly from existing
primitives (Wuk Canopy swap, Emmitt Glitch swap/batch, `MoveTokenStep`,
`CountMatchFilter`, `ChooseCardColorStep`, `ForceDiscardStep(color_key)`,
`ForceDiscardOrDefeatStep`, choose-one branching) — delegable.

---

# Per-card test paths

Notation: **H** = happy path, **U** = unhappy/edge path. Range/radius checks
always use topology distance. Offensive targeting includes `ImmunityFilter`
unless stated.

## 1. Imbue Doubt / Time to Reconsider
`imbue_doubt` (radius 3) / `time_to_reconsider` (radius 4) — one class.

> "Name a color. Next turn, after playing cards: An enemy hero in radius
> discards a card of that color, if able."

- **H1** Name BLUE → next turn after all commits/reveals, enemy hero in radius with a BLUE card in hand → NebKher picks the victim → victim picks which BLUE card → discarded before any action resolves.
- **H2** Radius from NebKher's position at trigger time: enemy out of radius at cast but in radius at trigger → valid (and vice versa).
- **H3** Victim holds two cards of the color → victim chooses which.
- **H4** Color choice emits a public event (S4) offering the 5 standard colors.
- **U1** Victim has no card of the color in hand → "if able": nothing, no penalty.
- **U2** Victim's only card of the color is their committed (revealed) card → hand-only: no discard.
- **U3** No enemy hero in radius at trigger → fizzles.
- **U4** Played on the round's last turn → fizzles (S1).
- **U5** NebKher defeated before the trigger → effect deactivates, no discard (card-bound default).
- **U6** Immune enemy hero at trigger → excluded from selection.
- **U7** Trigger order (S2): with an Emmitt two-card reveal in play, the discard fires after the retrieve settles the hand.

## 2. An Illusion of Choice
`an_illusion_of_choice` (radius 4).

> "…Up to two enemy heroes in radius each discard a card of that color, if able."

- **H1** Two enemy heroes in radius → pick both → each discards a card of the color (each picks their own).
- **H2** Pick only one of two candidates ("up to").
- **H3** One victim has the color, the other doesn't → first discards, second does nothing (per-victim "if able").
- **U1** Pick zero → nothing.
- **U2** Same hero cannot be picked twice (sequential picks exclude prior pick).
- **U3** Second pick re-checks immunity after the first discard resolves (S3).

## 3. Crack in Reality
`crack_in_reality` (THIS_TURN, `TOPOLOGY_SPLIT`).

> "Split the board into two sides with a straight line of spaces drawn
> through your space. This turn: Units on either side cannot interact with
> objects and spaces on the other side, as if they did not exist."

- **H1** Cast → prompt offers exactly 3 axis options through NebKher's hex → effect created with `split_axis`/`split_value` = his cast position.
- **H2** Enemy on one side cannot target (attack/skill) a unit on the other side.
- **H3** Movement pathfinding cannot cross the line.
- **H4** A unit standing ON the line interacts with both sides; both sides can interact with it.
- **H5** Radius effects/auras do not reach across the line.
- **H6** NebKher moves off the line after casting → the line stays at the cast position (locked interp 4).
- **H7** Expires at end of turn → cross-line interaction restored.
- **U1** Push cannot cross the line (unit stops at it).
- **U2** Friendly cross-line interactions are blocked too (ally swap/nudge targeting fails).
- **U3** Client contract: a `GameEvent` describing the split is emitted on creation and on expiry (P2).

## 4. Shift Reality
`shift_reality` (THIS_TURN, `TOPOLOGY_ISOLATION`). Inherits all Crack in Reality paths, plus:

> "…Units on either side of the line cannot interact with you, nor with
> objects and spaces on the other side…"

- **H1** Enemy on either side cannot target NebKher (only units on the line can).
- **H2** Mutual: NebKher cannot target units on either side; he CAN target units on the line.
- **H3** NebKher moves along his side → isolation follows his current position (S6): enemy adjacent to his NEW hex but off-line still cannot target him.
- **U1** Aura/radius effects from either side do not affect NebKher.
- **U2** Expiry restores everything.

## 5. Fleeting Image / Multiple Projections / Master of Illusions
`fleeting_image` (N=1, radius 2) / `multiple_projections` (N=2, radius 3) / `master_of_illusions` (N=3, radius 3) — one class.

> "Place up to N Illusion tokens in radius. You may swap with an Illusion
> token in play."

- **H1** Place N tokens on empty hexes in radius.
- **H2** Place fewer than N, including zero (free 0..N choice).
- **H3** Swap with an Illusion token anywhere on the board (no range — "in play").
- **H4** Swap with a token placed by this very card ("in play" includes them).
- **H5** Supply reconciliation: 3 Illusions already on board, place more → prompted to remove existing Illusions first (standard `PlaceTokenStep` behavior).
- **H6** Decline the swap → action completes.
- **U1** No empty hex in radius → placement yields nothing; swap still offered if an Illusion exists.
- **U2** No Illusion in play and none placed → swap silently skipped.
- **U3** Placed token is an obstacle: blocks enemy movement/pathing; cannot be placed on occupied/terrain/spawn hexes.
- **U4** End of round → all Illusion tokens removed from the board, returned to supply.

## 6. Illusionary Force / Illusionary Army
`illusionary_force` (N=2, radius 4) / `illusionary_army` (N=3, radius 4) — one class.

> "Place up to N Illusion tokens in radius. This round: While you are
> performing actions, all Illusion tokens count as both tokens and friendly
> melee minions."

Placement paths as family 5 (H1/H2/U1). Equivalence paths:

- **H3** During NebKher's attack, an Illusion adjacent to his enemy target applies the minion defense modifier as an enemy-of-target melee minion (−1 defense for the target).
- **H4** During NebKher's actions, a friendly-minion filter (e.g. `UnitTypeFilter(MINION)` + `TeamFilter(FRIENDLY)` collect) matches Illusion tokens.
- **H4b** `SelectStep(target_type=UNIT)` during his actions offers Illusion tokens as candidates (enumeration, not just filter matching).
- **H4c** Effect-source gate: if another hero performs the card (copy/perform mechanic), the equivalence binds to THAT performer's actions, not NebKher's.
- **H5** THIS_ROUND: still applies on NebKher's later turn in the same round (with Illusions still on board).
- **H6** Stacks correctly with a real friendly melee minion adjacent to the same target (both counted).
- **U2** Enemy attacks NebKher: an Illusion adjacent to him grants NO defense bonus (not his action).
- **U3** A teammate's attack gets no benefit (effect is "you" only).
- **U4** Minion battle: Illusions do NOT count toward minion totals (not an action).
- **U5** Effect ends at end of round (and tokens are removed anyway).
- **U6** Illusions remain obstacles/tokens throughout ("both tokens and minions") — token-type filters still match them.
- **U7** NebKher cannot attack/defeat an Illusion (friendly).

## 7. Phantasmal Sentry
`phantasmal_sentry` (ATK 2, ranged, range 4).

> "Choose one — • Target a hero in range adjacent to an Illusion token in
> range. • Target a unit adjacent to you."

- **H1** Bullet 1: enemy hero within range 4, adjacent to an Illusion that is itself within range 4 → attack resolves.
- **H2** Bullet 2: any enemy unit adjacent to NebKher (minion or hero) → attack.
- **H3** Bullet 2's adjacent attack is still RANGED (card property — ranged-block defenses apply).
- **U1** Bullet 1: hero in range whose only adjacent Illusion is OUT of NebKher's range → invalid target.
- **U2** Bullet 1 chosen with no legal target → mandatory failure → action aborts (no fallback to bullet 2).
- **U3** Immune hero/unit excluded in both bullets.
- **U4** Cross-check: range uses topology distance (split active → cross-line target invalid).

## 8. Phantasmal Warrior / Phantasmal Champion
`phantasmal_warrior` (move ≤ 1, ATK 3, range 5) / `phantasmal_champion` (move ≤ 2, ATK 3, range 5) — one class.

> "Choose one — • Before the attack: Move an Illusion token in range up to N
> spaces to a space adjacent to an enemy hero in range. Target that hero.
> • Target a unit adjacent to you."

- **H1** Bullet 1: select Illusion in range → select empty hex adjacent to a target enemy hero in range (≤ N, path-constrained) → select that target enemy hero adjacent to the hex → move token to hex → attack is forced onto that hero.
- **H2** Token already adjacent to the chosen hero → move 0 allowed (S12).
- **H3** Bullet 2: attack a unit adjacent to NebKher (still ranged, as family 7 H3).
- **U1** Token move is path-constrained: a wall of obstacles between token and destination → destination invalid even within N.
- **U2** Destination must be empty (not the hero's own hex, no units/tokens/terrain).
- **U3** Enemy hero at range 6 → destination hex adjacent to them not selectable even if reachable by the token.
- **U4** Forced target: after the move, the attack cannot be redirected to any other unit.
- **U5** Bullet 1 chosen but no (token, hero, path) combination exists → mandatory failure → abort.
- **U6** Immune hero not selectable.

## 9. Twist Fate / Devious Scheme
`twist_fate` (ATK 4, range 2; Illusion **adjacent to you**) / `devious_scheme` (ATK 4, range 2; Illusion **in range**) — one class, parameterized swap-token zone.

> "Target a unit in range. After the attack: You may swap an enemy unit in
> range with an Illusion token [adjacent to you / in range]."

- **H1** Attack a unit in range; after combat fully resolves → swap an enemy unit in range with an Illusion in the card's zone.
- **H2** Swap declined → action completes.
- **H3** Attack target defeated → a DIFFERENT enemy unit in range can still be swapped.
- **H4** Swapped unit may be the (surviving) attack target itself.
- **H5** Post-attack ranges measured from NebKher's position when the swap resolves.
- **U1** No Illusion in the required zone → swap silently unavailable.
- **U2** Immune enemy (heavy minion, smoke-bombed hero) not swappable.
- **U3** Attack aborts (no target in range) → mandatory failure → no swap either.
- **U4** Zone difference: token adjacent-to-NebKher valid for Twist Fate but a token at distance 2 is only valid for Devious Scheme.

## 10. Diabolical Laughter
`diabolical_laughter` (SILVER basic skill, radius 4).

> "Laugh diabolically; if you do, choose up to three times — • Swap with an
> Illusion token in radius. • Place an Illusion token in an adjacent space.
> • Swap two resolved cards of an enemy hero in radius, without canceling
> active effects."

- **H1** Laugh YES → three picks, any mix incl. repeats (e.g. swap, swap, place).
- **H2** Bullet 1: swap NebKher with an Illusion within radius 4.
- **H3** Bullet 2: place an Illusion in an empty adjacent hex (supply rules apply).
- **H4** Bullet 3: pick enemy hero in radius with ≥ 2 resolved cards → pick 2 of their resolved cards → slots swapped; an active effect bound to one of them keeps working; a subsequent previous-turn-slot lookup (Mind Grip / Cutter-ult style) sees the NEW order.
- **H5** Stop after 0/1/2 picks (each pick optional).
- **U1** Laugh NO → nothing: no menu, no placements, no ultimate trigger.
- **U2** Bullet 3: enemy hero with only 1 resolved card → not selectable for that bullet.
- **U3** A bullet with no legal option is not offered (S11); if none is legal the menu ends.
- **U4** Basic (silver) card: performing it via basic-action effects behaves normally.

## 11. Mind Grip
`mind_grip` (GOLD basic skill, ranged, range 5).

> "Choose one — • Perform an action on the card in the previous turn slot of
> an enemy hero in range; if you would place any tokens this way, place
> Illusion tokens instead; skip giving markers. • Defeat a minion adjacent
> to you."

- **H1** Bullet 1: enemy hero in range with a card in the previous turn slot → chooser offers the normal resolution menu for that card minus defense (primary, secondary movement, Hold, Fast Travel where legal) → chosen action performs with the card's values computed with NebKher as actor.
- **H2** Copied primary ATTACK: NebKher's attack modifiers apply; the copied card's `is_ranged`/range are used (S8).
- **H3** Copied secondary MOVEMENT: NebKher moves up to the printed secondary value (movement action semantics).
- **H4** Copied effect that places tokens → Illusion tokens placed instead, same counts/positions, from Illusion supply (S13); supply reconciliation prompts if short.
- **H5** Copied effect that gives markers → marker step skipped, subsequent steps still run.
- **H6** Enemy already resolved this turn AND enemy not yet resolved → both are valid targets (slot is by turn index).
- **H7** Bullet 2: defeat an enemy minion adjacent to NebKher → removed, coins awarded.
- **U1** Turn 1 of a round → no previous slot exists → bullet 1 has no valid target.
- **U2** Enemy passed on the previous turn (empty slot) → that hero not selectable.
- **U3** Previous-slot card is primary DEFENSE → menu offers its non-defense options (secondary movement, Hold, …) but never the defense action; the hero is still selectable (Hold always exists).
- **U4** Bullet 2 with no adjacent enemy minion → mandatory failure → abort. Friendly minions and immune (heavy) minions are not valid.
- **U5** Immune enemy hero → not selectable for bullet 1.
- **U6** Marker skip covers all marker types; token substitution covers batch/line/trail placement variants.

## 12. Ultimate — What the Hell Are You?
`what_the_hell_are_you` (PURPLE passive, radius 5).

> "Each time after you laugh diabolically as part of performing an action,
> all enemy heroes in radius discard a card, or are defeated."

- **H1** Ultimate PASSIVE + Diabolical Laughter laugh YES → immediately after the laugh, before the three choices: every enemy hero within radius 5 discards a card of their own choice.
- **H2** Enemy hero in radius with empty hand → defeated, coins awarded.
- **H3** Multiple enemy heroes in radius → ALL are hit (no actor choice; collect + for-each).
- **H4** Radius measured from NebKher's position at laugh time.
- **H5** A later performance of Diabolical Laughter in the same game triggers again ("each time").
- **U1** Ultimate not active → laugh has no extra consequence.
- **U2** Immune enemy hero → excluded (locked interp 9).
- **U3** Enemy at distance 6 → excluded; topology split blocks cross-line victims.
- **U4** Laugh declined → no trigger.

---

## Implementation ownership summary

**Critical infra (implemented by me, with the primitives' unit tests):**
P2 topology card layer, P3 after-playing-cards trigger point, P4 illusion-minion
equivalence, P5 `PerformCardActionStep` + substitution flags, P6 laugh trigger,
P7 resolved-slot swap. Card effects that are mostly these primitives: Crack in
Reality, Shift Reality, Mind Grip, Diabolical Laughter (bullet 3 + laugh),
ultimate wiring, Imbue Doubt family trigger scheduling.

**Delegable effect bodies (pure reuse/assembly):** P1 token registration,
families 5 (Fleeting Image line), 6 placement halves (equivalence effect comes
from P4), 7 (Phantasmal Sentry), 8 (Warrior/Champion), 9 (Twist Fate/Devious
Scheme), Imbue Doubt family bodies (color select + color discard once P3
lands), Diabolical Laughter bullets 1–2, ultimate effect body (collect +
for-each + discard-or-defeat once P6 lands), hero glue/registration.

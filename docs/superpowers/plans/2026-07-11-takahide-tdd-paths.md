# Takahide — TDD Test Paths (for review)

Status: **IMPLEMENTED** (2026-07-11). All 19 cards + the ultimate are live in
`src/goa2/scripts/takahide_effects.py`; every H/U path below has at least one
test (138 tests across `tests/engine/effects/cases/test_takahide_*.py` and the
four primitive suites `test_takahide_setup.py`, `test_empty_hex_obstacle.py`,
`test_swap_with_deck_card.py`, `test_facedown_masking.py`).

Deviations from this doc, decided during implementation:

- **Range/radius are topology-service distance, not obstacle pathfinding.**
  `RangeFilter` (used by every hero) resolves distance through the topology
  service, which is cube distance plus reality-split awareness — walls do not
  lengthen it. So §1 U4 is tested as "an ally beyond max range is not
  selectable", and §14 H2 as "the denied ring lengthens enemy movement PATHS"
  (pathfinding does consult obstacles), not their attack range.
- **The victim select in §8–§10 is optional** (Snorri Runetrap precedent): a
  mandatory select with no candidates aborts the whole action, which would
  contradict §8 U3. Declining the first victim also ends the picking, which is
  how Takahide picks zero victims (§10 H2).
- **No new `color_output_key`**: `SelectStep.selected_card_color_key` already
  existed and does exactly what S4 needs.
- **`Hero.initialize_state()` now marks starting-hand cards faceup.** Cards
  defaulted to `is_facedown=True`, which is only meaningful for cards in play
  areas; leaving it set made Bushido's swap deliver a facedown card into hand.

Takahide is a support samurai: 19 deck cards + ultimate. Two engines drive
his kit: **ally discard-for-benefit** (feed and reward allies' discard
piles) and a **three-gold-card cycle** (Float Like a Butterfly / Sting
Like a Bee / Strike Like a Tiger rotate through his deck; the ultimate
puts all three in hand permanently and retires the silver). Data:
`src/goa2/data/heroes/takahide.py`. Effects will live in
`src/goa2/scripts/takahide_effects.py`. Tests use `tests/engine/effects/`
helpers (`EffectScenarioBuilder` + `run_card`), marked `effect_contract` /
`effect_flow`, per repo convention.

## Locked interpretations (confirmed with user, 2026-07-11)

1. **Gold swap (Float/Sting/Strike)**: the swap happens AFTER the primary
   action completes; the incoming deck gold takes the outgoing card's
   exact place (becomes the turn card, ends faceup in the resolved slot);
   the outgoing gold goes to the deck faceup. Mandatory when a gold
   exists in the deck. Pre-ultimate exactly one gold is ever outside the
   deck; post-ultimate the deck holds zero golds and these swap texts
   permanently fizzle (intended).
2. **Facedown rule (rulebook)**: a facedown resolved/discarded card loses
   its type, color and actions until it returns to hand or is turned
   faceup; it is hidden information; turning a card facedown cancels its
   active effect. Consequences: facedown cards are never selectable as a
   color source, and their identity is masked in views for everyone
   (they render as an anonymous facedown card).
3. **Ultimate (Ready for War)**: fires once at level-8 unlock
   (`on_ultimate_unlocked`, Ursafar precedent), mid-upgrade-phase. The
   silver returns to the deck from wherever it is (hand / discard /
   resolved slot). The deck always holds exactly 2 golds at that moment,
   so both go to hand with no choice. Bushido is permanently unplayable
   afterwards. Hand size 6 needs no engine change (no cap exists).
4. **"A friendly hero" excludes Takahide** across the whole kit (standing
   GoA2 default): the discard-support family, the coin family, the
   swap-unresolved family, and the Proven Warrior color source all
   target OTHER friendly heroes only.
5. **"If that hero has a card in the discard"** is checked AFTER the
   optional discard and is satisfied by PRE-EXISTING discards — the ally
   can decline to discard and the benefit still fires if their discard
   pile is non-empty.
6. **"an attack card"** (Calculated Risk / Tactical Gambit) = a card
   whose PRIMARY action is Attack.
7. **"retrieve a discarded card"** (Pledge / Loyal Retainer) = from
   Takahide's OWN discard only.
8. **Proven Warrior family color source**: the discard of another
   friendly hero in radius — never Takahide's own.
9. **Enemy choice is blind**: Takahide picks the enemy hero(es) without
   any constraint from their hidden hand; "if able" resolves engine-side
   (no matching color in hand → no-op). "Up to two" (The Right Hand) =
   freely pick 0, 1, or 2 distinct enemies.
10. **Swap-unresolved family**: eligible targets are friendly heroes (≠
    Takahide) in radius whose current turn card is still UNRESOLVED
    (they act after him this turn). All committed cards are faceup
    during Resolution (revealed at Revelation), so the swap is fully
    public: the incoming card becomes their faceup UNRESOLVED turn card.
    The ally decides whether/what to swap. Initiative is dynamic — the
    ally acts at the new card's initiative in the engine's per-action
    re-sort (`resolve_next_action`, Hanu Hurry Up! precedent).
11. **Hold My Saké discard branch**: outgoing unresolved card lands in
    the ally's discard faceup (public, as everything already is).
12. **Spatial denial duration/tracking**: "This turn" = until end of the
    current game turn; affected hexes track Takahide's CURRENT position
    dynamically (Wasp barrier precedent). Spinning Blade = fixed
    adjacency (distance 1); Blade Helix = the card's radius stat
    (1 + RADIUS items).
13. **What the virtual obstacles block**: exactly like Wasp's barrier —
    consulted by `is_obstacle_for_actor`, so enemy movement, pushes,
    placement AND topology range/radius counting are all affected.
14. **"enemy units"** = enemy heroes AND enemy minions (any
    enemy-controlled move/push/place during the turn). End-of-round
    minion wave movement happens after expiry, unaffected.
15. **Facedown cards still occupy their zone**: a facedown card in a
    discard pile still counts for existence checks ("has a card in the
    discard") — those check presence, not type/color. (Flagged during
    review, not objected.)

## Spec decisions made by implementer (veto during review if wrong)

- **S1**: Discard-support flow & routing: Takahide picks the ally
  (mandatory SelectStep over friendly heroes in range/radius, ≠ self;
  no candidate → whole effect fizzles). The ally then gets an OPTIONAL
  hand-card select (their player decides, `override_player_id`; SKIP
  allowed). Then the condition (interp 5) gates the benefit.
- **S2**: Effect movement ("you/that hero may move up to X") =
  `SelectStep`(hex, reachable ≤ X by topology) + `MoveUnitStep`, NOT
  `MoveSequenceStep` (standing feedback: MoveSequenceStep is for primary
  MOVEMENT actions only). The MOVING hero picks the destination.
  "Ignoring obstacles" variants path with `ignore_obstacles=True`;
  destination must still be an empty hex.
- **S3**: "Attack card" filter = `primary_action == ActionType.ATTACK`
  on the ally's hand cards (interp 6).
- **S4**: Proven Warrior color choice: Takahide first picks the friendly
  hero in radius, then picks a FACEUP card in that hero's discard; the
  chosen card's color (GOLD/SILVER included) is the forced color.
  Facedown discards are excluded from selection (interp 2).
- **S5**: Enemy discard resolution = `ForceDiscardByColorStep` (victim
  chooses which matching card to discard; hand-only; no match → no-op).
  The Right Hand: two sequential optional enemy selections (distinct
  victims, SKIP allowed at each, 0–2 total), each followed by the
  forced discard. Immune enemy heroes are excluded from selection
  (Snorri S7 precedent — a forced discard is an enemy action).
- **S6**: Swap-unresolved flow: Takahide picks the ally
  (`HasUnresolvedCardFilter` + radius + friendly ≠ self; optional —
  "may" scopes the whole rider, so SKIP at hero selection is allowed
  too); then the ALLY picks a card from their hand (Hold My Saké: hand
  or faceup discard) or declines. Swap via `SwapCardStep` semantics
  (state/facedown/played_this_round swap; both cards' active effects
  expire). The incoming card is UNRESOLVED + faceup.
- **S7**: "After the attack:" riders fire regardless of attack outcome
  (defended/target survived), per existing convention. No adjacent
  target → mandatory targeting fails → action aborts, riders skipped.
- **S8**: Spatial denial = new `EMPTY_HEX_OBSTACLE` `ActiveEffect`
  created via `CreateEffectStep` (scope RADIUS around Takahide,
  `affects=ENEMY_UNITS`, `THIS_TURN`), activated at
  `FinalizeHeroTurnStep` like all card effects, expired at end of turn.
  Consulted inside `is_obstacle_for_actor`: if the ACTING/MOVING unit is
  an enemy of the source and the hex is EMPTY and within radius of the
  source's current position → obstacle. Spinning Blade radius literal 1;
  Blade Helix radius from `stats.radius` (item-boostable).
- **S9**: Gold swap step: new `SwapWithDeckCardStep` (or an extension of
  `SwapCardStep` — decided at implementation): finds the outgoing card
  (hand / discard / resolved slot / current turn card), swaps it with a
  chosen DECK card; outgoing card → `state=DECK`, faceup; incoming card
  inherits the outgoing card's zone/state/slot. Bushido rider: if the
  outgoing card was in a resolved slot or the discard, the incoming card
  is placed FACEDOWN there (and, per the rulebook, turning facedown
  cancels active effects — moot for golds, asserted anyway). Takahide's
  player picks the deck gold when 2 are available.
- **S10**: Gold-swap timing on Float/Sting/Strike: the swap step is
  pushed after the primary-action steps; for Sting/Strike it sits with
  the after-attack riders. The incoming gold becomes
  `current_turn_card` and is finalized into the turn slot as RESOLVED
  faceup by `FinalizeHeroTurnStep`.
- **S11**: Bushido: "your gold card" is located automatically (exactly
  one gold outside the deck pre-ultimate — hand, discard, or resolved
  slot; never the turn card, which is Bushido itself). No selection
  prompt for the outgoing card; only the incoming deck gold is chosen.
  Skill is mandatory; deck always has a gold pre-ultimate.
- **S12**: `Card.starts_in_deck: bool = False` field, honored by
  `Hero.initialize_state()` (UNTIERED/Tier I cards with the flag stay in
  the deck). Set on Sting Like a Bee and Strike Like a Tiger. Starting
  hand = Float, Bushido, 3 Tier I = 5 cards.
- **S13**: Facedown discard/resolved masking in `build_view()`: a
  facedown card outside the owner's hand renders masked for ALL viewers
  including the owner's client (same masking shape as opponents'
  facedown committed cards). Client integration guide updated.
- **S14**: Sting Like a Bee "at maximum range" =
  `RangeFilter(min_range == max_range == effective range)` (base 3 +
  range items), topology distance (Snorri S2 precedent).
- **S15**: Retrieve on Pledge/Loyal Retainer may target a FACEDOWN card
  in Takahide's own discard (existence-based zone change; the card turns
  faceup on returning to hand via `return_card_to_hand`).
- **S16**: Ready for War implementation: `on_ultimate_unlocked` returns
  the silver to deck via `Hero.return_card_to_deck` (removing it from
  hand / discard / resolved slot, wherever it is) and moves both
  DECK-state golds to hand (`return_card_to_hand`-equivalent state
  change). Emits public `GameEvent`s for both movements.
- **S17**: Coins: "both you and that hero gain 1/2 coin(s)" =
  `GainCoinsStep` × 2 (Takahide and the ally), fired only when the
  interp-5 condition holds — the coins and the retrieve share the same
  gate.

## New engine primitives (each gets its own unit tests)

| # | Primitive | Where |
|---|-----------|-------|
| P1 | `Card.starts_in_deck` flag + `Hero.initialize_state()` honoring it | `domain/models/card.py`, `domain/models/unit.py` |
| P2 | Deck-swap step (`SwapWithDeckCardStep` or extended `SwapCardStep`): non-deck card ↔ deck card, zone inheritance, Bushido facedown rider, effect expiry | `engine/steps/cards.py` (+ `domain/models/unit.py` if `swap_cards` learns deck) |
| P3 | Facedown-outside-hand masking in views (+ excluded from card-select enumerations that read color/type) | `domain/views.py`, `engine/steps/selection.py`, `docs/CLIENT_INTEGRATION_GUIDE.md` |
| P4 | `EMPTY_HEX_OBSTACLE` `EffectType` + `is_obstacle_for_actor` integration (enemy-of-source actors incl. minions, empty hexes only, dynamic origin, radius payload) | `domain/models/effect.py`, `engine/validation_terrain.py` |
| P5 | Ready for War one-shot (silver → deck from any zone; deck golds → hand) | `scripts/takahide_effects.py` via `on_ultimate_unlocked` |

Everything else is effect-body assembly from existing primitives
(`SelectStep` with card containers/filters, `DiscardCardStep`,
`ForceDiscardByColorStep`, `RetrieveCardStep`, `SwapCardStep`,
`GainCoinsStep`, `MoveUnitStep`, `AttackSequenceStep`,
`CreateEffectStep`, `HasUnresolvedCardFilter`).

---

# Per-card test paths

Notation: **H** = happy path, **U** = unhappy/edge path. Range/radius
checks always use topology distance, measured from Takahide. Offensive
targeting includes `ImmunityFilter` unless stated. "Ally" always means a
friendly hero other than Takahide.

## 1. Come to Aid (I, GREEN, init 4, SKILL, ranged 3)

> "A friendly hero in range may discard a card. If that hero has a card
> in the discard, you may move up to 3 spaces."

- **H1** Ally in range 3 → Takahide picks them → ally picks a hand card → it lands in their discard → Takahide gets an optional move up to 3 (S2) → moves.
- **H2** Ally DECLINES the discard but already has a card in the discard (interp 5) → Takahide still gets the move.
- **H3** Move is optional → Takahide may SKIP it; may also move fewer than 3 spaces.
- **H4** Discard choice routes to the ALLY's player, not Takahide's (S1).
- **U1** No ally in range → effect fizzles entirely (no prompts).
- **U2** Ally declines AND their discard is empty → no move.
- **U3** Ally has an empty hand and empty discard → selectable, but no discard prompt fires and no move.
- **U4** Range 3 is topology: an ally 3 hexes away around an obstacle wall (path length > 3) is NOT selectable.
- **U5** Takahide himself is never a selectable "friendly hero" (interp 4).

## 2. Bring the Relief (II, GREEN, init 3, SKILL, ranged 4)

Same as Come to Aid with range 4 / move up to 4. Regression paths only:

- **H1** Full happy flow at range 4, move 4.
- **U1** Move destinations beyond 4 path-steps not offered.

## 3. Commit Reserves (III, GREEN, init 3, SKILL, ranged 4)

Adds "ignoring obstacles" to the move.

- **H1** Full flow; Takahide's move paths THROUGH an obstacle hex (path only legal with `ignore_obstacles`) → allowed.
- **U1** Destination itself must be empty — an obstacle/occupied hex is not offered as a landing spot.
- **U2** Without the condition met (decline + empty discard) → no move.

## 4. Pledge of Allegiance (II, GREEN, init 3, SKILL, ranged 4)

> "A friendly hero in range may discard a card. If that hero has a card
> in the discard, both you and that hero gain 1 coin and you may
> retrieve a discarded card."

- **H1** Ally discards → both Takahide and the ally gain 1 coin (S17) → Takahide gets an optional retrieve from his OWN discard (interp 7) → chosen card returns to his hand.
- **H2** Ally declines but has a pre-existing discard → coins + retrieve still fire (interp 5).
- **H3** Retrieve declined → coins only.
- **H4** Takahide's discard contains a facedown card (from Bushido) → it IS retrievable (S15) and turns faceup in hand.
- **U1** Condition not met → no coins, no retrieve.
- **U2** Takahide's own discard empty → coins fire, no retrieve prompt.
- **U3** The ally's just-discarded card is NOT offered for retrieval (it is in the ally's discard, not Takahide's).

## 5. Loyal Retainer (III, GREEN, init 3, SKILL, ranged 4)

Same as Pledge with 2 coins each. Regression paths only:

- **H1** Full happy flow → +2 coins each + retrieve.

## 6. Calculated Risk (II, BLUE, init 10, SKILL, radius 4)

> "A friendly hero in radius may discard an attack card. If that hero
> has a card in the discard, that hero may move up to 2 spaces."

- **H1** Ally in radius 4 with an attack-primary card in hand → discards it → ally gets an optional move up to 2 (destination chosen by the ALLY, S2).
- **H2** Ally declines the discard but has a pre-existing discard (of ANY card, not necessarily an attack card) → ally still gets the move (interp 5).
- **H3** The discard select only offers cards with `primary_action == ATTACK` (S3) — a card with only a secondary attack value is NOT offered.
- **U1** Ally has no attack-primary card in hand and an empty discard → selectable, no discard possible, no move.
- **U2** Ally declines the move → nothing (both "may"s independent).
- **U3** No ally in radius → fizzle.

## 7. Tactical Gambit (III, BLUE, init 10, SKILL, radius 4)

Adds "ignoring obstacles" to the ally's move.

- **H1** Ally's 2-space move paths through an obstacle → allowed; lands on an empty hex.
- **U1** Occupied/obstacle destination not offered.

## 8. Proven Warrior (I, BLUE, init 9, SKILL, radius 3)

> "Choose a card in the discard of a friendly hero in radius. An enemy
> hero in radius discards a card of the same color, if able."

- **H1** Ally in radius 3 with a RED card in discard → Takahide picks that card → picks an enemy hero in radius 3 → that enemy discards a RED card from hand (their choice among matching, S5).
- **H2** Color source may be GOLD or SILVER (basics land in discards constantly) → enemy forced to discard their gold/silver.
- **H3** Enemy with multiple matching cards chooses which one to discard.
- **U1** Chosen enemy has no card of that color in hand → no-op ("if able"); the choice was blind (interp 9) and is spent.
- **U2** No friendly hero in radius, or all their discards empty → effect fizzles.
- **U3** No enemy hero in radius → color chosen but nothing happens.
- **U4** Takahide's own discard is NOT offered (interp 8 / interp 4).
- **U5** A FACEDOWN card in the ally's discard is not selectable as color source (interp 2 / S4).
- **U6** Immune enemy heroes excluded from victim selection (S5).
- **U7** Enemy's committed/resolved cards of the color don't count — hand only (S5).

## 9. Chosen Champion (II, BLUE, init 10, SKILL, radius 4)

Same as Proven Warrior at radius 4. Regression paths only:

- **H1** Full happy flow at radius 4.

## 10. The Right Hand (III, BLUE, init 10, SKILL, radius 4)

> "Choose a card in the discard of a friendly hero in radius. Up to two
> enemy heroes in radius discard a card of the same color, if able."

Inherits Proven Warrior paths, plus:

- **H1** Two enemy heroes in radius → both selected sequentially → each discards a matching card independently.
- **H2** Takahide freely picks 0, 1, or 2 victims (interp 9) — picking just one of two available is legal; SKIP at either selection.
- **U1** The same enemy cannot be picked twice (distinct victims, S5).
- **U2** One victim has the color, the other doesn't → first discards, second no-ops.

## 11. Set an Example (I, RED, init 11, ATK 2, radius 3)

> "Target a unit adjacent to you. After the attack: A friendly hero in
> radius may swap their unresolved card with a card in their hand."

- **H1** Adjacent attack resolves → ally in radius 3 with an UNRESOLVED turn card → Takahide picks them → the ALLY picks a hand card → swap: hand card becomes their faceup UNRESOLVED turn card; old turn card goes to hand (S6, interp 10).
- **H2** Initiative is dynamic: ally swaps in a HIGHER-initiative card than any remaining actor → they act next; swaps in a lower one → they act later (interp 10).
- **H3** Rider fires even if the attack was defended/blocked (S7).
- **H4** The ally may decline (SKIP at either the hero pick by Takahide or the card pick by the ally).
- **U1** No adjacent unit → mandatory targeting fails → action aborts → no rider (S7).
- **U2** No ally in radius with an unresolved card (all already acted) → rider fizzles.
- **U3** Ally with an unresolved card but EMPTY hand → not a useful target; card select offers nothing → no swap.
- **U4** Heroes who already resolved this turn are not eligible (`HasUnresolvedCardFilter`).
- **U5** Takahide himself is never eligible (interp 4; he has no unresolved card mid-action anyway).

## 12. Lead from the Front (II, RED, init 11, ATK 3, radius 4)

Same as Set an Example at radius 4 / ATK 3. Regression paths only:

- **H1** Full happy flow at radius 4.

## 13. Hold My Saké (III, RED, init 12, ATK 3, radius 4)

> "…may swap their unresolved card with a card in their hand, or in
> their discard."

Inherits Set an Example paths, plus:

- **H1** Ally swaps their unresolved card with a card from their DISCARD → discard card becomes their faceup UNRESOLVED turn card; the old turn card lands in the discard faceup (interp 11).
- **H2** The select offers BOTH containers (hand + discard) in one choice.
- **U1** Empty hand AND empty discard → no swap possible.
- **U2** A facedown card in the ally's discard is not offered (interp 2).

## 14. Spinning Blade (II, RED, init 11, ATK 3)

> "Target a unit adjacent to you. After the attack: This turn: Empty
> spaces adjacent to you count as obstacles for enemy units."

- **H1** After the attack + turn finalization, an enemy hero acting later this turn cannot move INTO or THROUGH an empty hex adjacent to Takahide (S8).
- **H2** Enemy topology range is affected: an enemy whose only ≤N path to a target runs through the denied hexes finds it out of range (interp 13).
- **H3** Enemy MINION movement (e.g. moved by an enemy card this turn) is blocked the same way (interp 14).
- **H4** Friendly units path through those hexes freely.
- **H5** Dynamic origin: Takahide is pushed 2 hexes by a later enemy action this turn → the denied ring follows his new position (interp 12).
- **H6** OCCUPIED hexes adjacent to Takahide are unaffected by the effect (it only applies to empty ones — they're blocked by occupancy anyway; a hex vacated later this turn becomes denied).
- **H7** Rider fires even if the attack was defended (S7).
- **U1** Effect expires at end of turn: next turn enemies path through freely.
- **U2** No adjacent target → abort → no effect created.
- **U3** Enemy pushes/placements into the denied hexes are blocked (displacement counts, interp 13).

## 15. Blade Helix (III, RED, init 12, ATK 3, radius 1)

Same as Spinning Blade but "empty spaces in radius" (base 1).

- **H1** Full flow at radius 1 (≡ adjacent).
- **H2** With +1 RADIUS item equipped → denied area extends to radius 2 (S8: `stats.radius`).

## 16. Bushido (SILVER, init 5, SKILL, DEF 6)

> "Swap your gold card with a different gold card in your deck; if you
> swap a resolved or discarded card this way, place the new card
> facedown."

- **H1** Gold in HAND (e.g. Float unplayed) → Takahide picks one of the 2 deck golds → chosen gold arrives in hand FACEUP; outgoing gold to deck faceup (S9, S11).
- **H2** Gold in a RESOLVED slot (played earlier this round) → incoming gold lands in that exact slot FACEDOWN; outgoing to deck.
- **H3** Gold in DISCARD (e.g. discarded for defense) → incoming gold lands in the discard FACEDOWN.
- **H4** Facedown card masking: opponents' views (and all clients) show an anonymous facedown card in the discard/slot (P3, interp 2).
- **H5** At end of round, the facedown card returns to hand and turns faceup (`retrieve_cards`). (Facedown state can never persist across rounds, and Bushido plays once per round — so a facedown card is never itself a swap source.)
- **H6** The outgoing card's zone is found automatically — no prompt for it (S11); only the deck gold is chosen (2 options).
- **U1** Post-ultimate: Bushido is in the DECK and can never be played (interp 3) — asserted via ultimate tests (#20), no direct path here.
- **U2** The swap is mandatory (skill text has no "may"): the only choice is WHICH deck gold.

## 17. Float Like a Butterfly (GOLD, init 8, MOVE 5, DEF 8)

> "Swap this card with a different gold card in your deck.
> (This card starts the game in your hand.)"

- **H1** Starts the game in hand; Sting/Strike start in deck (S12/P1); starting hand = 5 (Float, Bushido, 3 Tier I).
- **H2** Play Float → move up to 5 (primary) → afterwards the swap fires (S10): Float goes to deck faceup; the chosen deck gold becomes the turn card and finalizes RESOLVED faceup in Float's turn slot.
- **H3** Take the movement as 0 spaces → swap still fires (mandatory, interp 1).
- **H4** At end of round the swapped-in gold returns to hand → hand now cycles a different gold.
- **U1** Post-ultimate (no golds in deck) → swap fizzles silently; Float just resolves in place (interp 1).
- **U2** The swap only offers GOLD deck cards — never tier II/III upgrades or the returned silver.

## 18. Sting Like a Bee (GOLD, init 7, ATK 5, ranged 3)

> "Target a unit at maximum range. After the attack: Swap this card with
> a different gold card in your deck. (Starts in deck.)"

- **H1** Starts the game in the deck (S12).
- **H2** (Once in hand via a swap) target must be at EXACTLY effective max range (3 + range items), topology (S14); nearer units not targetable.
- **H3** After the attack → swap fires; Sting returns to deck.
- **H4** Rider fires even if the attack was defended (S7).
- **U1** No unit at exactly max range → mandatory targeting fails → abort → NO swap (rider skipped, S7).
- **U2** Post-ultimate → swap fizzles; Sting stays.

## 19. Strike Like a Tiger (GOLD, init 9, ATK 7)

> "Target a unit adjacent to you. After the attack: Swap this card with
> a different gold card in your deck. (Starts in deck.)"

- **H1** Starts the game in the deck (S12).
- **H2** Adjacent attack for 7 → swap fires after.
- **U1** No adjacent target → abort → no swap.

## 20. Ready for War (ultimate, one-shot at level 8)

> "Return your silver card to your deck and take two gold cards from
> your deck into your hand. (You now have a total hand size of 6 cards.)"

- **H1** Level 8 reached with Bushido in HAND → Bushido → deck; both deck golds → hand; hand ends at 6 (3 golds + 3 tier III) (S16, interp 3).
- **H2** Bushido in DISCARD at unlock (was discarded this round) → still returned to deck.
- **H3** Bushido in a RESOLVED slot at unlock (played this round) → returned to deck; its slot is emptied (None).
- **H4** Both DECK-state golds move to hand regardless of WHICH two they are (the set varies with prior swaps) — no player choice.
- **H5** Public `GameEvent`s emitted for the silver return and the gold draws (S16).
- **H6** End-of-round retrieve afterwards → Bushido stays in the deck (DECK state untouched by `retrieve_cards`); hand stays 6 across rounds.
- **H7** Post-ultimate gold-swap fizzle (interp 1) asserted here end-to-end: play Float after the ultimate → no swap prompt, Float resolves normally.
- **U1** Fires exactly once — reaching level 8 does not re-trigger later; no steps run at levels < 8.

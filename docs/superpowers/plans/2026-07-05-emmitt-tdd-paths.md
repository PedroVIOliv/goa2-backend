# Emmitt — TDD Test Paths (for review)

Status: **PENDING REVIEW** — do not implement until approved.

Emmitt is a time-manipulation hero: 17 cards + ultimate, 13 unique effects.
Data: `src/goa2/data/heroes/emmitt.py`. Effects will live in
`src/goa2/scripts/emmitt_effects.py`. Tests use `tests/engine/effects/` helpers
(`EffectScenarioBuilder` + `run_card`), marked `effect_contract` / `effect_flow`,
per repo convention.

## Locked interpretations (confirmed with user, 2026-07-05)

1. **Temporal line**: defender blocks with fully **computed** Initiative
   (card base + items + modifiers) instead of Defense; minion defense
   modifiers apply as normal on top.
2. **Position snapshot**: taken once per turn, **just before Planning**
   (equivalently: end of previous turn; initial setup counts as the first
   snapshot). "Remained in the same space since the last turn" is the literal
   check `current tile == snapshot tile` — leaving and returning within the
   turn still counts as "remained"; being displaced by others counts as moved.
3. **Time Walk / Fast Forward**: the forced move is **exactly 2** straight-line
   spaces; if no legal exactly-2 path exists, that hero is an invalid target.
   On turn 1 of a round the snapshot reaches into the previous round.
4. **Back to the Future A**: excludes self; any non-immune unit; if the
   snapshot space is occupied the unit is still selectable but the place
   fails (mandatory → action aborts).
5. **Time Capsule / Future Proof A**: each hero retrieves only their **own**
   cards discarded this turn; **all-or-nothing** per hero; **each hero
   decides** for themselves (prompt routed to them); defense-reaction
   discards count.
6. **Future Proof B**: **aura** — radius measured from Emmitt's current
   space at check time (heroes entering later gain immunity, leaving lose
   it); excludes Emmitt himself.
7. **Glitch tokens**: supply **3**; spacing "at least two spaces between" =
   two **empty spaces in between** = pairwise hex distance **≥ 3**;
   placement is **all-or-nothing** (if all N cannot legally fit, the
   placement option is unavailable / the mandatory placement fizzles).
   Emmitt picks which enemy hero (or none where "up to 1"); that hero picks
   the token.
8. **Unstable Timeline**: Emmitt picks **which** enemy hero chooses the
   token. As defense: text resolves before the defense total is calculated;
   the attack still resolves against Emmitt (at his new location) with
   defense 6. If tokens can't be placed, the text stops but the defense
   value 6 still counts.
9. **Reverse Time**: NEXT_TURN global inversion — ascending **computed**
   initiative, ties as normal; **fizzles at the round boundary** (no effect
   if played on the last turn of a round); ignores immunity (global rule,
   no targeting, so no immunity check anywhere).
10. **Time Warp B**: target needs an unresolved card AND ≥ 1 resolved card;
    the enemy picks which resolved card to swap in; the swapped-out card
    sits in the resolved area without ever resolving; initiative order
    self-corrects (recomputed after every action).
11. **Alternative Timelines**: standard ultimate activation (level ≥ 8,
    PASSIVE). Planning: commit one card, then **optionally add a second
    before planning closes** (explicit done-signal; server contract
    change). Both cards are publicly revealed; the retrieve-one choice is
    **mandatory** and happens immediately after reveal, before any hero
    resolves.

## Spec decisions made by implementer (veto during review if wrong)

- **S1**: Glitch spacing is checked pairwise **within the batch being
  placed** only (pre-existing Glitch tokens on the board — possible when
  Unstable Timeline was used as a defense earlier in the same turn — do not
  constrain the new batch, but their hexes are occupied and thus unplaceable).
- **S2**: Units with no snapshot entry (spawned/respawned this turn) are
  **excluded from targeting** for Time Walk/Fast Forward ("remained" is
  false) and for Back to the Future A (no defined start-of-turn space).
- **S3** (corrected by user): Reverse Time's inversion is a card effect and
  **deactivates if Emmitt is defeated** — this is the engine's default
  behavior for card-bound effects; the test asserts the default applies.
- **S4**: Time Capsule prompts are only shown to heroes that actually have
  ≥ 1 own card discarded this turn (no empty YES/NO prompts).
- **S5**: The `defense_uses_initiative` flag is scoped to the single attack
  sequence that set it (cleaned up with the attack context) — it never leaks
  into other attacks, repeats, or other heroes' turns.
- **S6**: For Flashback/Déjà Vu the "up to 1 enemy hero swaps" rider only
  fires when **all N** tokens were placed ("if you do").
- **S7**: Ultimate planning flow: after Emmitt's first commit, planning does
  not close on his account until he either commits a second card or sends an
  explicit `DONE` signal (new server/session affordance). With 1 card in
  hand, first commit auto-closes (no second card possible).

## New engine primitives (each gets its own unit tests)

| # | Primitive | Where |
|---|-----------|-------|
| P1 | `HasResolvedCardFilter` (inverse of Hanu's `HasUnresolvedCardFilter`; index logic from `PlayedCardFilter`) | `engine/filters_cards.py` + new `FilterType` |
| P2 | `defense_uses_initiative` context flag consumed by `ReactionWindowStep` (value + option labels) | `engine/steps/reactions.py` |
| P3 | Position snapshot: `state.last_turn_positions: dict[str, Hex]`, recorded just before PLANNING (and at game creation) | `domain/state.py`, `engine/phases.py` |
| P4 | Turn discard log: `state.turn_discard_log: list[{hero_id, card_id}]`, appended in `DiscardCardStep`, cleared in `end_turn` | `domain/state.py`, `engine/steps/cards.py`, `engine/phases.py` |
| P5 | Card swap: REUSE existing `SwapCardStep` (`engine/steps/cards.py`) — `Hero.swap_cards` already swaps location + state + facedown + `played_this_round`; precedent: `rogue_skill_gold`. Only additions: `HasResolvedCardFilter` (P1-style) and `override_player_id_key` so the ENEMY picks the resolved card | no new step |
| P6 | `EffectType.REVERSED_INITIATIVE` + ascending sort in `resolve_next_action`; NEXT_TURN round-boundary fizzle | `domain/models/effect.py`, `engine/phases.py` |
| P7 | Aura immunity: `is_immune()` evaluates RADIUS-scoped `IMMUNITY_ENEMY_ACTIONS` (origin = Emmitt, affects FRIENDLY_HEROES) in addition to the existing per-unit `source_id` form | `engine/rules.py` |
| P8 | `TokenType.GLITCH`, supply 3 | `domain/models/enums.py`, `token.py` |
| P9 | Two-card planning commit + post-reveal retrieve step for the ultimate | `engine/phases.py`, `engine/session.py`, server routes |
| P10 | Glitch batch placement with feasibility precheck (all-or-nothing, pairwise dist ≥ 3) | effect-side helper or small step |

P3/P4 are new `GameState` fields → must round-trip persistence
(`engine/persistence.py` save/load test).

---

# Per-card test paths

Notation: **H** = happy path, **U** = unhappy/edge path. Range checks always
use topology distance. All offensive targeting includes `ImmunityFilter`
unless stated.

## 1. Temporal Punch / Temporal Slam / Temporal Judgment
`temporal_punch` (ATK 9) / `temporal_slam` (ATK 11) / `temporal_judgment` (ATK 12) — one effect class, shared tests parameterized by card.

> "Target a unit adjacent to you; when defending, the enemy hero must use the
> Initiative value of their card and items instead of the Defense value."

- **H1** Attack adjacent enemy hero; defender plays a card with initiative ≥ attack (after minion modifiers) → blocked.
- **H2** Defender plays a card with high Defense but low Initiative → defeated (proves initiative is used, not defense).
- **H3** Minion defense modifiers apply: initiative + friendly-minion modifier ≥ attack → blocked.
- **H4** Computed initiative: an active initiative modifier on the defender changes the block value.
- **H5** Reaction option labels show the initiative-based value (client contract: the defender sees what they'd block with).
- **U1** Defender passes → defeated (normal flow unchanged).
- **U2** Target is a minion → no reaction window; normal minion combat, unchanged.
- **U3** No adjacent enemy unit → mandatory targeting fails → action aborts.
- **U4** Flag scoping (S5): a later attack in the same turn (repeat/passive) and other heroes' attacks use normal Defense.

## 2. Time Snare / Time Trap
`time_snare` (range 2) / `time_trap` (range 3) — one effect class.

> "An enemy hero in range who has already resolved a card this turn discards a card, if able."

- **H1** Enemy hero in range with a resolved card this turn → they choose and discard a card from hand.
- **H2** Two valid targets → Emmitt chooses which.
- **U1** Enemy in range whose card is still unresolved → not targetable; if no enemy qualifies → mandatory select fails → abort.
- **U2** Enemy resolved but out of topology range → invalid.
- **U3** Victim's hand is empty → "if able": no discard, no penalty, action completes.
- **U4** Enemy who passed this turn (no card) → not a valid target.
- **U5** Immune enemy hero → excluded.

## 3. Time Bomb
`time_bomb` (range 3).

> "…discards a card, or is defeated."

- **H1** Victim with cards → forced discard (their choice).
- **H2** Victim with empty hand → defeated, coins awarded.
- **U1–U3** Same targeting paths as Time Snare (unresolved not targetable / out of range / passed).

## 4. Time Loop
`time_loop` (range 4).

> "Swap with an enemy hero in range who has already resolved a card this turn."

- **H1** Swap with valid target → both positions exchanged, `UNITS_SWAPPED` (or equivalent) event emitted.
- **U1** No enemy in range has resolved → abort.
- **U2** Swap-prevention effect on the target (displacement validation) → swap denied → mandatory → abort.
- **U3** Immune enemy excluded.

## 5. Time Warp
`time_warp` (range 4) — Choose one: (A) = Time Loop swap; (B) card swap.

- **H1** Bullet A behaves exactly like Time Loop (inheritance test).
- **H2** Bullet B: enemy in range with unresolved card + ≥1 resolved card; **that enemy** picks one of their resolved cards; cards swap — the old resolved card becomes their `current_turn_card` (UNRESOLVED, face-up), the previously unresolved card sits in that played slot as RESOLVED.
- **H3** After the swap the resolution order reflects the swapped-in card's initiative (enemy acts earlier/later accordingly).
- **H4** The enemy still acts this turn and resolves the swapped-in card's action.
- **U1** Enemy with unresolved card but 0 resolved cards → not targetable for B.
- **U2** Bullet B chosen with no valid target → mandatory select fails → abort (consistent with existing choose-one branches).
- **U3** The swapped-out card never resolves its action (no steps fire from it).

## 6. Time Walk / Fast Forward
`time_walk` (range 3) / `fast_forward` (range 4) — one effect class.

> "Move an enemy hero in range, who remained in the same space since the last turn, 2 spaces in a straight line."

- **H1** Enemy hero whose current tile == pre-planning snapshot tile → Emmitt moves them exactly 2 in a straight line (Emmitt picks the destination; path must be passable — forced movement, not through obstacles/units; `is_movement_action=False`).
- **H2** Enemy left and returned to the same tile within this turn → still valid (literal snapshot comparison).
- **H3** Turn 1 of round 2: snapshot from the last turn of round 1 is used.
- **U1** Enemy moved this turn (tile differs from snapshot) → invalid target.
- **U2** Enemy displaced by another effect (push/swap) → invalid target.
- **U3** No exactly-2 straight-line destination (all lines blocked at distance 1 or 2) → that hero is invalid; if none valid → abort.
- **U4** Hero respawned this turn (no snapshot entry / off-board at snapshot) → invalid (S2).
- **U5** Forced-movement protection (`ForcedMovementByEnemyFilter`) respected.
- **U6** Immune enemy excluded.

## 7. Back to the Future
`back_to_the_future` (range 4) — Choose one: (A) place unit to snapshot space; (B) = Fast Forward.

- **H1** Bullet A: unit in range that moved this turn → placed into its pre-planning snapshot space (empty) — works for enemy hero, friendly hero, and minion.
- **H2** Bullet B inherits all Fast Forward tests (inheritance test only).
- **U1** Snapshot space occupied (by anyone, including the unit itself if it never moved) → unit selectable, place fails → mandatory → abort.
- **U2** Emmitt himself not selectable.
- **U3** Immune units excluded.
- **U4** Unit spawned this turn (no snapshot entry) → excluded from targeting (S2).

## 8. Time Capsule
`time_capsule` (radius 4).

> "You, and friendly heroes in radius, may retrieve all cards discarded this turn."

- **H1** Emmitt discarded a card earlier this turn (e.g. as a defense reaction) → prompted; YES → all his this-turn discards return to hand.
- **H2** Friendly hero in radius with 2 cards discarded this turn → prompted (routed to **their** player); YES → both return; the decision is theirs, not Emmitt's.
- **H3** Emmitt is always eligible regardless of radius ("You, and…").
- **H4** A card discarded from the played area this turn also returns to hand.
- **U1** Friendly hero outside radius → not prompted, cards stay discarded.
- **U2** Hero with no this-turn discards → not prompted (S4).
- **U3** All-or-nothing: NO → nothing returns (no partial option exists).
- **U4** Cards discarded in previous turns stay in the discard pile.
- **U5** Enemy heroes never prompted / unaffected.
- **U6** Turn boundary: log cleared at end of turn (a discard from last turn is not retrievable even if the pile is otherwise identical).

## 9. Future Proof
`future_proof` (radius 4) — Choose one: (A) = Time Capsule; (B) aura immunity.

- **H1** Bullet A inherits Time Capsule tests.
- **H2** Bullet B: friendly hero inside radius → enemy attack/skill cannot target them this turn.
- **H3** Aura semantics: friendly hero enters the radius after resolution → immune; leaves the radius (e.g. pushed out) → loses immunity; Emmitt is displaced → radius follows him.
- **H4** Expires at end of turn (targetable next turn).
- **U1** Emmitt himself is NOT immune.
- **U2** Friendly minions not covered (heroes only).
- **U3** Friendly actions still work on the immune heroes (enemy-actions immunity only).
- **U4** Backward compat: existing per-unit `source_id` immunity (Whisper Death Seeker, Hanu Journey) still works after the `is_immune` extension.

## 10. Flashback / Déjà Vu
`flashback` (ATK 5, 3 tokens, radius 3) / `deja_vu` (ATK 6, 2 tokens, radius 3) — one effect class parameterized by token count.

> "Target a unit adjacent to you. After the attack: You may place N Glitch tokens in radius, with at least two spaces between each token; if you do, up to 1 enemy hero in radius swaps with a Glitch token of their choice. End of turn: Remove all Glitch tokens."

- **H1** Attack adjacent unit resolves fully first (reaction, combat).
- **H2** Player opts in → places all N tokens in radius (measured from Emmitt's post-attack position), each placement hex empty, pairwise distance ≥ 3 within the batch.
- **H3** All N placed → Emmitt may pick 1 enemy hero in radius; **that hero's player** picks which Glitch token; hero and token swap positions.
- **H4** "Up to 1": Emmitt may skip the swap after placing.
- **H5** End of turn: all Glitch tokens auto-removed (THIS_TURN effect finishing steps through the real `end_turn`).
- **U1** Attack aborts (no adjacent unit) → whole action aborts, no tokens.
- **U2** Player declines placement → no tokens, no swap offer.
- **U3** Board cannot fit all N with spacing → placement option unavailable (all-or-nothing precheck, P10) → no swap.
- **U4** Enemy hero outside radius → not selectable for the swap.
- **U5** Immune enemy hero → excluded from the swap.
- **U6** Tokens are obstacles while on board (block movement through/placement onto).
- **U7** Supply interplay: Glitch tokens already on board from Unstable Timeline used as defense earlier this turn → `PlaceTokenStep` overflow kicks in (remove-and-replace), batch spacing checked within the new batch only (S1).
- **U7b** Overflow must remove a **pre-existing** token, never a batch member: supply 3, 1 Glitch already on board, place a batch of 3 → tokens 1 and 2 come from supply; the 3rd triggers overflow and the removal MUST target the pre-existing token (batch-placed token ids are excluded from the overflow selection — with one legal candidate it auto-resolves). Generalizes: with 3 pre-existing and a batch of 2, both removals hit pre-existing tokens only.
- **U8** Swap rider requires "if you do": impossible to reach the swap without all N placed (guarded by U3's precheck).

## 11. Unstable Timeline
`unstable_timeline` (SILVER, DEFENSE_SKILL 6, radius 4; skill: 2 tokens, defense: 3 tokens).

> "Place 2 Glitch tokens in radius (…); if used as a defense, place 3 tokens instead. An enemy hero in play chooses one of the Glitch tokens; you swap with that token. End of turn: Remove all Glitch tokens."

Skill mode:
- **H1** Mandatory placement of 2 tokens (spacing ≥ 3); Emmitt picks an enemy hero **in play** (no range limit); that hero's player picks a token; **Emmitt** swaps with it (mandatory, no range limit on the swap).

Defense mode:
- **H2** Used as a reaction: defense text resolves **before** the combat total — 3 tokens placed, enemy hero chooses, Emmitt swaps — then combat resolves vs defense 6 (+ minion modifiers) with Emmitt at his new location; attack ≤ total → blocked, else defeated.
- **H3** Tokens placed during an enemy's turn are removed at the end of **that** turn.

Both modes:
- **U1** Required tokens cannot all be placed (spacing/space) → text stops: no choice, no swap; in defense mode the defense value 6 still counts toward the block.
- **U2** No enemy hero in play → chooser selection fails → stop before swap (tokens remain until end of turn).
- **U3** The enemy's token choice is adversarial: routed to the chosen enemy's player via input request (client contract check).
- **U4** End-of-turn removal fires in both modes.

## 12. Reverse Time
`reverse_time` (GOLD, ATK 4).

> "Target a unit adjacent to you. After the attack: Next turn: Heroes with lower initiative act before heroes with higher initiative; this effect ignores immunity."

- **H1** Attack resolves; next turn, resolution order is ascending computed initiative (lowest first).
- **H2** Computed: items/modifiers included in the inverted comparison.
- **H3** Ties next turn resolve through the normal tie-breaker flow.
- **H4** The turn after next is back to normal descending order.
- **H5** Heroes immune to enemy actions are still re-ordered (global rule — verified by absence of any immunity gate).
- **U1** Attack aborts (no adjacent unit) → no effect created (mandatory-step rule).
- **U2** Played on the last turn of a round → fizzles: turn 1 of the next round is normal order.
- **U3** Emmitt defeated before/during next turn → inversion does NOT apply (card effects deactivate on their hero's defeat — default engine behavior, S3).

## 13. Alternative Timelines (Ultimate)
`alternative_timelines` (Tier IV, PASSIVE).

> "You may play two cards each turn; if you do, after the cards are revealed, retrieve one of your unresolved cards."

Planning flow:
- **H1** Ult active: Emmitt commits card A → planning stays open for him → commits card B → once all heroes are done, revelation reveals **both** of Emmitt's cards.
- **H2** After reveal, before any hero resolves: Emmitt gets a **mandatory** choice of which of his two unresolved cards to retrieve; retrieved card returns to hand (face state restored); the other becomes his `current_turn_card`.
- **H3** Resolution order uses the remaining card's initiative.
- **H4** Emmitt may play only one card: first commit + explicit DONE signal (S7) → planning closes, no retrieve prompt, normal turn.
- **H5** Only 1 card in hand → single commit auto-completes planning for him (S7), no DONE needed.
- **U1** Ult not active (level < 8 or card not PASSIVE) → second commit rejected with a clear error.
- **U2** Retrieve prompt cannot be skipped (mandatory; "if you do" already satisfied by playing two).
- **U3** Views: between reveal and retrieve, both cards are visible to all players (`build_view`); after retrieve, the retrieved card is back in hand and hidden from opponents again.
- **U4** Third commit always rejected.
- **U5** Server contract: REST/WS commit endpoint accepts the second commit + DONE signal only for a hero with this ult active; `docs/CLIENT_INTEGRATION_GUIDE.md` updated; server tests in `tests/server/`.
- **U6** Persistence: game saved mid-retrieve-prompt restores correctly (input request re-emitted).
- **U7** Rule "must play a card if able" unchanged — Emmitt with cards cannot pass outright.

---

# Engine-primitive test paths (outside card files)

- **P1 `HasResolvedCardFilter`**: passes hero with `played_cards[turn_index]` set; rejects unresolved-card hero, passed hero, minion candidates, off-board heroes.
- **P3 snapshot**: recorded before planning each turn and at game creation; includes heroes, minions, tokens; respawned hero gets a fresh entry next snapshot; **persistence round-trip**.
- **P4 discard log**: appended on hand discard, played-area discard, and defense-reaction discard; cleared in `end_turn`; **persistence round-trip**.
- **P6 reversed initiative**: NEXT_TURN activation timing (created turn N → active turn N+1 only); round-boundary fizzle; no interference with `unresolved_hero_ids` bookkeeping.
- **P7 aura immunity**: radius scope evaluated dynamically; existing source_id-bound effects unaffected (regression tests around Whisper/Hanu).
- **P9 planning**: `_check_phase_transition` waits for Emmitt's DONE/second commit; non-Emmitt heroes unaffected; interaction with `pass_turn`.

# Implementation order (hardest first — per user; easy tail can be delegated to cheaper agents)

1. **P9 ultimate** (Alternative Timelines) — planning-phase two-card commit, post-reveal retrieve, server contract. Hardest; done first by the strongest agent.
2. **P7 aura immunity** → card 9 (Future Proof) — `is_immune` extension with regression risk.
3. **P6 reversed initiative** → card 12 (Reverse Time) — phases ordering + defeat-deactivation + round-boundary fizzle.
4. **P5 card swap** → card 5 (Time Warp) — novel card-state manipulation.
5. **P8/P10 Glitch tokens** → cards 10, 11 (Flashback/Déjà Vu, Unstable Timeline) — batch feasibility precheck + overflow batch-exclusion (U7b) + defense-mode hybrid.
6. **P3 snapshot + P4 discard log** → cards 6, 7, 8 (Time Walk/Fast Forward, Back to the Future, Time Capsule).
7. **P2 initiative-as-defense** → card 1 (Temporal line).
8. **P1 filter** → cards 2, 3, 4 (Time Snare/Trap, Time Bomb, Time Loop) — easiest, pure reuse; safe to delegate.

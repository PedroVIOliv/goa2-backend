# Snorri — TDD Test Paths (for review)

Status: **AWAITING REVIEW** (2026-07-10). No implementation started.

Snorri is a rune hero: 16 deck cards + ultimate, 9 effect classes (6 card
families + Inscribe + Rune Sigils + ultimate). Data:
`src/goa2/data/heroes/snorri.py`. Effects will live in
`src/goa2/scripts/snorri_effects.py`. Tests use `tests/engine/effects/`
helpers (`EffectScenarioBuilder` + `run_card`), marked `effect_contract` /
`effect_flow`, per repo convention.

**Core mechanic:** `inscribe_the_runes` places 4 rune markers (AXE, BIRD,
ANVIL, HORN) one below each of Snorri's 4 turn slots. A rune is **active**
while it sits below the slot matching the current turn (`state.turn` 1–4).
Markers persist across rounds and defeat. Every other card keys off which
rune is active; the ultimate adds a second active rune per action.

## Locked interpretations (confirmed with user, 2026-07-10)

1. **Rune activity is global by turn number**: the rune under slot N is
   active during ALL of turn N — Snorri's actions, enemy actions, and
   defense reactions alike.
2. **Inscribe replay = full re-placement**: every play of Inscribe
   (re)arranges all 4 runes freely. Nothing ever removes them (end of
   round and defeat both leave `rune_slots` untouched).
3. **Ultimate scope**: fires on Snorri's own actions AND on his defense
   reactions. Requires placed runes (Inscribe never played → inert). He
   chooses one **inactive placed** rune; it counts as a second active rune
   for that one action / that one defense only.
4. **Two active runes**: on "If a rune is active: • …" cards, ALL bullets
   whose rune is active apply, in printed order. "Choose one active rune"
   cards (Runebomb, Oath of Perseverance) pick exactly one — chosen
   **automatically when only one rune is active** (no prompt).
   Two-active-rune situations only need handling/tests on **tier III and
   untiered (gold/silver)** cards: at level 8 (ultimate) tier I/II cards
   are no longer in hand.
5. **Runecaster/Runeblaster axe rider**: "an enemy hero who was adjacent
   to the target" is snapshotted **at targeting time** (before the
   reaction window / damage). Snorri picks the hero if several qualify;
   the victim picks which card to discard; empty hand → defeated.
6. **Runic Battleaxe axe repeat = full-sequence repeat**: the repeat
   re-runs the whole printed sequence — the "before the attack" horn move
   (if horn is also active via the ultimate), the attack (constrained to
   an enemy minion adjacent to Snorri), and the after-attack riders
   (anvil retrieve can fire once per sequence) — except the repeat clause
   itself (max one repeat).
7. **Rune Sigils anvil**: 3 coins per attack **instance** that targeted a
   hero (base + horn repeat on a second hero = 6 coins).
8. **Oath immunity is unconditional on defend**: whenever an Oath is used
   as a defense reaction — block matched or not, rune active or not —
   Snorri gains "immune to enemy actions" for the REST of the turn,
   **starting after the current attack fully resolves**. If the attack
   defeats him, no immunity. The immunity never cancels the attack being
   defended.
9. **Self-exclusion (general GoA2 rule)**: "a hero" / "a unit" /
   "a friendly hero" in card text EXCLUDES the acting hero unless
   explicitly included. Ancestral Boon/Grace therefore target another
   friendly hero, never Snorri.
10. **Ancestral Grace item swap**: items are ITEM-state cards. Pick one
    ITEM-state card X and one non-item card Y of the **same tier and
    color** owned by that hero — Y may be in hand, resolved slots, or
    discard. Y flips to ITEM; X lands exactly where Y was
    (`Hero.swap_cards` semantics). Items dict: −1 X.item, +1 Y.item.
11. **One hero for all bullets**: on Runetrap / Ancestral Boon & Grace,
    when two runes are active, the affected hero is chosen ONCE and all
    active bullets apply to that same hero.
12. **Choice routing**: all card/item choices (and accept/decline of
    "may") for the affected friendly hero route to that hero's player;
    Snorri only picks the hero (and the rune, where the card says
    "choose one active rune").

## Spec decisions made by implementer (veto during review if wrong)

- **S1**: Inscribe placement flow: 4 sequential `SELECT_OPTION` prompts
  (slot 1 → 4, offering the runes not yet placed this play); the last
  rune is auto-placed. Final arrangement is emitted as a public
  `GameEvent` and `rune_slots` is public in `build_view()` for everyone.
- **S2**: "Target a unit at maximum range" =
  `RangeFilter(min_range=max_range=effective range)` (base + range items
  + modifiers), topology distance — Silverarrow/Swift/Ignatia precedent.
  No candidate at exactly max range → mandatory targeting fails → action
  aborts (after-attack riders skipped).
- **S3**: New `attack_is_basic` context flag set alongside
  `attack_is_ranged` by `AttackSequenceStep`, derived from the acting
  card's color (GOLD/SILVER = basic — repo reference rule). Consumed by
  Oath blocks (horn = basic, anvil = non-basic).
- **S4**: Ultimate hooks: own actions via the action-start path in
  `ResolveCardStep` (BEFORE any card text, including "before the attack"
  riders); defense reactions via the reaction path, prompted before the
  defense text evaluates, cleared per-defense (like `_PER_DEFENSE_KEYS`).
  The chosen rune lives in `execution_context` and is read by
  `active_runes()`.
- **S5**: The ultimate choice is **mandatory** when available (text has
  no "may"): with runes placed there are always exactly 3 inactive runes
  to pick from. No runes placed → no prompt.
- **S6**: Passage "This turn: you may ignore obstacles" = the card's
  movement runs with `pass_through_obstacles=True` (Bain precedent),
  offered as a may (player can path normally). No lingering board effect
  is created — Snorri performs no other own-movement this turn.
- **S7**: Runetrap/Runebomb discards are from **hand only**; "if able"
  fizzles silently; Snorri picks the victim; immune enemy heroes are
  excluded from selection.
- **S8**: Oath immunity implementation: `IMMUNITY_ENEMY_ACTIONS`
  `ActiveEffect`, `THIS_TURN` duration, created by a step scheduled to
  run after the defended attack's combat resolution (fires only if
  Snorri is alive).
- **S9**: Rune Sigils horn repeat: the repeat re-runs the attack sequence
  against a **different enemy hero** within range 2 (≠ original target);
  axe +3 and anvil coins apply per instance; the bird retarget option
  does not apply to the repeat (its target is constrained to a hero);
  max one repeat.
- **S10**: Ancestral Boon/Grace flow: Snorri picks the target hero
  (friendly, in radius 4, ≠ self, immunity does not apply — it's a
  friendly effect and allies can decline); then the affected player
  resolves each active bullet in printed order, each independently
  optional (the "may" scopes every bullet).
- **S11**: Grace bird bullet is only offered if the hero has ≥1
  ITEM-state card with ≥1 non-item card sharing its tier+color.
- **S12**: Rune Sigils bird = **enemy minion** within range 2 (topology).
- **S13**: Runeblaster bird = normal ranged targeting,
  `RangeFilter(max_range=effective range)`.
- **S14**: On "choose one active rune" cards with the ultimate: the
  ultimate rune is chosen first (action/defense start, S4), then the
  card's choose-one picks among the up-to-2 active runes.
- **S15**: Attack after-riders (retrieve, move, axe discard rider) fire
  regardless of whether the target survived, per existing after-attack
  convention.

## New engine primitives (each gets its own unit tests)

| # | Primitive | Where |
|---|-----------|-------|
| P1 | `RuneType` enum (AXE, BIRD, ANVIL, HORN); `Hero.rune_slots: dict[int, RuneType]` (default `{}`); public exposure in `build_view()`; placement `GameEvent` | `domain/models/enums.py`, `domain/models/unit.py`, `domain/views.py`, `domain/events.py` |
| P2 | `active_runes(state, hero, context)` helper: `rune_slots[state.turn]` + ultimate context rune | `scripts/snorri_effects.py` |
| P3 | Ultimate hooks: own-action prompt at action start + defense-reaction prompt, per-scope context key & clearing | `engine/steps/cards.py` (ResolveCardStep), `engine/steps/reactions.py` |
| P4 | `attack_is_basic` context flag from acting card color | `engine/steps/combat.py` |
| P5 | Targeting-time adjacency snapshot (enemy hero ids adjacent to the target, recorded when the target is selected) | effect-side step or `engine/steps/combat.py` |
| P6 | Post-defended-attack effect scheduling (immunity that activates after the current attack resolves, only if defender alive) | `engine/steps/reactions.py` / `combat.py` |
| P7 | `SwapItemCardStep`: ITEM-state card ↔ same tier+color card anywhere, items dict adjustment | `engine/steps/cards.py` |

Everything else is effect-body assembly from existing primitives
(`AttackSequenceStep`, `SelectStep`, `MoveUnitStep`/`MoveSequenceStep`,
`RetrieveCardStep`, `Hero.swap_cards`, forced-discard steps with color
filters (Tali precedent), `ForceDiscardOrDefeatStep` (Sabina/Trinkets),
`CreateEffectStep` for `IMMUNITY_ENEMY_ACTIONS` (Whisper Death Seeker),
repeat-attack assembly, coin grant).

---

# Per-card test paths

Notation: **H** = happy path, **U** = unhappy/edge path. Range/radius
checks always use topology distance. Offensive targeting includes
`ImmunityFilter` unless stated. "Rune R active" means Inscribe placed R
under the slot matching `state.turn`.

## 1. Inscribe the Runes (silver, init 1, SKILL)

> "Give yourself 4 Rune markers and place one below each of your turn
> slots. A rune is active as long as it is below the turn slot matching
> the current turn. Rune markers are not removed at the end of round, nor
> if you are defeated."

- **H1** First play → 4 sequential `SELECT_OPTION` prompts (4, 3, 2 options; last auto-placed) → `rune_slots` = chosen permutation → public `GameEvent` emitted (S1).
- **H2** `rune_slots` visible in `build_view()` for an OPPONENT (public info).
- **H3** Replay in a later round → full re-arrangement; new permutation overwrites the old (interp 2).
- **H4** End of round → `rune_slots` unchanged; Inscribe returns to hand like any card.
- **H5** Snorri defeated and respawns → `rune_slots` unchanged.
- **H6** Activity: rune under slot 2 is active on turn 2 and inactive on turns 1/3/4 (verified via a rune-conditional card).
- **U1** All rune-conditional clauses across the kit fizzle before Inscribe is ever played (covered per-card as "no rune active").

## 2. Runic Dagger (I, attack 5, adjacent)

> "Target a unit adjacent to you. After the attack: If the anvil rune is
> active, you may retrieve a discarded card."

- **H1** Anvil active, own discard non-empty → after the attack, optional retrieve prompt → chosen card returns to hand.
- **H2** Decline the retrieve → nothing.
- **H3** Retrieve fires even if the target was defeated (S15).
- **U1** Anvil not active → no retrieve prompt.
- **U2** Discard empty → no prompt.
- **U3** No adjacent target → mandatory targeting fails → action aborts.

## 3. Runic Hammer (II, attack 5, adjacent)

> "Before the attack: If the horn rune is active, you may move 1 space.
> Target a unit adjacent to you. After the attack: If the anvil rune is
> active, you may retrieve a discarded card."

- **H1** Horn active → optional 1-space move → target selected adjacent to the NEW position.
- **H2** Pre-move declined → attack from current position.
- **H3** Anvil active (instead of horn) → no pre-move; retrieve prompt after the attack.
- **U1** No rune active → plain adjacent attack, no riders.
- **U2** Horn active but no legal move hex → pre-move skipped, attack proceeds.
- **U3** Pre-move to a spot with no adjacent enemy → mandatory targeting fails → abort (player's risk).

## 4. Runic Battleaxe (III, attack 6, adjacent)

> "Before the attack: If the horn rune is active, you may move 1 space.
> Target a unit adjacent to you. After the attack: If a rune is active:
> • axe: May repeat once on an enemy minion. • anvil: You may retrieve a
> discarded card."

Inherits Hammer paths (H1/H2/U1/U2), plus:

- **H3** Axe active → after the attack, may repeat the full sequence on an enemy minion adjacent to Snorri (interp 6) → both targets damaged.
- **H4** Repeat declined → single attack.
- **H5** (ult) Horn+axe active → pre-move, attack, then the repeat re-runs the pre-move (second 1-space move) before attacking the minion.
- **H6** (ult) Axe+anvil active → riders in printed order: repeat first, retrieve fires once per sequence (up to 2 retrieves).
- **U3** No enemy minion adjacent (post-sequence position) → repeat not offered.
- **U4** The repeat's own riders do NOT include another repeat (max once).

## 5. Runecaster (II, ranged 3, attack 4)

> "Target a unit at maximum range. After the attack: If a rune is active:
> • horn: Move up to 2 spaces. • axe: An enemy hero who was adjacent to
> the target discards a card, or is defeated."

- **H1** Unit at exactly effective max range (3 + range items) → targetable; nearer units are NOT (S2).
- **H2** Horn active → after the attack, move up to 2 spaces (0–2, optional).
- **H3** Axe active → enemy hero adjacent to the target at targeting time → discards a card of their choice.
- **H4** Axe: victim's hand empty → defeated.
- **H5** Axe: several qualifying heroes → Snorri picks one (interp 5).
- **H6** Axe: adjacency snapshot — target pushed/defeated between targeting and rider → rider still uses targeting-time adjacency (interp 5, P5).
- **U1** No unit at exactly max range → mandatory targeting fails → abort.
- **U2** Axe active, no enemy hero adjacent to target at targeting time → rider fizzles.
- **U3** Topology: max range counted around obstacles, not through them.
- **U4** Axe rider: immune adjacent hero excluded.

## 6. Runeblaster (III, ranged 3, attack 5)

> "If the bird rune is active, target a unit in range, otherwise target a
> unit at maximum range. After the attack: (horn / axe riders as
> Runecaster)"

Inherits Runecaster paths, plus:

- **H1** Bird active → any unit within range targetable (S13).
- **H2** (ult) Turn rune horn + ult bird → flexible range AND post-attack move.
- **U1** Bird not active → exact-max-range targeting enforced.

## 7. Runetrap (II, SKILL, radius 3)

> "If a rune is active, an enemy hero in radius: • horn: Discards a green
> card, if able. • axe: Discards a silver card, if able. • anvil:
> Discards a blue card, if able."

- **H1** Horn active → Snorri picks an enemy hero in radius 3 → that hero discards a green card from hand (their choice among greens).
- **H2** Axe → silver; **H3** anvil → blue (same flow).
- **U1** Bird active → nothing (no bird bullet on this tier).
- **U2** Victim has no card of the color in hand → nothing ("if able").
- **U3** No enemy hero in radius → fizzle.
- **U4** No rune active → fizzle.
- **U5** Immune enemy hero excluded from selection (S7).
- **U6** Hand only: victim's committed/resolved cards of the color don't count (S7).

## 8. Runebomb (III, SKILL, radius 3)

> "Choose one active rune; depending on that rune, an enemy hero in
> radius: • horn: green • axe: silver • anvil: blue • bird: gold —
> discards, if able."

- **H1** One active rune → auto-chosen, no prompt (interp 4) → its bullet fires.
- **H2** Bird active → gold discard (bullet exists on this tier).
- **H3** (ult) Two active runes → Snorri prompted to choose ONE → only that bullet fires (S14).
- **U1** No active rune → fizzle.
- (Inherits Runetrap's U2/U3/U5/U6 flows.)

## 9. Oath of Endurance (I, DEFENSE primary)

> "If a rune is active: • horn: Block a basic attack. • axe: Block a
> non-ranged attack. This Turn: You are immune to enemy actions."

Defense reaction only (DEFENSE primary is never offered as a turn action —
engine default, contract-checked).

- **H1** Horn active + incoming basic attack (attacker's card is GOLD/SILVER, P4) → `auto_block` → no damage → immunity for the rest of the turn.
- **H2** Axe active + non-ranged attack → block.
- **H3** Rune/attack mismatch (e.g. horn active, colored-card melee attack) → no block, `defense_invalid` (card has no defense value) → damage resolves → Snorri survives → immune to enemy actions for the rest of the turn (interp 8): a second enemy attack this turn cannot target him.
- **H4** No rune active → no block; immunity still granted after the attack (interp 8).
- **U1** Snorri defeated by the unblocked attack → no immunity.
- **U2** Immunity does NOT cancel the attack being defended (starts after resolution).
- **U3** Immunity expires at end of turn — next turn he is targetable.

## 10. Oath of Fortitude (II)

Endurance + "• bird: Block a ranged attack."

- **H1** Bird active + ranged attack → block.
- **H2** Ranged card attacking from adjacency is still RANGED (repo rule) → bird blocks it; axe does not.
- (Inherits Endurance paths.)

## 11. Oath of Perseverance (III)

> "Choose one active rune: horn → basic; axe → non-ranged; bird → ranged;
> anvil → non-basic. This Turn: You are immune to enemy actions."

- **H1** Single active rune → auto-chosen → block per its type.
- **H2** Anvil + non-basic attack (colored card) → block.
- **H3** (ult on defend, interp 3) Ultimate prompt fires on the defense → Snorri picks an inactive rune → chooses between the two active runes' block types → blocks an attack the turn rune alone couldn't.
- **U1** Chosen rune's type mismatch → no block; immunity after (as Endurance H3).

## 12. Safe Passage (I, MOVEMENT 3)

> "If the bird rune is active, This turn: You may ignore obstacles."

- **H1** Bird active → movement may path through obstacle hexes (cannot end on one) (S6).
- **H2** The ignore is optional — normal pathing allowed.
- **U1** Bird not active → obstacles block pathing as normal.

## 13. Hidden Passage (II, MOVEMENT 3)

Safe Passage + "• anvil: This turn: You are immune to enemy actions."

- **H1** Anvil active → move, then immune to enemy actions for the rest of the turn (enemy acting after Snorri this turn cannot target him).
- **H2** Bird active → ignore obstacles (as Safe Passage).
- **U1** Immunity expires at end of turn.
- **U2** No rune active → plain move 3.

## 14. Deep Passage (III, MOVEMENT 3)

Hidden Passage + "• horn: Gain +2 Movement."

- **H1** Horn active → move up to 5.
- **H2** (ult) Bird+horn → 5 movement ignoring obstacles.
- **H3** (ult) Anvil+horn → 5 movement + immunity.
- **U1** No rune active → plain move 3.

## 15. Ancestral Boon (II, SKILL, radius 4)

> "If a rune is active, a friendly hero in radius may: • axe: Swap a
> resolved card with a card in hand. • anvil: Retrieve all their
> discarded cards."

- **H1** Axe active → Snorri picks a friendly hero (≠ self, interp 9) in radius 4 → THAT player picks one of their resolved cards + one hand card → swapped in place (resolved slot ↔ hand).
- **H2** Anvil active → chosen hero retrieves ALL their discarded cards to hand.
- **H3** Affected player declines ("may") → nothing (interp 12).
- **U1** No friendly hero (other than Snorri) in radius → fizzle.
- **U2** Snorri himself is never selectable.
- **U3** Axe: hero has no resolved cards or no hand cards → bullet unavailable.
- **U4** Anvil: empty discard → nothing.
- **U5** No rune active → fizzle.

## 16. Ancestral Grace (III, SKILL, radius 4)

Boon + "• bird: Swap one of their items with an item on their card of the
same tier and color."

Inherits Boon paths, plus:

- **H1** Bird active → hero picks one of their ITEM-state cards X and a non-item card Y of the same tier+color → Y flips to ITEM (+1 Y.item), X lands exactly where Y was (interp 10, P7); hero stats reflect the item change.
- **H2** Y in a resolved slot → X becomes RESOLVED in that slot.
- **H3** Y in discard → X lands in the discard pile.
- **H4** (ult) Two runes active → ONE hero chosen; both bullets offered to that same hero in printed order (interp 11).
- **U1** Hero has no ITEM-state cards → bird bullet unavailable (S11).
- **U2** No non-item card sharing tier+color with any ITEM card → unavailable.

## 17. Rune Sigils (gold, attack 2, ranged 2)

> "Target a unit adjacent to you; if a rune is active: • bird: You may
> target a minion in range instead. • axe: +3 Attack. • anvil: If you
> target a hero, gain 3 coins. • horn: Repeat once on a different hero in
> range."

- **H1** No rune → attack 2 on an adjacent unit; the attack counts as RANGED even at adjacency (repo rule; contract vs block-ranged defenses).
- **H2** Bird active → may instead target an enemy minion within range 2 (S12); adjacent targeting still offered.
- **H3** Axe active → attack resolves at 5.
- **H4** Anvil active → target is a hero → +3 coins; target is a minion → no coins.
- **H5** Horn active → may repeat once on a DIFFERENT enemy hero within range 2 (S9).
- **H6** (ult) Axe+horn → both attack instances at 5.
- **H7** (ult) Anvil+horn, both instances target heroes → 6 coins (interp 7).
- **U1** Horn: no other enemy hero in range → repeat not offered.
- **U2** Bird declined → adjacent targeting proceeds.
- **U3** No adjacent unit and bird inactive → mandatory targeting fails → abort.

## 18. Rune Mastery (ultimate, passive, level ≥ 8)

> "Each time you perform an action, choose one inactive rune; that rune
> counts as a second active rune for this action."

- **H1** Runes placed, Snorri performs an action → mandatory prompt: choose 1 of the 3 inactive runes (S5) → both runes' clauses apply for the whole action (verify via a tier III card, e.g. Deep Passage bird+horn).
- **H2** Fires on defense reactions too (interp 3): prompted when defending → second active rune for that defense only (verify via Oath of Perseverance H3).
- **H3** Scope: after the action/defense ends, only the turn rune is active again.
- **H4** Choice repeats per action — a later action the same round can pick a different rune.
- **H5** Two defenses in one turn → two independent prompts (per-defense clearing, S4).
- **U1** Runes never placed → no prompt, ultimate inert (interp 3).
- **U2** Level < 8 → inert.

---

## Test organization

- `tests/engine/effects/cases/test_snorri_effects.py` — all paths above,
  `effect_contract` for input/event shapes, `effect_flow` for multi-step
  behavior.
- P1–P7 primitives get focused unit tests next to their homes
  (`tests/engine/` / `tests/domain/`), including: `rune_slots` survives
  `retrieve_cards()` and defeat handling; view exposure; serialization
  round-trip of the new Hero field and `SwapItemCardStep`.
- Server contract untouched except `build_view()` gaining a public
  `rune_slots` entry → update `docs/CLIENT_INTEGRATION_GUIDE.md` (view
  structure) when implementing P1.

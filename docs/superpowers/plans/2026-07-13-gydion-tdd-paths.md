# Gydion — First Six Spells TDD Test Paths (for review)

Status: **IMPLEMENTED** (2026-07-13). Final verification: **2,823 passed**;
Ruff, Black, and mypy clean.

Implementation note: ordinary cards and spells retain their public printed
effect IDs, while subtype-aware registry lookup separates their behavior. In
particular, Brogan's Shield and Gydion's Shield can both use `"shield"`
without import-order-dependent registration collisions.

This phase implements Gydion's spellbook and the first six spell cards:
**Shocking Grasp**, **Magic Missile**, **Expeditious Retreat**, **Burning
Hands**, **Suggestion**, and **Shield**. Gydion's deck data already lives in
`src/goa2/data/heroes/gydion.py`; effect logic will live in
`src/goa2/scripts/gydion_effects.py`.

The scope includes every Gydion access card that can cast one of those six
spells, even at higher tiers. Higher, unimplemented spells and Wish remain
out of scope. Tests use the `tests/engine/effects/` fluent helpers for card
flows and raw-stack tests for new engine primitives.

Source image used for the six fronts:
`https://steamusercontent-a.akamaihd.net/ugc/11036076096773994562/200CD926916ED231EFC9ABC1F64A9483FBB7EC25/`

## Locked interpretations (confirmed with user, 2026-07-13)

1. **Unique spellbook**: a game contains at most one Gydion, and only Gydion
   owns spell cards/a spellbook. The engine may locate that unique owner
   rather than routing among multiple spellbooks.
2. **Initial state**: all six spells start faceup outside the spellbook.
   They are not in Gydion's deck, hand, discard pile, played slots, upgrade
   pool, or item pool.
3. **Prepare Spells**: returns every outside spell to the spellbook; spells
   already inside stay there. Inside spells are facedown. Returning Shield
   immediately cancels an active Shield effect tied to it.
4. **Visibility**: Gydion sees complete identities/details of cards in the
   spellbook. Other players and spectators see only its count. Every spell
   outside the spellbook is faceup and public.
5. **Cast timing**: after a spell is selected it immediately moves outside
   the spellbook faceup, before its action chooser. It remains spent even if
   the selected action later cannot complete.
6. **Normal action menu**: spells generate the same secondary actions as
   ordinary cards. Attack spells offer primary Attack, Clear, Hold; Movement
   spells offer primary Movement, Fast Travel, Hold; Skill spells offer
   primary Skill, Hold. A secondary action spends the spell but does not run
   its primary effect text.
7. **Nested complete action**: the outer Gydion card performs its Skill, then
   the selected spell action is performed as a complete nested action with
   its own BEFORE/AFTER action-type and basic-action hooks. Only the outer
   Gydion card fires `AFTER_RESOLVE_CARD`; a cast spell is not a played turn
   card.
8. **Action source**: while resolving the nested spell action, the spell is
   the source card for color, basic status, action restrictions, passive
   conditions, effect binding, and attack classification. Context is restored
   to the outer Gydion card before its remaining after-action hooks run.
9. **Caster stats**: Attack, Movement, Range, and Radius use the casting
   hero's items and active modifiers. The outer access card contributes no
   stats to the spell action.
10. **Copied access cards**: if another hero performs a Gydion access-card
    action, that hero chooses from Gydion's unique spellbook and becomes the
    caster. Their position/stats/items drive the spell; Gydion remains the
    owner of the spellbook. The cast-selection request is an intentional
    exception to normal spellbook-view secrecy.
11. **Repeats**: repeating an outer access-card Skill casts another available
    spell. Repeating the already-cast spell action performs that spell action
    again without spending another spell.
12. **Suggestion**: the caster chooses any targetable enemy hero in computed
    Radius; the target is not prefiltered by whether it can complete the move.
    The caster then chooses a legal destination exactly 3 spaces away on one
    straight-line path. If the chosen hero has no such destination, the spell
    fizzles with no fallback target choice. This is forced movement, not a
    Movement action; Movement bonuses do not change 3. Immunity applies.
13. **Shocking Grasp**: after the attack, the caster may move the surviving
    target up to 1 space. It fires after a blocked attack, but fizzles if the
    target was defeated/removed or cannot be moved.
14. **Burning Hands**: choose the adjacent attack target first. Before its
    reaction window, the caster may choose zero or one enemy hero adjacent to
    that target; that hero chooses a card to discard, if able. The target is
    not adjacent to itself.
15. **Magic Missile / Expeditious Retreat**: Magic Missile targets at minimum
    distance 2 and computed maximum Range. Expeditious Retreat's primary path
    is straight and up to computed Movement; its Fast Travel secondary does
    not inherit the straight-line restriction.
16. **Shield**: protects the caster (including a copied-action caster) from
    basic attacks. This includes normal Gold/Silver attacks and the basic
    spell attacks Shocking Grasp and Magic Missile, but not Burning Hands.
    It ends at round end or immediately when Shield returns to the spellbook.
17. **Partial six-spell phase**: higher Evocation, Abjuration, and Enchantment
    access cards may cast their implemented level-one spell. Necromancy,
    Conjuration, Transmutation, and Wish currently produce no spell action.

## Spell definitions and generated actions

| Spell | Card classification | Printed stats/text | Generated menu |
|---|---|---|---|
| Shocking Grasp | GOLD/UNTIERED, basic | Attack 3; adjacent; after attack move target up to 1 | Attack / Clear / Hold |
| Magic Missile | GOLD/UNTIERED, basic | Ranged Attack 1; Range 3; not adjacent | Attack / Clear / Hold |
| Expeditious Retreat | GOLD/UNTIERED, basic | Movement 5; straight line only | Movement / Fast Travel / Hold |
| Burning Hands | RED/I, non-basic | Attack 5; adjacent; optional pre-attack discard | Attack / Clear / Hold |
| Suggestion | BLUE/I, non-basic | Skill; Radius 3; forced straight move 3 | Skill / Hold |
| Shield | GREEN/I, non-basic | Skill; this-round basic-attack immunity | Skill / Hold |

`initiative=0` and `item=None` are inert spell-model values. The spell rank
is stored separately from ordinary deck progression; spell cards never enter
planning or upgrading.

## Spec decisions made by the plan (implementation defaults)

- **S1 — Representation**: `SpellCard` subclasses `Card`. Add spell-specific
  metadata plus `CardState.SPELLBOOK` and `CardState.OUTSIDE_SPELLBOOK`.
  Gydion owns one master `spells: list[SpellCard]`; state determines which
  computed zone a spell occupies. Inherited Card validators generate Hold,
  Clear, and Fast Travel.
- **S2 — Unique owner lookup**: add a `GameState` helper that returns the one
  hero with a non-empty spell list. No effect script hardcodes
  `hero_gydion`; copied actions keep working with custom test IDs.
- **S3 — Cast primitive**: `CastSpellStep(allowed_spell_ids, caster_id/key)`
  filters only currently prepared allowed spells. Zero options is a clean
  no-op; one auto-selects; multiple produce `SELECT_CARD` for the caster.
  A valid selection spends/reveals before pushing the spell action chooser.
- **S4 — Prepare primitive**: `PrepareSpellbookStep` expires effects bound to
  each returning spell, moves every outside spell inside/facedown, and emits
  one public event. Repeating it is idempotent.
- **S5 — Nested action context**: generalize the existing performed-card
  dispatcher rather than create a third action implementation. Maintain an
  action-context stack containing action type and performing-card ID. Spell
  actions run normal before/after hooks except `AFTER_RESOLVE_CARD`; restore
  the outer context on every completion/abort path.
- **S6 — Source-card lookup**: `GameState` card lookup includes spell cards.
  Combat basic classification, stat auras, repeat machinery, effect creation,
  and validation consult the performing-card override before the hero's turn
  card.
- **S7 — Visibility contract**: hero views gain `spellbook` and
  `cast_spells`. For the owner/reveal-all, `spellbook` is a list of full card
  views; for everyone else it is `{count: N}`. `cast_spells` is always a list
  of full faceup views. Heroes without spells expose no spellbook (`null`) and
  an empty cast list.
- **S8 — Events**: add public `SPELL_CAST` and `SPELLBOOK_PREPARED` events.
  Cast metadata includes spell ID, owner ID, and caster ID. Prepare metadata
  includes the public IDs returned plus the resulting count.
- **S9 — Basic-only immunity through the existing effect pipeline**: Shield
  uses `CreateEffectStep(effect_type=ATTACK_IMMUNITY, ...)`, as existing Arien
  and Tigerclaw effects do. Add only a generic `basic_attacks_only` payload to
  `ActiveEffect`/`CreateEffectStep`; existing immunities default false and
  remain unchanged. Reuse the `attack_is_basic` context written by
  `AttackSequenceStep` and already consumed by Snorri's Oath logic, so Shield
  filters the caster out of basic-attack target choices only. Do not add a
  Shield-specific step or effect type.
- **S10 — One card-bound effect per spell**: repeated Shield primary actions
  refresh/reuse the spell's effect instead of accumulating duplicate
  card-bound immunity instances.
- **S11 — Partial access map**: all 16 Gydion spell-access effect IDs are
  registered against their printed allowed IDs. The cast primitive intersects
  that list with implemented/prepared spells; empty families no-op and become
  live automatically as future spell data/effects are added.

## New engine primitives

| # | Primitive | Main files |
|---|---|---|
| P1 | `SpellCard`, spell states, `Hero.spells`, unique owner/card lookup | `domain/models/spell.py`, `domain/models/enums.py`, `domain/models/unit.py`, `domain/state.py` |
| P2 | Nested performing-card/action context + generalized `PerformCardActionStep` | `engine/steps/cards.py`, `engine/steps/phases.py`, `engine/stats.py`, `engine/steps/combat.py` |
| P3 | `CastSpellStep` / `PrepareSpellbookStep` and events | `engine/steps/spells.py`, `domain/events.py` |
| P4 | Spellbook/cast-spell player views | `domain/views.py`, `docs/CLIENT_INTEGRATION_GUIDE.md` |
| P5 | Basic-only condition on existing `ATTACK_IMMUNITY` creation/evaluation | `domain/models/effect.py`, `engine/steps/effects.py`, `engine/filters_units.py` |

Everything else is effect assembly from `AttackSequenceStep`, `MoveSequenceStep`,
`SelectStep`, `MoveUnitStep`, `ForceDiscardStep`, and `CreateEffectStep`.

---

# Contract and flow test paths

Notation: **H** = happy path, **U** = unhappy/edge path. Offensive selections
respect immunity unless the card explicitly says otherwise.

## 1. SpellCard data and generated actions

- **H1** Registry Gydion has exactly six spell cards with the printed values,
  range/radius exclusivity, classification, and effect IDs in the table.
- **H2** Shocking Grasp, Magic Missile, and Burning Hands expose primary
  Attack + Clear + Hold.
- **H3** Expeditious Retreat exposes Movement + Fast Travel + Hold.
- **H4** Suggestion and Shield expose Skill + Hold.
- **H5** All start `OUTSIDE_SPELLBOOK`, faceup, and absent from every normal
  card zone.
- **H6** Hero/GameState JSON round-trip preserves subtype, spell state, and
  all six cards.
- **U1** Spell cards cannot be committed, discarded, upgraded, converted to
  items, selected from a normal hand/deck/discard container, or retrieved.
- **U2** Adding a spell to `Hero.spells` does not change starting hand size.

## 2. Prepare Spells, zones, events, and visibility

- **H1** Playing Prepare Spells primary moves all six inside facedown and
  emits `SPELLBOOK_PREPARED` with resulting count 6.
- **H2** With two spells already inside and four outside, only the four return;
  final count is 6 and no duplicate objects appear.
- **H3** Owner view after preparation shows six complete spell cards;
  opponent/spectator views show only `{count: 6}`.
- **H4** After one cast, every view shows that spell in `cast_spells` faceup;
  owner sees five prepared identities while others see `{count: 5}`.
- **H5** REST and WebSocket player-scoped views preserve the same secrecy.
- **H6** Save/load after preparation and after a cast preserves zones and
  visibility.
- **U1** Preparing an already-full spellbook is idempotent: no duplicate,
  no effect corruption, count remains six.
- **U2** Heroes without spell cards expose `spellbook: null` and
  `cast_spells: []` without changing their normal card views.

## 3. Cast lifecycle and normal action dispatch

- **H1** Cantrip with all three spells prepared prompts the caster with exactly
  those three spell IDs.
- **H2** A single eligible spell auto-selects; no redundant spell-choice input.
- **H3** Immediately after spell selection and before the action choice, the
  spell is outside/faceup, the public cast event exists, and the spellbook
  count has decreased.
- **H4** Action chooser menus match §1 H2-H4 and route input to the caster.
- **H5** Choosing a primary action resolves the registered spell effect with
  caster stats.
- **H6** Choosing Clear, Fast Travel, or Hold resolves that normal secondary
  and never runs the spell's primary effect.
- **U1** No prepared allowed spell → no choice, no event, no state change; the
  outer access card continues/finalizes normally.
- **U2** Invalid/stale spell selection is rejected without spending a spell.
- **U3** Once validly selected, choosing a primary action with no legal target
  still leaves the spell outside the spellbook.
- **U4** A spent spell is absent from later allowed-spell choices until Prepare
  Spells returns it.

## 4. Nested actions, source identity, copying, and repeats

- **H1** Cantrip → Shocking Grasp primary fires outer BEFORE_ACTION /
  BEFORE_SKILL and inner BEFORE_ACTION / BEFORE_ATTACK in order, then inner
  AFTER_ATTACK / AFTER_BASIC_ACTION / AFTER_PRIMARY_ACTION, then restores
  outer Skill context for its basic-skill/basic-action/primary/card-resolved
  hooks.
- **H2** Only the outer card fires `AFTER_RESOLVE_CARD`.
- **H3** During the spell action, card-color/basic/action checks see the spell;
  immediately afterwards they see the outer access card again.
- **H4** An item/modifier on the caster changes the matching spell stat;
  Gydion's items do not affect a copied-action caster.
- **H5** Another hero performing Cantrip chooses from Gydion's spellbook,
  spends Gydion's spell, and attacks/moves from the copier's board position.
- **H6** Shield cast by another hero protects that caster, not Gydion.
- **H7** Repeating Cantrip casts another available cantrip spell.
- **H8** Repeating Shocking Grasp's spell action attacks again without a
  second spellbook removal or second `SPELL_CAST` event.
- **U1** Context restores correctly when the inner action aborts for no target
  or stops on a failed mandatory step.
- **U2** Existing normal `ResolveCardStep`, Mind Grip's performed-card menu,
  repeats, and non-spell basic-action classification remain unchanged.
- **U3** Stack persistence round-trip while waiting at the spell choice and
  action choice resumes with the same owner/caster/source identities.

## 5. Access-card map and partial scope

- **H1** Cantrip permits only Shocking Grasp, Magic Missile, and Expeditious
  Retreat.
- **H2** Elementary/Lesser/Greater Evocation can cast Burning Hands while it
  is prepared.
- **H3** Elementary/Lesser/Greater Abjuration can cast Shield while prepared.
- **H4** Elementary/Lesser/Greater Enchantment can cast Suggestion while
  prepared.
- **U1** A listed but already-spent spell is not offered.
- **U2** Lesser/Greater Necromancy, Conjuration, and Transmutation safely
  produce no spell action in this phase; their normal secondary actions still
  work.
- **U3** The Archwizard/Wish remains inert until Wish is implemented.

## 6. Shocking Grasp

> Basic Attack 3. "Target a unit adjacent to you. After the attack: Move the
> target up to 1 space."

- **H1** Adjacent enemy target → Attack 3 resolves through the normal defense
  window → caster may choose a legal destination at distance 0 or 1 from the
  target's current space.
- **H2** Blocked attack still offers the optional move.
- **H3** Caster may SKIP the move; target stays put.
- **H4** Caster's Attack items/modifiers change Attack 3.
- **H5** It is classified basic for Shield and basic-attack passives.
- **H6** Clear and Hold spend Shocking Grasp but neither attacks nor moves a
  target.
- **U1** Defeated/removed target → no movement prompt.
- **U2** Surviving but immovable target or no legal adjacent destination →
  movement cleanly fizzles.
- **U3** No adjacent legal attack target → primary aborts after the spell has
  already been spent.

## 7. Magic Missile

> Basic ranged Attack 1, Range 3. "Target a unit in range and not adjacent to
> you."

- **H1** Enemy at distance 2 or 3 is selectable; attack is ranged and basic.
- **H2** Range item raises maximum range and offers the farther target.
- **H3** Ranged-defense reactions see `attack_is_ranged=True`.
- **H4** Attack items/modifiers change Attack 1.
- **H5** Clear and Hold spend the spell without attacking.
- **U1** Adjacent enemy is excluded even when no other target exists.
- **U2** Enemy beyond computed Range is excluded.

## 8. Expeditious Retreat

> Basic Movement 5. "Move only in a straight line."

- **H1** Primary offers every legal destination up to computed Movement 5 on
  any of the six straight axes, including distance 0.
- **H2** Movement item raises the maximum while preserving straightness.
- **H3** Fast Travel uses the standard safe-zone flow and ignores the printed
  straight-line restriction.
- **H4** Hold spends the spell without movement.
- **U1** Non-straight destinations are excluded even if path distance <= 5.
- **U2** Obstacle/occupancy/path rules still restrict primary Movement.

## 9. Burning Hands

> Attack 5. "Target a unit adjacent to you. Before the attack: Up to 1 enemy
> hero adjacent to the target discards a card, if able."

- **H1** Select adjacent attack target, then select a different adjacent enemy
  hero; victim chooses one hand card; discard finishes before the attack
  reaction window opens.
- **H2** Caster chooses zero victims and the attack still proceeds.
- **H3** Chosen hero with empty hand suffers no penalty; attack still proceeds.
- **H4** Blocked attack does not undo the already-resolved discard.
- **H5** Attack items/modifiers change Attack 5; attack is non-basic.
- **H6** Clear/Hold spend the spell without discard or attack.
- **U1** The attack target itself is not offered merely because it is a hero
  (distance 0 is not adjacent).
- **U2** Non-hero units adjacent to the target are not discard candidates.
- **U3** No discard candidate → attack proceeds with no discard prompt.
- **U4** No adjacent attack target → nothing in the before-attack rider runs.

## 10. Suggestion

> Skill, Radius 3. "If able, an enemy hero in radius moves 3 spaces in a
> straight line."

- **H1** Caster chooses any targetable enemy hero in computed radius, then
  chooses an exact-3 straight legal destination for that hero.
- **H2** With multiple axes/destinations, caster controls both choices.
- **H3** Radius item expands candidate range but movement remains exactly 3.
- **H4** Movement is forced: it does not receive Movement items, does not use
  Movement-action limits, and does not fire movement-action hooks.
- **H5** Hold spends Suggestion but moves nobody.
- **U1** An enemy hero with no exact-3 straight destination is still offered.
  Selecting that hero produces no destination prompt and fizzles the spell;
  the caster does not return to target selection, even if another enemy could
  have moved.
- **U2** No targetable enemy hero in radius → the mandatory target selection
  has no options and the spell fizzles.
- **U3** Immune enemy hero is excluded.
- **U4** Obstacles, occupied destination, blocked path, and board edge remove
  destination options. Displacement prevention is enforced again by
  `MoveUnitStep`; if it blocks the chosen move, the spell fizzles with no
  fallback hero choice.
- **U5** Distance 1, 2, or 4 and bent paths are never offered.

## 11. Shield

> Skill. "This round: You are immune to basic attacks. (Cancelled if the
> spell is returned to the spellbook.)"

- **H1** Primary creates one active, card-bound, THIS_ROUND basic-only attack
  immunity on the caster.
- **H2** Normal Gold/Silver attacks and Shocking Grasp/Magic Missile cannot
  target the protected hero.
- **H3** Burning Hands and other non-basic attacks can target normally.
- **H4** Another hero casting Shield receives the protection.
- **H5** Prepare Spells returns Shield and removes its active effect
  immediately, allowing later basic attacks that round.
- **H6** End of round removes the effect but leaves Shield faceup/outside until
  prepared.
- **H7** Hold spends Shield without creating immunity.
- **H8** Repeating Shield's primary action leaves one effective card-bound
  immunity instance, not duplicates.
- **U1** Existing unrestricted `ATTACK_IMMUNITY` effects still block both
  basic and non-basic attacks.
- **U2** Effect/source cleanup survives JSON rollback/persistence round-trip.

## Required regression and quality gates

- New concrete steps have unique enum types and round-trip through `AnyStep`
  persistence. Suggestion uses existing selectors and geometry/movement
  filters; it introduces no new filter or selector mode.
- Every spellbook state mutation emits an observable event.
- `build_view()` never exposes prepared identities to opponents/spectators.
- Existing 2,751-test baseline stays green after every task.
- Final gates:

```bash
PYTHONPATH=src uv run pytest tests/ -q
uv run ruff check src/
uv run black --check src/
uv run mypy src/
```

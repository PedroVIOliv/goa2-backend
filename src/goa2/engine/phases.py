import logging

from goa2.domain.models import Card, GamePhase
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.handler import push_steps
from goa2.engine.steps import (
    FinishedExpiringEffectStep,
    GameStep,
    ResolveTieBreakerStep,
)

logger = logging.getLogger(__name__)


def commit_card(state: GameState, hero_id: HeroID, card: Card):
    """
    Called when a player selects a card during the Planning Phase.
    Validates that the card is in the player's hand.
    """
    if state.phase != GamePhase.PLANNING:
        logger.warning("Cannot commit card. Game is in %s", state.phase)
        return

    hero = state.get_hero(hero_id)
    if not hero:
        logger.warning("Hero %s not found.", hero_id)
        return

    if hero_id in state.pending_inputs:
        raise ValueError(f"{hero_id} has already committed a card this turn")

    # Check if card is in hand
    if card not in hero.hand:
        logger.warning(
            "%s tried to play card %s which is not in hand.",
            hero_id,
            card.id,
        )
        return

    # Move card from hand to pending buffer (Facedown on board)
    # Using helper to ensure state consistency
    try:
        hero.play_card(card)
    except ValueError as e:
        logger.warning("Error playing card: %s", e)
        return

    state.pending_inputs[hero_id] = card
    logger.info("%s committed a card.", hero_id)

    _check_phase_transition(state)


def pass_turn(state: GameState, hero_id: HeroID):
    """
    Called when a player has no cards and must Pass.
    """
    if state.phase != GamePhase.PLANNING:
        return

    hero = state.get_hero(hero_id)
    if not hero:
        return

    # Rule Check: You must play a card if able.
    if len(hero.hand) > 0:
        logger.warning("%s cannot pass. Hand has %s cards.", hero_id, len(hero.hand))
        return

    state.pending_inputs[hero_id] = None
    logger.info("%s passed.", hero_id)

    _check_phase_transition(state)


def _check_phase_transition(state: GameState):
    # Check if all heroes have committed (Card or Pass)
    total_heroes = sum(len(team.heroes) for team in state.teams.values())
    if len(state.pending_inputs) >= total_heroes:
        start_revelation_phase(state)


def start_revelation_phase(state: GameState):
    """
    Reveals all cards and sets up the unresolved pool.
    """
    state.phase = GamePhase.REVELATION
    logger.info("Revelation phase started.")

    state.unresolved_hero_ids = []

    # Assign cards to heroes and populate the unresolved list
    for h_id, card in state.pending_inputs.items():
        # If card is None, the player Passed. They do not enter the resolution pool.
        if card is None:
            continue

        hero = state.get_hero(h_id)
        if hero:
            logger.info(
                "%s reveals %s (initiative: %s)",
                h_id,
                card.name,
                card.initiative,
            )
            card.is_facedown = False
            # card.state is already UNRESOLVED from play_card

            hero.current_turn_card = card
            state.unresolved_hero_ids.append(h_id)
        else:
            logger.warning("Hero %s not found during revelation.", h_id)

    state.pending_inputs = {}  # Clear buffer

    # Transition to Resolution
    start_resolution_phase(state)


def start_resolution_phase(state: GameState):
    state.phase = GamePhase.RESOLUTION
    logger.info("Resolution phase started.")
    resolve_next_action(state)


def resolve_next_action(state: GameState):
    """
    Dynamically identifies the next actor based on current initiatives.
    Follows Rule: "After each action... re-identify the player with Highest Initiative".
    """
    if not state.unresolved_hero_ids:
        logger.info("All cards resolved. Turn complete.")
        end_turn(state)
        return

    # 1. Calculate current initiatives for all candidates
    from goa2.domain.models import StatType
    from goa2.engine.stats import get_computed_stat

    candidates: list[tuple[HeroID, int]] = []
    for h_id in state.unresolved_hero_ids:
        hero = state.get_hero(h_id)
        if hero and hero.current_turn_card:
            # Safety Check: Cards must be revealed to have effective initiative > 0
            if hero.current_turn_card.is_facedown:
                logger.warning(
                    "Initiative calculated for facedown card of %s.",
                    h_id,
                )

            # Use Computed Stat (Card Base + Items + Modifiers)
            base_init = hero.current_turn_card.get_base_stat_value(StatType.INITIATIVE)
            total_init = get_computed_stat(state, h_id, StatType.INITIATIVE, base_init)

            candidates.append((h_id, total_init))

    if not candidates:
        return

    # 2. Sort Descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    # 3. Identify Tied Group
    highest_init = candidates[0][1]
    tied_hero_ids = [c[0] for c in candidates if c[1] == highest_init]

    # 4. If no tie -> Resolve immediately
    if len(tied_hero_ids) == 1:
        hero_id = tied_hero_ids[0]
        state.current_actor_id = hero_id

        # Remove from pool immediately (Acting/Resolved)
        if hero_id in state.unresolved_hero_ids:
            state.unresolved_hero_ids.remove(hero_id)

        logger.info("Next actor: %s (initiative: %s)", hero_id, highest_init)

        # Convert Card to Steps
        from goa2.engine.steps import (
            ConfirmResolutionStep,
            FinalizeHeroTurnStep,
            ResolveCardStep,
            RespawnHeroStep,
        )

        steps: list[GameStep] = []
        if hero_id not in state.entity_locations:
            steps.append(RespawnHeroStep(hero_id=hero_id))
        steps.extend(
            [
                ResolveCardStep(hero_id=hero_id),
                ConfirmResolutionStep(hero_id=hero_id),
                FinalizeHeroTurnStep(hero_id=hero_id),
            ]
        )
        push_steps(state, steps)
        return

    # 5. If tie -> Push Tie Breaker Step
    logger.info(
        "Tie detected at initiative %s between %s",
        highest_init,
        tied_hero_ids,
    )

    # We DO NOT remove them from unresolved_hero_ids yet.
    state.execution_stack.append(ResolveTieBreakerStep(tied_hero_ids=tied_hero_ids))


def end_turn(state: GameState):
    """
    Called when all players have acted in the Resolution Phase.
    Expires THIS_TURN and active NEXT_TURN effects. If any have finishing
    steps, those are pushed onto the stack followed by AdvanceTurnStep
    (deferred advancement). Otherwise, advances synchronously.
    """
    logger.info("End of turn %s.", state.turn)

    from goa2.engine.effect_manager import EffectManager

    finishing = EffectManager.expire_active_turn_effects(state)

    if finishing:
        from goa2.engine.steps import AdvanceTurnStep, SetActorStep

        finish_steps: list[GameStep] = []
        for source_id, steps in finishing:
            finish_steps.append(SetActorStep(actor_id=source_id))
            finish_steps.extend(steps)
            finish_steps.append(FinishedExpiringEffectStep())

        finish_steps.append(AdvanceTurnStep())
        push_steps(state, finish_steps)
        return

    # No finishing steps — advance synchronously (existing behavior)
    if state.turn < 4:
        state.turn += 1
        state.phase = GamePhase.PLANNING
        logger.info("Start of turn %s. Phase: planning.", state.turn)
        # Auto-pass heroes with no cards in hand
        auto_passed = False
        for team in state.teams.values():
            for hero in team.heroes:
                if len(hero.hand) == 0:
                    state.pending_inputs[hero.id] = None
                    logger.info("%s auto-passed (empty hand).", hero.id)
                    auto_passed = True
        if auto_passed:
            _check_phase_transition(state)
    else:
        start_end_phase(state)


def start_end_phase(state: GameState):
    state.phase = GamePhase.CLEANUP
    logger.info("End phase started.")

    from goa2.engine.steps import EndPhaseStep

    push_steps(state, [EndPhaseStep()])

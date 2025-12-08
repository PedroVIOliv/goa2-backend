from goa2.engine.effects import Effect, EffectRegistry, EffectContext
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.types import UnitID, HeroID
from goa2.domain.models import TeamColor
from goa2.engine.rules import validate_target
import uuid

@EffectRegistry.register
class ViolentTorrentEffect(Effect):
    @property
    def id(self) -> str:
        return "effect_attack_discard_behind_repeat" # Matching Definition

    def on_pre_action(self, ctx: EffectContext) -> None:
        """
        Target a unit adjacent to you. Before the attack: Up to 1 enemy hero in any of the 5 spaces in a straight line directly behind the target discards a card, or is defeated.
        """
        state = ctx.state
        attacker = ctx.actor
        target = ctx.target
        
        if not attacker or not target:
            return
            
        attacker_loc = state.unit_locations.get(attacker.id)
        target_loc = state.unit_locations.get(target.id)
        
        if not attacker_loc or not target_loc:
            return
            
        # Determine Direction
        direction = attacker_loc.direction_to(target_loc)
        if direction is None: return # Not straight line?
        
        # Check 5 spaces behind target
        current_hex = target_loc
        found_hero = None
        
        for _ in range(5):
            current_hex = current_hex.neighbor(direction)
            if current_hex in state.unit_locations.values():
                # Check Unit
                # Inefficient reverse lookup or new state helper needed.
                # Assuming state.get_unit_at(hex) exists or we iterate.
                unit_at = None
                for uid, loc in state.unit_locations.items():
                    if loc == current_hex:
                         # Get unit object
                         unit_at = state.get_unit(uid)
                         break
                
                if unit_at and unit_at.team != attacker.team:
                    # Is it a Hero?
                    if hasattr(unit_at, 'hand'): # Duck typing for Hero
                        found_hero = unit_at
                        break # "Up to 1 enemy hero"
        
        if found_hero:
            print(f"   [Effect] Violent Torrent hits {found_hero.name} behind target!")
            # Discard Logic
            if found_hero.hand:
                # Discard random or choice? Usually choice.
                # Simplification: Discard first card or Random.
                # Rule check: "Discards a card". Usually opponent chooses? or victim?
                # Assuming Victim Chooses -> Needs Input Request.
                # For MVP: Random/First Discard.
                discarded = found_hero.hand.pop(0)
                discarded.state = "DISCARD"
                found_hero.discard_pile.append(discarded)
                print(f"   {found_hero.name} discarded {discarded.name}")
            else:
                print(f"   {found_hero.name} has no cards -> Defeated!")
                # Defeat Logic (Reduce Life/Respawn?)
                pass

@EffectRegistry.register
class EbbAndFlowEffect(Effect):
    @property
    def id(self) -> str:
        return "effect_swap_enemy_minion_repeat"

    def on_pre_action(self, ctx: EffectContext) -> None:
        # Push Input Request for Target Selection
        req_id = str(uuid.uuid4())
        req = InputRequest(
            id=req_id,
            player_id=ctx.actor.id,
            request_type=InputRequestType.SELECT_UNIT,
            context={
                "criteria": "enemy_minion",
                "range": ctx.card.range_value
            }
        )
        ctx.state.input_stack.append(req)

    def on_post_action(self, ctx: EffectContext) -> None:
        # Handle the input resolution
        target_id_str = ctx.data.get("input_unit_id")
        if not target_id_str:
            print("   [Effect] No target selected for Swap")
            return
            
        target_id = UnitID(target_id_str)
        target_unit = ctx.state.get_unit(target_id)
        
        if not target_unit:
            return
            
        # Swap Locations
        actor_loc = ctx.state.unit_locations.get(ctx.actor.id)
        target_loc = ctx.state.unit_locations.get(target_id)
        
        ctx.state.move_unit(ctx.actor.id, target_loc)
        ctx.state.move_unit(target_id, actor_loc)
        
        print(f"   [Effect] Swapped {ctx.actor.name} with {target_unit.name}")

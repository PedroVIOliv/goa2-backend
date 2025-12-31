from goa2.engine.effects import Effect, EffectRegistry, EffectContext
from goa2.domain.input import InputRequest, InputRequestType
from goa2.engine.defeat import defeat_unit
from goa2.domain.types import UnitID, HeroID
from goa2.domain.models import TeamColor, Marker
from goa2.domain.hex import Hex
from goa2.engine.rules import validate_target, validate_movement_path
import uuid

# =========================================================================
# Shared Effects
# =========================================================================

class DiscardBehindEffect(Effect):
    """
    Base effect for Violent Torrent and Dangerous Current.
    """
    def __init__(self, id_val: str, distance: int, repeat: bool):
        self._id = id_val
        self.distance = distance
        self.repeat = repeat

    @property
    def id(self) -> str:
        return self._id

    def on_pre_action(self, ctx: EffectContext) -> None:
        # Metadata check to preventing re-execution after interruption
        if ctx.card.metadata.get("discard_resolved"):
            return

        state = ctx.state
        attacker = ctx.actor
        target = ctx.target
        
        if not attacker or not target:
            return
            
        attacker_loc = state.unit_locations.get(attacker.id)
        target_loc = state.unit_locations.get(target.id)
        
        if not attacker_loc or not target_loc:
            return
            
        direction = attacker_loc.direction_to(target_loc)
        if direction is None: return 
        
        current_hex = target_loc
        candidates = []
        
        for _ in range(self.distance):
            current_hex = current_hex.neighbor(direction)
            for uid, loc in state.unit_locations.items():
                if loc == current_hex:
                    unit = state.get_unit(uid)
                    if unit and unit.team != attacker.team:
                         if hasattr(unit, 'hand'):
                             candidates.append(unit)
                             # Text: "Up to 1 enemy hero in ANY of the X spaces..."
                             # This implies we look at all eligible spaces and choose 1 hero from ALL found.
        
        if not candidates:
            return
            
        if not candidates:
            return
            
        # Always request choice to support "Up to 1" (Optional)
        req_id = str(uuid.uuid4())
        candidate_ids = [u.id for u in candidates]
        req = InputRequest(
            id=req_id,
            player_id=ctx.actor.id,
            request_type=InputRequestType.SELECT_UNIT,
            context={
                "criteria": "specific_units",
                "unit_ids": candidate_ids,
                "reason": f"Select hero to discard via {ctx.card.name}",
                "can_skip": True
            }
        )
        ctx.state.input_stack.append(req)
        ctx.card.metadata["waiting_for_discard_target"] = True
        # AttackCommand will detect stack change and interrupt.

    def on_post_action(self, ctx: EffectContext) -> None:
        if ctx.card.metadata.get("waiting_for_discard_target"):
             target_id_str = ctx.data.get("input_unit_id")
             
             if target_id_str == "SKIP":
                 print(f"   [Effect] {self.id} skipped by user.")
             elif target_id_str:
                 target_hero = ctx.state.get_hero(HeroID(target_id_str))
                 if target_hero:
                     self._apply_discard(target_hero, ctx.state, killer_id=ctx.actor.id)
                     print(f"   [Effect] {self.id} hits chosen {target_hero.name}!")
             
             ctx.card.metadata["discard_resolved"] = True
             ctx.card.metadata["waiting_for_discard_target"] = False
             return
             
        if self.repeat:
             repeat_count = ctx.card.metadata.get("repeat_count", 0)
             if repeat_count < 1:
                  print(f"   [Effect] {ctx.card.name} REPEATS!")
                  
                  # Mark metadata for next run
                  ctx.card.metadata["repeat_count"] = repeat_count + 1
                  
                  # New Standardized Repeat Logic
                  ctx.card.metadata["forced_action"] = ctx.card.primary_action
                  
                  # Exclude current target
                  excluded = ctx.card.metadata.get("excluded_targets", [])
                  target_id = ctx.card.metadata.get("target_unit_id") # Set by AttackCommand
                  if target_id:
                       excluded.append(target_id)
                  ctx.card.metadata["excluded_targets"] = excluded

                  # Reset state for fresh execution
                  ctx.card.metadata["discard_resolved"] = False
                  ctx.card.metadata["target_unit_id"] = None
                  
                  # Re-insert at head
                  ctx.state.resolution_queue.insert(0, (ctx.actor.id, ctx.card))
        
    def _apply_discard(self, hero, state=None, killer_id=None):
        if hero.hand:
            discarded = hero.hand.pop(0)
            discarded.state = "DISCARD"
            hero.discard_pile.append(discarded)
            print(f"   {hero.name} discarded {discarded.name}")
        else:
            print(f"   {hero.name} has no cards -> Defeated!")
            if state:
                defeat_unit(state, hero.id, killer_id=killer_id)

# Register Instances
EffectRegistry.register_instance(DiscardBehindEffect("effect_attack_discard_behind_repeat", 5, True))
EffectRegistry.register_instance(DiscardBehindEffect("effect_attack_discard_behind", 2, False))


# =========================================================================
# Ebb and Flow / Arcane Whirlpool
# =========================================================================

@EffectRegistry.register
class EbbAndFlowEffect(Effect):
    @property
    def id(self) -> str:
        return "effect_swap_enemy_minion_repeat"

    def on_pre_action(self, ctx: EffectContext) -> None:
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
        # Note: Skills already use `ResolveSkillCommand` which handles stack, so no explicit interrupt logic needed here 
        # because Skill is the primary action and ResolveSkillCommand loops.

    def on_post_action(self, ctx: EffectContext) -> None:
        target_id_str = ctx.data.get("input_unit_id")
        if not target_id_str: return
            
        target_id = UnitID(target_id_str)
        target_unit = ctx.state.get_unit(target_id)
        if not target_unit: return
            
        actor_loc = ctx.state.unit_locations.get(ctx.actor.id)
        target_loc = ctx.state.unit_locations.get(target_id)
        
        ctx.state.move_unit(ctx.actor.id, target_loc)
        ctx.state.move_unit(target_id, actor_loc)
        print(f"   [Effect] Swapped {ctx.actor.name} with {target_unit.name}")

# =========================================================================
# Liquid Leap
# =========================================================================

@EffectRegistry.register
class LiquidLeapEffect(Effect):
    @property
    def id(self) -> str:
        return "effect_teleport_strict"

    def on_pre_action(self, ctx: EffectContext) -> None:
        req_id = str(uuid.uuid4())
        req = InputRequest(
            id=req_id,
            player_id=ctx.actor.id,
            request_type=InputRequestType.SELECT_HEX,
            context={
                "constraint": "no_spawn_point_no_adj_spawn",
                "range": ctx.card.range_value
            }
        )
        ctx.state.input_stack.append(req)

    def on_post_action(self, ctx: EffectContext) -> None:
        target_hex = ctx.data.get("input_hex")
        if target_hex:
            ctx.state.move_unit(ctx.actor.id, target_hex)
            print(f"   [Effect] Liquid Leap to {target_hex}")

# =========================================================================
# Aspiring Duelist
# =========================================================================

@EffectRegistry.register
class AspiringDuelistEffect(Effect):
    @property
    def id(self) -> str:
        return "effect_ignore_minion_defense"

    def modify_defense_components(self, components: dict[str, int], ctx: EffectContext) -> None:
        if "auras" in components:
            print("   [Effect] Aspiring Duelist ignores minion defense aura")
            components["auras"] = 0

# =========================================================================
# Noble Blade
# =========================================================================

@EffectRegistry.register
class NobleBladeEffect(Effect):
    @property
    def id(self) -> str:
        return "effect_attack_move_ally"

    def on_pre_action(self, ctx: EffectContext) -> None:
        if ctx.card.metadata.get("noble_blade_resolved"): return

        target = ctx.target
        if not target: return
        
        target_loc = ctx.state.unit_locations.get(target.id)
        if not target_loc: return

        candidates = []
        for adj in target_loc.neighbors():
             if adj in ctx.state.unit_locations.values():
                 for uid, loc in ctx.state.unit_locations.items():
                     if loc == adj:
                         u = ctx.state.get_unit(uid)
                         if u and u.id != ctx.actor.id: #another unit
                             candidates.append(u)
        
        if candidates:
             req_id = str(uuid.uuid4())
             candidate_ids = [u.id for u in candidates]
             req = InputRequest(
                id=req_id,
                player_id=ctx.actor.id,
                request_type=InputRequestType.SELECT_UNIT,
                context={
                    "criteria": "specific_units",
                    "unit_ids": candidate_ids,
                    "reason": "Select unit to move (Noble Blade)"
                }
             )
             ctx.state.input_stack.append(req)
             ctx.card.metadata["noble_blade_step"] = "select_unit"
        else:
             ctx.card.metadata["noble_blade_resolved"] = True

    def on_post_action(self, ctx: EffectContext) -> None:
        step = ctx.card.metadata.get("noble_blade_step")
        print(f"DEBUG: NobleBlade PostAction. Step: {step}. Input: {ctx.data.get('input_unit_id')}")
        
        if step == "select_unit":
             unit_id_str = ctx.data.get("input_unit_id")
             if unit_id_str:
                 # Push Next Request: Move Hex
                 ctx.card.metadata["selected_unit_id"] = unit_id_str
                 req = InputRequest(
                    id=str(uuid.uuid4()),
                    player_id=ctx.actor.id, 
                    request_type=InputRequestType.SELECT_HEX,
                    context={
                        "unit_id": unit_id_str, # Unit to move
                        "range": 1,
                        "reason": "Select destination for unit"
                    }
                 )
                 ctx.state.input_stack.append(req)
                 ctx.card.metadata["noble_blade_step"] = "select_hex"
             else:
                 ctx.card.metadata["noble_blade_resolved"] = True

        elif step == "select_hex":
             hex_val = ctx.data.get("input_hex")
             unit_id_str = ctx.card.metadata.get("selected_unit_id")
             
             if hex_val and unit_id_str:
                 target_uid = UnitID(unit_id_str)
                 u_loc = ctx.state.unit_locations.get(target_uid)
                 
                 if u_loc and validate_movement_path(ctx.state.board, ctx.state.unit_locations, u_loc, hex_val, 1):
                      ctx.state.move_unit(target_uid, hex_val)
                      print(f"   [Effect] Noble Blade moved {unit_id_str} to {hex_val}")
                 else:
                      print(f"   [Effect] Noble Blade move INVALID/BLOCKED to {hex_val}")
             
             ctx.card.metadata["noble_blade_resolved"] = True
             ctx.card.metadata["noble_blade_step"] = None
             ctx.card.metadata["selected_unit_id"] = None

# =========================================================================
# Spell Break
# =========================================================================
# MVP Stub: Requires Marker System or Status Effect System
@EffectRegistry.register
class SpellBreakEffect(Effect):
    @property
    def id(self) -> str:
        return "effect_silence_heroes_radius"
        
    def on_pre_action(self, ctx: EffectContext) -> None:
        radius = ctx.card.radius_value or 2 # Default to 2 if not set
        
        actor_loc = ctx.state.unit_locations.get(ctx.actor.id)
        if not actor_loc: return

        print(f"   [Effect] Spell Break: Applying SILENCE (Radius {radius})")
        
        for uid, loc in ctx.state.unit_locations.items():
            if uid == ctx.actor.id: continue
            
            dist = actor_loc.distance(loc)
            if dist <= radius:
                unit = ctx.state.get_unit(uid)
                if unit and unit.team != ctx.actor.team:
                    if hasattr(unit, 'hand'): # Duck type Hero
                        if not any(m.name == "SILENCE" for m in unit.markers):
                            m = Marker(id=str(uuid.uuid4()), name="SILENCE")
                            unit.markers.append(m)
                            print(f"   Applied SILENCE to {unit.name}")
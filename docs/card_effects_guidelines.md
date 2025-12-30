# Card Effects Implementation Guidelines

This guide explains how to implement card effects following GoA2's mandatory/optional step rules.

## Core Rule

> When performing a primary action the card text must be applied in exact order. If you cannot complete a mandatory step, stop and skip remaining steps.

## Mandatory vs Optional Steps

| Text Pattern | Mandatory | Example |
|-------------|-----------|---------|
| Direct instructions | ✅ Yes | "Move 2 spaces" |
| "you may" | ❌ No | "You may move 1 space" |
| "up to" | ❌ No | "Push up to 2 spaces" |
| "if able" | ❌ No | "Deal damage, if able" |

## Implementation Pattern

### Default (Mandatory)
```python
@register_effect("effect_attack_then_move")
class AttackThenMoveEffect(CardEffect):
    def get_steps(self, state, hero, card):
        return [
            # Mandatory attack - if no target, abort action
            SelectStep(
                target_type="UNIT",
                prompt="Select target",
                filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
                is_mandatory=True  # Default, explicit for clarity
            ),
            AttackSequenceStep(damage=card.primary_action_value),
            # Mandatory move after attack
            MoveUnitStep(unit_id=hero.id, range_val=1)
        ]
```

### Optional Step
```python
@register_effect("effect_optional_push")
class OptionalPushEffect(CardEffect):
    """Card text: 'Attack. You may push target up to 2 spaces.'"""
    def get_steps(self, state, hero, card):
        return [
            SelectStep(...),
            AttackSequenceStep(...),
            # "You may" = optional
            PushUnitStep(target_id=..., distance=2, is_mandatory=False)
        ]
```

## Abort Behavior

> **Key Insight:** Abort only triggers when **no valid options exist**, not when an invalid option is chosen. `SelectStep` ensures players only see valid options.

### When Abort Triggers (SelectStep)
```
SelectStep has no valid candidates?
├── is_mandatory=True
│   └── Return StepResult(abort_action=True)
│       └── Engine aborts, skips to FinalizeHeroTurnStep
└── is_mandatory=False
    └── Return StepResult(is_finished=True)
        └── Continue to next step (skip this selection)
```

### Invalid Input is an Error, Not Abort
If a player somehow provides an invalid input (e.g., hex out of range), subsequent steps like `MoveUnitStep` treat this as an **error** - log it and continue. This should rarely happen because `SelectStep` filters ensure only valid options are presented.

## Parsing Card Text

When implementing a card effect, parse the text for optional keywords:

```python
def parse_is_mandatory(text_segment: str) -> bool:
    """Check if a segment of card text is mandatory."""
    optional_keywords = ["you may", "up to", "if able"]
    text_lower = text_segment.lower()
    return not any(kw in text_lower for kw in optional_keywords)
```

## Example: Complex Card

**Card Text:** "Move 2 spaces. Attack an adjacent enemy. You may push target up to 3 spaces."

```python
@register_effect("effect_dash_attack_push")
class DashAttackPushEffect(CardEffect):
    def get_steps(self, state, hero, card):
        return [
            # "Move 2 spaces" - mandatory
            SelectStep(target_type="HEX", ..., is_mandatory=True),
            MoveUnitStep(range_val=2, is_mandatory=True),
            
            # "Attack an adjacent enemy" - mandatory
            SelectStep(target_type="UNIT", ..., is_mandatory=True),
            AttackSequenceStep(damage=card.primary_action_value),
            
            # "You may push target up to 3 spaces" - optional
            PushUnitStep(target_id=..., distance=3, is_mandatory=False)
        ]
```

from goa2.domain.models import TargetType
from goa2.engine.filters_units import ExcludeIdentityFilter
from goa2.engine.steps import AttackSequenceStep, PerformPrimaryActionStep, SelectStep


def test_perform_primary_action_exclusion_is_injected_into_unit_targets() -> None:
    attack = AttackSequenceStep(damage=3, range_val=1)
    unit_select = SelectStep(
        target_type=TargetType.UNIT,
        prompt="Select unit",
        output_key="unit_id",
    )
    hex_select = SelectStep(
        target_type=TargetType.HEX,
        prompt="Select hex",
        output_key="hex",
    )

    PerformPrimaryActionStep._inject_exclusion_filter(
        [attack, unit_select, hex_select],
        "blocked_target",
    )

    attack_exclusions = [f for f in attack.target_filters if isinstance(f, ExcludeIdentityFilter)]
    select_exclusions = [f for f in unit_select.filters if isinstance(f, ExcludeIdentityFilter)]

    assert attack_exclusions
    assert attack_exclusions[0].exclude_keys == ["blocked_target"]
    assert select_exclusions
    assert select_exclusions[0].exclude_keys == ["blocked_target"]
    assert not hex_select.filters

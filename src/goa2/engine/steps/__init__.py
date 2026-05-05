"""Step implementations and compatibility exports.

The public ``goa2.engine.steps`` import path is intentionally preserved while
step classes are exposed through focused submodules for new code.
"""

from goa2.engine.steps._legacy import *
from goa2.engine.steps._legacy import __all__ as _legacy_all
from goa2.domain.models import TargetType

__all__ = list(_legacy_all)
if "TargetType" not in __all__:
    __all__.append("TargetType")

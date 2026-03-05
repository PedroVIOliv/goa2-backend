from .registry import HeroRegistry

# Import modules to register them (side effects only)
# ruff: noqa: F401
import goa2.data.heroes.arien
import goa2.data.heroes.xargatha
import goa2.data.heroes.wasp
import goa2.data.heroes.brogan

__all__ = ["HeroRegistry"]

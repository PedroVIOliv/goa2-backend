from .registry import HeroRegistry

# Import modules to register them (side effects only)
# ruff: noqa: F401
import goa2.data.heroes.arien
import goa2.data.heroes.xargatha
import goa2.data.heroes.wasp
import goa2.data.heroes.brogan
import goa2.data.heroes.tigerclaw
import goa2.data.heroes.sabina
import goa2.data.heroes.dodger
import goa2.data.heroes.bain
import goa2.data.heroes.whisper
import goa2.data.heroes.rowenna

__all__ = ["HeroRegistry"]

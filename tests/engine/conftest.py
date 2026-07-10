"""Make the repo root importable so tests here can do `from tests.engine...`.

`tests/engine` has no `__init__.py` (project convention: most test dirs
aren't packages), so pytest's default "prepend" import mode inserts this
directory itself onto sys.path rather than walking up to the repo root. That
means `from tests.engine.effects.builders import EffectScenarioBuilder`
(needed to reuse the shared scenario builder) can't resolve without a nudge
for test modules that live directly in `tests/engine/` (as opposed to a
subdirectory like `tests/engine/pieces`, which already has its own copy of
this nudge). Insert the repo root here so `tests` resolves as an implicit
namespace package, without touching the no-`__init__.py` convention for
sibling dirs.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# `AnyMiscEntity`/`AnyStep` (used by GameState.model_dump_json /
# model_validate_json) are patched onto GameState as an import side effect of
# goa2.engine.step_types (see rebuild_serialization_models()). That module is
# normally pulled in transitively via goa2.engine.handler. Import it here so
# persistence round-trip tests in this directory work in isolation, not just
# when collected alongside other tests that happen to import handler first.
import goa2.engine.handler  # noqa: E402, F401

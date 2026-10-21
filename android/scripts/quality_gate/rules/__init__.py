"""Rule discovery.

Importing a rule module runs its ``@register`` decorator, adding the rule to the
registry. To enable a new rule, add one import line here (and enable it in the
config). ``_template`` is intentionally NOT imported — it is a copy-paste
starting point, not a live rule.
"""

from . import coverage  # noqa: F401
from . import layering  # noqa: F401
from . import no_comments  # noqa: F401

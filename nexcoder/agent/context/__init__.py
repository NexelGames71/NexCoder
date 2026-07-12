"""Context-builder subpackage.

Public entry points:

- :class:`nexcoder.agent.context_builder.ContextBuilder` — the original
  character-bounded builder. Kept for backward compatibility with
  existing tests and the legacy path.
- :class:`nexcoder.agent.context.token_builder.TokenAwareContextBuilder`
  — the production builder with a token budget, priority packing, and
  per-block caps.

New code should use :class:`TokenAwareContextBuilder`.
"""

from nexcoder.agent.context_builder import ContextBuilder
from nexcoder.agent.context.token_builder import TokenAwareContextBuilder

__all__ = ["ContextBuilder", "TokenAwareContextBuilder"]
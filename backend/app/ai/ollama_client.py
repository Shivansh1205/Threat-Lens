"""Compatibility boundary for the configured external LLM provider.

The module name remains temporarily stable for existing imports and tests;
the implementation is now the provider-neutral OpenAI-compatible client.
"""

from app.ai.llm_client import generate, generate_grounded

__all__ = ["generate", "generate_grounded"]

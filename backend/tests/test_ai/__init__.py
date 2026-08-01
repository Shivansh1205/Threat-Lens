"""Tests for the Phase 6 AI/explainability layer.

None of these tests require a real running Ollama instance — every test
mocks at the ``app.ai.ollama_client.generate`` boundary (or, for
test_ollama_client.py itself, at the ``httpx.AsyncClient`` layer one level
below it). CI and most dev machines have no Ollama process, so this is a
hard requirement, not just a nicety.
"""

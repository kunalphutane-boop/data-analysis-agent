"""Pricing math tests — no LLM key required."""
from llm import pricing


def test_known_model_cost():
    # gemini-2.0-flash: $0.10/1M in, $0.40/1M out
    cost = pricing.cost_usd("gemini-2.0-flash", 1_000_000, 1_000_000)
    assert cost == round(0.10 + 0.40, 8)


def test_partial_tokens():
    cost = pricing.cost_usd("gemini-2.0-flash", 500_000, 250_000)
    expected = round(0.5 * 0.10 + 0.25 * 0.40, 8)
    assert cost == expected


def test_zero_tokens_zero_cost():
    assert pricing.cost_usd("gemini-2.5-flash", 0, 0) == 0.0


def test_unknown_model_uses_fallback_nonzero():
    cost = pricing.cost_usd("some-unknown-model", 1_000_000, 0)
    assert cost > 0


def test_gemini_25_flash_present():
    assert "gemini-2.5-flash" in pricing.PRICING

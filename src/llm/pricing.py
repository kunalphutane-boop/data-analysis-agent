"""Model -> USD-per-1M-token pricing and per-run cost computation.

Rates are (input_usd_per_1M, output_usd_per_1M). Used by the graph's `finalize`
node to turn accumulated token counts into `cost_usd` for the /ask response and
the persisted `messages` row.
"""

# (input $/1M tokens, output $/1M tokens)
PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-001": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-flash-latest": (0.30, 2.50),
}

# Used when a model id is unknown so cost is still non-zero and sane.
_FALLBACK = (0.30, 2.50)


def rates_for(model: str) -> tuple[float, float]:
    return PRICING.get(model, _FALLBACK)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = rates_for(model)
    cost = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
    return round(cost, 8)

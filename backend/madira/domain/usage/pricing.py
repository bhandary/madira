"""Estimated model prices for the venue's own key.

Amounts are micro-dollars per million tokens (1 dollar = 1_000_000). They are
a config table, not an invoice, a plan, or a payment. Demo mode does not use
them: that cost is zero.
"""

from __future__ import annotations

# input, output. Unknown live models use DEFAULT.
PRICES: dict[str, tuple[int, int]] = {
    "gpt-4.1-mini": (400_000, 1_600_000),
    "gpt-4.1": (2_000_000, 8_000_000),
    "claude-haiku-4-5-20251001": (1_000_000, 5_000_000),
    "gemini-3.5-flash": (150_000, 600_000),
    "madira-demo-fixtures": (0, 0),
}
DEFAULT_PRICE = (1_000_000, 4_000_000)


def estimate_cost(model: str, tokens_in: int, tokens_out: int, *, demo: bool) -> tuple[int, str]:
    """Return ``(micro_dollars, label)``. Demo is always ``(0, "demo")``."""

    if demo:
        return 0, "demo"
    incoming = max(int(tokens_in), 0)
    outgoing = max(int(tokens_out), 0)
    rate_in, rate_out = PRICES.get((model or "").strip(), DEFAULT_PRICE)
    micro = (incoming * rate_in + outgoing * rate_out) // 1_000_000
    return micro, "estimate"

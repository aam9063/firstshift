"""Price table for eval cost accounting (T3, S5).

Spec source: specs/05-iteration-evals.md section 2, row 6: "Tokens and USD per
hired candidate, p95 response latency. From LLM call logs."

The table is USD per 1M tokens (input, output), list prices for the OpenAI
models the project may run through settings.openai_model. The scripted model
used by the deterministic eval harness has no real API cost; it is priced at
the ``PROXY_MODEL`` rate so the baseline report still shows a comparable
estimate, and the report labels it as a proxy.

Prices are public OpenAI list prices for gpt-4.1-mini and gpt-4.1 (April
2025 price list) and o4-mini; update the table when models change.
"""

from __future__ import annotations

# model name -> (input USD per 1M tokens, output USD per 1M tokens)
PRICES_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "o4-mini": (1.10, 4.40),
}

# The scripted eval model is priced at this real model's rate (documented
# proxy: the baseline cost is an estimate, not a bill).
PROXY_MODEL = "gpt-4.1-mini"

# Models with no entry fall back to the proxy rate instead of failing the
# whole suite over a pricing gap; add the model to PRICES_PER_1M to price it
# exactly.
DEFAULT_MODEL = PROXY_MODEL


def price_for(model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens for one model name."""
    return PRICES_PER_1M.get(model, PRICES_PER_1M[DEFAULT_MODEL])


def usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of one model call with the given token counts."""
    input_rate, output_rate = price_for(model)
    return input_tokens / 1e6 * input_rate + output_tokens / 1e6 * output_rate

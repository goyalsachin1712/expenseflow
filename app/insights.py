"""Generate short natural-language spending insights from expense records via Claude."""

import logging
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
FALLBACK_MESSAGE = "Insights are unavailable right now. Please try again later."


def _summarize_expenses(expenses: list[dict]) -> str:
    """Build a compact text summary of expenses for the prompt."""
    lines = [
        f"- {expense.get('amount_base_minor')} minor units, "
        f"category={expense.get('category')}, status={expense.get('status')}"
        for expense in expenses
    ]
    return "\n".join(lines)


def generate_insight(expenses: list[dict]) -> str:
    """Ask Claude for three short bullet insights about the given expenses.

    Each dict in `expenses` is expected to have `amount_base_minor`, `category`,
    and `status` keys. Returns a safe fallback string if the API call fails.
    """
    summary = _summarize_expenses(expenses)
    prompt = (
        "Here is a list of expenses (amount in base currency minor units, "
        "category, and status):\n\n"
        f"{summary}\n\n"
        "Give exactly three short bullet-point insights about this spending."
    )

    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return next((block.text for block in response.content if block.type == "text"), FALLBACK_MESSAGE)
    except anthropic.APIError as e:
        logger.error("Anthropic API error while generating insights: %s", e)
        return FALLBACK_MESSAGE

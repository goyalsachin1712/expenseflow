# 1. Store money as integer minor units

## Status

Accepted. In force since the first version of `app/models.py` (`amount_minor`, `amount_base_minor` are both `Mapped[int]`), and codified as a project convention in `CLAUDE.md`: "Money is stored as integer minor units (paise / cents), never float."

## Context

Every expense has a submitted amount and, once normalized, a base-currency amount. Both need to be stored, transmitted over JSON, summed for reports, and displayed back to a user. We needed one representation used consistently everywhere — schema, API payloads, and UI — rather than deciding per call site.

## Decision

Represent every monetary amount as a plain integer count of the currency's minor unit (paise for INR, cents for USD, etc.) — e.g. ₹1.00 is stored and transmitted as `100`, never as `1.0` or `1.00`. This applies to `amount_minor` and `amount_base_minor` on the `Expense` model, to the `ExpenseCreate` request schema, and to every response. Converting to/from a human-readable decimal amount (dividing or multiplying by 100) happens only at the edges — user input parsing and display — never in storage or in business logic.

## Alternatives considered

- **Float, in major units** (e.g. store `1.0` for ₹1). Rejected outright: binary floating point can't represent most decimal fractions exactly, so repeated arithmetic (summing many expenses, applying an FX rate) accumulates rounding error. This is the one option `CLAUDE.md` explicitly rules out.
- **`Decimal`, in major units** (e.g. store `Decimal("1.00")`). Avoids the binary rounding problem, but SQLite has no native decimal column type — a `Decimal` would have to round-trip through `TEXT` or `REAL` at the storage layer, and `Decimal` isn't JSON-serializable by default, so every API boundary (pydantic response models, the Streamlit UI's `httpx` calls) would need explicit encode/decode handling. More moving parts, for a PoC, than the problem justifies.
- **Integer minor units** (chosen). Every value is a plain integer: exact arithmetic, trivial to store in a SQLite `INTEGER` column, trivial to serialize as JSON, and it's what most payment APIs (Stripe, etc.) do for the same reason.

## Consequences

- Arithmetic (summing, comparing, checking `amount_minor > 0`) is exact — no rounding-error class of bug is possible in storage or business logic.
- Every place that accepts or displays a human-typed decimal amount must explicitly convert, and that conversion is easy to get wrong or forget. This already happened once in this codebase: the Streamlit "Existing expenses" table originally rendered the raw `amount_minor`/`amount_base_minor` integers straight from the API response, so a ₹1 expense showed as `100` in the UI. The fix was adding an explicit `/ 100` step in `ui/app.py` before display — the convention didn't cause a wrong *value* anywhere (the stored data was always correct), but it does mean every new display or input surface has to remember this step, and forgetting it fails silently (wrong by a factor of 100) rather than raising an error.
- The current implementation assumes a fixed exponent of 100 minor units per major unit for *all* currencies (see `int(round(amount * 100))` in `ui/app.py`, and the `ExpenseCreate.amount_minor` contract in `app/schemas.py`). That's correct for INR and USD but wrong for currencies with a different minor-unit exponent — e.g. JPY (0 decimal places) or KWD (3 decimal places). This ADR covers the decision to use integer minor units; it does not cover per-currency exponents, which aren't handled anywhere in the code today.
- Input validation must round deliberately (not truncate) when converting a decimal amount to minor units, and should reject non-positive amounts before they reach storage — `ExpenseCreate.amount_minor` already enforces `> 0` via `Field(gt=0)`.

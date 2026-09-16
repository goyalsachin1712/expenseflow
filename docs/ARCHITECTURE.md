# ExpenseFlow — Architecture

PoC expense submission and approval API per `CLAUDE.md`. One user journey: submit an expense, convert it to base currency (INR), approve or reject it.

**Assumptions:**
- FX rate is fetched live via `httpx` at submission time (no caching) — simplest behavior for a PoC with one rate call per submission.
- Approve/reject is a single-step transition (`PENDING → APPROVED/REJECTED`); no multi-level workflow, no auth/roles.

---

## 1. SQLite schema — `expenses` table

```sql
CREATE TABLE expenses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    description         TEXT NOT NULL,
    amount_minor         INTEGER NOT NULL,
    currency             TEXT NOT NULL,
    category             TEXT NOT NULL,
    submitted_by         TEXT NOT NULL,
    amount_base_minor    INTEGER NOT NULL,
    base_currency        TEXT NOT NULL DEFAULT 'INR',
    fx_rate              REAL NOT NULL,
    fx_rate_fetched_at   TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'PENDING',
    created_at           TEXT NOT NULL,
    decided_at           TEXT,
    decision_note        TEXT
);
```

| Column | Type | Why |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Stable surface identifier used in route paths. |
| `description` | `TEXT NOT NULL` | Free-text reason for the expense; required so approvers have context. |
| `amount_minor` | `INTEGER NOT NULL` | Original submitted amount in integer minor units (paise/cents) — money is never float, per convention. Kept separate from the base amount so the original submission survives even if FX rates or base-currency policy change later. |
| `currency` | `TEXT NOT NULL` | ISO 4217 code of the *submitted* currency. Needed to interpret `amount_minor` and audit the conversion. |
| `category` | `TEXT NOT NULL` | Free-text expense category (e.g. "Travel", "Meals"), for reporting/filtering. |
| `submitted_by` | `TEXT NOT NULL` | Identifier of the person who submitted the expense. |
| `amount_base_minor` | `INTEGER NOT NULL` | Normalized amount in INR minor units, computed at submission time. This is the field approval/reporting logic reads — amounts are normalised to base on write. |
| `base_currency` | `TEXT NOT NULL DEFAULT 'INR'` | Stored explicitly so historical rows stay self-describing if the base-currency policy ever changes. |
| `fx_rate` | `REAL NOT NULL` | Exact rate used for the conversion, stored for audit/reproducibility. `REAL` is fine here — it's a rate, not a stored monetary value; the money itself is the integer `amount_base_minor`. |
| `fx_rate_fetched_at` | `TEXT NOT NULL` (ISO 8601) | When the rate was fetched, for staleness reasoning later. |
| `status` | `TEXT NOT NULL DEFAULT 'PENDING'` | One of `PENDING`, `APPROVED`, `REJECTED`; validated at the app level (pydantic/Enum) since SQLite has no native enum type. |
| `created_at` | `TEXT NOT NULL` (ISO 8601) | Creation timestamp, for ordering and audit trail. |
| `decided_at` | `TEXT` (nullable) | Set when status leaves `PENDING`; `NULL` while pending. |
| `decision_note` | `TEXT` (nullable) | Optional free-text reason from the approver, especially useful on rejection. |

No separate `currencies` or `fx_rates` table — out of scope for a PoC with one external rate call per submission.

---

## 2. Endpoints

### `POST /expenses`
Submit a new expense; converts to base currency (INR) via the FX provider and persists.

**Request body:**
```json
{ "description": "Client dinner", "amount_minor": 450000, "currency": "USD", "category": "Meals", "submitted_by": "alice@example.com" }
```

**Response `201`:**
```json
{
  "id": 1,
  "description": "Client dinner",
  "amount_minor": 450000,
  "currency": "USD",
  "category": "Meals",
  "submitted_by": "alice@example.com",
  "amount_base_minor": 3735000,
  "base_currency": "INR",
  "fx_rate": 83.0,
  "fx_rate_fetched_at": "2026-09-10T09:00:00Z",
  "status": "PENDING",
  "created_at": "2026-09-10T09:00:00Z",
  "decided_at": null,
  "decision_note": null
}
```
Errors: `422` (invalid currency code / non-positive amount), `502` (FX provider unreachable or returned no rate for the currency).

### `GET /expenses/{id}`
Fetch a single expense by id.

**Response `200`:** same shape as above. `404` if not found.

### `GET /expenses`
List expenses, optionally filtered by status and/or category.

**Query params:** `status` (optional: `PENDING` | `APPROVED` | `REJECTED`), `category` (optional)

**Response `200`:** JSON array of the same expense object shape.

### `POST /expenses/{id}/approve`
Approve a pending expense.

**Request body (optional):**
```json
{ "note": "Within policy limit" }
```

**Response `200`:** the updated expense object (`status`, `decided_at`, `decision_note` set).

Errors: `404` if not found, `409` if the expense is not currently `PENDING` (no re-deciding an already-decided expense).

### `POST /expenses/{id}/reject`
Reject a pending expense. Same request/response shape as `approve`, with `status` set to `REJECTED`.

Errors: same as `approve`.

No `DELETE` or `PUT` endpoints — not in the brief.

---

## 3. File layout

```
app/
  main.py     — FastAPI app instance, startup (create tables), router registration
  db.py       — SQLAlchemy engine/session setup for expenseflow.db, get_db dependency
  models.py   — SQLAlchemy ORM model: Expense
  schemas.py  — pydantic v2 models: ExpenseCreate, ExpenseOut, DecisionIn
  routes.py   — the 5 endpoints above; calls into fx.py for the rate lookup
  fx.py       — thin httpx wrapper: get_rate(from_currency, to_currency) -> (rate, fetched_at); reads FX provider URL/key from env via python-dotenv
tests/
  test_expenses.py — submit/list/get/decision flow, using a temp SQLite DB
.env.example  — documents required env vars (FX provider URL/key) without values
requirements.txt — fastapi, uvicorn, sqlalchemy, httpx, pydantic, python-dotenv, pytest
```

Note: `fx.py` is one file beyond the layout listed in `CLAUDE.md` (`main.py, db.py, models.py, schemas.py, routes.py`). Keeping the httpx call isolated here avoids mixing HTTP-client concerns into `routes.py`; folding it into `routes.py` instead would stay strictly within the stated file list at the cost of that separation.

---

## 4. Edge cases and how the design handles them

1. **FX provider is down or returns no rate for the submitted currency.**
   Conversion happens synchronously on write, and `amount_base_minor` is `NOT NULL`, so a failed FX call must reject the submission outright. `routes.py` catches `httpx` errors / missing-rate responses and returns `502` before any DB insert — no row is ever created with a missing or fabricated base amount.

2. **Rounding when converting to minor units.**
   `amount_base_minor = round(amount_minor * fx_rate)` can drift due to floating-point rate multiplication. The conversion helper rounds to the nearest integer explicitly (never truncates), and the exact `fx_rate` used is stored alongside the result — so any discrepancy is auditable/reproducible rather than silently drifting.

3. **Double-deciding an expense (race or duplicate approve/reject calls).**
   Two concurrent `PATCH .../decision` calls (or a retried request) could both try to transition the same `PENDING` row. The update is a conditional write (`UPDATE ... WHERE id = ? AND status = 'PENDING'`); if zero rows are affected, the endpoint returns `409 Conflict` instead of silently overwriting a prior decision. This makes the transition atomic at the DB level rather than relying on a read-then-write check in Python.

---

## Verification (once implemented)
- `python -m pytest -q` — cover: submit with valid currency, submit with FX provider mocked to fail (expect `502`, no row persisted), decide a pending expense (expect `200` + status change), decide an already-decided expense (expect `409`), get/list filtering by status.
- Manual: `python -m uvicorn app.main:app --reload`, then exercise all 4 endpoints via `curl` or FastAPI's `/docs` Swagger UI.

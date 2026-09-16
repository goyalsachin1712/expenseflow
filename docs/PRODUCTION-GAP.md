# ExpenseFlow — Production Readiness Gap Analysis

This audits the code as it exists today in `app/` and `ui/` against a production bar.
Every gap below was verified against the actual source (grepped for auth/middleware/
logging/rate-limiting, read `app/schemas.py`, `app/db.py`, `app/routes.py`,
`app/insights.py`, and checked `git log` / the filesystem for tests, migrations, and
CI) — nothing here is inferred from `docs/ARCHITECTURE.md`'s intended design or from
`steps.md`.

**Classification key:**
- **Blocking** — should not ship to production (or to real user/spend data) without this.
- **Deferrable** — acceptable to launch without, but should be scheduled soon after.

**Effort key:** S = hours, M = 1–5 engineer-days, L = 1–2 engineer-weeks, XL = multi-week.

---

## 1. Authentication and key rotation

- **Gap:** No authentication or authorization exists on any endpoint. Every route in
  `app/routes.py` is reachable by anyone who can send an HTTP request — including
  `approve`/`reject`. `submitted_by` is a free-text string, not a verified identity,
  so it can't be used for access control or a trustworthy audit trail.
- **Gap:** No role separation — the same unauthenticated caller can submit an expense
  and immediately approve their own submission. There's no concept of "approver" vs
  "submitter."
- **Gap:** The only credential in the system, `ANTHROPIC_API_KEY`, has no rotation
  process — rotating it means manually editing `.env` and restarting the process on
  every host that runs it.

**Classification:** Blocking (identity + authorization; separation of duties).
**Effort:** M (3–5 days) for API-key or JWT auth end-to-end, including the Streamlit
UI's login flow. L (1–2 weeks) for real role-based access control with an audit
trail. S–M (1–2 days) for automated key rotation, if a secrets manager is already
available in the target environment.

---

## 2. Input validation

- **Gap:** `amount_minor` only enforces `> 0` (`app/schemas.py`) — there's no upper
  bound, so a data-entry typo (an extra zero) or a malicious value is accepted and
  stored without question.
- **Gap:** `description`, `category`, and `submitted_by` have no `max_length` — an
  arbitrarily long string is accepted and persisted.
- **Gap:** `currency` is checked to be 3 alphabetic characters but not checked
  against a real ISO 4217 list — `"ZZZ"` passes validation even though no real
  currency exists with that code. This is low-risk today only because FX conversion
  itself isn't implemented yet (see the note in `README.md`); it will matter once it is.
- **Gap:** No format constraint on `submitted_by` (not validated as an email or a
  real user id) and no allow-list on `category` — this is already visible in the live
  data as inconsistent casing (`"travel"` vs `"Travel"`, `"sachin"` vs `"Sachin"`).
- **Gap:** `DecisionIn.note` also has no length limit.

**Classification:** Deferrable on its own (none of these are exploitable without
another gap alongside them); becomes Blocking the moment this API sits behind a
public endpoint without a gateway-level body-size limit in front of it.
**Effort:** S (a few hours) — add `max_length`/bounds to the existing Pydantic
fields and a real ISO 4217 allow-list for `currency`.

---

## 3. Rate limiting

- **Gap:** None exists anywhere in the app — no middleware, no per-IP or per-key
  throttling, no request-size cap. A single caller can submit unlimited expenses, or
  call `GET /reports/insights` (which makes a paid, external Anthropic API call) as
  fast as the network allows.

**Classification:** Blocking before any deployment reachable by untrusted callers
(direct cost/abuse exposure via the insights endpoint); Deferrable for a
trusted-internal, VPN-only deployment.
**Effort:** S (a few hours–1 day) for an in-process limiter (e.g. `slowapi`) on the
write and insights endpoints. M (2–3 days) for a distributed (Redis-backed) limiter
if the app ever runs as more than one instance.

---

## 4. Observability and logging

- **Gap:** The entire codebase has exactly one log statement — `logger.error(...)` in
  `app/insights.py` — and no `logging.basicConfig` or handler setup anywhere, so its
  destination depends entirely on whatever the process supervisor happens to capture
  from stdout/stderr.
- **Gap:** No request logging (method, path, status, latency), no correlation/request
  IDs, no metrics endpoint, no tracing.
- **Gap:** `GET /reports/insights` fails *silently* from an operator's perspective —
  a failed Anthropic call returns `200` with a fixed fallback string, so nothing
  distinguishes "genuinely nothing interesting to report" from "this feature is
  broken in production" without reading application logs.

**Classification:** Blocking for anything you intend to operate and support past a
short demo.
**Effort:** S–M (1–2 days) for structured logging plus a request-logging middleware.
M (3–5 days) for metrics and dashboards, depending on the observability stack already
available in the target environment.

---

## 5. Error handling

- **Gap:** No custom exception handlers are registered on the FastAPI app
  (`app/main.py`) — an unhandled exception (e.g. a DB error) falls through to
  FastAPI's default handler: a generic `500` with no consistent error envelope and
  no logging of the underlying cause.
- **Gap:** As noted in §4, `/reports/insights` converts every failure into a fake
  `200` success with a fallback string — callers (including the UI) cannot tell a
  degraded response from a real one.
- **Gap:** No specific handling for a locked/unavailable SQLite file (a real failure
  mode for this datastore) — it would surface as an unhandled `500` with no useful
  message.

**Classification:** Deferrable for the generic-500 case (FastAPI's default is safe,
just uninformative). Blocking to fix the insights silent-failure if the feature is
ever relied on for real decisions rather than as a nice-to-have.
**Effort:** S (a few hours) for a global exception handler with a consistent error
envelope. S (a few hours) to make the insights failure mode honest (e.g. a
`degraded: true` field, or a `502`, instead of a disguised success).

---

## 6. Database migrations and pooling

- **Gap:** No migrations tool (no Alembic, no equivalent). `app/db.py`'s `init_db()`
  only runs `Base.metadata.create_all()`, which creates missing tables and never
  alters existing columns. There is currently no defined, repeatable process for
  evolving the schema against a live database.
- **Gap:** `create_engine` (`app/db.py`) only sets `connect_args={"check_same_thread":
  False}` — no pool sizing, timeout, or recycle configuration. This is largely moot
  for a single SQLite file, but there is no migration path defined for a pooled,
  concurrently-written database (e.g. Postgres) when that becomes necessary.
- **Gap:** SQLite is a single file (`expenseflow.db`) with no backup or
  point-in-time-recovery story — a lost or corrupted file loses all expense history
  permanently.

**Classification:** Blocking before any deployment where the schema is expected to
evolve, or where more than one instance might run concurrently. Deferrable only for a
single-instance deployment with a deliberately frozen schema.
**Effort:** S–M (1 day) to introduce Alembic against the current schema. M–L
(3–7 days) to migrate to a pooled database like Postgres, including data migration
and pool tuning.

---

## 7. Secrets management

- **Gap:** The only secret, `ANTHROPIC_API_KEY`, lives in a plaintext `.env` file at
  the project root, and **there is no `.gitignore` in the repo at all** — nothing
  currently stops that file (or `expenseflow.db`, or `.venv/`) from being committed
  by a `git add .` / `git add -A`. This is a live risk, not a theoretical one: `git
  status` currently shows `.env` sitting untracked and unexcluded.
- **Gap:** No secrets-manager or vault integration — rotating the key means manually
  editing `.env` on every host that runs the process.
- **Gap:** `load_dotenv()` is called independently in `app/insights.py` and
  `ui/app.py` rather than once centrally at startup — easy to forget when a new
  module later needs an env var.

**Classification:** Blocking — the missing `.gitignore` next to a real API key in the
working directory is an active leak risk today, independent of anything else in this
document.
**Effort:** S (under an hour) to add a `.gitignore` and confirm `.env` has never been
committed. S–M (1–2 days) to move the key into a real secrets manager, depending on
the target platform's SDK.

---

## 8. Tests and coverage

- **Gap:** There are zero test files in the repo — no `tests/` directory, no
  `test_*.py` modules, and no coverage tool (`pytest-cov` is not installed).
  `python -m pytest -q` currently reports `no tests ran`. `docs/ARCHITECTURE.md`
  describes an intended `tests/test_expenses.py` that was never written.
- **Gap:** No CI pipeline exists (no `.github/workflows` or equivalent) to run
  anything automatically on a change, so nothing today prevents a regression to the
  submit/approve/reject flow from shipping unnoticed.

**Classification:** Blocking — this is a money-adjacent approval workflow with
literally no automated verification that it works, today or after the next change.
**Effort:** M (2–4 days) for a first meaningful suite covering submit/list/get/
approve/reject happy paths plus the 404/409/422 error cases against a temp SQLite DB.
S (a few hours) to wire that suite into CI once it exists.

---

## 9. Deployment and health checks

- **Gap:** No `/health` or `/healthz` endpoint exists anywhere in `app/routes.py` —
  there is nothing for a load balancer or orchestrator to probe; `/docs` is the
  closest available substitute today.
- **Gap:** No Dockerfile, no process-manager config (Procfile, systemd unit, etc.),
  and no CI/CD pipeline — there is no defined, repeatable way to build or deploy this
  beyond running `uvicorn` by hand on a machine.
- **Gap:** No environment-based configuration — the DB path (`app/db.py`) and the
  insights model name (`app/insights.py`) are hardcoded Python constants, not
  environment-driven, so there's no clean way to point a staging deployment at a
  different DB or model without editing source.
- **Gap:** The single-SQLite-file design (§6) means this cannot be horizontally
  scaled without a datastore change first, which limits deployment topology options
  regardless of orchestration tooling chosen.

**Classification:** Blocking for any real deployment target — you can't safely wire
up automated rollout, rollback, or monitoring without at least a health check and a
repeatable build artifact.
**Effort:** S (under an hour) for a health endpoint. M (2–3 days) for a Dockerfile
plus a basic CI/CD pipeline, depending on the target platform.

---

## 10. Data privacy for expense data

- **Gap:** `submitted_by` and `description` are free-text fields that can contain
  personal or sensitive information (names, what money was spent on), stored in
  plaintext in SQLite with no field-level encryption. Combined with §1 (no auth),
  **anyone who can reach the API can read every submitter's name and full spending
  history** via `GET /expenses`.
- **Gap:** No data retention or deletion policy — there is no `DELETE` endpoint and
  no automated purge job, so expense data (including submitter names) accumulates
  indefinitely with no mechanism to honor a deletion request.
- **Gap:** No reliable audit trail of *who* approved or rejected an expense beyond
  the free-text, optional `decision_note` — there's no authenticated actor recorded
  against a decision (ties directly back to §1).
- **Positive finding:** the `/reports/insights` endpoint's summary
  (`app/insights.py`, `_summarize_expenses`) sends only `amount_base_minor`,
  `category`, and `status` to the Anthropic API — it does **not** send `description`
  or `submitted_by`. Today's only third-party data flow already avoids sending PII.

**Classification:** Blocking before storing real employees' spend data (unrestricted
read access to names and personal spending is a real exposure, not a hypothetical
one). The retention-policy gap is Deferrable in the short term but should be scoped
before this holds real people's data for any length of time.
**Effort:** Access control on read endpoints is covered by §1's effort estimate.
S–M (1–2 days) for a retention/deletion policy and endpoint. An audit trail tied to
real identities depends on §1 being done first, so no independent estimate applies.

---

## Summary

| # | Area | Classification | Rough effort |
|---|---|---|---|
| 1 | Authentication and key rotation | Blocking | M–L |
| 2 | Input validation | Deferrable (Blocking if public-facing) | S |
| 3 | Rate limiting | Blocking (untrusted callers) | S–M |
| 4 | Observability and logging | Blocking | S–M |
| 5 | Error handling | Deferrable (Blocking for insights honesty) | S |
| 6 | DB migrations and pooling | Blocking (if schema evolves / multi-instance) | S–L |
| 7 | Secrets management | Blocking (`.gitignore` gap is live today) | S–M |
| 8 | Tests and coverage | Blocking | M |
| 9 | Deployment and health checks | Blocking | S–M |
| 10 | Data privacy | Blocking (once real spend data is involved) | S–M (+ §1) |

Nine of ten areas have at least one blocking gap. The cheapest, highest-leverage fix
is §7's `.gitignore` (under an hour, closes an active leak risk today); the largest
is real authentication/authorization (§1), which several other gaps (role
separation, audit trail, read access control in §10) directly depend on.

# Steps.md — Playbook for rebuilding ExpenseFlow (or something like it) with Claude Code

This file contains the **exact prompts** used to build ExpenseFlow — a FastAPI +
SQLAlchemy/SQLite expense-approval API with a Streamlit UI and a Claude-powered
insights endpoint. Run these prompts in order in a fresh folder and you get the same
project back.

Every prompt block is followed by a **✏️ To reuse for a different project** note
telling you exactly which words to change and where. Nothing is left as a bare `<...>`
placeholder — copy a block as-is to rebuild ExpenseFlow, or edit the noted words to
build something else with the same tools and shape.

---

## 0. Prerequisites (you do this, not Claude Code)

**Why:** Claude Code needs somewhere to run Python and a place to install
dependencies — this is manual setup that has to happen before any prompt can do
anything. **What it does:** creates an isolated environment for this project so its
dependencies don't collide with anything else on your machine.

- Create the project folder and `cd` into it.
- Install Python 3.12 (this repo's actual `.venv` ended up on 3.10.12 — either works
  for this stack, but 3.12 is what CLAUDE.md declares).
- Create and activate a virtualenv: `python -m venv .venv`, then
  `.\.venv\Scripts\Activate.ps1` on Windows PowerShell.
- Open Claude Code in that folder.

## 1. Write CLAUDE.md first

Do this before asking for any code — it's loaded on every turn and is the single
biggest lever for keeping Claude Code's output consistent.

**Prompt:**
```
Create a CLAUDE.md file for a project called ExpenseFlow API.

What this is: a small expense submission and approval API. PoC, not production. One
user journey: submit an expense, convert it to a base currency, approve or reject it.

Stack:
- Python 3.12, FastAPI, Uvicorn
- SQLAlchemy ORM on SQLite (file: expenseflow.db) for the PoC
- httpx for the external FX rate call
- pydantic v2 for request and response models
- pytest for tests

Conventions:
- Layout: app/main.py, app/db.py, app/models.py, app/schemas.py, app/routes.py
- Type hints on every function. Docstrings on every endpoint.
- Money is stored as integer minor units (paise / cents), never float.
- Base currency is INR. All amounts are normalised to base on write.
- Never hardcode secrets. Read them from environment variables via python-dotenv.

Run and test:
- Run:  python -m uvicorn app.main:app --reload
- Test: python -m pytest -q

Do not touch:
- Do not edit .venv, .git, or expenseflow.db directly.
- Do not add new third-party dependencies without telling me first.
- Do not invent endpoints that are not in the brief.
```

**✏️ To reuse for a different project**, change: the project name and one-line
description; the stack list (framework/ORM/DB/validation/test-runner); the DB file
name; the layout file list; the domain-specific convention line ("Money is stored
as...", "Base currency is...") to whatever normalization rule *your* domain has; the
run/test commands; and the "do not touch" file names.

## 2. Scaffold the backend

**Why:** this turns the CLAUDE.md conventions into actual working code — the data
model and endpoints are the foundation everything else (UI, insights, docs) gets
built on top of. **What it does:** asks Claude Code to create the SQLAlchemy model,
Pydantic schemas, and FastAPI routes in one pass, following the file layout declared
in CLAUDE.md.

**Prompt:**
```
Following CLAUDE.md, scaffold the backend.

Data model: Expense with fields:
- id: integer primary key, autoincrement
- description: string, required
- amount_minor: integer, required, must be > 0
- currency: string, required, 3-letter ISO 4217-style code
- category: string, required
- submitted_by: string, required
- amount_base_minor: integer, required — the amount converted to base currency (INR)
- base_currency: string, required, defaults to "INR"
- fx_rate: float, required — the exact rate used for the conversion
- fx_rate_fetched_at: datetime, required
- status: string, required, defaults to "PENDING", one of PENDING / APPROVED /
  REJECTED (enforce with a DB check constraint)
- created_at: datetime, required, defaults to now (UTC)
- decided_at: datetime, nullable — set when status leaves PENDING
- decision_note: string, nullable — optional free-text reason from the approver

Endpoints:
- POST /expenses — create a new expense as PENDING; convert amount_minor to base
  currency via an FX lookup and persist
- GET /expenses — list expenses, optionally filtered by status and/or category
- GET /expenses/{id} — fetch a single expense, 404 if missing
- POST /expenses/{id}/approve — transition PENDING -> APPROVED, optional
  {"note": "..."} body, 404 if missing, 409 if not currently PENDING
- POST /expenses/{id}/reject — same as approve but -> REJECTED

Create tables automatically on startup (no migrations tool needed for this PoC).
```

**✏️ To reuse for a different project**, change: the entity name (`Expense`) and its
field list to your domain's data; the status values and their transition rules; and
the endpoint list to match. Keep the shape (create → list/filter → fetch one →
state-transition actions) if your domain has a similar submit-then-decide workflow.

> **Heads-up from this project:** the FX-conversion part of this prompt didn't get a
> real implementation — Claude Code left it as a `TODO` in `routes.py` and stubbed it
> out (`amount_base_minor` just copies `amount_minor`, `fx_rate` hardcoded to `1.0`).
> If you need the real conversion this time, ask for it explicitly as its own step
> and check the generated code before trusting it — don't assume a prompt like this
> one produces a working implementation just because it was requested.

## 3. Start the API server and verify

**Why:** catches integration mistakes — a wrong status code, a typo'd field name, a
broken state transition — right after scaffolding, before anything else (UI,
insights) gets built on top of a foundation that doesn't actually work. **What it
does:** starts the real server and exercises the full submit → list → fetch → decide
flow against it, instead of just reading the generated code and assuming it's
correct.

**Prompt:**
```
Start the API server and walk through the happy path with curl or /docs: submit an
expense, list expenses, fetch it by id, then approve it. Also try rejecting an
already-approved expense and confirm it returns 409. Show me the responses.
```

**✏️ To reuse for a different project**, change: the happy-path sequence to match
your own endpoints and state machine.

## 4. Add the AI-powered insights endpoint

**Why:** adds an optional, non-critical feature (spending insights) on top of a core
CRUD/approval flow that's already been verified in step 3, without risking that flow.
**What it does:** wires a new endpoint to an external LLM call, with an explicit
instruction to fail safely (a fallback message) instead of taking the whole API down
if that external call fails.

**Prompt:**
```
Add a GET /reports/insights endpoint that summarizes all expenses (amount in base
currency minor units, category, and status) and asks Claude for exactly three short
bullet-point insights. Read the API key from ANTHROPIC_API_KEY via python-dotenv. If
the call fails for any reason, return the fallback string "Insights are unavailable
right now. Please try again later." instead of an error — don't let this endpoint
take the whole API down.
```

**✏️ To reuse for a different project**, change: the endpoint path and name; which
fields go into the summary sent to Claude; the number/shape of insights requested;
and the env var name if you're calling a different provider.

## 5. Set up the Streamlit front end

**Why:** gives a human-usable way to exercise the API without hand-writing curl
commands for every check — useful for you, and for anyone else who needs to poke at
this without reading the OpenAPI docs first. **What it does:** builds a simple
form-plus-table front end that talks to the already-running API over HTTP; it has no
logic of its own beyond calling the API and rendering the response.

**Prompt:**
```
Create a Streamlit front end in ui/app.py that talks to the FastAPI backend over
httpx. Include:
- A form to submit a new expense: amount, currency, category, description,
  submitted by.
- A table listing existing expenses.
- A button that calls /reports/insights and renders the result as markdown.
Read the API's base URL from an API_BASE env var, defaulting to
http://127.0.0.1:8000. Show friendly error messages (not stack traces) if the API is
unreachable or returns an error.
```

**✏️ To reuse for a different project**, change: the form fields to match your
create-endpoint's request body; the table's data source; and whether you need the
insights button at all.

## 6. Run and visually verify the UI

**Prompt (this is literally what was typed to trigger it):**
```
streamlit run ui/app.py
```

Claude Code should recognize this needs the API running too, start both in the
background, and — since a headless agent can't open a real browser window — drive a
headless Chromium against the running UI and take a screenshot to confirm it actually
rendered (not just that the process started without crashing).

**✏️ To reuse for a different project:** nothing to change here — this step is the
same regardless of what the UI contains, just point it at your own `ui/app.py` (or
equivalent) path.

## 7. Iterate: add a feature

This is the normal loop for the rest of development — describe the feature in plain
language and let Claude Code find the files. The exact prompt used to add the
approve/reject workflow to the UI in this project:

**Prompt:**
```
create one more section on my UI. Add approve and reject button also to approve and
reject the submitted expenses. Make the status column with different color coding for
approve, reject and pending in expense table
```

**✏️ To reuse for a different project**, change: the section/feature description and
the specific behavior (button labels, which states get which colors) to match your
own workflow.

## 8. Iterate: fix a bug you find while using it

Describe symptom → expected vs. actual, and let Claude Code find the root cause —
don't pre-diagnose it yourself unless you're sure. The exact prompt used to fix a
display bug in this project:

**Prompt:**
```
I added an expense using the streamlit UI for INR 1, but in the expense table is is
being shown as 100. Kindly fix it, so that in UI it is shown as 1 and not 100, and
same change for other expenses as well.
```

**✏️ To reuse for a different project**, change: the description of what you did,
what you expected, and what actually happened — keep the "and same change for other
[similar cases] as well" framing, it's what tells Claude Code to fix the general case
and not just the one row/example you noticed.

## 9. Write the README

**Why:** ask for this once the feature set has settled, not before — otherwise it
goes stale immediately. **What it does:** produces the single doc a new developer
reads first — setup, running, and the endpoint contract — written by reading the
actual code rather than by recalling what was asked for.

**Prompt:**
```
Write README.md for ExpenseFlow: what it does, the stack, how to set up the venv and
install on Windows, how to configure .env, how to run the server and the tests, and
the full endpoint reference. Base it on the real code, not assumptions.
```

**✏️ To reuse for a different project**, change: the project name and OS if not
Windows. Keep the "Base it on the real code, not assumptions" instruction verbatim —
without it, generated docs tend to describe intended design rather than what's
actually implemented, and the two quietly drift apart (see `docs/ARCHITECTURE.md` in
this repo for a real example: it describes an FX lookup and a test suite that were
never actually built).

## 10. Write a handoff doc and an architecture decision record

**Why:** the code and endpoint list don't explain *why* decisions were made or what
someone operating this needs to know before running it somewhere real — that context
is easy to lose once the person who built it moves on. **What it does:** produces two
different documents — an operational handoff doc for whoever deploys/runs this next,
and a decision record (ADR) that captures one specific convention, the alternatives
considered, and the tradeoff, for anyone who later questions it.

**Prompt:**
```
Create docs/HANDOFF.md (what it does, how it works, what a deployment engineer needs
to know) and docs/adr/0001-money-as-integer-minor-units.md as a short ADR explaining
the decision, the alternatives, and the consequences.
```

**✏️ To reuse for a different project**, change: the ADR filename and topic to
whatever convention in *your* CLAUDE.md a future contributor might question (why this
file layout, why this DB, why no auth yet, why these status values, etc.) — the
integer-minor-units decision is specific to this project's money handling.

## 11. Audit against a production bar

**Why:** once the core feature set, docs, and handoff notes exist, it's easy for a
working PoC to get mistaken for something ready to hold real data — this step forces
an honest look before that happens. **What it does:** checks the actual code (not the
docs, not this playbook) against a list of production concerns, and for each one
states the gap, whether it blocks shipping, and roughly how much work it'd take to
close.

**Prompt:**
```
Audit ExpenseFlow against a production bar: authentication and key rotation, input
validation, rate limiting, observability and logging, error handling, database
migrations and pooling, secrets management, tests and coverage, deployment and health
checks, and data privacy for expense data. For each: state the gap, classify it
blocking or deferrable, and give a rough effort estimate. Write it to
docs/PRODUCTION-GAP.md. Do not consider steps.md file while doing this task.
```

**✏️ To reuse for a different project**, change: the project name and the list of
audit categories to whatever matters for your domain (add things like PCI scope,
GDPR/data-residency, multi-tenancy isolation, etc. if relevant). Keep the "state the
gap, classify it blocking or deferrable, give a rough effort estimate" structure —
it's what keeps the output actionable instead of a wall of generic security advice.
Keep the "do not consider steps.md" instruction (or the equivalent exclusion for
whatever meta-files you've accumulated) so the audit is grounded in the actual code,
not in this playbook's description of what was *supposed* to get built.

## 12. Push the project to GitHub

**Why:** none of the previous steps put this project under real version control or
made it reachable by anyone but you. **What it does:** gets the working tree
committed locally and pushed to a new GitHub repository.

**What was actually done in this project** (run directly in the terminal, not via a
Claude Code prompt):

```
git init
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
git add .
git commit -m "final project"
```

This initialized the repo and created the first commit (`52db0571 final project`).

After that commit, a `.gitignore` was created to exclude the files that shouldn't be
pushed (API keys, the local venv, the SQLite db, caches, etc.).

With a personal access token generated on GitHub, the next part — creating the new
remote repository and pushing this project to it — is being done using Claude Code.

> **⚠️ Heads-up flagged during this run, worth fixing before pushing:** the
> `.gitignore` was added *after* `git add . && git commit` had already run, so that
> first commit already contains `.env` (with a real Anthropic API key in it) and the
> entire `.venv/` directory — `.gitignore` only stops *new* changes from being
> staged, it does nothing to files already committed. Confirm with `git ls-files`
> before pushing; if `.env` or `.venv/` show up, they need to be removed from history
> (e.g. `git rm --cached .env` plus a new commit, or rewriting history entirely if
> the token/secret needs to be treated as burned) — not just added to `.gitignore`
> — before this repo goes anywhere public or shared.

**Prompt (to create the remote and push, once the history is clean):**
```
Create a new GitHub repository called expenseflow (ask me whether it should be
public or private before creating it). Commit any remaining changes and push the
working tree to the new repo's main branch. Use the gh CLI if it's available, and
check with me before actually pushing.
```

A few things worth knowing going in:
- This needs `gh auth login` (or the generated personal access token) to already be
  usable — Claude Code can't complete an OAuth/browser login flow for you. In this
  environment, prefix interactive login commands with `!` to run them directly in
  the session.
- Pushing code and creating a repository are both visible, hard-to-undo actions —
  expect (and want) Claude Code to show you what it's about to commit/push and wait
  for a yes before it actually does either, rather than doing it silently.
- The current local branch here is named `master`, not `main` — decide up front
  whether to rename it (`git branch -m master main`) or just push it as `master`;
  don't let that get decided implicitly by whatever `gh repo create` defaults to.

**✏️ To reuse for a different project**, change: the repository name; the list of
files to `.gitignore` (match it to whatever this project's dependency manager and
runtime actually generate — a different stack won't have `.venv/`, for instance);
and public/private depending on whether the project is meant to be shared. If you
create `.gitignore` *before* your first `git add`/`commit` instead of after, you'll
avoid the history-cleanup problem flagged above entirely.

## 13. Save this playbook for the next project

**Why:** the exact prompts that worked, in order, are otherwise only visible by
scrolling back through the whole conversation — not something you or anyone else will
remember by the next project. **What it does:** writes out this file itself, turning
the session's history into a reusable, editable checklist instead of a one-off
transcript.

**Prompt:**
```
Create steps.md with the steps and prompts we used to build this project, so I can
reuse and edit it for future similar projects.
```

Once you've adapted this file's contents for the new project (per the ✏️ notes
above), it's worth re-running this exact prompt again at the end of the new project
too — it'll capture whatever *actually* happened this time, including any detours,
which is more useful than hand-editing this file in advance and hoping it holds.

---

## Things worth keeping regardless of domain

- **State the domain's core convention (money as integers, timestamps as UTC,
  whatever it is) in CLAUDE.md up front**, not after the first bug. It's cheap to
  write once and expensive to retrofit across every file that touches the value.
- **Ask for docs "based on the real code, not assumptions."** Generated docs default
  to describing intended design otherwise.
- **Ask Claude Code to actually run and screenshot the UI**, not just start the
  process. A process that starts cleanly can still render a blank page.
- **When something looks wrong, describe symptom → expected vs. actual** and let
  Claude Code find the root cause, rather than prescribing the fix yourself.

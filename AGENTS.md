# Fathom — agent instructions

Single-user personal finance app. Python 3.12, FastAPI (sync), React + Vite SPA, Postgres.
Domain terms (pay-cycle month, Transfer, Cover, Saver, Split, Reimbursement, Snapshot)
are defined in `CONTEXT.md`. Use them exactly; don't invent synonyms.

## Commands

- Install: `uv sync`
- Database: `docker compose up -d`
- Tests: `uv run pytest`
- Lint and format: `uv run ruff check --fix` then `uv run ruff format`
- Pre-commit must pass before any commit. Never use `--no-verify`.
<!-- Add migration and run-app commands once S1-25 and the walking skeleton land. -->

## Domain rules (non-negotiable)

- Transfers and Covers never count as spend, in any aggregation. There is no toggle.
- Spend is net of linked Reimbursements by default; gross is opt-in.
- Joint accounts count at a fixed 50% for balance, Spend and Income, in every
  aggregation. Spend is attributed to the Account that funded it (a confirmed Cover
  moves it) and counts at that Account's share. Never apply a share inline. See ADR-009.
- All period boundaries come from the single date-range resolver. Never compute
  the 15th–14th pay-cycle (or any period) inline.
- Money amounts are integer cents: `int` in Python, `BIGINT` in Postgres, a number in
  the API. Unit prices, units held, rates and percentages are `Decimal` / `NUMERIC`.
  The two meet only in the single rounding function in `domain/`. No money amount is
  ever a `float`. See ADR-004 (Amendment).

## Architecture

- Layering follows ADR-005: `api` → `services` → `repositories`, imports never run upward.
  `domain/` (pure rules), `schemas/`, `models/`, `core/`, `jobs/` and `providers/` sit
  beside that stack. Jobs and importers call services.
- `domain/` is pure: no database, HTTP or framework imports.
- Read the relevant ADR in `docs/adr/` before changing anything architectural.
  To deviate, propose a new ADR. Don't quietly work around one.

## Human versus AI split (ADR-011)

Every ticket is one tier. The tier decides who writes the code.

- **Tier A, hand-write (`ready-for-human`).** Jake writes the implementation. You ask
  questions, explain, review and write tests once his code exists. Never write,
  paste or dictate the implementation, not even in chat. Paths are listed in
  `.claude/hand-write-paths.txt`, and a hook blocks edits to them. Tier A covers:
  - Data model and schema, including migrations
  - The transaction relationship model (Transfers, Covers, Splits, Reimbursements)
  - Sync and idempotency: fetch orchestration, dedupe, the advisory lock
  - Balance forecasting (post-v1)
- **Tier B, design-led (`ready-for-agent`, `Mode: design-led`).** Jake decides the
  design and you build it. Covers the error model, CI, AWS deployment and the Up
  API client.
- **Tier C, agent-built (`ready-for-agent`).** Everything else.

Grilling: for Tier A and B questions, ask and wait for Jake's answer before you
give your view. Then challenge it. Recommend directly only for Tier C.

When Jake is stuck on Tier A, climb one rung at a time: a question, then the
concept, then where to look (file, docs, ADR), then pseudocode. Never real code.
Before each step up, ask what he has tried and log it in the ticket's
`## Comments`. If he asks you to just write it, don't. Remind him that moving
work out of Tier A means relabelling the ticket, writing the reason in Comments
and adding a line to the README's "Moved out of hand-written" list, and that
it's his call.

## Secrets and config

- All config goes through the typed settings object. No `os.environ` reads elsewhere.
- Never read, print, log or commit `.env` or the Up token.

## Testing

- Every behaviour change ships with tests.
- Tests use the isolated test database fixture and committed fixtures.
  Never call the live Up API from tests.
<!-- Add fixture locations once S1-13 lands. -->

## Commits

- Reference the task or story ID in every commit message (e.g. `S1-36: …`, `ET-12: …`).

## Coding standards

- Sync only: plain `def`, synchronous clients and sessions (ADR-002).
- Annotate every signature. Use a `StrEnum` for a closed set of values, and a typed
  model rather than a bare `dict` across a layer boundary. No `Any`.
- A `# type: ignore` or `# noqa` names its code and gives the reason on the same line.
- Name modules for their feature, the same name in every layer
  (`api/transactions.py`, `services/transactions.py`).
- Name tests for the behaviour they prove (`test_blank_secret_is_rejected`).
- Raise a specific exception where the problem is found. Only `api/` turns exceptions
  into HTTP responses.
- An `except` handles the error or re-raises it.
- Validate external data (Up payloads, CSV rows, prices) into a typed model before a
  service sees it.

Reviewing a diff: check it against every item in `docs/agents/review-checklist.md`.


## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, using their default names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` at the repo root plus ADRs in `docs/adr/`. See `docs/agents/domain.md`.

## Specs and tickets

Lifecycle (draft vs committed) is defined in `docs/agents/issue-tracker.md`. New spec and ticket output goes in `.scratch/_drafts/`. Never promote it yourself.

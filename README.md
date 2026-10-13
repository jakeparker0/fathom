# Fathom

Personal finance tracking and forecasting for a single user — Up Bank sync, ASX portfolio, and net worth on a pay-cycle calendar.

Fathom syncs transactions from Up Bank, tracks manually-entered and CSV-imported accounts (AMEX, Bendigo), values an ASX ETF portfolio and Vanguard managed funds, and reports spending and net worth on a configurable pay-cycle month rather than a calendar one.

Built in Python and React, deployed to AWS. Not intended for multi-user use or general release.

---

## Status

**Sprint 1 of 6 — Foundations.** Nothing user-facing is functional yet. This sprint stands up the repo and tooling, locks the architecture and data model decisions that are expensive to retrofit, gathers real sample data from each provider, and ends with a walking skeleton that validates an Up token and displays account balances.

Done so far:

- Repo, `uv` dependency management, Python 3.12, ruff and pre-commit
- Local Postgres 18 in Docker Compose, with a connection check script
- Typed settings object and `.env` template, with tests
- Architecture decisions ADR-001 to ADR-006 and ADR-008 to ADR-010
- Domain glossary (`CONTEXT.md`), agent instructions (`AGENTS.md`) and review checklist
- Real Up API sample responses under `tests/fixtures/up/` (a few are still empty)

Not started: the data model and migrations, the Up client, the API, the frontend, CI and the runbook.

**Scope is under review.** The plan is being cut down so a smaller v1 is live in daily use by about 22 January 2027. The roadmap and feature areas below describe the full plan and will change when that rescope lands.

---

## What it does

Four feature areas, built out across sprints 2–5:

**Expense tracking.** Scheduled daily sync from the Up Bank API plus an always-available manual sync. Manual accounts and CSV import for institutions without an API. Card-based categorisation queue with merchant-based suggestions, user-defined sub-categories, tags, and transaction splitting. Automatic detection of internal transfers and Up "Cover" events. Manual reimbursement linking. Heuristic subscription detection.

**Stock portfolio.** Buy and sell trades recorded as permanent individual records, with holdings derived from full history rather than stored as an editable figure. Dividends with franking credits. Bulk trade import from CMC Markets CSV export. Daily ASX end-of-day pricing. Portfolio dashboard covering value, cost basis, realised and unrealised gain, day change, and allocation by holding and sector.

**Spending analysis and net worth.** Spend by category and over time, filterable by account, category, and tag. Income tracked separately for salary and interest. A consolidated net worth figure across all cash accounts, the stock portfolio, managed funds, and term deposits, less the AMEX balance as a liability. Both portfolio value and net worth are snapshotted daily so historical trends are available rather than only a current reading.

**Budget forecasting.** Balance projections at 3, 6, and 12 month horizons, presented as a range rather than a single number, factoring in known recurring charges and expected income alongside statistical modelling of historical spend. Category trend analysis ranked by rate of change. Spending limit and savings goals tracked against projections.

---

## Design decisions that shape everything

Five cross-cutting rules apply across every feature area. They are worth understanding before reading any of the reporting code, because almost every aggregation depends on them. The full wording is in [`AGENTS.md`](AGENTS.md) and [`CONTEXT.md`](CONTEXT.md).

**The reporting period is a pay cycle, not a calendar month.** The default period runs the 15th to the 14th, aligned to salary. This is configurable, and any view can be switched to calendar month, week, quarter, financial year, calendar year, or a custom range. There is one date-range resolver and every chart, budget, and forecast goes through it — the pay-cycle boundary is not reimplemented per view.

**Transfers and Cover transfer legs never count as spend.** Moving money between own accounts is not spending, and it must not inflate reported totals or double-count in net worth. This applies whether the movement was detected automatically from the Up API or flagged manually. There is no user-facing toggle to include them.

**Spend is net of reimbursements by default.** When an incoming payment is linked to an original expense, reporting shows the net figure. A gross view is available as a toggle, but net is the default everywhere.

**Joint accounts count at a fixed 50%.** Balance, Spend and Income on a Joint account all count at half, whoever made the transaction. A confirmed Cover moves a purchase's Spend to the account that funded it, where it counts at that account's share. See [ADR-009](docs/adr/009-joint-account-share-and-cover-attribution.md).

**Money is integer cents.** Amounts are `int` in Python, `BIGINT` in Postgres and a plain number in the API. Unit prices, units held, rates and percentages are `Decimal` / `NUMERIC`, and the two meet only in one rounding function. No money amount is ever a `float`. See the amendment to [ADR-004](docs/adr/004-database.md).

---

## Glossary

Domain vocabulary is defined in [`CONTEXT.md`](CONTEXT.md): Pay-cycle month, Transfer, Cover, Saver, Joint account, Split, Reimbursement, Refund, Snapshot and the rest. Use those terms exactly. Several are Up Bank concepts and some are overloaded elsewhere in finance, so they are defined there deliberately. `CONTEXT.md` is the single source; this README does not repeat the definitions.

---

## Data sources

| Source | Method | Notes |
|---|---|---|
| Up Bank | REST API, personal access token | Primary transaction and balance source. Covers the spending account, the Joint account and all Savers. Scheduled daily sync plus manual trigger. |
| AMEX | Manual entry and CSV import | No API. Treated as a liability in net worth. |
| Bendigo Bank | Manual entry and CSV import | No API. |
| CMC Markets | CSV export | Trade history import. Column mapping confirmed against a real export rather than assumed. |
| Vanguard | Manual entry only | No usable public API exists for individual investors. This is a deliberate decision, not a gap to be filled later. |
| ASX prices | yfinance | Daily end-of-day close, behind an abstracted price-provider interface so the provider can be swapped without rearchitecture. |

---

## Tech stack

| Concern | Choice | Decision |
|---|---|---|
| Language and tooling | Python 3.12, `uv` | [ADR-008](docs/adr/008-dependency-mgmt.md) |
| Backend | FastAPI, synchronous (`def`, not `async def`) | [ADR-002](docs/adr/002-backend-framework.md) |
| Frontend | React SPA with Vite, TypeScript, types generated from the OpenAPI schema | [ADR-003](docs/adr/003-frontend-framwork.md) |
| Database | PostgreSQL 18 in Docker locally; SQLAlchemy and Alembic; `psycopg` v3 | [ADR-004](docs/adr/004-database.md) |
| Code structure | Technical layers with a pure `domain/` package | [ADR-005](docs/adr/005-code-structure.md) |
| Scheduled jobs | Idempotent CLI entry points run by cron or systemd timers | [ADR-006](docs/adr/006-scheduled-jobs.md) |
| Branching | Trunk-based, short-lived feature branches merged by PR | [ADR-001](docs/adr/001-branching-strategy.md) |
| Joint accounts and Covers | Fixed 50% share; a confirmed Cover moves Spend | [ADR-009](docs/adr/009-joint-account-share-and-cover-attribution.md) |
| Secrets | Local `.env` through the typed settings object; AWS Secrets Manager in production | — |
| Deployment | AWS, hosting service not yet chosen | — |

**Still open:**

- Cost-basis method for realised gains — [ADR-007](docs/adr/007-cost-basis-method.md) is an empty template
- AWS hosting service (S1-39) — the ADRs assume a single always-on host until it is chosen
- Authentication mechanism, charting library, and client-side data fetching

---

## Getting started

> **Partial.** A verified clean-clone runbook is a Sprint 1 deliverable. Until it lands, only the steps below work: there are no migrations, API or frontend to run yet.

Prerequisites: [`uv`](https://docs.astral.sh/uv/) and a container runtime with Docker Compose.

```bash
git clone https://github.com/jakeparker0/fathom
cd fathom

# install dependencies (also installs Python 3.12)
uv sync

# configure
cp .env.example .env
# then edit .env: set POSTGRES_PASSWORD (any value locally) and UP_API_TOKEN

# start local Postgres (reads the POSTGRES_* values from .env)
docker compose up -d

# confirm the app can reach the database
uv run --env-file .env python scripts/check_db.py

# run the tests
uv run pytest
```

An Up Bank personal access token is required and can be generated at [api.up.com.au](https://api.up.com.au). Every configuration key the app needs is listed in `.env.example`. `.env` itself is never committed.

Before committing, run `uv run ruff check --fix` and `uv run ruff format`. The pre-commit hooks run both.

### Running tests

Tests that use the database need Postgres up (`docker compose up -d`), then `uv run pytest`.

Database tests use a separate `<POSTGRES_DB>_test` database on the same Postgres, dropped and recreated at the start of each run. Each test runs in a transaction that is rolled back, so even a `commit()` leaves nothing behind. The provisioning helper asserts the name ends in `_test` before any `DROP` or `CREATE`. Tests that do not use the database run without Postgres. See [ADR-010](docs/adr/010-test-database-isolation.md).

---

## Repository layout

```
src/fathom/       application code (config only so far)
tests/            pytest suite
  fixtures/up/    real Up API responses used by tests
scripts/          one-off scripts, e.g. database connection check
docs/
  adr/            architecture decision records
  agents/         agent workflow docs and the code review checklist
  requirements/   user stories and acceptance criteria (not yet moved in)
.scratch/
  _drafts/
CONTEXT.md        domain glossary
AGENTS.md         instructions for AI coding agents
CLAUDE.md         Claude Code rules, imports AGENTS.md
docker-compose.yml  local Postgres
.env.example      every configuration key the app reads
```

Backend modules will follow the layering in [ADR-005](docs/adr/005-code-structure.md), none of which exists yet:

```
src/fathom/
  api/            FastAPI routers
  services/       use cases; the only entry point for jobs and importers
  repositories/   all database access
  models/         SQLAlchemy ORM models
  schemas/        Pydantic request and response models
  domain/         pure business rules: no database, HTTP or framework imports
  core/           database session, logging, shared infrastructure
  jobs/           scheduled job entry points
  providers/      Up client, price provider
```

Imports run `api` → `services` → `repositories` and never upward. The React tree has no structure yet.

---

## Roadmap

Under review: this is the original six-sprint plan, and the v1 rescope may move work out of it.

| Sprint | Focus |
|---|---|
| 1 | Foundations — repo, tooling, architecture and data model decisions, real sample data, walking skeleton |
| 2 | Up sync and categorisation — transaction list, categorisation workflow, tags, transfers, covers |
| 3 | Manual accounts and netting — CSV import, splits, reimbursements, subscriptions |
| 4 | Stocks and net worth — trades, dividends, pricing, portfolio dashboard, snapshots |
| 5 | Analysis and forecasting — periods, visualisations, trends, forecasting, goals |
| 6 | Deployment — authentication, AWS secrets and hosting, deploy, server-side scheduled jobs |

Sequencing is deliberate: transactions come before stocks because net worth depends on portfolio value, and CSV import lands before forecasting because a model trained on a few weeks of data is not worth building.

---

## Out of scope

Deliberately excluded from v1 and tracked in the requirements parking lot rather than dropped:

- Multi-user and household support — this is a single-user application by design
- Multi-currency support
- Superannuation and HECS tracking
- Intraday price movement — daily EOD pricing is sufficient
- Proactive insights, alerts, and anomaly detection — reporting is passive in v1
- AI-generated "where to cut back" recommendations — v1 surfaces ranked data and leaves conclusions to the reader
- Deep stock analysis including technical indicators, benchmarking, and news sentiment — a separate future project, not an extension of this one

---

## Development notes

Requirements are captured as 56 user stories across five epics, with acceptance criteria and priorities. Code references stories by ID (`ET-12`, `SP-11`, `SA-01`) and sprint tasks by `S1-XX` in commits and comments so implementation can be traced back to intent. The stories are being moved into `docs/requirements/`.

Development is AI-assisted, with a deliberate split between what is hand-written and what is generated. The forecasting work, the transaction relationship model, and the data model are written by hand as learning exercises and because they carry the most risk. CRUD, forms, CSV parsing, boilerplate, and tests are generated and reviewed. [`AGENTS.md`](AGENTS.md) holds the project rules that agents read, [`CONTEXT.md`](CONTEXT.md) the vocabulary, and [`docs/agents/review-checklist.md`](docs/agents/review-checklist.md) what generated code must satisfy before it is accepted.

Architectural change goes through a new ADR, starting from [`docs/adr/000-template.md`](docs/adr/000-template.md). Don't work around an accepted one.

Balance forecasting is an intentional exercise in real time-series technique — Prophet, ARIMA, or similar — rather than a linear trend line drawn through past spending.

---

## License

Private project. No license granted.

# Fathom

Personal finance tracking and forecasting for a single user — Up Bank sync, ASX portfolio, and net worth on a pay-cycle calendar.

Fathom syncs transactions from Up Bank, tracks manually-entered and CSV-imported accounts (AMEX, Bendigo), values an ASX ETF portfolio and Vanguard managed funds, and reports spending and net worth on a configurable pay-cycle month rather than a calendar one.

Built in Python, deployed to Oracle Cloud Infrastructure. Not intended for multi-user use or general release.

---

## Status

**Sprint 1 of 6 — Foundations.** Nothing is functional yet. This sprint stands up the repo and tooling, locks the architecture and data model decisions that are expensive to retrofit, gathers real sample data from each provider, and ends with a walking skeleton that validates an Up token and displays account balances.

Setup instructions below are incomplete until the stack decisions land (see [Tech stack](#tech-stack)). A verified clean-clone runbook is a Sprint 1 deliverable and will replace the placeholder section.

---

## What it does

Four feature areas, built out across sprints 2–5:

**Expense tracking.** Scheduled daily sync from the Up Bank API plus an always-available manual sync. Manual accounts and CSV import for institutions without an API. Card-based categorisation queue with merchant-based suggestions, user-defined sub-categories, tags, and transaction splitting. Automatic detection of internal transfers and Up "Cover" events. Manual reimbursement linking. Heuristic subscription detection.

**Stock portfolio.** Buy and sell trades recorded as permanent individual records, with holdings derived from full history rather than stored as an editable figure. Dividends with franking credits. Bulk trade import from CMC Markets CSV export. Daily ASX end-of-day pricing. Portfolio dashboard covering value, cost basis, realised and unrealised gain, day change, and allocation by holding and sector.

**Spending analysis and net worth.** Spend by category and over time, filterable by account, category, and tag. Income tracked separately for salary and interest. A consolidated net worth figure across all cash accounts, the stock portfolio, managed funds, and term deposits, less the AMEX balance as a liability. Both portfolio value and net worth are snapshotted daily so historical trends are available rather than only a current reading.

**Budget forecasting.** Balance projections at 3, 6, and 12 month horizons, presented as a range rather than a single number, factoring in known recurring charges and expected income alongside statistical modelling of historical spend. Category trend analysis ranked by rate of change. Spending limit and savings goals tracked against projections.

---

## Design decisions that shape everything

Three cross-cutting rules apply across every feature area. They are worth understanding before reading any of the reporting code, because almost every aggregation depends on them.

**The reporting period is a pay cycle, not a calendar month.** The default period runs the 15th to the 14th, aligned to salary. This is configurable, and any view can be switched to calendar month, week, quarter, financial year, calendar year, or a custom range. There is one date-range resolver and every chart, budget, and forecast goes through it — the pay-cycle boundary is not reimplemented per view.

**Transfers and covers never count as spend.** Moving money between own accounts is not spending, and it must not inflate reported totals or double-count in net worth. This applies whether the movement was detected automatically from the Up API or flagged manually. There is no user-facing toggle to include them.

**Spend is net of reimbursements by default.** When an incoming payment is linked to an original expense, reporting shows the net figure. A gross view is available as a toggle, but net is the default everywhere.

---

## Glossary

Domain vocabulary used throughout the codebase. Several of these terms are Up Bank concepts and some are overloaded elsewhere in finance, so they are defined here deliberately.

| Term | Meaning |
|---|---|
| **Pay-cycle month** | The default reporting period, 15th to 14th, aligned to salary. Not a calendar month. |
| **Transfer** | A movement between two accounts both belonging to the user. Excluded from spend. |
| **Cover** | An Up-specific event where a purchase is funded from a linked Saver. Produces a purchase and a transfer leg; the legs are merged for display and the transfer leg is excluded from spend. |
| **Saver** | A named Up savings pocket. A user may hold several. |
| **Split** | One transaction divided across multiple categories by dollar amount or percentage. Splits carry no transfer logic. |
| **Reimbursement** | An incoming payment linked to an earlier expense, reducing its effective cost. One expense may have several partial reimbursements. |
| **Snapshot** | A stored daily row capturing state at a point in time. Portfolio snapshots are stored per holding per day, not pre-aggregated. |
| **Vault** | Refers to OCI Vault, the production secrets store. Never used to mean an in-app concept. |

---

## Data sources

| Source | Method | Notes |
|---|---|---|
| Up Bank | REST API, personal access token | Primary transaction and balance source. Covers Spending, 2Up, and all Savers. Scheduled daily sync plus manual trigger. |
| AMEX | Manual entry and CSV import | No API. Treated as a liability in net worth. |
| Bendigo Bank | Manual entry and CSV import | No API. |
| CMC Markets | CSV export | Trade history import. Column mapping confirmed against a real export rather than assumed. |
| Vanguard | Manual entry only | No usable public API exists for individual investors. This is a deliberate decision, not a gap to be filled later. |
| ASX prices | yfinance | Daily end-of-day close, behind an abstracted price-provider interface so the provider can be swapped without rearchitecture. |

---

## Tech stack

**Decided:**

- Python backend
- Web frontend
- Local development uses a `.env` file; production secrets move to OCI Vault in the deployment sprint
- Deployment target is an OCI compute instance

**Pending Sprint 1 architecture decisions**, each recorded as an ADR in `docs/adr/`:

| Decision | ADR |
|---|---|
| Backend framework | `ADR-002` |
| Frontend approach | `ADR-003` |
| Database (Postgres leaning, SQLite under consideration) | `ADR-004` |
| Code structure and layering | `ADR-005` |
| Scheduled job mechanism | `ADR-006` |
| Cost-basis method for realised gains | `ADR-007` |

This table is updated as each decision lands.

---

## Getting started

> **Placeholder.** Real instructions land with the Sprint 1 runbook, once the stack decisions above are made and the walking skeleton runs end to end. Do not treat the commands below as working.

Expected shape:

```bash
git clone <repo-url>
cd fathom

# install dependencies (tool TBC — uv or Poetry)
<install command>

# start local database
docker compose up -d

# configure secrets
cp .env.example .env
# then edit .env and add your Up Bank personal access token

# run migrations
<migration command>

# start the app
<run command>
```

An Up Bank personal access token is required and can be generated at [api.up.com.au](https://api.up.com.au). Every configuration key the app needs is listed in `.env.example`. `.env` itself is never committed.

---

## Repository layout

```
docs/
  adr/          architecture decision records
  requirements/ user stories and acceptance criteria
CLAUDE.md       project context for AI coding agents
README.md
```

Application module structure is pending `ADR-005` and will be documented here once decided.

---

## Roadmap

| Sprint | Focus |
|---|---|
| 1 | Foundations — repo, tooling, architecture and data model decisions, real sample data, walking skeleton |
| 2 | Up sync and categorisation — transaction list, categorisation workflow, tags, transfers, covers |
| 3 | Manual accounts and netting — CSV import, splits, reimbursements, subscriptions |
| 4 | Stocks and net worth — trades, dividends, pricing, portfolio dashboard, snapshots |
| 5 | Analysis and forecasting — periods, visualisations, trends, forecasting, goals |
| 6 | Deployment — authentication, OCI Vault migration, deploy, server-side scheduled jobs |

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

Requirements are captured as 56 user stories across five epics in `docs/requirements/`, with acceptance criteria and priorities. Code references stories by ID (`ET-12`, `SP-11`, `SA-01`) in commits and comments so implementation can be traced back to intent.

Development is AI-assisted, with a deliberate split between what is hand-written and what is generated. The forecasting work, the transaction relationship model, and the data model are written by hand as learning exercises and because they carry the most risk. CRUD, forms, CSV parsing, boilerplate, and tests are generated and reviewed. `CLAUDE.md` holds the project context that agents read; the coding standards and review checklist in `docs/` define what generated code must satisfy before it is accepted.

Balance forecasting is an intentional exercise in real time-series technique — Prophet, ARIMA, or similar — rather than a linear trend line drawn through past spending.

---

## License

Private project. No license granted.
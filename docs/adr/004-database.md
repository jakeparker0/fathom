# ADR-004: Database Choice

**Status:** Accepted (amended 2026-10-11: money is stored as integer cents, see Amendment)
**Date:** 2026-09-17

## Context

Fathom needs a relational database to store all application and transactional data: accounts, transactions and their relationships (transfers, covers, splits, reimbursements), categories and tags, trades and dividends, and daily portfolio and net worth snapshots.

The database must be straightforward to interface with from Python, have a repeatable local setup and a standard deployment path to the OCI compute instance in Sprint 6, and support the analytical workload in Sprint 5 — rolling-average category trends (BF-03), spend aggregated over a configurable pay-cycle period rather than a calendar month (SA-01), and per-holding-per-day snapshot rows aggregated at query time rather than pre-computed (SP-11).

Two properties of the application push in opposite directions. It is explicitly single-user with no concurrency requirement, which is SQLite's ideal case. It is also money-handling and reporting-heavy, with a schema that will be migrated repeatedly as the relationship model in S1-21 is refined, which favours a fuller engine.

This decision is about the database engine. How that engine is *run* locally (Docker Compose, covered in S1-03) and in production (Sprint 6) is a separate concern and is not what is being decided here.

## Options Considered

### Option A: PostgreSQL, run locally as a Docker container

- Pros:
  - Native `NUMERIC` type for exact decimal arithmetic. Money handling never touches floating point at the storage layer.
  - Native `timestamptz`, `date` and interval arithmetic, plus `date_trunc` and `generate_series`. The pay-cycle month resolver and the snapshot backfill in SP-12 are materially easier to express.
  - Mature window function and CTE support for the Sprint 5 analytics, with a query planner that handles them well at the row counts daily snapshots will produce.
  - Full `ALTER TABLE` support, so Alembic migrations (S1-25) are ordinary operations rather than table rebuilds.
  - Strong typing enforced at the database layer — a wrong type is rejected rather than silently coerced.
  - Best-supported target in the Python ecosystem (psycopg, SQLAlchemy, Alembic), and the default assumption in most documentation and AI-generated code, which matters given the human/AI split in S1-33.
  - Local development matches production exactly, so no class of bug can appear only after deployment.
- Cons:
  - Requires a running container and therefore a container runtime. Real setup cost, already paid during S1-03 and non-trivial on a fresh machine.
  - Consumes memory on the OCI instance that a file-based database would not.
  - Backup and restore is a deliberate task (`pg_dump`/`pg_restore` plus volume management) rather than copying a file. Adds scope to Sprint 6.
  - More moving parts to keep running for an application with exactly one user.

### Option B: SQLite

- Pros:
  - Zero operational overhead. No container, no service, no port, no credentials.
  - Backup and restore is copying a single file. Genuinely attractive for the Sprint 6 backup requirement.
  - Single-user with no write concurrency is precisely the workload SQLite is designed for.
  - Supports window functions (3.25+) and CTEs, so the Sprint 5 queries are not out of reach.
  - Fastest possible path to a working local environment, and trivially reproducible from a clean clone.
- Cons:
  - No native decimal type. Numeric values are stored as `REAL` (floating point) or worked around with integer cents or text. For an application whose entire purpose is summing money, this is the deciding weakness.
  - No real date/time type. Dates are text or numbers, and the pay-cycle logic and snapshot date ranges are built on string comparison conventions rather than typed arithmetic.
  - Dynamic typing at the storage layer — a column will accept a value of the wrong type. Weakens the schema as a correctness guarantee, which matters more than usual where a significant share of the code is AI-generated.
  - Limited `ALTER TABLE`. Alembic requires batch mode, which rebuilds and copies tables to apply many changes. Given that S1-21 is acknowledged as the highest-risk retrofit in the project, migration friction is a cost that lands exactly where the risk is.
  - Local and production environments would diverge if the app later outgrows SQLite, deferring rather than avoiding this decision.

### Option C: Oracle Autonomous Database (OCI Always Free tier)

- Pros:
  - Available at no cost on the existing OCI tenancy, alongside the compute instance already in use.
  - Fully managed — backups, patching and tuning are handled rather than owned.
  - Overlaps directly with existing professional Oracle experience, so the learning curve on the database itself is near zero.
- Cons:
  - Near-zero learning curve is a cost here, not a benefit. Fathom is a deliberate exercise in a stack outside the Oracle day job, and choosing Oracle would forfeit that.
  - Weakest Python ecosystem fit of the three. Workable with `oracledb` and SQLAlchemy, but it is the least-travelled path, with correspondingly less documentation and more scope for AI-generated code to be subtly wrong.
  - No practical offline or local-first development story — development would depend on network access to a cloud tenancy.
  - Always Free instances are reclaimed after a sustained idle period, which is a poor fit for a project developed in evenings and weekends with gaps between sprints.
  - Couples the project to a specific cloud vendor at the data layer, where the other options are portable.

## Decision

PostgreSQL, run locally as a Docker container and deployed to the OCI compute instance in Sprint 6.

The deciding factor is type fidelity rather than performance or scale: exact decimal arithmetic and real date/time types for pay-cycle and snapshot logic are the two things SQLite cannot provide without workarounds, and they sit underneath every figure the application reports.

As amended on 2026-10-11, money amounts are stored as integer cents and `NUMERIC` holds the values that are not cent-denominated. See Amendment.

## Consequences

**Easier:**

- Money arithmetic is exact at the storage layer. Money amounts are integer cents in `BIGINT` columns; unit prices, units held, rates and percentages are `NUMERIC` (amended 2026-10-11, see Amendment).
- The pay-cycle date-range resolver, the daily snapshot backfill (SP-12) and the rolling-average trend analysis (BF-03) can be expressed directly in SQL using typed date arithmetic and window functions.
- Schema changes are ordinary Alembic migrations, which reduces the cost of iterating on the S1-21 relationship model — the change most likely to need revision.
- The database rejects malformed data rather than storing it, which is a meaningful safety net for generated code.
- Local behaviour matches production, so deployment in Sprint 6 surfaces no database-specific surprises.

**Harder:**

- A container runtime is now a hard prerequisite for local development. This must be stated explicitly in the S1-30 runbook, including the installation step, since a Docker CLI without an engine fails in a way that is not self-explanatory.
- Backup and restore in Sprint 6 becomes a designed task rather than a file copy.
- Postgres consumes memory on the OCI instance that would otherwise be available to the application.
- Local data now lives in a Docker named volume rather than in the project directory — recoverable only until someone runs `docker compose down -v`.

**Commits us to:**

- `psycopg` (v3) as the driver, currently a dev dependency and to be promoted to a runtime dependency once the framework decision in ADR-002 lands.
- Alembic against Postgres for all migrations (S1-25).
- Running Postgres on the OCI compute instance in Sprint 6, including backup, restore and upgrade ownership.
- Integer cents for every money amount, in the database, in Python and across the API. No money amount is ever a `float`.
- Pinning the Postgres major version. Major upgrades require `pg_upgrade` and will not start against an existing data directory.

**Deliberately deferred:**

- Whether to use a managed Postgres service instead of self-hosting on the compute instance. Revisit in Sprint 6 if operational overhead proves higher than expected.
- Any use of Postgres-specific features beyond standard SQL (e.g. `JSONB` for raw Up API payloads, materialised views for snapshot aggregation). Available if wanted, but not assumed by this decision.

## Amendment (2026-10-11): money is stored as integer cents

The original decision assumed money would be stored as `NUMERIC` dollars, and listed "no integer-cents convention to apply" as a consequence. That is reversed. The engine choice stands.

**What changed**

- A money amount (a Transaction amount, a balance, Spend, Income, Net worth, a Trade's total, a Dividend) is an integer number of cents: `BIGINT` in Postgres, `int` in Python, a JSON number in the API.
- A value that is not cent-denominated (a unit price, units held, an interest rate, a percentage) is `NUMERIC` in Postgres and `Decimal` in Python.
- Where the two meet (price × units, a rate applied to a balance, a share or a percentage Split applied to an amount), the result is rounded to cents by a single rounding function in `domain/`. Nothing else rounds.

**Why**

- Up returns every amount as `valueInBaseUnits`, an integer, so the common case stores with no conversion.
- An `int` makes a stray float visible: `/` yields a `float` that type checks catch, where a `Decimal` built from or mixed with a float fails silently or at runtime. This matters with a large share of the code AI-generated.
- The API returns a plain number that is exact in JavaScript. A `Decimal` serialises as a string the client must never do arithmetic on.
- Rounding is forced at each division, so it is always an explicit decision. `NUMERIC` dollars allow sub-cent values to sit unnoticed in a money column.

**What it costs**

- A two-type rule to apply consistently, which is the convention the original decision set out to avoid.
- Amounts in the database, logs and tests read as `1234`, not `12.34`. Formatting to dollars happens once, on the way out.
- The portfolio code (Sprint 4) works across both types and converts at a boundary.

**Effect on the engine choice**

Exact decimal storage for money was one of the two deciding factors against SQLite, and integer cents is the workaround SQLite would have needed. That factor is weaker now. Postgres still stands on `NUMERIC` for prices, units and rates, on typed dates, on strict column typing and on full `ALTER TABLE` support.

**Still open**

- The rounding mode, and the rule for the leftover cent when a percentage Split or a 50% share does not divide evenly. Decided with the data model (S1-20 to S1-24).

## Notes

- Version pinned to `postgres:18` in `docker-compose.yml`. Note that Postgres 18 changed the image's data directory layout: `PGDATA` is now version-specific (`/var/lib/postgresql/18/docker`) and the volume mounts at `/var/lib/postgresql`, not `/var/lib/postgresql/data` as most existing documentation states.
- SQLite was a genuinely close call, not a straw man. If Fathom had been a spending tracker without the portfolio, snapshot and forecasting workstreams, SQLite would likely have been the better choice.
- Triggers to revisit: sustained operational burden from self-hosting on OCI; the analytical queries in Sprint 5 proving slow enough to warrant materialised views or a different storage approach for snapshots; or the application scope expanding beyond a single user, which would invalidate the premise that concurrency is a non-issue.
- Related: ADR-002 (backend framework) will determine the ORM, which sits on top of this decision. ADR-005 (code structure) determines where data-access code lives.

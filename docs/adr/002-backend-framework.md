# ADR-002: Backend framework

**Status:** Accepted
**Date:** 2026-09-20

Sprint task: S1-08

## Context

Python is already fixed as the backend language (3.12, per ADR-008). What is not fixed is the framework the HTTP layer, request validation and app wiring sit on.

What this project actually asks of a backend framework:

- **Single user, no admin requirement.** No roles, permissions, tenancy or user management. Authentication is one login, deliberately deferred to Sprint 6 (PL-12).
- **Typed boundaries matter more than usual.** Money, dates and derived flags (transfer, cover, net vs gross) move through every layer. A large share of the code is AI-generated, so the framework's own validation is a real safety net, not ceremony.
- **Scheduled work is first-class.** Daily Up sync (ET-02), daily EOD pricing (SP-08), daily snapshots (SP-11), manual Sync Now (ET-03). The framework only has to host or expose these — the mechanism itself is ADR-006 — but how easily it does so differs.
- **Analytical read paths.** Pay-cycle window queries, category rollups, trend comparisons, snapshot aggregation. The ORM will be used for writes and simple reads and stepped around for the heavy ones.
- **Postgres and Alembic** (ADR-004, S1-25). Django brings its own ORM and migration system; the others do not.
- **Deployment target is one small AWS-hosted instance.** Single process or a couple of workers. No horizontal scaling story needed.
- **Coupled to ADR-003.** Django's value is concentrated in server-rendered templates and admin; FastAPI's is concentrated in a typed JSON API. Choosing one framework narrows the sensible frontend options and vice versa, so these two ADRs should be settled together.

## Options Considered

### Option A: FastAPI
- Pros:
  - Pydantic validation at the boundary is the framework's default, not an add-on — strong fit for the typed-API requirement and for catching bad AI-generated handlers early.
  - Generated OpenAPI docs give a free, always-accurate contract to point AI agents and a future frontend at.
  - Small surface area; pairs naturally with SQLAlchemy + Alembic, which are already the assumed data stack.
  - Async support available if the Up sync ever wants concurrent paged fetches.
- Cons:
  - Unopinionated: project structure, auth, sessions, settings wiring and background jobs are all yours to assemble (ADR-005 and ADR-006 carry more weight as a result).
  - No batteries — no admin, no built-in forms, no template-first workflow, so a server-rendered frontend is more DIY here.
  - Async/sync mixing is a well-known foot-gun with a synchronous ORM and generated code.

### Option B: Django
- Pros:
  - Batteries included: ORM, migrations, auth, forms, sessions and admin ship in the box. The admin alone is a free CRUD surface for accounts, categories, tags and manual trade entry.
  - Strong, conventional structure that AI agents already know well — the layout decision in ADR-005 is largely made for you.
  - Mature ecosystem for exactly the parts deferred to later sprints (auth in Sprint 6, management commands for scheduled jobs).
- Cons:
  - Its ORM and migrations replace SQLAlchemy and Alembic, which contradicts the S1-25 plan as currently written — a real change, not a preference.
  - Most of the weight (multi-user auth, permissions, admin, i18n) is for problems this app does not have.
  - Typed request/response validation is not native; you add DRF or django-ninja to get it, which is another dependency and another set of conventions.
  - Template-and-forms orientation pulls ADR-003 toward server-rendered before you have decided that.

### Option C: Flask
- Pros:
  - Smallest and simplest of the three; very little framework to learn, which leaves attention for the domain problems that are the actual learning goal.
  - Completely free choice of ORM, migrations and structure — SQLAlchemy + Alembic is the standard Flask pairing.
  - Equally comfortable serving Jinja templates or a JSON API, so it constrains ADR-003 the least.
- Cons:
  - No native validation or typing story at all; Pydantic is bolted on manually, and nothing enforces it on a generated route.
  - No auto-generated API docs without extra libraries.
  - Least opinionated of the three, so the codebase's shape depends entirely on discipline and ADR-005 holding.
  - Increasingly the "neither" choice: FastAPI has taken the API use case and Django owns the full-stack one.

## Decision

**Option A — FastAPI**, running synchronously.

Two things decided it. First, a typed boundary is the default rather than an add-on: with a large share of the code AI-generated, Pydantic validating every request and response at the edge is the cheapest safety net available, and it is one the framework enforces rather than one that depends on review discipline. Second, this project is a learning exercise, and assembling the stack — router, service layer, SQLAlchemy, Alembic, settings, auth — teaches materially more than inheriting a complete set of Django conventions. Django's batteries are mostly for problems this app does not have; paying for them in structure and ORM lock-in to use the admin and little else is a bad trade here.

Endpoints are synchronous `def`, with synchronous SQLAlchemy. One user generates no concurrency pressure, and mixing sync and async around a synchronous ORM is the most common way FastAPI projects go wrong. This is revisited only if the Up sync becomes slow enough that concurrent paged fetches are worth the complexity.

## Consequences

**Accepted costs**

- **No admin.** Django's admin would have been a free CRUD surface for categories, tags, manual accounts and trade entry. Those screens now have to be built — but they are all requirements in their own right (ET-05, ET-15, ET-19, SP-01 to SP-03), so the admin was only ever a stopgap before the real UI existed. The cost is that no shortcut exists in the meantime: before a screen is built, its data is managed directly in the database.
- **Nothing is wired for you.** Router registration, session handling, error handling, logging and app startup are all assembled by hand. ADR-005 stops being cosmetic and becomes the thing that holds the codebase together.
- **Sprint 6 auth is not inherited.** Django's auth would have been near-free. The mechanism stays genuinely open and remains a Sprint 6 decision (PL-12); what this ADR records is that the free option was knowingly given up.

**What this commits the project to**

- **The planned data stack stands.** SQLAlchemy + Alembic remain as assumed in S1-25 — no rework, which a Django choice would have forced.
- **Sync throughout.** Every library choice follows: a synchronous HTTP client for Up, synchronous SQLAlchemy sessions, synchronous job entry points. Generated code that reaches for `async def` or `httpx.AsyncClient` is a review rejection, not a style preference, and this belongs in the S1-32 checklist.
- **A JSON API, not a view layer.** The backend renders no HTML. This is consistent with ADR-003 (React), and it means the API contract — not a template — is the integration surface. The generated OpenAPI schema is the contract, and is worth pointing both the frontend and AI agents at.
- **Heavy analytical reads step around the ORM.** Pay-cycle window queries, category rollups and snapshot aggregation are expected to be hand-written SQL through SQLAlchemy Core rather than ORM relationship traversal. FastAPI is neutral on this; it is noted so the pattern is deliberate when Sprint 5 arrives.

**What it makes easier**

- Typed contracts end to end, which is the main defence against AI-generated handlers doing something subtly wrong with money or dates.
- Handlers that are plain functions over a service layer, testable without an HTTP client.
- A clean separation for the Sprint 5 analysis endpoints, which are read-only and map naturally onto response schemas.

**Unaffected**

- ADR-006 is untouched. Scheduled jobs remain a separate mechanism; FastAPI simply provides no scheduler of its own, so the job entry points are plain Python modules.

## Notes

- Recorded in `CLAUDE.md` (S1-31) as the standing stack, together with the sync rule — generated code otherwise defaults to whatever is most common in training data, which for FastAPI is async.
- Litestar was considered and set aside: Pydantic-native with more built-in structure, but a thinner ecosystem and less represented in the training data AI agents draw on.
- Triggers to revisit: a multi-user or household requirement appearing (would have favoured Django); the Up sync becoming slow enough to want concurrency (would reopen the sync decision, not the framework one).
- Depends on: S1-07 (ADR folder and template). Feeds: ADR-003 (React consumes this API), ADR-005, ADR-006, S1-26 to S1-28 (walking skeleton), S1-31 (CLAUDE.md), S1-32 (review checklist).

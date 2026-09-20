# ADR-005: Code structure and layering convention

**Status:** Accepted
**Date:** 2026-09-20

Sprint task: S1-11

## Context

The repository currently has `docs/` and config, and no application code beyond `src/fathom/config.py`. The layout is decided now, before the walking skeleton (S1-26 to S1-28), because a significant share of the code from Sprint 2 onward is AI-generated: if the structure is not stated, generated code will invent one file at a time and the shape will be set by accident.

What the structure has to hold over six sprints:

- **Five to six feature areas** that arrive at different times: accounts and transactions (Sprint 2), manual accounts, import and netting (Sprint 3), portfolio (Sprint 4), analysis and forecasting (Sprint 5).
- **Domain rules that must live in exactly one place.** Transfers and covers never count as spend (SA-07). Spend is net of reimbursements by default, gross behind a toggle (SA-05). The pay-cycle month is the default period everywhere (SA-01). These are cross-cutting rules, and a duplicate implementation in a second place is a bug waiting for a Sprint 5 report to expose it.
- **Non-HTTP entry points.** Scheduled jobs (ADR-006), CSV importers, the Alembic environment and any CLI spike all need to reach the service layer without going through a web request.
- **An external-provider boundary.** The Up client and the yfinance price provider are both explicitly meant to be swappable behind an interface.
- **Testability.** S1-06 sets up an isolated test database; pure domain logic (relationship rules, netting, period maths) should be testable without one.
- **A reviewable diff.** S1-32's review checklist needs a structural rule to check generated code against — "is this in the right layer" only works if the layers are named.

This ADR fixes two things: the module layout, and the boundary rules between layers.

## Options Considered

### Option A: Feature modules (vertical slices)
`src/fathom/{accounts,transactions,portfolio,analysis,forecasting}/`, each containing its own `router.py`, `service.py`, `repository.py`, `models.py`, `schemas.py`; plus a shared `core/` for config, database session, domain primitives and cross-cutting rules.

- Pros:
  - A feature lands as one directory — easy to scope an AI task to "work only inside `transactions/`" and easy to review the resulting diff.
  - Matches how the sprints are organised, so each sprint mostly adds a folder rather than editing five.
  - Related code sits together; navigating one feature does not mean four open files in four trees.
- Cons:
  - Cross-feature logic has no obvious home — net worth spans accounts, portfolio and manual holdings, and forecasting reads from everything. Something has to own `core/` discipline or it becomes a junk drawer.
  - The ORM models still need one metadata registry and one Alembic target, so models are less independent than the layout suggests.
  - Easy for the layering *within* a slice to drift feature by feature unless the boundary rules are stated separately.

### Option B: Technical layers (horizontal)
`src/fathom/{api,services,repositories,models,schemas}/`, with a module per feature inside each.

- Pros:
  - The layering is impossible to miss — the directory name is the layer, so a misplaced file is visible at a glance.
  - Simplest rule to give an AI agent and to check in review: routers import services, services import repositories, nothing goes backwards.
  - Conventional and widely represented in training data, so generated code lands in the right shape more often.
- Cons:
  - One feature is spread across five directories; a single Sprint 3 change touches all of them.
  - Encourages layers to grow flat and large (`services/` with fifteen unrelated modules by Sprint 5).
  - Says nothing about which features may call which — the coupling it prevents is vertical, not horizontal.

### Option C: Flat pragmatic package
`src/fathom/` with modules named by concern (`up_client.py`, `transactions.py`, `categorisation.py`, `portfolio.py`, `reports.py`), no enforced layering, split out only when a module gets uncomfortable.

- Pros:
  - Least ceremony and least indirection — appropriate to a single-user app that will never have a team.
  - Structure emerges from real pressure rather than being guessed before any code exists.
  - Fastest to move in during Sprints 1 and 2.
- Cons:
  - Works directly against the reason this task exists: with generated volume, "split it out later" reliably becomes "never".
  - No stated boundary means business rules end up inline in route handlers, which is exactly how SA-07-style rules get duplicated.
  - Gives the S1-32 review checklist nothing structural to enforce.

## Decision

**Option B — technical layers**, strictly enforced, with a separate pure `domain/` package for cross-cutting rules.

Three things decided it. The directory name is the layer, so misplaced code is visible in a diff — a router touching the database or a service making an HTTP call stands out immediately, which matters most when reviewing generated code you did not write. The rule it produces is one sentence long and therefore actually gives an agent something to follow: routers import services, services import repositories, nothing goes backwards. And being forced to place every new file in a named layer builds the habit deliberately, which is worth more here than the navigational convenience of feature folders — this project is a learning exercise, and layering implied by a folder structure is layering you never have to think about.

The cost — one feature change touching several directories — is accepted. At this scale that is a minor inconvenience, not an architectural problem.

### Layout

```
src/fathom/
  api/            FastAPI routers, request/response wiring only
  services/       use cases and orchestration; the only entry point for jobs and importers
  repositories/   all database access; the only place SQLAlchemy queries live
  models/         SQLAlchemy ORM models (single metadata registry, Alembic target)
  schemas/        Pydantic request/response models
  domain/         pure business rules; no ORM, no database, no I/O
  core/           config, database session, logging, shared infrastructure
  jobs/           scheduled job entry points (ADR-006)
  providers/      external integrations: Up client, price provider
```

Each layer holds a module per feature (`api/transactions.py`, `services/transactions.py`, and so on) rather than growing flat.

### Boundary rules

1. **Direction.** `api` → `services` → `repositories` → database. Nothing imports upward, ever.
2. **No shortcuts.** A router never touches a repository directly, not even for a one-line read. A pass-through service function is the cost of having no precedent for skipping the layer.
3. **No ORM models above the service layer.** Services return Pydantic schemas. Persistence types never reach a router or a response body.
4. **`domain/` is pure.** Transfers and covers never counting as spend (SA-07), net-of-reimbursement (SA-05) and pay-cycle period boundaries (SA-01) live here as functions over plain values — no session, no models, no I/O. Any service may import it; it imports nothing from the app.
5. **Providers behind an interface.** The Up client and the price provider live in `providers/`, are used only by services, and are never imported by a router.
6. **Jobs and importers call services.** Never repositories, never routers — so an ADR-006 change does not ripple through the codebase.
7. **Enforcement is automated.** A layer contract in `import-linter` runs in CI (S1-29); a boundary violation fails the pipeline.

## Consequences

**What this commits the project to**

- **A sixth top-level directory that is not a layer.** `domain/` sits outside the router-service-repository stack by design. It needs its own line in CLAUDE.md explaining that purity is the point, or generated code will put a database call in it within a sprint.
- **Pass-through boilerplate.** Rule 2 guarantees service functions that do nothing but call a repository. That is the accepted price of a rule with no exceptions; the moment one trivial read is allowed to skip a layer, the boundary stops being checkable.
- **A schema for every response.** Rule 3 means no endpoint ever returns an ORM object, so `schemas/` grows alongside `models/`. This dovetails with ADR-003's generated TypeScript client, which consumes exactly these schemas.
- **A new dev dependency and CI step.** `import-linter` and its contract configuration join the repo, and S1-29's pipeline gains a boundary check. It needs to be added when the layout lands, not retrofitted after the first violations exist.
- **A stated position on the frontend tree.** ADR-003 introduced a second codebase. This ADR governs `src/fathom/` only; the React structure is out of scope here and needs its own convention before Sprint 2.

**What it makes easier**

- `domain/` is testable without a database, so the highest-risk logic in the project — the relationship and netting rules from S1-21, which are on the hand-written side of the human/AI split — gets fast unit tests that do not need the S1-06 fixture.
- Review has a structural question with a yes-or-no answer: is this file in the right directory, and does it import only downward. CI answers most of it before you read the diff.
- AI task scoping gets a precise instruction: "add the endpoint in `api/`, the use case in `services/`, the query in `repositories/`; put no logic in the router."

**Accepted costs and known pressure points**

- **A feature change touches four or five directories.** Adding transaction splitting in Sprint 3 means a model, a schema, a repository, a service and a router. Accepted as the trade for visible layering.
- **Layers grow flat.** By Sprint 4 or 5, `services/` and `repositories/` will hold a module per feature area and start to feel wide. The response is to split each layer into sub-packages (`services/portfolio/`), not to abandon the layering. Worth deciding when it happens rather than drifting.
- **Heavy analytical reads need a home.** Sprint 5's window-function queries are repository code by this scheme, even though they serve a single report. If a `repositories/analysis.py` starts to look like a reporting engine, that is the signal to revisit — not a reason to put SQL in a service.

## Notes

- Written into `CLAUDE.md` (S1-31) as the directory tree plus the seven rules verbatim, and into the README's repository layout section, which currently says the module structure is pending this ADR.
- Feature modules (Option A) were the closer alternative and remain the natural migration target if the multi-directory cost becomes annoying: each layer already holds a module per feature, so the transposition is mechanical rather than a rewrite.
- Ports and adapters was considered and set aside as too heavy for a single-user app, though `domain/` borrows its central idea — the business rules know nothing about the framework or the database.
- Triggers to revisit: a layer growing past comfortable navigation; repeated CI boundary failures suggesting the rules fight the work rather than protect it; the Sprint 5 forecasting code wanting a genuinely separate domain core.
- Depends on: S1-07, ADR-002 (FastAPI leaves the layout genuinely open, which is why this decision has weight). Feeds: S1-26 to S1-28 (the first code to follow it), S1-29 (CI boundary check), S1-31 (CLAUDE.md), S1-32 (review checklist).
